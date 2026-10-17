"""What a browser or device can do for itself: login, whoami and the profile's own data
(memory, conversations, documents, reminders, calendar, e-mail, Home Assistant, voice, settings)."""
import asyncio
import inspect
import json
import time
import os
import re
import sys

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPBasicCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent  # noqa: E402
import documents  # noqa: E402
import wissen  # noqa: E402
import guard  # noqa: E402
import push  # noqa: E402
import speakers  # noqa: E402
import calendars  # noqa: E402
import coadmin  # noqa: E402
import echo  # noqa: E402
import mail  # noqa: E402
import memtidy  # noqa: E402
import gedaechtnis  # noqa: E402
import mfa  # noqa: E402
import notaus  # noqa: E402
import passkey  # noqa: E402
import stufen  # noqa: E402
import profiles  # noqa: E402
import homeassistant  # noqa: E402
import features  # noqa: E402
from common import load_config, model_url  # noqa: E402
from core import (  # noqa: E402
    json_body,
    spawn,
    ADMIN_IDLE,
    admin_cookie_ok,
    COOKIE,
    FACES,
    NO_BASIC,
    _session_token,
    acting_profile,
    admin_family,
    end_admin_sessions,
    admin_code,
    admin_code_fresh,
    confirmed_until,
    confirm_login,
    end_window,
    browser_profile,
    secret_profile,
    secret_profile_fresh,
    api_headers,
    auth,
    main_auth,
    admin_login,
    app_version,
    assistant,
    calendar_on,
    check_password,
    confirm_code,
    ha_on,
    is_main_admin,
    mail_on,
    own_profile,
    security,
    speaker_on)
from chat import user_zone  # noqa: E402
from admin import tts_voices  # noqa: E402

router = APIRouter()


# whoami flag -> function in features.py
WHO = {"documents": "documents", "reminders": "reminders", "speaker_id": "speaker", "calendar": "calendar",
       "homeassistant": "ha", "mail": "mail", "mail_tidy": "tidy", "mail_style": "mailstil", "proactive": "proactive", "room": "room",
       "room_voices": "roomtv", "room_ha": "roomha", "room_remote": "roomfar", "weather": "weather", "contacts": "contacts",
       "parcels": "parcels", "telegram": "telegram", "tasks": "tasks", "transit": "transit",
       "esp32": "esp32", "iphone": "iphone", "iphone_panel": "iphonepanel", "pebble": "pebble", "pebble_chat": "pebblechat", "pebble_reply": "pebbleantwort", "pebble_remote": "pebblefern", "pebble_health": "pebblegesund", "pebble_face": "pebblezifferblatt", "pebble_day": "pebbletag", "pebble_alerts": "pebblemeldung", "pebble_note": "pebblemerken", "pebble_place": "pebbleort", "pebble_follow": "pebblefolge", "pebble_quick": "pebbleschnell", "pebble_remind": "pebbleerinnern", "terminal": "terminal",
       "android": "android", "android_live": "androidlive", "android_update": "androidupdate", "android_assist": "androidassist", "android_lock": "androidlock", "mcp_server": "mcpserver", "my_mcp": "mymcp", "write_help": "schreib", "write_apps": "schreibapps", "desk": "begleiter", "desk_act": "begleitertun", "desk_meeting": "begleitermeeting", "desk_view": "begleiterschirm", "desk_operate": "begleiterbedienen",
       "remarkable": "remarkable", "remarkable_send": "rmsend", "remarkable_fresh": "rmfresh", "remarkable_plus": "rmguide", "remarkable_paper": "rmpapier", "remarkable_tasks": "rmaufgaben", "my_status": "mystatus", "usage_count": "verbrauch", "person_priority": "vorrang",
       "ha_live": "halive", "ha_loud": "haloud", "ha_events": "haevent", "ha_voice_rules": "havoice", "ha_camera": "hacam",
       "systemone_mail": "mailwichtig", "report": "melden", "doc_make": "erstellen", "bilder": "bilder", "bilder_aendern": "bildaendern", "musik": "musik", "storage": "speicher", "nas": "nas", "nasquelle": "nasquelle", "nas_drop": "nasablage", "nas_status": "naszustand", "nas_shared": "nashaushalt",
       "chats": "chats", "chats_groups": "chatgroups", "chats_media": "chatmedia", "chats_invite": "chatinvite", "chats_private": "chatprivate", "chats_verbund": "verbund", "verbund_media": "verbundmedia", "verbund_groups": "verbundgruppen",
       "chats_calls": "anrufe", "calls_turn": "anrufeturn", "telefon": "telefon", "saetze": "tippssaetze"}


# the Ich page of a function without a page of its own in features.py (me): reminders live under Mitteilungen
OWN_BOX = {"reminders": "notebox"}


def _locked(prof, request, chat):
    """Functions the admin released but blocked for this profile that still hold its own data (features.OWN): Ich
    shows only „Daten löschen“ in place of their page. Only numbers, never contents; never guests or device keys."""
    if not prof or request.headers.get(profiles.DEVICE_HEADER) or request.scope.get("speech_profile") \
            or request.scope.get("speech_mcp"):
        return []
    out = []
    for key, (count, _clear) in features.OWN.items():
        if not features.admin_on(key, chat) or not features.blocked(key, prof["id"], chat):
            continue
        try:
            n = int(count(prof["id"]) or 0)
        except Exception:   # unreadable data: no card rather than a broken whoami
            n = 0
        if n > 0:
            f = features.BY_KEY[key]
            out.append({"key": key, "box": f.me or OWN_BOX.get(key, ""), "n": n, "name": [f.de, f.en]})
    return out


def _setup(prof, request):
    if not prof or request.headers.get(profiles.DEVICE_HEADER):
        return None
    import onboard
    return onboard.whoami(prof["id"])


