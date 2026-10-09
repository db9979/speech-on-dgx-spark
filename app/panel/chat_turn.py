"""One chat turn, before the model is asked: who is speaking and what they may use (profile, voice, device
key, Telegram, iPhone app), the system prompt, answers to waiting proposals ("Ja" to a calendar entry,
a mail change, a correction ...), the tools on offer and the locks after outside text.

prepare() returns a Turn: every value it worked out, as attributes (t.who, t.ha, t.tools ...).
chat._answer() asks the model with it, chat_tools.run() carries out the tool calls."""
import asyncio
import json
import os
import sys
import time

import httpx
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import DEFAULTS  # noqa: E402
from core import admin_cookie_ok  # noqa: E402
import calendars  # noqa: E402
import documents  # noqa: E402
import extras  # noqa: E402
import fixes  # noqa: E402
import homeassistant  # noqa: E402
import images  # noqa: E402
from common import load_config  # noqa: E402
import mail  # noqa: E402
import proactive  # noqa: E402
import profiles  # noqa: E402
import speakers  # noqa: E402
import tidy  # noqa: E402
import wissen  # noqa: E402
import chat  # noqa: E402  (constants and helpers; imported fully before any call)


def shared_stranger(request, body, who):
    """Why this turn at a shared device gets no personal things ("" when it may): the request comes
    from an own speaker (its key, or it says so: that only makes it stricter) and the voice of this
    recording was not clearly the profile's own. Whose voice it was comes only from the panel itself
    (esp32.py sets it in the request scope), never from what a request says."""
    dev = profiles.device(request)
    shared = body.get("client") == "speaker" or "speech_voice" in request.scope
    if not shared and dev and not dev["scope"]:
        import esp32
        shared = esp32.by_device(dev["id"])[0] is not None
    if not shared or not who:
        return ""
    voice = request.scope.get("speech_voice")
    if voice and voice == who["id"]:
        return ""
    return str(request.scope.get("speech_voice_why") or "voice not recognized as the profile's own")[:160]


class Turn:
    """The values prepare() worked out for one turn (plus the queues chat._answer() adds)."""

    def __init__(self, values):
        self.__dict__.update(values)


