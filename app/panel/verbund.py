"""Spark-Verbund: chats with people on other Sparks (plan plaene/spark-verbund.md, Dominik 2026-10-13: "1c 2a 3a 4a 5a").

Each person gets a Spark address, handle@domain (domain: chat.verbund_domain, the name the Spark is reached at from
outside). Chats → ＋ Neuer Chat → „Jemand auf einem anderen Spark“ sends a contact request to such an address; the
other person answers Annehmen, Ablehnen or Sperren. Only after Annehmen does a message get through. Then it is a chat
of two like any other (kind "far" in chats.py, the other one a member "r_<12 hex>"): ticks, answers, reactions,
change and take back. Private chats, groups and calls across Sparks come later.

Photos, files and voice (V2, chat.verbund_media, plan plaene/messenger-d-v2.md Teil 3): the file goes first, alone
and signed, to https://<domain>/api/verbund/blob; its message follows with the file's SHA-256. The receiving Spark
takes a file only from an allowed, known Spark (key and switch checked before a byte of the body is read), at most
BLOB_DAY a day per Spark, keeps it sealed until its message comes (at most BLOB_KEEP), then makes it again as if
uploaded here: a photo drawn anew (no EXIF, no place), a file checked by its content, a voice message decoded and
written down by this Spark's own speech recognition. Nothing of it goes to the model.

Which Sparks (chat.verbund_mode, the admin picks, Dominik 1c):
    "pair"   only Sparks both admins paired once with a one-time code (Funktionen → Chats → Chats mit anderen Sparks);
    "open"   every Spark, like e-mail; the admin can block one.
Blocked is blocked in both modes, at once, for the whole Spark.

Spark to Spark: every message is one HTTPS POST to https://<domain>/api/verbund/in, a JSON body signed with the
Spark's own Ed25519 key (derived from the Spark's secret key with HKDF, so it never leaves the Spark and comes along
only with a move backup). The signature covers the receiving domain too, so a message cannot be sent on to a third
Spark; time (±10 minutes) and a one-time number stop a replay. The key of the other Spark comes from its
/.well-known/spark-verbund, fetched over https (the certificate proves the domain) and then kept: a different key
later is refused until the admin removes the Spark and pairs again. Outbound only to public addresses (netguard
PUBLIC; never the home network through a foreign name), nothing during the Notaus.

What comes from another Spark is data, never a command: it goes to no model and no tool, the page shows it as text,
the own speaker can read it as someone else's words. Accepted only from allowed Sparks, from people whose request was
accepted, inside fixed limits (size, rate per Spark, 20 open requests per person). The other Spark learns only what it
needs: the sender's address, display name and the message. It never learns which profiles exist here: every
request it sends gets the same "ok", whether someone took it or not.

Delivery waits when the other Spark is away: again after 1 minute, after 5 minutes, then every hour, at most 7 days.
The second tick comes when the other Spark has the message; after 7 days the message shows "nicht zugestellt".

Logs only fixed words and numbers ("verbund: sent", "verbund: refused signature"), never a domain, a name or a text;
the domains are only in the admin's list. Live (tile Chats): Sparks, contacts, in and out today, waiting.

Storage (USERS_DIR/_verbund/, in the backup with users/): peers.json (domain -> key, state, times, counts),
contacts.json (uid -> rid -> address, name, state), handles.json (uid -> handle), queue.json (what still goes out),
pairs.json (hashes of open pairing codes).
"""
import asyncio
import base64
import collections
import hashlib
import json
import os
import re
import secrets
import threading
import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

import features
import profiles
import verbundgruppe
from common import DayCounter

VERSION = 1
MAX_BODY = 32 * 1024     # one request between Sparks
MAX_KEYDOC = 8 * 1024    # the other Spark's /.well-known/spark-verbund
SKEW = 600               # a request's time may differ this much
MAX_PEERS = 200          # Sparks in the list
MAX_CONTACTS = 300       # contacts on other Sparks per person
MAX_WAITING = 20         # open requests one person gets
MAX_ASKING = 20          # open requests one person sends
MAX_QUEUE = 5000         # waiting to go out
KEEP = 7 * 86400         # how long the Spark keeps trying
STEPS = (60, 300)        # again after 1 and 5 minutes, then every hour
HOUR = 3600
PAIR_SECS = 24 * 3600    # a pairing code works a day and once
MAX_PAIRS = 5
PEER_PER_MIN = 120       # requests from one Spark per minute
FETCH_PER_MIN = 30       # look-ups of other Sparks' keys per minute (open mode: strangers can make the Spark ask)
NO_DAYS = 30             # a declined request: the same address is not heard again this long
TIMEOUT = 10
DOMAIN = re.compile(r"(?=.{4,200}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(:[0-9]{2,5})?")
HANDLE = re.compile(r"[a-z0-9][a-z0-9._-]{0,29}")
RID = re.compile(r"r_[0-9a-f]{12}")
NONCE = re.compile(r"[0-9a-f]{32}")
MID = re.compile(r"[0-9a-f]{12}")
TYPES = ("pair", "ask", "yes", "msg", "read", "edit", "back", "react") + verbundgruppe.TYPES
STATES = ("in", "out", "ok", "no", "block")
WELL_KNOWN = "/.well-known/spark-verbund"
INBOX = "/api/verbund/in"
BLOB_PATH = "/api/verbund/blob"
BLOB_KEEP = 24 * 3600            # a file waits this long here for its message
BLOB_DAY = 500 * 1024**2         # bytes of files one Spark may send here per day
BLOB_WAITING = 2 * 1024**3       # all files waiting here for their message together
BLOB_TIMEOUT = 120               # one file to another Spark
SHA = re.compile(r"[0-9a-f]{64}")
MODES = ("pair", "open")

_lock = threading.RLock()
_pkey = None             # the Ed25519 key (backup._forget_cached drops it after a restore)
_nonces = {}             # (domain, nonce) -> time, the last 2 * SKEW seconds
_peer_rate = collections.defaultdict(collections.deque)   # domain -> request times (a minute)
_fetches = collections.deque()                            # look-ups of keys (a minute)
_kick = None             # asyncio.Event: something new to send
_kick_loop = None        # ... and the event loop it belongs to
_count = DayCounter(**{"in": 0, "out": 0, "refused": 0, "failed": 0, "files_in": 0, "files_out": 0, "bytes": {}})   # today (Live)
_today = _count.today


