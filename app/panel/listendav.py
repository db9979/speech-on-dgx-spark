"""Listen in Erinnerungen (plan listen-teilen.md Stufe 3, Dominik 2026-10-20 „5a“): the profile's Spark lists
(Einkauf, Aufgaben, own lists) as task lists (VTODO) of the Spark's CalDAV server (kalenderserver.py), so the
iPhone's Reminders app (or Thunderbird, DAVx5 with tasks.org) shows them and changes them both ways: ticking off,
putting on and deleting there changes the list on the Spark, and the other way round.

Who may: the function listdav (features.py, admin switch chat.tasks_dav, off) on top of Listen and the calendar
server; every profile the admin did not block, never guests. The same door as the calendars: the profile's app
password, its own path only, Mein Notaus, guard.RATE "caldav" (kalenderserver.caldav does all of it before here).

- Only the profile's own lists that live on the Spark (a list kept in a calendar account is there already) and
  never another profile's list, also not a shared one.
- What comes in is data: one VTODO per object, only its summary (cut to tasks.clean, at most 400 characters) and
  whether it is done are taken; the rest of the object is not kept. At most tasks.MAX_ITEMS entries.
- An entry from Reminders is put on with the source „iPhone Erinnerungen“; it keeps the app's object name and UID
  so the app finds it again. Deleting there deletes it on the Spark (the owner's own list), ticking off keeps it
  under „Zuletzt erledigt“ for tasks.KEEP_DONE like on the page.
- Journal: the lines of tasks.py („tasks: add einkauf | 1 entries | …“), fixed words and numbers; Live: changes
  from calendar apps today.
"""
import datetime
import hashlib
import os
import re
import time
from xml.sax.saxutils import escape

import icalendar

import features
import sparkkalender
import tasks
from common import DayCounter

PART = "liste-"                                    # /caldav/<uid>/liste-<list id>/
NAME = re.compile(r"[A-Za-z0-9._@-]{1,200}\.ics")
MAX_TEXT = 64 * 1024                               # characters of one object
_count = DayCounter()                              # per day: "gespeichert" (changes from calendar apps)


def collections(uid):
    """[(path part, list)] of the profile's lists a calendar app sees: its own lists on the Spark."""
    if not features.allowed("listdav", uid):
        return []
    d = tasks._load(uid)
    return [(PART + li["id"], li) for li in tasks.lists_of(uid, d) if li["id"] not in d["targets"]]


def _name(x):
    return x.get("dav") or f"{x['id']}.ics"


def _entries(uid, lid, d=None):
    """{object name: entry} of the list: the open entries and the ones ticked off in the last tasks.KEEP_DONE."""
    d = d or tasks._load(uid)
    return {_name(x): x for x in d["items"] if x["list"] == lid and not x.get("sent")}


def _stamp(t):
    return datetime.datetime.fromtimestamp(t or 0, datetime.timezone.utc)


def _ics(x):
    cal = icalendar.Calendar()
    cal.add("prodid", "-//speech-on-dgx-spark//Listen//DE")
    cal.add("version", "2.0")
    todo = icalendar.Todo()
    todo.add("uid", x.get("dav_uid") or f"{x['id']}@speech-spark")
    todo.add("dtstamp", _stamp(x.get("done") or x.get("t")))
    todo.add("created", _stamp(x.get("t")))
    todo.add("summary", tasks.show(x))
    if x.get("due"):   # „bis“ (a meeting's task): a date, so Reminders shows it on that day
        todo.add("due", datetime.date.fromisoformat(x["due"]))
    if x.get("done"):
        todo.add("status", "COMPLETED")
        todo.add("completed", _stamp(x["done"]))
        todo.add("percent-complete", 100)
    else:
        todo.add("status", "NEEDS-ACTION")
    cal.add_component(todo)
    return cal.to_ical().decode()


def _ctag(items):
    raw = "|".join(f"{n}:{tasks.show(x)}:{x.get('done', 0)}:{x.get('due', '')}" for n, x in sorted(items.items()))
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def collection(uid, part, li, base):
    """The PROPFIND answer for one list as a task collection (also for the calendar home, kalenderserver.py)."""
    title = (li["icon"] + " " if li.get("icon") else "") + li["name"]
    return sparkkalender._resp(base, "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                                     f"<d:displayname>{escape(title)}</d:displayname>"
                                     '<c:supported-calendar-component-set><c:comp name="VTODO"/>'
                                     "</c:supported-calendar-component-set>"
                                     f"<cs:getctag>{_ctag(_entries(uid, li['id']))}</cs:getctag>" + sparkkalender.PROPS)


def _read(body):
    """(summary, done, uid, due) of the one VTODO in a calendar object, or None (due: only the date, "" without)."""
    text = (body or b"").decode("utf-8", "replace")
    if len(text) > MAX_TEXT:
        return None
    try:
        todos = list(icalendar.Calendar.from_ical(text).walk("VTODO"))
    except Exception:
        return None
    if len(todos) != 1:
        return None
    t = todos[0]
    summary = tasks.clean(str(t.get("SUMMARY", "")))[:400]
    if not summary:
        return None
    done = str(t.get("STATUS", "")).upper() == "COMPLETED" or bool(t.get("COMPLETED"))
    due = tasks._todo_due(t)
    return summary, done, re.sub(r"[^A-Za-z0-9._@-]", "", str(t.get("UID", "")))[:200], due if tasks.due_ok(due) else ""


