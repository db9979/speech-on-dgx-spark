"""reMarkable notebooks as knowledge (V01.0.270, plan plaene/remarkable.md).

A profile connects its own my.remarkable account (reMarkable 2, Paper Pro, Paper Pro Move) with a one-time
code from my.remarkable.com, like reMarkable's desktop app does. There is no official interface: this
uses the same sync protocol ("sync15") as rmapi, the Obsidian plugin and remarkable-mcp (MIT, used as a
model). reMarkable can change it; "Verbindung prüfen" then says so, uploading a PDF stays as a way.

- Off until the admin allows it (Funktionen: chat.remarkable below "Bilder und Scans lesen") and the
  profile switches it on (rm_on); guests never. The long-lived device token is sealed in the vault
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
  profile rm_send, also off): an answer or a dictated note as a new EPUB in the folder "Spark"; existing
  documents are never changed, moved or deleted.

Connections go through netguard (PUBLIC) to the fixed reMarkable hosts only (ALLOWED); redirects are
followed by hand and only to these hosts; the login header only goes to the host it was made for.
Answers have a byte cap, page files a size cap, parsing runs off the event loop.

    GET    /api/profile/remarkable          state, library with what is picked (own login)
    POST   /api/profile/remarkable/pair     {"code"}  connect (browser login, fresh code with MFA)
    DELETE /api/profile/remarkable          disconnect: token and all notebooks gone from the Spark
    PUT    /api/profile/remarkable/pick     {"ids": [...], "all": bool}  what is read
    POST   /api/profile/remarkable/sync     compare now (also refreshes the library)
    POST   /api/profile/remarkable/send     {"title", "text"}  an answer onto the reMarkable (rm_send)
"""
import asyncio
import base64
import hashlib
import html
import io
import json
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
import netguard
import profiles
import vault
import vorrang
from core import assistant, browser_profile, secret_profile

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
TIMEOUT = httpx.Timeout(60, connect=10)
CONCURRENT = 6
SEND_DAY = 20               # uploads per profile and day
MAX_SEND = 60_000           # characters of one upload
SIDE = documents.SIDE
_user = {}                  # uid -> (user token, until)
_busy = set()               # profiles being compared right now
_progress = {}              # uid -> [entries read, entries to read] while the list loads
_auto_last = {}             # uid -> when the background comparison last ran (in memory)
BACKGROUND = True           # tests run the listing and the comparison themselves


class CloudError(RuntimeError):
    pass


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


async def _authed(uid, method, url, most=MAX_INDEX, headers=None, **kw):
    r = await _request(method, url, await user_token(uid), most, headers, **kw)
    if r.status_code == 401:
        r = await _request(method, url, await user_token(uid, fresh=True), most, headers, **kw)
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


def _clean(v, n=120):
    return re.sub(r"[\x00-\x1f\x7f<>\"\\]", "", str(v or ""))[:n].strip()


