"""One description per function (plan „Vereinheitlichen“, V01.0.267).

Every function the admin can switch is written down here once: its name on every page, its group,
the admin switches it needs (and the functions it builds on), the profile's own switch, whether
guests may ever use it and the Ich page it belongs to. The modules ask `admin_on`, `profile_on` and
`allowed` here instead of each building "admin on and profile on" itself, and the panel, the iPhone
app and the search read `/api/features` instead of keeping their own lists.

The stored names stay as they are (config.json chat.*, users/<id>/settings.json), so nothing has to
move: this table only knows both. The fixed protection rules (secrets never spoken, voice priority,
the owner's voice at a shared speaker) are not switches and stay where they are.
"""
import json
import os
import re
import time
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
import profiles
from common import load_config
from core import assistant, auth

DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.default.json")

# groups as on the Funktionen page (guides.js GGROUPS)
GROUPS = (("talk", "Gespräch", "Conversation"), ("data", "Wissen und Gedächtnis", "Knowledge and memory"),
          ("day", "Alltag", "Everyday"), ("post", "Post und Kontakte", "Mail and contacts"),
          ("home", "Zuhause", "Home"), ("go", "Unterwegs und Geräte", "On the go and devices"),
          ("sec", "Sicherheit", "Security"))


class Feature(NamedTuple):
    key: str
    de: str
    en: str
    group: str
    admin: tuple            # chat.* switches that must all be on
    profile: str = ""       # the profile's own switch in settings.json ("" = none: the admin's switch is enough)
    guests: bool = False    # may guests (no profile) ever use it
    parent: str = ""        # the function it builds on (its switch must be on too)
    me: str = ""            # the Ich page (tab id) where the profile sets it up
    guide: str = ""         # guides.js id


