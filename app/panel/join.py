"""New people by invitation (plan plaene/registrierung-onboarding.md, V01.0.269).

The admin switches "Neue Personen" from "aus" (default) to "nur mit Einladung" and makes an invitation:
a one-time link with a QR code (https://<panel>/#join=<code>). The code stands after the "#", so it never
reaches a proxy log, the panel log or a Referer. The person opens it, picks name and PIN (at least six
characters) and is signed in; it can use at once every function the admin has on (plan
plaene/freigabe-vereinfachen.md: no per-profile release, so no "Startpakete" any more). The same kind of link
sets a new PIN for an existing profile ("PIN selbst wählen" / "PIN vergessen"); a profile with its second step still has to give its code.

Rules: while the switch is off every /api/join route answers 404. Codes are random (128 bits), only their
hash is kept, each works once and until its day; wrong codes count like wrong PINs (guard.py lockout per
address). At most MAX_OPEN open invitations. A new profile never gets a role. Every step is in the change
log without the code.

Second step for new profiles ("mfa": "data", the default): a profile that came in by invitation cannot use
e-mail, documents or agent functions until its second step is on (features.reason "mfa", mail.get,
wissen.add, agent.granted), and cannot switch it off again itself.

Chat invitations (chats.py, Funktionen → Chats → In einen Chat einladen): a profile with Chats invites a person
straight into a chat with itself. The same kind of invitation, "chat" names the inviting profile; it needs
"Neue Personen: nur mit Einladung", counts toward MAX_OPEN and the admin sees and can withdraw it like his own.

    STATE/join.json  {"mode": "off"|"invite", "mfa": "off"|"data", "handoff": bool, "app_link": "https://...",
                      "invites": {id: {"h", "name", "kind": "new"|"pin", "uid", "t", "until", "used", "by", "made",
                                       "chat": uid of the inviting profile | absent}},
                      "joined": {uid: {"t", "invite", "mfa": bool, "chat": cid | absent}}}
    Older files may still hold "packs" and invitations with "pack": read without a word, dropped at the next write.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import features
import guard
import mfa
import profiles
from common import STATE, write_json
import core
from core import spawn, acting_profile, admin_code, auth

router = APIRouter()
_lock = threading.Lock()

FILE = os.path.join(STATE, "join.json")
MODES = ("off", "invite")
MFA_MODES = ("off", "data")
DAYS = (1, 7, 30)
MAX_OPEN = 50
CHAT_OPEN = 3             # open chat invitations per profile (chats.py)
KEEP_DAYS = 30            # expired invitations stay visible this long
KEEP_USED_DAYS = 7        # used ones this long after use; with the profile deleted they go at once (forget)
MAX_BODY = 4096
PIN_MIN = profiles.STRONG_PIN
CODE = re.compile(r"[A-Za-z0-9_\-]{20,40}")
_ID = re.compile(r"i_[0-9a-f]{12}")
_UID = re.compile(r"u_[0-9a-f]{12}")
LINK = re.compile(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?(?:/[A-Za-z0-9._~%!$&'()*+,;=:@/\-]*)?(?:\?[A-Za-z0-9._~%!$&'()*+,;=:@/?\-]*)?")
JOIN_KEY = "\0join"       # one lockout entry for every wrong code from one address (guard.py)
DATA_KEYS = ("mail", "documents", "agent")   # what waits for the second step ("mfa": "data")


# ---------------------------------------------------------------- the file
def _read():
    try:
        with open(FILE) as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    return {"mode": d.get("mode") if d.get("mode") in MODES else "off",
            "mfa": d.get("mfa") if d.get("mfa") in MFA_MODES else "data",
            "handoff": d.get("handoff") is True,
            "app_link": d.get("app_link") if isinstance(d.get("app_link"), str) and LINK.fullmatch(d["app_link"]) else "",
            "invites": _invites(d.get("invites")),
            "joined": d.get("joined") if isinstance(d.get("joined"), dict) else {}}


def _invites(raw):
    """The invitations; an old "pack" field (the starter packs are gone) is left out."""
    if not isinstance(raw, dict):
        return {}
    return {k: {f: x for f, x in v.items() if f != "pack"} if isinstance(v, dict) else v for k, v in raw.items()}


def _write(d):
    write_json(FILE, d, indent=1, mode=0o600, ensure_ascii=False)


def _prune(d, now):
    for k in [k for k, v in d["invites"].items()
              if (v.get("used") and v["used"] < now - KEEP_USED_DAYS * 86400)
              or (not v.get("used") and v.get("until", 0) < now - KEEP_DAYS * 86400)]:
        d["invites"].pop(k)


def forget(uid):
    """A deleted profile: its invitation (the one it came in with), its PIN links and its entry go."""
    with _lock:
        d = _read()
        j = d["joined"].pop(uid, None)
        drop = [k for k, v in d["invites"].items() if v.get("uid") == uid or (j and k == j.get("invite"))]
        for k in drop:
            d["invites"].pop(k)
        if j or drop:
            _write(d)


def mode():
    return _read()["mode"]


def settings():
    d = _read()
    return {k: d[k] for k in ("mode", "mfa", "handoff", "app_link")}


def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


# ---------------------------------------------------------------- the second step for new profiles
def mfa_due(uid):
    """True while this profile came in by invitation with the duty and has no second step (and can set one up)."""
    if not uid:
        return False
    d = _read()
    j = d["joined"].get(uid)
    if not j or not j.get("mfa") or d["mfa"] != "data":
        return False
    return features.admin_on("mfa") and not mfa.enabled(uid)


def mfa_kept(uid):
    """The profile may not switch its second step off itself (it came in with the duty)."""
    d = _read()
    j = d["joined"].get(uid)
    return bool(j and j.get("mfa") and d["mfa"] == "data")


def _duty(uid, key):
    if not mfa_due(uid):
        return False
    f = features.BY_KEY.get(key)
    while f:
        if f.key in DATA_KEYS:
            return True
        f = features.BY_KEY.get(f.parent) if f.parent else None
    return False


features.DUTY = _duty   # features.reason asks it: "mfa" (erst den zweiten Anmeldeschritt)


# ---------------------------------------------------------------- invitations
def _public(i, v, now):
    state = "used" if v.get("used") else "gone" if v.get("until", 0) < now else "open"
    who = profiles.by_id(v.get("uid")) if v.get("uid") else None
    return {"id": i, "name": v.get("name", ""), "kind": v.get("kind", "new"),
            "profile": (who or {}).get("name"), "made": v.get("t"), "until": v.get("until"), "used": v.get("used"),
            "by": v.get("by", ""), "state": state, "chat": bool(v.get("chat"))}


def listing(now=None):
    """The admin's list; tidied first: old entries and those of profiles deleted meanwhile go."""
    now = int(now if now is not None else time.time())
    with _lock:
        d = _read()
        before = json.dumps(d, sort_keys=True)
        _prune(d, now)
        alive = {u["id"] for u in profiles._load()["users"]}
        for uid in [u for u in d["joined"] if u not in alive]:
            iid = d["joined"].pop(uid).get("invite")
            d["invites"].pop(iid, None)
        for k in [k for k, v in d["invites"].items() if (v.get("uid") and v["uid"] not in alive)
                  or (v.get("chat") and v["chat"] not in alive)]:
            d["invites"].pop(k)
        if json.dumps(d, sort_keys=True) != before:
            _write(d)
    out = [_public(i, v, now) for i, v in d["invites"].items()]
    return sorted(out, key=lambda x: (x["state"] != "open", -(x["made"] or 0)))


