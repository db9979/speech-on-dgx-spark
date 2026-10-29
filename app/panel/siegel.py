"""Versiegeln im Ruhezustand (plan nutzerwissen, Punkt 3, Dominik 2026-10-29 „a“ zu Frage 3): memory, conversations
and what the Spark learned about a person lie sealed in the profile's folder (dateien.SIEGEL, profiles.write_own:
AES-256-GCM, the key of the purpose „profildaten“ from secret.key, the profile and the file name as associated data).

1. Once, safely (migrate, at the panel's start in the background, vorrang.in_thread with the fixed name JOB): plain
   files of older versions are sealed. Before the first one a backup „vor-siegel“ (backup.create); without it nothing
   is changed. Per file under profiles._own_lock (so no write of the panel comes between): read, write sealed
   (atomically), open again and compare; only then it counts. A file that does not compare is written back plain and
   counted as an error. Idempotent: a sealed file is never touched again, a second run with nothing to do makes no
   backup. Journal: „profiles: versiegelt | profile=N dateien=M fehler=F“.
2. A sealed file that does not open (another key: a backup restored on another Spark without the move backup;
   another profile; changed on the disk): profiles.read_own sets it aside once (<name>.unlesbar), never overwrites it,
   the profile starts empty. Admins see a hint on top (alerts, Einstellungen → Sicherung: restore the move backup of
   the old Spark, which carries secret.key); the person sees it under Ich → Gedächtnis (view). When the key is back,
   „Wieder einlesen“ (POST /api/profile/memory/einlesen, einlesen) merges what was set aside with what came since
   (lists by id, the newer entry wins; nothing of the current data goes) and removes the copy only after the merged
   file opened again.
3. On this Spark every backup holds the sealed files and opens again; on another Spark only with the move backup.
   „Kopie meiner Daten“ (speicher.py) copies them unsealed into its own encryption (profiles.own_bytes) and writes
   them back sealed (profiles.write_own).

No switch: a fixed protection rule like the Vorrat (Richtlinie Teil 3, Ausnahmen). Live, logs and the hints carry only
fixed words and numbers, never a file's content.
"""
import json
import os
import time

from fastapi import APIRouter, Depends, Request

import dateien
import guard
import profiles
from core import assistant, browser_profile, json_body

router = APIRouter()

JOB = "Versiegeln"            # vorrang.in_thread: the fixed name of the one-time sealing
WHY = "vor-siegel"            # the backup before it (backup.NAME allows it)
LIVE_S = 60                   # the counts for Live and the hints are taken at most once a minute
WEG_ADMIN = "Einstellungen → Sicherung"
WEG = "Ich → Gedächtnis"
_live = [0.0, None]
_last = {"t": 0, "profile": 0, "dateien": 0, "fehler": 0}   # the last run of migrate (numbers only)


def _raw(uid, name):
    try:
        with open(profiles._path(uid, name), "rb") as f:
            return f.read()
    except OSError:
        return None


HEAD = b'{"v": 1, "data": "'     # how common.write_json begins a sealed file (profiles.write_own)


def _state(uid, name):
    """"sealed", "plain" or None (no file), from the first bytes only: Live asks every minute, convos.json is big."""
    try:
        with open(profiles._path(uid, name), "rb") as f:
            head = f.read(len(HEAD))
    except OSError:
        return None
    return "sealed" if head == HEAD else "plain"


def plain_files(uid):
    """The sealed kinds of files of a profile that still lie plain on the disk."""
    return [name for name in sorted(dateien.SIEGEL) if _state(uid, name) == "plain"]


def aside(uid):
    """The files of a profile set aside because they did not open: [(the file's name, the name aside)]."""
    try:
        there = set(os.listdir(profiles._path(uid)))
    except OSError:
        return []
    return [(name, n) for name in sorted(dateien.SIEGEL) for n in profiles.aside_names(uid, name) if n in there]


