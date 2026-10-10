"""Ich → Mein Zustand (V01.0.281, plan plaene/hintergrund-status.md).

One page where a profile sees what the Spark does for it in the background (reading documents, meaning
search, document cards, the reMarkable comparison, tidying mailboxes, contacts, planned jobs, the
morning briefing, the weekly memory check) and whether the services it connected answer (mailboxes,
calendars, address books, Home Assistant, Telegram, iPhone app, Pebble, speakers). Only what is switched
on and connected appears; for each row the reason it waits ("pausiert, solange gesprochen wird",
"wartet auf die Nacht", "Tageslimit erreicht") or what needs the person ("Anmeldung abgelehnt").

Rules:
- Only numbers, fixed words and names the person gave or uploaded (document, mailbox, calendar, device
  names); never document text, mail subjects, senders, events or a server's error text. Errors are
  reduced to a fixed reason (WHY), also for the free texts the modules keep (reason_of).
- Only the own profile; guests never. The page asks no service itself: a service's state is the outcome
  of its last real request (netguard.client(seen=tracker(...)), mail._Session, tidy), kept in memory and
  in state/dienste-zustand.json, keyed by the account's random id.
- Off until the admin (chat.my_status) and the profile (my_status) switch it on (features.py "mystatus").
- History: what ran when (users/<id>/hintergrund.json, at most HIST entries per job, HIST_DAYS days),
  written only for profiles that use the page.

    GET /api/profile/hintergrund     {"rows": [...], "sum": {...}, "why": {...}}  own profile, iPhone app too
    GET /api/admin/hintergrund       counts per state over all profiles, no names (Zustand → Monitoring)
"""
import datetime
import json
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from core import assistant, auth, own_profile

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
HIST, HIST_DAYS = 50, 7
SAVE_EVERY = 600          # service states are written at once when they change, else at most this often
MAX_SERVICES = 2000
OLD_DEVICE = 14 * 86400   # an iPhone or watch not seen for this long is shown as "länger nicht gesehen"

# fixed reasons; clients show the words, never anything a server or a model wrote
WHY = {"sprache": ("pausiert, solange gesprochen wird", "paused while someone speaks"),
       "ruhe": ("wartet auf eine Gesprächspause", "waits for a quiet minute"),
       "nacht": ("wartet auf die Nacht", "waits for the night"),
       "tageslimit": ("Tageslimit erreicht", "daily limit reached"),
       "reihe": ("wartet, bis es dran ist", "waits for its turn"),
       "anmeldung": ("Anmeldung abgelehnt", "sign-in refused"),
       "nicht_erreichbar": ("nicht erreichbar", "not reachable"),
       "adresse": ("Adresse stimmt nicht", "address not found"),
       "dienst": ("Dienst meldet einen Fehler", "the service reports an error"),
       "gesperrt": ("Adresse nicht erlaubt", "address not allowed"),
       "voll": ("Speicher voll", "storage full"),
       "angehalten": ("angehalten, bitte Vorschau ansehen", "stopped, please look at the preview"),
       "antwort": ("wartet auf deine Antwort", "waits for your answer"),
       "lange_nicht": ("länger nicht gesehen", "not seen for a while"),
       "offline": ("gerade nicht verbunden", "not connected right now"),
       "ungeprueft": ("noch nicht abgefragt", "not asked yet"),
       "auswahl": ("noch nichts ausgewählt", "nothing picked yet"),
       "fehler": ("Fehler", "error")}
NEEDS_YOU = {"anmeldung", "adresse", "gesperrt", "voll", "angehalten", "antwort"}
STATES = ("run", "wait", "ok", "bad", "idle")
JOBS = ("docs", "meaning", "brief", "remarkable", "tidy", "contacts", "agent", "briefing", "memtidy")
KINDS = ("mail", "cal", "contacts", "ha")
SERVICES_FILE = os.path.join(STATE, "dienste-zustand.json")

