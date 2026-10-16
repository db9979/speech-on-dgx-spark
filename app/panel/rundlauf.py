"""Rundlauf-Wächter (plan plaene/verbesserungen-2026-10-16.md, 3a; Dominik 2026-10-16 "alles umsetzten"): a real
round trip through the models every few minutes, part of the Dienst-Wächter.

The Dienst-Wächter only asks /health. A service can answer "healthy" and still deliver nothing (no memory for its
cache, a stuck engine), and with Spark teilen the way panel computer → TLS-Tor → model computer is part of it. So every
PACE minutes (chat.rundlauf_min: 2, 5 or 15) the panel tries the real thing, with the request stage "hinten" so
people always go first:
    1. Sprechen: Sprechen says the fixed sentence (health.LIVE_SENTENCE) as WAV,
    2. Hören: Hören writes it down again; at least SHARE of its words must come back (fixed words, no model),
    3. Sprachmodell: the language model answers a fixed question in at most LLM_TOKENS tokens.
Each step in ms, and the whole way. Nothing of a profile goes in, nothing is kept but numbers and fixed words
(STATE/rundlauf.json: time, ms per step, the step that failed and a fixed word why).

Left out (a fixed word, counted, no note) while someone talks with the Spark (update.talking), during a
Wartungspause of one of the three, an update, the Notaus, the first START_S after the panel started, while pictures
or music are made, and in the night window of "Heute Nacht einspielen" (so the update finds its pause).

FAIL_N failed runs in a row are a "Störung": the Dienst-Wächter tells the admins once with the step that hakt
("Rundlauf: Hören antwortet nicht") and once when it runs again (dienstwacht.warn: its night, device and queue
rules); the banner on every admin page names the step (alerts). A step clearly slower than usual (more than SLOW_X
times its median of the last DAY, at least SLOW_MS more, with MIN_N runs to compare) is a quiet line (level info).

Shown in the same commit: Zustand → Monitoring (tile "Rundlauf" with the steps and the curve of the last
CURVE runs), Zustand → Live (the step's time on Sprechen, Hören and Sprachmodell, a hint at the box that hakt),
the Steuerzentrale and the iPhone app's "Spark verwalten" (both from health.alerts and live.snapshot).
Admin switch chat.rundlauf (off) below the Dienst-Wächter. Logs: "rundlauf: ok tts 420 asr 310 llm 280 ms",
"rundlauf: fehler asr zeit", "rundlauf: ausgelassen gespraech", "rundlauf: stoerung asr", "rundlauf: wieder ok".
"""
import asyncio
import os
import threading
import time

import httpx

import features
from common import STATE, load_config, read_json, write_json

FILE = os.path.join(STATE, "rundlauf.json")
PACES = (2, 5, 15)            # minutes between two runs (chat.rundlauf_min), 5 by default
LOOP_S = 30                   # the loop looks this often whether a run is due
START_S = 180                 # after the panel started: the models may still be loading
TIMEOUT_S = 60                # per step; a step that takes longer counts as "zeit"
LLM_TOKENS = 3
LLM_QUESTION = "Antworte nur mit dem Wort OK."
SHARE = 0.6                   # share of the sentence's words Hören must bring back
FAIL_N = 2                    # failed runs in a row before the admins hear of it
DAY = 86400
KEEP = 800                    # runs kept (a day at 2 minutes is 720)
CURVE = 24                    # runs in the curve on Zustand → Monitoring
MIN_N, SLOW_X, SLOW_MS = 12, 2.0, 300
STEPS = ("tts", "asr", "llm")
NAME = {"tts": ("Sprechen", "Speaking"), "asr": ("Hören", "Listening"), "llm": ("Sprachmodell", "Language model")}
WHY = {"zeit": "antwortet nicht rechtzeitig", "fehler": "antwortet nicht", "stumm": "liefert keinen Ton",
       "falsch": "versteht den Satz nicht", "leer": "antwortet leer"}
LIVE_NODE = {"tts": "tts", "asr": "asr", "llm": "llm"}
AUS = {"start": "Panel startet", "notaus": "Notaus", "update": "Update", "gespraech": "Gespräch läuft", "nacht": "Update-Nacht",
       "wartung": "Wartungspause", "bild": "Bild entsteht", "musik": "Lied entsteht"}
