"""User profiles for the assistant: who is talking, and what the assistant remembers about them.

Every profile has its own folder; nothing in one profile is reachable from another. The profile of
a request comes only from its login cookie or its device key, never from anything the LLM says.

    USERS_DIR/profiles.json   {"users": [...], "devices": [...]}
    USERS_DIR/secret          signs the login cookies
    USERS_DIR/seen.json       when and from where each device key was last used (a profile id: when
                              its browser login was last used, without the address)
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

from common import write_json

USERS_DIR = os.environ.get("SPEECH_SPARK_USERS", "/var/lib/speech-spark/users")
COOKIE = "speech_spark_user"
DEVICE_HEADER = "x-speech-device"
MAX_FACTS, MAX_FACT_LEN = 200, 300
WARN_FACTS = 180   # Ich → Gedächtnis shows „N von MAX_FACTS“ in yellow from here on (plan nutzerwissen, Punkt 4.5)
_lock = threading.Lock()
# the assistant's faces (static/js/face.js): the admin picks the Spark's (chat.face), each profile may pick its own
FACES = ("robot", "comic", "comic_woman")


def _path(*parts):
    return os.path.join(USERS_DIR, *parts)


def _write(path, data):
    write_json(path, data, indent=1, mode=0o600, ensure_ascii=False, dir_mode=0o700)


# ---------------------------------------------------------------- the profile's own data (plan nutzerwissen, Stufe 4)
# Memory, conversations and what the Spark learned about a person are read and written only here (read_own,
# write_own, drop_own), never with open() or _write on their path (test_siegel): so they can be sealed at rest in one
# place. Written without indenting: convos.json (up to 2 MB) is written on every saved turn (code check B6).
def read_own(uid, name, default=None):
    """The content of users/<uid>/<name>, else default (missing or broken file)."""
    try:
        with open(_path(uid, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_own(uid, name, data):
    """users/<uid>/<name> atomically (common.write_json), only for the profile's service user."""
    write_json(_path(uid, name), data, mode=0o600, ensure_ascii=False, dir_mode=0o700)


def drop_own(uid, name):
    """Deletes users/<uid>/<name>; True when there was one."""
    try:
        os.remove(_path(uid, name))
        return True
    except FileNotFoundError:
        return False


# One proposal per profile and module waiting for a yes: USERS_DIR/<uid>/<name>-pending.json with "t" (when) and
# "src" (where it was proposed; only a yes from there confirms it). calendars, tidy, tasks, agent, meinmcp, fixes, messages.
# PENDING_HOOKS get (uid, name, proposal) after it is written (vorgaenge.from_pending: the card „Wartet auf dein Ja“).
PENDING_HOOKS = []


def pending_file(uid, name):
    return _path(uid, f"{name}-pending.json")


def pending_set(uid, name, data, src=""):
    item = dict(data, t=int(time.time()), src=str(src or "")[:120])
    _write(pending_file(uid, name), item)
    for f in PENDING_HOOKS:
        try:
            f(uid, name, item)
        except Exception as e:
            print("profiles: pending hook", type(e).__name__, flush=True)


def pending_get(uid, name, seconds):
    """The proposal, or None when there is none or it is older than seconds."""
    try:
        with open(pending_file(uid, name)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and time.time() - d.get("t", 0) < seconds else None
    except (OSError, ValueError):
        return None


def pending_drop(uid, name):
    try:
        os.remove(pending_file(uid, name))
    except OSError:
        pass


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


# PBKDF2-SHA256 rounds of a PIN: OWASP's 600 000 since V01.0.825 (code check 19.10. C8; self-tests lower it for speed
# only, test_tempo checks what ships). Stored as "salt$digest$rounds"; "salt$digest" is from before (OLD_PIN_ROUNDS)
# and renewed at the next sign-in with the PIN.
PIN_ROUNDS = 600_000
OLD_PIN_ROUNDS = 200_000


def _pin_hash(pin, salt=None, rounds=None):
    salt, rounds = salt or secrets.token_hex(16), rounds or PIN_ROUNDS
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), rounds).hex()}${rounds}"


def _pin_rounds(stored):
    parts = str(stored).split("$")
    return int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else OLD_PIN_ROUNDS


def _pin_ok(pin, stored):
    salt, rounds = str(stored).split("$")[0], _pin_rounds(stored)
    want = str(stored).split("$")[1] if "$" in str(stored) else ""
    return secrets.compare_digest(_pin_hash(pin, salt, rounds).split("$")[1], want)


def valid_name(name):
    return isinstance(name, str) and 1 <= len(name.strip()) <= 40 and not re.search(r"[<>\"\\\n]", name)


def valid_call(call):
    """A Rufname goes into other profiles' conversations (spoken back, asked about): only a short name,
    never a sentence an assistant could take for an instruction."""
    return isinstance(call, str) and re.fullmatch(r"[\wäöüÄÖÜß.'\- ]{1,30}", call) is not None \
        and not re.search(r"\d{4}|_", call) and len(call.split()) <= 3


def valid_pin(pin):
    return isinstance(pin, str) and re.fullmatch(r"\S{4,64}", pin) is not None


# ---------------------------------------------------------------- profiles
def user_ids():
    return [u["id"] for u in _load()["users"]]


def names():
    """[{"id", "name", "call"}] of every profile, from one read of profiles.json."""
    return [{"id": u["id"], "name": u["name"], "call": u.get("call", "")} for u in _load()["users"]]


def last_use(uid, last=None, devs=None):
    """When the profile was last used: its browser login or one of its device keys (time, or 0)."""
    last = seen() if last is None else last
    devs = _load()["devices"] if devs is None else devs
    ts = [int((last.get(uid) or {}).get("t") or 0)]
    ts += [int((last.get(x["id"]) or {}).get("t") or 0) for x in devs if x.get("user") == uid]
    return max(ts)


ADMIN_SHOW = ("", "mfa", "nomfa", "idle", "nodev", "room")
ADMIN_SORT = ("name", "recent", "new")
ADMIN_PER = 100      # at most this many profiles per page of the admin list
IDLE_DAYS = 90


