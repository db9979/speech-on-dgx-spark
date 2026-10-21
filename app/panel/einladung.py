"""Einladungen aus Mails (Dominik 2026-10-21 „ja alles umsetzen 1-6“, Punkt 3; Apple-Stil Kalender „später:
Einladungen“): a mail with an invitation (.ics, iMIP) shows above its text what, when, where and who invites, and
with one tap it goes into a calendar of the profile; „Zusagen“, „Vielleicht“ and „Absagen“ answer the organiser
like Apple Mail and Outlook do.

Who may: the admin switch chat.mail_invites (features.py "einladungen", off by default, needs E-Mail lesen and
Kalender), every profile the admin did not block, never guests. The answer to the organiser goes out only with
„Mails senden“ (features "mailsend"), from the mailbox the invitation came to, counted like every sent mail
(senden.send_now: day limit, Notaus, journal).

The invitation is someone else's text, so it is data:
- at most MAX_ICS bytes, one appointment (VEVENTs of one UID: the series and its changed dates), at most MAX_EVENTS;
  METHOD REQUEST, PUBLISH or CANCEL (an ADD, COUNTER or REFRESH is shown as not supported);
- into the calendar goes a new calendar of the Spark's own making with only the fields KEEP (no alarms, no
  attachments, no links of the sender), the description cut at MAX_TEXT, at most MAX_PEOPLE people, the time zones
  the times need;
- the place the appointment goes is fixed by its UID (sha1), so the same invitation again (or its update with a
  higher SEQUENCE) replaces it instead of adding it twice; a cancellation removes it only after the tap.
- the model never sees or decides any of this; the assistant does not answer invitations.
Journal: fixed words and numbers; Live: invitations shown, taken and answered today, numbers only.
"""
import asyncio
import datetime
import email.message
import email.policy
import email.utils
import hashlib
import re
import time

import icalendar

import calendars
import features
import mail
import notaus
import profiles
import senden
from common import DayCounter

MAX_ICS = 256 * 1024
MAX_EVENTS = 50
MAX_PEOPLE = 100
MAX_TEXT = 4000
METHODS = ("REQUEST", "PUBLISH", "CANCEL")
KEEP = ("UID", "DTSTAMP", "DTSTART", "DTEND", "DURATION", "RRULE", "RDATE", "EXDATE", "RECURRENCE-ID", "SEQUENCE",
        "SUMMARY", "LOCATION", "DESCRIPTION", "ORGANIZER", "ATTENDEE", "STATUS", "TRANSP", "CLASS")
ANSWERS = {"accept": "ACCEPTED", "tentative": "TENTATIVE", "decline": "DECLINED"}
SUBJECT = {"accept": ("Zugesagt", "Accepted"), "tentative": ("Vielleicht", "Tentative"), "decline": ("Abgesagt", "Declined")}
TYPES = ("text/calendar", "application/ics")
_count = DayCounter(gezeigt=0, eingetragen=0, beantwortet=0)


def admin_on():
    return features.admin_on("einladungen")


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


def _part(msg):
    """The text of the message's first calendar part (an inline text/calendar or an .ics file), or None."""
    for part in (msg.walk() if msg is not None else ()):
        if part.is_multipart():
            continue
        name = str(part.get_filename() or "").lower()
        if part.get_content_type() in TYPES or name.endswith(".ics"):
            data = part.get_payload(decode=True) or b""
            return data.decode(part.get_content_charset() or "utf-8", "replace") if 0 < len(data) <= MAX_ICS else None
    return None


def has(uid, msg):
    """mail.show: does the message carry an invitation this profile may take? (only a look at the parts' types)"""
    if not features.allowed("einladungen", uid) or msg is None:
        return False
    return any(not p.is_multipart() and (p.get_content_type() in TYPES or str(p.get_filename() or "").lower().endswith(".ics"))
               for p in msg.walk())


def parse(text):
    """(method, [VEVENT], [VTIMEZONE]) of an invitation; ValueError when it is none the Spark takes."""
    if not text or len(text.encode("utf-8", "replace")) > MAX_ICS:
        raise ValueError("no invitation, or a too big one")
    try:
        cal = icalendar.Calendar.from_ical(text)
    except Exception:
        raise ValueError("the invitation cannot be read")
    method = str(cal.get("METHOD") or "PUBLISH").strip().upper()
    if method not in METHODS:
        raise ValueError("this kind of invitation is not supported")
    evs = [c for c in cal.walk("VEVENT")]
    if not evs or len(evs) > MAX_EVENTS:
        raise ValueError("the invitation holds no appointment, or too many")
    uids = {str(e.get("UID") or "") for e in evs}
    if len(uids) != 1 or not re.fullmatch(r"[\x21-\x7e]{1,255}", next(iter(uids))):
        raise ValueError("the invitation holds more than one appointment")
    if any(e.get("DTSTART") is None for e in evs if method != "CANCEL"):
        raise ValueError("the appointment has no start")
    return method, evs, [c for c in cal.walk("VTIMEZONE")][:10]


