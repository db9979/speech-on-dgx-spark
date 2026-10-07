"""Calendar and daily briefing per profile (read only; guests have neither).

    USERS_DIR/<user id>/calendar.json  {"url", "user", "password", "topics": [...], "updated"}

The address is either a CalDAV server (Nextcloud, Radicale, iCloud with an app password, ...:
the server address, the user's principal or one calendar) or an iCal subscription link (.ics,
webcal://, Google's "secret address in iCal format"). The password never leaves the Spark again:
the panel only learns whether one is stored. Topics are a few search phrases for the briefing.
"""
import asyncio
import datetime
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx
import icalendar
import recurring_ical_events

import profiles

MAX_TOPICS = 3
CACHE_SECONDS = 300
_cache = {}
_lock = threading.Lock()
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# ---------------------------------------------------------------- settings
def _file(uid):
    return profiles._path(uid, "calendar.json")


def get(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def public(uid):
    """What the panel may see: everything but the password."""
    d = get(uid)
    return {"url": d.get("url", ""), "user": d.get("user", ""), "has_password": bool(d.get("password")),
            "topics": d.get("topics", [])}


def save(uid, body):
    old = get(uid)
    url = str(body.get("url", "")).strip()
    if url and not re.fullmatch(r"(https?|webcals?)://[^\s]{3,500}", url, re.I):
        raise ValueError("the calendar address must start with https://, http:// or webcal://")
    user = str(body.get("user", "")).strip()[:200]
    pw = body.get("password")
    if not isinstance(pw, str) or not pw:          # empty = keep the stored one
        pw = old.get("password", "") if url and url == old.get("url") and user == old.get("user") else ""
    topics = body.get("topics", old.get("topics", []))
    topics = [str(x).strip()[:80] for x in (topics if isinstance(topics, list) else []) if str(x).strip()][:MAX_TOPICS]
    with _lock:
        profiles._write(_file(uid), {"url": url, "user": user, "password": pw[:500], "topics": topics,
                                     "updated": int(time.time())})
        _drop(uid)
    return public(uid)


def forget(uid):
    with _lock:
        try:
            os.remove(_file(uid))
        except OSError:
            pass
        _drop(uid)


def _drop(uid):
    for k in [k for k in _cache if k[0] == uid]:
        _cache.pop(k, None)


# ---------------------------------------------------------------- fetching
def _xml(text):
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _href(base, el):
    return urljoin(base, el.text.strip()) if el is not None and el.text else None


async def _propfind(c, url, body, depth):
    r = await c.request("PROPFIND", url, content=body, headers={"Depth": str(depth), "Content-Type": "application/xml"})
    if r.status_code == 401:
        raise ValueError("the calendar server rejects the user name or password (401)")
    if r.status_code != 207:
        return None
    return _xml(r.content)


async def _calendars(c, url):
    """[(calendar url, name)] reachable from the address: a calendar, a principal, a home or the server."""
    q = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
         '<d:resourcetype/><d:displayname/><d:current-user-principal/><c:calendar-home-set/>'
         '<c:supported-calendar-component-set/></d:prop></d:propfind>')
    seen, todo, out = set(), [url], []
    for _ in range(4):   # address -> principal -> calendar home -> calendars
        nxt = []
        for u in todo:
            if u in seen:
                continue
            seen.add(u)
            root = await _propfind(c, u, q, 1)
            if root is None and u == url:
                root = await _propfind(c, urljoin(u, "/.well-known/caldav"), q, 0)
            if root is None:
                continue
            for resp in root.findall("d:response", NS):
                href = _href(u, resp.find("d:href", NS))
                prop = resp.find("d:propstat/d:prop", NS)
                if prop is None or not href:
                    continue
                comps = [x.get("name") for x in prop.findall("c:supported-calendar-component-set/c:comp", NS)]
                if prop.find("d:resourcetype/c:calendar", NS) is not None and (not comps or "VEVENT" in comps):
                    name = (prop.findtext("d:displayname", "", NS) or "").strip()
                    if href not in [x[0] for x in out]:
                        out.append((href, name))
                    continue
                for tag in ("c:calendar-home-set/d:href", "d:current-user-principal/d:href"):
                    h = _href(u, prop.find(tag, NS))
                    if h and h not in seen:
                        nxt.append(h)
        if out or not nxt:
            break
        todo = nxt
    return out


