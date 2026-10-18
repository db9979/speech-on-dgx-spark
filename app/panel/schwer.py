"""Schwere Aufträge: one queue and one place on the model computer for the models that load on demand (plan
plaene/schwere-auftraege.md, Dominik 2026-10-18 „soll immer nur ein Model geladen sein, beide nicht gleichzeitig“,
„ja wie Empfehlung“ = 1a 2a 3a 4a 5a 6a). Fixed rule like Vorrang für Sprache, no switch.

Bilder malen and Bilder ändern (bilder.py) and Musik machen (musik.py), and their admin measurements, keep their own
jobs, limits and texts; for the model they ask here:

    await schwer.run("bild", jid, t0, once)     # waits its turn, frees the place, runs once(), retries on memory

The rules, all fixed (the model decides nothing):
- one place: only one of these models is loaded at a time; before a model of another kind starts, the panel ends the
  one loaded (STOPS, the service's /v1/<art>/stop), and the services refuse a second one themselves (bedarf.py, 503
  "belegt"), so the rule holds even for a call that passes the panel by;
- order (pick): by arrival, but while the loaded kind still waits it goes first, at most BUNDLE in a row while the
  other kind waits; that saves loading without leaving anybody behind;
- unloading: a model ends at once when the other kind is next, else after its idle minutes as before (the service);
- memory: "memory" (too little free) or "belegt" (the other model still there) is not the end: the job keeps its
  turn and tries again every RETRY_S seconds, for at most MEM_WAIT_S, then it gives up with that reason;
- at most WAITING open jobs of all kinds on the whole Spark (the jobs of SOURCES, the modules' own lists).

Who waits behind others hears it with a fixed sentence from the panel (hint), with the place and the time it may
take, estimated from the measured seconds (avg, load); the job's card shows the same (where). Journal lines start
with "schwer:", fixed words and numbers only (no wish, no prompt, no name). Live: busy() and for_live()."""
import asyncio
import secrets
import time

from common import DayCounter

ARTEN = {"bild": ("Bild malen", "image"), "musik": ("Musik machen", "music")}   # art -> (Live name, config part)
BUNDLE = 3              # the loaded kind at most this often in a row while the other kind waits
WAITING = 10            # open heavy jobs on the whole Spark
MEM_WAIT_S = 10 * 60    # Dominik 5a: a job waits this long for memory (or the other model) before it gives up
RETRY_S = 30
WAIT_S = 30 * 60        # the longest a job may stand in the queue (the modules add it to their job time)
SOON = ("memory", "belegt")   # reasons that are waited out
# seconds before the first measurement of this panel: one job, and loading the model (bild_server/musik_server)
RUN_S = {"bild": 15, "musik": 60}
LOAD_S = {"bild": 10, "musik": 20}

SOURCES = {}            # art -> function: the open jobs [{"id", "t0", "state"}] (bilder.py, musik.py register)
STOPS = {}              # art -> async function ending that model now (bilder.py, musik.py register)
_ready = {}             # jid -> {"art", "t0", "phase"}: jobs inside run(); phase wait | run | speicher
_state = {"run": None, "loaded": None, "streak": 0, "t1": 0.0}
_avg = dict(RUN_S)
_load = dict(LOAD_S)
_cond = []              # [(loop, asyncio.Condition)] of the running loop
count = DayCounter(done=0, wechsel=0, gewartet=0, abgesagt=0)


def _condition():
    loop = asyncio.get_running_loop()
    if not _cond or _cond[0][0] is not loop:
        _cond[:] = [(loop, asyncio.Condition())]
    return _cond[0][1]


def pick(waiting, loaded, streak):
    """The job to run next: waiting = [{"id", "art", "t0"}] in arrival order. The loaded kind goes first while it
    waits, at most BUNDLE in a row while the other kind waits too; else the oldest."""
    if not waiting:
        return None
    same = [e for e in waiting if e["art"] == loaded]
    other = [e for e in waiting if e["art"] != loaded]
    if same and (not other or streak < BUNDLE):
        return same[0]
    return other[0] if other else same[0]


