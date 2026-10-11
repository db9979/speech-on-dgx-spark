"""Notaus (kill switch, plan plaene/notaus.md, V01.0.31x): three stages that stop the Spark from the outside in.

    1 "Außen zu"    nothing from the internet (reverse proxy, MCP from outside, Telegram), and the Spark itself
                    reaches nothing on the internet (netguard, web search, weather, transit, Wikipedia, parcels,
                    reMarkable, firmware and app downloads); the home network goes on as before
    2 "Hände weg"   stage 1, and no actions: smart home, mail changes, messages, reminders and appointments,
                    lists, reMarkable, MCP actions, memory; agent jobs are held, "Von selbst", briefings, mail
                    tidying and learning pause; the assistant still answers from what it knows and reads
    3 "Alles still" stage 2, and no conversation at all: chat, speech recognition, speakers, Wyoming, room mode,
                    the watch; the panel shows only the Notaus page (login, logs and lifting stay)

Triggering is easy and lifting is hard. Only admins (main admin, or a profile in its admin mode) see and
trigger it (Dominik 2026-10-10: it stops the Spark for everyone); a stage can only go up that way. Ordinary
profiles and guests see neither the button nor who or why, only that the Spark is stopped. Lifting (down to stage 1, or off) only by the main
admin or a profile in its admin mode (not the Verwalter role), in a browser in the home network, never from an
app key, with a fresh code (the main admin without a second step types the panel password again). The language
model, mail, web pages, documents, Home Assistant, Telegram or MCP can never trigger or lift it: nothing reads
text for it, the panel's own endpoints decide.

The stage survives a restart and an update (STATE/notaus.json). Way out without the panel:
sudo rm /var/lib/speech-spark/state/notaus.json (the panel reads the file anew on its next request).

What it held off is counted by kind only, in memory (Zustand → Notaus), never with contents.

"Mein Notaus" (V01.0.338, Dominik 2026-10-10 "3b"): every signed-in profile can stop its own part only. While it is
on, every way in of that profile is closed except the browser it was switched on in (device keys of the phone
apps, Siri, watch, speakers and Home Assistant, MCP keys and OAuth, Telegram, other browser logins), and nothing
is done in its name (actions, jobs, "Von selbst" and smart home notes). Reading stays: the profile's own browser
still talks with the Spark and may read its mail, calendar and memory. Lifting: the profile itself in a browser
with its PIN (and its code when its second step is on), or an admin. STATE/notaus-mine.json; a damaged file
holds every profile (a Notaus must never go away by a damaged file).
"""
import contextvars
import hashlib
import hmac
import ipaddress
import json
import os
import re
import threading
import time

import guard

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "notaus.json")
MINE_FILE = os.path.join(STATE, "notaus-mine.json")
KEYS_FILE = os.path.join(STATE, "notaus-keys.json")   # Home Assistant keys that can only trigger
MAX_KEYS = 5
LEVELS = (0, 1, 2, 3)
NAMES = {1: "Außen zu", 2: "Hände weg", 3: "Alles still"}
NAMES_EN = {1: "Outside closed", 2: "Hands off", 3: "All quiet"}
CHANNELS = ("panel", "app", "android", "telegram", "sprache", "esp32", "ha", "pebble", "waechter")
MAX_REASON = 120
MAX_HISTORY = 20

# the kinds "Mein Notaus" holds off for its profile (reading, the internet and the conversation go on)
PERSONAL = ("aktion", "auftrag", "auto")
# from which stage each kind of thing is held off
STAGE = {"aussen": 1, "internet": 1, "aktion": 2, "auftrag": 2, "auto": 2, "gespraech": 3}
# the rows of Zustand → Notaus, in this order (kind, German, English)
KINDS = (("aussen", "Zugriffe von außen (Internet, Proxy, MCP von außen)", "Access from outside (internet, proxy, MCP)"),
         ("internet", "Verbindungen ins Internet", "Connections to the internet"),
         ("aktion", "Aktionen (Home Assistant, Mail, Nachrichten, Termine, Listen)", "Actions (smart home, mail, messages, appointments, lists)"),
         ("auftrag", "Aufträge und Routinen", "Jobs and routines"),
         ("auto", "Von selbst, Briefings, Aufräumen, Lernen", "On its own, briefings, tidying, learning"),
         ("gespraech", "Gespräch, Spracherkennung, Lautsprecher", "Conversation, speech recognition, speakers"))

# Tools the model may not use from a stage on (chat_tools / chat_turn): stage 1 the ones that go to the internet
# by themselves (fixed services, not through netguard), stage 2 every tool that changes something.
INTERNET_TOOLS = {"web_search", "weather", "transit", "wikipedia", "article_more", "parcels", "read_page"}
# the to-do change of Home Assistant is decided in chat_tools (the same tool also reads)
BLOCKED = ("Not done: the Notaus (emergency stop) is on and holds this off. Tell the user exactly that in one "
           "sentence: the Notaus blocks it until an admin switches it off. Do not try again, do not offer a workaround.")

BLOCKED_MINE = ("Not done: the user's own Notaus (\"Mein Notaus\") is on and holds every action in their name off. "
                "Tell the user exactly that in one sentence: they can lift it under Ich → Sicherheit with their PIN. "
                "Do not try again, do not offer a workaround.")


def locked_tools(held, changes=(), mine=False):
    """The tool names the Notaus holds off at this stage: from 1 the ones that go to the internet by themselves,
    from 2 (or with the profile's own Notaus) every one that changes something (chat.LOCKED_OUTSIDE, mail
    changes, the extras' changing tools)."""
    out = set(INTERNET_TOOLS) if held >= 1 else set()
    if held >= 2 or mine:
        import chat
        out |= chat.LOCKED_OUTSIDE | set(changes) | {"mail_draft", "mail_tidy_propose"}
    return out


