"""The assistant speaks up by itself: a short note or question when something real happens.

The panel decides when, by fixed rules and only from real data (calendar, Home Assistant states,
mail headers, reminders, the profile's own conversations, a weather search); the language model
never decides that something happened. Fixed sentences where possible; where the model words
something (follow-up question, weather), its answer must quote the data it came from.

Everything is per profile and off until the person switches it on (admin: chat.proactive allows
it at all). Each kind has its own switch, plus quiet hours, a daily limit and a pause. "Nicht
jetzt" pauses, "interessiert mich nicht" halves how often that kind may speak (learning, can be
switched off and reset). Guests never get anything.

Delivery: to the open conversation page (it polls /api/proactive), else as a push message.

    USERS_DIR/<user id>/proactive.json        state: counts, queue, last note, marks
    USERS_DIR/<user id>/proactive-rules.json  Home Assistant rules [{id, conds, minutes, text}]
"""
import asyncio
import datetime
import json
import re
import secrets
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import llm
import profiles
import vorrang
import features
from common import load_config, no_think
import core
from core import assistant, browser_profile, own_profile

router = APIRouter()

# kind: (label, at most per day before any feedback, setting that switches it)
# notes that hold nothing personal: these may also go to Telegram without tg_private (see telegram.py)
PUBLIC_KINDS = {"weather"}
KINDS = {"events": ("Termin-Vorlauf", 10, "pro_events"), "ha": ("Smart Home", 10, "pro_ha"),
         "greet": ("Begrüßung", 3, "pro_greet"), "follow": ("Nachfrage", 1, "pro_follow"),
         "mail": ("Wichtige Mail", 10, "pro_mail"), "weather": ("Wetter", 1, "pro_weather"),
         "tidy": ("Postfach aufräumen", 2, "pro_tidy"), "bday": ("Geburtstag", 1, "pro_bday"),
         "parcel": ("Paket kommt heute", 3, "pro_parcel"), "fuerdich": ("Fristen und Verdacht", 3, "pro_fuerdich"), "rueckblick": ("Wochenrückblick", 1, "pro_rueckblick"), "transit": ("Bus und Bahn", 1, "pro_transit"),
         "tipp": ("Funktion vorschlagen", 1, "pro_tips"),
         "feeds": ("Neues aus Feeds", 10, "pro_feeds"),   # feeds.py: replies at once, keyword hits at most feeds.WORD_DAY
         "meldung": ("Neue Problem-Meldung", 10, "pro_meldung"),
         "berater": ("Einstellungs-Assistent", 3, "pro_berater")}   # only forced (meldung.tell_admins), own switches
PAGE_ACTIVE = 75            # seconds since the page last asked: it is open, no push needed
QUEUE_KEEP = 2 * 3600
OFFER_SECONDS = 15 * 60     # an answer to a note counts this long after it
PAUSE_SECONDS = 2 * 3600    # "nicht jetzt"
GREET_GAP = 3 * 3600        # no greeting when the last conversation or greeting is more recent
MAIL_EVERY = 300
MAX_RULES = 20
_lock = threading.Lock()
_polled = {}                # uid -> time the page last asked


def ccfg():
    return load_config().get("chat", {})   # with the shipped defaults


def enabled():
    return features.admin_on("proactive")


def prefs(uid):
    return profiles.effective(uid)


def _zone(p):
    from chat import user_zone
    return user_zone(p.get("tz", ""))


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[„“\"'»«‚‘’]", "", str(text or "").lower())).strip()


# ---------------------------------------------------------------- state
def state(uid):
    try:
        with open(profiles._path(uid, "proactive.json")) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _mut(uid, fn):
    """Changes the state under the lock (load, fn(state), save); returns what fn returns."""
    with _lock:
        st = state(uid)
        res = fn(st)
        profiles._write(profiles._path(uid, "proactive.json"), st)
        return res


def _today(st, day):
    if st.get("day") != day:
        st.update(day=day, count=0, per={})


def quiet(p, local):
    m = re.fullmatch(r"(\d\d):(\d\d)-(\d\d):(\d\d)", p.get("pro_quiet") or "")
    if not m:
        return False
    a, b, t = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4]), local.hour * 60 + local.minute
    return a <= t < b if a < b else (t >= a or t < b) if a > b else False


def cap(st, p, kind):
    neg = int(st.get("neg", {}).get(kind, 0)) if p.get("pro_learn", True) else 0
    return KINDS[kind][1] >> neg


def blocked(uid, kind, p=None, local=None, st=None):
    """Why nothing may be said now, or "" when it may."""
    p = p or prefs(uid)
    local = local or datetime.datetime.now(_zone(p))
    st = state(uid) if st is None else st
    if not enabled():
        return "turned off by the admin"
    import notaus
    if notaus.refuse("auto", uid):     # the Notaus from stage 2, or the profile's own (notaus.py)
        return "Notaus"
    if features.blocked("proactive", uid):    # the admin blocked it for this profile (Personen und Geräte → Gesperrte Funktionen)
        return "blocked by the admin"
    if not p.get("pro_on"):
        return "turned off in the profile"
    if not p.get(KINDS[kind][2], True):
        return "this kind is turned off"
    if quiet(p, local):
        return "quiet hours"
    if st.get("pause_until", 0) > time.time():
        return "paused (nicht jetzt)"
    day = local.strftime("%Y-%m-%d")
    if st.get("day") == day and st.get("count", 0) >= int(p.get("pro_max", 6)):
        return "daily limit reached"
    if st.get("day") == day and st.get("per", {}).get(kind, 0) >= cap(st, p, kind):
        return "limit for this kind reached" if cap(st, p, kind) else "turned off by feedback"
    return ""


async def deliver(uid, kind, text, why="", data="", offer=None, until=None, force=False, mail=False, ref="", vg=None):
    """Says text to the profile (open page, else push) unless something blocks it; logs it in the
    profile's tool log. ref: what it is about (a Für-dich card), for the Begleiter's buttons. Returns the item, or None.
    vg: a Vorgang of Offen (vorgaenge.py) the note is about: its card goes into today's main conversation, the page
    only rings and speaks."""
    p = prefs(uid)
    local = datetime.datetime.now(_zone(p))
    text = re.sub(r"\s+", " ", str(text)).strip()[:400]
    reason = "" if force else blocked(uid, kind, p, local)
    if reason or not text:
        print(f"proactive: {kind} not said ({reason or 'empty'}) | {len(text)} chars", flush=True)
        return None
    import push
    now = time.time()
    page = now - _polled.get(uid, 0) < PAGE_ACTIVE
    item = {"id": secrets.token_hex(6), "t": int(now * 1000), "kind": kind, "text": text,
            "until": int(until or now + QUEUE_KEEP)}
    if mail:
        item["mail"] = True    # kept out of what the learner reads, like answers made from mail
    if vg:
        item["vg"] = vg
    private = kind not in PUBLIC_KINDS
    if not page and push.reachable(uid, private):
        item["pushed"] = True

    def put(st):
        _today(st, local.strftime("%Y-%m-%d"))
        st["count"] = st.get("count", 0) + (0 if force else 1)
        st.setdefault("per", {})[kind] = st["per"].get(kind, 0) + (0 if force else 1)
        st["last"] = {"t": now, "kind": kind, "offer": offer, "text": text}
        st["queue"] = [x for x in st.get("queue", []) if x.get("until", 0) > now][-19:] + [item]
        st["said"] = [x for x in st.get("said", []) if x.get("t", 0) > now - SAID_KEEP][-(SAID_MAX - 1):] + [
            {"t": now, "kind": kind, "text": text, "basis": basis_of(kind, why, data, mail)}]
    _mut(uid, put)
    # Zustand → Live: what it says by itself shows as a request of "Von selbst" (or on the rule's own way,
    # hamelden.said), with the push or the open page as target; never the text
    import live
    rec = own = live.current()
    if rec is None:
        rec = own = live.begin("auto", "", uid=uid, auto=True, why=KINDS[kind][0], src="timer")
        if rec is not None:
            rec.step("in", "Von selbst", now)
    else:
        own = None
    with live.within(rec):
        if item.get("pushed"):
            try:
                await push.send(uid, "💬 Spark", text, tag="pro-" + kind, private=private, ref=ref, **({"vg": vg} if vg else {}))
            except Exception as e:
                print("proactive: push:", type(e).__name__, e, flush=True)
        else:
            live.note(uid, "page", now, 1)
    if own is not None:
        live.end(own)
    if vg:
        try:
            import vorgaenge
            vorgaenge.say(uid, vg)
        except Exception as e:
            print("proactive: card", type(e).__name__, flush=True)
    profiles.tool_log_add(uid, f"(von selbst: {KINDS[kind][0]})",
                          [{"name": "von selbst: " + kind, "args": why, "result": data or text}], text)
    print(f"proactive: {kind} said ({'push' if item.get('pushed') else 'page'})", flush=True)
    return item


