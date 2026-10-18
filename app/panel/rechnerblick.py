"""Zustand → Monitoring → Rechner (Dominik 2026-10-16, Variante 1): when the panel and the models run on two computers
(Spark teilen), both side by side: a tile each on top and a card each under „Rechner“, with curves of the last 20
minutes. On one Spark nothing changes (the page shows what it showed before).

    probe(gpu)        every 3 s from the panel's sampler: measures this computer (rechner.messen), takes the model
                      computer's values from its last status (steuer.cached, the Wärter sends rechner.messen), keeps
                      the curves and checks the warnings
    fuer_status()     /api/status "rechner": both cards (numbers, fixed words, curves, level, warnings; the panel
                      computer's card also the stalls of the panel's loop, loopwacht.view)
    alerts()          the warnings for „Braucht dich“ (health.alerts), each with the way to the cards
    for_live()        Zustand → Live: the boxes „Modell-Rechner“ and „Panel-Rechner“, numbers only

„Wer rechnet gerade“ (Dominik 2026-10-18 „1a 2a 3a 4b“): each card lists the services by their share of the
computer's CPU (rechner.dienste_cpu, systemd's counters), the panel with its parts (rechenteile.py), and the rest of
the system; „spitze“ names the biggest for the tile, Live and the Steuerzentrale, the curve „top“ keeps it every 3 s
for the strip of the last 20 minutes (below LEERLAUF_PCT nobody: idle). Names come only from DIENST_NAMEN and
TEIL_NAMEN (de/en, also for the chips „Dienste“), the model computer's ids are data like its other values.

The warnings follow fixed rules (never a model): the panel computer TEMP_WARN °C or warmer (back below TEMP_OK),
throttled or under-voltage now (the Raspberry Pi's firmware flags), less than RAM_MIN_GIB available memory; on either
computer less than PLATTE_MIN_PCT % free disk; the model computer not answering (steuer.weg). One log line per
change ("rechner: hinweis <art> an|aus"). The model computer's values are data: only known keys with numbers in
their range are taken, words only from fixed lists.
"""
import os
import re
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
MODELL_TEILE = ("asr", "tts", "llm", "llmtor", "sehen", "bild", "musik", "werkstatt")
PANEL_UNITS = {"turn": "speech-spark-turn", "notasr": "speech-spark-notasr", "gehaeuse": "speech-spark-gehaeuse",
               "schirm": "speech-spark-schirm"}
ZAHLEN = {"cpu": (0, 100), "kerne": (0, 4096), "last": (0, 10000), "ram_total": (0, 65536), "ram_frei": (0, 65536),
          "ram_cache": (0, 65536), "ram_pct": (0, 100), "swap": (0, 65536), "platte_total": (0, 1e6),
          "platte_frei": (0, 1e6), "platte_pct": (0, 100), "netz_rx": (0, 1e18), "netz_tx": (0, 1e18),
          "netz_mbit": (0, 1e6), "laeuft_s": (0, 1e10), "temp": (-50, 150), "strom": (0, 2 ** 32), "t": (0, 1e12)}
WORTE = ("name", "geraet", "system")
LEERLAUF_PCT = 5       # % of the whole CPU: below it the biggest service does not count as working (grey in the strip)
ZEILEN = 6             # services listed per card, the others count for the rest
REST_MIN = 0.5         # % below which no rest line is shown
DIENST_ID = re.compile(r"[a-z][a-z0-9-]{0,23}")
# the services' names (de, en): the ids rechner.dienste_cpu gives (speech-spark-<id>.service, qwen38, docker) and the
# chips „Dienste“; an unknown own unit shows its id
DIENST_NAMEN = {"asr": ("Spracherkennung", "Speech recognition"), "asr-engine": ("Spracherkennung (Engine)", "Speech recognition (engine)"),
                "tts": ("Sprachausgabe", "Speech output"), "tts-engine": ("Sprachausgabe (Engine)", "Speech output (engine)"),
                "tts-design": ("Stimmen gestalten", "Voice design"), "llm": ("Sprachmodell", "Language model"),
                "llmtor": ("LLM-Tor", "LLM-Tor"), "sehen": ("Bildverständnis", "Image understanding"),
                "bild": ("Bilder malen", "Painting pictures"), "musik": ("Musik machen", "Making music"),
                "werkstatt": ("Werkstatt", "Werkstatt"), "waerter": ("Wärter", "Wärter"), "panel": ("Panel", "Panel"),
                "turn": ("Anrufe (TURN)", "Calls (TURN)"), "notasr": ("Notbetrieb-Erkennung", "Emergency recognition"),
                "gehaeuse": ("Gehäuse", "Case"), "schirm": ("Steuerzentrale", "Control centre"), "tlstor": ("TLS-Tor", "TLS gate"),
                "watch": ("API-Wächter", "API watchdog"), "update": ("Update", "Update"), "wechsel": ("Modellwechsel", "Model switch"),
                "messen-wunsch": ("Modelle messen", "Measuring models"), "qwen38": ("qwen38", "qwen38"),
                "docker": ("Modell in Docker", "Model in Docker"), "rest": ("System und Rest", "System and rest")}
