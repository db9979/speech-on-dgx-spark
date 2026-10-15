"""NAS-Verbindung (plan plaene/synology-bauplan.md, S1; Dominik 2026-10-13 "S1 - S8 umsetzen").

One connection per NAS: address, kind (WebDAV, SMB 3, SFTP), user, password, the accepted certificate (WebDAV) or
the server's key (SFTP). Everything the Spark does with a NAS uses it: Eigener Speicher (speicher.py), the backup
to the NAS (offsite.py) and, in later stages, the Wissensordner, the Ablage and the NAS's state. The address and
the password are typed once; a new password or an accepted certificate counts for every use at once.

Two stores, each with at most MAX connections:
    USERS_DIR/<uid>/nas.json   {"nas": [conn]}   a profile's places (Ich → Speicher, nas.js)
    STATE/nas-admin.json       {"nas": [conn]}   the Spark's NAS (backup), only the main admin
    conn = {"id", "name", "kind" (webdav, smb, sftp), "url" (scheme://host[:port], no path), "user",
            "password" (sealed), "cert" (PEM, public; webdav), "hostkey" (sftp), "added", "checked"}

How the uses keep working unchanged (S1, "Umstellung"): a use stores {"nas": id, "path": "/folder"} instead of
address, user and password. expand() fills the full address and the login back in when the use is read,
collapse() writes them into the connection when the use is saved (the same kind, address and user mean the same
connection). So an old speicher.json or offsite.json is moved over the first time it is saved (and once at start,
migrate_all), and a restored old backup still works. The old file stays readable as it was.

Rules (fixed, not decided by the model): adding a connection or changing its user, password, certificate or
server key only in the profile's browser login with a code (stufen.py); a connection that a use still needs is
not removed (409); the password never comes back; the certificate check is never switched off: a certificate
that does not fit is accepted only by its fingerprint (zertpin.py), and a new one stops every use until it is
accepted again. Connections go through netguard HOME (a NAS lives in the home network) with the IP checked once.

Zustand → Live: target "NAS" (live.py "nas", numbers only), events when a connection is added, changed or removed
(guard.LIVE_WORDS). Logs →
Diagnose, area "NAS" (lines "nas: ..."), only fixed words, kinds and numbers, never an address or a name.
"""
import asyncio
import json
import os
import re
import secrets
import ssl
import threading
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import netguard
import profiles
import vault
import zertpin
from common import STATE, write_json
import core
from core import auth, browser_profile, secret_profile

router = APIRouter()
ADMIN_FILE = "nas-admin.json"
ADMIN = None                     # the owner of the Spark's own connections (STATE/nas-admin.json)
MAX = 4                          # connections a person adds per store (two NAS, each with two users, is plenty)
HARD = 16                        # what a store ever holds (moved-over uses may bring more than MAX)
KINDS = ("webdav", "smb", "sftp")
SCHEMES = {"webdav": ("https", "http"), "smb": ("smb",), "sftp": ("sftp",)}
PORTS = {"https": 443, "http": 80, "smb": 445, "sftp": 22}
ID = re.compile(r"[0-9a-f]{6}")
NAME = re.compile(r"[A-Za-zÄÖÜäöüß0-9 ._\-]{1,40}")
HOSTKEY = re.compile(r"[a-z0-9@.\-]{3,40} SHA256:[A-Za-z0-9+/]{43}")
TIMEOUT = 20
# what a use of a connection is called on the page (fixed words): name -> function(owner) -> {id: count}
USES = {}
USE_NAMES = {"speicher": "Kopie meiner Daten", "sicherung": "Sicherung", "wissen": "Wissensordner", "ablage": "Ablage-Ordner"}
WHY = {"offline": ("nicht erreichbar", "not reachable"), "auth": ("Anmeldung abgelehnt", "sign-in refused"),
       "cert": ("Zertifikat passt nicht", "certificate does not fit"), "hostkey": ("Schlüssel des Servers hat sich geändert", "the server's key changed"),
       "blocked": ("vom Wächter nicht erlaubt", "not allowed by the Wächter"), "notaus": ("Notaus", "kill switch"),
       "other": ("antwortet nicht wie erwartet", "does not answer as expected")}
_lock = threading.RLock()


