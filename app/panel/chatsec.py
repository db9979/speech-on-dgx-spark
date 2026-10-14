"""Private chats with end-to-end encryption (Messenger Schritt C, plan plaene/messenger-e2e.md, Dominik 2026-10-12
"plus einzelne private Chats mit Ende-zu-Ende", picks 1a 2a 3a: a key per device, browser and Android app first,
only two people).

Every device (each browser, the Android app's page) makes its own key pair (ECDH P-256) the first time a private
chat is used. The private key never leaves the device (the browser keeps it as a non-extractable WebCrypto key in
IndexedDB); the Spark keeps only the public keys (users/<uid>/chatkeys.json) and the messages as the device sent
them: a box the Spark cannot open.

A box (made and opened only in chatsec.js):
    {"v": 1, "f": sender key id, "iv": b64 12 bytes, "ct": b64 AES-256-GCM(content key, payload JSON, aad=cid),
     "k": {key id: {"s": b64 16 bytes salt, "i": b64 12 bytes, "w": b64 AES-GCM(wrap key, content key)}}}
    wrap key = HKDF-SHA256(ECDH(sender device, receiving device), salt, "spark-e2e-v1|cid|from|to")
The content key is wrapped for every current device of both people (the sender's other devices too). The Spark
checks the form and that every current device of the other person is in "k" (nobody is left out silently), and
that "f" is a current key of the sender; it never sees a text, a file name or a photo. Photos, files and voice
come as one more box-encrypted blob beside the message (its key travels inside the message's payload).

A new device of someone who already has one (Dominik 2026-10-14, Wahl 2 „Verlauf vom alten Gerät übertragen“): its key
waits SHARE_SECS for an older device of the same person. That device shows a code made from the new key (the new one
shows the same code), and after "Übertragen" it opens each content key of its private chats and wraps it once more for
the new device; the Spark adds only that wrap, marked {"b": the wrapping device}, and never touches the text:
    wrap key = HKDF-SHA256(ECDH(wrapping device, new device), salt, "spark-e2e-v1|cid|wrapping|new")

What the Spark sees: who wrote to whom, when, how big. The people compare the "Sicherheitsnummer" (made from both
sides' public keys, in chatsec.js) once; a new or removed device puts a line into each private chat of that person.

Switches: Funktionen → Chats → „Private Chats (Ende-zu-Ende)“ (chat.chats_private, off) on top of Chats; the
profile's own switch is the one of Chats. A new device key asks for the second step's code (stufen.py, Bestätigen).
"""
import base64
import hashlib
import json
import re
import secrets
import threading
import time

import features
import profiles


MAX_KEYS = 10            # current device keys per profile
KEEP_GONE = 30           # removed keys kept (their public half opens older messages)
MAX_BOX = 64 * 1024      # one message's box as JSON
MAX_BLOB = 26 * 1024**2  # a photo, file or voice message, encrypted (25 MB and the tag)
SHARE_SECS = 24 * 3600   # how long a new device waits for the history from an older one
SHARE_MAX = 300          # wraps per request
KID = re.compile(r"[0-9a-f]{12}")
KINDS = ("browser", "android", "iphone")
_B64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_lock = threading.RLock()


# ---------------------------------------------------------------- switches
def admin_on():
    return features.admin_on("chatprivate")


def usable(uid):
    import chats
    return bool(chats.usable(uid) and features.allowed("chatprivate", uid))


# ---------------------------------------------------------------- device keys
def _file(uid):
    return profiles._path(uid, "chatkeys.json")


def _load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    keys = [x for x in (d.get("keys") if isinstance(d, dict) else None) or []
            if isinstance(x, dict) and KID.fullmatch(str(x.get("id"))) and isinstance(x.get("pub"), str)]
    return keys


def _save(uid, keys):
    gone = [k for k in keys if k.get("gone")][-KEEP_GONE:]
    profiles._write(_file(uid), {"keys": [k for k in keys if not k.get("gone")] + gone})


def current(uid):
    """The device keys messages are made for now."""
    return [k for k in _load(uid) if not k.get("gone")]


