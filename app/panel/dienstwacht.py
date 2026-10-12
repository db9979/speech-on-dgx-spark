"""Dienst-Wächter (plan plaene/dienst-ausfall-melden.md): the Spark looks at its services by itself and tells the
admins when one is gone and when it is back.

What is looked at (only what is switched on, every minute; mail, calendar and NAS every 5 minutes, after a failure
every minute): the language model (/models of the stored address), Hören and Sprechen (/health of the front ends),
the internet (two fixed public addresses), SearXNG (/healthz), the own Kiwix, Home Assistant, the mail servers, the
calendar servers and the NAS of the backup. A probe never sends a login: an HTTP answer below 500 (401 included)
counts as "answers", for mail the TLS greeting of the IMAP server. Addresses come only from the stored settings,
never from a request, through netguard at the level each module uses (Kiwix, Home Assistant, NAS: home network;
mail and calendar: user rules; the internet: public), 5 seconds and 64 KB at most. Probes do not count on the
Live page's Wächter list and never start the Selbst-Notaus.

No flood of notes:
- "gone" only after FAIL_N failed probes in a row over at least FAIL_S seconds; "back" after OK_N good ones;
- one note about a service's outage per REPEAT seconds; one that comes and goes faster ("wackelt") is counted
  and told once with the number when the half hour is over and it is still gone;
- while the internet is gone the services behind it (mail, calendar, a Kiwix on a public address ...) get no
  note of their own: one note "Internet weg" names what is affected;
- everything that changes in one round is one note per admin; a note that does not get out (no internet for the
  iPhone's push) waits and goes with the next one, with times; at night (the profile's own switch) notes wait
  until 7 o'clock and come as one summary;
- nothing while the Spark updates, while it starts, or just after the watchdog restarted Hören or Sprechen.

Who hears it: the admin profiles (notaus.admin_uids: the one chosen for admin notes, owners, Mit-Admins) whose own
switch svc_note is on, on the device they chose (svc_device, push.send to=...). The words are fixed: the
service's name, times and what does not work; never an address, a host, a profile's name or an error text.

The admin pages show a banner (health.alerts, also in the iPhone app's "Spark verwalten"), Zustand → Dienste the
list with the outages of 7 days, the Live page a dot per service. With "Hinweis, wenn ein Dienst fehlt" (profile
switch svc_hint) a tool whose service is gone answers with a fixed sentence at once instead of waiting for it.
Admin switch chat.svc_watch (off), below it chat.svc_watch_users (off).
"""
import asyncio
import contextlib
import hashlib
import ipaddress
import os
import re
import socket
import ssl
import time
from typing import NamedTuple
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import netguard
import profiles
from common import load_config, write_json
from core import auth

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")

LOOP = 30                 # the loop wakes this often; each service has its own pace
EVERY, SLOW = 60, 300     # most services every minute; mail, calendar, NAS every 5 minutes (after a failure: EVERY)
FAIL_N, FAIL_S = 3, 180   # gone: this many failed probes in a row, over at least this many seconds
OK_N = 2                  # back: this many good probes in a row
REPEAT = 30 * 60          # at most one outage note per service in this time
TIMEOUT, MOST = 5, 64 * 1024
START_GRACE = 180         # after the panel started: services may still be loading
RESTART_GRACE = 300       # after the watchdog restarted Hören or Sprechen
KEEP_LOG = 7 * 86400
MAX_LOG, MAX_PARTS, MAX_QUEUE = 300, 10, 30
RETRY_GAP = 300           # a note that did not get out is tried again after this long
QUEUE_KEEP = 12 * 3600    # and given up after this long
NIGHT = (22, 7)           # "nachts sammeln": from 22 to 7 o'clock Spark time
# two fixed public addresses: the internet is gone only when neither answers
INET = ("https://api.github.com/", "https://cloudflare.com/cdn-cgi/trace")
DEVICES = ("", "app", "and", "desk", "tg", "web", "all")

