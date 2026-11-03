"""Spontanhilfe S2a, Steuern (plan spontanhilfe/s2-plan.md, Dominik 2026-11-03 „Empfehlung“ = 1a 2a 3a 4a 5a): when
looking is not enough, the admin may move the mouse and type at the person's computer. Nothing is installed: a small
program (SparkHilfe, S2b Windows) runs once from her downloads, asks her itself and is gone when she closes it.

Three consents, all needed:
1. the admin asks („Steuern anfragen“, a fresh code or passkey: stufen „Schutz ändern“);
2. only then /hilfe shows „Programm laden“: her page fetches the file by POST with her own session key, as a blob
   (the key for the program never stands in an address or a proxy log); its name carries the address and a one-time
   key: SparkHilfe-<host>-<key>.exe (KEY_S seconds, once, only its hash kept here, compared in constant time);
3. she starts it and clicks „Erlauben“ in the program (Ablehnen / Nur ansehen / Erlauben).

    admin (core.auth, the browser only, the unlocked Fernzugang page, a fresh code):
    POST   /api/admin/spontanhilfe/steuern             ask for control in the open help
    person (no login, her session key from /api/hilfe/start):
    POST   /api/hilfe/programm {tok, art}              the program for her system as a file; X-Spark-Schluessel the
                                                       one-time key, X-Spark-Sha256 its checksum (also on /hilfe)
    program (no page: any Origin header is refused):
    WS     /api/hilfe/steuern                          first message {"typ": "hallo", "schluessel", "art"}; then
                                                       {"typ": "antwort", "modus": no|view|control}, JPEG pictures
                                                       (binary, at most FPS a second, fernsicht.MAX_FRAME each) to the
                                                       admin's socket, inputs from it back (fernsicht.clean_events)

Rules: off by default (chat.spontansteuern, Funktionen → Fernzugang zu Servern → Steuern bei der Spontanhilfe, under the
Spontanhilfe switch), admins only, never a guest, never a tool for the model. Every wrong key gets the same answer;
the program learns the helper's name only after the key was taken. Inputs only from the fixed lists of fernsicht
(KEYS, BUTTONS, text, a point 0..1), checked here and again in the program, passed only while she allowed control
and the admin's toolbar says „Steuern“. The picture lives only in memory on its way through (no recording, nothing
to a model). One help at a time, its clock (chat.spontanhilfe_max_min) and the Notaus end the program too and make
key and file worthless. Logs: „spontanhilfe: steuern_frage|programm|steuern|steuern_zu | <word> | n“, fixed words.
The program files come only from the cache CACHE that the signed manifest filled, checked by SHA-256 before every
delivery.

S2b, the program: SparkHilfe for Windows (tools/sparkhilfe/windows, x64 and ARM64, one self-contained file, no setup, no
admin rights) is built only by CI (.github/workflows/sparkhilfe-windows.yml, actions pinned by SHA) and published with
sparkhilfe.json (version, per kind name, size, SHA-256; signed with signatur.py once UPDATE_SIGNING_KEY exists) in the
release TAG. While the switch is on and the Notaus lets the internet through, fetch() takes it once a day (after an
error within the hour): only GitHub's download addresses (begleiter._download), the signature when keys are listed,
size and SHA-256 of every file, else nothing is kept; then programme.json names the files. The Dienst-Wächter looks
whether every program is there with its checksum (probes, vorhanden). Logs: „spontanhilfe: programm_holen | <word> | n“.
"""
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse

import features
import fernsicht
import guard
import spontanhilfe as sh
from common import STATE, load_config, read_json, write_json
from core import admin_code_fresh, auth, json_body

router = APIRouter()

CACHE = os.path.join(STATE, "spontanhilfe-programme")   # programme.json and the files the signed manifest named (S2b)
KEY_S = 600             # the program's key works this long, once
FPS = 4                 # pictures a second at most; more are dropped
ARTEN = {"windows-x64": ".exe", "windows-arm64": ".exe"}   # S2c macOS and S2d Linux come later
KEY = re.compile(r"[A-Za-z0-9_\-]{22}")
SHA = re.compile(r"[0-9a-f]{64}")
DATEI = re.compile(r"SparkHilfe-[a-z0-9\-]{1,40}\.(?:exe|zip)")
MODI = ("no", "view", "control")
TAG = "sparkhilfe-windows"     # the release the CI run fills (S2b)
MANIFEST = "sparkhilfe.json"
MAX_META = 4096
FIRST = 120             # the first look this long after the start or after switching on
_sha = {}               # path -> (mtime, size, sha256): checked again whenever the file changed
_upd = {"checked": 0.0, "error": ""}