def _b64(v, n=None, most=None):
    v = str(v or "")
    if not v or not _B64.fullmatch(v) or len(v) > 4 * ((most or n or 1 << 20) + 2) // 3 + 4:
        raise ValueError("bad box")
    try:
        raw = base64.b64decode(v, validate=True)
    except ValueError:
        raise ValueError("bad box")
    if n is not None and len(raw) != n:
        raise ValueError("bad box")
    if most is not None and len(raw) > most:
        raise ValueError("bad box")
    return raw


def _check_pub(pub):
    """An uncompressed P-256 point (65 bytes), really on the curve."""
    raw = _b64(pub, 65)
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
    except ValueError:
        raise ValueError("Das ist kein gültiger Schlüssel.")
    return base64.b64encode(raw).decode()


def add_key(uid, pub, kind, now=None):
    """A device's public key; returns its id. The private chats of uid get a line "neues Gerät"."""
    now = time.time() if now is None else now
    if not usable(uid):
        raise PermissionError("Private Chats sind für dich ausgeschaltet.")
    pub = _check_pub(pub)
    kind = kind if kind in KINDS else "browser"
    with _lock:
        keys = _load(uid)
        old = next((k for k in keys if k["pub"] == pub and not k.get("gone")), None)
        if old:
            return old["id"]
        if sum(1 for k in keys if not k.get("gone")) >= MAX_KEYS:
            raise OverflowError(f"Höchstens {MAX_KEYS} Geräte für private Chats. Ein altes unter ⓘ → Deine Geräte entfernen.")
        kid = secrets.token_hex(6)
        had = any(not k.get("gone") for k in keys)
        keys.append({"id": kid, "pub": pub, "kind": kind, "t": now, **({"want": now} if had else {})})
        _save(uid, keys)
    _changed(uid, "newkey", now)
    _log("key added", kind=kind)
    return kid


def remove_key(uid, kid, now=None):
    now = time.time() if now is None else now
    with _lock:
        keys = _load(uid)
        k = next((k for k in keys if k["id"] == kid and not k.get("gone")), None)
        if not k:
            raise LookupError("no such key")
        k["gone"] = now
        _save(uid, keys)
    _changed(uid, "keygone", now)
    _log("key removed")


def forget(uid):
    """A deleted profile: its keys go (chats.forget takes its messages)."""
    import os
    try:
        os.remove(_file(uid))
    except OSError:
        pass


def _changed(uid, what, now):
    """A line in each private chat of uid: the other side compares the Sicherheitsnummer again."""
    import chats
    for cid, c in chats.mine(uid).items():
        if c.get("kind") != "priv":
            continue

        def f(meta, d, idx):
            chats._sys(d, uid, now, what, [uid])
            meta["updated"] = now
            return meta["members"]
        try:
            chats._tell(chats._mutate(cid, f, now), {"type": "chat", "id": cid})
        except LookupError:
            pass


def keys_for(uid, cid):
    """Every key (current and removed) of the people in a private chat uid is in, for the page to make and open boxes."""
    import chats
    c = chats._member(uid, cid)
    if c.get("kind") != "priv":
        raise LookupError("no such chat")
    out = []
    for u in c["members"]:
        for k in _load(u):
            out.append({"id": k["id"], "uid": u, "pub": k["pub"], "kind": k.get("kind", "browser"), "t": int(k.get("t") or 0),
                        **({"gone": int(k["gone"])} if k.get("gone") else {})})
    return out


def _wants(k, now):
    return bool(k.get("want")) and now - float(k["want"]) < SHARE_SECS


def own(uid, now=None):
    """The own devices; "want": a new one waiting for the history, "pub" so an older one can show its code."""
    now = time.time() if now is None else now
    return [{"id": k["id"], "kind": k.get("kind", "browser"), "t": int(k.get("t") or 0),
             **({"want": True, "pub": k["pub"]} if _wants(k, now) else {})} for k in current(uid)]


