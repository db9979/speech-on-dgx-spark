"""Answer check: the panel, not the model, decides whether a sentence may be said. Only for data
questions (the question needs a tool, or a tool ran in this answer). A sentence is held back when it
names a time, a date, a score or an amount of money that is nowhere in what the model was given (the
question, the conversation, the instructions with today's date, the tool results of this answer).
Only figures written with digits (or a score in words) are checked, so a plain sentence never falls
out; "10:00" counts as "10 Uhr", "13.10.2026" as "13. Oktober", "3:1" as "3 zu 1".
"""
import re

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
    for m in MONEY.finditer(low):
        if m.group(1):
            whole, cents = re.sub(r"[.\s]", "", m.group(1)), m.group(2) or m.group(3) or "0"
        else:
            whole, cents = m.group(4), m.group(5) or "0"
        out.add(("m", int(whole), int(cents.ljust(2, "0"))))
    return out


def known(texts):
    """Every figure the model was given. A score "3:1" in a result also stands for the time-like
    reading and the other way round, so neither spelling is held back."""
    have = set()
    for t in texts:
        if isinstance(t, str):
            have |= facts(t)
    for k in list(have):
        if k[0] == "t":
            have.add(("s", k[1], k[2]))
    return have


def unsupported(sentence, have):
    """The figures of sentence that are not in have (empty: the sentence may be said)."""
    miss = []
    for f in sorted(facts(sentence)):
        if f in have:
            continue
        if f[0] == "t" and f[2] == 0 and any(k[0] == "t" and k[1] == f[1] for k in have):
            continue  # "um 10" for 10:15 is vague, not made up
        if f[0] == "t" and ("t", f[1] + 12 if f[1] < 12 else f[1] - 12, f[2]) in have:
            continue  # "um 2 Uhr" for 14:00
        miss.append(f)
    return miss


def label(f):
    return {"t": "{1}:{2:02d} Uhr", "d": "{1}.{2}.", "s": "{1}:{2}", "m": "{1},{2:02d} €"}[f[0]].format(*f)


FALLBACK = {"de": "Genauere Angaben dazu habe ich nicht.", "en": "I have no more precise details on that."}
RETRY_NOTE = ("(Für diese Frage brauchst du zuerst das passende Werkzeug. Rufe es jetzt auf und antworte nicht aus "
              "dem Gedächtnis.)")
