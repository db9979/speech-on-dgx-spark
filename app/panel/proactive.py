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

import profiles
import vorrang
import features
from common import load_config
from core import assistant, browser_profile, own_profile

router = APIRouter()

# kind: (label, at most per day before any feedback, setting that switches it)
# notes that hold nothing personal: these may also go to Telegram without tg_private (see telegram.py)
PUBLIC_KINDS = {"weather"}
KINDS = {"events": ("Termin-Vorlauf", 10, "pro_events"), "ha": ("Smart Home", 10, "pro_ha"),
         "greet": ("Begrüßung", 3, "pro_greet"), "follow": ("Nachfrage", 1, "pro_follow"),
         "mail": ("Wichtige Mail", 10, "pro_mail"), "weather": ("Wetter", 1, "pro_weather"),
         "tidy": ("Postfach aufräumen", 2, "pro_tidy"), "bday": ("Geburtstag", 1, "pro_bday"),
         "parcel": ("Paket kommt heute", 3, "pro_parcel"), "transit": ("Bus und Bahn", 1, "pro_transit")}
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


async def deliver(uid, kind, text, why="", data="", offer=None, until=None, force=False, mail=False):
    """Says text to the profile (open page, else push) unless something blocks it; logs it in the
    profile's tool log. Returns the item, or None."""
    p = prefs(uid)
    local = datetime.datetime.now(_zone(p))
    text = re.sub(r"\s+", " ", str(text)).strip()[:400]
    reason = "" if force else blocked(uid, kind, p, local)
    if reason or not text:
        print(f"proactive: {kind} not said ({reason or 'empty'}): {text[:80]!r}", flush=True)
        return None
    import push
    now = time.time()
    page = now - _polled.get(uid, 0) < PAGE_ACTIVE
    item = {"id": secrets.token_hex(6), "t": int(now * 1000), "kind": kind, "text": text,
            "until": int(until or now + QUEUE_KEEP)}
    if mail:
        item["mail"] = True    # kept out of what the learner reads, like answers made from mail
    private = kind not in PUBLIC_KINDS
    if not page and push.reachable(uid, private):
        item["pushed"] = True

    def put(st):
        _today(st, local.strftime("%Y-%m-%d"))
        st["count"] = st.get("count", 0) + (0 if force else 1)
        st.setdefault("per", {})[kind] = st["per"].get(kind, 0) + (0 if force else 1)
        st["last"] = {"t": now, "kind": kind, "offer": offer, "text": text}
        st["queue"] = [x for x in st.get("queue", []) if x.get("until", 0) > now][-19:] + [item]
    _mut(uid, put)
    if item.get("pushed"):
        try:
            await push.send(uid, "💬 Spark", text, tag="pro-" + kind, private=private)
        except Exception as e:
            print("proactive: push:", type(e).__name__, e, flush=True)
    profiles.tool_log_add(uid, f"(von selbst: {KINDS[kind][0]})",
                          [{"name": "von selbst: " + kind, "args": why, "result": data or text}], text)
    print(f"proactive: {kind} said ({'push' if item.get('pushed') else 'page'})", flush=True)
    return item