def make(name, days, uid=None, by="", now=None, chat=""):
    """A new invitation. Returns (id, code); the code is shown only now. chat: the profile inviting into a chat with
    itself (chats.py), at most CHAT_OPEN open ones per profile."""
    now = int(now if now is not None else time.time())
    code = secrets.token_urlsafe(16)
    with _lock:
        d = _read()
        _prune(d, now)
        if sum(1 for v in d["invites"].values() if not v.get("used") and v.get("until", 0) >= now) >= MAX_OPEN:
            raise HTTPException(409, f"Schon {MAX_OPEN} offene Einladungen. Erst welche zurückziehen.")
        if chat and len(open_chats(chat, now, d)) >= CHAT_OPEN:
            raise HTTPException(409, f"Du hast schon {CHAT_OPEN} offene Einladungen. Erst eine zurückziehen.")
        iid = "i_" + secrets.token_hex(6)
        d["invites"][iid] = {"h": _hash(code), "name": name, "kind": "pin" if uid else "new",
                             "uid": uid or "", "t": now, "until": now + days * 86400, "used": None, "by": by}
        if chat:
            d["invites"][iid]["chat"] = chat
        _write(d)
    return iid, code


def open_chats(uid, now=None, d=None):
    """The open chat invitations of a profile: [(id, invitation)]."""
    now = int(now if now is not None else time.time())
    d = _read() if d is None else d
    return [(i, v) for i, v in d["invites"].items()
            if v.get("chat") == uid and not v.get("used") and v.get("until", 0) >= now]


