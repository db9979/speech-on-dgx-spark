"""KI-Dungeon-Master: Herzenswunsch je Held (D&D ideas round 2, idea 7, Dominik 2026-10-26 „1-9 umsetzten reihenfolge
überlasse ich dir.“; the bonds and goals of many tabletop games, only as an idea, own code; the list of wishes per
world is the DnDAppFiles thread's, ideen.wuensche).

Every hero may carry one heart's wish (set): one of the world's list (choices, ideen.wuensche "alle" and the round's
world) or its own words of at most WUNSCH_MAX characters. It is a secret: only the own seat, the host (the game
master) and the model see it. Per act of the story (without a story plan every ZUEGE turns) the panel gives the
narrator at most one wish, the heroes with an open wish in turn by their seats (whose); the narrator weaves in a chance
for it and reports in the field wunsch_erfuellt the hero's name when it came true in this turn. The panel takes that
only by fixed rules (check): the hero of this act's wish, it acted this turn, the narration names it, the wish still
open; then the hero gets the experience of an act (r["ep"]["akt"]) and the table sees „💖 … Herzenswunsch hat sich
erfüllt“ (never the wish itself). The wish goes to the model only as game text between <<< and >>>.

Off by default: the admin's switch dungeonwunsch (features.py, chat.dungeon_wunsch) for the round's host.
Journal: fixed words and numbers („dungeon: wunsch | …“), Live only counts.

    POST /api/profile/dungeon/{rid}/wunsch   {text} or {id}; both empty: the wish away
    POST /api/dungeon/wunsch                 {code, text} or {code, id}: a guest's seat
"""
import asyncio

from fastapi import APIRouter, Depends, Request

import features
import guard
from common import DayCounter
from core import assistant, browser_profile, json_body
from dungeon_ideen import WUNSCH_MAX

router = APIRouter()
KEY = "dungeonwunsch"
ZUEGE = 8                  # without a story plan: a new wish's turn every this many turns
BODY = 1024
NAME_MAX = 40
SCHEMA = {"type": "string", "maxLength": NAME_MAX}

