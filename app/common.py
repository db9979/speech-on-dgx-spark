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
PREFIX = os.environ.get("SPEECH_SPARK_PREFIX", "/opt/speech-spark")
# the TLS certificate of this machine (cert.pem, key.pem): the panel's https port and the TLS-Tor (tlstor.py)
TLS_DIR = os.environ.get("SPEECH_SPARK_TLS", "/etc/speech-spark/tls")
# the door's own certificate (Spark teilen, tlstor.py): apart from the panel's https certificate, which apps pin and
# which moves with the panel (umziehen); the door's stays on the model computer and is only ever seen in the LAN
TOR_CERT, TOR_KEY = os.path.join(TLS_DIR, "tor-cert.pem"), os.path.join(TLS_DIR, "tor-key.pem")


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


# Qwen3-ASR languages by ISO 639-1 code (OpenAI clients send codes, qwen-asr wants names).
ASR_ISO = {"zh": "Chinese", "en": "English", "yue": "Cantonese", "ar": "Arabic", "de": "German",
           "fr": "French", "es": "Spanish", "pt": "Portuguese", "id": "Indonesian", "it": "Italian",
           "ko": "Korean", "ru": "Russian", "th": "Thai", "vi": "Vietnamese", "ja": "Japanese",
           "tr": "Turkish", "hi": "Hindi", "ms": "Malay", "nl": "Dutch", "sv": "Swedish", "da": "Danish",
           "fi": "Finnish", "pl": "Polish", "cs": "Czech", "fil": "Filipino", "fa": "Persian",
           "el": "Greek", "ro": "Romanian", "hu": "Hungarian", "mk": "Macedonian"}


def estimate_gib(model_id):
    """Unified memory a speech model needs while loaded (GiB, incl. CUDA context): its need_gib in the model catalog
    (modelle.json), 8 for a repository the catalog lacks."""
    import modelle
    return modelle.need_gib(model_id)


def fehler_stelle(e):
    """Where an exception stopped, in fixed words (kind, file, function, line) for a log line, never its message (it
    may name a profile's file or words); with the exception it came from ("aus ...") when there is one."""
    f = traceback.extract_tb(e.__traceback__)[-1] if e.__traceback__ is not None else None
    out = type(e).__name__ + (f" {os.path.basename(f.filename)} {f.name} {f.lineno}" if f else "")
    c = e.__context__
    if c is not None and c.__traceback__ is not None:
        g = traceback.extract_tb(c.__traceback__)[-1]
        out += f" | aus {type(c).__name__} {os.path.basename(g.filename)} {g.name} {g.lineno}"
    return out


def mem_available_gib(key="MemAvailable"):
    """GiB from /proc/meminfo: what is free for new work (MemAvailable), or with key="MemTotal" all of it."""
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith(key + ":"):
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


# the units of the model side (speech, engines, the own language model); the panel may start/stop/restart UNITS
# (matches /etc/sudoers.d/speech-spark); OWN_LLM_UNITS only `speech-spark modelle llm uebernehmen|zurueck` switches
SERVICES = {"asr": "speech-spark-asr", "tts": "speech-spark-tts"}
UNITS = dict(SERVICES, **{"asr-engine": "speech-spark-asr-engine", "tts-engine": "speech-spark-tts-engine",
                          "tts-design": "speech-spark-tts-design"})
OWN_LLM_UNITS = {"llm": "speech-spark-llm", "llmtor": "speech-spark-llmtor", "sehen": "speech-spark-sehen"}
# the optional services that load their engine only on demand (install.sh --bild, --musik): watched and shown on the
# model computer's card (Monitoring, Steuerzentrale), never started or stopped by the panel
ON_DEMAND_UNITS = {"bild": "speech-spark-bild", "musik": "speech-spark-musik"}
# Units installed by github.com/hasso5703/dgx-spark-qwen38; only one lane runs at a time.
QWEN38_UNITS = ["qwen38-sglang", "qwen38-sglang-1m", "qwen38-flash", "qwen38-image",
                "qwen38-video", "qwen38-llamacpp", "qwen38-keepalive", "qwen38-dashboard"]