class NotausAktiv(ValueError):
    """Raised where an action would happen while the Notaus holds it off (the last line of defence; the tools
    are already locked before)."""


_lock = threading.Lock()
_cache = {"key": None, "state": None}
_counts = {}
_mine_cache = {"key": None, "d": None}
_mine_counts = {}
# the profile a request or turn acts for (set by the panel's middleware, chat_turn, the agent): the last line of
# defence (stop/refuse) holds its actions off without every sink knowing who it is for
ACTING = contextvars.ContextVar("notaus_acting", default="")
ALL = "*"     # a damaged notaus-mine.json: every profile counts as held


def _empty():
    return {"level": 0, "since": None, "by": "", "uid": "", "channel": "", "reason": "", "history": []}


def _clean(d):
    """The stored state, checked: a broken or foreign file counts as stage 0 only when it is missing; a file
    that is there but cannot be read counts as stage 3 (a Notaus must never go away by a damaged file)."""
    if not isinstance(d, dict):
        return dict(_empty(), level=3, reason="Notaus-Datei unlesbar")
    lvl = d.get("level")
    if not isinstance(lvl, int) or isinstance(lvl, bool) or lvl not in LEVELS:
        return dict(_empty(), level=3, reason="Notaus-Datei unlesbar")
    out = _empty()
    out["level"] = lvl
    out["since"] = int(d["since"]) if isinstance(d.get("since"), (int, float)) and not isinstance(d.get("since"), bool) else None
    for k, n in (("by", 60), ("uid", 20), ("channel", 20), ("reason", MAX_REASON)):
        out[k] = str(d.get(k) or "")[:n]
    if out["channel"] not in CHANNELS:
        out["channel"] = ""
    hist = d.get("history") if isinstance(d.get("history"), list) else []
    out["history"] = [h for h in hist if isinstance(h, dict)][-MAX_HISTORY:]
    return out


def state():
    """The current state (read anew when the file changed; a stat per call)."""
    try:
        st = os.stat(FILE)
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
    except FileNotFoundError:
        key = None
    except OSError:
        return dict(_empty(), level=3, reason="Notaus-Datei unlesbar")
    if key is None:
        return _empty()
    if _cache["key"] == key and _cache["state"] is not None:
        return _cache["state"]
    try:
        with open(FILE, encoding="utf-8") as f:
            d = _clean(json.load(f))
    except (OSError, ValueError):
        d = dict(_empty(), level=3, reason="Notaus-Datei unlesbar")
    _cache.update(key=key, state=d)
    return d


def level():
    return state()["level"]


def blocks(kind, uid=None):
    """True while the Notaus holds this kind of thing off (see STAGE), or the own Notaus of the profile it is
    for (uid, else the acting profile) holds a PERSONAL kind."""
    return level() >= STAGE[kind] or _mine_blocks(kind, uid)


def _mine_blocks(kind, uid=None):
    return kind in PERSONAL and own(uid if uid is not None else ACTING.get())


def refuse(kind, uid=None):
    """Like blocks(), and counts it when it holds something off (for Zustand → Notaus)."""
    if level() >= STAGE[kind]:
        with _lock:
            _counts[kind] = min(_counts.get(kind, 0) + 1, 10**9)
        return True
    if _mine_blocks(kind, uid):
        with _lock:
            _mine_counts[kind] = min(_mine_counts.get(kind, 0) + 1, 10**9)
        return True
    return False


def stop(kind, uid=None):
    """Raises NotausAktiv while the Notaus (or the profile's own) holds this kind off."""
    if refuse(kind, uid):
        what = dict((k, de) for k, de, _ in KINDS)[kind]
        if level() >= STAGE[kind]:
            raise NotausAktiv(f"Notaus Stufe {level()}: {what} gesperrt")
        raise NotausAktiv(f"Mein Notaus ist an: {what} gesperrt")


def why(uid, what):
    """A sentence for the person: which Notaus holds `what` off."""
    if level() >= 2 or not own(uid):
        return f"Der Notaus ist an: {what}, bis ein Admin ihn aufhebt."
    return f"Mein Notaus ist an: {what}, bis du ihn unter Ich → Sicherheit aufhebst."


# ---------------------------------------------------------------- Mein Notaus (one profile)
def acting(uid):
    """Marks the profile this request or task acts for (see ACTING)."""
    ACTING.set(str(uid or ""))


def mine():
    """{uid: {"since", "channel"}} of the profiles whose own Notaus is on; {ALL: …} for a damaged file."""
    try:
        st = os.stat(MINE_FILE)
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
    except FileNotFoundError:
        return {}
    except OSError:
        return {ALL: {"since": None, "channel": ""}}
    if _mine_cache["key"] == key and _mine_cache["d"] is not None:
        return _mine_cache["d"]
    try:
        with open(MINE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict) or not isinstance(raw.get("profiles"), dict):
            raise ValueError("form")
        d = {}
        for uid, v in list(raw["profiles"].items())[:500]:
            if isinstance(uid, str) and 0 < len(uid) <= 40 and isinstance(v, dict):
                since = v.get("since")
                d[uid] = {"since": int(since) if isinstance(since, (int, float)) and not isinstance(since, bool) else None,
                          "channel": str(v.get("channel") or "") if v.get("channel") in CHANNELS else ""}
    except (OSError, ValueError):
        d = {ALL: {"since": None, "channel": ""}}
    _mine_cache.update(key=key, d=d)
    return d


def own(uid):
    """True while this profile's own Notaus is on."""
    if not uid:
        return False
    m = mine()
    return bool(m) and (uid in m or ALL in m)