def admin_list(q="", show="", sort="name", page=0, per=None, now=None, extra=None):
    """The admin's list of profiles: searched (name, Rufname or device name), filtered, sorted and one page
    of it; the devices of the shown profiles plus every device that matches the search. extra(u) adds
    what other modules know (second login step, messages on) and is asked only for the profiles a filter
    or the page needs. per None: every profile (the setup wizard)."""
    d = _load()
    last = seen()
    now = time.time() if now is None else now
    want = re.sub(r"\s+", " ", str(q or "")).strip().lower()[:40]
    show = show if show in ADMIN_SHOW else ""
    sort = sort if sort in ADMIN_SORT else "name"
    extra = extra or (lambda u: {})
    devs = d["devices"]
    users = []
    for u in d["users"]:
        mine = [x for x in devs if x.get("user") == u["id"]]
        if want and want not in u["name"].lower() and want not in u.get("call", "").lower() \
                and not any(want in x["name"].lower() for x in mine):
            continue
        row = {"id": u["id"], "name": u["name"], "call": u.get("call", ""), "created": u.get("created"),
               "last": last_use(u["id"], last, devs), "devices": len(mine)}
        if show == "idle" and row["last"] and now - row["last"] < IDLE_DAYS * 86400:
            continue
        if show == "idle" and not row["last"] and now - int(row["created"] or 0) < IDLE_DAYS * 86400:
            continue
        if show == "nodev" and mine:
            continue
        if show == "room":     # in room mode right now (extra adds "room", the number of its rooms)
            row.update(extra(u["id"]))
            if not row.get("room"):
                continue
        if show in ("mfa", "nomfa"):
            row.update(extra(u["id"]))
            if bool(row.get("mfa")) != (not show.startswith("no")):
                continue
        users.append(row)
    if sort == "recent":
        users.sort(key=lambda r: (-r["last"], r["name"].lower()))
    elif sort == "new":
        users.sort(key=lambda r: (-int(r["created"] or 0), r["name"].lower()))
    else:
        users.sort(key=lambda r: r["name"].lower())
    total = len(users)
    if per is not None:
        per = max(1, min(int(per), ADMIN_PER))
        page = max(0, min(int(page), max(0, (total - 1) // per)))
        users = users[page * per:(page + 1) * per]
    for r in users:
        r["facts"] = len(memory(r["id"]))
        r.update(extra(r["id"]))
    shown = {r["id"] for r in users}
    devices = [dict({k: v[k] for k in ("id", "name", "user", "created") if k in v}, last=last.get(v["id"]),
                    app=v.get("scope") == "app", kind=v.get("scope") or "") for v in devs
               if v.get("user") in shown or (want and want in v["name"].lower())]
    return {"users": users, "devices": devices, "total": total, "page": page if per is not None else 0,
            "per": per or total, "all": len(d["users"]), "names": [{"id": u["id"], "name": u["name"]} for u in d["users"]]}


def _taken(d, text, uid=None):
    """True when a name or Rufname of another profile already reads like this text."""
    t = text.strip().lower()
    return any(u["id"] != uid and t in (u["name"].lower(), u.get("call", "").lower()) for u in d["users"])


def set_call(uid, call):
    """The Rufname: how others call this profile in messages ("Thomas M.", "Papa"); "" removes it. Unique
    among every name and Rufname, so a spoken name never fits two profiles."""
    call = str(call or "").strip()
    if call and not valid_call(call):
        raise ValueError("Rufname: up to 30 letters, digits, spaces, dots, hyphens; at most 3 words")
    with _lock:
        d = _load()
        u = next((u for u in d["users"] if u["id"] == uid), None)
        if not u:
            raise LookupError("no such profile")
        if call.lower() == u["name"].lower():
            call = ""   # the same as the own name: no Rufname needed
        if call and _taken(d, call, uid):
            raise ValueError("this name is already used by another profile")
        if call:
            u["call"] = call
        else:
            u.pop("call", None)
        _write(_path("profiles.json"), d)
        return call


# Only the length of a PIN is noted ("short": fewer than STRONG_PIN characters), when it is set and at a
# sign-in, for "Sicherheit auf einen Blick"; PINs from before V01.0.262 count from their next sign-in.
STRONG_PIN = 6


def _note_short(uid, short):
    with _lock:
        d = _load()
        for u in d["users"]:
            if u["id"] == uid and u.get("short") != short:
                u["short"] = short
                _write(_path("profiles.json"), d)


def short_pins():
    return [u["name"] for u in _load()["users"] if u.get("short")]


def add_user(name, pin):
    with _lock:
        d = _load()
        if _taken(d, name):
            raise ValueError("a profile with this name exists")
        u = {"id": "u_" + secrets.token_hex(6), "name": name.strip(), "pin": _pin_hash(pin), "created": int(time.time()),
             "short": len(str(pin)) < STRONG_PIN}
        d["users"].append(u)
        _write(_path("profiles.json"), d)
        return u["id"]


def _renew_pin(uid, pin):
    """The PIN's hash with today's rounds (V01.0.825). Logins stay: they are signed with the old hash (pin_sig)
    until the PIN itself changes."""
    with _lock:
        d = _load()
        for u in d["users"]:
            if u["id"] == uid and _pin_rounds(u["pin"]) != PIN_ROUNDS:
                u.setdefault("pin_sig", u["pin"])
                u["pin"] = _pin_hash(pin)
                _write(_path("profiles.json"), d)
                print(f"profiles: PIN mit {PIN_ROUNDS} Runden neu gespeichert | {log_name(u)}", flush=True)
                return u
    return None


def set_pin(uid, pin):
    with _lock:
        d = _load()
        for u in d["users"]:
            if u["id"] == uid:
                u["pin"] = _pin_hash(pin)  # also ends the logins made with the old PIN
                u.pop("pin_sig", None)
                u["short"] = len(str(pin)) < STRONG_PIN
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
# A browser login is "<user id>.<issued>.<session>.<signature>". It ends after session_days() without use
# (the panel renews it while it is used), when the PIN changes, with "log out everywhere" (epoch) or when
# its session is ended in the list of signed-in browsers (V01.0.262). Logins from before V01.0.262 have no
# session part ("<user id>.<issued>.<signature>") and get one at their next renewal.
SESSION_DAYS = 90   # the longest an admin may set (panel.session_days, 7..90, default 30)
RENEW_AFTER = 86400
MAX_SESSIONS = 20   # per profile; the oldest login ends when a new one would be the 21st
_slock = threading.Lock()


def session_days():
    try:
        from common import load_config
        d = int(load_config().get("panel", {}).get("session_days", 30))
    except Exception:
        d = 30
    return min(max(d, 7), SESSION_DAYS)


def session_secs():
    return session_days() * 86400


def _sign(u, issued, sid=""):
    msg = f"{u['id']}|{u.get('pin_sig') or u['pin']}|{u.get('epoch', 0)}|{issued}" + (f"|{sid}" if sid else "")
    return hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()


def _sessions():
    try:
        with open(_path("sessions.json")) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def agent_label(ua):
    """A short name for a browser ("iPhone · Safari"), never the raw user agent."""
    ua = str(ua or "")[:400]
    dev = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Macintosh", "Mac"),
                               ("Windows", "Windows"), ("CrOS", "ChromeOS"), ("Linux", "Linux")) if k in ua), "")
    br = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("CriOS", "Chrome"),
                              ("Chrome/", "Chrome"), ("Safari/", "Safari"), ("SparkApp", "Spark-App")) if k in ua), "")
    return " · ".join(x for x in (dev, br) if x) or "Browser"


def _new_session(uid, agent=""):
    sid = secrets.token_hex(8)
    now = int(time.time())
    with _slock:
        d = _sessions()
        for k in [k for k, v in d.items() if now - v.get("l", 0) > SESSION_DAYS * 86400]:
            d.pop(k)
        mine = sorted((v.get("l", 0), k) for k, v in d.items() if v.get("u") == uid)
        for _, k in mine[:max(0, len(mine) - MAX_SESSIONS + 1)]:
            d.pop(k)
        d[sid] = {"u": uid, "f": now, "l": now, "a": agent_label(agent)}
        _write(_path("sessions.json"), d)
    return sid


def _touch_session(sid):
    with _slock:
        d = _sessions()
        if sid in d:
            d[sid]["l"] = int(time.time())
            _write(_path("sessions.json"), d)


def sessions(uid, current=""):
    """The signed-in browsers of a profile, newest use first (no address, only a short browser name)."""
    cur = (current or "").split(".")
    cur = cur[2] if len(cur) == 4 else ""
    out = [{"id": k, "first": v.get("f", 0), "last": v.get("l", 0), "agent": v.get("a", "Browser"), "this": k == cur}
           for k, v in _sessions().items() if v.get("u") == uid and time.time() - v.get("l", 0) <= session_secs()]
    return sorted(out, key=lambda x: -x["last"])


def end_session(uid, sid):
    """Ends one browser login of this profile; False when there is no such login."""
    with _slock:
        d = _sessions()
        if d.get(sid, {}).get("u") != uid:
            return False
        d.pop(sid)
        _write(_path("sessions.json"), d)
    return True


def _drop_sessions(uid):
    with _slock:
        d = _sessions()
        for k in [k for k, v in d.items() if v.get("u") == uid]:
            d.pop(k)
        _write(_path("sessions.json"), d)


def mark_second_step(raw, mark):
    """This browser login was made with the profile's second step (code, passkey, trusted browser): remember its
    fingerprint (mfa.mark). Only such a login acts as admin (coadmin.session); a new setup makes it count no more."""
    parts = (raw or "").split(".")
    if len(parts) != 4 or not mark:
        return
    with _slock:
        d = _sessions()
        if d.get(parts[2], {}).get("u") == parts[0]:
            d[parts[2]]["m"] = mark
            _write(_path("sessions.json"), d)


def second_step_of(raw):
    """The second step's fingerprint this browser login was made with, "" for none (see mark_second_step)."""
    parts = (raw or "").split(".")
    return str(_sessions().get(parts[2], {}).get("m", "")) if len(parts) == 4 else ""


def _cookie_value(u, issued=None, sid=None, agent=""):
    issued = int(issued or time.time())
    sid = sid or _new_session(u["id"], agent)
    return f"{u['id']}.{issued}.{sid}.{_sign(u, issued, sid)}"


def login(name, pin, agent=""):
    """Returns the cookie value, or None for an unknown name or a wrong PIN (indistinguishable)."""
    name = str(name).strip().lower()
    u = next((u for u in _load()["users"] if u["name"].lower() == name), None)
    if u and _pin_ok(pin, u["pin"]):
        _note_short(u["id"], len(str(pin)) < STRONG_PIN)
        if _pin_rounds(u["pin"]) != PIN_ROUNDS:
            u = _renew_pin(u["id"], pin) or u
        return _cookie_value(u, agent=agent)
    if not u:
        _pin_hash(pin)  # same work as a wrong PIN, so timing does not reveal which names exist
    return None


def by_id(uid):
    u = next((u for u in _load()["users"] if u["id"] == uid), None)
    return {"id": u["id"], "name": u["name"]} if u else None


def _cookie_user(d, raw):
    """(user, issued) of a valid browser login, else (None, 0)."""
    parts = raw.split(".")
    if len(parts) not in (3, 4) or not parts[1].isdigit():
        return None, 0
    uid, issued, sig = parts[0], int(parts[1]), parts[-1]
    sid = parts[2] if len(parts) == 4 else ""
    u = next((u for u in d["users"] if u["id"] == uid), None)
    if not u or time.time() - issued > session_secs() or not secrets.compare_digest(sig, _sign(u, issued, sid)):
        return None, 0
    if sid and _sessions().get(sid, {}).get("u") != uid:   # ended in the list of signed-in browsers
        return None, 0
    import guard
    if guard.revoked(raw):
        return None, 0
    return u, issued


def renewed_cookie(request):
    """A fresh cookie value when this request's login is valid and older than a day, else None."""
    d = _load()
    raw = request.cookies.get(COOKIE, "")
    u, issued = _cookie_user(d, raw)
    if u and time.time() - issued > RENEW_AFTER and not request.headers.get(DEVICE_HEADER):
        parts = raw.split(".")
        if len(parts) == 4:
            _touch_session(parts[2])
            return _cookie_value(u, sid=parts[2])
        return _cookie_value(u, agent=request.headers.get("user-agent", ""))
    return None


def end_sessions(uid):
    """Logs this profile out in every browser (device keys stay)."""
    with _lock:
        d = _load()
        for u in d["users"]:
            if u["id"] == uid:
                u["epoch"] = int(u.get("epoch", 0)) + 1
                _write(_path("profiles.json"), d)
                _drop_sessions(uid)
                return True
        return False


# last use of each device key: kept in memory, written at most every SEEN_EVERY seconds
SEEN_EVERY = 600
_seen, _seen_written = {}, [0.0]


