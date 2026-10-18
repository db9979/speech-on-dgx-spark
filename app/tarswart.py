"""Wärter (plan Raspberry-Pi split, B4): the model computer's few hands for a panel on another computer.

When the panel runs on a Raspberry Pi, it can no longer call systemctl or nvidia-smi for the models itself. This
small service on the DGX does it for it, with a fixed list of commands and nothing else: no shell, no free unit
names, no paths. It listens on 127.0.0.1:WAERTER_PORT only; the panel reaches it through the TLS-Tor (TLS 1.3,
pinned certificate, only the panel computer, tlstor.py) and signs every request with the Wärter key from the pairing
(STATE/waerter.key, not the API key, which other devices know too): HMAC-SHA256 over the exact body, which carries
a time (at most WINDOW seconds off) and a one-time number (each is taken once).

    status                      version, state and uptime of the model units, GPU, free memory, settings hash,
                                the model choice (common.MODEL_CHOICE: which model runs is this computer's), its
                                Wartungspause (speech-spark pause, modelle messen: the panel pauses those parts too),
                                this computer's values for Zustand → Monitoring → Rechner (rechner.messen)
    einheit <start|stop|restart> <teil>   only parts of common.UNITS (speech and its engines)
    einstellen {settings}       the panel's speech settings (common.model_settings_take: known keys, same kind,
                                never addresses, ports or backends, model ids only Qwen's)
    logs <teil> <n>             the last n (at most MAX_LINES) log lines of a model unit
    modelle                     what Zustand → Modelle needs from here: memory, qwen38 lanes, measurement, switches,
                                own models, whether a switch or a measurement runs
    wechseln <art> <id|zurueck> a switch with the fixed rules (modelle.wechsel_anfragen), then speech-spark-wechsel
    messen <id>                 Zustand → Modelle „Messen“ (modelle.messen_anfragen), then speech-spark-messen-wunsch
    eigen_dazu {entry}          an own model (modelle.eigen_speichern checks it again)
    eigen_weg <id>              an own model off the list and its files off the disk (modelle.eigen_loeschen)
    weiter                      ends this computer's Wartungspause ("Weiter" on the panel)
    update                      starts this computer's own update (speech-spark-update with its own rules: the newest
                                version with passed GitHub tests, never a version the panel names)
    werkstatt                   what Funktionen → Werkstatt needs from here (werkstatt.daten: results without patches)
    werkstatt_auftrag {art, text}   an order with the fixed rules (werkstatt.anfragen), then speech-spark-werkstatt
    werkstatt_eins <id>         one order with its text and patch
    werkstatt_weg <id>          deletes one order

Every action writes one log line ("waerter:" with the command and the result word, never content); the reads
status and modelle only when refused.
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

import llmstart
import modelle
import rechner
import werkstatt
from common import (CONFIG_PATH, ON_DEMAND_UNITS, OWN_LLM_UNITS, UNITS, WAERTER_PORT, BodyLimit, gpu_stats, journal, load_config,
                    WARTUNG_FILE, installed_version, mem_available_gib, model_choice, model_settings_hash, model_settings_take, qwen38_lanes, read_json,
                    run, shipped, waerter_key, waerter_sign, write_json)

WINDOW = 60            # seconds a request's time may be off
MAX_BODY = 64 * 1024     # the speech settings (pronunciation, context) fit easily
MAX_LINES = 2000
MAX_SEEN = 5000        # one-time numbers kept (each lives WINDOW * 2 seconds)
RATE = (40, 10)        # at most 40 requests in 10 seconds (the panel asks for the status every few seconds)
ACTIONS = ("start", "stop", "restart")
COMMANDS = ("status", "einheit", "einstellen", "logs", "modelle", "wechseln", "messen", "platz", "eigen_dazu", "eigen_weg",
            "weiter", "update", "werkstatt", "werkstatt_auftrag", "werkstatt_eins", "werkstatt_weg")
UPDATE_UNIT = "speech-spark-update"
PAUSE_KEYS = ("on", "parts", "since", "until", "channel")   # what the panel needs of the pause (never who)
WITH_DATA = ("einstellen", "eigen_dazu", "werkstatt_auftrag")
# what status reports: the units the panel shows and watches
WATCHED = dict(UNITS, **OWN_LLM_UNITS, **ON_DEMAND_UNITS)

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
        got[unit] = {"state": state, "seit": round(time.monotonic() - t) if state == "active" and t else None,
                     "eintritt": int(t * 1e6)}
    return {u: got.get(u, {"state": "unknown", "seit": None, "eintritt": 0}) for u in units}


def pause():
    """This computer's Wartungspause as the file says (only PAUSE_KEYS); the panel checks it (wartung._clean).
    No panel here ends it after its time (wartung.tick), so the Wärter drops a pause whose time is over."""
    d = read_json(WARTUNG_FILE, {})
    if isinstance(d, dict) and d.get("on") is True and isinstance(d.get("until"), (int, float)) and d["until"] <= time.time():
        try:
            os.remove(WARTUNG_FILE)
            print("waerter: pause abgelaufen", flush=True)
        except OSError:
            print("waerter: pause abgelaufen fehler", flush=True)
        return {}
    return {k: d[k] for k in PAUSE_KEYS if k in d} if isinstance(d, dict) and d.get("on") is True else {}


def _update_laeuft():
    return modelle.im_gang(run(["systemctl", "is-active", UPDATE_UNIT])[1])


def update():
    ok = run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", UPDATE_UNIT], timeout=20)[0] == 0
    print(f"waerter: update {'angefragt' if ok else 'fehler'}", flush=True)
    return {"ok": ok}


def weiter():
    try:
        os.remove(WARTUNG_FILE)
        print("waerter: weiter ok", flush=True)
        return {"ok": True, "war": True}
    except FileNotFoundError:
        print("waerter: weiter keine", flush=True)
        return {"ok": True, "war": False}


def status():
    try:
        mem, total = round(mem_available_gib(), 1), round(mem_available_gib("MemTotal"), 1)
    except OSError:
        mem = total = None
    cfg = load_config()
    return {"version": version(), "einheiten": _states(list(WATCHED.values())), "gpu": gpu_stats(),
            "mem_avail_gib": mem, "mem_total_gib": total, "einstellungen": model_settings_hash(cfg), "modellwahl": model_choice(cfg), "pause": pause(),
            "commit": str(installed_version().get("commit") or "")[:40], "update": _update_laeuft(), "rechner": _rechner()}


def _rechner():
    """This computer's values for Zustand → Monitoring → Rechner (rechner.messen): numbers and fixed words only."""
    try:
        return rechner.messen()
    except Exception as e:
        print("waerter: rechner", type(e).__name__, flush=True)
        return None


