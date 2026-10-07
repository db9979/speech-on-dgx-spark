"""Stability: a watchdog for hung speech services, a warning before memory runs out, and a live
check of the real services (LLM answers, TTS speaks, ASR understands what TTS said).

Watchdog (config watch.watchdog, on by default): every WATCH_EVERY seconds it looks at the ASR
and TTS front ends and their engines. It restarts a unit that
  - does not answer at all for HUNG_AFTER seconds although systemd says it runs,
  - is busy without finishing a single request for HUNG_AFTER seconds (engine stuck),
  - has been "loading" for longer than LOAD_LIMIT (stuck while starting).
At most MAX_RESTARTS per unit and hour; after that it only reports. Nothing happens while an
update runs or when the unit was started less than GRACE seconds ago.

Memory: below watch.warn_gib (default 10 GiB; DGX OS starts killing processes at about 8 GiB) the
panel shows a warning on every admin page and writes it to the change log once per episode.

Live check: after an update (and on request) the real services are tried once; the result is in
STATE/livecheck.json and on the page System und Update.
"""
import asyncio
import io
import json
import os
import re
import sys
import time
import wave

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guard  # noqa: E402
from common import load_config  # noqa: E402
from core import UNITS, api_headers, app_version, run  # noqa: E402
from monitor import service_health, system_stats  # noqa: E402

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
WATCH_EVERY, HUNG_AFTER, LOAD_LIMIT, GRACE = 30, 300, 45 * 60, 180
MAX_RESTARTS = 3
_seen = {}       # unit -> {"bad_since", "busy_since", "requests", "loading_since"}
_restarts = {}   # unit -> [times]
events = []      # recent watchdog actions for the page: {"t", "unit", "reason", "done"}
memory_state = {"low": False, "since": None, "min": None}


# ---------------------------------------------------------------- memory
def check_memory(avail_gib, cfg=None):
    cfg = cfg or load_config()
    warn = float(cfg.get("watch", {}).get("warn_gib", 10))
    low = avail_gib is not None and avail_gib < warn
    if low and not memory_state["low"]:
        memory_state.update(low=True, since=time.time(), min=avail_gib)
        guard.log("memory_low", detail=f"{avail_gib:.1f} GiB free (warning below {warn:g} GiB)")
        print(f"memory low: {avail_gib:.1f} GiB free", flush=True)
    elif low:
        memory_state["min"] = min(memory_state["min"] or avail_gib, avail_gib)
    elif memory_state["low"] and avail_gib >= warn + 1:  # a little hysteresis
        memory_state.update(low=False, since=None, min=None)
    memory_state["warn_gib"] = warn
    memory_state["avail"] = avail_gib
    return memory_state


# ---------------------------------------------------------------- watchdog
def _active_seconds(unit):
    """Seconds since the unit became active, None if it is not active."""
    code, out = run(["systemctl", "show", unit, "-p", "ActiveState,ActiveEnterTimestampMonotonic"])
    props = dict(x.split("=", 1) for x in out.splitlines() if "=" in x)
    if props.get("ActiveState") != "active":
        return None
    try:
        since = int(props.get("ActiveEnterTimestampMonotonic", "0")) / 1e6
        return time.monotonic() - since if since else None
    except ValueError:
        return None


def _may_restart(unit, now):
    times = [t for t in _restarts.get(unit, []) if now - t < 3600]
    _restarts[unit] = times
    return len(times) < MAX_RESTARTS


def _restart(name, unit, reason, now):
    if not _may_restart(unit, now):
        item = {"t": int(now), "unit": name, "reason": reason, "done": False,
                "note": f"schon {MAX_RESTARTS}-mal in der letzten Stunde"}
    else:
        code, out = run(["sudo", "-n", "/usr/bin/systemctl", "restart", unit], timeout=120)
        _restarts.setdefault(unit, []).append(now)
        item = {"t": int(now), "unit": name, "reason": reason, "done": code == 0,
                "note": "" if code == 0 else out[-200:]}
    events.append(item)
    del events[:-20]
    _seen.pop(unit, None)
    guard.log("watchdog", who="watchdog", detail=f"{name}: {reason}" + (", neu gestartet" if item["done"] else
                                                                       f" ({item['note']})"))
    print("watchdog:", name, reason, "restarted" if item["done"] else item["note"], flush=True)
    return item