def admin_on(c=None):
    """Funktionen → Fernzugang zu Servern → Steuern bei der Spontanhilfe (admin, off; its parents too)."""
    return features.admin_on("spontansteuern", c)


class Steuern:
    """The control part of one help (memory only)."""

    def __init__(self):
        self.gefragt = False      # the admin asked (fresh code)
        self.key_h, self.key_bis = "", 0.0
        self.programm = None      # the program's socket
        self.modus = ""           # her answer in the program: no | view | control
        self.steuern = False      # the admin's toolbar: Steuern (True) or Nur ansehen
        self.gesteuert = False    # control happened in this help (history „Ansehen + Steuern“)
        self.seit = 0.0
        self.bilder = []          # times of the last pictures (FPS)


def of(h):
    if h is not None and getattr(h, "st", None) is None:
        h.st = Steuern()
    return h.st if h is not None else None


def view(h):
    """What the admin page and Live learn: states only."""
    st = getattr(h, "st", None) if h is not None else None
    if st is None or not admin_on():
        return {"an": admin_on(), "gefragt": False, "programm": False, "modus": "", "steuern": False}
    return {"an": True, "gefragt": st.gefragt, "programm": st.programm is not None, "modus": st.modus,
            "steuern": st.steuern and st.modus == "control"}


# ---------------------------------------------------------------- the program files (filled by S2b)
def programm(art):
    """(path, sha256) of the program for art from the cache, only when its file matches the manifest's SHA-256."""
    if art not in ARTEN:
        return None
    idx = read_json(os.path.join(CACHE, "programme.json"), {})
    x = idx.get(art) if isinstance(idx, dict) else None
    if not isinstance(x, dict) or not SHA.fullmatch(str(x.get("sha256") or "")) or not DATEI.fullmatch(str(x.get("datei") or "")):
        return None
    path = os.path.join(CACHE, x["datei"])
    try:
        stt = os.stat(path)
    except OSError:
        return None
    seen = _sha.get(path)
    if not seen or seen[:2] != (stt.st_mtime_ns, stt.st_size):
        d = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                d.update(block)
        seen = _sha[path] = (stt.st_mtime_ns, stt.st_size, d.hexdigest())
    return (path, x["sha256"]) if hmac.compare_digest(seen[2], x["sha256"]) else None


def vorhanden():
    """For the Dienst-Wächter: every program of ARTEN is in the cache and matches its SHA-256 (reads the files when they
    changed: call it in a thread)."""
    return all(programm(art) is not None for art in ARTEN)


def probes():
    """The Dienst-Wächter's part while the switch is on (no question of its own, only the cache)."""
    return {"sparkhilfe": {"sparkhilfe": True}} if admin_on() else {}


def angebot():
    """The programs /hilfe may offer, with their checksums (shown beside the button)."""
    out = {}
    for art in ARTEN:
        p = programm(art)
        if p:
            out[art] = p[1]
    return out


# ---------------------------------------------------------------- S2b: the program from the CI release
def _repo():
    return load_config().get("chat", {}).get("esp32_repo") or "db9979/speech-on-dgx-spark"


