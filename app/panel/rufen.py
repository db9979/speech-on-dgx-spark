"""Anrufe per Assistent (Dominik 2026-10-18 „ja umsetzen“ für 1, 2a und 3a, dazu „Android-Telefone nicht vergessen“; Bild
/mnt/project-files/anruf-per-assistent/vorschlag.png): „Ruf Sabine an“, „Videoanruf mit Sabine“, „Ruf Mama übers Telefon an“.

The panel reads the request from the person's own latest message by fixed rules (parse); the model never picks whom
or when, and there is no tool for it. Nothing happens before the person's plain "Ja" on the same device and in the
same conversation (like a message, messages.py):

    Spark-Anruf     the name fits a profile of this Spark (name or Rufname, messages.find_all) the person may call
                    (anrufe.why_not: Chats and Anrufe on for both, the other takes messages from the caller). After
                    the yes the chat of the two is opened (chats.open_one) and
                      - a device with a screen that asked (the panel page, the Android app's page, the iPhone app)
                        gets the event "anruf" and starts the ordinary call itself (anrufe.js, Calls.swift);
                      - the Android app's assistant sheet (client "android") opens the app, which shows the call bar;
                      - a device without a screen (speaker, phone, Telegram, watch, Siri, CarPlay, Begleiter) leaves
                        the call waiting READY_SECONDS: a note goes to every device of the profile ("📞 Sabine
                        anrufen"); the app or page that opens next shows a bar with "Anrufen" (one tap starts it).
    Telefon         the name fits no profile, or the person says "übers Telefon": on the iPhone the app's own
                    iphone_action does it with the iPhone's contacts (unchanged); on Android the panel looks the name
                    up in the profile's own address book (contacts.search, only exactly one contact with a number)
                    and after the yes the event "waehlen" opens the phone app with the number: the person still
                    taps the green button there. Never on another device.

Admin switch chat.calls_assistant (off), parent Anrufe; only the admin blocks a profile. Never for guests, a voice
recognized at someone else's device or Telegram without personal data. The Notaus stops it like any action.

    USERS_DIR/<uid>/rufen-pending.json   the proposal waiting for "Ja" (PENDING_SECONDS)
    in memory                            the call waiting for a tap on a device (READY_SECONDS), never on disk

Logs: area "chats" ("call assistant …"), fixed words and numbers only, never a name or a number.
"""
import re
import time

import features
import profiles
from common import DayCounter

PENDING_SECONDS = 5 * 60   # the proposal waits this long for the "Ja"
READY_SECONDS = 3 * 60     # a call sent to the person's devices waits this long for the tap
PUSH_PER_HOUR = 6          # notes "📞 … anrufen" one profile gets in an hour
NAME = "rufen"
NUMBER = re.compile(r"\+?[0-9][0-9 /()\-]{2,28}")
_ready = {}                # uid -> {"id": chat, "name", "video", "t"}
_pushed = {}               # uid -> [t] (PUSH_PER_HOUR)
_count = DayCounter(asked=0, started=0, sent=0, phone=0, refused=0)


# ---------------------------------------------------------------- switches
def admin_on():
    return features.admin_on("anrufassistent")


def usable(uid):
    import anrufe
    return bool(anrufe.usable(uid) and features.allowed("anrufassistent", uid))


def _log(what, **nums):
    import chats
    chats._log("call assistant " + what, **nums)


def for_live():
    """Zustand → Live, tile Chats: numbers of today only (never a name, a chat or a number)."""
    if not admin_on():
        return {"on": False}
    t = _count.today()
    now = time.time()
    return {"on": True, "asked": t["asked"], "started": t["started"], "sent": t["sent"], "phone": t["phone"],
            "refused": t["refused"], "waiting": sum(1 for x in list(_ready.values()) if now - x["t"] < READY_SECONDS)}


def offer(ctx):
    """No tool for the model: the panel's fixed rule (answer) recognizes the request in the person's own words."""
    return None


# ---------------------------------------------------------------- the person's own words (fixed rules)
_POLITE = re.compile(r"(?i)^\s*(?:(?:hey|hallo|ok|okay)\s+)?(?:spark\s*[,:]?\s*)?(?:(?:bitte|mal|doch)\s+)*"
                     r"(?:(?:kannst|könntest|würdest)\s+du\s+(?:(?:bitte|mal|doch)\s+)*|(?:ich\s+)?(?:möchte|will|würde\s+gern)\s+"
                     r"(?:gern\s+|gerne\s+)?|(?:can|could|would)\s+you\s+(?:please\s+)?|please\s+)?")