# Where a note came from (V01.0.385): kept two days, so the chat can say it when the person asks "wie meinst du
# das?" or "woher weißt du das?". Before, the model saw the note only as an answer from outside text and made
# up a source ("Du hast mir den Test in einer E-Mail geschrieben"). Only words the panel made or the person's
# own words go in; for a note from the mailbox no word of the mail.
SAID_KEEP = 2 * 86400
SAID_MAX = 20
OWN_DATA = {"follow"}       # the data of these kinds are the person's own words


def basis_of(kind, why, data, mail=False):
    why = re.sub(r"\s+", " ", str(why or "")).strip()[:120]
    if mail:
        return (why + " (nur Absender und Betreff gelesen)").strip()
    if kind in OWN_DATA and data:
        return (why + ": " + re.sub(r"\s+", " ", str(data)).strip()[:200]).strip(": ")
    return why or KINDS.get(kind, (kind,))[0]


def basis_note(uid, said):
    """A note for this chat turn when the conversation holds notes the Spark said by itself: what each rested on,
    so the model never makes up a source. said: the assistant's messages in the conversation. Returns
    (system line, log entry) or None."""
    if not said:
        return None
    heads = {_norm(x)[:60] for x in said if x}
    found = [x for x in state(uid).get("said", []) if _norm(x.get("text"))[:60] in heads][-3:]
    if not found:
        return None
    parts = []
    for x in found:
        local = datetime.datetime.fromtimestamp(x["t"], _zone(prefs(uid)))
        parts.append(f"um {local:%H:%M} am {local:%d.%m.} ({KINDS.get(x['kind'], (x['kind'],))[0]}), "
                     f"Grundlage laut Panel: {x.get('basis') or 'keine Angabe'}")
    line = ("Von selbst: Mindestens eine Nachricht des Assistenten in diesem Gespräch hat der Spark von sich aus "
            "geschickt, nicht auf eine Frage hin: " + "; ".join(parts) + ". Fragt der Nutzer, wie sie gemeint ist "
            "oder woher sie kommt, sag genau diese Grundlage. Erfinde keine andere Herkunft (keine E-Mail, kein "
            "Dokument, kein Gespräch, das hier nicht steht). Passt die Grundlage nicht zu dem, was der Nutzer "
            "meint, sag ehrlich, dass die Nachfrage danebenlag.")
    return line, {"name": "von selbst: Grundlage", "args": str(len(found)), "result": "; ".join(parts)[:400]}


def poll(uid, since=0):
    """Notes for the open page since a time (ms); also marks the page as open. A note one device
    already played is left out (V01.0.179: said once, not on every device of the profile)."""
    _polled[uid] = time.time()
    now = time.time()
    return [{k: x[k] for k in ("id", "t", "kind", "text", "mail", "vg") if k in x}
            for x in state(uid).get("queue", []) if x["t"] > since and x.get("until", 0) > now
            and not x.get("pushed") and not x.get("played")]


def take(uid, nid):
    """True for the first device that plays the note; every later one gets False."""
    def mark(st):
        x = next((x for x in st.get("queue", []) if x.get("id") == nid), None)
        if not x or x.get("played"):
            return False
        x["played"] = True
        return True
    return _mut(uid, mark)


# ---------------------------------------------------------------- answers to a note
NOT_NOW = re.compile(r"(?i)\b(nicht jetzt|jetzt nicht|lass mich( in ruhe)?|st[öo]r mich nicht|ruhe bitte|not now)\b")
SHORT = 60   # only a short answer counts; a longer message is a new question, not an answer to the note
LESS = re.compile(r"(?i)(interessiert mich nicht|brauch(e)? ich nicht|will ich nicht wissen|nicht mehr melden|"
                  r"meld(e)? dich (da(zu|mit)? )?nicht mehr|weniger davon|nervt|not interested|less of (this|that))")
MORE = re.compile(r"(?i)(danke für den hinweis|gut,? dass du (das )?(sagst|erinnerst)|mehr davon|thanks for the heads)")


def feedback(uid, kind, vote):
    """less: that kind may speak half as often (0: not at all); more: undoes one step; reset: all
    back; pause: nothing for two hours; resume: ends the pause."""
    def f(st):
        neg = st.setdefault("neg", {})
        if vote == "less" and kind in KINDS:
            neg[kind] = min(int(neg.get(kind, 0)) + 1, 4)
        elif vote == "more" and kind in KINDS:
            neg[kind] = max(int(neg.get(kind, 0)) - 1, 0)
        elif vote == "reset":
            st["neg"] = {}
        elif vote == "pause":
            st["pause_until"] = time.time() + PAUSE_SECONDS
        elif vote == "resume":
            st["pause_until"] = 0
    _mut(uid, f)
    return status(uid)


def calendars_confirms_or_feedback(text):
    import calendars
    return calendars.confirms(text) or bool(LESS.search(text) or NOT_NOW.search(text) or MORE.search(text))


def reply(uid, text, prev=None):
    """The panel's part when the person answers a note: a yes to an offered reminder sets it, "nicht
    jetzt" pauses, "interessiert mich nicht" lowers that kind. Returns {"system", "call"} for the
    chat (the model then says the checked result), or None.

    prev: the assistant's message right before this answer, if any. The answer only counts for the
    note when that message is the note (a "ja" to some other question is not meant for it)."""
    if not enabled() or not text:
        return None
    last = state(uid).get("last") or {}
    if time.time() - last.get("t", 0) > OFFER_SECONDS or len(text) > SHORT:
        return None
    if prev is not None and last.get("text") and _norm(last["text"])[:60] not in _norm(prev):
        return None
    if prev is None and not calendars_confirms_or_feedback(text):
        return None  # no note before it in this conversation: only a plain yes/no counts, never a new question
    import calendars
    kind = last.get("kind", "")
    offer = last.get("offer")
    p = prefs(uid)
    if offer and calendars.confirms(text):
        item = profiles.add_reminder(uid, offer["text"], offer["due"])
        _mut(uid, lambda st: st.get("last", {}).update(offer=None))
        when = datetime.datetime.fromtimestamp(item["due"] / 1000, _zone(p))
        note = f"Erinnerung gesetzt (vom Panel bestätigt): {when:%H:%M} Uhr, {item['text']}"
        return {"system": f"Von selbst: {note}. Sag dem Nutzer genau das in einem kurzen Satz.",
                "call": {"name": "von selbst: Erinnerung (bestätigt)", "args": text[:100], "result": note}}
    if LESS.search(text) and kind in KINDS:
        feedback(uid, kind, "less")
        left = cap(state(uid), p, kind)
        note = (f"Meldungen der Art „{KINDS[kind][0]}“ kommen ab jetzt seltener (höchstens {left} am Tag)"
                if left else f"Meldungen der Art „{KINDS[kind][0]}“ sind ab jetzt aus")
        _mut(uid, lambda st: st.update(last={}))
        return {"system": f"Von selbst: {note}; im Ich-Fenster unter „Von selbst“ lässt sich das zurücksetzen. "
                          "Bestätige das in einem kurzen Satz.",
                "call": {"name": "von selbst: weniger", "args": text[:100], "result": note}}
    if NOT_NOW.search(text):
        feedback(uid, kind, "pause")
        _mut(uid, lambda st: st.update(last={}))
        note = "Der Assistent meldet sich die nächsten zwei Stunden nicht von selbst"
        return {"system": f"Von selbst: {note}. Bestätige das in einem kurzen Satz.",
                "call": {"name": "von selbst: Pause", "args": text[:100], "result": note}}
    if MORE.search(text) and kind in KINDS:
        feedback(uid, kind, "more")
        return None
    if offer and calendars.NO.search(text):
        _mut(uid, lambda st: st.get("last", {}).update(offer=None))
        return {"system": "Von selbst: Der Nutzer will keine weitere Erinnerung; es wurde keine gesetzt. "
                          "Bestätige das kurz.",
                "call": {"name": "von selbst: Angebot abgelehnt", "args": text[:100], "result": "keine Erinnerung"}}
    return None


