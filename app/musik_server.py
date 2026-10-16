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
requests is set here; the caller gives only caption, seconds, lyrics, language and seed. The MP3 is checked (size,
frame header) and gets our own ID3 tag that marks it as made by an AI. The service never logs a caption or lyrics:
only seconds, sizes and states.

    GET  /health        status (off | starting | ready | busy | error | missing), variant, counts, measurements
    POST /v1/musik      {caption, seconds, lyrics?, language?, seed?} -> {mp3, seconds, lm_s, synth_s, peak_gib, ...}
    POST /v1/musik/stop ends the engine now (Wartungspause, Musik testen)
"""
import asyncio
import base64
import email.parser
import email.policy
import struct
import time

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request

import musikmodell
from bedarf import OnDemand, idle_loop
from common import BodyLimit, api_key_dependency, api_key_ok, check_memory, load_config, mem_available_gib, quiet_access_log

MAX_BODY = 64 * 1024
MAX_CAPTION = 600
MAX_LYRICS = 4000
MIN_S, MAX_S = 10, 600        # what the model can (10 s to 10 min); the panel's own limit is smaller
MAX_MP3 = 40 * 1024**2        # what the engine hands back, before checking (10 min at 320 kbit/s is 24 MB)
START_S = 120                 # ace-server itself starts at once; the models load with the first request
JOB_S = 900                   # one song, both steps
POLL_S = 0.5
LANGS = ("de", "en", "fr", "es", "it", "nl", "pt", "pl", "sv", "da", "no", "fi", "tr", "ru", "uk", "ja", "zh", "ko")
INSTRUMENTAL = "[Instrumental]"
AI_TEXT = "KI-erzeugt mit ACE-Step 1.5 auf dem Spark / AI-generated with ACE-Step 1.5 on the Spark"

app = FastAPI(title="Musik machen (ACE-Step 1.5 via acestep.cpp)")
app.add_middleware(BodyLimit, default=MAX_BODY, gate=api_key_ok, gated=("/v1/",))
auth = [Depends(api_key_dependency())]
started = time.time()
stats = {"songs": 0, "failures": 0, "refused_memory": 0, "starts": 0, "last_s": None, "last_lm_s": None,
         "last_synth_s": None, "last_len_s": None, "peak_gib": None}


def cfg():
    return load_config("music")


class Engine(OnDemand):
    """ace-server as a child process: started on demand, ended after music.idle_min minutes without a song."""

    def __init__(self):
        super().__init__("musik")

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

    async def start(self):
        if self.alive() and self.state == "ready":
            return
        v = musikmodell.variant(cfg().get("variant"))
        if not musikmodell.installed(v):
            self.state = "error"
            raise HTTPException(503, "missing")
        try:
            check_memory(musikmodell.VARIANTS[v]["need_gib"])
        except MemoryError:
            stats["refused_memory"] += 1
            print(f"musik: engine nicht gestartet speicher {mem_available_gib():.1f} gib frei", flush=True)
            raise HTTPException(503, "memory")
        t0 = time.time()
        self.state = "starting"
        stats["starts"] += 1
        self.spawn(self.command(), musikmodell.FOLDER)
        while time.time() - t0 < START_S:
            if not self.alive():
                self.state = "error"
                print(f"musik: engine beendet beim start code {self.proc.returncode}", flush=True)
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

    async def job(self, step, body, t0, low):
        """One step of the engine (lm or synth): starts the job and waits for its result. Returns (response, lowest
        free memory seen)."""
        r = await self.client.post(f"{self.base}/{step}", json=body)
        if r.status_code != 200:
            raise HTTPException(502, "engine")
        job = str((r.json() or {}).get("id") or "")
        if not job.isdigit() or len(job) > 12:
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

    async def make(self, req):
        """One song: (MP3 bytes from the engine, seconds of both steps, GiB taken at the peak)."""
        async with self.lock:
            await self.start()
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


engine = Engine()


def audio_part(res):
    """The MP3 out of the engine's multipart/mixed answer (an audio part and a latent part per track): the first part
    whose bytes look like an MP3. ValueError when there is none."""
    ctype = res.headers.get("content-type", "")
    if not ctype.lower().startswith("multipart/"):
        raise ValueError("no multipart")
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + ctype.encode("latin-1", "replace") + b"\r\n\r\n" + res.content)
    for part in msg.iter_parts():
        raw = part.get_payload(decode=True) or b""
        if is_mp3(raw):
            return raw
    raise ValueError("no mp3")


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


def finish(raw, title):
    """The engine's MP3 -> our own: its ID3 tag (if any) dropped, ours in front (ID3v2.3: title, software, the AI
    mark as comment and TXXX). Raises ValueError for anything that is not an MP3 of a sane size."""
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

    frames = (_frame(b"TIT2", text(title[:120] or "Musik")) + _frame(b"TSSE", text("Speech on DGX Spark"))
              + _frame(b"COMM", utf16 + b"deu" + "".encode("utf-16") + b"\0\0" + AI_TEXT.encode("utf-16"))
              + _frame(b"TXXX", utf16 + "KI-erzeugt".encode("utf-16") + b"\0\0" + "ACE-Step 1.5".encode("utf-16")))
    return b"ID3\x03\x00\x00" + _syncsafe(len(frames)) + frames + raw


def request_body(b):
    """The checked request for the engine: every field fixed here except caption, length, lyrics, language, seed."""
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
    v = musikmodell.VARIANTS[musikmodell.variant(cfg().get("variant"))]
    return {"caption": caption, "lyrics": lyrics or INSTRUMENTAL, "vocal_language": lang if lyrics else "unknown",
            "duration": float(secs), "seed": seed, "lm_batch_size": 1, "synth_batch_size": 1,
            "inference_steps": musikmodell.STEPS, "task_type": "text2music", "output_format": "mp3",
            "mp3_bitrate": musikmodell.MP3_KBPS, "synth_model": v["dit"].stem, "lm_model": v["lm"].stem,
            "use_cot_caption": True, "lm_mode": "generate", "adapter": ""}


@app.post("/v1/musik", dependencies=auth)
async def musik(request: Request):
    try:
        b = await request.json()
        req = request_body(b)
    except ValueError:
        raise HTTPException(400, "JSON object")
    title = str(b.get("title") or "")[:120]
    try:
        raw, lm_s, synth_s, peak = await engine.make(req)
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
    print(f"musik: gemacht {int(req['duration'])} s {'gesang' if sung else 'instrumental'} "
          f"{lm_s + synth_s:.1f} s spitze {peak:.1f} gib", flush=True)
    return {"mp3": base64.b64encode(mp3).decode(), "seconds": round(lm_s + synth_s, 1), "lm_s": round(lm_s, 1),
            "synth_s": round(synth_s, 1), "peak_gib": round(peak, 1), "length_s": int(req["duration"]),
            "sung": sung, "seed": req["seed"], "bytes": len(mp3)}


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
            "missing": musikmodell.missing(v), "idle_min": int(c["idle_min"]), "uptime_s": round(time.time() - started),
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