F = Feature
FEATURES = (
    # conversation
    F("search", "Websuche", "Web search", "talk", ("search",), guests=True, guide="search"),
    F("wiki", "Wikipedia direkt", "Wikipedia straight away", "talk", ("wiki",), "wiki_on", me="setbox", guide="wiki"),
    F("kiwix", "Eigenes Kiwix-Archiv", "Own Kiwix archive", "talk", ("kiwix",), "kiwix_on", me="setbox", guide="kiwix"),
    F("lokal", "Erst lokal suchen", "Look locally first", "talk", ("local_first",), "local_first", me="setbox", guide="lokal"),
    F("roles", "Rollen per Sprache", "Roles by voice", "talk", ("roles",), "roles_on", me="setbox", guide="roles"),
    F("style", "Eigener Gesprächsstil", "Own conversation style", "talk", ("own_style",), me="setbox", guide="style"),
    F("follow", "Rückfrage ohne Weckwort", "Follow-up without wake word", "talk", ("follow_up",), me="setbox", guide="follow"),
    F("selfecho", "Eigene Stimme überhören", "Ignore my own voice", "talk", ("no_self_echo",), me="setbox", guide="selfecho"),
    F("fixes", "Aus Korrekturen lernen", "Learning from corrections", "talk", ("learn_fixes",), "fix_learn",
      parent="memory", me="setbox", guide="fixes"),
    F("images", "Bilder erkennen", "Picture recognition", "talk", ("images",), "images_on", me="setbox", guide="images"),
    F("toolthink", "Bei der Werkzeugwahl nachdenken", "Thinking while choosing tools", "talk", ("tool_thinking",), "tool_think",
      me="setbox", guide="toolthink"),
    F("routing", "Gezielte Werkzeugwahl", "Targeted tool choice", "talk", ("routing",), "route", me="setbox", guide="routing"),
    F("vorrang", "Vorrang für Personen", "Priority for people", "talk", ("person_priority",), guide="vorrang"),
    # knowledge and memory
    F("memory", "Gedächtnis", "Memory", "data", ("memory",), me="factbox", guide="memory"),
    F("history", "Frühere Gespräche", "Past conversations", "data", ("history",), me="setbox", guide="history"),
    F("documents", "Eigene Dokumente", "Own documents", "data", ("documents",), me="docbox", guide="documents"),
    F("docpics", "Bilder und Scans lesen", "Read pictures and scans", "data", ("doc_pictures",), "doc_pictures",
      parent="documents", me="docbox", guide="docpics"),
    F("docmeaning", "Bedeutungssuche", "Meaning search", "data", ("doc_semantic",), "doc_semantic",
      parent="documents", me="docbox", guide="docmeaning"),
    F("docfiles", "Originale aufbewahren", "Keep originals", "data", ("doc_originals",), "doc_originals",
      parent="documents", me="docbox", guide="docfiles"),
    F("docnight", "Lange Dokumente nachts lesen", "Read long documents at night", "data", ("doc_night",),
      parent="documents", me="docbox", guide="docnight"),
    F("docshared", "Gemeinsame Dokumente", "Shared documents", "data", ("doc_shared",), "doc_shared",
      parent="documents", me="docbox", guide="docshared"),
    F("remarkable", "reMarkable-Notizen", "reMarkable notes", "data", ("remarkable",), "rm_on",
      parent="docpics", me="rmbox", guide="remarkable"),
    F("rmsend", "Aufs reMarkable schicken", "Sending to the reMarkable", "data", ("remarkable_send",), "rm_send",
      parent="remarkable", me="rmbox", guide="rmsend"),
    F("docbrief", "Steckbrief und Tags", "Document card and tags", "data", ("doc_brief",), "doc_brief",
      parent="documents", me="docbox", guide="docbrief"),
    # everyday
    F("proactive", "Von selbst melden", "Speaking up by itself", "day", ("proactive",), "pro_on", me="probox", guide="proactive"),
    F("reminders", "Timer und Erinnerungen", "Timers and reminders", "day", ("reminders",), guests=True, guide="reminders"),
    F("tasks", "Aufgaben und Einkaufsliste", "Tasks and shopping list", "day", ("tasks",), "tasks_on", me="taskbox", guide="tasks"),
    F("mystatus", "Mein Zustand", "My status", "day", ("my_status",), "my_status", me="bgbox", guide="mystatus"),
    F("agent", "Agent-Funktionen", "Agent functions", "day", ("agent",), "agent_on", me="agentbox", guide="agent"),
    F("mcp", "Dienste per MCP", "Services over MCP", "day", ("agent_mcp",), parent="agent", guide="mcp"),
    F("messages", "Nachrichten an andere", "Messages to others", "day", ("messages",), "msg_on", me="msgbox", guide="messages"),
    F("messages_all", "Nachricht an alle", "Message to everybody", "day", ("messages_all",), parent="messages",
      me="msgbox", guide="messages_all"),
    F("messages_voice", "Sprachnachrichten", "Voice messages", "day", ("messages_voice",), parent="messages",
      me="msgbox", guide="messages_voice"),
    F("calendar", "Kalender", "Calendar", "day", ("calendar",), me="calbox", guide="calendar"),
    F("weather", "Wetter", "Weather", "day", ("weather",), "wx_on", me="wxbox", guide="weather"),
    # mail and contacts
    F("mail", "E-Mail lesen", "Reading e-mail", "post", ("mail",), me="mailbox", guide="mail"),
    F("tidy", "Postfach aufräumen", "Inbox tidying", "post", ("mail_tidy",), parent="mail", me="mailbox", guide="tidy"),
    F("parcels", "Pakete", "Parcels", "post", ("parcels",), "par_on", parent="mail", me="parbox", guide="parcels"),
    F("contacts", "Kontakte", "Contacts", "post", ("contacts",), "con_on", me="conbox", guide="contacts"),
    # home
    F("ha", "Home Assistant", "Home Assistant", "home", ("homeassistant",), me="habox", guide="ha"),
    F("room", "Raum-Modus", "Room mode", "home", ("room",), me="roombox", guide="room"),
    F("roomtv", "Fernsehstimmen überhören", "Ignore TV voices", "home", ("room_voices",), parent="room", me="roombox", guide="roomtv"),
    F("roomha", "Raum-Modus für Home Assistant", "Room mode for Home Assistant", "home", ("room_ha",), parent="room",
      me="roombox", guide="roomha"),
    F("esp32", "Eigene Lautsprecher (ESP32)", "Own speakers (ESP32)", "home", ("esp32",), "esp_on", me="espbox", guide="esp32"),
    F("roomfar", "Raum-Modus aus der Ferne starten", "Start room mode from afar", "home", ("room_remote", "esp32"), "room_remote",
      parent="room", me="roombox", guide="roomfar"),
    F("messages_announce", "Durchsagen auf Lautsprechern", "Announcements on speakers", "home", ("messages_announce",),
      "msg_announce", parent="messages", me="msgbox", guide="messages_announce"),
    F("wyoming", "Home Assistant Assist (Wyoming)", "Home Assistant Assist (Wyoming)", "home", ("wyoming",), guide="wyoming"),
    # on the go and devices
    F("transit", "Bus und Bahn", "Bus and train", "go", ("transit",), "transit_on", me="trbox", guide="transit"),
    F("telegram", "Telegram", "Telegram", "go", ("telegram",), me="tgbox", guide="telegram"),
    F("pebble", "Pebble-Uhr", "Pebble watch", "go", ("pebble",), "pebble_on", me="pebbox", guide="pebblepair"),
    F("iphone", "iPhone-App", "iPhone app", "go", ("iphone",), "app_on", me="appbox", guide="iphone"),
    F("iphonepush", "Push an die iPhone-App", "Push to the iPhone app", "go", ("iphone_push",), "app_push", parent="iphone",
      me="appbox", guide="iphonepush"),
    F("iphonepanel", "Panel-Bereiche in der iPhone-App", "Panel areas in the iPhone app", "go", ("iphone_panel",),
      parent="iphone", me="appbox", guide="iphonepanel"),
    F("iphoneupdate", "Spark-Update über die iPhone-App", "Spark update from the iPhone app", "go", ("iphone_update",),
      parent="iphone", guide="iphoneupdate"),
    # security
    F("speaker", "Sprechererkennung", "Speaker recognition", "sec", ("speaker_id",), me="voicebox", guide="speaker"),
    F("mfa", "Zweiter Anmeldeschritt", "Second sign-in step", "sec", ("mfa",), me="secbox", guide="mfa"),
)
BY_KEY = {f.key: f for f in FEATURES}
profiles.NO_PRESET.update(f.profile for f in FEATURES if f.profile)