def _master(evs):
    return next((e for e in evs if e.get("RECURRENCE-ID") is None), evs[0])


def _addr(v):
    s = str(v or "").strip()
    s = s[7:] if s.lower().startswith("mailto:") else s
    return s if senden.ADDR.fullmatch(s) else ""


def _ts(v):
    """(unix seconds, all day) of a DTSTART/DTEND value."""
    if v is None:
        return 0, False
    d = v.dt
    if isinstance(d, datetime.datetime):
        if d.tzinfo is None:
            d = d.astimezone()
        return int(d.timestamp()), False
    return int(datetime.datetime(d.year, d.month, d.day).timestamp()), True


def _key(ev_uid):
    return hashlib.sha1(ev_uid.encode()).hexdigest()[:24]


def _account(uid, ref):
    m = re.fullmatch(r"(m[0-9a-f]{8}):\d{1,10}", str(ref).strip())
    acct = next((a for a in mail.get(uid)["accounts"] if m and a["id"] == m.group(1)), None)
    if not acct:
        raise ValueError("unknown message id")
    return acct


def _load(uid, ref, folder):
    """(method, events, zones, the mailbox) of the invitation in mail ref; LookupError when it has none."""
    acct = _account(uid, ref)
    text = _part(mail.message(uid, ref, folder))
    if text is None:   # a long mail: the calendar part after MAX_FETCH
        text = _part(mail.whole(uid, ref, folder))
    if text is None:
        raise LookupError("the mail holds no invitation (any more)")
    return (*parse(text), acct)


def _people(ev):
    v = ev.get("ATTENDEE")
    return [] if v is None else (v if isinstance(v, list) else [v])


def _mine(ev, own):
    """The profile's own ATTENDEE line (by the mailbox's address), or None."""
    return next((a for a in _people(ev) if _addr(a).lower() == own.lower()), None)


async def _targets(uid):
    """[(key, entry, calendar url, name)] of the profile's own writable calendars."""
    out = []
    for d in calendars._writable(uid):
        try:
            async with calendars._cal_client(d) as c:
                for href, name in await calendars._parts(c, d):
                    k = hashlib.sha1(f"{d['id']}|{href}".encode()).hexdigest()[:12]
                    out.append((k, d, href, name or d.get("name") or "Kalender"))
        except Exception:
            continue
    return out


async def _where(targets, ev_uid):
    """(entry, href, name) where this invitation already is, or None (one GET per calendar, at its fixed place)."""
    for _, d, cal, name in targets:
        href = cal.rstrip("/") + f"/{_key(ev_uid)}.ics"
        try:
            async with calendars._cal_client(d) as c:
                if (await c.get(href)).status_code == 200:
                    return d, href, name
        except Exception:
            continue
    return None


async def show(uid, ref, folder="INBOX"):
    """What the bar above the mail shows: the appointment, who invites, the own answer so far, whether it is in a
    calendar already, the calendars to choose and whether an answer can go out."""
    method, evs, _, acct = await asyncio.to_thread(_load, uid, ref, folder)
    ev = _master(evs)
    start, allday = _ts(ev.get("DTSTART"))
    end, _ = _ts(ev.get("DTEND"))
    if not end and ev.get("DURATION") is not None:
        end = start + int(ev.get("DURATION").dt.total_seconds())
    org = ev.get("ORGANIZER")
    own = _mine(ev, acct["user"])
    targets = await _targets(uid)
    found = await _where(targets, str(ev.get("UID")))
    _count.bump("gezeigt")
    print(f"calendar: invitation shown | {_who(uid)}", flush=True)
    return {"method": method.lower(), "title": str(ev.get("SUMMARY") or "")[:200], "start": start, "end": end,
            "allday": allday, "place": str(ev.get("LOCATION") or "")[:200], "repeats": ev.get("RRULE") is not None,
            "organizer": {"name": str((org.params.get("CN") if org is not None else "") or "")[:80], "addr": _addr(org)},
            "people": len(_people(ev)), "mine": str(own.params.get("PARTSTAT", "")).lower() if own is not None else "",
            "in": found[2] if found else "", "calendars": [{"id": k, "name": n} for k, _, _, n in targets],
            "reply": bool(method == "REQUEST" and own is not None and _addr(org) and features.allowed("mailsend", uid))}


