"""Own speakers: small ESP32-S3 boards (microphone, amplifier, maybe a small display) with the open
XiaoZhi firmware, talking to this Spark instead of a cloud.

Setting one up:
    Browser (Chrome/Edge, USB)  The page flashes the firmware and writes a small settings block (NVS)
                                with the Wi-Fi, the Spark address and a new device key. The Wi-Fi
                                password is put together in the browser and never reaches the Spark.
    Code                        A board that was flashed elsewhere asks the Spark at start and gets a
                                6-digit code; the profile types it in "Ich" → Lautsprecher.

Each speaker is a device key of its profile (profiles.add_device), so the profile's voice, memory,
Home Assistant (with code word) and the device's room apply. Off until the admin allows it
(chat.esp32) and the profile switches it on (esp_on).

Protocol (XiaoZhi, see github.com/78/xiaozhi-esp32):
    POST /api/esp32/ota/            at every start: which server, which firmware, the clock
    POST /api/esp32/ota/activate    while a code is shown: 202 until it was typed in, then 200
    GET  /api/esp32/fw/<v>/<file>   firmware for updates over Wi-Fi (and for the browser setup)
    WS   /api/esp32/ws              conversation: Opus 16 kHz from the board, Opus 24 kHz back

    STATE/esp32.json   {"clients": {client id: {"device", "uid", "variant", "fw", "auto", "update", ...}},
                        "checked": t, "error": ""}
    FW_DIR/<version>/  manifest.json and the files of each board variant (from the repo's release)
"""
import asyncio
import ctypes
import ctypes.util
import datetime
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import threading
import time
import wave
import zoneinfo

import httpx
import numpy as np

import profiles
import vault
from common import load_config

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FW_DIR = os.path.join(os.path.dirname(STATE.rstrip("/")), "firmware")
CODE_SECONDS = 600
MAX_PENDING = 30
FOLLOW_UP = 600            # earlier turns at the same speaker count this long
FETCH_EVERY = 24 * 3600
FRAME_IN = 960             # 60 ms at 16 kHz from the board
OUT_RATE, FRAME_OUT = 24000, 1440   # 60 ms at 24 kHz to the board
_lock = threading.Lock()
_pending = {}              # client id -> {"code", "t", "challenge", "variant", "fw", "mac", "paired"}
_fails = {}                # uid -> [times of wrong codes]
_history = {}              # device id -> (time, messages)
_live = {}                 # device id -> Session


def admin_on():
    return bool(load_config().get("chat", {}).get("esp32", False))


def profile_on(uid):
    return bool(profiles.settings(uid).get("esp_on"))


def _file():
    return os.path.join(STATE, "esp32.json")


def _state():
    try:
        with open(_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = _file() + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f)
    os.replace(tmp, _file())


def _update(fn):
    with _lock:
        d = _state()
        d.setdefault("clients", {})
        out = fn(d)
        _save(d)
        return out


def _devices():
    return {x["id"]: x for x in profiles._load()["devices"]}


def clients():
    """Known speakers whose device key still exists: {client id: entry}."""
    devs = _devices()
    return {k: v for k, v in _state().get("clients", {}).items() if v.get("device") in devs}


def by_device(did):
    return next(((k, v) for k, v in clients().items() if v.get("device") == did), (None, None))


# ---------------------------------------------------------------- firmware
def manifest():
    """The newest firmware on the Spark: {"version", "variants": {name: {"label", "parts", "app"}}} or None."""
    try:
        with open(os.path.join(FW_DIR, "current.json")) as f:
            v = json.load(f).get("version", "")
        with open(os.path.join(FW_DIR, v, "manifest.json")) as f:
            m = json.load(f)
        return m if m.get("version") == v else None
    except (OSError, ValueError, AttributeError):
        return None


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


def newer(new, old):
    a, b = version_tuple(new), version_tuple(old)
    return bool(a) and bool(b) and a > b


SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,120}")


