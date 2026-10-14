"""Wissensordner (plan plaene/synology-bauplan.md, S2; Dominik 2026-10-13 "S1 - S8 umsetzen").

A profile picks folders at one of its places (nas.py: a NAS or cloud connected once) and the Spark finds what is in
them: the files are read into the profile's own document search (documents.py, source "nas"), so document_search,
"Erst lokal" and Ich → Dokumente find them like an upload. Only reading: the Spark never writes, moves or deletes
anything at the place. Originals are not copied; "Öffnen" fetches the file from the place when it is wanted.

    USERS_DIR/<uid>/nasquelle.json        {"sources": [src]}   the profile's folders (Ich → Speicher, nasquelle.js)
    USERS_DIR/<uid>/nasquelle-stand.json  {sid: state}         what was read: per file path hash its path, size,
                                                                time and document id (or why it was left out)
    src = {"id", "nas" (connection id), "path" ("/Dokumente"), "groups" ([GROUPS]), "skip" (sub folders), "added"}

Rules (fixed, never decided by the model):
- What is read: only the kinds of file in the chosen groups (GROUPS, default on: documents, tables, slides, text,
  mails; pictures only on request and with "Bilder und Scans lesen"); never programs, archives, video, music,
  images of disks, databases or backups (everything not in a group). Hidden, system (Synology @eaDir, #recycle,
  #snapshot), lock and temporary files are always left out. The content must fit the name (magic bytes, as an
  upload): a ".pdf" that is no PDF is left out.
- How much: at most MAX_SOURCES folders, MAX_LIST entries looked at per folder, ROUND_FILES files or ROUND_BYTES
  per round (the first round of a big folder spreads over several, one a minute in quiet minutes), and
  chat.nas_max_docs documents from the places per profile (default NAS_DOCS, they do not count against the
  uploads). When a folder holds more than fits, what is read first is fixed (first): documents, tables, slides,
  text and mails before pictures and scans, the newest first; the rest waits until there is room again.
- When: every chat.nas_sources_every minutes (15 to 1440, default 30), only in quiet minutes (vorrang), never
  while an update runs or with Notaus. A file that changed is read again; one that is gone leaves the search.
- Deleting in Ich → Dokumente means "nicht mehr finden": the file is left out until it changes, never deleted
  at the place. Removing a folder takes its documents out of the search.
- Everything read is outside text (documents.py marks it like an upload; document_search is READS_OUTSIDE).
- Connections only through netguard HOME with the place's login (nas.py), its accepted certificate or server key.

Zustand → Live: target "Wissensordner" (live.py "nasquelle", numbers only), job "Wissensordner-Abgleich" of
"Von selbst". Logs → Diagnose, area "NAS" (lines "nasquelle: ..."), only fixed words and numbers, never a path or
a file name.
"""
import asyncio
import email.utils
import hashlib
import json
import os
import re
import secrets
import ssl
import stat
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import netguard
import profiles
import vault
import zertpin
from common import load_config
import core
from core import auth, browser_profile, spawn

router = APIRouter()

MAX_SOURCES = 8
MAX_LIST = 50_000              # entries looked at in one folder per round
LIST_SECS = 120                # the most one look at a folder may take
PREVIEW_SECS = 60
ROUND_FILES = 200
ROUND_BYTES = 1024 ** 3
NAS_DOCS = 5000                # documents from the places per profile (chat.nas_max_docs, 100 to 20000)
EVERY = 30                     # minutes (chat.nas_sources_every, 15 to 1440)
HAUS = "haushalt"              # the Haushaltsordner (S5): its folders, state and documents as if it were a profile
OWNER = re.compile(r"u_[0-9a-f]{12}")
RETRY = (600, 1800, 3600, 7200)
START_GRACE = 180
TIMEOUT = 20
ID = re.compile(r"[0-9a-f]{6}")
DOC = re.compile(r"[0-9a-f]{12}")
SEG_BAD = re.compile(r"[\x00-\x1f\x7f/\\]")
STARTED = time.time()

# the groups a profile may pick: id -> (German, English, endings, on by default)
GROUPS = {
    "dokumente": ("Dokumente", "Documents", (".pdf", ".docx", ".odt", ".html", ".htm"), True),
    "tabellen": ("Tabellen", "Tables", (".xlsx", ".ods", ".csv"), True),
    "praesentationen": ("Präsentationen", "Presentations", (".pptx", ".odp"), True),
    "text": ("Text", "Text", (".txt", ".md"), True),
    "mails": ("Mails", "Mails", (".eml",), True),
    "bilder": ("Bilder und Scans", "Pictures and scans", (".jpg", ".jpeg", ".png", ".webp"), False),
}
# never read, whatever is picked (shown with their reason in the preview)
SKIP_DIRS = re.compile(r"^(?:[.@#].*|\$RECYCLE\.BIN|System Volume Information|lost\+found)$", re.I)
SKIP_FILES = re.compile(r"^(?:\..*|~\$.*|.*\.(?:tmp|part|crdownload|lock|swp)|Thumbs\.db|desktop\.ini)$", re.I)
# why a file was left out (the preview and Ich → Speicher show these words)
WHY_OUT = {"versteckt": ("System- oder versteckte Datei", "system or hidden file"),
           "art": ("Art wird nie gelesen", "kind is never read"),
           "gruppe": ("Gruppe nicht gewählt", "group not picked"),
           "gross": ("zu groß", "too large"),
           "inhalt": ("Inhalt passt nicht zur Endung", "content does not fit the ending"),
           "lesen": ("ließ sich nicht lesen", "could not be read"),
           "aus": ("unter Dokumente ausgenommen", "left out under Documents")}