# Spark-wide conditions besides the switches (an address that must be set), registered by the module
# that knows them, so this file imports none of them: key -> function(chat config) -> bool
READY = {}
# extra per-profile conditions given by the admin (the agent level): key -> function(uid) -> bool
GRANTED = {}
# the second step a profile still owes before using a function (join.py, new profiles by invitation):
# function(uid, key) -> bool, set by join.py
DUTY = None

# chat.* switches that are no function a profile uses (how the Spark itself works)
SPARK_ONLY = {"public", "thinking", "prompt_cache", "answer_check", "datetime", "face_life"}
# names for the Spark-wide switches that are no function of their own (the app's Funktionen page shows them under "Spark")
SPARK_NAMES = {"public": ("Gastzugang", "Guest access"), "thinking": ("Vorher nachdenken", "Think first"),
               "prompt_cache": ("Schneller Antwortbeginn", "Faster first words"),
               "answer_check": ("Antworten prüfen", "Check answers"), "datetime": ("Datum und Uhrzeit mitgeben", "Pass date and time"),
               "face_life": ("Gesicht zeigt, was es tut", "Face shows what it does")}


def switch_names(keys):
    """For the app (GET /api/admin/switches): a name per admin switch and the groups in menu order, from this
    table, so the app keeps no list of its own. A switch shared by several functions takes the first one's name."""
    names, groups = {}, {g: [] for g, _, _ in GROUPS}
    for f in FEATURES:
        k = f.admin[0]
        if k in keys and k not in names:
            names[k] = [f.de, f.en]
            groups[f.group].append(k)
    for k, (de, en) in SPARK_NAMES.items():
        if k in keys and k not in names:
            names[k] = [de, en]
    return names, [{"key": g, "name": [de, en], "switches": groups[g]} for g, de, en in GROUPS if groups[g]]


def _defaults():
    try:
        with open(DEFAULTS) as f:
            return json.load(f).get("chat", {})
    except (OSError, ValueError):
        return {}


_DEF = _defaults()


def chat_cfg():
    """The chat section; common.load_config fills every missing key with the shipped default."""
    return load_config().get("chat", {})


