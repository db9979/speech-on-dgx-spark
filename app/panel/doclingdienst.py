"""Docling-Server anbinden (plan plaene/docling-anbinden.md): the admin connects a docling-serve in the home network
(Docker on another machine), and uploaded documents are read a second time, better, in quiet moments.

How it runs:
- An upload is read on the Spark at once as before (documents.py: pypdf, Office parts) and can be searched right
  away. When Docling is allowed for the profile, documents.add also marks the document "wartet auf Docling" and keeps
  the file until then (users/<id>/docling-wait/, or the kept original), at most WAIT_DAYS days.
- due_once (called first by wissen.due_once, only while nobody talks to the assistant) sends one file at a time to
  POST /v1/convert/file/async, waits for the task and takes the Markdown (tables, headings, reading order, OCR of
  scanned pages). It replaces the document's text; the meaning vectors and the "Steckbrief" are made again. Pages the
  language model would have read (wissen.read_page) are dropped where Docling found text; the rest stays for it.
- Server off, unreachable, refused certificate or key: nothing is lost, the document keeps the Spark's own text and
  the pages wait for the language model as before; after WAIT_DAYS the file is let go.

Switches: admin chat.docling (features "docling", below "Eigene Dokumente", off; ready only with an address), for all
profiles once on (Freigabe-Regel 2026-10-13); the profile's own preference "Mit Docling lesen" (settings doc_docling,
on unless the profile turned it off: its files leave the Spark). Guests have no documents.

Safety: only through netguard (HOME), with redirects off, so the file and the key go to exactly that address. https
is the recommendation and checks the certificate (or the one the admin accepted, zertpin.py); plain http only to an
address in the home network, checked again before every call, with a warning on the page. The key sits sealed in
the vault, is never shown again and never logged. What Docling sends back is outside text like every document: it
is stored as data, searched as outside text (chat.READS_OUTSIDE) and never an instruction. The file goes with a
neutral name ("dokument.pdf"), never the profile's file name. Answers are capped (MAX_ANSWER), the wait too.

    STATE/docling.json  {"url", "key" (sealed), "cert" (PEM, public), "last": {...}, "stats": {"day", "ok", "failed"}}
    GET  /api/admin/docling          the settings without the key, the counts
    PUT  /api/admin/docling          {"url", "key", "cert"} main admin with a fresh code
    POST /api/admin/docling/cert     {"url"?} the certificate the server shows, to compare
    POST /api/admin/docling/test     reads the built-in sample (a short PDF with a table) and says how it went
"""
import asyncio
import ipaddress
import os
import re
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import documents
import features
import guard
import netguard
import profiles
import vault
import zertpin
from common import read_json, write_json
from core import admin_code_fresh, auth, json_body

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "docling.json")
PREF = "doc_docling"           # the profile's preference (on unless turned off)
WAIT_DIR = "docling-wait"      # users/<id>/docling-wait/<doc id><ext>: the file until Docling has read it
WAIT_DAYS = 2
TYPES = documents.DOCLING_TYPES
CTYPE = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".html": "text/html", ".htm": "text/html",
         ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
         ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
DOC_TIMEOUT = 600              # one document at most this long on the server
MAX_ANSWER = 16 * 1024 * 1024  # the Markdown of one document
DOWN_WAIT = 600                # after the server did not answer: the next try this much later
TEXT_MIN = 40                  # a page with less text than this is left to the language model (documents.SCAN_TEXT)
TASK = re.compile(r"[A-Za-z0-9_\-]{1,100}")
_lock = threading.Lock()
profiles.NO_PRESET.add(PREF)   # only the profile itself says whether its files go to the server, never the admin's presets
_mem = {"down_until": 0.0, "now": None}     # now: {"uid"} while a file is with Docling


# ---------------------------------------------------------------- settings
def _read():
    return read_json(FILE, {})


def _write(d):
    write_json(FILE, d, mode=0o600)


def _update(**kw):
    with _lock:
        d = _read()
        d.update(kw)
        _write(d)
        return d


