"""Bildschirm zeigen und bedienen (Dominik 2026-10-17, „Rechner fernsteuern“ Stufe 2): the profile looks at its own
PC or Mac from the panel, the iPhone or Android (Ich → Begleiter) and, when the person at the computer allows it,
moves the mouse and types there.

Off until the admin switches chat.desk_view on (Funktionen → Bildschirm zeigen und bedienen) and the device has the
part "view" on (Ich → Begleiter). Only the profile's own devices, never guests. Every session is asked at the
computer itself (Ablehnen / Nur ansehen / Erlauben); while it runs the computer shows a red frame and a bar with
„Beenden“, and the program's own hotkey ends it too. The panel is only a relay: the program sends pictures
(JPEG, at most a few per second), the viewer long-polls the newest one, inputs go the other way. Nothing is
stored: a session keeps only its newest picture in memory and forgets it when it ends; no recording, no history.

Inputs come from fixed lists: a click, a move, a scroll at a point given as 0..1 of the picture, a key from KEYS
(no Windows key, no Cmd, no free combination like Strg+Alt+Entf) or text the viewer typed. The program checks
them again before it does anything.

    browser login (own profile):
    POST   /api/profile/desk/view {did, want: view|control}  -> {"id", "state"} (asks the computer)
    GET    /api/profile/desk/view/{id}?after=n               -> image/jpeg (X-Spark-Seq, -State, -W, -H) or {"state"}
    POST   /api/profile/desk/view/{id}/input {events: [...]} -> {"n"} (only while the computer allowed control)
    DELETE /api/profile/desk/view/{id}                       -> {} (ends it)
    program (device key, part view; the request comes with /api/desk/wait as "views"):
    POST   /api/desk/view/answer {id, mode: no|view|control} -> {"state"}
    POST   /api/desk/view/frame?id=…&w=…&h=… (image/jpeg)    -> {"state"}
    GET    /api/desk/view/input?id=…                         -> {"state", "events"} (held up to INPUT_WAIT s)
    POST   /api/desk/view/end {id}                           -> {}
    POST   /api/desk/view/step {id, n, answer, error?}       -> {} (Stufe 3, bedienen.py: one step done there)

Stufe 3 (bedienen.py, "Spark bedient den Rechner") uses the same session with want "operate": nobody watches in a
browser, the panel's own job reads the pictures and hands the computer one step at a time ("step" in the inputs),
each confirmed there.
"""
import asyncio
import collections
import contextlib
import json
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import begleiter
import guard
import profiles
import schreib
from core import assistant, browser_profile, json_body

router = APIRouter()

ASK_SECONDS = 60          # the person at the computer has this long to answer
VIEW_MAX = 30 * 60        # one session at most this long
VIEWER_IDLE = 30          # nobody looked that long: the session ends
PROGRAM_IDLE = 30         # no picture from the computer that long: the session ends (Stufe 3: four times, a step
                          # waits up to 60 s for its answer at the computer and a Mac dialog may hold the pictures)
FRAME_WAIT = 10           # the viewer's poll waits this long for a newer picture
INPUT_WAIT = 20           # the program's poll waits this long for inputs
MAX_FRAME = 700 * 1024    # one JPEG
MAX_SIDE = 4096
MAX_INPUT_BODY = 16 * 1024
MAX_EVENTS = 40           # per input request
QUEUE = 200               # inputs waiting for the program
TEXT_MAX = 200
OPEN_MAX = 4              # running sessions on the whole Spark
# the keys a viewer may press (the program maps them; Windows key, Cmd and free combinations do not exist)
KEYS = ("enter", "escape", "tab", "backspace", "delete", "space", "up", "down", "left", "right", "home", "end",
        "pageup", "pagedown", "undo", "redo", "copy", "paste", "save", "reload", "find")
BUTTONS = ("left", "right", "double")
MODES = ("view", "control")
WANTS = MODES + ("operate",)
MODE_NAMES = {"view": "ansehen", "control": "bedienen", "operate": "Spark bedient"}
APP_MAX = 200             # the front program's name and path the computer reports with a picture (Stufe 3)
STATES = ("asked", "view", "control", "no", "ended")
STEP_ANSWERS = ("done", "skip", "stop", "failed")

