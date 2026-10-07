"""What a browser or device can do for itself: login, whoami and the profile's own data
(memory, conversations, documents, reminders, calendar, e-mail, Home Assistant, voice, settings)."""
import asyncio
import json
import os
import sys

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPBasicCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import documents  # noqa: E402
import guard  # noqa: E402
import push  # noqa: E402
import speakers  # noqa: E402
import calendars  # noqa: E402
import mail  # noqa: E402
import profiles  # noqa: E402
import homeassistant  # noqa: E402
from common import load_config  # noqa: E402
from core import (  # noqa: E402
    ADMIN_IDLE,
    COOKIE,
    NO_BASIC,
    _session_token,
    api_headers,
    app_version,
    assistant,
    calendar_on,
    check_password,
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
    return {"admin": is_admin(request, creds), "version": app_version(), "public": cfg.get("chat", {}).get("public", True),
            "profile": profiles.current(request), "documents": cfg.get("chat", {}).get("documents", True),
            "reminders": cfg.get("chat", {}).get("reminders", True),
            "speaker_id": cfg.get("chat", {}).get("speaker_id", False),
            "calendar": cfg.get("chat", {}).get("calendar", True),
            "homeassistant": cfg.get("chat", {}).get("homeassistant", False),
            "mail": cfg.get("chat", {}).get("mail", False),
            # what the assistant needs without the full configuration (which holds keys)
            "assistant": {"default_voice": cfg["tts"].get("default_voice"),
                          "asr_language": cfg["asr"].get("default_language"),
                          "https_port": cfg["panel"].get("https_port")}}


@router.post("/api/login")
async def login(request: Request):
    body = await request.json()
    guard.check(request)
    if not check_password(str(body.get("password", ""))):
        guard.failed(request, what="admin_login")
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "wrong password")
    guard.succeeded(request)
    guard.log("admin_login", ip=guard.client_ip(request))
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(COOKIE, _session_token(), max_age=ADMIN_IDLE, httponly=True, samesite="strict")
    r.delete_cookie(NO_BASIC)
    return r


@router.post("/api/logout")
def logout():
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(COOKIE)
    r.set_cookie(NO_BASIC, "1", max_age=365 * 86400, httponly=True, samesite="strict")
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
    guard.succeeded(request, name)
    guard.log("profile_login", ip=guard.client_ip(request), name=name.strip(), uid=value.split(".", 1)[0])
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(profiles.COOKIE, value, max_age=profiles.SESSION_DAYS * 86400, httponly=True, samesite="lax")
    return r


@router.post("/api/profile/logout")
def profile_logout():
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(profiles.COOKIE)
    return r


# The profile's own logins: its device keys (with last use), recent logins, log out everywhere.
LOGIN_EVENTS = ("profile_login", "profile_login_failed", "profile_logout_all", "profile_device_removed")


@router.get("/api/profile/security", dependencies=[Depends(assistant)])
def profile_security(prof=Depends(own_profile)):
    mine = lambda x: x.get("uid") == prof["id"] or (x.get("event") == "profile_login_failed"
                                                    and str(x.get("name", "")).strip().lower() == prof["name"].lower())
    events = [x for x in guard.read(3000) if x.get("event") in LOGIN_EVENTS and mine(x)][:8]
    return {"devices": profiles.own_devices(prof["id"]), "events": events}


