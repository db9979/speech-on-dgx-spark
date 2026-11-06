"""sshTermy als Jump-Host (plan plaene/sshtermy-vermittler.md, Dominik 2026-11-06 „alle empfehlungen umsetzten“): the
client side of sshTermy's Vermittler-Protokoll v1, Stufe B. sshTermy on a computer reaches the paired systems of the
Fernzugang through the panel; SSH runs end to end between sshTermy and the server's own sshd, the panel only passes
the encrypted bytes on (no paramiko here, the session kind „sshtermy“ of fernzugang.aufbauen):

    sshTermy ──WSS /api/fernzugang/sshtermy/v1/kanal──► panel (bytes only) ──anchor pipe, channel n──► spark-anker ──► sshd

Rules (fixed, Sicherheits-Checkliste):
- Admin switch chat.fernzugang_sshtermy (Funktionen → Fernzugang zu Servern → sshTermy als Jump-Host), off, under the
  Fernzugang. No tool for the model, never guests, never the Verwalter: a key belongs to a profile whose role Admin
  counts (coadmin.admin_uids, with its second step) and stops the moment that is no longer so.
- Pairing (E3a): only an admin in the browser on the unlocked page, with a fresh code or passkey, gets the setup line
  `https://<panel>/api/fernzugang/sshtermy#termy=<code>[&fp=<sha256 of the certificate>]` (terminal.setup_base: the
  certificate pinned at home). The code: 144 bits, CODE_S seconds, once, only its hash kept (kopplung.Codes). sshTermy
  trades it for its own device key „sshTermy · <name>“ of that admin profile with scope „sshtermy“ (profiles.current
  gives that key no profile anywhere; only the four ways below take it, as Bearer). At most MAX_GERAETE such keys, at
  most VERSUCHE pairing attempts per address in VERSUCHE_S seconds.
- Unlocking (rule „Bereich entsperren“): POST …/v1/entsperren with a fresh code of the key's admin profile unlocks
  this one key for chat.fernzugang_entsperrt_min minutes from this kind of place (fernzugang.ENTSPERRT, tor()); a
  change between Zuhause and Internet, the Notaus, „Trennen“ … „Entfernen“ lock it. Locked, „systeme“ says
  gesperrt with an empty list and „kanal“ answers 423.
- A channel (E4a: several per key, each counts toward chat.fernzugang_sitzungen): checked in this order before the
  WebSocket is accepted, each with its status of the protocol: switch (503), Notaus (503), key (401, lockout per
  address), admin role (403), own Notaus (503), rate (429), unlocked (423), system known (404), online, allowed and the
  host key right (409), a free place (429), the anchor opened the channel (504). Then only binary messages of at most
  fernzugang.MAX_MSG bytes, both ways. It ends (E2a) after chat.fernzugang_leerlauf_min minutes without any byte,
  after MAX_KANAL_S at the latest, at Trennen, Entfernen (here, in Personen und Geräte or of the system), the switch
  off, the role gone and the Notaus.
- The server's consent stays with a person as root: `sudo spark-anker schluessel dazu '<key>' [--weiterleiten]`
  (anchor 1.11.0) writes sshTermy's own key into ~spark/.ssh/authorized_keys with from="127.0.0.1,::1",restrict,pty;
  the panel can never add one. The anchor reports only fingerprint, type, comment and the forwarding mark
  (POST /api/fernzugang/anker/schluessel), shown on the system's card.
- Live, „Gerade verbunden“, the history and MELDUNG_PUSH show the kind „sshTermy“ and the client „sshTermy“, never
  content. Logs: „fernzugang: sshtermy_<word> | <reason> | <number>“, never a key, a code, a name or an address.

    sshTermy (Bearer: its device key; no cookies, no Origin):
    POST   /api/fernzugang/sshtermy/v1/koppeln {code, name}  -> {key, name, art}
    GET    /api/fernzugang/sshtermy/v1/systeme               -> {name, art, gesperrt, entsperrt_min, systeme[]}
    POST   /api/fernzugang/sshtermy/v1/entsperren {code}     -> {bis}
    WS     /api/fernzugang/sshtermy/v1/kanal?system=<gid>    binary messages: the raw bytes to and from the server's sshd
    anchor (Bearer: its own key):
    POST   /api/fernzugang/anker/schluessel {schluessel[]}    what `schluessel dazu|weg|liste` left on the server
    admin (core.auth, the Fernzugang page unlocked):
    POST   /api/admin/fernzugang/sshtermy/koppeln {origin}   the setup line (browser only, fresh code)
    POST   /api/admin/fernzugang/sshtermy/{did}/trennen      ends this key's channels (browser or own app)
    DELETE /api/admin/fernzugang/sshtermy/{did}              removes the key, its channels end (fresh code; browser or app)
"""
import asyncio
import collections
import contextlib
import hashlib
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

