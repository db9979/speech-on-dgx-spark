"""Natürliches Gespräch (plan gespraechshinweise/plan.md, Dominik 2026-11-14 „1 ja 2 ja 3 ja 4 ja 5 ja deine
Reihenfolge“, Paket A: Vorschlag 1 Gesprächshinweise und 3 Gesprächston).

In the voice mode a conversation should not be plain question and answer. Two parts:

    Gesprächston   a spoken turn the Weiche did not give a group (small talk) gets a fixed note with the question
                   (TON, chat_turn): short whole sentences, now and then a real question back, no „Kann ich sonst noch
                   helfen?“.
    Hinweise       after a spoken answer that needed no tool, the panel may add ONE fixed sentence about what it knows
                   and that fits the conversation („Apropos draußen: ab etwa 16 Uhr wird es wahrscheinlich regnen. Soll
                   ich dir das Wetter der nächsten Stunden sagen?“, chat_modell.gespraechshinweis). A „Ja“ within
                   OFFER_SECONDS becomes the fixed question of that kind (FRAGE), which then goes through the Weiche like
                   the person's own words; „Nein“ rests the kind for NO_PAUSE.

The panel decides, never the model (Richtlinie Teil 0.2): which kind comes is a fixed word list over the person's own
last sentences (THEMEN), else after EVERY answers only something due soon (an appointment within URGENT_MIN minutes).
The sentence is fixed and holds only numbers and times the panel read itself from the profile's own data (calendar
cache, the weather of the own place, the parcels' last reading, the shopping list), never a title, a subject or any
other outside text. Nothing is fetched for it from the network: the calendar only from its cache within CAL_WAIT
(calendars.heute_noch), the weather only from a reading at most WEATHER_FRESH old (weather.regen_ab), the parcels only
from their last reading (parcels.heute_zahl).

Sparing: at most one hint per EVERY spoken answers, each kind once per KIND_GAP, never after outside text, under the
Notaus, over MCP, for guests or a voice that is not the profile's own, and no parcels (they come from mail) in the car.
The state is kept in memory only (counts and times, no words); a restart forgets it.

The bottom layer (test_schichten.GRUND): imports no panel module; the callers ask features, notaus and the data.
Off until the admin switches chat.gespraech on (Funktionen → Natürliches Gespräch); then for every profile the admin
did not block, each can switch it off for itself (preference talk_hints, Ich → Gespräch). Journal: „gespraech: …“
with fixed words and numbers only; Live: Ereignisse „Natürliches Gespräch“.
"""
import re
import threading
import time

KEY = "gespraech"
EVERY = 3                    # at most one hint per this many spoken answers without a tool
KIND_GAP = 2 * 3600          # one kind comes again at the earliest after this
OFFER_SECONDS = 15 * 60      # a „Ja“ counts this long after the hint
NO_PAUSE = 86400             # „Nein“ to a hint: that kind rests this long
URGENT_MIN = 60              # without a topic: only an appointment that starts within these minutes
CAL_WAIT = 0.4               # seconds for the calendar's own cache; slower means no hint, never waiting
WEATHER_FRESH = 3 * 3600     # the weather of the own place only from a reading at most this old
LOOK_BACK = 3                # the person's own last sentences the topic words look at
YES_MAX = 60
SPOKEN = {"speaker", "telefon", "watch", "car", "iphone"}   # channels (saetze.channel) whose answers are spoken anyway
NOT_IN_CAR = {"pakete"}      # comes from mail: never in the car
NOT_TALK = ("Notruf", "Stopp", "Abbruch")   # plaudern for these reasons is no small talk

# kind -> (function the profile must be allowed, topic words of the person's own sentences)
THEMEN = {
    "termine": ("calendar", re.compile(
        r"(?i)\b(viel los|stress\w*|voll\w* tag|keine zeit|beschäftigt|hektisch|müde|kaputt|erschöpft|anstrengend\w*|"
        r"busy|tired|exhausted|hectic)\b")),
    "wetter": ("weather", re.compile(
        r"(?i)\b(raus|rausgehen|draußen|draussen|spazier\w*|jogg\w*|laufen gehen|rad fahren|fahrrad\w*|radtour|"
        r"garten|grill\w*|ausflug|wander\w*|gassi|outside|walk|jogging|bike ride|hike|hiking)\b")),
    "pakete": ("parcels", re.compile(
        r"(?i)\b(bestellt|bestellung|lieferung|postbote|paketbote|warte auf (die|eine|meine) (post|lieferung|bestellung)|"
        r"ordered|delivery|mailman)\b")),
    "einkauf": ("tasks", re.compile(
        r"(?i)\b(kochen|koche|abendessen|mittagessen|essen machen|einkaufen|supermarkt|kühlschrank|hunger|"
        r"cook|cooking|dinner|groceries|grocery|fridge|hungry)\b")),
}
# the fixed question a „Ja“ becomes (de, en): it goes through the Weiche like the person's own words
FRAGE = {"termine": ("Was steht heute noch in meinem Kalender?", "What is left in my calendar today?"),
         "wetter": ("Wie wird das Wetter in den nächsten Stunden?", "What will the weather be in the next hours?"),
         "pakete": ("Welche Pakete kommen heute?", "Which parcels come today?"),
         "einkauf": ("Was steht auf meiner Einkaufsliste?", "What is on my shopping list?")}
