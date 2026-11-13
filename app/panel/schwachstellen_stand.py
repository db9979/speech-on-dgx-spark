"""Schwachstellen, the stored result and its counts (schwachstellen.py checks, this one only reads): kept apart so
Live and the note on top (live.py, health.py) read the counts without importing the check and its routes
(test_schichten: no new module joins the big import cycle). Counts and fixed words only, never a package name.

    STATE/schwachstellen.json  written by schwachstellen.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import STATE, read_json  # noqa: E402

LIVE_CACHE = 10
_live_cache = [0.0, None]


def _file():
    return os.path.join(STATE, "schwachstellen.json")


def _read():
    d = read_json(_file(), {})
    if not isinstance(d, dict):
        d = {}
    for k, empty in (("funde", []), ("n", {}), ("seit", {}), ("hingenommen", {}), ("gemeldet", {})):
        if not isinstance(d.get(k), type(empty)):
            d[k] = empty
    return d


def hingenommen(d, f, now=None):
    """True while the admin accepted this finding knowingly (until "bis", for the same version only)."""
    now = time.time() if now is None else now
    h = (d.get("hingenommen") or {}).get(f.get("key")) if isinstance(d.get("hingenommen"), dict) else None
    return isinstance(h, dict) and h.get("v") == f.get("v") and float(h.get("bis") or 0) > now


def aktiv(d, now=None):
    """The findings that count (not accepted knowingly)."""
    return [f for f in d["funde"] if not hingenommen(d, f, now)]


def gemeldet(d=None):
    """{OSV id: {"nr", "url", "t"}} of the issues sent for holes (Als Issue melden), also for System-Updates."""
    d = _read() if d is None else d
    g = d.get("gemeldet")
    return {k: v for k, v in g.items() if isinstance(v, dict) and isinstance(v.get("nr"), int)} if isinstance(g, dict) else {}


def issue(ids, d=None):
    """{"nr", "url"} of the issue one of these ids was sent in, None when none."""
    g = gemeldet(d)
    for i in ids or ():
        if i in g:
            return {"nr": g[i]["nr"], "url": str(g[i].get("url") or "")}
    return None


def _stufen(d, now=None):
    funde = aktiv(d, now)
    return (sum(1 for f in funde if f.get("stufe") == "kritisch"),
            sum(1 for f in funde if f.get("stufe") == "hoch"))


def zahlen(on, now=None):
    """Live: the counts when the function is on (on: features.admin_on("schwachstellen"), asked by the caller)."""
    now = time.time() if now is None else now
    if not on:
        return {"on": False}
    if 0 <= now - _live_cache[0] < LIVE_CACHE and _live_cache[1]:
        return _live_cache[1]
    d = _read()
    krit, hoch = _stufen(d, now)
    out = {"on": True, "t": int(d.get("t") or 0), "fehler": d.get("fehler") is True, "funde": len(aktiv(d, now)),
           "kritisch": krit, "hoch": hoch}
    _live_cache[:] = [now, out]
    return out


def live_sub(v):
    if not v.get("t"):
        return "noch nicht geprüft"
    t = f"{v['funde']} Funde" if v["funde"] != 1 else "1 Fund"
    if v["kritisch"]:
        t += f", {v['kritisch']} kritisch"
    if v["hoch"]:
        t += f", {v['hoch']} hoch"
    if v["fehler"]:
        t += " · zuletzt ohne Antwort"
    return t[:120]


def hinweise(on):
    """The note on top of the admin pages: a critical or high hole (fixed sentences, counts only)."""
    if not on:
        return []
    krit, hoch = _stufen(_read())
    if not krit and not hoch:
        return []
    teile = ([f"{krit} kritische"] if krit else []) + ([f"{hoch} hohe"] if hoch else [])
    return [{"kind": "schwachstellen", "level": "warn", "go": "Zustand → Schwachstellen",
             "text": f"{' und '.join(teile)} Schwachstellen unter Zustand → Schwachstellen."}]
