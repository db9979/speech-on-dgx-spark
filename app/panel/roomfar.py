"""Room mode on another device of the profile, by voice or chat: "Raummodus im Wohnzimmer an".

Fixed rules here, never the model and never Home Assistant (the model used to look for a "Wohnzimmer"
in the smart home and ask for the code word). The panel reads the place from the person's own words
and matches it against the profile's own speakers (name or the room set at the speaker):

- starting needs the admin's chat.room_remote and the profile's room_remote (both off by default), the
  profile's own login, app or speaker (never Telegram or Siri alone, never a guest or a voice taken for
  someone else), a speaker that is connected right now, and a plain "Ja" to the question in the next
  message of the same conversation (15 minutes). The speaker says who started it.
- ending ("Raummodus im Wohnzimmer aus") always works for the profile's own rooms, without a question:
  it only means less.
- a sentence about another device's room mode while starting is off gets a fixed answer, nothing else.

A speaker that is not connected does not start later by itself (that would be a surprise in the room);
the switch "Raum" under Ich → Lautsprecher still does that on purpose.
"""
import re
import time

import features

PENDING_SECONDS = 900
MAX_CHOICE = 4
MINS = (15, 30, 60, 120, 240)
_PENDING = {}    # uid -> proposal (in memory: a restart drops it, the person just asks again)

ROOM = re.compile(r"\braum ?modus\b")
END = re.compile(r"\b(aus|ausschalten|ausmachen|abschalten|beenden|beende|beendet|beend|stopp|stop|stoppe|stoppen|"
                 r"deaktivieren|deaktiviere|abbrechen)\b")
START = re.compile(r"\b(an|ein|einschalten|anschalten|anmachen|starten|starte|start|aktivieren|aktiviere|aktiviert|"
                   r"schalte|schalt|mach|mache)\b")
# words around the place that are not the place
FILL = set("""kannst könntest kann du bitte mal doch noch jetzt gleich sofort wieder den die das der dem des im in am
auf für fuer beim bei vom von zum zur raummodus raum modus lautsprecher lautsprechers box gerät geraet geräte an ein
einschalten anschalten anmachen starten starte start aktivieren aktiviere aktiviert schalte schalt mach mache aus
ausschalten ausmachen abschalten beenden beende beendet beend stopp stop stoppe stoppen deaktivieren deaktiviere
abbrechen spark hey jarvis und mir mit minuten minute min stunde stunden eine einen ein halbe halben zwei drei vier
eins lass lasse soll sollst zuhören zuhoeren hören dort da bis lang lange für den ganzen mal""".split())
EVERY = ("alle", "überall", "allen", "allen geräten", "alle geräte")
NUM = {"eine": 1, "einen": 1, "ein": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4}


def admin_on():
    return features.admin_on("roomfar")


def profile_on(uid):
    return features.profile_on("roomfar", uid)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\wäöüß ]", " ", str(s or "").lower().replace("-", ""))).strip()


def _mins(t):
    m = re.search(r"\b(\d{1,3}) ?(?:minuten|minute|min)\b", t)
    if m:
        n = int(m.group(1))
    elif re.search(r"\bhalbe(?:n)? stunde\b", t):
        n = 30
    else:
        m = re.search(r"\b(\d|eine|einen|ein|zwei|drei|vier) stunden?\b", t)
        if not m:
            return None
        n = (int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]) * 60
    return min(MINS, key=lambda x: (abs(x - n), x))


def parse(text):
    """("start" | "end", place, minutes or None) from the person's own words, or None. Without a place it
    is the device's own room mode (esp32.py, room.py), not this."""
    t = _norm(text)
    if len(t) > 160 or not ROOM.search(t):
        return None
    t = ROOM.sub("raummodus", t)
    action = "end" if END.search(t) else "start" if START.search(t) else None
    if not action:
        return None
    mins = _mins(t) if action == "start" else None
    t = re.sub(r"\b\d{1,3} ?(?:minuten|minute|min)\b", " ", t)
    words = [w for w in t.split() if w not in FILL and not w.isdigit()]
    place = " ".join(words)[:60]
    if not place:
        return None
    return action, place, mins


def asks(text):
    """True when the message is about another device's room mode (chat_turn: no smart home in this turn)."""
    return parse(text) is not None


