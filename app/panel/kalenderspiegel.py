"""Spark-Kalender, Stufe 1 (Dominik 2026-10-19 „1a 2a“): a copy of every CalDAV calendar on the Spark itself.

Before, every look at a calendar month asked iCloud or Nextcloud for it (1 to 8 seconds). Now each calendar of an
address is mirrored here: the first time completely, from then on only what changed (WebDAV sync-collection with
its sync-token, RFC 6578; a server without it is compared by the etags of its objects). The page, Heute, the
assistant and the briefing read the copy in milliseconds; calendars.keep_fresh asks the server every SYNC_SECONDS
for the changes of the profiles active in the last day, and a change made here marks the copy for the next look.

- On the disk only encrypted (vault, the key stays in STATE and out of a backup); without the key nothing is written
  and the copy lives in memory only. STATE/kalender-spiegel/<calendar entry id>.json, deleted with the entry or
  the profile.
- Stage 2: a change from the page goes into the copy first (put_local) and to the server behind it
  (calendars._behind); taken() or undo() when the server answered. The assistant's changes still wait for the server.
- What comes from the server is data: kept and parsed as iCalendar text, never followed or run. At most MAX_ITEMS
  objects of at most MAX_TEXT characters per calendar.
- Live: how many calendars are mirrored, how many appointments, how long since the last comparison (numbers only).
"""
import asyncio
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from common import STATE, write_json

import vault

SYNC_SECONDS = 120        # a copy older than this asks the server for its changes before it answers
MAX_ITEMS = 5000          # objects kept per calendar
MAX_TEXT = 256 * 1024     # characters of one object
MULTIGET = 50             # objects fetched per request
FOREVER = 4102444800.0    # 2100-01-01: a repeating appointment has no last day
DIR = os.path.join(STATE, "kalender-spiegel")
CID = re.compile(r"c[0-9a-f]{8}")
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
DAV = "{DAV:}"
CALDATA = "{urn:ietf:params:xml:ns:caldav}calendar-data"

_mem = {}              # cid -> {calendar url: {"token", "at", "items": {href: [etag, text, lo, hi]}}}
_locks = {}            # (cid, calendar url) -> asyncio.Lock of the event loop it was made in
_without = {}          # (cid, calendar url) -> when it turned out the server lists neither changes nor etags
WITHOUT_SECONDS = 6 * 3600   # such a calendar is read the old way (a query per month); asked again after this


class Unsupported(Exception):
    """The server answers neither sync-collection nor a PROPFIND for etags: calendars reads it month by month."""
_file_lock = threading.Lock()
_last = [0.0]          # when the last comparison ended (Live)


def _file(cid):
    return os.path.join(DIR, cid + ".json")


def _load(cid):
    if cid in _mem:
        return _mem[cid]
    d = {}
    try:
        with open(_file(cid)) as f:
            raw = json.load(f)
        d = json.loads(vault.open_(raw.get("enc", "")) or "{}")
    except (OSError, ValueError, AttributeError):
        d = {}
    for cal in d.values():
        cal["at"] = 0.0   # read from the disk: compared with the server before it answers the first time
    _mem[cid] = d
    return d


def _save(cid):
    """The copy of one calendar entry, encrypted; nothing on the disk without the key."""
    if not vault.available():
        return
    text = vault.seal(json.dumps(_mem.get(cid) or {}, ensure_ascii=False, separators=(",", ":")))
    if not str(text).startswith(vault.PREFIX):
        return
    with _file_lock:
        write_json(_file(cid), {"enc": text}, mode=0o600, dir_mode=0o700)


def forget(cids):
    """Deletes the copies of these calendar entries (an entry removed, a profile deleted)."""
    for cid in cids:
        if not CID.fullmatch(str(cid)):
            continue
        _mem.pop(cid, None)
        for k in [k for k in _without if k[0] == cid]:
            _without.pop(k, None)
        with _file_lock:
            try:
                os.remove(_file(cid))
            except OSError:
                pass


def stale(cids):
    """Something changed here (an appointment saved, moved, deleted): the next look asks the server first."""
    for cid in cids:
        for cal in (_mem.get(cid) or {}).values():
            cal["at"] = 0.0