import core
import features
import fernzugang
import guard
import kopplung
import notaus
import profiles
from common import load_config
from core import admin_code_fresh, auth, json_body

router = APIRouter()

BASE = "/api/fernzugang/sshtermy"
V1 = BASE + "/v1"
SCOPE = "sshtermy"
NAME_VORN = "sshTermy · "
ART = "spark"                # what this Vermittler is (protocol: „art“)
BENUTZER = fernzugang.USER   # the login sshTermy suggests (its own key, added on the server by root)
CODE_S = 600                 # a pairing code works this long, once
MAX_GERAETE = 5              # sshTermy keys on this Spark at most
VERSUCHE, VERSUCHE_S = 10, 600   # pairing attempts per address in this many seconds at most
MAX_KANAL_S = 12 * 3600      # one channel at most this long (E2a: the bytes are encrypted, keepalives look like keys)
WACHE_S = 10                 # an open channel checks this often that its key, role and switch still stand
SENDE_S = 20                 # the bytes to sshTermy may wait this long, then the channel ends (a dead line)
MAX_BODY = 1024
MAX_SCHLUESSEL = 20          # keys a server reports at most (the anchor's SCHLUESSEL_MAX)
NAME = re.compile(r"[A-Za-z0-9ÄÖÜäöüß._@+\- ]{1,40}")
KEY = re.compile(r"sd_[A-Za-z0-9_\-]{20,60}")
DID = re.compile(r"d_[0-9a-f]{12}")
FP = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")
TYPEN = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521", "ssh-rsa")
KOMMENTAR = re.compile(r"[A-Za-z0-9._@+\-]{0,60}")
GEMELDET = {"aus": (503, "sshTermy als Jump-Host ist aus (Funktionen → Fernzugang zu Servern → sshTermy als Jump-Host)."),
            "notaus": (503, "Notaus: Fernzugang gesperrt."),
            "schluessel": (401, "Schlüssel unbekannt: in sshTermy neu koppeln."),
            "kein_admin": (403, "Der Schlüssel gehört zu keinem Admin mehr."),
            "gesperrt": (423, "Gesperrt: erst entsperren (Code aus der App)."),
            "unbekannt": (404, "System unbekannt."),
            "offline": (409, "Das System ist nicht verbunden."),
            "voll": (429, "Zu viele Sitzungen offen (Funktionen → Fernzugang zu Servern)."),
            "zu_oft": (429, "Zu viele Versuche, bitte warten."),
            "anker": (504, "Der Anker hat keinen Kanal geöffnet.")}

CODES = kopplung.Codes(kopplung.link_code, kopplung.link_form, CODE_S, 10, 3, kind="sshtermy")
_versuche = {}   # sha256(address) -> deque of times (VERSUCHE in VERSUCHE_S)
ZULETZT = {}     # device id -> time of its last request (memory only, for the admin's list)


def on(c=None):
    """Funktionen → Fernzugang zu Servern → sshTermy als Jump-Host (admin, off); a Spark-wide door (ADMIN_ON_OK)."""
    return features.admin_on("fernsshtermy", c) and fernzugang.admin_on(c)