def _mine_write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = MINE_FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w", encoding="utf-8") as f:
        json.dump({"profiles": d}, f, ensure_ascii=False)
    os.replace(tmp, MINE_FILE)
    _mine_cache.update(key=None, d=None)


def mine_on(uid, name, channel, now=None):
    """Switches the profile's own Notaus on; False when it already was."""
    if not uid or channel not in CHANNELS:
        raise ValueError("profile and channel")
    now = int(time.time() if now is None else now)
    with _lock:
        cur = {k: v for k, v in mine().items() if k != ALL}
        if uid in cur:
            return False
        cur[uid] = {"since": now, "channel": channel}
        _mine_write(cur)
    guard.log("notaus_mine_on", who=str(name or "")[:60], uid=uid, detail=f"über {channel}")
    print(f"notaus: Mein Notaus an ({channel})", flush=True)
    _live(f"ein Profil schaltet Mein Notaus an über {channel}")
    return True


def mine_off(uid, by, admin=False):
    """Switches the profile's own Notaus off (the profile itself or an admin; checked by the endpoints). A damaged
    file (every profile held) only an admin clears, and then for all."""
    with _lock:
        cur = mine()
        if ALL in cur:
            if not admin:
                return False
            cur = {}
        elif uid not in cur:
            return False
        else:
            cur = {k: v for k, v in cur.items() if k != uid}
        if cur:
            _mine_write(cur)
        else:
            try:
                os.remove(MINE_FILE)
            except FileNotFoundError:
                pass
            _mine_cache.update(key=None, d=None)
    guard.log("notaus_mine_off", who=str(by or "")[:60], uid=uid)
    print("notaus: Mein Notaus aufgehoben", flush=True)
    _live("ein Profil hebt Mein Notaus auf")
    return True


def counts():
    with _lock:
        return {k: _counts.get(k, 0) for k, _, _ in KINDS}


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, FILE)
    _cache.update(key=None, state=None)


def clean_reason(text):
    text = " ".join(str(text or "").split())
    return "".join(c for c in text if c.isprintable())[:MAX_REASON]


def trigger(new, by, uid, channel, reason="", now=None):
    """Raises the stage to `new` (1..3). Returns (old, state); old == new level when nothing changed (a stage
    never goes down this way)."""
    if new not in (1, 2, 3):
        raise ValueError("Stufe 1, 2 oder 3")
    if channel not in CHANNELS:
        raise ValueError("unknown channel")
    now = int(time.time() if now is None else now)
    with _lock:
        cur = state()
        old = cur["level"]
        if new <= old:
            return old, cur
        d = dict(cur)
        d.update(level=new, since=now if not old else (cur["since"] or now), by=str(by or "")[:60], uid=str(uid or "")[:20],
                 channel=channel, reason=clean_reason(reason))
        d["history"] = (cur["history"] + [{"t": now, "from": old, "to": new, "by": d["by"], "channel": channel}])[-MAX_HISTORY:]
        if not old:
            _counts.clear()
        _write(d)
    guard.log("notaus_on", who=d["by"], uid=d["uid"] or None, detail=f"Stufe {old} → {new} über {channel}"
              + (f": {d['reason']}" if d["reason"] else ""))
    print(f"notaus: Stufe {old} -> {new} ({channel})", flush=True)
    _live(f"Stufe {old} → {new} über {channel}")
    return old, state()


def _live(text):
    """One line for Zustand → Live "Ereignisse": stage and channel only, never the reason or a name."""
    try:
        import live
        live.event("Notaus", text)
    except Exception:
        pass


def for_live():
    """What Zustand → Live and the monitor show: stage, since, channel and per kind held/count, no content."""
    s = state()
    lvl, cnt = s["level"], counts()
    m = mine()
    with _lock:
        mc = dict(_mine_counts)
    return {"level": lvl, "name": NAMES.get(lvl, ""), "since": s["since"] if lvl else None, "channel": s["channel"] if lvl else "",
            "kinds": [{"k": k, "de": de, "en": en, "from": STAGE[k], "n": cnt.get(k, 0)} for k, de, en in KINDS] if lvl else [],
            # Mein Notaus: how many profiles, and what it held off; never which profile
            "mine": {"n": len(m) if ALL not in m else -1, "held": sum(mc.values()) if m else 0}}


def lift(to, by, uid="", now=None):
    """Lowers the stage to `to` (0 or 1). Only the admin endpoint below calls this."""
    if to not in (0, 1):
        raise ValueError("nur auf Stufe 1 oder aus")
    now = int(time.time() if now is None else now)
    with _lock:
        cur = state()
        old = cur["level"]
        if to >= old:
            raise ValueError("Der Notaus steht nicht höher als das.")
        hist = (cur["history"] + [{"t": now, "from": old, "to": to, "by": str(by or "")[:60], "channel": "panel"}])[-MAX_HISTORY:]
        d = dict(cur, level=to, history=hist) if to else dict(_empty(), history=hist)
        _write(d)
    guard.log("notaus_off", who=str(by or "")[:60], uid=uid or None, detail=f"Stufe {old} → {to}")
    print(f"notaus: Stufe {old} -> {to} (aufgehoben)", flush=True)
    _live(f"Stufe {old} → {to}, aufgehoben")
    return old, state()


# ---------------------------------------------------------------- where a request comes from
_PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip")


def _private(text):
    try:
        ip = ipaddress.ip_address(str(text or "").split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback) and not ip.is_unspecified and not ip.is_link_local


