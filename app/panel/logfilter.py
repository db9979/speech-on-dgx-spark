"""Diagnose filters for Zustand → Logs: the journal lines threads usually ask for ("room:", "esp32:",
"chat: web search", ...), so nobody has to type journalctl | grep on the console.

Admin only. The filters are a fixed list and the matching runs in Python: nothing the browser sends
reaches a shell or journalctl except numbers from fixed lists. Time window, lines read and lines shown
are capped; secrets that might still slip into a line (bot tokens, keys, passwords, URL logins) are
blacked out before the text leaves the panel.
"""
import datetime
import re
import subprocess
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import guard
from common import JOURNAL_NAMESPACE
from core import auth

router = APIRouter()

# areas: which kind of line it is, from the word before the colon (search before chat: it is a chat line)
AREAS = (("search", r"^chat: web search"), ("chat", r"^chat:"), ("weiche", r"^weiche:"), ("ha", r"^homeassistant:"),
         ("room", r"^room:"), ("esp32", r"^esp32:"), ("watch", r"^watch:"), ("telegram", r"^telegram:"), ("mail", r"^(mail|tidy|imap)\b"),
         ("vorrang", r"^vorrang:"))
_AREAS = [(k, re.compile(rx)) for k, rx in AREAS]
# filter keys the page may send: every area, "errors" (lines at level err) and "update" (the update unit)
FILTERS = dict(AREAS, update=None, errors=None)
# levels by fixed words, never by a model
ERR = re.compile(r"(?i)(error|exception|traceback|failed|broke|refused|timeout|timed out|fehler|not reachable)")
WARN = re.compile(r"(?i)\b(warn\w*|stalled|behind|ignored|asked again|retry|slow|refused)\b")
# a uvicorn access-log line: INFO:     1.2.3.4:5 - "GET /x?y HTTP/1.1" 200 OK
# update.sh: "Available: 46fb0e8 …", "Update finished: 46fb0e8 …", "  46fb0e8 subject"
COMMIT = re.compile(r"^(?:(?:Installed|Available|Update finished): |\s+)[0-9a-f]{7,40} ")
ACCESS = re.compile(r'^INFO:\s+\S+ - "[A-Z]+ \S+ HTTP/[\d.]+" (\d{3})\b')
# a fixed hint for the newest error: (area or None, regex on the message, German, English)
HINTS = (
    ("ha", r"\b401\b|Unauthorized", "Home-Assistant-Token abgelaufen oder falsch: Ich → Home Assistant.",
     "Home Assistant token expired or wrong: Me → Home Assistant."),
    ("room", r"tv check", "Fernseher-Abfrage in Home Assistant klappt nicht: ist Home Assistant erreichbar?",
     "TV check in Home Assistant fails: can the Spark reach Home Assistant?"),
    (None, r"(?i)tts.*(timeout|broke)|(timeout|broke).*tts", "Sprachausgabe hängt oder ist ausgelastet: Zustand → Monitoring, TTS-Engine.",
     "Speech output hangs or is busy: State → Monitoring, TTS engine."),
    (None, r"language model not reachable", "Sprachmodell nicht erreichbar: läuft qwen38?",
     "Language model not reachable: is qwen38 running?"),
    ("search", r".", "Websuche klappt nicht: SearXNG-Adresse unter Funktionen → Websuche prüfen.",
     "Web search fails: check the SearXNG address under Features → Web search."),
    ("esp32", r"(?i)connect", "Lautsprecher nicht erreichbar: Strom und WLAN prüfen.",
     "Speaker not reachable: check power and Wi-Fi."),
    ("telegram", r"(?i)conflict", "Ein anderes Programm nutzt denselben Bot-Token: Token nur an einer Stelle nutzen "
     "oder bei @BotFather einen neuen holen und unter Einbinden → Telegram eintragen.",
     "Another program uses the same bot token: use it in one place only or get a new one from @BotFather "
     "and enter it under Integrate → Telegram."),
    ("telegram", r".", "Telegram klappt nicht: Bot unter Einbinden → Telegram prüfen.",
     "Telegram fails: check the bot under Integrate → Telegram."),
)
_HINTS = [(a, re.compile(rx), de, en) for a, rx, de, en in HINTS]
_LINE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:[+-]\d\d:?\d\d|Z))\s+\S+\s+([^:\s]+?)(?:\[\d+\])?:\s?(.*)$")
BUCKETS = 12
UPDATE_UNIT = "speech-spark-update"
MINUTES = (10, 60, 120, 720, 1440)
LINES = (30, 100, 300, 1000)
READ_MAX = 20000          # journal lines read at most per request
OUT_MAX = 2 * 1024**2     # bytes of journal output looked at

