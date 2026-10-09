"""Qwen3-TTS as a small HTTP service (OpenAI-style /v1/audio/speech).

Works with all three model kinds:
  *-CustomVoice  -> built-in speakers ("voice" = speaker name, optional instruct)
  *-VoiceDesign  -> "instruct" describes the voice
  *-Base         -> voice cloning from VOICES_DIR/<name>.wav + <name>.txt
"""
import io
import os
import time

import soundfile as sf
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from common import BodyLimit, KeyedCORS, inside, outside_view, ServiceState, api_key_dependency, api_key_ok, check_memory, estimate_gib, load_config, quiet_access_log, torch_dtype
from textnorm import MAX_INPUT, apply_pronunciations, clean_text, hide_secrets, parse_pronunciations, speak_numbers

VOICES_DIR = os.environ.get("SPEECH_SPARK_VOICES", "/var/lib/speech-spark/voices")

cfg = load_config("tts")
PRONUNCIATION = parse_pronunciations(cfg.get("pronunciation", ""))
state = ServiceState("tts", cfg)
app = FastAPI(title="Qwen3-TTS (DGX Spark)")
app.add_middleware(KeyedCORS)
# bodies are refused before they are read when too large or without the API key
app.add_middleware(BodyLimit, default=1024**2, gate=api_key_ok, gated=("/v1/",))
auth = [Depends(api_key_dependency())]
# OpenAI response_format -> (soundfile format, subtype, media type)
FORMATS = {"mp3": ("MP3", None, "audio/mpeg"), "wav": ("WAV", None, "audio/wav"),
           "flac": ("FLAC", None, "audio/flac"), "opus": ("OGG", "OPUS", "audio/ogg"),
           "pcm": ("RAW", "PCM_16", "audio/pcm")}
_clone_prompts = {}  # voice name -> (mtime, prompt)


def load_model(cfg):
    check_memory(estimate_gib(cfg["model"]))
    from qwen_tts import Qwen3TTSModel
    model = Qwen3TTSModel.from_pretrained(
        cfg["model"],
        device_map="cuda:0",
        dtype=torch_dtype(cfg["dtype"]),
        attn_implementation="sdpa",  # flash-attn does not build for GB10 (sm_121)
    )
    # warm-up: the first generation after loading is much slower than the rest
    try:
        kind = getattr(model.model, "tts_model_type", None)
        if kind == "custom_voice":
            speakers = model.get_supported_speakers() or []
            speaker = cfg.get("default_voice") if cfg.get("default_voice") in speakers else speakers[0]
            model.generate_custom_voice(text="Hallo.", speaker=speaker, language="Auto")
        elif kind == "voice_design":
            model.generate_voice_design(text="Hallo.", instruct="ruhige Stimme", language="Auto")
    except Exception as e:
        print(f"warm-up failed: {type(e).__name__}: {e}", flush=True)
    return model


def model_kind():
    return getattr(state.model.model, "tts_model_type", None) if state.model else None


def clone_voices():
    if not os.path.isdir(VOICES_DIR):
        return []
    return sorted(f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))


def voices():
    kind = model_kind()
    if kind == "custom_voice":
        return state.model.get_supported_speakers() or []
    if kind == "base":
        return clone_voices()
    return []


@app.on_event("startup")
def startup():
    state.load_in_background(load_model)


@app.get("/health")
def health(request: Request):
    out = state.health({"model_kind": model_kind()})
    return out if inside(request) else outside_view(out)


@app.get("/v1/models", dependencies=auth)
def models():
    return {"object": "list", "data": [{"id": cfg["model"], "object": "model", "owned_by": "local"}]}


@app.get("/v1/voices")
def list_voices(request: Request):
    if not inside(request):
        raise HTTPException(401, "invalid or missing API key")
    if state.status != "ready":
        return {"model_kind": None, "voices": [], "languages": []}
    return {
        "model_kind": model_kind(),
        "voices": voices(),
        "languages": ["auto"] + list(state.model.get_supported_languages() or []),
    }