# ---------------------------------------------------------------- switches
def cfg():
    return features.chat_cfg()


def domain(c=None):
    d = str((cfg() if c is None else c).get("verbund_domain") or "").strip().lower()
    return d if DOMAIN.fullmatch(d) else ""


def mode(c=None):
    m = (cfg() if c is None else c).get("verbund_mode")
    return m if m in MODES else "pair"


def _ready(c):
    return bool(domain(c))


features.READY["verbund"] = _ready   # needs the Spark's own address from outside (chat.verbund_domain)


def admin_on():
    return features.admin_on("verbund")


def usable(uid):
    """The admin allows it (not blocked for this profile) and Chats work for the person."""
    import chats
    return bool(uid and features.allowed("verbund", uid) and chats.usable(uid))


def media_on():
    return features.admin_on("verbundmedia")


def media_ok(uid):
    """Photos, files and voice to and from other Sparks for this person: the switch, Verbund and chat media."""
    import chats
    return bool(usable(uid) and features.allowed("verbundmedia", uid) and chats.media_ok(uid))


# ---------------------------------------------------------------- the Spark's own key
def _priv():
    global _pkey
    if _pkey:
        return _pkey
    import vault
    vault._key()   # makes the Spark's secret key when there is none yet
    with open(vault.KEY_FILE, "rb") as f:
        base = f.read().strip()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"speech-spark verbund v1").derive(base)
    _pkey = Ed25519PrivateKey.from_private_bytes(seed)
    return _pkey


def public_b64():
    from cryptography.hazmat.primitives import serialization
    raw = _priv().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def fingerprint(key_b64):
    """What two admins compare: 20 hex digits of the key's SHA-256 in groups of four."""
    try:
        h = hashlib.sha256(base64.b64decode(key_b64)).hexdigest()[:20].upper()
    except (ValueError, TypeError):
        return ""
    return " ".join(h[i:i + 4] for i in range(0, 20, 4))


def _signed(to_domain, raw):
    return b"spark-verbund v1\n" + to_domain.encode() + b"\n" + raw


def sign(to_domain, raw):
    return base64.b64encode(_priv().sign(_signed(to_domain, raw))).decode()


def verify(key_b64, to_domain, raw, sig_b64):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64))
        sig = base64.b64decode(sig_b64)
        if len(sig) != 64:
            return False
        key.verify(sig, _signed(to_domain, raw))
        return True
    except Exception:
        return False


def _key_ok(k):
    try:
        return isinstance(k, str) and len(base64.b64decode(k, validate=True)) == 32
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- storage
def _dir():
    return profiles._path("_verbund")


