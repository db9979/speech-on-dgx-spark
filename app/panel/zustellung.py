"""Meldung ans gerade genutzte Gerät (plan benachrichtigung-geraet, Dominik 2026-10-20 "ok", stage 1).

push.pick sends a note to one way of the profile. Before, that was the way it used last (profiles.LAST_USED, 12 h), which
also counted a page left open in the background and never the iPhone app. With the admin switch chat.note_device on, each
device says how long ago a person last touched it, and push.pick asks here first:

    1. a device that is in use right now (input less than ACTIVE seconds ago, its signal younger than FRESH): the one
       touched last
    2. none: the phone app at once (iPhone, else Android)
    3. no phone app: push.pick as before (Begleiter, Telegram, browser)

A way the profile chose for a kind of note (push.send to=, e.g. the Dienst-Wächter) still wins. Off: push.pick as before.

The signals carry only a state, never content: the browser and the Android app (POST /api/zustellung/da with the seconds
since the last input, or "weg" when hidden), the iPhone app (the same, "0" in front, "weg" in the background) and the
Spark-Begleiter (its poll every POLL seconds with the computer's idle seconds). Kept in memory only, at most MAX
profiles; a signal older than FRESH says nothing any more.
"""
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from core import assistant, json_body, own_profile

router = APIRouter()

ACTIVE = 120        # s since the last input: the device counts as in use
FRESH = 90          # s: an older signal says nothing (pages and the iPhone say it every 60 s, the Begleiter every 30 s)
PHONES = ("app", "and")   # the fallback when no device is in use: the phone app at once
MAX = 1000          # profiles kept (in memory only)
MAX_BODY = 256
IDLE_MAX = 7 * 86400
_lock = threading.Lock()
_sig = {}           # uid -> {way: (time of the signal, time of the last input, gone, key)}
_today = {"day": "", "aktiv": 0, "handy": 0}   # notes routed today (numbers for Zustand → Live)


def seen(uid, way, idle=0, gone=False, key="", now=None):
    """A device of the profile said how long ago it was last touched (idle seconds) or that it is away (gone)."""
    now = time.time() if now is None else now
    if way not in ("app", "and", "desk", "tg", "web") or not uid:
        return
    idle = max(0, min(int(idle or 0), IDLE_MAX))
    with _lock:
        if uid not in _sig and len(_sig) >= MAX:
            _sig.pop(min(_sig, key=lambda u: max((v[0] for v in _sig[u].values()), default=0)), None)
        _sig.setdefault(uid, {})[way] = (now, now - idle, bool(gone), key if re.fullmatch(r"[0-9a-f]{16}", key or "") else "")


def in_use(uid, now=None):
    """[(way, key, time of the last input)] of the profile's devices in use right now, the one touched last first."""
    now = time.time() if now is None else now
    with _lock:
        sig = dict(_sig.get(uid, {}))
    out = [(w, k, t_in) for w, (t, t_in, gone, k) in sig.items() if not gone and now - t < FRESH and now - t_in < ACTIVE]
    return sorted(out, key=lambda x: -x[2])


def pick(uid, have, now=None):
    """(way, key, why) for a note by the rules above, None to let push.pick go on as before. have: way -> set up."""
    if not features.allowed("notedevice", uid):
        return None
    got = next(((w, k, "aktiv") for w, k, _ in in_use(uid, now) if have.get(w)), None)
    if got is None:
        got = next(((w, "", "handy") for w in PHONES if have.get(w)), None)
    if got is not None:
        day = time.strftime("%Y-%m-%d")
        with _lock:
            if _today["day"] != day:
                _today.update(day=day, aktiv=0, handy=0)
            _today[got[2]] += 1
        print(f"push: route {got[2]} {got[0]} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return got


def for_live(now=None):
    """{"on", "devices", "aktiv", "handy"}: devices in use right now and notes routed today, numbers only."""
    now = time.time() if now is None else now
    with _lock:
        uids = list(_sig)
        day = dict(_today) if _today["day"] == time.strftime("%Y-%m-%d") else {"aktiv": 0, "handy": 0}
    return {"on": features.admin_on("notedevice"), "devices": sum(len(in_use(u, now)) for u in uids),
            "aktiv": day["aktiv"], "handy": day["handy"]}


@router.post("/api/zustellung/da", dependencies=[Depends(assistant)])
async def api_da(request: Request, prof=Depends(own_profile)):
    """A page, the Android app or the iPhone app says: touched idle seconds ago, or away ("weg"). Only for the own
    profile and only a state; {"on"} tells the page whether to keep saying it."""
    guard.limit(request, "zustellung", prof["id"])
    body = await json_body(request, MAX_BODY, lenient=True)
    import android
    scope = profiles.key_scope(request)
    if scope == "app":
        way = "app"
    elif request.headers.get(profiles.DEVICE_HEADER) or request.scope.get("speech_profile"):
        raise HTTPException(403, "only pages and the apps")   # other keys (Begleiter, speakers) have their own ways
    else:
        way = "and" if android.from_app(request) else "web"
    idle = body.get("idle", 0)
    if not isinstance(idle, int) or isinstance(idle, bool):
        raise HTTPException(400, "idle is a number")
    if not features.allowed("notedevice", prof["id"]):
        return {"on": False}
    seen(prof["id"], way, idle, body.get("weg") is True, str(body.get("id") or "")[:16])
    return {"on": True}
