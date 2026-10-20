"""Kalender wie Apple Kalender (Apple-Stil „4a“ „5a“, Dominik 2026-10-20): the fields of an appointment the page
Kalender and the iPhone app set (place, all day, start and end, repeat, alert, people, note, link) and the changes of
a repeating appointment, „Nur dieser Termin“ or „Alle künftigen“, on its iCal text. Pure functions without the
network: calendars.py finds the object, writes it (the Spark's copy first, the server behind) and keeps the old text
for „Rückgängig“.

People are a list inside the appointment (ATTENDEE with SCHEDULE-AGENT=CLIENT): no calendar server sends an
invitation for them, and the Spark sends none either (invitations later, with an admin switch of their own).
Everything read from a calendar is data: names and addresses only as text."""
import datetime
import re
import zoneinfo

import icalendar
import recurring_ical_events

# the repeat choices of the page (Apple: Nie, Täglich, Wöchentlich, Alle 2 Wochen, Monatlich, Jährlich); a rule the
# page cannot show this way is "custom": it stays as it is
RULES = {"daily": ("DAILY", 1), "weekly": ("WEEKLY", 1), "biweekly": ("WEEKLY", 2), "monthly": ("MONTHLY", 1),
         "yearly": ("YEARLY", 1)}
_SIMPLE = {"FREQ", "INTERVAL", "UNTIL", "WKST"}
ALARMS = (5, 10, 15, 30, 60, 120, 1440, 2880)   # minutes before the start the page offers; 0: no alert
ALARM_MAX = 40320                               # four weeks: an alert read from a calendar may be any of these
PEOPLE_MAX = 20
UNTIL_YEARS = 10
SCOPES = ("one", "future")
_MAIL = re.compile(r"[^@\s<>\"(),;:\\]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
UTC = datetime.timezone.utc


# ---------------------------------------------------------------- reading an appointment
def rule_of(ev):
    """(word, until as YYYY-MM-DD or "") of the appointment's repeat rule; ("", "") without one."""
    r = ev.get("RRULE")
    if r is None:
        return "", ""
    if isinstance(r, list):
        return "custom", ""
    freq = str((r.get("FREQ") or [""])[0]).upper()
    try:
        n = int((r.get("INTERVAL") or [1])[0] or 1)
    except (TypeError, ValueError):
        n = 0
    word = next((w for w, v in RULES.items() if v == (freq, n)), "")
    if not word or {str(k).upper() for k in r} - _SIMPLE:
        return "custom", ""
    u = (r.get("UNTIL") or [None])[0]
    return word, ((u.date() if isinstance(u, datetime.datetime) else u).isoformat() if u else "")


def alarm_of(ev):
    """Minutes before the start of the appointment's first alert (relative to its start), 0 without one."""
    for a in ev.walk("VALARM"):
        t = a.get("TRIGGER")
        td = getattr(t, "dt", None)
        if isinstance(td, datetime.timedelta) and td <= datetime.timedelta(0) \
                and str(t.params.get("RELATED", "START")).upper() == "START":
            return min(ALARM_MAX, int(round(-td.total_seconds() / 60))) or 0
    return 0


def people_of(ev):
    """[{"name", "mail"}] of the appointment's people (ATTENDEE), at most PEOPLE_MAX, only valid addresses."""
    v = ev.get("ATTENDEE")
    out = []
    for a in (v if isinstance(v, list) else [v] if v is not None else []):
        mail = re.sub(r"(?i)^mailto:", "", str(a)).strip()
        if not _MAIL.fullmatch(mail):
            continue
        name = _CTRL.sub("", str(getattr(a, "params", {}).get("CN", "") or "")).strip()[:80]
        out.append({"name": name, "mail": mail[:254]})
    return out[:PEOPLE_MAX]


# ---------------------------------------------------------------- the page's fields, checked
def people(v):
    """The page's people: "Anna <anna@example.org>", "anna@example.org" or {"name", "mail"}; checked, each address
    once, at most PEOPLE_MAX. A wrong address is refused (ValueError), never guessed."""
    out, seen = [], set()
    for p in (v if isinstance(v, list) else [])[:PEOPLE_MAX + 1]:
        if isinstance(p, dict):
            name, mail = str(p.get("name") or ""), str(p.get("mail") or "")
        else:
            m = re.fullmatch(r"\s*(.*?)\s*<\s*([^<>]+?)\s*>\s*", str(p))
            name, mail = (m.group(1), m.group(2)) if m else ("", str(p))
        mail = mail.strip()
        if not _MAIL.fullmatch(mail):
            raise ValueError("a person needs a mail address like anna@example.org")
        if mail.lower() in seen:
            continue
        seen.add(mail.lower())
        out.append({"name": _CTRL.sub("", name).strip().strip('"')[:80], "mail": mail[:254]})
    if len(out) > PEOPLE_MAX:
        raise ValueError(f"at most {PEOPLE_MAX} people")
    return out


def fields(body, start):
    """The page's repeat, alert, people, note and link next to calendars.page_item's title and times: checked, as
    item keys, only those the body names (an older app sends none of them: a change keeps what the calendar has).
    start: the appointment's start (the end of a repetition lies after it)."""
    out = {}
    rule = str(body.get("rule") or "")
    if rule not in RULES and rule not in ("", "custom"):
        raise ValueError("repeat must be one of " + ", ".join(RULES))
    until = str(body.get("until") or "")[:10] if rule else ""
    if until:
        try:
            u = datetime.date.fromisoformat(until)
        except ValueError:
            raise ValueError("the end of the repetition must be a date like 2026-12-31")
        if not start.date() <= u <= start.date().replace(year=start.year + UNTIL_YEARS):
            raise ValueError(f"the repetition ends after the start, within {UNTIL_YEARS} years")
    if "rule" in body:
        out.update(rule=rule, until=until)
    if "alarm" in body:
        try:
            alarm = int(body.get("alarm") or 0)
        except (TypeError, ValueError):
            raise ValueError("the alert is minutes before the start")
        if not 0 <= alarm <= ALARM_MAX:
            raise ValueError("the alert is minutes before the start")
        out["alarm"] = alarm
    if "note" in body:
        out["note"] = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(body.get("note") or "")).replace("\r", "").strip()[:2000]
    if "link" in body:
        link = str(body.get("link") or "").strip()
        if link and not re.fullmatch(r"https?://[^\s<>\"]{1,300}", link):
            raise ValueError("the link must start with https:// or http://")
        out["link"] = link
    if "people" in body:
        out["people"] = people(body.get("people"))
    return out


