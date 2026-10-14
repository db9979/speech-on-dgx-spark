"""Eigener Speicher (plan plaene/eigener-speicher.md, Dominik 2026-10-12 "umsetzen": 1, 2, 5a, 5b, 6-10).

A profile keeps a copy of its data on its own storage: a NAS in the home network or a WebDAV service
(Synology, QNAP, Nextcloud, ownCloud, Fritzbox, HiDrive, MagentaCLOUD, ...), or a folder on the Spark the
admin mounted there himself (NFS, SMB, a USB disk). Ich → Speicher.

The Spark always works locally first. The storage is a target a background run copies to; the Spark never
mounts anything itself (a hanging NFS or SMB mount would freeze the panel and the answers). When the storage is
gone, nothing on the Spark changes: the run tries again later and the profile hears once what is wrong.

What goes there (Kopie, point 5a): the areas the profile picks, each file as an object of its own, only what
changed since the last run. What never goes there: keys, logins, the second sign-in step, passwords of other
services, settings, voice prints (point 7): the list of areas is a fixed allowlist, nothing else is read.

Encryption (point 6): every object is AES-256-GCM in 1 MiB pieces (numbered, the last one marked, so nothing can
be cut, swapped or changed unnoticed) with a key of its own derived from the profile's storage key (HKDF over a
random salt and the object's name: an object moved to another name does not open). Names on the storage are
random; the list of what is where (the manifest) is an object like the others. The storage only ever sees noise.
The profile's storage key is sealed with the Spark's vault key in the profile folder: a move backup (which
carries the vault key) brings it along; without it the copy cannot be read any more.

Connections (point 2): WebDAV over https through netguard (USER: public addresses; addresses in the home network
only with the admin's "Speicher im Heimnetz", then HOME), the password only to that site, http only for an
address in the home network. SFTP (sftp://host/path, user and password; the server's SSH key is learned when
the target is added and must not change) and SMB3 (smb://host/share/folder, only in the home network, only with
SMB encryption): the address checked by netguard once and the connection made to exactly that address, one
connection per run, every call in a thread with a time limit. "Ordner auf dem Spark": only below the folder the admin named (chat.storage_root,
under /mnt, /media or /srv, no symlinks), every file call in its own thread with a time limit.

Rules (fixed): at most MAX_TARGETS targets per profile; adding one or changing its address or password only in
the profile's browser login with a code (stufen.py); a deleted file stays in the storage's bin for TRASH_DAYS
before it is removed there; only objects this Spark wrote are ever deleted; "Fehlendes zurückholen" writes
only files that are missing on the Spark, only into the areas of the list, each checked against its SHA-256.

Monitoring and logging (point 9): Zustand → Speicher (admin: per profile and target only kind, state, sizes,
counts, never file names or contents), Ich → Speicher (the profile's own targets and its last 7 days), the
Dienst-Wächter looks at each WebDAV target (dienstwacht.py "store"), the owner gets one note when a target fails
for an hour (offline, full, sign-in refused) and one when it is back, Zustand → Live shows each run as a job of
"Von selbst" to the target "Eigener Speicher" and events under "Speicher", Logs → Diagnose has the area
"Speicher" (lines "speicher: ..."), the admin log the changes (storage_add, storage_change, storage_remove).

    USERS_DIR/<uid>/speicher.json        {"key": sealed storage key, "targets": [{"id", "name", "kind" (webdav,
                                         sftp, smb, folder), "url", "user", "password" (sealed), "hostkey"
                                         (sftp), "folder", "areas": [...],
                                         "added"}]}
    USERS_DIR/<uid>/speicher-stand.json  {tid: {"files": {rel: {"o", "size", "sha", "mt"}}, "trash": [{"o", "t"}],
                                         "last", "fail", "noted", "free", "hist"}}
    on the target:  <base>/spark-<16 hex>/manifest.enc and <base>/spark-<16 hex>/o/<24 hex>.enc
"""
import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import stat
import struct
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import nas
import netguard
import profiles
import vault
import zertpin
import core
from core import auth, browser_profile, secret_profile, spawn

router = APIRouter()

MAX_TARGETS = 2
MAX_FILES = 5000               # files of one profile in one copy
MAX_FILE = 300 * 1024 * 1024   # one file (the biggest PDF the admin may allow)
RUN_BYTES = 2 * 1024 ** 3      # one run sends at most this much; the next run goes on
EVERY = 30 * 60                # a target is looked at this often (only changed files go)
RETRY = (10 * 60, 30 * 60, 60 * 60, 2 * 3600)   # after failures in a row
TRASH_DAYS = 30
OFFLOAD_DAYS = 30              # Auslagern (5b): an original unchanged and unused this long may live only on the storage
OFFLOAD_RUN = 1024 ** 3        # at most this much is moved out per run (each object read back and checked first)
OFF_PREFIX = "docs/files/"     # only kept originals of documents are moved out; everything else stays a copy
NOTE_AFTER = 3600              # the owner hears of a failure that lasts this long
NOTE_AGAIN = 24 * 3600         # and of the same kind again only after this long
KEEP_HIST = 7 * 86400
MAX_HIST = 200
TIMEOUT = 60                   # one call to the storage (a file of 300 MB gets more, see _time)
FOLDER_TIMEOUT = 20            # one file call in a folder on the Spark (a hanging mount)
AT_ONCE = 2                    # runs on the whole Spark at once
START_GRACE = 120
CHUNK = 1 << 20
MAGIC = b"SPARKSP1\n"
NAME = re.compile(r"[A-Za-zÄÖÜäöüß0-9 ._\-]{1,40}")
SUB = re.compile(r"[A-Za-z0-9._\-]{1,40}")
TID = re.compile(r"[0-9a-f]{6}")
OBJ = re.compile(r"[0-9a-f]{24}")
FILE_RE = re.compile(r"[A-Za-z0-9._\-]{1,80}")
ROOTS = ("/mnt/", "/media/", "/srv/")
KINDS = ("webdav", "folder", "sftp", "smb")
LOGIN_KINDS = ("webdav", "sftp", "smb")     # an address, a user and a password
HOSTKEY = re.compile(r"[a-z0-9@.\-]{3,40} SHA256:[A-Za-z0-9+/]{43}")
STARTED = time.time()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")

# the areas a profile may copy: id -> (German, English, files or folders "x/" in its profile folder). A fixed
# allowlist: keys, logins, passwords of other services, settings and voice prints are in none of them (point 7)
AREAS = {
    "gespraeche": ("Gespräche", "Conversations", ("convos.json", "toollog.json", "room-history.json")),
    "gedaechtnis": ("Gedächtnis", "Memory", ("memory.json", "learned.json", "zuordnungen.json")),
    "alltag": ("Aufgaben und Erinnerungen", "Tasks and reminders", ("tasks.json", "reminders.json")),
    "dokumente": ("Dokumente (Text, Suche, Originale)", "Documents (text, search, originals)", ("wissen.db", "docs/files/", "suchpruefung.json")),
    "erstellt": ("Erstellte Dokumente", "Created documents", ("erstellt/",)),
    "bilder": ("Gemalte Bilder", "Painted pictures", ("bilder/",)),
}
# every other file a profile has stays on the Spark (docs/de/richtlinien.md, Teil 1 "Eigener Speicher"): keys,
# logins, settings, voiceprint, queues and marks. A new file under users/<uid>/ goes either into AREAS or here,
# with its reason; test_speicher checks every name the code passes to profiles._path.
LOCAL = {
    "settings.json": "Einstellungen", "setup.json": "Einstellungen", "speicher.json": "Einstellungen",
    "speicher-stand.json": "Zustand", "transit.json": "Einstellungen", "weather.json": "Einstellungen",
    "proactive.json": "Einstellungen", "proactive-rules.json": "Einstellungen", "hintergrund.json": "Einstellungen",
    "mail.json": "Login", "nas.json": "Login", "nasquelle.json": "Einstellungen", "nasquelle-stand.json": "Zustand", "nasablage.json": "Einstellungen", "speicher.vor-nas.json": "Login", "mail-tidy.json": "Einstellungen", "mailstil.json": "Einstellungen", "calendar.json": "Login", "homeassistant.json": "Login",
    "telegram.json": "Login", "push.json": "Gerät", "remarkable.json": "Login", "remarkable-lib.json": "Zustand",
    "mcp-dienste.json": "Login", "mcp-actions.json": "Zustand", "agent.json": "Einstellungen",
    "voice.json": "Stimmabdruck", "speaker-code.json": "Schlüssel", "chatkeys.json": "Schlüssel", "contacts.json": "noch nicht angeboten",
    "ha-events.json": "Zustand", "briefing-sent": "Zustand",
    "messages.json": "Einstellungen", "messages": "alte Sprachnachrichten (bis zur Übernahme in die Chats)",
    "agent-pending.json": "Warteschlange", "calendar-pending.json": "Warteschlange", "fix-pending.json": "Warteschlange", "memory-ask.json": "Warteschlange",
    "mail-pending.json": "Warteschlange", "mcp-dienste-pending.json": "Warteschlange",
    "messages-pending.json": "Warteschlange", "tasks-pending.json": "Warteschlange",
    "tagebuch.json": "Zustand",
    "docling-wait": "Warteschlange",
}
# what the owner hears (fixed words, never an address or an error text from outside)
WHY = {"offline": ("nicht erreichbar", "not reachable"), "auth": ("Anmeldung abgelehnt", "sign-in refused"),
       "full": ("voll", "full"), "blocked": ("vom Wächter nicht erlaubt", "not allowed by the Wächter"),
       "key": ("Schlüssel fehlt (nach einem Umzug ohne Umzugs-Sicherung)", "key missing (after a move without a move backup)"),
       "notaus": ("Notaus", "kill switch"), "hostkey": ("Schlüssel des Servers hat sich geändert", "the server's key changed"),
       "cert": ("Zertifikat passt nicht", "certificate does not fit"),
       "other": ("Fehler beim Ablegen", "error while storing")}