LABEL = {"termine": "Termine", "wetter": "Wetter", "pakete": "Pakete", "einkauf": "Einkaufsliste"}
YES = re.compile(r"(?i)^\W*(ja|jo|jep|jawohl|gern|gerne|klar|na klar|ok|okay|sicher|bitte|erzähl\w*|sag (mal|schon|an|es)|"
                 r"lies vor|yes|yeah|yep|sure|please|go ahead|tell me)\b")
NO = re.compile(r"(?i)^\W*(nein|nee|nö|ne|lass mal|lass gut sein|nicht jetzt|später|brauch ich nicht|no|nope|not now|"
                r"no thanks)\b|\b(nicht|nein|no|not)\b")
TON = ("Gesprächston (fest vom Panel, nur dieser Hinweis): Dies ist ein gesprochenes Gespräch. Antworte kurz und "
       "natürlich in ganzen Sätzen, ohne Listen. Stelle ab und zu eine echte Gegenfrage, wenn sie zum Gespräch passt. "
       "Beende die Antwort nicht mit Floskeln wie „Kann ich sonst noch helfen?“ oder „Was kann ich noch für dich tun?“.")
TON_EN = ("Conversation tone (fixed by the panel, only this note): this is a spoken conversation. Answer briefly and "
          "naturally in whole sentences, without lists. Now and then ask a real question back when it fits the "
          "conversation. Do not end the answer with phrases like “Can I help with anything else?”.")

_lock = threading.Lock()
_st = {}                     # uid -> {"n": answers since the last hint, "kinds": {kind: t}, "no": {kind: t}, "offer": {...}}


def _state(uid):
    return _st.setdefault(uid, {"n": EVERY, "kinds": {}, "no": {}, "offer": None})


def spoken(body, channel):
    """The answer is spoken in the voice mode: never text only; the panel's page and the Android app only when the
    question itself was spoken (body „spoken“, chat.js); speakers, phone, watch, car and the iPhone's assistant always
    speak. channel: saetze.channel of the turn."""
    body = body if isinstance(body, dict) else {}
    return body.get("speak") is not False and (channel in SPOKEN or body.get("spoken") is True)


def talk(route):
    """The Weiche gave this turn no group (small talk) or plaudern without an emergency, stop or abort."""
    if route is None:
        return False
    names = list(getattr(route, "names", []) or [])
    why = getattr(route, "why", {}) or {}
    return not names or (names == ["plaudern"] and why.get("plaudern") not in NOT_TALK)


def ton(talking, en=False):
    """Vorschlag 3: the fixed note for the tone of a spoken small-talk turn (the caller checked everything else)."""
    if not talking:
        return ""
    print("gespraech: ton small talk", flush=True)
    return TON_EN if en else TON


# ---------------------------------------------------------------- the person answers a hint
def answer(uid, src, text, allowed=True, now=None):
    """A „Ja“ to the open hint of this conversation: (the fixed question of its kind, kind), else None. „Nein“ rests
    the kind for NO_PAUSE; anything else lets the hint lapse. Only the same conversation within OFFER_SECONDS."""
    now = time.time() if now is None else now
    text = str(text or "").strip()
    with _lock:
        st = _st.get(uid)
        offer = st and st.get("offer")
        if not offer:
            return None
        st["offer"] = None
        if offer["src"] != src or now - offer["t"] > OFFER_SECONDS or not allowed:
            print("gespraech: hinweis verfallen", flush=True)
            return None
        kind = offer["kind"]
        short = len(text) <= YES_MAX
        if short and YES.match(text) and not NO.search(text):
            yes = True
        elif short and NO.search(text):
            st["no"][kind] = now
            yes = False
        else:
            print(f"gespraech: hinweis {kind} uebergangen", flush=True)
            return None
    print(f"gespraech: hinweis {kind} {'angenommen' if yes else 'abgelehnt'}", flush=True)
    return (FRAGE[kind][1 if offer.get("en") else 0], kind) if yes else None


