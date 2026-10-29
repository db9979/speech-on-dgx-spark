"""Alle meine Daten herunterladen (plan nutzerwissen, Punkt 5; Dominik 2026-10-29 „a“ zu Frage 4): one ZIP with
everything a profile keeps on the Spark, for the person herself.

No switch: the right to see the own data (Richtlinie Teil 3, „Ausnahmen“). Guests have no profile and get nothing.

What goes in comes only from the Datei-Register (dateien.EXPORT, the field export=): every file with bereich= or
siegel= (conversations, memory with its earlier versions, tasks, reminders, documents with their originals, what was
made, pictures, songs), the settings without a sealed value, the Spark calendar, health, interests, the Spark diary,
and of the chats between profiles only the person's own messages (chats.own_messages). Sealed files go in opened
(profiles.read_own), a value sealed inside a JSON file never (_ohne_siegel). What stays out (passwords, tokens,
keys, the second step, code words, the phone PIN, the voiceprint, queues, the mail, weather and parcel supplies of
foreign servers) is listed in LIESMICH.txt with the register's reason (dateien.DRAUSSEN_DATEIEN), German and English.

    GET  /api/profile/export              what would go in, by area with sizes, and what stays out with its reason
    POST /api/profile/export {ohne?, pin?} builds the ZIP: always a fresh code or passkey (stufen.LIST „Schutz
                                          ändern“), without a second step the PIN; from the iPhone app only with the
                                          second step. JE_STUNDE per hour and profile, one at a time on the Spark,
                                          GRENZE bytes at most before packing (too big: 413 with the areas to leave
                                          out). Answers a one-time pickup code (128 bits, only its hash is kept,
                                          ABHOLEN_S seconds).
    GET  /api/profile/export/{code}       the ZIP once (no-store), then it is deleted; only the profile it was made for

Built in state/export-tmp/ (common.STATE, register lokal=), in a thread (vorrang.in_thread), never on the event loop;
a file not picked up goes after ABHOLEN_S, at the next export or when the panel starts. The ZIP holds no link and
only names from the register (folders one level, names as speicher.FILE_RE). Journal lines „meinedaten:“ with fixed
words and numbers, the admin's change log only „profile_export“ with counts; Live numbers only.
"""
import collections
import datetime
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import stat
import tempfile
import threading
import time
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

import dateien
import guard
import mfa
import profiles
from common import STATE, DayCounter
from core import app_version, assistant, browser_profile, confirm_code, json_body

router = APIRouter()

TMP = os.path.join(STATE, "export-tmp")
GRENZE = 2 * 1024 ** 3       # bytes on the disk before packing (plan: 2 GB)
PLATZ_REST = 64 * 1024 ** 2  # free disk the Spark keeps on top of the ZIP
ABHOLEN_S = 600              # the pickup code works this long, once
JE_STUNDE = 3                # ZIPs per profile and hour
BODY_MAX = 1024
CODE_BYTES = 16              # 128 bits
DATEIEN_MAX = 20000          # files in one ZIP
WEG = "Ich → Sicherheit → Meine Daten"
# the areas a person can leave out: the register's areas of „Kopie meiner Daten“, the rest and the own chat messages
BEREICHE = dict(dateien.BEREICHE, weiteres=("Einstellungen und Weiteres", "Settings and more"),
                chats=("Eigene Nachrichten in Chats", "Own messages in chats"))
GRUENDE = ("code", "pin", "limit", "zu-gross", "belegt", "platz", "ohne-schritt", "fehler")
SAY = {"limit": f"Höchstens {JE_STUNDE} Mal je Stunde. Bitte später noch einmal.",
       "belegt": "Der Spark packt gerade schon eine Datei. Bitte gleich noch einmal.",
       "platz": "Auf dem Spark ist dafür gerade nicht genug Platz frei.",
       "zu-gross": "Zu groß für eine Datei: bitte Bereiche abwählen.",
       "ohne-schritt": "Dafür braucht dein Profil den zweiten Anmeldeschritt (Ich → Sicherheit).",
       "pin": "Falsche PIN.", "fehler": "Das Packen hat nicht geklappt. Bitte noch einmal.",
       "abgelaufen": "Dieser Abhol-Code gilt nicht mehr. Bitte neu herunterladen."}

_lock = threading.Lock()
_abholen = {}                # sha256(code) -> {"uid", "path", "bis", "bytes"}
_stunde = collections.defaultdict(collections.deque)   # uid -> times of the ZIPs of the last hour
_baut = set()                # profiles whose ZIP is being packed (one at a time on the Spark)
_day = DayCounter(gebaut=0, abgeholt=0, abgelehnt=0, abgelaufen=0)   # Zustand → Live, numbers only


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