_lock = threading.RLock()
_running = {}                  # (uid, tid) -> "copy" / "restore"
_slots = None


class StoreError(Exception):
    def __init__(self, kind, text=""):
        super().__init__(text or kind)
        self.kind = kind if kind in WHY else "other"


# ---------------------------------------------------------------- switches
def admin_on(c=None):
    return features.admin_on("speicher", c)


def allowed(uid):
    return bool(uid) and features.allowed("speicher", uid)


def _chat():
    return features.chat_cfg()


def offload_ok(c=None):
    return features.admin_on("speicherauslagern", c)


def lan_ok(c=None):
    return features.admin_on("speicherlan", c)


def folder_ok(c=None):
    return features.admin_on("speicherordner", c) and bool(root())


def root(c=None):
    """The folder the admin allowed for "Ordner auf dem Spark", checked; "" when there is none."""
    c = _chat() if c is None else c
    r = str(c.get("storage_root") or "").strip()
    return r if check_root(r, quiet=True) else ""


def check_root(r, quiet=False):
    """Absolute, below /mnt, /media or /srv, no "..", no symlink on the way, an existing folder."""
    ok = (isinstance(r, str) and 1 < len(r) <= 200 and r.startswith(ROOTS) and re.fullmatch(r"/[A-Za-z0-9._\-/]+", r)
          and "/../" not in r + "/" and "/./" not in r + "/" and "//" not in r)
    if ok:
        ok = os.path.isdir(r) and os.path.realpath(r) == r.rstrip("/")
    if not ok and not quiet:
        raise ValueError("Der Ordner muss unter /mnt, /media oder /srv liegen, schon da sein und darf kein Verweis sein.")
    return bool(ok)


# ---------------------------------------------------------------- stored targets
def _file(uid):
    return profiles._path(uid, "speicher.json")


def _state_file(uid):
    return profiles._path(uid, "speicher-stand.json")


def _json(path):
    try:
        if os.path.islink(path):
            return {}
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _clean(t):
    """One stored target, checked (a restored backup or a hand-edited file must not bring anything else)."""
    if not isinstance(t, dict) or not TID.fullmatch(str(t.get("id", ""))) or t.get("kind") not in KINDS \
            or not NAME.fullmatch(str(t.get("name", ""))):
        return None
    out = {"id": t["id"], "name": t["name"], "kind": t["kind"], "added": int(t.get("added") or 0), "offload": t.get("offload") is True,
           "areas": [a for a in t.get("areas") or [] if a in AREAS] if isinstance(t.get("areas"), list) else []}
    if t["kind"] in LOGIN_KINDS and nas.ID.fullmatch(str(t.get("nas") or "")):
        out["nas"] = t["nas"]
    if t["kind"] == "webdav":
        out["cert"] = zertpin.clean(t.get("cert"))
    if t["kind"] in LOGIN_KINDS:
        try:
            out["url"] = check_url(str(t.get("url") or ""), t["kind"])
        except ValueError:
            return None
        out["user"] = str(t.get("user") or "")[:128]
        out["password"] = str(t.get("password") or "")
        if t["kind"] == "sftp":
            out["hostkey"] = str(t.get("hostkey") or "") if HOSTKEY.fullmatch(str(t.get("hostkey") or "")) else ""
    else:
        if not SUB.fullmatch(str(t.get("folder") or "")) or str(t["folder"]).startswith("."):
            return None
        out["folder"] = t["folder"]
    return out


def load(uid):
    """The profile's targets; one on a NAS connection (nas.py, S1) comes with its full address and login."""
    d = _json(_file(uid))
    raw = d.get("targets") if isinstance(d.get("targets"), list) else []
    return {"key": str(d.get("key") or ""),
            "targets": [x for x in (_clean(nas.expand(uid, t)) for t in raw) if x][:MAX_TARGETS]}


def save(uid, d):
    """Address and login of a NAS target go into its NAS connection (nas.py); the target keeps {"nas", "path"}."""
    with _lock:
        out = [nas.collapse(uid, t, t["kind"]) if t["kind"] in LOGIN_KINDS else t for t in d["targets"][:MAX_TARGETS]]
        profiles._write(_file(uid), {"key": d["key"], "targets": out})


def _nas_uses(owner):
    """For nas.py: how many targets of this profile use each of its connections."""
    if owner is nas.ADMIN:
        return {}
    out = {}
    for t in targets(owner):
        if t.get("nas"):
            out[t["nas"]] = out.get(t["nas"], 0) + 1
    return out


nas.USES["speicher"] = _nas_uses


def targets(uid):
    return load(uid)["targets"]


def find(uid, tid):
    return next((t for t in targets(uid) if t["id"] == tid), None)


def _key(uid, make=False):
    """The profile's storage key (32 bytes), made the first time; None when it cannot be opened."""
    with _lock:
        d = load(uid)
        if d["key"]:
            try:
                raw = base64.b64decode(vault.open_(d["key"]) or "", validate=True)
            except ValueError:
                raw = b""
            return raw if len(raw) == 32 else None
        if not make:
            return None
        raw = os.urandom(32)
        d["key"] = vault.seal(base64.b64encode(raw).decode())
        save(uid, d)
        return raw


def folder_name(key):
    """The folder of this profile's copy on the target: from its key, so it names nobody."""
    return "spark-" + hashlib.sha256(b"spark-speicher-ordner\0" + key).hexdigest()[:16]


def _states(uid):
    d = _json(_state_file(uid))
    return {k: v for k, v in d.items() if TID.fullmatch(str(k)) and isinstance(v, dict)}


def _state(uid, tid):
    s = _states(uid).get(tid) or {}
    files = s.get("files") if isinstance(s.get("files"), dict) else {}
    return {"files": {k: v for k, v in files.items() if _rel_ok(k) and isinstance(v, dict) and OBJ.fullmatch(str(v.get("o", "")))},
            "trash": [x for x in s.get("trash") or [] if isinstance(x, dict) and OBJ.fullmatch(str(x.get("o", "")))]
            if isinstance(s.get("trash"), list) else [],
            "last": s.get("last") if isinstance(s.get("last"), dict) else None,
            "fail": s.get("fail") if isinstance(s.get("fail"), dict) else None,
            "noted": s.get("noted") if isinstance(s.get("noted"), dict) else {},
            "free": s.get("free") if isinstance(s.get("free"), dict) else None,
            "hist": [x for x in s.get("hist") or [] if isinstance(x, dict)][-MAX_HIST:] if isinstance(s.get("hist"), list) else [],
            "manifest": s.get("manifest") is True,
            "used": {k: int(v) for k, v in (s.get("used") or {}).items() if _rel_ok(k) and isinstance(v, (int, float))}
            if isinstance(s.get("used"), dict) else {}}


def _put_state(uid, tid, st):
    with _lock:
        d = _states(uid)
        if st is None:
            d.pop(tid, None)
        else:
            old = d.get(tid)
            if isinstance(old, dict) and isinstance(old.get("used"), dict):   # stamped by another writer since st was read
                used = st.setdefault("used", {})
                for k, v in old["used"].items():
                    if _rel_ok(k) and isinstance(v, (int, float)) and v > used.get(k, 0):
                        used[k] = int(v)
                for k, x in (st.get("files") or {}).items():
                    if x.get("off") and used.get(k, 0) >= x["off"]:
                        x.pop("off")      # fetched back meanwhile (bring_back)
            d[tid] = st
        known = {t["id"] for t in targets(uid)}
        profiles._write(_state_file(uid), {k: v for k, v in d.items() if k in known or k == tid and st is not None})


# ---------------------------------------------------------------- addresses
def _home_name(host):
    import ipaddress
    try:
        return ipaddress.ip_address(host).is_private      # loopback too: netguard decides whether it may be reached
    except ValueError:
        return host.endswith((".local", ".lan", ".home", ".fritz.box", ".home.arpa", ".internal")) or "." not in host


SCHEMES = {"webdav": ("https", "http"), "sftp": ("sftp",), "smb": ("smb",)}
START = {"webdav": "https://", "sftp": "sftp://", "smb": "smb://"}


def check_url(url, kind="webdav"):
    """WebDAV: https://host[:port]/path/ (http only for an address in the home network). SFTP: sftp://host[:port]/path
    (SSH is encrypted: any address the Wächter allows). SMB: smb://host[:port]/share[/folder] only in the home
    network. Never a login, ? or # in it."""
    url = str(url or "").strip()
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme not in SCHEMES.get(kind, ()) or not host or u.username or u.password or u.query or u.fragment \
            or len(url) > 300 or re.search(r"[\s\x00-\x1f\\]", url) \
            or kind != "webdav" and re.search(r"[%\"<>|*:]", u.path or ""):
        raise ValueError(f"Die Adresse beginnt mit {START.get(kind, 'https://')} und enthält keine Anmeldung, kein ? und kein #.")
    try:
        u.port
    except ValueError:
        raise ValueError("Die Adresse hat einen ungültigen Port.")
    if u.scheme == "http" and not _home_name(host):
        raise ValueError("http:// nur für Adressen im Heimnetz, sonst https://.")
    if kind == "smb" and not _home_name(host):
        raise ValueError("SMB nur im Heimnetz; über das Internet SFTP oder WebDAV mit https://.")
    if kind == "smb" and not [x for x in (u.path or "").split("/") if x]:
        raise ValueError("Nach der Adresse kommt die Freigabe: smb://nas/freigabe/ordner.")
    if "/../" in (u.path or "/") + "/" or "/./" in (u.path or "/") + "/":
        raise ValueError("Die Adresse enthält „..“.")
    return url.rstrip("/") + "/" if kind == "webdav" else url.rstrip("/")


# ---------------------------------------------------------------- encryption
def _subkey(key, salt, name):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"spark-speicher\0" + name.encode()).derive(key)


