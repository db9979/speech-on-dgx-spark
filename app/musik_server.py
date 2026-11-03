"""Musik machen: the music service (plan plaene/musik.md, Dominik 2026-10-16 „1a 2a 3a 4a 5a“). Unit
speech-spark-musik, only on 127.0.0.1 (music.port, 31004; on a split install the TLS door tlstor.py takes the same
port for the panel computer); the panel is its only caller (musik.py).

The engine is acestep.cpp's ace-server with ACE-Step 1.5 (musikmodell.py: files, variant, memory). It runs only on
demand like the picture engine: the first song starts it as a child process on 127.0.0.1 (music.engine_port, 31014),
music.idle_min minutes without a song stop it again, so it holds no memory while nobody makes music (Dominik
2026-10-16: load only when used, unload when unused for long). Before it starts, common.check_memory looks at the
unified memory with the variant's need; too little is a 503 "memory", never a start that pushes DGX OS into killing.
One song at a time. The unit's OOMScoreAdjust (1000) makes the engine the first thing to go when memory runs out.

A song takes two steps of the engine: /lm (the small language model plans structure, lyrics when none are given,
and the audio codes), then /synth (the DiT makes the sound, the VAE the wave, out as MP3). Every field of both
requests is set here; the caller gives only caption, seconds, lyrics, language and seed, and may fix tempo, key,
time signature and a negative prompt from fixed values (metadata) and name a quality level and loudness
(quality, musikmodell.QUALITAET; the Dungeon-Master's music does). The MP3 is checked (size,
frame header) and gets our own ID3 tag that marks it as made by an AI. The service never logs a caption or lyrics:
only seconds, sizes and states.

    GET  /health        status (off | starting | ready | busy | error | missing), variant, counts, measurements
    POST /v1/musik      {caption, seconds, lyrics?, language?, seed?, lm_seed?, variant?, bpm?, keyscale?, timesignature?, negative?,
                         quality?, loud?} -> {mp3, variant, quality, seconds, lm_s, ...}
    POST /v1/musik/stop ends the engine now (Wartungspause, Musik testen)

Musik bearbeiten (plan musik-experte, Dominik 2026-10-20 „alles nach Empfehlung“, Stufe E1): the panel sends one of
the person's own songs as MP3. With the engine: Abschnitt neu and Verlängern (repaint; outside the region acestep.cpp
puts the original samples back itself), Musikrichtung ändern (cover) and Remix (cover-nofsq with the song as its own
timbre reference); Erkennen (/understand: tempo, key, description, lyrics). Without a model, ffmpeg only from pipes:
an own file read in (one known format, at most MAX_S seconds, no tags) and Schneiden & Blenden, Tempo & Tonart.
Every number is checked here, every result is our own MP3 again, a change by the engine marked "KI-bearbeitet".

    POST /v1/musik/quelle?art=mp3|wav|flac|m4a|ogg   the raw file -> {mp3, length_s}
    POST /v1/musik/ton        {mp3, length_s, start?, end?, fade_in?, fade_out?, tempo?, halftones?, mark?} -> {mp3}
    POST /v1/musik/bearbeiten {mp3, art, length_s, caption, lyrics?, start?, end?, add_s?, where?, near?, bpm?, ...}
                              -> {mp3s, variant, seconds, peak_gib}
    POST /v1/musik/erkennen   {mp3, variant?} -> {bpm?, key?, caption?, lyrics?, language?}
"""
import asyncio
import base64
import email.parser
import email.policy
import json
import re
import struct
import time

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request

import musikmodell
from bedarf import Belegt, OnDemand, idle_loop
from common import BodyLimit, api_key_dependency, api_key_ok, check_memory, load_config, mem_available_gib, quiet_access_log

