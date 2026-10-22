"""Krisenspiel gemeinsam (plan krisenspiel/plan.md Paket 11, Dominik 2026-10-22 „mache selbständig weiter“): up to
PLAETZE more players join the running game of a profile, each with a role (Technik, Kommunikation, Leitung,
krisenspiel.ROLLEN), and all see the same situation live. The owner plays as Leitung; every seat comes by an
invitation link, a guest without a profile as well as another profile (the link is the same for both).

Who may: the function krisenteam (features.py, admin switch chat.krisenspiel_team, off) on top of IT-Krisenspiel.
Every use asks again whether the function is still allowed for the owner and whether the owner's game is still the
same game: a switch turned off, a blocked or deleted profile or a new game ends every seat at once.

- The link is https://<panel>/#krise=<code>. The code stands after the "#", so it never reaches a proxy log, the panel
  log or a Referer; it is random (192 bits), shown once, only its hash is kept. It works for exactly one game and at
  most GUELTIG_H hours, and the owner can take it back at any time.
- What a seat may do: see the dashboard (values, systems, the chronicle with the fixed texts, never the narrator's
  words, never the owner's history or achievements) and take the moves of its role (krisenspiel.darf; Leitung all).
  Nothing else: no console, no new game, no giving up, no tool, no model, no assistant. Wrong codes count like
  wrong PINs (guard.failed, a lock after five, longer each time), every request counts against guard.RATE
  "krisegast" per address; a web page of another site cannot use it (its Origin is refused).
- The name a player types is data: cleaned, at most NAME_MAX characters, shown only in this game (always through esc).
- Journal: fixed words and numbers („spiel: team | einladung | technik | Profil ab12“, „spiel: team zug | ok |
  kommunikation“), never the code or the name. Live: open seats, seats online, moves of the team today.

    STATE/krisenspiel-team.json  {"plaetze": {id: {"owner", "spiel", "rolle", "h", "made", "until", "name"}}}

    GET    /api/profile/krisenspiel/team        the seats of the running game and its move (the owner's page polls)
    POST   /api/profile/krisenspiel/team        {rolle, base}: a new seat, the link and its QR code shown once
    DELETE /api/profile/krisenspiel/team/{id}   take a seat back
    POST   /api/krise/lage                      {code, name?}: what a seat sees (krisegast.js)
    POST   /api/krise/zug                       {code, aktion, zug}: a move of the seat's role
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import krisenspiel as K
import mfa
import profiles
from common import STATE, DayCounter, write_json
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
FILE = os.path.join(STATE, "krisenspiel-team.json")
PLAETZE = 3              # invited seats per game: four players with the owner
GUELTIG_H = 24           # hours a link works at most
NAME_MAX = 30
ONLINE_S = 15            # a seat that asked within these seconds counts as online
POLL_S = 4               # seconds between two asks of an open page (owner and seat)
CHRONIK_GAST = 40        # chronicle entries a seat sees
BODY = 1024
CODE = re.compile(r"[A-Za-z0-9_\-]{32}")
_ID = re.compile(r"p[0-9a-f]{8}")
KEY = "\0krisegast"      # one lockout entry for every wrong code from one address (guard.py)
_lock = threading.Lock()
_seen = {}               # seat id -> last ask (memory only, so polling never writes)
_count = DayCounter(zuege=0, abgelehnt=0)   # Zustand → Live, numbers only


def _read():
    try:
        with open(FILE) as f:
            d = json.load(f)
        p = d.get("plaetze") if isinstance(d, dict) else None
        return {"plaetze": {k: v for k, v in (p or {}).items() if _ID.fullmatch(k) and isinstance(v, dict)}}
    except (OSError, ValueError):
        return {"plaetze": {}}


def _write(d):
    write_json(FILE, d, mode=0o600, dir_mode=0o700)


def _hash(code):
    return hashlib.sha256(("spark-krisegast:" + code).encode()).hexdigest()


def _game_id(owner):
    st = K.load(owner)["spiel"]
    return st["id"] if st else None


def _prune(d, now):
    """Expired seats, seats of deleted profiles and of a game that is no longer the owner's go at the next write."""
    have = set(profiles.user_ids())
    games = {}
    keep = {}
    for k, v in d["plaetze"].items():
        o = v.get("owner")
        if v.get("until", 0) <= now or o not in have:
            continue
        if o not in games:
            games[o] = _game_id(o)
        if games[o] == v.get("spiel"):
            keep[k] = v
    d["plaetze"] = keep


