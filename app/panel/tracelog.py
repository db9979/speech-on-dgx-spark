"""Zustand → Logs → Anfragen (V01.0.262): the way of each request through the panel, step by step, for the
admin: arrival, preparation, the switch (intent.py), every round of the language model, every tool, the
answer check and the speech output, each with its time.

Off by default (admin switch logs.trace). Only ways, tool names and numbers are kept: never the question,
the answer, tool arguments or results, outside text or secrets. Every text that goes in is a fixed word
from the panel or passes SAFE (tool names only from the tools the turn offered). A profile's name and
device show only while that profile allows it (its switch "trace_name", Ich → Gespräch); else the
request is "Profil". Guests are "Gast". Kept for 48 hours at most, 500 requests, 40 steps each, in
STATE/traces.jsonl (not in backups). Main admin and profiles with the role Admin read it (not the Verwalter role).
A person's 👍/👎 for the answer (faelle.rate) is added to its request by vote(): only the thumb, the fixed
reason word (faelle.REASONS), the seconds after the answer and the case id, never the note or the question
(Dominik 2026-10-12: „den Daumen anzeigen ob hoch oder runter“). A changed vote replaces the old one.
"""
import json
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
from common import STATE, load_config
from core import auth

router = APIRouter()
KEEP_S, MAX_TRACES, MAX_STEPS, MAX_INFO = 48 * 3600, 500, 40, 12
SLOW_S = 5.0          # first sound later than this (or no sound and longer than this): "langsam"
CLIENTS = ("web", "speaker", "telefon", "watch", "siri", "telegram", "app", "car", "mcp", "ha", "auto", "desk", "tui", "other")
# channels that only speak, without a screen (an own speaker, a call: telefon.py): no buttons, no cards, short answers
NO_SCREEN = ("speaker", "telefon")
KINDS = ("in", "prep", "asr", "weiche", "llm", "tool", "check", "tts", "ack", "err")
MARKS = ("first", "sound", "ack", "end")   # ack: the ready-made sentence (ack.py), never the answer
SAFE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ .,:+()/äöüÄÖÜß-]{0,59}")
ID = re.compile(r"[0-9a-f]{6}")
MINUTES = (10, 60, 120, 720, 1440, 2880)
_lock = threading.Lock()


def _file():
    return os.path.join(STATE, "traces.jsonl")


def on():
    return load_config().get("logs", {}).get("trace", False) is True


