"""Second login step: a six-digit code from an authenticator app (TOTP, RFC 6238), or a one-time
recovery code when the phone is gone.

Who has it: the admin (STATE/mfa-admin.json) and every profile that switched it on for itself
(USERS_DIR/<uid>/mfa.json). The app secret is stored encrypted (vault.py); the recovery codes only as
hashes. Each file also holds "tkey", which signs "trust this browser for 30 days" cookies and, for the
admin, the login cookie: a new setup, switching it off or "forget trusted browsers" replaces it, and
with it every trusted browser (and every other admin login) ends.

Device keys (speakers, Siri, Pebble, phone) are not asked for a code: they are made by the admin, who
confirms that with a code.

Admin locked out (phone and recovery codes lost): sudo rm /var/lib/speech-spark/state/mfa-admin.json
A profile locked out: the admin resets it under Profile.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import threading
import time
from urllib.parse import quote

import profiles
import vault

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
ADMIN = "admin"
STEP, DIGITS, DRIFT = 30, 6, 1          # 30 s codes; one step early or late still counts
RECOVERY_COUNT = 10
TRUST_DAYS = 30
PENDING_SECS = 900                       # a started setup must be confirmed within 15 minutes
ISSUER = "Speech Spark"
_lock = threading.Lock()
_pending = {}                            # who -> (secret, started)


def _path(who):
    if who == ADMIN:
        return os.path.join(STATE, "mfa-admin.json")
    if not re.fullmatch(r"u_[0-9a-f]{12}", str(who)):
        raise ValueError("bad profile id")
    return os.path.join(profiles.USERS_DIR, who, "mfa.json")


def _read(who):
    try:
        with open(_path(who)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("secret") else None
    except (OSError, ValueError):
        return None


def _write(who, d):
    p = _path(who)
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    tmp = p + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f)
    os.replace(tmp, p)


def enabled(who):
    return _read(who) is not None


def status(who):
    d = _read(who)
    return {"on": bool(d), "codes_left": len(d.get("recovery", [])) if d else 0, "since": d.get("since") if d else None}


# ---------------------------------------------------------------- codes
def _totp(secret_b32, counter):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS).zfill(DIGITS)


def _match(secret_b32, code, after=-1, now=None):
    """The time step the code belongs to, or None. Steps up to `after` are used up (no replay)."""
    now = int(now if now is not None else time.time()) // STEP
    for c in range(now - DRIFT, now + DRIFT + 1):
        if c > after and secrets.compare_digest(_totp(secret_b32, c), code):
            return c
    return None


def _norm(code):
    return re.sub(r"[\s\-]", "", str(code or "")).lower()[:32]


def _rhash(code):
    return hashlib.sha256(("speech-spark-recovery:" + _norm(code)).encode()).hexdigest()


def _new_recovery():
    abc = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i
    return ["".join(secrets.choice(abc) for _ in range(4)) + "-" + "".join(secrets.choice(abc) for _ in range(4))
            for _ in range(RECOVERY_COUNT)]


def verify(who, code):
    """True for the current app code (each one only once) or an unused recovery code (then used up).
    Always True when the second step is off for `who`."""
    c = _norm(code)
    with _lock:
        d = _read(who)
        if not d:
            return True
        if not c:
            return False
        if re.fullmatch(r"\d{%d}" % DIGITS, c):
            secret = vault.open_(d["secret"])
            step = _match(secret, c, int(d.get("last", -1))) if secret else None
            if step is None:
                return False
            d["last"] = step
            _write(who, d)
            return True
        h = _rhash(c)
        if h in d.get("recovery", []):
            d["recovery"].remove(h)
            _write(who, d)
            return True
        return False


# ---------------------------------------------------------------- setup
def begin(who, label):
    """Starts a setup: a new secret, kept here until confirmed with a code from the app."""
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    with _lock:
        _pending[who] = (secret, time.time())
    uri = (f"otpauth://totp/{quote(ISSUER)}:{quote(label)}?secret={secret}&issuer={quote(ISSUER)}"
           f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")
    return {"secret": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)), "uri": uri, "qr": _qr_svg(uri)}


def finish(who, code):
    """Confirms the setup with the app's code; returns the recovery codes (shown once) or None."""
    with _lock:
        secret, started = _pending.get(who, (None, 0))
        if not secret or time.time() - started > PENDING_SECS:
            return None
        step = _match(secret, _norm(code))
        if step is None:
            return None
        _pending.pop(who, None)
        codes = _new_recovery()
        _write(who, {"secret": vault.seal(secret), "last": step, "recovery": [_rhash(c) for c in codes],
                     "tkey": secrets.token_hex(32), "since": int(time.time())})
    return codes


def disable(who):
    with _lock:
        _pending.pop(who, None)
        try:
            os.remove(_path(who))
        except OSError:
            pass


def new_recovery(who):
    with _lock:
        d = _read(who)
        if not d:
            return None
        codes = _new_recovery()
        d["recovery"] = [_rhash(c) for c in codes]
        _write(who, d)
    return codes


def forget_trust(who):
    """Every trusted browser has to enter a code again (for the admin: every other login ends too)."""
    with _lock:
        d = _read(who)
        if d:
            d["tkey"] = secrets.token_hex(32)
            _write(who, d)


def session_salt(who):
    """Part of the key that signs the admin's login cookie: changes with every setup or switch-off."""
    d = _read(who)
    return d.get("tkey", "") if d else ""


# ---------------------------------------------------------------- trusted browsers
def trust_cookie(who):
    return "speech_spark_trust_" + who


def trust_value(who):
    d = _read(who)
    if not d:
        return None
    issued = int(time.time())
    return f"{issued}." + hmac.new(bytes.fromhex(d["tkey"]), f"{who}|{issued}".encode(), hashlib.sha256).hexdigest()


def trusted(who, request):
    d = _read(who)
    raw = request.cookies.get(trust_cookie(who), "")
    issued, _, sig = raw.partition(".")
    if not d or not issued.isdigit() or time.time() - int(issued) > TRUST_DAYS * 86400:
        return False
    want = hmac.new(bytes.fromhex(d["tkey"]), f"{who}|{issued}".encode(), hashlib.sha256).hexdigest()
    return secrets.compare_digest(sig, want)


def set_trust(response, who):
    response.set_cookie(trust_cookie(who), trust_value(who), max_age=TRUST_DAYS * 86400, httponly=True, samesite="strict")


# ---------------------------------------------------------------- QR code for the app
def _qr_svg(text):
    """The QR code as inline SVG; "" without segno (the key can still be typed into the app)."""
    try:
        import io
        import segno
        buf = io.BytesIO()
        segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, xmldecl=False, dark="#000", light="#fff")
        return buf.getvalue().decode()
    except Exception:
        return ""
