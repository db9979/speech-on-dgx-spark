"""Ich starts with "Heute" (plan „Bedienung gesamt“ B1/B3, V01.0.286).

GET /api/profile/today gives the signed-in profile (browser or its own app) what is due today, only from
functions it may use (features.allowed): the next appointments (titles and times, at most 3, read with a
time budget), open reminders, unread messages, own documents and remembered facts. Only numbers and short
titles, never mail or message text. What is still to set up comes from onboard.py ("Los geht's",
/api/profile/setup), not from here.
"""
import asyncio
import datetime
import os
import time

from fastapi import APIRouter, Depends, Request

import features
import guard
import profiles
from core import assistant, own_profile

router = APIRouter()
CAL_BUDGET = 3.0          # seconds for the calendars; a slow server shows "nicht erreicht", the page never waits longer
CAL_CACHE = 300           # the appointments of a profile are read again after 5 minutes at the earliest
MAX_EVENTS = 3
_cal = {}                 # uid -> (time, zone name, result)


async def _events(uid, zone):
    import calendars
    hit = _cal.get(uid)
    now = time.time()
    if hit and now - hit[0] < CAL_CACHE and hit[1] == str(zone):
        return hit[2]
    start = datetime.datetime.now(zone)
    end = (start + datetime.timedelta(days=1)).replace(hour=23, minute=59)   # today and tomorrow
    try:
        r = await asyncio.wait_for(calendars.events(uid, start, end, zone), CAL_BUDGET)
    except (asyncio.TimeoutError, OSError, ValueError):
        return {"error": True, "next": []}
    if r is None:
        out = {"connected": False, "next": []}
    else:
        evs, errors = r
        out = {"connected": True, "error": bool(errors), "next": [
            {"start": int(x["start"].timestamp()), "allday": bool(x["allday"]), "title": str(x["title"])[:80]}
            for x in evs[:MAX_EVENTS]]}
    if len(_cal) > 500:
        _cal.clear()
    _cal[uid] = (now, str(zone), out)
    return out


@router.get("/api/profile/today", dependencies=[Depends(assistant)])
async def today(request: Request, tz: str = "", prof=Depends(own_profile)):
    uid = prof["id"]
    guard.limit(request, "features", uid)
    from chat import user_zone
    zone = user_zone(tz[:64])
    c = features.chat_cfg()
    s = profiles.settings(uid)
    may = lambda k: features.allowed(k, uid, c, s)   # noqa: E731
    out = {"cards": {}}
    if may("calendar"):
        out["cards"]["calendar"] = await _events(uid, zone)
    if may("reminders"):
        now = time.time() * 1000
        rem = sorted((x for x in profiles.reminders(uid) if x.get("due", 0) >= now), key=lambda x: x["due"])
        out["cards"]["reminders"] = {"count": len(rem), "next": {"text": str(rem[0]["text"])[:80], "due": int(rem[0]["due"] // 1000)} if rem else None}
    if may("messages"):
        import messages
        out["cards"]["messages"] = {"unread": len(messages.unread(uid))}
    if may("documents"):
        import documents
        has = os.path.exists(documents.db_path(uid))
        out["cards"]["documents"] = {"count": len(documents.list_docs(uid)) if has else 0,
                                     "waiting": documents.pages_waiting(uid) if has else 0}
    if may("memory"):
        out["cards"]["memory"] = {"facts": len(profiles.memory(uid))}
    return out
