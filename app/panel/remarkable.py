"""reMarkable notebooks as knowledge (V01.0.270, plan plaene/remarkable.md).

A profile connects its own my.remarkable account (reMarkable 2, Paper Pro, Paper Pro Move) with a one-time
code from my.remarkable.com, like reMarkable's desktop app does. There is no official interface: this
uses the same sync protocol ("sync15") as rmapi, the Obsidian plugin and remarkable-mcp (MIT, used as a
model). reMarkable can change it; "Verbindung prüfen" then says so, uploading a PDF stays as a way.

- Off until the admin allows it (Funktionen: chat.remarkable below "Bilder und Scans lesen"); released, it works
  for every profile the admin did not block (chat.deny); guests never. The long-lived device token is sealed in the vault
  (users/<p>/remarkable.json), the short-lived user token lives in memory only; neither is ever logged.
- Only what the person picks (notebooks or folders; nothing by default) is read: typed text and text
  highlights come straight from the page files, handwriting is drawn from the strokes as a picture and
  read once by the language model in quiet minutes (wissen.py, its daily limit and night window). Each
  notebook becomes one document in users/<p>/wissen.db (source "remarkable"), so the document search,
  the meaning search, the "Steckbrief" and "Erst lokal suchen" use it. Everything read is outside text.
- Every SYNC_EVERY seconds, only while nobody talks (vorrang.py), the account is compared: unchanged
  pages are kept (hash per page), changed ones are read again, notebooks gone from the cloud or no
  longer picked disappear from the Spark.
- Reading never changes the cloud. Writing happens only for "Aufs reMarkable schicken" (chat.remarkable_send,
  also off): an answer or a dictated note as a new EPUB in the folder "Spark"; existing
  documents are never changed, moved or deleted.

Connections go through netguard (PUBLIC) to the fixed reMarkable hosts only (ALLOWED); redirects are
followed by hand and only to these hosts; the login header only goes to the host it was made for.
Answers have a byte cap, page files a size cap, parsing runs off the event loop.

    GET    /api/profile/remarkable          state, library with what is picked (own login)
    POST   /api/profile/remarkable/pair     {"code"}  connect (browser login, fresh code with MFA)
    DELETE /api/profile/remarkable          disconnect: token and all notebooks gone from the Spark
    PUT    /api/profile/remarkable/pick     {"ids": [...], "all": bool}  what is read
    POST   /api/profile/remarkable/sync     compare now (also refreshes the library)
    POST   /api/profile/remarkable/send     {"title", "text"}  an answer onto the reMarkable (rmsend)
"""
import asyncio
import base64
import hashlib
import html
import io
import json
import logging
import os
import re
import struct
import time
import uuid
import zipfile
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import documents
import features
import guard
import hintergrund
import netguard
import notaus
import profiles
import vault
import vorrang
from core import assistant, browser_profile, secret_profile
from textnorm import plain_markdown

router = APIRouter()

AUTH_HOST = "https://webapp-prod.cloud.remarkable.engineering"
DEVICE_URL = AUTH_HOST + "/token/json/2/device/new"
USER_URL = AUTH_HOST + "/token/json/2/user/new"
SYNC_HOST = "https://internal.cloud.remarkable.com"
ROOT_URL = SYNC_HOST + "/sync/v4/root"
ROOT_PUT_URL = SYNC_HOST + "/sync/v3/root"
FILES_URL = SYNC_HOST + "/sync/v3/files/"
CONNECT_URL = "https://my.remarkable.com/pair"
ALLOWED = (".remarkable.com", ".remarkable.engineering", "storage.googleapis.com")

CODE = re.compile(r"[a-z]{8}")
HASH = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
MAX_ENTRIES = 5000          # documents and folders in an account that are looked at
MAX_INDEX = 2 * 1024**2     # an index file
MAX_META = 1024**2          # .metadata / .content
MAX_PAGE = 20 * 1024**2     # one page file (.rm)
MAX_PAGES = 500             # pages per notebook
MAX_PICKED = 300            # picked notebooks and folders
MAX_RUN_PAGES = 300         # page files fetched in one comparison (the rest follows soon after)
MAX_POINTS = 2_000_000      # stroke points drawn per page
SYNC_EVERY = 1800
SOON = 120                  # next comparison when one was cut short
PEEK = 180                  # in between: one small look at the account's root every 3 minutes; changed -> compare now
TIMEOUT = httpx.Timeout(60, connect=10)
CONCURRENT = 6
SEND_DAY = 20               # uploads per profile and day
MAX_SEND = 60_000           # characters of one upload
MAX_FILE = 30 * 1024**2     # one EPUB or PDF (a web page, a mail attachment)
AUTO_DAY = 30               # documents the Spark makes itself per profile and day (rmplus.py)
SIDE = documents.SIDE
_user = {}                  # uid -> (user token, until)
_busy = set()               # profiles being compared right now
_progress = {}              # uid -> [entries read, entries to read] while the list loads
_auto_last = {}             # uid -> when the background comparison last ran (in memory)
_peek_last = {}             # uid -> when the root was last looked at (in memory)
_roots = {}                 # uid -> the root hash the last listing read
BACKGROUND = True           # tests run the listing and the comparison themselves


class CloudError(RuntimeError):
    pass


def _said(r):
    """A short, token-free piece of what the cloud answered, for the error text and the journal."""
    try:
        t = r.text
    except Exception:
        return ""
    return _redact(re.sub(r"\s+", " ", t or "").strip())[:120]


# ---------------------------------------------------------------- switches and state
def allowed(uid):
    return bool(uid) and features.allowed("remarkable", uid)


def send_allowed(uid):
    return bool(uid) and features.allowed("rmsend", uid)


def _file(uid):
    return profiles._path(uid, "remarkable.json")


def _libfile(uid):
    return profiles._path(uid, "remarkable-lib.json")