@router.get("/api/whoami")
def whoami(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    cfg = load_config()
    chat = features.chat_cfg()
    main = is_main_admin(request, creds)
    elev = None if main else coadmin.session(request)
    prof = profiles.current(request)
    own = prof and not request.headers.get(profiles.DEVICE_HEADER) and coadmin.role(prof["id"])
    return {"admin": bool(main or elev), "admin_by": "main" if main else elev["role"] if elev else "",
            "admin_name": elev["name"] if elev else "",
            # the profile's own role: Ich → Sicherheit says what it may, or why its rights rest right now
            "admin_role": {"role": own, "mfa": mfa.enabled(prof["id"]), "acts": bool(elev),
                           "main": prof["id"] == coadmin.main_uid()} if own else None,
            # admins are not asked at the level "Bestätigen" (core.admin_login, Dominik „A2“)
            "confirm_free": admin_login(request),
            "version": app_version(), "public": cfg.get("chat", {}).get("public", False),
            # the Notaus (notaus.py): its stage, and whether this login may trigger it (the button in the header)
            "notaus": notaus.level(), "notaus_may": bool(main or elev),
            # the login form's "trust this browser" (days) and a right code that still counts (core.CONFIRM_WINDOW)
            "trust_days": mfa.trust_days(), "confirm_until": confirmed_until(request),
            "profile": prof,
            # which pages the panel shows: the Spark's switches from features.py (one place for "on")
            # a function the admin blocked for this profile (Personen und Geräte → Gesperrte Funktionen) shows no page either
            **{name: features.admin_on(key, chat) and not (prof and features.blocked(key, prof["id"], chat))
               for name, key in WHO.items()},
            "agent": bool(prof and agent.level(prof["id"])),
            # Chats (chats.py): the menu entry only for a profile that may use them now (Spark and own switch)
            "chats_use": bool(prof and features.allowed("chats", prof["id"], chat)),
            # what this profile may use now (features.stamp): a page or app that started with another one reloads its switches
            "rights": features.stamp(prof["id"] if prof else None, chat),
            # Spark-Hilfe (hilfe.py): the card in the answer and "Frag Spark" on every page, only for this profile
            "hilfe": {"suggest": features.allowed("hilfevorschlag", prof["id"], chat),
                      "page": features.allowed("hilfeseite", prof["id"], chat)}
            if prof and features.allowed("hilfe", prof["id"], chat) and not request.headers.get(profiles.DEVICE_HEADER) else None,
            # "Funktionen vorschlagen" (tipps.py): the hint under an answer and the list under Ich → Überblick
            "tipps": bool(prof and features.allowed("tipps", prof["id"], chat) and not request.headers.get(profiles.DEVICE_HEADER)),
            # "Los geht's" / "Einrichten x von y" (onboard.py): only for the profile's own login
            "setup": _setup(prof, request),
            # blocked by the admin but own data left (features.OWN): Ich shows only „Daten löschen“ there
            "locked": _locked(prof, request, chat),
            # Logs → Anfragen: main admin and profiles with the role Admin (tracelog.py), not the Verwalter role
            "trace": bool(main or elev and elev.get("role") != "manager") and cfg.get("logs", {}).get("trace", False) is True,
            # Zustand → Live (live.py): the same people
            "live": bool(main or elev and elev.get("role") != "manager") and cfg.get("logs", {}).get("live", False) is True,
            # the profile's own face (Ich → Gespräch → Anzeige), else the Spark's (Einstellungen → Vorgaben); guests the Spark's
            "face": profiles.face_of(prof["id"] if prof else None, cfg.get("chat", {})),
            "face_spark": cfg.get("chat", {}).get("face") if cfg.get("chat", {}).get("face") in FACES else "robot",
            # "Gesicht zeigt, was es tut" (face.js lifeMode): only a plain true switches it on
            "face_life": cfg.get("chat", {}).get("face_life") is True,
            # what the assistant needs without the full configuration (which holds keys)
            "assistant": {"default_voice": cfg["tts"].get("default_voice"),
                          "asr_language": cfg["asr"].get("default_language"),
                          "https_port": cfg["panel"].get("https_port")}}


async def second_step(request: Request, body, who, name, what):
    """After the right password or PIN: the app's code or a passkey (passkey.py), unless the second step is off
    or this browser is trusted. Returns None to go on, or the answer asking for the code."""
    if not mfa.enabled(who) or mfa.trusted(who, request):
        return None
    if isinstance(body.get("passkey"), dict):
        if passkey.finish_auth(who, body["passkey"], request, "login"):
            return None
        guard.failed(request, name, what=what)
        await asyncio.sleep(1)
        raise HTTPException(401, "wrong code")
    code = str(body.get("code", "")).strip()
    if not code:
        # the code field comes next; with a passkey for this host also its challenge
        opt = passkey.begin_auth(who, request, "login") if passkey.available(who, request) else None
        return Response(json.dumps({"code": True, **({"passkey": opt} if opt else {})}), media_type="application/json")
    if not mfa.verify(who, code):
        guard.failed(request, name, what=what)
        await asyncio.sleep(1)
        raise HTTPException(401, "wrong code")
    return None


def _browser_only(request):
    """The panel password is the emergency access (Notzugang): only in a browser. An admin profile's own app is
    admin by its key (coadmin.session), so the app never sends the password (since V01.0.541)."""
    if request.headers.get(profiles.DEVICE_HEADER):
        raise HTTPException(403, "Der Notzugang geht nur im Browser. Ein Admin-Profil ist in seiner App schon Admin.")


def _trust(r, body, who, request):
    """"Diesem Browser vertrauen": an entry in the list of trusted browsers, and a note about it."""
    if body.get("trust") and mfa.enabled(who):
        name = profiles.agent_label(request.headers.get("user-agent", ""))
        if mfa.set_trust(r, who, name):
            guard.log("trusted_browser", ip=guard.client_ip(request), uid=None if who == mfa.ADMIN else who, detail=name)
            spawn(_tell_trusted(who, name))


async def _tell_trusted(who, name):
    """A short note to the person (the admin: the profile chosen for admin notes), if push is set up."""
    uid = coadmin.main_uid() if who == mfa.ADMIN else who
    if not uid:
        return 0
    whose = "den Admin" if who == mfa.ADMIN else "dein Profil"
    try:
        return await push.send(uid, "🔐 Spark", f"Neuer vertrauter Browser für {whose}: {name}. "
                               "Warst du das nicht? Unter Sicherheit entfernen.", tag="security", private=False)
    except Exception as e:
        print("push: trust note failed:", type(e).__name__, flush=True)
        return 0


@router.post("/api/login")
async def login(request: Request):
    body = await request.json()
    guard.check(request, guard.ADMIN)
    _browser_only(request)
    # PBKDF2 with 200 000 rounds takes about 0.2 s on the Spark: in a worker thread, not on the event loop
    if not await asyncio.to_thread(check_password, str(body.get("password", ""))):
        guard.failed(request, guard.ADMIN, what="admin_login")
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "wrong password")
    ask = await second_step(request, body, mfa.ADMIN, guard.ADMIN, "admin_code")
    if ask:
        return ask
    r = Response('{"ok": true}', media_type="application/json")
    guard.succeeded(request, guard.ADMIN, r)
    guard.log("admin_login", ip=guard.client_ip(request))
    r.set_cookie(COOKIE, _session_token(), max_age=ADMIN_IDLE, httponly=True, samesite="strict")
    r.delete_cookie(NO_BASIC)
    _trust(r, body, mfa.ADMIN, request)
    return r


@router.post("/api/logout")
def logout(request: Request):
    end_window(request)
    raw = request.cookies.get(COOKIE, "")
    guard.revoke(raw, ADMIN_IDLE)
    if admin_family(raw):  # also every older or newer copy of this login
        guard.revoke("admin-family:" + admin_family(raw), ADMIN_IDLE)
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(COOKIE)
    r.set_cookie(NO_BASIC, "1", max_age=365 * 86400, httponly=True, samesite="strict")
    return r


@router.post("/api/logout-everywhere", dependencies=[Depends(main_auth)])
async def logout_everywhere(request: Request):
    """Ends the admin login in every browser (this one too)."""
    await admin_code(request)
    end_admin_sessions()
    guard.log("admin_logout_everywhere", ip=guard.client_ip(request))
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(COOKIE)
    return r


# ---------------------------------------------------------------- profiles as admins (coadmin.py)
# The admin gives roles (Admin, Verwalter); a profile with a role is admin in its own browser login and its own
# iPhone app, without a second stage (plan plaene/admin-ohne-zweite-stufe.md).
ADMIN_EVENTS = ("admin_login", "admin_login_failed", "admin_code_failed", "admin_profile_login",
                "admin_role", "admin_role_refused", "admin_main", "admin_mfa_on", "admin_mfa_off", "admin_logout_everywhere",
                "feature_profile", "agent_level", "iphone_update_rights", "person_priority",
                "live_monitor_code", "live_monitor_paired", "live_monitor_deleted", "live_code_failed")


@router.get("/api/admin/roles", dependencies=[Depends(auth)])
def admin_roles():
    return coadmin.listing()


def _by(request):
    """"main" for the panel password, else the acting admin profile's id."""
    me = acting_profile(request)
    return me["id"] if me else "main"


