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
and through the assistant, named "<owner> · <calendar>". An address can hold several calendars (an iCloud or
Nextcloud account): a share holds exactly the one the owner chose ({"share_parts": {profile id: its address}},
Code-Prüfung C2, 2026-10-19), never the whole account; an older share of such an address without that choice shows
nothing until it is shared again. A private appointment (CLASS PRIVATE or CONFIDENTIAL)
shows there only as „belegt“ with its time, never title or place. "add" lets the other profile's assistant propose
a new appointment there, saved only after its yes; changing and deleting stay with the owner. Guests never.
"""
import asyncio
import concurrent.futures
import datetime
import hashlib
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
import kalenderspiegel
import netguard
import notaus
import profiles
import sparkkalender
import vault

MAX_TOPICS = 3
MAX_CALENDARS = 8
CACHE_SECONDS = kalenderspiegel.SYNC_SECONDS   # a calendar block younger than this is used as it is (then the copy asks for changes)
STALE_SECONDS = 24 * 3600   # the page shows an older block at once and fetches it anew in the background
FOUND_SECONDS = 6 * 3600    # where the calendars of an address are (CalDAV discovery), asked again after this
WARM_SECONDS = 24 * 3600    # profiles that read their calendars in this time are kept fresh in the background
_cache = {}                 # (owner uid, calendar id, month "YYYY-MM-01" or "*" for an iCal file) -> (time, iCal texts)
_found = {}                 # (calendar id, address, user) -> (time, [(calendar url, name)], or None for an iCal file)
_inflight = {}              # cache key -> the task fetching that block (one fetch per block, whoever asks)
_used = {}                  # uid -> when it last read its calendars (keep_fresh)
_epoch = [0]                # counts drops: a fetch started before a change never stores its older answer
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
    for x in cals:   # a Spark calendar is bound to the profile whose file holds it, never to what the file says
        x.pop("uid", None)
        if x.get("spark"):
            x["uid"] = uid
    return {"calendars": cals,
            "topics": d.get("topics", []) if isinstance(d.get("topics"), list) else []}


def public(uid):
    """What the panel may see: everything but the passwords. With Kalender teilen also with whom each calendar is
    shared, the other profiles to choose from and what others share with this profile (names only, never their
    addresses)."""
    d = get(uid)
    out = {"calendars": [{"id": x["id"], "name": x.get("name", ""), "url": x["url"], "user": x.get("user", ""),
                          "has_password": bool(x.get("password")), "spark": bool(x.get("spark"))} for x in d["calendars"]],
           "topics": d["topics"]}
    if _sharing(uid):
        have = set(profiles.user_ids())
        for x, c in zip(out["calendars"], d["calendars"]):
            x["shares"] = {k: v for k, v in (c.get("shares") or {}).items() if k in have and v in LEVELS}
            x["share_parts"] = {k: v for k, v in (c.get("share_parts") or {}).items() if k in x["shares"]}
        out["people"] = [{"id": p["id"], "name": p["name"]} for p in profiles.names() if p["id"] != uid]
        out["shared"] = [{"owner": n, "name": c.get("name", ""), "level": lvl} for _, n, c, lvl in shared_to(uid)]
    return out


def _store(uid, d):
    with _lock:
        cals = [{k: v for k, v in dict(x, password=vault.seal(x.get("password", ""))).items() if k != "uid"}
                for x in d["calendars"]]
        profiles._write(_file(uid), {"calendars": cals, "topics": d["topics"], "updated": int(time.time())})
        _drop(uid)


def entry(body):
    """A checked calendar entry from the panel's form."""
    url = str(body.get("url", "")).strip()
    if not re.fullmatch(r"(https?|webcals?)://[^\s]{3,500}", url, re.I):
        raise ValueError("the calendar address must start with https://, http://, webcal:// or webcals://")
    if sparkkalender.is_spark(url):
        raise ValueError("this address belongs to a Spark calendar; add one with „Spark-Kalender anlegen“")
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


def set_share(uid, cid, to, level, part="", parts=None):
    """Shares the calendar cid of uid with the profile to ("see", "add"), or takes it back (level ""). parts: the
    calendars the address holds ([(address, name)], parts()); with more than one, part names the one shared (one of
    them, else ValueError), with one it is that one."""
    if level not in LEVELS + ("",):
        raise ValueError("level must be see, add or empty")
    if to == uid or to not in profiles.user_ids():
        raise ValueError("no such other profile")
    d = get(uid)
    cal = next((x for x in d["calendars"] if x["id"] == cid), None)
    if cal is None:
        raise KeyError(cid)
    sh = {k: v for k, v in (cal.get("shares") or {}).items() if v in LEVELS and k != to}
    only = {k: v for k, v in (cal.get("share_parts") or {}).items() if k in sh}
    if level:
        hrefs = [x[0] for x in parts or []]
        if len(hrefs) > 1 and part not in hrefs:
            raise ValueError("choose which calendar of this address is shared")
        sh[to] = level
        if hrefs:
            only[to] = part if len(hrefs) > 1 else hrefs[0]
    cal["shares"] = sh
    cal["share_parts"] = only
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
    d["calendars"] = d["calendars"] + [dict(c, name=shared_name(n, c), owner=o, level=lvl,
                                            only=(c.get("share_parts") or {}).get(uid, ""))
                                       for o, n, c, lvl in shared_to(uid)]
    return d