class NasError(Exception):
    def __init__(self, kind, text=""):
        super().__init__(text or kind)
        self.kind = kind if kind in WHY else "other"


# ---------------------------------------------------------------- switches
def admin_on(c=None):
    return features.admin_on("nas", c)


# ---------------------------------------------------------------- addresses
def home_name(host):
    import ipaddress
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host.endswith((".local", ".lan", ".home", ".fritz.box", ".home.arpa", ".internal")) or "." not in host


def split(url, kind):
    """A full address of a use -> (the connection's address scheme://host[:port], the path "/a/b" or "")."""
    url = str(url or "").strip()
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if kind not in KINDS or u.scheme not in SCHEMES[kind] or not host or u.username or u.password or u.query \
            or u.fragment or len(url) > 300 or re.search(r"[\s\x00-\x1f\\]", url):
        raise ValueError("bad address")
    try:
        port = u.port
    except ValueError:
        raise ValueError("bad port")
    if not re.fullmatch(r"[a-z0-9.\-]{1,253}|\[[0-9a-f:.]{2,45}\]", host if ":" not in host else f"[{host}]"):
        raise ValueError("bad host")
    hostpart = f"[{host}]" if ":" in host else host
    base = f"{u.scheme}://{hostpart}" + (f":{port}" if port and port != PORTS[u.scheme] else "")
    path = (u.path or "").rstrip("/")
    if "/../" in path + "/" or "/./" in path + "/":
        raise ValueError("bad path")
    return base, path


def check_base(url, kind):
    """The address of a connection as typed on the page: only scheme, host and port."""
    base, path = split(url, kind)
    if kind == "webdav" and urlsplit(base).scheme == "http" and not home_name(urlsplit(base).hostname or ""):
        raise ValueError("http:// nur für Adressen im Heimnetz, sonst https://.")
    if kind == "smb" and not home_name(urlsplit(base).hostname or ""):
        raise ValueError("SMB nur im Heimnetz.")
    return base


def zone(conn):
    return "lan" if home_name((urlsplit(conn["url"]).hostname or "").lower()) else "net"


# ---------------------------------------------------------------- stored connections
def _file(owner):
    return os.path.join(STATE, ADMIN_FILE) if owner is ADMIN else profiles._path(owner, "nas.json")


def _clean(c):
    if not isinstance(c, dict) or not ID.fullmatch(str(c.get("id", ""))) or c.get("kind") not in KINDS \
            or not NAME.fullmatch(str(c.get("name", ""))):
        return None
    try:
        base, path = split(str(c.get("url") or ""), c["kind"])
    except ValueError:
        return None
    if path:
        return None
    out = {"id": c["id"], "name": c["name"], "kind": c["kind"], "url": base, "user": str(c.get("user") or "")[:128],
           "password": str(c.get("password") or ""), "added": int(c.get("added") or 0),
           "checked": c.get("checked") if isinstance(c.get("checked"), dict) else None}
    if re.search(r"[\x00-\x1f]", out["user"]):
        return None
    if c["kind"] == "webdav":
        out["cert"] = zertpin.clean(c.get("cert"))
    if c["kind"] == "sftp":
        out["hostkey"] = str(c.get("hostkey") or "") if HOSTKEY.fullmatch(str(c.get("hostkey") or "")) else ""
    return out


def load(owner):
    path = _file(owner)
    try:
        if os.path.islink(path):
            return []
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    items = d.get("nas") if isinstance(d, dict) else None
    return [x for x in map(_clean, items if isinstance(items, list) else []) if x][:HARD]


def save(owner, items):
    with _lock:
        path = _file(owner)
        if owner is ADMIN:
            write_json(path, {"nas": items[:HARD]}, mode=0o600)
        else:
            profiles._write(path, {"nas": items[:HARD]})


def find(owner, nid):
    return next((c for c in load(owner) if c["id"] == nid), None)


def match(owner, kind, url, user):
    """The connection a full address of a use and a user belong to, or None."""
    try:
        base, _ = split(url, kind)
    except ValueError:
        return None
    user = str(user or "")[:128]
    return next((x for x in load(owner) if x["kind"] == kind and x["url"] == base and x["user"] == user), None)


