"""Pairing the Pebble watch app "Spark" (pebble/ in the repo) with a profile.

The profile's own browser login (with its second step, when it has one) asks for a setup code: a line
"<address>#pebble=<code>" that the person copies into the watch app's settings on the phone. The phone
sends the code to /api/pebble/pair and gets its own device key with scope "watch". The code is random
(144 bits), works once and for CODE_SECONDS; only its hash is kept, in memory.

A key with scope "watch" only asks (profiles.WATCH_PREFIX: /api/watch/...) and only while the admin
switch chat.pebble and the profile's pebble_on are on. Removing the watch in the panel stops its key.
Keys made by hand in the admin's device list keep working as before.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import profiles
import features
from account import browser_profile
from common import load_config
from core import FACES, assistant, confirm_code, own_profile

router = APIRouter()
_lock = threading.Lock()

CODE_SECONDS = 600
MAX_PENDING = 20          # open codes on the whole Spark
PER_PROFILE = 3           # open codes of one profile (a new one replaces the oldest)
MAX_WATCHES = 5           # paired watches per profile
MAX_BODY = 1024

_pending = {}             # sha256(code) -> {"uid", "t"}


def admin_on():
    return features.admin_on("pebble")


def profile_on(uid):
    return features.profile_on("pebble", uid)


def allowed(uid):
    return features.allowed("pebble", uid)


profiles.WATCH_GATE[0] = allowed


def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def _clean(now):
    for k in [k for k, v in _pending.items() if now - v["t"] > CODE_SECONDS]:
        _pending.pop(k, None)


def new_code(uid, now=None):
    now = time.time() if now is None else now
    code = secrets.token_urlsafe(18)
    with _lock:
        _clean(now)
        mine = sorted((v["t"], k) for k, v in _pending.items() if v["uid"] == uid)
        for _, k in mine[:max(0, len(mine) - PER_PROFILE + 1)]:
            _pending.pop(k, None)
        if len(_pending) >= MAX_PENDING:
            raise HTTPException(429, "Zu viele offene Kopplungen. Bitte in zehn Minuten noch einmal.")
        _pending[_hash(code)] = {"uid": uid, "t": now}
    return code


def take_code(code, now=None):
    """The profile id the code was made for, once; None when unknown, used or expired."""
    now = time.time() if now is None else now
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{20,40}", code):
        return None
    h = _hash(code)
    with _lock:
        _clean(now)
        hit = next((k for k in _pending if hmac.compare_digest(k, h)), None)
        return _pending.pop(hit)["uid"] if hit else None


APP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pebble", "speech-spark.pbw")
_app_cache = {}


def app_version():
    """versionLabel of the watch app the panel serves ("1.4.0"), "" when it is missing."""
    try:
        mtime = os.path.getmtime(APP_FILE)
    except OSError:
        return ""
    if _app_cache.get("mtime") != mtime:
        try:
            with zipfile.ZipFile(APP_FILE) as z:
                label = str(json.loads(z.read("appinfo.json")).get("versionLabel", ""))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            label = ""
        _app_cache.update(mtime=mtime, label=label if re.fullmatch(r"\d{1,3}(\.\d{1,3}){0,2}", label) else "")
    return _app_cache["label"]


def _parts(v):
    return tuple(int(x) for x in v.split("."))


def newer_app(have):
    """True when the panel serves a newer watch app than the one asking (the phone sends its version)."""
    served = app_version()
    if not served or not isinstance(have, str) or not re.fullmatch(r"\d{1,3}(\.\d{1,3}){0,2}", have):
        return False
    return _parts(served) > _parts(have)


def watches(uid):
    return [x for x in profiles.own_devices(uid) if x.get("watch")]


def _base(body):
    """The address the phone reaches the Spark at. http is fine here: the Pebble app does not trust
    the self-signed certificate, so at home it uses the plain panel port."""
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Adresse: http(s)://name oder http(s)://name:port, ohne Pfad.")
    return base


async def _json(request):
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise HTTPException(413, "too large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY:
            raise HTTPException(413, "too large")
    try:
        d = json.loads(bytes(data) or b"{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _on(prof=Depends(browser_profile)):
    """Pairing and managing watches: only from the profile's own browser login, never with a device key."""
    if not admin_on():
        raise HTTPException(403, "the Pebble watch is turned off")
    return prof


@router.get("/api/profile/pebble", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    return {"enabled": admin_on(), "on": profile_on(prof["id"]), "watches": watches(prof["id"]),
            "minutes": CODE_SECONDS // 60, "app": app_version()}


@router.get("/api/profile/pebble/qr", dependencies=[Depends(assistant)])
def profile_qr(base: str, prof=Depends(_on)):
    """QR code of the app file's address, to scan with the phone that is paired with the watch."""
    url = _base({"base": base}) + "/pebble/speech-spark.pbw"
    try:
        import mfa
        svg = mfa._qr_svg(url)
    except Exception:
        svg = ""
    return {"url": url, "qr": svg}


@router.post("/api/profile/pebble/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(_on)):
    """A one-time setup line for the watch app's settings on the phone."""
    body = await _json(request)
    if not profile_on(prof["id"]):
        raise HTTPException(403, "Erst „Pebble-Uhr für mich“ einschalten.")
    if len(watches(prof["id"])) >= MAX_WATCHES:
        raise HTTPException(409, f"Schon {MAX_WATCHES} Uhren gekoppelt. Erst eine entfernen.")
    base = _base(body)
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
    code = new_code(prof["id"])
    print("pebble: setup code made for", prof["name"], flush=True)
    return {"setup": f"{base}#pebble={code}", "minutes": CODE_SECONDS // 60}


@router.delete("/api/profile/pebble/{did}", dependencies=[Depends(assistant)])
def profile_remove(did: str, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in watches(prof["id"])):
        raise HTTPException(404, "no such watch")
    profiles.delete_device(did)
    print("pebble: watch removed for", prof["name"], flush=True)
    return profile_get(prof)


@router.post("/api/pebble/pair")
async def watch_pair(request: Request):
    """The phone's first contact: the one-time code gives the watch app its own key (scope "watch")."""
    guard.limit(request, "pair")
    body = await _json(request)
    uid = take_code(body.get("code"))
    prof = uid and profiles.by_id(uid)
    if not prof or not allowed(uid):
        raise HTTPException(400, "Der Einrichtungscode passt nicht oder ist abgelaufen. Im Panel einen neuen holen.")
    if len(watches(uid)) >= MAX_WATCHES:
        raise HTTPException(409, "Zu viele Uhren für dieses Profil.")
    token = profiles.add_device("Pebble", uid, scope="watch")
    print("pebble: watch paired for", prof["name"], flush=True)
    face = load_config().get("chat", {}).get("face")
    return {"token": token, "profile": prof["name"], "face": face if face in FACES else "robot"}
