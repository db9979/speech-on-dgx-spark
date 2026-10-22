"""Einfaches sofort beantworten (plan genauer-und-schneller, 6): a few plain questions get a fixed sentence from the
panel, without the language model, so the first sound comes at once.

With the admin switch chat.sofort (Funktionen → Einfaches sofort beantworten, off by default) the panel answers by
fixed rules, only when the whole short sentence is one of these questions:

    the time ("Wie spät ist es?", notbetrieb.UHR)                  "Es ist 14 Uhr 20."
    the date or the weekday ("Welcher Tag ist heute?")             "Heute ist Freitag, der 17. Oktober 2026."
    arithmetic ("Was ist 17 mal 23?", "Rechne (3 + 4) mal 5")      "17 mal 23 ist 391."
      with percent, brackets, powers and roots: rechnen.calc, the same core as the tool rechnen
    date arithmetic ("Wie viele Tage bis Weihnachten?", "Welcher Wochentag ist der 24.12.2026?",
      "Welches Datum ist in 90 Tagen?"): rechnen.days                 "Vom … bis … sind es 63 Tage …"
    units ("Wie viel sind 3 Zoll in Zentimeter?", room._CONV)      "3 Zoll sind etwa 7,6 Zentimeter."

Anything with more words, a place, a person or a wish goes to the model as before. No tool, no data of a profile, so
a guest gets it too (it is plain question and answer). Setting a timer stays with the model and its tool: that changes
something, and only the offered tool may do that. The clock comes from the caller (chat.local_now), never from here.
Logs: "chat: feste Antwort, <art>" with a fixed word.
"""
import re

import notbetrieb
import rechnen
import room

KINDS = ("uhrzeit", "datum", "rechnen", "tage", "einheit")
MAX_CHARS = 80          # longer sentences go to the model
_LEAD = r"\W*(?:(?:hey|hallo|ok)\s+)?(?:spark\W*\s*)?(?:(?:sag|verrat)\s+mir\s+(?:mal\s+)?(?:bitte\s+)?)?"
_END = r"\s*(?:bitte|denn|eigentlich|gerade|jetzt)?\s*[?.!]*\s*"
_DAY = re.compile(_LEAD + r"(?:(?:welcher|was für ein) (?:wochen)?tag ist (?:heute|es|morgen)|welches datum (?:ist|haben wir)"
                  r"(?: heute| morgen)?|(?:den |der )?wievielte(?:n)? (?:ist|haben wir) (?:heute|morgen)|"
                  r"(?:welchen|was für einen) tag haben wir(?: heute| morgen)?|"
                  r"what(?:'s| is) the date(?: today| tomorrow)?|what day is (?:it|today|tomorrow)(?: today)?)" + _END, re.I)
_MATH = re.compile(_LEAD + r"(?:(?:was|wie ?viel|what|how much)\s+(?:ist|sind|ergibt|ergeben|macht|is|are)|"
                   r"(?:rechne|berechne|calculate|compute)(?:\s+(?:mir\s+)?(?:mal|bitte)\s*)?(?:\s+aus)?)?\s*"
                   r"([-+(√\d][^\n]{0,70}?)\s*(?:aus)?" + _END, re.I)
_SAY_OPS = (("**", "^"), ("×", "*"), ("÷", "/"), ("·", "*"))
_SAY_WORD = {"+": ("plus", "plus"), "-": ("minus", "minus"), "*": ("mal", "times"), "/": ("geteilt durch", "divided by"),
             "^": ("hoch", "to the power of"), "%": ("Prozent", "percent"), "√": ("Wurzel aus", "square root of")}
_DAYS = re.compile(_LEAD + r"(?:wie ?viele tage (?:sind es |ist es |hat es )?(?:noch )?bis (?:zum |zu |)|"
                   r"how many days (?:are there |is it )?(?:left )?(?:until|till|to|before) )" + rechnen.DAY + _END, re.I)