# id: (name, name in English, what does not work while it is gone, pace, the Live page's node)
SVC = {
    "qwen": ("Sprachmodell", "Language model", "Der Assistent kann gerade nicht antworten.", EVERY, "qwen"),
    "asr": ("Hören", "Listening", "Gesprochene Fragen werden gerade nicht verstanden, Tippen geht weiter.", EVERY, "asr"),
    "tts": ("Sprechen", "Speaking", "Antworten kommen nur als Text, nicht gesprochen.", EVERY, "tts"),
    "inet": ("Internet", "Internet", "Alles, was ins Internet muss, geht gerade nicht. Das Heimnetz läuft weiter.", EVERY, "inet"),
    "web": ("Websuche (SearXNG)", "Web search (SearXNG)", "Die Websuche geht gerade nicht.", EVERY, "web"),
    "kiwix": ("Archiv (Kiwix)", "Archive (Kiwix)", "Fragen ans Archiv gehen gerade nicht.", EVERY, "kiwix"),
    "ha": ("Home Assistant", "Home Assistant", "Schalten und Abfragen im Haus gehen gerade nicht.", EVERY, "ha"),
    "mail": ("Mail", "Mail", "Mails lesen und suchen geht gerade nicht.", SLOW, "mail"),
    "cal": ("Kalender", "Calendar", "Termine lesen und eintragen geht gerade nicht.", SLOW, "cal"),
    "nas": ("NAS (Sicherung)", "NAS (backup)", "Die Sicherung auf das NAS geht gerade nicht.", SLOW, "nas"),
}
# what needs the internet besides the watched services (for the note "Internet weg"): function -> name
NEEDS_NET = (("search", "Websuche"), ("weather", "Wetter"), ("transit", "Bus und Bahn"), ("parcels", "Pakete"),
             ("wiki", "Wikipedia"), ("remarkable", "reMarkable"), ("iphonepush", "Push ans iPhone"))
# the tools whose service the assistant names when it is gone (svc_hint); the rest of chat_tools runs as before
TOOL_SVC = {"archive_search": "kiwix", "web_search": "web",
            "home_assistant": "ha", "home_assistant_action": "ha", "home_assistant_history": "ha",
            "home_assistant_states": "ha", "home_assistant_todo": "ha",
            "mail_list": "mail", "mail_read": "mail", "mail_search": "mail", "mail_tidy_overview": "mail",
            "mail_tidy_propose": "mail", "calendar_events": "cal", "calendar_add": "cal",
            "weather": "inet", "transit": "inet", "parcels": "inet", "wikipedia": "inet", "read_page": "inet"}
WORD = {"ok": "läuft", "wobble": "wackelt", "down": "antwortet nicht", "inet": "wegen Internet", "off": "nicht geprüft",
        "held": "Notaus: nicht geprüft", "blocked": "vom Wächter nicht erlaubt", "new": "noch nicht geprüft"}
STARTED = time.time()

profiles.NO_PRESET.update({"svc_night", "svc_device"})   # the admin's presets never set who hears what, and where


def admin_on(c=None):
    return features.admin_on("dienstwacht", c)


def _file():
    return os.path.join(STATE, "dienstwacht.json")


_mem = {"d": None}      # the state, read once (only this module writes it)
_due = {}               # id -> unix time of the next probe (in memory: after a start every service is due)


def _read():
    if _mem["d"] is None:
        import json
        try:
            with open(_file()) as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        d = d if isinstance(d, dict) else {}
        _mem["d"] = {"skip": [s for s in d.get("skip", []) if s in SVC] if isinstance(d.get("skip"), list) else [],
                     "svc": {k: v for k, v in (d.get("svc") or {}).items() if k in SVC and isinstance(v, dict)}
                     if isinstance(d.get("svc"), dict) else {},
                     "log": [x for x in d.get("log", []) if isinstance(x, dict) and x.get("s") in SVC]
                     if isinstance(d.get("log"), list) else [],
                     "queue": {u: q for u, q in (d.get("queue") or {}).items() if isinstance(q, dict)}
                     if isinstance(d.get("queue"), dict) else {}}
    return _mem["d"]


def _write():
    try:
        write_json(_file(), _read())
    except OSError as e:
        print("dienstwacht: state not written", type(e).__name__, flush=True)


def reset():
    """For the self-tests: forget everything (file and memory)."""
    _mem["d"] = None
    _due.clear()
    with contextlib.suppress(OSError):
        os.remove(_file())


def _hm(t):
    return time.strftime("%H:%M", time.localtime(t))


def _dur(secs):
    m = max(1, int(round(secs / 60)))
    return f"{m} min" if m < 60 else f"{m // 60} h" + (f" {m % 60} min" if m % 60 else "")


def _hour(now):
    return time.localtime(now).tm_hour


# ---------------------------------------------------------------- what is looked at
def _origin(url):
    u = urlsplit(str(url or ""))
    if u.scheme not in ("http", "https") or not u.hostname:
        return ""
    return f"{u.scheme}://{u.hostname}" + (f":{u.port}" if u.port else "")


