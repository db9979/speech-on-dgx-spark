"""KI-Dungeon-Master: echte Würfel am Tisch (D&D idea 5, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du“).

Whoever sits at the real table throws their own d20: before the panel rolls a turn's checks, a seat the host gave its
own dice (rd["echt"], the main thread's round switch) sees „Wirf W20 für Geschick gegen 14“ and taps or says the number.
The panel then rolls on as always, only this seat's d20 is the number given; the Würfel-Beleg says "echt" (the main
thread's). After WARTE_S without a number the panel rolls itself, as it always did. Never in the car (CarPlay): a seat
whose profile plays from the car is not asked (dungeon_auto.im_auto); a guest seat has no car.

Off by default: the admin's switch dungeonechtwuerfel (features.py, chat.dungeon_echtwuerfel) for the round's host.
The number is data: only the own seat, only whole numbers 1 to 20, only for the turn asked, an own rate limit.
State in the round (dungeon.py's rounds file), only while a turn waits for numbers:
    rd["echt_frage"]  {"zug", "t", "plaetze": {pid: {"fragen": [{"wert", "schwer", "n"}], "zahlen": [..] | None}}}
Journal: fixed words and numbers („dungeon: echt | …“), Live only counts.

    POST /api/profile/dungeon/{rid}/echt   {zug, zahlen}: the seat's numbers (a profile)
    POST /api/dungeon/echt                 {code, zug, zahlen}: the same for a guest's seat
"""
import asyncio
import time

from fastapi import APIRouter, Depends, Request

import features
import guard
from common import DayCounter
from core import assistant, browser_profile, json_body

router = APIRouter()
KEY = "dungeonechtwuerfel"
WARTE_S = 30               # the seats have this long for their numbers, then the panel rolls (as WURF_MAX_S of the wait)
TAKT_S = 0.5               # how often the waiting turn looks for the numbers
SEITEN = 20                # a d20: 1 to 20
BODY = 512

_day = DayCounter(gefragt=0, echt=0, rueckfall=0, abgelehnt=0)


def on(rd):
    """The host's admin switch and the round's seats with own dice."""
    return bool(rd.get("owner")) and bool(rd.get("echt")) and features.allowed(KEY, rd["owner"])


def _im_auto(uid):
    """Whether the seat's profile plays from the car (the main thread's dungeon_auto.im_auto). Until that helper is
    there, nobody is asked: never a question to a driver."""
    try:
        import dungeon_auto
        f = getattr(dungeon_auto, "im_auto", None)
    except Exception:  # noqa: BLE001 - no car module, no car
        return False
    return True if f is None else bool(uid) and bool(f(uid))


def seats(rd, proben):
    """{pid: [questions]}: the checks of this turn whose seat throws its own die."""
    out = {}
    for p in proben or []:
        pid = p.get("pid")
        seat = rd["plaetze"].get(pid) or {}
        if pid not in (rd.get("echt") or []) or not seat.get("held") or _im_auto(seat.get("uid")):
            continue
        out.setdefault(pid, []).append({"wert": p.get("wert", ""), "schwer": int(p.get("schwer") or 0), "n": 2 if p.get("vt") else 1})
    return out


class Hand:
    """The numbers the seats gave; the panel's roll takes a seat's d20 from here first, then from its own dice."""

    def __init__(self, zahlen):
        self._z = {pid: list(z) for pid, z in zahlen.items()}
        self._used = set()

    def d20(self, pid, rng):
        q = self._z.get(pid)
        if q:
            self._used.add(pid)
            return q.pop(0)
        return rng.randint(1, SEITEN)

    def used(self, pid):
        return pid in self._used