def seal_file(src, dst, key, name):
    """Encrypts the open binary file src into dst; returns (plain bytes, SHA-256 of the plain text)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, prefix = os.urandom(16), os.urandom(4)
    dst.write(MAGIC + salt + prefix)
    aes, h, n = AESGCM(_subkey(key, salt, name)), hashlib.sha256(), 0
    i, block = 0, src.read(CHUNK)
    while True:
        nxt = src.read(CHUNK)
        last = not nxt
        h.update(block)
        n += len(block)
        ct = aes.encrypt(prefix + struct.pack(">Q", i), block, struct.pack(">Q?", i, last))
        dst.write(struct.pack(">I", len(ct)) + ct)
        if last:
            return n, h.hexdigest()
        i, block = i + 1, nxt


def open_file(src, dst, key, name, most=MAX_FILE):
    """Decrypts src into dst; returns the SHA-256 of the plain text. ValueError for another key or name, a
    changed or cut object, or more than most bytes."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    head = src.read(len(MAGIC) + 20)
    if len(head) != len(MAGIC) + 20 or not head.startswith(MAGIC):
        raise ValueError("not an object of the own storage")
    salt, prefix = head[len(MAGIC):len(MAGIC) + 16], head[len(MAGIC) + 16:]
    aes, h, total, i = AESGCM(_subkey(key, salt, name)), hashlib.sha256(), 0, 0
    size = src.read(4)
    while True:
        if len(size) != 4:
            raise ValueError("the object is cut off")
        (ln,) = struct.unpack(">I", size)
        if ln > CHUNK + 16:
            raise ValueError("the object is damaged")
        ct = src.read(ln)
        size = src.read(4)
        last = not size
        try:
            block = aes.decrypt(prefix + struct.pack(">Q", i), ct, struct.pack(">Q?", i, last))
        except InvalidTag:
            raise ValueError("the object was changed, cut off or belongs to another key")
        total += len(block)
        if total > most:
            raise ValueError("the object is too large")
        h.update(block)
        dst.write(block)
        if last:
            return h.hexdigest()
        i += 1


def seal_bytes(data, key, name):
    import io
    out = io.BytesIO()
    seal_file(io.BytesIO(data), out, key, name)
    return out.getvalue()


def open_bytes(data, key, name, most=8 * 1024 * 1024):
    import io
    out = io.BytesIO()
    open_file(io.BytesIO(data), out, key, name, most)
    return out.getvalue()


# ---------------------------------------------------------------- the profile's files
def _rel_ok(rel):
    """A path of the allowlist: one of the files, or a plain file name in one of the folders."""
    if not isinstance(rel, str) or len(rel) > 120:
        return False
    for _, _, items in AREAS.values():
        for it in items:
            if it.endswith("/"):
                rest = rel[len(it):] if rel.startswith(it) else ""
                if rest and "/" not in rest and FILE_RE.fullmatch(rest) and not rest.startswith(".") \
                        and not rest.endswith(".tmp"):
                    return True
            elif rel == it:
                return True
    return False


def local_files(uid, areas):
    """{rel: (path, size, mtime_ns)} of the chosen areas: regular files only, no symlinks, at most MAX_FILES."""
    base, out = profiles._path(uid), {}
    for a in areas:
        for it in AREAS.get(a, ("", "", ()))[2]:
            if it.endswith("/"):
                d = os.path.join(base, it)
                try:
                    if os.path.islink(d.rstrip("/")) or not os.path.isdir(d):
                        continue
                    entries = sorted(os.scandir(d), key=lambda e: e.name)
                except OSError:
                    continue
                cands = [(it + e.name, e) for e in entries]
            else:
                p = os.path.join(base, it)
                try:
                    cands = [(it, os.lstat(p) and _Entry(p))]
                except OSError:
                    continue
            for rel, e in cands:
                if len(out) >= MAX_FILES or not _rel_ok(rel):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode) and st.st_size <= MAX_FILE:
                    out[rel] = (os.path.join(base, rel), st.st_size, st.st_mtime_ns)
    return out


class _Entry:
    def __init__(self, path):
        self.path = path

    def stat(self, follow_symlinks=False):
        return os.lstat(self.path)


def _snapshot(path, dst):
    """A consistent copy of one file: SQLite through its backup (the panel may be writing), else the bytes."""
    if path.endswith(".db"):
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            out = sqlite3.connect(dst)
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()
        return
    with open(path, "rb") as a, open(dst, "wb") as b:
        if os.fstat(a.fileno()).st_size > MAX_FILE:
            raise ValueError("file too large")
        shutil.copyfileobj(a, b, CHUNK)


# ---------------------------------------------------------------- the targets themselves
def _time(size):
    return TIMEOUT + size / (2 * 1024 * 1024)     # at least 2 MB/s


class WebDav:
    """A WebDAV folder (https, or http in the home network) through netguard; the login only for its site."""

    def __init__(self, t, key):
        self.base = t["url"] + folder_name(key) + "/"
        self.root = t["url"]
        self.auth = (t["user"], vault.open_(t["password"]) or "") if t.get("user") else None
        self.level = netguard.HOME if lan_ok() else netguard.USER
        self.cert = t.get("cert") or ""     # the certificate accepted for its NAS connection (zertpin.py), else the normal check

    def _client(self, timeout, most=1024 * 1024):
        return netguard.client(self.level, origin=self.root, max_bytes=most, timeout=httpx.Timeout(timeout, connect=15),
                               verify=zertpin.verify(self.cert))

    @staticmethod
    def _raise(code):
        if code in (401, 403):
            raise StoreError("auth", f"HTTP {code}")
        if code == 507:
            raise StoreError("full", "HTTP 507")
        if code in (502, 503, 504):
            raise StoreError("offline", f"HTTP {code}")
        raise StoreError("other", f"HTTP {code}")

    async def _call(self, method, url, timeout=TIMEOUT, most=1024 * 1024, **kw):
        try:
            async with self._client(timeout, most) as c:
                r = await c.request(method, url, auth=self.auth, **kw)
                return r
        except netguard.Blocked as e:
            raise StoreError("notaus" if "Notaus" in str(e) else "blocked", str(e)[:200])
        except (httpx.ConnectError, httpx.TimeoutException, OSError, ssl.SSLError) as e:
            raise StoreError("cert" if zertpin.problem(e) else "offline", type(e).__name__)
        except (httpx.HTTPError, netguard.TooLarge, ValueError) as e:
            raise StoreError("cert" if zertpin.problem(e) else "other", type(e).__name__)

    async def prepare(self):
        for url in (self.base, self.base + "o/"):
            r = await self._call("MKCOL", url)
            if r.status_code not in (201, 405, 301, 302):   # 405: it is there already
                self._raise(r.status_code)

    async def put(self, name, path):
        size = os.path.getsize(path)

        async def body():
            with open(path, "rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk
        r = await self._call("PUT", self.base + quote(name), timeout=_time(size), content=body(),
                             headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)})
        if r.status_code not in (200, 201, 204):
            self._raise(r.status_code)

    async def get(self, name, dst, most):
        try:
            async with self._client(_time(most), most + 64 * 1024) as c:
                async with c.stream("GET", self.base + quote(name), auth=self.auth) as r:
                    if r.status_code == 404:
                        raise StoreError("other", "missing")
                    if r.status_code != 200:
                        self._raise(r.status_code)
                    with open(dst, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
        except StoreError:
            raise
        except netguard.Blocked as e:
            raise StoreError("blocked", str(e)[:200])
        except (httpx.ConnectError, httpx.TimeoutException, OSError, ssl.SSLError) as e:
            raise StoreError("cert" if zertpin.problem(e) else "offline", type(e).__name__)
        except (httpx.HTTPError, netguard.TooLarge, ValueError) as e:
            raise StoreError("cert" if zertpin.problem(e) else "other", type(e).__name__)

    async def delete(self, name):
        r = await self._call("DELETE", self.base + quote(name))
        if r.status_code not in (200, 204, 404):
            self._raise(r.status_code)

    async def free(self):
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:quota-available-bytes/>'
                '<d:quota-used-bytes/></d:prop></d:propfind>')
        r = await self._call("PROPFIND", self.root, content=body.encode(), most=64 * 1024,
                             headers={"Depth": "0", "Content-Type": "application/xml"})
        if r.status_code != 207:
            return None
        # only two numbers are read: no XML parser for the server's answer
        av = re.search(r"quota-available-bytes[^>]*>\s*(\d{1,20})\s*<", r.text)
        us = re.search(r"quota-used-bytes[^>]*>\s*(\d{1,20})\s*<", r.text)
        if not av and not us:
            return None
        return {"avail": int(av.group(1)) if av else None, "used": int(us.group(1)) if us else None}

    def probe(self):
        """For the Dienst-Wächter: the address it looks at (no login)."""
        return {"url": self.root, "level": self.level, "verify": True, "pin": self.cert}

    async def close(self):
        pass


