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
    modelle()                   what Zustand → Modelle needs from the model computer (checked), None without answer
    cached()                    the last status without asking (the Wartungspause reads the model computer's pause)
    weg()                       Notbetrieb: the model computer has not answered for GONE seconds
    stumm_s()                   seconds since it last answered (Zustand → Monitoring → Rechner)
    for_live()                  the Live view's box „Modell-Rechner“: reachable, units active, version, pause
    update_modell_rechner()     its own update first, then this computer's (update.sh: python3 steuer.py update)
    rundlauf()                  after the pairing: Wärter, then TTS speaks a sentence and ASR hears it, through the pin

When the model computer reports other speech settings than the panel's (a hash in its status), they are handed over
again, at most every PUSH seconds: a save while it was away is not lost. Which model runs (common.MODEL_CHOICE) goes
the other way: the model computer reports it in its status and the panel takes it into its own configuration
(checked by common.model_choice_take), so its pages show what really runs.

The status of the model computer is asked at most every CACHE seconds; when it does not answer, its units read
"unknown" and the GPU None, which the pages show as „nicht erreichbar“. Logs ("steuer:" lines) only for actions.
"""
import json
import os
import secrets
import sys
import threading
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # common.py, also as a script
from common import (CONFIG_PATH, OWN_LLM_UNITS, UNITS, gpu_stats, journal, load_config, model_choice, model_choice_take,
                    model_local, model_settings, model_settings_hash, model_url, run, shipped, waerter_key, waerter_sign,
                    write_json)

CACHE = 3              # seconds a status of the model computer is reused
PUSH = 60              # seconds between two hand-overs of the speech settings when the hashes differ
TIMEOUT = 5
MODEL_UNITS = set(UNITS.values()) | set(OWN_LLM_UNITS.values())
_status = {"t": 0.0, "d": None, "push": -PUSH, "wahl": None, "try": 0.0, "ok": 0.0, "weg": False}
GONE = 30              # seconds without an answer of the model computer before the panel runs in Notbetrieb
_lock = threading.Lock()
_client = None         # the self-tests put a client for the Wärter here
UPDATE_WAIT = 2400     # seconds the panel computer's update waits for the model computer's
UPDATE_SEEN = 90       # seconds to see its update start (a quick "nothing new" may be over before)
POLL = 10


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
        _status.update(t=now, d=d, **{"try": now}, **({"ok": now} if d is not None else {}))
        gone, was = now - _status["ok"] > GONE, _status["weg"]
        _status["weg"] = gone
        due = d is not None and d.get("einstellungen") != model_settings_hash(cfg) and now - _status["push"] >= PUSH
        if due:
            _status["push"] = now
    if gone != was:
        print(f"steuer: notbetrieb {'an' if gone else 'aus'}", flush=True)
    if due:
        einstellen(cfg, why="abgleich")
    if d is not None and d.get("modellwahl") != model_choice(cfg):
        modellwahl(cfg, d.get("modellwahl"))
    return d


def modellwahl(cfg, got):
    """Takes the model computer's model choice into this computer's configuration (one line per new report)."""
    seen = json.dumps(got, sort_keys=True)
    with _lock:
        if _status["wahl"] == seen:
            return False
        _status["wahl"] = seen
    try:
        diff = model_choice_take(cfg, got, shipped())
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
        for sec, vals in diff.items():
            raw[sec] = dict(raw.get(sec) or {}, **vals)
        if diff:
            write_json(CONFIG_PATH, raw, indent=2)
    except (ValueError, OSError):
        print("steuer: modellwahl abgelehnt", flush=True)
        return False
    print(f"steuer: modellwahl uebernommen {len(diff)}", flush=True)
    return True


def modelle(cfg=None):
    """Zustand → Modelle from the model computer: {gesamt_gib, lanes, messung, wechsel, eigene, laeuft}, checked;
    None when it does not answer or sends something else."""
    d = call("modelle", cfg=cfg, timeout=15)
    try:
        ok = (isinstance(d, dict) and isinstance(d["gesamt_gib"], (int, float)) and 1 <= d["gesamt_gib"] <= 8192
              and isinstance(d["lanes"], list) and all(isinstance(x, (int, float)) and 0 < x <= 1 for x in d["lanes"])
              and isinstance(d["messung"], dict) and isinstance(d["wechsel"], dict)
              and isinstance(d["eigene"], list) and isinstance(d["laeuft"], bool))
    except KeyError:
        ok = False
    return d if ok else None


def weg(now=None):
    """Notbetrieb (plan Raspberry-Pi split B5): the models run on another computer, it was asked lately and has not
    answered for GONE seconds. Never asks it itself (the pause loop does, every few seconds)."""
    if not remote():
        return False
    now = time.monotonic() if now is None else now
    with _lock:
        tried, ok = _status["try"], _status["ok"]
    return bool(tried) and now - tried < 120 and now - ok > GONE


def stumm_s(now=None):
    """Seconds since the model computer last answered (None before its first answer): Zustand → Monitoring → Rechner."""
    now = time.monotonic() if now is None else now
    with _lock:
        ok = _status["ok"]
    return max(0, int(now - ok)) if ok else None


def cached(max_age=60, now=None):
    """The last status of the model computer without asking it (None when older than max_age seconds): for paths that
    must never wait, like the Wartungspause on every question. The pause loop keeps it fresh (wartung.tick)."""
    now = time.monotonic() if now is None else now
    with _lock:
        d, t = _status["d"], _status["t"]
    return d if d is not None and t and now - t <= max_age else None


def for_live(now=None):
    """Zustand → Live, box „Modell-Rechner“ (only with the models on another computer): kind, counts and status only."""
    if not remote():
        return {"on": False}
    d = cached(now=now)
    if d is None:
        return {"on": True, "ok": False, "notbetrieb": weg(now)}
    units = [u for u in (d.get("einheiten") or {}).values() if isinstance(u, dict) and u.get("state") != "unknown"]
    v = str(d.get("version") or "")
    return {"on": True, "ok": True, "aktiv": sum(u.get("state") == "active" for u in units), "n": len(units),
            "version": v if v.startswith("V") and len(v) <= 20 else "", "pause": bool((d.get("pause") or {}).get("on"))}


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


def update_modell_rechner(cfg=None, sleep=time.sleep, now=time.monotonic):
    """The model computer's own update (its update.sh, its own rules), waited for before the panel computer updates
    itself (plan Raspberry-Pi split B5). True when it ran and ended; the panel's update goes on either way, two
    different versions are only a hint (between panel and models there is only the API)."""
    cfg = load_config() if cfg is None else cfg
    if not remote(cfg):
        return True
    d = call("update", cfg=cfg, timeout=30)
    if not (isinstance(d, dict) and d.get("ok") is True):
        print("steuer: update modell-rechner fehler", flush=True)
        return False
    print("steuer: update modell-rechner angefragt", flush=True)
    t0, seen = now(), False
    while now() - t0 < UPDATE_WAIT:
        sleep(POLL)
        s = call("status", cfg=cfg)
        if not isinstance(s, dict):
            continue                  # restarting its services (and the Wärter itself): ask again
        seen = seen or s.get("update") is True
        if s.get("update") is not True and (seen or now() - t0 >= UPDATE_SEEN):
            v = str(s.get("version") or "")
            v = v if v.startswith("V") and len(v) <= 20 else "-"
            print(f"steuer: update modell-rechner fertig {v}", flush=True)
            with _lock:
                _status.update(t=0.0)
            return True
    print("steuer: update modell-rechner zeitlimit", flush=True)
    return False


RUND_SATZ = "Heute ist ein schöner Tag, und der Spark spricht wieder."
RUND_TIMEOUT = 180     # the first request may wait for a model to load


def rundlauf(cfg=None, client=None):
    """The round trip after the pairing (B6b): the Wärter answers, TTS speaks RUND_SATZ and ASR hears at least 60 % of
    its words, all through the door with the pinned certificate. (ok, the first part that failed or "")."""
    import re
    cfg = load_config() if cfg is None else cfg
    if not remote(cfg):
        return False, "lokal"
    if not isinstance(call("status", cfg=cfg), dict):
        print("steuer: rundlauf fehler waerter", flush=True)
        return False, "waerter"
    key = str((cfg.get("api") or {}).get("key") or "")
    auth = {"Authorization": f"Bearer {key}"} if key else {}
    c = client or httpx.Client(timeout=RUND_TIMEOUT, trust_env=False, follow_redirects=False)
    try:
        r = c.post(model_url("tts", "/v1/audio/speech", cfg), headers=auth,
                   json={"input": RUND_SATZ, "language": "German", "response_format": "wav"})
        if r.status_code != 200 or len(r.content) < 8000:
            print("steuer: rundlauf fehler tts", flush=True)
            return False, "tts"
        r = c.post(model_url("asr", "/v1/audio/transcriptions", cfg), headers=auth,
                   files={"file": ("rundlauf.wav", r.content, "audio/wav")}, data={"language": "German"})
        text = str(r.json().get("text") or "") if r.status_code == 200 else ""
    except (httpx.HTTPError, OSError, ValueError, AttributeError):
        print("steuer: rundlauf fehler verbindung", flush=True)
        return False, "verbindung"
    finally:
        if client is None:
            c.close()
    words = set(re.findall(r"\w+", RUND_SATZ.lower()))
    share = int(100 * len(words & set(re.findall(r"\w+", text.lower()))) / len(words))
    if share < 60:
        print(f"steuer: rundlauf fehler asr {share}", flush=True)
        return False, "asr"
    print(f"steuer: rundlauf ok {share}", flush=True)
    return True, ""


if __name__ == "__main__":
    if sys.argv[1:] == ["update"]:
        update_modell_rechner()
        sys.exit(0)
    if sys.argv[1:] == ["rundlauf"]:
        sys.exit(0 if rundlauf()[0] else 1)
    print("steuer.py update|rundlauf", file=sys.stderr)
    sys.exit(2)
