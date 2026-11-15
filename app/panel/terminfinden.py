"""Termin finden (Nextcloud-Ideen 3 / K1+K2, Dominik 2026-11-15 „alles umsetzen“; Idee aus Nextcloud Calendar, nur als
Idee, kein Code; Bild /mnt/project-files/nextcloud-ideen/bauplan.png): in einem Chat dieses Sparks (zu zweit oder Gruppe)
sucht der Spark Zeiten, in denen alle Mitglieder frei sind, und stellt sie als Umfrage (umfrage.py, art "termin").

- Frei/belegt nur aus den Terminen mit Uhrzeit der eigenen Kalender jedes Mitglieds (calendars.events aus der Kopie);
  nie ein Titel, ein Ort oder eine Uhrzeit eines anderen Termins nach außen, nur die freien Zeiten. Wer keinen Kalender
  hat oder für wen die Funktion gesperrt ist, zählt als „ohne Kalender“ (nur die Zahl).
- Die Zeiten: ab einem Tag höchstens SPAN_MAX Tage, zwischen zwei vollen Stunden, im Raster STEP Minuten, höchstens zwei
  pro Tag und MAX_SLOTS insgesamt; nie in der Vergangenheit.
- Schließt, wer gefragt hat, die Umfrage, trägt der Spark die gewählte Zeit bei ihm und bei jedem ein, der für sie
  gestimmt hat (ihre Stimme ist ihr Ja), in den ersten beschreibbaren Kalender (calendars.add_event); sonst bei niemandem.

Admin-Schalter chat.calendar_find (aus; baut auf Kalender und Umfragen in Chats); nie ein Werkzeug fürs Modell.
Journal (Bereich Kalender): „calendar: find | members n | free n | without n“, „calendar: find poll | slots n“,
„calendar: find entered | n 2 | failed 0“.
"""
import datetime
import time

from fastapi import APIRouter, Depends, Request

import calendars
import chats
import core
import features
import umfrage
from chat import user_zone
from common import DayCounter
from core import assistant, json_body

KEY = "terminfinden"
SPAN_MAX = 14           # days looked at, at most
MAX_SLOTS = 6           # times offered, at most (a poll takes up to umfrage.MAX_OPTS)
PER_DAY = 2
STEP = 30               # minutes between possible starts
LENGTHS = (30, 60, 90, 120, 180)
_count = DayCounter(gesucht=0, gestellt=0, eingetragen=0)
_DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _chat(uid, cid):
    """The chat's members on this Spark; only a chat for two or a group of this Spark."""
    c = chats._member(uid, cid)
    if c.get("kind") not in ("one", "group") or chats.spans(c):
        raise ValueError("Termin finden geht nur in einem Chat dieses Spark.")
    return chats._locals(c)


def label(s, e):
    """„Mo 16.11. 10:00–11:00“ (the answer's text in the poll)."""
    return f"{_DAYS[s.weekday()]} {s.day}.{s.month}. {s:%H:%M}–{e:%H:%M}"


def _busy(evs):
    out = []
    for x in evs or []:
        if x.get("allday"):
            continue        # birthdays, holidays, Abwesenheit as a day: never busy for a time of day
        s, e = x.get("start"), x.get("end")
        if isinstance(s, datetime.datetime) and isinstance(e, datetime.datetime) and e > s:
            out.append((s, e))
    return out


def suchen(busy, first, days, minutes, von, bis, zone, now):
    """The free times (pure, the rules above): [(start, end)] as aware datetimes in zone."""
    out, dur = [], datetime.timedelta(minutes=minutes)
    for k in range(days):
        day, n = first + datetime.timedelta(days=k), 0
        t = datetime.datetime.combine(day, datetime.time(von), zone)
        end = datetime.datetime.combine(day, datetime.time(0), zone) + datetime.timedelta(hours=bis)
        last = None
        while t + dur <= end and n < PER_DAY and len(out) < MAX_SLOTS:
            free = t.timestamp() >= now and not any(s < t + dur and e > t for s, e in busy)
            if free and (last is None or t >= last + dur + datetime.timedelta(hours=2)):
                out.append((t, t + dur))
                last, n = t, n + 1
            t += datetime.timedelta(minutes=STEP)
        if len(out) >= MAX_SLOTS:
            break
    return out


def _numbers(b):
    try:
        first = datetime.date.fromisoformat(str(b.get("from") or "")[:10])
        days, minutes = int(b.get("days") or 7), int(b.get("minutes") or 60)
        von, bis = int(b.get("von") if b.get("von") is not None else 8), int(b.get("bis") or 20)
    except (TypeError, ValueError):
        raise ValueError("Bitte Tag, Dauer und Uhrzeiten angeben.")
    if not 1 <= days <= SPAN_MAX or minutes not in LENGTHS or not 0 <= von < bis <= 24:
        raise ValueError(f"Bitte 1 bis {SPAN_MAX} Tage, eine Dauer aus der Liste und von früh bis spät.")
    return first, days, minutes, von, bis