def add(uid, item):
    d = get(uid)
    if len(d["calendars"]) >= MAX_CALENDARS:
        raise ValueError(f"at most {MAX_CALENDARS} calendars")
    d["calendars"].append(item)
    _store(uid, d)
    return public(uid)


def add_spark(uid, name):
    """A new Spark calendar (sparkkalender.py) as an entry of the profile."""
    if len(get(uid)["calendars"]) >= MAX_CALENDARS:
        raise ValueError(f"at most {MAX_CALENDARS} calendars")
    item = sparkkalender.create(uid, name)
    try:
        return add(uid, item)
    except Exception:
        sparkkalender.forget(uid, [item["id"]])
        raise


def remove(uid, cid):
    d = get(uid)
    spark = [x["id"] for x in d["calendars"] if x["id"] == cid and x.get("spark")]
    d["calendars"] = [x for x in d["calendars"] if x["id"] != cid]
    _store(uid, d)
    kalenderspiegel.forget([cid])
    sparkkalender.forget(uid, spark)   # a Spark calendar's appointments live nowhere else: they go with it
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
    kalenderspiegel.forget([c["id"] for c in get(uid)["calendars"]])
    sparkkalender.forget(uid, [c["id"] for c in get(uid)["calendars"] if c.get("spark")])
    sparkkalender.drop_profile(uid)
    with _lock:
        try:
            os.remove(_file(uid))
        except OSError:
            pass
        _drop(uid)


def _drop(uid):
    kalenderspiegel.stale([c["id"] for c in get(uid)["calendars"]])
    _epoch[0] += 1
    _found.clear()
    for k in [k for k in _cache if k[0] == uid]:
        _cache.pop(k, None)


def changed_outside(uid, cid):
    """A calendar app changed a Spark calendar (kalenderserver.py): the owner's and every reader's views anew."""
    _drop(uid)
    _drop_shared(cid)


def _drop_shared(cid):
    _epoch[0] += 1
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
    root = await asyncio.to_thread(_xml, r.content)   # a month of a big calendar: parsed outside the event loop
    return [x.text for x in (root.iter("{urn:ietf:params:xml:ns:caldav}calendar-data") if root is not None else [])
            if x.text and "BEGIN:VCALENDAR" in x.text]


async def _parts(c, d):
    """The calendars of an entry's address a reader may see (_only), from the last discovery while it is fresh
    (FOUND_SECONDS), else found anew: a change on the page needs no round trips to find them again."""
    if d.get("spark"):   # a Spark calendar is one calendar at its own address (sparkkalender.py)
        return [(d["url"], d.get("name", ""))]
    where = (d.get("id"), d["url"], d.get("user"))
    known = _found.get(where)
    if not (known and known[1] and time.time() - known[0] < FOUND_SECONDS):
        cals = await _calendars(c, d["url"])
        if cals:
            _found[where] = (time.time(), cals)
        known = (0, cals)
    return _only(d, known[1])


def _only(d, cals):
    """The calendars of an address a reader may see: all of them for the owner; for a calendar another profile shares
    (d["owner"]) only the one chosen when it was shared (an address with a single calendar: that one). ValueError
    when it is not there (C2: never the whole account)."""
    if not d.get("owner"):
        return cals
    keep = [x for x in cals if x[0] == d.get("only")] if d.get("only") else cals if len(cals) == 1 else []
    if not keep:
        raise ValueError("the shared calendar is no longer there; its owner shares it again")
    return keep


async def parts(uid, cid):
    """[(address, name)] of the calendars an own CalDAV entry holds (the share window offers them); [] for an iCal
    link (one calendar)."""
    d = next((x for x in get(uid)["calendars"] if x["id"] == cid), None)
    if d is None:
        raise KeyError(cid)
    if re.match(r"webcals?://", d["url"], re.I) or re.search(r"\.ics(\?|$)", d["url"], re.I):
        return []
    async with _cal_client(d) as c:
        return (await _calendars(c, d["url"]))[:20]


async def _read(c, d, url, start, end):
    """One CalDAV calendar's texts for [start, end): from the Spark's copy (kalenderspiegel, only the changes come
    from the server); an entry not saved yet (the check before it is added) asks the server directly."""
    if kalenderspiegel.CID.fullmatch(str(d.get("id") or "")) and not d.get("unsaved") and not d.get("spark"):
        try:
            return await kalenderspiegel.texts(c, d["id"], url, start, end)
        except kalenderspiegel.Unsupported:
            pass
    return await _report(c, url, start, end)


