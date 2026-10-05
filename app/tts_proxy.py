"""Qwen3-TTS front end for the vllm-omni engine (backend "vllm-omni").

The engine (Docker, 127.0.0.1 only) does the work, including streaming:
`stream: true` returns OpenAI `speech.audio.*` Server-Sent Events with base64 PCM
16 bit mono 24 kHz chunks. This service sits on the public TTS port and adds the API
key, defaults (voice, language, format), routing of VoiceDesign requests to the second
engine, and the counters the panel shows. Request and stream pass through unchanged.
"""
import base64
import json
import os
import subprocess
import time
from collections import deque

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from common import api_key_dependency, load_config

STATE_DIR = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
LANGUAGES = ["auto", "Chinese", "English", "Japanese", "Korean", "German", "French",
             "Russian", "Portuguese", "Spanish", "Italian"]
PCM_BYTES_PER_S = 24000 * 2  # Qwen3-TTS: 24 kHz, 16 bit, mono

cfg = load_config("tts")
app = FastAPI(title="Qwen3-TTS via vllm-omni (DGX Spark)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
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
    return out


def model_kind(model):
    name = model.lower()
    return "voice_design" if "voicedesign" in name else "base" if name.endswith("-base") else "custom_voice"


def unit_active(unit):
    try:
        return subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True,
                              timeout=5).stdout.strip()
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
    unit = f"speech-spark-tts-{'engine' if role == 'main' else 'design'}"
    try:
        with open(os.path.join(STATE_DIR, f"speech-spark-tts-{role}.json")) as f:
            st = json.load(f)
    except Exception:
        st = {}
    active = unit_active(unit)
    if st.get("status") in ("blocked", "error") and active != "active":
        return st["status"], st.get("error")
    if active in ("active", "activating"):
        return "loading", "engine starting (first start downloads the image and model)"
    return "stopped", f"{unit} is {active}"


async def engine_voices(role):
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


@app.get("/health")
async def health():
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
    return out


@app.get("/v1/models", dependencies=auth)
def models():
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "local"}
                                       for m, _ in engines().values()]}


@app.get("/v1/voices")
async def voices_for_panel():
    status, _ = await engine_status("main")
    return {"model_kind": model_kind(cfg["model"]) if status == "ready" else None,
            "voices": await engine_voices("main") if status == "ready" else [],
            "languages": LANGUAGES, "voicedesign": "design" in engines()}


@app.get("/v1/audio/voices", dependencies=auth)
async def audio_voices():
    _, port = engines()["main"]
    r = await client.get(f"http://127.0.0.1:{port}/v1/audio/voices")
    return Response(r.content, status_code=r.status_code, media_type="application/json")


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

    role = "main"
    if str(body.get("task_type", "")).lower() == "voicedesign" and model_kind(cfg["model"]) != "voice_design":
        if "design" not in engines():
            raise HTTPException(400, "VoiceDesign is not enabled on this server (panel: Konfiguration -> TTS)")
        role = "design"
    model, port = engines()[role]
    status, error = await engine_status(role)
    if status != "ready":
        raise HTTPException(503, f"TTS engine {status}: {error or ''}".strip())

    stream = bool(body.get("stream")) or body.get("stream_format") in ("sse", "audio")
    body["model"] = model  # vLLM checks this field; clients send anything (tts-1, qwen3-tts, ...)
    body.setdefault("response_format", "pcm" if stream else "mp3")
    if not body.get("language") or str(body["language"]).lower() == "auto":
        lang = cfg.get("default_language") or "auto"
        body["language"] = "Auto" if lang.lower() == "auto" else lang
    if "instruct" in body and "instructions" not in body:  # older field name of this API
        body["instructions"] = body.pop("instruct")
    if not body.get("instructions") and cfg.get("default_instruct"):
        body["instructions"] = cfg["default_instruct"]
    if role == "main" and model_kind(model) != "voice_design":
        known = {v.lower(): v for v in await engine_voices(role)}
        voice = str(body.get("voice") or cfg.get("default_voice") or "")
        # unknown names (e.g. OpenAI's "alloy") fall back to the configured default voice
        body["voice"] = known.get(voice.lower()) or known.get(str(cfg.get("default_voice", "")).lower()) or voice
    else:
        body.pop("voice", None)

    url = f"http://127.0.0.1:{port}/v1/audio/speech"
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
        dt = time.time() - t0
        if r.status_code != 200:
            fail(r.text[:300])
        else:
            audio_s = len(r.content) / PCM_BYTES_PER_S if body["response_format"] == "pcm" else None
            recent.append((dt, audio_s, None))
        headers = {k: v for k, v in r.headers.items() if k.lower().startswith("x-vllm-omni")}
        headers["X-Processing-Seconds"] = f"{dt:.3f}"
        return Response(r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type"), headers=headers)

    # Streaming: open the upstream stream first so engine errors still become proper HTTP errors.
    stats["streams"] += 1
    req = client.build_request("POST", url, json=body)
    try:
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        fail(f"engine unreachable: {e}")
        raise HTTPException(502, f"engine unreachable: {e}")
    if upstream.status_code != 200:
        content = await upstream.aread()
        await upstream.aclose()
        fail(content.decode(errors="replace")[:300])
        return Response(content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"))

    sse = "event-stream" in upstream.headers.get("content-type", "")

    async def relay():
        stats["active"] += 1
        first, pcm_bytes, buf = None, 0, b""
        try:
            async for chunk in upstream.aiter_raw():
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
            await upstream.aclose()

    return StreamingResponse(relay(), status_code=200, media_type=upstream.headers.get("content-type"),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