async def fetch_firmware(c=None):
    """Takes the newest firmware release (tag fw-…) of the repo, checks every file's SHA-256 against its
    manifest and keeps it with the one before. Returns the version."""
    repo = load_config().get("chat", {}).get("esp32_repo") or "db9979/speech-on-dgx-spark"
    own = c is None
    c = c or httpx.AsyncClient(timeout=120, follow_redirects=True)
    try:
        api = os.environ.get("SPEECH_SPARK_GITHUB_API", "https://api.github.com")
        r = await c.get(f"{api}/repos/{repo}/releases", params={"per_page": 30})
        r.raise_for_status()
        rel = next((x for x in r.json() if str(x.get("tag_name", "")).startswith("fw-")
                    and not x.get("draft") and not x.get("prerelease")), None)
        if not rel:
            raise ValueError("Im Repo gibt es noch keine Firmware-Version (fw-…).")
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        if "manifest.json" not in assets:
            raise ValueError("Die Firmware-Version hat kein manifest.json.")
        m = (await c.get(assets["manifest.json"])).raise_for_status().json()
        ver = str(m.get("version", ""))
        if not version_tuple(ver) or not isinstance(m.get("variants"), dict):
            raise ValueError("manifest.json ist ungültig.")
        cur = manifest()
        if cur and cur["version"] == ver:
            return ver
        tmp = os.path.join(FW_DIR, ver + ".part")
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        for name, var in m["variants"].items():
            for p in var.get("parts", []) + [var.get("app", {})]:
                fn = str(p.get("file", ""))
                if not SAFE_NAME.fullmatch(fn) or fn not in assets:
                    raise ValueError(f"{name}: Datei {fn!r} fehlt in der Version.")
                dst = os.path.join(tmp, fn)
                if os.path.exists(dst):
                    continue
                data = (await c.get(assets[fn])).raise_for_status().content
                if hashlib.sha256(data).hexdigest() != p.get("sha256"):
                    raise ValueError(f"{fn}: Prüfsumme passt nicht, nichts übernommen.")
                with open(dst, "wb") as f:
                    f.write(data)
        with open(os.path.join(tmp, "manifest.json"), "w") as f:
            json.dump(m, f)
        final = os.path.join(FW_DIR, ver)
        shutil.rmtree(final, ignore_errors=True)
        os.replace(tmp, final)
        with open(os.path.join(FW_DIR, "current.json.tmp"), "w") as f:
            json.dump({"version": ver, "previous": cur["version"] if cur else ""}, f)
        os.replace(os.path.join(FW_DIR, "current.json.tmp"), os.path.join(FW_DIR, "current.json"))
        keep = {ver, cur["version"] if cur else ""}
        for x in os.listdir(FW_DIR):
            if os.path.isdir(os.path.join(FW_DIR, x)) and x not in keep:
                shutil.rmtree(os.path.join(FW_DIR, x), ignore_errors=True)
        print("esp32: firmware", ver, "taken", flush=True)
        return ver
    finally:
        if own:
            await c.aclose()


async def fetch_loop():
    while True:
        await asyncio.sleep(60)
        try:
            if admin_on() and time.time() - float(_state().get("checked") or 0) > FETCH_EVERY:
                err = ""
                try:
                    await fetch_firmware()
                except Exception as e:
                    err = str(e)[:200]
                    print("esp32: firmware check", type(e).__name__, err, flush=True)
                _update(lambda d: d.update(checked=time.time(), error=err))
        except Exception as e:
            print("esp32: loop", type(e).__name__, e, flush=True)


# ---------------------------------------------------------------- Opus (libopus, comes with ffmpeg)
class Opus:
    _lib = None

    @classmethod
    def lib(cls):
        if cls._lib is None:
            name = ctypes.util.find_library("opus") or "libopus.so.0"
            lib = ctypes.CDLL(name)
            lib.opus_decoder_create.restype = ctypes.c_void_p
            lib.opus_decoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
            lib.opus_decode.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32,
                                        ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_int]
            lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
            lib.opus_encoder_create.restype = ctypes.c_void_p
            lib.opus_encoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
            lib.opus_encode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.c_int,
                                        ctypes.c_char_p, ctypes.c_int32]
            lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
            cls._lib = lib
        return cls._lib