def _open():
    """Every open heavy job (of the modules' lists and inside run()), oldest first: [{"id", "art", "t0", "state"}]."""
    seen = {}
    for art, src in SOURCES.items():
        try:
            for j in src():
                if j.get("state") in ("wait", "run") and j.get("id"):
                    seen[j["id"]] = {"id": j["id"], "art": art, "t0": float(j.get("t0") or 0), "state": j["state"]}
        except Exception:   # noqa: BLE001 - a module's list never stops the queue
            pass
    for jid, e in _ready.items():
        seen.setdefault(jid, {"id": jid, "art": e["art"], "t0": e["t0"], "state": "wait"})
    return sorted(seen.values(), key=lambda e: e["t0"])


def offen():
    """The number of open heavy jobs (the limit WAITING)."""
    return len(_open())


def full():
    return offen() >= WAITING


def where(jid, now=None):
    """The job's place: {"platz", "von", "sek", "phase"} (platz 1 = it runs or is next), or None when it is not open.
    The order is simulated with pick(); the seconds count the job running now, every job before this one and a load
    whenever the kind changes."""
    now = time.time() if now is None else now
    run = _state["run"]
    items = _open()
    if not any(e["id"] == jid for e in items):
        return None
    phase = (_ready.get(jid) or {}).get("phase", "wait")
    loaded, streak = _state["loaded"], _state["streak"]
    secs, order = 0.0, []
    if run and run in _ready:
        art = _ready[run]["art"]
        secs += max(5.0, _avg[art] - (now - _state["t1"]))
        order.append(run)
        loaded = art
    rest = [e for e in items if e["id"] != run]
    while rest:
        e = pick(rest, loaded, streak)
        if e["id"] == jid:
            break
        others = any(x["art"] != loaded for x in rest if x is not e)
        streak = streak + 1 if e["art"] == loaded and others else 0
        secs += (_load[e["art"]] if e["art"] != loaded else 0) + _avg[e["art"]]
        loaded = e["art"]
        order.append(e["id"])
        rest.remove(e)
    if jid == run:
        return {"platz": 1, "von": len(items), "sek": 0, "phase": phase}
    return {"platz": len(order) + 1, "von": len(items), "sek": int(secs), "phase": phase}


def _zeit(sek, en=False):
    m = max(1, round(sek / 60))
    if en:
        return "a minute" if m == 1 else f"{m} minutes"
    return "eine Minute" if m == 1 else f"{m} Minuten"


def hint(jid, en=False, now=None):
    """The fixed sentence for a job that waits behind others (Dominik 3a 4a: only when it really waits), else ""."""
    w = where(jid, now)
    if not w or w["platz"] < 2:
        return ""
    if en:
        return (f"Many requests are running right now, you are in the queue at place {w['platz']}. It takes a moment, "
                f"about {_zeit(w['sek'], True)}.")
    return (f"Gerade laufen viele Anfragen, du bist in der Warteschlange auf Platz {w['platz']}. Es dauert einen "
            f"Moment, etwa {_zeit(w['sek'])}.")


def _free_turn(e):
    if _state["run"] is not None:
        return False
    waiting = sorted(({"id": k, "art": v["art"], "t0": v["t0"]} for k, v in _ready.items() if v["phase"] == "wait"),
                     key=lambda x: x["t0"])
    nxt = pick(waiting, _state["loaded"], _state["streak"])
    return nxt is not None and nxt["id"] == e


async def _stop(art, why):
    """Ends the model of art now (its module's STOPS function: True when it ended one, False when that service is
    not installed)."""
    fn = STOPS.get(art)
    if fn is None:
        return
    try:
        if await fn():
            print(f"schwer: entladen {art} {why}", flush=True)
    except Exception as e:   # noqa: BLE001 - the service refuses a second model anyway ("belegt")
        print(f"schwer: entladen {art} nicht ok {type(e).__name__}", flush=True)


