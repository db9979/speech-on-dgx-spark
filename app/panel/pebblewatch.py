"""Pairing the Pebble watch app "Spark" (pebble/ in the repo) with a profile.

The profile's own browser login (with its second step, when it has one) asks for a setup code: a line
"<address>#pebble=<code>" that the person copies into the watch app's settings on the phone. The phone
sends the code to /api/pebble/pair and gets its own device key with scope "watch". The code is random
(144 bits), works once and for CODE_SECONDS; only its hash is kept, in memory.

A key with scope "watch" only asks (profiles.WATCH_PREFIX: /api/watch/...) and only while the admin
switch chat.pebble is on and the profile is not blocked. Removing the watch in the panel stops its key.
Keys made by hand in the admin's device list keep working as before.
"""
import json
import os
import re
import time
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request

import geraeteupdate
import guard
import kopplung
import profiles
import features
from account import browser_profile
from common import load_config
import core
from core import assistant, confirm_code, own_profile

router = APIRouter()

CODE_SECONDS = 600
MAX_PENDING = 20          # open codes on the whole Spark
PER_PROFILE = 3           # open codes of one profile (a new one replaces the oldest)
MAX_WATCHES = 5           # paired watches per profile
MAX_BODY = 1024

_codes = kopplung.Codes(kopplung.link_code, kopplung.link_form, CODE_SECONDS, MAX_PENDING, PER_PROFILE)
new_code, take_code, _pending = _codes.new, _codes.take, _codes.pending   # one-time pairing codes (kopplung.py)


def admin_on():
    return features.admin_on("pebble")


def profile_on(uid):
    return features.profile_on("pebble", uid)


def allowed(uid):
    return features.allowed("pebble", uid)


profiles.WATCH_GATE[0] = allowed


APP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pebble", "speech-spark.pbw")
_app_cache = {}


def app_version():
    """versionLabel of the watch app the panel serves ("1.4.0"), "" when it is missing."""
    try:
        mtime = os.path.getmtime(APP_FILE)
    except OSError:
        return ""
    if _app_cache.get("mtime") != mtime:
        try:
            with zipfile.ZipFile(APP_FILE) as z:
                label = str(json.loads(z.read("appinfo.json")).get("versionLabel", ""))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            label = ""
        _app_cache.update(mtime=mtime, label=label if re.fullmatch(r"\d{1,3}(\.\d{1,3}){0,2}", label) else "")
    return _app_cache["label"]


def newer_app(have):
    """True when the panel serves a newer watch app than the one asking (the phone sends its version)."""
    served = app_version()
    if not served or not isinstance(have, str) or not re.fullmatch(r"\d{1,3}(\.\d{1,3}){0,2}", have):
        return False
    return geraeteupdate.newer(served, have)


def watches(uid):
    return [x for x in profiles.own_devices(uid) if x.get("watch")]


def _base(body):
    """The address the phone reaches the Spark at. http is fine here: the Pebble app does not trust
    the self-signed certificate, so at home it uses the plain panel port."""
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Adresse: http(s)://name oder http(s)://name:port, ohne Pfad.")
    return base


def _outside(body):
    """The second address for on the road (Zuhause und unterwegs), optional: https only (the watch key goes there
    through the internet), like the first without a path."""
    out = str(body.get("out") or "").strip().rstrip("/")
    if out and not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?", out):
        raise HTTPException(400, "Adresse unterwegs: nur https://name oder https://name:port, ohne Pfad.")
    return out


def _on(request: Request, prof=Depends(browser_profile)):
    """Pairing and managing watches: only from the profile's own browser login, never with a device key."""
    if not admin_on():
        raise HTTPException(403, "the Pebble watch is turned off")
    if request.method not in ("GET", "HEAD", "DELETE") and features.blocked("pebble", prof["id"]):   # own data: seen and deleted also while blocked
        raise HTTPException(403, "blocked for this profile by the admin (Personen und Geräte → Gesperrte Funktionen)")
    return prof