def tor(did):
    """The unlock of one sshTermy key in fernzugang.ENTSPERRT (never the same as a browser's or an app's)."""
    return hashlib.sha256(b"sshtermy|" + str(did).encode()).hexdigest()


def _spark_name():
    return "Spark"


# ---------------------------------------------------------------- the keys
def geraete():
    """The paired sshTermy keys: [{id, name, user, created}] (profiles.json, scope „sshtermy“)."""
    return profiles.devices_of(SCOPE)


def anzahl():
    return len(geraete())


def _admin(uid):
    import coadmin
    return bool(uid) and uid in coadmin.admin_uids()


def _geraet(conn):
    """The sshTermy key behind this request's Bearer, or None (compared by its hash in constant time)."""
    key = fernzugang._bearer(conn)
    if not KEY.fullmatch(key or ""):
        return None
    dev = profiles.device_by_token(key)
    return dev if dev and dev.get("scope") == SCOPE else None


def _kanaele(did=None):
    return [s for s in fernzugang.SITZUNG.values() if s.art == "sshtermy" and (did is None or s.geraet == did)]


async def schliessen(did, why):
    """Every channel of this key ends now; n."""
    n = 0
    for s in _kanaele(did):
        await s.end(why)
        n += 1
    return n


def view(now=None):
    """The box on the Fernzugang page and the iPhone app: the keys with their profile, unlocked until, open channels."""
    now = time.time() if now is None else now
    out = []
    for x in sorted(geraete(), key=lambda x: x.get("created") or 0):
        p = profiles.by_id(x["user"]) or {}
        e = fernzugang.ENTSPERRT.get(tor(x["id"]))
        bis = e["bis"] if e and e["bis"] > now else None
        out.append({"id": x["id"], "name": str(x.get("name", ""))[len(NAME_VORN):] if str(x.get("name", "")).startswith(NAME_VORN) else x.get("name", ""),
                    "profil": str(p.get("name") or ""), "seit": x.get("created"), "zuletzt": int(ZULETZT[x["id"]]) if x["id"] in ZULETZT else None,
                    "entsperrt_bis": int(bis) if bis else None, "kanaele": len(_kanaele(x["id"])), "admin": _admin(x["user"])})
    return {"max": MAX_GERAETE, "code_s": CODE_S, "geraete": out, "kanaele": len(_kanaele())}


def row(x):
    """The system's card: the sshTermy keys the server reported (fingerprint, type, comment, tunnels), never a key."""
    k = x.get("schluessel")
    return {"schluessel": [dict(y) for y in k] if isinstance(k, list) else None}


def clean(body):
    """The anchor's report as stored here, or None when anything in it is not what the anchor writes."""
    rows = body.get("schluessel") if isinstance(body, dict) else None
    if not isinstance(rows, list) or len(rows) > MAX_SCHLUESSEL:
        return None
    out = []
    for r in rows:
        if not isinstance(r, dict) or not FP.fullmatch(str(r.get("fp", ""))) or r.get("typ") not in TYPEN \
                or not isinstance(r.get("kommentar", ""), str) or not KOMMENTAR.fullmatch(r.get("kommentar", "")) \
                or not isinstance(r.get("weiterleiten", False), bool):
            return None
        out.append({"fp": r["fp"], "typ": r["typ"], "kommentar": r.get("kommentar", ""), "weiterleiten": bool(r.get("weiterleiten"))})
    return out


# ---------------------------------------------------------------- checks of sshTermy's ways
def _status(why):
    return GEMELDET.get(why, (403, "nein"))


