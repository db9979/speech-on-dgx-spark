"""Protection of the logins: lockout after wrong passwords or PINs, requests from foreign pages,
and the change log (who changed what, from where).

Lockout: after MAX_FAILS wrong attempts from one address within WINDOW seconds (or MAX_NAME_FAILS
for one profile name or the admin password, from anywhere), logins from there are refused for a
while; every new lockout doubles the wait, up to LOCK_MAX. On top, a name gets at most DAY_FAILS
wrong attempts in 24 hours. The locks of a name do not apply to addresses that logged in to it
before (KNOWN), nor for browsers that logged in to it before (cookie speech_known, only its hash is
kept; such a browser also passes the lock of its address), so a stranger guessing cannot lock
the owner out at home or on the phone. A correct login clears the counter. Kept in STATE/guard.json, so a restart of the panel does not reset the count; the
kept entries are pruned and capped (MAX_KEYS), so made-up names and changing addresses cannot grow it.

Reverse proxy: X-Forwarded-For is only taken from the addresses in panel.trusted_proxies, or from a
proxy on this host (loopback) while that list is empty. Any other device could otherwise claim to be
any address and get around the lockout.

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
DAY_FAILS, KNOWN = 30, 20
MAX_KEYS = 2000
KNOWN_COOKIE = "speech_known"
_fails, _locks, _day, _known = {}, {}, {}, {}
BASIC = "\0basic"
ADMIN = "\0admin"
_lock = threading.Lock()

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
AUDIT = os.path.join(STATE, "audit.log")
AUDIT_MAX = 1_000_000
SAVED = os.path.join(STATE, "guard.json")


def _k(key):
    return "|".join(key)


def _prune(now):
    """Forget what no longer counts, and cap what is kept (called with _lock held)."""
    for k in [k for k, q in _fails.items() if not q or now - q[-1] > WINDOW]:
        _fails.pop(k, None)
    for k in [k for k, v in _locks.items() if v[0] < now - LOCK_MAX * 4]:
        _locks.pop(k, None)
    for k in [k for k, q in _day.items() if not q or now - q[-1] > 86400]:
        _day.pop(k, None)
    for d, age in ((_fails, lambda q: q[-1]), (_locks, lambda v: v[0]), (_day, lambda q: q[-1])):
        if len(d) > MAX_KEYS:
            for k in sorted(d, key=lambda k: age(d[k]))[:len(d) - MAX_KEYS]:
                d.pop(k, None)


def _save():
    """Locks, the 24 hour counts and the known addresses survive a restart (called with _lock held)."""
    data = {"locks": {_k(k): v for k, v in _locks.items()}, "day": {_k(k): list(v) for k, v in _day.items()},
            "known": {_k(k): sorted(v) for k, v in _known.items()}}
    try:
        tmp = SAVED + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(data, f)
        os.replace(tmp, SAVED)
    except OSError:
        pass


def _restore():
    try:
        with open(SAVED) as f:
            data = json.load(f)
        now = time.time()
        for k, v in data.get("locks", {}).items():
            if v[0] > now - LOCK_MAX * 4:  # an old level does not double new waits for ever
                _locks[tuple(k.split("|", 1))] = (float(v[0]), int(v[1]))
        for k, v in data.get("day", {}).items():
            _day[tuple(k.split("|", 1))] = deque((t for t in v if now - t < 86400), maxlen=DAY_FAILS)
        for k, v in data.get("known", {}).items():
            _known[tuple(k.split("|", 1))] = set(v[-KNOWN:])
    except (OSError, ValueError, TypeError, IndexError):
        pass


_restore()


def _proxies():
    try:
        from common import load_config
        return [str(x) for x in load_config().get("panel", {}).get("trusted_proxies", []) or []]
    except Exception:
        return []


def client_ip(request):
    """The browser's address. Behind a reverse proxy in the LAN (the direct peer is a private or
    loopback address) the proxy's X-Forwarded-For says who it is, else every user would share the
    proxy's address and one bad guesser would lock everybody out."""
    peer = (request.client.host if request.client else "") or "?"
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd and forward_trusted(request):
        return fwd.split(",")[-1].strip()[:64] or peer
    return peer