@router.get("/api/profile/pebble", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    uid = prof["id"]
    return {"enabled": admin_on(), "on": profile_on(uid), "watches": watches(uid),
            "minutes": CODE_SECONDS // 60, "app": app_version(),
            # what the watch does besides asking (each its own admin switch): Ich → Pebble-Uhr shows only those
            "quick_on": features.allowed("pebbleschnell", uid), "quick": quick_of(uid), "remind_on": remind_on(uid), "follow_on": features.allowed("pebblefolge", uid),
            "max": QUICK_MAX, "len": QUICK_LEN}


@router.get("/api/profile/pebble/qr", dependencies=[Depends(assistant)])
def profile_qr(base: str, prof=Depends(_on)):
    """QR code of the app file's address, to scan with the phone that is paired with the watch."""
    url = _base({"base": base}) + "/pebble/speech-spark.pbw"
    try:
        import mfa
        svg = mfa._qr_svg(url)
    except Exception:
        svg = ""
    return {"url": url, "qr": svg}


@router.post("/api/profile/pebble/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(_on)):
    """A one-time setup line for the watch app's settings on the phone."""
    body = await core.json_body(request, MAX_BODY, lenient=True)
    if not profile_on(prof["id"]):
        raise HTTPException(403, "Die Pebble-Uhr hat der Admin für dein Profil gesperrt (Personen und Geräte → Gesperrte Funktionen).")
    if len(watches(prof["id"])) >= MAX_WATCHES:
        raise HTTPException(409, f"Schon {MAX_WATCHES} Uhren gekoppelt. Erst eine entfernen.")
    base = _base(body)
    out = _outside(body)
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
    code = new_code(prof["id"])
    print("pebble: setup code made for", profiles.log_name(prof) + (" | unterwegs" if out else ""), flush=True)
    return {"setup": f"{base}#pebble={code}" + (f"&aussen={out}" if out else ""), "minutes": CODE_SECONDS // 60}


@router.delete("/api/profile/pebble/{did}", dependencies=[Depends(assistant)])
def profile_remove(did: str, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in watches(prof["id"])):
        raise HTTPException(404, "no such watch")
    _remove(did)
    print("pebble: watch removed for", profiles.log_name(prof), flush=True)
    return profile_get(prof)


def _remove(did):
    profiles.delete_device(did)
    _live_mark("Eingang", "Pebble-Uhr entfernt")


def _clear(uid):
    for x in watches(uid):
        _remove(x["id"])


# own data for Ich while the admin blocks the Pebble watch for the profile (features.OWN): its paired watches
features.OWN["pebble"] = (lambda uid: len(watches(uid)), _clear)


@router.post("/api/pebble/pair")
async def watch_pair(request: Request):
    """The phone's first contact: the one-time code gives the watch app its own key (scope "watch")."""
    guard.limit(request, "pair")
    body = await core.json_body(request, MAX_BODY, lenient=True)
    uid = take_code(body.get("code"))
    prof = uid and profiles.by_id(uid)
    if not prof or not allowed(uid):
        raise HTTPException(400, "Der Einrichtungscode passt nicht oder ist abgelaufen. Im Panel einen neuen holen.")
    if len(watches(uid)) >= MAX_WATCHES:
        raise HTTPException(409, "Zu viele Uhren für dieses Profil.")
    token = profiles.add_device("Pebble", uid, scope="watch")
    print("pebble: watch paired for", profiles.log_name(prof), flush=True)
    _live_mark("Eingang", "Pebble-Uhr gekoppelt")
    return {"token": token, "profile": prof["name"], "face": profiles.face_of(uid, load_config().get("chat", {}))}


# ---------------------------------------------------------------- more on the watch (plan pebble-ideen/plan.md)
# Schnellbefehle: the profile's own fixed sentences (settings peb_cmds), sent from the watch as a normal question.
# Erinnerungen am Handgelenk: the next AGENDA_MAX reminders go to the watch as wake-ups, so they ring without the
# phone; the watch takes the one it rang (one ring for the profile), push waits WATCH_GRACE for it first.
QUICK_MAX, QUICK_LEN = 12, 60
AGENDA_MAX = 8            # wake-ups a Pebble app may hold
AGENDA_DAYS = 30
TEXT_LEN = 60             # reminder text on the watch
WATCH_GRACE = 90 * 1000   # ms push waits for a watch that holds the reminder (push.due_reminders)
HELD_TTL = 24 * 3600      # a watch that has not synced for a day holds nothing any more
SNOOZE_MS = 10 * 60 * 1000
PLUS_MS = 60 * 1000
ACTS = ("played", "snooze", "stop", "plus", "cancel")
_held = {}                # uid -> (time of the sync, ids on the watch); memory only


def remind_on(uid):
    """Reminders on the watch need their own switch and the reminders themselves (also not blocked for the profile)."""
    return all(features.allowed(k, uid) for k in ("pebbleerinnern", "reminders"))


def quick_of(uid):
    v = profiles.settings(uid).get("peb_cmds")
    return [x for x in v if isinstance(x, str)][:QUICK_MAX] if isinstance(v, list) else []


def _short(text, n=TEXT_LEN):
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))).strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def agenda(uid):
    """The next reminders and timers for the watch: id, due and made in epoch seconds, a short text, repeating."""
    now = time.time() * 1000
    items = [x for x in profiles.reminders(uid) if now - 60_000 < x.get("due", 0) < now + AGENDA_DAYS * 86400_000]
    return [{"id": x["id"], "due": int(x["due"] // 1000), "made": int(x.get("made", 0) // 1000),
             "text": _short(x.get("text")), "rep": 1 if x.get("every") in profiles.REPEATS else 0}
            for x in sorted(items, key=lambda x: x["due"])[:AGENDA_MAX]]


def held(uid):
    """Ids of the reminders a watch of this profile holds as wake-ups (synced within HELD_TTL)."""
    at, ids = _held.get(uid, (0, frozenset()))
    return ids if time.time() - at < HELD_TTL else frozenset()


def _hold(uid, items):
    _held[uid] = (time.time(), frozenset(x["id"] for x in items))
    if len(_held) > 1000:
        _held.clear()


def _watch_prof(request):
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "device key (X-Speech-Device) or profile login required")
    return prof


