"""Diagnose filters for Zustand → Logs: the journal lines threads usually ask for ("room:", "esp32:",
"chat: web search", ...), so nobody has to type journalctl | grep on the console.

Admin only. The filters are a fixed list and the matching runs in Python: nothing the browser sends
reaches a shell or journalctl except numbers from fixed lists. Time window, lines read and lines shown
are capped; secrets that might still slip into a line (bot tokens, keys, passwords, URL logins) are
blacked out before the text leaves the panel.
"""
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import guard
from common import JOURNAL_NAMESPACE
from core import auth

router = APIRouter()

# key -> regex on the message; "update" instead picks the update unit (update.sh and the self-tests)
FILTERS = {
    "chat": r"\bchat:",
    "search": r"\bchat: web search",
    "ha": r"\bhomeassistant:",
    "room": r"\broom:",
    "esp32": r"\besp32:",
    "update": None,
    "errors": r"(?i)\b(error|fehler|traceback|exception|failed|warn(ing)?)\b",
}
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


def pick(text, keys, lines):
    rx = [re.compile(FILTERS[k]) for k in keys if FILTERS[k]]
    hits = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("-- ")
            and (not rx or any(r.search(ln) for r in rx))]
    return [redact(ln[:2000]) for ln in hits[-lines:]], len(hits)


@router.get("/api/logfilter", dependencies=[Depends(auth)])
def logfilter(request: Request, f: str = "", minutes: int = 60, lines: int = 100):
    guard.limit(request, "logs", admin=True)
    keys = [k for k in f.split(",") if k][:len(FILTERS)]
    if any(k not in FILTERS for k in keys) or minutes not in MINUTES or lines not in LINES:
        raise HTTPException(400, "bad filter, time or lines")
    text = read_journal(minutes, UPDATE_UNIT if "update" in keys else None)
    shown, found = pick(text, keys, lines)
    names = ", ".join(keys) or "alles"
    head = f"# Filter: {names} · letzte {minutes} min · {len(shown)} von {found} Zeilen"
    return Response("\n".join([head] + shown) + "\n", media_type="text/plain")
