"""Tagesaktuell (Dominik 2026-10-21 „sämtliche Informationen immer aktuell überprüfen, ob das aktuelle Daten sind“):
fixed rules of the panel, never of the model, that hold every source against today's date.

- stand(): the one way to say how old a reading is, always with its day („heute 06:40“, „gestern 18:00“,
  „Montag 19.10., 18:00“). vorrat.stand (calendar, weather, parcels), mail._as_of and the morning briefing take it;
  a reading from yesterday never sounds like one from this morning again („Stand 18:00“ was said at 7 in the morning).
- The web search (chat.web_search): the person's own words or the query asking for today (HEUTE) or the last days
  (WOCHE) ask SearXNG for that period (time_range), news words also in its news category; every hit carries its date
  („Datum: heute 06:10“ / „ohne Datum“), and for such a question a hit dated before the period is dropped. When no hit
  of the period is left, the result says so with the newest date found, and the answer says it too (nachsatz).
- nachsatz(): the rule „Stand nennen“ of the Antwort-Prüfung (chat.answer_check): a reading that was not current
  (vorrat „alt“), a search without a hit of its period or an article from an own Kiwix book older than ARCHIV_TAGE
  (note_archive), and the answer did not say so: the panel adds one fixed sentence. The morning briefing as a push
  gets the same sentence (chat.due_briefings).

Logs: „frisch:“ with fixed words and numbers only; Live (node Websuche): today's numbers, never a query or a title.
"""
import datetime
import re
import threading
import time

# own words or the query: the person wants what is new today (time_range day) or of the last days (week)
HEUTE = re.compile(r"(?i)\b(heute\w*|heutig\w*|aktuell\w*|neueste\w*|neuste\w*|tagesaktuell\w*|nachrichten|news|"
                   r"schlagzeilen|today\w*|latest|breaking|morgenbericht|tagesbriefing)\b")
WOCHE = re.compile(r"(?i)\b(gestern|vorgestern|diese[rnms]? woche|letzte[rn]? tage|in den letzten tagen|"
                   r"seit (?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)|am wochenende|"
                   r"yesterday|this week|past few days|recent\w*)\b")
NEWS = re.compile(r"(?i)\b(nachrichten|news|schlagzeilen|meldung(?:en)?|headlines?|politisch|tagesschau)\b")
# how far back a dated hit may be for that period (a day: also last evening's news in the morning, said with its day)
WINDOW = {"day": 36 * 3600, "week": 8 * 86400}
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_lock = threading.Lock()
_today = {"day": "", "searches": 0, "old": 0, "dropped": 0, "hints": 0}   # Live: numbers of today, RAM only


def _zone(zone):
    if zone is not None:
        return zone
    import chat     # late: chat imports this module's users
    return chat.system_zone()


def stand(when, now=None, zone=None):
    """„heute 06:40“, „gestern 18:00“, „Montag 19.10., 18:00“ (within the week), „19.10.2025, 18:00“ for a
    reading at the unix time `when`; the day always comes with it."""
    zone = _zone(zone)
    at = datetime.datetime.fromtimestamp(when, zone)
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now, zone).date()
    days = (today - at.date()).days
    if days == 0:
        return f"heute {at:%H:%M}"
    if days == 1:
        return f"gestern {at:%H:%M}"
    if 1 < days < 7:
        return f"{WEEKDAYS[at.weekday()]} {at:%d.%m.}, {at:%H:%M}"
    return f"{at:%d.%m.%Y}, {at:%H:%M}"


def is_today(when, now=None, zone=None):
    zone = _zone(zone)
    return (datetime.datetime.fromtimestamp(when, zone).date()
            == datetime.datetime.fromtimestamp(time.time() if now is None else now, zone).date())


def zeitraum(*texts):
    """"day", "week" or "" for the person's words and the query (fixed words only, never the model's judgement)."""
    t = " ".join(str(x or "")[:400] for x in texts)
    return "day" if HEUTE.search(t) else "week" if WOCHE.search(t) else ""


def news(*texts):
    return bool(NEWS.search(" ".join(str(x or "")[:400] for x in texts)))