def poll(uid, since=0):
    """Notes for the open page since a time (ms); also marks the page as open. A note one device
    already played is left out (V01.0.179: said once, not on every device of the profile)."""
    _polled[uid] = time.time()
    now = time.time()
    return [{k: x[k] for k in ("id", "t", "kind", "text", "mail") if k in x}
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
    if not ccfg().get("calendar", True) or not calendars.get(uid)["calendars"]:
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
        if mins > 10 and ccfg().get("reminders", True):
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


async def add_rule(uid, body, src=""):
    """Checks a rule against what Home Assistant has and stores it. body: {"conds": [{entity, op, value,
    when}], "minutes", "text", "pause", "only", "loud", "speakers", "camera"}; src "voice" for a rule made by
    voice (hamelden.py, after a yes)."""
    import homeassistant
    import hamelden
    item = homeassistant.get(uid)
    if not item:
        raise ValueError("Home Assistant ist nicht verbunden.")
    have = rules(uid)
    if len(have) >= MAX_RULES:
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
    item = homeassistant.get(uid) if rs and ccfg().get("homeassistant", False) else None
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
        if not conds:
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
    if ccfg().get("calendar", True) and calendars.get(uid)["calendars"]:
        try:
            res = await calendars.events(uid, now, now + datetime.timedelta(hours=4), zone)
            nxt = next((x for x in (res or ([], []))[0] if not x["allday"] and x["start"] > now), None)
            if nxt:
                point, data = f"Um {nxt['start']:%H:%M} Uhr hast du {nxt['title']}.", calendars.line(nxt)
        except Exception as e:
            print("proactive: greet calendar:", type(e).__name__, e, flush=True)
    if not point and ccfg().get("reminders", True):
        end = now.replace(hour=23, minute=59).timestamp() * 1000
        rem = [x for x in profiles.reminders(uid) if now.timestamp() * 1000 < x["due"] <= end]
        if rem:
            when = datetime.datetime.fromtimestamp(rem[0]["due"] / 1000, zone)
            point, data = f"Heute um {when:%H:%M} Uhr erinnere ich dich an {rem[0]['text']}.", rem[0]["text"]
    if not point:
        return None
    return await deliver(uid, "greet", f"Hallo {prof['name']}. {point}".strip(), why="Gespräch geöffnet", data=data)


# ---------------------------------------------------------------- 5: follow-up on a plan
FOLLOW_SYSTEM = (
    "Unten stehen Sätze, die eine Person gestern zu ihrem Sprachassistenten gesagt hat. Finde höchstens "
    "EIN konkretes Vorhaben, das die Person selbst erledigen wollte (etwas verschicken, anrufen, kaufen, "
    "reparieren, erledigen), bei dem eine freundliche Nachfrage heute passt. Keine Fragen oder Aufträge an "
    "den Assistenten, nichts zu Gesundheit, Gefühlen oder anderen Menschen Privates. Antworte nur mit "
    "JSON: {\"quote\": \"wörtlicher Ausschnitt aus genau einem der Sätze\", \"question\": \"eine kurze "
    "Nachfrage in Du-Form, ein Satz mit Fragezeichen\"}. Gibt es nichts Passendes: {}.")


def parse_follow(text, lines):
    """The model's proposal, only when its quote really is in one of the person's sentences."""
    text = re.sub(r"(?s)<think>.*?</think>", "", text or "")
    m = re.search(r"(?s)\{.*\}", text)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    quote, question = _norm(d.get("quote")), re.sub(r"\s+", " ", str(d.get("question") or "")).strip()
    if len(quote) < 10 or not question.endswith("?") or len(question) > 200:
        return None
    if not any(quote in _norm(x) for x in lines):
        return None
    return {"quote": d["quote"].strip(), "question": question}


async def _llm(system, user, max_tokens=300):
    from chat import llm_model
    cc = ccfg()
    headers = {"Authorization": f"Bearer {cc['llm_key']}"} if cc.get("llm_key") else {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
        payload = {"model": await llm_model(c, cc, headers), "temperature": 0.1, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user[:12000]}],
                   "chat_template_kwargs": {"enable_thinking": False}}
        r = await vorrang.post(c, "Proaktiver Hinweis", cc["llm_url"].rstrip("/") + "/chat/completions",
                               json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"].get("content") or ""


async def check_follow(uid, p, now):
    day = now.strftime("%Y-%m-%d")
    if state(uid).get("follow_day") == day or not 10 <= now.hour < 20 or not ccfg().get("history", True):
        return
    if blocked(uid, "follow", p, now):
        return
    _mut(uid, lambda st: st.update(follow_day=day))   # first: one try a day
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)
    a, b = start.timestamp() * 1000, (start + datetime.timedelta(days=1)).timestamp() * 1000
    lines = [m["content"][:300] for c in profiles.convos(uid) if a <= c.get("updated", 0) < b
             for m in c.get("msgs", []) if m["role"] == "user" and not m.get("mail")][-40:]
    if not lines:
        return
    found = parse_follow(await _llm(FOLLOW_SYSTEM, "\n".join("- " + x for x in lines)), lines)
    if found:
        await deliver(uid, "follow", found["question"], why="Vorhaben von gestern", data=f"gestern gesagt: „{found['quote']}“")


