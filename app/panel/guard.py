"""Protection of the logins: lockout after wrong passwords or PINs, requests from foreign pages,
and the change log (who changed what, from where).

Lockout: after MAX_FAILS wrong attempts from one address within WINDOW seconds (or MAX_NAME_FAILS
for one profile name, from anywhere), logins from there are refused for a while; every new lockout
doubles the wait, up to LOCK_MAX. A correct login clears the counter. Kept in memory: a restart of
the panel forgets it, which is fine for a box in the LAN.

Foreign pages: a page from another site (also another port on the same host, e.g. another web app
on the Spark) must not use the browser's login cookies to change anything here. Changing requests
that carry a login cookie must come from the panel's own page (Origin or Sec-Fetch-Site).

Change log: STATE/audit.log, one JSON line per event, rotated at AUDIT_MAX bytes (one old file).
"""
import ipaddress
import json
import os
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException
from fastapi.responses import JSONResponse

MAX_FAILS, MAX_NAME_FAILS, WINDOW = 5, 10, 15 * 60
LOCK_FIRST, LOCK_MAX = 60, 3600
_fails, _locks = {}, {}
BASIC = "\0basic"
_lock = threading.Lock()

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
AUDIT = os.path.join(STATE, "audit.log")
AUDIT_MAX = 1_000_000


def client_ip(request):
    """The browser's address. Behind a reverse proxy in the LAN (the direct peer is a private or
    loopback address) the proxy's X-Forwarded-For says who it is, else every user would share the
    proxy's address and one bad guesser would lock everybody out."""
    peer = (request.client.host if request.client else "") or "?"
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd and from_lan(request):
        return fwd.split(",")[-1].strip()[:64] or peer
    return peer


def from_lan(request):
    """The direct peer is in the LAN (a reverse proxy there may set X-Forwarded-* headers)."""
    try:
        ip = ipaddress.ip_address(request.client.host if request.client else "")
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def https(request):
    """The browser talks https to the panel or to the reverse proxy in front of it."""
    proto = request.headers.get("x-forwarded-proto", "") if from_lan(request) else ""
    return request.url.scheme == "https" or proto.split(",")[0].strip().lower() == "https"


def _keys(request, name=None):
    if name == BASIC:  # scripts with HTTP Basic: counted apart, so a stale browser login cannot lock the page
        return [("basic", client_ip(request))]
    keys = [("ip", client_ip(request))]
    if name:
        keys.append(("name", str(name).strip().lower()[:60]))
    return keys


def wait_left(request, name=None):
    """Seconds until a login from here (or for this name) is allowed again, 0 if it is now."""
    now = time.time()
    with _lock:
        return max([int(_locks.get(k, (0, 0))[0] - now) + 1 for k in _keys(request, name)
                    if _locks.get(k, (0, 0))[0] > now] or [0])


def check(request, name=None):
    """Raises 429 while logins from here (or for this name) are locked."""
    left = wait_left(request, name)
    if left:
        raise HTTPException(429, f"too many wrong attempts, try again in {_human(left)}",
                            headers={"Retry-After": str(left)})


def failed(request, name=None, what="login"):
    now = time.time()
    locked = 0
    with _lock:
        for k in _keys(request, name):
            q = _fails.setdefault(k, deque(maxlen=MAX_NAME_FAILS))
            q.append(now)
            limit = MAX_NAME_FAILS if k[0] == "name" else MAX_FAILS
            recent = [t for t in q if now - t < WINDOW]
            if len(recent) >= limit:
                level = _locks.get(k, (0, 0))[1] + 1
                secs = min(LOCK_MAX, LOCK_FIRST * 2 ** (level - 1))
                _locks[k] = (now + secs, level)
                q.clear()
                locked = max(locked, secs)
    log(what + "_failed", ip=client_ip(request), name="" if name == BASIC else name, locked=locked or None)


def succeeded(request, name=None):
    with _lock:
        for k in _keys(request, name):
            _fails.pop(k, None)
            if k in _locks and _locks[k][0] <= time.time():
                _locks.pop(k, None)


def _human(secs):
    return f"{secs} s" if secs < 120 else f"{round(secs / 60)} min"


def reset():
    with _lock:
        _fails.clear()
        _locks.clear()


# ---------------------------------------------------------------- requests from foreign pages
CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def same_origin(request, cookies):
    """False for a changing request that carries one of the login cookies and comes from another page."""
    if request.method not in CHANGING or not any(request.cookies.get(c) for c in cookies):
        return True
    # Browsers say themselves whether a request comes from the same page; this also holds behind a
    # reverse proxy, which may change the Host header.
    site = request.headers.get("sec-fetch-site")
    if site:
        return site in ("same-origin", "none")
    origin = request.headers.get("origin")
    if origin and origin != "null":
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        return urlsplit(origin).netloc.lower() == host.lower()
    return True  # neither header: not a browser (scripts, old clients)


def foreign_page():
    return JSONResponse({"detail": "request from another page refused"}, status_code=403)


# ---------------------------------------------------------------- change log
_audit_lock = threading.Lock()
# changing requests that are normal use, not a change worth logging
QUIET = ("/api/chat", "/api/assistant/say", "/api/watch/", "/api/profile/convos", "/api/test/",
         "/api/profile/calendar/test", "/api/profile/mail/test", "/api/profile/homeassistant/test", "/api/login", "/api/logout",
         "/api/profile/login", "/api/profile/logout", "/api/profile/reminders")


def log(event, **detail):
    item = {"t": int(time.time()), "event": event}
    item.update({k: v for k, v in detail.items() if v not in (None, "")})
    try:
        with _audit_lock:
            os.makedirs(STATE, exist_ok=True)
            if os.path.exists(AUDIT) and os.path.getsize(AUDIT) > AUDIT_MAX:
                os.replace(AUDIT, AUDIT + ".1")
            with open(os.open(AUDIT, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError as e:
        print("audit:", e, flush=True)


def read(limit=300, user=None):
    """Newest first; with user only the entries about that profile id."""
    out = []
    for path in (AUDIT, AUDIT + ".1"):
        try:
            with open(path) as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if user and item.get("uid") != user:
                continue
            out.append(item)
            if len(out) >= limit:
                return out
    return out


def logged(path, method):
    return method in CHANGING and path.startswith("/api/") and not path.startswith(QUIET)