def hit_time(x):
    """The unix time a search hit was published (SearXNG publishedDate / pubdate), or None."""
    raw = str((x or {}).get("publishedDate") or (x or {}).get("pubdate") or "").strip()
    if not re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    try:
        d = datetime.datetime.fromisoformat(raw[:25].replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        try:
            d = datetime.datetime.fromisoformat(raw[:10])
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    t = d.timestamp()
    return t if t <= time.time() + 86400 else None    # a date in the future is no date


def _count(key, n=1):
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _today["day"] != day:
            _today.update(day=day, searches=0, old=0, dropped=0, hints=0)
        _today[key] += n


def sieve(results, period, now=None, zone=None, note=True):
    """The hits of a search for `period` ("day"/"week"/""): (kept hits, each with "_when", the newest dated time or None,
    whether a hit of the period is among them). For a period, hits dated before it are dropped. note: the answer says
    it when nothing of the period was found (not for the briefing's topics: a quiet topic is no news)."""
    now = time.time() if now is None else now
    for x in results:
        x["_when"] = hit_time(x)
    dated = [x["_when"] for x in results if x["_when"]]
    newest = max(dated) if dated else None
    if not period:
        return results, newest, True
    edge = now - WINDOW[period]
    kept = [x for x in results if not x["_when"] or x["_when"] >= edge]
    dropped = len(results) - len(kept)
    inside = any(x["_when"] and x["_when"] >= edge for x in kept)
    _count("searches")
    if dropped:
        _count("dropped", dropped)
        print(f"frisch: search dropped | {dropped} old hits | {period}", flush=True)
    if not inside:
        _count("old")
        print(f"frisch: search without a current hit | {period}", flush=True)
        if note:
            note_search(newest or 0)
    return kept, newest, inside


def hit_line(x, now=None, zone=None):
    """„Datum: heute 06:10“ or „Datum: unbekannt“ for the text the model gets."""
    return f"Datum: {stand(x['_when'], now, zone)}" if x.get("_when") else "Datum: unbekannt"


def nothing_current(period, newest, now=None, zone=None):
    """The line on top of a search result without a hit of its period."""
    span = "von heute" if period == "day" else "aus den letzten Tagen"
    old = f" Der neueste Treffer mit Datum ist von {stand(newest, now, zone)}." if newest else ""
    return (f"Kein Treffer {span} gefunden.{old} Say clearly that you found nothing {span} and give the date of what "
            "you report; never present an older hit as today's news.")


# ---------------------------------------------------------------- the answer's notes (vorrat's turn state)
def note_search(newest):
    """A search of this answer had no hit of its period (newest: its newest dated hit or 0)."""
    import vorrat
    cur = vorrat.current()
    if cur is not None:
        cur.setdefault("frisch", {})["suche"] = newest


ARCHIV_TAGE = 365   # an archive book (own Kiwix) older than this gets its date said (Dominik 2026-10-21)


def note_archive(date, turn_state=None):
    """An answer read an article from an own Kiwix book of this date ("2024-03" or "2024-03-15"); the oldest counts.
    turn_state: the answer's notes where no tool runs yet (the quick look of „Erst lokal suchen“)."""
    import vorrat
    cur = turn_state if isinstance(turn_state, dict) else vorrat.current()
    date = str(date or "")[:10]
    if cur is not None and re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", date):
        f = cur.setdefault("frisch", {})
        if not f.get("archiv") or date < f["archiv"]:
            f["archiv"] = date


def archive_old(date, now=None, zone=None):
    """The book's date („2024-03“) lies more than ARCHIV_TAGE days before today."""
    try:
        d = datetime.date.fromisoformat(date if len(date) == 10 else date + "-01")
    except ValueError:
        return False
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now, _zone(zone)).date()
    return (today - d).days > ARCHIV_TAGE


DIENST_NAME = {"mail": ("E-Mails", "e-mail"), "calendar": ("Kalender", "calendar"), "weather": ("Wetter", "weather"),
               "parcels": ("Pakete", "parcels")}