# the parts inside the panel (rechenteile.py); a background job („bg:<job>“) shows its fixed name from the code
TEIL_NAMEN = {"anfragen": ("Anfragen und Seiten", "Requests and pages"), "bedeutungssuche": ("Bedeutungssuche", "Meaning search"),
              "nachsortieren": ("Nachsortieren", "Re-ranking"), "auslassen": ("Ordner auslassen", "Leaving out folders"),
              "loopwacht": ("Hänge-Wächter", "Stall watch"), "aufraeumen": ("Chat löschen", "Deleting a chat"),
              "weitere": ("Weitere Threads", "Other threads"), "uebrig": ("Kurze Programme und Rest", "Short programs and rest")}
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
    d = m.get("dienste_cpu")
    out["dienste_cpu"] = {k: v for k, v in list(d.items())[:rechner.DIENSTE_MAX]
                          if isinstance(k, str) and DIENST_ID.fullmatch(k) and isinstance(v, (int, float))
                          and not isinstance(v, bool) and 0 <= v <= 100} if isinstance(d, dict) else None
    return out


def _name(namen, i):
    if i.startswith("bg:"):
        return {"name": i[3:], "en": i[3:]}
    de, en = namen.get(i, (i, i))
    return {"name": de, "en": en}


def rechnen(k, m):
    """„Wer rechnet gerade“: the biggest services first (at most ZEILEN), the panel with its parts, then the rest of
    the computer's CPU; [] while not measured (first round, an older Wärter)."""
    d = (m or {}).get("dienste_cpu")
    if not isinstance(d, dict):
        return []
    liste = [{"id": i, **_name(DIENST_NAMEN, i), "pct": v} for i, v in sorted(d.items(), key=lambda x: -x[1])[:ZEILEN]]
    teile = m.get("teile") if k == "panel" else None
    for x in liste:
        if x["id"] == "panel" and isinstance(teile, dict):
            x["teile"] = [{"id": i, **_name(TEIL_NAMEN, i), "pct": v} for i, v in teile.items()]
            uebrig = round(x["pct"] - sum(teile.values()), 1)
            if uebrig >= REST_MIN:
                x["teile"].append({"id": "uebrig", **_name(TEIL_NAMEN, "uebrig"), "pct": uebrig})
    cpu = m.get("cpu")
    rest = round(cpu - sum(x["pct"] for x in liste), 1) if isinstance(cpu, (int, float)) else None
    if rest is not None and rest >= REST_MIN:
        liste.append({"id": "rest", **_name(DIENST_NAMEN, "rest"), "pct": rest})
    return liste