def clean_name(x):
    return re.sub(r"[\x00-\x1f<>\"\\`]", "", str(x or "")).strip()[:NAME_MAX]


def seats(owner, spiel, now=None):
    """[{"id", "rolle", "name", "until", "online"}] of the open seats of one game (never the code or its hash)."""
    now = time.time() if now is None else now
    return sorted(({"id": k, "rolle": v["rolle"], "name": v.get("name", ""), "until": v["until"],
                    "online": now - _seen.get(k, 0) < ONLINE_S, "made": v.get("made", 0)}
                   for k, v in _read()["plaetze"].items()
                   if v.get("owner") == owner and v.get("spiel") == spiel and v.get("until", 0) > now),
                  key=lambda x: x["made"])


def make(owner, rolle, now=None):
    """(id, code) of a new seat in the owner's running game; the code is shown once and only its hash is kept."""
    if rolle not in K.ROLLEN:
        raise ValueError("rolle")
    st = K.load(owner)["spiel"]
    if not st or st.get("ende"):
        raise LookupError("no running game")
    now = int(time.time() if now is None else now)
    code = secrets.token_urlsafe(24)
    with _lock:
        d = _read()
        _prune(d, now)
        if sum(1 for v in d["plaetze"].values() if v.get("owner") == owner) >= PLAETZE:
            raise OverflowError(f"at most {PLAETZE} players besides you")
        pid = "p" + os.urandom(4).hex()
        d["plaetze"][pid] = {"owner": owner, "spiel": st["id"], "rolle": rolle, "h": _hash(code), "made": now,
                             "until": now + GUELTIG_H * 3600, "name": ""}
        _write(d)
    print(f"spiel: team | einladung | {rolle} | {profiles.log_name(profiles.by_id(owner))}", flush=True)
    return pid, code


def revoke(owner, pid):
    with _lock:
        d = _read()
        v = d["plaetze"].get(pid)
        if not v or v.get("owner") != owner:
            print("spiel: team | widerruf | nicht da", flush=True)
            return False
        d["plaetze"].pop(pid)
        _prune(d, time.time())
        _write(d)
    _seen.pop(pid, None)
    print("spiel: team | widerruf | ok", flush=True)
    return True


def find(code, now=None):
    """The seat for a valid code while everything behind it still holds, else None."""
    now = time.time() if now is None else now
    if not isinstance(code, str) or not CODE.fullmatch(code):
        return None
    h = _hash(code)
    for k, v in _read()["plaetze"].items():
        if hmac.compare_digest(str(v.get("h", "")), h):
            owner = v.get("owner")
            if v.get("until", 0) <= now or not profiles.by_id(owner) or not features.allowed("krisenteam", owner) \
                    or _game_id(owner) != v.get("spiel"):
                return None
            return dict(v, id=k)
    return None


def _name_once(pid, name):
    """The name a player typed, kept on the first ask that brings one (later asks cannot change it)."""
    with _lock:
        d = _read()
        v = d["plaetze"].get(pid)
        if v is not None and not v.get("name") and name:
            v["name"] = name
            _write(d)
            return name
    return v.get("name", "") if v else ""


def own_count(uid):
    return sum(1 for v in _read()["plaetze"].values() if v.get("owner") == uid)


def own_clear(uid):
    """The owner's seats go with „Meine Daten löschen“ of the game and with the profile (features.OWN)."""
    with _lock:
        d = _read()
        gone = [k for k, v in d["plaetze"].items() if v.get("owner") == uid]
        for k in gone:
            d["plaetze"].pop(k)
            _seen.pop(k, None)
        if gone:
            _write(d)
    return len(gone)


def for_live():
    """Live (Krisenspiel): open seats, seats online, moves of the team and refusals today; numbers only."""
    now = time.time()
    p = _read()["plaetze"]
    c = _count.today()
    return {"on": features.admin_on("krisenteam"), "plaetze": sum(1 for v in p.values() if v.get("until", 0) > now),
            "online": sum(1 for k in p if now - _seen.get(k, 0) < ONLINE_S), "zuege": c["zuege"], "abgelehnt": c["abgelehnt"]}