_hinted = set()


def forward_trusted(request):
    """X-Forwarded-For counts only from a listed proxy (or from this host while none is listed)."""
    peer = (request.client.host if request.client else "") or "?"
    proxies = _proxies()
    if proxies:
        return peer in proxies
    try:
        if ipaddress.ip_address(peer).is_loopback:
            return True
    except ValueError:
        return False
    if peer not in _hinted and len(_hinted) < 20:
        _hinted.add(peer)
        print(f"guard: X-Forwarded-For from {peer} ignored; enter the reverse proxy under "
              "Einstellungen -> Sicherheit (panel.trusted_proxies)", flush=True)
    return False


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


def _browser(request):
    raw = request.cookies.get(KNOWN_COOKIE, "")
    if not raw or len(raw) > 100:
        return None
    import hashlib
    return "b:" + hashlib.sha256(raw.encode()).hexdigest()


def _applies(k, ip, browser=None):
    """A name's lock does not hold for addresses or browsers that logged in to that name before."""
    if browser and k[0] == "ip" and any(browser in v for v in _known.values()):
        return False  # a browser that logged in here before (e.g. all users behind one proxy address)
    known = _known.get(k, ())
    return k[0] != "name" or (ip not in known and (not browser or browser not in known))


def wait_left(request, name=None):
    """Seconds until a login from here (or for this name) is allowed again, 0 if it is now."""
    now = time.time()
    ip, browser = client_ip(request), _browser(request)
    with _lock:
        return max([int(_locks.get(k, (0, 0))[0] - now) + 1 for k in _keys(request, name)
                    if _locks.get(k, (0, 0))[0] > now and _applies(k, ip, browser)] or [0])


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
            if k[0] == "name":
                day = _day.setdefault(k, deque(maxlen=DAY_FAILS))
                day.append(now)
                if len(day) >= DAY_FAILS and now - day[0] < 86400:  # the day's guesses are used up
                    until = day[0] + 86400
                    if until > _locks.get(k, (0, 0))[0]:
                        _locks[k] = (until, _locks.get(k, (0, 0))[1])
                        locked = max(locked, int(until - now))
        _prune(now)
        _save()
    log(what + "_failed", ip=client_ip(request), name="" if name in (BASIC, ADMIN) else name, locked=locked or None)


def succeeded(request, name=None, response=None):
    """A correct login. With response, the browser gets the cookie that lets it past this name's
    lock next time (strangers' guesses then cannot lock it out, also from a new address)."""
    ip = client_ip(request)
    browser = _browser(request)
    if response is not None and name and name != BASIC:
        import hashlib
        import secrets
        raw = request.cookies.get(KNOWN_COOKIE, "")
        if not browser:
            raw = secrets.token_urlsafe(24)
            browser = "b:" + hashlib.sha256(raw.encode()).hexdigest()
        response.set_cookie(KNOWN_COOKIE, raw, max_age=365 * 86400, httponly=True, samesite="strict")
    with _lock:
        for k in _keys(request, name):
            if k[0] == "name":
                known = _known.setdefault(k, set())
                known.add(ip)
                if response is not None and browser:
                    known.add(browser)
                while len(known) > KNOWN:
                    known.pop()
                continue  # strangers' failed guesses for this name keep counting
            _fails.pop(k, None)
            if k in _locks and _locks[k][0] <= time.time():
                _locks.pop(k, None)
        _save()


# ---------------------------------------------------------------- logged-out cookies
# A logout makes that browser's login cookie worthless on the server too (a copy of it no longer
# works); kept until the cookie would have expired anyway.
REVOKED = os.path.join(STATE, "revoked.json")
_revoked = None


def _rev():
    global _revoked
    if _revoked is None:
        try:
            with open(REVOKED) as f:
                _revoked = {k: float(v) for k, v in json.load(f).items()}
        except (OSError, ValueError, AttributeError):
            _revoked = {}
    return _revoked