# ---------------------------------------------------------------- the history for a new device of the same person
def _pair(uid, by, new, now):
    """(older device, new device) of uid, both current; the new one still waits and is younger."""
    keys = {k["id"]: k for k in current(uid)}
    b, n = keys.get(by), keys.get(new)
    if not b or not n or by == new:
        raise LookupError("no such key")
    if not _wants(n, now) or float(b.get("t") or 0) >= float(n.get("t") or 0):
        raise PermissionError("Dieses Gerät wartet nicht mehr auf den Verlauf.")
    return b, n


def share_list(uid, cid, by, new, now=None):
    """The boxes of a private chat the new device cannot open yet: id, sender, sending key, the wrap for by."""
    import chats
    now = time.time() if now is None else now
    _pair(uid, by, new, now)
    c = chats._member(uid, cid)
    if c.get("kind") != "priv":
        raise LookupError("no such chat")
    out = []
    for x in chats._chat(cid, c, now)["items"]:
        b = x.get("box") if x.get("kind") == "box" and not x.get("gone") else None
        if isinstance(b, dict) and by in (b.get("k") or {}) and new not in b["k"]:
            out.append({"id": x["id"], "from": x["from"], "f": b.get("f"), "w": b["k"][by]})
    return out


def share_add(uid, cid, by, new, wraps, now=None):
    """Adds the new device's wraps (made by the older device by) to the boxes; returns how many were added."""
    import chats
    now = time.time() if now is None else now
    _pair(uid, by, new, now)
    if not isinstance(wraps, dict) or not wraps or len(wraps) > SHARE_MAX:
        raise ValueError("bad wraps")
    clean = {}
    for mid, w in wraps.items():
        if not chats.MID.fullmatch(str(mid)) or not isinstance(w, dict) or set(w) != {"s", "i", "w"}:
            raise ValueError("bad wraps")
        _b64(w["s"], 16)
        _b64(w["i"], 12)
        _b64(w["w"], 48)
        clean[mid] = {"s": w["s"], "i": w["i"], "w": w["w"], "b": by}
    c = chats._member(uid, cid)
    if c.get("kind") != "priv":
        raise LookupError("no such chat")

    def f(meta, d, idx):
        n = 0
        for x in d["items"]:
            b = x.get("box") if x.get("kind") == "box" and not x.get("gone") else None
            w = clean.get(x["id"])
            if w and isinstance(b, dict) and by in (b.get("k") or {}) and new not in b["k"] and len(b["k"]) < 3 * MAX_KEYS:
                b["k"][new] = w
                n += 1
        return n
    n = chats._mutate(cid, f, now)
    if n:
        chats._tell([uid], {"type": "keys", "id": cid})   # the new device opens what it can read now
    return n


def share_done(uid, new, n, now=None):
    """The older device is through: the new one waits no more."""
    now = time.time() if now is None else now
    with _lock:
        keys = _load(uid)
        k = next((k for k in keys if k["id"] == new and not k.get("gone")), None)
        if not k or not k.get("want"):
            raise LookupError("no such key")
        k.pop("want", None)
        _save(uid, keys)
    import chats
    chats._tell([uid], {"type": "keys", "id": ""})
    _log("history shared", n=max(0, min(10**6, int(n) if isinstance(n, int) else 0)))


def waiting(now=None):
    """New devices waiting for their history, for Live (a number)."""
    now = time.time() if now is None else now
    return sum(1 for p in profiles.names() for k in current(p["id"]) if _wants(k, now))


# ---------------------------------------------------------------- a private chat of two
def priv_id(a, b):
    return "c" + hashlib.sha256(("priv|" + "|".join(sorted((a, b)))).encode()).hexdigest()[:12]


def why_not(rcpt, sender):
    import chats
    if not usable(sender):
        return "Private Chats sind für dich ausgeschaltet."
    if not chats.takes(rcpt, sender) or not usable(rcpt):
        return chats.why_not(rcpt, sender) if not chats.takes(rcpt, sender) else "Diese Person hat private Chats nicht an."
    if not current(rcpt):
        return "Diese Person hat noch kein Gerät für private Chats. Sie muss einmal einen privaten Chat öffnen."
    if not current(sender):
        return "Dieses Gerät hat noch keinen Schlüssel für private Chats."
    return ""


