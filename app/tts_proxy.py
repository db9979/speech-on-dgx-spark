"""Qwen3-TTS front end for the vllm-omni engine (backend "vllm-omni").

The engine (native vllm-omni venv, 127.0.0.1 only) does the work, including streaming:
`stream: true` returns OpenAI `speech.audio.*` Server-Sent Events with base64 PCM
16 bit mono 24 kHz chunks. This service sits on the public TTS port and adds the API
key, defaults (voice, language, format), routing of VoiceDesign requests to the second
engine, and the counters the panel shows. Request and stream pass through unchanged.

Designed voices (Eigene Stimmen gestalten, panel stimmdesign.py, Dominik 2026-11-11): a voice named "sd-…" or
"eigen-…" is a stored sample in VOICES_DIR (stimmablage.py); when the main engine cannot clone (CustomVoice), the
third engine "klon" (tts.klon_enabled, a Base model) speaks it, and when that one is not up the main engine's
default voice stands in. The VoiceDesign engine runs on demand when tts.voicedesign_leerlauf_min is above 0: the
first request starts it (503 "TTS engine loading" until it answers) and it stops after that many idle minutes.
"""
import asyncio
import base64
import json
import os
import subprocess
import time
from collections import deque

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

import kurzref

from common import (dauerlauf, FOLGE_HEADER, BodyLimit, GateFull, KeyedCORS, PrioGate, inside, outside_view, api_key_dependency,
                    api_key_ok, engine_crash_reason, klon_noetig, load_config, quiet_access_log, SpeechMark, stage_of, STATE)
from textnorm import (MAX_INPUT, apply_pronunciations, clean_text, guess_language, hide_secrets, parse_pronunciations,
                      speak_abbreviations, speak_numbers, speech_markdown)

VOICES_DIR = os.environ.get("SPEECH_SPARK_VOICES", "/var/lib/speech-spark/voices")  # panel tab "Stimmen"
LANGUAGES = ["auto", "Chinese", "English", "Japanese", "Korean", "German", "French",
             "Russian", "Portuguese", "Spanish", "Italian"]
PCM_BYTES_PER_S = 24000 * 2  # Qwen3-TTS: 24 kHz, 16 bit, mono

cfg = load_config("tts")
PRONUNCIATION = parse_pronunciations(cfg.get("pronunciation", ""))  # the proxy restarts on config changes
app = FastAPI(title="Qwen3-TTS via vllm-omni (DGX Spark)")
# innermost: only requests that passed the size limit and API key count as speech
app.add_middleware(SpeechMark)
app.add_middleware(KeyedCORS)
# bodies are refused before they are read when too large or without the API key
app.add_middleware(BodyLimit, default=20 * 1024**2, gate=api_key_ok, gated=("/v1/",))
auth = [Depends(api_key_dependency())]
client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5))
started = time.time()
stats = {"requests": 0, "failures": 0, "streams": 0, "last_error": None, "active": 0}
recent = deque(maxlen=50)  # (seconds, audio_seconds or None, time to first audio or None)
_voice_cache = {}  # engine role -> (fetched_at, [voices])


def engines():
    out = {"main": (cfg["model"], cfg["engine_port"])}
    if cfg.get("voicedesign_enabled"):
        out["design"] = (cfg["voicedesign_model"], cfg["voicedesign_port"])
    if klon_noetig(cfg):
        out["klon"] = (cfg.get("klon_model", ""), cfg.get("klon_port", 31019))
    return out


UNIT_OF = {"main": "speech-spark-tts-engine", "design": "speech-spark-tts-design", "klon": "speech-spark-tts-klon"}
EIGENE = ("sd-", "eigen-")   # the names of designed voices (stimmablage.NAME)
design = {"used": 0.0, "start": 0.0}   # the VoiceDesign engine on demand: last request, last start (time.time)
DESIGN_START_S = 600        # a start on demand counts as running this long before a new start is tried


def design_bedarf():
    """Minutes the VoiceDesign engine stays loaded without a request; 0 = always loaded (it starts with the machine)."""
    m = cfg.get("voicedesign_leerlauf_min", 5)
    return m if isinstance(m, int) and not isinstance(m, bool) and 0 <= m <= 120 else 5


