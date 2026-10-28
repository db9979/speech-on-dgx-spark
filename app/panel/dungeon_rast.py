"""KI-Dungeon-Master: Lagerfeuer und Rast (D&D idea 4, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du alles
umsetzten kannst.“; short and long rests of the SRD 5.1, CC BY 4.0; own code, the tables „landschaften“, „nachtwachen“
and „fragekarten“ come from the thread „DnDAppFiles für den Dungeon-Master“, dungeon_srd.json „ideen“).

Outside a fight the host calls a rest for the group (POST …/rast {art}):
- kurz: every hero up heals a quarter of its life (at least 1); at most KURZ_MAX between two long rests;
- lang: three night watches (WACHEN) on the table of the landscape the group stands in (the map's place, a vault is
  „unter der Erde“, else „weg“); a watch „ueberfall“ disturbs the night: half the life back and no spell charges,
  else full life and every charge; every seat with a hero gets a question card of the campfire (fragekarten of the
  world and „alle“) for its next action; at most one long rest in LANG_ZUEGE turns. At the children's table a raid
  is only a noise, never a disturbed night.
Only the panel rolls and heals; the next narration tells the camp from its facts (rast), a raid may bring a fight as
the narration's encounter of the panel's foes. While a rest waits for its narration rd["rast"] stands (the music's
mood „lager“, dungeon_musik); the narrated turn ends it (done).

Off by default: the admin's switch dungeonrast (features.py, chat.dungeon_rast) for the round's host.
Journal: fixed words and numbers („dungeon: rast | …“), Live only counts.
"""
import asyncio
import random

from fastapi import APIRouter, Depends, Request

import features
import guard
from common import DayCounter
from core import assistant, browser_profile, json_body

router = APIRouter()

KEY = "dungeonrast"
ARTEN = ("kurz", "lang")
KURZ_MAX = 2               # short rests between two long ones
KURZ_TEIL = 4              # a short rest heals this part of the life (at least 1)
LANG_ZUEGE = 8             # turns between two long rests
WACHEN = 3                 # night watches of a long rest
BODY = 256

