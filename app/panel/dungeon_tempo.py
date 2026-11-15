"""KI-Dungeon-Master: how long the table waits (Prüfung 2026-11-15, Punkt 2, Dominik „1-11“).

Per day in memory, only numbers: the wait of every told turn from its close to the narration at the table, the
model's answers for the checks („proben“) and the narration („erzaehlen“, every try, rewrites too), and how many turns
needed at least one rewrite. Live (Zustand → Überblick) shows the mean and the longest wait, the mean per call and the
share of turns rewritten; a wish for speed is measured here first. The Erzähler-Prüfstand never counts (count=False).
"""
import time

from common import DayCounter

ARTEN = ("proben", "erzaehlen")
# per kind [answers, milliseconds in all, the longest]; "zug" the told turns, "neu" turns with a rewrite
_day = DayCounter(zug=[0, 0, 0], proben=[0, 0, 0], erzaehlen=[0, 0, 0], neu=0)


def uhr():
    """Seconds of a steady clock (tests replace it)."""
    return time.perf_counter()


def took(art, s):
    """One measured wait of art ("zug" or one of ARTEN), in seconds."""
    t = _day.today()
    ms = max(0, round(s * 1000))
    x = t[art]
    x[0] += 1
    x[1] += ms
    x[2] = max(x[2], ms)


def zug(s, neu):
    """A told turn: its wait and whether the narration was written anew at least once."""
    took("zug", s)
    if neu:
        _day.bump("neu")


def _mean_ms(x):
    return round(x[1] / x[0]) if x[0] else 0


def for_live():
    """Today's waits as whole numbers (dungeon.for_live puts them under tempo_): told turns, mean and longest wait in
    milliseconds, per kind of call its count and mean, the share of turns rewritten in per cent."""
    t = _day.counts()
    z = t["zug"]
    out = {"zuege": z[0], "mittel_ms": _mean_ms(z), "laengste_ms": z[2], "neu_pct": round(100 * t["neu"] / z[0]) if z[0] else 0}
    for a in ARTEN:
        out[a + "_n"], out[a + "_ms"] = t[a][0], _mean_ms(t[a])
    return out