# ---------------------------------------------------------------- writing an appointment
def _people_same(ev, want):
    return sorted(p["mail"].lower() for p in people_of(ev)) == sorted(p["mail"].lower() for p in want or [])


def fill(ev, item):
    """The appointment's fields from a checked item (calendars.page_item): title, place, note, link, start and end
    (with a repeat rule in the item's own zone, so it stays at its hour across summer time), alert and people. An
    alert or a list of people that did not change stays as the calendar had it (several alerts, answers)."""
    keep_alarm = "alarm" not in item or alarm_of(ev) == int(item.get("alarm") or 0)
    keep_people = "people" not in item or _people_same(ev, item.get("people"))
    for k in ("SUMMARY", "LOCATION", "DTSTART", "DTEND", "DURATION", "DTSTAMP") + (("DESCRIPTION",) if "note" in item else ()) + \
            (("URL",) if "link" in item else ()) + (() if keep_people else ("ATTENDEE",)):
        ev.pop(k, None)
    ev.add("summary", item["title"])
    if item.get("location"):
        ev.add("location", item["location"])
    if item.get("note"):
        ev.add("description", item["note"])
    if item.get("link"):
        ev.add("url", item["link"])
    s, e = datetime.datetime.fromisoformat(item["start"]), datetime.datetime.fromisoformat(item["end"])
    if item.get("allday"):
        ev.add("dtstart", s.date())
        ev.add("dtend", e.date())
    else:
        zone = _zone(item.get("zone")) if ev.get("RRULE") is not None or item.get("rule") else None
        ev.add("dtstart", s.astimezone(zone) if zone else s.astimezone(UTC))
        ev.add("dtend", e.astimezone(zone) if zone else e.astimezone(UTC))
    ev.add("dtstamp", datetime.datetime.now(UTC))
    if not keep_alarm:
        ev.subcomponents = [c for c in ev.subcomponents if c.name != "VALARM"]
        if item.get("alarm"):
            al = icalendar.Alarm()
            al.add("action", "DISPLAY")
            al.add("description", item["title"])
            al.add("trigger", datetime.timedelta(minutes=-int(item["alarm"])))
            ev.add_component(al)
    if not keep_people:
        for p in item.get("people") or []:
            a = icalendar.vCalAddress("mailto:" + p["mail"])
            if p.get("name"):
                a.params["CN"] = icalendar.vText(p["name"])
            a.params["ROLE"] = icalendar.vText("REQ-PARTICIPANT")
            a.params["PARTSTAT"] = icalendar.vText("NEEDS-ACTION")
            a.params["SCHEDULE-AGENT"] = icalendar.vText("CLIENT")   # the server sends no invitation
            ev.add("attendee", a, encode=0)
    return ev


def _zone(name):
    try:
        return zoneinfo.ZoneInfo(str(name or "Europe/Berlin"))
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return zoneinfo.ZoneInfo("Europe/Berlin")


