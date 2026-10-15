"""Monitoring: GPU, memory and CPU samples, and the health of the speech services."""
import os
import sys
from collections import deque

import httpx
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import mem_available_gib, model_url  # noqa: E402
history = deque(maxlen=400)  # one sample every 3 s, ~20 min


def system_stats():
    """CPU of this computer; the memory of the computer the models run on: with the models on another computer
    (steuer.remote) its last status, else None (the panel computer's memory says nothing about the models, and a
    Raspberry Pi's 8 GB would read as "nur noch 7 GiB frei", tars 2026-10-15)."""
    import steuer
    out = {"cpu": psutil.cpu_percent(), "load": os.getloadavg()}
    if steuer.remote():
        d = steuer.cached() or {}
        avail, total = d.get("mem_avail_gib"), d.get("mem_total_gib")
        ok = all(isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 for x in (avail, total))
        return dict(out, mem_total_gib=total if ok else None, mem_avail_gib=avail if ok else None,
                    mem_used_pct=round(100 * (1 - avail / total), 1) if ok and total else None, mem_von="modell-rechner")
    vm = psutil.virtual_memory()
    return dict(out, mem_total_gib=round(vm.total / 2**30, 1), mem_avail_gib=round(mem_available_gib(), 1),
                mem_used_pct=vm.percent, mem_von="hier")


async def service_health(name, cfg):
    url = model_url(name, "/health", cfg)
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            return (await c.get(url)).json()
    except Exception:
        return None
