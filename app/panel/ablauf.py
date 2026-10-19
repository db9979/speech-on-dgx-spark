"""Ablauf und Freigabe zeigen (plan plaene/redde-ideen/plan.md, package A, Dominik 2026-10-17 „2a“).

Under an answer the assistant shows which tools it used, each with ok or not and its time (folded:
„3 Werkzeuge benutzt · 2,1 s“), and a proposal this answer left waiting for a plain "Ja" as a card with
Ja and Nein. A tap sends "Ja" or "Nein" like a typed answer from the same device and conversation, so the
module that made the proposal decides with its own fixed rules (calendars.confirms ...); the card itself
carries nothing out and never says more than the kind of the proposal.

Only fixed words: the readable tool name (werkzeuge.NAMES), never its arguments or its result; the kind of a
proposal from KINDS, never its text. Admin switch chat.show_steps (off); never for guests or another voice
(chat_turn steps_on). The same events reach the iPhone app (Assistant.swift); Android shows the panel.

Rückfrage-Karten (asks, Dominik 2026-10-18): when no proposal waits and the answer ends with a question to the person,
its answers as buttons: Ja/Nein (fixed words), or the short parts of „A oder B?“ from the answer's own last sentence
(never after mail or outside text). Telegram shows them as a reply keyboard, the Pebble as follow-ups to tap; the
speaker stays speech. A short yes or no right after it takes up the person's question before (chat_turn, was_asked).
"""
import re

import profiles
import taten
import werkzeuge

# module of a waiting proposal (chat_turn.waiting_mods) -> what it is about, in fixed words
KINDS = {
    "calendars": ("Termin", "Appointment"),
    "tidy": ("Postfach", "Mailbox"),
    "tasks": ("Liste", "List"),
    "fixes": ("Gedächtnis", "Memory"),
    "agent": ("Auftrag", "Job"),
    "messages": ("Nachricht", "Message"),
    "roomfar": ("Durchsage", "Announcement"),
    "meinmcp": ("Eigener Dienst", "Own service"),
    "hamelden": ("Smart-Home-Meldung", "Smart home alert"),
    "aendern": ("Rückgängig", "Undo"),
    "nasablage": ("NAS-Ablage", "NAS filing"),
    "rufen": ("Anruf", "Call"),
    "senden": ("Mail", "Mail"),
    "remarkable": ("reMarkable", "reMarkable"),
}


def step(name, result, seconds):
    """The event for one tool call of this answer (only offered tools reach here): readable name, ok, ms."""
    return {"type": "step", "tool": name, "de": werkzeuge.label(name), "en": werkzeuge.label(name, True),
            "ok": not taten.failed(result) if isinstance(result, str) else True, "ms": max(0, int(seconds * 1000))}


def waiting(uid, mods, since, src):
    """The kinds of the proposals this answer left for a "Ja": made since the start of the turn, from this device
    and conversation (the yes only counts there). Returns [{"type": "confirm", "kind", "de", "en"}]."""
    out = []
    for mod in mods:
        try:
            p = mod.pending(uid)
        except Exception:
            continue
        if not isinstance(p, dict) or p.get("t", 0) < int(since) or p.get("src", src) != src:
            continue
        kind = mod.__name__.rsplit(".", 1)[-1]
        de, en = KINDS.get(kind, ("Vorschlag", "Proposal"))
        out.append({"type": "confirm", "kind": kind, "de": de, "en": en})
    if out:
        print(f"chat: freigabe-karte gezeigt | {len(out)}", flush=True)
    return out[:1]   # one yes confirms one thing (chat_turn): one card


# ---------------------------------------------------------------- Rückfrage-Karten (Dominik 2026-10-18 „1a 2a 3a 4a 5a“)
# The answer ends with a question to the person: its answers as buttons under it, built by fixed rules from the last
# sentence only (the model never makes buttons). A yes/no question gets Ja and Nein; „A oder B?“ gets its short parts
# (at most ASK_MAX, only after an answer of the panel's own, never after mail or outside text) and „Anders …“, which
# only puts the cursor in the text field. A tap sends the word like a typed answer. Plan plaene/rueckfrage-karten.md.
ASK_MAX = 3
ASK_LEN = 30
ASK_WORDS = 4
ASKED_SECONDS = 10 * 60   # a short yes or no within this time takes up the person's question before (chat_turn)
YES_NO = re.compile(r"(?i)^\W*(soll(en)? (ich|wir)|möchtest du|moechtest du|willst du|darf ich|magst du|passt (das|es|dir)|"
                    r"ist (das|es) (ok|okay|in ordnung|recht)|brauchst du|hast du|kann ich|können wir|sollte ich|"
                    r"shall (i|we)|should (i|we)|do you (want|need)|would you like|want me to|may i|can i|is (that|this) (ok|okay|fine))\b")
