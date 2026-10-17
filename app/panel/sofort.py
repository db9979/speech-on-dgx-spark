"""Einfaches sofort beantworten (plan genauer-und-schneller, 6): a few plain questions get a fixed sentence from the
panel, without the language model, so the first sound comes at once.

With the admin switch chat.sofort (Funktionen → Einfaches sofort beantworten, off by default) the panel answers by
fixed rules, only when the whole short sentence is one of these questions:

    the time ("Wie spät ist es?", notbetrieb.UHR)                  "Es ist 14 Uhr 20."
    the date or the weekday ("Welcher Tag ist heute?")             "Heute ist Freitag, der 17. Oktober 2026."
    plain arithmetic ("Was ist 17 mal 23?")                        "17 mal 23 ist 391."
    units ("Wie viel sind 3 Zoll in Zentimeter?", room._CONV)      "3 Zoll sind etwa 7,6 Zentimeter."

Anything with more words, a place, a person or a wish goes to the model as before. No tool, no data of a profile, so
a guest gets it too (it is plain question and answer). Setting a timer stays with the model and its tool: that changes
something, and only the offered tool may do that. The clock comes from the caller (chat.local_now), never from here.
Logs: "chat: feste Antwort, <art>" with a fixed word.
"""
import re

import notbetrieb
import room

KINDS = ("uhrzeit", "datum", "rechnen", "einheit")
MAX_CHARS = 80          # longer sentences go to the model
_LEAD = r"\W*(?:(?:hey|hallo|ok)\s+)?(?:spark\W*\s*)?(?:(?:sag|verrat)\s+mir\s+(?:mal\s+)?(?:bitte\s+)?)?"
_END = r"\s*(?:bitte|denn|eigentlich|gerade|jetzt)?\s*[?.!]*\s*"
_DAY = re.compile(_LEAD + r"(?:(?:welcher|was für ein) (?:wochen)?tag ist (?:heute|es|morgen)|welches datum (?:ist|haben wir)"
                  r"(?: heute| morgen)?|(?:den |der )?wievielte(?:n)? (?:ist|haben wir) (?:heute|morgen)|"
                  r"(?:welchen|was für einen) tag haben wir(?: heute| morgen)?|"
                  r"what(?:'s| is) the date(?: today| tomorrow)?|what day is (?:it|today|tomorrow)(?: today)?)" + _END, re.I)
_NUM = r"(-?\d{1,9}(?:[.,]\d{1,6})?)"
_OPS = {"plus": "+", "+": "+", "und": "+", "minus": "-", "weniger": "-", "-": "-", "mal": "*", "x": "*", "×": "*",
        "*": "*", "times": "*", "geteilt durch": "/", "durch": "/", "/": "/", ":": "/", "divided by": "/"}
_OP = "(" + "|".join(re.escape(k) for k in sorted(_OPS, key=len, reverse=True)) + ")"
_MATH = re.compile(_LEAD + r"(?:was|wie ?viel|what|how much)\s+(?:ist|sind|ergibt|ergeben|macht|is|are)\s+"
                   + _NUM + r"\s*" + _OP + r"\s*" + _NUM + _END, re.I)
_UNIT = re.compile(_LEAD + r"(?:(?:wie ?viel|was)\s+(?:sind|ist|wären|entsprechen)\s+)?(.{3,60}?)" + _END, re.I)
_WEEKDAY = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
_WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTH = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")
_MONTH_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December")


def _num(x):
    return float(x.replace(",", "."))


def _say(v, en=False):
    """A result as it is spoken: whole numbers plain, else two places, "etwa" when it was rounded (German comma)."""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    s = s if en else s.replace(".", ",")
    return s if abs(v - round(v, 2)) < 1e-9 else ("about " if en else "etwa ") + s


def _date(text, now, en):
    import datetime
    day = now + datetime.timedelta(days=1) if re.search(r"(?i)\b(morgen|tomorrow)\b", text) else now
    when = ("Tomorrow" if en else "Morgen") if day is not now else ("Today" if en else "Heute")
    if en:
        return f"{when} is {_WEEKDAY_EN[day.weekday()]}, {_MONTH_EN[day.month - 1]} {day.day}, {day.year}."
    return f"{when} ist {_WEEKDAY[day.weekday()]}, der {day.day}. {_MONTH[day.month - 1]} {day.year}."


def _math(m, en):
    a, op, b = _num(m.group(1)), _OPS[m.group(2).lower()], _num(m.group(3))
    if op == "/" and b == 0:
        return None
    v = a + b if op == "+" else a - b if op == "-" else a * b if op == "*" else a / b
    if abs(v) >= 1e12:
        return None
    word = m.group(2) if m.group(2).isalpha() or " " in m.group(2) else \
        {"+": "plus", "-": "minus", "*": "times" if en else "mal", "/": "divided by" if en else "geteilt durch"}[op]
    return f"{m.group(1)} {word.lower()} {m.group(3)} {'is' if en else 'ist'} {_say(v, en)}."


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
    m = _MATH.fullmatch(text)
    if m:
        said = _math(m, en)
        return ("rechnen", said) if said else None
    if not en:
        said = _unit(text)
        if said:
            return "einheit", said
    return None
