"""Answers for the Pebble watch app: the chat runs here, the phone polls for text and audio.

The watch plays 8 kHz audio through its small speaker. To fit through Bluetooth, the TTS
output (16-bit PCM at 24 kHz) is low-passed, decimated to 8 kHz and packed as IMA ADPCM
(4 bits per sample, 4000 bytes per second). The watch app decodes it with the same tables.
"""
import asyncio
import base64
import json
import secrets
import time

import numpy as np

JOB_TTL = 600          # seconds a finished answer stays fetchable
MAX_RUNNING = 8        # answers being made at once (each one runs the LLM and TTS)
MAX_AUDIO = 6000       # ADPCM bytes per poll (1.5 s of speech)

STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
         73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
         449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
         2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
         9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
INDEX = [-1, -1, -1, -1, 2, 4, 6, 8]

# loudness for the watch speaker (8 kHz samples)
BLOCK = 80             # 10 ms
TARGET = 30000.0       # peak level the compressor aims for
MAX_GAIN = 8.0         # at most +18 dB, so pauses stay quiet
RELEASE = 0.96         # per block, about 250 ms
LIMIT = 32000.0        # soft limit at full scale

# 3.4 kHz low-pass for 24 kHz input (windowed sinc), so decimating by 3 does not alias
_N = np.arange(-24, 25)
_FIR = np.sinc(2 * 3400 / 24000 * _N) * np.hamming(len(_N))
_FIR /= _FIR.sum()


class Encoder:
    """24 kHz 16-bit PCM in, 8 kHz IMA ADPCM out, in pieces of any length."""

    def __init__(self, loud=True):
        self.tail = np.zeros(len(_FIR) - 1)
        self.phase = 0          # samples to skip before the next kept one
        self.pred, self.idx = 0, 0
        self.half = None        # low nibble waiting for its high nibble
        self.loud = loud
        self.env = 0.0          # loudness follower for the compressor
        self.g = 1.0            # gain at the end of the last block
        self.block = np.zeros(0)
        self.rest = b""         # odd byte left over from the last piece

    def feed(self, pcm: bytes) -> bytes:
        pcm = self.rest + pcm
        cut = len(pcm) // 2 * 2
        self.rest = pcm[cut:]
        x = np.frombuffer(pcm[:cut], dtype="<i2").astype(np.float64)
        if not len(x):
            return b""
        buf = np.concatenate([self.tail, x])
        y = np.convolve(buf, _FIR, mode="valid")
        self.tail = buf[-(len(_FIR) - 1):]
        y = y[self.phase::3]
        self.phase = (self.phase - len(x)) % 3
        if self.loud:
            y = self._louder(y)
        return self._adpcm(np.clip(y, -32768, 32767).astype(np.int32).tolist())

    def _louder(self, y):
        """Compressor and limiter: the watch speaker is small and quiet, so quiet syllables are
        lifted up to MAX_GAIN and peaks are pressed softly below full scale."""
        y = np.concatenate([self.block, y])
        n = len(y) // BLOCK * BLOCK
        self.block = y[n:]
        out = np.empty(n)
        for i in range(0, n, BLOCK):
            b = y[i:i + BLOCK]
            peak = float(np.abs(b).max())
            # fast attack, slow release, so loudness changes do not pump between syllables
            self.env = peak if peak > self.env else self.env * RELEASE + peak * (1 - RELEASE)
            g = min(MAX_GAIN, TARGET / max(self.env, 1.0))
            out[i:i + BLOCK] = b * np.linspace(self.g, g, BLOCK, endpoint=False)
            self.g = g
        return LIMIT * np.tanh(out / LIMIT)

    def flush(self) -> bytes:
        out = b""
        if len(self.block):  # the last few ms the compressor held back
            y = LIMIT * np.tanh(self.block * self.g / LIMIT)
            self.block = np.zeros(0)
            out = self._adpcm(np.clip(y, -32768, 32767).astype(np.int32).tolist())
        return out + (bytes([self.half]) if self.half is not None else b"")

    def _adpcm(self, samples):
        out = bytearray()
        pred, idx, half = self.pred, self.idx, self.half
        for s in samples:
            step = STEPS[idx]
            diff = s - pred
            code = 8 if diff < 0 else 0
            diff = abs(diff)
            delta = step >> 3
            if diff >= step:
                code |= 4
                diff -= step
                delta += step
            if diff >= step >> 1:
                code |= 2
                diff -= step >> 1
                delta += step >> 1
            if diff >= step >> 2:
                code |= 1
                delta += step >> 2
            pred = max(-32768, min(32767, pred - delta if code & 8 else pred + delta))
            idx = max(0, min(88, idx + INDEX[code & 7]))
            if half is None:
                half = code
            else:
                out.append(half | (code << 4))
                half = None
        self.pred, self.idx, self.half = pred, idx, half
        return bytes(out)


