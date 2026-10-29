"""Fernzugang, Dateien (plan ssh-vermittlung stage 3, Dominik 2026-10-28 „2-4“): the files of a paired remote server
in the browser over SFTP, inside one SSH connection like the shell's (fernzugang.aufbauen with art "dateien": the
anchor's pipe, paramiko, the host key pinned at pairing, the panel's own key from the vault, the user `spark`).

Rules (fixed, Sicherheits-Checkliste):
- Admins in their own browser only (fernzugang.is_admin_browser; the apps open it as a panel page), never the
  Verwalter, guests, a device key or the model; the switch chat.fernzugang and the Notaus as for the shell. „Dateien“
  works only on the unlocked page (fernzugang._frei, rule „Bereich entsperren“: its code or passkey came first; locked
  every door but closing answers 423) and opens one session bound to that login (only the hash of its cookies), counted with the shell sessions (chat.fernzugang_sitzungen); idle ends it
  (chat.fernzugang_leerlauf_min).
- What the remote user `spark` may do there is what counts: the panel reads and writes only with that user's own
  permissions on the server. A path is a plain absolute path (no control characters, at most PATH_MAX), made normal
  with posixpath; a name for an upload is one part (no „/“, not „.“ or „..“). Nothing the server says is a command:
  names, sizes and times are shown as text only.
- Upload: at most chat.fernzugang_datei_mb MB (the Content-Length before, the bytes counted while reading), into a
  hidden part file next to the target, renamed only when complete (without „Ersetzen“ an SFTP rename, which never
  overwrites); a broken, stopped or too big upload leaves nothing behind. Download: the same limit, through a one-time
  link (LINK_S seconds, once, only its hash kept, only while its session lives), so the Android app's own download
  works too; neither the file name nor its path is in the link.
- Every action writes one journal line for every result in fixed words and numbers (count, KB), never a name, a path
  or a byte of a file. Live shows only how many file sessions and transfers run (fernzugang.counts). The Notaus,
  „Alle trennen“, „Trennen“ and the switch end the session and stop every transfer at its next piece.

    admin in the browser (core.auth + fernzugang.is_admin_browser):
    POST   /api/admin/fernzugang/dateien {geraet}             -> {"id", "pfad", "max_mb", "leerlauf"} (unlocked page)
    POST   /api/admin/fernzugang/dateien/{sid}/liste {pfad}   -> {"pfad", "oben", "eintraege", "mehr", "max_mb"}
    POST   /api/admin/fernzugang/dateien/{sid}/link {pfad}    -> {"url", "gilt_s"} (a one-time download link)
    POST   /api/admin/fernzugang/dateien/{sid}/hoch           raw body; headers x-fz-pfad, x-fz-name, x-fz-ersetzen
    DELETE /api/admin/fernzugang/dateien/{sid}                ends the session
    the one-time link (no login: the token is the key; LINK_S seconds, once, only while its session lives):
    GET    /api/fernzugang/datei?t=<token>                    -> the file (attachment)
"""
import asyncio
import hashlib
import hmac
import posixpath
import re
import secrets
import stat
import time
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import core
import fernzugang
import guard
from core import auth, json_body

router = APIRouter()

PATH_MAX = 4096         # characters of a path
NAME_MAX = 255          # characters of one name
LIST_MAX = 1000         # entries of one folder shown at most („mehr“ says there are more)
LINK_STAT = 200         # symbolic links in one folder looked up at most (to tell a folder from a file)
LINK_S = 60             # a download link works this long, once
LINKS_MAX = 20          # open download links at most
CHUNK = 64 * 1024       # bytes per piece, both ways
BAD = re.compile(r"[\x00-\x1f\x7f]")
TOKEN = re.compile(r"[A-Za-z0-9_\-]{40,50}")

LINKS = {}              # sha256(token) -> {"sid", "pfad", "name", "groesse", "until"}


def max_bytes(c=None):
    return 1024 * 1024 * fernzugang.datei_mb(c)


def pfad(v, home):
    """A normal absolute path from what the browser sent ("" or "~": the remote user's home); None when it is no
    plain path. The server's own permissions decide what can be read; this only keeps the text a path."""
    v = str(v if v is not None else "")
    if v in ("", "~"):
        return home
    if len(v) > PATH_MAX or BAD.search(v) or not v.startswith("/"):
        return None
    p = posixpath.normpath(v)
    return "/" + p.lstrip("/")


def name_ok(v):
    v = str(v or "")
    return bool(v) and len(v) <= NAME_MAX and "/" not in v and v not in (".", "..") and not BAD.search(v)