_SECRETS = [
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}"), "***"),                       # Telegram bot token
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 ***"),
    (re.compile(r"(?i)\b(api[_-]?key|apikey|key|token|secret|password|passwort|pin)(\"?'?\s*[=:]\s*\"?'?)"
                r"[^\s\"',&;]+"), r"\1\2***"),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1***@"),               # user:pass@host
    (re.compile(r"(?i)/bot[^/\s]{20,}/"), "/bot***/"),
]


def redact(line):
    for rx, rep in _SECRETS:
        line = rx.sub(rep, line)
    return line


def read_journal(minutes, unit=None):
    """Journal lines of the speech-spark namespace (or one unit) from the last minutes; falls back to the
    system journal for installs from before the namespace, like common.journal."""
    base = ["journalctl", f"--since=-{int(minutes)}min", "-n", str(READ_MAX), "--no-pager", "-o", "short-iso"]
    if unit:
        base += ["-u", unit]
    out = ""
    for cmd in (base[:1] + [f"--namespace={JOURNAL_NAMESPACE}"] + base[1:], base):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout[-OUT_MAX:]
        except Exception:
            continue
        if out.strip() and "-- No entries --" not in out:
            return out
    return out


def parse(line):
    """One journal line -> dict with time, area, level and the message (secrets blacked out)."""
    raw = redact(line[:2000])
    m = _LINE.match(raw)
    ts, msg = (m.group(1), m.group(3)) if m else ("", raw)
    area = next((k for k, rx in _AREAS if rx.search(msg)), "")
    acc = ACCESS.search(msg)
    if COMMIT.search(msg):   # update.sh quotes commit subjects; their words ("Fehler") are no error
        level = ""
    elif acc:   # a web request: its status decides, never words in the address (?f=errors)
        code = int(acc.group(1))
        level = "err" if code >= 500 else ""
    else:
        level = "err" if ERR.search(msg) else "warn" if WARN.search(msg) else ""
    return {"ts": ts, "t": ts[11:19], "area": area, "level": level, "msg": msg, "raw": raw}


def keep(row, keys):
    if not keys or keys == ["update"]:
        return True
    areas = [k for k in keys if k not in ("update", "errors")]
    if "errors" in keys and row["level"] != "err":
        return False
    return not areas or row["area"] in areas


def _when(ts):
    try:
        return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        return None