# ---------------------------------------------------------------- 6: mail from chosen senders
async def check_mail(uid, p):
    import mail
    senders = [s.strip().lower() for s in str(p.get("pro_mail_from", "")).split(",") if len(s.strip()) > 2]
    st = state(uid)
    if not senders or not ccfg().get("mail", False) or not mail.get(uid)["accounts"]:
        return
    if time.time() - st.get("mail_checked", 0) < MAIL_EVERY - 5:
        return
    first = not st.get("mail_since")
    _mut(uid, lambda s: s.update(mail_checked=time.time(), mail_since=s.get("mail_since") or time.time()))
    if first:
        return      # only mails that come after switching it on
    since = st["mail_since"]
    found, _, _ = await asyncio.to_thread(mail.find, uid, "", 2, True, 20)
    seen = set(st.get("mail_seen", []))
    for aid, u, h in reversed(found):
        key = f"{aid}:{u}"
        if key in seen or h["date"].timestamp() < since or not any(s in h["from"].lower() for s in senders):
            continue
        seen.add(key)
        _mut(uid, lambda s, key=key: s.update(mail_seen=(s.get("mail_seen", []) + [key])[-200:]))
        who = h["from"].split(" <")[0].strip() or h["from"]
        await deliver(uid, "mail", f"Neue Mail von {who}: {(h['subject'] or 'ohne Betreff')[:120]}.",
                      why="Absender auf deiner Liste", data=f"{h['from']}: {h['subject']}"[:300], mail=True)


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
    text = re.sub(r"(?s)<think>.*?</think>", "", text or "")
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
            (not direct and (not place or not cc.get("search") or not cc.get("search_url"))):
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
        if not p.get("pro_on"):
            continue
        local = now.astimezone(_zone(p)) if now else datetime.datetime.now(_zone(p))
        for name, fn in (("events", lambda: check_events(uid, p, local) if p.get("pro_events") else None),
                         ("ha", lambda: check_ha(uid, p) if p.get("pro_ha") else None),
                         ("mail", lambda: check_mail(uid, p) if p.get("pro_mail") else None),
                         ("follow", lambda: check_follow(uid, p, local) if p.get("pro_follow") else None),
                         ("weather", lambda: check_weather(uid, p, local) if p.get("pro_weather") else None),
                         ("bday", lambda: check_bday(uid, p, local) if p.get("pro_bday") else None),
                         ("parcel", lambda: check_parcel(uid, p, local) if p.get("pro_parcel") else None),
                         ("transit", lambda: check_transit(uid, p, local) if p.get("pro_transit") else None)):
            try:
                job = fn()
                if job:
                    await job
            except Exception as e:
                print(f"proactive: {name}:", type(e).__name__, str(e)[:200], flush=True)


# ---------------------------------------------------------------- API
def _on():
    if not enabled():
        raise HTTPException(403, "speaking up by itself is turned off")


def status(uid):
    import calendars
    import contacts
    import parcels
    import transit
    import weather
    import homeassistant
    import hamelden
    import mail
    p, st = prefs(uid), state(uid)
    cc = ccfg()
    day = datetime.datetime.now(_zone(p)).strftime("%Y-%m-%d")
    per = st.get("per", {}) if st.get("day") == day else {}
    return {"enabled": enabled(), "today": st.get("count", 0) if st.get("day") == day else 0,
            "paused_until": int(st.get("pause_until", 0)) if st.get("pause_until", 0) > time.time() else 0,
            "kinds": [{"kind": k, "label": v[0], "cap": cap(st, p, k), "full": v[1], "today": per.get(k, 0)}
                      for k, v in KINDS.items()],
            "rules": [dict(r, line=rule_line(r)) for r in rules(uid)],
            "ha": hamelden.status(uid),
            "speakers": hamelden.speakers(uid) if features.allowed("haloud", uid) else [],
            "has": {"calendar": bool(cc.get("calendar", True) and calendars.get(uid)["calendars"]),
                    "ha": bool(cc.get("homeassistant", False) and homeassistant.get(uid)),
                    "mail": bool(cc.get("mail", False) and mail.get(uid)["accounts"]),
                    "search": bool(cc.get("search") and cc.get("search_url")),
                    "history": bool(cc.get("history", True)), "reminders": bool(cc.get("reminders", True)),
                    "weather": weather.usable(uid), "contacts": contacts.usable(uid), "parcels": parcels.usable(uid),
                    "transit": bool(transit.usable(uid) and transit.get(uid).get("commute"))}}


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
    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    try:
        await add_rule(prof["id"], body if isinstance(body, dict) else {})
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
    item = homeassistant.get(prof["id"]) if ccfg().get("homeassistant", False) else None
    if not item:
        raise HTTPException(409, "Home Assistant ist nicht verbunden.")
    try:
        items = devices(await _all_states(item))
    except Exception as e:
        raise HTTPException(502, f"Home Assistant: {type(e).__name__}")
    return {"items": items}


@router.delete("/api/proactive/rules/{rid}", dependencies=[Depends(assistant)])
def api_rule_remove(rid: str, prof=Depends(browser_profile)):
    remove_rule(prof["id"], rid)
    return status(prof["id"])


@router.post("/api/proactive/test", dependencies=[Depends(assistant), Depends(_on)])
async def api_test(prof=Depends(own_profile)):
    """A sample note on the normal way (open page or push), outside every limit."""
    item = await deliver(prof["id"], "greet", "So melde ich mich, wenn etwas los ist.", why="Test", force=True)
    return {"item": item and {k: item[k] for k in ("id", "t", "kind", "text", "pushed") if k in item}}
