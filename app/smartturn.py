"""Satzende am Tonfall (panel satzende.py, admin chat.turn_tone, off by default): Smart Turn v3.2 on the model computer.

Smart Turn (pipecat-ai/smart-turn, BSD-2-Clause) hears from the last 8 seconds of a recording whether the speaker
sounds finished and gives a number from 0 to 1 (1: finished). It only measures (plan "Ins Wort fallen und Satzende am
Tonfall", B1); the panel decides nothing with it yet. The model is the int8 ONNX file (8 MB, CPU) as Daily ships it in
its pipecat-ai wheel: install.sh fetches that wheel from PyPI at the pinned version, checks the wheel and the model
against their SHA-256 below and keeps only the model. No pickle, no code from the model, no transformers: the
Whisper log-mel features are computed here with numpy, the session runs on onnxruntime (already in venv-panel).

asr_proxy.py answers POST /v1/turn with {"p": 0.82, "ms": 31}; without the model file the answer is a 503 and the
panel logs "p=none".
"""
import hashlib
import os
import io
import threading
import time
import wave

import numpy as np

from common import PREFIX

WHEEL_VERSION = "1.12.0"   # pipecat-ai on PyPI, 2026-09-26
WHEEL_PATH = "10/fe/566fd73f43e66ce48b9a7e5dfa9cf79c713184978681708ac5c109c233ee"   # its folder on files.pythonhosted.org
WHEEL_URL = f"https://files.pythonhosted.org/packages/{WHEEL_PATH}/pipecat_ai-{WHEEL_VERSION}-py3-none-any.whl"
WHEEL_SHA256 = "4cd3dc071b7b64da7ac700a26a224b773ae6ef8d6694a4566332d2e5e39ed6d9"
MEMBER = "pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx"
MODEL_SHA256 = "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f"
MODEL = os.path.join(PREFIX, "smartturn", "smart-turn-v3.2-cpu.onnx")   # root's, read-only for the service

RATE = 16000
SECONDS = 8                 # the model hears the last 8 s, shorter recordings get silence in front
MAX_BYTES = 2 * 1024 ** 2   # a 16 kHz mono WAV of 8 s is 256 KB; the panel sends no more than SECONDS
N_FFT, HOP, MELS = 400, 160, 80

_lock = threading.Lock()
_session = None


def _slaney(f):
    """Hertz to mel on the Slaney scale (linear below 1 kHz, logarithmic above), as Whisper uses it."""
    f = np.asarray(f, dtype=np.float64)
    return np.where(f < 1000.0, 3.0 * f / 200.0, 15.0 + np.log(np.maximum(f, 1e-9) / 1000.0) * 27.0 / np.log(6.4))


def _slaney_hz(m):
    m = np.asarray(m, dtype=np.float64)
    return np.where(m < 15.0, 200.0 * m / 3.0, 1000.0 * np.exp((m - 15.0) * np.log(6.4) / 27.0))


def _filters():
    """The 80 triangular mel filters over the 201 FFT bins, area-normalized (Slaney), shape (201, 80)."""
    edges = _slaney_hz(np.linspace(_slaney(0.0), _slaney(RATE / 2), MELS + 2))
    bins = np.linspace(0, RATE // 2, N_FFT // 2 + 1)
    rise = (bins[:, None] - edges[None, :-2]) / np.diff(edges)[None, :-1]
    fall = (edges[None, 2:] - bins[:, None]) / np.diff(edges)[None, 1:]
    return np.maximum(0.0, np.minimum(rise, fall)) * (2.0 / (edges[2:] - edges[:-2]))[None, :]


FILTERS = _filters()
WINDOW = np.hanning(N_FFT + 1)[:-1]   # periodic Hann window


def features(audio):
    """Whisper log-mel features of exactly SECONDS of 16 kHz audio (the end kept), shape (80, 800), float32."""
    n = RATE * SECONDS
    x = np.asarray(audio, dtype=np.float32)[-n:]
    x = np.pad(x, (n - x.size, 0))
    x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)
    p = np.pad(x.astype(np.float64), (N_FFT // 2, N_FFT // 2), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(p, N_FFT)[::HOP]
    power = np.abs(np.fft.rfft(frames * WINDOW, axis=-1)) ** 2          # (801, 201)
    mel = np.log10(np.maximum(1e-10, power @ FILTERS)).T[:, :-1]       # (80, 800)
    mel = np.maximum(mel, mel.max() - 8.0)
    return ((mel + 4.0) / 4.0).astype(np.float32)


def present():
    return os.path.isfile(MODEL)


def _load():
    global _session
    with _lock:
        if _session is None:
            with open(MODEL, "rb") as f:
                blob = f.read()
            if hashlib.sha256(blob).hexdigest() != MODEL_SHA256:   # checked before every load, never run unchecked
                raise ValueError("Smart Turn model does not match its SHA-256")
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = 1
            so.inter_op_num_threads = 1
            _session = ort.InferenceSession(blob, sess_options=so, providers=["CPUExecutionProvider"])
    return _session


def pcm(data):
    """16 kHz mono float32 from WAV bytes as the panel sends them (16-bit, 16 kHz, mono); ValueError otherwise."""
    if len(data) > MAX_BYTES:
        raise ValueError("recording too large")
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != RATE:
                raise ValueError("16 kHz mono 16-bit WAV only")
            raw = w.readframes(RATE * SECONDS * 2)
    except (wave.Error, EOFError) as e:
        raise ValueError("not a WAV recording") from e
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def predict(audio):
    """(p, ms): how finished the speaker sounds (0 to 1) and how long it took."""
    t0 = time.perf_counter()
    out = _load().run(None, {"input_features": features(audio)[None]})[0]
    p = float(np.asarray(out).reshape(-1)[0])
    if not 0.0 <= p <= 1.0:   # the file gives the sigmoid already; a raw logit would be squeezed here
        p = float(1.0 / (1.0 + np.exp(-p)))
    return round(p, 3), int(round((time.perf_counter() - t0) * 1000))
