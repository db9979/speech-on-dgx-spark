"""Speech on DGX Spark: web panel for config and monitoring."""
import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections import deque

import httpx
import psutil
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import CONFIG_PATH, estimate_gib, load_config, mem_available_gib  # noqa: E402

VOICES_DIR = os.environ.get("SPEECH_SPARK_VOICES", "/var/lib/speech-spark/voices")
PASSWORD = os.environ.get("PANEL_PASSWORD", "")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SERVICES = {"asr": "speech-spark-asr", "tts": "speech-spark-tts"}
# Units installed by github.com/hasso5703/dgx-spark-qwen38; only one lane runs at a time.
QWEN38_UNITS = ["qwen38-sglang", "qwen38-sglang-1m", "qwen38-flash", "qwen38-image",
                "qwen38-video", "qwen38-llamacpp", "qwen38-keepalive", "qwen38-dashboard"]
LANGS = ["auto", "Chinese", "English", "German", "French", "Spanish", "Italian", "Portuguese",
         "Russian", "Japanese", "Korean", "Dutch", "Polish", "Turkish", "Arabic"]

app = FastAPI(title="Speech on DGX Spark")
security = HTTPBasic()
history = deque(maxlen=400)  # one sample every 3 s, ~20 min


def auth(creds: HTTPBasicCredentials = Depends(security)):
    if not PASSWORD:
        return
    ok = secrets.compare_digest(creds.password.encode(), PASSWORD.encode())
    if not ok:
        raise HTTPException(401, "wrong password", headers={"WWW-Authenticate": "Basic"})


def run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def unit_state(unit):
    out = run(["systemctl", "is-active", unit])[1].split("\n")[0].strip()
    return out if re.fullmatch(r"[a-z\-]+", out) else "unknown"


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


@app.on_event("startup")
async def sampler():
    async def loop():
        psutil.cpu_percent()
        while True:
            try:
                cfg = load_config()
                g = gpu_stats() or {}
                s = system_stats()
                h = {n: await service_health(n, cfg) for n in SERVICES}
                history.append({"t": time.time(), "gpu": g.get("util"), "cpu": s["cpu"],
                                "avail": s["mem_avail_gib"], "temp": g.get("temp"), "power": g.get("power"),
                                "asr_req": (h["asr"] or {}).get("requests"),
                                "tts_req": (h["tts"] or {}).get("requests")})
            except Exception as e:
                print("sampler:", e, flush=True)
            await asyncio.sleep(3)
    asyncio.create_task(loop())


@app.get("/", dependencies=[Depends(auth)])
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status", dependencies=[Depends(auth)])
async def status():
    cfg = load_config()
    services = {}
    for name, unit in SERVICES.items():
        services[name] = {"unit": unit, "state": unit_state(unit), "enabled": cfg[name]["enabled"],
                          "port": cfg[name]["port"], "estimate_gib": estimate_gib(cfg[name]["model"]),
                          "health": await service_health(name, cfg)}
    qwen38 = [{"unit": u, "state": unit_state(u), "mem_fraction": lane_fraction(u)}
              for u in QWEN38_UNITS if unit_exists(u)]
    return {"time": time.time(), "system": system_stats(), "gpu": gpu_stats(),
            "services": services, "qwen38": qwen38, "history": list(history)}


@app.get("/api/config", dependencies=[Depends(auth)])
def get_config():
    with open(DEFAULTS) as f:
        cfg = json.load(f)
    for sec, vals in load_config().items():  # fill keys added by newer versions
        cfg.setdefault(sec, {}).update(vals)
    return cfg


