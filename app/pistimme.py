#!/usr/bin/env python3
"""Pi-Stimme (plan alzeo-mischbetrieb M4, Dominik 2026-11-18 „Piper als eigenes Programm“): when the panel runs on a
computer of its own and the model computer's speech output is gone (Notbetrieb) or given away by its Speicher-Wache
(Mischbetrieb), this computer speaks by itself with the Piper voice Thorsten (CC0, 22.05 kHz) on its CPU.

It runs as its own service speech-spark-nottts, only on 127.0.0.1:NOTTTS_PORT, with the API key like every speech
service, and only while the admin switch chat.notbetrieb_tts is on (panel/notbetrieb.py spricht): common.model_url
sends "tts" here then. The voice loads at the first sentence and gives its memory back after NOTTTS_IDLE seconds
without one. It speaks the same small part of the speech API the panel uses: POST /v1/audio/speech with "pcm" or
"wav" (16 bit, 24 kHz, mono, like Qwen3-TTS), "stream": true as speech.audio.delta events, one sentence at a time.
Voice, instructions and language of the request are ignored: there is one German voice.

Fixed rules: the runtime is sherpa-onnx from the panel's lock file (Apache-2.0, already there for Parakeet), the voice
is the package of the sherpa-onnx project, fetched once by install.sh (python3 pistimme.py laden) and checked against
its pinned SHA-256 before it is unpacked; only plain files and folders below its own folder are unpacked, nothing is
run from it. Logs start with "notbetrieb: pistimme" and hold fixed words and numbers only.
"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import threading
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import NOTTTS_IDLE, NOTTTS_PORT, STATE  # noqa: E402

URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
       "vits-piper-de_DE-thorsten-medium.tar.bz2")
SHA256 = "50487d9c95fdf2191f31d2588569381063ba1591dcd4c7d4bdd30f12b2191714"
PAKET = "vits-piper-de_DE-thorsten-medium"
MODELL = "de_DE-thorsten-medium.onnx"
NAME = "Piper Thorsten (medium, CPU)"
STIMME = "thorsten"
DIR = os.path.join(STATE, "pistimme")
MAX_BYTES = 100 * 1024**2      # the package is about 64 MiB
RATE_IN = 22050
RATE = 24000                   # what every caller of the speech output reads (Qwen3-TTS)
THREADS = 2                    # the panel keeps the other cores
MAX_INPUT = 3000               # characters per request
FORMATE = ("pcm", "wav")
SATZ = re.compile(r"(?<=[.!?…:;])\s+")


def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def da(d=DIR):
    """The pinned package is unpacked here (its hash noted beside it)."""
    try:
        with open(os.path.join(d, ".sha256")) as f:
            ok = f.read().strip() == SHA256
        return ok and os.path.isfile(os.path.join(d, PAKET, MODELL))
    except OSError:
        return False


def _sicher(tar, ziel):
    """Only plain files and folders below PAKET/, never a link, a device or a path out of it."""
    for m in tar.getmembers():
        name = m.name
        if not (name == PAKET or name.startswith(PAKET + "/")) or ".." in name.split("/") or name.startswith("/"):
            raise ValueError("pfad")
        if not (m.isfile() or m.isdir()):
            raise ValueError("art")
        p = os.path.realpath(os.path.join(ziel, name))
        if not p.startswith(os.path.realpath(ziel) + os.sep):
            raise ValueError("pfad")
        yield m


def entpacken(datei, d=DIR):
    """Checks the hash, unpacks into a new folder and puts it in place at once. Raises ValueError("hash") on a wrong file."""
    if _hash(datei) != SHA256:
        raise ValueError("hash")
    neu = d + ".neu"
    shutil.rmtree(neu, ignore_errors=True)
    os.makedirs(neu, mode=0o700)
    with tarfile.open(datei, "r:bz2") as t:
        for m in _sicher(t, neu):
            m.mode = 0o700 if m.isdir() else 0o600
            t.extract(m, neu, set_attrs=False)
    with open(os.path.join(neu, ".sha256"), "w") as f:
        f.write(SHA256 + "\n")
    alt = d + ".alt"
    shutil.rmtree(alt, ignore_errors=True)
    if os.path.isdir(d):
        os.rename(d, alt)
    os.rename(neu, d)
    shutil.rmtree(alt, ignore_errors=True)


def laden(d=DIR, url=URL):
    """install.sh: fetches the package once (nothing when it is there), at most MAX_BYTES."""
    if da(d):
        print("notbetrieb: pistimme da", flush=True)
        return 0
    import urllib.request
    os.makedirs(os.path.dirname(d), exist_ok=True)
    tmp = d + ".tar.bz2"
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:   # noqa: S310 - fixed https URL
            n = 0
            for b in iter(lambda: r.read(1 << 20), b""):
                n += len(b)
                if n > MAX_BYTES:
                    raise ValueError("gross")
                f.write(b)
        entpacken(tmp, d)
    except (OSError, ValueError, tarfile.TarError) as e:
        print("notbetrieb: pistimme laden fehler", type(e).__name__, flush=True)
        return 1
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("notbetrieb: pistimme laden ok", flush=True)
    return 0


def pcm16(samples, rate_in=RATE_IN, rate=RATE):
    """Float samples (-1..1) at rate_in to 16-bit PCM at rate (linear, enough for speech)."""
    import numpy as np
    x = np.asarray(samples, dtype=np.float32)
    if len(x) and rate_in != rate:
        n = int(round(len(x) * rate / rate_in))
        x = np.interp(np.arange(n) * (rate_in / rate), np.arange(len(x)), x).astype(np.float32)
    return (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def wav(pcm, rate=RATE):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return b.getvalue()


def text_fuer(text, lang="German"):
    """The same cleaning as the main speech output (textnorm): no Markdown signs, no secrets, numbers in words."""
    from textnorm import clean_text, hide_secrets, speak_abbreviations, speak_numbers, speech_markdown
    t = clean_text(hide_secrets(speech_markdown(str(text)), lang), calm=True)
    try:
        t = speak_numbers(speak_abbreviations(t, lang), lang, "words")
    except Exception:   # noqa: BLE001 - never fail a sentence over number formatting
        pass
    return t.strip()


def saetze(text):
    return [s for s in (x.strip() for x in SATZ.split(text)) if s]


class Stimme:
    """The voice: loaded at the first sentence, gone again after `idle` seconds without one (vergessen)."""

    def __init__(self, d=DIR, idle=NOTTTS_IDLE):
        self.d, self.idle = d, idle
        self.tts = None
        self.lock = threading.Lock()
        self.used = time.monotonic()

    def _laden(self):
        import sherpa_onnx
        p = os.path.join(self.d, PAKET)
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(model=os.path.join(p, MODELL), lexicon="",
                                                     data_dir=os.path.join(p, "espeak-ng-data"),
                                                     tokens=os.path.join(p, "tokens.txt"))
        cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, provider="cpu",
                                                                                     num_threads=THREADS),
                                           max_num_sentences=1)
        t0 = time.time()
        self.tts = sherpa_onnx.OfflineTts(cfg)
        print(f"notbetrieb: pistimme geladen {time.time() - t0:.1f} s", flush=True)

    def sprich(self, satz, speed=1.0):
        """One sentence as 16-bit PCM at RATE."""
        with self.lock:
            self.used = time.monotonic()
            if self.tts is None:
                if not da(self.d):
                    raise RuntimeError("fehlt")
                self._laden()
            a = self.tts.generate(satz, sid=0, speed=speed)
            self.used = time.monotonic()
            return pcm16(a.samples, a.sample_rate)

    def vergessen(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.tts is not None and now - self.used > self.idle:
                self.tts = None
                print("notbetrieb: pistimme entladen", flush=True)
                return True
        return False


def anfrage(body):
    """(text, format, stream, speed) of a request, or raises ValueError with a fixed word."""
    if not isinstance(body, dict) or not isinstance(body.get("input"), str) or not body["input"].strip():
        raise ValueError("input")
    if len(body["input"]) > MAX_INPUT:
        raise ValueError("lang")
    fmt = body.get("response_format") or "pcm"
    if fmt not in FORMATE:
        raise ValueError("format")
    stream = body.get("stream") is True or body.get("stream_format") in ("sse", "audio")
    speed = body.get("speed", 1.0)
    speed = float(speed) if isinstance(speed, (int, float)) and not isinstance(speed, bool) and 0.5 <= speed <= 2.0 \
        else 1.0
    return body["input"], fmt, stream, speed


def event(pcm):
    return ("event: speech.audio.delta\ndata: " + json.dumps({"type": "speech.audio.delta",
            "audio": base64.b64encode(pcm).decode(), "response_format": "pcm"}) + "\n\n").encode()


DONE = b"event: speech.audio.done\ndata: " + json.dumps({"type": "speech.audio.done"}).encode() + b"\n\n"


def app_bauen(stimme=None):
    import asyncio

    from fastapi import Depends, FastAPI, HTTPException, Request
    from fastapi.responses import Response, StreamingResponse

    from common import BodyLimit, api_key_dependency
    stimme = stimme or Stimme()
    app = FastAPI(title="Pi-Stimme (Piper Thorsten)")
    app.add_middleware(BodyLimit, limits=[], default=64 * 1024)
    auth = [Depends(api_key_dependency())]
    app.state.stimme = stimme
    n = {"saetze": 0}

    @app.get("/health")
    def health():
        return {"status": "ok" if da(stimme.d) else "error", "geladen": stimme.tts is not None, "model": NAME,
                "saetze": n["saetze"]}

    @app.get("/v1/voices", dependencies=auth)
    def voices():
        return {"model_kind": "pistimme", "voices": [STIMME], "languages": ["German"], "voicedesign": False,
                "eigene": []}

    @app.post("/v1/audio/speech", dependencies=auth)
    async def speech(request: Request):
        try:
            text, fmt, stream, speed = anfrage(await request.json())
        except ValueError as e:
            print("notbetrieb: pistimme abgelehnt", e.args[0] if e.args else "json", flush=True)
            raise HTTPException(400, f"pistimme: {e.args[0] if e.args else 'json'}")
        stuecke = saetze(await asyncio.to_thread(text_fuer, text))
        if not stuecke:
            raise HTTPException(400, "nothing left to speak after removing emojis and markup")
        if not da(stimme.d):
            print("notbetrieb: pistimme fehlt", flush=True)
            raise HTTPException(503, "TTS engine error: pistimme fehlt")
        if not stream:
            try:
                pcm = b"".join([await asyncio.to_thread(stimme.sprich, s, speed) for s in stuecke])
            except Exception as e:   # noqa: BLE001
                print("notbetrieb: pistimme fehler", type(e).__name__, flush=True)
                raise HTTPException(503, "TTS engine error: pistimme")
            n["saetze"] += len(stuecke)
            print(f"notbetrieb: pistimme gesprochen {len(stuecke)} saetze", flush=True)
            return Response(wav(pcm) if fmt == "wav" else pcm, media_type="audio/wav" if fmt == "wav" else "audio/pcm")

        async def strom():
            k = 0
            try:
                for s in stuecke:
                    yield event(await asyncio.to_thread(stimme.sprich, s, speed))
                    k += 1
                yield DONE
                print(f"notbetrieb: pistimme gesprochen {k} saetze", flush=True)
            except Exception as e:   # noqa: BLE001
                print("notbetrieb: pistimme fehler", type(e).__name__, k, flush=True)
                yield (b"event: speech.audio.error\ndata: " + json.dumps({"type": "speech.audio.error",
                       "error": "pistimme"}).encode() + b"\n\n")
            finally:
                n["saetze"] += k
        return StreamingResponse(strom(), media_type="text/event-stream")

    @app.on_event("startup")
    async def leerlauf():
        async def schauen():
            while True:
                await asyncio.sleep(30)
                stimme.vergessen()
        asyncio.get_running_loop().create_task(schauen())

    return app


def main(argv):
    if argv[:1] == ["laden"]:
        return laden()
    if argv[:1] == ["da"]:
        return 0 if da() else 1
    if argv:
        print("pistimme.py [laden|da]", file=sys.stderr)
        return 2
    import uvicorn
    uvicorn.run(app_bauen(), host="127.0.0.1", port=NOTTTS_PORT, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