async def _pruefen(conn, unlocked=False):
    """(device, uid) for a request or WebSocket of sshTermy, else (None, why): switch, Notaus, the key (lockout per
    address), the admin role, the own Notaus, the rate per key; with unlocked=True also the unlock."""
    if not on():
        return None, "aus"
    if fernzugang._notaus(count=True):
        return None, "notaus"
    try:
        guard.check(conn, "sshtermy-schluessel")
    except HTTPException:
        return None, "zu_oft"
    dev = _geraet(conn)
    if dev is None:
        await asyncio.to_thread(guard.failed, conn, "sshtermy-schluessel", "fernzugang_sshtermy")
        return None, "schluessel"
    if not _admin(dev["user"]):
        return None, "kein_admin"
    if notaus.own(dev["user"]):
        return None, "notaus"
    try:
        guard.limit(conn, "fernzugang_sshtermy", uid="st:" + dev["id"])
    except HTTPException:
        return None, "zu_oft"
    ZULETZT[dev["id"]] = time.time()
    if len(ZULETZT) > 100:
        ZULETZT.clear()
    if unlocked and fernzugang.entsperrt_bis(conn, tor=tor(dev["id"])) is None:
        return None, "gesperrt"
    return dev, ""


def _nein(word, why):
    fernzugang.log(word, why, 0)
    status, text = _status(why)
    raise HTTPException(status, text, headers={"Retry-After": "60"} if status == 429 else None)


def _versuch(request, now=None):
    """At most VERSUCHE pairing attempts per address in VERSUCHE_S (the protocol's rule), else 429."""
    now = time.time() if now is None else now
    k = hashlib.sha256(guard.client_ip(request).encode()).hexdigest()
    q = _versuche.setdefault(k, collections.deque(maxlen=VERSUCHE))
    while q and now - q[0] > VERSUCHE_S:
        q.popleft()
    if len(q) >= VERSUCHE:
        fernzugang.log("sshtermy_koppeln", "zu oft", 0)
        raise HTTPException(429, GEMELDET["zu_oft"][1], headers={"Retry-After": str(int(VERSUCHE_S - (now - q[0])) + 1)})
    q.append(now)
    if len(_versuche) > 1000:
        for x in [x for x, v in _versuche.items() if not v or now - v[-1] > VERSUCHE_S]:
            _versuche.pop(x, None)


@router.post("/api/fernzugang/sshtermy/v1/koppeln")
async def koppeln(request: Request):
    """sshTermy's first contact: the one-time code from „Koppeln (Code)“ for its own device key."""
    if not on():
        _nein("sshtermy_koppeln", "aus")
    if fernzugang._notaus(count=True):
        _nein("sshtermy_koppeln", "notaus")
    _versuch(request)
    guard.limit(request, "fernzugang_sshtermy_koppeln")
    guard.check(request, "sshtermy-koppeln")
    body = await json_body(request, MAX_BODY)
    uid = CODES.take(body.get("code"))
    if not uid:
        await asyncio.to_thread(guard.failed, request, "sshtermy-koppeln", "fernzugang_sshtermy")
        await asyncio.sleep(1)
        fernzugang.log("sshtermy_koppeln", "falsch", 0)
        raise HTTPException(403, "Der Code passt nicht oder ist abgelaufen: im Panel neu „Koppeln (Code)“.")
    if not _admin(uid):
        fernzugang.log("sshtermy_koppeln", "kein admin", 0)
        raise HTTPException(403, GEMELDET["kein_admin"][1])
    if anzahl() >= MAX_GERAETE:
        fernzugang.log("sshtermy_koppeln", "voll", 0)
        raise HTTPException(429, f"Schon {MAX_GERAETE} sshTermy gekoppelt: erst eins entfernen.")
    name = str(body.get("name") or "").strip()
    name = name if NAME.fullmatch(name) else "sshTermy"
    key = await asyncio.to_thread(profiles.add_device, NAME_VORN + name, uid, scope=SCOPE)
    guard.succeeded(request, "sshtermy-koppeln")
    fernzugang.log("sshtermy_koppeln", "ok", anzahl())
    guard.log("fernzugang_sshtermy_paired", detail="sshTermy gekoppelt")
    fernzugang._live("sshTermy gekoppelt")
    return {"key": key, "name": _spark_name(), "art": ART}


