"""Steuer (plan Raspberry-Pi split, B4): the model units and the GPU, here or on the model computer.

On the all-in-one install everything stays local (systemctl, nvidia-smi). When the models run on another computer
(models.host), the panel asks its Wärter (tarswart.py) instead: through the TLS-Tor with the pinned certificate,
every request signed with the Wärter key (common.waerter_sign). Units of this computer (panel, TURN relay, its own
update) are never sent there.

    unit_state(unit)            "active", "inactive", "failed", … or "unknown"
    active_seconds(unit)        seconds since the unit became active, None when it is not
    systemctl(action, unit)     (code, text): start, stop or restart a unit of common.UNITS
    gpu()                       the GPU (common.gpu_stats), None without one
    einstellen(cfg)             hands the speech settings to the model computer (common.model_settings)
    logs(name, n)               the last log lines of a model unit, here or there

When the model computer reports other speech settings than the panel's (a hash in its status), they are handed over
again, at most every PUSH seconds: a save while it was away is not lost.

The status of the model computer is asked at most every CACHE seconds; when it does not answer, its units read
"unknown" and the GPU None, which the pages show as „nicht erreichbar“. Logs ("steuer:" lines) only for actions.
"""
import json
import secrets
import threading
import time

import httpx

from common import (OWN_LLM_UNITS, UNITS, gpu_stats, journal, load_config, model_local, model_settings,
                    model_settings_hash, model_url, run, waerter_key, waerter_sign)

CACHE = 3              # seconds a status of the model computer is reused
PUSH = 60              # seconds between two hand-overs of the speech settings when the hashes differ
TIMEOUT = 5
MODEL_UNITS = set(UNITS.values()) | set(OWN_LLM_UNITS.values())
_status = {"t": 0.0, "d": None, "push": -PUSH}
_lock = threading.Lock()
_client = None         # the self-tests put a client for the Wärter here


def remote(cfg=None):
    return not model_local(cfg)


def call(cmd, args=(), cfg=None, timeout=TIMEOUT, daten=None):
    """One signed request to the Wärter; its JSON answer, or None when it does not answer or refuses."""
    cfg = load_config() if cfg is None else cfg
    key = waerter_key()
    if not key:
        return None
    d = {"cmd": cmd, "args": list(args), "ts": int(time.time()), "nonce": secrets.token_hex(16)}
    if daten is not None:
        d["daten"] = daten
    body = json.dumps(d, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "X-Wart": waerter_sign(key, body)}
    try:
        if _client is not None:
            r = _client.post("/v1/wart", content=body, headers=headers)
        else:
            with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as c:
                r = c.post(model_url("waerter", "/v1/wart", cfg), content=body, headers=headers)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, OSError, ValueError):
        return None


def status(cfg=None, now=None):
    """The model computer's status (cached CACHE seconds), None when it does not answer."""
    now = time.monotonic() if now is None else now
    with _lock:
        if _status["d"] is not None and now - _status["t"] < CACHE:
            return _status["d"]
    cfg = load_config() if cfg is None else cfg
    d = call("status", cfg=cfg)
    d = d if isinstance(d, dict) and isinstance(d.get("einheiten"), dict) else None
    with _lock:
        _status.update(t=now, d=d)
        due = d is not None and d.get("einstellungen") != model_settings_hash(cfg) and now - _status["push"] >= PUSH
        if due:
            _status["push"] = now
    if due:
        einstellen(cfg, why="abgleich")
    return d


def einstellen(cfg=None, why="gespeichert"):
    """Hands the speech settings to the model computer; True when it took them."""
    cfg = load_config() if cfg is None else cfg
    d = call("einstellen", cfg=cfg, daten=model_settings(cfg), timeout=10)
    ok = isinstance(d, dict) and d.get("ok") is True
    print(f"steuer: einstellen {why} {'ok' if ok else 'fehler'}", flush=True)
    return ok


def logs(name, unit, n, cfg=None):
    """The last n log lines of a unit: of a model unit on the model computer through the Wärter."""
    if _remote_unit(unit, cfg):
        d = call("logs", (name, str(n)), cfg=cfg, timeout=15)
        return d["text"] if isinstance(d, dict) and isinstance(d.get("text"), str) else "Modell-Rechner: nicht erreichbar\n"
    return journal(unit, n, "short-iso")


def _remote_unit(unit, cfg=None):
    return unit in MODEL_UNITS and remote(cfg)


def unit_state(unit, cfg=None):
    if _remote_unit(unit, cfg):
        u = ((status(cfg) or {}).get("einheiten") or {}).get(unit) or {}
        st = u.get("state")
        return st if isinstance(st, str) and st.replace("-", "").isalpha() and len(st) <= 20 else "unknown"
    out = run(["systemctl", "is-active", unit])[1].split("\n")[0].strip()
    return out if out.replace("-", "").isalpha() and out.islower() else "unknown"


def active_seconds(unit, cfg=None):
    if _remote_unit(unit, cfg):
        u = ((status(cfg) or {}).get("einheiten") or {}).get(unit) or {}
        s = u.get("seit")
        return float(s) if u.get("state") == "active" and isinstance(s, (int, float)) and s >= 0 else None
    code, out = run(["systemctl", "show", unit, "-p", "ActiveState,ActiveEnterTimestampMonotonic"])
    props = dict(x.split("=", 1) for x in out.splitlines() if "=" in x)
    if props.get("ActiveState") != "active":
        return None
    try:
        since = int(props.get("ActiveEnterTimestampMonotonic", "0")) / 1e6
        return time.monotonic() - since if since else None
    except ValueError:
        return None


def systemctl(action, unit, cfg=None, timeout=60):
    """Starts, stops or restarts a unit: here with sudo, a model unit on another computer through the Wärter."""
    if _remote_unit(unit, cfg):
        teil = next((k for k, v in UNITS.items() if v == unit), "")
        d = call("einheit", (action, teil), cfg=cfg, timeout=max(timeout, 130)) if teil else None
        ok = isinstance(d, dict) and d.get("ok") is True
        print(f"steuer: einheit {action} {teil or 'unbekannt'} {'ok' if ok else 'fehler'}", flush=True)
        with _lock:
            _status.update(t=0.0)          # the next status is asked fresh
        return (0, "") if ok else (1, "Modell-Rechner: nicht erreichbar oder abgelehnt")
    return run(["sudo", "-n", "/usr/bin/systemctl", action, unit], timeout=timeout)


def gpu(cfg=None):
    if remote(cfg):
        g = (status(cfg) or {}).get("gpu")
        return g if isinstance(g, dict) else None
    return gpu_stats()
