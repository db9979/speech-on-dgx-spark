"""Reminders as push notifications, also while no page of the panel is open (Web Push, RFC 8030/
8291/8292, without extra libraries: the encryption comes from the cryptography package).

A profile switches it on per device in the "Ich" window; the browser hands over its push
subscription (an address at Google, Mozilla, Apple or Microsoft plus two keys), stored in
USERS_DIR/<user id>/push.json. When a reminder of the profile is due, the panel sends it to every
subscription of that profile and then removes the reminder. Only the profile's own devices get it.

Browsers allow push only on https with a trusted certificate (e.g. behind a reverse proxy);
on an iPhone the page has to be added to the home screen first.
"""
import base64
import json
import os
import re
import struct
import threading
import time
from urllib.parse import urlsplit

import httpx

import profiles

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError:
    ec = None

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
KEY_FILE = os.path.join(STATE, "vapid.pem")
SUBJECT = "https://github.com/db9979/speech-on-dgx-spark"
# only the push services of the browsers: the panel never posts to other addresses
PUSH_HOSTS = re.compile(r"(fcm\.googleapis\.com|android\.googleapis\.com|updates\.push\.services\.mozilla\.com|"
                        r"push\.services\.mozilla\.com|web\.push\.apple\.com|[\w.\-]+\.notify\.windows\.com)")
MAX_SUBS = 10
_lock = threading.Lock()
_key = None


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text):
    text = str(text)
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def available():
    return ec is not None


def _private():
    global _key
    if _key is None:
        with _lock:
            try:
                with open(KEY_FILE, "rb") as f:
                    _key = serialization.load_pem_private_key(f.read(), None)
            except FileNotFoundError:
                os.makedirs(STATE, exist_ok=True)
                _key = ec.generate_private_key(ec.SECP256R1())
                pem = _key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())
                with open(os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                    f.write(pem)
    return _key


def public_key():
    """The server key the browser needs to subscribe (base64url, uncompressed point)."""
    return b64(_private().public_key().public_bytes(serialization.Encoding.X962,
                                                    serialization.PublicFormat.UncompressedPoint))


# ---------------------------------------------------------------- subscriptions
def _file(uid):
    return profiles._path(uid, "push.json")


def subs(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def valid(sub):
    """A checked subscription from the browser, or ValueError."""
    if not isinstance(sub, dict):
        raise ValueError("invalid subscription")
    url = str(sub.get("endpoint", ""))
    parts = urlsplit(url)
    if parts.scheme != "https" or not PUSH_HOSTS.fullmatch(parts.hostname or "") or len(url) > 1000:
        raise ValueError("unknown push service")
    keys = sub.get("keys") or {}
    try:
        p256dh, auth = unb64(keys.get("p256dh", "")), unb64(keys.get("auth", ""))
    except (ValueError, TypeError):
        raise ValueError("invalid keys")
    if len(p256dh) != 65 or len(auth) != 16:
        raise ValueError("invalid keys")
    return {"endpoint": url, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}


def add(uid, sub, name=""):
    item = dict(valid(sub), name=str(name)[:60], created=int(time.time()))
    with _lock:
        rest = [x for x in subs(uid) if x["endpoint"] != item["endpoint"]]
        profiles._write(_file(uid), (rest + [item])[-MAX_SUBS:])
    return item


def remove(uid, endpoint):
    with _lock:
        items = subs(uid)
        keep = [x for x in items if x["endpoint"] != endpoint]
        profiles._write(_file(uid), keep)
    return len(items) != len(keep)


# ---------------------------------------------------------------- sending
def _hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(sub, payload):
    """aes128gcm body for one subscription (RFC 8291)."""
    ua_public = unb64(sub["keys"]["p256dh"])
    auth = unb64(sub["keys"]["auth"])
    eph = ec.generate_private_key(ec.SECP256R1())
    as_public = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = os.urandom(16)
    prk_cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(prk_cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!IB", 4096, len(as_public)) + as_public + body


def vapid(endpoint):
    """Authorization header value (RFC 8292)."""
    parts = urlsplit(endpoint)
    head = b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64(json.dumps({"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 3600,
                             "sub": SUBJECT}).encode())
    sig = _private().sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(sig)
    token = f"{head}.{claims}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={public_key()}"


async def send(uid, title, body, tag=""):
    """Sends to every device of the profile; drops subscriptions the push service no longer knows.
    Returns the number of devices reached."""
    payload = json.dumps({"title": title, "body": body, "tag": tag}).encode()[:3000]
    n = 0
    async with httpx.AsyncClient(timeout=15) as c:
        for sub in subs(uid):
            try:
                r = await c.post(sub["endpoint"], content=encrypt(sub, payload), headers={
                    "Authorization": vapid(sub["endpoint"]), "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream", "TTL": "3600", "Urgency": "high"})
            except httpx.HTTPError as e:
                print("push:", type(e).__name__, e, flush=True)
                continue
            if r.status_code in (404, 410):
                remove(uid, sub["endpoint"])
            elif r.status_code < 300:
                n += 1
            else:
                print("push:", r.status_code, r.text[:200], flush=True)
    return n


async def due_reminders():
    """Sends due reminders of profiles that have push switched on, then removes them."""
    now = time.time() * 1000
    sent = 0
    for uid in profiles.user_ids():
        if not subs(uid):
            continue
        due = [x for x in profiles.reminders(uid) if x.get("due", 0) <= now]
        for x in due:
            if now - x["due"] < 6 * 3600 * 1000:  # older ones (panel was off) are dropped quietly
                sent += await send(uid, "⏰ " + x["text"], "Erinnerung", tag=x["id"])
        if due:
            profiles.remove_reminders(uid, [x["id"] for x in due])
    return sent
