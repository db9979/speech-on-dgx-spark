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


def _login(sid):
    """The login a browser's subscription is bound to, as a short hash of its session (never the session itself)."""
    return hashlib.sha256(("push-login:" + str(sid)).encode()).hexdigest()[:16] if sid else ""


def add(uid, sub, name="", login=""):
    """A browser's subscription belongs to exactly one profile (P1 Sicherheit, review A-K1): a browser has one per
    origin, so whoever switches it on last at this browser gets it, and every other profile loses it at once (else the
    next person at a shared PC or tablet read the notes of the one before, with title and text). login: the session of
    the browser login that switched it on; logging out there ends the subscription too (drop_login)."""
    item = dict(valid(sub), name=str(name)[:60], created=int(time.time()), **({"login": _login(login)} if login else {}))
    with _lock:
        for other in profiles.user_ids():
            if other != uid and any(x.get("endpoint") == item["endpoint"] for x in subs(other)):
                profiles._write(_file(other), [x for x in subs(other) if x.get("endpoint") != item["endpoint"]])
                print("push: browser moved to another profile | removed from the one before", flush=True)
        rest = [x for x in subs(uid) if x["endpoint"] != item["endpoint"]]
        profiles._write(_file(uid), (rest + [item])[-MAX_SUBS:])
    return item


def drop_login(uid, sid):
    """The browser login sid ended (Abmelden, a login ended under Ich → Sicherheit or by the admin): the subscriptions
    it switched on go with it. Returns how many."""
    key = _login(sid)
    if not key:
        return 0
    with _lock:
        items = subs(uid)
        keep = [x for x in items if x.get("login") != key]
        if len(keep) != len(items):
            profiles._write(_file(uid), keep)
    if len(keep) != len(items):
        print(f"push: browser abo beim abmelden entfernt | {len(items) - len(keep)}", flush=True)
    return len(items) - len(keep)


def logins_ended(uid, keep_sid="", new_sid=""):
    """Überall abmelden: every subscription bound to a browser login goes, the one of this browser (keep_sid) moves
    to its new login (new_sid). Subscriptions without a login (older ones) stay."""
    old, new = _login(keep_sid), _login(new_sid)
    with _lock:
        items = subs(uid)
        keep = [dict(x, login=new) if old and x.get("login") == old and new else x for x in items
                if not x.get("login") or (old and x.get("login") == old and new)]
        profiles._write(_file(uid), keep)
    if len(items) != len(keep):
        print(f"push: browser abos nach ueberall abmelden entfernt | {len(items) - len(keep)}", flush=True)
    return len(items) - len(keep)


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


def has_sub(uid, key):
    """The browser behind this short name (sub_id) has a subscription of the profile."""
    return bool(key) and any(sub_id(s["endpoint"]) == key for s in subs(uid))


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
    """One target for a note (V01.0.181: everything once): with Meldung ans genutzte Gerät (zustellung.pick) the device in
    use right now, else the phone app; otherwise the device the profile used last, else the
    iPhone app, else the Android app (android.py, it asks for notes itself), else the Spark-Begleiter on PC or
    Mac (begleiter.py, same), else Telegram, else the newest browser. A browser used last without a subscription of its
    own never sends the note to another browser: the next way in that order, the newest browser only when browsers
    are all the profile has (P1). Returns ("app"|"and"|"desk"|"tg"|"web", [subscriptions]).
    to: the way the profile chose for this kind of note (e.g. svc_device of the Dienst-Wächter), when it is set up."""
    import zustellung
    have = _have(uid, private)
    kind, key, t = profiles.LAST_USED.get(uid, ("", "", 0))
    routed = None if to in have and have[to] else zustellung.pick(uid, have)
    used = False   # the way is the device used last (profiles.LAST_USED)
    if to in have and have[to]:
        kind, key = to, (key if kind == to else "")
    elif routed:   # Meldung ans genutzte Gerät (zustellung.py): the device in use now, else the phone app
        kind, key = routed[0], routed[1]
    elif not (have.get(kind) and time.time() - t < LAST_KEEP):
        kind = next((k for k in WAYS if have[k]), "")
    else:
        used = True
    if kind == "web" and used and not has_sub(uid, key):
        # the browser in use has no subscription of this profile (P1 Sicherheit, review A-H6): never another browser
        # instead (an old phone in a drawer), the next way of the profile (phone app, Begleiter, Telegram)
        kind = next((k for k in WAYS if k != "web" and have[k]), "web")
        print("push: route web ohne abo | " + (kind if kind != "web" else "neuester browser"), flush=True)
    if kind != "web":
        return kind, []
    mine = [s for s in subs(uid) if key and sub_id(s["endpoint"]) == key]
    # no browser named (none used lately, or browsers are the only way left): the profile's newest one; a subscription
    # belongs to one profile only (add), so it is always one of the profile's own browsers
    return "web", mine or subs(uid)[-1:]


# what a note is for on Zustand → Live (live.note), by its tag; fixed words only
WHY = {"agent": "Auftrag", "briefing": "Tagesüberblick", "notaus": "Notaus", "setup": "Einrichtung",
       "pro-": "Von selbst", "mcp": "MCP-Bestätigung", "admin": "Hinweis", "hello": "Test", "devup": "Geräte-Update", "doc": "Dokument", "bild": "Bild",
       "svc": "Dienst-Wächter", "wartung": "Wartungspause", "chat-": "Chat", "wache": "Wachposten",
       "modell": "Modellwechsel", "ruf": "Anruf starten", "listen": "Listen",
       "share": "Geteilt", "vg-": "Offen", "mailcode": "Bestätigungscode", "hoerstueck": "Hörstück"}


