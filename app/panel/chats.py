"""Chats between the people of this Spark (plan plaene/messenger.md, Dominik 2026-10-12: "WhatsApp ablösen").

A chat is two profiles or a group. Everybody in it sees the same messages, kept until they are deleted (or the
chat's own rule "selbst löschen" takes them), in the Spark's backup like the profiles, never anywhere else.

Off until the admin allows it (chat.chats); then every profile has it (Freigabe vereinfachen, 2026-10-13). Groups
have their own admin switch (chat.chats_groups). Guests get nothing. Since V01.0.488 the old "Nachrichten" live here
(plan plaene/nachrichten-in-chats.md): the assistant's "Sag Anna …" (messages.py), the fixed group "Alle"
(chat.messages_all, each profile's msg_all), new messages on the own speaker (msg_speaker) and announcements.

Who may write to whom (fixed rules in messages.takes_from, never the model): the other one has chats on, has not
blocked the sender and takes messages from every profile or picked the sender. A group can only take in people who
take messages from the one adding them; anybody can leave a group. The group Alle has no admins: everybody who takes
part is in it, leaving it switches msg_all off.

What a message is: someone else's words. In the assistant it comes as outside text (it can never make it act),
in the page it is shown only as text (textContent), links are not opened or fetched, nothing is ever spoken
on its own. Live, the journal and Logs → Anfragen get kinds and numbers only, never a text, a name or a group name.

Storage (USERS_DIR/_chats/, in the backup with users/):
    index.json   {"chats": {cid: {"kind": "one"|"group"|"priv" (chatsec.py), "members": [uid], "admins": [uid], "name": sealed,
                                  "by": uid, "t", "updated", "vanish": seconds, "last": {...}, "unread": {uid: n},
                                  "read": {uid: t}, "got": {uid: t}, "mute": {uid: until | -1}, "cleared": {uid: t}}}}
    <cid>.json   {"items": [{id, from, t, text (sealed AES-GCM), kind "text"|"sys", reply?, edited?, gone?,
                             react: {uid: emoji}, via?, sys?}]}
Texts are sealed with AES-256-GCM, a key of its own derived from the Spark's secret key (HKDF), the chat and the
message id as associated data (a text cannot be moved to another message or chat). A backup restored on another
Spark without a move backup keeps the chats but not their texts (like every other secret).
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

import features
import profiles

MAX_TEXT = 4000          # characters per message
MAX_ITEMS = 5000         # messages kept per chat (the oldest go first)
MAX_MEMBERS = 50         # people in a group
MAX_GROUPS = 30          # groups a profile is in
MAX_CHATS = 300          # chats a profile is in
MAX_NAME = 40            # a group's name
PAGE = 60                # messages per page
PER_HOUR = 240           # messages one profile may send in an hour
EDIT_SECS = 15 * 60      # a message can be changed this long
BACK_SECS = 60 * 60      # ... and taken back for everybody this long
TYPING_SECS = 6          # "schreibt …" shows this long
REACTIONS = ("👍", "❤️", "😂", "😮", "😢", "🙏")
VANISH = (0, 86400, 7 * 86400, 90 * 86400)      # "selbst löschen": off, a day, a week, 90 days
MUTE = (0, 3600, 8 * 3600, -1)                  # stumm: off, an hour, 8 hours, always
MAX_STREAMS = 8          # open pages per profile with the event stream
STREAM_SECONDS = 30 * 60
BEAT = 25
QUEUE = 100
FIND_MAX = 30            # hits of a search
CID = re.compile(r"c[0-9a-f]{12}")
MID = re.compile(r"[0-9a-f]{12}")
UID = re.compile(r"u_[0-9a-f]{12}")
RID = re.compile(r"r_[0-9a-f]{12}")   # a person on another Spark (verbund.py), only in chats of kind "far"
TWO = ("one", "priv", "far")         # the kinds of a chat of two
ALL_ID = "c" + hashlib.sha256(b"all|speech-spark").hexdigest()[:12]   # the fixed group Alle (one per Spark)
SYS = ("made", "add", "remove", "leave", "name", "vanish", "admin", "joined")   # what a line of the chat itself says
MEDIA = ("photo", "file", "voice")             # what else a message can be (Schritt B, chat.chats_media)
MAX_PHOTO_IN = 15 * 1024**2  # a photo as it comes from the phone
PHOTO_SIDE, THUMB_SIDE = 2048, 480
MAX_FILE = 25 * 1024**2      # a file (PDF, Office, text)
MAX_VOICE_SECS = 300         # a voice message: 5 minutes
MAX_VOICE_IN = 12 * 1024**2
QUOTA = 2 * 1024**3          # photos, files and voice one profile keeps in all its chats
MAX_FILE_NAME = 120
INVITE_DAYS = 7              # a chat invitation works a week (join.py, at most join.CHAT_OPEN open per profile)
MEDIA_WORD = {"photo": "📷 Foto", "file": "📄 Datei", "voice": "🎤 Sprachnachricht"}

_lock = threading.RLock()
_sent = collections.defaultdict(collections.deque)   # uid -> send times (the last hour)
_subs = {}               # uid -> {stream id: (loop, queue)}
_count = {"day": "", "sent": 0, "pushed": 0, "push_failed": 0, "media": 0}   # today, numbers only (Live)
_ckey = None             # the AES-GCM key (backup._forget_cached drops it after a restore)


# ---------------------------------------------------------------- switches
def admin_on():
    return features.admin_on("chats")


def groups_on():
    return features.admin_on("chatgroups")


def usable(uid):
    return bool(uid and features.allowed("chats", uid) and profiles.by_id(uid))


def invite_on():
    return features.admin_on("chatinvite")


def _invite_ready(c):
    import join
    return join.mode() == "invite"


features.READY["chatinvite"] = _invite_ready   # needs Personen und Geräte → Neue Personen „nur mit Einladung“


def media_on():
    return features.admin_on("chatmedia")


def media_ok(uid):
    """Photos, files and voice messages: the admin's switch (Funktionen → Chats → Fotos, Dateien und Sprache) on top of
    Chats; the profile's own switch is the one of Chats."""
    return bool(usable(uid) and features.allowed("chatmedia", uid))


def name_of(uid):
    return (profiles.by_id(uid) or {}).get("name", "")


def _names():
    """{id: name} of the profiles and of the contacts on other Sparks (the name they sent)."""
    names = {x["id"]: x["name"] for x in profiles.names()}
    try:
        import verbund
        names.update(verbund.names())
    except Exception:
        pass
    return names


def takes(rcpt, sender):
    """True when rcpt takes chat messages from sender: both have chats on, rcpt has not blocked sender and takes
    from everybody or picked sender (Ich → Gespräch → Chats „Wer darf mir schreiben“, messages.takes_from).
    rcpt on another Spark (verbund.py): an accepted contact of sender, its Spark allowed."""
    if RID.fullmatch(rcpt or ""):
        import verbund
        return verbund.can_write(sender, rcpt)
    import messages
    return messages.takes_from(rcpt, sender)


def why_not(rcpt, sender):
    """Said to the sender: only "switched off" or "takes none from you", never who blocked whom."""
    if RID.fullmatch(rcpt or ""):
        import verbund
        return verbund.why_not(sender, rcpt)
    if not usable(rcpt):
        return f"{name_of(rcpt) or 'Diese Person'} hat Chats nicht eingeschaltet."
    return f"{name_of(rcpt)} nimmt gerade keine Nachrichten von dir an."


def clean(text, n=MAX_TEXT):
    """Plain text: no control characters except line breaks, no markers of outside text, at most n characters."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]+", " ", text)
    text = re.sub(r"<{3,}|>{3,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(re.sub(r"[ \t]+", " ", x).strip() for x in text.split("\n")).strip()[:n]


def clean_name(name):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]+", " ", str(name or ""))).strip()[:MAX_NAME]


# ---------------------------------------------------------------- sealing (AES-256-GCM)
def _key():
    global _ckey
    if _ckey:
        return _ckey
    import vault
    vault._key()   # makes the Spark's secret key when there is none yet
    try:
        with open(vault.KEY_FILE, "rb") as f:
            base = f.read().strip()
    except OSError:
        return None
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _ckey = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"speech-spark chats v1").derive(base)
    return _ckey


def seal(text, cid, mid):
    if not text:
        return ""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k = _key()
    if not k:
        raise RuntimeError("no key")
    nonce = os.urandom(12)
    ct = AESGCM(k).encrypt(nonce, text.encode(), f"{cid}/{mid}".encode())
    return "g1:" + base64.b64encode(nonce + ct).decode()


def seal_bytes(data, cid, mid, part):
    """A photo, file or voice message, sealed like the texts (bound to chat, message and part)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k = _key()
    if not k:
        raise RuntimeError("no key")
    nonce = os.urandom(12)
    return b"G1" + nonce + AESGCM(k).encrypt(nonce, data, f"{cid}/{mid}/{part}".encode())


def unseal_bytes(raw, cid, mid, part):
    if not raw or raw[:2] != b"G1":
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(_key()).decrypt(raw[2:14], raw[14:], f"{cid}/{mid}/{part}".encode())
    except Exception:
        return None


def unseal(value, cid, mid):
    """The plain text; "" when it cannot be read (another Spark's key, a text moved to another message)."""
    if not isinstance(value, str) or not value.startswith("g1:"):
        return ""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.b64decode(value[3:])
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], f"{cid}/{mid}".encode()).decode()
    except Exception:
        return ""


# ---------------------------------------------------------------- storage
def _dir():
    return profiles._path("_chats")


def _index_file():
    return os.path.join(_dir(), "index.json")


def _chat_file(cid):
    if not CID.fullmatch(cid or ""):
        raise ValueError("bad chat id")
    return os.path.join(_dir(), cid + ".json")


def _read(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, data):
    os.makedirs(_dir(), mode=0o700, exist_ok=True)
    profiles._write(path, data)


def _index():
    d = _read(_index_file())
    chats = d.get("chats") if isinstance(d.get("chats"), dict) else {}
    return {cid: c for cid, c in chats.items() if CID.fullmatch(cid) and isinstance(c, dict)
            and isinstance(c.get("members"), list)}


def _save_index(chats):
    _write(_index_file(), {"chats": chats})


def _chat(cid, meta=None, now=None):
    """One chat's file, its messages without the ones its "selbst löschen" rule already took."""
    d = _read(_chat_file(cid))
    items = [x for x in d.get("items") or [] if isinstance(x, dict) and MID.fullmatch(str(x.get("id")))]
    keep = int((meta or {}).get("vanish") or 0)
    if keep:
        now = time.time() if now is None else now
        items = [x for x in items if now - float(x.get("t") or 0) < keep]
    return {"items": items[-MAX_ITEMS:]}


def _save_chat(cid, d):
    _write(_chat_file(cid), {"items": d["items"][-MAX_ITEMS:]})
    _sweep(cid, d["items"][-MAX_ITEMS:])


def _media_dir(cid):
    if not CID.fullmatch(cid or ""):
        raise ValueError("bad chat id")
    return os.path.join(_dir(), cid)


def _media_file(cid, mid, part):
    if not MID.fullmatch(mid or "") or part not in ("f", "t"):
        raise ValueError("bad media id")
    return os.path.join(_media_dir(cid), f"{mid}.{part}.enc")


def _sweep(cid, items):
    """Photos, files and voice of messages that are gone (taken back, "selbst löschen", the oldest beyond MAX_ITEMS,
    a deleted profile) are removed from the disk with them."""
    try:
        names = os.listdir(_media_dir(cid))
    except OSError:
        return
    keep = {x["id"] for x in items if (x.get("kind") in MEDIA or x.get("blob")) and not x.get("gone")}
    for n in names:
        if n[:12] not in keep:
            try:
                os.remove(os.path.join(_media_dir(cid), n))
            except OSError:
                pass


def _map(meta, k):
    """One of a chat's small maps in the index: read, got, unread, mute, cleared (uid -> time or number)."""
    v = meta.get(k)
    if not isinstance(v, dict):
        v = meta[k] = {}
    return v


def mine(uid):
    """{cid: meta} of the chats the profile is in."""
    return {cid: c for cid, c in _index().items() if uid in c["members"]}


def _member(uid, cid):
    if cid == ALL_ID:   # the group Alle: who takes part right now (all_sync)
        all_sync()
    c = _index().get(cid)
    if not c or uid not in c["members"]:
        raise LookupError("no such chat")
    return c


def one_id(a, b):
    """The chat of two profiles is always the same one."""
    return "c" + hashlib.sha256(("one|" + "|".join(sorted((a, b)))).encode()).hexdigest()[:12]


