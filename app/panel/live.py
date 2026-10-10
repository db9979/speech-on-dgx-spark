"""Zustand → Live (V01.0.312): what the Spark does right now, for the admin and for a wall monitor.

Running requests with their way through the panel (from tracelog.Rec, also while Logs → Anfragen is off),
what the Wächter (netguard.py) decides for each outgoing connection and why, who came in from the
internet or was turned away (guard.failed, monitor pairing), what the tools gave back, open channels and
the machine's numbers. Everything lives in memory only and is gone after a restart.

Only fixed words, tool names, numbers and service names: never a question, an answer, tool arguments or
results, mail subjects, URLs with paths or secrets. Web pages from search results show as "Webseite",
not with their address; blocked addresses show (they are the reason). Senders from the internet are
shortened (89.204.x.x). A profile's name shows only with its consent (trace_name, as in Logs → Anfragen);
the monitor shows names only when the admin also allows it (logs.live_names), else "Person".

Off by default: admin switch logs.live (Einstellungen → Spark → Betrieb → Logs). The monitor page /live is
a second switch (logs.live_monitor): a screen in the home network pairs once with a 6-digit code (10 min,
one use) and then keeps a cookie that may only read /api/live/state. Requests from the internet are
refused (the monitor is for the home network). Monitors are kept as hashes in STATE/live-monitors.json,
unused ones expire after 90 days, deleting one cuts it off at once. At most logs.live_screens at a time.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import guard
from common import load_config
from core import auth

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
FADE = 10                 # a finished request fades out this many seconds after a newer one came
MAX_RUN = 40              # requests watched at once (more: the oldest go)
CODE_S = 600              # a pairing code lasts 10 minutes
MAX_CODES, MAX_MONITORS = 5, 10
KEEP_DAYS = 90            # a monitor nobody used that long must pair again
SEEN_S = 6                # a monitor that asked within this many seconds counts as watching
COOKIE = "speech_spark_live"
NAME = re.compile(r"[A-Za-zÄÖÜäöüß0-9 ._-]{1,30}")
_lock = threading.RLock()

# Where each tool goes: a target of the picture. Every tool of chat.py and the extras must be here
# (tests/test_live.py), so a new tool shows on the monitor too (Dominik 2026-10-10: keep it current).
TOOLS = {
    "calendar_add": "cal", "calendar_events": "cal", "daily_briefing": "cal", "tasks_add": "cal", "tasks_change": "cal",
    "tasks_show": "cal", "home_assistant": "ha", "home_assistant_action": "ha", "home_assistant_history": "ha",
    "home_assistant_states": "ha", "home_assistant_todo": "ha", "web_search": "web", "read_page": "web",
    "archive_search": "kiwix", "article_more": "wiki", "wikipedia": "wiki", "mail_draft": "mail", "mail_list": "mail",
    "mail_read": "mail", "mail_search": "mail", "mail_tidy_overview": "mail", "mail_tidy_propose": "mail",
    "contacts_search": "contacts", "remarkable_note": "rm", "iphone_action": "push", "weather": "weather",
    "parcels": "parcels", "transit": "transit", "document_search": "mem", "history_search": "mem", "local_search": "mem",
    "memory_forget": "mem", "memory_save": "mem", "reminder_cancel": "mem", "reminder_list": "mem", "reminder_set": "mem",
    "message_announce": "mem", "message_read": "mem", "message_send": "mem", "agent_list": "mem",
    "agent_schedule": "mem", "agent_task": "mem", "routine_save": "mem",
    # steps the panel runs itself (tracelog "… (Panel)")
    "Erst lokal": "mem", "remarkable": "rm", "Ablauf": "mem",
}
# The targets: name, short line, zone (spark = on this machine, lan = home network, net = internet), fixed = always shown
TARGETS = {
    "qwen": ("Sprachmodell qwen38", "LLM · auf dem Spark", "spark", True),
    "ha": ("Home Assistant", "HTTP · Heimnetz", "lan", True),
    "web": ("Websuche", "SearXNG · Heimnetz", "lan", True),
    "kiwix": ("Kiwix", "Archiv · Heimnetz", "lan", True),
    "mem": ("Spark-Speicher", "Dokumente, Erinnerungen", "spark", False),
    "cal": ("Kalender", "CalDAV · Internet", "net", True),
    "mail": ("Mail", "IMAP · Internet", "net", True),
    "contacts": ("Kontakte", "CardDAV · Internet", "net", False),
    "wiki": ("Wikipedia", "HTTPS · Internet", "net", False),
    "weather": ("Wetter", "HTTPS · Internet", "net", False),
    "transit": ("Bahn", "HTTPS · Internet", "net", False),
    "parcels": ("Pakete", "HTTPS · Internet", "net", False),
    "rm": ("reMarkable", "Cloud · Internet", "net", True),
    "push": ("Apple Push", "APNs · Internet", "net", True),
}
RETURNS = {"cal": "Termine oder Aufgaben", "ha": "Zustände oder Schaltung", "web": "Suchergebnisse", "kiwix": "Archiv-Treffer",
           "wiki": "Artikel", "mail": "Mails (nur Anzahl und Größe)", "contacts": "Kontakte", "rm": "Ablage", "push": "Zustellung",
           "weather": "Wetterwerte", "parcels": "Sendungen", "transit": "Verbindungen", "mem": "eigene Daten"}
CLIENT = {"web": "Browser", "speaker": "Lautsprecher", "watch": "Uhr", "siri": "Siri", "telegram": "Telegram",
          "app": "iPhone-App", "car": "CarPlay", "mcp": "MCP-Client", "other": "Gerät"}
VOICE = ("speaker", "watch", "siri", "app", "car")
LEVEL = {"public": "Öffentlich (Seiten aus Suchergebnissen)", "user": "Nutzer-Dienst", "home": "Heimnetz"}

_run = {}                         # request id -> tracelog.Rec while it runs and FADE seconds after
_events = deque(maxlen=100)       # (t, area, text)
_guard = deque(maxlen=60)         # Wächter decisions
_door = deque(maxlen=60)          # who came in from the internet or was turned away
_rets = deque(maxlen=40)          # what tools gave back
_count = {}                       # per day: guard_ok, guard_bad, guard_cut, door_in, door_out
_codes = {}                       # hash of a pairing code -> (until, name)
_seen = {}                        # monitor id -> (last time, address)
_saved = [0.0]                    # last time live-monitors.json was written for "last seen"


def cfg():
    return load_config().get("logs", {}) or {}


def on():
    return cfg().get("live", False) is True


def monitor_on():
    c = cfg()
    return c.get("live", False) is True and c.get("live_monitor", False) is True


def screens():
    try:
        return max(1, min(5, int(cfg().get("live_screens", 3))))
    except (TypeError, ValueError):
        return 3


def _bump(key, now=None):
    day = time.strftime("%Y-%m-%d", time.localtime(now or time.time()))
    if _count.get("day") != day:
        _count.clear()
        _count["day"] = day
    _count[key] = _count.get(key, 0) + 1


def event(area, text, now=None):
    """One line for "Ereignisse": fixed words and numbers only."""
    with _lock:
        _events.append((now or time.time(), area, str(text)[:120]))


def short_ip(ip):
    """89.204.x.x / 2a02:810::x: enough to tell senders apart, not enough to find a person."""
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return "?"
    if a.version == 4:
        return ".".join(str(a).split(".")[:2]) + ".x.x"
    return ":".join(a.exploded.split(":")[:2]) + "::x"


def from_internet(request):
    """The sender (after the trusted reverse proxy) is a public address."""
    try:
        return ipaddress.ip_address(guard.client_ip(request)).is_global
    except ValueError:
        return False


# ------------------------------------------------------------------ hooks (called by other modules; never raise)
def track(rec):
    """tracelog.Rec was created: watch it while it runs."""
    try:
        with _lock:
            _run[rec.id] = rec
            if len(_run) > MAX_RUN:
                for k in sorted(_run, key=lambda k: _run[k].t0)[:len(_run) - MAX_RUN]:
                    _run.pop(k, None)
    except Exception:
        pass


def came_in(request, rec):
    """A request's sender: from the internet it shows under "Über das Internet" and in the Eingang list."""
    try:
        if not from_internet(request):
            return
        rec.net = True
        with _lock:
            _bump("door_in")
            _door.append({"t": time.time(), "ok": True, "who": CLIENT.get(rec.client, "Gerät"), "from": short_ip(guard.client_ip(request)),
                          "why": "Anmeldung gültig, kam über den Proxy",
                          "steps": ["Absender aus X-Forwarded-For des eingetragenen Proxys (panel.trusted_proxies)",
                                    "Anmeldung oder Geräteschlüssel gültig", "Rate-Limit eingehalten"]})
    except Exception:
        pass


