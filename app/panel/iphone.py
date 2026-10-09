"""The iPhone app "Spark" (ios/ in the repo): pairing and what the app may do.

Pairing: the profile's own browser login (with its second step, when it has one) asks for a one-time
link. The panel shows it as a QR code for the iPhone camera and as a link for the iPhone the panel is
open on. The link opens the app (spark-app://pair?url=...&code=...); the app sends the code to
/api/iphone/pair and gets its own device key with scope "app". The code is random (144 bits), works
once and for CODE_SECONDS; only its hash is kept, in memory.

A key with scope "app" only asks and listens (profiles.APP_PATHS: chat, speech recognition, the Siri
question, hello). It works only while the admin switch chat.iphone and the profile's app_on are on.
Switching the smart home from the app needs the profile's app_ha as well (chat.py), plus the code word
as everywhere. Removing the iPhone in the panel stops its key at once.
"""
import hashlib
import hmac
import re
import secrets
import threading
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request

import appupdate
import guard
import images
import profiles
from account import browser_profile
from common import load_config
from core import FACES, app_version, assistant, confirm_code, own_profile

router = APIRouter()
_lock = threading.Lock()

CODE_SECONDS = 600
MAX_PENDING = 20          # open codes on the whole Spark
PER_PROFILE = 3           # open codes of one profile (a new one replaces the oldest)
MAX_PHONES = 5            # paired iPhones per profile
MAX_BODY = 4096
SCHEME = "spark-app"

_pending = {}             # sha256(code) -> {"uid", "t"}


def admin_on():
    return bool(load_config().get("chat", {}).get("iphone", False))


def profile_on(uid):
    return bool(profiles.settings(uid).get("app_on"))


def allowed(uid):
    return admin_on() and profile_on(uid)


profiles.APP_GATE[0] = allowed


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


def phones(uid):
    return [x for x in profiles.own_devices(uid) if x.get("app")]


def _name(x):
    name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(x or "")).strip()[:40]
    return name or "iPhone"


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Die App braucht die Adresse des Panels mit https (dein Reverse Proxy), ohne Pfad.")
    return base


def _language():
    return str(load_config().get("asr", {}).get("default_language") or "auto")


def _qr(text):
    try:
        import mfa
        return mfa._qr_svg(text)
    except Exception:
        return ""