def set_rule(ev, item, old=None):
    """The repeat rule from the item: none, one of RULES (with its end), or "custom": the old rule stays."""
    word = item.get("rule") or "" if "rule" in item else "custom"
    if word == "custom":
        if old is not None:
            ev.pop("RRULE", None)
            ev.add("rrule", old)
        return
    ev.pop("RRULE", None)
    if not word:
        return
    freq, n = RULES[word]
    r = {"FREQ": freq}
    if n > 1:
        r["INTERVAL"] = n
    if item.get("until"):
        u = datetime.date.fromisoformat(item["until"])
        r["UNTIL"] = u if item.get("allday") else \
            datetime.datetime.combine(u, datetime.time(23, 59, 59), _zone(item.get("zone"))).astimezone(UTC)
    ev.add("rrule", r)


def _bump(ev):
    seq = int(ev.get("SEQUENCE", 0) or 0)
    ev.pop("SEQUENCE", None)
    ev.add("sequence", seq + 1)


def new_calendar(item, uid_text):
    """A new appointment (calendars.ical): one VEVENT with every field and its repeat rule."""
    cal = icalendar.Calendar()
    cal.add("prodid", "-//speech-on-dgx-spark//DE")
    cal.add("version", "2.0")
    ev = icalendar.Event()
    ev.add("uid", uid_text)
    if item.get("rule"):
        set_rule(ev, item)
    fill(ev, dict(item, people=item.get("people") or [], alarm=int(item.get("alarm") or 0)))
    cal.add_component(ev)
    _zones(cal)
    return cal.to_ical()


def _zones(cal):
    """A VTIMEZONE for every zone a start names (a repeating appointment keeps its hour across summer time)."""
    try:
        cal.add_missing_timezones()
    except Exception:
        pass


def change_single(text, item):
    """A single appointment (one VEVENT, no rule yet) changed by the page's form; a repeat rule makes it a series.
    Returns the new text, or ValueError for an object that is not one single appointment."""
    cal = icalendar.Calendar.from_ical(text)
    evs = list(cal.walk("VEVENT"))
    if len(evs) != 1 or evs[0].get("RRULE") is not None or evs[0].get("RECURRENCE-ID") is not None:
        raise ValueError("not a single appointment")
    ev = evs[0]
    if item.get("rule") and item["rule"] != "custom":
        set_rule(ev, item)
    fill(ev, item)
    _bump(ev)
    _zones(cal)
    return cal.to_ical().decode()


# ---------------------------------------------------------------- a repeating appointment
def _series(cal, uid):
    """(the series' master VEVENT, its changed occurrences) of the appointment uid in one object."""
    evs = [x for x in cal.walk("VEVENT") if str(x.get("UID", "")) == uid]
    master = next((x for x in evs if x.get("RECURRENCE-ID") is None and x.get("RRULE") is not None), None)
    if master is None:
        raise LookupError("the series is not there as shown (changed meanwhile)")
    return master, [x for x in evs if x.get("RECURRENCE-ID") is not None]


def _rid(master, rid, zone):
    """The occurrence's original start (epoch) in the form of the master's start: a date, a time with its zone, or
    a floating time."""
    s = master.get("DTSTART").dt
    if not isinstance(s, datetime.datetime):
        return datetime.datetime.fromtimestamp(rid, zone).date()
    if s.tzinfo is None:
        return datetime.datetime.fromtimestamp(rid, zone).replace(tzinfo=None)
    return datetime.datetime.fromtimestamp(rid, UTC).astimezone(s.tzinfo)


def _key(v, zone):
    v = getattr(v, "dt", v)
    if not isinstance(v, datetime.datetime):
        return ("d", v.isoformat())
    return ("t", int((v if v.tzinfo else v.replace(tzinfo=zone)).timestamp()))


def _occurs(master, r, zone):
    """True when the master's rule (without its changed occurrences) has an occurrence starting at r."""
    one = icalendar.Calendar()
    one.add_component(master)
    if isinstance(r, datetime.datetime):
        a = (r if r.tzinfo else r.replace(tzinfo=zone)) - datetime.timedelta(minutes=1)
        b = a + datetime.timedelta(minutes=2)
    else:
        a, b = r, r + datetime.timedelta(days=1)
    want = _key(r, zone)
    try:
        hits = recurring_ical_events.of(one).between(a, b)
    except Exception:
        return False
    return any(_key(h.get("RECURRENCE-ID") or h.get("DTSTART"), zone) == want for h in hits)


def _copy(ev):
    return icalendar.Event.from_ical(ev.to_ical())