class Decoder:
    def __init__(self, rate=16000):
        err = ctypes.c_int()
        self.rate = rate
        self.h = Opus.lib().opus_decoder_create(rate, 1, ctypes.byref(err))
        if err.value:
            raise RuntimeError(f"opus decoder {err.value}")

    def decode(self, packet: bytes) -> bytes:
        n = self.rate * 120 // 1000
        buf = (ctypes.c_int16 * n)()
        got = Opus.lib().opus_decode(self.h, packet, len(packet), buf, n, 0)
        return bytes(buf)[:max(0, got) * 2]

    def __del__(self):
        if getattr(self, "h", None):
            Opus.lib().opus_decoder_destroy(self.h)


class Encoder:
    """16-bit PCM at 24 kHz in pieces of any length, 60 ms Opus frames out."""

    def __init__(self):
        err = ctypes.c_int()
        self.h = Opus.lib().opus_encoder_create(OUT_RATE, 1, 2048, ctypes.byref(err))   # 2048 = VOIP
        if err.value:
            raise RuntimeError(f"opus encoder {err.value}")
        self.rest = b""

    def _one(self, pcm):
        buf = (ctypes.c_int16 * FRAME_OUT).from_buffer_copy(pcm)
        out = ctypes.create_string_buffer(4000)
        n = Opus.lib().opus_encode(self.h, buf, FRAME_OUT, out, 4000)
        if n < 0:
            raise RuntimeError(f"opus encode {n}")
        return out.raw[:n]

    def feed(self, pcm: bytes, flush=False):
        pcm = self.rest + pcm
        size = FRAME_OUT * 2
        if flush and len(pcm) % size:
            pcm += b"\0" * (size - len(pcm) % size)
        frames = [self._one(pcm[i:i + size]) for i in range(0, len(pcm) - size + 1, size)]
        self.rest = pcm[len(frames) * size:]
        return frames

    def __del__(self):
        if getattr(self, "h", None):
            Opus.lib().opus_encoder_destroy(self.h)


# ---------------------------------------------------------------- end of a question (simple level check)
class Ear:
    """Collects 16 kHz PCM; done when someone spoke and then was quiet for QUIET seconds."""
    QUIET, MIN_SPEECH, MAX_LEN, NOTHING = 0.7, 0.25, 30.0, 12.0

    def __init__(self):
        self.pcm = bytearray()
        self.noise = None
        self.speech = 0.0
        self.silence = 0.0
        self.heard = False
        self.started = time.time()

    def feed(self, pcm: bytes):
        """Returns "done", "nothing" (long quiet, nobody spoke) or None."""
        self.pcm += pcm
        x = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2").astype(np.float32)
        if not len(x):
            return None
        sec = len(x) / 16000
        rms = float(np.sqrt(np.mean(x * x)))
        loud = rms > max(500.0, (self.noise or rms) * 3)
        if not loud:   # background level: follows quiet frames, rises only slowly
            self.noise = rms if self.noise is None else min(self.noise * 1.02 + 1, max(rms, 1.0))
        if loud:
            self.speech += sec
            self.silence = 0.0
            if self.speech >= self.MIN_SPEECH:
                self.heard = True
        else:
            self.silence += sec
            if not self.heard:
                self.speech = 0.0
        if self.heard and (self.silence >= self.QUIET or len(self.pcm) / 32000 >= self.MAX_LEN):
            return "done"
        if not self.heard and time.time() - self.started > self.NOTHING:
            return "nothing"
        return None


def wav16k(pcm: bytes) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return b.getvalue()


async def transcribe(pcm: bytes) -> str:
    from core import api_headers
    cfg = load_config()
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions",
                         files={"file": ("speaker.wav", wav16k(pcm))}, data={"language": "auto", "response_format": "json"},
                         headers=api_headers())
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()


SENTENCE_END = re.compile(r"[.!?…:;]\s|\n")


