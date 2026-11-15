"""Abwesend (Nextcloud-Ideen 1, Dominik 2026-11-15 „alles umsetzen“; Idee aus Nextclouds Abwesenheit, nur als Idee,
kein Code; Bild /mnt/project-files/nextcloud-ideen/abwesenheit.png): ein Profil trägt unter Kalender → Einstellungen
„Abwesenheit“ ein, von wann bis wann es weg ist, einen Text für Antworten und eine Vertretung. Dann, nach festen
Regeln des Panels, nie des Modells:

- Kalender: ein eigener Kalender „Abwesenheit“ mit dem ganztägigen Eintrag (calendars.EXTRA, nur lesen, nichts in
  einem CalDAV-Kalender), wenn „Im Kalender zeigen“ an ist;
- Chats: neben dem Namen „abwesend bis 4.1.“ für alle, die mit dem Profil einen Chat haben (profiles.AWAY);
- Anrufe: ein Spark-Anruf klingelt nicht, er ist gleich ein verpasster (anrufe.start), und „Ruf Dominik an“ sagt
  vorher „Dominik ist bis 4. Januar weg, Vertretung Sabine.“ (rufen._spark_offer);
- E-Mail: aktiv() gibt dem Mail-Thread {von, bis, text}, wenn „Mail-Antwort“ an ist; die Antwort selbst baut mail.py.

Beschäftigt im Termin (Stufe 2b, eigener Admin-Schalter chat.calendar_busy, aus, baut auf Kalender): läuft gerade ein
Termin mit Uhrzeit in einem eigenen Kalender des Profils (nie ganztägig, nie ein geteilter), ist das Profil
„beschäftigt“ wie beim „Nicht stören“ des Begleiters (begleiter.set_busy, Grund "termin"): keine Durchsagen an seine
Lautsprecher, Mitteilungen warten und kommen danach als eine Zusammenfassung (Alarme, Erinnerungen und
Sicherheitshinweise immer, begleiter.URGENT), Spark-Anrufe klingeln nicht, in Chats steht nur das Wort „beschäftigt“,
nie der Termin. minute() prüft das jede Minute aus der Kopie der Kalender (calendars.events, stale) für die Profile,
deren Kalender der Spark ohnehin frisch hält (calendars._used); höchstens BUSY_WAIT Sekunden je Profil.

Nur mit dem Admin-Schalter chat.away (aus, baut auf Kalender auf), für jedes Profil, das der Admin nicht sperrt; nie
für Gäste, nie ein Werkzeug fürs Modell. Gespeichert versiegelt im Ordner des Profils (abwesenheit.bin, vorrat.Vorrat):
die Tage, der Text (höchstens MAX_TEXT Zeichen), die Vertretung (ein Name, höchstens MAX_NAME Zeichen), die Schalter
und die Zeitzone des Browsers. Höchstens MAX_DAYS Tage am Stück; ist der letzte Tag vorbei, gilt nichts mehr und der
Eintrag geht beim nächsten Lesen.

Schnittstelle zum Mail-Thread (abgesprochen 2026-11-15): aktiv(uid, now=None) → {von, bis, text} (Unix-Sekunden) oder
None; ON_CHANGE: Funktionen f(uid), gerufen nach jedem Speichern und Löschen.
Journal (Bereich Listen): „calendar: away saved | <Profil>“, „calendar: away deleted …“, „calendar: away refused …“.
"""
import asyncio
import datetime
import re
import threading
import time

import begleiter
import calendars
import features
import profiles
from chat import user_zone
from common import DayCounter
from vorrat import Vorrat

KEY = "abwesend"
BUSY_KEY = "beschaeftigt"
BUSY_WAIT = 5                # seconds per profile for the calendar copy
NAME = "abwesenheit.bin"
CAL = "Abwesenheit"          # the calendar's name (the page and the app say it in their language, "made": "abwesend")
MAX_TEXT = 2000
MAX_NAME = 60
MAX_DAYS = 366
STORE = Vorrat(NAME, idle_days=MAX_DAYS + 35, write_every=0)
ON_CHANGE = []               # f(uid) after each save or delete (the mail thread's auto reply)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ZONE = re.compile(r"[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+){0,2}")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")
_count = DayCounter(gespeichert=0, geloescht=0, anrufe=0, termine=0)
_termin = set()              # profiles busy now because of an appointment (minute())
_lock = threading.Lock()


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


def _read(uid):
    a = STORE.load(uid).get("a")
    return a if isinstance(a, dict) and DATE.fullmatch(str(a.get("von") or "")) and DATE.fullmatch(str(a.get("bis") or "")) else None