def _end_before(master, r):
    """The series ends before the occurrence r (RRULE UNTIL; a COUNT gives way to it)."""
    rule = master["RRULE"]
    rule.pop("COUNT", None)
    if isinstance(r, datetime.datetime):
        until = (r if r.tzinfo else r.replace(tzinfo=UTC)).astimezone(UTC) - datetime.timedelta(seconds=1)
    else:
        until = r - datetime.timedelta(days=1)
    old = (rule.get("UNTIL") or [None])[0]
    rule["UNTIL"] = [old if old is not None and type(old) is type(until) and old < until else until]


def _left(master, r, zone):
    """How many occurrences a COUNT rule still has from r on (for the new series after „Alle künftigen“)."""
    rule = master.get("RRULE")
    if not rule or not rule.get("COUNT"):
        return 0
    one = icalendar.Calendar()
    one.add_component(_copy(master))
    s = master.get("DTSTART").dt
    try:
        before = len(recurring_ical_events.of(one).between(s, r))
    except Exception:
        before = 0
    return max(1, int(rule["COUNT"][0]) - before)


def change_one(text, uid, rid, item, zone):
    """„Nur dieser Termin“: item None deletes the one occurrence (EXDATE), else it becomes a changed occurrence
    (RECURRENCE-ID) with the item's fields; the rule of the series stays. Returns the new text."""
    cal = icalendar.Calendar.from_ical(text)
    master, overs = _series(cal, uid)
    r = _rid(master, rid, zone)
    over = next((o for o in overs if _key(o.get("RECURRENCE-ID"), zone) == _key(r, zone)), None)
    if over is None and not _occurs(master, r, zone):
        raise LookupError("the series has no appointment at this time (changed meanwhile)")
    if item is None:
        if over is not None:
            cal.subcomponents.remove(over)
        master.add("exdate", r)
        _bump(master)
    else:
        if over is None:
            over = _copy(master)
            for k in ("RRULE", "RDATE", "EXDATE", "RECURRENCE-ID", "SEQUENCE"):
                over.pop(k, None)
            over.add("recurrence-id", r)
            cal.add_component(over)
        fill(over, dict(item, rule=""))
        _bump(over)
    _zones(cal)
    return cal.to_ical().decode()


def change_future(text, uid, rid, item, zone, new_uid):
    """„Alle künftigen“ from the occurrence rid: (the series' object after it, or None to delete the object; a new
    object for the future part, or None). From the first occurrence it is the whole series, changed in place; a
    later one ends the old series before it and the future goes on as a series of its own (new_uid)."""
    cal = icalendar.Calendar.from_ical(text)
    master, overs = _series(cal, uid)
    r = _rid(master, rid, zone)
    if _key(master.get("DTSTART"), zone) == _key(r, zone):
        if item is None:
            return None, None
        old = master.get("RRULE")
        old = icalendar.vRecur(dict(old)) if old is not None else None
        moved = item["start"] != _iso(master.get("DTSTART").dt, item)
        set_rule(master, item, old)
        if master.get("RRULE") is None or moved:   # the changed occurrences and gaps no longer fit the new times
            for o in overs:
                cal.subcomponents.remove(o)
            master.pop("EXDATE", None)
            master.pop("RDATE", None)
        fill(master, item)
        _bump(master)
        _zones(cal)
        return cal.to_ical().decode(), None
    if not _occurs(master, r, zone) and not any(_key(o.get("RECURRENCE-ID"), zone) == _key(r, zone) for o in overs):
        raise LookupError("the series has no appointment at this time (changed meanwhile)")
    old = icalendar.vRecur(dict(master["RRULE"]))
    left = _left(master, r, zone)
    _end_before(master, r)
    for o in overs:
        if _key(o.get("RECURRENCE-ID"), zone) >= _key(r, zone):
            cal.subcomponents.remove(o)
    _bump(master)
    _zones(cal)
    rest = cal.to_ical().decode()
    if item is None:
        return rest, None
    new = icalendar.Calendar()
    new.add("prodid", "-//speech-on-dgx-spark//DE")
    new.add("version", "2.0")
    ev = _copy(master)
    for k in ("UID", "RRULE", "RDATE", "EXDATE", "RECURRENCE-ID", "SEQUENCE"):
        ev.pop(k, None)
    ev.add("uid", new_uid)
    if left:
        old["COUNT"] = [left]
        old.pop("UNTIL", None)
    set_rule(ev, item, old)
    if ev.get("RRULE") is None and item.get("rule") == "custom":
        ev.add("rrule", old)
    fill(ev, item)
    new.add_component(ev)
    _zones(new)
    return rest, new.to_ical().decode()


def _iso(dt, item):
    """The master's start as the page's item writes it, to see whether the whole series moved."""
    if not isinstance(dt, datetime.datetime):
        return datetime.datetime.combine(dt, datetime.time(), _zone(item.get("zone"))).isoformat()
    return (dt if dt.tzinfo else dt.replace(tzinfo=_zone(item.get("zone")))).astimezone(_zone(item.get("zone"))).isoformat()