VIDEO_WITH = re.compile(r"(?i)\b(?:per|mit|über|als|on|by|via)\s+(?:einem\s+|einen\s+|a\s+)?(?:video\w*|facetime|kamera|bild|camera)\b")
VIDEO = re.compile(r"(?i)\bvideo\s*(?:anruf|call|chat|telefonat)\w*\b|\bfacetime\b|" + VIDEO_WITH.pattern[4:])
QUESTION = re.compile(r"(?i)^\W*(?:wie|wann|wo|warum|weshalb|wieso|was|wer|kann\s+ich|darf\s+ich|soll\s+ich|muss\s+ich|"
                      r"how|when|where|why|what|who|can\s+i|should\s+i)\b")
PHONE = re.compile(r"(?i)\b(?:übers?|per|mit\s+dem|auf\s+(?:dem|der|sein\w*|ihr\w*|das)|by|on\s+(?:the|his|her|their))\s+"
                   r"(?:telefon|handy|mobil\w*|festnetz|phone|mobile|landline)\b|\b(?:normal|richtig)\s+anrufen\b")
_WORD = r"[\wäöüßÄÖÜ][\wäöüßÄÖÜ'.-]*"
_WHO = r"(?P<to>(?!(?:mich|mir|uns|dich|dir|ihn|sie|es|alle|allen|jemanden|niemanden|me|us|him|her|them|everybody|everyone)\b)" \
       + _WORD + r"(?:\s+" + _WORD + r"){0,2}?)"
_TAIL = r"(?:\s+(?:bitte|mal|jetzt|gleich|sofort|now|please))*\s*[.!?]*\s*$"
CALL = [re.compile(r"(?is)^ruf(?:e)?\s+(?:(?:bitte|mal|doch|jetzt)\s+)*" + _WHO + r"(?:\s+(?:bitte|mal|jetzt|gleich))*\s+an" + _TAIL),
        re.compile(r"(?is)^" + _WHO + r"\s+anrufen" + _TAIL),
        re.compile(r"(?is)^(?:(?:starte|mach\w*|beginne?)\s+)?(?:(?:einen|ein|eine)\s+)?(?:video)?(?:anruf|videochat|telefonat|facetime)"
                   r"\s+(?:mit|an|bei|zu|für)\s+" + _WHO + r"(?:\s+(?:starten|machen|beginnen))?" + _TAIL),
        re.compile(r"(?is)^telefonier\w*\s+(?:(?:bitte|mal)\s+)*mit\s+" + _WHO + _TAIL),
        re.compile(r"(?is)^(?:video\s*)?call\s+(?:with\s+)?" + _WHO + _TAIL),
        re.compile(r"(?is)^(?:start|make|place)\s+an?\s+(?:video\s*)?call\s+(?:with|to)\s+" + _WHO + _TAIL),
        re.compile(r"(?is)^(?:phone|ring)\s+" + _WHO + _TAIL)]
_LEAD = re.compile(r"(?i)^(?:den|die|der|dem|meine[nmrs]?|unsere[nmrs]?|my|our|the)\s+")


def parse(text):
    """(name as said, "video" | "audio" | "phone") from the person's own request to call someone, or None.
    "Ruf mich an" (the Spark calls the person, telefon_anruf.py) and "Ruf alle an" are no such request."""
    t = str(text or "").strip()
    if not t or len(t) > 160 or "\n" in t:
        return None
    if QUESTION.match(t):
        return None   # „Wie kann ich Sabine anrufen?“ asks how, it orders nothing
    mode = "phone" if PHONE.search(t) else "video" if VIDEO.search(t) else "audio"
    t = PHONE.sub(" ", VIDEO_WITH.sub(" ", t))
    t = re.sub(r"\s{2,}", " ", _POLITE.sub("", t, count=1)).strip()
    for rx in CALL:
        m = rx.match(t)
        if m:
            to = _LEAD.sub("", m.group("to").strip(" ,.-")).strip()
            return (to, mode) if 2 <= len(to) <= 40 else None
    return None


# ---------------------------------------------------------------- "Ja" before calling
def pending(uid):
    return profiles.pending_get(uid, NAME, PENDING_SECONDS)


def drop_pending(uid):
    """Like messages.drop_pending: a proposal made by answer() in this very turn only loses its mark."""
    p = pending(uid)
    if p and p.pop("fresh", False):
        profiles._write(profiles.pending_file(uid, NAME), p)
        return
    profiles.pending_drop(uid, NAME)


def _propose(uid, p, src):
    profiles.pending_set(uid, NAME, dict(p, fresh=True), src)
    _count.today()["asked"] += 1


