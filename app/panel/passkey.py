"""Passkeys (Face ID, Touch ID, Windows Hello; WebAuthn) instead of typing the six-digit code (V01.0.295,
plan plaene/zweiter-schritt-seltener.md, point 4).

A passkey belongs to the second login step: it is kept in the same file (mfa.json "passkeys", at most MAX_KEYS)
and only while that step is on; the authenticator app's code and the recovery codes stay as the way back.
Everywhere a code is asked (login, admin mode, important changes) a passkey counts the same: the browser signs
a one-time challenge of this panel, for this host name, with the person's fingerprint, face or device PIN
(user verification required). That cannot be phished like a typed code: another page gets no signature for us.

Adding a passkey is a new way in, so it needs a fresh code; removing one needs none. Passkeys work only over a
host name with https (the browser refuses IP addresses), e.g. https://speech.example.de, not https://192.168.x.y.
Each key remembers its host name and is offered only there. The panel never sees the private key; it keeps the
public key, a short name and when it was added and last used. The challenges live in memory for STATE_SECS,
bound to the person and the login, each one usable once.

The library is python-fido2 (Yubico), pinned and installed without its dependencies (it only needs
cryptography, which the panel has anyway).
"""
import base64
import hashlib
import ipaddress
import json
import re
import secrets
import threading
import time

import mfa

MAX_KEYS = 10
STATE_SECS = 120
MAX_STATES = 200
HEADER = "x-speech-passkey"              # the signed answer, instead of X-Speech-Code
OPTIONS_HEADER = "X-Speech-Passkey-Options"  # sent with "428 code required" when the person has a passkey here
_states = {}                              # sid -> (who, kind, state, rp, until, login)
_lock = threading.Lock()
_HOST = re.compile(r"[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)+")


def _lib():
    """python-fido2, or None when it is not installed (then passkeys are simply not offered)."""
    try:
        from fido2 import server, webauthn
        return server, webauthn
    except Exception:
        return None


def rp_id(request):
    """The host name the browser uses for this panel, or None (an IP address, localhost, no https)."""
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip().lower()
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if not host or len(host) > 253 or not _HOST.fullmatch(host):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    return host


def _server(rp):
    lib = _lib()
    if not lib or not rp:
        return None
    server, webauthn = lib
    return server.Fido2Server(webauthn.PublicKeyCredentialRpEntity(name="Speech Spark", id=rp),
                              verify_origin=lambda origin: origin == "https://" + rp or origin.startswith("https://" + rp + ":"))


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s):
    return base64.urlsafe_b64decode(str(s) + "=" * (-len(str(s)) % 4))


def _keys(who):
    d = mfa._read(who)
    k = d.get("passkeys") if d else None
    return k if isinstance(k, dict) else {}


def _creds(who, rp):
    lib = _lib()
    if not lib:
        return []
    out = []
    for v in _keys(who).values():
        if isinstance(v, dict) and v.get("rp") == rp:
            try:
                out.append(lib[1].AttestedCredentialData(_unb64(v["cred"])))
            except Exception:
                continue
    return out


def listing(who, rp=None):
    """The person's passkeys (name, host, added, last used), newest use first."""
    out = [{"id": k, "name": v.get("name", "Passkey"), "rp": v.get("rp", ""), "added": v.get("added", 0),
            "last": v.get("last", 0), "here": rp is not None and v.get("rp") == rp}
           for k, v in _keys(who).items() if isinstance(v, dict)]
    return sorted(out, key=lambda x: -(x["last"] or x["added"]))


def available(who, request):
    """True when `who` has a passkey for the host name of this request (and the library is there)."""
    return bool(mfa.enabled(who) and _lib() and _creds(who, rp_id(request)))


def _keep(who, kind, state, rp, login, now):
    sid = secrets.token_hex(16)
    with _lock:
        for k in [k for k, v in _states.items() if v[4] <= now]:
            _states.pop(k)
        if len(_states) >= MAX_STATES:
            _states.pop(min(_states, key=lambda k: _states[k][4]))
        _states[sid] = (who, kind, state, rp, now + STATE_SECS, login)
    return sid


def _take(sid, who, kind, rp, login, now):
    """The kept state of this challenge, once; None when it is not this person's, this login's or too old."""
    if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
        return None
    with _lock:
        v = _states.pop(sid, None)
    if not v or v[0] != who or v[1] != kind or v[3] != rp or v[4] <= now or v[5] != login:
        return None
    return v[2]