MAX_BODY = 64 * 1024
MAX_CAPTION = 600
MAX_LYRICS = 4000
MIN_S, MAX_S = 10, 600        # what the model can (10 s to 10 min); the panel's own limit is smaller
MAX_MP3 = 40 * 1024**2        # what the engine hands back, before checking (10 min at 320 kbit/s is 24 MB)
START_S = 120                 # ace-server itself starts at once; the models load with the first request
JOB_S = 900                   # one song, both steps
POLL_S = 0.5
JOB_ID = re.compile(r"[0-9a-f]{1,32}")   # ace-server names a job with 16 hex digits (V01.0.681: not only digits)
LANGS = ("de", "en", "fr", "es", "it", "nl", "pt", "pl", "sv", "da", "no", "fi", "tr", "ru", "uk", "ja", "zh", "ko")
INSTRUMENTAL = "[Instrumental]"
AI_TEXT = "KI-erzeugt mit ACE-Step 1.5 auf dem Spark / AI-generated with ACE-Step 1.5 on the Spark"
AI_EDIT_TEXT = "KI-bearbeitet mit ACE-Step 1.5 auf dem Spark / AI-edited with ACE-Step 1.5 on the Spark"
# Musik bearbeiten (plan musik-experte, Dominik 2026-10-20 „alles nach Empfehlung“): the song comes along as MP3
MAX_UPLOAD = 30 * 1024**2     # an own file as it was uploaded (the panel's limit, musik.MAX_UPLOAD)
MAX_SRC = 24 * 1024**2        # a song to change: our own MP3 (10 min at 192 kbit/s is 14.4 MB)
EDIT_BODY = MAX_SRC * 4 // 3 + 64 * 1024
MAX_SUGGEST = 3               # suggestions of one change (synth_batch_size)
MAX_ADD_S = 120               # longer by at most this much at once
MIN_LEN_S = 3                 # an upload shorter than this is no song
FFMPEG_S = 120                # one ffmpeg run at most this long
SAMPLE_RATE = 48000           # what ACE-Step works with (acestep.cpp resamples everything to 48 kHz)
# the own file's format -> ffmpeg's demuxer (only these; the panel checks the first bytes before)
DEMUX = {"mp3": "mp3", "wav": "wav", "flac": "flac", "m4a": "mov", "ogg": "ogg"}
TASKS = {"abschnitt": "repaint", "verlaengern": "repaint", "richtung": "cover", "remix": "cover-nofsq", "text": "cover"}
# Tempo & Tonart: tempo as a factor (atempo keeps the pitch), the key in half tones (resampled, tempo kept)
TEMPO = (0.75, 1.25)
HALFTONES = 4
KEY = re.compile(r"[A-G][#b]?\s?(?:major|minor|maj|min|dur|moll)?")
# the song's metadata a caller may fix (Dungeon-Musik, plan dungeon-musik-tuning V1a, Dominik 2026-10-30 „1-8“): with
# tempo, key, time signature and length all given acestep.cpp skips the planner's rewriting of the caption (src/
# pipeline-lm.cpp at musikmodell.ACECPP_COMMIT: "Filled = don't touch"); only the values its planner knows
# (src/metadata-fsm.h: A-G with #/b, major/minor; time signature 2, 3, 4, 6)
BPM = (40, 220)
KEYSCALE = re.compile(r"[A-G][#b]? (?:major|minor)")
TIMESIG = ("2", "3", "4", "6")
MAX_NEGATIVE = 200
NEGATIVE = re.compile(r"[a-z][a-z ,-]*")   # the panel's own fixed English words only, never a text from elsewhere

app = FastAPI(title="Musik machen (ACE-Step 1.5 via acestep.cpp)")
app.add_middleware(BodyLimit, default=MAX_BODY, gate=api_key_ok, gated=("/v1/",), limits=[
    ("/v1/musik/quelle", MAX_UPLOAD + 4096), ("/v1/musik/bearbeiten", EDIT_BODY), ("/v1/musik/ton", EDIT_BODY),
    ("/v1/musik/erkennen", EDIT_BODY)])
auth = [Depends(api_key_dependency())]
started = time.time()
stats = {"songs": 0, "edits": 0, "uploads": 0, "tones": 0, "heard": 0, "failures": 0, "refused_memory": 0, "refused_place": 0, "starts": 0, "last_s": None, "last_lm_s": None,
         "last_synth_s": None, "last_len_s": None, "peak_gib": None}


def cfg():
    return load_config("music")