async def _fetch(d, start, end):
    """iCal texts of all events overlapping [start, end) (UTC datetimes); number of calendars."""
    if d.get("spark"):   # lives in the panel: no discovery, no copy, no network (sparkkalender.py)
        async with _cal_client(d) as c:
            return await _report(c, d["url"], start, end), 1
    url = d["url"]
    auth = (d["user"], d.get("password", "")) if d.get("user") else None
    web = re.sub(r"^webcals?://", "https://", url, flags=re.I)
    async with netguard.client(netguard.USER, origin=web, timeout=httpx.Timeout(20, connect=8), auth=auth,
                               follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"},
                               seen=hintergrund.tracker("cal", d.get("id")) if d.get("id") else None) as c:
        where = (d.get("id"), url, d.get("user"))
        known = _found.get(where)
        if known and known[1] and time.time() - known[0] < FOUND_SECONDS:
            known = (known[0], _only(d, known[1]))
            # the calendars of this address were found before: straight to them, without the discovery round trips
            texts, ok, last = [], 0, None
            for part in await asyncio.gather(*(_read(c, d, u, start, end) for u, _ in known[1][:20]), return_exceptions=True):
                if isinstance(part, Exception):
                    last = part
                    continue
                texts += part
                ok += 1
            if ok:
                return texts, len(known[1])
            _found.pop(where, None)   # none answered: find them anew below (the error of a single one stands)
            if len(known[1]) == 1 and isinstance(last, ValueError) and "401" in str(last):
                raise last
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
            _found[where] = (time.time(), None)
            return [r.text], 1
        cals = await _calendars(c, str(r.url) if r.status_code == 200 else url)
        if not cals:
            raise ValueError("no calendar found at this address (CalDAV server or iCal link expected)")
        _found[where] = (time.time(), cals)
        cals = _only(d, cals)
        texts = []
        for part in await asyncio.gather(*(_read(c, d, u, start, end) for u, _ in cals[:20]), return_exceptions=True):
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


EXPANDED_MAX = 30000          # (object, month) results kept (a few MB at most)
_expanded = {}               # (sha1 of one iCal text, month "YYYY-MM-01" UTC, zone) -> [events of that month]


def _low():
    """The expanding thread runs at low priority, so voice and the event loop go first on a busy Pi."""
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except (AttributeError, OSError):
        pass


# One thread for all expanding (Dominik 2026-10-19, panel stalls of 6-8 s): two at once held the GIL so often that
# the event loop waited; one at a time, nice 10, and it lets go of the GIL after every object it computes.
_EXPANDER = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="kalender-ausdehnen",
                                                  initializer=_low)


async def expand(texts, start, end, zone, name=""):
    """_expand outside the event loop, one at a time (_EXPANDER)."""
    return await asyncio.get_running_loop().run_in_executor(_EXPANDER, _expand, texts, start, end, zone, name)


def _month_events(text, a, b, zone):
    """The events of one iCal text in the month block [a, b) (UTC) with a day of slack on both sides, as dicts
    without the calendar's name. Pure Python and slow for long repeating series: kept in _expanded."""
    out = []
    try:
        cal = _tame(icalendar.Calendar.from_ical(text), a)
        # every occurrence carries a RECURRENCE-ID after expanding: a repeating one is known by its master
        rep = {str(v.get("UID", "")) for v in cal.walk("VEVENT")
               if v.get("RRULE") is not None or v.get("RDATE") is not None or v.get("RECURRENCE-ID") is not None}
        items = recurring_ical_events.of(cal).between(a - datetime.timedelta(days=1), b + datetime.timedelta(days=1))
    except Exception:
        return out
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
                    "location": str(ev.get("LOCATION", "") or "").strip()[:200],
                    "note": _note(ev.get("DESCRIPTION")), "link": _link(ev.get("URL")),
                    "private": str(ev.get("CLASS", "") or "").upper() in ("PRIVATE", "CONFIDENTIAL"),
                    "repeat": str(ev.get("UID", "")) in rep})
    return out


NOTE_MAX = 2000      # characters of an appointment's own text (DESCRIPTION) the page shows


def _note(v):
    """An appointment's own text as plain text: control characters out, at most two empty lines, NOTE_MAX long.
    Written by whoever made the appointment: shown as text, never as a page or an order."""
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v or "")).replace("\r", "").strip()
    return re.sub(r"\n{3,}", "\n\n", s)[:NOTE_MAX]


def _link(v):
    """The appointment's web address (URL) as text when it is http(s), else empty."""
    s = str(v or "").strip()
    return s[:300] if re.fullmatch(r"https?://[^\s<>\"]{1,300}", s) else ""


