"""Neu verfügbar (Dominik 2026-11-16 „1-6“ point 6, stage D2): once a day the panel asks Hugging Face's public list for
the newest models of a few fixed publishers (modelle.NEU_HERAUSGEBER), checks them with the quick rules of the search
(modelle.neu_auswahl: the kind's task, safetensors, no code, a known family or architecture, memory) and keeps the
fitting ones of the last 30 days as a hint for Zustand → Modelle. Nothing is downloaded or added; „Hinzufügen“ there
runs the full check on the pinned commit like every own model. Only through netguard (public internet), only the
publisher's name in the address, never a token. Admin switch Funktionen → Modelle wechseln → „Neu verfügbar“
(chat.modelle_neu, off). The log gets only fixed words and numbers ("modelle: neu …").
"""
import asyncio
import os
import time

import features
import modelle
import netguard
from common import STATE, load_config, read_json, write_json

NEU = os.path.join(STATE, "modelle-neu.json")
ALLE_S = 86400
_task = None


def an(cfg=None):
    return features.admin_on("modelleneu", cfg)


def stand():
    d = read_json(NEU, {})
    return d if isinstance(d, dict) else {}


def faellig(cfg=None, now=None):
    now = time.time() if now is None else now
    return an(cfg) and now - float(stand().get("zeit", 0) or 0) >= ALLE_S


def schritt(cfg=None, now=None):
    """Once a minute (panel.every_minute): starts the daily look in its own task when it is due."""
    global _task
    if not faellig(cfg, now) or (_task and not _task.done()):
        return ""
    _task = asyncio.get_running_loop().create_task(lauf())
    return "start"


async def _holen(herausgeber):
    import httpx
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=modelle.SUCHE_ANTWORT_MAX, timeout=20,
                                   follow_redirects=False) as c:
            r = await c.get(modelle.neu_url(herausgeber))
    except (httpx.HTTPError, OSError, ValueError):
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


async def lauf(now=None, holen=None):
    """The daily look; returns the kept hits."""
    import modellseite
    holen = holen or _holen
    cfg = load_config()
    q = await asyncio.to_thread(modellseite._quelle, cfg)
    total_gib, kat, profil = q[0], q[3], q[8]
    familien = {a: await modellseite._familien(a, kat) for a in modelle.NEU_ARTEN if a in modelle.SPRACH}
    treffer, gesehen, fehler = [], set(), 0
    for h in modelle.NEU_HERAUSGEBER:
        items = await holen(h)
        if items is None:
            fehler += 1
            continue
        for art in modelle.NEU_ARTEN:
            for x in modelle.neu_auswahl(items, art, total_gib, kat, profil, now, familien.get(art, ())):
                if x["repo"] not in gesehen:
                    gesehen.add(x["repo"])
                    treffer.append(x)
    treffer.sort(key=lambda x: (x["tage"], x["repo"]))
    treffer = treffer[:modelle.NEU_MAX]
    write_json(NEU, {"zeit": int(time.time() if now is None else now), "treffer": treffer,
                     "fehler": fehler}, indent=1)
    print(f"modelle: neu {len(treffer)} treffer {fehler} fehler", flush=True)
    return treffer


def zeigen(lang="de"):
    """For Zustand → Modelle: the kept hits with the kind's name, None while switched off or before the first look."""
    if not an():
        return None
    d = stand()
    if not d.get("zeit"):
        return None
    i = 1 if lang == "en" else 0
    return {"zeit": d["zeit"], "fehler": d.get("fehler", 0),
            "treffer": [dict(x, art_name=modelle.ARTEN.get(x.get("art"), ("", ""))[i]) for x in d.get("treffer") or []
                        if isinstance(x, dict) and x.get("art") in modelle.NEU_ARTEN]}
