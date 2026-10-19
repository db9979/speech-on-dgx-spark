"""Calendar and daily briefing per profile (guests have neither). New appointments only after the person
confirms a proposal (see "new appointments" below).

    USERS_DIR/<user id>/calendar.json  {"calendars": [{id, name, url, user, password}], "topics": [...]}

A profile can connect several calendars (up to 8). Each address is either a CalDAV server
(Nextcloud, Radicale, iCloud ...: the server address, the user's principal or one calendar) or an
iCal subscription link (.ics, webcal:// or webcals://, Google's "secret address in iCal format",
a shared iCloud calendar). iCloud's CalDAV is https://caldav.icloud.com with the Apple ID and an
app-specific password. The password never leaves the Spark again: the panel only learns whether
one is stored. Topics are a few search phrases for the briefing.

Sharing (Dominik 2026-10-18 „1a 2a“, function Kalender teilen, off): the owner shares one connected calendar with
another profile, "see" or "add" (see and enter), kept in the owner's file as {"shares": {profile id: level}}. The
other profile reads it with the owner's access (the password never leaves the owner's file), on the page Kalender
and through the assistant, named "<owner> · <calendar>". A private appointment (CLASS PRIVATE or CONFIDENTIAL)
shows there only as „belegt“ with its time, never title or place. "add" lets the other profile's assistant propose
a new appointment there, saved only after its yes; changing and deleting stay with the owner. Guests never.
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

import hintergrund
import netguard
import notaus
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
    """What the panel may see: everything but the passwords. With Kalender teilen also with whom each calendar is
    shared, the other profiles to choose from and what others share with this profile (names only, never their
    addresses)."""
    d = get(uid)
    out = {"calendars": [{"id": x["id"], "name": x.get("name", ""), "url": x["url"], "user": x.get("user", ""),
                          "has_password": bool(x.get("password"))} for x in d["calendars"]],
           "topics": d["topics"]}
    if _sharing(uid):
        have = set(profiles.user_ids())
        for x, c in zip(out["calendars"], d["calendars"]):
            x["shares"] = {k: v for k, v in (c.get("shares") or {}).items() if k in have and v in LEVELS}
        out["people"] = [{"id": p["id"], "name": p["name"]} for p in profiles.names() if p["id"] != uid]
        out["shared"] = [{"owner": n, "name": c.get("name", ""), "level": lvl} for _, n, c, lvl in shared_to(uid)]
    return out


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


LEVELS = ("see", "add")
BUSY = "belegt"


def _sharing(uid):
    import features   # late: features reads the profiles' settings
    return bool(uid) and features.allowed("calshare", uid)


def set_share(uid, cid, to, level):
    """Shares the calendar cid of uid with the profile to ("see", "add"), or takes it back (level "")."""
    if level not in LEVELS + ("",):
        raise ValueError("level must be see, add or empty")
    if to == uid or to not in profiles.user_ids():
        raise ValueError("no such other profile")
    d = get(uid)
    cal = next((x for x in d["calendars"] if x["id"] == cid), None)
    if cal is None:
        raise KeyError(cid)
    sh = {k: v for k, v in (cal.get("shares") or {}).items() if v in LEVELS and k != to}
    if level:
        sh[to] = level
    cal["shares"] = sh
    _store(uid, d)
    _drop_shared(cid)
    _live[0] = 0.0
    return public(uid)


def shared_to(uid):
    """[(owner id, owner name, calendar entry, level)] of the calendars other profiles share with uid; only while
    the function is allowed for both."""
    if not _sharing(uid):
        return []
    out = []
    for p in profiles.names():
        if p["id"] == uid or not os.path.exists(_file(p["id"])):
            continue
        for c in get(p["id"])["calendars"]:
            lvl = (c.get("shares") or {}).get(uid)
            if lvl in LEVELS and _sharing(p["id"]):
                out.append((p["id"], p["name"], c, lvl))
    return out


_live = [0.0, {}]
_page = {"day": "", "n": 0}   # changes made on the page Kalender today (Live: a number, never which)


def page_done():
    day = time.strftime("%Y-%m-%d")
    if _page["day"] != day:
        _page.update(day=day, n=0)
    _page["n"] += 1


def page_today():
    return _page["n"] if _page["day"] == time.strftime("%Y-%m-%d") else 0


def for_live(now=None):
    """Live and Monitoring: how many shares there are, between how many profiles, in numbers only (never a name,
    a calendar or an appointment); counted at most every 30 s."""
    import features
    now = time.time() if now is None else now
    if not features.admin_on("calshare"):
        return {"on": False}
    if 0 <= now - _live[0] < 30:
        return _live[1]
    n, owners = 0, 0
    for u in profiles.user_ids():
        if not os.path.exists(_file(u)):
            continue
        k = sum(len([v for v in (c.get("shares") or {}).values() if v in LEVELS]) for c in get(u)["calendars"])
        n, owners = n + k, owners + (1 if k else 0)
    _live[:] = [now, {"on": True, "shares": n, "owners": owners}]
    return _live[1]


def shared_name(owner, cal):
    return f"{owner} · {cal.get('name') or 'Kalender'}"


def reading(uid):
    """get(uid) plus the calendars shared with uid, each marked with owner, level and its shown name: what the
    page and the assistant read. Writing and the briefing use get(uid) (only the own calendars)."""
    d = get(uid)
    d["calendars"] = d["calendars"] + [dict(c, name=shared_name(n, c), owner=o, level=lvl)
                                       for o, n, c, lvl in shared_to(uid)]
    return d


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


def _drop_shared(cid):
    for k in [k for k in _cache if k[1] == cid]:
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


async def _calendars(c, url, comp="VEVENT"):
    """[(calendar url, name)] reachable from the address: a calendar, a principal, a home or the server.
    comp: what the collection must hold, VEVENT (appointments) or VTODO (tasks, see tasks.py)."""
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
                if prop.find("d:resourcetype/c:calendar", NS) is not None and (not comps or comp in comps):
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
    web = re.sub(r"^webcals?://", "https://", url, flags=re.I)
    async with netguard.client(netguard.USER, origin=web, timeout=httpx.Timeout(20, connect=8), auth=auth,
                               follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"},
                               seen=hintergrund.tracker("cal", d.get("id")) if d.get("id") else None) as c:
        if re.match(r"webcals?://", url, re.I):
            # webcal:// is a subscription link; iCloud, Google and most others serve it over https only
            # (plain http only for a link without login data: a password never goes unencrypted)
            rest = re.sub(r"^webcals?://", "", url, flags=re.I)
            try:
                url = "https://" + rest
                r = await c.get(url)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if auth:
                    raise
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


# Recurrence rules that repeat faster than hourly, or hourly since long ago, cost seconds to minutes to
# expand: one such invitation would stall every check. They are left out (no real appointment needs them).
FAST = {"SECONDLY", "MINUTELY"}
MAX_EVENTS = 2000


def _tame(cal, start):
    for comp in list(cal.subcomponents):
        rule = comp.get("RRULE")
        if rule is None:
            continue
        rules = rule if isinstance(rule, list) else [rule]
        freqs = {str(f).upper() for r in rules for f in (r.get("FREQ") or [])}
        if freqs & FAST:
            cal.subcomponents.remove(comp)
            continue
        if "HOURLY" in freqs:
            s = comp.get("DTSTART")
            s = s.dt if s is not None else None
            if not isinstance(s, datetime.datetime) or abs((start - (s if s.tzinfo else s.replace(tzinfo=start.tzinfo))).days) > 31:
                cal.subcomponents.remove(comp)
    return cal


def _expand(texts, start, end, zone, name=""):
    out = []
    for text in texts:
        try:
            cal = _tame(icalendar.Calendar.from_ical(text), start)
            # every occurrence carries a RECURRENCE-ID after expanding: a repeating one is known by its master
            rep = {str(v.get("UID", "")) for v in cal.walk("VEVENT")
                   if v.get("RRULE") is not None or v.get("RDATE") is not None or v.get("RECURRENCE-ID") is not None}
            items = recurring_ical_events.of(cal).between(start, end)
        except Exception:
            continue
        for ev in items[:MAX_EVENTS]:
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
                        "location": str(ev.get("LOCATION", "") or "").strip()[:200], "calendar": name,
                        "private": str(ev.get("CLASS", "") or "").upper() in ("PRIVATE", "CONFIDENTIAL"),
                        "repeat": str(ev.get("UID", "")) in rep})
    uniq = {(x["start"], x["title"]): x for x in out}
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"]))


async def _one(uid, cal, start, end, zone):
    # fetched for whole days (so the check every minute hits the cache instead of adding an entry
    # and asking the server each time); expanded for the exact period asked
    utc = datetime.timezone.utc
    day0 = start.astimezone(utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = end.astimezone(utc).replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    key = (uid, cal["id"], day0.isoformat(), day1.isoformat())
    now = time.time()
    for k in [k for k, v in _cache.items() if now - v[0] >= CACHE_SECONDS]:
        _cache.pop(k, None)
    # a longer period fetched before (e.g. the next days, vorab.py) holds every event of a shorter one in it
    hit = _cache.get(key) or next((v for k, v in _cache.items() if k[:2] == key[:2] and k[2] <= key[2] and k[3] >= key[3]), None)
    if hit:
        texts = hit[1]
    else:
        texts, _ = await _fetch(cal, day0, day1)
        _cache[key] = (now, texts)
    # expanding runs outside the event loop, so a heavy calendar never stalls the panel
    evs = await asyncio.to_thread(_expand, texts, start, end, zone, cal.get("name", ""))
    if cal.get("owner"):   # shared by another profile (2a): a private appointment is only „belegt“ with its time
        evs = [dict(x, title=BUSY, location="") if x["private"] else x for x in evs]
    return evs


async def events(uid, start, end, zone, shared=False):
    """(events of all the profile's calendars from start to end, sorted; [(name, error)] of the
    calendars that could not be read). None when no calendar is connected. shared: also the calendars other
    profiles share with it (the page and the assistant's calendar_events; never the briefing or Von selbst)."""
    cals = (reading(uid) if shared else get(uid))["calendars"]
    if not cals:
        return None
    # a shared calendar is cached under its owner (the same fetch serves the owner and everyone it is shared with)
    res = await asyncio.gather(*(_one(c.get("owner") or uid, c, start, end, zone) for c in cals), return_exceptions=True)
    evs, errors = [], []
    for c, r in zip(cals, res):
        if isinstance(r, Exception):
            errors.append((c.get("name", ""), str(r) if isinstance(r, ValueError) else f"not reachable ({type(r).__name__})"))
        else:
            evs += r
    many = len(cals) > 1 or any(c.get("owner") for c in cals)   # a shared one always says whose it is
    uniq = {}
    for x in evs:   # the same appointment in two calendars (e.g. shared ones) is read out once
        k = (x["start"], x["title"].lower())
        if k in uniq:
            if x["calendar"] and x["calendar"] not in uniq[k]["calendar"].split(", "):
                uniq[k]["calendar"] += ", " + x["calendar"]
        else:
            uniq[k] = dict(x, many=many)
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"])), errors


# ---------------------------------------------------------------- the page Kalender (kalender.js)
VIEW_DAYS = 42            # the page asks for at most six weeks at a time (a month with its weeks around it)
VIEW_BUDGET = 8.0         # seconds; a slow calendar shows "nicht erreicht" on the page, the page never waits longer
VIEW_MAX = 600            # appointments per answer


async def view(uid, day, days, zone):
    """The appointments of `days` days from the date `day` for the page Kalender, each with the place of its
    calendar in the profile's list (the colour on the page), and the names of the calendars that could not be
    read. Only titles, times and places as the calendars give them; nothing is kept beyond the cache."""
    days = max(1, min(int(days), VIEW_DAYS))
    t0 = datetime.datetime.combine(day, datetime.time(), zone)
    t1 = t0 + datetime.timedelta(days=days)
    cals = reading(uid)["calendars"]
    names = [c.get("name", "") for c in cals]
    if not names:
        return {"connected": False, "calendars": [], "events": [], "errors": []}
    shared = [i for i, c in enumerate(cals) if c.get("owner")]
    # the page may change an appointment of an own CalDAV calendar (never an iCal link, never a shared one) and add
    # to those and to a shared one with "add"
    own = {d["id"] for d in _writable(uid)}
    edit = [i for i, c in enumerate(cals) if not c.get("owner") and c["id"] in own]
    add = edit + [i for i, c in enumerate(cals) if c.get("owner") and c.get("level") == "add"
                  and not re.match(r"webcals?://", c["url"], re.I) and not re.search(r"\.ics(\?|$)", c["url"], re.I)]
    try:
        r = await asyncio.wait_for(events(uid, t0, t1, zone, shared=True), VIEW_BUDGET)
    except asyncio.TimeoutError:
        return {"connected": True, "calendars": names, "shared": shared, "edit": edit, "add": add, "events": [],
                "errors": names, "slow": True}
    evs, errors = r if r else ([], [])
    out = []
    for x in evs[:VIEW_MAX]:
        first = (x.get("calendar") or "").split(", ")[0]
        i = names.index(first) if first in names else 0
        out.append({"start": int(x["start"].timestamp()), "end": int(x["end"].timestamp()), "allday": bool(x["allday"]),
                    "title": x["title"], "location": x["location"], "cal": i,
                    "edit": i in edit and not x.get("repeat")})
    return {"connected": True, "calendars": names, "shared": shared, "edit": edit, "add": add, "events": out,
            "errors": [n for n, _ in errors]}


# ---------------------------------------------------------------- the page Kalender changes (stage 2)
# A button on the page is the person's own yes: no proposal and no second question, but the same checks as the
# assistant's way (the Notaus, only own CalDAV calendars, If-Match against a change meanwhile, never a repeating one).
def page_item(body, zone):
    """A checked appointment from the page's form: title, local start and end ('YYYY-MM-DDTHH:MM', or dates for
    all day, end exclusive), place, calendar (its shown name, empty: the first own one)."""
    title = str(body.get("title") or "").strip()[:200]
    if not title:
        raise ValueError("a title is needed")
    allday = bool(body.get("allday"))
    try:
        if allday:
            s = datetime.datetime.combine(datetime.date.fromisoformat(str(body.get("start") or "")[:10]), datetime.time(), zone)
            e = datetime.datetime.combine(datetime.date.fromisoformat(str(body.get("end") or "")[:10] or s.date().isoformat()),
                                          datetime.time(), zone)
            e = max(e, s + datetime.timedelta(days=1))
        else:
            s = datetime.datetime.fromisoformat(str(body.get("start") or "")[:16]).replace(tzinfo=zone)
            e = datetime.datetime.fromisoformat(str(body.get("end") or "")[:16]).replace(tzinfo=zone)
    except ValueError:
        raise ValueError("start and end must be dates like 2026-10-19 or 2026-10-19T10:00")
    if e <= s or e - s > datetime.timedelta(days=31):
        raise ValueError("the end must lie after the start, at most 31 days")
    return {"title": title, "start": s.isoformat(), "end": e.isoformat(), "allday": allday,
            "location": str(body.get("location") or "").strip()[:200], "alarm": 0,
            "calendar": str(body.get("calendar") or "").strip()[:120]}


async def page_find(uid, cal, title, start, zone):
    """The one single appointment the page shows: in the own calendar at place cal of reading(uid), with exactly this
    title and start (epoch seconds). The proposal dict change_event takes, or LookupError."""
    cals = reading(uid)["calendars"]
    if not 0 <= cal < len(cals) or cals[cal].get("owner"):
        raise LookupError("not an own calendar")
    s = datetime.datetime.fromtimestamp(int(start), zone)
    found, _ = await find_events(uid, title, s - datetime.timedelta(minutes=1), s + datetime.timedelta(minutes=1), zone)
    hits = [x for x in found if x["account"] == cals[cal]["id"] and x["title"] == title
            and int(datetime.datetime.fromisoformat(x["start"]).timestamp()) == int(start)]
    if len(hits) != 1:
        raise LookupError("the appointment is not there as a single one (changed meanwhile, or repeating)")
    return hits[0]


async def check(item, zone):
    """Reads one calendar entry before it is saved: number of calendars found, the next events."""
    now = datetime.datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=14)
    texts, n = await _fetch(item, start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
    evs = [x for x in await asyncio.to_thread(_expand, texts, start, end, zone) if x["end"] >= now or x["allday"]]
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


def line(x, now=None):
    """One appointment for the model; with now, one that has ended is marked, so it is never read out as
    still to come (Dominik, 2026-10-11)."""
    s = x["start"]
    day = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.}"
    if x["allday"]:
        days = (x["end"].date() - s.date()).days
        when = f"{day} ganztägig" + (f" ({days} Tage)" if days > 1 else "")
    else:
        when = f"{day} {s:%H:%M}" + (f"–{x['end']:%H:%M}" if x["end"] > s else "")
    return f"{when}: {x['title']}" + (f" (Ort: {x['location']})" if x["location"] else "") \
        + (f" [{x['calendar']}]" if x.get("many") and x.get("calendar") else "") \
        + (" (already over)" if now is not None and not x["allday"] and x["end"] <= now else "")


