"""Wachposten (plan plaene/sicheres-ki-system, Dominik 2026-10-18 "1-3"): the Spark tells its admins by itself when
something happens on the doors and locks, so nobody has to read the change log to notice it.

Fixed rules on what the change log (guard.log) notes, never a model; the words are the log's own fixed words
(guard.LIVE_WORDS), never a name, an address or a detail:
    sperre      a lockout after wrong sign-ins starts (any *_failed entry with "locked")
    zugang      a new way in: trusted browser, passkey, a program over MCP, a paired Spark, an invitation used,
                an iPhone with a review code
    schutz      protection changed: admin password, second step off or reset, roles, main admin, Notaus key,
                a sensitive setting, the GitHub or report token, the emergency access, a backup restored or
                downloaded, the backup to the outside set up
    protokoll   the change log was changed afterwards (guard.chain_daily)
    qualitaet   the quality test after an update has questions newly broken (health.quality_alert, quality.last)
The Selbst-Notaus (notaus.AUTO) stays what it is: it raises stage 1 and tells the admins itself; the Wachposten
warns before, on single events.

Each admin profile (notaus.admin_uids) gets one push note per round (every LOOP_S) with what came together, at
most MAX_DAY notes a day; what is left waits for the next day and comes as one note. Day and night alike: a
security note is not a reminder. Nothing while the switch is off: the rules only count from the moment it is on.
Admin switch chat.wachposten (Funktionen → Wachposten, off). STATE/wachposten.json keeps the queue (rule, fixed
words, time), the notes of the day and the newest quality run told. Logs: "wachposten: gemeldet | 2 Einträge |
1 Admin(s)", "wachposten: keine Admins mit Gerät", "wachposten: Tageshöchstzahl erreicht".
"""
import asyncio
import os
import threading
import time

import features
from common import STATE, read_json, write_json

FILE = os.path.join(STATE, "wachposten.json")
LOOP_S = 60
MAX_DAY = 12          # notes per day; what is left waits for the next day
MAX_QUEUE = 200       # entries kept waiting; the oldest go first
MAX_SENT = 7 * MAX_DAY   # times of the notes sent, for the day's count and the week on Zustand
SHOW = 6              # entries named in one note, the rest only counted
WAY = "Zustand → Logs → Änderungen"
RULES = {
    "sperre": ("Sperre nach falschen Anmeldungen", "Lockout after wrong sign-ins"),
    "zugang": ("Neuer Zugang", "New way in"),
    "schutz": ("Schutz geändert", "Protection changed"),
    "protokoll": ("Änderungsprotokoll verändert", "Change log changed"),
    "qualitaet": ("Qualitätstest schlechter", "Quality test worse"),
}
EVENTS = {
    "zugang": ("trusted_browser", "passkey_added", "mcp_connect", "verbund_paired", "invite_used", "invite_app",
               "review_used", "chat_key_added"),
    "schutz": ("admin_password_changed", "admin_mfa_off", "profile_mfa_reset", "admin_mfa_forget", "admin_role",
               "admin_roles_switch", "admin_main", "notaus_key_new", "config_sensitive", "github_token", "report_token",
               "notzugang_cli", "restore", "backup_download", "offsite_settings"),
    "protokoll": ("audit_chain_broken",),
}
RULE_OF = {e: r for r, evs in EVENTS.items() for e in evs}

_lock = threading.Lock()
_capped = {"day": ""}


def an(c=None):
    """Funktionen → Wachposten (admin, off)."""
    return features.admin_on("wachposten", c)