def _span(text):
    """(first, last) epoch seconds an object can touch; a repeating one reaches FOREVER. A day of slack on both
    sides covers floating times and all-day dates in any zone."""
    import datetime
    import icalendar
    lo, hi = FOREVER, 0.0
    try:
        cal = icalendar.Calendar.from_ical(text)
    except Exception:
        return 0.0, FOREVER
    for ev in cal.walk("VEVENT"):
        s, e = ev.get("DTSTART"), ev.get("DTEND")
        if s is None:
            continue
        s = s.dt
        e = e.dt if e is not None else s

        def epoch(x):
            if not isinstance(x, datetime.datetime):
                x = datetime.datetime.combine(x, datetime.time())
            if x.tzinfo is None:
                x = x.replace(tzinfo=datetime.timezone.utc)
            return x.timestamp()
        a, b = epoch(s), max(epoch(e), epoch(s))
        if ev.get("RRULE") is not None or ev.get("RDATE") is not None:
            b = FOREVER
        lo, hi = min(lo, a - 86400), max(hi, b + 86400)
    return (lo, hi) if hi else (0.0, FOREVER)


def _lock(cid, url):
    loop = asyncio.get_running_loop()
    k = (cid, url)
    held = _locks.get(k)
    if held is None or held[0] is not loop:
        held = _locks[k] = (loop, asyncio.Lock())
    return held[1]


async def texts(c, cid, url, start, end):
    """iCal texts of calendar `url` (of entry cid) that can touch [start, end) (aware datetimes), from the copy;
    compared with the server first when older than SYNC_SECONDS. c: the open netguard client of calendars._fetch."""
    if not CID.fullmatch(str(cid)):
        raise ValueError("unknown calendar entry")
    if time.time() - _without.get((cid, url), 0) < WITHOUT_SECONDS:
        raise Unsupported()
    async with _lock(cid, url):
        cal = _load(cid).setdefault(url, {"token": "", "at": 0.0, "items": {}})
        if time.time() - cal["at"] >= SYNC_SECONDS:
            await _sync(c, cid, url, cal)
    a, b = start.timestamp(), end.timestamp()
    return [x[1] for x in cal["items"].values() if x[2] < b and x[3] > a]


async def objects(c, cid, url, start, end):
    """[(href as the server writes it, etag, text)] like texts(), for finding one appointment to change."""
    await texts(c, cid, url, start, end)
    a, b = start.timestamp(), end.timestamp()
    cal = _load(cid).get(url) or {"items": {}}
    return [(h, x[0], x[1]) for h, x in cal["items"].items() if x[2] < b and x[3] > a]


def ready(cid, url):
    """True when the copy of this calendar is complete (a page change may go into it first)."""
    cal = _load(cid).get(url) if CID.fullmatch(str(cid or "")) else None
    return bool(cal and cal.get("done"))


def item(cid, url, href):
    """(etag, text) of one object in the copy, or None (not there, or the copy is not ready)."""
    cal = _load(cid).get(url) if CID.fullmatch(str(cid)) else None
    x = cal["items"].get(_path(href)) if cal and cal.get("done") else None
    return (x[0], x[1]) if x else None


# Stufe 2 (Dominik 2026-10-19 „3a“): a change from the page lands in the copy at once and goes to the server behind
# it (calendars._behind). Until the server took it, the object is "pending": a comparison neither drops it nor
# overwrites it. If the server refuses, the copy goes back and the next comparison starts from scratch (the
# server's version wins).
_pending = set()       # (cid, href) written here, not yet taken by the server
# A comparison that was already asking the server while the page changed an object (and the server took it before
# the comparison ended) holds that object's old state: it must not put it back, nor mark the copy as up to date
# (seen on a busy GitHub runner, V01.0.862: a changed appointment showed its old time again until the next look).
_seq = [0]             # counts the page's changes
_touch = {}            # (cid, href) -> the count at its last change here


