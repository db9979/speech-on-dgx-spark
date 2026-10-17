"""The iPhone app "Spark" (ios/ in the repo): pairing and what the app may do.

Pairing: the profile's own browser login (with its second step, when it has one) asks for a one-time
link. The panel shows it as a QR code for the iPhone camera and as a link for the iPhone the panel is
open on. The link opens the app (spark-app://pair?url=...&code=...); the app sends the code to
/api/iphone/pair and gets its own device key with scope "app". The code is random (144 bits), works
once and for CODE_SECONDS; only its hash is kept, in memory.

A key with scope "app" only asks and listens (profiles.APP_PATHS: chat, speech recognition, the Siri
question, hello). It works only while the admin switch chat.iphone is on and the admin has not blocked the profile.
Switching the smart home from the app needs the profile's app_ha as well (chat.py), plus the code word
as everywhere. Removing the iPhone in the panel stops its key at once.
"""
import re
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

import appupdate
import guard
import kopplung
import images
import profiles
import features
from account import browser_profile
from common import load_config
from core import app_version, assistant, confirm_code, json_body, own_profile

router = APIRouter()

CODE_SECONDS = 600
MAX_PENDING = 20          # open codes on the whole Spark
PER_PROFILE = 3           # open codes of one profile (a new one replaces the oldest)
MAX_PHONES = 5            # paired iPhones per profile
MAX_BODY = 4096
SCHEME = "spark-app"

_codes = kopplung.Codes(kopplung.link_code, kopplung.link_form, CODE_SECONDS, MAX_PENDING, PER_PROFILE)
new_code, take_code, _pending = _codes.new, _codes.take, _codes.pending   # one-time pairing codes (kopplung.py)


def admin_on():
    return features.admin_on("iphone")


def profile_on(uid):
    return features.profile_on("iphone", uid)


def allowed(uid):
    return features.allowed("iphone", uid)


profiles.APP_GATE[0] = allowed