def spitze(k, m):
    """The biggest service (the panel: its biggest part) when it takes at least LEERLAUF_PCT % of the CPU, else None."""
    liste = [x for x in rechnen(k, m) if x["id"] != "rest"]
    if not liste or liste[0]["pct"] < LEERLAUF_PCT:
        return None
    x = liste[0]
    t = max(x.get("teile") or [], key=lambda y: y["pct"], default=None)
    if t is None:
        return {"id": x["id"], "name": x["name"], "en": x["en"], "pct": x["pct"]}
    return {"id": "panel/" + t["id"], "name": "Panel · " + t["name"], "en": "Panel · " + t["en"], "pct": t["pct"]}


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
        sp = spitze(k, m)
        _verlauf[k].append({"t": now, "cpu": m.get("cpu"), "frei": m.get("ram_frei"), "temp": m.get("temp"),
                            "netz": round(rx + tx, 2) if rx is not None else None,
                            "gpu": (gpu or {}).get("util") if k == "modell" else None,
                            "top": sp and sp["id"], "top_name": sp and (sp["name"], sp["en"])})
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
    import rechenteile
    p = rechner.messen()
    p["teile"] = rechenteile.messen()        # the parts inside the panel (only this computer)
    _nehmen("panel", p, now)
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
    out = [{"id": "panel", "state": "active", **_name(DIENST_NAMEN, "panel")}]
    code, txt = run(["systemctl", "show", *PANEL_UNITS.values(), "-p", "Id,ActiveState,LoadState"])
    seen = {}
    for block in txt.split("\n\n") if code == 0 else []:
        props = dict(x.split("=", 1) for x in block.splitlines() if "=" in x)
        seen[props.get("Id", "").removesuffix(".service")] = props
    for teil, unit in PANEL_UNITS.items():
        props = seen.get(unit) or {}
        st = props.get("ActiveState", "")
        if props.get("LoadState") == "loaded" and st.replace("-", "").isalpha() and len(st) <= 20:
            out.append({"id": teil, "state": st, **_name(DIENST_NAMEN, teil)})
    with _lock:
        _dienste.update(t=now, d=out)
    return out


def _dienste_modell(d):
    units = (d or {}).get("einheiten") or {}
    out = []
    for teil in MODELL_TEILE:
        st = (units.get(UNITS.get(teil) or OWN_LLM_UNITS.get(teil) or ON_DEMAND_UNITS.get(teil)) or {}).get("state")
        if isinstance(st, str) and st != "unknown" and st.replace("-", "").isalpha() and len(st) <= 20:
            out.append({"id": teil, "state": st, **_name(DIENST_NAMEN, teil)})
    return out + ([{"id": "waerter", "state": "active", **_name(DIENST_NAMEN, "waerter")}] if d else [])


def kurven(k):
    with _lock:
        v = list(_verlauf[k])
    v = [x for x in v if x["t"] >= v[-1]["t"] - FENSTER_S] if v else v
    v = v[::max(1, -(-len(v) // PUNKTE))]
    keys = ("cpu", "frei", "temp", "netz", "top") + (("gpu",) if k == "modell" else ())
    return {key: [x.get(key) for x in v] for key in keys}


def namen(k):
    """The names (de, en) of the ids in the strip „top“ of the last 20 minutes."""
    with _lock:
        v = list(_verlauf[k])
    return {x["top"]: list(x["top_name"]) for x in v if x.get("top") and x.get("top_name")}


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
           "netz_rx_mbs": rx, "netz_tx_mbs": tx, "hinweise": sorted(w), "kurven": kurven(k),
           "rechnen": rechnen(k, m), "spitze": spitze(k, m), "namen": namen(k)}
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
        import loopwacht
        out.update(ok=bool(m), stumm_s=None, version=app_version(), temp_warn=TEMP_WARN,
                   dienste=_dienste_panel(time.monotonic() if mono is None else mono),
                   haenger=loopwacht.view(now))   # the Hänge-Wächter: stalls of the panel's loop, numbers only
    lv = {ARTEN[a][1] for a in w}
    out["stufe"] = "bad" if "bad" in lv or not out["ok"] else "warn" if "warn" in lv else "ok"
    return out


def last(k):
    """The last CPU and RAM load of one computer in % ("modell" or "panel"), None where not measured yet: the OLED
    pages "Pi" and "TARS" (gehaeuse.py, Dominik 2026-10-17 "1a")."""
    with _lock:
        m = dict(_letzt.get(k) or {})
    tot, frei = m.get("ram_total"), m.get("ram_frei")
    ram = round(100 * (tot - frei) / tot) if isinstance(tot, (int, float)) and isinstance(frei, (int, float)) and tot > 0 else None
    return {"cpu": m.get("cpu"), "ram": ram}


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
    import loopwacht
    return {"on": True, "panel": {"cpu": p.get("cpu"), "belegt": belegt, "total": p.get("ram_total"), "temp": p.get("temp"),
                                  "platte": p.get("platte_pct"), "haenger": loopwacht.view()["n"], "spitze": spitze("panel", p)},
            "modell": {"gpu": g.get("util"), "frei": m.get("ram_frei"), "cpu": m.get("cpu"), "spitze": spitze("modell", m)}}
