"""KI-Dungeon-Master: Eigene Geschichten (Dominik 2026-10-26 „nach empfehlung umsetzten“ und „und 2“ = Punkte 1, 2
und 3b; own code).

1. Every story card of a new round has „⋯“: Bearbeiten (title, idea, tone, acts in the planner's form), Kopieren,
   Löschen. A story of the admin or one that comes with the Spark becomes the host's own copy on Bearbeiten (the
   original is hidden for this host); Löschen only hides such a story for this host („Ausgeblendete wieder zeigen“
   brings them back). The host's own stories are deleted for good.
2. The card „＋ Neue Geschichte“ comes first: the tone (and keywords if wanted) and „Erstellen“; the planner writes
   title, idea, goal, foe, places and acts (dungeon.propose_plan), the panel checks the draft like a typed one
   (dungeon.check_plan) and keeps it as the host's own story.
3b. Every host manages only the own stories (EIGENE_MAX); the admin sees and changes all of them under Regeln →
   Geschichten (the admin's own list and limit stay as they were).

Off by default: the admin's switch dungeongeschichten (features.py, chat.dungeon_geschichten) for the host. While off
no host has own or hidden stories (the admin's and the Spark's stories as before), the files stay.

    STATE/dungeon-geschichten.json      the stories, a host's own with "von": profile id (dungeon.plans)
    STATE/dungeon-geschichten-aus.json  {profile id: [gid]}  the stories a host hid

    GET    /api/profile/dungeon/geschichten/{gid}         a story the host may play, whole (for Bearbeiten)
    PUT    /api/profile/dungeon/geschichten/{gid}         {story}: save („neu“, the own, or an own copy of another)
    POST   /api/profile/dungeon/geschichten/{gid}/kopie   an own copy
    DELETE /api/profile/dungeon/geschichten/{gid}         the own: delete; another: hide for this host
    POST   /api/profile/dungeon/geschichten/zeigen        every hidden story back
    POST   /api/profile/dungeon/geschichten/erstellen     {welt, ton, stichworte, lang}: the planner writes a new own story
    POST   /api/profile/dungeon/geschichten/akt           {plan, n, hinweis}: the planner writes act n of the form again

Every answer with a story list: {"gid"?, "geschichten": [the cards of the new round], "aus": hidden count}.
Journal: fixed words and numbers („dungeon: geschichten | …“), Live only counts.
"""
import asyncio
import copy
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import dungeon
import features
import guard
from common import STATE, DayCounter, read_json, write_json
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "dungeongeschichten"
AUS = os.path.join(STATE, "dungeon-geschichten-aus.json")
EIGENE_MAX = 20            # own stories of one host
AUS_MAX = 200              # stories one host hides at most
_GID = re.compile(r"g[0-9a-f]{8}|v-[a-z0-9-]{1,40}")
_UID = re.compile(r"[a-z0-9_-]{1,64}")
_lock = threading.Lock()
_day = DayCounter(gespeichert=0, kopiert=0, geloescht=0, ausgeblendet=0, gezeigt=0, erstellt=0)


def hidden(uid):
    d = read_json(AUS, {})
    x = d.get(uid) if isinstance(d, dict) else None
    return [g for g in x if isinstance(g, str) and _GID.fullmatch(g)][:AUS_MAX] if isinstance(x, list) else []


def _hide(uid, gid, show=False):
    with _lock:
        d = read_json(AUS, {})
        d = {k: v for k, v in d.items() if _UID.fullmatch(str(k)) and isinstance(v, list)} if isinstance(d, dict) else {}
        aus = [g for g in d.get(uid, []) if isinstance(g, str) and _GID.fullmatch(g)]
        if show:
            aus = []
        elif gid not in aus:
            aus = (aus + [gid])[-AUS_MAX:]
        if aus:
            d[uid] = aus
        else:
            d.pop(uid, None)
        write_json(AUS, d, 2, 0o600, False, 0o700)


def visible(r, uid, lang):
    """The stories a host may start a round with, in this order: the own (while the switch is on), the admin's, the
    Spark's; hidden ones left out. uid None: the admin's view (the admin's and the Spark's). [(gid, story, von)]."""
    eigen = features.allowed(KEY, uid)
    aus = set(hidden(uid)) if eigen else set()
    ps = sorted(dungeon.plans().items(), key=lambda x: x[1].get("titel", ""))
    out = [(k, g, "eigen") for k, g in ps if eigen and g.get("von") == uid]
    out += [(k, g, "admin") for k, g in ps if not g.get("von") and k not in aus]
    out += [(k, g, "spark") for k, g in dungeon.shipped(r, lang).items() if k not in aus]
    return out


