"""User profiles for the assistant: who is talking, and what the assistant remembers about them.

Every profile has its own folder; nothing in one profile is reachable from another. The profile of
a request comes only from its login cookie or its device key, never from anything the LLM says.

    USERS_DIR/profiles.json   {"users": [...], "devices": [...]}
    USERS_DIR/secret          signs the login cookies
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
def admin_list():
    d = _load()
    users = [{"id": u["id"], "name": u["name"], "created": u.get("created"), "facts": len(memory(u["id"]))}
             for u in d["users"]]
    devices = [{k: v[k] for k in ("id", "name", "user", "created") if k in v} for v in d["devices"]]
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
def add_device(name, uid):
    with _lock:
        d = _load()
        if not any(u["id"] == uid for u in d["users"]):
            raise ValueError("no such profile")
        token = "sd_" + secrets.token_urlsafe(24)
        d["devices"].append({"id": "d_" + secrets.token_hex(6), "name": name.strip(), "user": uid,
                             "token": hashlib.sha256(token.encode()).hexdigest(), "created": int(time.time())})
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
def _cookie_value(u):
    sig = hmac.new(_secret(), (u["id"] + u["pin"]).encode(), hashlib.sha256).hexdigest()
    return f"{u['id']}.{sig}"


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


def current(request):
    """{"id", "name"} of the profile behind this request (device key first, then cookie), or None."""
    d = _load()
    token = request.headers.get(DEVICE_HEADER, "")
    if token:
        h = hashlib.sha256(token.encode()).hexdigest()
        dev = next((x for x in d["devices"] if secrets.compare_digest(x["token"], h)), None)
        uid = dev and dev["user"]
    else:
        raw = request.cookies.get(COOKIE, "")
        uid = raw.split(".", 1)[0]
        u = next((u for u in d["users"] if u["id"] == uid), None)
        if not u or not secrets.compare_digest(raw, _cookie_value(u)):
            return None
    u = next((u for u in d["users"] if u["id"] == uid), None)
    return {"id": u["id"], "name": u["name"]} if u else None


# ---------------------------------------------------------------- conversation settings
# key: (default, check). The admin's defaults (config chat.defaults) apply where a profile has
# set nothing; guests keep theirs in the browser.
SETTINGS = {
    "hands": (False, lambda v: isinstance(v, bool)),
    "auto": (True, lambda v: isinstance(v, bool)),
    "live": (True, lambda v: isinstance(v, bool)),
    "barge": (True, lambda v: isinstance(v, bool)),
    "barge_level": ("mid", lambda v: v in ("low", "mid", "high")),
    "voice": ("", lambda v: isinstance(v, str) and len(v) <= 64 and re.fullmatch(r"[\w .\-]*", v)),
    "speed": (1.0, lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0.7 <= v <= 1.4),
    "length": ("normal", lambda v: v in ("short", "normal", "long")),
    "timing": (True, lambda v: isinstance(v, bool)),
}


def clean_settings(d):
    """Only known keys with valid values."""
    d = d if isinstance(d, dict) else {}
    return {k: d[k] for k, (_, ok) in SETTINGS.items() if k in d and ok(d[k])}


def defaults(admin=None):
    return dict({k: v for k, (v, _) in SETTINGS.items()}, **clean_settings(admin))


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
    msgs = [{"role": m["role"], "content": str(m["content"])[:MAX_MSG_LEN]} for m in c["msgs"][-MAX_MSGS:]
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


def remember(uid, text):
    text = re.sub(r"\s+", " ", str(text)).strip()[:MAX_FACT_LEN]
    if not text:
        return None
    with _lock:
        facts = [x for x in memory(uid) if x["text"].lower() != text.lower()]
        facts.append({"id": secrets.token_hex(4), "text": text, "created": int(time.time())})
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