async def run(art, jid, t0, once, learn=True, sleep=asyncio.sleep, clock=time.time):
    """Runs once() (a function returning a fresh coroutine) when it is this job's turn on the one place; see above.
    Raises what once() raises; ValueError("memory"/"belegt") only after MEM_WAIT_S. learn=False: a measurement of
    several songs, its seconds do not count for the estimate."""
    if art not in ARTEN:
        raise ValueError("art")
    jid = jid or secrets.token_hex(6)
    cond = _condition()
    _ready[jid] = {"art": art, "t0": float(t0 or clock()), "phase": "wait"}
    t_in = clock()
    try:
        async with cond:
            if not _free_turn(jid):
                print(f"schwer: wartet {art} platz {(where(jid) or {}).get('platz', 0)}", flush=True)
                count.bump("gewartet")
            await cond.wait_for(lambda: _free_turn(jid))
            waiting_other = any(v["art"] != art and v["phase"] == "wait" for k, v in _ready.items() if k != jid)
            before = _state["loaded"]
            _state["streak"] = _state["streak"] + 1 if before == art and waiting_other else 0
            _state.update(run=jid, t1=clock())
            _ready[jid]["phase"] = "run"
        if before is not None and before != art:
            count.bump("wechsel")
            await _stop(before, "wechsel")
        waited = int(clock() - t_in)
        if waited:
            print(f"schwer: dran {art} nach {waited} s", flush=True)
        t_mem, freed = None, False
        while True:
            t1 = clock()
            try:
                out = await once()
            except ValueError as e:
                why = str(e)
                if why not in SOON:
                    raise
                if why == "belegt" and not freed:   # the other model is still there (the panel restarted and
                    freed = True                    # forgot it): end it and try again at once
                    for other in ARTEN:
                        if other != art:
                            await _stop(other, "belegt")
                    continue
                t_mem = clock() if t_mem is None else t_mem
                if clock() - t_mem >= MEM_WAIT_S:
                    count.bump("abgesagt")
                    print(f"schwer: abgesagt {art} {why} nach {int(clock() - t_mem)} s", flush=True)
                    raise
                _ready[jid]["phase"] = "speicher"
                print(f"schwer: wartet {art} {why} naechster versuch in {RETRY_S} s", flush=True)
                await sleep(RETRY_S)
                _ready[jid]["phase"] = "run"
                continue
            took = clock() - t1     # with the same kind before: one job; else loading and one job
            if not learn:
                pass
            elif took > 0 and before == art:
                _avg[art] = round(_avg[art] * 0.7 + took * 0.3, 1)
            elif took > 0:
                _load[art] = round(_load[art] * 0.7 + max(0.0, took - _avg[art]) * 0.3, 1)
            count.bump("done")
            _state["loaded"] = art
            return out
    finally:
        async with cond:
            _ready.pop(jid, None)
            if _state["run"] == jid:
                _state["run"] = None
            cond.notify_all()


def busy(now=None):
    """Live „Im Hintergrund“: [{"job", "st", "secs"}] for every heavy job, oldest first; st run | wait (a pause in
    the conversation) | platz (waits for the place) | speicher (waits for memory). No wish, no prompt."""
    now = time.time() if now is None else now
    return [{"job": ARTEN[e["art"]][0], "st": _st(e), "secs": int(now - e["t0"])} for e in _open()]


def _st(e):
    """run | wait (before the queue: a pause in the conversation) | platz | speicher."""
    r = _ready.get(e["id"])
    if r is None:
        return "run" if e["state"] == "run" else "wait"
    return "platz" if r["phase"] == "wait" else r["phase"]


def for_live():
    """Numbers only: the kind on the place and its state, waiting jobs per kind, today's counts."""
    count.today()
    run = _state["run"]
    r = _ready.get(run) if run else None
    items = _open()
    return {"platz": r["art"] if r else "", "phase": r["phase"] if r else "",
            "wait": {a: sum(1 for e in items if e["art"] == a and _st(e) != "run") for a in ARTEN},
            "loaded": _state["loaded"] or "", **{k: count[k] for k in ("done", "wechsel", "gewartet", "abgesagt")}}