def _switch(c, k):
    return c.get(k, _DEF.get(k, False)) is True


def admin_on(key, c=None):
    """The Spark allows it: its switches, the ones of the function it builds on, and what must be set up."""
    f = BY_KEY[key]
    c = chat_cfg() if c is None else c
    if not all(_switch(c, k) for k in f.admin):
        return False
    if f.parent and not admin_on(f.parent, c):
        return False
    ready = READY.get(key)
    return bool(ready(c)) if ready else True


def profile_on(key, uid, s=None):
    """The profile's own switch (True when the function has none). Never from the admin's presets."""
    f = BY_KEY[key]
    if not uid:
        return False
    if f.profile:
        s = profiles.settings(uid) if s is None else s
        if s.get(f.profile) is not True:
            return False
    grant = GRANTED.get(key)
    return bool(grant(uid)) if grant else True


def reason(key, uid, c=None, s=None):
    """Why it cannot be used: "spark" (admin switch), "guest", "profile" (own switch), "mfa" (the second
    step first, join.py) or None."""
    if not admin_on(key, c):
        return "spark"
    if not uid:
        return None if BY_KEY[key].guests else "guest"
    if not profile_on(key, uid, s):
        return "profile"
    return "mfa" if DUTY and DUTY(uid, key) else None


def allowed(key, uid, c=None, s=None):
    return reason(key, uid, c, s) is None


def count(uid, c=None):
    """(on, of) for Personen und Geräte: of the functions with an own switch the Spark allows, how many are on for uid."""
    c = chat_cfg() if c is None else c
    s = profiles.settings(uid)
    mine = [f for f in FEATURES if f.profile and admin_on(f.key, c)]
    return sum(1 for f in mine if s.get(f.profile) is True), len(mine)


def guests(c=None):
    """What guests get: the guest access switch and how many functions they could use with it."""
    c = chat_cfg() if c is None else c
    return {"public": _switch(c, "public"), "features": sum(1 for f in FEATURES if f.guests and admin_on(f.key, c))}


WHY = {"spark": ("Vom Admin ausgeschaltet", "Switched off by the admin"),
       "guest": ("Nur mit Profil", "Only with a profile"),
       "profile": ("Bei dir aus", "Off for you"),
       "mfa": ("Erst den zweiten Anmeldeschritt einrichten (Ich → Sicherheit)", "Set up the second sign-in step first (Me → Security)")}


def state(uid, c=None):
    """Every function with what the Spark, the profile and guests may: for Ich, the app and the search.
    Guests see only the functions guests can use."""
    c = chat_cfg() if c is None else c
    s = profiles.settings(uid) if uid else {}
    out = []
    for f in FEATURES:
        if not uid and not f.guests:
            continue
        why = reason(f.key, uid, c, s)
        out.append({"key": f.key, "name": [f.de, f.en], "group": f.group, "spark": admin_on(f.key, c),
                    "own": f.profile or None, "mine": (s.get(f.profile) is True) if uid and f.profile else None,
                    "can": why is None, "why": why, "guests": f.guests, "parent": f.parent or None,
                    "me": f.me or None, "guide": f.guide or None})
    return out


router = APIRouter()


@router.get("/api/features", dependencies=[Depends(assistant)])
def features_list(request: Request):
    """What may be used here and why not: one list for Ich, the app and the search."""
    prof = profiles.current(request)
    guard.limit(request, "features", prof and prof["id"])
    return {"groups": [{"key": k, "name": [de, en]} for k, de, en in GROUPS],
            "features": state(prof["id"] if prof else None), "why": WHY}


# ---------------------------------------------------------------- Funktionen → "Wer darf was" (admin)
SEEN = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "features-seen.json")
_UID = re.compile(r"u_[0-9a-f]{12}")


def _seen(c):
    """When each function was first on on this Spark: "Neu, noch nie an" lists the others."""
    try:
        with open(SEEN) as f:
            d = json.load(f)
        d = {k: int(v) for k, v in d.items() if k in BY_KEY and isinstance(v, (int, float))} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    new = {f.key: int(time.time()) for f in FEATURES if f.key not in d and admin_on(f.key, c)}
    if new:
        d.update(new)
        try:
            os.makedirs(os.path.dirname(SEEN), exist_ok=True)
            tmp = SEEN + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f)
            os.replace(tmp, SEEN)
        except OSError:
            pass
    return d


