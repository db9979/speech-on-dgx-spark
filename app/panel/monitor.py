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
    vm = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(), "load": os.getloadavg(),
            "mem_total_gib": round(vm.total / 2**30, 1), "mem_avail_gib": round(mem_available_gib(), 1),
            "mem_used_pct": vm.percent}


async def service_health(name, cfg):
    url = model_url(name, "/health", cfg)
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            return (await c.get(url)).json()
    except Exception:
        return None