def _last(cid, x):
    """What the list shows of the newest message (sealed again for the index)."""
    if not x:
        return {}
    out = {"id": x["id"], "from": x["from"], "t": x["t"], "kind": x.get("kind", "text")}
    if x.get("gone"):
        out["gone"] = True
    elif x.get("kind") == "sys":
        out["sys"] = x.get("sys")
    elif x.get("kind") == "box":
        pass                     # a private chat: the Spark has no text to show (the page says 🔒)
    else:
        out["text"] = seal(unseal(x.get("text"), cid, x["id"])[:120], cid, "last")
        if x.get("kind") == "voice":
            out["secs"] = int((x.get("media") or {}).get("secs") or 0)
    return out


# ---------------------------------------------------------------- events (open pages and apps)
def streams():
    """Open event streams (for the live view: only the number)."""
    with _lock:
        return sum(len(x) for x in _subs.values())


def listening(uid):
    with _lock:
        return bool(_subs.get(uid))


def _send_event(uid, ev):
    with _lock:
        subs = list(_subs.get(uid, {}).values())
    for loop, q in subs:
        def put(q=q):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(ev)
        try:
            loop.call_soon_threadsafe(put)
        except RuntimeError:
            pass


def _tell(members, ev, but=None):
    for u in members:
        if u != but:
            _send_event(u, ev)


def _today():
    day = time.strftime("%Y-%m-%d")
    if _count["day"] != day:
        _count.update(day=day, sent=0, pushed=0, push_failed=0, media=0, private=0, spoken=0, far_group_in=0)
    return _count


def _log(what, **nums):
    """A journal line: fixed words and numbers only (never a text, a name or a group name)."""
    print("chats: " + what + "".join(f" | {k} {v}" for k, v in nums.items()), flush=True)


def _live(text):
    try:
        import live
        live.mark("Chats", text)
    except Exception:
        pass


# ---------------------------------------------------------------- what a page sees
def _ticks(x, c, uid):
    """For the own messages: "read" (everybody else read it), "got" (every device of the others has it) or "sent".
    "gelesen" only counts between profiles that both show it (chat_receipts)."""
    others = [u for u in c["members"] if u != uid and not (c.get("kind") == "group" and RID.fullmatch(u))]
    if not others:
        return "sent"
    mine_on = profiles.settings(uid).get("chat_receipts", True) is not False
    if mine_on and all((RID.fullmatch(u) or profiles.settings(u).get("chat_receipts", True) is not False)
                       and float(_map(c, "read").get(u) or 0) >= x["t"] for u in others):
        return "read"
    if all(max(float(_map(c, "got").get(u) or 0), float(_map(c, "read").get(u) or 0)) >= x["t"] for u in others):
        return "got"
    return "sent"


def _public(x, cid, c, d, uid, names):
    out = {"id": x["id"], "from": x["from"], "name": names.get(x["from"], ""), "t": x["t"],
           "kind": x.get("kind", "text"), "mine": x["from"] == uid}
    if x.get("gone"):
        out["gone"] = True
    elif x.get("kind") == "sys":
        out["sys"] = x.get("sys")
        out["who"] = [names.get(u, "") for u in x.get("who") or []][:MAX_MEMBERS]
        if x.get("sys") == "name":
            out["text"] = unseal(x.get("text"), cid, x["id"])
        if x.get("sys") == "vanish":
            out["secs"] = int(x.get("secs") or 0)
        if x.get("sys") in ("call", "call_missed", "call_rejected"):   # anrufe.py: how long, with picture or not
            out["secs"], out["video"] = int(x.get("secs") or 0), bool(x.get("video"))
    elif x.get("kind") == "box":   # private chat (chatsec.py): the box as the sending device made it
        out["box"] = x.get("box")
        if x.get("blob"):
            out["blob"] = {"bytes": int(x["blob"].get("bytes") or 0)}
    else:
        out["text"] = unseal(x.get("text"), cid, x["id"])
        if x.get("kind") in MEDIA:
            m = x.get("media") or {}
            out["media"] = {k: m[k] for k in ("mime", "size", "secs", "w", "h", "ext") if k in m}
            if m.get("name"):
                out["media"]["name"] = unseal(m["name"], cid, x["id"] + "/name")
        if x.get("edited"):
            out["edited"] = True
        if x.get("via"):
            out["via"] = x["via"]
    if x.get("reply") and not x.get("gone"):
        r = next((y for y in d["items"] if y["id"] == x["reply"]), None)
        out["reply"] = {"id": x["reply"], "name": names.get(r["from"], "") if r else "",
                        "text": ("" if not r or r.get("gone") or r.get("kind") == "box" else unseal(r.get("text"), cid, r["id"])[:160]),
                        "gone": not r or bool(r.get("gone")), "kind": (r or {}).get("kind", "text")}
    react = x.get("react") if isinstance(x.get("react"), dict) else {}
    if react:
        n = collections.Counter(v for v in react.values() if v in REACTIONS)
        out["react"] = [{"e": e, "n": k, "me": react.get(uid) == e} for e, k in n.items()]
    if out["mine"] and x.get("kind") != "sys" and not x.get("gone"):
        out["tick"] = _ticks(x, c, uid)
        if x.get("fail"):
            out["fail"] = True     # another Spark did not take it within 7 days (verbund.py)
        now = time.time()
        out["can_edit"] = now - x["t"] < EDIT_SECS and x.get("kind") == "text"
        out["can_back"] = now - x["t"] < BACK_SECS
    return out


def _title(cid, c, uid, names):
    if c.get("kind") == "group":
        return unseal(c.get("name"), cid, "name") or "Gruppe"
    other = next((u for u in c["members"] if u != uid), "")
    if RID.fullmatch(other):
        import verbund
        return names.get(other) or verbund.addr_of(other) or "Kontakt auf einem anderen Spark"
    return names.get(other) or "Gelöschtes Profil"


def listing(uid, now=None):
    """The chat list of a profile, newest first, and the people it can start a chat with."""
    now = time.time() if now is None else now
    all_sync(now)
    names = _names()
    out = []
    for cid, c in mine(uid).items():
        last = c.get("last") or {}
        d_cleared = float((c.get("cleared") or {}).get(uid) or 0)
        if c.get("kind") in TWO and (not last or float(last.get("t") or 0) <= d_cleared):
            continue   # deleted for me and nothing new since, or nobody wrote yet
        if c.get("vanish") and last and now - float(last.get("t") or 0) >= int(c["vanish"]):
            last = {}
        other = next((u for u in c["members"] if u != uid), "") if c.get("kind") in TWO else ""
        item = {"id": cid, "kind": c.get("kind", "one"), "title": _title(cid, c, uid, names),
                "members": [{"id": u, "name": names.get(u, "")} for u in c["members"]][:MAX_MEMBERS],
                "admin": uid in (c.get("admins") or []), "unread": int((c.get("unread") or {}).get(uid) or 0),
                "updated": c.get("updated") or c.get("t") or 0, "vanish": int(c.get("vanish") or 0),
                "mute": _muted_until(c, uid, now), "can_send": True}
        if other:
            item["with"] = other
            item["can_send"] = takes(other, uid)
        if c.get("kind") == "priv":
            import chatsec
            item["private"], item["can_send"] = True, chatsec.can(other, uid)
        if c.get("kind") == "far":
            import verbund
            item["far"], item["addr"] = True, verbund.addr_of(other)
        if c.get("fixed"):
            item["fixed"] = True
        if last and float(last.get("t") or 0) > d_cleared:
            item["last"] = {"t": last["t"], "mine": last.get("from") == uid, "name": names.get(last.get("from"), ""),
                            "kind": last.get("kind", "text"), "gone": bool(last.get("gone")), "sys": last.get("sys"),
                            "text": unseal(last.get("text"), cid, "last")}
        out.append(item)
    out.sort(key=lambda x: -float(x["updated"]))
    return out


def contacts(uid):
    """[{"id", "name", "call"}] the profile can start a chat with (who takes messages from it)."""
    if not usable(uid):
        return []
    import messages
    c = features.chat_cfg()   # once for all profiles, not once per profile and question
    return sorted([x for x in profiles.names() if messages.takes_from(x["id"], uid, c=c)], key=lambda x: x["name"].lower())


def _muted_until(c, uid, now):
    m = (c.get("mute") or {}).get(uid)
    if m == -1:
        return -1
    return int(m) if m and float(m) > now else 0


def items(uid, cid, before="", now=None):
    """One page of a chat (PAGE messages, the newest last), with what the page needs to draw it."""
    now = time.time() if now is None else now
    with _lock:
        if cid == ALL_ID:
            all_sync(now)
        chats = _index()
        c = chats.get(cid)
        if not c or uid not in c["members"]:
            raise LookupError("no such chat")
        _map(c, "got")[uid] = now
        _save_index(chats)
        d = _chat(cid, c, now)
    names = _names()
    cleared = float(_map(c, "cleared").get(uid) or 0)
    shown = [x for x in d["items"] if x["t"] > cleared]
    if before and MID.fullmatch(before):
        at = next((i for i, x in enumerate(shown) if x["id"] == before), len(shown))
        shown = shown[:at]
    page = shown[-PAGE:]
    others = [u for u in c["members"] if u != uid]
    if c.get("kind") == "priv":
        import chatsec
        why = chatsec.why_not(others[0], uid) if others else "Diese Person gibt es nicht mehr."
    elif c.get("fixed"):
        import messages
        why = "" if messages.all_on() and messages.takes_all(uid) else "Nachrichten an alle sind gerade ausgeschaltet."
    if c.get("kind") == "far":
        why = "" if others and takes(others[0], uid) else why_not(others[0], uid) if others else "Diese Person gibt es nicht mehr."
    out = {"id": cid, "kind": c.get("kind", "one"), "title": _title(cid, c, uid, names),
           "items": [_public(x, cid, c, d, uid, names) for x in page], "more": len(shown) > len(page),
           "members": [{"id": u, "name": names.get(u, ""), "admin": u in (c.get("admins") or [])} for u in c["members"]],
           "admin": uid in (c.get("admins") or []), "vanish": int(c.get("vanish") or 0),
           "mute": _muted_until(c, uid, now), "reactions": list(REACTIONS),
           "can_send": (not why if c.get("kind") in ("priv", "far") or c.get("fixed") else
                        takes(others[0], uid) if c.get("kind") == "one" and others else usable(uid) and groups_on()),
           "why": (why if c.get("kind") in ("priv", "far") or c.get("fixed") else
                   why_not(others[0], uid) if c.get("kind") == "one" and others and not takes(others[0], uid) else
                   "" if c.get("kind") == "one" or groups_on() else "Gruppen-Chats sind gerade ausgeschaltet."),
           "private": c.get("kind") == "priv", "fixed": bool(c.get("fixed")), "far": c.get("kind") == "far",
           "far_home": bool(c.get("home")), **({"addr": _far_addr(c, uid)} if c.get("kind") == "far" else {})}
    if spans(c):
        import verbundgruppe
        if not (verbundgruppe.admin_on() and verbundgruppe.usable(uid)):
            out.update(can_send=False, why="Gruppen mit anderen Sparks sind gerade ausgeschaltet.")
    return out


def _far_addr(c, uid):
    import verbund
    return verbund.addr_of(next((u for u in c["members"] if u != uid), ""))


# ---------------------------------------------------------------- changing a chat
def _mutate(cid, fn, now=None, items=True):
    """fn(meta, chat file, index) under the lock; saves the index and (items) the chat's messages. Returns fn's result."""
    with _lock:
        chats = _index()
        c = chats.get(cid)
        if c is None:
            raise LookupError("no such chat")
        d = _chat(cid, c, now) if items else {"items": []}
        res = fn(c, d, chats)
        if cid in chats and items:
            newest = next((x for x in reversed(d["items"])), None)
            c["last"] = _last(cid, newest)
            c["bytes"] = _bytes_of(d["items"][-MAX_ITEMS:])
            _save_chat(cid, d)
        _save_index(chats)
    return res


def _rate(uid, now):
    q = _sent[uid]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= PER_HOUR:
        return False
    if len(_sent) > 5000:
        for k in [k for k, v in _sent.items() if not v or now - v[-1] > 3600]:
            _sent.pop(k, None)
    q.append(now)
    return True


def open_one(uid, other, now=None):
    """The chat of two profiles (made the first time). Only when the other one takes messages from uid."""
    now = time.time() if now is None else now
    if not usable(uid):
        raise PermissionError("Chats sind für dich ausgeschaltet.")
    if not UID.fullmatch(other or "") or other == uid or not profiles.by_id(other):
        raise LookupError("no such profile")
    cid = one_id(uid, other)
    with _lock:
        chats = _index()
        if cid in chats:
            return cid
        if not takes(other, uid):
            raise PermissionError(why_not(other, uid))
        if sum(1 for c in chats.values() if uid in c["members"]) >= MAX_CHATS:
            raise OverflowError(f"Höchstens {MAX_CHATS} Chats.")
        chats[cid] = {"kind": "one", "members": sorted([uid, other]), "admins": [], "by": uid, "t": now,
                      "updated": now, "vanish": 0, "last": {}, "unread": {}}
        _save_chat(cid, {"items": []})
        _save_index(chats)
    _log("new chat", kind="one")
    return cid