def new_profile(uid):
    """A new profile gets the functions the admin chose for new profiles (chat.new_profile_on)."""
    keys = [k for k in chat_cfg().get("new_profile_on", []) if k in BY_KEY and BY_KEY[k].profile]
    if keys:
        profiles.save_settings(uid, {BY_KEY[k].profile: True for k in keys})


def matrix():
    c = chat_cfg()
    seen = _seen(c)
    users = profiles.names()
    s = {u["id"]: profiles.settings(u["id"]) for u in users}
    import admin
    import coadmin
    switchable = set(admin.app_switches())   # what /api/admin/switches may change (not public, mfa, iphone …)
    rows, new = [], set(c.get("new_profile_on", []))
    for f in FEATURES:
        rows.append({"key": f.key, "name": [f.de, f.en], "group": f.group, "switch": f.admin[0], "spark": admin_on(f.key, c),
                     "own": _switch(c, f.admin[0]), "switchable": f.admin[0] in switchable, "parent": f.parent or None, "guests": f.guests, "seen": f.key in seen,
                     "profile": f.profile or None, "guide": f.guide, "new": f.key in new if f.profile else None,
                     "cells": {u["id"]: s[u["id"]].get(f.profile) is True for u in users} if f.profile else None})
    return {"groups": [{"key": k, "name": [de, en]} for k, de, en in GROUPS], "features": rows,
            "profiles": [{"id": u["id"], "name": u["name"], "role": coadmin.role(u["id"]) if coadmin.on() else ""} for u in users],
            "public": _switch(c, "public"), "why": WHY}


@router.get("/api/admin/features", dependencies=[Depends(auth)])
def admin_features(request: Request):
    guard.limit(request, "features", admin=True)
    return matrix()


@router.put("/api/admin/features/{key}/profiles/{uid}", dependencies=[Depends(auth)])
async def admin_feature_profile(key: str, uid: str, request: Request):
    """The admin switches a function for one profile (its own switch, which the profile sees under Ich)."""
    guard.limit(request, "features", admin=True)
    f = BY_KEY.get(key)
    if not f or not f.profile or not _UID.fullmatch(uid) or not profiles.by_id(uid):
        raise HTTPException(404, "no such function or profile")
    raw = await request.body()
    if len(raw) > 256:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    on = body.get("on") if isinstance(body, dict) else None
    if not isinstance(on, bool):
        raise HTTPException(400, "on: true or false")
    import admin
    admin._no_admin_profile(request, uid)
    profiles.save_settings(uid, {f.profile: on})
    elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
    by = "main" if not elev else elev["id"]
    guard.log("feature_profile", uid=uid, by=by,
              detail=f"{f.de} für {profiles.by_id(uid)['name']} {'an' if on else 'aus'}")
    return {"key": key, "uid": uid, "on": on}


@router.put("/api/admin/features/{key}/new", dependencies=[Depends(auth)])
async def admin_feature_new(key: str, request: Request):
    """On for every new profile (chat.new_profile_on); profiles that exist keep their own switch."""
    guard.limit(request, "features", admin=True)
    f = BY_KEY.get(key)
    if not f or not f.profile:
        raise HTTPException(404, "no such function with an own switch")
    raw = await request.body()
    if len(raw) > 256:
        raise HTTPException(413, "too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    on = body.get("on") if isinstance(body, dict) else None
    if not isinstance(on, bool):
        raise HTTPException(400, "on: true or false")
    import admin
    new = admin.get_config()
    keys = [k for k in new["chat"].get("new_profile_on", []) if k != key] + ([key] if on else [])
    new["chat"]["new_profile_on"] = [k for k in BY_KEY if k in keys]
    admin.validate(new)
    tmp = admin.CONFIG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(new, fh, indent=2)
    os.replace(tmp, admin.CONFIG_PATH)
    elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
    guard.log("feature_profile", by="main" if not elev else elev["id"], detail=f"{f.de} für neue Profile {'an' if on else 'aus'}")
    return {"key": key, "on": on}