def _read(name):
    try:
        with open(os.path.join(_dir(), name)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(name, d):
    os.makedirs(_dir(), mode=0o700, exist_ok=True)
    profiles._write(os.path.join(_dir(), name), d)


def _log(what, **nums):
    """A journal line: fixed words and numbers only (never a domain, a name or a text)."""
    print("verbund: " + what + "".join(f" | {k} {v}" for k, v in nums.items()), flush=True)


def _live(text):
    try:
        import live
        live.mark("Chats", text)
    except Exception:
        pass


# ---------------------------------------------------------------- addresses
_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _slug(name):
    s = unicodedata.normalize("NFKD", (name or "").lower().translate(_UML))
    s = re.sub(r"[^a-z0-9]+", ".", s.encode("ascii", "ignore").decode()).strip(".")[:24]
    return s if HANDLE.fullmatch(s or "") else "person"


def handle(uid, make=True):
    """The person's part before the @ (made once from its name, kept when the name changes)."""
    with _lock:
        d = _read("handles.json")
        h = d.get(uid)
        if isinstance(h, str) and HANDLE.fullmatch(h):
            return h
        if not make or not profiles.by_id(uid):
            return ""
        taken, base = set(v for v in d.values() if isinstance(v, str)), _slug((profiles.by_id(uid) or {}).get("name"))
        h, n = base, 1
        while h in taken:
            n += 1
            h = f"{base}{n}"
        d[uid] = h
        _save("handles.json", d)
        return h


def uid_of_handle(h):
    if not HANDLE.fullmatch(h or ""):
        return ""
    for uid, x in _read("handles.json").items():
        if x == h and profiles.by_id(uid):
            return uid
    return ""


def address(uid):
    d = domain()
    h = handle(uid) if d else ""
    return f"{h}@{d}" if h else ""


def split(addr):
    """("handle", "domain") of an address, or raises ValueError."""
    addr = str(addr or "").strip().lower()
    if addr.count("@") != 1:
        raise ValueError("Eine Spark-Adresse sieht so aus: name@spark.example.de")
    h, d = addr.split("@")
    if not HANDLE.fullmatch(h) or not DOMAIN.fullmatch(d):
        raise ValueError("Eine Spark-Adresse sieht so aus: name@spark.example.de")
    return h, d


def rid_of(addr):
    return "r_" + hashlib.sha256(("far|" + addr).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- other Sparks
def peers():
    d = _read("peers.json")
    return {k: v for k, v in d.items() if DOMAIN.fullmatch(k) and isinstance(v, dict) and _key_ok(v.get("key"))}


def _save_peers(p):
    _save("peers.json", p)


def peer_allowed(dom, p=None):
    """Messages to and from this Spark may go: paired, or open mode and not blocked."""
    p = peers() if p is None else p
    x = p.get(dom)
    if x and x.get("state") == "blocked":
        return False
    if x and x.get("state") == "paired":
        return True
    return mode() == "open"


def _touch_peer(dom, way, now):
    with _lock:
        p = peers()
        x = p.get(dom)
        if x:
            x["last"] = now
            x[way] = int(x.get(way) or 0) + 1
            _save_peers(p)


# ---------------------------------------------------------------- contacts
def _contacts():
    d = _read("contacts.json")
    return {u: {r: c for r, c in v.items() if RID.fullmatch(r) and isinstance(c, dict) and c.get("state") in STATES}
            for u, v in d.items() if isinstance(v, dict)}


def contacts_of(uid):
    return _contacts().get(uid, {})


def contact(uid, rid):
    return contacts_of(uid).get(rid)


def names():
    """{rid: shown name} for chats.py: the name the other one sent, with its Spark's domain kept out (contacts,
    and people met in groups across Sparks)."""
    out = {r: x["name"] for r, x in _people().items() if x.get("name")}
    for v in _contacts().values():
        for r, c in v.items():
            if c.get("name"):
                out[r] = c["name"]
    return out


def addr_of(rid):
    for v in _contacts().values():
        c = v.get(rid)
        if c and c.get("addr"):
            return c["addr"]
    return str(_people().get(rid, {}).get("addr") or "")


MAX_PEOPLE = 5000        # people met in groups across Sparks (address and name, the oldest go first)


def _people():
    p = _read("people.json").get("people")
    return p if isinstance(p, dict) else {}


def remember(addr, name):
    """A person on another Spark met in a group (verbundgruppe.py): address and shown name, for the chat's lines."""
    try:
        h, d = split(addr)
    except ValueError:
        return ""
    addr = f"{h}@{d}"
    rid = rid_of(addr)
    with _lock:
        p = _people()
        if p.get(rid) == {"addr": addr, "name": name, "t": p.get(rid, {}).get("t")}:
            return rid
        p[rid] = {"addr": addr, "name": name, "t": time.time()}
        if len(p) > MAX_PEOPLE:
            for k in sorted(p, key=lambda k: p[k].get("t") or 0)[:len(p) - MAX_PEOPLE]:
                p.pop(k, None)
        _save("people.json", {"people": p})
    return rid


def _set_contact(uid, rid, **kw):
    with _lock:
        d = _contacts()
        mine = d.setdefault(uid, {})
        c = mine.setdefault(rid, {})
        c.update(kw)
        _save("contacts.json", d)
        return c


def _drop_contact(uid, rid):
    with _lock:
        d = _contacts()
        if d.get(uid, {}).pop(rid, None) is not None:
            _save("contacts.json", d)


def can_write(uid, rid):
    c = contact(uid, rid)
    if not c or c.get("state") != "ok" or not usable(uid) or not admin_on():
        return False
    return peer_allowed(split(c["addr"])[1])


def why_not(uid, rid):
    if not admin_on():
        return "Chats mit anderen Sparks sind gerade ausgeschaltet."
    if not usable(uid):
        return ("Chats mit anderen Sparks gehen für dich gerade nicht. " + features.missing_text("verbund", uid)).strip()
    c = contact(uid, rid)
    if not c or c.get("state") != "ok":
        return "Diese Person ist nicht mehr in deinen Kontakten auf anderen Sparks."
    return "Mit diesem Spark sind Chats gerade nicht erlaubt."


def listing(uid):
    """The person's contacts on other Sparks for the page: requests to it first, then its own, then the rest."""
    order = {"in": 0, "out": 1, "ok": 2, "block": 3}
    out = [{"id": r, "addr": c.get("addr", ""), "name": c.get("name", ""), "state": c["state"], "t": c.get("t", 0)}
           for r, c in contacts_of(uid).items() if c["state"] in order]
    out.sort(key=lambda x: (order[x["state"]], (x["name"] or x["addr"]).lower()))
    return out


def ask(uid, addr, now=None):
    """A contact request from uid to a person on another Spark. Returns the contact's rid."""
    now = time.time() if now is None else now
    if not usable(uid) or not admin_on():
        raise PermissionError("Chats mit anderen Sparks sind für dich aus.")
    h, d = split(addr)
    if d == domain():
        raise ValueError("Diese Adresse ist auf diesem Spark. Schreib der Person einfach unter ＋ Neuer Chat.")
    p = peers()
    if not peer_allowed(d, p):
        raise PermissionError("Mit diesem Spark sind Chats nicht erlaubt. Der Admin koppelt Sparks unter "
                              "Funktionen → Chats → Chats mit anderen Sparks.")
    addr = f"{h}@{d}"
    rid = rid_of(addr)
    mine = contacts_of(uid)
    c = mine.get(rid)
    if c and c.get("state") == "in":
        answer(uid, rid, "ok", now)
        return rid
    if c and c.get("state") == "ok":
        return rid
    if c and c.get("state") == "out" and now - float(c.get("t") or 0) < HOUR:
        return rid    # asked a moment ago: not again
    if not c and sum(1 for x in mine.values() if x.get("state") == "out") >= MAX_ASKING:
        raise OverflowError(f"Du hast schon {MAX_ASKING} offene Anfragen.")
    if not c and len(mine) >= MAX_CONTACTS:
        raise OverflowError(f"Höchstens {MAX_CONTACTS} Kontakte auf anderen Sparks.")
    import chats
    _set_contact(uid, rid, addr=addr, name=(c or {}).get("name", ""), state="out", t=now)
    _enqueue(d, {"type": "ask", "from": handle(uid), "to": h, "name": chats.name_of(uid)[:40]}, now=now)
    _log("asked")
    _live("Verbund: Kontaktanfrage raus")
    return rid


def answer(uid, rid, act, now=None):
    """Annehmen ("ok"), Ablehnen ("no", the other one learns nothing) or Sperren ("block") of a request; also
    unblocking ("unblock": gone from the list, a new request can come)."""
    now = time.time() if now is None else now
    c = contact(uid, rid)
    if not c:
        raise LookupError("no such contact")
    if act == "ok":
        if c.get("state") not in ("in", "ok"):
            raise LookupError("no such request")
        if not usable(uid) or not admin_on():
            raise PermissionError("Chats mit anderen Sparks sind für dich aus.")
        h, d = split(c["addr"])
        if not peer_allowed(d):
            raise PermissionError("Mit diesem Spark sind Chats gerade nicht erlaubt.")
        import chats
        _set_contact(uid, rid, state="ok", t=now)
        _enqueue(d, {"type": "yes", "from": handle(uid), "to": h, "name": chats.name_of(uid)[:40]}, now=now)
        _log("accepted")
        return chats.open_far(uid, rid, now)
    if act == "no":
        _set_contact(uid, rid, state="no", t=now)
        _log("declined")
        return ""
    if act == "block":
        _set_contact(uid, rid, state="block", t=now)
        _log("blocked")
        return ""
    if act == "unblock":
        _drop_contact(uid, rid)
        return ""
    raise ValueError("unknown answer")


def remove(uid, rid):
    """Out of the own contacts (the chat stays to read; nothing goes in any more). The other Spark is not told."""
    if not contact(uid, rid):
        raise LookupError("no such contact")
    _drop_contact(uid, rid)
    _log("removed")


def forget(uid):
    """A deleted profile: its contacts, its address and what still waited to go out from it (but leaving the groups
    of other Sparks, chats.forget)."""
    with _lock:
        d = _contacts()
        if d.pop(uid, None) is not None:
            _save("contacts.json", d)
        h = _read("handles.json")
        mine = h.pop(uid, None)
        if mine is not None:
            _save("handles.json", h)
            q = _read("queue.json")
            items = [x for x in q.get("items") or [] if (x.get("body") or {}).get("from") != mine
                     or (x.get("body") or {}).get("type") == "gleave"]   # its groups on other Sparks hear it is gone
            _save("queue.json", {"items": items})


# ---------------------------------------------------------------- what goes out (queue)
def _queue():
    q = _read("queue.json").get("items")
    return [x for x in q or [] if isinstance(x, dict) and DOMAIN.fullmatch(str(x.get("domain") or ""))
            and isinstance(x.get("body"), dict)]


def _enqueue(dom, body, cid="", mid="", now=None):
    now = time.time() if now is None else now
    with _lock:
        q = _queue()
        if len(q) >= MAX_QUEUE:
            raise OverflowError("Zu viele Nachrichten warten auf andere Sparks. Bitte später noch einmal.")
        q.append({"id": secrets.token_hex(6), "domain": dom, "body": body, "cid": cid, "mid": mid, "tries": 0,
                  "next": now, "t": now})
        _save("queue.json", {"items": q})
    _wake()


def _wake():
    """The delivery loop looks at once (from its own event loop, or from another thread through it)."""
    k, loop = _kick, _kick_loop
    if k is None or loop is None or loop.is_closed():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        k.set()
    else:
        loop.call_soon_threadsafe(k.set)


def waiting_count():
    return len(_queue())


def out_event(uid, rid, kind, cid="", mid="", **fields):
    """A message or a change in a chat with someone on another Spark, into the queue (chats.py calls this)."""
    c = contact(uid, rid)
    if not c or c.get("state") != "ok":
        return False
    h, d = split(c["addr"])
    body = {"type": kind, "from": handle(uid), "to": h}
    body.update({k: v for k, v in fields.items() if v is not None})
    _enqueue(d, body, cid, mid)
    return True


def _next(tries, now):
    return now + (STEPS[tries - 1] if tries <= len(STEPS) else HOUR)


async def _post(dom, raw, sig):
    """One POST to the other Spark's inbox: its status code, or 0 when it could not be reached."""
    import httpx
    import netguard
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=MAX_BODY, follow_redirects=False,
                                   timeout=httpx.Timeout(TIMEOUT, connect=TIMEOUT)) as c:
            r = await c.post("https://" + dom + INBOX, content=raw,
                             headers={"Content-Type": "application/json", "X-Spark-From": domain(), "X-Spark-Sig": sig})
            return r.status_code
    except Exception:
        return 0


def _wire(dom, body, now):
    b = dict(body, v=VERSION, t=int(now), n=secrets.token_hex(16))
    raw = json.dumps(b, ensure_ascii=False, separators=(",", ":")).encode()
    return raw, sign(dom, raw)


async def deliver_once(now=None):
    """What is due goes out, oldest first; a Spark that does not answer is tried again later as a whole.
    Returns how many went out."""
    now = time.time() if now is None else now
    if not admin_on() or not domain():
        return 0
    q = sorted(_queue(), key=lambda x: float(x.get("t") or 0))
    # a Spark that did not answer waits as a whole until its retry is due (its newer ones do not go first)
    sent, down = 0, {x["domain"] for x in q if int(x.get("tries") or 0) and float(x.get("next") or 0) > now}
    for x in q:
        dom = x["domain"]
        if dom in down or float(x.get("next") or 0) > now:
            continue
        if now - float(x.get("t") or now) > KEEP or not peer_allowed(dom):
            _done(x, failed=True)
            continue
        status = await _send_one(dom, x, now)
        if status is None:                 # the file of a message is gone here (taken back, chat cleared)
            _done(x, failed=True)
            continue
        if 200 <= status < 300:
            _done(x)
            sent += 1
            _today()["out"] += 1
            _touch_peer(dom, "out", now)
            if x["body"].get("type") == "msg" and x.get("cid") and x.get("mid"):
                import chats
                chats.far_seen(x["cid"], x["mid"], "got")
        elif status in (400, 401, 403, 404, 409, 413):   # 401: the other Spark takes no files (its gate)
            _done(x, failed=True)          # the other Spark refuses it for good
            _log("refused there", status=status)
        else:                              # away, busy (429), 5xx: later, the rest of that Spark too
            down.add(dom)
            tries = 0
            with _lock:
                q = _queue()
                for y in q:
                    if y["id"] == x["id"]:
                        y["tries"] = int(y.get("tries") or 0) + 1
                        y["next"] = _next(y["tries"], now)
                        tries = y["tries"]
                _save("queue.json", {"items": q})
            _log("retry", tries=tries)
    if sent:
        _log("sent", n=sent)
    return sent


async def _send_one(dom, x, now):
    """One queued request; a message with a file sends the file first. None: its file is no longer here."""
    m = x["body"].get("media")
    if isinstance(m, dict) and m.get("sha"):
        import chats
        data = chats.far_blob(x.get("cid", ""), x.get("mid", ""))
        if data is None or hashlib.sha256(data).hexdigest() != m["sha"]:
            return None
        status = await _post_blob(dom, m["sha"], data, now)
        if not 200 <= status < 300:
            return status
        _today()["files_out"] += 1
    raw, sig = _wire(dom, x["body"], now)
    return await _post(dom, raw, sig)


async def _post_blob(dom, sha, data, now):
    """The file of a message to the other Spark: the signed head (time, one-time number, hash, size) in a header,
    the bytes as the body. Its status code, or 0 when it could not be reached."""
    import httpx
    import netguard
    head = json.dumps({"v": VERSION, "t": int(now), "n": secrets.token_hex(16), "sha": sha, "size": len(data)},
                      separators=(",", ":")).encode()
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=MAX_BODY, follow_redirects=False,
                                   timeout=httpx.Timeout(BLOB_TIMEOUT, connect=TIMEOUT)) as c:
            r = await c.post("https://" + dom + BLOB_PATH, content=data,
                             headers={"Content-Type": "application/octet-stream", "X-Spark-From": domain(),
                                      "X-Spark-Blob": base64.urlsafe_b64encode(head).decode(), "X-Spark-Sig": sign(dom, head)})
            return r.status_code
    except Exception:
        return 0


