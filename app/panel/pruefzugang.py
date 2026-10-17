"""Prüfzugang für die iPhone-App (Dominik 2026-10-17, "1+2"): Apple's app review gets in without the 10-minute link.

The admin makes a review access for one profile (Personen und Geräte → Prüfzugang für die iPhone-App), best a profile
of its own such as "App Review". The panel shows a code of twelve letters and digits (XXXX-XXXX-XXXX, 31 signs without
look-alikes, about 59 bits) once, together with the panel's https address; both go into App Store Connect → App Review
Information. In the app the reviewer taps „Mit Prüf-Code verbinden“, types address and code and gets a device key
with scope "app" through the usual /api/iphone/pair (iphone.py hands every code that is not a pairing link to take()).

Rules: admin switch chat.iphone_review (off, parent iPhone-App); while it is off no code pairs and making one answers
403, the list and deleting stay. A code works DAYS days and for at most MAX_USES iPhones; only its sha256 is kept.
Wrong codes count like wrong PINs (guard.check/guard.failed lockout per address) on top of the "pair" rate limit.
Profiles with an admin role are refused. While a profile has a review access, LOCKED (smart home, mail, contacts,
calendars, calls, chats, Telegram, agent jobs, speakers, phone, PC control, updates, reports, NAS, reMarkable) is
blocked for it (features.REVIEW), whatever the admin switches say. Deleting the access, an expired access (tidy) and
deleting the profile remove the iPhones paired with it at once. Every step is in the admin log without the code.

    STATE/iphone-pruef.json  {"codes": {id: {"h", "uid", "t", "until", "used": n, "devices": [did], "by"}}}
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import STATE, write_json
import core
from core import acting_profile, admin_code, auth

router = APIRouter()
_lock = threading.Lock()

FILE = os.path.join(STATE, "iphone-pruef.json")
KEY = "iphonepruef"
DAYS = 14
MAX_USES = 5            # iPhones per code (a reviewer may use more than one device)
MAX_OPEN = 3            # review accesses on the whole Spark
KEEP_DAYS = 7           # an expired access stays in the list this long (its iPhones are gone already)
MAX_BODY = 4096
SIGNS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L
LENGTH = 12
FORM = re.compile(rf"[{SIGNS}]{{{LENGTH}}}")
_ID = re.compile(r"p_[0-9a-f]{12}")
_UID = re.compile(r"u_[0-9a-f]{12}")
# blocked for a profile with a review access: whatever reaches other people, the house, accounts or the Spark itself
LOCKED = ("ha", "mail", "contacts", "calendar", "anrufe", "chats", "telegram", "agent", "mcp", "esp32", "room",
          "messages_announce", "telefon", "begleiter", "iphoneupdate", "melden", "nas", "speicher", "remarkable")


# ---------------------------------------------------------------- the file
def _read():
    try:
        with open(FILE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    codes = d.get("codes") if isinstance(d, dict) and isinstance(d.get("codes"), dict) else {}
    return {"codes": {k: v for k, v in codes.items() if _ID.fullmatch(str(k)) and isinstance(v, dict)}}


def _write(d):
    write_json(FILE, d, indent=1, mode=0o600)


def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def norm(typed):
    """The typed code without spaces and dashes, in capitals; None when it is not of the form."""
    if not isinstance(typed, str) or len(typed) > 40:
        return None
    c = re.sub(r"[\s\-]", "", typed).upper()
    return c if FORM.fullmatch(c) else None


def shown(code):
    return "-".join(code[i:i + 4] for i in range(0, LENGTH, 4))


def on():
    return features.admin_on(KEY)


# ---------------------------------------------------------------- what a review access blocks
_seen = {"m": None, "uids": frozenset()}


def _uids():
    """The profiles with a review access, read again only when the file changed (features.blocked asks often)."""
    try:
        m = os.stat(FILE).st_mtime_ns
    except OSError:
        return frozenset()
    if m != _seen["m"]:
        _seen["uids"] = frozenset(v.get("uid") for v in _read()["codes"].values() if v.get("uid"))
        _seen["m"] = m
    return _seen["uids"]


def locked(uid):
    """The functions blocked for this profile because of a review access (features.REVIEW)."""
    return LOCKED if uid and uid in _uids() else ()


features.REVIEW = locked


# ---------------------------------------------------------------- tidy, list, make, delete
def _drop_devices(v):
    for did in v.get("devices") or ():
        profiles.delete_device(did)


def tidy(now=None):
    """Expired accesses lose their iPhones; KEEP_DAYS later, or with the profile deleted, the entry goes."""
    now = int(now if now is not None else time.time())
    alive = set(profiles.user_ids())
    with _lock:
        d = _read()
        changed = False
        for k, v in list(d["codes"].items()):
            if v.get("uid") not in alive or v.get("until", 0) < now - KEEP_DAYS * 86400:
                _drop_devices(v)
                d["codes"].pop(k)
                changed = True
            elif v.get("until", 0) < now and v.get("devices"):
                _drop_devices(v)
                v["devices"] = []
                changed = True
                print("iphone: review access expired, iPhones removed", flush=True)
        if changed:
            _write(d)


def listing(now=None):
    now = int(now if now is not None else time.time())
    tidy(now)
    alive = {x["id"] for x in profiles._load()["devices"]}
    out = []
    for k, v in _read()["codes"].items():
        who = profiles.by_id(v.get("uid")) or {}
        out.append({"id": k, "profile": who.get("name", ""), "made": v.get("t"), "until": v.get("until"),
                    "used": int(v.get("used") or 0), "max": MAX_USES, "by": v.get("by", ""),
                    "phones": sum(1 for did in v.get("devices") or () if did in alive),
                    "state": "open" if v.get("until", 0) >= now else "gone"})
    return sorted(out, key=lambda x: -(x["made"] or 0))


def make(uid, by="", now=None):
    """A new review access for the profile uid. Returns (id, code); the code is shown only now."""
    now = int(now if now is not None else time.time())
    code = "".join(secrets.choice(SIGNS) for _ in range(LENGTH))
    with _lock:
        d = _read()
        if sum(1 for v in d["codes"].values() if v.get("until", 0) >= now) >= MAX_OPEN:
            raise HTTPException(409, f"Schon {MAX_OPEN} offene Prüfzugänge. Erst einen löschen.")
        rid = "p_" + secrets.token_hex(6)
        d["codes"][rid] = {"h": _hash(code), "uid": uid, "t": now, "until": now + DAYS * 86400, "used": 0,
                           "devices": [], "by": by}
        _write(d)
    return rid, code


def delete(rid):
    """Deletes a review access and the iPhones paired with it."""
    with _lock:
        d = _read()
        v = d["codes"].pop(rid, None)
        if not v:
            return False
        _drop_devices(v)
        _write(d)
        return True


def forget(uid):
    """A deleted profile: its review accesses go (its devices went with the profile)."""
    with _lock:
        d = _read()
        drop = [k for k, v in d["codes"].items() if v.get("uid") == uid]
        for k in drop:
            d["codes"].pop(k)
        if drop:
            _write(d)


# ---------------------------------------------------------------- the app
def take(request, typed, now=None):
    """/api/iphone/pair with a typed review code: (rid, uid) and one use counted, else None (the caller answers).
    Raises 429 while this address is locked for wrong codes."""
    code = norm(typed)
    if not code:
        return None
    now = int(now if now is not None else time.time())
    if not on():
        return None
    guard.check(request)
    h = _hash(code)
    with _lock:
        d = _read()
        hit = next((k for k, v in d["codes"].items() if hmac.compare_digest(str(v.get("h", "")), h)), None)
        v = d["codes"].get(hit) if hit else None
        if not v or v.get("until", 0) < now or int(v.get("used") or 0) >= MAX_USES:
            hit = None
        else:
            v["used"] = int(v.get("used") or 0) + 1
            _write(d)
    if not hit:
        guard.failed(request, None, what="review_code")
        return None
    return hit, v["uid"]


def paired(rid, did):
    """The iPhone that came in with this access: deleting the access removes it."""
    with _lock:
        d = _read()
        v = d["codes"].get(rid)
        if v is not None:
            v["devices"] = (v.get("devices") or []) + [did]
            _write(d)


# ---------------------------------------------------------------- admin
def _by(request):
    prof = acting_profile(request)
    return prof["name"] if prof else "Admin"


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Der Prüfzugang braucht die https-Adresse des Panels (diese Seite über https öffnen).")
    return base


@router.get("/api/admin/pruefzugang", dependencies=[Depends(auth)])
def admin_get():
    return {"on": on(), "iphone_on": features.admin_on("iphone"), "codes": listing(), "days": DAYS,
            "max_uses": MAX_USES, "max_open": MAX_OPEN, "locked": list(LOCKED),
            "profiles": [{"id": u["id"], "name": u["name"]} for u in profiles._load()["users"]]}


@router.post("/api/admin/pruefzugang", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_make(request: Request):
    if not on():
        raise HTTPException(403, "Erst Funktionen → Prüfzugang für die iPhone-App einschalten.")
    body = await core.json_body(request, MAX_BODY)
    base = _base(body)
    uid = str(body.get("uid") or "")
    if not _UID.fullmatch(uid) or not profiles.by_id(uid):
        raise HTTPException(404, "no such profile")
    import coadmin
    if coadmin.role(uid):
        raise HTTPException(403, "Ein Profil mit Admin-Rolle bekommt keinen Prüfzugang. Ein eigenes Profil anlegen, z. B. „App Review“.")
    rid, code = make(uid, by=_by(request))
    guard.log("review_made", by=_by(request), review=rid, uid=uid, days=DAYS)
    print("iphone: review access made for", profiles.log_name(profiles.by_id(uid)), flush=True)
    return {"id": rid, "code": shown(code), "base": base, "days": DAYS, "max_uses": MAX_USES}


@router.delete("/api/admin/pruefzugang/{rid}", dependencies=[Depends(auth)])
def admin_delete(rid: str, request: Request):
    if not _ID.fullmatch(rid) or not delete(rid):
        raise HTTPException(404, "no such review access")
    guard.log("review_deleted", by=_by(request), review=rid)
    print("iphone: review access deleted", flush=True)
    return {"ok": True}