# ---------------------------------------------------------------- the owner (page Krisenspiel)
def _need(uid):
    K._need(uid)
    if not features.allowed("krisenteam", uid):
        print("spiel: team abgelehnt | nicht freigegeben", flush=True)
        raise HTTPException(403, features.missing_text("krisenteam", uid))


def _owner_view(uid):
    st = K.load(uid)["spiel"]
    return {"spiel": st["id"] if st else None, "zug": st["zug"] if st else 0, "ende": bool(st and st.get("ende")),
            "plaetze": seats(uid, st["id"]) if st else [], "max": PLAETZE, "poll": POLL_S, "stunden": GUELTIG_H,
            "rollen": [{"id": k, "name": list(v)} for k, v in K.ROLLEN.items()]}


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "the panel's address is missing (base)")
    return base


@router.get("/api/profile/krisenspiel/team", dependencies=[Depends(assistant)])
def owner_team(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    return _owner_view(uid)


@router.post("/api/profile/krisenspiel/team", dependencies=[Depends(assistant)])
async def owner_invite(request: Request, prof=Depends(browser_profile)):
    """{"rolle": technik | kommunikation | leitung, "base": "https://panel"} -> the link with its QR code, shown once."""
    uid = prof["id"]
    _need(uid)
    guard.limit(request, "spiel", uid)
    body = await json_body(request, BODY)
    base = _base(body)
    try:
        pid, code = await asyncio.to_thread(make, uid, body.get("rolle"))
    except ValueError:
        print("spiel: team abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "rolle")
    except LookupError:
        print("spiel: team abgelehnt | kein spiel", flush=True)
        raise HTTPException(404, "no running game")
    except OverflowError as e:
        print("spiel: team abgelehnt | voll", flush=True)
        raise HTTPException(409, str(e))
    link = f"{base}/#krise={code}"
    return dict(_owner_view(uid), id=pid, link=link, qr=mfa._qr_svg(link))


@router.delete("/api/profile/krisenspiel/team/{pid}", dependencies=[Depends(assistant)])
def owner_revoke(pid: str, request: Request, prof=Depends(browser_profile)):
    """Taking a seat back (also while the function is off by now: the owner's own data)."""
    guard.limit(request, "spiel", prof["id"])
    if not _ID.fullmatch(pid) or not revoke(prof["id"], pid):
        raise HTTPException(404, "no such seat")
    return _owner_view(prof["id"])


# ---------------------------------------------------------------- a seat (#krise=<code>, krisegast.js)
def _door(request):
    if not features.admin_on("krisenteam"):
        raise HTTPException(404, "Not Found")
    origin = request.headers.get("origin")
    if origin and origin != "null" and urlsplit(origin).netloc.lower() != (request.headers.get("host") or "").lower():
        raise HTTPException(403, "not from another site")
    guard.limit(request, "krisegast")
    guard.check(request, KEY)


def _seat(request, code):
    v = find(code)
    if not v:
        _count.bump("abgelehnt")
        guard.failed(request, KEY, what="krise_link")
        print("spiel: team abgelehnt | falscher code", flush=True)
        raise HTTPException(400, "Der Link passt nicht oder ist abgelaufen.")
    _seen[v["id"]] = time.time()
    return v


def guest_view(seat, st):
    """What a seat sees: fixed values and texts of the game only; never the narrator's words, the inspector, the
    console or anything of the owner's profile (history, achievements, name)."""
    sz = K.SZENARIEN[st["szenario"]]
    rolle = seat["rolle"]
    acts = [] if st["ende"] or st.get("modus") == "konsole" else \
        [dict(a, darf=K.darf(rolle, a)) for a in K.available(st)]
    ende = None
    if st["ende"]:
        ende = {k: st["ende"][k] for k in ("art", "punkte", "note", "gruende", "minuten")}
    team = [{"rolle": "leitung", "name": "", "gastgeber": True, "online": True, "ich": False}]
    team += [{"rolle": x["rolle"], "name": x["name"], "gastgeber": False, "online": x["online"], "ich": x["id"] == seat["id"]}
             for x in seats(seat["owner"], st["id"])]
    return {"titel": sz["titel"], "stufe": list(K.STUFEN[st["stufe"]]["name"]), "zug": st["zug"], "m": st["m"],
            "min": K.minutes_gone(st), "modus": st.get("modus", "knoepfe"), "uhr": K._uhr_view(st), "ende": ende,
            "assets": [{"id": x["id"], "name": x["name"], "typ": x["typ"], "status": st["assets"][x["id"]]["status"],
                        "details": st["assets"][x["id"]]["details"]} for x in sz["assets"]],
            "chronik": [{k: c[k] for k in ("zug", "min", "art", "text", "wer") if k in c} for c in st["chronik"][-CHRONIK_GAST:]],
            "aktionen": acts, "rolle": rolle, "rollen": {k: list(v) for k, v in K.ROLLEN.items()},
            "name": seat.get("name", ""), "team": team, "until": seat["until"], "poll": POLL_S}


@router.post("/api/krise/lage")
async def seat_lage(request: Request):
    """What the seat's page shows; the first ask with a name keeps it. With „Uhr läuft“ the ask moves the clock at most
    every UHR_POLL seconds (the same rule as the owner's page), so the game goes on while the owner's page is closed."""
    _door(request)
    body = await json_body(request, BODY)
    v = _seat(request, body.get("code"))
    name = clean_name(body.get("name"))
    if name and not v.get("name"):
        v["name"] = await asyncio.to_thread(_name_once, v["id"], name)
    owner = v["owner"]

    def go():
        with K._lock(owner):
            d = K.load(owner)
            st = d["spiel"]
            if not st or st["id"] != v["spiel"]:
                return None
            u = st.get("uhr")
            now = time.time()
            if u and not st.get("ende") and not u["pause"] and now - u["t"] >= K.UHR_POLL:
                K.uhr_ticken(st, now)
                if st.get("ende"):
                    K._book(d, now)
                    print("spiel: uhr | abgelaufen", flush=True)
                K.save(owner, d)
            return st
    st = await asyncio.to_thread(go)
    if not st:
        raise HTTPException(400, "Der Link passt nicht oder ist abgelaufen.")
    return guest_view(v, st)


@router.post("/api/krise/zug")
async def seat_zug(request: Request):
    """{"code", "aktion", "zug"}: one move of the seat's role, the same fixed rules as the owner's button."""
    _door(request)
    body = await json_body(request, BODY)
    v = _seat(request, body.get("code"))
    aktion, turn = body.get("aktion"), body.get("zug")
    if not isinstance(aktion, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", aktion) or not isinstance(turn, int) \
            or isinstance(turn, bool):
        print("spiel: team zug abgelehnt | eingabe", flush=True)
        raise HTTPException(400, "aktion, zug")
    owner = v["owner"]

    def go():
        with K._lock(owner):
            d = K.load(owner)
            st = d["spiel"]
            if not st or st["id"] != v["spiel"] or st.get("ende"):
                return None, 404
            if st["zug"] != turn:
                return st, 409
            if st.get("modus") == "konsole":
                return st, 423
            now = time.time()
            K.uhr_ticken(st, now)
            if st.get("ende"):                  # the clock ran out before this move
                K._book(d, now)
                K.save(owner, d)
                print("spiel: uhr | abgelaufen", flush=True)
                return st, 200
            try:
                K.move(st, aktion, rolle=v["rolle"], wer={"rolle": v["rolle"], "name": v.get("name", "")})
            except ValueError:
                return st, 422
            if st.get("ende"):
                K._book(d, now)
            K.save(owner, d)
            return st, 200
    st, code = await asyncio.to_thread(go)
    if code != 200:
        why = {404: "kein spiel", 409: "alter zug", 422: "nicht erlaubt", 423: "nur konsole"}[code]
        print(f"spiel: team zug abgelehnt | {why}", flush=True)
        raise HTTPException(422 if code == 423 else code, why)
    _count.bump("zuege")
    K._day.bump("zuege")
    print(f"spiel: team zug | ok | {v['rolle']}", flush=True)
    return guest_view(v, st)


features.OWN["krisenteam"] = (own_count, own_clear)