async def refresh_library(uid):
    """The account's documents and folders: {id: {"h", "name", "parent", "folder", "kind", "n", "mod"}}.
    Entries whose hash did not change are taken from the last listing."""
    rh, _ = await root(uid)
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

    failed = 0
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
            if e["id"] in old:        # a hiccup never makes a notebook disappear: the last listing stays
                out[e["id"]] = old[e["id"]]
    if failed > max(3, len(todo) // 10):
        raise CloudError(f"{failed} of {len(todo)} entries could not be read; try again later")
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
def parse_page(data, draw=True):
    """(typed text, [highlighted texts], JPEG of the handwriting or None, has ink) of one v6 page file.
    Raises ValueError for other formats (old firmware) or broken files."""
    if not data.startswith(b"reMarkable .lines file, version=6"):
        raise ValueError("old page format (please update the reMarkable)")
    from rmscene import scene_items as si
    from rmscene import scene_stream as ss
    from rmscene.text import TextDocument
    typed, marks, lines, points = [], [], [], 0
    for b in ss.read_blocks(io.BytesIO(data)):
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
        res["docs"] += 1
        res["pages"] += got["fetched"]
        save(uid, d)
    d["last"] = int(time.time())
    d["count"] = len(d["docs"])
    d.pop("error", None)
    if full:
        d["error"] = "Der Speicher für Dokumente ist voll (Ich → Dokumente)."
    save(uid, d)
    return res


async def _notebook(uid, rid, it, path, st, draw, budget):
    files = parse_index(await blob(uid, it["h"], rid + ".docSchema"))
    byid = {f["id"]: f for f in files}
    cf = byid.get(rid + ".content")
    content = _json_of(await blob(uid, cf["hash"], cf["id"], MAX_META)) if cf else {}
    order = page_order(content)[:MAX_PAGES]
    old = st.get("pages") or {}
    texts = documents.notebook_texts(uid, st.get("doc", ""))
    pages, new_map, fetched, ink_skipped, failed = [], {}, 0, False, 0
    for n, pid in enumerate(order, 1):
        f = byid.get(f"{rid}/{pid}.rm")
        if not f:
            continue                      # an empty page (or a PDF page without notes)
        o = old.get(pid)
        if o and o[0] == f["hash"] and not (draw and o[2]) and o[1] in texts:
            pages.append((n, texts[o[1]], None))
            new_map[pid] = [f["hash"], n, o[2]]
            continue
        if fetched >= budget:
            break
        fetched += 1
        try:
            data = await blob(uid, f["hash"], f["id"], MAX_PAGE)
            typed, marks, jpeg, ink = await asyncio.wait_for(asyncio.to_thread(parse_page, data, draw), 60)
        except (ValueError, asyncio.TimeoutError, CloudError, httpx.HTTPError) as e:
            failed += 1
            print("remarkable: page not read:", type(e).__name__, flush=True)
            continue
        except Exception as e:            # rmscene on a file it does not know
            failed += 1
            print("remarkable: page not read:", type(e).__name__, flush=True)
            continue
        skipped = ink and not draw
        ink_skipped = ink_skipped or skipped
        pages.append((n, page_text(typed, marks), jpeg))
        new_map[pid] = [f["hash"], n, 1 if skipped else 0]
    notes = []
    if len(page_order(content)) > MAX_PAGES:
        notes.append(f"nur die ersten {MAX_PAGES} Seiten")
    if ink_skipped:
        notes.append("Handschrift nicht gelesen („Bilder und Scans lesen“ ist aus)")
    if failed:
        notes.append(f"{failed} Seite{'n' if failed > 1 else ''} nicht lesbar")
    if it.get("mod"):
        notes.append("geändert am " + time.strftime("%d.%m.%Y", time.localtime(it["mod"])))
    doc, left = await asyncio.to_thread(documents.notebook_put, uid, st.get("doc"), path, pages, "; ".join(notes))
    cut = fetched >= budget and len(new_map) < len([p for p in order if f"{rid}/{p}.rm" in byid])
    return {"fetched": fetched, "state": {"doc": doc, "h": "" if cut else it["h"], "pages": new_map,
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
            continue
        _auto_last[uid] = now
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
        print("remarkable: comparison failed:", type(e).__name__, flush=True)
        return None
    d = load(uid)
    d["more"] = res["more"]
    save(uid, d)
    print(f"remarkable: {res['docs']} notebook(s), {res['pages']} page(s) new, {res['removed']} removed", flush=True)
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
    if r.status_code not in (200, 201, 204):
        raise CloudError(f"upload HTTP {r.status_code}")
    return {"hash": h, "id": name, "size": len(data)}


async def _new_doc(uid, name, files):
    """Uploads the files of one new document and its index; returns its root line."""
    entries = [await _put(uid, data, fid) for fid, data in files]
    entries.sort(key=lambda e: e["id"])
    body = ("3\n" + "".join(f"{e['hash']}:0:{e['id']}:0:{e['size']}\n" for e in entries)).encode()
    dh = hashlib.sha256(b"".join(bytes.fromhex(e["hash"]) for e in entries)).hexdigest()
    await _put(uid, body, name + ".docSchema", h=dh)
    return {"hash": dh, "id": name, "subfiles": len(entries), "size": sum(e["size"] for e in entries)}


async def _add_to_root(uid, new):
    """Adds documents to the root index (generation-checked, a few tries when another device was faster).
    Only appends lines; the existing ones are written back unchanged."""
    for attempt in range(4):
        rh, gen = await root(uid)
        entries = parse_index(await blob(uid, rh, "root.docSchema"))
        have = {e["id"] for e in entries}
        entries += [e for e in new if e["id"] not in have]
        entries.sort(key=lambda e: e["id"])
        body = ("4\n" + f"0:.:{len(entries)}:{sum(e['size'] for e in entries)}\n" +
                "".join(f"{e['hash']}:0:{e['id']}:{e['subfiles']}:{e['size']}\n" for e in entries)).encode()
        nh = (await _put(uid, body, "root.docSchema", "text/plain; charset=UTF-8"))["hash"]
        r = await _authed(uid, "PUT", ROOT_PUT_URL, most=64 * 1024, headers={"rm-filename": "roothash"},
                          json={"broadcast": True, "hash": nh, "generation": gen})
        if r.status_code in (409, 412, 428):
            await asyncio.sleep(1 + attempt)
            continue
        if r.status_code not in (200, 201):
            raise CloudError(f"root HTTP {r.status_code}")
        return
    raise CloudError("another device kept writing; try again")


def _meta(name, parent, kind):
    now = str(int(time.time() * 1000))
    return json.dumps({"createdTime": now, "deleted": False, "lastModified": now, "lastOpened": "0", "lastOpenedPage": 0,
                       "metadatamodified": False, "modified": False, "new": False, "parent": parent, "pinned": False,
                       "source": "", "synced": False, "type": kind, "version": 1, "visibleName": name}, sort_keys=True).encode()


async def send(uid, title, text):
    """A new EPUB with this text in the folder "Spark" (created when missing). Nothing else is changed."""
    title = _clean(title, 80) or "Vom Spark"
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text or ""))[:MAX_SEND].strip()
    if not text:
        raise ValueError("nothing to send")
    d = load(uid)
    day = time.strftime("%Y-%m-%d")
    s = d.get("sent") if isinstance(d.get("sent"), dict) and d["sent"].get("day") == day else {"day": day, "n": 0}
    if s["n"] >= SEND_DAY:
        raise ValueError(f"heute schon {SEND_DAY} Mal geschickt; morgen wieder")
    items = await refresh_library(uid)
    folder = next((i for i, it in items.items() if it.get("folder") and it["name"] == "Spark" and not it["parent"]), None)
    new = []
    if not folder:
        folder = str(uuid.uuid4())
        new.append(await _new_doc(uid, folder, [(folder + ".metadata", _meta("Spark", "", "CollectionType"))]))
    did = str(uuid.uuid4())
    book = epub(title, text)
    content = json.dumps({"coverPageNumber": -1, "documentMetadata": {"title": title}, "dummyDocument": False,
                          "extraMetadata": {}, "fileType": "epub", "fontName": "", "formatVersion": 1, "lineHeight": -1,
                          "margins": 100, "orientation": "portrait", "pageCount": 0, "pages": [], "tags": [],
                          "textScale": 1}, sort_keys=True).encode()
    new.append(await _new_doc(uid, did, [(did + ".content", content), (did + ".metadata", _meta(title, folder, "DocumentType")),
                                        (did + ".pagedata", b"\n"), (did + ".epub", book)]))
    await _add_to_root(uid, new)
    d = load(uid)
    s["n"] += 1
    d["sent"] = s
    save(uid, d)
    return title


# ---------------------------------------------------------------- the assistant: a dictated note
NOTE_TOOL = {"type": "function", "function": {
    "name": "remarkable_note",
    "description": "Puts a note the user dictates onto the user's reMarkable tablet (a new document in the folder "
                   "\"Spark\"). Only when the user asks for it in this message.",
    "parameters": {"type": "object", "properties": {
        "title": {"type": "string", "description": "Short title, at most 8 words"},
        "text": {"type": "string", "description": "The text of the note, as the user said it"}},
        "required": ["title", "text"]}}}
NOTE_HINT = ("remarkable_note puts a note the user dictates onto the user's reMarkable as a new document; use it only "
             "when the user asks to write or send something to the reMarkable.")
WORDS = re.compile(r"re\s?markable|remarkabel|e-?ink[- ]?tablet", re.I)


def offer(ctx):
    """Only in the profile's own session, only when the person's own words name the reMarkable."""
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False:
        return None
    if not send_allowed(who["id"]) or not load(who["id"]).get("token"):
        return None
    if not WORDS.search(str(ctx.get("text") or "")):
        return None
    return {"tools": [NOTE_TOOL], "hint": NOTE_HINT, "changes": {"remarkable_note"},
            "filler": {"remarkable_note": ("Ich schicke es aufs reMarkable.", "Sending it to the reMarkable.")}}


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    if name != "remarkable_note" or not send_allowed(uid):
        return "Aufs reMarkable schicken ist aus."
    try:
        t = await send(uid, args.get("title"), args.get("text"))
        return f"Auf dem reMarkable liegt jetzt „{t}“ im Ordner Spark."
    except (CloudError, ValueError, httpx.HTTPError) as e:
        return "Nicht geschickt: " + _redact(e if isinstance(e, ValueError) else type(e).__name__)


async def briefing(uid, zone=None):
    return ""


# ---------------------------------------------------------------- routes
def _on(prof=Depends(browser_profile)):
    if not allowed(prof["id"]):
        raise HTTPException(403, "reMarkable ist aus (Funktionen und Ich → reMarkable)")
    return prof


def public(uid):
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
            "sent_today": (d.get("sent") or {}).get("n", 0) if (d.get("sent") or {}).get("day") == time.strftime("%Y-%m-%d") else 0,
            "send_day": SEND_DAY, "busy": uid in _busy, "progress": list(_progress.get(uid) or [])}


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
    d = load(uid)
    for st in d.get("docs", {}).values():
        documents.delete(uid, st.get("doc", ""))
    for f in (_file(uid), _libfile(uid)):
        try:
            os.remove(f)
        except OSError:
            pass
    _user.pop(uid, None)
    guard.log("remarkable_unpair", ip=guard.client_ip(request), profile=uid)
    return {"ok": True, "hint": "Entferne das Gerät „desktop-linux“ auch auf my.remarkable.com unter Geräte."}


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


@router.post("/api/profile/remarkable/send", dependencies=[Depends(assistant)])
async def send_route(request: Request, prof=Depends(browser_profile)):
    uid = prof["id"]
    if not send_allowed(uid):
        raise HTTPException(403, "Aufs reMarkable schicken ist aus (Funktionen und Ich → reMarkable)")
    guard.limit(request, "rmsend", uid)
    import iphone
    body = await iphone._json(request, 4 * MAX_SEND + 4096)
    if not load(uid).get("token"):
        raise HTTPException(400, "nicht verbunden")
    try:
        t = await send(uid, body.get("title"), body.get("text"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (CloudError, httpx.HTTPError, netguard.Blocked, netguard.TooLarge) as e:
        raise HTTPException(502, "reMarkable: " + _redact(type(e).__name__))
    guard.log("remarkable_send", ip=guard.client_ip(request), profile=uid)
    return {"ok": True, "title": t}
