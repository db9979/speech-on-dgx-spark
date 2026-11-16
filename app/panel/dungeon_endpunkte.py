"""KI-Dungeon-Master: the endpoints (Prüfung 15.11., Punkt 10, dungeon.py split). The own page (/api/profile/dungeon/*),
a guest's seat (/api/dungeon/*) and the admin's rules and stories (/api/admin/dungeon/*), on their own router (panel.py includes it where dungeon's stood). Every
rule, every helper and every state stays in dungeon.py and is reached as dm.NAME at call time, so a test that swaps a
helper of dungeon (ask_model, spawn, rules …) reaches the endpoints too. Only this module imports dungeon, never the
other way round."""
import asyncio
import json
import os
import re
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
import dungeon_erzaehler as erz
import dungeon_kampf as kampf
import dungeon_mut as mut
import dungeon_anleiten as anleiten
import dungeon_personen as personen
import dungeon_grenzen as grenzen
import dungeon_zufall as zufall
import dungeon_fraktionen as fraktionen
import dungeon_orakel as orakel
import dungeon_geben as geben
import dungeon_warten as warten
import dungeon_stimmen as stimmen
import dungeon_gast as gastkonto
import dungeon_auto as auto_car
import dungeon_echt as echt
import dungeon_schrift as schrift
import dungeon_tiefe
import guard
import mfa
import profiles
from common import write_json
from core import assistant, auth, browser_profile, json_body, own_profile

import dungeon as dm

router = APIRouter()


# ---------------------------------------------------------------- the profile's endpoints
def _mine(uid, lang):
    r = dm.rules()
    now = time.time()
    out = []
    d = dm._read()
    for rid, v in d["runden"].items():
        pid, p = dm.seat_of(v, uid)
        if pid and uid not in (v.get("weg") or []) and (v.get("status") != "ende" or now - v.get("ende_t", 0) < dm.ENDE_H * 3600):
            out.append({"rid": rid, "titel": v["titel"], "welt": v["welt"], "status": v["status"], "zug": v["zug"], "gastgeber": v["owner"] == uid,
                        "pause": v["status"] == "laeuft" and bool(v.get("pause")),     # „Pause“ wherever the round shows
                        **({"ehrungen": v["ehrung"]} if v["status"] == "ende" and v.get("ehrung") else {}),   # D&D idea 1
                        "kapitel": v.get("kapitel", 0), "kapitel_zu": bool(v.get("kapitel_zu")),
                        "spieler": len(dm.seated(v)), "made": v["made"], "held": p["held"]["name"] if p.get("held") else ""})
    return {"on": True, "runden": sorted(out, key=lambda x: -x["made"]), "helden": [dm.hero_view(r, h, lang) for h in dm.heroes(uid)],
            "wahl": dict(dm._choices(lang, uid=uid), bilder_an=dm.pictures_on(uid), **dm._own_stories(uid)), "runden_max": dm.RUNDEN_MAX, "helden_max": dm.HELDEN_MAX,
            "kampagnen": dm.campaign_view(r, uid, lang), "kampagnen_max": dm.KAMPAGNEN_MAX, "bisher_max": dm.BISHER_MAX,
            "schnell": dm.quick(r, uid, d)}


@router.get("/api/profile/dungeon", dependencies=[Depends(assistant)])
def show(request: Request, prof=Depends(own_profile)):
    dm._need(prof["id"])
    guard.limit(request, "dungeon", prof["id"])
    return _mine(prof["id"], "en" if request.query_params.get("lang") == "en" else "de")


@router.post("/api/profile/dungeon/runde", dependencies=[Depends(assistant)])
async def neue_runde(request: Request, response: Response, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY + dm.PROMPT_MAX * 3)
    try:
        rid = await asyncio.to_thread(dm.make_round, uid, b, dm._lang(b))
    except dm.KNOWN as e:
        raise dm._http(e)
    await asyncio.to_thread(mark_device, rid, uid, dm.device(_device_cookie(request, response)))
    dm._go(dm.run_prolog(rid), name="dungeon-prolog")
    return await asyncio.to_thread(dm.view, rid, dm._seat_uid(rid, uid))


