"""Answer check: the panel, not the model, decides whether a sentence may be said. Only for data
questions (the question needs a tool, or a tool ran in this answer). A sentence is held back when it
names a time, a date, a score or an amount of money that is nowhere in what the model was given (the
question, the conversation, the instructions with today's date, the tool results of this answer).
Only figures written with digits (or a score in words) are checked, so a plain sentence never falls
out; "10:00" counts as "10 Uhr", "13.10.2026" as "13. Oktober", "3:1" as "3 zu 1".

Antwort-Prüfung erweitern (chat.answer_check_more, plan genauer-und-schneller, 9; off by default): also temperatures
("14 Grad", "-3 °C"), distances in km and percentages must be in what the model was given, with room for rounding
(MORE_SLACK: "14 Grad" for 14.3 is right, "20 Grad" for 14.3 is not), and a quoted name („Kaffee mit Anke“) must be
in it in every data answer, not only in one that read the calendar.
"""
import decimal
import re

import rechnen
import taten

MONTHS = {m: i + 1 for i, m in enumerate(
    ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
     "dezember"])}
MONTHS.update({"jänner": 1, "maerz": 3, "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
               "october": 10, "december": 12, "jan": 1, "feb": 2, "mär": 3, "apr": 4, "jun": 6, "jul": 7,
               "aug": 8, "sep": 9, "sept": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12})
WORDS = {w: i for i, w in enumerate(["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht",
                                     "neun", "zehn", "elf", "zwölf"])}
WORDS.update({"ein": 1, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10})
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM = "|".join(sorted(WORDS, key=len, reverse=True))
ISO = re.compile(r"\b\d{4}-(\d{2})-(\d{2})(?:[t ](\d{2}):(\d{2}))?")
TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*uhr\b|\b([01]?\d|2[0-3]):([0-5]\d)(?!\d)(?![.:]\d)"
                  r"|\b([01]?\d|2[0-3])\s*uhr(?:\s+([0-5]\d)\b)?")
DATE = re.compile(r"\b([0-3]?\d)\.\s?(1[0-2]|0?[1-9])\.|\b([0-3]?\d)\.?\s+(" + _MON + r")\b")
SCORE = re.compile(r"\b(\d{1,2})\s*(?::|zu|to)\s*(\d{1,2})\b(?![:.]\d)|\b(" + _NUM + r")\s+(?:zu|to)\s+(" + _NUM + r")\b")
MONEY = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,(\d{1,2})|\.(\d{2})(?!\d))?\s*(?:€|euro\b|eur\b)"
                   r"|(?:€|eur\b)\s*(\d+)(?:[.,](\d{1,2}))?")
# "13.10." alone is a date, never the time 13:10; "3:1" is a score, "10:00" a time
TIMELIKE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_V = r"((?:-|minus\s+)?\d{1,5}(?:[.,]\d{1,2})?)"
_RANGE = r"(?:" + _V + r"\s*(?:bis|und|to|and|-|–)\s*)?" + _V
DEGREES = re.compile(_RANGE + r"\s*(?:°\s*c\b|°(?!\s*f)|grad\b(?!\s+fahrenheit)|degrees?\s+celsius\b)")
KM = re.compile(_RANGE + r"\s*(?:km\b(?!/)|kilometer(?:n)?\b(?!\s+pro)|kilometres?\b(?!\s+per))")
PERCENT = re.compile(_RANGE + r"\s*(?:%|prozent\b|percent\b)")
MORE = {"c": DEGREES, "k": KM, "p": PERCENT}
# room for rounding, in tenths: a degree, a percent point, for km one km or a tenth of the value
MORE_SLACK = {"c": 10, "p": 10, "k": 10}


def _tenths(x):
    neg = x.startswith("-") or x.startswith("minus")
    v = round(float(re.sub(r"^(-|minus\s+)", "", x).replace(",", ".")) * 10)
    return -v if neg else v


def more_facts(text):
    """Temperatures, km and percentages in a text, as ("c"|"k"|"p", tenths)."""
    low = (text or "").lower()
    out = set()
    for kind, rx in MORE.items():
        for m in rx.finditer(low):
            for g in (m.group(1), m.group(2)):
                if g:
                    out.add((kind, _tenths(g)))
    return out