def _expand(texts, start, end, zone, name=""):
    """The events of the iCal texts in [start, end), sorted. Each object is expanded once per month block and zone
    and kept (_expanded): a look, the check every minute, keep_fresh and the briefing only compute what changed."""
    utc = datetime.timezone.utc
    blocks = _months(start.astimezone(utc), end.astimezone(utc))
    zkey = getattr(zone, "key", None) or str(zone)
    out = []
    for text in texts:
        h = hashlib.sha1(text.encode("utf-8", "replace") if isinstance(text, str) else bytes(text)).hexdigest()
        for m in blocks:
            key = (h, m.date().isoformat(), zkey)
            got = _expanded.get(key)
            if got is None:
                got = _month_events(text, m, (m + datetime.timedelta(days=32)).replace(day=1), zone)
                if len(_expanded) >= EXPANDED_MAX:
                    for k in list(_expanded)[:EXPANDED_MAX // 10]:
                        _expanded.pop(k, None)
                _expanded[key] = got
                time.sleep(0)   # let go of the GIL: the event loop waits for nobody
            out += got
    keep = [dict(x, calendar=name) for x in out
            if x["start"] < end and (x["end"] > start or (x["end"] <= x["start"] and x["start"] >= start))]
    uniq = {(x["start"], x["title"]): x for x in keep}
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"]))


def _months(start, end):
    """The first days (UTC) of the months [start, end) touches: the blocks the cache keeps."""
    m = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    while m < end and len(out) < 24:
        out.append(m)
        m = (m + datetime.timedelta(days=32)).replace(day=1)
    return out


async def _pull(uid, cal, key, a, b):
    epoch = _epoch[0]
    texts, _ = await _fetch(cal, a, b)
    if epoch == _epoch[0]:
        ical = (cal.get("id"), cal.get("url"), cal.get("user")) in _found \
            and _found[(cal.get("id"), cal.get("url"), cal.get("user"))][1] is None
        _cache[(uid, cal["id"], "*") if ical else key] = (time.time(), texts)
    return texts


def _block(uid, cal, key, a, b, behind=False):
    """The task fetching one block, started once however many ask. It runs on its own: a page that stops waiting
    (VIEW_BUDGET) never cancels it, so its answer still lands in the cache for the next look. behind: nobody waits
    for it (a refresh behind the page), so a failure writes its own line."""
    task = _inflight.get(key)
    if task is not None and task.get_loop() is not asyncio.get_running_loop():
        task = None   # started in another event loop (a thread of its own): this one fetches for itself
    if task is None:
        task = asyncio.ensure_future(_pull(uid, cal, key, a, b))
        task.behind = behind
        _inflight[key] = task
        task.add_done_callback(lambda t, k=key, who=uid: _pulled(k, who, t))
    return task


def _pulled(key, uid, task):
    _inflight.pop(key, None)
    if task.cancelled():
        return
    e = task.exception()   # always read, so no "exception never retrieved"
    if e is not None and task.behind:
        print(f"calendar: refresh failed ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)


async def _one(uid, cal, start, end, zone, stale=False):
    # kept per calendar month (UTC), so the check every minute, the assistant, the briefing and the page all hit the
    # same blocks; expanded for the exact period asked. stale (the page, keep_fresh): a block up to a day old is used
    # at once and fetched anew in the background.
    now = time.time()
    for k in [k for k, v in _cache.items() if now - v[0] >= STALE_SECONDS]:
        _cache.pop(k, None)
    blocks = _months(start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
    whole = (uid, cal["id"], "*")
    if whole in _cache:   # an iCal file: one text for every period
        want = [(whole, blocks[0], (blocks[-1] + datetime.timedelta(days=32)).replace(day=1))]
    else:
        want = [((uid, cal["id"], m.date().isoformat()), m, (m + datetime.timedelta(days=32)).replace(day=1)) for m in blocks]
    wait = {}
    for key, a, b in want:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            continue
        task = _block(uid, cal, key, a, b, behind=bool(hit and stale))
        if not (hit and stale):
            wait[key] = task
    got = {}
    for key, r in zip(wait, await asyncio.gather(*(asyncio.shield(t) for t in wait.values()), return_exceptions=True)):
        if isinstance(r, BaseException):
            raise r
        got[key] = r   # also when a change meanwhile kept it out of the cache (_epoch)
    keys = [whole] if whole in _cache else [k for k, _, _ in want]
    texts = list(dict.fromkeys(x for k in keys for x in (_cache.get(k) or (0, got.get(k, [])))[1]))
    # expanding runs outside the event loop, one at a time, so a heavy calendar never stalls the panel
    evs = await expand(texts, start, end, zone, cal.get("name", ""))
    if cal.get("owner"):   # shared by another profile (2a): a private appointment is only „belegt“ with its time
        evs = [dict(x, title=BUSY, location="", note="", link="") if x["private"] else x for x in evs]
    return evs


async def _collect(uid, start, end, zone, shared, stale, budget=None):
    """(events, [(name, error)], [names still loading]) of the profile's calendars. budget: seconds to wait at most;
    a calendar not done by then keeps loading in the background and is named in the third list."""
    cals = (reading(uid) if shared else get(uid))["calendars"]
    _used[uid] = time.time()
    # a shared calendar is cached under its owner (the same fetch serves the owner and everyone it is shared with)
    tasks = [asyncio.ensure_future(_one(c.get("owner") or uid, c, start, end, zone, stale)) for c in cals]
    if budget is not None and tasks:
        await asyncio.wait(tasks, timeout=budget)
    else:
        await asyncio.gather(*tasks, return_exceptions=True)
    evs, errors, loading = [], [], []
    for c, t in zip(cals, tasks):
        if not t.done():
            t.cancel()   # only this reader; the fetch itself goes on (_block)
            loading.append(c.get("name", ""))
        elif t.exception() is not None:
            r = t.exception()
            errors.append((c.get("name", ""), str(r) if isinstance(r, ValueError) else f"not reachable ({type(r).__name__})"))
        else:
            evs += t.result()
    many = len(cals) > 1 or any(c.get("owner") for c in cals)   # a shared one always says whose it is
    uniq = {}
    for x in evs:   # the same appointment in two calendars (e.g. shared ones) is read out once
        k = (x["start"], x["title"].lower())
        if k in uniq:
            if x["calendar"] and x["calendar"] not in uniq[k]["calendar"].split(", "):
                uniq[k]["calendar"] += ", " + x["calendar"]
        else:
            uniq[k] = dict(x, many=many)
    return sorted(uniq.values(), key=lambda x: (x["start"], not x["allday"])), errors, loading


async def events(uid, start, end, zone, shared=False, stale=False):
    """(events of all the profile's calendars from start to end, sorted; [(name, error)] of the
    calendars that could not be read). None when no calendar is connected. shared: also the calendars other
    profiles share with it (the page and the assistant's calendar_events; never the briefing or Von selbst). stale: an
    older block (up to STALE_SECONDS) at once while it is fetched anew behind (the card under Heute; the assistant
    always waits for a fresh one)."""
    if not (reading(uid) if shared else get(uid))["calendars"]:
        return None
    evs, errors, _ = await _collect(uid, start, end, zone, shared, stale)
    return evs, errors


async def keep_fresh(now=None):
    """Background refresh (Dominik 2026-10-19 „caching für einträge und hintergrund aktualisierung“): the blocks of
    this and the next month of every profile that read its calendars in the last WARM_SECONDS are fetched anew when
    older than CACHE_SECONDS, so the page and the assistant answer from the cache. Only reading; nothing is said or
    kept elsewhere. Returns (profiles, calendars refreshed)."""
    import features
    now = time.time() if now is None else now
    people = n = 0
    for uid, seen in list(_used.items()):
        if now - seen > WARM_SECONDS:
            _used.pop(uid, None)
            continue
        if not features.allowed("calendar", uid):
            continue
        people += 1
        n += await warm(uid, now)
    return people, n


async def warm(uid, now=None):
    """This and the next month of one profile's calendars (also those shared with it) anew when older than
    CACHE_SECONDS; kept fresh from now on (keep_fresh, vorwaermen.py at sign-in). Returns the calendars read."""
    now = time.time() if now is None else now
    _used.setdefault(uid, now)
    t0 = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    res = await asyncio.gather(*(_one(c.get("owner") or uid, c, t0, t0 + datetime.timedelta(days=35),
                                      datetime.timezone.utc) for c in reading(uid)["calendars"]), return_exceptions=True)
    return sum(1 for r in res if not isinstance(r, BaseException))


async def keep_fresh_loop():
    """Started with the panel; every CACHE_SECONDS one keep_fresh, one line when it fetched something."""
    while True:
        await asyncio.sleep(CACHE_SECONDS)
        try:
            people, n = await keep_fresh()
            if people:
                print(f"calendar: kept fresh | {n} calendars of {people} profiles", flush=True)
        except Exception as e:
            print(f"calendar: keep fresh failed ({type(e).__name__})", flush=True)


# ---------------------------------------------------------------- the page Kalender (kalender.js)
VIEW_DAYS = 42            # the page asks for at most six weeks at a time (a month with its weeks around it)
VIEW_BUDGET = 8.0         # seconds; a slow calendar shows „lädt noch“ and keeps loading in the background, the page
                          # never waits longer and asks again (kalender.js)
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
    evs, errors, loading = await _collect(uid, t0, t1, zone, True, True, VIEW_BUDGET)
    out = []
    for x in evs[:VIEW_MAX]:
        first = (x.get("calendar") or "").split(", ")[0]
        i = names.index(first) if first in names else 0
        ok = i in edit and not x.get("repeat")
        out.append({"start": int(x["start"].timestamp()), "end": int(x["end"].timestamp()), "allday": bool(x["allday"]),
                    "title": x["title"], "location": x["location"], "cal": i, "edit": ok,
                    "note": x.get("note", ""), "link": x.get("link", ""), "why": "" if ok else _why(cals[i], x)})
    return {"connected": True, "calendars": names, "shared": shared, "edit": edit, "add": add, "events": out,
            "errors": [n for n, _ in errors], "loading": loading, "notes": notes(uid)}


def _why(cal, x):
    """Why the page may not change an appointment, as a fixed word (READONLY): abo, geteilt, serie, lesen."""
    if cal.get("owner"):
        return "geteilt"
    if re.match(r"webcals?://", cal.get("url", ""), re.I) or re.search(r"\.ics(\?|$)", cal.get("url", ""), re.I):
        return "abo"
    return "serie" if x.get("repeat") else "lesen"


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


# Schnell eintragen (Dominik 2026-10-19 „2a“): one line on the page Kalender, e.g. „Zahnarzt morgen 10 Uhr bei
# Dr. Weber“, becomes the form's fields by fixed rules (no model); the page shows them as chips and saves only on
# „Eintragen“ through page_item, like the form.
QUICK_MAX = 200
QUICK_HOURS = 1   # an appointment with only a start lasts an hour
# a short day (Mo, Fr …) only as „am Fr“ or „Fr.“, so „so“ or „do“ in a title stay words
_DAYS = (r"montags?|dienstags?|mittwochs?|donnerstags?|freitags?|samstags?|sonntags?|monday|tuesday|wednesday|"
         r"thursday|friday|saturday|sunday|(?<=am )(?:mo|di|mi|do|fr|sa|so)|(?:mo|di|mi|do|fr|sa|so)(?=\.)")
_DAY_ORDER = ("mo", "di", "mi", "do", "fr", "sa", "so")
_DAY_EN = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_Q_REL = re.compile(r"(?i)(?<!\w)(?:am\s+)?(heute|today|übermorgen|morgen|tomorrow)(?!\w)")
_Q_IN = re.compile(r"(?i)(?<!\w)in\s+(\d{1,2})\s+(tagen|wochen|days|weeks)(?!\w)")
_Q_DAY = re.compile(r"(?i)(?<!\w)(?:(?:am|on)\s+)?(?:(nächsten|kommenden|next)\s+)?(" + _DAYS + r")\.?(?!\w)")
_Q_DATE = re.compile(r"(?<![\w.])(?:am\s+)?(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})?(?![\w])")
_Q_TIME = r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?"
_Q_SPAN = re.compile(r"(?i)(?<![\w.:])(?:(?:um|von|at|from)\s+)?" + _Q_TIME + r"\s*(?:-|–|bis|to)\s*" + _Q_TIME +
                     r"(?:\s*uhr)?(?![\w:])")
_Q_AT = re.compile(r"(?i)(?<![\w.:])(?:(?:um|at)\s+" + _Q_TIME + r"(?:\s*uhr)?|" + r"(\d{1,2})(?:[:.](\d{2}))?\s*uhr|"
                   r"(\d{1,2}):(\d{2})|(\d{1,2})\s*(am|pm))(?![\w:])")
_Q_PLACE = re.compile(r"(?i)\s(?:in|im|bei|beim|@|at)\s+(.+)$")


def _hour(h, m, ap):
    h, m = int(h), int(m or 0)
    if ap:
        if not 1 <= h <= 12:
            raise ValueError
        h = h % 12 + (12 if ap.lower() == "pm" else 0)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return datetime.time(h, m)


def quick(text, now):
    """The form's fields from one line (page_item takes them): {"title", "start", "end", "allday", "location",
    "found": [the recognised parts, for the chips]}; ValueError without a title. now: aware datetime (the person's
    zone). A day without a time is all day; a time without a day is today, or tomorrow when it has passed."""
    t = " " + " ".join(str(text or "").split())[:QUICK_MAX] + " "
    found, day, times = [], None, None

    def cut(m):
        nonlocal t
        t = t[:m.start()] + " " + t[m.end():]
    m = _Q_DATE.search(t)
    if m:
        y = m.group(3)
        y = int(y) + (2000 if len(y) == 2 else 0) if y else now.year
        try:
            day = datetime.date(y, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and day < now.date():
                day = day.replace(year=y + 1)
            cut(m)
        except ValueError:
            day = None
    if day is None:
        m = _Q_REL.search(t)
        if m:
            w = m.group(1).lower()
            day = now.date() + datetime.timedelta(days={"heute": 0, "today": 0, "morgen": 1, "tomorrow": 1}.get(w, 2))
            cut(m)
    if day is None:
        m = _Q_IN.search(t)
        if m:
            day = now.date() + datetime.timedelta(days=int(m.group(1)) * (7 if m.group(2).lower()[0] == "w" else 1))
            cut(m)
    if day is None:
        m = _Q_DAY.search(t)
        if m:
            w = m.group(2).lower()[:3]
            wd = _DAY_EN.index(w) if w in _DAY_EN else _DAY_ORDER.index(w[:2])
            ahead = (wd - now.weekday()) % 7   # the coming one; today's weekday is today, „nächsten“ a week on
            day = now.date() + datetime.timedelta(days=ahead or (7 if m.group(1) else 0))
            cut(m)
    m = _Q_SPAN.search(t)
    try:
        if m:
            times = (_hour(*m.group(1, 2, 3)), _hour(*m.group(4, 5, 6)))
            cut(m)
        else:
            m = _Q_AT.search(t)
            if m:
                g = m.groups()
                h, mi, ap = (g[0], g[1], g[2]) if g[0] else (g[3], g[4], None) if g[3] else \
                    (g[5], g[6], None) if g[5] else (g[7], None, g[8])
                times = (_hour(h, mi, ap), None)
                cut(m)
    except ValueError:
        times = None
    location = ""
    rest = " " + " ".join(t.split())
    m = _Q_PLACE.search(rest)
    if m and m.start() > 0:
        location, rest = m.group(1).strip(" ,.;"), rest[:m.start()]
    title = re.sub(r"(?i)^(?:(?:am|um|on|at)\s+)+|(?:\s+(?:am|um|on|at))+$", "", " ".join(rest.split())).strip(" ,.;-–")
    if not title:
        raise ValueError("a title is needed")
    if times is None:
        day = day or now.date()
        start, end, allday = day.isoformat(), (day + datetime.timedelta(days=1)).isoformat(), True
        found.append(day.isoformat())
    else:
        if day is None:
            day = now.date() if datetime.datetime.combine(now.date(), times[0], now.tzinfo) > now \
                else now.date() + datetime.timedelta(days=1)
        s = datetime.datetime.combine(day, times[0])
        e = datetime.datetime.combine(day, times[1]) if times[1] else s + datetime.timedelta(hours=QUICK_HOURS)
        if e <= s:
            e += datetime.timedelta(days=1)
        start, end, allday = s.isoformat(timespec="minutes"), e.isoformat(timespec="minutes"), False
        found.append(start)
    if location:
        found.append(location)
    return {"title": title[:200], "start": start, "end": end, "allday": allday, "location": location[:200],
            "found": found}


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
    texts, n = await _fetch(dict(item, unsaved=True), start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc))
    evs = [x for x in await expand(texts, start, end, zone) if x["end"] >= now or x["allday"]]
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


async def add_event(uid, item, out=None, wait=True):
    """_add_event with one journal line for every outcome (saved, refused by the Notaus, failed); never the
    appointment or the calendar's name."""
    who = profiles.log_name(profiles.by_id(uid))
    try:
        res = await _add_event(uid, item, out, wait)
    except notaus.NotausAktiv:
        print(f"calendar: appointment refused, notaus | {who}", flush=True)
        raise
    except Exception as e:
        print(f"calendar: appointment not saved ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"calendar: appointment saved | {who}", flush=True)
    return res


async def _add_event(uid, item, out=None, wait=True):
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
                found += [(d, x) for x in await _parts(c, d)]
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
    uid_text = f"{os.urandom(8).hex()}@speech-spark"
    url = pick[0].rstrip("/") + f"/{uid_text.split('@')[0]}.ics"
    if not wait and kalenderspiegel.ready(d.get("id"), pick[0]):
        # Stufe 2 (the page): into the Spark's copy at once, to the server behind it
        text = ical(item, uid_text)
        text = text if isinstance(text, str) else text.decode()
        import core
        core.later(_behind(uid, d, pick[0], url, text, _local(uid, d, pick[0], url, text)))
        if d.get("owner"):
            return d.get("name") or "Kalender"
        if out is not None:
            out.update(account=d.get("id"), href=url)
        return pick[1] or d.get("name", "Kalender")
    async with _cal_client(d) as c:
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


async def _objects(c, cal, start, end, d=None):
    """[(href, etag, ical text)] of the events overlapping [start, end) in one calendar; from the Spark's copy when
    the entry d has one (kalenderspiegel), else asked from the server."""
    if d is not None and kalenderspiegel.CID.fullmatch(str(d.get("id") or "")) and not d.get("spark"):
        try:
            return [(urljoin(cal, h), tag, text) for h, tag, text in await kalenderspiegel.objects(c, d["id"], cal, start, end)]
        except kalenderspiegel.Unsupported:
            pass
    fmt = "%Y%m%dT%H%M%SZ"
    q = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
         '<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
         f'<c:comp-filter name="VEVENT"><c:time-range start="{start.strftime(fmt)}" end="{end.strftime(fmt)}"/>'
         '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    r = await c.request("REPORT", cal, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    if r.status_code != 207:
        raise ValueError(f"the calendar server answered {r.status_code}")
    root = await asyncio.to_thread(_xml, r.content)   # a month of a big calendar: parsed outside the event loop
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
            for href, _ in (await _parts(c, d))[:20]:
                for ohref, etag, text in await _objects(c, href, start.astimezone(datetime.timezone.utc),
                                                        end.astimezone(datetime.timezone.utc), d):
                    title = re.search(r"(?m)^SUMMARY[^:]*:(.*)$", text)
                    title = (title.group(1).strip() if title else "")[:200]
                    if want and not all(w in title.lower() for w in want):
                        continue
                    ev, _cal = _event_of(text)
                    if ev is None:
                        repeating += 1
                        continue
                    s, e, allday = _when(ev, zone)
                    found.append({"account": d.get("id"), "cal": href, "href": ohref, "etag": etag, "title": str(ev.get("SUMMARY", "") or title)[:200],
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


async def change_event(uid, p, out=None, wait=True):
    """_change_event with one journal line for every outcome (moved, deleted, refused by the Notaus, failed);
    never the appointment or the calendar's name."""
    who = profiles.log_name(profiles.by_id(uid))
    what = {"delete": "deleted", "edit": "changed"}.get(p.get("change"), "moved")
    try:
        res = await _change_event(uid, p, out, wait)
    except notaus.NotausAktiv:
        print(f"calendar: appointment change refused, notaus | {who}", flush=True)
        raise
    except Exception as e:
        print(f"calendar: appointment not {what} ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"calendar: appointment {what} | {who}", flush=True)
    return res


async def _change_event(uid, p, out=None, wait=True):
    """Moves or deletes the appointment after the yes; out gets the old object for undo. Returns the checked result.
    The object and its etag come from the Spark's copy when it has it, else from the server. wait False (the page,
    Stufe 2 „3a“): the change lands in the copy at once and goes to the server behind it (_behind)."""
    notaus.stop("aktion", uid)
    d = _account(uid, p["account"])
    local = kalenderspiegel.item(d.get("id"), p.get("cal") or "", p["href"]) if p.get("cal") else None
    if local and local[0] and not (p.get("etag") and p["etag"] != local[0]):
        etag, old = local
    else:
        local = None
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
    if p["change"] == "delete":
        text = None
    else:
        for k in ("DTSTART", "DTEND", "DURATION", "DTSTAMP") + (("SUMMARY", "LOCATION") if p["change"] == "edit" else ()):
            ev.pop(k, None)
        if p["change"] == "edit":   # the page's form: title, place, start and end at once
            s1, e1 = datetime.datetime.fromisoformat(p["new_start"]), datetime.datetime.fromisoformat(p["new_end"])
            ev.add("summary", p["new_title"])
            if p.get("new_location"):
                ev.add("location", p["new_location"])
            allday = p.get("new_allday")
        else:
            s0 = datetime.datetime.fromisoformat(p["start"])
            e0 = datetime.datetime.fromisoformat(p["end"])
            s1 = datetime.datetime.fromisoformat(p["new_start"])
            e1 = s1 + (e0 - s0)
            allday = p.get("allday")
        if allday:
            ev.add("dtstart", s1.date())
            ev.add("dtend", e1.date())
        else:
            ev.add("dtstart", s1.astimezone(datetime.timezone.utc))
            ev.add("dtend", e1.astimezone(datetime.timezone.utc))
        ev.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
        seq = int(ev.get("SEQUENCE", 0) or 0)
        ev.pop("SEQUENCE", None)
        ev.add("sequence", seq + 1)
        text = cal.to_ical().decode()
    if not wait and local:
        import core
        core.later(_behind(uid, d, p["cal"], p["href"], text, _local(uid, d, p["cal"], p["href"], text), etag))
    else:
        head = {"If-Match": etag} if etag else {}
        async with _cal_client(d) as c:
            if text is None:
                r = await c.delete(p["href"], headers=head)
            else:
                r = await c.put(p["href"], content=text.encode(),
                                headers=dict(head, **{"Content-Type": "text/calendar; charset=utf-8"}))
        if r.status_code not in (200, 201, 204):
            raise ValueError(f"the calendar server answered {r.status_code}")
        _drop(uid)
    if out is not None:
        out.update(account=p["account"], href=p["href"], ics=old, deleted=p["change"] == "delete")
    if p["change"] == "edit":
        return f"Termin „{p['new_title']}“ geändert."
    return f"Termin {_old(p)} gelöscht." if p["change"] == "delete" else f"Termin „{p['title']}“ auf {_new(p)} verschoben."


# ---------------------------------------------------------------- Stufe 2: the page's changes behind the page
NOTE_SECONDS = 600   # how long the page shows that a change did not reach the server
_notes = {}          # uid -> [(when, title or "")] of changes the server refused


def _blocks(*uids):
    """After a change in the copy: the month blocks are built anew from it (discovery and the copy stay)."""
    _epoch[0] += 1
    for k in [k for k in _cache if k[0] in uids]:
        _cache.pop(k, None)


def _local(uid, d, cal_url, href, text):
    """A page change into the copy of entry d and of every other entry of the writer (and of the owner of a shared
    calendar) holding the same calendar, so no view shows the old version meanwhile. {entry id: how it was}."""
    owner = d.get("owner")
    ids = [d["id"]] + [x["id"] for x in reading(uid)["calendars"] + (get(owner)["calendars"] if owner else [])]
    before = {cid: kalenderspiegel.put_local(cid, cal_url, href, text)
              for cid in dict.fromkeys(ids) if cid == d["id"] or kalenderspiegel.ready(cid, cal_url)}
    _blocks(uid, owner)
    return before


def notes(uid, now=None):
    """The page's notes: changes of the last NOTE_SECONDS the server did not take (the copy went back)."""
    now = time.time() if now is None else now
    keep = [x for x in _notes.get(uid, []) if now - x[0] < NOTE_SECONDS]
    if keep:
        _notes[uid] = keep
    else:
        _notes.pop(uid, None)
    return [x[1] for x in keep]


async def _behind(uid, d, cal_url, href, text, before, etag=""):
    """Sends one change of the page to the server after the copies took it (before: {entry id: how the object was
    there}, from _local). text None deletes. Refused (changed
    elsewhere meanwhile, not reachable): the copy goes back, the server's version wins at the next look, and the
    page shows a note. One journal line for each outcome."""
    who = profiles.log_name(profiles.by_id(uid))
    tag, status = "", 0
    try:
        async with _cal_client(d) as c:
            if text is None:
                r = await c.delete(href, headers={"If-Match": etag} if etag else {})
                ok = r.status_code in (200, 204, 404)
            else:
                head = {"Content-Type": "text/calendar; charset=utf-8"}
                head.update({"If-Match": etag} if etag else {} if before.get(d["id"]) else {"If-None-Match": "*"})
                r = await c.put(href, content=text.encode(), headers=head)
                ok = r.status_code in (200, 201, 204)
                tag = r.headers.get("etag", "")
            status = r.status_code
    except Exception as e:
        ok, status = False, type(e).__name__
    for cid, was in before.items():
        if ok:
            kalenderspiegel.taken(cid, cal_url, href, tag)
        else:
            kalenderspiegel.undo(cid, cal_url, href, was)
    if ok:
        print(f"calendar: saved behind | {who}", flush=True)
    else:
        was = before.get(d["id"]) or ["", ""]
        title = re.search(r"(?m)^SUMMARY[^:]*:(.*)$", (text or was[1] or "").replace("\r", ""))
        _notes.setdefault(uid, []).append((time.time(), (title.group(1).strip() if title else "")[:80]))
        print(f"calendar: not saved behind ({status}) | {who}", flush=True)
    _blocks(uid, d.get("owner"))


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
    if d.get("spark"):   # answered in the panel itself, bound to this entry of its owner (sparkkalender.client)
        return sparkkalender.client(d["uid"], d["id"])
    auth = (d["user"], d.get("password", "")) if d.get("user") else None
    return netguard.client(netguard.USER, origin=d["url"], timeout=httpx.Timeout(20, connect=8), auth=auth,
                           follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"})
