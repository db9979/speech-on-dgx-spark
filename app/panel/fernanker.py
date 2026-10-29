"""Anker-Update (Dominik 2026-10-29 08:59 „1 und 2“): the panel brings its paired anchors to the program it hands out.

- The panel has one Ed25519 signing key of its own (made once; the private half only sealed in the vault, in
  STATE/fernanker.json). It signs „spark-anker <version> <sha256>“ of the program it serves (PROGRAM). Pairing
  hands the public half to the anchor (fernzugang.anker_pair, „sign_pub“), which pins it.
- „Aktualisieren“ (one system) and „Alle aktualisieren“ on the unlocked page send the fixed message
  {"typ": "update", version, sha256, sig} over the anchor's own channel; only to an anchor that is online, knows the
  update (1.3.0 or newer, UPDATE_MIN), runs an older version (never a step back) and has no session open (the restart
  would end it). The anchor fetches the program from its own panel only, checks SHA-256 and signature against the
  pinned key, and its root unit swaps it atomically, restarts and goes back to the one before when the new one has
  not reached the panel within 60 seconds. Its „hallo“ then reports the result (ok, zurueck or why not).
- An anchor before 1.3.0 has neither the root unit nor the key: the page shows the one line
  `curl -fsSL <panel>/fernzugang/anker | sudo python3 - aktualisieren` (POST …/aktualisieren/befehl, from the address
  the browser is on, like the pairing line) with „Kopieren“ and „In die Shell einfügen“ (never Enter). That run asks
  the panel for the signed state with its device key (GET /api/fernzugang/anker/stand), replaces program and units in
  place, keeps keys and pairing and pins the signing key.
- Logs: „fernzugang: aktualisieren | <word> | <number>“ and the version as digits with „_“; never a key or an address.

    GET  /api/fernzugang/anker/stand                 (the anchor's device key) -> {version, sha256, sig, sign_pub}
    POST /api/admin/fernzugang/aktualisieren {geraete: [id …]}   (admin, unlocked page) -> the counts by result
    POST /api/admin/fernzugang/aktualisieren/befehl {origin}     (admin, unlocked page) -> {befehl, befehl_mac}
"""
import asyncio
import base64
import hashlib
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import fernzugang
import guard
import vault
from common import STATE, read_json, write_json
from core import auth, json_body

router = APIRouter()

FILE = os.path.join(STATE, "fernanker.json")   # the signing key: public half, private half sealed
UPDATE_MIN = (1, 3, 0)     # anchors from here on take „update“ over the channel (root unit and pinned key)
MAX_GERAETE = 64           # ids in one request at most (there are at most fernzugang.MAX_ANKER systems)
_lock = threading.Lock()
_CACHE = {}                # sha256 of the program -> its signed state


