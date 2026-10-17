"""„Apps merken sich den letzten Stand“ (Dominik 2026-10-17, plan app-zwischenspeicher/entwurf.png).

The iPhone app and the Android app keep the last state of a few pages for their profile on the phone (the
conversations, the chats, the own settings and functions, the numbers on the tiles of „Meine Sachen“: only how many, no names, no files) and
show it at once on the next start, with a small note „Stand 16:05 · wird aktualisiert …“, until the Spark answers.
The Spark keeps nothing for this; it only says whether the app on this device may keep (keep), and the apps delete
what they kept when it says no, on signing out and when another profile or another Spark comes. Never kept: keys,
codes, the admin areas, anything of a guest (guests have no profile, so keep is always False for them).

An app also tells the Spark when a page took longer than SLOW_MS until its data was there (POST /api/app/langsam):
a fixed page word and the milliseconds, one log line under Zustand → Logs (area Apps), never what was on the page.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from core import assistant, json_body, own_profile

router = APIRouter()

# the pages an app may name (the iPhone app's lists, the Android app's page start); anything else is refused
PAGES = ("start", "verlauf", "chats", "chat", "einstellungen", "funktionen", "sachen", "seite")
SLOW_MS = 2000            # from here an app reports a page (the same number in Merken.swift and merken.js)
MAX_MS = 600_000
BODY = 256
ANDROID_UA = "SparkAndroid/"


def device_kind(request):
    """"iphone" for the iPhone app's key, "android" for the Android app's page, else "" (a browser, another device)."""
    dev = profiles.device(request)
    if dev and dev.get("scope") == "app":
        return "iphone"
    if not request.headers.get(profiles.DEVICE_HEADER) and ANDROID_UA in request.headers.get("user-agent", ""):
        return "android"
    return ""


def keep(prof, request):
    """The app on this device may keep the profile's last state: an app, a profile (never a guest) and the function
    released for it. A plain browser never (its copy for reading offline is verlauf.offline_here)."""
    return bool(prof and request is not None and device_kind(request) and features.allowed("appmerken", prof["id"]))


@router.post("/api/app/langsam", dependencies=[Depends(assistant)])
async def slow(request: Request, prof=Depends(own_profile)):
    """An app's page needed long until its data was there: one log line with fixed words and numbers."""
    guard.limit(request, "applangsam", prof["id"])
    kind = device_kind(request)
    body = await json_body(request, BODY)
    page, ms = body.get("seite"), body.get("ms")
    if not kind:
        print("app: langsam abgelehnt kein-app", profiles.log_name(prof), flush=True)
        raise HTTPException(403, "only the apps")
    if page not in PAGES or not isinstance(ms, int) or isinstance(ms, bool) or not SLOW_MS <= ms <= MAX_MS:
        print("app: langsam abgelehnt falsch", kind, profiles.log_name(prof), flush=True)
        raise HTTPException(400, "unknown page or time")
    print("app: langsam", page, ms, "ms", kind, profiles.log_name(prof), flush=True)
    return {"ok": True}