async def fetch(c=None):
    """Takes the newest SparkHilfe build when it is newer than the kept one or a file is missing; every file must match
    size and SHA-256 of the (signed) sparkhilfe.json. Returns the version the Spark keeps now."""
    import begleiter
    import geraeteupdate
    import signatur
    own = c is None
    c = c or httpx.AsyncClient(timeout=300, follow_redirects=True)
    try:
        api = os.environ.get("SPEECH_SPARK_GITHUB_API", "https://api.github.com")
        import ghtoken
        r = await ghtoken.get(c, f"{api}/repos/{_repo()}/releases/tags/{TAG}")
        if r.status_code == 404:
            raise begleiter.NotYet("Im Repo gibt es SparkHilfe noch nicht.")
        r.raise_for_status()
        assets = {a.get("name"): a.get("browser_download_url", "") for a in r.json().get("assets", [])}
        if MANIFEST not in assets:
            raise begleiter.NotYet("Die Version hat noch kein Verzeichnis.")
        raw = await begleiter._download(c, assets[MANIFEST], MAX_META)
        if signatur.required():
            if MANIFEST + ".sig" not in assets:
                raise ValueError("Die Version ist nicht signiert, nichts übernommen.")
            signatur.verify(raw, await begleiter._download(c, assets[MANIFEST + ".sig"], signatur.MAX_SIG))
        m = json.loads(raw)
        ver, files = str(m.get("version", "")), m.get("files")
        if not begleiter.VERSION_RE.fullmatch(ver) or not isinstance(files, dict):
            raise ValueError("sparkhilfe.json ist ungültig.")
        clean = {}
        for art, v in files.items():
            if art not in ARTEN or not isinstance(v, dict):
                continue
            name, size, sha = str(v.get("name", "")), v.get("size"), str(v.get("sha256", ""))
            if not (DATEI.fullmatch(name) and name in assets and isinstance(size, int) and not isinstance(size, bool)
                    and 0 < size <= begleiter.MAX_FILE and SHA.fullmatch(sha)):
                raise ValueError("sparkhilfe.json ist ungültig.")
            clean[art] = {"datei": name, "size": size, "sha256": sha, "version": ver}
        if not clean:
            raise ValueError("sparkhilfe.json nennt kein Programm.")
        idx = read_json(os.path.join(CACHE, "programme.json"), {})
        idx = idx if isinstance(idx, dict) else {}
        cur = {k: x for k, x in idx.items() if k in ARTEN and isinstance(x, dict)}
        have = {k for k in cur if await asyncio.to_thread(programm, k)}
        old_ver = max((str(x.get("version", "")) for x in cur.values()), key=geraeteupdate.vt, default="")
        if have >= set(clean) and old_ver and not geraeteupdate.newer(ver, old_ver):
            return old_ver
        os.makedirs(CACHE, exist_ok=True)
        for v in clean.values():
            part = os.path.join(CACHE, v["datei"] + ".part")
            n, h = await begleiter._download(c, assets[v["datei"]], v["size"], part)
            if n != v["size"] or not hmac.compare_digest(h, v["sha256"]):
                os.remove(part)
                raise ValueError("Prüfsumme passt nicht, nichts übernommen.")
        for v in clean.values():
            os.replace(os.path.join(CACHE, v["datei"] + ".part"), os.path.join(CACHE, v["datei"]))
        write_json(os.path.join(CACHE, "programme.json"), clean, mode=0o644)
        for name in {x.get("datei") for x in cur.values()} - {v["datei"] for v in clean.values()}:
            if isinstance(name, str) and DATEI.fullmatch(name):
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(CACHE, name))
        sh.log("programm_holen", "neu", len(clean))
        return ver
    finally:
        if own:
            await c.aclose()


async def check():
    """One look on GitHub, with a line in the journal and a „Von selbst“ job on the Live page."""
    import begleiter
    t0, err, word = time.time(), "", "ok"
    try:
        await fetch()
    except begleiter.NotYet as e:            # nothing wrong, just nothing to take yet
        err, word = str(e)[:200], "noch nicht"
    except Exception as e:
        err, word = str(e)[:200] or type(e).__name__, "fehler"
    sh.log("programm_holen", word, 1 if word == "ok" else 0)
    _upd["checked"], _upd["error"] = time.time(), err
    try:
        import live
        live.job("SparkHilfe holen", "GitHub", t0, ok=not err)
    except Exception:
        pass
    return err


async def fetch_loop():
    """While the switch is on and the Notaus lets the internet through: once a day, after an error within the hour."""
    import begleiter
    import notaus
    since = 0.0
    while True:
        await asyncio.sleep(60)
        try:
            if not admin_on() or notaus.blocks("internet"):
                since = 0.0
                continue
            since = since or time.time()
            every = begleiter.RETRY if _upd["error"] else begleiter.FETCH_EVERY
            if time.time() - since >= FIRST and time.time() - _upd["checked"] > every:
                await check()
        except Exception:
            sh.log("programm_holen", "schleife", 0)


