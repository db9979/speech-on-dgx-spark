"""Der Spark ruft an (plan plaene/telefon-anruf.md, Stufe T4): the SIP part (telefon.Call.dial) places the call, this
module decides with fixed rules whom, when and why; never the model, a mail or the conversation.

    Weckruf, Erinnerung   ordered by the profile itself: the tool anruf_planen ("Ruf mich morgen um 7 an"), listed
                          and deleted under Ich → Telefon. The tool takes a time, a kind and a text, never a number.
    Rückruf               from outside with an unsure voice the caller says "Ruf mich zurück": the Spark hangs up and
                          calls the profile's confirmed number that matches the call (a forged number never reaches
                          the one who forged it). The answered call counts as proof like the Telefon-PIN.
    Alarm                 a service the Dienst-Wächter watches is gone ALARM_AFTER seconds or more: one call to the
                          admin, at most one per ALARM_EVERY, besides the note. Never in the quiet hours
                          (dienstwacht.NIGHT, always for calls, and the admin's quiet hours or "Nicht stören"): then
                          only the note; still gone when they end, the call comes then.
    Testanruf             the admin's button in step 4: an internal number, a fixed sentence.

Whom: target() picks the profile's assigned handset first, with chat.telefon_ziel "eigene" else its first confirmed
own number; the Rückruf goes to the confirmed number the call came from and also needs "eigene". At most DAY_LIMIT
calls a profile and day; the preference telefon_anrufbar ("Der Spark darf mich anrufen") says no for good; "Nicht
stören" holds a call. Not answered: once more after RETRY seconds, then a note instead. Ordered calls ring also in the
profile's quiet hours (the person asked for exactly that time), the alarm never.

Logs: kinds, profiles (profiles.log_name) and results, never a number, a reminder text or a PIN.
"""
import datetime
import re
import time

import features
import profiles
import telefon
import telefon_ich
from common import load_config

DAY_LIMIT = 5                   # calls from the Spark to one profile a day
RETRY = 5 * 60                  # not answered: once more after this, then a note
CALLBACK_WAIT = 5               # seconds between hanging up and the call back
ALARM_AFTER = 10 * 60           # a service gone this long: the alarm call
ALARM_EVERY = 60 * 60           # at most one alarm call in this time
LATE = 30 * 60                  # an ordered call this late (the Spark was off): a note instead
_queue = []                     # [{"t", "uid", "art", "text", "nr", "tries"}]: call backs and second tries
_alarm = {"held": False}        # the alarm waits for the end of the quiet hours

NO_CALLBACK = {
    "aus": "Einen Rückruf kann ich gerade nicht anbieten. Tippe stattdessen deine Telefon-PIN und Raute.",
    "ziel": "Rückrufe nach außen hat der Admin nicht freigegeben. Tippe stattdessen deine Telefon-PIN und Raute.",
    "limit": "Heute habe ich schon so oft angerufen, wie ich darf. Tippe stattdessen deine Telefon-PIN und Raute.",
    "nein": "Du hast Anrufe vom Spark unter Ich, Telefon ausgeschaltet. Tippe stattdessen deine Telefon-PIN und Raute.",
}
NOTE = {"weckruf": ("⏰ Weckruf", "Der Spark hat dich zum Weckruf nicht erreicht."),
        "erinnerung": ("📞 Erinnerung", ""),
        "rueckruf": ("📞 Rückruf", "Der Spark hat dich zum Rückruf nicht erreicht. Ruf gern noch einmal an.")}

TOOL = {"type": "function", "function": {
    "name": "anruf_planen",
    "description": "Lets the Spark call the user on their own phone at a time: a wake-up call (art 'weckruf') or a "
                   "reminder by phone call (art 'erinnerung', text = what to remind of). Give minutes from now or a "
                   "local date and time 'YYYY-MM-DDTHH:MM'. The Spark only ever calls the user's own phone; there is no "
                   "number to give and none may be given.",
    "parameters": {"type": "object", "required": ["art"], "properties": {
        "art": {"type": "string", "enum": list(telefon_ich.PLAN_ARTEN)},
        "text": {"type": "string", "description": "for a reminder: what to remind of, short"},
        "minutes": {"type": "number"}, "at": {"type": "string"}}}}}