WHY = {"offline": ("nicht erreichbar", "not reachable"), "auth": ("Anmeldung abgelehnt", "sign-in refused"),
       "cert": ("Zertifikat passt nicht", "certificate does not fit"),
       "hostkey": ("Schlüssel des Servers hat sich geändert", "the server's key changed"),
       "blocked": ("vom Wächter nicht erlaubt", "not allowed by the Wächter"), "notaus": ("Notaus", "kill switch"),
       "missing": ("Ordner nicht gefunden", "folder not found"), "gone": ("Ort entfernt", "place removed"),
       "voll": ("Höchstzahl an Dokumenten erreicht", "most documents reached"),
       "other": ("antwortet nicht wie erwartet", "does not answer as expected")}
_lock = threading.RLock()
_running = set()               # (uid, sid)


class SourceError(Exception):
    def __init__(self, kind, text=""):
        super().__init__(text or kind)
        self.kind = kind if kind in WHY else "other"


# ---------------------------------------------------------------- switches and limits
def _chat():
    return load_config().get("chat", {})


def admin_on(c=None):
    return features.admin_on("nasquelle", c)


def allowed(uid, c=None):
    """Released for this profile (features.py: the place, documents and this switch, not blocked). HAUS: the
    Haushaltsordner is switched on."""
    c = features.chat_cfg() if c is None else c
    if uid == HAUS:
        return haus_on(c)
    return bool(uid) and features.allowed("nasquelle", uid, c) and features.allowed("documents", uid, c)


def haus_on(c=None):
    """The Haushaltsordner is switched on (chat.nas_shared and what it builds on: the place, the Wissensordner)."""
    return features.admin_on("nashaushalt", c)


def haus_find(uid, c=None):
    """This profile finds what is in the Haushaltsordner (released, not blocked, documents too); guests never."""
    c = features.chat_cfg() if c is None else c
    return bool(uid) and uid != HAUS and features.allowed("nashaushalt", uid, c) and features.allowed("documents", uid, c)


def haus_admin(uid, c=None):
    """This profile may choose a Haushaltsordner at one of its own places: an admin profile with Wissensordner."""
    import zustand_wz
    return bool(uid) and uid != HAUS and haus_find(uid, c) and allowed(uid, c) and zustand_wz.is_admin(uid)


def _owner(uid, s):
    """Whose place a folder is at: the profile itself, for the Haushaltsordner the admin profile that chose it."""
    return s.get("owner", "") if uid == HAUS else uid


def _pictures(uid):
    import wissen
    return wissen.on(uid, "pictures")


def _int(key, default, lo, hi):
    v = _chat().get(key, default)
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else default


def max_docs():
    return _int("nas_max_docs", NAS_DOCS, 100, 20000)


def every():
    return _int("nas_sources_every", EVERY, 15, 1440) * 60


# ---------------------------------------------------------------- files of a profile
def _file(uid):
    return profiles._path(uid, "nasquelle.json")


def _state_file(uid):
    return profiles._path(uid, "nasquelle-stand.json")


