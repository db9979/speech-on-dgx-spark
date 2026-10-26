"""KI-Dungeon-Master: Knapp daneben, Erfolg mit Preis (D&D ideas round 2, idea 1, Dominik 2026-10-26 „1-9 umsetzten
reihenfolge überlasse ich dir.“; the idea „Pay the Price“ of Ironsworn and Starforged by Shawn Tomkin, via datasworn,
CC BY 4.0; the price texts are own ones of the thread „DnDAppFiles für den Dungeon-Master“).

A check (never an attack) that misses its difficulty by 1 to KNAPP, and is no natural 1, asks its seat once in the turn:
give up, or pass at a price? The seat answers within WARTE_S; no answer gives up, as without the switch. Paying rolls a
d20 on the price table („ideen“ → „knapp“ of dungeon_srd.json; at the children's table only the mild rows): the check
counts as passed, the receipt says "knapp" and "preis" (the row's id), the narration gets the price's line as data.
The price works by a fixed rule of the panel (pay): laerm makes noise on the map (dungeon_karte.laerm, once the map
thread has it), nachteil gives the hero's next check a disadvantage, schaden costs 1d4 life (never below 1), werkzeug
breaks a tool of the bag (the smith of a settlement mends it), gold costs up to GOLD gold, zeit and nsc stay in the story.
Never in the car: a seat that plays from the car is not asked (dungeon_echt._im_auto). The model decides nothing.

Off by default: the admin's switch dungeonknapp (features.py, chat.dungeon_knapp) for the round's host.
State in the round, only while a turn waits for the answers:
    rd["knapp_frage"]  {"zug", "t", "plaetze": {pid: {"frage": {"wert", "schwer", "gesamt", "wofuer"}, "wahl": None | "zahlen" | "aufgeben"}}}
Journal: fixed words and numbers („dungeon: knapp | …“), Live only counts.

    POST /api/profile/dungeon/{rid}/knapp   {zug, wahl}: the seat's choice (a profile)
    POST /api/dungeon/knapp                 {code, zug, wahl}: the same for a guest's seat
"""
import asyncio
import random
import time

from fastapi import APIRouter, Depends, Request

import features
import guard
from common import DayCounter
from core import assistant, browser_profile, json_body

router = APIRouter()
KEY = "dungeonknapp"
KNAPP = 2                  # a check missing by at most this much is a near miss
WARTE_S = 20               # the seats have this long to choose, then the check stays failed
TAKT_S = 0.5               # how often the waiting turn looks for the answers
WAHL = ("zahlen", "aufgeben")
GOLD = 10                  # the price „gold“: 1 to this much gold, never more than the hero has
SCHADEN = 4                # the price „schaden“: 1d4, never below 1 life
BODY = 256