def describe(p):
    if p["kind"] == "phone":
        return f"{p['name']} übers Telefon anrufen ({p['number']})"
    if p["kind"] == "choose":
        return "Anruf: " + " oder ".join(p["names"])
    return f"{p['name']} per Spark-{'Videoanruf' if p.get('video') else 'Anruf'} anrufen"


def question(p):
    if p["kind"] == "phone":
        return f"Soll ich {p['name']} übers Telefon anrufen ({p['number']})?"
    return f"Soll ich {p['name']} per Spark-{'Videoanruf' if p.get('video') else 'Anruf'} anrufen?"


# "Ja", "Ja, mit Video", "Nur Sprache", "Ohne Video": the yes, and a change between sound and picture with it
_YES_VIDEO = re.compile(r"(?i)^\W*(?:(?:ja|ok|okay|gerne?|bitte|klar|yes|sure)\W+)*(?:aber\s+|lieber\s+|doch\s+)*"
                        r"(?:(?:mit|per|als|with|on)\s+video|video|videoanruf|video call)\W*(?:bitte|please)?\W*$")
_YES_AUDIO = re.compile(r"(?i)^\W*(?:(?:ja|ok|okay|gerne?|bitte|klar|yes|sure)\W+)*(?:aber\s+|lieber\s+|doch\s+)*"
                        r"(?:nur\s+(?:sprache|ton|audio|telefon)|ohne\s+(?:video|bild|kamera)|voice\s+only|audio\s+only|"
                        r"without\s+video)\W*(?:bitte|please)?\W*$")


def _yes(text, p):
    """(yes, video): the person's plain yes, also with "mit Video" / "nur Sprache" for a Spark call."""
    import calendars
    if p["kind"] == "spark" and _YES_VIDEO.match(text or ""):
        return True, True
    if p["kind"] == "spark" and _YES_AUDIO.match(text or ""):
        return True, False
    return calendars.confirms(text), bool(p.get("video"))


def _note(call, system):
    return {"call": {"name": "Anruf per Assistent " + call[0], "args": call[1], "result": call[2]}, "system": "Anrufe: " + system,
            "proposed": NAME, "quiet": True}


def device(ctx):
    """Where the request came from: "web" (a panel page, also inside the Android app), "iphone" (the iPhone app),
    "android" (the Android app's assistant sheet) or "far" (no screen for a call: speaker, phone, Telegram, …)."""
    c = str(ctx.get("client") or "")
    if c == "android":
        return "android"
    if c in ("iphone", "app") and ctx.get("app"):
        return "iphone"
    if c in ("", "web") and not ctx.get("app"):
        return "web"
    return "far"


def _phone_here(ctx):
    """Dialling a phone number works only on Android here (the iPhone app has its own way, iphone_action)."""
    return device(ctx) == "android" or (device(ctx) == "web" and bool(ctx.get("android")))


async def answer(ctx, latest):
    """The person's yes or no to a waiting proposal, or a new request in their own words: {"call", "system", …} or None."""
    who = ctx.get("who")
    if not who or not ctx.get("own") or not ctx.get("private", True) or not admin_on() or not usable(who["id"]):
        return None
    uid, src = who["id"], ctx.get("src", "")
    got = parse(latest)
    p = pending(uid)
    if p and p.get("src", src) == src and not got:
        profiles.pending_drop(uid, NAME)   # answered: gone, whatever its mark
        if p["kind"] == "choose":
            return _answer_which(ctx, uid, p, latest, src)
        yes, video = _yes(latest, p)
        if yes:
            return await carry_out(ctx, uid, dict(p, video=video))
        _log("declined")
        return _note(("(abgelehnt)", describe(p), "nicht angerufen"),
                     f"{describe(p)} wurde NICHT gemacht, weil der Nutzer nicht zugestimmt hat. Sag das kurz.")
    if not got:
        return None
    return _direct(ctx, uid, got, src)


def _refused(why):
    _count.today()["refused"] += 1
    _log("refused", why=why)