class Engine(OnDemand):
    """ace-server as a child process: started on demand, ended after music.idle_min minutes without a song."""

    def __init__(self):
        super().__init__("musik")
        self.variant = ""          # the variant whose models the running engine holds (M1: picked per song)

    @property
    def base(self):
        return f"http://127.0.0.1:{int(cfg()['engine_port'])}"

    def command(self):
        c = cfg()
        # only options ace-server knows (it prints its help and ends with code 1 on any other, V01.0.679: an
        # "--mp3-bitrate" did that); the bitrate goes with every song (mp3_bitrate in request_body)
        return [musikmodell.ENGINE, "--models", musikmodell.FOLDER, "--host", "127.0.0.1", "--port",
                str(int(c["engine_port"])), "--max-batch", "1",
                "--keep-loaded"]   # all modules stay while the engine runs; the idle stop frees them

    async def start(self, v):
        """The engine for variant v: a running one with another variant ends first, so the memory check before the
        start covers the models it will load (M1: the admin picks the variant, Musik testen measures each)."""
        if self.alive() and self.state == "ready" and self.variant == v:
            return
        if self.alive():
            self.stop("anderes modell")
        if not musikmodell.installed(v):
            self.state = "error"
            raise HTTPException(503, "missing")
        try:   # one model on demand at a time (bedarf.py): the place first, then the memory
            self.claim()
        except Belegt:
            stats["refused_place"] += 1
            raise HTTPException(503, "belegt")
        try:
            check_memory(musikmodell.VARIANTS[v]["need_gib"])
        except MemoryError:
            self.release()
            stats["refused_memory"] += 1
            print(f"musik: engine nicht gestartet speicher {mem_available_gib():.1f} gib frei", flush=True)
            raise HTTPException(503, "memory")
        t0 = time.time()
        self.state = "starting"
        stats["starts"] += 1
        self.variant = v
        self.spawn(self.command(), musikmodell.FOLDER)
        while time.time() - t0 < START_S:
            if not self.alive():
                self.state = "error"
                print(f"musik: engine beendet beim start code {self.proc.returncode}", flush=True)
                self.stop("fehler")
                raise HTTPException(503, "engine")
            try:
                r = await self.client.get(self.base + "/health")
                if r.status_code == 200:
                    self.state = "ready"
                    self.used = time.time()
                    print(f"musik: engine gestartet {time.time() - t0:.1f} s", flush=True)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        self.stop("zeitlimit")
        self.state = "error"
        raise HTTPException(503, "engine")

    async def job(self, step, body, t0, low, audio=None, ref=False):
        """One step of the engine (lm, synth or understand): starts the job and waits for its result. Returns
        (response, lowest free memory seen). With audio (MP3 bytes, Musik bearbeiten) the request goes as
        multipart/form-data: the JSON as part "request", the song as part "audio" and, for a remix, once more as the
        timbre reference "ref_audio" (acestep.cpp ARCHITECTURE: "Pass ref_audio = src_audio for best results")."""
        if audio is None:
            r = await self.client.post(f"{self.base}/{step}", json=body)
        else:
            files = {"request": ("request.json", json.dumps(body), "application/json"),
                     "audio": ("quelle.mp3", audio, "audio/mpeg")}
            if ref:
                files["ref_audio"] = ("quelle.mp3", audio, "audio/mpeg")
            r = await self.client.post(f"{self.base}/{step}", files=files)
        if r.status_code != 200:
            raise HTTPException(502, "engine")
        job = str((r.json() or {}).get("id") or "")
        if not JOB_ID.fullmatch(job):
            raise HTTPException(502, "engine")
        while time.time() - t0 < JOB_S:
            await asyncio.sleep(POLL_S)
            low = min(low, mem_available_gib())
            if not self.alive():
                self.state = "error"
                raise HTTPException(502, "engine")
            s = ((await self.client.get(f"{self.base}/job", params={"id": job})).json() or {}).get("status")
            if s == "done":
                res = await self.client.get(f"{self.base}/job", params={"id": job, "result": "1"})
                if res.status_code != 200 or len(res.content) > MAX_MP3:
                    raise HTTPException(502, "engine")
                return res, low
            if s in ("failed", "cancelled"):
                raise HTTPException(502, "engine")
        try:
            await self.client.post(f"{self.base}/job", params={"id": job, "cancel": "1"})
        except httpx.HTTPError:
            pass
        raise HTTPException(504, "timeout")

    async def make(self, req, v):
        """One song with variant v: (MP3 bytes from the engine, seconds of both steps, GiB taken at the peak)."""
        async with self.lock:
            await self.start(v)
            self.busy = True
            t0 = time.time()
            first = low = mem_available_gib()
            try:
                lm, low = await self.job("lm", req, t0, low)
                planned = lm.json()
                planned = planned[0] if isinstance(planned, list) and planned else None
                if not isinstance(planned, dict) or not str(planned.get("audio_codes") or ""):
                    raise HTTPException(502, "engine")
                lm_s = time.time() - t0
                # the plan of the language model, with our own fields again on top (it may only add codes and
                # metadata; caption, length, lyrics and the output stay ours)
                synth = dict(planned, **req)
                synth["audio_codes"] = str(planned["audio_codes"])
                res, low = await self.job("synth", synth, t0, low)
                return audio_part(res), lm_s, time.time() - t0 - lm_s, max(0.0, first - low)
            except httpx.HTTPError:
                raise HTTPException(502, "engine")
            except ValueError:
                raise HTTPException(502, "engine")
            finally:
                self.busy = False
                self.used = time.time()


    async def edit(self, req, mp3, v, ref=False):
        """Musik bearbeiten with variant v: the song mp3 changed by one /synth job (repaint, cover or cover-nofsq;
        the language model is skipped, acestep.cpp "Model compatibility"). Returns ([MP3 bytes per suggestion],
        seconds, GiB taken at the peak). Outside a repainted region the engine puts the original samples back
        itself ("WAV-Splice"), so the rest of the song stays as it was."""
        async with self.lock:
            await self.start(v)
            self.busy = True
            t0 = time.time()
            first = low = mem_available_gib()
            try:
                res, low = await self.job("synth", req, t0, low, audio=mp3, ref=ref)
                return audio_parts(res), time.time() - t0, max(0.0, first - low)
            except (httpx.HTTPError, ValueError):
                raise HTTPException(502, "engine")
            finally:
                self.busy = False
                self.used = time.time()

    async def understand(self, req, mp3, v):
        """Erkennen: what the engine hears in the song (/understand: the language model listens). Returns the
        engine's JSON (checked by heard())."""
        async with self.lock:
            await self.start(v)
            self.busy = True
            t0 = time.time()
            try:
                res, _low = await self.job("understand", req, t0, mem_available_gib(), audio=mp3)
                return json_part(res)
            except (httpx.HTTPError, ValueError):
                raise HTTPException(502, "engine")
            finally:
                self.busy = False
                self.used = time.time()


