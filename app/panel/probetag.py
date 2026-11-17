"""Probetag nach dem Wechsel (Dominik 2026-11-16 „1-6“ point 4, stage B2; 2026-11-17 „mache das projekt bis zu ende
durch“): after the language model changed, the panel puts the new one through the fixed quality test (quality.py,
reason "probetag") as soon as it answers, and compares it with the newest run of the model before. Fixed rules, never
a model's judgement:

- more than SCHLECHTER questions fewer right than the model before (on the same number of questions): back to the model
  before, the same way as „Zurückholen“ (here or through the model computer's Wärter, within modelle.ALT_TAGE);
- else it stays („behalten“); without a run of the model before it stays too („ohne Vergleich“);
- a test that broke off (no answer) decides nothing: „fehler“, the model stays; switched off meanwhile: „aus“.

Admin switch Funktionen → Modelle wechseln → „Probetag nach dem Wechsel“ (chat.modelle_probetag, off). The state is in
STATE/modelle-probetag.json; the log gets only fixed words and numbers ("modelle: probetag …"), Zustand → Modelle shows
the result.
"""
import asyncio
import os
import time

import features
import modelle
import quality
from common import STATE, load_config, read_json, write_json

STAND = os.path.join(STATE, "modelle-probetag.json")
SCHLECHTER = 1            # this many questions fewer right are still chance (a run repeats each failed one once)
WARTEN_S = 1800           # the new model must answer within this long after the switch, else „fehler“
ERGEBNISSE = ("wartet", "laeuft", "behalten", "ohne_vergleich", "zurueck", "fehler", "aus")
_task = None


def an(cfg=None):
    return features.admin_on("modelleprobetag", cfg)


def stand():
    d = read_json(STAND, {})
    return d if isinstance(d, dict) else {}


def _merken(d):
    write_json(STAND, d, indent=1)


def urteil(neu, alt):
    """The fixed rule: (word) from the new run and the newest run of the model before (quality results, or None)."""
    if not neu or not neu.get("total") or neu.get("error"):
        return "fehler"
    if not alt or alt.get("total") != neu["total"]:
        return "ohne_vergleich"
    return "zurueck" if neu["passed"] < alt["passed"] - SCHLECHTER else "behalten"


def letzter_lauf(mid, history=None):
    """The newest quality run of the catalog model mid (quality-history „katalog“), None without one."""
    for h in reversed(quality.history() if history is None else history):
        if h.get("katalog") == mid and h.get("total"):
            return h
    return None


def schritt(cfg=None, now=None):
    """Once a minute (panel.every_minute): notices a new language model and, when it is due, starts the test in its
    own task. Returns the word of what it did: "", "neu", "start"."""
    global _task
    cfg = load_config() if cfg is None else cfg
    now = time.time() if now is None else now
    mid = cfg.get("llm", {}).get("modell", "") if cfg.get("llm", {}).get("enabled") else ""
    d = stand()
    if not mid:
        return ""
    if d.get("gesehen") != mid:            # a switch (or the first look): the model before is the one seen until now
        alt = d.get("gesehen", "")
        d = {"gesehen": mid, "alt": alt, "seit": int(now), "ergebnis": "wartet" if alt and an(cfg) else ""}
        _merken(d)
        if d["ergebnis"]:
            print("modelle: probetag wartet", flush=True)
        return "neu"
    if d.get("ergebnis") != "wartet" or not an(cfg) or (_task and not _task.done()) or quality.running():
        return ""
    if now - d.get("seit", now) > WARTEN_S:
        d.update(ergebnis="fehler", ende=int(now))
        _merken(d)
        print("modelle: probetag fehler zeit", flush=True)
        return ""
    _task = asyncio.get_running_loop().create_task(_lauf(mid, d["alt"]))
    return "start"


async def _lauf(mid, alt):
    """The test of the new model, the verdict, and the way back when it is worse."""
    import health
    d = dict(stand(), ergebnis="laeuft")
    _merken(d)
    print("modelle: probetag start", flush=True)
    try:
        await health.ready(load_config(), minutes=5)
        neu = await quality.run("probetag")
    except Exception:
        neu = None
    vorher = letzter_lauf(alt)
    wort = urteil(neu, vorher) if an() else "aus"      # switched off meanwhile: the test decides nothing
    d = dict(stand(), ergebnis=wort, ende=int(time.time()),
             neu=[neu["passed"], neu["total"]] if neu and neu.get("total") else None,
             vorher=[vorher["passed"], vorher["total"]] if vorher else None)
    if d.get("gesehen") != mid:         # switched again meanwhile: this verdict belongs to nobody
        print("modelle: probetag verworfen", flush=True)
        return
    if wort == "zurueck":
        try:
            await asyncio.to_thread(_zurueck)
        except Exception:
            d["ergebnis"] = "fehler"
            print("modelle: probetag zurueck fehler", flush=True)
    _merken(d)
    print(f"modelle: probetag {d['ergebnis']} {d['neu'][0] if d['neu'] else 0} {d['vorher'][0] if d['vorher'] else 0}", flush=True)


def _zurueck():
    import modellseite
    modellseite.wunsch_ohne_seite("llm", "zurueck")


def zeigen(kat=None, lang="de"):
    """For Zustand → Modelle: the last trial with the names, None without one."""
    d = stand()
    if not d.get("ergebnis"):
        return None
    kat = modelle.katalog() if kat is None else kat
    i = "en" if lang == "en" else "de"

    def name(x):
        return ((kat.get(x) or {}).get("name") or {}).get(i, x) if x else ""
    return {"ergebnis": d["ergebnis"] if d["ergebnis"] in ERGEBNISSE else "fehler", "name": name(d.get("gesehen")),
            "alt_name": name(d.get("alt")), "neu": d.get("neu"), "vorher": d.get("vorher"), "seit": d.get("seit"),
            "ende": d.get("ende"), "an": an()}
