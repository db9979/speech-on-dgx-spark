"""User profiles for the assistant: who is talking, and what the assistant remembers about them.

Every profile has its own folder; nothing in one profile is reachable from another. The profile of
a request comes only from its login cookie or its device key, never from anything the LLM says.

    USERS_DIR/profiles.json   {"users": [...], "devices": [...]}
    USERS_DIR/secret          signs the login cookies
    USERS_DIR/seen.json       when and from where each device key was last used
    USERS_DIR/<user id>/memory.json   [{"id", "text", "created"}]
    USERS_DIR/<user id>/settings.json {conversation settings, see SETTINGS}
    USERS_DIR/<user id>/convos.json   [{"id", "title", "updated", "msgs": [{"role", "content"}]}]
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time

USERS_DIR = os.environ.get("SPEECH_SPARK_USERS", "/var/lib/speech-spark/users")
COOKIE = "speech_spark_user"
DEVICE_HEADER = "x-speech-device"
MAX_FACTS, MAX_FACT_LEN = 200, 300
_lock = threading.Lock()


def _path(*parts):
    return os.path.join(USERS_DIR, *parts)


def _write(path, data):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _load():
    try:
        with open(_path("profiles.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {"users": d.get("users", []), "devices": d.get("devices", [])}


def _secret():
    p = _path("secret")
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        os.makedirs(USERS_DIR, mode=0o700, exist_ok=True)
        s = secrets.token_bytes(32)
        with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(s)
        return s


def _pin_hash(pin, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def _pin_ok(pin, stored):
    salt, _, _ = stored.partition("$")
    return secrets.compare_digest(_pin_hash(pin, salt), stored)


def valid_name(name):
    return isinstance(name, str) and 1 <= len(name.strip()) <= 40 and not re.search(r"[<>\"\\\n]", name)


def valid_pin(pin):
    return isinstance(pin, str) and re.fullmatch(r"\S{4,64}", pin) is not None


# ---------------------------------------------------------------- profiles
def user_ids():
    return [u["id"] for u in _load()["users"]]


def admin_list():
    d = _load()
    users = [{"id": u["id"], "name": u["name"], "created": u.get("created"), "facts": len(memory(u["id"]))}
             for u in d["users"]]
    last = seen()
    devices = [dict({k: v[k] for k in ("id", "name", "user", "created") if k in v}, last=last.get(v["id"]),
                    app=v.get("scope") == "app") for v in d["devices"]]
    return {"users": users, "devices": devices}


def add_user(name, pin):
    with _lock:
        d = _load()
        if any(u["name"].lower() == name.strip().lower() for u in d["users"]):
            raise ValueError("a profile with this name exists")
        u = {"id": "u_" + secrets.token_hex(6), "name": name.strip(), "pin": _pin_hash(pin), "created": int(time.time())}
        d["users"].append(u)
        _write(_path("profiles.json"), d)
        return u["id"]


def set_pin(uid, pin):
    with _lock:
        d = _load()
        for u in d["users"]:
            if u["id"] == uid:
                u["pin"] = _pin_hash(pin)  # also ends the logins made with the old PIN
                _write(_path("profiles.json"), d)
                return True
        return False


def delete_user(uid):
    with _lock:
        d = _load()
        d["users"] = [u for u in d["users"] if u["id"] != uid]
        d["devices"] = [x for x in d["devices"] if x.get("user") != uid]
        _write(_path("profiles.json"), d)
        folder = _path(uid)
        if re.fullmatch(r"u_[0-9a-f]{12}", uid) and os.path.isdir(folder):
            shutil.rmtree(folder)


# ---------------------------------------------------------------- devices (speakers, scripts)
def add_device(name, uid, scope=None):
    """scope "app": a key of the iPhone app, good only for APP_PATHS (see current)."""
    with _lock:
        d = _load()
        if not any(u["id"] == uid for u in d["users"]):
            raise ValueError("no such profile")
        token = "sd_" + secrets.token_urlsafe(24)
        d["devices"].append(dict({"id": "d_" + secrets.token_hex(6), "name": name.strip(), "user": uid,
                                  "token": hashlib.sha256(token.encode()).hexdigest(), "created": int(time.time())},
                                 **({"scope": scope} if scope else {})))
        _write(_path("profiles.json"), d)
        return token  # shown once; only its hash is stored


def set_device_user(did, uid):
    with _lock:
        d = _load()
        if not any(u["id"] == uid for u in d["users"]):
            return False
        for x in d["devices"]:
            if x["id"] == did:
                x["user"] = uid
                _write(_path("profiles.json"), d)
                return True
        return False


def delete_device(did):
    with _lock:
        d = _load()
        d["devices"] = [x for x in d["devices"] if x["id"] != did]
        _write(_path("profiles.json"), d)


# ---------------------------------------------------------------- who is asking
# A browser login is "<user id>.<issued>.<signature>". It ends after SESSION_DAYS without use (the
# panel renews it while it is used), when the PIN changes, or with "log out everywhere" (epoch).
SESSION_DAYS = 90
RENEW_AFTER = 86400


def _sign(u, issued):
    msg = f"{u['id']}|{u['pin']}|{u.get('epoch', 0)}|{issued}"
    return hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()


def _cookie_value(u, issued=None):
    issued = int(issued or time.time())
    return f"{u['id']}.{issued}.{_sign(u, issued)}"


def login(name, pin):
    """Returns the cookie value, or None for an unknown name or a wrong PIN (indistinguishable)."""
    name = str(name).strip().lower()
    u = next((u for u in _load()["users"] if u["name"].lower() == name), None)
    if u and _pin_ok(pin, u["pin"]):
        return _cookie_value(u)
    if not u:
        _pin_hash(pin)  # same work as a wrong PIN, so timing does not reveal which names exist
    return None


def by_id(uid):
    u = next((u for u in _load()["users"] if u["id"] == uid), None)
    return {"id": u["id"], "name": u["name"]} if u else None


def _cookie_user(d, raw):
    """(user, issued) of a valid browser login, else (None, 0)."""
    parts = raw.split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        return None, 0
    uid, issued, sig = parts[0], int(parts[1]), parts[2]
    u = next((u for u in d["users"] if u["id"] == uid), None)
    if not u or time.time() - issued > SESSION_DAYS * 86400 or not secrets.compare_digest(sig, _sign(u, issued)):
        return None, 0
    import guard
    if guard.revoked(raw):
        return None, 0
    return u, issued


def renewed_cookie(request):
    """A fresh cookie value when this request's login is valid and older than a day, else None."""
    d = _load()
    u, issued = _cookie_user(d, request.cookies.get(COOKIE, ""))
    if u and time.time() - issued > RENEW_AFTER and not request.headers.get(DEVICE_HEADER):
        return _cookie_value(u)
    return None


