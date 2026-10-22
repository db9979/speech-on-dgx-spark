"""Qwen3-ASR front end for the vLLM engine (backend "vllm").

The engine (native vLLM venv, 127.0.0.1 only) does the work: it decodes any audio ffmpeg
knows (webm, mp4, ogg, ...), cuts long recordings into model-sized clips, batches parallel
requests and streams text with `stream=true` (OpenAI `transcription.chunk` SSE events).
This service sits on the public ASR port and adds the API key, the default language,
language names besides ISO codes, `verbose_json`, and the counters the panel shows.
"""
import asyncio
import json
import os
import subprocess
import time
from collections import deque

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from common import (ASR_ISO, audio_rate_ok, BodyLimit, GateFull, KeyedCORS, PrioGate, inside, outside_view, api_key_dependency, api_key_ok,
                    engine_crash_reason, load_config, NOTASR_IDLE, NOTASR_PORT, quiet_access_log, SpeechMark, stage_of, STATE)
import smartturn

UNIT = "speech-spark-asr-engine"
NAME_TO_ISO = {v.lower(): k for k, v in ASR_ISO.items()}

cfg = load_config("asr")
# Notbetrieb on the panel computer (plan Raspberry-Pi split B5c, chat.notbetrieb_asr): the same front end with Parakeet,
# only on 127.0.0.1, loaded at the first recording and unloaded after NOTASR_IDLE seconds without one
NOT = os.environ.get("SPEECH_SPARK_NOTASR") == "1"
if NOT:
    cfg = dict(cfg, recognizer="parakeet", host="127.0.0.1", port=NOTASR_PORT)
app = FastAPI(title="Qwen3-ASR via vLLM (DGX Spark)")
# innermost: only requests that passed the size limit and API key count as speech
app.add_middleware(SpeechMark)
app.add_middleware(KeyedCORS)
# bodies are refused before they are read when too large or without the API key
app.add_middleware(BodyLimit, limits=[("/v1/turn", smartturn.MAX_BYTES)], default=201 * 1024**2, gate=api_key_ok, gated=("/v1/",))
auth = [Depends(api_key_dependency())]
client = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=5))
started = time.time()
stats = {"requests": 0, "failures": 0, "streams": 0, "last_error": None, "active": 0}
recent = deque(maxlen=50)  # (seconds, audio_seconds or None, time to first text or None)
# asr.recognizer = "parakeet": no engine, the CPU model in this process does the work
local = None
if cfg.get("recognizer") == "parakeet":
    import parakeet
    local = parakeet.Recognizer()


# Priority for people (panel stufe.py): as many recordings at once as the engine takes, the rest wait here by stage
_n = cfg.get("engine_max_seqs", 4)
gate = PrioGate(_n if isinstance(_n, int) and not isinstance(_n, bool) and 1 <= _n <= 64 else 4)


def engine_url(path):
    return f"http://127.0.0.1:{cfg['engine_port']}{path}"