def _touched(cid, h):
    _seq[0] += 1
    _touch[(cid, h)] = _seq[0]
    if len(_touch) > 2000:   # only recent changes matter: a comparison lasts seconds, not thousands of changes
        for k in [k for k, v in _touch.items() if v < _seq[0] - 1000]:
            del _touch[k]


def put_local(cid, url, href, text):
    """The object as the page just saved it (text) or deleted it (None). Returns how it was, for undo()."""
    cal = _load(cid).setdefault(url, {"token": "", "at": 0.0, "items": {}})
    h = _path(href)
    before = cal["items"].get(h)
    if text is None:
        cal["items"].pop(h, None)
    else:
        cal["items"][h] = ["", text, *_span(text)]
    _pending.add((cid, h))
    _touched(cid, h)
    return before


def taken(cid, url, href, tag=""):
    """The server took the change: the object's new etag (or "" until the next comparison brings it). The next look
    lists the whole calendar once (etags only): a server may leave out of its changes an object made and removed
    after the token the copy holds (RFC 6578 3.5), and this one was made here."""
    h = _path(href)
    _pending.discard((cid, h))
    _touched(cid, h)
    cal = _load(cid).get(url)
    if cal and h in cal["items"]:
        cal["items"][h][0] = tag or ""
    if cal:
        cal.update(token="", at=0.0)
        _save(cid)


def undo(cid, url, href, before):
    """The server refused: the copy goes back, and the next look compares everything anew (the server wins)."""
    h = _path(href)
    _pending.discard((cid, h))
    _touched(cid, h)
    cal = _load(cid).get(url)
    if not cal:
        return
    if before is None:
        cal["items"].pop(h, None)
    else:
        cal["items"][h] = before
    cal.update(token="", at=0.0)


def _status(resp):
    s = resp.findtext("d:status", "", NS) or resp.findtext("d:propstat/d:status", "", NS)
    m = re.search(r"\s(\d{3})\s", s + " ")
    return int(m.group(1)) if m else 200


async def _sync(c, cid, url, cal):
    """Asks the server what changed since the copy's token and fetches only that. One line when something changed
    or it failed; a quiet one when all stayed as it was."""
    t0, start = time.time(), _seq[0]
    try:
        tags, gone, token = await _changes(c, url, cal["token"])
        if tags is None:   # no sync-collection (or the token is no longer valid there): compare all etags
            tags, token = await _etags(c, url)
            gone = [h for h in cal["items"] if h not in tags]
        elif not cal["token"]:   # without a token the server lists every object: what it leaves out is gone
            gone = sorted(set(gone) | {h for h in cal["items"] if h not in tags})
        want = [h for h, tag in tags.items() if (cal["items"].get(h) or [None])[0] != tag][:MAX_ITEMS]
        got = {}
        for i in range(0, len(want), MULTIGET):
            got.update(await _multiget(c, url, want[i:i + MULTIGET]))
        spans = await asyncio.to_thread(lambda: {h: _span(t) for h, (_, t) in got.items()})
    except Unsupported:
        _without[(cid, url)] = time.time()
        print("calendar: mirror not possible | the server lists no changes, read by month", flush=True)
        raise
    except Exception as e:
        print(f"calendar: mirror failed ({type(e).__name__})", flush=True)
        raise
    late = {h for (c2, h), n in list(_touch.items()) if c2 == cid and n > start}
    gone = [h for h in gone if (cid, h) not in _pending and h not in late]
    got = {h: v for h, v in got.items() if (cid, h) not in _pending and h not in late}
    for h in gone:
        cal["items"].pop(h, None)
    for h, (tag, text) in got.items():
        if h in cal["items"] or len(cal["items"]) < MAX_ITEMS:
            cal["items"][h] = [tag, text, *spans[h]]
    full = not cal["token"] and not cal.get("done")
    # changed here meanwhile: the next look compares everything again instead of trusting this answer's token
    cal.update(token="" if late else token or "", at=0.0 if late else time.time(), done=True)
    _last[0] = time.time()
    if got or gone:
        _save(cid)
        what = "full" if full else "changed"
        print(f"calendar: mirror {what} | {len(got)} new or changed, {len(gone)} gone, {len(cal['items'])} kept, "
              f"{time.time() - t0:.1f} s", flush=True)