def nachsatz(turn_state, said, en=False, now=None, zone=None):
    """The fixed sentence the panel adds when this answer used a reading that was not current, or a search found
    nothing of its period, and the answer did not say so itself; "" otherwise."""
    cur = turn_state if isinstance(turn_state, dict) else {}
    said = str(said or "")
    parts = []
    for d, when in sorted((cur.get("when") or {}).items()):
        if d not in DIENST_NAME or not when:
            continue
        at = stand(when, now, zone)
        if at.split(" ")[-1] in said and ("gestern" not in at or "gestern" in said.lower()):
            continue   # the answer said the time (and the day, when it was not today)
        name = DIENST_NAME[d][1 if en else 0]
        parts.append(f"{name}: as of {at}" if en else f"{name}: Stand {at} Uhr")
        print(f"frisch: hint said | {d} | {'today' if is_today(when, now, zone) else 'older'}", flush=True)
    if "suche" in (cur.get("frisch") or {}):
        newest = cur["frisch"]["suche"]
        low = said.lower()
        if not any(w in low for w in ("nichts aktuelles", "nichts von heute", "nicht von heute", "keine aktuellen",
                                      "nothing current", "nothing from today")) \
                and not (newest and stand(newest, now, zone).split(",")[0].split(" ")[0] in low):
            if en:
                parts.append("I found nothing current on the web" + (f", the newest hit is from {stand(newest, now, zone)}" if newest else ""))
            else:
                parts.append("Aktuelles von heute habe ich im Netz nicht gefunden"
                             + (f", der neueste Treffer ist von {stand(newest, now, zone)}" if newest else ""))
            print("frisch: hint said | search | older", flush=True)
    old = (cur.get("frisch") or {}).get("archiv")
    if old and archive_old(old, now, zone) and old[:4] not in said:   # the answer did not name the archive's year
        parts.append(f"archive: as of {old}" if en else f"Archiv: Stand {old}")
        print("frisch: hint said | archive | older", flush=True)
    if not parts:
        return ""
    _count("hints")
    return ("Not quite current: " if en else "Nicht ganz aktuell: ") + "; ".join(parts) + "."


# ---------------------------------------------------------------- spanne: a period from the person's own words
# (plan such-index Stufe C): the one place that turns „gestern“, „letzte Woche“, „im März“, „2023“ or „vor 3 Wochen“
# into unix times, by fixed rules (Finden's filter, wissen.recent_window). Never the model; no clock inside (now given).
MONATE = (("januar", "jänner", "january", "jan"), ("februar", "feber", "february", "feb"), ("märz", "maerz", "march", "mar"),
          ("april", "apr"), ("mai", "may"), ("juni", "june", "jun"), ("juli", "july", "jul"), ("august", "aug"),
          ("september", "sept", "sep"), ("oktober", "october", "okt", "oct"), ("november", "nov"),
          ("dezember", "december", "dez", "dec"))
_MONAT = {w: i + 1 for i, ws in enumerate(MONATE) for w in ws}
ZAHLWORTE = {"ein": 1, "einem": 1, "einer": 1, "one": 1, "a": 1, "an": 1, "zwei": 2, "two": 2, "drei": 3, "three": 3,
             "vier": 4, "four": 4, "fünf": 5, "five": 5, "sechs": 6, "six": 6, "sieben": 7, "seven": 7, "acht": 8,
             "eight": 8, "neun": 9, "nine": 9, "zehn": 10, "ten": 10, "elf": 11, "eleven": 11, "zwölf": 12, "twelve": 12}
_M = "|".join(sorted(_MONAT, key=len, reverse=True))
_N = r"\d{1,2}|" + "|".join(sorted(ZAHLWORTE, key=len, reverse=True))
SPANNE = (   # (kind, pattern); a match of a longer kind first, the words stand as said (one line, lower case)
    ("monatjahr", re.compile(r"(?i)(?<!\w)(" + _M + r")\.?\s+(19[5-9]\d|20\d\d)(?!\w)")),
    ("vor", re.compile(r"(?i)(?<!\w)(?:vor\s+(" + _N + r")\s+(tag(?:en)?|woche(?:n)?|monat(?:en)?|jahr(?:en)?)|"
                       r"(" + _N + r")\s+(days?|weeks?|months?|years?)\s+ago)(?!\w)")),
    ("relativ", re.compile(r"(?i)(?<!\w)(vorgestern|gestern|heute|yesterday|today|"
                           r"(?:diese[nmrs]?|letzte[nmrs]?|vergangene[nmrs]?|vorige[nmrs]?|this|last|past)\s+"
                           r"(?:woche|monat|jahr|week|month|year)|im vorjahr)(?!\w)")),
    ("monat", re.compile(r"(?i)(?<!\w)(?:im|in|vom|seit|ab|von|aus dem|during)\s+(" + _M + r")(?!\w)")),
    ("jahr", re.compile(r"(?<![\w.,/-])(19[5-9]\d|20\d\d)(?![\w,/-]|\.\d)")),
)


def _tag0(now, zone):
    return datetime.datetime.fromtimestamp(now, zone).replace(hour=0, minute=0, second=0, microsecond=0)


