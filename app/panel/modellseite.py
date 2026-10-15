"""Zustand → Modelle (plan plaene/eigene-modelle.md, Stufe E1): the model catalog (app/modelle.py) to look at, for
admins only. Per kind (Sprachmodell, Bildverständnis, Spracherkennung, Sprachausgabe, Bilder malen, kleine Modelle)
which models the catalog knows, which one this configuration runs, its memory need (measured or estimated), licence,
and the memory budget: fixed models, models loaded on demand, what is left beside the system and the reserve, and
the fixed rule that follows from the numbers (all at once, one on-demand model at a time, too tight). Numbers from
`sudo speech-spark modelle messen` (STATE/modelle-messung.json) next to each measured model.

Nothing here switches or loads anything (that comes with stage E4 behind its own admin switch). Only names, numbers
and fixed words; never an address, a key or a text of an answer.
"""
import os
import sys
import time

from fastapi import APIRouter, Depends, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guard  # noqa: E402
import modelle  # noqa: E402
from common import load_config, read_json  # noqa: E402
from core import auth  # noqa: E402

LIVE_EVERY = 30          # seconds the Live view reuses the budget (systemctl and /proc are not read on every look)
MESSWERTE = ("tok_s", "erste_s", "belegt_gib", "laden_s", "mtp_annahme", "werkzeug", "bild_text", "bild_szene", "bild_ok", "ok")
_live = {"t": None, "v": None}


def _gesamt_gib():
    import psutil
    return psutil.virtual_memory().total / 2**30


def _lanes():
    import admin
    return [f for _, f in admin._qwen38_lanes()]


def seite(cfg=None, total_gib=None, lanes=None, messung=None, lang="de"):
    """What the page shows: {arten: [{art, name, modelle: [...]}], budget, messung_zeit}."""
    cfg = load_config() if cfg is None else cfg
    total_gib = _gesamt_gib() if total_gib is None else total_gib
    lanes = _lanes() if lanes is None else lanes
    messung = read_json(modelle.MESSUNG, {}) if messung is None else messung
    i = 1 if lang == "en" else 0
    kat = modelle.katalog()
    b = modelle.budget(cfg, total_gib, lanes, kat)
    laufend = {x["id"]: x["gib"] for x in b["teile"]}
    gemessen = messung.get("modelle") or {}
    arten = []
    for art, namen in modelle.ARTEN.items():
        rows = []
        for mid, m in kat.items():
            if m["art"] != art:
                continue
            r = gemessen.get(mid) or {}
            rows.append({"id": mid, "name": m["name"]["en" if i else "de"], "engine": m["engine"], "need_gib": m["need_gib"],
                         "gemessen": m["gemessen"], "betrieb": m["betrieb"], "lizenz": m["lizenz"], "gewerblich": m["gewerblich"],
                         "aktiv": mid in laufend, "gib": laufend.get(mid), "fest": bool(m["revision"]) or m["engine"] == "extern",
                         "messung": {k: r[k] for k in MESSWERTE if k in r}})
        arten.append({"art": art, "name": namen[i], "modelle": rows})
    return {"arten": arten, "budget": {k: v for k, v in b.items() if k != "teile"}, "messung_zeit": messung.get("zeit")}


def for_live(now=None):
    """For the Live view's language model box: the memory left for models and the budget's rule (numbers, fixed word),
    after the move (llm.enabled) the catalog name of the own model."""
    now = time.monotonic() if now is None else now
    if _live["t"] is None or now - _live["t"] > LIVE_EVERY:
        try:
            cfg = load_config()
            b = modelle.budget(cfg, _gesamt_gib(), _lanes())
            _live["v"] = {"on": True, "frei": b["frei"], "regel": b["regel"]}
            if cfg.get("llm", {}).get("enabled"):   # after the move: the own model's catalog name instead of qwen38
                _live["v"]["eigen"] = modelle.rolle("llm", cfg)[0]["name"]["de"]
        except Exception:
            _live["v"] = {"on": False}
        _live["t"] = now
    return _live["v"]


router = APIRouter()


@router.get("/api/admin/modelle", dependencies=[Depends(auth)])
def admin_modelle(request: Request, lang: str = "de"):
    """Zustand → Modelle: catalog, active models, memory budget and the last measurement (names and numbers only)."""
    guard.limit(request, "modelle", None, True)
    return seite(lang="en" if lang == "en" else "de")
