"""Hänge-Wächter des Panels (Dominik 2026-10-18 "1a"): the panel answers every request on one event loop, so one
piece of heavy work on it (2026-10-18: Ordner auslassen with thousands of documents) holds every chat, app and
speaker until it ends. systemd only restarts a panel that crashed, not one that hangs.

    beat()      a task on the loop: notes the time every BEAT seconds
    start()     from panel.serve(): the beat and the watcher thread
    the thread  every second: while the loop beats, it tells systemd "WATCHDOG=1" (speech-spark-panel.service has
                WatchdogSec=RESTART_S); after STALL_S seconds without a beat one line names where the loop stands
                (module and function of the panel's code, from the loop thread's stack) and the thread that used
                the most CPU in the second before (Pi 2026-10-19: the loop stood at harmless file reads while one
                core ran at 100 %, another thread kept Python's lock), after WARN_S a second
                one; when the loop beats again, a line with the seconds. Without a beat for RESTART_S seconds
                systemd stops the panel and starts it again (Restart=always). Before the first beat (start-up) it
                pings for at most START_MAX_S seconds.
    view()      the stalls of the last DAY_S seconds in numbers: Zustand → Überblick, Live, the hint on the admin
                pages (health.alerts) for HINT_S seconds after a stall

Fixed rule without a switch (a protection, like the watchdog of the speech services). Logs → Diagnose, area System:
"loopwacht: stalled | <module.function> | <s> s | busy <module.function or thread name> <%> %", "loopwacht: free again | ... | <s> s": only names from the code
and numbers, never a request's content.
"""
import asyncio
import os
import re
import socket
import sys
import threading
import time
from collections import deque

BEAT = 1.0          # s between two beats of the loop
STALL_S = 5         # s without a beat: one log line with the place
WARN_S = 60         # s: the line that the restart follows
RESTART_S = 90      # s: WatchdogSec= of speech-spark-panel.service (install.sh takes it from here)
START_MAX_S = 600   # s the thread pings systemd before the loop's first beat (start-up of the panel)
DAY_S = 86400       # the stalls counted in view()
HINT_S = 3600       # s the hint on the admin pages stays after a stall
KEEP = 50           # stalls kept in memory
# s a thread computing in Python keeps the interpreter's lock before the loop gets it back (Python's default 0.005).
# Every file access of the loop gives the lock up and waits that long again; with two threads computing
# (Pi 2026-10-19: calendars._expand 127 %) a handful of reads made the loop stand 6-8 s. Shorter: the loop comes
# back sooner, the computing threads lose a little.
SWITCH_S = 0.001

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # app/
_NAME = re.compile(r"[^A-Za-z0-9_.<>]")
_lock = threading.Lock()
_st = {"last": None, "tid": None, "ntid": None, "since": None, "where": "", "warned": False, "started": None, "cpu": {}}
_TICK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
_stalls = deque(maxlen=KEEP)   # (end time, seconds, where)


def _notify(msg):
    """sd_notify without a library: one datagram to $NOTIFY_SOCKET (nothing when systemd did not give one)."""
    addr = os.environ.get("NOTIFY_SOCKET", "")
    if not addr:
        return False
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(msg.encode())
        return True
    except OSError:
        return False


async def beat():
    with _lock:
        _st["tid"], _st["ntid"] = threading.get_ident(), threading.get_native_id()
    while True:
        with _lock:
            _st["last"] = time.monotonic()
        await asyncio.sleep(BEAT)


def where(tid, frames=None):
    """Where the loop thread stands: "module.function" of the outermost and the innermost frame of the panel's own
    code that runs right now ("auslassen.add > nasquelle._put_state"; the frames between the library's (asyncio,
    starlette) and the innermost own one), or "" (only names from the code, nothing of a request)."""
    f = (sys._current_frames() if frames is None else frames).get(tid)
    own = []
    while f is not None:
        path = os.path.abspath(f.f_code.co_filename)
        mine = path.startswith(_HERE + os.sep) and os.path.basename(path) != "loopwacht.py"
        if mine:
            own.append(os.path.basename(path)[:-3] + "." + f.f_code.co_name)
        elif own:
            break
        f = f.f_back
    if not own:
        return ""
    names = [own[0]] if own[0] == own[-1] else [own[-1], own[0]]
    return " > ".join(_NAME.sub("", n)[:60] for n in names)


def cpu_times():
    """{native thread id: CPU ticks so far} of this process's threads (Linux /proc; {} elsewhere)."""
    out = {}
    try:
        tasks = os.listdir("/proc/self/task")
    except OSError:
        return out
    for t in tasks:
        try:
            with open(f"/proc/self/task/{t}/stat", encoding="ascii", errors="replace") as f:
                rest = f.read().rsplit(")", 1)[1].split()
            out[int(t)] = int(rest[11]) + int(rest[12])    # utime, stime
        except (OSError, IndexError, ValueError):
            pass
    return out