# ---------------------------------------------------------------- new appointments
# The assistant proposes an appointment (pending, per profile); only when the person says yes in
# the next message does the panel itself write it to the first CalDAV calendar (iCal links are
# read only). The model never writes on its own.
PENDING_SECONDS = 15 * 60
YES = re.compile(r"(?i)^\W*(ja|jo|jap|jep|jawohl|genau|passt|richtig|stimmt|ok(ay)?|mach( das| es)?|trag (es |ihn |das )?ein|"
                 r"bitte|gerne?|klar|yes|sure|do it)\b")
# "nein", and also a correction ("ok, aber am Freitag", "bitte um 11 statt 10"): then the proposal
# as it stands is not what the person wants
NO = re.compile(r"(?i)\b(nein|nö|nee|nicht|stopp|abbrechen|lass( es)?|doch nicht|no|cancel|aber|statt|stattdessen|"
                r"sondern|lieber|anders|ändern?|änder|verschieb\w*|but|instead|rather|change)\b")


# A plain yes holds nothing but yes words: "Okay, wie wird das Wetter?" is a new question, not a yes.
PLAIN = re.compile(r"(?i)^(\W*\b(ja|jo|jap|jep|jawohl|genau|passt|richtig|stimmt|ok|okay|mach|machs|das|es|ihn|den|"
                   r"trag|ein|leg|entwurf|ab|bitte|gerne?|danke|klar|gut|super|prima|perfekt|sehr|so|gemacht|"
                   r"codewort|yes|yeah|sure|do|it|please|thanks|fine)\b)+\W*$")


