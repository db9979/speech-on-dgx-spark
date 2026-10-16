"""Zustand → Monitoring → Rechner (Dominik 2026-10-16, Variante 1): when the panel and the models run on two computers
(Spark teilen), both side by side: a tile each on top and a card each under „Rechner“, with curves of the last 20
minutes. On one Spark nothing changes (the page shows what it showed before).

    probe(gpu)        every 3 s from the panel's sampler: measures this computer (rechner.messen), takes the model
                      computer's values from its last status (steuer.cached, the Wärter sends rechner.messen), keeps
                      the curves and checks the warnings
    fuer_status()     /api/status "rechner": both cards (numbers, fixed words, curves, level, warnings)
    alerts()          the warnings for „Braucht dich“ (health.alerts), each with the way to the cards
    for_live()        Zustand → Live: the boxes „Modell-Rechner“ and „Panel-Rechner“, numbers only

The warnings follow fixed rules (never a model): the panel computer TEMP_WARN °C or warmer (back below TEMP_OK),
throttled or under-voltage now (the Raspberry Pi's firmware flags), less than RAM_MIN_GIB available memory; on either
computer less than PLATTE_MIN_PCT % free disk; the model computer not answering (steuer.weg). One log line per
change ("rechner: hinweis <art> an|aus"). The model computer's values are data: only known keys with numbers in
their range are taken, words only from fixed lists.
"""
import os
import sys
import threading
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rechner  # noqa: E402
from common import ON_DEMAND_UNITS, OWN_LLM_UNITS, UNITS, run  # noqa: E402

VERLAUF = 400          # samples per computer, one every 3 s (the sampler): 20 minutes
PUNKTE = 100           # points per curve on the page
FENSTER_S = 1200       # seconds a curve shows (a model computer that answered less often keeps fewer points)
TEMP_WARN, TEMP_OK = 80, 75      # °C of the panel computer (a Raspberry Pi throttles from 85 °C)
PLATTE_MIN_PCT = 10    # % free disk on either computer
RAM_MIN_GIB = 0.5      # GiB available memory on the panel computer (the model computer has its own 8 GiB rule)
DIENSTE_S = 15         # seconds the panel computer's unit states are kept
# the model computer's parts shown as chips (its status "einheiten"), the panel computer's own units
MODELL_TEILE = ("asr", "tts", "llm", "llmtor", "sehen", "bild", "musik")
PANEL_UNITS = {"turn": "speech-spark-turn", "notasr": "speech-spark-notasr", "gehaeuse": "speech-spark-gehaeuse",
               "schirm": "speech-spark-schirm"}
ZAHLEN = {"cpu": (0, 100), "kerne": (0, 4096), "last": (0, 10000), "ram_total": (0, 65536), "ram_frei": (0, 65536),
          "ram_cache": (0, 65536), "ram_pct": (0, 100), "swap": (0, 65536), "platte_total": (0, 1e6),
          "platte_frei": (0, 1e6), "platte_pct": (0, 100), "netz_rx": (0, 1e18), "netz_tx": (0, 1e18),
          "netz_mbit": (0, 1e6), "laeuft_s": (0, 1e10), "temp": (-50, 150), "strom": (0, 2 ** 32), "t": (0, 1e12)}
WORTE = ("name", "geraet", "system")
# the warnings: kind -> (computer, level)
ARTEN = {"heiss": ("panel", "warn"), "drossel": ("panel", "warn"), "strom": ("panel", "bad"), "ram": ("panel", "bad"),
         "platte_panel": ("panel", "warn"), "platte_modell": ("modell", "warn"), "weg": ("modell", "bad")}

_lock = threading.Lock()
_verlauf = {"modell": deque(maxlen=VERLAUF), "panel": deque(maxlen=VERLAUF)}
_letzt = {"modell": None, "panel": None}     # the last measurement of each (checked)
_netz = {"modell": (None, None), "panel": (None, None)}   # MB/s received, sent
_gpu = {}
_dienste = {"t": 0.0, "d": []}
_warn = {}             # kind -> value while the warning is on


def an():
    import steuer
    return steuer.remote()


def pruefen(m):
    """The model computer's measurement as data: known keys only, numbers in range, words of plain characters."""
    if not isinstance(m, dict):
        return None
    out = {}
    for k, (lo, hi) in ZAHLEN.items():
        v = m.get(k)
        out[k] = v if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi else None
    for k in WORTE:
        out[k] = rechner._sauber(m.get(k), 24 if k == "name" else 40) if isinstance(m.get(k), str) else ""
    out["luefter"] = m.get("luefter") if isinstance(m.get("luefter"), bool) else None
    return out


