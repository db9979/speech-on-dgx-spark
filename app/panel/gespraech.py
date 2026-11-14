"""Natürliches Gespräch (plan gespraechshinweise/plan.md, Dominik 2026-11-14 „1 ja 2 ja 3 ja 4 ja 5 ja deine
Reihenfolge“, Paket A: Vorschlag 1 Gesprächshinweise und 3 Gesprächston; Paket B: 2 Anschluss-Angebot und 4 „Was
gibt's Neues?“).

In the voice mode a conversation should not be plain question and answer. Four parts:

    Gesprächston   a spoken turn the Weiche did not give a group (small talk) gets a fixed note with the question
                   (TON, chat_turn): short whole sentences, now and then a real question back, no „Kann ich sonst noch
                   helfen?“.
    Hinweise       after a spoken answer that needed no tool, the panel may add ONE fixed sentence about what it knows
                   and that fits the conversation („Apropos draußen: ab etwa 16 Uhr wird es wahrscheinlich regnen. Soll
                   ich dir das Wetter der nächsten Stunden sagen?“, chat_modell.gespraechshinweis). A „Ja“ within
                   OFFER_SECONDS becomes the fixed question of that kind (FRAGE), which then goes through the Weiche like
                   the person's own words; „Nein“ rests the kind for NO_PAUSE.
    Anschluss      after a spoken answer with a tool of ANSCHLUSS (the weather or the calendar) one fixed
                   offer of the kind that goes with it („Soll ich dir auch das Wetter für die nächsten Stunden
                   sagen?“), under the same sparing rules; no data is read for it.
    Überblick      „Was gibt's Neues?“, „Gib mir einen Überblick“ (NEUES, whole sentence, spoken) gets the panel's fixed
                   short overview (teil per kind: numbers and times only, without the model) and „Worüber soll ich mehr
                   erzählen?“; a kind's word („das Wetter“) or „Ja“ becomes that kind's fixed question.

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
LABEL = {"termine": "Termine", "wetter": "Wetter", "pakete": "Pakete", "einkauf": "Einkaufsliste",
         "ueberblick": "Überblick"}
# Anschluss (Vorschlag 2): a tool of the answer -> the kind offered after it, with its fixed offer (de, en)
ANSCHLUSS = {"weather": "termine", "calendar_events": "wetter"}
EIGENE = {"termine": {"calendar_events", "daily_briefing"}, "wetter": {"weather"}}   # tools that read the kind itself
ANGEBOT = {"termine": ("Soll ich dir auch sagen, was heute noch im Kalender steht?",
                       "Shall I also tell you what is left in your calendar today?"),
           "wetter": ("Soll ich dir auch das Wetter für die nächsten Stunden sagen?",
                      "Shall I also tell you the weather for the next hours?")}
# Überblick (Vorschlag 4): the whole spoken sentence asks what is new for the person
NEUES = re.compile(r"(?i)^\W*(was gibt'?s|was gibt es)( denn| so)? (neues|bei mir neues|neues bei mir|neues für mich)\W*$|"
                   r"^\W*(gib|mach) mir( mal)? (einen|ein) (kurzen |kleinen )?(überblick|update)"
                   r"( über (heute|den tag|meinen tag))?\W*$|^\W*was (ist|liegt) heute (so )?(los|an)( bei mir)?\W*$|"
                   r"^\W*(what'?s new( with me)?|give me (a|an) (quick |short )?(overview|update))\W*$")
# words that pick one kind after the overview
WAHL = {"termine": re.compile(r"(?i)\b(termin\w*|kalender|appointment\w*|calendar)\b"),
        "wetter": re.compile(r"(?i)\b(wetter|regen|weather|rain)\b"),
        "pakete": re.compile(r"(?i)\b(paket\w*|lieferung\w*|parcel\w*|deliver\w*)\b"),
        "einkauf": re.compile(r"(?i)\b(einkauf\w*|liste|shopping|list)\b")}
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
        chosen = [k for k in offer.get("kinds", ()) if WAHL[k].search(text)] if short else []
        if kind == "ueberblick" and len(chosen) == 1 and not NO.match(text):
            kind, yes = chosen[0], True
        elif short and YES.match(text) and not NO.search(text):
            if kind == "ueberblick":
                if not offer.get("kinds"):
                    return None
                kind = offer["kinds"][0]
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


def keep(uid, kind, src, en, offers, urgent=False, now=None, how=None, kinds=()):
    """The hint was said: the count starts anew, the kind rests KIND_GAP, a „Ja“ may follow when it offers more.
    how: the word for the journal (dringend, thema, anschluss, ueberblick); kinds: the overview's kinds to pick."""
    now = time.time() if now is None else now
    with _lock:
        st = _state(uid)
        if kind != "ueberblick":
            st["n"] = 0
            st["kinds"][kind] = now
        st["offer"] = {"kind": kind, "t": now, "src": src, "en": bool(en), "kinds": list(kinds)} if offers else None
    how = how or ("dringend" if urgent else "thema")
    print(f"gespraech: hinweis {kind} {how} {'angeboten' if offers else 'gesagt'}", flush=True)