# ---------------------------------------------------------------- chats with people on other Sparks (verbund.py)
def far_id(uid, rid):
    return "c" + hashlib.sha256(("far|" + uid + "|" + rid).encode()).hexdigest()[:12]


def open_far(uid, rid, now=None):
    """The chat of uid with a contact on another Spark (made the first time; verbund.py decides who that may be)."""
    now = time.time() if now is None else now
    if not UID.fullmatch(uid or "") or not RID.fullmatch(rid or ""):
        raise LookupError("no such contact")
    cid = far_id(uid, rid)
    with _lock:
        chats = _index()
        if cid in chats:
            return cid
        if sum(1 for c in chats.values() if uid in c["members"]) >= MAX_CHATS:
            raise OverflowError(f"Höchstens {MAX_CHATS} Chats.")
        chats[cid] = {"kind": "far", "members": [uid, rid], "admins": [], "by": uid, "t": now,
                      "updated": now, "vanish": 0, "last": {}, "unread": {}}
        _save_chat(cid, {"items": []})
        _save_index(chats)
    _log("new chat", kind="far")
    return cid


def far_tell(uid, ask=False):
    """Something new about contacts on other Sparks: open pages look again; a new request also as a notification."""
    _send_event(uid, {"type": "verbund", "id": ""})
    if ask and not listening(uid):
        async def note():
            import push
            import room
            if room.night(uid) or not push.reachable(uid, private=True):
                return
            await push.send(uid, "🌐 Kontaktanfrage", "Jemand auf einem anderen Spark möchte mit dir schreiben.",
                            tag="verbund", private=True, why="Chat", to="every")
        try:
            asyncio.get_running_loop().create_task(note())
        except RuntimeError:
            pass


def _store_media(cid, mid, media, item):
    """A photo, file or voice message (photo/a_file/voice below) into the item, its parts sealed beside the chat."""
    info = dict(media["info"])
    if info.get("name"):
        info["name"] = seal(info["name"], cid, mid + "/name")
    item["kind"], item["media"] = media["kind"], info
    os.makedirs(_media_dir(cid), mode=0o700, exist_ok=True)
    for part, data in media["parts"].items():
        tmp = _media_file(cid, mid, part) + ".tmp"
        with open(tmp, "wb") as f:
            f.write(seal_bytes(data, cid, mid, part))
        os.replace(tmp, _media_file(cid, mid, part))


def far_blob(cid, mid):
    """The bytes of an own photo, file or voice message in a chat with another Spark, for verbund.py to send; None
    when it is no longer there (taken back, chat cleared or gone)."""
    try:
        d = _chat(cid)
    except LookupError:
        return None
    x = next((x for x in d.get("items", []) if x["id"] == mid and x.get("kind") in MEDIA and not x.get("gone")), None)
    if not x:
        return None
    try:
        with open(_media_file(cid, mid, "f"), "rb") as f:
            return unseal_bytes(f.read(), cid, mid, "f")
    except OSError:
        return None


def far_in(uid, rid, mid, text, reply="", now=None, media=None):
    """A message from a contact on another Spark (verbund.py checked who and where): stored like any other, its
    own id kept (a second delivery of the same message changes nothing), then the notification as for a chat.
    media: its photo, file or voice message as this Spark made it again (verbund._media_in)."""
    now = time.time() if now is None else now
    text = clean((media or {}).get("text") or "" if media else text)
    if not text and not media or not MID.fullmatch(mid or ""):
        return False
    cid = open_far(uid, rid, now)
    item = {"id": mid, "from": rid, "t": now, "kind": "text", "text": seal(text, cid, mid), "react": {}}
    if media:
        size = sum(len(b) for b in media["parts"].values())
        if used(uid) + size > QUOTA:
            _log("far in refused", why="quota")
            return False
        if any(x["id"] == mid for x in _chat(cid).get("items", [])):
            return False
        _store_media(cid, mid, media, item)

    def put(meta, d, chats):
        if any(x["id"] == mid for x in d["items"]):
            return None
        if reply and any(x["id"] == reply for x in d["items"]):
            item["reply"] = reply
        d["items"].append(item)
        meta["updated"] = now
        un = _map(meta, "unread")
        un[uid] = int(un.get(uid) or 0) + 1
        if listening(uid):
            _map(meta, "got")[uid] = now
        return json.loads(json.dumps(meta))
    meta = _mutate(cid, put, now)
    if meta is None:
        return False
    _tell([uid], {"type": "chat", "id": cid})
    _log("far in", chars=len(text), **({"media": media["kind"]} if media else {}))
    _far_notify([uid], cid, meta, rid, text, now, (media or {}).get("kind", ""))
    return True


def _far_notify(uids, cid, meta, sender, text, now, kind=""):
    """Notification and the own speaker for a message that came from another Spark, as send() does for one here."""
    async def deliver():
        for u in uids:
            try:
                await _notify(u, cid, meta, sender, text or MEDIA_WORD.get(kind, ""), now)
                if not listening(u) and not _muted_until(meta, u, now):
                    import messages
                    if await messages.speak_now(u, _names().get(sender) or "Jemand", "" if meta.get("kind") in TWO else
                                                _title(cid, meta, u, {}), " ".join(p for p in (MEDIA_WORD.get(kind, ""), text) if p), now):
                        _today()["spoken"] = _today().get("spoken", 0) + 1
            except Exception as e:
                _log("notify failed", error=type(e).__name__)
    try:
        asyncio.get_running_loop().create_task(deliver())
    except RuntimeError:
        pass


# ---------------------------------------------------------------- groups across Sparks (verbundgruppe.py)
def spans(c):
    """A group with people on other Sparks: of this Spark (members r_…) or of another one (meta "home")."""
    return c.get("kind") == "group" and bool(c.get("home") or any(RID.fullmatch(u) for u in c["members"]))


def _locals(meta):
    return [u for u in meta["members"] if UID.fullmatch(u)]


def _far_rids(rids):
    return [r for r in dict.fromkeys(rids) if RID.fullmatch(r)][:MAX_MEMBERS]


def far_group_in(to, cid, dom, gid, name, rids, adder, now=None):
    """A group of another Spark (dom) took the profile to in: the chat for it here is made, or to joins it."""
    now = time.time() if now is None else now
    with _lock:
        chats = _index()
        c = chats.get(cid)
        if c is None:
            if sum(1 for x in chats.values() if to in x["members"] and x.get("kind") == "group") >= MAX_GROUPS \
                    or sum(1 for x in chats.values() if to in x["members"]) >= MAX_CHATS:
                _log("far group refused", why="full")
                return False
            c = chats[cid] = {"kind": "group", "members": [], "admins": [], "by": adder, "t": now, "updated": now,
                              "vanish": 0, "name": seal(name, cid, "name"), "last": {}, "unread": {}, "home": dom, "gid": gid}
            d = {"items": []}
        elif c.get("home") != dom or c.get("gid") != gid:
            return False
        else:
            d = _chat(cid, c, now)
        if to not in c["members"] and len(c["members"]) < MAX_MEMBERS + 1:
            c["members"] = _locals(c) + [to] + _far_rids(rids)
            _sys(d, adder, now, "add", [to])
        c["updated"] = now
        c["last"] = _last(cid, d["items"][-1] if d["items"] else None)
        _save_chat(cid, d)
        _save_index(chats)
    _tell([to], {"type": "chat", "id": cid})
    _log("far group in", members=len(c["members"]))
    return True


def far_group_members(to, cid, rids, now=None):
    """Who is in a group of another Spark now (its home Spark says so); the people of this Spark stay as they are."""
    def f(meta, d, chats):
        if not meta.get("home") or to not in meta["members"]:
            return []
        meta["members"] = _locals(meta) + _far_rids(rids)
        return _locals(meta)
    try:
        _tell(_mutate(cid, f, now, items=False), {"type": "chat", "id": cid})
    except LookupError:
        _log("far group dropped", why="no chat")


def far_group_name(to, cid, name, now=None):
    now = time.time() if now is None else now
    if not name:
        return

    def f(meta, d, chats):
        if not meta.get("home") or to not in meta["members"]:
            return []
        meta["name"] = seal(name, cid, "name")
        mid = _sys(d, meta.get("by", ""), now, "name")
        d["items"][-1]["text"] = seal(name, cid, mid)
        meta["updated"] = now
        return _locals(meta)
    try:
        _tell(_mutate(cid, f, now), {"type": "chat", "id": cid})
    except LookupError:
        _log("far group dropped", why="no chat")


def far_group_out(to, cid, now=None):
    """The home Spark took the profile out of its group; with nobody of this Spark left the chat goes."""
    now = time.time() if now is None else now

    def f(meta, d, chats):
        if not meta.get("home") or to not in meta["members"]:
            return None
        meta["members"].remove(to)
        for k in ("unread", "mute", "cleared", "read", "got"):
            (meta.get(k) or {}).pop(to, None)
        if not _locals(meta):
            chats.pop(cid)
            return []
        _sys(d, meta.get("by", ""), now, "remove", [to])
        meta["updated"] = now
        return _locals(meta)
    try:
        rest = _mutate(cid, f, now)
    except LookupError:
        return
    if rest is None:
        return
    if not rest:
        _drop(cid)
    _tell(rest, {"type": "chat", "id": cid})
    _send_event(to, {"type": "gone", "id": cid})


def _far_put(cid, rid, mid, text, reply, now, need=None):
    """A message of someone on another Spark into a group chat here, its id kept (a second delivery changes nothing).
    need(meta): whether it may go in. Returns the chat's meta, or None."""
    text = clean(text)
    if not text or not MID.fullmatch(mid or ""):
        return None
    item = {"id": mid, "from": rid, "t": now, "kind": "text", "text": seal(text, cid, mid), "react": {}}

    def put(meta, d, chats):
        if not need(meta) or any(x["id"] == mid for x in d["items"]):
            return None
        if reply and any(x["id"] == reply for x in d["items"]):
            item["reply"] = reply
        d["items"].append(item)
        meta["updated"] = now
        un = _map(meta, "unread")
        for u in _locals(meta):
            un[u] = int(un.get(u) or 0) + 1
            if listening(u):
                _map(meta, "got")[u] = now
        return json.loads(json.dumps(meta))
    try:
        meta = _mutate(cid, put, now)
    except LookupError:
        return None
    if meta is None:
        return None
    _tell(_locals(meta), {"type": "chat", "id": cid})
    _far_notify(_locals(meta), cid, meta, rid, text, now)
    _today()["far_group_in"] = _today().get("far_group_in", 0) + 1
    _log("far group message", chars=len(text))
    return meta


def far_group_msg(cid, rid, mid, text, reply="", now=None):
    """A message in a group of another Spark, sent on by its home Spark."""
    now = time.time() if now is None else now
    return _far_put(cid, rid, mid, text, reply, now, lambda m: bool(m.get("home") and _locals(m))) is not None


def home_group_in(gid, rid, mid, text, reply="", now=None):
    """A member on another Spark writes into a group of this Spark (verbundgruppe._at_home checked it is in)."""
    now = time.time() if now is None else now
    return _far_put(gid, rid, mid, text, reply, now, lambda m: not m.get("home") and rid in m["members"])


def far_member_left(gid, rid, now=None):
    """A member on another Spark left a group of this Spark."""
    now = time.time() if now is None else now

    def f(meta, d, chats):
        if meta.get("home") or rid not in meta["members"]:
            return None
        meta["members"].remove(rid)
        _sys(d, rid, now, "leave", [rid])
        meta["updated"] = now
        return json.loads(json.dumps(meta))
    try:
        meta = _mutate(gid, f, now)
    except LookupError:
        return
    if meta:
        _tell(_locals(meta), {"type": "chat", "id": gid})
        import verbundgruppe
        verbundgruppe.changed(gid, meta)


def far_seen(cid, mid, what):
    """The other Spark has the own message ("got": second tick) or it was given up ("fail": not delivered)."""
    def f(meta, d, chats):
        x = next((x for x in d["items"] if x["id"] == mid), None)
        if not x:
            return None
        rid = next((u for u in meta["members"] if RID.fullmatch(u)), "")
        if what == "got" and rid:
            _map(meta, "got")[rid] = max(float(_map(meta, "got").get(rid) or 0), float(x["t"]))
            x.pop("fail", None)
        elif what == "fail":
            x["fail"] = True
        return [u for u in meta["members"] if not RID.fullmatch(u)]
    try:
        members = _mutate(cid, f)
    except LookupError:
        return
    if members:
        _tell(members, {"type": "chat", "id": cid})


