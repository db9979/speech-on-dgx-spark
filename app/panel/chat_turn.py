"""One chat turn, before the model is asked: who is speaking and what they may use (profile, voice, device
key, Telegram, iPhone app), the system prompt, answers to waiting proposals ("Ja" to a calendar entry,
a mail change, a correction ...), the tools on offer and the locks after outside text.

prepare() returns a Turn: every value it worked out, as attributes (t.who, t.ha, t.tools ...).
chat._answer() asks the model with it, chat_tools.run() carries out the tool calls."""
import asyncio
import os
import time
import sys

import httpx
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import admin_cookie_ok  # noqa: E402
import calendars  # noqa: E402
import documents  # noqa: E402
import extras  # noqa: E402
import faelle  # noqa: E402
import fixes  # noqa: E402
import hamelden  # noqa: E402
import aendern  # noqa: E402
import nasablage  # noqa: E402
import meinmcp  # noqa: E402
import homeassistant  # noqa: E402
import images  # noqa: E402
from common import load_config  # noqa: E402
import mail  # noqa: E402
import proactive  # noqa: E402
import profiles  # noqa: E402
import speakers  # noqa: E402
import taten  # noqa: E402
import tidy  # noqa: E402
import wissen  # noqa: E402
import chat  # noqa: E402  (constants and helpers; imported fully before any call)
import features  # noqa: E402
import wartung  # noqa: E402  (Wartungspause)


def at_speaker(request, body):
    """The request comes from an own speaker (its key, or it says so: that only makes it stricter)."""
    if body.get("client") == "speaker" or "speech_voice" in request.scope:
        return True
    dev = profiles.device(request)
    if dev and not dev["scope"]:
        import esp32
        return esp32.by_device(dev["id"])[0] is not None
    return False


def quiet(request, body, pset, car):
    """"Antworten vorlesen" switched off (profile setting speak): the answer comes as text only, without TTS and
    without the ready-made sentence (ack.py). A speaker without a screen and CarPlay keep speaking: there is
    nothing to read there. The request may always ask for text only itself (speak false), never for sound."""
    return pset.get("speak") is False and not car and not at_speaker(request, body)


def shared_stranger(request, body, who):
    """Why this turn at a shared device gets no personal things ("" when it may): the request comes
    from an own speaker (its key, or it says so: that only makes it stricter) and the voice of this
    recording was not clearly the profile's own. Whose voice it was comes only from the panel itself
    (esp32.py sets it in the request scope), never from what a request says."""
    if not at_speaker(request, body) or not who:
        return ""
    voice = request.scope.get("speech_voice")
    if voice and voice == who["id"]:
        return ""
    return str(request.scope.get("speech_voice_why") or "voice not recognized as the profile's own")[:160]


def notaus_note(held, mine=False):
    if not held:
        return ("Mein Notaus dieses Profils ist an: Du kannst nichts ändern oder auslösen, nur lesen und antworten. "
                "Fragt der Nutzer danach, sag ihm genau das in einem Satz: sein eigener Notaus sperrt es, bis er ihn "
                "unter Ich → Sicherheit aufhebt.")
    return (f"Notaus Stufe {held} ist an: " + ("Du kannst nichts ändern oder auslösen und " if held >= 2 or mine else "")
            + "erreichst nichts im Internet. Fragt der Nutzer danach, sag ihm genau das in einem Satz: der Notaus "
            "sperrt es, bis ein Admin ihn aufhebt.")


# a plain yes that finds no proposal of its own device and conversation (profiles.quelle), while one waits elsewhere or
# was replaced from elsewhere (review A-H3): the model only says that, nothing was done
YES_ELSEWHERE = ("Ja: Hier wartet kein Vorschlag auf dieses Ja. Ein Vorschlag wartet auf einem anderen Gerät oder in einem "
                 "anderen Gespräch, oder er wurde dort durch einen neueren ersetzt. Nichts wurde ausgeführt. Sag das in "
                 "einem kurzen Satz, ohne Werkzeug, und behaupte nicht, etwas sei erledigt.")


def waiting_mods():
    """Every module that keeps one proposal per profile waiting for a plain "Ja" (profiles.pending_set): Notaus
    drops them all, and the Freigabe-Karte (ablauf.py) asks about the one this turn left."""
    import agent
    import messages as inbox   # (messages is the conversation in prepare)
    import tasks
    import roomfar
    import remarkable
    import rufen
    import senden
    return (calendars, tidy, tasks, fixes, agent, inbox, roomfar, meinmcp, hamelden, aendern, nasablage, rufen, remarkable, senden)


class Turn:
    """The values prepare() worked out for one turn (plus the queues chat._answer() adds)."""

    def __init__(self, values):
        self.__dict__.update(values)


async def prepare(request):
    """One turn of the chat, worked out in fixed stages (Kritische Prüfung 2026-11-12 point 3). Each stage reads
    and writes only z, the Turn under construction; the order is fixed, a stage only reads what the stages before
    it set. The Turn holds every value (as Turn(locals()) did before)."""
    z = Turn({"request": request})
    for stufe in STUFEN:
        early = await stufe(z)
        if early is not None:   # only the first stage ends early: the stop word ended the turn
            return early
    return z