def unit_active():
    try:
        return subprocess.run(["systemctl", "is-active", UNIT], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except Exception:
        return "unknown"



def sub_state(unit):
    try:
        return subprocess.run(["systemctl", "show", unit, "-p", "SubState", "--value"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return "unknown"


async def engine_status():
    """ready | loading | blocked | error | stopped, plus a message."""
    if local:
        return local.status, local.error
    try:
        r = await client.get(engine_url("/health"), timeout=2)
        if r.status_code == 200:
            return "ready", None
    except httpx.HTTPError:
        pass
    # systemctl and journalctl block for a moment: in a worker thread (only while the engine is not up)
    return await asyncio.to_thread(_not_ready)


def _not_ready():
    try:
        with open(os.path.join(STATE, "speech-spark-asr-engine.json")) as f:
            st = json.load(f)
    except Exception:
        st = {}
    active = unit_active()
    if st.get("status") in ("blocked", "error") and active != "active":
        return st["status"], st.get("error")
    if active == "activating" and sub_state(UNIT) == "auto-restart":
        reason = engine_crash_reason(UNIT)
        return "error", f"engine exited and restarts every 30 s: {reason or 'see panel Logs -> ASR-Engine'}"
    if active in ("active", "activating"):
        return "loading", (st.get("status") == "loading" and st.get("error")) or "engine starting (first start downloads the model and compiles kernels)"
    return "stopped", f"{UNIT} is {active}"


def fail(msg):
    stats["failures"] += 1
    stats["last_error"] = {"time": time.time(), "error": msg}


def iso_language(lang):
    """'de', 'German', 'auto' or None -> ISO code or None (= let the model detect it)."""
    lang = str(lang or cfg.get("default_language") or "auto").strip()
    if lang.lower() == "auto":
        return None
    return NAME_TO_ISO.get(lang.lower(), lang.lower())


def silence_wav(seconds=1.0, rate=16000):
    """A short, almost silent 16 kHz mono WAV for the warm-up request."""
    import struct
    n = int(seconds * rate)
    pcm = b"".join(struct.pack("<h", (i * 7919) % 64 - 32) for i in range(n))  # faint noise, not pure zeros
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


async def warm_up():
    """One short request right after the engine comes up, so the first real request does not
    pay for the remaining compilation and cache warm-up."""
    try:
        t0 = time.time()
        r = await client.post(engine_url("/v1/audio/transcriptions"), data={"model": cfg["model"]},
                              files={"file": ("warmup.wav", silence_wav(), "audio/wav")})
        print(f"warm-up: HTTP {r.status_code} in {time.time() - t0:.1f} s", flush=True)
    except httpx.HTTPError as e:
        print(f"warm-up failed: {e}", flush=True)


@app.on_event("startup")
async def watch_engine():
    if local and NOT:
        local.status = "idle"
        asyncio.create_task(idle_loop())
        return
    if local:
        local.load_in_background()
        return
    async def loop():
        ready = False
        while True:
            now = (await engine_status())[0] == "ready"
            if now and not ready:
                await warm_up()
            ready = now
            await asyncio.sleep(5)
    asyncio.create_task(loop())


async def idle_loop():
    """Notbetrieb: the recognizer goes again when nobody spoke for NOTASR_IDLE seconds."""
    while True:
        await asyncio.sleep(30)
        if local.status == "ready" and not stats["active"] and time.monotonic() - local.used > NOTASR_IDLE:
            await asyncio.to_thread(local.unload)


async def wake_local():
    """Notbetrieb: the first recording loads the recognizer and waits for it (once, however many come at once)."""
    if local.status in ("idle", "error"):
        local.status = "loading"
        await asyncio.to_thread(local.load)
    while local.status == "loading":
        await asyncio.sleep(0.2)


@app.get("/health")
async def health(request: Request):
    if not inside(request):
        return outside_view({"service": "asr", "status": (await engine_status())[0]})
    status, error = await engine_status()
    lat = [r[0] for r in recent]
    rtf = [r[0] / r[1] for r in recent if r[1]]
    ttft = [r[2] for r in recent if r[2] is not None]
    return {
        "service": "asr", "backend": "vllm", "status": status, "error": error,
        "model": parakeet.NAME if local else cfg["model"], "recognizer": "parakeet" if local else "qwen",
        "uptime_s": round(time.time() - started), "load_seconds": local.load_seconds if local else None,
        "requests": stats["requests"], "failures": stats["failures"], "streams": stats["streams"],
        "busy": stats["active"] > 0, "last_error": stats["last_error"],
        "avg_latency_s": round(sum(lat) / len(lat), 3) if lat else None,
        "avg_rtf": round(sum(rtf) / len(rtf), 3) if rtf else None,
        "avg_ttft_s": round(sum(ttft) / len(ttft), 3) if ttft else None,
        "timestamps": False, "queue": gate.view(),
    }


@app.get("/v1/models", dependencies=auth)
def models():
    return {"object": "list", "data": [{"id": parakeet.NAME if local else cfg["model"], "object": "model", "owned_by": "local"}]}


@app.get("/v1/languages")
def languages():
    return {"languages": ["auto"] + list(ASR_ISO.values())}


MAX_UPLOAD = 200 * 1024**2  # as much as the engine takes (VLLM_MAX_AUDIO_CLIP_FILESIZE_MB)


async def read_upload(upload):
    data = bytearray()   # appending to bytes copies everything each time
    while chunk := await upload.read(1 << 20):
        data += chunk
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "audio file larger than 200 MB")
    return bytes(data)


# form fields that go on to the engine (OpenAI's transcription API); anything else stays here, so a
# client cannot switch on engine options nobody checked
ENGINE_FIELDS = {"prompt", "temperature", "stream"}


@app.post("/v1/turn", dependencies=auth)
async def turn(request: Request):
    """Satzende am Tonfall (smartturn.py, panel satzende.py): how finished the end of a recording sounds, 0 to 1.
    Only a number for the panel's measurement, nothing here decides; 503 without the model file."""
    data = await request.body()
    if not smartturn.present():
        raise HTTPException(503, "turn model not installed")
    try:
        audio = smartturn.pcm(data)
    except ValueError as e:
        raise HTTPException(415, str(e))
    try:
        p, ms = await asyncio.to_thread(smartturn.predict, audio)
    except Exception as e:
        fail(f"turn: {type(e).__name__}")
        raise HTTPException(503, "turn model failed")
    return {"p": p, "ms": ms}


@app.post("/v1/audio/transcriptions", dependencies=auth)
async def transcriptions(request: Request):
    form = await request.form()
    upload = form.get("file")
    if upload is None or isinstance(upload, str):
        raise HTTPException(400, "field 'file' is required")
    if NOT:
        await wake_local()
    status, error = await engine_status()
    if status != "ready":
        raise HTTPException(503, f"ASR engine {status}: {error or ''}".strip())

    fields = [(k, v) for k, v in form.multi_items() if k != "file" and isinstance(v, str)]
    opts = dict(fields)
    want = opts.get("response_format", "json")
    stream = str(opts.get("stream", "")).lower() in ("true", "1")
    if want not in ("json", "text", "verbose_json"):
        raise HTTPException(400, "response_format must be json, text or verbose_json")
    lang = iso_language(opts.get("language"))
    drop = {"model", "language", "response_format", "timestamps", "timestamp_granularities[]"}
    data = [(k, v[:2000]) for k, v in fields if k not in drop and k in ENGINE_FIELDS]
    data += [("model", cfg["model"]), ("response_format", "json")]  # text / verbose_json are built here
    if lang:
        data.append(("language", lang))
    if not opts.get("prompt") and cfg.get("context"):
        data.append(("prompt", cfg["context"]))  # names and terms the model should expect
    # the gate first: a waiting upload stays in the spooled form file, only the few that run are read into
    # memory (up to 200 MB each)
    try:
        ticket = await gate.enter(stage_of(request))
    except GateFull:
        raise HTTPException(503, "ASR busy: too many recordings waiting")
    try:
        audio = await read_upload(upload)
        bad = await asyncio.to_thread(audio_rate_ok, audio)
    except BaseException:
        gate.leave(ticket)
        raise
    if bad:
        gate.leave(ticket)
        raise HTTPException(415, bad)
    files = {"file": (upload.filename or "audio", audio, upload.content_type)}
    # httpx takes form fields as a dict of lists
    form_data = {}
    for k, v in data:
        form_data.setdefault(k, []).append(v)
    stats["requests"] += 1
    t0 = time.time()
    if local:
        try:
            return await local_transcription(upload, audio, want, stream, lang, t0, PrioGate.headers(ticket))
        finally:
            gate.leave(ticket)
    if not stream:
        stats["active"] += 1
        try:
            r = await client.post(engine_url("/v1/audio/transcriptions"), data=form_data, files=files)
        except httpx.HTTPError as e:
            fail(f"engine unreachable: {e}")
            raise HTTPException(502, f"engine unreachable: {e}")
        finally:
            stats["active"] -= 1
            gate.leave(ticket)
        dt = time.time() - t0
        if r.status_code != 200:
            fail(r.text[:300])
            return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))
        out = r.json()
        audio_s = (out.get("usage") or {}).get("seconds")
        recent.append((dt, audio_s or None, None))
        headers = {"X-Processing-Seconds": f"{dt:.3f}", **PrioGate.headers(ticket)}
        if want == "text":
            return PlainTextResponse(out["text"], headers=headers)
        if want == "verbose_json":
            return JSONResponse({"task": "transcribe", "language": lang or "auto", "duration": audio_s,
                                 "text": out["text"], "segments": [], "processing_s": round(dt, 3)},
                                headers=headers)
        return JSONResponse(dict(out, processing_s=round(dt, 3)), headers=headers)

    # Streaming: open the upstream stream first so engine errors still become proper HTTP errors.
    stats["streams"] += 1
    req = client.build_request("POST", engine_url("/v1/audio/transcriptions"), data=form_data, files=files)
    try:
        upstream = await client.send(req, stream=True)
    except BaseException as e:
        gate.leave(ticket)
        if isinstance(e, httpx.HTTPError):
            fail(f"engine unreachable: {e}")
            raise HTTPException(502, f"engine unreachable: {e}")
        raise
    if upstream.status_code != 200:
        gate.leave(ticket)
        content = await upstream.aread()
        await upstream.aclose()
        fail(content.decode(errors="replace")[:300])
        return Response(content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"))

    async def relay():
        stats["active"] += 1
        first = None
        try:
            async for chunk in upstream.aiter_raw():
                if first is None:
                    first = time.time() - t0
                yield chunk
            recent.append((time.time() - t0, None, first))
        except Exception as e:
            fail(f"stream aborted: {e}")
            raise
        finally:
            stats["active"] -= 1
            gate.leave(ticket)
            await upstream.aclose()

    return StreamingResponse(relay(), status_code=200, media_type=upstream.headers.get("content-type"),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **PrioGate.headers(ticket)})


