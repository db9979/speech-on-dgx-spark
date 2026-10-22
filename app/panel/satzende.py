"""Satzende am Tonfall: messen (admin chat.turn_tone, off by default; plan "Ins Wort fallen und Satzende am Tonfall" B1).

Today a word list on the page (chat.js turnState) decides at each speaking pause whether the sentence is finished:
"fertig" (it ends on . ? !) ends the turn at once, "offen" ("und", "weil", "ähm", a comma …) waits up to 2 s,
"neutral" ends after END_MS of quiet. Smart Turn v3.2 on the model computer (smartturn.py, idea from sonia-assistant)
also hears the tone and says from 0 to 1 how finished the speaker sounds. Here it only measures and decides nothing:

1. At a pause the page sends its snapshot with "turn" (only profiles with the switch, never guests). start() gives
   it an id and asks the model computer (POST /v1/turn, the last 8 s as 16 kHz WAV) beside the recognition; the
   answer waits for it at most GRACE seconds after the recognition (settle), then it goes on alone.
2. Once the page knows what happened (the word list's verdict, whether the voice went on after the pause), it sends
   "id:regel:0|1" with its next recording; report() writes the line `hoeren: satzende p=0.82 regel=neutral
   weiter=nein ms=31` and keeps only these numbers in STATE/satzende.json. Never sound, never words, no profile.
3. After ROWS pauses or DAYS days, whichever comes first, it stops measuring; the admin sees summary() under
   Funktionen → Gespräch → „Satzende am Tonfall“: hits (sounded finished and was), false alarms (sounded finished,
   went on), and how much waiting it would have saved. Using it (B2) comes only after Dominik's yes to the numbers.
"""
import asyncio
import io
import json
import os
import re
import secrets
import time
import wave

from common import STATE, write_json

ROWS = 200                 # pauses to measure
DAYS = 7                   # or this many days, whichever comes first
HIGH, LOW = 0.8, 0.2       # "sounds finished" / "sounds unfinished" for the summary (B2 would use them)
PAUSE_MS, END_MS = 250, 800   # chat.js: the snapshot after 250 ms of quiet, the turn ends after 800 ms
KEEP = 600                 # seconds a pause waits for the page's report
GRACE = 0.3                # seconds the snapshot's answer waits for Smart Turn after the recognition at most
SECONDS = 8                # what Smart Turn hears (smartturn.SECONDS)
REGELN = ("fertig", "offen", "neutral")
REPORT = re.compile(r"^([A-Za-z0-9_-]{12}):(fertig|offen|neutral):([01])$")
FILE = os.path.join(STATE, "satzende.json")

_pending = {}   # id -> {"uid", "t", "p", "ms"}


def on(uid):
    """The admin released it and this profile may use it (never guests)."""
    import features
    return bool(uid) and features.allowed("satzende", uid)