def _direct(ctx, uid, got, src):
    import messages
    to, mode = got
    if mode != "phone":
        r, why, cands = messages.find_all(uid, to)
        if cands:
            q = {"kind": "choose", "to": [x["id"] for x in cands[:messages.MAX_CHOICE]],
                 "names": [messages.label(x) for x in cands[:messages.MAX_CHOICE]], "video": mode == "video"}
            _propose(uid, q, src)
            ask = "Meinst du " + " oder ".join(q["names"]) + "?"
            res = _note(("(Rückfrage)", ", ".join(q["names"]), "wartet auf Auswahl"),
                        f"Noch NICHT angerufen, mehrere Profile passen. Frag den Nutzer genau: „{ask}“")
            res["event"] = messages.choice_event(uid, cands[:messages.MAX_CHOICE])
            return res
        if r:
            return _spark_offer(uid, r["id"], r["name"], mode == "video", src)
        if messages._profile_named(uid, to):   # a profile of this Spark, but not reachable for the caller
            _refused("not taken")
            return _note(("(nicht möglich)", to, why), why + " Sag dem Nutzer genau das.")
    if not _phone_here(ctx):
        if mode == "phone" and device(ctx) != "iphone":
            _refused("no phone here")
            note = "Übers Telefon anrufen geht nur in der iPhone- oder Android-App."
            return _note(("(nicht möglich)", "Telefon", note), note + " Sag dem Nutzer genau das.")
        return None   # the iPhone app's own iphone_action, or no call at all: the model handles it
    return _phone_offer(uid, to, src)


def _spark_offer(uid, other, name, video, src):
    import anrufe
    why = anrufe.why_not(other, uid)
    if why:
        _refused("not taken")
        return _note(("(nicht möglich)", name, why), why + " Sag dem Nutzer genau das.")
    p = {"kind": "spark", "to": other, "name": name, "video": bool(video)}
    _propose(uid, p, src)
    _log("proposed", video=int(bool(video)))
    return _note(("(Vorschlag)", describe(p), "wartet auf Ja"),
                 f"Noch NICHT angerufen. Frag den Nutzer genau: „{question(p)}“ Erst sein Ja in der nächsten Nachricht "
                 "ruft an; mit „mit Video“ oder „nur Sprache“ wählt er Bild oder nur Ton.")


def _phone_offer(uid, to, src):
    import contacts
    if not contacts.usable(uid):
        _refused("no contacts")
        note = ("Übers Telefon rufe ich nur Kontakte aus deinem Adressbuch an. " + features.missing_text("contacts", uid)).strip()
        return _note(("(nicht möglich)", "Telefon", note), note + " Sag dem Nutzer genau das.")
    found = [x for x in contacts.search(uid, to, limit=5) if x.get("phones")]
    if len(found) != 1:
        _refused("no contact" if not found else "several contacts")
        note = (f"Ich finde in deinen Kontakten niemanden „{to}“ mit Telefonnummer." if not found else
                "Mehrere Kontakte passen: " + ", ".join(x["name"] for x in found[:3]) + ". Sag bitte den ganzen Namen.")
        return _note(("(nicht möglich)", "Telefon", note), note + " Sag dem Nutzer genau das.")
    c = found[0]
    kind, number = next((k, n) for k, n in c["phones"] if k == "Handy") if any(k == "Handy" for k, _ in c["phones"]) \
        else c["phones"][0]
    number = re.sub(r"\s{2,}", " ", str(number)).strip()
    if not NUMBER.fullmatch(number):
        _refused("bad number")
        note = "Die Nummer im Kontakt verstehe ich nicht."
        return _note(("(nicht möglich)", "Telefon", note), note + " Sag dem Nutzer genau das.")
    p = {"kind": "phone", "name": c["name"][:60], "number": number, "art": kind}
    _propose(uid, p, src)
    _log("proposed", phone=1)
    return _note(("(Vorschlag)", describe(p), "wartet auf Ja"),
                 f"Noch NICHT angerufen. Frag den Nutzer genau: „{question(p)}“ Erst sein Ja in der nächsten Nachricht "
                 "öffnet die Telefon-App mit der Nummer.")


def _answer_which(ctx, uid, p, latest, src):
    import messages
    known = {x["id"]: x for x in profiles.names()}
    cands = [known[u] for u in p.get("to", []) if u in known]
    r = messages.pick(cands, latest)
    if not r:
        _log("declined", why="no pick")
        return _note(("(keine Auswahl)", ", ".join(p.get("names", [])), "nicht angerufen"),
                     "NICHT angerufen, weil nicht klar war, wen der Nutzer meint. Sag das kurz; er kann es mit dem ganzen "
                     "Namen noch einmal sagen.")
    return _spark_offer(uid, r["id"], r["name"], p.get("video"), src)


