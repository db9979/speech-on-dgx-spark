"""Probleme melden (plan plaene/probleme-melden.md, V01.0.37x): a problem report from the panel, the phone apps,
Telegram, the voice and the speakers as an issue on GitHub, with anonymized log lines.

The way, always in this order:
  1. Entwurf   The panel builds a draft on the Spark (STATE/meldungen, 14 days): the person's text, a fixed area, the
               time window, and what they ticked. Everything goes through `anon` BEFORE it is stored: the Spark never
               keeps the raw lines of a report, only what could go out.
  2. Vorschau  Exactly the text that would go out, with the replacements marked ([PERSON-1], [MAIL], [IP-LAN] …) and
               counted. Log lines can still be dropped. The answer carries a signature over exactly that text.
  3. Senden    Only with the signature of the preview the person saw (a changed text needs a new preview), and only
               when the final leak check finds nothing it knows (secrets, profile and device names, mail addresses,
               own host names). Telegram, the voice, the watch and the speakers only make drafts.

What goes out is built by fixed rules here, never by the language model, and only to api.github.com, only to the one
repository the admin set (default db9979/spark-meldungen, private), with a fine-grained token that the main admin
enters with a fresh code; it lives sealed in the vault (STATE/meldung-token.json) and is never shown or logged.
Without a token "Im Browser öffnen" fills GitHub's "new issue" page instead (the person is signed in there itself).

Who: the admin switch chat.report and the profile's own switch report_on (both off), guests never. The main admin
and admin profiles (not the Verwalter role) may add Diagnose lines (journal of the whole Spark, anonymized); a
profile only gets its own requests (Logs → Anfragen, fixed words and numbers), the system state and its app's log.
Limits: text 2000 characters, 200 lines / 32 KB per report, 10 drafts and 3 sent per profile and day, 10 sent per
day on the whole Spark, one send per minute, 20 open drafts per profile, 200 in all.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
import vault
from common import load_config, write_json
import core
from core import admin_code_fresh, assistant, auth

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
DIR = os.path.join(STATE, "meldungen")
TOKEN_FILE = os.path.join(STATE, "meldung-token.json")
API = "https://api.github.com"
DEFAULT_REPO = "db9979/spark-meldungen"
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")
# only fine-grained tokens: they can be bound to one repository and to "Issues" alone (a classic ghp_ token cannot)
TOKEN = re.compile(r"github_pat_[A-Za-z0-9_]{20,255}")
ID = re.compile(r"[0-9a-f]{10}")
KEEP_S = 14 * 86400
MAX_TEXT, MAX_LINES, MAX_BYTES, MAX_APPLOG = 2000, 200, 32 * 1024, 32 * 1024
MAX_BODY = 48 * 1024
MAX_OPEN_UID, MAX_OPEN_ALL = 20, 200
DAY_DRAFTS_UID, DAY_SENT_UID, DAY_SENT_ALL, GAP_S = 10, 3, 10, 60
MINUTES = (10, 30, 60)
LINE_MAX = 300
# the areas a report can be about: key -> (German, English, Diagnose areas of logfilter.AREAS)
AREAS = {"sprache": ("Sprache und Hören", "Speech and listening", ("chat", "room", "esp32", "watch")),
         "antwort": ("Antworten und Werkzeuge", "Answers and tools", ("chat", "weiche", "anfrage", "search", "wissen", "vorrang")),
         "zuhause": ("Smart Home", "Smart home", ("ha", "room")),
         "post": ("Mail, Kalender, Kontakte", "Mail, calendar, contacts", ("mail", "chat")),
         "geraete": ("Geräte und Lautsprecher", "Devices and speakers", ("esp32", "watch", "telegram", "room")),
         "app": ("App (iPhone, Android, Begleiter)", "App (iPhone, Android, companion)", ("chat", "anfrage")),
         "update": ("Update und Betrieb", "Update and operation", ("update",)),
         "sonstiges": ("Sonstiges", "Other", ())}
CHANNELS = ("panel", "app", "android", "telegram", "sprache", "esp32", "pebble", "begleiter")
STATUS = ("entwurf", "gesendet", "lokal")
_lock = threading.Lock()
_key = secrets.token_bytes(32)        # signs previews; a restart only means "look at the preview again"
_last = {"t": 0.0, "status": "", "n_day": "", "sent": {}}   # for Live: the last outcome in fixed words
_check = {"t": 0, "ok": None, "why": "", "until": None}


# ---------------------------------------------------------------- switches and who
def admin_on():
    return features.admin_on("melden")


def repo():
    r = str(features.chat_cfg().get("report_repo") or DEFAULT_REPO)
    return r if REPO.fullmatch(r) else DEFAULT_REPO


def _staff(request):
    """(name, uid, logs) for the main admin or a profile with the admin role; logs: may add Diagnose
    lines. The Verwalter role is no staff here (Prüfung 2026-10-14, B): it reports like any profile and never sees,
    sends or deletes another profile's draft. None otherwise."""
    import coadmin
    import core
    if request.headers.get(profiles.DEVICE_HEADER) or request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
        return None
    if core.password_set() and core._admin_cookie_age(request) is not None:
        return "Admin", "", True
    elev = coadmin.session(request)
    if elev and elev.get("role") != "manager":
        return elev["name"], elev["id"], True
    return None


def caller(request):
    """{"uid", "name", "channel", "logs", "staff"} of who may report from this request, else an HTTPException.
    Logins in the browser (also the Android app's page) and the iPhone app's key; nothing else."""
    if request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
        raise HTTPException(403, "not from here")
    if not admin_on():
        raise HTTPException(404, "Probleme melden ist ausgeschaltet.")
    dev = profiles.device(request) if request.headers.get(profiles.DEVICE_HEADER) else None
    if dev is not None and dev["scope"] != "app":
        raise HTTPException(403, "not with this key")
    st = None if dev else _staff(request)
    if st:
        return {"uid": st[1], "name": st[0], "channel": _channel(request, dev), "logs": st[2], "staff": True}
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "login required")
    if not features.allowed("melden", prof["id"]):
        raise HTTPException(403, "Probleme melden geht für dich gerade nicht. " + features.missing_text("melden", prof["id"]))
    return {"uid": prof["id"], "name": prof["name"], "channel": _channel(request, dev), "logs": False, "staff": False}