@router.put("/api/admin/roles", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_roles_set(request: Request):
    """{"main": "<profile id>"}: the main admin profile (its code also counts for the panel password); only the
    panel password or the main profile itself changes it."""
    body = await json_body(request, 1024)
    if "main" not in body:
        raise HTTPException(400, "main missing")
    uid = str(body["main"] or "")
    try:
        coadmin.set_main(uid, _by(request))
    except PermissionError as e:
        guard.log("admin_role_refused", ip=guard.client_ip(request), uid=uid or None, detail="haupt")
        raise HTTPException(403, str(e))
    except ValueError as e:
        guard.log("admin_role_refused", ip=guard.client_ip(request), uid=uid or None, detail="haupt")
        raise HTTPException(409, str(e))
    guard.log("admin_main", ip=guard.client_ip(request), uid=uid or None)
    name = (profiles.by_id(uid) or {}).get("name", "")
    spawn(coadmin.tell(f"Haupt-Admin ist jetzt {name}." if name else "Es gibt keinen Haupt-Admin mehr."))
    return coadmin.listing()


@router.put("/api/admin/roles/{uid}", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_role_set(uid: str, request: Request):
    """{"role": "admin" | "manager" | ""}: give, change or take away a profile's role (takes effect at once)."""
    role = str((await json_body(request, 1024)).get("role", "") or "")
    try:
        coadmin.set_role(uid, role, _by(request))
    except LookupError:
        raise HTTPException(404, "no such profile")
    except PermissionError as e:
        guard.log("admin_role_refused", ip=guard.client_ip(request), uid=uid, detail="haupt")
        raise HTTPException(403, str(e))
    except ValueError as e:
        guard.log("admin_role_refused", ip=guard.client_ip(request), uid=uid, detail="regel")
        raise HTTPException(400 if "role must" in str(e) else 409, str(e))
    guard.log("admin_role", ip=guard.client_ip(request), uid=uid, detail=coadmin.NAMES.get(role, "keine"))
    name = (profiles.by_id(uid) or {}).get("name", "")
    spawn(coadmin.tell(f"{name} ist jetzt {coadmin.NAMES[role]}." if role else f"{name} hat keine Admin-Rolle mehr."))
    return coadmin.listing()


def _admin_signed_in(request, uid, name):
    """A profile with a role signed in with its second step: log line and a note to the admin profiles."""
    r = coadmin.acts(uid)
    if not r:
        return
    guard.log("admin_profile_login", ip=guard.client_ip(request), uid=uid, name=name, detail=coadmin.NAMES[r])
    agent_name = profiles.agent_label(request.headers.get("user-agent", ""))
    spawn(coadmin.tell(f"{name} ist als {coadmin.NAMES[r]} angemeldet ({agent_name})."))


@router.get("/api/admin/protocol", dependencies=[Depends(auth)])
def admin_protocol(request: Request, limit: int = 300):
    """Admin actions with who did them: the main admin sees everything, a Verwalter his own."""
    me = acting_profile(request)
    out = []
    for x in guard.read(5000):
        if not (x.get("by") or x.get("event") in ADMIN_EVENTS):
            continue
        if me and me["role"] != "admin" and x.get("by") != me["id"] and not (x.get("event") == "admin_profile_login" and x.get("uid") == me["id"]):
            continue
        out.append(x)
        if len(out) >= max(1, min(limit, 1000)):
            break
    names = {u["id"]: u["name"] for u in profiles.names()}
    return {"events": out, "names": names, "all": not me}


# ---------------------------------------------------------------- profiles
# Who is talking to the assistant. A browser logs in to a profile with its PIN (cookie), a speaker
# sends its device key. Everything stored for a profile is only reachable through that login.
@router.post("/api/profile/login")  # open: without chat.public it is the way in
async def profile_login(request: Request):
    body = await request.json()
    name = str(body.get("name", ""))[:60]
    guard.check(request, name)
    value = await asyncio.to_thread(profiles.login, name, str(body.get("pin", "")), request.headers.get("user-agent", ""))
    if not value:
        guard.failed(request, name, what="profile_login")
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "wrong name or PIN")
    uid = value.split(".", 1)[0]
    ask = await second_step(request, body, uid, name, "profile_code")
    if ask:
        return ask
    admin = bool(coadmin.acts(uid)) and bool(mfa.mark(uid))
    r = Response(json.dumps({"ok": True, **({"admin": True} if admin else {})}), media_type="application/json")
    guard.succeeded(request, name, r)
    guard.log("profile_login", ip=guard.client_ip(request), name=name.strip(), uid=uid)
    r.set_cookie(profiles.COOKIE, value, max_age=profiles.session_secs(), httponly=True, samesite="lax")
    # made with the second step (code, passkey or a trusted browser): this login may act as admin (coadmin.session)
    if mfa.enabled(uid):
        profiles.mark_second_step(value, mfa.mark(uid))
    _trust(r, body, uid, request)
    _admin_signed_in(request, uid, next((u["name"] for u in profiles.names() if u["id"] == uid), name.strip()))
    return r


@router.post("/api/profile/logout")
def profile_logout(request: Request):
    end_window(request)
    raw = request.cookies.get(profiles.COOKIE, "")
    guard.revoke(raw, profiles.session_secs())
    u, _ = profiles._cookie_user(profiles._load(), raw)
    if u and raw.count(".") == 3:
        profiles.end_session(u["id"], raw.split(".")[2])
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(profiles.COOKIE)
    return r


# The profile's own logins: its device keys (with last use), recent logins, log out everywhere.
LOGIN_EVENTS = ("profile_login", "profile_login_failed", "profile_code_failed", "profile_logout_all", "profile_device_removed", "profile_session_end",
                "profile_mfa_on", "profile_mfa_off", "profile_mfa_reset", "invite_pin", "handoff_login")


@router.get("/api/profile/security", dependencies=[Depends(assistant)])
def profile_security(prof=Depends(own_profile)):
    mine = lambda x: x.get("uid") == prof["id"] or (x.get("event") in ("profile_login_failed", "profile_code_failed")
                                                    and str(x.get("name", "")).strip().lower() == prof["name"].lower())
    events = [x for x in guard.read(3000) if x.get("event") in LOGIN_EVENTS and mine(x)][:8]
    import esp32
    spk = esp32.speaker_ids()
    return {"devices": [dict(x, speaker=x["id"] in spk) for x in profiles.own_devices(prof["id"])], "events": events}


@router.get("/api/profile/toollog", dependencies=[Depends(assistant)])
def profile_toollog(prof=Depends(own_profile)):
    return {"days": profiles.TOOL_LOG_DAYS, "items": profiles.tool_log(prof["id"])[::-1]}


@router.post("/api/profile/quality-case", dependencies=[Depends(assistant)])
async def profile_quality_case(request: Request, prof=Depends(browser_profile)):
    """A question the assistant got wrong goes to the admin's quality test (fixes.py, quality.py). Only the
    profile's own browser login; the text comes from the profile's own log, not from the request."""
    guard.limit(request, "chat", uid=prof["id"])
    if not load_config().get("chat", {}).get("learn_fixes") or features.blocked("fixes", prof["id"]):
        raise HTTPException(403, "learning from corrections is off")
    body = await request.json()
    t = body.get("t") if isinstance(body, dict) else None
    if not isinstance(t, int) or isinstance(t, bool):
        raise HTTPException(400, "t is required")
    item = next((x for x in profiles.tool_log(prof["id"]) if x.get("t") == t), None)
    q = next((c["args"] for c in (item or {}).get("calls", []) if c.get("name") == "Korrektur" and c.get("args")), "")
    if not q:
        raise HTTPException(404, "no corrected question in this entry")
    import quality
    if not quality.add_own(q):
        raise HTTPException(409, "already in the test or the list is full")
    guard.log("quality_case", uid=prof["id"])
    return {"ok": True}


@router.delete("/api/profile/toollog", dependencies=[Depends(assistant)])
def profile_toollog_clear(prof=Depends(browser_profile)):
    profiles.tool_log_clear(prof["id"])
    return {"ok": True}


@router.get("/api/profile/sessions", dependencies=[Depends(assistant)])
def profile_sessions(request: Request, prof=Depends(browser_profile)):
    """The browsers signed in to this profile (short browser name, first and last use; this one marked)."""
    return {"sessions": profiles.sessions(prof["id"], request.cookies.get(profiles.COOKIE, "")),
            "days": profiles.session_days()}


@router.delete("/api/profile/sessions/{sid}", dependencies=[Depends(assistant)])
def profile_end_session(sid: str, request: Request, prof=Depends(browser_profile)):
    if not re.fullmatch(r"[0-9a-f]{16}", sid) or not profiles.end_session(prof["id"], sid):
        raise HTTPException(404, "no such login")
    guard.log("profile_session_end", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    return {"ok": True}


async def _app_code(request, prof):
    """From the iPhone app (its key, area "Sicherheit"): a current code of the profile's second step, as the
    area promises (iphone.py); in the profile's own browser the PIN login is that proof already."""
    if request.headers.get(profiles.DEVICE_HEADER):
        await confirm_code(request, prof["id"], prof["name"])


@router.post("/api/profile/logout-all", dependencies=[Depends(assistant)])
async def profile_logout_all(request: Request, prof=Depends(browser_profile)):
    """Ends the login in every browser; this one gets a fresh login and stays signed in."""
    await _app_code(request, prof)
    profiles.end_sessions(prof["id"])
    mfa.forget_trust(prof["id"])  # trusted browsers have to enter a code again
    guard.log("profile_logout_all", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    u = next(u for u in profiles._load()["users"] if u["id"] == prof["id"])
    r = Response('{"ok": true}', media_type="application/json")
    if not request.headers.get(profiles.DEVICE_HEADER):
        mark = profiles.second_step_of(request.cookies.get(profiles.COOKIE, ""))
        value = profiles._cookie_value(u, agent=request.headers.get("user-agent", ""))
        r.set_cookie(profiles.COOKIE, value, max_age=profiles.session_secs(), httponly=True, samesite="lax")
        if mark and mark == mfa.mark(prof["id"]):
            profiles.mark_second_step(value, mark)   # the new login keeps what the old one was made with
    return r


@router.delete("/api/profile/devices/{did}", dependencies=[Depends(assistant)])
async def profile_remove_device(did: str, request: Request, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in profiles.own_devices(prof["id"])):
        raise HTTPException(404, "no such device")
    await _app_code(request, prof)
    profiles.delete_device(did)
    guard.log("profile_device_removed", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"], device=did)
    return {"devices": profiles.own_devices(prof["id"])}


# ---------------------------------------------------------------- second step (authenticator app)
# Admin: under Einstellungen → Sicherheit. Profiles: in their "Ich" window → Sicherheit, only in their
# own browser login (not with a device key) and only while the admin allows it (chat.mfa). Switching
# it off, new recovery codes and a new setup need a current code.
def _admin_reply(request, data):
    """The admin's login cookie is signed with the second step's key: hand this browser a fresh one."""
    r = Response(json.dumps(data), media_type="application/json")
    r.set_cookie(COOKIE, _session_token(), max_age=ADMIN_IDLE, httponly=True, samesite="strict")
    return r


def _not_linked():
    """While the panel password uses the main admin profile's second step (mfa.linked, one code per person),
    that step is changed only there (Ich -> Sicherheit), never through the emergency access."""
    uid = mfa.linked()
    if uid:
        name = next((u["name"] for u in profiles.names() if u["id"] == uid), "")
        raise HTTPException(409, f"Der Notzugang nutzt den zweiten Schritt von {name}. Ändern unter Ich → Sicherheit von {name}.")


@router.get("/api/mfa", dependencies=[Depends(main_auth)])
def admin_mfa():
    uid = mfa.linked()
    return {**mfa.status(mfa.ADMIN),
            "linked": next((u["name"] for u in profiles.names() if u["id"] == uid), "") if uid else ""}


@router.post("/api/mfa/setup", dependencies=[Depends(main_auth), Depends(_not_linked), Depends(admin_code_fresh)])
def admin_mfa_setup():
    return mfa.begin(mfa.ADMIN, "Admin")


@router.post("/api/mfa/enable", dependencies=[Depends(main_auth), Depends(_not_linked)])
async def admin_mfa_enable(request: Request):
    codes = mfa.finish(mfa.ADMIN, (await request.json()).get("code", ""))
    if not codes:
        raise HTTPException(400, "wrong code")
    guard.log("admin_mfa_on", ip=guard.client_ip(request))
    return _admin_reply(request, {"recovery": codes})


@router.post("/api/mfa/disable", dependencies=[Depends(main_auth), Depends(_not_linked), Depends(admin_code_fresh)])
def admin_mfa_disable(request: Request):
    mfa.disable(mfa.ADMIN)
    guard.log("admin_mfa_off", ip=guard.client_ip(request))
    r = _admin_reply(request, {"ok": True})
    r.delete_cookie(mfa.trust_cookie(mfa.ADMIN))
    return r


@router.post("/api/mfa/recovery", dependencies=[Depends(main_auth), Depends(_not_linked), Depends(admin_code_fresh)])
def admin_mfa_recovery(request: Request):
    guard.log("admin_mfa_recovery", ip=guard.client_ip(request))
    return {"recovery": mfa.new_recovery(mfa.ADMIN) or []}


@router.post("/api/mfa/forget", dependencies=[Depends(main_auth)])
def admin_mfa_forget(request: Request):
    """Every trusted browser has to enter a code again, and every other admin login ends."""
    mfa.forget_trust(mfa.ADMIN)
    guard.log("admin_mfa_forget", ip=guard.client_ip(request))
    r = _admin_reply(request, {"ok": True})
    r.delete_cookie(mfa.trust_cookie(mfa.ADMIN))
    return r


# Trusted browsers one by one (mfa.py): the admin's under Einstellungen → Sicherheit, a profile's under Ich → Sicherheit.
_TID = re.compile(r"[0-9a-f]{16}")


@router.get("/api/mfa/trusted", dependencies=[Depends(main_auth)])
def admin_trusted(request: Request):
    return {"items": mfa.list_trusted(mfa.ADMIN, request), "days": mfa.trust_days(), "idle": mfa.TRUST_IDLE_DAYS}


@router.delete("/api/mfa/trusted/{tid}", dependencies=[Depends(main_auth)])
def admin_untrust(tid: str, request: Request):
    guard.limit(request, "trust", admin=True)
    if not _TID.fullmatch(tid) or not mfa.remove_trusted(mfa.ADMIN, tid):
        raise HTTPException(404, "no such browser")
    guard.log("trusted_browser_removed", ip=guard.client_ip(request))
    return {"ok": True}


@router.get("/api/profile/mfa/trusted", dependencies=[Depends(assistant)])
def profile_trusted(request: Request, prof=Depends(browser_profile)):
    return {"items": mfa.list_trusted(prof["id"], request), "days": mfa.trust_days(), "idle": mfa.TRUST_IDLE_DAYS}


@router.delete("/api/profile/mfa/trusted/{tid}", dependencies=[Depends(assistant)])
def profile_untrust(tid: str, request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "trust", uid=prof["id"])
    if not _TID.fullmatch(tid) or not mfa.remove_trusted(prof["id"], tid):
        raise HTTPException(404, "no such browser")
    guard.log("trusted_browser_removed", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    return {"ok": True}


# Passkeys (passkey.py): listed and removed freely, added only with a fresh code (a new way in).
_KID = re.compile(r"[0-9a-f]{16}")


def _passkeys(who, request):
    return {"items": passkey.listing(who, passkey.rp_id(request)), "host": passkey.rp_id(request) or "",
            "ready": passkey._lib() is not None, "max": passkey.MAX_KEYS}


async def _passkey_begin(request, who, label):
    guard.limit(request, "trust", uid=who)
    opt = passkey.begin_add(who, label, request, confirm_login(request, who))
    if not opt:
        raise HTTPException(409, "Passkeys gehen nur über die Adresse mit Namen (https), nicht über eine IP-Adresse, "
                                 f"und höchstens {passkey.MAX_KEYS} pro Person.")
    return opt


async def _passkey_finish(request, who):
    guard.limit(request, "trust", uid=who)
    body = await json_body(request, 16384)
    kid = passkey.finish_add(who, body.get("sid"), body.get("response"), str(body.get("name", ""))[:60], request,
                             confirm_login(request, who))
    if not kid:
        raise HTTPException(400, "Passkey nicht angenommen. Bitte noch einmal von vorn.")
    guard.log("passkey_added", ip=guard.client_ip(request), uid=None if who == mfa.ADMIN else who)
    return _passkeys(who, request)


def _passkey_remove(request, who, kid):
    guard.limit(request, "trust", uid=who)
    if not _KID.fullmatch(kid) or not passkey.remove(who, kid):
        raise HTTPException(404, "no such passkey")
    guard.log("passkey_removed", ip=guard.client_ip(request), uid=None if who == mfa.ADMIN else who)
    return _passkeys(who, request)


@router.get("/api/mfa/passkeys", dependencies=[Depends(main_auth)])
def admin_passkeys(request: Request):
    return _passkeys(mfa.ADMIN, request)


@router.post("/api/mfa/passkeys/begin", dependencies=[Depends(main_auth), Depends(_not_linked), Depends(admin_code_fresh)])
async def admin_passkey_begin(request: Request):
    return await _passkey_begin(request, mfa.ADMIN, "Admin")


@router.post("/api/mfa/passkeys/finish", dependencies=[Depends(main_auth), Depends(_not_linked)])
async def admin_passkey_finish(request: Request):
    return await _passkey_finish(request, mfa.ADMIN)


@router.delete("/api/mfa/passkeys/{kid}", dependencies=[Depends(main_auth), Depends(_not_linked)])
def admin_passkey_remove(kid: str, request: Request):
    return _passkey_remove(request, mfa.ADMIN, kid)


@router.get("/api/profile/mfa/passkeys", dependencies=[Depends(assistant)])
def profile_passkeys(request: Request, prof=Depends(browser_profile)):
    return _passkeys(prof["id"], request)


@router.post("/api/profile/mfa/passkeys/begin", dependencies=[Depends(assistant)])
async def profile_passkey_begin(request: Request, prof=Depends(secret_profile_fresh)):
    if request.scope.get("speech_app_area"):
        raise HTTPException(403, "only in the browser")
    return await _passkey_begin(request, prof["id"], prof["name"])


@router.post("/api/profile/mfa/passkeys/finish", dependencies=[Depends(assistant)])
async def profile_passkey_finish(request: Request, prof=Depends(browser_profile)):
    if request.scope.get("speech_app_area"):
        raise HTTPException(403, "only in the browser")
    return await _passkey_finish(request, prof["id"])


@router.delete("/api/profile/mfa/passkeys/{kid}", dependencies=[Depends(assistant)])
def profile_passkey_remove(kid: str, request: Request, prof=Depends(browser_profile)):
    return _passkey_remove(request, prof["id"], kid)


@router.get("/api/stufen", dependencies=[Depends(assistant)])
def code_levels(request: Request):
    """Ich -> Sicherheit -> „Wann fragt der Spark?": the one list (stufen.py) by level and area, no routes."""
    guard.limit(request, "trust")
    import core
    return {"minutes": core.CONFIRM_WINDOW // 60, "levels": stufen.overview()}


@router.post("/api/confirm/end")  # open: ends only the confirmation window of the logins this request carries
def confirm_end(request: Request):
    """"Bestätigung beenden": the next important change asks for a code again."""
    guard.limit(request, "trust")
    return {"ended": end_window(request)}


@router.get("/api/profile/mfa", dependencies=[Depends(assistant)])
def profile_mfa(prof=Depends(own_profile)):
    return dict(mfa.status(prof["id"]), allowed=bool(load_config().get("chat", {}).get("mfa", False)))


@router.post("/api/profile/mfa/setup", dependencies=[Depends(assistant)])
async def profile_mfa_setup(request: Request, prof=Depends(browser_profile)):
    if not load_config().get("chat", {}).get("mfa", False):
        raise HTTPException(403, "the second login step is turned off")
    await confirm_code(request, prof["id"], prof["name"], fresh=True)
    return mfa.begin(prof["id"], prof["name"])


@router.post("/api/profile/mfa/enable", dependencies=[Depends(assistant)])
async def profile_mfa_enable(request: Request, prof=Depends(browser_profile)):
    codes = mfa.finish(prof["id"], (await request.json()).get("code", ""))
    if not codes:
        raise HTTPException(400, "wrong code")
    # logins made with the PIN alone end everywhere else; this browser stays signed in
    profiles.end_sessions(prof["id"])
    guard.log("profile_mfa_on", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    u = next(u for u in profiles._load()["users"] if u["id"] == prof["id"])
    r = Response(json.dumps({"recovery": codes}), media_type="application/json")
    value = profiles._cookie_value(u, agent=request.headers.get("user-agent", ""))
    r.set_cookie(profiles.COOKIE, value, max_age=profiles.session_secs(), httponly=True, samesite="lax")
    profiles.mark_second_step(value, mfa.mark(prof["id"]))   # this browser just typed the new step's code
    return r


@router.post("/api/profile/mfa/disable", dependencies=[Depends(assistant)])
async def profile_mfa_disable(request: Request, prof=Depends(browser_profile)):
    import join
    if join.mfa_kept(prof["id"]):
        raise HTTPException(403, "Dein Admin verlangt den zweiten Anmeldeschritt für dein Profil.")
    await confirm_code(request, prof["id"], prof["name"], fresh=True)
    mfa.disable(prof["id"])
    guard.log("profile_mfa_off", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(mfa.trust_cookie(prof["id"]))
    return r


@router.post("/api/profile/mfa/recovery", dependencies=[Depends(assistant)])
async def profile_mfa_recovery(request: Request, prof=Depends(browser_profile)):
    await confirm_code(request, prof["id"], prof["name"], fresh=True)
    return {"recovery": mfa.new_recovery(prof["id"]) or []}


@router.get("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_memory(prof=Depends(own_profile)):
    # Gedächtnis prüfen (gedaechtnis.py): with the switches on every fact carries its source, confirmation and mark
    check = features.allowed("gedpruefen", prof["id"])
    return {"profile": prof, "facts": gedaechtnis.view(prof["id"]), "tidy": memtidy.pending(prof["id"]),
            "check": check, "months": gedaechtnis.months() if check else None,
            "topics": {k: v for k, v in gedaechtnis.TOPICS.items()} if gedaechtnis.topics_on(prof["id"]) else None}


@router.post("/api/profile/memory/{fact_id}/confirm", dependencies=[Depends(assistant)])
async def profile_confirm_fact(fact_id: str, request: Request, prof=Depends(browser_profile)):
    """Ich → Gedächtnis → „Stimmt noch“: the fact counts as right from now on (the panel's rules, no model)."""
    guard.limit(request, "memory", uid=prof["id"])
    await json_body(request, 256)
    if not features.allowed("gedpruefen", prof["id"]):
        raise HTTPException(403, "Gedächtnis prüfen ist für dich nicht freigegeben (Funktionen → Gedächtnis prüfen).")
    if not gedaechtnis.confirm(prof["id"], str(fact_id)[:40]):
        raise HTTPException(404, "Eintrag nicht gefunden")
    return {"facts": gedaechtnis.view(prof["id"])}


@router.post("/api/profile/memory/{fact_id}/restore", dependencies=[Depends(assistant)])
async def profile_restore_fact(fact_id: str, request: Request, prof=Depends(browser_profile)):
    """Ich → Gedächtnis → „Zurückholen“: {"i": n} makes the fact's earlier version n its wording again."""
    guard.limit(request, "memory", uid=prof["id"])
    body = await json_body(request, 256)
    if not features.allowed("gedpruefen", prof["id"]):
        raise HTTPException(403, "Gedächtnis prüfen ist für dich nicht freigegeben (Funktionen → Gedächtnis prüfen).")
    i = body.get("i") if isinstance(body, dict) else None
    if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < profiles.MAX_PREV:
        raise HTTPException(400, "i fehlt")
    if not profiles.restore_fact(prof["id"], str(fact_id)[:40], i):
        raise HTTPException(404, "Eintrag oder Fassung nicht gefunden")
    gedaechtnis.log_version(prof["id"], "zurueck")
    return {"facts": gedaechtnis.view(prof["id"])}


@router.post("/api/profile/memory/{fact_id}/topic", dependencies=[Depends(assistant)])
async def profile_fact_topic(fact_id: str, request: Request, prof=Depends(browser_profile)):
    """Ich → Gedächtnis → Thema: {"topic": one of gedaechtnis.TOPICS}; the model never changes it again."""
    guard.limit(request, "memory", uid=prof["id"])
    body = await json_body(request, 256)
    if not gedaechtnis.topics_on(prof["id"]):
        raise HTTPException(403, "Themen sind für dich nicht freigegeben (Funktionen → Gedächtnis prüfen).")
    topic = body.get("topic")
    if topic not in gedaechtnis.TOPICS:
        raise HTTPException(400, "unbekanntes Thema")
    if not any(f["id"] == str(fact_id)[:40] for f in profiles.memory(prof["id"])):
        raise HTTPException(404, "Eintrag nicht gefunden")
    gedaechtnis.set_topics(prof["id"], {str(fact_id)[:40]: topic}, by="hand")
    return {"facts": gedaechtnis.view(prof["id"])}


@router.post("/api/profile/memory/tidy", dependencies=[Depends(assistant)])
async def profile_tidy(request: Request, prof=Depends(browser_profile)):
    """{"do": "check"} asks for a proposal now, "accept" carries it out, "reject" drops it."""
    guard.limit(request, "memory", uid=prof["id"])
    do = (await json_body(request, 256)).get("do")
    if do == "check":
        if not profiles.memory(prof["id"]):
            return {"tidy": None}
        try:
            return {"tidy": await memtidy.propose(prof["id"])}
        except Exception as e:
            print(f"memtidy: language model not reachable ({type(e).__name__})", flush=True)
            raise HTTPException(502, "Das Sprachmodell ist gerade nicht erreichbar. Bitte später noch einmal.")
    if do == "accept":
        n = memtidy.apply(prof["id"])
        guard.log("profile_memory_tidied", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"], removed=n)
        return {"removed": n, "facts": profiles.memory(prof["id"])}
    if do == "reject":
        memtidy.drop(prof["id"])
        return {"tidy": None}
    raise HTTPException(400, "do must be check, accept or reject")


@router.delete("/api/profile/memory/{fact_id}", dependencies=[Depends(assistant)])
def profile_forget(fact_id: str, request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "memory", uid=prof["id"])
    return {"removed": profiles.forget(prof["id"], fact_id=fact_id)}


@router.put("/api/profile/memory/{fact_id}", dependencies=[Depends(assistant)])
async def profile_change_fact(fact_id: str, request: Request, prof=Depends(browser_profile)):
    """Ich → Gedächtnis → Ändern: the person's own wording replaces the fact (no model involved)."""
    guard.limit(request, "memory", uid=prof["id"])
    b = await json_body(request, 4096)
    text = profiles.change_fact(prof["id"], str(fact_id)[:40], str((b or {}).get("text", ""))[:4000])
    if text is None:
        raise HTTPException(404, "Eintrag nicht gefunden oder leer")
    return {"text": text, "facts": profiles.memory(prof["id"])}


@router.post("/api/profile/memory/forget", dependencies=[Depends(assistant)])
async def profile_forget_some(request: Request, prof=Depends(browser_profile)):
    """Ich → Gedächtnis → Auswählen: several facts at once (at most 500)."""
    guard.limit(request, "memory", uid=prof["id"])
    b = await json_body(request, 32768)
    ids = [str(x)[:40] for x in (b or {}).get("ids", []) if isinstance(x, str)][:500] if isinstance((b or {}).get("ids"), list) else []
    if not ids:
        raise HTTPException(400, "ids fehlen")
    return {"removed": profiles.forget(prof["id"], fact_id=ids)}


@router.delete("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_forget_all(prof=Depends(browser_profile)):
    return {"removed": profiles.forget(prof["id"])}


CONVO_SLACK = 5 * 60 * 1000   # "since": a few minutes back, so a device whose clock is a little late is not missed


@router.get("/api/profile/convos", dependencies=[Depends(assistant)])
def profile_convos(request: Request, since: int | None = None, prof=Depends(own_profile)):
    if since is None:
        return profiles.convos(prof["id"])
    guard.limit(request, "convos", prof["id"])
    items = profiles.convos(prof["id"])
    # an open page asks again now and then: only what changed since then, and which ones still exist (deleted elsewhere)
    return {"ids": [x["id"] for x in items], "items": [x for x in items if x.get("updated", 0) > since - CONVO_SLACK]}


CONVO_BODY = 4 * 1024 * 1024   # 60 messages of 20 000 characters


@router.put("/api/profile/convos", dependencies=[Depends(assistant)])
async def profile_save_convo(request: Request, prof=Depends(own_profile)):
    body = await json_body(request, CONVO_BODY, lenient=True)   # size checked while reading (also for the iPhone app)
    ha = homeassistant.get(prof["id"])
    if ha and homeassistant.needs_code(ha) and isinstance(body, dict) and isinstance(body.get("msgs"), list):
        body["msgs"] = [dict(m, content=homeassistant.redact(ha, m.get("content")))
                        if isinstance(m, dict) and m.get("role") == "user" else m for m in body["msgs"]]
    if isinstance(body, dict) and "add" in body:
        guard.limit(request, "convos", prof["id"])
        # only the new messages ("add", not "msgs": an older Spark refuses it instead of replacing the conversation
        # with them): added to the Spark's copy, so what another device added meanwhile stays (replacing the
        # whole conversation lost it); the answer is the whole conversation as it is now
        msgs = body.get("add")
        item = profiles.append_convo(prof["id"], str(body.get("id", "")), str(body.get("title", "")), msgs) \
            if isinstance(msgs, list) and any(isinstance(x, dict) and x.get("role") in ("user", "assistant") and x.get("content")
                                              for x in msgs) else None
        if not item:
            raise HTTPException(400, "invalid conversation")
        return {"ok": True, "item": item}
    item = profiles.save_convo(prof["id"], body)
    if not item:
        raise HTTPException(400, "invalid conversation")
    return {"ok": True}


@router.delete("/api/profile/convos/{cid}", dependencies=[Depends(assistant)])
def profile_delete_convo(cid: str, prof=Depends(own_profile)):
    profiles.delete_convo(prof["id"], cid)
    return {"ok": True}


# Documents: profiles only. Guests can neither upload nor search anything.
@router.get("/api/profile/docs", dependencies=[Depends(assistant)])
def profile_docs(request: Request, prof=Depends(own_profile)):
    dev = profiles.device(request)
    if dev:   # only the profile's iPhone app while Eigene Dokumente is released for it, never other keys
        if dev.get("scope") != "app" or not features.allowed("documents", prof["id"]):
            raise HTTPException(403, "only in the profile's own login or its iPhone app")
    return documents.list_docs(prof["id"])


@router.post("/api/profile/docs", dependencies=[Depends(assistant)])
async def profile_add_doc(file: UploadFile = File(...), prof=Depends(browser_profile)):
    if not load_config().get("chat", {}).get("documents", True):
        raise HTTPException(403, "documents are turned off (Einstellungen -> Funktionen)")
    if features.blocked("documents", prof["id"]):
        raise HTTPException(403, "documents are blocked for this profile (Personen und Geräte → Gesperrte Funktionen)")
    data = await file.read(wissen.pdf_bytes() + 1)
    try:
        return await asyncio.to_thread(wissen.add, prof["id"], file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/profile/docs/{doc_id}", dependencies=[Depends(assistant)])
def profile_delete_doc(doc_id: str, prof=Depends(browser_profile)):
    import nasquelle   # a document from a Wissensordner: left out from now on, the file at the place stays
    nasquelle.excluded(prof["id"], doc_id)
    removed = documents.delete(prof["id"], doc_id)
    if removed:   # a document the Spark made (docmake.py) goes with its file
        import docmake
        docmake.forget(prof["id"], doc_id)
    return {"removed": removed}


@router.get("/api/profile/reminders", dependencies=[Depends(assistant)])
def profile_reminders(request: Request, page: int = 0, push_id: str = "", prof=Depends(own_profile)):
    if page:
        # an open panel page rings by itself: push waits a moment for it, and later notes go to this browser
        push.page_open(prof["id"], push_id[:16])
        import android
        if android.from_app(request) and android.reachable(prof["id"]):
            profiles.used(prof["id"], "and")   # the page inside the Android app: later notes go to that app
    return profiles.reminders(prof["id"])


@router.post("/api/profile/reminders/played", dependencies=[Depends(assistant)])
async def profile_reminder_played(request: Request, prof=Depends(own_profile)):
    """A device is about to play a due reminder: only the first one gets "play", so the other devices
    of the profile (pages, the iPhone app, push) do not repeat it."""
    guard.limit(request, "chat", prof["id"], False)
    body = await request.json()
    rid = str(body.get("id", "") if isinstance(body, dict) else "")[:16]
    if not re.fullmatch(r"[0-9a-f]{1,16}", rid):
        raise HTTPException(400, "id is required")
    # only a due one (a device whose clock runs ahead does not take it early)
    play = profiles.take_reminder(prof["id"], rid, time.time() * 1000 + 60_000) is not None
    if play:   # only the device that plays it writes the line (the others get "play": false)
        print(f"reminders: one played on a device | {profiles.log_name(prof)}", flush=True)
    return {"play": play}


@router.delete("/api/profile/reminders/{rid}", dependencies=[Depends(assistant)])
def profile_reminder_done(rid: str, prof=Depends(own_profile)):
    n = profiles.remove_reminders(prof["id"], {rid})
    print(f"reminders: {n} deleted on a page or device | {profiles.log_name(prof)}", flush=True)
    return {"removed": n}


@router.get("/api/profile/calendar", dependencies=[Depends(assistant)])
def profile_calendar(prof=Depends(own_profile)):
    return calendars.public(prof["id"])


@router.post("/api/profile/calendar", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_add(request: Request, prof=Depends(secret_profile)):
    """Adds a calendar only after it could be read once."""
    body = await request.json()
    body = body if isinstance(body, dict) else {}
    try:
        item = calendars.entry(body)
        found = await calendars.check(item, user_zone(body.get("tz")))
        return dict(calendars.add(prof["id"], item), check=found)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError:
        raise HTTPException(400, "Der Kalender ist nicht erreichbar. Bitte Adresse und Netz prüfen.")


@router.delete("/api/profile/calendar/{cid}", dependencies=[Depends(assistant)])
def profile_calendar_remove(cid: str, prof=Depends(browser_profile)):
    return calendars.remove(prof["id"], cid)


@router.put("/api/profile/calendar/topics", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_topics(request: Request, prof=Depends(browser_profile)):
    body = await request.json()
    return calendars.set_topics(prof["id"], body.get("topics") if isinstance(body, dict) else [])


@router.post("/api/profile/calendar/test", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_test(request: Request, prof=Depends(browser_profile)):
    body = await request.json()
    try:
        return await calendars.test(prof["id"], user_zone(body.get("tz")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/profile/mail", dependencies=[Depends(assistant)])
def profile_mail(prof=Depends(own_profile)):
    return mail.public(prof["id"])


@router.post("/api/profile/mail", dependencies=[Depends(assistant), Depends(mail_on)])
async def profile_mail_add(request: Request, prof=Depends(secret_profile)):
    """Adds a mailbox only after its inbox could be opened once."""
    import join
    if join.mfa_due(prof["id"]):
        raise HTTPException(403, "Erst den zweiten Anmeldeschritt einrichten (Ich → Sicherheit), dann E-Mail verbinden.")
    body = await request.json()
    try:
        item = mail.entry(body if isinstance(body, dict) else {})
        found = await asyncio.wait_for(asyncio.to_thread(mail.check, item), 40)
        return dict(mail.add(prof["id"], item), check=found)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "Der Mailserver ist nicht erreichbar. Bitte Server, Port und Netz prüfen.")


@router.delete("/api/profile/mail/{aid}", dependencies=[Depends(assistant)])
def profile_mail_remove(aid: str, prof=Depends(browser_profile)):
    return mail.remove(prof["id"], aid)


@router.post("/api/profile/mail/test", dependencies=[Depends(assistant), Depends(mail_on)])
async def profile_mail_test(prof=Depends(browser_profile)):
    return await asyncio.to_thread(mail.test, prof["id"])


@router.get("/api/profile/homeassistant", dependencies=[Depends(assistant)])
def profile_ha(prof=Depends(own_profile)):
    return homeassistant.public(prof["id"])


@router.put("/api/profile/homeassistant", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_save(request: Request, prof=Depends(secret_profile)):
    """Stores the connection only after Home Assistant accepted the token."""
    body = await request.json()
    try:
        item = homeassistant.entry(body if isinstance(body, dict) else {}, homeassistant.get(prof["id"]))
        await homeassistant.check(item)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return homeassistant.save(prof["id"], item)


@router.delete("/api/profile/homeassistant", dependencies=[Depends(assistant)])
def profile_ha_remove(prof=Depends(browser_profile)):
    return homeassistant.remove(prof["id"])


@router.put("/api/profile/homeassistant/code", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_code(request: Request, prof=Depends(secret_profile_fresh)):
    """Sets the code word for changes; an empty one removes it. It is never sent back."""
    body = await request.json()
    try:
        res = homeassistant.set_code(prof["id"], str((body or {}).get("code", ""))[:200])
        guard.log("ha_code_set" if res["has_code"] else "ha_code_removed", ip=guard.client_ip(request),
                  name=prof["name"], uid=prof["id"])
        return res
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/profile/homeassistant/test", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_test(request: Request, prof=Depends(browser_profile)):
    item = homeassistant.get(prof["id"])
    if not item:
        raise HTTPException(400, "no Home Assistant connected")
    body = await request.json()
    text = str((body or {}).get("text", "")).strip()
    try:
        if not text:
            return await homeassistant.check(item)
        ok, answer, targets = await homeassistant.command(item, text)
        return {"ok": ok, "answer": answer, "targets": targets}
    except ValueError as e:
        raise HTTPException(400, str(e) or "Home Assistant hat das nicht angenommen.")
    except httpx.HTTPError:
        raise HTTPException(400, "Home Assistant ist nicht erreichbar. Bitte Adresse und Netz prüfen.")


@router.get("/api/profile/voice", dependencies=[Depends(assistant)])
def profile_voice(prof=Depends(own_profile)):
    return {"samples": len(speakers.samples(prof["id"])),
            "enabled": features.admin_on("speaker") and not features.blocked("speaker", prof["id"])}


@router.post("/api/profile/voice", dependencies=[Depends(assistant), Depends(speaker_on)])
async def profile_voice_add(file: UploadFile = File(...), prof=Depends(secret_profile)):
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "recording is too large")
    try:
        n = await asyncio.to_thread(speakers.enroll, prof["id"], data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"samples": n}


@router.delete("/api/profile/voice", dependencies=[Depends(assistant)])
def profile_voice_delete(prof=Depends(browser_profile)):
    speakers.forget(prof["id"])
    return {"samples": 0}


# own data of the functions whose delete routes live here (features.OWN): what those routes remove, nothing else
def _clear_reminders(uid):
    profiles.remove_reminders(uid, {x.get("id") for x in profiles.reminders(uid)})


def _clear_calendars(uid):
    for x in calendars.get(uid)["calendars"]:
        calendars.remove(uid, x["id"])


def _clear_mail(uid):
    for x in mail.get(uid)["accounts"]:
        mail.remove(uid, x["id"])


def _voice_count(uid):
    return len(speakers.samples(uid)) + sum(len(v) for v in speakers.device_samples(uid).values() if isinstance(v, list))


features.OWN.update({"reminders": (lambda uid: len(profiles.reminders(uid)), _clear_reminders),
                     "speaker": (_voice_count, speakers.forget),
                     "calendar": (lambda uid: len(calendars.get(uid)["calendars"]), _clear_calendars),
                     "ha": (lambda uid: int(bool(homeassistant.get(uid))), homeassistant.remove),
                     "mail": (lambda uid: len(mail.get(uid)["accounts"]), _clear_mail)})


@router.delete("/api/profile/owndata/{key}", dependencies=[Depends(assistant)])
async def profile_owndata_delete(key: str, request: Request, prof=Depends(browser_profile)):
    """„Daten löschen“ on the card under Ich for a function the admin blocked for this profile: removes the
    profile's own data of it (features.OWN). Only the profile's own browser login, only while blocked; otherwise
    the function's own page deletes. Never a device key, never a guest."""
    uid = prof["id"]
    guard.limit(request, "owndata", uid)
    if key not in features.OWN:
        print(f"profiles: own data not deleted | unknown function | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "no such function")
    if not features.blocked(key, uid):
        print(f"profiles: own data not deleted | {key} not blocked | {profiles.log_name(prof)}", flush=True)
        f = features.BY_KEY[key]
        raise HTTPException(409, f"„{f.de}“ ist für dich nicht gesperrt. Deine Daten löschst du auf der Seite der "
                                 "Funktion unter Ich.")
    count, clear = features.OWN[key]
    try:
        before = int(count(uid) or 0)
        res = clear(uid)
        if inspect.isawaitable(res):
            await res
        left = int(count(uid) or 0)
    except Exception as e:
        print(f"profiles: own data delete failed | {key} | {type(e).__name__} | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(500, "Die Daten ließen sich nicht ganz löschen. Bitte noch einmal versuchen.")
    n = max(0, before - left)
    print(f"profiles: own data deleted while blocked | {key} | {n} entries, {left} left | {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "n": n}


@router.post("/api/assistant/say", dependencies=[Depends(assistant)])
async def assistant_say(request: Request):
    """Speaks a short text (a due reminder) as streamed PCM events, like the chat's audio."""
    me = profiles.current(request)
    admin = not me and admin_cookie_ok(request)
    guard.limit(request, "chat", me and me["id"], admin)
    body = await request.json()
    # a reminder, or an answer read out again; guests (with "Assistent ohne Anmeldung") a short one
    text = str(body.get("text", "")).strip()[:6000 if me or admin else 1000]
    if not text:
        raise HTTPException(400, "text is required")
    slot = None if me or admin else guard.Slot("chat")   # guests share the few places of the chat
    cfg = load_config()
    who = profiles.current(request)
    pset = profiles.effective(who and who["id"], cfg.get("chat", {}))
    req = {"input": text, "stream": True, "response_format": "pcm"}
    if who and pset.get("voice"):
        req["voice"] = pset["voice"]
    if pset.get("speed", 1.0) != 1.0:
        req["speed"] = pset["speed"]

    device = echo.device_of(request)

    async def gen():
        try:
            async for part in _say(cfg, req, text, who, device):
                yield part
        finally:
            if slot:
                slot.release()
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


async def _say(cfg, req, text, who, device):
    """The TTS stream of /api/assistant/say as server-sent events."""
    mine, until = None, 0.0   # another device of the house does not take this for a question (echo.py)
    pcm = 0                   # bytes spoken (Verbrauchszähler)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
        async with c.stream("POST", model_url("tts", "/v1/audio/speech", cfg),
                            json=req, headers=api_headers()) as r:
            async for line in r.aiter_lines():
                if line.startswith("data:") and "speech.audio.delta" in line:
                    try:
                        audio = json.loads(line[5:])['audio']
                    except (ValueError, KeyError, TypeError):
                        continue
                    if not isinstance(audio, str):
                        continue
                    if mine is None:
                        mine = echo.said(text, who and who["id"], device)
                        until = time.time()
                    # 16-bit mono PCM at 24 kHz: 48000 bytes per second, 4 base64 characters per 3 bytes
                    until = max(until, time.time()) + len(audio) * 3 / 4 / 48000
                    pcm += len(audio) * 3 // 4
                    echo.played(mine, until)
                    yield f"data: {json.dumps({'type': 'audio', 'audio': audio})}\n\n"
    import verbrauch
    verbrauch.spoken("Antwort sprechen", pcm, who=verbrauch.who_of(who))
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.get("/api/profile/settings", dependencies=[Depends(assistant)])
def profile_settings(request: Request):
    """Conversation settings: the admin's defaults, overlaid with the profile's own (if logged in)."""
    prof = profiles.current(request)
    base = profiles.defaults(load_config().get("chat", {}).get("defaults"))
    chat = load_config().get("chat", {})
    import verlauf
    return {"settings": dict(base, **(profiles.settings(prof["id"]) if prof else {})), "defaults": base,
            # the allowed values and bounds (profiles.CHOICES, RANGES): the browser builds its lists only from these
            "choices": profiles.CHOICES, "ranges": profiles.RANGES,
            "profile": prof, "allow": _allow(prof, chat),
            # this browser may keep the conversations for reading offline (trusted, verlauf.offline_here); else it deletes them
            "offline_here": verlauf.offline_here(prof, request)}


# which functions the admin released for this profile (features.py), only for a signed-in profile
ALLOW = {"tool_think": "toolthink", "route": "routing", "direct_read": "direct", "fix_learn": "fixes", "style": "style", "roles": "roles",
         "wiki": "wiki", "kiwix": "kiwix", "local": "lokal", "follow": "follow", "echo": "selfecho", "images": "images",
         "prefetch": "vorab", "instant_ack": "ack", "spark_help": "hilfe", "tips_on": "tipps", "pro_tips": "tippspush", "voice_tips": "tippsstimme", "systemone_on": "einordnung",
         "devup": "geraeteupdate", "devup_night": "geraetenacht", "report": "melden", "doc_make": "erstellen",
         "doc_make_templates": "erstellenvorlagen", "doc_make_wikipics": "erstellenbilder", "bilder": "bilder", "bilder_aendern": "bildaendern", "musik": "musik", "svcwatch": "dienstwacht", "svchint": "dienstnutzer",
         "mem_check": "gedpruefen", "mem_ask": "gedfragen", "mem_topics": "gedthemen",
         "sync_live": "verlaufsync", "sync_one": "eingespraech", "sync_offline": "offlinelesen",
         "chats": "chats", "chatall": "messages_all", "chatann": "messages_announce", "verbund": "verbund",
         "rate": "bewerten", "rateback": "bewertenzurueck", "beratnote": "beraterhinweis", "beratask": "beraterchat",
         "beratme": "beratermich", "klaeren": "klaeren", "klaeren_merken": "klaerenmerken",
         "tagebuch": "tagebuch", "warum": "beraterwarum"}


def _allow(prof, chat):
    out = {k: bool(prof and features.admin_on(f, chat) and not features.blocked(f, prof["id"], chat)) for k, f in ALLOW.items()}
    out["trace"] = bool(prof and load_config().get("logs", {}).get("trace", False) is True)
    # "Bild in Meine Dokumente" under an answer to a picture (wissen.py)
    out["docpics"] = bool(prof and out["images"] and wissen.on(prof["id"], "pictures"))
    # the Dienst-Wächter's notes are for admin profiles only: the others do not see those rows at all
    import notaus
    out["svcadmin"] = bool(out["svcwatch"] and prof["id"] in notaus.admin_uids())
    # the Einstellungs-Assistent's notes and questions are for admin profiles only, like the Dienst-Wächter's
    out["berateradmin"] = bool((out["beratnote"] or out["beratask"]) and prof["id"] in notaus.admin_uids())
    return out


@router.put("/api/profile/settings", dependencies=[Depends(assistant)])
async def profile_save_settings(request: Request, prof=Depends(browser_profile)):
    body = await request.json()
    # what Telegram may reach (personal data, switching the home) only from the profile's own browser
    # login: a shared device with a key cannot open it up
    if isinstance(body, dict) and request.headers.get(profiles.DEVICE_HEADER) \
            and any(k in ("tg_private", "tg_ha", "tg_push", "trace_name") and body[k] for k in body):
        raise HTTPException(403, "only in the profile's own browser login")
    # what the model is told about the tone, too: a device key cannot change it
    if isinstance(body, dict) and request.headers.get(profiles.DEVICE_HEADER) \
            and any(k in body and body[k] != profiles.settings(prof["id"]).get(k, "") for k in ("style", "roles")):
        raise HTTPException(403, "only in the profile's own browser login")
    return {"settings": profiles.save_settings(prof["id"], body)}


@router.get("/api/assistant/voices", dependencies=[Depends(assistant)])
async def assistant_voices(prof=Depends(own_profile)):
    """Voice names to choose from in the conversation settings (profiles only; guests get the default)."""
    v = await tts_voices()
    return {"voices": [x for x in v.get("voices", []) if isinstance(x, str)]}


# Push notifications for reminders, per device of the profile (see push.py).
def _push_on():
    if not load_config().get("chat", {}).get("reminders", True) or not push.available():
        raise HTTPException(403, "reminders are turned off")


@router.get("/api/profile/push", dependencies=[Depends(assistant), Depends(_push_on)])
def profile_push(prof=Depends(own_profile)):
    return {"key": push.public_key(), "devices": [{"name": x.get("name", ""), "created": x.get("created"),
                                                    "endpoint": x["endpoint"]} for x in push.subs(prof["id"])]}


@router.post("/api/profile/push", dependencies=[Depends(assistant), Depends(_push_on)])
async def profile_push_add(request: Request, prof=Depends(secret_profile)):
    body = await request.json()
    try:
        push.add(prof["id"], body.get("subscription"), body.get("name", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    n = await push.send(prof["id"], "Spark", "Erinnerungen kommen jetzt auch auf dieses Gerät.", tag="hello")
    return {"ok": True, "sent": n}


@router.delete("/api/profile/push", dependencies=[Depends(assistant)])
async def profile_push_remove(request: Request, prof=Depends(browser_profile)):
    return {"removed": push.remove(prof["id"], str((await request.json()).get("endpoint", "")))}