async def _report(c, url, body):
    return await c.request("REPORT", url, content=body, headers={"Depth": "1", "Content-Type": "application/xml"})


def _root(content):
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None


async def _changes(c, url, token):
    """({href: etag}, [href gone], new token) since token, or (None, None, None) when the server cannot say."""
    q = ('<?xml version="1.0"?><d:sync-collection xmlns:d="DAV:"><d:sync-token>' + escape(token) +
         '</d:sync-token><d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>')
    r = await _report(c, url, q)
    if r.status_code == 401:
        raise ValueError("the calendar server rejects the user name or password (401)")
    if r.status_code != 207:
        return None, None, None
    root = await asyncio.to_thread(_root, r.content)
    if root is None:
        return None, None, None
    tags, gone = {}, []
    for resp in root.findall("d:response", NS):
        href = (resp.findtext("d:href", "", NS) or "").strip()
        if not href or href.rstrip("/") == _path(url).rstrip("/"):
            continue
        if _status(resp) == 404:
            gone.append(href)
            continue
        tag = (resp.findtext("d:propstat/d:prop/d:getetag", "", NS) or "").strip()
        if tag and href.lower().endswith(".ics"):
            tags[href] = tag
    new = (root.findtext("d:sync-token", "", NS) or "").strip()
    if not new:
        return None, None, None
    return tags, gone, new


async def _etags(c, url):
    """({href: etag} of every object of the calendar, "") by PROPFIND: for servers without sync-collection."""
    q = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>'
    r = await c.request("PROPFIND", url, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    if r.status_code == 401:
        raise ValueError("the calendar server rejects the user name or password (401)")
    if r.status_code != 207:
        raise Unsupported()
    root = await asyncio.to_thread(_root, r.content)
    tags, members = {}, 0
    for resp in (root.findall("d:response", NS) if root is not None else []):
        href = (resp.findtext("d:href", "", NS) or "").strip()
        tag = (resp.findtext("d:propstat/d:prop/d:getetag", "", NS) or "").strip()
        members += bool(href) and href.rstrip("/") != _path(url).rstrip("/")
        if href and tag and href.lower().endswith(".ics"):
            tags[href] = tag
    if not members:   # no sync-collection and no member list either: it cannot be compared, asked by period instead
        raise Unsupported()
    return tags, ""


async def _multiget(c, url, hrefs):
    """{href: (etag, text)} of these objects."""
    q = ('<?xml version="1.0"?><c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
         '<d:prop><d:getetag/><c:calendar-data/></d:prop>' + "".join(f"<d:href>{escape(h)}</d:href>" for h in hrefs) +
         '</c:calendar-multiget>')
    r = await _report(c, url, q)
    if r.status_code == 401:
        raise ValueError("the calendar server rejects the user name or password (401)")
    if r.status_code != 207:
        raise ValueError(f"the calendar server answered {r.status_code}")
    root = await asyncio.to_thread(_root, r.content)
    out = {}
    for resp in (root.findall("d:response", NS) if root is not None else []):
        href = (resp.findtext("d:href", "", NS) or "").strip()
        text = resp.findtext("d:propstat/d:prop/c:calendar-data", "", NS) or ""
        tag = (resp.findtext("d:propstat/d:prop/d:getetag", "", NS) or "").strip()
        if href in hrefs and "BEGIN:VCALENDAR" in text and len(text) <= MAX_TEXT:
            out[href] = (tag, text)
    return out


def _path(url):
    m = re.match(r"\w+://[^/]+(/.*)?$", url)
    return (m.group(1) or "/") if m else url


def for_live(now=None):
    """Live (Kalender): mirrored calendars, appointments kept, minutes since the last comparison; numbers only."""
    now = time.time() if now is None else now
    cals = [cal for d in list(_mem.values()) for cal in d.values() if cal.get("done")]
    return {"calendars": len(cals), "items": sum(len(x["items"]) for x in cals),
            "ago": int((now - _last[0]) // 60) if _last[0] else None}
