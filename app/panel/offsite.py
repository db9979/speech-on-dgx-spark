"""Sicherung nach außen (plan „Bedienung gesamt“ D4, V01.0.286): once a day an encrypted copy of the backup goes to
a WebDAV folder (NAS, Nextcloud, Synology), off unless the main admin switches it on.

The copy is a move backup (backup.create with the backup password: it carries the vault key, sealed with that
password) and is encrypted as a whole with the same password before it leaves the Spark (scrypt, AES-256-GCM in
1 MiB pieces, each numbered and the last one marked, so nothing can be cut off, swapped or changed unnoticed). The
NAS only ever sees noise. Restoring: download the file there and upload it under Einstellungen → Sicherung with the
backup password; it then works on a new Spark without entering anything again. Without that password the copy is
lost for good, so the panel says to write it down.

Only https, through netguard (HOME: the NAS may live in the home network), with the login only for that site.
WebDAV password and backup password sit sealed in the vault (state/offsite.json), never in a log; a new address
needs the WebDAV password again. Only the copies this Spark uploaded are ever deleted there (the newest KEEP stay).
A NAS whose certificate does not fit its address (self-made, or made for a name while the address is an IP) is
never sent to with the check switched off: the admin compares its fingerprint and accepts exactly that certificate
(zertpin.py, "cert"); a new address forgets it.

    STATE/offsite.json  {"on", "nas" (the Spark's NAS connection, nas.py), "path", "key" (sealed),
                         "last": {...}, "sent": [names]}
                        (before V01.0.4xx "url", "user", "password" (sealed) and "cert" stood here; such a file is
                        read as before and moved onto a NAS connection the next time it is written)

Address, user, password and the accepted certificate live in the Spark's NAS connection (nas.py, plan
synology-bauplan.md S1): _read() gives them back in the old shape, _write() puts them there, so everything below
works as before.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import struct
import threading
import time
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request

import backup
import guard
import netguard
import vault
import vorrang
import nas
import zertpin
from common import write_json
from core import spawn, admin_code, admin_code_fresh, auth

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "offsite.json")
KEEP = 7
DAILY = 86400
RETRY = 6 * 3600          # after a failed upload the next try waits six hours
MAGIC = b"SPARKENC1\n"
CHUNK = 1 << 20
MAX_HEADER = 512
_lock = threading.Lock()
_running = {"on": False}


# ---------------------------------------------------------------- encryption
def _key(password, salt, n, r, p):
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024**2, dklen=32)


def encrypt(src, dst, password):
    """Encrypts the open file src into dst (both binary)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, prefix = os.urandom(16), os.urandom(4)
    head = {"kdf": "scrypt", **backup.SCRYPT, "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(prefix).decode(), "chunk": CHUNK}
    dst.write(MAGIC + json.dumps(head).encode() + b"\n")
    aes = AESGCM(_key(password, salt, **backup.SCRYPT))
    i, block = 0, src.read(CHUNK)
    while True:
        nxt = src.read(CHUNK)
        last = not nxt
        ct = aes.encrypt(prefix + struct.pack(">Q", i), block, struct.pack(">Q?", i, last))
        dst.write(struct.pack(">I", len(ct)) + ct)
        if last:
            return
        i, block = i + 1, nxt


def encrypted(f):
    """Is the open file an encrypted copy? (reads the start, then goes back)"""
    pos = f.tell()
    start = f.read(len(MAGIC))
    f.seek(pos)
    return start == MAGIC


def decrypt(src, dst, password, most=backup.MAX_UPLOAD):
    """Decrypts src into dst; ValueError for a wrong password, a changed or cut file, or more than most bytes."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if src.read(len(MAGIC)) != MAGIC:
        raise ValueError("not an encrypted backup")
    line = src.readline(MAX_HEADER)
    try:
        h = json.loads(line)
        salt, prefix = base64.b64decode(h["salt"], validate=True), base64.b64decode(h["nonce"], validate=True)
        n, r, p = int(h["n"]), int(h["r"]), int(h["p"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("the encrypted backup is damaged")
    # only the cost this panel writes (a file must not make the Spark compute for minutes)
    if h.get("kdf") != "scrypt" or (n, r, p) != (backup.SCRYPT["n"], backup.SCRYPT["r"], backup.SCRYPT["p"]) \
            or len(salt) != 16 or len(prefix) != 4 or h.get("chunk") != CHUNK:
        raise ValueError("the encrypted backup is damaged")
    aes = AESGCM(_key(password, salt, n, r, p))
    i, total = 0, 0
    size = src.read(4)
    while True:
        if len(size) != 4:
            raise ValueError("the encrypted backup is cut off")
        (ln,) = struct.unpack(">I", size)
        if ln > CHUNK + 16:
            raise ValueError("the encrypted backup is damaged")
        ct = src.read(ln)
        size = src.read(4)
        last = not size
        try:
            block = aes.decrypt(prefix + struct.pack(">Q", i), ct, struct.pack(">Q?", i, last))
        except InvalidTag:
            raise ValueError("wrong password for this backup, or the file was changed" if i == 0
                             else "the encrypted backup was changed or cut off")
        total += len(block)
        if total > most:
            raise ValueError("backup too large")
        dst.write(block)
        if last:
            return
        i += 1


# ---------------------------------------------------------------- settings
def _raw():
    try:
        with open(FILE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def _read():
    """The settings with address, user, password and certificate from the Spark's NAS connection."""
    d = _raw()
    if "nas" not in d:
        return d
    out = {k: v for k, v in d.items() if k not in ("nas", "path")}
    e = nas.expand(nas.ADMIN, {"nas": d.get("nas"), "path": d.get("path", "")})
    if e and e.get("url"):
        out.update(url=e["url"], user=e["user"], password=e["password"], cert=e.get("cert", ""))
        if not out["cert"]:
            out.pop("cert")
    return out


def _write(d):
    """Address and login go into the Spark's NAS connection (nas.py); this file keeps {"nas", "path"}."""
    d = dict(d)
    if d.get("url"):
        t = {"url": d["url"], "user": d.get("user", ""), "password": d.get("password", ""), "cert": d.get("cert") or ""}
        d = {k: v for k, v in d.items() if k not in ("url", "user", "password", "cert")}
        d.update({k: v for k, v in nas.collapse(nas.ADMIN, t, "webdav").items() if k in ("nas", "path")})
    else:
        d = {k: v for k, v in d.items() if k not in ("nas", "path")}
    write_json(FILE, d, mode=0o600)


def _nas_uses(owner):
    """For nas.py: the backup uses the Spark's connection it names."""
    if owner is not nas.ADMIN:
        return {}
    nid = _raw().get("nas")
    return {nid: 1} if nid else {}


nas.USES["sicherung"] = _nas_uses


def _update(**kw):
    with _lock:
        d = _read()
        d.update(kw)
        _write(d)
        return d


def view():
    d = _read()
    return {"on": d.get("on") is True, "url": d.get("url", ""), "user": d.get("user", ""),
            "has_password": bool(d.get("password")), "has_key": bool(d.get("key")),
            "last": d.get("last"), "running": _running["on"], "kept": len(d.get("sent") or []),
            "cert": zertpin.sha_of(d.get("cert"))}


CERT_SAY = ("Das Zertifikat des NAS passt nicht zur Adresse oder ist selbst ausgestellt. Unter Einstellungen → "
            "Sicherung → „Zertifikat prüfen“ den Fingerabdruck vergleichen und annehmen, oder die Adresse mit dem "
            "Namen aus dem Zertifikat eintragen.")


def check_url(url):
    u = urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment or len(url) > 300:
        raise ValueError("the address must start with https:// and hold no login, ? or #")
    return url.rstrip("/") + "/"


def due(now=None):
    d = _read()
    if d.get("on") is not True or not d.get("url") or not d.get("key"):
        return False
    last = d.get("last") or {}
    now = time.time() if now is None else now
    return now - int(last.get("t") or 0) > (DAILY if last.get("ok") else RETRY)


# ---------------------------------------------------------------- upload
async def run(reason="daily"):
    """Makes the backup, encrypts it and sends it; returns the "last" entry."""
    if _running["on"]:
        return _read().get("last")
    d = _read()
    key, url = vault.open_(d.get("key") or ""), d.get("url") or ""
    if not key or not url:
        raise ValueError("address or backup password missing")
    _running["on"] = True
    t0 = time.time()
    item, enc = None, None
    try:
        item = await vorrang.in_thread("Sicherung nach außen", backup.create, "offsite", key)
        src = backup.path_of(item["name"])
        enc = src + ".enc.part"

        def pack():
            with open(src, "rb") as a, open(os.open(enc, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as b:
                encrypt(a, b, key)
        await vorrang.in_thread("Sicherung verschlüsseln", pack)
        name = item["name"] + ".enc"
        size = os.path.getsize(enc)
        auth = (d.get("user") or "", vault.open_(d.get("password") or "")) if d.get("user") else None

        async def body():
            with open(enc, "rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk
        async with netguard.client(netguard.HOME, origin=url, timeout=600, verify=zertpin.verify(d.get("cert"))) as c:
            r = await c.put(url + quote(name), content=body(), auth=auth,
                            headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)})
            if r.status_code not in (200, 201, 204):
                raise ValueError(f"HTTP {r.status_code} from the WebDAV folder")
            sent = [x for x in (_read().get("sent") or []) if isinstance(x, str)] + [name]
            for old in sent[:-KEEP]:   # only copies this Spark sent
                try:
                    await c.delete(url + quote(old), auth=auth)
                except Exception:   # noqa: BLE001 - an old copy that stays is no error
                    pass
        last = {"t": int(time.time()), "ok": True, "name": name, "bytes": size, "seconds": round(time.time() - t0),
                "why": reason}
        _update(last=last, sent=sent[-KEEP:])
        guard.log("offsite_backup", detail=f"{name} {size // 1048576} MB")
        import live
        live.job("Sicherung nach außen", "NAS-Sicherung", t0)
        print("offsite:", name, size // 1048576, "MB sent", flush=True)
        return last
    except Exception as e:   # noqa: BLE001 - every failure is shown on the page and in the log
        cert = zertpin.problem(e)
        msg = CERT_SAY if cert else f"{type(e).__name__}: {e}"[:200]
        last = {"t": int(time.time()), "ok": False, "error": msg, "why": reason, **({"kind": cert} if cert else {})}
        _update(last=last)
        guard.log("offsite_failed", detail="Zertifikat passt nicht" if cert else msg)
        import live
        http = re.match(r"HTTP (\d{3}) ", str(e))
        live.job("Sicherung nach außen", "NAS-Sicherung", t0, ok=False,
                 code="zertifikat" if cert else f"http_{http.group(1)}" if http else type(e).__name__.lower()[:30])
        print("offsite: failed -", "certificate refused" if cert else msg, flush=True)
        return last
    finally:
        _running["on"] = False
        for p in ([enc] if enc else []) + ([backup.path_of(item["name"])] if item and _exists(item["name"]) else []):
            try:
                os.remove(p)   # the local copy: the daily backups stay as they are
            except OSError:
                pass


def _exists(name):
    try:
        backup.path_of(name)
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------- endpoints (main admin only)
@router.get("/api/admin/offsite", dependencies=[Depends(auth)])
def offsite_get():
    return view()


# the address and password decide where a backup with every secret goes: a fresh code every time,
# like downloading a backup (core.admin_code_fresh)
@router.put("/api/admin/offsite", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def offsite_put(request: Request):
    guard.limit(request, "offsite", admin=True)
    raw = await request.body()
    if len(raw) > 2048:
        raise HTTPException(413, "too large")
    try:
        b = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    if not isinstance(b, dict):
        raise HTTPException(400, "invalid JSON")
    d = _read()
    url = d.get("url", "")
    if "url" in b:
        try:
            url = check_url(str(b["url"]).strip()) if str(b["url"]).strip() else ""
        except ValueError as e:
            raise HTTPException(400, str(e))
    user = str(b.get("user", d.get("user", "")))[:128]
    if re.search(r"[\x00-\x1f]", user):
        raise HTTPException(400, "invalid user name")
    pw, key = b.get("password"), b.get("key")
    new = dict(d, url=url, user=user)
    if url != d.get("url", "") and d.get("password") and not pw:
        new["password"] = ""      # a new address gets the WebDAV password typed again
    if url != d.get("url", ""):
        new.pop("cert", None)     # and its certificate is checked anew
    if "cert" in b:               # the fingerprint the admin compared: accepted only if the NAS shows it now
        want = b["cert"]
        if not isinstance(want, str) or len(want) > 200:
            raise HTTPException(400, "cert: a fingerprint")
        if not want:
            new.pop("cert", None)
        else:
            if not url:
                raise HTTPException(400, "address first")
            try:
                got = await zertpin.fetch(url, netguard.HOME)
            except (OSError, ValueError, asyncio.TimeoutError, netguard.Blocked):
                raise HTTPException(502, "Der NAS antwortet nicht.")
            if got["sha256"] != want.strip().upper():
                raise HTTPException(409, "Der NAS zeigt jetzt ein anderes Zertifikat als eben. Noch einmal prüfen.")
            new["cert"] = got["pem"]
    if isinstance(pw, str) and pw:
        if len(pw) > 256:
            raise HTTPException(400, "password too long")
        new["password"] = vault.seal(pw)
    if isinstance(key, str) and key:
        try:
            backup.check_password(key)
        except ValueError as e:
            raise HTTPException(400, str(e))
        new["key"] = vault.seal(key)
    if "on" in b:
        if not isinstance(b["on"], bool):
            raise HTTPException(400, "on: true or false")
        new["on"] = b["on"]
    if new.get("on") and not (new.get("url") and new.get("key")):
        raise HTTPException(400, "address and backup password first")
    with _lock:
        _write(new)
    guard.log("offsite_settings", detail=f"{'on' if new.get('on') else 'off'} {urlsplit(url).hostname or '-'}"
              + (" Zertifikat angenommen" if new.get("cert") and new.get("cert") != d.get("cert") else ""))
    return view()


@router.post("/api/admin/offsite/cert", dependencies=[Depends(auth)])
async def offsite_cert(request: Request):
    """{"url"?}: the certificate the NAS shows (fingerprint, names, until, fits the address), to compare. Reads only;
    accepting it is PUT {"cert": fingerprint} with a fresh code."""
    guard.limit(request, "offsite", admin=True)
    raw = await request.body()
    if len(raw) > 1024:
        raise HTTPException(413, "too large")
    try:
        b = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    url = (b.get("url") if isinstance(b, dict) else None) or _read().get("url", "")
    try:
        url = check_url(str(url).strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        got = await zertpin.fetch(url, netguard.HOME)
    except netguard.Blocked:
        raise HTTPException(403, "Der Wächter erlaubt diese Adresse nicht.")
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(502, "Der NAS antwortet nicht.")
    pinned = zertpin.sha_of(_read().get("cert"))
    return {k: got[k] for k in ("sha256", "names", "until", "self_signed", "fits", "expired")} | {"pinned": pinned == got["sha256"]}


@router.post("/api/admin/offsite/now", dependencies=[Depends(auth), Depends(admin_code)])
async def offsite_now(request: Request):
    guard.limit(request, "offsite", admin=True)
    if _running["on"]:
        raise HTTPException(409, "already running")
    d = _read()
    if not d.get("url") or not d.get("key"):
        raise HTTPException(400, "address and backup password first")
    spawn(run("manual"))
    await asyncio.sleep(0.05)
    return view()
