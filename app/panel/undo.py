"""Rückgängig im Admin-Protokoll (plan „Bedienung gesamt“ C5, V01.0.286).

Every saved change of the settings (Einstellungen, Funktionen, the iPhone app's switches) keeps what each value was
before: the last 50 changes, newest first. "Rückgängig" puts the old values back, but only those still as that
change left them (a value changed again since stays), and through the same checks as saving (admin.validate,
service restarts). Never kept: secrets and addresses that need the admin's code (admin.SENSITIVE, names with key,
token, password ...), the panel section (ports, proxies: a wrong value could shut the admin out), lists and long
texts. Only the names of the values and short values are stored, so the file holds nothing secret.

    STATE/config-undo.json  [{"id", "t", "by", "changes": [{"k": "chat.weather", "old": false, "new": true}], "undone"}]
"""
import json
import os
import re
import secrets
import threading
import time

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "config-undo.json")
KEEP = 50
MAX_CHANGES = 40
MAX_TEXT = 300
SKIP_SECTIONS = {"panel", "api"}
SECRET = re.compile(r"(?i)(key|token|passw|secret|pin\b|code|cert|cookie|salt)")
ID = re.compile(r"[0-9a-f]{12}")
_lock = threading.Lock()


def _read():
    try:
        with open(FILE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    return [x for x in d if isinstance(x, dict) and ID.fullmatch(str(x.get("id")))] if isinstance(d, list) else []


def _write(items):
    os.makedirs(STATE, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
        json.dump(items[-KEEP:], f, ensure_ascii=False)
    os.replace(tmp, FILE)


def _plain(v):
    return isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= MAX_TEXT)


def keep(k, sensitive):
    sec, _, name = k.partition(".")
    return sec not in SKIP_SECTIONS and (sec, name) not in sensitive and not SECRET.search(name)


def diff(old, new, sensitive=()):
    """The values that changed and may be undone, as [{"k", "old", "new"}]."""
    sensitive = set(sensitive)
    out = []
    for sec, vals in new.items():
        if not isinstance(vals, dict):
            continue
        before = old.get(sec) if isinstance(old.get(sec), dict) else {}
        for name, v in vals.items():
            k = f"{sec}.{name}"
            o = before.get(name)
            if o != v and name in before and _plain(o) and _plain(v) and keep(k, sensitive):
                out.append({"k": k, "old": o, "new": v})
    return out[:MAX_CHANGES]


def record(old, new, by, sensitive=()):
    """Keeps one saved change (nothing when no value may be undone); returns its id or None."""
    changes = diff(old, new, sensitive)
    if not changes:
        return None
    item = {"id": secrets.token_hex(6), "t": int(time.time()), "by": str(by or "main")[:20], "changes": changes}
    with _lock:
        items = _read()
        items.append(item)
        _write(items)
    return item["id"]


def listing(by=None):
    """Newest first; with by only that admin's own changes."""
    return [x for x in reversed(_read()) if by is None or x.get("by") == by]


def get(uid):
    return next((x for x in _read() if x["id"] == uid), None)


def revert(item, cfg, sensitive=()):
    """cfg with the old values of item put back where the value is still the one item set; (cfg, done, kept)."""
    sensitive = set(sensitive)
    new = json.loads(json.dumps(cfg))
    done, kept = [], []
    for c in item.get("changes") or []:
        k = str(c.get("k", ""))
        sec, _, name = k.partition(".")
        if not keep(k, sensitive) or not isinstance(new.get(sec), dict) or name not in new[sec] or not _plain(c.get("old")):
            kept.append(k)
            continue
        if new[sec][name] != c.get("new"):
            kept.append(k)          # changed again since: that newer value stays
            continue
        new[sec][name] = c["old"]
        done.append(k)
    return new, done, kept


def mark_undone(uid, by):
    with _lock:
        items = _read()
        for x in items:
            if x["id"] == uid:
                x["undone"] = {"t": int(time.time()), "by": str(by or "main")[:20]}
        _write(items)