async def _report(c, cal, start, end):
    fmt = "%Y%m%dT%H%M%SZ"
    q = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
         '<d:prop><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
         f'<c:time-range start="{start.strftime(fmt)}" end="{end.strftime(fmt)}"/>'
         '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    r = await c.request("REPORT", cal, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    if r.status_code != 207:
        raise ValueError(f"the calendar server answered {r.status_code}")
    root = _xml(r.content)
    return [x.text for x in (root.iter("{urn:ietf:params:xml:ns:caldav}calendar-data") if root is not None else [])
            if x.text and "BEGIN:VCALENDAR" in x.text]


async def _fetch(d, start, end):
    """iCal texts of all events overlapping [start, end) (UTC datetimes); number of calendars."""
    url = re.sub(r"^webcal", "http", d["url"], flags=re.I)
    auth = (d["user"], d.get("password", "")) if d.get("user") else None
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8), auth=auth, follow_redirects=True,
                                 headers={"User-Agent": "speech-on-dgx-spark"}) as c:
        r = await c.get(url)
        if r.status_code == 401:
            raise ValueError("the calendar server rejects the user name or password (401)")
        if r.status_code == 200 and r.content[:4096].lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"BEGIN:VCALENDAR"):
            if len(r.content) > 20 * 1024 * 1024:
                raise ValueError("the calendar file is larger than 20 MB")
            return [r.text], 1
        cals = await _calendars(c, str(r.url) if r.status_code == 200 else url)
        if not cals:
            raise ValueError("no calendar found at this address (CalDAV server or iCal link expected)")
        texts = []
        for part in await asyncio.gather(*(_report(c, u, start, end) for u, _ in cals[:20]), return_exceptions=True):
            if isinstance(part, Exception):
                if len(cals) == 1:
                    raise part
                continue
            texts += part
        return texts, len(cals)


def _expand(texts, start, end, zone):
    out = []
    for text in texts:
        try:
            cal = icalendar.Calendar.from_ical(text)
            items = recurring_ical_events.of(cal).between(start, end)
        except Exception:
            continue
        for ev in items:
            if ev.name != "VEVENT" or str(ev.get("STATUS", "")).upper() == "CANCELLED":
                continue
            s, e = ev.get("DTSTART"), ev.get("DTEND")
            if s is None:
                continue
            s = s.dt
            e = e.dt if e is not None else s
            allday = not isinstance(s, datetime.datetime)
            if allday:
                s = datetime.datetime.combine(s, datetime.time(), zone)
                e = datetime.datetime.combine(e if not isinstance(e, datetime.datetime) else e.date(), datetime.time(), zone)
            else:
                s = (s if s.tzinfo else s.replace(tzinfo=zone)).astimezone(zone)
                e = (e if isinstance(e, datetime.datetime) and e.tzinfo else s).astimezone(zone) \
                    if isinstance(e, datetime.datetime) else s
            out.append({"start": s, "end": e, "allday": allday,
                        "title": str(ev.get("SUMMARY", "") or "(ohne Titel)").strip()[:200],
                        "location": str(ev.get("LOCATION", "") or "").strip()[:200]})
    uniq = {(x["start"], x["title"]): x for x in out}
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"]))


async def events(uid, start, end, zone):
    """Events of the profile's calendar from start to end (aware datetimes), sorted."""
    d = get(uid)
    if not d.get("url"):
        return None
    key = (uid, start.isoformat(), end.isoformat())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        texts = hit[1]
    else:
        texts, _ = await _fetch(d, start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
        _cache[key] = (time.time(), texts)
    return _expand(texts, start, end, zone)


async def test(uid, zone):
    """For the panel: number of calendars and the next few events."""
    d = get(uid)
    if not d.get("url"):
        raise ValueError("no calendar address saved")
    now = datetime.datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=14)
    texts, n = await _fetch(d, start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
    _drop(uid)
    evs = [x for x in _expand(texts, start, end, zone) if x["end"] >= now or x["allday"]]
    return {"calendars": n, "events": [line(x) for x in evs[:5]]}


def line(x):
    s = x["start"]
    day = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.}"
    if x["allday"]:
        days = (x["end"].date() - s.date()).days
        when = f"{day} ganztägig" + (f" ({days} Tage)" if days > 1 else "")
    else:
        when = f"{day} {s:%H:%M}" + (f"–{x['end']:%H:%M}" if x["end"] > s else "")
    return f"{when}: {x['title']}" + (f" (Ort: {x['location']})" if x["location"] else "")