def _channel(request, dev):
    if dev:
        return "app"
    import android
    return "android" if android.from_app(request) else "panel"


# ---------------------------------------------------------------- what the Spark knows about itself (for anon)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
_URL = re.compile(r"(?i)\b(?:https?|wss?|ftp|webcal|imaps?|caldavs?|carddavs?)://[^\s\"'<>)\]]+")
_IPV4 = re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")
_IPV6 = re.compile(r"(?<![0-9A-Za-z:.])(?=[0-9A-Fa-f:]*:[0-9A-Fa-f]*:)[0-9A-Fa-f:]{3,39}(?:%\w+)?(?![0-9A-Za-z:])")
_MAC = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
_PHONE = re.compile(r"(?<![\w+])(?:\+|00)\d{1,3}[ /-]?\(?\d{1,5}\)?(?:[ /-]?\d{2,}){2,}|(?<![\w/.-])0\d{2,5}[ /-]\d{3,}(?:[ -]\d{2,})*")
_COORD = re.compile(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}")
_LONG = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{32,}(?![A-Za-z0-9])")
_TLDS = ("de", "com", "net", "org", "me", "io", "info", "eu", "local", "lan", "home", "box", "arpa", "app", "dev",
         "cloud", "ch", "at", "uk", "nl", "fr", "it", "es", "be", "dk", "se", "no", "pl", "cz", "us", "ai", "co",
         "tv", "biz", "online", "site", "xyz", "internal", "localdomain", "fritz", "intern")
_HOST = re.compile(r"(?i)(?<![\w.@-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + "|".join(_TLDS) + r")(?![\w-])")
# a quotation in a log line is somebody's words (a question, a subject, a title, a search): never out
_QUOTED = re.compile(r"\"[^\"\n]{1,400}\"|„[^“\n]{1,400}“|“[^”\n]{1,400}”|«[^»\n]{1,400}»|'[^'\n]{2,400}'")
# what follows these words in a log line is content too
_CONTENT = re.compile(r"(?i)\b(detail|betreff|subject|titel|title|frage|question|text|query|suche|search for|termin|"
                      r"datei|file|name|von|from|an|to|für|for)\b(\s*[:=]\s*)(\S.*)$")
# placeholders: what the leak check must leave alone
_HOLDER = re.compile(r"\[(?:PERSON|GERÄT|KONTO)-\d+\]|\[(?:MAIL|URL|HOST|IP|IP-LAN|MAC|TELEFON|ORT|GEHEIM|INHALT|ID)\]")


def _strings(x, out, depth=0):
    """Every string in a JSON value (with its key), at most 4000, 6 levels deep."""
    if depth > 6 or len(out) > 4000:
        return
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(v, str):
                out.append((str(k), v))
            else:
                _strings(v, out, depth + 1)
    elif isinstance(x, list):
        for v in x[:500]:
            if isinstance(v, str):
                out.append(("", v))
            else:
                _strings(v, out, depth + 1)


_ACCOUNT_KEYS = re.compile(r"(?i)^(user|username|login|account|benutzer|konto|email|mail|address|from|sender)$")


def known():
    """What the Spark knows that must never go out: names of profiles and devices, account names, mail addresses,
    own host names and the plain secrets (opened from the vault). Read anew for each report (a few small files)."""
    names, devices, accounts, hosts, mails, secs = set(), set(), set(), set(), set(), set()
    d = profiles._load()
    for u in d.get("users", []):
        n = str(u.get("name") or "").strip()
        if 2 <= len(n) <= 60:
            names.add(n)
    for x in d.get("devices", []):
        n = str(x.get("name") or "").strip()
        if 3 <= len(n) <= 80:
            devices.add(n)
    found = []
    try:
        _strings(load_config(), found)
    except Exception:
        pass
    users = profiles.USERS_DIR
    try:
        for uid in sorted(os.listdir(users))[:300]:
            p = os.path.join(users, uid)
            if not os.path.isdir(p) or os.path.islink(p):
                continue
            for fn in sorted(os.listdir(p))[:60]:
                f = os.path.join(p, fn)
                if not fn.endswith(".json") or os.path.islink(f) or not os.path.isfile(f) or os.path.getsize(f) > 512 * 1024:
                    continue
                try:
                    with open(f) as fh:
                        _strings(json.load(fh), found)
                except (OSError, ValueError):
                    continue
    except OSError:
        pass
    for k, v in found:
        if not v or len(v) > 2000:
            continue
        if v.startswith(vault.PREFIX):
            plain = vault.open_(v)
            if plain and len(plain) >= 6:
                secs.add(plain)
            continue
        for m in _EMAIL.findall(v):
            mails.add(m.lower())
        for m in _URL.findall(v):
            h = re.sub(r"(?i)^[a-z]+://(?:[^@/]*@)?", "", m).split("/")[0].split(":")[0].strip("[]").lower()
            if h and not _is_ip(h) and "." in h and h not in ("api.github.com", "github.com"):
                hosts.add(h)
        if _ACCOUNT_KEYS.fullmatch(k) and 3 <= len(v) <= 80 and not v.startswith("http"):
            accounts.add(v.strip())
        if re.fullmatch(r"(?i)(llm_key|key|token|password|secret|api_key|pin)", k) and len(v) >= 8:
            secs.add(v)
    for env in ("PANEL_PASSWORD",):
        if len(os.environ.get(env, "")) >= 6:
            secs.add(os.environ[env])
    t = _token()
    if t:
        secs.add(t)
    accounts -= mails
    return {"names": sorted(names, key=len, reverse=True), "devices": sorted(devices, key=len, reverse=True),
            "accounts": sorted(accounts, key=len, reverse=True), "hosts": sorted(hosts, key=len, reverse=True),
            "mails": sorted(mails), "secrets": sorted(secs, key=len, reverse=True)}


def _is_ip(s):
    try:
        ipaddress.ip_address(s.split("%")[0])
        return True
    except ValueError:
        return False


