"""Calendar and daily briefing per profile (guests have neither). New appointments only after the person
confirms a proposal (see "new appointments" below).

    USERS_DIR/<user id>/calendar.json  {"calendars": [{id, name, url, user, password}], "topics": [...]}

A profile can connect several calendars (up to 8). Each address is either a CalDAV server
(Nextcloud, Radicale, iCloud ...: the server address, the user's principal or one calendar) or an
iCal subscription link (.ics, webcal:// or webcals://, Google's "secret address in iCal format",
a shared iCloud calendar). iCloud's CalDAV is https://caldav.icloud.com with the Apple ID and an
app-specific password. The password never leaves the Spark again: the panel only learns whether
one is stored. Topics are a few search phrases for the briefing.
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
import vault

MAX_TOPICS = 3
MAX_CALENDARS = 8
CACHE_SECONDS = 300
_cache = {}
_lock = threading.Lock()
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# ---------------------------------------------------------------- settings
def _file(uid):
    return profiles._path(uid, "calendar.json")


def get(uid):
    """{"calendars": [{id, name, url, user, password}], "topics": [...]} (older files had one url)."""
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    cals = d.get("calendars") if isinstance(d.get("calendars"), list) else []
    if not cals and d.get("url"):
        cals = [{"id": "c1", "name": "Kalender", "url": d["url"], "user": d.get("user", ""),
                 "password": d.get("password", "")}]
    cals = [dict(x, password=vault.open_(x.get("password", ""))) for x in cals if isinstance(x, dict) and x.get("url")]
    return {"calendars": cals,
            "topics": d.get("topics", []) if isinstance(d.get("topics"), list) else []}


def public(uid):
    """What the panel may see: everything but the passwords."""
    d = get(uid)
    return {"calendars": [{"id": x["id"], "name": x.get("name", ""), "url": x["url"], "user": x.get("user", ""),
                           "has_password": bool(x.get("password"))} for x in d["calendars"]],
            "topics": d["topics"]}


def _store(uid, d):
    with _lock:
        cals = [dict(x, password=vault.seal(x.get("password", ""))) for x in d["calendars"]]
        profiles._write(_file(uid), {"calendars": cals, "topics": d["topics"], "updated": int(time.time())})
        _drop(uid)


def entry(body):
    """A checked calendar entry from the panel's form."""
    url = str(body.get("url", "")).strip()
    if not re.fullmatch(r"(https?|webcals?)://[^\s]{3,500}", url, re.I):
        raise ValueError("the calendar address must start with https://, http://, webcal:// or webcals://")
    name = str(body.get("name", "")).strip()[:60]
    if not name:
        m = re.match(r"\w+://([^/:]+)", url)
        name = m.group(1) if m else "Kalender"
    pw = body.get("password")
    return {"id": "c" + os.urandom(4).hex(), "name": name, "url": url, "user": str(body.get("user", "")).strip()[:200],
            "password": pw[:500] if isinstance(pw, str) else ""}


def add(uid, item):
    d = get(uid)
    if len(d["calendars"]) >= MAX_CALENDARS:
        raise ValueError(f"at most {MAX_CALENDARS} calendars")
    d["calendars"].append(item)
    _store(uid, d)
    return public(uid)


def remove(uid, cid):
    d = get(uid)
    d["calendars"] = [x for x in d["calendars"] if x["id"] != cid]
    _store(uid, d)
    return public(uid)


def set_topics(uid, topics):
    d = get(uid)
    d["topics"] = [str(x).strip()[:80] for x in (topics if isinstance(topics, list) else [])
                   if str(x).strip()][:MAX_TOPICS]
    _store(uid, d)
    return public(uid)