_lock = threading.Lock()
_sessions = {}            # id -> session (memory only)


def allowed(uid):
    """The admin switch and the admin's per-profile block (Freigabe nur durch Admin)."""
    import features
    return bool(uid) and features.allowed("begleiterschirm", uid)


def _log(what, prof, extra=""):
    print(f"begleiter: bildschirm {what}{(' ' + extra) if extra else ''} | {profiles.log_name(prof)}", flush=True)


def _live(text):
    begleiter._live("Bildschirm: " + text)


def _notify(s):
    """Wakes every poll waiting on this session, also from another thread (a tool call) or event loop."""
    for loop, ev in s["waiters"]:
        with contextlib.suppress(RuntimeError):     # that loop is already gone
            loop.call_soon_threadsafe(ev.set)
    s["waiters"] = []


async def _wait(s, seconds):
    w = (asyncio.get_running_loop(), asyncio.Event())
    with _lock:
        s["waiters"].append(w)
    try:
        await asyncio.wait_for(w[1].wait(), seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        with _lock:
            if w in s["waiters"]:
                s["waiters"].remove(w)


def _end(s, why):
    """Ends a session once: the picture is dropped at once, the waiting polls answer."""
    if s["state"] in ("ended", "no"):
        return False
    s["state"] = "no" if why == "abgelehnt" else "ended"
    s["why"] = why
    s["frame"] = b""
    s["inputs"].clear()
    _notify(s)
    return True


def _ended_line(s, why, prof=None):
    prof = prof or profiles.by_id(s["uid"]) or {"id": s["uid"]}
    secs = int(time.time() - (s["since"] or s["t"]))
    _log("ende", prof, f"({why}, {secs} s, {s['seq']} Bilder, {s['events']} Eingaben)")
    _live(f"{MODE_NAMES[s['want'] if s['want'] == 'operate' else s['mode'] or s['want']]} beendet ({why})")


def sweep(now=None):
    """Ends sessions nobody answered, nobody looks at, the computer stopped sending or that ran too long."""
    now = time.time() if now is None else now
    ended = []
    with _lock:
        for k, s in list(_sessions.items()):
            why = ("nicht beantwortet" if s["state"] == "asked" and now - s["t"] > ASK_SECONDS else
                   "zu lange" if now - s["t"] > VIEW_MAX + ASK_SECONDS else
                   # Stufe 3: the panel's own job looks, with its own limits (bedienen.py)
                   "niemand schaut" if s["state"] in MODES and s["want"] != "operate" and now - s["viewer"] > VIEWER_IDLE else
                   "Rechner still" if s["state"] in MODES and now - s["program"] > PROGRAM_IDLE * (4 if s["want"] == "operate" else 1)
                   else "")
            if why and _end(s, why):
                ended.append((s, why))
            if s["state"] in ("ended", "no") and now - s["t"] > ASK_SECONDS and now - s["viewer"] > 2 * FRAME_WAIT:
                _sessions.pop(k, None)
    for s, why in ended:
        _ended_line(s, why)


def counts():
    """Running sessions by kind for Zustand → Live (only numbers)."""
    sweep()
    with _lock:
        return {m: sum(1 for s in _sessions.values() if s["state"] == m and s["want"] != "operate") for m in MODES} | \
            {"asked": sum(1 for s in _sessions.values() if s["state"] == "asked"),
             "operate": sum(1 for s in _sessions.values() if s["state"] == "control" and s["want"] == "operate")}


def asked_for(did, mark=True):
    """Open requests for this computer that its wait has not handed out yet: [{"id", "want", "task"?}]."""
    sweep()
    with _lock:
        out = [s for s in _sessions.values() if s["did"] == did and s["state"] == "asked" and not s["sent"]]
        if mark:
            for s in out:
                s["sent"] = True
        return [{"id": s["id"], "want": s["want"]} | ({"task": s["task"]} if s["task"] else {}) for s in out]


def end_device(did, why):
    """The device lost the part or its key: every session of it ends."""
    ended = []
    with _lock:
        for s in _sessions.values():
            if s["did"] == did and _end(s, why):
                ended.append(s)
    for s in ended:
        _ended_line(s, why)


def start(uid, did, want, now=None, task=""):
    now = time.time() if now is None else now
    if want not in (WANTS if task else MODES):
        raise HTTPException(400, "want: view oder control")
    if not any(x["id"] == did for x in begleiter.devices(uid)):
        raise HTTPException(404, "Diesen Rechner gibt es nicht (Ich → Begleiter).")
    if not begleiter.part_on(uid, did, "view"):
        raise HTTPException(403, "Bildschirm zeigen ist für diesen Rechner aus (Ich → Begleiter).")
    if now - begleiter._seen.get(did, -1e12) > begleiter.ONLINE:
        raise HTTPException(409, "Der Rechner meldet sich gerade nicht. Läuft der Begleiter dort?")
    sweep(now)
    with _lock:
        for s in _sessions.values():
            if s["did"] == did and s["state"] in STATES[:3]:
                _end(s, "neu gefragt")
        if sum(1 for s in _sessions.values() if s["state"] in STATES[:3]) >= OPEN_MAX:
            raise HTTPException(429, "Gerade laufen schon zu viele Bildschirm-Sitzungen.")
        sid = secrets.token_urlsafe(12)
        _sessions[sid] = {"id": sid, "uid": uid, "did": did, "want": want, "mode": None, "state": "asked", "t": now,
                          "since": None, "viewer": now, "program": now, "frame": b"", "seq": 0, "w": 0, "h": 0,
                          "inputs": collections.deque(maxlen=QUEUE), "waiters": [], "sent": False, "why": "",
                          "events": 0, "task": task, "app": "", "exe": "", "answers": {}}
    begleiter.wake(did)
    return _sessions[sid]


def _mine(sid, uid, browser=False):
    with _lock:
        s = _sessions.get(str(sid or "")[:40])
    # a session the Spark itself runs (Stufe 3) is never shown in or steered from a browser
    if not s or s["uid"] != uid or (browser and s["want"] == "operate"):
        raise HTTPException(404, "Diese Sitzung gibt es nicht mehr.")
    return s


def step(s, item):
    """Stufe 3: hands one checked step to the computer (with its inputs); the answer comes to /api/desk/view/step."""
    with _lock:
        if s["state"] != "control" or s["want"] != "operate":
            return False
        s["inputs"].append(dict(item, t="step"))
        _notify(s)
    return True


def _need(prof):
    begleiter._need(prof)
    if not allowed(prof["id"]):
        raise HTTPException(403, "Bildschirm zeigen und bedienen ist aus (Funktionen → Bildschirm zeigen und bedienen).")


def clean_events(raw):
    """The viewer's inputs, each checked; anything else is dropped. Points are 0..1 of the picture."""
    out = []
    for e in raw[:MAX_EVENTS] if isinstance(raw, list) else []:
        if not isinstance(e, dict):
            continue
        kind = e.get("t")
        if kind in ("move", "click"):
            try:
                x, y = float(e.get("x")), float(e.get("y"))
            except (TypeError, ValueError):
                continue
            if not (0 <= x <= 1 and 0 <= y <= 1):
                continue
            ev = {"t": kind, "x": round(x, 4), "y": round(y, 4)}
            if kind == "click":
                if e.get("b", "left") not in BUTTONS:
                    continue
                ev["b"] = e.get("b", "left")
            out.append(ev)
        elif kind == "scroll":
            try:
                dy = int(e.get("dy"))
            except (TypeError, ValueError):
                continue
            if dy:
                out.append({"t": "scroll", "dy": max(-10, min(10, dy))})
        elif kind == "key" and e.get("k") in KEYS:
            out.append({"t": "key", "k": e["k"]})
        elif kind == "text" and isinstance(e.get("s"), str):
            s = "".join(c for c in e["s"] if c == "\n" or c.isprintable())[:TEXT_MAX]
            if s:
                out.append({"t": "text", "s": s})
    return out


# ---------------------------------------------------------------- browser (own profile)
@router.post("/api/profile/desk/view", dependencies=[Depends(assistant)])
async def view_start(request: Request, prof=Depends(browser_profile)):
    _need(prof)
    guard.limit(request, "viewstart", prof["id"])
    body = await json_body(request, begleiter.MAX_BODY)
    s = start(prof["id"], str(body.get("did") or "")[:40], body.get("want"))
    _log("gefragt", prof, f"({MODE_NAMES[s['want']]})")
    _live(f"{MODE_NAMES[s['want']]} gefragt")
    return {"id": s["id"], "state": s["state"]}


@router.get("/api/profile/desk/view/{sid}", dependencies=[Depends(assistant)])
async def view_poll(sid: str, request: Request, after: int = 0, prof=Depends(browser_profile)):
    _need(prof)
    guard.limit(request, "viewframe", prof["id"])
    s = _mine(sid, prof["id"], browser=True)
    s["viewer"] = time.time()
    if s["state"] in MODES and not begleiter.part_on(prof["id"], s["did"], "view"):
        with _lock:
            ended = _end(s, "ausgeschaltet")
        if ended:
            _ended_line(s, "ausgeschaltet", prof)
    if s["state"] in STATES[:3] and not (s["seq"] > after and s["frame"]):
        await _wait(s, FRAME_WAIT)
    s["viewer"] = time.time()
    head = {"X-Spark-State": s["state"], "X-Spark-Seq": str(s["seq"]), "Cache-Control": "no-store"}
    frame = s["frame"]
    if s["state"] in MODES and frame and s["seq"] > after:
        return Response(frame, media_type="image/jpeg",
                        headers=head | {"X-Spark-W": str(s["w"]), "X-Spark-H": str(s["h"])})
    return Response(json.dumps({"state": s["state"], "seq": s["seq"], "why": s["why"]}),
                    media_type="application/json", headers=head)


@router.post("/api/profile/desk/view/{sid}/input", dependencies=[Depends(assistant)])
async def view_input(sid: str, request: Request, prof=Depends(browser_profile)):
    _need(prof)
    guard.limit(request, "viewinput", prof["id"])
    s = _mine(sid, prof["id"], browser=True)
    body = await json_body(request, MAX_INPUT_BODY)
    if s["state"] != "control":
        raise HTTPException(409, "Bedienen hat der Rechner nicht erlaubt." if s["state"] == "view"
                            else "Diese Sitzung läuft nicht mehr.")
    events = clean_events(body.get("events"))
    with _lock:
        s["inputs"].extend(events)
        s["events"] += len(events)
        _notify(s)
    s["viewer"] = time.time()
    return {"n": len(events)}


@router.delete("/api/profile/desk/view/{sid}", dependencies=[Depends(assistant)])
async def view_end(sid: str, request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "viewstart", prof["id"])
    s = _mine(sid, prof["id"], browser=True)
    with _lock:
        ended = _end(s, "im Panel beendet")
    if ended:
        _ended_line(s, "im Panel beendet", prof)
    begleiter.wake(s["did"])
    return {}


# ---------------------------------------------------------------- program (device key, part view)
def _program(request):
    prof, dev = begleiter._program(request)
    if not begleiter.part_on(prof["id"], dev["id"], "view"):
        end_device(dev["id"], "ausgeschaltet")
        raise HTTPException(403, "Bildschirm zeigen ist für dieses Gerät aus (Ich → Begleiter).")
    return prof, dev


def _session_of(prof, dev, sid):
    s = _mine(sid, prof["id"])
    if s["did"] != dev["id"]:
        raise HTTPException(404, "Diese Sitzung gibt es nicht mehr.")
    return s


@router.post("/api/desk/view/answer", dependencies=[Depends(assistant)])
async def program_answer(request: Request):
    prof, dev = _program(request)
    guard.limit(request, "deskact", prof["id"])
    body = await json_body(request, begleiter.MAX_BODY)
    s = _session_of(prof, dev, body.get("id"))
    mode = body.get("mode")
    if mode not in ("no",) + MODES:
        raise HTTPException(400, "mode: no, view oder control")
    if mode == "control" and s["want"] == "view":
        mode = "view"              # nobody asked for more than looking
    if mode == "view" and s["want"] == "operate":
        mode = "no"                # the Spark operating: allowed or not, looking alone makes no sense
    with _lock:
        if s["state"] != "asked":
            raise HTTPException(409, "Diese Sitzung läuft nicht mehr.")
        if mode == "no":
            _end(s, "abgelehnt")
        else:
            s["state"] = s["mode"] = mode
            s["since"] = s["program"] = s["viewer"] = time.time()
            _notify(s)
    if mode == "no":
        _log("abgelehnt", prof)
        _live("am Rechner abgelehnt")
    else:
        name = MODE_NAMES["operate" if s["want"] == "operate" else mode]
        _log("start", prof, f"({name})")
        _live(f"{name} läuft")
    return {"state": s["state"]}


@router.post("/api/desk/view/frame", dependencies=[Depends(assistant)])
async def program_frame(request: Request, id: str = "", w: int = 0, h: int = 0, app: str = "", exe: str = ""):
    prof, dev = _program(request)
    guard.limit(request, "deskframe", prof["id"])
    s = _session_of(prof, dev, id)
    if s["state"] not in MODES:
        return {"state": s["state"]}
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        raise HTTPException(400, f"w, h: 1 bis {MAX_SIDE}")
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > MAX_FRAME:
        raise HTTPException(413, "too large")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_FRAME:
            raise HTTPException(413, "too large")
    if raw[:3] != b"\xff\xd8\xff":
        raise HTTPException(400, "nur JPEG")
    with _lock:
        if s["state"] in MODES:
            s["frame"], s["w"], s["h"] = bytes(raw), w, h
            # the front program (Stufe 3 checks it against the released ones): data, cut and cleaned
            s["app"], s["exe"] = (" ".join("".join(c for c in v if c.isprintable()).split())[:APP_MAX] for v in (app, exe))
            s["seq"] += 1
            s["program"] = time.time()
            _notify(s)
    return {"state": s["state"]}


@router.get("/api/desk/view/input", dependencies=[Depends(assistant)])
async def program_input(request: Request, id: str = ""):
    prof, dev = _program(request)
    guard.limit(request, "deskviewin", prof["id"])
    s = _session_of(prof, dev, id)
    if s["state"] == "control" and not s["inputs"]:
        await _wait(s, INPUT_WAIT)
    with _lock:
        events = list(s["inputs"]) if s["state"] == "control" else []
        s["inputs"].clear()
    return {"state": s["state"], "events": events}


@router.post("/api/desk/view/end", dependencies=[Depends(assistant)])
async def program_end(request: Request):
    prof, dev = begleiter._program(request)
    guard.limit(request, "deskact", prof["id"])
    body = await json_body(request, begleiter.MAX_BODY)
    s = _session_of(prof, dev, body.get("id"))
    with _lock:
        ended = _end(s, "am Rechner beendet")
    if ended:
        _ended_line(s, "am Rechner beendet", prof)
    return {}


@router.post("/api/desk/view/step", dependencies=[Depends(assistant)])
async def program_step(request: Request):
    """Stufe 3: the person's answer to one step at the computer: done (allowed and carried out), skip, stop, failed."""
    prof, dev = _program(request)
    guard.limit(request, "deskact", prof["id"])
    body = await json_body(request, begleiter.MAX_BODY)
    s = _session_of(prof, dev, body.get("id"))
    answer = body.get("answer")
    if s["want"] != "operate" or answer not in STEP_ANSWERS or not isinstance(body.get("n"), int):
        raise HTTPException(400, "n, answer: " + ", ".join(STEP_ANSWERS))
    with _lock:
        s["answers"][body["n"]] = (answer, schreib.CTRL.sub(" ", str(body.get("error") or ""))[:200])
        _notify(s)
    return {}