def at_home(request):
    """The browser or device is in the home network. Through a reverse proxy only when the proxy is trusted
    (panel.trusted_proxies, or one on this host) and says the browser behind it is in the home network; a
    listed proxy without that, or forwarding headers from anyone else, count as outside."""
    peer = (request.client.host if request.client else "") or ""
    if not _private(peer):
        return False
    forwarded = any(request.headers.get(h) for h in _PROXY_HEADERS)
    if not forwarded:
        return peer not in guard._proxies()
    if not request.headers.get("x-forwarded-for") or not guard.forward_trusted(request):
        return False
    return _private(guard.client_ip(request))


# What still answers while the Notaus is on (everything else gets 503 with the stage):
#   from outside (stage 1 and up): the page and its files, the Notaus state and raising it
#   at home in stage 3 also: logins, the admin mode, whoami, lifting, and reading Zustand, the logs and Zustand → Live
PAGE = ("/", "/live", "/sw.js", "/manifest.webmanifest", "/favicon.ico", "/apple-touch-icon.png")
OUTSIDE_OK = ("/api/notaus",)
STILL_OK = ("/api/notaus", "/api/admin/notaus/off", "/api/whoami", "/api/login", "/api/logout", "/api/profile/login",
            "/api/profile/logout", "/api/admin/elevate", "/api/admin/elevate/end", "/api/admin/elevate/keep")
STILL_READ = ("/api/status", "/api/audit", "/api/admin/undo", "/api/admin/live", "/api/admin/live/monitors", "/api/live/state")
STILL_READ_PREFIX = ("/api/logs/",)


def _page(path):
    return path in PAGE or path.startswith("/static/")


def mine_gate(request):
    """Mein Notaus: a device key of a held profile gets nothing (the status aside), and the request's profile is
    marked as acting (ACTING) so the last line of defence knows whose action it would be. None or (503, detail)."""
    if not mine():
        return None
    import profiles
    if request.headers.get(profiles.DEVICE_HEADER):
        dev = profiles.device(request)
        if dev and own(dev["user"]):
            if request.url.path == "/api/notaus" and request.method == "GET":
                return None
            with _lock:
                _mine_counts["zugang"] = min(_mine_counts.get("zugang", 0) + 1, 10**9)
            return 503, "Mein Notaus ist an: dieser Zugang ist gesperrt, bis das Profil ihn im Browser aufhebt."
        return None
    try:
        prof = profiles.current(request)
    except Exception:
        prof = None
    if prof:
        acting(prof["id"])
    return None


def gate(request):
    """None when this request may go on, else (status, detail) for the answer."""
    lvl = level()
    if not lvl:
        return None
    path = request.url.path
    if _page(path):
        return None
    if not at_home(request):
        if path in OUTSIDE_OK:
            return None
        refuse("aussen")
        return 503, f"Notaus Stufe {lvl}: von außen gesperrt"
    if lvl < 3 or path in STILL_OK:
        return None
    if request.method == "GET" and (path in STILL_READ or path.startswith(STILL_READ_PREFIX)):
        return None
    refuse("gespraech")
    return 503, f"Notaus Stufe {lvl}: alles angehalten"


# ---------------------------------------------------------------- what happens right after a change
async def after_change(old, new, by, channel):
    """Holds what runs (agent jobs, speakers, room mode) and tells the admins; never raises."""
    if new >= 2 > old:
        try:
            import agent
            agent.notaus_hold()
        except Exception as e:
            print("notaus: agent", type(e).__name__, flush=True)
        try:
            import hamelden
            hamelden.stop_all()      # the live connections to Home Assistant (rules wait until it is lifted)
        except Exception as e:
            print("notaus: ha rules", type(e).__name__, flush=True)
    if new >= 3 > old:
        try:
            import esp32
            await esp32.notaus_close()
        except Exception as e:
            print("notaus: speakers", type(e).__name__, flush=True)
        try:
            import roomlive
            await roomlive.end_all("notaus")
        except Exception as e:
            print("notaus: room mode", type(e).__name__, flush=True)
    try:
        await tell_admins(old, new, by, channel)
    except Exception as e:
        print("notaus: push", type(e).__name__, flush=True)


def admin_uids():
    """The profiles that hear about a Notaus: the one chosen for admin notes, and every owner and Mit-Admin."""
    import coadmin
    uids = []
    first = coadmin.notify_uid()
    if first:
        uids.append(first)
    for u in coadmin.listing()["users"]:
        if u["role"] in ("owner", "coadmin") and u["id"] not in uids:
            uids.append(u["id"])
    return uids[:6]


async def tell_admins(old, new, by, channel):
    import push
    if new > old:
        title = f"Notaus Stufe {new}: {NAMES[new]}"
        body = f"Ausgelöst von {by or 'jemandem'} über {channel or 'das Panel'}. Aufheben nur im Heimnetz mit Admin-Code."
    else:
        title = "Notaus aufgehoben" if not new else f"Notaus zurück auf Stufe {new}"
        body = f"Von {by or 'einem Admin'}."
    for uid in admin_uids():
        try:
            await push.send(uid, title, body, tag="notaus", private=False)
        except Exception as e:
            print("notaus: push to an admin", type(e).__name__, flush=True)


# ---------------------------------------------------------------- API
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from core import admin_code_fresh, auth  # noqa: E402
from fastapi.security import HTTPBasicCredentials  # noqa: E402

router = APIRouter()
MAX_BODY = 2048


def _settings():
    from common import load_config
    return load_config().get("panel", {})