# ---------------------------------------------------------------- what goes in
def _gruppe(d):
    return d.bereich or ("chats" if d.name == "_chats/" else "weiteres")


def _settings(uid):
    return profiles.settings(uid)


def _kalender(uid):
    import sparkkalender
    return sparkkalender.export(uid)


def _gesundheit(uid):
    import pebblewatch
    return pebblewatch.health(uid)


def _chats(uid):
    import chats
    return chats.own_messages(uid)


def _fund(uid):
    import fund
    return fund.export(uid)


# a file of the register sealed in its own way (not siegel=) is opened by the module that keeps it, never copied raw
LESER = {"settings.json": _settings, "spark-kalender.json": _kalender, "gesundheit.json": _gesundheit,
         "_chats/": _chats, "fund.db": _fund}
VERSIEGELT = ("enc1:", "g1:", "G1")   # vault.PREFIX, chats, vorrat: a sealed value inside a file never goes out


def _ohne_siegel(x):
    """x without any value that is still sealed (a token, a password, a feed address inside a settings file)."""
    if isinstance(x, dict):
        return {k: _ohne_siegel(v) for k, v in x.items() if not (isinstance(v, str) and v.startswith(VERSIEGELT))}
    if isinstance(x, list):
        return [_ohne_siegel(v) for v in x if not (isinstance(v, str) and v.startswith(VERSIEGELT))]
    return x


def _datei(path):
    """(size) of a regular file that is no link, else None."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_size if stat.S_ISREG(st.st_mode) else None


def plan(uid):
    """[{"rel", "name", "gruppe", "bytes", "wie"}] of what the ZIP would hold, from dateien.EXPORT only; wie: "eigen"
    (sealed whole, profiles.read_own), "leser" (LESER), "db" (SQLite), "json" or "datei"."""
    import speicher
    base, out = profiles._path(uid), []
    for name, d in dateien.EXPORT.items():
        g = _gruppe(d)
        if name in LESER:
            p = profiles._path(uid, name) if d.ort == "profil" else ""
            size = _datei(p) if p else None
            out.append({"rel": name.rstrip("/") + ".json", "name": name, "gruppe": g, "bytes": size or 0, "wie": "leser"})
            continue
        if d.ort != "profil":
            continue
        if name.endswith("/"):
            folder = os.path.join(base, name)
            try:
                if os.path.islink(folder.rstrip("/")) or not os.path.isdir(folder):
                    continue
                entries = sorted(os.scandir(folder), key=lambda e: e.name)
            except OSError:
                continue
            for e in entries:
                if not speicher.FILE_RE.fullmatch(e.name) or e.name.startswith(".") or e.name.endswith(".tmp"):
                    continue
                size = _datei(os.path.join(folder, e.name))
                if size is not None:
                    out.append({"rel": name + e.name, "name": name, "gruppe": g, "bytes": size, "wie": "datei"})
            continue
        size = _datei(os.path.join(base, name))
        if size is None:
            continue
        wie = "eigen" if d.siegel else "db" if name.endswith(".db") else "json" if name.endswith(".json") else "datei"
        out.append({"rel": name, "name": name, "gruppe": g, "bytes": size, "wie": wie})
    return out[:DATEIEN_MAX]


def overview(uid):
    """For the page and the apps: the areas with count and size, what stays out with its reason (fixed words only)."""
    items = plan(uid)
    areas = []
    for k, (de, en) in BEREICHE.items():
        mine = [x for x in items if x["gruppe"] == k]
        areas.append({"id": k, "name": [de, en], "dateien": len(mine), "bytes": sum(x["bytes"] for x in mine)})
    out = [{"name": n, "was": [dateien.INHALT[n][0], dateien.INHALT[n][1]], "grund": list(r)}
           for n, r in sorted(dateien.DRAUSSEN_DATEIEN.items())]
    return {"bereiche": areas, "draussen": out, "grenze": GRENZE, "je_stunde": JE_STUNDE, "abholen_s": ABHOLEN_S,
            "code": mfa.enabled(uid), "weg": WEG}


# ---------------------------------------------------------------- the ZIP
class ZuGross(Exception):
    def __init__(self, sizes):
        super().__init__("zu gross")
        self.sizes = sizes


class KeinPlatz(Exception):
    pass


def _liesmich(uid, drin, ohne, unlesbar, now):
    """LIESMICH.txt: what is in, what stays out and why, German and English; only the register's words and names."""
    prof = profiles.by_id(uid) or {}
    stamp = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    namen = sorted({x["name"] for x in drin})
    lines = []
    for lang, i in (("de", 0), ("en", 1)):
        de = lang == "de"
        lines += ["Alle meine Daten – Speech on DGX Spark" if de else "All my data – Speech on DGX Spark",
                  ("Profil: " if de else "Profile: ") + str(prof.get("name") or ""), ("Stand: " if de else "As of: ") + stamp,
                  ("Version: " if de else "Version: ") + app_version(), "",
                  "Was drin ist (Ordner daten/):" if de else "What is in it (folder daten/):"]
        lines += [f"- {n}: {dateien.INHALT[n][i]}" for n in namen]
        if ohne:
            lines += ["", "Von dir abgewählt:" if de else "Left out by you:"]
            lines += [f"- {BEREICHE[k][i]}" for k in ohne]
        if unlesbar:
            lines += ["", "Nicht lesbar (mit dem Schlüssel dieses Spark nicht zu öffnen, beiseitegelegt):" if de
                      else "Not readable (does not open with this Spark's key, set aside):"]
            lines += [f"- {n}" for n in unlesbar]
        lines += ["", "Was draußen bleibt und warum:" if de else "What stays out and why:"]
        lines += [f"- {n} ({dateien.INHALT[n][i]}): {r[i]}" for n, r in sorted(dateien.DRAUSSEN_DATEIEN.items())]
        lines += ["", ("Chats zwischen Profilen: nur deine eigenen Nachrichten, ohne private Chats; Fotos, Dateien und "
                       "Sprachnachrichten nur als Art." if de else
                       "Chats between profiles: only your own messages, without private chats; photos, files and "
                       "voice messages only as their kind."), "", "-" * 40, ""]
    return "\n".join(lines).encode()