# ---------------------------------------------------------------- 2: appointments ahead
def _minutes(n):
    return "einer Minute" if n == 1 else f"{n} Minuten"


async def check_events(uid, p, now):
    import calendars
    if not features.allowed("calendar", uid) or not calendars.get(uid)["calendars"]:
        return
    lead = int(p.get("pro_lead", 20))
    res = await calendars.events(uid, now, now + datetime.timedelta(minutes=lead + 1), now.tzinfo)
    if not res:
        return
    done = state(uid).get("events_done", {})
    for x in res[0]:
        if x["allday"]:
            continue
        mins = round((x["start"] - now).total_seconds() / 60)
        key = f"{x['start'].isoformat()}|{x['title']}"
        if not 0 < mins <= lead or key in done:
            continue

        def mark(st, key=key):
            d = {k: v for k, v in st.get("events_done", {}).items() if v > time.time() - 2 * 86400}
            d[key] = time.time()
            st["events_done"] = d
        _mut(uid, mark)   # first: a note that cannot be said now is not tried again every minute
        text = f"In {_minutes(mins)}: {x['title']}" + (f", Ort {x['location']}" if x.get("location") else "") + "."
        offer = None
        if mins > 10 and features.allowed("reminders", uid):
            due = x["start"] - datetime.timedelta(minutes=5)
            offer = {"text": x["title"], "due": int(due.timestamp() * 1000)}
            text += f" Soll ich dich um {due:%H:%M} Uhr noch einmal erinnern?"
        await deliver(uid, "events", text, why=f"Termin in {_minutes(mins)}", data=calendars.line(x),
                      offer=offer, until=x["start"].timestamp())


# ---------------------------------------------------------------- 3: Home Assistant rules
OPS = {"above": "über", "below": "unter", "is": "ist", "changes": "ändert sich"}
ON_WORDS, OFF_WORDS = {"on", "an", "ein", "offen", "open", "auf"}, {"off", "aus", "zu", "geschlossen", "closed"}
_OPENING = {"window", "door", "opening", "garage_door"}


def rules(uid):
    try:
        with open(profiles._path(uid, "proactive-rules.json")) as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save_rules(uid, items):
    profiles._write(profiles._path(uid, "proactive-rules.json"), items[:MAX_RULES])