async def _json(request, most=MAX_BODY):
    if int(request.headers.get("content-length") or 0) > most:
        raise HTTPException(413, "too large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > most:
            raise HTTPException(413, "too large")
    import json
    try:
        d = json.loads(bytes(data) or b"{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _on(prof=Depends(browser_profile)):
    """Pairing and managing iPhones: only from the profile's own browser login, never with a device key."""
    if not admin_on():
        raise HTTPException(403, "the iPhone app is turned off")
    return prof


@router.get("/api/profile/iphone", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    import apns
    return {"enabled": admin_on(), "on": profile_on(prof["id"]), "phones": phones(prof["id"]),
            "minutes": CODE_SECONDS // 60, "push": apns.ready()}


@router.post("/api/profile/iphone/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(_on)):
    """A one-time link for the app: as a QR code and as a link for this very iPhone."""
    body = await _json(request)
    if not profile_on(prof["id"]):
        raise HTTPException(403, "Erst „iPhone-App für mich“ einschalten.")
    if len(phones(prof["id"])) >= MAX_PHONES:
        raise HTTPException(409, f"Schon {MAX_PHONES} iPhones gekoppelt. Erst eines entfernen.")
    base = _base(body)
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
    code = new_code(prof["id"])
    link = f"{SCHEME}://pair?" + urllib.parse.urlencode({"url": base, "code": code})
    print("iphone: pairing link made for", prof["name"], flush=True)
    return {"link": link, "qr": _qr(link), "minutes": CODE_SECONDS // 60}


@router.delete("/api/profile/iphone/{did}", dependencies=[Depends(assistant)])
def profile_remove(did: str, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in phones(prof["id"])):
        raise HTTPException(404, "no such iPhone")
    profiles.delete_device(did)
    print("iphone: removed for", prof["name"], flush=True)
    return profile_get(prof)


@router.post("/api/iphone/pair")
async def app_pair(request: Request):
    """The app's first contact: the one-time code from the link gives it its own key (scope "app")."""
    guard.limit(request, "pair")
    body = await _json(request)
    uid = take_code(body.get("code"))
    prof = uid and profiles.by_id(uid)
    if not prof or not allowed(uid):
        raise HTTPException(400, "Der Kopplungs-Link passt nicht oder ist abgelaufen. Im Panel einen neuen holen.")
    if len(phones(uid)) >= MAX_PHONES:
        raise HTTPException(409, "Zu viele iPhones für dieses Profil.")
    token = profiles.add_device(_name(body.get("name")), uid, scope="app")
    print("iphone: paired for", prof["name"], flush=True)
    return {"token": token, "profile": prof["name"], "version": app_version(), "language": _language()}


@router.get("/api/iphone/hello", dependencies=[Depends(assistant)])
def app_hello(prof=Depends(own_profile)):
    """The app checks its key: whose it is and which Spark."""
    s = profiles.settings(prof["id"])
    import apns
    import proactive
    face = load_config().get("chat", {}).get("face")
    return {"profile": prof["name"], "version": app_version(), "language": _language(),
            # what the profile allows the app (the panel decides; the app only shows and follows it)
            "listen": bool(s.get("app_listen")), "act": bool(s.get("app_act")),
            "proactive": bool(proactive.enabled() and s.get("pro_on")),
            "reminders": bool(load_config().get("chat", {}).get("reminders", True)),
            # the face the admin picked for everybody (Einstellungen → Vorgaben), only names from the fixed list
            "face": face if face in FACES else "robot",
            # Apple push is set up and on for this profile: reminders then come as push, not as local alarms
            "push": apns.on_for(prof["id"]),
            # CarPlay: the smart home only with its own switch
            "car_ha": bool(s.get("app_car_ha")),
            # documents from the app into "Meine Dokumente"
            "docs": docs_on(prof["id"]),
            # Apple Reminders: Spark reminders and list entries may be written into the iPhone's Reminders
            "ios": bool(s.get("app_ios")),
            # pictures go to the model itself (images.py); without it the app reads text on the phone (OCR)
            "images": images.allowed(prof["id"], "app:x"),
            # Spark updates (appupdate.py): the version page and the start button, rights set by the admin
            "update": appupdate.for_app(prof["id"]),
            # where room mode listens right now (roomlive.py): the line in the chat, the widget and the Live Activity
            "rooms": bool(load_config().get("chat", {}).get("room", False) and s.get("app_room"))}


DOC_BODY = 3 * 1024 * 1024     # the text of one document as JSON (the iPhone reads PDFs and scans itself)
DOC_CHARS = 1_000_000


def docs_on(uid):
    return bool(load_config().get("chat", {}).get("documents", True) and profiles.settings(uid).get("app_docs"))


@router.post("/api/iphone/doc", dependencies=[Depends(assistant)])
async def app_doc(request: Request, prof=Depends(own_profile)):
    """A document from the app into the profile's documents. Only the app's own key, only with app_docs;
    the text is stored as it is, like an upload in the panel (it is data, never an instruction)."""
    import asyncio
    import documents
    dev = profiles.device(request)
    if not dev or dev.get("scope") != "app":
        raise HTTPException(403, "only the iPhone app")
    if not docs_on(prof["id"]):
        raise HTTPException(403, "documents from the app are off (Ich -> iPhone-App)")
    guard.limit(request, "doc", prof["id"], False)
    body = await _json(request, DOC_BODY)
    name, text = body.get("name"), body.get("text")
    if not isinstance(name, str) or not isinstance(text, str):
        raise HTTPException(400, "name and text are required")
    name = re.sub(r"[\x00-\x1f\x7f<>\"\\/:]", "", name).strip()[:100] or "iPhone"
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:DOC_CHARS]
    if not text.strip():
        raise HTTPException(400, "no text")
    try:
        r = await asyncio.to_thread(documents.add, prof["id"], name, text.encode(), text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    print("iphone: document stored,", len(text), "chars", flush=True)
    return r


# The app's "Mein Profil": only these fields, each checked by the same rule as in the panel. What the app
# may do (app_*), Telegram, the smart home and the tone ("style", told to the model) stay in the panel.
APP_FIELDS = ("voice", "speed", "length", "pro_on", "pro_quiet", "pro_max", "pro_events", "pro_lead",
              "pro_weather", "pro_place", "pro_weather_at", "pro_parcel", "pro_bday", "pro_transit",
              "pro_greet", "pro_mail", "briefing_at")
RIGHTS = ("app_ha", "app_car_ha", "app_act", "app_listen", "app_push", "app_docs", "app_ios", "app_images", "app_room")
SETTINGS_BODY = 8192


def _app_only(request):
    dev = profiles.device(request)
    if not dev or dev.get("scope") != "app":
        raise HTTPException(403, "only the iPhone app")


@router.get("/api/iphone/settings", dependencies=[Depends(assistant)])
def app_settings(request: Request, prof=Depends(own_profile)):
    _app_only(request)
    import proactive
    chat = load_config().get("chat", {})
    p = dict(profiles.defaults(chat.get("defaults")), **profiles.settings(prof["id"]))
    return {"settings": {k: p[k] for k in APP_FIELDS},
            # shown only: the tone is changed in the browser login, the rights in Ich -> iPhone-App
            "style": p.get("style", "") if chat.get("own_style", False) else None,
            "rights": {k: bool(p.get(k)) for k in RIGHTS},
            "allow": {"proactive": proactive.enabled(), "documents": bool(chat.get("documents", True))},
            # services the profile switched on in the panel ("Von selbst" can only use those)
            "services": {k: bool(p.get(k)) for k in ("wx_on", "par_on", "con_on", "transit_on")}}


@router.put("/api/iphone/settings", dependencies=[Depends(assistant)])
async def app_settings_save(request: Request, prof=Depends(own_profile)):
    _app_only(request)
    guard.limit(request, "chat", prof["id"], False)
    body = await _json(request, SETTINGS_BODY)
    wrong = [k for k in body if k not in APP_FIELDS]
    if wrong:
        raise HTTPException(400, "not changeable from the app: " + ", ".join(sorted(wrong))[:200])
    bad = [k for k, v in body.items() if not profiles.SETTINGS[k][1](v)]
    if bad:
        raise HTTPException(400, "invalid value: " + ", ".join(sorted(bad)))
    saved = profiles.save_settings(prof["id"], body)
    return {"settings": {k: saved[k] for k in APP_FIELDS if k in saved}}
