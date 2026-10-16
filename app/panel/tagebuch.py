"""Spark-Tagebuch: what the Spark itself did for a profile (plan plaene/vorschlaege-besser.md, Version 3; Dominik
2026-10-12, trace e62151: „Wurde ein neues Dokument erstellt?“ was answered „Nein“ although one was made).

Every module that does something for a person notes it here with fixed words: note(uid, art, title, ref, before,
src). The assistant answers „Was hast du heute für mich gemacht?“ from this list (tool spark_tagebuch), never from
its own memory. Kept per profile in users/<id>/tagebuch.json, 7 days, at most 200 entries; it stays on the Spark
(speicher.LOCAL). A title that came from outside (a web page, a mail: src "web"/"mail") is stored but never repeated
to the model, only its kind. `before` is a small state a module may need for undoing (the Fernseher thread's
devices), at most 300 characters as JSON. Off by default: admin switch chat.tagebuch and the profile's tagebuch_on;
nothing is noted while it is off, guests never. The journal gets kind and count only.
"""
import json
import re
import threading
import time

import features
import profiles

ARTEN = {   # key -> (German, English)
    "geraet": ("Gerät geschaltet", "Device switched"),
    "erinnerung": ("Erinnerung gestellt", "Reminder set"),
    "mail_entwurf": ("Mail-Entwurf abgelegt", "Mail draft saved"),
    "dokument": ("Dokument erstellt", "Document made"),
    "remarkable": ("Aufs reMarkable gelegt", "Put on the reMarkable"),
    "nachricht": ("Nachricht geschickt", "Message sent"),
    "ablegen": ("Auf der NAS abgelegt", "Filed on the NAS"),
    "bild": ("Bild gemalt", "Picture painted"),
    "musik": ("Lied gemacht", "Song made"),
    # kinds of the action check (taten.KIND); no diary hook yet, so the tool may answer "nothing noted" for them
    "termin": ("Termin eingetragen", "Appointment added"),
    "merken": ("Gemerkt oder vergessen", "Remembered or forgotten"),
    "aufgabe": ("Aufgabe eingetragen", "Task added"),
    "aenderung": ("Geändert oder rückgängig gemacht", "Changed or undone"),
}
KEEP_S = 7 * 86400
MAX = 200
MAX_TITLE = 80
MAX_BEFORE = 300
OUTSIDE = ("web", "mail")
_lock = threading.Lock()


def _file(uid):
    return profiles._path(uid, "tagebuch.json")


def _load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return [x for x in d.get("items", []) if isinstance(x, dict)] if isinstance(d, dict) else []
    except (OSError, ValueError):
        return []


def _clean(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()[:n]
    return s if s.isprintable() else ""


def note(uid, art, title, ref="", before=None, src="", now=None):
    """Notes one thing the Spark did. Never raises (a module's action must not fail over its diary entry)."""
    try:
        if art not in ARTEN or not features.allowed("tagebuch", uid):
            return False
        now = time.time() if now is None else now
        b = None
        if before is not None:
            raw = json.dumps(before, ensure_ascii=False)
            b = before if len(raw) <= MAX_BEFORE else None
        row = {"t": round(now, 1), "art": art, "title": _clean(title, MAX_TITLE), "ref": _clean(ref, 80),
               "src": src if src in OUTSIDE else ""}
        if b is not None:
            row["before"] = b
        with _lock:
            items = [x for x in _load(uid) if now - float(x.get("t", 0)) < KEEP_S] + [row]
            profiles._write(_file(uid), {"items": items[-MAX:]})
        print(f"tagebuch: {art} notiert", flush=True)
        return True
    except Exception as e:
        print("tagebuch: nicht notiert", type(e).__name__, flush=True)
        return False


def recent(uid, art=None, since=None, n=20, now=None):
    """The newest entries first (at most n), only of the last 7 days."""
    now = time.time() if now is None else now
    since = now - KEEP_S if since is None else max(float(since), now - KEEP_S)
    rows = [x for x in _load(uid) if float(x.get("t", 0)) >= since and (art is None or x.get("art") == art)]
    return list(reversed(rows))[:max(1, min(int(n), MAX))]


def counts(uid, now=None):
    """{art: number} of today (Ich → Mein Spark-Tagebuch and Live: numbers only)."""
    now = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    out = {}
    for x in _load(uid):
        if time.strftime("%Y-%m-%d", time.localtime(float(x.get("t", 0)))) == day:
            out[x["art"]] = out.get(x["art"], 0) + 1
    return out


def text(uid, art=None, days=1, now=None, english=False):
    """The list for the model: time, kind and title (outside titles only as their kind)."""
    now = time.time() if now is None else now
    days = max(1, min(int(days or 1), 7))
    rows = recent(uid, art, now - days * 86400, 40, now)
    if not rows:
        return ("Nothing noted in the Spark's diary for this time." if english else
                "Im Spark-Tagebuch steht für diese Zeit nichts. Sag das so; rate nichts dazu.")
    i = 1 if english else 0
    out = []
    for x in rows:
        title = x.get("title") if not x.get("src") else ""
        out.append(time.strftime("%d.%m. %H:%M", time.localtime(float(x["t"])))
                   + f" · {ARTEN.get(x['art'], (x['art'], x['art']))[i]}" + (f" · „{title}“" if title else ""))
    return "\n".join(out)


# ---------------------------------------------------------------- the tool (extras.SERVICES)
TOOL = {"type": "function", "function": {
    "name": "spark_tagebuch",
    "description": "What the Spark itself did for the user in the last days (devices switched, reminders, mail drafts, "
                   "documents, reMarkable, messages), newest first. Answer only from this list.",
    "parameters": {"type": "object", "properties": {
        "art": {"type": "string", "enum": [""] + list(ARTEN)},
        "tage": {"type": "integer", "description": "days back, 1-7 (default 1)"}}}}}
HINT = ("Fragt der Nutzer, was der Spark für ihn gemacht, geschaltet, geschickt oder erstellt hat, schau mit "
        "spark_tagebuch nach und antworte nur aus dessen Ergebnis.")


# the diary holds only the Spark's own doing; titles from outside (src web/mail) come back only as their kind
# (text()), so no text other people wrote (see chat.INSIDE)
INSIDE = {"spark_tagebuch"}


def offer(ctx):
    who = ctx.get("who")
    # like the other personal tools: only the profile's own login or device key (not a voice recognized at someone
    # else's browser, it could be a recording) and not over Telegram without tg_private
    if not who or not features.allowed("tagebuch", who["id"]) or ctx.get("client") == "mcp" or not ctx.get("own") \
            or ctx.get("private") is False:
        return None
    import chat
    words = str(ctx.get("text") or "")
    if not (chat.DIARY_WORDS.search(words) or chat.DONE_WORDS.search(words)):
        return None
    return {"tools": [TOOL], "hint": HINT, "filler": {"spark_tagebuch": ("Ich schaue nach.", "Let me check.")}}


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    if name != "spark_tagebuch" or not features.allowed("tagebuch", who.get("id")):
        return "Das Spark-Tagebuch ist für dieses Profil aus."
    args = args if isinstance(args, dict) else {}
    art = args.get("art") if args.get("art") in ARTEN else None
    days = args.get("tage") if isinstance(args.get("tage"), int) and not isinstance(args.get("tage"), bool) else 1
    return text(who["id"], art, days)

