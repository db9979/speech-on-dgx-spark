"""Zustand → Logs → Anfragen (V01.0.262): the way of each request through the panel, step by step, for the
admin: arrival, preparation, the switch (intent.py), every round of the language model, every tool, the
answer check and the speech output, each with its time.

Off by default (admin switch logs.trace). Only ways, tool names and numbers are kept: never the question,
the answer, tool arguments or results, outside text or secrets. Every text that goes in is a fixed word
from the panel or passes SAFE (tool names only from the tools the turn offered). A profile's name and
device show only while that profile allows it (its switch "trace_name", Ich → Gespräch); else the
request is "Profil". Guests are "Gast". Kept for 48 hours at most, 500 requests, 40 steps each, in
STATE/traces.jsonl (not in backups). Main admin and co-admins read it (not the Verwalter role).
"""
import json
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import guard
from common import load_config
from core import auth

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
KEEP_S, MAX_TRACES, MAX_STEPS, MAX_INFO = 48 * 3600, 500, 40, 12
SLOW_S = 5.0          # first sound later than this (or no sound and longer than this): "langsam"
CLIENTS = ("web", "speaker", "watch", "siri", "telegram", "app", "car", "mcp", "other")
KINDS = ("in", "prep", "weiche", "llm", "tool", "check", "tts", "err")
MARKS = ("first", "sound", "end")
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

    def __init__(self, t0, client, who=None, kind="guest", device=""):
        self.id = secrets.token_hex(3)
        self.t0 = float(t0)
        self.client = client if client in CLIENTS else "other"
        self.who = who if isinstance(who, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", who) else None
        self.kind = kind if kind in ("profile", "guest", "admin") else "guest"
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
    """A new record, or None while the admin switch is off (then nothing is kept at all)."""
    try:
        return Rec(t0, client, who, kind, device) if on() else None
    except Exception:
        return None


def line(d):
    """The journal line for one finished request (no name: the journal is not bound to the profile's switch)."""
    tools = ", ".join(f"{s['n']} {'ok' if (s.get('x') or {}).get('ok', True) else 'nicht ok'}"
                      for s in d["steps"] if s["k"] == "tool")[:200]
    m = d["marks"]
    return (f"anfrage: {d['id']} | {d['client']} | {d['intent'] or '-'} | {tools or 'keine Werkzeuge'} | "
            + (f"erster Ton {m['sound'] / 1000:.1f} s | " if "sound" in m else "")
            + f"fertig {m.get('end', 0) / 1000:.1f} s | " + (", ".join(d["errors"]) if d["errors"] else d["status"]))


def finish(rec, now=None):
    """Keeps the finished record (called once; off the event loop) and writes its journal line."""
    if rec is None or rec.done:
        return
    rec.done = True
    rec.mark("end", time.time() if now is None else now)
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
    elif x.get("kind") == "profile":
        p = profiles.by_id(who) if who else None
        if p and profiles.settings(p["id"]).get("trace_name") is True:
            name, device = p["name"], x.get("device") or ""
        else:
            name = "Profil"
    out = {k: x.get(k) for k in ("id", "t", "client", "intent", "steps", "marks", "errors", "status")}
    out.update(name=name, device=device, named=name not in ("Gast", "Profil"))
    return out


@router.get("/api/admin/traces", dependencies=[Depends(auth)])
def traces(request: Request, minutes: int = 60):
    guard.limit(request, "logs", admin=True)
    if minutes not in MINUTES:
        raise HTTPException(400, "bad time")
    now = time.time()
    rows = [shown(x) for x in all_traces(now) if x["t"] >= now - minutes * 60]
    return {"on": on(), "keep_hours": KEEP_S // 3600, "slow_s": SLOW_S, "items": rows[::-1]}


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
