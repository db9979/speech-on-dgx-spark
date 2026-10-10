"""Where room mode listens right now (V01.0.207, plan plaene/raummodus-anzeige.md).

Every device in room mode is in one list: a browser page (it says when it starts, gives a sign of life every
minute and says when it stops; without a sign of life for ALIVE seconds it drops out) and an own speaker
(esp32.py adds and removes it; a speaker that waits for its next wake word is shown as waiting). The list
holds only where and how long: the device's name, kind, since, until, who it listens to and the trial;
never what was heard. It lives in memory only; after a restart the pages add themselves again with their
next sign of life.

Who sees it:
    the profile itself     a strip on every page, Ich → Raum-Modus "Gerade aktiv" (+15/+30 min, Beenden)
    its iPhone app         with the profile's switch app_room: a line in the chat, the widget, Live Activity
    Home Assistant         with a room key of the profile (scope "room", only when the admin allows chat.room_ha)
    the admin              Zustand → "Hört gerade zu" with "Alle beenden", a mark in Personen und Geräte

Ending is allowed to all of them, because it only means less listening. Extending only in the profile's own
browser login (a lost phone or a Home Assistant key can never make it listen longer). Starting stays where it
was: at the device ("Raummodus an", the switch "Raum") or for a speaker in Ich → Lautsprecher.

With the profile's switch room_tell a note goes out (push.send, one target) when a speaker starts room mode by
voice, i.e. when somebody else in the house may have started it; not in quiet hours, at most once per speaker
per hour. The profile's history (users/<id>/room-history.json, last HIST_MAX times within HIST_DAYS days)
keeps when and where, how it ended and how many sentences it heard, said and overheard; never text.
"""
import asyncio
import json
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import profiles
import features
from core import assistant, auth, browser_profile, own_profile, secret_profile

router = APIRouter()

clock = time.time            # tests set their own clock
ALIVE = 180                  # a page without a sign of life for this long has stopped (closed, phone locked)
MINS = (15, 30, 60, 120, 240)
LONGEST = 240 * 60           # never longer than this from now, also when extended
EXTEND = (15, 30, 60)
PER_PROFILE = 8              # browser pages of one profile in room mode at once
TOTAL = 50                   # entries at most (pages and speakers of everybody)
ENDED_KEEP = 600             # a page ended from elsewhere learns it with its next request within this time
TELL_GAP = 3600              # a note for the same speaker at most this often
HIST_MAX, HIST_DAYS = 20, 14
NAME_MAX = 40
WHY = {   # how a room ended: shown in the history, never free text
    "time": "Zeit um", "voice": "„Raummodus aus“", "here": "am Gerät beendet", "panel": "im Panel beendet",
    "iphone": "in der iPhone-App beendet", "ha": "von Home Assistant beendet", "admin": "vom Admin beendet",
    "lost": "Gerät nicht mehr erreichbar", "off": "ausgeschaltet", "far": "von einem anderen Gerät beendet",
}

ACTIVE = {}                  # (uid, rid) -> entry
_ENDED = {}                  # (uid, rid) -> (time, why): pages told to stop with their next request
_TOLD = {}                   # (uid, device) -> time of the last note


def enabled():
    return features.admin_on("room")


def ha_on():
    """The admin allows Home Assistant to read the list with a room key (chat.room_ha, off by default)."""
    return features.admin_on("roomha")


def _gate(uid):
    return ha_on()


profiles.ROOM_GATE[0] = _gate


def clean_name(x, fallback="Browser"):
    name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(x or "")).strip()[:NAME_MAX]
    return name or fallback


# ---------------------------------------------------------------- the list
def _view(e, admin=False):
    out = {"key": e["key"], "kind": e["kind"], "name": e["name"], "since": int(e["since"] * 1000),
           "until": int(e["until"] * 1000), "voices": e.get("voices", "all"), "probe": bool(e.get("probe"))}
    if e.get("device"):
        out["device"] = e["device"]
    if admin:
        out["profile"] = (profiles.by_id(e["uid"]) or {}).get("name", "?")
        out["uid"] = e["uid"]
    return out


def sweep():
    """Pages without a sign of life drop out; old end marks and notes are forgotten."""
    now = clock()
    for k, e in list(ACTIVE.items()):
        if e["kind"] == "browser" and now - e["seen"] > ALIVE:
            ACTIVE.pop(k, None)
            history(e, "lost")
            print(f"room: page {e['name']} gave no sign of life, dropped from the list", flush=True)
        elif now > e["until"] + ALIVE:
            ACTIVE.pop(k, None)
            history(e, "time")
    for k in [k for k, (t, _) in _ENDED.items() if now - t > ENDED_KEEP]:
        _ENDED.pop(k, None)
    if len(_TOLD) > 500:
        _TOLD.clear()