# ---------------------------------------------------------------- the hint after an answer
def _free(st, kind, now):
    return now - st["kinds"].get(kind, 0) >= KIND_GAP and now - st["no"].get(kind, 0) >= NO_PAUSE


def pick(uid, texts, may, car=False, now=None):
    """Counts one spoken answer without a tool and says which hint may come: (kind, urgent) or None. texts: the
    person's own last sentences, oldest first; may: the kinds whose function the profile may use."""
    now = time.time() if now is None else now
    text = " ".join(str(x)[:400] for x in reversed(list(texts)[-LOOK_BACK:]))   # the newest sentence first
    with _lock:
        st = _state(uid)
        st["n"] += 1
        if st["n"] < EVERY:
            return None
        best = None
        for kind, (_, words) in THEMEN.items():
            if kind not in may or (car and kind in NOT_IN_CAR) or not _free(st, kind, now):
                continue
            m = words.search(text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), kind)
        if best:
            return best[1], False
        if "termine" in may and _free(st, "termine", now):
            return "termine", True
    return None


def satz(kind, data, now_dt, en=False, urgent=False):
    """(fixed sentence, offers more) from the numbers the caller read, or None. data per kind: termine the start times
    (datetime) of today's timed appointments still to come, sorted; wetter the hour rain is likely from, -1 for none;
    pakete how many come today; einkauf how many entries are open on the shopping list. now_dt: the caller's clock."""
    if data is None:
        return None
    if kind == "termine":
        if urgent:
            if not data or (data[0] - now_dt).total_seconds() > URGENT_MIN * 60:
                return None
            at = f"{data[0]:%H:%M}"
            return ((f"Just so you know: you have an appointment at {at}. Shall I tell you which one?" if en else
                     f"Kurz zur Erinnerung: um {at} Uhr hast du einen Termin. Soll ich dir sagen, welchen?"), True)
        if not data:
            return (("At least your calendar is empty for the rest of today." if en else
                     "Immerhin: im Kalender steht heute nichts mehr."), False)
        at, n = f"{data[0]:%H:%M}", len(data)
        if n == 1:
            return ((f"By the way, you have one more appointment today, at {at}. Shall I tell you which one?" if en else
                     f"Übrigens steht heute noch ein Termin an, um {at} Uhr. Soll ich dir sagen, welcher?"), True)
        return ((f"By the way, you have {n} more appointments today, the next at {at}. Shall I tell you about them?"
                 if en else f"Übrigens stehen heute noch {n} Termine an, der nächste um {at} Uhr. Soll ich sie dir "
                            "sagen?"), True)
    if kind == "wetter":
        if data >= 0:
            return ((f"Speaking of outside: rain is likely from {data} o'clock. Shall I tell you the weather for the "
                     "next hours?" if en else f"Apropos draußen: ab etwa {data} Uhr wird es wahrscheinlich regnen. "
                     "Soll ich dir das Wetter der nächsten Stunden sagen?"), True)
        return (("Speaking of outside: no rain is expected for the next hours. Want to know more about the weather?"
                 if en else "Apropos draußen: für die nächsten Stunden ist kein Regen angesagt. Willst du mehr zum "
                            "Wetter wissen?"), True)
    if not data:
        return None
    if kind == "pakete":
        if data == 1:
            return (("By the way, a parcel should arrive today. Shall I tell you which one?" if en else
                     "Übrigens soll heute noch ein Paket kommen. Soll ich dir sagen, welches?"), True)
        return ((f"By the way, {data} parcels should arrive today. Shall I tell you which ones?" if en else
                 f"Übrigens sollen heute noch {data} Pakete kommen. Soll ich dir sagen, welche?"), True)
    if kind == "einkauf":
        if en:
            return (("By the way, there is one thing on your shopping list." if data == 1 else
                     f"By the way, there are {data} things on your shopping list.") + " Shall I read it to you?", True)
        return (("Auf deiner Einkaufsliste steht übrigens eine Sache." if data == 1 else
                 f"Auf deiner Einkaufsliste stehen übrigens {data} Sachen.") + " Soll ich sie dir vorlesen?", True)
    return None


def keep(uid, kind, src, en, offers, urgent=False, now=None):
    """The hint was said: the count starts anew, the kind rests KIND_GAP, a „Ja“ may follow when it offers more."""
    now = time.time() if now is None else now
    with _lock:
        st = _state(uid)
        st["n"] = 0
        st["kinds"][kind] = now
        st["offer"] = {"kind": kind, "t": now, "src": src, "en": bool(en)} if offers else None
    print(f"gespraech: hinweis {kind} {'dringend' if urgent else 'thema'} {'angeboten' if offers else 'gesagt'}",
          flush=True)