def zone_offset(uid):
    tz = profiles.settings(uid).get("tz") or "Europe/Berlin"
    try:
        z = zoneinfo.ZoneInfo(tz)
    except Exception:
        z = zoneinfo.ZoneInfo("Europe/Berlin")
    return int(datetime.datetime.now(z).utcoffset().total_seconds() // 60), z


# ---------------------------------------------------------------- one connection of a speaker
class Session:
    def __init__(self, ws, token, dev, client):
        self.ws, self.token, self.dev, self.client = ws, token, dev, client
        self.sid = secrets.token_hex(8)
        self.dec = None
        self.ear = None
        self.mode = "auto"
        self.answer = None       # running answer task
        self.send_lock = asyncio.Lock()

    async def send(self, obj):
        async with self.send_lock:
            await self.ws.send_text(json.dumps(dict(obj, session_id=self.sid), ensure_ascii=False))

    async def send_audio(self, frame):
        async with self.send_lock:
            await self.ws.send_bytes(frame)

    def listen(self, mode):
        self.mode = mode if mode in ("auto", "manual", "realtime") else "auto"
        self.ear = Ear()
        self.dec = self.dec or Decoder(16000)

    async def on_text(self, m):
        kind = m.get("type")
        if kind == "hello":
            await self.ws.send_text(json.dumps({"type": "hello", "transport": "websocket", "session_id": self.sid,
                                                "audio_params": {"format": "opus", "sample_rate": OUT_RATE,
                                                                 "channels": 1, "frame_duration": 60}}))
        elif kind == "listen":
            st = m.get("state")
            if st == "start":
                if self.answer and not self.answer.done():
                    self.answer.cancel()
                self.listen(m.get("mode", "auto"))
            elif st == "stop" and self.ear:
                ear, self.ear = self.ear, None
                if ear.heard or len(ear.pcm) > 16000:
                    self.start_answer(bytes(ear.pcm))
            elif st == "detect":
                print("esp32: wake word at", self.dev["name"], flush=True)
        elif kind == "abort":
            if self.answer and not self.answer.done():
                self.answer.cancel()
        # mcp, iot and the rest: not used yet

    async def on_audio(self, packet):
        if not self.ear or (self.answer and not self.answer.done()):
            return
        pcm = self.dec.decode(packet)
        if self.mode == "manual":
            self.ear.pcm += pcm
            return
        r = self.ear.feed(pcm)
        if r == "done":
            ear, self.ear = self.ear, None
            self.start_answer(bytes(ear.pcm))
        elif r == "nothing":
            self.ear = None
            await self.ws.close(1000)   # nobody spoke: the board goes back to waiting for its wake word

    def start_answer(self, pcm):
        self.answer = asyncio.create_task(self.run_answer(pcm))

    async def run_answer(self, pcm):
        try:
            try:
                text = await transcribe(pcm)
            except Exception as e:
                print("esp32: speech recognition", type(e).__name__, str(e)[:120], flush=True)
                text = ""
            if not text:
                await self.send({"type": "tts", "state": "start"})
                await self.send({"type": "tts", "state": "stop"})
                return
            await self.send({"type": "stt", "text": text})
            await self.send({"type": "llm", "emotion": "thinking", "text": "🤔"})
            await self.speak(text)
        except asyncio.CancelledError:
            try:
                await self.send({"type": "tts", "state": "stop"})
            except Exception:
                pass
            raise
        except Exception as e:
            print("esp32: answer", type(e).__name__, str(e)[:160], flush=True)

    async def speak(self, text):
        import chat
        from starlette.requests import Request
        uid, did = self.dev["user"], self.dev["id"]
        now = time.time()
        last = _history.get(did)
        history = last[1][-8:] if last and now - last[0] < FOLLOW_UP else []
        body = {"messages": history + [{"role": "user", "content": text}], "client": "speaker",
                "tz": profiles.settings(uid).get("tz", "")}
        data = json.dumps(body).encode()
        # the device key in the header: the profile's settings and this device's room apply
        scope = {"type": "http", "method": "POST", "path": "/api/chat", "query_string": b"",
                 "headers": [(profiles.DEVICE_HEADER.encode(), self.token.encode())],
                 "client": (self.ws.client.host if self.ws.client else "speaker", 0),
                 "server": ("127.0.0.1", 0), "scheme": "http"}

        async def receive():
            return {"type": "http.request", "body": data, "more_body": False}
        response = await chat.chat(Request(scope, receive))
        enc = Encoder()
        answer, said, from_mail = "", 0, False
        t0, sent = None, 0
        await self.send({"type": "tts", "state": "start"})

        async def out(frames):
            nonlocal t0, sent
            for fr in frames:
                if t0 is None:
                    t0 = time.monotonic()
                # a little ahead of real time, so the board's buffer never runs dry or overflows
                ahead = sent * 0.06 - (time.monotonic() - t0)
                if ahead > 0.36:
                    await asyncio.sleep(ahead - 0.36)
                await self.send_audio(fr)
                sent += 1
        try:
            async for chunk in response.body_iterator:
                for line in (chunk.decode() if isinstance(chunk, bytes) else chunk).split("\n"):
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:])
                    except ValueError:
                        continue
                    k = ev.get("type")
                    if k == "text":
                        answer += ev.get("delta", "")
                        while (m := SENTENCE_END.search(answer, said)):
                            piece = answer[said:m.end()].strip()
                            said = m.end()
                            if piece:
                                await self.send({"type": "tts", "state": "sentence_start", "text": piece})
                    elif k in ("truncated", "retract"):
                        answer = answer[:max(0, len(answer) - int(ev.get("drop") or 0))]
                        said = min(said, len(answer))
                    elif k == "mail":
                        from_mail = True
                    elif k == "audio":
                        import base64
                        await out(await asyncio.to_thread(enc.feed, base64.b64decode(ev["audio"])))
            if answer[said:].strip():
                await self.send({"type": "tts", "state": "sentence_start", "text": answer[said:].strip()})
            await out(enc.feed(b"", flush=True))
            if t0 is not None:   # until the board has played it
                await asyncio.sleep(max(0.0, sent * 0.06 - (time.monotonic() - t0)))
        finally:
            if hasattr(response.body_iterator, "aclose"):
                await response.body_iterator.aclose()   # stops LLM and TTS when cancelled
        await self.send({"type": "tts", "state": "stop"})
        answer = answer.strip()
        if answer:
            remember(self.dev, history, text, answer, from_mail)