def _note_device(did, request, ip=True):
    """did: a device id, or a profile id for its browser login (then without the address)."""
    now = time.time()
    _seen[did] = {"t": int(now), "ip": request.client.host if ip and getattr(request, "client", None) else ""}
    if not ip:
        _seen[did].pop("ip")
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
             "/api/zustellung/da",    # "in use now" or "away" (zustellung.py: notes go to the device in use)
             "/api/proactive", "/api/proactive/greet", "/api/proactive/played", "/api/assistant/say",
             "/api/iphone/push-token", "/api/iphone/note",
             "/api/profile/convos",   # the conversations, the same list as in the panel
             "/api/iphone/doc",       # a document's text into the profile's documents (Eigene Dokumente)
             "/api/chat/image",       # a picture for the next question (app_images, images.py)
             "/api/chat/rate",        # 👍/👎 on an answer of the own profile (faelle.py, Einstellungs-Assistent)
             "/api/iphone/settings",  # the profile's own voice, answers and "Von selbst" (iphone.APP_FIELDS only)
             "/api/assistant/voices",  # the voice names to choose from
             # Apple Reminders on the iPhone (app_ios): new list entries to the iPhone, adding from Shortcuts
             "/api/tasks/inbox", "/api/profile/tasks/einkauf", "/api/profile/tasks/aufgaben",
             # Spark updates (appupdate.py): rights only from the admin, starting needs a fresh code
             "/api/iphone/update",
             # chats (chats.py): the list, a chat's messages, writing, reacting, groups, the event stream
             "/api/chats", "/api/chats/items", "/api/chats/open", "/api/chats/group", "/api/chats/send", "/api/chats/edit",
             "/api/chats/back", "/api/chats/react", "/api/chats/read", "/api/chats/typing", "/api/chats/opts",
             "/api/chats/members", "/api/chats/leave", "/api/chats/clear", "/api/chats/find", "/api/chats/stream",
             "/api/chats/media",
             # private chats (chatsec.py): the app's own device key in the Secure Enclave, the history for a new device
             "/api/chats/keys", "/api/chats/keys/remove", "/api/chats/private", "/api/chats/share", "/api/chats/share/done",
             # calls between two profiles (anrufe.py): the app rings through CallKit, sound and picture go device to device
             "/api/anrufe/ice", "/api/anrufe/info", "/api/anrufe/start", "/api/anrufe/answer", "/api/anrufe/signal",
             "/api/anrufe/end",
             # where room mode listens and ending it (roomlive.py, only with app_room; never starting or extending)
             "/api/room/active", "/api/room/end",
             "/api/profile/docs",     # the list of the own documents (GET only for the app, with Eigene Dokumente)
             "/api/features",         # what the Spark and the profile allow (features.py, read only; "Im Panel öffnen")
             "/api/profile/hintergrund",   # Ich → Mein Zustand (hintergrund.py, read only, own switch my_status)
             "/api/vorrang/spricht",       # "recording starts" for a profile with Vorrang (stufe.py)
             "/api/profile/today",    # Heute: numbers and short titles of today (today.py, read only)
             "/api/notaus",           # the Notaus: its stage, and raising it when the admin allows profiles (notaus.py)
             "/api/notaus/mine",      # Mein Notaus from the app's button and Siri (switching on only; lifting stays in the browser)
             # Probleme melden (meldung.py): draft, preview, send exactly the previewed text, answers, delete
             "/api/report", "/api/report/draft", "/api/report/preview", "/api/report/send", "/api/report/thread", "/api/report/delete",
             "/api/make",             # Dokumente erstellen (docmake.py): the list of made documents, read only
             "/api/write", "/api/write/assist",   # Schreibhilfe (schreib.py, only with "In anderen Programmen")
             "/api/app/langsam")      # a page of the app took long: page word and milliseconds into the log (appmerken.py)
# looking at an own document again (wissen.reader: only with Eigene Dokumente); reading only, never changing
APP_PATTERNS = (re.compile(r"/api/profile/wissen/[0-9a-f]{12}/(?:text|file)"),
                # a made document (docmake.py), its preview and its file: reading only, never changing or sending
                re.compile(r"/api/make/doc/[0-9a-f]{12}(?:/file)?"), re.compile(r"/api/make/job/[0-9a-f]{12}"),
                # a picture painted for an answer (bilder.py, with chat.bilder): its job and its file, reading only
                re.compile(r"/api/bilder/job/[0-9a-f]{12}"), re.compile(r"/api/bilder/[0-9a-f]{12}/datei"),
                # a song made for an answer (musik.py, with chat.musik): its job and its file, reading only
                re.compile(r"/api/musik/job/[0-9a-f]{12}"), re.compile(r"/api/musik/[0-9a-f]{12}/datei"))
APP_GATE = [lambda uid: False]
# Panel areas in the app (iphone.py, V01.0.246): with the admin switch chat.iphone_panel and the profile's
# own switch for an area, the app's key also reaches that area's panel paths. right -> ((methods, pattern), ...);
# filled by iphone.py, APP_AREA_GATE(uid, right) says whether the area is open for the profile.
APP_AREAS = {}
APP_AREA_GATE = [lambda uid, right: False]


def _app_path(request):
    path = request.scope.get("path") or ""
    if path in APP_PATHS:
        return True
    return request.method == "GET" and any(p.fullmatch(path) for p in APP_PATTERNS)


def _app_area(request, uid):
    """The panel area (its switch name) this request of the app's key belongs to, when it is open; else None."""
    path = request.scope.get("path") or ""
    for right, rules in APP_AREAS.items():
        if any(request.method in methods and pat.fullmatch(path) for methods, pat in rules) \
                and APP_AREA_GATE[0](uid, right):
            return right
    return None
# A room key (scope "room", for Home Assistant) only reads where room mode listens and ends it (roomlive.py),
# and only while the admin allows it (ROOM_GATE, set by roomlive.py; closed without it).
# A Spark-Begleiter key (scope "desk", begleiter.py, the program in the Windows notification area or the Mac menu
# bar) only reaches its own paths, only while the admin and the profile allow it (DESK_GATE, set by begleiter.py);
# each part (writing help, questions, dictation, notes, Notaus button) is checked again per device there.
DESK_PATHS = ("/api/write", "/api/write/assist", "/api/write/suggest", "/api/desk/config", "/api/desk/poll", "/api/desk/ask",
              "/api/desk/dictate", "/api/desk/notaus", "/api/desk/update", "/api/desk/file", "/api/desk/screen", "/api/desk/hear", "/api/desk/act",
              # Version 4 (exact paths; the ids go in the query or the body)
              "/api/desk/speak", "/api/desk/inbox/file", "/api/desk/inbox/done", "/api/desk/agenda", "/api/desk/remind",
              "/api/desk/busy", "/api/desk/meeting/start", "/api/desk/meeting/chunk", "/api/desk/meeting/end",
              "/api/desk/meeting/keep", "/api/desk/home", "/api/desk/daily", "/api/desk/apps",
              # Rechner fernsteuern, Stufe 1: what the person chose at the computer, the held wait for orders
              "/api/desk/local", "/api/desk/wait",
              # Begleiter nachziehen (2026-10-20): a button of a note of its own kind (Für dich: erledigt, erinnern)
              "/api/desk/note/act",
              # Post im Begleiter (part post): unread, Für dich, the buttons of its cards
              "/api/desk/post", "/api/desk/post/act",
              # Schnell erfassen (part capture): the chips of one line, „Eintragen“, Rückgängig
              "/api/desk/capture", "/api/desk/capture/undo", "/api/desk/lists",
              # Ordner auslassen (auslassen.py): the sub folders of "Spark-Wissen", for the tree
              "/api/desk/ordner",
              # Stufe 2 (fernsicht.py): answer at the computer, pictures out, inputs in, end
              "/api/desk/view/answer", "/api/desk/view/frame", "/api/desk/view/input", "/api/desk/view/end",
              # Stufe 3 (bedienen.py): the answer to one step
              "/api/desk/view/step",
              # Office-Add-ins (2026-10-12): the three manifests
              "/api/desk/office/word.xml", "/api/desk/office/excel.xml", "/api/desk/office/outlook.xml")
DESK_GATE = [lambda uid: False]
ROOM_PATHS = ("/api/room/active", "/api/room/end")
ROOM_GATE = [lambda uid: False]
# A watch key (scope "watch", the Pebble app paired by code, pebblewatch.py) only asks on the watch paths,
# and only while the admin and the profile have the watch switched on (WATCH_GATE, set by pebblewatch.py).
WATCH_PREFIX = "/api/watch/"
WATCH_GATE = [lambda uid: False]
# A Home Assistant event key (scope "haev", hamelden.py) only tells the Spark that something happened, on this
# one path, and only while the admin and the profile have "Home Assistant meldet an Spark" on (HAEV_GATE).
HAEV_PATHS = ("/api/ha/event",)
HAEV_GATE = [lambda uid: False]
# A writing help key (scope "write", Mac quick action, Windows program, Office add-in, browser extension, paired
# by code in schreib.py) only gets texts improved, on these paths, and only while the admin and the profile have
# the writing help and "In anderen Programmen" on (WRITE_GATE, set by schreib.py).
WRITE_PATHS = ("/api/write", "/api/write/assist", "/api/write/plain", "/api/write/suggest")
WRITE_GATE = [lambda uid: False]
# A terminal key (scope "tui", spark-tui paired by code, terminal.py) only reaches terminal.TUI_RULES (TUI_REACH says
# "panel" or "agent", None for anything else), and only while the admin has the terminal client on (TUI_GATE).
TUI_GATE = [lambda uid: False]
TUI_REACH = [lambda request: None]