def _caller(request, creds=None):
    """(name, uid, admin, profile, channel) of who sends this request, or None. Only logins and the phone apps'
    keys count: no guests, no speaker, Siri or watch keys, no MCP, no Telegram (they come in a later step)."""
    import coadmin
    import core
    import profiles
    if request.scope.get("speech_mcp") or request.scope.get("speech_profile"):
        return None
    dev = profiles.device(request) if request.headers.get(profiles.DEVICE_HEADER) else None
    # the Spark-Begleiter's key only for its own "Mein Notaus" button (begleiter.py), never for anything else
    if dev is not None and dev["scope"] != "app" and not (dev["scope"] == "desk" and request.url.path == "/api/desk/notaus"):
        return None
    import android
    # the Android app (its page or its quick settings tile, both with the page's login) is named as such
    where = "app" if dev else "android" if android.from_app(request) else "panel"
    if not dev and core.is_main_admin(request, creds) and core.password_set():
        return "Admin", "", True, None, where
    elev = coadmin.session(request)
    if elev:          # a profile in its admin mode, in the browser or in the phone app (coadmin holds it there)
        return elev["name"], elev["id"], True, None, where
    prof = profiles.current(request)
    if not prof:
        return None
    return prof["name"], prof["id"], False, prof, where


def _lift_how(request, creds=None):
    """"code" / "password" when this request may lift the Notaus, else "" (main admin or a profile in its admin
    mode that is not a Verwalter, a browser login, in the home network)."""
    import coadmin
    import core
    import mfa
    import profiles
    if request.headers.get(profiles.DEVICE_HEADER) or request.headers.get("authorization") or not at_home(request):
        return ""
    if core.password_set() and core._admin_cookie_age(request) is not None:
        return "code" if mfa.enabled(mfa.ADMIN) else "password"
    elev = coadmin.session(request)
    if elev and elev.get("role") in ("owner", "coadmin") and not str(elev.get("via", "")).startswith("d_"):
        return "code"
    return ""


def view(request, creds=None):
    s = state()
    out = {"level": s["level"], "outside": not at_home(request)}
    who = _caller(request, creds)
    if not who:
        # a phone app's key of a held profile: it may still learn that its own Notaus is on (the app says so)
        import profiles
        dev = profiles.device(request) if request.headers.get(profiles.DEVICE_HEADER) else None
        if dev and dev.get("scope") == "app" and own(dev["user"]):
            out["mine"] = {"on": True, "since": (mine().get(dev["user"]) or {}).get("since"), "lift": False}
        return out
    me = _mine_uid(request, who)
    if me:           # Mein Notaus of this profile (the admin mode's profile, or the profile beside the main admin)
        m = mine()
        on = own(me)
        out["mine"] = {"on": on, "since": (m.get(me) or {}).get("since") if on else None,
                       "lift": bool(on and _mine_lift_ok(request) and (ALL not in m or me in m))}
    if not who[2]:
        return out    # ordinary profiles: only that the Spark is stopped, not who, why or how to change it
    out.update(may=True, lift=_lift_how(request, creds), names=NAMES)
    out["mine_list"] = _mine_list()
    if s["level"]:
        out.update(since=s["since"], by=s["by"], channel=s["channel"], reason=s["reason"], counts=counts(),
                   kinds=[{"k": k, "de": de, "en": en, "from": STAGE[k]} for k, de, en in KINDS])
    return out


def _mine_uid(request, who):
    """The profile whose own Notaus this request is about: the caller's, or the signed-in profile next to the
    main admin's login."""
    if who and who[1]:
        return who[1]
    import profiles
    try:
        prof = profiles.current(request)
    except Exception:
        prof = None
    return prof["id"] if prof else ""


def _mine_lift_ok(request):
    """The profile lifts its own Notaus only in a browser (no device key, no Authorization header)."""
    import profiles
    return not request.headers.get(profiles.DEVICE_HEADER) and not request.headers.get("authorization")


def _mine_list():
    """For admins: the profiles whose own Notaus is on (name, since), never why."""
    import profiles
    m = mine()
    if ALL in m:
        return [{"uid": "", "name": "alle (Datei unlesbar)", "since": None}]
    names = {u["id"]: u["name"] for u in profiles._load()["users"]}
    return [{"uid": uid, "name": names.get(uid, "?"), "since": v["since"]} for uid, v in m.items()][:50]


async def _body(request):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "too large")
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "JSON expected")
    if not isinstance(d, dict):
        raise HTTPException(400, "JSON object expected")
    return d


def _creds(request):
    """HTTP Basic is never a way in here (scripts would bypass the browser rules); only the cookie counts."""
    return None


@router.get("/api/notaus")
def get_state(request: Request):
    guard.limit(request, "notaus")
    return view(request, _creds(request))


@router.post("/api/notaus")
async def post_trigger(request: Request):
    who = _caller(request, _creds(request))
    if not who:
        raise HTTPException(401, "login required")
    name, uid, admin, prof, channel = who
    guard.limit(request, "notausset", uid=uid or None, admin=admin)
    if not admin:
        raise HTTPException(403, "Den Notaus dürfen nur Admins auslösen.")
    body = await _body(request)
    lvl = body.get("level")
    if not isinstance(lvl, int) or isinstance(lvl, bool) or lvl not in (1, 2, 3):
        raise HTTPException(400, "Stufe 1, 2 oder 3")
    old, s = trigger(lvl, name, uid, channel, body.get("reason", ""))
    if old >= lvl:
        raise HTTPException(409, f"Der Notaus steht schon auf Stufe {old}.")
    await after_change(old, lvl, name, channel)
    return view(request, _creds(request))


