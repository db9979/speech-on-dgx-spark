"""Fernzugang, große Dateien (stage 3b, Dominik 2026-10-29 07:43): three ways for a big file onto a paired server,
inside the open „Dateien“ session (ferndateien.py: the same SSH connection, the same login, the unlocked page).

1. Hochladen in Teilen: the browser sends TEIL bytes at a time with the SHA-256 of each piece; the panel checks
   every piece before it writes, keeps the SHA-256 of the whole file as it grows and, at the end, compares it with
   what the server itself computes of the part file (sha256sum, shasum -a 256 on a Mac). A piece goes once more
   after a broken line; „Pause“ and „Weiter“ go on at the last whole piece, also in a new session of the same login
   (while the panel runs, UPLOAD_S at most). The request body is never bigger than one piece, so a proxy in front
   of the panel does not matter.
2. Per Link holen: the server fetches an https address itself (curl, https only, also on redirects, at most the
   limit), into a part file; the panel only watches its size. With a SHA-256 given, a file that does not match it is
   deleted. The address is checked (https, a host, no login in it, safe characters, at most URL_MAX) and passed as
   one quoted word, never a part of the command's text; it is never written to the journal.
3. Vom NAS übertragen: one file of an NAS place of the own profile (nas.py, read only) goes piece by piece through
   the panel onto the server, never all at once in memory or on the Spark's disk; the same check at the end.

Rules (fixed, Sicherheits-Checkliste): admin in the own browser, the unlocked page, the switch
chat.fernzugang_gross (Funktionen → Fernzugang zu Servern → Große Dateien, off), the Notaus and „Trennen“ as for the
files; never a guest, a device key or the model. At most chat.fernzugang_gross_mb MB per file, the free space on the
server checked first (df -Pk). The commands on the server are fixed per kind of system (BEFEHL), every value a
quoted word; they run in their own channel with a pty, so closing it (Abbrechen, Trennen, Notaus) hangs up the
command there. A file is written only to a hidden part file next to the target and renamed only after the check
(without „Ersetzen“ an SFTP rename, which never overwrites). What breaks leaves nothing behind: the part file is
removed, or, when the session was gone already, at the next „Dateien“ of that system (REST). The journal gets fixed
words and numbers only (KB, KB/s), never a name, a path, an address or a byte of a file. Windows follows in stage 5.

    admin in the browser (core.auth + fernzugang.is_admin_browser), inside a files session {sid}:
    GET    /api/admin/fernzugang/gross/{sid}/stand                  -> {"teil", "max_mb", "uploads", "jobs", "nas"}
    POST   /api/admin/fernzugang/gross/{sid}/hoch {pfad, name, groesse, ersetzen, sha256?}  -> {"id", "offset", "teil"}
    POST   /api/admin/fernzugang/gross/{sid}/hoch/{uid}/weiter                            -> {"offset", "groesse"}
    PUT    /api/admin/fernzugang/gross/{sid}/hoch/{uid}?offset=N    raw piece, header x-fz-sha256 -> {"offset"}
    POST   /api/admin/fernzugang/gross/{sid}/hoch/{uid}/fertig                            -> {"id", "sha256"} (the check)
    DELETE /api/admin/fernzugang/gross/{sid}/hoch/{uid}             stops it, the part file goes
    POST   /api/admin/fernzugang/gross/{sid}/holen {url, pfad, name, sha256?, ersetzen}   -> {"id"}
    POST   /api/admin/fernzugang/gross/{sid}/nas/liste {nas, pfad}  -> {"pfad", "ordner", "dateien"}
    POST   /api/admin/fernzugang/gross/{sid}/nas {nas, datei, pfad, name, ersetzen}       -> {"id"}
    DELETE /api/admin/fernzugang/gross/{sid}/job/{jid}              stops a fetch or an NAS transfer
"""
import asyncio
import hashlib
import hmac
import posixpath
import re
import secrets
import shlex
import socket
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import core
import features
import ferndateien
import fernzugang
import guard
from core import auth, json_body

router = APIRouter()

TEIL = 8 * 1024 * 1024     # bytes of one piece of an upload (the request body at most)
SCHREIB = 256 * 1024       # bytes per SFTP write (other calls of the session go in between)
NAS_STUECK = 1024 * 1024   # bytes read from the NAS at a time
UPLOAD_S = 24 * 3600       # a paused upload is kept this long (in memory: a restart of the panel starts it anew)
UPLOADS_MAX = 8            # uploads kept at most (running or paused)
JOBS_MAX = 4               # fetches and NAS transfers at the same time at most
RESERVE = 64 * 1024 * 1024  # bytes that stay free on the server beyond the file
URL_MAX = 2048
LANGSAM_KB = 1024          # below this many KB/s the page says why and what helps
BAD = re.compile(r"[\x00-\x1f\x7f]")
HEX = re.compile(r"[0-9a-f]{64}")
UID = re.compile(r"[0-9a-f]{16}")
# an https address: a host name or an IPv4 address, a port, a path and a query of the safe characters of RFC 3986
# (no quotes, no backslash, no space, no login „user@“)
URL = re.compile(r"https://([A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}[A-Za-z0-9])?)*)"
                 r"(?::(\d{1,5}))?(/[A-Za-z0-9._~!$&()*+,;=:%/\-]*)?(\?[A-Za-z0-9._~!$&()*+,;=:%/?\-]*)?")