def judge(unit, health, now, up_for, front=True, work=True):
    """What is wrong with one unit (or None); keeps the timers in _seen. front: a front end that
    does not answer; work: loading forever or busy without finishing a request."""
    s = _seen.setdefault(unit, {})
    if up_for is None or up_for < GRACE:
        _seen.pop(unit, None)
        return None
    if health is None:
        if front:
            s.setdefault("bad_since", now)
            if now - s["bad_since"] >= HUNG_AFTER:
                return f"antwortet seit {int(now - s['bad_since'])} s nicht"
        return None
    s.pop("bad_since", None)
    if not work:
        return None
    if health.get("status") == "loading":
        s.setdefault("loading_since", now)
        if now - s["loading_since"] >= LOAD_LIMIT:
            return f"lädt seit {int((now - s['loading_since']) / 60)} min"
    else:
        s.pop("loading_since", None)
    req = health.get("requests")
    if health.get("busy") and req == s.get("requests"):
        s.setdefault("busy_since", now)
        if now - s["busy_since"] >= HUNG_AFTER:
            return f"arbeitet seit {int(now - s['busy_since'])} s, ohne eine Anfrage fertigzustellen"
    else:
        s.pop("busy_since", None)
    s["requests"] = req
    return None


async def watch_once(update_running=lambda: False):
    cfg = load_config()
    if not cfg.get("watch", {}).get("watchdog", True) or update_running():
        return []
    now = time.time()
    done = []
    for name in ("asr", "tts"):
        if not cfg[name].get("enabled", True):
            continue
        health = await service_health(name, cfg)
        engine = cfg[name].get("backend") in ("vllm", "vllm-omni")
        front_up = await asyncio.to_thread(_active_seconds, UNITS[name])
        # the front end: restarted when it does not answer (or, without an engine, when it hangs)
        reason = judge(UNITS[name], health, now, front_up, work=not engine)
        if reason:
            done.append(await asyncio.to_thread(_restart, name.upper(), UNITS[name], reason, now))
            continue
        if engine and health is not None:
            # a stuck engine shows in the front end's status: loading forever or busy without progress
            unit = UNITS[name + "-engine"]
            reason = judge(unit, health, now, await asyncio.to_thread(_active_seconds, unit), front=False)
            if reason:
                done.append(await asyncio.to_thread(_restart, name.upper() + "-Engine", unit, reason, now))
    return done


# ---------------------------------------------------------------- live check
LIVE_FILE = os.path.join(STATE, "livecheck.json")
LIVE_SENTENCE = "Heute ist ein schöner Tag, und der Spark spricht wieder."
_live_lock = asyncio.Lock()