@router.post("/api/profile/logout-all", dependencies=[Depends(assistant)])
def profile_logout_all(request: Request, prof=Depends(own_profile)):
    """Ends the login in every browser; this one gets a fresh login and stays signed in."""
    profiles.end_sessions(prof["id"])
    guard.log("profile_logout_all", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    u = next(u for u in profiles._load()["users"] if u["id"] == prof["id"])
    r = Response('{"ok": true}', media_type="application/json")
    if not request.headers.get(profiles.DEVICE_HEADER):
        r.set_cookie(profiles.COOKIE, profiles._cookie_value(u), max_age=profiles.SESSION_DAYS * 86400,
                     httponly=True, samesite="lax")
    return r


@router.delete("/api/profile/devices/{did}", dependencies=[Depends(assistant)])
def profile_remove_device(did: str, request: Request, prof=Depends(own_profile)):
    if not any(x["id"] == did for x in profiles.own_devices(prof["id"])):
        raise HTTPException(404, "no such device")
    profiles.delete_device(did)
    guard.log("profile_device_removed", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"], device=did)
    return {"devices": profiles.own_devices(prof["id"])}


@router.get("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_memory(prof=Depends(own_profile)):
    return {"profile": prof, "facts": profiles.memory(prof["id"])}


@router.delete("/api/profile/memory/{fact_id}", dependencies=[Depends(assistant)])
def profile_forget(fact_id: str, prof=Depends(own_profile)):
    return {"removed": profiles.forget(prof["id"], fact_id=fact_id)}


@router.delete("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_forget_all(prof=Depends(own_profile)):
    return {"removed": profiles.forget(prof["id"])}


@router.get("/api/profile/convos", dependencies=[Depends(assistant)])
def profile_convos(prof=Depends(own_profile)):
    return profiles.convos(prof["id"])


@router.put("/api/profile/convos", dependencies=[Depends(assistant)])
async def profile_save_convo(request: Request, prof=Depends(own_profile)):
    body = await request.json()
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
def profile_docs(prof=Depends(own_profile)):
    return documents.list_docs(prof["id"])


@router.post("/api/profile/docs", dependencies=[Depends(assistant)])
async def profile_add_doc(file: UploadFile = File(...), prof=Depends(own_profile)):
    if not load_config().get("chat", {}).get("documents", True):
        raise HTTPException(403, "documents are turned off (Einstellungen -> Funktionen)")
    data = await file.read(documents.MAX_FILE + 1)
    try:
        return await asyncio.to_thread(documents.add, prof["id"], file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/profile/docs/{doc_id}", dependencies=[Depends(assistant)])
def profile_delete_doc(doc_id: str, prof=Depends(own_profile)):
    return {"removed": documents.delete(prof["id"], doc_id)}


@router.get("/api/profile/reminders", dependencies=[Depends(assistant)])
def profile_reminders(prof=Depends(own_profile)):
    return profiles.reminders(prof["id"])


@router.delete("/api/profile/reminders/{rid}", dependencies=[Depends(assistant)])
def profile_reminder_done(rid: str, prof=Depends(own_profile)):
    return {"removed": profiles.remove_reminders(prof["id"], {rid})}


@router.get("/api/profile/calendar", dependencies=[Depends(assistant)])
def profile_calendar(prof=Depends(own_profile)):
    return calendars.public(prof["id"])


@router.post("/api/profile/calendar", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_add(request: Request, prof=Depends(own_profile)):
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
def profile_calendar_remove(cid: str, prof=Depends(own_profile)):
    return calendars.remove(prof["id"], cid)


@router.put("/api/profile/calendar/topics", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_topics(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    return calendars.set_topics(prof["id"], body.get("topics") if isinstance(body, dict) else [])


@router.post("/api/profile/calendar/test", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_test(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    try:
        return await calendars.test(prof["id"], user_zone(body.get("tz")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/profile/mail", dependencies=[Depends(assistant)])
def profile_mail(prof=Depends(own_profile)):
    return mail.public(prof["id"])


@router.post("/api/profile/mail", dependencies=[Depends(assistant), Depends(mail_on)])
async def profile_mail_add(request: Request, prof=Depends(own_profile)):
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
def profile_mail_remove(aid: str, prof=Depends(own_profile)):
    return mail.remove(prof["id"], aid)


@router.post("/api/profile/mail/test", dependencies=[Depends(assistant), Depends(mail_on)])
async def profile_mail_test(prof=Depends(own_profile)):
    return await asyncio.to_thread(mail.test, prof["id"])


@router.get("/api/profile/homeassistant", dependencies=[Depends(assistant)])
def profile_ha(prof=Depends(own_profile)):
    return homeassistant.public(prof["id"])


@router.put("/api/profile/homeassistant", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_save(request: Request, prof=Depends(own_profile)):
    """Stores the connection only after Home Assistant accepted the token."""
    body = await request.json()
    try:
        item = homeassistant.entry(body if isinstance(body, dict) else {}, homeassistant.get(prof["id"]))
        await homeassistant.check(item)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return homeassistant.save(prof["id"], item)


@router.delete("/api/profile/homeassistant", dependencies=[Depends(assistant)])
def profile_ha_remove(prof=Depends(own_profile)):
    return homeassistant.remove(prof["id"])


@router.put("/api/profile/homeassistant/code", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_code(request: Request, prof=Depends(own_profile)):
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
async def profile_ha_test(request: Request, prof=Depends(own_profile)):
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
async def profile_voice_add(file: UploadFile = File(...), prof=Depends(own_profile)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "recording is too large")
    try:
        n = await asyncio.to_thread(speakers.enroll, prof["id"], data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"samples": n}


@router.delete("/api/profile/voice", dependencies=[Depends(assistant)])
def profile_voice_delete(prof=Depends(own_profile)):
    speakers.forget(prof["id"])
    return {"samples": 0}


@router.post("/api/assistant/say", dependencies=[Depends(assistant)])
async def assistant_say(request: Request):
    """Speaks a short text (a due reminder) as streamed PCM events, like the chat's audio."""
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

    async def gen():
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
            async with c.stream("POST", f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech",
                                json=req, headers=api_headers()) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data:") and "speech.audio.delta" in line:
                        try:
                            yield f"data: {json.dumps({'type': 'audio', 'audio': json.loads(line[5:])['audio']})}\n\n"
                        except (ValueError, KeyError):
                            continue
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/api/profile/settings", dependencies=[Depends(assistant)])
def profile_settings(request: Request):
    """Conversation settings: the admin's defaults, overlaid with the profile's own (if logged in)."""
    prof = profiles.current(request)
    base = profiles.defaults(load_config().get("chat", {}).get("defaults"))
    return {"settings": dict(base, **(profiles.settings(prof["id"]) if prof else {})), "defaults": base,
            "profile": prof}


@router.put("/api/profile/settings", dependencies=[Depends(assistant)])
async def profile_save_settings(request: Request, prof=Depends(own_profile)):
    return {"settings": profiles.save_settings(prof["id"], await request.json())}


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
async def profile_push_add(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    try:
        push.add(prof["id"], body.get("subscription"), body.get("name", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    n = await push.send(prof["id"], "Spark", "Erinnerungen kommen jetzt auch auf dieses Gerät.", tag="hello")
    return {"ok": True, "sent": n}


@router.delete("/api/profile/push", dependencies=[Depends(assistant)])
async def profile_push_remove(request: Request, prof=Depends(own_profile)):
    return {"removed": push.remove(prof["id"], str((await request.json()).get("endpoint", "")))}
