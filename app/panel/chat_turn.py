"""One chat turn, before the model is asked: who is speaking and what they may use (profile, voice, device
key, Telegram, iPhone app), the system prompt, answers to waiting proposals ("Ja" to a calendar entry,
a mail change, a correction ...), the tools on offer and the locks after outside text.

prepare() returns a Turn: every value it worked out, as attributes (t.who, t.ha, t.tools ...).
chat._answer() asks the model with it, chat_tools.run() carries out the tool calls."""
import asyncio
import os
import sys
import time

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


def waiting_mods():
    """Every module that keeps one proposal per profile waiting for a plain "Ja" (profiles.pending_set): Notaus
    drops them all, and the Freigabe-Karte (ablauf.py) asks about the one this turn left."""
    import agent
    import messages as inbox   # (messages is the conversation in prepare)
    import tasks
    import roomfar
    return (calendars, tidy, tasks, fixes, agent, inbox, roomfar, meinmcp, hamelden, aendern, nasablage)


class Turn:
    """The values prepare() worked out for one turn (plus the queues chat._answer() adds)."""

    def __init__(self, values):
        self.__dict__.update(values)


async def prepare(request):
    body = await request.json()
    if isinstance(body, dict) and profiles.key_scope(request) == "tui":
        body["client"] = "tui"   # a terminal's key (terminal.py) says what it is, never the request; Markdown shown as text
    cfg = load_config()
    ccfg = cfg.get("chat", {})   # with the shipped defaults (common.load_config)
    # text only (no image links or other parts); an answer the browser marked as made from mail or
    # other outside text keeps that mark (the browser is the person's own and has no reason to lie)
    # every message (the latest too, which the trimming always keeps) is cut at chat.MAX_TURN_CHARS:
    # the word rules below run over it on the event loop
    # a described screen (bedienen.look) is never carried on: later turns see only profiles.SCREEN_NOTE
    messages = [dict({"role": m["role"], "content": profiles.SCREEN_NOTE if m.get("screen") and m["role"] == "assistant"
                      else m["content"][:chat.MAX_TURN_CHARS]},
                     **({"mark": "mail" if m.get("mail") else "outside"} if m.get("mail") or m.get("outside") or m.get("screen")
                        else {}))
                for m in (body.get("messages") if isinstance(body.get("messages"), list) else [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                and m["content"].strip()]
    if not messages:
        raise HTTPException(400, "messages are required")
    # what the assistant said right before this message (a note it made by itself may open the
    # conversation, which the trimming below drops)
    said_before = next((str(m["content"]) for m in reversed(messages[:-1]) if m["role"] == "assistant"), None) \
        if messages[-1]["role"] == "user" else None
    # everything the assistant said in this conversation, before trimming: notes it sent by itself are looked up
    # by their text further down (proactive.basis_note), also when the trimming drops them
    said_all = [str(m["content"]) for m in messages if m["role"] == "assistant"][-20:]
    # with chat.prompt_cache the kept part starts at a fixed question for several turns (chat.trim_history)
    messages = chat.trim_history(messages, chat.history_chars(ccfg), anchor=ccfg.get("prompt_cache") is True)
    # Outside text from earlier turns: the latest such answer still counts as read in this turn (it
    # could ask for something "in the next message"), so this turn starts locked; older ones are not
    # sent again at all.
    marked = [i for i, m in enumerate(messages) if m.get("mark")]
    carry = messages[marked[-1]]["mark"] if marked and marked[-1] >= len(messages) - 3 else None
    came_from = carry   # what the answer right before rested on (for learning from corrections)
    # Guests (no profile) and a voice the shared speaker did not recognize only ask and get answers: no tool, no
    # memory, no history, no timers, no web search (Dominik 2026-10-13: "einfach bloß Frage, Antwort"). Fixed rule.
    me0 = profiles.current(request)
    if body.get("client") == "android":   # the Android app's assistant sheet: only while released, never guests
        import android
        android.assist_gate(request, me0)
    guest = not me0 or bool(shared_stranger(request, body, me0))
    search = bool(ccfg.get("search") and ccfg.get("search_url")) and not guest and features.allowed("search", me0["id"], ccfg)
    # The answer before came from mail (also a mail note the assistant made by itself): kept in this
    # turn it would lock the web search too (its text could carry the mail away). So it is kept only
    # when the new question goes on about it ("Was schreibt sie noch?"); any other question (or one
    # that clearly wants the web) leaves it out, and with no word of the mail in this turn the search
    # and everything else is open again.
    if carry == "mail" and search and messages[-1]["role"] == "user":
        ask = messages[-1]["content"]
        wants_web = bool(chat.needed(ask, {"web_search"}, ccfg.get("tool_words", "")))
        if wants_web or not chat.MAIL_FOLLOW_UP.search(ask):
            carry = None
            print("chat: answer from mail before; this question", "wants the web" if wants_web else "is not about it",
                  "- that answer is left out, search offered", flush=True)
    # The person asks to send a message to someone ("Schreib Anna, dass ..."): the answer before, made
    # from outside text, would lock that. It is left out instead, so no word of it can get into the
    # message, and the panel reads the message back before the "Ja" (messages.py).
    if carry and messages[-1]["role"] == "user":
        import messages as inbox   # (messages is the conversation here)
        if inbox.wants_send(messages[-1]["content"]):
            carry = None
            print("chat: answer from outside text before; this message asks to write to someone - that answer "
                  "is left out, messages offered", flush=True)
    # the switch (intent.py): what the person's own latest message asks for, by fixed rules only.
    # With the admin's chat.routing on (released for the profile), it narrows the tools (further down)
    # and a new request of the person's own that does not point back at an answer made from outside
    # text leaves that answer out, and with it its lock ("Setz das auf die Liste" keeps it locked).
    import intent   # (needs chat fully loaded: its word lists)
    ask0 = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
    route = intent.classify_cfg(ask0, ccfg)
    # a follow-up („Und morgen?“) takes the group of the person's own question just before (plan weiche-intelligenter 1)
    if ask0 and not route.names:
        before0 = next((m["content"] for m in reversed(messages[:-1])
                        if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        follow = intent.follow_up(ask0, before0, ccfg)
        if follow:
            route = follow
            print("weiche: Folgefrage -", route.label(), flush=True)
    # a photo of this turn with a wish to change it is Bilder ändern (bilder.from_turn decides by its fixed rule
    # further down): the group bild, so no model pick starts and Logs → Anfragen does not show it as „unklar“
    if ask0 and not route.names and images.ids_of(body):
        import bilder
        if bilder.wants_change(ask0):
            route = intent.Route(["bild"], {"bild": "Foto ändern"})
            print("weiche: Foto mit Änderungswunsch - bild", flush=True)
    route_on = bool(me0 and features.allowed("routing", me0["id"], ccfg))
    # "Frag Spark" (hilfe.py): asked from a page of the panel, the question is about the Spark itself (a fixed
    # rule on where it was asked, never the model); the admin's own login only counts for the Spark's switches
    import hilfe
    hilfe_page = hilfe.page_of(body, me0["id"], ccfg) if me0 else None
    hilfe_focus = hilfe.focus_of(body, me0["id"], ccfg) if me0 else None
    hilfe_admin = hilfe.admin_here(request) if me0 else "profile"
    # where the question came from (plan hilfe-besser 10): only what the panel knows itself, never the question
    hilfe_origin = hilfe.origin(body, request)
    hilfe_app = hilfe.app_view(body)
    if (hilfe_focus or hilfe.page_rule(hilfe_page, ask0, route.names)) and route_on and hilfe_origin != "mcp":
        route = intent.Route(["spark"], {"spark": "Schalter" if hilfe_focus else "Seite"})
    # chat.route_model "on": the model's pick for a question no rule recognizes starts right here and runs while
    # the panel prepares the rest of the turn (plan „Anfrage aufteilen“ 2); it is waited for further down
    pick_state = None   # Logs → Anfragen: what became of the model's pick
    pick_info = {}      # with chat.route_model "systemone": its probability
    pick_task = asyncio.create_task(intent.ask_model(ccfg, ask0, pick_info, me0["id"])) \
        if route_on and ask0 and not route.names and ccfg.get("route_model") in ("on", "systemone") else None
    if carry == "outside" and route_on and intent.wants_own(route, ask0):
        carry = None
        print("weiche: answer from outside text before; this message asks for", route.label(),
              "in its own words - that answer is left out, nothing locked", flush=True)
    # a song in the person's own words („mach daraus einen House-Track“): the last answer from outside text (chords,
    # a style found on the web) stays as data for the description instead of being left out (Dominik 2026-10-16:
    # without it the model made up other chords); it locks the turn like any carried answer, the song excepted
    import musik
    if not carry and marked and marked[-1] >= len(messages) - musik.BACK and messages[marked[-1]]["mark"] == "outside" \
            and musik.wants(ask0):
        carry = "outside"
        print("musik: answer from outside text before kept as data for the song wish", flush=True)
    messages, gone = chat.left_out(messages, marked[-1] if carry else -1)
    system = ccfg.get("system_prompt") or ""
    # "Schneller Antwortbeginn" (chat.prompt_cache): what holds for this turn only goes with the question
    # (turn_notes, chat._answer), so the system prompt, the tool list and the conversation before stay the same
    # from turn to turn and the LLM server reads them from its cache. Switched off, all of it is in the system prompt.
    cache_on = ccfg.get("prompt_cache") is True and messages[-1]["role"] == "user"
    turn_notes = []

    def per_turn(system, text):
        if cache_on:
            turn_notes.append(text)
            return system
        return (system + "\n\n" + text).strip()
    if gone:
        system = per_turn(system, chat.LEFT_OUT_NOTE)
        print("chat:", gone, "earlier answer(s) from outside text left out with their questions", flush=True)
    # "Spark fragen" from another program over MCP (mcpserver.py; only the panel sets this in the scope): the
    # question is outside text from the start, and the turn only reads, with the tools the connection was given.
    # No memory, no earlier conversations, no smart home, no mail, no proposals and no "Ja" to waiting ones.
    mcp = request.scope.get("speech_mcp")
    if mcp:
        import mcpserver
        carry = "outside"
        messages = [m for m in messages[-1:] if m["role"] == "user"]
        system = (system + "\n\n" + mcpserver.MCP_HINT).strip()
    # an attached photo or document: outside text, so this answer is locked like one made from the web
    attach = chat.attachment(body) if messages[-1]["role"] == "user" else None
    if attach:
        carry = carry or "outside"
        kind, name, text, cut = attach
        system = per_turn(system, (chat.ATTACH_HINT + " " + ("Foto" if kind == "photo" else "Dokument")
                                   + (f" „{name}“" if name else "") + "\n" + chat.wrap_outside(text)
                                   + ("\n" + chat.ATTACH_CUT if cut and kind == "document" else "")).strip())
        print("chat: attachment", kind, len(text), "chars, answer locked like outside text", flush=True)
    # the time changes every minute: early in the system prompt it would make the model read the
    # prompt, all tools and the whole history anew each turn. With chat.prompt_cache it goes with the
    # question instead (only to the model, never into the history), so the server's cache keeps the rest.
    time_note = None
    if ccfg.get("datetime", True):
        if cache_on:
            time_note = chat.now_line(body.get("tz"))
        else:
            system = (system + "\n\n" + chat.now_line(body.get("tz"))).strip()
    # why the search is (not) offered, for the journal and for the model (never silently missing)
    print("chat: web search", "NOT offered: guest, only questions and answers" if guest
          else "NOT offered: switched off (Funktionen → Websuche)" if not ccfg.get("search")
          else "NOT offered: not for this profile (Personen und Geräte → Gesperrte Funktionen)" if not features.allowed("search", me0["id"], ccfg)
          else "NOT offered: no SearXNG address" if not search
          else "locked: the answer before came from e-mail" if carry == "mail" else "offered", flush=True)
    if cache_on and search and carry == "mail":   # the usual hint stays, the lock goes with the question
        system = (system + "\n\n" + chat.SEARCH_HINT).strip()
        turn_notes.append(chat.SEARCH_LOCKED_HINT)
    else:
        system = (system + "\n\n" + (chat.GUEST_HINT if guest else chat.SEARCH_LOCKED_HINT if search and carry == "mail"
                                      else chat.SEARCH_HINT if search else chat.SEARCH_OFF_HINT)).strip()
    who = profiles.current(request)
    # A shared device (an own speaker in a room, see esp32.py): anyone in the room can talk to it, so
    # the device key alone is nobody's word. Personal things (mail, calendar, memory, documents,
    # contacts, reminders, messages, smart home ...) only when the speech recognition clearly heard the
    # profile's own voice in this very recording; anyone else gets what a guest gets. Fixed rule, no switch.
    stranger = shared_stranger(request, body, who)
    if stranger:   # Zustand → Logs, area "Lautsprecher", yellow: only the reason, never what was asked
        if body.get("client") == "telefon":
            print("telefon: persoenliches zurueckgehalten -", stranger, "- guest rights for this question", flush=True)
        else:
            print("esp32: personal data withheld at", (profiles.device_name(request) or "speaker")[:40],
                  "-", stranger, "- guest rights for this question", flush=True)
    sound_of = who      # voice, speed and length of the answer stay the speaker's own
    # A voice recognized by the speech recognition (signed token, see speakers.py) picks that
    # profile for this turn; its own settings apply then, not the ones this browser sends.
    heard = speakers.check(body.get("speaker"), who["id"]) \
        if ccfg.get("speaker_id", False) and body.get("speaker") and who and not stranger else None
    heard = heard and profiles.by_id(heard)
    own_browser = not heard or (who and who["id"] == heard["id"])
    device_owner = who
    if heard:
        who = heard
    if stranger:
        who, own_browser = None, False
        system = (system + "\n\n" + chat.SHARED_STRANGER_HINT
                  + (" " + chat.SHARED_SHORT_HINT if stranger.startswith("too little speech") else "")
                  + (" " + chat.PHONE_PIN_HINT if request.scope.get("speech_pin_hint") else "")
                  + (" " + chat.PHONE_CALLBACK_HINT if request.scope.get("speech_callback_hint") else "")).strip()
    if not own_browser:
        # someone else's voice at this browser: the browser's conversation is not theirs, so it is
        # not sent along (and the browser keeps this turn out of its own history, see "foreign")
        messages = [m for m in messages[-1:] if m["role"] == "user"]
        if not messages:
            raise HTTPException(400, "a question is required")
    # conversation settings: what the request sends, else the profile's, else the admin's defaults
    # (speakers with a device key send nothing and get their profile's voice, speed and length)
    pset = profiles.effective(who and who["id"], ccfg)
    if stranger and sound_of:
        own = profiles.settings(sound_of["id"])
        pset.update({k: own[k] for k in ("voice", "speed", "length") if k in own})
    # guests change nothing: they get the admin's defaults (the admin's own browser may try speed and length)
    for k in (("voice", "speed", "length") if who else ("speed", "length") if admin_cookie_ok(request) else ()) \
            if own_browser else ():
        if k in body and profiles.SETTINGS[k][1](body[k]):
            pset[k] = body[k]
    length = chat.LENGTH_HINT.get(pset["length"])
    if length:
        system = (system + "\n\n" + length).strip()
    style = chat.own_style(ccfg, who, pset, own_browser)
    if style:
        system = (system + "\n\n" + chat.STYLE_INTRO + style).strip()
    # roles (roles.py): "Sei jetzt der Butler" is carried out by the panel with fixed rules, only for a
    # name the profile saved, only from its own words and voice; the model just says the result
    import roles
    role_cmd = None
    if roles.on(ccfg, who, pset, own_browser) and messages[-1]["role"] == "user" and not mcp:
        role_cmd = roles.command(messages[-1]["content"], roles.parse(pset.get("roles")))
        if role_cmd:
            note = role_note = roles.carry_out(who["id"], role_cmd, pset) if not mcp else "nicht über MCP"
            print("rolle:", role_cmd[0], "-", role_cmd[1] or "-", "(fixed rule, no tools in this answer)", flush=True)
            system = per_turn(system, "Rolle: " + note)
    # the Notaus by a fixed sentence (notaus.phrase): the panel decides from the person's own whole sentence, the
    # model only says the result; never over MCP, never for a stranger's voice at a shared speaker (who is then None)
    if not role_cmd and who and not mcp and messages[-1]["role"] == "user":
        import notaus
        na = notaus.phrase(messages[-1]["content"])
        if na:
            note = role_note = await notaus.by_phrase(na, who["name"], who["id"], notaus.phrase_channel(body.get("client")))
            role_cmd = ("notaus", na[0])
            print("notaus: fester Satz", na[0], "(fixed rule, no tools in this answer)", flush=True)
            system = per_turn(system, "Notaus: " + note + " Sag genau das in einem Satz.")
    # "Spark, Problem melden: …" (meldung.phrase): the panel makes a draft from the person's own words; nothing goes
    # out before the person looked at the preview (Ich → Probleme melden); never over MCP or for a stranger's voice
    if not role_cmd and who and not mcp and messages[-1]["role"] == "user":
        import meldung
        rp = meldung.phrase(messages[-1]["content"])
        if rp:
            note = role_note = await meldung.by_phrase(who["id"], who["name"], rp, meldung.phrase_channel(body.get("client")))
            role_cmd = ("meldung", "")
            print("meldung: fester Satz (fixed rule, no tools in this answer)", flush=True)
            system = per_turn(system, "Problem melden: " + note + " Sag genau das in einem Satz.")
    # "Das war falsch" / "Gut so" right after an answer (faelle.phrase): the panel notes it for the last answer of
    # the last 10 minutes; the model only says the fixed sentence. Never over MCP or for a stranger's voice.
    if not role_cmd and who and not mcp and messages[-1]["role"] == "user":
        verdict = faelle.phrase(messages[-1]["content"])
        if verdict:
            note = role_note = await asyncio.to_thread(faelle.by_phrase, who["id"], verdict)
            role_cmd = ("bewertung", verdict)
            print("faelle: fester Satz", verdict, "(fixed rule, no tools in this answer)", flush=True)
            system = per_turn(system, "Bewertung: " + note + " Sag genau das in einem Satz.")
    # "Was schlägt der Einstellungs-Assistent vor?" (berater.phrase): open proposals in fixed words for an admin
    # profile; a "ja" afterwards never takes one (that happens only on Zustand → Verbessern)
    if not role_cmd and who and not mcp and messages[-1]["role"] == "user":
        import berater
        if berater.takes(messages[-1]["content"], who["id"]):
            note = role_note = await asyncio.to_thread(berater.by_phrase, who["id"], messages[-1]["content"])
            role_cmd = ("berater", "")
            print("berater: fester Satz (fixed rule, no tools in this answer)", flush=True)
            system = per_turn(system, "Einstellungs-Assistent: " + note + " Sag genau das, kurz.")
    role = roles.prompt(pset) if roles.on(ccfg, who, pset, own_browser) else ""
    if role:
        system = (system + "\n\n" + role).strip()
    if body.get("client") == "watch":
        system = (system + "\n\n" + chat.WATCH_HINT).strip()
    if body.get("client") == "siri":
        system = (system + "\n\n" + chat.SIRI_HINT).strip()
    if body.get("client") == "android":
        system = (system + "\n\n" + chat.ANDROID_HINT).strip()
    if body.get("client") == "speaker":
        system = (system + "\n\n" + chat.SPEAKER_HINT).strip()
    if body.get("client") == "telefon":
        system = (system + "\n\n" + chat.PHONE_HINT).strip()
    # a voice recognized at someone else's device gets no personal data at all (it could be a recording
    # of that person): no memory, history, documents, calendar, contacts, lists or reminders
    prof = who if who and ccfg.get("memory", True) and own_browser and not mcp and features.allowed("memory", who["id"], ccfg) else None
    memcheck = None
    if prof:  # guests get no memory at all
        system = (system + "\n\n" + chat.memory_hint(prof)).strip()
        memcheck = chat.gedaechtnis.for_turn(prof["id"]) if features.allowed("gedpruefen", prof["id"], ccfg) else None
    past = bool(prof and ccfg.get("history", True) and features.allowed("history", prof["id"], ccfg))
    if past:
        system = (system + "\n\n" + chat.HISTORY_HINT).strip()
    # pictures (images.py): only with the admin's and the profile's switches, from its own login, app or
    # Telegram. The model sees them in this turn without any tools (no smart home either), and the
    # answer counts as outside text, so the next turn is locked as well.
    pics = images.for_turn(request, body, who if own_browser else None) if messages[-1]["role"] == "user" and not mcp else []
    if pics:
        carry = carry or "outside"
        system = per_turn(system, images.hint(len(pics)))
        print("chat:", len(pics), "picture(s) attached, no tools in this answer, locked like outside text", flush=True)
    # Home Assistant only for the profile's own login or device key: a voice recognized at someone
    # else's device does not switch that profile's home
    ha = homeassistant.get(who["id"]) if who and own_browser and ccfg.get("homeassistant", False) and not pics and not mcp \
        and features.allowed("ha", who["id"], ccfg) else None
    # over Telegram the profile decides: personal data only with tg_private, switching only with tg_ha
    # and a code word (the messages pass Telegram's servers)
    tg = body.get("client") == "telegram"
    tset = profiles.settings(who["id"]) if tg and who else {}
    private_ok = (not tg or bool(tset.get("tg_private"))) and own_browser
    if tg and ha and not (tset.get("tg_ha") and homeassistant.needs_code(ha)):
        ha = None
    # from the iPhone app the smart home switches only when the profile allowed it there (app_ha); the
    # key decides, not what the request says it is
    app_key = profiles.key_scope(request) == "app"
    # CarPlay: what the request says only makes it stricter (shorter answers, no smart home without
    # the profile's own car switch); it never unlocks anything
    car = bool(app_key and body.get("car") is True)
    if quiet(request, body, pset, car):
        body["speak"] = False
        print("chat: Antworten vorlesen aus, nur Text", flush=True)
    elif body.get("speak") is not False and wartung.paused("tts"):   # Wartungspause of the speech output: text only
        body["speak"] = False
        print("chat: wartungspause sprachausgabe, nur Text", flush=True)
    app_blocked = bool(ha and who and app_key and (not profiles.settings(who["id"]).get("app_ha")
                                                   or car and not profiles.settings(who["id"]).get("app_car_ha")))
    # actions on the iPhone itself: only from the app's own key, only when the profile allowed them
    phone_act = bool(app_key and who and own_browser and profiles.settings(who["id"]).get("app_act"))
    if app_key:
        system = (system + "\n\n" + chat.IPHONE_HINT + (" " + chat.IPHONE_ACT_HINT if phone_act else "")).strip()
        if car:
            system = (system + "\n\n" + chat.CAR_HINT).strip()
    if app_blocked:
        ha = None
    if tg:
        system = (system + "\n\n" + chat.TELEGRAM_HINT).strip()
    # the panel's own chat (browser, phone view, Android app) and the Begleiter: Markdown is shown formatted,
    # never spoken
    if body.get("client") in (None, "", "desk", "tui") and not app_key and not mcp:
        system = (system + "\n\n" + chat.WEB_HINT + " " + (
            chat.WEB_TEXT_HINT if body.get("speak") is False and body.get("client") != "desk"   # the Begleiter may read aloud
            else chat.WEB_SPOKEN_HINT)).strip()
    if ccfg.get("homeassistant", False):  # why the smart home tools are (not) offered, for the journal
        print("homeassistant: turn for", profiles.log_name(who), "- tools",
              "offered" if ha else "NOT offered: " + (
                  "no profile signed in" if not who else "voice of another profile" if not own_browser
                  else "a picture is attached (no tools in this answer)" if pics
                  else "not for this profile (Personen und Geräte → Gesperrte Funktionen)" if not features.allowed("ha", who["id"], ccfg)
                  else "not allowed in the car (Ich → iPhone-App)" if app_blocked and car
                  else "not allowed from the iPhone app (Ich → iPhone-App)" if app_blocked
                  else "token unreadable (stored with another key), connect again" if homeassistant._raw(who["id"])
                  else "this profile has not connected Home Assistant"), flush=True)
    if ha:
        system = (system + "\n\n" + chat.HA_HINT).strip()
    # code word for changes: only the user's own latest message counts, checked here, never by the
    # model; the model and everything after it see "[Codewort]" instead of the word
    ha_code = bool(ha and homeassistant.needs_code(ha))
    ha_code_ok = ha_code and messages[-1]["role"] == "user" and homeassistant.code_given(ha, messages[-1]["content"])
    if ha_code:
        system = (system + "\n\n" + chat.HA_CODE_HINT).strip()
        messages = [dict(m, content=homeassistant.redact(ha, m["content"])) if m["role"] == "user" else m
                    for m in messages]
    if not own_browser and device_owner:
        # a voice taken for someone else at this device may still have been the owner saying their
        # code word: it never reaches the model or the other profile's log either
        oha = homeassistant.get(device_owner["id"])
        if oha and homeassistant.needs_code(oha):
            messages = [dict(m, content=homeassistant.redact(oha, m["content"])) if m["role"] == "user" else m
                        for m in messages]
    # A plain switching command is carried out by the panel itself, not left to the model: the model
    # only puts the checked result into words. Without the code word the command waits (two minutes)
    # and runs as soon as the next message brings it.
    ha_direct = None
    # "Raummodus im Wohnzimmer an" is about the profile's own devices (roomfar.py, fixed rules), never
    # the smart home: no switching, no code word and no smart home tools in this turn
    import roomfar
    room_far = messages[-1]["role"] == "user" and roomfar.asks(messages[-1]["content"])
    # Rückfrage und Merken (klaeren.py): the answer to the panel's own question of this conversation,
    # read by fixed rules before anything else; it carries the code word of the command it answers
    import klaeren
    src = f"{body.get('client') or 'web'}:{body.get('convo') if isinstance(body.get('convo'), str) else ''}"
    kl_on = bool(who and own_browser and private_ok and not mcp and features.allowed("klaeren", who["id"]))
    kl = klaeren.answer(who["id"], src, messages[-1]["content"], own_browser) \
        if kl_on and messages[-1]["role"] == "user" and not room_far else None
    kl_took = bool(kl)
    ha_choice = ha_list = None
    kl_note, kl_events = [], []
    if kl and kl["kind"] == "remember":
        if kl["yes"]:
            row = klaeren.remember(who["id"], kl["area"], kl["words"], kl["target"])
            kl_note.append({"name": "Zuordnung (Panel)", "args": "", "result": "gemerkt"})
            system = per_turn(system, "Zuordnung: Gemerkt ist jetzt, dass „" + klaeren._shown(kl["said"]) + "“ "
                              + row["name"] + " ist. Sag dem Nutzer genau das in einem kurzen Satz, ohne Werkzeug.")
        else:
            system = per_turn(system, "Zuordnung: Nichts gemerkt, weil der Nutzer es nicht wollte. Bestätige das "
                              "in drei Wörtern, ohne Werkzeug.")
    elif kl and kl["kind"] == "none":
        system = per_turn(system, "Rückfrage: Der Nutzer meinte keines der genannten Geräte. Nichts wurde geschaltet. "
                          "Sag kurz, dass du nichts geschaltet hast, ohne Werkzeug.")
    elif kl and kl["area"] == "ha" and ha and (kl["code_ok"] or not homeassistant.needs_code(ha)):
        if kl["kind"] == "choice":
            ha_choice, ha_direct = kl, kl["said"] or "(Auswahl)"
        else:
            ha_list, ha_direct = kl, kl["said"] or "(Liste)"
    elif kl and kl["area"] in klaeren.TOOLS and kl["kind"] == "list":   # a tool's own candidates were all there is
        system = per_turn(system, "Rückfrage: Der Nutzer meinte keines der genannten. Nichts wurde ausgeführt. Bitte ihn "
                          "kurz, es genauer zu sagen, ohne Werkzeug.")
    elif kl and kl["area"] in klaeren.TOOLS:   # the choice runs the tool it answers, below (direct)
        ha_code_ok = ha_code_ok or bool(kl.get("code_ok"))   # it carries the code word of the request it answers
    elif kl:   # an area this turn cannot act in (Home Assistant off meanwhile): nothing happens
        system = per_turn(system, "Rückfrage: Die Auswahl kann gerade nicht ausgeführt werden. Sag das kurz, ohne Werkzeug.")
    if ha and messages[-1]["role"] == "user" and not room_far and not kl_took:
        latest = messages[-1]["content"]
        pend = chat._HA_PENDING.pop(who["id"], None)
        if homeassistant.is_command(latest) and await homeassistant.mentions_device(ha, latest):
            ha_direct = homeassistant.clean_command(latest)
        elif homeassistant._intent(latest):  # sounds like switching but is not taken as a command: say why
            print(f"homeassistant: not taken as a command | {len(str(latest).split())} words", flush=True)
        elif ha_code_ok and pend and time.time() - pend[0] < 120:
            ha_direct = pend[1]
        if ha_direct and ha_code and not ha_code_ok:
            chat._HA_PENDING[who["id"]] = (time.time(), ha_direct)
            print("homeassistant: command waits for the code word", flush=True)
            system = per_turn(system, "Der Nutzer will etwas im Smart Home schalten, aber das Codewort fehlt. "
                              "Frag in einem kurzen Satz nach dem Codewort; sag nicht, dass etwas geschaltet wurde.")
            ha_direct = None
            ha_wait = True
        else:
            ha_wait = False
    else:
        ha_wait = False
    # A question that names a device or room is answered from states the panel reads itself, so the
    # value never comes from the model's memory of earlier turns or from a guess.
    ha_read = None
    if ha and not ha_direct and not ha_wait and messages[-1]["role"] == "user" and not room_far and not kl_took \
            and not homeassistant._intent(messages[-1]["content"]):
        try:
            ha_read = await homeassistant.lookup(ha, messages[-1]["content"])
        except (httpx.HTTPError, ValueError) as e:
            print("homeassistant: lookup failed:", type(e).__name__, flush=True)
    # own documents plus the ones other profiles offer to everyone; neither for guests or a voice the
    # shared speaker does not recognize (private_ok)
    docs_ok = bool(who and private_ok and ccfg.get("documents", True) and (not mcp or "document_search" in mcp["tools"])
                   and features.allowed("documents", who["id"], ccfg))
    docs = documents.list_docs(who["id"], used_only=True) if docs_ok else []
    shared_docs = wissen.shared_list(who["id"]) if docs_ok else []
    if docs or shared_docs:
        system = per_turn(system, chat.docs_hint(who, docs, shared_docs, str(messages[-1].get("content") or ""),
                                                 wissen.on(who["id"], "brief")))
    docs = docs + shared_docs
    timers = bool(ccfg.get("reminders", True)) and not guest and bool(who) and features.allowed("reminders", who["id"], ccfg)
    if timers:
        system = (system + "\n\n" + chat.REMINDER_HINT).strip()
    # e-mail like Home Assistant: only for the profile's own login or device key
    mailbox = bool(who and own_browser and private_ok and not mcp and ccfg.get("mail", False) and features.allowed("mail", who["id"], ccfg)
                   and mail.get(who["id"])["accounts"])
    if mailbox:
        system = (system + "\n\n" + chat.MAIL_HINT).strip()
    # tidying and drafts (tidy.py): only for mailboxes the profile switched on; changes after a yes
    tidy_st = tidy.state(who["id"]) if mailbox and features.allowed("tidy", who["id"], ccfg) else None
    tidy_on = bool(tidy_st and any(tidy.acct_state(tidy_st, x["id"])["mode"] != "off"
                                   for x in mail.get(who["id"])["accounts"]))
    drafts_on = bool(tidy_st and any(tidy.acct_state(tidy_st, x["id"]).get("drafts")
                                     for x in mail.get(who["id"])["accounts"]))
    if tidy_on:
        system = (system + "\n\n" + chat.TIDY_HINT).strip()
    if drafts_on:
        system = (system + "\n\n" + chat.DRAFT_HINT).strip()
    briefing = bool(ccfg.get("calendar", True)) and not guest and bool(who) and features.allowed("calendar", who["id"], ccfg)
    cal_note = list(kl_note)
    if role_cmd:   # shown in the tool log like a tool the panel ran itself
        cal_note.append({"name": {"notaus": "Notaus (Panel)", "meldung": "Meldung (Panel)", "bewertung": "Bewertung (Panel)",
                                 "berater": "Einstellungs-Assistent (Panel)"}.get(role_cmd[0], "Rolle (Panel)"), "args": role_cmd[1], "result": role_note})
    cal = calendars.get(who["id"]) if who and briefing and private_ok and (not mcp or "calendar_events" in mcp["tools"]) \
        else {"calendars": [], "topics": []}
    # new appointments: only the profile's own login or device key, and only after a yes (see calendars.py)
    # Notaus stage 2 (notaus.py): no "Ja" carries anything out, every proposal waiting in this conversation is
    # dropped, and below no tool that changes something is offered (stage 1: none that goes to the internet)
    import notaus
    held = notaus.level()
    # Mein Notaus (notaus.py): this profile's own, like stage 2 for its actions only (reading goes on)
    mine = bool(who and notaus.own(who["id"]))
    if who:
        notaus.acting(who["id"])
    act_held = held >= 2 or mine
    src = f"{body.get('client') or 'web'}:{body.get('convo') if isinstance(body.get('convo'), str) else ''}"
    if act_held and who:
        for mod in waiting_mods():
            if mod.pending(who["id"]):
                mod.drop_pending(who["id"])
        print(f"notaus: {'Stufe ' + str(held) if held >= 2 else 'Mein Notaus'} - keine Aktion, kein Ja, nur lesen", flush=True)
    cal_write = bool(cal["calendars"] and own_browser and not mcp and not act_held)
    prop = None
    if cal_write:
        system = (system + "\n\n" + chat.CALENDAR_ADD_HINT).strip()
        prop = calendars.pending(who["id"]) if not kl_took else None
        if prop and prop.get("src", src) != src:
            prop = None  # proposed on another device or in another conversation: the yes is not for it
        if prop:
            latest = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
            calendars.drop_pending(who["id"])
            if prop.get("change") and calendars.confirms(latest):
                # calendar_change: move or delete one appointment (calendars.change_event), then keep the old one for undo
                kept = {}
                try:
                    note = await calendars.change_event(who["id"], prop, kept) + " (vom Kalender-Server bestätigt)"
                    aendern.note(who["id"], "calendar_ics", kept, "den Termin „" + prop["title"][:60] + "“ wie vorher stellen")
                except Exception as e:
                    note = f"NICHT geändert, der Kalender lehnte ab: {str(e)[:160]}. Vorschlag war {calendars.describe_change(prop)}"
                cal_note[:] = [{"name": "calendar_change (bestätigt)", "args": calendars.describe_change(prop), "result": note}]
                system = per_turn(system, "Kalender: " + note + " Sag dem Nutzer genau das in einem Satz.")
            elif prop.get("change"):
                system = per_turn(system, "Kalender: Der Vorschlag, " + calendars.describe_change(prop)
                                  + ", wurde NICHT ausgeführt, weil der Nutzer nicht zugestimmt hat.")
            elif calendars.confirms(latest):
                try:
                    put = {}
                    where = await calendars.add_event(who["id"], prop, put)
                    note = f"Saved in calendar '{where}' (confirmed by the calendar server): {calendars.describe(prop)}"
                    if put.get("href"):
                        aendern.note(who["id"], "calendar", put, "den Termin „" + prop["title"][:60] + "“ wieder löschen")
                except Exception as e:
                    note = f"NOT saved, the calendar refused it: {e}. Proposal was {calendars.describe(prop)}"
                cal_note[:] = [{"name": "calendar_add (bestätigt)", "args": calendars.describe(prop), "result": note}]
                system = per_turn(system, "Kalender: " + note + " Sag dem Nutzer genau das in einem Satz.")
            else:
                system = per_turn(system, "Kalender: Der vorgeschlagene Termin " + calendars.describe(prop)
                                  + " wurde NICHT eingetragen, weil der Nutzer nicht zugestimmt hat.")
    # an answer to something the assistant said by itself (yes to its offer, "nicht jetzt", ...):
    # the panel does what it means and the model only says the checked result (see proactive.py)
    mprop = None
    if (tidy_on or drafts_on) and not prop and not mcp and not act_held and not kl_took:
        mprop = tidy.pending(who["id"])
        if mprop and mprop.get("src", src) != src:
            mprop = None
        if mprop:
            latest = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
            tidy.drop_pending(who["id"])
            what = tidy.describe(mprop, tidy_st)
            if tidy.confirms(latest):
                try:
                    note = await asyncio.to_thread(tidy.carry_out, who["id"], mprop)
                except Exception as e:
                    note = f"NICHT ausgeführt, Fehler: {e}"
                cal_note.append({"name": "mail (bestätigt)", "args": what, "result": note})
                system = per_turn(system, "Postfach: " + note + " Sag dem Nutzer genau das in einem Satz.")
            else:
                system = per_turn(system, "Postfach: Der Vorschlag „" + what + "“ wurde NICHT ausgeführt, weil der "
                                  "Nutzer nicht zugestimmt hat.")
    # ticking off a list entry ... (extras.py): the module waiting for a yes in this conversation
    xprop = None
    if who and messages[-1]["role"] == "user" and not prop and not mprop and not mcp and not act_held and not kl_took:
        xprop = await extras.answer({"who": who, "own": own_browser, "src": src, "client": body.get("client"), "private": private_ok,
                                     "app": app_key, "device": (profiles.device_name(request) or "")[:40],
                                     "ha": ha, "ha_code": ha_code, "ha_code_ok": ha_code_ok}, messages[-1]["content"])
        if xprop:
            if xprop.get("event"):
                kl_events.append(xprop["event"])
            if xprop.get("outside"):
                carry = carry or "outside"
            cal_note.append(xprop["call"])
            system = per_turn(system, xprop["system"])
    # Bilder ändern (bilder.py): a photo of this turn with a wish to change it, or a short follow-up right after a
    # change, starts the change by a fixed rule; the model only says so (a turn with a photo has no tools anyway)
    if who and messages[-1]["role"] == "user" and not prop and not mprop and not xprop and not mcp and not act_held \
            and not kl_took:
        import bilder
        bprop = await bilder.from_turn({"who": who, "own": own_browser, "client": body.get("client"),
                                        "private": private_ok}, messages[-1]["content"], pics)
        if bprop:
            if bprop.get("event"):
                kl_events.append(bprop["event"])
            cal_note.append(bprop["call"])
            system = per_turn(system, bprop["system"])
    pro = None
    if who and own_browser and messages[-1]["role"] == "user" and not prop and not mprop and not xprop and not mcp \
            and not act_held and not kl_took:  # one yes confirms one thing
        pro = proactive.reply(who["id"], messages[-1]["content"], said_before)
        if pro:
            cal_note.append(pro["call"])
            system = per_turn(system, pro["system"])
    # a note the Spark said by itself is in this conversation: what it rested on, so the model does not make up a
    # source when the person asks about it (proactive.basis_note, V01.0.385)
    if who and messages[-1]["role"] == "user" and not mcp:
        basis = proactive.basis_note(who["id"], said_all)
        if basis:
            cal_note.append(basis[1])
            system = per_turn(system, basis[0])
    # learning from corrections (fixes.py): a yes saves the proposed sentence, a correction leads to one
    fix_ok = bool(who and own_browser and private_ok and ccfg.get("memory", True) and features.allowed("fixes", who["id"], ccfg)
                  and messages[-1]["role"] == "user" and not mcp and not act_held)
    fix_fix, fix_prev = False, ""
    if fix_ok and not prop and not mprop and not xprop and not pro and not kl_took:
        fp = fixes.pending(who["id"])
        if fp and fp.get("src", src) == src:
            fixes.drop_pending(who["id"])
            if fixes.confirms(messages[-1]["content"]):
                saved = profiles.remember(who["id"], fp["text"], src="fix", convo=body.get("convo"),
                                           version="fix")
                cal_note.append({"name": "Korrektur gemerkt", "args": "", "result": saved or "nicht gespeichert"})
                system = per_turn(system, "Gedächtnis: Gemerkt wurde „" + (saved or "") + "“. Sag dem Nutzer genau das "
                                  "in einem kurzen Satz.")
            else:
                system = per_turn(system, "Gedächtnis: Der Vorschlag „" + fp["text"] + "“ wurde NICHT gemerkt, weil der "
                                  "Nutzer nicht zugestimmt hat.")
        elif fixes.is_correction(messages[-1]["content"], said_before):
            fix_fix = True
            fix_prev = next((m["content"] for m in reversed(messages[:-2]) if m["role"] == "user"), "")[:200]
    # Nachfrage zum Gedächtnis (gedaechtnis.py): the answer to the panel's "Stimmt das noch?", and whether this
    # answer may ask one (same conditions as learning from corrections, its own switches)
    import gedaechtnis
    mem_ask_ok = bool(who and own_browser and private_ok and ccfg.get("memory", True) and gedaechtnis.ask_on(who["id"], ccfg)
                      and messages[-1]["role"] == "user" and not mcp and not act_held and not held)
    mem_ask_ok = mem_ask_ok and not (prop or mprop or xprop or pro or fixes.pending(who["id"]))
    mq = gedaechtnis.pending(who["id"]) if who and own_browser and messages[-1]["role"] == "user" and not mcp else None
    if mq and mq.get("src", src) == src and mq.get("convo", "") in ("", body.get("convo") or ""):
        gedaechtnis.drop_pending(who["id"])
        mem_ask_ok = False
        mf = next((f for f in profiles.memory(who["id"]) if f["id"] == mq.get("fact")), None)
        kind = gedaechtnis.reply_kind(messages[-1]["content"]) if mf else ""
        if kind == "yes":
            gedaechtnis.confirm(who["id"], mf["id"])
            system = per_turn(system, "Gedächtnis: Der Eintrag „" + mf["text"] + "“ ist jetzt bestätigt. Sag das in einem "
                              "kurzen Satz.")
        elif kind == "forget" and not act_held:
            profiles.forget(who["id"], fact_id=mf["id"])
            system = per_turn(system, "Gedächtnis: Der Eintrag „" + mf["text"] + "“ wurde vergessen. Sag das in einem "
                              "kurzen Satz.")
        elif kind == "no":
            system = per_turn(system, "Gedächtnis: Der Nutzer sagt, „" + mf["text"] + "“ stimmt nicht mehr. Frag kurz, "
                              "was jetzt stimmt, oder ob du es vergessen sollst. Geändert wird nichts.")
        elif kind == "fix" and fix_ok:
            fix_fix, fix_prev = True, mf["text"]   # fixes.py words it, a yes keeps it as a new version of the fact
        if kind:
            cal_note.append({"name": "Nachfrage (Panel)", "args": "", "result": {"yes": "bestätigt", "forget": "vergessen",
                             "no": "stimmt nicht mehr", "fix": "Korrektur"}[kind]})
            print(f"gedaechtnis: nachfrage beantwortet {profiles.log_name(who)} | antwort={kind}", flush=True)
    if who and own_browser and messages[-1]["role"] == "user" and not mcp:
        # one answer settles every proposal waiting in this conversation: a later "ja" meant for
        # something else never carries out an old one
        import agent
        import messages as inbox   # (messages is the conversation here)
        import tasks
        for mod in (calendars, tidy, tasks, fixes, agent, inbox, roomfar, hamelden, meinmcp, gedaechtnis, aendern, nasablage):
            if xprop and xprop.get("proposed") == mod.__name__:
                continue   # the panel made this proposal from this very message (agent: „Sag mir Bescheid, wenn …“)
            p = mod.pending(who["id"])
            if p and p.get("src", src) == src:
                mod.drop_pending(who["id"])
    if briefing:
        system = per_turn(system, chat.BRIEFING_HINT + (" " + chat.CALENDAR_HINT if cal["calendars"] else "")
                          + (" Nenne im Briefing nach den Erinnerungen kurz die ungelesenen Mails (Absender und Thema)."
                             if mailbox else ""))
    # a voice recognized at someone else's device may read its own things but changes nothing that
    # lasts: no memory changes, no cancelled reminders (it could be a recording of that person)
    tools = ([chat.SEARCH_TOOL] if search else []) + (chat.MEMORY_TOOLS if prof and own_browser else []) + ([chat.HISTORY_TOOL] if past else []) \
        + ([chat.DOC_TOOL, chat.DOC_LIST_TOOL] if docs else []) + (([chat.HA_STATES_TOOL, chat.HA_HISTORY_TOOL] if ha_direct or ha_wait
             else [chat.HA_TOOL, chat.HA_STATES_TOOL, chat.HA_ACTION_TOOL, chat.HA_HISTORY_TOOL, chat.HA_TODO_TOOL]) if ha else []) \
        + ([chat.CAMERA_TOOL] if ha and hamelden.camera_on(who["id"]) else []) \
        + (chat.REMINDER_TOOLS if timers and own_browser else []) + ([chat.BRIEFING_TOOL] if briefing else []) \
        + ([chat.CALENDAR_TOOL] if cal["calendars"] else []) + ([chat.CALENDAR_ADD_TOOL, chat.CALENDAR_CHANGE_TOOL] if cal_write else []) \
        + (chat.MAIL_TOOLS if mailbox else []) + (chat.TIDY_TOOLS if tidy_on else []) + ([chat.DRAFT_TOOL] if drafts_on else []) \
        + ([chat.IPHONE_TOOL] if phone_act else [])
    # weather, contacts, parcels ... (extras.py): each offers its tools only when the profile switched it on
    ex = extras.offer({"who": who, "own": own_browser, "tz": body.get("tz"), "private": private_ok,
                       "client": body.get("client"), "src": src,
                       "before": messages[-2]["content"] if len(messages) > 1 and messages[-2]["role"] == "assistant"
                       and isinstance(messages[-2].get("content"), str) else "",
                       "text": messages[-1]["content"] if messages[-1]["role"] == "user" else ""})
    tools += ex["tools"]
    if messages[-1]["role"] == "user" and isinstance(messages[-1].get("content"), str):
        kept = chat.offer_memory(tools, messages[-1]["content"])
        if len(kept) < len(tools):
            print("chat: memory_save not offered - the message only asks", flush=True)
        tools = kept
    if held or mine:
        gone_n = len(tools)
        tools = [t for t in tools if t["function"]["name"] not in notaus.locked_tools(held, ex["changes"], mine)]
        system = per_turn(system, notaus_note(held, mine))
        print(f"notaus: Stufe {held}{' + Mein Notaus' if mine else ''} - {gone_n - len(tools)} Werkzeuge nicht angeboten", flush=True)
    if mcp:   # only what the connection was given (mcpserver.ASK_TOOLS), never more than the rights above left
        tools = [t for t in tools if t["function"]["name"] in mcp["tools"]]
    if pics or role_cmd:
        tools = []
    if guest and tools:   # the fixed rule above, once more as a net: whatever offered something, a guest gets no tool
        print(f"chat: guest - {len(tools)} tools withheld, only questions and answers", flush=True)
        tools = []
    if room_far:
        if not xprop:   # a guest or a voice of another profile: the fixed answer, nothing else
            note = roomfar.why_not({"who": who if own_browser else None, "own": own_browser, "client": body.get("client")})
            system = per_turn(system, "Raum-Modus: " + (note or "Das geht hier nicht.") + " Sag dem Nutzer genau das, kurz.")
        tools = []
        print("room: message about another device's room mode - fixed rules, no tools in this answer", flush=True)
    # „Beschwerde erkennen“ (taten.py, systemone.py): "geht immer noch nicht" right after a deed of this profile.
    # The fixed list first, qwen38's probability only when the list finds nothing; then the model is told to look
    # first, and the tools that change things of that kind are not offered (unless the message asks again)
    last_acts = taten.last(who["id"]) if who and own_browser and not mcp and messages[-1]["role"] == "user" \
        and isinstance(messages[-1].get("content"), str) and features.allowed("einordnungklage", who["id"], ccfg) else []
    if last_acts and tools:
        said = messages[-1]["content"]
        klage, via = taten.complaint(said), "Liste"
        if not klage and len(said) <= 300:
            import systemone
            p_klage = await systemone.complaint(ccfg, said, taten.WHAT.get(last_acts[-1]["art"], taten.WHAT[""])[0])
            klage, via = p_klage is not None and p_klage >= systemone.KLAGE_MIN, "Einordnung"
        if klage:
            gone = taten.locked(last_acts, said)
            tools = [t for t in tools if t["function"]["name"] not in gone]
            system = per_turn(system, taten.complaint_note(last_acts, chat.guess_language(said) == "English"))
            cal_note.append({"name": "Beschwerde (Panel)", "args": "", "result": f"erkannt ({via}), "
                             + ("nur nachsehen" if gone else "Nutzer bittet erneut")})
            taten.note_live("klage")
            print(f"taten: beschwerde erkannt {profiles.log_name(who)} | {via} | gesperrt={len(gone)}", flush=True)
    # the switch narrows what the model sees (never more than the rights above left); a question no
    # rule recognizes may go to the model once as a pick from a fixed list (chat.route_model)
    all_tools = len(tools)
    all_names = {t["function"]["name"] for t in tools}   # before the Weiche narrows them (a choice runs its own tool)
    # "Schneller Antwortbeginn": the model always sees this list; what the rules below leave for this turn is
    # what the panel runs (st["offered"], chat_tools.run), and the model is told so with the question
    tools_stable = list(tools) if cache_on else None
    offered_all = {t["function"]["name"] for t in tools}
    if route_on and tools and not pics and not ha_direct and not ha_wait:
        # the answer to the assistant's own question about a wish just before ("Worum soll es gehen?" - "Den
        # Mauerfall, 3 Folien"): the group of that wish, by the module's fixed rule (extras "route")
        if not route.names and ex.get("route"):
            route = intent.Route([ex["route"][0]], {ex["route"][0]: ex["route"][1]})
            print("weiche: Antwort auf die Rückfrage davor -", ex["route"][0], flush=True)
        if pick_task and not route.names:
            # the message as the model would see it anyway (code words already replaced); with the stable start
            # (chat.prompt_cache) the model sees every tool anyway, so a pick that is late is left out
            pick = await intent.pick_in_time(pick_task, intent.CACHED_WAIT if cache_on else intent.ASK_TIMEOUT + 1)
            if pick:   # the hint words' groups stay beside the pick (intent.narrow)
                route = intent.Route([pick], {pick: "Modell"}, route.hints)
            pick_state = "gewählt" if pick else "zu spät" if pick_task.cancelled() else \
                "unsicher" if pick_info.get("p") is not None else "keine"
        tools = intent.narrow(route, tools, ccfg, ex.get("keep", set()))
        if ccfg.get("route_model") == "lean" and not route.names and not chat.needed(
                messages[-1]["content"] if messages[-1]["role"] == "user" else "",
                {t["function"]["name"] for t in tools}, ccfg.get("tool_words", "")):
            # nothing recognized and no tool required: a short list, so the model starts sooner
            tools = intent.lean(route, tools, ex.get("keep", set()))
    if pick_task and not pick_task.done():   # not needed in this turn (no tools, a picture, a direct command)
        pick_task.cancel()
    # "Erst lokal suchen" (lokal.py): the own sources before anything outside, by a fixed rule on the person's
    # own words. A knowledge question gets a quick look in exactly the sources this turn offers (tools before
    # narrowing: the same rights), started here and waited for in chat._answer (at most chat.local_first_ms);
    # naming an own source leaves the web out of this answer; anything current goes out as before.
    local_task, web_own = None, ""
    import lokal
    if lokal.on(ccfg, who) and own_browser and private_ok and messages[-1]["role"] == "user" and tools \
            and not pics and not role_cmd and not room_far and not ha_direct and not ha_wait:
        lk_text = messages[-1]["content"]
        lk_kind, lk_why = lokal.classify(lk_text, route, ccfg.get("tool_words", ""))
        lk_src = lokal.sources(offered_all)
        web_own = lokal.own_words(lk_text)
        if lk_kind == "lokal" and any(t["function"]["name"] == "web_search" for t in tools):
            tools = [t for t in tools if t["function"]["name"] != "web_search"]
            system = per_turn(system, lokal.LOCAL_ONLY)
        if lk_kind == "wissen" and lk_src:
            local_task = asyncio.create_task(lokal.run(who["id"], lk_text, lk_src, lokal.budget(ccfg),
                                                       body.get("convo") if isinstance(body.get("convo"), str) else None))
        else:
            print(lokal.log_line(lk_kind, lk_why, lk_src), flush=True)
    # "... und leg es aufs reMarkable" (remarkable.py): the panel puts this answer there afterwards, by a fixed rule
    # on the person's own words; the model only writes the answer
    import remarkable
    rm_after = bool(messages[-1]["role"] == "user" and not pics and not role_cmd and not room_far and not mcp
                    and remarkable.answer_wanted(messages[-1]["content"], (who or {}).get("id"))
                    and remarkable.answer_ok(who, own_browser, private_ok))
    if rm_after:
        system = per_turn(system, remarkable.ANSWER_HINT)
    if ex["hints"] and not pics:
        system = per_turn(system, " ".join(ex["hints"]))
    # once mail or other outside text was read in this answer, nothing in it may change the home or
    # the memory, and after mail no words go to the web (see LOCKED_OUTSIDE / LOCKED_MAIL)
    # (after the person's own documents also no web search: a document could ask to carry its text away;
    # with "Erst lokal suchen" it stays open, but only the person's own words go out, see chat_tools.py)
    def locked(st):
        # the Notaus is read again for every tool call: switched on during an answer it holds the next call off
        # (ex["own"]: asked for in the person's own words, e.g. a song after a web search about chords; outside
        # text stays data for it, mail and the Notaus still lock it)
        return ((chat.LOCKED_MAIL | ex["changes"]) if st["mail"] else ((chat.LOCKED_OUTSIDE | ex["changes"]) - ex["own"])
                if st["outside"] else set()) | ({"web_search"} if st.get("docs") and not web_own else set()) \
            | notaus.locked_tools(notaus.level(), ex["changes"], bool(who and notaus.own(who["id"])))
    # what this request cannot reach: said plainly, so the model does not make up appointments or mails
    missing = ([] if cal["calendars"] else ["Kalender"]) + ([] if mailbox else ["E-Mails"])
    if missing:
        system = (system + "\n\n" + "Du hast in diesem Gespräch keinen Zugriff auf: " + ", ".join(missing)
                  + " (nicht eingerichtet oder nicht mit einem Profil angemeldet). Fragt der Nutzer danach, sag "
                    "genau das und nenne nie Termine oder E-Mails, die du nicht aus einem Werkzeug hast.").strip()
    # a question about appointments, mail, reminders, news ... must go through the tool, not the
    # model's imagination (NEED_TOOLS)
    ask_text = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
    # "Schau in meinem Archiv ..." means the own Kiwix (V01.0.261); when it is not offered, the model is told
    # why, so it does not answer from the uploaded documents instead
    import kiwix
    if chat.needed(ask_text, {"archive_search"}) and "archive_search" not in {t["function"]["name"] for t in tools} \
            and (kiwix.admin_on() or "kiwix" in ask_text.lower()):
        why_not = kiwix.why_not(who, own_browser) or "es ist in dieser Antwort nicht angeboten"
        print("kiwix: archive asked, not offered:", why_not, flush=True)
        system = per_turn(system, "Der Nutzer fragt nach seinem Kiwix-Archiv, das ist hier nicht verfügbar: " + why_not
                          + ". Sag ihm das in einem Satz. Das Archiv ist nicht dasselbe wie seine hochgeladenen Dokumente: "
                            "durchsuche die Dokumente nicht stattdessen und antworte nicht aus ihnen.")
    need = chat.needed(ask_text, {t["function"]["name"] for t in tools}, ccfg.get("tool_words", ""))
    own_hint = chat.hint_lines(ccfg.get("tool_hints", ""), {t["function"]["name"] for t in tools})
    if own_hint:     # the admin's sentence per offered tool (chat.tool_hints, R2), never the model's own
        system = per_turn(system, own_hint)
    # the one tool the first round must call (chat.first_tool; Nachstellen uses the same rules)
    force = chat.first_tool(route, need, {t["function"]["name"] for t in tools}, route_on)
    import berater
    if berater.wanted():    # which own rules this turn used (Verbessern → Regeln „30 Tage nicht gebraucht“)
        berater.rule_hits(ask_text, route, need, {t["function"]["name"] for t in tools}, ccfg)
    # "Was habe ich zuletzt / heute notiert?" ("Neueste zuerst", wissen.recent_window): a fixed rule on the person's
    # own words; the first round must look in the documents, which then lists the pages changed last
    recent_ask = None
    if docs and own_browser and private_ok and ask_text and "document_search" in {t["function"]["name"] for t in tools} \
            and features.allowed("rmfresh", who["id"]):
        recent_ask = wissen.recent_window(ask_text, chat.user_zone(body.get("tz")))
        if recent_ask is not None:
            force, need = "document_search", ["document_search"]
    # a module's own fixed rule (begleiter.py: "Öffne Safari" asked at the computer itself): that tool first
    if not force and ex.get("must") and ex["must"] in {t["function"]["name"] for t in tools}:
        force, need = ex["must"], [ex["must"]]
    # the words that matched, only as far as they are still in the message (a code word is gone by now)
    why = ", ".join(f"{k}: „{v if v.lower() in ask_text.lower() or v in ('Modell', 'Sende-Bitte', 'Seite', 'Folgefrage', 'Foto ändern') else '…'}“"
                    for k, v in route.why.items())[:200]
    print("weiche: Absicht", route.label(), "| Grund", why or "-",
          "| Hinweis", "+".join(route.hints) or "-",
          "| Werkzeuge", f"{len(tools)} von {all_tools}" if len(tools) != all_tools else len(tools),
          "| Pflicht", force or ", ".join(need) or "-", "| gesperrt", carry or "nichts",
          "| eingrenzen", "an" if route_on else "aus", flush=True)
    if carry:   # what is locked and why, said plainly so the model never makes up another reason
        line = intent.lock_line(carry, {t["function"]["name"] for t in tools} & locked({"mail": carry == "mail",
                                                                                          "outside": carry != "mail"}))
        if line:
            system = per_turn(system, line)
    # "Erklären statt Schweigen" (B4): asked for a function this turn does not offer -> a hint under the answer
    # with the reason from the rules above; the model only answers, the reason is never its own
    explain = intent.explain(route, offered_all, who, stranger, ccfg) \
        if messages[-1]["role"] == "user" and not pics and not role_cmd and not room_far else None
    if explain:
        print("weiche: erklärt", explain["key"], "-", explain["why"], flush=True)
    # "Funktionen vorschlagen" (tipps.py): fixed rules decide whether the hint above gets a card; only the kind of
    # question is counted, never its words; only for the profile's own login or device, never another voice
    tip_kind = None
    if who and own_browser and messages[-1]["role"] == "user":
        import tipps
        tipps.record(who["id"], route.names, body.get("spoken") is True or hilfe_origin in hilfe.SPOKEN)
        if body.get("more"):   # a suggested sentence was sent (saetze.py): only the tool's name is counted
            import saetze
            saetze.tapped(who["id"], body.get("more"))
        if explain:
            convo = body.get("convo") if isinstance(body.get("convo"), str) else ""
            explain["tip"] = tipps.wish(who["id"], explain, convo[:80], hilfe_origin, outside=bool(carry),
                                        admin=hilfe_admin != "profile")
            tip_kind = explain["tip"] and explain["tip"]["kind"]
    # "Eindeutiges direkt abrufen" (intent.DIRECT): a short, plain reading question; the panel calls the tool itself
    # in chat._answer and the model only says the result. Admin and profile switch, never guests or another voice.
    direct = intent.direct(ask_text, {t["function"]["name"] for t in tools}) \
        if who and own_browser and features.allowed("direct", who["id"], ccfg) and not pics and not role_cmd \
        and not room_far and not ha_direct and not ha_wait and not local_task and not recent_ask else None
    # a question about the Spark itself (hilfe.py): the panel looks it up itself, the model only says it (plan 4)
    if not direct and route.names == ["spark"] and who and own_browser and "spark_hilfe" in {t["function"]["name"] for t in tools} \
            and not pics and not role_cmd and not room_far and not ha_direct and not ha_wait and not local_task:
        direct = "spark_hilfe"
    direct_args = intent.direct_args(ask_text, chat.local_now(body.get("tz")).date()) \
        if direct in ("weather", "calendar_events") else {}
    # Rückfrage (klaeren.py, Stufe C): the person chose among a tool's candidates; the panel runs that tool again with
    # the same arguments and the chosen target fixed (ctx "pin", never an argument the model could write)
    kl_pin = None
    if kl and kl["kind"] == "choice" and kl["area"] in klaeren.TOOLS:
        kl_tool = kl["act"].get("tool")
        if kl_tool in ex["run"] or kl_tool in all_names:
            direct, direct_args = kl_tool, dict(kl["act"].get("args") or {})
            kl_pin = {"area": kl["area"], "said": kl["said"], "cand": kl["cand"]}
            print("klaeren: auswahl", kl["area"], flush=True)
        else:
            system = per_turn(system, "Rückfrage: Die Auswahl kann gerade nicht ausgeführt werden. Sag das kurz, ohne Werkzeug.")
    if direct:
        print("weiche: direkt abgerufen", direct, direct_args.get("date", ""), flush=True)
    if messages[-1]["role"] == "user" and ask_text:
        import weiche   # Funktionen → Weiche, Statistik: only the group and numbers, never a word of the question
        weiche.count(route, len(tools), all_tools, direct)
    check_on = bool(ccfg.get("answer_check", True))
    tool_temp = float(ccfg.get("tool_temperature", 0.1))
    # thinking only while choosing the tool: released by the admin for this profile (never guests)
    think_tools = bool(who and own_browser and features.allowed("toolthink", who["id"], ccfg))
    small = bool(chat.SMALLTALK.fullmatch(ask_text))
    # Ablauf und Freigabe zeigen (ablauf.py): the tools of this answer under it, a waiting proposal as a card with
    # Ja and Nein; only the profile's own device, never guests or another voice
    steps_on = bool(who and own_browser and features.allowed("ablauf", who["id"], ccfg))
    if tools_stable is not None and tools_stable:
        names = [t["function"]["name"] for t in tools]
        if len(names) < len(tools_stable):   # fewer for this question: said with it, the list itself stays
            turn_notes.append(chat.TOOLS_NOW + (", ".join(names) + "." if names else chat.TOOLS_NONE))
    if tools or tools_stable:
        system = (system + "\n\n" + chat.TOOL_RULES).strip()
    if system:
        messages = [{"role": "system", "content": system}] + messages
    return Turn(locals())