class Folder:
    """A folder below the admin's chat.storage_root: every call in its own thread with a time limit."""

    def __init__(self, t, key):
        r = root()
        if not r:
            raise StoreError("blocked", "no folder allowed")
        self.top = os.path.join(r, t["folder"])
        self.base = os.path.join(self.top, folder_name(key))

    async def _run(self, fn, *args, timeout=FOLDER_TIMEOUT):
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout)
        except asyncio.TimeoutError:
            raise StoreError("offline", "the folder does not answer")
        except StoreError:
            raise
        except OSError as e:
            import errno
            if e.errno in (errno.ENOSPC, errno.EDQUOT):
                raise StoreError("full", "no space left")
            if e.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
                raise StoreError("auth", "no right to write")
            raise StoreError("offline", type(e).__name__)

    def _safe_dir(self, d):
        """Creates d (0700) when missing; refuses a symlink on the way."""
        for p in (self.top, self.base, os.path.join(self.base, "o")):
            if not p.startswith(self.top):
                break
            if os.path.islink(p):
                raise StoreError("blocked", "a symlink in the folder")
            if not os.path.isdir(p):
                os.mkdir(p, 0o700)
            if p == d:
                break

    def _path(self, name):
        parts = name.split("/")
        if not all(FILE_RE.fullmatch(x) and not x.startswith(".") for x in parts) or len(parts) > 2:
            raise StoreError("other", "bad name")
        return os.path.join(self.base, *parts)

    async def prepare(self):
        await self._run(self._safe_dir, os.path.join(self.base, "o"))

    async def put(self, name, path):
        dst = self._path(name)

        def copy():
            self._safe_dir(os.path.dirname(dst))
            tmp = dst + ".part"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with open(fd, "wb") as b, open(path, "rb") as a:
                shutil.copyfileobj(a, b, CHUNK)
                b.flush()
                os.fsync(b.fileno())
            os.replace(tmp, dst)
        await self._run(copy, timeout=FOLDER_TIMEOUT + _time(os.path.getsize(path)))

    async def get(self, name, dst, most):
        src = self._path(name)

        def copy():
            fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
            with open(fd, "rb") as a, open(dst, "wb") as b:
                if os.fstat(a.fileno()).st_size > most + 64 * 1024:
                    raise StoreError("other", "too large")
                shutil.copyfileobj(a, b, CHUNK)
        try:
            await self._run(copy, timeout=FOLDER_TIMEOUT + _time(most))
        except StoreError as e:
            if not os.path.exists(src):
                raise StoreError("other", "missing")
            raise e

    async def delete(self, name):
        p = self._path(name)

        def rm():
            try:
                if not os.path.islink(p):
                    os.remove(p)
            except FileNotFoundError:
                pass
        await self._run(rm)

    async def free(self):
        def look():
            s = os.statvfs(self.top if os.path.isdir(self.top) else root())
            return {"avail": s.f_bavail * s.f_frsize, "used": (s.f_blocks - s.f_bfree) * s.f_frsize}
        return await self._run(look)

    def probe(self):
        return None

    async def close(self):
        pass


class _Remote:
    """A folder on a server the Spark reaches itself (SFTP, SMB3): the address checked by netguard once (the
    connection goes to that address), one connection per run, every call in its own thread with a time limit
    (a server that hangs never holds the panel). Written as <name>.part, then renamed."""
    SEP = "/"

    def __init__(self, t, key):
        u = urlsplit(t["url"])
        self.t = t
        self.host = (u.hostname or "").lower()
        self.port = u.port or self.PORT
        self.user = t.get("user") or ""
        self.pw = vault.open_(t["password"]) or "" if t.get("password") else ""
        self.level = netguard.HOME if lan_ok() else netguard.USER
        self.top = self._top(u.path)
        self.base = self._join(self.top, folder_name(key))
        self.conn = None

    def _join(self, *parts):
        return self.SEP.join(p.strip(self.SEP) if i else p.rstrip(self.SEP) for i, p in enumerate(parts) if p)

    @staticmethod
    def _parts(name):
        parts = name.split("/")
        if not all(FILE_RE.fullmatch(x) and not x.startswith(".") for x in parts) or len(parts) > 2:
            raise StoreError("other", "bad name")
        return parts

    def _path(self, parts):
        return self._join(self.base, *parts)      # only inside a call: SMB knows its address after connecting

    def _address(self):
        try:
            return netguard.resolve(self.host, self.port, self.level)
        except netguard.Blocked as e:
            raise StoreError("notaus" if "Notaus" in str(e) else "blocked", str(e)[:200])
        except httpx.ConnectError as e:
            raise StoreError("offline", type(e).__name__)

    def _with(self, fn, *args):
        if self.conn is None:
            self.conn = self._connect()
        return fn(*args)

    async def _run(self, fn, *args, timeout=TIMEOUT):
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._with, fn, *args), timeout)
        except asyncio.TimeoutError:
            await self.close()
            raise StoreError("offline", "the server does not answer")
        except StoreError:
            raise
        except Exception as e:
            kind = self._kind(e)
            if kind == "offline":
                await self.close()
            raise StoreError("other", "missing") if kind == "missing" else StoreError(kind, type(e).__name__)

    def _errno_kind(self, e):
        import errno
        n = getattr(e, "errno", None)
        if n in (errno.ENOSPC, errno.EDQUOT):
            return "full"
        if n in (errno.EACCES, errno.EPERM, errno.EROFS):
            return "auth"
        if n == errno.ENOENT:
            return "missing"
        return None

    def _mkdirs(self):
        p = ""
        for part in [x for x in self.base.split(self.SEP) if x] + ["o"]:
            p = self._join(p, part) if p else (self.SEP + part if self.base.startswith(self.SEP) else part)
            if not self._isdir(p):
                self._mkdir(p)

    async def prepare(self):
        await self._run(self._mkdirs)

    async def put(self, name, path):
        parts = self._parts(name)

        def copy():
            dst = self._path(parts)
            tmp = dst + ".part"
            with open(path, "rb") as a, self._open(tmp, "wb") as b:
                while chunk := a.read(CHUNK):
                    b.write(chunk)
            self._replace(tmp, dst)
        await self._run(copy, timeout=_time(os.path.getsize(path)))

    async def get(self, name, dst, most):
        parts = self._parts(name)

        def copy():
            src = self._path(parts)
            if self._size(src) > most + 64 * 1024:
                raise StoreError("other", "too large")
            got = 0
            with self._open(src, "rb") as a, open(dst, "wb") as b:
                while chunk := a.read(CHUNK):
                    got += len(chunk)
                    if got > most + 64 * 1024:
                        raise StoreError("other", "too large")
                    b.write(chunk)
        await self._run(copy, timeout=_time(most))

    async def delete(self, name):
        parts = self._parts(name)

        def rm():
            try:
                self._remove(self._path(parts))
            except Exception as e:
                if self._kind(e) != "missing":
                    raise
        await self._run(rm)

    async def free(self):
        return None

    async def close(self):
        conn, self.conn = self.conn, None
        if conn is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.to_thread(self._disconnect, conn), 5)

    def probe(self):
        return {"tcp": True, "host": self.host, "port": self.port, "level": self.level, "ssh": self.SSH}


def hostkey_of(key):
    """How a server's SSH key is shown and pinned: "<type> SHA256:<base64>" (like ssh-keygen -l)."""
    return f"{key.get_name()} SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")


class Sftp(_Remote):
    """SFTP (SSH) with user and password: the server's key is learned when the target is added and must stay the
    same (else "hostkey": the profile accepts a new key itself with its password and a code)."""
    PORT = 22
    SSH = True

    def __init__(self, t, key):
        super().__init__(t, key)
        self.pinned = t.get("hostkey") or ""
        self.seen = ""

    def _top(self, path):
        return path.rstrip("/") or "."

    def _connect(self):
        import logging
        import paramiko
        logging.getLogger("paramiko").setLevel(logging.CRITICAL)   # its tracebacks carry server texts: our own fixed words only
        sock = socket.create_connection((self._address(), self.port), 15)
        tr = paramiko.Transport(sock, disabled_algorithms={"keys": ["ssh-dss"], "pubkeys": ["ssh-dss"]})
        tr.banner_timeout = tr.handshake_timeout = tr.auth_timeout = 15
        try:
            tr.start_client(timeout=15)
            self.seen = hostkey_of(tr.get_remote_server_key())
            if self.pinned and not hmac.compare_digest(self.seen, self.pinned):
                raise StoreError("hostkey", "the server's key changed")
            tr.auth_password(self.user, self.pw)
            sftp = paramiko.SFTPClient.from_transport(tr)
            sftp.get_channel().settimeout(TIMEOUT)
            return (tr, sftp)
        except BaseException:
            tr.close()
            raise

    def _disconnect(self, conn):
        conn[1].close()
        conn[0].close()

    def _kind(self, e):
        import paramiko
        if isinstance(e, paramiko.AuthenticationException):
            return "auth"
        if isinstance(e, (paramiko.SSHException, EOFError, socket.timeout, ConnectionError)):
            return "offline"
        if isinstance(e, OSError):
            k = self._errno_kind(e)
            if k:
                return k
            return "offline" if not getattr(e, "errno", None) else "other"
        return "other"

    def _isdir(self, p):
        try:
            return stat.S_ISDIR(self.conn[1].stat(p).st_mode)
        except FileNotFoundError:
            return False

    def _mkdir(self, p):
        self.conn[1].mkdir(p, 0o700)

    def _open(self, p, mode):
        f = self.conn[1].open(p, mode)
        if "w" in mode:
            f.set_pipelined(True)
        return f

    def _size(self, p):
        return self.conn[1].stat(p).st_size

    def _replace(self, a, b):
        try:
            self.conn[1].posix_rename(a, b)
        except OSError:
            with contextlib.suppress(OSError):
                self.conn[1].remove(b)
            self.conn[1].rename(a, b)

    def _remove(self, p):
        self.conn[1].remove(p)


class Smb(_Remote):
    """SMB3 (Windows share, NAS share) with user and password, only in the home network and only encrypted
    (encrypt=True: SMB 3 with encryption; an older server is refused). Own connection cache per run."""
    PORT = 445
    SSH = False
    SEP = "\\"

    def _top(self, path):
        parts = [x for x in path.split("/") if x]
        return "\\\\" + "{ip}" + "\\" + "\\".join(parts)

    def _connect(self):
        import smbclient
        ip = self._address()
        cache = {}
        smbclient.register_session(ip, username=self.user, password=self.pw, port=self.port, encrypt=True,
                                   connection_timeout=15, connection_cache=cache, auth_protocol="ntlm")
        self.top = self.top.replace("{ip}", ip)
        self.base = self.base.replace("{ip}", ip)
        return (ip, cache)

    def _join(self, *parts):
        out = parts[0].rstrip("\\") if parts else ""
        for p in parts[1:]:
            if p:
                out += "\\" + p.strip("\\/").replace("/", "\\")
        return out

    def _mkdirs(self):
        parts = self.base[2:].split("\\")     # {ip}, share, sub ..., spark-...
        p = "\\\\" + "\\".join(parts[:2])
        for part in parts[2:] + ["o"]:
            p += "\\" + part
            if not self._isdir(p):
                self._mkdir(p)

    def _kw(self):
        return {"port": self.port, "connection_cache": self.conn[1]}

    def _disconnect(self, conn):
        import smbclient
        smbclient.reset_connection_cache(connection_cache=conn[1])

    def _kind(self, e):
        from smbprotocol import exceptions as x
        if isinstance(e, (x.SMBAuthenticationError, x.LogonFailure, x.AccessDenied)):
            return "auth"
        if isinstance(e, OSError):
            k = self._errno_kind(e)
            if k:
                return k
            if isinstance(e, (ConnectionError, socket.timeout)) or not getattr(e, "errno", None):
                return "offline"
            return "other"
        if isinstance(e, (x.SMBConnectionClosed, x.SMBException, ValueError)):
            return "offline" if isinstance(e, x.SMBConnectionClosed) else "other"
        return "other"

    def _isdir(self, p):
        import smbclient
        try:
            return stat.S_ISDIR(smbclient.stat(p, **self._kw()).st_mode)
        except FileNotFoundError:
            return False

    def _mkdir(self, p):
        import smbclient
        smbclient.mkdir(p, **self._kw())

    def _open(self, p, mode):
        import smbclient
        return smbclient.open_file(p, mode=mode, **self._kw())

    def _size(self, p):
        import smbclient
        return smbclient.stat(p, **self._kw()).st_size

    def _replace(self, a, b):
        import smbclient
        smbclient.replace(a, b, **self._kw())

    def _remove(self, p):
        import smbclient
        smbclient.remove(p, **self._kw())