async def real_ask(dm, rid, turn, rd, proben):
    """Asks the seats with own dice for their numbers and waits at most WARTE_S. Returns a Hand, or None when no
    seat of this turn throws its own die (then the panel rolls as always)."""
    if not on(rd):
        return None
    ask = seats(rd, proben)
    if not ask:
        return None

    def put():
        with dm._lock:
            d = dm._read()
            cur = d["runden"].get(rid)
            if not cur or cur["zug"] != turn:
                return False
            cur["echt_frage"] = {"zug": turn, "t": time.time(), "plaetze": {pid: {"fragen": f, "zahlen": None} for pid, f in ask.items()}}
            if cur.get("dm"):
                dm.warten.step(cur, "wuerfeln")
            dm._write(d)
            return True

    if not await asyncio.to_thread(put):
        return None
    _day.bump("gefragt", len(ask))
    print(f"dungeon: echt | frage | {len(ask)} plaetze", flush=True)
    t0 = time.monotonic()
    got = {}
    while True:
        cur = (await asyncio.to_thread(dm._read))["runden"].get(rid) or {}
        q = cur.get("echt_frage") or {}
        if q.get("zug") != turn:
            break
        got = {pid: x["zahlen"] for pid, x in q["plaetze"].items() if x.get("zahlen")}
        if len(got) == len(ask) or time.monotonic() - t0 >= WARTE_S:
            break
        await asyncio.sleep(TAKT_S)

    def clear():
        with dm._lock:
            d = dm._read()
            cur = d["runden"].get(rid)
            if cur and (cur.get("echt_frage") or {}).get("zug") == turn:
                cur.pop("echt_frage", None)
                dm._write(d)

    await asyncio.to_thread(clear)
    left = len(ask) - len(got)
    if got:
        _day.bump("echt", len(got))
    if left:
        _day.bump("rueckfall", left)
    print(f"dungeon: echt | {'alle da' if not left else 'rueckfall'} | {len(got)} echt {left} panel | {round(time.monotonic() - t0)} s", flush=True)
    return Hand(got)


def give(rd, pid, zug, zahlen):
    """The seat's numbers for the turn asked: whole numbers 1 to SEITEN, as many as its questions want."""
    q = rd.get("echt_frage") or {}
    if q.get("zug") != zug or not isinstance(zug, int) or isinstance(zug, bool):
        raise TimeoutError("alter zug")
    me = (q.get("plaetze") or {}).get(pid)
    if not me:
        raise LookupError("platz")
    if me.get("zahlen"):
        raise FileExistsError("eingabe")
    want = sum(f["n"] for f in me["fragen"])
    if not isinstance(zahlen, list) or len(zahlen) != want \
            or not all(isinstance(z, int) and not isinstance(z, bool) and 1 <= z <= SEITEN for z in zahlen):
        raise ValueError("eingabe")
    me["zahlen"] = list(zahlen)


def view(rd, pid, now=None):
    """What a seat sees of the question: its own questions with the seconds left, the names of the others still
    throwing; None while nothing is asked."""
    q = rd.get("echt_frage")
    if not q:
        return None
    now = time.time() if now is None else now
    names = {p: (x.get("held") or {}).get("name", "") for p, x in rd["plaetze"].items()}
    me = q["plaetze"].get(pid)
    return {"zug": q["zug"], "rest": max(0, round(WARTE_S - (now - q["t"]))), "max": WARTE_S, "seiten": SEITEN,
            "fragen": me["fragen"] if me and not me.get("zahlen") else [], "fertig": bool(me and me.get("zahlen")),
            "andere": sorted(names[p] for p, x in q["plaetze"].items() if p != pid and not x.get("zahlen") and names.get(p))}


def for_live():
    """Numbers only: seats asked, numbers given, turns the panel rolled itself after the wait, refused inputs today."""
    t = _day.counts()
    return {"gefragt": t["gefragt"], "echt": t["echt"], "rueckfall": t["rueckfall"], "abgelehnt": t["abgelehnt"]}


# ---------------------------------------------------------------- routes
async def _give(rid, seat, b):
    import dungeon as dm

    def go():
        pid = seat()
        with dm._lock:
            d = dm._read()
            give(dm._round(d, rid), pid, b.get("zug"), b.get("zahlen"))
            dm._write(d)
        return dm.view(rid, pid)
    try:
        v = await asyncio.to_thread(go)
    except dm.KNOWN as e:
        _day.bump("abgelehnt")
        print(f"dungeon: echt | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)
    print("dungeon: echt | eingetragen", flush=True)
    return v


@router.post("/api/profile/dungeon/{rid}/echt", dependencies=[Depends(assistant)])
async def echt(rid: str, request: Request, prof=Depends(browser_profile)):
    """The seat's own dice: {zug, zahlen}."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonecht", uid)
    b = await json_body(request, BODY)
    return await _give(rid, lambda: dm._seat_uid(rid, uid), b)


@router.post("/api/dungeon/echt")
async def gast_echt(request: Request):
    """{"code", "zug", "zahlen"}: a guest's seat gives its own dice."""
    import dungeon as dm
    b, rid, pid = await dm._guest(request, BODY)
    guard.limit(request, "dungeonecht")
    return await _give(rid, lambda: pid, b)