def api_headers():
    key = load_config().get("api", {}).get("key", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


DEFAULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.default.json")


def validate(new):
    old = load_config()
    with open(DEFAULTS) as f:
        defaults = json.load(f)
    for sec in defaults:
        if sec not in new or not isinstance(new[sec], dict):
            raise HTTPException(400, f"section '{sec}' missing")
        for k in new[sec]:
            if k not in defaults[sec]:
                raise HTTPException(400, f"unknown key {sec}.{k}")
    if not re.fullmatch(r"[A-Za-z0-9_\-]*", new["api"]["key"]):
        raise HTTPException(400, "API key: letters, digits, _ and - only")
    ports = [new["asr"]["port"], new["tts"]["port"], new["panel"]["port"]]
    for p in ports:
        if not isinstance(p, int) or not 1024 <= p <= 65535:
            raise HTTPException(400, f"invalid port {p}")
        if 30000 <= p <= 30099:
            raise HTTPException(400, f"port {p} is in the 30000-30099 range used by dgx-spark-qwen38")
    if len(set(ports)) != 3:
        raise HTTPException(400, "ports must differ")
    for sec in ("asr", "tts"):
        if not re.fullmatch(r"[\w.\-/]+", str(new[sec]["model"])):
            raise HTTPException(400, f"invalid model id {new[sec]['model']}")
        if new[sec]["dtype"] not in ("bfloat16", "float16", "float32"):
            raise HTTPException(400, "dtype must be bfloat16, float16 or float32")
    return old


@app.put("/api/config", dependencies=[Depends(auth)])
async def put_config(request: Request):
    new = await request.json()
    old = validate(new)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
    # the API key is read per request, so changing it needs no restart
    restart = [n for n in SERVICES if new[n] != old[n] or new["memory"] != old.get("memory")]
    for n in SERVICES:
        if n in restart:
            action = "restart" if new[n]["enabled"] else "stop"
            run(["sudo", "-n", "/usr/bin/systemctl", action, SERVICES[n]])
    return {"saved": True, "restarted": restart, "panel_restart_needed": new["panel"] != old["panel"]}


@app.post("/api/service/{name}/{action}", dependencies=[Depends(auth)])
def service_action(name: str, action: str):
    if name not in SERVICES or action not in ("start", "stop", "restart"):
        raise HTTPException(400, "bad service or action")
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", action, SERVICES[name]], timeout=30)
    if code != 0:
        raise HTTPException(500, out or f"systemctl {action} failed")
    return {"ok": True}


@app.get("/api/logs/{name}", dependencies=[Depends(auth)])
def logs(name: str, lines: int = 200):
    units = dict(SERVICES, panel="speech-spark-panel")
    if name not in units:
        raise HTTPException(400, "bad service")
    code, out = run(["journalctl", "-u", units[name], "-n", str(min(lines, 2000)),
                     "--no-pager", "-o", "short-iso"])
    return Response(out, media_type="text/plain")


@app.get("/api/languages", dependencies=[Depends(auth)])
def languages():
    return LANGS


@app.post("/api/test/asr", dependencies=[Depends(auth)])
async def test_asr(file: UploadFile = File(...), language: str = Form("auto")):
    cfg = load_config()
    data = await file.read()
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions",
                         files={"file": (file.filename or "audio.wav", data)}, data={"language": language},
                         headers=api_headers())
    return Response(r.content, status_code=r.status_code, media_type="application/json")


@app.post("/api/test/tts", dependencies=[Depends(auth)])
async def test_tts(request: Request):
    cfg = load_config()
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", json=await request.json(),
                         headers=api_headers())
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"),
                    headers={k: v for k, v in r.headers.items() if k.lower() == "x-processing-seconds"})


@app.get("/api/tts/voices", dependencies=[Depends(auth)])
async def tts_voices():
    cfg = load_config()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            return (await c.get(f"http://127.0.0.1:{cfg['tts']['port']}/v1/voices")).json()
    except Exception:
        return {"model_kind": None, "voices": [], "languages": []}


@app.get("/api/clone-voices", dependencies=[Depends(auth)])
def clone_voices():
    os.makedirs(VOICES_DIR, exist_ok=True)
    return sorted(f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))


@app.post("/api/clone-voices", dependencies=[Depends(auth)])
async def add_clone_voice(name: str = Form(...), text: str = Form(""), file: UploadFile = File(...)):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
        raise HTTPException(400, "name: letters, digits, _ and - only")
    os.makedirs(VOICES_DIR, exist_ok=True)
    with open(os.path.join(VOICES_DIR, name + ".wav"), "wb") as f:
        f.write(await file.read())
    txt = os.path.join(VOICES_DIR, name + ".txt")
    if text.strip():
        with open(txt, "w") as f:
            f.write(text.strip())
    elif os.path.exists(txt):
        os.remove(txt)
    return {"ok": True}


@app.delete("/api/clone-voices/{name}", dependencies=[Depends(auth)])
def delete_clone_voice(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
        raise HTTPException(400, "bad name")
    for ext in (".wav", ".txt"):
        p = os.path.join(VOICES_DIR, name + ext)
        if os.path.exists(p):
            os.remove(p)
    return {"ok": True}


if __name__ == "__main__":
    pcfg = load_config("panel")
    uvicorn.run(app, host=pcfg["host"], port=pcfg["port"])