def clean(evs, zones, own="", partstat=""):
    """The Spark's own calendar of the invitation: only KEEP, text cut, people limited, no alarm; the own
    ATTENDEE gets the answer."""
    cal = icalendar.Calendar()
    cal.add("PRODID", "-//speech-spark//Einladung//DE")
    cal.add("VERSION", "2.0")
    for z in zones:
        cal.add_component(z)
    for ev in evs:
        new = icalendar.Event()
        for k in KEEP:
            v = ev.get(k)
            if v is None:
                continue
            if k == "ATTENDEE":
                for a in (v if isinstance(v, list) else [v])[:MAX_PEOPLE]:
                    if own and partstat and _addr(a).lower() == own.lower():
                        params = dict(a.params)
                        a = icalendar.vCalAddress(str(a))
                        a.params.update(params)
                        a.params["PARTSTAT"] = partstat
                        a.params.pop("RSVP", None)
                    new.add("ATTENDEE", a)
            elif k in ("SUMMARY", "LOCATION"):
                new.add(k, str(v)[:200])
            elif k == "DESCRIPTION":
                new.add(k, str(v)[:MAX_TEXT])
            elif isinstance(v, list):
                for x in v:
                    new.add(k, x)
            else:
                new[k] = v
        if new.get("DTSTAMP") is None:
            new.add("DTSTAMP", icalendar.vDatetime.from_ical(time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())))
        cal.add_component(new)
    return cal.to_ical().decode()


def reply_mail(acct, prof, ev, answer):
    """The iMIP REPLY to the organiser (RFC 6047): a short text and the answer as text/calendar METHOD:REPLY."""
    org = _addr(ev.get("ORGANIZER"))
    title = str(ev.get("SUMMARY") or "")[:120]
    cal = icalendar.Calendar()
    cal.add("PRODID", "-//speech-spark//Einladung//DE")
    cal.add("VERSION", "2.0")
    cal.add("METHOD", "REPLY")
    r = icalendar.Event()
    for k in ("UID", "SEQUENCE", "RECURRENCE-ID", "DTSTART", "DTEND", "ORGANIZER"):
        if ev.get(k) is not None:
            r[k] = ev.get(k)
    r.add("SUMMARY", title)
    r.add("DTSTAMP", icalendar.vDatetime.from_ical(time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())))
    me = icalendar.vCalAddress("mailto:" + acct["user"])
    me.params["PARTSTAT"] = ANSWERS[answer]
    if prof.get("name"):
        me.params["CN"] = str(prof["name"])[:80]
    r.add("ATTENDEE", me)
    cal.add_component(r)
    name = str(prof.get("name") or acct["user"])[:80]
    de, en = SUBJECT[answer]
    msg = email.message.EmailMessage(policy=email.policy.SMTP)
    msg["From"] = email.utils.formataddr((str(prof.get("name") or "")[:80], acct["user"])) if prof.get("name") else acct["user"]
    msg["To"] = org
    msg["Subject"] = f"{de}: {title}"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=acct["user"].rsplit("@", 1)[1])
    words = {"accept": "nimmt teil", "tentative": "nimmt vielleicht teil", "decline": "nimmt nicht teil"}[answer]
    msg.set_content(f"{name} {words}: {title}\n")
    msg.add_alternative(cal.to_ical().decode(), subtype="calendar", params={"method": "REPLY"})
    return msg


