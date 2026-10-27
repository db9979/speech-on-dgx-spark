"""KI-Dungeon-Master: echte Würfel am Tisch (D&D idea 5, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du“).

Whoever sits at the real table throws their own d20: before the panel rolls a turn's checks, a seat the host gave its
own dice (rd["echt"], the host's choice in the console: choose) sees „Wirf W20 für Geschick gegen 14“ and taps or says
the number. The panel then rolls on as always, only this seat's d20 is the number given (dungeon.roll and
dungeon_kampf.attacks with the Hand); the Würfel-Beleg says "echt". After WARTE_S without a number the panel rolls
itself, as it always did. In a fight a hero whose action attacks by the panel's rules (dungeon_kampf.attackers) is
asked „Wirf W20 für den Angriff auf X“ instead of the model's checks (review 2026-10-27 T14); with advantage or
disadvantage the second d20 is the panel's. A seat that gave no number twice in a row waits only KURZ_S, until it
throws again. Never in the car (CarPlay): a seat
whose profile plays from the car is not asked (dungeon_auto.im_auto); a guest seat has no car.

Off by default: the admin's switch dungeonechtwuerfel (features.py, chat.dungeon_echtwuerfel) for the round's host.
The number is data: only the own seat, only whole numbers 1 to 20, only for the turn asked, an own rate limit.
State in the round (dungeon.py's rounds file), only while a turn waits for numbers:
    rd["echt_frage"]  {"zug", "t", "plaetze": {pid: {"fragen": [{"wert", "schwer", "n"} | {"angriff": True, "gegner",
                      "n"}], "zahlen": [..] | None, "max": seconds}}}
    rd["echt_aus"]    {pid: turns in a row without a number}; from AUS_N on the seat waits only KURZ_S
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
KURZ_S = 10                # a seat that did not throw AUS_N times in a row waits only this long (T14)
AUS_N = 2
TAKT_S = 0.5               # how often the waiting turn looks for the numbers
SEITEN = 20                # a d20: 1 to 20
BODY = 512

_day = DayCounter(gefragt=0, echt=0, rueckfall=0, abgelehnt=0, angriff=0, kurz=0)


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


def seats(rd, proben, angriffe=()):
    """{pid: [questions]}: the checks of this turn whose seat throws its own die; angriffe [(pid, foe's name)]: the
    heroes attacking this fight turn (dungeon_kampf.attackers), one question each instead of their checks."""
    out = {}
    ok = lambda pid: pid in (rd.get("echt") or []) and (rd["plaetze"].get(pid) or {}).get("held") \
        and not _im_auto((rd["plaetze"].get(pid) or {}).get("uid"))
    hit = {pid for pid, _ in angriffe}
    for p in proben or []:
        pid = p.get("pid")
        if pid in hit or not ok(pid):
            continue
        out.setdefault(pid, []).append({"wert": p.get("wert", ""), "schwer": int(p.get("schwer") or 0), "n": 2 if p.get("vt") else 1})
    for pid, gegner in angriffe:
        if ok(pid):
            out[pid] = [{"angriff": True, "gegner": gegner or "", "n": 1}]
    return out


def attacking(dm, rd, proben):
    """[(pid, foe's name)]: the heroes who attack this fight turn by the panel's rules; a hero a prop of the fight took
    (dungeon_umgebung's check) makes that check instead."""
    if not rd.get("kampf"):
        return []
    import dungeon_kampf
    prop = {p.get("pid") for p in proben or [] if p.get("umgebung")}
    first = next((g for g in dungeon_kampf.up(rd) if g["leben"] > 0), None)   # none named: the first standing (as attacks)
    return [(p["pid"], (g or first or {}).get("name", "")) for p, g, _ in dungeon_kampf.attackers(dm, dm.rules(), rd, proben, skip=prop)]


def wait_s(rd, pid):
    """How long the turn waits for this seat: KURZ_S after AUS_N turns in a row without its number, else WARTE_S."""
    return KURZ_S if (rd.get("echt_aus") or {}).get(pid, 0) >= AUS_N else WARTE_S


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
    ask = seats(rd, proben, attacking(dm, rd, proben))
    if not ask:
        return None
    frist = {pid: wait_s(rd, pid) for pid in ask}

    def put():
        with dm._lock:
            d = dm._read()
            cur = d["runden"].get(rid)
            if not cur or cur["zug"] != turn:
                return False
            cur["echt_frage"] = {"zug": turn, "t": time.time(), "plaetze": {pid: {"fragen": f, "zahlen": None, "max": frist[pid]} for pid, f in ask.items()}}
            if cur.get("dm"):
                dm.warten.step(cur, "wuerfeln")
            dm._write(d)
            return True

    if not await asyncio.to_thread(put):
        return None
    _day.bump("gefragt", len(ask))
    n_ang, n_kurz = sum(1 for f in ask.values() if f[0].get("angriff")), sum(1 for x in frist.values() if x == KURZ_S)
    _day.bump("angriff", n_ang)
    _day.bump("kurz", n_kurz)
    print(f"dungeon: echt | frage | {len(ask)} plaetze | {n_ang} angriff | {n_kurz} kurz", flush=True)
    t0 = time.monotonic()
    got = {}
    while True:
        cur = (await asyncio.to_thread(dm._read))["runden"].get(rid) or {}
        q = cur.get("echt_frage") or {}
        if q.get("zug") != turn:
            break
        got = {pid: x["zahlen"] for pid, x in q["plaetze"].items() if x.get("zahlen")}
        el = time.monotonic() - t0
        if all(pid in got or el >= frist[pid] for pid in ask):
            break
        await asyncio.sleep(TAKT_S)

    def clear():
        with dm._lock:
            d = dm._read()
            cur = d["runden"].get(rid)
            if cur and (cur.get("echt_frage") or {}).get("zug") == turn:
                cur.pop("echt_frage", None)
                aus = dict(cur.get("echt_aus") or {})
                for pid in ask:                   # a seat that threw is back to the long wait
                    if pid in got:
                        aus.pop(pid, None)
                    else:
                        aus[pid] = min(9, aus.get(pid, 0) + 1)
                if aus:
                    cur["echt_aus"] = aus
                else:
                    cur.pop("echt_aus", None)
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


def choice(rd):
    """The host's console (Am Tisch): the seats with a hero and whether each throws its own d20; None while the admin's
    switch is off for the host."""
    if not rd.get("owner") or not features.allowed(KEY, rd["owner"]):
        return None
    on_ = set(rd.get("echt") or [])
    return [{"pid": pid, "name": p["held"]["name"], "an": pid in on_, "auto": _im_auto(p.get("uid"))}
            for pid, p in rd["plaetze"].items() if p.get("held")]


def choose(rd, pids):
    """The host's choice {echt: [pid, …]}: only seats of the round with a hero, each once, only with the admin's switch
    (a seat in the car stays chosen, it is only not asked while it drives)."""
    ok = isinstance(pids, list) and len(pids) <= len(rd["plaetze"]) and all(isinstance(p, str) for p in pids) \
        and len(set(pids)) == len(pids) and all((rd["plaetze"].get(p) or {}).get("held") for p in pids)
    if not ok or not rd.get("owner") or not features.allowed(KEY, rd["owner"]):
        print("dungeon: echt | plaetze | abgelehnt", flush=True)
        raise ValueError("eingabe")
    if pids:
        rd["echt"] = list(pids)
    else:
        rd.pop("echt", None)
    aus = {k: v for k, v in (rd.get("echt_aus") or {}).items() if k in pids}
    if aus:
        rd["echt_aus"] = aus
    else:
        rd.pop("echt_aus", None)


def view(rd, pid, now=None):
    """What a seat sees of the question: its own questions with the seconds left, the names of the others still
    throwing; None while nothing is asked."""
    q = rd.get("echt_frage")
    if not q:
        return None
    now = time.time() if now is None else now
    names = {p: (x.get("held") or {}).get("name", "") for p, x in rd["plaetze"].items()}
    me = q["plaetze"].get(pid)
    mx = (me or {}).get("max", WARTE_S)
    return {"zug": q["zug"], "rest": max(0, round(mx - (now - q["t"]))), "max": mx, "seiten": SEITEN,
            "fragen": me["fragen"] if me and not me.get("zahlen") else [], "fertig": bool(me and me.get("zahlen")),
            "andere": sorted(names[p] for p, x in q["plaetze"].items() if p != pid and not x.get("zahlen") and names.get(p))}


def for_live():
    """Numbers only: seats asked, numbers given, turns the panel rolled itself after the wait, refused inputs, attacks
    asked and short waits today."""
    t = _day.counts()
    return {k: t[k] for k in ("gefragt", "echt", "rueckfall", "abgelehnt", "angriff", "kurz")}


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