# ---------------------------------------------------------------- panel areas in the app
# The app takes over the panel bit by bit (plan plaene/iphone-uebernimmt-panel.md). The admin switch
# chat.iphone_panel opens every area for every profile at once, only the admin blocks single profiles
# (Freigabe nur durch Admin; the areas' own profile switches are gone since the App-Gleichstand, Dominik
# 2026-10-14). Only these paths open for the app's key; each keeps its own checks (secret_profile
# wants a fresh code from the app, so the profile needs its second step). "Spark verwalten" needs no area: a
# profile with an admin role is admin by its app key (coadmin.session), since V01.0.541 without a switch.
_ID = r"[0-9a-f]{1,16}"
_DOC = r"[0-9a-f]{12}"
_DEV = r"d_[0-9a-f]{12}"
_ACC = r"[mck][0-9a-f]{8}"
AREAS = {
    # Mein Alltag: the next appointments and the Spark's own reminders
    "app_mine": ((("POST",), r"/api/profile/calendar/test"), (("DELETE",), rf"/api/profile/reminders/{_ID}")),
    # Stimme einlernen: the speaker ID sample from the iPhone's microphone (with a fresh code), and
    # "Stimme hier anlernen" at one of the profile's own speakers
    "app_voice": ((("GET", "POST", "DELETE"), r"/api/profile/voice"), (("GET",), r"/api/profile/esp32"),
                  (("POST",), rf"/api/profile/esp32/{_DEV}/voice")),
    # Von selbst: weather place, parcels, bus and train, the profile's jobs (look, stop), room mode longer
    "app_auto": ((("GET", "PUT"), r"/api/profile/weather"), (("POST",), r"/api/profile/weather/test"),
                 (("GET", "PUT"), r"/api/profile/transit"), (("POST",), r"/api/profile/transit/(?:find|test)"),
                 (("GET",), r"/api/profile/parcels"), (("GET",), r"/api/profile/agent"),
                 (("GET",), rf"/api/profile/agent/jobs/{_ID}"), (("POST",), rf"/api/profile/agent/jobs/{_ID}/cancel"),
                 # own tasks (plan „Eigene Aufgaben“): pause, run again or delete a watch or scheduled job
                 (("POST",), rf"/api/profile/agent/plans/{_ID}/pause"), (("DELETE",), rf"/api/profile/agent/plans/{_ID}"),
                 (("POST",), r"/api/room/extend"), (("GET",), r"/api/room/history")),
    # Sicherheit: own logins and devices, log out everywhere, the second step off or new recovery codes
    # (each with a current code). Setting the second step up stays in the browser: there the PIN proves
    # the person, here only the key would.
    "app_security": ((("GET",), r"/api/profile/(?:security|mfa)"), (("POST",), r"/api/profile/logout-all"),
                     (("POST",), r"/api/profile/mfa/(?:disable|recovery)"), (("DELETE",), rf"/api/profile/devices/{_DEV}")),
    # Konten verbinden: mailboxes, calendars, address books, Home Assistant, Telegram. Adding hands the
    # Spark a password or token: secret_profile, from the app only with the profile's second step and a
    # fresh code. Passwords go straight to the Spark's vault and are never sent back.
    "app_accounts": ((("GET", "POST"), r"/api/profile/(?:mail|calendar|contacts)"),
                     (("DELETE",), rf"/api/profile/(?:mail|calendar|contacts)/{_ACC}"),
                     (("POST",), r"/api/profile/mail/test"),
                     (("GET", "PUT", "DELETE"), r"/api/profile/homeassistant"),   # the code word stays in the browser
                     (("GET", "DELETE"), r"/api/profile/telegram"), (("POST",), r"/api/profile/telegram/link")),
}
# "Meine Sachen" in the app (Dominik 2026-10-17, plan app-meine-sachen/plan.md): each part opens with the admin
# release of its own function (the key is its features.py key), no panel switch and no profile switch: what the
# admin released for the profile, the app shows. Each path keeps its own checks (EDIT_KEY for changing pictures,
# DOC_FEATURE switches, the day limits); forgetting everything at once stays in the browser.
THINGS = {
    # Dokumente: the list, the switches, "Für alle", tags, read again, deadline reminder, several at once, the
    # content search, delete (own documents only; the list and reading are APP_PATHS/APP_PATTERNS)
    "documents": ((("GET",), r"/api/profile/wissen"), (("PUT",), rf"/api/profile/wissen/{_DOC}"),
                  (("POST",), rf"/api/profile/wissen/{_DOC}/(?:reread|remind)"),
                  (("POST",), r"/api/profile/wissen/(?:batch|search)"), (("DELETE",), rf"/api/profile/docs/{_DOC}")),
    # Gedächtnis: look, change the wording, forget one or several, the tidy-up proposal
    "memory": ((("GET",), r"/api/profile/memory"), (("DELETE", "PUT"), rf"/api/profile/memory/{_ID}"),
               (("POST",), r"/api/profile/memory/(?:tidy|forget)")),
    # Bilder (bilder.py): look, paint from a wish, delete one or all; change an own picture (FLUX or a quick
    # button) and upload an own photo to change only with Bilder ändern (bilder.EDIT_KEY, checked there)
    "bilder": ((("GET", "POST", "DELETE"), r"/api/bilder"), (("GET",), rf"/api/bilder/job/{_DOC}"),
               (("GET",), rf"/api/bilder/{_DOC}/datei"), (("DELETE",), rf"/api/bilder/{_DOC}"),
               (("POST",), rf"/api/bilder/{_DOC}/(?:aendern|schnell)"), (("POST",), r"/api/bilder/foto")),
    # Musik (musik.py): listen, make from a wish, delete one or all
    "musik": ((("GET", "POST", "DELETE"), r"/api/musik"), (("GET",), rf"/api/musik/job/{_DOC}"),
              (("GET",), rf"/api/musik/{_DOC}/datei"), (("DELETE",), rf"/api/musik/{_DOC}")),
}
# what hello tells the app (the app shows an area where it is true)
RIGHTS_PANEL = ("app_mine", "app_voice", "app_auto", "app_security", "app_accounts")
# conversation settings the app may change with "Mein Alltag" (each still needs its admin switch to matter)
MINE_FIELDS = ("daily", "learn")
# document settings (Ich -> Dokumente) with Meine Sachen → Dokumente; the functions themselves follow the admin release
DOC_FIELDS = ("doc_due",)
AUTO_FIELDS = ()
# switches older apps still send although the admin release alone decides now: ignored. Only the keys the old
# apps sent, all out of profiles.GONE (the one list); app_on and the other rights stay refused (400).
GONE = frozenset(("fix_learn", "tool_think", "route", "doc_pictures", "doc_semantic", "doc_originals", "doc_shared",
                  "doc_brief", "wx_on", "par_on", "transit_on", "agent_on", "con_on",
                  "app_mine", "app_docs_edit", "app_docs", "app_voice", "app_auto", "app_security", "app_accounts",
                  "app_admin"))