def _key(x):
    return hashlib.sha256(str(x).encode()).hexdigest()[:12]


def _json(path):
    import json
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ha_parts():
    out = {}
    for uid in profiles.user_ids():
        d = _json(profiles._path(uid, "homeassistant.json"))     # read raw: the token is never opened here
        o = _origin(d.get("url")) if d.get("token") else ""
        if o:
            out.setdefault(_key(o), {"url": str(d["url"]).rstrip("/") + "/api/", "level": netguard.HOME,
                                     "verify": d.get("verify", True) is not False, "uids": []})["uids"].append(uid)
    return out


def _mail_parts():
    out = {}
    for uid in profiles.user_ids():
        for a in _json(profiles._path(uid, "mail.json")).get("accounts") or []:
            host = str((a or {}).get("host") or "").strip().lower() if isinstance(a, dict) else ""
            try:
                port = int(a.get("port") or 993)
            except (TypeError, ValueError):
                continue
            if host and re.fullmatch(r"[a-z0-9.-]{1,253}", host) and 0 < port < 65536:
                out.setdefault(_key(f"{host}:{port}"), {"host": host, "port": port, "uids": []})["uids"].append(uid)
    return out


def _cal_parts():
    out = {}
    for uid in profiles.user_ids():
        d = _json(profiles._path(uid, "calendar.json"))
        cals = d.get("calendars") if isinstance(d.get("calendars"), list) else ([{"url": d["url"]}] if d.get("url") else [])
        for c in cals:
            o = _origin(c.get("url")) if isinstance(c, dict) else ""
            if o:
                out.setdefault(_key(o), {"url": o + "/", "level": netguard.USER, "verify": True, "uids": []})["uids"].append(uid)
    return out


def active(c=None, cfg=None):
    """The services to look at now: id -> list of parts (one per address)."""
    cfg = cfg or load_config()
    c = cfg.get("chat", {}) if c is None else c
    out = {}
    url = str(c.get("llm_url") or "").rstrip("/")
    if url.startswith(("http://", "https://")):
        out["qwen"] = {"llm": {"url": url + "/models", "key": str(c.get("llm_key") or "")}}
    for name in ("asr", "tts"):
        if (cfg.get(name) or {}).get("enabled", True) and (cfg.get(name) or {}).get("port"):
            out[name] = {"own": {"name": name}}
    out["inet"] = {_key(u): {"url": u, "level": netguard.PUBLIC, "verify": True, "any": True} for u in INET}
    surl = str(c.get("search_url") or "").strip().rstrip("/")
    if features.admin_on("search", c) and _origin(surl):
        base = surl[:-len("/search")] if surl.endswith("/search") else surl
        out["web"] = {"searx": {"url": base + "/healthz", "level": netguard.HOME, "verify": True}}
    try:
        import kiwix
        if kiwix.admin_on() and kiwix.base():
            out["kiwix"] = {"kiwix": {"url": kiwix.base() + "/", "level": netguard.HOME, "verify": True}}
    except Exception:
        pass
    for sid, fkey, parts in (("ha", "ha", _ha_parts), ("mail", "mail", _mail_parts), ("cal", "calendar", _cal_parts)):
        if features.admin_on(fkey, c):
            p = dict(list(parts().items())[:MAX_PARTS])
            if p:
                out[sid] = p
    try:
        import offsite
        d = offsite._read()
        if d.get("on") is True and _origin(d.get("url")):
            out["nas"] = {"nas": {"url": str(d["url"]), "level": netguard.HOME, "verify": True}}
    except Exception:
        pass
    skip = set(_read()["skip"])
    return {k: v for k, v in out.items() if k not in skip}


# ---------------------------------------------------------------- probes
_glob = {}     # host -> (time, is a public address)


def _is_public(host):
    """Whether a name points to the internet (cached an hour); None when it cannot be told."""
    hit = _glob.get(host)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    try:
        ip = ipaddress.ip_address(host)
        g = ip.is_global
    except ValueError:
        try:
            g = ipaddress.ip_address(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)[0][4][0].split("%")[0]).is_global
        except (OSError, ValueError, IndexError):
            return hit[1] if hit else None
    _glob[host] = (time.time(), g)
    if len(_glob) > 200:
        _glob.pop(next(iter(_glob)))
    return g


class Probe(NamedTuple):
    ok: bool
    why: str = ""        # "", "notaus", "blocked" (a fixed word, never the error text)