class SpeechRequest(BaseModel):
    input: str
    voice: str | None = None
    language: str | None = None
    instruct: str | None = None
    response_format: str = "mp3"  # OpenAI default
    speed: float | None = None  # accepted for OpenAI client compatibility, ignored
    model: str | None = None  # accepted for OpenAI client compatibility, ignored


def clone_prompt(name):
    wav = os.path.join(VOICES_DIR, name + ".wav")
    txt = os.path.join(VOICES_DIR, name + ".txt")
    if not os.path.exists(wav):
        raise HTTPException(400, f"unknown voice '{name}', available: {clone_voices()}")
    mtime = os.path.getmtime(wav)
    cached = _clone_prompts.get(name)
    if cached and cached[0] == mtime:
        return cached[1]
    ref_text = open(txt).read().strip() if os.path.exists(txt) else None
    prompt = state.model.create_voice_clone_prompt(
        ref_audio=wav, ref_text=ref_text, x_vector_only_mode=ref_text is None
    )
    _clone_prompts[name] = (mtime, prompt)
    return prompt


@app.post("/v1/audio/speech", dependencies=auth)
def speech(req: SpeechRequest):
    if state.status != "ready":
        raise HTTPException(503, f"model {state.status}: {state.error or 'still loading'}")
    if req.response_format not in FORMATS:
        raise HTTPException(400, f"response_format must be one of {list(FORMATS)}")
    lang = req.language or cfg.get("default_language") or "auto"
    instruct = req.instruct if req.instruct is not None else cfg.get("default_instruct", "")
    text = req.input
    if len(text) > MAX_INPUT:
        raise HTTPException(400, f"input: at most {MAX_INPUT} characters per request")
    text = hide_secrets(text, lang)  # always, whatever clean_text says (textnorm.SECRET_HINT)
    if cfg.get("clean_text", True):
        text = clean_text(text, calm=cfg.get("calm", True))
    if PRONUNCIATION:
        text = apply_pronunciations(text, PRONUNCIATION)
    if cfg.get("numbers", "words") != "off":
        try:
            text = speak_numbers(text, lang, cfg.get("numbers", "words"))
        except Exception as e:  # never fail a request over number formatting
            print(f"speak_numbers failed: {type(e).__name__}: {e}", flush=True)
    if not text.strip():
        raise HTTPException(400, "nothing left to speak after removing emojis and markup")
    voice = req.voice or cfg.get("default_voice")
    kind = model_kind()
    # OpenAI clients send their own voice names (alloy, nova, ...): fall back to the default.
    known = {v.lower(): v for v in voices()}
    if kind in ("custom_voice", "base") and voice and voice.lower() not in known:
        voice = cfg.get("default_voice")
    voice = known.get((voice or "").lower(), voice)
    try:
        t0 = time.time()
        with state.lock:
            if kind == "custom_voice":
                wavs, sr = state.model.generate_custom_voice(
                    text=text, speaker=voice, language=lang, instruct=instruct or None)
            elif kind == "voice_design":
                wavs, sr = state.model.generate_voice_design(
                    text=text, instruct=instruct, language=lang)
            elif kind == "base":
                wavs, sr = state.model.generate_voice_clone(
                    text=text, language=lang, voice_clone_prompt=clone_prompt(voice))
            else:
                raise HTTPException(500, f"unsupported model kind {kind}")
        dt = time.time() - t0
        state.record(dt, len(wavs[0]) / sr)
    except HTTPException:
        raise
    except Exception as e:
        state.record(0, error=f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"{type(e).__name__}: {e}")

    fmt, subtype, media = FORMATS[req.response_format]
    buf = io.BytesIO()
    sf.write(buf, wavs[0], sr, format=fmt, subtype=subtype)
    return Response(buf.getvalue(), media_type=media,
                    headers={"X-Processing-Seconds": f"{dt:.3f}"})


if __name__ == "__main__":
    quiet_access_log()
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
