"""Listen in Erinnerungen (plan listen-teilen.md Stufe 3, Dominik 2026-10-20 „5a“): the profile's Spark lists
(Einkauf, Aufgaben, own lists) as task lists (VTODO) of the Spark's CalDAV server (kalenderserver.py), so the
iPhone's Reminders app (or Thunderbird, DAVx5 with tasks.org) shows them and changes them both ways: ticking off,
putting on and deleting there changes the list on the Spark, and the other way round.

Who may: the function listdav (features.py, admin switch chat.tasks_dav, off) on top of Listen and the calendar
server; every profile the admin did not block, never guests. The same door as the calendars: the profile's app
password, its own path only, Mein Notaus, guard.RATE "caldav" (kalenderserver.caldav does all of it before here).

- Only the profile's own lists that live on the Spark (a list kept in a calendar account is there already) and
  never another profile's list, also not a shared one.
- What comes in is data: one VTODO per object, only its summary (cut to tasks.clean, at most 400 characters),
  whether it is done, its date and time (DUE), note (DESCRIPTION, tasks.NOTE_MAX) and priority (PRIORITY) are taken
  (Apple-Stil Stufe 4); the rest of the object is not kept. At most tasks.MAX_ITEMS entries. The time goes out as
  floating local time, as the person typed it; a time with zone comes in in the profile's zone.
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
import profiles
import sparkkalender
import tasks
from common import DayCounter

PART = "liste-"                                    # /caldav/<uid>/liste-<list id>/
NAME = re.compile(r"[A-Za-z0-9._@-]{1,200}\.ics")
MAX_TEXT = 64 * 1024                               # characters of one object
_count = DayCounter()                              # per day: "gespeichert" (changes from calendar apps)
PRIO_OUT = {1: 9, 2: 5, 3: 1}                      # tasks.PRIOS low, medium, high as iCalendar PRIORITY (1 = highest)


def prio_in(n):
    """tasks.PRIOS of an iCalendar PRIORITY: 1-4 high, 5 medium, 6-9 low, 0 or anything else none."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return 0
    return 3 if 1 <= n <= 4 else 2 if n == 5 else 1 if 6 <= n <= 9 else 0


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
    if x.get("due") and x.get("at"):   # date and time: floating, the wall clock time the person set
        todo.add("due", datetime.datetime.fromisoformat(f"{x['due']}T{x['at']}"))
    elif x.get("due"):   # „bis“ (a meeting's task): a date, so Reminders shows it on that day
        todo.add("due", datetime.date.fromisoformat(x["due"]))
    if x.get("note"):
        todo.add("description", x["note"])
    if x.get("prio"):
        todo.add("priority", PRIO_OUT[x["prio"]])
    if x.get("done"):
        todo.add("status", "COMPLETED")
        todo.add("completed", _stamp(x["done"]))
        todo.add("percent-complete", 100)
    else:
        todo.add("status", "NEEDS-ACTION")
    cal.add_component(todo)
    return cal.to_ical().decode()


def _ctag(items):
    raw = "|".join(f"{n}:{tasks.show(x)}:{x.get('done', 0)}:{x.get('due', '')}:{x.get('at', '')}:{x.get('prio', 0)}:"
                   f"{hashlib.sha1(x.get('note', '').encode('utf-8', 'replace')).hexdigest()[:8]}"
                   for n, x in sorted(items.items()))
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def collection(uid, part, li, base):
    """The PROPFIND answer for one list as a task collection (also for the calendar home, kalenderserver.py)."""
    title = (li["icon"] + " " if li.get("icon") else "") + li["name"]
    return sparkkalender._resp(base, "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                                     f"<d:displayname>{escape(title)}</d:displayname>"
                                     '<c:supported-calendar-component-set><c:comp name="VTODO"/>'
                                     "</c:supported-calendar-component-set>"
                                     f"<cs:getctag>{_ctag(_entries(uid, li['id']))}</cs:getctag>" + sparkkalender.PROPS)


def _read(body, zone=None):
    """{"summary", "done", "uid", "due", "at", "note", "prio"} of the one VTODO in a calendar object, or None (due a
    date, at a time „HH:MM“ in zone, "" without)."""
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
    due, at = tasks.todo_due_at(t, zone)
    due = due if tasks.due_ok(due) else ""
    note = re.sub(r"[\x00-\x08\x0b-\x1f]", "", str(t.get("DESCRIPTION", ""))).strip()[:tasks.NOTE_MAX]
    return {"summary": summary, "done": done, "uid": re.sub(r"[^A-Za-z0-9._@-]", "", str(t.get("UID", "")))[:200],
            "due": due, "at": at if due and tasks.AT_RE.fullmatch(at or "") else "", "note": note,
            "prio": prio_in(t.get("PRIORITY"))}


def _put(uid, lid, name, body, headers):
    import chat
    got = _read(body, chat.user_zone(profiles.settings(uid).get("tz", "")))
    if not got:
        return 415, "failed (not a task)"
    summary, done, ref, due = got["summary"], got["done"], got["uid"], got["due"]
    info = {k: got[k] for k in ("at", "note", "prio") if got[k]}
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
                      "src": "erinnerungen", "dav": name, "pos": tasks._last_pos(d, lid) + 1},
                     **({"qty": qty} if qty else {}), **({"dav_uid": ref} if ref else {}),
                     **({"due": due} if due else {}), **(info if due else {k: v for k, v in info.items() if k != "at"}))
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
            for k in ("at", "note", "prio"):   # the same for time, note and priority
                if info.get(k) and (k != "at" or due):
                    have[k] = info[k]
                else:
                    have.pop(k, None)
            what = "edit"
            if done and not have.get("done"):
                have["done"], have["done_by"], what = now, uid, "done"
            elif not done and have.get("done"):
                have.pop("done", None)
                have.pop("done_by", None)
                what = "undo"
            x = have
            tasks._remind(uid, x, uid)   # a reminder set on the page follows the new time, ticked off it goes
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
