"""Meldung ans gerade genutzte Gerät (plan benachrichtigung-geraet, Dominik 2026-10-20 "ok", stage 1).

push.pick sends a note to one way of the profile. Before, that was the way it used last (profiles.LAST_USED, 12 h), which
also counted a page left open in the background and never the iPhone app. With the admin switch chat.note_device on, each
device says how long ago a person last touched it, and push.pick asks here first:

    1. a device that is in use right now (input less than ACTIVE seconds ago, its signal younger than FRESH): the one
       touched last
    2. none: the phone app at once (iPhone, else Android)
    3. no phone app: push.pick as before (Begleiter, Telegram, browser)

A way the profile chose for a kind of note (push.send to=, e.g. the Dienst-Wächter) still wins. Off: push.pick as before.

The signals carry only a state, never content: the browser and the Android app (POST /api/zustellung/da with the seconds
since the last input, or "weg" when hidden), the iPhone app (the same, "0" in front, "weg" in the background) and the
Spark-Begleiter (its poll every POLL seconds with the computer's idle seconds). Each device says it for itself (P6 Gerät
statt Profil, review A-H5): one entry per way and device (profiles.geraet, for a page also its tab), so an idle second
window never outvotes the one in use and a hidden tab marks only itself away. Kept in memory only, at most MAX
profiles and DEVICES_MAX devices each; a signal older than FRESH says nothing any more.

Stage 2 (Nachfassen und „gelesen überall“), same switch:

    4. a note that went to a device other than the phone app (push.send without to=) comes once more to the phone
       app after FOLLOW seconds (an urgent one after FOLLOW_URGENT: vorgaenge.ARTEN "dringend", the one list), unless
       it was seen: its Vorgang is no longer open (vorgaenge.seen, erledigt, später, weg) or a device it went to was
       touched after the note came (a browser: only the one with the subscription it went to, never another one).
       Never a third time; no phone app: nothing.
    5. a note about a Vorgang (vg) leaves the other devices once the Vorgang is no longer open: the Begleiter and the
       Android app no longer fetch it, pages and the iPhone app get the numbers back with their signal ("zu") and
       take the notification away. Opening a note says "gesehen" (field "gesehen" of the signal).

The notes waiting for a follow-up are kept in memory only (title and text at most KEEP seconds, like the boxes of
the Begleiter and the Android app).
"""
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from core import assistant, json_body, own_profile

router = APIRouter()

ACTIVE = 120        # s since the last input: the device counts as in use
FRESH = 90          # s: an older signal says nothing (pages and the iPhone say it every 60 s, the Begleiter every 30 s)
PHONES = ("app", "and")   # the fallback when no device is in use: the phone app at once
MAX = 1000          # profiles kept (in memory only)
DEVICES_MAX = 12    # devices (pages, apps, Begleiter) kept per profile: the one quiet longest goes
MAX_BODY = 256
IDLE_MAX = 7 * 86400
FOLLOW = 300        # s: a note nobody saw comes once more to the phone app (plan 2a)
FOLLOW_URGENT = 120  # s: the same for an urgent one (vorgaenge.ARTEN "dringend")
ART_BY_WHY = {"Erinnerung": "erinnerung"}   # notes without a Vorgang: their kind in vorgaenge.ARTEN
KEEP = 6 * 3600     # s: a sent note is remembered this long (follow-up, „gelesen überall“)
OUT_MAX = 30        # notes kept per profile
SEEN_MAX = 5        # Vorgang numbers per signal ("gesehen")
_lock = threading.Lock()
_sig = {}           # uid -> {(way, device): (time of the signal, time of the last input, gone, key)}
_out = {}           # uid -> [{"t", "way", "vg", "due", ...the note}] notes sent, for the follow-up and the clean-up
_today = {"day": "", "aktiv": 0, "handy": 0, "nachgefasst": 0}   # notes today (numbers for Zustand → Live)


def seen(uid, way, idle=0, gone=False, key="", now=None, dev=""):
    """A device of the profile said how long ago it was last touched (idle seconds) or that it is away (gone). dev:
    which device of that way (profiles.geraet, a page also with its tab): its own entry, never another's."""
    now = time.time() if now is None else now
    if way not in ("app", "and", "desk", "tg", "web") or not uid:
        return
    idle = max(0, min(int(idle or 0), IDLE_MAX))
    with _lock:
        if uid not in _sig and len(_sig) >= MAX:
            _sig.pop(min(_sig, key=lambda u: max((v[0] for v in _sig[u].values()), default=0)), None)
        mine = _sig.setdefault(uid, {})
        mine[(way, str(dev or "")[:64])] = (now, now - idle, bool(gone),
                                             key if re.fullmatch(r"[0-9a-f]{16}", key or "") else "")
        while len(mine) > DEVICES_MAX:
            mine.pop(min(mine, key=lambda d: mine[d][0]))
    if not gone and idle < ACTIVE:   # in use: read its services ahead (vorwaermen.ask, at most every WARM_AGAIN)
        import vorwaermen
        vorwaermen.ask(uid, now)