@router.post("/api/profile/dungeon/auto", dependencies=[Depends(assistant)])
async def auto(request: Request, prof=Depends(browser_profile)):
    """The game in the car (CarPlay, dungeon_auto.py): the iPhone app reads aloud what comes back and listens."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonauto", uid)
    b = await json_body(request, dm.BODY)
    nach = b.get("nach") if isinstance(b.get("nach"), int) and not isinstance(b.get("nach"), bool) else 0
    rid = b.get("rid") if isinstance(b.get("rid"), str) and dm._RID.fullmatch(b["rid"]) else ""
    wahl = [g for g in b.get("wahl") or [] if isinstance(g, str)][:auto_car.WAHL] if isinstance(b.get("wahl"), list) else None
    try:
        out = await asyncio.to_thread(auto_car.car, uid, str(b.get("text") or ""), nach, dm._lang(b), rid, b.get("ok") is True,
                                      b.get("neu") is True, wahl, b.get("rf") is True)
    except dm.KNOWN as e:
        raise dm._http(e)
    if out.pop("prolog", None):          # a new round chosen in the car opens like one made at the table
        dm._go(dm.run_prolog(out["rid"]), name="dungeon-prolog")
    return out


@router.get("/api/profile/dungeon/{rid}", dependencies=[Depends(assistant)])
async def runde(rid: str, request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    try:
        pid = await asyncio.to_thread(dm._seat_uid, rid, uid)
        await asyncio.to_thread(dm.maybe_close, rid)
        dm._go(dm.hero_voices(), name="dungeon")
        return await asyncio.to_thread(dm.look, rid, pid, request.query_params.get("stand", "")[:32])
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/aktion", dependencies=[Depends(assistant)])
async def aktion(rid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    return await dm._act(rid, lambda: dm._seat_uid(rid, uid), b)


def more_time(rid, pid):
    """One more minute for the open turn, once per seat and turn (Dominik 2026-10-24 „1-5“, point 4)."""
    with dm._lock:
        d = dm._read()
        rd = dm._round(d, rid)
        if rd["status"] != "laeuft" or rd.get("dm") or not (rd["plaetze"].get(pid) or {}).get("held"):
            print("dungeon: mehrzeit | nicht jetzt", flush=True)
            raise TimeoutError("zug")
        mehr = rd.setdefault("mehr", {})
        if pid in mehr:
            print("dungeon: mehrzeit | schon", flush=True)
            raise FileExistsError("mehrzeit")
        mehr[pid] = rd["zug"]
        dm._write(d)
    print("dungeon: mehrzeit | ok", flush=True)


async def _more(rid, seat):
    def go():
        pid = seat()
        more_time(rid, pid)
        return dm.view(rid, pid)
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/mehrzeit", dependencies=[Depends(assistant)])
async def mehrzeit(rid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    await json_body(request, dm.BODY)
    return await _more(rid, lambda: dm._seat_uid(rid, uid))


@router.post("/api/profile/dungeon/{rid}/held", dependencies=[Depends(assistant)])
async def held(rid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        pid = dm._seat_uid(rid, uid)
        out = dm.hero_act(rid, pid, b)
        return dict(dm.view(rid, pid), **(out or {}))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/weiter", dependencies=[Depends(assistant)])
async def weiter(rid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)

    def go():
        dm._host(rid, uid)
        if not dm.maybe_close(rid, force=True):
            raise ValueError("keine aktion")
        print("dungeon: weiter | gastgeber", flush=True)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


def set_pause(rid, uid, an):
    """The host pauses the round or goes on (the page's button, the car's „Runde pausieren“); the clock starts anew.
    The other seats that take notes get one („… ist pausiert“, „… geht weiter“) when the state changed (Dominik
    2026-10-26 „da wo man es überall sieht, dass da ein Spiel läuft“)."""
    with dm._lock:
        d = dm._read()
        rd = dm._round(d, rid)
        if rd["owner"] != uid or rd["status"] == "ende":
            raise LookupError("gastgeber")
        neu = bool(an) != bool(rd.get("pause"))
        rd["pause"] = bool(an)
        rd["zug_t"], rd["lesen"] = time.time(), 0
        dm._write(d)
        notes = [(p["uid"], "pause" if an else "weiter") for p in rd["plaetze"].values() if dm._wants(p) and p["uid"] != uid] if neu else []
        copy = dict(rd, rid=rid)
    print(f"dungeon: pause | {'an' if an else 'aus'}", flush=True)
    if notes:
        dm._go(dm.send_notes(copy, notes), name="dungeon-melden")


@router.post("/api/profile/dungeon/{rid}/pause", dependencies=[Depends(assistant)])
async def pause(rid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        set_pause(rid, uid, b.get("an"))
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/melden", dependencies=[Depends(assistant)])
async def melden(rid: str, request: Request, prof=Depends(browser_profile)):
    """„Mitteilungen“ of the own seat on or off (a note when it is your turn, a reminder, the game date)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        pid = dm._seat_uid(rid, uid)
        with dm._lock:
            d = dm._read()
            dm._round(d, rid)["plaetze"][pid]["melden"] = bool(b.get("an"))
            dm._write(d)
        print(f"dungeon: melden | {'an' if b.get('an') else 'aus'}", flush=True)
        return dm.view(rid, pid)
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/daumen", dependencies=[Depends(assistant)])
async def daumen(rid: str, request: Request, prof=Depends(browser_profile)):
    """{zug, gut, grund?}: the own seat's 👍/👎 for the narration of that turn (numbers for the admin, the model learns nothing;
    a 👎 with a fixed reason becomes a case while the narrator bench is on)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        if "aktion" in b:
            return {"mut": await asyncio.to_thread(lambda: praise(rid, dm._seat_uid(rid, uid), b))}
        return await asyncio.to_thread(lambda: erz.thumb(dm._me, rid, dm._seat_uid(rid, uid), b.get("zug"), b.get("gut"), b.get("grund")))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/grenzen", dependencies=[Depends(assistant)])
async def grenzen_setzen(rid: str, request: Request, prof=Depends(browser_profile)):
    """{linien, schleier}: the own seat's lines and veils (Tabletop-Punkt 18); {x: true} lays the X-Karte."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        return await asyncio.to_thread(limits_of, rid, dm._seat_uid(rid, uid), b)
    except dm.KNOWN as e:
        raise dm._http(e)


def limits_of(rid, pid, b):
    """{x: true}: the X-Karte (dungeon_grenzen.lay), else the seat's two lists; returns the table's view."""
    if b.get("x") is True:
        grenzen.lay(dm._me, rid, pid)
        return dm.view(rid, pid)
    with dm._lock:
        d = dm._read()
        rd = dm._round(d, rid)
        grenzen.put(dm._me, rd, pid, b)
        dm._write(d)
    return dm.view(rid, pid)


def praise(rid, pid, b):
    """{zug, aktion}: the seat's 👍 for another seat's action, for Heldenmut (dungeon_mut.praise). Returns the seat's
    Heldenmut as the table shows it."""
    with dm._lock:
        d = dm._read()
        rd = dm._round(d, rid)
        mut.praise(rd, pid, b.get("zug"), b.get("aktion"), [p for p, _ in dm.seated(rd)])
        dm._write(d)
        return mut.view(rd, pid)


@router.post("/api/profile/dungeon/{rid}/tisch", dependencies=[Depends(assistant)])
async def tisch(rid: str, request: Request, prof=Depends(browser_profile)):
    """{text}: one line of table talk between the seats of the round; the model never sees it (5j)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeontisch", uid)
    b = await json_body(request, dm.BODY)
    return await _talk(rid, lambda: dm._seat_uid(rid, uid), b)


async def _talk(rid, seat, b):
    def go():
        pid = seat()
        with dm._lock:
            d = dm._read()
            warten.talk(dm._me, dm._round(d, rid), pid, b.get("text"), time.time())
            dm._write(d)
        return dm.view(rid, pid)
    try:
        v = await asyncio.to_thread(go)
    except dm.KNOWN as e:
        print(f"dungeon: tisch | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)
    dm._day.bump("tisch")
    print("dungeon: tisch | gesagt", flush=True)
    return v


@router.post("/api/profile/dungeon/{rid}/tippt", dependencies=[Depends(assistant)])
async def tippt(rid: str, request: Request, prof=Depends(browser_profile)):
    """A keystroke in the own action field: the others see „X schreibt …“ for a few seconds (kept in memory only)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeontippt", uid)
    await json_body(request, dm.BODY)
    try:
        warten.typing(rid, await asyncio.to_thread(dm._seat_uid, rid, uid))
    except dm.KNOWN as e:
        raise dm._http(e)
    return {"ok": True}


@router.post("/api/profile/dungeon/{rid}/wurf", dependencies=[Depends(assistant)])
async def wurf(rid: str, request: Request, prof=Depends(browser_profile)):
    """The seat throws its own die (tap or shake): the number the panel rolled shows for the others too."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonwurf", uid)
    await json_body(request, dm.BODY)
    return await _throw(rid, lambda: dm._seat_uid(rid, uid))


async def _throw(rid, seat):
    def go():
        pid = seat()
        with dm._lock:
            d = dm._read()
            hit = warten.throw(dm._round(d, rid), pid)
            if hit:
                dm._write(d)
        return hit, dm.view(rid, pid)
    try:
        hit, v = await asyncio.to_thread(go)
    except dm.KNOWN as e:
        print(f"dungeon: wurf | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)
    if hit:
        dm._day.bump("geworfen")
    print(f"dungeon: wurf | {'geworfen' if hit else 'keiner'}", flush=True)
    return v


@router.post("/api/profile/dungeon/{rid}/termin", dependencies=[Depends(assistant)])
async def termin(rid: str, request: Request, prof=Depends(browser_profile)):
    """The host sets the next game date (t epoch seconds, 0 takes it back)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        dm.set_date(uid, rid, b.get("t"))
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


