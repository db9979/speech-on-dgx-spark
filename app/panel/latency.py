"""How long people wait: the time from the question to the first sound of the answer, for every
answer of the assistant (chat.py), kept for two weeks in STATE/latency.json.

Zustand → Prüfen shows the median of the last 24 hours and of the six days before, and the page warns
(health.alerts) when answers became clearly slower, e.g. while qwen38 is busy or memory runs short.
Nothing personal is kept: only the time, the seconds and the kind of client (web, speaker, watch ...).

Since plan genauer-und-schneller (1) each answer also keeps, as fixed words and numbers (MEASURE): the Weiche group,
the number of tools offered, the model rounds, the share the model read from its cache, the seconds to its first
character and to the end, and the version. Zustand → Prüfen then shows the last 7 days per group and the last versions
side by side, so every change can be judged by its numbers.
"""
import json
import os
import re
import statistics
import threading
import time

from common import STATE, write_json

KEEP_DAYS, MAX_ENTRIES = 14, 5000
DAY = 86400
_lock = threading.Lock()


def _file():
    return os.path.join(STATE, "latency.json")


def _load():
    try:
        with open(_file()) as f:
            d = json.load(f)
        return [x for x in d if isinstance(x, dict) and isinstance(x.get("t"), (int, float))
                and isinstance(x.get("a"), (int, float))] if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


# what an answer may keep besides its first sound: key -> check (fixed words and numbers only, never text)
_SECS = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 3600   # noqa: E731
MEASURE = {"g": lambda v: isinstance(v, str) and re.fullmatch(r"[a-z_@]{1,24}(?:\+[a-z_@]{1,24}){0,3}", v),
           "n": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 500,
           "r": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 20,
           "h": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100,
           "f": _SECS, "e": _SECS,
           "v": lambda v: isinstance(v, str) and re.fullmatch(r"V\d{2}\.\d\.\d{3,4}", v)}


def add(seconds, client="web", now=None, measure=None):
    """Notes one answer: seconds until its first sound (called off the event loop), with what MEASURE allows of
    measure (Weiche group, tools, rounds, cache share, first character, end, version)."""
    now = time.time() if now is None else now
    if not isinstance(seconds, (int, float)) or not 0 <= seconds < 3600:
        return
    client = client if isinstance(client, str) and re.fullmatch(r"[a-z]{1,12}", client) else "other"
    rec = {"t": round(now), "a": round(seconds, 2), "c": client}
    for k, v in (measure or {}).items():
        if k in MEASURE and MEASURE[k](v):
            rec[k] = round(v, 2) if isinstance(v, float) else v
    with _lock:
        items = [x for x in _load() if x["t"] > now - KEEP_DAYS * DAY]
        items = (items + [rec])[-MAX_ENTRIES:]
        write_json(_file(), items, mode=0o600)


def _med(values):
    return round(statistics.median(values), 2) if values else None


def by_group(items, now, days=7):
    """Per Weiche group of the last days: answers, median and p90 to the first sound, median to the first
    character and to the end, cache share and tools offered (medians), the slowest group first."""
    rows = {}
    for x in items:
        if x["t"] > now - days * DAY and x.get("g"):
            rows.setdefault(x["g"], []).append(x)
    out = []
    for g, xs in rows.items():
        s = _stats([x["a"] for x in xs])
        out.append(dict(s, group=g, first=_med([x["f"] for x in xs if "f" in x]), end=_med([x["e"] for x in xs if "e" in x]),
                        cache=_med([x["h"] for x in xs if "h" in x]), tools=_med([x["n"] for x in xs if "n" in x]),
                        rounds=_med([x["r"] for x in xs if "r" in x])))
    return sorted(out, key=lambda r: -r["median"])[:20]


def by_version(items, last=4):
    """The newest versions that answered, newest first: answers, median and p90 to the first sound, cache share."""
    rows = {}
    for x in items:
        if x.get("v"):
            rows.setdefault(x["v"], []).append(x)
    key = lambda v: tuple(int(p) for p in re.findall(r"\d+", v))   # noqa: E731
    return [dict(_stats([x["a"] for x in rows[v]]), version=v, cache=_med([x["h"] for x in rows[v] if "h" in x]))
            for v in sorted(rows, key=key, reverse=True)[:last]]


def add_ack(seconds, now=None):
    """Notes when the ready-made sentence (ack.py) sounded: kept apart, it never counts as the answer's first sound."""
    now = time.time() if now is None else now
    if not isinstance(seconds, (int, float)) or not 0 <= seconds < 3600:
        return
    with _lock:
        items = [x for x in _load() if x["t"] > now - KEEP_DAYS * DAY]
        items = (items + [{"t": round(now), "a": round(seconds, 2), "c": "web", "k": "ack"}])[-MAX_ENTRIES:]
        write_json(_file(), items, mode=0o600)


def _stats(values):
    if not values:
        return None
    values = sorted(values)
    return {"n": len(values), "median": round(statistics.median(values), 2),
            "p90": round(values[min(len(values) - 1, int(len(values) * 0.9))], 2)}


def summary(now=None):
    """The last 24 hours (with answers per hour), the six days before, and a warning sentence when answers got
    slower."""
    now = time.time() if now is None else now
    loaded = _load()
    items = [x for x in loaded if x.get("k") != "ack"]   # the answer's first sound only
    day = [x["a"] for x in items if x["t"] > now - DAY]
    week = [x["a"] for x in items if now - 7 * DAY < x["t"] <= now - DAY]
    acks = [x["a"] for x in loaded if x.get("k") == "ack" and x["t"] > now - DAY]
    # answers per hour of the last 24 hours, oldest first, the last one is the running hour (Zustand „Heute“ bars)
    hours = [0] * 24
    for x in items:
        if now - DAY < x["t"] <= now:
            hours[23 - min(23, int((now - x["t"]) // 3600))] += 1
    res = {"day": _stats(day), "week": _stats(week), "ack": _stats(acks), "warn": None, "hours": hours,
           "groups": by_group(items, now), "versions": by_version(items)}
    d, w = res["day"], res["week"]
    # clearly slower: at least 10 answers today, median more than 1.5 times and 1.5 s above the week's
    if d and w and d["n"] >= 10 and w["n"] >= 10 and d["median"] > 1.5 * w["median"] and d["median"] > w["median"] + 1.5:
        res["warn"] = (f"Antworten sind langsamer geworden: bis zum ersten Ton im Mittel {d['median']:g} s "
                       f"(sonst {w['median']:g} s). Läuft qwen38 gerade viel oder ist der Speicher knapp?")
    return res