def pause_rule(uid, rid, paused):
    """Pauses or resumes one rule (Ich → Aufträge); True if there was one. A paused rule stays and says nothing."""
    with _lock:
        have = rules(uid)
        hit = next((r for r in have if isinstance(r, dict) and r.get("id") == rid), None)
        if hit is None:
            return False
        if paused:
            hit["paused"] = True
        else:
            hit.pop("paused", None)
        _save_rules(uid, have)
    print(f"proactive: rule {'paused' if paused else 'resumed'} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return True


async def _all_states(item):
    import homeassistant
    async with homeassistant._client(item) as c:
        r = await c.get(item["url"] + "/api/states")
        if r.status_code == 401:
            raise ValueError("Home Assistant rejected the token")
        r.raise_for_status()
        return [s for s in r.json() or [] if isinstance(s, dict) and s.get("entity_id")]


async def _resolve(item, text):
    """(entity_id, name) for a name or an entity id, from what the token may read."""
    import homeassistant
    all_states = await _all_states(item)
    names = {s["entity_id"]: (s.get("attributes") or {}).get("friendly_name") or s["entity_id"] for s in all_states}
    exact = next((s["entity_id"] for s in all_states if s["entity_id"] == text.strip().lower()), None)
    if exact:
        return exact, names[exact]
    words = [w for w in homeassistant._norm(text).split() if len(w) > 1 and w not in homeassistant._STOP]
    scored = homeassistant._score(all_states, {}, names, words) if words else []
    if not scored or scored[0][0] < len(words):
        raise ValueError(f"Kein Gerät zu „{text}“ gefunden. Nimm den Namen aus Home Assistant oder die entity_id.")
    eid = scored[0][2]["entity_id"]
    return eid, names[eid]


ONLY = {"": "", "away": "nur wenn ich unterwegs bin", "empty": "nur wenn niemand zu Hause ist",
        "night": "nur nachts", "day": "nur tagsüber"}
WHEN = {"both": "", "on": "bei an", "off": "bei aus"}
MAX_PAUSE = 24 * 60
# entities whose state says where a person is: never said aloud in a room (shared speaker rule)
PERSONAL = {"person", "device_tracker", "calendar", "todo", "notify", "camera", "image"}


def _me(all_states, uid):
    """The profile's person in Home Assistant: the one chosen under Ich (pro_ha_me), else the person
    whose name is the profile's name."""
    want = str(prefs(uid).get("pro_ha_me") or "")
    persons = [s for s in all_states if s["entity_id"].startswith("person.")]
    if want:
        return want if any(s["entity_id"] == want for s in persons) else ""
    name = _norm((profiles.by_id(uid) or {}).get("name", ""))
    hits = [s["entity_id"] for s in persons if name and _norm((s.get("attributes") or {}).get("friendly_name", "")) == name]
    return hits[0] if len(hits) == 1 else ""


async def add_rule(uid, body, src="", replace=""):
    """Checks a rule against what Home Assistant has and stores it. body: {"conds": [{entity, op, value,
    when}], "minutes", "text", "pause", "only", "loud", "speakers", "camera"}; src "voice" for a rule made by
    voice (hamelden.py, after a yes). replace: the id of a rule to change in place (same checks, keeps its
    id and place, forgets what it remembered so it starts fresh)."""
    import homeassistant
    import hamelden
    item = homeassistant.get(uid)
    if not item:
        raise ValueError("Home Assistant ist nicht verbunden.")
    have = rules(uid)
    old = next((r for r in have if r.get("id") == replace), None) if replace else None
    if replace and not old:
        raise LookupError("Diese Regel gibt es nicht mehr.")
    if not old and len(have) >= MAX_RULES:
        raise ValueError(f"Höchstens {MAX_RULES} Regeln.")
    conds = []
    for c in (body.get("conds") or [])[:2]:
        if not isinstance(c, dict) or not str(c.get("entity", "")).strip():
            continue
        op = c.get("op")
        if op not in OPS:
            raise ValueError("Unbekannte Bedingung.")
        value = str(c.get("value", "")).strip()[:40]
        if op in ("above", "below"):
            try:
                value = float(value.replace(",", "."))
            except ValueError:
                raise ValueError("Für „über“ und „unter“ braucht es eine Zahl.")
        elif op == "is" and not value:
            raise ValueError("Für „ist“ braucht es einen Zustand, z. B. an, aus, offen.")
        try:
            eid, name = await _resolve(item, str(c["entity"])[:80])
        except httpx.HTTPError as e:
            raise ValueError(f"Home Assistant nicht erreichbar: {type(e).__name__}")
        cond = {"entity": eid, "name": name, "op": op, "value": value if op != "changes" else ""}
        if op == "changes" and c.get("when") in ("on", "off"):
            cond["when"] = c["when"]
        conds.append(cond)
    if not conds:
        raise ValueError("Bitte ein Gerät angeben.")
    if any(c["op"] == "changes" for c in conds) and len(conds) > 1:
        raise ValueError("„ändert sich“ geht nur allein, ohne zweite Bedingung.")
    try:
        minutes = max(0, min(int(body.get("minutes") or 0), 720))
    except (TypeError, ValueError):
        minutes = 0
    try:
        pause = max(0, min(int(body.get("pause") or 0), MAX_PAUSE))
    except (TypeError, ValueError):
        pause = 0
    only = body.get("only") or ""
    if only not in ONLY:
        raise ValueError("Unbekannte Zusatzbedingung.")
    rule = {"id": secrets.token_hex(4), "conds": conds, "minutes": minutes,
            "text": re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", " ", str(body.get("text") or ""))).strip()[:200]}
    if pause:
        rule["pause"] = pause
    if only:
        rule["only"] = only
    if only == "away":
        try:
            me = _me(await _all_states(item), uid)
        except httpx.HTTPError as e:
            raise ValueError(f"Home Assistant nicht erreichbar: {type(e).__name__}")
        if not me:
            raise ValueError("Ich finde dich in Home Assistant nicht als Person. Wähle unter Ich → Von selbst "
                             "„Ich in Home Assistant“.")
        rule["me"] = me
    if body.get("loud"):
        rule.update(hamelden.check_loud(uid, rule, body.get("speakers")))
    if body.get("camera"):
        rule["camera"] = await hamelden.check_camera(uid, item, str(body.get("camera"))[:80])
    if src == "voice":
        rule["src"] = "voice"
    if old:
        rule["id"] = old["id"]
        _save_rules(uid, [rule if r.get("id") == old["id"] else r for r in have])
        _mut(uid, lambda st: st.get("rules", {}).pop(old["id"], None))
        return rules(uid)
    _save_rules(uid, have + [rule])
    return rules(uid)


def remove_rule(uid, rid):
    _save_rules(uid, [r for r in rules(uid) if r.get("id") != rid])
    _mut(uid, lambda st: st.get("rules", {}).pop(rid, None))
    return rules(uid)


def _number(s):
    a = s.get("attributes") or {}
    try:
        return float(s.get("state")), a.get("unit_of_measurement") or ""
    except (TypeError, ValueError):
        pass
    for k in ("current_temperature", "temperature"):   # thermostats, pools, spas
        if isinstance(a.get(k), (int, float)) and not isinstance(a.get(k), bool):
            return float(a[k]), "°C" if "temperature" in k else ""
    return None, ""


def _word(s):
    st = str(s.get("state", ""))
    dc = (s.get("attributes") or {}).get("device_class") or ""
    if st == "on":
        return "offen" if dc in _OPENING else "an"
    if st == "off":
        return "zu" if dc in _OPENING else "aus"
    return {"open": "offen", "closed": "zu", "home": "zu Hause", "not_home": "unterwegs",
            "playing": "am Abspielen", "idle": "ruhig"}.get(st, st)


def met(cond, s):
    if not s or s.get("state") in ("unavailable", "unknown", None):
        return False
    if cond["op"] in ("above", "below"):
        v, _ = _number(s)
        return v is not None and (v > cond["value"] if cond["op"] == "above" else v < cond["value"])
    if cond["op"] == "is":
        want, have = str(cond["value"]).strip().lower(), str(s.get("state", "")).lower()
        if have == want or _word(s).lower() == want:
            return True
        return (want in ON_WORDS and have in ("on", "open")) or (want in OFF_WORDS and have in ("off", "closed"))
    return False


def on_like(s):
    return met({"op": "is", "value": "an"}, s) or str((s or {}).get("state", "")) in ("home", "detected", "playing")


def off_like(s):
    return met({"op": "is", "value": "aus"}, s) or str((s or {}).get("state", "")) in ("not_home", "clear", "idle")


def only_ok(r, by_id, local):
    """The extra condition of a rule ("nur wenn ich unterwegs bin" ...), checked by the panel itself."""
    only = r.get("only") or ""
    if not only:
        return True
    if only == "away":
        s = by_id.get(r.get("me") or "")
        return bool(s) and s.get("state") not in ("home", "unavailable", "unknown", None)
    if only == "empty":
        persons = [s for e, s in by_id.items() if e.startswith("person.")]
        return bool(persons) and all(s.get("state") not in ("home", "unavailable", "unknown") for s in persons)
    sun = (by_id.get("sun.sun") or {}).get("state")
    night = sun == "below_horizon" if sun in ("below_horizon", "above_horizon") else (local.hour >= 21 or local.hour < 6)
    return night if only == "night" else not night


def describe(cond, s):
    """What the state is now, in words, e.g. "Whirlpool hat jetzt 38 °C"."""
    v, unit = _number(s)
    if cond["op"] in ("above", "below") and v is not None:
        return f"{cond['name']} hat jetzt {v:g}{(' ' + unit) if unit else ''}"
    return f"{cond['name']} ist jetzt {_word(s)}"


async def check_ha(uid, p, by_id=None):
    """Every rule of the profile against the states: from the live connection when it runs (hamelden.py,
    by_id), else read once now. The panel decides; nothing here switches anything."""
    import homeassistant
    import hamelden
    rs = rules(uid)
    item = homeassistant.get(uid) if rs and features.allowed("ha", uid) else None
    if not item:
        return
    if by_id is None:
        by_id = hamelden.cache(uid)
    if by_id is None or any(c.get("entity") not in by_id for r in rs for c in r.get("conds") or []):
        # no live connection, or it does not follow a new rule's device yet: read once now
        by_id = dict({s["entity_id"]: s for s in await _all_states(item)}, **(by_id or {}))
    now = time.time()
    fired = []
    for r in rs:
        conds = r.get("conds") or []
        if not conds or r.get("paused"):   # paused under Ich → Aufträge (plan „Eigene Aufgaben“): stays, says nothing
            continue

        def step(st, r=r, conds=conds):
            mem = st.setdefault("rules", {}).setdefault(r["id"], {})
            if conds[0]["op"] == "changes":
                s = by_id.get(conds[0]["entity"])
                cur = s.get("state") if s else None
                if cur in (None, "unavailable", "unknown"):
                    return None
                prev, mem["prev"] = mem.get("prev"), cur
                if prev is None or prev == cur:
                    return False
                when = conds[0].get("when")
                return (when != "on" or on_like(s)) and (when != "off" or off_like(s))
            if all(met(c, by_id.get(c["entity"])) for c in conds):
                mem.setdefault("since", now)
                if mem.get("armed") and not mem.get("fired") and now - mem["since"] >= r.get("minutes", 0) * 60:
                    mem["fired"] = True
                    return True
            else:   # false once: from now on the rule may fire (not at once when it was already true)
                mem.update(armed=True, fired=False)
                mem.pop("since", None)
            return False
        if _mut(uid, step):
            fired.append(r)
    if not fired:
        return
    local = datetime.datetime.now(_zone(p))
    full = by_id
    if any(r.get("only") for r in fired) and hamelden.cache(uid) is not None:
        # the live list holds only the rules' devices: persons and the sun are read once now
        full = dict({s["entity_id"]: s for s in await _all_states(item)}, **by_id)
    for r in fired:
        if not only_ok(r, full, local):
            print(f"proactive: ha rule {r['id']} true, but not now ({r['only']})", flush=True)
            continue

        def gap(st, r=r):
            mem = st.setdefault("rules", {}).setdefault(r["id"], {})
            if r.get("pause") and now - mem.get("said", 0) < r["pause"] * 60:
                return False
            mem["said"] = now
            return True
        if not _mut(uid, gap):
            print(f"proactive: ha rule {r['id']} true, but in its pause", flush=True)
            continue
        conds = r["conds"]
        said = "; ".join(describe(c, by_id.get(c["entity"])) for c in conds)
        text = r.get("text") or (said + ".")
        await hamelden.said(uid, r, text, said, item)


def rule_line(r):
    parts = []
    for c in r.get("conds") or []:
        v = f" {c['value']:g}" if isinstance(c.get("value"), (int, float)) else (f" {c['value']}" if c.get("value") else "")
        when = f" ({WHEN[c['when']]})" if c.get("when") in ("on", "off") else ""
        parts.append(f"{c.get('name') or c.get('entity', '?')} {OPS.get(c.get('op'), '')}{v}{when}")
    extra = [f"mindestens {r['minutes']} Minuten"] if r.get("minutes") else []
    extra += [ONLY[r["only"]]] if r.get("only") in ONLY and r.get("only") else []
    extra += [f"höchstens alle {r['pause']} Minuten"] if r.get("pause") else []
    extra += ["auch laut"] if r.get("loud") else []
    extra += ["mit Kamerabild"] if r.get("camera") else []
    return " und ".join(parts) + "".join(", " + x for x in extra)


# ---------------------------------------------------------------- 4: greeting when the page opens
async def greet(uid, now=None):
    """One sentence with the single most useful thing right now, when the last conversation and
    the last greeting are a while ago. Nothing to say: no greeting."""
    p = prefs(uid)
    zone = _zone(p)
    now = now or datetime.datetime.now(zone)
    st = state(uid)
    if blocked(uid, "greet", p, now, st) or time.time() - st.get("greet_t", 0) < GREET_GAP:
        return None
    newest = max([c.get("updated", 0) for c in profiles.convos(uid)] or [0]) / 1000
    if time.time() - newest < GREET_GAP:
        return None
    _mut(uid, lambda s: s.update(greet_t=time.time()))
    prof = profiles.by_id(uid) or {"name": ""}
    point, data = "", ""
    import calendars
    if features.allowed("calendar", uid) and calendars.get(uid)["calendars"]:
        try:
            # four real hours, also across a change of the clocks (wall-clock arithmetic would lose or add one)
            end = (now.astimezone(datetime.timezone.utc) + datetime.timedelta(hours=4)).astimezone(zone)
            res = await calendars.events(uid, now, end, zone)
            nxt = next((x for x in (res or ([], []))[0] if not x["allday"] and x["start"] > now), None)
            if nxt:
                point, data = f"Um {nxt['start']:%H:%M} Uhr hast du {nxt['title']}.", calendars.line(nxt)
        except Exception as e:
            print("proactive: greet calendar:", type(e).__name__, e, flush=True)
    if not point and features.allowed("reminders", uid):
        end = now.replace(hour=23, minute=59).timestamp() * 1000
        rem = [x for x in profiles.reminders(uid) if now.timestamp() * 1000 < x["due"] <= end]
        if rem:
            when = datetime.datetime.fromtimestamp(rem[0]["due"] / 1000, zone)
            point, data = f"Heute um {when:%H:%M} Uhr erinnere ich dich an {rem[0]['text']}.", rem[0]["text"]
    if not point:
        return None
    return await deliver(uid, "greet", f"Hallo {prof['name']}. {point}".strip(), why="Gespräch geöffnet", data=data)


# ---------------------------------------------------------------- 5: follow-up on a plan
# The model only points at a sentence; the panel checks it and says a fixed sentence with the person's own
# words (V01.0.385, Dominik 2026-10-11: "Hast du den Test für deine letzte E-Mail schon erledigt?" came from a
# request to the assistant, and the model's own question did not say where it came from).
FOLLOW_SYSTEM = (
    "Unten stehen Sätze, die eine Person gestern zu ihrem Sprachassistenten gesagt hat. Finde höchstens "
    "EIN konkretes Vorhaben, das die Person selbst erledigen wollte (etwas verschicken, anrufen, kaufen, "
    "reparieren, erledigen), bei dem eine freundliche Nachfrage heute passt. Keine Fragen oder Aufträge an "
    "den Assistenten, nichts zu Gesundheit, Gefühlen oder anderen Menschen Privates. Antworte nur mit "
    "JSON: {\"quote\": \"wörtlicher Ausschnitt aus genau einem der Sätze\"}. Gibt es nichts Passendes: {}.")
FOLLOW_SAY = "Gestern hast du zu mir gesagt: „{}“. Hat das geklappt?"
FOLLOW_LINE = 200      # a longer message is pasted or dictated text, not a plan said in passing
FOLLOW_QUOTE = 120
# the person's own plan: said in the first person ...
_OWN = re.compile(r"\b(ich|wir)\b")
# ... and not a request to the assistant: no question, no "du", no command at the start
_TO_YOU = re.compile(r"\b(du|dir|dich|dein|deine|deinen|deinem|deiner|deines|kannst|könntest|würdest|bitte)\b")
_ORDER = re.compile(r"^(sag|zeig|schreib|lies|such|mach|teste|test|prüf|pruef|schau|erinner|erzähl|nenn|gib|hol|leg|"
                    r"setz|trag|schick|ruf|öffne|starte|stell|spiel|lösch|merk|übersetz|fass|erklär|hilf|finde|check)\w*\b")


def own_plan(line):
    """True when a sentence of the person reads like their own plan, not like a request to the assistant
    (fixed rule; the model's pick alone is not enough)."""
    n = _norm(line)
    if not n or len(line) > FOLLOW_LINE or "\n" in line.strip() or n.rstrip(" .!").endswith("?"):
        return False
    return bool(_OWN.search(n)) and not _TO_YOU.search(n) and not _ORDER.match(n)


def follow_lines(convos, a, b):
    """The person's own short sentences from [a, b) (ms). Left out: questions an answer from mail or other
    outside text followed (those are about that text), and the Spark's own conversations (briefing, jobs,
    meetings: the user turn there is no sentence of the person)."""
    out = []
    for c in convos:
        if not a <= c.get("updated", 0) < b or str(c.get("id", "")).startswith(("brief-", "agent-", "meet-")):
            continue
        msgs = c.get("msgs", [])
        for i, m in enumerate(msgs):
            nxt = msgs[i + 1] if i + 1 < len(msgs) else {}
            if m.get("role") == "user" and not m.get("mail") and not nxt.get("mail") and not nxt.get("outside"):
                out.append(str(m.get("content") or "")[:FOLLOW_LINE + 1])
    return out[-40:]


def parse_follow(text, lines):
    """The model's pick, only when its quote really is in one of the person's sentences and that sentence is
    the person's own plan. Returns {"quote", "line", "question"} (question: the fixed sentence), or None."""
    text = no_think(text or "")
    m = re.search(r"(?s)\{.*\}", text)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    raw = re.sub(r"\s+", " ", str(d.get("quote") or "")).strip().strip("„“\"'").strip()
    quote = _norm(raw)
    if len(quote) < 10 or len(raw) > FOLLOW_QUOTE:
        return None
    line = next((x for x in lines if quote in _norm(x)), None)
    if line is None or not own_plan(line):
        return None
    return {"quote": raw, "line": line, "question": FOLLOW_SAY.format(raw.rstrip(" .!"))}


async def _llm(system, user, max_tokens=300):
    return await llm.complete(system, user[:12000], "Proaktiver Hinweis", max_tokens, ccfg=ccfg())


async def check_follow(uid, p, now):
    day = now.strftime("%Y-%m-%d")
    if state(uid).get("follow_day") == day or not 10 <= now.hour < 20 or not features.allowed("history", uid):
        return
    if blocked(uid, "follow", p, now):
        return
    _mut(uid, lambda st: st.update(follow_day=day))   # first: one try a day
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)
    a, b = start.timestamp() * 1000, (start + datetime.timedelta(days=1)).timestamp() * 1000
    lines = [x for x in follow_lines(profiles.convos(uid), a, b) if own_plan(x)]
    if not lines:
        return
    picked = await _llm(FOLLOW_SYSTEM, "\n".join("- " + x for x in lines))
    found = parse_follow(picked, lines)
    if not found and '"quote"' in picked:
        import live      # Zustand → Live: the panel's rule turned the model's pick down (no words of it)
        live.event("Von selbst", "Nachfrage verworfen: Zitat kein eigenes Vorhaben")
        print("proactive: follow pick refused (not an own plan in the person's words)", flush=True)
    if found:
        await deliver(uid, "follow", found["question"], why="Vorhaben von gestern",
                      data=f"am {start:%d.%m.} hast du gesagt: „{found['quote']}“")


# ---------------------------------------------------------------- 6: mail from chosen senders
# "Wichtige Mails erkennen" (pro_mail_smart, chat.systemone_mail): a mail from a sender not on the list counts
# when qwen38's /v1/systemone says yes to WICHTIG with at least systemone.WICHTIG_MIN, judged from sender and
# subject only (never the text); at most SMART_PER_CHECK such questions per check, only while nobody speaks
SMART_PER_CHECK = 5


def mail_smart(uid, p):
    return p.get("pro_mail_smart") is True and features.allowed("mailwichtig", uid)


async def important(h):
    """The probability that a mail is important to its reader, from its sender and subject; None when
    qwen38 cannot answer (asked again at the next check)."""
    import systemone
    await vorrang.quiet("Wichtige Mail", model=True)
    def one(v):     # a header stays one line of data
        return re.sub(r"\s+", " ", str(v or ""))[:300]
    state = f"Absender: {one(h['from'])}\nBetreff: {one(h['subject']) or '(ohne Betreff)'}"
    try:
        ans = await systemone.ask(ccfg(), "wichtig", state, systemone.wichtig_question(), timeout=20)
    except systemone.Unavailable:
        return None
    return ans["wichtig"]["yes"]


async def check_mail(uid, p):
    import mail
    import systemone
    senders = [s.strip().lower() for s in str(p.get("pro_mail_from", "")).split(",") if len(s.strip()) > 2]
    smart = mail_smart(uid, p)
    st = state(uid)
    if not (senders or smart) or not features.allowed("mail", uid) or not mail.get(uid)["accounts"]:
        return
    if time.time() - st.get("mail_checked", 0) < MAIL_EVERY - 5:
        return
    first = not st.get("mail_since")
    first_smart = smart and not st.get("mail_smart_since")
    now = time.time()
    _mut(uid, lambda s: s.update(mail_checked=now, mail_since=s.get("mail_since") or now,
                                 mail_smart_since=(s.get("mail_smart_since") or now) if smart else 0))
    if first:
        return      # only mails that come after switching it on
    since = st["mail_since"]
    smart_since = now if first_smart else st.get("mail_smart_since") or now
    found, _, _ = await asyncio.to_thread(mail.find, uid, "", 2, True, 20)
    seen = set(st.get("mail_seen", []))
    asked = 0
    for aid, u, h in reversed(found):
        key = f"{aid}:{u}"
        if key in seen or h["date"].timestamp() < since:
            continue
        why = "Absender auf deiner Liste" if any(s in h["from"].lower() for s in senders) else ""
        if not why:
            if not smart or h["date"].timestamp() < smart_since or asked >= SMART_PER_CHECK:
                continue
            asked += 1
            yes = await important(h)
            if yes is None:
                break       # busy or missing: these mails are asked about at the next check
            if yes < systemone.WICHTIG_MIN:
                seen.add(key)
                _mut(uid, lambda s, key=key: s.update(mail_seen=(s.get("mail_seen", []) + [key])[-200:]))
                continue
            why = f"Einordnung: wichtig ({int(round(yes * 100))} %)"
        seen.add(key)
        _mut(uid, lambda s, key=key: s.update(mail_seen=(s.get("mail_seen", []) + [key])[-200:]))
        who = h["from"].split(" <")[0].strip() or h["from"]
        import vorgaenge     # its card with Lesen and Antwort (Alles Offene im Assistenten, stage 3); the note carries it
        addr = h["from"].split("<")[-1].rstrip(">").strip() if "<" in h["from"] else h["from"]
        x, _ = vorgaenge.put(uid, "mail", f"mail:{key}", f"Wichtige Mail von {who}", h["subject"] or "ohne Betreff",
                             daten={"ref": key, "folder": "INBOX", "addr": addr, "subject": h["subject"] or ""})
        await deliver(uid, "mail", f"Neue Mail von {who}: {(h['subject'] or 'ohne Betreff')[:120]}.",
                      why=why, data=f"{h['from']}: {h['subject']}"[:300], mail=True, vg=x["id"] if x else None)


# ---------------------------------------------------------------- 8: weather for tomorrow
WEATHER_SYSTEM = (
    "Unten stehen Suchergebnisse zur Wettervorhersage für morgen. Prüfe nur, was dort ausdrücklich für "
    "morgen steht. Antworte nur mit JSON: {\"rain\": false, \"frost\": false, \"storm\": false, "
    "\"heat\": false, \"evidence\": \"wörtlicher Ausschnitt aus den Ergebnissen, der das belegt\"}. "
    "rain: Regen, Schauer oder Gewitter erwartet. frost: Tiefstwert unter 0 Grad. storm: Sturm oder "
    "Unwetterwarnung. heat: Höchstwert 30 Grad oder mehr. Steht nichts Eindeutiges da: alles false und "
    "evidence leer.")
WEATHER_SAY = {"rain": ("Regen", "Denk an einen Schirm."), "frost": ("Frost", "Empfindliche Pflanzen besser reinholen."),
               "storm": ("Sturm", "Lose Sachen draußen besser sichern."),
               "heat": ("Hitze", "Viel trinken und tagsüber die Rollläden zu.")}


def parse_weather(text, source):
    text = no_think(text or "")
    m = re.search(r"(?s)\{.*\}", text)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return []
    if not isinstance(d, dict):
        return []
    ev = _norm(d.get("evidence"))
    if len(ev) < 6 or ev not in _norm(source):
        return []
    return [k for k in WEATHER_SAY if d.get(k) is True]


WEATHER_RETRY = 600   # seconds until the next try after a passing failure of the weather service


async def check_weather(uid, p, now):
    import weather
    cc = ccfg()
    place = str(p.get("pro_place") or "").strip()
    at = re.fullmatch(r"(\d\d):(\d\d)", p.get("pro_weather_at") or "")
    day = now.strftime("%Y-%m-%d")
    direct = weather.usable(uid)   # the profile's own weather service: numbers, no search, no model
    st = state(uid)
    if not at or st.get("weather_day") == day or float(st.get("weather_wait") or 0) > time.time() or \
            (not direct and (not place or not cc.get("search_url") or not features.allowed("search", uid, cc))):
        return
    start = now.replace(hour=int(at[1]), minute=int(at[2]), second=0, microsecond=0)
    if not start <= now < start + datetime.timedelta(hours=2) or blocked(uid, "weather", p, now):
        return
    _mut(uid, lambda st: st.update(weather_day=day))
    if direct:
        try:
            text, kinds = await weather.notable_tomorrow(uid)
        except Exception as e:
            why = weather.passing(e)
            if not why:
                raise
            # the weather service is busy or briefly down (503, timeout): no error, try again within the time window
            _mut(uid, lambda st: st.update(weather_day="", weather_wait=time.time() + WEATHER_RETRY))
            print(f"proactive: weather: Open-Meteo {why}, retry in {WEATHER_RETRY // 60} min", flush=True)
            return
        if text:
            await deliver(uid, "weather", text + " " + " ".join(WEATHER_SAY[k][1] for k in kinds[:2]),
                          why="Wettervorhersage (Open-Meteo)", data=text)
        return
    from chat import web_search
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as c:
        source = (await web_search(c, dict(cc, search_pages=0, search_results=4), f"Wetter morgen {place}"))[0][:6000]
    kinds = parse_weather(await _llm(WEATHER_SYSTEM, f"Ort: {place}\n\n{source}"), source)
    if kinds:
        text = (f"Morgen in {place} laut Vorhersage: " + ", ".join(WEATHER_SAY[k][0] for k in kinds) + ". "
                + " ".join(WEATHER_SAY[k][1] for k in kinds[:2]))
        await deliver(uid, "weather", text, why=f"Wettervorhersage {place}", data=source[:600])


# ---------------------------------------------------------------- birthdays and parcels (contacts.py, parcels.py)
async def check_bday(uid, p, now):
    import contacts
    day = now.strftime("%Y-%m-%d")
    if not contacts.usable(uid) or state(uid).get("bday_day") == day or not 8 <= now.hour < 11 \
            or blocked(uid, "bday", p, now):
        return
    _mut(uid, lambda st: st.update(bday_day=day))
    names = [f"{n} (wird {a})" if a else n for _, n, a in contacts.birthdays(uid, now.date(), 1)]
    if names:
        await deliver(uid, "bday", "Heute hat Geburtstag: " + ", ".join(names) + ".", why="Geburtstag aus deinen Kontakten",
                      data=", ".join(names)[:300])


async def check_parcel(uid, p, now):
    import parcels
    st = state(uid)
    if not parcels.usable(uid) or not 7 <= now.hour < 20 or time.time() - st.get("parcel_checked", 0) < 1800:
        return
    _mut(uid, lambda s: s.update(parcel_checked=time.time()))
    day = now.strftime("%Y-%m-%d")
    seen = set(st.get("parcel_seen", []))
    for line in await asyncio.to_thread(parcels.today_lines, uid, now.date()):
        key = day + " " + line
        if key in seen or blocked(uid, "parcel", p, now):
            continue
        _mut(uid, lambda s, key=key: s.update(parcel_seen=(s.get("parcel_seen", []) + [key])[-50:]))
        await deliver(uid, "parcel", line, why="Versandmail in deinem Postfach", data=line[:300], mail=True)


FUER_EVERY = 1800
FUER_WAIT = 5


async def check_fuerdich(uid, p, now):
    """Für dich (fuerdich.due_notes): a bill or a cancelling deadline today or tomorrow and a suspected phishing mail,
    once per card, 8 am to 8 pm; from the last reading, read anew every FUER_EVERY or right after a new mail."""
    import fuerdich
    st = state(uid)
    fresh = fuerdich.wants_fresh(uid)
    if not fuerdich.usable(uid) or not 8 <= now.hour < 20 or blocked(uid, "fuerdich", p, now) or \
            (not fresh and time.time() - st.get("fuer_checked", 0) < FUER_EVERY):
        return
    try:    # the reading goes on behind a short wait; its result is in the cache at the next minute
        items, _ = await asyncio.wait_for(asyncio.shield(fuerdich._reading(uid, fresh)), FUER_WAIT)
    except Exception:
        return
    _mut(uid, lambda s: s.update(fuer_checked=time.time()))
    said = set(st.get("fuer_said", []))
    for k, why, text in fuerdich.due_notes(uid, items, now.date()):
        if k in said or blocked(uid, "fuerdich", p, now):
            continue
        _mut(uid, lambda s, k=k: s.update(fuer_said=(s.get("fuer_said", []) + [k])[-100:]))
        import vorgaenge   # with Offen on, the note is its card in today's conversation
        await deliver(uid, "fuerdich", text, why=f"Für dich: {why}", data=why, mail=True, ref=k,
                      vg=vorgaenge.id_of(uid, "fuerdich:" + k) if features.allowed("vorgaenge", uid) else None)


RUECK_DAY, RUECK_HOURS = 6, (18, 21)    # Sundays from 18 o'clock (6a), once per calendar week


async def check_rueckblick(uid, p, now):
    """Wochenrückblick (ichweiss.week_sentence): Sundays from 18 o'clock, once per ISO week; fixed sentence with numbers
    and the titles of the coming deadlines only."""
    import fuerdich
    import ichweiss
    st = state(uid)
    wk = "%d-%02d" % now.isocalendar()[:2]
    if now.weekday() != RUECK_DAY or not RUECK_HOURS[0] <= now.hour < RUECK_HOURS[1] or st.get("rueck_week") == wk or \
            not ichweiss.usable(uid) or blocked(uid, "rueckblick", p, now):
        return
    try:
        items, _ = await asyncio.wait_for(asyncio.shield(fuerdich._reading(uid)), FUER_WAIT)
    except Exception:
        return
    _mut(uid, lambda s: s.update(rueck_week=wk))
    w = ichweiss.week(uid, items, now.date())
    await deliver(uid, "rueckblick", ichweiss.week_sentence(w, now.date()), why="Wochenrückblick am Sonntag",
                  data="rueckblick", mail=True)


async def check_tips(uid, p, now):
    """One hint on a function that would help, at most once a week (tipps.py decides which), in the day only."""
    import tipps
    st = state(uid)
    if not 10 <= now.hour < 19 or time.time() - st.get("tipp_checked", 0) < 3600 or blocked(uid, "tipp", p, now):
        return
    _mut(uid, lambda s: s.update(tipp_checked=time.time()))
    text, _ = await asyncio.to_thread(tipps.weekly_text, uid)
    if text:
        await deliver(uid, "tipp", text, why="Vorschlag einer Funktion")


async def check_transit(uid, p, now):
    """The commute train late or cancelled: checked every 5 minutes from 45 to 5 minutes before, once a day."""
    import transit
    st = state(uid)
    c = transit.get(uid).get("commute")
    day = now.strftime("%Y-%m-%d")
    if not c or not transit.usable(uid) or now.weekday() not in c.get("days", []) or st.get("transit_day") == day \
            or time.time() - st.get("transit_checked", 0) < 300:
        return
    hh, mm = map(int, c["at"].split(":"))
    at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if not at - datetime.timedelta(minutes=45) <= now <= at - datetime.timedelta(minutes=5) or blocked(uid, "transit", p, now):
        return
    _mut(uid, lambda s: s.update(transit_checked=time.time()))
    note = await transit.commute_note(uid, now)
    if note:
        _mut(uid, lambda s: s.update(transit_day=day))
        await deliver(uid, "transit", note[0], why="Fahrplan für deine Pendelstrecke", data=note[1][:300])


# ---------------------------------------------------------------- the minute loop
async def due_once(now=None):
    """Called once a minute: every check for every profile that switched it on."""
    import hamelden
    try:
        await hamelden.ensure()      # the live connections to Home Assistant (started, ended, renewed)
    except Exception as e:
        print("proactive: ha live:", type(e).__name__, str(e)[:200], flush=True)
    if not enabled():
        return
    for uid in profiles.user_ids():
        p = prefs(uid)
        if not p.get("pro_on") or features.blocked("proactive", uid):
            continue
        local = now.astimezone(_zone(p)) if now else datetime.datetime.now(_zone(p))
        for name, fn in (("events", lambda: check_events(uid, p, local) if p.get("pro_events") else None),
                         ("ha", lambda: check_ha(uid, p) if p.get("pro_ha") else None),
                         ("mail", lambda: check_mail(uid, p) if p.get("pro_mail") else None),
                         ("follow", lambda: check_follow(uid, p, local) if p.get("pro_follow") else None),
                         ("weather", lambda: check_weather(uid, p, local) if p.get("pro_weather") else None),
                         ("bday", lambda: check_bday(uid, p, local) if p.get("pro_bday") else None),
                         ("parcel", lambda: check_parcel(uid, p, local) if p.get("pro_parcel") else None),
                         ("fuerdich", lambda: check_fuerdich(uid, p, local) if p.get("pro_fuerdich", True) else None),
                         ("rueckblick", lambda: check_rueckblick(uid, p, local) if p.get("pro_rueckblick", True) else None),
                         ("transit", lambda: check_transit(uid, p, local) if p.get("pro_transit") else None),
                         ("tipp", lambda: check_tips(uid, p, local) if p.get("pro_tips") else None)):
            try:
                job = fn()
                if job:
                    await job
            except Exception as e:
                print(f"proactive: {name}:", type(e).__name__, str(e)[:200], flush=True)


# ---------------------------------------------------------------- API
def _on(request: Request):
    if not enabled():
        raise HTTPException(403, "speaking up by itself is turned off")
    prof = profiles.current(request)
    if prof and features.blocked("proactive", prof["id"]):
        raise HTTPException(403, "blocked for this profile by the admin (Personen und Geräte → Gesperrte Funktionen)")


def status(uid):
    import calendars
    import contacts
    import parcels
    import transit
    import weather
    import feeds
    import fuerdich
    import ichweiss
    import homeassistant
    import hamelden
    import mail
    p, st = prefs(uid), state(uid)
    cc = ccfg()
    day = datetime.datetime.now(_zone(p)).strftime("%Y-%m-%d")
    per = st.get("per", {}) if st.get("day") == day else {}
    return {"enabled": enabled() and not features.blocked("proactive", uid, cc), "today": st.get("count", 0) if st.get("day") == day else 0,
            "paused_until": int(st.get("pause_until", 0)) if st.get("pause_until", 0) > time.time() else 0,
            "kinds": [{"kind": k, "label": v[0], "cap": cap(st, p, k), "full": v[1], "today": per.get(k, 0)}
                      for k, v in KINDS.items()],
            "rules": [dict(r, line=rule_line(r)) for r in rules(uid)],
            "ha": hamelden.status(uid),
            "speakers": hamelden.speakers(uid) if features.allowed("haloud", uid) else [],
            "has": {"calendar": bool(features.allowed("calendar", uid, cc) and calendars.get(uid)["calendars"]),
                    "ha": bool(features.allowed("ha", uid, cc) and homeassistant.get(uid)),
                    "mail": bool(features.allowed("mail", uid, cc) and mail.get(uid)["accounts"]),
                    "search": bool(cc.get("search_url") and features.allowed("search", uid, cc)),
                    "history": features.allowed("history", uid, cc), "reminders": features.allowed("reminders", uid, cc),
                    "weather": weather.usable(uid), "contacts": contacts.usable(uid), "parcels": parcels.usable(uid),
                    "fuerdich": fuerdich.usable(uid), "ichweiss": ichweiss.usable(uid),
                    "transit": bool(transit.usable(uid) and transit.get(uid).get("commute")),
                    "feeds": feeds.usable(uid)}}


@router.get("/api/proactive", dependencies=[Depends(assistant), Depends(_on)])
def api_poll(since: int = 0, prof=Depends(own_profile)):
    return {"items": poll(prof["id"], since)}


@router.post("/api/proactive/played", dependencies=[Depends(assistant), Depends(_on)])
async def api_played(request: Request, prof=Depends(own_profile)):
    """A device is about to say a note: only the first one gets "play" (the others stay silent)."""
    import guard
    guard.limit(request, "chat", prof["id"], False)
    body = await request.json()
    nid = str(body.get("id", "") if isinstance(body, dict) else "")[:16]
    if not re.fullmatch(r"[0-9a-f]{1,16}", nid):
        raise HTTPException(400, "id is required")
    return {"play": take(prof["id"], nid)}


@router.post("/api/proactive/greet", dependencies=[Depends(assistant), Depends(_on)])
async def api_greet(prof=Depends(own_profile)):
    _polled[prof["id"]] = time.time()
    item = await greet(prof["id"])
    return {"item": {k: item[k] for k in ("id", "t", "kind", "text")} if item else None}


@router.get("/api/proactive/status", dependencies=[Depends(assistant)])
def api_status(prof=Depends(own_profile)):
    return status(prof["id"])


@router.post("/api/proactive/feedback", dependencies=[Depends(assistant), Depends(_on)])
async def api_feedback(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    vote = body.get("vote")
    if vote not in ("less", "more", "reset", "pause", "resume"):
        raise HTTPException(400, "vote must be less, more, reset, pause or resume")
    return feedback(prof["id"], str(body.get("kind", "")), vote)


@router.post("/api/proactive/rules", dependencies=[Depends(assistant), Depends(_on)])
async def api_rule_add(request: Request, prof=Depends(browser_profile)):
    import guard
    guard.limit(request, "hamelden", prof["id"])
    body = await core.json_body(request, 8192)
    try:
        await add_rule(prof["id"], body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return status(prof["id"])     # a live connection takes the new rule's device with the next minute (hamelden.ensure)


MAX_DEVICES = 1500      # devices the rule form may pick from


def devices(all_states):
    """For the rule form: what the profile's Home Assistant token sees, last changed first. Only id, name,
    state and the time of the last change as HA wrote it (the browser compares it, no clock here)."""
    out = []
    for x in all_states:
        eid = str(x.get("entity_id", ""))
        if not re.fullmatch(r"[a-z0-9_]{1,40}\.[a-z0-9_]{1,120}", eid):
            continue
        name = str((x.get("attributes") or {}).get("friendly_name") or eid)
        out.append({"id": eid, "name": re.sub(r"[\x00-\x1f<>]", "", name)[:80],
                    "state": re.sub(r"[\x00-\x1f<>]", "", str(x.get("state", "")))[:40],
                    "lc": str(x.get("last_changed") or "")[:40]})
    out.sort(key=lambda d: d["lc"], reverse=True)
    return out[:MAX_DEVICES]


@router.get("/api/proactive/ha-devices", dependencies=[Depends(assistant), Depends(_on)])
async def api_devices(request: Request, prof=Depends(browser_profile)):
    """Devices to pick for a rule ("Zuletzt geändert", "Gerät erkennen" in Ich → Von selbst)."""
    import guard
    import homeassistant
    guard.limit(request, "hament", prof["id"])
    item = homeassistant.get(prof["id"]) if features.allowed("ha", prof["id"]) else None
    if not item:
        raise HTTPException(409, "Home Assistant ist nicht verbunden.")
    try:
        items = devices(await _all_states(item))
    except Exception as e:
        raise HTTPException(502, f"Home Assistant: {type(e).__name__}")
    return {"items": items}


@router.put("/api/proactive/rules/{rid}", dependencies=[Depends(assistant), Depends(_on)])
async def api_rule_change(rid: str, request: Request, prof=Depends(browser_profile)):
    """Change a rule in place (Ich → Von selbst → Bearbeiten): the same checks as adding one."""
    import guard
    guard.limit(request, "hamelden", prof["id"])
    if not re.fullmatch(r"[0-9a-f]{8}", rid):
        raise HTTPException(404, "no such rule")
    body = await core.json_body(request, 8192)
    try:
        await add_rule(prof["id"], body, replace=rid)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return status(prof["id"])


@router.delete("/api/proactive/rules/{rid}", dependencies=[Depends(assistant)])
def api_rule_remove(rid: str, prof=Depends(browser_profile)):
    remove_rule(prof["id"], rid)
    return status(prof["id"])


def _clear_rules(uid):
    for r in rules(uid):
        if isinstance(r, dict):
            remove_rule(uid, r.get("id"))


# own data for Ich while the admin blocks „Von selbst melden“ for the profile (features.OWN): its rules
features.OWN["proactive"] = (lambda uid: len(rules(uid)), _clear_rules)


@router.post("/api/proactive/test", dependencies=[Depends(assistant), Depends(_on)])
async def api_test(prof=Depends(own_profile)):
    """A sample note on the normal way (open page or push), outside every limit."""
    item = await deliver(prof["id"], "greet", "So melde ich mich, wenn etwas los ist.", why="Test", force=True)
    return {"item": item and {k: item[k] for k in ("id", "t", "kind", "text", "pushed") if k in item}}
