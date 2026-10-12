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
    if _first_hint(peer):
        print(f"guard: X-Forwarded-For from {peer} ignored; enter the reverse proxy under "
              "Einstellungen -> Sicherheit (panel.trusted_proxies)", flush=True)
    return False


HINTED = os.path.join(STATE, "guard-xff-hinted.json")


def _first_hint(peer, now=None):
    """The hint above once per day and address, also across panel restarts (every update restarts the
    panel; the log on tars had it 39 times a day for the same proxy)."""
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))
    if not _hinted:
        try:
            with open(HINTED) as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("day") == day and isinstance(d.get("peers"), list):
                _hinted.update(str(x)[:64] for x in d["peers"][:20])
            _hinted.add("day:" + str(d.get("day") if isinstance(d, dict) else ""))
        except (OSError, ValueError):
            pass
    if "day:" + day not in _hinted:
        _hinted.clear()
        _hinted.add("day:" + day)
    if peer in _hinted or len(_hinted) > 20:
        return False
    _hinted.add(peer)
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(HINTED + ".part", "w") as f:
            json.dump({"day": day, "peers": sorted(x for x in _hinted if not x.startswith("day:"))}, f)
        os.replace(HINTED + ".part", HINTED)
    except OSError:
        pass
    return True


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
    """A name's lock does not hold for a browser that logged in to that name before. Only the browser
    counts, not the address: a housemate behind the same address (or with a profile of their own,
    whose browser is known for that other name) must not guess this name's PIN without any limit."""
    if browser and k[0] == "ip" and any(browser in v for v in _known.values()):
        return False  # a browser that logged in here before (e.g. all users behind one proxy address)
    return k[0] != "name" or not browser or browser not in _known.get(k, ())


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
    _watch(request, "login")
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
    try:   # Zustand → Live: the Eingang list (sender shortened, no name)
        import live
        live.refused(request, what, locked)
    except Exception:
        pass


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
    _to_live(event)