def _device(d, request):
    token = request.headers.get(DEVICE_HEADER, "")
    return device_by_token(token, d) if token else None


def device_by_token(token, d=None):
    """The device entry behind a key (also one just handed out by add_device), or None."""
    h = hashlib.sha256(str(token).encode()).hexdigest()
    return next((x for x in (_load() if d is None else d)["devices"] if secrets.compare_digest(x["token"], h)), None)


def device(request):
    """The device entry behind this request's key (id, user, scope), or None for logins."""
    if request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
        return None
    dev = _device(_load(), request)
    return {"id": dev["id"], "user": dev["user"], "scope": dev.get("scope") or ""} if dev else None


def device_name(request):
    """The name of the device key behind this request ("" for logins and guests)."""
    if request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
        return ""
    dev = _device(_load(), request)
    return str(dev.get("name") or "") if dev else ""


def key_scope(request):
    """The scope of the device key this request carries ("app"), "" for other keys and logins."""
    if request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
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


def _gate_closed(request, why="off"):
    """A known device key whose function is switched off right now (Gesperrte Funktionen, Ich, Mein Notaus): no profile
    for this request, but core.assistant answers 503 ("not now", like the Notaus) instead of 401, so the apps keep
    their pairing, do not ask again in a loop, and work again as soon as the switch is back on (V01.0.388)."""
    request.scope["speech_gate_closed"] = why
    return None


def current(request):
    """{"id", "name"} of the profile behind this request (device key first, then cookie), or None."""
    d = _load()
    # "Spark fragen" over MCP (mcpserver.py): set only by the panel itself after checking the connection's token
    import notaus
    mcp = request.scope.get("speech_mcp")
    if mcp:
        if notaus.own(mcp.get("uid")):   # Mein Notaus closes every way in of the profile but its own browser
            return None
        u = next((u for u in d["users"] if u["id"] == mcp.get("uid")), None)
        return {"id": u["id"], "name": u["name"]} if u else None
    inner = request.scope.get("speech_profile")   # set only by the panel itself (Telegram, see telegram.py; telefon.py)
    if inner:
        if notaus.own(inner):
            return None
        if request.scope.get("speech_channel") != "telefon":   # a call is no device push could go to
            used(inner, "tg")
        u = next((u for u in d["users"] if u["id"] == inner), None)
        return {"id": u["id"], "name": u["name"]} if u else None
    token = request.headers.get(DEVICE_HEADER, "")
    if token:
        dev = _device(d, request)
        if not dev:
            return None
        if dev.get("scope") == "app":
            area = None if _app_path(request) else _app_area(request, dev["user"])
            if not area and not _app_path(request):
                return None
            if not APP_GATE[0](dev["user"]):
                return _gate_closed(request)
            # core.browser_profile lets the app into the area's paths like the profile's own browser login
            request.scope["speech_app_area"] = area
        if dev.get("scope") == "room" and request.scope.get("path") not in ROOM_PATHS:
            return None
        if dev.get("scope") == "room" and not ROOM_GATE[0](dev["user"]):
            return _gate_closed(request)
        if dev.get("scope") == "watch" and not str(request.scope.get("path") or "").startswith(WATCH_PREFIX):
            return None
        if dev.get("scope") == "watch" and not WATCH_GATE[0](dev["user"]):
            return _gate_closed(request)
        if dev.get("scope") == "haev" and request.scope.get("path") not in HAEV_PATHS:
            return None
        if dev.get("scope") == "haev" and not HAEV_GATE[0](dev["user"]):
            return _gate_closed(request)
        if dev.get("scope") == "write" and request.scope.get("path") not in WRITE_PATHS:
            return None
        if dev.get("scope") == "write" and not WRITE_GATE[0](dev["user"]):
            return _gate_closed(request)
        if dev.get("scope") == "desk" and request.scope.get("path") not in DESK_PATHS:
            return None
        if dev.get("scope") == "desk" and not DESK_GATE[0](dev["user"]):
            return _gate_closed(request)
        if dev.get("scope") == "tui":
            reach = TUI_REACH[0](request)
            if not reach:
                return None
            if not TUI_GATE[0](dev["user"]):
                return _gate_closed(request)
            if reach == "agent":   # the agent's pages want the browser login: the terminal's key counts like it there
                request.scope["speech_app_area"] = "tui"
        if dev.get("scope") not in (None, "", "app", "room", "watch", "haev", "write", "desk", "tui"):
            return None
        if notaus.own(dev["user"]):
            return _gate_closed(request, "notaus")
        _note_device(dev["id"], request)
        uid = dev["user"]
        if dev.get("scope") == "app":
            used(uid, "app")
    else:
        u, _ = _cookie_user(d, request.cookies.get(COOKIE, ""))
        if not u:
            return None
        uid = u["id"]
        _note_device(uid, request, ip=False)   # "zuletzt benutzt" in the admin's list, without the address
    u = next((u for u in d["users"] if u["id"] == uid), None)
    return {"id": u["id"], "name": u["name"]} if u else None


def own_devices(uid):
    last = seen()
    return [{"id": x["id"], "name": x["name"], "created": x.get("created"), "last": last.get(x["id"]),
             "app": x.get("scope") == "app", "watch": x.get("scope") == "watch", "write": x.get("scope") == "write",
             "desk": x.get("scope") == "desk", "tui": x.get("scope") == "tui"}
            for x in _load()["devices"] if x.get("user") == uid]


# ---------------------------------------------------------------- conversation settings
# The allowed values of every setting with a fixed list (in this order), and the bounds of the numbers: the one list,
# SETTINGS checks against it and /api/profile/settings hands it to the browser (me.js builds its lists from it).
CHOICES = {
    "follow": ("0", "4", "6", "8", "10"),
    "barge_level": ("low", "mid", "high"),
    "length": ("short", "normal", "long"),
    "face": ("",) + FACES,
    "doc_deliver": ("", "pc", "rm", "tg", "mail", "box"),
    "rm_model": ("auto", "rm2", "pro", "move"),
    "rm_color": ("farbe", "grau"),
    "pro_lead": (5, 10, 15, 20, 30, 45, 60),
    "svc_device": ("", "app", "and", "desk", "tg", "web", "all"),
    "msg_from": ("all", "chosen"),
    "msg_speaker": ("off", "hint", "text"),
}
RANGES = {"speed": (0.7, 1.4), "pro_max": (1, 30)}


def _in(key):
    return lambda v: not isinstance(v, bool) and v in CHOICES[key]


def _within(key, kind):
    lo, hi = RANGES[key]
    return lambda v: isinstance(v, kind) and not isinstance(v, bool) and lo <= v <= hi