def can(rcpt, sender):
    return not why_not(rcpt, sender)


def open_priv(uid, other, now=None):
    """The private chat of two profiles (made the first time): both have private chats on and a device key."""
    import chats
    now = time.time() if now is None else now
    if not admin_on():
        raise PermissionError("Private Chats sind auf dem Spark aus.")
    if not chats.UID.fullmatch(other or "") or other == uid or not profiles.by_id(other):
        raise LookupError("no such profile")
    cid = priv_id(uid, other)
    with chats._lock:
        idx = chats._index()
        if cid in idx:
            return cid
        why = why_not(other, uid)
        if why:
            raise PermissionError(why)
        if sum(1 for c in idx.values() if uid in c["members"]) >= chats.MAX_CHATS:
            raise OverflowError(f"Höchstens {chats.MAX_CHATS} Chats.")
        idx[cid] = {"kind": "priv", "members": sorted([uid, other]), "admins": [], "by": uid, "t": now,
                    "updated": now, "vanish": 0, "last": {}, "unread": {}}
        chats._save_chat(cid, {"items": []})
        chats._save_index(idx)
    chats._log("new chat", kind="priv")
    return cid


def check_box(uid, c, box, blob=False):
    """The box as the page sent it, in its fixed form; every current device of the other one is in it."""
    if not isinstance(box, dict) or box.get("v") != 1 or set(box) - {"v", "f", "iv", "ct", "k"}:
        raise ValueError("bad box")
    f = str(box.get("f") or "")
    if not any(k["id"] == f for k in current(uid)):
        raise PermissionError("Dieses Gerät ist für private Chats nicht mehr eingetragen. Seite neu laden.")
    _b64(box.get("iv"), 12)
    _b64(box.get("ct"), most=MAX_BOX)
    k = box.get("k")
    if not isinstance(k, dict) or not k or len(k) > 2 * MAX_KEYS:
        raise ValueError("bad box")
    known = {x["id"] for u in c["members"] for x in current(u)}
    for kid, w in k.items():
        if kid not in known or not isinstance(w, dict) or set(w) != {"s", "i", "w"}:
            raise ValueError("bad box")
        _b64(w["s"], 16)
        _b64(w["i"], 12)
        _b64(w["w"], 48)
    others = [u for u in c["members"] if u != uid]
    if any(x["id"] not in k for u in others for x in current(u)):
        raise PermissionError("Die andere Person hat ein neues Gerät. Seite neu laden und noch einmal senden.")
    clean = {"v": 1, "f": f, "iv": box["iv"], "ct": box["ct"], "k": {kid: dict(w) for kid, w in k.items()}}
    if len(json.dumps(clean)) > MAX_BOX + 8 * 1024:
        raise ValueError("too large")
    return clean


def blob_check(data):
    """An encrypted photo, file or voice message: only its size can be checked (12 bytes IV first, then the GCM text)."""
    if not data or len(data) < 12 + 16 or len(data) > MAX_BLOB:
        raise ValueError("Die Datei ist zu groß." if data and len(data) > MAX_BLOB else "bad blob")
    return data


# ---------------------------------------------------------------- numbers for Live, words for the journal
def for_live():
    import chats
    if not admin_on():
        return {"on": False}
    idx = chats._index()
    return {"on": True, "chats": sum(1 for x in idx.values() if x.get("kind") == "priv"),
            "devices": sum(len(current(u["id"])) for u in profiles.names()), "waiting": waiting()}


def _log(what, **nums):
    import chats
    chats._log("private " + what, **nums)


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from core import assistant, confirm_code, json_body, own_profile  # noqa: E402

router = APIRouter()


def _on(request: Request, prof=Depends(own_profile)):
    """Only in the profile's own browser login (the Android app's page is one): the key lives in that browser."""
    import guard
    if request.headers.get(profiles.DEVICE_HEADER):
        raise HTTPException(403, "only in the profile's own browser login")
    if not admin_on():
        raise HTTPException(403, "private chats are turned off")
    if not usable(prof["id"]):
        raise HTTPException(403, "Chats gehen für dich gerade nicht. " + features.missing_text("chats", prof["id"]))
    guard.limit(request, "chatskeys", prof["id"])
    return prof