def _why(tag):
    return next((v for k, v in WHY.items() if tag == k or (k.endswith("-") and tag.startswith(k))), "")


async def send(uid, title, body, tag="", private=True, why="", to="", ref="", vg="", bis=0):
    """Sends a note once: to one device of the profile (pick), the iPhone app, Telegram (private notes,
    i.e. appointments, mails, the briefing, only when it allowed personal data there) or a browser.
    "hello" goes to the browsers only. to: the way the profile chose for this kind of note ("all": every way it
    has set up, "every": every device and browser of the profile but Telegram, for chats). ref: what the note is about
    (a Für-dich card), only for the Begleiter's buttons (begleiter.NOTE_ACTS), never sent anywhere. vg: the Vorgang
    of Offen the note is about (vorgaenge.py; a tag "vg-<id>" says it too): with Meldung ans genutzte Gerät a note
    nobody saw comes once more to the phone app, and leaves every device when the Vorgang is done (zustellung.py).
    bis: the time the note is over (a confirmation code's validity, mailcode.py): no device shows or fetches it after,
    a browser push lives at most until then (TTL), and it is not followed up.
    Drops subscriptions the push service no longer knows. Returns the number of devices reached."""
    import zustellung
    vg = vg or (tag[3:] if tag.startswith("vg-") else "")
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
        n += await _send_one(uid, kind, targets, title, body, tag, private, why, ref, **({"vg": vg} if vg else {}), **({"bis": bis} if bis else {}))
    if tag != "hello" and n:   # Meldung ans genutzte Gerät, stage 2: follow-up and „gelesen überall“
        zustellung.sent(uid, [k for k, _ in ways if k], {"title": title, "body": body, "tag": tag, "private": private,
                                                          "why": why, "ref": ref, "bis": bis}, vg, follow=not to,
                        keys=[sub_id(x["endpoint"]) for _, targets in ways[:1] for x in targets[:5]])
    # one line per note, sent or not: the kind of note, the ways and how many devices it reached, never its text
    print(f"push: {_word(tag, why)} {'sent' if n else 'reached no device'} | {n} device(s) | "
          f"{','.join(k for k, _ in ways if k) or 'no way'} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return n


def _word(tag, why):
    """The kind of a note in a journal line: a fixed word of WHY, never a free text."""
    return why if why in set(WHY.values()) | {"Erinnerung"} else _why(tag) or "Hinweis"


def ttl(bis, now=None):
    """Seconds a browser push may wait at the push service: an hour, less when the note is over sooner (bis)."""
    now = time.time() if now is None else now
    return max(0, min(3600, int(bis - now))) if bis else 3600


async def _send_one(uid, kind, targets, title, body, tag, private, why, ref="", vg="", bis=0):
    import apns
    import telegram
    t0 = time.time()
    # the iPhone app: Apple only carries "new message", the text waits on the Spark (apns.py)
    n = await apns.send(uid, title, body, tag=tag, **({"vg": vg} if vg else {}), **({"ref": ref} if ref else {}), bis=bis) \
        if kind == "app" else 0
    # a tapped note opens as a card in the conversation (mitteilungen.py): the devices get only its number "m"
    import mitteilungen
    mid = mitteilungen.keep(uid, title, body, tag, vg, ref, bis=bis) if kind in ("and", "desk", "web") else ""
    if kind == "and":   # the Android app fetches it with its next question (android.py)
        import android
        android.keep(uid, title, body, tag, **({"vg": vg} if vg else {}), m=mid, bis=bis)
        n += 1
    if kind == "desk":  # the Spark-Begleiter on PC or Mac fetches it with its next poll (begleiter.py)
        import begleiter
        begleiter.keep(uid, title, body, tag, ref=ref, **({"vg": vg} if vg else {}), m=mid, bis=bis)
        n += 1
    # a note naming a place in the panel opens it there when tapped (sw.js, way.js); with "m" as its card
    import wege
    payload = json.dumps({"title": title, "body": body, "tag": tag, "weg": wege.find(body), "vg": vg,
                          "m": mid}).encode()[:3000]
    n += await telegram.notify(uid, f"{title}\n{body}", private, vg=vg) if kind == "tg" else 0
    async with httpx.AsyncClient(timeout=15) as c:
        for sub in targets:
            try:
                r = await c.post(sub["endpoint"], content=encrypt(sub, payload), headers={
                    "Authorization": vapid(sub["endpoint"]), "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream", "TTL": str(ttl(bis)), "Urgency": "high"})
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
            took = profiles.take_reminder(uid, x["id"], by)
            if not took:
                continue   # a device played it in the meantime
            if now - x["due"] < 6 * 3600 * 1000:  # older ones (panel was off) are dropped, with a line
                vg = {"vg": took["vg"]} if took.get("vg") else {}   # the Vorgang of the reminder (zustellung.py)
                sent += await send(uid, "⏰ " + x["text"], "Erinnerung", tag=x["id"], private=False, why="Erinnerung", **vg)
            else:
                print(f"reminders: one dropped, more than 6 h overdue | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return sent