def _ver(v):
    m = re.fullmatch(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def newer(a, b):
    """Version a is newer than b (an anchor without a version counts as older)."""
    va, vb = _ver(a), _ver(b)
    return bool(va) and (vb is None or va > vb)


def can_update(version):
    """The anchor takes „update“ over its channel (UPDATE_MIN or newer)."""
    v = _ver(version)
    return bool(v) and v >= UPDATE_MIN


def _word(v):
    return str(v or "").replace(".", "_") or "-"


def _key():
    """(private key, public half in base64): made once, the private half only sealed in the vault."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    raw = serialization.Encoding.Raw
    with _lock:
        d = read_json(FILE, {})
        sealed = d.get("priv") if isinstance(d, dict) else None
        if isinstance(sealed, str) and sealed:
            try:
                k = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(vault.open_(sealed)))
                return k, base64.b64encode(k.public_key().public_bytes(raw, serialization.PublicFormat.Raw)).decode()
            except (ValueError, TypeError):
                fernzugang.log("aktualisieren", "schluessel unlesbar", 0)
                raise HTTPException(503, "signing key not readable")
        k = Ed25519PrivateKey.generate()
        priv = k.private_bytes(raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()
        sealed = vault.seal(priv)
        if not str(sealed).startswith(vault.PREFIX):     # never a private key in plain text on the disk
            fernzugang.log("aktualisieren", "tresor fehlt", 0)
            raise HTTPException(503, "vault not available")
        pub = base64.b64encode(k.public_key().public_bytes(raw, serialization.PublicFormat.Raw)).decode()
        write_json(FILE, {"priv": sealed, "pub": pub, "seit": int(time.time())}, mode=0o600)
        fernzugang.log("aktualisieren", "schluessel neu", 1)
        return k, pub


def sign_pub():
    return _key()[1]


def stand():
    """The program the panel hands out, signed: {version, sha256, sig, sign_pub} (cached per SHA-256)."""
    try:
        with open(fernzugang.PROGRAM, "rb") as f:
            prog = f.read()
    except OSError:
        raise HTTPException(404, "not found")
    sha = hashlib.sha256(prog).hexdigest()
    if sha not in _CACHE:
        m = re.search(rb'^VERSION = "(\d{1,3}\.\d{1,3}\.\d{1,3})"$', prog, re.M)
        if not m:
            raise HTTPException(500, "program without a version")
        version = m.group(1).decode()
        k, pub = _key()
        sig = base64.b64encode(k.sign(f"spark-anker {version} {sha}".encode())).decode()
        _CACHE.clear()
        _CACHE[sha] = {"version": version, "sha256": sha, "sig": sig, "sign_pub": pub}
    return dict(_CACHE[sha])


def version():
    try:
        return stand()["version"]
    except HTTPException:
        return ""


def row(x, panel_version):
    """What the page shows of one system: the newer version there is, whether the panel can send it, the last result."""
    have = x.get("anker", "")
    return {"anker_neu": panel_version if panel_version and newer(panel_version, have) else "",
            "anker_fern": can_update(have), "update_stand": x.get("update_stand") or ""}


# ---------------------------------------------------------------- the anchor's answers (fernzugang._on_anker_text)
WORTE = ("laeuft", "kein_schluessel", "nicht_neuer", "laden", "gross", "pruefsumme", "version", "signatur", "schreiben",
         "unlesbar", "ok", "zurueck")


async def on_answer(gid, m):
    """„update_stand“ (the anchor took it or why not) right after the message."""
    w = str(m.get("stand") or "")
    if w not in WORTE:
        return
    fernzugang.log("aktualisieren", w, 1)
    await asyncio.to_thread(fernzugang._update, gid, update_stand=w)


async def on_hello(gid, d):
    """„hallo“ with what the root unit wrote after the last update: logged once (its time), kept for the page."""
    if not isinstance(d, dict):
        return
    w, v, t = str(d.get("stand") or ""), str(d.get("version") or ""), d.get("t")
    if w not in WORTE or not isinstance(t, int):
        return
    x = fernzugang._read()["geraete"].get(gid) or {}
    if x.get("update_t") == t:
        return
    fernzugang.log("aktualisieren", f"{w} {_word(v) if _ver(v) else '-'}", 1)
    fernzugang._live("Fern-Anker aktualisiert" if w == "ok" else "Fern-Anker nicht aktualisiert")
    await asyncio.to_thread(fernzugang._update, gid, update_stand=w, update_t=t)


# ---------------------------------------------------------------- doors
@router.get("/api/fernzugang/anker/stand")
async def anchor_state(request: Request):
    """`spark-anker aktualisieren` (an anchor before 1.3.0 too): the signed state, only for a paired anchor's key."""
    if not fernzugang.admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_koppeln")
    gid, _ = fernzugang.by_key(fernzugang._bearer(request))
    if not gid:
        guard.failed(request, "fernzugang-anker", what="fernzugang_anker")
        fernzugang.log("aktualisieren", "schluessel", 0)
        raise HTTPException(403, "unknown key")
    out = await asyncio.to_thread(stand)
    fernzugang.log("aktualisieren", "stand " + _word(out["version"]), 1)
    return out


@router.post("/api/admin/fernzugang/aktualisieren", dependencies=[Depends(auth)])
async def admin_update(request: Request):
    """„Aktualisieren“ / „Alle aktualisieren“ (the unlocked page): the fixed message to every chosen anchor that can
    take it; the others counted by why not. Nothing here comes from the model or from outside: only the panel's own,
    signed program."""
    fernzugang._on(request)
    fernzugang._frei(request)
    guard.limit(request, "fernzugang_update", admin=True)
    body = await json_body(request, fernzugang.MAX_BODY)
    ids = body.get("geraete")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_GERAETE or not all(isinstance(x, str) for x in ids):
        fernzugang.log("aktualisieren", "ungueltig", 0)
        raise HTTPException(400, "geraete: a list of ids")
    st = await asyncio.to_thread(stand)
    msg = {"typ": "update", "version": st["version"], "sha256": st["sha256"], "sig": st["sig"]}
    geraete = fernzugang._read()["geraete"]
    n = {"gesendet": 0, "aktuell": 0, "alt": 0, "offline": 0, "belegt": 0, "unbekannt": 0}
    for gid in dict.fromkeys(ids):
        x, a = geraete.get(gid), fernzugang.ANKER.get(gid)
        if x is None or x.get("stand") == "abbau":
            why = "unbekannt"
        elif not newer(st["version"], x.get("anker")):
            why = "aktuell"
        elif not can_update(x.get("anker")):
            why = "alt"
        elif a is None:
            why = "offline"
        elif any(s.gid == gid for s in fernzugang.SITZUNG.values()):
            why = "belegt"
        else:
            try:
                await a.send_json(msg)
                why = "gesendet"
                await asyncio.to_thread(fernzugang._update, gid, update_stand="gesendet")
            except Exception:
                why = "offline"
        n[why] += 1
    for why, k in n.items():
        if k:
            fernzugang.log("aktualisieren", why + (" " + _word(st["version"]) if why == "gesendet" else ""), k)
    if n["gesendet"]:
        fernzugang._live("Fern-Anker: Aktualisieren gesendet")
    return {"version": st["version"], **n}


@router.post("/api/admin/fernzugang/aktualisieren/befehl", dependencies=[Depends(auth)])
async def admin_update_line(request: Request):
    """The one line for an anchor before 1.3.0, from the address this browser is on (like the pairing line)."""
    fernzugang._on(request)
    fernzugang._frei(request)
    guard.limit(request, "fernzugang", admin=True)
    body = await json_body(request, fernzugang.MAX_BODY)
    c = fernzugang.command(body.get("origin"), art="aktualisieren")
    if not c:
        fernzugang.log("aktualisieren", "keine adresse", 0)
        raise HTTPException(409, "Die Zeile braucht die https-Adresse des Panels: die Seite über https öffnen.")
    fernzugang.log("aktualisieren", "zeile", 1)
    return {"befehl": c["befehl"], "befehl_mac": c["befehl_mac"]}