async def local_transcription(upload, audio, want, stream, lang, t0, waited=None):
    import tempfile
    suffix = os.path.splitext(upload.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)  # read once above: a second read of the upload would be empty
        path = tmp.name
    stats["active"] += 1
    try:
        text, audio_s = await asyncio.to_thread(local.transcribe_file, path)
    except ValueError as e:
        fail(str(e))
        raise HTTPException(415, str(e))
    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    finally:
        stats["active"] -= 1
        os.unlink(path)
    dt = time.time() - t0
    recent.append((dt, audio_s or None, dt if stream else None))
    headers = {"X-Processing-Seconds": f"{dt:.3f}", **(waited or {})}
    if stream:
        stats["streams"] += 1
        return Response(parakeet.sse(text, audio_s), media_type="text/event-stream",
                        headers=dict(headers, **{"Cache-Control": "no-cache"}))
    if want == "text":
        return PlainTextResponse(text, headers=headers)
    if want == "verbose_json":
        return JSONResponse({"task": "transcribe", "language": lang or "de", "duration": audio_s,
                             "text": text, "segments": [], "processing_s": round(dt, 3)}, headers=headers)
    return JSONResponse({"text": text, "usage": {"type": "duration", "seconds": round(audio_s, 2)},
                         "processing_s": round(dt, 3)}, headers=headers)


if __name__ == "__main__":
    quiet_access_log()
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
