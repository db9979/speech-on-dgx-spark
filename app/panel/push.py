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
import hashlib
import json
import os
import re
import struct
import threading
import time
from urllib.parse import urlsplit

import httpx

import profiles
from common import STATE

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError:
    ec = None

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


def reachable(uid, private=True):
    """The profile gets notes somewhere: a browser with push, Telegram (see telegram.py) or one of the apps."""
    import android
    import apns
    import telegram
    import begleiter
    return bool(subs(uid) or telegram.push_on(uid, private) or apns.reachable(uid) or android.reachable(uid)
                or begleiter.reachable(uid))


def sub_id(endpoint):
    """The short name a page gives for its own push subscription (reminders.js pushId)."""
    return hashlib.sha256(str(endpoint).encode()).hexdigest()[:16]


LAST_KEEP = 12 * 3600


def _have(uid, private):
    import android
    import apns
    import telegram
    import begleiter
    return {"app": apns.reachable(uid), "and": android.reachable(uid), "desk": begleiter.reachable(uid),
            "tg": telegram.push_on(uid, private), "web": bool(subs(uid))}


WAYS = ("app", "and", "desk", "tg", "web")


def pick(uid, private=True, to=""):
    """One target for a note (V01.0.181: everything once): the device the profile used last, else the
    iPhone app, else the Android app (android.py, it asks for notes itself), else the Spark-Begleiter on PC or
    Mac (begleiter.py, same), else Telegram, else the newest browser. Returns ("app"|"and"|"desk"|"tg"|"web", [subscriptions]).
    to: the way the profile chose for this kind of note (e.g. svc_device of the Dienst-Wächter), when it is set up."""
    have = _have(uid, private)
    kind, key, t = profiles.LAST_USED.get(uid, ("", "", 0))
    if to in have and have[to]:
        kind, key = to, (key if kind == to else "")
    elif not (have.get(kind) and time.time() - t < LAST_KEEP):
        kind = next((k for k in WAYS if have[k]), "")
    if kind != "web":
        return kind, []
    mine = [s for s in subs(uid) if key and sub_id(s["endpoint"]) == key]
    return "web", mine or subs(uid)[-1:]


# what a note is for on Zustand → Live (live.note), by its tag; fixed words only
WHY = {"agent": "Auftrag", "briefing": "Tagesüberblick", "notaus": "Notaus", "setup": "Einrichtung",
       "pro-": "Von selbst", "mcp": "MCP-Bestätigung", "admin": "Hinweis", "hello": "Test", "devup": "Geräte-Update", "doc": "Dokument", "bild": "Bild",
       "svc": "Dienst-Wächter", "wartung": "Wartungspause", "chat-": "Chat", "wache": "Wachposten"}


def _why(tag):
    return next((v for k, v in WHY.items() if tag == k or (k.endswith("-") and tag.startswith(k))), "")