# the Wärter on the model computer (tarswart.py, plan Raspberry-Pi split B4): behind the TLS-Tor, own key
WAERTER_PORT = 31007
# Notbetrieb mit Parakeet on the panel computer (B5c, panel/notbetrieb.py): asr_proxy.py with SPEECH_SPARK_NOTASR=1
NOTASR_PORT = 31009
NOTASR_IDLE = 600      # seconds without a recording before Parakeet gives its memory back
ASR_UMWEG = None       # set by panel/notbetrieb.py: callable(cfg) -> True while this computer's Parakeet hears
WAERTER_KEY = os.path.join(STATE, "waerter.key")
WARTUNG_FILE = os.path.join(STATE, "wartung.json")   # the Wartungspause (panel/wartung.py); on the model computer its wish


def installed_version():
    """What update.sh / install.sh installed (PREFIX/VERSION.json: commit, short, subject, date, …)."""
    try:
        with open(os.path.join(PREFIX, "VERSION.json")) as f:
            return json.load(f)
    except Exception:
        return {"commit": None, "subject": "unknown"}


def run(cmd, timeout=10, env=None):
    """A command without a shell: (exit code, stdout+stderr); any failure is (1, its text)."""
    import subprocess
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def unit_exists(unit):
    code, out = run(["systemctl", "list-unit-files", unit + ".service", "--no-legend"])
    return code == 0 and out.startswith(unit + ".service")


def lane_fraction(unit):
    """The static share of the unified pool a qwen38 lane claims (0.50 / 0.76 / 0.85)."""
    code, out = run(["systemctl", "cat", unit])
    m = re.search(r"--mem-fraction-static\s+([0-9.]+)", out)
    if m:
        return float(m.group(1))
    if unit == "qwen38-flash":  # the flag lives in its launch script; installer default
        return 0.85
    return None


def qwen38_lanes():
    """[(unit, share)] of the qwen38 lanes installed on this computer."""
    return [(u, lane_fraction(u)) for u in QWEN38_UNITS if unit_exists(u)]


def gpu_stats():
    """The GPU from nvidia-smi (name, load, temperature, power, clock, compute processes), None without one."""
    import shutil
    if not shutil.which("nvidia-smi"):
        return None
    fields = "name,utilization.gpu,temperature.gpu,power.draw,clocks.sm,memory.used,memory.total"
    code, out = run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
    if code != 0 or not out:
        return None
    vals = [v.strip() for v in out.splitlines()[0].split(",")]

    def num(v):
        try:
            return float(v)
        except ValueError:
            return None  # GB10 reports "[N/A]" for memory: it is the shared pool
    g = dict(zip(fields.split(","), vals))
    procs = []
    code, out = run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                     "--format=csv,noheader,nounits"])
    for line in out.splitlines() if code == 0 else []:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            procs.append({"pid": parts[0], "name": parts[1].split("/")[-1], "mem_mib": num(parts[2])})
    return {"name": g["name"], "util": num(g["utilization.gpu"]), "temp": num(g["temperature.gpu"]),
            "power": num(g["power.draw"]), "clock": num(g["clocks.sm"]), "processes": procs}


# The engines load models with --trust-remote-code: any other repo could bring its own code along.
MODEL_ID = re.compile(r"Qwen/Qwen3-(ASR|TTS|ForcedAligner)-[\w.\-]+")
# settings of the model side the panel sets and the model computer must know (Spark teilen, B4b): the sections and the
# keys that stay as each computer's install made them (addresses, ports, backends)
SYNC_SECTIONS = ("asr", "tts", "memory", "watch", "image", "music")
SYNC_KEEP = {"host", "port", "engine_port", "voicedesign_port", "backend"}
# which model runs (B4c): the model computer decides (install.sh, Zustand → Modelle, `speech-spark modelle`) and
# reports it in its status; the panel takes it over, never the other way round
MODEL_CHOICE = {"asr": ("model", "aligner_model", "recognizer"), "tts": ("model", "voicedesign_model"),
                "image": ("enabled", "variant"), "music": ("enabled", "variant"),
                "llm": ("enabled", "modell", "sehen_modell")}