HINT = ("anruf_planen lässt den Spark die Person auf ihrem eigenen Telefon anrufen: Weckruf oder Erinnerung per Anruf. "
        "Nur wenn sie ausdrücklich einen Anruf möchte („ruf mich an“, „weck mich per Anruf“); sonst reminder_set. "
        "Nie eine Rufnummer annehmen oder nennen.")
WORDS = re.compile(r"(?i)\b(ruf\w*\s+mich\b.{0,40}\ban\b|anrufen|per anruf|telefonisch|weckruf\w*|call me)")


def ziel(c=None):
    c = c or load_config()
    return "eigene" if c.get("chat", {}).get("telefon_ziel") == "eigene" else "intern"


def target(uid, c=None):
    """The number the Spark calls for uid: its assigned handset (the first), with chat.telefon_ziel "eigene" else its
    first confirmed own number; "" when none. Never anything the model, a mail or a call named."""
    hs = sorted(n for n, x in telefon.nummern().items() if x.get("uid") == uid)
    if hs:
        return hs[0]
    if ziel(c) == "eigene":
        for e in telefon_ich.numbers(uid):
            if e.get("ok"):
                return telefon.clean_number(telefon_ich._plain(e, "nr"))
    return ""


def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _busy(uid, now):
    """ "Nicht stören" (Spark-Begleiter: in a call or presenting)."""
    try:
        import begleiter
        return begleiter.busy(uid, now)
    except Exception:
        return False


def why_not(uid, now=None, nr=""):
    """"" when the Spark may call uid now, else the reason (a fixed word)."""
    now = time.time() if now is None else now
    r = features.reason("telefonanrufen", uid) if profiles.by_id(uid) else "guest"
    if r:
        return "nein" if r == "profile" else "aus"
    if not (nr or target(uid)):
        return "ziel"
    if telefon_ich.day_calls(uid, _day(now)) >= DAY_LIMIT:
        return "limit"
    if not telefon.signed_in():
        return "abgemeldet"
    if _busy(uid, now):
        return "stoeren"
    return ""


def call_back(uid, number, dry=False, now=None):
    """The caller from outside asked for a call back (telefon.Call.call_back): "ok" when it is queued, else the reason.
    Only to the profile's confirmed number that matches this call, and only with chat.telefon_ziel "eigene"."""
    now = time.time() if now is None else now
    nr = next((telefon.clean_number(telefon_ich._plain(e, "nr")) for e in telefon_ich.numbers(uid)
               if e.get("ok") and number and telefon_ich.same(telefon_ich._plain(e, "nr"), number)), "")
    if not nr:
        return "aus"
    if ziel() != "eigene":
        return "ziel"
    why = why_not(uid, now, nr)
    if why in ("stoeren", "abgemeldet"):
        why = "aus"
    if why or dry:
        return why or "ok"
    if any(q["uid"] == uid and q["art"] == "rueckruf" for q in _queue):
        return "ok"
    _queue.append({"t": now + CALLBACK_WAIT, "uid": uid, "art": "rueckruf", "text": "", "nr": nr, "tries": 1})
    print(f"telefon: rueckruf geplant fuer {telefon._log_name(uid)}", flush=True)
    return "ok"


async def _note(uid, art, text):
    import push
    title, body = NOTE.get(art, NOTE["erinnerung"])
    try:
        await push.send(uid, title, body or text or "Der Spark hat dich nicht erreicht.", tag="telefonanruf", why="Erinnerung")
    except Exception as e:
        print("telefon: anruf mitteilung", type(e).__name__, flush=True)


