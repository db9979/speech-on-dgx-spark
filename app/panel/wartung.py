"""Wartungspause (plan plaene/wartungspause.md, Dominik 2026-10-14 „1b 2c 3a 4a 5a 6a“): while the language model
(own or qwen38), the speech recognition or the speech output is updated, the Spark pauses on purpose instead of failing.

An admin starts it under Zustand → Wartungspause (or on the Spark: sudo speech-spark pause llm 30) for one or more parts
(PARTS) and at most MAX_MIN minutes. While it holds:
- a question that needs the language model gets a fixed sentence at once (chat.LLM_GONE "llm_pause"), never the model's
  time-out; the Weiche and System One do not ask the model either;
- background work that asks the model waits (vorrang.quiet) and runs afterwards, one after the other;
- the Dienst-Wächter sends no outage note for a paused part and the watchdog (health.watch_once) restarts nothing of it;
- Zustand and the Live view show the part as "Pause".
Automatic (chat.wartung_auto, Funktionen → Wartungspause → "Automatisch bei Neustart", off): the loop looks at the
systemd units of the parts (WATCH); when one restarts or switches (activating, or started anew since the last look)
and it was not our own watchdog nor our own update, the part pauses for AUTO_MIN minutes, by "automatisch". Such a
pause ends as soon as the part answers OK_N times in a row, not only at the end of its time.
Speakers (P2): with the speech output paused an ESP32 speaker and Home Assistant (Wyoming) play the short sentence
from a file the loop made earlier (esp32.pause_clip, CLIP_DAYS), else a short tone; with the speech recognition
paused a speaker says the sentence at once instead of listening.
It ends with "Weiter" (Zustand, sudo speech-spark weiter) or by itself: at the end of its time the panel looks at the
paused parts; once they answer OK_N times in a row the pause ends. Do they not answer, the pause stays, the admins get
one push and from then on the Dienst-Wächter counts it as an outage again (overdue).

Models on another computer (plan Raspberry-Pi split, B4c): a pause there (its `speech-spark pause`, `modelle messen`,
a switch) pauses the same parts here too, as long as its time runs; its status brings it (steuer.cached, kept fresh
by the loop), so a question never waits for that computer. "Weiter" here ends both. The automatic looks at the
model units there through the Wärter. On the model computer itself the shell command writes the pause without the
panel's switch: the panel decides with its own switch whether it counts.

It is no safety switch: it never lifts or eases a Notaus, the Notaus always goes first. A damaged file means no pause
(the Spark goes on as usual). STATE/wartung.json is run time state (backup.STATE_LOCAL). Journal lines start with
"wartung:" and hold only fixed words and numbers.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # common.py, also as a script (speech-spark pause)
import features  # noqa: E402
import guard  # noqa: E402
from common import WARTUNG_FILE, load_config, model_side, write_json  # noqa: E402

FILE = WARTUNG_FILE
# the parts that can pause: id -> (Dienst-Wächter id, name de, name en)
PARTS = {"llm": ("qwen", "Sprachmodell", "Language model"), "asr": ("asr", "Spracherkennung", "Speech recognition"),
         "tts": ("tts", "Sprachausgabe", "Speech output"), "bild": ("bild", "Bilder malen", "Painting pictures")}
MINUTES = (15, 30, 60, 120)    # the choices on Zustand; the shell command takes any whole number in MIN_MIN..MAX_MIN
MIN_MIN, MAX_MIN = 5, 240
MORE = 15                      # "+15 min"
OK_N = 2                       # good checks in a row before the pause ends by itself
EVERY = 15                     # seconds between two looks of the loop
CHANNELS = ("panel", "app", "kommandozeile", "automatisch")
AUTO_MIN = 30                  # an automatic pause: at most this long before it counts as overdue
AUTO_GRACE = 180               # a restart by our own watchdog this many seconds ago is no update (health._restarts)
AUTO_SKIP = ("qwen38-keepalive", "qwen38-dashboard")   # qwen38 units that are no model
MOVING = ("activating", "deactivating", "reloading")
CLIP_DAYS = 1                  # the speakers' sentence is made anew once a day (voice or model may have changed)
# the short sentence (no minutes): when the time is over and for the speakers' file
SHORT = ("Ich werde gerade aktualisiert und bin gleich wieder da.", "I am being updated right now and will be back shortly.")
# Notbetrieb (plan Raspberry-Pi split B5): the model computer does not answer (off, restarting); its own file too
NOTBETRIEB = ("Der Spark macht gerade Pause.", "The Spark is taking a break right now.")

_cache = {"key": None, "state": None}
_seen = {"since": None, "bad": False}   # what the loop already wrote into the journal
_n = {"asked": 0, "held": 0, "oks": 0}  # this pause: answered with the sentence, background work held, good checks
_units = {}                             # unit -> (state, entered) at the last look of the automatic


def admin_on(c=None):
    return features.admin_on("wartung", c)


def auto_on(c=None):
    """Funktionen → Wartungspause → "Automatisch bei Neustart" (chat.wartung_auto, below chat.wartung)."""
    return features.admin_on("wartungauto", c)


def _empty():
    return {"on": False, "parts": [], "since": 0, "until": 0, "by": "", "channel": "", "overdue": False, "told": False}


def _clean(d):
    if not isinstance(d, dict) or d.get("on") is not True:
        return _empty()
    parts = [p for p in PARTS if p in (d.get("parts") or [])]
    since, until = d.get("since"), d.get("until")
    if not parts or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (since, until)) or until <= since:
        return None
    return {"on": True, "parts": parts, "since": float(since), "until": float(until), "by": str(d.get("by") or "")[:40],
            "channel": d.get("channel") if d.get("channel") in CHANNELS else "panel",
            "overdue": d.get("overdue") is True, "told": d.get("told") is True}


def _fern(now=None):
    """The model computer's pause while its time runs (from its last status, never asked here), else None."""
    try:
        import steuer
        if not steuer.remote():
            return None
        p = _clean((steuer.cached() or {}).get("pause") or {})
    except Exception:
        return None
    return p if p and p["on"] and (time.time() if now is None else now) < p["until"] else None