# the commands on the server, fixed per kind of system; every {value} is passed through shlex.quote (_befehl)
CURL = "curl -fsSL --proto =https --proto-redir =https --max-redirs 5 --connect-timeout 20"
BEFEHL = {"linux": {"frei": "df -Pk -- {ordner}", "summe": "sha256sum -- {datei}", "kopf": CURL + " -I -- {url}",
                    "holen": CURL + " --max-filesize {most} -o {datei} -- {url}"},
          "macos": {"frei": "df -Pk -- {ordner}", "summe": "shasum -a 256 -- {datei}", "kopf": CURL + " -I -- {url}",
                    "holen": CURL + " --max-filesize {most} -o {datei} -- {url}"}}
# curl's exit codes as fixed words (the page shows SAY)
CURL_WORT = {6: "offline", 7: "offline", 22: "http", 23: "voll", 28: "zeit", 35: "zertifikat", 47: "umleitung",
             51: "zertifikat", 60: "zertifikat", 63: "zu gross", 127: "curl fehlt"}
SAY = {"zu gross": (413, "Größer als erlaubt (Funktionen → Fernzugang zu Servern → Größte große Datei)."),
       "voll": (507, "Auf dem Server ist nicht genug Platz frei."),
       "pruefsumme": (422, "Die Prüfsumme passt nicht: die Datei wurde gelöscht."),
       "gibt es schon": (409, "Die Datei gibt es dort schon („Ersetzen“ überschreibt sie)."),
       "offline": (502, "Der Server erreicht die Adresse nicht."), "http": (502, "Die Adresse antwortet mit einem Fehler."),
       "zeit": (504, "Die Adresse antwortet zu langsam."), "zertifikat": (502, "Das Zertifikat der Adresse ist nicht gültig."),
       "umleitung": (502, "Zu viele Weiterleitungen."), "curl fehlt": (501, "Auf dem Server fehlt curl."),
       "abgebrochen": (503, "Abgebrochen."), "windows": (501, "Große Dateien gehen unter Windows noch nicht; dort „Dateien“ nehmen."),
       "nas": (502, "Das NAS gibt die Datei nicht."), "fehler": (502, "Der Server hat das nicht ausgeführt.")}

UPLOADS = {}   # id -> Upload
JOBS = {}      # id -> Job
REST = {}      # gid -> {part file}: left behind when the session was gone; removed at the next „Dateien“ there


def admin_on(c=None):
    """Funktionen → Fernzugang zu Servern → Große Dateien (admin, off), under the Fernzugang switch."""
    return features.admin_on("ferngross", c)


def max_bytes(c=None):
    return 1024 * 1024 * fernzugang.gross_mb(c)


def url_ok(v):
    """The address as given when it is a plain https address (URL), else None. Never a part of a command's text:
    it goes as one quoted word."""
    v = str(v or "")
    if not v or len(v) > URL_MAX or BAD.search(v):
        return None
    m = URL.fullmatch(v)
    if not m or (m.group(2) and not 0 < int(m.group(2)) < 65536):
        return None
    return v


def sha_ok(v):
    """"" when none was given, the hex digits when they are a SHA-256, else None."""
    v = str(v or "").strip().lower()
    return "" if not v else v if HEX.fullmatch(v) else None


def _befehl(kind, was, **values):
    """One fixed command of BEFEHL with every value as one quoted word."""
    return BEFEHL[kind][was].format(**{k: shlex.quote(str(v)) for k, v in values.items()})


def _kind(s):
    g = fernzugang._read()["geraete"].get(s.gid, {})
    return fernzugang.art(g.get("os"))


# ---------------------------------------------------------------- on the server
def _exec(s, cmd, timeout, most=64 * 1024, stop=None, tick=None):
    """In a thread: one command on the server in its own channel with a pty (closing it hangs up the command there),
    (exit status, the first `most` bytes of what it wrote); status None when stopped or out of time."""
    chan = s.transport.open_session(timeout=10)
    try:
        chan.get_pty(term="dumb", width=200, height=24)
        chan.exec_command(cmd)
        chan.settimeout(1.0)
        out, end, last = b"", time.monotonic() + timeout, 0.0
        while True:
            if (stop and stop()) or time.monotonic() > end:
                return None, out
            try:
                data = chan.recv(4096)
            except socket.timeout:
                data = None
            if data == b"":
                break
            if data and len(out) < most:
                out += data[:most - len(out)]
            if tick and time.monotonic() - last >= 1:
                last = time.monotonic()
                tick()
        return chan.recv_exit_status(), out
    finally:
        chan.close()


