"""Spark updates from the iPhone app: a notice when a new tested version is ready, and starting it.

Off until the admin switches on chat.iphone_update. Who may get the notice ("notify") or start the update
("start") is set per profile by the admin only (Profile und Geräte, with the admin's code when the second
step is on); a profile cannot give itself these rights, and "start" needs the profile's own second login
step. Starting from the app needs the app's own key, a fresh 6-digit code from the profile's authenticator
app (each code once) and at most one start per START_GAP. The update is the same as in the panel:
backup, then update.sh, which installs only versions whose GitHub tests passed. The app cannot pick a
version, and the language model has no tool for any of this.

    STATE/iphone-update.json  {"rights": {uid: {"notify": bool, "start": bool}}, "told": {uid: version},
                               "last": time of the last start from the app}
"""
import asyncio
import datetime
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import mfa
import profiles
from common import load_config
from core import CODE_HEADER, admin_code, assistant, auth, confirm_code, own_profile

router = APIRouter()
_lock = threading.Lock()
_start_lock = asyncio.Lock()     # one start at a time (the checks below await)

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
START_GAP = 600            # seconds between two starts from the app (all profiles together)
CHECK_EVERY = 600          # the notice looks for a new version this often
MAX_BODY = 1024


def _file():
    return os.path.join(STATE, "iphone-update.json")


def _read():
    try:
        with open(_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = _file() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, _file())


def admin_on():
    return bool(load_config().get("chat", {}).get("iphone_update", False))


def rights(uid):
    r = _read().get("rights", {}).get(uid) or {}
    return {"notify": bool(r.get("notify")), "start": bool(r.get("start")) and mfa.enabled(uid)}


def set_rights(uid, notify, start):
    with _lock:
        d = _read()
        all_ = d.setdefault("rights", {})
        if notify or start:
            all_[uid] = {"notify": bool(notify), "start": bool(start)}
        else:
            all_.pop(uid, None)
        _write(d)


def _app_key(request):
    dev = profiles.device(request)
    if not dev or dev.get("scope") != "app":
        raise HTTPException(403, "only the iPhone app")
    return dev


def for_app(uid):
    """What hello tells the app: whether it shows the version page and the start button."""
    import iphone
    if not admin_on() or not iphone.allowed(uid):
        return {"notify": False, "start": False}
    return rights(uid)


# ---------------------------------------------------------------- admin: who may
@router.get("/api/admin/iphone-update", dependencies=[Depends(auth)])
def admin_get():
    d = _read().get("rights", {})
    return {"on": admin_on(), "profiles": [
        {"id": u, "name": (profiles.by_id(u) or {}).get("name", "?"), "mfa": mfa.enabled(u),
         "notify": bool((d.get(u) or {}).get("notify")), "start": bool((d.get(u) or {}).get("start"))}
        for u in profiles.user_ids()]}


