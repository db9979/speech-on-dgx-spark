"""Mitteilung antippen öffnet genau diese Meldung (Dominik 2026-10-23 „nach Empfehlung umsetzen“).

Every note push.send hands to a device (the iPhone app, the Android app, the Spark-Begleiter, a browser) is kept here
for a while with a random number: title, text, its kind (tag), the Vorgang it is about (vg) and, for a new mail, the
mail's reference (ref). Over Apple, the push services and the polls goes only that number (the iPhone app's
notification extension fetches the text with it, GET /api/iphone/note). A tapped notification opens the app or the
panel on the conversation and shows the note there as a card, with the full text and the button that fits it.

What the card offers is decided here with fixed rules from the kind of note (ziel), never by a model:

    1. a note about a Vorgang (vg): that Vorgang's card with its own buttons (vorgaenge.py)
    2. a message in a chat (tag chat-<cid>): open that chat
    3. a new mail with its reference: read that mail
    4. a Bestätigungscode (mailcode): copy the code, the note's first word
    4a. „Du bist dran“ of the Dungeon-Master (tag dungeon) with its round's id: open that table (the app asks for the
        seat's code only then, the note never carries it)
    5. a way in the text or a fixed way of the kind (begleiter.note_weg): open that place (Sprung-Link)
    6. else: title and text only

Kept in memory only (KEEP seconds, at most MAX per profile, a restart forgets them), never written to state/. Only the
profile the note was for gets it back; another profile's number answers 404 like an old one.
"""
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import profiles
from core import assistant, own_profile

router = APIRouter()

KEEP = 24 * 3600               # a note can be opened again for a day
MAX = 30                       # notes kept per profile
ID = re.compile(r"[0-9a-f]{16}")
VG = re.compile(r"v[0-9a-f]{10}")
CHAT = re.compile(r"chat-(c[0-9a-f]{12})")
MAIL = re.compile(r"m[0-9a-f]{8}:\d{1,10}")
CODE = re.compile(r"[A-Z0-9]{4,8}")
RUNDE = re.compile(r"r[0-9a-f]{10}")          # a Dungeon-Master round (dungeon_ablage.RID)
# what a card offers, fixed words; the Live line and the journal name only these
ARTEN = {"vorgang": "Offen", "chat": "Chat", "mail": "Mail", "code": "Code", "weg": "Weg", "text": "Text"}
_lock = threading.Lock()
_box = {}                      # uid -> [{"id", "t", "title", "body", "tag", "vg", "ref"}]


def keep(uid, title, body, tag="", vg="", ref="", now=None):
    """Keeps a note for the profile; returns its number (16 hex), the only thing that leaves the Spark with it."""
    now = time.time() if now is None else now
    item = {"id": secrets.token_hex(8), "t": now, "title": str(title)[:200], "body": str(body)[:1500],
            "tag": str(tag or "")[:40], "vg": str(vg or "")[:12], "ref": str(ref or "")[:40]}
    with _lock:
        box = [x for x in _box.get(uid, []) if now - x["t"] < KEEP]
        box.append(item)
        _box[uid] = box[-MAX:]
    return item["id"]


def get(uid, mid, now=None):
    """The profile's own note by its number, or None (unknown, another profile's, or older than KEEP)."""
    now = time.time() if now is None else now
    if not isinstance(mid, str) or not ID.fullmatch(mid):
        return None
    with _lock:
        return next((dict(x) for x in _box.get(uid, []) if x["id"] == mid and now - x["t"] < KEEP), None)


def ziel(x):
    """What the card of a note offers (see the module's rules): {"art", and "vg" | "chat" | "ref" | "code" | "rid"}, plus "weg"
    when the note names a place. Only fixed patterns pass, never a free text."""
    import begleiter
    tag, out = x.get("tag", ""), {}
    weg = begleiter.note_weg(x)
    chat = CHAT.fullmatch(tag)
    code = (x.get("body", "").split(" ", 1) or [""])[0]
    if VG.fullmatch(x.get("vg", "")):
        out = {"art": "vorgang", "vg": x["vg"]}
    elif chat:
        out = {"art": "chat", "chat": chat.group(1)}
    elif tag == "mail-new" and MAIL.fullmatch(x.get("ref", "")):
        out = {"art": "mail", "ref": x["ref"]}
    elif tag == "mailcode" and CODE.fullmatch(code):
        out = {"art": "code", "code": code}
    elif tag == "dungeon" and RUNDE.fullmatch(x.get("ref", "")):
        out = {"art": "dungeon", "rid": x["ref"]}
    elif weg:
        out = {"art": "weg"}
    else:
        out = {"art": "text"}
    if weg:
        out["weg"] = weg
    return out


def view(x):
    """What a device gets for a tapped note: title, text, time (seconds) and the card's target."""
    return {"title": x["title"], "body": x["body"], "t": int(x["t"]), "ziel": ziel(x)}


def opened(uid, mid, way, now=None):
    """A device opened a tapped note: its view, or 404. One line for Live and the journal (the kind of card and the
    way only, never the text)."""
    import live
    x = get(uid, mid, now)
    who = profiles.log_name(profiles.by_id(uid))
    if x is None:
        live.mark("Mitteilung", f"nicht mehr da {way}")
        print(f"push: mitteilung nicht mehr da {way} | {who}", flush=True)
        raise HTTPException(404, "gone")
    out = view(x)
    live.mark("Mitteilung", f"geöffnet {ARTEN[out['ziel']['art']]} {way}")
    print(f"push: mitteilung geoeffnet {out['ziel']['art']} {way} | {who}", flush=True)
    return out


@router.get("/api/profile/mitteilung", dependencies=[Depends(assistant)])
def api_get(request: Request, id: str = "", prof=Depends(own_profile)):
    """A page or the Android app opens a tapped note (#meldung=<number>): only the own profile's notes."""
    guard.limit(request, "mitteilung", prof["id"])
    import android
    return opened(prof["id"], id, "and" if android.from_app(request) else "web")