def _keep(sec):
    return SYNC_KEEP | set(MODEL_CHOICE.get(sec, ()))


def model_settings(cfg):
    """The settings the model computer takes from the panel: SYNC_SECTIONS without the install's own keys and
    without the model choice."""
    return {sec: {k: v for k, v in (cfg.get(sec) or {}).items() if k not in _keep(sec)} for sec in SYNC_SECTIONS}


def model_settings_hash(cfg):
    import hashlib
    return hashlib.sha256(json.dumps(model_settings(cfg), sort_keys=True).encode()).hexdigest()[:16]


def model_settings_take(cfg, got, defaults):
    """cfg with the panel's settings `got` taken in: only known keys of SYNC_SECTIONS of the same kind as the
    shipped default, never the install's own keys or the model choice. ValueError on anything else."""
    if not isinstance(got, dict) or set(got) - set(SYNC_SECTIONS):
        raise ValueError("abschnitt")
    new = json.loads(json.dumps(cfg))
    for sec, vals in got.items():
        if not isinstance(vals, dict):
            raise ValueError("abschnitt")
        for k, v in vals.items():
            d = (defaults.get(sec) or {}).get(k, None)
            if k in _keep(sec) or k not in (defaults.get(sec) or {}):
                raise ValueError("schluessel")
            num = (int, float)
            same = (isinstance(v, bool) == isinstance(d, bool)) and (
                isinstance(v, type(d)) or (isinstance(d, num) and isinstance(v, num)))
            if not same or (isinstance(v, str) and len(v) > 4000):
                raise ValueError("wert")
            new.setdefault(sec, {})[k] = v
    return new


def model_choice(cfg):
    """{section: {key: value}} of MODEL_CHOICE as this configuration has it."""
    return {sec: {k: (cfg.get(sec) or {}).get(k) for k in keys} for sec, keys in MODEL_CHOICE.items()}


def model_choice_take(cfg, got, defaults):
    """The changes of the model choice the model computer reports, checked: only MODEL_CHOICE keys of the same kind
    as the shipped default, the speech models only Qwen's (MODEL_ID), names short. {section: {key: value}} of what
    differs from cfg; ValueError("wahl") on anything else."""
    if not isinstance(got, dict) or set(got) - set(MODEL_CHOICE):
        raise ValueError("wahl")
    out = {}
    for sec, vals in got.items():
        if not isinstance(vals, dict) or set(vals) - set(MODEL_CHOICE[sec]):
            raise ValueError("wahl")
        for k, v in vals.items():
            d = (defaults.get(sec) or {}).get(k)
            if isinstance(d, bool) != isinstance(v, bool) or not isinstance(v, type(d)) \
                    or (isinstance(v, str) and not re.fullmatch(r"([A-Za-z0-9][\w.\-]{0,47}(/[A-Za-z0-9][\w.\-]{0,95})?)?", v)):
                raise ValueError("wahl")
            if k.endswith("model") and sec in ("asr", "tts") and not MODEL_ID.fullmatch(v):
                raise ValueError("wahl")
            if (cfg.get(sec) or {}).get(k) != v:
                out.setdefault(sec, {})[k] = v
    return out


def waerter_key(path=None):
    """The Wärter's shared key (32 bytes from the pairing, hex in STATE/waerter.key), b"" without one."""
    try:
        with open(path or WAERTER_KEY) as f:
            k = f.read().strip()
        return bytes.fromhex(k) if re.fullmatch(r"[0-9a-f]{64}", k) else b""
    except (OSError, ValueError):
        return b""


def waerter_sign(key, body):
    """HMAC-SHA256 of the exact request body with the Wärter key (hex); both sides use this one function."""
    import hashlib
    import hmac
    return hmac.new(key, body, hashlib.sha256).hexdigest()


# the model computer (plan Raspberry-Pi split, B1): speech recognition, speech output, pictures, music and the LLM-Tor
# live on models.host, 127.0.0.1 when everything runs on one Spark. art -> its config section with the port
MODEL_ARTS = {"asr": "asr", "tts": "tts", "bild": "image", "musik": "music", "llm": "llm"}
MODEL_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|[0-9A-Fa-f:]{2,39}")