def einstellen(daten):
    """Takes the panel's speech settings into this computer's config (atomic write); returns the new hash."""
    cfg = load_config()
    try:
        new = model_settings_take(cfg, daten, shipped())
    except ValueError as e:
        print(f"waerter: einstellen abgelehnt {e}", flush=True)
        raise ValueError("befehl")
    with open(CONFIG_PATH) as f:
        raw = json.load(f)
    for sec in daten:
        raw[sec] = dict(raw.get(sec) or {}, **{k: new[sec][k] for k in daten[sec]})
    write_json(CONFIG_PATH, raw, indent=2)
    print("waerter: einstellen ok", flush=True)
    return {"ok": True, "einstellungen": model_settings_hash(load_config())}


def logs(teil, n):
    if teil not in WATCHED or not str(n).isdigit() or not 1 <= int(n) <= MAX_LINES:
        raise ValueError("befehl")
    print(f"waerter: logs {teil}", flush=True)
    return {"text": journal(WATCHED[teil], int(n), "short-iso")[-400_000:]}


def _wechsel_laeuft():
    return modelle.im_gang(run(["systemctl", "is-active", modelle.WECHSEL_UNIT])[1])


def _misst():
    """The unit of a running measurement (the command line's or the one for the panel's „Messen“), "" when none."""
    units = (modelle.MESS_UNIT, modelle.MESS_WUNSCH_UNIT)
    zeilen = run(["systemctl", "is-active", *units])[1].splitlines()
    return next((u for u, z in zip(units, zeilen) if modelle.im_gang(z)), "")