def far_mark(uid, rid, mid, what):
    """"Gelesen" from the other Spark: everything of uid up to the message mid of uid."""
    cid = far_id(uid, rid)

    def f(meta, d, chats):
        x = next((x for x in d["items"] if x["id"] == mid and x["from"] == uid), None)
        if not x:
            return False
        for k in ("got", what):
            _map(meta, k)[rid] = max(float(_map(meta, k).get(rid) or 0), float(x["t"]))
        return True
    try:
        if _mutate(cid, f):
            _tell([uid], {"type": "chat", "id": cid})
    except LookupError:
        pass


def far_change(uid, rid, kind, mid, value, now=None):
    """Changed ("edit"), taken back ("back") or a reaction ("react") from the other Spark, on its own messages only
    (a reaction on any message); the same time limits as here."""
    now = time.time() if now is None else now
    cid = far_id(uid, rid)

    def f(meta, d, chats):
        x = next((x for x in d["items"] if x["id"] == mid and x.get("kind") != "sys" and not x.get("gone")), None)
        if not x:
            return False
        if kind == "react":
            if value and value not in REACTIONS:
                return False
            r = x.setdefault("react", {})
            if value:
                r[rid] = value
            else:
                r.pop(rid, None)
            return True
        if x["from"] != rid:
            return False
        if kind == "edit":
            text = clean(value if isinstance(value, str) else "")
            if not text or now - x["t"] >= EDIT_SECS + 3600 or x.get("kind") != "text":
                return False
            x["text"], x["edited"] = seal(text, cid, mid), True
            return True
        if kind == "back" and now - x["t"] < BACK_SECS + 3600:
            for k in ("text", "reply", "edited", "via", "media", "box", "blob"):
                x.pop(k, None)
            x["gone"], x["react"] = True, {}
            return True
        return False
    try:
        if _mutate(cid, f, now):
            _tell([uid], {"type": "chat", "id": cid})
    except LookupError:
        pass


def joined_by_invite(uid, inviter, now=None):
    """A person who came in with inviter's chat invitation (join.py): Chats on for the new profile, both take
    each other's messages, the chat of the two open with a line "… ist dazugekommen". Returns its id or ""."""
    now = time.time() if now is None else now
    if not invite_on() or not usable(inviter) or not profiles.by_id(uid):
        return ""
    import messages
    messages.allow_each_other(inviter, uid)   # only matters with "nur ausgewählte"; never past a block
    try:
        cid = open_one(inviter, uid, now)
    except (PermissionError, LookupError, OverflowError):
        return ""

    def add(c, d, chats):
        _sys(d, uid, now, "joined")
        c["updated"] = now
    _mutate(cid, add, now)
    _tell(_index().get(cid, {}).get("members", []), {"type": "chat", "id": cid})
    _log("invite used")
    return cid


def all_sync(now=None):
    """The fixed group Alle (chat.messages_all): its members are everybody who takes part (messages.takes_all), counted
    anew at every look; made the first time. Returns its id, or "" while nobody takes part."""
    import messages
    now = time.time() if now is None else now
    cc = features.chat_cfg()   # once for all profiles
    want = [u for u in profiles.user_ids() if messages.takes_all(u, cc)] if messages.all_on() else []
    with _lock:
        chats = _index()
        c = chats.get(ALL_ID)
        if c is None:
            if not want:
                return ""
            chats[ALL_ID] = {"kind": "group", "fixed": True, "members": want, "admins": [], "by": "", "t": now,
                             "updated": now, "vanish": 0, "name": seal("Alle", ALL_ID, "name"), "last": {}, "unread": {}}
            _save_chat(ALL_ID, {"items": []})
            _save_index(chats)
            _log("new chat", kind="all")
        elif c["members"] != [u for u in c["members"] if u in want] + [u for u in want if u not in c["members"]]:
            c["members"] = [u for u in c["members"] if u in want] + [u for u in want if u not in c["members"]]
            for k in ("unread", "mute", "read", "got", "cleared"):
                for u in [u for u in (c.get(k) or {}) if u not in want]:
                    c[k].pop(u, None)
            _save_index(chats)
    return ALL_ID if want else ""


def all_group(now=None):
    """The group Alle to send into (messages.send for "Sag allen …"); LookupError while nobody takes part."""
    cid = all_sync(now)
    if not cid:
        raise LookupError("Niemand nimmt gerade Nachrichten an alle an.")
    return cid


def put_old(sender, uid, text, t, read):
    """One message of the old mailbox (messages.migrate, before V01.0.488) into the chat of sender and uid, at its own
    time and marked "via Spark". The chat is made even when one of them has chats off: it is their history."""
    if not text or not UID.fullmatch(sender or "") or not UID.fullmatch(uid or ""):
        raise ValueError("bad old message")
    cid = one_id(sender, uid)
    with _lock:
        chats = _index()
        if cid not in chats:
            chats[cid] = {"kind": "one", "members": sorted([sender, uid]), "admins": [], "by": sender, "t": t,
                          "updated": t, "vanish": 0, "last": {}, "unread": {}}
            _save_chat(cid, {"items": []})
            _save_index(chats)
    mid = secrets.token_hex(6)

    def put(meta, d, chats):
        d["items"].append({"id": mid, "from": sender, "t": t, "kind": "text", "text": seal(clean(text), cid, mid),
                           "react": {}, "via": "spark"})
        d["items"].sort(key=lambda x: float(x.get("t") or 0))
        meta["updated"] = max(float(meta.get("updated") or 0), t)
        if not read:
            un = _map(meta, "unread")
            un[uid] = int(un.get(uid) or 0) + 1
        else:
            _map(meta, "read")[uid] = max(float(_map(meta, "read").get(uid) or 0), t)
    _mutate(cid, put)
    return cid


def make_group(uid, name, members, now=None):
    """A group the profile makes: it is its admin; only people who take messages from it come in."""
    now = time.time() if now is None else now
    if not usable(uid) or not groups_on():
        raise PermissionError("Gruppen-Chats sind ausgeschaltet.")
    name = clean_name(name)
    if not name:
        raise ValueError("Der Gruppe fehlt ein Name.")
    if not isinstance(members, list) or len(members) > MAX_MEMBERS - 1:
        raise ValueError(f"Höchstens {MAX_MEMBERS} Personen in einer Gruppe.")
    members = [str(x) for x in members]
    want = [u for u in dict.fromkeys(str(x) for x in members) if UID.fullmatch(u) and u != uid]
    ok = [u for u in want if takes(u, uid)]
    far, far_out = _far_pick(uid, members, [])
    ok += far
    if not ok:
        raise PermissionError("Niemand davon nimmt gerade Nachrichten von dir an.")
    cid = "c" + secrets.token_hex(6)
    with _lock:
        chats = _index()
        for u in [uid] + [u for u in ok if UID.fullmatch(u)]:
            if sum(1 for c in chats.values() if u in c["members"] and c.get("kind") == "group") >= MAX_GROUPS:
                if u == uid:
                    raise OverflowError(f"Höchstens {MAX_GROUPS} Gruppen.")
                ok.remove(u)
        chats[cid] = {"kind": "group", "members": [uid] + ok, "admins": [uid], "by": uid, "t": now, "updated": now,
                      "vanish": 0, "name": seal(name, cid, "name"), "last": {}, "unread": {}}
        mid = secrets.token_hex(6)
        d = {"items": [{"id": mid, "from": uid, "t": now, "kind": "sys", "sys": "made", "who": ok}]}
        chats[cid]["read"] = {uid: now}
        chats[cid]["last"] = _last(cid, d["items"][-1])
        _save_chat(cid, d)
        _save_index(chats)
    _tell(ok, {"type": "chat", "id": cid})
    _log("new group", members=len(ok) + 1)
    _live(f"Neue Gruppe ({len(ok) + 1} Personen)")
    if far:
        import verbundgruppe
        verbundgruppe.added(cid, _index()[cid], uid, far)
    return cid, [name_of(u) for u in set(want) - set(ok)] + far_out


def _far_pick(uid, wanted, already):
    """People on other Sparks an admin of a group here puts in: only its accepted contacts, at most
    verbundgruppe.MAX_SPARKS other Sparks. Returns (in, names of who stays out)."""
    rids = [r for r in dict.fromkeys(str(x) for x in wanted) if RID.fullmatch(r) and r not in already]
    if not rids:
        return [], []
    import verbundgruppe
    names, ok, out = _names(), [], []
    for r in rids:
        if verbundgruppe.can_add(uid, r) and len(verbundgruppe.sparks_of(already + ok + [r])) <= verbundgruppe.MAX_SPARKS:
            ok.append(r)
        else:
            out.append(names.get(r) or "Kontakt auf einem anderen Spark")
    return ok, out