async def take(uid, ref, folder, answer, cal_key="", reply=True):
    """The tap: accept / tentative put the appointment into the calendar (where it already is, else the one chosen,
    else the first), decline and remove (a cancellation) take it out; the answer goes to the organiser when asked
    and allowed. {"in": calendar name or "", "replied": bool}."""
    who = _who(uid)
    if answer not in (*ANSWERS, "remove"):
        raise ValueError("unknown answer")
    notaus.stop("aktion", uid)
    method, evs, zones, acct = await asyncio.to_thread(_load, uid, ref, folder)
    ev = _master(evs)
    ev_uid = str(ev.get("UID"))
    if (answer == "remove") != (method == "CANCEL"):
        raise ValueError("this answer does not fit the invitation")
    targets = await _targets(uid)
    found = await _where(targets, ev_uid)
    shown = ""
    if answer in ("accept", "tentative"):
        if found:
            d, href, shown = found
        else:
            pick = next((t for t in targets if t[0] == cal_key), None) or (targets[0] if targets else None)
            if pick is None:
                raise ValueError("there is no calendar to write into; connect one under Kalender → Einstellungen")
            _, d, cal, shown = pick
            href = cal.rstrip("/") + f"/{_key(ev_uid)}.ics"
        text = clean(evs, zones, acct["user"], ANSWERS[answer])
        async with calendars._cal_client(d) as c:
            r = await c.put(href, content=text.encode(), headers={"Content-Type": "text/calendar; charset=utf-8"})
        if r.status_code not in (200, 201, 204):
            print(f"calendar: invitation not saved ({r.status_code}) | {who}", flush=True)
            raise ValueError(f"the calendar server answered {r.status_code}")
        calendars._drop(uid)
        _count.bump("eingetragen")
        print(f"calendar: invitation saved | {who}", flush=True)
    elif found:   # decline or a cancellation: out of the calendar
        d, href, _ = found
        async with calendars._cal_client(d) as c:
            r = await c.delete(href)
        if r.status_code not in (200, 204, 404):
            print(f"calendar: invitation not removed ({r.status_code}) | {who}", flush=True)
            raise ValueError(f"the calendar server answered {r.status_code}")
        calendars._drop(uid)
        print(f"calendar: invitation removed | {who}", flush=True)
    else:
        print(f"calendar: invitation not in a calendar | {who}", flush=True)
    replied = False
    if reply and answer in ANSWERS and method == "REQUEST" and _mine(ev, acct["user"]) is not None \
            and _addr(ev.get("ORGANIZER")) and features.allowed("mailsend", uid):
        await asyncio.to_thread(senden.send_now, uid, acct, reply_mail(acct, profiles.by_id(uid) or {}, ev, answer))
        replied = True
        _count.bump("beantwortet")
        print(f"calendar: invitation answered ({'accepted' if answer == 'accept' else 'maybe' if answer == 'tentative' else 'declined'}) | {who}", flush=True)
    return {"in": shown, "replied": replied}


def for_live():
    """Live (Kalender): invitations shown, taken into a calendar and answered today; numbers only."""
    c = _count.counts()
    return {"on": admin_on(), "shown": c.get("gezeigt", 0), "saved": c.get("eingetragen", 0),
            "answered": c.get("beantwortet", 0)}


# ---------------------------------------------------------------- API (page E-Mail, iPhone app)
import imaplib  # noqa: E402

import httpx  # noqa: E402
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import guard  # noqa: E402
from core import assistant, browser_profile, json_body, own_profile  # noqa: E402

router = APIRouter()


def _on(request: Request):
    prof = profiles.current(request)
    if not admin_on() or not prof or not features.allowed("einladungen", prof["id"]):
        raise HTTPException(403, "Einladungen aus Mails ist aus (Funktionen → E-Mail lesen → „Einladungen aus Mails“)")


async def _answer(job, prof):
    try:
        return await asyncio.wait_for(job, 90)
    except notaus.NotausAktiv:
        print(f"calendar: invitation refused, notaus | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(423, "Notaus: gerade wird nichts geändert")
    except LookupError as e:
        print(f"calendar: invitation refused, not found | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, str(e)[:200])
    except ValueError as e:
        print(f"calendar: invitation refused | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, str(e)[:200])
    except asyncio.TimeoutError:
        print(f"calendar: invitation too slow | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(504, "Postfach oder Kalender haben zu lange gebraucht. Bitte gleich noch einmal.")
    except (OSError, imaplib.IMAP4.error, httpx.HTTPError, ConnectionError) as e:
        print(f"calendar: invitation failed ({type(e).__name__}) | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(502, "Postfach oder Kalender waren nicht erreichbar.")


@router.get("/api/profile/mail/invite", dependencies=[Depends(assistant), Depends(_on)])
async def api_show(request: Request, id: str = "", folder: str = "", prof=Depends(own_profile)):
    guard.limit(request, "einladung", prof["id"])
    return await _answer(show(prof["id"], id[:40], folder[:200] or "INBOX"), prof)


@router.post("/api/profile/mail/invite", dependencies=[Depends(assistant), Depends(_on)])
async def api_take(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "einladung", prof["id"])
    body = await json_body(request, 4 * 1024)
    return await _answer(take(prof["id"], str(body.get("id") or "")[:40], str(body.get("folder") or "INBOX")[:200],
                              str(body.get("answer") or "")[:20], str(body.get("calendar") or "")[:20],
                              body.get("reply", True) is not False), prof)