def _fits(place, names):
    p = _norm(place)
    for n in names:
        n = _norm(n)
        if n and (n == p or p in n or n in p or n.rstrip("n") == p.rstrip("n")):
            return True
    return False


def _speakers(uid):
    """The profile's own speakers: [{"id", "name", "area", "live", "room"}]."""
    import esp32
    devs = esp32._devices()
    out = []
    for did in esp32.speaker_ids():
        d = devs.get(did)
        if not d or d.get("user") != uid:
            continue
        s = esp32._live.get(did)
        out.append({"id": did, "name": d.get("name", ""), "area": esp32.room_cfg(esp32.by_device(did)[1])["area"],
                    "live": s is not None, "room": s is not None and s.room is not None,
                    "until": s.room["until"] if s is not None and s.room is not None else None,
                    "mins": esp32.room_cfg(esp32.by_device(did)[1])["mins"]})
    return sorted(out, key=lambda x: x["name"].lower())


def _clock(ts, uid):
    import datetime
    import proactive
    try:
        return datetime.datetime.fromtimestamp(ts, proactive._zone(proactive.prefs(uid))).strftime("%H:%M")
    except Exception:
        return time.strftime("%H:%M", time.localtime(ts))


def _say(name, note, result=""):
    return {"call": {"name": name, "args": "", "result": result or note},
            "system": "Raum-Modus: " + note + " Sag dem Nutzer genau das, kurz. Such nicht im Smart Home und frag "
                      "nicht nach einem Codewort."}


def why_not(ctx):
    """Why starting on another device is not possible for this request, or ""."""
    import esp32
    import room
    who = ctx.get("who")
    if not room.enabled():
        return "Der Raum-Modus ist ausgeschaltet (Admin: Funktionen)."
    if not admin_on():
        return ("Den Raum-Modus eines anderen Geräts zu starten ist ausgeschaltet (Admin: Funktionen → "
                "„Raum-Modus aus der Ferne starten“). Am Gerät selbst geht „Raummodus an“.")
    if not who:
        return "Den Raum-Modus aus der Ferne starten geht nur für angemeldete Profile."
    if not ctx.get("own"):
        return "Den Raum-Modus aus der Ferne startet nur das Profil selbst, an seinem eigenen Gerät."
    if ctx.get("client") in ("telegram", "siri"):
        return "Über " + ("Telegram" if ctx.get("client") == "telegram" else "Siri") + \
            " startet der Raum-Modus nicht aus der Ferne. Im Panel, in der iPhone-App oder am Lautsprecher geht es."
    if not esp32.admin_on() or not esp32.profile_on(who["id"]):
        return "Für dein Profil sind Lautsprecher ausgeschaltet (Ich → Lautsprecher)."
    if not profile_on(who["id"]):
        return ("Für dein Profil ist das ausgeschaltet (Ich → Raum-Modus → „Raum-Modus an einem anderen Gerät "
                "starten“). Am Gerät selbst geht „Raummodus an“.")
    return ""


# ---------------------------------------------------------------- the proposal waiting for "Ja"
def pending(uid):
    p = _PENDING.get(uid)
    if p and time.time() - p["t"] > PENDING_SECONDS:
        _PENDING.pop(uid, None)
        return None
    return p


def drop_pending(uid):
    """Drops the proposal; one made in this very turn only loses its mark (see messages.drop_pending)."""
    p = _PENDING.get(uid)
    if p and p.pop("fresh", False):
        return
    _PENDING.pop(uid, None)


def _from(ctx):
    """Who started it, said by the speaker: the device the request came from."""
    if ctx.get("client") == "speaker":
        return ("dem Lautsprecher " + ctx["device"]) if ctx.get("device") else "einem Lautsprecher"
    if ctx.get("app"):
        return "der iPhone-App"
    return "dem Panel"


async def start(uid, did, mins, by):
    """Starts room mode on the profile's own connected speaker now. Returns the sentence for the person."""
    import esp32
    hit = next((x for x in _speakers(uid) if x["id"] == did), None)
    if not hit:
        return "NICHT gestartet: Der Lautsprecher gehört nicht (mehr) zu deinem Profil."
    s = esp32._live.get(did)
    if s is None:
        return f"NICHT gestartet: {hit['name']} ist gerade nicht verbunden."
    if s.room is not None:
        return f"{hit['name']} hört schon zu, bis {_clock(s.room['until'], uid)}."
    if s.answer and not s.answer.done():
        s.answer.cancel()
    s.room_ask = {"source": "remote", "mins": mins, "by": by}
    s.start_answer(None)
    print(f"room: start at speaker {hit['name']} asked from {by} ({mins} min)", flush=True)
    return f"{hit['name']} hört jetzt {mins} Minuten zu."