def summary(rows, minutes, now):
    """Counts per area and level over the whole window, a small history per area and the newest error with
    a fixed hint. now comes from the caller (tests pass a fixed one)."""
    counts, spark = {}, {}
    start, size = now - minutes * 60, minutes * 60 / BUCKETS
    for r in rows:
        for k in (r["area"] or "other", "lines") + (("errors",) if r["level"] == "err" else ()) + \
                (("warnings",) if r["level"] == "warn" else ()):
            counts[k] = counts.get(k, 0) + 1
        w = _when(r["ts"])
        if r["area"] and w is not None and start <= w <= now + 60:
            b = spark.setdefault(r["area"], [0] * BUCKETS)
            b[min(BUCKETS - 1, max(0, int((w - start) // size)))] += 1
    last = next((r for r in reversed(rows) if r["level"] == "err"), None)
    hint = None
    if last:
        hint = next(({"de": de, "en": en} for a, rx, de, en in _HINTS
                     if (a is None or a == last["area"]) and rx.search(last["msg"])), None)
    errs = {}
    for r in rows:
        if r["level"] == "err":
            errs[r["area"] or "other"] = errs.get(r["area"] or "other", 0) + 1
    return {"counts": counts, "spark": spark, "errors_by_area": errs,
            "last_error": last and {"t": last["t"], "area": last["area"], "msg": last["msg"], "hint": hint}}


def pick(text, keys, lines):
    """Text form (kept for scripts and older pages): the newest matching raw lines."""
    rows = [parse(ln) for ln in text.splitlines() if ln.strip() and not ln.startswith("-- ")]
    hits = [r["raw"] for r in rows if keep(r, keys)]
    return hits[-lines:], len(hits)


@router.get("/api/logfilter", dependencies=[Depends(auth)])
def logfilter(request: Request, f: str = "", minutes: int = 60, lines: int = 100, format: str = "text"):
    guard.limit(request, "logs", admin=True)
    keys = [k for k in f.split(",") if k][:len(FILTERS)]
    if any(k not in FILTERS for k in keys) or minutes not in MINUTES or lines not in LINES \
            or format not in ("text", "json"):
        raise HTTPException(400, "bad filter, time or lines")
    text = read_journal(minutes, UPDATE_UNIT if "update" in keys else None)
    rows = [parse(ln) for ln in text.splitlines() if ln.strip() and not ln.startswith("-- ")]
    hits = [r for r in rows if keep(r, keys)]
    shown = hits[-lines:]
    names = ", ".join(keys) or "alles"
    head = f"# Filter: {names} · letzte {minutes} min · {len(shown)} von {len(hits)} Zeilen"
    if format == "json":
        return dict(summary(rows, minutes, time.time()), head=head, found=len(hits),
                    rows=[{k: r[k] for k in ("t", "area", "level", "msg", "raw")} for r in shown])
    return Response("\n".join([head] + [r["raw"] for r in shown]) + "\n", media_type="text/plain")


# ---- extra detail per area ("Ausführlich"): admin only, off by default, switches itself off ----
# Kept in memory only, so a restart switches it off too. The extra lines carry numbers and decisions
# (times, lengths, levels, rules), never heard or written text, names from the room or secrets.
VERBOSE = {"room": "room", "esp32": "esp32", "ha": "homeassistant", "chat": "chat"}   # area -> log prefix
VERBOSE_MINUTES = (15, 60, 240)
_verbose = {}


def verbose(area):
    until = _verbose.get(area)
    if until is None:
        return False
    if until > time.time():
        return True
    _verbose.pop(area, None)
    print(f"logs: detail {area} off (time up)", flush=True)
    return False


def detail(area, text):
    """One extra line while the area's detail switch is on. Callers pass numbers and decisions only."""
    if verbose(area):
        print(f"{VERBOSE[area]}: detail {redact(str(text))[:200]}", flush=True)


@router.get("/api/logverbose", dependencies=[Depends(auth)])
def verbose_state():
    now = time.time()
    return {"areas": {a: max(0, int(_verbose[a] - now)) if verbose(a) else 0 for a in VERBOSE},
            "minutes": VERBOSE_MINUTES}


@router.post("/api/logverbose", dependencies=[Depends(auth)])
async def verbose_set(request: Request):
    guard.limit(request, "logs", admin=True)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(400, "bad request")
    area, minutes = body.get("area"), body.get("minutes")
    if area not in VERBOSE or not isinstance(minutes, int) or isinstance(minutes, bool) \
            or (minutes and minutes not in VERBOSE_MINUTES):
        raise HTTPException(400, "bad area or minutes")
    if minutes:
        _verbose[area] = time.time() + minutes * 60
        print(f"logs: detail {area} on for {minutes} min", flush=True)
    elif _verbose.pop(area, None) is not None:
        print(f"logs: detail {area} off", flush=True)
    return verbose_state()