def _add(zf, arc, data):
    zf.writestr(zipfile.ZipInfo(arc, date_time=time.localtime()[:6]), data, compress_type=zipfile.ZIP_DEFLATED)


def build(uid, ohne=(), now=None):
    """Packs the ZIP in TMP (a thread, never the event loop). Returns (path, files, bytes). Raises ZuGross with the
    sizes by area when the chosen files are over GRENZE, KeinPlatz when the disk is too full."""
    import speicher
    now = time.time() if now is None else now
    items = [x for x in plan(uid) if x["gruppe"] not in ohne]
    total = sum(x["bytes"] for x in items)
    if total > GRENZE:
        sizes = {}
        for x in items:
            sizes[x["gruppe"]] = sizes.get(x["gruppe"], 0) + x["bytes"]
        raise ZuGross(sizes)
    os.makedirs(TMP, mode=0o700, exist_ok=True)
    if shutil.disk_usage(TMP).free < total + PLATZ_REST:
        raise KeinPlatz()
    fd, path = tempfile.mkstemp(prefix="export-", suffix=".zip", dir=TMP)
    os.close(fd)
    base, n, unlesbar, counts = profiles._path(uid), 0, [], {}
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for x in items:
                arc = "daten/" + x["rel"]
                src = os.path.join(base, x["rel"])
                if x["wie"] in ("eigen", "leser", "json"):
                    if x["wie"] == "eigen":
                        data = profiles.read_own(uid, x["name"])
                        if data is None and _datei(src) is None and x["bytes"]:
                            unlesbar.append(x["name"])    # set aside by read_own: never an empty copy of it
                            continue
                    elif x["wie"] == "leser":
                        data = LESER[x["name"]](uid)
                    else:
                        try:
                            with open(src, "rb") as f:
                                data = json.loads(f.read(speicher.MAX_FILE + 1))
                        except (OSError, ValueError):
                            continue
                    _add(zf, arc, json.dumps(_ohne_siegel(data), ensure_ascii=False, indent=1))
                elif x["wie"] == "db":
                    tmp = path + ".db"
                    try:
                        speicher._snapshot(src, tmp)      # SQLite through its backup: the panel may be writing
                        zf.write(tmp, arc)
                    except (OSError, ValueError):
                        continue
                    finally:
                        try:
                            os.remove(tmp)
                        except FileNotFoundError:
                            pass
                else:
                    try:
                        f = open(os.open(src, os.O_RDONLY | os.O_NOFOLLOW), "rb")
                    except OSError:
                        continue
                    with f, zf.open(zipfile.ZipInfo(arc, date_time=time.localtime()[:6]), "w", force_zip64=True) as w:
                        shutil.copyfileobj(f, w, 1 << 20)
                n += 1
                counts[x["gruppe"]] = counts.get(x["gruppe"], 0) + 1
            _add(zf, "LIESMICH.txt", _liesmich(uid, items, list(ohne), unlesbar, now))
            _add(zf, "uebersicht.json", json.dumps({"version": app_version(), "stand": int(now), "dateien": n,
                                                     "bereiche": counts, "abgewaehlt": list(ohne),
                                                     "nicht_lesbar": unlesbar,
                                                     "draussen": sorted(dateien.DRAUSSEN_DATEIEN)}, indent=1))
    except BaseException:
        _weg(path)
        raise
    os.chmod(path, 0o600)
    return path, n, os.path.getsize(path)