engine = Engine()


def _parts(res):
    """The parts of the engine's multipart/mixed answer, as bytes. ValueError when it is no multipart answer."""
    ctype = res.headers.get("content-type", "")
    if not ctype.lower().startswith("multipart/"):
        raise ValueError("no multipart")
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + ctype.encode("latin-1", "replace") + b"\r\n\r\n" + res.content)
    return [part.get_payload(decode=True) or b"" for part in msg.iter_parts()]


def audio_parts(res):
    """Every MP3 out of the engine's multipart/mixed answer (an audio part and a latent part per track), at most
    MAX_SUGGEST. ValueError when there is none."""
    out = [raw for raw in _parts(res) if is_mp3(raw)][:MAX_SUGGEST]
    if not out:
        raise ValueError("no mp3")
    return out


def audio_part(res):
    """The first MP3 out of the engine's multipart/mixed answer. ValueError when there is none."""
    return audio_parts(res)[0]


def json_part(res):
    """The JSON object of the engine's /understand answer (a JSON part and an optional latent part)."""
    for raw in _parts(res):
        try:
            d = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        d = d[0] if isinstance(d, list) and d else d
        if isinstance(d, dict):
            return d
    raise ValueError("no json")


def is_mp3(raw):
    """An ID3 tag or an MPEG audio frame header at the start."""
    if len(raw) < 4:
        return False
    if raw[:3] == b"ID3":
        return True
    return raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0


