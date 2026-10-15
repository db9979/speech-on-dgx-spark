"""Shared helpers for the ASR and TTS services: config, model state, request stats."""
import json
import os
import re
import threading
import time
import traceback
from collections import deque

CONFIG_PATH = os.environ.get("SPEECH_SPARK_CONFIG", "/etc/speech-spark/config.json")
# the state folder of this Spark (keys, shared state, marks): every module takes it from here (Richtlinie Teil 17);
# what lies in it is listed once in panel/dateien.py
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")


DEFAULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.default.json")
_shipped = {"mtime": None, "cfg": {}}


def _share_tls():
    """httpx builds a new TLS context for every client, loading the whole CA bundle each time: about 40 ms of
    CPU on the event loop per request to a sibling service, the LLM or the web (measured, review 11.10.2026).
    Every client of this process that verifies with the default CAs now shares one context; a client with its
    own verify (False for a self-signed Home Assistant, a file, a context) or a client certificate is unchanged.
    tests/test_pruefung.py checks it still holds with the pinned httpx (requirements-panel.lock)."""
    try:
        import httpx._transports.default as transport
    except ImportError:
        return
    make = transport.create_ssl_context
    if getattr(make, "shared", False):
        return
    cache = {}
    lock = threading.Lock()

    def create_ssl_context(verify=True, cert=None, trust_env=True):
        if verify is not True or cert is not None:
            return make(verify=verify, cert=cert, trust_env=trust_env)
        with lock:
            if trust_env not in cache:
                cache[trust_env] = make(verify=True, cert=None, trust_env=trust_env)
            return cache[trust_env]
    create_ssl_context.shared = True
    transport.create_ssl_context = create_ssl_context


_share_tls()


def _merge(base, over):
    """Like jq's `*` in install.sh: objects merged key by key, everything else taken from `over`."""
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def shipped():
    """config.default.json (re-read when it changes, e.g. after an update)."""
    try:
        m = os.stat(DEFAULTS_PATH).st_mtime
        if m != _shipped["mtime"]:
            with open(DEFAULTS_PATH) as f:
                _shipped["cfg"], _shipped["mtime"] = json.load(f), m
    except (OSError, ValueError):
        pass
    return _shipped["cfg"]


def no_think(text):
    """An answer without the model's thinking. Qwen with thinking on gets "<think>" in the prompt, so a
    server that does not hand the thinking over apart sends it as text up to a lone "</think>": all of that
    goes, as does every "<think>...</think>" block."""
    text = re.sub(r"(?s)<think>.*?</think>", "", str(text or ""))
    return text.rsplit("</think>", 1)[-1].replace("<think>", "").strip()


def load_config(section=None):
    """The configuration with the shipped default for every key that is missing (plan „Vereinheitlichen“,
    V01.0.268): one place for defaults instead of a `.get(key, default)` at every caller."""
    with open(CONFIG_PATH) as f:
        cfg = _merge(shipped(), json.load(f))
    return cfg[section] if section else cfg


def read_json(path, default=None):
    """The JSON in path, or a fresh copy of default when the file is missing, broken or of another kind than
    default (a dict where a list belongs). The one JSON reader next to write_json."""
    import copy
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return copy.deepcopy(default)
    return d if default is None or isinstance(d, type(default)) else copy.deepcopy(default)


def write_json(path, data, indent=None, mode=None, ensure_ascii=True, dir_mode=0o777):
    """Writes JSON atomically: a fresh temporary file next to it (never a fixed .tmp name two writers would share,
    never through a link), then rename. Keeps the file's mode, a new one gets 0600 (or mode); a missing folder is
    made with dir_mode. The one JSON writer (Richtlinie Teil 17, test_aufraeumen)."""
    import tempfile
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, mode=dir_mode, exist_ok=True)
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o600
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class DayCounter(dict):
    """Numbers of today (Live page, Zustand → Technik): a dict with "day" (local date) and the counts, back to a
    fresh copy of the given zeros on a new local day. The one helper for every "today: n" counter in memory."""

    def __init__(self, **zero):
        import copy
        super().__init__(day="", **copy.deepcopy(zero))
        self._zero = zero

    @staticmethod
    def date(now=None):
        return time.strftime("%Y-%m-%d", time.localtime(now))

    def today(self, now=None):
        """Itself, reset first when the local date changed (now: epoch seconds, None = the clock)."""
        day = self.date(now)
        if self.get("day") != day:
            import copy
            self.clear()
            self.update(copy.deepcopy(self._zero), day=day)
        return self

    def bump(self, key, n=1, now=None):
        t = self.today(now)
        t[key] = t.get(key, 0) + n
        return t[key]

    def counts(self, now=None):
        """Today's counts without "day", read only: the zeros when nothing was counted today yet."""
        import copy
        if self.get("day") != self.date(now):
            return copy.deepcopy(self._zero)
        return {k: copy.deepcopy(v) for k, v in self.items() if k != "day"}