def _systemctl(action, unit):
    """sudo systemctl for exactly the VoiceDesign unit (the sudoers line of install.sh allows start and stop)."""
    try:
        return subprocess.run(["sudo", "-n", "/usr/bin/systemctl", action, unit], capture_output=True, text=True,
                              timeout=30).returncode
    except Exception:
        return 1


async def design_bereit(status):
    """On demand: starts the stopped VoiceDesign engine once (the request still gets its 503 "loading"). A "blocked"
    or "error" left in its state file by an earlier start counts as stopped while the unit is not running: a Hörstück
    or a "▶ Probe" an hour later tries again (at most every DESIGN_START_S), never the old word for good (2026-11-12)."""
    design["used"] = time.time()
    if not design_bedarf() or time.time() - design["start"] < DESIGN_START_S:
        return status
    alt = status
    if status in ("blocked", "error") and await asyncio.to_thread(unit_active, UNIT_OF["design"]) not in ("active", "activating"):
        status = "stopped"
    if status != "stopped":
        return status
    design["start"] = time.time()
    rc = await asyncio.to_thread(_systemctl, "start", UNIT_OF["design"])
    print("tts: voicedesign start" if rc == 0 else "tts: voicedesign start fehler", flush=True)
    return "loading" if rc == 0 else alt


async def design_leerlauf():
    """Stops the VoiceDesign engine on demand after design_bedarf() minutes without a request."""
    while True:
        await asyncio.sleep(30)
        m = design_bedarf()
        if m and design["used"] and time.time() - design["used"] > m * 60 and "design" in engines():
            design["used"], design["start"] = 0.0, 0.0
            rc = await asyncio.to_thread(_systemctl, "stop", UNIT_OF["design"])
            print("tts: voicedesign gestoppt leerlauf" if rc == 0 else "tts: voicedesign stop fehler", flush=True)


def model_kind(model):
    name = model.lower()
    return "voice_design" if "voicedesign" in name else "base" if name.endswith("-base") else "custom_voice"


def unit_active(unit):
    try:
        return subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except Exception:
        return "unknown"



