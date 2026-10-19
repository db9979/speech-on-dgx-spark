"""Spark-Kalender, Stufe 3 (Dominik 2026-10-19 „5a“): a calendar that lives only on the Spark, without iCloud,
Google or Nextcloud.

A profile adds it under Ich → Kalender („Spark-Kalender anlegen“). It is an ordinary entry of calendars.py with
"spark": True; its address https://spark.invalid/<entry id>/ never reaches the network: client() answers every
request in the panel itself (httpx.MockTransport) with the small part of CalDAV that calendars.py speaks (PROPFIND,
REPORT calendar-query, GET, PUT, DELETE with etags). So the page, the assistant, the briefing, Heute, Kalender
teilen and „Mach das rückgängig“ work with it unchanged. Stufe 4 (the Spark as a CalDAV server for the iPhone's
own calendar app) will answer through the same handler.

- The client is bound to one entry of one profile (owner uid, entry id): the path of a request never picks
  another calendar, a request for another entry id is 404. A calendar shared by its owner is read with the owner's
  uid, like every shared calendar (calendars.reading).
- Stored in the profile folder (users/<uid>/spark-kalender.json), only encrypted (vault); without the key the
  calendar cannot be made (create() refuses), so no appointment ever lives in memory only. It moves and is backed
  up with the profile; removing the entry or the profile deletes its appointments.
- What is written is checked: an iCalendar text with at least one VEVENT, at most MAX_TEXT characters, at most
  MAX_ITEMS appointments per calendar, an object name of letters, digits and „._@-“ only. Texts are data, never
  followed or run.
- Journal: fixed words and numbers; Live: how many Spark calendars and appointments.
"""
import datetime
import hashlib
import json
import os
import re
import threading
from xml.sax.saxutils import escape

import httpx
import icalendar

import kalenderspiegel
import profiles
import vault
from common import write_json

HOST = "spark.invalid"            # RFC 6761: never resolves, so this address can never mean a server outside
MAX_ITEMS = 5000                  # appointments per Spark calendar
MAX_TEXT = 256 * 1024             # characters of one appointment
NAME = re.compile(r"[A-Za-z0-9._@-]{1,200}\.ics")
FILE = "spark-kalender.json"

_mem = {}                         # uid -> {entry id: {"items": {name: [etag, text, lo, hi]}, "ctag": int}}
_lock = threading.Lock()


def url(cid):
    return f"https://{HOST}/{cid}/"


def is_spark(address):
    m = re.match(r"\w+://([^/:]+)", str(address or ""))
    return bool(m and m.group(1).lower().rstrip(".") == HOST)


def _file(uid):
    return profiles._path(uid, FILE)


def _load(uid):
    with _lock:
        if uid in _mem:
            return _mem[uid]
        d = {}
        try:
            with open(_file(uid)) as f:
                raw = json.load(f)
            d = json.loads(vault.open_(raw.get("enc", "")) or "{}")
        except (OSError, ValueError, AttributeError):
            d = {}
        d = {k: v for k, v in (d if isinstance(d, dict) else {}).items()
             if kalenderspiegel.CID.fullmatch(k) and isinstance(v, dict)}
        for cal in d.values():
            cal.setdefault("items", {})
            cal.setdefault("ctag", 0)
        _mem[uid] = d
        return d


def _save(uid):
    text = vault.seal(json.dumps(_mem.get(uid) or {}, ensure_ascii=False, separators=(",", ":")))
    if not str(text).startswith(vault.PREFIX):
        raise ValueError("the Spark calendar needs the Spark's key (vault) to be saved")
    with _lock:
        write_json(_file(uid), {"enc": text}, mode=0o600, dir_mode=0o700)


def create(uid, name):
    """A new, empty Spark calendar of the profile: the entry for calendars.add (it saves the entry)."""
    if not vault.available():
        raise ValueError("the Spark calendar needs the Spark's key (vault); without it nothing could be kept")
    cid = "c" + os.urandom(4).hex()
    _load(uid)[cid] = {"items": {}, "ctag": 0}
    _save(uid)
    print(f"calendar: spark calendar made | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return {"id": cid, "name": (str(name or "").strip()[:60] or "Spark-Kalender"), "url": url(cid), "user": "",
            "password": "", "spark": True}


def forget(uid, cids):
    """The appointments of these Spark calendars go (the entry removed, the profile deleted)."""
    d = _load(uid)
    gone = [c for c in cids if c in d]
    for c in gone:
        d.pop(c, None)
    if gone:
        _save(uid)
        print(f"calendar: spark calendar deleted | {len(gone)} | {profiles.log_name(profiles.by_id(uid))}", flush=True)


def drop_profile(uid):
    """The profile folder is gone: nothing of it stays in memory."""
    with _lock:
        _mem.pop(uid, None)


def client(uid, cid, **kw):
    """An httpx.AsyncClient whose every request is answered by the Spark calendar cid of profile uid; no network."""
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda req: handle(uid, cid, req)), **kw)


# ---------------------------------------------------------------- the CalDAV answers
def _ms(responses):
    """(status, headers, body) of a WebDAV multistatus."""
    body = ('<?xml version="1.0" encoding="utf-8"?><d:multistatus xmlns:d="DAV:" '
            'xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/">' + "".join(responses)
            + "</d:multistatus>")
    return 207, {"Content-Type": "application/xml; charset=utf-8"}, body.encode()


def _resp(href, props):
    return f"<d:response><d:href>{escape(href)}</d:href><d:propstat><d:prop>{props}</d:prop>" \
           "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"


def _etag(text):
    return '"' + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:20] + '"'


def _valid(text):
    if len(text) > MAX_TEXT:
        return False
    try:
        cal = icalendar.Calendar.from_ical(text)
    except Exception:
        return False
    return any(True for _ in cal.walk("VEVENT"))


