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

import modelle
from common import STATE, load_config, read_json, write_json

NEU = os.path.join(STATE, "modelle-neu.json")
ALLE_S = 86400
# Only the rules and the state live here; the model page (modellseite.neu_schritt) gives the switch, the fetch through
# netguard and its own sources, so this module stays below the big import knot (test_schichten).


def stand():
    d = read_json(NEU, {})
    return d if isinstance(d, dict) else {}


def faellig(an, now=None):
    """an: the switch (modellseite._neu_an)."""
    now = time.time() if now is None else now
    return bool(an) and now - float(stand().get("zeit", 0) or 0) >= ALLE_S


async def lauf(holen, quelle, familien, now=None):
    """The daily look; returns the kept hits. holen(publisher): the public list or None; quelle and familien: the
    model page's (modellseite._quelle, _familien)."""
    cfg = load_config()
    q = await asyncio.to_thread(quelle, cfg)
    total_gib, kat, profil = q[0], q[3], q[8]
    fam = familien
    familien = {a: await fam(a, kat) for a in modelle.NEU_ARTEN if a in modelle.SPRACH}
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


def zeigen(an, lang="de"):
    """For Zustand → Modelle: the kept hits with the kind's name, None while switched off or before the first look."""
    if not an:
        return None
    d = stand()
    if not d.get("zeit"):
        return None
    i = 1 if lang == "en" else 0
    return {"zeit": d["zeit"], "fehler": d.get("fehler", 0),
            "treffer": [dict(x, art_name=modelle.ARTEN.get(x.get("art"), ("", ""))[i]) for x in d.get("treffer") or []
                        if isinstance(x, dict) and x.get("art") in modelle.NEU_ARTEN]}