def _frei_kb(out):
    """The free KB from `df -Pk` (the last line's fourth field), None when it says nothing usable."""
    lines = [x for x in out.decode("utf-8", "replace").replace("\r", "").split("\n") if x.strip()]
    parts = lines[-1].split() if len(lines) >= 2 else []
    return int(parts[3]) if len(parts) >= 6 and parts[3].isdigit() else None


def _summe(out):
    m = re.search(rb"(?<![0-9a-f])([0-9a-f]{64})(?![0-9a-f])", out)
    return m.group(1).decode() if m else None


def _laenge(out):
    """The size the address announced (the last Content-Length of curl -I, after the redirects), None when it named
    none (outside data: digits only, at most 19)."""
    nums = re.findall(rb"(?im)^content-length:[ \t]*(\d{1,19})[ \t]*\r?$", out)
    n = int(nums[-1]) if nums else 0
    return n if n > 0 else None


async def _platz(s, ordner, groesse):
    """True when the server has room for groesse bytes (and RESERVE), False when not, None when df said nothing."""
    st, out = await asyncio.to_thread(_exec, s, _befehl(_kind(s), "frei", ordner=ordner), 30)
    kb = _frei_kb(out) if st == 0 else None
    return None if kb is None else kb * 1024 >= groesse + RESERVE