async def place(uid, art, text="", nr="", tries=0, now=None):
    """One call from the Spark to uid (weckruf, erinnerung, rueckruf): the rules, the call, the second try or a note.
    The result word."""
    now = time.time() if now is None else now
    why = why_not(uid, now, nr)
    if why:
        print(f"telefon: anruf raus ({art}) fuer {telefon._log_name(uid)} nicht moeglich ({why}), nur mitteilung", flush=True)
        await _note(uid, art, text)
        return why
    a = telefon._agent["a"]
    telefon_ich.day_calls(uid, _day(now), add=1)
    telefon._bump("raus")
    res = await telefon.Call.dial(a, nr or target(uid), uid, art, text)
    print(f"telefon: anruf raus ({art}) fuer {telefon._log_name(uid)}: {res}", flush=True)
    if res != "angenommen":
        if tries < 1:
            _queue.append({"t": now + RETRY, "uid": uid, "art": art, "text": text, "nr": nr, "tries": tries + 1})
            print(f"telefon: anruf raus ({art}) noch einmal in {RETRY // 60} min", flush=True)
        else:
            await _note(uid, art, text)
            print(f"telefon: anruf raus ({art}) aufgegeben, nur mitteilung", flush=True)
    return res


async def test_call(nr):
    """The admin's test call (step 4) to an internal number: a fixed sentence."""
    a = telefon._agent["a"]
    if not a or not telefon.signed_in():
        return "abgemeldet"
    telefon._bump("raus")
    res = await telefon.Call.dial(a, nr, "", "test")
    print(f"telefon: testanruf an {nr}: {res}", flush=True)
    return res


# ---------------------------------------------------------------- the alarm (Dienst-Wächter)
def _gone(now):
    """[(name, seconds)] of the watched services gone ALARM_AFTER or more (only names from dienstwacht.SVC)."""
    import dienstwacht
    out = []
    for sid, e in dienstwacht._read()["svc"].items():
        if e.get("st") == "down" and e.get("since") and now - e["since"] >= ALARM_AFTER and sid in dienstwacht.SVC:
            out.append((dienstwacht.SVC[sid][0], now - e["since"]))
    return out


def quiet_alarm(uid, now):
    """No alarm call: the fixed night of the Dienst-Wächter (always for calls), the admin's quiet hours or "Nicht stören"."""
    import dienstwacht
    h = dienstwacht._hour(now)
    if h >= dienstwacht.NIGHT[0] or h < dienstwacht.NIGHT[1]:
        return True
    try:
        import room
        if room.night(uid, datetime.datetime.fromtimestamp(now).astimezone()):
            return True
    except Exception:
        pass
    return _busy(uid, now)


def _admin():
    import notaus
    return next((u for u in notaus.admin_uids() if features.allowed("telefonalarm", u)), "")


