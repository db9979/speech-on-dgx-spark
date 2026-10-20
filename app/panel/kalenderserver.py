"""Spark-Kalender, Stufe 4 (Dominik 2026-10-19 „1a-5a“): the Spark as a CalDAV server, so the iPhone's own calendar
app (or Thunderbird, DAVx5 on Android) shows and changes the profile's Spark calendars directly.

Who may: the admin switch chat.calendar_server (features.py "calserver", off by default), every profile the admin
did not block, never guests. A profile makes an app password under Ich → Kalender → „Für Kalender-Apps“ (in the
profile's own browser login or the iPhone app, with its code); the password is shown once, only its hash is kept
(users/<id>/kalender-server.json), „Zugang löschen“ ends it at once. A new one replaces the old one.

- Reached in the home network and through the reverse proxy (*.i234.me), like the panel; the app logs in with HTTP
  Basic: user = the profile's id, password = the app password. Wrong guesses count like a PIN (guard.failed: a lock
  after five, longer each time), every request counts against guard.RATE "caldav".
- Only the profile's own Spark calendars (sparkkalender.py), nothing of its iCloud or other accounts (the iPhone
  has those itself) and no calendar of another profile. The path names the profile; another profile's path is 404.
- What comes in is data: sparkkalender.serve checks every object (iCalendar with an appointment, sizes, count) and
  the etags; a request from a web page (Origin of another site) is refused; Mein Notaus closes the door.
- Journal: fixed words and numbers; Live: profiles with an app password, requests and refusals today.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from urllib.parse import unquote, urlsplit
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import calendars
import features
import guard
import listendav
import notaus
import profiles
import sparkkalender
from common import DayCounter, write_json
from core import assistant, browser_profile, calendar_on, calserver_on, own_profile, secret_profile

router = APIRouter()
PREFIX = "/caldav/"
FILE = "kalender-server.json"
LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: typed by hand on a phone
METHODS = ["OPTIONS", "PROPFIND", "REPORT", "GET", "HEAD", "PUT", "DELETE", "PROPPATCH", "MKCALENDAR"]
TOUCH_SECONDS = 600     # „zuletzt benutzt“ is written at most this often
_lock = threading.Lock()
_count = DayCounter()   # per day: "anfragen", "abgelehnt", "gespeichert"
_seen = {}              # uid -> when „zuletzt benutzt“ was last written


def admin_on():
    return features.admin_on("calserver")


def _file(uid):
    return profiles._path(uid, FILE)


def _load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("hash"), str) else None
    except (OSError, ValueError):
        return None


def _hash(pw):
    return hashlib.sha256(("spark-caldav:" + pw).encode()).hexdigest()


def make(uid, now=None):
    """A new app password for the profile (replaces the old one); returned once, only its hash is kept."""
    pw = "-".join("".join(secrets.choice(LETTERS) for _ in range(4)) for _ in range(5))
    with _lock:
        write_json(_file(uid), {"hash": _hash(pw), "made": int(time.time() if now is None else now), "last": None},
                   mode=0o600, dir_mode=0o700)
    _seen.pop(uid, None)
    return pw


def remove(uid):
    with _lock:
        try:
            os.remove(_file(uid))
            return True
        except OSError:
            return False


def state(uid):
    d = _load(uid) or {}
    return {"has": bool(d), "made": d.get("made"), "last": d.get("last"), "user": uid, "path": PREFIX,
            "calendars": len(_own(uid))}


def _own(uid):
    """The profile's own Spark calendars: [(entry id, name)]."""
    return [(c["id"], c.get("name") or "Spark-Kalender") for c in calendars.get(uid)["calendars"] if c.get("spark")]


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


# ---------------------------------------------------------------- the door
def _basic(request):
    head = request.headers.get("authorization", "")
    if head[:6].lower() != "basic ":
        return None, None
    try:
        user, _, pw = base64.b64decode(head[6:].strip(), validate=True).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError):
        return None, None
    return user.strip()[:80], pw.strip()[:200]


