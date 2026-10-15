"""Wärter (plan Raspberry-Pi split, B4): the model computer's few hands for a panel on another computer.

When the panel runs on a Raspberry Pi, it can no longer call systemctl or nvidia-smi for the models itself. This
small service on the DGX does it for it, with a fixed list of commands and nothing else: no shell, no free unit
names, no paths. It listens on 127.0.0.1:WAERTER_PORT only; the panel reaches it through the TLS-Tor (TLS 1.3,
pinned certificate, only the panel computer, tlstor.py) and signs every request with the Wärter key from the pairing
(STATE/waerter.key, not the API key, which other devices know too): HMAC-SHA256 over the exact body, which carries
a time (at most WINDOW seconds off) and a one-time number (each is taken once).

    status                      version, state and uptime of the model units, GPU, free memory
    einheit <start|stop|restart> <teil>   only parts of common.UNITS (speech and its engines)

Every request writes one log line ("waerter:" with the command and the result word, never content).
"""
import json
import os
import re
import sys
import threading
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from common import (OWN_LLM_UNITS, UNITS, WAERTER_PORT, BodyLimit, gpu_stats, mem_available_gib, run,
                    waerter_key, waerter_sign)

WINDOW = 60            # seconds a request's time may be off
MAX_BODY = 4096
MAX_SEEN = 5000        # one-time numbers kept (each lives WINDOW * 2 seconds)
RATE = (40, 10)        # at most 40 requests in 10 seconds (the panel asks for the status every few seconds)
ACTIONS = ("start", "stop", "restart")
# what status reports: the units the panel shows and watches
WATCHED = dict(UNITS, **OWN_LLM_UNITS)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(BodyLimit, default=MAX_BODY)
_seen = {}
_times = []
_lock = threading.Lock()


def version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as f:
            return f.read().strip()[:20]
    except OSError:
        return ""


def _states(units):
    """{unit: {"state", "seit"}} from one systemctl show for all units (blocks in the asked order)."""
    code, out = run(["systemctl", "show", *units, "-p", "Id,ActiveState,ActiveEnterTimestampMonotonic"])
    got = {}
    for block in out.split("\n\n") if code == 0 else []:
        props = dict(x.split("=", 1) for x in block.splitlines() if "=" in x)
        unit = props.get("Id", "").removesuffix(".service")
        if unit not in units:
            continue
        state = props.get("ActiveState", "")
        state = state if re.fullmatch(r"[a-z\-]{1,20}", state) else "unknown"
        try:
            t = int(props.get("ActiveEnterTimestampMonotonic", "0")) / 1e6
        except ValueError:
            t = 0
        got[unit] = {"state": state, "seit": round(time.monotonic() - t) if state == "active" and t else None}
    return {u: got.get(u, {"state": "unknown", "seit": None}) for u in units}


def status():
    try:
        mem = round(mem_available_gib(), 1)
    except OSError:
        mem = None
    return {"version": version(), "einheiten": _states(list(WATCHED.values())), "gpu": gpu_stats(),
            "mem_avail_gib": mem}


def einheit(action, teil):
    if action not in ACTIONS or teil not in UNITS:
        raise ValueError("befehl")
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", action, UNITS[teil]], timeout=120)
    print(f"waerter: einheit {action} {teil} {'ok' if code == 0 else 'fehler'}", flush=True)
    return {"ok": code == 0, "code": code}


def check(raw, sig, key, now=None):
    """The command from a signed body, or ValueError with the reason word (unterschrift, zeit, nummer, befehl)."""
    now = time.time() if now is None else now
    if not key or not isinstance(sig, str) or not re.fullmatch(r"[0-9a-f]{64}", sig):
        raise ValueError("unterschrift")
    import hmac
    if not hmac.compare_digest(waerter_sign(key, raw), sig):
        raise ValueError("unterschrift")
    try:
        d = json.loads(raw)
    except ValueError:
        raise ValueError("befehl")
    if not isinstance(d, dict) or not isinstance(d.get("ts"), (int, float)) or abs(now - d["ts"]) > WINDOW:
        raise ValueError("zeit")
    nonce = d.get("nonce")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("nummer")
    with _lock:
        for n, t in list(_seen.items()):
            if now - t > WINDOW * 2:
                del _seen[n]
        if nonce in _seen or len(_seen) >= MAX_SEEN:
            raise ValueError("nummer")
        _seen[nonce] = now
    cmd, args = d.get("cmd"), d.get("args") or []
    if cmd not in ("status", "einheit") or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("befehl")
    return cmd, args


def _rate(now):
    with _lock:
        _times[:] = [t for t in _times if now - t < RATE[1]]
        if len(_times) >= RATE[0]:
            return False
        _times.append(now)
        return True


@app.post("/v1/wart")
async def wart(request: Request):
    now = time.time()
    if not _rate(now):
        print("waerter: abgelehnt zu viele", flush=True)
        raise HTTPException(429, "too many")
    raw = await request.body()
    try:
        cmd, args = check(raw, request.headers.get("x-wart", ""), waerter_key(), now)
    except ValueError as e:
        print(f"waerter: abgelehnt {e}", flush=True)
        raise HTTPException(403 if str(e) != "befehl" else 400, str(e))
    if cmd == "status":       # asked every few seconds: no line for a good answer, only for refusals
        return JSONResponse(status())
    try:
        return JSONResponse(einheit(*args) if len(args) == 2 else einheit("", ""))
    except ValueError:
        print("waerter: abgelehnt befehl", flush=True)
        raise HTTPException(400, "befehl")


@app.get("/health")
def health():
    return {"status": "ready" if waerter_key() else "no key"}


if __name__ == "__main__":
    if not waerter_key():
        print("waerter: ohne schluessel, kein start", flush=True)
        sys.exit(1)
    uvicorn.run(app, host="127.0.0.1", port=WAERTER_PORT, log_level="warning")