def sub_state(unit):
    try:
        return subprocess.run(["systemctl", "show", unit, "-p", "SubState", "--value"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return "unknown"


async def engine_status(role):
    """ready | loading | blocked | error | stopped, plus a message."""
    model, port = engines()[role]
    try:
        r = await client.get(f"http://127.0.0.1:{port}/health", timeout=2)
        if r.status_code == 200:
            return "ready", None
    except httpx.HTTPError:
        pass
    unit = UNIT_OF[role]
    # systemctl and journalctl block for a moment: in a worker thread (only while the engine is not up)
    return await asyncio.to_thread(_not_ready, role, unit)


def _not_ready(role, unit):
    try:
        with open(os.path.join(STATE, f"speech-spark-tts-{role}.json")) as f:
            st = json.load(f)
    except Exception:
        st = {}
    active = unit_active(unit)
    if st.get("status") in ("blocked", "error") and active != "active":
        return st["status"], st.get("error")
    if active == "activating" and sub_state(unit) == "auto-restart":
        reason = engine_crash_reason(unit)
        return "error", f"engine exited and restarts every 30 s: {reason or 'see panel Logs -> TTS-Engine'}"
    if active in ("active", "activating"):
        return "loading", (st.get("status") == "loading" and st.get("error")) or "engine starting (first start downloads the model)"
    return "stopped", f"{unit} is {active}"


def clone_voices():
    try:
        return sorted(f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))
    except OSError:
        return []


_ref_cache = {}  # voice -> (mtime, data URL, transcript)
_short = {}      # voice -> (mtime, ref_max_s, data URL, transcript): the shorter reference (kurzref.py)
_short_tried = {}  # voice -> (mtime, ref_max_s, time, for good): not shortened, why is in the log
_short_busy = set()
SHORT_RETRY_S = 600


def wav_url(data):
    return "data:audio/wav;base64," + base64.b64encode(data).decode()


def ref_limit():
    m = cfg.get("ref_max_s", 0)
    return m if m in (8, 10, 15) and not isinstance(m, bool) else 0


def clone_reference(name):
    """The recorded reference of a cloned voice as vllm-omni's Base task wants it; with tts.ref_max_s the shorter
    piece once it is cut (until then, and when it cannot be cut, the whole recording)."""
    wav = os.path.join(VOICES_DIR, name + ".wav")
    mtime = os.path.getmtime(wav)
    lim = ref_limit()
    if lim:
        s = _short.get(name)
        if s and s[:2] == (mtime, lim):
            return s[2], s[3]
        tried = _short_tried.get(name)
        if name not in _short_busy and not (tried and tried[:2] == (mtime, lim)
                                            and (tried[3] or time.time() - tried[2] < SHORT_RETRY_S)):
            try:
                asyncio.get_running_loop().create_task(shorten(name))
            except RuntimeError:   # no loop (a plain call): the whole recording this time
                pass
    cached = _ref_cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    with open(wav, "rb") as f:
        url = wav_url(f.read())
    txt = os.path.join(VOICES_DIR, name + ".txt")
    text = open(txt).read().strip() if os.path.exists(txt) else ""
    _ref_cache[name] = (mtime, url, text)
    return url, text


async def transcribe(wav):
    """What the local speech recognition hears in wav (this machine's ASR service), None when it cannot say."""
    full = load_config()
    if not full["asr"].get("enabled"):
        return None
    key = full.get("api", {}).get("key", "")
    r = await client.post(f"http://127.0.0.1:{full['asr']['port']}/v1/audio/transcriptions", timeout=60,
                          headers={"Authorization": f"Bearer {key}"} if key else {},
                          files={"file": ("referenz.wav", wav)})
    text = r.json().get("text") if r.status_code == 200 else None
    return text if isinstance(text, str) and text.strip() else None


async def shorten(name):
    """Cuts the reference of a voice once (kurzref.py) and keeps the piece; every result writes one log line."""
    lim = ref_limit()
    path = os.path.join(VOICES_DIR, name + ".wav")
    if not lim or name in _short_busy:
        return
    _short_busy.add(name)

    def gave_up(why, for_good=False):
        _short_tried[name] = (mtime, lim, time.time(), for_good)
        print(f"tts: referenz nicht gekuerzt {why}", flush=True)
    mtime = None
    try:
        mtime = os.path.getmtime(path)
        hit = await asyncio.to_thread(kurzref.cached, VOICES_DIR, name, mtime, lim)
        if hit:
            _short[name] = (mtime, lim, wav_url(hit[0]), hit[1])
            print("tts: referenz kurz geladen", flush=True)
            return
        got = await asyncio.to_thread(kurzref.piece, path, lim)   # up to 60 MB: never in the event loop
        if isinstance(got, str):
            return gave_up(got, True)
        piece, full_s, kept_s = got
        txt = os.path.join(VOICES_DIR, name + ".txt")
        own = open(txt).read().strip() if os.path.exists(txt) else ""
        text = ""
        if own:   # without a transcript only the timbre is used (x_vector_only_mode): no words to match
            heard = await transcribe(piece)
            if heard is None:
                return gave_up("spracherkennung")
            text = kurzref.keep_words(own, heard)
            if not text:
                return gave_up("passt nicht", True)
        await asyncio.to_thread(kurzref.store, VOICES_DIR, name, mtime, lim, piece, text, full_s, kept_s)
        _short[name] = (mtime, lim, wav_url(piece), text)
        print(f"tts: referenz gekuerzt {full_s:.1f} s auf {kept_s:.1f} s", flush=True)
    except (OSError, ValueError, httpx.HTTPError) as e:
        gave_up(f"fehler {type(e).__name__}")
    finally:
        _short_busy.discard(name)


MAX_REF = 15 * 1024 * 1024  # characters of a data: URL (about 11 MB of audio)


def check_reference(body):
    """A reference recording only as data: URL. vllm-omni would fetch an http(s) or file address
    itself, from inside the Spark (home network, local files)."""
    ref = body.get("ref_audio")
    if ref is not None and (not isinstance(ref, str) or not ref.startswith("data:audio/") or len(ref) > MAX_REF):
        raise HTTPException(400, "ref_audio: only a data:audio/... URL of at most 15 MB")
    emb = body.get("speaker_embedding")
    if emb is not None and (not isinstance(emb, list) or len(emb) > 8192
                            or not all(isinstance(x, (int, float)) for x in emb)):
        raise HTTPException(400, "speaker_embedding: a list of at most 8192 numbers")


def apply_clone(body):
    """Base checkpoints only clone: turn the voice name into the stored reference recording."""
    if body.get("ref_audio") or body.get("speaker_embedding"):
        body["task_type"] = "Base"
        return
    known = {v.lower(): v for v in clone_voices()}
    if not known:
        raise HTTPException(400, "the Base model needs a cloned voice: record one in the panel (tab Stimmen/Voices)")
    voice = str(body.get("voice") or "")
    name = known.get(voice.lower()) or known.get(str(cfg.get("default_voice", "")).lower()) or next(iter(known.values()))
    ref, text = clone_reference(name)
    body.update(task_type="Base", ref_audio=ref)
    if text:
        body["ref_text"] = text
    else:
        body["x_vector_only_mode"] = True  # without a transcript only the voice timbre is used
    body.pop("voice", None)
    body.pop("instructions", None)  # Base checkpoints do not follow instructions


def eigene_stimme(body):
    """A designed voice (sd-…, eigen-…) whose sample lies here, asked without a reference of its own."""
    v = str(body.get("voice") or "")
    return v.startswith(EIGENE) and not body.get("ref_audio") and v in clone_voices()


_ersatz = {}   # status -> time of the last log line, so a missing engine is named once a minute


async def eigene_rolle(body):
    """The engine for a designed voice: the main one when it clones itself (Base), else "klon"; when that one is
    off or not up, the main engine's default voice stands in (the request still gets its answer)."""
    if model_kind(cfg["model"]) == "base":
        return "main"
    status = (await engine_status("klon"))[0] if "klon" in engines() else "aus"
    if status == "ready":
        return "klon"
    body.pop("voice", None)
    if time.time() - _ersatz.get(status, 0) > 60:
        _ersatz[status] = time.time()
        print(f"tts: eigene stimme ersatz {status}", flush=True)
    return "main"


async def engine_voices(role):
    if model_kind(engines()[role][0]) == "base":
        return clone_voices()
    cached = _voice_cache.get(role)
    if cached and time.time() - cached[0] < 60:
        return cached[1]
    model, port = engines()[role]
    try:
        r = await client.get(f"http://127.0.0.1:{port}/v1/audio/voices", timeout=5)
        voices = r.json().get("voices", []) if r.status_code == 200 else []
        voices += [v["name"] for v in r.json().get("uploaded_voices", []) if "name" in v]
    except Exception:
        voices = []
    if voices:
        _voice_cache[role] = (time.time(), voices)
    return voices


async def warm_up(role):
    """One short request right after an engine comes up, so the first real request does not
    pay for the remaining compilation and cache warm-up."""
    model, port = engines()[role]
    kind = model_kind(model)
    body = {"input": "Hallo, ich bin bereit.", "model": model, "response_format": "pcm", "language": "Auto"}
    if kind == "base":
        if not clone_voices():
            return  # nothing to clone yet
        if ref_limit():   # the shorter references first, so already the first sentence gets them
            for name in clone_voices():
                await shorten(name)
        apply_clone(body)
    elif kind == "voice_design":
        body.update(task_type="VoiceDesign", instructions="ruhige Stimme")
    else:
        voices = await engine_voices(role)
        body["voice"] = cfg.get("default_voice") if cfg.get("default_voice") in voices else (voices or [None])[0]
    try:
        t0 = time.time()
        r = await client.post(f"http://127.0.0.1:{port}/v1/audio/speech", json=body)
        print(f"warm-up {role}: HTTP {r.status_code} in {time.time() - t0:.1f} s", flush=True)
    except httpx.HTTPError as e:
        print(f"warm-up {role} failed: {e}", flush=True)


@app.on_event("startup")
async def watch_design():
    dauerlauf("tts", "voicedesign-leerlauf", design_leerlauf)


@app.on_event("startup")
async def watch_engines():
    async def loop():
        ready = {}
        while True:
            for role in engines():
                now = (await engine_status(role))[0] == "ready"
                if now and not ready.get(role):
                    await warm_up(role)
                ready[role] = now
            await asyncio.sleep(5)
    dauerlauf("tts", "aufwaermen", loop)


@app.get("/health")
async def health(request: Request):
    if not inside(request):
        return outside_view({"service": "tts", "status": (await engine_status("main"))[0]})
    status, error = await engine_status("main")
    lat = [r[0] for r in recent]
    rtf = [r[0] / r[1] for r in recent if r[1]]
    ttfa = [r[2] for r in recent if r[2] is not None]
    out = {
        "service": "tts", "backend": "vllm-omni", "status": status, "error": error,
        "model": cfg["model"], "model_kind": model_kind(cfg["model"]),
        "uptime_s": round(time.time() - started), "load_seconds": None,
        "requests": stats["requests"], "failures": stats["failures"], "streams": stats["streams"],
        "busy": stats["active"] > 0, "last_error": stats["last_error"],
        "avg_latency_s": round(sum(lat) / len(lat), 3) if lat else None,
        "avg_rtf": round(sum(rtf) / len(rtf), 3) if rtf else None,
        "avg_ttfa_s": round(sum(ttfa) / len(ttfa), 3) if ttfa else None,
    }
    if "design" in engines():
        out["voicedesign"] = dict(zip(("status", "error"), await engine_status("design")))
        out["voicedesign"]["bedarf_min"] = design_bedarf()
    if "klon" in engines():
        out["klon"] = dict(zip(("status", "error"), await engine_status("klon")))
    out["queue"] = gate("main").view()
    return out


@app.get("/v1/models", dependencies=auth)
def models():
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "local"}
                                       for m, _ in engines().values()]}