async def _http(p):
    try:
        async with netguard.client(p["level"], max_bytes=MOST, verify=p.get("verify", True),
                                   timeout=httpx.Timeout(TIMEOUT, connect=TIMEOUT)) as c:
            async with c.stream("HEAD" if p.get("any") else "GET", p["url"]) as r:
                return Probe(r.status_code < 500)
    except netguard.Blocked as e:
        return Probe(False, "notaus" if "Notaus" in str(e) else "blocked")
    except (httpx.HTTPError, netguard.TooLarge, ssl.SSLError, OSError, ValueError):
        return Probe(False)


async def _llm(p):
    # the language model lives on this machine's ports, which netguard refuses on purpose (like admin.llm_models)
    headers = {"Authorization": f"Bearer {p['key']}"} if p.get("key") else {}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as c:
            async with c.stream("GET", p["url"], headers=headers) as r:
                return Probe(r.status_code < 500)
    except (httpx.HTTPError, OSError, ValueError):
        return Probe(False)


async def _own(p, cfg):
    from monitor import service_health
    h = await service_health(p["name"], cfg)
    return Probe(isinstance(h, dict) and h.get("status") not in ("blocked", "error"))


async def _imap(p):
    """The mail server answers with TLS on its port: no login, no command."""
    try:
        ip = await asyncio.to_thread(netguard.resolve, p["host"], p["port"], netguard.USER)
        ctx = ssl.create_default_context()
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, p["port"], ssl=ctx, server_hostname=p["host"]), TIMEOUT)
        try:
            line = await asyncio.wait_for(r.readline(), TIMEOUT)
        finally:
            w.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(w.wait_closed(), 1)
        return Probe(line.startswith(b"* "))
    except netguard.Blocked as e:
        return Probe(False, "notaus" if "Notaus" in str(e) else "blocked")
    except (OSError, ssl.SSLError, asyncio.TimeoutError, httpx.HTTPError, ValueError):
        return Probe(False)


async def probe(sid, key, p, cfg):
    token = netguard.QUIET.set(True)   # a probe is no request: not on the Wächter list, no Selbst-Notaus
    try:
        if sid == "qwen":
            return await _llm(p)
        if sid in ("asr", "tts"):
            return await _own(p, cfg)
        if sid == "mail":
            return await _imap(p)
        return await _http(p)
    finally:
        netguard.QUIET.reset(token)


def _host(sid, p):
    if sid == "mail":
        return p.get("host", "")
    return urlsplit(p.get("url", "")).hostname or ""


# ---------------------------------------------------------------- one round
def _paused(now):
    """Nothing counts while the Spark updates or just started."""
    if now - STARTED < START_GRACE:
        return True
    try:
        import update
        if update.update_running():
            return True
    except Exception:
        pass
    return False


def _restarted(sid, now):
    if sid not in ("asr", "tts"):
        return False
    try:
        import health
        return any(str(e.get("unit", "")).lower().startswith(sid) and now - e.get("t", 0) < RESTART_GRACE for e in health.events)
    except Exception:
        return False


def saw(sid, ok=False):
    """A request found a service gone (web search, the language model): look at it in the next round."""
    if not ok and sid in SVC:
        _due[sid] = 0


def _entry(sid):
    return _read()["svc"].setdefault(sid, {"st": "new", "fails": 0, "oks": 0, "fail_t": 0, "since": 0, "checked": 0,
                                           "noted": 0, "told": False, "flaps": 0, "parts": {}, "net": None})