def _opens(uid, name, n):
    """The content of a file set aside when it opens now (the key is back), else None."""
    raw = _raw(uid, n)
    if raw is None:
        return None
    try:
        return json.loads(profiles.open_sealed(uid, name, raw))
    except (profiles.Unreadable, ValueError):
        return None


def _seal_one(uid, name):
    """One plain file sealed: True done, False an error (written back plain), None nothing to do."""
    path = profiles._path(uid, name)
    with profiles._own_lock:
        raw = _raw(uid, name)
        if raw is None or profiles.is_sealed(raw):
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None               # broken: the module's own default; the next write seals what it writes
        if not profiles.write_own(uid, name, data):
            return False
        profiles._own.pop(path, None)  # open it from the disk, not from the cache
        try:
            ok = profiles.is_sealed(_raw(uid, name) or b"") and json.loads(profiles.own_bytes(uid, name)) == data
        except (profiles.Unreadable, ValueError, TypeError):
            ok = False
        if not ok:
            from common import write_json
            write_json(path, data, mode=0o600, ensure_ascii=False, dir_mode=0o700)
            profiles._own.pop(path, None)
        return ok


def migrate(backup_create=None):
    """Seals every plain file of dateien.SIEGEL in every profile, after one backup WHY. Returns the numbers."""
    import vorrat
    todo = {uid: plain_files(uid) for uid in profiles.user_ids()}
    todo = {u: n for u, n in todo.items() if n}
    if not todo:
        return {"profile": 0, "dateien": 0, "fehler": 0}
    if not vorrat.key("profildaten"):
        print("profiles: nicht versiegelt | grund=schluessel", flush=True)
        return {"profile": 0, "dateien": 0, "fehler": 0, "grund": "schluessel"}
    try:
        if backup_create is None:
            import backup
            backup_create = backup.create
        backup_create(WHY)
    except Exception as e:   # noqa: BLE001 - without the backup nothing changes
        print(f"profiles: versiegeln abgebrochen | grund=sicherung art={type(e).__name__}", flush=True)
        return {"profile": 0, "dateien": 0, "fehler": 0, "grund": "sicherung"}
    n = bad = 0
    for uid, names in todo.items():
        for name in names:
            r = _seal_one(uid, name)
            n += r is True
            bad += r is False
    print(f"profiles: versiegelt | profile={len(todo)} dateien={n} fehler={bad}", flush=True)
    _last.update(t=int(time.time()), profile=len(todo), dateien=n, fehler=bad)
    _live[1] = None
    return {"profile": len(todo), "dateien": n, "fehler": bad}


async def migrate_later():
    """At the panel's start: once in the background, behind speech (vorrang)."""
    import vorrang
    try:
        await vorrang.in_thread(JOB, migrate)
    except Exception as e:   # noqa: BLE001 - the panel runs on; the next start tries again
        print(f"profiles: versiegeln fehler | art={type(e).__name__}", flush=True)


# ---------------------------------------------------------------- what is set aside comes back
def _merge(name, now, old):
    """What was set aside (old) merged into what came since (now): the current data always stays. By the content's
    shape, never by the file's name (the names only through profiles.read_own / write_own): conversations newest first
    and at most profiles.MAX_CONVOS, facts within profiles._cap."""
    if now in (None, [], {}):
        return old
    if isinstance(now, list) and isinstance(old, list):
        ids = {x.get("id") for x in now if isinstance(x, dict) and x.get("id")}
        if ids:
            more = [x for x in old if isinstance(x, dict) and x.get("id") and x["id"] not in ids]
        else:
            more = [x for x in old if x not in now]
        out = more + now if not ids else now + more
        rows = [x for x in out if isinstance(x, dict)]
        if rows and len(rows) == len(out) and all("msgs" in x for x in rows):        # conversations: newest first, the cap
            out = sorted(rows, key=lambda x: -int(x.get("updated") or 0))[:profiles.MAX_CONVOS]
        elif rows and len(rows) == len(out) and all("text" in x for x in rows):      # facts: the memory's cap
            out, _ = profiles._cap(out)
        return out
    if isinstance(now, dict) and isinstance(old, dict):
        out = dict(now)
        for k, v in old.items():
            out[k] = _merge(name, now[k], v) if k in now and isinstance(now[k], (list, dict)) else now.get(k, v)
        return out
    return now