def key_call(request, who, why):
    """A device key call outside a chat request (Home Assistant events, hamelden.py): a line under
    "Ereignisse" and, from the internet, an entry in Eingang. Fixed words only."""
    try:
        event(who, why)
        if not from_internet(request):
            return
        with _lock:
            _bump("door_in")
            _door.append({"t": time.time(), "ok": True, "who": who, "from": short_ip(guard.client_ip(request)), "why": why,
                          "steps": ["Absender aus X-Forwarded-For des eingetragenen Proxys (panel.trusted_proxies)",
                                    "Geräteschlüssel gültig (Bereich haev)", "Rate-Limit eingehalten"]})
    except Exception:
        pass


def step(rec, s):
    """A step was added to a watched request: tool steps also go to "Was die Dienste zurückgeben"."""
    try:
        if s["k"] != "tool":
            return
        name = s["n"][:-8] if s["n"].endswith(" (Panel)") else s["n"]
        tgt = TOOLS.get(name, "")
        x = s.get("x") or {}
        ok = x.get("ok", True) is not False
        chars = x.get("chars")
        with _lock:
            _rets.append({"t": rec.t0 + (s["a"] + s["d"]) / 1000, "req": rec.id, "tool": name, "to": tgt, "ok": ok,
                          "what": RETURNS.get(tgt, "Antwort"), "size": chars if isinstance(chars, int) else None, "ms": s["d"]})
            _events.append((time.time(), "Werkzeug", f"{rec.id} · {name} → {TARGETS[tgt][0] if tgt else 'Spark'}"
                                                      f"{'' if ok else ' · nicht ok'}"))
    except Exception:
        pass