# What the audit log notes shows on Zustand → Live under "Ereignisse" (live.py), in fixed words: never who,
# which device, which address or any detail. Kinds that report there themselves (Notaus, watchdog, monitors)
# and the generic "change" are left out.
LIVE_WORDS = {
    "profile_login": ("Eingang", "Anmeldung eines Profils"), "admin_login": ("Eingang", "Admin-Anmeldung"),
    "handoff_login": ("Eingang", "Anmeldung per Übergabe"), "trusted_browser": ("Eingang", "neuer vertrauter Browser"),
    "trusted_browser_removed": ("Eingang", "vertrauter Browser entfernt"),
    "admin_mode_on": ("Eingang", "Admin-Modus geöffnet"), "admin_mode_off": ("Eingang", "Admin-Modus beendet"),
    "admin_mode_failed": ("Eingang", "Admin-Modus abgewiesen"), "notzugang_cli": ("Eingang", "Notzugang auf dem Spark zurückgesetzt"), "passkey_added": ("Eingang", "Passkey angelegt"),
    "passkey_removed": ("Eingang", "Passkey entfernt"), "invite_used": ("Eingang", "Einladung benutzt"),
    "invite_made": ("Eingang", "Einladung erstellt"), "invite_revoked": ("Eingang", "Einladung zurückgezogen"),
    "invite_app": ("Eingang", "Einladung in der App angenommen"), "profile_device_removed": ("Eingang", "Gerät entfernt"),
    "profile_logout_all": ("Eingang", "Profil überall abgemeldet"), "profile_session_end": ("Eingang", "Sitzung beendet"),
    "mcp_connect": ("Eingang", "Programm per MCP verbunden"), "mcp_remove": ("Eingang", "MCP-Zugang entfernt"),
    "mcp_action": ("MCP", "Aktion entschieden"), "remarkable_pair": ("Geräte", "reMarkable gekoppelt"),
    "remarkable_unpair": ("Geräte", "reMarkable entkoppelt"), "speaker_code_set": ("Sprechererkennung", "Codewort gesetzt"),
    "profile_mfa_on": ("Sicherheit", "zweiter Schritt an (Profil)"), "profile_mfa_off": ("Sicherheit", "zweiter Schritt aus (Profil)"),
    "admin_mfa_on": ("Sicherheit", "zweiter Schritt an (Admin)"), "admin_mfa_off": ("Sicherheit", "zweiter Schritt aus (Admin)"),
    "admin_password_changed": ("Sicherheit", "Admin-Passwort geändert"),
    "admin_logout_everywhere": ("Sicherheit", "Admin überall abgemeldet"), "admin_role": ("Sicherheit", "Rolle geändert"),
    "config_switch": ("Einstellungen", "Schalter geändert"), "config_weiche": ("Einstellungen", "Weiche geändert"), "config_sensitive": ("Einstellungen", "Sicherheitseinstellung geändert"),
    "config_undo": ("Einstellungen", "Änderung zurückgenommen"), "feature_profile": ("Einstellungen", "Funktion für ein Profil geändert"),
    "backup": ("Sicherung", "Sicherung erstellt"), "backup_failed": ("Sicherung", "Sicherung fehlgeschlagen"),
    "backup_download": ("Sicherung", "Sicherung heruntergeladen"), "restore": ("Sicherung", "Sicherung eingespielt"),
    "offsite_backup": ("Sicherung", "Sicherung nach außen übertragen"), "offsite_failed": ("Sicherung", "Sicherung nach außen fehlgeschlagen"),
    "rollback": ("Update", "Rückkehr zur vorigen Version gestartet"), "update_from_app": ("Update", "Update aus der App gestartet"),
    "livecheck_failed": ("Dienste", "Funktionsprüfung fehlgeschlagen"), "memory_low": ("Dienste", "Speicher knapp"),
    "room_end": ("Raum-Modus", "Zuhören beendet"), "foreign_page_refused": ("Wächter", "fremde Seite abgewiesen"),
    "profile_memory_tidied": ("Hintergrund", "Gedächtnis aufgeräumt"), "person_priority": ("Vorrang", "Vorrang eines Profils geändert"),
    # added 2026-10-12 (Dominik: everything on the live page; test_live checks every kind here or in LIVE_SKIP)
    "admin_mfa_recovery": ("Sicherheit", "neue Wiederherstellungscodes"), "admin_mfa_forget": ("Sicherheit", "vertraute Browser vergessen"),
    "profile_mfa_reset": ("Sicherheit", "zweiter Schritt eines Profils zurückgesetzt"),
    "notaus_key_new": ("Sicherheit", "Notaus-Schlüssel angelegt"), "notaus_key_delete": ("Sicherheit", "Notaus-Schlüssel gelöscht"),
    "report_token": ("Sicherheit", "Token für Meldungen geändert"), "github_token": ("Sicherheit", "GitHub-Token für Updates geändert"), "ha_code_set": ("Sicherheit", "Home-Assistant-Codewort geändert"),
    "invite_pin": ("Eingang", "Einladung mit PIN geöffnet"), "handoff_ok": ("Eingang", "Übergabe-Code bestätigt"),
    "handoff_wrong": ("Eingang", "Übergabe-Code falsch"), "live_monitor_code": ("Eingang", "Code für einen Live-Monitor"),
    "live_monitor_paired": ("Eingang", "Live-Monitor gekoppelt"), "live_monitor_deleted": ("Eingang", "Live-Monitor gelöscht"),
    "mcp_change": ("Eingang", "MCP-Zugang geändert"),
    "admin_roles_switch": ("Rechte", "Rollen geändert"), "iphone_update_rights": ("Rechte", "Update-Recht der App geändert"),
    "agent_level": ("Rechte", "Stufe der Aufträge geändert"),
    "backup_move": ("Sicherung", "Sicherungsort geändert"), "offsite_settings": ("Sicherung", "Sicherung nach außen eingestellt"),
    "devup_resume": ("Geräte-Updates", "Geräte-Updates fortgesetzt"), "svcwatch": ("Dienste", "Dienst-Wächter, Dienst von der Liste genommen oder zurück"), "berater_take": ("Verbessern", "Vorschlag übernommen"), "berater_undo": ("Verbessern", "Vorschlag zurückgenommen"), "berater_reject": ("Verbessern", "Vorschlag abgelehnt"), "berater_issue": ("Verbessern", "Fall als Meldung vorbereitet"), "berater_idea": ("Verbessern", "Idee als gut markiert"), "berater_me": ("Verbessern", "Profil hat einen Vorschlag übernommen"), "storage_add": ("Speicher", "eigenen Speicher eingebunden"), "storage_change": ("Speicher", "eigenen Speicher geändert"),
    "storage_remove": ("Speicher", "eigenen Speicher getrennt"), "remarkable_send": ("Geräte", "aufs reMarkable geschickt"),
    "doc_quota": ("Dokumente", "Platz für Dokumente geändert"), "doc_unshare": ("Dokumente", "Freigabe beendet"),
    "join_settings": ("Einstellungen", "Einladungen eingestellt"), "join_packs": ("Einstellungen", "Einladungspakete geändert"),
    "setup_remind": ("Einstellungen", "Erinnerung an die Einrichtung geschickt"), "quality_case": ("Hilfe", "Korrektur in den Qualitätstest"),
    "tipp_ask": ("Hilfe", "Tipp gefragt"),
}
# kinds the live page shows in its own way (so not as a line from here): the Notaus banner, Probleme melden,
# the update card, the watchdog (live.watchdog), Hilfe cards (hilfe._live) and every changing request ("change")
LIVE_SKIP = {"notaus_on", "notaus_off", "notaus_mine_on", "notaus_mine_off", "report_sent", "update_night", "watchdog",
             "hilfe_applied", "hilfe_undone", "change"}