def span(a):
    """(start, end) in Unix seconds: 00:00 of the first day to 00:00 after the last one, in the stored zone."""
    zone = user_zone(a.get("tz"))
    t0 = datetime.datetime.combine(datetime.date.fromisoformat(a["von"]), datetime.time(), zone)
    t1 = datetime.datetime.combine(datetime.date.fromisoformat(a["bis"]) + datetime.timedelta(days=1), datetime.time(), zone)
    return int(t0.timestamp()), int(t1.timestamp())


def eintrag(uid):
    """The profile's own entry for the page and the apps, None without one; an entry whose last day is over (by the
    clock, never by a time asked about) goes."""
    a = _read(uid)
    if not a:
        return None
    t0, t1 = span(a)
    if time.time() >= t1:
        _drop(uid, "over")
        return None
    return {"von": a["von"], "bis": a["bis"], "text": a.get("text", ""), "vertretung": a.get("vertretung", ""),
            "mail": bool(a.get("mail")), "kalender": bool(a.get("kalender")), "tz": a.get("tz", ""),
            "start": t0, "end": t1}


def jetzt(uid, now=None):
    """The entry while the profile is away now and the function is on for it, else None."""
    if not uid or not features.allowed(KEY, uid):
        return None
    a = eintrag(uid)
    now = time.time() if now is None else now
    return a if a and a["start"] <= now < a["end"] else None


def aktiv(uid, now=None):
    """For the mail thread: {von, bis, text} (Unix seconds) while away with „Mail-Antwort“ on, else None."""
    a = jetzt(uid, now)
    return {"von": a["start"], "bis": a["end"], "text": a["text"]} if a and a["mail"] and a["text"] else None


def satz(uid, now=None):
    """„Dominik ist bis 4. Januar weg, Vertretung Sabine.“ while away, else ""; the name is the profile's name."""
    a = jetzt(uid, now)
    if not a:
        return ""
    d = datetime.date.fromisoformat(a["bis"])
    v = f", Vertretung {a['vertretung']}" if a["vertretung"] else ""
    return f"{(profiles.by_id(uid) or {}).get('name') or 'Die Person'} ist bis {d.day}. {MONATE[d.month - 1]} weg{v}."


def away(uid, now=None):
    """profiles.AWAY: {"bis": last day (ISO), "satz": …} while away; {"busy": True, "satz": …} while in an appointment
    (only that, never which); else None."""
    a = jetzt(uid, now)
    if a:
        return {"bis": a["bis"], "satz": satz(uid, now)}
    if uid in _termin and features.allowed(BUSY_KEY, uid):
        return {"bis": "", "busy": True,
                "satz": f"{(profiles.by_id(uid) or {}).get('name') or 'Die Person'} ist gerade in einem Termin."}
    return None


def im_termin(evs, now):
    """True when one of the events (calendars.events) with a time of day runs at now (an aware datetime)."""
    return any(not x.get("allday") and x["start"] <= now < x["end"] for x in evs)


async def minute(now=None):
    """Every minute (panel.every_minute): busy while an appointment runs (begleiter.set_busy "termin"), and not any
    more after it, then the held notes come as one summary. Returns how many profiles are busy because of one."""
    now = time.time() if now is None else now
    t = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    for uid in set(calendars._used) | _termin:
        busy = False
        if features.allowed(BUSY_KEY, uid):
            try:
                r = await asyncio.wait_for(calendars.events(uid, t - datetime.timedelta(hours=12),
                                                            t + datetime.timedelta(minutes=1), datetime.timezone.utc,
                                                            stale=True), BUSY_WAIT)
            except (asyncio.TimeoutError, OSError, ValueError):
                continue                      # the calendar is slow: as it was, asked again next minute
            busy = bool(r) and im_termin(r[0], t)
        why = begleiter.quiet_why(uid, now)
        if busy:
            if why and why != "termin":       # the Begleiter's own „Nicht stören“ already holds everything
                continue
            held = begleiter.set_busy(uid, True, "termin", now)
            if held:                          # a busy time that ran out: its summary first, then busy again
                await begleiter.release(uid, held)
                begleiter.set_busy(uid, True, "termin", now)
            if uid not in _termin:
                _termin.add(uid)
                _count.bump("termine")
                print(f"calendar: busy on, appointment | {_who(uid)}", flush=True)
        elif uid in _termin:
            _termin.discard(uid)
            if why == "termin":
                await begleiter.release(uid, begleiter.set_busy(uid, False, "termin", now))
            print(f"calendar: busy off | {_who(uid)}", flush=True)
    return len(_termin)


def _clean(text, n):
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(text or "")).strip()
    return text[:n]