@router.post("/api/admin/notaus/off")
async def post_lift(request: Request):
    import agent
    import core
    how = _lift_how(request, _creds(request))
    if not how:
        raise HTTPException(403, "Aufheben nur als Admin, im Browser, im Heimnetz.")
    guard.limit(request, "notausoff", admin=True)
    body = await _body(request)
    to = body.get("to")
    if not isinstance(to, int) or isinstance(to, bool) or to not in (0, 1):
        raise HTTPException(400, "to: 0 oder 1")
    if to >= level():
        raise HTTPException(409, "Der Notaus steht nicht höher als das.")
    main = core.password_set() and core._admin_cookie_age(request) is not None
    if how == "password":
        guard.check(request, guard.ADMIN)
        if not core.check_password(str(body.get("password") or "")[:200]):
            guard.failed(request, guard.ADMIN, what="notaus_password")
            raise HTTPException(401, "Falsches Passwort.")
    elif main:
        import mfa
        await core.confirm_code(request, mfa.ADMIN, guard.ADMIN, fresh=True)
    else:
        import coadmin
        elev = coadmin.session(request)
        await core.confirm_code(request, elev["id"], elev["name"], fresh=True)
    import coadmin
    elev = None if main else coadmin.session(request)
    by, uid = ("Admin", "") if main else (elev["name"], elev["id"])
    old, s = lift(to, by, uid)
    if old >= 2 > to:
        agent.notaus_release(resume=body.get("resume") is True)
    try:
        await tell_admins(old, to, by, "panel")
    except Exception as e:
        print("notaus: push", type(e).__name__, flush=True)
    return view(request, _creds(request))


# ---------------------------------------------------------------- Mein Notaus endpoints
@router.post("/api/notaus/mine")
async def post_mine(request: Request):
    """The profile stops its own part: every way in but this browser, every action in its name."""
    import agent
    import profiles
    who = _caller(request, _creds(request))
    uid = _mine_uid(request, who)
    if not who or not uid:
        raise HTTPException(401, "login required")
    name, _, admin, prof, channel = who
    if not who[1]:      # the main admin's login beside a profile: the profile's name
        name = (profiles.current(request) or {}).get("name", name)
    guard.limit(request, "notausset", uid=uid, admin=admin)
    await _body(request)
    if not mine_on(uid, name, channel):
        raise HTTPException(409, "Mein Notaus ist schon an.")
    agent.notaus_hold(only=uid)
    try:
        import hamelden
        hamelden.stop(uid)
    except Exception as e:
        print("notaus: ha rules", type(e).__name__, flush=True)
    # every other browser login ends; this browser gets a fresh one and stays signed in (as "logout everywhere")
    profiles.end_sessions(uid)
    out = view(request, _creds(request))
    out["mine"] = {"on": True, "since": int(time.time()), "lift": _mine_lift_ok(request)}
    r = JSONResponse(out, headers={"Cache-Control": "no-store"})
    if not request.headers.get(profiles.DEVICE_HEADER):
        u = next((u for u in profiles._load()["users"] if u["id"] == uid), None)
        if u:
            r.set_cookie(profiles.COOKIE, profiles._cookie_value(u, agent=request.headers.get("user-agent", "")),
                         max_age=profiles.session_secs(), httponly=True, samesite="lax")
    try:
        await tell_admins_mine(name, True)
    except Exception as e:
        print("notaus: push", type(e).__name__, flush=True)
    return r


@router.post("/api/notaus/mine/off")
async def post_mine_off(request: Request):
    """The profile lifts its own Notaus: in a browser, with its PIN, and its code when its second step is on."""
    import agent
    import core
    import profiles
    if not _mine_lift_ok(request):
        raise HTTPException(403, "Aufheben nur im Browser.")
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "login required")
    uid = prof["id"]
    guard.limit(request, "notausoff", uid=uid)
    body = await _body(request)
    if not own(uid) or (ALL in mine() and uid not in mine()):
        raise HTTPException(409, "Mein Notaus ist nicht an." if not own(uid) else "Nur ein Admin kann ihn gerade aufheben.")
    u = next((u for u in profiles._load()["users"] if u["id"] == uid), None)
    guard.check(request, prof["name"])
    pin = body.get("pin")
    if not u or not isinstance(pin, str) or len(pin) > 64 or not profiles._pin_ok(pin, u["pin"]):
        guard.failed(request, prof["name"], what="notaus_pin")
        raise HTTPException(401, "Falsche PIN.")
    await core.confirm_code(request, uid, prof["name"], fresh=True)
    mine_off(uid, prof["name"])
    agent.kick()
    try:
        await tell_admins_mine(prof["name"], False)
    except Exception as e:
        print("notaus: push", type(e).__name__, flush=True)
    return view(request, _creds(request))


@router.post("/api/admin/notaus/mine/off")
async def post_mine_off_admin(request: Request):
    """An admin lifts a profile's own Notaus (the same rules as lifting the big one)."""
    import agent
    import core
    import coadmin
    how = _lift_how(request, _creds(request))
    if not how:
        raise HTTPException(403, "Aufheben nur als Admin, im Browser, im Heimnetz.")
    guard.limit(request, "notausoff", admin=True)
    body = await _body(request)
    uid = body.get("uid")
    if not isinstance(uid, str) or len(uid) > 40:
        raise HTTPException(400, "uid")
    m = mine()
    if not (uid in m or (ALL in m and uid == "")):
        raise HTTPException(404, "Für dieses Profil ist Mein Notaus nicht an.")
    main = core.password_set() and core._admin_cookie_age(request) is not None
    if how == "password":
        guard.check(request, guard.ADMIN)
        if not core.check_password(str(body.get("password") or "")[:200]):
            guard.failed(request, guard.ADMIN, what="notaus_password")
            raise HTTPException(401, "Falsches Passwort.")
    elif main:
        import mfa
        await core.confirm_code(request, mfa.ADMIN, guard.ADMIN, fresh=True)
    else:
        elev = coadmin.session(request)
        await core.confirm_code(request, elev["id"], elev["name"], fresh=True)
    by = "Admin" if main else coadmin.session(request)["name"]
    mine_off(uid, by, admin=True)
    agent.kick()
    return view(request, _creds(request))