def seal_stored(uid):
    """Encrypts passwords that an older version stored in plain text."""
    try:
        with open(_file(uid)) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return
    plain = [x for x in raw.get("calendars") or [] if isinstance(x, dict) and x.get("password")
             and not str(x["password"]).startswith(vault.PREFIX)]
    if (plain or raw.get("password")) and vault.available():
        _store(uid, get(uid))


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
            if root is None:   # some servers (iCloud) refuse Depth 1 on the root or the principal
                root = await _propfind(c, u, q, 0)
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
    url = d["url"]
    auth = (d["user"], d.get("password", "")) if d.get("user") else None
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8), auth=auth, follow_redirects=True,
                                 headers={"User-Agent": "speech-on-dgx-spark"}) as c:
        if re.match(r"webcals?://", url, re.I):
            # webcal:// is a subscription link; iCloud, Google and most others serve it over https only
            rest = re.sub(r"^webcals?://", "", url, flags=re.I)
            try:
                url = "https://" + rest
                r = await c.get(url)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                url = "http://" + rest
                r = await c.get(url)
        else:
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


def _expand(texts, start, end, zone, name=""):
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
                        "location": str(ev.get("LOCATION", "") or "").strip()[:200], "calendar": name})
    uniq = {(x["start"], x["title"]): x for x in out}
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"]))


async def _one(uid, cal, start, end, zone):
    key = (uid, cal["id"], start.isoformat(), end.isoformat())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        texts = hit[1]
    else:
        texts, _ = await _fetch(cal, start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
        _cache[key] = (time.time(), texts)
    return _expand(texts, start, end, zone, cal.get("name", ""))


async def events(uid, start, end, zone):
    """(events of all the profile's calendars from start to end, sorted; [(name, error)] of the
    calendars that could not be read). None when no calendar is connected."""
    cals = get(uid)["calendars"]
    if not cals:
        return None
    res = await asyncio.gather(*(_one(uid, c, start, end, zone) for c in cals), return_exceptions=True)
    evs, errors = [], []
    for c, r in zip(cals, res):
        if isinstance(r, Exception):
            errors.append((c.get("name", ""), str(r) if isinstance(r, ValueError) else f"not reachable ({type(r).__name__})"))
        else:
            evs += r
    many = len(cals) > 1
    uniq = {}
    for x in evs:   # the same appointment in two calendars (e.g. shared ones) is read out once
        k = (x["start"], x["title"].lower())
        if k in uniq:
            if x["calendar"] and x["calendar"] not in uniq[k]["calendar"].split(", "):
                uniq[k]["calendar"] += ", " + x["calendar"]
        else:
            uniq[k] = dict(x, many=many)
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"])), errors


async def check(item, zone):
    """Reads one calendar entry before it is saved: number of calendars found, the next events."""
    now = datetime.datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=14)
    texts, n = await _fetch(item, start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
    evs = [x for x in _expand(texts, start, end, zone) if x["end"] >= now or x["allday"]]
    return {"found": n, "events": [line(x) for x in evs[:5]]}


async def test(uid, zone):
    """For the panel: the next few events of all calendars and which ones failed."""
    _drop(uid)
    now = datetime.datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    r = await events(uid, start, start + datetime.timedelta(days=14), zone)
    if r is None:
        raise ValueError("no calendar connected")
    evs, errors = r
    evs = [x for x in evs if x["end"] >= now or x["allday"]]
    return {"events": [line(x) for x in evs[:6]], "errors": [f"{n}: {e}" for n, e in errors]}


def line(x):
    s = x["start"]
    day = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.}"
    if x["allday"]:
        days = (x["end"].date() - s.date()).days
        when = f"{day} ganztägig" + (f" ({days} Tage)" if days > 1 else "")
    else:
        when = f"{day} {s:%H:%M}" + (f"–{x['end']:%H:%M}" if x["end"] > s else "")
    return f"{when}: {x['title']}" + (f" (Ort: {x['location']})" if x["location"] else "") \
        + (f" [{x['calendar']}]" if x.get("many") and x.get("calendar") else "")