def driver(t, key):
    if t["kind"] == "webdav":
        return WebDav(t, key)
    if t["kind"] == "sftp":
        return Sftp(t, key)
    if t["kind"] == "smb":
        return Smb(t, key)
    if not folder_ok():
        raise StoreError("blocked", "folders on the Spark are switched off")
    return Folder(t, key)


# ---------------------------------------------------------------- one run
def _rec(st, ok, kind="", n=0, size=0, now=None, what="copy"):
    now = int(now or time.time())
    st["hist"] = [x for x in st["hist"] if now - int(x.get("t") or 0) < KEEP_HIST][-(MAX_HIST - 1):] + \
        [{"t": now, "ok": ok, "kind": kind, "n": n, "bytes": size, "what": what}]


async def _manifest(drv, key, st):
    data = json.dumps({"v": 1, "t": int(time.time()), "files": st["files"]}, separators=(",", ":")).encode()
    tmp = _tmp(".enc")
    with open(tmp, "wb") as f:
        f.write(seal_bytes(data, key, "manifest"))
    try:
        await drv.put("manifest.enc", tmp)
    finally:
        _rm(tmp)
    st["manifest"] = True


def _tmp(suffix=""):
    """A temp file only the panel can read, in STATE/speicher-tmp (never /tmp: plain profile data passes there)."""
    d = os.path.join(STATE, "speicher-tmp")
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="sp-", suffix=suffix, dir=d)
    os.close(fd)
    return path


def clean_tmp():
    """At start: what a run cut off by a restart left behind."""
    d = os.path.join(STATE, "speicher-tmp")
    try:
        for n in os.listdir(d):
            if n.startswith("sp-"):
                _rm(os.path.join(d, n))
    except OSError:
        pass


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _quiet_hold():
    try:
        import vorrang
        vorrang.hold("Speicher-Abgleich")
    except Exception:
        pass


def _pack(path, key, obj):
    """Snapshot + encryption of one file in a worker thread: (temp file, plain bytes, SHA-256)."""
    _quiet_hold()
    plain, enc = _tmp(), _tmp(".enc")
    try:
        _snapshot(path, plain)
        with open(plain, "rb") as a, open(enc, "wb") as b:
            size, sha = seal_file(a, b, key, obj)
        return enc, size, sha
    except Exception:
        _rm(enc)
        raise
    finally:
        _rm(plain)


async def copy_once(uid, tid, why="auto", now=None):
    """One run of the Kopie: only what changed since the last run. Returns the "last" entry."""
    t = find(uid, tid)
    if not t:
        raise StoreError("other", "no such target")
    if (uid, tid) in _running:
        return _state(uid, tid)["last"]
    _running[(uid, tid)] = "copy"
    t0 = time.time()
    st = _state(uid, tid)
    n = sent = 0
    drv = None
    _live_bg("run")
    try:
        key = _key(uid)
        if not key:
            raise StoreError("key", "the storage key cannot be opened")
        drv = driver(t, key)
        files = await asyncio.to_thread(local_files, uid, t["areas"])
        await drv.prepare()
        changed = False
        for rel, (path, size, mt) in files.items():
            old = st["files"].get(rel)
            if old and old.get("size") == size and old.get("mt") == mt:
                continue
            if sent + size > RUN_BYTES and n:
                break   # the next run goes on
            obj = secrets.token_hex(12)
            try:
                enc, plain, sha = await asyncio.to_thread(_pack, path, key, obj)
            except (OSError, ValueError, sqlite3.Error):
                continue   # gone or locked just now: the next run
            try:
                if old and old.get("sha") == sha:
                    st["files"][rel] = {k: v for k, v in dict(old, size=size, mt=mt).items() if k != "off"}
                    continue
                await drv.put("o/" + obj + ".enc", enc)
            finally:
                _rm(enc)
            if old:
                st["trash"].append({"o": old["o"], "t": int(time.time())})
            st["files"][rel] = {"o": obj, "size": size, "sha": sha, "mt": mt}
            n, sent, changed = n + 1, sent + plain, True
            if n % 50 == 0:
                await _manifest(drv, key, st)
                _put_state(uid, tid, st)
        for rel in [r for r in st["files"] if r not in files]:   # deleted, or its area taken off the list
            if st["files"][rel].get("off") and await asyncio.to_thread(_still_used, uid, rel):
                continue      # moved out (Auslagern): it lives only there now
            st["trash"].append({"o": st["files"].pop(rel)["o"], "t": int(time.time())})
            changed = True
        if t.get("offload") and offload_ok() and "dokumente" in t["areas"]:
            changed = await _offload(uid, tid, st, drv, key, files) or changed
        if changed or not st["manifest"]:
            await _manifest(drv, key, st)
        keep = []
        for x in st["trash"]:
            if time.time() - int(x.get("t") or 0) > TRASH_DAYS * 86400:
                try:
                    await drv.delete("o/" + x["o"] + ".enc")
                except StoreError:
                    keep.append(x)
            else:
                keep.append(x)
        st["trash"] = keep[-MAX_FILES:]
        try:
            st["free"] = dict(await drv.free() or {}, t=int(time.time()))
        except StoreError:
            pass
        last = {"t": int(time.time()), "ok": True, "n": n, "bytes": sent, "seconds": round(time.time() - t0), "why": why,
                "files": len(st["files"]), "pending": sum(1 for r, (_, s, m) in files.items()
                                                           if (st["files"].get(r) or {}).get("mt") != m)}
        was = st["fail"]
        st.update(last=last, fail=None)
        _rec(st, True, n=n, size=sent)
        _put_state(uid, tid, st)
        print(f"speicher: lauf ziel={t['kind']} prof={_log_name(uid)} dateien={n} bytes={sent} dauer={last['seconds']}s ok",
              flush=True)
        _job(t0, True, uid)
        if was and was.get("noted"):
            await _note(uid, t, "back")
        return last
    except StoreError as e:
        kind = "offline" if e.kind == "notaus" else e.kind
        fail = st["fail"] or {"since": int(t0), "n": 0}
        fail.update(kind=kind, n=int(fail.get("n") or 0) + 1, t=int(time.time()))
        last = {"t": int(time.time()), "ok": False, "kind": kind, "n": n, "bytes": sent, "why": why}
        st.update(last=last, fail=fail)
        _rec(st, False, kind, n, sent)
        _put_state(uid, tid, st)
        print(f"speicher: fehler ziel={t['kind']} prof={_log_name(uid)} art={kind} versuch={fail['n']}", flush=True)
        _job(t0, False, uid)
        if e.kind != "notaus":
            await _maybe_note(uid, t, st)
        return last
    finally:
        if drv is not None:
            await drv.close()
        _running.pop((uid, tid), None)
        _live_bg(None, t0)