async def _pruefen(s, teil, groesse):
    """The SHA-256 the server computes of the part file itself (None when it could not)."""
    st, out = await asyncio.to_thread(_exec, s, _befehl(_kind(s), "summe", datei=teil), 120 + groesse // (20 * 1024 * 1024))
    return _summe(out) if st == 0 else None


async def _weg(s, teil):
    """The part file goes (best effort); when the session is gone already, at the next „Dateien“ there."""
    if s is None or s.ende.is_set():
        REST.setdefault(s.gid if s else "", set()).add(teil)
        return
    try:
        await ferndateien._sftp(s, lambda c: c.remove(teil))
    except FileNotFoundError:
        pass
    except Exception:
        REST.setdefault(s.gid, set()).add(teil)


async def _ablegen(s, teil, ziel, ersetzen):
    """The checked part file becomes the target: "" or the fixed word why not."""
    try:
        if ersetzen:
            await ferndateien._sftp(s, lambda c: c.posix_rename(teil, ziel))
        else:
            await ferndateien._sftp(s, lambda c: c.rename(teil, ziel))   # an SFTP rename never overwrites
        return ""
    except (PermissionError, FileNotFoundError) as e:
        return ferndateien._err(e)
    except Exception as e:
        return "gibt es schon" if not ersetzen else ferndateien._err(e)


async def sweep(s):
    """At a new „Dateien“ of a system: what was left behind there goes, and uploads too old (or all of them, with the
    switch off) are forgotten."""
    now, on = time.time(), admin_on()
    for k in [k for k, u in UPLOADS.items() if now - u.t > UPLOAD_S or not on]:
        u = UPLOADS.pop(k)
        REST.setdefault(u.gid, set()).add(u.teil)
    left = REST.pop(s.gid, set())
    n = 0
    for p in left:
        try:
            await ferndateien._sftp(s, lambda c, p=p: c.remove(p))
            n += 1
        except FileNotFoundError:
            pass
        except Exception:
            pass
    if left:
        fernzugang.log("gross_rest", "weg", n)


# ---------------------------------------------------------------- the checks of every door
def _sitzung(request, sid, word):
    """The files session of this login (ferndateien._session: switch, browser, unlocked page, Notaus) and the
    switch of the big files."""
    s = ferndateien._session(request, sid, word)
    if not admin_on():
        fernzugang.log(word, "aus", 0)
        raise HTTPException(404, "Große Dateien sind aus (Funktionen → Fernzugang zu Servern → Große Dateien)")
    if _kind(s) == "windows":
        fernzugang.log(word, "windows", 0)
        raise HTTPException(*SAY["windows"])
    return s


def _ziel(s, body, word):
    """(folder, name, target, replace) from what the browser sent, else 400."""
    ordner = ferndateien.pfad(body.get("pfad"), s.home)
    name = str(body.get("name") or "")
    if ordner is None or not ferndateien.name_ok(name):
        fernzugang.log(word, "name ungueltig", 0)
        raise HTTPException(400, "pfad and name: a folder and one name")
    return ordner, name, posixpath.join(ordner, name), body.get("ersetzen") is True


async def _vorher(s, ordner, ziel, ersetzen, groesse, word):
    """Before anything is written: not too big, the target free (without „Ersetzen“), room on the server."""
    if groesse is not None and groesse > max_bytes():
        fernzugang.log(word, "zu gross", groesse // 1024)
        raise HTTPException(*SAY["zu gross"])
    if not ersetzen:
        try:
            await ferndateien._sftp(s, lambda c: c.stat(ziel))
            fernzugang.log(word, "gibt es schon", 0)
            raise HTTPException(*SAY["gibt es schon"])
        except FileNotFoundError:
            pass
        except HTTPException:
            raise
        except Exception as e:
            fernzugang.log(word, ferndateien._err(e), 0)
            raise HTTPException(*ferndateien.SAY[ferndateien._err(e)]) from None
    if groesse is not None:
        try:
            room = await _platz(s, ordner, groesse)
        except Exception:
            room = None
        if room is False:
            fernzugang.log(word, "voll", groesse // 1024)
            raise HTTPException(*SAY["voll"])


def _teil_name(ordner, name, uid):
    return posixpath.join(ordner, f".{name[:200]}.spark-teil-{uid}")


# ---------------------------------------------------------------- 1. upload in pieces
class Upload:
    def __init__(self, s, ordner, name, ziel, groesse, ersetzen, sha):
        self.id = secrets.token_hex(8)
        self.gid, self.login, self.sid = s.gid, s.login, s.id
        self.ordner, self.name, self.ziel = ordner, name, ziel
        self.teil = _teil_name(ordner, name, self.id)
        self.groesse, self.ersetzen, self.sha = groesse, ersetzen, sha
        self.offset = 0
        self.h = hashlib.sha256()
        self.seit = self.t = time.time()
        self.lock = asyncio.Lock()

    def public(self):
        return {"id": self.id, "name": ferndateien._shown(self.name), "pfad": self.ordner, "groesse": self.groesse,
                "offset": self.offset, "seit": int(self.seit)}


def _upload(s, uid, word, bind=False):
    """This login's upload on this system, else 404; bind: it goes on in this session (a new one after Trennen)."""
    u = UPLOADS.get(str(uid)) if UID.fullmatch(str(uid or "")) else None
    if u is None or u.gid != s.gid or not hmac.compare_digest(u.login, s.login) or (u.sid != s.id and not bind):
        fernzugang.log(word, "kein upload", 0)
        raise HTTPException(404, "no such upload")
    return u


@router.post("/api/admin/fernzugang/gross/{sid}/hoch", dependencies=[Depends(auth)])
async def upload_start(sid: str, request: Request):
    s = _sitzung(request, sid, "gross_auf")
    guard.limit(request, "fernzugang_gross", admin=True)
    body = await json_body(request, ferndateien.PATH_MAX + 1024)
    ordner, name, ziel, ersetzen = _ziel(s, body, "gross_auf")
    groesse, sha = body.get("groesse"), sha_ok(body.get("sha256"))
    if not isinstance(groesse, int) or isinstance(groesse, bool) or groesse < 1 or sha is None:
        fernzugang.log("gross_auf", "ungueltig", 0)
        raise HTTPException(400, "groesse: bytes; sha256: 64 hex digits or nothing")
    if len(UPLOADS) >= UPLOADS_MAX:
        fernzugang.log("gross_auf", "voll", len(UPLOADS))
        raise HTTPException(409, "Zu viele offene große Uploads: erst einen beenden oder abbrechen.")
    await _vorher(s, ordner, ziel, ersetzen, groesse, "gross_auf")
    u = Upload(s, ordner, name, ziel, groesse, ersetzen, sha)
    try:
        f = await ferndateien._sftp(s, lambda c: c.open(u.teil, "wbx"))
        await asyncio.to_thread(ferndateien._close, f)
    except Exception as e:
        fernzugang.log("gross_auf", ferndateien._err(e), 0)
        raise HTTPException(*ferndateien.SAY[ferndateien._err(e)]) from None
    UPLOADS[u.id] = u
    fernzugang.log("gross_auf", "ok", groesse // 1024)
    return {"id": u.id, "offset": 0, "teil": TEIL}


@router.post("/api/admin/fernzugang/gross/{sid}/hoch/{uid}/weiter", dependencies=[Depends(auth)])
async def upload_resume(sid: str, uid: str, request: Request):
    """Goes on where the last whole piece ended, also in a new session of the same login: the part file is cut back
    to it; when the server has less, it starts anew."""
    s = _sitzung(request, sid, "gross_weiter")
    guard.limit(request, "fernzugang_gross", admin=True)
    u = _upload(s, uid, "gross_weiter", bind=True)
    async with u.lock:
        try:
            have = (await ferndateien._sftp(s, lambda c: c.stat(u.teil))).st_size or 0
            if have < u.offset:
                u.offset, u.h = 0, hashlib.sha256()
            if have != u.offset:
                await ferndateien._sftp(s, lambda c: c.truncate(u.teil, u.offset))
        except Exception as e:
            fernzugang.log("gross_weiter", ferndateien._err(e), 0)
            raise HTTPException(*ferndateien.SAY[ferndateien._err(e)]) from None
        u.sid, u.t = s.id, time.time()
    fernzugang.log("gross_weiter", "ok" if u.offset else "neu", u.offset // 1024)
    return {"offset": u.offset, "groesse": u.groesse}


async def _body(request, most):
    """The piece, never more than most bytes (413 above it)."""
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > most:
        return None
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > most:
            return None
    return bytes(raw)


@router.put("/api/admin/fernzugang/gross/{sid}/hoch/{uid}", dependencies=[Depends(auth)])
async def upload_piece(sid: str, uid: str, request: Request, offset: int = -1):
    """One piece at its place: only at the current end, only whole, only when its SHA-256 matches; then it is
    written and counts into the SHA-256 of the whole file."""
    s = _sitzung(request, sid, "gross_teil")
    guard.limit(request, "fernzugang_teil", admin=True)
    u = _upload(s, uid, "gross_teil")
    want = str(request.headers.get("x-fz-sha256", "")).lower()
    async with u.lock:
        if offset != u.offset:
            fernzugang.log("gross_teil", "stelle", 0)
            raise HTTPException(409, "Dieses Stück ist nicht dran („Weiter“ fragt, wo es weitergeht).")
        data = await _body(request, min(TEIL, u.groesse - u.offset))
        if data is None:
            fernzugang.log("gross_teil", "zu gross", 0)
            raise HTTPException(413, "Ein Stück ist höchstens 8 MB und endet am Ende der Datei.")
        if not data or not HEX.fullmatch(want) or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), want):
            fernzugang.log("gross_teil", "pruefsumme", len(data) // 1024)
            raise HTTPException(422, "Das Stück kam nicht heil an, es geht noch einmal.")
        try:
            f = await ferndateien._sftp(s, lambda c: c.open(u.teil, "r+b"))
            f.set_pipelined(True)
            try:
                f.seek(u.offset)
                for i in range(0, len(data), SCHREIB):
                    if s.ende.is_set() or fernzugang._notaus():
                        raise ConnectionAbortedError()
                    await ferndateien._sftp(s, lambda c, b=data[i:i + SCHREIB]: f.write(b))
            finally:
                await asyncio.to_thread(ferndateien._close, f)
        except ConnectionAbortedError:
            fernzugang.log("gross_teil", "abgebrochen", 0)
            raise HTTPException(*SAY["abgebrochen"]) from None
        except Exception as e:
            fernzugang.log("gross_teil", ferndateien._err(e), 0)
            raise HTTPException(*ferndateien.SAY[ferndateien._err(e)]) from None
        u.h.update(data)
        u.offset += len(data)
        u.t = s.zuletzt = time.time()   # counts as moving for a minute (fernzugang.counts, „Übertragungen“)
    fernzugang.log("gross_teil", "ok", len(data) // 1024)
    return {"offset": u.offset}


@router.post("/api/admin/fernzugang/gross/{sid}/hoch/{uid}/fertig", dependencies=[Depends(auth)])
async def upload_done(sid: str, uid: str, request: Request):
    """All pieces there: the check runs in the background like a fetch (a big file takes the server minutes, longer
    than a proxy waits): the server's own SHA-256 of the part file against the panel's (and the given one), then the
    rename; a mismatch deletes the part file. The page follows it under „stand“."""
    s = _sitzung(request, sid, "gross_fertig")
    guard.limit(request, "fernzugang_gross", admin=True)
    u = _upload(s, uid, "gross_fertig")
    async with u.lock:
        if u.offset != u.groesse:
            fernzugang.log("gross_fertig", "unvollstaendig", u.offset // 1024)
            raise HTTPException(409, "Es fehlen noch Stücke.")
        UPLOADS.pop(u.id, None)
    ours = u.h.hexdigest()
    j = Job(s, "hoch", u.ordner, u.name, u.ziel, u.ersetzen, ours)
    j.teil, j.bytes, j.groesse, j.seit = u.teil, u.groesse, u.groesse, u.seit
    if u.sha and not hmac.compare_digest(u.sha, ours):
        await _weg(s, u.teil)
        fernzugang.log("gross_fertig", "pruefsumme", u.groesse // 1024)
        raise HTTPException(*SAY["pruefsumme"])
    _start(s, j, _abschluss(s, j, "gross_fertig"))
    return {"id": j.id, "sha256": ours}


@router.delete("/api/admin/fernzugang/gross/{sid}/hoch/{uid}", dependencies=[Depends(auth)])
async def upload_stop(sid: str, uid: str, request: Request):
    s = _sitzung(request, sid, "gross_ab")
    guard.limit(request, "fernzugang_gross", admin=True)
    u = _upload(s, uid, "gross_ab", bind=True)
    UPLOADS.pop(u.id, None)
    await _weg(s, u.teil)
    fernzugang.log("gross_ab", "ok", u.offset // 1024)
    return {"ok": True}


# ---------------------------------------------------------------- 2. and 3.: jobs the panel watches
FERTIG = {"link": "holen_fertig", "nas": "nas_fertig", "hoch": "gross_fertig"}   # the journal's word at a job's end


class Job:
    def __init__(self, s, art, ordner, name, ziel, ersetzen, sha):
        self.id = secrets.token_hex(8)
        self.art, self.sid, self.gid = art, s.id, s.gid
        self.ordner, self.name, self.ziel, self.ersetzen, self.sha = ordner, name, ziel, ersetzen, sha
        self.teil = _teil_name(ordner, name, self.id)
        self.stand, self.grund, self.summe = "laeuft", "", ""
        self.bytes, self.groesse = 0, None
        self.seit = self.ende_t = time.time()
        self.stop = False
        self.task = None

    def kb_s(self):
        secs = max(1.0, (time.time() if self.stand in ("laeuft", "pruefen") else self.ende_t) - self.seit)
        return int(self.bytes / 1024 / secs)

    def public(self):
        return {"id": self.id, "art": self.art, "name": ferndateien._shown(self.name), "stand": self.stand,
                "grund": self.grund, "text": SAY.get(self.grund, (0, ""))[1] if self.grund else "",
                "bytes": self.bytes, "groesse": self.groesse, "kb_s": self.kb_s(), "sha256": self.summe}


def _halt(s, j):
    return j.stop or s.ende.is_set() or fernzugang._notaus() or not admin_on()


async def _abschluss(s, j, word):
    """The common end of a job: the server's SHA-256, against the given one, then the rename; one journal line."""
    why = ""
    if _halt(s, j):
        why = "abgebrochen"
    else:
        j.stand = "pruefen"
        summe = await _pruefen(s, j.teil, j.bytes)
        if summe is None:
            why = "fehler"
        elif j.sha and not hmac.compare_digest(j.sha, summe):
            why = "pruefsumme"
        else:
            j.summe = summe
            why = await _ablegen(s, j.teil, j.ziel, j.ersetzen)
    if why:
        await _weg(s, j.teil)
    j.stand, j.grund, j.ende_t = ("fehler", why, time.time()) if why else ("fertig", "", time.time())
    fernzugang.log(word, why or "ok", j.bytes // 1024)
    if not why:
        fernzugang.log("gross_rate", "kb_s", j.kb_s())


def _start(s, j, coro):
    for k in [k for k, x in JOBS.items() if x.stand not in ("laeuft", "pruefen") and time.time() - x.ende_t > 3600]:
        JOBS.pop(k, None)
    JOBS[j.id] = j

    async def run():
        fernzugang.STATS["uebertragungen"] += 1
        try:
            await coro
        except Exception:
            await _weg(s, j.teil)
            j.stand, j.grund, j.ende_t = "fehler", "fehler", time.time()
            fernzugang.log(FERTIG[j.art], "fehler", j.bytes // 1024)
        finally:
            fernzugang.STATS["uebertragungen"] -= 1
    j.task = asyncio.create_task(run())
    s.tasks.append(j.task)


def _jobs_voll(word):
    if sum(1 for x in JOBS.values() if x.stand in ("laeuft", "pruefen")) >= JOBS_MAX:
        fernzugang.log(word, "voll", JOBS_MAX)
        raise HTTPException(409, "Schon genug Übertragungen laufen: erst eine fertig werden lassen.")


async def _holen(s, j, url):
    """The server fetches the address itself into the part file; the panel watches its size."""
    kind, most = _kind(s), max_bytes()

    def size():
        try:
            with s.sftp_lock:
                j.bytes = int(s.sftp.stat(j.teil).st_size or 0)
        except Exception:
            pass
        if j.bytes > most:
            j.stop, j.grund = True, "zu gross"
    st, _out = await asyncio.to_thread(_exec, s, _befehl(kind, "holen", most=most, datei=j.teil, url=url),
                                       24 * 3600, 4096, lambda: _halt(s, j), size)
    await asyncio.to_thread(size)          # SFTP waits on the anchor's pipe: never on the event loop
    if st != 0:
        why = j.grund or ("abgebrochen" if st is None else CURL_WORT.get(st, "fehler"))
        await _weg(s, j.teil)
        j.stand, j.grund, j.ende_t = "fehler", why, time.time()
        fernzugang.log("holen_fertig", why, j.bytes // 1024)
        return
    await _abschluss(s, j, "holen_fertig")


@router.post("/api/admin/fernzugang/gross/{sid}/holen", dependencies=[Depends(auth)])
async def fetch(sid: str, request: Request):
    """„Per Link holen“: checks the address, asks for its size (curl -I), checks the room, then lets the server
    fetch it. The address is never written to the journal."""
    s = _sitzung(request, sid, "holen")
    guard.limit(request, "fernzugang_gross", admin=True)
    body = await json_body(request, URL_MAX + ferndateien.PATH_MAX + 1024)
    url, sha = url_ok(body.get("url")), sha_ok(body.get("sha256"))
    if url is None or sha is None:
        fernzugang.log("holen", "ungueltig", 0)
        raise HTTPException(400, "Nur eine https-Adresse ohne Anmeldedaten, höchstens 2048 Zeichen; "
                                 "die Prüfsumme 64 Zeichen 0-9 a-f oder leer.")
    ordner, name, ziel, ersetzen = _ziel(s, body, "holen")
    _jobs_voll("holen")
    try:
        st, out = await asyncio.to_thread(_exec, s, _befehl(_kind(s), "kopf", url=url), 30, 4096)
    except Exception:
        st, out = None, b""
    if st == 127:
        fernzugang.log("holen", "curl fehlt", 0)
        raise HTTPException(*SAY["curl fehlt"])
    groesse = _laenge(out) if st == 0 else None
    await _vorher(s, ordner, ziel, ersetzen, groesse, "holen")
    j = Job(s, "link", ordner, name, ziel, ersetzen, sha)
    j.groesse = groesse
    _start(s, j, _holen(s, j, url))
    fernzugang.log("holen", "ok", (groesse or 0) // 1024)
    return {"id": j.id, "groesse": groesse}


# ---------------------------------------------------------------- 3. from the NAS
def _nas_owner(request):
    """The NAS places of the acting profile (the panel password: the Spark's own), read only; 404 when NAS
    connections are off or not for this profile."""
    import nas
    prof = core.acting_profile(request)
    owner = prof["id"] if prof else nas.ADMIN
    if not nas.admin_on() or (prof and not features.allowed("nas", prof["id"])):
        return None, owner
    return nas, owner


def _orte(request):
    nas, owner = _nas_owner(request)
    return [{"id": c["id"], "name": c["name"], "art": c["kind"]} for c in nas.load(owner)] if nas else []


def _nas_ort(request, nid, word):
    nas, owner = _nas_owner(request)
    c = nas.find(owner, str(nid or "")) if nas else None
    if c is None:
        fernzugang.log(word, "kein nas", 0)
        raise HTTPException(404, "Diese NAS-Verbindung gibt es nicht (Ich → Speicher → NAS).")
    return c


def _nas_pfad(v):
    import nasquelle
    try:
        return nasquelle.clean_path(v)
    except ValueError:
        return None


@router.post("/api/admin/fernzugang/gross/{sid}/nas/liste", dependencies=[Depends(auth)])
async def nas_list(sid: str, request: Request):
    """One folder of an NAS place: folders and files with their sizes, as text."""
    import nasquelle
    s = _sitzung(request, sid, "nas_liste")
    guard.limit(request, "fernzugang_gross", admin=True)
    body = await json_body(request, ferndateien.PATH_MAX + 256)
    c = _nas_ort(request, body.get("nas"), "nas_liste")
    p = _nas_pfad(body.get("pfad"))
    if p is None or (c["kind"] == "smb" and not p):
        fernzugang.log("nas_liste", "pfad ungueltig", 0)
        raise HTTPException(400, "Bei SMB zuerst die Freigabe angeben, z. B. /home." if p == "" else "invalid folder")
    rd = nasquelle.reader(c, p)
    try:
        items = await asyncio.wait_for(rd.list(""), nasquelle.TIMEOUT + 5)
    except (nasquelle.SourceError, asyncio.TimeoutError):
        fernzugang.log("nas_liste", "nas", 0)
        raise HTTPException(*SAY["nas"]) from None
    finally:
        await rd.close()
    s.zuletzt = time.time()
    dirs = sorted((n for n, d, _, _ in items if d), key=str.lower)[:ferndateien.LIST_MAX]
    files = sorted(((n, z) for n, d, z, _ in items if not d), key=lambda x: x[0].lower())[:ferndateien.LIST_MAX]
    fernzugang.log("nas_liste", "ok", len(dirs) + len(files))
    return {"pfad": p or "/", "ordner": dirs, "dateien": [{"name": n, "groesse": z} for n, z in files],
            "mehr": len(items) > 2 * ferndateien.LIST_MAX}


async def _nas(s, j, c, ordner_nas, name_nas):
    """NAS → panel → server, piece by piece (NAS_STUECK in memory at most), the SHA-256 as it goes."""
    import nasquelle
    rd = nasquelle.reader(c, ordner_nas)
    h, f = hashlib.sha256(), None
    try:
        f = await ferndateien._sftp(s, lambda x: x.open(j.teil, "wbx"))
        f.set_pipelined(True)
        async for piece in rd.pieces(name_nas, max_bytes(), NAS_STUECK):
            if _halt(s, j):
                break
            h.update(piece)
            for i in range(0, len(piece), SCHREIB):
                await ferndateien._sftp(s, lambda x, b=piece[i:i + SCHREIB]: f.write(b))
            j.bytes += len(piece)
            s.zuletzt = time.time()
    except nasquelle.SourceError as e:
        j.grund = "zu gross" if "large" in str(e) else "nas"
    except Exception as e:
        j.grund = ferndateien._err(e)
    finally:
        if f is not None:
            await asyncio.to_thread(ferndateien._close, f)
        await rd.close()
    if j.grund:
        await _weg(s, j.teil)
        j.stand, j.ende_t = "fehler", time.time()
        fernzugang.log("nas_fertig", j.grund, j.bytes // 1024)
        return
    if not j.sha:
        j.sha = h.hexdigest()   # what went in must be what the server has
    await _abschluss(s, j, "nas_fertig")


@router.post("/api/admin/fernzugang/gross/{sid}/nas", dependencies=[Depends(auth)])
async def from_nas(sid: str, request: Request):
    """„Vom NAS übertragen“: one file of an NAS place onto the server, checked at the end."""
    import nasquelle
    s = _sitzung(request, sid, "nas_holen")
    guard.limit(request, "fernzugang_gross", admin=True)
    body = await json_body(request, 2 * ferndateien.PATH_MAX + 1024)
    c = _nas_ort(request, body.get("nas"), "nas_holen")
    quelle = _nas_pfad(body.get("datei"))
    if not quelle:
        fernzugang.log("nas_holen", "pfad ungueltig", 0)
        raise HTTPException(400, "datei: a file of the NAS place")
    ordner_nas, name_nas = posixpath.split(quelle)
    ordner_nas = "" if ordner_nas == "/" else ordner_nas
    ordner, name, ziel, ersetzen = _ziel(s, body, "nas_holen")
    _jobs_voll("nas_holen")
    rd = nasquelle.reader(c, ordner_nas)
    try:
        items = await asyncio.wait_for(rd.list(""), nasquelle.TIMEOUT + 5)
    except (nasquelle.SourceError, asyncio.TimeoutError):
        fernzugang.log("nas_holen", "nas", 0)
        raise HTTPException(*SAY["nas"]) from None
    finally:
        await rd.close()
    hit = next((z for n, d, z, _ in items if n == name_nas and not d), None)
    if hit is None:
        fernzugang.log("nas_holen", "fehlt", 0)
        raise HTTPException(404, "Die Datei gibt es auf dem NAS nicht (mehr).")
    await _vorher(s, ordner, ziel, ersetzen, hit, "nas_holen")
    j = Job(s, "nas", ordner, name, ziel, ersetzen, "")
    j.groesse = hit
    _start(s, j, _nas(s, j, c, ordner_nas, name_nas))
    fernzugang.log("nas_holen", "ok", hit // 1024)
    return {"id": j.id, "groesse": hit}


# ---------------------------------------------------------------- the page's view and stopping
@router.get("/api/admin/fernzugang/gross/{sid}/stand", dependencies=[Depends(auth)])
async def overview(sid: str, request: Request):
    """What runs and what waits in this session: the uploads of this login on this system (also the paused ones),
    the jobs of this session, the NAS places to choose from."""
    s = _sitzung(request, sid, "gross_stand")
    guard.limit(request, "fernzugang_gross", admin=True)
    ups = [u.public() for u in UPLOADS.values() if u.gid == s.gid and hmac.compare_digest(u.login, s.login)]
    jobs = [j.public() for j in JOBS.values() if j.sid == s.id]
    return {"teil": TEIL, "max_mb": fernzugang.gross_mb(), "langsam_kb": LANGSAM_KB, "uploads": ups, "jobs": jobs,
            "nas": _orte(request)}


@router.delete("/api/admin/fernzugang/gross/{sid}/job/{jid}", dependencies=[Depends(auth)])
async def job_stop(sid: str, jid: str, request: Request):
    s = _sitzung(request, sid, "job_ab")
    guard.limit(request, "fernzugang_gross", admin=True)
    j = JOBS.get(str(jid)) if UID.fullmatch(str(jid or "")) else None
    if j is None or j.sid != s.id:
        fernzugang.log("job_ab", "kein job", 0)
        raise HTTPException(404, "no such transfer")
    j.stop = True
    fernzugang.log("job_ab", "ok", 1)
    return {"ok": True}