def confirms(text):
    """A plain yes to a proposal: starts like a yes, nothing else in it (no correction, no new question)."""
    t = str(text or "").strip()
    return bool(YES.search(t)) and not NO.search(t) and len(t.split()) <= 8 and bool(PLAIN.fullmatch(t))


def propose(uid, item, src=""):
    """src: where it was proposed (client and conversation); only a yes from there confirms it."""
    profiles.pending_set(uid, "calendar", item, src)


def pending(uid):
    return profiles.pending_get(uid, "calendar", PENDING_SECONDS)


def drop_pending(uid):
    profiles.pending_drop(uid, "calendar")


def describe(item):
    s = datetime.datetime.fromisoformat(item["start"])
    e = datetime.datetime.fromisoformat(item["end"])
    if item.get("allday"):
        when = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.%Y} ganztägig"
    else:
        when = f"{WEEKDAYS[s.weekday()]} {s:%d.%m.%Y} {s:%H:%M}–{e:%H:%M}"
    return f"„{item['title']}“ am {when}" + (f", Ort: {item['location']}" if item.get("location") else "") \
        + (f", Erinnerung {item['alarm']} Minuten vorher" if item.get("alarm") else "") \
        + (f", Kalender: {item['calendar']}" if item.get("calendar") else "")


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