def _done(x, failed=False):
    with _lock:
        q = [y for y in _queue() if y["id"] != x["id"]]
        _save("queue.json", {"items": q})
    if failed:
        _today()["failed"] += 1
        if x["body"].get("type") == "msg" and x.get("cid") and x.get("mid"):
            import chats
            chats.far_seen(x["cid"], x["mid"], "fail")
        _log("given up")


async def loop():
    """Every 30 seconds, and at once when something new waits."""
    global _kick, _kick_loop
    _kick, _kick_loop = asyncio.Event(), asyncio.get_running_loop()
    while True:
        try:
            await asyncio.wait_for(_kick.wait(), 30)
        except asyncio.TimeoutError:
            pass
        _kick.clear()
        try:
            blob_tidy()
            await deliver_once()
        except Exception as e:
            _log("loop failed", error=type(e).__name__)


# ---------------------------------------------------------------- the other Spark's key
async def fetch_key(dom):
    """The key from https://<dom>/.well-known/spark-verbund (public addresses only), or "" when there is none."""
    import httpx
    import netguard
    now = time.time()
    with _lock:
        while _fetches and now - _fetches[0] > 60:
            _fetches.popleft()
        if len(_fetches) >= FETCH_PER_MIN:
            return ""
        _fetches.append(now)
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=MAX_KEYDOC, follow_redirects=False,
                                   timeout=httpx.Timeout(TIMEOUT, connect=TIMEOUT)) as c:
            r = await c.get("https://" + dom + WELL_KNOWN)
            if r.status_code != 200:
                return ""
            d = r.json()
    except Exception:
        return ""
    k = d.get("key") if isinstance(d, dict) and d.get("v") == VERSION else None
    return k if _key_ok(k) else ""