TAG = re.compile(r"(?i)(,\s*(oder|nicht wahr|ja|okay|ok|right|or not)|\b(oder nicht))\W*$")
OR = re.compile(r"(?i)\s+(oder|or)\s+")
VERB_END = re.compile(r"^[a-zäöüß]+(en|ern|eln)$")   # a trailing German verb („ablegen“): lowercase, nouns are capitalized
BAD = re.compile(r"(?i)https?:|www\.|[<>{}\[\]|`@#\\/]|\d{4,}")
EN = re.compile(r"(?i)^\W*(shall|should|do|would|want|may|can|is)\b")


def _last(said):
    """The last sentence of the answer when it is a question to the person, else ""."""
    t = re.sub(r"\s+", " ", str(said or "")[-600:]).strip().rstrip(" *_\"'“”»«)")
    if not t.endswith("?"):
        return ""
    return re.split(r"(?<=[.!?:\n])\s+", t)[-1].strip(" *_\"'„“”»«(")


def _parts(q):
    """„A oder B?“, „A, B oder C?“: the short parts, built from the question's own words, or []."""
    body = q.rstrip("?").strip()
    if TAG.search(body) or len(OR.findall(body)) != 1:
        return []
    left, right = OR.split(body, maxsplit=1)[0], OR.split(body, maxsplit=1)[2]
    rw = right.split()
    while len(rw) > 1 and VERB_END.match(rw[-1]):
        rw.pop()
    n = len(rw)
    if not n or n > ASK_WORDS:
        return []
    pieces = [x.strip() for x in left.split(",")]
    lw = pieces[0].split()
    if len(lw) < n or any(not 0 < len(p.split()) <= n + 1 for p in pieces[1:]):
        return []
    out = [" ".join(lw[-n:])] + pieces[1:] + [" ".join(rw)]
    if len(out) > ASK_MAX:
        return []
    clean = []
    for x in out:
        x = x.strip(" .,;:!?\"'„“”»«()")
        if not x or len(x) > ASK_LEN or len(x.split()) > ASK_WORDS or BAD.search(x):
            return []
        x = x[0].upper() + x[1:]
        if x.lower() not in (c.lower() for c in clean):
            clean.append(x)
    return clean[:ASK_MAX] if len(clean) >= 2 else []


def asks(said, outside=False):
    """The buttons for the question the answer ends with: {"type": "choice", "from": "frage", ...} or None.
    Ja/Nein are fixed words; the parts of „A oder B?“ only after an answer of the panel's own (outside False)."""
    q = _last(said)
    if not q:
        return None
    parts = _parts(q)
    if parts and outside:   # never words of outside text on a button, and „Ja“ would not answer „A oder B?“
        return None
    if parts:
        en = bool(EN.match(q))
        return {"type": "choice", "from": "frage", "options": [{"label": p, "send": p} for p in parts],
                "free": "Something else …" if en else "Anders …"}
    if YES_NO.match(q) or TAG.search(q.rstrip("?").strip()):
        yes, no = ("Yes", "No") if EN.match(q) else ("Ja", "Nein")
        return {"type": "choice", "from": "frage", "options": [{"label": yes, "send": yes}, {"label": no, "send": no}]}
    return None


NO_REPLY = re.compile(r"(?i)\W*(nein|nö|nee|no|nope)(\W+\w+){0,2}\W*")


def short_reply(text):
    """A plain yes or no („Ja“, „Okay“, „Nein danke“): an answer to a question before, never a request of its own."""
    import calendars
    text = str(text or "")[:200]
    return bool(NO_REPLY.fullmatch(text)) or calendars.confirms(text)


def remember_asked(uid, src, ev):
    """The answer asked the person something (ev from asks): its buttons, for this conversation."""
    profiles.pending_set(uid, "rueckfrage", {"options": [o["send"] for o in ev["options"]]}, src)


def was_asked(uid, src, text):
    """The person's message answers the question of the answer before: a plain yes or no, or one of its buttons, in
    the same conversation within ASKED_SECONDS. The mark is used once."""
    p = profiles.pending_get(uid, "rueckfrage", ASKED_SECONDS)
    if not p:
        return False
    profiles.pending_drop(uid, "rueckfrage")
    words = str(text or "").strip().rstrip(".!").lower()
    return p.get("src", src) == src and (short_reply(text) or words in (str(o).lower() for o in p.get("options") or []))
