"""New people by invitation (plan plaene/registrierung-onboarding.md, V01.0.269).

The admin switches "Neue Personen" from "aus" (default) to "nur mit Einladung" and makes an invitation:
a one-time link with a QR code (https://<panel>/#join=<code>). The code stands after the "#", so it never
reaches a proxy log, the panel log or a Referer. The person opens it, picks name and PIN (at least six
characters) and is signed in; a "Startpaket" switches on the profile's own switches of a few functions
(only those the admin has on). The same kind of link sets a new PIN for an existing profile ("PIN selbst
wählen" / "PIN vergessen"); a profile with its second step still has to give its code.

Rules: while the switch is off every /api/join route answers 404. Codes are random (128 bits), only their
hash is kept, each works once and until its day; wrong codes count like wrong PINs (guard.py lockout per
address). At most MAX_OPEN open invitations. A new profile never gets a role. Every step is in the change
log without the code.

Second step for new profiles ("mfa": "data", the default): a profile that came in by invitation cannot use
e-mail, documents or agent functions until its second step is on (features.reason "mfa", mail.get,
wissen.add, agent.granted), and cannot switch it off again itself.

    STATE/join.json  {"mode": "off"|"invite", "mfa": "off"|"data", "handoff": bool, "app_link": "https://...",
                      "invites": {id: {"h", "name", "pack", "kind": "new"|"pin", "uid", "t", "until", "used", "by", "made"}},
                      "joined": {uid: {"t", "invite", "mfa": bool}}, "packs": [{"id", "name", "keys"}] | absent}
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
from core import acting_profile, admin_code, auth

router = APIRouter()
_lock = threading.Lock()

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "join.json")
MODES = ("off", "invite")
MFA_MODES = ("off", "data")
DAYS = (1, 7, 30)
MAX_OPEN = 50
KEEP_DAYS = 30            # used and expired invitations stay visible this long
MAX_PACKS, MAX_PACK_KEYS = 10, 40
MAX_BODY = 4096
PIN_MIN = profiles.STRONG_PIN
CODE = re.compile(r"[A-Za-z0-9_\-]{20,40}")
_ID = re.compile(r"i_[0-9a-f]{12}")
_UID = re.compile(r"u_[0-9a-f]{12}")
LINK = re.compile(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?(?:/[A-Za-z0-9._~%!$&'()*+,;=:@/\-]*)?(?:\?[A-Za-z0-9._~%!$&'()*+,;=:@/?\-]*)?")
JOIN_KEY = "\0join"       # one lockout entry for every wrong code from one address (guard.py)
DATA_KEYS = ("mail", "documents", "agent")   # what waits for the second step ("mfa": "data")

# the functions a pack may switch on: those with their own profile switch, never a role
PACKS = ({"id": "familie", "name": "Familie", "keys": ["weather", "tasks", "messages", "iphone", "iphonepush", "contacts",
                                                        "esp32", "transit"]},
         {"id": "gast", "name": "Gast plus", "keys": ["weather"]})


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
            "invites": d.get("invites") if isinstance(d.get("invites"), dict) else {},
            "joined": d.get("joined") if isinstance(d.get("joined"), dict) else {},
            "packs": _clean_packs(d["packs"]) if isinstance(d.get("packs"), list) else None}


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def _prune(d, now):
    for k in [k for k, v in d["invites"].items()
              if (v.get("used") or v.get("until", 0) < now) and max(v.get("used") or 0, v.get("until", 0)) < now - KEEP_DAYS * 86400]:
        d["invites"].pop(k)


def mode():
    return _read()["mode"]


def settings():
    d = _read()
    return {k: d[k] for k in ("mode", "mfa", "handoff", "app_link")}


def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


# ---------------------------------------------------------------- packs
def packable():
    """Functions a pack can switch on: an own profile switch, not the admin-mode ones."""
    return [f for f in features.FEATURES if f.profile and f.key not in ("iphonepanel", "iphoneupdate")]


def _clean_packs(raw):
    keys = {f.key for f in packable()}
    out = []
    for p in raw[:MAX_PACKS]:
        if not isinstance(p, dict):
            continue
        name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(p.get("name") or "")).strip()[:30]
        pid = str(p.get("id") or "")
        if not name or not re.fullmatch(r"[a-z0-9]{1,16}", pid):
            continue
        ks = [k for k in p.get("keys", []) if k in keys][:MAX_PACK_KEYS] if isinstance(p.get("keys"), list) else []
        if not any(x["id"] == pid for x in out):
            out.append({"id": pid, "name": name, "keys": sorted(set(ks))})
    return out


def packs():
    d = _read()
    return d["packs"] if d["packs"] is not None else _clean_packs([dict(p) for p in PACKS])


def apply_pack(uid, pack_id):
    """Switches on the profile's own switches of the pack's functions that the Spark has on. Returns the keys."""
    p = next((x for x in packs() if x["id"] == pack_id), None)
    if not p:
        return []
    c = features.chat_cfg()
    on = [k for k in p["keys"] if k in features.BY_KEY and features.BY_KEY[k].profile and features.admin_on(k, c)]
    if on:
        profiles.save_settings(uid, {features.BY_KEY[k].profile: True for k in on})
    return on


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
    return {"id": i, "name": v.get("name", ""), "pack": v.get("pack", ""), "kind": v.get("kind", "new"),
            "profile": (who or {}).get("name"), "made": v.get("t"), "until": v.get("until"), "used": v.get("used"),
            "by": v.get("by", ""), "state": state}


def listing(now=None):
    now = int(now if now is not None else time.time())
    d = _read()
    out = [_public(i, v, now) for i, v in d["invites"].items()]
    return sorted(out, key=lambda x: (x["state"] != "open", -(x["made"] or 0)))


def make(name, pack, days, uid=None, by="", now=None):
    """A new invitation. Returns (id, code); the code is shown only now."""
    now = int(now if now is not None else time.time())
    code = secrets.token_urlsafe(16)
    with _lock:
        d = _read()
        _prune(d, now)
        if sum(1 for v in d["invites"].values() if not v.get("used") and v.get("until", 0) >= now) >= MAX_OPEN:
            raise HTTPException(409, f"Schon {MAX_OPEN} offene Einladungen. Erst welche zurückziehen.")
        iid = "i_" + secrets.token_hex(6)
        d["invites"][iid] = {"h": _hash(code), "name": name, "pack": pack, "kind": "pin" if uid else "new",
                             "uid": uid or "", "t": now, "until": now + days * 86400, "used": None, "by": by}
        _write(d)
    return iid, code


def revoke(iid):
    with _lock:
        d = _read()
        v = d["invites"].get(iid)
        if not v or v.get("used"):
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


def _joined(uid, iid, now):
    with _lock:
        d = _read()
        d["joined"][uid] = {"t": now, "invite": iid, "mfa": d["mfa"] == "data"}
        _write(d)


def create_profile(code, name, pin, now=None):
    """The person's own profile from a "new" invitation: (uid, name, pack keys switched on).
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
    _joined(uid, iid, now)
    on = apply_pack(uid, v.get("pack", ""))
    import onboard
    onboard.save_state(uid, fresh=True)   # "Los geht's" opens at the first sign-in in a browser
    guard.log("invite_used", uid=uid, name=name, invite=iid, pack=v.get("pack") or None)
    return uid, name, on


