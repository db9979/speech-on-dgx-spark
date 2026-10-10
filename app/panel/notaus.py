"""Notaus (kill switch, plan plaene/notaus.md, V01.0.31x): three stages that stop the Spark from the outside in.

    1 "Außen zu"    nothing from the internet (reverse proxy, MCP from outside, Telegram), and the Spark itself
                    reaches nothing on the internet (netguard, web search, weather, transit, Wikipedia, parcels,
                    reMarkable, firmware and app downloads); the home network goes on as before
    2 "Hände weg"   stage 1, and no actions: smart home, mail changes, messages, reminders and appointments,
                    lists, reMarkable, MCP actions, memory; agent jobs are held, "Von selbst", briefings, mail
                    tidying and learning pause; the assistant still answers from what it knows and reads
    3 "Alles still" stage 2, and no conversation at all: chat, speech recognition, speakers, Wyoming, room mode,
                    the watch; the panel shows only the Notaus page (login, logs and lifting stay)

Triggering is easy and lifting is hard. Any admin may trigger, and every profile when the admin allows it
(panel.notaus_profiles); a stage can only go up that way. Lifting (down to stage 1, or off) only by the main
admin or a profile in its admin mode (not the Verwalter role), in a browser in the home network, never from an
app key, with a fresh code (the main admin without a second step types the panel password again). The language
model, mail, web pages, documents, Home Assistant, Telegram or MCP can never trigger or lift it: nothing reads
text for it, the panel's own endpoints decide.

The stage survives a restart and an update (STATE/notaus.json). Way out without the panel:
sudo rm /var/lib/speech-spark/state/notaus.json (the panel reads the file anew on its next request).

What it held off is counted by kind only, in memory (Zustand → Notaus), never with contents.
"""
import ipaddress
import json
import os
import threading
import time

import guard

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "notaus.json")
LEVELS = (0, 1, 2, 3)
NAMES = {1: "Außen zu", 2: "Hände weg", 3: "Alles still"}
NAMES_EN = {1: "Outside closed", 2: "Hands off", 3: "All quiet"}
CHANNELS = ("panel", "app", "android", "telegram", "sprache", "esp32", "ha", "pebble", "waechter")
MAX_REASON = 120
MAX_HISTORY = 20

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


def locked_tools(held, changes=()):
    """The tool names the Notaus holds off at this stage: from 1 the ones that go to the internet by themselves,
    from 2 every one that changes something (chat.LOCKED_OUTSIDE, mail changes, the extras' changing tools)."""
    out = set(INTERNET_TOOLS) if held >= 1 else set()
    if held >= 2:
        import chat
        out |= chat.LOCKED_OUTSIDE | set(changes) | {"mail_draft", "mail_tidy_propose"}
    return out


class NotausAktiv(ValueError):
    """Raised where an action would happen while the Notaus holds it off (the last line of defence; the tools
    are already locked before)."""


_lock = threading.Lock()
_cache = {"key": None, "state": None}
_counts = {}


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


def blocks(kind):
    """True while the Notaus holds this kind of thing off (see STAGE)."""
    return level() >= STAGE[kind]


def refuse(kind):
    """Like blocks(), and counts it when it holds something off (for Zustand → Notaus)."""
    if not blocks(kind):
        return False
    with _lock:
        _counts[kind] = min(_counts.get(kind, 0) + 1, 10**9)
    return True


def stop(kind):
    """Raises NotausAktiv while the Notaus holds this kind off."""
    if refuse(kind):
        raise NotausAktiv(f"Notaus Stufe {level()}: {dict((k, de) for k, de, _ in KINDS)[kind]} gesperrt")


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
    return {"level": lvl, "name": NAMES.get(lvl, ""), "since": s["since"] if lvl else None, "channel": s["channel"] if lvl else "",
            "kinds": [{"k": k, "de": de, "en": en, "from": STAGE[k], "n": cnt.get(k, 0)} for k, de, en in KINDS] if lvl else []}


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
from fastapi.security import HTTPBasicCredentials  # noqa: E402

router = APIRouter()
MAX_BODY = 2048


def _settings():
    from common import load_config
    return load_config().get("panel", {})


def profiles_may():
    """The admin lets every profile trigger the Notaus (Einstellungen → Sicherheit → Notaus, default off)."""
    return _settings().get("notaus_profiles") is True


def _caller(request, creds=None):
    """(name, uid, admin, profile, channel) of who sends this request, or None. Only logins and the phone apps'
    keys count: no guests, no speaker, Siri or watch keys, no MCP, no Telegram (they come in a later step)."""
    import coadmin
    import core
    import profiles
    if request.scope.get("speech_mcp") or request.scope.get("speech_profile"):
        return None
    dev = profiles.device(request) if request.headers.get(profiles.DEVICE_HEADER) else None
    if dev is not None and dev["scope"] != "app":
        return None
    if not dev and core.is_main_admin(request, creds) and core.password_set():
        return "Admin", "", True, None, "panel"
    elev = coadmin.session(request)
    if elev and not dev:
        return elev["name"], elev["id"], True, None, "panel"
    prof = profiles.current(request)
    if not prof:
        return None
    return prof["name"], prof["id"], False, prof, ("app" if dev else "panel")


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
        return out
    may = bool(who[2] or profiles_may())
    out.update(may=may, lift=_lift_how(request, creds), names=NAMES)
    if s["level"]:
        out.update(since=s["since"], by=s["by"], channel=s["channel"], reason=s["reason"], counts=counts(),
                   kinds=[{"k": k, "de": de, "en": en, "from": STAGE[k]} for k, de, en in KINDS])
    return out


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
    if not admin and not profiles_may():
        raise HTTPException(403, "Den Notaus dürfen hier nur Admins auslösen (Einstellungen → Sicherheit → Notaus).")
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