def _put(uid, lid, name, body, headers):
    got = _read(body)
    if not got:
        return 415, "failed (not a task)"
    summary, done, ref, due = got
    with tasks._lock:
        d = tasks._load(uid)
        have = _entries(uid, lid, d).get(name)
        match, none = headers.get("If-Match"), headers.get("If-None-Match")
        if (match and (have is None or match.strip() != sparkkalender._etag(_ics(have)))) or (none == "*" and have is not None):
            return 412, "refused (changed meanwhile)"
        now = int(time.time())
        if have is None:
            if sum(1 for x in d["items"] if not x.get("sent")) >= tasks.MAX_ITEMS:
                return 507, "refused (full)"
            text, qty = tasks.split_qty(summary)
            x = dict({"id": os.urandom(5).hex(), "list": lid, "text": text or summary, "t": now, "by": uid,
                      "src": "erinnerungen", "dav": name}, **({"qty": qty} if qty else {}), **({"dav_uid": ref} if ref else {}),
                     **({"due": due} if due else {}))
            if done:
                x["done"], x["done_by"] = now, uid
            d["items"].append(x)
            what = "add"
        else:
            if summary != tasks.show(have):
                have["text"], qty = tasks.split_qty(summary)
                have["text"] = have["text"] or summary
                have.pop("qty", None)
                if qty:
                    have["qty"] = qty
            if due:                 # the date set or moved in Reminders; taken away there: gone here too
                have["due"] = due
            else:
                have.pop("due", None)
            what = "edit"
            if done and not have.get("done"):
                have["done"], have["done_by"], what = now, uid, "done"
            elif not done and have.get("done"):
                have.pop("done", None)
                have.pop("done_by", None)
                what = "undo"
            x = have
        tasks._save(uid, d)
    tasks._log(what, lid, uid, "1 entries from calendar app")
    if what in ("done", "undo"):
        tasks.card_follows(uid, lid, [x["id"]], what)
    if what != "edit":
        tasks._count.bump(what, 1)
    if what == "add":
        tasks._tell(uid, lid, uid, 1)
    return (201 if have is None else 204), sparkkalender._etag(_ics(x))


def _delete(uid, lid, name, headers):
    with tasks._lock:
        d = tasks._load(uid)
        have = _entries(uid, lid, d).get(name)
        if have is None:
            return 404
        match = headers.get("If-Match")
        if match and match.strip() != sparkkalender._etag(_ics(have)):
            return 412
        d["items"] = [x for x in d["items"] if x is not have]
        tasks._save(uid, d)
    tasks._log("delete", lid, uid, "1 entries from calendar app")
    tasks._count.bump("delete", 1)
    tasks.card_follows(uid, lid, [have["id"]], "delete")
    return 204


def serve(uid, part, method, name, headers, body, base):
    """(status, headers, body) of one CalDAV request to the list behind part („liste-einkauf“) of profile uid; the
    caller (kalenderserver.caldav) has checked the login, the path's profile and the Notaus."""
    li = dict(collections(uid)).get(part)
    if li is None:
        return 404, {}, b""
    lid = li["id"]
    method = method.upper()
    items = _entries(uid, lid)
    item = lambda n, x, data: sparkkalender._resp(
        base + n, f"<d:getetag>{escape(sparkkalender._etag(_ics(x)))}</d:getetag>"
                  "<d:getcontenttype>text/calendar; charset=utf-8</d:getcontenttype>"
                  + (f"<c:calendar-data>{escape(_ics(x))}</c:calendar-data>" if data else ""))
    if not name:
        if method == "PROPFIND":
            out = [collection(uid, part, li, base)]
            if headers.get("Depth", "0") == "1":
                out += [item(n, x, False) for n, x in items.items()]
            return sparkkalender._ms(out)
        if method == "REPORT":
            if b"sync-collection" in (body or b""):
                return 403, {}, b""   # not offered: the app compares etags instead
            if b"calendar-multiget" in (body or b""):
                want = [h.decode("utf-8", "replace").rsplit("/", 1)[-1]
                        for h in re.findall(rb"<(?:\w+:)?href>\s*([^<\s]+)\s*<", body)[:1000]]
                return sparkkalender._ms([item(n, items[n], True) if n in items else
                                          f"<d:response><d:href>{escape(base + n)}</d:href>"
                                          "<d:status>HTTP/1.1 404 Not Found</d:status></d:response>"
                                          for n in dict.fromkeys(want) if NAME.fullmatch(n)])
            return sparkkalender._ms([item(n, x, True) for n, x in items.items()])
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
            return sparkkalender._ms([item(name, have, False)])
        text = _ics(have)
        return 200, {"ETag": sparkkalender._etag(text), "Content-Type": "text/calendar; charset=utf-8"}, \
            text.encode() if method == "GET" else b""
    if method == "PUT":
        status, etag = _put(uid, lid, name, body, headers)
        if status >= 300:
            tasks._log("add", lid, uid, etag)
            return status, {}, b""
        _count.bump("gespeichert")
        return status, {"ETag": etag}, b""
    if method == "DELETE":
        status = _delete(uid, lid, name, headers)
        if status < 300:
            _count.bump("gespeichert")
        else:
            tasks._log("delete", lid, uid, f"refused ({status})")
        return status, {}, b""
    return 405, {}, b""


def for_live():
    """Live (Listen): changes from calendar apps today; a number only."""
    return {"on": features.admin_on("listdav"), "saved": _count.counts().get("gespeichert", 0)}
