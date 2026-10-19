"""Aktiv in den letzten 10 Minuten (Dominik 2026-10-17, "1b 2a 3a"): how many people used the Spark lately.

Every request that a person starts (chat, voice, speaker, app, phone, Wyoming, MCP, Begleiter) passes tracelog.start,
which hands it here before its own switches: the count works also while Logs → Anfragen and Zustand → Live are off.
What the Spark does by itself (rules, schedules, jobs) never counts.

    profile     one per profile (the admin without a profile counts as one); never a name
    guest       one per device: the device key's name, else the sender's address, kept only as a short
                keyed hash (a new key at every start)

Kept in memory only (gone after a restart), at most MAX entries, each forgotten FENSTER_S after its last request.
Shown as numbers only: the OLED page "Aktiv 10 min" (gehaeuse.py), Zustand → Überblick "Heute", Zustand → Live,
the Steuerzentrale and the iPhone app's Zustand.
"""
import hashlib
import hmac
import secrets
import threading
import time

FENSTER_S = 600     # "aktiv" means at least one request in the last 10 minutes
MAX = 2000          # more keys than this: the oldest go first (a flood of guests cannot grow the memory)

_lock = threading.Lock()
_seen = {}          # key -> time of the last request; "p:<profile id>" or "g:<hash>"
_SALZ = secrets.token_bytes(16)   # new at every start: a guest's hash cannot be turned back into an address


def schluessel(who, kind, client, device="", ort=""):
    """The key a request counts under, or None when it does not count (the Spark itself)."""
    if kind == "spark" or client == "auto":
        return None
    if who:
        return "p:" + str(who)
    if kind == "admin":
        return "p:admin"
    roh = f"{client}|{device}|{'' if device else ort}"
    return "g:" + hmac.new(_SALZ, roh.encode(), hashlib.sha256).hexdigest()[:16]


def sah(t, who, kind, client, device="", ort=""):
    """A request came in (tracelog.start). Never raises."""
    try:
        k = schluessel(who, kind, client, device, ort)
        if k is None:
            return
        with _lock:
            _seen[k] = max(float(t), _seen.get(k, 0.0))
            if len(_seen) > MAX:
                for x in sorted(_seen, key=_seen.get)[:len(_seen) - MAX]:
                    _seen.pop(x, None)
    except Exception:
        pass


def zahlen(now=None):
    """{"gesamt", "profile", "gaeste"}: who had a request in the last FENSTER_S seconds (numbers only)."""
    now = time.time() if now is None else now
    with _lock:
        for k in [k for k, t in _seen.items() if now - t > FENSTER_S]:
            _seen.pop(k, None)
        p = sum(1 for k in _seen if k.startswith("p:"))
        g = sum(1 for k in _seen if k.startswith("g:"))
    return {"gesamt": p + g, "profile": p, "gaeste": g}