def _syncsafe(n):
    return bytes(((n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F))


def _frame(fid, payload):
    return fid + struct.pack(">I", len(payload)) + b"\0\0" + payload


def finish(raw, title, mark="made"):
    """The engine's MP3 -> our own: its ID3 tag (if any) dropped, ours in front (ID3v2.3: title, software and, for
    a song the AI made or changed, the AI mark as comment and TXXX: mark "made" KI-erzeugt, "edited" KI-bearbeitet;
    "" for an own upload that no model touched). Raises ValueError for anything that is not an MP3 of a sane size."""
    if not is_mp3(raw) or len(raw) > MAX_MP3:
        raise ValueError("no mp3")
    if raw[:3] == b"ID3":
        size = 10 + sum((raw[6 + i] & 0x7F) << (7 * (3 - i)) for i in range(4)) + (10 if raw[5] & 0x10 else 0)
        raw = raw[size:]
        if not is_mp3(raw) or raw[:3] == b"ID3":
            raise ValueError("no mp3")
    utf16 = b"\x01"

    def text(s):
        return utf16 + s.encode("utf-16")

    frames = _frame(b"TIT2", text(title[:120] or "Musik")) + _frame(b"TSSE", text("Speech on DGX Spark"))
    if mark:
        word, comment = ("KI-bearbeitet", AI_EDIT_TEXT) if mark == "edited" else ("KI-erzeugt", AI_TEXT)
        frames += (_frame(b"COMM", utf16 + b"deu" + "".encode("utf-16") + b"\0\0" + comment.encode("utf-16"))
                   + _frame(b"TXXX", utf16 + word.encode("utf-16") + b"\0\0" + "ACE-Step 1.5".encode("utf-16")))
    return b"ID3\x03\x00\x00" + _syncsafe(len(frames)) + frames + raw


def pick(b):
    """The variant of one song: the caller's "variant" (the admin's pick, Musik testen) when it is known, else the
    one install.sh set (music.variant). Whether it is installed decides start (503 "missing")."""
    v = b.get("variant") if isinstance(b, dict) else None
    if v is not None and v not in musikmodell.VARIANTS:
        raise HTTPException(400, "variant")
    return musikmodell.variant(v or cfg().get("variant"))


def request_body(b, v=None):
    """The checked request for the engine: every field fixed here except caption, length, lyrics, language, seed, the
    optional planner seed (lm_seed) and the optional metadata (metadata: tempo, key, time signature, negative prompt; absent as before).
    ace-server knows its models by the whole file name, .gguf included (V01.0.681)."""
    if not isinstance(b, dict):
        raise HTTPException(400, "JSON object")
    caption = b.get("caption")
    if not isinstance(caption, str) or not caption.strip() or len(caption) > MAX_CAPTION:
        raise HTTPException(400, f"caption: 1-{MAX_CAPTION} characters")
    caption = "".join(ch for ch in caption if ch.isprintable() and ch not in "<>")
    secs = b.get("seconds")
    if isinstance(secs, bool) or not isinstance(secs, int) or not MIN_S <= secs <= MAX_S:
        raise HTTPException(400, f"seconds: {MIN_S}-{MAX_S}")
    lyrics = b.get("lyrics", "")
    if not isinstance(lyrics, str) or len(lyrics) > MAX_LYRICS:
        raise HTTPException(400, f"lyrics: at most {MAX_LYRICS} characters")
    lyrics = "".join(ch for ch in lyrics if ch.isprintable() or ch == "\n").strip()
    lang = b.get("language", "")
    if lang not in ("",) + LANGS:
        raise HTTPException(400, "language")
    seed = b.get("seed", -1)
    if isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed < 2**31:
        raise HTTPException(400, "seed")
    lm_seed = b.get("lm_seed")   # optional: the planner's seed, kept by the Dungeon-Master's store (plan V5a)
    if lm_seed is not None and (isinstance(lm_seed, bool) or not isinstance(lm_seed, int) or not 0 <= lm_seed < 2**31):
        raise HTTPException(400, "lm_seed")
    v = musikmodell.VARIANTS[v or pick(b)]
    return {"caption": caption, "lyrics": lyrics or INSTRUMENTAL, "vocal_language": lang if lyrics else "unknown",
            "duration": float(secs), "seed": seed, "lm_batch_size": 1, "synth_batch_size": 1,
            "inference_steps": musikmodell.STEPS, "task_type": "text2music", "output_format": "mp3",
            "mp3_bitrate": musikmodell.MP3_KBPS, "synth_model": v["dit"].name, "lm_model": v["lm"].name,
            "use_cot_caption": True, "lm_mode": "generate", "adapter": "", **metadata(b), **quality(b)[1],
            **({} if lm_seed is None else {"lm_seed": lm_seed})}


def quality(b):
    """The quality level and loudness a caller names (musikmodell.QUALITAET, LAUT; absent: the engine's defaults as
    before) -> (the level made, the engine's fields). "beste" takes the SFT DiT with SFT_STEPS only when it is
    installed, else QUALITAET_ERSATZ (the answer says which level it was)."""
    q = b.get("quality", "schnell")
    if q not in musikmodell.QUALITAET:
        raise HTTPException(400, "quality")
    loud = b.get("loud")
    if loud is not None and loud not in musikmodell.LAUT:
        raise HTTPException(400, "loud")
    if musikmodell.QUALITAET[q].get("sft") and not musikmodell.sft_installed():
        q = musikmodell.QUALITAET_ERSATZ
    out = {k: v for k, v in musikmodell.QUALITAET[q].items() if k != "sft"}
    if musikmodell.QUALITAET[q].get("sft"):
        out.update(synth_model=musikmodell.SFT.name, inference_steps=musikmodell.SFT_STEPS)
    if loud is not None:
        out["peak_clip"] = musikmodell.LAUT[loud]
    return q, out


def metadata(b):
    """The optional metadata of a song, each checked here (absent: the engine's planner fills it as before):
    bpm (whole number in BPM), keyscale („D minor“, KEYSCALE), timesignature (TIMESIG), negative (the planner's
    negative prompt lm_negative_prompt: lowercase words, commas and hyphens, at most MAX_NEGATIVE)."""
    out = {}
    bpm = b.get("bpm")
    if bpm is not None:
        if isinstance(bpm, bool) or not isinstance(bpm, int) or not BPM[0] <= bpm <= BPM[1]:
            raise HTTPException(400, f"bpm: {BPM[0]}-{BPM[1]}")
        out["bpm"] = bpm
    key = b.get("keyscale")
    if key is not None:
        if not isinstance(key, str) or not KEYSCALE.fullmatch(key):
            raise HTTPException(400, "keyscale")
        out["keyscale"] = key
    ts = b.get("timesignature")
    if ts is not None:
        if ts not in TIMESIG:
            raise HTTPException(400, "timesignature")
        out["timesignature"] = ts
    neg = b.get("negative")
    if neg is not None:
        if not isinstance(neg, str) or len(neg) > MAX_NEGATIVE or not NEGATIVE.fullmatch(neg):
            raise HTTPException(400, f"negative: at most {MAX_NEGATIVE} lowercase words")
        out["lm_negative_prompt"] = neg
    return out


@app.post("/v1/musik", dependencies=auth)
async def musik(request: Request):
    try:
        b = await request.json()
        v = pick(b)
        req = request_body(b, v)
        stufe = quality(b)[0]
    except ValueError:
        raise HTTPException(400, "JSON object")
    title = str(b.get("title") or "")[:120]
    try:
        raw, lm_s, synth_s, peak = await engine.make(req, v)
        mp3 = finish(raw, "".join(ch for ch in title if ch.isprintable()))
    except HTTPException as e:
        stats["failures"] += 1
        print(f"musik: nicht gemacht {e.detail}", flush=True)
        raise
    except ValueError:
        stats["failures"] += 1
        print("musik: nicht gemacht kein mp3", flush=True)
        raise HTTPException(502, "engine")
    stats["songs"] += 1
    stats.update(last_s=round(lm_s + synth_s, 1), last_lm_s=round(lm_s, 1), last_synth_s=round(synth_s, 1),
                 last_len_s=int(req["duration"]), peak_gib=round(peak, 1))
    sung = req["lyrics"] != INSTRUMENTAL
    print(f"musik: gemacht {int(req['duration'])} s {'gesang' if sung else 'instrumental'} {v} {stufe} "
          f"{lm_s + synth_s:.1f} s spitze {peak:.1f} gib", flush=True)
    return {"mp3": base64.b64encode(mp3).decode(), "variant": v, "quality": stufe, "seconds": round(lm_s + synth_s, 1), "lm_s": round(lm_s, 1),
            "synth_s": round(synth_s, 1), "peak_gib": round(peak, 1), "length_s": int(req["duration"]),
            "sung": sung, "seed": req["seed"], "bytes": len(mp3)}


# ---------------------------------------------------------------- Musik bearbeiten (plan musik-experte, Stufe E1)
_ffmpeg = asyncio.Semaphore(1)      # one ffmpeg run at a time on this machine


async def ffmpeg(args, data, most):
    """One ffmpeg run on the bytes data (stdin) -> its output (stdout), at most most bytes. Only pipes, no shell,
    no network (the protocol whitelist), FFMPEG_S at most; ValueError when ffmpeg fails, takes too long or writes too
    much. Nothing of its own output goes to the journal."""
    async with _ffmpeg:
        p = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.DEVNULL)
        try:
            out, _err = await asyncio.wait_for(p.communicate(data), FFMPEG_S)
        except asyncio.TimeoutError:
            p.kill()
            await p.wait()
            raise ValueError("zeit")
    if p.returncode != 0 or not out or len(out) > most:
        raise ValueError("ffmpeg")
    return out