async def _json(request):
    """The body, read with a byte limit before anything is parsed (most routes here need no sign-in)."""
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise HTTPException(413, "too big")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "too big")
    try:
        body = json.loads(bytes(raw) or b"{}")
    except ValueError:
        raise HTTPException(400, "not JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "not JSON")
    return body


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
    return dict(settings(), invites=listing(), packs=packs(), max_open=MAX_OPEN, days=list(DAYS), pin_min=PIN_MIN,
                mfa_on=features.admin_on("mfa", c), iphone_on=features.admin_on("iphone", c),
                packable=[{"key": f.key, "name": [f.de, f.en], "on": features.admin_on(f.key, c)} for f in packable()])


@router.put("/api/admin/join", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_put(request: Request):
    body = await _json(request)
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
        if d["packs"] is None:
            d.pop("packs")
        _write(d)
    guard.log("join_settings", by=_by(request), mode=new["mode"], mfa=new["mfa"], handoff=new["handoff"])
    return settings()


@router.put("/api/admin/join/packs", dependencies=[Depends(auth)])
async def admin_packs(request: Request):
    body = await _json(request)
    raw = body.get("packs")
    if not isinstance(raw, list) or len(raw) > MAX_PACKS:
        raise HTTPException(400, f"packs: a list of at most {MAX_PACKS}")
    clean = _clean_packs(raw)
    with _lock:
        d = _read()
        d["packs"] = clean
        _write(d)
    guard.log("join_packs", by=_by(request), packs=len(clean))
    return {"packs": clean}


def _qr(text):
    return mfa._qr_svg(text)


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Einladungen brauchen die https-Adresse des Panels (diese Seite über https öffnen).")
    return base


@router.post("/api/admin/join/invites", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_invite(request: Request):
    body = await _json(request)
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
            raise HTTPException(403, "Profile mit Admin-Rolle ändert nur der Hauptadmin.")
        name, pack = profiles.by_id(uid)["name"], ""
    else:
        if mode() != "invite":
            raise HTTPException(409, "Erst „Neue Personen: nur mit Einladung“ einschalten.")
        name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(body.get("name") or "")).strip()[:40]
        pack = str(body.get("pack") or "")
        if pack and not any(p["id"] == pack for p in packs()):
            raise HTTPException(400, "unknown pack")
    iid, code = make(name, pack, days, uid=uid or None, by=_by(request))
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
    body = await _json(request)
    iid, v = _peek(request, body.get("code"))
    c = features.chat_cfg()
    pack = next((p for p in packs() if p["id"] == v.get("pack")), None)
    uid = v.get("uid") or ""
    return {"kind": v.get("kind", "new"), "name": (profiles.by_id(uid) or {}).get("name") if uid else v.get("name", ""),
            "until": v.get("until"), "pin_min": PIN_MIN, "code": bool(uid and mfa.enabled(uid)),
            "pack": pack["name"] if pack else "", "mfa": _read()["mfa"] == "data" and features.admin_on("mfa", c),
            "app": features.admin_on("iphone", c) and v.get("kind") == "new"}


def _cookie(r, uid, request):
    u = next((u for u in profiles._load()["users"] if u["id"] == uid), None)
    value = profiles._cookie_value(u, agent=request.headers.get("user-agent", ""))
    r.set_cookie(profiles.COOKIE, value, max_age=profiles.session_secs(), httponly=True, samesite="lax")


@router.post("/api/join")
async def join(request: Request):
    """A new profile ("new") or a new PIN ("pin") from an invitation; the browser is signed in afterwards."""
    _pin_or_on()
    body = await _json(request)
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
    uid, name, on = create_profile(code, body.get("name"), body.get("pin"), now)
    r = Response(json.dumps({"ok": True, "name": name, "kind": "new", "on": on}), media_type="application/json")
    _cookie(r, uid, request)
    guard.succeeded(request, name, r)
    _tell_admin(name)
    return r


def _tell_admin(name):
    """The main admin's chosen profile hears of it (coadmin's "notify"), if any."""
    try:
        import coadmin
        import push
        uid = coadmin._read().get("notify")
        if uid and uid in profiles.user_ids():
            loop = asyncio.get_running_loop()
            loop.create_task(push.send(uid, "👋 Spark", f"{name} ist mit einer Einladung dazugekommen.", tag="admin", private=False))
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
    body = await _json(request)
    _peek(request, body.get("code"))
    uid, name, on = create_profile(body.get("code"), body.get("name"), body.get("pin"))
    profiles.save_settings(uid, {"app_on": True})
    token = profiles.add_device(iphone._name(body.get("device")), uid, scope="app")
    guard.log("invite_app", uid=uid, name=name)
    _tell_admin(name)
    return {"token": token, "profile": name, "version": iphone.app_version(), "language": iphone._language(), "on": on}