def _to_live(event):
    w = LIVE_WORDS.get(event)
    if w:
        try:
            import live
            live.mark(*w)
        except Exception:
            pass


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
RATE = {"chat": (30, 120), "asr": (60, 240), "logs": (1, 60), "pair": (10, 10), "doc": (0, 10), "image": (0, 10), "msg": (0, 30), "route": (0, 60), "weichesave": (0, 20), "room": (0, 60), "kiwix": (0, 10), "lokal": (0, 20), "features": (30, 120), "tipps": (0, 30),
        "rmpair": (0, 3), "rm": (0, 30), "rmsync": (0, 2), "rmsend": (0, 6), "handoff": (60, 60), "bg": (0, 30), "vorrang": (0, 60), "undo": (0, 20), "llmmodels": (0, 30), "offsite": (0, 10), "trust": (10, 30), "android": (0, 20), "androidwait": (0, 90),
        "mcp": (0, 60), "mcpask": (0, 10), "mcpreg": (10, 10), "mcptoken": (20, 20),
        "convos": (0, 120), "convostream": (0, 30), "chats": (0, 240), "chatsstream": (0, 30), "chatstyping": (0, 40), "chatsfind": (0, 20), "chatsmedia": (0, 20), "chatsinvite": (0, 6), "chatsget": (0, 600), "live": (0, 150), "livemon": (90, 90), "hilfe": (0, 30), "write": (0, 20), "desk": (0, 20), "deskask": (0, 10), "deskupd": (0, 6), "deskfile": (0, 10), "deskhear": (0, 40), "deskact": (0, 20),
        "deskspeak": (0, 20), "deskinbox": (0, 60), "desksend": (0, 20), "deskagenda": (0, 30), "deskbusy": (0, 30),
        "deskmeet": (0, 20), "deskhome": (0, 30), "deskdaily": (0, 10), "deskapps": (0, 6), "deskoffice": (0, 10),
        "haev": (0, 30), "hamelden": (0, 30), "hament": (0, 40), "notaus": (30, 60), "notausset": (0, 10), "notausoff": (0, 10), "notausha": (10, 10),
        "systemone": (0, 10), "changelog": (0, 30), "mymcp": (0, 30), "devup": (0, 20), "report": (0, 30),
        "make": (0, 60), "makejob": (0, 120), "makefile": (0, 30), "makesend": (0, 10), "maketmpl": (0, 10),
        "makedl": (20, 30), "svcwatch": (0, 30), "svcwatchnow": (0, 4),
        "rate": (0, 30), "zuordnung": (0, 60), "zuordnungset": (0, 30), "berater": (0, 60), "beraterset": (0, 30), "beraterrun": (0, 4),
        "storage": (0, 60), "storagenow": (0, 6), "ghtoken": (0, 20), "memory": (0, 60)}  # per minute: (guest, profile or admin)
BUSY = {"chat": 4, "asr": 3}  # at once, guests together


def _watch(request, kind):
    """Selbst-Notaus (notaus.watch): only what comes from outside the home network counts; never raises."""
    try:
        import notaus
        if not notaus.at_home(request):
            notaus.watch(kind)
    except Exception as e:
        print("guard: watch", type(e).__name__, flush=True)


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
        flood = len(q) >= most and now - q[0] < 60
        if not flood:
            q.append(now)
    if flood:
        if what.startswith("mcp"):
            _watch(request, "mcp")
        raise HTTPException(429, "too many requests, please wait a moment", headers={"Retry-After": "30"})


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