async def round_once(now=None, force=False):
    """Probes what is due, moves states and sends the notes. Returns the changes [(id, "down"|"up")]."""
    now = time.time() if now is None else now
    if not admin_on():
        return []
    import notaus
    if notaus.blocks("auto"):        # Notaus stage 2: nothing happens by itself
        return []
    cfg = load_config()
    act = active(cfg.get("chat", {}), cfg)
    d = _read()
    for sid in list(d["svc"]):        # a service switched off or no longer set up: off the list
        if sid not in act:
            e = d["svc"][sid]
            if e.get("st") == "down":
                _close(sid, now)
            d["svc"].pop(sid)
    if _paused(now) and not force:
        return []
    held = notaus.level() >= 1         # stage 1: nothing to the internet, so nothing out there is looked at
    todo = [(sid, k, p) for sid, parts in act.items() for k, p in parts.items()
            if (force or now >= _due.get(sid, 0)) and not (held and sid == "inet")]
    if held and "inet" in act:
        _entry("inet").update(st="held", fails=0, oks=0, checked=now)
    token = netguard.QUIET.set(True)   # probes are no request: not on the Wächter list, no Selbst-Notaus
    try:
        res = await asyncio.gather(*(asyncio.wait_for(probe(sid, k, p, cfg), TIMEOUT * 2) for sid, k, p in todo),
                                   return_exceptions=True)
        nets = await asyncio.gather(*(asyncio.to_thread(_is_public, _host(sid, p)) for sid, k, p in todo if sid not in ("qwen", "asr", "tts", "inet")),
                                    return_exceptions=True)
    finally:
        netguard.QUIET.reset(token)
    nets = iter(nets)
    seen = {}
    for (sid, k, p), r in zip(todo, res):
        r = r if isinstance(r, Probe) else Probe(False)
        g = None if sid in ("qwen", "asr", "tts", "inet") else next(nets, None)
        x = seen.setdefault(sid, {"ok": [], "bad": [], "why": set(), "net": []})
        (x["ok"] if r.ok else x["bad"]).append(k)
        if r.why:
            x["why"].add(r.why)
        if isinstance(g, bool):
            x["net"].append(g)
    inet_down = d["svc"].get("inet", {}).get("st") == "down"
    changes = []
    for sid in sorted(seen, key=lambda s: s != "inet"):      # the internet first: the others depend on it
        x, e = seen[sid], _entry(sid)
        parts = act[sid]
        e["checked"] = now
        _due[sid] = now + (EVERY if x["bad"] else SVC[sid][3])
        if x["net"]:
            e["net"] = all(x["net"])
        elif e.get("net") is None and sid in ("mail", "cal"):
            e["net"] = True
        if sid == "inet":
            good = bool(x["ok"])                        # one of the two fixed addresses is enough
        else:
            good = not x["bad"]
        e["parts"] = {k: (k not in x["bad"]) for k in parts}
        if not good and (held and ("notaus" in x["why"] or sid == "inet") or x["why"] == {"blocked"}):
            if e["st"] == "down":              # no longer looked at: the outage ends here, nobody waits for "back"
                _close(sid, now)
            e.update(st="held" if held else "blocked", fails=0, oks=0, told=False)
            continue
        if not good and _restarted(sid, now):
            continue
        if good:
            e["oks"] += 1
            e["fails"] = 0
            if e["st"] in ("down", "inet") and e["oks"] >= OK_N:
                if e["st"] == "down":
                    changes.append((sid, "up"))
                    _back(sid, e, now)
                e["st"] = "ok"
            elif e["st"] not in ("down", "inet"):
                e["st"] = "ok"
            continue
        e["oks"] = 0
        e["fails"] += 1
        if e["fails"] == 1:
            e["fail_t"] = now
        if e["st"] in ("down", "inet"):
            if e["st"] == "inet" and not (inet_down and e.get("net")):
                e["st"] = "down"                    # the internet is back, this one is still gone
                e["since"] = now
                _open(sid, now)
                changes.append((sid, "down"))
                _gone(sid, e, now)
            continue
        if e["fails"] >= FAIL_N and now - e["fail_t"] >= FAIL_S - 1:
            if sid != "inet" and inet_down and e.get("net"):
                e.update(st="inet", since=e["fail_t"])   # no note of its own: "Internet weg" names it
                continue
            e.update(st="down", since=e["fail_t"])
            _open(sid, e["fail_t"])
            changes.append((sid, "down"))
            _gone(sid, e, now)
            if sid == "inet":
                inet_down = True
        else:
            e["st"] = "wobble"
    _later(now)
    _write()
    if changes:
        await notes(now)
    else:
        await notes(now, only_due=True)
    return changes


def _gone(sid, e, now):
    """The service is gone: a note now, or (it went and came within REPEAT) counted and told later."""
    import live
    live.event("Dienste", f"{SVC[sid][0]} antwortet nicht")
    if now - (e.get("noted") or 0) >= REPEAT:
        n = int(e.get("flaps") or 0)          # outages since the last note that nobody heard of
        e.update(noted=now, told=True, flaps=0)
        _queue_all({"k": "down", "s": sid, "t": e["since"], "n": n}, now)
    else:
        e["flaps"] = int(e.get("flaps") or 0) + 1
        e["told"] = False


def _back(sid, e, now):
    import live
    live.event("Dienste", f"{SVC[sid][0]} wieder da nach {_dur(now - (e.get('since') or now))}")
    _close(sid, now)
    if e.get("told"):
        _queue_all({"k": "up", "s": sid, "t": now, "a": e.get("since") or now}, now)
    e["told"] = False