def revoke(raw, ttl):
    import hashlib
    if not raw:
        return
    now = time.time()
    with _lock:
        r = _rev()
        for k in [k for k, v in r.items() if v < now]:
            r.pop(k, None)
        r[hashlib.sha256(raw.encode()).hexdigest()] = now + ttl
        try:
            tmp = REVOKED + ".tmp"
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                json.dump(r, f)
            os.replace(tmp, REVOKED)
        except OSError:
            pass


def revoked(raw):
    import hashlib
    r = _rev()
    return bool(r) and hashlib.sha256(raw.encode()).hexdigest() in r


def _human(secs):
    return f"{secs} s" if secs < 120 else f"{round(secs / 60)} min"


def reset():
    with _lock:
        _fails.clear()
        _locks.clear()
        _day.clear()
        _known.clear()
        _save()


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
QUIET = ("/api/chat", "/api/siri/", "/api/assistant/say", "/api/watch/", "/api/profile/convos", "/api/test/",
         "/api/profile/calendar/test", "/api/profile/mail/test", "/api/profile/homeassistant/test", "/api/login", "/api/logout",
         "/api/profile/login", "/api/profile/logout", "/api/profile/reminders", "/api/tasks/inbox",
         "/api/admin/elevate")   # opening, keeping and ending the admin mode have their own entries (admin_mode_*)


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


# ---------------------------------------------------------------- load limits
# Chat, speech recognition and watch answers cost GPU time. Per caller (profile, else address) only
# so many requests per minute, and only so many at once for callers without a profile (guests, when
# the assistant is open without login), so one page or script cannot take the Spark for itself.
_rate, _busy = {}, {}
_rate_lock = threading.Lock()
RATE = {"chat": (30, 120), "asr": (60, 240), "logs": (1, 60), "pair": (10, 10), "doc": (0, 10), "image": (0, 10), "msg": (0, 30), "route": (0, 60), "room": (0, 60), "kiwix": (0, 10), "lokal": (0, 20), "features": (30, 120),
        "rmpair": (0, 3), "rm": (0, 30), "rmsync": (0, 2), "rmsend": (0, 6), "handoff": (60, 60), "bg": (0, 30), "vorrang": (0, 60), "undo": (0, 20), "offsite": (0, 10)}  # per minute: (guest, profile or admin)
BUSY = {"chat": 4, "asr": 3}  # at once, guests together


def caller(request, uid=None):
    return ("u", uid) if uid else ("ip", client_ip(request))


def limit(request, what, uid=None, admin=False):
    """Raises 429 when this caller asked too often in the last minute."""
    now = time.time()
    key = (what,) + caller(request, uid or ("admin" if admin else None))
    most = RATE[what][1 if uid or admin else 0]
    with _rate_lock:
        q = _rate.get(key)
        if q is None:
            if len(_rate) > MAX_KEYS:
                for k in [k for k, v in _rate.items() if not v or now - v[-1] > 60]:
                    _rate.pop(k, None)
            q = _rate[key] = deque(maxlen=most)
        if len(q) >= most and now - q[0] < 60:
            raise HTTPException(429, "too many requests, please wait a moment", headers={"Retry-After": "30"})
        q.append(now)


class Slot:
    """One of the few places guests share (BUSY); free it with release() (safe to call twice). A place
    nobody released (a stream that never started) counts as free again after SLOT_MAX seconds."""
    SLOT_MAX = 600

    def __init__(self, what):
        self.what, self.id = what, object()
        now = time.time()
        with _rate_lock:
            held = _busy.setdefault(what, {})
            for k in [k for k, t in held.items() if now - t > self.SLOT_MAX]:
                held.pop(k, None)
            if len(held) >= BUSY[what]:
                raise HTTPException(429, "the assistant is busy, please try again in a moment",
                                    headers={"Retry-After": "10"})
            held[self.id] = now

    def release(self):
        with _rate_lock:
            _busy.get(self.what, {}).pop(self.id, None)