def modelle_daten():
    """Read only, asked by the page and the Live view: no line, like status."""
    messung = read_json(modelle.MESSUNG, {})
    return {"gesamt_gib": round(modelle.gesamt_gib(), 1), "lanes": [f for _, f in qwen38_lanes() if f],
            "messung": messung, "wechsel": read_json(modelle.WECHSEL, {}),
            "eigene": modelle.eigene(), "laeuft": _wechsel_laeuft(), **_messung_laeuft(),
            "start": llmstart.hier(load_config(), messung)}     # what the language model does while it starts


def _messung_laeuft():
    """misst, and while it runs its last progress lines (fixed words and numbers, modelle.stand)."""
    unit = _misst()
    return {"misst": bool(unit), "stand": modelle.stand(journal(unit, 60)) if unit else []}


def wechseln(art, was):
    if art not in modelle.TAUSCH or not (was == "zurueck" or modelle.ID.match(was)):
        raise ValueError("befehl")

    def starten():
        return run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", modelle.WECHSEL_UNIT], timeout=20)[0] == 0
    if _misst():
        print("waerter: wechseln abgelehnt misst", flush=True)
        return {"ok": False, "fehler": "misst"}
    try:
        m = modelle.wechsel_anfragen(art, was, load_config(), modelle.gesamt_gib(), [f for _, f in qwen38_lanes() if f],
                                     starten, _wechsel_laeuft())
    except modelle.Fehler as e:
        print(f"waerter: wechseln abgelehnt {e}", flush=True)
        return {"ok": False, "fehler": str(e)}
    print(f"waerter: wechseln {art} ok", flush=True)
    return {"ok": True, "name": m["name"]["de"]}


def platz(was):
    """Zustand → Modelle „Lange Gespräche“: the rule (modelle.platz_anfragen) with this computer's settings, the wish,
    then speech-spark-wechsel restarts the language model with it."""
    if was not in modelle.PLATZ:
        raise ValueError("befehl")

    def starten():
        return run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", modelle.WECHSEL_UNIT], timeout=20)[0] == 0
    if _misst():
        print("waerter: platz abgelehnt misst", flush=True)
        return {"ok": False, "fehler": "misst"}
    try:
        modelle.platz_anfragen(was, load_config(), modelle.gesamt_gib(), [f for _, f in qwen38_lanes() if f], starten,
                               _wechsel_laeuft())
    except modelle.Fehler as e:
        print(f"waerter: platz abgelehnt {e}", flush=True)
        return {"ok": False, "fehler": str(e)}
    print("waerter: platz ok", flush=True)
    return {"ok": True}


def messen(mid):
    """Zustand → Modelle „Messen“: the rule (modelle.messen_anfragen), the wish, then speech-spark-messen-wunsch."""
    if not modelle.ID.match(mid):
        raise ValueError("befehl")

    def starten():
        return run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", modelle.MESS_WUNSCH_UNIT], timeout=20)[0] == 0
    try:
        m = modelle.messen_anfragen(mid, starten, bool(_misst()) or _wechsel_laeuft())
    except modelle.Fehler as e:
        print(f"waerter: messen abgelehnt {e}", flush=True)
        return {"ok": False, "fehler": str(e)}
    print("waerter: messen ok", flush=True)
    return {"ok": True, "name": m["name"]["de"]}


def eigen_dazu(m):
    try:
        modelle.eigen_speichern(m)
    except (modelle.Fehler, KeyError, TypeError, AttributeError) as e:
        word = str(e) if isinstance(e, modelle.Fehler) else "eigen"
        print(f"waerter: eigen_dazu abgelehnt {word}", flush=True)
        return {"ok": False, "fehler": word}
    print("waerter: eigen_dazu ok", flush=True)
    return {"ok": True}