def _later(now):
    """A service that wobbled and is still gone when its half hour is over: one note with the count."""
    for sid, e in _read()["svc"].items():
        if e.get("st") == "down" and not e.get("told") and now - (e.get("noted") or 0) >= REPEAT:
            n = int(e.get("flaps") or 0)
            e.update(noted=now, told=True, flaps=0)
            _queue_all({"k": "down", "s": sid, "t": e.get("since") or now, "n": n}, now)


def _open(sid, t):
    log = _read()["log"]
    log.append({"s": sid, "a": int(t), "b": None})


def _close(sid, now):
    for x in reversed(_read()["log"]):
        if x["s"] == sid and x.get("b") is None:
            x["b"] = int(now)
            break


def _prune(now):
    d = _read()
    d["log"] = [x for x in d["log"] if (x.get("b") or now) > now - KEEP_LOG][-MAX_LOG:]


# ---------------------------------------------------------------- notes
def recipients():
    import notaus
    return [u for u in notaus.admin_uids() if features.allowed("dienstwacht", u)]


def _queue_all(item, now):
    q = _read()["queue"]
    for uid in recipients():
        x = q.setdefault(uid, {"items": [], "tried": 0})
        x["items"] = (x["items"] + [dict(item, q=now)])[-MAX_QUEUE:]


def night(uid, now):
    if profiles.settings(uid).get("svc_night") is not True:
        return False
    h = _hour(now)
    return h >= NIGHT[0] or h < NIGHT[1]


def _affected(c):
    """For "Internet weg": what does not work (the watched services behind it and the functions that need it)."""
    names = [SVC[s][0] for s, e in _read()["svc"].items() if s != "inet" and e.get("net") and s in active(c)]
    for key, name in NEEDS_NET:
        try:
            if features.admin_on(key, c) and name not in names and not (key == "search" and "Websuche (SearXNG)" in names):
                names.append(name)
        except KeyError:
            pass
    return names


def text(items, now, c=None):
    """(title, body) from the queued items: fixed words, names of services, times. Never an address or error."""
    c = features.chat_cfg() if c is None else c
    svc = _read()["svc"]
    per = {}
    for it in items:
        per.setdefault(it["s"], []).append(it)
    gone, back, lines = [], [], []
    for s in SVC:
        its = per.get(s)
        if not its:
            continue
        last, downs = its[-1], [i for i in its if i["k"] == "down"]
        name = SVC[s][0]
        if last["k"] == "down" and (svc.get(s) or {}).get("st") == "down":
            gone.append(s)
            if s == "inet":
                aff = _affected(c)
                lines.insert(0, f"Internet weg seit {_hm(last['t'])}." + (f" Betroffen: {', '.join(aff)}." if aff else "")
                             + " Das Heimnetz läuft weiter.")
            else:
                n = max(int(i.get("n") or 0) for i in downs)
                wob = f" Wackelt: {n + 1} Ausfälle in der letzten halben Stunde." if n else ""
                lines.append(f"{name} antwortet seit {_hm(last['t'])} nicht. {SVC[s][2]}{wob}")
            continue
        back.append(s)
        up = last if last["k"] == "up" else {"t": now, "a": last["t"]}
        if downs:
            a = downs[0]["t"]
            more = f" {len(downs)} Ausfälle." if len(downs) > 1 else ""
            lines.append(f"{name} war von {_hm(a)} bis {_hm(up['t'])} weg ({_dur(up['t'] - a)}), läuft wieder.{more}")
        else:
            lines.append(f"{name} läuft wieder, war {_dur(up['t'] - up.get('a', up['t']))} weg.")
    still = [SVC[s][0] for s in SVC if (svc.get(s) or {}).get("st") == "down" and s not in gone]
    names = lambda ids: ", ".join(SVC[s][0] for s in ids)   # noqa: E731
    if gone:
        title = "⚠️ Internet weg" if gone == ["inet"] else "⚠️ " + names(gone) + " nicht erreichbar"
        if back:
            title += " · ✅ " + names(back) + " wieder da"
        if still:
            lines.append("Weiter weg: " + ", ".join(still) + ".")
    else:
        title = "✅ Wieder da: " + names(back)
        lines.append("Noch weg: " + ", ".join(still) + "." if still else "Alles läuft wieder.")
    return title[:120], " ".join(lines)[:600]