def ended(rec, now=None):
    try:
        now = now or time.time()
        rec.t_end = now
        status = rec.status()
        event("Anfrage", f"{rec.id} fertig in {max(0, now - rec.t0):.1f} s".replace(".", ",")
              + (f" · {rec.intent}" if rec.intent else "") + (" · Fehler" if status == "err" else ""), now)
    except Exception:
        pass


def outgoing(host, port, level, ip, why):
    """netguard.resolve decided about one connection (called in a worker thread)."""
    try:
        if not on():
            return
        try:
            a = ipaddress.ip_address(str(ip).split("%")[0])
        except ValueError:
            a = None
        public = bool(a and a.is_global)
        shown = "Webseite" if (level == "public" and not why) else str(host)[:60]
        if why:
            shown = f"{ip}:{port}"
        steps = [f"Name einmal aufgelöst → {'öffentliche Adresse' if public else 'Heimnetz- oder eigene Adresse'}",
                 f"Stufe {LEVEL.get(level, level)}"]
        if why:
            reason = ("eigene Dienste des Spark sind so nicht erreichbar" if "own services" in why
                      else "nur öffentliche Internet-Adressen" if "only public" in why
                      else "Heimnetz-Adressen sind für Nutzer-Dienste aus (Einstellungen → Sicherheit)" if "home network" in why
                      else "diese Adresse ist nie erlaubt (Link-lokal, Multicast, reserviert)")
            steps.append("→ geblockt, die Verbindung kommt nicht zustande")
        else:
            reason = ("öffentliche Adresse" if public else "Heimnetz-Adresse ist auf dieser Stufe erlaubt")
            steps += ["verbunden genau mit der geprüften Adresse (gegen DNS-Rebinding)", "Antwort-Grenze 20 MB"]
        with _lock:
            _bump("guard_bad" if why else "guard_ok")
            _guard.append({"t": time.time(), "ok": not why, "to": shown, "level": LEVEL.get(level, level), "why": reason, "steps": steps})
            if why:
                _events.append((time.time(), "Wächter", f"{shown} geblockt: {reason}"))
    except Exception:
        pass