class Job:
    def __init__(self, speak):
        self.id = secrets.token_urlsafe(16)
        self.text, self.audio = "", bytearray()
        self.done, self.error = False, None
        self.speak = speak
        self.enc = Encoder()
        self.changed = asyncio.Event()
        self.task = None
        self.t = self.start = time.time()
        self.first_text = self.first_audio = 0.0   # when the Spark had them (for the watch's report)
        self.reported = False

    def ping(self):
        self.changed.set()
        self.changed = asyncio.Event()


JOBS: dict[str, Job] = {}


def cleanup():
    now = time.time()
    for k, j in list(JOBS.items()):
        if now - j.t > JOB_TTL:
            if j.task:
                j.task.cancel()
            JOBS.pop(k, None)


async def run(job: Job, response):
    """Reads the chat's event stream into the job."""
    try:
        async for chunk in response.body_iterator:
            for line in (chunk.decode() if isinstance(chunk, bytes) else chunk).split("\n"):
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:])
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "text":
                    job.text += ev.get("delta", "")
                    job.first_text = job.first_text or time.time()
                elif kind in ("truncated", "retract"):
                    job.text = job.text[:max(0, len(job.text) - int(ev.get("drop") or 0))]
                elif kind == "audio" and job.speak:
                    job.audio += await asyncio.to_thread(job.enc.feed, base64.b64decode(ev["audio"]))
                    job.first_audio = job.first_audio or time.time()
                elif kind == "error" and not job.error:
                    job.error = str(ev.get("message", "Fehler"))[:200]
                else:
                    continue
                job.ping()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        job.error = job.error or f"{type(e).__name__}: {e}"[:200]
    finally:
        if hasattr(response.body_iterator, "aclose"):
            await response.body_iterator.aclose()  # stops LLM and TTS when cancelled
        job.audio += job.enc.flush()
        job.done = True
        job.t = time.time()
        job.ping()


async def poll(job: Job, t: int, a: int, wait: float = 4.0):
    """New text from offset t and audio from offset a; waits a few seconds for news."""
    end = time.time() + wait
    while not job.done and len(job.text) <= t and len(job.audio) <= a and time.time() < end:
        try:
            await asyncio.wait_for(job.changed.wait(), end - time.time())
        except asyncio.TimeoutError:
            break
    chunk = bytes(job.audio[a:a + MAX_AUDIO])
    job.t = max(job.t, time.time()) if job.done else job.t
    return {"text": job.text[t:], "t": len(job.text), "audio": base64.b64encode(chunk).decode(),
            "a": a + len(chunk), "done": job.done and a + len(chunk) >= len(job.audio), "error": job.error}


OUTCOMES = {"ok": "ok", "cancel": "abgebrochen", "replaced": "neue Frage", "send": "failed: Uhr nimmt nichts an",
            "poll": "failed: Abruf", "ask": "failed: Frage", "spark": "failed: Fehler vom Spark"}


def _ms(x):
    try:
        return max(0, min(600000, int(x)))
    except (TypeError, ValueError):
        return 0


def report_line(job: Job, body: dict):
    """One log line per answer on the watch: where the time went (watch, phone, Spark) and how it
    ended. Only numbers and fixed words, nothing the phone sends is written as text."""
    s = lambda ms: f"{ms / 1000:.1f} s" if ms else "–"
    sp = lambda t: f"{t - job.start:.1f} s" if t else "–"
    outcome = OUTCOMES.get(str(body.get("outcome")), "failed: unbekannt")
    return (f"watch: zeit Diktat {s(_ms(body.get('dictation_ms')))} · erster Text auf der Uhr "
            f"{s(_ms(body.get('text_ms')))} · erster Ton {s(_ms(body.get('audio_ms')))} · fertig {s(_ms(body.get('done_ms')))}"
            f" · Spark: Text {sp(job.first_text)}, Ton {sp(job.first_audio)} · Wiederholungen "
            f"{min(_ms(body.get('retries')), 9999)} · Stück {min(_ms(body.get('chunk')), 9999)} B · {outcome}")