def remember(dev, history, text, answer, from_mail):
    """Keeps the turn for follow-ups and as the day's conversation "<speaker> dd.mm." of the profile
    (the code word blacked out, like everywhere)."""
    import chat
    import homeassistant
    uid = dev["user"]
    ha = homeassistant.get(uid)
    if ha and homeassistant.needs_code(ha):
        text = homeassistant.redact(ha, text)
    msgs = history + [{"role": "user", "content": text},
                      dict({"role": "assistant", "content": answer}, **({"mail": True} if from_mail else {}))]
    _history[dev["id"]] = (time.time(), msgs)
    local = datetime.datetime.now(chat.user_zone(profiles.settings(uid).get("tz", "")))
    cid = f"esp-{dev['id']}-{local:%Y%m%d}"
    try:
        old = next((c for c in profiles.convos(uid) if c.get("id") == cid), None)
        profiles.save_convo(uid, {"id": cid, "title": f"{dev['name']} {local:%d.%m.}", "updated": int(time.time() * 1000),
                                  "msgs": (old["msgs"] if old else []) + msgs[-2:]})
    except Exception as e:
        print("esp32: convo", type(e).__name__, e, flush=True)


def device_for_token(token):
    if not token:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    return next((x for x in profiles._load()["devices"] if secrets.compare_digest(x["token"], h)), None)


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

from account import browser_profile  # noqa: E402
from core import admin_code, assistant, auth, confirm_code, own_profile  # noqa: E402

router = APIRouter()


def _base(request):
    """The address the speakers use for this Spark: the admin's setting, else the one asked for."""
    url = (load_config().get("chat", {}).get("esp32_url") or "").rstrip("/")
    if url:
        return url
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def ws_url(base):
    return re.sub(r"^http", "ws", base) + "/api/esp32/ws"


def _client_info(request, body):
    app = body.get("application") if isinstance(body.get("application"), dict) else {}
    board = body.get("board") if isinstance(body.get("board"), dict) else {}
    return {"client": request.headers.get("client-id", "")[:64], "mac": request.headers.get("device-id", "")[:32],
            "fw": str(app.get("version", ""))[:32], "variant": str(board.get("name") or board.get("type") or "")[:64]}