@router.put("/api/admin/iphone-update/{uid}", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_set(uid: str, request: Request):
    if uid not in profiles.user_ids():
        raise HTTPException(404, "no such profile")
    body = await request.json()
    notify, start = body.get("notify"), body.get("start")
    if not isinstance(notify, bool) or not isinstance(start, bool):
        raise HTTPException(400, "notify and start must be true or false")
    if start and not mfa.enabled(uid):
        raise HTTPException(409, "Dieses Profil braucht zuerst den zweiten Anmeldeschritt (Ich → Sicherheit).")
    set_rights(uid, notify, start)
    guard.log("iphone_update_rights", ip=guard.client_ip(request), uid=uid,
              detail=f"notify={notify} start={start}")
    return rights(uid)


# ---------------------------------------------------------------- the app
def _changes(remote):
    return [c["title"][:160] for c in (remote.get("commits") or [])][-30:][::-1]


@router.get("/api/iphone/update", dependencies=[Depends(assistant)])
async def app_state(request: Request, prof=Depends(own_profile)):
    _app_key(request)
    guard.limit(request, "chat", prof["id"], False)
    r = for_app(prof["id"])
    if not (r["notify"] or r["start"]):
        raise HTTPException(403, "Spark updates are not allowed for this profile")
    import update
    from core import app_version
    remote = await update.remote_state()
    running = await asyncio.to_thread(update.update_running)
    p = update.update_progress() or {}
    newer = bool(remote.get("latest")) and remote.get("behind") not in (0, None)
    return {"installed": app_version(), "latest": remote.get("version") if newer else None,
            "newer": newer, "behind": remote.get("behind") if newer else 0, "changes": _changes(remote) if newer else [],
            "error": remote.get("error"), "running": running,
            "progress": {k: p.get(k) for k in ("percent", "text", "done", "ok", "version")} if p else None,
            "start": r["start"], "wait": _wait_left()}


def _wait_left(now=None):
    now = time.time() if now is None else now
    return max(0, int(START_GAP - (now - float(_read().get("last", 0)))))


@router.post("/api/iphone/update", dependencies=[Depends(assistant)])
async def app_start(request: Request, prof=Depends(own_profile)):
    dev = _app_key(request)
    uid = prof["id"]
    if not for_app(uid)["start"]:
        raise HTTPException(403, "starting the update is not allowed for this profile")
    guard.limit(request, "chat", uid, False)
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise HTTPException(413, "too large")
    # a fresh code from the authenticator app, always (rights() already needs the second step on)
    if not re.fullmatch(r"\d{6}", request.headers.get(CODE_HEADER, "").strip()):
        raise HTTPException(428, "code required")
    await confirm_code(request, uid, prof["name"])
    import update
    async with _start_lock:
        if _wait_left():
            raise HTTPException(429, "Das Update wurde gerade erst gestartet. Bitte etwas warten.")
        if await asyncio.to_thread(update.update_running):
            raise HTTPException(409, "Ein Update läuft schon.")
        remote = await update.remote_state(force=True)
        if not remote.get("latest") or remote.get("behind") in (0, None):
            raise HTTPException(409, "Es gibt keine neuere geprüfte Version.")
        with _lock:
            d = _read()
            d["last"] = time.time()
            _write(d)
    version = remote.get("version") or remote["latest"][:7]
    await asyncio.to_thread(update._backup_first, "before-update")
    update._start()
    guard.log("update_from_app", ip=guard.client_ip(request), uid=uid,
              detail=f"{dev.get('name', '')[:40]} -> {version}")
    print("update: started from the iPhone app by", prof["name"], flush=True)
    await _tell_others(uid, prof["name"], version)
    return {"started": True, "version": version}


async def _tell_others(uid, name, version):
    import apns
    for u, r in _read().get("rights", {}).items():
        if u != uid and r.get("notify") and apns.on_for(u):
            await apns.send(u, "Spark-Update", f"{name} hat das Update auf {version} gestartet.", tag="update")


# ---------------------------------------------------------------- the notice
_checked = [0.0]


def _quiet(uid, now):
    import proactive
    p = profiles.settings(uid)
    return proactive.quiet(p, datetime.datetime.fromtimestamp(now, proactive._zone(p)))


async def due_once(now=None):
    """Every CHECK_EVERY: a new tested version that nobody was told about yet goes to the profiles with
    "notify" (once per version; during a profile's quiet time it waits for the next check)."""
    now = time.time() if now is None else now
    if now - _checked[0] < CHECK_EVERY or not admin_on():
        return 0
    _checked[0] = now
    who = [u for u, r in _read().get("rights", {}).items() if r.get("notify") and u in profiles.user_ids()]
    if not who:
        return 0
    import apns
    import iphone
    import update
    remote = await update.remote_state()
    if not remote.get("latest") or remote.get("behind") in (0, None):
        return 0
    version = remote.get("version") or remote["latest"][:7]
    d = _read()
    told = d.setdefault("told", {})
    sent = 0
    n = len(remote.get("commits") or [])
    text = f"{version} ist geprüft und bereit" + (f" ({n} Änderungen)." if n > 0 else ".") + \
        " In der App unter Einstellungen → Spark-Version."
    for u in who:
        if told.get(u) == version or not iphone.allowed(u) or not apns.on_for(u) or _quiet(u, now):
            continue
        if await apns.send(u, "Neue Spark-Version", text, tag="update", now=now):
            told[u] = version
            sent += 1
    if sent:
        with _lock:
            fresh = _read()
            fresh.setdefault("told", {}).update(told)
            _write(fresh)
    return sent
