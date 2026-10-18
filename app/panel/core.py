"""Shared panel helpers: paths, logins (admin password, profiles) and small system calls."""
import os
import re
import asyncio
import hashlib
import hmac
import json
import secrets
import sys
import threading
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import coadmin  # noqa: E402
import guard  # noqa: E402
import mfa  # noqa: E402
import passkey  # noqa: E402
import profiles  # noqa: E402
import stufen  # noqa: E402
from common import OWN_LLM_UNITS, PREFIX, SERVICES, STATE, UNITS, load_config, run  # noqa: E402,F401


VOICES_DIR = os.environ.get("SPEECH_SPARK_VOICES", "/var/lib/speech-spark/voices")
PASSWORD = os.environ.get("PANEL_PASSWORD", "")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
LOG_UNITS = dict(UNITS, panel="speech-spark-panel", update="speech-spark-update", wechsel="speech-spark-wechsel", **OWN_LLM_UNITS)
# asr keys the vLLM engine reads; changing them restarts it
ASR_ENGINE_KEYS = ("model", "engine_port", "engine_mem", "engine_max_seqs")
# tts keys that only the vllm-omni engine reads; changing them restarts the engine
ENGINE_KEYS = ("model", "engine_port", "engine_mem_talker", "engine_mem_code2wav", "engine_max_seqs",
               "engine_max_model_len", "initial_chunk_frames", "engine_decode_batch", "engine_prefix_cache")
DESIGN_KEYS = ("voicedesign_enabled", "voicedesign_model", "voicedesign_port",
               "engine_mem_talker", "engine_mem_code2wav", "engine_max_seqs", "engine_max_model_len", "initial_chunk_frames",
               "engine_decode_batch", "engine_prefix_cache")
LANGS = ["auto", "Chinese", "English", "German", "French", "Spanish", "Italian", "Portuguese",
         "Russian", "Japanese", "Korean", "Dutch", "Polish", "Turkish", "Arabic"]
security = HTTPBasic(auto_error=False)


# Login: the voice assistant is open to everyone in the LAN (config chat.public), everything
# else needs the panel password. The browser logs in once and keeps a cookie; scripts can still
# send HTTP Basic. The password from the installer can be replaced in the panel; the new one is
# stored as a PBKDF2 hash in the state directory (the panel cannot write /etc).
PASSWORD_FILE = os.path.join(STATE, "panel-password")
COOKIE = "speech_spark_admin"
# Browsers keep sending HTTP Basic credentials from the old login dialog; after "log out" this
# cookie makes the panel ignore them in that browser until the next password login.
NO_BASIC = "speech_spark_no_basic"


async def json_body(request: Request, limit, lenient=False):
    """The request's JSON object, read in pieces and never more than limit bytes (413 above it, also when the
    announced length says so). Broken JSON or no object: 400, or {} with lenient (what older apps send). The one
    reader of a request body (Große Aufräumaktion step 4)."""
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > limit:
        raise HTTPException(413, "too large")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise HTTPException(413, "too large")
    try:
        d = json.loads(bytes(raw) or b"{}")
    except ValueError:
        d = None
    if isinstance(d, dict):
        return d
    if lenient:
        return {}
    raise HTTPException(400, "invalid JSON")


def _stored_hash():
    try:
        with open(PASSWORD_FILE) as f:
            salt, digest = f.read().split()
        return bytes.fromhex(salt), digest
    except (OSError, ValueError):
        return None


ROUNDS = 200_000   # PBKDF2 rounds of the admin password (self-tests lower it for speed only, test_tempo checks this)


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ROUNDS).hex()


def password_set():
    return bool(_stored_hash() or PASSWORD)


def store_password(new):
    """Writes the panel password's hash (Einstellungen → Sicherheit, and sudo speech-spark notzugang)."""
    salt = secrets.token_bytes(16)
    os.makedirs(os.path.dirname(PASSWORD_FILE), exist_ok=True)
    tmp = PASSWORD_FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(f"{salt.hex()} {_hash(new, salt)}\n")
    os.replace(tmp, PASSWORD_FILE)


def check_password(password):
    stored = _stored_hash()
    if stored:
        return secrets.compare_digest(_hash(password, stored[0]), stored[1])
    return bool(PASSWORD) and secrets.compare_digest(password.encode(), PASSWORD.encode())


# The admin login "<issued>.<family>.<signature>" is signed with the current password and the second
# step's key (changing either logs every browser out) and ends after ADMIN_IDLE seconds without use;
# the panel renews it while used. A renewal keeps the family (one per login), so logging out ends
# every copy of that login, also older renewed ones.
ADMIN_IDLE = 7 * 86400
ADMIN_RENEW = 3600


SESSION_KEY_FILE = os.path.join(os.path.dirname(PASSWORD_FILE), "admin-session.key")