def decode_args(demux):
    """ffmpeg: an own file (one known format) -> raw 16-bit PCM, stereo, 48 kHz, at most MAX_S seconds, only its first
    audio stream, without pictures, subtitles or metadata."""
    return ["ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe", "-hide_banner", "-loglevel", "error",
            "-f", demux, "-i", "pipe:0", "-t", str(MAX_S), "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1",
            "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"]


def encode_args(src, filters=""):
    """ffmpeg: raw PCM ("pcm") or our own MP3 ("mp3") -> MP3 at MP3_KBPS, with the filters on the way, no tags (ours
    come with finish)."""
    inp = ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "2"] if src == "pcm" else ["-f", "mp3"]
    return (["ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe", "-hide_banner", "-loglevel", "error"] + inp
            + ["-i", "pipe:0", "-t", str(MAX_S + MAX_ADD_S), "-map_metadata", "-1", "-vn"]
            + (["-af", filters] if filters else [])
            + ["-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "libmp3lame", "-b:a", f"{musikmodell.MP3_KBPS}k",
               "-id3v2_version", "0", "-write_xing", "0", "-f", "mp3", "pipe:1"])


def _secs(v, lo, hi, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= float(v) <= hi:
        raise HTTPException(400, name)
    return round(float(v), 2)


def tone_filters(b):
    """The ffmpeg filters of Schneiden & Blenden and Tempo & Tonart, every number checked here: keep start..end,
    fade in and out (seconds), tempo (factor, atempo keeps the pitch), key (half tones, tempo kept). Raises
    HTTPException 400 for anything else or for nothing to do."""
    if not isinstance(b, dict):
        raise HTTPException(400, "JSON object")
    length = _secs(b.get("length_s"), 1, MAX_S + MAX_ADD_S, "length_s")
    out = []
    start, end = b.get("start"), b.get("end")
    if start is not None or end is not None:
        start = _secs(start if start is not None else 0, 0, length, "start")
        end = _secs(end if end is not None else length, 0, length, "end")
        if end - start < 1:
            raise HTTPException(400, "range")
        out.append(f"atrim=start={start}:end={end},asetpts=PTS-STARTPTS")
        length = end - start
    fin, fout = b.get("fade_in"), b.get("fade_out")
    if fin:
        out.append(f"afade=t=in:st=0:d={_secs(fin, 0.1, min(30, length / 2), 'fade_in')}")
    if fout:
        d = _secs(fout, 0.1, min(30, length / 2), "fade_out")
        out.append(f"afade=t=out:st={round(length - d, 2)}:d={d}")
    if out and not fin and not fout and (start is not None or end is not None):
        out.append("afade=t=in:st=0:d=0.03")                 # no click at a cut
        out.append(f"afade=t=out:st={round(max(0, length - 0.03), 2)}:d=0.03")
    tempo = b.get("tempo")
    if tempo is not None and tempo != 1:
        out.append(f"atempo={_secs(tempo, TEMPO[0], TEMPO[1], 'tempo')}")
    half = b.get("halftones")
    if half:
        if isinstance(half, bool) or not isinstance(half, int) or not -HALFTONES <= half <= HALFTONES:
            raise HTTPException(400, "halftones")
        r = round(2 ** (half / 12), 6)
        out.append(f"asetrate={int(SAMPLE_RATE * r)},aresample={SAMPLE_RATE},atempo={round(1 / r, 6)}")
    if not out:
        raise HTTPException(400, "nothing")
    return ",".join(out)


def source(b):
    """The song to change: our own MP3 as base64 (checked: size, MP3 header). HTTPException 400 otherwise."""
    raw = b.get("mp3") if isinstance(b, dict) else None
    if not isinstance(raw, str) or len(raw) > EDIT_BODY:
        raise HTTPException(400, "mp3")
    try:
        mp3 = base64.b64decode(raw, validate=True)
    except ValueError:
        raise HTTPException(400, "mp3")
    if len(mp3) > MAX_SRC or not is_mp3(mp3):
        raise HTTPException(400, "mp3")
    return mp3


def edit_body(b, v):
    """The checked request for one change by the engine: every field fixed here except the kind (TASKS), the
    description, the lyrics, the region, the closeness, the tempo and the seed. Repaint and cover skip the language
    model (acestep.cpp), so only the DiT and the VAE work."""
    if not isinstance(b, dict) or b.get("art") not in TASKS:
        raise HTTPException(400, "art")
    art = b["art"]
    length = _secs(b.get("length_s"), 1, MAX_S, "length_s")
    caption = b.get("caption")
    if not isinstance(caption, str) or not caption.strip() or len(caption) > MAX_CAPTION:
        raise HTTPException(400, f"caption: 1-{MAX_CAPTION} characters")
    caption = "".join(ch for ch in caption if ch.isprintable() and ch not in "<>")
    lyrics = b.get("lyrics", "")
    if not isinstance(lyrics, str) or len(lyrics) > MAX_LYRICS:
        raise HTTPException(400, f"lyrics: at most {MAX_LYRICS} characters")
    lyrics = "".join(ch for ch in lyrics if ch.isprintable() or ch == "\n").strip()
    lang = b.get("language", "")
    if lang not in ("",) + LANGS:
        raise HTTPException(400, "language")
    seed = b.get("seed", -1)
    if isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed < 2**31:
        raise HTTPException(400, "seed")
    n = b.get("suggestions", 1)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_SUGGEST:
        raise HTTPException(400, "suggestions")
    m = musikmodell.VARIANTS[v]
    req = {"caption": caption, "lyrics": lyrics or INSTRUMENTAL, "vocal_language": (lang or "unknown") if lyrics else "unknown",
           "seed": seed, "synth_batch_size": n, "lm_batch_size": 1, "inference_steps": musikmodell.STEPS,
           "task_type": TASKS[art], "output_format": "mp3", "mp3_bitrate": musikmodell.MP3_KBPS,
           "synth_model": m["dit"].name, "lm_model": m["lm"].name, "use_cot_caption": False, "adapter": ""}
    if art == "abschnitt":       # a part inside the song new, the rest stays sample for sample
        start = _secs(b.get("start"), 0, length, "start")
        end = _secs(b.get("end"), 0, length, "end")
        if end - start < 1:
            raise HTTPException(400, "range")
        req.update(repainting_start=start, repainting_end=end)
    elif art == "verlaengern":   # longer at the front (start below 0) or at the end (end beyond the song)
        add = _secs(b.get("add_s"), 5, MAX_ADD_S, "add_s")
        if b.get("where") == "vorne":
            req.update(repainting_start=-add, repainting_end=-1)
        elif b.get("where") == "hinten":
            req.update(repainting_start=length, repainting_end=round(length + add, 2))
        else:
            raise HTTPException(400, "where")
    else:                        # another direction or new lyrics (cover) or a remix close to the song (cover-nofsq)
        near = _secs(b.get("near", 0.6), 0.1, 1.0, "near")
        req.update(audio_cover_strength=near)
        bpm = b.get("bpm")
        if bpm is not None:
            if isinstance(bpm, bool) or not isinstance(bpm, int) or not BPM[0] <= bpm <= BPM[1]:
                raise HTTPException(400, "bpm")
            req["bpm"] = bpm
    return req


def heard(d):
    """What /understand heard, as fixed fields with checked values (it is the engine's text: data, never more)."""
    d = d if isinstance(d, dict) else {}
    out = {}
    bpm = d.get("bpm")
    if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) and 30 <= bpm <= 300:
        out["bpm"] = int(round(bpm))
    key = str(d.get("keyscale") or "").strip()[:20]
    if KEY.fullmatch(key):
        out["key"] = key
    cap = "".join(ch for ch in str(d.get("caption") or "") if ch.isprintable() and ch not in "<>").strip()
    if cap:
        out["caption"] = cap[:MAX_CAPTION]
    lyr = "".join(ch for ch in str(d.get("lyrics") or "") if ch.isprintable() or ch == "\n").strip()
    if lyr and lyr != INSTRUMENTAL:
        out["lyrics"] = lyr[:MAX_LYRICS]
    lang = d.get("vocal_language")
    if lang in LANGS:
        out["language"] = lang
    return out