def find(r, uid, gid, lang):
    """A story this host may play (or Bearbeiten, Kopieren): (story, von), else LookupError."""
    for k, g, von in visible(r, uid, lang):
        if k == gid:
            return g, von
    raise LookupError("geschichte")


def cards(r, uid, lang):
    """The cards of the new round's form (dungeon._choices)."""
    return [{"gid": k, "titel": g["titel"], "welt": g["welt"], "ton": g["ton"], "akte": len(g["akte"]), "idee": g["idee"], "von": von}
            for k, g, von in visible(r, uid, lang)]


def answer(r, uid, lang, gid=None):
    return dict({"geschichten": cards(r, uid, lang), "aus": len(hidden(uid)) if features.allowed(KEY, uid) else 0}, **({"gid": gid} if gid else {}))


def _store(uid, g, gid=None, now=None):
    """The host's own story into the file (gid None: a new one), the host's limit counted."""
    now = int(time.time() if now is None else now)
    with dungeon._lock:
        ps = dungeon.plans()
        if gid is None:
            if sum(1 for x in ps.values() if x.get("von") == uid) >= EIGENE_MAX:
                raise OverflowError("geschichten")
            gid = "g" + os.urandom(4).hex()
            g["made"] = now
        else:
            g["made"] = ps[gid].get("made", now)
        g.update(von=uid, t=now)
        ps[gid] = g
        write_json(dungeon.GESCHICHTEN, ps, 2, 0o600, False, 0o700)
    return gid


def save(uid, gid, b, lang, now=None):
    """Bearbeiten: „neu“ a new own story; the own one changed; the admin's or the Spark's becomes an own copy and the
    original is hidden for this host. Returns (gid, errors)."""
    r = dungeon.rules()
    g, err = dungeon.check_plan(r, b)
    if err:
        print(f"dungeon: geschichten | abgelehnt | {len(err)} fehler", flush=True)
        return None, err
    if gid == "neu":
        new = _store(uid, g, None, now)
    else:
        _, von = find(r, uid, gid, lang)
        if von == "eigen":
            new = _store(uid, g, gid, now)
        else:
            new = _store(uid, g, None, now)
            _hide(uid, gid)
    _day.bump("gespeichert")
    print(f"dungeon: geschichten | gespeichert | {len(g['akte'])} akte", flush=True)
    return new, []


KOPIE = (" (Kopie)", " (copy)")


def copy_of(uid, gid, lang, now=None):
    """Kopieren: an own copy of a story the host may play, its title with „(Kopie)“."""
    r = dungeon.rules()
    g, _ = find(r, uid, gid, lang)
    g = copy.deepcopy(g)
    k = KOPIE[1 if g.get("lang") == "en" else 0]
    g["titel"] = g["titel"][:dungeon.TITEL_MAX - len(k)] + k
    g.pop("von", None)
    g, err = dungeon.check_plan(r, g)
    if err:
        raise ValueError("geschichte")
    new = _store(uid, g, None, now)
    _day.bump("kopiert")
    print("dungeon: geschichten | kopiert", flush=True)
    return new


def drop(uid, gid, lang):
    """Löschen: the own story for good; the admin's or the Spark's hidden for this host."""
    r = dungeon.rules()
    _, von = find(r, uid, gid, lang)
    if von == "eigen":
        with dungeon._lock:
            ps = dungeon.plans()
            ps.pop(gid, None)
            write_json(dungeon.GESCHICHTEN, ps, 2, 0o600, False, 0o700)
        _day.bump("geloescht")
        print("dungeon: geschichten | geloescht", flush=True)
    else:
        _hide(uid, gid)
        _day.bump("ausgeblendet")
        print("dungeon: geschichten | ausgeblendet", flush=True)


def show_all(uid):
    n = len(hidden(uid))
    _hide(uid, "", show=True)
    _day.bump("gezeigt")
    print(f"dungeon: geschichten | wieder gezeigt | {n}", flush=True)


def for_live():
    """Numbers only: own stories, hosts with hidden ones; saved, copied, deleted, hidden, shown, created today."""
    t = _day.counts()
    d = read_json(AUS, {})
    return dict(t, eigene=sum(1 for x in dungeon.plans().values() if x.get("von")), ausgeblendet_bei=len(d) if isinstance(d, dict) else 0)


# ---------------------------------------------------------------- endpoints
def _need(uid):
    dungeon._need(uid)
    if not features.allowed(KEY, uid):
        print("dungeon: geschichten | abgelehnt | aus", flush=True)
        raise HTTPException(403, features.missing_text(KEY, uid))