@app.get("/v1/voices")
async def voices_for_panel(request: Request):
    if not inside(request):
        raise HTTPException(401, "invalid or missing API key")
    status, _ = await engine_status("main")
    voices = [v for v in await engine_voices("main") if not v.startswith(EIGENE)] if status == "ready" else []
    return {"model_kind": model_kind(cfg["model"]) if status == "ready" else None, "voices": voices,
            "languages": LANGUAGES, "voicedesign": "design" in engines(),
            "voicedesign_bedarf": design_bedarf() if "design" in engines() else None,
            "klon": (await engine_status("klon"))[0] if "klon" in engines() else None,
            "eigene": [v for v in clone_voices() if v.startswith(EIGENE)]}


@app.get("/v1/audio/voices", dependencies=auth)
async def audio_voices():
    _, port = engines()["main"]
    r = await client.get(f"http://127.0.0.1:{port}/v1/audio/voices")
    return Response(ohne_eigene(r.content), status_code=r.status_code, media_type="application/json")


def ohne_eigene(content):
    """The engine's list of voices without the designed ones (EIGENE): they belong to profiles, the panel alone
    decides who speaks with which (stimmdesign.stimme_ok), and this list goes to every holder of the API key.
    With the Base model as the main engine the samples sit in its own folder and were listed (code review 2026-11-11)."""
    try:
        d = json.loads(content)
    except ValueError:
        return content
    if not isinstance(d, dict):
        return content
    if isinstance(d.get("voices"), list):
        d["voices"] = [v for v in d["voices"] if not (isinstance(v, str) and v.startswith(EIGENE))]
    if isinstance(d.get("uploaded_voices"), list):
        d["uploaded_voices"] = [v for v in d["uploaded_voices"]
                                if not (isinstance(v, dict) and str(v.get("name", "")).startswith(EIGENE))]
    return json.dumps(d).encode()


