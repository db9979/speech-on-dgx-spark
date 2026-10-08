"""Shared helpers for the ASR and TTS services: config, model state, request stats."""
import json
import os
import threading
import time
import traceback
from collections import deque

CONFIG_PATH = os.environ.get("SPEECH_SPARK_CONFIG", "/etc/speech-spark/config.json")


def load_config(section=None):
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return cfg[section] if section else cfg


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


def quiet_access_log(paths=("/health", "/api/status", "/api/update", "/api/bench", "/api/logs/")):
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


class _TooLarge(Exception):
    pass


class BodyLimit:
    """ASGI middleware: refuses request bodies over a per-path limit before anything reads them.
    FastAPI parses File/Form/JSON parameters before it runs the login check, so without this anyone
    could fill the disk or memory with a big upload that only gets its 401 afterwards. `limits` is
    [(path prefix, bytes)], first match wins; `gate(scope)` may refuse a big upload from someone who is
    clearly not logged in (False -> 401) before a byte of it is read."""

    def __init__(self, app, limits=(), default=2 * 1024**2, gate=None, gated=()):
        self.app, self.limits, self.default, self.gate, self.gated = app, list(limits), default, gate, tuple(gated)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        limit = next((n for p, n in self.limits if path.startswith(p)), self.default)
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


def api_key_ok(scope):
    """For BodyLimit's gate on the speech services: the right Bearer key, or no key configured."""
    import hmac
    key = load_config().get("api", {}).get("key", "")
    got = dict(scope.get("headers") or []).get(b"authorization", b"")
    return not key or hmac.compare_digest(got, f"Bearer {key}".encode())