def add(uid, rid, kind, name, until, device="", voices="all", probe=False, ctl=None, source=""):
    """Puts a device into the list (again). Returns the entry. A speaker started by voice may send a note."""
    sweep()
    now = clock()
    old = ACTIVE.get((uid, rid))
    if old is None:
        if kind == "browser" and sum(1 for e in ACTIVE.values() if e["uid"] == uid and e["kind"] == "browser") >= PER_PROFILE:
            raise HTTPException(429, "Zu viele Geräte dieses Profils im Raum-Modus.")
        if len(ACTIVE) >= TOTAL:
            raise HTTPException(429, "Zu viele Geräte im Raum-Modus.")
    e = old or {"key": secrets.token_hex(6), "uid": uid, "rid": rid, "since": now, "said": 0}
    e.update(kind=kind, name=clean_name(name), until=min(float(until), now + LONGEST), device=device,
             voices=voices if voices in ("all", "tv", "known") else "all", probe=bool(probe), seen=now, ctl=ctl)
    ACTIVE[(uid, rid)] = e
    _ENDED.pop((uid, rid), None)
    if old is None:
        print(f"room: listed {kind} {e['name']}", flush=True)
        if source == "voice" and kind == "speaker":
            try:
                asyncio.get_running_loop().create_task(tell(uid, device, e["name"], int(round((e["until"] - now) / 60))))
            except RuntimeError:
                pass
    return e


def alive(uid, rid):
    e = ACTIVE.get((uid, rid))
    if e:
        e["seen"] = clock()
    return e


def ended(uid, rid):
    """The reason when this page was ended from elsewhere (it then stops), else ""."""
    x = _ENDED.pop((uid, rid), None)
    return x[1] if x else ""


def remove(uid, rid, why, r=None):
    """Takes a device off the list when its room mode ends; r is room.py's state of that room (for the counts)."""
    e = ACTIVE.pop((uid, rid), None)
    if e:
        history(e, why, r)
    return e


def mine(uid):
    sweep()
    return sorted((_view(e) for e in ACTIVE.values() if e["uid"] == uid), key=lambda x: x["since"])


def everybody():
    sweep()
    return sorted((_view(e, admin=True) for e in ACTIVE.values()), key=lambda x: (x["profile"].lower(), x["since"]))


def count(uid):
    sweep()
    return sum(1 for e in ACTIVE.values() if e["uid"] == uid)


def devices_listening():
    sweep()
    return {e["device"] for e in ACTIVE.values() if e.get("device")}


def _waiting(uid=None):
    """Speakers whose switch "Raum" waits for their next wake word (esp32.py)."""
    try:
        import esp32
        return [w for w in esp32.room_waiting() if uid is None or w["uid"] == uid]
    except Exception:
        return []


def _find(key, uid=None):
    sweep()
    return next((e for e in ACTIVE.values() if e["key"] == key and (uid is None or e["uid"] == uid)), None)


async def end(key, why, uid=None):
    """Ends one room (or one waiting speaker). False when there is none (or not of this profile)."""
    if key.startswith("w_"):
        w = next((w for w in _waiting(uid) if w["key"] == key), None)
        if not w:
            return False
        import esp32
        esp32.room_cancel_wait(w["device"])
        print(f"room: waiting speaker {w['name']} will not start ({why})", flush=True)
        return True
    e = _find(key, uid)
    if not e:
        return False
    if e["kind"] == "speaker" and e.get("ctl") is not None:
        await e["ctl"].room_end(f"ended ({why})", code=why)
    import room
    r = room.ROOMS.pop((e["uid"], e["rid"]), None)
    if (e["uid"], e["rid"]) in ACTIVE:
        remove(e["uid"], e["rid"], why, r)
    if e["kind"] == "browser":
        _ENDED[(e["uid"], e["rid"])] = (clock(), why)
    print(f"room: {e['kind']} {e['name']} ended ({why})", flush=True)
    return True


async def end_all(why, uid=None):
    n = 0
    for e in [e for e in list(ACTIVE.values()) if uid is None or e["uid"] == uid]:
        n += await end(e["key"], why, e["uid"])
    for w in _waiting(uid):
        n += await end(w["key"], why, w["uid"])
    return n


def extend(key, mins, uid):
    e = _find(key, uid)
    if not e:
        return None
    now = clock()
    e["until"] = min(max(e["until"], now) + mins * 60, now + LONGEST)
    if e["kind"] == "speaker" and e.get("ctl") is not None and getattr(e["ctl"], "room", None):
        e["ctl"].room["until"] = e["until"]
    print(f"room: {e['kind']} {e['name']} extended by {mins} min", flush=True)
    return e