class Anon:
    """Replaces with fixed rules and counts what it replaced. One per report, so the same name keeps its number."""

    def __init__(self, k):
        self.k = k
        self.n = {}
        self.map = {}
        self.word = {}
        for kind, items in (("PERSON", k["names"]), ("GERÄT", k["devices"]), ("KONTO", k["accounts"])):
            for x in items:
                self.word.setdefault(x.lower(), kind)
        self._names = None
        if self.word:
            alts = sorted(self.word, key=len, reverse=True)[:2000]
            self._names = re.compile(r"(?i)(?<![\w@.-])(" + "|".join(re.escape(a) for a in alts) + r")(?![\w-])")

    def _count(self, what):
        self.n[what] = self.n.get(what, 0) + 1

    def _holder(self, kind, value):
        key = (kind, value.lower())
        if key not in self.map:
            self.map[key] = f"[{kind}-{sum(1 for x in self.map if x[0] == kind) + 1}]"
        self._count(kind)
        return self.map[key]

    def text(self, s, log=False):
        """One piece of text. log=True: a log line, where quotations and what follows content words go too."""
        import logfilter
        s = str(s or "").replace("\r", " ").replace("\t", " ")
        s = logfilter.redact(s)
        for sec in self.k["secrets"]:
            if sec in s:
                s = s.replace(sec, "[GEHEIM]")
                self._count("GEHEIM")
        if log:
            s, c = _QUOTED.subn("[INHALT]", s)
            if c:
                self.n["INHALT"] = self.n.get("INHALT", 0) + c
            m = _CONTENT.search(s)
            if m and not _HOLDER.fullmatch(m.group(3).strip()):
                s = s[:m.start(3)] + "[INHALT]"
                self._count("INHALT")
        s = self._sub(_URL, s, "URL")
        s = self._sub(_EMAIL, s, "MAIL")
        s = _MAC.sub(lambda m: self._c("MAC"), s)
        s = _IPV4.sub(self._ip, s)
        s = _IPV6.sub(lambda m: self._c("IP") if (":" in m.group(0) and (re.search(r"[a-fA-F]", m.group(0)) or "::" in m.group(0))) else m.group(0), s)
        s = self._sub(_COORD, s, "ORT")
        for h in self.k["hosts"]:
            if h and h in s.lower():
                s = re.sub(re.escape(h), "[HOST]", s, flags=re.I)
                self._count("HOST")
        s = _HOST.sub(lambda m: self._c("HOST"), s)
        s = self._sub(_PHONE, s, "TELEFON")
        s = _LONG.sub(lambda m: m.group(0) if _HOLDER.fullmatch(m.group(0)) else self._c("ID"), s)
        if self._names:
            s = self._names.sub(lambda m: self._holder(self.word[m.group(1).lower()], m.group(1)), s)
        return s.replace("```", "'''").replace("@", "@​")

    def _c(self, what):
        self._count(what)
        return f"[{what}]"

    def _sub(self, rx, s, what):
        return rx.sub(lambda m: self._c(what), s)

    def _ip(self, m):
        try:
            a = ipaddress.ip_address(m.group(0))
        except ValueError:
            return m.group(0)
        return self._c("IP-LAN" if a.is_private or a.is_loopback or a.is_link_local else "IP")


def leaks(text, k=None):
    """What the final check finds in a text that must not go out (fixed words naming the kind, never the value)."""
    k = known() if k is None else k
    out = []
    low = text.lower()
    rest = _HOLDER.sub(" ", text)
    if any(s and s in text for s in k["secrets"]):
        out.append("Geheimnis")
    for kind, items in (("Name", k["names"]), ("Gerätename", k["devices"]), ("Konto", k["accounts"])):
        if any(re.search(r"(?i)(?<![\w@.-])" + re.escape(x) + r"(?![\w-])", rest.replace("@​", "@")) for x in items if x):
            out.append(kind)
    if any(m in low for m in k["mails"]) or _EMAIL.search(rest.replace("@​", "@")):
        out.append("Mail-Adresse")
    if any(h in low for h in k["hosts"]):
        out.append("eigene Adresse")
    if _IPV4.search(rest) or _URL.search(rest):
        out.append("Adresse")
    return out


# ---------------------------------------------------------------- what a report can carry
def _journal(minutes):
    """Parsed journal lines of the last minutes (logfilter; empty where there is no journal)."""
    import logfilter
    try:
        out = logfilter.read_journal(int(minutes))
    except Exception:
        return []
    return [logfilter.parse(ln) for ln in out.splitlines() if ln.strip() and not ln.startswith("-- ")]


def diagnose(area, minutes, now=None):
    """Diagnose lines for the area, newest last: errors and warnings of the window and the area's lines."""
    keys = set(AREAS.get(area, AREAS["sonstiges"])[2])
    rows = [r for r in _journal(minutes) if r.get("level") in ("err", "warn") or (keys and r.get("area") in keys)
            or ("update" in keys and "update" in str(r.get("raw", "")[:80]).lower())]
    return [f"{r.get('t') or ''} {r.get('msg') or ''}".strip() for r in rows][-MAX_LINES:]


def traces(uid, staff, minutes, now=None, tid=None):
    """Logs → Anfragen as journal-style lines (tracelog.line: fixed words and numbers, never a name). A profile
    gets its own requests only; the main admin and admin profiles every request (or one by its id)."""
    import tracelog
    now = time.time() if now is None else now
    rows = [x for x in tracelog.all_traces(now) if x["t"] >= now - minutes * 60]
    if tid:
        rows = [x for x in tracelog.all_traces(now) if x["id"] == tid]
    if not staff:
        rows = [x for x in rows if x.get("kind") == "profile" and x.get("who") == uid]
    return [time.strftime("%H:%M:%S", time.localtime(x["t"])) + " " + tracelog.line(x) for x in rows][-60:]