def revoke(iid, chat=""):
    """Withdraws an open invitation; with chat only one this profile made."""
    with _lock:
        d = _read()
        v = d["invites"].get(iid)
        if not v or v.get("used") or (chat and v.get("chat") != chat):
            return False
        v["until"] = min(v.get("until", 0), int(time.time()) - 1)
        _write(d)
        return True


def find(code, now=None):
    """(id, invitation) for a valid open code, else (None, None). Does not use it up."""
    now = int(now if now is not None else time.time())
    if not isinstance(code, str) or not CODE.fullmatch(code):
        return None, None
    h = _hash(code)
    d = _read()
    for i, v in d["invites"].items():
        if hmac.compare_digest(str(v.get("h", "")), h):
            if v.get("used") or v.get("until", 0) < now:
                return None, None
            if v.get("kind") == "pin" and not profiles.by_id(v.get("uid")):
                return None, None
            if v.get("chat"):   # a chat invitation works only while its switch is on and its profile has Chats
                import chats
                if not chats.invite_on() or not chats.usable(v["chat"]):
                    return None, None
            return i, v
    return None, None


def _use(iid, h, now):
    """Marks it used, once: False when someone else was quicker."""
    with _lock:
        d = _read()
        v = d["invites"].get(iid)
        if not v or v.get("used") or v.get("h") != h or v.get("until", 0) < now:
            return False
        v["used"] = now
        _write(d)
        return True


def _unuse(iid):
    with _lock:
        d = _read()
        if iid in d["invites"]:
            d["invites"][iid]["used"] = None
            _write(d)


def _joined(uid, iid, now, cid=""):
    with _lock:
        d = _read()
        d["joined"][uid] = {"t": now, "invite": iid, "mfa": d["mfa"] == "data"}
        if cid:
            d["joined"][uid]["chat"] = cid
        _write(d)


def chat_of(uid):
    """The chat a new profile was invited into (opened at its first sign-in), or ""."""
    return (_read()["joined"].get(uid) or {}).get("chat", "")


def create_profile(code, name, pin, now=None):
    """The person's own profile from a "new" invitation: (uid, name). What it may use is what the admin has on.
    Raises HTTPException for a bad code, name or PIN."""
    now = int(now if now is not None else time.time())
    iid, v = find(code, now)
    if not v or v.get("kind") != "new":
        raise HTTPException(400, "Die Einladung passt nicht oder ist abgelaufen.")
    name = str(name or "").strip()
    if not profiles.valid_name(name):
        raise HTTPException(400, "Name: 1 bis 40 Zeichen.")
    pin = str(pin or "")
    if not profiles.valid_pin(pin) or len(pin) < PIN_MIN:
        raise HTTPException(400, f"PIN: mindestens {PIN_MIN} Zeichen, ohne Leerzeichen.")
    if any(u["name"].lower() == name.lower() for u in profiles._load()["users"]):
        raise HTTPException(409, "Diesen Namen gibt es schon. Bitte einen anderen wählen.")
    if not _use(iid, v["h"], now):
        raise HTTPException(400, "Die Einladung passt nicht oder ist abgelaufen.")
    try:
        uid = profiles.add_user(name, pin)
    except ValueError:   # taken a moment ago: the invitation stays usable
        _unuse(iid)
        raise HTTPException(409, "Diesen Namen gibt es schon. Bitte einen anderen wählen.")
    cid = ""
    if v.get("chat"):   # invited into a chat (chats.py): Chats on for the new person, the chat with the inviter open
        import chats
        try:
            cid = chats.joined_by_invite(uid, v["chat"], now)
        except Exception as e:
            print("join: chat invitation failed:", type(e).__name__, flush=True)
    _joined(uid, iid, now, cid)
    import onboard
    onboard.save_state(uid, fresh=not cid)   # "Los geht's" opens at the first sign-in (a chat invitation opens the chat)
    guard.log("invite_used", uid=uid, name=name, invite=iid, chat=bool(cid) or None)
    return uid, name