def cut(host):
    """netguard: an answer was larger than allowed and was stopped."""
    try:
        if on():
            with _lock:
                _bump("guard_cut")
                _guard.append({"t": time.time(), "ok": None, "to": "Webseite", "level": "", "why": "Antwort größer als 20 MB, abgebrochen",
                               "steps": ["Antwort-Grenze 20 MB (auch entpackt)", "→ abgebrochen, nur bis dahin gelesen"]})
    except Exception:
        pass


def refused(request, what, locked=0):
    """guard.failed: a wrong login or code. Shown in the Eingang list (sender shortened)."""
    try:
        if not on():
            return
        word = {"login": "Anmeldung", "handoff_code": "Übergabe-Code", "live_code": "Monitor-Code", "profile_login": "Profil-Anmeldung",
                "mfa": "zweiter Schritt", "pin": "PIN"}.get(what, "Anmeldung")
        steps = [("kam aus dem Internet" if from_internet(request) else "kam aus dem Heimnetz"), f"{word} falsch"]
        if locked:
            steps.append(f"→ Absender {int(locked) // 60 or 1} min gesperrt, steht im Admin-Protokoll")
        with _lock:
            _bump("door_out")
            _door.append({"t": time.time(), "ok": False, "who": word, "from": short_ip(guard.client_ip(request)),
                          "why": f"{word} falsch" + (" · gesperrt" if locked else ""), "steps": steps})
            _events.append((time.time(), "Eingang", f"{word} falsch von {short_ip(guard.client_ip(request))}"))
    except Exception:
        pass


def _door_no(request, why, steps):
    with _lock:
        _bump("door_out")
        _door.append({"t": time.time(), "ok": False, "who": "Monitor", "from": short_ip(guard.client_ip(request)), "why": why, "steps": steps})


# ------------------------------------------------------------------ the picture
def _now_at(rec, now):
    """Where the request is right now: the step after the last finished one (or the running tool)."""
    if getattr(rec, "t_end", None):
        return "done", ""
    cur = getattr(rec, "cur", None)
    last = rec.steps[-1] if rec.steps else None
    if cur and (not last or cur[2] >= rec.t0 + (last["a"] + last["d"]) / 1000 - 0.01):
        return cur[0], cur[1]
    k = last["k"] if last else "in"
    if k in ("in", "prep"):
        return "weiche", ""
    if k in ("weiche", "tool"):
        return "llm", ""
    if k in ("llm", "check"):
        return ("tts", "") if "first" in rec.marks else ("llm", "")
    return k, ""


def _who(rec, view):
    """(person, device) as this view may show them."""
    import profiles
    if rec.kind == "admin":
        return "Admin", rec.device if view == "admin" else ""
    if rec.kind != "profile" or not rec.who:
        return "Gast", ""
    p = profiles.by_id(rec.who)
    if p and profiles.settings(p["id"]).get("trace_name") is True and (view == "admin" or cfg().get("live_names") is True):
        return p["name"], rec.device
    return ("Profil" if view == "admin" else "Person"), ""


def _gone_from(rec):
    """When a finished request starts to fade: once a newer request came (Dominik 2026-10-10: the last action
    stays until something new comes), never before it ended. None while it is the newest."""
    end = getattr(rec, "t_end", None)
    if not end:
        return None
    newer = [r.t0 for r in _run.values() if r is not rec and r.t0 > rec.t0]
    return max(end, min(newer)) if newer else None