_day = DayCounter(kurz=0, lang=0, gestoert=0, abgelehnt=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def land(r, rd):
    """The landscape the group stands in: the map place's kind in ideen.landschaften, a vault under the earth, else
    the road („weg“, the table's fallback)."""
    rows = (r.get("ideen") or {}).get("landschaften") or []
    by = {x["id"]: x for x in rows}
    k = rd.get("karte") or {}
    if k.get("drin") is not None and "unterwelt" in by:
        return by["unterwelt"]
    orte = k.get("orte") or []
    art = orte[k["hier"]].get("art") if 0 <= k.get("hier", -1) < len(orte) else ""
    return next((x for x in rows if art and art in x["ortsarten"]), by.get("weg"))


def watches(r, rd, rng, kids):
    """WACHEN rolls of a d20 on the landscape's night table: [{art, t}]; a raid is a noise at the children's table."""
    import dungeon_ideen
    la = land(r, rd)
    table = ((r.get("ideen") or {}).get("nachtwachen") or {})
    rows = table.get(la["id"] if la else "") or table.get("weg") or []
    out = []
    for _ in range(WACHEN if rows else 0):
        w = rng.randint(1, dungeon_ideen.NARBEN_W)
        x = next((x for x in rows if x["von"] <= w <= x["bis"]), None)
        if x:
            out.append({"w": w, "art": "geraeusch" if kids and x["art"] == "ueberfall" else x["art"], "t": list(x["t"])})
    return out


def cards(dm, r, rd, rng):
    """One question card of the campfire per seat with a hero (the world's and „alle“), none twice if enough."""
    f = (r.get("ideen") or {}).get("fragekarten") or {}
    pool = list(f.get(rd.get("welt", "")) or []) + list(f.get("alle") or [])
    rng.shuffle(pool)
    return {pid: list(pool[i % len(pool)]) for i, (pid, _) in enumerate(dm.seated(rd))} if pool else {}


def rest(dm, r, rd, art, rng=None):
    """The host's rest by fixed rules; raises the game's refusals."""
    import dungeon_kalender
    rng = rng or random
    if not on(rd):
        raise LookupError("rast aus")
    if art not in ARTEN:
        raise ValueError("eingabe")
    if rd.get("kampf"):
        raise FileExistsError("rast kampf")
    if rd.get("rast"):
        raise FileExistsError("rast schon")
    zug = rd.get("zug", 0)
    if art == "kurz" and rd.get("rast_kurz", 0) >= KURZ_MAX:
        raise FileExistsError("rast kurz")
    last = rd.get("rast_lang_zug")
    if art == "lang" and isinstance(last, int) and zug - last < LANG_ZUEGE:
        raise FileExistsError("rast lang")
    li = 1 if rd.get("lang") == "en" else 0
    la = land(r, rd)
    e = {"art": art, "zug": zug, "landschaft": la["name"] if la else ["", ""]}
    up = [(pid, p) for pid, p in dm.seated(rd) if not p["held"].get("tot") and not p["held"].get("ohnmacht")]
    if art == "kurz":
        rd["rast_kurz"] = rd.get("rast_kurz", 0) + 1
        for pid, p in up:
            h = p["held"]
            if dm.zustand(h) == "boden":
                continue
            dm.heal(h, max(1, h["leben_max"] // KURZ_TEIL))
    else:
        rd["rast_kurz"], rd["rast_lang_zug"] = 0, zug
        dungeon_kalender.weiter(r, rd, 2, "rast")   # the night: a day of the world's calendar (D&D idea 6)
        e["wachen"] = watches(r, rd, rng, dm.kids(r, rd))
        e["gestoert"] = any(x["art"] == "ueberfall" for x in e["wachen"])
        e["fragen"] = cards(dm, r, rd, rng)
        import dungeon_wandern
        dungeon_wandern.rest(dm, r, rd, rng)     # people of the map move on, a rumour at the campfire (LlamaTale idea 6)
        for pid, p in up:
            h = p["held"]
            was = h["leben"]
            dm.heal(h, h["leben_max"] // 2 if e["gestoert"] else h["leben_max"])
            if not e["gestoert"]:
                h["ladungen"] = dm.full_charges(r, h)
            dm.stood_up(rd, pid, h, was)
    rd["rast"] = e
    dm._log(rd, "rast", rast=art, landschaft=e["landschaft"][li], wachen=[x["t"][li] for x in e.get("wachen") or []],
            gestoert=bool(e.get("gestoert")))
    _day.bump(art)
    if e.get("gestoert"):
        _day.bump("gestoert")
    print(f"dungeon: rast | {art}" + (f" | {len(e['wachen'])} wachen | {'gestoert' if e['gestoert'] else 'ruhig'}" if art == "lang" else ""), flush=True)


def done(rd):
    """A narrated turn after the rest ends it."""
    e = rd.get("rast")
    if e and e.get("zug", 0) < rd.get("zug", 0):
        rd.pop("rast", None)


def facts(rd):
    """The rest for the narration: kind, landscape, watches, disturbed, the question cards by hero."""
    e = rd.get("rast")
    if not e or not on(rd):
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    names = {pid: (p.get("held") or {}).get("name", "") for pid, p in rd["plaetze"].items()}
    out = {"art": e["art"], "landschaft": e["landschaft"][li]}
    if e["art"] == "lang":
        out.update(wachen=[{"art": x["art"], "t": x["t"][li]} for x in e.get("wachen") or []], gestoert=e.get("gestoert", False),
                   fragen={names[pid]: q[li] for pid, q in (e.get("fragen") or {}).items() if names.get(pid)})
    return {"rast": out}


AUFGABE = {
    "de": (" Steht in den Fakten rast, erzählst du diesen Zug als Lager der Gruppe in dieser Landschaft: bei einer langen "
           "Rast die Nachtwachen in ihrer Reihenfolge; gestoert heißt, die Nacht wurde unterbrochen. Die Heilung hat das "
           "Panel schon vergeben; nenne keine Zahlen. Die fragen sind Fragen am Lagerfeuer an die Helden."),
    "en": (" When the facts hold rast, tell this turn as the group's camp in this landscape: on a long rest the night "
           "watches in their order; gestoert means the night was interrupted. The panel has already given the healing; "
           "name no numbers. The fragen are questions at the campfire for the heroes."),
}


def task(rd, lang):
    return AUFGABE[lang] if facts(rd) else ""   # only with its data this turn (Review 27.10. T20)


def view(rd, pid, host):
    """The rest for the table: the current one (with the own question card) and, for the host, what may be called."""
    if not on(rd):
        return None
    li = 1 if rd.get("lang") == "en" else 0
    e = rd.get("rast")
    out = {}
    if e:
        out["jetzt"] = {"art": e["art"], "landschaft": e["landschaft"][li], "wachen": [{"art": x["art"], "t": x["t"][li]} for x in e.get("wachen") or []],
                        "gestoert": bool(e.get("gestoert")), "frage": ((e.get("fragen") or {}).get(pid) or ["", ""])[li]}
    if host:
        last = rd.get("rast_lang_zug")
        noch = max(0, LANG_ZUEGE - (rd.get("zug", 0) - last)) if isinstance(last, int) else 0
        out.update(kurz_frei=max(0, KURZ_MAX - rd.get("rast_kurz", 0)), lang_in=noch, geht=not rd.get("kampf") and not e and rd.get("status") != "ende")
    return out


def for_live():
    """Numbers only: short and long rests, disturbed nights and refusals today."""
    t = _day.counts()
    return {k: t[k] for k in ("kurz", "lang", "gestoert", "abgelehnt")}


# ---------------------------------------------------------------- route
@router.post("/api/profile/dungeon/{rid}/rast", dependencies=[Depends(assistant)])
async def rast(rid: str, request: Request, prof=Depends(browser_profile)):
    """The host calls a rest: {art: kurz|lang}."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, BODY)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            rest(dm, dm.rules(), rd, b.get("art"))
            dm._write(d)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        _day.bump("abgelehnt")
        print(f"dungeon: rast | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)