async def send(uid, cid, text, reply="", via="", now=None, media=None, box=None, blob=None):
    """A message into a chat (rechecks every rule), then delivered: events to open pages, a notification to the
    devices of everybody else who has none open. media (from photo/file/voice below): {"kind", "parts": {part:
    bytes}, "info": {...}}, stored sealed beside the chat. box/blob: a private chat's message as the device made it
    (chatsec.py), never anything else there. Returns the message as the page shows it."""
    import notaus
    if notaus.refuse("aktion", uid):
        raise PermissionError(notaus.why(uid, "keine Nachrichten"))
    now = time.time() if now is None else now
    c = _member(uid, cid)
    if c.get("kind") == "priv" or box is not None:
        import chatsec
        if c.get("kind") != "priv" or box is None or media:
            raise ValueError("Private Chats gehen nur verschlüsselt." if c.get("kind") == "priv" else "bad box")
        if not chatsec.admin_on():
            raise PermissionError("Private Chats sind auf dem Spark aus.")
        other = next((u for u in c["members"] if u != uid), "")
        if not other or not chatsec.can(other, uid):
            raise PermissionError(chatsec.why_not(other, uid) if other else "Diese Person gibt es nicht mehr.")
        box = chatsec.check_box(uid, c, box)
        if blob is not None:
            blob = chatsec.blob_check(blob)
            if not media_ok(uid):
                raise PermissionError("Fotos, Dateien und Sprachnachrichten sind für dich ausgeschaltet.")
        text = ""
    else:
        text = clean(text)
    if not text and not media and box is None:
        raise ValueError("Die Nachricht ist leer.")
    if media and not media_ok(uid):
        raise PermissionError("Fotos, Dateien und Sprachnachrichten sind für dich ausgeschaltet.")
    if not usable(uid):
        raise PermissionError("Chats sind für dich ausgeschaltet.")
    others = [u for u in c["members"] if u != uid]
    if c.get("kind") in ("one", "far"):
        if c.get("kind") == "far" and media:
            import verbund
            if not verbund.media_on() or not verbund.media_ok(uid):
                raise PermissionError("Fotos, Dateien und Sprache an andere Sparks sind ausgeschaltet.")
        if not others or not takes(others[0], uid):
            raise PermissionError(why_not(others[0], uid) if others else "Diese Person gibt es nicht mehr.")
    elif c.get("fixed"):
        import messages
        if not messages.all_on() or not messages.takes_all(uid):
            raise PermissionError("Nachrichten an alle sind ausgeschaltet.")
        why = messages.allowed_now(uid, [], "all", now)
        if why:
            raise OverflowError(why)
    elif c.get("kind") == "group" and not groups_on():
        raise PermissionError("Gruppen-Chats sind gerade ausgeschaltet.")
    if spans(c):
        import verbundgruppe
        if not verbundgruppe.admin_on() or not verbundgruppe.usable(uid):
            raise PermissionError("Gruppen mit anderen Sparks sind gerade ausgeschaltet.")
        if media:
            raise PermissionError("In Gruppen mit anderen Sparks gehen bisher nur Textnachrichten.")
    if not _rate(uid, now):
        raise OverflowError(f"Du hast in der letzten Stunde schon {PER_HOUR} Nachrichten geschickt.")
    if c.get("fixed"):
        import messages
        messages._count(uid, [], "all", now)
    mid = secrets.token_hex(6)
    item = {"id": mid, "from": uid, "t": now, "kind": "text", "text": seal(text, cid, mid), "react": {}}
    size = 0
    if box is not None:
        item = {"id": mid, "from": uid, "t": now, "kind": "box", "box": box, "react": {}}
        if blob is not None:
            size = len(blob)
            if used(uid) + size > QUOTA:
                raise OverflowError(f"Dein Platz für Fotos, Dateien und Sprache ist voll ({QUOTA // 1024**3} GB). "
                                    "Alte Chats leeren oder Nachrichten zurücknehmen schafft Platz.")
            item["blob"] = {"bytes": size}
            os.makedirs(_media_dir(cid), mode=0o700, exist_ok=True)
            tmp = _media_file(cid, mid, "f") + ".tmp"
            with open(tmp, "wb") as f:
                f.write(seal_bytes(blob, cid, mid, "f"))
            os.replace(tmp, _media_file(cid, mid, "f"))
    if media:
        size = sum(len(b) for b in media["parts"].values())
        if used(uid) + size > QUOTA:
            raise OverflowError(f"Dein Platz für Fotos, Dateien und Sprache ist voll ({QUOTA // 1024**3} GB). "
                                "Alte Chats leeren oder Nachrichten zurücknehmen schafft Platz.")
        _store_media(cid, mid, media, item)
    if reply and MID.fullmatch(reply):
        item["reply"] = reply
    if via in ("spark",):
        item["via"] = via

    def put(meta, d, chats):
        if reply and not any(x["id"] == reply for x in d["items"]):
            item.pop("reply", None)
        d["items"].append(item)
        _map(meta, "read")[uid] = now
        meta["updated"] = now
        un = _map(meta, "unread")
        for u in meta["members"]:
            if u != uid:
                un[u] = int(un.get(u) or 0) + 1
                if listening(u):
                    _map(meta, "got")[u] = now
        un[uid] = 0
        return json.loads(json.dumps(meta))
    try:
        meta = _mutate(cid, put, now)
    except Exception:
        _sweep(cid, _chat(cid).get("items", []))   # the sealed parts written above go again
        raise
    _today()["sent"] += 1
    if media or blob is not None:
        _today()["media"] = _today().get("media", 0) + 1
    if box is not None:
        _today()["private"] = _today().get("private", 0) + 1
    _tell(meta["members"], {"type": "chat", "id": cid})
    if meta.get("kind") == "far":      # to the other Spark (verbund.py): the queue sends it, the second tick comes from there
        try:
            import verbund
            far_media = None
            if media:   # the file goes first (verbund.py), the other Spark makes it again; voice: it writes it down itself
                far_media = {"kind": media["kind"], "sha": hashlib.sha256(media["parts"]["f"]).hexdigest(),
                             "size": len(media["parts"]["f"]), "name": media["info"].get("name") or None}
            verbund.out_event(uid, others[0], "msg", cid, mid, id=mid, text="" if media else text,
                              reply=item.get("reply", ""), media=far_media)
        except Exception as e:
            far_seen(cid, mid, "fail")
            _log("far failed", error=type(e).__name__)
    if spans(meta):     # to the members on other Sparks (verbundgruppe.py): from here, or through the group's home
        try:
            import verbundgruppe
            if meta.get("home"):
                verbundgruppe.member_out(uid, meta, mid, text, item.get("reply", ""))
            else:
                verbundgruppe.out(cid, meta, uid, mid, text, item.get("reply", ""))
        except Exception as e:
            _log("far failed", error=type(e).__name__)
    _log("sent", kind=meta.get("kind", "one"), chars=len(text), **({"media": media["kind"], "kb": size // 1024} if media else
                                                                   {"kb": size // 1024} if blob is not None else {}))
    for u in others:
        if RID.fullmatch(u):
            continue
        try:
            await _notify(u, cid, meta, uid, "🔒 Neue Nachricht" if box is not None else
                          text or MEDIA_WORD.get(media["kind"] if media else "", ""), now)
        except Exception as e:
            _log("notify failed", error=type(e).__name__)
        try:   # the own speaker reads it (msg_speaker) when no page of u is open; a private chat only who wrote
            if not listening(u) and not _muted_until(meta, u, now):
                import messages
                if await messages.speak_now(u, name_of(uid), "" if meta.get("kind") in TWO else
                                            _title(cid, meta, u, {}), "" if box is not None else
                                            " ".join(p for p in (MEDIA_WORD.get(media["kind"], "") if media else "", text) if p), now):
                    _today()["spoken"] = _today().get("spoken", 0) + 1
        except Exception as e:
            _log("speaker failed", error=type(e).__name__)
    names = _names()
    d = _chat(cid, meta, now)
    return _public(next(x for x in d["items"] if x["id"] == mid), cid, meta, d, uid, names)


async def _notify(u, cid, meta, sender, text, now):
    """One notification to every device of u (iPhone, Android, Begleiter, each browser with push), unless a page
    of u is open, the chat is muted, chats are off for u or it is u's quiet time. Only who and "Neue Nachricht",
    the text only when u wants it (chat_push_text); the apps fetch the rest from the Spark."""
    if not usable(u) or listening(u) or _muted_until(meta, u, now):
        return 0
    import room
    if room.night(u):
        return 0
    import push
    if not push.reachable(u, private=True):
        return 0
    who = name_of(sender) or "Jemand"
    title = "💬 " + (who if meta.get("kind") in TWO else _title(cid, meta, u, {}) + " · " + who)
    body = ("🔒 Neue Nachricht" if meta.get("kind") == "priv" else
            text[:200] if profiles.settings(u).get("chat_push_text") is True else "Neue Nachricht")
    n = await push.send(u, title, body, tag="chat-" + cid, private=True, why="Chat", to="every")
    _today()["pushed" if n else "push_failed"] += 1
    if n:
        def got(m, d, chats):
            _map(m, "got")[u] = max(float(_map(m, "got").get(u) or 0), now)
        _mutate(cid, got, now, items=False)
    return n


def read(uid, cid, now=None):
    """Everything up to now counts as read for uid (the chat is open on its screen)."""
    now = time.time() if now is None else now
    _member(uid, cid)

    def f(meta, d, chats):
        _map(meta, "read")[uid] = now
        _map(meta, "got")[uid] = now
        _map(meta, "unread")[uid] = 0
        return [u for u in meta["members"] if u != uid]
    others = _mutate(cid, f, now, items=False)
    if profiles.settings(uid).get("chat_receipts", True) is not False:
        _tell(others, {"type": "chat", "id": cid, "read": True})
        if others and RID.fullmatch(others[0]):
            _far_read(uid, cid, others[0], now)


def _far_read(uid, cid, rid, now):
    """"Gelesen" to the other Spark: the newest message of the other one that uid has seen, once."""
    c = _index().get(cid) or {}
    newest = next((x for x in reversed(_chat(cid, c, now)["items"]) if x["from"] == rid and x.get("kind") == "text"), None)
    if not newest or (c.get("rsent") or {}).get(uid) == newest["id"]:
        return
    import verbund
    if verbund.out_event(uid, rid, "read", id=newest["id"]):
        _mutate(cid, lambda m, d, ch: _map(m, "rsent").__setitem__(uid, newest["id"]), now, items=False)


def _own(d, uid, mid):
    x = next((x for x in d["items"] if x["id"] == mid), None)
    if not x or x["from"] != uid or x.get("kind") == "sys" or x.get("gone"):
        raise LookupError("no such message")
    return x


def edit(uid, cid, mid, text, now=None):
    now = time.time() if now is None else now
    text = clean(text)
    if not text:
        raise ValueError("Die Nachricht ist leer.")
    c = _member(uid, cid)
    if spans(c):
        raise PermissionError("In Gruppen mit anderen Sparks geht das noch nicht.")

    def f(meta, d, chats):
        x = _own(d, uid, mid)
        if now - x["t"] >= EDIT_SECS or x.get("kind") != "text":
            raise PermissionError("Ändern geht nur in den ersten 15 Minuten.")
        x["text"], x["edited"] = seal(text, cid, mid), True
        return meta["members"]
    _tell(_mutate(cid, f, now), {"type": "chat", "id": cid})
    _far_out(uid, c, "edit", id=mid, text=text)
    _log("edited")


def take_back(uid, cid, mid, now=None):
    """The own message gone for everybody (only its place stays: "Nachricht zurückgezogen")."""
    now = time.time() if now is None else now
    c = _member(uid, cid)
    if spans(c):
        raise PermissionError("In Gruppen mit anderen Sparks geht das noch nicht.")

    def f(meta, d, chats):
        x = _own(d, uid, mid)
        if now - x["t"] >= BACK_SECS:
            raise PermissionError("Zurückziehen geht nur in der ersten Stunde.")
        for k in ("text", "reply", "edited", "via", "media", "box", "blob"):
            x.pop(k, None)
        x["gone"], x["react"] = True, {}
        return meta["members"]
    _tell(_mutate(cid, f, now), {"type": "chat", "id": cid})
    _far_out(uid, c, "back", id=mid)
    _log("taken back")


def react(uid, cid, mid, emoji, now=None):
    if emoji and emoji not in REACTIONS:
        raise ValueError("unknown reaction")
    c = _member(uid, cid)

    def f(meta, d, chats):
        x = next((x for x in d["items"] if x["id"] == mid and x.get("kind") != "sys" and not x.get("gone")), None)
        if not x:
            raise LookupError("no such message")
        r = x.setdefault("react", {})
        if emoji and r.get(uid) != emoji:
            r[uid] = emoji
        else:
            r.pop(uid, None)
        return meta["members"], r.get(uid, "")
    members, mine_now = _mutate(cid, f, now)
    _tell(members, {"type": "chat", "id": cid})
    _far_out(uid, c, "react", id=mid, emoji=mine_now)


def _far_out(uid, c, kind, **fields):
    """A change in a chat with someone on another Spark goes there too (verbund.py queue)."""
    if c.get("kind") != "far":
        return
    rid = next((u for u in c["members"] if u != uid), "")
    if RID.fullmatch(rid):
        import verbund
        verbund.out_event(uid, rid, kind, **fields)


def typing(uid, cid):
    c = _member(uid, cid)
    _tell(c["members"], {"type": "typing", "id": cid, "name": name_of(uid), "secs": TYPING_SECS}, but=uid)


def _sys(d, uid, now, what, who=(), **extra):
    mid = secrets.token_hex(6)
    d["items"].append(dict({"id": mid, "from": uid, "t": now, "kind": "sys", "sys": what, "who": list(who)}, **extra))
    return mid


def options(uid, cid, body, now=None):
    """Stumm (each for itself), selbst löschen (in a group only its admins) and the group's name (its admins)."""
    now = time.time() if now is None else now
    c = _member(uid, cid)
    admin = c.get("kind") in TWO or uid in (c.get("admins") or [])

    def f(meta, d, chats):
        if "mute" in body:
            m = body["mute"]
            if m not in MUTE:
                raise ValueError("unknown mute")
            mu = meta.setdefault("mute", {})
            if m:
                mu[uid] = -1 if m == -1 else now + m
            else:
                mu.pop(uid, None)
        if "vanish" in body:
            v = body["vanish"]
            if v not in VANISH:
                raise ValueError("unknown vanish")
            if not admin:
                raise PermissionError("Nur die Admins der Gruppe ändern das.")
            if int(meta.get("vanish") or 0) != v:
                meta["vanish"] = v
                _sys(d, uid, now, "vanish", secs=v)
        if "name" in body and meta.get("kind") == "group":
            if not admin:
                raise PermissionError("Nur die Admins der Gruppe ändern das.")
            name = clean_name(body["name"])
            if not name:
                raise ValueError("Der Gruppe fehlt ein Name.")
            meta["name"] = seal(name, cid, "name")
            mid = _sys(d, uid, now, "name")
            d["items"][-1]["text"] = seal(name, cid, mid)
        meta["updated"] = max(float(meta.get("updated") or 0), now) if ("vanish" in body or "name" in body) else meta.get("updated")
        return json.loads(json.dumps(meta))
    meta = _mutate(cid, f, now)
    _tell(meta["members"], {"type": "chat", "id": cid})
    if "name" in body and spans(meta) and not meta.get("home"):
        import verbundgruppe
        verbundgruppe.named(cid, meta, clean_name(body["name"]))


def members(uid, cid, add=(), remove=(), admin=(), now=None):
    """A group's admins add people (only who takes messages from them), take people out and make admins."""
    now = time.time() if now is None else now
    c = _member(uid, cid)
    if c.get("kind") != "group" or c.get("fixed"):
        raise ValueError("only groups have members to change" if not c.get("fixed") else
                         "In „Alle“ ist jeder, der Nachrichten an alle annimmt.")
    if c.get("home"):
        raise PermissionError("Diese Gruppe gehört zu einem anderen Spark und wird dort verwaltet.")
    if uid not in (c.get("admins") or []):
        raise PermissionError("Nur die Admins der Gruppe ändern das.")
    if not groups_on():
        raise PermissionError("Gruppen-Chats sind gerade ausgeschaltet.")
    far, left_out = _far_pick(uid, add, list(c["members"]))
    add = [u for u in dict.fromkeys(str(x) for x in add) if UID.fullmatch(u)]
    far_new, far_gone = [], []

    def f(meta, d, chats):
        new = []
        for u in add:
            if u in meta["members"]:
                continue
            groups = sum(1 for x in chats.values() if u in x["members"] and x.get("kind") == "group")
            if not takes(u, uid) or groups >= MAX_GROUPS or len(meta["members"]) >= MAX_MEMBERS:
                left_out.append(name_of(u))
                continue
            meta["members"].append(u)
            new.append(u)
        for r in far:
            if r not in meta["members"] and len(meta["members"]) < MAX_MEMBERS:
                meta["members"].append(r)
                new.append(r)
                far_new.append(r)
        if new:
            _sys(d, uid, now, "add", new)
        gone = [u for u in dict.fromkeys(str(x) for x in remove) if u in meta["members"] and u != uid]
        far_gone.extend(u for u in gone if RID.fullmatch(u))
        for u in gone:
            meta["members"].remove(u)
            meta["admins"] = [a for a in meta.get("admins") or [] if a != u]
            (meta.get("unread") or {}).pop(u, None)
        if gone:
            _sys(d, uid, now, "remove", gone)
        made = [u for u in dict.fromkeys(str(x) for x in admin) if u in meta["members"] and u not in meta["admins"]
                and UID.fullmatch(u)]
        if made:
            meta["admins"].extend(made)
            _sys(d, uid, now, "admin", made)
        meta["updated"] = now
        return meta["members"] + gone
    told = _mutate(cid, f, now)
    _tell([u for u in told if UID.fullmatch(u)], {"type": "chat", "id": cid})
    meta = _index().get(cid, {"members": []})
    _log("members changed", members=len(meta["members"]))
    if far_new or far_gone or (spans(meta) and (add or remove)):
        import verbundgruppe
        if far_gone:
            verbundgruppe.removed(cid, far_gone)
        if far_new:
            verbundgruppe.added(cid, meta, uid, far_new)
        verbundgruppe.changed(cid, meta, but=far_new)
    return left_out


def leave(uid, cid, now=None):
    """Out of a group. The last admin leaving makes the longest member admin; the last one leaving ends the group."""
    now = time.time() if now is None else now
    c = _member(uid, cid)
    if c.get("kind") != "group":
        raise ValueError("only groups can be left")
    if c.get("fixed"):   # Alle: leaving is the own switch „Nachrichten an alle“ going off
        profiles.save_settings(uid, {"msg_all": False})
        all_sync(now)
        _send_event(uid, {"type": "gone", "id": cid})
        _log("left group", kind="all")
        return

    far = spans(c)
    if far and c.get("home"):
        import verbundgruppe
        verbundgruppe.member_left(uid, c)

    def f(meta, d, chats):
        meta["members"].remove(uid)
        meta["admins"] = [a for a in meta.get("admins") or [] if a != uid]
        (meta.get("unread") or {}).pop(uid, None)
        if not _locals(meta):     # nobody of this Spark left: the group ends here (and for the other Sparks)
            chats.pop(cid)
            return [], [u for u in meta["members"] if RID.fullmatch(u)] if not meta.get("home") else [], meta
        if not meta["admins"] and not meta.get("home"):
            meta["admins"] = [_locals(meta)[0]]
        _sys(d, uid, now, "leave", [uid])
        meta["updated"] = now
        return _locals(meta), [], json.loads(json.dumps(meta))
    rest, ended, meta = _mutate(cid, f, now)
    if not rest:
        _drop(cid)
    _tell(rest, {"type": "chat", "id": cid})
    _send_event(uid, {"type": "gone", "id": cid})
    if far and not c.get("home"):
        import verbundgruppe
        if ended:
            verbundgruppe.removed(cid, ended)
        elif rest:
            verbundgruppe.changed(cid, meta)
    _log("left group")


def clear(uid, cid, now=None):
    """Deletes the chat for uid only: its messages up to now are gone from uid's list and view."""
    now = time.time() if now is None else now
    _member(uid, cid)

    def f(meta, d, chats):
        _map(meta, "cleared")[uid] = now
        _map(meta, "unread")[uid] = 0
    _mutate(cid, f, now, items=False)
    _send_event(uid, {"type": "gone", "id": cid})
    _log("cleared for one member")


def _drop(cid):
    try:
        os.remove(_chat_file(cid))
    except OSError:
        pass
    import shutil
    shutil.rmtree(_media_dir(cid), ignore_errors=True)


def forget(uid):
    """A deleted profile: out of every group, its messages gone everywhere (their place stays), chats with only it
    left removed. Called by admin.py when a profile is deleted."""
    now = time.time()
    ended, left, moved = [], [], []
    with _lock:
        chats = _index()
        for cid, c in list(chats.items()):
            if uid not in c["members"]:
                continue
            if c.get("home"):
                left.append(json.loads(json.dumps(c)))
            elif spans(c):
                moved.append(cid)
            d = _chat(cid, c, now)
            for x in d["items"]:
                if x["from"] == uid and x.get("kind") != "sys":
                    for k in ("text", "reply", "edited", "via", "media", "box", "blob"):
                        x.pop(k, None)
                    x["gone"], x["react"] = True, {}
                (x.get("react") or {}).pop(uid, None)
            c["members"].remove(uid)
            c["admins"] = [a for a in c.get("admins") or [] if a != uid]
            if c.get("kind") == "group" and _locals(c) and not c["admins"] and not c.get("home"):
                c["admins"] = [_locals(c)[0]]
            for k in ("unread", "mute", "cleared", "read", "got", "bytes"):
                (c.get(k) or {}).pop(uid, None)
            if not [u for u in c["members"] if not RID.fullmatch(u)]:   # nobody of this Spark left in it
                if spans(c) and not c.get("home"):
                    ended.append((cid, [u for u in c["members"] if RID.fullmatch(u)]))
                chats.pop(cid)
                _drop(cid)
                continue
            c["last"] = _last(cid, d["items"][-1] if d["items"] else None)
            _save_chat(cid, d)
        _save_index(chats)
    if ended or left or moved:     # the groups across Sparks hear it (verbundgruppe.py)
        import verbundgruppe
        for c in left:
            verbundgruppe.member_left(uid, c)
        for cid, rids in ended:
            verbundgruppe.removed(cid, rids)
        idx = _index()
        for cid in moved:
            if cid in idx:
                verbundgruppe.changed(cid, idx[cid])


def find(uid, q, now=None):
    """Search in the own chats (on the Spark): at most FIND_MAX hits, newest first."""
    q = clean(q, 80).lower()
    if len(q) < 2:
        return []
    names = _names()
    hits = []
    for cid, c in mine(uid).items():
        d = _chat(cid, c, now)
        cleared = float(_map(c, "cleared").get(uid) or 0)
        for x in reversed(d["items"]):
            if x["t"] <= cleared or x.get("kind") in ("sys", "box") or x.get("gone"):
                continue
            text = unseal(x.get("text"), cid, x["id"])
            if q in text.lower():
                hits.append({"id": cid, "mid": x["id"], "t": x["t"], "title": _title(cid, c, uid, names),
                             "name": names.get(x["from"], ""), "text": text[:160]})
    hits.sort(key=lambda x: -x["t"])
    return hits[:FIND_MAX]


def unread_total(uid):
    return sum(int((c.get("unread") or {}).get(uid) or 0) for c in mine(uid).values())


def for_live(now=None):
    """Zustand → Live: numbers only (never a text, a name or a group's name)."""
    if not admin_on():
        return {"on": False}
    chats = _index()
    c = _today()
    return {"on": True, "chats": sum(1 for x in chats.values() if x.get("kind") == "one"),
            "groups": sum(1 for x in chats.values() if x.get("kind") == "group"), "sent": c["sent"],
            "pushed": c["pushed"], "push_failed": c["push_failed"], "streams": streams(), "media_on": media_on(),
            "private": sum(1 for x in chats.values() if x.get("kind") == "priv"), "private_sent": c.get("private", 0),
            "all": len((chats.get(ALL_ID) or {}).get("members") or []), "spoken": c.get("spoken", 0),
            **_private_live(), **_far_live(), **_call_live(),
            "media": c.get("media", 0), "media_mb": round(sum(sum(int(v or 0) for v in (x.get("bytes") or {}).values())
                                                               for x in chats.values()) / 1024**2)}


def _far_live():
    try:
        import verbund
        v = verbund.for_live()
    except Exception:
        v = {}
    return {"far_on": bool(v.get("on")), "far_sparks": int(v.get("sparks") or 0), "far_contacts": int(v.get("contacts") or 0),
            "far_in": int(v.get("in") or 0), "far_out": int(v.get("out") or 0), "far_waiting": int(v.get("waiting") or 0),
            "far_media": bool(v.get("media")), "far_files_in": int(v.get("files_in") or 0), "far_files_out": int(v.get("files_out") or 0),
            **_far_group_live()}


def _far_group_live():
    try:
        import verbundgruppe
        g = verbundgruppe.for_live()
    except Exception:
        g = {}
    return {"far_groups": bool(g.get("on")), "far_groups_home": int(g.get("home") or 0),
            "far_groups_there": int(g.get("there") or 0), "far_group_in": int(_today().get("far_group_in") or 0)}


def _call_live():
    try:
        import anrufe
        a = anrufe.for_live()
    except Exception:
        a = {}
    return {"call_on": bool(a.get("on")), **{"call_" + k: a[k] for k in ("talking", "ringing", "today", "talked", "missed",
                                                                         "minutes", "turn", "turn_ok", "turn_why") if k in a}}


def _private_live():
    try:
        import chatsec
        p = chatsec.for_live()
    except Exception:
        p = {}
    return {"private_on": bool(p.get("on")), "devices": int(p.get("devices") or 0),
            "history_waiting": int(p.get("waiting") or 0)}


# ---------------------------------------------------------------- photos, files, voice messages (Schritt B)
def used(uid):
    """Bytes of photos, files and voice the profile keeps in all its chats (the 2 GB of QUOTA)."""
    return sum(int((c.get("bytes") or {}).get(uid) or 0) for c in mine(uid).values())


def _bytes_of(items):
    """uid -> bytes of the photos, files and voice it keeps in this chat (counted anew at every save)."""
    out = {}
    for x in items:
        if x.get("kind") in MEDIA and not x.get("gone"):
            out[x["from"]] = out.get(x["from"], 0) + int((x.get("media") or {}).get("bytes") or 0)
        elif x.get("blob") and not x.get("gone"):
            out[x["from"]] = out.get(x["from"], 0) + int(x["blob"].get("bytes") or 0)
    return out


_tidied = [0.0]


def tidy(now=None, every=600):
    """What "selbst löschen" already took leaves the disk too (photos, files, voice) and frees its space; at most
    every ten minutes, from the list call. Returns how many chats were tidied."""
    now = time.time() if now is None else now
    if now - _tidied[0] < every:
        return 0
    _tidied[0] = now
    n = 0
    for cid, c in list(_index().items()):
        keep = int(c.get("vanish") or 0)
        if not keep:
            continue
        raw = _read(_chat_file(cid)).get("items") or []
        if any(isinstance(x, dict) and now - float(x.get("t") or 0) >= keep for x in raw):
            try:
                _mutate(cid, lambda m, d, ch: None, now)
                n += 1
            except LookupError:
                pass
    if n:
        _log("tidied", chats=n)
    return n


def _file_name(name, ext):
    """A file's name as shown (never a path), always with the extension of what it really is."""
    base = os.path.basename(str(name or "").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]+", " ", base).strip(" .")
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base).strip() or "Datei"
    return stem[:MAX_FILE_NAME - len(ext) - 1] + "." + ext


OFFICE = {"word/": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
          "xl/": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
          "ppt/": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
ODF = {"application/vnd.oasis.opendocument.text": "odt", "application/vnd.oasis.opendocument.spreadsheet": "ods",
       "application/vnd.oasis.opendocument.presentation": "odp"}


def file_kind(data, name=""):
    """(ext, mime) of a file by its content, never by its name; ValueError for anything else. Allowed: PDF, Word,
    Excel, PowerPoint, OpenDocument, plain text (txt, csv, md)."""
    if data[:5] == b"%PDF-":
        return "pdf", "application/pdf"
    if data[:4] == b"PK\x03\x04":
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if len(names) > 5000:
                    raise ValueError("Diese Datei ist kein Dokument, das Chats annehmen.")
                if "mimetype" in names:
                    with z.open("mimetype") as f:   # only the first bytes: never unpack a whole entry (zip bomb)
                        mt = f.read(100).decode("ascii", "replace").strip()
                    if mt in ODF:
                        return ODF[mt], mt
                if "[Content_Types].xml" in names:
                    for prefix, (ext, mime) in OFFICE.items():
                        if any(n.startswith(prefix) for n in names):
                            return ext, mime
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
            pass
        raise ValueError("Diese Datei ist kein Dokument, das Chats annehmen (PDF, Office, OpenDocument, Text).")
    if b"\x00" not in data[:65536]:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Diese Datei ist kein Dokument, das Chats annehmen (PDF, Office, OpenDocument, Text).")
        ext = (re.search(r"\.([A-Za-z0-9]{1,4})$", name or "") or [None, "txt"])[1].lower()
        return (ext if ext in ("txt", "csv", "md") else "txt"), "text/plain; charset=utf-8"
    raise ValueError("Diese Datei ist kein Dokument, das Chats annehmen (PDF, Office, OpenDocument, Text).")


async def photo(data):
    """A photo as it is kept: decoded and saved again by Pillow (no EXIF, no place), at most 2048 px, plus a
    480 px preview. Anything that is not a JPEG, PNG or WebP picture is refused."""
    import images
    if not data or len(data) > MAX_PHOTO_IN:
        raise ValueError("Das Foto ist zu groß.")
    try:
        full, w, h = await asyncio.to_thread(images.prepare, data, PHOTO_SIDE, 85)
        thumb, _, _ = await asyncio.to_thread(images.prepare, full, THUMB_SIDE, 75)
    except ValueError:
        raise ValueError("Das ist kein Foto, das sich lesen lässt (JPEG, PNG oder WebP).")
    return {"kind": "photo", "parts": {"f": full, "t": thumb},
            "info": {"mime": "image/jpeg", "w": w, "h": h, "size": len(full), "bytes": len(full) + len(thumb)}}


def a_file(data, name):
    if not data:
        raise ValueError("Die Datei ist leer.")
    if len(data) > MAX_FILE:
        raise ValueError(f"Die Datei ist zu groß (höchstens {MAX_FILE // 1024**2} MB).")
    import images
    if images.kind(data):
        raise ValueError("Bilder bitte als Foto schicken.")
    ext, mime = file_kind(data, name)
    return {"kind": "file", "parts": {"f": data},
            "info": {"mime": mime, "ext": ext, "size": len(data), "bytes": len(data), "name": _file_name(name, ext)}}


def _ffmpeg(data, args, secs, timeout=60):
    """ffmpeg on a recording; secs cuts it (a small compressed file must not unpack to hours of sound)."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in"), os.path.join(d, "out")
        with open(src, "wb") as f:
            f.write(data)
        p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-protocol_whitelist", "file,pipe", "-y", "-i", src,
                            "-t", str(secs)] + args + [dst], capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise ValueError("this recording cannot be read")
        with open(dst, "rb") as f:
            return f.read()


async def _transcribe(pcm):
    import esp32
    return clean(await esp32.transcribe(pcm), 2000).replace("\n", " ")


async def voice(data):
    """A recorded voice message (browser, app): at most 5 minutes, kept as AAC; the speech recognition on the
    Spark writes what was said underneath (sealed like a text). Kept as AAC: it plays everywhere, also on iPhones."""
    if not data or len(data) > MAX_VOICE_IN:
        raise ValueError("Die Aufnahme ist zu groß.")
    try:
        pcm = await asyncio.to_thread(_ffmpeg, data, ["-ac", "1", "-ar", "16000", "-f", "s16le"], MAX_VOICE_SECS, 180)
        aac = await asyncio.to_thread(_ffmpeg, data, ["-ac", "1", "-ar", "24000", "-c:a", "aac", "-b:a", "32k", "-f", "adts"],
                                      MAX_VOICE_SECS, 180)
    except Exception:
        raise ValueError("Die Aufnahme lässt sich nicht lesen.")
    secs = len(pcm) / 32000
    if secs < 0.5:
        raise ValueError("Die Aufnahme ist zu kurz.")
    text = ""
    try:
        text = await _transcribe(pcm[:MAX_VOICE_SECS * 32000])
    except Exception as e:
        _log("voice text failed", error=type(e).__name__)
    return {"kind": "voice", "parts": {"f": aac}, "text": text,
            "info": {"mime": "audio/aac", "secs": round(secs), "size": len(aac), "bytes": len(aac)}}


def media(uid, cid, mid, part="f"):
    """(bytes, mime, name) of a photo, file or voice message for a member of its chat; LookupError otherwise."""
    c = _member(uid, cid)
    d = _chat(cid, c)
    cleared = float(_map(c, "cleared").get(uid) or 0)
    x = next((x for x in d["items"] if x["id"] == mid and (x.get("kind") in MEDIA or x.get("blob")) and not x.get("gone")
              and x["t"] > cleared), None)
    if not x or (part == "t" and x["kind"] != "photo"):
        raise LookupError("no such message")
    if x.get("kind") == "box":   # a private chat's photo, file or voice: as the device encrypted it
        try:
            with open(_media_file(cid, mid, "f"), "rb") as f:
                data = unseal_bytes(f.read(), cid, mid, "f")
        except OSError:
            data = None
        if data is None:
            raise LookupError("no such message")
        return data, "application/octet-stream", ""
    try:
        with open(_media_file(cid, mid, part), "rb") as f:
            data = unseal_bytes(f.read(), cid, mid, part)
    except OSError:
        data = None
    if data is None:
        raise LookupError("no such message")
    m = x.get("media") or {}
    return data, ("image/jpeg" if x["kind"] == "photo" else m.get("mime") or "application/octet-stream"), \
        unseal(m.get("name"), cid, mid + "/name")


# ---------------------------------------------------------------- the assistant ("Was hat Anna geschrieben?")
def _line(x, cid, c, names, where):
    if x.get("kind") == "box":   # the Spark cannot read it, so it says only that it is there
        return f"Chat von {names.get(x['from'], '?')}{where}: [🔒 private Nachricht, nur auf deinen Geräten lesbar]"
    word = MEDIA_WORD.get(x.get("kind"), "")
    return f"Chat von {names.get(x['from'], '?')}{where}: " + " ".join(
        p for p in (f"[{word}]" if word else "", unseal(x.get("text"), cid, x["id"])) if p)


def for_model(uid, now=None, most=10, old=False):
    """Unread chat messages as (t, sender, line, new) for message_read (outside text, see messages.tool), marked read.
    old: nothing unread, so the last ones already read (not marked again)."""
    now = time.time() if now is None else now
    if not usable(uid):
        return []
    names = _names()
    lines, seen = [], []
    for cid, c in mine(uid).items():
        if c.get("kind") == "far":   # from another Spark: never to the language model (plan spark-verbund.md)
            continue
        d = None
        where = "" if c.get("kind") in TWO else f" in der Gruppe {_title(cid, c, uid, names)}"
        cleared = float(_map(c, "cleared").get(uid) or 0)
        if int((c.get("unread") or {}).get(uid) or 0):
            d = _chat(cid, c, now)
            since = max(float(_map(c, "read").get(uid) or 0), cleared)
            new = [x for x in d["items"] if x["t"] > since and x["from"] != uid
                   and x.get("kind") in ("text", "box") + MEDIA and not x.get("gone")]
            lines += [(x["t"], x["from"], _line(x, cid, c, names, where), True) for x in new[-most:]]
            read(uid, cid, now)
        elif old:
            d = _chat(cid, c, now)
            seen += [(x["t"], x["from"], _line(x, cid, c, names, where), False) for x in d["items"]
                     if x["t"] > cleared and x["from"] != uid and x.get("kind") in ("text", "box") + MEDIA
                     and not x.get("gone")][-most:]
    lines.sort()
    if not lines and old:
        seen.sort()
        return seen[-most:]
    return lines[-most:]


def waiting(uid, since, now=None):
    """[(who, where, text)] of the unread chat messages from others after since, oldest first, for the own speaker
    (messages.speaker_waiting): muted chats left out, a private chat's text never (the Spark cannot read it)."""
    now = time.time() if now is None else now
    if not usable(uid):
        return []
    names = _names()
    out = []
    for cid, c in mine(uid).items():
        if not int((c.get("unread") or {}).get(uid) or 0) or _muted_until(c, uid, now):
            continue
        after = max(since, float(_map(c, "read").get(uid) or 0), float(_map(c, "cleared").get(uid) or 0))
        where = "" if c.get("kind") in TWO else _title(cid, c, uid, names)
        for x in _chat(cid, c, now)["items"]:
            if x["t"] <= after or x["from"] == uid or x.get("gone") or x.get("kind") not in ("text", "box") + MEDIA:
                continue
            text = "" if x.get("kind") == "box" else " ".join(p for p in (MEDIA_WORD.get(x.get("kind"), ""),
                                                                       unseal(x.get("text"), cid, x["id"])) if p)
            out.append((x["t"], names.get(x["from"], ""), where, text))
    out.sort()
    return [x[1:] for x in out]


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402
from fastapi.responses import Response, StreamingResponse  # noqa: E402

from core import assistant, json_body, own_profile  # noqa: E402

router = APIRouter()


def _on(request: Request, prof=Depends(own_profile)):
    """The profile's own browser login or its iPhone app; admin switch and own switch; a limit per minute."""
    import guard
    if request.headers.get(profiles.DEVICE_HEADER) and profiles.key_scope(request) != "app":
        raise HTTPException(403, "only in the profile's own browser login or the iPhone app")
    if not admin_on():
        raise HTTPException(403, "chats are turned off")
    if not usable(prof["id"]):
        raise HTTPException(403, ("Chats gehen für dich gerade nicht. " + features.missing_text("chats", prof["id"])).strip())
    guard.limit(request, "chats", prof["id"])
    return prof


def _seen(request: Request, prof=Depends(own_profile)):
    """Like _on for showing photos and playing voice: a page with many photos asks for each one (own limit)."""
    import guard
    if request.headers.get(profiles.DEVICE_HEADER) and profiles.key_scope(request) != "app":
        raise HTTPException(403, "only in the profile's own browser login or the iPhone app")
    if not admin_on() or not usable(prof["id"]):
        raise HTTPException(403, "chats are turned off")
    guard.limit(request, "chatsget", prof["id"])
    return prof


def _cid(v):
    v = str(v or "")
    if not CID.fullmatch(v):
        raise HTTPException(400, "chat id is required")
    return v


def _mid(v):
    v = str(v or "")
    if not MID.fullmatch(v):
        raise HTTPException(400, "message id is required")
    return v


def _err(e):
    """A refusal as a sentence the page shows (fixed sentences from above, never an exception text from outside),
    with its journal line: the kind of refusal only, never the sentence (it can name people)."""
    kind = {LookupError: ("not found", 404), OverflowError: ("limit", 429), PermissionError: ("not allowed", 403)}
    word, code = next((v for k, v in kind.items() if isinstance(e, k)), ("invalid", 400))
    _log("refused", why=word, http=code)
    return HTTPException(code, "Diesen Chat oder diese Nachricht gibt es nicht." if code == 404 else str(e))


def _state(uid):
    s = profiles.settings(uid)
    import messages
    return {"speakers": [{"id": x["id"], "name": x["name"]} for x in messages.speakers_for(uid)],
            "all": messages.all_on() and messages.takes_all(uid), "enabled": admin_on(), "on": usable(uid), "groups": groups_on(), "chats": listing(uid),
            "contacts": contacts(uid), "max_text": MAX_TEXT, "reactions": list(REACTIONS),
            "receipts": s.get("chat_receipts", True) is not False, "push_text": s.get("chat_push_text") is True,
            "max_members": MAX_MEMBERS, "media": media_ok(uid), "invite": invite_on(), "private": _private_ok(uid),
            "invite_switch": features._switch(features.chat_cfg(), "chats_invite"),
            **_far_state(uid), "calls": _calls_ok(uid),
            "limits": {"photo_mb": MAX_PHOTO_IN // 1024**2, "file_mb": MAX_FILE // 1024**2, "voice_secs": MAX_VOICE_SECS,
                       "used_mb": round(used(uid) / 1024**2), "quota_mb": QUOTA // 1024**2}}


def _far_state(uid):
    """Chats mit anderen Sparks (verbund.py): whether the page offers it, and how many requests wait."""
    import verbund
    on = verbund.admin_on() and verbund.usable(uid)
    return {"verbund": on, "far_asks": sum(1 for c in verbund.contacts_of(uid).values() if c.get("state") == "in") if on else 0,
            "far_media": bool(on and verbund.media_on() and verbund.media_ok(uid)), "far_people": _far_people(uid)}


def _far_people(uid):
    """The accepted contacts on other Sparks an admin of a group can put into it (verbundgruppe.py), marked 🌐."""
    import verbundgruppe
    import verbund
    if not (verbundgruppe.admin_on() and verbundgruppe.usable(uid)):
        return []
    return [{"id": x["id"], "name": "🌐 " + (x["name"] or x["addr"]), "far": True}
            for x in verbund.listing(uid) if x["state"] == "ok"]


def _calls_ok(uid):
    import anrufe
    return anrufe.admin_on() and anrufe.usable(uid)


def _private_ok(uid):
    import chatsec
    return chatsec.admin_on() and chatsec.usable(uid)


@router.get("/api/chats", dependencies=[Depends(assistant)])
def api_list(request: Request, prof=Depends(own_profile)):
    if request.headers.get(profiles.DEVICE_HEADER) and profiles.key_scope(request) != "app":
        raise HTTPException(403, "only in the profile's own browser login or the iPhone app")
    if not admin_on():
        return {"enabled": False, "on": False, "chats": [], "contacts": []}
    if not usable(prof["id"]):
        return {"enabled": True, "on": False, "chats": [], "contacts": []}
    import guard
    guard.limit(request, "chats", prof["id"])
    uid, now = prof["id"], time.time()
    tidy(now)
    with _lock:   # a device asking for the list counts as "has it" for every chat (the second tick)
        chats = _index()
        for c in chats.values():
            if uid in c["members"]:
                _map(c, "got")[uid] = now
        _save_index(chats)
    return _state(uid)


@router.get("/api/chats/items", dependencies=[Depends(assistant)])
def api_items(request: Request, id: str = "", before: str = "", prof=Depends(_on)):
    try:
        return items(prof["id"], _cid(id), before)
    except (LookupError, ValueError) as e:
        raise _err(e)


@router.post("/api/chats/open", dependencies=[Depends(assistant)])
async def api_open(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    try:
        cid = open_one(prof["id"], str(body.get("to") or ""))
    except (LookupError, PermissionError, OverflowError) as e:
        raise _err(e)
    return {"id": cid}


@router.post("/api/chats/group", dependencies=[Depends(assistant)])
async def api_group(request: Request, prof=Depends(_on)):
    body = await json_body(request, 8192)
    try:
        cid, left = make_group(prof["id"], body.get("name"), body.get("members"))
    except (PermissionError, ValueError, OverflowError) as e:
        raise _err(e)
    return {"id": cid, "left_out": left}


@router.post("/api/chats/send", dependencies=[Depends(assistant)])
async def api_send(request: Request, prof=Depends(_on)):
    body = await json_body(request, 96 * 1024)   # a private chat's box carries the text once per device
    try:
        item = await send(prof["id"], _cid(body.get("id")), body.get("text"), str(body.get("reply") or ""),
                          box=body.get("box") if "box" in body else None)
    except (LookupError, PermissionError, ValueError, OverflowError) as e:
        raise _err(e)
    return {"item": item}


@router.post("/api/chats/edit", dependencies=[Depends(assistant)])
async def api_edit(request: Request, prof=Depends(_on)):
    body = await json_body(request, 16384)
    try:
        edit(prof["id"], _cid(body.get("id")), _mid(body.get("mid")), body.get("text"))
    except (LookupError, PermissionError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/back", dependencies=[Depends(assistant)])
async def api_back(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    try:
        take_back(prof["id"], _cid(body.get("id")), _mid(body.get("mid")))
    except (LookupError, PermissionError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/react", dependencies=[Depends(assistant)])
async def api_react(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    try:
        react(prof["id"], _cid(body.get("id")), _mid(body.get("mid")), str(body.get("emoji") or ""))
    except (LookupError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/read", dependencies=[Depends(assistant)])
async def api_read(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    try:
        read(prof["id"], _cid(body.get("id")))
    except (LookupError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/typing", dependencies=[Depends(assistant)])
async def api_typing(request: Request, prof=Depends(_on)):
    import guard
    guard.limit(request, "chatstyping", prof["id"])
    body = await json_body(request, 1024)
    try:
        typing(prof["id"], _cid(body.get("id")))
    except (LookupError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/opts", dependencies=[Depends(assistant)])
async def api_opts(request: Request, prof=Depends(_on)):
    body = await json_body(request, 2048)
    try:
        options(prof["id"], _cid(body.get("id")), {k: body[k] for k in ("mute", "vanish", "name") if k in body})
    except (LookupError, PermissionError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/members", dependencies=[Depends(assistant)])
async def api_members(request: Request, prof=Depends(_on)):
    body = await json_body(request, 8192)
    lists = []
    for k in ("add", "remove", "admin"):
        v = body.get(k) or []
        if not isinstance(v, list) or len(v) > MAX_MEMBERS:
            raise HTTPException(400, "a list of profiles is required")
        lists.append(v)
    try:
        left = members(prof["id"], _cid(body.get("id")), *lists)
    except (LookupError, PermissionError, ValueError) as e:
        raise _err(e)
    return {"ok": True, "left_out": left}


@router.post("/api/chats/leave", dependencies=[Depends(assistant)])
async def api_leave(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    try:
        leave(prof["id"], _cid(body.get("id")))
    except (LookupError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/clear", dependencies=[Depends(assistant)])
async def api_clear(request: Request, prof=Depends(_on)):
    body = await json_body(request, 1024)
    try:
        clear(prof["id"], _cid(body.get("id")))
    except (LookupError, ValueError) as e:
        raise _err(e)
    return {"ok": True}


@router.post("/api/chats/find", dependencies=[Depends(assistant)])
async def api_find(request: Request, prof=Depends(_on)):
    """POST, not ?q=: the words searched for must not land in the access log."""
    import guard
    guard.limit(request, "chatsfind", prof["id"])
    q = str((await json_body(request, 1024)).get("q") or "")
    if len(q) > 200:
        raise HTTPException(413, "too long")
    return {"hits": await asyncio.to_thread(find, prof["id"], q)}


@router.post("/api/chats/media", dependencies=[Depends(assistant)])
async def api_media_send(request: Request, id: str = "", kind: str = "", reply: str = "", prof=Depends(_on)):
    """A photo, file or voice message as the raw body. A file's name comes in the header X-Chat-Name (percent
    encoded), never in the address: addresses land in the access log."""
    import guard
    from urllib.parse import unquote
    cid = _cid(id)
    if kind == "box":
        return await _box_media(request, cid, reply, prof)
    if kind not in MEDIA:
        raise HTTPException(400, "kind must be photo, file or voice")
    if not media_on() or not media_ok(prof["id"]):
        raise HTTPException(403, "Fotos, Dateien und Sprachnachrichten sind für dich ausgeschaltet.")
    guard.limit(request, "chatsmedia", prof["id"])
    most = {"photo": MAX_PHOTO_IN, "file": MAX_FILE, "voice": MAX_VOICE_IN}[kind]
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > most:
            raise HTTPException(413, "too large")
    try:
        _member(prof["id"], cid)
        if kind == "photo":
            m = await photo(bytes(data))
        elif kind == "voice":
            m = await voice(bytes(data))
        else:
            m = a_file(bytes(data), unquote(request.headers.get("x-chat-name", ""))[:300])
        item = await send(prof["id"], cid, m.pop("text", ""), reply if MID.fullmatch(reply or "") else "", media=m)
    except (LookupError, PermissionError, ValueError, OverflowError) as e:
        raise _err(e)
    _live(f"{MEDIA_WORD[kind]} im Chat")
    return {"item": item}


async def _box_media(request, cid, reply, prof):
    """A private chat's photo, file or voice: the body is the box (one line of JSON), a line break, then the blob the
    device encrypted. The Spark sees only its size."""
    import chatsec
    import guard
    if not media_on() or not media_ok(prof["id"]):
        raise HTTPException(403, "Fotos, Dateien und Sprachnachrichten sind für dich ausgeschaltet.")
    guard.limit(request, "chatsmedia", prof["id"])
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > chatsec.MAX_BLOB + chatsec.MAX_BOX + 16 * 1024:
            raise HTTPException(413, "too large")
    head, sep, blob = bytes(data).partition(b"\n")
    if not sep or len(head) > chatsec.MAX_BOX + 8 * 1024:
        raise HTTPException(400, "bad box")
    try:
        box = json.loads(head)
    except ValueError:
        raise HTTPException(400, "bad box")
    try:
        item = await send(prof["id"], cid, "", reply if MID.fullmatch(reply or "") else "", box=box, blob=blob)
    except (LookupError, PermissionError, ValueError, OverflowError) as e:
        raise _err(e)
    _live("🔒 Anhang im privaten Chat")
    return {"item": item}


@router.get("/api/chats/media", dependencies=[Depends(assistant)])
def api_media_get(request: Request, id: str = "", mid: str = "", part: str = "f", prof=Depends(_seen)):
    """A photo (preview t or full f), a file or a voice message, for the members of its chat. Files only as a
    download (attachment, nosniff, sandbox): the panel never opens or shows them itself."""
    from urllib.parse import quote
    if part not in ("f", "t"):
        raise HTTPException(400, "part is f or t")
    try:
        data, mime, name = media(prof["id"], _cid(id), _mid(mid), part)
    except (LookupError, ValueError) as e:
        raise _err(e)
    head = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox"}
    if not mime.startswith(("image/jpeg", "audio/aac")):
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "Datei")[:120]
        head["Content-Disposition"] = f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(name or safe)}"
        mime = "application/octet-stream" if not mime.startswith("text/plain") else mime
    return Response(data, media_type=mime, headers=head)


# ---------------------------------------------------------------- invite a new person straight into a chat
def _invites(uid, now=None):
    import join
    now = int(time.time() if now is None else now)
    return [{"id": i, "name": v.get("name", ""), "until": v.get("until")} for i, v in join.open_chats(uid, now)]


@router.get("/api/chats/invites", dependencies=[Depends(assistant)])
def api_invites(request: Request, prof=Depends(_on)):
    """Whether this profile may invite (admin switch, „Neue Personen: nur mit Einladung“) and its open invitations."""
    import join
    on = invite_on()
    return {"on": on, "switch": features._switch(features.chat_cfg(), "chats_invite"),
            "open": _invites(prof["id"]) if on else [], "max": join.CHAT_OPEN, "days": INVITE_DAYS}


@router.post("/api/chats/invite", dependencies=[Depends(assistant)])
async def api_invite(request: Request, prof=Depends(_on)):
    """A one-time link with QR code: the person picks name and PIN and lands in the chat with this profile.
    The code is shown only now and stands after the "#" (never in a log)."""
    import guard
    import join
    if not invite_on():
        raise HTTPException(403, "Einladungen in Chats sind auf dem Spark aus.")
    guard.limit(request, "chatsinvite", prof["id"])
    body = await json_body(request, 2048)
    base = join._base(body)
    name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(body.get("name") or "")).strip()[:MAX_NAME]
    iid, code = join.make(name, INVITE_DAYS, by=prof["name"], chat=prof["id"])
    link = f"{base}/#join={code}"
    guard.log("invite_made", by=prof["name"], invite=iid, kind="chat", days=INVITE_DAYS)
    _log("invite made")
    return {"id": iid, "link": link, "qr": join._qr(link), "days": INVITE_DAYS, "open": _invites(prof["id"])}


@router.post("/api/chats/invite/back", dependencies=[Depends(assistant)])
async def api_invite_back(request: Request, prof=Depends(_on)):
    import guard
    import join
    iid = str((await json_body(request, 1024)).get("id") or "")
    if not join._ID.fullmatch(iid) or not join.revoke(iid, chat=prof["id"]):
        raise HTTPException(404, "Diese Einladung gibt es nicht mehr.")
    guard.log("invite_revoked", by=prof["name"], invite=iid)
    return {"open": _invites(prof["id"])}


@router.get("/api/chats/stream", dependencies=[Depends(assistant)])
async def api_stream(request: Request, prof=Depends(_on)):
    """Events for the open page or app: "chat" (a chat changed: only its id), "typing" (a name, a few seconds),
    "gone" (a chat left or deleted for me). Never a text."""
    import guard
    uid = prof["id"]
    guard.limit(request, "chatsstream", uid)
    loop, q, sid = asyncio.get_running_loop(), asyncio.Queue(maxsize=QUEUE), secrets.token_hex(6)
    with _lock:
        subs = _subs.setdefault(uid, {})
        if len(subs) >= MAX_STREAMS:   # the oldest page gives way (it asks again now and then anyway)
            subs.pop(next(iter(subs)))
        subs[sid] = (loop, q)

    async def events():
        end_at = time.monotonic() + STREAM_SECONDS
        try:
            yield "retry: 5000\n\n"
            while time.monotonic() < end_at and usable(uid):
                try:
                    ev = await asyncio.wait_for(q.get(), BEAT)
                except asyncio.TimeoutError:
                    yield ": .\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            with _lock:
                (_subs.get(uid) or {}).pop(sid, None)
                if uid in _subs and not _subs[uid]:
                    _subs.pop(uid)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