_day = DayCounter(gefragt=0, gezahlt=0, aufgegeben=0, ohne_antwort=0, abgelehnt=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def table(r, rd, kids):
    """The rows a price is rolled on: the d20 table, at the children's table only its mild rows; [] without one."""
    rows = (r.get("ideen") or {}).get("knapp") or []
    return [x for x in rows if x.get("kinder")] if kids else list(rows)


def near(rd, wuerfe):
    """{pid: index}: the first near miss of each seat with a hero (not from the car) in this turn's checks."""
    import dungeon_echt
    out = {}
    for i, x in enumerate(wuerfe):
        seat = rd["plaetze"].get(x.get("pid")) or {}
        if x["pid"] in out or x["ok"] or x["w"] == 1 or not 1 <= x["schwer"] - x["gesamt"] <= KNAPP:
            continue
        if seat.get("held") and not dungeon_echt._im_auto(seat.get("uid")):
            out[x["pid"]] = i
    return out


def price(rows, rng, kids):
    """A row of the price table: the d20 on the whole table, one of the mild rows at the children's table."""
    if kids:
        return rng.choice(rows)
    w = rng.randint(1, 20)
    return next((x for x in rows if x["von"] <= w <= x["bis"]), rows[0])


async def ask(dm, rid, turn, r, rd, wuerfe, rng=None):
    """Asks the seats with a near miss and waits at most WARTE_S. Returns the checks, a paid one passed with its price
    ("knapp", "preis", "preis_art", "preis_t"); unchanged without the switch, a table or a near miss."""
    rng = rng or random
    kids = dm.kids(r, rd)
    rows = table(r, rd, kids)
    ask_ = near(rd, wuerfe) if on(rd) and rows else {}
    if not ask_:
        return wuerfe
    frage = {pid: {k: wuerfe[i].get(k, "") for k in ("wert", "schwer", "gesamt", "wofuer")} for pid, i in ask_.items()}

    def put():
        with dm._lock:
            d = dm._read()
            cur = d["runden"].get(rid)
            if not cur or cur["zug"] != turn:
                return False
            cur["knapp_frage"] = {"zug": turn, "t": time.time(), "plaetze": {pid: {"frage": f, "wahl": None} for pid, f in frage.items()}}
            dm._write(d)
            return True

    if not await asyncio.to_thread(put):
        return wuerfe
    _day.bump("gefragt", len(ask_))
    print(f"dungeon: knapp | frage | {len(ask_)} plaetze", flush=True)
    t0 = time.monotonic()
    got = {}
    while True:
        q = ((await asyncio.to_thread(dm._read))["runden"].get(rid) or {}).get("knapp_frage") or {}
        if q.get("zug") != turn:
            break
        got = {pid: x["wahl"] for pid, x in q["plaetze"].items() if x.get("wahl")}
        if len(got) == len(ask_) or time.monotonic() - t0 >= WARTE_S:
            break
        await asyncio.sleep(TAKT_S)

    def clear():
        with dm._lock:
            d = dm._read()
            cur = d["runden"].get(rid)
            if cur and (cur.get("knapp_frage") or {}).get("zug") == turn:
                cur.pop("knapp_frage", None)
                dm._write(d)

    await asyncio.to_thread(clear)
    li = 1 if rd.get("lang") == "en" else 0
    out = list(wuerfe)
    for pid, i in ask_.items():
        if got.get(pid) != "zahlen":
            _day.bump("aufgegeben" if got.get(pid) else "ohne_antwort")
            print(f"dungeon: knapp | {'aufgegeben' if got.get(pid) else 'ohne antwort'}", flush=True)
            continue
        row = price(rows, rng, kids)
        out[i] = dict(out[i], ok=True, knapp=True, preis=row["id"], preis_art=row["art"], preis_t=row["t"][li])
        _day.bump("gezahlt")
        print(f"dungeon: knapp | gezahlt | {row['art']}", flush=True)
    return out


def pay(dm, r, rd, h, w, rng=None):
    """The price of a paid near miss by its fixed rule, when the turn is told (dungeon.apply, before the receipt is
    logged: a broken tool goes the way of a natural 1's, "kaputt")."""
    rng = rng or random
    art = w.get("preis_art")
    if not h or not art:
        return
    if art == "laerm":
        import dungeon_karte
        f = getattr(dungeon_karte, "laerm", None)
        if f:
            f(rd, 1, "preis")
    elif art == "nachteil":
        h["nachteil_zug"] = rd.get("zug", 0) + 1       # dungeon.roll: the hero's checks of the next turn at a disadvantage
    elif art == "schaden":
        n = min(rng.randint(1, SCHADEN), h["leben"] - 1)
        if n > 0:
            h["leben"] -= n
            dm._log(rd, "folge", pid=w["pid"], name=h["name"], was="schaden", zahl=n, leben=h["leben"])
    elif art == "werkzeug":
        it = next((x for x in h.get("tasche") or [] if dm._c(r, x).get("art") == "werkzeug" and not (dm._c(r, x).get("hilft") or {}).get("fest")), None)
        if it and not w.get("kaputt"):
            w["kaputt"] = it["i"]
    elif art == "gold":
        n = min(h.get("gold", 0), rng.randint(1, GOLD))
        if n > 0:
            h["gold"] -= n
            dm._log(rd, "system", text=[f"{h['name']} zahlt {n} Gold.", f"{h['name']} pays {n} gold."])
    print(f"dungeon: knapp | preis | {art}", flush=True)


def give(rd, pid, zug, wahl):
    """The seat's choice for the turn asked: zahlen or aufgeben, once."""
    q = rd.get("knapp_frage") or {}
    if not isinstance(zug, int) or isinstance(zug, bool) or q.get("zug") != zug:
        raise TimeoutError("alter zug")
    me = (q.get("plaetze") or {}).get(pid)
    if not me:
        raise LookupError("platz")
    if me.get("wahl"):
        raise FileExistsError("eingabe")
    if wahl not in WAHL:
        raise ValueError("eingabe")
    me["wahl"] = wahl


def view(rd, pid, now=None):
    """What a seat sees: its own question with the seconds left, the names of the others still choosing; None while
    nothing is asked."""
    q = rd.get("knapp_frage")
    if not q:
        return None
    now = time.time() if now is None else now
    names = {p: (x.get("held") or {}).get("name", "") for p, x in rd["plaetze"].items()}
    me = q["plaetze"].get(pid)
    return {"zug": q["zug"], "rest": max(0, round(WARTE_S - (now - q["t"]))), "max": WARTE_S,
            "frage": me["frage"] if me and not me.get("wahl") else None, "fertig": bool(me and me.get("wahl")),
            "andere": sorted(names[p] for p, x in q["plaetze"].items() if p != pid and not x.get("wahl") and names.get(p))}


def for_live():
    """Numbers only: near misses asked, paid, given up, without an answer, refused inputs today."""
    t = _day.counts()
    return {k: t[k] for k in ("gefragt", "gezahlt", "aufgegeben", "ohne_antwort", "abgelehnt")}


# ---------------------------------------------------------------- routes
async def _give(rid, seat, b):
    import dungeon as dm

    def go():
        pid = seat()
        with dm._lock:
            d = dm._read()
            give(dm._round(d, rid), pid, b.get("zug"), b.get("wahl"))
            dm._write(d)
        return dm.view(rid, pid)
    try:
        v = await asyncio.to_thread(go)
    except dm.KNOWN as e:
        _day.bump("abgelehnt")
        print(f"dungeon: knapp | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)
    print(f"dungeon: knapp | gewaehlt | {b.get('wahl')}", flush=True)
    return v


@router.post("/api/profile/dungeon/{rid}/knapp", dependencies=[Depends(assistant)])
async def knapp(rid: str, request: Request, prof=Depends(browser_profile)):
    """A near miss: {zug, wahl} (zahlen or aufgeben)."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonknapp", uid)
    b = await json_body(request, BODY)
    return await _give(rid, lambda: dm._seat_uid(rid, uid), b)


@router.post("/api/dungeon/knapp")
async def gast_knapp(request: Request):
    """{"code", "zug", "wahl"}: a guest's seat chooses."""
    import dungeon as dm
    b, rid, pid = await dm._guest(request, BODY)
    guard.limit(request, "dungeonknapp")
    return await _give(rid, lambda: pid, b)