def _day(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _read():
    d = read_json(FILE, {})
    d = d if isinstance(d, dict) else {}
    q = [x for x in d.get("queue") or [] if isinstance(x, dict) and x.get("r") in RULES
         and isinstance(x.get("w"), str) and isinstance(x.get("t"), (int, float))]
    sent = [t for t in d.get("sent") or [] if isinstance(t, (int, float))]
    return {"queue": q[-MAX_QUEUE:], "sent": sent[-MAX_SENT:], "quality": d.get("quality") or 0}


def _write(d):
    write_json(FILE, d, mode=0o600)


def rule_for(item):
    """The rule an entry of the change log falls under, or None (fixed: the event's word and "locked")."""
    ev = str(item.get("event") or "")
    if ev.endswith("_failed") and item.get("locked"):
        return "sperre"
    return RULE_OF.get(ev)


def words_for(item):
    """The fixed words for one entry: the change log's own Live words, never a detail."""
    import guard
    ev = str(item.get("event") or "")
    if ev in guard.LIVE_WORDS:
        return guard.LIVE_WORDS[ev][1]
    return "falsche Anmeldungen, Sperre begonnen" if rule_for(item) == "sperre" else RULES.get(rule_for(item), ("",))[0]


def seen(item):
    """Called by guard.log for every entry; queues what a rule names. Never raises, nothing while off."""
    try:
        rule = rule_for(item)
        if not rule or not an():
            return
        with _lock:
            d = _read()
            d["queue"].append({"r": rule, "w": words_for(item), "t": int(item.get("t") or time.time())})
            d["queue"] = d["queue"][-MAX_QUEUE:]
            _write(d)
    except Exception as e:   # noqa: BLE001 - the change log never fails because of the Wachposten
        print("wachposten: seen", type(e).__name__, flush=True)


def _quality(d, now):
    """A quality run with questions newly broken, told once per run."""
    import health
    import quality
    if not health.quality_alert():
        return
    res = quality.last() or {}
    t = int(res.get("t") or 0)
    if t and t != d["quality"]:
        n = len([x for x in res.get("cases") or [] if x.get("new")])
        d["quality"] = t
        d["queue"].append({"r": "qualitaet", "w": f"{n} Frage(n) neu kaputt", "t": t})


def text(items):
    """(title, body) of one note: what came together, oldest first, in fixed words with times."""
    from collections import Counter
    rules = Counter(x["r"] for x in items)
    title = "🛡️ Wachposten: " + " · ".join(RULES[r][0] for r in RULES if rules[r])
    lines = [f"{time.strftime('%H:%M', time.localtime(x['t']))} {x['w']}" for x in items[:SHOW]]
    more = len(items) - SHOW
    body = "; ".join(lines) + (f"; und {more} weitere" if more > 0 else "") + f". Mehr unter {WAY}."
    return title, body


async def tick(now=None):
    """One round: queue the quality run, then one note per admin with what waits. Returns the number of admins reached."""
    import live
    import notaus
    import push
    now = time.time() if now is None else now
    if not an():
        return 0
    with _lock:
        d = _read()
        _quality(d, now)
        _write(d)
    if not d["queue"]:
        return 0
    today = [t for t in d["sent"] if _day(t) == _day(now)]
    if len(today) >= MAX_DAY:
        if _capped["day"] != _day(now):
            _capped["day"] = _day(now)
            print(f"wachposten: Tageshöchstzahl erreicht | {len(d['queue'])} wartet bis morgen", flush=True)
        return 0
    items = sorted(d["queue"], key=lambda x: x["t"])
    title, body = text(items)
    reached = 0
    for uid in notaus.admin_uids():
        if not push.reachable(uid, False):
            continue
        try:
            reached += 1 if await push.send(uid, title, body, tag="wache", private=False) else 0
        except Exception as e:   # noqa: BLE001 - one admin's device must not stop the others
            print("wachposten: push", type(e).__name__, flush=True)
    if not reached:
        print("wachposten: keine Admins mit Gerät | wartet", flush=True)
        return 0
    with _lock:
        d = _read()
        told = {(x["r"], x["w"], x["t"]) for x in items}
        d["queue"] = [x for x in d["queue"] if (x["r"], x["w"], x["t"]) not in told]
        d["sent"] = (d["sent"] + [int(now)])[-MAX_SENT:]
        _write(d)
    print(f"wachposten: gemeldet | {len(items)} Einträge | {reached} Admin(s)", flush=True)
    live.event("Sicherheit", f"Wachposten-Hinweis an {reached} Admin{'s' if reached > 1 else ''}")
    return reached


async def loop():
    while True:
        await asyncio.sleep(LOOP_S)
        try:
            await tick()
        except Exception as e:   # noqa: BLE001 - the loop goes on
            print("wachposten: loop", type(e).__name__, flush=True)


def for_status(now=None):
    """Zustand → Sicherheit: on, waiting entries and the notes of the last 7 days (numbers only)."""
    now = time.time() if now is None else now
    d = _read()
    return {"on": an(), "waiting": len(d["queue"]), "week": len([t for t in d["sent"] if now - t < 7 * 86400])}
