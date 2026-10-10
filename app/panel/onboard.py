"""Einrichten an der Hand (plan plaene/registrierung-onboarding.md, V01.0.269).

One list per profile of what is still to set up: second step, devices (iPhone app, Pebble, speakers,
voice, notifications, Telegram) and services (calendar, mail, contacts, weather, bus and train, smart
home). Only what the Spark allows (features.py) shows; "done" is checked by the panel itself (an iPhone is
paired, a calendar connected …), never taken from the browser. The page "Los geht's" walks through it step
by step, and the same list gives "Einrichten x von y" (Ich, and for the admin under Personen und Geräte).
"Später" hides one item for this profile.

"Am Handy weitermachen" (handoff): the computer's own profile login shows a QR code (code 128 bits, two
minutes, once). The phone that scans it gets a two-digit number; the computer shows three numbers and only
the matching one signs the phone in, a wrong one ends the code. Off unless the admin switched it on
(join.json "handoff"). Codes live in memory only.

    USERS_DIR/<uid>/setup.json  {"welcome": bool, "later": [keys], "fresh": bool}
"""
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import features
import guard
import join
import mfa
import profiles
from core import assistant, auth, browser_profile, own_profile

router = APIRouter()
_lock = threading.Lock()

# key, function, step, Ich page, name
ITEMS = (
    ("welcome", None, "hello", "setbox", "Stimme und Gespräch einstellen", "Voice and conversation"),
    ("mfa", "mfa", "secure", "secbox", "Zweiter Anmeldeschritt", "Second sign-in step"),
    ("iphone", "iphone", "devices", "appbox", "iPhone-App koppeln", "Pair the iPhone app"),
    ("pebble", "pebble", "devices", "pebbox", "Pebble-Uhr koppeln", "Pair the Pebble watch"),
    ("esp32", "esp32", "devices", "espbox", "Lautsprecher einrichten", "Set up a speaker"),
    ("voice", "speaker", "devices", "voicebox", "Stimme einlernen", "Teach your voice"),
    ("push", "reminders", "devices", "notebox", "Mitteilungen erlauben", "Allow notifications"),
    ("telegram", "telegram", "devices", "tgbox", "Telegram verbinden", "Link Telegram"),
    ("calendar", "calendar", "services", "calbox", "Kalender verbinden", "Connect a calendar"),
    ("mail", "mail", "services", "mailbox", "E-Mail verbinden", "Connect e-mail"),
    ("contacts", "contacts", "services", "conbox", "Kontakte verbinden", "Connect contacts"),
    ("remarkable", "remarkable", "services", "rmbox", "reMarkable verbinden", "Connect the reMarkable"),
    ("weather", "weather", "services", "wxbox", "Wetterort wählen", "Pick a weather place"),
    ("transit", "transit", "services", "trbox", "Haltestelle wählen", "Pick a stop"),
    ("ha", "ha", "services", "habox", "Smart Home verbinden", "Connect the smart home"),
)
KEYS = tuple(x[0] for x in ITEMS)
STEPS = (("hello", "Willkommen", "Welcome"), ("secure", "Absichern", "Secure"), ("devices", "Geräte", "Devices"),
         ("services", "Dienste", "Services"), ("done", "Fertig", "Done"))
CACHE_SECS = 20
_cache = {}


def _file(uid):
    return profiles._path(uid, "setup.json")


