"""Push notifications to the iPhone app over Apple's push service (APNs), also while the app is closed.

Off until the admin switches it on (chat.iphone_push) and enters the key from developer.apple.com
(a .p8 file, its Key ID, the Team ID and the app's bundle ID). The .p8 is kept sealed (vault.py) in
STATE/apns.json, only changed with the admin login plus the second step, and never sent back.

Each paired iPhone hands over its push address (device token) with its own app key
(POST /api/iphone/push-token); it is kept per device and dropped with the device. A profile gets
pushes only with its own switch app_push.

What Apple sees: only "Neue Nachricht vom Spark" and a random id. The text stays on the Spark in a
short inbox (INBOX_SECONDS, INBOX_MAX per profile); the app's notification extension fetches it with
the app key from GET /api/iphone/note?id=... and shows it in the banner.

Everything that goes out through push.send (reminders, the daily briefing, proactive notes, memory
tidying) also comes here: see push.send.
"""
import base64
import json
import os
import re
import secrets
import threading
import time

import httpx

import profiles
import vault
from common import load_config

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
except ImportError:
    ec = None

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
HOSTS = {False: "https://api.push.apple.com", True: "https://api.sandbox.push.apple.com"}
JWT_SECONDS = 40 * 60          # Apple wants a fresh token at least every hour, not more than every 20 minutes
INBOX_SECONDS = 24 * 3600
INBOX_MAX = 30
PER_HOUR = 30                  # pushes per profile and hour
GENERIC = "Neue Nachricht vom Spark"
TOKEN = re.compile(r"[0-9a-f]{64,200}")
_lock = threading.Lock()
_jwt = (0.0, "", "")           # (made, key id, token)
_inbox = {}                    # uid -> [{"id", "t", "title", "body"}]
_sent = {}                     # uid -> [times]


# ---------------------------------------------------------------- stored key and device tokens
def _file(name):
    return os.path.join(STATE, name)