def ensure(owner, kind, url, user, password="", hostkey=None, cert=None, name=None):
    """The connection for this kind, address and user (made when there is none): (id, path). A new password
    (sealed), server key or certificate is written into it; None keeps what is there, "" clears it."""
    base, path = split(url, kind)
    user = str(user or "")[:128]
    with _lock:
        items = load(owner)
        c = next((x for x in items if x["kind"] == kind and x["url"] == base and x["user"] == user), None)
        if c is None:
            host = (urlsplit(base).hostname or "NAS")[:30]
            nm = name if name and NAME.fullmatch(name) else re.sub(r"[^A-Za-zÄÖÜäöüß0-9 ._\-]", "", f"NAS {host}")[:40] or "NAS"
            c = {"id": _new_id(items), "name": nm, "kind": kind, "url": base, "user": user, "password": "",
                 "added": int(time.time()), "checked": None}
            if kind == "webdav":
                c["cert"] = ""
            if kind == "sftp":
                c["hostkey"] = ""
            items.append(c)
        if password:
            c["password"] = password
        if hostkey is not None and kind == "sftp":
            c["hostkey"] = hostkey if HOSTKEY.fullmatch(hostkey or "") else ""
        if cert is not None and kind == "webdav":
            c["cert"] = zertpin.clean(cert)
        save(owner, items)
        return c["id"], path


def _new_id(items):
    while True:
        nid = secrets.token_hex(3)
        if all(x["id"] != nid for x in items):
            return nid


def expand(owner, t, keep_cert=True):
    """A stored use {"nas", "path", ...} with the connection's full address and login filled in; the use as it is
    when it names no connection; None when its connection is gone."""
    if not isinstance(t, dict) or "nas" not in t:
        return t
    c = find(owner, str(t.get("nas") or ""))
    path = str(t.get("path") or "")
    if not c or (path and (not path.startswith("/") or "/../" in path + "/" or re.search(r"[\x00-\x1f\\]", path))):
        return None
    out = {k: v for k, v in t.items() if k not in ("nas", "path")}
    out.update(url=c["url"] + path + ("/" if c["kind"] == "webdav" else ""), user=c["user"], password=c["password"],
               nas=c["id"])
    if c["kind"] == "webdav" and keep_cert:
        out["cert"] = c.get("cert", "")
    if c["kind"] == "sftp":
        out["hostkey"] = c.get("hostkey", "")
    return out


def collapse(owner, t, kind, fields=("url", "user", "password", "hostkey", "cert")):
    """A use as it is saved: address and login go into the connection, the use keeps {"nas", "path"}."""
    nid, path = ensure(owner, kind, t.get("url"), t.get("user"), t.get("password") or "",
                       hostkey=t.get("hostkey") if kind == "sftp" else None,
                       cert=t.get("cert") if kind == "webdav" and "cert" in t else None)
    out = {k: v for k, v in t.items() if k not in fields}
    out.update(nas=nid, path=path)
    return out


def uses(owner):
    """{connection id: {use name: count}} from every module that registered in USES."""
    out = {}
    for name, fn in USES.items():
        try:
            got = fn(owner) or {}
        except Exception:   # noqa: BLE001 - a module that cannot tell blocks nothing here, it is checked again on remove
            continue
        for nid, n in got.items():
            out.setdefault(nid, {})[name] = n
    return out