# ---------------------------------------------------------------- pairing (mode "pair")
def _pairs(now):
    d = _read("pairs.json")
    return {h: t for h, t in d.items() if re.fullmatch(r"[0-9a-f]{64}", h) and isinstance(t, (int, float)) and t > now}


def pair_new(now=None):
    """A one-time code for the admin of another Spark: "<own domain>#<secret>", a day long."""
    now = time.time() if now is None else now
    if not domain():
        raise ValueError("Zuerst die eigene Adresse von außen eintragen.")
    with _lock:
        p = _pairs(now)
        if len(p) >= MAX_PAIRS:
            raise OverflowError(f"Höchstens {MAX_PAIRS} offene Kopplungs-Codes.")
        secret = secrets.token_urlsafe(18)
        p[hashlib.sha256(secret.encode()).hexdigest()] = now + PAIR_SECS
        _save("pairs.json", p)
    _log("pair code made")
    return f"{domain()}#{secret}"


def _pair_take(secret, now):
    if not isinstance(secret, str) or not 16 <= len(secret) <= 64:
        return False
    h = hashlib.sha256(secret.encode()).hexdigest()
    with _lock:
        p = _pairs(now)
        if h not in p:
            return False
        p.pop(h)
        _save("pairs.json", p)
    return True


def _pair_known(secret, now):
    return isinstance(secret, str) and hashlib.sha256(secret.encode()).hexdigest() in _pairs(now)


async def pair_use(code, now=None):
    """The code of the other Spark's admin: fetch its key, tell it ours with the secret, then both know each other."""
    now = time.time() if now is None else now
    code = str(code or "").strip()
    m = re.fullmatch(r"([^#\s]{4,200})#([A-Za-z0-9_\-]{16,64})", code)
    if not m or not DOMAIN.fullmatch(m.group(1).lower()):
        raise ValueError("Der Code sieht so aus: spark.example.de#… (vom Admin des anderen Sparks).")
    dom, secret = m.group(1).lower(), m.group(2)
    if dom == domain():
        raise ValueError("Das ist der Code dieses Sparks.")
    if not domain():
        raise ValueError("Zuerst die eigene Adresse von außen eintragen.")
    p = peers()
    if len(p) >= MAX_PEERS and dom not in p:
        raise OverflowError(f"Höchstens {MAX_PEERS} Sparks.")
    key = await fetch_key(dom)
    if not key:
        raise LookupError("Der andere Spark ist nicht erreichbar oder hat Chats mit anderen Sparks nicht an.")
    old = p.get(dom)
    if old and old.get("key") != key:
        raise PermissionError("Dieser Spark hat einen anderen Schlüssel als beim letzten Mal. Erst entfernen, dann neu koppeln.")
    raw, sig = _wire(dom, {"type": "pair", "secret": secret}, now)
    status = await _post(dom, raw, sig)
    if status != 200:
        _log("pairing refused", status=status)
        raise PermissionError("Der andere Spark hat den Code nicht angenommen (abgelaufen, schon benutzt oder falsch).")
    with _lock:
        p = peers()
        p[dom] = {"key": key, "state": "paired", "t": now, "last": now, "in": 0, "out": 0}
        _save_peers(p)
    _log("paired")
    _live("Verbund: Spark gekoppelt")
    return {"domain": dom, "fingerprint": fingerprint(key)}


def peer_set(dom, act, now=None):
    """The admin: allow ("allow", paired from now on), block ("block") or remove ("remove") a Spark."""
    now = time.time() if now is None else now
    dom = str(dom or "").lower()
    with _lock:
        p = peers()
        if dom not in p:
            raise LookupError("no such Spark")
        if act == "remove":
            p.pop(dom)
        elif act in ("allow", "block"):
            p[dom]["state"] = "paired" if act == "allow" else "blocked"
            p[dom]["t"] = now
        else:
            raise ValueError("unknown action")
        _save_peers(p)
        if act != "allow":
            q = [x for x in _queue() if x["domain"] != dom]
            _save("queue.json", {"items": q})
    _log("spark " + {"allow": "allowed", "block": "blocked", "remove": "removed"}[act])


def for_admin():
    p, now = peers(), time.time()
    counts = collections.Counter()
    for v in _contacts().values():
        for c in v.values():
            if c.get("state") == "ok" and c.get("addr"):
                counts[c["addr"].split("@")[-1]] += 1
    q = collections.Counter(x["domain"] for x in _queue())
    return {"domain": domain(), "mode": mode(), "on": admin_on(), "key": fingerprint(public_b64()),
            "pairs": len(_pairs(now)), "max_pairs": MAX_PAIRS,
            "peers": sorted([{"domain": d, "state": x.get("state", "open"), "fingerprint": fingerprint(x["key"]),
                              "t": x.get("t", 0), "last": x.get("last", 0), "contacts": counts.get(d, 0),
                              "waiting": q.get(d, 0), "in": int(x.get("in") or 0), "out": int(x.get("out") or 0)}
                             for d, x in p.items()], key=lambda x: x["domain"])}


