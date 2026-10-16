"""Zustand → Praxistest (plan plaene/verbesserungen-2026-10-16.md, Dominik 2026-10-16 "alles umsetzten", 4a): the
points of the hands-on test, for admins only.

Every function gets a point that an admin tries out in daily use (guideline part 1, line 19). The points are one
list in this repository, praxistest.json next to this file (until V01.0.688 they were a file in the project folder
the panel never saw): number, version, title, steps, thread. A new function adds its point at the end with the next
number; numbers never change and are never used twice (tests/test_praxistest.py).

The page shows what is still open, the newest first; every way in a step („Funktionen → …“) becomes a jump link by
itself (way.js). Per point the admin marks „Klappt“, „Problem“ or „Später“; „Problem“ opens Zustand → Logs →
Diagnose with the point's number to copy for the thread. Points older than ALT_BIS that nobody marked are folded
away as „alt, vermutlich erledigt“ (4a), with one button that marks them all as done.

Kept is only the mark per point (STATE/praxistest-stand.json: number → word and time), never a text. Logs: fixed
words and the number. „Braucht dich“ shows a quiet line with the count (level info, never red); the Live view, the
Steuerzentrale and the iPhone app's "Spark verwalten" take it from there (health.alerts). No switch: the page does
nothing by itself and only admins see it, like Zustand → Modelle and Technik.

The steps are written in German by the threads that build the function, for the admin's hands-on test; in English the
page names that once instead of translating every step.
"""
import json
import os
import re
import sys
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import guard  # noqa: E402
from common import STATE, read_json, write_json  # noqa: E402
from core import auth  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PUNKTE_FILE = os.path.join(HERE, "praxistest.json")
STAND_FILE = os.path.join(STATE, "praxistest-stand.json")
ALT_BIS = 600              # points before V01.0.600 nobody marked are folded away (Dominik 2026-10-16, 4a)
STAENDE = ("ok", "problem", "spaeter", "erledigt")   # erledigt: the button for all old points at once
WORT = {"ok": "klappt", "problem": "problem", "spaeter": "spaeter", "erledigt": "erledigt", "offen": "offen"}
ID = re.compile(r"P\d{3,4}")
MAX_BODY = 256
_lock = threading.Lock()
_punkte = {"mtime": None, "v": []}


def punkte():
    """The list from praxistest.json (read again when the file changed with an update)."""
    try:
        mt = os.path.getmtime(PUNKTE_FILE)
    except OSError:
        return []
    with _lock:
        if _punkte["mtime"] != mt:
            try:
                with open(PUNKTE_FILE, encoding="utf-8") as f:
                    raw = json.load(f).get("punkte") or []
            except (OSError, ValueError):
                raw = []
            _punkte.update(mtime=mt, v=[p for p in raw if isinstance(p, dict) and ID.fullmatch(str(p.get("id", "")))])
        return _punkte["v"]


def stand():
    d = read_json(STAND_FILE, {})
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if ID.fullmatch(k) and isinstance(v, dict) and v.get("s") in STAENDE}


def alt(p):
    """A point from before ALT_BIS, unless its thread marked it as still waiting (aktuell)."""
    return isinstance(p.get("v"), int) and p["v"] < ALT_BIS and not p.get("aktuell")


def seite(st=None):
    """The page: every point with its mark, the newest first, and the counts."""
    st = stand() if st is None else st
    out, n = [], {"offen": 0, "ok": 0, "problem": 0, "spaeter": 0, "erledigt": 0, "alt": 0}
    for p in punkte():
        s = (st.get(p["id"]) or {}).get("s") or ("erledigt" if p.get("erledigt") else "")
        a = not s and alt(p)
        n["alt" if a else (s or "offen")] += 1
        out.append({"id": p["id"], "v": p.get("v"), "titel": p.get("titel", ""), "text": p.get("text", ""),
                    "thread": p.get("thread", ""), "stand": s, "alt": a,
                    "zeit": (st.get(p["id"]) or {}).get("t")})
    out.sort(key=lambda x: (-(x["v"] or 0), x["id"]))
    return {"punkte": out, "zahlen": n, "alt_bis": ALT_BIS}


def _merke(ids, s, now=None):
    now = int(time.time() if now is None else now)
    with _lock:
        d = stand()
        for pid in ids:
            if s == "offen":
                d.pop(pid, None)
            else:
                d[pid] = {"s": s, "t": now}
        write_json(STAND_FILE, d, mode=0o600)


def alerts():
    """„Braucht dich“: a quiet line with the open points (level info), the problems named apart."""
    try:
        n = seite()["zahlen"]
    except Exception:
        return []
    if not n["offen"] and not n["problem"]:
        return []
    teile = []
    if n["offen"]:
        teile.append("1 Praxistest ist offen" if n["offen"] == 1 else f"{n['offen']} Praxistests sind offen")
    if n["problem"]:
        teile.append("1 hat ein Problem" if n["problem"] == 1 else f"{n['problem']} haben ein Problem")
    return [{"kind": "praxistest", "level": "info", "go": "Zustand → Praxistest", "text": ", ".join(teile) + "."}]


router = APIRouter()


@router.get("/api/admin/praxistest", dependencies=[Depends(auth)])
def admin_praxistest(request: Request):
    guard.limit(request, "praxistest", None, True)
    return seite()


@router.post("/api/admin/praxistest/alt", dependencies=[Depends(auth)])
async def admin_alt(request: Request):
    """„Alle erledigt“: every old point nobody marked counts as done."""
    guard.limit(request, "praxistest", None, True)
    await core.json_body(request, MAX_BODY, lenient=True)
    ids = [p["id"] for p in seite()["punkte"] if p["alt"]]
    _merke(ids, "erledigt")
    print(f"praxistest: alt erledigt {len(ids)}", flush=True)
    return {"ok": True, "n": len(ids)}


@router.post("/api/admin/praxistest/{pid}", dependencies=[Depends(auth)])
async def admin_mark(request: Request, pid: str):
    guard.limit(request, "praxistest", None, True)
    body = await core.json_body(request, MAX_BODY)
    s = body.get("stand")
    if not ID.fullmatch(pid) or pid not in {p["id"] for p in punkte()}:
        print("praxistest: abgelehnt punkt", flush=True)
        raise HTTPException(404, "Diesen Prüfpunkt gibt es nicht.")
    if s not in STAENDE + ("offen",) or s == "erledigt":
        print("praxistest: abgelehnt stand", flush=True)
        raise HTTPException(400, "ungültig")
    _merke([pid], s)
    print(f"praxistest: {WORT[s]} {pid}", flush=True)
    return {"ok": True}