# ---------------------------------------------------------------- new appointments
# The assistant proposes an appointment (pending, per profile); only when the person says yes in
# the next message does the panel itself write it to the first CalDAV calendar (iCal links are
# read only). The model never writes on its own.
PENDING_SECONDS = 15 * 60
YES = re.compile(r"(?i)^\W*(ja|jo|jap|jep|jawohl|genau|passt|richtig|stimmt|ok(ay)?|mach( das| es)?|trag (es |ihn |das )?ein|"
                 r"bitte|gerne?|klar|yes|sure|do it)\b")
NO = re.compile(r"(?i)\b(nein|nö|nee|nicht|stopp|abbrechen|lass( es)?|doch nicht|no|cancel)\b")


def _pending_file(uid):
    return profiles._path(uid, "calendar-pending.json")


def propose(uid, item):
    profiles._write(_pending_file(uid), dict(item, t=int(time.time())))


def pending(uid):
    try:
        with open(_pending_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and time.time() - d.get("t", 0) < PENDING_SECONDS else None
    except (OSError, ValueError):
        return None


def drop_pending(uid):
    try:
        os.remove(_pending_file(uid))
    except OSError:
        pass


def describe(item):
    s = datetime.datetime.fromisoformat(item["start"])
    e = datetime.datetime.fromisoformat(item["end"])
    if item.get("allday"):
        when = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.%Y} ganztägig"
    else:
        when = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.%Y} {s:%H:%M}–{e:%H:%M}"
    return f"„{item['title']}“ am {when}" + (f", Ort: {item['location']}" if item.get("location") else "") \
        + (f", Erinnerung {item['alarm']} Minuten vorher" if item.get("alarm") else "")


def ical(item, uid_text):
    cal = icalendar.Calendar()
    cal.add("prodid", "-//speech-on-dgx-spark//DE")
    cal.add("version", "2.0")
    ev = icalendar.Event()
    ev.add("uid", uid_text)
    ev.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
    ev.add("summary", item["title"])
    s, e = datetime.datetime.fromisoformat(item["start"]), datetime.datetime.fromisoformat(item["end"])
    if item.get("allday"):
        ev.add("dtstart", s.date())
        ev.add("dtend", e.date())
    else:
        ev.add("dtstart", s.astimezone(datetime.timezone.utc))
        ev.add("dtend", e.astimezone(datetime.timezone.utc))
    if item.get("location"):
        ev.add("location", item["location"])
    if item.get("alarm"):
        al = icalendar.Alarm()
        al.add("action", "DISPLAY")
        al.add("description", item["title"])
        al.add("trigger", datetime.timedelta(minutes=-int(item["alarm"])))
        ev.add_component(al)
    cal.add_component(ev)
    return cal.to_ical()


async def add_event(uid, item):
    """Writes the appointment to the first writable CalDAV calendar (the one named in item
    "calendar" when it exists). Returns the calendar's name; ValueError when none can take it."""
    wanted = str(item.get("calendar") or "").strip().lower()
    last_error = "no CalDAV calendar connected (iCal links are read only)"
    for d in get(uid)["calendars"]:
        if re.match(r"webcals?://", d["url"], re.I) or re.search(r"\.ics(\?|$)", d["url"], re.I):
            continue
        auth = (d["user"], d.get("password", "")) if d.get("user") else None
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8), auth=auth, follow_redirects=True,
                                     headers={"User-Agent": "speech-on-dgx-spark"}) as c:
            try:
                cals = await _calendars(c, d["url"])
            except Exception as e:
                last_error = str(e)
                continue
            if not cals:
                continue
            pick = next((x for x in cals if wanted and wanted in (x[1] or "").lower()), None) or cals[0]
            uid_text = f"{os.urandom(8).hex()}@speech-spark"
            url = pick[0].rstrip("/") + f"/{uid_text.split('@')[0]}.ics"
            r = await c.put(url, content=ical(item, uid_text),
                            headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
            if r.status_code in (200, 201, 204):
                _drop(uid)
                return pick[1] or d.get("name", "Kalender")
            last_error = f"the calendar server answered {r.status_code}"
    raise ValueError(last_error)