@router.api_route("/api/esp32/ota/", methods=["GET", "POST"])
@router.api_route("/api/esp32/ota", methods=["GET", "POST"], include_in_schema=False)
async def ota(request: Request):
    if not admin_on():
        return JSONResponse({"error": "speakers are turned off on this Spark"}, status_code=403)
    try:
        body = await request.json() if request.method == "POST" else {}
    except ValueError:
        body = {}
    info = _client_info(request, body if isinstance(body, dict) else {})
    cid = info["client"]
    if not re.fullmatch(r"[0-9a-fA-F\-]{8,64}", cid):
        raise HTTPException(400, "Client-Id missing")
    base = _base(request)
    known = clients().get(cid)
    if not known:
        return _activation(cid, info)
    dev = _devices()[known["device"]]
    off, _ = zone_offset(dev["user"])
    resp = {"server_time": {"timestamp": int(time.time() * 1000), "timezone_offset": off},
            "websocket": {"url": ws_url(base), "version": 1}}
    once = known.get("token_once")
    m = manifest()
    var = known.get("variant") or info["variant"]
    fw = (m or {}).get("variants", {}).get(var)
    offer = bool(fw and newer(m["version"], info["fw"]) and (known.get("auto", True) or known.get("update")))
    if offer:
        resp["firmware"] = {"version": m["version"], "url": f"{base}/api/esp32/fw/{m['version']}/{fw['app']['file']}"}
    else:
        resp["firmware"] = {"version": info["fw"] or "0", "url": ""}

    def note(d):
        e = d["clients"][cid]
        e.update(fw=info["fw"] or e.get("fw", ""), mac=info["mac"] or e.get("mac", ""), seen=int(time.time()),
                 ip=request.client.host if request.client else "", variant=e.get("variant") or info["variant"])
        if offer:
            e["update"] = False
        e.pop("token_once", None)
    if once:
        tok = vault.open_(once)
        if tok:
            resp["websocket"]["token"] = tok   # only once, right after the code was typed in
    _update(note)
    return resp


def _activation(cid, info):
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v["t"] > CODE_SECONDS]:
            _pending.pop(k)
        p = _pending.get(cid)
        if not p:
            if len(_pending) >= MAX_PENDING:
                return JSONResponse({"error": "too many speakers waiting for a code"}, status_code=429)
            used = {v["code"] for v in _pending.values()}
            code = next(c for c in (f"{secrets.randbelow(10 ** 6):06d}" for _ in range(100)) if c not in used)
            p = _pending[cid] = dict(info, code=code, t=now, challenge=secrets.token_hex(16), paired=False)
    return {"activation": {"code": p["code"], "challenge": p["challenge"], "timeout_ms": CODE_SECONDS * 1000,
                           "message": f"Code {p['code']} am Spark unter Ich → Lautsprecher eingeben"},
            "server_time": {"timestamp": int(now * 1000)}}


@router.post("/api/esp32/ota/activate")
async def ota_activate(request: Request):
    if not admin_on():
        return JSONResponse({"error": "off"}, status_code=403)
    p = _pending.get(request.headers.get("client-id", ""))
    if p and p.get("paired"):
        _pending.pop(request.headers.get("client-id", ""), None)
        return {"ok": True}
    return JSONResponse({"waiting": True}, status_code=202)


@router.get("/api/esp32/fw/{version}/{name}")
def firmware_file(version: str, name: str):
    """Firmware files: the board fetches them without a key (it is the published open-source firmware)."""
    if not admin_on():
        raise HTTPException(403, "speakers are turned off")
    if not re.fullmatch(r"\d+(?:\.\d+){1,4}", version) or not SAFE_NAME.fullmatch(name) or name == "manifest.json":
        raise HTTPException(404, "not found")
    path = os.path.join(FW_DIR, version, name)
    if not os.path.isfile(path):
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "max-age=86400"})