# ---------------------------------------------------------------- a note when a speaker starts by voice
async def tell(uid, device, name, mins):
    import room
    if not profiles.settings(uid).get("room_tell") or room.night(uid):
        return False
    now = clock()
    if now - _TOLD.get((uid, device), -1e9) < TELL_GAP:
        return False
    _TOLD[(uid, device)] = now
    import push
    try:
        n = await push.send(uid, "🎙 Spark", f"{name} hört jetzt {mins} Minuten zu (Raum-Modus). Beenden: Ich → Raum-Modus.",
                            tag="room", private=False)
    except Exception as e:
        print("room: note failed:", type(e).__name__, flush=True)
        return False
    print(f"room: note about {name} sent to {n} device(s)", flush=True)
    return bool(n)


# ---------------------------------------------------------------- the history (no text)
def _hist_file(uid):
    return profiles._path(uid, "room-history.json")


def load_history(uid):
    try:
        with open(_hist_file(uid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = []
    now = clock()
    return [x for x in (d if isinstance(d, list) else []) if isinstance(x, dict) and now - float(x.get("end") or 0) < HIST_DAYS * 86400][-HIST_MAX:]


def history(e, why, r=None):
    uid = e["uid"]
    if not re.fullmatch(r"u_[0-9a-f]{12}", str(uid)) or uid not in profiles.user_ids():
        return
    c = (r or {}).get("count") or {}
    item = {"name": e["name"], "kind": e["kind"], "start": int(e["since"]), "end": int(clock()), "why": why if why in WHY else "off",
            "heard": int(c.get("heard") or 0), "ignored": int(c.get("ignored") or 0), "said": len((r or {}).get("done") or [])}
    with profiles._lock:
        profiles._write(_hist_file(uid), (load_history(uid) + [item])[-HIST_MAX:])


# ---------------------------------------------------------------- API
def _on():
    if not enabled():
        raise HTTPException(403, "room mode is turned off")


async def _body(request, limit=2048):
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(413, "too large")
    try:
        b = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    if not isinstance(b, dict):
        raise HTTPException(400, "invalid JSON")
    return b


def _rid(b):
    rid = str(b.get("room") or "")
    if not re.fullmatch(r"[A-Za-z0-9]{6,32}", rid):
        raise HTTPException(400, "room id is required")
    return rid


def _key(b):
    key = str(b.get("key") or "")
    if not re.fullmatch(r"(?:w_)?[A-Za-z0-9_\-]{6,40}", key):
        raise HTTPException(400, "key is required")
    return key


def _who(request):
    """Who ends a room: the iPhone app, Home Assistant (room key) or the panel."""
    scope = profiles.key_scope(request)
    return {"app": "iphone", "room": "ha"}.get(scope, "panel")


def _may_see(request, uid):
    scope = profiles.key_scope(request)
    if scope == "app" and not profiles.settings(uid).get("app_room"):
        raise HTTPException(403, "room mode is not shown in the app (Ich -> iPhone-App)")


def _name_of(request, b, uid):
    dev = profiles.device(request)
    if dev:
        return next((x["name"] for x in profiles.own_devices(uid) if x["id"] == dev["id"]), "Gerät")
    return clean_name(b.get("name"))


@router.post("/api/room/start", dependencies=[Depends(assistant), Depends(_on)])
async def api_start(request: Request, prof=Depends(own_profile)):
    """A page starts room mode: it is listed with its name and end."""
    guard.limit(request, "room", prof["id"])
    b = await _body(request)
    mins = b.get("mins") if b.get("mins") in MINS else 30
    e = add(prof["id"], _rid(b), "browser", _name_of(request, b, prof["id"]), clock() + mins * 60,
            voices=b.get("voices"), probe=b.get("probe"))
    return {"key": e["key"], "until": int(e["until"] * 1000)}


@router.post("/api/room/alive", dependencies=[Depends(assistant), Depends(_on)])
async def api_alive(request: Request, prof=Depends(own_profile)):
    """A page's sign of life: tells it its end (maybe extended elsewhere), or that it was ended."""
    guard.limit(request, "room", prof["id"])
    import room
    b = await _body(request)
    uid, rid = prof["id"], _rid(b)
    why = ended(uid, rid)
    if why:
        return {"end": True, "why": why}
    e = alive(uid, rid)
    if e is None:   # the Spark was restarted: the page adds itself again with the end it knows
        try:
            left = max(60.0, min(float(b.get("left") or 0), LONGEST))
        except (TypeError, ValueError):
            left = 60.0
        e = add(uid, rid, "browser", _name_of(request, b, uid), clock() + left, voices=b.get("voices"), probe=b.get("probe"))
    return {"key": e["key"], "until": int(e["until"] * 1000), "quiet": room.night(uid)}


@router.get("/api/room/active", dependencies=[Depends(assistant)])
def api_active(request: Request, prof=Depends(own_profile)):
    """Where the profile's devices listen right now (also the iPhone app and Home Assistant)."""
    if not enabled():
        return {"on": False, "rooms": [], "waiting": [], "count": 0}
    guard.limit(request, "room", prof["id"])
    _may_see(request, prof["id"])
    rooms = mine(prof["id"])
    waiting = [{k: w[k] for k in ("key", "name", "device")} for w in _waiting(prof["id"])]
    first = rooms[0] if rooms else None
    # the plain fields are for Home Assistant's REST sensor (state: count, attributes: first room)
    return {"on": True, "rooms": rooms, "waiting": waiting, "count": len(rooms),
            "first": first["name"] if first else "", "first_until": first["until"] if first else None}


@router.post("/api/room/end", dependencies=[Depends(assistant)])
async def api_end(request: Request, prof=Depends(own_profile)):
    """Ends one room of the profile ({"key"}) or all of them ({"all": true}). Allowed to the app and the room key."""
    guard.limit(request, "room", prof["id"])
    _may_see(request, prof["id"])
    b = await _body(request)
    why = _who(request)
    if b.get("all") is True:
        return {"ended": await end_all(why, prof["id"]), "rooms": mine(prof["id"])}
    if not await end(_key(b), why, prof["id"]):
        raise HTTPException(404, "no such room")
    return {"ended": 1, "rooms": mine(prof["id"])}


@router.post("/api/room/extend", dependencies=[Depends(assistant), Depends(_on)])
async def api_extend(request: Request, prof=Depends(browser_profile)):
    """Longer: only in the profile's own browser login, never longer than 4 hours from now."""
    guard.limit(request, "room", prof["id"])
    b = await _body(request)
    if b.get("mins") not in EXTEND:
        raise HTTPException(400, "mins: 15, 30 or 60")
    if not extend(_key(b), b["mins"], prof["id"]):
        raise HTTPException(404, "no such room")
    return {"rooms": mine(prof["id"])}


@router.get("/api/room/history", dependencies=[Depends(assistant)])
def api_history(prof=Depends(browser_profile)):
    return {"items": list(reversed(load_history(prof["id"]))), "why": WHY}


# Home Assistant: a key of its own (scope "room") that can only read this list and end rooms
def _ha_keys(uid):
    return [x for x in profiles._load()["devices"] if x.get("user") == uid and x.get("scope") == "room"]


@router.get("/api/profile/room/ha", dependencies=[Depends(assistant)])
def api_ha_get(prof=Depends(browser_profile)):
    last = profiles.seen()
    return {"allowed": ha_on(), "keys": [{"id": x["id"], "name": x["name"], "created": x.get("created"),
                                          "last": (last.get(x["id"]) or {}).get("t")} for x in _ha_keys(prof["id"])]}


@router.post("/api/profile/room/ha", dependencies=[Depends(assistant)])
async def api_ha_new(request: Request, prof=Depends(secret_profile)):
    """A new room key for Home Assistant (shown once). The old one stops working."""
    if not ha_on():
        raise HTTPException(403, "Home Assistant darf den Raum-Modus nicht lesen (Admin: Funktionen → Raum-Modus).")
    guard.limit(request, "room", prof["id"])
    for x in _ha_keys(prof["id"]):
        profiles.delete_device(x["id"])
    token = profiles.add_device("Home Assistant (Raum-Modus)", prof["id"], scope="room")
    print("room: Home Assistant key made for", prof["name"], flush=True)
    return {"token": token}


@router.delete("/api/profile/room/ha", dependencies=[Depends(assistant)])
def api_ha_delete(prof=Depends(browser_profile)):
    for x in _ha_keys(prof["id"]):
        profiles.delete_device(x["id"])
    return {"ok": True}


# the admin
@router.get("/api/admin/rooms", dependencies=[Depends(auth)])
def api_admin_rooms():
    if not enabled():
        return {"on": False, "rooms": [], "waiting": []}
    waiting = [{"key": w["key"], "name": w["name"], "profile": (profiles.by_id(w["uid"]) or {}).get("name", "?")} for w in _waiting()]
    return {"on": True, "rooms": everybody(), "waiting": waiting}


@router.post("/api/admin/rooms/end", dependencies=[Depends(auth)])
async def api_admin_end(request: Request):
    """Ends one room or all of them (e.g. when guests come). Ending only means less: no fresh code needed."""
    guard.limit(request, "room", admin=True)
    b = await _body(request)
    if b.get("all") is True:
        n = await end_all("admin")
    else:
        n = int(await end(_key(b), "admin"))
        if not n:
            raise HTTPException(404, "no such room")
    guard.log("room_end", ip=guard.client_ip(request), count=n)
    return {"ended": n, "rooms": everybody()}