async def notes(now=None, only_due=False):
    """Sends what waits for each admin: one note per admin. At night (svc_night) it waits until 7 o'clock and then
    comes as one summary; one that did not get out is tried again every RETRY_GAP. Returns the number sent."""
    now = time.time() if now is None else now
    import live
    import notaus
    import push
    d, sent = _read(), 0
    allowed = set(recipients())
    for uid in list(d["queue"]):
        x = d["queue"][uid]
        x["items"] = [i for i in x.get("items", []) if isinstance(i, dict) and i.get("s") in SVC and now - i.get("q", now) < QUEUE_KEEP]
        if uid not in allowed or not x["items"]:
            d["queue"].pop(uid)
            continue
        if night(uid, now) or notaus.blocks("auto", uid):
            x["night"] = x.get("night") or (night(uid, now) and now)
            continue
        if only_due and not x.get("night") and now - (x.get("tried") or 0) < RETRY_GAP:
            continue
        if not push.reachable(uid, False):
            print("dienstwacht: admin profile without a device for notes, note dropped", flush=True)
            d["queue"].pop(uid)
            continue
        title, body = text(x["items"], now)
        if x.get("night"):
            title = "🌙 Heute Nacht: " + title.lstrip("⚠️✅ ")
        dev = str(profiles.settings(uid).get("svc_device") or "")
        try:
            n = await push.send(uid, title, body, tag="svc", private=False, to=dev if dev in DEVICES else "")
        except Exception as e:
            print("dienstwacht: note", type(e).__name__, flush=True)
            n = 0
        if n:
            sent += 1
            d["queue"].pop(uid)
        else:
            x["tried"] = now
    if sent:
        live.event("Dienste", f"Ausfall-Hinweis an {sent} Admin{'s' if sent > 1 else ''}")
    _prune(now)
    _write()
    return sent


# ---------------------------------------------------------------- what pages, Live and the assistant see
def down(sid):
    e = _read()["svc"].get(sid)
    return bool(e and e.get("st") == "down" and admin_on())


def alerts(now=None):
    """The banner on every admin page (health.alerts): what is gone and what does not work."""
    if not admin_on():
        return []
    out = []
    for sid, e in _read()["svc"].items():
        if e.get("st") == "down":
            out.append({"kind": "service", "level": "bad",
                        "text": f"Gerade eingeschränkt: {SVC[sid][0]} antwortet seit {_hm(e.get('since') or 0)} nicht. {SVC[sid][2]}"})
    return out


def _state(e):
    st = e.get("st", "new")
    if st == "ok" and e.get("fails"):
        st = "wobble"
    return st


def for_live(now=None):
    """Live: a dot per service (fixed words), and the warnings at their node."""
    now = time.time() if now is None else now
    if not admin_on():
        return {}, []
    svc, hints = {}, []
    act = active()                                   # not set up or taken off the list: no dot, no line (Live shows only what exists)
    dot = {"ok": "ok", "wobble": "load", "down": "down", "inet": "down", "held": "off", "blocked": "off", "new": "load", "off": "off"}
    for sid, e in _read()["svc"].items():
        if sid not in act:
            continue
        st = _state(e)
        node = SVC[sid][4]
        svc[node] = {"st": dot.get(st, "off"), "word": WORD.get(st, st), "ago": int(max(0, now - (e.get("checked") or now)))}
        if st == "down":
            hints.append({"at": "llm" if node == "qwen" else node, "level": "bad", "word": f"antwortet nicht seit {_hm(e.get('since') or now)}"})
        elif st == "inet":
            hints.append({"at": node, "level": "warn", "word": "wegen Internet weg"})
    return svc, hints


def overview(now=None):
    now = time.time() if now is None else now
    d = _read()
    c = features.chat_cfg()
    on = admin_on(c)
    act = active(c) if on else {}
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    rows = []
    for sid, (de, en, what, pace, _) in SVC.items():
        e = d["svc"].get(sid) or {}
        parts = e.get("parts") or {}
        today = sum(1 for x in d["log"] if x["s"] == sid and time.strftime("%Y-%m-%d", time.localtime(x["a"])) == day)
        rows.append({"id": sid, "name": [de, en], "what": what, "watched": sid not in d["skip"], "set": sid in act or sid in d["skip"] and sid in active_all(c),
                     "st": (_state(e) if sid in act else "off"), "since": e.get("since") if e.get("st") in ("down", "inet") else None,
                     "checked": e.get("checked"), "today": today, "every": pace // 60,
                     "parts": {"n": len(parts), "bad": sum(1 for v in parts.values() if not v)} if len(parts) > 1 and sid != "inet" else None})
    log = [{"id": x["s"], "name": [SVC[x["s"]][0], SVC[x["s"]][1]], "a": x["a"], "b": x.get("b")}
           for x in reversed(d["log"]) if (x.get("b") or now) > now - KEEP_LOG][:20]
    return {"on": on, "paused": on and _paused(now), "services": rows, "log": log, "words": WORD,
            "admins": len(recipients()) if on else 0}