# key: (default, check). The admin's defaults (config chat.defaults) apply where a profile has
# set nothing; guests keep theirs in the browser.
SETTINGS = {
    "hands": (False, lambda v: isinstance(v, bool)),
    "auto": (True, lambda v: isinstance(v, bool)),
    # follow-up without the wake word: seconds the microphone stays open after an answer (admin chat.follow_up)
    "follow": ("0", _in("follow")),
    # the Spark's own voice from another device is no question (admin chat.no_self_echo, echo.py)
    "echo": (True, lambda v: isinstance(v, bool)),
    "daily": (True, lambda v: isinstance(v, bool)),
    "turn": (True, lambda v: isinstance(v, bool)),
    "live": (True, lambda v: isinstance(v, bool)),
    "barge": (True, lambda v: isinstance(v, bool)),
    "barge_level": ("mid", _in("barge_level")),
    "voice": ("", lambda v: isinstance(v, str) and len(v) <= 64 and re.fullmatch(r"[\w .\-]*", v)),
    "speed": (1.0, _within("speed", (int, float))),
    "length": ("normal", _in("length")),
    # "Antworten vorlesen": off = answers as text only on every own screen (chat_turn.quiet), speakers keep speaking
    "speak": (True, lambda v: isinstance(v, bool)),
    "timing": (True, lambda v: isinstance(v, bool)),
    # Ich → Gespräch → Anzeige „Gesicht“: the profile's own face on all its devices, "" = the Spark's (chat.face)
    "face": ("", _in("face")),
    "learn": (True, lambda v: isinstance(v, bool)),
    "trace_name": (False, lambda v: isinstance(v, bool)),   # Logs → Anfragen may show this profile's name (tracelog.py)
    "unklar_anon": (True, lambda v: isinstance(v, bool)),   # its unclear questions anonymized on Funktionen → Weiche (weiche_unklar.py)
    # documents (wissen.py): photos and scans read by the model, meaning search, keeping the originals
    "doc_due": (False, lambda v: isinstance(v, bool)),
    # "Mit Docling lesen" (doclingdienst.py): a preference, on unless the profile says no (its files leave the Spark)
    "doc_docling": (True, lambda v: isinstance(v, bool)),
    # Dokumente erstellen (docmake.py): the profile's own switch, own templates, the sender lines of a letter
    "doc_sender": ("", lambda v: isinstance(v, str) and len(v) <= 300 and v.count("\n") <= 5
                   and not re.search(r"[\x00-\x09\x0b-\x1f\x7f]", v)),
    # where a finished document also goes on its own (docmake.deliver_of; only a target that is set up counts)
    "doc_deliver": ("", _in("doc_deliver")),
    # more with the reMarkable (rmplus.py, admin chat.remarkable_plus)
    "rm_morning": (True, lambda v: isinstance(v, bool)),
    # "Der Spark darf mich anrufen" (telefon_anruf.py): ordered wake-up calls, reminders by call, call backs
    "telefon_anrufbar": (True, lambda v: isinstance(v, bool)),
    "rm_morning_at": ("06:30", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", v)),
    "rm_week": (True, lambda v: isinstance(v, bool)),
    "rm_inbox": (True, lambda v: isinstance(v, bool)),
    # paper for the reMarkable (rmpapier.py, admin chat.remarkable_paper)
    "rm_tidy": (True, lambda v: isinstance(v, bool)),
    # what comes on the Aufgabenblatt (rmaufgaben.PARTS): each part on unless the profile turns it off
    "rm_tasks_cal": (True, lambda v: isinstance(v, bool)),
    "rm_tasks_lists": (True, lambda v: isinstance(v, bool)),
    "rm_tasks_mail": (True, lambda v: isinstance(v, bool)),
    "rm_tasks_new": (True, lambda v: isinstance(v, bool)),
    "rm_tasks_note": (True, lambda v: isinstance(v, bool)),
    "rm_model": ("auto", _in("rm_model")),   # the model whose page format the paper takes (rmpapier.MODELS)
    "rm_color": ("farbe", _in("rm_color")),  # colour or grey on a device with a colour screen (rmpapier.model_of)
    # own wishes for the tone (admin chat.own_style): plain text, no control characters, no markers of outside text
    "style": ("", lambda v: isinstance(v, str) and len(v) <= 500 and not re.search(r"[\x00-\x09\x0b-\x1f\x7f]|<<<|>>>", v)),
    # roles switched by voice (roles.py, admin chat.roles): one "Name: ..." per line, the active name
    "roles": ("", lambda v: isinstance(v, str) and len(v) <= 1500 and not re.search(r"[\x00-\x09\x0b-\x1f\x7f]|<<<|>>>", v)),
    "role": ("", lambda v: isinstance(v, str) and len(v) <= 30 and re.fullmatch(r"[\w äöüÄÖÜß\-]*", v)),
    # daily briefing as a push notification at this local time ("" = off), in the device's time zone
    "briefing_at": ("", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d|", v)),
    "tz": ("", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+){0,2})?", v)),
    # speaking up by itself (see proactive.py): off until the person switches it on, each kind on its own
    "pro_on": (True, lambda v: isinstance(v, bool)),
    "msg_all": (True, lambda v: isinstance(v, bool)),    # in the fixed group "Alle" (chats.py); leaving it switches it off
    "pro_quiet": ("22:00-07:00", lambda v: isinstance(v, str) and re.fullmatch(r"(?:(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d)?", v)),
    "pro_max": (6, _within("pro_max", int)),
    "pro_events": (True, lambda v: isinstance(v, bool)),
    "pro_lead": (20, _in("pro_lead")),
    "pro_ha": (True, lambda v: isinstance(v, bool)),
    # Home Assistant tells the Spark (hamelden.py, each behind its own admin switch)
    "pro_ha_live": (True, lambda v: isinstance(v, bool)),     # live connection instead of the minute check
    "pro_ha_loud": (True, lambda v: isinstance(v, bool)),     # rules may also speak on speakers
    "pro_ha_events": (True, lambda v: isinstance(v, bool)),   # Home Assistant sends events with its own key
    "pro_ha_cam": (True, lambda v: isinstance(v, bool)),      # a camera's still picture in a few words
    "pro_ha_me": ("", lambda v: isinstance(v, str) and (v == "" or re.fullmatch(r"person\.[a-z0-9_]{1,80}", v) is not None)),
    "pro_mail_smart": (True, lambda v: isinstance(v, bool)),  # important mail recognized by systemone (chat.systemone_mail)
    "pro_greet": (True, lambda v: isinstance(v, bool)),
    "pro_follow": (True, lambda v: isinstance(v, bool)),
    "pro_mail": (True, lambda v: isinstance(v, bool)),
    "pro_tidy": (True, lambda v: isinstance(v, bool)),
    "pro_mail_from": ("", lambda v: isinstance(v, str) and len(v) <= 300 and "\n" not in v),
    # „Nicht wichtig“ on a card „Wichtige Mail“: senders never reported by the model (proactive.NOT_MAX characters)
    "pro_mail_not": ("", lambda v: isinstance(v, str) and len(v) <= 2000 and "\n" not in v),
    "pro_weather": (True, lambda v: isinstance(v, bool)),
    "pro_place": ("", lambda v: isinstance(v, str) and len(v) <= 60 and re.fullmatch(r"[^<>\"\\\n]*", v)),
    "pro_weather_at": ("18:00", lambda v: isinstance(v, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", v)),
    "pro_learn": (True, lambda v: isinstance(v, bool)),
    # weather, contacts, parcels (see weather.py, contacts.py, parcels.py): each profile switches them on itself
    "con_bday": (True, lambda v: isinstance(v, bool)),
    "pro_bday": (True, lambda v: isinstance(v, bool)),
    "pro_parcel": (True, lambda v: isinstance(v, bool)),
    "pro_fuerdich": (True, lambda v: isinstance(v, bool)),   # Für dich: deadlines today or tomorrow and phishing (fuerdich.due_notes)
    "pro_rueckblick": (True, lambda v: isinstance(v, bool)),   # Wochenrückblick on Sundays at 18 o'clock (ichweiss.week_sentence)
    "pro_transit": (True, lambda v: isinstance(v, bool)),
    "pro_feeds": (True, lambda v: isinstance(v, bool)),     # replies and keyword hits from Reddit und Feeds (feeds.py)
    "pro_tips": (True, lambda v: isinstance(v, bool)),     # one hint on a function a week (tipps.py, chat.feature_tips_push)
    "voice_tips": (True, lambda v: isinstance(v, bool)),   # one example sentence a day at speakers (saetze.py, chat.feature_sentences_voice)
    "list_note": (True, lambda v: isinstance(v, bool)),    # a note when others put something on a shared list (tasks.py)
    "share_note": (True, lambda v: isinstance(v, bool)),   # a note when another profile shares something (geteilt.py)
    # Telegram (see telegram.py): what this profile allows over Telegram, all off until it says so
    "tg_voice": (False, lambda v: isinstance(v, bool)),
    "tg_private": (False, lambda v: isinstance(v, bool)),
    "tg_ha": (False, lambda v: isinstance(v, bool)),
    "tg_push": (False, lambda v: isinstance(v, bool)),
    "tg_images": (False, lambda v: isinstance(v, bool)),    # photos sent to the bot go to the model (images.py)
    "devup_night": (True, lambda v: isinstance(v, bool)), # own speakers updated at night (geraeteupdate.py)
    "svc_note": (True, lambda v: isinstance(v, bool)),    # an admin profile hears when a service is gone (dienstwacht.py)
    "svc_night": (False, lambda v: isinstance(v, bool)),   # ... at night only one summary at 7 o'clock
    "svc_device": ("", _in("svc_device")),   # ... on this way (push.send to=)
    # Verlauf auf allen Geräten (verlauf.py): instant sync, one conversation for all channels, offline reading
    # Einstellungs-Assistent (faelle.py, berater.py): 👍/👎 under answers, hearing when a report helped, admin notes,
    # asking it in the chat, proposals for the own settings (and the ones the profile put aside)
    "rate_back": (True, lambda v: isinstance(v, bool)),
    "berater_note": (True, lambda v: isinstance(v, bool)),
    "berater_skip": ([], lambda v: isinstance(v, list) and len(v) <= 20 and all(isinstance(x, str) and re.fullmatch(r"p[a-z]{1,6}", x) for x in v)),
    "android_live": (True, lambda v: isinstance(v, bool)),  # ... with a lasting connection: notes at once
    # Uhr: Schnellbefehle (pebblewatch.py, admin chat.pebble_quick): the profile's own fixed sentences on the watch
    "peb_cmds": ([], lambda v: isinstance(v, list) and len(v) <= 12 and all(
        isinstance(x, str) and 0 < len(x) <= 60 and x == x.strip() and not re.search(r"[\x00-\x1f\x7f]", x) for x in v)),
    # Uhr: Fernbedienung (pebblewatch.py, admin chat.pebble_remote): the Home Assistant devices picked for the watch
    "peb_fern": ([], lambda v: isinstance(v, list) and len(v) <= 12 and all(
        isinstance(x, str) and re.fullmatch(r"[a-z0-9_]{1,64}\.[a-z0-9_]{1,200}", x) for x in v)),
    "report_notify": (True, lambda v: isinstance(v, bool)),   # an admin profile hears of a new report (meldung.tell_admins)
    # iPhone app (iphone.py): pairing for this profile, and switching the smart home from it, both off
    "app_ha": (False, lambda v: isinstance(v, bool)),
    "app_listen": (False, lambda v: isinstance(v, bool)),   # listening all the time for the wake word
    "app_act": (False, lambda v: isinstance(v, bool)),      # routes and calls on the iPhone (iphone_action)
    "app_push": (True, lambda v: isinstance(v, bool)),     # notes as Apple push to the closed app (apns.py)
    "app_car_ha": (False, lambda v: isinstance(v, bool)),   # smart home from CarPlay
    "app_ios": (False, lambda v: isinstance(v, bool)),      # Apple Reminders and the lists on the iPhone (tasks.py)
    "app_images": (False, lambda v: isinstance(v, bool)),   # pictures from the app to the model (images.py)
    "app_room": (False, lambda v: isinstance(v, bool)),     # where room mode listens, in the app (roomlive.py)
    # panel areas in the app (iphone.AREAS, admin chat.iphone_panel): one switch per area, set in the browser
    "room_tell": (False, lambda v: isinstance(v, bool)),    # a note when a speaker starts room mode by voice
    # agent functions (agent.py): the admin gives the level, the profile switches it on itself
    "agent_doc": (False, lambda v: isinstance(v, bool)),    # every report also under "Meine Dokumente"
    # what the chats brought along from "Nachrichten" (messages.py, V01.0.488): who may write to me, the group Alle,
    # new chat messages read on my speakers, announcements of others on my speakers
    "msg_from": ("all", _in("msg_from")),   # every profile, or only the ones picked
    "msg_speaker": ("off", _in("msg_speaker")),   # say new ones on my speakers
    # chats (chats.py): off until the profile switches them on; "gelesen" shown both ways, the text in notifications
    "chat_receipts": (True, lambda v: isinstance(v, bool)),
    "chat_push_text": (False, lambda v: isinstance(v, bool)),
}


# what only the profile itself writes, never the admin's defaults: its tone and its roles
OWN_ONLY = ("style", "roles", "role")
# the profiles' own preferences for what the Spark does unasked (features.py fills it, Feature.pref) and a few
# settings of single modules: never from the admin's presets, each profile sets them itself
NO_PRESET = {"face"}   # the face: the admin's own pick is chat.face, the presets never copy it into a profile


def face_of(uid, chat):
    """The face a profile sees: its own pick (Ich → Gespräch → Anzeige), else the Spark's (chat.face), else the
    robot. Only names from FACES; guests (uid None) and shared devices get the Spark's."""
    own = settings(uid).get("face") if uid else ""
    if own in FACES:
        return own
    spark = (chat or {}).get("face")
    return spark if spark in FACES else "robot"


# profile keys that are gone (Freigabe vereinfachen, App-Gleichstand …): the one list; never stored again, and what
# older apps or pages still send is ignored (iphone.py). A key removed from SETTINGS comes here (Richtlinie Teil 17).
GONE = frozenset((
    "agent_on", "android_on", "app_accounts", "app_admin", "app_auto", "app_docs", "app_docs_edit", "app_mine", "app_on",
    "app_security", "app_voice", "berater_ask", "berater_me", "chats_on", "con_on", "desk_on", "devup_on",
    "direct_read", "doc_brief", "doc_make", "doc_make_templates", "doc_make_wikipics", "doc_originals",
    "doc_pictures", "doc_semantic", "doc_shared", "esp_on", "esp_stop", "fix_learn", "images_on", "instant_ack",
    "kiwix_on", "klaeren", "klaeren_merken", "local_first", "mcps_on", "mem_ask", "mem_check", "mem_topics",
    "msg_announce", "my_status", "mymcp_on", "par_on", "pebble_on", "prefetch", "pro_ha_voice", "rate_on",
    "report_on", "rm_ask", "rm_folders", "rm_fresh", "rm_guide", "rm_meet", "rm_on", "rm_paper", "rm_send",
    "rm_todo", "rm_web", "roles_on", "room_remote", "route", "spark_help", "spk_code", "storage_on", "svc_hint",
    "sync_live", "sync_offline", "sync_one", "systemone_on", "tagebuch_on", "tasks_on", "tips_on", "tool_think",
    "transit_on", "why_on", "wiki_on", "write_apps", "write_on", "wx_on"))


def clean_settings(d):
    """Only known keys with valid values."""
    d = d if isinstance(d, dict) else {}
    return {k: d[k] for k, (_, ok) in SETTINGS.items() if k in d and ok(d[k])}


def defaults(admin=None):
    own = {k: v for k, v in clean_settings(admin).items() if k not in OWN_ONLY and k not in NO_PRESET}  # the tone is the profile's own
    return dict({k: v for k, (v, _) in SETTINGS.items()}, **own)


def effective(uid, chat=None):
    """What applies to this profile (or a guest, uid None): the admin's presets, overlaid with its own.
    The one place that mixes them (plan „Vereinheitlichen“, V01.0.268)."""
    if chat is None:
        from common import load_config
        chat = load_config().get("chat", {})
    return dict(defaults(chat.get("defaults")), **(settings(uid) if uid else {}))


def settings(uid):
    try:
        with open(_path(uid, "settings.json")) as f:
            return clean_settings(json.load(f))
    except (OSError, ValueError):
        return {}


def log_name(prof):
    """A profile in a journal line: its name only with its consent ("trace_name", the same switch as for
    Logs → Anfragen and the Live page), else "Profil" and the end of its id, so lines still tell profiles
    apart (Dominik 2026-10-12, docs/de/richtlinien.md: journal lines without names)."""
    if not prof:
        return "guest"
    if settings(prof["id"]).get("trace_name") is True:
        return prof["name"]
    return "Profil " + prof["id"][-4:]


def save_settings(uid, d):
    with _lock:
        merged = dict(settings(uid), **clean_settings(d))
        _write(_path(uid, "settings.json"), merged)
    return merged


# ---------------------------------------------------------------- conversations
MAX_CONVOS, MAX_MSGS, MAX_MSG_LEN = 50, 60, 20000


def convos(uid):
    return read_own(uid, "convos.json", [])


def save_convo(uid, c):
    """Adds or replaces one conversation (newest first); returns it, or None if invalid."""
    item = _clean_convo(c, uid)
    if item:
        with _lock:
            _store_convo(uid, item)
    return item


# called with (uid, conversation id, gone) after a conversation was stored or deleted (verlauf.py: Sofort-Abgleich)
CONVO_HOOKS = []
VIA = ("telegram", "siri", "desk", "watch", "speaker", "telefon")   # the channel a message came through (verlauf.target)
MAX_ATT = 8


def _att(a):
    """What stood under an answer, kept with it so every device shows it again (verlauf-sync point 3): web sources
    (title, http(s) address), the own documents it came from (name, id, page), a document made (title, kind)."""
    out = []
    for x in (a if isinstance(a, list) else [])[:MAX_ATT]:
        if not isinstance(x, dict):
            continue
        k = x.get("k")
        if k == "src" and isinstance(x.get("l"), list):
            items = [{"t": str(i.get("t", ""))[:100], "u": str(i.get("u", ""))[:500]} for i in x["l"][:5]
                     if isinstance(i, dict) and re.match(r"https?://", str(i.get("u", "")))]
            if items:
                out.append({"k": "src", "q": str(x.get("q", ""))[:200], "l": items})
        elif k == "doc" and isinstance(x.get("l"), list):
            items = [{"n": str(i.get("n", ""))[:120], "id": str(i.get("id", ""))[:40] if re.fullmatch(r"[\w\-]{0,40}", str(i.get("id", ""))) else "",
                      "p": i.get("p") if isinstance(i.get("p"), int) and 0 < i.get("p") < 100000 else 0}
                     for i in x["l"][:6] if isinstance(i, dict) and i.get("n")]
            if items:
                out.append({"k": "doc", "l": items})
        elif k == "mk" and x.get("t"):
            out.append({"k": "mk", "t": str(x["t"])[:120], "n": str(x.get("n", ""))[:40]})
        elif k == "bild" and x.get("p"):   # a picture painted for this answer (bilder.py): its prompt and its job, so the
            j = str(x.get("j", ""))     # chat shows the picture again after a reload and on every device
            out.append({"k": "bild", "p": str(x["p"])[:300], **({"j": j} if re.fullmatch(r"[0-9a-f]{12}", j) else {})})
        elif k == "musik" and x.get("p"):   # a song made for this answer (musik.py): its description and its job
            j = str(x.get("j", ""))
            out.append({"k": "musik", "p": str(x["p"])[:300], **({"j": j} if re.fullmatch(r"[0-9a-f]{12}", j) else {})})
    return out


# „Bildschirm beschreiben“ (bedienen.look, Dominik 2026-10-17 „Nur anzeigen“): an answer that described the own
# screen is shown and spoken, but every stored conversation holds SCREEN_NOTE instead, whatever device saves it
SCREEN_NOTE = "(Hier stand eine Beschreibung deines Bildschirms. Sie wird nicht gespeichert.)"
SCREEN_KEEP = 86400       # that long a described screen's answer is recognised when a device saves it
_screen_out = {}          # uid -> [(time, normalized start of such an answer)], memory only


def _norm_start(text):
    return "".join(c for c in str(text or "").casefold() if c.isalnum())[:80]


def keep_screen_out(uid, answer, now=None):
    """chat.py: this answer described the screen; it is never stored (_clean_msg)."""
    n, now = _norm_start(answer), time.time() if now is None else now
    if uid and len(n) >= 12:
        _screen_out[uid] = [x for x in _screen_out.get(uid, []) if now - x[0] < SCREEN_KEEP][-20:] + [(now, n)]


def _screen(uid, m, now=None):
    if m.get("screen"):    # the browser marks it itself (chat.js)
        return True
    now = time.time() if now is None else now
    n = _norm_start(m["content"])
    return bool(uid and n) and any(now - t < SCREEN_KEEP and n.startswith(k) for t, k in _screen_out.get(uid, []))


def _clean_msg(m, uid=None):
    # "mail": an answer made from e-mails (kept out of what the background learner reads)
    screen = m["role"] == "assistant" and _screen(uid, m)
    d = dict({"role": m["role"], "content": SCREEN_NOTE if screen else str(m["content"])[:MAX_MSG_LEN]},
             **({"mail": True} if m.get("mail") else {}),
             # the note is the panel's own sentence: marked "screen", it locks nothing in a later turn (V01.0.752)
             **({"screen": True} if screen else {"outside": True} if m.get("outside") and not m.get("mail") else {}))
    if m.get("via") in VIA:
        d["via"] = m["via"]
    # a card of Offen (vorgaenge.py): only its number; every device draws the card with today's state
    if m["role"] == "assistant" and isinstance(m.get("vg"), str) and re.fullmatch(r"v[0-9a-f]{10}", m["vg"]):
        d["vg"] = m["vg"]
    if m["role"] == "assistant" and m.get("mem"):   # Gemerkt-Hinweis: the facts this answer kept, numbers only
        import gemerkt
        mem = gemerkt.clean(m["mem"])
        if mem:
            d["mem"] = mem
    att = _att(m.get("att")) if m["role"] == "assistant" and not screen else []
    if att:
        d["att"] = att
    return d


def _clean_convo(c, uid=None):
    cid = str(c.get("id", ""))
    if not re.fullmatch(r"[\w\-]{1,40}", cid) or not isinstance(c.get("msgs"), list):
        return None
    msgs = [_clean_msg(m, uid) for m in c["msgs"][-MAX_MSGS:]
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    item = {"id": cid, "title": str(c.get("title", ""))[:80], "msgs": msgs,
            "updated": int(c["updated"]) if isinstance(c.get("updated"), (int, float)) else int(time.time() * 1000)}
    return item


def _store_convo(uid, item):
    rest = [x for x in convos(uid) if x["id"] != item["id"]]
    write_own(uid, "convos.json", sorted([item] + rest, key=lambda x: -x["updated"])[:MAX_CONVOS])
    _tell(uid, item["id"])


def _tell(uid, cid, gone=False):
    for f in CONVO_HOOKS:
        try:
            f(uid, cid, gone)
        except Exception as e:
            print("profiles: convo hook", type(e).__name__, flush=True)


def append_convo(uid, cid, title, msgs):
    """Adds messages to the end of one conversation (made if new), read and written under the lock: two turns at
    the same time (Telegram, a speaker, Siri) each keep their messages (V01.0.405; read, add, save lost one)."""
    with _lock:
        old = next((x for x in convos(uid) if x.get("id") == cid), None)
        c = {"id": cid, "title": title, "updated": int(time.time() * 1000), "msgs": (old["msgs"] if old else []) + list(msgs)}
        item = _clean_convo(c, uid)
        if item:
            _store_convo(uid, item)
    return item


def delete_convo(uid, cid):
    with _lock:
        write_own(uid, "convos.json", [x for x in convos(uid) if x["id"] != cid])
    _tell(uid, cid, gone=True)


# ---------------------------------------------------------------- reminders
MAX_REMINDERS = 50


def reminders(uid):
    try:
        with open(_path(uid, "reminders.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


REPEATS = ("daily", "weekdays", "weekly", "monthly")   # „Erinnere mich jeden Montag an den Müll“


def add_reminder(uid, text, due, every="", made=None):
    item = {"id": secrets.token_hex(4), "text": re.sub(r"\s+", " ", str(text)).strip()[:200], "due": int(due),
            # when it was set (epoch ms): the watch draws a timer's ring from it (pebblewatch.agenda)
            "made": int(made if made is not None else time.time() * 1000)}
    if every in REPEATS:
        item["every"] = every
    with _lock:
        items = sorted(reminders(uid) + [item], key=lambda x: x["due"])[-MAX_REMINDERS:]
        _write(_path(uid, "reminders.json"), items)
    return item


# called once when a reminder rang (take_reminder): vorgaenge.from_reminder makes its card of Offen and returns its number
REMINDER_HOOKS = []


def take_reminder(uid, rid, due_by):
    """The one device that plays a due reminder takes it off the list; every later one gets None
    (one ring for the whole profile, not one per device). Only when it is due by due_by (ms)."""
    with _lock:
        items = reminders(uid)
        item = next((x for x in items if x.get("id") == rid and x.get("due", 0) <= due_by), None)
        if item is not None:
            keep = [x for x in items if x is not item]
            nxt = next_due(item, settings(uid).get("tz", "")) if item.get("every") in REPEATS else None
            if nxt:   # a repeating reminder comes back at its next time (a new id: each ring is taken once)
                keep = sorted(keep + [dict(item, id=secrets.token_hex(4), due=nxt)], key=lambda x: x["due"])[-MAX_REMINDERS:]
            _write(_path(uid, "reminders.json"), keep)
    if item is not None:
        for f in REMINDER_HOOKS:   # outside the lock: a hook may write the conversation (vorgaenge.from_reminder)
            try:
                item = dict(item, vg=f(uid, item) or "")
            except Exception as e:
                print("profiles: reminder hook", type(e).__name__, flush=True)
    return item


def next_due(item, tz=""):
    """The next time of a repeating reminder (epoch ms), in local time so it stays at its clock time over DST."""
    import datetime
    import zoneinfo
    try:
        zone = zoneinfo.ZoneInfo(tz) if tz else zoneinfo.ZoneInfo("Europe/Berlin")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        zone = zoneinfo.ZoneInfo("Europe/Berlin")
    at = datetime.datetime.fromtimestamp(item["due"] / 1000, zone)
    now = time.time() * 1000
    for _ in range(400):
        every = item.get("every")
        if every == "daily":
            at = at + datetime.timedelta(days=1)
        elif every == "weekdays":
            at = at + datetime.timedelta(days=3 if at.weekday() == 4 else 2 if at.weekday() == 5 else 1)
        elif every == "weekly":
            at = at + datetime.timedelta(days=7)
        elif every == "monthly":
            y, m = (at.year + 1, 1) if at.month == 12 else (at.year, at.month + 1)
            at = at.replace(year=y, month=m, day=min(at.day, 28))
        else:
            return None
        at = at.replace(tzinfo=zone)
        due = int(datetime.datetime(at.year, at.month, at.day, at.hour, at.minute, tzinfo=zone).timestamp() * 1000)
        if due > now:
            return due
    return None


def remove_reminders(uid, ids):
    with _lock:
        items = reminders(uid)
        keep = [x for x in items if x["id"] not in ids]
        _write(_path(uid, "reminders.json"), keep)
    return len(items) - len(keep)


# ---------------------------------------------------------------- memory
def memory(uid):
    return read_own(uid, "memory.json", [])


MAX_PREV = 5   # earlier wordings kept per fact (gedaechtnis.py, Fassungen)


def _keep_prev(item, why, now):
    """The fact's wording so far becomes its newest earlier version (why: fix, hand, nachfrage, zurueck)."""
    old = {"text": item["text"], "until": now, "why": why,
           "src": item.get("src") or ("auto" if item.get("auto") else "said")}
    for k in ("confirmed", "changed"):   # kept so „Rückgängig“ (undo_fact) brings the wording back as it was
        if item.get(k):
            old[k] = item[k]
    item["prev"] = ([old] + [p for p in item.get("prev") or [] if isinstance(p, dict)])[:MAX_PREV]


class _Full:
    """remember's answer when the memory holds MAX_FACTS facts and none of them may go (_cap): falsy like None, so
    every caller that only asks „saved?“ stays right; memory_save and „Aus Korrekturen lernen“ say why."""
    def __bool__(self):
        return False

    def __repr__(self):
        return "profiles.FULL"


FULL = _Full()
# what the model hears when memory_save meets a full memory (starts with a word of taten.FAILED, with the way to tidy up)
FULL_TEXT = (f"Not done: the memory is full ({MAX_FACTS} entries the user said or confirmed, and the Spark never throws "
             "one of those away). Tell the user in one short sentence that nothing new can be remembered until they "
             "tidy up under Ich → Gedächtnis („Aufräumen vorschlagen“) or delete entries there.")
FULL_LOG_S = 86400   # „gedaechtnis: voll“ once a day per profile, with when the next line may come (no log flood)
_full_said = {}      # uid -> when the last „voll“ line was written


def _droppable(f):
    """A fact the cap may take: learned by the Spark itself (src auto) and never confirmed by the person."""
    import gedaechtnis
    return gedaechtnis.source(f) == "auto" and not gedaechtnis.confirmed(f)


def _cap(facts, keep=None):
    """At most MAX_FACTS facts without losing what the person said (plan nutzerwissen, Punkt 4): over the cap the oldest
    learned, never confirmed facts go first; said, corrected, changed by hand, tidied or confirmed facts never go, nor
    keep (the fact just added). Earlier versions (prev) do not count. Returns (facts, how many went); the list stays
    over MAX_FACTS when only protected facts are left, and then nothing at all goes (the caller decides)."""
    over = len(facts) - MAX_FACTS
    if over <= 0:
        return facts, 0
    old = sorted((x for x in facts if x is not keep and _droppable(x)), key=lambda x: int(x.get("created") or 0))
    if len(old) < over:
        return facts, 0
    gone = {id(x) for x in old[:over]}
    return [x for x in facts if id(x) not in gone], over


def memory_full(uid, facts=None):
    """True when a new fact would be refused: MAX_FACTS facts or more and none of them learned and unconfirmed."""
    facts = memory(uid) if facts is None else facts
    return len(facts) >= MAX_FACTS and not any(_droppable(x) for x in facts)


def _log_full(who, src):
    """The line when the memory is full; who is profiles.log_name (remember writes it once a day per profile)."""
    print(f"gedaechtnis: voll {who} | abgelehnt={'auto' if src == 'auto' else 'said'} "
          f"max={MAX_FACTS} | next log in {FULL_LOG_S // 3600} h", flush=True)


def log_freed(uid, gone):
    """The line when the cap took old learned facts (remember, memtidy.apply)."""
    if gone:
        print(f"gedaechtnis: platz frei {log_name(by_id(uid))} | entfernt={gone} grund=alt-gelernt", flush=True)


def remember(uid, text, auto=False, src=None, convo=None, version=None):
    """Keeps a fact with its evidence (gedaechtnis.py): src said (memory_save in a conversation), fix (a confirmed
    correction), auto (learned from a quiet conversation), the conversation it came from and, when the person said
    it, the time it counts as confirmed. With „Gedächtnis prüfen“ on, a fact about a fixed place (gedaechtnis.SLOTS,
    „wohnt in“, „Bruder heißt“) gives the fact that holds it the new wording and keeps the old one as an earlier
    version (why: version or „platz“), instead of a second fact beside it; a value learned by itself (auto) never
    replaces one the person said or confirmed: it waits there as an offer (card „Übernehmen / Verwerfen“). Returns the
    text kept, None (nothing to keep, or only offered) or FULL (only protected facts left at MAX_FACTS: nothing is
    thrown away, the new fact is refused, _cap)."""
    import features
    import gedaechtnis
    text = re.sub(r"\s+", " ", str(text)).strip()[:MAX_FACT_LEN]
    if not text:
        return None
    src = src if src in gedaechtnis.SRC else "auto" if auto else "said"
    name = str((by_id(uid) or {}).get("name") or "")
    kv = gedaechtnis.slot_of(text, name) if features.allowed("gedpruefen", uid) else None
    res = None    # what happened: ("offer", fact), ("place", id of a closed offer), ("new", how many went), ("full", log)
    with _lock:
        facts = memory(uid)
        now = int(time.time())
        item = gedaechtnis.holder(facts, kv[0], name) if kv else None
        if item is not None and src == "auto" and gedaechtnis.confirmed(item):
            # learned by itself against a value the person said or confirmed: only an offer, never a replacement
            if gedaechtnis.offer(item, text, convo, now, name):
                write_own(uid, "memory.json", facts)
                res = ("offer", dict(item))
        elif item is not None:
            if item["text"] != text:
                _keep_prev(item, version or "platz", now)
            item["text"], item["src"], item["changed"] = text, src, now
            closed = None
            if src != "auto":
                item["confirmed"] = now
                item.pop("auto", None)
                closed = item["id"] if item.pop("offer", None) else None
            if gedaechtnis.clean_convo(convo):
                item["convo"] = convo
            # the same sentence twice would be noise: an older twin goes
            facts = [x for x in facts if x is item or x["text"].lower() != text.lower()]
            write_own(uid, "memory.json", facts)
            res = ("place", closed)
        else:
            facts = [x for x in facts if x["text"].lower() != text.lower()]
            item = {"id": secrets.token_hex(4), "text": text, "created": now, "src": src}
            if src == "auto":  # learned from a conversation, not asked for
                item["auto"] = True
            else:
                item["confirmed"] = now
            if gedaechtnis.clean_convo(convo):
                item["convo"] = convo
            facts.append(item)
            facts, gone = _cap(facts, keep=item)
            if len(facts) > MAX_FACTS:   # only protected facts left: refuse the new one rather than lose an old one
                log = now - _full_said.get(uid, 0) >= FULL_LOG_S   # once a day per profile (Richtlinie Teil 4)
                if log:
                    _full_said[uid] = now
                res = ("full", log)
            else:
                write_own(uid, "memory.json", facts)
                res = ("new", gone)
    if res is None:          # learned by itself, the same value as the confirmed one or asked before: nothing new
        return None
    if res[0] == "offer":
        gedaechtnis.offer_card(uid, res[1])
        print(f"gedaechtnis: angebot {log_name(by_id(uid))} | platz={gedaechtnis.slot_base(kv[0])}", flush=True)
        return None
    if res[0] == "full":
        if res[1]:
            _log_full(log_name(by_id(uid)), src)
            gedaechtnis.full_card(uid, True)   # „Gedächtnis voll – aufräumen“ (at most with the daily line)
        return FULL
    if res[0] == "place":
        if res[1]:
            gedaechtnis.close_card(uid, res[1])
        gedaechtnis.log_version(uid, version or "platz")
        return text
    log_freed(uid, res[1])
    print(f"gedaechtnis: fact saved | {src} | {log_name(by_id(uid))}", flush=True)   # never the fact itself
    return text


def change_fact(uid, fact_id, text):
    """The person's own wording for a fact (Ich → Gedächtnis → Ändern); the fact counts as told, no longer as
    learned. Returns the new text, or None when the fact is gone or the text is empty."""
    text = re.sub(r"\s+", " ", str(text)).strip()[:MAX_FACT_LEN]
    if not text:
        return None
    with _lock:
        facts = memory(uid)
        item = next((x for x in facts if x["id"] == fact_id), None)
        if not item:
            return None
        now = int(time.time())
        if item["text"] != text:
            _keep_prev(item, "hand", now)
        item["text"] = text
        item.pop("auto", None)
        item["changed"] = item["confirmed"] = now
        item["src"] = "hand"
        # the same sentence twice would be noise: an older twin goes
        facts = [x for x in facts if x is item or x["text"].lower() != text.lower()]
        write_own(uid, "memory.json", facts)
    return text


def restore_fact(uid, fact_id, i):
    """„Zurückholen“: earlier version i becomes the fact's wording again, the wording so far an earlier version.
    Returns the fact, or None when the fact or the version is gone."""
    with _lock:
        facts = memory(uid)
        item = next((x for x in facts if x["id"] == fact_id), None)
        prev = [p for p in (item or {}).get("prev") or [] if isinstance(p, dict) and p.get("text")]
        if not item or not 0 <= i < len(prev):
            return None
        back, now = prev.pop(i), int(time.time())
        item["prev"] = prev
        _keep_prev(item, "zurueck", now)
        item["text"], item["src"], item["changed"] = back["text"][:MAX_FACT_LEN], "hand", now
        item["confirmed"] = now
        item.pop("auto", None)
        write_own(uid, "memory.json", facts)
    return item


def undo_fact(uid, fact_id, ok):
    """Gemerkt-Hinweis „Rückgängig“ (gemerkt.py): takes back what remember just did to one fact. A new fact goes; a
    fixed place it gave a new wording gets its earlier version 0 back as it was (source, confirmation, change time),
    and the undone wording is not kept as a version. ok(item) is the caller's check under the lock (the fact is
    unchanged since it was saved). Returns "geloescht" or "zurueckgeholt", or why not: "fehlt", "geaendert" or
    "gleich" (the same wording said again: nothing to take back)."""
    import gedaechtnis
    with _lock:
        facts = memory(uid)
        item = next((x for x in facts if x["id"] == fact_id), None)
        if item is None:
            return "fehlt"
        if not ok(item):
            return "geaendert"
        prev = [p for p in item.get("prev") or [] if isinstance(p, dict) and p.get("text")]
        if not item.get("changed"):
            was_full = memory_full(uid, facts)
            facts = [x for x in facts if x is not item]
            write_own(uid, "memory.json", facts)
            how = "geloescht"
        elif prev and prev[0].get("until") == item["changed"]:
            back = prev.pop(0)
            was_full = False
            item["prev"], item["text"] = prev, str(back["text"])[:MAX_FACT_LEN]
            item["src"] = back.get("src") if back.get("src") in gedaechtnis.SRC else "said"
            for k in ("confirmed", "changed"):
                if back.get(k):
                    item[k] = back[k]
                else:
                    item.pop(k, None)
            if item["src"] == "auto":
                item["auto"] = True
            else:
                item.pop("auto", None)
            write_own(uid, "memory.json", facts)
            how = "zurueckgeholt"
        else:
            return "gleich"
    if was_full:   # room again: the card „Gedächtnis voll“ closes (as in forget)
        gedaechtnis.full_card(uid, False)
    return how


def forget(uid, fact_id=None, text=None):
    """Removes one fact by id, or the facts containing text; returns how many went."""
    with _lock:
        facts = memory(uid)
        if isinstance(fact_id, (list, tuple, set)):
            ids = set(fact_id)
            keep = [x for x in facts if x["id"] not in ids]
        elif fact_id:
            keep = [x for x in facts if x["id"] != fact_id]
        elif text:
            t = str(text).lower().strip()
            keep = [x for x in facts if t not in x["text"].lower()]
        else:
            keep = []
        write_own(uid, "memory.json", keep)
    if len(keep) < len(facts) and memory_full(uid, facts):   # room again: the card „Gedächtnis voll“ closes
        import gedaechtnis
        gedaechtnis.full_card(uid, False)
    print(f"gedaechtnis: {len(facts) - len(keep)} fact(s) forgotten | {log_name(by_id(uid))}", flush=True)
    return len(facts) - len(keep)


# ---------------------------------------------------------------- tool log
# What the assistant looked up per turn (question, tools with arguments and a short result, the
# answer), so the person can see where an answer came from. Only the profile's own turns, short
# texts, and only for a few days.
TOOL_LOG_DAYS, TOOL_LOG_MAX = 7, 200


def tool_log(uid):
    items = read_own(uid, "toollog.json", [])
    cut = (time.time() - TOOL_LOG_DAYS * 86400) * 1000
    return [x for x in items if isinstance(x, dict) and x.get("t", 0) >= cut] if isinstance(items, list) else []


def tool_log_add(uid, question, calls, answer):
    item = {"t": int(time.time() * 1000), "q": str(question)[:300], "answer": str(answer).strip()[:600],
            "calls": [{"name": str(c["name"])[:60], "args": str(c["args"])[:300], "result": str(c["result"])[:600]}
                      for c in calls[:12]]}
    with _lock:
        write_own(uid, "toollog.json", (tool_log(uid) + [item])[-TOOL_LOG_MAX:])


def tool_log_clear(uid):
    with _lock:
        write_own(uid, "toollog.json", [])