def _json(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_path(v):
    """A folder at the place: "/a/b" (no "..", no control characters), "" = the place's own folder."""
    v = str(v or "").strip().replace("\\", "/")
    parts = [p for p in v.split("/") if p]
    if len(v) > 500 or any(p in (".", "..") or SEG_BAD.search(p) or len(p) > 255 for p in parts):
        raise ValueError("bad folder")
    return "/" + "/".join(parts) if parts else ""


def clean_rel(v):
    v = clean_path(v)
    return v[1:]


def _clean(s):
    if not isinstance(s, dict) or not ID.fullmatch(str(s.get("id", ""))) or not ID.fullmatch(str(s.get("nas", ""))):
        return None
    try:
        path = clean_path(s.get("path"))
        skip = sorted({clean_rel(x) for x in s.get("skip") or [] if isinstance(x, str) and x.strip()})[:50]
    except ValueError:
        return None
    groups = [g for g in GROUPS if g in (s.get("groups") or [])]
    out = {"id": s["id"], "nas": s["nas"], "path": path, "groups": groups or [g for g, v in GROUPS.items() if v[3]],
           "skip": [x for x in skip if x], "added": int(s.get("added") or 0)}
    if OWNER.fullmatch(str(s.get("owner", ""))):
        out["owner"] = s["owner"]
    return out


def sources(uid):
    with _lock:
        raw = _json(_file(uid)).get("sources")
    return [x for x in (_clean(s) for s in raw if isinstance(raw, list)) if x][:MAX_SOURCES] if isinstance(raw, list) else []


def _save(uid, items):
    with _lock:
        profiles._write(_file(uid), {"sources": items})


def find(uid, sid):
    return next((s for s in sources(uid) if s["id"] == sid), None)


def _states(uid):
    with _lock:
        return _json(_state_file(uid))


def state(uid, sid):
    st = _states(uid).get(sid)
    st = st if isinstance(st, dict) else {}
    files = st.get("files") if isinstance(st.get("files"), dict) else {}
    return {"files": files, "last": st.get("last") if isinstance(st.get("last"), dict) else None,
            "fail": st.get("fail") if isinstance(st.get("fail"), dict) else None,
            "left": int(st.get("left") or 0), "seen": int(st.get("seen") or 0),
            "out": st.get("out") if isinstance(st.get("out"), dict) else {}}


def _put_state(uid, sid, st):
    with _lock:
        all_ = _states(uid)
        if st is None:
            all_.pop(sid, None)
        else:
            all_[sid] = st
        profiles._write(_state_file(uid), all_)


def _hash(sid, rel):
    return hashlib.sha256(f"{sid}\0{rel}".encode()).hexdigest()[:16]


def uses(uid):
    """For nas.uses: {connection id: number of folders}, the Haushaltsordner at this profile's places too."""
    out = {}
    for s in sources(uid) + [s for s in sources(HAUS) if uid and s.get("owner") == uid]:
        out[s["nas"]] = out.get(s["nas"], 0) + 1
    return out


# ---------------------------------------------------------------- what is read
def group_of(name):
    ext = os.path.splitext(name.lower())[1]
    return next((g for g, v in GROUPS.items() if ext in v[2]), None)


def classify(rel, size, groups, pictures=False):
    """None when the file is read, else the reason it is left out (WHY_OUT)."""
    parts = rel.split("/")
    if any(SKIP_DIRS.match(p) for p in parts[:-1]) or SKIP_FILES.match(parts[-1]):
        return "versteckt"
    g = group_of(parts[-1])
    if not g:
        return "art"
    if g not in groups or (g == "bilder" and not pictures):
        return "gruppe"
    import documents
    import wissen
    most = wissen.pdf_bytes() if parts[-1].lower().endswith(".pdf") else documents.MAX_OTHER
    if size > most:
        return "gross"
    return None


def fits(name, head):
    """The content fits the ending (magic bytes, like an upload): the first bytes of the file."""
    ext = os.path.splitext(name.lower())[1]
    if ext == ".pdf":
        return head[:1024].lstrip().startswith(b"%PDF")
    if ext in (".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"):
        return head.startswith(b"PK\x03\x04")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return b"\0" not in head[:4096]    # text: no NUL bytes


# ---------------------------------------------------------------- reading a place
def _seg_ok(name):
    return bool(name) and name not in (".", "..") and len(name) <= 255 and not SEG_BAD.search(name)


class _Dav:
    """A WebDAV folder, only PROPFIND and GET (the place's login only for its own address)."""

    def __init__(self, c, path):
        self.root = c["url"]
        self.base = c["url"] + quote(path or "")
        pw = vault.open_(c["password"]) or "" if c.get("password") else ""
        self.auth = (c["user"], pw) if c.get("user") else None
        self.cert = c.get("cert") or ""
        self.level = netguard.HOME

    def _client(self, timeout, most):
        return netguard.client(self.level, origin=self.root + "/", max_bytes=most, timeout=httpx.Timeout(timeout, connect=10),
                               verify=zertpin.verify(self.cert))

    def _err(self, e):
        if isinstance(e, netguard.Blocked):
            return SourceError("notaus" if "Notaus" in str(e) else "blocked")
        if isinstance(e, (httpx.ConnectError, httpx.TimeoutException, OSError, ssl.SSLError)):
            return SourceError("cert" if zertpin.problem(e) else "offline", type(e).__name__)
        return SourceError("cert" if zertpin.problem(e) else "other", type(e).__name__)

    @staticmethod
    def _code(code):
        if code in (401, 403):
            return SourceError("auth", f"HTTP {code}")
        if code == 404:
            return SourceError("missing", "HTTP 404")
        return SourceError("offline" if code in (502, 503, 504) else "other", f"HTTP {code}")

    async def list(self, rel):
        """[(name, is folder, size, time)] of one folder."""
        url = self.base + "/" + quote(rel) + "/" if rel else self.base + "/"
        body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:getcontentlength/>'
                b'<d:getlastmodified/></d:prop></d:propfind>')
        try:
            async with self._client(TIMEOUT, 8 * 1024 * 1024) as cl:
                r = await cl.request("PROPFIND", url, auth=self.auth, content=body,
                                     headers={"Depth": "1", "Content-Type": "application/xml"})
        except (netguard.Blocked, httpx.HTTPError, OSError, ssl.SSLError, netguard.TooLarge, ValueError) as e:
            raise self._err(e)
        if r.status_code != 207:
            raise self._code(r.status_code)
        return parse_multistatus(r.content, urlsplit(url).path)

    async def get(self, rel, dst, most):
        try:
            async with self._client(60 + most // (512 * 1024), most + 64 * 1024) as cl:
                async with cl.stream("GET", self.base + "/" + quote(rel), auth=self.auth) as r:
                    if r.status_code != 200:
                        raise self._code(r.status_code)
                    got = 0
                    with open(dst, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            got += len(chunk)
                            if got > most:
                                raise SourceError("other", "too large")
                            f.write(chunk)
        except SourceError:
            raise
        except (netguard.Blocked, httpx.HTTPError, OSError, ssl.SSLError, netguard.TooLarge, ValueError) as e:
            raise self._err(e)

    async def close(self):
        pass


def parse_multistatus(raw, own_path):
    """The entries of a PROPFIND answer (outside data: no DTD or entities, names checked, sizes as numbers)."""
    if len(raw) > 8 * 1024 * 1024 or b"<!DOCTYPE" in raw[:4096].upper() or b"<!ENTITY" in raw.upper():
        raise SourceError("other", "bad listing")
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError:
        raise SourceError("other", "bad listing")
    ns = "{DAV:}"
    own = unquote(own_path).rstrip("/")
    out = []
    for resp in tree.iter(ns + "response"):
        href = resp.findtext(ns + "href") or ""
        path = unquote(urlsplit(href).path).rstrip("/")
        if path == own or not path.startswith(own + "/"):
            continue
        name = path[len(own) + 1:]
        if "/" in name or not _seg_ok(name):
            continue
        isdir = resp.find(f".//{ns}resourcetype/{ns}collection") is not None
        size = resp.findtext(f".//{ns}getcontentlength") or "0"
        size = int(size) if size.strip().isdigit() and len(size.strip()) < 16 else 0
        when = resp.findtext(f".//{ns}getlastmodified") or ""
        try:
            mtime = int(email.utils.parsedate_to_datetime(when).timestamp()) if when else 0
        except (TypeError, ValueError, IndexError, OverflowError):
            mtime = 0
        out.append((name, isdir, size, mtime))
    return out


def _remote(c, path):
    """SFTP or SMB at a place: the drivers of speicher.py, but on the chosen folder and only for reading."""
    import speicher
    t = {"url": c["url"] + (path or "/"), "user": c["user"], "password": c["password"], "hostkey": c.get("hostkey", "")}
    base = speicher.Sftp if c["kind"] == "sftp" else speicher.Smb

    class Reader(base):
        def __init__(self):
            super().__init__(t, b"\0" * 32)
            self.level = netguard.HOME
            self.base = self.top

        def _at(self, rel):
            return self._join(self.base, *[p for p in rel.split("/") if p]) if rel else self.base

        def _ls(self, rel):
            p = self._at(rel)
            out = []
            if c["kind"] == "sftp":
                for a in self.conn[1].listdir_attr(p):
                    if _seg_ok(a.filename):
                        out.append((a.filename, stat.S_ISDIR(a.st_mode or 0), int(a.st_size or 0), int(a.st_mtime or 0)))
            else:
                import smbclient
                for e in smbclient.scandir(p, **self._kw()):
                    if _seg_ok(e.name):
                        st = e.stat()
                        out.append((e.name, e.is_dir(), int(st.st_size), int(st.st_mtime)))
            return out

        async def list(self, rel):
            try:
                return await self._run(self._ls, rel)
            except speicher.StoreError as e:
                raise SourceError(e.kind if e.kind in WHY else ("missing" if str(e) == "missing" else "other"))

        async def get(self, rel, dst, most):
            def copy():
                src = self._at(rel)
                if self._size(src) > most:
                    raise speicher.StoreError("other", "too large")
                got = 0
                with self._open(src, "rb") as a, open(dst, "wb") as b:
                    while chunk := a.read(1 << 20):
                        got += len(chunk)
                        if got > most:
                            raise speicher.StoreError("other", "too large")
                        b.write(chunk)
            try:
                await self._run(copy, timeout=60 + most // (512 * 1024))
            except speicher.StoreError as e:
                raise SourceError(e.kind if e.kind in WHY else "other")
    return Reader()


def reader(c, path):
    return _Dav(c, path) if c["kind"] == "webdav" else _remote(c, path)


def _conn(uid, nid):
    import nas
    c = nas.find(uid, nid)
    if not c:
        raise SourceError("gone")
    return c


def first(item):
    """The order files are read in (Dominik 2026-10-14: what gets in when a folder holds more than the limit):
    every group before pictures and scans, then the newest first. item = (rel, size, mtime)."""
    m = item[2] if isinstance(item[2], (int, float)) else 0
    return (group_of(item[0]) == "bilder", -m)


def plan(n, size, room):
    """For the preview: of n files (size bytes) how many fit, how many stay out, and in how many rounds."""
    read = max(0, min(n, room))
    part = size * read // n if n else 0
    return {"read": read, "left_out": n - read,
            "rounds": max(1, -(-read // ROUND_FILES), -(-part // ROUND_BYTES)) if read else 0}


async def walk(rd, skip=(), most=MAX_LIST, secs=LIST_SECS):
    """Every file below the folder: ([(rel, size, time)], {"versteckt": n} folders left out, complete)."""
    t_end = time.monotonic() + secs
    todo, files, out, seen = [""], [], {}, 0
    skip = tuple(skip)
    while todo:
        rel = todo.pop()
        if time.monotonic() > t_end or seen >= most:
            return files, out, False
        for name, isdir, size, mtime in await rd.list(rel):
            seen += 1
            sub = f"{rel}/{name}" if rel else name
            if isdir:
                if SKIP_DIRS.match(name):
                    out["versteckt"] = out.get("versteckt", 0) + 1
                elif not any(sub == s or sub.startswith(s + "/") for s in skip):
                    todo.append(sub)
            else:
                files.append((sub, size, mtime))
    return files, out, True


# ---------------------------------------------------------------- one round
def _tmp_dir():
    return os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "nasquelle-tmp")


def _tmp():
    """A temp file only the panel can read (never /tmp: plain profile data passes there)."""
    d = _tmp_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, p = tempfile.mkstemp(prefix="nq-", dir=d)
    os.close(fd)
    return p


def clean_tmp():
    """At start: what a round cut off by a restart left behind."""
    try:
        for n in os.listdir(_tmp_dir()):
            if n.startswith("nq-"):
                _rm(os.path.join(_tmp_dir(), n))
    except OSError:
        pass


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _log_name(uid):
    return "haushalt" if uid == HAUS else profiles.log_name(profiles.by_id(uid))


def _live(name, *a, **kw):
    try:
        import live
        getattr(live, name)(*a, **kw)
    except Exception as e:   # noqa: BLE001 - the overview never stops the work
        print("nasquelle: live", type(e).__name__, flush=True)


def nas_docs(uid):
    import documents
    return documents.count_source(uid, "nas")


async def _read_one(uid, s, rd, rel, size, pictures):
    """Fetches one file and stores it as a document: (doc id, None) or ("", reason)."""
    import doclingdienst
    import documents
    import wissen
    name = rel.split("/")[-1]
    most = wissen.pdf_bytes() if name.lower().endswith(".pdf") else documents.MAX_OTHER
    tmp = _tmp()
    try:
        await rd.get(rel, tmp, most)
        with open(tmp, "rb") as f:
            data = f.read(most + 1)
    finally:
        _rm(tmp)
    if not fits(name, data[:4096]):
        return "", "inhalt"
    try:
        got = await asyncio.to_thread(lambda: documents.add(uid, name, data, pictures=pictures, keep=0, source="nas", most=most,
                                                            docling=uid != HAUS and doclingdienst.wanted(uid, name, None), limit=max_docs()))
    except ValueError:
        return "", "lesen"
    folder = s["path"] + "/" + "/".join(rel.split("/")[:-1]) if "/" in rel else s["path"]
    await asyncio.to_thread(documents.set_place, uid, got["id"], f"{s['id']}:{_hash(s['id'], rel)}", folder or "/")
    if uid == HAUS:     # the Haushaltsordner's documents are for every profile that may find them (wissen._sharers)
        await asyncio.to_thread(documents.set_shared, HAUS, got["id"], True)
    return got["id"], None


def _drop(uid, doc):
    if doc and DOC.fullmatch(doc):
        import documents
        documents.delete(uid, doc)


def due(uid, s, st, now=None):
    now = now or time.time()
    if (uid, s["id"]) in _running:
        return False
    last = int((st["last"] or {}).get("t") or 0)
    if st["left"]:
        return now - last > 60                     # the first rounds of a big folder follow each other
    if st["fail"]:
        if st["fail"].get("kind") in ("auth", "cert", "hostkey", "gone"):
            return now - last > RETRY[-1]
        return now - last > RETRY[min(len(RETRY), int(st["fail"].get("n") or 1)) - 1]
    return now - last > every()


async def sync_once(uid, sid, why="auto", now=None):
    """One comparison of one folder. Returns {"ok", "new", "gone", "left"} or {"ok": False, "kind"}."""
    s = find(uid, sid)
    if not s or (uid, sid) in _running:
        return {"ok": False, "kind": "other"}
    _running.add((uid, sid))
    now = now or time.time()
    t0 = time.time()
    st = state(uid, sid)
    _live("bg", "Wissensordner-Abgleich", "läuft")
    rd = None
    try:
        pictures = _pictures(uid)
        if uid == HAUS:
            import zustand_wz
            if not zustand_wz.is_admin(_owner(uid, s)):    # only an admin's place serves the whole household
                raise SourceError("gone")
        c = _conn(_owner(uid, s), s["nas"])
        rd = reader(c, s["path"])
        files, out, complete = await walk(rd, s["skip"])
        have = st["files"]
        now_set = {}
        for rel, size, mtime in files:
            h = _hash(sid, rel)
            reason = classify(rel, size, s["groups"], pictures)
            if reason:
                out[reason] = out.get(reason, 0) + 1
                if h in have and have[h].get("d"):
                    _drop(uid, have[h]["d"])                     # the group was taken away: out of the search
                continue
            now_set[h] = (rel, size, mtime)
        gone = 0
        if complete:
            for h in [h for h in have if h not in now_set]:
                _drop(uid, have[h].get("d"))
                have.pop(h, None)
                gone += 1
        todo = [(h, x) for h, x in now_set.items()
                if h not in have or (have[h].get("s"), have[h].get("m")) != (x[1], x[2])]
        todo = [(h, x) for h, x in todo if not (h in have and have[h].get("x") == "aus" and (have[h].get("s"), have[h].get("m")) == (x[1], x[2]))]
        todo.sort(key=lambda hx: first(hx[1]))      # documents before pictures, the newest first (first)
        new, size_sum, full = 0, 0, False
        for h, (rel, size, mtime) in todo:
            if new >= ROUND_FILES or size_sum + size > ROUND_BYTES and new:
                break
            if nas_docs(uid) >= max_docs():
                full = True
                break
            old = have.get(h, {}).get("d")
            try:
                doc, reason = await _read_one(uid, s, rd, rel, size, pictures)
            except SourceError as e:
                if e.kind in ("offline", "auth", "cert", "hostkey", "blocked", "notaus"):
                    raise
                doc, reason = "", "lesen"
            _drop(uid, old)
            have[h] = {"p": rel, "s": size, "m": mtime, "d": doc, "x": reason or ""}
            if reason:
                out[reason] = out.get(reason, 0) + 1
            new += 1
            size_sum += size
            st["files"] = have
            if new % 20 == 0:
                _put_state(uid, sid, dict(st, files=have))
        left = max(0, len(todo) - new)
        st.update(files=have, left=0 if full else left, seen=len(now_set), out=out, fail=None if not full else {"kind": "voll", "since": int(now), "n": 1},
                  last={"t": int(now), "ok": not full, "n": new, "gone": gone, "why": why, "complete": complete})
        _put_state(uid, sid, st)
        print(f"nasquelle: abgeglichen | {new} neu | {gone} weg | {left} übrig | {len(now_set)} im ordner"
              + (" | unvollständig" if not complete else "") + (" | höchstzahl" if full else "")
              + f" | {_log_name(uid)}", flush=True)
        _live("job", "Wissensordner", "Wissensordner-Abgleich", t0, ok=True, uid=uid)
        return {"ok": True, "new": new, "gone": gone, "left": left, "full": full}
    except SourceError as e:
        f = st["fail"] or {}
        st.update(fail={"kind": e.kind, "since": int(f.get("since") or now), "n": int(f.get("n") or 0) + 1},
                  last={"t": int(now), "ok": False, "kind": e.kind, "why": why})
        _put_state(uid, sid, st)
        print(f"nasquelle: fehler | art={e.kind} | {_log_name(uid)}", flush=True)
        _live("job", "Wissensordner", "Wissensordner-Abgleich", t0, ok=False, uid=uid)
        return {"ok": False, "kind": e.kind}
    finally:
        _running.discard((uid, sid))
        _live("bg", "Wissensordner-Abgleich", None)
        if rd is not None:
            await rd.close()


def _paused(now):
    if now - STARTED < START_GRACE:
        return True
    try:
        import update
        if update.update_running():
            return True
    except Exception as e:   # noqa: BLE001
        print("nasquelle: pause", type(e).__name__, flush=True)
    import notaus
    return notaus.level() >= 1


async def round_once(now=None):
    """Every folder that is due, one after another (only in quiet minutes)."""
    now = now or time.time()
    c = features.chat_cfg()
    if not admin_on(c) or _paused(now):
        return []
    import vorrang
    if vorrang.speaking():
        return []
    done = []
    ids = profiles.user_ids()
    for s in sources(HAUS):
        if s.get("owner") not in ids:    # the admin profile whose place it was is gone: so is its Haushaltsordner
            n = remove_source(HAUS, s["id"])
            print(f"nasquelle: haushalt entfernt | besitzer weg | {n} dokumente", flush=True)
    for uid in ids + [HAUS]:
        if not allowed(uid, c):
            continue
        for s in sources(uid):
            if due(uid, s, state(uid, s["id"]), now):
                await sync_once(uid, s["id"], "auto", now)
                done.append((uid, s["id"]))
    return done


async def loop():
    while True:
        await asyncio.sleep(60)
        try:
            await round_once()
        except Exception as e:   # noqa: BLE001 - the next minute tries again
            print("nasquelle: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- for other modules
def excluded(uid, doc_id):
    """A document from a place was deleted in Ich → Dokumente: left out until the file changes (never deleted there)."""
    for s in sources(uid):
        st = state(uid, s["id"])
        for h, x in st["files"].items():
            if x.get("d") == doc_id:
                x.update(d="", x="aus")
                _put_state(uid, s["id"], st)
                print(f"nasquelle: ausgenommen | {_log_name(uid)}", flush=True)
                return True
    return False


def _entry(uid, doc_id):
    for s in sources(uid):
        for h, x in state(uid, s["id"])["files"].items():
            if x.get("d") == doc_id:
                return s, x
    return None, None


async def fetch(uid, doc_id):
    """(temporary path, name, content type) of a document's file, fetched from its place now; None if it is no
    document from a place; SourceError when the place cannot be reached. The caller deletes the file."""
    import documents
    import wissen
    if not DOC.fullmatch(str(doc_id)) or not allowed(uid):
        return None
    s, x = _entry(uid, doc_id)
    if not s:
        return None
    rel = x["p"]
    name = rel.split("/")[-1]
    most = wissen.pdf_bytes() if name.lower().endswith(".pdf") else documents.MAX_OTHER
    rd = reader(_conn(_owner(uid, s), s["nas"]), s["path"])
    tmp = _tmp()
    try:
        await rd.get(rel, tmp, most)
        with open(tmp, "rb") as f:
            ok = fits(name, f.read(4096))
    except SourceError:
        _rm(tmp)
        print(f"nasquelle: öffnen fehlgeschlagen | {_log_name(uid)}", flush=True)
        raise
    finally:
        await rd.close()
    if not ok:
        _rm(tmp)
        print(f"nasquelle: öffnen abgelehnt | inhalt | {_log_name(uid)}", flush=True)
        return None
    print(f"nasquelle: geöffnet | {_log_name(uid)}", flush=True)
    ext = os.path.splitext(name.lower())[1]
    return tmp, name, documents.CTYPE.get(ext, "application/octet-stream")


def summary(uid):
    """(folders, failing, documents) for Ich → Mein Zustand and others."""
    ss = sources(uid)
    return len(ss), sum(1 for s in ss if state(uid, s["id"])["fail"]), nas_docs(uid) if ss else 0


def for_live():
    """Live: how many profiles and folders, documents, failing (numbers only)."""
    if not admin_on():
        return {"on": False}
    profs = folders = bad = docs = 0
    for uid in profiles.user_ids():
        ss = sources(uid)
        if not ss:
            continue
        profs += 1
        folders += len(ss)
        bad += sum(1 for s in ss if state(uid, s["id"])["fail"])
        docs += nas_docs(uid)
    hs = sources(HAUS) if haus_on() else []
    return {"on": True, "profiles": profs, "folders": folders, "bad": bad, "docs": docs,    # the Haushaltsordner apart
            "haus_folders": len(hs), "haus_bad": sum(1 for s in hs if state(HAUS, s["id"])["fail"]), "haus_docs": nas_docs(HAUS) if hs else 0}


def probes():
    """For the Dienst-Wächter: the places with a folder of a profile that may use it (no login)."""
    out = {}
    if not admin_on():
        return out
    import nas
    for uid in profiles.user_ids() + [HAUS]:
        if not allowed(uid):
            continue
        for s in sources(uid):
            c = nas.find(_owner(uid, s), s["nas"])
            if not c:
                continue
            u = urlsplit(c["url"])
            k = hashlib.sha256(f"{u.scheme}://{u.netloc}".encode()).hexdigest()[:8]
            if c["kind"] == "webdav":
                p = {"url": f"{u.scheme}://{u.netloc}/", "level": netguard.HOME, "verify": True, "pin": c.get("cert") or ""}
            else:
                p = {"tcp": True, "host": (u.hostname or "").lower(), "port": u.port or (22 if c["kind"] == "sftp" else 445),
                     "level": netguard.HOME, "ssh": c["kind"] == "sftp"}
            out.setdefault(k, dict(p, uids=[]))["uids"].append(uid)
    return out


def overview():
    """Zustand (admin): per profile folders, state and numbers, never a path or a name."""
    rows = []
    names = dict({p["id"]: p["name"] for p in profiles.names()}, **{HAUS: "Haushalt"})
    for uid in profiles.user_ids() + [HAUS]:
        for s in sources(uid):
            st = state(uid, s["id"])
            rows.append({"profile": names.get(uid, "?"), "haus": uid == HAUS, "files": sum(1 for x in st["files"].values() if x.get("d")),
                         "left": st["left"], "fail": (st["fail"] or {}).get("kind", ""), "last": (st["last"] or {}).get("t", 0)})
    return {"on": admin_on(), "rows": rows}


# ---------------------------------------------------------------- views
def public(uid, s, st=None):
    st = st or state(uid, s["id"])
    return {"id": s["id"], "nas": s["nas"], "path": s["path"] or "/", "groups": s["groups"], "skip": s["skip"],
            "added": s["added"], "docs": sum(1 for x in st["files"].values() if x.get("d")), "seen": st["seen"],
            "left": st["left"], "out": st["out"], "last": st["last"], "fail": st["fail"],
            "running": (uid, s["id"]) in _running}


def _view(uid):
    mine = [s for s in sources(HAUS) if s.get("owner") == uid]
    return {"admin": admin_on(), "on": allowed(uid), "why": features.reason("nasquelle", uid), "max": MAX_SOURCES,
            "pictures": _pictures(uid), "docs": nas_docs(uid), "max_docs": max_docs(),
            # the Haushaltsordner this admin profile chose at its places (S5); "may": it can choose one
            "haus": {"may": haus_admin(uid), "pictures": _pictures(HAUS), "docs": nas_docs(HAUS) if mine else 0,
                     "max": MAX_SOURCES, "count": len(sources(HAUS)), "sources": [public(HAUS, s) for s in mine]},
            "groups": [{"id": g, "name": [v[0], v[1]], "ends": list(v[2]), "on": v[3]} for g, v in GROUPS.items()],
            "out_words": {k: list(v) for k, v in WHY_OUT.items()}, "why_words": {k: list(v) for k, v in WHY.items()},
            "sources": [public(uid, s) for s in sources(uid)]}


# ---------------------------------------------------------------- routes (profile)
def _on(prof=Depends(browser_profile)):
    """Only the profile's own browser login, never a device key."""
    if not admin_on():
        raise HTTPException(403, "Wissensordner sind ausgeschaltet.")
    if not allowed(prof["id"]):
        raise HTTPException(403, "Wissensordner sind für dieses Profil nicht frei.")
    return prof


def _say(kind):
    return {"offline": "Der Ort antwortet nicht (Adresse, Netz oder NAS aus?).",
            "auth": "Der Ort lehnt die Anmeldung ab: beim Ort „Anmeldung ändern“.",
            "cert": "Das Zertifikat des Orts hat sich geändert: beim Ort „Verbindung prüfen“.",
            "hostkey": "Der Schlüssel des Servers ist ein anderer: beim Ort „Anmeldung ändern“.",
            "blocked": "Der Wächter erlaubt diese Adresse nicht.", "notaus": "Notaus ist an: keine Verbindung nach außen.",
            "missing": "Diesen Ordner gibt es dort nicht (mehr).", "gone": "Diesen Ort gibt es nicht mehr.",
            "voll": "Die Höchstzahl an Dokumenten von Orten ist erreicht.",
            "other": "Der Ort antwortet nicht wie erwartet."}.get(kind, "Fehler")


def _groups(v):
    if v is None:
        return [g for g, x in GROUPS.items() if x[3]]
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise HTTPException(400, "groups: a list")
    g = [x for x in GROUPS if x in v]
    if not g:
        raise HTTPException(400, "Mindestens eine Gruppe wählen.")
    return g


def _skip(v):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > 50:
        raise HTTPException(400, "skip: up to 50 folders")
    try:
        return sorted({clean_rel(x) for x in v if isinstance(x, str) and x.strip()} - {""})
    except ValueError:
        raise HTTPException(400, "invalid folder")


def _store(uid, sid, setting=True):
    """(uid or HAUS) whose folder sid is: the profile's own, or the Haushaltsordner it chose (changing and reading
    that needs haus_admin; removing it stays possible, it is at the profile's own place)."""
    if find(uid, sid):
        return uid
    s = find(HAUS, sid)
    if s and s.get("owner") == uid and (not setting or haus_admin(uid)):
        return HAUS
    raise HTTPException(404, "no such folder")


def _want_haus(uid, body):
    """{"haus": true}: the folder is for the whole household (S5), only for an admin profile that may choose one."""
    if body.get("haus") is not True:
        return uid
    if not haus_admin(uid):
        raise HTTPException(403, "Den Haushaltsordner wählt nur ein Admin-Profil, wenn der Admin ihn freigegeben hat.")
    return HAUS


def _place(uid, nid):
    import nas
    if not ID.fullmatch(str(nid or "")) or not nas.find(uid, nid):
        raise HTTPException(404, "no such place")
    return nas.find(uid, nid)


def _path(v, c=None):
    try:
        p = clean_path(v)
    except ValueError:
        raise HTTPException(400, "invalid folder")
    if c is not None and c["kind"] == "smb" and not p:
        raise HTTPException(400, "Bei SMB zuerst die Freigabe angeben, z. B. /home.")
    return p


@router.get("/api/profile/nasquelle")
def get_mine(request: Request, prof=Depends(browser_profile)):
    """Also when switched off or blocked: own folders stay visible and can be removed."""
    guard.limit(request, "storage", prof["id"])
    return _view(prof["id"])


@router.get("/api/profile/nasquelle/tree")
async def tree(request: Request, nas: str = "", path: str = "", prof=Depends(_on)):
    """The sub folders of one folder at a place (one level; the page opens the next on a tap)."""
    guard.limit(request, "storage", prof["id"])
    c = _place(prof["id"], nas)
    path = _path(path, c)
    rd = reader(c, path)
    try:
        items = await asyncio.wait_for(rd.list(""), TIMEOUT + 5)
    except SourceError as e:
        print(f"nasquelle: ordnerliste fehler | art={e.kind} | {_log_name(prof['id'])}", flush=True)
        raise HTTPException(502, _say(e.kind))
    except asyncio.TimeoutError:
        print(f"nasquelle: ordnerliste fehler | art=offline | {_log_name(prof['id'])}", flush=True)
        raise HTTPException(502, _say("offline"))
    finally:
        await rd.close()
    dirs = sorted((n for n, d, _, _ in items if d and not SKIP_DIRS.match(n)), key=str.lower)
    files = sum(1 for _, d, _, _ in items if not d)
    print(f"nasquelle: ordnerliste | {len(dirs)} ordner | {_log_name(prof['id'])}", flush=True)
    return {"path": path or "/", "dirs": dirs[:500], "more": len(dirs) > 500, "files": files}


@router.post("/api/profile/nasquelle/preview")
async def preview(request: Request, prof=Depends(_on)):
    """{"nas", "path", "groups", "skip"}: what would be read (numbers per group, left out with reason, size)."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    body = await core.json_body(request, 8192, lenient=True)
    who = _want_haus(uid, body)
    c = _place(uid, body.get("nas"))
    path, groups, skip = _path(body.get("path"), c), _groups(body.get("groups")), _skip(body.get("skip"))
    rd = reader(c, path)
    try:
        files, out, complete = await walk(rd, skip, MAX_LIST, PREVIEW_SECS)
    except SourceError as e:
        print(f"nasquelle: vorschau fehler | art={e.kind} | {_log_name(uid)}", flush=True)
        raise HTTPException(502, _say(e.kind))
    finally:
        await rd.close()
    pictures = _pictures(who)
    per, size = {}, 0
    for rel, sz, _ in files:
        reason = classify(rel, sz, groups, pictures)
        if reason:
            out[reason] = out.get(reason, 0) + 1
        else:
            g = group_of(rel)
            per[g] = per.get(g, 0) + 1
            size += sz
    n = sum(per.values())
    room = max(0, max_docs() - nas_docs(who))
    print(f"nasquelle: vorschau | {n} dateien | {_log_name(uid)}" + (" | haushalt" if who == HAUS else ""), flush=True)
    return dict({"files": n, "groups": per, "out": out, "bytes": size, "complete": complete, "seen_most": MAX_LIST,
                 "every": every() // 60, "room": room, "limit": max_docs()}, **plan(n, size, room))


@router.post("/api/profile/nasquelle")
async def add(request: Request, prof=Depends(_on)):
    """{"nas", "path", "groups", "skip"}: a new folder; the first round starts at once."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    body = await core.json_body(request, 8192, lenient=True)
    c = _place(uid, body.get("nas"))
    path, groups, skip = _path(body.get("path"), c), _groups(body.get("groups")), _skip(body.get("skip"))
    who = _want_haus(uid, body)
    items = sources(who)
    if len(items) >= MAX_SOURCES:
        raise HTTPException(400, f"Höchstens {MAX_SOURCES} Wissensordner.")
    if any(s["nas"] == c["id"] and s["path"] == path for s in items):
        raise HTTPException(409, "Diesen Ordner gibt es schon.")
    rd = reader(c, path)
    try:
        await asyncio.wait_for(rd.list(""), TIMEOUT + 5)     # it is there and can be read
    except SourceError as e:
        print(f"nasquelle: hinzufügen fehler | art={e.kind} | {_log_name(uid)}", flush=True)
        raise HTTPException(502, _say(e.kind))
    except asyncio.TimeoutError:
        print(f"nasquelle: hinzufügen fehler | art=offline | {_log_name(uid)}", flush=True)
        raise HTTPException(502, _say("offline"))
    finally:
        await rd.close()
    sid = secrets.token_hex(3)
    while any(s["id"] == sid for s in items):
        sid = secrets.token_hex(3)
    while find(uid if who == HAUS else HAUS, sid):      # ids stay unique over the profile and the household
        sid = secrets.token_hex(3)
    item = {"id": sid, "nas": c["id"], "path": path, "groups": groups, "skip": skip, "added": int(time.time())}
    if who == HAUS:
        item["owner"] = uid
    items.append(item)
    _save(who, items)
    guard.log("nasquelle_add", detail=c["kind"] + (" haushalt" if who == HAUS else ""))
    print(f"nasquelle: hinzugefügt | art={c['kind']} | {_log_name(uid)}" + (" | haushalt" if who == HAUS else ""), flush=True)
    spawn(sync_once(who, sid, "add"))
    return {"ok": True, "added": sid}


@router.put("/api/profile/nasquelle/{sid}")
async def change(sid: str, request: Request, prof=Depends(_on)):
    """{"groups"?, "skip"?}: what is read from this folder; the next round follows it."""
    guard.limit(request, "storage", prof["id"])
    uid = _store(prof["id"], sid)
    body = await core.json_body(request, 8192, lenient=True)
    items = sources(uid)
    s = next((x for x in items if x["id"] == sid), None)
    if not s:
        raise HTTPException(404, "no such folder")
    if "groups" in body:
        s["groups"] = _groups(body["groups"])
    if "skip" in body:
        s["skip"] = _skip(body["skip"])
        st = state(uid, sid)          # files below a folder now skipped leave the search at once
        for h, x in list(st["files"].items()):
            if any(x.get("p", "") == k or x.get("p", "").startswith(k + "/") for k in s["skip"]):
                _drop(uid, x.get("d"))
                st["files"].pop(h, None)
        _put_state(uid, sid, st)
    _save(uid, items)
    st = state(uid, sid)
    st["last"] = None                 # due again at once
    _put_state(uid, sid, st)
    guard.log("nasquelle_change")
    print(f"nasquelle: geändert | {_log_name(prof['id'])}" + (" | haushalt" if uid == HAUS else ""), flush=True)
    return {"ok": True}


@router.delete("/api/profile/nasquelle/{sid}")
def remove(sid: str, request: Request, prof=Depends(browser_profile)):
    """The folder and its documents leave the search (nothing changes at the place). Also when blocked: own data."""
    guard.limit(request, "storage", prof["id"])
    uid = _store(prof["id"], sid, setting=False)
    n = remove_source(uid, sid)
    guard.log("nasquelle_remove", detail=str(n))
    print(f"nasquelle: entfernt | {n} dokumente | {_log_name(prof['id'])}" + (" | haushalt" if uid == HAUS else ""), flush=True)
    return {"ok": True, "removed": n}


def remove_source(uid, sid):
    st = state(uid, sid)
    n = 0
    for x in st["files"].values():
        if x.get("d"):
            _drop(uid, x["d"])
            n += 1
    _put_state(uid, sid, None)
    _save(uid, [s for s in sources(uid) if s["id"] != sid])
    return n


def _clear(uid):
    for s in sources(uid):
        remove_source(uid, s["id"])


# own data for Ich while the admin blocks the knowledge folders for the profile (features.OWN): its folders (their
# documents leave the search, nothing changes at the place)
features.OWN["nasquelle"] = (lambda uid: len(sources(uid)), _clear)


@router.post("/api/profile/nasquelle/{sid}/now")
async def now_route(sid: str, request: Request, prof=Depends(_on)):
    guard.limit(request, "storagenow", prof["id"])
    uid = _store(prof["id"], sid)
    if (uid, sid) in _running:
        raise HTTPException(409, "Der Abgleich läuft schon.")
    got = await sync_once(uid, sid, "now")
    if not got.get("ok"):
        raise HTTPException(502, _say(got.get("kind", "other")))
    return got


@router.get("/api/admin/nasquelle", dependencies=[Depends(auth)])
def admin_get():
    return overview()


import nas  # noqa: E402 - registers the folders as a use of their place (nas.uses: no removing while used)
nas.USES["wissen"] = uses