@router.get("/api/watch/sync", dependencies=[Depends(assistant)])
def watch_sync(request: Request):
    """What the watch keeps for itself: the quick commands, the next reminders (or None while off), follow-ups on."""
    prof = _watch_prof(request)
    guard.limit(request, "watchsync", prof["id"])
    uid = prof["id"]
    quick = quick_of(uid) if features.allowed("pebbleschnell", uid) else []
    items = agenda(uid) if remind_on(uid) else None
    if items is not None:
        _hold(uid, items)
    else:
        _held.pop(uid, None)
    print(f"watch: sync | {len(quick)} Schnellbefehle · {len(items) if items is not None else 'aus'} Erinnerungen"
          f" | {profiles.log_name(prof)}", flush=True)
    return {"quick": quick, "agenda": items, "follow": features.allowed("pebblefolge", uid)}


@router.post("/api/watch/reminder", dependencies=[Depends(assistant)])
async def watch_reminder(request: Request):
    """The watch rang a reminder (played), or the person pressed Später (snooze), Serie beenden (stop), +1 Minute
    (plus) or stopped a timer (cancel). Returns the new list for the watch."""
    prof = _watch_prof(request)
    guard.limit(request, "watchrem", prof["id"])
    uid = prof["id"]
    if not remind_on(uid):
        print(f"watch: reminder refused | why off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, "reminders on the watch are turned off")
    body = await core.json_body(request, MAX_BODY, lenient=True)
    rid, act = str(body.get("id", ""))[:16], body.get("act")
    if not re.fullmatch(r"[0-9a-f]{1,16}", rid) or act not in ACTS:
        print(f"watch: reminder refused | why invalid | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, "id and act (played, snooze, stop, plus, cancel) are required")
    now = time.time() * 1000
    item = next((x for x in profiles.reminders(uid) if x.get("id") == rid), None)
    done = False
    if act == "cancel":   # a timer stopped on the watch before it rang
        done = profiles.remove_reminders(uid, {rid}) > 0
    elif act == "plus":
        if item:   # a running timer one minute longer (a new id, like every changed reminder)
            profiles.remove_reminders(uid, {rid})
            profiles.add_reminder(uid, item["text"], max(item["due"], now) + PLUS_MS, item.get("every", ""), item.get("made"))
            done = True
    else:
        taken = profiles.take_reminder(uid, rid, now + 60_000) if item else None
        if act == "snooze":
            text = (taken or item or {}).get("text") or _short(body.get("text"), 200)
            if text:   # also when another device took it already: the watch still knows the text
                profiles.add_reminder(uid, text, now + SNOOZE_MS)
                done = True
        elif act == "stop":
            if taken and taken.get("every") in profiles.REPEATS:   # the series ends: its next time goes as well
                nxt = profiles.next_due(taken, profiles.settings(uid).get("tz", ""))
                profiles.remove_reminders(uid, {x["id"] for x in profiles.reminders(uid)
                                                if x.get("text") == taken["text"] and x.get("every") == taken.get("every")
                                                and x.get("due") == nxt})
            done = taken is not None
        else:
            done = taken is not None
    print(f"watch: reminder {act} | {'ok' if done else 'nothing to do'} | {profiles.log_name(prof)}", flush=True)
    items = agenda(uid)
    _hold(uid, items)
    return {"ok": done, "agenda": items}


@router.put("/api/profile/pebble/quick", dependencies=[Depends(assistant)])
async def profile_quick(request: Request, prof=Depends(_on)):
    """The profile's own quick commands for the watch (Ich → Pebble-Uhr), one line each."""
    guard.limit(request, "watchsync", prof["id"])
    if not features.allowed("pebbleschnell", prof["id"]):
        print(f"watch: quick commands refused | why off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, "quick commands for the watch are turned off")
    body = await core.json_body(request, 4096, lenient=True)
    raw = body.get("quick")
    if not isinstance(raw, list):
        print(f"watch: quick commands refused | why invalid | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, "quick: a list of sentences")
    lines = []
    for x in raw:
        x = _short(x, 10_000)
        if x and x not in lines:
            lines.append(x)
    if len(lines) > QUICK_MAX or any(len(x) > QUICK_LEN for x in lines):
        print(f"watch: quick commands refused | why too long | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, f"Höchstens {QUICK_MAX} Befehle mit je {QUICK_LEN} Zeichen.")
    profiles.save_settings(prof["id"], {"peb_cmds": lines})
    print(f"watch: quick commands saved | {len(lines)} | {profiles.log_name(prof)}", flush=True)
    return profile_get(prof)


# own data while blocked (features.OWN): the quick commands of the profile
features.OWN["pebbleschnell"] = (lambda uid: len(quick_of(uid)), lambda uid: profiles.save_settings(uid, {"peb_cmds": []}))


def _live_mark(area, text):
    """Zustand → Live: a line under Ereignisse, fixed words only (never the profile's name)."""
    try:
        import live
        live.mark(area, text)
    except Exception:
        pass
