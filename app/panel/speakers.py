"""Speaker identification for profiles (optional; off unless the admin enables it).

Each profile can record a few sentences; their voice embeddings are kept in the profile's folder:

    USERS_DIR/<user id>/voice.json   {"samples": [[256 floats], ...], "updated": epoch}

A spoken question is compared with every enrolled profile. Only a clear match (similarity above
the threshold and clearly ahead of the runner-up) picks a profile; anything else stays as it was.

The embedding model is Resemblyzer's voice encoder (GE2E, 3-layer LSTM over 40 mel bands,
Apache 2.0, https://github.com/resemble-ai/Resemblyzer). Its weights ship as voice_encoder.npz
and run here in plain numpy, so the panel needs neither torch nor a GPU (~20 ms per second of
audio on the CPU).
"""
import hashlib
import hmac
import secrets
import io
import json
import os
import subprocess
import threading
import time
import wave

import numpy as np

import profiles

SR = 16000
N_FFT, HOP, N_MELS = 400, 160, 40         # 25 ms windows, 10 ms steps
PARTIAL = 160                             # frames per partial utterance (1.6 s)
MAX_SAMPLES = 10
MIN_SECONDS = 1.0
MAX_SECONDS = 120
_W = None
_lock = threading.Lock()


# ---------------------------------------------------------------- audio
def decode(data):
    """16 kHz mono float32 from WAV bytes (any rate) or, via ffmpeg, any other audio file."""
    if data[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(data)) as w:
                if w.getsampwidth() == 2:
                    x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
                    if w.getnchannels() > 1:
                        x = x.reshape(-1, w.getnchannels()).mean(axis=1)
                    rate = w.getframerate()
                    # a made-up rate in the header ("1 Hz") would blow a tiny file up 16000-fold
                    if not 8000 <= rate <= 48000:
                        raise ValueError("unsupported sample rate")
                    x = x[:rate * MAX_SECONDS]
                    if rate != SR:
                        n = int(len(x) * SR / rate)
                        x = np.interp(np.arange(n) * rate / SR, np.arange(len(x)), x).astype(np.float32)
                    return x
        except (wave.Error, EOFError):
            pass
    # at most MAX_SECONDS of audio, however small and well compressed the file is
    p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-t", str(MAX_SECONDS),
                        "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"], input=data, capture_output=True, timeout=60)
    if p.returncode or not p.stdout:
        raise ValueError("cannot read this audio")
    return np.frombuffer(p.stdout, "<i2").astype(np.float32) / 32768


def preprocess(x):
    """Louder to -30 dBFS if quiet, long pauses cut (like Resemblyzer, with an energy gate
    instead of webrtcvad)."""
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    gain = 10 ** ((-30 - 20 * np.log10(rms)) / 20)
    if gain > 1:
        x = x * gain
    win = SR * 30 // 1000
    x = x[:len(x) - len(x) % win]
    if not len(x):
        return x
    e = np.sqrt(np.mean(x.reshape(-1, win) ** 2, axis=1))
    voiced = e > max(0.01, np.percentile(e, 20) * 2.5)
    voiced = np.convolve(voiced, np.ones(8) / 8, mode="same") >= 0.5          # smooth
    voiced = np.convolve(voiced, np.ones(7), mode="same") > 0                 # keep up to 180 ms around speech
    return x[np.repeat(voiced, win)]


def _mel_filters():
    """Slaney-style mel filter bank, as librosa.filters.mel(sr=16000, n_fft=400, n_mels=40)."""
    def hz_to_mel(f):
        f = np.asanyarray(f, dtype=np.float64)
        m = f / (200.0 / 3)
        return np.where(f >= 1000, 15 + np.log(np.maximum(f, 1e-10) / 1000) / (np.log(6.4) / 27), m)

    def mel_to_hz(m):
        m = np.asanyarray(m, dtype=np.float64)
        f = m * (200.0 / 3)
        return np.where(m >= 15, 1000 * np.exp((np.log(6.4) / 27) * (m - 15)), f)

    fft_f = np.linspace(0, SR / 2, N_FFT // 2 + 1)
    mel_f = mel_to_hz(np.linspace(hz_to_mel(0), hz_to_mel(SR / 2), N_MELS + 2))
    fdiff = np.diff(mel_f)
    ramps = mel_f[:, None] - fft_f[None, :]
    lower = -ramps[:-2] / fdiff[:-1, None]
    upper = ramps[2:] / fdiff[1:, None]
    w = np.maximum(0, np.minimum(lower, upper))
    w *= (2.0 / (mel_f[2:N_MELS + 2] - mel_f[:N_MELS]))[:, None]
    return w.astype(np.float32)


_MEL = _mel_filters()
_WIN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)


def mel(x):
    """Power mel spectrogram, frames x 40 (librosa.feature.melspectrogram with center=True)."""
    x = np.pad(x, N_FFT // 2, mode="reflect")
    n = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * _WIN, axis=1)) ** 2
    return (spec @ _MEL.T).astype(np.float32)


# ---------------------------------------------------------------- model
def _weights():
    global _W
    if _W is None:
        with np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_encoder.npz")) as z:
            _W = {k: z[k].astype(np.float32) for k in z.files}
    return _W


def _sigmoid(x):
    return 0.5 * (1 + np.tanh(0.5 * x))