def state(now=None):
    """The pause here, together with the model computer's (fern=True) when the models run there."""
    s = _local()
    f = _fern(now)
    if not f:
        return s
    if not s["on"]:
        return dict(f, fern=True, overdue=False, told=False)
    return dict(s, parts=[p for p in PARTS if p in s["parts"] or p in f["parts"]], until=max(s["until"], f["until"]),
                fern=True)


def _local():
    """The pause as the file says (read anew when it changed; a stat per call). Damaged: no pause."""
    try:
        st = os.stat(FILE)
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return _empty()
    if _cache["key"] == key and _cache["state"] is not None:
        return _cache["state"]
    try:
        with open(FILE, encoding="utf-8") as f:
            d = _clean(json.load(f))
    except (OSError, ValueError):
        d = None
    if d is None:
        if not _seen["bad"]:
            print("wartung: datei unlesbar, keine pause", flush=True)
        _seen["bad"] = True
        d = _empty()
    _cache.update(key=key, state=d)
    return d


def _pause(part):
    try:
        s = state()
        return bool(s["on"] and part in s["parts"] and admin_on())
    except Exception:
        return False


def notbetrieb():
    """Notbetrieb: the models run on another computer that has not answered lately (steuer.weg); every part counts
    as paused (the fixed sentence at once, background work waits), but the Dienst-Wächter reports it (not quiet)."""
    try:
        import steuer
        return steuer.weg()
    except Exception:
        return False


def paused(part):
    """True while this part (llm, asr, tts, bild) is paused and the admin switch is on, or in Notbetrieb; there the
    speech recognition goes on when this computer's Parakeet hears (notbetrieb.hoert, chat.notbetrieb_asr)."""
    if _pause(part):
        return True
    if not notbetrieb():
        return False
    if part == "asr":
        import notbetrieb as nb
        return not nb.hoert()
    return True


def quiet(part):
    """The Dienst-Wächter and the watchdog leave the part alone: paused on purpose and its time not yet over."""
    return _pause(part) and not state()["overdue"]