def speichern(uid, b, now=None):
    """Saves the entry from the page or an app: {von, bis (YYYY-MM-DD), text, vertretung, mail, kalender, tz}."""
    if not isinstance(b, dict):
        raise ValueError("Bitte Von und Bis angeben.")
    von, bis = str(b.get("von") or ""), str(b.get("bis") or "")
    try:
        if not (DATE.fullmatch(von) and DATE.fullmatch(bis)):
            raise ValueError
        d0, d1 = datetime.date.fromisoformat(von), datetime.date.fromisoformat(bis)
    except ValueError:
        raise ValueError("Bitte Von und Bis als Datum angeben.")
    if d1 < d0:
        raise ValueError("Bis liegt vor Von.")
    if (d1 - d0).days + 1 > MAX_DAYS:
        raise ValueError(f"Höchstens {MAX_DAYS} Tage am Stück.")
    tz = str(b.get("tz") or "")[:64]
    a = {"von": von, "bis": bis, "text": _clean(b.get("text"), MAX_TEXT), "vertretung": _clean(b.get("vertretung"), MAX_NAME),
         "mail": bool(b.get("mail")), "kalender": b.get("kalender") is not False, "tz": tz if ZONE.fullmatch(tz) else ""}
    if span(a)[1] <= (time.time() if now is None else now):
        raise ValueError("Der letzte Tag ist schon vorbei.")
    with _lock:
        STORE.load(uid)["a"] = a
        STORE.changed(uid, force=True)
    _count.bump("gespeichert")
    print(f"calendar: away saved | {(d1 - d0).days + 1} tage | {_who(uid)}", flush=True)
    _changed(uid)
    return eintrag(uid)


def _drop(uid, why):
    with _lock:
        STORE.load(uid).pop("a", None)
        STORE.changed(uid, force=True)
    _count.bump("geloescht")
    print(f"calendar: away deleted, {why} | {_who(uid)}", flush=True)
    _changed(uid)


def loeschen(uid):
    if not _read(uid):
        return False
    _drop(uid, "by hand")
    return True


def _changed(uid):
    for f in ON_CHANGE:
        try:
            f(uid)
        except Exception as e:   # a hook never stops the save
            print(f"calendar: away hook failed ({type(e).__name__}) | {_who(uid)}", flush=True)


def kalender(uid, day, days, zone):
    """calendars.EXTRA: the calendar „Abwesenheit“ with the all-day entry, when it falls into the days shown."""
    if not features.allowed(KEY, uid):
        return None
    a = eintrag(uid)
    if not a or not a["kalender"]:
        return None
    w0 = datetime.datetime.combine(day, datetime.time(), zone).timestamp()
    if a["end"] <= w0 or a["start"] >= w0 + days * 86400 + 7200:
        return None
    title = "Abwesend" + (f" · Vertretung {a['vertretung']}" if a["vertretung"] else "")
    return CAL, "abwesend", [{"start": a["start"], "end": a["end"], "allday": True, "title": title}]


def anruf(uid):
    """anrufe.start: the call to uid rings not while it is away (counted for Live)."""
    if jetzt(uid):
        _count.bump("anrufe")
        return True
    return False


def for_live():
    """Zustand → Live, node Kalender: on or off, how many profiles are away now, calls not rung today (numbers)."""
    now = time.time()
    n = 0
    for p in profiles.names():
        a = _read(p.get("id")) if p.get("id") else None
        if a:
            t0, t1 = span(a)
            n += t0 <= now < t1
    return {"on": bool(features.chat_cfg().get("away")), "weg": n, "anrufe": _count.counts()["anrufe"],
            "busy_on": bool(features.chat_cfg().get("calendar_busy")), "termin": len(_termin),
            "termine": _count.counts()["termine"]}


calendars.EXTRA.append(kalender)
calendars.LIVE["abwesend"] = lambda: for_live()
profiles.AWAY.append(away)


# ---------------------------------------------------------------- API (Kalender → Einstellungen, apps)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import guard  # noqa: E402
from core import assistant, json_body, own_profile  # noqa: E402

router = APIRouter()


def _mine(request, prof):
    guard.limit(request, "kalenderaendern", prof["id"])
    if not features.allowed(KEY, prof["id"]):
        print(f"calendar: away refused, off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, features.missing_text(KEY, prof["id"]) or "Abwesenheit ist aus.")


@router.get("/api/profile/abwesenheit", dependencies=[Depends(assistant)])
def api_get(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    return {"eintrag": eintrag(prof["id"]), "max_text": MAX_TEXT, "max_days": MAX_DAYS}


@router.put("/api/profile/abwesenheit", dependencies=[Depends(assistant)])
async def api_put(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    b = await json_body(request, 4 * 1024 + 2 * MAX_TEXT)
    try:
        return {"eintrag": speichern(prof["id"], b)}
    except ValueError as e:
        print(f"calendar: away refused, input | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, str(e)[:200])


@router.delete("/api/profile/abwesenheit", dependencies=[Depends(assistant)])
def api_delete(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    if not loeschen(prof["id"]):
        print(f"calendar: away delete, none | {profiles.log_name(prof)}", flush=True)
    return {"eintrag": None}