def _ask():
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Spark-Kalender", charset="UTF-8"'})


def login(request, now=None):
    """(uid, None) or (None, refusing response) for one request of a calendar app."""
    origin = request.headers.get("origin")
    if origin and origin != "null" and urlsplit(origin).netloc.lower() != (request.headers.get("host") or "").lower():
        return None, Response(status_code=403)   # a web page of another site never uses the calendar door
    user, pw = _basic(request)
    if not user:
        return None, _ask()
    name = "caldav:" + user
    guard.check(request, name)
    d = _load(user) if profiles.by_id(user) else None
    if not d or not pw or not hmac.compare_digest(d["hash"], _hash(pw)):
        _count.bump("abgelehnt")
        guard.failed(request, name, what="caldav_login")
        print("calendar: caldav login refused | wrong user or app password", flush=True)
        return None, _ask()
    if notaus.own(user):
        _count.bump("abgelehnt")
        print(f"calendar: caldav refused, notaus | {_who(user)}", flush=True)
        return None, Response(status_code=503)
    if not features.allowed("calserver", user):
        _count.bump("abgelehnt")
        print(f"calendar: caldav refused, switched off | {_who(user)}", flush=True)
        return None, Response(status_code=403)
    guard.limit(request, "caldav", user)
    now = time.time() if now is None else now
    if now - _seen.get(user, 0) >= TOUCH_SECONDS:
        _seen[user] = now
        guard.succeeded(request, name)
        with _lock:
            d["last"] = int(now)
            write_json(_file(user), d, mode=0o600, dir_mode=0o700)
    return user, None


def _ms(responses):
    status, head, body = sparkkalender._ms(responses)
    return Response(content=body, status_code=status, headers=head)


def _principal(uid, depth):
    home = f"{PREFIX}{uid}/"
    me = (f"<d:current-user-principal><d:href>{home}</d:href></d:current-user-principal>"
          f"<d:principal-URL><d:href>{home}</d:href></d:principal-URL>"
          f"<c:calendar-home-set><d:href>{home}</d:href></c:calendar-home-set>")
    name = escape((profiles.by_id(uid) or {}).get("name") or "Spark")
    out = [sparkkalender._resp(home, f"<d:resourcetype><d:collection/><d:principal/></d:resourcetype>"
                                     f"<d:displayname>{name}</d:displayname>{me}")]
    if depth == "1":
        for cid, title in _own(uid):
            cal = sparkkalender.calendar(uid, cid)
            if cal is not None:
                out.append(sparkkalender.collection(cal, f"{home}{cid}/", title))
        out += [listendav.collection(uid, part, li, f"{home}{part}/") for part, li in listendav.collections(uid)]
    return out


@router.api_route("/.well-known/caldav", methods=["GET", "PROPFIND", "OPTIONS"])
def well_known():
    """RFC 6764: the calendar app finds the server from the bare address."""
    if not admin_on():
        raise HTTPException(404, "not found")
    return Response(status_code=301, headers={"Location": PREFIX})