def left_min(now=None):
    now = time.time() if now is None else now
    s = state()
    return max(0, int((s["until"] - now + 59) // 60)) if s["on"] else 0


def sentence(en=False, now=None):
    """The fixed answer while the language model pauses (chat.py), counted for Zustand."""
    _n["asked"] += 1
    if not state()["on"] and notbetrieb():
        return NOTBETRIEB[1 if en else 0]
    m = left_min(now)
    if state()["overdue"] or m < 1:
        return SHORT[1 if en else 0]
    if en:
        return f"I am being updated right now and will be back in about {m} minute{'s' if m != 1 else ''}."
    return f"Ich werde gerade aktualisiert und bin in etwa {m} Minute{'n' if m != 1 else ''} wieder da."


def held():
    """vorrang.quiet: a background job waits for the pause to end."""
    _n["held"] += 1


def _write(d):
    write_json(FILE, d)
    _cache.update(key=None, state=None)


def _names(parts):
    return "+".join(parts)


def _event(text):
    """Zustand → Live, "Ereignisse" (fixed words); never raises."""
    try:
        import live
        live.event("Dienste", text)
    except Exception:
        pass


def start(parts, minutes, by="", channel="panel", now=None):
    """Starts a pause (or changes the parts and time of the running one). Returns the state; ValueError for a wrong
    part or time."""
    now = time.time() if now is None else now
    parts = [p for p in PARTS if p in (parts or [])]
    if not parts or any(p not in PARTS for p in parts):
        raise ValueError("parts")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not MIN_MIN <= minutes <= MAX_MIN:
        raise ValueError("minutes")
    old = _local()
    d = {"on": True, "parts": parts, "since": old["since"] if old["on"] else now, "until": now + minutes * 60,
         "by": str(by or "")[:40], "channel": channel if channel in CHANNELS else "panel", "overdue": False, "told": False}
    if not old["on"]:
        _n.update(asked=0, held=0, oks=0)
    _write(d)
    _seen["since"] = d["since"]
    print(f"wartung: an {_names(parts)} {d['channel']} {minutes} min", flush=True)
    _event("Wartungspause an: " + ", ".join(PARTS[p][1] for p in parts))
    return state()


def more(minutes=MORE, now=None):
    """"+15 min": the running pause lasts longer (never more than MAX_MIN from now)."""
    now = time.time() if now is None else now
    s = _local()
    if not s["on"]:
        raise ValueError("off")
    d = dict(s, until=min(max(s["until"], now) + minutes * 60, now + MAX_MIN * 60), overdue=False, told=False)
    _write(d)
    print(f"wartung: verlaengert {_names(s['parts'])} {minutes} min", flush=True)
    return state()


def end(why, now=None):
    """Ends the pause (why: weiter, geprueft, schalter_aus) and, with "weiter", the model computer's too. Returns the
    minutes it lasted, None when none ran."""
    now = time.time() if now is None else now
    s, f = _local(), _fern(now)
    if f and why == "weiter":
        import steuer
        d = steuer.call("weiter")
        ok = isinstance(d, dict) and d.get("ok") is True
        print(f"wartung: modell-rechner weiter {'ok' if ok else 'fehler'}", flush=True)
        if ok:
            with steuer._lock:
                steuer._status.update(t=0.0)       # its next status is asked fresh
    if not s["on"]:
        return int((now - f["since"]) // 60) if f and why == "weiter" else None
    try:
        os.remove(FILE)
    except FileNotFoundError:
        pass
    _cache.update(key=None, state=None)
    mins = int((now - s["since"]) // 60)
    print(f"wartung: aus {_names(s['parts'])} {why} nach {mins} min · {_n['asked']} anfragen · {_n['held']} hintergrund gewartet",
          flush=True)
    _seen["since"] = None
    _n["oks"] = 0
    _event("Wartungspause beendet")
    return mins


async def _answers(part, cfg):
    """Does the part answer? The Dienst-Wächter's own probe (no request of its own kind, nothing new to the outside)."""
    import dienstwacht
    sid = PARTS[part][0]
    parts = dienstwacht.active(cfg.get("chat", {}), cfg).get(sid) or {}
    if not parts:
        return False
    res = await asyncio.gather(*(dienstwacht.probe(sid, k, p, cfg) for k, p in parts.items()), return_exceptions=True)
    return all(getattr(r, "ok", False) for r in res)


async def tell_admins(title, body):
    import notaus
    import push
    for uid in notaus.admin_uids():
        try:
            await push.send(uid, title, body, tag="wartung", private=False)
        except Exception as e:
            print("wartung: push an admin fehlgeschlagen", type(e).__name__, flush=True)


async def tick(now=None, answers=_answers):
    """One look of the loop: a pause started by the shell command goes into the journal, the switch off ends it, its
    time over (an automatic pause: as soon as its units stopped starting): the parts are looked at, OK_N good looks in a
    row end it; not answering when the time is over: the pause stays, one push."""
    now = time.time() if now is None else now
    try:            # models on another computer: its status (with its pause) stays fresh without a question waiting
        import steuer
        if steuer.remote():
            await asyncio.to_thread(steuer.status)
    except Exception as e:
        print("wartung: modell-rechner status fehlgeschlagen", type(e).__name__, flush=True)
    s = _local()
    if not s["on"]:
        return None
    if not admin_on():
        end("schalter_aus", now)
        return "aus"
    if _seen["since"] != s["since"]:
        _seen["since"] = s["since"]
        _n.update(asked=0, held=0, oks=0)
        print(f"wartung: an {_names(s['parts'])} {s['channel']} {max(0, int((s['until'] - s['since']) // 60))} min", flush=True)
    auto = s["channel"] == "automatisch"
    if now < s["until"] and not auto:
        return "pause"
    if auto and now < s["until"] and any((_units.get(u) or ("",))[0] in MOVING for p in s["parts"] for u in watched()[p]):
        return "pause"   # still starting (as the automatic saw it a moment ago): no check yet
    cfg = load_config()
    good = True
    for p in s["parts"]:
        try:
            good = good and await answers(p, cfg)
        except Exception as e:
            print("wartung: pruefung fehlgeschlagen", p, type(e).__name__, flush=True)
            good = False
    if good:
        _n["oks"] += 1
        print(f"wartung: pruefung gut {_n['oks']} von {OK_N}", flush=True)
        if _n["oks"] >= OK_N:
            end("geprueft", now)
            return "aus"
        return "pruefen"
    _n["oks"] = 0
    if now < s["until"]:
        return "pause"
    if not s["overdue"]:
        _write(dict(s, overdue=True, told=True))
        print(f"wartung: zeitlimit {_names(s['parts'])} antwortet nicht, pause bleibt", flush=True)
        names = ", ".join(PARTS[p][1] for p in s["parts"])
        await tell_admins("Wartungspause läuft weiter",
                          f"{names} antwortet nach der geplanten Zeit noch nicht. Die Pause bleibt, bis es wieder antwortet "
                          "oder du unter Zustand → Wartungspause „Weiter“ drückst.")
    return "wartet"


# ---------------------------------------------------------------- automatic (P2)
def watched():
    """{part: [systemd units]} the automatic looks at."""
    from common import OWN_LLM_UNITS, QWEN38_UNITS, UNITS
    return {"llm": [u for u in QWEN38_UNITS if u not in AUTO_SKIP] + [OWN_LLM_UNITS["llm"], OWN_LLM_UNITS["llmtor"]],
            "asr": [UNITS["asr"], UNITS["asr-engine"]],
            "tts": [UNITS["tts"], UNITS["tts-engine"], UNITS["tts-design"]]}


def _look(unit):
    """(ActiveState, when it last became active) of a unit, None when it is not installed. A model unit on another
    computer: from its Wärter's status."""
    import core
    import steuer
    if steuer._remote_unit(unit):
        u = ((steuer.status() or {}).get("einheiten") or {}).get(unit) or {}
        return None if u.get("state") in (None, "unknown") else (u["state"], str(u.get("eintritt", "")))
    code, out = core.run(["systemctl", "show", unit, "-p", "LoadState,ActiveState,ActiveEnterTimestampMonotonic"])
    props = dict(x.split("=", 1) for x in out.splitlines() if "=" in x)
    if code != 0 or props.get("LoadState") != "loaded":
        return None
    return props.get("ActiveState", ""), props.get("ActiveEnterTimestampMonotonic", "")


def _ours(unit, now):
    """Did our own watchdog restart it just now (health.py)? Then it is no update but a repair."""
    try:
        import health
        return any(now - t < AUTO_GRACE for t in health._restarts.get(unit, []))
    except Exception:
        return False


def restarted(look=_look, now=None):
    """The parts with a unit that restarts or switches since the last look ([] at the first look: only noted)."""
    now = time.time() if now is None else now
    hit = []
    for part, units in watched().items():
        for u in units:
            cur, old = look(u), _units.get(u)
            _units[u] = cur
            if cur is None or old is None:
                continue
            if (cur[0] in MOVING or (cur[0] == "active" and cur[1] != old[1])) and not _ours(u, now):
                if part not in hit:
                    hit.append(part)
    return hit


async def auto_tick(now=None, look=_look):
    """One look of the automatic: a restarting part pauses by itself for AUTO_MIN minutes. Returns the parts paused."""
    now = time.time() if now is None else now
    if not auto_on():
        _units.clear()
        return []
    import update
    hit = await asyncio.to_thread(restarted, look, now)
    if not hit:
        return []
    if update.update_running():
        print("wartung: automatisch ignoriert eigenes_update", _names(hit), flush=True)
        return []
    if state()["on"]:
        print("wartung: automatisch ignoriert pause_laeuft", _names(hit), flush=True)
        return []
    start(hit, AUTO_MIN, "automatisch", "automatisch", now)
    print(f"wartung: automatisch erkannt {_names(hit)} neustart", flush=True)
    return hit


# ---------------------------------------------------------------- the speakers' sentence (P2)
async def clips_tick(now=None):
    """Keeps the speakers' file of the short sentence fresh while the speech output works (esp32.pause_clip)."""
    c = load_config().get("chat", {})
    import steuer
    if not (admin_on() or steuer.remote()) or paused("tts") or not (c.get("esp32") or c.get("wyoming")):   # only with speakers or Assist
        return False
    import esp32
    import notbetrieb
    now = time.time() if now is None else now
    made = await esp32.make_pause_clips(now)
    return await notbetrieb.make_clips(now, lambda text: esp32.tts_stream("", text)) or made


async def loop():
    while True:
        await asyncio.sleep(EVERY)
        for step in (auto_tick, clips_tick, tick):
            try:
                await step()
            except Exception as e:
                print("wartung: runde fehlgeschlagen", step.__name__, type(e).__name__, flush=True)


def view(now=None):
    """Zustand → Wartungspause: parts, times, who (a name only for the admin's page) and numbers, never contents."""
    now = time.time() if now is None else now
    s = state()
    out = {"on": admin_on(), "paused": s["on"], "parts": s["parts"], "since": s["since"] or None, "until": s["until"] or None,
           "left": left_min(now), "overdue": s["overdue"], "channel": s["channel"], "by": _by_name(s["by"]),
           "fern": s.get("fern", False),
           "asked": _n["asked"] if s["on"] else 0, "held": _n["held"] if s["on"] else 0,
           "choices": {"parts": [[k, v[1], v[2]] for k, v in PARTS.items()], "minutes": list(MINUTES), "more": MORE}}
    return out


def _by_name(by):
    if by in ("", "main", "admin"):
        return "Admin" if by else ""
    if by in ("kommandozeile", "automatisch"):
        return by.capitalize()
    try:
        import profiles
        prof = profiles.by_id(by)
        return prof["name"] if prof else ""
    except Exception:
        return ""


def for_live(now=None):
    """Zustand → Live: which parts pause and the numbers (never who or why)."""
    s = state()
    if not s["on"] or not admin_on():
        return {"on": False}
    return {"on": True, "parts": s["parts"], "left": left_min(now), "overdue": s["overdue"],
            "asked": _n["asked"], "held": _n["held"], "fern": s.get("fern", False)}


# ---------------------------------------------------------------- API (admin)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import core  # noqa: E402
from core import acting_profile, auth  # noqa: E402

router = APIRouter()
MAX_BODY = 256


def _who(request):
    elev = acting_profile(request)
    return "main" if not elev else elev["id"]


@router.get("/api/admin/wartung", dependencies=[Depends(auth)])
def get_wartung():
    return view()


@router.post("/api/admin/wartung", dependencies=[Depends(auth)])
async def post_wartung(request: Request):
    """Starts the pause (parts, minutes) or, with {"more": true}, gives the running one MORE minutes."""
    guard.limit(request, "wartung", admin=True)
    if not admin_on():
        raise HTTPException(409, "Die Wartungspause ist aus (Funktionen → Wartungspause).")
    body = await core.json_body(request, MAX_BODY)
    channel = "app" if body.get("channel") == "app" else "panel"
    try:
        if body.get("more") is True:
            more()
            guard.log("wartung", by=_who(request), detail="Wartungspause verlängert")
        else:
            parts = body.get("parts")
            if not isinstance(parts, list) or not all(isinstance(p, str) for p in parts):
                raise ValueError("parts")
            start(parts, body.get("minutes"), _who(request), channel)
            guard.log("wartung", by=_who(request), detail="Wartungspause an: " + _names(state()["parts"]))
    except ValueError as e:
        print("wartung: abgelehnt", str(e)[:20], flush=True)
        raise HTTPException(400, {"parts": "Teil: llm, asr, tts oder bild", "minutes": f"Minuten: {MIN_MIN} bis {MAX_MIN}",
                                  "off": "Es läuft keine Wartungspause."}.get(str(e), "ungültig"))
    return view()


@router.post("/api/admin/wartung/weiter", dependencies=[Depends(auth)])
def post_weiter(request: Request):
    """„Weiter“: the admin says the update is done; the pause ends at once."""
    guard.limit(request, "wartung", admin=True)
    if end("weiter") is None:
        print("wartung: weiter ohne pause", flush=True)
    else:
        guard.log("wartung", by=_who(request), detail="Wartungspause beendet")
    return view()


# ---------------------------------------------------------------- shell command (sudo speech-spark pause|weiter)
USAGE = "speech-spark pause [llm|asr|tts|bild|alles][,…] [Minuten]  ·  speech-spark weiter  ·  speech-spark pause status"


def cli(args, now=None):
    """Runs as the panel's service user (speech-spark.sh). Returns (exit code, German line).
    On the model computer no panel loop looks at the parts at the end of the time (tick), so a pause there ends with
    its time: one left behind by an aborted `modelle messen` would otherwise block every later pause and its end."""
    now = time.time() if now is None else now
    s = _local()
    if s["on"] and now >= s["until"] and model_side():
        end("abgelaufen", now)
    if args[:1] == ["status"]:
        s = state()
        if not s["on"]:
            return 0, "Keine Wartungspause."
        return 0, f"Wartungspause: {', '.join(PARTS[p][1] for p in s['parts'])}, noch {left_min(now)} min" + \
            (" (Zeit um, Teil antwortet noch nicht)" if s["overdue"] else "")
    if args[:1] == ["weiter"]:
        mins = end("weiter", now)
        if mins is not None:
            guard.log("wartung", by="kommandozeile", detail="Wartungspause beendet")
        return 0, "Keine Wartungspause lief." if mins is None else f"Wartungspause beendet nach {mins} min."
    if not admin_on() and not model_side():   # on the model computer the panel's own switch decides
        print("wartung: kommandozeile abgelehnt schalter_aus", flush=True)
        return 1, "Die Wartungspause ist aus. Einschalten unter Funktionen → Wartungspause."
    what = args[0] if args else "llm"
    minutes = args[1] if len(args) > 1 else "30"
    parts = list(PARTS) if what in ("alles", "all") else what.split(",")
    try:
        start(parts, int(minutes) if minutes.isdigit() else -1, "kommandozeile", "kommandozeile", now)
    except ValueError:
        print("wartung: kommandozeile abgelehnt eingabe", flush=True)
        return 2, "Aufruf: " + USAGE
    guard.log("wartung", by="kommandozeile", detail="Wartungspause an: " + _names(state()["parts"]))
    s = state()
    return 0, f"Wartungspause an: {', '.join(PARTS[p][1] for p in s['parts'])}, höchstens {left_min(now)} min. " \
              "Beenden mit: sudo speech-spark weiter"


if __name__ == "__main__":
    code, line = cli(sys.argv[1:])
    print(line)
    sys.exit(code)
