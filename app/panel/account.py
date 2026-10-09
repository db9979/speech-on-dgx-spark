"""What a browser or device can do for itself: login, whoami and the profile's own data
(memory, conversations, documents, reminders, calendar, e-mail, Home Assistant, voice, settings)."""
import asyncio
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
import echo  # noqa: E402
import mail  # noqa: E402
import memtidy  # noqa: E402
import mfa  # noqa: E402
import profiles  # noqa: E402
import homeassistant  # noqa: E402
from common import load_config  # noqa: E402
from core import (  # noqa: E402
    ADMIN_IDLE,
    admin_cookie_ok,
    COOKIE,
    FACES,
    NO_BASIC,
    _session_token,
    admin_family,
    end_admin_sessions,
    admin_code,
    browser_profile,
    secret_profile,
    api_headers,
    auth,
    app_version,
    assistant,
    calendar_on,
    check_password,
    confirm_code,
    ha_on,
    is_admin,
    mail_on,
    own_profile,
    security,
    speaker_on)
from chat import user_zone  # noqa: E402
from admin import tts_voices  # noqa: E402

router = APIRouter()


@router.get("/api/whoami")
def whoami(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    cfg = load_config()
    return {"admin": is_admin(request, creds), "version": app_version(), "public": cfg.get("chat", {}).get("public", False),
            "profile": profiles.current(request), "documents": cfg.get("chat", {}).get("documents", True),
            "reminders": cfg.get("chat", {}).get("reminders", True),
            "speaker_id": cfg.get("chat", {}).get("speaker_id", False),
            "calendar": cfg.get("chat", {}).get("calendar", True),
            "homeassistant": cfg.get("chat", {}).get("homeassistant", False),
            "mail": cfg.get("chat", {}).get("mail", False),
            "mail_tidy": bool(cfg.get("chat", {}).get("mail", False) and cfg.get("chat", {}).get("mail_tidy", False)),
            "proactive": cfg.get("chat", {}).get("proactive", False),
            "room": cfg.get("chat", {}).get("room", False),
            "room_voices": bool(cfg.get("chat", {}).get("room", False) and cfg.get("chat", {}).get("room_voices", False)),
            "room_ha": bool(cfg.get("chat", {}).get("room", False) and cfg.get("chat", {}).get("room_ha", False)),
            "room_remote": bool(cfg.get("chat", {}).get("room", False) and cfg.get("chat", {}).get("room_remote", False)
                                and cfg.get("chat", {}).get("esp32", False)),
            "weather": cfg.get("chat", {}).get("weather", False),
            "contacts": cfg.get("chat", {}).get("contacts", False),
            "parcels": bool(cfg.get("chat", {}).get("mail", False) and cfg.get("chat", {}).get("parcels", False)),
            "telegram": cfg.get("chat", {}).get("telegram", False),
            "tasks": cfg.get("chat", {}).get("tasks", False),
            "transit": cfg.get("chat", {}).get("transit", False),
            "agent": bool(cfg.get("chat", {}).get("agent", False) and profiles.current(request)
                          and agent.granted(profiles.current(request)["id"])),
            "messages": bool(cfg.get("chat", {}).get("messages", False)),
            "esp32": cfg.get("chat", {}).get("esp32", False),
            "iphone": cfg.get("chat", {}).get("iphone", False),
            "pebble": cfg.get("chat", {}).get("pebble", False),
            "face": cfg.get("chat", {}).get("face") if cfg.get("chat", {}).get("face") in FACES else "robot",
            # what the assistant needs without the full configuration (which holds keys)
            "assistant": {"default_voice": cfg["tts"].get("default_voice"),
                          "asr_language": cfg["asr"].get("default_language"),
                          "https_port": cfg["panel"].get("https_port")}}


async def second_step(request: Request, body, who, name, what):
    """After the right password or PIN: the app's code, unless the second step is off or this
    browser is trusted. Returns None to go on, or the answer asking for the code."""
    if not mfa.enabled(who) or mfa.trusted(who, request):
        return None
    code = str(body.get("code", "")).strip()
    if not code:
        return Response('{"code": true}', media_type="application/json")  # the code field comes next
    if not mfa.verify(who, code):
        guard.failed(request, name, what=what)
        await asyncio.sleep(1)
        raise HTTPException(401, "wrong code")
    return None


def _trust(r, body, who):
    if body.get("trust") and mfa.enabled(who):
        mfa.set_trust(r, who)


@router.post("/api/login")
async def login(request: Request):
    body = await request.json()
    guard.check(request, guard.ADMIN)
    if not check_password(str(body.get("password", ""))):
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
    _trust(r, body, mfa.ADMIN)
    return r


@router.post("/api/logout")
def logout(request: Request):
    raw = request.cookies.get(COOKIE, "")
    guard.revoke(raw, ADMIN_IDLE)
    if admin_family(raw):  # also every older or newer copy of this login
        guard.revoke("admin-family:" + admin_family(raw), ADMIN_IDLE)
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(COOKIE)
    r.set_cookie(NO_BASIC, "1", max_age=365 * 86400, httponly=True, samesite="strict")
    return r


@router.post("/api/logout-everywhere", dependencies=[Depends(auth)])
async def logout_everywhere(request: Request):
    """Ends the admin login in every browser (this one too)."""
    await admin_code(request)
    end_admin_sessions()
    guard.log("admin_logout_everywhere", ip=guard.client_ip(request))
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(COOKIE)
    return r


# ---------------------------------------------------------------- profiles
# Who is talking to the assistant. A browser logs in to a profile with its PIN (cookie), a speaker
# sends its device key. Everything stored for a profile is only reachable through that login.
@router.post("/api/profile/login")  # open: without chat.public it is the way in
async def profile_login(request: Request):
    body = await request.json()
    name = str(body.get("name", ""))[:60]
    guard.check(request, name)
    value = profiles.login(name, str(body.get("pin", "")))
    if not value:
        guard.failed(request, name, what="profile_login")
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "wrong name or PIN")
    uid = value.split(".", 1)[0]
    ask = await second_step(request, body, uid, name, "profile_code")
    if ask:
        return ask
    r = Response('{"ok": true}', media_type="application/json")
    guard.succeeded(request, name, r)
    guard.log("profile_login", ip=guard.client_ip(request), name=name.strip(), uid=value.split(".", 1)[0])
    r.set_cookie(profiles.COOKIE, value, max_age=profiles.SESSION_DAYS * 86400, httponly=True, samesite="lax")
    _trust(r, body, uid)
    return r