def area_on(uid, right):
    """A panel area opens with chat.iphone_panel, a part of Meine Sachen with its own function (THINGS)."""
    return features.allowed(right if right in THINGS else "iphonepanel", uid)


profiles.APP_AREAS.update({right: tuple((frozenset(m), re.compile(p)) for m, p in rules)
                           for right, rules in (AREAS | THINGS).items()})
profiles.APP_AREA_GATE[0] = area_on


def panel_rights(uid):
    """What hello tells the app: which panel areas and which parts of Meine Sachen it shows."""
    return {r: area_on(uid, r) for r in RIGHTS_PANEL + tuple(THINGS)}


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


def _on(request: Request, prof=Depends(browser_profile)):
    """Pairing and managing iPhones: only from the profile's own browser login, never with a device key."""
    if not admin_on():
        raise HTTPException(403, "the iPhone app is turned off")
    if request.method not in ("GET", "HEAD", "DELETE") and features.blocked("iphone", prof["id"]):   # own data: seen and deleted also while blocked
        raise HTTPException(403, "blocked for this profile by the admin (Personen und Geräte → Gesperrte Funktionen)")
    return prof


@router.get("/api/profile/iphone", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    import apns
    return {"enabled": admin_on(), "on": profile_on(prof["id"]), "phones": phones(prof["id"]),
            "minutes": CODE_SECONDS // 60, "push": apns.ready()}


@router.post("/api/profile/iphone/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(_on)):
    """A one-time link for the app: as a QR code and as a link for this very iPhone."""
    body = await json_body(request, MAX_BODY, lenient=True)
    if not profile_on(prof["id"]):
        raise HTTPException(403, "Die iPhone-App hat der Admin für dein Profil gesperrt (Personen und Geräte → Gesperrte Funktionen).")
    if len(phones(prof["id"])) >= MAX_PHONES:
        raise HTTPException(409, f"Schon {MAX_PHONES} iPhones gekoppelt. Erst eines entfernen.")
    base = _base(body)
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
    code = new_code(prof["id"])
    link = f"{SCHEME}://pair?" + urllib.parse.urlencode({"url": base, "code": code})
    print("iphone: pairing link made for", profiles.log_name(prof), flush=True)
    _live_mark("Eingang", "iPhone-App: Kopplungslink erstellt")
    return {"link": link, "qr": _qr(link), "minutes": CODE_SECONDS // 60}


@router.delete("/api/profile/iphone/{did}", dependencies=[Depends(assistant)])
def profile_remove(did: str, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in phones(prof["id"])):
        raise HTTPException(404, "no such iPhone")
    _remove(did)
    print("iphone: removed for", profiles.log_name(prof), flush=True)
    return profile_get(prof)


def _remove(did):
    profiles.delete_device(did)
    _live_mark("Eingang", "iPhone-App entfernt")


def _clear(uid):
    for x in phones(uid):
        _remove(x["id"])


# own data for Ich while the admin blocks the iPhone app for the profile (features.OWN): its paired iPhones
features.OWN["iphone"] = (lambda uid: len(phones(uid)), _clear)


def app_ids():
    """The app's ID for Apple ("TEAMID.bundle"), from the push settings (Funktionen → Push an die iPhone-App), or []."""
    import apns
    s = apns.settings()
    team, bundle = str(s.get("team", "")), str(s.get("bundle", ""))
    if not re.fullmatch(r"[A-Z0-9]{10}", team) or not re.fullmatch(r"[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+){1,8}", bundle):
        return []
    return [team + "." + bundle]


@router.get("/.well-known/apple-app-site-association")  # open: Apple asks for it; only the app's public ID
def apple_site(request: Request):
    """Passkeys in the iPhone app (V01.0.357): Apple fetches this file from the panel's host name and lets
    the app (entitlement webcredentials:<host>) use the passkeys of this host. Says nothing but the app's ID,
    which is public anyway; 404 while the iPhone app is off or push has no Team ID and bundle."""
    guard.limit(request, "trust")
    ids = app_ids() if admin_on() else []
    if not ids:
        raise HTTPException(404, "not found")
    return JSONResponse({"webcredentials": {"apps": ids}}, headers={"Cache-Control": "max-age=3600"})


@router.post("/api/iphone/pair")
async def app_pair(request: Request):
    """The app's first contact: the one-time code from the link gives it its own key (scope "app")."""
    guard.limit(request, "pair")
    body = await json_body(request, MAX_BODY, lenient=True)
    uid = take_code(body.get("code"))
    prof = uid and profiles.by_id(uid)
    if not prof or not allowed(uid):
        raise HTTPException(400, "Der Kopplungs-Link passt nicht oder ist abgelaufen. Im Panel einen neuen holen.")
    if len(phones(uid)) >= MAX_PHONES:
        raise HTTPException(409, "Zu viele iPhones für dieses Profil.")
    token = profiles.add_device(_name(body.get("name")), uid, scope="app")
    print("iphone: paired for", profiles.log_name(prof), flush=True)
    _live_mark("Eingang", "iPhone-App gekoppelt")
    return {"token": token, "profile": prof["name"], "version": app_version(), "language": _language()}


def _admin_role(uid):
    """The role the app acts with: an admin profile is admin in its own app by its key (coadmin.session)."""
    import coadmin
    return coadmin.acts(uid)


@router.get("/api/iphone/hello", dependencies=[Depends(assistant)])
def app_hello(prof=Depends(own_profile)):
    """The app checks its key: whose it is and which Spark."""
    s = profiles.settings(prof["id"])
    import apns
    import proactive
    return {"profile": prof["name"], "version": app_version(), "language": _language(),
            # what the profile allows the app (the panel decides; the app only shows and follows it)
            "listen": bool(s.get("app_listen")), "act": bool(s.get("app_act")),
            "proactive": bool(proactive.enabled() and features.allowed("proactive", prof["id"])),
            "reminders": features.allowed("reminders", prof["id"]),
            # the profile's own face (Ich → Gespräch → Anzeige, also the app's Einstellungen → Gesicht), else the
            # Spark's (Einstellungen → Vorgaben); only names from the fixed list
            "face": profiles.face_of(prof["id"], load_config().get("chat", {})),
            # the face shows what it does (signs, wink, puzzled, asleep), admin switch next to the face
            "face_life": load_config().get("chat", {}).get("face_life") is True,
            # Apple push is set up and on for this profile: reminders then come as push, not as local alarms
            "push": apns.on_for(prof["id"]),
            # CarPlay: the smart home only with its own switch
            "car_ha": bool(s.get("app_car_ha")),
            # "Spark verwalten" with the profile's own role (coadmin.py): "admin", "manager" or "" (none, or its second step off)
            "admin_role": _admin_role(prof["id"]),
            # documents from the app into "Meine Dokumente"
            "docs": features.allowed("documents", prof["id"]),
            # Apple Reminders: Spark reminders and list entries may be written into the iPhone's Reminders
            "ios": bool(s.get("app_ios")),
            # pictures go to the model itself (images.py); without it the app reads text on the phone (OCR)
            "images": images.allowed(prof["id"], "app:x"),
            # Spark updates (appupdate.py): the version page and the start button, rights set by the admin
            "update": appupdate.for_app(prof["id"]),
            # where room mode listens right now (roomlive.py): the line in the chat, the widget and the Live Activity
            "rooms": bool(features.allowed("room", prof["id"]) and s.get("app_room")),
            # panel areas in the app (plaene/iphone-uebernimmt-panel.md); panel: the bridge "Im Panel öffnen"
            "panel": features.allowed("iphonepanel", prof["id"]), "areas": panel_rights(prof["id"]),
            # "Problem melden" in the settings (meldung.py): admin switch and the profile's own
            "report": features.allowed("melden", prof["id"]),
            # "Vom Spark erstellt" (docmake.py): the made documents to look at, download and share
            "make": features.allowed("erstellen", prof["id"]),
            # calls between profiles (anrufe.py): call buttons in a chat of two, CallKit, VoIP push only with this on
            "calls": _calls_on(prof["id"])}


def _calls_on(uid):
    import anrufe
    return bool(anrufe.admin_on() and anrufe.usable(uid))


DOC_BODY = 3 * 1024 * 1024     # the text of one document as JSON (the iPhone reads PDFs and scans itself)
DOC_CHARS = 1_000_000


@router.post("/api/iphone/doc", dependencies=[Depends(assistant)])
async def app_doc(request: Request, prof=Depends(own_profile)):
    """A document from the app into the profile's documents. Only the app's own key, only while Eigene
    Dokumente is released for the profile; the text is stored as it is, like an upload in the panel (it is data, never an instruction)."""
    import asyncio
    import documents
    dev = profiles.device(request)
    if not dev or dev.get("scope") != "app":
        raise HTTPException(403, "only the iPhone app")
    if not features.allowed("documents", prof["id"]):
        raise HTTPException(403, "Eigene Dokumente sind aus (Funktionen → Eigene Dokumente)")
    guard.limit(request, "doc", prof["id"], False)
    body = await json_body(request, DOC_BODY, lenient=True)
    name, text = body.get("name"), body.get("text")
    if not isinstance(name, str) or not isinstance(text, str):
        raise HTTPException(400, "name and text are required")
    name = re.sub(r"[\x00-\x1f\x7f<>\"\\/:]", "", name).strip()[:100] or "iPhone"
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:DOC_CHARS]
    if not text.strip():
        raise HTTPException(400, "no text")
    try:
        r = await asyncio.to_thread(documents.add, prof["id"], name, text.encode(), text, source="app")
    except ValueError as e:
        raise HTTPException(400, str(e))
    print("iphone: document stored,", len(text), "chars", flush=True)
    return r


# The app's "Mein Profil": only these fields, each checked by the same rule as in the panel. What the app
# may do (app_*), Telegram, the smart home and the tone ("style", told to the model) stay in the panel.
APP_FIELDS = ("voice", "speed", "length", "pro_on", "pro_quiet", "pro_max", "pro_events", "pro_lead",
              "pro_weather", "pro_place", "pro_weather_at", "pro_parcel", "pro_bday", "pro_transit",
              "pro_greet", "pro_mail", "briefing_at",
              "hands", "barge",   # Freihändig and Ins Wort fallen: the same values as in the browser (Vereinheitlichen Phase 6)
              "face",             # Einstellungen → Gesicht: the profile's own face, the same as Ich → Gespräch → Anzeige
              "speak")            # Antworten vorlesen: the profile's switch, every device of it follows (chat_turn.quiet)
RIGHTS = ("app_ha", "app_car_ha", "app_act", "app_listen", "app_push", "app_ios", "app_images",
          "app_room")
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
    p = profiles.effective(prof["id"], chat)
    fields = _fields(prof["id"])
    return {"settings": {k: p[k] for k in fields},
            # the allowed values and bounds of the fields with a fixed list (profiles.CHOICES, RANGES), for the pickers
            "choices": {k: v for k, v in profiles.CHOICES.items() if k in fields},
            "ranges": {k: v for k, v in profiles.RANGES.items() if k in fields},
            # which of the conversation switches the admin allows (the rest change nothing)
            "admin": {"tool_think": features.allowed("toolthink", prof["id"], chat), "route": features.allowed("routing", prof["id"], chat),
                      "fix_learn": features.allowed("fixes", prof["id"], chat)},
            # shown only: the tone is changed in the browser login, the rights in Ich -> iPhone-App
            "style": p.get("style", "") if features.allowed("style", prof["id"], chat) else None,
            "rights": {k: bool(p.get(k)) for k in RIGHTS},
            "allow": {"proactive": proactive.enabled() and not features.blocked("proactive", prof["id"], chat),
                      "documents": features.allowed("documents", prof["id"], chat)},
            # services the admin released for this profile ("Von selbst" can only use those)
            "services": {k: features.allowed(f, prof["id"], chat)
                         for k, f in (("wx_on", "weather"), ("par_on", "parcels"), ("con_on", "contacts"),
                                      ("transit_on", "transit"))}}


@router.put("/api/iphone/settings", dependencies=[Depends(assistant)])
async def app_settings_save(request: Request, prof=Depends(own_profile)):
    _app_only(request)
    guard.limit(request, "chat", prof["id"], False)
    body = {k: v for k, v in (await json_body(request, SETTINGS_BODY, lenient=True)).items() if k not in GONE}
    fields = _fields(prof["id"])
    wrong = [k for k in body if k not in fields]
    if wrong:
        raise HTTPException(400, "not changeable from the app: " + ", ".join(sorted(wrong))[:200])
    bad = [k for k, v in body.items() if not profiles.SETTINGS[k][1](v)]
    if bad:
        raise HTTPException(400, "invalid value: " + ", ".join(sorted(bad)))
    saved = profiles.save_settings(prof["id"], body)
    return {"settings": {k: saved[k] for k in fields if k in saved}}


def _fields(uid):
    return APP_FIELDS + sum((f for right, f in (("app_mine", MINE_FIELDS), ("documents", DOC_FIELDS),
                                                ("app_auto", AUTO_FIELDS)) if area_on(uid, right)), ())


def _live_mark(area, text):
    """Zustand → Live: a line under Ereignisse, fixed words only (never the profile's name)."""
    try:
        import live
        live.mark(area, text)
    except Exception:
        pass
