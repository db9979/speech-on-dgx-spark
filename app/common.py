"""Shared helpers for the ASR and TTS services: config, model state, request stats."""
import json
import os
import threading
import time
import traceback
from collections import deque

CONFIG_PATH = os.environ.get("SPEECH_SPARK_CONFIG", "/etc/speech-spark/config.json")


DEFAULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.default.json")
_shipped = {"mtime": None, "cfg": {}}


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


def load_config(section=None):
    """The configuration with the shipped default for every key that is missing (plan „Vereinheitlichen“,
    V01.0.268): one place for defaults instead of a `.get(key, default)` at every caller."""
    with open(CONFIG_PATH) as f:
        cfg = _merge(shipped(), json.load(f))
    return cfg[section] if section else cfg


# Speech first (panel vorrang.py): every STT/TTS request touches this file, the panel holds its
# background work (and cancels its background requests to the language model) while it is fresh.
SPEECH_MARK = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "speech-active")
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
    return os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "vorrang-key")


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
                await asyncio.wait_for(asyncio.shield(fut), timeout=1.0)
            except asyncio.TimeoutError:
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


def api_key_dependency():
    """FastAPI dependency: if config api.key is set, require 'Authorization: Bearer <key>'.
    Read per request, so a key changed in the panel applies without a model reload."""
    from fastapi import Header, HTTPException

    def dep(authorization: str = Header(None)):
        import hmac
        key = load_config().get("api", {}).get("key", "")
        if key and not hmac.compare_digest(str(authorization or "").encode(), f"Bearer {key}".encode()):
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
    """For BodyLimit's gate on the speech services: the right Bearer key, or no key configured."""
    import hmac
    key = load_config().get("api", {}).get("key", "")
    got = dict(scope.get("headers") or []).get(b"authorization", b"")
    return not key or hmac.compare_digest(got, f"Bearer {key}".encode())