@router.api_route("/caldav", methods=METHODS)
@router.api_route("/caldav/{rest:path}", methods=METHODS)
async def caldav(request: Request, rest: str = ""):
    if not admin_on():
        raise HTTPException(404, "not found")
    method = request.method.upper()
    if method == "OPTIONS" and not request.headers.get("authorization"):
        return Response(status_code=200, headers={"DAV": "1, 2, calendar-access", "Allow": ", ".join(METHODS)})
    uid, refused = login(request)
    if refused:
        return refused
    _count.bump("anfragen")
    parts = [unquote(p) for p in rest.split("/") if p]
    body = await request.body() if method in ("PROPFIND", "REPORT", "PUT", "PROPPATCH") else b""
    if method == "OPTIONS":
        return Response(status_code=200, headers={"DAV": "1, 2, calendar-access", "Allow": ", ".join(METHODS)})
    if not parts:   # the root: who is logged in
        if method != "PROPFIND":
            return Response(status_code=405)
        home = f"{PREFIX}{uid}/"
        return _ms([sparkkalender._resp(PREFIX, "<d:resourcetype><d:collection/></d:resourcetype>"
                                                f"<d:current-user-principal><d:href>{home}</d:href></d:current-user-principal>"
                                                f"<c:calendar-home-set><d:href>{home}</d:href></c:calendar-home-set>")])
    if parts[0] != uid or len(parts) > 3:
        return Response(status_code=404)   # only the logged-in profile's own path
    if len(parts) == 1:   # the profile: principal and calendar home in one
        if method == "PROPFIND":
            return _ms(_principal(uid, request.headers.get("depth", "0")))
        if method in ("PROPPATCH", "MKCALENDAR"):
            return Response(status_code=403)   # new calendars are made on the Spark (Ich → Kalender)
        return Response(status_code=405)
    cid = parts[1]
    lists = cid.startswith(listendav.PART)   # a Spark list as a task list (listendav.py, Listen Stufe 3)
    title = None if lists else dict(_own(uid)).get(cid)
    if title is None and not lists:
        return Response(status_code=404)   # not an own Spark calendar of this profile
    if method in ("PROPPATCH", "MKCALENDAR"):
        return Response(status_code=403)   # name and colour are kept on the Spark
    name = parts[2] if len(parts) == 3 else ""
    writes = method in ("PUT", "DELETE")
    if writes:
        try:
            notaus.stop("aktion", uid)
        except notaus.NotausAktiv:
            print(f"calendar: caldav not saved, notaus | {_who(uid)}", flush=True)
            return Response(status_code=423)
    if lists:
        status, head, out = listendav.serve(uid, cid, method, name, request.headers, body, f"{PREFIX}{uid}/{cid}/")
        return Response(content=out, status_code=status, headers=head)
    status, head, out = sparkkalender.serve(uid, cid, method, name, request.headers, body, f"{PREFIX}{uid}/{cid}/", title)
    if writes:
        if status < 300:
            _count.bump("gespeichert")
            calendars.changed_outside(uid, cid)
            print(f"calendar: caldav {'deleted' if method == 'DELETE' else 'saved'} | {_who(uid)}", flush=True)
        else:
            print(f"calendar: caldav not saved ({status}) | {_who(uid)}", flush=True)
    return Response(content=out, status_code=status, headers=head)


# ---------------------------------------------------------------- the profile's own page
@router.get("/api/profile/calserver", dependencies=[Depends(assistant), Depends(calendar_on), Depends(calserver_on)])
def server_state(request: Request, prof=Depends(own_profile)):
    guard.limit(request, "kalenderserver", prof["id"])
    return state(prof["id"])


@router.post("/api/profile/calserver", dependencies=[Depends(assistant), Depends(calendar_on), Depends(calserver_on)])
async def server_make(request: Request, prof=Depends(secret_profile)):
    """A new app password (shown once); the old one stops working."""
    guard.limit(request, "kalenderserver", prof["id"])
    pw = make(prof["id"])
    print(f"calendar: caldav password made | {_who(prof['id'])}", flush=True)
    return dict(state(prof["id"]), password=pw)


@router.delete("/api/profile/calserver", dependencies=[Depends(assistant)])
def server_remove(request: Request, prof=Depends(browser_profile)):
    """Ends the access of every calendar app at once (also when the function is off by now)."""
    guard.limit(request, "kalenderserver", prof["id"])
    gone = remove(prof["id"])
    print(f"calendar: caldav password {'removed' if gone else 'not there'} | {_who(prof['id'])}", flush=True)
    return state(prof["id"])


def for_live():
    """Live (Kalender): profiles with an app password, requests, refusals and saved changes today; numbers only."""
    c = _count.counts()
    n = sum(1 for uid in profiles.user_ids() if os.path.exists(_file(uid)))
    return {"on": admin_on(), "profiles": n, "requests": c.get("anfragen", 0), "refused": c.get("abgelehnt", 0),
            "saved": c.get("gespeichert", 0)}