async def prepare(request):
    body = await request.json()
    cfg = load_config()
    with open(DEFAULTS) as f:
        ccfg = dict(json.load(f)["chat"], **cfg.get("chat", {}))
    # text only (no image links or other parts); an answer the browser marked as made from mail or
    # other outside text keeps that mark (the browser is the person's own and has no reason to lie)
    messages = [dict({"role": m["role"], "content": m["content"]},
                     **({"mark": "mail" if m.get("mail") else "outside"} if m.get("mail") or m.get("outside") else {}))
                for m in (body.get("messages") if isinstance(body.get("messages"), list) else [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                and m["content"].strip()]
    if not messages:
        raise HTTPException(400, "messages are required")
    # what the assistant said right before this message (a note it made by itself may open the
    # conversation, which the trimming below drops)
    said_before = next((str(m["content"]) for m in reversed(messages[:-1]) if m["role"] == "assistant"), None) \
        if messages[-1]["role"] == "user" else None
    messages = chat.trim_history(messages, chat.history_chars(ccfg))
    # Outside text from earlier turns: the latest such answer still counts as read in this turn (it
    # could ask for something "in the next message"), so this turn starts locked; older ones are not
    # sent again at all.
    marked = [i for i, m in enumerate(messages) if m.get("mark")]
    carry = messages[marked[-1]]["mark"] if marked and marked[-1] >= len(messages) - 3 else None
    came_from = carry   # what the answer right before rested on (for learning from corrections)
    search = bool(ccfg.get("search") and ccfg.get("search_url"))
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
    # With the admin's chat.routing and the profile's "route" on, it narrows the tools (further down)
    # and a new request of the person's own that does not point back at an answer made from outside
    # text leaves that answer out, and with it its lock ("Setz das auf die Liste" keeps it locked).
    import intent   # (needs chat fully loaded: its word lists)
    ask0 = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
    route = intent.classify(ask0, ccfg.get("tool_words", ""), ccfg.get("route_words", ""))
    me0 = profiles.current(request)
    route_on = bool(ccfg.get("routing", False) and me0 and profiles.settings(me0["id"]).get("route"))
    if carry == "outside" and route_on and intent.wants_own(route, ask0):
        carry = None
        print("weiche: answer from outside text before; this message asks for", route.label(),
              "in its own words - that answer is left out, nothing locked", flush=True)
    messages, gone = chat.left_out(messages, marked[-1] if carry else -1)
    system = ccfg.get("system_prompt") or ""
    if gone:
        system = (system + "\n\n" + chat.LEFT_OUT_NOTE).strip()
        print("chat:", gone, "earlier answer(s) from outside text left out with their questions", flush=True)
    # an attached photo or document: outside text, so this answer is locked like one made from the web
    attach = chat.attachment(body) if messages[-1]["role"] == "user" else None
    if attach:
        carry = carry or "outside"
        kind, name, text, cut = attach
        system = (system + "\n\n" + chat.ATTACH_HINT + " " + ("Foto" if kind == "photo" else "Dokument")
                  + (f" „{name}“" if name else "") + "\n" + chat.wrap_outside(text)
                  + ("\n" + chat.ATTACH_CUT if cut and kind == "document" else "")).strip()
        print("chat: attachment", kind, len(text), "chars, answer locked like outside text", flush=True)
    # the time changes every minute: early in the system prompt it would make the model read the
    # prompt, all tools and the whole history anew each turn. With chat.prompt_cache it goes with the
    # question instead (only to the model, never into the history), so the server's cache keeps the rest.
    time_note = None
    if ccfg.get("datetime", True):
        if ccfg.get("prompt_cache", False) and messages[-1]["role"] == "user":
            time_note = chat.now_line(body.get("tz"))
        else:
            system = (system + "\n\n" + chat.now_line(body.get("tz"))).strip()
    # why the search is (not) offered, for the journal and for the model (never silently missing)
    print("chat: web search", "NOT offered: switched off (Einstellungen → Funktionen → Websuche)" if not ccfg.get("search")
          else "NOT offered: no SearXNG address" if not search
          else "locked: the answer before came from e-mail" if carry == "mail" else "offered", flush=True)
    system = (system + "\n\n" + (chat.SEARCH_LOCKED_HINT if search and carry == "mail" else chat.SEARCH_HINT if search
                                  else chat.SEARCH_OFF_HINT)).strip()
    who = profiles.current(request)
    # A shared device (an own speaker in a room, see esp32.py): anyone in the room can talk to it, so
    # the device key alone is nobody's word. Personal things (mail, calendar, memory, documents,
    # contacts, reminders, messages, smart home ...) only when the speech recognition clearly heard the
    # profile's own voice in this very recording; anyone else gets what a guest gets. Fixed rule, no switch.
    stranger = shared_stranger(request, body, who)
    if stranger:   # Zustand → Logs, area "Lautsprecher", yellow: only the reason, never what was asked
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
                  + (" " + chat.SHARED_SHORT_HINT if stranger.startswith("too little speech") else "")).strip()
    if not own_browser:
        # someone else's voice at this browser: the browser's conversation is not theirs, so it is
        # not sent along (and the browser keeps this turn out of its own history, see "foreign")
        messages = [m for m in messages[-1:] if m["role"] == "user"]
        if not messages:
            raise HTTPException(400, "a question is required")
    # conversation settings: what the request sends, else the profile's, else the admin's defaults
    # (speakers with a device key send nothing and get their profile's voice, speed and length)
    pset = dict(profiles.defaults(ccfg.get("defaults")), **(profiles.settings(who["id"]) if who else {}))
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
    if body.get("client") == "watch":
        system = (system + "\n\n" + chat.WATCH_HINT).strip()
    if body.get("client") == "siri":
        system = (system + "\n\n" + chat.SIRI_HINT).strip()
    if body.get("client") == "speaker":
        system = (system + "\n\n" + chat.SPEAKER_HINT).strip()
    # a voice recognized at someone else's device gets no personal data at all (it could be a recording
    # of that person): no memory, history, documents, calendar, contacts, lists or reminders
    prof = who if ccfg.get("memory", True) and own_browser else None
    if prof:  # guests get no memory at all
        system = (system + "\n\n" + chat.memory_hint(prof)).strip()
    past = bool(prof and ccfg.get("history", True))
    if past:
        system = (system + "\n\n" + chat.HISTORY_HINT).strip()
    # pictures (images.py): only with the admin's and the profile's switches, from its own login, app or
    # Telegram. The model sees them in this turn without any tools (no smart home either), and the
    # answer counts as outside text, so the next turn is locked as well.
    pics = images.for_turn(request, body, who if own_browser else None) if messages[-1]["role"] == "user" else []
    if pics:
        carry = carry or "outside"
        system = (system + "\n\n" + images.hint(len(pics))).strip()
        print("chat:", len(pics), "picture(s) attached, no tools in this answer, locked like outside text", flush=True)
    # Home Assistant only for the profile's own login or device key: a voice recognized at someone
    # else's device does not switch that profile's home
    ha = homeassistant.get(who["id"]) if who and own_browser and ccfg.get("homeassistant", False) and not pics else None
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
    if ccfg.get("homeassistant", False):  # why the smart home tools are (not) offered, for the journal
        print("homeassistant: turn for", who["name"] if who else "guest", "- tools",
              "offered" if ha else "NOT offered: " + (
                  "no profile signed in" if not who else "voice of another profile" if not own_browser
                  else "a picture is attached (no tools in this answer)" if pics
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
    if ha and messages[-1]["role"] == "user" and not room_far:
        latest = messages[-1]["content"]
        pend = chat._HA_PENDING.pop(who["id"], None)
        if homeassistant.is_command(latest) and await homeassistant.mentions_device(ha, latest):
            ha_direct = homeassistant.clean_command(latest)
        elif homeassistant._intent(latest):  # sounds like switching but is not taken as a command: say why
            print("homeassistant: not taken as a command:", repr(homeassistant.clean_command(latest)[:100]), flush=True)
        elif ha_code_ok and pend and time.time() - pend[0] < 120:
            ha_direct = pend[1]
        if ha_direct and ha_code and not ha_code_ok:
            chat._HA_PENDING[who["id"]] = (time.time(), ha_direct)
            print("homeassistant: command waits for the code word", flush=True)
            system = (system + "\n\n" + "Der Nutzer will etwas im Smart Home schalten, aber das Codewort fehlt. "
                      "Frag in einem kurzen Satz nach dem Codewort; sag nicht, dass etwas geschaltet wurde.").strip()
            ha_direct = None
            ha_wait = True
        else:
            ha_wait = False
    else:
        ha_wait = False
    # A question that names a device or room is answered from states the panel reads itself, so the
    # value never comes from the model's memory of earlier turns or from a guess.
    ha_read = None
    if ha and not ha_direct and not ha_wait and messages[-1]["role"] == "user" and not room_far \
            and not homeassistant._intent(messages[-1]["content"]):
        try:
            ha_read = await homeassistant.lookup(ha, messages[-1]["content"])
        except (httpx.HTTPError, ValueError) as e:
            print("homeassistant: lookup failed:", type(e).__name__, flush=True)
    # own documents plus the ones other profiles offer to everyone; neither for guests or a voice the
    # shared speaker does not recognize (private_ok)
    docs = documents.list_docs(who["id"], used_only=True) if who and private_ok and ccfg.get("documents", True) else []
    shared_docs = wissen.shared_list(who["id"]) if who and private_ok and ccfg.get("documents", True) else []
    if docs or shared_docs:
        system = (system + "\n\n" + chat.docs_hint(who, docs, shared_docs)).strip()
    docs = docs + shared_docs
    timers = bool(ccfg.get("reminders", True))
    if timers:
        system = (system + "\n\n" + chat.REMINDER_HINT).strip()
    # guests keep their reminders in the browser, which sends them along; profiles keep them on the Spark
    guest_rem = [{"id": x["id"][:16], "text": str(x.get("text", ""))[:200], "due": x["due"]}
                 for x in (body.get("reminders") if isinstance(body.get("reminders"), list) else [])
                 if isinstance(x, dict) and isinstance(x.get("id"), str)
                 and isinstance(x.get("due"), (int, float))][:50] if not who else []
    # e-mail like Home Assistant: only for the profile's own login or device key
    mailbox = bool(who and own_browser and private_ok and ccfg.get("mail", False) and mail.get(who["id"])["accounts"])
    if mailbox:
        system = (system + "\n\n" + chat.MAIL_HINT).strip()
    # tidying and drafts (tidy.py): only for mailboxes the profile switched on; changes after a yes
    tidy_st = tidy.state(who["id"]) if mailbox and tidy.admin_on() else None
    tidy_on = bool(tidy_st and any(tidy.acct_state(tidy_st, x["id"])["mode"] != "off"
                                   for x in mail.get(who["id"])["accounts"]))
    drafts_on = bool(tidy_st and any(tidy.acct_state(tidy_st, x["id"]).get("drafts")
                                     for x in mail.get(who["id"])["accounts"]))
    if tidy_on:
        system = (system + "\n\n" + chat.TIDY_HINT).strip()
    if drafts_on:
        system = (system + "\n\n" + chat.DRAFT_HINT).strip()
    briefing = bool(ccfg.get("calendar", True))
    cal_note = []
    cal = calendars.get(who["id"]) if who and briefing and private_ok else {"calendars": [], "topics": []}
    # new appointments: only the profile's own login or device key, and only after a yes (see calendars.py)
    cal_write = bool(cal["calendars"] and own_browser)
    prop = None
    src = f"{body.get('client') or 'web'}:{body.get('convo') if isinstance(body.get('convo'), str) else ''}"
    if cal_write:
        system = (system + "\n\n" + chat.CALENDAR_ADD_HINT).strip()
        prop = calendars.pending(who["id"])
        if prop and prop.get("src", src) != src:
            prop = None  # proposed on another device or in another conversation: the yes is not for it
        if prop:
            latest = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
            calendars.drop_pending(who["id"])
            if calendars.confirms(latest):
                try:
                    where = await calendars.add_event(who["id"], prop)
                    note = f"Saved in calendar '{where}' (confirmed by the calendar server): {calendars.describe(prop)}"
                except Exception as e:
                    note = f"NOT saved, the calendar refused it: {e}. Proposal was {calendars.describe(prop)}"
                cal_note[:] = [{"name": "calendar_add (bestätigt)", "args": calendars.describe(prop), "result": note}]
                system = (system + "\n\nKalender: " + note + " Sag dem Nutzer genau das in einem Satz.").strip()
            else:
                system = (system + "\n\nKalender: Der vorgeschlagene Termin " + calendars.describe(prop)
                          + " wurde NICHT eingetragen, weil der Nutzer nicht zugestimmt hat.").strip()
    # an answer to something the assistant said by itself (yes to its offer, "nicht jetzt", ...):
    # the panel does what it means and the model only says the checked result (see proactive.py)
    mprop = None
    if (tidy_on or drafts_on) and not prop:
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
                system = (system + "\n\nPostfach: " + note + " Sag dem Nutzer genau das in einem Satz.").strip()
            else:
                system = (system + "\n\nPostfach: Der Vorschlag „" + what + "“ wurde NICHT ausgeführt, weil der "
                          "Nutzer nicht zugestimmt hat.").strip()
    # ticking off a list entry ... (extras.py): the module waiting for a yes in this conversation
    xprop = None
    if who and messages[-1]["role"] == "user" and not prop and not mprop:
        xprop = await extras.answer({"who": who, "own": own_browser, "src": src, "client": body.get("client"), "private": private_ok,
                                     "app": app_key, "device": (profiles.device_name(request) or "")[:40],
                                     "ha": ha, "ha_code": ha_code, "ha_code_ok": ha_code_ok}, messages[-1]["content"])
        if xprop:
            if xprop.get("outside"):
                carry = carry or "outside"
            cal_note.append(xprop["call"])
            system = (system + "\n\n" + xprop["system"]).strip()
    pro = None
    if who and own_browser and messages[-1]["role"] == "user" and not prop and not mprop and not xprop:  # one yes confirms one thing
        pro = proactive.reply(who["id"], messages[-1]["content"], said_before)
        if pro:
            cal_note.append(pro["call"])
            system = (system + "\n\n" + pro["system"]).strip()
    # learning from corrections (fixes.py): a yes saves the proposed sentence, a correction leads to one
    fix_ok = bool(who and own_browser and private_ok and ccfg.get("memory", True) and fixes.on(ccfg, pset)
                  and messages[-1]["role"] == "user")
    fix_fix, fix_prev = False, ""
    if fix_ok and not prop and not mprop and not xprop and not pro:
        fp = fixes.pending(who["id"])
        if fp and fp.get("src", src) == src:
            fixes.drop_pending(who["id"])
            if fixes.confirms(messages[-1]["content"]):
                saved = profiles.remember(who["id"], fp["text"])
                cal_note.append({"name": "Korrektur gemerkt", "args": "", "result": saved or "nicht gespeichert"})
                system = (system + "\n\nGedächtnis: Gemerkt wurde „" + (saved or "") + "“. Sag dem Nutzer genau das "
                          "in einem kurzen Satz.").strip()
            else:
                system = (system + "\n\nGedächtnis: Der Vorschlag „" + fp["text"] + "“ wurde NICHT gemerkt, weil der "
                          "Nutzer nicht zugestimmt hat.").strip()
        elif fixes.is_correction(messages[-1]["content"], said_before):
            fix_fix = True
            fix_prev = next((m["content"] for m in reversed(messages[:-2]) if m["role"] == "user"), "")[:200]
    if who and own_browser and messages[-1]["role"] == "user":
        # one answer settles every proposal waiting in this conversation: a later "ja" meant for
        # something else never carries out an old one
        import agent
        import messages as inbox   # (messages is the conversation here)
        import tasks
        for mod in (calendars, tidy, tasks, fixes, agent, inbox, roomfar):
            p = mod.pending(who["id"])
            if p and p.get("src", src) == src:
                mod.drop_pending(who["id"])
    if briefing:
        system = (system + "\n\n" + chat.BRIEFING_HINT + (" " + chat.CALENDAR_HINT if cal["calendars"] else "")
                  + (" Nenne im Briefing nach den Erinnerungen kurz die ungelesenen Mails (Absender und Thema)."
                     if mailbox else "")).strip()
    # a voice recognized at someone else's device may read its own things but changes nothing that
    # lasts: no memory changes, no cancelled reminders (it could be a recording of that person)
    tools = ([chat.SEARCH_TOOL] if search else []) + (chat.MEMORY_TOOLS if prof and own_browser else []) + ([chat.HISTORY_TOOL] if past else []) \
        + ([chat.DOC_TOOL] if docs else []) + (([chat.HA_STATES_TOOL, chat.HA_HISTORY_TOOL] if ha_direct or ha_wait
             else [chat.HA_TOOL, chat.HA_STATES_TOOL, chat.HA_ACTION_TOOL, chat.HA_HISTORY_TOOL, chat.HA_TODO_TOOL]) if ha else []) \
        + (chat.REMINDER_TOOLS if timers and own_browser else []) + ([chat.BRIEFING_TOOL] if briefing else []) \
        + ([chat.CALENDAR_TOOL] if cal["calendars"] else []) + ([chat.CALENDAR_ADD_TOOL] if cal_write else []) \
        + (chat.MAIL_TOOLS if mailbox else []) + (chat.TIDY_TOOLS if tidy_on else []) + ([chat.DRAFT_TOOL] if drafts_on else []) \
        + ([chat.IPHONE_TOOL] if phone_act else [])
    # weather, contacts, parcels ... (extras.py): each offers its tools only when the profile switched it on
    ex = extras.offer({"who": who, "own": own_browser, "tz": body.get("tz"), "private": private_ok,
                       "client": body.get("client"),
                       "text": messages[-1]["content"] if messages[-1]["role"] == "user" else ""})
    tools += ex["tools"]
    if pics:
        tools = []
    if room_far:
        if not xprop:   # a guest or a voice of another profile: the fixed answer, nothing else
            note = roomfar.why_not({"who": who if own_browser else None, "own": own_browser, "client": body.get("client")})
            system = (system + "\n\nRaum-Modus: " + (note or "Das geht hier nicht.") + " Sag dem Nutzer genau das, kurz.").strip()
        tools = []
        print("room: message about another device's room mode - fixed rules, no tools in this answer", flush=True)
    # the switch narrows what the model sees (never more than the rights above left); a question no
    # rule recognizes may go to the model once as a pick from a fixed list (chat.route_model)
    all_tools = len(tools)
    if route_on and tools and not pics and not ha_direct and not ha_wait:
        if not route.names and ccfg.get("route_model") == "on":
            # the message as the model would see it anyway (code words already replaced)
            pick = await intent.ask_model(ccfg, messages[-1]["content"] if messages[-1]["role"] == "user" else "")
            if pick:
                route = intent.Route([pick], {pick: "Modell"})
        tools = intent.narrow(route, tools)
        if ccfg.get("route_model") == "lean" and not route.names and not chat.needed(
                messages[-1]["content"] if messages[-1]["role"] == "user" else "",
                {t["function"]["name"] for t in tools}, ccfg.get("tool_words", "")):
            # nothing recognized and no tool required: a short list, so the model starts sooner
            tools = intent.lean(route, tools)
    if ex["hints"] and not pics:
        system = (system + "\n\n" + " ".join(ex["hints"])).strip()
    # once mail or other outside text was read in this answer, nothing in it may change the home or
    # the memory, and after mail no words go to the web (see LOCKED_OUTSIDE / LOCKED_MAIL)
    # (after the person's own documents also no web search: a document could ask to carry its text away)
    def locked(st):
        return ((chat.LOCKED_MAIL | ex["changes"]) if st["mail"] else (chat.LOCKED_OUTSIDE | ex["changes"]) if st["outside"]
                else set()) | ({"web_search"} if st.get("docs") else set())
    # what this request cannot reach: said plainly, so the model does not make up appointments or mails
    missing = ([] if cal["calendars"] else ["Kalender"]) + ([] if mailbox else ["E-Mails"])
    if missing:
        system = (system + "\n\n" + "Du hast in diesem Gespräch keinen Zugriff auf: " + ", ".join(missing)
                  + " (nicht eingerichtet oder nicht mit einem Profil angemeldet). Fragt der Nutzer danach, sag "
                    "genau das und nenne nie Termine oder E-Mails, die du nicht aus einem Werkzeug hast.").strip()
    # a question about appointments, mail, reminders, news ... must go through the tool, not the
    # model's imagination (NEED_TOOLS)
    ask_text = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
    need = chat.needed(ask_text, {t["function"]["name"] for t in tools}, ccfg.get("tool_words", ""))
    # one clear intent with one needed tool: the first round must call exactly that one
    force = intent.forced(route, need, {t["function"]["name"] for t in tools}) if route_on else None
    # the words that matched, only as far as they are still in the message (a code word is gone by now)
    why = ", ".join(f"{k}: „{v if v.lower() in ask_text.lower() or v in ('Modell', 'Sende-Bitte') else '…'}“"
                    for k, v in route.why.items())[:200]
    print("weiche: Absicht", route.label(), "| Grund", why or "-",
          "| Werkzeuge", f"{len(tools)} von {all_tools}" if len(tools) != all_tools else len(tools),
          "| Pflicht", force or ", ".join(need) or "-", "| gesperrt", carry or "nichts",
          "| eingrenzen", "an" if route_on else "aus", flush=True)
    if carry:   # what is locked and why, said plainly so the model never makes up another reason
        line = intent.lock_line(carry, {t["function"]["name"] for t in tools} & locked({"mail": carry == "mail",
                                                                                          "outside": carry != "mail"}))
        if line:
            system = (system + "\n\n" + line).strip()
    check_on = bool(ccfg.get("answer_check", True))
    tool_temp = float(ccfg.get("tool_temperature", 0.1))
    # thinking only while choosing the tool: the admin allows it, the profile switches it on (never guests)
    think_tools = bool(who and own_browser and ccfg.get("tool_thinking", False) and pset.get("tool_think"))
    small = bool(chat.SMALLTALK.fullmatch(ask_text))
    if tools:
        system = (system + "\n\n" + chat.TOOL_RULES).strip()
    if system:
        messages = [{"role": "system", "content": system}] + messages
    return Turn(locals())