@router.websocket("/api/esp32/ws")
async def speaker_ws(ws: WebSocket):
    token = ws.headers.get("authorization", "")
    token = token[7:].strip() if token.lower().startswith("bearer ") else token.strip()
    dev = device_for_token(token)
    if not dev or not admin_on() or not profile_on(dev["user"]):
        await ws.close(code=4403)
        print("esp32: connection refused (unknown key or switched off)", flush=True)
        return
    await ws.accept()
    cid = ws.headers.get("client-id", "")[:64]
    s = Session(ws, token, dev, cid)
    old = _live.get(dev["id"])
    _live[dev["id"]] = s
    if old:
        try:
            await old.ws.close(1000)
        except Exception:
            pass
    profiles._note_device(dev["id"], ws)
    print("esp32: connected", dev["name"], flush=True)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await s.on_audio(msg["bytes"])
            elif msg.get("text") is not None:
                try:
                    m = json.loads(msg["text"])
                except ValueError:
                    continue
                if isinstance(m, dict):
                    await s.on_text(m)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if s.answer and not s.answer.done():
            s.answer.cancel()
        if _live.get(dev["id"]) is s:
            _live.pop(dev["id"], None)


def _on(prof=Depends(browser_profile)):
    """Setting up and managing speakers: only from the profile's own browser login, never with a device key."""
    if not admin_on():
        raise HTTPException(403, "speakers are turned off")
    if not profile_on(prof["id"]):
        raise HTTPException(403, "switch speakers on for your profile first")
    return prof


def _list(uid=None):
    devs, last = _devices(), profiles.seen()
    m = manifest()
    out = []
    for cid, c in clients().items():
        d = devs[c["device"]]
        if uid and d["user"] != uid:
            continue
        out.append({"id": d["id"], "name": d["name"], "user": d["user"], "variant": c.get("variant", ""),
                    "fw": c.get("fw", ""), "auto": c.get("auto", True), "update": bool(c.get("update")),
                    "newer": bool(m and newer(m["version"], c.get("fw", ""))), "online": d["id"] in _live,
                    "seen": max(int(c.get("seen") or 0), int((last.get(d["id"]) or {}).get("t") or 0)) or None,
                    "created": d.get("created")})
    return sorted(out, key=lambda x: x["name"].lower())


def _fw_public():
    m = manifest()
    if not m:
        return None
    return {"version": m["version"], "built": m.get("built", ""),
            "variants": {k: {"label": v.get("label", k), "flash": v.get("flash", "16MB"), "parts": v.get("parts", [])}
                         for k, v in m["variants"].items()}}


@router.get("/api/profile/esp32", dependencies=[Depends(assistant)])
def profile_get(request: Request, prof=Depends(own_profile)):
    base = _base(request)
    return {"enabled": admin_on(), "on": profile_on(prof["id"]), "firmware": _fw_public(), "base": base,
            "fixed_base": bool(load_config().get("chat", {}).get("esp32_url")), "devices": _list(prof["id"])}


def _check_base(base):
    base = str(base or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Adresse für das Gerät: http(s)://name oder http(s)://name:port, ohne Pfad.")
    return base


def _name(x):
    name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(x or "")).strip()[:40]
    if not name:
        raise HTTPException(400, "Bitte einen Namen eingeben (z. B. Küche).")
    return name


@router.post("/api/profile/esp32/setup", dependencies=[Depends(assistant)])
async def profile_setup(request: Request, prof=Depends(_on)):
    """A new speaker set up from this browser: its device key, its client id and the addresses. The
    browser writes them with the Wi-Fi into the board's settings; the key is not kept here in clear."""
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
    body = await request.json()
    m = manifest()
    var = str(body.get("variant", ""))
    if not m or var not in m["variants"]:
        raise HTTPException(400, "Für dieses Board liegt keine Firmware auf dem Spark.")
    name = _name(body.get("name"))
    base = _check_base(load_config().get("chat", {}).get("esp32_url") or body.get("base"))
    token = profiles.add_device(name, prof["id"])
    did = device_for_token(token)["id"]
    import uuid as uuidlib
    cid = str(uuidlib.uuid4())

    def put(d):
        d["clients"][cid] = {"device": did, "uid": prof["id"], "variant": var, "fw": "", "auto": True,
                             "update": False, "created": int(time.time()), "how": "usb"}
    _update(put)
    print("esp32: new speaker set up over USB for", prof["name"], flush=True)
    return {"device": did, "token": token, "uuid": cid, "ota_url": base + "/api/esp32/ota/", "ws_url": ws_url(base),
            "firmware": m["version"],
            "parts": [dict(p, url=f"/api/esp32/fw/{m['version']}/{p['file']}") for p in m["variants"][var]["parts"]]}