def _read(name):
    try:
        with open(_file(name)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(name, d):
    with _lock:
        os.makedirs(STATE, exist_ok=True)
        tmp = _file(name) + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(d, f)
        os.replace(tmp, _file(name))


def settings():
    return _read("apns.json")


def admin_on():
    return bool(load_config().get("chat", {}).get("iphone_push", False))


def ready():
    s = settings()
    return bool(ec and admin_on() and s.get("key") and s.get("key_id") and s.get("team") and s.get("bundle"))


def check_key(pem):
    """The .p8 as Apple hands it out: a P-256 private key in PEM. Returns the key or None."""
    if not ec or not isinstance(pem, str) or len(pem) > 1000 or "PRIVATE KEY" not in pem:
        return None
    try:
        key = serialization.load_pem_private_key(pem.strip().encode(), None)
    except (ValueError, TypeError):
        return None
    return key if isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == "secp256r1" else None


def save(pem, key_id, team, bundle, sandbox):
    global _jwt
    _write("apns.json", {"key": vault.seal(pem.strip()), "key_id": key_id, "team": team, "bundle": bundle,
                         "sandbox": bool(sandbox)})
    _jwt = (0.0, "", "")


def forget():
    global _jwt
    _write("apns.json", {})
    _jwt = (0.0, "", "")


def tokens():
    return _read("apns-tokens.json")


def set_token(did, uid, token):
    d = {k: v for k, v in tokens().items() if k in _app_devices()}   # drops removed iPhones
    d[did] = {"uid": uid, "token": token, "t": int(time.time())}
    _write("apns-tokens.json", d)


def _drop(did):
    d = tokens()
    if d.pop(did, None):
        _write("apns-tokens.json", d)


def _app_devices():
    """device id -> profile id of every paired iPhone."""
    return {x["id"]: x["user"] for x in profiles._load()["devices"] if x.get("scope") == "app"}


def profile_tokens(uid):
    """(device id, token) of the profile's iPhones that still exist and still belong to it."""
    devs = _app_devices()
    return [(did, v["token"]) for did, v in tokens().items()
            if devs.get(did) == uid and v.get("uid") == uid and TOKEN.fullmatch(str(v.get("token", "")))]


def on_for(uid):
    import iphone
    return ready() and iphone.allowed(uid) and bool(profiles.settings(uid).get("app_push"))


def reachable(uid):
    return on_for(uid) and bool(profile_tokens(uid))


# ---------------------------------------------------------------- the short inbox the app reads from
def _keep(uid, title, body, now):
    item = {"id": secrets.token_hex(8), "t": now, "title": str(title)[:200], "body": str(body)[:1500]}
    with _lock:
        box = [x for x in _inbox.get(uid, []) if now - x["t"] < INBOX_SECONDS]
        box.append(item)
        _inbox[uid] = box[-INBOX_MAX:]
    return item["id"]


def note(uid, nid, now=None):
    now = time.time() if now is None else now
    if not isinstance(nid, str) or not re.fullmatch(r"[0-9a-f]{16}", nid):
        return None
    with _lock:
        return next((dict(x) for x in _inbox.get(uid, []) if x["id"] == nid and now - x["t"] < INBOX_SECONDS), None)


def _allowed_now(uid, now):
    with _lock:
        times = [t for t in _sent.get(uid, []) if now - t < 3600]
        if len(times) >= PER_HOUR:
            _sent[uid] = times
            return False
        _sent[uid] = times + [now]
        return True


# ---------------------------------------------------------------- talking to Apple
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _bearer(s, now):
    """The provider token: ES256, signed with the .p8, reused for JWT_SECONDS."""
    global _jwt
    made, kid, tok = _jwt
    if tok and kid == s["key_id"] and now - made < JWT_SECONDS:
        return tok
    key = check_key(vault.open_(s.get("key", "")))
    if not key:
        raise ValueError("Apple-Schlüssel nicht lesbar, bitte im Panel neu eintragen")
    head = _b64(json.dumps({"alg": "ES256", "kid": s["key_id"]}).encode())
    claims = _b64(json.dumps({"iss": s["team"], "iat": int(now)}).encode())
    r, sig = decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    tok = f"{head}.{claims}.{_b64(r.to_bytes(32, 'big') + sig.to_bytes(32, 'big'))}"
    _jwt = (now, s["key_id"], tok)
    return tok


def payload(nid, tag):
    """What goes through Apple: nothing but a fixed sentence, the inbox id and the kind."""
    # the kind may carry a random message id ("msg-<12 hex>") so the app can answer it; never text
    kind = re.sub(r"[^a-z0-9\-]", "", str(tag).lower())[:24]
    return {"aps": {"alert": {"title": "Spark", "body": GENERIC}, "sound": "default", "mutable-content": 1,
                    "thread-id": "spark"}, "n": nid, "k": kind}


def _client():
    try:
        return httpx.AsyncClient(http2=True, timeout=15)
    except ImportError:   # h2 missing: APNs only speaks HTTP/2
        raise ValueError("Paket h2 fehlt (Update ausführen)")


async def _post(c, s, token, body, now):
    return await c.post(f"{HOSTS[bool(s.get('sandbox'))]}/3/device/{token}", content=json.dumps(body).encode(),
                        headers={"authorization": "bearer " + _bearer(s, now), "apns-topic": s["bundle"],
                                 "apns-push-type": "alert", "apns-priority": "10",
                                 "apns-expiration": str(int(now) + 3600)})


def _reason(r):
    try:
        return str(r.json().get("reason", ""))[:60]
    except ValueError:
        return ""


async def send(uid, title, body, tag="", now=None):
    """To every iPhone of the profile; returns how many Apple accepted."""
    now = time.time() if now is None else now
    if not reachable(uid) or not _allowed_now(uid, now):
        return 0
    s = settings()
    nid = _keep(uid, title, body, now)
    n = 0
    try:
        async with _client() as c:
            for did, token in profile_tokens(uid):
                try:
                    r = await _post(c, s, token, payload(nid, tag), now)
                except httpx.HTTPError as e:
                    print("apns:", type(e).__name__, flush=True)
                    continue
                if r.status_code == 200:
                    n += 1
                elif r.status_code == 410 or _reason(r) in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
                    _drop(did)
                    print("apns: token dropped:", r.status_code, _reason(r), flush=True)
                else:
                    print("apns:", r.status_code, _reason(r), flush=True)
    except ValueError as e:
        print("apns:", e, flush=True)
    return n


async def test(uid, now=None):
    """A test message to the profile's iPhones, with Apple's reason when it is refused."""
    now = time.time() if now is None else now
    if not ready():
        return {"ok": False, "why": "Apple-Push ist nicht eingerichtet (Admin: Funktionen → iPhone-App)."}
    if not profile_tokens(uid):
        return {"ok": False, "why": "Noch kein iPhone hat sich für Meldungen angemeldet. App einmal öffnen."}
    s = settings()
    nid = _keep(uid, "Spark", "Test-Meldung: Push auf dieses iPhone klappt.", now)
    out = []
    try:
        async with _client() as c:
            for did, token in profile_tokens(uid):
                try:
                    r = await _post(c, s, token, payload(nid, "test"), now)
                    out.append("ok" if r.status_code == 200 else f"{r.status_code} {_reason(r)}".strip())
                except httpx.HTTPError as e:
                    out.append(type(e).__name__)
    except ValueError as e:
        return {"ok": False, "why": str(e)}
    ok = any(x == "ok" for x in out)
    hint = ""
    if any("BadDeviceToken" in x for x in out):
        hint = " Entwicklung/Produktion vertauscht? Xcode-Builds brauchen „Entwicklung“, TestFlight „Produktion“."
    elif any("InvalidProviderToken" in x for x in out):
        hint = " Key ID oder Team ID passen nicht zum Schlüssel."
    elif any("TopicDisallowed" in x or "BadTopic" in x for x in out):
        hint = " Die Bundle-ID passt nicht zur App."
    return {"ok": ok, "why": ", ".join(out) + hint}


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from account import browser_profile  # noqa: E402
from core import admin_code, assistant, auth, own_profile  # noqa: E402

router = APIRouter()


def _public():
    s = settings()
    return {"has_key": bool(s.get("key")), "key_id": s.get("key_id", ""), "team": s.get("team", ""),
            "bundle": s.get("bundle", ""), "sandbox": bool(s.get("sandbox")), "available": ec is not None,
            "phones": len(tokens())}


@router.get("/api/admin/apns", dependencies=[Depends(auth)])
def admin_get():
    return _public()


@router.put("/api/admin/apns", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_set(request: Request):
    import iphone
    body = await iphone._json(request)    # size limit while reading, also without content-length
    key_id, team = str(body.get("key_id", "")).strip(), str(body.get("team", "")).strip()
    bundle = str(body.get("bundle", "")).strip()
    if not re.fullmatch(r"[A-Z0-9]{10}", key_id):
        raise HTTPException(400, "Key ID: 10 Zeichen, Großbuchstaben und Ziffern (steht neben dem Schlüssel bei Apple).")
    if not re.fullmatch(r"[A-Z0-9]{10}", team):
        raise HTTPException(400, "Team ID: 10 Zeichen, Großbuchstaben und Ziffern (Apple Developer → Membership).")
    if not re.fullmatch(r"[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+){1,8}", bundle) or len(bundle) > 155:
        raise HTTPException(400, "Bundle-ID wie in Xcode, z. B. io.github.db9979.speechspark")
    pem = body.get("key")
    old = settings()
    if pem:
        if not check_key(pem):
            raise HTTPException(400, "Das ist kein Apple-Push-Schlüssel (.p8-Datei mit BEGIN PRIVATE KEY).")
    elif old.get("key"):
        pem = vault.open_(old["key"])   # only the other fields change
    else:
        raise HTTPException(400, "Bitte die .p8-Datei wählen.")
    save(pem, key_id, team, bundle, body.get("sandbox") is True)
    print("apns: key saved", "(sandbox)" if body.get("sandbox") is True else "(production)", flush=True)
    return _public()


@router.delete("/api/admin/apns", dependencies=[Depends(auth), Depends(admin_code)])
def admin_delete():
    forget()
    return _public()


@router.post("/api/iphone/push-token", dependencies=[Depends(assistant)])
async def app_token(request: Request, prof=Depends(own_profile)):
    """The app's push address. Only with the app's own key: the token belongs to that device."""
    import guard
    dev = profiles.device(request)
    if not dev or dev.get("scope") != "app":
        raise HTTPException(403, "only the iPhone app")
    guard.limit(request, "chat", prof["id"], False)
    import iphone
    body = await iphone._json(request)
    token = body.get("token") if isinstance(body.get("token"), str) else ""
    token = token.lower()
    if not TOKEN.fullmatch(token):
        raise HTTPException(400, "bad token")
    set_token(dev["id"], prof["id"], token)
    return {"ok": True, "push": on_for(prof["id"])}


@router.get("/api/iphone/note", dependencies=[Depends(assistant)])
def app_note(id: str = "", prof=Depends(own_profile)):
    item = note(prof["id"], id)
    if not item:
        raise HTTPException(404, "gone")
    return {"title": item["title"], "body": item["body"]}


@router.post("/api/profile/iphone/push-test", dependencies=[Depends(assistant)])
async def profile_test(prof=Depends(browser_profile)):
    return await test(prof["id"])