URL = None                    # tests point the models elsewhere (None: common.model_url)

_lock = threading.Lock()
_st = {"letzt": 0.0, "laeuft": False, "lauf": 0.0, "aus": "", "aus_n": 0}
STARTED = time.time()


def an(c=None):
    """Funktionen → Dienst-Wächter → Rundlauf prüfen (admin, off; needs the Dienst-Wächter)."""
    return features.admin_on("rundlauf", c)


def pace_min(c=None):
    c = features.chat_cfg() if c is None else c
    v = c.get("rundlauf_min", 5)
    return v if v in PACES else 5


def check(c):
    """None when the setting in chat is fine, else the reason (admin.validate)."""
    v = c.get("rundlauf_min", 5)
    if isinstance(v, bool) or v not in PACES:
        return "rundlauf_min: 2, 5 oder 15"
    return None


# ---------------------------------------------------------------- what is kept
def _read():
    d = read_json(FILE, {})
    runs = d.get("runs") if isinstance(d, dict) else None
    out = []
    for r in runs if isinstance(runs, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("t"), (int, float)):
            continue
        ms = {k: int(v) for k, v in (r.get("ms") or {}).items() if k in STEPS + ("ganz",) and isinstance(v, (int, float))
              and not isinstance(v, bool) and 0 <= v < 10 ** 7}
        step = r.get("step") if r.get("step") in STEPS else ""
        out.append({"t": int(r["t"]), "ok": not step, "step": step, "why": r.get("why") if r.get("why") in WHY else "",
                    "ms": ms})
    stoer = d.get("stoerung") if isinstance(d, dict) and isinstance(d.get("stoerung"), dict) else None
    if stoer and (stoer.get("step") not in STEPS or not isinstance(stoer.get("seit"), (int, float))):
        stoer = None
    return {"runs": out[-KEEP:], "stoerung": stoer}


def _write(d):
    write_json(FILE, {"runs": d["runs"][-KEEP:], "stoerung": d["stoerung"]}, mode=0o600)


def reset():
    with _lock:
        _write({"runs": [], "stoerung": None})
        _st.update(letzt=0.0, laeuft=False, lauf=0.0, aus="", aus_n=0)


# ---------------------------------------------------------------- one run
def skip_reason(now=None, c=None):
    """A fixed word why a run is left out now, else ""."""
    now = time.time() if now is None else now
    if now - STARTED < START_S:
        return "start"
    try:
        import notaus
        if notaus.level() > 0:
            return "notaus"
    except Exception:
        pass
    try:
        import update
        if update.update_running():
            return "update"
        if update.talking(now)["now"]:
            return "gespraech"
        if update.night_on():
            from datetime import datetime
            if update.NIGHT[0] <= datetime.fromtimestamp(now).hour < update.NIGHT[1]:
                return "nacht"
    except Exception:
        pass
    try:
        import wartung
        if any(wartung.quiet(p) for p in ("llm", "asr", "tts")):
            return "wartung"
    except Exception:
        pass
    try:
        import bilder
        if bilder.stats()["run"]:
            return "bild"
    except Exception:
        pass
    try:
        import musik
        if musik.stats()["run"]:
            return "musik"
    except Exception:
        pass
    return ""


def _headers():
    import stufe
    from core import api_headers
    return {**api_headers(), **stufe.headers("hinten")}   # people always go first