def _shown(name):
    """A remote name as text for the page (never interpreted): control characters out, length cut."""
    return BAD.sub("?", str(name))[:NAME_MAX]


def _art(mode):
    return "dir" if stat.S_ISDIR(mode) else "file" if stat.S_ISREG(mode) else "link" if stat.S_ISLNK(mode) else "other"


def _mb():
    return fernzugang.datei_mb()


# ---------------------------------------------------------------- the session
def _session(request, sid, word, frei=True):
    """The file session of this login, else 404/403/423/503 (switch, admin in the browser, the unlocked page, Notaus,
    the same login). Closing it works on the locked page too, like disconnecting the own shell."""
    if not fernzugang.admin_on():
        raise HTTPException(404, "Fernzugang ist aus (Funktionen → Fernzugang zu Servern)")
    fernzugang._browser(request)
    if frei:
        fernzugang._frei(request)
    if fernzugang._notaus(count=True):
        fernzugang.log(word, "notaus", 0)
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    s = fernzugang.SITZUNG.get(str(sid))
    if s is None or s.art != "dateien" or s.ende.is_set() or not hmac.compare_digest(s.login, fernzugang._login(request)):
        fernzugang.log(word, "keine sitzung", 0)
        raise HTTPException(404, "no such session")
    s.zuletzt = time.time()
    return s


def _sftp(s, fn):
    """One SFTP call in a thread, one at a time per session (the transfers interleave piece by piece)."""
    def run():
        with s.sftp_lock:
            return fn(s.sftp)
    return asyncio.to_thread(run)


def _err(e):
    """The fixed word for an SFTP error (never the server's text)."""
    if isinstance(e, PermissionError):
        return "verboten"
    if isinstance(e, FileNotFoundError):
        return "fehlt"
    return "fehler"


SAY = {"verboten": (403, "Das darf der Benutzer spark auf dem Server nicht."),
       "fehlt": (404, "Das gibt es auf dem Server nicht (mehr)."),
       "fehler": (502, "Der Server hat das nicht ausgeführt.")}


def _too_big():
    return HTTPException(413, f"Größer als {_mb()} MB (Funktionen → Fernzugang zu Servern).")