def for_live():
    """Zustand → Live (tile Chats): numbers only."""
    if not admin_on():
        return {"on": False}
    p = peers()
    c = _today()
    return {"on": True, "sparks": sum(1 for x in p.values() if x.get("state") != "blocked"),
            "contacts": sum(1 for v in _contacts().values() for x in v.values() if x.get("state") == "ok"),
            "in": c["in"], "out": c["out"], "waiting": waiting_count(), "media": media_on(),
            "files_in": c["files_in"], "files_out": c["files_out"]}


# ---------------------------------------------------------------- what comes in
def _clean_name(v):
    import chats
    return chats.clean_name(str(v or ""))[:40]


def _seen_nonce(dom, n, now):
    with _lock:
        for k in [k for k, t in _nonces.items() if now - t > 2 * SKEW]:
            _nonces.pop(k, None)
        if (dom, n) in _nonces:
            return True
        if len(_nonces) > 50000:
            _nonces.clear()
        _nonces[(dom, n)] = now
        return False


def _rate_ok(dom, now):
    with _lock:
        q = _peer_rate[dom]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= PEER_PER_MIN:
            return False
        q.append(now)
        if len(_peer_rate) > 1000:
            for k in [k for k, v in _peer_rate.items() if not v]:
                _peer_rate.pop(k, None)
        return True


def _refuse(status, word):
    _today()["refused"] += 1
    _log("refused " + word)
    raise HTTPException(status, "refused")


async def receive(dom, raw, sig, now=None):
    """One request of another Spark (already within MAX_BODY): checked in this order, every step a fixed refusal."""
    now = time.time() if now is None else now
    if not admin_on() or not domain():
        _refuse(404, "off")
    dom = (dom or "").strip().lower()
    if not DOMAIN.fullmatch(dom) or dom == domain():
        _refuse(400, "sender")
    try:
        body = json.loads(raw)
    except ValueError:
        _refuse(400, "form")
    if not isinstance(body, dict) or body.get("v") != VERSION or body.get("type") not in TYPES \
            or not isinstance(body.get("t"), int) or not NONCE.fullmatch(str(body.get("n") or "")):
        _refuse(400, "form")
    if abs(now - body["t"]) > SKEW:
        _refuse(400, "time")
    if not _rate_ok(dom, now):
        _log("refused rate")
        raise HTTPException(429, "too many", headers={"Retry-After": "60"})
    p = peers()
    x = p.get(dom)
    kind = body["type"]
    if x and x.get("state") == "blocked":
        _refuse(403, "blocked")
    if kind == "pair":
        if not _pair_known(body.get("secret"), now):
            _refuse(403, "pairing")
    elif not peer_allowed(dom, p):
        _refuse(403, "unknown spark")
    key = (x or {}).get("key", "")
    if not key:
        key = await fetch_key(dom)
        if not key:
            _refuse(403, "no key")
    elif kind == "pair":
        fresh = await fetch_key(dom)
        if fresh and fresh != key:
            _refuse(403, "key changed")
    if not verify(key, domain(), raw, sig):
        _refuse(403, "signature")
    if _seen_nonce(dom, body["n"], now):
        _refuse(409, "replay")
    if kind == "pair":
        if not _pair_take(body.get("secret"), now):
            _refuse(403, "pairing")
        with _lock:
            p = peers()
            if len(p) >= MAX_PEERS and dom not in p:
                _refuse(403, "full")
            p[dom] = {"key": key, "state": "paired", "t": now, "last": now, "in": 0, "out": 0}
            _save_peers(p)
        _log("paired")
        _live("Verbund: Spark gekoppelt")
        return {"ok": True}
    if not x:
        with _lock:   # open mode: the Spark is known from now on, with this key
            p = peers()
            if len(p) >= MAX_PEERS:
                _refuse(403, "full")
            p.setdefault(dom, {"key": key, "state": "open", "t": now, "last": now, "in": 0, "out": 0})
            _save_peers(p)
    _touch_peer(dom, "in", now)
    _today()["in"] += 1
    m = await _media_in(dom, body) if kind == "msg" and "media" in body else None
    _handle(dom, body, now, m)
    return {"ok": True}   # always the same answer: the other Spark never learns who is here


def _handle(dom, b, now, media=None):
    """What one request means; anything that does not fit is dropped without a word to the sender. media: the
    message's file as this Spark made it again (_media_in), only for a message that announced one."""
    if b["type"] in verbundgruppe.TYPES:   # groups across Sparks (verbundgruppe.py)
        verbundgruppe.handle(dom, b, now)
        return
    to = uid_of_handle(str(b.get("to") or ""))
    frm = str(b.get("from") or "").lower()
    if not to or not HANDLE.fullmatch(frm) or not usable(to):
        _log("dropped", why=1)
        return
    addr = f"{frm}@{dom}"
    rid = rid_of(addr)
    c = contact(to, rid)
    kind = b["type"]
    import chats
    if kind == "ask":
        if c and c.get("state") == "block" or c and c.get("state") == "no" and now - float(c.get("t") or 0) < NO_DAYS * 86400:
            _log("dropped", why=2)
            return
        if c and c.get("state") == "ok":     # they lost us: say yes again
            _enqueue(dom, {"type": "yes", "from": handle(to), "to": frm, "name": chats.name_of(to)[:40]}, now=now)
            return
        if c and c.get("state") == "out":    # both asked: accepted on both sides
            _set_contact(to, rid, state="ok", name=_clean_name(b.get("name")) or c.get("name", ""), t=now)
            _enqueue(dom, {"type": "yes", "from": handle(to), "to": frm, "name": chats.name_of(to)[:40]}, now=now)
            chats.open_far(to, rid, now)
            chats.far_tell(to)
            return
        mine = contacts_of(to)
        if not c and (sum(1 for y in mine.values() if y.get("state") == "in") >= MAX_WAITING or len(mine) >= MAX_CONTACTS):
            _log("dropped", why=3)
            return
        _set_contact(to, rid, addr=addr, name=_clean_name(b.get("name")), state="in", t=now)
        _log("request in")
        _live("Verbund: Kontaktanfrage rein")
        chats.far_tell(to, ask=not c)        # a request asked again is no new notification
        return
    if not c:
        _log("dropped", why=4)
        return
    if kind == "yes":
        if c.get("state") in ("out", "ok"):
            _set_contact(to, rid, state="ok", name=_clean_name(b.get("name")) or c.get("name", ""), t=now)
            chats.open_far(to, rid, now)
            chats.far_tell(to)
            _log("request accepted there")
        return
    if c.get("state") != "ok":
        _log("dropped", why=5)
        return
    mid = str(b.get("id") or "")
    if not MID.fullmatch(mid):
        _log("dropped", why=6)
        return
    if kind == "msg":
        text = b.get("text") if isinstance(b.get("text"), str) else ""
        if "media" in b and not media:
            _log("dropped", why=7)                # a file announced but not here, not allowed or not readable
            return
        if not text.strip() and not media:
            return
        reply = str(b.get("reply") or "")
        chats.far_in(to, rid, mid, text, reply if MID.fullmatch(reply) else "", now, media=media)
    elif kind == "read":
        chats.far_mark(to, rid, mid, "read")
    elif kind in ("edit", "back", "react"):
        chats.far_change(to, rid, kind, mid, b.get("text") if kind == "edit" else b.get("emoji") if kind == "react" else None, now)