def facts(text):
    """The checked figures in a text as a set of tuples."""
    low = (text or "").lower()
    out = set()
    for m in ISO.finditer(low):
        out.add(("d", int(m.group(2)), int(m.group(1))))
        if m.group(3):
            out.add(("t", int(m.group(3)), int(m.group(4))))
    low_noiso = ISO.sub(" ", low)
    for m in DATE.finditer(low_noiso):
        if m.group(1):
            out.add(("d", int(m.group(1)), int(m.group(2))))
        else:
            out.add(("d", int(m.group(3)), MONTHS[m.group(4)]))
    nodate = DATE.sub(" ", low_noiso)
    for m in TIME.finditer(nodate):
        h, mi = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4)) if m.group(3) else (m.group(5), m.group(6))
        out.add(("t", int(h), int(mi or 0)))
    for m in SCORE.finditer(nodate):
        if m.group(1):
            if TIMELIKE.fullmatch(m.group(0).replace(" ", "")) and len(m.group(2)) == 2:
                continue  # 10:00 is a time
            out.add(("s", int(m.group(1)), int(m.group(2))))
        else:
            out.add(("s", WORDS[m.group(3)], WORDS[m.group(4)]))
    for m in _money(low):
        if m.group(1):
            whole, cents = re.sub(r"[.\s]", "", m.group(1)), m.group(2) or m.group(3) or "0"
        else:
            whole, cents = m.group(4), m.group(5) or "0"
        out.add(("m", int(whole), int(cents.ljust(2, "0"))))
    return out


CURRENCY = re.compile(r"€|eur")
NUMBERISH = set("0123456789., \t\n")


def _money(low):
    """MONEY matches, looked for only in a short window around each currency sign: run over a
    whole long text the pattern backtracks for every digit (a page of digits took seconds)."""
    seen = set()
    for c in CURRENCY.finditer(low):
        start, end = max(0, c.start() - 60), min(len(low), c.end() + 25)
        while start > 0 and start < c.start() and low[start - 1] in NUMBERISH:
            start += 1   # never start inside a number: a cut "12 345" would read as "345"
        for m in MONEY.finditer(low, start, end):
            if m.span() not in seen:
                seen.add(m.span())
                yield m


