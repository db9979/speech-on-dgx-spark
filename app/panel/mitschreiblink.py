"""Mitschreib-Link (plan listen-teilen.md Stufe 4, Dominik 2026-10-20 „4a“): a link for people without a profile,
so a visitor, the cleaner or the grandparents can put something on one list („Bring bitte Milch mit“).

Who may: the function listlink (features.py, admin switch chat.tasks_link, off) on top of Listen; the owner makes
links for its own lists that live on the Spark (not for a list in a calendar account, never for another profile's
list). Every use asks again whether the function is still allowed for the owner: a switch turned off, a blocked
profile or a deleted list ends every link at once, like „Widerrufen“.

- The link is https://<panel>/#liste=<code>. The code stands after the "#", so it never reaches a proxy log, the
  panel log or a Referer; it is random (144 bits), shown once, only its hash is kept. It works until its day
  (DAYS: 7, 30 or 365 days) and can be taken back at any time; at most MAX_PER_PROFILE open links per profile.
- What a visitor may do: put entries on (at most MAX_TEXT characters, ten at a time), optionally with a name it
  types; with „darf die Liste sehen“ also read the open entries (texts only, never who put them on). Nothing else:
  no ticking off, no deleting, no other list, no tool, no model. Wrong codes count like wrong PINs (guard.failed,
  a lock after five, longer each time), every request counts against guard.RATE "mitschreib" per address.
- What comes in is data: the entry is cleaned like any other (tasks.clean) and stands with the source
  „Mitschreib-Link“ and the typed name; the assistant reads such a list as outside text (tasks.offer).
- A web page of another site cannot use it (its Origin is refused); Mein Notaus of the owner holds every entry off.
- Journal: fixed words and numbers („tasks: link made 30d | Profil ab12“, „tasks: link refused | bad code“), never
  the code, the name or the entry. Live: open links, entries and refusals today.

    STATE/mitschreib-links.json  {"links": {id: {"owner", "list", "h", "made", "until", "see"}}}
"""
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

import core
import features
import guard
import mfa
import notaus
import profiles
import tasks
from common import STATE, DayCounter, write_json

router = APIRouter()
FILE = os.path.join(STATE, "mitschreib-links.json")
DAYS = (7, 30, 365)
MAX_PER_PROFILE = 20
MAX_BODY = 2048
MAX_TEXT = 400
NAME_MAX = 30
CODE = re.compile(r"[A-Za-z0-9_\-]{24}")
_ID = re.compile(r"k[0-9a-f]{8}")
KEY = "\0mitschreib"     # one lockout entry for every wrong code from one address (guard.py)
_lock = threading.Lock()
_count = DayCounter()    # per day: "eingetragen", "abgelehnt"
_on = tasks._on          # the owner's door: the page Listen's (signed in, Listen allowed, no guests)


def _read():
    try:
        with open(FILE) as f:
            d = json.load(f)
        links = d.get("links") if isinstance(d, dict) else None
        return {"links": {k: v for k, v in (links or {}).items() if _ID.fullmatch(k) and isinstance(v, dict)}}
    except (OSError, ValueError):
        return {"links": {}}


def _write(d):
    write_json(FILE, d, mode=0o600, dir_mode=0o700)


def _hash(code):
    return hashlib.sha256(("spark-mitschreib:" + code).encode()).hexdigest()


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


def _prune(d, now):
    """Expired links and links of deleted profiles go at the next write."""
    have = set(profiles.user_ids())
    d["links"] = {k: v for k, v in d["links"].items() if v.get("until", 0) > now and v.get("owner") in have}


def _ok_list(owner, lid):
    d = tasks._load(owner)
    return tasks.known(owner, lid) and lid not in d["targets"]


def links(owner, lid, now=None):
    """[{"id", "until", "see", "made"}] of the owner's open links for one list (never the code or its hash)."""
    now = time.time() if now is None else now
    return sorted(({"id": k, "until": v["until"], "see": bool(v.get("see")), "made": v.get("made", 0)}
                   for k, v in _read()["links"].items()
                   if v.get("owner") == owner and v.get("list") == lid and v.get("until", 0) > now),
                  key=lambda x: x["made"])


def make(owner, lid, days, see, now=None):
    """(id, code) of a new link; the code is shown once and only its hash is kept."""
    if days not in DAYS:
        raise ValueError("days: 7, 30 or 365")
    if not _ok_list(owner, lid):
        raise LookupError("this list does not exist (any more) or lives in a calendar account")
    now = int(time.time() if now is None else now)
    code = secrets.token_urlsafe(18)
    with _lock:
        d = _read()
        _prune(d, now)
        if sum(1 for v in d["links"].values() if v.get("owner") == owner) >= MAX_PER_PROFILE:
            raise OverflowError(f"at most {MAX_PER_PROFILE} open links per profile")
        kid = "k" + os.urandom(4).hex()
        d["links"][kid] = {"owner": owner, "list": lid, "h": _hash(code), "made": now, "until": now + days * 86400,
                           "see": bool(see)}
        _write(d)
    print(f"tasks: link made {days}d{' see' if see else ''} | {_who(owner)}", flush=True)
    return kid, code


def revoke(owner, lid, kid):
    with _lock:
        d = _read()
        v = d["links"].get(kid)
        if not v or v.get("owner") != owner or v.get("list") != lid:
            print(f"tasks: link revoke | not there | {_who(owner)}", flush=True)
            return False
        d["links"].pop(kid)
        _prune(d, time.time())
        _write(d)
    print(f"tasks: link revoke | ok | {_who(owner)}", flush=True)
    return True