def state(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    return {"welcome": d.get("welcome") is True, "fresh": d.get("fresh") is True,
            "later": [k for k in d.get("later", []) if k in KEYS] if isinstance(d.get("later"), list) else []}


def save_state(uid, **change):
    with _lock:
        d = dict(state(uid), **change)
        profiles._write(_file(uid), d)
    _cache.pop(uid, None)
    return d


def _done(key, uid):
    """Checked by the panel; a module that is missing or fails counts as not done."""
    try:
        if key == "welcome":
            return state(uid)["welcome"]
        if key == "mfa":
            return mfa.enabled(uid)
        if key == "iphone":
            import iphone
            return bool(iphone.phones(uid))
        if key == "pebble":
            import pebblewatch
            return bool(pebblewatch.watches(uid))
        if key == "esp32":
            import esp32
            return bool(esp32._list(uid))
        if key == "voice":
            import speakers
            return bool(speakers.has_voice(uid))
        if key == "push":
            import push
            return bool(push.subs(uid))
        if key == "telegram":
            import telegram
            return bool(telegram.link(uid))
        if key == "calendar":
            import calendars
            return bool(calendars.public(uid).get("calendars"))
        if key == "mail":
            import mail
            return bool(mail.public(uid)["accounts"])
        if key == "contacts":
            import contacts
            return bool(contacts.accounts(uid))
        if key == "remarkable":
            import remarkable
            return bool(remarkable.load(uid).get("token"))
        if key == "weather":
            import weather
            return bool(weather.get(uid))
        if key == "transit":
            import transit
            return bool((transit.get(uid).get("home") or {}).get("id"))
        if key == "ha":
            import homeassistant
            return bool(homeassistant.public(uid).get("has_token"))
    except Exception as e:
        print("onboard:", key, type(e).__name__, flush=True)
    return False


def _shown(key, feat, c):
    """The Spark allows it and it can be set up here."""
    if feat and not features.admin_on(feat, c):
        return False
    try:
        if key == "push":
            import push
            return push.available()
        if key == "telegram":
            import telegram
            return bool(telegram.token())
    except Exception:
        return False
    return True


def items(uid, c=None):
    c = features.chat_cfg() if c is None else c
    s = profiles.settings(uid)
    st = state(uid)
    out = []
    for key, feat, step, me, de, en in ITEMS:
        if not _shown(key, feat, c):
            continue
        f = features.BY_KEY.get(feat) if feat else None
        why = features.reason(feat, uid, c, s) if feat else None
        out.append({"key": key, "step": step, "name": [de, en], "me": me, "done": _done(key, uid),
                    "own": f.profile if f and f.profile else None, "mine": why != "profile",
                    "why": why, "required": key == "mfa" and join.mfa_kept(uid), "later": key in st["later"]})
    return out


def summary(uid, now=None):
    """{"done", "total", "open": [German names]}; "Später" items count as neither. Cached a little."""
    now = time.time() if now is None else now
    hit = _cache.get(uid)
    if hit and now - hit[0] < CACHE_SECS:
        return hit[1]
    its = [x for x in items(uid) if not x["later"]]
    out = {"done": sum(1 for x in its if x["done"]), "total": len(its), "open": [x["name"][0] for x in its if not x["done"]]}
    if len(_cache) > 500:
        _cache.clear()
    _cache[uid] = (now, out)
    return out


def whoami(uid):
    s = summary(uid)
    return dict(s, fresh=state(uid)["fresh"], open=len(s["open"]))


# ---------------------------------------------------------------- the profile's own list
@router.get("/api/profile/setup", dependencies=[Depends(assistant)])
def profile_setup(request: Request, prof=Depends(own_profile)):
    guard.limit(request, "features", prof["id"])
    d = join.settings()
    out = {"steps": [{"key": k, "name": [de, en]} for k, de, en in STEPS], "items": items(prof["id"]),
           "state": state(prof["id"]), "handoff": d["handoff"]}
    if d["app_link"] and features.admin_on("iphone"):
        out["app_link"], out["app_qr"] = d["app_link"], join._qr(d["app_link"])
    return out


@router.put("/api/profile/setup", dependencies=[Depends(assistant)])
async def profile_setup_put(request: Request, prof=Depends(browser_profile)):
    body = await join._json(request)
    change = {}
    if "welcome" in body:
        change["welcome"] = body["welcome"] is True
    if "fresh" in body:
        change["fresh"] = body["fresh"] is True
    if "later" in body:
        later = body["later"]
        if not isinstance(later, list) or len(later) > len(KEYS) or not all(k in KEYS for k in later):
            raise HTTPException(400, "later: known keys only")
        change["later"] = sorted(set(later))
    st = save_state(prof["id"], **change)
    return {"state": st, "summary": summary(prof["id"])}


# ---------------------------------------------------------------- the admin sees it, and reminds
_reminded = {}
REMIND_EVERY = 3600


@router.post("/api/admin/profiles/{uid}/remind", dependencies=[Depends(auth)])
async def admin_remind(uid: str, request: Request):
    if not re.fullmatch(r"u_[0-9a-f]{12}", uid) or not profiles.by_id(uid):
        raise HTTPException(404, "no such profile")
    now = time.time()
    if now - _reminded.get(uid, 0) < REMIND_EVERY:
        raise HTTPException(429, "Schon erinnert. Höchstens einmal pro Stunde.")
    s = summary(uid, now=now + CACHE_SECS + 1)
    if not s["open"]:
        return {"sent": 0, "open": 0}
    import push
    _reminded[uid] = now
    text = "Noch einzurichten: " + ", ".join(s["open"][:4]) + ("…" if len(s["open"]) > 4 else "") + ". Im Panel unter Ich → Los geht's."
    try:
        sent = await push.send(uid, "Spark", text, tag="setup", private=False)
    except Exception as e:
        print("onboard: remind failed:", type(e).__name__, flush=True)
        sent = 0
    who = join._by(request)
    guard.log("setup_remind", by=who, uid=uid, sent=sent)
    return {"sent": sent, "open": len(s["open"])}


# ---------------------------------------------------------------- "Am Handy weitermachen"
HAND_SECS = 120
MAX_HAND = 20
_hand = {}    # hid -> {"uid", "h", "t", "state": open|claimed|ok|dead|used, "num", "w", "agent"}


def _hclean(now):
    for k in [k for k, v in _hand.items() if now - v["t"] > HAND_SECS]:
        _hand.pop(k, None)


def _hand_on():
    if not join.settings()["handoff"]:
        raise HTTPException(404, "Not Found")


def _hbase(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Adresse: http(s)://name oder http(s)://name:port")
    return base


def hand_new(uid, now=None):
    now = time.time() if now is None else now
    code = secrets.token_urlsafe(16)
    hid = secrets.token_hex(8)
    with _lock:
        _hclean(now)
        for k in [k for k, v in _hand.items() if v["uid"] == uid]:   # one at a time per profile
            _hand.pop(k)
        if len(_hand) >= MAX_HAND:
            raise HTTPException(429, "Gerade zu viele offene Übergaben. Bitte gleich noch einmal.")
        _hand[hid] = {"uid": uid, "h": hashlib.sha256(code.encode()).hexdigest(), "t": now, "state": "open",
                      "num": 0, "w": "", "agent": ""}
    return hid, code


def _hfind(code, now):
    if not isinstance(code, str) or not join.CODE.fullmatch(code):
        return None, None
    h = hashlib.sha256(code.encode()).hexdigest()
    _hclean(now)
    for k, v in _hand.items():
        if hmac.compare_digest(v["h"], h):
            return k, v
    return None, None


def hand_claim(code, agent="", now=None):
    """The phone scanned it: its number and its wait token, once."""
    now = time.time() if now is None else now
    with _lock:
        hid, v = _hfind(code, now)
        if not v or v["state"] != "open":
            return None
        w = secrets.token_urlsafe(16)
        v.update(state="claimed", num=random.SystemRandom().randint(10, 99), w=hashlib.sha256(w.encode()).hexdigest(),
                 agent=profiles.agent_label(agent))
        return {"num": v["num"], "wait": w}


def hand_choices(hid, uid, now=None):
    with _lock:
        _hclean(time.time() if now is None else now)
        v = _hand.get(hid)
    if not v or v["uid"] != uid:
        return None
    out = {"state": v["state"], "agent": v["agent"]}
    if v["state"] == "claimed":
        rnd = random.Random(hid)   # the same three numbers on every poll
        nums = {v["num"]}
        while len(nums) < 3:
            nums.add(rnd.randint(10, 99))
        out["choices"] = sorted(nums, key=lambda n: rnd.random())
    return out


def hand_confirm(hid, uid, num, now=None):
    with _lock:
        _hclean(time.time() if now is None else now)
        v = _hand.get(hid)
        if not v or v["uid"] != uid or v["state"] != "claimed":
            return None
        v["state"] = "ok" if num == v["num"] else "dead"
        return v["state"]


def hand_finish(code, wait, now=None):
    """The uid once the computer picked the right number; "wait" while not yet; None when over."""
    now = time.time() if now is None else now
    with _lock:
        hid, v = _hfind(code, now)
        if not v or not isinstance(wait, str) or not v["w"] \
                or not hmac.compare_digest(v["w"], hashlib.sha256(wait.encode()).hexdigest()):
            return None
        if v["state"] == "claimed":
            return "wait"
        if v["state"] != "ok":
            return None
        v["state"] = "used"
        return v["uid"]


@router.post("/api/profile/handoff", dependencies=[Depends(assistant)])
async def handoff_new(request: Request, prof=Depends(browser_profile)):
    _hand_on()
    body = await join._json(request)
    base = _hbase(body)
    guard.limit(request, "pair")
    hid, code = hand_new(prof["id"])
    link = f"{base}/#hand={code}"
    return {"id": hid, "link": link, "qr": join._qr(link), "seconds": HAND_SECS}


@router.get("/api/profile/handoff/{hid}", dependencies=[Depends(assistant)])
def handoff_state(hid: str, prof=Depends(browser_profile)):
    _hand_on()
    out = hand_choices(hid, prof["id"]) if re.fullmatch(r"[0-9a-f]{16}", hid) else None
    if not out:
        raise HTTPException(404, "abgelaufen")
    return out


@router.post("/api/profile/handoff/{hid}/confirm", dependencies=[Depends(assistant)])
async def handoff_confirm(hid: str, request: Request, prof=Depends(browser_profile)):
    _hand_on()
    body = await join._json(request)
    num = body.get("num")
    st = hand_confirm(hid, prof["id"], num if isinstance(num, int) and not isinstance(num, bool) else -1) \
        if re.fullmatch(r"[0-9a-f]{16}", hid) else None
    if not st:
        raise HTTPException(404, "abgelaufen")
    guard.log("handoff_" + ("ok" if st == "ok" else "wrong"), uid=prof["id"], name=prof["name"])
    return {"state": st}


@router.post("/api/handoff/claim")
async def handoff_claim(request: Request):
    """The phone that scanned the computer's code: it gets a number to show (no login yet)."""
    _hand_on()
    guard.check(request)
    guard.limit(request, "pair")
    body = await join._json(request)
    got = hand_claim(body.get("code"), request.headers.get("user-agent", ""))
    if not got:
        guard.failed(request, None, what="handoff_code")
        raise HTTPException(400, "Der Code ist abgelaufen oder schon benutzt. Am Rechner einen neuen holen.")
    return got


@router.post("/api/handoff/finish")
async def handoff_finish(request: Request):
    """The phone asks whether the computer picked its number; then it is signed in."""
    _hand_on()
    guard.limit(request, "handoff")
    body = await join._json(request)
    uid = hand_finish(body.get("code"), body.get("wait"))
    if uid == "wait":
        return {"wait": True}
    u = next((u for u in profiles._load()["users"] if u["id"] == uid), None) if uid else None
    if not u:
        raise HTTPException(410, "Nicht bestätigt. Am Rechner einen neuen Code holen.")
    r = Response(json.dumps({"ok": True, "name": u["name"]}), media_type="application/json")
    r.set_cookie(profiles.COOKIE, profiles._cookie_value(u, agent=request.headers.get("user-agent", "")),
                 max_age=profiles.session_secs(), httponly=True, samesite="lax")
    guard.log("handoff_login", uid=uid, name=u["name"], ip=guard.client_ip(request))
    return r