_day = DayCounter(gesetzt=0, erfuellt=0, verworfen=0, abgelehnt=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def choices(r, rd):
    """The world's list of wishes: {id, t [de, en]}, those for every world first."""
    w = (r.get("ideen") or {}).get("wuensche") or {}
    return list(w.get("alle") or []) + ([] if rd.get("welt") == "alle" else list(w.get(rd.get("welt")) or []))


def text_of(h, li):
    w = (h or {}).get("wunsch") or {}
    t = w.get("t")
    return t[li] if isinstance(t, list) else str(t or "")


def put(dm, r, rd, pid, text, wid):
    """The hero's wish from the list (wid) or in its own words; both empty: the wish away."""
    if not on(rd):
        raise LookupError("wunsch aus")
    h = (rd["plaetze"].get(pid) or {}).get("held")
    if not h or h.get("tot"):
        raise LookupError("platz")
    if not wid and not str(text or "").strip():
        h.pop("wunsch", None)
        print("dungeon: wunsch | weg", flush=True)
        return
    if wid:
        x = next((x for x in choices(r, rd) if x.get("id") == wid), None)
        if not x:
            raise ValueError("wunsch")
        t = list(x["t"])
    else:
        t = dm.plain(text, WUNSCH_MAX)
        if len(t) < 3:
            raise ValueError("wunsch")
        if dm.bad_words(r, rd, t):
            raise ValueError("wortliste")
    h["wunsch"] = {"t": t, "id": wid or "", "erfuellt": 0}
    _day.bump("gesetzt")
    print(f"dungeon: wunsch | gesetzt | {'liste' if wid else 'eigen'}", flush=True)


def _act(rd):
    return rd.get("akt", 0) if rd.get("plan") else max(0, rd.get("zug", 1) - 1) // ZUEGE


def whose(dm, rd):
    """(pid, hero) whose wish this act carries: the seats with an open wish in turn; None without one."""
    if not on(rd):
        return None
    open_ = [(pid, p["held"]) for pid, p in dm.seated(rd) if (p["held"].get("wunsch") or {}).get("t")
             and not p["held"]["wunsch"].get("erfuellt") and not p["held"].get("tot")]
    return open_[_act(rd) % len(open_)] if open_ else None


def facts(dm, rd):
    """Only the hero's name as data; the wish itself goes into the game text (game_lines)."""
    x = whose(dm, rd)
    return {"herzenswunsch_von": x[1]["name"]} if x else {}


def game_lines(dm, rd):
    """The act's wish as game text for dungeon.facts (between <<< and >>>)."""
    x = whose(dm, rd)
    li = 1 if rd.get("lang") == "en" else 0
    return [("Herzenswunsch von ", "Heart's wish of ")[li] + f"{x[1]['name']}: {text_of(x[1], li)}"] if x else []


AUFGABE = {
    "de": (" Steht herzenswunsch_von in den Fakten, steht der Herzenswunsch dieses Helden im Spieltext: gib ihm in diesem "
           "Akt eine Gelegenheit dafür, ohne den Wunsch wörtlich zu nennen. Geht er in diesem Zug durch die Tat des Helden "
           "in Erfüllung, schreibe den Namen des Helden in wunsch_erfuellt, sonst lass es leer."),
    "en": (" When the facts hold herzenswunsch_von, that hero's heart's wish stands in the game text: give it a chance in "
           "this act without saying the wish word for word. When it comes true in this turn by the hero's deed, write the "
           "hero's name in wunsch_erfuellt, else leave it empty."),
}


def task(dm, rd, lang):
    return AUFGABE[lang] if whose(dm, rd) else ""


def check(dm, rd, name, text):
    """The narration's wunsch_erfuellt by fixed rules: the pid of this act's wish hero, who acted and is named; else ""."""
    x = whose(dm, rd)
    n = str(name or "").strip().lower()
    if not n:
        return ""
    if not x or x[1]["name"].lower() != n or x[0] not in (rd.get("offen") or {}) or n not in str(text or "").lower():
        _day.bump("verworfen")
        print("dungeon: wunsch | verworfen", flush=True)
        return ""
    return x[0]


def come_true(dm, r, rd, pid, ep):
    """In dungeon.apply: the wish fulfilled, the experience of an act, a card for the table without the wish."""
    h = (rd["plaetze"].get(pid) or {}).get("held")
    if not h or not h.get("wunsch") or h["wunsch"].get("erfuellt"):
        return
    h["wunsch"]["erfuellt"] = rd["zug"]
    if pid in ep:
        ep[pid] += r["ep"]["akt"]
    dm._log(rd, "wunsch", pid=pid, name=h["name"])
    _day.bump("erfuellt")
    print("dungeon: wunsch | erfuellt", flush=True)


def view(dm, r, rd, pid, host):
    """The own wish with the list to pick from; the host also every other seat's wish (the game master)."""
    if not on(rd):
        return None
    li = 1 if rd.get("lang") == "en" else 0
    h = (rd["plaetze"].get(pid) or {}).get("held")
    w = (h or {}).get("wunsch") or {}
    x = whose(dm, rd)
    out = {"text": text_of(h, li), "id": w.get("id", ""), "erfuellt": bool(w.get("erfuellt")), "dran": bool(x and x[0] == pid),
           "wahl": [{"id": c["id"], "t": c["t"][li]} for c in choices(r, rd)], "max": WUNSCH_MAX}
    if host:
        out["andere"] = [{"name": p["held"]["name"], "text": text_of(p["held"], li), "erfuellt": bool(p["held"]["wunsch"].get("erfuellt"))}
                         for q, p in rd["plaetze"].items() if q != pid and p.get("held") and (p["held"].get("wunsch") or {}).get("t")]
    return out


def for_live():
    """Numbers only: wishes set, fulfilled, reports refused, refused requests today."""
    t = _day.counts()
    return {k: t[k] for k in ("gesetzt", "erfuellt", "verworfen", "abgelehnt")}


# ---------------------------------------------------------------- routes
async def _set(rid, seat, b):
    import dungeon as dm

    def go():
        pid = seat()
        with dm._lock:
            d = dm._read()
            put(dm, dm.rules(), dm._round(d, rid), pid, b.get("text"), str(b.get("id") or "")[:40])
            dm._write(d)
        return dm.view(rid, pid)
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        _day.bump("abgelehnt")
        print(f"dungeon: wunsch | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/wunsch", dependencies=[Depends(assistant)])
async def wunsch(rid: str, request: Request, prof=Depends(browser_profile)):
    """{text} or {id}: the own hero's heart's wish; both empty: away."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonwunsch", uid)
    b = await json_body(request, BODY)
    return await _set(rid, lambda: dm._seat_uid(rid, uid), b)


@router.post("/api/dungeon/wunsch")
async def gast_wunsch(request: Request):
    """{"code", "text"} or {"code", "id"}: a guest's seat sets its hero's wish."""
    import dungeon as dm
    b, rid, pid = await dm._guest(request, BODY)
    guard.limit(request, "dungeonwunsch")
    return await _set(rid, lambda: pid, b)