def _gid(gid, neu=False):
    if not (_GID.fullmatch(gid) or neu and gid == "neu"):
        raise dungeon._http(LookupError("geschichte"))


async def _run(fn, *a):
    try:
        return await asyncio.to_thread(fn, *a)
    except dungeon.KNOWN as e:
        raise dungeon._http(e)


@router.get("/api/profile/dungeon/geschichten/{gid}", dependencies=[Depends(assistant)])
async def ansehen(gid: str, request: Request, lang: str = "de", prof=Depends(own_profile)):
    """A story the host may play, whole, for the form of Bearbeiten."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeongeschichte", uid)
    _gid(gid)
    lang = "en" if lang == "en" else "de"
    r = dungeon.rules()
    g, von = await _run(find, r, uid, gid, lang)
    return dict(dungeon.plan_view(r, gid, g), von=von)


@router.put("/api/profile/dungeon/geschichten/{gid}", dependencies=[Depends(assistant)])
async def speichern(gid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeongeschichte", uid)
    _gid(gid, neu=True)
    b = await json_body(request, dungeon.PLAN_BODY)
    lang = dungeon._lang(b)
    new, errs = await _run(save, uid, gid, b, lang)
    if errs:
        raise HTTPException(422, errs[:20])
    return answer(dungeon.rules(), uid, lang, new)


@router.post("/api/profile/dungeon/geschichten/zeigen", dependencies=[Depends(assistant)])
async def zeigen(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeongeschichte", uid)
    b = await json_body(request, dungeon.BODY)
    await _run(show_all, uid)
    return answer(dungeon.rules(), uid, dungeon._lang(b))


@router.post("/api/profile/dungeon/geschichten/erstellen", dependencies=[Depends(assistant)])
async def erstellen(request: Request, prof=Depends(browser_profile)):
    """{welt, ton, stichworte, lang}: „＋ Neue Geschichte“; the planner writes it, the panel checks and keeps it."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeonplan", uid)
    b = await json_body(request, dungeon.PLAN_BODY)
    lang = dungeon._lang(b)
    try:
        leute = dungeon.personen.on({"owner": uid})
        g = await dungeon.propose_plan({k: b.get(k) for k in ("welt", "ton", "stichworte", "lang")}, leute)
    except TimeoutError:
        print("dungeon: geschichten | abgelehnt | sprachmodell pausiert", flush=True)
        raise HTTPException(409, "sprachmodell pausiert")
    except LookupError:
        print("dungeon: geschichten | abgelehnt | kein vorschlag", flush=True)
        raise HTTPException(422, "kein vorschlag")
    except dungeon.KNOWN as e:
        raise dungeon._http(e)
    new = await _run(_store, uid, g)
    _day.bump("erstellt")
    print(f"dungeon: geschichten | erstellt | {len(g['akte'])} akte", flush=True)
    return answer(dungeon.rules(), uid, lang, new)


@router.post("/api/profile/dungeon/geschichten/akt", dependencies=[Depends(assistant)])
async def akt(request: Request, prof=Depends(browser_profile)):
    """{plan, n, hinweis}: the planner writes act n of the host's form again (nothing kept until „Speichern“)."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeonplan", uid)
    b = await json_body(request, dungeon.PLAN_BODY)
    try:
        return {"plan": await dungeon.redo_act(b)}
    except TimeoutError:
        print("dungeon: geschichten | abgelehnt | sprachmodell pausiert", flush=True)
        raise HTTPException(409, "sprachmodell pausiert")
    except LookupError:
        print("dungeon: geschichten | abgelehnt | kein vorschlag", flush=True)
        raise HTTPException(422, "kein vorschlag")
    except dungeon.KNOWN as e:
        raise dungeon._http(e)


@router.post("/api/profile/dungeon/geschichten/{gid}/kopie", dependencies=[Depends(assistant)])
async def kopie(gid: str, request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeongeschichte", uid)
    _gid(gid)
    b = await json_body(request, dungeon.BODY)
    lang = dungeon._lang(b)
    new = await _run(copy_of, uid, gid, lang)
    return answer(dungeon.rules(), uid, lang, new)


@router.delete("/api/profile/dungeon/geschichten/{gid}", dependencies=[Depends(assistant)])
async def loeschen(gid: str, request: Request, lang: str = "de", prof=Depends(browser_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "dungeongeschichte", uid)
    _gid(gid)
    lang = "en" if lang == "en" else "de"
    await _run(drop, uid, gid, lang)
    return answer(dungeon.rules(), uid, lang)
