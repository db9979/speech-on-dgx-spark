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


def api_key_dependency():
    """FastAPI dependency: if config api.key is set, require 'Authorization: Bearer <key>'.
    Read per request, so a key changed in the panel applies without a model reload."""
    from fastapi import Header, HTTPException

    def dep(authorization: str = Header(None)):
        key = load_config().get("api", {}).get("key", "")
        if key and authorization != f"Bearer {key}":
            raise HTTPException(401, "invalid or missing API key")
    return dep