async def frei(uid, cid, b, now=None):
    """{"slots": [{start, end, label}], "ohne": members without a calendar} for the chat's members."""
    if not features.allowed(KEY, uid):
        raise PermissionError(("Termin finden ist für dich aus. " + features.missing_text(KEY, uid)).strip())
    now = time.time() if now is None else now
    members = _chat(uid, cid)
    first, days, minutes, von, bis = _numbers(b)
    zone = user_zone(b.get("tz"))
    if first < datetime.datetime.fromtimestamp(now, zone).date() - datetime.timedelta(days=1):
        raise ValueError("Der erste Tag liegt in der Vergangenheit.")
    start = datetime.datetime.combine(first, datetime.time(0), zone)
    end = start + datetime.timedelta(days=days + 1)
    busy, ohne = [], 0
    for m in members:
        r = None
        if features.allowed("calendar", m):
            try:
                r = await calendars.events(m, start, end, zone, stale=True)
            except Exception:
                r = None
        if r is None:
            ohne += 1
            continue
        busy += _busy(r[0])
    slots = suchen(busy, first, days, minutes, von, bis, zone, now)
    _count.bump("gesucht")
    print(f"calendar: find | members {len(members)} | free {len(slots)} | without {ohne}", flush=True)
    return {"slots": [{"start": s.isoformat(timespec="minutes"), "end": e.isoformat(timespec="minutes"),
                       "label": label(s, e)} for s, e in slots], "ohne": ohne}


async def vorschlagen(uid, cid, title, slots, tz, now=None):
    """The chosen times as a poll (art "termin"); the title becomes its question, sealed like it."""
    if not features.allowed(KEY, uid):
        raise PermissionError(("Termin finden ist für dich aus. " + features.missing_text(KEY, uid)).strip())
    now = time.time() if now is None else now
    _chat(uid, cid)
    zone = user_zone(tz)
    title = chats.clean(title, 120)
    if not title:
        raise ValueError("Bitte einen Titel für den Termin eingeben.")
    got = []
    for x in slots if isinstance(slots, list) else []:
        try:
            s = datetime.datetime.fromisoformat(str(x.get("start"))[:25]).astimezone(zone)
            e = datetime.datetime.fromisoformat(str(x.get("end"))[:25]).astimezone(zone)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Diese Zeit gibt es nicht.")
        if not (e > s and e - s <= datetime.timedelta(hours=12) and s.timestamp() >= now - 3600):
            raise ValueError("Diese Zeit gibt es nicht.")
        got.append((s, e))
    if not 2 <= len(got) <= MAX_SLOTS:
        raise ValueError(f"Bitte 2 bis {MAX_SLOTS} Zeiten wählen.")
    zname = getattr(zone, "key", None) or "UTC"

    def data(mid):
        return {"slots": [[s.isoformat(timespec="minutes"), e.isoformat(timespec="minutes")] for s, e in got],
                "tz": zname, "title": chats.seal(title, cid, f"{mid}/t")}
    item = await umfrage.stellen(uid, cid, title, [label(s, e) for s, e in got], multi=True, art="termin",
                                 data=data, now=now, mark="📅 ")
    _count.bump("gestellt")
    print(f"calendar: find poll | slots {len(got)}", flush=True)
    return item


async def eintragen(who, cid, mid, poll, win):
    """The winning time into the calendar of who asked and of everybody who voted for it."""
    d = poll.get("data") or {}
    try:
        s, e = d["slots"][win]
    except (KeyError, IndexError, TypeError, ValueError):
        return 0
    zone = user_zone(d.get("tz"))
    title = chats.unseal(d.get("title"), cid, f"{mid}/t") or "Termin"
    ok = bad = 0
    for u in who:
        if not features.allowed(KEY, u):
            continue
        try:
            item = calendars.page_item({"title": title, "start": s[:16], "end": e[:16]}, zone)
            await calendars.add_event(u, item)
            ok += 1
        except Exception:
            bad += 1
    _count.bump("eingetragen", ok)
    print(f"calendar: find entered | n {ok} | failed {bad}", flush=True)
    return ok


def _closed(uid, cid, mid, poll, win):
    """umfrage.ON_CLOSE["termin"]: who asked and every vote for the winner; nothing without a winner."""
    if win < 0:
        print("calendar: find entered | n 0 | failed 0", flush=True)
        return None
    who = [uid] + [u for u, picks in (poll.get("votes") or {}).items() if win in picks and u != uid]
    return core.later(eintragen(who, cid, mid, poll, win))


def for_live():
    """Zustand → Live, node Kalender: searches, polls and appointments entered today (numbers only)."""
    c = _count.counts()
    return {"on": bool(features.chat_cfg().get("calendar_find")), **c}


umfrage.ON_CLOSE["termin"] = _closed
chats.STATE["termin"] = lambda uid: features.allowed(KEY, uid)
calendars.LIVE["terminfinden"] = lambda: for_live()

# ---------------------------------------------------------------- API (page Chats, apps)
router = APIRouter()


@router.post("/api/chats/termin/frei", dependencies=[Depends(assistant)])
async def api_frei(request: Request, prof=Depends(chats._on)):
    """{"id": chat, "from": "YYYY-MM-DD", "days", "minutes", "von", "bis", "tz"}"""
    b = await json_body(request, 1024)
    try:
        return await frei(prof["id"], chats._cid(b.get("id")), b)
    except (LookupError, PermissionError, ValueError) as e:
        raise chats._err(e)


@router.post("/api/chats/termin", dependencies=[Depends(assistant)])
async def api_poll(request: Request, prof=Depends(chats._on)):
    """{"id": chat, "title", "slots": [{"start", "end"}], "tz"}"""
    b = await json_body(request, 4 * 1024)
    try:
        return {"item": await vorschlagen(prof["id"], chats._cid(b.get("id")), b.get("title"), b.get("slots"), b.get("tz"))}
    except (LookupError, PermissionError, ValueError, OverflowError) as e:
        raise chats._err(e)