def last_live():
    try:
        with open(LIVE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _words(text):
    return set(re.findall(r"\w+", (text or "").lower()))


def _wav_seconds(data):
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


async def livecheck(reason="manual"):
    """LLM, TTS and ASR once, with times; returns and stores the result."""
    if _live_lock.locked():
        return last_live()
    async with _live_lock:
        cfg = load_config()
        steps = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=5)) as c:
            # LLM
            t0 = time.time()
            ccfg = cfg.get("chat", {})
            try:
                from chat import llm_model
                headers = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
                model = await llm_model(c, ccfg, headers)
                r = await c.post(ccfg["llm_url"].rstrip("/") + "/chat/completions", headers=headers, json={
                    "model": model, "max_tokens": 200, "stream": False,
                    "messages": [{"role": "user", "content": "Antworte nur mit dem Wort OK."}]})
                ok = r.status_code == 200
                text = (r.json()["choices"][0]["message"].get("content") or "").strip() if ok else r.text[:200]
                steps.append({"name": "llm", "ok": ok, "seconds": round(time.time() - t0, 2),
                              "detail": (model + ": " + text[:80]) if ok else f"HTTP {r.status_code}: {text}"})
            except Exception as e:
                steps.append({"name": "llm", "ok": False, "seconds": round(time.time() - t0, 2),
                              "detail": f"{type(e).__name__}: {e}"[:200]})
            # TTS
            audio = None
            if cfg["tts"].get("enabled", True):
                t0 = time.time()
                try:
                    r = await c.post(f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", headers=api_headers(),
                                     json={"input": LIVE_SENTENCE, "language": "German", "response_format": "wav"})
                    secs = _wav_seconds(r.content) if r.status_code == 200 else None
                    ok = bool(secs and secs > 0.5)
                    audio = r.content if ok else None
                    steps.append({"name": "tts", "ok": ok, "seconds": round(time.time() - t0, 2),
                                  "detail": f"{secs:.1f} s Audio" if ok else f"HTTP {r.status_code}: {r.text[:150]}"})
                except Exception as e:
                    steps.append({"name": "tts", "ok": False, "seconds": round(time.time() - t0, 2),
                                  "detail": f"{type(e).__name__}: {e}"[:200]})
            # ASR: does it understand what TTS said?
            if cfg["asr"].get("enabled", True):
                t0 = time.time()
                if audio is None:
                    steps.append({"name": "asr", "ok": None, "seconds": 0, "detail": "skipped: no audio from TTS"})
                else:
                    try:
                        r = await c.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions",
                                         headers=api_headers(), files={"file": ("check.wav", audio)},
                                         data={"language": "German"})
                        text = r.json().get("text", "") if r.status_code == 200 else ""
                        want = _words(LIVE_SENTENCE)
                        share = len(want & _words(text)) / len(want)
                        steps.append({"name": "asr", "ok": r.status_code == 200 and share >= 0.6,
                                      "seconds": round(time.time() - t0, 2),
                                      "detail": f"„{text[:100]}“ ({round(share * 100)} % der Wörter)" if r.status_code == 200
                                      else f"HTTP {r.status_code}: {r.text[:150]}"})
                    except Exception as e:
                        steps.append({"name": "asr", "ok": False, "seconds": round(time.time() - t0, 2),
                                      "detail": f"{type(e).__name__}: {e}"[:200]})
        res = {"t": int(time.time()), "version": app_version(), "reason": reason,
               "ok": all(s["ok"] is not False for s in steps), "steps": steps}
        try:
            os.makedirs(STATE, exist_ok=True)
            with open(LIVE_FILE + ".tmp", "w") as f:
                json.dump(res, f, ensure_ascii=False)
            os.replace(LIVE_FILE + ".tmp", LIVE_FILE)
        except OSError as e:
            print("livecheck:", e, flush=True)
        if not res["ok"]:
            guard.log("livecheck_failed", who="livecheck",
                      detail="; ".join(f"{s['name']}: {s['detail']}" for s in steps if s["ok"] is False))
        return res


async def ready(cfg, minutes=20):
    """Waits until the enabled services report ready (or the time is up)."""
    end = time.time() + minutes * 60
    while time.time() < end:
        states = [((await service_health(n, cfg)) or {}).get("status") for n in ("asr", "tts") if cfg[n].get("enabled", True)]
        if all(s == "ready" for s in states):
            return True
        await asyncio.sleep(15)
    return False


def after_update_due(progress):
    """True when an update finished recently and this version has not been checked yet."""
    last = last_live() or {}
    return bool(progress and progress.get("done") and progress.get("ok")
                and time.time() - (progress.get("updated") or 0) < 3600 and last.get("version") != app_version())


# ---------------------------------------------------------------- what the page shows on top
def alerts():
    out = []
    if memory_state.get("low"):
        out.append({"kind": "memory", "level": "bad",
                    "text": f"Nur noch {memory_state['avail']:.1f} GiB Speicher frei (Warnung unter "
                            f"{memory_state['warn_gib']:g} GiB). Unter etwa 8 GiB beendet DGX OS Prozesse."})
    recent = [e for e in events if time.time() - e["t"] < 3600]
    for e in recent[-3:]:
        out.append({"kind": "watchdog", "level": "warn" if e["done"] else "bad",
                    "text": f"Wächter: {e['unit']} {e['reason']}"
                            + (", neu gestartet." if e["done"] else f", nicht neu gestartet ({e['note']}).")})
    live = last_live()
    if live and not live.get("ok") and time.time() - live["t"] < 86400:
        bad = ", ".join(s["name"].upper() for s in live["steps"] if s["ok"] is False)
        out.append({"kind": "livecheck", "level": "bad", "text": f"Funktionsprüfung fehlgeschlagen: {bad}."})
    return out


def memory_now():
    return system_stats()["mem_avail_gib"]