def _fail(what, why):
    stats["failures"] += 1
    print(f"musik: nicht {what} {why}", flush=True)


@app.post("/v1/musik/quelle", dependencies=auth)
async def quelle(request: Request, art: str = ""):
    """An own file (the raw bytes, art one of DEMUX) -> our MP3 at MP3_KBPS without its tags, and its length. ffmpeg
    reads only this format from a pipe; the file never touches the disk here."""
    if art not in DEMUX:
        raise HTTPException(400, "art")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "too big")
    try:
        pcm = await ffmpeg(decode_args(DEMUX[art]), bytes(data), MAX_S * SAMPLE_RATE * 4)
        secs = len(pcm) / (SAMPLE_RATE * 4)
        if secs < MIN_LEN_S:
            raise ValueError("kurz")
        mp3 = finish(await ffmpeg(encode_args("pcm"), pcm, MAX_MP3), "", mark="")
    except ValueError as e:
        _fail("eingelesen", str(e) if str(e) in ("zeit", "kurz") else "ffmpeg")
        raise HTTPException(415, "audio")
    stats["uploads"] += 1
    print(f"musik: eingelesen {art} {int(secs)} s", flush=True)
    return {"mp3": base64.b64encode(mp3).decode(), "length_s": round(secs, 1), "bytes": len(mp3)}


