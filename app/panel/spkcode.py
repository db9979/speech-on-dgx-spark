"""Code word at an own speaker in a room (plan plaene/lautsprecher-codewort.md, V01.0.297).

A speaker in a room is shared (chat_turn.shared_stranger): personal things only for the owner's voice,
clearly recognized in that very recording (speakers.verify). With this function a voice that is close
but not sure (the grey zone), or a sure one in a moment that is not plausible, may still get them after
saying the profile's own speaker code word:

    sure       score >= strictness, clearly ahead of every other profile, nothing implausible: as before
    grey       score at most GREY below the strictness and the owner still the best match, or a sure
               score in an implausible moment: "Sag bitte dein Codewort."
    foreign    anything else: guest rights, never asked for the code word (one overheard in the room is
               of no use to another voice)

Not plausible (fixed rules): another profile within the margin, less than SHORT seconds of speech, an
unknown voice heard by room mode at this speaker in the last FOREIGN_RECENT seconds, a wrong code word
there in the last FAIL_WINDOW seconds.

The code word is the profile's own (not the smart home one), at least 2 words and 8 letters, sealed in
the vault, never sent back; it is compared like the smart home code word (homeassistant._spans: a letter
or two misheard is fine). The sentence that carries it reaches no model, history, protocol, diagnosis or
journal. Three wrong ones in FAIL_WINDOW: this speaker stops asking that profile for LOCK seconds and the
profile gets a notification. Waiting questions, open windows, failures and locks live in memory only.

Off until the admin (chat.speaker_code) and the profile (spk_code) switch it on (features.py "spkcode").
"""
import json
import re
import threading
import time

import features
import homeassistant
import profiles
import vault

GREY = 0.10             # how far below the strictness the grey zone reaches
SHORT = 1.5             # seconds of speech below which even a sure match asks
WAIT = 60               # the question waits this long for the code word, at the same speaker
OPEN = 120              # after a right code word, follow-ups at that speaker stay open this long
FAIL_WINDOW = 15 * 60
FAILS = 3
LOCK = 30 * 60
FOREIGN_RECENT = 120

_lock = threading.Lock()
_pending = {}           # device id -> {"uid", "text", "t", "why"}
_open = {}              # device id -> (uid, until)
_fails = {}             # (uid, device id) -> [times]
_locked = {}            # (uid, device id) -> until

# what counts as asking for personal things (intent.py groups), plus "mein/meine ..."
PERSONAL = {"smarthome", "kalender", "mail", "erinnerung", "liste", "paket", "kontakt", "gedaechtnis", "dokument",
            "nachricht", "agent", "iphone"}
_MINE = re.compile(r"(?i)\b(mein|meine|meinen|meinem|meiner|meines|mir|mich)\b")


def _file(uid):
    return profiles._path(uid, "speaker-code.json")


def _read(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _code(uid):
    try:
        c = json.loads(vault.open_(_read(uid).get("code") or "") or "null")
        return c if isinstance(c, dict) and c.get("code") else None
    except ValueError:
        return {"code": "\0unreadable", "words": 1}   # sealed with another key: never matches


def has_code(uid):
    c = _code(uid)
    return bool(c and c["code"] != "\0unreadable")


def public(uid):
    return {"has_code": has_code(uid), "unreadable": bool(_code(uid)) and not has_code(uid)}


def set_code(uid, code):
    """Sets the code word (empty removes it); raises ValueError when it is too weak."""
    words = homeassistant._words(code)
    joined = "".join(words)
    if joined and (len(words) < 2 or len(joined) < 8 or len(words) > 6):
        raise ValueError("Das Codewort braucht mindestens 2 Wörter und 8 Buchstaben, höchstens 6 Wörter.")
    with _lock:
        d = _read(uid)
        d.pop("code", None)
        if joined:
            d["code"] = vault.seal(json.dumps({"v": 1, "code": joined, "words": len(words)}))
            d["updated"] = int(time.time())
        profiles._write(_file(uid), d)
        for did in [k for k, v in _pending.items() if v["uid"] == uid]:
            _pending.pop(did, None)
        for did in [k for k, v in _open.items() if v[0] == uid]:
            _open.pop(did, None)
    return public(uid)


def on(uid):
    """The function is switched on for this profile and it has set a code word."""
    return bool(uid) and features.allowed("spkcode", uid) and has_code(uid)


def personal(text):
    """Whether a question asks for personal things (fixed rules, intent.py groups)."""
    import intent
    route = intent.classify(text)
    return bool(set(route.names) & PERSONAL) or bool(_MINE.search(str(text or "")))


def level(v, uid, did, foreign_at=0.0, now=None):
    """("sure" | "grey" | "foreign", why) for one speakers.verify() result at the speaker did."""
    now = time.time() if now is None else now
    if not v or not v.get("score"):
        return "foreign", v.get("why", "") if v else "no voice check"
    score, other, need = v["score"], v["other"], v["need"]
    ahead = score > other
    odd = []
    if score >= need and score - other < 0.05:
        odd.append("another profile close behind")
    if v.get("seconds", 0) < SHORT:
        odd.append("short question")
    if foreign_at and now - foreign_at < FOREIGN_RECENT:
        odd.append("unknown voice in the room just now")
    if recent_fail(uid, did, now):
        odd.append("wrong code word lately")
    if v.get("ok") and not odd:
        return "sure", ""
    if ahead and score >= need - GREY:
        return "grey", ", ".join(odd) or "voice not sure"
    return "foreign", v.get("why") or "voice not recognized"


def recent_fail(uid, did, now=None):
    now = time.time() if now is None else now
    return any(now - t < FAIL_WINDOW for t in _fails.get((uid, did), []))


def locked(uid, did, now=None):
    now = time.time() if now is None else now
    return _locked.get((uid, did), 0) > now


def is_open(uid, did, now=None):
    now = time.time() if now is None else now
    o = _open.get(did)
    return bool(o and o[0] == uid and o[1] > now)


def ask(uid, did, text, why, now=None):
    """The question waits for the code word at this speaker."""
    now = time.time() if now is None else now
    if len(_pending) > 100:
        _pending.clear()
    _pending[did] = {"uid": uid, "text": str(text)[:2000], "t": now, "why": why}


def waiting(did, now=None):
    now = time.time() if now is None else now
    p = _pending.get(did)
    return p if p and now - p["t"] < WAIT else None


def attempt(uid, did, text, now=None):
    """The answer to "Sag bitte dein Codewort": ("right", question) / ("wrong", None) / ("locked", None).
    The waiting question is taken off either way."""
    now = time.time() if now is None else now
    p = _pending.pop(did, None)
    if not p or p["uid"] != uid or now - p["t"] >= WAIT:
        return "none", None
    if locked(uid, did, now):
        return "locked", None
    c = _code(uid)
    if c and c["code"] != "\0unreadable" and homeassistant._spans(c, text):
        _fails.pop((uid, did), None)
        _open[did] = (uid, now + OPEN)
        return "right", p["text"]
    fails = [t for t in _fails.get((uid, did), []) if now - t < FAIL_WINDOW] + [now]
    _fails[(uid, did)] = fails[-10:]
    if len(_fails) > 1000:
        _fails.clear()
    if len(fails) >= FAILS:
        _locked[(uid, did)] = now + LOCK
        return "locked", None
    return "wrong", None


def fail_count(uid, did, now=None):
    now = time.time() if now is None else now
    return sum(1 for t in _fails.get((uid, did), []) if now - t < FAIL_WINDOW)


def forget(did):
    """The speaker went away or the code word changed: nothing waits, nothing stays open."""
    _pending.pop(did, None)
    _open.pop(did, None)