def _range(body):
    m = re.search(rb'time-range[^>]*?start="(\d{8}T\d{6}Z)"[^>]*?end="(\d{8}T\d{6}Z)"', body or b"")
    if not m:
        return 0.0, kalenderspiegel.FOREVER
    f = lambda s: datetime.datetime.strptime(s.decode(), "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
    return f(m.group(1)), f(m.group(2))


def handle(uid, cid, req):
    """One CalDAV request to the Spark calendar cid of profile uid (bound: the path names only this calendar)."""
    m = re.fullmatch(r"/([^/]+)/([^/]*)", req.url.path)
    if req.url.host != HOST or not m or m.group(1) != cid:
        return httpx.Response(404)
    status, head, body = serve(uid, cid, req.method, m.group(2), req.headers, req.content, f"/{cid}/")
    return httpx.Response(status, headers=head, content=body)


PROPS = ("<d:current-user-privilege-set><d:privilege><d:read/></d:privilege><d:privilege><d:write/></d:privilege>"
         "<d:privilege><d:write-content/></d:privilege><d:privilege><d:bind/></d:privilege><d:privilege><d:unbind/>"
         "</d:privilege></d:current-user-privilege-set><d:supported-report-set><d:supported-report><d:report>"
         "<c:calendar-query/></d:report></d:supported-report><d:supported-report><d:report><c:calendar-multiget/>"
         "</d:report></d:supported-report></d:supported-report-set>")


def collection(cal, base, title=""):
    """The PROPFIND answer for one Spark calendar as a collection (also for the calendar home, kalenderserver.py)."""
    return _resp(base, "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                       f"<d:displayname>{escape(title)}</d:displayname>"
                       '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
                       f"<cs:getctag>{cal['ctag']}</cs:getctag>" + PROPS)


def calendar(uid, cid):
    """The stored calendar (ctag, items) or None."""
    return _load(uid).get(cid)


def serve(uid, cid, method, name, headers, body, base, title=""):
    """(status, headers, body) of one CalDAV request to the Spark calendar cid of profile uid; name: the object
    („x.ics“) or "" for the calendar itself; base: the calendar's path in the answer's hrefs."""
    cal = _load(uid).get(cid)
    if cal is None:
        return 404, {}, b""
    method = method.upper()
    items = cal["items"]
    item = lambda n, x, data: _resp(base + n, f"<d:getetag>{escape(x[0])}</d:getetag>"
                                              '<d:getcontenttype>text/calendar; charset=utf-8</d:getcontenttype>'
                                              + (f"<c:calendar-data>{escape(x[1])}</c:calendar-data>" if data else ""))
    if not name:
        if method == "PROPFIND":
            out = [collection(cal, base, title)]
            if headers.get("Depth", "0") == "1":
                out += [item(n, x, False) for n, x in items.items()]
            return _ms(out)
        if method == "REPORT":
            if b"sync-collection" in (body or b""):
                return 403, {}, b""   # not offered (supported-report-set): the client compares etags instead
            if b"calendar-multiget" in (body or b""):
                want = [h.rsplit("/", 1)[-1] for h in re.findall(rb"<(?:\w+:)?href>\s*([^<\s]+)\s*<", body)[:1000]
                        for h in [h.decode("utf-8", "replace")]]
                return _ms([item(n, items[n], True) if n in items else
                            f"<d:response><d:href>{escape(base + n)}</d:href><d:status>HTTP/1.1 404 Not Found</d:status></d:response>"
                            for n in dict.fromkeys(want) if NAME.fullmatch(n)])
            a, b = _range(body)
            return _ms([item(n, x, True) for n, x in items.items() if x[2] < b and x[3] > a])
        if method == "OPTIONS":
            return 200, {"DAV": "1, 2, calendar-access", "Allow": "OPTIONS, PROPFIND, REPORT, GET, PUT, DELETE"}, b""
        return 405, {}, b""
    if not NAME.fullmatch(name):
        return 404, {}, b""
    have = items.get(name)
    if method in ("GET", "HEAD", "PROPFIND"):
        if have is None:
            return 404, {}, b""
        if method == "PROPFIND":
            return _ms([item(name, have, False)])
        return 200, {"ETag": have[0], "Content-Type": "text/calendar; charset=utf-8"}, have[1].encode() if method == "GET" else b""
    match, none = headers.get("If-Match"), headers.get("If-None-Match")
    if (match and (have is None or match.strip() != have[0])) or (none == "*" and have is not None):
        return 412, {}, b""
    if method == "DELETE":
        if have is None:
            return 404, {}, b""
        items.pop(name, None)
    elif method == "PUT":
        text = (body or b"").decode("utf-8", "replace")
        if not _valid(text):
            return 415, {}, b""
        if have is None and len(items) >= MAX_ITEMS:
            return 507, {}, b""
        items[name] = [_etag(text), text, *kalenderspiegel._span(text)]
    else:
        return 405, {}, b""
    cal["ctag"] += 1
    try:
        _save(uid)
    except ValueError:
        if have is None:
            items.pop(name, None)
        else:
            items[name] = have
        return 507, {}, b""
    if method == "DELETE":
        return 204, {}, b""
    return (201 if have is None else 204), {"ETag": items[name][0]}, b""


def for_live():
    """Live (Kalender): Spark calendars and their appointments of all profiles; numbers only (read once, then kept)."""
    for uid in profiles.user_ids():
        if uid not in _mem and os.path.exists(_file(uid)):
            _load(uid)
    cals = [c for d in list(_mem.values()) for c in d.values()]
    return {"calendars": len(cals), "items": sum(len(c["items"]) for c in cals)}