def _read(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def load(uid):
    d = _read(_file(uid))
    d.setdefault("picked", [])
    d.setdefault("all", False)
    d.setdefault("docs", {})
    return d


def save(uid, d):
    profiles._write(_file(uid), d)


def library(uid):
    return _read(_libfile(uid)).get("items") or {}


def _save_library(uid, items):
    profiles._write(_libfile(uid), {"items": items, "t": int(time.time())})


def device_token(uid):
    return vault.open_(load(uid).get("token", "")) or ""


def _redact(text):
    """Error text without anything that looks like a token."""
    return re.sub(r"[A-Za-z0-9_\-.]{24,}", "…", str(text))[:200]


# ---------------------------------------------------------------- talking to the cloud
def host_ok(url):
    p = urlsplit(url)
    h = (p.hostname or "").lower()
    return p.scheme == "https" and bool(h) and any(h == a.lstrip(".") or h.endswith(a) for a in ALLOWED)


async def _request(method, url, token="", most=MAX_INDEX, headers=None, **kw):
    """One request to the reMarkable hosts, redirects followed by hand (only to ALLOWED, without the
    login header to another host). Returns the httpx response with its body read (at most `most` bytes)."""
    if not host_ok(url):
        raise CloudError("host not allowed")
    origin = url
    for _ in range(4):
        h = dict(headers or {})
        if token and urlsplit(url).hostname == urlsplit(origin).hostname:
            h["Authorization"] = "Bearer " + token
        async with netguard.client(netguard.PUBLIC, origin=origin, max_bytes=most, timeout=TIMEOUT,
                                   follow_redirects=False) as c:
            r = await c.request(method, url, headers=h, **kw)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            if not host_ok(url):
                raise CloudError("redirect to a host that is not allowed")
            if r.status_code == 303:
                method, kw = "GET", {}
            continue
        return r
    raise CloudError("too many redirects")


async def register(code):
    """The long-lived device token for a one-time code from my.remarkable.com."""
    code = str(code or "").strip().lower()
    if not CODE.fullmatch(code):
        raise ValueError("Der Code hat acht Buchstaben (my.remarkable.com → Gerät verbinden).")
    body = {"code": code, "deviceDesc": "desktop-linux", "deviceID": str(uuid.uuid4())}
    r = await _request("POST", DEVICE_URL, json=body, most=64 * 1024)
    tok = r.text.strip()
    if r.status_code != 200 or not re.fullmatch(r"[A-Za-z0-9_\-.]{20,8000}", tok):
        raise ValueError("reMarkable hat den Code nicht angenommen (abgelaufen, schon benutzt oder vertippt). "
                         "Bitte einen neuen Code holen.")
    return tok


async def user_token(uid, fresh=False):
    have = _user.get(uid)
    if have and not fresh and have[1] > time.time():
        return have[0]
    dev = device_token(uid)
    if not dev:
        raise CloudError("not connected")
    r = await _request("POST", USER_URL, token=dev, most=64 * 1024)
    tok = r.text.strip()
    if r.status_code != 200 or not re.fullmatch(r"[A-Za-z0-9_\-.]{20,8000}", tok):
        raise CloudError(f"reMarkable did not renew the sign-in (HTTP {r.status_code}); connect again")
    _user[uid] = (tok, time.time() + 12 * 3600)
    return tok


BUSY = (429, 500, 502, 503, 504)   # the cloud was briefly busy or asked to slow down: one more try after a pause
BUSY_WAIT = 2                       # (uploads go by hash, the root by generation, so a second try is harmless)
BUSY_WAIT_MAX = 10                  # at most this long when the cloud says Retry-After


def _pause(r):
    try:
        return min(BUSY_WAIT_MAX, max(BUSY_WAIT, int(r.headers.get("retry-after", BUSY_WAIT))))
    except (TypeError, ValueError, AttributeError):
        return BUSY_WAIT


SAFE_WHY = re.compile(r"(file|root|upload|put|send) HTTP \d{3}|bad hash|not connected")


def why(e):
    """Fixed words and numbers for the journal: the cloud's status for our own CloudError texts, else the type."""
    return str(e) if isinstance(e, CloudError) and SAFE_WHY.fullmatch(str(e)) else type(e).__name__


def why_long(e):
    """why(e), and for the listing's own summary its counts and reasons (built from why() only)."""
    m = re.fullmatch(r"(\d+ of \d+ entries could not be read) \(((?:[A-Za-z0-9 ]+ ×\d+)(?:, [A-Za-z0-9 ]+ ×\d+)*)\); try again later", str(e)) if isinstance(e, CloudError) else None
    return f"{m.group(1)} ({m.group(2)})" if m else why(e)


def why_count(errors):
    """"file HTTP 429 ×12, ReadTimeout ×3": the reasons of a batch, most frequent first."""
    seen = {}
    for e in errors:
        seen[why(e)] = seen.get(why(e), 0) + 1
    return ", ".join(f"{k} ×{n}" for k, n in sorted(seen.items(), key=lambda x: (-x[1], x[0])))


async def _authed(uid, method, url, most=MAX_INDEX, headers=None, **kw):
    r = await _request(method, url, await user_token(uid), most, headers, **kw)
    if r.status_code == 401:
        r = await _request(method, url, await user_token(uid, fresh=True), most, headers, **kw)
    if r.status_code in BUSY:
        print(f"remarkable: cloud answered HTTP {r.status_code}, trying once more", flush=True)
        await asyncio.sleep(_pause(r))
        r = await _request(method, url, await user_token(uid), most, headers, **kw)
    return r


async def root(uid):
    r = await _authed(uid, "GET", ROOT_URL, most=64 * 1024)
    if r.status_code != 200:
        raise CloudError(f"root HTTP {r.status_code}")
    try:
        d = r.json()
    except ValueError:
        raise CloudError("root is no JSON (has reMarkable changed its interface?)")
    if not isinstance(d, dict) or not HASH.fullmatch(str(d.get("hash", ""))):
        raise CloudError("root without hash (has reMarkable changed its interface?)")
    gen = d.get("generation", 0)
    return d["hash"], gen if isinstance(gen, int) and not isinstance(gen, bool) else 0


async def blob(uid, h, name, most=MAX_INDEX):
    if not HASH.fullmatch(h or ""):
        raise CloudError("bad hash")
    r = await _authed(uid, "GET", FILES_URL + h, most=most, headers={"rm-filename": name})
    if r.status_code != 200:
        raise CloudError(f"file HTTP {r.status_code}")
    return r.content


def parse_index(data):
    """[{"hash", "id", "subfiles", "size"}] of a sync15 index (schema 3 or 4); odd lines are skipped."""
    out = []
    for line in data.decode("utf-8", "replace").splitlines()[1:]:
        p = line.split(":")
        if len(p) < 5 or p[2] == "." or not HASH.fullmatch(p[0]):
            continue
        if not re.fullmatch(r"[\w.\-/]{1,200}", p[2]) or ".." in p[2]:
            continue
        try:
            out.append({"hash": p[0], "type": p[1][:10], "id": p[2], "subfiles": int(p[3]), "size": int(p[4])})
        except ValueError:
            continue
        if len(out) > MAX_ENTRIES * 2:
            break
    return out


def _json_of(data):
    try:
        d = json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def page_order(content):
    """Page ids in the notebook's order from its .content (formats 1 and 2), deleted pages left out."""
    cp = content.get("cPages")
    if isinstance(cp, dict) and isinstance(cp.get("pages"), list):
        pages = []
        for p in cp["pages"]:
            if not isinstance(p, dict) or not ID.fullmatch(str(p.get("id", ""))):
                continue
            if isinstance(p.get("deleted"), dict) and p["deleted"].get("value"):
                continue
            idx = p.get("idx")
            pages.append((str(idx.get("value", "")) if isinstance(idx, dict) else "", p["id"]))
        return [i for _, i in sorted(pages, key=lambda x: x[0])]
    if isinstance(content.get("pages"), list):
        return [p for p in content["pages"] if isinstance(p, str) and ID.fullmatch(p)]
    return []


def page_times(content):
    """{page id: when it last changed (s)} where the .content names it per page (newer software), else {}."""
    out = {}
    pages = (content.get("cPages") or {}).get("pages") if isinstance(content.get("cPages"), dict) else None
    for p in pages if isinstance(pages, list) else []:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            continue
        v = p.get("modifed", p.get("modified"))
        v = v.get("value") if isinstance(v, dict) else v
        try:
            t = int(str(v)) // 1000
        except (TypeError, ValueError):
            continue
        if 1262304000 < t < time.time() + 86400:      # 2010 .. tomorrow: anything else is no time
            out[p["id"]] = t
    return out


def _clean(v, n=120):
    return re.sub(r"[\x00-\x1f\x7f<>\"\\]", "", str(v or ""))[:n].strip()


async def refresh_library(uid):
    """The account's documents and folders: {id: {"h", "name", "parent", "folder", "kind", "n", "mod"}}.
    Entries whose hash did not change are taken from the last listing."""
    rh, _ = await root(uid)
    _roots[uid] = rh
    entries = parse_index(await blob(uid, rh, "root.docSchema"))[:MAX_ENTRIES]
    old = library(uid)
    out, todo = {}, []
    for e in entries:
        if not ID.fullmatch(e["id"]):
            continue
        o = old.get(e["id"])
        if o and o.get("h") == e["hash"]:
            out[e["id"]] = o
        else:
            todo.append(e)
    sem = asyncio.Semaphore(CONCURRENT)
    _progress[uid] = [0, len(todo)]

    async def one(e):
        async with sem:
            _progress[uid][0] += 1
            files = parse_index(await blob(uid, e["hash"], e["id"] + ".docSchema"))
            meta, content = {}, {}
            for f in files:
                if f["id"] == e["id"] + ".metadata":
                    meta = _json_of(await blob(uid, f["hash"], f["id"], MAX_META))
                elif f["id"] == e["id"] + ".content":
                    content = _json_of(await blob(uid, f["hash"], f["id"], MAX_META))
            if not meta or meta.get("deleted"):
                return None
            folder = meta.get("type") == "CollectionType"
            kind = "folder" if folder else str(content.get("fileType") or "notebook")
            kind = kind if kind in ("folder", "notebook", "pdf", "epub") else "notebook"
            mod = meta.get("lastModified")
            try:
                mod = int(mod) // 1000
            except (TypeError, ValueError):
                mod = 0
            parent = str(meta.get("parent") or "")
            return e["id"], {"h": e["hash"], "name": _clean(meta.get("visibleName")) or "ohne Namen",
                             "parent": parent if parent == "trash" or ID.fullmatch(parent) else "",
                             "folder": folder, "kind": kind, "n": 0 if folder else len(page_order(content)), "mod": mod}

    failed, errors = 0, []
    try:
        got_all = await asyncio.gather(*(one(e) for e in todo), return_exceptions=True)
    finally:
        _progress.pop(uid, None)
    for e, got in zip(todo, got_all):
        if isinstance(got, tuple):
            out[got[0]] = got[1]
        elif isinstance(got, BaseException):
            if not isinstance(got, (CloudError, httpx.HTTPError, ValueError, netguard.TooLarge)):
                raise got
            failed += 1
            errors.append(got)
            if e["id"] in old:        # a hiccup never makes a notebook disappear: the last listing stays
                out[e["id"]] = old[e["id"]]
    if failed:
        print(f"remarkable: {failed} of {len(todo)} entries not read | {why_count(errors)}", flush=True)
    if failed > max(3, len(todo) // 10):
        raise CloudError(f"{failed} of {len(todo)} entries could not be read ({why_count(errors)}); try again later")
    _save_library(uid, out)
    return out


def path_of(items, i):
    """"Ordner/Unterordner/Name"; None when it lies in the trash."""
    names, seen = [], set()
    while i and i not in seen:
        seen.add(i)
        if i == "trash":
            return None
        it = items.get(i)
        if not it:
            break
        names.append(it["name"])
        i = it["parent"]
    return "/".join(reversed(names))


def wanted(uid, items=None, d=None):
    """{rm id: path} of the documents to read: picked ones, those in picked folders, or with "all" every
    notebook; never the trash."""
    items = library(uid) if items is None else items
    d = load(uid) if d is None else d
    picked = set(d.get("picked") or [])
    out = {}
    for i, it in items.items():
        if it.get("folder"):
            continue
        p = path_of(items, i)
        if p is None:
            continue
        hit = i in picked or (d.get("all") and it.get("kind") == "notebook")
        j, seen = it.get("parent"), set()
        while not hit and j and j not in seen:
            seen.add(j)
            hit = j in picked
            j = (items.get(j) or {}).get("parent")
        if hit:
            out[i] = p
    return out


# ---------------------------------------------------------------- one page
class _Hints(logging.Filter):
    """rmscene warns about every block of a newer page format it skips (hundreds a day in the journal);
    they are counted instead and named once per comparison (run)."""
    n = 0

    def filter(self, rec):
        if rec.levelno <= logging.WARNING:
            _Hints.n += 1
            return False
        return True


_HINTS = _Hints()


def _quiet_rmscene():
    """A filter on a logger only sees its own records, so each rmscene module's logger gets it."""
    for name in list(logging.Logger.manager.loggerDict):
        if name == "rmscene" or name.startswith("rmscene."):
            lg = logging.getLogger(name)
            if _HINTS not in lg.filters:
                lg.addFilter(_HINTS)


def parse_page(data, draw=True, size=None):
    """(typed text, [highlighted texts], JPEG of the handwriting or None, has ink) of one v6 page file.
    size: a list that gets the page's size in device pixels when the file names it (which model, rmpapier.py).
    Raises ValueError for other formats (old firmware) or broken files."""
    if not data.startswith(b"reMarkable .lines file, version=6"):
        raise ValueError("old page format (please update the reMarkable)")
    from rmscene import scene_items as si
    from rmscene import scene_stream as ss
    from rmscene.text import TextDocument
    _quiet_rmscene()
    typed, marks, lines, points = [], [], [], 0
    for b in ss.read_blocks(io.BytesIO(data)):
        if size is not None and isinstance(b, ss.SceneInfo) and getattr(b, "paper_size", None):
            size[:] = list(b.paper_size)[:2]
        v = getattr(b, "value", None)
        if isinstance(v, si.Text):
            try:
                typed += [str(p).strip() for p in TextDocument.from_scene_item(v).contents]
            except Exception:
                pass
            continue
        it = getattr(b, "item", None)
        v = getattr(it, "value", None)
        if isinstance(v, si.GlyphRange):
            t = _clean(v.text, 2000) if isinstance(getattr(v, "text", None), str) else ""
            if t:
                y = v.rectangles[0].y if v.rectangles else 0
                marks.append((y, t))
        elif isinstance(v, si.Line) and v.points:
            tool = int(getattr(v.tool, "value", v.tool))
            if tool in (5, 18, 6, 8):          # highlighters and erasers
                continue
            if points < MAX_POINTS:
                pts = [(p.x, p.y) for p in v.points]
                width = sum(p.width for p in v.points) / len(v.points)
                lines.append((pts, width))
                points += len(pts)
    jpeg = render(lines) if draw and lines else None
    return "\n".join(t for t in typed if t), [t for _, t in sorted(marks)], jpeg, bool(lines)


def render(lines):
    """The strokes black on white, cut to what is written (margin around it), at most SIDE pixels."""
    from PIL import Image, ImageDraw
    xs = [x for pts, _ in lines for x, _ in pts]
    ys = [y for pts, _ in lines for _, y in pts]
    if not xs:
        return None
    m = 40
    x0, y0, x1, y1 = min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    scale = min(SIDE / w, SIDE / h, 1.5)
    im = Image.new("L", (max(1, int(w * scale)), max(1, int(h * scale))), 255)
    dr = ImageDraw.Draw(im)
    for pts, width in lines:
        xy = [((x - x0) * scale, (y - y0) * scale) for x, y in pts]
        px = max(2, int(round(min(max(width / 4, 1.5), 6) * scale)))
        if len(xy) == 1:
            x, y = xy[0]
            dr.ellipse((x - px / 2, y - px / 2, x + px / 2, y + px / 2), fill=0)
        else:
            dr.line(xy, fill=0, width=px, joint="curve")
    return documents._jpeg_of(im)


def page_text(typed, marks):
    out = typed
    if marks:
        out += ("\n" if out else "") + "\n".join("Markiert: " + t for t in marks)
    return out


# ---------------------------------------------------------------- comparing
def _pictures(uid):
    import wissen
    return wissen.on(uid, "pictures")


def _space_left(uid):
    import wissen
    return documents.usage_total(uid) < wissen.quota_bytes(uid)


async def sync(uid, budget=MAX_RUN_PAGES):
    """Compares the picked notebooks with the cloud. Returns {"docs", "pages", "removed", "more"}."""
    if uid in _busy:
        raise CloudError("a comparison is already running")
    _busy.add(uid)
    try:
        return await _sync(uid, budget)
    finally:
        _busy.discard(uid)


SYNC_KEYS = ("docs", "picked", "skip", "last", "count", "error", "paper_size")


def _save_sync(uid, d):
    """The comparison runs for minutes with its own copy: it writes back only its own parts, so what was saved in
    between (a document sent, a sheet's boxes, rmpapier.py) stays."""
    cur = load(uid)
    for k in SYNC_KEYS:
        if k in d:
            cur[k] = d[k]
        else:
            cur.pop(k, None)
    save(uid, cur)


async def _sync(uid, budget):
    items = await refresh_library(uid)
    d = load(uid)
    want = wanted(uid, items, d)
    draw = _pictures(uid)
    res = {"docs": 0, "pages": 0, "removed": 0, "more": False}
    full = False
    # gone from the cloud, no longer picked, or deleted under Ich → Dokumente (then no longer picked)
    for rid in list(d["docs"]):
        local = d["docs"][rid].get("doc", "")
        if rid in want and not documents.has_doc(uid, local) and d["docs"][rid].get("seen"):
            if rid in d["picked"]:
                d["picked"].remove(rid)
            d.setdefault("skip", []).append(rid)
            d["skip"] = d["skip"][-MAX_PICKED:]
            want.pop(rid, None)
        if rid not in want or rid in d.get("skip", []):
            documents.delete(uid, local)
            d["docs"].pop(rid)
            res["removed"] += 1
    for rid in d.get("skip", []):
        want.pop(rid, None)
    for rid, path in sorted(want.items(), key=lambda x: -items[x[0]].get("mod", 0)):
        it, st = items[rid], d["docs"].get(rid) or {}
        complete = st.get("h") == it["h"] and not st.get("left") and not (draw and st.get("ink_skipped"))
        if complete and documents.has_doc(uid, st.get("doc", "")):
            continue
        if budget <= 0:
            res["more"] = True
            break
        if not _space_left(uid):
            full = True
            break
        got = await _notebook(uid, rid, it, path, st, draw, budget)
        budget -= got["fetched"]
        d["docs"][rid] = got["state"]
        if got.get("size"):        # the page size names the model (rmpapier.detect): sheets are made in its format
            d["paper_size"] = got["size"]
        res["docs"] += 1
        res["pages"] += got["fetched"]
        _save_sync(uid, d)
    d["last"] = int(time.time())
    d["count"] = len(d["docs"])
    d.pop("error", None)
    if full:
        d["error"] = "Der Speicher für Dokumente ist voll (Ich → Dokumente)."
    _save_sync(uid, d)
    return res


async def _notebook(uid, rid, it, path, st, draw, budget):
    files = parse_index(await blob(uid, it["h"], rid + ".docSchema"))
    byid = {f["id"]: f for f in files}
    cf = byid.get(rid + ".content")
    content = _json_of(await blob(uid, cf["hash"], cf["id"], MAX_META)) if cf else {}
    order = page_order(content)[:MAX_PAGES]
    old = st.get("pages") or {}
    texts = documents.notebook_texts(uid, st.get("doc", ""))
    times = page_times(content)
    doc_time = int(it.get("mod") or 0) or int(time.time())
    pages, new_map, fetched, ink_skipped, failed, size = [], {}, 0, False, 0, []
    for n, pid in enumerate(order, 1):
        f = byid.get(f"{rid}/{pid}.rm")
        if not f:
            continue                      # an empty page (or a PDF page without notes)
        o = old.get(pid)
        if o and o[0] == f["hash"] and not (draw and o[2]) and o[1] in texts:
            when = times.get(pid) or (o[3] if len(o) > 3 else 0) or doc_time
            pages.append((n, texts[o[1]], None, when))
            new_map[pid] = [f["hash"], n, o[2], when]
            continue
        if fetched >= budget:
            break
        fetched += 1
        try:
            data = await blob(uid, f["hash"], f["id"], MAX_PAGE)
            typed, marks, jpeg, ink = await asyncio.wait_for(asyncio.to_thread(parse_page, data, draw, size), 60)
        except (ValueError, asyncio.TimeoutError, CloudError, httpx.HTTPError) as e:
            failed += 1
            print("remarkable: page not read:", why(e), flush=True)
            continue
        except Exception as e:            # rmscene on a file it does not know
            failed += 1
            print("remarkable: page not read:", type(e).__name__, flush=True)
            continue
        skipped = ink and not draw
        ink_skipped = ink_skipped or skipped
        when = times.get(pid) or doc_time   # changed since the last look: its own time, else the notebook's
        pages.append((n, page_text(typed, marks), jpeg, when))
        new_map[pid] = [f["hash"], n, 1 if skipped else 0, when]
    notes = []
    if len(page_order(content)) > MAX_PAGES:
        notes.append(f"nur die ersten {MAX_PAGES} Seiten")
    if ink_skipped:
        notes.append("Handschrift nicht gelesen („Bilder und Scans lesen“ ist aus)")
    if failed:
        notes.append(f"{failed} Seite{'n' if failed > 1 else ''} nicht lesbar")
    if it.get("mod"):
        notes.append("geändert am " + time.strftime("%d.%m.%Y", time.localtime(it["mod"])))
    doc, left = await asyncio.to_thread(documents.notebook_put, uid, st.get("doc"), path, pages, "; ".join(notes),
                                        "remarkable", doc_time)
    cut = fetched >= budget and len(new_map) < len([p for p in order if f"{rid}/{p}.rm" in byid])
    return {"fetched": fetched, "size": size, "state": {"doc": doc, "h": "" if cut else it["h"], "pages": new_map,
                                          "left": left, "ink_skipped": ink_skipped, "seen": True}}


async def due_once(idle=True, now=None):
    """Background: compares one profile whose turn it is (SYNC_EVERY, sooner after a cut-short run)."""
    now = now or time.time()
    if not idle or not features.admin_on("remarkable"):
        return None
    for uid in profiles.user_ids():
        if not allowed(uid) or uid in _busy:
            continue
        d = load(uid)
        if not d.get("token") or not (d.get("picked") or d.get("all")):
            continue
        wait = SOON if d.get("more") else SYNC_EVERY
        if now - max(d.get("last", 0), _auto_last.get(uid, 0)) < wait:
            # new notes come quickly: one small request for the root; only when it changed, a comparison now
            if now - _peek_last.get(uid, 0) < PEEK or not d.get("root"):
                continue
            _peek_last[uid] = now
            try:
                rh, _ = await root(uid)
            except (CloudError, httpx.HTTPError, netguard.Blocked, netguard.TooLarge) as e:
                print("remarkable: quick look failed:", why(e), flush=True)
                continue
            if rh == d.get("root"):
                continue
            print("remarkable: account changed, comparing now", flush=True)
        _auto_last[uid] = _peek_last[uid] = now
        await run(uid)
        return uid
    return None


async def run(uid):
    """One comparison with its outcome kept for Ich → reMarkable (never raises)."""
    try:
        res = await sync(uid)
    except Exception as e:
        d = load(uid)
        d["error"] = _redact(f"{type(e).__name__}: {e}") if isinstance(e, (CloudError, ValueError)) else type(e).__name__
        d["more"] = False
        save(uid, d)
        hintergrund.note(uid, "remarkable", False)
        print("remarkable: comparison failed:", why_long(e), flush=True)
        return None
    if _Hints.n:
        print(f"remarkable: {_Hints.n} reader hint(s) about newer page parts it skips (usual with newer reMarkable software)", flush=True)
        _Hints.n = 0
    d = load(uid)
    d["more"] = res["more"]
    if uid in _roots:
        d["root"] = _roots[uid]     # what the quick look compares with (due_once)
    save(uid, d)
    hintergrund.note(uid, "remarkable", True, res["pages"])
    print(f"remarkable: {res['docs']} notebook(s), {res['pages']} page(s) new, {res['removed']} removed", flush=True)
    if res["pages"] or res["removed"]:
        try:      # Zustand → Live: numbers only
            import live
            if live.on():
                live.event("reMarkable", f"Abgleich: {res['pages']} Seite(n) neu, {res['removed']} entfernt")
        except Exception:
            pass
    return res


# ---------------------------------------------------------------- writing: an answer onto the reMarkable
_CRC = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (0x82F63B78 & -(_c & 1))
    _CRC.append(_c & 0xFFFFFFFF)


def crc32c(data):
    c = 0xFFFFFFFF
    for b in data:
        c = (c >> 8) ^ _CRC[(c ^ b) & 0xFF]
    return c ^ 0xFFFFFFFF


def epub(title, text):
    """A small EPUB (reflows on the device, every character works): the text as paragraphs."""
    t = html.escape(title)
    body = "".join(f"<p>{html.escape(p).replace(chr(10), '<br/>')}</p>" for p in re.split(r"\n\s*\n", text) if p.strip())
    ident = "urn:uuid:" + str(uuid.uuid4())
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile '
                   'full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
                   zipfile.ZIP_DEFLATED)
        z.writestr("content.opf", f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
                   f'version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   f'<dc:identifier id="id">{ident}</dc:identifier><dc:title>{t}</dc:title><dc:language>de</dc:language>'
                   f'<meta property="dcterms:modified">{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}</meta>'
                   f'</metadata><manifest><item id="t" href="text.xhtml" media-type="application/xhtml+xml"/>'
                   f'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest>'
                   f'<spine><itemref idref="t"/></spine></package>', zipfile.ZIP_DEFLATED)
        z.writestr("nav.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
                   f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{t}</title></head><body><nav epub:type="toc">'
                   f'<ol><li><a href="text.xhtml">{t}</a></li></ol></nav></body></html>', zipfile.ZIP_DEFLATED)
        z.writestr("text.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
                   f'<head><title>{t}</title></head><body><h1>{t}</h1>{body}</body></html>', zipfile.ZIP_DEFLATED)
    return out.getvalue()


async def _put(uid, data, name, ctype="application/octet-stream", h=None):
    """Uploads one file under its hash (a document's index is stored under the hash of its entries)."""
    h = h or hashlib.sha256(data).hexdigest()
    headers = {"rm-filename": name, "content-type": ctype,
               "x-goog-hash": "crc32c=" + base64.b64encode(struct.pack(">I", crc32c(data))).decode()}
    r = await _authed(uid, "PUT", FILES_URL + h, most=64 * 1024, headers=headers, content=data)
    if not 200 <= r.status_code < 300:
        raise CloudError(f"upload of {name.rsplit('.', 1)[-1]} HTTP {r.status_code} {_said(r)}".strip())
    return {"hash": h, "id": name, "size": len(data)}


async def _index(uid, name, entries):
    """Uploads one document's index for its (sorted) files; returns its root line."""
    body = ("3\n" + "".join(f"{e['hash']}:0:{e['id']}:0:{e['size']}\n" for e in entries)).encode()
    dh = hashlib.sha256(b"".join(bytes.fromhex(e["hash"]) for e in entries)).hexdigest()
    await _put(uid, body, name + ".docSchema", h=dh)
    return {"hash": dh, "id": name, "subfiles": len(entries), "size": sum(e["size"] for e in entries)}


async def _new_doc(uid, name, files):
    """Uploads the files of one new document and its index; returns its root line."""
    entries = [await _put(uid, data, fid) for fid, data in files]
    entries.sort(key=lambda e: e["id"])
    return await _index(uid, name, entries)


async def _add_to_root(uid, new, swap=None):
    """Adds documents to the root index (generation-checked, a few tries when another device was faster).
    Only appends lines; the existing ones are written back unchanged, except the Spark's own documents in
    swap ({doc id: new root line}: the guide, the day's inbox), which must still be there."""
    swap = swap or {}
    for attempt in range(4):
        rh, gen = await root(uid)
        raw = await blob(uid, rh, "root.docSchema")
        entries = parse_index(raw)
        # every line must be understood: a line left out here would vanish from the account with the new root
        lines = [x for x in raw.decode("utf-8", "replace").splitlines()[1:] if x.strip() and x.split(":")[1:2] != ["."]]
        if len(entries) != len(lines):
            raise CloudError(f"root index has {len(lines) - len(entries)} lines the Spark does not understand; nothing written")
        have = {e["id"] for e in entries}
        if set(swap) - have:
            raise CloudError("the document to renew is gone; nothing written")
        entries = [swap.get(e["id"], e) for e in entries]
        entries += [e for e in new if e["id"] not in have]
        entries.sort(key=lambda e: e["id"])
        body = ("4\n" + f"0:.:{len(entries)}:{sum(e['size'] for e in entries)}\n" +
                "".join(f"{e['hash']}:{e.get('type') or '0'}:{e['id']}:{e['subfiles']}:{e['size']}\n" for e in entries)).encode()
        nh = (await _put(uid, body, "root.docSchema", "text/plain; charset=UTF-8"))["hash"]
        r = await _authed(uid, "PUT", ROOT_PUT_URL, most=64 * 1024, headers={"rm-filename": "roothash"},
                          json={"broadcast": True, "hash": nh, "generation": gen})
        if r.status_code in (409, 412, 428):
            await asyncio.sleep(1 + attempt)
            continue
        if not 200 <= r.status_code < 300:
            raise CloudError(f"root commit HTTP {r.status_code} {_said(r)}".strip())
        _own_root(uid, rh, nh)
        return
    raise CloudError("another device kept writing; try again")


def _own_root(uid, before, after):
    """The Spark's own write changed the root: the quick look (due_once) should not take it for a change
    on the reMarkable. Only when the root it knew was the one this write started from; else the next look
    still sees the other device's change."""
    if _roots.get(uid) == before:
        _roots[uid] = after
    d = load(uid)
    if d.get("root") == before:
        d["root"] = after
        save(uid, d)


def _meta(name, parent, kind, pinned=False):
    now = str(int(time.time() * 1000))
    return json.dumps({"createdTime": now, "deleted": False, "lastModified": now, "lastOpened": "0", "lastOpenedPage": 0,
                       "metadatamodified": False, "modified": False, "new": False, "parent": parent, "pinned": bool(pinned),
                       "source": "", "synced": False, "type": kind, "version": 1, "visibleName": name}, sort_keys=True).encode()


def where(uid, items=None):
    """(folder id, path) the profile chose under Ich → reMarkable → "Ablegen in"; ("", "Spark") for the default
    or when that folder is gone or in the trash."""
    t = load(uid).get("target") or ""
    items = library(uid) if items is None else items
    it = items.get(t) if t else None
    p = path_of(items, t) if it and it.get("folder") else None
    return (t, p) if p else ("", "Spark")


async def send(uid, title, text):
    """A new EPUB with this text in the chosen folder (default "Spark", created when missing). Only adds a new
    document; nothing existing is changed. Returns {"title", "where", "lost"} (lost: the chosen folder is gone)."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text or ""))[:MAX_SEND].strip()
    text = plain_markdown(text)   # an answer's Markdown signs stay off the paper
    if not text:
        raise ValueError("nothing to send")
    title = _clean(title, 80) or "Vom Spark"
    import rmpapier
    if rmpapier.paper_on(uid):      # a designed sheet in the device's format, in "Antworten" (rmpapier.py)
        return await rmpapier.place(uid, "antwort", title, rmpapier.built_text(uid, "Antwort", title, text), "text",
                                    auto=False)
    return await place(uid, title, epub(title, text), art="antwort")


def _count(d, key, most):
    """Today's uploads of one kind ("sent": asked for, "auto": made by the Spark itself); over the limit: ValueError."""
    day = time.strftime("%Y-%m-%d")
    s = d.get(key) if isinstance(d.get(key), dict) and d[key].get("day") == day else {"day": day, "n": 0}
    if s["n"] >= most:
        raise ValueError(f"heute schon {most} Mal geschickt; morgen wieder")
    return s


def _content(kind, title):
    if kind == "pdf":
        return json.dumps({"coverPageNumber": 0, "documentMetadata": {"title": title}, "dummyDocument": False,
                           "extraMetadata": {}, "fileType": "pdf", "fontName": "", "formatVersion": 1, "lineHeight": -1,
                           "margins": 125, "orientation": "portrait", "pageCount": 0, "pages": [], "tags": [],
                           "textScale": 1}, sort_keys=True).encode()
    return json.dumps({"coverPageNumber": -1, "documentMetadata": {"title": title}, "dummyDocument": False,
                       "extraMetadata": {}, "fileType": "epub", "fontName": "", "formatVersion": 1, "lineHeight": -1,
                       "margins": 100, "orientation": "portrait", "pageCount": 0, "pages": [], "tags": [],
                       "textScale": 1}, sort_keys=True).encode()


async def base_folder(uid, items, new):
    """(folder id, path, lost) where new documents go: the folder chosen under "Ablegen in", else "Spark" (made when
    missing; the new folder's root line is appended to new). lost: the chosen folder is gone."""
    folder, path = where(uid, items)
    lost = bool(load(uid).get("target")) and not folder
    if not folder:
        folder = next((i for i, it in items.items() if it.get("folder") and it["name"] == "Spark" and not it["parent"]), None)
    if not folder:
        folder = next((e["id"] for e in new if e.get("spark_base")), None)
    if not folder:
        folder = str(uuid.uuid4())
        entry = await _new_doc(uid, folder, [(folder + ".metadata", _meta("Spark", "", "CollectionType"))])
        entry["spark_base"] = True
        new.append(entry)
    return folder, path, lost


MAX_MADE = 400              # documents the Spark made, remembered for sorting and tidying up (rmpapier.py)


async def place(uid, title, data, kind="epub", own="", auto=False, src="", art="", pinned=False):
    """Puts one EPUB or PDF into the chosen folder (default "Spark", created when missing).
    own: a name for one of the Spark's OWN documents (the guide, the day's inbox): when the Spark made it before
    and it is still there, that document gets the new text (its other files, e.g. the person's marks, stay);
    else a new one. A PDF sheet with handwriting on it is never filled with new text: it gets a new version (and
    the old one goes to "Archiv" with "Ordner nach Art"). Nothing the person made is ever changed. auto: made by
    the Spark itself (rmplus.py), its own daily limit. src: "web" or "mail" when the title is outside text (a page's
    or an attachment's name; recent() then never repeats it). Every upload is noted (recent). art: a kind from
    rmpapier.ARTEN, its folder below the base folder ("Ordner nach Art"; the caller passes it only when that is on).
    pinned: a favourite on the device.
    Returns {"title", "where", "lost", "id", "renewed"}."""
    notaus.stop("aktion", uid)   # the Notaus (or the profile's own) holds every action off (notaus.py)
    if kind not in ("epub", "pdf") or not data:
        raise ValueError("nothing to send")
    if len(data) > MAX_FILE:
        raise ValueError(f"zu groß (höchstens {MAX_FILE // 1024**2} MB)")
    import rmpapier
    title = _clean(title, 80) or "Vom Spark"
    key = "auto" if auto else "sent"
    s = _count(load(uid), key, AUTO_DAY if auto else SEND_DAY)
    try:
        items = await refresh_library(uid)
    except CloudError as e:     # a few unreadable entries must not stop a new document: the last listing
        print("remarkable: listing before sending:", why_long(e), "- using the last listing", flush=True)
        items = library(uid)
    mine = (load(uid).get("own") or {}).get(own) if own else None
    renew = mine if mine and ID.fullmatch(str(mine)) and mine in items and not items[mine].get("folder") else None
    swap, new, lost, path, marked = {}, [], False, "", None
    if renew:
        old = parse_index(await blob(uid, items[renew]["h"], renew + ".docSchema"))
        if kind == "pdf" and any(e["id"].endswith(".rm") for e in old):
            marked, renew = renew, None     # handwriting on the sheet: never new text under it, a new version
    if renew:
        keep = [(e["id"], e) for e in old if not e["id"].endswith((".epub", ".pdf", ".content", ".metadata"))]
        meta = _meta(title, items[renew].get("parent") or "", "DocumentType", pinned)
        fresh = [await _put(uid, x, n) for n, x in ((renew + "." + kind, data), (renew + ".content", _content(kind, title)),
                                                    (renew + ".metadata", meta))]
        entries = sorted([e for _, e in keep] + fresh, key=lambda e: e["id"])
        swap[renew] = await _index(uid, renew, entries)
        did, path = renew, path_of(items, items[renew].get("parent")) if items[renew].get("parent") else ""
    else:
        folder, path, lost = await base_folder(uid, items, new)
        if art in rmpapier.ARTEN and rmpapier.folders_on(uid):
            folder = await rmpapier.art_folder(uid, items, folder, art, new)
            path = (path or "Spark") + "/" + rmpapier.ARTEN[art]
        if marked and rmpapier.folders_on(uid):
            base, _, _ = await base_folder(uid, items, new)
            swap.update(await rmpapier.set_meta(uid, items, {marked: {
                "parent": await rmpapier.art_folder(uid, items, base, "archiv", new), "pinned": False}}))
        did = str(uuid.uuid4())
        new.append(await _new_doc(uid, did, [(did + ".content", _content(kind, title)),
                                            (did + ".metadata", _meta(title, folder, "DocumentType", pinned)),
                                            (did + ".pagedata", b"\n"), (did + "." + kind, data)]))
    await _add_to_root(uid, [{k: v for k, v in e.items() if k not in ("spark_base", "folder_of")} for e in new], swap)
    d = load(uid)
    s["n"] += 1
    d[key] = s
    if own:
        d.setdefault("own", {})[own] = did
    if lost:
        d.pop("target", None)    # the chosen folder is gone: from now on "Spark" again, and the person is told
    now = int(time.time())
    log = [x for x in d.get("log") or [] if isinstance(x, dict) and now - int(x.get("t", 0)) < LOG_S][-(LOG_MAX - 1):]
    d["log"] = log + [{"t": now, "title": title, "auto": bool(auto), "renewed": bool(renew),
                       "src": src if src in ("web", "mail") else ""}]
    made = d.get("made") if isinstance(d.get("made"), dict) else {}
    made[did] = dict(made.get(did) or {}, art=art, t=now, k=kind)
    d["made"] = dict(sorted(made.items(), key=lambda x: x[1].get("t", 0))[-MAX_MADE:])
    save(uid, d)
    import tagebuch
    tagebuch.note(uid, "remarkable", title, ref=did, src=src)
    return {"title": title, "where": path or "Spark", "lost": lost, "id": did, "renewed": bool(renew)}


LOG_S = 7 * 86400       # what the Spark put on the reMarkable, kept this long (recent, document_status)
LOG_MAX = 40


def recent(uid, now=None):
    """The uploads of the last 7 days, newest first: {t, title, auto, renewed, src}. Titles of web pages and mail
    attachments (src) are outside text and come back only as their kind."""
    now = time.time() if now is None else now
    out = []
    for x in reversed(load(uid).get("log") or []):
        if isinstance(x, dict) and isinstance(x.get("t"), int) and 0 <= now - x["t"] < LOG_S:
            title = {"web": "eine Webseite", "mail": "ein Mail-Anhang"}.get(x.get("src")) or _clean(x.get("title"), 80)
            out.append(dict(x, title=title, src=x.get("src") or ""))
    return out


def recent_text(uid, now=None):
    """One sentence for the assistant: what the Spark put on the reMarkable in the last 7 days, with time."""
    rows = recent(uid, now)
    if not rows:
        return "Auf das reMarkable hat der Spark in den letzten 7 Tagen nichts gelegt."
    parts = [("„" + x["title"] + "“" if not x["src"] else x["title"])
             + " " + time.strftime("%d.%m. %H:%M", time.localtime(x["t"]))
             + (" (vom Spark selbst)" if x.get("auto") else "") + (" (erneuert)" if x.get("renewed") else "")
             for x in rows[:10]]
    return f"Auf das reMarkable gelegt (letzte 7 Tage, {len(rows)}): " + "; ".join(parts) + "."


def _told(r):
    """The sentence after sending: where it is, and when the chosen folder was gone."""
    gone = " Dein gewählter Ordner ist nicht mehr da, deshalb liegt es in „Spark“." if r["lost"] else ""
    return f"im Ordner „{r['where']}“ („{r['title']}“).{gone}"


# ---------------------------------------------------------------- the assistant: a dictated note
NOTE_TOOL = {"type": "function", "function": {
    "name": "remarkable_note",
    "description": "Puts a note the user dictates onto the user's reMarkable tablet (a new document in the folder "
                   "\"Spark\"). Only when the user asks for it in this message.",
    "parameters": {"type": "object", "properties": {
        "title": {"type": "string", "description": "Short title, at most 8 words"},
        "text": {"type": "string", "description": "The text of the note, as the user said it"}},
        "required": ["title", "text"]}}}
SENT_TOOL = {"type": "function", "function": {
    "name": "remarkable_sent",
    "description": "Lists what the Spark put on the user's reMarkable in the last 7 days (title and time). Use it when "
                   "the user asks whether something was made, sent or put on the reMarkable.",
    "parameters": {"type": "object", "properties": {}}}}
NOTE_HINT = ("remarkable_note puts a note the user dictates onto the user's reMarkable as a new document; use it only "
             "when the user asks to write or send something to the reMarkable.")
WORDS = re.compile(r"re\s?markable|remarkabel|e-?ink[- ]?tablet", re.I)


# "Fass die Lage zusammen und leg es aufs reMarkable": the answer itself goes there. A fixed panel rule on the
# person's own words decides it, never the model: the tool would be cut by the switch (intent.narrow) and locked
# remarkable_sent reads only the Spark's own list of what it put on the tablet; titles from outside (a web page,
# an attachment) come back only as their kind (recent), so no text other people wrote (see chat.INSIDE)
INSIDE = {"remarkable_sent"}


# after the web search (outside text), and the destination is fixed anyway (a new document in "Spark").
ANSWER_ASK = re.compile(r"\b(?:aufs|auf(?:\s+(?:das|dem|den|mein(?:em|en)?|dein(?:em)?))?|ins|an(?:s|\s+(?:das|mein(?:en)?))?|on(?:to)?|to)"
                        r"\s+(?:(?:my|the)\s+)?re\s?markable\b", re.I)
ANSWER_VERB = re.compile(r"\b(?:leg|ableg|abzuleg|speicher|schick|send|pack|tu|stell|kopier|übertrag|bring|put|sav|stor)\w*"
                         r"|\bschreib\w*\s+(?:es|das|sie|die\s+\w+)\b", re.I)
DICTATE = re.compile(r"re\s?markable\W{0,3}:|notier|diktier|\bdass\b", re.I)


def answer_wanted(text, uid=None):
    """The person asks for the answer of this message on the reMarkable (not a dictated note, and not a web page
    or a mail attachment the profile can put there itself, rmplus.py)."""
    text = str(text or "")[:2000]
    if not (ANSWER_ASK.search(text) and ANSWER_VERB.search(text) and not DICTATE.search(text)):
        return False
    import chat
    if chat.DONE_WORDS.search(text) and "?" in text:
        return False      # „Hast du mir was aufs reMarkable geschickt?“ asks about the past, it sends nothing
    import rmplus     # one of the Spark's own sheets is never the model's text (remarkable_sheet, even when off)
    if any(rx.search(text) for rx, _ in rmplus.SHEETS.values()):
        return False
    return not (uid and rmplus.tools_for(uid, text))


def answer_title(text):
    """A title from the question without the reMarkable part: "Politische Lage zusammenfassen"."""
    t = ANSWER_ASK.sub(" ", str(text or "")[:300])
    t = re.sub(r"\b(?:und|and)?\s*(?:leg|schick|speicher|pack|send|put|save)\w*\s+(?:es|das|sie|it|mir|ihn)?\s*(?:ab|bitte)?\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", re.sub(r"[^\w\s,.\-äöüÄÖÜß]", " ", t)).strip(" ,.-")
    t = " ".join(t.split()[:8])
    return (t[:1].upper() + t[1:]) if t else "Vom Spark"


def answer_ok(who, own, private):
    """May this answer go to the reMarkable at all (same rule as the tool)."""
    return bool(who and own and private is not False and send_allowed(who["id"]) and load(who["id"]).get("token"))


async def send_answer(uid, question, answer):
    """After the answer: the panel puts it on the reMarkable. Returns (ok, sentence to say)."""
    if not send_allowed(uid):
        return False, "Aufs reMarkable schicken ist aus."
    if not str(answer or "").strip():
        return False, "Es gab keine Antwort zum Ablegen."
    try:
        r = await send(uid, answer_title(question), answer)
        return True, "Die Antwort liegt jetzt auf deinem reMarkable " + _told(r)
    except (CloudError, ValueError, httpx.HTTPError, netguard.Blocked, netguard.TooLarge) as e:
        why = _redact(e if isinstance(e, (ValueError, CloudError)) else type(e).__name__)
        print("remarkable: sending failed:", why, flush=True)
        return False, "Aufs reMarkable ging es nicht: " + why


ANSWER_HINT = ("Der Nutzer will diese Antwort auf seinem reMarkable haben. Das erledigt der Spark nach deiner Antwort "
               "selbst: schreib einfach die vollständige Antwort, ruf dafür kein Werkzeug auf und sag nicht, dass sie "
               "schon dort liegt.")


def offer(ctx):
    """Only in the profile's own session, only when the person's own words name the reMarkable."""
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False:
        return None
    if not send_allowed(who["id"]) or not load(who["id"]).get("token"):
        return None
    if not WORDS.search(str(ctx.get("text") or "")) or answer_wanted(ctx.get("text"), who["id"]):
        return None   # the whole answer: the panel sends it afterwards (answer_wanted), no tool
    import rmplus     # a web page or a mail attachment (rmplus.py, rm_web), only with an address / attachment named
    more = rmplus.tools_for(who["id"], ctx.get("text"))
    return {"tools": [NOTE_TOOL, SENT_TOOL] + more, "hint": NOTE_HINT + (" " + rmplus.HINT if more else ""),
            "changes": {"remarkable_note", "remarkable_page", "remarkable_attachment", "remarkable_sheet"},
            # offered only when the person's own words name the reMarkable: the Weiche keeps them (werkzeug-abdeckung)
            "keep": {t["function"]["name"] for t in [NOTE_TOOL, SENT_TOOL] + more},
            # what comes back names the page's title or the mail's file name: outside text, the rest of the answer locked
            "mail": {"remarkable_attachment"}, "outside": {"remarkable_page"},
            "filler": {"remarkable_note": ("Ich schicke es aufs reMarkable.", "Sending it to the reMarkable."),
                       "remarkable_page": ("Ich hole die Seite.", "Fetching the page."),
                       "remarkable_sheet": ("Ich lege das Blatt hin.", "Putting the sheet there."),
                       "remarkable_attachment": ("Ich suche den Anhang.", "Looking for the attachment."),
                       "remarkable_sent": ("Ich schaue nach.", "Let me check.")}}


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    if name not in ("remarkable_note", "remarkable_page", "remarkable_attachment", "remarkable_sent", "remarkable_sheet") \
            or not send_allowed(uid):
        return "Aufs reMarkable schicken ist aus."
    if name == "remarkable_sent":       # reading only: what the Spark already put there
        return recent_text(uid)
    import rmplus
    try:
        if name == "remarkable_sheet":       # one of the Spark's own sheets, by its own switch (rmplus.sheet_now)
            return await rmplus.tool(name, args, uid)
        if name != "remarkable_note":
            if not rmplus.on("rmweb", uid):
                return "Webseiten und Anhänge aufs reMarkable sind aus."
            return await rmplus.tool(name, args, uid)
        if rmplus.on("rminbox", uid):       # one inbox document per day (rmplus.py)
            r = await rmplus.inbox_add(uid, args.get("title"), args.get("text"))
            return "Steht jetzt im Eingang des Tages auf dem reMarkable " + _told(r)
        r = await send(uid, args.get("title"), args.get("text"))
        return "Liegt jetzt auf dem reMarkable " + _told(r)
    except (CloudError, ValueError, httpx.HTTPError, netguard.Blocked, netguard.TooLarge) as e:
        why = _redact(e if isinstance(e, (ValueError, CloudError)) else type(e).__name__)
        print("remarkable: sending failed:", why, flush=True)
        return "Nicht geschickt: " + why


async def briefing(uid, zone=None):
    return ""


# ---------------------------------------------------------------- routes
def _on(prof=Depends(browser_profile)):
    if not allowed(prof["id"]):
        raise HTTPException(403, "reMarkable ist aus (Funktionen → reMarkable-Notizen)")
    return prof


def public(uid):
    import rmplus
    import rmpapier
    d, items = load(uid), library(uid)
    want = wanted(uid, items, d)
    lib = []
    for i, it in items.items():
        p = path_of(items, i)
        if p is None:
            continue
        lib.append({"id": i, "name": it["name"], "path": p, "folder": bool(it.get("folder")), "kind": it.get("kind"),
                    "pages": it.get("n", 0), "mod": it.get("mod", 0), "picked": i in d["picked"], "read": i in want})
    lib.sort(key=lambda x: (not x["folder"], x["path"].lower()))
    return {"connected": bool(d.get("token")), "since": d.get("paired", 0), "last": d.get("last", 0),
            "error": d.get("error", ""), "count": len(d["docs"]), "all": bool(d.get("all")), "library": lib,
            "pictures": _pictures(uid), "send": send_allowed(uid), "connect_url": CONNECT_URL,
            "target": where(uid, items)[0], "target_path": where(uid, items)[1],
            "sent_today": (d.get("sent") or {}).get("n", 0) if (d.get("sent") or {}).get("day") == time.strftime("%Y-%m-%d") else 0,
            "send_day": SEND_DAY, "busy": uid in _busy, "progress": list(_progress.get(uid) or []),
            "plus": rmplus.public(uid),
            "paper": rmpapier.public(uid) if features.admin_on("rmpapier") and send_allowed(uid) else None}


@router.get("/api/profile/remarkable", dependencies=[Depends(assistant)])
def info(prof=Depends(_on)):
    return public(prof["id"])


@router.post("/api/profile/remarkable/pair", dependencies=[Depends(assistant)])
async def pair(request: Request, prof=Depends(secret_profile)):
    uid = prof["id"]
    if not allowed(uid):
        raise HTTPException(403, "reMarkable ist aus")
    guard.limit(request, "rmpair", uid)
    import iphone
    body = await iphone._json(request, 1024)
    try:
        tok = await register(body.get("code"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (CloudError, httpx.HTTPError, netguard.Blocked) as e:
        raise HTTPException(502, "reMarkable nicht erreichbar: " + type(e).__name__)
    d = load(uid)
    d.update(token=vault.seal(tok), paired=int(time.time()), docs=d.get("docs", {}))
    d.pop("error", None)
    save(uid, d)
    _user.pop(uid, None)
    guard.log("remarkable_pair", ip=guard.client_ip(request), profile=uid)
    _start(uid, listing_only=True)
    return public(uid)


_tasks = set()


def _start(uid, listing_only=False):
    """Runs the listing (after pairing) or a comparison in the background; the page asks for the state."""
    if not BACKGROUND:
        return
    async def go():
        if listing_only:
            _busy.add(uid)
            try:
                await refresh_library(uid)
            except Exception as e:
                d = load(uid)
                d["error"] = _redact(f"{type(e).__name__}: {e}") if isinstance(e, (CloudError, ValueError)) else type(e).__name__
                save(uid, d)
            finally:
                _busy.discard(uid)
        else:
            await run(uid)
    t = asyncio.create_task(go())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


@router.delete("/api/profile/remarkable", dependencies=[Depends(assistant)])
async def unpair(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    guard.limit(request, "rm", uid)
    forget(uid)
    guard.log("remarkable_unpair", ip=guard.client_ip(request), profile=uid)
    return {"ok": True, "hint": "Entferne das Gerät „desktop-linux“ auch auf my.remarkable.com unter Geräte."}


def forget(uid):
    """The connection and what came from the notebooks (their documents) go; the reMarkable keeps its notes."""
    d = load(uid)
    for st in d.get("docs", {}).values():
        documents.delete(uid, st.get("doc", ""))
    for f in (_file(uid), _libfile(uid)):
        try:
            os.remove(f)
        except OSError:
            pass
    _user.pop(uid, None)


def _own_count(uid):
    have = os.path.exists(_file(uid)) or os.path.exists(_libfile(uid))
    return int(have) + len(load(uid)["docs"]) if have else 0


# own data for Ich while the admin blocks the reMarkable for the profile (features.OWN): the connection and its documents
features.OWN["remarkable"] = (_own_count, forget)


@router.put("/api/profile/remarkable/pick", dependencies=[Depends(assistant)])
async def pick(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _on(prof)
    guard.limit(request, "rm", uid)
    import iphone
    body = await iphone._json(request, 64 * 1024)
    ids = body.get("ids")
    if not isinstance(ids, list) or len(ids) > MAX_PICKED or not all(isinstance(i, str) and ID.fullmatch(i) for i in ids):
        raise HTTPException(400, f"ids: a list of at most {MAX_PICKED} reMarkable ids")
    d = load(uid)
    d["picked"] = list(dict.fromkeys(ids))
    d["all"] = body.get("all") is True
    d["skip"] = [i for i in d.get("skip", []) if i not in d["picked"]]
    d["more"] = True          # read soon
    save(uid, d)
    return public(uid)


@router.put("/api/profile/remarkable/target", dependencies=[Depends(assistant)])
async def target(request: Request, prof=Depends(browser_profile)):
    """Ich → reMarkable → "Ablegen in": one folder of the own account ("" = "Spark"). Only where new documents go."""
    uid = prof["id"]
    _on(prof)
    if not send_allowed(uid):
        raise HTTPException(403, "Aufs reMarkable schicken ist aus (Funktionen → Aufs reMarkable schicken)")
    guard.limit(request, "rm", uid)
    import iphone
    body = await iphone._json(request, 1024)
    t = body.get("id") or ""
    items = library(uid)
    if t and (not isinstance(t, str) or not ID.fullmatch(t) or not (items.get(t) or {}).get("folder")
              or path_of(items, t) is None):
        raise HTTPException(400, "id: ein Ordner aus deiner reMarkable-Liste (nicht im Papierkorb)")
    d = load(uid)
    if t:
        d["target"] = t
    else:
        d.pop("target", None)
    save(uid, d)
    return public(uid)


@router.post("/api/profile/remarkable/sync", dependencies=[Depends(assistant)])
async def sync_now(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    _on(prof)
    guard.limit(request, "rmsync", uid)
    if not load(uid).get("token"):
        raise HTTPException(400, "nicht verbunden")
    if vorrang.speaking():
        raise HTTPException(409, "gerade wird gesprochen; gleich noch einmal")
    if uid in _busy:
        raise HTTPException(409, "der Abgleich läuft schon")
    _auto_last[uid] = time.time()
    _start(uid)
    await asyncio.sleep(0)
    return dict(public(uid), busy=True)


def _live_job(uid, t0, ok):
    """Zustand → Live: the button "Aufs reMarkable" as a way to the cloud (never the title)."""
    try:
        import live
        live.job("Aufs reMarkable", "reMarkable", t0, ok=ok, uid=uid)
    except Exception:
        pass


@router.post("/api/profile/remarkable/send", dependencies=[Depends(assistant)])
async def send_route(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    if not send_allowed(uid):
        raise HTTPException(403, "Aufs reMarkable schicken ist aus (Funktionen → Aufs reMarkable schicken)")
    guard.limit(request, "rmsend", uid)
    import iphone
    body = await iphone._json(request, 4 * MAX_SEND + 4096)
    if not load(uid).get("token"):
        raise HTTPException(400, "nicht verbunden")
    t0 = time.time()
    try:
        r = await send(uid, body.get("title"), body.get("text"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (CloudError, httpx.HTTPError, netguard.Blocked, netguard.TooLarge) as e:
        why = _redact(e) if isinstance(e, CloudError) else type(e).__name__
        print("remarkable: sending failed:", why, flush=True)
        _live_job(uid, t0, False)
        raise HTTPException(502, "reMarkable hat das Dokument nicht angenommen: " + why)
    _live_job(uid, t0, True)
    guard.log("remarkable_send", ip=guard.client_ip(request), profile=uid)
    return {"ok": True, "title": r["title"], "where": r["where"], "lost": r["lost"]}