def _req(rec, view, now):
    stage, tool = _now_at(rec, now)
    person, device = _who(rec, view)
    steps = []
    for s in rec.steps:
        n = s["n"][:-8] if s["n"].endswith(" (Panel)") else s["n"]
        x = s.get("x") or {}
        steps.append({"k": s["k"], "n": n, "a": s["a"], "d": s["d"], "ok": x.get("ok", True) is not False,
                      "to": TOOLS.get(n, "") if s["k"] == "tool" else ("qwen" if s["k"] == "llm" else "")})
    end, gone = getattr(rec, "t_end", None), _gone_from(rec)
    return {"id": rec.id, "client": rec.client, "dev": device or CLIENT.get(rec.client, "Gerät"), "who": person,
            "voice": rec.client in VOICE or any((s.get("x") or {}).get("voice") for s in rec.steps[:1]),
            "net": bool(getattr(rec, "net", False)), "intent": rec.intent, "stage": stage, "tool": tool,
            "to": TOOLS.get(tool, "") if stage == "tool" else ("qwen" if stage == "llm" else ""),
            "steps": steps, "marks": dict(rec.marks), "age": round((end or now) - rec.t0, 2),
            "done": bool(end), "left": max(0, int(FADE - (now - gone))) if gone else None, "last": bool(end and not gone),
            "ago": int(now - end) if end else None, "err": bool(rec.errors)}


