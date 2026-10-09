"""The assistant does not answer its own voice (admin chat.no_self_echo, per profile "echo"; off by default).

Every device only cancels its own echo. When the speaker in the living room answers and the iPhone
next to it listens, the iPhone hears the Spark's voice as a new question. The Spark spoke that
sentence itself a moment ago, so a fixed rule here drops it, for every device alike:

1. Own words: a recording whose words are mostly a piece the Spark spoke in the last 60 s (on any
   device of the household) is dropped.
2. Speaking pause (chat.self_echo_mode "pause"): a recording made almost entirely while another
   device of the same profile was playing an answer is dropped too (catches echoes the speech
   recognition garbled). The device that speaks is never held back, so "Stopp" there still works.

A sentence that starts with the wake word ("Spark, ...", "Jarvis ...") always counts. Only for
signed-in profiles (their login or device key), never for guests: a guest could otherwise test
what the Spark said to someone else. What the Spark said stays in RAM only, at most 20 pieces for
60 s; nothing goes to disk, the log names only the reason, never the text."""
import hashlib
import re
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import load_config  # noqa: E402
import profiles  # noqa: E402

KEEP = 60          # seconds a spoken piece is remembered after it ended
MAX_PIECES = 20    # pieces remembered at most (the whole household)
MAX_WORDS = 400    # words kept per piece
MIN_WORDS = 3      # shorter recordings ("Ja", "Stopp") are never taken for an echo
SHARE = 0.6        # share of the recording's word pairs that must come from a spoken piece
TAIL = 1.0         # seconds after the end of playback that still count as "speaking"
PAUSE_SHARE = 0.7  # share of the recording that must fall into another device's playback
MODES = ("text", "pause")
WAKE = re.compile(r"\s*(?:hey\s+|hallo\s+|hi\s+|ok\s+|okay\s+)?(?:spark|jarvis|computer)\b", re.I)

_pieces = []
_lock = threading.Lock()


def mode():
    """"text" or "pause" while the admin switched it on, else None."""
    ch = load_config().get("chat", {})
    if ch.get("no_self_echo") is not True:
        return None
    return ch.get("self_echo_mode") if ch.get("self_echo_mode") in MODES else "pause"


def active(uid):
    """The mode for this profile (its own switch "echo", on unless it switched it off), None for guests."""
    m = mode()
    if not m or not uid:
        return None
    return m if profiles.settings(uid).get("echo", True) is not False else None


def device_of(request):
    """Which device a request comes from: its device key, else its browser (a hash of the login
    cookie, never the cookie itself), else its address."""
    d = profiles.device(request)
    if d:
        return "dev:" + d["id"]
    raw = request.cookies.get(profiles.COOKIE, "") or request.cookies.get("speech_spark_admin", "")
    if raw:
        return "web:" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return "ip:" + (request.client.host if getattr(request, "client", None) else "")


def words(text):
    return re.findall(r"\w+", str(text or "").lower())[:MAX_WORDS]


def said(text, uid, device, start=None, now=None):
    """Remembers a piece the Spark is about to play on a device; returns it so played() can move its
    end while the sound comes. None while the admin switch is off (then nothing is kept)."""
    if not mode():
        return None
    w = words(text)
    if len(w) < 2:
        return None
    now = time.time() if now is None else now
    start = now if start is None else start
    p = {"t0": start, "t1": start, "pairs": set(zip(w, w[1:])), "uid": uid or None, "dev": str(device or "")}
    with _lock:
        _forget(now)
        _pieces.append(p)
        del _pieces[:-MAX_PIECES]
    return p


def played(piece, until):
    """The piece plays until this time (moves only forward)."""
    if piece is not None and until > piece["t1"]:
        piece["t1"] = until


def _forget(now):
    _pieces[:] = [p for p in _pieces if now - p["t1"] <= KEEP]


def check(uid, device, text, duration=None, now=None):
    """Why this recording of a profile's device is the Spark's own voice ("own voice", "speaking
    pause"), or None when it counts as a question."""
    m = active(uid)
    if not m or not str(text or "").strip() or WAKE.match(str(text)):
        return None
    now = time.time() if now is None else now
    with _lock:
        _forget(now)
        pieces = list(_pieces)
    w = words(text)
    if len(w) >= MIN_WORDS:
        pairs = list(zip(w, w[1:]))
        known = set().union(*(p["pairs"] for p in pieces)) if pieces else set()
        hits = sum(1 for x in pairs if x in known)
        if hits >= 2 and hits >= SHARE * len(pairs):
            return "own voice"
    if m == "pause" and isinstance(duration, (int, float)) and not isinstance(duration, bool) and 0 < duration <= 600:
        a = now - duration
        for p in pieces:
            if p["uid"] != uid or p["dev"] == str(device or ""):
                continue
            overlap = min(now, p["t1"] + TAIL) - max(a, p["t0"])
            if overlap >= PAUSE_SHARE * duration:
                return "speaking pause"
    return None


def note(reason, client):
    """The journal line for a dropped recording: the reason and the kind of device, never the text."""
    print(f"chat: ignored ({reason}) from {re.sub(r'[^a-z0-9]', '', str(client))[:12] or 'device'}", flush=True)


def clear():
    with _lock:
        _pieces.clear()