def calc_facts(values):
    """The panel's own results (rechnen.py) as figures the answer may name: an amount of money (to the cent) and, for
    the extended check, a percentage, km or degrees (in tenths)."""
    out = set()
    for v in values:
        if v is None or abs(v) >= 10 ** 12:
            continue
        cents = int(abs(v).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP) * 100)
        out.add(("m", cents // 100, cents % 100))
        tenths = int((v * 10).to_integral_value(rounding=decimal.ROUND_HALF_UP))
        out |= {(k, tenths) for k in MORE}
    return out


def known(texts, more=False):
    """Every figure the model was given. A score "3:1" in a result also stands for the time-like
    reading and the other way round, so neither spelling is held back. more: temperatures, km, percentages too.
    A result of the tool rechnen counts as money and, with more, as a percentage too (calc_facts)."""
    have = set()
    for t in texts:
        if isinstance(t, str):
            have |= facts(t) | (more_facts(t) if more else set()) | calc_facts([rechnen.value(t)])
    for k in list(have):
        if k[0] == "t":
            have.add(("s", k[1], k[2]))
    return have


def unsupported(sentence, have, more=False):
    """The figures of sentence that are not in have (empty: the sentence may be said)."""
    miss = []
    for f in sorted(facts(sentence) | (more_facts(sentence) if more else set())):
        if f in have:
            continue
        if f[0] in MORE:   # rounded is right, made up is not
            slack = max(MORE_SLACK[f[0]], abs(f[1]) // 10) if f[0] == "k" else MORE_SLACK[f[0]]
            if any(k[0] == f[0] and abs(k[1] - f[1]) <= slack for k in have):
                continue
            miss.append(f)
            continue
        if f[0] == "t" and f[2] == 0 and any(k[0] == "t" and k[1] == f[1] for k in have):
            continue  # "um 10" for 10:15 is vague, not made up
        if f[0] == "t" and ("t", f[1] + 12 if f[1] < 12 else f[1] - 12, f[2]) in have:
            continue  # "um 2 Uhr" for 14:00
        miss.append(f)
    return miss


def label(f):
    if f[0] in MORE:
        return f"{f[1] / 10:g} " + {"c": "Grad", "k": "km", "p": "%"}[f[0]]
    return {"t": "{1}:{2:02d} Uhr", "d": "{1}.{2}.", "s": "{1}:{2}", "m": "{1},{2:02d} €",
            "n": "Termin aus früherer Antwort", "q": "Name, der nirgends steht"}[f[0]].format(*f)


FALLBACK = {"de": "Genauere Angaben dazu habe ich nicht.", "en": "I have no more precise details on that."}
RETRY_NOTE = ("(Für diese Frage brauchst du zuerst das passende Werkzeug. Rufe es jetzt auf und antworte nicht aus "
              "dem Gedächtnis.)")


def fresh(msgs, have):
    """For an answer that read the calendar: times and dates count only when they are in the instructions,
    the question of this turn (with the panel's time note) or what came after it (the tool results).
    An appointment from an earlier answer in the conversation is not today's (Dominik, 2026-10-11:
    yesterday's appointments read out as today's). Other figures stay as known() found them."""
    return {f for f in have if f[0] not in ("t", "d")} | known(fresh_texts(msgs))


def fresh_texts(msgs):
    """The instructions, the question of this turn and everything after it (the tool results)."""
    msgs = [m for m in msgs if isinstance(m, dict)]
    last = max((i for i, m in enumerate(msgs) if m.get("role") == "user" and m.get("content") != RETRY_NOTE), default=0)
    return [m.get("content") for m in msgs if m.get("role") == "system"] + [m.get("content") for m in msgs[last:]]


OLD = ("n", 0, 0)   # held back: a quoted name not read in this answer (unquoted)
NAME = ("q", 0, 0)  # Antwort-Prüfung erweitern: a quoted name in nothing the model was given
QUOTED = re.compile(r"[„“\"»«]([^„“”\"»«\n]{2,80})[“”\"«»]")


def unquoted(sentence, texts):
    """The quoted names in sentence („deBug & Coffee“) that are in none of texts: in an answer that read the
    calendar, an appointment title the model quotes must come from this answer's results."""
    low = " ".join(t for t in texts if isinstance(t, str)).lower()
    return [m.group(1).strip() for m in QUOTED.finditer(sentence or "") if m.group(1).strip().lower() not in low]


# ---------------------------------------------------------------- built-in answer rules (taten.py)
# Handlungs-Prüfung and Fehlerschleife stoppen (Dominik 2026-10-12, plan handlungs-pruefung): fixed rules of the panel,
# shown in Zustand → Verbessern → Regeln as „eingebaut“ with how often they stepped in today; never removable there,
# only their switches (chat.action_check, chat.loop_stop, standard on) turn them off.
BUILTIN = {
    "action_check": ("Taten prüfen", "Check deeds",
                     "Ein Satz, der eine Tat behauptet oder ankündigt, die in dieser Antwort kein Werkzeug geschafft hat, "
                     "wird nicht gesagt; stattdessen ein ehrlicher Satz.",
                     "A sentence claiming or announcing a deed no tool managed in this answer is not said; an honest "
                     "sentence instead.",
                     "held"),
    "loop_stop": ("Fehlerschleife stoppen", "Stop error loops",
                  "Ein Werkzeug, das mit denselben Angaben zweimal gescheitert ist, läuft in dieser Antwort nicht noch "
                  "einmal.", "A tool that failed twice with the same details does not run again in this answer.",
                  "loop"),
}


def action_check(text, acts, offered, looked=False):
    """The built-in rule „Taten prüfen“ (chat.speak): the kinds of deed a finished sentence claims although no tool of
    that kind worked in this answer; the sentence is held back when this is not empty (taten.check decides)."""
    return taten.check(text, acts, offered, looked)


def builtin(ccfg, now=None):
    """The built-in rules for Verbessern → Regeln: name, what it does, switch state, how often today (numbers only)."""
    n = taten.for_live(now)
    return [{"key": k, "name": [de, en], "what": [wde, wen], "on": bool((ccfg or {}).get(k, True)),
             "today": int(n.get(cnt, 0))} for k, (de, en, wde, wen, cnt) in BUILTIN.items()]