# ---------------------------------------------------------------- files from other Sparks
def _blob_dir():
    return os.path.join(_dir(), "blobs")


def _blob_file(dom, sha):
    """Per sending Spark: one Spark can never hand in or take the file another one sent."""
    return os.path.join(_blob_dir(), hashlib.sha256(dom.encode()).hexdigest()[:16] + "_" + sha)


def _blob_waiting():
    try:
        return sum(e.stat().st_size for e in os.scandir(_blob_dir()) if e.is_file())
    except OSError:
        return 0


def blob_tidy(now=None):
    """Files whose message did not come within BLOB_KEEP go."""
    now = time.time() if now is None else now
    n = 0
    try:
        for e in os.scandir(_blob_dir()):
            if e.is_file() and now - e.stat().st_mtime > BLOB_KEEP:
                os.remove(e.path)
                n += 1
    except OSError:
        pass
    if n:
        _log("files dropped", n=n)
    return n


def blob_gate(headers):
    """Before a byte of a file is read (panel.py BodyLimit): the switches are on and the sender is a Spark that may
    send here and whose key is known. The full check follows in blob_head."""
    if not admin_on() or not media_on() or not domain():
        return False
    dom = str(headers.get("x-spark-from") or "").strip().lower()
    x = peers().get(dom) if DOMAIN.fullmatch(dom) else None
    return bool(x and x.get("key") and peer_allowed(dom))


def blob_head(dom, head_b64, sig, now=None):
    """The signed head of a file: checked like a message (form, time, rate, allowed Spark with a known key,
    signature, one-time number) and against the day's limit. Returns (domain, sha, size)."""
    import chats
    now = time.time() if now is None else now
    if not admin_on() or not media_on() or not domain():
        _refuse(404, "file while off")
    dom = (dom or "").strip().lower()
    if not DOMAIN.fullmatch(dom) or dom == domain():
        _refuse(400, "sender")
    try:
        raw = base64.urlsafe_b64decode(str(head_b64 or "").encode())
        head = json.loads(raw)
    except ValueError:
        _refuse(400, "form")
    if not isinstance(head, dict) or head.get("v") != VERSION or not isinstance(head.get("t"), int) \
            or not NONCE.fullmatch(str(head.get("n") or "")) or not SHA.fullmatch(str(head.get("sha") or "")) \
            or not isinstance(head.get("size"), int) or not 0 < head["size"] <= chats.MAX_FILE:
        _refuse(400, "form")
    if abs(now - head["t"]) > SKEW:
        _refuse(400, "time")
    if not _rate_ok(dom, now):
        _log("refused rate")
        raise HTTPException(429, "too many", headers={"Retry-After": "60"})
    x = peers().get(dom)
    if not x or not x.get("key") or not peer_allowed(dom):
        _refuse(403, "unknown spark")
    if not verify(x["key"], domain(), raw, sig):
        _refuse(403, "signature")
    if _seen_nonce(dom, head["n"], now):
        _refuse(409, "replay")
    day = _today()["bytes"]
    if int(day.get(dom) or 0) + head["size"] > BLOB_DAY or _blob_waiting() + head["size"] > BLOB_WAITING:
        _log("refused file limit")
        raise HTTPException(429, "too much today", headers={"Retry-After": "3600"})
    return dom, head["sha"], head["size"]