# Speech first (panel vorrang.py): every STT/TTS request touches this file, the panel holds its
# background work (and cancels its background requests to the language model) while it is fresh.
SPEECH_MARK = os.path.join(STATE, "speech-active")
_speech_marked = [0.0]


def speech_mark(now=None, path=None, end=False):
    """Notes "speech is running right now" for the panel; at most once a second (always at the end of
    a request, the panel's pause counts from there), never fails a request."""
    now = time.time() if now is None else now
    if not end and now - _speech_marked[0] < 1:
        return
    _speech_marked[0] = now
    path = path or SPEECH_MARK
    try:
        os.utime(path, (now, now))
    except FileNotFoundError:
        try:
            with open(path, "a"):
                pass
            os.utime(path, (now, now))
        except OSError:
            pass
    except OSError:
        pass


class SpeechMark:
    """ASGI middleware: speech_mark() while a speech request (POST /v1/audio/...) runs, also on every
    piece of a streamed answer, and once more at its end."""

    def __init__(self, app, paths=("/v1/audio/",)):
        self.app, self.paths = app, tuple(paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not scope.get("path", "").startswith(self.paths):
            return await self.app(scope, receive, send)
        speech_mark()

        async def sending(msg):
            if msg.get("type") == "http.response.body":
                speech_mark()
            await send(msg)
        try:
            await self.app(scope, receive, sending)
        finally:
            speech_mark(end=True)


# Priority for people (panel stufe.py, plan plaene/vorrang-personen.md): the panel tells the ASR/TTS
# services how urgent a request is. Only the panel can: it sends the stage together with a key from
# STATE/vorrang-key (made by the panel, readable only by the service user) and only from this machine.
# Anybody else (Open WebUI, apps with the API key, other machines) is always "normal".
STAGE_LOW, STAGE_NORMAL, STAGE_HIGH = 0, 1, 2
STAGE_HEADER, STAGE_KEY_HEADER = "x-spark-stufe", "x-spark-vorrang"
_stage_key = [None]


def stage_key_path():
    return os.path.join(STATE, "vorrang-key")


def stage_key(create=False):
    """The shared secret ("" while there is none). The panel creates it once (create=True)."""
    if _stage_key[0]:
        return _stage_key[0]
    path = stage_key_path()
    try:
        with open(path) as f:
            key = f.read().strip()
    except OSError:
        key = ""
    if not key and create:
        import secrets
        key = secrets.token_hex(32)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(key)
            os.replace(path + ".tmp", path)
        except OSError:
            return ""
    if len(key) == 64:
        _stage_key[0] = key
        return key
    return ""


def stage_of(request):
    """The stage of a request to a speech service: what the panel says, else normal."""
    import hmac
    import ipaddress
    h = request.headers
    got = h.get(STAGE_HEADER, "")
    if got not in ("0", "2"):
        return STAGE_NORMAL
    try:
        local = ipaddress.ip_address(request.client.host if request.client else "").is_loopback
    except ValueError:
        local = False
    key = stage_key()
    if not local or not key or not hmac.compare_digest(h.get(STAGE_KEY_HEADER, "").encode(), key.encode()):
        return STAGE_NORMAL
    return int(got)


class GateFull(Exception):
    """Too many requests wait already."""


class PrioGate:
    """At most `slots` requests at once go on to an engine (as many as it takes, engine_max_seqs); the
    others wait here instead of in the engine's own first-come queue. Who waits goes by stage (2
    Vorrang, 1 normal, 0 hinten), then by arrival; a request never stops one that already runs. Every
    `age` seconds of waiting move a request one stage up, so nobody starves. A slot is given back at
    the end of the request, at the latest after `lease` seconds (a stream the client dropped before it
    began must not block the engine for good). One gate per engine and process (asyncio only)."""

    def __init__(self, slots, age=4.0, lease=90.0, most=64, clock=time.monotonic):
        self.slots, self.age, self.lease, self.most, self.clock = max(1, int(slots)), age, lease, most, clock
        self.running = {}       # ticket -> start
        self.waiting = []       # [stage, arrival, seq, future, ticket]
        self.seq = 0
        self.stats = {"waited": 0, "overtook": 0, "waited_max_ms": 0, "full": 0}

    def _busy(self):
        now = self.clock()
        for t, s in list(self.running.items()):
            if now - s > self.lease:
                del self.running[t]
        return len(self.running)

    def _rank(self, w, now):
        return (min(STAGE_HIGH, w[0] + int((now - w[1]) // self.age)) if self.age else w[0], -w[2])

    def _grant(self):
        while self.waiting and self._busy() < self.slots:
            now = self.clock()
            best = max(self.waiting, key=lambda w: self._rank(w, now))
            self.waiting.remove(best)
            if best[3].done():          # given up while waiting
                continue
            best[4]["overtook"] = sum(1 for w in self.waiting if w[2] < best[2])
            self.running[best[4]["id"]] = now
            best[3].set_result(True)

    async def enter(self, stage=STAGE_NORMAL):
        """Waits for a slot. Returns the ticket: {"id", "waited_ms", "overtook"}; pass it to leave()."""
        import asyncio
        self.seq += 1
        ticket = {"id": self.seq, "waited_ms": 0, "overtook": 0}
        if not self.waiting and self._busy() < self.slots:
            self.running[ticket["id"]] = self.clock()
            return ticket
        if len(self.waiting) >= self.most:
            self.stats["full"] += 1
            raise GateFull()
        t0 = self.clock()
        fut = asyncio.get_running_loop().create_future()
        self.waiting.append([stage if stage in (STAGE_LOW, STAGE_NORMAL, STAGE_HIGH) else STAGE_NORMAL, t0, self.seq, fut, ticket])
        self._grant()
        while not fut.done():   # a slot whose lease ran out frees itself: look again now and then
            try:
                await asyncio.wait({fut}, timeout=1.0)   # (never cancels fut itself)
                if not fut.done():
                    self._grant()
            except asyncio.CancelledError:
                if fut.done():
                    self.leave(ticket)
                else:
                    fut.cancel()
                    self.waiting = [w for w in self.waiting if w[3] is not fut]
                raise
        ticket["waited_ms"] = int((self.clock() - t0) * 1000)
        self.stats["waited"] += 1
        self.stats["overtook"] += ticket["overtook"]
        self.stats["waited_max_ms"] = max(self.stats["waited_max_ms"], ticket["waited_ms"])
        if ticket["overtook"]:
            print(f"vorrang: Stufe {stage} überholt {ticket['overtook']} wartende Anfrage(n), wartete "
                  f"{ticket['waited_ms'] / 1000:.1f} s", flush=True)
        return ticket

    def leave(self, ticket):
        """Gives the slot back (twice is harmless)."""
        if ticket and self.running.pop(ticket["id"], None) is not None:
            self._grant()

    def view(self):
        return dict(self.stats, running=self._busy(), waiting=len(self.waiting), slots=self.slots)

    @staticmethod
    def headers(ticket):
        """For the response: how long this request waited and how many it overtook (Logs → Anfragen)."""
        return {"X-Spark-Wait-Ms": str(ticket["waited_ms"]), "X-Spark-Overtook": str(ticket["overtook"])}


# Rough unified-memory footprint per model incl. CUDA context and activations (GiB).
# Estimates, not measurements; refine them on the box via the panel's numbers.
MODEL_GIB = {
    "Qwen3-ASR-1.7B": 6, "Qwen3-ASR-0.6B": 3, "Qwen3-ForcedAligner-0.6B": 2,
    "Qwen3-TTS-12Hz-1.7B": 7, "Qwen3-TTS-12Hz-0.6B": 4,
}


# Qwen3-ASR languages by ISO 639-1 code (OpenAI clients send codes, qwen-asr wants names).
ASR_ISO = {"zh": "Chinese", "en": "English", "yue": "Cantonese", "ar": "Arabic", "de": "German",
           "fr": "French", "es": "Spanish", "pt": "Portuguese", "id": "Indonesian", "it": "Italian",
           "ko": "Korean", "ru": "Russian", "th": "Thai", "vi": "Vietnamese", "ja": "Japanese",
           "tr": "Turkish", "hi": "Hindi", "ms": "Malay", "nl": "Dutch", "sv": "Swedish", "da": "Danish",
           "fi": "Finnish", "pl": "Polish", "cs": "Czech", "fil": "Filipino", "fa": "Persian",
           "el": "Greek", "ro": "Romanian", "hu": "Hungarian", "mk": "Macedonian"}


def estimate_gib(model_id):
    name = model_id.rstrip("/").split("/")[-1]
    for prefix, gib in MODEL_GIB.items():
        if name.startswith(prefix):
            return gib
    return 8


def mem_available_gib():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 / 1024
    return 0.0


def check_memory(need_gib):
    """GB10 shares one 128 GB pool between CPU and GPU. The qwen38 lanes claim a static
    fraction of it (0.50 to 0.85), and DGX OS earlyoom kills processes when the host
    drops to ~8 GiB. Refuse to load when loading would eat into the reserve."""
    mem = load_config().get("memory", {})
    if not mem.get("guard", True):
        return
    avail = mem_available_gib()
    reserve = float(mem.get("reserve_gib", 10))
    if avail - need_gib < reserve:
        raise MemoryError(
            f"not enough unified memory: {avail:.1f} GiB available, model needs ~{need_gib} GiB, "
            f"reserve is {reserve:g} GiB. Use a 0.6B model, stop the large qwen38 lane, "
            f"or lower memory.reserve_gib.")


def torch_dtype(name):
    import torch
    return {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[name]


class ServiceState:
    """Holds the loaded model plus counters the panel reads from /health."""

    def __init__(self, name, cfg):
        self.name = name
        self.cfg = cfg
        self.model = None
        self.status = "loading"
        self.error = None
        self.started = time.time()
        self.load_seconds = None
        self.lock = threading.Lock()  # one GPU job at a time
        self.requests = 0
        self.failures = 0
        self.last_error = None
        self.recent = deque(maxlen=50)  # (timestamp, seconds, audio_seconds)

    def load_in_background(self, loader):
        def run():
            t0 = time.time()
            try:
                self.model = loader(self.cfg)
                self.load_seconds = round(time.time() - t0, 1)
                self.status = "ready"
            except MemoryError as e:
                self.status = "blocked"
                self.error = str(e)
            except Exception as e:  # keep the process up so the panel can show the error
                self.status = "error"
                self.error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
        threading.Thread(target=run, daemon=True).start()

    def record(self, seconds, audio_seconds=None, error=None):
        self.requests += 1
        if error:
            self.failures += 1
            self.last_error = {"time": time.time(), "error": error}
        else:
            self.recent.append((time.time(), seconds, audio_seconds))

    def health(self, extra=None):
        lat = [r[1] for r in self.recent]
        rtf = [r[1] / r[2] for r in self.recent if r[2]]
        out = {
            "service": self.name,
            "status": self.status,
            "error": self.error,
            "model": self.cfg["model"],
            "uptime_s": round(time.time() - self.started),
            "load_seconds": self.load_seconds,
            "requests": self.requests,
            "failures": self.failures,
            "busy": self.lock.locked(),
            "avg_latency_s": round(sum(lat) / len(lat), 3) if lat else None,
            "avg_rtf": round(sum(rtf) / len(rtf), 3) if rtf else None,
            "last_error": self.last_error,
        }
        try:
            import torch
            if torch.cuda.is_available():
                out["torch_cuda_alloc_gb"] = round(torch.cuda.memory_allocated() / 1e9, 2)
                out["torch_cuda_reserved_gb"] = round(torch.cuda.memory_reserved() / 1e9, 2)
        except Exception:
            pass
        if extra:
            out.update(extra)
        return out



# All speech-spark units log into their own journal namespace, capped by install.sh
# (/etc/systemd/journald@speech-spark.conf), so speech logs cannot fill the disk.
JOURNAL_NAMESPACE = "speech-spark"


def journal(unit, lines, fmt="cat"):
    """Last lines a unit logged: its own namespace first, then the system journal (installs
    from before the namespace)."""
    import subprocess
    base = ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", fmt]
    out = ""
    for cmd in (base[:1] + [f"--namespace={JOURNAL_NAMESPACE}"] + base[1:], base):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except Exception:
            continue
        if out.strip() and "-- No entries --" not in out:
            return out
    return out


def quiet_access_log(paths=("/health", "/api/status", "/api/update", "/api/bench", "/api/logs/", "/api/logfilter")):
    """Drop the access-log lines of successful status polls (the panel asks every few seconds)."""
    import logging

    class Polls(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return not ('" 200' in msg and any(f'"GET {p}' in msg for p in paths))
    logging.getLogger("uvicorn.access").addFilter(Polls())


def engine_crash_reason(unit):
    """Last real exception an engine logged before it exited (vLLM prints the cause in the
    EngineCore process; the final 'Engine core initialization failed' line only points back)."""
    import re
    out = journal(unit, 1500)
    if not out:
        return None
    hits = [m.group(1).strip() for m in re.finditer(r"((?:\w+\.)*\w*(?:Error|Exception): .+)", out)
            if "Engine core initialization failed" not in m.group(1)
            and "Orchestrator initialization failed" not in m.group(1)]
    return hits[-1][:300] if hits else None


# ---------------------------------------------------------------- audio sample rate
# The engines resample every recording to 16 kHz. A header that claims "1 Hz" turns a 2 MB file into
# tens of GB on the way (and the DGX OS then stops the LLM lanes), so the rate is checked before
# anything is decoded. Up to 192 kHz is fine: resampling down never grows the audio.
RATE_MIN, RATE_MAX = 8000, 192000


def _wav_rate(data):
    pos = 12
    while pos + 8 <= min(len(data), 1 << 16):
        cid, size = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], "little")
        if cid == b"fmt " and pos + 16 <= len(data):
            return int.from_bytes(data[pos + 12:pos + 16], "little")
        pos += 8 + size + (size & 1)
    return None


def _ogg_rate(head):
    if b"OpusHead" in head:
        return 48000   # Opus always decodes at 48 kHz, whatever the header says it was recorded at
    i = head.find(b"\x01vorbis")
    if i >= 0 and i + 16 <= len(head):
        return int.from_bytes(head[i + 12:i + 16], "little")
    return None


def _probe_rate(data):
    """Sample rate of any other container (mp4/m4a from Safari, mp3, webm with another codec) by
    ffprobe on a temporary file (an m4a keeps its index at the end, so a pipe would not do)."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("ffprobe"):
        print("audio: ffprobe is missing, the sample rate of this file is not checked", flush=True)
        return RATE_MIN
    with tempfile.NamedTemporaryFile(suffix=".audio") as f:
        f.write(data)
        f.flush()
        try:
            p = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "a", "-show_entries", "stream=sample_rate",
                                "-of", "csv=p=0", f.name], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return None
    rates = [int(x) for x in p.stdout.split() if x.strip().isdigit()]
    return min(rates) if rates and p.returncode == 0 else None


def audio_rate(data):
    """The sample rate an audio file will be decoded at, or None when it cannot be found out.
    Reads only the header for WAV, FLAC, Ogg and WebM/Opus; anything else asks ffprobe."""
    head = bytes(data[:1 << 16])
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return _wav_rate(head)
    if head[:4] == b"fLaC" and len(head) >= 21:
        return (head[18] << 12) | (head[19] << 4) | (head[20] >> 4)
    if head[:4] == b"OggS":
        rate = _ogg_rate(head)
        if rate:
            return rate
    if head[:4] == b"\x1a\x45\xdf\xa3" and b"A_OPUS" in head:
        return 48000   # WebM with Opus (what browsers record)
    return _probe_rate(data)


def audio_rate_ok(data):
    """"" when the recording may go to an engine, else why not (for a 415)."""
    rate = audio_rate(data)
    if rate is None:
        return "cannot read this audio"
    if not RATE_MIN <= rate <= RATE_MAX:
        return f"unsupported sample rate {rate} Hz (allowed {RATE_MIN}-{RATE_MAX})"
    return ""


def _loopback(host):
    import ipaddress
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def api_key_dependency():
    """FastAPI dependency: if config api.key is set, require 'Authorization: Bearer <key>'. Without a key only
    this machine itself may call (an old configuration that never went through the panel's check would
    otherwise leave the speech APIs open to the whole network). Read per request, so a key changed in the
    panel applies without a model reload."""
    from fastapi import Header, HTTPException, Request

    def dep(request: Request, authorization: str = Header(None)):
        import hmac
        key = load_config().get("api", {}).get("key", "")
        if not key:
            if not _loopback(request.client.host if request.client else ""):
                raise HTTPException(401, "API key required: none is set, so only this machine may call")
            return
        if not hmac.compare_digest(str(authorization or "").encode(), f"Bearer {key}".encode()):
            raise HTTPException(401, "invalid or missing API key")
    return dep


class KeyedCORS:
    """ASGI middleware: other web pages may call the speech APIs from a browser (CORS) only while an
    API key is set. Without a key any page someone opens in the home network could otherwise use
    the services in the background; with one, the page also needs the key."""

    def __init__(self, app):
        from starlette.middleware.cors import CORSMiddleware
        self.app = app
        self.cors = CORSMiddleware(app, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and load_config().get("api", {}).get("key"):
            return await self.cors(scope, receive, send)
        return await self.app(scope, receive, send)


class _TooLarge(Exception):
    pass


class BodyLimit:
    """ASGI middleware: refuses request bodies over a per-path limit before anything reads them.
    FastAPI parses File/Form/JSON parameters before it runs the login check, so without this anyone
    could fill the disk or memory with a big upload that only gets its 401 afterwards. `limits` is
    [(path prefix, bytes or a function returning them)], first match wins; `gate(scope)` may refuse a big upload from someone who is
    clearly not logged in (False -> 401) before a byte of it is read."""

    def __init__(self, app, limits=(), default=2 * 1024**2, gate=None, gated=()):
        self.app, self.limits, self.default, self.gate, self.gated = app, list(limits), default, gate, tuple(gated)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        limit = next((n for p, n in self.limits if path.startswith(p)), self.default)
        limit = limit() if callable(limit) else limit       # a limit the admin sets (documents)
        cl = dict(scope.get("headers") or []).get(b"content-length", b"")
        if cl.isdigit() and int(cl) > limit:
            return await self._reply(send, 413, "request too large")
        if self.gate and path.startswith(self.gated) and not self.gate(scope):
            return await self._reply(send, 401, "login required")
        seen, started = 0, False

        async def recv():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return msg

        async def snd(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, recv, snd)
        except _TooLarge:
            if not started:
                await self._reply(send, 413, "request too large")

    @staticmethod
    async def _reply(send, status, text):
        import json as _json
        body = _json.dumps({"detail": text}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def inside(request):
    """The caller may see details (errors, model, voices): this machine itself, or the right API key."""
    import ipaddress
    try:
        if ipaddress.ip_address(request.client.host if request.client else "").is_loopback:
            return True
    except ValueError:
        pass
    return api_key_ok(request.scope)


def outside_view(out):
    """What /health shows to anybody else: whether the service is up, nothing more."""
    return {"service": out.get("service"), "status": out.get("status")}


def api_key_ok(scope):
    """For BodyLimit's gate on the speech services: the right Bearer key, or no key configured and a call
    from this machine itself."""
    import hmac
    key = load_config().get("api", {}).get("key", "")
    if not key:
        return _loopback((scope.get("client") or ("",))[0])
    got = dict(scope.get("headers") or []).get(b"authorization", b"")
    return hmac.compare_digest(got, f"Bearer {key}".encode())