async def alarm_tick(now=None):
    now = time.time() if now is None else now
    if not features.admin_on("telefonalarm"):
        _alarm["held"] = False
        return ""
    gone = _gone(now)
    if not gone:
        if _alarm["held"]:
            print("telefon: alarm entfallen, dienst wieder da", flush=True)
        _alarm["held"] = False
        return ""
    with telefon._lock:
        last = telefon._read().get("alarm_t", 0)
    if now - last < ALARM_EVERY:
        return ""
    uid = _admin()
    if not uid:
        return ""
    if quiet_alarm(uid, now):
        if not _alarm["held"]:
            _alarm["held"] = True
            print("telefon: alarm in ruhezeit, nur push", flush=True)
        return "ruhe"
    with telefon._lock:                 # also when no call goes out: the next try in an hour
        d = telefon._read()
        d["alarm_t"] = int(now)
        telefon._write(d)
    nr = target(uid)
    if not nr or not telefon.signed_in():
        print("telefon: alarm ohne ziel, nur push", flush=True)
        _alarm["held"] = False
        return "ziel"
    names = ", ".join(n for n, _s in gone[:3])
    mins = int(max(s for _n, s in gone) // 60)
    text = f"{names} {'antwortet' if len(gone) == 1 else 'antworten'} seit {mins} Minuten nicht. Mehr unter Zustand, Dienste."
    telefon._bump("alarm")
    telefon._bump("raus")
    res = await telefon.Call.dial(telefon._agent["a"], nr, uid, "alarm", text)
    if _alarm["held"]:
        print(f"telefon: alarm nach ruhezeit angerufen ({len(gone)} dienste): {res}", flush=True)
    else:
        print(f"telefon: alarm angerufen ({len(gone)} dienste): {res}", flush=True)
    _alarm["held"] = False
    return res


# ---------------------------------------------------------------- the clock
async def tick(now=None):
    """Every few seconds (telefon.loop): ordered calls that are due, call backs and second tries, the alarm."""
    now = time.time() if now is None else now
    if not telefon.settings()["on"]:
        return
    for uid in profiles.user_ids():
        for r in telefon_ich.planned(uid):
            if r["t"] > now:
                break
            telefon_ich.plan_drop(uid, r["id"])
            if now - r["t"] > LATE:
                print(f"telefon: anruf raus ({r['art']}) verpasst fuer {telefon._log_name(uid)}, nur mitteilung", flush=True)
                await _note(uid, r["art"], r.get("text", ""))
                continue
            await place(uid, r["art"], r.get("text", ""), now=now)
    for q in [q for q in _queue if q["t"] <= now]:
        _queue.remove(q)
        await place(q["uid"], q["art"], q["text"], q["nr"], q["tries"], now=now)
    await alarm_tick(now)


# ---------------------------------------------------------------- the assistant
def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    if not WORDS.search(str(ctx.get("text") or "")) or not features.allowed("telefonanrufen", who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "changes": {"anruf_planen"}, "keep": {"anruf_planen"}}


async def tool(name, args, ctx):
    import chat
    who = ctx.get("who") or {}
    uid = who.get("id")
    if name != "anruf_planen" or not uid:
        return "Not done: unknown tool."
    args = args if isinstance(args, dict) else {}
    art = args.get("art") if args.get("art") in telefon_ich.PLAN_ARTEN else "erinnerung"
    text = str(args.get("text") or "").strip()
    if art == "erinnerung" and not text:
        return "Not done: say what the reminder is about (text)."
    why = why_not(uid)
    if why in ("aus", "nein", "ziel"):
        de = {"aus": "Anrufe vom Spark sind für dich gerade nicht freigegeben.",
              "nein": "Du hast Anrufe vom Spark unter Ich → Telefon ausgeschaltet.",
              "ziel": "Für dich ist kein Telefon eingerichtet, das der Spark anrufen darf (Ich → Telefon)."}[why]
        print(f"telefon: anruf planen fuer {telefon._log_name(uid)} abgelehnt ({why})", flush=True)
        return f"Not done: {de} Sag das so in einem Satz."
    due = chat.reminder_due(args, ctx.get("tz"))
    if not due:
        return "Invalid time: give minutes from now or a future 'YYYY-MM-DDTHH:MM'."
    try:
        row = telefon_ich.plan_add(uid, due / 1000, art, text)
    except ValueError:
        print(f"telefon: anruf planen fuer {telefon._log_name(uid)} abgelehnt (voll)", flush=True)
        return f"Not done: there are already {telefon_ich.PLAN_MAX} planned calls (Ich → Telefon). Say so."
    when = datetime.datetime.fromtimestamp(row["t"], chat.user_zone(ctx.get("tz"))).strftime("%d.%m. %H:%M")
    print(f"telefon: anruf geplant ({art}) fuer {telefon._log_name(uid)}", flush=True)
    try:
        import tagebuch
        tagebuch.note(uid, "erinnerung", ("Weckruf" if art == "weckruf" else f"Anruf: {text}") + f" ({when})", ref=row["id"])
    except Exception as e:
        print("telefon: tagebuch", type(e).__name__, flush=True)
    return (f"Planned: the Spark calls the user's own phone at {when} ({'wake-up call' if art == 'weckruf' else 'reminder'})."
            " Say so in one short sentence; it is listed under Ich → Telefon.")