def blob_put(dom, sha, size, data):
    """The bytes of a checked head: exactly its size and hash, kept sealed until the message comes."""
    import chats
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
        _refuse(400, "file")
    os.makedirs(_blob_dir(), mode=0o700, exist_ok=True)
    path = _blob_file(dom, sha)
    with open(path + ".tmp", "wb") as f:
        f.write(chats.seal_bytes(data, "verbund", sha, dom))
    os.replace(path + ".tmp", path)
    day = _today()
    day["bytes"][dom] = int(day["bytes"].get(dom) or 0) + size
    day["files_in"] += 1
    _log("file in", kb=size // 1024)
    return {"ok": True}


def _blob_take(dom, sha):
    import chats
    path = _blob_file(dom, sha)
    try:
        with open(path, "rb") as f:
            raw = f.read()
        os.remove(path)
    except OSError:
        return None
    return chats.unseal_bytes(raw, "verbund", sha, dom)


async def _media_in(dom, b):
    """The file a message announces, made again here as if uploaded (chats.photo/a_file/voice); None when it is not
    here, the person does not take files from other Sparks or it cannot be read. The file goes either way."""
    import chats
    m = b.get("media")
    if not isinstance(m, dict) or m.get("kind") not in chats.MEDIA or not SHA.fullmatch(str(m.get("sha") or "")):
        return None
    data = _blob_take(dom, m["sha"])
    to = uid_of_handle(str(b.get("to") or ""))
    frm = str(b.get("from") or "").lower()
    if data is None or not to or not HANDLE.fullmatch(frm) or not media_ok(to):
        return None
    c = contact(to, rid_of(f"{frm}@{dom}"))
    if not c or c.get("state") != "ok":
        return None
    try:
        if m["kind"] == "photo":
            return await chats.photo(data)
        if m["kind"] == "voice":
            return await chats.voice(data)
        return chats.a_file(data, str(m.get("name") or "")[:300])
    except ValueError:
        _log("file unreadable", kind=m["kind"])
        return None


# ---------------------------------------------------------------- endpoints
from core import admin_code, assistant, auth, json_body, own_profile  # noqa: E402

router = APIRouter()


@router.get(WELL_KNOWN)   # open: other Sparks ask for the key; only while Chats mit anderen Sparks is on
def api_well_known(request: Request):
    import guard
    guard.limit(request, "trust")
    if not admin_on():
        _refuse(404, "key while off")
    return JSONResponse({"v": VERSION, "key": public_b64(), "inbox": INBOX}, headers={"Cache-Control": "max-age=300"})


@router.post(INBOX)       # open: another Spark, proven by its signature instead of a login
async def api_in(request: Request):
    import guard
    guard.limit(request, "verbundin")
    if not admin_on():
        _refuse(404, "off")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        _refuse(413, "size")
    return await receive(request.headers.get("x-spark-from", ""), raw, request.headers.get("x-spark-sig", ""))


@router.post(BLOB_PATH)   # open: another Spark's file for a message, proven by the signed head
async def api_blob(request: Request):
    import guard
    guard.limit(request, "verbundin")
    dom, sha, size = blob_head(request.headers.get("x-spark-from", ""), request.headers.get("x-spark-blob", ""),
                               request.headers.get("x-spark-sig", ""))
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > size:
            _refuse(413, "file size")
    return blob_put(dom, sha, size, bytes(data))


def _on(request: Request, prof=Depends(own_profile)):
    """Like chats' own: the profile's browser login or its iPhone app, the switches, a limit per minute."""
    import guard
    if request.headers.get(profiles.DEVICE_HEADER) and profiles.key_scope(request) != "app":
        _log("page refused", why="device")
        raise HTTPException(403, "only in the profile's own browser login or the iPhone app")
    if not admin_on():
        _log("page refused", why="off")
        raise HTTPException(403, "Chats mit anderen Sparks sind auf dem Spark aus.")
    if not usable(prof["id"]):
        _log("page refused", why="no chats")
        raise HTTPException(403, "Chats sind auf diesem Spark für dich aus.")
    guard.limit(request, "verbund", prof["id"])
    return prof


def _rid(v):
    v = str(v or "")
    if not RID.fullmatch(v):
        raise HTTPException(400, "contact id is required")
    return v


def _state(uid):
    import mfa
    a = address(uid)
    return {"on": True, "address": a, "qr": mfa._qr_svg(a) if a else "", "contacts": listing(uid),
            "max_waiting": MAX_WAITING}


@router.get("/api/verbund", dependencies=[Depends(assistant)])
def api_state(request: Request, prof=Depends(_on)):
    return _state(prof["id"])


@router.post("/api/verbund/ask", dependencies=[Depends(assistant)])
async def api_ask(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 1024)
    try:
        rid = ask(prof["id"], body.get("addr"))
    except (PermissionError, ValueError, OverflowError, LookupError) as e:
        _log("ask refused", why=type(e).__name__)
        raise chats._err(e)
    return {"id": rid, **_state(prof["id"])}


@router.post("/api/verbund/answer", dependencies=[Depends(assistant)])
async def api_answer(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 1024)
    try:
        cid = answer(prof["id"], _rid(body.get("id")), str(body.get("act") or ""))
    except (PermissionError, ValueError, OverflowError, LookupError) as e:
        _log("answer refused", why=type(e).__name__)
        raise chats._err(e)
    return {"chat": cid, **_state(prof["id"])}


@router.post("/api/verbund/remove", dependencies=[Depends(assistant)])
async def api_remove(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 1024)
    try:
        remove(prof["id"], _rid(body.get("id")))
    except LookupError as e:
        _log("remove refused", why=type(e).__name__)
        raise chats._err(e)
    return _state(prof["id"])


@router.post("/api/verbund/open", dependencies=[Depends(assistant)])
async def api_open(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 1024)
    rid = _rid(body.get("id"))
    if not can_write(prof["id"], rid):
        _log("open refused")
        raise HTTPException(403, why_not(prof["id"], rid))
    return {"id": chats.open_far(prof["id"], rid)}


def _admin(request: Request):
    import guard
    guard.limit(request, "verbundadmin", admin=True)


@router.get("/api/admin/verbund", dependencies=[Depends(auth), Depends(_admin)])
def api_admin(request: Request):
    import mcpserver
    from urllib.parse import urlsplit
    host = (urlsplit(mcpserver.base_url(request)).netloc or "").lower()
    return {**for_admin(), "suggest": host if DOMAIN.fullmatch(host) else ""}


@router.post("/api/admin/verbund/pair", dependencies=[Depends(auth), Depends(_admin), Depends(admin_code)])
def api_pair_new(request: Request):
    import guard
    try:
        code = pair_new()
    except (ValueError, OverflowError) as e:
        _log("pair code refused", why=type(e).__name__)
        raise HTTPException(429 if isinstance(e, OverflowError) else 400, str(e))
    guard.log("verbund_code")
    return {"code": code, "hours": PAIR_SECS // 3600, **for_admin()}


@router.post("/api/admin/verbund/connect", dependencies=[Depends(auth), Depends(_admin), Depends(admin_code)])
async def api_connect(request: Request):
    import guard
    body = await json_body(request, 1024)
    try:
        r = await pair_use(body.get("code"))
    except (ValueError, OverflowError, LookupError, PermissionError) as e:
        _log("pairing refused", why=type(e).__name__)
        raise HTTPException(400, str(e))
    guard.log("verbund_paired")
    return {**r, **for_admin()}


@router.post("/api/admin/verbund/peer", dependencies=[Depends(auth), Depends(_admin)])
async def api_peer(request: Request):
    import guard
    body = await json_body(request, 1024)
    act = str(body.get("act") or "")
    try:
        peer_set(body.get("domain"), act)
    except LookupError:
        _log("spark change refused", why="unknown")
        raise HTTPException(404, "Diesen Spark gibt es in der Liste nicht.")
    except ValueError as e:
        _log("spark change refused", why=type(e).__name__)
        raise HTTPException(400, str(e))
    guard.log("verbund_peer_" + act)
    return for_admin()