# ---------------------------------------------------------------- Anschluss (Vorschlag 2)
def anschluss(uid, called, may, now=None):
    """Counts one spoken answer with tools and says which kind may be offered after it, or "". called: the names of
    the tools this answer ran; may: the kinds the profile may use. Never a kind the answer already read (EIGENE)."""
    now = time.time() if now is None else now
    called = set(called)
    with _lock:
        st = _state(uid)
        st["n"] += 1
        if st["n"] < EVERY:
            return ""
        for tool in sorted(called & set(ANSCHLUSS)):
            kind = ANSCHLUSS[tool]
            if kind in may and _free(st, kind, now) and not called & EIGENE[kind]:
                return kind
    return ""


def angebot(kind, en=False):
    return ANGEBOT[kind][1 if en else 0]


# ---------------------------------------------------------------- Überblick (Vorschlag 4)
def neues(text):
    """The whole sentence asks what is new for the person (NEUES)."""
    return bool(NEUES.match(str(text or "")[:120]))


def teil(kind, data, en=False):
    """One short fixed statement of the overview and whether there is more to tell, or ("", False)."""
    if data is None:
        return "", False
    if kind == "termine":
        if not data:
            return ("Your calendar is empty for the rest of today." if en else "Im Kalender steht heute nichts mehr."), False
        at = f"{data[0]:%H:%M}"
        if len(data) == 1:
            return (f"You have one more appointment today, at {at}." if en else
                    f"Heute steht noch ein Termin an, um {at} Uhr."), True
        return (f"You have {len(data)} more appointments today, the next at {at}." if en else
                f"Heute stehen noch {len(data)} Termine an, der nächste um {at} Uhr."), True
    if kind == "wetter":
        if data >= 0:
            return (f"Rain is likely from {data} o'clock." if en else
                    f"Ab etwa {data} Uhr wird es wahrscheinlich regnen."), True
        return ("No rain is expected for the next hours." if en else
                "In den nächsten Stunden ist kein Regen angesagt."), True
    if not data:
        return "", False
    if kind == "pakete":
        if data == 1:
            return ("A parcel should arrive today." if en else "Heute soll noch ein Paket kommen."), True
        return (f"{data} parcels should arrive today." if en else f"Heute sollen noch {data} Pakete kommen."), True
    if kind == "einkauf":
        if data == 1:
            return ("There is one thing on your shopping list." if en else "Auf der Einkaufsliste steht eine Sache."), True
        return (f"There are {data} things on your shopping list." if en else
                f"Auf der Einkaufsliste stehen {data} Sachen."), True
    return "", False


def ueberblick(teile, en=False):
    """The overview from [(kind, (statement, more))]: (text, the kinds a word may pick next)."""
    said = [(k, s, more) for k, (s, more) in teile if s]
    if not said:
        print("gespraech: ueberblick 0 teile", flush=True)
        return ("Right now nothing new is waiting for you." if en else "Gerade liegt bei dir nichts Neues an."), []
    kinds = [k for k, _, more in said if more]
    text = " ".join(s for _, s, _ in said)
    if kinds:
        text += " What shall I tell you more about?" if en else " Worüber soll ich mehr erzählen?"
    print(f"gespraech: ueberblick {len(said)} teile", flush=True)
    return text, kinds