def _keep(path):
    """The file as it was before the move, next to it as *.vor-nas.json (0600): an older version after a rollback
    finds the login there by hand (docs: Eigener Speicher, "Zurück auf eine ältere Version")."""
    old = path[:-5] + ".vor-nas.json"
    if os.path.islink(path) or os.path.exists(old):
        return
    with open(path, "rb") as f:
        data = f.read()
    with open(os.open(old, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as f:
        f.write(data)


def _switch_carry():
    from common import CONFIG_PATH, write_json
    try:
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
        c = raw.get("chat") if isinstance(raw.get("chat"), dict) else None
        if c is not None and c.get("storage_own") is True and c.get("nas_on") is not True:
            c["nas_on"] = True
            write_json(CONFIG_PATH, raw, indent=2)
            print("nas: umgestellt schalter=1", flush=True)
    except (OSError, ValueError) as e:
        print("nas: umstellung schalter fehlgeschlagen", type(e).__name__, flush=True)


def migrate_all():
    """Once at start: every profile's copy (speicher.py) and the backup to the NAS move onto connections (S1). Saving
    through the modules does it; this only makes sure it happens before anybody opens a page. "Kopie meiner Daten"
    hangs below "Speicher und NAS" since the clean-up: who had only the copy on gets the heading switched on too."""
    _switch_carry()
    n = 0
    try:
        import speicher
        for uid in profiles.user_ids():
            raw = speicher._json(speicher._file(uid))
            if any(isinstance(t, dict) and t.get("kind") in speicher.LOGIN_KINDS and "nas" not in t
                   for t in raw.get("targets") or [] if isinstance(raw.get("targets"), list)):
                _keep(speicher._file(uid))
                d = speicher.load(uid)
                speicher.save(uid, d)
                n += 1
    except Exception as e:   # noqa: BLE001 - the old file keeps working, the next save moves it
        print("nas: umstellung speicher fehlgeschlagen", type(e).__name__, flush=True)
    try:
        import offsite
        raw = offsite._raw()
        if raw.get("url") and "nas" not in raw:
            _keep(offsite.FILE)
            with offsite._lock:
                offsite._write(offsite._read())
            n += 1
    except Exception as e:   # noqa: BLE001
        print("nas: umstellung sicherung fehlgeschlagen", type(e).__name__, flush=True)
    if n:
        print(f"nas: umgestellt nutzungen={n}", flush=True)
    return n


# ---------------------------------------------------------------- checking a connection
def _level():
    return netguard.HOME


async def check(c, path=""):
    """Signs in once and looks at the folder (nothing is written). Returns {"t", "ok": True, "hostkey"?}; NasError."""
    if c["kind"] == "webdav":
        await _check_dav(c, path)
        return {"t": int(time.time()), "ok": True}
    import speicher
    t = {"url": c["url"] + (path or "/x") if c["kind"] == "smb" else c["url"] + (path or ""), "user": c["user"],
         "password": c["password"], "hostkey": c.get("hostkey", "")}
    drv = (speicher.Sftp if c["kind"] == "sftp" else speicher.Smb)(t, b"\0" * 32)
    drv.level = _level()
    try:
        await drv._run(lambda: True, timeout=TIMEOUT)
    except speicher.StoreError as e:
        raise NasError(e.kind if e.kind in WHY else "other", str(e))
    finally:
        await drv.close()
    out = {"t": int(time.time()), "ok": True}
    if c["kind"] == "sftp":
        out["hostkey"] = getattr(drv, "seen", "")
    return out


async def _check_dav(c, path):
    url = c["url"] + (path or "") + "/"
    pw = vault.open_(c["password"]) or "" if c.get("password") else ""
    auth_ = (c["user"], pw) if c.get("user") else None
    try:
        async with netguard.client(_level(), origin=c["url"] + "/", max_bytes=256 * 1024, verify=zertpin.verify(c.get("cert")),
                                   timeout=httpx.Timeout(TIMEOUT, connect=10)) as cl:
            r = await cl.request("PROPFIND", url, auth=auth_, headers={"Depth": "0", "Content-Type": "application/xml"},
                                 content=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
    except netguard.Blocked as e:
        raise NasError("notaus" if "Notaus" in str(e) else "blocked", str(e)[:200])
    except (httpx.ConnectError, httpx.TimeoutException, OSError, ssl.SSLError) as e:
        raise NasError("cert" if zertpin.problem(e) else "offline", type(e).__name__)
    except (httpx.HTTPError, netguard.TooLarge, ValueError) as e:
        raise NasError("cert" if zertpin.problem(e) else "other", type(e).__name__)
    if r.status_code in (401, 403):
        raise NasError("auth", f"HTTP {r.status_code}")
    if r.status_code != 207:
        raise NasError("offline" if r.status_code in (502, 503, 504) else "other", f"HTTP {r.status_code}")


def say(kind):
    return {"offline": "Die NAS antwortet nicht (Adresse, Netz oder NAS aus?).",
            "auth": "Die NAS lehnt die Anmeldung ab (Benutzer, Passwort oder Rechte prüfen).",
            "cert": "Das Zertifikat der NAS passt nicht zur Adresse oder ist selbst ausgestellt. Fingerabdruck "
                    "vergleichen und unter Ich → Speicher beim Ort „Verbindung prüfen“ annehmen.",
            "hostkey": "Der Schlüssel des Servers ist ein anderer als beim Einrichten. Nur wenn du weißt, warum "
                       "(NAS neu eingerichtet), unter Ich → Speicher beim Ort „Anmeldung ändern“ den neuen Schlüssel annehmen.",
            "blocked": "Der Wächter erlaubt diese Adresse nicht.", "notaus": "Notaus ist an: keine Verbindung nach außen.",
            "other": "Die NAS antwortet nicht wie erwartet (Adresse, Freigabe oder Art prüfen)."}.get(kind, "Fehler")


# ---------------------------------------------------------------- views
def public(owner, c, used=None):
    """A connection for the page: never the password, the certificate only as its fingerprint."""
    out = {"id": c["id"], "name": c["name"], "kind": c["kind"], "url": c["url"], "user": c["user"],
           "has_password": bool(c["password"]), "zone": zone(c), "added": c["added"], "checked": c["checked"],
           "uses": (used if used is not None else uses(owner)).get(c["id"], {})}
    if c["kind"] == "webdav":
        out["cert"] = zertpin.sha_of(c.get("cert"))
    if c["kind"] == "sftp":
        out["hostkey"] = c.get("hostkey", "")
    return out


def _view(uid):
    used = uses(uid)
    return {"admin": admin_on(), "on": features.allowed("nas", uid), "why": features.reason("nas", uid), "max": MAX,
            "items": [public(uid, c, used) for c in load(uid)]}


def overview():
    """Zustand (admin): per profile only how many connections, which kinds and zones and their state; the
    Spark's own connections with their uses. Never a password, never a file name."""
    rows = []
    names = {p["id"]: p["name"] for p in profiles.names()}
    for uid in profiles.user_ids():
        for c in load(uid):
            rows.append({"profile": names.get(uid, "?"), "name": c["name"], "kind": c["kind"], "zone": zone(c),
                         "checked": c["checked"], "uses": uses(uid).get(c["id"], {})})
    used = uses(ADMIN)
    return {"on": admin_on(), "rows": rows, "spark": [public(ADMIN, c, used) for c in load(ADMIN)]}


def summary(uid):
    items = load(uid)
    return len(items), sum(1 for c in items if (c["checked"] or {}).get("ok") is False)


def for_live():
    """Zustand → Live (live.py "nas"): only numbers, never an address, a user or a name."""
    if not admin_on():
        return {"on": False}
    conns = bad = profs = 0
    for uid in profiles.user_ids():
        items = load(uid)
        profs += bool(items)
        conns += len(items)
        bad += sum(1 for c in items if (c["checked"] or {}).get("ok") is False)
    spark = load(ADMIN)
    return {"on": True, "conns": conns + len(spark), "profiles": profs, "bad": bad, "backup": bool(spark)}


def _log_name(uid):
    return profiles.log_name(profiles.by_id(uid))


# ---------------------------------------------------------------- routes (profile)
def _on(prof=Depends(browser_profile)):
    """Only the profile's own browser login, never a device key."""
    if not admin_on():
        raise HTTPException(403, "NAS connections are turned off")
    if not features.allowed("nas", prof["id"]):
        raise HTTPException(403, "NAS connections are not allowed for this profile")
    return prof


def _name(v):
    v = str(v or "").strip()
    if not NAME.fullmatch(v):
        raise HTTPException(400, "Name: bis 40 Buchstaben, Ziffern, Leerzeichen, . _ -")
    return v


def _user(v):
    v = str(v or "")
    if len(v) > 128 or re.search(r"[\x00-\x1f]", v):
        raise HTTPException(400, "invalid user name")
    return v


async def _cert_for(c, want):
    """The fingerprint the person compared: accepted only if the NAS shows exactly it now."""
    if not isinstance(want, str) or len(want) > 200:
        raise HTTPException(400, "cert: a fingerprint")
    if not want:
        return ""
    if urlsplit(c["url"]).scheme != "https":
        raise HTTPException(400, "Nur https-Adressen haben ein Zertifikat.")
    try:
        got = await zertpin.fetch(c["url"] + "/", _level())
    except netguard.Blocked:
        raise HTTPException(403, say("blocked"))
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(502, say("offline"))
    if got["sha256"] != want.strip().upper():
        raise HTTPException(409, "Die NAS zeigt jetzt ein anderes Zertifikat als eben. Noch einmal prüfen.")
    return got["pem"]


async def _show_cert(base):
    try:
        got = await zertpin.fetch(base + "/", _level())
    except netguard.Blocked:
        raise HTTPException(403, say("blocked"))
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(502, say("offline"))
    return {k: got[k] for k in ("sha256", "names", "until", "self_signed", "fits", "expired")}


async def _checked(c, request=None):
    """Checks the connection; a refused certificate answers 409 with what the NAS shows, so the page can ask."""
    try:
        return await check(c)
    except NasError as e:
        if e.kind == "cert":
            raise HTTPException(409, {"cert": await _show_cert(c["url"]), "message": say("cert")})
        raise HTTPException(502, say(e.kind))


@router.get("/api/profile/nas")
def get_mine(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "storage", prof["id"])
    if not admin_on():
        raise HTTPException(403, "NAS connections are turned off")
    return _view(prof["id"])


@router.post("/api/profile/nas")
async def add(request: Request, prof=Depends(_on)):
    """{"name", "kind", "url", "user", "password", "cert"?}: a new connection, checked by signing in."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    body = await core.json_body(request, 8192, lenient=True)
    kind = body.get("kind")
    if kind not in KINDS:
        raise HTTPException(400, "kind: webdav, smb or sftp")
    try:
        base = check_base(body.get("url"), kind)
    except ValueError as e:
        raise HTTPException(400, str(e) if " " in str(e) else "Die Adresse ist ungültig.")
    user, pw = _user(body.get("user")), body.get("password")
    if not isinstance(pw, str) or not pw or len(pw) > 256:
        raise HTTPException(400, "Bitte das Passwort eingeben.")
    if any(x["kind"] == kind and x["url"] == base and x["user"] == user for x in load(uid)):
        raise HTTPException(409, "Diese NAS mit diesem Benutzer ist schon eingerichtet.")
    if len(load(uid)) >= MAX:
        raise HTTPException(400, f"Höchstens {MAX} NAS-Verbindungen.")
    c = {"id": "000000", "name": _name(body.get("name")), "kind": kind, "url": base, "user": user,
         "password": vault.seal(pw), "added": int(time.time()), "checked": None, "cert": "", "hostkey": ""}
    await secret_profile(request)     # a new place the profile's login goes to: a code (stufen.py)
    if kind == "webdav" and body.get("cert"):
        c["cert"] = await _cert_for(c, body["cert"])
    got = await _checked(c)
    with _lock:
        items = load(uid)
        if len(items) >= MAX:
            raise HTTPException(400, f"Höchstens {MAX} NAS-Verbindungen.")
        c["id"] = _new_id(items)
        c["checked"] = {"t": got["t"], "ok": True}
        if kind == "sftp":
            c["hostkey"] = got.get("hostkey", "")
        items.append(_clean(c))
        save(uid, items)
    guard.log("nas_add", detail=f"{kind} {zone(c)}")
    print(f"nas: verbunden art={kind} zone={zone(c)} prof={_log_name(uid)}", flush=True)
    return dict(_view(uid), added=c["id"])


@router.post("/api/profile/nas/cert")
async def cert_of(request: Request, prof=Depends(_on)):
    """{"url"} or {"id"}: the certificate the NAS shows (fingerprint, names, until, fits), to compare. Reads only."""
    guard.limit(request, "storage", prof["id"])
    body = await core.json_body(request, 1024, lenient=True)
    if body.get("id"):
        c = find(prof["id"], str(body["id"]))
        if not c:
            raise HTTPException(404, "no such connection")
        base = c["url"]
    else:
        try:
            base = check_base(body.get("url"), "webdav")
        except ValueError:
            raise HTTPException(400, "Die Adresse ist ungültig.")
    if urlsplit(base).scheme != "https":
        raise HTTPException(400, "Nur https-Adressen haben ein Zertifikat.")
    out = await _show_cert(base)
    c = find(prof["id"], str(body.get("id") or ""))
    return dict(out, pinned=bool(c) and zertpin.sha_of(c.get("cert")) == out["sha256"])


@router.put("/api/profile/nas/{nid}")
async def change(nid: str, request: Request, prof=Depends(_on)):
    """{"name"}; a new "user", "password", "cert" (fingerprint) or "accept_key" needs a code and is checked first."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    old = find(uid, nid)
    if not old:
        raise HTTPException(404, "no such connection")
    body = await core.json_body(request, 8192, lenient=True)
    c = dict(old)
    if "name" in body:
        c["name"] = _name(body["name"])
    if "url" in body and str(body["url"]).strip().rstrip("/") != old["url"]:
        raise HTTPException(400, "Eine andere Adresse ist eine neue NAS-Verbindung.")
    if "user" in body:
        c["user"] = _user(body["user"])
    pw = body.get("password")
    login = c["user"] != old["user"] or bool(pw) or "cert" in body or body.get("accept_key") is True
    if c["user"] != old["user"] and not pw:
        raise HTTPException(400, "Ein anderer Benutzer braucht das Passwort noch einmal.")
    if isinstance(pw, str) and pw:
        if len(pw) > 256:
            raise HTTPException(400, "password too long")
        c["password"] = vault.seal(pw)
    if login:
        await secret_profile(request)
        if "cert" in body and c["kind"] == "webdav":
            c["cert"] = await _cert_for(c, body["cert"])
        if body.get("accept_key") is True and c["kind"] == "sftp":
            c["hostkey"] = ""
        got = await _checked(c)
        c["checked"] = {"t": got["t"], "ok": True}
        if c["kind"] == "sftp" and not c.get("hostkey"):
            c["hostkey"] = got.get("hostkey", "")
    with _lock:
        items = [c if x["id"] == nid else x for x in load(uid)]
        save(uid, items)
    if login:
        what = "Zertifikat" if "cert" in body else "Schlüssel" if body.get("accept_key") else "Zugang"
        guard.log("nas_change", detail=f"{c['kind']} {what}")
        print(f"nas: geaendert art={c['kind']} was={'cert' if 'cert' in body else 'key' if body.get('accept_key') else 'login'} prof={_log_name(uid)}", flush=True)
    return _view(uid)


@router.delete("/api/profile/nas/{nid}")
def remove(nid: str, request: Request, prof=Depends(browser_profile)):
    """Removes a connection that nothing uses any more (its password goes with it)."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    c = find(uid, nid)
    if not c:
        raise HTTPException(404, "no such connection")
    used = uses(uid).get(nid)
    if used:
        what = " und ".join(f"„{USE_NAMES.get(k, k)}“" for k in sorted(used))
        raise HTTPException(409, f"Dieser Ort ist noch für {what} an. Erst dort ausschalten.")
    with _lock:
        save(uid, [x for x in load(uid) if x["id"] != nid])
    guard.log("nas_remove", detail=c["kind"])
    print(f"nas: entfernt art={c['kind']} prof={_log_name(uid)}", flush=True)
    return _view(uid)


@router.post("/api/profile/nas/{nid}/check")
async def check_route(nid: str, request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    uid = prof["id"]
    c = find(uid, nid)
    if not c:
        raise HTTPException(404, "no such connection")
    try:
        got = await check(c)
        state = {"t": got["t"], "ok": True}
        if c["kind"] == "sftp" and c.get("hostkey") and got.get("hostkey") and got["hostkey"] != c["hostkey"]:
            state, got = {"t": got["t"], "ok": False, "kind": "hostkey"}, None
    except NasError as e:
        state, got = {"t": int(time.time()), "ok": False, "kind": e.kind}, None
    with _lock:
        items = load(uid)
        for x in items:
            if x["id"] == nid:
                x["checked"] = state
        save(uid, items)
    print(f"nas: geprueft art={c['kind']} {'ok' if state['ok'] else 'fehler ' + state['kind']} prof={_log_name(uid)}", flush=True)
    if not state["ok"]:
        if state["kind"] == "cert":
            raise HTTPException(409, {"cert": await _show_cert(c["url"]), "message": say("cert")})
        raise HTTPException(502, say(state["kind"]))
    return _view(uid)


# ---------------------------------------------------------------- routes (admin)
@router.get("/api/admin/nas", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "storage", admin=True)
    return overview()