async def send(uid, title, body, tag="", private=True, why="", to=""):
    """Sends a note once: to one device of the profile (pick), the iPhone app, Telegram (private notes,
    i.e. appointments, mails, the briefing, only when it allowed personal data there) or a browser.
    "hello" goes to the browsers only. to: the way the profile chose for this kind of note ("all": every way it
    has set up, "every": every device and browser of the profile but Telegram, for chats). Drops subscriptions the push service no longer knows. Returns the number of devices reached."""
    import begleiter
    # "Nicht stören" (Spark-Begleiter part quiet): while the profile is in a call or presenting, notes wait and one
    # summary follows; alarms, reminders and safety notes always go (begleiter.urgent)
    if tag != "quiet":
        held = begleiter.lapsed(uid)
        if held:
            await begleiter.release(uid, held)
        if begleiter.hold(uid, title, tag, why):
            print(f"push: {_word(tag, why)} held, Nicht stören | {profiles.log_name(profiles.by_id(uid))}", flush=True)
            return 1
    if tag == "hello":
        ways = [("web", subs(uid))]
    elif to == "all":
        have = _have(uid, private)
        ways = [(k, subs(uid)[-1:] if k == "web" else []) for k in WAYS if have[k]]
    elif to == "every":   # chats (chats.py): every device of the profile rings, like a messenger; never Telegram
        have = _have(uid, private)
        ways = [(k, subs(uid) if k == "web" else []) for k in ("app", "and", "desk", "web") if have[k]]
    else:
        ways = [pick(uid, private, to)]
    n = 0
    for kind, targets in ways:
        n += await _send_one(uid, kind, targets, title, body, tag, private, why)
    # one line per note, sent or not: the kind of note, the ways and how many devices it reached, never its text
    print(f"push: {_word(tag, why)} {'sent' if n else 'reached no device'} | {n} device(s) | "
          f"{','.join(k for k, _ in ways if k) or 'no way'} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return n


def _word(tag, why):
    """The kind of a note in a journal line: a fixed word of WHY, never a free text."""
    return why if why in set(WHY.values()) | {"Erinnerung"} else _why(tag) or "Hinweis"


async def _send_one(uid, kind, targets, title, body, tag, private, why):
    import apns
    import telegram
    t0 = time.time()
    # the iPhone app: Apple only carries "new message", the text waits on the Spark (apns.py)
    n = await apns.send(uid, title, body, tag=tag) if kind == "app" else 0
    if kind == "and":   # the Android app fetches it with its next question (android.py)
        import android
        android.keep(uid, title, body, tag)
        n += 1
    if kind == "desk":  # the Spark-Begleiter on PC or Mac fetches it with its next poll (begleiter.py)
        import begleiter
        begleiter.keep(uid, title, body, tag)
        n += 1
    # a note naming a place in the panel opens it there when tapped (sw.js, way.js)
    import wege
    payload = json.dumps({"title": title, "body": body, "tag": tag, "weg": wege.find(body)}).encode()[:3000]
    n += await telegram.notify(uid, f"{title}\n{body}", private) if kind == "tg" else 0
    async with httpx.AsyncClient(timeout=15) as c:
        for sub in targets:
            try:
                r = await c.post(sub["endpoint"], content=encrypt(sub, payload), headers={
                    "Authorization": vapid(sub["endpoint"]), "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream", "TTL": "3600", "Urgency": "high"})
            except httpx.HTTPError as e:
                print(f"push: browser push failed ({type(e).__name__})", flush=True)
                continue
            if r.status_code in (404, 410):
                remove(uid, sub["endpoint"])
            elif r.status_code < 300:
                n += 1
            else:
                print(f"push: browser push refused | http {r.status_code}", flush=True)   # never the server's text
    import live
    live.note(uid, kind, t0, n, why or _why(tag))
    return n


# An open panel page rings due reminders itself and takes them (/api/profile/reminders/played).
# While one was seen lately, push waits PAGE_GRACE so the reminder is not played there and pushed too.
PAGE_SEEN = 180
PAGE_GRACE = 20 * 1000
_pages = {}


def page_open(uid, sid=""):
    _pages[uid] = time.monotonic()
    profiles.used(uid, "web", sid if re.fullmatch(r"[0-9a-f]{16}", sid or "") else "")
    if len(_pages) > 1000:
        _pages.clear()


def page_lately(uid):
    return time.monotonic() - _pages.get(uid, -1e9) < PAGE_SEEN


async def due_reminders():
    """Sends due reminders of profiles that have push switched on. Each one is taken off the list
    first, so a reminder a device already played is never pushed, and a pushed one never rings again."""
    import features
    now = time.time() * 1000
    sent = 0
    c = features.chat_cfg()   # read once: many profiles
    for uid in profiles.user_ids():
        if not reachable(uid, private=False) or not features.allowed("reminders", uid, c):
            continue   # (the admin may have blocked reminders for this profile: Personen und Geräte → Gesperrte Funktionen)
        by = now - (PAGE_GRACE if page_lately(uid) else 0)
        import pebblewatch   # a reminder the watch holds as a wake-up: the watch rings it, push waits for that first
        on_watch = pebblewatch.held(uid)
        for x in [x for x in profiles.reminders(uid)
                  if x.get("due", 0) <= (by - pebblewatch.WATCH_GRACE if x.get("id") in on_watch else by)]:
            if not profiles.take_reminder(uid, x["id"], by):
                continue   # a device played it in the meantime
            if now - x["due"] < 6 * 3600 * 1000:  # older ones (panel was off) are dropped, with a line
                sent += await send(uid, "⏰ " + x["text"], "Erinnerung", tag=x["id"], private=False, why="Erinnerung")
            else:
                print(f"reminders: one dropped, more than 6 h overdue | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return sent
