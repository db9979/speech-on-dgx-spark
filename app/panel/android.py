"""The Android app "Spark" (android/ in the repo, plan plaene/handy-wie-app.md 4a): a thin shell around the page.

The app shows the panel in a WebView (the page looks like the iPhone app on phones, appview.js) and adds only
what a page cannot do: notes while the app is closed, the assistant button, sharing text to the Spark and
the hint that a new app version is there. It signs in like a browser (name and PIN in the page); its own
requests carry that login's cookie, never a key of their own.

The APK comes from no store: GitHub Actions builds and signs it as release android-v<version> with
android.json (version, code, size, SHA-256). The Spark fetches the newest one (like the speaker firmware,
esp32.py), checks the SHA-256 and keeps it in STATE/android. A profile gets a download link with a one-time
token (TOKEN_SECONDS, at most TOKEN_USES downloads, only its hash in memory), as QR code for the phone's
camera. Notes: the app asks /api/android/notes every 15 minutes; push.send picks it like the iPhone app when
the app asked lately. The notes wait in memory only (NOTE_SECONDS, NOTE_MAX per profile).

"Mitteilungen sofort" (chat.android_live, off; the profile's preference android_live, on unless switched off;
plan messenger.md): the app keeps one connection open (a foreground service with a quiet lasting notification)
and asks /api/android/wait, which answers as soon as a note is there or after WAIT_SECONDS with nothing; then it asks
again. No Google service.

"Update in der App" (chat.android_update, off; plan android-update-in-app.md): the app (from 1.3.0) asks
/api/profile/android which version the Spark keeps, loads it from GET /api/android/apk with its sign-in, checks
SHA-256, package name, version code and signing certificate itself and hands it to Android's package installer,
which checks the signature against the installed app once more and asks the person. Only the own Spark, never
GitHub. The version each profile's app runs (from its user agent) is kept in memory for Zustand → Geräte-Updates.

Admin switch chat.android, off at first; released it works for every profile the admin did not block (chat.deny);
never guests.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

import features
import guard
import notaus
import profiles
from common import load_config
from core import assistant, auth, own_profile
from account import browser_profile

router = APIRouter()
_lock = threading.Lock()

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
DIR = os.path.join(STATE, "android")
APK = os.path.join(DIR, "spark.apk")
META = os.path.join(DIR, "android.json")
MAX_APK = 40 * 1024 * 1024
MAX_META = 4096
MAX_BODY = 1024
FETCH_EVERY = 24 * 3600
TOKEN_SECONDS = 30 * 60
TOKEN_USES = 5            # the phone's browser may ask twice for one download
MAX_TOKENS = 50
NOTE_SECONDS = 24 * 3600
NOTE_MAX = 30
POLLED_KEEP = 3 * 3600    # the app asks every 15 minutes; after 3 hours without, notes go elsewhere
WAIT_SECONDS = 50         # /api/android/wait holds the question this long (below the usual 60 s of a proxy)
MAX_WAITERS = 2           # open waits per profile (a second phone); the oldest gives way
VERSION = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}")
UA = re.compile(r"SparkAndroid/(\d{1,3}\.\d{1,3}\.\d{1,3})")

_tokens = {}              # sha256(token) -> {"uid", "t", "n"}
_notes = {}               # uid -> [{"n", "t", "title", "body", "tag"}]
_seq = {}                 # uid -> last note number
_polled = {}              # uid -> time of the app's last question
_waiters = {}             # uid -> [(loop, asyncio.Event)] of the open waits
_seen = {}                # uid -> (app version from the user agent, time), for Zustand → Geräte-Updates
SEEN_KEEP = 14 * 24 * 3600
_state = {"checked": 0.0, "error": ""}


def admin_on():
    return features.admin_on("android")


def profile_on(uid):
    return features.profile_on("android", uid)


def allowed(uid):
    return features.allowed("android", uid)


def live_ok(uid):
    """Notes at once over a lasting connection (admin switch, not blocked, the profile's preference)."""
    return features.allowed("androidlive", uid)


def update_ok(uid):
    """The app may load and install its own update (admin switch android_update, not blocked)."""
    return features.allowed("androidupdate", uid)


def _ver(v):
    return tuple(int(x) for x in v.split(".")) if v and VERSION.fullmatch(v) else ()


def newer(have, kept):
    """True when the Spark keeps a newer version than `have`, None when one of them is unknown."""
    a, b = _ver(have), _ver(kept)
    return (b > a) if a and b else None


def saw(request, prof, now=None):
    """Remembers which app version the profile's app runs (user agent "SparkAndroid/x.y.z"); logs a change."""
    m = UA.search(request.headers.get("user-agent", ""))
    if not m:
        return
    now = time.time() if now is None else now
    v = m.group(1)
    with _lock:
        old = _seen.get(prof["id"], ("", 0))[0]
        _seen[prof["id"]] = (v, now)
    if old != v:
        print("android: app version", old or "first", "->", v, "for", profiles.log_name(prof), flush=True)


def seen(uid, now=None):
    """The app version the profile's app named lately, "" when it did not ask in SEEN_KEEP."""
    now = time.time() if now is None else now
    with _lock:
        v, t = _seen.get(uid, ("", 0))
    return v if now - t < SEEN_KEEP else ""


def live_count():
    """Open waits (Zustand → Live): a number only."""
    with _lock:
        return sum(len(v) for v in _waiters.values())


def from_app(request):
    """The app's WebView names itself in the user agent (only used to send notes to the device used last)."""
    return bool(UA.search(request.headers.get("user-agent", "")))


# ---------------------------------------------------------------- the APK on the Spark
def meta():
    """{"version", "code", "size", "sha256"} of the APK the Spark keeps, None without one."""
    try:
        with open(META) as f:
            m = json.load(f)
        if not (VERSION.fullmatch(str(m.get("version", ""))) and isinstance(m.get("code"), int)
                and re.fullmatch(r"[0-9a-f]{64}", str(m.get("sha256", ""))) and os.path.isfile(APK)):
            return None
        return {"version": m["version"], "code": m["code"], "size": os.path.getsize(APK), "sha256": m["sha256"]}
    except (OSError, ValueError, AttributeError):
        return None


def _allowed_download(url):
    """Only GitHub's own download addresses (or the test server set by the self-test)."""
    test = os.environ.get("SPEECH_SPARK_GITHUB_API")
    if test and url.startswith(test.rstrip("/") + "/"):
        return True
    return bool(re.fullmatch(r"https://github\.com/[\w.\-]+/[\w.\-]+/releases/download/[^\s?#]+", url))


async def _download(c, url, limit):
    if not _allowed_download(url):
        raise ValueError("Download-Adresse ist nicht von GitHub.")
    out = bytearray()
    async with c.stream("GET", url) as r:
        r.raise_for_status()
        async for chunk in r.aiter_bytes():
            out += chunk
            if len(out) > limit:
                raise ValueError("Datei ist größer als erlaubt, nichts übernommen.")
    return bytes(out)


class NoRelease(ValueError):
    """The repo has no android-v… release yet: a state to show, not a failure of the Spark."""


async def fetch_apk(c=None):
    """Takes the newest release android-v… of the repo when it is newer than the kept one; the APK must match
    the SHA-256 and size in its android.json. Returns the version the Spark keeps now."""
    repo = load_config().get("chat", {}).get("esp32_repo") or "db9979/speech-on-dgx-spark"
    own = c is None
    c = c or httpx.AsyncClient(timeout=120, follow_redirects=True)
    try:
        api = os.environ.get("SPEECH_SPARK_GITHUB_API", "https://api.github.com")
        import ghtoken
        r = await ghtoken.get(c, f"{api}/repos/{repo}/releases", params={"per_page": 30})
        r.raise_for_status()
        rel = next((x for x in r.json() if str(x.get("tag_name", "")).startswith("android-v")
                    and not x.get("draft") and not x.get("prerelease")), None)
        if not rel:
            raise NoRelease("Im Repo gibt es noch keine Android-App (android-v…): einmal den Signierschlüssel anlegen und die Aktion „Android app“ starten, siehe Anleitung.")
        assets = {a.get("name"): a.get("browser_download_url", "") for a in rel.get("assets", [])}
        if "android.json" not in assets or "spark.apk" not in assets:
            raise ValueError("Die Version hat kein android.json oder spark.apk.")
        m = json.loads(await _download(c, assets["android.json"], MAX_META))
        ver, code, sha, size = str(m.get("version", "")), m.get("code"), str(m.get("sha256", "")), m.get("size")
        if not (VERSION.fullmatch(ver) and isinstance(code, int) and 0 < code < 10 ** 9
                and re.fullmatch(r"[0-9a-f]{64}", sha) and isinstance(size, int) and 0 < size <= MAX_APK):
            raise ValueError("android.json ist ungültig.")
        cur = meta()
        if cur and cur["code"] >= code:
            return cur["version"]
        data = await _download(c, assets["spark.apk"], size)
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("spark.apk: Prüfsumme passt nicht, nichts übernommen.")
        os.makedirs(DIR, exist_ok=True)
        with open(APK + ".part", "wb") as f:
            f.write(data)
        os.replace(APK + ".part", APK)
        with open(META + ".part", "w") as f:
            json.dump({"version": ver, "code": code, "sha256": sha}, f)
        os.replace(META + ".part", META)
        print("android: app", ver, "taken", flush=True)
        return ver
    finally:
        if own:
            await c.aclose()


async def _check():
    """Returns (error text, whether it is only "no release yet")."""
    err, none = "", False
    try:
        await fetch_apk()
    except NoRelease as e:
        err, none = str(e)[:200], True
    except Exception as e:
        err = str(e)[:200]
        print("android: app check failed:", type(e).__name__, err, flush=True)
    _state.update(checked=time.time(), error=err)
    return err, none


async def fetch_loop():
    while True:
        await asyncio.sleep(90)
        try:
            if admin_on() and not notaus.blocks("internet") and time.time() - _state["checked"] > FETCH_EVERY:
                t0 = time.time()
                err, none = await _check()
                try:
                    import live
                    live.job("Geräte-Updates prüfen", "Geräte-Updates", t0, ok=not err or none)
                except Exception:
                    pass
        except Exception as e:
            print("android: loop", type(e).__name__, e, flush=True)


# ---------------------------------------------------------------- download links
def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _clean(now):
    for k in [k for k, v in _tokens.items() if now - v["t"] > TOKEN_SECONDS or v["n"] >= TOKEN_USES]:
        _tokens.pop(k, None)


def new_token(uid, now=None):
    now = time.time() if now is None else now
    token = secrets.token_urlsafe(24)
    with _lock:
        _clean(now)
        for k in [k for k, v in _tokens.items() if v["uid"] == uid]:
            _tokens.pop(k, None)   # one open link per profile
        if len(_tokens) >= MAX_TOKENS:
            raise HTTPException(429, "Zu viele offene Download-Links. Bitte später noch einmal.")
        _tokens[_hash(token)] = {"uid": uid, "t": now, "n": 0}
    return token


def use_token(token, now=None):
    """The profile id the link was made for while it is valid (counts one download), else None."""
    now = time.time() if now is None else now
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{30,40}", token):
        return None
    h = _hash(token)
    with _lock:
        _clean(now)
        hit = next((k for k in _tokens if hmac.compare_digest(k, h)), None)
        if not hit:
            return None
        _tokens[hit]["n"] += 1
        return _tokens[hit]["uid"]


def _base(body):
    base = str(body.get("base") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?", base):
        raise HTTPException(400, "Adresse: http(s)://name oder http(s)://name:port, ohne Pfad.")
    return base


async def _json(request):
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise HTTPException(413, "too large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY:
            raise HTTPException(413, "too large")
    try:
        d = json.loads(bytes(data) or b"{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


# ---------------------------------------------------------------- notes while the app is closed
def reachable(uid, now=None):
    now = time.time() if now is None else now
    return allowed(uid) and now - _polled.get(uid, -1e12) < POLLED_KEEP


def keep(uid, title, body, tag="", now=None):
    """A note for the profile's Android app; it fetches it with its next question."""
    now = time.time() if now is None else now
    with _lock:
        n = _seq.get(uid, 0) + 1
        _seq[uid] = n
        box = [x for x in _notes.get(uid, []) if now - x["t"] < NOTE_SECONDS]
        box.append({"n": n, "t": now, "title": str(title)[:200], "body": str(body)[:1500], "tag": str(tag)[:20]})
        _notes[uid] = box[-NOTE_MAX:]
        waits = list(_waiters.get(uid, []))
    for loop, ev in waits:   # a waiting app hears it at once (keep may run in any thread)
        try:
            loop.call_soon_threadsafe(ev.set)
        except RuntimeError:
            pass
    return n


def notes(uid, after, now=None):
    now = time.time() if now is None else now
    with _lock:
        _polled[uid] = now
        box = [x for x in _notes.get(uid, []) if now - x["t"] < NOTE_SECONDS]
        _notes[uid] = box
        return [dict(x) for x in box if x["n"] > after], _seq.get(uid, 0)


# ---------------------------------------------------------------- endpoints
def _on(request: Request, prof=Depends(browser_profile)):
    if not admin_on():
        raise HTTPException(403, "the Android app is turned off")
    if request.method not in ("GET", "HEAD", "DELETE") and features.blocked("android", prof["id"]):   # own data: seen and deleted also while blocked
        raise HTTPException(403, "blocked for this profile by the admin (Funktionen → Wer darf was)")
    return prof


@router.get("/api/profile/android", dependencies=[Depends(assistant)])
def profile_get(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    saw(request, prof)
    with _lock:
        waiting = bool(_waiters.get(uid))
    return {"enabled": admin_on(), "on": profile_on(uid), "app": meta() if admin_on() else None,
            "minutes": TOKEN_SECONDS // 60, "notes": reachable(uid), "live_enabled": features.admin_on("androidlive") and not features.blocked("androidlive", uid),
            "live": live_ok(uid), "connected": waiting, "update": update_ok(uid)}


@router.post("/api/profile/android/link", dependencies=[Depends(assistant)])
async def profile_link(request: Request, prof=Depends(_on)):
    """A download link with a one-time token, as QR code for the phone's camera."""
    guard.limit(request, "android", prof["id"])
    body = await _json(request)
    if not profile_on(prof["id"]):
        raise HTTPException(403, "Die Android-App hat der Admin für dein Profil gesperrt (Funktionen → Wer darf was).")
    if not meta():
        raise HTTPException(409, "Der Spark hat die App noch nicht geholt.")
    url = f"{_base(body)}/android/spark.apk?t={new_token(prof['id'])}"
    try:
        import mfa
        svg = mfa._qr_svg(url)
    except Exception:
        svg = ""
    print("android: download link made for", profiles.log_name(prof), flush=True)
    _live_mark("Eingang", "Android-App: Download-Link erstellt")
    return {"url": url, "qr": svg, "minutes": TOKEN_SECONDS // 60}


@router.get("/api/android/notes", dependencies=[Depends(assistant)])
def app_notes(request: Request, after: int = 0, prof=Depends(browser_profile)):
    """The app's question every 15 minutes: notes since number `after` (the app keeps the last one)."""
    guard.limit(request, "android", prof["id"])
    if not allowed(prof["id"]):
        raise HTTPException(403, "the Android app is turned off")
    saw(request, prof)
    return _answer(prof["id"], after)


def _answer(uid, after):
    items, last = notes(uid, max(0, min(after, 10 ** 9)))
    m = meta()
    return {"notes": [{"n": x["n"], "title": x["title"], "body": x["body"], "tag": x["tag"]} for x in items],
            "last": last, "app": {"version": m["version"], "code": m["code"]} if m else None, "live": live_ok(uid),
            "update": update_ok(uid)}


@router.get("/api/android/wait", dependencies=[Depends(assistant)])
async def app_wait(request: Request, after: int = 0, prof=Depends(browser_profile)):
    """The lasting connection: answers as soon as there is a note after `after`, else after WAIT_SECONDS empty.
    403 when the app or "Mitteilungen sofort" is off (the app then ends its connection)."""
    import asyncio
    uid = prof["id"]
    guard.limit(request, "androidwait", uid)
    if not allowed(uid) or not live_ok(uid):
        raise HTTPException(403, "notes at once are turned off")
    saw(request, prof)
    after = max(0, min(after, 10 ** 9))
    if _seq.get(uid, 0) > after or _seq.get(uid, 0) < after:   # something new, or the Spark started over
        return _answer(uid, after)
    loop, ev = asyncio.get_running_loop(), asyncio.Event()
    me = (loop, ev)
    with _lock:
        _polled[uid] = time.time()
        box = _waiters.setdefault(uid, [])
        if len(box) >= MAX_WAITERS:
            old = box.pop(0)
            old[0].call_soon_threadsafe(old[1].set)
        box.append(me)
    try:
        await asyncio.wait_for(ev.wait(), WAIT_SECONDS)
    except asyncio.TimeoutError:
        pass
    finally:
        with _lock:
            box = _waiters.get(uid, [])
            if me in box:
                box.remove(me)
            if not box:
                _waiters.pop(uid, None)
    return _answer(uid, after)


@router.get("/api/admin/android", dependencies=[Depends(auth)])
def admin_get():
    return {"app": meta(), "checked": _state["checked"], "error": _state["error"]}


@router.post("/api/admin/android/fetch", dependencies=[Depends(auth)])
async def admin_fetch(request: Request):
    guard.limit(request, "android", admin=True)
    err, none = await _check()
    if err and not none:   # "no app in the repo yet" is a state the page shows (with 200), not a failed request
        raise HTTPException(502, err)
    return admin_get()


@router.get("/api/android/apk", dependencies=[Depends(assistant)])
def app_apk(request: Request, prof=Depends(browser_profile)):
    """Update in der App: the APK the Spark keeps, for the profile's own app (its sign-in, never a link). The app
    checks the file itself before Android installs it; this only hands out what the Spark checked when fetching."""
    uid = prof["id"]
    guard.limit(request, "android", uid)
    if not update_ok(uid):
        print("android: app update refused for", profiles.log_name(prof), "reason switched off or blocked", flush=True)
        raise HTTPException(403, "Update in der App hat der Admin nicht freigegeben.")
    m = meta()
    if not m:
        print("android: app update refused for", profiles.log_name(prof), "reason no app on the Spark", flush=True)
        raise HTTPException(409, "Der Spark hat die App noch nicht geholt.")
    print("android: app update", m["version"], "sent to", profiles.log_name(prof), flush=True)
    _live_mark("Eingang", "Android-App: Update geladen")
    return FileResponse(APK, media_type="application/vnd.android.package-archive",
                        filename=f"spark-{m['version']}.apk", headers={"Cache-Control": "no-store"})


def apk_response(request: Request, t: str = ""):
    """GET /android/spark.apk?t=…: the app file for whoever holds a valid link (the phone's browser is not
    signed in). Wrong or old links get 404 like a missing file."""
    guard.limit(request, "pair")
    uid = use_token(t)
    m = meta()
    if not uid or not m or not allowed(uid):
        raise HTTPException(404, "Der Download-Link passt nicht oder ist abgelaufen. Im Spark einen neuen holen.")
    return FileResponse(APK, media_type="application/vnd.android.package-archive",
                        filename=f"spark-{m['version']}.apk", headers={"Cache-Control": "no-store"})


def _live_mark(area, text):
    """Zustand → Live: a line under Ereignisse, fixed words only (never the profile's name)."""
    try:
        import live
        live.mark(area, text)
    except Exception:
        pass