def eigen_weg(mid):
    if not modelle.ID.match(mid):
        raise ValueError("befehl")
    try:
        weg = modelle.ordner_weg(modelle.eigen_loeschen(mid, load_config()))
    except modelle.Fehler as e:
        print(f"waerter: eigen_weg abgelehnt {e}", flush=True)
        return {"ok": False, "fehler": str(e)}
    except OSError:
        print("waerter: eigen_weg dateien fehler", flush=True)
        return {"ok": False, "fehler": "dateien"}
    print("waerter: eigen_weg ok", flush=True)
    return {"ok": True, "dateien": weg}


def _werkstatt_laeuft():
    return werkstatt.im_gang(run(["systemctl", "is-active", werkstatt.UNIT, werkstatt.LAUF_UNIT])[1])


def werkstatt_daten():
    """Read only, asked by the page and the Live view: no line, like status."""
    laeuft = _werkstatt_laeuft()
    return werkstatt.daten(laeuft, werkstatt.stand(journal(werkstatt.UNIT, 60)) if laeuft else [])


def werkstatt_auftrag(daten):
    def starten():
        return run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", werkstatt.UNIT], timeout=20)[0] == 0
    try:
        art = werkstatt.anfragen(daten.get("art"), daten.get("text", ""), starten, _werkstatt_laeuft())
    except werkstatt.Fehler as e:
        print(f"waerter: werkstatt abgelehnt {e}", flush=True)
        return {"ok": False, "fehler": str(e)}
    print(f"waerter: werkstatt {art} ok", flush=True)
    return {"ok": True}


def werkstatt_eins(aid):
    a = werkstatt.eins(aid)
    print(f"waerter: werkstatt_eins {'ok' if a else 'keins'}", flush=True)
    return {"ok": bool(a), "auftrag": a}


def werkstatt_weg(aid):
    ok = werkstatt.weg(aid)
    print(f"waerter: werkstatt_weg {'ok' if ok else 'keins'}", flush=True)
    return {"ok": ok}


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
    cmd, args, daten = d.get("cmd"), d.get("args") or [], d.get("daten")
    if cmd not in COMMANDS or not isinstance(args, list) or not all(isinstance(a, str) for a in args) \
            or (cmd in WITH_DATA) != isinstance(daten, dict):
        raise ValueError("befehl")
    return cmd, args, daten


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
        cmd, args, daten = check(raw, request.headers.get("x-wart", ""), waerter_key(), now)
    except ValueError as e:
        print(f"waerter: abgelehnt {e}", flush=True)
        raise HTTPException(403 if str(e) != "befehl" else 400, str(e))
    if cmd == "status":       # asked every few seconds: no line for a good answer, only for refusals
        return JSONResponse(status())
    if cmd == "modelle":
        return JSONResponse(modelle_daten())
    if cmd == "werkstatt":
        return JSONResponse(werkstatt_daten())
    try:
        if cmd == "einstellen":
            return JSONResponse(einstellen(daten))
        if cmd == "eigen_dazu":
            return JSONResponse(eigen_dazu(daten))
        if cmd == "werkstatt_auftrag":
            return JSONResponse(werkstatt_auftrag(daten))
        if cmd in ("werkstatt_eins", "werkstatt_weg"):
            one = werkstatt_eins if cmd == "werkstatt_eins" else werkstatt_weg
            return JSONResponse(one(*args) if len(args) == 1 else one(""))
        if cmd == "weiter":
            return JSONResponse(weiter())
        if cmd == "update":
            return JSONResponse(update())
        if cmd == "eigen_weg":
            return JSONResponse(eigen_weg(*args) if len(args) == 1 else eigen_weg(""))
        if cmd == "messen":
            return JSONResponse(messen(*args) if len(args) == 1 else messen(""))
        if cmd == "platz":
            return JSONResponse(platz(*args) if len(args) == 1 else platz(""))
        two = {"logs": logs, "wechseln": wechseln, "einheit": einheit}[cmd]
        return JSONResponse(two(*args) if len(args) == 2 else two("", ""))
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