async def _eingang(z):
    """Stufe 1 Eingang: die Nachrichten, wer fragt, Gast oder nicht, das Stoppwort (endet hier früh)."""
    z.body = await z.request.json()
    if isinstance(z.body, dict) and profiles.key_scope(z.request) == "tui":
        z.body["client"] = "tui"   # a terminal's key (terminal.py) says what it is, never the request; Markdown shown as text
    z.cfg = load_config()
    z.ccfg = z.cfg.get("chat", {})   # with the shipped defaults (common.load_config)
    # text only (no image links or other parts); an answer the browser marked as made from mail or
    # other outside text keeps that mark (the browser is the person's own and has no reason to lie)
    # every message (the latest too, which the trimming always keeps) is cut at chat.MAX_TURN_CHARS:
    # the word rules below run over it on the event loop
    # a described screen (bedienen.look) is never carried on: later turns see only profiles.SCREEN_NOTE, the panel's
    # own sentence, so no word of the screen is left and nothing is locked by it (V01.0.752: "Hol das Terminal nach
    # vorn" right after "Was siehst du?" was locked before)
    # (not named "screen": every value of z is on the turn, and turn.screen says this answer described a screen)
    def screen_msg(m):   # marked by the browser or the app, or the note stored in its place before V01.0.752
        return m["role"] == "assistant" and (bool(m.get("screen")) or m["content"].strip() == profiles.SCREEN_NOTE)
    z.screen_msg = screen_msg
    z.messages = [dict({"role": m["role"], "content": profiles.SCREEN_NOTE if z.screen_msg(m) else m["content"][:chat.MAX_TURN_CHARS]},
                     **({"mark": "mail" if m.get("mail") else "outside"}
                        if (m.get("mail") or m.get("outside")) and not z.screen_msg(m) else {}))
                for m in (z.body.get("messages") if isinstance(z.body.get("messages"), list) else [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                and m["content"].strip()]
    if not z.messages:
        raise HTTPException(400, "messages are required")
    # what the assistant said right before this message (a note it made by itself may open the
    # conversation, which the trimming below drops)
    z.said_before = next((str(m["content"]) for m in reversed(z.messages[:-1]) if m["role"] == "assistant"), None) \
        if z.messages[-1]["role"] == "user" else None
    # everything the assistant said in this conversation, before trimming: notes it sent by itself are looked up
    # by their text further down (proactive.basis_note), also when the trimming drops them
    z.said_all = [str(m["content"]) for m in z.messages if m["role"] == "assistant"][-20:]
    # with chat.prompt_cache the kept part starts at a fixed question for several turns (chat.trim_history)
    z.messages = chat.trim_history(z.messages, chat.history_chars(z.ccfg), anchor=z.ccfg.get("prompt_cache") is True)
    # Outside text from earlier turns: the latest such answer still counts as read in this turn (it
    # could ask for something "in the next message"), so this turn starts locked; older ones are not
    # sent again at all.
    z.marked = [i for i, m in enumerate(z.messages) if m.get("mark")]
    z.carry = z.messages[z.marked[-1]]["mark"] if z.marked and z.marked[-1] >= len(z.messages) - 3 else None
    z.came_from = z.carry   # what the answer right before rested on (for learning from corrections)
    # Guests (no profile) and a voice the shared speaker did not recognize only ask and get answers: no tool, no
    # memory, no history, no timers, no web search (Dominik 2026-10-13: "einfach bloß Frage, Antwort"). Fixed rule.
    z.me0 = profiles.current(z.request)
    if z.body.get("client") == "android":   # the Android app's assistant sheet: only while released, never guests
        import android
        z.android = android
        z.android.assist_gate(z.request, z.me0)
    z.guest = not z.me0 or bool(shared_stranger(z.request, z.body, z.me0))
    # A voice recognized by the speech recognition (signed token, speakers.check, good once): read here once, for the
    # answer to the panel's question which way (klaeren weg, below) and for the profile of this turn (further down)
    z.heard_id = speakers.check(z.body.get("speaker"), z.me0["id"]) \
        if z.ccfg.get("speaker_id", False) and z.body.get("speaker") and not z.guest else None
    z.search = bool(z.ccfg.get("search") and z.ccfg.get("search_url")) and not z.guest and features.allowed("search", z.me0["id"], z.ccfg)
    # The answer before came from mail (also a mail note the assistant made by itself): kept in this
    # turn it would lock the web search too (its text could carry the mail away). So it is kept only
    # when the new question goes on about it ("Was schreibt sie noch?"); any other question (or one
    # that clearly wants the web) leaves it out, and with no word of the mail in this turn the search
    # and everything else is open again.
    if z.carry == "mail" and z.search and z.messages[-1]["role"] == "user":
        z.ask = z.messages[-1]["content"]
        z.wants_web = bool(chat.needed(z.ask, {"web_search"}, z.ccfg.get("tool_words", "")))
        if z.wants_web or not chat.MAIL_FOLLOW_UP.search(z.ask):
            z.carry = None
            print("chat: answer from mail before; this question", "wants the web" if z.wants_web else "is not about it",
                  "- that answer is left out, search offered", flush=True)
    # The person asks to send a message to someone ("Schreib Anna, dass ..."): the answer before, made
    # from outside text, would lock that. It is left out instead, so no word of it can get into the
    # message, and the panel reads the message back before the "Ja" (messages.py).
    if z.carry and z.messages[-1]["role"] == "user":
        import messages as inbox   # (messages is the conversation here)
        z.inbox = inbox
        if z.inbox.wants_send(z.messages[-1]["content"]):
            z.carry = None
            print("chat: answer from outside text before; this message asks to write to someone - that answer "
                  "is left out, messages offered", flush=True)
    # the switch (intent.py): what the person's own latest message asks for, by fixed rules only.
    # With the admin's chat.routing on (released for the profile), it narrows the tools (further down)
    # and a new request of the person's own that does not point back at an answer made from outside
    # text leaves that answer out, and with it its lock ("Setz das auf die Liste" keeps it locked).
    # „Auch im Internet suchen“ (lokal.web_offer, plan such-index/zuverlaessig.md step 5): the chip under an answer from
    # the own data sends its fixed words; the panel takes the question's own words it kept for this profile and device
    # (only for the very next message, every message takes the offer away) and searches the web with exactly those,
    # never a word of what was found. The offer is never kept after mail, for guests, another voice or MCP.
    # where this turn comes from: client, conversation and device (profiles.quelle, the one key for everything that
    # waits on an answer: a yes, the code word, the panel's own question, a follow-up, the web chip; P6 Gerät statt Profil)
    z.src0 = profiles.quelle(z.request, z.body)
    import lokal
    z.lokal = lokal
    z.web_tap = ""
    if z.me0 and z.messages[-1]["role"] == "user":
        z.web_tap = z.lokal.web_pop(z.me0["id"], z.src0)
        z.web_tap = z.web_tap if z.web_tap and not z.guest and z.lokal.web_chip(z.messages[-1]["content"]) else ""
        if z.web_tap:
            z.messages[-1] = dict(z.messages[-1], content=z.web_tap)
    import intent   # (needs chat fully loaded: its word lists)
    z.intent = intent
    z.ask0 = z.messages[-1]["content"] if z.messages[-1]["role"] == "user" else ""
    # Abbrechen heißt aus (stoppwort.py, Dominik 2026-11-10 2a): a whole sentence of stop words or a goodbye ends the
    # talk by the panel's fixed rule, before the switch and before any model: no answer, no tool, nothing kept. The
    # panel's own waiting question of this conversation (klaeren.py) lapses; the clients close the microphone
    # (event "ende", chat._chat)
    # (an answer to the Spark's own note, „Nicht jetzt“, stays that note's feedback: proactive.reply pauses it)
    import stoppwort
    z.stoppwort = stoppwort
    z.ende = z.stoppwort.ende(z.ask0) if z.ask0 and not z.web_tap else ""
    if z.ende and z.me0 and not z.guest and proactive.answers_note(z.me0["id"], z.ask0, z.said_before):
        z.ende = ""
    if z.ende:
        if z.me0 and not z.guest:
            import klaeren
            z.klaeren = klaeren
            if z.klaeren.waiting(z.me0["id"], z.src0):
                z.klaeren.drop(z.me0["id"])
        import verlauf
        z.verlauf = verlauf
        z.kind = z.verlauf.kind_of(z.request, z.body)   # a fixed word for the kind of device
        print(f"chat: ende {z.ende} | {z.kind}", flush=True)
        return Turn({"ende": z.ende, "body": z.body, "who": None if z.guest else z.me0, "ask_text": z.ask0})


async def _weg(z):
    """Stufe 2 Weg: der feste Weg, die Weiche, Hilfe-Seite, die Wahl des Modells im Hintergrund, der Grund-Prompt."""
    # Rückfragen der Weiche (klaeren.py area "weg", P5): the answer to the panel's question which way the person's own
    # sentence before goes, by fixed rules (a chip, a number, a word of the way, „Einfach antworten“), only in the same
    # conversation, from the own login or voice, never over MCP. The sentence then runs again with the chosen group
    # (reason „Rückfrage“), or as plain chat without a changing tool („Einfach antworten“); the choice is a correction
    # signal for the Weiche (weiche.learn_choice: groups and numbers only). Anything else lets the question lapse.
    z.weg = None
    if z.ask0 and z.me0 and not z.guest and not z.web_tap and not z.request.scope.get("speech_mcp") \
            and z.heard_id in (None, z.me0["id"]) and features.allowed("klaerenweg", z.me0["id"], z.ccfg):
        import klaeren
        z.klaeren = klaeren
        z.weg = z.klaeren.weg_answer(z.me0["id"], z.src0, z.ask0, time.time())
    if z.weg:
        z.messages[-1] = dict(z.messages[-1], content=z.weg["said"])
        z.ask0 = z.weg["said"]
        z.g = z.weg["group"]
        z.route = z.intent.Route([z.g], {z.g: "Rückfrage"}) if z.g else z.intent.Route(["plaudern"], {"plaudern": "Einfach antworten"})
        import weiche
        z.weiche = weiche
        z.weiche.learn_choice(z.weg["route"], z.g)
    else:
        z.route = z.intent.classify_cfg(z.ask0, z.ccfg)
    # how long ago the person's own message before came in this conversation (P4, review D-8: a follow-up only while
    # it is fresh); the clock is read here, intent only gets the number
    z.age0 = z.intent.asked_age(((z.me0 or {}).get("id") or "", z.src0), time.time()) if z.ask0 else None
    # a follow-up („Und morgen?“) takes the group of the person's own question just before (plan weiche-intelligenter 1)
    if z.ask0 and not z.route.names:
        z.before0 = next((m["content"] for m in reversed(z.messages[:-1])
                        if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        # Rückfrage-Karten 3a: the answer before asked the person (ablauf.py, only with „Ablauf und Freigabe zeigen“)
        import ablauf
        z.ablauf = ablauf
        z.answered = bool(z.before0 and z.me0 and features.allowed("ablauf", z.me0["id"], z.ccfg)
                        and z.ablauf.was_asked(z.me0["id"], z.src0, z.ask0))
        z.follow = z.intent.follow_up(z.ask0, z.before0, z.ccfg, z.answered, z.age0)
        if z.follow:
            z.route = z.follow
            print("weiche: Antwort auf Rückfrage -" if z.answered else "weiche: Folgefrage -", z.route.label(), flush=True)
        elif z.age0 is not None and z.age0 > z.intent.FOLLOW_SECONDS and z.intent.follow_up(z.ask0, z.before0, z.ccfg, z.answered):
            print("weiche: Folgefrage zu alt - unklar", flush=True)
    # a photo of this turn with a wish to change it is Bilder ändern (bilder.from_turn decides by its fixed rule
    # further down): the group bild, so no model pick starts and Logs → Anfragen does not show it as „unklar“
    if z.ask0 and not z.route.names and images.ids_of(z.body):
        import bilder
        z.bilder = bilder
        if z.bilder.wants_change(z.ask0):
            z.route = z.intent.Route(["bild"], {"bild": "Foto ändern"})
            print("weiche: Foto mit Änderungswunsch - bild", flush=True)
    z.route_on = bool(z.me0 and features.allowed("routing", z.me0["id"], z.ccfg))
    # "Frag Spark" (hilfe.py): asked from a page of the panel, the question is about the Spark itself (a fixed
    # rule on where it was asked, never the model); the admin's own login only counts for the Spark's switches
    import hilfe
    z.hilfe = hilfe
    z.hilfe_page = z.hilfe.page_of(z.body, z.me0["id"], z.ccfg) if z.me0 else None
    z.hilfe_focus = z.hilfe.focus_of(z.body, z.me0["id"], z.ccfg) if z.me0 else None
    z.hilfe_admin = z.hilfe.admin_here(z.request) if z.me0 else "profile"
    # where the question came from (plan hilfe-besser 10): only what the panel knows itself, never the question
    z.hilfe_origin = z.hilfe.origin(z.body, z.request)
    z.hilfe_app = z.hilfe.app_view(z.body)
    if (z.hilfe_focus or z.hilfe.page_rule(z.hilfe_page, z.ask0, z.route.names)) and z.route_on and z.hilfe_origin != "mcp" and not z.weg:
        z.route = z.intent.Route(["spark"], {"spark": "Schalter" if z.hilfe_focus else "Seite"})
    # chat.route_model "on": the model's pick for a question no rule recognizes starts right here and runs while
    # the panel prepares the rest of the turn (plan „Anfrage aufteilen“ 2); it is waited for further down
    z.pick_state = None   # Logs → Anfragen: what became of the model's pick
    z.pick_info = {}      # with chat.route_model "systemone": its probability
    z.pick_task = asyncio.create_task(z.intent.ask_model(z.ccfg, z.ask0, z.pick_info, z.me0["id"])) \
        if z.route_on and z.ask0 and not z.route.names and z.ccfg.get("route_model") in ("on", "systemone") else None
    if z.carry == "outside" and z.route_on and z.intent.wants_own(z.route, z.ask0):
        z.carry = None
        print("weiche: answer from outside text before; this message asks for", z.route.label(),
              "in its own words - that answer is left out, nothing locked", flush=True)
    # a song in the person's own words („mach daraus einen House-Track“): the last answer from outside text (chords,
    # a style found on the web) stays as data for the description instead of being left out (Dominik 2026-10-16:
    # without it the model made up other chords); it locks the turn like any carried answer, the song excepted
    import musik
    z.musik = musik
    if not z.carry and z.marked and z.marked[-1] >= len(z.messages) - z.musik.BACK and z.messages[z.marked[-1]]["mark"] == "outside" \
            and z.musik.wants(z.ask0):
        z.carry = "outside"
        print("musik: answer from outside text before kept as data for the song wish", flush=True)
    z.messages, z.gone = chat.left_out(z.messages, z.marked[-1] if z.carry else -1)
    z.system = z.ccfg.get("system_prompt") or ""
    # "Schneller Antwortbeginn" (chat.prompt_cache): what holds for this turn only goes with the question
    # (turn_notes, chat._answer), so the system prompt, the tool list and the conversation before stay the same
    # from turn to turn and the LLM server reads them from its cache. Switched off, all of it is in the system prompt.
    z.cache_on = z.ccfg.get("prompt_cache") is True and z.messages[-1]["role"] == "user"
    z.turn_notes = []

    def per_turn(system, text):
        if z.cache_on:
            z.turn_notes.append(text)
            return system
        return (system + "\n\n" + text).strip()
    z.per_turn = per_turn
    if z.gone:
        z.system = z.per_turn(z.system, chat.LEFT_OUT_NOTE)
        print("chat:", z.gone, "earlier answer(s) from outside text left out with their questions", flush=True)
    # "Spark fragen" from another program over MCP (mcpserver.py; only the panel sets this in the scope): the
    # question is outside text from the start, and the turn only reads, with the tools the connection was given.
    # No memory, no earlier conversations, no smart home, no mail, no proposals and no "Ja" to waiting ones.
    z.mcp = z.request.scope.get("speech_mcp")
    if z.mcp:
        import mcpserver
        z.mcpserver = mcpserver
        z.carry = "outside"
        z.messages = [m for m in z.messages[-1:] if m["role"] == "user"]
        z.system = (z.system + "\n\n" + z.mcpserver.MCP_HINT).strip()
    # an attached photo or document: outside text, so this answer is locked like one made from the web
    z.attach = chat.attachment(z.body) if z.messages[-1]["role"] == "user" else None
    if z.attach:
        z.carry = z.carry or "outside"
        z.kind, z.name, z.text, z.cut = z.attach
        z.system = z.per_turn(z.system, (chat.ATTACH_HINT + " " + ("Foto" if z.kind == "photo" else "Dokument")
                                   + (f" „{z.name}“" if z.name else "") + "\n" + chat.wrap_outside(z.text)
                                   + ("\n" + chat.ATTACH_CUT if z.cut and z.kind == "document" else "")).strip())
        print("chat: attachment", z.kind, len(z.text), "chars, answer locked like outside text", flush=True)
    # the time changes every minute: early in the system prompt it would make the model read the
    # prompt, all tools and the whole history anew each turn. With chat.prompt_cache it goes with the
    # question instead (only to the model, never into the history), so the server's cache keeps the rest.
    z.time_note = None
    if z.ccfg.get("datetime", True):
        if z.cache_on:
            z.time_note = chat.now_line(z.body.get("tz"))
        else:
            z.system = (z.system + "\n\n" + chat.now_line(z.body.get("tz"))).strip()
    # why the search is (not) offered, for the journal and for the model (never silently missing)
    print("chat: web search", "NOT offered: guest, only questions and answers" if z.guest
          else "NOT offered: switched off (Funktionen → Websuche)" if not z.ccfg.get("search")
          else "NOT offered: not for this profile (Personen und Geräte → Gesperrte Funktionen)" if not features.allowed("search", z.me0["id"], z.ccfg)
          else "NOT offered: no SearXNG address" if not z.search
          else "locked: the answer before came from e-mail" if z.carry == "mail" else "offered", flush=True)
    if z.cache_on and z.search and z.carry == "mail":   # the usual hint stays, the lock goes with the question
        z.system = (z.system + "\n\n" + chat.SEARCH_HINT).strip()
        z.turn_notes.append(chat.SEARCH_LOCKED_HINT)
    else:
        z.system = (z.system + "\n\n" + (chat.GUEST_HINT if z.guest else chat.SEARCH_LOCKED_HINT if z.search and z.carry == "mail"
                                      else chat.SEARCH_HINT if z.search else chat.SEARCH_OFF_HINT)).strip()


async def _wer(z):
    """Stufe 3 Wer: Person, Lautsprecher und Stimme, Stil, Rolle, Gerät, Gedächtnis, Bilder, Smart Home, Rückfragen."""
    z.who = profiles.current(z.request)
    # A shared device (an own speaker in a room, see esp32.py): anyone in the room can talk to it, so
    # the device key alone is nobody's word. Personal things (mail, calendar, memory, documents,
    # contacts, reminders, messages, smart home ...) only when the speech recognition clearly heard the
    # profile's own voice in this very recording; anyone else gets what a guest gets. Fixed rule, no switch.
    z.stranger = shared_stranger(z.request, z.body, z.who)
    if z.stranger:   # Zustand → Logs, area "Lautsprecher", yellow: only the reason, never what was asked
        if z.body.get("client") == "telefon":
            print("telefon: persoenliches zurueckgehalten -", z.stranger, "- guest rights for this question", flush=True)
        else:
            print("esp32: personal data withheld at", (profiles.device_name(z.request) or "speaker")[:40],
                  "-", z.stranger, "- guest rights for this question", flush=True)
    z.sound_of = z.who      # voice, speed and length of the answer stay the speaker's own
    # A voice recognized by the speech recognition (signed token, see speakers.py) picks that
    # profile for this turn; its own settings apply then, not the ones this browser sends.
    z.heard = z.heard_id and profiles.by_id(z.heard_id)
    z.own_browser = not z.heard or (z.who and z.who["id"] == z.heard["id"])
    z.device_owner = z.who
    if z.heard:
        z.who = z.heard
    if z.stranger:
        z.who, z.own_browser = None, False
        z.system = (z.system + "\n\n" + chat.SHARED_STRANGER_HINT
                  + (" " + chat.SHARED_SHORT_HINT if z.stranger.startswith("too little speech") else "")
                  + (" " + chat.PHONE_PIN_HINT if z.request.scope.get("speech_pin_hint") else "")
                  + (" " + chat.PHONE_CALLBACK_HINT if z.request.scope.get("speech_callback_hint") else "")).strip()
    if not z.own_browser:
        # someone else's voice at this browser: the browser's conversation is not theirs, so it is
        # not sent along (and the browser keeps this turn out of its own history, see "foreign")
        z.messages = [m for m in z.messages[-1:] if m["role"] == "user"]
        if not z.messages:
            raise HTTPException(400, "a question is required")
    # conversation settings: what the request sends, else the profile's, else the admin's defaults
    # (speakers with a device key send nothing and get their profile's voice, speed and length)
    z.pset = profiles.effective(z.who and z.who["id"], z.ccfg)
    if z.stranger and z.sound_of:
        z.own = profiles.settings(z.sound_of["id"])
        z.pset.update({k: z.own[k] for k in ("voice", "speed", "length")
                     if k in z.own and (k != "voice" or profiles.voice_ok(z.sound_of["id"], z.own[k]))})
    # guests change nothing: they get the admin's defaults (the admin's own browser may try speed and length)
    for k in (("voice", "speed", "length") if z.who else ("speed", "length") if admin_cookie_ok(z.request) else ()) \
            if z.own_browser else ():
        # a voice the profile may not speak with (profiles.voice_ok: a designed one) is not taken from the request
        if k in z.body and profiles.SETTINGS[k][1](z.body[k]) and (k != "voice" or profiles.voice_ok(z.who["id"], z.body[k])):
            z.pset[k] = z.body[k]
    z.length = chat.LENGTH_HINT.get(z.pset["length"])
    if z.length:
        z.system = (z.system + "\n\n" + z.length).strip()
    z.style = chat.own_style(z.ccfg, z.who, z.pset, z.own_browser)
    if z.style:
        z.system = (z.system + "\n\n" + chat.STYLE_INTRO + z.style).strip()
    # roles (roles.py): "Sei jetzt der Butler" is carried out by the panel with fixed rules, only for a
    # name the profile saved, only from its own words and voice; the model just says the result
    import roles
    z.roles = roles
    z.role_cmd = None
    if z.roles.on(z.ccfg, z.who, z.pset, z.own_browser) and z.messages[-1]["role"] == "user" and not z.mcp:
        z.role_cmd = z.roles.command(z.messages[-1]["content"], z.roles.parse(z.pset.get("roles")))
        if z.role_cmd:
            z.note = z.role_note = z.roles.carry_out(z.who["id"], z.role_cmd, z.pset) if not z.mcp else "nicht über MCP"
            print("rolle:", z.role_cmd[0], "-", z.role_cmd[1] or "-", "(fixed rule, no tools in this answer)", flush=True)
            z.system = z.per_turn(z.system, "Rolle: " + z.note)
    # the Notaus by a fixed sentence (notaus.phrase): the panel decides from the person's own whole sentence, the
    # model only says the result; never over MCP, never for a stranger's voice at a shared speaker (who is then None)
    if not z.role_cmd and z.who and not z.mcp and z.messages[-1]["role"] == "user":
        import notaus
        z.notaus = notaus
        z.na = z.notaus.phrase(z.messages[-1]["content"])
        if z.na:
            z.note = z.role_note = await z.notaus.by_phrase(z.na, z.who["name"], z.who["id"], z.notaus.phrase_channel(z.body.get("client")))
            z.role_cmd = ("notaus", z.na[0])
            print("notaus: fester Satz", z.na[0], "(fixed rule, no tools in this answer)", flush=True)
            z.system = z.per_turn(z.system, "Notaus: " + z.note + " Sag genau das in einem Satz.")
    # "Spark, Problem melden: …" (meldung.phrase): the panel makes a draft from the person's own words; nothing goes
    # out before the person looked at the preview (Ich → Probleme melden); never over MCP or for a stranger's voice
    if not z.role_cmd and z.who and not z.mcp and z.messages[-1]["role"] == "user":
        import meldung
        z.meldung = meldung
        z.rp = z.meldung.phrase(z.messages[-1]["content"])
        if z.rp:
            z.note = z.role_note = await z.meldung.by_phrase(z.who["id"], z.who["name"], z.rp, z.meldung.phrase_channel(z.body.get("client")))
            z.role_cmd = ("meldung", "")
            print("meldung: fester Satz (fixed rule, no tools in this answer)", flush=True)
            z.system = z.per_turn(z.system, "Problem melden: " + z.note + " Sag genau das in einem Satz.")
    # "Das war falsch" / "Gut so" right after an answer (faelle.phrase): the panel notes it for the last answer of
    # the last 10 minutes; the model only says the fixed sentence. Never over MCP or for a stranger's voice.
    if not z.role_cmd and z.who and not z.mcp and z.messages[-1]["role"] == "user":
        z.verdict = faelle.phrase(z.messages[-1]["content"])
        if z.verdict:
            z.note = z.role_note = await asyncio.to_thread(faelle.by_phrase, z.who["id"], z.verdict)
            z.role_cmd = ("bewertung", z.verdict)
            print("faelle: fester Satz", z.verdict, "(fixed rule, no tools in this answer)", flush=True)
            z.system = z.per_turn(z.system, "Bewertung: " + z.note + " Sag genau das in einem Satz.")
    # "Was schlägt der Einstellungs-Assistent vor?" (berater.phrase): open proposals in fixed words for an admin
    # profile; a "ja" afterwards never takes one (that happens only on Zustand → Verbessern)
    if not z.role_cmd and z.who and not z.mcp and z.messages[-1]["role"] == "user":
        import berater
        z.berater = berater
        if z.berater.takes(z.messages[-1]["content"], z.who["id"]):
            z.note = z.role_note = await asyncio.to_thread(z.berater.by_phrase, z.who["id"], z.messages[-1]["content"])
            z.role_cmd = ("berater", "")
            print("berater: fester Satz (fixed rule, no tools in this answer)", flush=True)
            z.system = z.per_turn(z.system, "Einstellungs-Assistent: " + z.note + " Sag genau das, kurz.")
    z.role = z.roles.prompt(z.pset) if z.roles.on(z.ccfg, z.who, z.pset, z.own_browser) else ""
    if z.role:
        z.system = (z.system + "\n\n" + z.role).strip()
    if z.body.get("client") == "watch":
        z.system = (z.system + "\n\n" + chat.WATCH_HINT).strip()
    if z.body.get("client") == "siri":
        z.system = (z.system + "\n\n" + chat.SIRI_HINT).strip()
    if z.body.get("client") == "android":
        z.system = (z.system + "\n\n" + chat.ANDROID_HINT).strip()
    if z.body.get("client") == "speaker":
        z.system = (z.system + "\n\n" + chat.SPEAKER_HINT).strip()
    if z.body.get("client") == "telefon":
        z.system = (z.system + "\n\n" + chat.PHONE_HINT).strip()
    # a voice recognized at someone else's device gets no personal data at all (it could be a recording
    # of that person): no memory, history, documents, calendar, contacts, lists or reminders
    z.prof = z.who if z.who and z.ccfg.get("memory", True) and z.own_browser and not z.mcp and features.allowed("memory", z.who["id"], z.ccfg) else None
    z.memcheck = None
    if z.prof:  # guests get no memory at all
        z.mem_extra = []
        z.system = (z.system + "\n\n" + chat.memory_hint(z.prof, str(z.messages[-1].get("content") or ""), z.mem_extra)).strip()
        for z.note in z.mem_extra:   # Großes Gedächtnis kürzen: the matching older facts only for this turn
            z.system = z.per_turn(z.system, z.note)
        z.memcheck = chat.gedaechtnis.for_turn(z.prof["id"]) if features.allowed("gedpruefen", z.prof["id"], z.ccfg) else None
    z.past = bool(z.prof and z.ccfg.get("history", True) and features.allowed("history", z.prof["id"], z.ccfg))
    if z.past:
        z.system = (z.system + "\n\n" + chat.HISTORY_HINT).strip()
    # pictures (images.py): only with the admin's and the profile's switches, from its own login, app or
    # Telegram. The model sees them in this turn without any tools (no smart home either), and the
    # answer counts as outside text, so the next turn is locked as well.
    z.pics = images.for_turn(z.request, z.body, z.who if z.own_browser else None) if z.messages[-1]["role"] == "user" and not z.mcp else []
    if z.pics:
        z.carry = z.carry or "outside"
        z.system = z.per_turn(z.system, images.hint(len(z.pics)))
        print("chat:", len(z.pics), "picture(s) attached, no tools in this answer, locked like outside text", flush=True)
    # Home Assistant only for the profile's own login or device key: a voice recognized at someone
    # else's device does not switch that profile's home
    z.ha = homeassistant.get(z.who["id"]) if z.who and z.own_browser and z.ccfg.get("homeassistant", False) and not z.pics and not z.mcp \
        and features.allowed("ha", z.who["id"], z.ccfg) else None
    # over Telegram the profile decides: personal data only with tg_private, switching only with tg_ha
    # and a code word (the messages pass Telegram's servers)
    z.tg = z.body.get("client") == "telegram"
    z.tset = profiles.settings(z.who["id"]) if z.tg and z.who else {}
    z.private_ok = (not z.tg or bool(z.tset.get("tg_private"))) and z.own_browser
    # Mappen (mappen.py): the Mappe the person chose for this conversation (body "mappe", an own id, checked there);
    # its entries by the fixed levels go as data and lock this answer like any outside text
    z.mp = None
    if z.body.get("mappe") and z.who and z.own_browser and z.private_ok and not z.mcp and not z.pics \
            and z.messages[-1]["role"] == "user":
        import mappen
        z.mappen = mappen
        z.mp = await asyncio.to_thread(z.mappen.for_turn, z.who, str(z.body.get("mappe"))[:20], z.messages[-1]["content"])
        if z.mp:
            z.carry = z.carry or "outside"
            z.system = z.per_turn(z.system, z.mp["text"])
    if z.tg and z.ha and not (z.tset.get("tg_ha") and homeassistant.needs_code(z.ha)):
        z.ha = None
    # from the iPhone app the smart home switches only when the profile allowed it there (app_ha); the
    # key decides, not what the request says it is
    z.app_key = profiles.key_scope(z.request) == "app"
    # CarPlay: what the request says only makes it stricter (shorter answers, no smart home without
    # the profile's own car switch); it never unlocks anything
    z.car = bool(z.app_key and z.body.get("car") is True)
    if quiet(z.request, z.body, z.pset, z.car):
        z.body["speak"] = False
        print("chat: Antworten vorlesen aus, nur Text", flush=True)
    elif z.body.get("speak") is not False and wartung.paused("tts"):   # Wartungspause of the speech output: text only
        z.body["speak"] = False
        print("chat: wartungspause sprachausgabe, nur Text", flush=True)
    z.app_blocked = bool(z.ha and z.who and z.app_key and (not profiles.settings(z.who["id"]).get("app_ha")
                                                   or z.car and not profiles.settings(z.who["id"]).get("app_car_ha")))
    # actions on the iPhone itself: only from the app's own key, only when the profile allowed them
    z.phone_act = bool(z.app_key and z.who and z.own_browser and profiles.settings(z.who["id"]).get("app_act"))
    if z.app_key:
        z.system = (z.system + "\n\n" + chat.IPHONE_HINT + (" " + chat.IPHONE_ACT_HINT if z.phone_act else "")).strip()
        if z.car:
            z.system = (z.system + "\n\n" + chat.CAR_HINT).strip()
    if z.app_blocked:
        z.ha = None
    if z.tg:
        z.system = (z.system + "\n\n" + chat.TELEGRAM_HINT).strip()
    # the panel's own chat (browser, phone view, Android app) and the Begleiter: Markdown is shown formatted,
    # never spoken
    if z.body.get("client") in (None, "", "desk", "tui") and not z.app_key and not z.mcp:
        z.system = (z.system + "\n\n" + chat.WEB_HINT + " " + (
            chat.WEB_TEXT_HINT if z.body.get("speak") is False and z.body.get("client") != "desk"   # the Begleiter may read aloud
            else chat.WEB_SPOKEN_HINT)).strip()
    if z.ccfg.get("homeassistant", False):  # why the smart home tools are (not) offered, for the journal
        print("homeassistant: turn for", profiles.log_name(z.who), "- tools",
              "offered" if z.ha else "NOT offered: " + (
                  "no profile signed in" if not z.who else "voice of another profile" if not z.own_browser
                  else "a picture is attached (no tools in this answer)" if z.pics
                  else "not for this profile (Personen und Geräte → Gesperrte Funktionen)" if not features.allowed("ha", z.who["id"], z.ccfg)
                  else "not allowed in the car (Ich → iPhone-App)" if z.app_blocked and z.car
                  else "not allowed from the iPhone app (Ich → iPhone-App)" if z.app_blocked
                  else "token unreadable (stored with another key), connect again" if homeassistant._raw(z.who["id"])
                  else "this profile has not connected Home Assistant"), flush=True)
    if z.ha:
        z.system = (z.system + "\n\n" + chat.HA_HINT).strip()
    # code word for changes: only the user's own latest message counts, checked here, never by the
    # model; the model and everything after it see "[Codewort]" instead of the word
    z.ha_code = bool(z.ha and homeassistant.needs_code(z.ha))
    z.ha_code_ok = z.ha_code and z.messages[-1]["role"] == "user" and homeassistant.code_given(z.ha, z.messages[-1]["content"])
    if z.ha_code:
        z.system = (z.system + "\n\n" + chat.HA_CODE_HINT).strip()
        z.messages = [dict(m, content=homeassistant.redact(z.ha, m["content"])) if m["role"] == "user" else m
                    for m in z.messages]
    if not z.own_browser and z.device_owner:
        # a voice taken for someone else at this device may still have been the owner saying their
        # code word: it never reaches the model or the other profile's log either
        z.oha = homeassistant.get(z.device_owner["id"])
        if z.oha and homeassistant.needs_code(z.oha):
            z.messages = [dict(m, content=homeassistant.redact(z.oha, m["content"])) if m["role"] == "user" else m
                        for m in z.messages]
    # A plain switching command is carried out by the panel itself, not left to the model: the model
    # only puts the checked result into words. Without the code word the command waits (two minutes)
    # and runs as soon as the next message brings it.
    z.ha_direct = None
    # "Raummodus im Wohnzimmer an" is about the profile's own devices (roomfar.py, fixed rules), never
    # the smart home: no switching, no code word and no smart home tools in this turn
    import roomfar
    z.roomfar = roomfar
    z.room_far = z.messages[-1]["role"] == "user" and z.roomfar.asks(z.messages[-1]["content"])
    # Rückfrage und Merken (klaeren.py): the answer to the panel's own question of this conversation,
    # read by fixed rules before anything else; it carries the code word of the command it answers
    import klaeren
    z.klaeren = klaeren
    z.src = z.src0
    z.kl_on = bool(z.who and z.own_browser and z.private_ok and not z.mcp and features.allowed("klaeren", z.who["id"]))
    z.kl = z.klaeren.answer(z.who["id"], z.src, z.messages[-1]["content"], z.own_browser) \
        if z.kl_on and z.messages[-1]["role"] == "user" and not z.room_far and not z.weg else None
    z.kl_took = bool(z.kl)
    z.ha_choice = z.ha_list = None
    z.kl_note, z.kl_events = [], []
    if z.kl and z.kl["kind"] == "remember":
        if z.kl["yes"]:
            z.row = z.klaeren.remember(z.who["id"], z.kl["area"], z.kl["words"], z.kl["target"])
            z.kl_note.append({"name": "Zuordnung (Panel)", "args": "", "result": "gemerkt"})
            z.system = z.per_turn(z.system, "Zuordnung: Gemerkt ist jetzt, dass „" + z.klaeren._shown(z.kl["said"]) + "“ "
                              + z.row["name"] + " ist. Sag dem Nutzer genau das in einem kurzen Satz, ohne Werkzeug.")
        else:
            z.system = z.per_turn(z.system, "Zuordnung: Nichts gemerkt, weil der Nutzer es nicht wollte. Bestätige das "
                              "in drei Wörtern, ohne Werkzeug.")
    elif z.kl and z.kl["kind"] == "none":
        z.system = z.per_turn(z.system, "Rückfrage: Der Nutzer meinte keines der genannten Geräte. Nichts wurde geschaltet. "
                          "Sag kurz, dass du nichts geschaltet hast, ohne Werkzeug.")
    elif z.kl and z.kl["area"] == "ha" and z.ha and (z.kl["code_ok"] or not homeassistant.needs_code(z.ha)):
        if z.kl["kind"] == "choice":
            z.ha_choice, z.ha_direct = z.kl, z.kl["said"] or "(Auswahl)"
        else:
            z.ha_list, z.ha_direct = z.kl, z.kl["said"] or "(Liste)"
    elif z.kl and z.kl["area"] in z.klaeren.TOOLS and z.kl["kind"] == "list":   # a tool's own candidates were all there is
        z.system = z.per_turn(z.system, "Rückfrage: Der Nutzer meinte keines der genannten. Nichts wurde ausgeführt. Bitte ihn "
                          "kurz, es genauer zu sagen, ohne Werkzeug.")
    elif z.kl and z.kl["area"] in z.klaeren.TOOLS:   # the choice runs the tool it answers, below (direct)
        z.ha_code_ok = z.ha_code_ok or bool(z.kl.get("code_ok"))   # it carries the code word of the request it answers
    elif z.kl:   # an area this turn cannot act in (Home Assistant off meanwhile): nothing happens
        z.system = z.per_turn(z.system, "Rückfrage: Die Auswahl kann gerade nicht ausgeführt werden. Sag das kurz, ohne Werkzeug.")
    # the way chosen after the panel asked (klaeren weg): the sentence switches directly only when that way is the home
    z.weg_other = bool(z.weg and z.weg["group"] != "smarthome")
    if z.ha and z.messages[-1]["role"] == "user" and not z.room_far and not z.kl_took and not z.weg_other:
        z.latest = z.messages[-1]["content"]
        # a command waiting for the code word belongs to the device and conversation it was said at (chat.ha_take,
        # profiles.quelle): the code word from another device of the profile neither runs it nor clears it
        z.pend = chat.ha_take(z.who["id"], z.src)
        if homeassistant.is_command(z.latest) and await homeassistant.mentions_device(z.ha, z.latest):
            z.ha_direct = homeassistant.clean_command(z.latest)
        elif homeassistant._intent(z.latest):  # sounds like switching but is not taken as a command: say why
            print(f"homeassistant: not taken as a command | {len(str(z.latest).split())} words"
                  + (" | verneint" if homeassistant._negated(z.latest) else ""), flush=True)
        elif z.ha_code_ok and z.pend:
            z.ha_direct = z.pend
        if z.ha_direct and z.ha_code and not z.ha_code_ok:
            chat.ha_wait(z.who["id"], z.src, z.ha_direct)
            print("homeassistant: command waits for the code word", flush=True)
            z.system = z.per_turn(z.system, "Der Nutzer will etwas im Smart Home schalten, aber das Codewort fehlt. "
                              "Frag in einem kurzen Satz nach dem Codewort; sag nicht, dass etwas geschaltet wurde.")
            z.ha_direct = None
            z.ha_wait = True
        else:
            z.ha_wait = False
    else:
        z.ha_wait = False
    # A question that names a device or room is answered from states the panel reads itself, so the
    # value never comes from the model's memory of earlier turns or from a guess.
    z.ha_read = None
    if z.ha and not z.ha_direct and not z.ha_wait and z.messages[-1]["role"] == "user" and not z.room_far and not z.kl_took \
            and not homeassistant._intent(z.messages[-1]["content"]):
        try:
            z.ha_read = await homeassistant.lookup(z.ha, z.messages[-1]["content"])
        except (httpx.HTTPError, ValueError) as e:
            print("homeassistant: lookup failed:", type(e).__name__, flush=True)


async def _rechte(z):
    """Stufe 4 Rechte und Sperren: Dokumente, Erinnerungen, E-Mail, Kalender, Notaus."""
    # own documents plus the ones other profiles offer to everyone; neither for guests or a voice the
    # shared speaker does not recognize (private_ok)
    z.docs_ok = bool(z.who and z.private_ok and z.ccfg.get("documents", True) and (not z.mcp or "document_search" in z.mcp["tools"])
                   and features.allowed("documents", z.who["id"], z.ccfg))
    # beside the event loop: with many documents the lists cost a noticeable moment (code check 19.10. B1)
    z.docs = await asyncio.to_thread(documents.list_docs, z.who["id"], True) if z.docs_ok else []
    z.shared_docs = await asyncio.to_thread(wissen.shared_list, z.who["id"]) if z.docs_ok else []
    if z.docs or z.shared_docs:
        z.system = z.per_turn(z.system, await asyncio.to_thread(chat.docs_hint, z.who, z.docs, z.shared_docs,
                                                          str(z.messages[-1].get("content") or ""), wissen.on(z.who["id"], "brief")))
        import wissensbuch
        z.wissensbuch = wissensbuch
        z.book = z.wissensbuch.hint(z.who["id"], str(z.messages[-1].get("content") or "")) if z.docs else ""
        if z.book:
            z.system = z.per_turn(z.system, z.book)
    z.docs = z.docs + z.shared_docs
    z.timers = bool(z.ccfg.get("reminders", True)) and not z.guest and bool(z.who) and features.allowed("reminders", z.who["id"], z.ccfg)
    if z.timers:
        z.system = (z.system + "\n\n" + chat.REMINDER_HINT).strip()
    # e-mail like Home Assistant: only for the profile's own login or device key
    z.mailbox = bool(z.who and z.own_browser and z.private_ok and not z.mcp and z.ccfg.get("mail", False) and features.allowed("mail", z.who["id"], z.ccfg)
                   and mail.get(z.who["id"])["accounts"])
    if z.mailbox:
        z.system = (z.system + "\n\n" + chat.MAIL_HINT).strip()
    # tidying and drafts (tidy.py): only for mailboxes the profile switched on; changes after a yes
    z.tidy_st = tidy.state(z.who["id"]) if z.mailbox and features.allowed("tidy", z.who["id"], z.ccfg) else None
    z.tidy_on = bool(z.tidy_st and any(tidy.acct_state(z.tidy_st, x["id"])["mode"] != "off"
                                   for x in mail.get(z.who["id"])["accounts"]))
    z.drafts_on = bool(z.tidy_st and any(tidy.acct_state(z.tidy_st, x["id"]).get("drafts")
                                     for x in mail.get(z.who["id"])["accounts"]))
    if z.tidy_on:
        z.system = (z.system + "\n\n" + chat.TIDY_HINT).strip()
    if z.drafts_on:
        z.system = (z.system + "\n\n" + chat.DRAFT_HINT).strip()
    z.briefing = bool(z.ccfg.get("calendar", True)) and not z.guest and bool(z.who) and features.allowed("calendar", z.who["id"], z.ccfg)
    z.cal_note = list(z.kl_note)
    if z.role_cmd:   # shown in the tool log like a tool the panel ran itself
        z.cal_note.append({"name": {"notaus": "Notaus (Panel)", "meldung": "Meldung (Panel)", "bewertung": "Bewertung (Panel)",
                                 "berater": "Einstellungs-Assistent (Panel)"}.get(z.role_cmd[0], "Rolle (Panel)"), "args": z.role_cmd[1], "result": z.role_note})
    z.cal = calendars.get(z.who["id"]) if z.who and z.briefing and z.private_ok and (not z.mcp or "calendar_events" in z.mcp["tools"]) \
        else {"calendars": [], "topics": []}
    # Kalender teilen: the levels of the calendars others share with this profile (read with calendar_events,
    # "add" also for a named calendar_add); the briefing stays with the own calendars
    z.cal["shared"] = [lvl for _, _, _, lvl in calendars.shared_to(z.who["id"])] if z.who and z.briefing and z.private_ok and not z.mcp else []
    # new appointments: only the profile's own login or device key, and only after a yes (see calendars.py)
    # Notaus stage 2 (notaus.py): no "Ja" carries anything out, every proposal waiting in this conversation is
    # dropped, and below no tool that changes something is offered (stage 1: none that goes to the internet)
    import notaus
    z.notaus = notaus
    z.held = z.notaus.level()
    # Mein Notaus (notaus.py): this profile's own, like stage 2 for its actions only (reading goes on)
    z.mine = bool(z.who and z.notaus.own(z.who["id"]))
    if z.who:
        z.notaus.acting(z.who["id"])
    z.act_held = z.held >= 2 or z.mine
    if z.act_held and z.who:
        for mod in waiting_mods():
            if mod.pending(z.who["id"]):
                mod.drop_pending(z.who["id"])
        import vorgaenge
        z.vorgaenge = vorgaenge
        z.vorgaenge.sweep(z.who["id"])
        print(f"notaus: {'Stufe ' + str(z.held) if z.held >= 2 else 'Mein Notaus'} - keine Aktion, kein Ja, nur lesen", flush=True)
    z.cal_write = bool((z.cal["calendars"] or "add" in z.cal["shared"]) and z.own_browser and not z.mcp and not z.act_held)
    z.prop = None
    if z.cal["shared"]:
        z.system = (z.system + "\n\n" + chat.CALENDAR_SHARED_HINT
                  + (" " + chat.CALENDAR_SHARED_ADD_HINT if "add" in z.cal["shared"] and z.cal_write else "")).strip()
    if z.cal_write:
        z.system = (z.system + "\n\n" + chat.CALENDAR_ADD_HINT).strip()
        z.prop = calendars.pending(z.who["id"]) if not z.kl_took else None
        if z.prop and z.prop.get("src", z.src) != z.src:
            z.prop = None  # proposed on another device or in another conversation: the yes is not for it
        if z.prop:
            z.latest = z.messages[-1]["content"] if z.messages[-1]["role"] == "user" else ""
            calendars.drop_pending(z.who["id"])
            if z.prop.get("change") and calendars.confirms(z.latest):
                # calendar_change: move or delete one appointment, the old one kept for undo (calendars.carry)
                z.ok, z.res = await calendars.carry(z.who["id"], z.prop)
                z.note = z.res + " (vom Kalender-Server bestätigt)" if z.ok else \
                    f"NICHT geändert, der Kalender lehnte ab: {z.res}. Vorschlag war {calendars.describe_change(z.prop)}"
                z.cal_note[:] = [{"name": "calendar_change (bestätigt)", "args": calendars.describe_change(z.prop), "result": z.note}]
                z.system = z.per_turn(z.system, "Kalender: " + z.note + " Sag dem Nutzer genau das in einem Satz.")
            elif z.prop.get("change"):
                z.system = z.per_turn(z.system, "Kalender: Der Vorschlag, " + calendars.describe_change(z.prop)
                                  + ", wurde NICHT ausgeführt, weil der Nutzer nicht zugestimmt hat.")
            elif calendars.confirms(z.latest):
                z.ok, z.res = await calendars.carry(z.who["id"], z.prop)
                z.note = f"Saved in calendar '{z.res}' (confirmed by the calendar server): {calendars.describe(z.prop)}" if z.ok else \
                    f"NOT saved, the calendar refused it: {z.res}. Proposal was {calendars.describe(z.prop)}"
                z.cal_note[:] = [{"name": "calendar_add (bestätigt)", "args": calendars.describe(z.prop), "result": z.note}]
                z.system = z.per_turn(z.system, "Kalender: " + z.note + " Sag dem Nutzer genau das in einem Satz.")
            else:
                z.system = z.per_turn(z.system, "Kalender: Der vorgeschlagene Termin " + calendars.describe(z.prop)
                                  + " wurde NICHT eingetragen, weil der Nutzer nicht zugestimmt hat.")


async def _wartendes_ja(z):
    """Stufe 5 Wartendes Ja: Vorschläge, die auf ein Ja warten (Kalender, Mail, Rufen, Gedächtnis, reMarkable)."""
    # an answer to something the assistant said by itself (yes to its offer, "nicht jetzt", ...):
    # the panel does what it means and the model only says the checked result (see proactive.py)
    z.mprop = None
    if (z.tidy_on or z.drafts_on) and not z.prop and not z.mcp and not z.act_held and not z.kl_took:
        z.mprop = tidy.pending(z.who["id"])
        if z.mprop and z.mprop.get("src", z.src) != z.src:
            z.mprop = None
        if z.mprop:
            z.latest = z.messages[-1]["content"] if z.messages[-1]["role"] == "user" else ""
            tidy.drop_pending(z.who["id"])
            z.what = tidy.describe(z.mprop, z.tidy_st)
            if tidy.confirms(z.latest):
                try:
                    z.note = await asyncio.to_thread(tidy.carry_out, z.who["id"], z.mprop)
                except Exception as e:
                    z.note = f"NICHT ausgeführt, Fehler: {e}"
                z.cal_note.append({"name": "mail (bestätigt)", "args": z.what, "result": z.note})
                z.system = z.per_turn(z.system, "Postfach: " + z.note + " Sag dem Nutzer genau das in einem Satz.")
            else:
                z.system = z.per_turn(z.system, "Postfach: Der Vorschlag „" + z.what + "“ wurde NICHT ausgeführt, weil der "
                                  "Nutzer nicht zugestimmt hat.")
    # ticking off a list entry ... (extras.py): the module waiting for a yes in this conversation
    z.xprop = None
    if z.who and z.messages[-1]["role"] == "user" and not z.prop and not z.mprop and not z.mcp and not z.act_held and not z.kl_took:
        import android as android_app   # its user agent: the Android app's page (rufen.py dials a number only there)
        z.android_app = android_app
        z.xprop = await extras.answer({"who": z.who, "own": z.own_browser, "src": z.src, "client": z.body.get("client"), "private": z.private_ok,
                                     "app": z.app_key, "device": (profiles.device_name(z.request) or "")[:40],
                                     "android": bool(z.android_app.UA.search(z.request.headers.get("user-agent", ""))),
                                     "ha": z.ha, "ha_code": z.ha_code, "ha_code_ok": z.ha_code_ok}, z.messages[-1]["content"])
        if z.xprop:
            if z.xprop.get("event"):
                z.kl_events.append(z.xprop["event"])
            if z.xprop.get("outside"):
                z.carry = z.carry or "outside"
            z.cal_note.append(z.xprop["call"])
            z.system = z.per_turn(z.system, z.xprop["system"])
    # Bilder ändern (bilder.py): a photo of this turn with a wish to change it, or a short follow-up right after a
    # change, starts the change by a fixed rule; the model only says so (a turn with a photo has no tools anyway)
    if z.who and z.messages[-1]["role"] == "user" and not z.prop and not z.mprop and not z.xprop and not z.mcp and not z.act_held \
            and not z.kl_took:
        import bilder
        z.bilder = bilder
        z.bprop = await z.bilder.from_turn({"who": z.who, "own": z.own_browser, "client": z.body.get("client"),
                                        "private": z.private_ok}, z.messages[-1]["content"], z.pics)
        if z.bprop:
            if z.bprop.get("event"):
                z.kl_events.append(z.bprop["event"])
            z.cal_note.append(z.bprop["call"])
            z.system = z.per_turn(z.system, z.bprop["system"])
    z.pro = None
    if z.who and z.own_browser and z.messages[-1]["role"] == "user" and not z.prop and not z.mprop and not z.xprop and not z.mcp \
            and not z.act_held and not z.kl_took:  # one yes confirms one thing
        z.pro = proactive.reply(z.who["id"], z.messages[-1]["content"], z.said_before)
        if z.pro:
            z.cal_note.append(z.pro["call"])
            z.system = z.per_turn(z.system, z.pro["system"])
    # a note the Spark said by itself is in this conversation: what it rested on, so the model does not make up a
    # source when the person asks about it (proactive.basis_note, V01.0.385)
    if z.who and z.messages[-1]["role"] == "user" and not z.mcp:
        z.basis = proactive.basis_note(z.who["id"], z.said_all)
        if z.basis:
            z.cal_note.append(z.basis[1])
            z.system = z.per_turn(z.system, z.basis[0])
    # learning from corrections (fixes.py): a yes saves the proposed sentence, a correction leads to one
    z.fix_ok = bool(z.who and z.own_browser and z.private_ok and z.ccfg.get("memory", True) and features.allowed("fixes", z.who["id"], z.ccfg)
                  and z.messages[-1]["role"] == "user" and not z.mcp and not z.act_held)
    z.fix_fix, z.fix_prev, z.fix_took = False, "", False
    if z.fix_ok and not z.prop and not z.mprop and not z.xprop and not z.pro and not z.kl_took:
        z.fp = fixes.pending(z.who["id"])
        if z.fp and z.fp.get("src", z.src) == z.src:
            z.fix_took = True
            fixes.drop_pending(z.who["id"])
            if fixes.confirms(z.messages[-1]["content"]):
                z.saved = profiles.remember(z.who["id"], z.fp["text"], src="fix", convo=z.body.get("convo"),
                                           version="fix")
                z.full = z.saved is profiles.FULL   # only protected facts left (profiles._cap): refused, nothing lost
                z.cal_note.append({"name": "Korrektur gemerkt", "args": "",
                                 "result": "Gedächtnis voll" if z.full else z.saved or "nicht gespeichert"})
                z.system = z.per_turn(z.system, "Gedächtnis: NICHT gemerkt, das Gedächtnis ist voll. Sag dem Nutzer in einem "
                                  "kurzen Satz, dass er unter Ich → Gedächtnis aufräumen kann." if z.full else
                                  "Gedächtnis: Gemerkt wurde „" + (z.saved or "") + "“. Sag dem Nutzer genau das "
                                  "in einem kurzen Satz.")
            else:
                z.system = z.per_turn(z.system, "Gedächtnis: Der Vorschlag „" + z.fp["text"] + "“ wurde NICHT gemerkt, weil der "
                                  "Nutzer nicht zugestimmt hat.")
        elif fixes.is_correction(z.messages[-1]["content"], z.said_before):
            z.fix_fix = True
            z.fix_prev = next((m["content"] for m in reversed(z.messages[:-2]) if m["role"] == "user"), "")[:200]
    # Nachfrage zum Gedächtnis (gedaechtnis.py): the answer to the panel's "Stimmt das noch?", and whether this
    # answer may ask one (same conditions as learning from corrections, its own switches)
    import gedaechtnis
    z.gedaechtnis = gedaechtnis
    z.mem_ask_ok = bool(z.who and z.own_browser and z.private_ok and z.ccfg.get("memory", True) and z.gedaechtnis.ask_on(z.who["id"], z.ccfg)
                      and z.messages[-1]["role"] == "user" and not z.mcp and not z.act_held and not z.held)
    z.mem_ask_ok = z.mem_ask_ok and not (z.prop or z.mprop or z.xprop or z.pro or fixes.pending(z.who["id"]))
    z.mq = z.gedaechtnis.pending(z.who["id"]) if z.who and z.own_browser and z.messages[-1]["role"] == "user" and not z.mcp else None
    if z.mq and z.mq.get("src", z.src) == z.src and z.mq.get("convo", "") in ("", z.body.get("convo") or ""):
        z.gedaechtnis.drop_pending(z.who["id"])
        z.mem_ask_ok = False
        z.mf = next((f for f in profiles.memory(z.who["id"]) if f["id"] == z.mq.get("fact")), None)
        z.kind = z.gedaechtnis.reply_kind(z.messages[-1]["content"]) if z.mf else ""
        if z.kind == "yes":
            z.gedaechtnis.confirm(z.who["id"], z.mf["id"])
            z.system = z.per_turn(z.system, "Gedächtnis: Der Eintrag „" + z.mf["text"] + "“ ist jetzt bestätigt. Sag das in einem "
                              "kurzen Satz.")
        elif z.kind == "forget" and not z.act_held:
            profiles.forget(z.who["id"], fact_id=z.mf["id"])
            z.system = z.per_turn(z.system, "Gedächtnis: Der Eintrag „" + z.mf["text"] + "“ wurde vergessen. Sag das in einem "
                              "kurzen Satz.")
        elif z.kind == "no":
            z.system = z.per_turn(z.system, "Gedächtnis: Der Nutzer sagt, „" + z.mf["text"] + "“ stimmt nicht mehr. Frag kurz, "
                              "was jetzt stimmt, oder ob du es vergessen sollst. Geändert wird nichts.")
        elif z.kind == "fix" and z.fix_ok:
            z.fix_fix, z.fix_prev = True, z.mf["text"]   # fixes.py words it, a yes keeps it as a new version of the fact
        if z.kind:
            z.cal_note.append({"name": "Nachfrage (Panel)", "args": "", "result": {"yes": "bestätigt", "forget": "vergessen",
                             "no": "stimmt nicht mehr", "fix": "Korrektur"}[z.kind]})
            print(f"gedaechtnis: nachfrage beantwortet {profiles.log_name(z.who)} | antwort={z.kind}", flush=True)
    # "Ja" to „Soll ich das aufs reMarkable legen?“ (remarkable.propose): the panel puts the kept answer there and the
    # model only says the result; anything else drops the proposal (the loop below)
    import remarkable
    z.remarkable = remarkable
    z.rprop = z.remarkable.pending(z.who["id"]) if z.who and z.own_browser and not z.mcp and z.messages[-1]["role"] == "user" else None
    if z.rprop and z.rprop.get("src", z.src) == z.src:
        z.remarkable.drop_pending(z.who["id"])
        if calendars.confirms(z.messages[-1]["content"]) and not z.act_held and z.remarkable.answer_ok(z.who, z.own_browser, z.private_ok):
            z.ok, z.note = await z.remarkable.send_answer(z.who["id"], "", z.rprop.get("text", ""), z.rprop.get("title", ""))
            print("remarkable: answer", "sent" if z.ok else "not sent", "| after yes", flush=True)
            z.cal_note.append({"name": "remarkable (bestätigt)", "args": z.rprop.get("title", ""), "result": z.note})
            z.system = z.per_turn(z.system, "reMarkable: " + z.note + " Sag dem Nutzer genau das in einem Satz.")
        else:
            print("remarkable: answer not sent | no yes", flush=True)
    if z.who and z.own_browser and z.messages[-1]["role"] == "user" and not z.mcp:
        # one answer settles every proposal waiting in this conversation: a later "ja" meant for
        # something else never carries out an old one
        import agent
        z.agent = agent
        import messages as inbox   # (messages is the conversation here)
        z.inbox = inbox
        import tasks
        z.tasks = tasks
        import rufen
        z.rufen = rufen
        import senden
        z.senden = senden
        for mod in (calendars, tidy, z.tasks, fixes, z.agent, z.inbox, z.roomfar, hamelden, meinmcp, z.gedaechtnis, aendern, nasablage, z.rufen,
                    z.remarkable, z.senden):
            if z.xprop and z.xprop.get("proposed") == mod.__name__:
                continue   # the panel made this proposal from this very message (agent: „Sag mir Bescheid, wenn …“)
            z.p = mod.pending(z.who["id"])
            if z.p and z.p.get("src", z.src) == z.src:
                mod.drop_pending(z.who["id"])
        import vorgaenge   # the cards „Wartet auf dein Ja“ of the proposals answered now (Alles Offene, Stufe 2)
        z.vorgaenge = vorgaenge
        z.vorgaenge.sweep(z.who["id"])
        # a plain yes here while the proposal it may mean waits on another device or in another conversation, or was
        # replaced from there (one per profile and module): nothing is done, a fixed sentence says so (review A-H3)
        if not (z.prop or z.mprop or z.xprop or z.pro or z.kl_took or z.weg or z.fix_took) and calendars.confirms(z.messages[-1]["content"]) \
                and not (z.rprop and z.rprop.get("src", z.src) == z.src) and not (z.mq and z.mq.get("src", z.src) == z.src):
            z.gone = profiles.pending_replaced(z.who["id"], z.src)
            if z.gone or any((m.pending(z.who["id"]) or {}).get("src", z.src) != z.src for m in waiting_mods()):
                z.cal_note.append({"name": "Ja (Panel)", "args": "", "result": "nicht ausgeführt"})
                z.system = z.per_turn(z.system, YES_ELSEWHERE)
                print(f"chat: ja ohne vorschlag hier | {'ersetzt' if z.gone else 'anderes geraet'}", flush=True)


async def _werkzeuge(z):
    """Stufe 6 Werkzeuge: was angeboten wird, was die Weiche davon lässt, lokales Wissen, Sperren nach fremdem Text."""
    if z.briefing:
        z.system = z.per_turn(z.system, chat.BRIEFING_HINT + (" " + chat.CALENDAR_HINT if z.cal["calendars"] else "")
                          + (" Nenne im Briefing nach den Erinnerungen kurz die ungelesenen Mails (Absender und Thema)."
                             if z.mailbox else ""))
    # a voice recognized at someone else's device may read its own things but changes nothing that
    # lasts: no memory changes, no cancelled reminders (it could be a recording of that person)
    z.tools = ([chat.SEARCH_TOOL] if z.search else []) + (chat.MEMORY_TOOLS if z.prof and z.own_browser else []) + ([chat.HISTORY_TOOL] if z.past else []) \
        + ([chat.DOC_TOOL, chat.DOC_LIST_TOOL] if z.docs else []) + (([chat.HA_STATES_TOOL, chat.HA_HISTORY_TOOL] if z.ha_direct or z.ha_wait
             else [chat.HA_TOOL, chat.HA_STATES_TOOL, chat.HA_ACTION_TOOL, chat.HA_HISTORY_TOOL, chat.HA_TODO_TOOL]) if z.ha else []) \
        + ([chat.CAMERA_TOOL] if z.ha and hamelden.camera_on(z.who["id"]) else []) \
        + (chat.REMINDER_TOOLS if z.timers and z.own_browser else []) + ([chat.BRIEFING_TOOL] if z.briefing else []) \
        + ([chat.CALENDAR_TOOL] if z.cal["calendars"] or z.cal["shared"] else []) + ([chat.CALENDAR_ADD_TOOL, chat.CALENDAR_CHANGE_TOOL] if z.cal_write else []) \
        + (chat.MAIL_TOOLS if z.mailbox else []) + (chat.TIDY_TOOLS if z.tidy_on else []) + ([chat.DRAFT_TOOL] if z.drafts_on else []) \
        + ([chat.IPHONE_TOOL] if z.phone_act else [])
    # weather, contacts, parcels ... (extras.py): each offers its tools only when the profile switched it on
    z.ex = extras.offer({"who": z.who, "own": z.own_browser, "tz": z.body.get("tz"), "private": z.private_ok,
                       "client": z.body.get("client"), "src": z.src,
                       "before": z.messages[-2]["content"] if len(z.messages) > 1 and z.messages[-2]["role"] == "assistant"
                       and isinstance(z.messages[-2].get("content"), str) else "",
                       # the person's own two messages before this one (a follow-up like "Nochmal", begleiter.offer)
                       "asked": [m["content"] for m in z.messages[:-1] if m["role"] == "user"][-2:],
                       "text": z.messages[-1]["content"] if z.messages[-1]["role"] == "user" else ""})
    z.tools += z.ex["tools"]
    if z.messages[-1]["role"] == "user" and isinstance(z.messages[-1].get("content"), str):
        z.kept = chat.offer_memory(z.tools, z.messages[-1]["content"])
        if len(z.kept) < len(z.tools):
            print("chat: memory_save not offered - the message only asks", flush=True)
        z.tools = z.kept
    if z.held or z.mine:
        z.gone_n = len(z.tools)
        z.tools = [t for t in z.tools if t["function"]["name"] not in z.notaus.locked_tools(z.held, z.ex["changes"], z.mine)]
        z.system = z.per_turn(z.system, notaus_note(z.held, z.mine))
        print(f"notaus: Stufe {z.held}{' + Mein Notaus' if z.mine else ''} - {z.gone_n - len(z.tools)} Werkzeuge nicht angeboten", flush=True)
    if z.mcp:   # only what the connection was given (mcpserver.ASK_TOOLS), never more than the rights above left
        z.tools = [t for t in z.tools if t["function"]["name"] in z.mcp["tools"]]
    if z.pics or z.role_cmd:
        z.tools = []
    if z.xprop and z.xprop.get("quiet") and z.tools:   # the panel answered by a fixed rule (rufen.py): the model only says it
        print(f"chat: fester Weg {z.xprop.get('proposed', '')} - {len(z.tools)} Werkzeuge nicht angeboten", flush=True)
        z.tools = []
    if z.guest and z.tools:   # the fixed rule above, once more as a net: whatever offered something, a guest gets no tool
        print(f"chat: guest - {len(z.tools)} tools withheld, only questions and answers", flush=True)
        z.tools = []
    if z.room_far:
        if not z.xprop:   # a guest or a voice of another profile: the fixed answer, nothing else
            z.note = z.roomfar.why_not({"who": z.who if z.own_browser else None, "own": z.own_browser, "client": z.body.get("client")})
            z.system = z.per_turn(z.system, "Raum-Modus: " + (z.note or "Das geht hier nicht.") + " Sag dem Nutzer genau das, kurz.")
        z.tools = []
        print("room: message about another device's room mode - fixed rules, no tools in this answer", flush=True)
    # „Beschwerde erkennen“ (taten.py, systemone.py): "geht immer noch nicht" right after a deed of this profile.
    # The fixed list first, qwen38's probability only when the list finds nothing; then the model is told to look
    # first, and the tools that change things of that kind are not offered (unless the message asks again)
    z.last_acts = taten.last(z.who["id"]) if z.who and z.own_browser and not z.mcp and z.messages[-1]["role"] == "user" \
        and isinstance(z.messages[-1].get("content"), str) and features.allowed("einordnungklage", z.who["id"], z.ccfg) else []
    if z.last_acts and z.tools:
        z.said = z.messages[-1]["content"]
        z.klage, z.via = taten.complaint(z.said), "Liste"
        if not z.klage and len(z.said) <= 300:
            import systemone
            z.systemone = systemone
            z.p_klage = await z.systemone.complaint(z.ccfg, z.said, taten.WHAT.get(z.last_acts[-1]["art"], taten.WHAT[""])[0])
            z.klage, z.via = z.p_klage is not None and z.p_klage >= z.systemone.KLAGE_MIN, "Einordnung"
        if z.klage:
            z.gone = taten.locked(z.last_acts, z.said)
            z.tools = [t for t in z.tools if t["function"]["name"] not in z.gone]
            z.system = z.per_turn(z.system, taten.complaint_note(z.last_acts, chat.guess_language(z.said) == "English"))
            z.cal_note.append({"name": "Beschwerde (Panel)", "args": "", "result": f"erkannt ({z.via}), "
                             + ("nur nachsehen" if z.gone else "Nutzer bittet erneut")})
            taten.note_live("klage")
            print(f"taten: beschwerde erkannt {profiles.log_name(z.who)} | {z.via} | gesperrt={len(z.gone)}", flush=True)
    # the switch narrows what the model sees (never more than the rights above left); a question no
    # rule recognizes may go to the model once as a pick from a fixed list (chat.route_model)
    z.all_tools = len(z.tools)
    z.all_names = {t["function"]["name"] for t in z.tools}   # before the Weiche narrows them (a choice runs its own tool)
    # "Schneller Antwortbeginn": the model sees this list (for a clear group its fixed set, below); what the rules
    # leave for this turn is what the panel runs (st["offered"], chat_tools.run), and the model is told so with the
    # question
    z.tools_stable = list(z.tools) if z.cache_on else None
    z.offered_all = {t["function"]["name"] for t in z.tools}
    # a way the person chose after the panel asked (klaeren weg) narrows to it even with „Gezielte Werkzeugwahl“ off:
    # the person named it in so many words; like every narrowing it only takes away
    if (z.route_on or z.weg) and z.tools and not z.pics and not z.ha_direct and not z.ha_wait:
        # the answer to the assistant's own question about a wish just before ("Worum soll es gehen?" - "Den
        # Mauerfall, 3 Folien"): the group of that wish, by the module's fixed rule (extras "route")
        if not z.route.names and z.ex.get("route"):
            z.route = z.intent.Route([z.ex["route"][0]], {z.ex["route"][0]: z.ex["route"][1]})
            print("weiche: Antwort auf die Rückfrage davor -", z.ex["route"][0], flush=True)
        if z.pick_task and not z.route.names:
            # the message as the model would see it anyway (code words already replaced); with the stable start
            # (chat.prompt_cache) the model sees every tool anyway, so a pick that is late is left out
            z.pick = await z.intent.pick_in_time(z.pick_task, z.intent.CACHED_WAIT if z.cache_on else z.intent.ASK_TIMEOUT + 1)
            if z.pick:   # the hint words' groups stay beside the pick (intent.narrow)
                z.route = z.intent.Route([z.pick], {z.pick: "Modell"}, z.route.hints)
            z.pick_state = "gewählt" if z.pick else "zu spät" if z.pick_task.cancelled() else \
                "unsicher" if z.pick_info.get("p") is not None else "keine"
        z.tools = z.intent.narrow(z.route, z.tools, z.ccfg, z.ex.get("keep", set()))
        if z.tools_stable is not None and z.route.names:
            # a fixed tool set per group (plan genauer-und-schneller, 3): a clear group always gets the same list in
            # the same order, so the server keeps one start per group in its cache, and the model chooses only among
            # the tools that fit; a question no rule recognizes keeps the full list
            z.tools_stable = list(z.tools)
        if z.ccfg.get("route_model") == "lean" and not z.route.names and not chat.needed(
                z.messages[-1]["content"] if z.messages[-1]["role"] == "user" else "",
                {t["function"]["name"] for t in z.tools}, z.ccfg.get("tool_words", "")):
            # nothing recognized and no tool required: a short list, so the model starts sooner
            z.tools = z.intent.lean(z.route, z.tools, z.ex.get("keep", set()))
    if z.pick_task and not z.pick_task.done():   # not needed in this turn (no tools, a picture, a direct command)
        z.pick_task.cancel()
    # „Einfach antworten“ to the panel's question which way (klaeren weg): the sentence as plain chat, so no tool that
    # changes something (taten.KIND) is offered in this answer; reading ones stay
    if z.weg and not z.weg["group"]:
        z.gone_n = len(z.tools)
        z.tools = [t for t in z.tools if t["function"]["name"] not in taten.KIND]
        z.tools_stable = [t for t in z.tools_stable if t["function"]["name"] not in taten.KIND] if z.tools_stable is not None else None
        print(f"klaeren: weg einfach | {z.gone_n - len(z.tools)} aendernde Werkzeuge nicht angeboten", flush=True)
    # Rückfragen der Weiche (klaeren.py area "weg", P5, Dominik 2026-11-10 3a): before anything changes, the panel asks
    # which way the person's own sentence goes when it could go two close changing ways or one changing way rests on weak
    # evidence (intent.ask_route, fixed rules, never the model). Only for the own login or voice, never a guest, MCP, after
    # outside text, a picture, an answer to another question or a fixed sentence of the panel; at most once per turn and
    # never twice for the same sentence. This answer is then only the fixed question with its chips (chat._answer), no
    # model and no tool, so nothing changes before the choice.
    z.weg_q = None
    if not z.weg and z.who and z.own_browser and z.private_ok and not z.mcp and not z.carry and not z.pics and not z.role_cmd \
            and not z.room_far and not z.ha_direct and not z.ha_wait and not z.kl_took and not z.cal_note and not z.xprop \
            and not z.kl_events and z.tools and z.messages[-1]["role"] == "user" and features.allowed("klaerenweg", z.who["id"], z.ccfg):
        z.weg_ask = z.intent.ask_route(z.route, z.messages[-1]["content"], z.offered_all, own=True, outside=bool(z.carry),
                                   unsure=z.pick_info.get("raw") if z.pick_state == "unsicher" else None)
        z.got = z.klaeren.weg_ask(z.who["id"], z.src, z.messages[-1]["content"], z.weg_ask, z.route,
                              chat.guess_language(z.messages[-1]["content"]) == "English", time.time()) if z.weg_ask else None
        if z.got:
            z.weg_q, z.weg_ev = z.got
            z.kl_events.append(z.weg_ev)
            z.tools, z.tools_stable = [], None
    # "Erst lokal suchen" (lokal.py) with the Quellen-Weiche (quellen.py, plan such-index/zuverlaessig.md, steps 3 and
    # 4): the second stage decides by fixed rules on the person's own words whether a question to know or read
    # something goes to the own data (intern), the world (extern) or both; the probe in Finden's index runs in a
    # thread of its own (quellen.PROBE_MS), only for the own profile. intern and beides get a quick look in exactly
    # the sources this turn offers (tools before narrowing: the same rights), started here and waited for in
    # chat._answer (at most chat.local_first_ms); beides also searches the web with the person's own words, started
    # before anything of the own data is read; naming an own source leaves the web out of this answer.
    z.local_task, z.web_own, z.lk_kind, z.web_ok = None, "", "", False
    if z.web_tap and not (z.lokal.on(z.ccfg, z.who) and z.own_browser and z.private_ok and not z.mcp and z.tools):
        print("lokal: Internet-Chip abgelehnt (nicht erlaubt)", flush=True)
        z.web_tap = ""
    if z.lokal.on(z.ccfg, z.who) and z.own_browser and z.private_ok and not z.mcp and z.messages[-1]["role"] == "user" and z.tools \
            and not z.cal_note and not z.pics and not z.role_cmd and not z.room_far and not z.ha_direct and not z.ha_wait and not z.weg_q:
        import quellen
        z.quellen = quellen
        z.lk_text = z.messages[-1]["content"]
        z.lk_nur = None
        if z.mp:   # the Mappe bound to this conversation: the probe and the look only in its entries
            import mappen
            z.mappen = mappen
            z.lk_nur = (await asyncio.to_thread(z.mappen.fuer_werkzeug, z.who, None, z.lk_text, z.mp.get("id")))[0]
        z.lk_ctx = {"route": z.route, "tool_words": z.ccfg.get("tool_words", ""), "eigen": True, "nur": z.lk_nur}
        if z.web_tap:   # „Auch im Internet suchen“: no second look in the own data, the turn before had it
            z.lk_kind, z.lk_why = "extern", ["Internet-Chip"]
            z.quellen.note("chip_genutzt")
        else:
            z.lk_kind, z.lk_why = await asyncio.to_thread(z.quellen.klasse, z.lk_text, z.who["id"], z.lk_ctx)
            z.quellen.note(z.lk_kind, z.lk_ctx.get("info"))
        # the panel's own web search only where the person may search the web in this turn: offered, no answer from
        # mail carried along, not held by the Notaus, its service not known to be gone (dienstwacht)
        import dienstwacht
        z.dienstwacht = dienstwacht
        import notaus
        z.notaus = notaus
        z.web_ok = "web_search" in z.offered_all and z.carry != "mail" and "web_search" not in z.notaus.locked_tools(
            z.notaus.level(), z.ex["changes"], bool(z.who and z.notaus.own(z.who["id"]))) \
            and not z.dienstwacht.tool_down("web_search", z.who["id"])
        z.lk_src = z.quellen.blick(z.lk_kind, z.lk_why, z.lokal.sources(z.offered_all), z.web_ok)
        z.web_own = z.lokal.own_words(z.lk_text)
        if z.web_tap:   # the web only, with the own words of the question kept with the offer
            z.lk_src = ["web"] if z.web_ok else []
            if not z.web_ok:   # Notaus, the service gone, the web not released, an answer from mail carried along
                print("lokal: Internet-Chip abgelehnt (Websuche gesperrt)", flush=True)
        if "eigene Quelle" in z.lk_why and any(t["function"]["name"] == "web_search" for t in z.tools):
            z.tools = [t for t in z.tools if t["function"]["name"] != "web_search"]
            z.system = z.per_turn(z.system, z.lokal.LOCAL_ONLY)
            z.lk_src = [k for k in z.lk_src if k != "web"]
        # a short plain reading question the panel fetches itself (intent.direct) needs no look before it
        if z.lk_src and not z.web_tap and features.allowed("direct", z.who["id"], z.ccfg) and z.intent.direct(
                z.lk_text, {t["function"]["name"] for t in z.tools}):
            z.lk_src = []
        if z.lk_src:
            z.local_task = asyncio.create_task(z.lokal.run(
                z.who["id"], z.lk_text, z.lk_src, z.lokal.budget(z.ccfg),
                z.body.get("convo") if isinstance(z.body.get("convo"), str) else None, z.lk_kind, z.lk_why, z.lk_ctx.get("info"),
                z.lk_nur, z.ccfg))
        else:
            print(z.lokal.log_line(z.lk_kind, z.lk_why, z.lk_src, info=z.lk_ctx.get("info")), flush=True)
    # "... und leg es aufs reMarkable" (remarkable.py): the panel puts this answer there afterwards, by a fixed rule
    # on the person's own words; the model only writes the answer
    import remarkable
    z.remarkable = remarkable
    z.rm_after = bool(z.messages[-1]["role"] == "user" and not z.pics and not z.role_cmd and not z.room_far and not z.mcp and not z.weg_q
                    and z.remarkable.answer_wanted(z.messages[-1]["content"], (z.who or {}).get("id"))
                    and z.remarkable.answer_ok(z.who, z.own_browser, z.private_ok))
    if z.rm_after:
        z.system = z.per_turn(z.system, z.remarkable.ANSWER_HINT)
    if z.ex["hints"] and not z.pics:
        z.system = z.per_turn(z.system, " ".join(z.ex["hints"]))
    # once mail or other outside text was read in this answer, nothing in it may change the home or
    # the memory, and after mail no words go to the web (see LOCKED_OUTSIDE / LOCKED_AFTER_MAIL)
    # (after the person's own documents also no web search: a document could ask to carry its text away;
    # with "Erst lokal suchen" it stays open, but only the person's own words go out, see chat_tools.py)
    def locked(st):
        # the Notaus is read again for every tool call: switched on during an answer it holds the next call off
        # (ex["own"]: asked for in the person's own words, e.g. a song after a web search about chords; outside
        # text stays data for it, mail and the Notaus still lock it)
        return ((chat.LOCKED_AFTER_MAIL | z.ex["changes"]) if st["mail"] else ((chat.LOCKED_OUTSIDE | z.ex["changes"]) - z.ex["own"])
                if st["outside"] else set()) | ({"web_search"} if st.get("docs") and not z.web_own else set()) \
            | z.notaus.locked_tools(z.notaus.level(), z.ex["changes"], bool(z.who and z.notaus.own(z.who["id"])))
    z.locked = locked
    # what this request cannot reach: said plainly, so the model does not make up appointments or mails
    z.missing = ([] if z.cal["calendars"] else ["Kalender"]) + ([] if z.mailbox else ["E-Mails"])
    if z.missing:
        z.system = (z.system + "\n\n" + "Du hast in diesem Gespräch keinen Zugriff auf: " + ", ".join(z.missing)
                  + " (nicht eingerichtet oder nicht mit einem Profil angemeldet). Fragt der Nutzer danach, sag "
                    "genau das und nenne nie Termine oder E-Mails, die du nicht aus einem Werkzeug hast.").strip()


async def _prompt(z):
    """Stufe 7 Prompt: Hinweise, erstes Werkzeug, direkte Befehle, Temperatur und der fertige Systemtext."""
    # a question about appointments, mail, reminders, news ... must go through the tool, not the
    # model's imagination (NEED_TOOLS)
    z.ask_text = z.messages[-1]["content"] if z.messages[-1]["role"] == "user" else ""
    # "Schau in meinem Archiv ..." means the own Kiwix (V01.0.261); when it is not offered, the model is told
    # why, so it does not answer from the uploaded documents instead
    import kiwix
    z.kiwix = kiwix
    if chat.needed(z.ask_text, {"archive_search"}) and "archive_search" not in {t["function"]["name"] for t in z.tools} \
            and (z.kiwix.admin_on() or "kiwix" in z.ask_text.lower()):
        z.why_not = z.kiwix.why_not(z.who, z.own_browser) or "es ist in dieser Antwort nicht angeboten"
        print("kiwix: archive asked, not offered:", z.why_not, flush=True)
        z.system = z.per_turn(z.system, "Der Nutzer fragt nach seinem Kiwix-Archiv, das ist hier nicht verfügbar: " + z.why_not
                          + ". Sag ihm das in einem Satz. Das Archiv ist nicht dasselbe wie seine hochgeladenen Dokumente: "
                            "durchsuche die Dokumente nicht stattdessen und antworte nicht aus ihnen.")
    z.need = chat.needed(z.ask_text, {t["function"]["name"] for t in z.tools}, z.ccfg.get("tool_words", ""))
    z.own_hint = chat.hint_lines(z.ccfg.get("tool_hints", ""), {t["function"]["name"] for t in z.tools})
    if z.own_hint:     # the admin's sentence per offered tool (chat.tool_hints, R2), never the model's own
        z.system = z.per_turn(z.system, z.own_hint)
    # the one tool the first round must call (chat.first_tool; Nachstellen uses the same rules)
    z.force = chat.first_tool(z.route, z.need, {t["function"]["name"] for t in z.tools}, z.route_on)
    import berater
    z.berater = berater
    if z.berater.wanted():    # which own rules this turn used (Verbessern → Regeln „30 Tage nicht gebraucht“)
        z.berater.rule_hits(z.ask_text, z.route, z.need, {t["function"]["name"] for t in z.tools}, z.ccfg)
    # "Was habe ich zuletzt / heute notiert?" ("Neueste zuerst", wissen.recent_window): a fixed rule on the person's
    # own words; the first round must look in the documents, which then lists the pages changed last
    z.recent_ask = None
    if z.docs and z.own_browser and z.private_ok and z.ask_text and "document_search" in {t["function"]["name"] for t in z.tools} \
            and features.allowed("rmfresh", z.who["id"]):
        z.recent_ask = wissen.recent_window(z.ask_text, chat.user_zone(z.body.get("tz")))
        if z.recent_ask is not None:
            z.force, z.need = "document_search", ["document_search"]
    # a module's own fixed rule (begleiter.py: "Öffne Safari" asked at the computer itself): that tool first
    if not z.force and z.ex.get("must") and z.ex["must"] in {t["function"]["name"] for t in z.tools}:
        z.force, z.need = z.ex["must"], [z.ex["must"]]
    # the words that matched, only as far as they are still in the message (a code word is gone by now)
    z.why = ", ".join(f"{k}: „{v if v.lower() in z.ask_text.lower() or v in ('Modell', 'Sende-Bitte', 'Seite', 'Folgefrage', 'Foto ändern', 'Abbruch', 'Rückfrage', 'Einfach antworten') else '…'}“"
                    for k, v in z.route.why.items())[:200]
    print("weiche: Absicht", z.route.label(), "| Grund", z.why or "-",
          "| Hinweis", "+".join(z.route.hints) or "-",
          "| Werkzeuge", f"{len(z.tools)} von {z.all_tools}" if len(z.tools) != z.all_tools else len(z.tools),
          "| Pflicht", z.force or ", ".join(z.need) or "-", "| gesperrt", z.carry or "nichts",
          "| eingrenzen", "an" if z.route_on else "aus", *(["| verneint"] if z.route.neg else []), flush=True)
    if z.carry:   # what is locked and why, said plainly so the model never makes up another reason
        z.line = z.intent.lock_line(z.carry, {t["function"]["name"] for t in z.tools} & z.locked({"mail": z.carry == "mail",
                                                                                          "outside": z.carry != "mail"}))
        if z.line:
            z.system = z.per_turn(z.system, z.line)
    # "Erklären statt Schweigen" (B4): asked for a function this turn does not offer -> a hint under the answer
    # with the reason from the rules above; the model only answers, the reason is never its own
    z.explain = z.intent.explain(z.route, z.offered_all, z.who, z.stranger, z.ccfg) \
        if z.messages[-1]["role"] == "user" and not z.pics and not z.role_cmd and not z.room_far else None
    if z.explain:
        print("weiche: erklärt", z.explain["key"], "-", z.explain["why"], flush=True)
    # "Funktionen vorschlagen" (tipps.py): fixed rules decide whether the hint above gets a card; only the kind of
    # question is counted, never its words; only for the profile's own login or device, never another voice
    z.tip_kind = None
    if z.who and z.own_browser and z.messages[-1]["role"] == "user":
        import tipps
        z.tipps = tipps
        z.tipps.record(z.who["id"], z.route.names, z.body.get("spoken") is True or z.hilfe_origin in z.hilfe.SPOKEN)
        if z.body.get("more"):   # a suggested sentence was sent (saetze.py): only the tool's name is counted
            import saetze
            z.saetze = saetze
            z.saetze.tapped(z.who["id"], z.body.get("more"))
        if z.explain:
            z.convo = z.body.get("convo") if isinstance(z.body.get("convo"), str) else ""
            z.explain["tip"] = z.tipps.wish(z.who["id"], z.explain, z.convo[:80], z.hilfe_origin, outside=bool(z.carry),
                                        admin=z.hilfe_admin != "profile")
            z.tip_kind = z.explain["tip"] and z.explain["tip"]["kind"]
    # "Eindeutiges direkt abrufen" (intent.DIRECT): a short, plain reading question; the panel calls the tool itself
    # in chat._answer and the model only says the result. Admin and profile switch, never guests or another voice.
    z.direct = z.intent.direct(z.ask_text, {t["function"]["name"] for t in z.tools}) \
        if z.who and z.own_browser and features.allowed("direct", z.who["id"], z.ccfg) and not z.pics and not z.role_cmd \
        and not z.room_far and not z.ha_direct and not z.ha_wait and not z.local_task and not z.recent_ask else None
    # a question about the Spark itself (hilfe.py): the panel looks it up itself, the model only says it (plan 4)
    if not z.direct and z.route.names == ["spark"] and z.who and z.own_browser and "spark_hilfe" in {t["function"]["name"] for t in z.tools} \
            and not z.pics and not z.role_cmd and not z.room_far and not z.ha_direct and not z.ha_wait and not z.local_task:
        z.direct = "spark_hilfe"
    z.direct_args = z.intent.direct_args(z.ask_text, chat.local_now(z.body.get("tz")).date()) \
        if z.direct in ("weather", "calendar_events") else {}
    # Rückfrage (klaeren.py, Stufe C): the person chose among a tool's candidates; the panel runs that tool again with
    # the same arguments and the chosen target fixed (ctx "pin", never an argument the model could write)
    z.kl_pin = None
    if z.kl and z.kl["kind"] == "choice" and z.kl["area"] in z.klaeren.TOOLS:
        z.kl_tool = z.kl["act"].get("tool")
        if z.kl_tool in z.ex["run"] or z.kl_tool in z.all_names:
            z.direct, z.direct_args = z.kl_tool, dict(z.kl["act"].get("args") or {})
            z.kl_pin = {"area": z.kl["area"], "said": z.kl["said"], "cand": z.kl["cand"]}
            print("klaeren: auswahl", z.kl["area"], flush=True)
        else:
            z.system = z.per_turn(z.system, "Rückfrage: Die Auswahl kann gerade nicht ausgeführt werden. Sag das kurz, ohne Werkzeug.")
    if z.direct:
        print("weiche: direkt abgerufen", z.direct, z.direct_args.get("date", ""), flush=True)
    if z.messages[-1]["role"] == "user" and z.ask_text:
        import weiche   # Funktionen → Weiche, Statistik: only the group and numbers, never a word of the question
        z.weiche = weiche
        z.weiche.count(z.route, len(z.tools), z.all_tools, z.direct)
        import weiche_unklar   # Funktionen → Weiche → unklar: the question only anonymized, never who asked
        z.weiche_unklar = weiche_unklar
        if z.weiche_unklar.wanted(z.who, z.guest, z.route, z.ccfg):
            z.weiche_unklar.start(z.route, z.ask_text, z.who["id"])
    z.check_on = bool(z.ccfg.get("answer_check", True))
    z.tool_temp = float(z.ccfg.get("tool_temperature", 0.1))
    # thinking only while choosing the tool: released by the admin for this profile (never guests)
    z.think_tools = bool(z.who and z.own_browser and features.allowed("toolthink", z.who["id"], z.ccfg))
    # small talk and a sentence that calls the wish off („Vergiss es“, intent.cancel): answered without any tool
    z.small = bool(chat.SMALLTALK.fullmatch(z.ask_text)) or z.intent.cancel(z.ask_text)
    # Ablauf und Freigabe zeigen (ablauf.py): the tools of this answer under it, a waiting proposal as a card with
    # Ja and Nein; only the profile's own device, never guests or another voice
    z.steps_on = bool(z.who and z.own_browser and features.allowed("ablauf", z.who["id"], z.ccfg))
    if z.tools_stable is not None and z.tools_stable:
        z.names = [t["function"]["name"] for t in z.tools]
        if len(z.names) < len(z.tools_stable):   # fewer for this question: said with it, the list itself stays
            z.turn_notes.append(chat.TOOLS_NOW + (", ".join(z.names) + "." if z.names else chat.TOOLS_NONE))
    if z.tools or z.tools_stable:
        z.system = (z.system + "\n\n" + chat.TOOL_RULES).strip()
    if z.system:
        z.messages = [{"role": "system", "content": z.system}] + z.messages


# the order of the stages, fixed (prepare runs them one after the other; tests read their source from here)
STUFEN = (_eingang, _weg, _wer, _rechte, _wartendes_ja, _werkzeuge, _prompt)