def _session_key():
    """A random key of this Spark only, never in a backup: a backup file alone (which holds the password
    hash) must not be enough to make an admin login."""
    try:
        with open(SESSION_KEY_FILE) as f:
            k = f.read().strip()
        if len(k) >= 32:
            return k
    except OSError:
        pass
    k = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(SESSION_KEY_FILE), exist_ok=True)
        with open(os.open(SESSION_KEY_FILE + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
            f.write(k)
        os.replace(SESSION_KEY_FILE + ".tmp", SESSION_KEY_FILE)
    except OSError:
        pass
    return k


def _session_token(issued=None, family=None):
    stored = _stored_hash()
    key = (_session_key() + (stored[1] if stored else PASSWORD) + mfa.session_salt(mfa.ADMIN)).encode()
    issued = int(issued or time.time())
    family = family or secrets.token_hex(8)
    sig = hmac.new(key, f"speech-spark-admin-session:{issued}:{family}".encode(), hashlib.sha256).hexdigest()
    return f"{issued}.{family}.{sig}"


def admin_family(raw):
    parts = (raw or "").split(".")
    return parts[1] if len(parts) == 3 and re.fullmatch(r"[0-9a-f]{16}", parts[1]) else None


def _admin_cookie_age(request: Request):
    """Seconds since the admin cookie was issued, or None when it is missing, wrong or expired."""
    raw = request.cookies.get(COOKIE, "")
    issued, family = raw.split(".", 1)[0], admin_family(raw)
    if not issued.isdigit() or not family or time.time() - int(issued) > ADMIN_IDLE or guard.revoked(raw) \
            or guard.revoked("admin-family:" + family):
        return None
    return time.time() - int(issued) if secrets.compare_digest(raw, _session_token(issued, family)) else None


def end_admin_sessions():
    """Logs every admin browser out (a new session key)."""
    try:
        os.remove(SESSION_KEY_FILE)
    except OSError:
        pass


def is_main_admin(request: Request, creds: HTTPBasicCredentials | None):
    """The main admin (the panel password): browser login or HTTP Basic."""
    if not password_set():
        return True
    # HTTP Basic (scripts) knows no second step, so it is off while the admin has one
    # wrong guesses count per address and against the admin password itself (from anywhere), like the login page
    if creds and not request.cookies.get(NO_BASIC) and not mfa.enabled(mfa.ADMIN) \
            and not guard.wait_left(request, guard.BASIC) and not guard.wait_left(request, guard.ADMIN):
        if check_password(creds.password):
            return True
        guard.failed(request, guard.BASIC, what="admin_basic")
        guard.failed(request, guard.ADMIN, what="admin_basic")
    return _admin_cookie_age(request) is not None


def is_admin(request: Request, creds: HTTPBasicCredentials | None):
    """The main admin (panel password), or an admin profile whose role reaches this request (coadmin.py): its own
    browser login or its iPhone app, no second stage (plan plaene/admin-ohne-zweite-stufe.md)."""
    if is_main_admin(request, creds):
        request.scope["speech_main_admin"] = True
        return True
    return coadmin.allows(request)


def acting_profile(request: Request):
    """The admin profile behind this admin request ({"id", "name", "role", ...}), None for the main admin."""
    return None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")


def admin_cookie_ok(request: Request):
    return not password_set() or _admin_cookie_age(request) is not None


def renewed_admin_cookie(request: Request):
    age = _admin_cookie_age(request)
    return _session_token(family=admin_family(request.cookies.get(COOKIE, ""))) \
        if age is not None and age > ADMIN_RENEW else None


def auth(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    if not is_admin(request, creds):
        raise HTTPException(403 if coadmin.session(request) else 401, "login required")


def main_auth(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    """Only the panel password (Notzugang): the password itself, its own second step, signing it out everywhere.
    Everything else an admin may, an admin profile may too (auth)."""
    if is_main_admin(request, creds):
        request.scope["speech_main_admin"] = True
        return
    if coadmin.session(request):
        raise HTTPException(403, "Das gehört zum Notzugang (Panel-Passwort).")
    raise HTTPException(401, "login required")


# Changes that matter most (password, restore, device keys, the second step itself) need a fresh code
# from the app while the second step is on, even inside a running login: header X-Speech-Code.
CODE_HEADER = "x-speech-code"
# One right code counts for CONFIRM_WINDOW seconds in the same login (plan plaene/zweiter-schritt-seltener.md,
# "sudo" window): the admin's login, the profile's browser login or the iPhone app's key, never another one.
# Admins (the panel password, a profile with a role) are never asked at the level "Bestätigen", only for
# "Schutz ändern" (plan plaene/admin-ohne-zweite-stufe.md, Dominik „A2“): admin_login().
# Kept in memory only (a restart of the panel ends it); logging out and the button
# "Bestätigung beenden" end it too. The most important changes ask every time (fresh=True).
CONFIRM_WINDOW = 600
MAX_WINDOWS = 200
_windows = {}                     # (who, login) -> until
_wlock = threading.Lock()


def _login_key(request: Request, who):
    """The login this request comes with, for `who`: "d:<device>" (its app key), "a:<family>" (the main admin's
    browser login) or "p:<session>" (the profile's browser login, also an admin profile's). Only
    checked logins count; None without one (HTTP Basic, a foreign cookie)."""
    if request.headers.get(profiles.DEVICE_HEADER):
        dev = profiles._device(profiles._load(), request)
        return "d:" + dev["id"] if dev and dev.get("user") == who else None
    if who == mfa.ADMIN:
        fam = admin_family(request.cookies.get(COOKIE, ""))
        return "a:" + fam if fam and _admin_cookie_age(request) is not None else None
    raw = request.cookies.get(profiles.COOKIE, "")
    u, _ = profiles._cookie_user(profiles._load(), raw)
    return "p:" + raw.split(".")[2] if u and u["id"] == who and raw.count(".") == 3 else None


def confirm_login(request: Request, who):
    """The login a confirmation (code, passkey) of `who` in this request belongs to (see _login_key)."""
    return _login_key(request, who)


def window_until(who, login, now=None):
    now = now if now is not None else time.time()
    with _wlock:
        until = _windows.get((who, login), 0) if login else 0
    return until if until > now else 0


def _open_window(who, login, now=None):
    if not login:
        return
    now = now if now is not None else time.time()
    with _wlock:
        for k in [k for k, v in _windows.items() if v <= now]:
            _windows.pop(k)
        if len(_windows) >= MAX_WINDOWS:
            _windows.pop(min(_windows, key=_windows.get))
        _windows[(who, login)] = now + CONFIRM_WINDOW


def end_window(request: Request):
    """Ends every confirmation window of the logins this request carries."""
    keys = set()
    for who in [mfa.ADMIN] + [x for x in (_cookie_uid(request), _device_uid(request)) if x]:
        k = _login_key(request, who)
        if k:
            keys.add((who, k))
    with _wlock:
        for k in keys:
            _windows.pop(k, None)
    return len(keys)


def _cookie_uid(request):
    u, _ = profiles._cookie_user(profiles._load(), request.cookies.get(profiles.COOKIE, ""))
    return u["id"] if u else None


def _device_uid(request):
    if not request.headers.get(profiles.DEVICE_HEADER):
        return None
    dev = profiles._device(profiles._load(), request)
    return dev.get("user") if dev else None


def admin_login(request: Request):
    """This request comes from an admin: the panel password's login or an admin profile (any role). Admins are
    not asked at the level "Bestätigen" (stufen.CONFIRM)."""
    if password_set() and _admin_cookie_age(request) is not None:
        return True
    return coadmin.session(request) is not None


def confirmed_until(request: Request):
    """Until when a right code still counts in this request's login (whoami shows it), 0 when it does not."""
    if is_main_admin(request, None) and mfa.enabled(mfa.ADMIN):
        return int(window_until(mfa.ADMIN, _login_key(request, mfa.ADMIN)))
    uid = _device_uid(request) or _cookie_uid(request)
    return int(window_until(uid, _login_key(request, uid))) if uid and mfa.enabled(uid) else 0


def code_name(who, name):
    """Whose code the dialog asks for: the person's name; for the panel password the main admin's profile
    (mfa.linked, one code per person) or „Notzugang"."""
    if who == mfa.ADMIN:
        uid = mfa.linked()
        return next((u["name"] for u in profiles.names() if u["id"] == uid), "Notzugang") if uid else "Notzugang"
    return str(name or "")


async def confirm_code(request: Request, who, name, fresh=False):
    """A code from the authenticator app (or a recovery code) in X-Speech-Code, or a passkey's signature in
    X-Speech-Passkey (passkey.py); the 428 answer carries the passkey challenge when the person has one here."""
    if not mfa.enabled(who):
        return
    # the list decides whether a code from the last minutes counts (stufen.py, "Bestätigen") or not ("Schutz ändern")
    lvl = stufen.level(request, fresh)
    login = _login_key(request, who)
    if lvl != stufen.PROTECT and (window_until(who, login) or admin_login(request)):
        return
    answer = passkey.header_answer(request)
    code = request.headers.get(CODE_HEADER, "")
    ask = lambda: {**passkey.options_header(who, request, login), **stufen.header(request, lvl, code_name(who, name))}   # noqa: E731
    if answer is None and not code:
        raise HTTPException(428, "code required", headers=ask())
    guard.check(request, name)
    ok = passkey.finish_auth(who, answer, request, login) if answer is not None else mfa.verify(who, code)
    if not ok:
        guard.failed(request, name, what="code")
        await asyncio.sleep(1)
        raise HTTPException(428, "wrong code", headers=ask())
    guard.succeeded(request, name)
    _open_window(who, login)


async def _admin_code(request, fresh):
    # the admin profile behind the request answers with its own code (or passkey), the panel password with its own
    prof = acting_profile(request)
    if prof:
        await confirm_code(request, prof["id"], prof["name"], fresh)
    else:
        await confirm_code(request, mfa.ADMIN, guard.ADMIN, fresh)


async def admin_code(request: Request):
    """A code for important changes: the main admin's, or the code of the admin profile behind the request. A right
    code from the last CONFIRM_WINDOW seconds in the same login counts too."""
    await _admin_code(request, False)


async def admin_code_fresh(request: Request):
    """Always a fresh code: the second step itself, the password, roles, backups (no confirmation window)."""
    await _admin_code(request, True)


def assistant(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    """Voice chat endpoints: open when chat.public is on; otherwise for logged-in profiles (cookie or
    device key) and the admin, so guests are locked out but profiles can still sign in."""
    if load_config().get("chat", {}).get("public", False) or profiles.current(request):
        return
    closed = request.scope.get("speech_gate_closed")
    if closed and not creds:   # a known device, its function off right now: keep the pairing (profiles._gate_closed)
        raise HTTPException(503, "Mein Notaus hält dieses Gerät an." if closed == "notaus"
                            else "Für dieses Gerät gerade ausgeschaltet (Personen und Geräte → Gesperrte Funktionen).")
    auth(request, creds)


# Tasks started with spawn(): asyncio keeps only a weak reference, so a running task could be collected
# mid-way; and a background loop that ends with an error would vanish without a word in the log.
_tasks = set()


def spawn(coro, name=None):
    """asyncio.create_task that keeps the task until it is done and logs an error it ends with."""
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_done)
    return task


def _done(task):
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        e = task.exception()
        print(f"hintergrund: background task {task.get_name()} ended: {type(e).__name__}: {str(e)[:200]}", flush=True)


def app_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return ""


def own_profile(request: Request):
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "no profile")
    return prof


def browser_profile(request: Request):
    """The profile of a browser login. Device keys (Siri, watch, speakers, own programs) may talk to the
    assistant but not change the profile's connections, devices or security."""
    prof = own_profile(request)
    if request.scope.get("speech_app_area"):
        return prof   # a panel area the profile opened for its iPhone app (iphone.py AREAS, own switch per area)
    if request.headers.get(profiles.DEVICE_HEADER) or request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
        raise HTTPException(403, "only in the profile's own browser login")
    return prof


async def _secret_profile(request, fresh):
    """Like browser_profile, plus a fresh code when the profile has the second step: for changes that
    hand out secrets (tokens, passwords, code word) or add a new way to reach the profile. From the iPhone
    app always with a fresh code: the profile needs its second step for that."""
    prof = browser_profile(request)
    if request.scope.get("speech_app_area") and not mfa.enabled(prof["id"]):
        raise HTTPException(403, "Dafür braucht dein Profil den zweiten Anmeldeschritt (Ich → Sicherheit).")
    await confirm_code(request, prof["id"], prof["name"], fresh)
    return prof


async def secret_profile(request: Request):
    return await _secret_profile(request, False)


async def secret_profile_fresh(request: Request):
    """Like secret_profile, always with a fresh code (the code word, the second step itself)."""
    return await _secret_profile(request, True)


def _gate(key, why, request):
    """The admin switch, and not blocked for the profile behind this request (Personen und Geräte → Gesperrte Funktionen)."""
    import features   # features.py imports this module
    if not features.admin_on(key):
        raise HTTPException(403, why)
    prof = profiles.current(request)
    if prof and features.blocked(key, prof["id"]):
        raise HTTPException(403, "blocked for this profile by the admin (Personen und Geräte → Gesperrte Funktionen)")


# Calendar and briefing topics: profiles only; the stored password is never sent back.
def calendar_on(request: Request):
    _gate("calendar", "calendar and daily briefing are turned off", request)


# Home Assistant: each profile connects its own; the token is never sent back.
def ha_on(request: Request):
    _gate("ha", "Home Assistant is turned off", request)


# E-mail: each profile connects its own mailboxes, read only; the password is never sent back.
def mail_on(request: Request):
    _gate("mail", "reading e-mail is turned off", request)


def speaker_on(request: Request):
    _gate("speaker", "speaker identification is turned off", request)


def api_headers():
    key = load_config().get("api", {}).get("key", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


# the assistant's faces (static/js/face.js): the admin picks the Spark's (chat.face), a profile its own (profiles.face_of)
FACES = profiles.FACES

DEFAULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.default.json")