def _rate(alt, neu):
    """MB/s received and sent between two measurements, None without both."""
    try:
        dt = neu["t"] - alt["t"]
        if dt <= 0 or neu["netz_rx"] < alt["netz_rx"] or neu["netz_tx"] < alt["netz_tx"]:
            return None, None
        return round((neu["netz_rx"] - alt["netz_rx"]) / dt / 1e6, 2), round((neu["netz_tx"] - alt["netz_tx"]) / dt / 1e6, 2)
    except (TypeError, KeyError):
        return None, None


def _nehmen(k, m, now, gpu=None):
    with _lock:
        alt = _letzt[k]
        if alt is not None and alt.get("t") == m.get("t"):
            return False                   # the same status again (the Wärter's answer is kept CACHE seconds)
        if alt is not None:
            _netz[k] = _rate(alt, m)
        _letzt[k] = m
        rx, tx = _netz[k]
        _verlauf[k].append({"t": now, "cpu": m.get("cpu"), "frei": m.get("ram_frei"), "temp": m.get("temp"),
                            "netz": round(rx + tx, 2) if rx is not None else None,
                            "gpu": (gpu or {}).get("util") if k == "modell" else None})
    return True


def _gpu_von(d):
    g = d.get("gpu") if isinstance(d, dict) else None
    if not isinstance(g, dict):
        return {}
    return {k: g[k] for k in ("util", "temp", "power")
            if isinstance(g.get(k), (int, float)) and not isinstance(g.get(k), bool) and 0 <= g[k] <= 10000}


def probe(now=None, mono=None):
    """One round of the sampler (only with the models on another computer)."""
    if not an():
        return False
    import steuer
    now = time.time() if now is None else now
    _nehmen("panel", rechner.messen(), now)
    d = steuer.cached(now=mono)
    m = pruefen((d or {}).get("rechner"))
    if m is not None:
        g = _gpu_von(d)
        with _lock:
            _gpu.clear()
            _gpu.update(g)
        _nehmen("modell", m, now, g)
    warnungen(mono)
    return True


def _setzen(art, wert):
    with _lock:
        war = art in _warn
        if wert is None:
            _warn.pop(art, None)
        else:
            _warn[art] = wert
    if war != (wert is not None):
        print(f"rechner: hinweis {art} {'an' if wert is not None else 'aus'}", flush=True)


def warnungen(mono=None):
    """The fixed rules over the last values (one log line per change)."""
    import steuer
    with _lock:
        p, m = dict(_letzt["panel"] or {}), dict(_letzt["modell"] or {})
        heiss = "heiss" in _warn
    t = p.get("temp")
    _setzen("heiss", t if t is not None and (t >= TEMP_WARN or heiss and t >= TEMP_OK) else None)
    flags = p.get("strom")
    _setzen("drossel", True if flags is not None and flags & 0x4 else None)
    _setzen("strom", True if flags is not None and flags & 0x1 else None)
    frei = p.get("ram_frei")
    _setzen("ram", frei if frei is not None and frei < RAM_MIN_GIB else None)
    for art, x in (("platte_panel", p), ("platte_modell", m)):
        pct = x.get("platte_pct")
        _setzen(art, (x.get("platte_frei"), pct) if pct is not None and 100 - pct < PLATTE_MIN_PCT else None)
    _setzen("weg", steuer.stumm_s(mono) if steuer.weg(mono) else None)


def alerts():
    """The warnings for „Braucht dich“: fixed sentences with numbers, the way to the cards."""
    if not an():
        return []
    with _lock:
        w = dict(_warn)
    texte = {
        "heiss": lambda v: f"Der Panel-Rechner ist {v:.0f} °C warm (Hinweis ab {TEMP_WARN} °C, ein Raspberry Pi drosselt ab 85 °C).",
        "drossel": lambda v: "Der Panel-Rechner drosselt gerade: zu warm oder zu wenig Strom.",
        "strom": lambda v: "Der Panel-Rechner bekommt zu wenig Strom: Netzteil oder Kabel sind zu schwach.",
        "ram": lambda v: f"Der Panel-Rechner hat nur noch {v:.1f} GiB Arbeitsspeicher frei.",
        "platte_panel": lambda v: f"Auf dem Panel-Rechner sind nur noch {v[0]:g} GB frei ({v[1]:.0f} % belegt).",
        "platte_modell": lambda v: f"Auf dem Modell-Rechner sind nur noch {v[0]:g} GB frei ({v[1]:.0f} % belegt).",
        "weg": lambda v: f"Der Modell-Rechner antwortet seit {max(1, round((v or 0) / 60))} min nicht: Notbetrieb.",
    }
    return [{"kind": "rechner", "level": ARTEN[a][1], "go": "Zustand → Monitoring → Rechner", "text": texte[a](v)}
            for a, v in w.items() if a in texte]