async def add_event(uid, item, out=None):
    """_add_event with one journal line for every outcome (saved, refused by the Notaus, failed); never the
    appointment or the calendar's name."""
    who = profiles.log_name(profiles.by_id(uid))
    try:
        res = await _add_event(uid, item, out)
    except notaus.NotausAktiv:
        print(f"calendar: appointment refused, notaus | {who}", flush=True)
        raise
    except Exception as e:
        print(f"calendar: appointment not saved ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"calendar: appointment saved | {who}", flush=True)
    return res


async def _add_event(uid, item, out=None):
    """Writes the appointment to a writable CalDAV calendar: the one named in item "calendar" (its exact name
    first, then a name containing the words, across all connected accounts), else the first one. A named
    calendar that no account has is never swapped for another one: ValueError with the names there are
    (before it silently went into the first calendar; plan Rückfrage, Stufe C). A calendar another profile shares
    with "add" (Kalender teilen) only when it is named („in Sabines Kalender“), never as the first one.
    Returns the calendar's name."""
    notaus.stop("aktion", uid)   # the Notaus (or the profile's own) holds every action off (notaus.py)
    wanted = str(item.get("calendar") or "").strip().lower()
    last_error = "no CalDAV calendar connected (iCal links are read only)"
    found = []   # (account, (href, name)) of every writable calendar, in the accounts' order
    cals = get(uid)["calendars"]
    if wanted:
        cals += [x for x in reading(uid)["calendars"] if x.get("owner") and x.get("level") == "add"]
    for d in cals:
        if re.match(r"webcals?://", d["url"], re.I) or re.search(r"\.ics(\?|$)", d["url"], re.I):
            continue
        async with _cal_client(d) as c:
            try:
                found += [(d, x) for x in await _calendars(c, d["url"])]
            except Exception as e:
                last_error = str(e)
    if not found:
        raise ValueError(last_error)
    named = lambda x: (x[1][1] or x[0].get("name") or "").strip().lower()
    # a shared one also by its shown name and its owner („Sabine · Familie“, „Sabines Kalender“)
    owner = lambda x: (x[0].get("name") or "").strip().lower() if x[0].get("owner") else ""
    if wanted:
        # the page names a calendar by its entry's name (the account), the assistant mostly by the server's name
        hits = [x for x in found if wanted in (named(x), owner(x), (x[0].get("name") or "").strip().lower())] or [x for x in found if wanted in named(x) or (
            owner(x) and (wanted in owner(x) or owner(x).split(" · ")[0].rstrip("s") in wanted))]
        if not hits:
            raise ValueError(f"there is no calendar called '{item.get('calendar')}'; the calendars are: "
                             + ", ".join(dict.fromkeys(x[1][1] or x[0].get("name", "Kalender") for x in found)))
    else:
        hits = found
    d, pick = hits[0]
    async with _cal_client(d) as c:
        uid_text = f"{os.urandom(8).hex()}@speech-spark"
        url = pick[0].rstrip("/") + f"/{uid_text.split('@')[0]}.ics"
        r = await c.put(url, content=ical(item, uid_text),
                        headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        if r.status_code in (200, 201, 204):
            _drop(d.get("owner") or uid)
            if d.get("owner"):   # in another profile's calendar: undo and changes stay with its owner
                return d.get("name") or "Kalender"
            if out is not None:   # where it went, for „Mach das rückgängig“ (aendern.py)
                out.update(account=d.get("id"), href=url)
            return pick[1] or d.get("name", "Kalender")
    raise ValueError(f"the calendar server answered {r.status_code}")


# ---------------------------------------------------------------- moving and deleting (plan werkzeug-abdeckung C2)
# calendar_change finds one single appointment in the writable CalDAV calendars by words of its title and its day,
# proposes the change, and only the person's yes moves or deletes it (chat_turn, like calendar_add). A repeating
# appointment is never changed (one change would move every date); the server's etag guards against a change made
# meanwhile elsewhere. The old object is kept in memory for „Mach das rückgängig“ (aendern.py).
MAX_FOUND = 5


def _writable(uid):
    return [d for d in get(uid)["calendars"]
            if not re.match(r"webcals?://", d["url"], re.I) and not re.search(r"\.ics(\?|$)", d["url"], re.I)]


async def _objects(c, cal, start, end):
    """[(href, etag, ical text)] of the events overlapping [start, end) in one calendar."""
    fmt = "%Y%m%dT%H%M%SZ"
    q = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
         '<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
         f'<c:comp-filter name="VEVENT"><c:time-range start="{start.strftime(fmt)}" end="{end.strftime(fmt)}"/>'
         '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    r = await c.request("REPORT", cal, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    if r.status_code != 207:
        raise ValueError(f"the calendar server answered {r.status_code}")
    root = _xml(r.content)
    out = []
    for resp in (root.findall("d:response", NS) if root is not None else []):
        href = _href(cal, resp.find("d:href", NS))
        prop = resp.find("d:propstat/d:prop", NS)
        text = prop.findtext("c:calendar-data", "", NS) if prop is not None else ""
        if href and text and "BEGIN:VCALENDAR" in text:
            out.append((href, (prop.findtext("d:getetag", "", NS) or "").strip(), text))
    return out


def _event_of(text):
    """(the one VEVENT, its calendar) or (None, None) for a repeating or odd object."""
    try:
        cal = icalendar.Calendar.from_ical(text)
    except Exception:
        return None, None
    evs = [x for x in cal.walk("VEVENT")]
    if len(evs) != 1 or evs[0].get("RRULE") is not None or evs[0].get("RECURRENCE-ID") is not None:
        return None, None
    return evs[0], cal


def _when(ev, zone):
    s = ev.get("DTSTART").dt
    e = ev.get("DTEND").dt if ev.get("DTEND") is not None else s
    if not isinstance(s, datetime.datetime):
        return datetime.datetime.combine(s, datetime.time(), zone), \
            datetime.datetime.combine(e if not isinstance(e, datetime.datetime) else e.date(), datetime.time(), zone), True
    s = (s if s.tzinfo else s.replace(tzinfo=zone)).astimezone(zone)
    e = (e if isinstance(e, datetime.datetime) and e.tzinfo else (e.replace(tzinfo=zone) if isinstance(e, datetime.datetime)
                                                                    else s)).astimezone(zone)
    return s, e, False


async def find_events(uid, words, start, end, zone):
    """[{"account", "href", "etag", "title", "start", "end", "allday"}] of single appointments in [start, end) whose
    title holds every word (at least three letters); repeating ones are counted in "repeating"."""
    want = [w for w in re.findall(r"\w{3,}", str(words or "").lower()) if w not in ("termin", "den", "die", "das", "mit")][:5]
    found, repeating = [], 0
    for d in _writable(uid):
        async with _cal_client(d) as c:
            for href, _ in (await _calendars(c, d["url"]))[:20]:
                for ohref, etag, text in await _objects(c, href, start.astimezone(datetime.timezone.utc),
                                                        end.astimezone(datetime.timezone.utc)):
                    title = re.search(r"(?m)^SUMMARY[^:]*:(.*)$", text)
                    title = (title.group(1).strip() if title else "")[:200]
                    if want and not all(w in title.lower() for w in want):
                        continue
                    ev, _cal = _event_of(text)
                    if ev is None:
                        repeating += 1
                        continue
                    s, e, allday = _when(ev, zone)
                    found.append({"account": d.get("id"), "href": ohref, "etag": etag, "title": str(ev.get("SUMMARY", "") or title)[:200],
                                  "start": s.isoformat(), "end": e.isoformat(), "allday": allday})
    return found, repeating


def _old(p):
    return describe({"title": p["title"], "start": p["start"], "end": p["end"], "allday": p.get("allday")})


def _new(p):
    s = datetime.datetime.fromisoformat(p["new_start"])
    return f"{WEEKDAYS[s.weekday()]} {s:%d.%m.%Y}" + ("" if p.get("allday") else f" {s:%H:%M}")


def describe_change(p):
    return f"den Termin {_old(p)} löschen" if p["change"] == "delete" else f"den Termin {_old(p)} auf {_new(p)} verschieben"


def _account(uid, acc):
    d = next((x for x in _writable(uid) if x.get("id") == acc), None)
    if not d:
        raise ValueError("the calendar account was removed")
    return d


async def change_event(uid, p, out=None):
    """_change_event with one journal line for every outcome (moved, deleted, refused by the Notaus, failed);
    never the appointment or the calendar's name."""
    who = profiles.log_name(profiles.by_id(uid))
    what = {"delete": "deleted", "edit": "changed"}.get(p.get("change"), "moved")
    try:
        res = await _change_event(uid, p, out)
    except notaus.NotausAktiv:
        print(f"calendar: appointment change refused, notaus | {who}", flush=True)
        raise
    except Exception as e:
        print(f"calendar: appointment not {what} ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"calendar: appointment {what} | {who}", flush=True)
    return res


async def _change_event(uid, p, out=None):
    """Moves or deletes the appointment after the yes; out gets the old object for undo. Returns the checked result."""
    notaus.stop("aktion", uid)
    d = _account(uid, p["account"])
    async with _cal_client(d) as c:
        r = await c.get(p["href"])
        if r.status_code != 200:
            raise ValueError(f"the calendar server answered {r.status_code}")
        etag = r.headers.get("etag") or p.get("etag") or ""
        if p.get("etag") and etag and etag != p["etag"]:
            raise ValueError("the appointment was changed meanwhile; ask again")
        old = r.text
        ev, cal = _event_of(old)
        if ev is None:
            raise ValueError("a repeating appointment is not changed by voice")
        head = {"If-Match": etag} if etag else {}
        if p["change"] == "delete":
            r = await c.delete(p["href"], headers=head)
        elif p["change"] == "edit":   # the page's form: title, place, start and end at once
            for k in ("DTSTART", "DTEND", "DURATION", "DTSTAMP", "SUMMARY", "LOCATION"):
                ev.pop(k, None)
            s1, e1 = datetime.datetime.fromisoformat(p["new_start"]), datetime.datetime.fromisoformat(p["new_end"])
            ev.add("summary", p["new_title"])
            if p.get("new_location"):
                ev.add("location", p["new_location"])
            if p.get("new_allday"):
                ev.add("dtstart", s1.date())
                ev.add("dtend", e1.date())
            else:
                ev.add("dtstart", s1.astimezone(datetime.timezone.utc))
                ev.add("dtend", e1.astimezone(datetime.timezone.utc))
            ev.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
            seq = int(ev.get("SEQUENCE", 0) or 0)
            ev.pop("SEQUENCE", None)
            ev.add("sequence", seq + 1)
            r = await c.put(p["href"], content=cal.to_ical(),
                            headers=dict(head, **{"Content-Type": "text/calendar; charset=utf-8"}))
        else:
            s0 = datetime.datetime.fromisoformat(p["start"])
            e0 = datetime.datetime.fromisoformat(p["end"])
            s1 = datetime.datetime.fromisoformat(p["new_start"])
            for k in ("DTSTART", "DTEND", "DURATION", "DTSTAMP"):
                ev.pop(k, None)
            if p.get("allday"):
                ev.add("dtstart", s1.date())
                ev.add("dtend", (s1 + (e0 - s0)).date())
            else:
                ev.add("dtstart", s1.astimezone(datetime.timezone.utc))
                ev.add("dtend", (s1 + (e0 - s0)).astimezone(datetime.timezone.utc))
            ev.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
            seq = int(ev.get("SEQUENCE", 0) or 0)
            ev.pop("SEQUENCE", None)
            ev.add("sequence", seq + 1)
            r = await c.put(p["href"], content=cal.to_ical(),
                            headers=dict(head, **{"Content-Type": "text/calendar; charset=utf-8"}))
        if r.status_code not in (200, 201, 204):
            raise ValueError(f"the calendar server answered {r.status_code}")
    _drop(uid)
    if out is not None:
        out.update(account=p["account"], href=p["href"], ics=old, deleted=p["change"] == "delete")
    if p["change"] == "edit":
        return f"Termin „{p['new_title']}“ geändert."
    return f"Termin {_old(p)} gelöscht." if p["change"] == "delete" else f"Termin „{p['title']}“ auf {_new(p)} verschoben."


async def delete_href(uid, acc, href):
    """„Mach das rückgängig“ after calendar_add: the appointment the Spark entered goes again."""
    notaus.stop("aktion", uid)
    async with _cal_client(_account(uid, acc)) as c:
        r = await c.delete(href)
    if r.status_code not in (200, 204, 404):
        raise ValueError(f"the calendar server answered {r.status_code}")
    _drop(uid)


async def put_ics(uid, acc, href, ics, new=False):
    """„Mach das rückgängig“ after a move or delete: the old object goes back as it was."""
    notaus.stop("aktion", uid)
    async with _cal_client(_account(uid, acc)) as c:
        r = await c.put(href, content=ics.encode() if isinstance(ics, str) else ics,
                        headers=dict({"Content-Type": "text/calendar; charset=utf-8"}, **({"If-None-Match": "*"} if new else {})))
    if r.status_code not in (200, 201, 204):
        raise ValueError(f"the calendar server answered {r.status_code}")
    _drop(uid)


def _cal_client(d):
    auth = (d["user"], d.get("password", "")) if d.get("user") else None
    return netguard.client(netguard.USER, origin=d["url"], timeout=httpx.Timeout(20, connect=8), auth=auth,
                           follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"})
