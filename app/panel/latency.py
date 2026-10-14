"""How long people wait: the time from the question to the first sound of the answer, for every
answer of the assistant (chat.py), kept for two weeks in STATE/latency.json.

Zustand → Prüfen shows the median of the last 24 hours and of the six days before, and the page warns
(health.alerts) when answers became clearly slower, e.g. while qwen38 is busy or memory runs short.
Nothing personal is kept: only the time, the seconds and the kind of client (web, speaker, watch ...).
"""
import json
import os
import re
import statistics
import threading
import time

from common import write_json

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
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


def add(seconds, client="web", now=None):
    """Notes one answer: seconds until its first sound (called off the event loop)."""
    now = time.time() if now is None else now
    if not isinstance(seconds, (int, float)) or not 0 <= seconds < 3600:
        return
    client = client if isinstance(client, str) and re.fullmatch(r"[a-z]{1,12}", client) else "other"
    with _lock:
        items = [x for x in _load() if x["t"] > now - KEEP_DAYS * DAY]
        items = (items + [{"t": round(now), "a": round(seconds, 2), "c": client}])[-MAX_ENTRIES:]
        write_json(_file(), items, mode=0o600)


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
    """The last 24 hours, the six days before, and a warning sentence when answers got slower."""
    now = time.time() if now is None else now
    loaded = _load()
    items = [x for x in loaded if x.get("k") != "ack"]   # the answer's first sound only
    day = [x["a"] for x in items if x["t"] > now - DAY]
    week = [x["a"] for x in items if now - 7 * DAY < x["t"] <= now - DAY]
    acks = [x["a"] for x in loaded if x.get("k") == "ack" and x["t"] > now - DAY]
    res = {"day": _stats(day), "week": _stats(week), "ack": _stats(acks), "warn": None}
    d, w = res["day"], res["week"]
    # clearly slower: at least 10 answers today, median more than 1.5 times and 1.5 s above the week's
    if d and w and d["n"] >= 10 and w["n"] >= 10 and d["median"] > 1.5 * w["median"] and d["median"] > w["median"] + 1.5:
        res["warn"] = (f"Antworten sind langsamer geworden: bis zum ersten Ton im Mittel {d['median']:g} s "
                       f"(sonst {w['median']:g} s). Läuft qwen38 gerade viel oder ist der Speicher knapp?")
    return res