def busy(before, after, frames=None, skip=None):
    """The thread (other than the loop) that used the most CPU between two cpu_times(): "<place or name> <%> %",
    or "" (only names from the code and the thread names the panel gives)."""
    use = {t: after[t] - before.get(t, after[t]) for t in after if t != skip}
    if not use or max(use.values()) <= 0:
        return ""
    t = max(use, key=use.get)
    th = next((x for x in threading.enumerate() if x.native_id == t), None)
    place = (where(th.ident, frames) if th else "") or (_NAME.sub("", th.name)[:40] if th else "") or "thread"
    return f"{place} {round(use[t] * 100 / _TICK)} %"


def tick(now=None, frames=None, cpu=None):
    """One look (every second from the thread; the tests call it with their own times)."""
    now = time.monotonic() if now is None else now
    cpu = cpu_times() if cpu is None else cpu
    with _lock:
        before, _st["cpu"] = _st["cpu"], cpu
        last, tid = _st["last"], _st["tid"]
        if _st["started"] is None:
            _st["started"] = now
    if last is None:
        if now - _st["started"] <= START_MAX_S:
            _notify("WATCHDOG=1")
        return "start"
    gap = now - last
    if gap < STALL_S:
        _notify("WATCHDOG=1")
        with _lock:
            since, place = _st["since"], _st["where"]
            _st.update(since=None, where="", warned=False)
        if since is not None:
            secs = max(STALL_S, round(last - since))
            with _lock:
                _stalls.append((time.time(), secs, place))
            print(f"loopwacht: free again | {place or 'unknown'} | {secs} s", flush=True)
            try:
                import live
                live.mark("Spark", f"Panel hing {secs} s")
            except Exception:   # noqa: BLE001  (Live is only a view; the log line above stays)
                pass
        return "ok"
    with _lock:
        first = _st["since"] is None
        if first:
            _st.update(since=last, where=where(tid, frames))
        place, warned = _st["where"], _st["warned"]
        if gap >= WARN_S and not warned:
            _st["warned"] = True
    if first:
        who = busy(before, cpu, frames, _st["ntid"])
        print(f"loopwacht: stalled | {place or 'unknown'} | {int(gap)} s" + (f" | busy {who}" if who else ""), flush=True)
    elif gap >= WARN_S and not warned:
        print(f"loopwacht: stalled | {place or 'unknown'} | {int(gap)} s | restart after {RESTART_S} s", flush=True)
    return "stalled"


def _watch():
    while True:
        time.sleep(1)
        try:
            tick()
        except Exception as e:   # noqa: BLE001  (the watcher never ends; systemd's own watchdog stays)
            print("loopwacht: error", type(e).__name__, flush=True)


def start():
    """From panel.serve(): the beat on the running loop and the watcher thread."""
    from core import spawn
    sys.setswitchinterval(SWITCH_S)
    spawn(beat(), name="loopwacht")
    threading.Thread(target=_watch, name="loopwacht", daemon=True).start()
    print(f"loopwacht: on | stall {STALL_S} s | restart {RESTART_S} s | switch {SWITCH_S * 1000:g} ms", flush=True)


def view(now=None, mono=None):
    """The stalls in numbers: the count and the longest of the last DAY_S seconds, how long ago the last one ended
    and how long it was, the seconds of a stall now."""
    now = time.time() if now is None else now
    mono = time.monotonic() if mono is None else mono
    with _lock:
        day = [(t, s) for t, s, _ in _stalls if now - t < DAY_S]
        since, last = _st["since"], _st["last"]
    return {"n": len(day), "max_s": max((s for _, s in day), default=0),
            "vor_s": round(now - day[-1][0]) if day else None, "letzt_s": day[-1][1] if day else 0,
            "jetzt_s": round(mono - last) if since is not None and last is not None else 0}


def alerts(now=None):
    """The hint on the admin pages: for HINT_S seconds after a stall (fixed sentence with numbers)."""
    v = view(now)
    if not v["n"] or v["vor_s"] is None or v["vor_s"] > HINT_S:
        return []
    return [{"kind": "loopwacht", "level": "warn", "go": "Zustand → Logs → Diagnose",
             "text": f"Das Panel stand vor {max(1, round(v['vor_s'] / 60))} min {v['letzt_s']} s lang still "
                     f"(heute {v['n']}-mal). Wo es hing, steht unter Zustand → Logs → Diagnose, Bereich System."}]