def model_host(cfg=None):
    """models.host, checked; anything else than a plain name or IP falls back to this Spark (127.0.0.1)."""
    cfg = load_config() if cfg is None else cfg
    host = str((cfg.get("models") or {}).get("host") or "").strip()
    return host if MODEL_HOST_RE.fullmatch(host) else "127.0.0.1"


def model_local(cfg=None):
    """True while the models run on this Spark (the all-in-one install)."""
    host = model_host(cfg)
    return host == "localhost" or _loopback(host)


def pinned_context(pem, minimum=None):
    """An SSLContext that trusts exactly this one certificate (PEM), checked inside the handshake; the name is not
    compared, the certificate itself must match. A missing or broken PEM trusts nothing (every handshake fails)."""
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = minimum or ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN     # the pinned (leaf) certificate is the only anchor
    if pem:
        try:
            ctx.load_verify_locations(cadata=pem)
        except (ssl.SSLError, ValueError, TypeError):
            pass
    return ctx


_mounts = {"key": None, "ctx": None}


def model_mounts(cfg=None, sync=False):
    """httpx mounts for the model computer (plan Raspberry-Pi split, B2): https to models.host trusts only the
    certificate the pairing pinned (models.cert, TLS 1.3), nothing else; None on the all-in-one install."""
    import ssl
    import httpx
    cfg = load_config() if cfg is None else cfg
    if model_local(cfg):
        return None
    host, pem = model_host(cfg), str((cfg.get("models") or {}).get("cert") or "")
    if _mounts["key"] != (host, pem):
        _mounts.update(key=(host, pem), ctx=pinned_context(pem, ssl.TLSVersion.TLSv1_3))
    kind = httpx.HTTPTransport if sync else httpx.AsyncHTTPTransport
    return {f"https://{'[' + host + ']' if ':' in host else host}": kind(verify=_mounts["ctx"], retries=0)}


def _pin_models():
    """Every httpx client of this process that does not bring its own transport, mounts or verify reaches the model
    computer only with the pinned certificate (model_mounts): one place instead of a mount at each of the ~50
    clients that talk to speech, pictures or the language model. netguard.client brings its own transport, so a
    tool never gets this way; on the all-in-one install nothing changes. tests/test_teilen.py checks it."""
    try:
        import httpx
    except ImportError:
        return
    for cls, sync in ((httpx.AsyncClient, False), (httpx.Client, True)):
        init = cls.__init__
        if getattr(init, "pinned", False):
            continue

        def __init__(self, *args, _init=init, _sync=sync, **kw):
            if kw.get("transport") is None and kw.get("mounts") is None and kw.get("verify", True) is True:
                try:
                    m = model_mounts(sync=_sync)
                except (OSError, ValueError, KeyError):
                    m = None
                if m:
                    kw["mounts"] = m
            _init(self, *args, **kw)
        __init__.pinned = True
        cls.__init__ = __init__


def model_side(cfg=None):
    """True on the model computer of a split install: its TLS-Tor serves a panel on another computer (api.tls_listen)."""
    cfg = load_config() if cfg is None else cfg
    return bool(str((cfg.get("api") or {}).get("tls_listen") or "").strip())


def model_url(art, path="", cfg=None):
    """The one address of a model service (B1): http on this Spark; https to another computer, whose certificate the
    pairing pins (B3), so speech, text and pictures never cross the network in plain text."""
    cfg = load_config() if cfg is None else cfg
    if art == "asr" and ASR_UMWEG is not None and ASR_UMWEG(cfg):   # Notbetrieb: the model computer is gone
        return f"http://127.0.0.1:{NOTASR_PORT}{path}"
    host = model_host(cfg)
    port = WAERTER_PORT if art == "waerter" else int(cfg[MODEL_ARTS[art]]["port"])
    if model_local(cfg):
        return f"http://127.0.0.1:{port}{path}"
    return f"https://{'[' + host + ']' if ':' in host else host}:{port}{path}"


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


_pin_models()