async def tell_admins_mine(name, on):
    """Admins hear when a profile switches its own Notaus on or off (the name, never a reason)."""
    import push
    title = "Mein Notaus an" if on else "Mein Notaus aufgehoben"
    body = (f"{name} hat den eigenen Notaus eingeschaltet. Aufheben kann {name} selbst mit PIN, oder ein Admin unter Zustand."
            if on else f"{name} hat den eigenen Notaus aufgehoben.")
    for uid in admin_uids():
        try:
            await push.send(uid, title, body, tag="notaus", private=False)
        except Exception as e:
            print("notaus: push to an admin", type(e).__name__, flush=True)


# ---------------------------------------------------------------- other channels (Telegram, voice, Home Assistant, apps)
# Only the panel's own fixed rules decide here: a command or a fixed sentence the person typed or said, never text the
# model wrote or read. They only switch on; lifting stays in the browser (above).
def admin_profile(uid):
    """A profile the main admin made an admin (owner, Mit-Admin, Verwalter) may trigger the big Notaus by itself."""
    import coadmin
    try:
        return bool(uid) and coadmin.on() and coadmin.role(uid) in ("owner", "coadmin", "manager")
    except Exception:
        return False


async def raise_by(name, uid, lvl, channel):
    """The big Notaus from another channel: raises to lvl (1..3). Returns a German sentence for the person."""
    if lvl not in (1, 2, 3):
        return "Stufe 1, 2 oder 3."
    old, _ = trigger(lvl, name, uid, channel)
    if old >= lvl:
        return f"Der Notaus steht schon auf Stufe {old}."
    await after_change(old, lvl, name, channel)
    return f"Notaus Stufe {lvl} „{NAMES[lvl]}“ ist an. Aufheben geht nur als Admin im Browser im Heimnetz."


async def mine_by(name, uid, channel):
    """Mein Notaus from another channel (every browser login ends, no browser stays). Returns a German sentence."""
    import agent
    import profiles
    if not mine_on(uid, name, channel):
        return "Mein Notaus ist schon an."
    agent.notaus_hold(only=uid)
    try:
        import hamelden
        hamelden.stop(uid)
    except Exception as e:
        print("notaus: ha rules", type(e).__name__, flush=True)
    profiles.end_sessions(uid)
    try:
        await tell_admins_mine(name, True)
    except Exception as e:
        print("notaus: push", type(e).__name__, flush=True)
    return ("Mein Notaus ist an: alle Anmeldungen und Geräte deines Profils sind gesperrt, in deinem Namen passiert nichts. "
            "Aufheben im Browser unter Ich → Sicherheit mit deiner PIN.")


# A fixed sentence said or typed by the profile itself, the whole utterance and nothing else (never a question about
# it, never text the model wrote): "Spark, Mein Notaus" / "Spark, Notaus" (stage 2) / "Spark, Notaus Stufe drei".
_WORD = {"eins": 1, "zwei": 2, "drei": 3, "1": 1, "2": 2, "3": 3}
_PHRASE = re.compile(r"(?:hey |hallo |ok )?spark (?:(mein notaus)|notaus(?: stufe (eins|zwei|drei|1|2|3))?)")


def phrase(text):
    """("mine",) or ("big", stage) for the fixed sentence, else None."""
    t = str(text or "").lower()[:80]
    t = re.sub(r"not[\s-]+aus", "notaus", t)
    t = " ".join(re.sub(r"[^a-zäöüß0-9 ]", " ", t).split())
    m = _PHRASE.fullmatch(t)
    if not m:
        return None
    if m.group(1):
        return ("mine",)
    return ("big", _WORD.get(m.group(2) or "", 2))


def phrase_channel(client):
    """The channel a fixed sentence came through, from the chat request's client."""
    return {"telegram": "telegram", "speaker": "esp32", "watch": "pebble", "app": "app", "car": "app",
            "siri": "app", "android": "android"}.get(str(client or ""), "sprache")


async def by_phrase(cmd, name, uid, channel="sprache"):
    """Carries out phrase()'s result for this profile; returns the sentence the assistant says."""
    if channel not in CHANNELS:
        channel = "sprache"
    if cmd[0] == "mine":
        return await mine_by(name, uid, channel)
    if not admin_profile(uid):
        return "Den Notaus für den ganzen Spark dürfen nur Admins auslösen. Für dich: „Spark, Mein Notaus“."
    return await raise_by(name, uid, cmd[1], channel)