def drop_list(owner, lid):
    """A deleted list takes its links along (tasks.drop_list)."""
    with _lock:
        d = _read()
        gone = [k for k, v in d["links"].items() if v.get("owner") == owner and v.get("list") == lid]
        for k in gone:
            d["links"].pop(k)
        if gone:
            _write(d)
    return len(gone)


def find(code, now=None):
    """The link for a valid code while everything behind it still holds, else None."""
    now = time.time() if now is None else now
    if not isinstance(code, str) or not CODE.fullmatch(code):
        return None
    h = _hash(code)
    for k, v in _read()["links"].items():
        if hmac.compare_digest(str(v.get("h", "")), h):
            owner = v.get("owner")
            if v.get("until", 0) <= now or not profiles.by_id(owner) or not features.allowed("listlink", owner) \
                    or not _ok_list(owner, v.get("list")):
                return None
            return dict(v, id=k)
    return None


def for_live():
    """Live (Listen): open links, entries and refusals today; numbers only."""
    now = time.time()
    c = _count.counts()
    return {"on": features.admin_on("listlink"), "links": sum(1 for v in _read()["links"].values() if v.get("until", 0) > now),
            "added": c.get("eingetragen", 0), "refused": c.get("abgelehnt", 0)}


# ---------------------------------------------------------------- the owner (page Listen, iPhone app)
def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "the panel's address is missing (base)")
    return base


def _mine(request, lid, prof):
    if not features.allowed("listlink", prof["id"]):
        raise HTTPException(403, "Mitschreib-Links are turned off (Funktionen → Listen für Einkauf und Aufgaben)")
    if not _ok_list(prof["id"], lid):
        raise HTTPException(404, "this list does not exist (any more) or lives in a calendar account")


@router.get("/api/profile/listen/{lid}/links")
def owner_links(lid: str, request: Request, prof=Depends(_on)):
    _mine(request, lid, prof)
    return {"links": links(prof["id"], lid), "days": list(DAYS)}


@router.post("/api/profile/listen/{lid}/links")
async def owner_make(lid: str, request: Request, prof=Depends(_on)):
    """{"days": 7 | 30 | 365, "see": bool, "base": "https://panel"} -> the link with its QR code, shown once."""
    _mine(request, lid, prof)
    body = await core.json_body(request, MAX_BODY)
    base = _base(body)
    try:
        kid, code = make(prof["id"], lid, body.get("days"), bool(body.get("see")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except OverflowError as e:
        raise HTTPException(409, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    link = f"{base}/#liste={code}"
    return {"id": kid, "link": link, "qr": mfa._qr_svg(link), "links": links(prof["id"], lid)}


@router.delete("/api/profile/listen/{lid}/links/{kid}")
def owner_revoke(lid: str, kid: str, request: Request, prof=Depends(_on)):
    """Taking a link back (also while the function is off by now: the owner's own data)."""
    if not _ID.fullmatch(kid) or not revoke(prof["id"], lid, kid):
        raise HTTPException(404, "no such link")
    return {"links": links(prof["id"], lid)}


# ---------------------------------------------------------------- the visitor (#liste=<code>, mitschreib.js)
def _door(request):
    if not features.admin_on("listlink"):
        raise HTTPException(404, "Not Found")
    origin = request.headers.get("origin")
    if origin and origin != "null" and urlsplit(origin).netloc.lower() != (request.headers.get("host") or "").lower():
        raise HTTPException(403, "not from another site")
    guard.limit(request, "mitschreib")
    guard.check(request, KEY)


def _link(request, code):
    v = find(code)
    if not v:
        _count.bump("abgelehnt")
        guard.failed(request, KEY, what="list_link")
        print("tasks: link refused | bad code", flush=True)
        raise HTTPException(400, "Der Link passt nicht oder ist abgelaufen.")
    return v


def _view(v):
    owner, lid = v["owner"], v["list"]
    d = tasks._load(owner)
    li = next(x for x in tasks.lists_of(owner, d) if x["id"] == lid)
    out = {"name": li["name"], "name_en": li["name_en"] if not li["own"] else li["name"], "icon": li["icon"],
           "until": v["until"], "see": bool(v.get("see"))}
    if v.get("see"):
        out["items"] = [tasks.show(x) for x in d["items"]
                        if x["list"] == lid and not x.get("sent") and not x.get("done")][:200]
    return out


@router.post("/api/liste/check")
async def visitor_check(request: Request):
    """What the visitor's page shows: the list's name and symbol, until when, and with „sehen“ the open entries."""
    _door(request)
    body = await core.json_body(request, MAX_BODY)
    return _view(_link(request, body.get("code")))


@router.post("/api/liste/add")
async def visitor_add(request: Request):
    """{"code", "text", "name"?}: puts entries on (comma separated like on the page)."""
    _door(request)
    body = await core.json_body(request, MAX_BODY)
    v = _link(request, body.get("code"))
    text = str(body.get("text") or "")[:MAX_TEXT]
    name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(body.get("name") or "")).strip()[:NAME_MAX]
    parts = [p for p in (tasks.clean(x) for x in text.split(",")) if p][:10]
    if not parts:
        raise HTTPException(400, "Bitte etwas eintragen.")
    try:
        added = await tasks.add(v["owner"], v["list"], parts, src="link", guest=name)
    except notaus.NotausAktiv:
        raise HTTPException(503, "Gerade nicht möglich.")
    except ValueError:
        raise HTTPException(400, "Der Link passt nicht oder ist abgelaufen.")
    _count.bump("eingetragen", len(added))
    return dict(_view(v), added=len(added))