@app.post("/v1/musik/ton", dependencies=auth)
async def ton(request: Request):
    """Schneiden & Blenden, Tempo & Tonart with ffmpeg alone (no model, no place of the models on demand)."""
    try:
        b = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON object")
    mp3 = source(b)
    filters = tone_filters(b)
    mark = b.get("mark") if b.get("mark") in ("made", "edited") else ""
    try:
        out = finish(await ffmpeg(encode_args("mp3", filters), mp3, MAX_MP3), str(b.get("title") or "")[:120], mark=mark)
    except ValueError as e:
        _fail("bearbeitet", "zeit" if str(e) == "zeit" else "ffmpeg")
        raise HTTPException(502, "ffmpeg")
    stats["tones"] += 1
    print(f"musik: ton bearbeitet {len(filters.split(','))} filter", flush=True)
    return {"mp3": base64.b64encode(out).decode(), "bytes": len(out)}


@app.post("/v1/musik/bearbeiten", dependencies=auth)
async def bearbeiten(request: Request):
    """Abschnitt neu, Verlängern, Musikrichtung ändern, Remix: one /synth job of the engine on the song, 1 to
    MAX_SUGGEST suggestions, each marked as changed by an AI."""
    try:
        b = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON object")
    v = pick(b)
    mp3 = source(b)
    req = edit_body(b, v)
    try:
        raws, secs, peak = await engine.edit(req, mp3, v, ref=b["art"] == "remix")
        title = "".join(ch for ch in str(b.get("title") or "")[:120] if ch.isprintable())
        outs = [finish(raw, title, mark="edited") for raw in raws]
    except HTTPException as e:
        _fail("bearbeitet", e.detail)
        raise
    except ValueError:
        _fail("bearbeitet", "kein mp3")
        raise HTTPException(502, "engine")
    stats["edits"] += 1
    stats.update(last_s=round(secs, 1), peak_gib=round(peak, 1))
    print(f"musik: bearbeitet {b['art']} {v} {len(outs)} vorschlaege {secs:.1f} s spitze {peak:.1f} gib", flush=True)
    return {"mp3s": [base64.b64encode(x).decode() for x in outs], "variant": v, "seconds": round(secs, 1),
            "peak_gib": round(peak, 1)}


@app.post("/v1/musik/erkennen", dependencies=auth)
async def erkennen(request: Request):
    """Erkennen: tempo, key, a description and the lyrics the language model hears in the song."""
    try:
        b = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON object")
    v = pick(b)
    mp3 = source(b)
    m = musikmodell.VARIANTS[v]
    req = {"synth_model": m["dit"].name, "lm_model": m["lm"].name, "seed": -1}
    try:
        d = heard(await engine.understand(req, mp3, v))
    except HTTPException as e:
        _fail("erkannt", e.detail)
        raise
    stats["heard"] += 1
    print(f"musik: erkannt {len(d)} felder", flush=True)
    return d


@app.post("/v1/musik/stop", dependencies=auth)
async def stop():
    async with engine.lock:
        engine.stop("auf wunsch")
    return {"ok": True}


@app.get("/health")
async def health(request: Request):
    c = cfg()
    v = musikmodell.variant(c.get("variant"))
    status = "missing" if not musikmodell.installed(v) else "busy" if engine.busy else engine.state
    if not api_key_ok(request.scope):
        return {"service": "musik", "status": status}
    return {"service": "musik", "status": status, "variant": v, "name": musikmodell.VARIANTS[v]["name"],
            "license": musikmodell.LICENSE, "need_gib": musikmodell.VARIANTS[v]["need_gib"],
            "missing": musikmodell.missing(v), "installed": musikmodell.available(), "sft": musikmodell.sft_installed(),
            "loaded": engine.variant if engine.state == "ready" else "", "idle_min": int(c["idle_min"]), "uptime_s": round(time.time() - started),
            "idle_s": round(time.time() - engine.used) if engine.state == "ready" else None, **stats}


@app.on_event("startup")
async def idle_stop():
    idle_loop(engine, lambda: cfg()["idle_min"])


@app.on_event("shutdown")
def end():
    engine.stop("dienst endet")


if __name__ == "__main__":
    quiet_access_log()
    c = cfg()
    uvicorn.run(app, host="127.0.0.1", port=int(c["port"]))