def end_sessions(uid):
    """Logs this profile out in every browser (device keys stay)."""
    with _lock:
        d = _load()
        for u in d["users"]:
            if u["id"] == uid:
                u["epoch"] = int(u.get("epoch", 0)) + 1
                _write(_path("profiles.json"), d)
                return True
        return False


# last use of each device key: kept in memory, written at most every SEEN_EVERY seconds
SEEN_EVERY = 600
_seen, _seen_written = {}, [0.0]


def _note_device(did, request):
    now = time.time()
    ip = request.client.host if getattr(request, "client", None) else ""
    _seen[did] = {"t": int(now), "ip": ip}
    if now - _seen_written[0] > SEEN_EVERY:
        _seen_written[0] = now
        try:
            with _lock:
                _write(_path("seen.json"), dict(seen(), **_seen))
        except OSError:
            pass


def seen():
    """{device id: {"t", "ip"}}: when and from where each device key was last used."""
    try:
        with open(_path("seen.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return dict(d if isinstance(d, dict) else {}, **_seen)


# A key of the iPhone app (scope "app") only asks and listens: these paths and nothing else, and only
# while the admin and the profile have the app switched on (APP_GATE, set by iphone.py; closed without it).
APP_PATHS = ("/api/chat", "/api/test/asr", "/api/siri/ask", "/api/iphone/hello", "/api/profile/reminders",
             "/api/profile/reminders/played",   # a due reminder rings once: the first device takes it
             "/api/proactive", "/api/proactive/greet", "/api/proactive/played", "/api/assistant/say",
             "/api/iphone/push-token", "/api/iphone/note",
             "/api/profile/convos",   # the conversations, the same list as in the panel
             "/api/iphone/doc",       # a document's text into the profile's documents (app_docs)
             "/api/chat/image",       # a picture for the next question (app_images, images.py)
             "/api/iphone/settings",  # the profile's own voice, answers and "Von selbst" (iphone.APP_FIELDS only)
             "/api/assistant/voices",  # the voice names to choose from
             # Apple Reminders on the iPhone (app_ios): new list entries to the iPhone, adding from Shortcuts
             "/api/tasks/inbox", "/api/profile/tasks/einkauf", "/api/profile/tasks/aufgaben",
             # Spark updates (appupdate.py): rights only from the admin, starting needs a fresh code
             "/api/iphone/update",
             # messages between profiles (messages.py; who may write to me stays in the browser)
             "/api/messages", "/api/messages/poll", "/api/messages/send", "/api/messages/voice",
             "/api/messages/announce", "/api/messages/played", "/api/messages/read", "/api/messages/delete",
             "/api/messages/audio")
APP_GATE = [lambda uid: False]


def _device(d, request):
    token = request.headers.get(DEVICE_HEADER, "")
    if not token:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    return next((x for x in d["devices"] if secrets.compare_digest(x["token"], h)), None)


def device(request):
    """The device entry behind this request's key (id, user, scope), or None for logins."""
    if request.scope.get("speech_profile"):
        return None
    dev = _device(_load(), request)
    return {"id": dev["id"], "user": dev["user"], "scope": dev.get("scope") or ""} if dev else None


def key_scope(request):
    """The scope of the device key this request carries ("app"), "" for other keys and logins."""
    if request.scope.get("speech_profile"):
        return ""
    dev = _device(_load(), request)
    return str(dev.get("scope") or "") if dev else ""


# uid -> (kind, key, time) of the device the profile used last: "app" (iPhone app), "tg" (Telegram),
# "web" (a panel page; key = its push subscription, see push.page_open). Push goes only there (push.pick).
LAST_USED = {}


def used(uid, kind, key=""):
    if len(LAST_USED) > 1000:
        LAST_USED.clear()
    LAST_USED[uid] = (kind, key, time.time())


def current(request):
    """{"id", "name"} of the profile behind this request (device key first, then cookie), or None."""
    d = _load()
    inner = request.scope.get("speech_profile")   # set only by the panel itself (Telegram, see telegram.py)
    if inner:
        used(inner, "tg")
        u = next((u for u in d["users"] if u["id"] == inner), None)
        return {"id": u["id"], "name": u["name"]} if u else None
    token = request.headers.get(DEVICE_HEADER, "")
    if token:
        dev = _device(d, request)
        if not dev:
            return None
        if dev.get("scope") == "app" and (request.scope.get("path") not in APP_PATHS or not APP_GATE[0](dev["user"])):
            return None
        _note_device(dev["id"], request)
        uid = dev["user"]
        if dev.get("scope") == "app":
            used(uid, "app")
    else:
        u, _ = _cookie_user(d, request.cookies.get(COOKIE, ""))
        if not u:
            return None
        uid = u["id"]
    u = next((u for u in d["users"] if u["id"] == uid), None)
    return {"id": u["id"], "name": u["name"]} if u else None


def own_devices(uid):
    last = seen()
    return [{"id": x["id"], "name": x["name"], "created": x.get("created"), "last": last.get(x["id"]),
             "app": x.get("scope") == "app"} for x in _load()["devices"] if x.get("user") == uid]


# ---------------------------------------------------------------- conversation settings
# key: (default, check). The admin's defaults (config chat.defaults) apply where a profile has
# set nothing; guests keep theirs in the browser.
SETTINGS = {
    "hands": (False, lambda v: isinstance(v, bool)),
    "auto": (True, lambda v: isinstance(v, bool)),
    # follow-up without the wake word: seconds the microphone stays open after an answer (admin chat.follow_up)
    "follow": ("0", lambda v: v in ("0", "4", "6", "8", "10")),
    # the Spark's own voice from another device is no question (admin chat.no_self_echo, echo.py)
    "echo": (True, lambda v: isinstance(v, bool)),
    "daily": (True, lambda v: isinstance(v, bool)),
    "turn": (True, lambda v: isinstance(v, bool)),
    "live": (True, lambda v: isinstance(v, bool)),
    "barge": (True, lambda v: isinstance(v, bool)),
    "barge_level": ("mid", lambda v: v in ("low", "mid", "high")),
    "voice": ("", lambda v: isinstance(v, str) and len(v) <= 64 and re.fullmatch(r"[\w .\-]*", v)),
    "speed": (1.0, lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0.7 <= v <= 1.4),
    "length": ("normal", lambda v: v in ("short", "normal", "long")),
    "timing": (True, lambda v: isinstance(v, bool)),
    "learn": (True, lambda v: isinstance(v, bool)),
    "tool_think": (False, lambda v: isinstance(v, bool)),   # think while choosing a tool (admin chat.tool_thinking)
    "fix_learn": (False, lambda v: isinstance(v, bool)),    # learning from corrections (fixes.py, admin chat.learn_fixes)
    "images_on": (False, lambda v: isinstance(v, bool)),    # pictures for the model (images.py, admin chat.images)
    # own wishes for the tone (admin chat.own_style): plain text, no control characters, no markers of outside text
    "style": ("", lambda v: isinstance(v, str) and len(v) <= 500 and not re.search(r"[\x00-\x09\x0b-\x1f\x7f]|<<<|>>>", v)),
    # daily briefing as a push notification at this local time ("" = off), in the device's time zone
    "briefing_at": ("", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d|", v)),
    "tz": ("", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+){0,2})?", v)),
    # speaking up by itself (see proactive.py): off until the person switches it on, each kind on its own
    "pro_on": (False, lambda v: isinstance(v, bool)),
    "pro_quiet": ("22:00-07:00", lambda v: isinstance(v, str) and re.fullmatch(r"(?:(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d)?", v)),
    "pro_max": (6, lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 30),
    "pro_events": (True, lambda v: isinstance(v, bool)),
    "pro_lead": (20, lambda v: v in (5, 10, 15, 20, 30, 45, 60)),
    "pro_ha": (True, lambda v: isinstance(v, bool)),
    "pro_greet": (True, lambda v: isinstance(v, bool)),
    "pro_follow": (True, lambda v: isinstance(v, bool)),
    "pro_mail": (True, lambda v: isinstance(v, bool)),
    "pro_tidy": (True, lambda v: isinstance(v, bool)),
    "pro_mail_from": ("", lambda v: isinstance(v, str) and len(v) <= 300 and "\n" not in v),
    "pro_weather": (True, lambda v: isinstance(v, bool)),
    "pro_place": ("", lambda v: isinstance(v, str) and len(v) <= 60 and re.fullmatch(r"[^<>\"\\\n]*", v)),
    "pro_weather_at": ("18:00", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", v)),
    "pro_learn": (True, lambda v: isinstance(v, bool)),
    # weather, contacts, parcels (see weather.py, contacts.py, parcels.py): each profile switches them on itself
    "wx_on": (False, lambda v: isinstance(v, bool)),
    "con_on": (False, lambda v: isinstance(v, bool)),
    "con_bday": (True, lambda v: isinstance(v, bool)),
    "par_on": (False, lambda v: isinstance(v, bool)),
    "pro_bday": (True, lambda v: isinstance(v, bool)),
    "pro_parcel": (True, lambda v: isinstance(v, bool)),
    "tasks_on": (False, lambda v: isinstance(v, bool)),
    "transit_on": (False, lambda v: isinstance(v, bool)),   # Bus und Bahn (transit.py)
    "pro_transit": (True, lambda v: isinstance(v, bool)),   # shopping and to-do list (tasks.py)
    # Telegram (see telegram.py): what this profile allows over Telegram, all off until it says so
    "tg_voice": (False, lambda v: isinstance(v, bool)),
    "tg_private": (False, lambda v: isinstance(v, bool)),
    "tg_ha": (False, lambda v: isinstance(v, bool)),
    "tg_push": (False, lambda v: isinstance(v, bool)),
    "tg_images": (False, lambda v: isinstance(v, bool)),    # photos sent to the bot go to the model (images.py)
    "esp_on": (False, lambda v: isinstance(v, bool)),   # own ESP32 speakers (esp32.py)
    # iPhone app (iphone.py): pairing for this profile, and switching the smart home from it, both off
    "app_on": (False, lambda v: isinstance(v, bool)),
    "app_ha": (False, lambda v: isinstance(v, bool)),
    "app_listen": (False, lambda v: isinstance(v, bool)),   # listening all the time for the wake word
    "app_act": (False, lambda v: isinstance(v, bool)),      # routes and calls on the iPhone (iphone_action)
    "app_push": (False, lambda v: isinstance(v, bool)),     # notes as Apple push to the closed app (apns.py)
    "app_car_ha": (False, lambda v: isinstance(v, bool)),   # smart home from CarPlay
    "app_docs": (False, lambda v: isinstance(v, bool)),     # documents from the app into "Meine Dokumente"
    "app_ios": (False, lambda v: isinstance(v, bool)),      # Apple Reminders and the lists on the iPhone (tasks.py)
    "app_images": (False, lambda v: isinstance(v, bool)),   # pictures from the app to the model (images.py)
    # agent functions (agent.py): the admin gives the level, the profile switches it on itself
    "agent_on": (False, lambda v: isinstance(v, bool)),
    "agent_doc": (False, lambda v: isinstance(v, bool)),    # every report also under "Meine Dokumente"
    # messages between profiles (messages.py): off until the profile switches them on
    "msg_on": (False, lambda v: isinstance(v, bool)),
    "msg_from": ("all", lambda v: v in ("all", "chosen")),   # every profile, or only the ones picked
    "msg_all": (True, lambda v: isinstance(v, bool)),        # also messages "an alle"
    "msg_speaker": ("off", lambda v: v in ("off", "hint", "text")),   # say new ones on my speakers
    "msg_announce": (False, lambda v: isinstance(v, bool)),  # announcements of others on my speakers
}


def clean_settings(d):
    """Only known keys with valid values."""
    d = d if isinstance(d, dict) else {}
    return {k: d[k] for k, (_, ok) in SETTINGS.items() if k in d and ok(d[k])}


def defaults(admin=None):
    own = {k: v for k, v in clean_settings(admin).items() if k != "style"}  # the tone is the profile's own
    return dict({k: v for k, (v, _) in SETTINGS.items()}, **own)


def settings(uid):
    try:
        with open(_path(uid, "settings.json")) as f:
            return clean_settings(json.load(f))
    except (OSError, ValueError):
        return {}


def save_settings(uid, d):
    with _lock:
        merged = dict(settings(uid), **clean_settings(d))
        _write(_path(uid, "settings.json"), merged)
    return merged


# ---------------------------------------------------------------- conversations
MAX_CONVOS, MAX_MSGS, MAX_MSG_LEN = 50, 60, 20000


def convos(uid):
    try:
        with open(_path(uid, "convos.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_convo(uid, c):
    """Adds or replaces one conversation (newest first); returns it, or None if invalid."""
    cid = str(c.get("id", ""))
    if not re.fullmatch(r"[\w\-]{1,40}", cid) or not isinstance(c.get("msgs"), list):
        return None
    # "mail": an answer made from e-mails (kept out of what the background learner reads)
    msgs = [dict({"role": m["role"], "content": str(m["content"])[:MAX_MSG_LEN]}, **({"mail": True} if m.get("mail") else {}),
                 **({"outside": True} if m.get("outside") and not m.get("mail") else {}))
            for m in c["msgs"][-MAX_MSGS:]
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    item = {"id": cid, "title": str(c.get("title", ""))[:80], "msgs": msgs,
            "updated": int(c["updated"]) if isinstance(c.get("updated"), (int, float)) else int(time.time() * 1000)}
    with _lock:
        rest = [x for x in convos(uid) if x["id"] != cid]
        _write(_path(uid, "convos.json"), sorted([item] + rest, key=lambda x: -x["updated"])[:MAX_CONVOS])
    return item


def delete_convo(uid, cid):
    with _lock:
        _write(_path(uid, "convos.json"), [x for x in convos(uid) if x["id"] != cid])


# ---------------------------------------------------------------- reminders
MAX_REMINDERS = 50


def reminders(uid):
    try:
        with open(_path(uid, "reminders.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def add_reminder(uid, text, due):
    item = {"id": secrets.token_hex(4), "text": re.sub(r"\s+", " ", str(text)).strip()[:200], "due": int(due)}
    with _lock:
        items = sorted(reminders(uid) + [item], key=lambda x: x["due"])[-MAX_REMINDERS:]
        _write(_path(uid, "reminders.json"), items)
    return item


def take_reminder(uid, rid, due_by):
    """The one device that plays a due reminder takes it off the list; every later one gets None
    (one ring for the whole profile, not one per device). Only when it is due by due_by (ms)."""
    with _lock:
        items = reminders(uid)
        item = next((x for x in items if x.get("id") == rid and x.get("due", 0) <= due_by), None)
        if item is not None:
            _write(_path(uid, "reminders.json"), [x for x in items if x is not item])
    return item


def remove_reminders(uid, ids):
    with _lock:
        items = reminders(uid)
        keep = [x for x in items if x["id"] not in ids]
        _write(_path(uid, "reminders.json"), keep)
    return len(items) - len(keep)


# ---------------------------------------------------------------- memory
def memory(uid):
    try:
        with open(_path(uid, "memory.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def remember(uid, text, auto=False):
    text = re.sub(r"\s+", " ", str(text)).strip()[:MAX_FACT_LEN]
    if not text:
        return None
    with _lock:
        facts = [x for x in memory(uid) if x["text"].lower() != text.lower()]
        item = {"id": secrets.token_hex(4), "text": text, "created": int(time.time())}
        if auto:  # learned from a conversation, not asked for
            item["auto"] = True
        facts.append(item)
        _write(_path(uid, "memory.json"), facts[-MAX_FACTS:])
    return text


def forget(uid, fact_id=None, text=None):
    """Removes one fact by id, or the facts containing text; returns how many went."""
    with _lock:
        facts = memory(uid)
        if fact_id:
            keep = [x for x in facts if x["id"] != fact_id]
        elif text:
            t = str(text).lower().strip()
            keep = [x for x in facts if t not in x["text"].lower()]
        else:
            keep = []
        _write(_path(uid, "memory.json"), keep)
        return len(facts) - len(keep)


# ---------------------------------------------------------------- tool log
# What the assistant looked up per turn (question, tools with arguments and a short result, the
# answer), so the person can see where an answer came from. Only the profile's own turns, short
# texts, and only for a few days.
TOOL_LOG_DAYS, TOOL_LOG_MAX = 7, 200


def tool_log(uid):
    try:
        with open(_path(uid, "toollog.json")) as f:
            items = json.load(f)
    except (OSError, ValueError):
        return []
    cut = (time.time() - TOOL_LOG_DAYS * 86400) * 1000
    return [x for x in items if isinstance(x, dict) and x.get("t", 0) >= cut] if isinstance(items, list) else []


def tool_log_add(uid, question, calls, answer):
    item = {"t": int(time.time() * 1000), "q": str(question)[:300], "answer": str(answer).strip()[:600],
            "calls": [{"name": str(c["name"])[:60], "args": str(c["args"])[:300], "result": str(c["result"])[:600]}
                      for c in calls[:12]]}
    with _lock:
        _write(_path(uid, "toollog.json"), (tool_log(uid) + [item])[-TOOL_LOG_MAX:])


def tool_log_clear(uid):
    with _lock:
        _write(_path(uid, "toollog.json"), [])