def active_all(c):
    """What could be looked at (also the ones the admin took off the list)."""
    d = _read()
    skip, d["skip"] = d["skip"], []
    try:
        return active(c)
    finally:
        d["skip"] = skip


# ---------------------------------------------------------------- the assistant (svc_hint)
class Down(RuntimeError):
    pass


def _mine(sid, uid):
    """Whether the profile's own address of that service is the one that is gone (Home Assistant, mail, calendar)."""
    e = _read()["svc"].get(sid) or {}
    parts = e.get("parts") or {}
    if sid == "ha":
        keys = [k for k, p in _ha_parts().items() if uid in p["uids"]]
    elif sid == "mail":
        keys = [k for k, p in _mail_parts().items() if uid in p["uids"]]
    elif sid == "cal":
        keys = [k for k, p in _cal_parts().items() if uid in p["uids"]]
    else:
        return True
    return bool(keys) and all(parts.get(k) is False for k in keys)


def tool_down(name, uid):
    """The fixed sentence for a tool whose service the Dienst-Wächter sees gone, else ''. Only with the switches."""
    sid = TOOL_SVC.get(name)
    if not sid or not uid or not features.allowed("dienstnutzer", uid):
        return ""
    e = _read()["svc"].get(sid) or {}
    inet = (_read()["svc"].get("inet") or {}).get("st") == "down"
    if e.get("st") == "down" and _mine(sid, uid):
        since, svc = e.get("since"), sid
    elif inet and (sid in ("inet", "web") or e.get("st") == "inet" or e.get("net")):
        since, svc = (_read()["svc"]["inet"].get("since")), "inet"
    else:
        return ""
    de = f"{SVC[svc][0]} ist gerade nicht erreichbar (seit {_hm(since or time.time())})."
    print(f"dienstwacht: {name} not tried, {svc} is gone", flush=True)
    return (f"Not done: the service {SVC[svc][1]} is not reachable right now, the Spark's service watch sees it gone. "
            f"Tell the user exactly this in one sentence, in their language: \"{de}\" Do not guess an answer, do not "
            "try again, do not offer a workaround.")


# ---------------------------------------------------------------- loop
async def loop():
    while True:
        await asyncio.sleep(LOOP)
        try:
            await round_once()
        except Exception as e:
            print("dienstwacht: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- routes (admin)
@router.get("/api/admin/svcwatch", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "svcwatch", admin=True)
    return overview()


@router.post("/api/admin/svcwatch/check", dependencies=[Depends(auth)])
async def admin_check(request: Request):
    """Zustand → Dienste → „Jetzt prüfen“: every service once now (counts like a normal round)."""
    guard.limit(request, "svcwatchnow", admin=True)
    if not admin_on():
        raise HTTPException(409, "Der Dienst-Wächter ist aus (Funktionen → Dienst-Wächter).")
    await round_once(force=True)
    return overview()


@router.put("/api/admin/svcwatch/{sid}", dependencies=[Depends(auth)])
async def admin_watch(sid: str, request: Request):
    """Takes a service off the list (or back on): it is not looked at and nobody hears of it."""
    guard.limit(request, "svcwatch", admin=True)
    if sid not in SVC:
        raise HTTPException(404, "no such service")
    raw = await request.body()
    if len(raw) > 64:
        raise HTTPException(413, "too large")
    import json
    try:
        on = json.loads(raw or b"{}").get("on")
    except (ValueError, AttributeError):
        raise HTTPException(400, "invalid JSON")
    if not isinstance(on, bool):
        raise HTTPException(400, "on: true or false")
    d = _read()
    d["skip"] = [s for s in d["skip"] if s != sid] + ([] if on else [sid])
    if not on and (d["svc"].get(sid) or {}).get("st") == "down":
        _close(sid, time.time())
    if not on:
        d["svc"].pop(sid, None)
    _due.pop(sid, None)
    _write()
    elev = None if request.scope.get("speech_main_admin") else request.scope.get("speech_coadmin")
    guard.log("svcwatch", by="main" if not elev else elev["id"], detail=f"Dienst-Wächter: {SVC[sid][0]} {'an' if on else 'aus'}")
    return overview()