def _weg(path):
    try:
        os.remove(path)
    except OSError:
        pass


def sweep(now=None):
    """Drops every pickup that ran out and every older file in TMP no code points to (a ZIP never fetched)."""
    now = time.time() if now is None else now
    with _lock:
        for h in [h for h, x in _abholen.items() if x["bis"] < now]:
            _weg(_abholen.pop(h)["path"])
            _day.bump("abgelaufen")
            print("meinedaten: abgelaufen | dateien=1", flush=True)
        keep = {x["path"] for x in _abholen.values()}
    try:
        names = os.listdir(TMP)
    except OSError:
        return
    for name in names:      # a ZIP being packed is fresh; one older than any code can never be fetched
        p = os.path.join(TMP, name)
        try:
            old = now - os.lstat(p).st_mtime > ABHOLEN_S
        except OSError:
            continue
        if p not in keep and old:
            _weg(p)


# ---------------------------------------------------------------- the rules before packing
def _stunde_frei(uid, now):
    q = _stunde[uid]
    while q and now - q[0] > 3600:
        q.popleft()
    return len(q) < JE_STUNDE


def _abgelehnt(uid, grund, status, text=None, headers=None):
    _day.bump("abgelehnt")
    print(f"meinedaten: abgelehnt grund={grund} | {_who(uid)}", flush=True)
    raise HTTPException(status, text or SAY[grund], headers=headers)


def _bestaetigt(request, prof, body):
    """Without the second step: the PIN, typed every time; the iPhone app needs the step (api_export asks the fresh
    code or passkey itself when the profile has it)."""
    uid = prof["id"]
    if request.scope.get("speech_app_area"):
        _abgelehnt(uid, "ohne-schritt", 403)
    u = next((u for u in profiles._load()["users"] if u["id"] == uid), None)
    guard.check(request, prof["name"])
    pin = body.get("pin")
    if not u or not isinstance(pin, str) or len(pin) > 64 or not profiles._pin_ok(pin, u["pin"]):
        guard.failed(request, prof["name"], what="export_pin")
        _abgelehnt(uid, "pin", 401)
    guard.succeeded(request, prof["name"])


# ---------------------------------------------------------------- endpoints
@router.get("/api/profile/export", dependencies=[Depends(assistant)])
def api_overview(request: Request, prof=Depends(browser_profile)):
    """The dialog: areas with sizes, what stays out and why, whether a code or the PIN is asked."""
    guard.limit(request, "export", uid=prof["id"])
    return overview(prof["id"])


