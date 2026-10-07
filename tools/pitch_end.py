#!/usr/bin/env python3
"""Measures the pitch at sentence ends of the TTS (read-only, only calls the local proxy on 31002).
For every voice: one sentence non-streamed (wav) and streamed (pcm SSE), saves the audio and prints
the F0 of the middle and of the last voiced 300 ms. A positive 'end-mid' means the voice goes up.
    ~/speech-debug$ python3 pitch_end.py [voice ...]
Without the API key of the proxy, measure straight at the engine (same audio, no text cleaning):
    ~/speech-debug$ TTS_URL=http://127.0.0.1:31012 python3 pitch_end.py
TTS_KEY=... sends a key to the proxy."""
import base64, io, json, os, sys, urllib.request, wave
import numpy as np

BASE = os.environ.get("TTS_URL", "http://127.0.0.1:31002").rstrip("/")
URL = BASE + "/v1/audio/speech"
HEAD = {"Content-Type": "application/json"}
if os.environ.get("TTS_KEY"):
    HEAD["Authorization"] = "Bearer " + os.environ["TTS_KEY"]
TEXT = "Morgen wird es in Berlin sonnig und warm. Am Abend kommen ein paar Wolken."
SR = 24000

def get(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(BASE + path, headers=HEAD), timeout=30))

MODEL = get("/v1/models")["data"][0]["id"]

def post(body):
    body = dict(body, model=MODEL, language="German")
    req = urllib.request.Request(URL, json.dumps(body).encode(), HEAD)
    return urllib.request.urlopen(req, timeout=120)

def nonstream(voice):
    with post({"input": TEXT, "voice": voice, "response_format": "wav"}) as r:
        w = wave.open(io.BytesIO(r.read()))
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768

def stream(voice):
    pcm = b""
    with post({"input": TEXT, "voice": voice, "stream": True, "response_format": "pcm"}) as r:
        for line in r:
            if line.startswith(b"data:"):
                try:
                    ev = json.loads(line[5:])
                except ValueError:
                    continue
                if ev.get("audio"):
                    pcm += base64.b64decode(ev["audio"])
    return np.frombuffer(pcm[: len(pcm) // 2 * 2], np.int16).astype(np.float32) / 32768

def f0_track(x, hop=0.01, win=0.04):
    out, n, h = [], int(win * SR), int(hop * SR)
    for i in range(0, len(x) - n, h):
        f = x[i:i + n] * np.hanning(n)
        if np.sqrt(np.mean(f ** 2)) < 0.01:
            out.append(np.nan); continue
        ac = np.correlate(f, f, "full")[n - 1:]
        lo, hi = SR // 400, SR // 70
        k = lo + int(np.argmax(ac[lo:hi]))
        out.append(SR / k if ac[k] > 0.3 * ac[0] else np.nan)
    return np.array(out)

def report(name, x):
    t = f0_track(x)
    v = np.where(~np.isnan(t))[0]
    if len(v) < 40:
        print(f"{name}: too little voiced audio"); return
    tail = t[v[-30:]]; mid = t[v[len(v) // 3: 2 * len(v) // 3]]
    trail = len(x) / SR - (v[-1] * 0.01 + 0.04)
    print(f"{name:28s} len {len(x)/SR:5.2f}s  mid {np.nanmedian(mid):6.1f} Hz  end {np.nanmedian(tail):6.1f} Hz  "
          f"end-mid {np.nanmedian(tail)-np.nanmedian(mid):+6.1f} Hz  last10 {np.nanmedian(t[v[-10:]]):6.1f}  silence after {trail:.2f}s")
    with wave.open(f"pitch_{name}.wav", "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())

voices = sys.argv[1:]
if not voices:
    voices = get("/v1/audio/voices").get("voices", [])[:6]
print("model", MODEL, "at", BASE)
for v in voices:
    v = v if isinstance(v, str) else v.get("name")
    for kind, fn in (("wav", nonstream), ("stream", stream)):
        try:
            report(f"{v}-{kind}", fn(v))
        except Exception as e:
            print(v, kind, "failed:", e)
