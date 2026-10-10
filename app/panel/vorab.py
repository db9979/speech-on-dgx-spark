"""Vorab holen bei Rückfrage (plan „Anfrage aufteilen“, V01.0.307).

When an answer ends with a question back to the person ("Für welchen Tag?"), the panel already fetches the
data the next answer will most likely need, while the question is still being spoken: the calendar of the
next days, the newest mails, the weather at home, the parcels. It only warms the caches those modules keep
anyway (calendars, mail, weather, parcels), so the tool call in the next answer finds its data at once. Nothing
is said, shown, switched or stored elsewhere, and the language model never sees any of it unless it calls the
tool in the next answer, with the rights and locks of that answer.

What to fetch is decided by fixed rules: the groups of intent.classify on the person's own words, and on the
question back only when nothing from outside was read in this answer. Only reading jobs, only those whose tool
this turn offered the profile (the same rights), at most MAX_JOBS, each at most JOB_SECONDS. It runs right away,
not behind "Vorrang für Sprache" (vorrang.py): that would wait until the speaking is over, and these are
network calls to the profile's own services, nothing that loads the graphics card.

Off until the admin allows it (chat.prefetch, below Gezielte Werkzeugwahl) and the profile switches it on
(setting prefetch). Guests never, a voice not recognised at a shared speaker never, a question from another
program over MCP never.
"""
import asyncio
import datetime
import re
import time

import features
import profiles

MAX_JOBS = 3
JOB_SECONDS = 5
MAX_RUNNING = 4         # prefetches at once on the whole Spark
KEEP_SECONDS = 90       # how long a prefetch counts as "ready" for the next answer (log only)
MAX_SAID = 400          # characters of the question back that are looked at

# group -> (the tool that must have been offered, label for the log)
JOBS = {"kalender": ("calendar_events", "Kalender"), "mail": ("mail_list", "Mails"),
        "wetter": ("weather", "Wetter"), "paket": ("parcels", "Pakete")}
# tool names whose call in the next answer uses a prefetch of that group
USES = {"calendar_events": "kalender", "daily_briefing": "kalender", "mail_list": "mail", "weather": "wetter",
        "parcels": "paket"}

_running = {}           # uid -> task
_ready = {}             # uid -> {group: time fetched}
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def admin_on(cfg=None):
    return features.admin_on("vorab", cfg)


def on(cfg, who):
    return bool(who and admin_on(cfg) and profiles.settings(who["id"]).get("prefetch") is True)


def asks_back(said):
    """The answer ends with a question to the person (its last sentence ends with "?")."""
    text = str(said or "").strip()[-MAX_SAID:]
    parts = [p for p in SENTENCE_END.split(text) if p.strip()]
    return bool(parts) and parts[-1].rstrip(" \"'“”»«)").endswith("?")


def groups(turn, said, st, called):
    """The groups to fetch for: from the person's own words, and from the question back when this answer read
    nothing from outside (then its words come from the person and the profile's own data only)."""
    import intent
    names = list(getattr(turn, "route", None).names if getattr(turn, "route", None) else [])
    if not st.get("mail") and not st.get("outside") and not getattr(turn, "carry", None):
        names += intent.classify(str(said or "")[-MAX_SAID:]).names
    offered = getattr(turn, "offered_all", set()) or set()
    out = []
    for g in names:
        if g in JOBS and g not in out and JOBS[g][0] in offered and JOBS[g][0] not in called:
            out.append(g)
    return out[:MAX_JOBS]


async def _job(group, turn):
    import calendars
    import chat
    uid = turn.who["id"]
    if group == "kalender":
        zone = chat.user_zone(turn.body.get("tz"))
        start = datetime.datetime.combine(datetime.datetime.now(zone).date(), datetime.time(), zone)
        await calendars.events(uid, start, start + datetime.timedelta(days=8), zone)
    elif group == "mail":
        import mail
        await asyncio.to_thread(mail.find, uid, "", 7, False, 8)   # what mail_list asks for without details
    elif group == "wetter":
        import weather
        w = weather.get(uid)
        if w:
            await weather.forecast(w["lat"], w["lon"], 7)
    elif group == "paket":
        import parcels
        await asyncio.to_thread(parcels.scan, uid)


async def _run(turn, todo):
    uid = turn.who["id"]
    t0 = time.time()
    res = await asyncio.gather(*(asyncio.wait_for(_job(g, turn), JOB_SECONDS) for g in todo), return_exceptions=True)
    done = [g for g, r in zip(todo, res) if not isinstance(r, BaseException)]
    failed = [f"{JOBS[g][1]} ({type(r).__name__})" for g, r in zip(todo, res) if isinstance(r, BaseException)]
    now = time.time()
    _ready[uid] = {g: now for g in done}
    print(f"vorab: geholt {', '.join(JOBS[g][1] for g in done) or 'nichts'}"
          + (f" | fehlgeschlagen {', '.join(failed)}" if failed else "") + f" | {now - t0:.1f} s", flush=True)


def after(turn, said, st, calls, tr=None):
    """Called once at the end of an answer (chat.py). Starts the prefetch in the background and returns at once."""
    try:
        who = getattr(turn, "who", None)
        if not (who and getattr(turn, "own_browser", False) and getattr(turn, "private_ok", False)):
            return None
        if getattr(turn, "mcp", None):   # "Spark fragen" from another program: its question is outside text
            return None
        if not on(getattr(turn, "ccfg", None), who) or not asks_back(said):
            return None
        # "mail_list (Panel)": what the panel fetched itself in this answer (Eindeutiges direkt abrufen) counts too
        todo = groups(turn, said, st, {str(c.get("name") or "").split(" ")[0] for c in calls or []})
        if not todo:
            return None
        task = _running.get(who["id"])
        if task and not task.done():
            return None
        for k in [k for k, v in _running.items() if v.done()]:
            _running.pop(k, None)
        if len(_running) >= MAX_RUNNING:
            print("vorab: zu viele gleichzeitig, ausgelassen", flush=True)
            return None
        if tr:
            tr.step("tool", "Vorab geholt (Panel)", time.time(), time.time(), panel=True, n=len(todo))
        _running[who["id"]] = asyncio.get_running_loop().create_task(_run(turn, todo))
        return todo
    except Exception as e:   # a prefetch must never break an answer
        print("vorab:", type(e).__name__, flush=True)
        return None


def used(uid, name, now=None):
    """The next answer calls a tool whose data was prefetched: logged once (to see whether it pays off)."""
    group = USES.get(name)
    got = _ready.get(uid) or {}
    if not group or group not in got:
        return False
    fresh = (now or time.time()) - got.pop(group) < KEEP_SECONDS
    if fresh:
        print(f"vorab: genutzt {JOBS[group][1]}", flush=True)
    return fresh