@router.post("/api/profile/logout")
def profile_logout(request: Request):
    guard.revoke(request.cookies.get(profiles.COOKIE, ""), profiles.SESSION_DAYS * 86400)
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(profiles.COOKIE)
    return r


# The profile's own logins: its device keys (with last use), recent logins, log out everywhere.
LOGIN_EVENTS = ("profile_login", "profile_login_failed", "profile_code_failed", "profile_logout_all", "profile_device_removed",
                "profile_mfa_on", "profile_mfa_off", "profile_mfa_reset")


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
    if not load_config().get("chat", {}).get("learn_fixes", False):
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


@router.post("/api/profile/logout-all", dependencies=[Depends(assistant)])
def profile_logout_all(request: Request, prof=Depends(browser_profile)):
    """Ends the login in every browser; this one gets a fresh login and stays signed in."""
    profiles.end_sessions(prof["id"])
    mfa.forget_trust(prof["id"])  # trusted browsers have to enter a code again
    guard.log("profile_logout_all", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    u = next(u for u in profiles._load()["users"] if u["id"] == prof["id"])
    r = Response('{"ok": true}', media_type="application/json")
    if not request.headers.get(profiles.DEVICE_HEADER):
        r.set_cookie(profiles.COOKIE, profiles._cookie_value(u), max_age=profiles.SESSION_DAYS * 86400,
                     httponly=True, samesite="lax")
    return r


@router.delete("/api/profile/devices/{did}", dependencies=[Depends(assistant)])
def profile_remove_device(did: str, request: Request, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in profiles.own_devices(prof["id"])):
        raise HTTPException(404, "no such device")
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


@router.get("/api/mfa", dependencies=[Depends(auth)])
def admin_mfa():
    return mfa.status(mfa.ADMIN)


@router.post("/api/mfa/setup", dependencies=[Depends(auth), Depends(admin_code)])
def admin_mfa_setup():
    return mfa.begin(mfa.ADMIN, "Admin")


@router.post("/api/mfa/enable", dependencies=[Depends(auth)])
async def admin_mfa_enable(request: Request):
    codes = mfa.finish(mfa.ADMIN, (await request.json()).get("code", ""))
    if not codes:
        raise HTTPException(400, "wrong code")
    guard.log("admin_mfa_on", ip=guard.client_ip(request))
    return _admin_reply(request, {"recovery": codes})


@router.post("/api/mfa/disable", dependencies=[Depends(auth), Depends(admin_code)])
def admin_mfa_disable(request: Request):
    mfa.disable(mfa.ADMIN)
    guard.log("admin_mfa_off", ip=guard.client_ip(request))
    r = _admin_reply(request, {"ok": True})
    r.delete_cookie(mfa.trust_cookie(mfa.ADMIN))
    return r


@router.post("/api/mfa/recovery", dependencies=[Depends(auth), Depends(admin_code)])
def admin_mfa_recovery(request: Request):
    guard.log("admin_mfa_recovery", ip=guard.client_ip(request))
    return {"recovery": mfa.new_recovery(mfa.ADMIN) or []}


@router.post("/api/mfa/forget", dependencies=[Depends(auth)])
def admin_mfa_forget(request: Request):
    """Every trusted browser has to enter a code again, and every other admin login ends."""
    mfa.forget_trust(mfa.ADMIN)
    guard.log("admin_mfa_forget", ip=guard.client_ip(request))
    r = _admin_reply(request, {"ok": True})
    r.delete_cookie(mfa.trust_cookie(mfa.ADMIN))
    return r


@router.get("/api/profile/mfa", dependencies=[Depends(assistant)])
def profile_mfa(prof=Depends(own_profile)):
    return dict(mfa.status(prof["id"]), allowed=bool(load_config().get("chat", {}).get("mfa", False)))


@router.post("/api/profile/mfa/setup", dependencies=[Depends(assistant)])
async def profile_mfa_setup(request: Request, prof=Depends(browser_profile)):
    if not load_config().get("chat", {}).get("mfa", False):
        raise HTTPException(403, "the second login step is turned off")
    await confirm_code(request, prof["id"], prof["name"])
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
    r.set_cookie(profiles.COOKIE, profiles._cookie_value(u), max_age=profiles.SESSION_DAYS * 86400, httponly=True, samesite="lax")
    return r


@router.post("/api/profile/mfa/disable", dependencies=[Depends(assistant)])
async def profile_mfa_disable(request: Request, prof=Depends(browser_profile)):
    await confirm_code(request, prof["id"], prof["name"])
    mfa.disable(prof["id"])
    guard.log("profile_mfa_off", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(mfa.trust_cookie(prof["id"]))
    return r


@router.post("/api/profile/mfa/recovery", dependencies=[Depends(assistant)])
async def profile_mfa_recovery(request: Request, prof=Depends(browser_profile)):
    await confirm_code(request, prof["id"], prof["name"])
    return {"recovery": mfa.new_recovery(prof["id"]) or []}


@router.get("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_memory(prof=Depends(own_profile)):
    return {"profile": prof, "facts": profiles.memory(prof["id"]), "tidy": memtidy.pending(prof["id"])}


@router.post("/api/profile/memory/tidy", dependencies=[Depends(assistant)])
async def profile_tidy(request: Request, prof=Depends(browser_profile)):
    """{"do": "check"} asks for a proposal now, "accept" carries it out, "reject" drops it."""
    do = (await request.json()).get("do")
    if do == "check":
        if not profiles.memory(prof["id"]):
            return {"tidy": None}
        try:
            return {"tidy": await memtidy.propose(prof["id"])}
        except Exception as e:
            raise HTTPException(502, f"language model not reachable: {type(e).__name__}")
    if do == "accept":
        n = memtidy.apply(prof["id"])
        guard.log("profile_memory_tidied", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"], removed=n)
        return {"removed": n, "facts": profiles.memory(prof["id"])}
    if do == "reject":
        memtidy.drop(prof["id"])
        return {"tidy": None}
    raise HTTPException(400, "do must be check, accept or reject")


@router.delete("/api/profile/memory/{fact_id}", dependencies=[Depends(assistant)])
def profile_forget(fact_id: str, prof=Depends(browser_profile)):
    return {"removed": profiles.forget(prof["id"], fact_id=fact_id)}


@router.delete("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_forget_all(prof=Depends(browser_profile)):
    return {"removed": profiles.forget(prof["id"])}


@router.get("/api/profile/convos", dependencies=[Depends(assistant)])
def profile_convos(prof=Depends(own_profile)):
    return profiles.convos(prof["id"])


CONVO_BODY = 4 * 1024 * 1024   # 60 messages of 20 000 characters


@router.put("/api/profile/convos", dependencies=[Depends(assistant)])
async def profile_save_convo(request: Request, prof=Depends(own_profile)):
    import iphone
    body = await iphone._json(request, CONVO_BODY)   # size checked while reading (also for the iPhone app)
    ha = homeassistant.get(prof["id"])
    if ha and homeassistant.needs_code(ha) and isinstance(body, dict) and isinstance(body.get("msgs"), list):
        body["msgs"] = [dict(m, content=homeassistant.redact(ha, m.get("content")))
                        if isinstance(m, dict) and m.get("role") == "user" else m for m in body["msgs"]]
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
    if dev:   # only the profile's iPhone app with "Dokumente aus der App" (app_docs), never other keys
        import iphone
        if dev.get("scope") != "app" or not iphone.docs_on(prof["id"]):
            raise HTTPException(403, "only in the profile's own login or its iPhone app")
    return documents.list_docs(prof["id"])


@router.post("/api/profile/docs", dependencies=[Depends(assistant)])
async def profile_add_doc(file: UploadFile = File(...), prof=Depends(browser_profile)):
    if not load_config().get("chat", {}).get("documents", True):
        raise HTTPException(403, "documents are turned off (Einstellungen -> Funktionen)")
    data = await file.read(documents.MAX_FILE + 1)
    try:
        return await asyncio.to_thread(wissen.add, prof["id"], file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/profile/docs/{doc_id}", dependencies=[Depends(assistant)])
def profile_delete_doc(doc_id: str, prof=Depends(browser_profile)):
    return {"removed": documents.delete(prof["id"], doc_id)}


@router.get("/api/profile/reminders", dependencies=[Depends(assistant)])
def profile_reminders(page: int = 0, push_id: str = "", prof=Depends(own_profile)):
    if page:
        # an open panel page rings by itself: push waits a moment for it, and later notes go to this browser
        push.page_open(prof["id"], push_id[:16])
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
    return {"play": profiles.take_reminder(prof["id"], rid, time.time() * 1000 + 60_000) is not None}


@router.delete("/api/profile/reminders/{rid}", dependencies=[Depends(assistant)])
def profile_reminder_done(rid: str, prof=Depends(own_profile)):
    return {"removed": profiles.remove_reminders(prof["id"], {rid})}


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
    except httpx.HTTPError as e:
        raise HTTPException(400, f"calendar not reachable: {type(e).__name__}")


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
    body = await request.json()
    try:
        item = mail.entry(body if isinstance(body, dict) else {})
        found = await asyncio.wait_for(asyncio.to_thread(mail.check, item), 40)
        return dict(mail.add(prof["id"], item), check=found)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"mail server not reachable: {type(e).__name__}")


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
async def profile_ha_code(request: Request, prof=Depends(secret_profile)):
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
    except (ValueError, httpx.HTTPError) as e:
        raise HTTPException(400, str(e) or type(e).__name__)


@router.get("/api/profile/voice", dependencies=[Depends(assistant)])
def profile_voice(prof=Depends(own_profile)):
    return {"samples": len(speakers.samples(prof["id"])), "enabled": load_config()["chat"].get("speaker_id", False)}


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


@router.post("/api/assistant/say", dependencies=[Depends(assistant)])
async def assistant_say(request: Request):
    """Speaks a short text (a due reminder) as streamed PCM events, like the chat's audio."""
    me = profiles.current(request)
    guard.limit(request, "chat", me and me["id"], not me and admin_cookie_ok(request))
    body = await request.json()
    text = str(body.get("text", "")).strip()[:6000]   # a reminder, or an answer read out again
    if not text:
        raise HTTPException(400, "text is required")
    cfg = load_config()
    who = profiles.current(request)
    pset = dict(profiles.defaults(cfg.get("chat", {}).get("defaults")), **(profiles.settings(who["id"]) if who else {}))
    req = {"input": text, "stream": True, "response_format": "pcm"}
    if who and pset.get("voice"):
        req["voice"] = pset["voice"]
    if pset.get("speed", 1.0) != 1.0:
        req["speed"] = pset["speed"]

    device = echo.device_of(request)

    async def gen():
        mine, until = None, 0.0   # another device of the house does not take this for a question (echo.py)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
            async with c.stream("POST", f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech",
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
                        echo.played(mine, until)
                        yield f"data: {json.dumps({'type': 'audio', 'audio': audio})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/api/profile/settings", dependencies=[Depends(assistant)])
def profile_settings(request: Request):
    """Conversation settings: the admin's defaults, overlaid with the profile's own (if logged in)."""
    prof = profiles.current(request)
    base = profiles.defaults(load_config().get("chat", {}).get("defaults"))
    chat = load_config().get("chat", {})
    return {"settings": dict(base, **(profiles.settings(prof["id"]) if prof else {})), "defaults": base,
            "profile": prof, "allow": {"tool_think": bool(prof and chat.get("tool_thinking", False)),
                                       "route": bool(prof and chat.get("routing", False) is True),
                                       "fix_learn": bool(prof and chat.get("learn_fixes", False) and chat.get("memory", True)),
                                       "style": bool(prof and chat.get("own_style", False)),
                                       "follow": bool(prof and chat.get("follow_up", False)),
                                       "echo": bool(prof and chat.get("no_self_echo", False)),
                                       "images": bool(prof and chat.get("images", False) is True),
                                       # "Bild in Meine Dokumente" under an answer to a picture (wissen.py)
                                       "docpics": bool(prof and chat.get("images", False) is True and wissen.on(prof["id"], "pictures"))}}


@router.put("/api/profile/settings", dependencies=[Depends(assistant)])
async def profile_save_settings(request: Request, prof=Depends(browser_profile)):
    body = await request.json()
    # what Telegram may reach (personal data, switching the home) only from the profile's own browser
    # login: a shared device with a key cannot open it up
    if isinstance(body, dict) and request.headers.get(profiles.DEVICE_HEADER) \
            and any(k in ("tg_private", "tg_ha", "tg_push") and body[k] for k in body):
        raise HTTPException(403, "only in the profile's own browser login")
    # what the model is told about the tone, too: a device key cannot change it
    if isinstance(body, dict) and request.headers.get(profiles.DEVICE_HEADER) \
            and "style" in body and body["style"] != profiles.settings(prof["id"]).get("style", ""):
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