# ---------------------------------------------------------------- adding one
def begin_add(who, label, request, login, now=None):
    """{"sid", "options"} for navigator.credentials.create, or None (no host name, no library, too many)."""
    rp = rp_id(request)
    srv = _server(rp)
    if not srv or not mfa.enabled(who) or len(_keys(who)) >= MAX_KEYS:
        return None
    lib = _lib()[1]
    user = lib.PublicKeyCredentialUserEntity(name=str(label)[:60] or "Spark", id=hashlib.sha256(("speech-spark-user:" + who).encode()).digest()[:16],
                                             display_name=str(label)[:60] or "Spark")
    options, state = srv.register_begin(user, _creds(who, rp), resident_key_requirement=lib.ResidentKeyRequirement.PREFERRED,
                                        user_verification=lib.UserVerificationRequirement.REQUIRED)
    now = now if now is not None else time.time()
    return {"sid": _keep(who, "add", state, rp, login, now), "options": json.loads(json.dumps(dict(options)))}


def finish_add(who, sid, response, name, request, login, now=None):
    """Stores the new passkey; returns its id, or None for a wrong or old answer."""
    rp = rp_id(request)
    now = now if now is not None else time.time()
    state = _take(sid, who, "add", rp, login, now)
    srv = _server(rp)
    if state is None or not srv or not isinstance(response, dict):
        return None
    try:
        auth = srv.register_complete(state, response)
    except Exception:
        return None
    cred = auth.credential_data
    if not cred:
        return None
    kid = secrets.token_hex(8)
    with mfa._lock:
        d = mfa._read(who)
        if not d:
            return None
        keys = d.get("passkeys") if isinstance(d.get("passkeys"), dict) else {}
        if len(keys) >= MAX_KEYS or any(v.get("cid") == _b64(cred.credential_id) for v in keys.values() if isinstance(v, dict)):
            return None
        keys[kid] = {"name": str(name or "Passkey").strip()[:60] or "Passkey", "rp": rp, "cred": _b64(bytes(cred)),
                     "cid": _b64(cred.credential_id), "added": int(now), "last": 0}
        d["passkeys"] = keys
        mfa._write(who, d)
    return kid


def remove(who, kid):
    with mfa._lock:
        d = mfa._read(who)
        keys = d.get("passkeys") if d and isinstance(d.get("passkeys"), dict) else {}
        if kid not in keys:
            return False
        keys.pop(kid)
        d["passkeys"] = keys
        mfa._write(who, d)
    return True


# ---------------------------------------------------------------- signing in or confirming with one
def begin_auth(who, request, login, now=None):
    """{"sid", "options"} for navigator.credentials.get with this person's passkeys for this host, or None."""
    rp = rp_id(request)
    creds = _creds(who, rp)
    srv = _server(rp)
    if not srv or not creds or not mfa.enabled(who):
        return None
    lib = _lib()[1]
    options, state = srv.authenticate_begin(creds, user_verification=lib.UserVerificationRequirement.REQUIRED)
    now = now if now is not None else time.time()
    return {"sid": _keep(who, "auth", state, rp, login, now), "options": json.loads(json.dumps(dict(options)))}


def finish_auth(who, answer, request, login, now=None):
    """True when `answer` ({"sid", "response"}) is a right signature of one of the person's passkeys."""
    if not isinstance(answer, dict):
        return False
    rp = rp_id(request)
    now = now if now is not None else time.time()
    state = _take(answer.get("sid"), who, "auth", rp, login, now)
    creds = _creds(who, rp)
    srv = _server(rp)
    if state is None or not srv or not creds or not isinstance(answer.get("response"), dict):
        return False
    try:
        used = srv.authenticate_complete(state, creds, answer["response"])
    except Exception:
        return False
    cid = _b64(used.credential_id)
    with mfa._lock:
        d = mfa._read(who)
        for v in ((d or {}).get("passkeys") or {}).values():
            if isinstance(v, dict) and v.get("cid") == cid:
                v["last"] = int(now)
                mfa._write(who, d)
                break
    return True


def header_answer(request):
    """The signed answer from the X-Speech-Passkey header (base64url JSON, at most 8 KB), or None."""
    raw = request.headers.get(HEADER, "")
    if not raw or len(raw) > 8192:
        return None
    try:
        v = json.loads(_unb64(raw))
    except Exception:
        return None
    return v if isinstance(v, dict) else None


def options_header(who, request, login):
    """The header for a 428 answer: the challenge for a passkey, when the person has one here."""
    if not available(who, request):
        return {}
    opt = begin_auth(who, request, login)
    return {OPTIONS_HEADER: _b64(json.dumps(opt, separators=(",", ":")).encode())} if opt else {}
