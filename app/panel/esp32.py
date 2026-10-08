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

Room mode (room.py, when the admin allows it with chat.room): "Raummodus an" after the wake word, or
the switch "Raum" in "Ich" → Lautsprecher (applies at once when the speaker is connected, else at its
next wake word). The Spark then keeps the connection and the board listening: every sentence goes
through the speech recognition to room.heard(), a pause to room.pause(), what it says comes with the
soft tone first. Nothing heard is written anywhere. It ends after its minutes (15 to 240, default 30),
with "Raummodus aus", the switch, when the connection ends, or when the admin or the profile switches
room mode or speakers off; then the board goes back to its wake word. In the profile's quiet hours it
stays silent (a speaker has no text). At most ROOM_MAX speakers are in room mode at once, because the
speech recognition runs all the time.

Protocol (XiaoZhi, see github.com/78/xiaozhi-esp32):
    POST /api/esp32/ota/            at every start: which server, which firmware, the clock
    POST /api/esp32/ota/activate    while a code is shown: 202 until it was typed in, then 200
    GET  /api/esp32/fw/<v>/<file>   firmware for updates over Wi-Fi (and for the browser setup)
    WS   /api/esp32/ws              conversation: Opus 16 kHz from the board, Opus 24 kHz back

    STATE/esp32.json   {"clients": {client id: {"device", "uid", "variant", "fw", "auto", "update", ...}},
                        "checked": t, "error": ""}
    FW_DIR/<version>/  manifest.json and the files of each board variant (from the repo's release)

Diagnosis ("Ich" → Lautsprecher → Prüfen): what each speaker did lately (start check, connection,
refusals with their reason, wake word, microphone level, what was understood, what was sent back)
stays in memory only (DIAG_MAX lines per speaker, lost at a restart). "Netz prüfen" asks the board's
address from the Spark itself, like the board does (certificate checked, home network allowed as for
Home Assistant, only the fixed paths below, answer at most 4 KB, NET_CHECKS per profile in 10 min):
    GET /api/esp32/ping            {"spark": PROBE}: shows the address really leads to this Spark
    WS  /api/esp32/ws  x-spark-probe: 1   sends {"type": "probe", "spark": PROBE} and closes (shows the
                                   reverse proxy passes WebSockets)
"Test" plays a test sentence at the next wake word (at once when connected), then checks the microphone
with the next sentence and says what it understood.
"""
import asyncio
import base64
import collections
import ctypes
import ctypes.util
import datetime
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import ssl
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
PENDING_PER_IP = 3         # codes one address may hold at once (nobody blocks the pairing for everyone)
MAX_BODY = 16 * 1024       # what a board or the page sends: small JSON only
MAX_FILE = 16 * 1024 * 1024
MAX_LISTEN = 30            # seconds of sound per question, also with the button held
FOLLOW_UP = 600            # earlier turns at the same speaker count this long
FETCH_EVERY = 24 * 3600
FRAME_IN = 960             # 60 ms at 16 kHz from the board
OUT_RATE, FRAME_OUT = 24000, 1440   # 60 ms at 24 kHz to the board
_lock = threading.Lock()
_pending = {}              # client id -> {"code", "t", "challenge", "variant", "fw", "mac", "paired"}
_fails = {}                # uid -> [times of wrong codes]
_history = {}              # device id -> (time, messages)
_live = {}                 # device id -> Session
_diag = {}                 # device id -> deque of (time, text): what the speaker did lately (memory only)
_net_tries = {}            # uid -> [times of "Netz prüfen"]
DIAG_MAX = 40
NET_CHECKS = 6
PROBE = secrets.token_hex(8)   # shows that an address leads to this very Spark (not secret)
ROOM_MINS = (15, 30, 60, 120, 240)
ROOM_MAX = 2               # speakers in room mode at once (the speech recognition runs all the time)
ROOM_LEVELS = ("questions", "hints", "all")
MIC_LEVELS = {"low": 300.0, "normal": 150.0, "high": 70.0}   # "Mikrofon" per speaker: least level that counts as speech
# "Raummodus an", "Raum-Modus einschalten", "starte den Raummodus"
ROOM_START = re.compile(r"(?i)^\W*(?:(?:hey )?(?:spark|jarvis),? )?(?:(?:den )?raum[- ]?modus (?:an|ein|einschalten|anschalten|starten)|"
                        r"(?:starte|schalte?) (?:den )?raum[- ]?modus(?: an| ein)?)\b")


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


def diag(did, text):
    """One line of the speaker's diagnosis (in memory, newest last)."""
    if did:
        _diag.setdefault(did, collections.deque(maxlen=DIAG_MAX)).append((int(time.time()), str(text)[:200]))


def _take_test(did):
    """"Test" was pressed while the speaker slept: the test runs at its next wake word (within a day)."""
    cid, c = by_device(did)
    if not c or not c.get("test_next") or time.time() - c["test_next"] > 24 * 3600:
        return False
    _update(lambda d: d["clients"].get(cid, {}).pop("test_next", None))
    return True


def _take_room_next(did):
    """The switch "Raum" was turned on while the speaker slept: room mode starts at its next wake word
    (once, and only within a day)."""
    cid, c = by_device(did)
    if not c or not c.get("room_next") or time.time() - c["room_next"] > 24 * 3600:
        return False
    _update(lambda d: d["clients"].get(cid, {}).pop("room_next", None))
    import room
    return room.enabled()


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


def _allowed_download(url):
    """Firmware only from GitHub's own download addresses (or the test server set by the self-test)."""
    test = os.environ.get("SPEECH_SPARK_GITHUB_API")
    if test and url.startswith(test.rstrip("/") + "/"):
        return True
    return bool(re.fullmatch(r"https://github\.com/[\w.\-]+/[\w.\-]+/releases/download/[^\s?#]+", url))


async def _download(c, url, size):
    """A release file, streamed and cut off at its announced size (at most MAX_FILE)."""
    if not _allowed_download(url):
        raise ValueError("Download-Adresse ist nicht von GitHub.")
    limit = min(size or MAX_FILE, MAX_FILE)
    out = bytearray()
    async with c.stream("GET", url) as r:
        r.raise_for_status()
        async for chunk in r.aiter_bytes():
            out += chunk
            if len(out) > limit:
                raise ValueError("Datei ist größer als angekündigt, nichts übernommen.")
    return bytes(out)


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
        m = json.loads(await _download(c, assets["manifest.json"], MAX_BODY * 8))
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
                data = await _download(c, assets[fn], int(p.get("size") or 0))
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
    MIN_LEVEL = 150.0   # about -47 dB: boards with a codec chip and echo cancelling send quiet sound

    def __init__(self, level=None):
        self.level = level or self.MIN_LEVEL
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
        loud = rms > max(self.level, (self.noise or rms) * 3)
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


def louder(pcm: bytes) -> bytes:
    """Quiet recordings brought up to a normal level for the speech recognition (at most 20 times)."""
    x = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2").astype(np.float32)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak < 1 or peak > 16000:
        return pcm
    return np.clip(x * min(20.0, 23000.0 / peak), -32768, 32767).astype("<i2").tobytes()


async def transcribe(pcm: bytes) -> str:
    from core import api_headers
    pcm = louder(pcm)
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


async def tts_pcm(uid, text):
    """The text in the profile's voice as 16-bit PCM at 24 kHz (at most a minute)."""
    from core import api_headers
    cfg = load_config()
    st = profiles.settings(uid)
    body = {"input": text[:600], "response_format": "pcm"}
    if st.get("voice"):
        body["voice"] = st["voice"]
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", json=body, headers=api_headers())
    r.raise_for_status()
    return r.content[:60 * OUT_RATE * 2]


def tone_pcm():
    """The soft two-note tone the browser plays before room mode speaks by itself (0.45 s at 24 kHz)."""
    t = np.arange(int(OUT_RATE * 0.45)) / OUT_RATE
    env = np.minimum(1.0, t / 0.04) * np.exp(-np.maximum(0.0, t - 0.04) * 9)
    x = np.sin(2 * np.pi * 523.25 * t) + np.where(t >= 0.14, np.sin(2 * np.pi * 659.25 * (t - 0.14)), 0)
    return (x * env * 2600).astype("<i2").tobytes()


def room_cfg(c):
    """The room settings of one speaker (kept with the speaker on the Spark, not in a browser)."""
    c = c or {}
    mins = c.get("room_mins") if c.get("room_mins") in ROOM_MINS else 30
    level = c.get("room_level") if c.get("room_level") in ROOM_LEVELS else "hints"
    area = re.sub(r"[\x00-\x1f<>\"\\]", "", str(c.get("room_area") or ""))[:60]
    return {"mins": mins, "level": level, "area": area}


# ---------------------------------------------------------------- one connection of a speaker
class Pacer:
    """Sends 60 ms frames to the board a little ahead of real time.

    The board holds at most 1.2 s of sound. We start only once ~0.6 s is ready, keep up to
    0.9 s in flight, and when the TTS fell behind and the board ran dry we wait for ~0.3 s
    again instead of trickling single frames (that is what sounds choppy)."""
    FRAME, LEAD, PRIME, REFILL = 0.06, 0.9, 0.6, 0.3

    def __init__(self, send):
        self.send, self.pending, self.sent, self.end, self.stalls, self.dry = send, [], 0, 0.0, 0, False

    async def push(self, frames, final=False):
        self.pending.extend(frames)
        while self.pending:
            now = time.monotonic()
            if self.end <= now and not final:
                need = self.PRIME if not self.sent else self.REFILL
                if len(self.pending) * self.FRAME < need:
                    if self.sent and not self.dry:
                        self.stalls += 1
                    self.dry = True
                    return
            ahead = self.end - now
            if ahead > self.LEAD:
                await asyncio.sleep(ahead - self.LEAD)
                now = time.monotonic()
            await self.send(self.pending.pop(0))
            self.sent += 1
            self.dry = False
            self.end = max(self.end, now) + self.FRAME

    async def finish(self):
        await self.push([], final=True)
        await asyncio.sleep(max(0.0, self.end - time.monotonic()))   # until the board has played it


class Session:
    def __init__(self, ws, token, dev, client):
        self.ws, self.token, self.dev, self.client = ws, token, dev, client
        self.sid = secrets.token_hex(8)
        self.dec = None
        self.ear = None
        self.mode = "auto"
        self.answer = None       # running answer task
        self.send_lock = asyncio.Lock()
        self.room_next = False   # room mode switched on in the panel: starts with the next "listen start"
        self.room = None         # room mode: {"rid", "until", "wait", "need", "last", "asking", "queue", "task"}
        self.mic = None          # this question's sound: [frames, seconds, peak, sum of squares, samples]
        self.testing = False     # "Test": the next sentence only checks the microphone

    def note(self, text):
        diag(self.dev["id"], text)

    def new_ear(self):
        c = clients().get(self.client) or by_device(self.dev["id"])[1] or {}
        return Ear(MIC_LEVELS.get(c.get("mic"), Ear.MIN_LEVEL))

    async def set_volume(self, volume):
        """The board's own loudspeaker volume (XiaoZhi MCP tool, kept on the board)."""
        await self.send_volume(self.ws, volume)

    @staticmethod
    async def send_volume(ws, volume):
        await ws.send_text(json.dumps({"type": "mcp", "payload": {
            "jsonrpc": "2.0", "id": secrets.randbelow(10 ** 6), "method": "tools/call",
            "params": {"name": "self.audio_speaker.set_volume", "arguments": {"volume": int(volume)}}}}))

    def mic_report(self, heard):
        """One diagnosis line about the sound the board sent for this question."""
        m, self.mic = self.mic, None
        if not m or self.room is not None:
            return
        if not m[0]:
            self.note("Mikrofon: kein Ton vom Board angekommen")
            return
        peak = 20 * np.log10(max(m[2], 1) / 32768)
        rms = 20 * np.log10(max(np.sqrt(m[3] / max(m[4], 1)), 1) / 32768)
        print(f"esp32: microphone at {self.dev['name']}: {m[1]:.1f} s, peak {peak:.0f} dB, mean {rms:.0f} dB, "
              + ("speech" if heard else "no speech"), flush=True)
        self.note(f"Mikrofon: {m[1]:.1f} s Ton, lautester Moment {peak:.0f} dB, Mittel {rms:.0f} dB, "
                  + ("Sprache gehört" if heard else "keine Sprache erkannt") + (" (zu leise oder nur Rauschen)" if peak < -40 else ""))

    async def send(self, obj):
        async with self.send_lock:
            await self.ws.send_text(json.dumps(dict(obj, session_id=self.sid), ensure_ascii=False))

    async def send_audio(self, frame):
        async with self.send_lock:
            await self.ws.send_bytes(frame)

    def listen(self, mode):
        self.mode = mode if mode in ("auto", "manual", "realtime") else "auto"
        self.ear = self.new_ear()
        self.mic = [0, 0.0, 0, 0.0, 0]
        self.dec = self.dec or Decoder(16000)

    async def run_test(self, mode="auto"):
        """"Test": a sentence and the tone (is the loudspeaker fine?), then the next sentence only checks
        the microphone."""
        self.note("Test: Testsatz gesendet")
        await self.say("Lautsprecher-Test. Wenn du mich hörst, geht der Ton. Sag jetzt einen Satz, dann prüfe ich das Mikrofon.", tone=True)
        self.testing = True
        self.listen(mode)

    async def on_text(self, m):
        kind = m.get("type")
        if kind == "hello":
            ap = m.get("audio_params") if isinstance(m.get("audio_params"), dict) else {}
            self.note(f"Begrüßung vom Board: Ton {str(ap.get('format', '?'))[:10]} {str(ap.get('sample_rate', '?'))[:6]} Hz")
            await self.ws.send_text(json.dumps({"type": "hello", "transport": "websocket", "session_id": self.sid,
                                                "audio_params": {"format": "opus", "sample_rate": OUT_RATE,
                                                                 "channels": 1, "frame_duration": 60}}))
            c = clients().get(self.client) or by_device(self.dev["id"])[1] or {}
            if isinstance(c.get("volume"), int):
                await self.set_volume(c["volume"])   # the volume set in the panel, at every connection
        elif kind == "listen":
            st = m.get("state")
            if st == "start":
                if self.answer and not self.answer.done():
                    self.answer.cancel()
                self.listen(m.get("mode", "auto"))
                self.note("Hört zu (" + self.mode + ")")
                if self.room is None and _take_test(self.dev["id"]):
                    self.answer = asyncio.create_task(self.run_test(self.mode))
                    return
                if self.room_next:
                    self.room_next = False
                    self.start_answer(None)
            elif st == "stop" and self.ear:
                ear, self.ear = self.ear, None
                self.mic_report(ear.heard)
                if ear.heard or len(ear.pcm) > 16000:
                    self.start_answer(bytes(ear.pcm))
            elif st == "detect":
                print("esp32: wake word at", self.dev["name"], flush=True)
                self.note("Weckwort erkannt" + (f": {str(m.get('text'))[:30]}" if m.get("text") else ""))
                if self.room is None and _take_room_next(self.dev["id"]):
                    self.room_next = True   # the switch in the panel: room mode starts at this wake word
        elif kind == "abort":
            if self.answer and not self.answer.done():
                self.answer.cancel()
        # mcp, iot and the rest: not used yet

    async def on_audio(self, packet):
        if not self.ear or (self.answer and not self.answer.done()):
            return
        pcm = self.dec.decode(packet)
        if self.mic is not None and pcm:
            x = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2").astype(np.float32)
            if len(x):
                self.mic[0] += 1
                self.mic[1] += len(x) / 16000
                self.mic[2] = max(self.mic[2], int(np.max(np.abs(x))))
                self.mic[3] += float(np.sum(x * x))
                self.mic[4] += len(x)
        if self.room is not None:
            r = self.ear.feed(pcm)
            if self.ear.heard:
                self.room["last"] = time.time()
            if r == "done":
                seg, self.ear = bytes(self.ear.pcm), self.new_ear()
                self.room["queue"] = asyncio.ensure_future(self._after(self.room["queue"], self.room_heard(seg)))
            elif r == "nothing":
                self.ear = self.new_ear()   # in room mode quiet is fine: keep listening
            return
        if self.mode == "manual":
            if len(self.ear.pcm) < MAX_LISTEN * 32000:
                self.ear.pcm += pcm
            return
        r = self.ear.feed(pcm)
        if r == "done":
            ear, self.ear = self.ear, None
            self.mic_report(True)
            self.start_answer(bytes(ear.pcm))
        elif r == "nothing":
            self.ear = None
            self.mic_report(False)
            if self.testing:
                self.testing = False
                self.note("Test: nichts gehört")
                self.answer = asyncio.create_task(self.say("Ich habe nichts gehört. Das Mikrofon ist vielleicht nicht richtig angeschlossen."))
                return
            await self.ws.close(1000)   # nobody spoke: the board goes back to waiting for its wake word

    def start_answer(self, pcm):
        self.answer = asyncio.create_task(self.run_answer(pcm))

    async def run_answer(self, pcm):
        try:
            if pcm is None:
                await self.room_start()
                return
            try:
                text = await transcribe(pcm)
            except Exception as e:
                print("esp32: speech recognition", type(e).__name__, str(e)[:120], flush=True)
                self.note("Spracherkennung fehlgeschlagen: " + type(e).__name__)
                text = ""
            self.note(f"Verstanden: „{text[:80]}“" if text else "Nichts verstanden")
            if self.testing:
                self.testing = False
                self.note("Test: Mikrofon " + ("geht" if text else "liefert keine verständlichen Wörter"))
                await self.say(f"Das Mikrofon geht. Verstanden habe ich: {text[:200]}" if text else
                               "Ich habe Ton bekommen, aber nichts verstanden. Bitte näher ran und deutlich sprechen.")
                return
            if not text:
                await self.send({"type": "tts", "state": "start"})
                await self.send({"type": "tts", "state": "stop"})
                return
            await self.send({"type": "stt", "text": text})
            if ROOM_START.match(text) and len(text) <= 60:
                await self.room_start()
                return
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
            self.note("Antwort fehlgeschlagen: " + type(e).__name__)

    # ------------------------------------------------------------ room mode
    @staticmethod
    async def _after(prev, coro):
        """Heard sentences are handled one after the other, in the order they were said."""
        if prev is not None:
            try:
                await prev
            except Exception:
                pass
        try:
            await coro
        except Exception as e:
            print("room: speaker sentence failed:", type(e).__name__, str(e)[:120], flush=True)

    def _room_body(self, **kw):
        c = room_cfg(clients().get(self.client) or by_device(self.dev["id"])[1])
        return dict({"room": self.room["rid"], "level": c["level"], "area": c["area"], "detect": False,
                     "tz": profiles.settings(self.dev["user"]).get("tz", "")}, **kw)

    async def room_start(self):
        import room
        uid = self.dev["user"]
        if self.room is not None:
            await self.say("Der Raum-Modus ist schon an.")
            return
        if not room.enabled():
            await self.say("Der Raum-Modus ist ausgeschaltet. Der Admin kann ihn unter Funktionen einschalten.")
            return
        if sum(1 for x in list(_live.values()) if x.room is not None) >= ROOM_MAX:
            print("room: speaker refused (already", ROOM_MAX, "speakers in room mode)", flush=True)
            await self.say("Gerade hören schon zu viele Lautsprecher im Raum zu. Bitte später noch einmal.")
            return
        mins = room_cfg(by_device(self.dev["id"])[1])["mins"]
        self.room = {"rid": "esp" + re.sub(r"[^A-Za-z0-9]", "", self.dev["id"])[:24], "until": time.time() + mins * 60,
                     "wait": False, "need": 2.5, "last": time.time(), "asking": False, "queue": None, "task": None}
        print(f"room: on at speaker {self.dev['name']} for {mins} min", flush=True)
        await self.say(f"Raum-Modus an. Ich höre {mins} Minuten zu. Mit „Raummodus aus“ beendest du ihn.")
        self.room["last"] = time.time()
        self.room["task"] = asyncio.create_task(self.room_loop())
        self.listen("auto")

    async def room_end(self, why, say=True):
        """Ends room mode: drops what was heard, says so and lets the board go back to its wake word."""
        import room
        r, self.room = self.room, None
        if r is None:
            return
        room.ROOMS.pop((self.dev["user"], r["rid"]), None)
        if r.get("task") and r["task"] is not asyncio.current_task():
            r["task"].cancel()
        print(f"room: off at speaker {self.dev['name']} ({why})", flush=True)
        try:
            if say and not room.night(self.dev["user"]):
                await self.say("Raum-Modus aus.")
            await self.ws.close(1000)
        except Exception:
            pass

    async def room_loop(self):
        import room
        try:
            while self.room is not None:
                await asyncio.sleep(0.3)
                r = self.room
                if r is None:
                    return
                uid = self.dev["user"]
                if not room.enabled() or not admin_on() or not profile_on(uid) or _devices().get(self.dev["id"]) is None:
                    await self.room_end("switched off", say=False)
                    return
                if time.time() > r["until"]:
                    await self.room_end("time is up")
                    return
                busy = (self.answer and not self.answer.done()) or (self.ear is not None and self.ear.heard)
                if not r["wait"] or r["asking"] or busy or time.time() - r["last"] < r["need"]:
                    continue
                r["wait"], r["asking"] = False, True
                try:
                    d = await room.pause(uid, r["rid"], self._room_body(quiet=time.time() - r["last"]))
                    self.note("Raum-Modus: Pause, " + ("spricht" if d.get("say") else "bleibt still"))
                    if d.get("again"):
                        r["need"], r["wait"] = d["again"], True
                    if d.get("say"):
                        self.room_say(d["say"])
                except Exception as e:
                    print("room: speaker pause failed:", type(e).__name__, str(e)[:120], flush=True)
                finally:
                    r["asking"] = False
        except asyncio.CancelledError:
            pass

    async def room_heard(self, pcm):
        import room
        import speakers
        if self.room is None:
            return
        uid, rid = self.dev["user"], self.room["rid"]
        rv = None
        if room.wants_voice(uid, rid):   # a yes counts only in the profile's voice, from this very recording
            th = speakers.STRICTNESS.get(load_config().get("chat", {}).get("speaker_strictness"), 0.75)
            rv = asyncio.create_task(asyncio.to_thread(speakers.identify, wav16k(pcm), th))
        try:
            text = await transcribe(pcm)
        except Exception as e:
            print("room: speaker speech recognition", type(e).__name__, flush=True)
            text = ""
        if rv is not None:
            try:
                room.set_voice(uid, rid, (await rv)[0] or "", text)
            except Exception:
                room.set_voice(uid, rid, "", text)
        if not text or self.room is None:
            return
        d = await room.heard(uid, rid, text, self._room_body())
        # what was heard in the room never goes into the diagnosis, only that something was
        self.note("Raum-Modus: Satz gehört" + (", wartet auf Pause" if d.get("wait") else ", nichts zu tun"))
        if self.room is None:
            return
        if d.get("end"):
            await self.room_end("by voice")
            return
        if d.get("stop") and self.answer and not self.answer.done():
            self.answer.cancel()
        if d.get("say"):
            self.room_say(d["say"])
        self.room["wait"], self.room["need"] = bool(d.get("wait")), 2.5

    def room_say(self, text):
        import room
        if room.night(self.dev["user"]):
            print("room: speaker silent (quiet hours)", flush=True)
            return
        if self.answer and not self.answer.done():
            return
        self.answer = asyncio.create_task(self.say(text, tone=True))

    async def say(self, text, tone=False):
        """Speaks a fixed text (no model): the tone first if asked, the text on boards with a display."""
        enc = Encoder()
        frames = enc.feed(tone_pcm()) if tone else []
        try:
            pcm = await tts_pcm(self.dev["user"], text)
        except Exception as e:
            print("esp32: tts", type(e).__name__, str(e)[:120], flush=True)
            self.note("Sprachausgabe fehlgeschlagen: " + type(e).__name__)
            pcm = b""
        frames += await asyncio.to_thread(enc.feed, pcm, True)
        await self.send({"type": "tts", "state": "start"})
        await self.send({"type": "tts", "state": "sentence_start", "text": text})
        try:
            pace = Pacer(self.send_audio)
            await pace.push(frames, final=True)
            await pace.finish()
            self.note(f"Gesprochen: {len(frames) * 0.06:.1f} s Ton gesendet")
        finally:
            try:
                await self.send({"type": "tts", "state": "stop"})
            except Exception:
                pass
        if self.room is not None:
            self.room["last"] = time.time()

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
        pace = Pacer(self.send_audio)
        await self.send({"type": "tts", "state": "start"})
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
                        await pace.push(await asyncio.to_thread(enc.feed, base64.b64decode(ev["audio"])))
            if answer[said:].strip():
                await self.send({"type": "tts", "state": "sentence_start", "text": answer[said:].strip()})
            await pace.push(enc.feed(b"", flush=True), final=True)
            await pace.finish()
        finally:
            if hasattr(response.body_iterator, "aclose"):
                await response.body_iterator.aclose()   # stops LLM and TTS when cancelled
        await self.send({"type": "tts", "state": "stop"})
        sent = pace.sent
        self.note(f"Antwort gesendet: {sent * 0.06:.1f} s Ton" if sent else "Antwort ohne Ton (Sprachausgabe lieferte nichts)")
        if pace.stalls:
            print(f"esp32: sound stalled {pace.stalls}x at {self.dev.get('name', '?')} (speech output slower than playback)", flush=True)
            self.note(f"Ton stockte {pace.stalls}-mal: die Sprachausgabe kam nicht schnell genug nach")
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


async def _body(request, limit=MAX_BODY):
    """JSON body of at most limit bytes, read before anything else; {} when empty or not JSON."""
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(413, "too large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise HTTPException(413, "too large")
    try:
        d = json.loads(bytes(data) or b"{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _client_info(request, body):
    app = body.get("application") if isinstance(body.get("application"), dict) else {}
    board = body.get("board") if isinstance(body.get("board"), dict) else {}
    return {"client": request.headers.get("client-id", "")[:64], "mac": request.headers.get("device-id", "")[:32],
            "fw": str(app.get("version", ""))[:32], "variant": str(board.get("name") or board.get("type") or "")[:64]}


@router.post("/api/esp32/ota/")
@router.post("/api/esp32/ota", include_in_schema=False)
async def ota(request: Request):
    """The board's check at every start (POST with its system info; a code can be handed out here,
    so never on GET)."""
    if not admin_on():
        print("esp32: start check refused (speakers are switched off in Funktionen)", flush=True)
        return JSONResponse({"error": "off"}, status_code=403)
    info = _client_info(request, await _body(request))
    cid = info["client"]
    if not re.fullmatch(r"[0-9a-fA-F\-]{8,64}", cid):
        print("esp32: start check without a board id refused", flush=True)
        raise HTTPException(400, "Client-Id missing")
    base = _base(request)
    known = clients().get(cid)
    if not known:
        import guard
        print(f"esp32: start check from an unknown board (firmware {info['fw'] or '?'}), it gets a pairing code", flush=True)
        return _activation(cid, info, guard.client_ip(request))
    dev = _devices()[known["device"]]
    off, _ = zone_offset(dev["user"])
    resp = {"server_time": {"timestamp": int(time.time() * 1000), "timezone_offset": off},
            "websocket": {"url": ws_url(base), "version": 1}}
    once = known.get("token_once")
    m = manifest()
    var = known.get("variant") or info["variant"]
    rep = info["variant"]
    if rep and rep != var and rep in (m or {}).get("variants", {}) and not var.startswith(rep):
        var = rep   # another board type was written over USB: updates follow what the board says it is
    fw = (m or {}).get("variants", {}).get(var)
    offer = bool(fw and newer(m["version"], info["fw"]) and (known.get("auto", True) or known.get("update")))
    if offer:
        resp["firmware"] = {"version": m["version"], "url": f"{base}/api/esp32/fw/{m['version']}/{fw['app']['file']}"}
    else:
        resp["firmware"] = {"version": info["fw"] or "0", "url": ""}

    def note(d):
        e = d["clients"][cid]
        e.update(fw=info["fw"] or e.get("fw", ""), mac=info["mac"] or e.get("mac", ""), seen=int(time.time()),
                 ip=request.client.host if request.client else "", variant=var)
        if offer:
            e["update"] = False
        e.pop("token_once", None)
    if once:
        tok = vault.open_(once)
        if tok:
            resp["websocket"]["token"] = tok   # only once, right after the code was typed in
    _update(note)
    print(f"esp32: start check from {dev['name']} (firmware {info['fw'] or '?'})" + (", update offered" if offer else ""), flush=True)
    diag(dev["id"], f"Start-Prüfung vom Board: Firmware {info['fw'] or '?'}, aus {request.client.host if request.client else '?'}"
         + (f", Update {m['version']} angeboten" if offer else "") + (", Schlüssel übergeben" if once else ""))
    return resp


def _activation(cid, info, ip):
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v["t"] > CODE_SECONDS]:
            _pending.pop(k)
        p = _pending.get(cid)
        if not p:
            if len(_pending) >= MAX_PENDING or sum(1 for v in _pending.values() if v.get("ip") == ip) >= PENDING_PER_IP:
                return JSONResponse({"error": "busy"}, status_code=429)
            used = {v["code"] for v in _pending.values()}
            code = next(c for c in (f"{secrets.randbelow(10 ** 6):06d}" for _ in range(100)) if c not in used)
            p = _pending[cid] = dict(info, code=code, t=now, challenge=secrets.token_hex(16), paired=False, ip=ip)
    return {"activation": {"code": p["code"], "challenge": p["challenge"], "timeout_ms": CODE_SECONDS * 1000,
                           "message": f"Code {p['code']} am Spark unter Ich → Lautsprecher eingeben"},
            "server_time": {"timestamp": int(now * 1000)}}


@router.post("/api/esp32/ota/activate")
async def ota_activate(request: Request):
    if not admin_on():
        return JSONResponse({"error": "off"}, status_code=403)
    await _body(request)
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
    if ws.headers.get("x-spark-probe") == "1" and admin_on():
        await ws.accept()   # "Netz prüfen": shows that WebSockets reach this Spark, nothing else
        await ws.send_text(json.dumps({"type": "probe", "spark": PROBE}))
        await ws.close(1000)
        return
    token = ws.headers.get("authorization", "")
    token = token[7:].strip() if token.lower().startswith("bearer ") else token.strip()
    dev = device_for_token(token)
    cid = ws.headers.get("client-id", "")[:64]
    why = ("speakers are switched off in Funktionen" if not admin_on() else "unknown device key" if not dev
           else "speakers are switched off in the profile" if not profile_on(dev["user"]) else "")
    if why:
        await ws.close(code=4403)
        known = clients().get(cid) if cid else None
        did = dev["id"] if dev else (known or {}).get("device")
        name = (_devices().get(did) or {}).get("name", "") if did else ""
        print(f"esp32: connection refused ({why})" + (f" from {name}" if name else ""), flush=True)
        diag(did, "Verbindung abgelehnt: " + {"unknown device key": "Schlüssel unbekannt (Lautsprecher neu einrichten)",
                                               "speakers are switched off in Funktionen": "Lautsprecher in Funktionen ausgeschaltet",
                                               "speakers are switched off in the profile": "„Eigene Lautsprecher für mich“ ist aus"}[why])
        return
    await ws.accept()
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
    diag(dev["id"], "Verbunden")
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
        if s.room is not None:
            import room
            r, s.room = s.room, None
            room.ROOMS.pop((dev["user"], r["rid"]), None)
            if r.get("task"):
                r["task"].cancel()
            print(f"room: off at speaker {dev['name']} (connection ended)", flush=True)
        if s.answer and not s.answer.done():
            s.answer.cancel()
        if _live.get(dev["id"]) is s:
            _live.pop(dev["id"], None)
        diag(dev["id"], "Verbindung beendet")


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
                    "created": d.get("created"), "volume": c.get("volume"), "mic": c.get("mic") or "normal",
                    **_room_info(d["id"], c)})
    return sorted(out, key=lambda x: x["name"].lower())


