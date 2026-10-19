"""Zustand → Überblick → Rechner, „Wer rechnet gerade“ (Dominik 2026-10-18 „1a 2a 3a 4b“): which part inside the panel
takes the CPU, next to the services of both computers (rechner.dienste_cpu).

    messen()      every 3 s from rechnerblick.probe (only with the models on another computer): the CPU share in % of
                  the whole computer of each part since the last call, from the kernel's counters of the panel's
                  threads (/proc/self/task) and of its own worker processes (the meaning search and the re-ranking
                  model run in their own process, docembed.py, nachsortieren.py)

A thread counts for the part its name says: the event loop and the helper threads of asyncio.to_thread for "Anfragen"
(answers, pages, devices), a thread of vorrang.in_thread ("bg-<job>") for its job, the fixed threads by their name.
Numbers and fixed words from the code only, never a process name, a path or what a part works on.
"""
import os
import threading
import time

ANFRAGEN = "anfragen"
# fixed thread names of the panel -> part
THREADS = {"auslassen": "auslassen", "loopwacht": "loopwacht", "chats-drop": "aufraeumen"}
# thread names of asyncio.to_thread, ThreadPoolExecutor and AnyIO: work for a request or a page
HELFER = ("asyncio_", "ThreadPoolExecutor", "AnyIO worker")
# the panel's own worker processes: module -> part
PROZESSE = {"docembed": "bedeutungssuche", "nachsortieren": "nachsortieren"}
TEILE_MAX = 12
_alt = {}             # the last measurement: {"t": monotonic, "ticks": {(kind, id): (part, ticks)}}


def _ticks(path):
    """utime + stime of one /proc/…/stat (the fields after the name in brackets), None when gone."""
    try:
        with open(path) as f:
            s = f.read()
        x = s[s.rindex(")") + 2:].split()
        return int(x[11]) + int(x[12])
    except (OSError, ValueError, IndexError):
        return None


def teil_von(name, haupt=False):
    """The part a thread of the panel counts for (fixed words; a vorrang job keeps its fixed name from the code)."""
    if haupt or not name or name.startswith(HELFER):
        return ANFRAGEN
    if name.startswith("bg-"):
        return "bg:" + name[3:43]
    return THREADS.get(name, "weitere")


def _prozesse():
    """pid -> part of the panel's own worker processes that run now."""
    import sys
    out = {}
    for mod, teil in PROZESSE.items():
        m = sys.modules.get(mod)
        p = getattr(m, "_proc", None) if m else None
        if p is not None and getattr(p, "returncode", 0) is None and isinstance(getattr(p, "pid", None), int):
            out[p.pid] = teil
    return out


def _lesen():
    namen = {t.native_id: t.name for t in threading.enumerate() if t.native_id is not None}
    haupt = threading.main_thread().native_id
    out = {}
    try:
        tids = os.listdir("/proc/self/task")
    except OSError:
        tids = []
    for tid in tids:
        if tid.isdigit():
            n = _ticks(f"/proc/self/task/{tid}/stat")
            if n is not None:
                out[("t", int(tid))] = (teil_von(namen.get(int(tid), ""), int(tid) == haupt), n)
    for pid, teil in _prozesse().items():
        n = _ticks(f"/proc/{pid}/stat")
        if n is not None:
            out[("p", pid)] = (teil, n)
    return out


def messen(now=None, lesen=_lesen, kerne=None, hz=None):
    """{part: % of the whole computer} since the last call ({} on the first), the biggest first, at most TEILE_MAX."""
    now = time.monotonic() if now is None else now
    kerne = kerne or os.cpu_count() or 1
    hz = hz or os.sysconf("SC_CLK_TCK")
    jetzt = lesen()
    alt = dict(_alt)
    _alt.update(t=now, ticks=jetzt)
    dt = now - alt["t"] if alt else 0
    if dt <= 0:
        return {}
    sum_ = {}
    for key, (teil, n) in jetzt.items():
        vorher = alt["ticks"].get(key)
        if vorher is not None and n > vorher[1]:      # a thread or process that is new counts from the next round
            sum_[teil] = sum_.get(teil, 0) + n - vorher[1]
    out = {t: round(min(100.0, 100 * v / hz / (dt * kerne)), 1) for t, v in sum_.items()}
    return dict(sorted(((t, v) for t, v in out.items() if v >= 0.1), key=lambda x: -x[1])[:TEILE_MAX])