def system():
    """Version, services and a few numbers (no names, no addresses)."""
    import core
    out = [f"Version: {core.app_version() or '?'}"]
    try:
        for k in ("asr", "tts", "asr-engine", "tts-engine"):
            out.append(f"Dienst {k}: {core.unit_state(core.UNITS[k])}")
    except Exception:
        pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        out.append(f"Speicher frei: {vm.available / 1024**3:.1f} GiB von {vm.total / 1024**3:.0f} GiB")
        du = psutil.disk_usage(STATE if os.path.isdir(STATE) else "/")
        out.append(f"Platte frei: {du.free / 1024**3:.0f} GiB")
        out.append(f"Läuft seit: {int((time.time() - psutil.boot_time()) / 3600)} h")
    except Exception:
        pass
    try:
        import notaus
        out.append(f"Notaus: Stufe {notaus.level()}")
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- drafts
def _path(rid):
    return os.path.join(DIR, rid + ".json")


def _read(rid):
    if not ID.fullmatch(str(rid or "")):
        return None
    try:
        with open(_path(rid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("id") == rid else None
    except (OSError, ValueError):
        return None


def _write(d):
    write_json(_path(d["id"]), d, mode=0o600, ensure_ascii=False, dir_mode=0o700)


def _all(now=None):
    """Every stored report, old ones (KEEP_S) removed on the way."""
    now = time.time() if now is None else now
    out = []
    try:
        names = sorted(os.listdir(DIR))
    except OSError:
        return []
    for fn in names[:2 * MAX_OPEN_ALL]:
        rid = fn[:-5] if fn.endswith(".json") else ""
        d = _read(rid)
        if not d:
            continue
        if now - float(d.get("t") or 0) > KEEP_S:
            try:
                os.remove(_path(rid))
            except OSError:
                pass
            continue
        out.append(d)
    return sorted(out, key=lambda d: d.get("t", 0), reverse=True)


def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _clip(lines, limit=MAX_LINES):
    out, size = [], 0
    for ln in lines[-limit:]:
        ln = str(ln)[:LINE_MAX]
        size += len(ln.encode()) + 1
        if size > MAX_BYTES:
            break
        out.append(ln)
    return out


def clean_text(s, n=MAX_TEXT):
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(s or ""))
    return s.strip()[:n]


def create(uid, name, channel, text, area="sonstiges", minutes=30, logs=False, reqs=True, sysinfo=True, applog="",
           staff=False, may_logs=False, tid=None, now=None):
    """A new draft, already anonymized. Returns it (as `view` shows it). Raises HTTPException on limits."""
    now = time.time() if now is None else now
    text = clean_text(text)
    if len(text) < 3:
        raise HTTPException(400, "Bitte kurz beschreiben, was passiert ist.")
    if area not in AREAS:
        area = "sonstiges"
    if minutes not in MINUTES:
        minutes = 30
    if channel not in CHANNELS:
        channel = "panel"
    with _lock:
        mine = [d for d in _all(now) if d.get("uid") == uid]
        if len([d for d in mine if d.get("status") == "entwurf"]) >= MAX_OPEN_UID or len(_all(now)) >= MAX_OPEN_ALL:
            raise HTTPException(429, "Zu viele offene Entwürfe. Bitte erst alte senden oder löschen.")
        if len([d for d in mine if _day(d.get("t", 0)) == _day(now)]) >= DAY_DRAFTS_UID:
            raise HTTPException(429, f"Heute höchstens {DAY_DRAFTS_UID} Entwürfe.")
    k = known()
    a = Anon(k)
    parts = {"text": a.text(text)}
    parts["system"] = [a.text(x, log=True) for x in system()] if sysinfo else []
    parts["requests"] = _clip([a.text(x, log=True) for x in traces(uid, staff, minutes, now, tid if staff else None)]) if reqs else []
    parts["lines"] = _clip([a.text(x, log=True) for x in diagnose(area, minutes, now)]) if logs and may_logs else []
    app = [x for x in str(applog or "")[:MAX_APPLOG].splitlines() if x.strip()]
    parts["applog"] = _clip([a.text(x, log=True) for x in app]) if app else []
    d = {"id": secrets.token_hex(5), "t": round(now, 1), "uid": uid or "", "channel": channel, "area": area,
         "minutes": minutes, "status": "entwurf", "parts": parts, "counts": dict(a.n), "issue": None}
    with _lock:
        _write(d)
    _live_mark("Entwurf angelegt", channel)
    print(f"meldung: Entwurf {d['id']} | {channel} | {area} | {len(parts['lines'])} Logzeilen | "
          f"{len(parts['requests'])} Anfragen | {sum(a.n.values())} ersetzt", flush=True)
    return d


def title(d):
    first = re.sub(r"\s+", " ", d["parts"]["text"]).strip()
    first = first[:70] + ("…" if len(first) > 70 else "")
    return f"[{AREAS[d['area']][0]}] {first}"[:110]


SECTIONS = (("requests", "Anfragen (Logs → Anfragen)"), ("lines", "Logzeilen (Diagnose)"), ("applog", "App-Protokoll"),
            ("system", "System"))


def numbered(d):
    """[(n, section, line)] for every line that can be dropped, numbered from 1 over all sections."""
    out, n = [], 0
    for key, _ in SECTIONS:
        for ln in d["parts"].get(key) or []:
            n += 1
            out.append((n, key, ln))
    return out


def body(d, skip=()):
    import core
    skip = set(skip)
    p = d["parts"]
    head = (f"**Bereich:** {AREAS[d['area']][0]} · **Version:** {core.app_version() or '?'} · **Weg:** {d['channel']} · "
            f"**Zeitraum:** {d['minutes']} min · **Entwurf:** {d['id']}")
    out = [head, "", "### Beschreibung", "", p["text"]]
    rows = numbered(d)
    for key, label in SECTIONS:
        keep = [ln for n, k, ln in rows if k == key and n not in skip]
        if keep:
            out += ["", f"### {label} ({len(keep)})", "", "```text"] + keep + ["```"]
    c = d.get("counts") or {}
    said = ", ".join(f"{v}× {k}" for k, v in sorted(c.items())) or "nichts"
    out += ["", f"_Anonymisiert vom Spark mit festen Regeln (ersetzt: {said}); vor dem Senden geprüft und angesehen._"]
    return "\n".join(out)[:MAX_BODY]


def _sign(rid, text):
    return hmac.new(_key, (rid + "\n" + hashlib.sha256(text.encode()).hexdigest()).encode(), hashlib.sha256).hexdigest()[:32]


def preview(d, skip=()):
    t, b = title(d), body(d, skip)
    found = leaks(t + "\n" + b)
    return {"title": t, "body": b, "leaks": found, "sig": _sign(d["id"], t + "\n" + b) if not found else ""}


def view(d, me=None, names=None):
    out = {k: d.get(k) for k in ("id", "t", "channel", "area", "minutes", "status", "counts", "issue")}
    out["text"] = d["parts"]["text"]
    out["lines"] = [{"n": n, "part": k, "line": ln} for n, k, ln in numbered(d)]
    out["mine"] = me is not None and d.get("uid") == me
    if names is not None:
        out["by"] = names.get(d.get("uid"), "Admin" if not d.get("uid") else "?")
    return out


def _skip(raw):
    if not isinstance(raw, list) or len(raw) > MAX_LINES * 4:
        raise HTTPException(400, "skip: list of numbers")
    out = []
    for x in raw:
        if not isinstance(x, int) or isinstance(x, bool) or not 1 <= x <= MAX_LINES * 4:
            raise HTTPException(400, "skip: list of numbers")
        out.append(x)
    return out


# ---------------------------------------------------------------- the token
def _token():
    try:
        with open(TOKEN_FILE) as f:
            d = json.load(f)
        t = vault.open_(d.get("token", "")) if isinstance(d, dict) else ""
        return t if isinstance(t, str) and TOKEN.fullmatch(t) else ""
    except (OSError, ValueError):
        return ""


def token_info():
    try:
        with open(TOKEN_FILE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {"set": bool(_token()), "since": d.get("since"), "until": _check.get("until") or d.get("until"),
            "checked": _check.get("t") or None, "ok": _check.get("ok"), "why": _check.get("why") or ""}


def token_save(token, now=None):
    if not vault.available():
        raise HTTPException(503, "Verschlüsselung fehlt (python3-cryptography).")
    d = {"token": vault.seal(token), "since": int(time.time() if now is None else now), "until": None}
    write_json(TOKEN_FILE, d, mode=0o600)
    _check.update(t=0, ok=None, why="", until=None)


def token_drop():
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass
    _check.update(t=0, ok=None, why="", until=None)


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "speech-on-dgx-spark"}


def _until(r):
    """GitHub names a fine-grained token's end in a header ("2026-12-31 00:00:00 UTC"); only the date is kept."""
    v = r.headers.get("github-authentication-token-expiration", "")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    return m.group(1) if m else None


async def _client():
    import netguard
    return netguard.client(netguard.PUBLIC, origin=API, max_bytes=256 * 1024, timeout=20)


async def check_token():
    """Asks GitHub whether the token reaches the repository (GET /repos/…). Fixed words only."""
    token = _token()
    if not token:
        _check.update(t=int(time.time()), ok=False, why="kein Token", until=None)
        return token_info()
    try:
        async with await _client() as c:
            r = await c.get(f"{API}/repos/{repo()}", headers=_headers(token))
        ok = r.status_code == 200
        why = "" if ok else {401: "Token abgelehnt oder abgelaufen", 403: "keine Rechte", 404: "Repo nicht erreichbar"}.get(
            r.status_code, f"GitHub antwortet {r.status_code}")
        if ok and isinstance(r.json(), dict) and r.json().get("private") is False:
            why = "Achtung: das Repo ist öffentlich"
        _check.update(t=int(time.time()), ok=ok, why=why, until=_until(r))
    except Exception as e:
        _check.update(t=int(time.time()), ok=False, why="GitHub nicht erreichbar", until=_check.get("until"))
        print("meldung: Token-Prüfung", type(e).__name__, flush=True)
    return token_info()


async def send(d, t, b):
    """POST /repos/{repo}/issues. Returns (number, url). Labels only as a wish: without them it goes out anyway."""
    token = _token()
    if not token:
        raise HTTPException(409, "Kein GitHub-Token eingetragen. Nimm „Im Browser öffnen“ oder frag den Admin.")
    payload = {"title": t, "body": b, "labels": ["von-spark", "bereich:" + d["area"]]}
    try:
        async with await _client() as c:
            r = await c.post(f"{API}/repos/{repo()}/issues", headers=_headers(token), json=payload)
            if r.status_code in (403, 422) and "label" in r.text.lower():
                payload.pop("labels")
                r = await c.post(f"{API}/repos/{repo()}/issues", headers=_headers(token), json=payload)
    except Exception as e:
        print("meldung: senden", type(e).__name__, flush=True)
        raise HTTPException(502, "GitHub nicht erreichbar. Der Entwurf bleibt; später noch einmal.")
    if r.status_code != 201:
        why = {401: "Token abgelehnt oder abgelaufen", 403: "Token hat keine Rechte für Issues", 404: "Repo nicht erreichbar",
               410: "Issues sind im Repo ausgeschaltet"}.get(r.status_code, f"GitHub antwortet {r.status_code}")
        _check.update(t=int(time.time()), ok=False, why=why)
        raise HTTPException(502, why + ". Der Entwurf bleibt.")
    j = r.json() if isinstance(r.json(), dict) else {}
    num = j.get("number") if isinstance(j.get("number"), int) else None
    url = j.get("html_url") if isinstance(j.get("html_url"), str) and j["html_url"].startswith("https://github.com/") else ""
    _check.update(t=int(time.time()), ok=True, why="", until=_until(r) or _check.get("until"))
    return num, url


_states = {"t": 0.0, "repo": "", "items": {}}     # issue number -> {"state", "comments", "closed"} (60 s)
MAX_COMMENTS, MAX_COMMENT = 30, 4000


async def issue_states(now=None):
    """State and number of answers of the issues the Spark sent (one request for the newest 100, kept 60 s).
    GitHub's words become fixed words here; {} without a token or when GitHub does not answer."""
    now = time.time() if now is None else now
    token = _token()
    if not token:
        return {}
    if now - _states["t"] < 60 and _states["repo"] == repo():
        return _states["items"]
    items = {}
    try:
        async with await _client() as c:
            r = await c.get(f"{API}/repos/{repo()}/issues", headers=_headers(token),
                            params={"state": "all", "per_page": 100, "sort": "created", "direction": "desc"})
        if r.status_code == 200 and isinstance(r.json(), list):
            for x in r.json()[:100]:
                if isinstance(x, dict) and isinstance(x.get("number"), int) and "pull_request" not in x:
                    items[x["number"]] = {"state": "erledigt" if x.get("state") == "closed" else "offen",
                                          "comments": x["comments"] if isinstance(x.get("comments"), int) else 0}
    except Exception as e:
        print("meldung: Stand holen", type(e).__name__, flush=True)
        return _states["items"] if _states["repo"] == repo() else {}
    _states.update(t=now, repo=repo(), items=items)
    return items


async def issue_thread(num):
    """The answers on one issue: author, time and text (GitHub's text, shown as text only; it never reaches the
    language model and switches nothing). At most 30 answers of 4000 characters."""
    token = _token()
    if not token:
        raise HTTPException(409, "Kein GitHub-Token eingetragen.")
    try:
        async with await _client() as c:
            r = await c.get(f"{API}/repos/{repo()}/issues/{int(num)}", headers=_headers(token))
            rc = await c.get(f"{API}/repos/{repo()}/issues/{int(num)}/comments", headers=_headers(token),
                             params={"per_page": MAX_COMMENTS})
    except Exception as e:
        print("meldung: Antworten holen", type(e).__name__, flush=True)
        raise HTTPException(502, "GitHub nicht erreichbar.")
    if r.status_code != 200 or rc.status_code != 200:
        raise HTTPException(502, f"GitHub antwortet {r.status_code if r.status_code != 200 else rc.status_code}.")
    j = r.json() if isinstance(r.json(), dict) else {}
    out = []
    for x in (rc.json() if isinstance(rc.json(), list) else [])[:MAX_COMMENTS]:
        if not isinstance(x, dict):
            continue
        who = ((x.get("user") or {}).get("login") if isinstance(x.get("user"), dict) else "") or "?"
        out.append({"by": str(who)[:40], "t": str(x.get("created_at") or "")[:20],
                    "text": clean_text(x.get("body") or "", MAX_COMMENT)})
    return {"state": "erledigt" if j.get("state") == "closed" else "offen", "answers": out}


def browser_link(t, b):
    """GitHub's "new issue" page, filled in (the person signs in there itself). Long bodies are cut."""
    base = f"https://github.com/{repo()}/issues/new?title={quote(t)}&body="
    room = 7000 - len(base)
    q = quote(b)
    if len(q) > room:
        cut = b
        while len(quote(cut)) > room - 200 and len(cut) > 200:
            cut = cut[: int(len(cut) * 0.8)]
        q = quote(cut + "\n\n_(gekürzt; der ganze Text steht im Entwurf auf dem Spark)_")
    return base + q


# ---------------------------------------------------------------- Live, limits, notes
def _live_mark(text, channel=""):
    _last.update(t=time.time(), status=text)
    try:
        import live
        live.mark("Meldung", f"{text}" + (f" ({channel})" if channel else ""))
    except Exception:
        pass


def for_live(now=None):
    """For Zustand → Live and the monitor: counts and the last outcome in fixed words, never text or titles."""
    now = time.time() if now is None else now
    try:
        items = _all(now)
    except Exception:
        items = []
    day = _day(now)
    return {"on": admin_on(), "drafts": sum(1 for d in items if d.get("status") == "entwurf"),
            "sent_today": sum(1 for d in items if d.get("status") == "gesendet" and _day((d.get("issue") or {}).get("t", 0)) == day),
            "last": _last.get("status") or "", "token": bool(_token()), "until": token_info().get("until")}


def live_hint(now=None):
    """A warning at "GitHub (Meldungen)" on Live: the token was refused, or ends within 14 days (fixed words)."""
    if not admin_on() or not _token():
        return ""
    now = time.time() if now is None else now
    if _check.get("ok") is False and _check.get("why"):
        return "Meldungen: " + _check["why"]
    until = token_info().get("until")
    if until:
        try:
            left = (time.mktime(time.strptime(until, "%Y-%m-%d")) - now) / 86400
        except ValueError:
            return ""
        if left < 14:
            return f"Meldungen: Token endet in {max(0, int(left))} Tagen"
    return ""


def _sent_count(items, uid, now):
    day = _day(now)
    sent = [d for d in items if d.get("status") == "gesendet" and _day((d.get("issue") or {}).get("t", 0)) == day]
    last = max([(d.get("issue") or {}).get("t", 0) for d in items if d.get("status") == "gesendet"] or [0])
    return len([d for d in sent if d.get("uid") == uid]), len(sent), last


async def note_ready(uid, channel):
    """A draft from Telegram, the voice, the watch or a speaker: the profile hears where to look at it."""
    if not uid:
        return
    try:
        import push
        await push.send(uid, "Problem-Entwurf liegt bereit",
                        "Ansehen und senden: Ich → Probleme melden (Panel oder App). Erst nach deinem Blick geht etwas raus.",
                        tag="meldung", private=False)
    except Exception as e:
        print("meldung: push", type(e).__name__, flush=True)


CHANNEL_NAMES = {"panel": "das Panel", "app": "die iPhone-App", "android": "die Android-App", "telegram": "Telegram",
                 "sprache": "Sprache", "esp32": "einen Lautsprecher", "pebble": "die Uhr", "begleiter": "den Begleiter"}


def notify_targets(skip=""):
    """The admin profiles that hear of a new report: every profile with the role Admin, the main one first
    (notaus.admin_uids), without the reporter, without those that turned it off for themselves (report_notify),
    and none when the admin switch chat.report_notify is off."""
    c = features.chat_cfg()
    if not c.get("report_notify", False):
        return []
    import notaus
    return [u for u in notaus.admin_uids() if u and u != skip and profiles.settings(u).get("report_notify", True) is not False
            and not features.blocked("meldenadmin", u, c)]


def _may_notify(uid):
    """The profile is one that would hear of new reports (its own switch report_notify shows on its page)."""
    if not uid or not features.chat_cfg().get("report_notify", False):
        return False
    import notaus
    return uid in notaus.admin_uids()


async def tell_admins(d):
    """A report was sent or kept on the Spark: the admin profiles hear it from the assistant (open page, else a
    note to their device), in fixed words with the reporter's profile name, area and way; never the text."""
    if not d.get("uid"):
        return 0                       # the main admin without a profile made it: nobody else to tell
    who = _names().get(d["uid"], "ein Profil")
    num = (d.get("issue") or {}).get("number")
    where = f"auf GitHub als Nummer {num}" if isinstance(num, int) else "nur auf dem Spark abgelegt"
    text = (f"Neue Problem-Meldung von {who}: {AREAS.get(d.get('area'), AREAS['sonstiges'])[0]}, über "
            f"{CHANNEL_NAMES.get(d.get('channel'), 'das Panel')}, {where}. Ansehen: Problem melden unten im Panel.")
    import notaus
    import proactive
    n = 0
    for uid in notify_targets(d["uid"]):
        if notaus.refuse("auto", uid):
            continue
        try:
            if await proactive.deliver(uid, "meldung", text, why="Neue Problem-Meldung", force=True):
                n += 1
        except Exception as e:
            print("meldung: admin note", type(e).__name__, flush=True)
    if n:
        _live_mark(f"Admin informiert ({n})", d.get("channel", "panel"))
    return n


# ---------------------------------------------------------------- other channels (Telegram, voice, watch, speakers)
# A fixed sentence the profile says or types itself, the whole utterance: "Spark, Problem melden: …",
# "Spark, melde ein Problem: …", "Spark, Fehler melden: …". What follows is the description. Never from text
# the model wrote or read, never over MCP, never for a voice the speaker did not recognise.
_PHRASE = re.compile(r"(?is)^\s*(?:hey |hallo |ok )?spark[\s,!.:]+(?:melde (?:ein(?:en)? )?(?:problem|fehler)|"
                     r"(?:ein(?:en)? )?(?:problem|fehler) melden)\s*[:,.!-]?\s*(.{3,1500})$")


def phrase(text):
    """The description when the text is the fixed sentence, else None."""
    m = _PHRASE.match(str(text or "")[:1600])
    return clean_text(m.group(1)) if m else None


def phrase_channel(client):
    return {"telegram": "telegram", "speaker": "esp32", "watch": "pebble", "app": "app", "car": "app", "siri": "app",
            "android": "android", "desk": "begleiter"}.get(str(client or ""), "sprache")


async def by_phrase(uid, name, text, channel="sprache"):
    """Makes a draft from the fixed sentence; returns the sentence the assistant says (German)."""
    if not admin_on():
        return "Probleme melden ist auf diesem Spark ausgeschaltet."
    if not features.allowed("melden", uid):
        return "Probleme melden geht für dich gerade nicht. " + features.missing_text("melden", uid)
    try:
        create(uid, name, channel, text, "sonstiges", 30)
    except HTTPException as e:
        return str(e.detail)
    if channel != "telegram":     # Telegram gets the answer right there
        await note_ready(uid, channel)
    return ("Ich habe einen Entwurf angelegt. Ansehen und senden kannst du ihn unter Ich → Probleme melden; "
            "erst nach deinem Blick geht etwas raus.")


# ---------------------------------------------------------------- endpoints
def _own(who, rid):
    d = _read(rid)
    if not d or (d.get("uid") != who["uid"] and not who["staff"]):
        raise HTTPException(404, "Entwurf nicht gefunden.")
    return d


def _names():
    return {u["id"]: u["name"] for u in profiles._load().get("users", [])}


@router.get("/api/report", dependencies=[Depends(assistant)])
async def get_reports(request: Request, id: str = ""):
    """The form's choices, the limits and the caller's reports (staff: all, with who made them)."""
    who = caller(request)
    guard.limit(request, "report", uid=who["uid"] or None, admin=who["staff"])
    if id:
        d = _own(who, id)
        return dict(view(d, who["uid"]), preview=preview(d))
    items = _all()
    if not who["staff"]:
        items = [d for d in items if d.get("uid") == who["uid"]]
    names = _names() if who["staff"] else None
    states = await issue_states() if any(d.get("status") == "gesendet" for d in items[:50]) else {}
    rows = []
    for d in items[:50]:
        row = dict(view(d, who["uid"], names), text=d["parts"]["text"][:200])
        num = (d.get("issue") or {}).get("number")
        if num in states:
            row["gh"] = states[num]
        rows.append(row)
    return {"areas": [{"key": k, "name": [v[0], v[1]]} for k, v in AREAS.items()], "minutes": list(MINUTES),
            "logs": who["logs"], "token": bool(_token()), "repo": repo(), "max_text": MAX_TEXT,
            "staff": who["staff"], "items": rows,
            "notify": _may_notify(who["uid"])}


@router.post("/api/report/draft", dependencies=[Depends(assistant)])
async def post_draft(request: Request):
    who = caller(request)
    guard.limit(request, "report", uid=who["uid"] or None, admin=who["staff"])
    b = await core.json_body(request, MAX_APPLOG + 8192)
    tid = b.get("trace") if isinstance(b.get("trace"), str) and re.fullmatch(r"[0-9a-f]{6}", b.get("trace") or "") else None
    applog = b.get("applog") if isinstance(b.get("applog"), str) and who["channel"] == "app" else ""
    d = create(who["uid"], who["name"], who["channel"], b.get("text", ""), str(b.get("area") or "sonstiges"),
               b.get("minutes") if isinstance(b.get("minutes"), int) else 30, logs=b.get("logs") is True,
               reqs=b.get("requests", True) is True, sysinfo=b.get("system", True) is True, applog=applog,
               staff=who["staff"] and who["logs"], may_logs=who["logs"], tid=tid)
    return dict(view(d, who["uid"]), preview=preview(d))


@router.post("/api/report/preview", dependencies=[Depends(assistant)])
async def post_preview(request: Request):
    who = caller(request)
    guard.limit(request, "report", uid=who["uid"] or None, admin=who["staff"])
    b = await core.json_body(request, 16384)
    d = _own(who, str(b.get("id") or ""))
    return preview(d, _skip(b.get("skip") or []))


@router.post("/api/report/send", dependencies=[Depends(assistant)])
async def post_send(request: Request):
    """Sends exactly the previewed text (its signature) to GitHub, or ("browser": true) hands back the filled
    "new issue" link, or ("local": true) only keeps it on the Spark."""
    who = caller(request)
    guard.limit(request, "report", uid=who["uid"] or None, admin=who["staff"])
    b = await core.json_body(request, 16384)
    d = _own(who, str(b.get("id") or ""))
    if d.get("status") != "entwurf":
        raise HTTPException(409, "Schon gesendet oder abgelegt.")
    if b.get("local") is True:
        d["status"] = "lokal"
        with _lock:
            _write(d)
        _live_mark("nur lokal behalten", who["channel"])
        await tell_admins(d)
        return view(d, who["uid"])
    p = preview(d, _skip(b.get("skip") or []))
    if p["leaks"]:
        _live_mark("gesperrt durch die Leck-Prüfung", who["channel"])
        print("meldung: gesperrt durch die Leck-Prüfung:", ", ".join(p["leaks"]), flush=True)
        raise HTTPException(422, "Die Prüfung hat noch etwas gefunden (" + ", ".join(p["leaks"]) + "). Bitte die Zeilen abwählen.")
    sig = str(b.get("sig") or "")
    if not p["sig"] or not hmac.compare_digest(sig, p["sig"]):
        raise HTTPException(409, "Die Vorschau hat sich geändert. Bitte noch einmal ansehen.")
    if b.get("browser") is True:
        return {"url": browser_link(p["title"], p["body"])}
    now = time.time()
    with _lock:
        mine, total, last = _sent_count(_all(now), d.get("uid"), now)
        if mine >= DAY_SENT_UID or total >= DAY_SENT_ALL:
            raise HTTPException(429, "Für heute sind genug Meldungen gesendet. Der Entwurf bleibt.")
        if now - last < GAP_S:
            raise HTTPException(429, "Bitte eine Minute warten.")
        d["status"] = "sendet"
        _write(d)
    t0 = time.time()
    rec = None
    try:
        import live
        rec = live.begin("web" if who["channel"] == "panel" else who["channel"] if who["channel"] in ("app", "telegram") else "other",
                         "", uid=who["uid"] or None, auto=False, why="Problem melden")
        if rec is not None:
            rec.step("in", "Problem melden", t0)
    except Exception:
        rec = None
    try:
        num, url = await send(d, p["title"], p["body"])
    except HTTPException:
        d["status"] = "entwurf"
        with _lock:
            _write(d)
        _live_mark("Senden fehlgeschlagen", who["channel"])
        if rec is not None:
            rec.step("tool", "GitHub-Meldung", t0, time.time(), ok=False)
            live.end(rec, False)
        raise
    d.update(status="gesendet", issue={"number": num, "url": url, "t": int(time.time()), "lines": len(numbered(d)) - len(set(b.get("skip") or []))})
    with _lock:
        _write(d)
    if rec is not None:
        rec.step("tool", "GitHub-Meldung", t0, time.time(), ok=True)
        live.end(rec, True)
    _live_mark("gesendet", who["channel"])
    print(f"meldung: gesendet {d['id']} als Issue {num}", flush=True)
    guard.log("report_sent", uid=who["uid"] or None, detail=f"Problem-Meldung an GitHub (Issue {num})")
    await tell_admins(d)
    return view(d, who["uid"])


@router.post("/api/report/thread", dependencies=[Depends(assistant)])
async def post_thread(request: Request):
    """State and answers on GitHub for one sent report (the caller's own; staff: every one)."""
    who = caller(request)
    guard.limit(request, "report", uid=who["uid"] or None, admin=who["staff"])
    b = await core.json_body(request, 1024)
    d = _own(who, str(b.get("id") or ""))
    num = (d.get("issue") or {}).get("number")
    if d.get("status") != "gesendet" or not isinstance(num, int):
        raise HTTPException(409, "Noch nicht gesendet.")
    return await issue_thread(num)


@router.post("/api/report/delete", dependencies=[Depends(assistant)])
async def post_delete(request: Request):
    who = caller(request)
    guard.limit(request, "report", uid=who["uid"] or None, admin=who["staff"])
    b = await core.json_body(request, 1024)
    d = _own(who, str(b.get("id") or ""))
    with _lock:
        try:
            os.remove(_path(d["id"]))
        except OSError:
            pass
    return {"ok": True}


# the admin: the token (only the main admin, fresh code), its check, the state
@router.get("/api/admin/report", dependencies=[Depends(auth)])
def admin_state(request: Request):
    guard.limit(request, "report", admin=True)
    return dict(token_info(), repo=repo(), on=admin_on(), live=for_live())


@router.put("/api/admin/report/token", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_token(request: Request):
    guard.limit(request, "report", admin=True)
    b = await core.json_body(request, 1024)
    tok = str(b.get("token") or "").strip()
    if not TOKEN.fullmatch(tok):
        raise HTTPException(400, "Nur ein fine-grained Token (beginnt mit github_pat_), nur für das Meldungs-Repo, nur „Issues“.")
    token_save(tok)
    guard.log("report_token", detail="GitHub-Token für Problem-Meldungen gesetzt")
    print("meldung: Token gesetzt", flush=True)
    return await check_token()


@router.delete("/api/admin/report/token", dependencies=[Depends(auth)])
def admin_token_drop(request: Request):
    guard.limit(request, "report", admin=True)
    token_drop()
    guard.log("report_token", detail="GitHub-Token für Problem-Meldungen entfernt")
    return token_info()


@router.post("/api/admin/report/check", dependencies=[Depends(auth)])
async def admin_check(request: Request):
    guard.limit(request, "report", admin=True)
    return await check_token()