def _conns(now):
    out = []
    try:
        import esp32
        n = len(getattr(esp32, "_live", {}) or {})
        if n:
            out.append({"name": "Lautsprecher", "proto": "WebSocket", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import telegram
        if (getattr(telegram, "_poller", {}) or {}).get("on"):
            out.append({"name": "Telegram", "proto": "Long-Poll · Internet", "dir": "aus", "n": 1})
    except Exception:
        pass
    try:
        import mcpserver
        n = sum(1 for v in (getattr(mcpserver, "_busy", {}) or {}).values() if v)
        if n:
            out.append({"name": "MCP-Clients", "proto": "HTTPS", "dir": "ein", "n": n})
    except Exception:
        pass
    try:
        import hamelden
        n = sum(1 for x in list((getattr(hamelden, "_streams", {}) or {}).values()) if x.synced and not x.error)
        if n:
            out.append({"name": "Home Assistant live", "proto": "WebSocket · Heimnetz", "dir": "aus", "n": n})
    except Exception:
        pass
    n = sum(1 for t, _ in _seen.values() if now - t < SEEN_S)
    if n:
        out.append({"name": "Live-Monitore", "proto": "HTTPS · nur lesen", "dir": "ein", "n": n})
    run = [r for r in _run.values() if not getattr(r, "t_end", None)]
    if run:
        out.append({"name": "Laufende Anfragen", "proto": "HTTPS / WebSocket", "dir": "ein", "n": len(run)})
    return out


def _sys():
    try:
        import monitor
        h = list(monitor.history)[-60:]
    except Exception:
        h = []
    last = h[-1] if h else {}
    num = lambda v: round(v, 1) if isinstance(v, (int, float)) else None  # noqa: E731
    return {"gpu": num(last.get("gpu")), "cpu": num(last.get("cpu")), "free": num(last.get("avail")), "temp": num(last.get("temp")),
            "power": num(last.get("power")), "hist": {k: [num(x.get(k)) for x in h] for k in ("gpu", "cpu", "avail")}}


def snapshot(view="admin", now=None):
    now = now or time.time()
    with _lock:
        for k in [k for k, r in _run.items() if (g := _gone_from(r)) and now - g > FADE]:
            _run.pop(k, None)
        reqs = [_req(r, view, now) for r in sorted(_run.values(), key=lambda r: r.t0)]
        cnt = dict(_count) if _count.get("day") == time.strftime("%Y-%m-%d", time.localtime(now)) else {}
        guard_items, door_items = list(_guard)[-12:][::-1], list(_door)[-12:][::-1]
        rets, events = list(_rets)[-12:][::-1], list(_events)[-14:][::-1]
    try:
        import vorrang
        speaking = bool(vorrang.speaking(now))
    except Exception:
        speaking = False
    try:
        import notaus
        held = notaus.for_live()
    except Exception:
        held = {"level": 0}
    used = {s["to"] for r in reqs for s in r["steps"] if s["to"]} | {r["to"] for r in reqs if r["to"]} | {x["to"] for x in rets if now - x["t"] < 60 and x["to"]}
    targets = [{"id": k, "name": v[0], "sub": v[1], "zone": v[2]} for k, v in TARGETS.items() if v[3] or k in used]
    return {"t": round(now, 1), "view": view, "fade": FADE, "reqs": reqs, "targets": targets, "speaking": speaking,
            "guard": {"ok": cnt.get("guard_ok", 0), "bad": cnt.get("guard_bad", 0), "cut": cnt.get("guard_cut", 0), "items": guard_items},
            "door": {"in": cnt.get("door_in", 0), "out": cnt.get("door_out", 0), "items": door_items},
            "rets": rets, "events": [{"t": t, "area": a, "text": x} for t, a, x in events], "conns": _conns(now), "sys": _sys(), "notaus": held}


# ------------------------------------------------------------------ admin view
@router.get("/api/admin/live", dependencies=[Depends(auth)])
def admin_live(request: Request):
    guard.limit(request, "live", admin=True)
    if not on():
        raise HTTPException(404, "live off")
    return snapshot("admin")


# ------------------------------------------------------------------ monitors
def _file():
    return os.path.join(STATE, "live-monitors.json")


def _load():
    try:
        with open(_file()) as f:
            items = json.load(f).get("items", [])
        return [m for m in items if isinstance(m, dict) and re.fullmatch(r"m_[0-9a-f]{8}", str(m.get("id")))
                and re.fullmatch(r"[0-9a-f]{64}", str(m.get("hash")))]
    except (OSError, ValueError, AttributeError):
        return []


def _store(items):
    os.makedirs(STATE, exist_ok=True)
    tmp = _file() + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump({"items": items}, f)
    os.replace(tmp, _file())


def _hash(x):
    return hashlib.sha256(x.encode()).hexdigest()


def _by(request):
    c = request.scope.get("speech_coadmin")
    return "main" if request.scope.get("speech_main_admin") or not c else c.get("id", "coadmin")


@router.get("/api/admin/live/monitors", dependencies=[Depends(auth)])
def monitors(request: Request):
    guard.limit(request, "live", admin=True)
    now = time.time()
    with _lock:
        items = _load()
        return {"on": monitor_on(), "screens": screens(), "codes": sum(1 for u, _ in _codes.values() if u > now),
                "items": [{"id": m["id"], "name": m.get("name", "Monitor"), "created": m.get("created"), "last": max(m.get("last") or 0, _seen.get(m["id"], (0, ""))[0]) or None,
                           "watching": now - _seen.get(m["id"], (0, ""))[0] < SEEN_S, "from": _seen.get(m["id"], (0, m.get("from", "")))[1] or m.get("from", "")} for m in items]}


@router.post("/api/admin/live/monitors", dependencies=[Depends(auth)])
async def monitor_new(request: Request):
    """A one-time 6-digit code for a new monitor (10 minutes); the screen enters it on /live."""
    guard.limit(request, "live", admin=True)
    if not monitor_on():
        raise HTTPException(409, "monitor off")
    try:
        body = await request.json()
    except ValueError:
        body = {}
    name = str((body or {}).get("name") or "Monitor").strip()
    if not NAME.fullmatch(name):
        raise HTTPException(400, "name: 1 to 30 letters, digits, spaces, . _ -")
    now = time.time()
    with _lock:
        for k in [k for k, (u, _) in _codes.items() if u <= now]:
            _codes.pop(k, None)
        if len(_codes) >= MAX_CODES:
            raise HTTPException(429, "too many open codes")
        if len(_load()) >= MAX_MONITORS:
            raise HTTPException(409, f"at most {MAX_MONITORS} monitors")
        while True:
            code = f"{secrets.randbelow(10 ** 6):06d}"
            if _hash(code) not in _codes:
                break
        _codes[_hash(code)] = (now + CODE_S, name)
    guard.log("live_monitor_code", by=_by(request), name=name)
    return {"code": code, "until": int(now + CODE_S), "path": "/live"}


@router.delete("/api/admin/live/monitors/{mid}", dependencies=[Depends(auth)])
def monitor_delete(request: Request, mid: str):
    guard.limit(request, "live", admin=True)
    if not re.fullmatch(r"m_[0-9a-f]{8}", mid):
        raise HTTPException(400, "bad id")
    with _lock:
        items = _load()
        if not any(m["id"] == mid for m in items):
            raise HTTPException(404, "not found")
        _store([m for m in items if m["id"] != mid])
        _seen.pop(mid, None)
    guard.log("live_monitor_deleted", by=_by(request), id=mid)
    return {"ok": True}


def _home_only(request):
    """The monitor is for the home network: a sender from the internet is turned away."""
    if from_internet(request):
        _door_no(request, "Monitor-Zugang gilt nur im Heimnetz", ["kam aus dem Internet", "Live-Monitor: nur Heimnetz", "→ abgewiesen (403)"])
        raise HTTPException(403, "the monitor works in the home network only")


@router.get("/live", include_in_schema=False)
def live_page(request: Request):
    """The monitor page (static, its script /static/js/live.js asks /api/live/state)."""
    if not monitor_on():
        raise HTTPException(404, "not found")
    _home_only(request)
    from core import app_version
    ver = re.sub(r"[^A-Za-z0-9.\-]", "", app_version())[:32] or "0"
    with open(os.path.join(STATIC, "live.html"), encoding="utf-8") as f:
        html = f.read().replace("{{V}}", ver)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.post("/api/live/pair")
async def pair(request: Request):
    """The screen enters the code: it gets its own key as a cookie (read-only, this page only)."""
    if not monitor_on():
        raise HTTPException(404, "not found")
    _home_only(request)
    guard.check(request)
    guard.limit(request, "pair")
    try:
        body = await request.json()
    except ValueError:
        body = {}
    code = re.sub(r"\D", "", str((body or {}).get("code") or ""))[:6]
    now = time.time()
    hit = None
    with _lock:
        for k, (until, name) in list(_codes.items()):
            if until > now and len(code) == 6 and hmac.compare_digest(k, _hash(code)):
                hit = name
                _codes.pop(k, None)
                break
    if not hit:
        guard.failed(request, what="live_code")
        import asyncio
        await asyncio.sleep(1)
        raise HTTPException(401, "wrong or expired code")
    token = "sl_" + secrets.token_urlsafe(32)
    mid = "m_" + secrets.token_hex(4)
    with _lock:
        items = _load()
        items.append({"id": mid, "name": hit, "hash": _hash(token), "created": int(now), "last": int(now),
                      "from": short_ip(guard.client_ip(request))})
        _store(items[-MAX_MONITORS:])
    guard.succeeded(request)
    guard.log("live_monitor_paired", name=hit, ip=guard.client_ip(request))
    event("Monitor", f"{hit} gekoppelt", now)
    r = JSONResponse({"ok": True, "name": hit})
    r.set_cookie(COOKIE, token, max_age=KEEP_DAYS * 86400, httponly=True, samesite="strict", secure=guard.https(request), path="/")
    return r


def monitor_of(request, now=None):
    """The paired monitor this request's cookie belongs to, or None."""
    token = request.cookies.get(COOKIE, "")
    if not token.startswith("sl_") or len(token) > 80:
        return None
    h, now = _hash(token), now or time.time()
    with _lock:
        for m in _load():
            if hmac.compare_digest(m["hash"], h):
                if now - max(m.get("last") or 0, _seen.get(m["id"], (0, ""))[0]) > KEEP_DAYS * 86400:
                    return None
                return m
    return None


@router.get("/api/live/state")
def state(request: Request):
    """What a paired monitor shows: like the admin view, names only when allowed twice."""
    if not monitor_on():
        raise HTTPException(404, "not found")
    _home_only(request)
    guard.limit(request, "livemon")
    m = monitor_of(request)
    if not m:
        raise HTTPException(401, "pair this screen first")
    now = time.time()
    with _lock:
        watching = [k for k, (t, _) in _seen.items() if now - t < SEEN_S and k != m["id"]]
        if len(watching) >= screens():
            raise HTTPException(429, f"at most {screens()} screens at once")
        _seen[m["id"]] = (now, short_ip(guard.client_ip(request)))
        if now - _saved[0] > 300:     # "last seen" on disk now and then, not every second
            _saved[0] = now
            items = _load()
            for x in items:
                if x["id"] in _seen:
                    x["last"] = int(_seen[x["id"]][0])
            _store(items)
    return dict(snapshot("monitor", now), monitor=m.get("name", "Monitor"))