def _ics_out(rd, rid):
    return Response(dm.ics(rd, rid), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="dungeon-master.ics"'})


@router.get("/api/profile/dungeon/{rid}/termin.ics", dependencies=[Depends(assistant)])
async def termin_ics(rid: str, request: Request, prof=Depends(own_profile)):
    """The game date as a calendar file, for a seat of the round."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    try:
        dm._seat_uid(rid, uid)
        r = _ics_out(dm._round(dm._read(), rid), rid)
    except dm.KNOWN as e:
        raise dm._http(e)
    print("dungeon: termin | kalender", flush=True)
    return r


@router.post("/api/profile/dungeon/{rid}/markt", dependencies=[Depends(assistant)])
async def markt(rid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        r = dm.rules()
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            if b.get("auf") and rd.get("kampf"):
                raise FileExistsError("markt kampf")   # Review 27.10. Paket 3: first the fight
            if b.get("auf") and not rd.get("markt"):
                dm.open_market(r, rd)
            elif not b.get("auf"):
                dm.close_market(rd)
            dm._write(d)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "the panel's address is missing (base)")
    return base


@router.post("/api/profile/dungeon/{rid}/platz", dependencies=[Depends(assistant)])
async def platz(rid: str, request: Request, prof=Depends(browser_profile)):
    """{"base": "https://panel"} -> a seat link with its QR code, shown once."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    base = _base(b)
    try:
        pid, code = await asyncio.to_thread(dm.make_seat, uid, rid, None, base)
    except dm.KNOWN as e:
        raise dm._http(e)
    link = f"{base}/#spiel={code}"
    return dict(await asyncio.to_thread(dm.view, rid, await asyncio.to_thread(dm._seat_uid, rid, uid)), link=link, qr=mfa._qr_svg(link), neu=pid)


@router.put("/api/profile/dungeon/{rid}/platz/{pid}", dependencies=[Depends(assistant)])
async def platz_aendern(rid: str, pid: str, request: Request, prof=Depends(browser_profile)):
    """The host on a fellow player's seat: {"was": "link", "base"} a new link with its QR code (shown once),
    {"was": "ruhen"|"wecken"} not waited for / waited for again, {"was": "name", "name"} the hero's new name."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        if not dm._PID.fullmatch(pid):
            raise LookupError("platz")
        base = _base(b) if b.get("was") == "link" else ""
        code = await asyncio.to_thread(dm.manage_seat, uid, rid, pid, b.get("was"), b.get("name"))
        out = await asyncio.to_thread(dm.view, rid, await asyncio.to_thread(dm._seat_uid, rid, uid))
    except dm.KNOWN as e:
        raise dm._http(e)
    if code:
        link = f"{base}/#spiel={code}"
        out = dict(out, link=link, qr=mfa._qr_svg(link))
    return out


@router.post("/api/profile/dungeon/{rid}/verbergen", dependencies=[Depends(assistant)])
async def verbergen(rid: str, request: Request, prof=Depends(browser_profile)):
    """The host hides a line: {"art": "tisch", "n"} a line of table talk, {"art": "aktion", "n", "pid"} a seat's action
    of turn n (Punkt 13 of 2026-10-24)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        pid = b.get("pid") or ""
        if b.get("art") == "aktion" and not (isinstance(pid, str) and dm._PID.fullmatch(pid)):
            raise LookupError("platz")
        await asyncio.to_thread(dm.hide_line, uid, rid, b.get("art"), b.get("n"), pid)
        return await asyncio.to_thread(dm.view, rid, await asyncio.to_thread(dm._seat_uid, rid, uid))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.delete("/api/profile/dungeon/{rid}/platz/{pid}", dependencies=[Depends(assistant)])
async def platz_weg(rid: str, pid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)
    try:
        if not dm._PID.fullmatch(pid) or not await asyncio.to_thread(dm.drop_seat, uid, rid, pid):
            raise LookupError("platz")
        return await asyncio.to_thread(dm.view, rid, await asyncio.to_thread(dm._seat_uid, rid, uid))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.delete("/api/profile/dungeon/daten", dependencies=[Depends(assistant)])
async def daten_loeschen(request: Request, prof=Depends(browser_profile)):
    """The own game data (before /{rid}, which would take „daten“ for a round): allowed also while the admin blocked the game for this profile (Richtlinie Teil 3)."""
    guard.limit(request, "dungeon", prof["id"])
    await asyncio.to_thread(dm.own_clear, prof["id"])
    return {"ok": True}


@router.delete("/api/profile/dungeon/{rid}", dependencies=[Depends(assistant)])
async def beenden(rid: str, request: Request, prof=Depends(browser_profile)):
    """The host ends the round (also while blocked: own data); the heroes of profiles are kept. An ended round goes:
    the host deletes it with its sounds and pictures, a player only takes it off the own list (Dominik 2026-10-23
    „alte runden sollen gelöscht werden können“). ?loeschen=1: the host ends a running round and deletes it at once,
    the heroes kept as on every end (Dominik 2026-10-25 „runden sollen immer löschbar bzw. beendbar sein. mit nachfrage
    wirklich.“, the list asks first)."""
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)
    weg = request.query_params.get("loeschen") == "1"

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            pid, _ = dm.seat_of(rd, uid)
            what = ""
            if weg and rd["owner"] == uid and rd["status"] != "ende":
                dm._end(rd, time.time(), "geloescht", rid)
            if rd["status"] == "ende" and rd["owner"] == uid:
                del d["runden"][rid]
                dm._ton_drop(rid)
                dm._bild_drop(rid)
                what = "geloescht"
            elif rd["status"] == "ende" and pid:
                rd["weg"] = sorted(set(rd.get("weg") or []) | {uid})
                what = "ausgeblendet"
            elif rd["owner"] != uid:
                raise LookupError("gastgeber")
            else:
                dm._end(rd, time.time(), "gastgeber", rid)
            dm._write(d)
        if what:
            print(f"dungeon: runde | {what}", flush=True)
        return _mine(uid, rd["lang"])
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/vorlesen", dependencies=[Depends(assistant)])
async def vorlesen(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: {an: bool} reads every narration aloud from the next turn on."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            rd["vorlesen"] = bool(b.get("an"))
            dm._write(d)
        print(f"dungeon: vorlesen | {'an' if b.get('an') else 'aus'}", flush=True)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/orakel", dependencies=[Depends(assistant)])
async def orakel_fragen(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: {frage?, wahrscheinlichkeit?, tabellen?, chaos?} asks the oracle or rolls its tables (Tabletop-Punkt 8,
    dungeon_orakel.ask); the answer is a line in the feed."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            orakel.ask(dm._me, dm.rules(), rd, b)
            dm._write(d)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.get("/api/profile/dungeon/{rid}/geben", dependencies=[Depends(assistant)])
async def geben_liste(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host as admin: the catalog things this round's world may get (dungeon_geben.catalog), once for the console."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    if not geben.admin(request, uid):
        print("dungeon: geben | kein admin", flush=True)
        raise dm._http(PermissionError("geben admin"))

    def go():
        rd = dm._host(rid, uid)
        if not geben.on(rd):
            raise PermissionError("geben aus")
        return {"dinge": geben.catalog(dm._me, dm.rules(), rd, rd["lang"])}
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/geben", dependencies=[Depends(assistant)])
async def geben_an(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host as admin: {an, art, id?, s?, n} gives a hero a catalog thing, gold, runes or experience by the game's rules
    (Dominik 2026-10-28 „1a 2a 3a 4a 5a“, dungeon_geben.give); a fixed line at the table."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    if not geben.admin(request, uid):                     # the own login acting as admin, never a guest or a manager
        print("dungeon: geben | kein admin", flush=True)
        raise dm._http(PermissionError("geben admin"))

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            geben.give(dm._me, dm.rules(), rid, rd, uid, b)
            dm._write(d)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/fraktion", dependencies=[Depends(assistant)])
async def fraktion_setzen(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: {name, will?, felder?, schritt?, weg?} adds an own faction, changes one, turns its clock a field or takes
    it away (Tabletop-Punkt 7, dungeon_fraktionen.host)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            was = fraktionen.host(dm._me, dm.rules(), rd, b)
            dm._write(d)
        print(f"dungeon: fraktion | gastgeber | {was}", flush=True)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        print("dungeon: fraktion | abgelehnt", flush=True)
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/zufall", dependencies=[Depends(assistant)])
async def zufall_setzen(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: {regeln} the round's own random rules (Tabletop-Punkt 9, dungeon_zufall.put), all of them replaced."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            zufall.put(dm._me, rd, b)
            dm._write(d)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/erzaehler", dependencies=[Depends(assistant)])
async def erzaehler(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: {k} one of the world's narrator voices, "" rolls a new one (dungeon_stimmen.choose); or {weise} the round's
    way of telling (WEISEN) from the next turn on; or {anleitung} the level of „Spieler anleiten“ (dungeon_anleiten.STUFEN);
    or {regler_fest} holds the game master's dial (Idee 6) or lets it go;
    or {kampfstufe} the stage of the next encounters (leicht, mittel, schwer, toedlich; Tabletop-Punkt 13);
    or {mail_vorschau} the narrator's last sentence in a guest's „Du bist dran“ mail (on unless switched off);
    or {echt: [pid, …]} the seats that throw their own d20 at the real table (dungeon_echt.choose, D&D idea 5);
    or {schrift: {id, sicht}} who sees a writing: alle, niemand or one seat (dungeon_schrift.set_sight, D&D idea 3);
    or {tiefe} the round's Regeltiefe einfach or voll, or {nur_narben} wounds keep to their look (dungeon_tiefe, Ausdünnen 1)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            if rd["owner"] != uid or rd["status"] == "ende":
                raise LookupError("gastgeber")
            if "regler_fest" in b:
                if not isinstance(b["regler_fest"], bool) or not kampf.dial_on(rd):
                    raise ValueError()
                rd["regler_fest"] = b["regler_fest"]
            elif "tiefe" in b:                        # Regeltiefe (Ausdünnen 1): the extra rules of „voll“ from the next turn on
                dungeon_tiefe.choose(rd, b["tiefe"])
            elif "nur_narben" in b:
                if not isinstance(b["nur_narben"], bool):
                    raise ValueError()
                rd["nur_narben"] = b["nur_narben"]
            elif "kampfstufe" in b:                   # Budget-Stufen (Tabletop-Punkt 13): how hard the next encounters are
                if b["kampfstufe"] not in kampf.STUFEN or not kampf.stages_on(rd):
                    raise ValueError()
                rd["kampfstufe"] = b["kampfstufe"]
            elif "mail_vorschau" in b:
                if not isinstance(b["mail_vorschau"], bool):
                    raise ValueError()
                rd["mail_vorschau"] = b["mail_vorschau"]
            elif "echt" in b:
                echt.choose(rd, b["echt"])
            elif "schrift" in b:
                if not isinstance(b["schrift"], dict):
                    raise ValueError()
                schrift.set_sight(rd, b["schrift"].get("id"), b["schrift"].get("sicht"))
            elif "weise" in b:
                if b["weise"] not in dm.WEISEN:
                    raise ValueError()
                rd["erzaehlweise"] = b["weise"]
            elif "anleitung" in b:
                anleiten.choose(rd, b["anleitung"])     # Spieler anleiten: the round's level
            else:
                stimmen.choose(rd, str(b.get("k") or ""))
            dm._write(d)
        if "regler_fest" in b:
            print(f"dungeon: regler | {'festgehalten' if b['regler_fest'] else 'frei'}", flush=True)
        elif "tiefe" in b:
            print(f"dungeon: regeltiefe | {b['tiefe']}", flush=True)
        elif "nur_narben" in b:
            print(f"dungeon: narbe | nur aussehen {'an' if b['nur_narben'] else 'aus'}", flush=True)
        elif "kampfstufe" in b:
            print(f"dungeon: kampfstufe | {b['kampfstufe']}", flush=True)
        elif "mail_vorschau" in b:
            print(f"dungeon: gastmail | vorschau {'an' if b['mail_vorschau'] else 'aus'}", flush=True)
        elif "echt" in b:
            print(f"dungeon: echt | plaetze | {len(b['echt'])}", flush=True)
        elif "schrift" in b:
            pass                                 # set_sight wrote its line
        elif "weise" in b:
            print(f"dungeon: erzaehlweise | {b['weise']}", flush=True)
        elif "anleitung" in b:
            print(f"dungeon: anleitung | stufe | {b['anleitung']}", flush=True)
        else:
            print(f"dungeon: erzaehler | {'gewaehlt' if b.get('k') else 'neu'}", flush=True)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/dinge", dependencies=[Depends(assistant)])
async def dinge(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: {n, weg} forgets kept thing n, {n, name, merkmale} fixes it (dungeon_erzaehler.edit_thing)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)

    def go():
        erz.edit_thing(dm._me, uid, rid, b.get("n"), b)
        return dm.view(rid, dm._seat_uid(rid, uid))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.get("/api/profile/dungeon/{rid}/ton/{n}/{k}", dependencies=[Depends(assistant)])
async def ton(rid: str, n: int, k: int, request: Request, prof=Depends(own_profile), mp3: int = 0):
    """Piece k of turn n read aloud (Punkt 16 of 2026-10-24), for a seat of the round; ?mp3=1 its MP3 copy."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonton", uid)
    try:
        data, media = await asyncio.to_thread(lambda: dm.ton_of(rid, dm._seat_uid(rid, uid), n, k, bool(mp3)))
    except dm.KNOWN as e:
        raise dm._http(e)
    return Response(data, media_type=media, headers={"Cache-Control": "no-store"})


@router.get("/api/profile/dungeon/{rid}/bild/{b}", dependencies=[Depends(assistant)])
async def bild(rid: str, b: str, request: Request, prof=Depends(own_profile)):
    """A scene picture of the round, for a seat of it."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    try:
        return dm._png_out(await asyncio.to_thread(lambda: dm.bild_of(rid, dm._seat_uid(rid, uid), b)))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.get("/api/profile/dungeon/{rid}/portraet/{pid}", dependencies=[Depends(assistant)])
async def portraet(rid: str, pid: str, request: Request, prof=Depends(own_profile)):
    """The portrait of the hero at seat pid, for a seat of the same round."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    try:
        return dm._png_out(await asyncio.to_thread(lambda: dm.portrait_of(rid, dm._seat_uid(rid, uid), pid)))
    except dm.KNOWN as e:
        raise dm._http(e)


async def _paint_start(request, key, go, lang):
    """A picture asked for by a seat (host: the scene; every seat: its portrait): the limits, then in the background."""
    guard.limit(request, "dungeonbild", key)
    try:
        coro = await asyncio.to_thread(go)
    except ValueError as e:
        dm._day.bump("abgelehnt")
        raise HTTPException(409, dm._nein(str(e), lang))
    except dm.KNOWN as e:
        raise dm._http(e)
    dm._go(coro, name="dungeon-bild")


@router.post("/api/profile/dungeon/{rid}/bild", dependencies=[Depends(assistant)])
async def bild_malen(rid: str, request: Request, prof=Depends(browser_profile)):
    """Host: „Szenenbild jetzt malen“ (the same limits as a new place)."""
    uid = prof["id"]
    dm._need(uid)
    b = await json_body(request, dm.BODY)
    await _paint_start(request, uid, lambda: dm.paint_scene(rid, *dm.paint_now(uid, rid)), dm._lang(b))
    return await asyncio.to_thread(dm.view, rid, dm._seat_uid(rid, uid))


@router.post("/api/profile/dungeon/{rid}/portraet", dependencies=[Depends(assistant)])
async def portraet_malen(rid: str, request: Request, prof=Depends(browser_profile)):
    """The own hero's portrait (once per level)."""
    uid = prof["id"]
    dm._need(uid)
    b = await json_body(request, dm.BODY)
    await _paint_start(request, uid, lambda: dm.paint_portrait(rid, *dm.queue_portrait(rid, dm._seat_uid(rid, uid))), dm._lang(b))
    return await asyncio.to_thread(dm.view, rid, dm._seat_uid(rid, uid))


@router.get("/api/profile/dungeon/held/{hid}/bild", dependencies=[Depends(assistant)])
async def held_bild(hid: str, request: Request, prof=Depends(own_profile)):
    """The portrait of an own kept hero (Meine Helden, the app)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)

    def go():
        h = next((x for x in dm.heroes(uid) if x["hid"] == hid), None)
        if not h or h.get("bild") is None:
            raise LookupError("bild")
        return dm._png("held-" + hid)
    try:
        return dm._png_out(await asyncio.to_thread(go))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.get("/api/profile/dungeon/kampagne/{kid}/bild/{n}", dependencies=[Depends(assistant)])
async def kampagne_bild(kid: str, n: int, request: Request, prof=Depends(own_profile)):
    """The cover of chapter n of an own campaign."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)

    def go():
        _, c = dm._campaign(uid, kid)
        if n not in (c.get("titelbilder") or []):
            raise LookupError("bild")
        return dm._png(f"{kid}-{n}")
    try:
        return dm._png_out(await asyncio.to_thread(go))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.get("/api/profile/dungeon/{rid}/probe", dependencies=[Depends(assistant)])
async def stimm_probe(rid: str, request: Request, stimme: str = "", klang: str = "", erzaehler: str = "", prof=Depends(own_profile)):
    """A fixed sentence in a voice the own hero at this table may take, or (erzaehler) one of the narrator voices of
    the round's world, as WAV."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonprobe", uid)
    try:
        await asyncio.to_thread(dm._seat_uid, rid, uid)
        if erzaehler:
            if erzaehler not in [x["k"] for x in stimmen.view(dm._round(dm._read(), rid), "de", True)["erzaehler_liste"]]:
                raise ValueError("stimme")
            stimme, klang = "", stimmen.probe_text(erzaehler)
        wav, ersatz = await dm.probe(stimme, "en" if request.query_params.get("lang") == "en" else "de", klang[:100],
                                  dm.voices(await asyncio.to_thread(dm.rules))["erzaehler"] if erzaehler else "")
    except dm.KNOWN as e:
        raise dm._http(e)
    except (RuntimeError, asyncio.TimeoutError) as e:
        print(f"dungeon: stimmprobe | fehler | {'klang' if klang else 'stimme'} | {str(e)[:20] or type(e).__name__}", flush=True)
        raise HTTPException(503, "Die Sprachausgabe ist gerade belegt.")
    return dm._probe_out(wav, ersatz)


@router.post("/api/profile/dungeon/{rid}/hoeren", dependencies=[Depends(assistant)])
async def hoeren(rid: str, request: Request, prof=Depends(browser_profile)):
    """{"wav"}: speak instead of type (base64 of a 16 kHz WAV), the text comes back for the own field."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonohr", uid)
    b = await json_body(request, dm.HOER_BYTES * 4 // 3 + dm.BODY)
    try:
        pid = await asyncio.to_thread(dm._seat_uid, rid, uid)
        return await dm.hear(rid, dm._wav_in(b), pid)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/profile/dungeon/{rid}/sitzcode", dependencies=[Depends(assistant)])
async def sitzcode(rid: str, request: Request, prof=Depends(browser_profile)):
    """The app's table: a code for the profile's own seat of the round (shown once, only its hash kept, a newer one
    replaces it, it ends with the round); the app opens <panel>/#spiel=<code> in its web view."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    code = secrets.token_urlsafe(24)

    def go():
        with dm._lock:
            d = dm._read()
            rd = dm._round(d, rid)
            pid, p = dm.seat_of(rd, uid)
            if not pid or rd["status"] == "ende":
                raise LookupError("platz")
            p["h"] = dm._hash(code)
            dm._write(d)
    try:
        await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)
    print("dungeon: sitzcode | app", flush=True)
    return {"code": code}


@router.post("/api/profile/dungeon/{rid}/kapitel", dependencies=[Depends(assistant)])
async def kapitel(rid: str, request: Request, prof=Depends(browser_profile)):
    """The host closes the chapter: the round ends into its campaign, „Bisher geschah“ is written in the background."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        kid = await asyncio.to_thread(dm.end_chapter, uid, rid)
    except dm.KNOWN as e:
        raise dm._http(e)
    dm._go(dm.summarize(uid, kid), name="dungeon")
    return dict(await asyncio.to_thread(_mine, uid, dm._lang(b)), kid=kid)


@router.put("/api/profile/dungeon/kampagne/{kid}", dependencies=[Depends(assistant)])
async def kampagne_aendern(kid: str, request: Request, prof=Depends(browser_profile)):
    """{"bisher"}: the host's own words for „Bisher geschah“ (the same checks as the model's)."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        await asyncio.to_thread(dm.edit_summary, uid, kid, b.get("bisher"))
    except dm.KNOWN as e:
        raise dm._http(e)
    return await asyncio.to_thread(_mine, uid, dm._lang(b))


@router.post("/api/profile/dungeon/kampagne/{kid}/neu", dependencies=[Depends(assistant)])
async def kampagne_neu_schreiben(kid: str, request: Request, prof=Depends(browser_profile)):
    """„Neu schreiben lassen“: the model writes „Bisher geschah“ of the last chapter again."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        await asyncio.to_thread(dm.rewrite_mark, uid, kid)
    except dm.KNOWN as e:
        raise dm._http(e)
    dm._go(dm.summarize(uid, kid), name="dungeon")
    return await asyncio.to_thread(_mine, uid, dm._lang(b))


@router.post("/api/profile/dungeon/kampagne/{kid}/weiter", dependencies=[Depends(assistant)])
async def kampagne_weiter(kid: str, request: Request, prof=Depends(browser_profile)):
    """{"held": hid | {...} | ""}: the next chapter as a new round; without a hero the host's hero of the last one."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    try:
        rid = await asyncio.to_thread(dm.next_chapter, uid, kid, b, dm._lang(b))
        dm._go(dm.run_prolog(rid), name="dungeon-prolog")
    except dm.KNOWN as e:
        raise dm._http(e)
    return await asyncio.to_thread(dm.view, rid, await asyncio.to_thread(dm._seat_uid, rid, uid))


@router.delete("/api/profile/dungeon/kampagne/{kid}", dependencies=[Depends(assistant)])
async def kampagne_weg(kid: str, request: Request, prof=Depends(browser_profile)):
    """Delete a campaign (also while blocked: own data); its rounds and the profiles' heroes stay."""
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)
    try:
        await asyncio.to_thread(dm.drop_campaign, uid, kid)
    except dm.KNOWN as e:
        raise dm._http(e)
    return await asyncio.to_thread(_mine, uid, "en" if request.query_params.get("lang") == "en" else "de")


@router.post("/api/profile/dungeon/beitreten", dependencies=[Depends(assistant)])
async def beitreten_profil(request: Request, response: Response, prof=Depends(browser_profile)):
    """{"code", "held": hid | {name, volk, klasse, geschlecht, satz}}: a profile takes a seat link for its own login."""
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, dm.BODY)
    guard.check(request, dm.KEY)
    rid, pid = await asyncio.to_thread(dm.find, b.get("code"))
    if not rid:
        guard.failed(request, dm.KEY, what="dungeon_link")
        dm._day.bump("abgelehnt")
        print("dungeon: abgelehnt | falscher code", flush=True)
        raise HTTPException(400, "Der Link passt nicht oder ist abgelaufen.")
    tok = _device_cookie(request, response)
    try:
        await asyncio.to_thread(dm.join, rid, pid, b, uid, None, dm.device(tok))
        return await asyncio.to_thread(dm.view, rid, pid)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.delete("/api/profile/dungeon/held/{hid}", dependencies=[Depends(assistant)])
async def held_weg(hid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)

    def go():
        with dm._lock:
            hs = dm.heroes(uid)
            if not any(h["hid"] == hid for h in hs):
                raise LookupError("held")
            dm._save_heroes(uid, [h for h in hs if h["hid"] != hid])
            if not dm._in_play(dm._read(), hid):
                dm._bild_rm("held-" + hid)
        print("dungeon: held geloescht", flush=True)
        return _mine(uid, "de")
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


# ---------------------------------------------------------------- a guest's seat (#spiel=<code>, dungeon.js)
@router.post("/api/dungeon/platz")
async def gast_platz(request: Request):
    """What the invitation shows: the round, the choices for a hero, whether this seat has one already."""
    b, rid, pid = await dm._guest(request)
    rd = dm._round(await asyncio.to_thread(dm._read), rid)
    p = rd["plaetze"][pid]
    host = profiles.by_id(rd["owner"]) or {}
    out = {"titel": rd["titel"], "von": host.get("name", ""), "frei": not p.get("held"), "until": rd["until"], "welt": rd["welt"],
           "spieler": len(dm.seated(rd)), "max": dm.rules()["grenzen"]["spieler"], "wahl": dict(dm._choices(rd["lang"], False, rd["welt"]), bilder_an=dm.pictures_on(rd["owner"])),
           "profil_genommen": bool(p.get("uid")), "kapitel": rd.get("kapitel", 0),
           "gastkonto": gastkonto.on() and bool(await asyncio.to_thread(gastkonto.sender)),
           "kampagne_helden": [] if p.get("held") else [dm.hero_view(dm.rules(), h, rd["lang"], full=False) for h in
                                                         await asyncio.to_thread(dm.campaign_heroes, rd)]}
    return out


def mark_device(rid, uid, geraet):
    """The host's seat keeps the hash of the device it was made on, so a seat link opened there takes no second hero."""
    with dm._lock:
        d = dm._read()
        pid, p = dm.seat_of(dm._round(d, rid), uid)
        if pid and geraet:
            p["geraet"] = geraet
            dm._write(d)


def _device_cookie(request, response):
    """This device's token (the cookie GERAET, made once, HttpOnly): the seat keeps only its hash (Punkt 6)."""
    tok = request.cookies.get(dm.GERAET, "")
    if not dm._GERAET.fullmatch(tok):
        tok = secrets.token_urlsafe(24)
    response.set_cookie(dm.GERAET, tok, max_age=365 * 86400, httponly=True, samesite="strict")
    return tok


@router.post("/api/dungeon/weiter")
async def gast_weiter(request: Request):
    """{"t"}: the „Weiterspielen“ link of a guest's mail (#weiter=<t>, dungeon_gast.redeem, used once): a fresh key for
    that seat on this device ({"code"}); the seat keeps at most WEITER_KEYS of them, a new seat link takes them back."""
    dm._door(request, "dungeonkonto")
    if not gastkonto.on():
        raise HTTPException(404, "Not Found")
    b = await json_body(request, dm.BODY)
    try:
        code = await asyncio.to_thread(play_on, b.get("t"))
    except PermissionError:
        dm._day.bump("abgelehnt")
        guard.failed(request, dm.KEY, what="dungeon_link")
        raise HTTPException(400, "Der Link passt nicht oder ist abgelaufen.")
    return {"code": code}


def play_on(tok):
    """The seat of a redeemed „Weiterspielen“ link gets one more key (hx), if it is still the account's seat."""
    kid, rid, pid = gastkonto.redeem(tok)
    code = secrets.token_urlsafe(24)
    with dm._lock:
        d = dm._read()
        rd = d["runden"].get(rid)
        p = (rd or {}).get("plaetze", {}).get(pid)
        if not rd or rd.get("status") == "ende" or not p or p.get("konto") != kid:
            print("dungeon: gastmail | weiter | platz weg", flush=True)
            raise PermissionError("weiter")
        p["hx"] = (list(p.get("hx") or []) + [dm._hash(code)])[-dm.WEITER_KEYS:]
        dm._write(d)
    print("dungeon: gastmail | weiter | neuer schluessel", flush=True)
    return code


@router.post("/api/dungeon/beitreten")
async def gast_beitreten(request: Request, response: Response):
    """{"code", "held": {name, volk, klasse, geschlecht, satz}} or {"code", "figur"}: a guest takes the seat (one seat per device)."""
    b, rid, pid = await dm._guest(request)
    tok = _device_cookie(request, response)
    try:
        await asyncio.to_thread(dm.join, rid, pid, b, "", None, dm.device(tok))
        return await asyncio.to_thread(dm.view, rid, pid)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/lage")
async def gast_lage(request: Request):
    b, rid, pid = await dm._guest(request)
    await asyncio.to_thread(dm.maybe_close, rid)
    dm._go(dm.hero_voices(), name="dungeon")
    try:
        return await asyncio.to_thread(dm.look, rid, pid, str(b.get("stand") or "")[:32])
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/aktion")
async def gast_aktion(request: Request):
    b, rid, pid = await dm._guest(request)
    return await dm._act(rid, lambda: pid, b)


@router.post("/api/dungeon/mehrzeit")
async def gast_mehrzeit(request: Request):
    b, rid, pid = await dm._guest(request)
    return await _more(rid, lambda: pid)


@router.post("/api/dungeon/held")
async def gast_held(request: Request):
    b, rid, pid = await dm._guest(request)

    def go():
        out = dm.hero_act(rid, pid, b)
        return dict(dm.view(rid, pid), **(out or {}))
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/figur")
async def gast_figur(request: Request):
    """The guest's hero as a Figur-Code (shown once) to take it into another round."""
    b, rid, pid = await dm._guest(request)
    try:
        rd = dm._round(await asyncio.to_thread(dm._read), rid)
        h = rd["plaetze"][pid].get("held")
        if not h or rd["plaetze"][pid].get("uid"):      # a profile's hero (the app's own seat code) stays with it
            raise LookupError("held")
        if h.get("tot"):
            raise LookupError("tot")
        code = await asyncio.to_thread(dm.make_figure, h)
    except dm.KNOWN as e:
        raise dm._http(e)
    return {"figur": code, "tage": dm.FIGUR_TAGE}


GASTKONTO_WAS = ("code", "anmelden", "konto", "merken", "zugmail", "held_weg", "loeschen")


def guest_account(rid, pid, b):
    """The guest account at a seat (dungeon_gast, switch „Gäste mit E-Mail“): ask a code, sign in with it (the seat's
    hero goes into the account), see it, keep the seat's hero, „Du bist dran per Mail“, drop a hero, delete it all."""
    was = b.get("was")
    if was not in GASTKONTO_WAS:
        raise ValueError("was")
    rd = dm._round(dm._read(), rid)
    p = rd["plaetze"][pid]
    if p.get("uid"):                                   # a profile's seat keeps its heroes in the profile
        raise LookupError("profil")
    if was == "code":
        gastkonto.ask_code(b.get("adresse"), rd["titel"], rd["lang"], welt=rd.get("welt", ""))
        return {"gesendet": True}
    if was == "anmelden":
        tok = gastkonto.login(b.get("adresse"), b.get("pin"))
        kid, k = gastkonto.account(tok)
        out = {"token": tok}
    else:
        kid, k = gastkonto.account(b.get("token"))
        out = {}
    if was in ("anmelden", "merken"):
        with dm._lock:
            d = dm._read()
            cur = dm._round(d, rid)
            q = cur["plaetze"][pid]
            if q.get("held") and q.get("konto") != kid:
                if not gastkonto.keep(kid, q["held"]):
                    raise OverflowError("helden")
                q["konto"] = kid
                dm._write(d)
    elif was == "zugmail":
        gastkonto.turn_mail(kid, b.get("an") is True, b.get("adresse", ""))
    elif was == "held_weg":
        if p.get("konto") == kid and (p.get("held") or {}).get("hid") == b.get("hid"):
            raise FileExistsError("held spielt")
        gastkonto.drop_hero(kid, b.get("hid"))
    elif was == "loeschen":
        gastkonto.forget(kid)
        with dm._lock:
            d = dm._read()
            for x in d["runden"].values():
                for q in x["plaetze"].values():
                    if q.get("konto") == kid:
                        q.pop("konto")
            dm._write(d)
        return {"geloescht": True}
    kid, k = gastkonto.account(out.get("token") or b.get("token"))
    rd = dm._round(dm._read(), rid)
    return dict(out, konto=gastkonto.view(kid, k, dm.rules(), dm.hero_view, rd["lang"]), gebunden=rd["plaetze"][pid].get("konto") == kid)


@router.post("/api/dungeon/gast")
async def gast_konto(request: Request):
    """{"code", "was", …}: the guest account of this seat (guest_account); only with the switch „Gäste mit E-Mail“."""
    b, rid, pid = await dm._guest(request)
    if not gastkonto.on():
        raise HTTPException(404, "aus")
    guard.limit(request, "dungeonkonto")
    try:
        return await asyncio.to_thread(guest_account, rid, pid, b)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/ton")
async def gast_ton(request: Request):
    """{"code", "zug", "k", "mp3"}: piece k of the turn read aloud (WAV, or its MP3 copy), the same file for every seat."""
    b, rid, pid = await dm._guest(request)
    try:
        data, media = await asyncio.to_thread(dm.ton_of, rid, pid, b.get("zug"), b.get("k", 0), b.get("mp3") is True)
    except dm.KNOWN as e:
        raise dm._http(e)
    return Response(data, media_type=media, headers={"Cache-Control": "no-store"})


@router.post("/api/dungeon/bild")
async def gast_bild(request: Request):
    """{"code", "b"}: a scene picture of the seat's round."""
    b, rid, pid = await dm._guest(request)
    try:
        return dm._png_out(await asyncio.to_thread(dm.bild_of, rid, pid, b.get("b")))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/daumen")
async def gast_daumen(request: Request):
    """{"code", "zug", "gut", "grund"?}: the seat's 👍/👎 for a narration of its round (a 👎 with a fixed reason: a case); {"code", "zug", "aktion"} a 👍 for another
    seat's action (Heldenmut)."""
    b, rid, pid = await dm._guest(request)
    try:
        if "aktion" in b:
            return {"mut": await asyncio.to_thread(praise, rid, pid, b)}
        return await asyncio.to_thread(erz.thumb, dm._me, rid, pid, b.get("zug"), b.get("gut"), b.get("grund"))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/grenzen")
async def gast_grenzen(request: Request):
    """{"code", "linien", "schleier"}: the seat's lines and veils; {"code", "x": true} lays the X-Karte."""
    b, rid, pid = await dm._guest(request)
    try:
        return await asyncio.to_thread(limits_of, rid, pid, b)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/tisch")
async def gast_tisch(request: Request):
    """{"code", "text"}: one line of table talk from the seat; the model never sees it."""
    b, rid, pid = await dm._guest(request)
    guard.limit(request, "dungeontisch")
    return await _talk(rid, lambda: pid, b)


@router.post("/api/dungeon/tippt")
async def gast_tippt(request: Request):
    """{"code"}: a keystroke of the seat in its action field („X schreibt …“ for the others)."""
    b, rid, pid = await dm._guest(request)
    guard.limit(request, "dungeontippt")
    warten.typing(rid, pid)
    return {"ok": True}


@router.post("/api/dungeon/wurf")
async def gast_wurf(request: Request):
    """{"code"}: the seat throws its own die, the others see the number."""
    b, rid, pid = await dm._guest(request)
    guard.limit(request, "dungeonwurf")
    return await _throw(rid, lambda: pid)


@router.post("/api/dungeon/termin")
async def gast_termin(request: Request):
    """{"code"}: the game date of the seat's round as a calendar file."""
    b, rid, pid = await dm._guest(request)
    try:
        return _ics_out(dm._round(dm._read(), rid), rid)
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/portraet")
async def gast_portraet(request: Request):
    """{"code", "pid"}: the portrait of a hero of the seat's round."""
    b, rid, pid = await dm._guest(request)
    try:
        return dm._png_out(await asyncio.to_thread(dm.portrait_of, rid, pid, str(b.get("pid") or "")))
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/dungeon/portraet/malen")
async def gast_portraet_malen(request: Request):
    """{"code"}: the guest's own hero's portrait (once per level, the host's „Bilder malen“ and the game's limits)."""
    b, rid, pid = await dm._guest(request)
    await _paint_start(request, None, lambda: dm.paint_portrait(rid, *dm.queue_portrait(rid, pid)), dm._lang(b))
    return await asyncio.to_thread(dm.view, rid, pid)


@router.post("/api/dungeon/probe")
async def gast_probe(request: Request):
    """{"code", "stimme"}: a fixed sentence in a voice the seat's hero may take, as WAV."""
    b, rid, pid = await dm._guest(request)
    guard.limit(request, "dungeonprobe")
    try:
        wav, ersatz = await dm.probe(b.get("stimme"), (await asyncio.to_thread(dm._read))["runden"][rid].get("lang", "de"),
                                  str(b.get("klang") or ""))
    except dm.KNOWN as e:
        raise dm._http(e)
    except (RuntimeError, asyncio.TimeoutError) as e:
        print(f"dungeon: stimmprobe | fehler | {'klang' if b.get('klang') else 'stimme'} | {str(e)[:20] or type(e).__name__}", flush=True)
        raise HTTPException(503, "Die Sprachausgabe ist gerade belegt.")
    return dm._probe_out(wav, ersatz)


@router.post("/api/dungeon/hoeren")
async def gast_hoeren(request: Request):
    """{"code", "wav"}: speak instead of type, the text comes back for the seat's own field."""
    b, rid, pid = await dm._guest(request, dm.HOER_BYTES * 4 // 3 + dm.BODY)
    guard.limit(request, "dungeonohr")
    try:
        wav = dm._wav_in(b)
        return await dm.hear(rid, wav, pid)
    except dm.KNOWN as e:
        raise dm._http(e)


# ---------------------------------------------------------------- the admin's rules (Funktionen → Dungeon-Master)
def _summary(r):
    return {k: len(r.get(k) or []) for k in dm.LISTS} | {"faehigkeiten": sum(len(k["faehigkeiten"]) for k in r["klassen"])}


@router.get("/api/admin/dungeon", dependencies=[Depends(auth)])
def admin_show(request: Request = None):
    """The admin's own rules (as written), what is in force (counts), the stories with the limits of the planner and Live."""
    import dungeon_dingbild
    r = dm.rules()
    lang = "en" if request is not None and request.query_params.get("lang") == "en" else "de"
    return dm.json_out(request, {"eigene": dm.own_rules(), "summe": _summary(r), "standard": dm._base_rules(), "live": dm.for_live(), "personen_an": dungeon_tiefe.admin_an(personen.KEY),
            "geschichten": [dm.plan_view(r, k, g) for k, g in sorted(dm.plans().items(), key=lambda x: -x[1].get("t", 0))],
            "wahl": dm._choices(lang), "planer": dm._planner_limits(),
            "dingbilder": dungeon_dingbild.status(r), "daumen": erz.stats(dm._me, r), "gastmail": gastkonto.admin_view()})


@router.put("/api/admin/dungeon", dependencies=[Depends(auth)])
async def admin_save(request: Request):
    """{"eigene": {...}}: the admin's own rules; refused with the list of what is wrong unless they pass check_rules."""
    b = await json_body(request, dm.ADMIN_BODY)
    own = b.get("eigene")
    if not isinstance(own, dict):
        raise HTTPException(400, "eigene")
    errs = [f"{k}: höchstens {dm.EIGENE_MAX} eigene Einträge" for k in dm.LISTS + dm.ID_LISTEN if isinstance(own.get(k), list) and len(own[k]) > dm.EIGENE_MAX]
    errs += dm.check_rules(dm.merge(await asyncio.to_thread(dm._base_rules), own))
    if errs:
        print(f"dungeon: regeln abgelehnt | {len(errs)} fehler", flush=True)
        raise HTTPException(422, errs[:20])
    await asyncio.to_thread(write_json, dm.EIGENE, own, 2, 0o600, False, 0o700)
    dm._rules["r"] = None
    print(f"dungeon: regeln gespeichert | {len(json.dumps(own))} zeichen", flush=True)
    return admin_show(request)


@router.delete("/api/admin/dungeon", dependencies=[Depends(auth)])
def admin_reset():
    try:
        os.remove(dm.EIGENE)
    except FileNotFoundError:
        pass
    dm._rules["r"] = None
    print("dungeon: regeln standard", flush=True)
    return admin_show()


@router.put("/api/admin/dungeon/geschichte/{gid}", dependencies=[Depends(auth)])
async def admin_geschichte(gid: str, request: Request):
    """A story of the admin („neu“ for a new one), refused with the list of what is wrong unless it passes check_plan."""
    if gid != "neu" and not dm._GID.fullmatch(gid):
        raise dm._http(LookupError("geschichte"))
    b = await json_body(request, dm.PLAN_BODY)
    try:
        _, errs = await asyncio.to_thread(dm.save_plan, gid, b)
    except dm.KNOWN as e:
        raise dm._http(e)
    if errs:
        print(f"dungeon: geschichte abgelehnt | {len(errs)} fehler", flush=True)
        raise HTTPException(422, errs[:20])
    return admin_show(request)


@router.put("/api/admin/dungeon/gastmail", dependencies=[Depends(auth)])
async def admin_gastmail(request: Request):
    """{"absender": "<profile id>/<mailbox id>" or ""}: the mailbox the codes and „Du bist dran“ of guests go from."""
    guard.limit(request, "dungeonkonto", admin=True)
    b = await json_body(request, 1024)
    try:
        await asyncio.to_thread(gastkonto.set_sender, str(b.get("absender") or ""))
    except dm.KNOWN as e:
        raise dm._http(e)
    return admin_show(request)


@router.delete("/api/admin/dungeon/geschichte/{gid}", dependencies=[Depends(auth)])
async def admin_geschichte_weg(gid: str, request: Request):
    try:
        await asyncio.to_thread(dm.drop_plan, gid)
    except dm.KNOWN as e:
        raise dm._http(e)
    return admin_show(request)


async def _planner(request, fn):
    """Both planner asks: one rate limit of the admin, the model's answer checked, fixed refusals."""
    guard.limit(request, "dungeonplan", admin=True)
    b = await json_body(request, dm.PLAN_BODY)
    try:
        return {"plan": await fn(b)}
    except TimeoutError:
        print("dungeon: abgelehnt | sprachmodell pausiert", flush=True)
        raise HTTPException(409, "sprachmodell pausiert")
    except LookupError:
        print("dungeon: abgelehnt | kein vorschlag", flush=True)
        raise HTTPException(422, "kein vorschlag")
    except dm.KNOWN as e:
        raise dm._http(e)


@router.post("/api/admin/dungeon/geschichte/vorschlag", dependencies=[Depends(auth)])
async def admin_vorschlag(request: Request):
    """{welt, ton, akte, stichworte, tabus, lang}: the model proposes a story; nothing is kept until the admin saves."""
    return await _planner(request, lambda b: dm.propose_plan(b, dungeon_tiefe.admin_an(personen.KEY)))


@router.post("/api/admin/dungeon/geschichte/akt", dependencies=[Depends(auth)])
async def admin_akt_neu(request: Request):
    """{plan, n, hinweis}: the model writes act n of the draft again."""
    return await _planner(request, dm.redo_act)