@router.post("/api/profile/export", dependencies=[Depends(assistant)])
async def api_export(request: Request, prof=Depends(browser_profile)):
    """Packs the ZIP after a fresh code (or the PIN): {"code", "url", "gilt_s", "dateien", "bytes"}."""
    import live
    import vorrang
    uid = prof["id"]
    guard.limit(request, "export", uid=uid)
    body = await json_body(request, BODY_MAX)
    ohne = [k for k in body.get("ohne") or [] if k in BEREICHE] if isinstance(body.get("ohne"), list) else []
    if mfa.enabled(uid):          # always a fresh code or passkey (stufen.LIST „Schutz ändern“), no window counts
        try:
            await confirm_code(request, uid, prof["name"], fresh=True)
        except HTTPException as e:
            if e.detail == "wrong code":
                _day.bump("abgelehnt")
                print(f"meinedaten: abgelehnt grund=code | {_who(uid)}", flush=True)
            raise
    else:
        _bestaetigt(request, prof, body)
    now = time.time()
    with _lock:
        if not _stunde_frei(uid, now):
            busy = "limit"
        elif _baut:
            busy = "belegt"
        else:
            busy = ""
            _baut.add(uid)
            _stunde[uid].append(now)
    if busy:
        _abgelehnt(uid, busy, 429 if busy == "limit" else 409, headers={"Retry-After": "60"})
    rec = live.begin("app" if request.scope.get("speech_app_area") else "web", "", uid=uid, why="Daten herunterladen",
                     request=request)
    t0 = time.time()
    try:
        await vorrang.in_thread("Daten herunterladen", sweep)
        path, n, size = await vorrang.in_thread("Daten herunterladen", build, uid, tuple(ohne))
    except ZuGross as e:
        live.end(rec, False, "zu_gross")
        _day.bump("abgelehnt")
        print(f"meinedaten: abgelehnt grund=zu-gross mb={sum(e.sizes.values()) // 1048576} | {_who(uid)}", flush=True)
        raise HTTPException(413, SAY["zu-gross"], headers={"X-Speech-Export": json.dumps(
            {k: v // 1048576 for k, v in e.sizes.items()}, separators=(",", ":"))})
    except KeinPlatz:
        live.end(rec, False, "platz")
        _abgelehnt(uid, "platz", 507)
    except (OSError, zipfile.BadZipFile, ValueError) as e:
        live.end(rec, False, "fehler")
        _day.bump("abgelehnt")
        print(f"meinedaten: abgelehnt grund=fehler art={type(e).__name__} | {_who(uid)}", flush=True)
        raise HTTPException(500, SAY["fehler"])
    finally:
        with _lock:
            _baut.discard(uid)
    ms = int((time.time() - t0) * 1000)
    if rec is not None:
        rec.step("tool", "Meine Daten packen", t0, time.time(), ok=True, dateien=str(n))
    live.end(rec, True)
    code = secrets.token_urlsafe(CODE_BYTES)
    with _lock:
        _abholen[hashlib.sha256(code.encode()).hexdigest()] = {"uid": uid, "path": path, "bis": now + ABHOLEN_S,
                                                                "bytes": size}
    timer = threading.Timer(ABHOLEN_S + 5, sweep)
    timer.daemon = True
    timer.start()
    _day.bump("gebaut")
    print(f"meinedaten: export {_who(uid)} | dateien={n} mb={size // 1048576} ms={ms}", flush=True)
    guard.log("profile_export", user=prof["name"], files=n, mb=size // 1048576)
    return {"code": code, "url": f"/api/profile/export/{code}", "gilt_s": ABHOLEN_S, "dateien": n, "bytes": size}


@router.get("/api/profile/export/{code}", dependencies=[Depends(assistant)])
def api_pickup(code: str, request: Request, prof=Depends(browser_profile)):
    """The ZIP once, for the profile it was made for; then it is deleted (also when the download breaks off)."""
    uid = prof["id"]
    guard.limit(request, "exportget", uid=uid)
    h = hashlib.sha256(str(code)[:64].encode()).hexdigest()
    now = time.time()
    with _lock:
        key = next((k for k, x in _abholen.items() if hmac.compare_digest(k, h) and x["uid"] == uid), None)
        got = _abholen.pop(key) if key else None
    if not got or got["bis"] < now:
        if got:
            _weg(got["path"])
        _day.bump("abgelehnt")
        print(f"meinedaten: abholen abgelehnt grund=code | {_who(uid)}", flush=True)
        raise HTTPException(404, SAY["abgelaufen"])
    _day.bump("abgeholt")
    print(f"meinedaten: abgeholt | mb={got['bytes'] // 1048576} | {_who(uid)}", flush=True)
    name = "spark-meine-daten-" + datetime.date.fromtimestamp(now).isoformat() + ".zip"
    return FileResponse(got["path"], media_type="application/zip", filename=name,
                        headers={"Cache-Control": "no-store"}, background=BackgroundTask(_weg, got["path"]))


# ---------------------------------------------------------------- Zustand → Live (numbers only)
def for_live(now=None):
    """Today's ZIPs, pickups, refusals, expired codes, whether one is being packed; never a name or a file."""
    with _lock:
        offen, baut = len(_abholen), len(_baut)
    return dict({k: v for k, v in _day.today(now).items() if k != "day"}, offen=offen, baut=baut)


# ---------------------------------------------------------------- the access log never holds a pickup code
PFAD = "/api/profile/export/"


class OhneCode(logging.Filter):
    """uvicorn writes every path into its access log (the journal): a pickup code there becomes „…“."""
    def filter(self, record):
        a = record.args
        if isinstance(a, tuple) and len(a) > 2 and isinstance(a[2], str) and a[2].startswith(PFAD):
            record.args = a[:2] + (PFAD + "…",) + a[3:]
        return True


if not any(isinstance(f, OhneCode) for f in logging.getLogger("uvicorn.access").filters):
    logging.getLogger("uvicorn.access").addFilter(OhneCode())

# a restart forgets every pickup code: what lies in TMP can never be fetched any more
try:
    for _n in os.listdir(TMP):
        _weg(os.path.join(TMP, _n))
except OSError:
    pass