def _load():
    try:
        with open(FILE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    rows = d.get("rows") if isinstance(d, dict) and isinstance(d.get("rows"), list) else []
    since = d.get("since") if isinstance(d, dict) and isinstance(d.get("since"), (int, float)) else None
    return {"since": since, "rows": [r for r in rows if isinstance(r, list) and len(r) == 4][:ROWS]}


def measuring(now=None):
    d = _load()
    now = time.time() if now is None else now
    return len(d["rows"]) < ROWS and (d["since"] is None or now - d["since"] < DAYS * 86400)


def _wav(pcm):
    """The last SECONDS of 16 kHz float audio as a 16-bit mono WAV."""
    import numpy as np
    x = (np.clip(np.asarray(pcm, dtype=np.float32)[-16000 * SECONDS:], -1, 1) * 32767).astype("<i2")
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(x.tobytes())
    return b.getvalue()


async def _ask(entry, data, cfg):
    """Smart Turn's number for the recording; None when the model computer has no model or does not answer."""
    import httpx
    import speakers
    from common import model_url
    from core import api_headers
    try:
        body = _wav(await asyncio.to_thread(speakers.decode, data))
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(model_url("asr", "/v1/turn", cfg), content=body,
                             headers=dict(api_headers(), **{"Content-Type": "audio/wav"}))
        got = r.json() if r.status_code == 200 else {}
        p, ms = got.get("p"), got.get("ms")
        if isinstance(p, (int, float)) and 0 <= p <= 1:
            entry["p"] = round(float(p), 2)
            entry["ms"] = int(ms) if isinstance(ms, (int, float)) and 0 <= ms < 60000 else None
    except Exception:   # no model, no answer, unreadable audio: no number, the word list counts as before
        pass


def start(uid, data, cfg, now=None):
    """A pause snapshot to measure: its id for the page (or None), Smart Turn asked beside the recognition."""
    if not on(uid) or not measuring(now):
        return None
    now = time.time() if now is None else now
    for k in [k for k, v in _pending.items() if now - v["t"] > KEEP]:
        del _pending[k]
    if len(_pending) >= 200:
        return None
    key = secrets.token_urlsafe(9)
    entry = _pending[key] = {"uid": uid, "t": now, "p": None, "ms": None}
    try:
        entry["task"] = asyncio.get_running_loop().create_task(_ask(entry, data, cfg))
    except RuntimeError:
        del _pending[key]
        return None
    return key


async def settle(key, timeout=GRACE):
    """After the recognition: Smart Turn usually answered long before; at most `timeout` more, then it goes on alone."""
    task = (_pending.get(key) or {}).get("task")
    if task is not None:
        await asyncio.wait({task}, timeout=timeout)


def report(uid, turns, now=None):
    """The page's reports "id:regel:0|1,…" for this profile's own pauses: one journal line and one row each."""
    if not uid or not isinstance(turns, str) or not turns:
        return 0
    now = time.time() if now is None else now
    d, done = _load(), 0
    for part in turns.split(",")[:8]:
        m = REPORT.match(part.strip())
        e = _pending.get(m.group(1)) if m else None
        if not e or e["uid"] != uid:
            print("hoeren: satzende unbekannt", flush=True)
            continue
        del _pending[m.group(1)]
        if len(d["rows"]) >= ROWS:
            continue
        regel, weiter = m.group(2), int(m.group(3))
        p = "none" if e["p"] is None else f"{e['p']:.2f}"
        ms = "-" if e["ms"] is None else e["ms"]
        print(f"hoeren: satzende p={p} regel={regel} weiter={'ja' if weiter else 'nein'} ms={ms}", flush=True)
        d["rows"].append([e["p"], regel, weiter, e["ms"]])
        d["since"] = d["since"] or now
        done += 1
    if done:
        write_json(FILE, d)
        if len(d["rows"]) >= ROWS:
            print(f"hoeren: satzende messung fertig n={len(d['rows'])}", flush=True)
        try:
            import live
            live.mark("Satzende am Tonfall", f"{done} Pause gemessen" if done == 1 else f"{done} Pausen gemessen")
        except Exception:
            pass
    return done


def summary(now=None):
    """The numbers for the admin: how many pauses, hits, false alarms and the waiting it would have saved."""
    d = _load()
    rows = [r for r in d["rows"] if r[1] in REGELN]
    rated = [r for r in rows if isinstance(r[0], (int, float))]
    hits = [r for r in rated if r[0] >= HIGH and not r[2]]
    false = [r for r in rated if r[0] >= HIGH and r[2]]
    low = [r for r in rated if r[0] <= LOW and r[2]]
    ms = sorted(r[3] for r in rated if isinstance(r[3], int))
    saved = sum(END_MS - PAUSE_MS for r in hits if r[1] == "neutral") / 1000
    return {"n": len(rows), "rated": len(rated), "hits": len(hits), "false": len(false), "low_right": len(low),
            "saved_s": round(saved, 2), "ms": ms[len(ms) // 2] if ms else None, "since": d["since"],
            "rows": ROWS, "days": DAYS, "measuring": measuring(now)}