@router.post("/api/profile/esp32/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(_on)):
    """The 6-digit code a board shows or says: binds it to this profile."""
    now = time.time()
    tries = [t for t in _fails.get(prof["id"], []) if now - t < CODE_SECONDS]
    if len(tries) >= 5:
        raise HTTPException(429, "Zu viele falsche Codes. Bitte in zehn Minuten noch einmal.")
    body = await request.json()
    code = re.sub(r"\D", "", str(body.get("code", "")))
    name = _name(body.get("name"))
    with _lock:
        cid, p = next(((k, v) for k, v in _pending.items() if v["code"] == code and not v["paired"]
                       and now - v["t"] < CODE_SECONDS), (None, None))
    if not p:
        _fails[prof["id"]] = tries + [now]
        await asyncio.sleep(1)
        raise HTTPException(400, "Der Code passt nicht oder ist abgelaufen. Das Gerät neu starten, dann kommt ein neuer.")
    await confirm_code(request, prof["id"], prof["name"])
    token = profiles.add_device(name, prof["id"])
    did = device_for_token(token)["id"]

    def put(d):
        d["clients"][cid] = {"device": did, "uid": prof["id"], "variant": p.get("variant", ""), "fw": p.get("fw", ""),
                             "mac": p.get("mac", ""), "auto": True, "update": False, "created": int(now), "how": "code",
                             "token_once": vault.seal(token)}
    _update(put)
    p["paired"] = True
    print("esp32: speaker paired by code for", prof["name"], flush=True)
    return {"device": did, "devices": _list(prof["id"])}


def _mine(did, prof):
    cid, c = by_device(did)
    if not c or (_devices()[did]["user"] != prof["id"]):
        raise HTTPException(404, "no such speaker")
    return cid


@router.put("/api/profile/esp32/{did}", dependencies=[Depends(assistant)])
async def profile_change(did: str, request: Request, prof=Depends(browser_profile)):
    cid = _mine(did, prof)
    body = await request.json()
    if "name" in body:
        name = _name(body["name"])
        with profiles._lock:
            d = profiles._load()
            for x in d["devices"]:
                if x["id"] == did:
                    x["name"] = name
            profiles._write(profiles._path("profiles.json"), d)
    if isinstance(body.get("auto"), bool):
        _update(lambda d: d["clients"][cid].update(auto=body["auto"]))
    return {"devices": _list(prof["id"])}


@router.post("/api/profile/esp32/{did}/update", dependencies=[Depends(assistant)])
async def profile_update_now(did: str, prof=Depends(_on)):
    """Update on the next start; a speaker that is connected right now restarts at once."""
    cid = _mine(did, prof)
    _update(lambda d: d["clients"][cid].update(update=True))
    s = _live.get(did)
    restarted = False
    if s:
        try:
            await s.send({"type": "system", "command": "reboot"})
            restarted = True
        except Exception:
            pass
    return {"restarted": restarted, "devices": _list(prof["id"])}


@router.delete("/api/profile/esp32/{did}", dependencies=[Depends(assistant)])
async def profile_delete(did: str, prof=Depends(browser_profile)):
    cid = _mine(did, prof)
    profiles.delete_device(did)
    _update(lambda d: d["clients"].pop(cid, None))
    s = _live.pop(did, None)
    if s:
        try:
            await s.ws.close(1000)
        except Exception:
            pass
    return {"devices": _list(prof["id"])}


@router.get("/api/admin/esp32", dependencies=[Depends(auth)])
def admin_get(request: Request):
    st = _state()
    return {"firmware": _fw_public(), "checked": st.get("checked"), "error": st.get("error", ""),
            "base": _base(request), "speakers": len(clients()), "online": len(_live),
            "repo": load_config().get("chat", {}).get("esp32_repo") or "db9979/speech-on-dgx-spark"}


@router.post("/api/admin/esp32/fetch", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_fetch(request: Request):
    err = ""
    try:
        await fetch_firmware()
    except Exception as e:
        err = str(e)[:200] or type(e).__name__
    _update(lambda d: d.update(checked=time.time(), error=err))
    if err:
        raise HTTPException(400, "Firmware nicht geholt: " + err)
    return admin_get(request)