async def answer(ctx, latest):
    """The person's yes to a waiting start, or a new request about another device's room mode:
    {"call", "system"} or None."""
    import calendars
    import roomlive
    who = ctx.get("who")
    if not who:
        return None
    uid, src = who["id"], ctx.get("src", "")
    p = pending(uid)
    if p and p.get("src") == src:
        _PENDING.pop(uid, None)
        if calendars.confirms(latest) and not why_not(ctx):
            note = await start(uid, p["did"], p["mins"], p["by"])
            return _say("room_start (bestätigt)", note)
        if not parse(latest):
            return _say("room_start (abgelehnt)", f"{p['name']} startet NICHT, weil der Nutzer nicht zugestimmt hat.")
    got = parse(latest)
    if not got:
        return None
    action, place, mins = got
    if action == "end":
        if not roomlive.enabled() or not ctx.get("own"):
            return None
        rooms = roomlive.mine(uid)
        if place in EVERY:
            n = await roomlive.end_all("far", uid)
            return _say("room_end", "Raum-Modus überall beendet." if n else "Gerade hört kein Gerät zu.")
        areas = {x["id"]: x["area"] for x in _speakers(uid)}
        hits = [r for r in rooms if _fits(place, [r["name"], areas.get(r.get("device"), "")])]
        if not hits:
            return _say("room_end", f"Im Raum-Modus ist kein Gerät „{place}“." +
                        (" Gerade hören zu: " + ", ".join(r["name"] for r in rooms) + "." if rooms else
                         " Gerade hört kein Gerät zu."))
        for r in hits:
            await roomlive.end(r["key"], "far", uid)
        return _say("room_end", "Raum-Modus beendet: " + ", ".join(r["name"] for r in hits) + ".")
    why = why_not(ctx)
    if why:
        print("room: start from afar not possible:", why.split(" (")[0], flush=True)
        return _say("room_start (nicht möglich)", why)
    mine = _speakers(uid)
    if not mine:
        return _say("room_start (nicht möglich)", "Dein Profil hat keinen Lautsprecher (Ich → Lautsprecher).")
    hits = [x for x in mine if _fits(place, [x["name"], x["area"]])]
    if not hits:
        return _say("room_start (nicht möglich)", f"Ich finde keinen Lautsprecher „{place}“. Deine Lautsprecher: "
                    + ", ".join(x["name"] for x in mine[:8]) + ".")
    if len(hits) > 1:
        return _say("room_start (Rückfrage)", "Mehrere Lautsprecher passen: " + ", ".join(x["name"] for x in hits[:MAX_CHOICE])
                    + ". Sag es noch einmal mit dem ganzen Namen.", "wartet auf genaueren Namen")
    x = hits[0]
    if not x["live"]:
        return _say("room_start (nicht möglich)", f"{x['name']} ist gerade nicht verbunden, darum startet dort nichts. "
                    "Der Schalter „Raum“ unter Ich → Lautsprecher startet ihn beim nächsten Weckwort.")
    if x["room"]:
        return _say("room_start", f"{x['name']} hört schon zu, bis {_clock(x['until'], uid)}.")
    mins = mins or x["mins"]
    _PENDING[uid] = {"did": x["id"], "name": x["name"], "mins": mins, "by": _from(ctx), "src": src,
                     "t": time.time(), "fresh": True}
    return {"call": {"name": "room_start (Vorschlag)", "args": f"{x['name']}, {mins} Min.", "result": "wartet auf Ja"},
            "system": f"Raum-Modus: Noch NICHT gestartet. Frag den Nutzer genau: „Soll {x['name']} {mins} Minuten "
                      "zuhören?“ Erst sein Ja in der nächsten Nachricht startet es. Such nicht im Smart Home und frag "
                      "nicht nach einem Codewort."}


def offer(ctx):
    """No tools: everything here goes by fixed rules (answer)."""
    return None