def einlesen(uid):
    """Brings back every file set aside that opens with the key now. Returns (brought back, still unreadable)."""
    back = left = 0
    with profiles._lock, profiles._own_lock:
        for name, n in aside(uid):
            old = _opens(uid, name, n)
            if old is None:
                left += 1
                continue
            merged = _merge(name, profiles.read_own(uid, name, None), old)
            if not profiles.write_own(uid, name, merged):
                left += 1
                continue
            profiles._own.pop(profiles._path(uid, name), None)
            if profiles.read_own(uid, name, None) != merged:
                left += 1
                continue
            os.remove(profiles._path(uid, n))
            back += 1
    print(f"profiles: wieder eingelesen {profiles.log_name(profiles.by_id(uid))} | dateien={back} offen={left}",
          flush=True)
    _live[1] = None
    return back, left


def view(uid):
    """Ich → Gedächtnis: how many files lie aside and how many of them open now (numbers only)."""
    a = aside(uid)
    return {"aside": len(a), "back": sum(_opens(uid, name, n) is not None for name, n in a), "weg": WEG_ADMIN}


@router.post("/api/profile/memory/einlesen", dependencies=[Depends(assistant)])
async def api_einlesen(request: Request, prof=Depends(browser_profile)):
    """„Wieder einlesen“ under Ich → Gedächtnis: the own profile's files set aside, when they open again."""
    guard.limit(request, "memory", uid=prof["id"])
    await json_body(request, 256)
    import asyncio
    back, left = await asyncio.to_thread(einlesen, prof["id"])
    return {"back": back, "left": left, "siegel": view(prof["id"])}


# ---------------------------------------------------------------- Live and the hints (numbers only)
def counts(now=None):
    """All profiles: sealed files, files of these kinds, plain ones, files set aside, profiles with one aside."""
    now = time.time() if now is None else now
    if _live[1] is not None and now - _live[0] < LIVE_S:
        return dict(_live[1])
    c = {"sealed": 0, "files": 0, "plain": 0, "aside": 0, "profiles_aside": 0}
    for uid in profiles.user_ids():
        for name in dateien.SIEGEL:
            st = _state(uid, name)
            if st:
                c["files"] += 1
                c[st] += 1
        a = len(aside(uid))
        c["aside"] += a
        c["profiles_aside"] += bool(a)
    _live[:] = [now, c]
    return dict(c)


def for_live(now=None):
    """Live node „Gedächtnis“: sealed n of m, set aside k (never a name or a content)."""
    import vault
    return dict(counts(now), on=True, crypto=vault.available())


def alerts():
    """The hint on top of the admin pages: files set aside (another key), or no cryptography (plain at rest)."""
    import vault
    out = []
    c = counts()
    if c["aside"]:
        out.append({"kind": "siegel", "level": "warn", "go": "Einstellungen → Sicherung",   # WEG_ADMIN, a literal for test_sprunglinks
                    "text": f"{c['aside']} {'Datei' if c['aside'] == 1 else 'Dateien'} mit Gedächtnis oder Gesprächen "
                            f"in {c['profiles_aside']} {'Profil' if c['profiles_aside'] == 1 else 'Profilen'} sind mit "
                            "einem anderen Schlüssel versiegelt und liegen beiseite. Die Umzugs-Sicherung des alten "
                            f"Spark einspielen ({WEG_ADMIN}); danach holt „Wieder einlesen“ unter {WEG} sie zurück."})
    if not vault.available() and c["files"]:
        out.append({"kind": "siegel", "level": "warn", "go": "Zustand → Technik",
                    "text": "Gedächtnis und Gespräche liegen unversiegelt auf der Platte: das Paket cryptography fehlt."})
    return out
