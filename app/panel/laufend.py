"""Laufendes: the one list of what is talking right now, so Notaus stage 3 „Alles still“ ends it at once.

Each answer that streams (chat.py: web, apps, Begleiter, Telegram, Siri, speakers, phone), each phone call (telefon.py)
and each Home Assistant session (wyoming.py) puts itself here while it runs and takes itself out at its end
(Paket „Abbrechen heißt aus“, Dominik 2026-11-10 4a). notaus.after_change calls end_all: every entry's own way to end
runs (the chat stream says "ende" with the kind "notaus" and stops, a call ends, a session closes). Only kinds and
numbers go to the journal and to Live, never what was said."""
import itertools
import threading

KINDS = ("chat", "telefon", "wyoming")
_lock = threading.Lock()
_ids = itertools.count(1)
_running = {}          # id -> (kind, stop)
_ended = {k: 0 for k in KINDS}   # ended by Notaus since the panel started (Live: numbers only)


def add(kind, stop):
    """Something of `kind` talks now; stop() ends it (called once, never raises out). Returns the token for drop."""
    if kind not in KINDS:
        raise ValueError("unknown kind")
    n = next(_ids)
    with _lock:
        _running[n] = (kind, stop)
    return n


def drop(token):
    with _lock:
        _running.pop(token, None)


def counts():
    """{kind: number running now} for every kind."""
    with _lock:
        got = [k for k, _ in _running.values()]
    return {k: got.count(k) for k in KINDS}


def ended():
    return dict(_ended)


def end_all(why="notaus"):
    """Ends everything that runs; {kind: number ended}. One journal line with the numbers."""
    with _lock:
        items = list(_running.items())
        _running.clear()
    out = {k: 0 for k in KINDS}
    for _, (kind, stop) in items:
        try:
            stop()
            out[kind] += 1
        except Exception as e:
            print(f"notaus: laufendes {kind} nicht beendet", type(e).__name__, flush=True)
    for k, v in out.items():
        _ended[k] += v
    print(f"notaus: laufendes beendet | {why} | " + " | ".join(f"{k} {v}" for k, v in out.items()), flush=True)
    try:
        import live
        if sum(out.values()):
            live.mark("Notaus", f"Laufendes beendet: {sum(out.values())}")
    except Exception:
        pass
    return out