def _encode(mels):
    """Embeddings of a batch of partial utterances (B x 160 x 40) -> B x 256, L2-normed."""
    w = _weights()
    h_seq = mels
    for layer in range(3):
        wi, wh = w[f"lstm_weight_ih_l{layer}"], w[f"lstm_weight_hh_l{layer}"]
        b = w[f"lstm_bias_ih_l{layer}"] + w[f"lstm_bias_hh_l{layer}"]
        xs = h_seq @ wi.T + b                       # B x T x 1024, gates i, f, g, o
        h = np.zeros((mels.shape[0], 256), np.float32)
        c = np.zeros_like(h)
        out = np.empty((mels.shape[0], mels.shape[1], 256), np.float32)
        for t in range(mels.shape[1]):
            g = xs[:, t] + h @ wh.T
            i, f, gg, o = _sigmoid(g[:, :256]), _sigmoid(g[:, 256:512]), np.tanh(g[:, 512:768]), _sigmoid(g[:, 768:])
            c = f * c + i * gg
            h = o * np.tanh(c)
            out[:, t] = h
        h_seq = out
    e = np.maximum(0, h @ w["linear_weight"].T + w["linear_bias"])
    return e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9)


def embed(x, rate=1.3, min_coverage=0.75):
    """Utterance embedding (256,), like VoiceEncoder.embed_utterance; None if too little speech."""
    x = preprocess(x)
    if len(x) < SR * MIN_SECONDS:
        return None
    n_frames = int(np.ceil((len(x) + 1) / HOP))
    step = int(np.round((SR / rate) / HOP))
    starts = list(range(0, max(1, n_frames - PARTIAL + step + 1), step))
    last = starts[-1] * HOP
    if (len(x) - last) / (PARTIAL * HOP) < min_coverage and len(starts) > 1:
        starts = starts[:-1]
    need = (starts[-1] + PARTIAL) * HOP
    if need >= len(x):
        x = np.pad(x, (0, need - len(x)))
    m = mel(x)
    e = _encode(np.stack([m[s:s + PARTIAL] for s in starts])).mean(axis=0)
    return e / np.linalg.norm(e)


# ---------------------------------------------------------------- voiceprints
def _file(uid):
    return profiles._path(uid, "voice.json")


def samples(uid):
    try:
        with open(_file(uid)) as f:
            return json.load(f).get("samples", [])
    except (OSError, ValueError):
        return []


def enroll(uid, data):
    """Adds one recording to the profile's voiceprint; returns the number of recordings."""
    e = embed(decode(data))
    if e is None:
        raise ValueError("too little speech; please speak for a few seconds")
    with _lock:
        s = (samples(uid) + [[round(float(v), 5) for v in e]])[-MAX_SAMPLES:]
        profiles._write(_file(uid), {"samples": s, "updated": int(time.time())})
    return len(s)


def forget(uid):
    with _lock:
        try:
            os.remove(_file(uid))
        except OSError:
            pass


def voiceprints():
    """{user id: mean embedding} of every enrolled profile."""
    out = {}
    for u in profiles._load()["users"]:
        s = samples(u["id"])
        if s:
            m = np.mean(np.array(s, np.float32), axis=0)
            out[u["id"]] = m / np.linalg.norm(m)
    return out


def identify(data, threshold=0.75, margin=0.05):
    """(user id, similarity) of the profile that clearly spoke this audio, else (None, best)."""
    prints = voiceprints()
    if not prints:
        return None, 0.0
    e = embed(decode(data))
    if e is None:
        return None, 0.0
    scores = sorted(((float(v @ e), uid) for uid, v in prints.items()), reverse=True)
    best, uid = scores[0]
    second = scores[1][0] if len(scores) > 1 else -1.0
    if best >= threshold and best - second >= margin:
        return uid, best
    return None, best


# ---------------------------------------------------------------- recognized speaker for one chat turn
# The speech recognition answers with a short-lived signed token; the chat request sends it back.
# So the profile still comes from the server, never from what the browser claims.
TOKEN_SECONDS = 60
_used = {}  # signature -> expiry: a token picks the profile for one answer only
STRICTNESS = {"low": 0.70, "normal": 0.75, "high": 0.82}


def _sig(msg):
    return hmac.new(profiles._secret(), b"speaker:" + msg.encode(), hashlib.sha256).hexdigest()[:32]


def token(uid, by):
    """A one-time token for a recognized voice, valid only at the profile or device (by) that sent the
    recording."""
    msg = f"{uid}.{by}.{int(time.time()) + TOKEN_SECONDS}.{secrets.token_hex(6)}"
    return f"{msg}.{_sig(msg)}"


def check(tok, by):
    """The user id a token was issued for, if it is genuine, fresh, not used before and presented by
    the same profile it was issued to; else None."""
    try:
        uid, owner, exp, nonce, sig = str(tok).rsplit(".", 4)
        now = time.time()
        if hmac.compare_digest(sig, _sig(f"{uid}.{owner}.{exp}.{nonce}")) and owner == str(by) \
                and int(exp) >= now and sig not in _used:
            for k in [k for k, v in _used.items() if v < now]:
                _used.pop(k, None)
            _used[sig] = int(exp)
            return uid
    except ValueError:
        pass
    return None
