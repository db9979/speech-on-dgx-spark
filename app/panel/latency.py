"""How long people wait: the time from the question to the first sound of the answer, for every
answer of the assistant (chat.py), kept for two weeks in STATE/latency.json.

Zustand → Prüfen shows the median of the last 24 hours and of the six days before, and the page warns
(health.alerts) when answers became clearly slower, e.g. while qwen38 is busy or memory runs short.
Nothing personal is kept: only the time, the seconds and the kind of client (web, speaker, watch ...).

Since plan genauer-und-schneller (1) each answer also keeps, as fixed words and numbers (MEASURE): the Weiche group,
the number of tools offered, the model rounds, the share the model read from its cache, the seconds to its first
character and to the end, and the version. Zustand → Prüfen then shows the last 7 days per group and the last versions
side by side, so every change can be judged by its numbers.

Since plan vorrat-je-profil (1) also the seconds the tools took ("w") and, per service, whether its data came from the
memory of the service, as an older reading, or after waiting for the server ("s", vorrat.seen); Zustand → Prüfen
shows that per service (by_service).
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
SUMMARY_S = 10        # summary() without a fixed time is worked out again after this many seconds or a new answer
_lock = threading.Lock()
# the entries as last read or written, by the file's stamp (code check 19.10. B4: the file of about 600 KB was read
# whole twice per status question, every second by the case's screen and the Live page); the file always wins
_mem = {"stamp": None, "items": [], "summary": (0.0, None, None)}


def _file():
    return os.path.join(STATE, "latency.json")


def _stamp():
    try:
        st = os.stat(_file())
        return (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return None


def _load():
    stamp = _stamp()
    if stamp is not None and stamp == _mem["stamp"]:
        return list(_mem["items"])
    try:
        with open(_file()) as f:
            d = json.load(f)
        items = [x for x in d if isinstance(x, dict) and isinstance(x.get("t"), (int, float))
                 and isinstance(x.get("a"), (int, float))] if isinstance(d, list) else []
    except (OSError, ValueError):
        items = []
    _mem.update(stamp=stamp, items=items)
    return list(items)


def _save(items):
    write_json(_file(), items, mode=0o600)
    _mem.update(stamp=_stamp(), items=items)


# what an answer may keep besides its first sound: key -> check (fixed words and numbers only, never text)
_SECS = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 3600   # noqa: E731
MEASURE = {"g": lambda v: isinstance(v, str) and re.fullmatch(r"[a-z_@]{1,24}(?:\+[a-z_@]{1,24}){0,3}", v),
           "n": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 500,
           "r": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 20,
           "h": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100,
           "f": _SECS, "e": _SECS, "w": _SECS,
           "s": lambda v: isinstance(v, str) and re.fullmatch(r"[a-z]{3,12}:(?:warm|alt|kalt)(?:\+[a-z]{3,12}:(?:warm|alt|kalt)){0,7}", v),
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
        _save((items + [rec])[-MAX_ENTRIES:])


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
                        rounds=_med([x["r"] for x in xs if "r" in x]), wait=_med([x["w"] for x in xs if "w" in x])))
    return sorted(out, key=lambda r: -r["median"])[:20]


def by_service(items, now, days=7):
    """Per service of the last days (vorrat.py): answers that used it, how many took it from the store, an older
    reading or waited, the share from the store, and the median seconds the tools took in those answers."""
    rows = {}
    for x in items:
        if x["t"] > now - days * DAY and x.get("s"):
            for part in x["s"].split("+"):
                d, _, kind = part.partition(":")
                r = rows.setdefault(d, {"warm": 0, "alt": 0, "kalt": 0, "w": []})
                r[kind] = r.get(kind, 0) + 1
                if "w" in x:
                    r["w"].append(x["w"])
    out = []
    for d, r in rows.items():
        n = r["warm"] + r["alt"] + r["kalt"]
        out.append({"service": d, "n": n, "warm": r["warm"], "alt": r["alt"], "kalt": r["kalt"],
                    "share": round(100 * (r["warm"] + r["alt"]) / n) if n else 0, "wait": _med(r["w"])})
    return sorted(out, key=lambda r: -r["n"])


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
        _save((items + [{"t": round(now), "a": round(seconds, 2), "c": "web", "k": "ack"}])[-MAX_ENTRIES:])


def _stats(values):
    if not values:
        return None
    values = sorted(values)
    return {"n": len(values), "median": round(statistics.median(values), 2),
            "p90": round(values[min(len(values) - 1, int(len(values) * 0.9))], 2)}


def summary(now=None):
    """The last 24 hours (with answers per hour), the six days before, and a warning sentence when answers got
    slower. Without a fixed time the result is kept SUMMARY_S seconds while no answer came (status, case, Live)."""
    if now is None:
        t, stamp, res = _mem["summary"]
        if res is not None and stamp == _stamp() and 0 <= time.time() - t < SUMMARY_S:
            return res
        t = time.time()
        res = _summary(t)
        _mem["summary"] = (t, _stamp(), res)
        return res
    return _summary(now)


def _summary(now):
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
           "groups": by_group(items, now), "versions": by_version(items), "services": by_service(items, now)}
    d, w = res["day"], res["week"]
    # clearly slower: at least 10 answers today, median more than 1.5 times and 1.5 s above the week's
    if d and w and d["n"] >= 10 and w["n"] >= 10 and d["median"] > 1.5 * w["median"] and d["median"] > w["median"] + 1.5:
        res["warn"] = (f"Antworten sind langsamer geworden: bis zum ersten Ton im Mittel {d['median']:g} s "
                       f"(sonst {w['median']:g} s). Läuft qwen38 gerade viel oder ist der Speicher knapp?")
    return res