async def carry_out(ctx, uid, p):
    """After the yes: start the call on this device, send it to the person's devices, or open the phone app."""
    import notaus
    if notaus.refuse("aktion", uid):
        _refused("notaus")
        note = notaus.why(uid, "kein Anruf")
        return _note(("(nicht möglich)", describe(p), note), note + " Sag dem Nutzer genau das.")
    if p["kind"] == "phone":
        if not _phone_here(ctx):
            _refused("no phone here")
            note = "Übers Telefon anrufen geht nur in der Android-App."
            return _note(("(nicht möglich)", describe(p), note), note + " Sag dem Nutzer genau das.")
        _count.today()["phone"] += 1
        _log("phone app opened")
        _diary(uid, f"Telefon-App geöffnet: {p['name']}")
        res = _note(("(bestätigt)", describe(p), "Telefon-App geöffnet"),
                    "Die Telefon-App öffnet sich mit der Nummer; angerufen wird, wenn der Nutzer dort auf den Hörer tippt. "
                    "Sag genau das in einem Satz.")
        res["event"] = {"type": "waehlen", "number": p["number"]}
        return res
    import anrufe
    import chats
    why = anrufe.why_not(p["to"], uid)
    try:
        cid = chats.open_one(uid, p["to"]) if not why else ""
    except (PermissionError, LookupError, OverflowError) as e:
        why = str(e) if not isinstance(e, LookupError) else "Diese Person gibt es nicht mehr."
    if why:
        _refused("not taken")
        return _note(("(nicht möglich)", describe(p), why), why + " Sag dem Nutzer genau das.")
    _ready[uid] = {"id": cid, "name": p["name"][:60], "video": bool(p.get("video")), "t": time.time()}
    _diary(uid, f"{'Videoanruf' if p.get('video') else 'Anruf'} an {p['name']}")
    where = device(ctx)
    if where in ("web", "iphone", "android"):
        _count.today()["started"] += 1
        _log("started here", video=int(bool(p.get("video"))))
        res = _note(("(bestätigt)", describe(p), "Anruf startet"),
                    ("Der Anruf startet jetzt auf diesem Gerät." if where != "android" else
                     "Die App öffnet den Anruf; dort auf „Anrufen“ tippen.") + " Sag genau das in einem Satz.")
        res["event"] = {"type": "anruf", "id": cid, "name": p["name"][:60], "video": bool(p.get("video"))}
        return res
    n = await _push(uid, p)
    if n:
        _count.today()["sent"] += 1
        note = ("Ich habe dir den Anruf aufs Handy geschickt: tippe auf die Mitteilung und dann auf „Anrufen“. "
                "Sag genau das in einem Satz.")
    else:
        note = ("Ich konnte dir den Anruf nicht aufs Handy schicken. Öffne die Spark-App oder das Panel: dort wartet er "
                "noch ein paar Minuten mit „Anrufen“. Sag genau das.")
    return _note(("(bestätigt)", describe(p), "aufs Handy geschickt" if n else "wartet in der App"), note)


def _diary(uid, title):
    import tagebuch
    tagebuch.note(uid, "anruf", title[:80])


async def _push(uid, p, now=None):
    """"📞 Sabine anrufen" to every device of the profile (never Telegram): PUSH_PER_HOUR at most."""
    import push
    now = time.time() if now is None else now
    q = [t for t in _pushed.get(uid, []) if now - t < 3600]
    if len(q) >= PUSH_PER_HOUR or not push.reachable(uid, private=True):
        _pushed[uid] = q
        _log("not sent", why="limit" if q and len(q) >= PUSH_PER_HOUR else "no device")
        return 0
    _pushed[uid] = q + [now]
    try:
        n = await push.send(uid, ("🎥 " if p.get("video") else "📞 ") + p["name"][:60] + " anrufen",
                            "Tippe hier, dann auf „Anrufen“.", tag="ruf", private=True, why="Anruf starten", to="every")
    except Exception as e:
        _log("not sent", error=type(e).__name__)
        return 0
    _log("sent to devices", devices=int(n or 0))
    return int(n or 0)


# ---------------------------------------------------------------- the call waiting for a tap on a device
def ready_for(uid, now=None):
    """The call this profile's next opened page or app offers with „Anrufen“, or None (/api/chats "ruf")."""
    now = time.time() if now is None else now
    x = _ready.get(uid)
    if not x or now - x["t"] >= READY_SECONDS or not usable(uid):
        _ready.pop(uid, None)
        return None
    return {"id": x["id"], "name": x["name"], "video": x["video"], "secs": int(READY_SECONDS - (now - x["t"]))}


def taken(uid, cid):
    """A call started from this chat (anrufe.start): the waiting one is done."""
    if (_ready.get(uid) or {}).get("id") == cid:
        _ready.pop(uid, None)
        _log("taken")


def decline(uid):
    """„Nein“ on the bar: the waiting call goes away on every device of the profile."""
    if _ready.pop(uid, None):
        _log("declined", why="bar")
        return True
    return False


def forget(uid):
    _ready.pop(uid, None)
    _pushed.pop(uid, None)
    profiles.pending_drop(uid, NAME)