# ---------------------------------------------------------------- admin: ask for control
@router.post("/api/admin/spontanhilfe/steuern", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_ask(request: Request):
    """„Steuern anfragen“: only in an open help where the person shares by browser; her page then offers the program."""
    if not admin_on():
        raise HTTPException(404, "Steuern ist aus (Funktionen → Fernzugang zu Servern → Steuern bei der Spontanhilfe).")
    sh._on(request)
    sh._frei(request)
    sh._second_step(request, "steuern_frage")
    guard.limit(request, "spontanhilfe_neu", admin=True)
    h = sh.current()
    sh._mine(request, h)
    if h.stand != "offen" or h.art != "ansehen" or h.person is None:
        sh.log("steuern_frage", "keine hilfe", 0)
        raise HTTPException(409, "Keine offene Hilfe mit Bild.")
    st = of(h)
    st.gefragt = True
    progs = angebot()
    sh.log("steuern_frage", "admin", len(progs))
    sh._live("Spontanhilfe: Steuern angefragt")
    await sh._send(h.person, {"typ": "steuern", "stand": "angefragt", "programme": progs})
    return {"programme": sorted(progs)}


# ---------------------------------------------------------------- the person's page: the file
@router.post("/api/hilfe/programm")
async def person_file(request: Request):
    """The program for her system, only after the admin asked, with her session key; a new one-time key each time
    (the one before stops)."""
    if not admin_on():
        raise HTTPException(404, "Not Found")
    guard.limit(request, "spontanhilfe_start")
    if sh._notaus(count=True):
        sh.log("abgewiesen", "notaus", 0)
        raise HTTPException(503, "Gerade nicht möglich.")
    body = await json_body(request, sh.MAX_BODY)
    h = sh.current()
    tok, art = body.get("tok"), body.get("art")
    st = getattr(h, "st", None) if h is not None else None
    if h is None or h.stand != "offen" or not h.tok_h or st is None or not st.gefragt or not isinstance(tok, str) \
            or not re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", tok) or not hmac.compare_digest(sh._h(tok), h.tok_h):
        sh.log("programm", "abgewiesen", 0)
        raise HTTPException(403, "Bitte die Seite neu laden.")
    p = await asyncio.to_thread(programm, art)
    if p is None:
        sh.log("programm", "fehlt", 0)
        raise HTTPException(404, "Für dieses System gibt es das Programm noch nicht. Ansehen läuft weiter.")
    key = secrets.token_urlsafe(16)       # 128 bits, 22 characters
    st.key_h, st.key_bis = sh._h(key), time.time() + KEY_S
    sh.log("programm", art.split("-")[0], 1)
    return FileResponse(p[0], media_type="application/octet-stream",
                        headers={"X-Spark-Schluessel": key, "X-Spark-Sha256": p[1], "Cache-Control": "no-store",
                                 "Content-Disposition": "attachment; filename=\"SparkHilfe" + ARTEN[art] + "\""})


# ---------------------------------------------------------------- the program's socket
def clean_admin(m):
    """The admin's control messages: the toolbar and the inputs (fernsicht's lists, one check for both)."""
    if m.get("typ") == "modus" and m.get("modus") in ("ansehen", "steuern"):
        return {"typ": "modus", "modus": m["modus"]}
    if m.get("typ") == "eingabe":
        ev = fernsicht.clean_events(m.get("events"))
        return {"typ": "eingabe", "events": ev} if ev else None
    return None


async def from_admin(h, m):
    """A checked toolbar or input message of the admin: inputs reach the program only while she allowed control and
    the toolbar says „Steuern“."""
    st = getattr(h, "st", None)
    if st is None or st.programm is None:
        return
    if m["typ"] == "modus":
        an = m["modus"] == "steuern" and st.modus == "control"
        if an != st.steuern:
            st.steuern = an
            st.gesteuert = st.gesteuert or an
            sh.log("steuern", "an" if an else "ansehen", 1 if an else 0)
            sh._live("Spontanhilfe: Steuern " + ("an" if an else "aus"))
        await sh._send(st.programm, {"typ": "modus", "steuern": st.steuern})
        await sh._send(h.admin, {"typ": "steuern", "stand": st.modus, "steuern": st.steuern})
        return
    if st.steuern and st.modus == "control":
        await sh._send(st.programm, m)


async def close(h, why):
    """The help ends: the program closes too (sh.end calls this)."""
    st = getattr(h, "st", None)
    if st is None:
        return
    st.key_h = ""
    ws, st.programm = st.programm, None
    if ws is not None:
        sh.log("steuern_zu", re.sub(r"[^a-z_]", "", why)[:20] or "ende", int(time.time() - st.seit) // 60 if st.seit else 0)
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps({"typ": "stand", "stand": "zu"}))
        with contextlib.suppress(Exception):
            await ws.close(1000)


async def _refuse(ws, why):
    with contextlib.suppress(Exception):
        await ws.send_text(json.dumps({"typ": "fehler", "grund": "neu laden"}))
    await sh._refuse(ws, why)


@router.websocket("/api/hilfe/steuern")
async def program_ws(ws: WebSocket):
    """SparkHilfe: a program, no page (any Origin header refused); its one-time key only in the first message."""
    if not admin_on():
        return await sh._refuse(ws, "aus", 4404)
    if ws.headers.get("origin") is not None:
        guard.log("foreign_page_refused", path="/api/hilfe/steuern")
        return await sh._refuse(ws, "fremde seite")
    if sh._notaus(count=True):
        return await sh._refuse(ws, "notaus", 4503)
    try:
        guard.limit(ws, "spontanhilfe_start")
    except HTTPException:
        return await sh._refuse(ws, "gesperrt", 4429)
    await ws.accept()
    try:
        raw = await asyncio.wait_for(ws.receive_text(), sh.HALLO_S)
        m = json.loads(raw) if len(raw) < 512 else {}
    except Exception:
        m = {}
    h = sh.current()
    st = getattr(h, "st", None) if h is not None else None
    key = m.get("schluessel") if isinstance(m, dict) and m.get("typ") == "hallo" else None
    ok = (h is not None and h.stand == "offen" and st is not None and st.key_h and st.programm is None
          and time.time() < st.key_bis and isinstance(key, str) and KEY.fullmatch(key) is not None
          and hmac.compare_digest(sh._h(key), st.key_h))
    if not ok:
        sh.log("programm", "schluessel", 0)
        return await _refuse(ws, "schluessel")
    st.key_h = ""                      # once
    st.programm, st.modus, st.steuern, st.seit, st.bilder = ws, "", False, time.time(), []
    sh.log("programm", "verbunden", 1)
    await sh._send(ws, {"typ": "stand", "stand": "frage", "admin": h.admin_name, "bis": int(h.bis),
                        "keys": list(fernsicht.KEYS), "buttons": list(fernsicht.BUTTONS)})
    for side in (h.admin, h.person):
        await sh._send(side, {"typ": "steuern", "stand": "programm"})
    await _program_loop(h, st, ws)


async def _program_loop(h, st, ws):
    from starlette.websockets import WebSocketDisconnect
    why = "programm"
    while sh.current() is h and st.programm is ws:
        try:
            got = await ws.receive()
        except (WebSocketDisconnect, RuntimeError, KeyError):
            break
        if got.get("type") == "websocket.disconnect":
            break
        data, raw = got.get("bytes"), got.get("text")
        if data is not None:
            if len(data) > fernsicht.MAX_FRAME or data[:3] != b"\xff\xd8\xff":
                sh.log("abgewiesen", "bild", 0)
                why = "bild"
                break
            now = time.time()
            st.bilder = [t for t in st.bilder if now - t < 1]
            if st.modus in ("view", "control") and len(st.bilder) < FPS and h.admin is not None:
                st.bilder.append(now)
                with contextlib.suppress(Exception):
                    await h.admin.send_bytes(data)
            continue
        if raw is None or len(raw) > sh.MAX_MSG:
            break
        try:
            m = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(m, dict):
            continue
        if m.get("typ") == "ende":
            break
        if m.get("typ") == "antwort" and m.get("modus") in MODI and not st.modus:
            st.modus = m["modus"]
            sh.log("steuern", {"no": "abgelehnt", "view": "nur ansehen", "control": "erlaubt"}[st.modus],
                   1 if st.modus == "control" else 0)
            await sh._send(h.admin, {"typ": "steuern", "stand": st.modus, "steuern": False})
            await sh._send(h.person, {"typ": "steuern", "stand": st.modus})
            if st.modus == "no":          # she said no: the program goes, the help goes on (looking by browser)
                await close(h, "abgelehnt")
                return
    if st.programm is ws:
        await close(h, why)
        if st.modus in ("view", "control"):     # closing the program she allowed ends the help (plan, Ablauf 6)
            await sh.end(h, why)
        else:
            await sh._send(h.admin, {"typ": "steuern", "stand": "zu"})