_lock = threading.Lock()
_svc = {"d": None, "saved": 0.0}


def on(uid):
    return bool(uid) and features.allowed("mystatus", uid)


# ---------------------------------------------------------------- what the modules report
def reason_of(text):
    """A module's free error text → one fixed reason (the text itself is never shown)."""
    t = str(text or "").lower()
    if not t:
        return ""
    if any(w in t for w in ("password", "passwort", "401", "403", "token", "unauthor", "anmeld", "rejects", "login")):
        return "anmeldung"
    if any(w in t for w in ("voll", "full", "quota", "speicher")):
        return "voll"
    if any(w in t for w in ("reach", "erreichbar", "timeout", "connect", "resolve", "network")):
        return "nicht_erreichbar"
    if any(w in t for w in ("blocked", "not allowed", "nicht erlaubt")):
        return "gesperrt"
    if any(w in t for w in ("404", "not found", "no calendar", "kein")):
        return "adresse"
    return "fehler"


def _services():
    if _svc["d"] is None:
        try:
            with open(SERVICES_FILE) as f:
                d = json.load(f)
            _svc["d"] = {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _svc["d"] = {}
    return _svc["d"]


def seen(kind, key, ok, why="", now=None):
    """A real request to a connected service ended: answered or not, and why not (a WHY word)."""
    if kind not in KINDS or not key:
        return
    now = int(now or time.time())
    k = f"{kind}:{str(key)[:40]}"
    with _lock:
        d = _services()
        old = d.get(k) or {}
        new = {"try": now, "ok": now if ok else int(old.get("ok") or 0),
               "why": "" if ok else (why if why in WHY else "fehler")}
        changed = not old or old.get("why") != new["why"]
        d[k] = new
        if len(d) > MAX_SERVICES:
            for x in sorted(d, key=lambda x: d[x].get("try", 0))[:len(d) - MAX_SERVICES]:
                d.pop(x, None)
        if changed or now - _svc["saved"] > SAVE_EVERY:
            _svc["saved"] = now
            try:
                os.makedirs(STATE, exist_ok=True)
                tmp = SERVICES_FILE + ".tmp"
                with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                    json.dump(d, f)
                os.replace(tmp, SERVICES_FILE)
            except OSError:
                pass


def tracker(kind, key):
    """For netguard.client(seen=...): one verdict per client."""
    return lambda ok, why: seen(kind, key, ok, why)


def service(kind, key):
    return dict(_services().get(f"{kind}:{str(key)[:40]}") or {})


def _hist_file(uid):
    return profiles._path(uid, "hintergrund.json")


def _hist(uid):
    try:
        with open(_hist_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def note(uid, key, ok, n=0, now=None, per_day=False):
    """A background job of uid ran (ok or not, how much). per_day: one line per day (pages read)."""
    if key not in JOBS or not on(uid):
        return
    now = int(now or time.time())
    day = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    with _lock:
        d = _hist(uid)
        h = [x for x in d.get(key) or [] if isinstance(x, dict)]
        if per_day and h and h[-1].get("day") == day and h[-1].get("ok") == bool(ok):
            h[-1]["n"] = int(h[-1].get("n") or 0) + int(n)
            h[-1]["t"] = now
        else:
            h.append({"t": now, "ok": bool(ok), "n": int(n), "day": day})
        d[key] = [x for x in h if x.get("t", 0) > now - HIST_DAYS * 86400][-HIST:]
        profiles._write(_hist_file(uid), {k: v for k, v in d.items() if k in JOBS})


# ---------------------------------------------------------------- the rows
def _row(key, area, name, state, why="", detail=("", ""), label="", done=None, total=None, last=0, nxt=0, go="", act=""):
    return {"key": key, "area": area, "name": list(name), "state": state, "why": why,
            "why_text": list(WHY[why]) if why in WHY else None, "detail": list(detail), "label": str(label or "")[:80],
            "done": done, "total": total, "last": int(last or 0) or None, "next": int(nxt or 0) or None, "go": go, "act": act}


def _at(now, hhmm, zone=None):
    """The next time of day hh:mm after now, as a unix time."""
    try:
        hh, mm = map(int, str(hhmm).split(":"))
    except ValueError:
        return 0
    t = datetime.datetime.fromtimestamp(now, zone)
    n = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if n <= t:
        n += datetime.timedelta(days=1)
    return int(n.timestamp())


def _docs(uid, now, hist):
    import documents
    import vorrang
    import wissen
    out = []
    if not os.path.exists(documents.db_path(uid)):
        return out
    reading = wissen._now.get("doc") if wissen._now.get("uid") == uid else None
    st = documents.waiting_state(uid, wissen.LONG, reading)
    if not st["docs"]:
        return out
    quiet = wissen.quiet()
    pause = "" if quiet else ("sprache" if vorrang.speaking() else "ruhe")
    last = lambda k: (hist.get(k) or [{}])[-1].get("t", 0)
    if features.allowed("docpics", uid):
        n = wissen.night(now)
        key, limit = ("night", wissen.NIGHT_PAGES) if n and n["active"] else ("vision", wissen.DAY_PAGES)
        day = n["key"] if n and n["active"] else wissen.today(now)
        today = documents.count_today(uid, day, key=key)
        tday = (f"heute {today} von {limit} Seiten", f"{today} of {limit} pages today")
        if not st["pages"]:
            out.append(_row("docs", "jobs", ("Dokumente lesen", "Reading documents"), "ok",
                            detail=("Alles gelesen · " + tday[0], "Everything read · " + tday[1]), last=last("docs"), go="docbox"))
        elif st["doc"]:
            dd = st["doc"]
            page = max(1, dd["pages"] - dd["left"] + 1)
            out.append(_row("docs", "jobs", ("Dokumente lesen", "Reading documents"), "run", label=dd["name"],
                            detail=(f"Seite {page} von {dd['pages']} · {tday[0]}", f"page {page} of {dd['pages']} · {tday[1]}"),
                            done=page - 1, total=dd["pages"], last=last("docs"), go="docbox"))
        else:
            nxt = 0
            if today >= limit:
                why, nxt = "tageslimit", (_at(now, n["from"]) if n and not n["active"] else _at(now, "00:00"))
            elif pause:
                why = pause
            elif not st["short"] and st["long_pages"] and not wissen.long_ok(now):
                why, nxt = "nacht", (_at(now, n["from"]) if n else 0)
            else:
                why = "reihe"
            more = (f" · {st['long_pages']} davon in {st['long_docs']} langen Dokumenten" if st["long_docs"] else "",
                    f" · {st['long_pages']} of them in {st['long_docs']} long documents" if st["long_docs"] else "")
            out.append(_row("docs", "jobs", ("Dokumente lesen", "Reading documents"), "wait", why,
                            (f"{st['pages']} Seiten warten{more[0]} · {tday[0]}", f"{st['pages']} pages waiting{more[1]} · {tday[1]}"),
                            last=last("docs"), nxt=nxt, go="docbox"))
    if features.allowed("docmeaning", uid):
        have, total = documents.vector_state(uid)
        if total:
            state, why = ("ok", "") if have >= total else (("run", "") if quiet else ("wait", pause))
            out.append(_row("meaning", "jobs", ("Bedeutungssuche vorbereiten", "Preparing meaning search"), state, why,
                            (f"{have} von {total} Abschnitten", f"{have} of {total} passages"),
                            done=have, total=total, last=last("meaning"), go="docbox"))
    if features.allowed("docbrief", uid):
        left = st["briefs"]
        made = documents.count_today(uid, wissen.today(now), key="brief")
        if not left:
            state, why = "ok", ""
        elif made >= wissen.BRIEF_DAY:
            state, why = "wait", "tageslimit"
        else:
            state, why = ("wait", pause or "reihe")
        out.append(_row("brief", "jobs", ("Steckbriefe schreiben", "Writing document cards"), state, why,
                        (f"{left} Dokumente ohne Steckbrief" if left else "Alle Dokumente haben einen Steckbrief",
                         f"{left} documents without a card" if left else "Every document has a card"),
                        last=last("brief"), go="docbox"))
    return out


def _remarkable(uid, now):
    import remarkable
    if not features.allowed("remarkable", uid):
        return []
    d = remarkable.load(uid)
    if not d.get("token"):
        return []
    name = ("reMarkable abgleichen", "Comparing the reMarkable")
    n = int(d.get("count") or len(d.get("docs") or {}))
    detail = (f"{n} Notizbücher", f"{n} notebooks")
    last = d.get("last", 0)
    nxt = (last + (remarkable.SOON if d.get("more") else remarkable.SYNC_EVERY)) if last else 0
    if uid in remarkable._busy:
        p = remarkable._progress.get(uid) or [None, None]
        return [_row("remarkable", "jobs", name, "run", detail=detail, done=p[0], total=p[1], last=last, go="rmbox")]
    if d.get("error"):
        return [_row("remarkable", "jobs", name, "bad", reason_of(d["error"]), detail, last=last, nxt=nxt, go="rmbox", act="rmsync")]
    if not (d.get("picked") or d.get("all")):
        return [_row("remarkable", "jobs", name, "idle", "auswahl", last=last, go="rmbox")]
    return [_row("remarkable", "jobs", name, "ok", detail=detail, last=last, nxt=nxt, go="rmbox", act="rmsync")]


def _tidy(uid, now, accts):
    import tidy
    if not features.allowed("tidy", uid):
        return []
    d, out = tidy.state(uid), []
    names = {"preview": ("nur Vorschau", "preview only"), "safe": ("sicher automatisch", "safe automatic"),
             "auto": ("automatisch", "automatic")}
    for x in accts:
        a = (d["accounts"].get(x["id"]) or {})
        mode = a.get("mode", "off")
        if mode == "off":
            continue
        last = a.get("last_run", 0)
        nxt = last + d["every"] * 60 if last else 0
        moved = sum(1 for e in d["log"] if e.get("aid") == x["id"] and e.get("t", 0) > now - 86400)
        det = (f"{names.get(mode, ('', ''))[0]} · heute {moved} verschoben", f"{names.get(mode, ('', ''))[1]} · {moved} moved today")
        if a.get("stopped"):
            state, why = "bad", "angehalten"
        elif a.get("error"):
            state, why = "bad", reason_of(a["error"])
        else:
            state, why = ("ok" if last else "idle"), ""
        out.append(_row("tidy", "jobs", ("Postfach aufräumen", "Tidying the inbox"), state, why, det, x.get("name", ""),
                        last=last, nxt=nxt, go="mailbox"))
    return out


def _contacts(uid, now):
    import contacts
    if not features.allowed("contacts", uid):
        return [], []
    raw = contacts._raw(uid)
    accts = [x for x in raw.get("accounts") or [] if isinstance(x, dict) and x.get("id")]
    if not accts:
        return [], []
    fetched = raw.get("fetched") or 0
    errors = raw.get("errors") or []
    state = "bad" if errors and len(errors) >= len(accts) else ("ok" if fetched else "idle")
    why = reason_of(errors[0]) if state == "bad" else ""
    job = _row("contacts", "jobs", ("Kontakte holen", "Fetching contacts"), state, why,
               ("einmal am Tag", "once a day"), last=fetched, nxt=(fetched + contacts.REFRESH) if fetched else 0,
               go="conbox", act="conrefresh")
    return [job], [_svc_row("contacts", x["id"], ("Adressbuch", "Address book"), x.get("name", ""), "conbox") for x in accts]


def _agent(uid, now):
    import agent
    if not features.allowed("agent", uid):
        return []
    d = agent.load(uid)
    plans = [p for p in d["plans"] if not p.get("paused") and p.get("next")]
    running = sum(1 for j in d["jobs"] if j.get("state") == "running")
    queued = sum(1 for j in d["jobs"] if j.get("state") == "queued")
    recent = [j for j in d["jobs"] if (j.get("finished") or j.get("created") or 0) > now - HIST_DAYS * 86400]
    if not (plans or running or queued or recent):
        return []
    last = max([j.get("finished") or 0 for j in d["jobs"]] or [0])
    nxt = min([p["next"] for p in plans] or [0])
    state, why = ("run", "") if running else (("wait", "reihe") if queued else ("ok" if recent else "idle", ""))
    failed = sum(1 for j in recent if j.get("state") == "failed")
    det = (f"{len(plans)} geplant · {queued} warten · {failed} ohne Bericht (7 Tage)",
           f"{len(plans)} planned · {queued} waiting · {failed} without a report (7 days)")
    return [_row("agent", "jobs", ("Aufträge", "Jobs"), state, why, det, last=last, nxt=nxt, go="agentbox")]


def _briefing(uid, now, s):
    import chat
    if not s.get("briefing_at") or not features.allowed("calendar", uid):
        return []
    zone = chat.user_zone(s.get("tz", ""))
    try:
        day = open(profiles._path(uid, "briefing-sent")).read().strip()
        last = int(datetime.datetime.strptime(day + " " + s["briefing_at"], "%Y-%m-%d %H:%M").replace(tzinfo=zone).timestamp())
    except (OSError, ValueError):
        last = 0
    return [_row("briefing", "jobs", ("Morgenbriefing", "Morning briefing"), "ok" if last else "idle",
                 detail=(f"jeden Tag um {s['briefing_at']}", f"every day at {s['briefing_at']}"),
                 last=last, nxt=_at(now, s["briefing_at"], zone), go="calbox")]


def _memtidy(uid, now):
    import memtidy
    if not features.allowed("memory", uid) or len(profiles.memory(uid)) < memtidy.MIN_FACTS:
        return []
    last = memtidy._checked(uid)
    waiting = os.path.exists(memtidy._file(uid, "memory-tidy.json"))
    return [_row("memtidy", "jobs", ("Gedächtnis aufräumen", "Tidying memory"), "bad" if waiting else ("ok" if last else "idle"),
                 "antwort" if waiting else "", ("einmal pro Woche", "once a week"),
                 last=last, nxt=(last + memtidy.EVERY) if last else 0, go="factbox")]


def _svc_row(kind, key, name, label, go):
    st = service(kind, key)
    if not st:
        return _row(f"{kind}:{key}", "services", name, "idle", "ungeprueft", label=label, go=go)
    if st.get("why"):
        return _row(f"{kind}:{key}", "services", name, "bad", st["why"], label=label, last=st.get("ok"), go=go)
    return _row(f"{kind}:{key}", "services", name, "ok", label=label, last=st.get("ok"), go=go)


def _devices(uid, now):
    out = []
    devs = profiles.own_devices(uid)
    for kind, flag, fkey, go, name in (("app", "app", "iphone", "appbox", ("iPhone-App", "iPhone app")),
                                       ("watch", "watch", "pebble", "pebbox", ("Pebble-Uhr", "Pebble watch"))):
        if not features.allowed(fkey, uid):
            continue
        for x in devs:
            if not x.get(flag):
                continue
            t = int((x.get("last") or {}).get("t") or 0) if isinstance(x.get("last"), dict) else int(x.get("last") or 0)
            old = not t or now - t > OLD_DEVICE
            out.append(_row(f"{kind}:{x['id']}", "services", name, "wait" if old else "ok", "lange_nicht" if old else "",
                            label=x.get("name", ""), last=t, go=go))
    if features.allowed("esp32", uid):
        import esp32
        for x in esp32._list(uid):
            out.append(_row(f"esp:{x['id']}", "services", ("Lautsprecher", "Speaker"), "ok" if x.get("online") else "wait",
                            "" if x.get("online") else "offline", label=x.get("name", ""), last=x.get("seen"), go="espbox"))
    return out


def rows(uid, now=None):
    """Every row for uid: background jobs first, then connected services."""
    now = now or time.time()
    s = profiles.settings(uid)
    hist = _hist(uid)
    jobs, svcs = [], []
    accts = []
    if features.allowed("mail", uid):
        import mail
        accts = mail.public(uid)["accounts"]
    for part in (lambda: _docs(uid, now, hist), lambda: _remarkable(uid, now), lambda: _tidy(uid, now, accts),
                 lambda: _agent(uid, now), lambda: _briefing(uid, now, s), lambda: _memtidy(uid, now)):
        try:
            jobs += part()
        except Exception as e:      # one broken part never hides the others
            print("hintergrund:", type(e).__name__, flush=True)
    try:
        cj, cs = _contacts(uid, now)
        jobs += cj
    except Exception as e:
        cs = []
        print("hintergrund: contacts:", type(e).__name__, flush=True)
    svcs += [_svc_row("mail", x["id"], ("Postfach", "Mailbox"), x.get("name", ""), "mailbox") for x in accts]
    try:
        if features.allowed("calendar", uid):
            import calendars
            svcs += [_svc_row("cal", x["id"], ("Kalender", "Calendar"), x.get("name", ""), "calbox")
                     for x in calendars.public(uid)["calendars"]]
        svcs += cs
        if features.allowed("ha", uid):
            import homeassistant
            if homeassistant._raw(uid):
                svcs.append(_svc_row("ha", uid, ("Home Assistant", "Home Assistant"), "", "habox"))
        if features.allowed("telegram", uid):
            import telegram
            if telegram.link(uid):
                bad = telegram.conflict["count"] >= 2
                svcs.append(_row("telegram", "services", ("Telegram", "Telegram"), "bad" if bad else "ok", "dienst" if bad else "", go="tgbox"))
        svcs += _devices(uid, now)
    except Exception as e:
        print("hintergrund: services:", type(e).__name__, flush=True)
    for r in jobs:
        h = hist.get(r["key"]) or []
        r["hist"] = [[x.get("t"), bool(x.get("ok")), int(x.get("n") or 0)] for x in h if r["key"] in JOBS][-HIST:]
    return jobs + svcs


def summary(rs):
    out = {k: sum(1 for r in rs if r["state"] == k) for k in STATES}
    out["need"] = sum(1 for r in rs if r["state"] == "bad" and r["why"] in NEEDS_YOU)
    return out


# ---------------------------------------------------------------- routes
@router.get("/api/profile/hintergrund", dependencies=[Depends(assistant)])
def profile_state(request: Request, brief: bool = False, prof=Depends(own_profile)):
    uid = prof["id"]
    guard.limit(request, "bg", uid)
    if not on(uid):
        raise HTTPException(403, "Mein Zustand ist aus (Funktionen, Ich → Mein Zustand)")
    rs = rows(uid)
    if brief:   # the dot at "Ich": only how many need the person
        return {"sum": summary(rs)}
    return {"rows": rs, "sum": summary(rs), "now": int(time.time())}


@router.get("/api/admin/hintergrund", dependencies=[Depends(auth)])
def admin_state(request: Request):
    """Zustand → Monitoring: counts over the profiles that use the page, never names or labels."""
    guard.limit(request, "bg", admin=True)
    if not features.admin_on("mystatus"):
        return {"on": False}
    out = {"on": True, "profiles": 0, "jobs": dict.fromkeys(STATES, 0), "services": dict.fromkeys(STATES, 0), "need": 0}
    for uid in profiles.user_ids():
        if not on(uid):
            continue
        out["profiles"] += 1
        rs = rows(uid)
        for r in rs:
            out[r["area"]][r["state"]] += 1
        out["need"] += summary(rs)["need"]
    return out