@router.post("/api/admin/fernzugang/dateien", dependencies=[Depends(auth)])
async def open_files(request: Request):
    """„Dateien“: on the unlocked page (its code or passkey came first) an SFTP session over the server's anchor,
    bound to this login."""
    fernzugang._on(request)
    fernzugang._second_step(request)
    fernzugang._frei(request)
    guard.limit(request, "fernzugang_sitzung", admin=True)
    body = await json_body(request, fernzugang.MAX_BODY)
    gid = str(body.get("geraet") or "")
    if not fernzugang.GID.fullmatch(gid):
        fernzugang.log("dateien_abgewiesen", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    prof = core.acting_profile(request)
    s, _g, why = await fernzugang.aufbauen(gid, "dateien", None, fernzugang._who(request), prof["id"] if prof else None,
                                           login=fernzugang._login(request), conn=request)
    if s is None:
        if why in ("voll", "offline"):     # the others are logged where they happen (aufbauen, Sitzung.end)
            fernzugang.log("dateien_abgewiesen", why, 0)
        raise HTTPException(*fernzugang.REFUSED.get("ssh" if why.startswith("ssh") else why, (502, "Die Dateien gingen nicht auf.")))
    try:
        home = await _sftp(s, lambda c: c.normalize("."))
    except Exception:
        await s.end("sftp")
        fernzugang.log("dateien_abgewiesen", "sftp", 0)
        raise HTTPException(502, "SFTP geht auf dem Server nicht (Subsystem sftp in der sshd_config).") from None
    s.home = home if isinstance(home, str) and home.startswith("/") and not BAD.search(home) else "/"
    s.tasks.append(asyncio.create_task(s._idle()))
    fernzugang.log("dateien_auf", s.who, len(fernzugang.SITZUNG))
    fernzugang._live("Fern-Dateien geöffnet")
    return {"id": s.id, "pfad": s.home, "max_mb": _mb(), "leerlauf": fernzugang.leerlauf_s() // 60}


@router.post("/api/admin/fernzugang/dateien/{sid}/liste", dependencies=[Depends(auth)])
async def listing(sid: str, request: Request):
    """One folder: names, kinds, sizes and times as text, folders first; at most LIST_MAX entries."""
    s = _session(request, sid, "liste")
    guard.limit(request, "fernzugang_dateien", admin=True)
    body = await json_body(request, PATH_MAX + 256)
    p = pfad(body.get("pfad"), s.home)
    if p is None:
        fernzugang.log("liste", "pfad ungueltig", 0)
        raise HTTPException(400, "pfad: an absolute path")
    try:
        attrs = await _sftp(s, lambda c: c.listdir_attr(p))
    except Exception as e:
        fernzugang.log("liste", _err(e), 0)
        raise HTTPException(*SAY[_err(e)]) from None
    rows, links = [], 0
    for a in attrs:
        art = _art(a.st_mode or 0)
        if art == "link" and links < LINK_STAT:
            links += 1
            try:
                t = await _sftp(s, lambda c, n=a.filename: c.stat(posixpath.join(p, n)))
                m = t.st_mode or 0
                art = "linkdir" if stat.S_ISDIR(m) else "linkfile" if stat.S_ISREG(m) else "link"
            except Exception:
                art = "link"
        rows.append({"name": _shown(a.filename), "art": art,
                     "groesse": int(a.st_size or 0) if art in ("file", "linkfile") else None,
                     "zeit": int(a.st_mtime or 0) or None})
    rows.sort(key=lambda r: (r["art"] not in ("dir", "linkdir"), r["name"].lower()))
    fernzugang.log("liste", "ok", len(rows))
    return {"pfad": p, "oben": posixpath.dirname(p) if p != "/" else None, "eintraege": rows[:LIST_MAX],
            "mehr": len(rows) > LIST_MAX, "max_mb": _mb()}


@router.post("/api/admin/fernzugang/dateien/{sid}/link", dependencies=[Depends(auth)])
async def download_link(sid: str, request: Request):
    """A one-time link for one regular file (LINK_S seconds): the browser or the Android app fetches it."""
    s = _session(request, sid, "link")
    guard.limit(request, "fernzugang_dateien", admin=True)
    body = await json_body(request, PATH_MAX + 256)
    p = pfad(body.get("pfad"), s.home)
    if p is None or p == "/":
        fernzugang.log("link", "pfad ungueltig", 0)
        raise HTTPException(400, "pfad: an absolute path of a file")
    try:
        a = await _sftp(s, lambda c: c.stat(p))
    except Exception as e:
        fernzugang.log("link", _err(e), 0)
        raise HTTPException(*SAY[_err(e)]) from None
    if not stat.S_ISREG(a.st_mode or 0):
        fernzugang.log("link", "keine datei", 0)
        raise HTTPException(400, "Nur eine gewöhnliche Datei.")
    size = int(a.st_size or 0)
    if size > max_bytes():
        fernzugang.log("link", "zu gross", size // 1024)
        raise _too_big()
    now = time.time()
    for k in [k for k, v in LINKS.items() if v["until"] < now]:
        LINKS.pop(k, None)
    if len(LINKS) >= LINKS_MAX:
        LINKS.pop(min(LINKS, key=lambda k: LINKS[k]["until"]))
    tok = secrets.token_urlsafe(32)
    LINKS[hashlib.sha256(tok.encode()).hexdigest()] = {"sid": s.id, "pfad": p, "name": posixpath.basename(p),
                                                       "groesse": size, "until": now + LINK_S}
    fernzugang.log("link", "ok", 1)
    return {"url": "/api/fernzugang/datei?t=" + tok, "gilt_s": LINK_S}


def _disposition(name):
    """attachment with the remote name, safe for the header (RFC 6266/5987): an ASCII fallback plus filename*."""
    shown = _shown(name) or "datei"
    plain = re.sub(r"[^A-Za-z0-9._\- ]", "_", shown)[:120] or "datei"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(shown, safe='')}"


def _close(f):
    try:
        f.close()
    except Exception:
        pass


@router.get("/api/fernzugang/datei")
async def download(request: Request, t: str = ""):
    """The one-time link: no login of its own (the token is the key, made by an admin in a session opened with a fresh
    code), once, LINK_S seconds, only while its session lives; streamed piece by piece, at most
    chat.fernzugang_datei_mb."""
    if not fernzugang.admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_datei")
    if fernzugang._notaus(count=True):
        fernzugang.log("laden", "notaus", 0)
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    h = hashlib.sha256(t.encode()).hexdigest() if TOKEN.fullmatch(t or "") else ""
    hit = next((k for k in list(LINKS) if h and hmac.compare_digest(k, h)), None)
    x = LINKS.pop(hit, None) if hit else None
    s = fernzugang.SITZUNG.get(x["sid"]) if x else None
    if not x or x["until"] < time.time() or s is None or s.ende.is_set():
        fernzugang.log("laden", "link", 0)
        raise HTTPException(404, "Der Link gilt nicht mehr.")
    limit = max_bytes()
    try:
        f = await _sftp(s, lambda c: c.open(x["pfad"], "rb"))
    except Exception as e:
        fernzugang.log("laden", _err(e), 0)
        raise HTTPException(*SAY[_err(e)]) from None
    s.zuletzt = time.time()
    fernzugang.STATS["uebertragungen"] += 1

    async def stream():
        n, why = 0, "ok"
        try:
            while True:
                if s.ende.is_set() or fernzugang._notaus():
                    why = "abgebrochen"
                    break
                part = await _sftp(s, lambda c: f.read(CHUNK))
                if not part:
                    break
                n += len(part)
                if n > limit:
                    why = "zu gross"
                    break
                s.zuletzt = time.time()
                yield part
        except Exception as e:
            why = _err(e)
        finally:
            fernzugang.STATS["uebertragungen"] -= 1
            await asyncio.to_thread(_close, f)
            fernzugang.log("laden", why, n // 1024)
    return StreamingResponse(stream(), media_type="application/octet-stream",
                             headers={"Content-Disposition": _disposition(x["name"]), "Cache-Control": "no-store",
                                      "X-Content-Type-Options": "nosniff"})


@router.post("/api/admin/fernzugang/dateien/{sid}/hoch", dependencies=[Depends(auth)])
async def upload(sid: str, request: Request):
    """The raw body into one new file (x-fz-pfad: the folder, x-fz-name: the name, both percent-encoded), written
    to a hidden part file and renamed when complete. Without x-fz-ersetzen: 1 an existing file stays (409)."""
    s = _session(request, sid, "hoch")
    guard.limit(request, "fernzugang_hoch", admin=True)
    folder = pfad(unquote(request.headers.get("x-fz-pfad", "")), s.home)
    name = unquote(request.headers.get("x-fz-name", ""))
    replace = request.headers.get("x-fz-ersetzen") == "1"
    if folder is None or not name_ok(name):
        fernzugang.log("hoch", "name ungueltig", 0)
        raise HTTPException(400, "x-fz-pfad and x-fz-name: a folder and one name")
    limit = max_bytes()
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > limit:
        fernzugang.log("hoch", "zu gross", int(cl) // 1024)
        raise _too_big()
    target = posixpath.join(folder, name)
    part = posixpath.join(folder, f".{name[:200]}.spark-teil-{secrets.token_hex(4)}")
    try:
        f = await _sftp(s, lambda c: c.open(part, "wbx"))
    except Exception as e:
        fernzugang.log("hoch", _err(e), 0)
        raise HTTPException(*SAY[_err(e)]) from None
    n, why = 0, ""
    fernzugang.STATS["uebertragungen"] += 1
    try:
        async for chunk in request.stream():
            if s.ende.is_set() or fernzugang._notaus():
                why = "abgebrochen"
                break
            n += len(chunk)
            if n > limit:
                why = "zu gross"
                break
            if chunk:
                await _sftp(s, lambda c, b=chunk: f.write(b))
                s.zuletzt = time.time()
    except Exception as e:
        why = _err(e)
    finally:
        fernzugang.STATS["uebertragungen"] -= 1
        await asyncio.to_thread(_close, f)
    if not why:
        try:
            if replace:
                await _sftp(s, lambda c: c.posix_rename(part, target))
            else:
                await _sftp(s, lambda c: c.rename(part, target))   # an SFTP rename never overwrites
        except Exception as e:
            why = "gibt es schon" if not replace and not isinstance(e, (PermissionError, FileNotFoundError)) else _err(e)
    if why:
        if not s.ende.is_set():
            try:
                await _sftp(s, lambda c: c.remove(part))
            except Exception:
                pass
        fernzugang.log("hoch", why, n // 1024)
        if why == "zu gross":
            raise _too_big()
        raise HTTPException(*{"gibt es schon": (409, "Die Datei gibt es dort schon („Ersetzen“ überschreibt sie)."),
                              "abgebrochen": (503, "Abgebrochen: die Sitzung ist zu.")}.get(why) or SAY.get(why, SAY["fehler"]))
    fernzugang.log("hoch", "ok", n // 1024)
    return {"ok": True, "groesse": n}


@router.delete("/api/admin/fernzugang/dateien/{sid}", dependencies=[Depends(auth)])
async def close_files(sid: str, request: Request):
    s = _session(request, sid, "dateien_zu", frei=False)
    guard.limit(request, "fernzugang", admin=True)
    await s.end("browser")
    return {"ok": True}