# Priority for people (panel stufe.py): as many requests at once as the engine takes, the rest wait here
# by stage instead of in the engine's first-come queue (one gate per engine)
gates = {}


def gate(role):
    if role not in gates:
        n = cfg.get("engine_max_seqs", 4)
        gates[role] = PrioGate(n if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 64 else 4)
    return gates[role]


def fail(msg):
    stats["failures"] += 1
    stats["last_error"] = {"time": time.time(), "error": msg}


@app.post("/v1/audio/speech", dependencies=auth)
async def speech(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be JSON")
    if not isinstance(body, dict) or not str(body.get("input", "")).strip():
        raise HTTPException(400, "field 'input' is required")
    if len(str(body["input"])) > MAX_INPUT:
        raise HTTPException(400, f"input: at most {MAX_INPUT} characters per request")
    check_reference(body)

    role = "main"
    if str(body.get("task_type", "")).lower() == "voicedesign" and model_kind(cfg["model"]) != "voice_design":
        if "design" not in engines():
            raise HTTPException(400, "VoiceDesign is not enabled on this server (panel: Konfiguration -> Sprachausgabe)")
        role = "design"
    elif eigene_stimme(body):
        role = await eigene_rolle(body)
    model, port = engines()[role]
    status, error = await engine_status(role)
    if role == "design":
        status = await design_bereit(status)
    if status != "ready":
        if role == "design" and status == "loading":
            raise HTTPException(503, "TTS engine loading: VoiceDesign starts on demand", headers={"Retry-After": "20"})
        raise HTTPException(503, f"TTS engine {status}: {error or ''}".strip())

    # always, whatever clean_text says: no Markdown signs, no secrets (textnorm.speech_markdown, SECRET_HINT)
    body["input"] = await asyncio.to_thread(lambda x: hide_secrets(speech_markdown(x), body.get("language")), str(body["input"]))
    if cfg.get("clean_text", True):
        body["input"] = await asyncio.to_thread(clean_text, body["input"], calm=cfg.get("calm", True))
        if not body["input"]:
            raise HTTPException(400, "nothing left to speak after removing emojis and markup")
    stream = bool(body.get("stream")) or body.get("stream_format") in ("sse", "audio")
    # vllm-omni makes the first audio chunk bigger when several requests run at once (2.4 s to
    # the first audio with 4 parallel requests on the Spark); a fixed small first chunk keeps it short.
    if stream and cfg.get("initial_chunk_frames"):
        body.setdefault("initial_codec_chunk_frames", int(cfg["initial_chunk_frames"]))
    body["model"] = model  # vLLM checks this field; clients send anything (tts-1, qwen3-tts, ...)
    body.setdefault("response_format", "pcm" if stream else "mp3")
    if not body.get("language") or str(body["language"]).lower() == "auto":
        lang = cfg.get("default_language") or "auto"
        body["language"] = "Auto" if lang.lower() == "auto" else lang
        if body["language"] == "Auto":
            body["language"] = guess_language(body["input"]) or "Auto"
    if cfg.get("pronunciation"):  # user's list, before numbers so "GB10 = Ge Be zehn" wins
        body["input"] = apply_pronunciations(body["input"], PRONUNCIATION)
    if cfg.get("numbers", "words") != "off":
        try:
            body["input"] = speak_abbreviations(body["input"], body["language"])   # "z. B." and "€/Monat" in full
            body["input"] = speak_numbers(body["input"], body["language"], cfg.get("numbers", "words"))
        except Exception as e:  # never fail a request over number formatting
            print(f"speak_numbers failed: {type(e).__name__}: {e}", flush=True)
    if "instruct" in body and "instructions" not in body:  # older field name of this API
        body["instructions"] = body.pop("instruct")
    if not body.get("instructions") and cfg.get("default_instruct"):
        body["instructions"] = cfg["default_instruct"]
    # Sampling: Qwen's defaults (temperature 0.9, top_p 1.0) vary tempo and tone a lot between
    # sentences. Server defaults from the config apply unless the request sets its own, either in
    # vLLM-Omni's "extra_params" or top-level (easier to put into a client's extra-parameters box).
    extra = body.get("extra_params") if isinstance(body.get("extra_params"), dict) else {}
    for k in ("temperature", "top_p", "top_k"):
        if k in body:
            extra.setdefault(k, body.pop(k))
        if k not in extra and cfg.get(k) is not None:
            extra[k] = cfg[k]
    if extra:
        body["extra_params"] = extra
    # A fixed seed keeps the voice consistent when a client sends a reply sentence by sentence.
    if body.get("seed") is None and isinstance(cfg.get("seed"), int) and cfg["seed"] >= 0:
        body["seed"] = cfg["seed"]
    if role == "klon" or (role == "main" and model_kind(model) == "base"):
        apply_clone(body)
    elif role == "main" and model_kind(model) != "voice_design":
        known = {v.lower(): v for v in await engine_voices(role)}
        voice = str(body.get("voice") or cfg.get("default_voice") or "")
        # unknown names (e.g. OpenAI's "alloy") fall back to the configured default voice
        body["voice"] = known.get(voice.lower()) or known.get(str(cfg.get("default_voice", "")).lower()) or voice
    else:
        body.pop("voice", None)

    # vllm-omni refuses `speed` on streamed requests; the proxy stretches streamed PCM itself
    stretch = None
    if stream:
        try:
            speed = float(body.pop("speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        if abs(speed - 1.0) > 0.01 and body["response_format"] == "pcm":
            try:
                from tempo import Stretcher
                stretch = Stretcher(min(2.0, max(0.5, speed)))
            except ImportError:  # numpy missing (older install): normal tempo
                print("speed ignored: numpy is not installed", flush=True)

    url = f"http://127.0.0.1:{port}/v1/audio/speech"
    g = gate(role)
    try:
        # a follow-up sentence of an answer that still plays waits behind first sentences (common.FOLGE_HEADER)
        ticket = await g.enter(stage_of(request), folge=request.headers.get(FOLGE_HEADER) == "1")
    except GateFull:
        raise HTTPException(503, "TTS busy: too many requests waiting")
    stats["requests"] += 1
    t0 = time.time()
    if not stream:
        stats["active"] += 1
        try:
            r = await client.post(url, json=body)
        except httpx.HTTPError as e:
            fail(f"engine unreachable: {e}")
            raise HTTPException(502, f"engine unreachable: {e}")
        finally:
            stats["active"] -= 1
            g.leave(ticket)
        dt = time.time() - t0
        if r.status_code != 200:
            fail(r.text[:300])
        else:
            audio_s = len(r.content) / PCM_BYTES_PER_S if body["response_format"] == "pcm" else None
            recent.append((dt, audio_s, None))
        headers = {k: v for k, v in r.headers.items() if k.lower().startswith("x-vllm-omni")}
        headers["X-Processing-Seconds"] = f"{dt:.3f}"
        headers.update(PrioGate.headers(ticket))
        return Response(r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type"), headers=headers)

    # Streaming: open the upstream stream first so engine errors still become proper HTTP errors.
    stats["streams"] += 1
    req = client.build_request("POST", url, json=body)
    try:
        upstream = await client.send(req, stream=True)
    except BaseException as e:
        g.leave(ticket)
        if isinstance(e, httpx.HTTPError):
            fail(f"engine unreachable: {e}")
            raise HTTPException(502, f"engine unreachable: {e}")
        raise
    if upstream.status_code != 200:
        g.leave(ticket)
        content = await upstream.aread()
        await upstream.aclose()
        fail(content.decode(errors="replace")[:300])
        return Response(content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"))

    sse = "event-stream" in upstream.headers.get("content-type", "")

    def sse_audio(pcm):
        return ("event: speech.audio.delta\ndata: " + json.dumps({"type": "speech.audio.delta",
                                       "audio": base64.b64encode(pcm).decode(), "response_format": "pcm"}) + "\n\n").encode()

    async def stretched():
        """The upstream stream with every audio piece run through the tempo stretcher."""
        buf = b""
        async for chunk in upstream.aiter_raw():
            if not sse:
                yield stretch.feed(chunk)
                continue
            buf += chunk
            while b"\n\n" in buf:
                event, buf = buf.split(b"\n\n", 1)
                data = next((ln[5:] for ln in event.split(b"\n") if ln.startswith(b"data:")), b"")
                try:
                    ev = json.loads(data) if data.strip() and data.strip() != b"[DONE]" else {}
                except ValueError:
                    ev = {}
                if ev.get("type") == "speech.audio.delta" and ev.get("audio"):
                    pcm = stretch.feed(base64.b64decode(ev["audio"]))
                    if pcm:
                        yield sse_audio(pcm)
                    continue
                if ev.get("type") in ("speech.audio.done", "speech.audio.error") or data.strip() == b"[DONE]":
                    tail = stretch.flush()
                    if tail:
                        yield sse_audio(tail)
                yield event + b"\n\n"
        tail = stretch.flush()
        if tail:
            yield sse_audio(tail) if sse else tail
        if buf:
            yield buf

    async def relay():
        stats["active"] += 1
        first, pcm_bytes, buf = None, 0, b""
        try:
            async for chunk in (stretched() if stretch else upstream.aiter_raw()):
                if not chunk:
                    continue
                if first is None:
                    first = time.time() - t0
                if sse:  # count audio for the RTF figure without touching what goes out
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.startswith(b"data:") and b"speech.audio.delta" in line:
                            try:
                                pcm_bytes += len(base64.b64decode(json.loads(line[5:])["audio"]))
                            except Exception:
                                pass
                else:
                    pcm_bytes += len(chunk)
                yield chunk
            recent.append((time.time() - t0, pcm_bytes / PCM_BYTES_PER_S or None, first))
        except Exception as e:
            fail(f"stream aborted: {e}")
            raise
        finally:
            stats["active"] -= 1
            g.leave(ticket)
            await upstream.aclose()

    return StreamingResponse(relay(), status_code=200, media_type=upstream.headers.get("content-type"),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **PrioGate.headers(ticket)})


if __name__ == "__main__":
    quiet_access_log()
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