@router.get("/api/chats/keys", dependencies=[Depends(assistant)])
def api_keys(request: Request, id: str = "", prof=Depends(_on)):
    """Without id: the own devices; with the id of a private chat: every key of both people in it."""
    import chats
    if not id:
        return {"keys": own(prof["id"]), "max": MAX_KEYS}
    try:
        return {"keys": keys_for(prof["id"], chats._cid(id))}
    except LookupError as e:
        raise chats._err(e)


@router.post("/api/chats/keys", dependencies=[Depends(assistant)])
async def api_key_add(request: Request, prof=Depends(_on)):
    """A new device for private chats: a new key, like a new device for the Spark (the second step's code)."""
    import chats
    import guard
    body = await json_body(request, 2048)
    await confirm_code(request, prof["id"], prof["name"])
    try:
        kid = add_key(prof["id"], body.get("pub"), str(body.get("kind") or "browser"))
    except (PermissionError, ValueError, OverflowError) as e:
        raise chats._err(e)
    guard.log("chat_key_added", name=prof["name"], uid=prof["id"])
    return {"id": kid, "keys": own(prof["id"])}


@router.post("/api/chats/keys/remove", dependencies=[Depends(assistant)])
async def api_key_remove(request: Request, prof=Depends(_on)):
    import chats
    import guard
    kid = str((await json_body(request, 1024)).get("id") or "")
    if not KID.fullmatch(kid):
        raise HTTPException(400, "key id is required")
    try:
        remove_key(prof["id"], kid)
    except LookupError as e:
        raise chats._err(e)
    guard.log("chat_key_removed", name=prof["name"], uid=prof["id"])
    return {"keys": own(prof["id"])}


@router.post("/api/chats/private", dependencies=[Depends(assistant)])
async def api_private(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 1024)
    try:
        cid = open_priv(prof["id"], str(body.get("to") or ""))
    except (LookupError, PermissionError, OverflowError) as e:
        raise chats._err(e)
    return {"id": cid}


def _share_args(body_or_q):
    by, new = str(body_or_q.get("by") or ""), str(body_or_q.get("new") or "")
    if not KID.fullmatch(by) or not KID.fullmatch(new):
        raise HTTPException(400, "key id is required")
    return by, new


@router.get("/api/chats/share", dependencies=[Depends(assistant)])
def api_share_list(request: Request, id: str = "", by: str = "", new: str = "", prof=Depends(_on)):
    """For an older device of the same person: the boxes of one private chat the new device cannot open yet."""
    import chats
    b, n = _share_args({"by": by, "new": new})
    try:
        return {"items": share_list(prof["id"], chats._cid(id), b, n)}
    except (LookupError, PermissionError) as e:
        _log("history refused", why=type(e).__name__)
        raise chats._err(e)


@router.post("/api/chats/share", dependencies=[Depends(assistant)])
async def api_share_add(request: Request, prof=Depends(_on)):
    import chats
    body = await json_body(request, 96 * 1024)
    b, n = _share_args(body)
    try:
        added = share_add(prof["id"], chats._cid(body.get("id")), b, n, body.get("wraps"))
    except (LookupError, PermissionError, ValueError) as e:
        _log("history refused", why=type(e).__name__)
        raise chats._err(e)
    return {"added": added}


@router.post("/api/chats/share/done", dependencies=[Depends(assistant)])
async def api_share_done(request: Request, prof=Depends(_on)):
    import chats
    import guard
    body = await json_body(request, 1024)
    _, n = _share_args({"by": "0" * 12, "new": body.get("new")})
    try:
        share_done(prof["id"], n, body.get("n"))
    except LookupError as e:
        _log("history refused", why="LookupError")
        raise chats._err(e)
    guard.log("chat_history_shared", name=prof["name"], uid=prof["id"])
    return {"keys": own(prof["id"])}