async def run_once(now=None):
    """One round trip. Returns {"t", "ok", "step", "why", "ms"}: step and why are fixed words, ms numbers only."""
    import health
    import llm
    import verbrauch
    cfg = load_config()
    t_start = time.time()
    ms, step, why = {}, "", ""
    hdr = _headers()
    url = URL
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=5)) as c:
        t0 = time.time()
        try:
            code, audio, _secs = await health.tts_wav(c, cfg, health.LIVE_SENTENCE, hdr, url)
            if code != 200:
                step, why = "tts", "fehler"
            elif audio is None:
                step, why = "tts", "stumm"
        except httpx.TimeoutException:
            step, why = "tts", "zeit"
        except (httpx.HTTPError, OSError, ValueError, KeyError):
            step, why = "tts", "fehler"
        ms["tts"] = int((time.time() - t0) * 1000)
        if not step:
            t0 = time.time()
            try:
                code, text = await health.asr_text(c, cfg, audio, hdr, url)
                if code != 200:
                    step, why = "asr", "fehler"
                elif health.heard_share(text) < SHARE:
                    step, why = "asr", "falsch"
            except httpx.TimeoutException:
                step, why = "asr", "zeit"
            except (httpx.HTTPError, OSError, ValueError, KeyError):
                step, why = "asr", "fehler"
            ms["asr"] = int((time.time() - t0) * 1000)
        if not step:
            t0 = time.time()
            ccfg = cfg.get("chat", {})
            try:
                headers = llm.headers(ccfg)
                model = await llm.model(c, ccfg, headers)
                r = await c.post(llm.url(ccfg), headers=headers, json={
                    "model": model, "max_tokens": LLM_TOKENS, "stream": False, "temperature": 0,
                    "chat_template_kwargs": {"enable_thinking": False},
                    "messages": [{"role": "user", "content": LLM_QUESTION}]})
                verbrauch.response("Dienst prüfen", r)
                if r.status_code != 200:
                    step, why = "llm", "fehler"
                elif not str(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip():
                    step, why = "llm", "leer"
            except httpx.TimeoutException:
                step, why = "llm", "zeit"
            except (httpx.HTTPError, OSError, ValueError, KeyError, IndexError, AttributeError, RuntimeError):
                step, why = "llm", "fehler"
            ms["llm"] = int((time.time() - t0) * 1000)
    ms["ganz"] = int((time.time() - t_start) * 1000)
    return {"t": int(time.time() if now is None else now), "ok": not step, "step": step, "why": why, "ms": ms}


def record(res, now=None):
    """Keeps the run, moves the Störung and tells the Dienst-Wächter. Returns "stoerung", "wieder" or ""."""
    import dienstwacht
    now = time.time() if now is None else now
    with _lock:
        d = _read()
        d["runs"].append(res)
        changed = ""
        if res["ok"]:
            if d["stoerung"]:
                d["stoerung"], changed = None, "wieder"
        elif not d["stoerung"]:
            last = d["runs"][-FAIL_N:]
            if len(last) == FAIL_N and all(not r["ok"] for r in last):
                d["stoerung"], changed = {"step": res["step"], "why": res["why"], "seit": int(last[0]["t"])}, "stoerung"
        _write(d)
    if res["ok"]:
        m = res["ms"]
        print(f"rundlauf: ok tts {m.get('tts', 0)} asr {m.get('asr', 0)} llm {m.get('llm', 0)} ms", flush=True)
    else:
        print(f"rundlauf: fehler {res['step']} {res['why']}", flush=True)
    if changed == "stoerung":
        print(f"rundlauf: stoerung {res['step']}", flush=True)
        dienstwacht.warn("rundlauf", f"{NAME[res['step']][0]} {WHY[res['why']]}", True, now)
    elif changed == "wieder":
        print("rundlauf: wieder ok", flush=True)
        dienstwacht.warn("rundlauf", "läuft wieder durch", False, now)
    return changed


async def tick(now=None):
    """What the loop does every LOOP_S: a run when one is due and nothing speaks against it."""
    now = time.time() if now is None else now
    c = features.chat_cfg()
    if not an(c) or now - _st["letzt"] < pace_min(c) * 60 or _st["laeuft"]:
        return None
    why = skip_reason(now, c)
    if why:
        if _st["aus"] != why:
            print(f"rundlauf: ausgelassen {why}", flush=True)
        _st.update(aus=why, aus_n=_st["aus_n"] + 1)
        return None
    _st.update(laeuft=True, letzt=now, aus="")
    try:
        res = await run_once(now)
    finally:
        _st["laeuft"] = False
    _st["lauf"] = time.time()
    record(res, now)
    return res


async def loop():
    while True:
        await asyncio.sleep(LOOP_S)
        try:
            await tick()
        except Exception as e:
            print("rundlauf: loop", type(e).__name__, flush=True)


# ---------------------------------------------------------------- what the pages show
def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def langsam(d=None, now=None):
    """[(step, ms now, usual ms)] for the steps of the newest good run clearly slower than their median of the day."""
    now = time.time() if now is None else now
    d = _read() if d is None else d
    good = [r for r in d["runs"] if r["ok"] and now - r["t"] < DAY]
    if len(good) <= MIN_N:
        return []
    last, before = good[-1], good[:-1]
    out = []
    for s in STEPS:
        usual = _median([r["ms"][s] for r in before if s in r["ms"]])
        cur = last["ms"].get(s)
        if usual and cur is not None and cur > SLOW_X * usual and cur - usual >= SLOW_MS:
            out.append((s, cur, usual))
    return out


def lebt(now=None):
    """For the Dienst-Wächter's dot: the loop ran or chose to leave a run out within three paces."""
    now = time.time() if now is None else now
    if not an():
        return True
    seen = max(_st["letzt"], _st["lauf"])
    return now - STARTED < 3 * pace_min() * 60 + START_S or now - seen < 3 * pace_min() * 60 + 2 * LOOP_S or bool(_st["aus"])


def _s(ms):
    return f"{ms / 1000:.1f}".replace(".", ",") + " s" if ms >= 1000 else f"{ms} ms"


def alerts(now=None):
    """„Braucht dich“: the step that hakt (bad), a step much slower than usual (info)."""
    if not an():
        return []
    from datetime import datetime
    d = _read()
    if d["stoerung"]:
        s = d["stoerung"]
        hm = datetime.fromtimestamp(s["seit"]).strftime("%H:%M")
        return [{"kind": "rundlauf", "level": "bad", "go": "Zustand → Monitoring",
                 "text": f"Rundlauf: {NAME[s['step']][0]} {WHY.get(s.get('why'), 'antwortet nicht')} (seit {hm})."}]
    return [{"kind": "rundlauf", "level": "info", "go": "Zustand → Monitoring",
             "text": f"Rundlauf: {NAME[s][0]} langsamer als sonst ({_s(cur)} statt {_s(usual)})."} for s, cur, usual in langsam(d, now)]


def fuer_status(now=None):
    """/api/status "rundlauf": {"an": False}, or the last run, the Störung and the curve of the whole way (ms)."""
    if not an():
        return {"an": False}
    now = time.time() if now is None else now
    d = _read()
    last = d["runs"][-1] if d["runs"] else None
    day = [r for r in d["runs"] if now - r["t"] < DAY]
    return {"an": True, "min": pace_min(), "letzt": last, "stoerung": d["stoerung"], "aus": _st["aus"],
            "kurve": [r["ms"].get("ganz") if r["ok"] else None for r in d["runs"][-CURVE:]],
            "heute": {"ok": sum(1 for r in day if r["ok"]), "fehler": sum(1 for r in day if not r["ok"]),
                      "aus": _st["aus_n"]},
            "langsam": [s for s, _c, _u in langsam(d, now)]}


def for_live(now=None):
    """Zustand → Live: the box „Rundlauf“ with its line (pace, the last run's times in fixed words and numbers) and a
    hint at the step's box (Sprechen, Hören, Sprachmodell) that hakt or is much slower than usual."""
    if not an():
        return {"on": False}, []
    d = _read()
    last = d["runs"][-1] if d["runs"] else None
    sub = f"alle {pace_min()} min"
    if last and last["ok"]:
        m = last["ms"]
        sub += (f" · ok in {_s(m.get('ganz', 0))} (Sprechen {_s(m.get('tts', 0))} · Hören {_s(m.get('asr', 0))}"
                f" · Modell {_s(m.get('llm', 0))})")
    elif last:
        sub += f" · {NAME[last['step']][0]} {WHY.get(last['why'], 'antwortet nicht')}"
    else:
        sub += " · noch kein Lauf"
    if _st["aus"]:
        sub += " · wartet: " + AUS.get(_st["aus"], _st["aus"])
    hints = []
    if d["stoerung"]:
        s = d["stoerung"]
        hints.append({"at": LIVE_NODE[s["step"]], "level": "bad", "word": f"Rundlauf: {WHY.get(s.get('why'), 'antwortet nicht')}"})
    for s, _cur, _usual in langsam(d, now):
        hints.append({"at": LIVE_NODE[s], "level": "warn", "word": "Rundlauf: langsamer als sonst"})
    return {"on": True, "sub": sub, "bad": bool(d["stoerung"])}, hints