def set_up(c=None):
    """features.READY: an address is stored."""
    return bool(_read().get("url"))


def admin_on(c=None):
    return features.admin_on("docling", c)


def allowed(uid, c=None):
    """The admin's switch (with an address) and the profile's own preference; never for guests."""
    if not uid or not features.allowed("docling", uid, c):
        return False
    return profiles.settings(uid).get(PREF, True) is not False


def wanted(uid, name, text=None):
    """Should this upload wait for Docling? Only files (not text an app read itself) of a kind Docling reads."""
    return text is None and os.path.splitext(str(name).lower())[1] in TYPES and allowed(uid)


def _lan_only(host, port):
    """Plain http only to the home network: every address of the name must be a private one (checked before each call)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("name not found")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_private or ip.is_link_local:
            raise ValueError("http only for an address in the home network; otherwise https")


def check_url(url):
    """The base address (no trailing /): https anywhere netguard allows, http only for the home network."""
    url = str(url or "").strip()
    u = urlsplit(url)
    if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password or u.query or u.fragment \
            or len(url) > 300 or re.search(r"[\s\x00-\x1f]", url):
        raise ValueError("the address must start with https:// or http:// and hold no login, ? or #")
    try:
        u.port
    except ValueError:
        raise ValueError("invalid port")
    return url.rstrip("/")


def _port(u):
    return u.port or (443 if u.scheme == "https" else 80)


def view():
    d = _read()
    url = d.get("url", "")
    return {"on": admin_on(), "url": url, "plain": url.startswith("http://"), "has_key": bool(d.get("key")),
            "cert": zertpin.sha_of(d.get("cert")), "last": d.get("last"), "stats": _stats(d),
            "down": _mem["down_until"] > time.time(), "busy": _mem["now"] is not None}


def _stats(d=None):
    d = _read() if d is None else d
    s = d.get("stats") if isinstance(d.get("stats"), dict) else {}
    if s.get("day") != time.strftime("%Y-%m-%d"):
        return {"ok": 0, "failed": 0, "pages": 0}
    return {k: int(s.get(k) or 0) for k in ("ok", "failed", "pages")}


def _count(ok, pages=0):
    with _lock:
        d = _read()
        s = dict(_stats(d), day=time.strftime("%Y-%m-%d"))
        s["ok" if ok else "failed"] += 1
        s["pages"] += int(pages or 0)
        d["stats"] = s
        _write(d)


# ---------------------------------------------------------------- talking to docling-serve
class Problem(Exception):
    """kind: "down" (not reachable: try again later), "cert", "key", "blocked" (the Wächter), "failed" (this file)."""
    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def _client(d, timeout):
    url = d.get("url") or ""
    if not url:
        raise Problem("down")
    u = urlsplit(url)
    if u.scheme == "http":
        try:
            _lan_only(u.hostname, _port(u))
        except ValueError:
            raise Problem("blocked")
    verify = zertpin.verify(d.get("cert")) if u.scheme == "https" else True
    return netguard.client(netguard.HOME, origin=url, max_bytes=MAX_ANSWER, verify=verify, follow_redirects=False,
                           timeout=httpx.Timeout(timeout, connect=10))


def _headers(d):
    key = vault.open_(d.get("key") or "") if d.get("key") else ""
    return {"X-Api-Key": key} if key else {}


def _status(r):
    if r.status_code in (401, 403):
        raise Problem("key")
    if r.status_code >= 500 or r.status_code in (404, 405):
        raise Problem("down" if r.status_code in (502, 503, 504) else "failed")
    if r.status_code >= 400:
        raise Problem("failed")


def _split(md, mark):
    """[(page, text)] from the Markdown: pages where Docling marked the breaks, else one piece."""
    md = re.sub(r"<!--.*?-->", "", md.replace(mark, "\f"), flags=re.S)   # image placeholders and other comments
    parts = md.split("\f")
    if len(parts) == 1:
        return [(None, parts[0].strip())] if parts[0].strip() else []
    return [(i + 1, p.strip()) for i, p in enumerate(parts) if p.strip()]


async def convert(name, data, deadline=DOC_TIMEOUT + 60):
    """[(page or None, Markdown)] of one file from the Docling server; raises Problem."""
    d = _read()
    ext = os.path.splitext(str(name).lower())[1]
    if ext not in TYPES:
        raise Problem("failed")
    mark = "SPARKPAGE" + secrets.token_hex(8)      # a page break nobody can put into a document beforehand
    form = {"to_formats": "md", "image_export_mode": "placeholder", "do_ocr": "true", "include_images": "false",
            "ocr_lang": ["de", "en"], "md_page_break_placeholder": mark, "abort_on_error": "false",
            "document_timeout": str(DOC_TIMEOUT)}
    base, h = d.get("url", ""), _headers(d)
    t_end = time.monotonic() + deadline
    try:
        async with _client(d, 60) as c:
            r = await c.post(base + "/v1/convert/file/async", headers=h, data=form,
                             files={"files": ("dokument" + ext, data, CTYPE.get(ext, "application/octet-stream"))})
            _status(r)
            task = r.json()
            tid = str(task.get("task_id") or "")
            if not TASK.fullmatch(tid):
                raise Problem("failed")
            st = task.get("task_status")
            while st not in ("success", "failure"):
                if time.monotonic() > t_end:
                    raise Problem("failed")
                r = await c.get(f"{base}/v1/status/poll/{tid}", headers=h, params={"wait": "10"})
                _status(r)
                st = r.json().get("task_status")
                if st not in ("success", "failure"):
                    await asyncio.sleep(2)
            if st == "failure":
                raise Problem("failed")
            r = await c.get(f"{base}/v1/result/{tid}", headers=h)
            _status(r)
            res = r.json()
    except Problem:
        raise
    except netguard.Blocked:
        raise Problem("blocked")
    except (httpx.HTTPError, OSError, netguard.TooLarge, ValueError) as e:
        if zertpin.problem(e):
            raise Problem("cert")
        if isinstance(e, (httpx.TransportError, OSError)):
            raise Problem("down")
        raise Problem("failed")
    if not isinstance(res, dict) or res.get("status") not in ("success", "partial_success"):
        raise Problem("failed")
    md = (res.get("document") or {}).get("md_content") if isinstance(res.get("document"), dict) else None
    if not isinstance(md, str):
        raise Problem("failed")
    return _split(md, mark)


async def health():
    """True when the server answers /health (no key needed there)."""
    d = _read()
    try:
        async with _client(d, 10) as c:
            r = await c.get(d["url"] + "/health")
            return r.status_code < 400
    except (Problem, netguard.Blocked, httpx.HTTPError, OSError, netguard.TooLarge, ValueError):
        return False


# ---------------------------------------------------------------- background work (wissen.due_once)
WORD = {"down": "nicht erreichbar", "cert": "Zertifikat passt nicht", "key": "Schlüssel abgelehnt",
        "blocked": "vom Wächter nicht erlaubt", "failed": "nicht lesbar", "old": "zu lange gewartet"}


async def due_once(now=None):
    """One file to Docling, if one waits and the server may be asked now. Returns "docling" or None."""
    now = time.time() if now is None else now
    ids = profiles.user_ids()
    if not admin_on():
        for uid in ids:   # switched off meanwhile: the files go, the pages wait for the language model again
            await asyncio.to_thread(documents.docling_release, uid)
        return None
    if _mem["down_until"] > now:
        return None
    for uid in ids:
        if not allowed(uid):
            await asyncio.to_thread(documents.docling_release, uid)
            continue
        nxt = await asyncio.to_thread(documents.docling_next, uid, now - WAIT_DAYS * 86400)
        if not nxt:
            continue
        doc, name, path = nxt
        try:
            with open(path, "rb") as f:
                data = f.read(documents.MAX_PDF + 1)
        except OSError:
            await asyncio.to_thread(documents.docling_done, uid, doc, None, "failed")
            continue
        _mem["now"] = {"uid": uid}
        t0 = time.time()
        try:
            pages = await convert(name, data)
        except Problem as e:
            ok = False
            if e.kind in ("down", "cert", "key", "blocked"):
                _mem["down_until"] = now + DOWN_WAIT     # the file waits; the server is asked again later
                _update(last={"t": int(time.time()), "ok": False, "why": e.kind})
                print(f"docling: server {e.kind} | retry in {DOWN_WAIT // 60} min", flush=True)
            else:
                await asyncio.to_thread(documents.docling_done, uid, doc, None, "failed")
                _count(False)
                print("docling: file not read | failed |", profiles.log_name(profiles.by_id(uid) or {"id": uid}), flush=True)
        else:
            ok = True
            n = await asyncio.to_thread(documents.docling_done, uid, doc, pages, "", TEXT_MIN)
            _count(True, n)
            _update(last={"t": int(time.time()), "ok": True, "seconds": round(time.time() - t0)})
            print(f"docling: read | {n} pages | {round(time.time() - t0)} s |",
                  profiles.log_name(profiles.by_id(uid) or {"id": uid}), flush=True)
        finally:
            _mem["now"] = None
        try:
            import live
            live.job("Dokument lesen", "Docling", t0, ok=ok, uid=uid)
        except Exception:
            pass
        return "docling"
    return None


def for_live():
    """Zustand → Live: the Docling line in numbers (waiting files, read and failed today), never a name or text."""
    if not admin_on():
        return {"on": False}
    wait = sum(documents.docling_waiting(u) for u in profiles.user_ids())
    s = _stats()
    return {"on": True, "wait": wait, "ok": s["ok"], "failed": s["failed"], "pages": s["pages"],
            "down": _mem["down_until"] > time.time(), "busy": _mem["now"] is not None}


# ---------------------------------------------------------------- the sample for "Probe lesen"
def sample_pdf():
    """A one-page PDF with a heading and a small table, made here (nothing from outside)."""
    lines = [("F2", 18, 72, 760, "Probe fuer den Spark"), ("F1", 11, 72, 730, "Docling liest Tabellen und Ueberschriften."),
             ("F2", 11, 72, 700, "Monat"), ("F2", 11, 220, 700, "Strom kWh"), ("F2", 11, 340, 700, "Wasser m3"),
             ("F1", 11, 72, 682, "Januar"), ("F1", 11, 220, 682, "312"), ("F1", 11, 340, 682, "9"),
             ("F1", 11, 72, 664, "Februar"), ("F1", 11, 220, 664, "287"), ("F1", 11, 340, 664, "8")]
    body = "".join(f"BT /{f} {s} Tf {x} {y} Td ({t}) Tj ET\n" for f, s, x, y, t in lines)
    body += "0.5 w 70 696 m 420 696 l S 70 678 m 420 678 l S 70 660 m 420 660 l S\n"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}endstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    return out.encode("latin-1")


# ---------------------------------------------------------------- endpoints (admin; changes main admin with a code)
SAY = {"down": "Der Docling-Server antwortet nicht.", "cert": "Das Zertifikat passt nicht zur Adresse. Unter "
       "„Zertifikat prüfen“ den Fingerabdruck vergleichen und annehmen.", "key": "Der Docling-Server lehnt den "
       "Schlüssel ab.", "blocked": "Der Wächter erlaubt diese Adresse nicht (http nur im Heimnetz).",
       "failed": "Der Docling-Server konnte die Probe nicht lesen."}


@router.get("/api/admin/docling", dependencies=[Depends(auth)])
def docling_get():
    return view()


# the address and the key decide where the profiles' documents go: the main admin with a fresh code every time
@router.put("/api/admin/docling", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def docling_put(request: Request):
    guard.limit(request, "docling", admin=True)
    b = await json_body(request, 2048)
    d = _read()
    url = d.get("url", "")
    if "url" in b:
        raw = str(b["url"]).strip()
        try:
            url = check_url(raw) if raw else ""
            if url.startswith("http://"):
                u = urlsplit(url)
                await asyncio.to_thread(_lan_only, u.hostname, _port(u))
        except ValueError as e:
            raise HTTPException(400, str(e))
    new = dict(d, url=url)
    if url != d.get("url", ""):
        new.pop("cert", None)      # a new address: its certificate is checked anew
        if d.get("key") and not b.get("key"):
            new["key"] = ""        # and the key typed again, so it never goes to a server it was not meant for
    if "cert" in b:                # the fingerprint the admin compared: accepted only if the server shows it now
        want = b["cert"]
        if not isinstance(want, str) or len(want) > 200:
            raise HTTPException(400, "cert: a fingerprint")
        if not want:
            new.pop("cert", None)
        else:
            if not url.startswith("https://"):
                raise HTTPException(400, "only https addresses have a certificate")
            try:
                got = await zertpin.fetch(url, netguard.HOME)
            except (OSError, ValueError, asyncio.TimeoutError, netguard.Blocked):
                raise HTTPException(502, SAY["down"])
            if got["sha256"] != want.strip().upper():
                raise HTTPException(409, "Der Server zeigt jetzt ein anderes Zertifikat als eben. Noch einmal prüfen.")
            new["cert"] = got["pem"]
    key = b.get("key")
    if isinstance(key, str) and key:
        if len(key) > 256 or re.search(r"[\x00-\x20\x7f]", key):
            raise HTTPException(400, "key: up to 256 visible characters")
        new["key"] = vault.seal(key)
    with _lock:
        _write(new)
    _mem["down_until"] = 0.0
    guard.log("docling_settings", detail=f"{urlsplit(url).scheme or '-'} {urlsplit(url).hostname or '-'}"
              + (" Schlüssel" if isinstance(key, str) and key else "")
              + (" Zertifikat angenommen" if new.get("cert") and new.get("cert") != d.get("cert") else ""))
    return view()


@router.post("/api/admin/docling/cert", dependencies=[Depends(auth)])
async def docling_cert(request: Request):
    """{"url"?}: the certificate the server shows (fingerprint, names, until, fits the address), to compare. Reads
    only; accepting it is PUT {"cert": fingerprint} with a fresh code."""
    guard.limit(request, "docling", admin=True)
    b = await json_body(request, 1024)
    try:
        url = check_url(b.get("url") or _read().get("url", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not url.startswith("https://"):
        raise HTTPException(400, "only https addresses have a certificate")
    try:
        got = await zertpin.fetch(url, netguard.HOME)
    except netguard.Blocked:
        raise HTTPException(403, SAY["blocked"])
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(502, SAY["down"])
    pinned = zertpin.sha_of(_read().get("cert"))
    return {k: got[k] for k in ("sha256", "names", "until", "self_signed", "fits", "expired")} | {"pinned": pinned == got["sha256"]}


@router.post("/api/admin/docling/test", dependencies=[Depends(auth)])
async def docling_test(request: Request):
    """Reads the built-in sample on the stored server: reachable, key, certificate, tables. Sends nothing of a profile."""
    guard.limit(request, "docling", admin=True)
    if not _read().get("url"):
        raise HTTPException(400, "address first")
    t0 = time.time()
    try:
        pages = await convert("probe.pdf", sample_pdf(), deadline=120)
    except Problem as e:
        _update(last={"t": int(time.time()), "ok": False, "why": e.kind})
        guard.log("docling_test", detail=e.kind)
        return {"ok": False, "why": e.kind, "say": SAY[e.kind]}
    text = "\n".join(t for _, t in pages)
    _mem["down_until"] = 0.0
    _update(last={"t": int(time.time()), "ok": True, "seconds": round(time.time() - t0)})
    guard.log("docling_test", detail="ok")
    # the sample is the Spark's own: its text may be shown (a table shows as | … | lines)
    return {"ok": True, "seconds": round(time.time() - t0, 1), "chars": len(text), "table": "|" in text,
            "text": text[:600]}