def _dienste_panel(now):
    """The panel computer's own units that are installed: the panel itself, TURN, Notbetrieb, Gehäuse."""
    with _lock:
        if now - _dienste["t"] < DIENSTE_S:
            return list(_dienste["d"])
    out = [{"id": "panel", "state": "active"}]
    code, txt = run(["systemctl", "show", *PANEL_UNITS.values(), "-p", "Id,ActiveState,LoadState"])
    seen = {}
    for block in txt.split("\n\n") if code == 0 else []:
        props = dict(x.split("=", 1) for x in block.splitlines() if "=" in x)
        seen[props.get("Id", "").removesuffix(".service")] = props
    for teil, unit in PANEL_UNITS.items():
        props = seen.get(unit) or {}
        st = props.get("ActiveState", "")
        if props.get("LoadState") == "loaded" and st.replace("-", "").isalpha() and len(st) <= 20:
            out.append({"id": teil, "state": st})
    with _lock:
        _dienste.update(t=now, d=out)
    return out


def _dienste_modell(d):
    units = (d or {}).get("einheiten") or {}
    out = []
    for teil in MODELL_TEILE:
        st = (units.get(UNITS.get(teil) or OWN_LLM_UNITS.get(teil) or ON_DEMAND_UNITS.get(teil)) or {}).get("state")
        if isinstance(st, str) and st != "unknown" and st.replace("-", "").isalpha() and len(st) <= 20:
            out.append({"id": teil, "state": st})
    return out + ([{"id": "waerter", "state": "active"}] if d else [])


def kurven(k):
    with _lock:
        v = list(_verlauf[k])
    v = [x for x in v if x["t"] >= v[-1]["t"] - FENSTER_S] if v else v
    v = v[::max(1, -(-len(v) // PUNKTE))]
    keys = ("cpu", "frei", "temp", "netz") + (("gpu",) if k == "modell" else ())
    return {key: [x.get(key) for x in v] for key in keys}


def karte(k, now=None, mono=None):
    """One computer's card: numbers, fixed words, curves, level and its warnings (kinds)."""
    import steuer
    now = time.time() if now is None else now
    with _lock:
        m = dict(_letzt[k] or {})
        rx, tx = _netz[k]
        w = {a for a in _warn if ARTEN.get(a, ("", ""))[0] == k}
        gpu = dict(_gpu)
    out = {"id": k, **{x: m.get(x) for x in (*ZAHLEN, *WORTE, "luefter") if x not in ("t", "netz_rx", "netz_tx", "strom")},
           "netz_rx_mbs": rx, "netz_tx_mbs": tx, "hinweise": sorted(w), "kurven": kurven(k)}
    flags = m.get("strom")
    out["strom"] = None if flags is None else dict(zip(("spannung", "drossel"), rechner.strom_worte(flags)))
    if k == "modell":
        d = steuer.cached(now=mono)
        v = str((d or {}).get("version") or "")
        llm = (((d or {}).get("modellwahl") or {}).get("llm") or {})
        out.update(ok=d is not None and not steuer.weg(mono), stumm_s=steuer.stumm_s(mono), gpu=gpu,
                   version=v if v.startswith("V") and len(v) <= 20 else "",
                   llm=rechner._sauber(str(llm.get("modell") or "").rsplit("/", 1)[-1], 40) if llm.get("enabled", True) else "",
                   dienste=_dienste_modell(d))
    else:
        from core import app_version
        out.update(ok=bool(m), stumm_s=None, version=app_version(), temp_warn=TEMP_WARN,
                   dienste=_dienste_panel(time.monotonic() if mono is None else mono))
    lv = {ARTEN[a][1] for a in w}
    out["stufe"] = "bad" if "bad" in lv or not out["ok"] else "warn" if "warn" in lv else "ok"
    return out


def fuer_status(now=None, mono=None):
    """/api/status "rechner": {"an": False} on one Spark, else both cards (the model computer first)."""
    if not an():
        return {"an": False}
    return {"an": True, "liste": [karte("modell", now, mono), karte("panel", now, mono)]}


def for_live():
    """Zustand → Live: the boxes „Modell-Rechner“ and „Panel-Rechner“, numbers only (no name, no address)."""
    if not an():
        return {"on": False}
    with _lock:
        p, m, g = dict(_letzt["panel"] or {}), dict(_letzt["modell"] or {}), dict(_gpu)
    belegt = (p["ram_total"] - p["ram_frei"]) if p.get("ram_total") is not None and p.get("ram_frei") is not None else None
    return {"on": True, "panel": {"cpu": p.get("cpu"), "belegt": belegt, "total": p.get("ram_total"), "temp": p.get("temp"),
                                  "platte": p.get("platte_pct")},
            "modell": {"gpu": g.get("util"), "frei": m.get("ram_frei"), "cpu": m.get("cpu")}}