_WDAY = re.compile(_LEAD + r"(?:(?:welcher|was für ein) (?:wochen)?tag ist (?:der |am )|auf welchen (?:wochen)?tag "
                   r"fällt (?:der )?|what day (?:of the week )?is )" + rechnen.DAY + _END, re.I)
_PLUS = re.compile(_LEAD + r"(?:(?:welches datum|welcher tag|was für ein datum) (?:ist|haben wir|ist es)(?: heute)? in|"
                   r"what (?:date|day) (?:is it|will it be|is) in) (\d{1,5}) (tagen|wochen|days|weeks)" + _END, re.I)
_UNIT = re.compile(_LEAD + r"(?:(?:wie ?viel|was)\s+(?:sind|ist|wären|entsprechen)\s+)?(.{3,60}?)" + _END, re.I)


def _date(text, now, en):
    import datetime
    day = now + datetime.timedelta(days=1) if re.search(r"(?i)\b(morgen|tomorrow)\b", text) else now
    when = ("Tomorrow" if en else "Morgen") if day is not now else ("Today" if en else "Heute")
    return f"{when} {'is' if en else 'ist'} {rechnen.long_day(day.date(), en)}."


def _math(m, en):
    """The fixed sentence for a calculation with at least two numbers (or a root), else None (the model answers)."""
    expr = m.group(1).strip()
    if len(re.findall(r"\d+", expr)) < 2 and not re.search(r"(?i)√|wurzel|square root", expr):
        return None
    try:
        v = rechnen.calc(expr, en)
    except rechnen.Fehler:
        return None
    for a, b in _SAY_OPS:
        expr = expr.replace(a, b)
    expr = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", expr)
    expr = re.sub(r"\s*([-+*/^%√])\s*", lambda x: " " + _SAY_WORD[x.group(1)][1 if en else 0] + " ", expr)
    expr = re.sub(r"(?<=\d) (?=Prozent|percent)", " ", re.sub(r"\s+", " ", expr)).strip()
    return f"{expr} {'is' if en else 'ist'} {rechnen.say(v, en)}."


def _days(text, now, en):
    """The fixed sentence for a date question (days until, the weekday of a day, the date in n days), else None."""
    today = now.date()
    try:
        m = _DAYS.fullmatch(text)
        if m:
            return rechnen.days("tage_bis", today, bis=m.group(1), en=en)
        m = _WDAY.fullmatch(text)
        if m and m.group(1).lower() not in ("heute", "morgen", "today", "tomorrow"):
            return rechnen.days("wochentag", today, datum=m.group(1), en=en)
        m = _PLUS.fullmatch(text)
        if m:
            n = int(m.group(1)) * (7 if m.group(2).lower() in ("wochen", "weeks") else 1)
            return rechnen.days("datum_plus", today, tage=n, en=en)
    except rechnen.Fehler:
        return None
    return None


def _unit(text):
    """The unit sentence when the whole question is one conversion (room._CONV), else None."""
    m = _UNIT.fullmatch(text)
    core = m.group(1) if m else ""
    for p in room._CONV:
        hit = p.fullmatch(core.strip())
        if hit:
            return room.conversion(hit.group(0))
    return None


def answer(text, now, en=False):
    """(kind, sentence) for a plain question, else None. `now` is the profile's local, aware datetime."""
    text = str(text or "").strip()
    if not text or len(text) > MAX_CHARS or "\n" in text:
        return None
    if notbetrieb.UHR.fullmatch(text):
        return "uhrzeit", notbetrieb.uhrzeit(now, en)[0]
    if _DAY.fullmatch(text):
        return "datum", _date(text, now, en)
    said = _days(text, now, en)
    if said:
        return "tage", said
    m = _MATH.fullmatch(text)
    said = _math(m, en) if m else None
    if said:
        return "rechnen", said
    if not en:
        said = _unit(text)
        if said:
            return "einheit", said
    return None