def _ts(d):
    return int(d.timestamp())


def _monat0(year, month, zone):
    return datetime.datetime(year, month, 1, tzinfo=zone)


def _plus_monate(d, n):
    m = d.month - 1 + n
    return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)


def _eine(kind, m, now, zone):
    """(von, bis) of one match: bis is the exclusive end, None for a period still running („heute“, „diese Woche“)."""
    day = _tag0(now, zone)
    if kind == "monatjahr":
        a = _monat0(int(m.group(2)), _MONAT[m.group(1).lower()], zone)
        return _ts(a), _ts(_plus_monate(a, 1))
    if kind == "jahr":
        y = int(m.group(1))
        return _ts(datetime.datetime(y, 1, 1, tzinfo=zone)), _ts(datetime.datetime(y + 1, 1, 1, tzinfo=zone))
    if kind == "monat":
        mon = _MONAT[m.group(1).lower()]
        year = day.year if mon <= day.month else day.year - 1   # the last such month that has begun
        a = _monat0(year, mon, zone)
        return _ts(a), _ts(_plus_monate(a, 1))
    monday = day - datetime.timedelta(days=day.weekday())
    first = day.replace(day=1)
    jan = day.replace(month=1, day=1)
    if kind == "vor":
        n = m.group(1) or m.group(3)
        n = int(n) if n.isdigit() else ZAHLWORTE[n.lower()]
        unit = (m.group(2) or m.group(4)).lower()
        if unit.startswith(("tag", "day")):
            a = day - datetime.timedelta(days=n)
            return _ts(a), _ts(a + datetime.timedelta(days=1))
        if unit.startswith(("woche", "week")):
            a = monday - datetime.timedelta(days=7 * n)
            return _ts(a), _ts(a + datetime.timedelta(days=7))
        if unit.startswith(("monat", "month")):
            a = _plus_monate(first, -n)
            return _ts(a), _ts(_plus_monate(a, 1))
        a = jan.replace(year=jan.year - n)
        return _ts(a), _ts(a.replace(year=a.year + 1))
    w = re.sub(r"\s+", " ", m.group(1).lower())
    if w in ("heute", "today"):
        return _ts(day), None
    if w in ("gestern", "yesterday"):
        return _ts(day - datetime.timedelta(days=1)), _ts(day)
    if w == "vorgestern":
        return _ts(day - datetime.timedelta(days=2)), _ts(day - datetime.timedelta(days=1))
    now_ = w.startswith(("diese", "this"))
    if w == "im vorjahr" or w.endswith(("jahr", "year")):
        return (_ts(jan), None) if now_ else (_ts(jan.replace(year=jan.year - 1)), _ts(jan))
    if w.endswith(("monat", "month")):
        return (_ts(first), None) if now_ else (_ts(_plus_monate(first, -1)), _ts(first))
    return (_ts(monday), None) if now_ else (_ts(monday - datetime.timedelta(days=7)), _ts(monday))


def spanne(text, now, zone=None):
    """(von, bis, (start, end)) for the period the words name, or None: von/bis unix seconds (bis exclusive, None for a
    period still running), (start, end) where in the text it was said (the caller can leave those words out of a
    search). Fixed rules only; the first kind of SPANNE that matches wins; two different periods of one kind (2022 und
    2023) are no period."""
    text = str(text or "")[:2000]
    zone = _zone(zone)
    for kind, rx in SPANNE:
        found = list(rx.finditer(text))
        if not found:
            continue
        spans = {_eine(kind, m, now, zone) for m in found}
        if len(spans) != 1:
            return None
        von, bis = spans.pop()
        return von, bis, found[0].span()
    return None


def for_live():
    """Today: searches for a period, of them without a current hit, old hits dropped, hints added (numbers only)."""
    day = time.strftime("%Y-%m-%d")
    with _lock:
        return {k: _today[k] for k in ("searches", "old", "dropped", "hints")} if _today["day"] == day \
            else {"searches": 0, "old": 0, "dropped": 0, "hints": 0}


def live_sub():
    c = for_live()
    if not (c["searches"] or c["hints"]):
        return ""
    return (f" · tagesaktuell: heute {c['searches']} Suchen mit Zeitraum, {c['old']} ohne Treffer von heute, "
            f"{c['dropped']} alte Treffer verworfen, {c['hints']} Stand-Hinweise")