def _room_info(did, c):
    s = _live.get(did)
    r = s.room if s else None
    return {"room": bool(r) or bool(c.get("room_next")), "room_until": int(r["until"] * 1000) if r else None,
            "room_waits": bool(c.get("room_next")) and not r, **{"room_" + k: v for k, v in room_cfg(c).items()}}


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
            "fixed_base": bool(load_config().get("chat", {}).get("esp32_url")), "devices": _list(prof["id"]),
            "room": bool(load_config().get("chat", {}).get("room", False))}


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
    body = await _body(request)
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
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
                             "update": False, "created": int(time.time()), "how": "usb", "base": base}
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
    body = await _body(request)
    code = re.sub(r"\D", "", str(body.get("code", "")))[:6]
    name = _name(body.get("name"))
    with _lock:
        cid, p = next(((k, v) for k, v in _pending.items() if hmac.compare_digest(v["code"], code) and not v["paired"]
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
    body = await _body(request)
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
    if "mic" in body:
        if body["mic"] not in MIC_LEVELS:
            raise HTTPException(400, "Mikrofon: low, normal oder high.")
        _update(lambda d: d["clients"][cid].update(mic=body["mic"]))
    if "volume" in body:
        v = body["volume"]
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
            raise HTTPException(400, "Lautstärke: 0 bis 100.")
        _update(lambda d: d["clients"][cid].update(volume=v))
        s = _live.get(did)
        if s:
            try:
                await s.set_volume(v)   # connected: at once, else at its next connection
            except Exception:
                pass
    if any(k in body for k in ("room_mins", "room_level", "room_area")):
        def put(d):
            e = d["clients"][cid]
            if body.get("room_mins") in ROOM_MINS:
                e["room_mins"] = body["room_mins"]
            if body.get("room_level") in ROOM_LEVELS:
                e["room_level"] = body["room_level"]
            if "room_area" in body:
                e["room_area"] = room_cfg({"room_area": body["room_area"]})["area"]
        _update(put)
    if isinstance(body.get("room"), bool):
        await _room_switch(did, cid, prof, body["room"])
    return {"devices": _list(prof["id"])}


async def _room_switch(did, cid, prof, on):
    """The switch "Raum" of a speaker: starts or ends room mode now when it is connected, else at its
    next wake word."""
    import room
    if on and (not room.enabled() or not admin_on() or not profile_on(prof["id"])):
        raise HTTPException(403, "Der Raum-Modus ist ausgeschaltet (Einstellungen → Funktionen).")
    s = _live.get(did)
    if on:
        if s and s.room is None:
            if s.answer and not s.answer.done():
                s.answer.cancel()
            s.start_answer(None)
        elif not s:
            _update(lambda d: d["clients"][cid].update(room_next=int(time.time())))
    else:
        _update(lambda d: d["clients"][cid].pop("room_next", None))
        if s and s.room is not None:
            await s.room_end("switched off in the panel")


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


# ---------------------------------------------------------------- diagnosis
@router.get("/api/esp32/ping")
def ping():
    """"Netz prüfen" asks this through the speaker's address: does it lead to this very Spark?"""
    if not admin_on():
        return JSONResponse({"error": "off"}, status_code=403)
    return {"spark": PROBE}


def _addr_hint(base):
    """What is wrong with an address before anything is tried (None when nothing)."""
    if not base:
        return None
    host = re.sub(r"^https?://", "", base).split(":")[0].lower()
    if host.endswith(".invalid"):
        return "Im Board steht keine Spark-Adresse. Lautsprecher per USB neu einrichten."
    if host in ("localhost", "127.0.0.1", "::1") or host.startswith("127."):
        return "Die Adresse zeigt auf den Spark selbst (localhost). Das Board erreicht sie nie: die Adresse im Heimnetz oder die des Reverse Proxys nehmen."
    if base.startswith("https://") and (re.fullmatch(r"[\d.]+", host) or base.endswith(":31443")):
        return "https mit IP-Adresse oder Port 31443 hat ein selbst signiertes Zertifikat. Das Board lehnt es ab: http://<Spark-IP>:31080 im Heimnetz oder die Adresse des Reverse Proxys nehmen."
    return None


def _ws_frame_text(buf):
    """The text of the first WebSocket frame in buf (server frames are not masked), or None."""
    if len(buf) < 2 or buf[0] & 0x0F != 1:
        return None
    n, i = buf[1] & 0x7F, 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, i = int.from_bytes(buf[2:4], "big"), 4
    elif n == 127:
        return None
    return buf[i:i + n].decode("utf-8", "replace") if len(buf) >= i + n else None


async def _ws_probe(base):
    """Opens the speaker WebSocket like the board does (name resolved once, certificate checked) and
    waits for the probe answer. "" when fine, else why not."""
    import netguard
    from urllib.parse import urlsplit
    u = urlsplit(base)
    tls = u.scheme == "https"
    port = u.port or (443 if tls else 80)
    ip = await asyncio.to_thread(netguard.resolve, u.hostname, port, netguard.HOME)
    ctx = None
    if tls:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except Exception:
            pass
    r, w = await asyncio.wait_for(asyncio.open_connection(ip, port, ssl=ctx, server_hostname=u.hostname if tls else None), 6)
    try:
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        hostport = u.netloc.rsplit("@", 1)[-1]
        w.write((f"GET /api/esp32/ws HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                 f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nx-spark-probe: 1\r\n\r\n").encode())
        await w.drain()
        head = await asyncio.wait_for(r.readuntil(b"\r\n\r\n"), 6)
        status = head.split(b"\r\n", 1)[0].decode("latin-1")[:60]
        if " 101 " not in status + " ":
            return f"Der WebSocket wird nicht durchgereicht (Antwort „{status}“). Im Reverse Proxy WebSockets für /api/esp32/ws erlauben."
        buf = b""
        while len(buf) < 4096:
            chunk = await asyncio.wait_for(r.read(4096), 6)
            if not chunk:
                break
            buf += chunk
            txt = _ws_frame_text(buf)
            if txt is not None:
                try:
                    ok = json.loads(txt).get("spark") == PROBE
                except (ValueError, AttributeError):
                    ok = False
                return "" if ok else "Der WebSocket landet nicht bei diesem Spark."
        return "Der WebSocket öffnet sich, aber es kommt nichts an (Reverse Proxy?)."
    finally:
        w.close()


async def net_check(base):
    """The board's way to this Spark, tried from the Spark: [(ok, text)]."""
    import netguard
    out = []
    hint = _addr_hint(base)
    if hint:
        out.append((False, hint))
        if ".invalid" in base:
            return out
    try:
        async with netguard.client(netguard.HOME, max_bytes=4096, timeout=6, follow_redirects=False) as c:
            r = await c.get(base + "/api/esp32/ping")
        if r.status_code == 200 and (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("spark") == PROBE:
            out.append((True, f"{base} erreicht diesen Spark" + (" mit gültigem Zertifikat." if base.startswith("https") else ".")))
        elif r.status_code == 403:
            out.append((False, f"{base} antwortet, aber die Lautsprecher sind beim Admin ausgeschaltet."))
        elif 300 <= r.status_code < 400:
            out.append((False, f"{base} leitet weiter (Status {r.status_code}). Das Board folgt keiner Weiterleitung: die Zieladresse direkt eintragen."))
        elif r.status_code in (401, 404):
            out.append((False, f"{base} antwortet mit {r.status_code}: der Reverse Proxy reicht /api/esp32/ nicht ohne Anmeldung durch."))
        else:
            out.append((False, f"{base} antwortet mit Status {r.status_code}, aber das ist nicht dieser Spark."))
            return out
    except netguard.Blocked:
        out.append((False, "Diese Adresse prüft der Spark nicht (sie zeigt auf seine eigenen Dienste oder ist nicht erlaubt)."))
        return out
    except Exception as e:
        cause = e.__cause__ or e.__context__ or e
        txt = (type(e).__name__ + " " + str(e) + " " + str(cause)).lower()
        if "certificate" in txt or "ssl" in txt:
            out.append((False, f"Das Zertifikat von {base} wird nicht anerkannt. Das Board lehnt es genauso ab."))
        elif "name" in txt and ("not found" in txt or "resolve" in txt):
            out.append((False, f"Den Namen in {base} findet der Spark nicht. Das Board vermutlich auch nicht."))
        elif "timeout" in txt or "timed out" in txt:
            out.append((False, f"{base} antwortet nicht (Zeit abgelaufen). Port oder Firewall prüfen."))
        else:
            out.append((False, f"{base} ist nicht erreichbar ({type(e).__name__})."))
        return out
    if out[-1][0]:
        try:
            why = await _ws_probe(base)
        except Exception as e:
            why = f"Der WebSocket ließ sich nicht öffnen ({type(e).__name__})."
        out.append((not why, why or "Der WebSocket (Gespräch) kommt beim Spark an."))
    return out


def _diag_view(did, c, request):
    """The diagnosis of one speaker: fixed checks first, then what it did lately (newest first)."""
    uid = _devices()[did]["user"]
    m = manifest()
    var = c.get("variant", "")
    checks = [(admin_on(), "Lautsprecher in Funktionen eingeschaltet" if admin_on() else "Lautsprecher sind in Funktionen ausgeschaltet (Admin)"),
              (profile_on(uid), "„Eigene Lautsprecher für mich“ ist an" if profile_on(uid) else "„Eigene Lautsprecher für mich“ ist aus"),
              (bool(m and var in m.get("variants", {})), f"Firmware für „{var}“ liegt auf dem Spark" if m and var in m.get("variants", {}) else "Für diese Board-Variante liegt keine Firmware auf dem Spark")]
    if c.get("seen"):
        checks.append((True, "Das Board hat sich beim Spark gemeldet, zuletzt " + time.strftime("%d.%m. %H:%M", time.localtime(c["seen"]))))
    else:
        checks.append((False, "Das Board hat sich noch nie beim Spark gemeldet. Es erreicht ihn nicht: WLAN, Adresse oder Zertifikat. "
                              "„Netz prüfen“ und „Protokoll vom Board lesen (USB)“ zeigen, woran es liegt."))
    base = c.get("base") or ""
    hint = _addr_hint(base)
    if hint:
        checks.append((False, hint))
    return {"base": base or _base(request), "base_known": bool(base), "online": did in _live,
            "test": bool(c.get("test_next")), "checks": [{"ok": ok, "text": t} for ok, t in checks],
            "events": [{"t": t, "text": x} for t, x in reversed(list(_diag.get(did, ())))]}


@router.get("/api/profile/esp32/{did}/diag", dependencies=[Depends(assistant)])
def profile_diag(did: str, request: Request, prof=Depends(browser_profile)):
    cid = _mine(did, prof)
    return _diag_view(did, clients()[cid], request)


@router.post("/api/profile/esp32/{did}/check", dependencies=[Depends(assistant)])
async def profile_net_check(did: str, request: Request, prof=Depends(browser_profile)):
    """"Netz prüfen": the speaker's address tried from the Spark (fixed paths only, see net_check)."""
    cid = _mine(did, prof)
    await _body(request)
    now = time.time()
    tries = [t for t in _net_tries.get(prof["id"], []) if now - t < 600]
    if len(tries) >= NET_CHECKS:
        raise HTTPException(429, "Bitte ein paar Minuten warten, dann noch einmal prüfen.")
    _net_tries[prof["id"]] = tries + [now]
    c = clients()[cid]
    base = c.get("base") or _base(request)
    res = await net_check(_check_base(base))
    diag(did, "Netz geprüft: " + ("alles gut" if all(ok for ok, _ in res) else next(t for ok, t in res if not ok)))
    return {"results": [{"ok": ok, "text": t} for ok, t in res], **_diag_view(did, clients()[cid], request)}


@router.post("/api/profile/esp32/{did}/test", dependencies=[Depends(assistant)])
async def profile_test(did: str, request: Request, prof=Depends(_on)):
    """"Test": a test sentence and then a microphone check, at once when connected, else at the next
    wake word."""
    cid = _mine(did, prof)
    s = _live.get(did)
    if s and s.room is None and not (s.answer and not s.answer.done()):
        s.answer = asyncio.create_task(s.run_test())
        return {"now": True, **_diag_view(did, clients()[cid], request)}
    _update(lambda d: d["clients"][cid].update(test_next=int(time.time())))
    diag(did, "Test vorgemerkt: beim nächsten Weckwort oder Knopfdruck")
    return {"now": False, **_diag_view(did, clients()[cid], request)}


@router.delete("/api/profile/esp32/{did}", dependencies=[Depends(assistant)])
async def profile_delete(did: str, prof=Depends(browser_profile)):
    cid = _mine(did, prof)
    profiles.delete_device(did)
    _update(lambda d: d["clients"].pop(cid, None))
    _diag.pop(did, None)
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
