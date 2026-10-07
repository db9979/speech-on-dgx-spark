"""Monitoring: GPU, memory and CPU samples, and the health of the speech services."""
import os
import re
import shutil
import sys
from collections import deque

import httpx
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import mem_available_gib  # noqa: E402
from core import run  # noqa: E402
history = deque(maxlen=400)  # one sample every 3 s, ~20 min


def lane_fraction(unit):
    """The static share of the unified pool a qwen38 lane claims (0.50 / 0.76 / 0.85)."""
    code, out = run(["systemctl", "cat", unit])
    m = re.search(r"--mem-fraction-static\s+([0-9.]+)", out)
    if m:
        return float(m.group(1))
    if unit == "qwen38-flash":  # the flag lives in its launch script; installer default
        return 0.85
    return None


def gpu_stats():
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


def system_stats():
    vm = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(), "load": os.getloadavg(),
            "mem_total_gib": round(vm.total / 2**30, 1), "mem_avail_gib": round(mem_available_gib(), 1),
            "mem_used_pct": vm.percent}


async def service_health(name, cfg):
    url = f"http://127.0.0.1:{cfg[name]['port']}/health"
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            return (await c.get(url)).json()
    except Exception:
        return None