async def restore_missing(uid, tid, now=None):
    """"Fehlendes zurückholen": every file of the copy that is missing on the Spark, checked against its SHA-256.
    Never overwrites a file that is there. Returns {"n", "skipped"}."""
    t = find(uid, tid)
    if not t:
        raise StoreError("other", "no such target")
    if (uid, tid) in _running:
        raise StoreError("other", "busy")
    _running[(uid, tid)] = "restore"
    t0 = time.time()
    n = skipped = 0
    drv = None
    back = []
    try:
        key = _key(uid)
        if not key:
            raise StoreError("key", "the storage key cannot be opened")
        drv = driver(t, key)
        tmp = _tmp()
        try:
            await drv.get("manifest.enc", tmp, 64 * 1024 * 1024)
            with open(tmp, "rb") as f:
                man = json.loads(open_bytes(f.read(), key, "manifest", 64 * 1024 * 1024))
        except (ValueError, OSError) as e:
            raise StoreError("other", f"manifest: {type(e).__name__}")
        finally:
            _rm(tmp)
        files = man.get("files") if isinstance(man, dict) and isinstance(man.get("files"), dict) else {}
        base = profiles._path(uid)
        for rel, x in list(files.items())[:MAX_FILES]:
            if not _rel_ok(rel) or not isinstance(x, dict) or not OBJ.fullmatch(str(x.get("o", ""))) \
                    or not re.fullmatch(r"[0-9a-f]{64}", str(x.get("sha", ""))):
                skipped += 1
                continue
            dst = os.path.join(base, rel)
            if os.path.lexists(dst):
                continue
            enc = _tmp(".enc")
            try:
                await drv.get("o/" + x["o"] + ".enc", enc, MAX_FILE + 64 * 1024)

                def unpack():
                    os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
                    part = dst + ".tmp"
                    try:
                        with open(enc, "rb") as a, open(os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as b:
                            sha = open_file(a, b, key, x["o"])
                        if sha != x["sha"]:
                            raise ValueError("checksum")
                        if os.path.lexists(dst):
                            raise ValueError("there now")
                        os.replace(part, dst)
                    finally:
                        _rm(part)
                await asyncio.to_thread(unpack)
                n += 1
                back.append(rel)
            except (ValueError, OSError):
                skipped += 1
            except StoreError as e:
                if e.kind != "other":
                    raise
                skipped += 1
            finally:
                _rm(enc)
        st = _state(uid, tid)
        for rel in back:          # an original that was moved out is on the Spark again
            if rel in st["files"]:
                st["files"][rel].pop("off", None)
                st["used"][rel] = int(time.time())
        _rec(st, True, n=n, what="restore")
        _put_state(uid, tid, st)
        print(f"speicher: zurueckgeholt ziel={t['kind']} prof={_log_name(uid)} dateien={n} uebersprungen={skipped}", flush=True)
        _job(t0, True, uid, "Speicher holen")
        _event(f"{n} Dateien aus der Kopie zurückgeholt")
        return {"n": n, "skipped": skipped}
    except StoreError as e:
        st = _state(uid, tid)
        _rec(st, False, e.kind, n, what="restore")
        _put_state(uid, tid, st)
        print(f"speicher: zurueckholen fehler ziel={t['kind']} prof={_log_name(uid)} art={e.kind}", flush=True)
        _job(t0, False, uid, "Speicher holen")
        raise
    finally:
        if drv is not None:
            await drv.close()
        _running.pop((uid, tid), None)


class _Null:
    def write(self, b):
        return len(b)


def _still_used(uid, rel):
    """A moved-out original whose document still exists (else it goes to the bin like any deleted file)."""
    if not rel.startswith(OFF_PREFIX):
        return False
    try:
        import documents
        if not os.path.exists(documents.db_path(uid)):
            return False
        with documents._Db(uid) as con:
            return bool(con.execute("SELECT 1 FROM docs WHERE file=?", (rel[len(OFF_PREFIX):],)).fetchone())
    except Exception:
        return True       # in doubt it stays listed: nothing is ever lost because of a locked database


async def _offload(uid, tid, st, drv, key, files, now=None):
    """Auslagern (5b): originals unchanged and unused for OFFLOAD_DAYS live only on the storage. Each object is
    read back and checked against its SHA-256 before the file on the Spark is removed. Returns whether any moved."""
    now, budget, moved = now or time.time(), OFFLOAD_RUN, 0
    for rel, x in list(st["files"].items()):
        if not rel.startswith(OFF_PREFIX) or x.get("off") or rel not in files:
            continue
        path, size, mt = files[rel]
        if x.get("mt") != mt or x.get("size") != size or size > budget:
            continue
        if now - mt / 1e9 < OFFLOAD_DAYS * 86400 or now - st["used"].get(rel, 0) < OFFLOAD_DAYS * 86400:
            continue
        enc = _tmp(".enc")
        try:
            await drv.get("o/" + x["o"] + ".enc", enc, size + 64 * 1024)

            def verify():
                with open(enc, "rb") as f:
                    return open_file(f, _Null(), key, x["o"], size)
            if await asyncio.to_thread(verify) != x["sha"]:
                continue
            if now - _state(uid, tid)["used"].get(rel, 0) < OFFLOAD_DAYS * 86400:
                continue        # opened while it was checked
            a = os.lstat(path)
            if not stat.S_ISREG(a.st_mode) or a.st_size != size or a.st_mtime_ns != mt:
                continue        # changed while it was checked: stays
            os.remove(path)
        except (ValueError, OSError):
            continue
        except StoreError as e:
            if e.kind != "other":
                raise
            continue
        finally:
            _rm(enc)
        x["off"] = int(now)
        budget -= size
        moved += 1
    if moved:
        print(f"speicher: ausgelagert prof={_log_name(uid)} dateien={moved}", flush=True)
        _event(f"{moved} Originale in die Kopie ausgelagert")
    return moved > 0


def offloaded(uid, rel):
    """The target (id) that holds a moved-out file, or None."""
    for tid, s in _states(uid).items():
        x = (s.get("files") or {}).get(rel) if isinstance(s, dict) else None
        if isinstance(x, dict) and x.get("off") and find(uid, tid):
            return tid
    return None


def opened(uid, rel):
    """documents.original: an original in use is not moved out (one stamp a day is enough)."""
    if not _rel_ok(rel) or not rel.startswith(OFF_PREFIX) or not offload_ok():
        return
    now = int(time.time())
    with _lock:
        for t in targets(uid):
            if t.get("offload"):
                st = _state(uid, t["id"])
                if rel in st["files"] and now - st["used"].get(rel, 0) > 86400:
                    st["used"][rel] = now
                    _put_state(uid, t["id"], st)


def away(uid):
    """{tid: number of originals that live only on that storage}."""
    out = {}
    for tid, s in _states(uid).items():
        n = sum(1 for x in (s.get("files") or {}).values() if isinstance(x, dict) and x.get("off"))
        if n:
            out[tid] = n
    return out


_back_locks = {}


def bring_back(uid, rel):
    """A moved-out original back on the Spark (documents.original calls it when the file is missing): fetched,
    checked against its SHA-256 and written only where nothing is. Blocking; never in the event loop's own
    thread (there it gives up: a page waits, the panel does not). True when the file is there now."""
    if not _rel_ok(rel) or not rel.startswith(OFF_PREFIX):
        return False
    try:
        asyncio.get_running_loop()
        return False
    except RuntimeError:
        pass
    tid = offloaded(uid, rel)
    if not tid or not allowed(uid):
        return False
    lk = _back_locks.setdefault(uid, threading.Lock())
    with lk:
        dst = os.path.join(profiles._path(uid), rel)
        if os.path.lexists(dst):
            return os.path.isfile(dst)
        return asyncio.run(_bring_back(uid, tid, rel, dst))


async def _bring_back(uid, tid, rel, dst):
    t, t0 = find(uid, tid), time.time()
    x = _state(uid, tid)["files"].get(rel) or {}
    key = _key(uid)
    if not t or not key or not x.get("off"):
        return False
    drv, enc, ok = driver(t, key), _tmp(".enc"), False
    try:
        await drv.get("o/" + x["o"] + ".enc", enc, MAX_FILE + 64 * 1024)

        def unpack():
            os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
            part = dst + ".tmp"
            try:
                with open(enc, "rb") as a, open(os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as b:
                    sha = open_file(a, b, key, x["o"])
                if sha != x["sha"] or os.path.lexists(dst):
                    return False
                os.replace(part, dst)
                return True
            finally:
                _rm(part)
        ok = await asyncio.to_thread(unpack)
    except (StoreError, ValueError, OSError) as e:
        print(f"speicher: holen fehler ziel={t['kind']} prof={_log_name(uid)} art={getattr(e, 'kind', 'other')}", flush=True)
    finally:
        _rm(enc)
        await drv.close()
    if ok:
        with _lock:
            st = _state(uid, tid)
            if rel in st["files"]:
                st["files"][rel].pop("off", None)
                st["used"][rel] = int(time.time())
                _put_state(uid, tid, st)
        print(f"speicher: geholt ziel={t['kind']} prof={_log_name(uid)}", flush=True)
        _event("Original aus der Kopie geholt")
    _job(t0, ok, uid, "Speicher holen")
    return ok


async def check(t, key):
    """Can the Spark write there? Folder, a test object written and deleted, free space. Raises StoreError.
    SFTP: a target without a pinned server key learns it here (t["hostkey"], the caller saves t)."""
    drv = driver(t, key)
    tmp = _tmp(".enc")
    try:
        await drv.prepare()
        if isinstance(drv, Sftp) and not t.get("hostkey"):
            t["hostkey"] = drv.seen
        with open(tmp, "wb") as f:
            f.write(seal_bytes(b"spark", key, "probe"))
        await drv.put("probe.enc", tmp)
        await drv.delete("probe.enc")
        try:
            return await drv.free()
        except StoreError:
            return None
    finally:
        _rm(tmp)
        await drv.close()


# ---------------------------------------------------------------- notes, Live, logs
def _log_name(uid):
    return profiles.log_name(profiles.by_id(uid))


def _event(text):
    try:
        import live
        live.mark("Speicher", text)
    except Exception:
        pass


def _job(t0, ok, uid, tool="Speicher-Abgleich"):
    try:
        import live
        live.job("Kopie meiner Daten", tool, t0, ok=ok, uid=uid)
    except Exception:
        pass


def _live_bg(state, t0=None):
    try:
        import live
        if state:
            live.bg("Speicher-Abgleich", state)
        else:
            live.bg("Speicher-Abgleich", None)
    except Exception:
        pass


async def _maybe_note(uid, t, st, now=None):
    """The owner hears once when a target fails for NOTE_AFTER, the same kind again only after NOTE_AGAIN."""
    now = now or time.time()
    f = st["fail"] or {}
    kind = f.get("kind", "other")
    if now - int(f.get("since") or now) < NOTE_AFTER and kind not in ("auth", "full", "key"):
        return
    if now - int(st["noted"].get(kind) or 0) < NOTE_AGAIN:
        return
    st["noted"][kind] = int(now)
    f["noted"] = True
    _put_state(uid, t["id"], st)
    await _note(uid, t, kind)
    _event(f"Speicher eines Profils: {WHY[kind][0]}")


async def _note(uid, t, kind):
    if not profiles_on(uid):
        return
    if kind == "back":
        title, body = "✅ Kopie meiner Daten wieder da", f"„{t['name']}“ ist wieder erreichbar; der Abgleich hat nachgeholt."
    else:
        title = f"⚠️ Kopie meiner Daten: {WHY[kind][0]}"
        body = {"offline": f"„{t['name']}“ ist seit über einer Stunde nicht erreichbar. Alles bleibt auf dem Spark und wird nachgeholt.",
                "auth": f"„{t['name']}“ lehnt die Anmeldung ab. Der Abgleich pausiert; bitte unter Ich → Speicher beim Ort „Anmeldung ändern“ das Passwort neu eingeben.",
                "full": f"„{t['name']}“ ist voll. Neues bleibt auf dem Spark, bis wieder Platz ist; nichts wird gelöscht.",
                "blocked": f"„{t['name']}“ ist gerade nicht erlaubt (Wächter oder Admin). Alles bleibt auf dem Spark.",
                "key": f"Der Schlüssel für „{t['name']}“ fehlt. Die Kopie dort kann der Spark nicht mehr lesen; Ich → Speicher.",
                "other": f"Beim Ablegen auf „{t['name']}“ geht etwas schief. Alles bleibt auf dem Spark; Ich → Speicher."}[kind]
    try:
        import push
        await push.send(uid, title, body, tag="store", private=False)
    except Exception as e:
        print("speicher: note", type(e).__name__, flush=True)


def profiles_on(uid):
    return admin_on() and allowed(uid)


# ---------------------------------------------------------------- the loop
def due(uid, t, st, now=None):
    now = now or time.time()
    if (uid, t["id"]) in _running or not t["areas"]:
        return False
    last = st["last"] or {}
    if st["fail"]:
        if st["fail"].get("kind") in ("auth", "key"):
            return now - int(last.get("t") or 0) > RETRY[-1]     # a refused sign-in is only tried now and then
        wait = RETRY[min(len(RETRY), int(st["fail"].get("n") or 1)) - 1]
        return now - int(last.get("t") or 0) > wait
    return now - int(last.get("t") or 0) > EVERY


def _paused(now):
    if now - STARTED < START_GRACE:
        return True
    try:
        import update
        if update.update_running():
            return True
    except Exception:
        pass
    try:
        import notaus
        if notaus.level() >= 2:
            return True
    except Exception:
        pass
    return False


async def round_once(now=None):
    global _slots
    now = now or time.time()
    if not admin_on() or _paused(now):
        return []
    if _slots is None:
        _slots = asyncio.Semaphore(AT_ONCE)
    jobs = []
    for uid in profiles.user_ids():
        if not allowed(uid):
            continue
        for t in targets(uid):
            if due(uid, t, _state(uid, t["id"]), now):
                jobs.append((uid, t["id"]))

    async def one(uid, tid):
        async with _slots:
            await copy_once(uid, tid)
    for uid, tid in jobs:
        spawn(one(uid, tid))
    return jobs


async def loop():
    clean_tmp()
    while True:
        await asyncio.sleep(60)
        try:
            await round_once()
        except Exception as e:
            print("speicher: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- for other modules
def probes():
    """For the Dienst-Wächter: every WebDAV, SFTP and SMB target of every profile that may use it: key -> probe (no login)."""
    out = {}
    if not admin_on():
        return out
    for uid in profiles.user_ids():
        if not allowed(uid):
            continue
        for t in targets(uid):
            if t["kind"] in LOGIN_KINDS:
                u = urlsplit(t["url"])
                k = hashlib.sha256(f"{u.scheme}://{u.netloc}".encode()).hexdigest()[:8]
                level = netguard.HOME if lan_ok() else netguard.USER
                if t["kind"] == "webdav":
                    p = {"url": f"{u.scheme}://{u.netloc}/", "level": level, "verify": True, "pin": t.get("cert") or ""}
                else:   # SFTP: the server greets with "SSH-"; SMB: the port answers (no login, no command)
                    p = {"tcp": True, "host": (u.hostname or "").lower(), "port": u.port or (22 if t["kind"] == "sftp" else 445),
                         "level": level, "ssh": t["kind"] == "sftp"}
                out.setdefault(k, dict(p, uids=[]))["uids"].append(uid)
    return out


def summary(uid):
    """For Ich → Mein Zustand and others: (targets, failing)."""
    ts = targets(uid)
    return len(ts), sum(1 for t in ts if _state(uid, t["id"])["fail"])


# ---------------------------------------------------------------- views
def _zone(t):
    if t["kind"] == "folder":
        return "spark"
    return "lan" if _home_name((urlsplit(t["url"]).hostname or "").lower()) else "net"


def public(uid, t, st=None):
    """A target for the profile's page: never the password."""
    st = st or _state(uid, t["id"])
    out = {"id": t["id"], "name": t["name"], "kind": t["kind"], "zone": _zone(t), "areas": t["areas"], "added": t["added"],
           "last": st["last"], "fail": st["fail"], "free": st["free"], "files": len(st["files"]),
           "bytes": sum(int(x.get("size") or 0) for x in st["files"].values()), "trash": len(st["trash"]),
           "running": _running.get((uid, t["id"]), ""), "offload": t["offload"],
           "away": sum(1 for x in st["files"].values() if x.get("off")),
           "hist": [{k: x.get(k) for k in ("t", "ok", "kind", "n", "bytes", "what")} for x in st["hist"][-50:]]}
    if t["kind"] in LOGIN_KINDS:
        out.update(url=t["url"], user=t["user"], has_password=bool(t["password"]), nas=t.get("nas", ""))
        if out["nas"]:   # the folder at the place, so the page can show and change it
            try:
                import nas
                out["path"] = nas.split(t["url"], t["kind"])[1]
            except ValueError:   # only display; the target keeps working without it
                out["path"] = ""
        if t["kind"] == "sftp":
            out["hostkey"] = t.get("hostkey", "")
    else:
        out["folder"] = t["folder"]
    return out


def _view(uid):
    c = _chat()
    return {"admin": admin_on(c), "on": allowed(uid), "why": features.reason("speicher", uid),
            "lan": lan_ok(c), "folder": folder_ok(c), "offload": offload_ok(c), "offload_days": OFFLOAD_DAYS, "root": root(c) if folder_ok(c) else "", "max": MAX_TARGETS,
            "key": bool(load(uid)["key"]) and _key(uid) is not None or not load(uid)["key"],
            "areas": [{"id": k, "name": [v[0], v[1]]} for k, v in AREAS.items()],
            "targets": [public(uid, t) for t in targets(uid)]}


def overview():
    """Zustand → Speicher (admin): per profile and target kind, zone, state and numbers, never names of files."""
    rows = []
    names = {p["id"]: p["name"] for p in profiles.names()}
    for uid in profiles.user_ids():
        for t in targets(uid):
            st = _state(uid, t["id"])
            day = [x for x in st["hist"] if time.time() - int(x.get("t") or 0) < 86400]
            rows.append({"profile": names.get(uid, "?"), "name": t["name"], "kind": t["kind"], "zone": _zone(t),
                         "last": st["last"], "fail": st["fail"], "free": st["free"], "files": len(st["files"]),
                         "bytes": sum(int(x.get("size") or 0) for x in st["files"].values()),
                         "pending": (st["last"] or {}).get("pending", 0), "offload": t["offload"],
                         "away": sum(1 for x in st["files"].values() if x.get("off")), "errors_today": sum(1 for x in day if not x.get("ok")),
                         "allowed": allowed(uid), "running": bool(_running.get((uid, t["id"])))})
    return {"on": admin_on(), "lan": lan_ok(), "folder": folder_ok(), "root": root(), "rows": rows,
            "sum": {"targets": len(rows), "bytes": sum(r["bytes"] for r in rows), "failing": sum(1 for r in rows if r["fail"]),
                    "errors_today": sum(r["errors_today"] for r in rows)}}


# ---------------------------------------------------------------- routes (profile)
def _on(prof=Depends(browser_profile)):
    """Only the profile's own browser login, never a device key (no app, speaker or program)."""
    if not admin_on():
        raise HTTPException(403, "own storage is turned off")
    return prof


def _may(prof):
    if not allowed(prof["id"]):
        raise HTTPException(403, features.missing_text("speicher", prof["id"]) or "Kopie meiner Daten ist ausgeschaltet.")


def _areas(v):
    if not isinstance(v, list) or not all(isinstance(a, str) for a in v):
        raise HTTPException(400, "areas: a list")
    out = [a for a in AREAS if a in v]
    if len(out) != len(set(v)):
        raise HTTPException(400, "unknown area")
    return out


def _target_from(body, old=None):
    """A target from the page's fields (without the password), checked."""
    name = str(body.get("name", old["name"] if old else "") or "").strip()
    if not NAME.fullmatch(name):
        raise HTTPException(400, "Name: bis 40 Buchstaben, Ziffern, Leerzeichen, . _ -")
    kind = old["kind"] if old else body.get("kind")
    if kind not in KINDS:
        raise HTTPException(400, "kind: webdav, sftp, smb or folder")
    t = {"id": old["id"] if old else secrets.token_hex(3), "name": name, "kind": kind,
         "areas": _areas(body["areas"]) if "areas" in body else (old["areas"] if old else list(AREAS)),
         "added": old["added"] if old else int(time.time()),
         "offload": body["offload"] if "offload" in body else bool(old and old["offload"])}
    if not isinstance(t["offload"], bool):
        raise HTTPException(400, "offload: true or false")
    if t["offload"] and not (old and old["offload"]) and not offload_ok():
        raise HTTPException(400, "Auslagern hat der Admin nicht erlaubt (Funktionen → Kopie meiner Daten).")
    if kind in LOGIN_KINDS:
        try:
            t["url"] = check_url(body.get("url", old["url"] if old else ""), kind)
        except ValueError as e:
            raise HTTPException(400, str(e))
        host = (urlsplit(t["url"]).hostname or "").lower()
        if _home_name(host) and not lan_ok():
            raise HTTPException(400, "Ziele im Heimnetz hat der Admin nicht erlaubt (Funktionen → Kopie meiner Daten).")
        user = str(body.get("user", old["user"] if old else "") or "")
        if len(user) > 128 or re.search(r"[\x00-\x1f]", user):
            raise HTTPException(400, "invalid user name")
        t["user"], t["password"] = user, old["password"] if old else ""
        if kind == "sftp":    # a new address learns the server's key anew (check); else it stays unless accepted
            t["hostkey"] = old.get("hostkey", "") if old and t["url"] == old["url"] and body.get("accept_key") is not True else ""
    else:
        if not folder_ok():
            raise HTTPException(400, "Ordner auf dem Spark hat der Admin nicht erlaubt (Funktionen → Kopie meiner Daten).")
        sub = str(body.get("folder", old["folder"] if old else "") or "").strip()
        if not SUB.fullmatch(sub) or sub.startswith("."):
            raise HTTPException(400, "Unterordner: bis 40 Buchstaben, Ziffern, . _ - (kein Verweis, kein ..)")
        t["folder"] = sub
    return t


def _nas_body(uid, body):
    """{"nas": id, "path": "/folder"}: a target on one of the profile's NAS connections (nas.py) takes its address
    and user from there."""
    if not body.get("nas"):
        return body
    c = nas.find(uid, str(body["nas"]))
    if not c:
        raise HTTPException(404, "no such NAS connection")
    path = str(body.get("path") or "").strip().strip("/")
    return dict(body, kind=c["kind"], url=c["url"] + ("/" + path if path else "") + ("/" if c["kind"] == "webdav" else ""),
                user=c["user"])


def _from_nas(uid, t, body):
    """A target on a NAS connection the profile already has takes its accepted certificate, its server key and,
    when none is typed, its password: a certificate or key is never learned anew by adding a target."""
    if t["kind"] not in LOGIN_KINDS:
        return t
    m = nas.match(uid, t["kind"], t["url"], t["user"])
    if not m:
        return t
    if t["kind"] == "webdav":
        t["cert"] = m.get("cert", "")
    if t["kind"] == "sftp" and not t.get("hostkey") and body.get("accept_key") is not True:
        t["hostkey"] = m.get("hostkey", "")
    if not body.get("password") and not t.get("password"):
        t["password"] = m["password"]
    return t


def _one_offload(uid, t):
    if t["offload"] and any(x["offload"] for x in targets(uid) if x["id"] != t["id"]):
        raise HTTPException(400, "Auslagern geht nur auf einen Speicher.")


def _keep_away(uid, tid):
    """Originals that live only on this storage: it may not be taken away or pointed elsewhere first."""
    n = away(uid).get(tid, 0)
    if n:
        raise HTTPException(409, f"Erst „Fehlendes zurückholen“: {n} Originale liegen nur auf diesem Speicher.")


def _say(e):
    return {"offline": "Der Speicher antwortet nicht (Adresse, Netz oder NAS aus?).",
            "auth": "Der Speicher lehnt die Anmeldung oder das Schreiben ab (Benutzer, Passwort, Rechte).",
            "full": "Der Speicher ist voll.", "blocked": "Der Wächter erlaubt diese Adresse nicht.",
            "notaus": "Notaus ist an: keine Verbindung nach außen.", "key": "Der Schlüssel fehlt.",
            "cert": "Das Zertifikat des Speicherorts passt nicht zur Adresse oder ist selbst ausgestellt. Unter Ich → Speicher "
                    "beim Ort „Verbindung prüfen“ und den Fingerabdruck vergleichen.",
            "hostkey": "Der Schlüssel des Servers ist ein anderer als beim Einbinden. Nur wenn du weißt, warum "
                       "(Server neu eingerichtet), unter „Adresse oder Passwort ändern“ den neuen Schlüssel annehmen.",
            "other": "Der Speicher antwortet nicht wie erwartet (Ordner, Freigabe oder Rechte prüfen)."}.get(e.kind, "Fehler")


@router.get("/api/profile/speicher")
def get_mine(request: Request, prof=Depends(_on)):
    guard.limit(request, "storage", prof["id"])
    return _view(prof["id"])


@router.post("/api/profile/speicher")
async def add(request: Request, prof=Depends(_on)):
    """{"name", "kind", "url", "user", "password" | "folder", "areas"}: a new target, checked by writing there."""
    guard.limit(request, "storage", prof["id"])
    _may(prof)
    uid = prof["id"]
    body = _nas_body(uid, await core.json_body(request, 8192, lenient=True))
    t = _from_nas(uid, _target_from(body), body)
    _one_offload(uid, t)
    pw = body.get("password")
    if t["kind"] in LOGIN_KINDS and isinstance(pw, str) and pw:
        if len(pw) > 256:
            raise HTTPException(400, "password too long")
        t["password"] = vault.seal(pw)
    if len(targets(uid)) >= MAX_TARGETS:
        raise HTTPException(400, f"Höchstens {MAX_TARGETS} Speicher.")
    await secret_profile(request)     # a new place the profile's data goes to: a code (stufen.py, "Bestätigen")
    key = _key(uid, make=True)
    if not key:
        raise HTTPException(409, "Der Schlüssel für den Speicher lässt sich nicht öffnen.")
    try:
        free = await check(t, key)
    except StoreError as e:
        raise HTTPException(502, _say(e))
    with _lock:
        d = load(uid)
        if len(d["targets"]) >= MAX_TARGETS:
            raise HTTPException(400, f"Höchstens {MAX_TARGETS} Speicher.")
        d["targets"].append(t)
        save(uid, d)
    st = _state(uid, t["id"])
    st["free"] = dict(free or {}, t=int(time.time()))
    _put_state(uid, t["id"], st)
    guard.log("storage_add", detail=f"{t['kind']} {_zone(t)}")
    _event(f"Profil hat eine Kopie eingeschaltet ({t['kind']})")
    print(f"speicher: eingebunden ziel={t['kind']} prof={_log_name(uid)}", flush=True)
    return dict(_view(uid), added=t["id"])


@router.put("/api/profile/speicher/{tid}")
async def change(tid: str, request: Request, prof=Depends(_on)):
    """{"name", "areas"}; a new "url", "user" or "password" needs a code and is checked by writing there."""
    guard.limit(request, "storage", prof["id"])
    _may(prof)
    uid = prof["id"]
    old = find(uid, tid)
    if not old:
        raise HTTPException(404, "no such target")
    body = await core.json_body(request, 8192, lenient=True)
    t = _from_nas(uid, _target_from(body, old), body)
    _one_offload(uid, t)
    login = old["kind"] in LOGIN_KINDS and (t["url"] != old["url"] or t["user"] != old["user"] or bool(body.get("password"))
                                            or t.get("hostkey") != old.get("hostkey"))
    if old["kind"] == "folder" and t["folder"] != old["folder"]:
        login = True
    if t.get("url") != old.get("url") or t.get("folder") != old.get("folder"):
        _keep_away(uid, tid)
    if t["offload"] and not old["offload"] and not login:
        await secret_profile(request)     # from now on originals may live only there: a code like a new place
    if login:
        if t["kind"] in LOGIN_KINDS:
            pw = body.get("password")
            if (t["url"] != old["url"] or t.get("hostkey") != old.get("hostkey")) and not pw:
                raise HTTPException(400, "Eine neue Adresse oder ein neuer Schlüssel des Servers braucht das Passwort noch einmal.")
            if isinstance(pw, str) and pw:
                if len(pw) > 256:
                    raise HTTPException(400, "password too long")
                t["password"] = vault.seal(pw)
        await secret_profile(request)
        key = _key(uid, make=True)
        try:
            await check(t, key)
        except StoreError as e:
            raise HTTPException(502, _say(e))
    with _lock:
        d = load(uid)
        d["targets"] = [t if x["id"] == tid else x for x in d["targets"]]
        save(uid, d)
    if login:
        st = _state(uid, tid)
        if t.get("url") != old.get("url") or t.get("folder") != old.get("folder"):
            st = _state(uid, "000000")    # another place: everything goes there again
        else:
            st.update(fail=None)          # a new password: the next run tries at once
        st["last"] = None
        _put_state(uid, tid, st)
    what = "Zugang" if login else ("Auslagern an" if t["offload"] else "Auslagern aus") if t["offload"] != old["offload"] else "Bereiche"
    guard.log("storage_change", detail=f"{t['kind']} {what}")
    return _view(uid)


@router.delete("/api/profile/speicher/{tid}")
def remove(tid: str, request: Request, prof=Depends(_on)):
    """Disconnects a target; what lies there stays (the page says so)."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    if (uid, tid) in _running:
        raise HTTPException(409, "Der Abgleich läuft gerade; gleich noch einmal.")
    t = find(uid, tid)
    _keep_away(uid, tid)
    with _lock:
        d = load(uid)
        d["targets"] = [x for x in d["targets"] if x["id"] != tid]
        save(uid, d)
        _put_state(uid, tid, None)
    if t:
        guard.log("storage_remove", detail=t["kind"])
        _event("Profil hat eine Kopie ausgeschaltet")
    return _view(uid)


@router.post("/api/profile/speicher/{tid}/check")
async def check_route(tid: str, request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    _may(prof)
    uid = prof["id"]
    t = find(uid, tid)
    if not t:
        raise HTTPException(404, "no such target")
    key = _key(uid)
    if not key:
        raise HTTPException(409, _say(StoreError("key")))
    try:
        free = await check(t, key)
    except StoreError as e:
        raise HTTPException(502, _say(e))
    st = _state(uid, tid)
    st["free"] = dict(free or {}, t=int(time.time()))
    _put_state(uid, tid, st)
    return _view(uid)


@router.post("/api/profile/speicher/{tid}/now")
async def now_route(tid: str, request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    _may(prof)
    uid = prof["id"]
    if not find(uid, tid):
        raise HTTPException(404, "no such target")
    if (uid, tid) in _running:
        raise HTTPException(409, "Läuft schon.")
    spawn(copy_once(uid, tid, "manual"))
    await asyncio.sleep(0.05)
    return _view(uid)


@router.post("/api/profile/speicher/{tid}/restore")
async def restore_route(tid: str, request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    _may(prof)
    uid = prof["id"]
    if not find(uid, tid):
        raise HTTPException(404, "no such target")
    if (uid, tid) in _running:
        raise HTTPException(409, "Läuft schon.")
    try:
        r = await restore_missing(uid, tid)
    except StoreError as e:
        raise HTTPException(502, _say(e))
    return dict(_view(uid), restored=r)


# ---------------------------------------------------------------- routes (admin)
@router.get("/api/admin/speicher", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "storage", admin=True)
    return overview()