def safe(v):
    """A value that may go into a trace: a number, a bool or a short fixed word; anything else is dropped."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(v, 3) if isinstance(v, float) else v
    if isinstance(v, str) and SAFE.fullmatch(v):
        return v
    return None


class Rec:
    """One request on its way. t0 is when the request came in (epoch seconds)."""

    def __init__(self, t0, client, who=None, kind="guest", device="", persist=True):
        self.id = secrets.token_hex(3)
        self.persist = persist    # kept in traces.jsonl (Logs → Anfragen on); else only watched live
        self.cur = None           # (kind, name, time) of what runs now, for Zustand → Live
        self.t0 = float(t0)
        self.client = client if client in CLIENTS else "other"
        self.who = who if isinstance(who, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", who) else None
        self.kind = kind if kind in ("profile", "guest", "admin", "spark") else "guest"
        self.device = safe(str(device or "")[:40]) or ""
        self.intent, self.steps, self.marks, self.errors, self.done = "", [], {}, [], False

    def ms(self, t):
        return max(0, int(round((float(t) - self.t0) * 1000)))

    def step(self, kind, name, start, end=None, **info):
        if kind not in KINDS or len(self.steps) >= MAX_STEPS:
            return
        name = safe(str(name)[:60]) or "unbekannt"
        info = {k: v for k, v in ((k, safe(v)) for k, v in list(info.items())[:MAX_INFO])
                if v is not None and re.fullmatch(r"[a-z_]{1,20}", k)}
        a = self.ms(start)
        self.steps.append({"k": kind, "n": name, "a": a, "d": max(0, self.ms(end if end is not None else start) - a),
                           **({"x": info} if info else {})})
        if getattr(self, "watched", False):
            import live
            live.step(self, self.steps[-1])

    def now(self, kind, name, t=None):
        """What starts right now (a tool call): only for the live picture, never stored."""
        if kind in KINDS:
            self.cur = (kind, safe(str(name)[:60]) or "unbekannt", time.time() if t is None else t)

    def mark(self, name, t):
        if name in MARKS and name not in self.marks:
            self.marks[name] = self.ms(t)

    def fail(self, code):
        code = str(code or "error")[:30]
        if re.fullmatch(r"[a-z0-9_]{1,30}", code) and code not in self.errors and len(self.errors) < 5:
            self.errors.append(code)

    def status(self):
        if self.errors:
            return "err"
        end = self.marks.get("end", 0) / 1000
        sound = self.marks.get("sound")
        return "slow" if (sound / 1000 if sound is not None else end) > SLOW_S else "ok"

    def data(self):
        return {"id": self.id, "t": round(self.t0, 3), "client": self.client, "who": self.who, "kind": self.kind,
                "device": self.device, "intent": self.intent, "steps": self.steps, "marks": self.marks,
                "errors": self.errors, "status": self.status()}


def start(t0, client, who=None, kind="guest", device=""):
    """A new record, or None while both admin switches are off (then nothing is kept at all). With only
    Zustand → Live on (live.py) the record is watched in memory and never written; with only the
    Einstellungs-Assistent on (faelle.py) it is summed up at the end of the answer and never written."""
    try:
        import faelle
        import live
        keep, watch = on(), live.on()
        if not keep and not watch and not faelle.wanted():
            return None
        rec = Rec(t0, client, who, kind, device, persist=keep)
        if watch:
            rec.watched = True
            live.track(rec)
        return rec
    except Exception:
        return None


def line(d):
    """The journal line for one finished request (no name: the journal is not bound to the profile's switch)."""
    tools = ", ".join(f"{s['n']} {'ok' if (s.get('x') or {}).get('ok', True) else 'nicht ok'}"
                      for s in d["steps"] if s["k"] == "tool")[:200]
    m = d["marks"]
    return (f"anfrage: {d['id']} | {d['client']} | {d['intent'] or '-'} | {tools or 'keine Werkzeuge'} | "
            + (f"Rückmeldung {m['ack'] / 1000:.1f} s | " if "ack" in m else "")
            + (f"erster Ton {m['sound'] / 1000:.1f} s | " if "sound" in m else "")
            + f"fertig {m.get('end', 0) / 1000:.1f} s | " + (", ".join(d["errors"]) if d["errors"] else d["status"]))


def finish(rec, now=None):
    """Keeps the finished record (called once; off the event loop) and writes its journal line."""
    if rec is None or rec.done:
        return
    rec.done = True
    rec.mark("end", time.time() if now is None else now)
    if getattr(rec, "watched", False):
        import live
        live.ended(rec, now)
    if not rec.persist:
        return
    d = rec.data()
    print(line(d), flush=True)
    with _lock:
        os.makedirs(STATE, exist_ok=True)
        with open(_file(), "a") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
        if os.path.getsize(_file()) > 2 * 1024**2 or len(_read()) > 2 * MAX_TRACES:
            _write(_keep(_read(), time.time() if now is None else now))


def _read():
    try:
        with open(_file()) as f:
            rows = []
            for ln in f.readlines()[-4 * MAX_TRACES:]:
                try:
                    x = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(x, dict) and isinstance(x.get("t"), (int, float)) and ID.fullmatch(str(x.get("id"))):
                    rows.append(x)
            return rows
    except OSError:
        return []


def _keep(rows, now):
    return [x for x in rows if now - KEEP_S <= x["t"] <= now + 60][-MAX_TRACES:]


def _write(rows):
    tmp = _file() + ".tmp"
    with open(tmp, "w") as f:
        f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
    os.replace(tmp, _file())


VOTES = ("gut", "schlecht")


def vote(tid, v, grund="", case=None, now=None):
    """Puts the person's newest 👍/👎 on its request (Logs → Anfragen). False when the request is not kept."""
    if not tid or not ID.fullmatch(str(tid)) or v not in VOTES:
        return False
    import faelle
    now = time.time() if now is None else now
    with _lock:
        rows = _keep(_read(), now)
        x = next((r for r in rows if r["id"] == tid), None)
        if x is None:
            return False
        end = x["t"] + ((x.get("marks") or {}).get("end") or 0) / 1000
        x["vote"] = {"v": v, "grund": grund if v == "schlecht" and grund in faelle.REASONS else "",
                     "after": max(0, round(now - end)), "case": case if isinstance(case, str) and
                     re.fullmatch(r"[0-9a-f]{8}", case) else ""}
        _write(rows)
    print(f"anfrage: {tid} bewertet {v}", flush=True)
    return True


def all_traces(now=None):
    with _lock:
        return _keep(_read(), time.time() if now is None else now)


def clear():
    with _lock:
        _write([])


def shown(x):
    """One record as the admin sees it: the name and device only with the profile's consent."""
    import profiles
    who, name, device = x.get("who"), "Gast", ""
    if x.get("kind") == "admin":
        name, device = "Admin", x.get("device") or ""
    elif x.get("kind") == "spark":
        name = "Spark"            # the Spark started it itself (update check, backup, rules): nobody asked
    elif x.get("kind") == "profile":
        p = profiles.by_id(who) if who else None
        if p and profiles.settings(p["id"]).get("trace_name") is True:
            name, device = p["name"], x.get("device") or ""
        else:
            name = "Profil"
    out = {k: x.get(k) for k in ("id", "t", "client", "intent", "steps", "marks", "errors", "status", "vote")}
    out.update(name=name, device=device, named=name not in ("Gast", "Profil"))
    return out


@router.get("/api/admin/traces", dependencies=[Depends(auth)])
def traces(request: Request, minutes: int = 60):
    guard.limit(request, "logs", admin=True)
    if minutes not in MINUTES:
        raise HTTPException(400, "bad time")
    now = time.time()
    rows = [shown(x) for x in all_traces(now) if x["t"] >= now - minutes * 60]
    import faelle
    import features
    import klartext
    return {"on": on(), "keep_hours": KEEP_S // 3600, "slow_s": SLOW_S, "items": rows[::-1],
            # an error code as a plain sentence (klartext.CODES, the one source for Verbessern and Erklären too)
            "codes": {c: list(klartext.code_text(c)) for c in {e for x in rows for e in x.get("errors") or []}},
            "explain": features.admin_on("beratererklaeren"),
            "reasons": faelle.REASONS}   # the fixed words for a 👎 (vote)   # „Erklären“ of the Einstellungs-Assistent (berater.py)


@router.get("/api/admin/traces/{tid}", dependencies=[Depends(auth)])
def trace_one(request: Request, tid: str):
    """One request plus the journal lines from its time (other requests at the same moment may show too)."""
    guard.limit(request, "logs", admin=True)
    if not ID.fullmatch(tid):
        raise HTTPException(400, "bad id")
    x = next((x for x in all_traces() if x["id"] == tid), None)
    if not x:
        raise HTTPException(404, "not found")
    import logfilter
    end = x["t"] + (x.get("marks") or {}).get("end", 0) / 1000
    rows = logfilter.between(x["t"] - 1, end + 2)
    return dict(shown(x), lines=[{k: r[k] for k in ("t", "area", "level", "msg", "raw")} for r in rows[-200:]])


@router.delete("/api/admin/traces", dependencies=[Depends(auth)])
def traces_clear(request: Request):
    guard.limit(request, "logs", admin=True)
    clear()
    print("anfrage: all requests deleted by the admin", flush=True)
    return {"ok": True}
