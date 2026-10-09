"""Qwen3-ASR as a small HTTP service (OpenAI-style /v1/audio/transcriptions)."""
import os
import subprocess
import tempfile
import time

import soundfile as sf
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from common import ASR_ISO as ISO, BodyLimit, KeyedCORS, inside, outside_view, ServiceState, api_key_dependency, api_key_ok, check_memory, estimate_gib, load_config, quiet_access_log, SpeechMark, torch_dtype

cfg = load_config("asr")
state = ServiceState("asr", cfg)
app = FastAPI(title="Qwen3-ASR (DGX Spark)")
# innermost: only requests that passed the size limit and API key count as speech
app.add_middleware(SpeechMark)
app.add_middleware(KeyedCORS)
# bodies are refused before they are read when too large or without the API key
app.add_middleware(BodyLimit, default=200 * 1024**2, gate=api_key_ok, gated=("/v1/",))
auth = [Depends(api_key_dependency())]


def load_model(cfg):
    need = estimate_gib(cfg["model"]) + (estimate_gib(cfg["aligner_model"]) if cfg.get("timestamps") else 0)
    check_memory(need)
    from qwen_asr import Qwen3ASRModel
    dtype = torch_dtype(cfg["dtype"])
    kwargs = dict(
        dtype=dtype,
        device_map="cuda:0",
        attn_implementation="sdpa",  # flash-attn does not build for GB10 (sm_121)
        max_inference_batch_size=cfg["max_batch_size"],
        max_new_tokens=cfg["max_new_tokens"],
    )
    if cfg.get("timestamps"):
        kwargs["forced_aligner"] = cfg["aligner_model"]
        kwargs["forced_aligner_kwargs"] = dict(dtype=dtype, device_map="cuda:0", attn_implementation="sdpa")
    model = Qwen3ASRModel.from_pretrained(cfg["model"], **kwargs)
    # warm-up: the first transcription after loading is much slower than the rest
    try:
        import numpy as np
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            sf.write(tmp.name, (np.random.default_rng(0).standard_normal(16000) * 0.001).astype("float32"), 16000)
            model.transcribe(audio=tmp.name, language=None)
    except Exception as e:
        print(f"warm-up failed: {type(e).__name__}: {e}", flush=True)
    return model



def load_parakeet(cfg):
    """asr.recognizer = "parakeet": the CPU model instead of Qwen3-ASR (see parakeet.py)."""
    import parakeet
    rec = parakeet.Recognizer()
    rec.load()
    if rec.status != "ready":
        raise RuntimeError(rec.error)
    return rec


PARAKEET = cfg.get("recognizer") == "parakeet"


@app.on_event("startup")
def startup():
    state.load_in_background(load_parakeet if PARAKEET else load_model)


@app.get("/health")
def health(request: Request):
    out = state.health({"timestamps": bool(cfg.get("timestamps")) and not PARAKEET})
    if not inside(request):
        return outside_view(out)
    if PARAKEET:
        import parakeet
        out.update(model=parakeet.NAME, recognizer="parakeet")
    return out


@app.get("/v1/models", dependencies=auth)
def models():
    return {"object": "list", "data": [{"id": cfg["model"], "object": "model", "owned_by": "local"}]}


@app.get("/v1/languages")
def languages():
    from qwen_asr.inference.utils import SUPPORTED_LANGUAGES
    return {"languages": ["auto"] + list(SUPPORTED_LANGUAGES)}


def as_wav(path):
    """Browser and phone recordings arrive as webm / mp4 / m4a / ogg, which libsndfile
    cannot read ("Format not recognised"). Anything soundfile can open is used as is;
    everything else is converted with ffmpeg (installed by install.sh) to 16 kHz mono
    WAV first. Returns (path to read, seconds of audio, path to delete or None)."""
    try:
        info = sf.info(path)
        return path, info.frames / info.samplerate, None
    except Exception:
        pass
    wav = path + ".wav"
    run = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", path, "-t", "7200",
                          "-ac", "1", "-ar", "16000", "-f", "wav", wav],
                         capture_output=True, text=True, timeout=120)
    if run.returncode != 0:
        if os.path.exists(wav):
            os.unlink(wav)
        raise HTTPException(415, f"unsupported audio: {run.stderr.strip()[-200:] or 'ffmpeg failed'}")
    info = sf.info(wav)
    return wav, info.frames / info.samplerate, wav


@app.post("/v1/audio/transcriptions", dependencies=auth)
async def transcriptions(
    file: UploadFile = File(...),
    language: str = Form(None),
    timestamps: bool = Form(False),
    response_format: str = Form("json"),  # json | verbose_json | text, as in the OpenAI API
    model: str = Form(None),  # accepted for OpenAI client compatibility, ignored
    prompt: str = Form(None),
    temperature: float = Form(None),
):
    if state.status != "ready":
        raise HTTPException(503, f"model {state.status}: {state.error or 'still loading'}")
    if PARAKEET:
        return await parakeet_transcription(file, response_format)
    if timestamps and not cfg.get("timestamps"):
        raise HTTPException(400, "timestamps are disabled in the config")
    lang = language or cfg.get("default_language") or "auto"
    lang = None if lang.lower() == "auto" else lang
    if lang and len(lang) <= 3:  # OpenAI clients send ISO codes like "de"
        lang = ISO.get(lang.lower(), lang)

    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await read_limited(file))
        path = tmp.name
    converted = None
    try:
        read, audio_s, converted = as_wav(path)
        t0 = time.time()
        with state.lock:
            r = state.model.transcribe(audio=read, context=prompt or cfg.get("context") or "",
                                       language=lang, return_time_stamps=timestamps)[0]
        dt = time.time() - t0
        state.record(dt, audio_s)
    except HTTPException as e:
        state.record(0, error=e.detail)
        raise
    except Exception as e:
        state.record(0, error=f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    finally:
        os.unlink(path)
        if converted:
            os.unlink(converted)

    if response_format == "text":
        return PlainTextResponse(r.text)
    out = {"text": r.text, "language": r.language, "duration": audio_s, "processing_s": round(dt, 3)}
    if timestamps and r.time_stamps is not None:
        out["words"] = [{"word": i.text, "start": i.start_time, "end": i.end_time} for i in r.time_stamps.items]
    return out


MAX_UPLOAD = 200 * 1024**2  # as the size limit in front of the service


async def read_limited(file):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "audio file larger than 200 MB")
    return data


async def parakeet_transcription(file, response_format):
    import asyncio
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await read_limited(file))
        path = tmp.name
    try:
        t0 = time.time()
        text, audio_s = await asyncio.to_thread(state.model.transcribe_file, path)
        dt = time.time() - t0
        state.record(dt, audio_s)
    except ValueError as e:
        state.record(0, error=str(e))
        raise HTTPException(415, str(e))
    except Exception as e:
        state.record(0, error=f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    finally:
        os.unlink(path)
    if response_format == "text":
        return PlainTextResponse(text)
    return {"text": text, "language": "German", "duration": audio_s, "processing_s": round(dt, 3)}


if __name__ == "__main__":
    quiet_access_log()
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