def in_use(uid, now=None):
    """[(way, key, time of the last input)] of the profile's devices in use right now, the one touched last first."""
    now = time.time() if now is None else now
    with _lock:
        sig = dict(_sig.get(uid, {}))
    out = [(w, k, t_in) for (w, _), (t, t_in, gone, k) in sig.items() if not gone and now - t < FRESH and now - t_in < ACTIVE]
    return sorted(out, key=lambda x: -x[2])


def pick(uid, have, now=None):
    """(way, key, why) for a note by the rules above, None to let push.pick go on as before. have: way -> set up."""
    if not features.allowed("notedevice", uid):
        return None
    # a browser counts only when it has a subscription itself (P1 Sicherheit, review A-H6): else the next device in use
    import push
    got = next(((w, k, "aktiv") for w, k, _ in in_use(uid, now) if have.get(w) and (w != "web" or push.has_sub(uid, k))),
               None)
    if got is None:
        got = next(((w, "", "handy") for w in PHONES if have.get(w)), None)
    if got is not None:
        _count(got[2])
        print(f"push: route {got[2]} {got[0]} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return got


def _count(what):
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _today["day"] != day:
            _today.update(day=day, aktiv=0, handy=0, nachgefasst=0)
        _today[what] += 1


# ---------------------------------------------------------------- stage 2: follow-up and „gelesen überall“
def sent(uid, ways, note, vg="", follow=True, now=None, keys=()):
    """push.send sent a note on ways; remembered when the switch is on. follow: push.send chose the way itself (no
    to=), so a note that did not go to the phone app may come there once more. note: title, body, tag, private,
    why, ref (what push.send needs again). keys: the browser subscriptions it went to (push.sub_id): only a touch
    there counts as seen."""
    if not features.allowed("notedevice", uid) or not ways:
        return
    now = time.time() if now is None else now
    wait = 0
    if follow and not set(ways) & set(PHONES):
        wait = FOLLOW_URGENT if _urgent(uid, vg, note.get("why", "")) else FOLLOW
    with _lock:
        box = [x for x in _out.get(uid, []) if now - x["t"] < KEEP]
        box.append(dict(note, t=now, way=ways[0], vg=vg, due=now + wait if wait else 0, keys=tuple(keys)[:5]))
        _out[uid] = box[-OUT_MAX:]


def _urgent(uid, vg, why):
    import vorgaenge
    art = _art(uid, vg) or ART_BY_WHY.get(why, "")
    return bool(vorgaenge.ARTEN.get(art, {}).get("dringend"))


def _art(uid, vg):
    import vorgaenge
    x = vorgaenge.find(uid, vg) if vg else None
    return x["art"] if x else ""


def _was_seen(uid, x):
    """The note was seen: its Vorgang is no longer open, or a device it went to was touched after it came: a browser
    only when it is the one with the subscription the note went to (another browser touched says nothing, review
    A-H5); the Begleiter and the apps show it on each of their devices of that way."""
    import vorgaenge
    v = vorgaenge.find(uid, x["vg"]) if x["vg"] else None
    if v is not None and v["zustand"] != "offen":
        return True
    keys = x.get("keys") or ()
    with _lock:
        sig = [s for (w, _), s in _sig.get(uid, {}).items() if w == x["way"] and (w != "web" or s[3] in keys)]
    return any(not s[2] and s[1] > x["t"] for s in sig)


async def follow(now=None):
    """Every minute (panel.every_minute): the notes whose wait is over and nobody saw come once to the phone app.
    One journal line per note: nachgefasst, gesehen or kein Handy."""
    import push
    now = time.time() if now is None else now
    with _lock:
        due = [(uid, x) for uid, box in _out.items() for x in box if x["due"] and x["due"] <= now]
        for _, x in due:
            x["due"] = 0          # never a third time
    n = 0
    for uid, x in due:
        who = profiles.log_name(profiles.by_id(uid))
        if not features.allowed("notedevice", uid):
            continue
        if _was_seen(uid, x):
            print(f"push: nachfassen nicht noetig, gesehen {x['way']} | {who}", flush=True)
            continue
        have = push._have(uid, x["private"])
        phone = next((w for w in PHONES if have.get(w)), "")
        if not phone:
            print(f"push: nachfassen ohne handy {x['way']} | {who}", flush=True)
            continue
        got = await push.send(uid, x["title"], x["body"], tag=x["tag"], private=x["private"], why=x["why"], to=phone,
                              ref=x["ref"], **({"vg": x["vg"]} if x["vg"] else {}))
        _count("nachgefasst")
        n += 1
        if x["vg"]:
            import vorgaenge
            vorgaenge.delivered(uid, x["vg"], phone, "nachgefasst")
        print(f"push: nachgefasst {x['way']} → {phone} | {got} device(s) | {who}", flush=True)
    return n


def closed(uid, now=None):
    """The Vorgang numbers of notes sent lately whose Vorgang is no longer open: the devices take them away."""
    import vorgaenge
    now = time.time() if now is None else now
    with _lock:
        vgs = {x["vg"] for x in _out.get(uid, []) if x["vg"] and now - x["t"] < KEEP}
    out = []
    for v in sorted(vgs):
        x = vorgaenge.find(uid, v)
        if x is None or x["zustand"] != "offen":
            out.append(v)
    return out


def seen_now(uid, ids, way):
    """A device opened notes about these Vorgänge: they count as seen everywhere (vorgaenge.seen)."""
    import vorgaenge
    if not features.allowed("vorgaenge", uid):
        return 0
    n = sum(1 for v in ids if vorgaenge.seen(uid, v, way))
    print(f"push: gesehen {n} {way} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return n


def for_live(now=None):
    """{"on", "devices", "aktiv", "handy"}: devices in use right now and notes routed today, numbers only."""
    now = time.time() if now is None else now
    with _lock:
        uids = list(_sig)
        day = dict(_today) if _today["day"] == time.strftime("%Y-%m-%d") else {"aktiv": 0, "handy": 0, "nachgefasst": 0}
        wait = sum(1 for box in _out.values() for x in box if x["due"])
    return {"on": features.admin_on("notedevice"), "devices": sum(len(in_use(u, now)) for u in uids),
            "aktiv": day["aktiv"], "handy": day["handy"], "nachgefasst": day["nachgefasst"], "warten": wait}


@router.post("/api/zustellung/da", dependencies=[Depends(assistant)])
async def api_da(request: Request, prof=Depends(own_profile)):
    """A page, the Android app or the iPhone app says: touched idle seconds ago, or away ("weg"), and which notes it
    opened ("gesehen": Vorgang numbers); "tab" names the page among the browser's open ones. Only for the own profile and only a state; {"on"} tells the page whether to
    keep saying it, "zu" the notes it may take away (their Vorgang is no longer open)."""
    guard.limit(request, "zustellung", prof["id"])
    body = await json_body(request, MAX_BODY, lenient=True)
    import android
    scope = profiles.key_scope(request)
    if scope == "app":
        way = "app"
    elif request.headers.get(profiles.DEVICE_HEADER) or request.scope.get("speech_profile"):
        raise HTTPException(403, "only pages and the apps")   # other keys (Begleiter, speakers) have their own ways
    else:
        way = "and" if android.from_app(request) else "web"
    idle, opened = body.get("idle", 0), body.get("gesehen", [])
    if not isinstance(idle, int) or isinstance(idle, bool):
        raise HTTPException(400, "idle is a number")
    import vorgaenge
    if not isinstance(opened, list) or len(opened) > SEEN_MAX or \
            not all(isinstance(v, str) and vorgaenge.ID.fullmatch(v) for v in opened):
        raise HTTPException(400, "gesehen: Vorgang numbers")
    if not features.allowed("notedevice", prof["id"]):
        return {"on": False}
    # this device only (P6): its key or login, and a page's tab (verlauf.js TAB), so another window never speaks for it
    tab = body.get("tab") if isinstance(body.get("tab"), str) and re.fullmatch(r"[a-z0-9]{1,12}", body["tab"]) else ""
    seen(prof["id"], way, idle, body.get("weg") is True, str(body.get("id") or "")[:16],
         dev=profiles.geraet(request) + (":" + tab if tab else ""))
    if opened:
        seen_now(prof["id"], opened, way)
    return {"on": True, "zu": closed(prof["id"])}