# ---------------------------------------------------------------- Home Assistant: a key that can only trigger
# The admin makes a key (Einstellungen → Sicherheit, fresh admin code); Home Assistant sends it as "Authorization:
# Bearer …" to POST /api/notaus/ha from the home network. It raises the big Notaus and nothing else: it reads
# nothing, lifts nothing, and is no device key of a profile. Only its hash is stored.
def _keys():
    try:
        with open(KEYS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        items = d.get("keys") if isinstance(d, dict) else None
        return [k for k in items if isinstance(k, dict) and isinstance(k.get("hash"), str)][:MAX_KEYS] if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _keys_write(items):
    os.makedirs(STATE, exist_ok=True)
    tmp = KEYS_FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w", encoding="utf-8") as f:
        json.dump({"keys": items}, f, ensure_ascii=False)
    os.replace(tmp, KEYS_FILE)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def key_new(name, now=None):
    import secrets
    name = " ".join(str(name or "").split())[:40] or "Home Assistant"
    if not re.fullmatch(r"[\w .,:()+-]{1,40}", name):
        raise ValueError("Name: nur Buchstaben, Ziffern und . , : ( ) + -")
    with _lock:
        items = _keys()
        if len(items) >= MAX_KEYS:
            raise ValueError(f"Höchstens {MAX_KEYS} Notaus-Schlüssel.")
        token = "na_" + secrets.token_urlsafe(24)
        items.append({"id": secrets.token_hex(5), "name": name, "hash": _hash(token),
                      "created": int(time.time() if now is None else now), "used": None})
        _keys_write(items)
    return token


def key_delete(kid):
    with _lock:
        items = _keys()
        rest = [k for k in items if k.get("id") != kid]
        if len(rest) == len(items):
            return False
        _keys_write(rest)
        return True


def key_find(token):
    if not isinstance(token, str) or not token.startswith("na_") or len(token) > 80:
        return None
    h = _hash(token)
    return next((k for k in _keys() if hmac.compare_digest(k["hash"], h)), None)


def key_used(kid, now=None):
    with _lock:
        items = _keys()
        for k in items:
            if k.get("id") == kid:
                k["used"] = int(time.time() if now is None else now)
        _keys_write(items)


@router.post("/api/notaus/ha")
async def post_ha(request: Request):
    """Home Assistant raises the big Notaus with its key (home network only); {"level": 1..3}, default 2."""
    guard.limit(request, "notausha")
    guard.check(request, "notaus-ha")
    if not at_home(request):
        raise HTTPException(403, "nur im Heimnetz")
    head = request.headers.get("authorization", "")
    k = key_find(head[7:].strip() if head[:7].lower() == "bearer " else "")
    if not k:
        guard.failed(request, "notaus-ha", what="notaus_key")
        raise HTTPException(401, "Schlüssel fehlt oder ist unbekannt")
    body = await _body(request)
    lvl = body.get("level", 2)
    if not isinstance(lvl, int) or isinstance(lvl, bool) or lvl not in (1, 2, 3):
        raise HTTPException(400, "level: 1, 2 oder 3")
    key_used(k["id"])
    text = await raise_by(f"Home Assistant ({k['name']})", "", lvl, "ha")
    return {"level": level(), "text": text}


@router.get("/api/admin/notaus/keys", dependencies=[Depends(auth)])
def get_keys():
    return {"keys": [{"id": k.get("id"), "name": k.get("name"), "created": k.get("created"), "used": k.get("used")} for k in _keys()],
            "max": MAX_KEYS}


@router.post("/api/admin/notaus/keys", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def post_key(request: Request):
    guard.limit(request, "notausoff", admin=True)
    body = await _body(request)
    try:
        token = key_new(body.get("name"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    guard.log("notaus_key_new", who="Admin", detail=" ".join(str(body.get("name") or "").split())[:40])
    return {"token": token}   # shown once


@router.delete("/api/admin/notaus/keys/{kid}", dependencies=[Depends(auth)])
def delete_key(kid: str):
    if not re.fullmatch(r"[0-9a-f]{10}", kid) or not key_delete(kid):
        raise HTTPException(404, "kein solcher Schlüssel")
    guard.log("notaus_key_delete", who="Admin", detail=kid)
    return {"ok": True}


# ---------------------------------------------------------------- Selbst-Notaus: the Wächter raises stage 1 by itself
# Admin switch panel.notaus_auto (Einstellungen → Sicherheit, off by default). Fixed rules only, counted in memory
# (a restart starts counting again): many wrong sign-ins from outside, a flood of MCP requests from outside that
# the rate limit turns away, or a series of outbound connections netguard refused (someone steering the Spark to
# addresses it must not reach). Each rule raises stage 1 "Außen zu", never higher, never down; lifting stays
# with the admin in the browser at home.
AUTO = {"login": (20, 600, "Wächter: 20 falsche Anmeldungen von außen in 10 Minuten"),
        "mcp": (30, 600, "Wächter: MCP-Flut von außen (30 abgewiesene Anfragen in 10 Minuten)"),
        "netguard": (15, 600, "Wächter: 15 gesperrte Verbindungen nach außen in 10 Minuten")}
_auto_lock = threading.Lock()
_auto_seen = {k: [] for k in AUTO}
_auto_tasks = set()


def auto_on():
    try:
        from common import load_config
        return load_config().get("panel", {}).get("notaus_auto", False) is True
    except Exception:
        return False


def _soon(coro):
    """Runs after_change without blocking the caller (an event loop task, or a short thread outside a loop)."""
    import asyncio
    try:
        task = asyncio.get_running_loop().create_task(coro)
        _auto_tasks.add(task)
        task.add_done_callback(_auto_tasks.discard)
    except RuntimeError:
        threading.Thread(target=asyncio.run, args=(coro,), daemon=True).start()


def watch(kind, now=None):
    """Counts one suspicious event; at a rule's threshold (and with the switch on) the Wächter raises stage 1.
    True when it did. Never raises: the callers are guard and netguard."""
    try:
        if kind not in AUTO:
            return False
        most, window, why = AUTO[kind]
        now = time.time() if now is None else now
        with _auto_lock:
            seen = [t for t in _auto_seen[kind] if now - window < t <= now][-most + 1:] + [now]
            hit = len(seen) >= most
            _auto_seen[kind] = [] if hit else seen
        if not hit or not auto_on() or level() >= 1:
            return False
        old, _ = trigger(1, "Wächter", "", "waechter", why, now=now)
        if old >= 1:
            return False
        print("notaus: Wächter löst Stufe 1 aus -", kind, flush=True)   # trigger() writes the admin log entry
        _soon(after_change(old, 1, "Wächter", "waechter"))
        return True
    except Exception as e:
        print("notaus: watch", type(e).__name__, flush=True)
        return False


def auto_reset():
    with _auto_lock:
        for k in _auto_seen:
            _auto_seen[k] = []