def _on():
    if mode() != "invite":
        raise HTTPException(404, "Not Found")


def _bad(request):
    guard.failed(request, None, what="invite_code")


# ---------------------------------------------------------------- admin
def _by(request):
    prof = acting_profile(request)
    return prof["name"] if prof else "Admin"


@router.get("/api/admin/join", dependencies=[Depends(auth)])
def admin_get():
    c = features.chat_cfg()
    return dict(settings(), invites=listing(), max_open=MAX_OPEN, days=list(DAYS), pin_min=PIN_MIN,
                mfa_on=features.admin_on("mfa", c), iphone_on=features.admin_on("iphone", c))


@router.put("/api/admin/join", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_put(request: Request):
    body = await core.json_body(request, MAX_BODY)
    new = settings()
    if "mode" in body:
        if body["mode"] not in MODES:
            raise HTTPException(400, "mode: off or invite")
        new["mode"] = body["mode"]
    if "mfa" in body:
        if body["mfa"] not in MFA_MODES:
            raise HTTPException(400, "mfa: off or data")
        new["mfa"] = body["mfa"]
    if "handoff" in body:
        if not isinstance(body["handoff"], bool):
            raise HTTPException(400, "handoff must be true or false")
        new["handoff"] = body["handoff"]
    if "app_link" in body:
        link = str(body["app_link"] or "").strip()
        if link and (len(link) > 300 or not LINK.fullmatch(link)):
            raise HTTPException(400, "Link zur App: nur https://…, höchstens 300 Zeichen.")
        new["app_link"] = link
    with _lock:
        d = _read()
        d.update(new)
        _write(d)
    guard.log("join_settings", by=_by(request), mode=new["mode"], mfa=new["mfa"], handoff=new["handoff"])
    return settings()


def _qr(text):
    return mfa._qr_svg(text)


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Einladungen brauchen die https-Adresse des Panels (diese Seite über https öffnen).")
    return base


@router.post("/api/admin/join/invites", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_invite(request: Request):
    body = await core.json_body(request, MAX_BODY)
    base = _base(body)
    uid = str(body.get("uid") or "")
    days = body.get("days", 7)
    if days not in DAYS:
        raise HTTPException(400, "days: 1, 7 or 30")
    if uid:
        if not _UID.fullmatch(uid) or not profiles.by_id(uid):
            raise HTTPException(404, "no such profile")
        import coadmin
        if acting_profile(request) and coadmin.role(uid):
            raise HTTPException(403, "Profile mit Admin-Rolle ändert nur das Panel-Passwort.")
        name = profiles.by_id(uid)["name"]
    else:
        if mode() != "invite":
            raise HTTPException(409, "Erst „Neue Personen: nur mit Einladung“ einschalten.")
        name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(body.get("name") or "")).strip()[:40]
    iid, code = make(name, days, uid=uid or None, by=_by(request))
    link = f"{base}/#join={code}"
    guard.log("invite_made", by=_by(request), invite=iid, name=name or None, kind="pin" if uid else "new", days=days)
    out = {"id": iid, "link": link, "qr": _qr(link), "days": days}
    if not uid and features.admin_on("iphone"):
        import urllib.parse
        out["app"] = "spark-app://join?" + urllib.parse.urlencode({"url": base, "code": code})
    return out


@router.delete("/api/admin/join/invites/{iid}", dependencies=[Depends(auth)])
def admin_revoke(iid: str, request: Request):
    if not _ID.fullmatch(iid) or not revoke(iid):
        raise HTTPException(404, "no such open invitation")
    guard.log("invite_revoked", by=_by(request), invite=iid)
    return {"ok": True}


# ---------------------------------------------------------------- the invited person
def _open_pins(now=None):
    now = time.time() if now is None else now
    return any(v.get("kind") == "pin" and not v.get("used") and v.get("until", 0) > now for v in _read()["invites"].values())


def _pin_or_on():
    """PIN links are the admin's tool and work while "Neue Personen" is off; then the routes answer only
    while such a link is open."""
    if mode() != "invite" and not _open_pins():
        raise HTTPException(404, "Not Found")


def _peek(request, code):
    _pin_or_on()
    guard.check(request)
    iid, v = find(code)
    if v and mode() != "invite" and v.get("kind") != "pin":
        v = None   # an old invitation for a new person, while new people are off
    if not v:
        _bad(request)
        raise HTTPException(400, "Die Einladung passt nicht oder ist abgelaufen.")
    return iid, v


@router.post("/api/join/check")
async def join_check(request: Request):
    """What the welcome page shows: the suggested name, until when, what is needed. Uses nothing up."""
    _pin_or_on()
    body = await core.json_body(request, MAX_BODY)
    iid, v = _peek(request, body.get("code"))
    c = features.chat_cfg()
    uid = v.get("uid") or ""
    return {"kind": v.get("kind", "new"), "name": (profiles.by_id(uid) or {}).get("name") if uid else v.get("name", ""),
            "until": v.get("until"), "pin_min": PIN_MIN, "code": bool(uid and mfa.enabled(uid)),
            "mfa": _read()["mfa"] == "data" and features.admin_on("mfa", c),
            "app": features.admin_on("iphone", c) and v.get("kind") == "new"}


def _cookie(r, uid, request):
    u = next((u for u in profiles._load()["users"] if u["id"] == uid), None)
    value = profiles._cookie_value(u, agent=request.headers.get("user-agent", ""))
    r.set_cookie(profiles.COOKIE, value, max_age=profiles.session_secs(), httponly=True, samesite="lax")


@router.post("/api/join")
async def join(request: Request):
    """A new profile ("new") or a new PIN ("pin") from an invitation; the browser is signed in afterwards."""
    _pin_or_on()
    body = await core.json_body(request, MAX_BODY)
    code = body.get("code")
    iid, v = _peek(request, code)
    now = int(time.time())
    if v.get("kind") == "pin":
        uid = v["uid"]
        name = profiles.by_id(uid)["name"]
        pin = str(body.get("pin") or "")
        if not profiles.valid_pin(pin) or len(pin) < PIN_MIN:
            raise HTTPException(400, f"PIN: mindestens {PIN_MIN} Zeichen, ohne Leerzeichen.")
        if mfa.enabled(uid):   # the second step stays: its code too
            got = str(body.get("mfa_code") or "").strip()
            if not got:
                return Response('{"code": true}', media_type="application/json")
            guard.check(request, name)
            if not mfa.verify(uid, got):
                guard.failed(request, name, what="profile_code")
                await asyncio.sleep(1)
                raise HTTPException(401, "wrong code")
        if not _use(iid, v["h"], now):
            raise HTTPException(400, "Die Einladung passt nicht oder ist abgelaufen.")
        profiles.set_pin(uid, pin)     # ends the logins made with the old PIN
        profiles._drop_sessions(uid)
        guard.log("invite_pin", uid=uid, name=name, invite=iid)
        r = Response(json.dumps({"ok": True, "name": name, "kind": "pin"}), media_type="application/json")
        _cookie(r, uid, request)
        guard.succeeded(request, name, r)
        return r
    uid, name = create_profile(code, body.get("name"), body.get("pin"), now)
    r = Response(json.dumps({"ok": True, "name": name, "kind": "new", "chat": chat_of(uid)}),
                 media_type="application/json")
    _cookie(r, uid, request)
    guard.succeeded(request, name, r)
    _tell_admin(name)
    return r


def _tell_admin(name):
    """The main admin profile hears of it (coadmin.main_uid), if any."""
    try:
        import coadmin
        import push
        uid = coadmin.main_uid()
        if uid and uid in profiles.user_ids():
            spawn(push.send(uid, "👋 Spark", f"{name} ist mit einer Einladung dazugekommen.", tag="admin", private=False))
    except Exception as e:
        print("join: note failed:", type(e).__name__, flush=True)


@router.post("/api/iphone/join")
async def app_join(request: Request):
    """The iPhone app with an invitation: the profile and this iPhone's key in one step."""
    _on()
    guard.limit(request, "pair")
    import iphone
    if not features.admin_on("iphone"):
        raise HTTPException(403, "Die iPhone-App ist auf diesem Spark aus.")
    body = await core.json_body(request, MAX_BODY)
    _peek(request, body.get("code"))
    uid, name = create_profile(body.get("code"), body.get("name"), body.get("pin"))
    token = profiles.add_device(iphone._name(body.get("device")), uid, scope="app")
    guard.log("invite_app", uid=uid, name=name)
    _tell_admin(name)
    return {"token": token, "profile": name, "version": iphone.app_version(), "language": iphone._language(),
            "chat": chat_of(uid)}