@router.get("/api/fernzugang/sshtermy/v1/systeme")
async def systeme(request: Request):
    """The paired systems for sshTermy: only unlocked; locked, gesperrt with an empty list (like admin_get)."""
    dev, why = await _pruefen(request)
    if dev is None:
        _nein("sshtermy_systeme", why)
    c = features.chat_cfg()
    head = {"name": _spark_name(), "art": ART, "entsperrt_min": fernzugang.entsperrt_s(c) // 60}
    if fernzugang.entsperrt_bis(request, tor=tor(dev["id"])) is None:
        return {**head, "gesperrt": True, "systeme": []}
    g = fernzugang._read()["geraete"]
    ordner = {}
    import fernordner
    if fernordner.on(c):
        v = fernordner.view(list(g))
        namen = {o["id"]: o.get("name", "") for o in v.get("ordner") or ()}
        ordner = {gid: namen.get(o, "") for gid, o in v["systeme"].items()}
    out = []
    for gid, x in sorted(g.items(), key=lambda kv: str(kv[1].get("name", "")).lower()):
        if x.get("stand") == "abbau" or not x.get("hostkey"):
            continue
        ok = gid in fernzugang.ANKER and x.get("erlaubt", True) and not x.get("wartet") and not x.get("hostkey_falsch")
        out.append({"id": gid, "name": str(x.get("name", "")), "os": str(x.get("os", "")), "online": bool(ok),
                    "hostkey": x["hostkey"], "ordner": ordner.get(gid, ""), "benutzer": BENUTZER})
    return {**head, "gesperrt": False, "systeme": out}


@router.post("/api/fernzugang/sshtermy/v1/entsperren")
async def entsperren(request: Request):
    """A fresh code of the key's admin profile unlocks this key for chat.fernzugang_entsperrt_min minutes."""
    dev, why = await _pruefen(request)
    if dev is None:
        _nein("sshtermy_entsperrt", why)
    import mfa
    uid = dev["user"]
    prof = profiles.by_id(uid) or {}
    body = await json_body(request, MAX_BODY)
    code = re.sub(r"\s", "", str(body.get("code") or ""))[:40]
    if not mfa.enabled(uid) or not code:
        _nein("sshtermy_entsperrt", "kein code")
    # the one code check of the panel (core.confirm_code: lockout per name, a passkey would count the same), with the
    # code sshTermy sends in the body
    request.scope["headers"] = [h for h in request.scope["headers"] if h[0] != core.CODE_HEADER.encode()] + \
        [(core.CODE_HEADER.encode(), code.encode())]
    with contextlib.suppress(AttributeError):
        del request._headers
    try:
        await core.confirm_code(request, uid, prof.get("name", ""), fresh=True)
    except HTTPException as e:
        if e.status_code == 429:
            fernzugang.log("sshtermy_entsperrt", "zu oft", 0)
            raise
        fernzugang.log("sshtermy_entsperrt", "falsch", 0)
        raise HTTPException(403, "Der Code passt nicht.") from None
    now, dauer = time.time(), fernzugang.entsperrt_s()
    word = "verlaengert" if fernzugang.entsperrt_bis(request, now, tor=tor(dev["id"])) is not None else "ok"
    fernzugang.ENTSPERRT[tor(dev["id"])] = {"bis": now + dauer, "herkunft": fernzugang._herkunft(request)}
    fernzugang.log("sshtermy_entsperrt", word, dauer // 60)
    return {"bis": int(now + dauer)}


async def _deny(ws, why, word="sshtermy_kanal"):
    """No channel: the protocol's HTTP status before the WebSocket is accepted (else a close code 4000 + status)."""
    fernzugang.STATS["abgewiesen"] += 1
    fernzugang.log(word, why, 0)
    status, text = _status(why)
    if "websocket.http.response" in ws.scope.get("extensions", {}):
        with contextlib.suppress(Exception):
            await ws.send_denial_response(JSONResponse({"fehler": text, "detail": text}, status_code=status))
        return
    with contextlib.suppress(Exception):
        await ws.close(4000 + status)


@router.websocket("/api/fernzugang/sshtermy/v1/kanal")
async def kanal(ws: WebSocket):
    """One raw channel to a system's own sshd for sshTermy (see the module's rules for the order of the checks)."""
    dev, why = await _pruefen(ws, unlocked=True)
    if dev is None:
        return await _deny(ws, why)
    gid = str(ws.query_params.get("system", ""))
    x = fernzugang._read()["geraete"].get(gid) if fernzugang.GID.fullmatch(gid) else None
    if not x or x.get("stand") == "abbau":
        return await _deny(ws, "unbekannt")
    _g, _a, _n, why = fernzugang._platz(gid)
    if why:
        return await _deny(ws, why)
    s, g, why = await fernzugang.aufbauen(gid, "sshtermy", None, "sshtermy", dev["user"], login="st:" + dev["id"], conn=ws)
    if s is None:
        return await _deny(ws, why if why in ("voll", "offline") else "anker")
    s.geraet, s.client = dev["id"], "sshtermy"
    try:
        await ws.accept()
    except Exception:
        await s.end("sshtermy")
        return
    s.browser = ws

    async def weiter(data):
        try:
            await asyncio.wait_for(ws.send_bytes(data), SENDE_S)
        except Exception:
            await s.end("sshtermy")
    if s.puffer:
        await weiter(bytes(s.puffer))
        s.puffer = bytearray()
    s.weiter = weiter
    fernzugang.STATS["sitzungen"] += 1
    fernzugang.log("sshtermy_kanal", "ok", len(fernzugang.SITZUNG))
    fernzugang._live("sshTermy-Kanal geöffnet")
    s.tasks += [asyncio.create_task(fernzugang._melden(s, g)), asyncio.create_task(s._idle()),
                asyncio.create_task(_wache(s, dev["id"]))]
    await _schleife(s, ws)


async def _wache(s, did):
    """The channel ends at MAX_KANAL_S, and as soon as its key is gone (removed anywhere), its profile no admin, the
    switch off or the Notaus on."""
    t0 = time.monotonic()
    while not s.ende.is_set():
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(s.ende.wait(), WACHE_S)
        if s.ende.is_set():
            return
        if time.monotonic() - t0 >= MAX_KANAL_S:
            return await s.end("hoechstdauer")
        dev = next((x for x in geraete() if x["id"] == did), None)
        if dev is None:
            return await s.end("entfernt")
        if not on() or fernzugang._notaus() or not _admin(dev["user"]):
            return await s.end("notaus" if fernzugang._notaus() else "aus")


async def _schleife(s, ws):
    """sshTermy's bytes to the anchor's channel, until either side closes or a rule ends it."""
    try:
        while not s.ende.is_set():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data, text = msg.get("bytes"), msg.get("text")
            if len(data or b"") > fernzugang.MAX_MSG or len(text or "") > fernzugang.MAX_MSG:
                await s.end("zu_gross")
                break
            if fernzugang._notaus() or not on():
                await s.end("notaus" if fernzugang._notaus() else "aus")
                break
            if data:
                s.zuletzt = time.time()
                await s.anker.send_bytes(bytes([s.n]) + data)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    except Exception as e:
        fernzugang.log("sshtermy_zu", "fehler " + type(e).__name__[:20], 0)
    finally:
        await s.end(s.grund or "sshtermy")


# ---------------------------------------------------------------- the anchor's report of the keys on the server
@router.post("/api/fernzugang/anker/schluessel")
async def anker_schluessel(request: Request):
    """`schluessel dazu|weg|liste` on the server: the fingerprints, types, comments and tunnel marks now there."""
    if not fernzugang.admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_koppeln")
    gid, _x = fernzugang.by_key(fernzugang._bearer(request))
    if not gid:
        await asyncio.to_thread(guard.failed, request, "fernzugang-anker", "fernzugang_anker")
        fernzugang.log("schluessel", "schluessel", 0)
        raise HTTPException(403, "unknown key")
    rows = clean(await json_body(request, 16 * 1024))
    if rows is None:
        fernzugang.log("schluessel", "meldung falsch", 0)
        raise HTTPException(400, "bad report")
    await asyncio.to_thread(fernzugang._update, gid, schluessel=rows)
    fernzugang.log("schluessel", "gemeldet", len(rows))
    fernzugang._live("Schlüssel für sshTermy gemeldet")
    return {}


# ---------------------------------------------------------------- the admin's box „sshTermy als Jump-Host“
def _tuer(request, app=False):
    if not on():
        raise HTTPException(404, "sshTermy als Jump-Host ist aus (Funktionen → Fernzugang zu Servern → sshTermy als Jump-Host).")
    if app:
        fernzugang._admin_here(request)
    else:
        fernzugang._browser(request)
    if fernzugang._notaus(count=True):
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    fernzugang._frei(request)


@router.post("/api/admin/fernzugang/sshtermy/koppeln", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_koppeln(request: Request):
    """„Koppeln (Code)“: the setup line for sshTermy (browser only, the unlocked page, a fresh code every time)."""
    _tuer(request)
    fernzugang._second_step(request)
    guard.limit(request, "fernzugang_code", admin=True)
    body = await json_body(request, MAX_BODY)
    import coadmin
    prof = core.acting_profile(request)
    uid = prof["id"] if prof else coadmin.main_uid()
    if not _admin(uid):
        fernzugang.log("sshtermy_code", "kein profil", 0)
        raise HTTPException(409, "sshTermy koppelt an ein Admin-Profil mit zweitem Schritt: erst eins anlegen (Personen und Geräte).")
    if anzahl() >= MAX_GERAETE:
        fernzugang.log("sshtermy_code", "voll", 0)
        raise HTTPException(409, f"Schon {MAX_GERAETE} sshTermy gekoppelt: erst eins entfernen.")
    import terminal
    base = terminal.setup_base(body.get("origin"), load_config("panel"))
    if not base:
        fernzugang.log("sshtermy_code", "kein https", 0)
        raise HTTPException(409, "Über diese Adresse geht es nur mit https. sshTermy spricht nur verschlüsselt mit dem Spark.")
    code = CODES.new(uid)
    fernzugang.log("sshtermy_code", fernzugang._who(request), 1)
    guard.log("fernzugang_sshtermy_code", detail="Kopplungszeile für sshTermy erstellt")
    return {"setup": f"{base[0]}{BASE}#termy={code}" + (f"&fp={base[1]}" if base[1] else ""), "gilt_s": CODE_S,
            "pinned": bool(base[1])}


def _eines(did):
    if not DID.fullmatch(did) or not any(x["id"] == did for x in geraete()):
        raise HTTPException(404, "no such sshTermy")


@router.post("/api/admin/fernzugang/sshtermy/{did}/trennen", dependencies=[Depends(auth)])
async def admin_trennen(did: str, request: Request):
    """„Trennen“: this key's open channels end now (it stays paired and unlocked)."""
    _tuer(request, app=True)
    guard.limit(request, "fernzugang", admin=True)
    _eines(did)
    n = await schliessen(did, "getrennt")
    fernzugang.log("sshtermy_trennen", fernzugang._who(request), n)
    return {"n": n}


@router.delete("/api/admin/fernzugang/sshtermy/{did}", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_entfernen(did: str, request: Request):
    """„Entfernen“: the key stops at once, its unlock and its channels end (a fresh code every time)."""
    _tuer(request, app=True)
    guard.limit(request, "fernzugang", admin=True)
    _eines(did)
    await asyncio.to_thread(profiles.delete_device, did)
    fernzugang.ENTSPERRT.pop(tor(did), None)
    ZULETZT.pop(did, None)
    n = await schliessen(did, "entfernt")
    fernzugang.log("sshtermy_entfernen", fernzugang._who(request), n)
    guard.log("fernzugang_sshtermy_removed", detail="sshTermy entfernt")
    fernzugang._live("sshTermy entfernt")
    return {"ok": True}
