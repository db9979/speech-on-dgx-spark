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

Admin switch chat.android and the profile's android_on, both off at first; never guests.
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
VERSION = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}")
UA = re.compile(r"SparkAndroid/(\d{1,3}\.\d{1,3}\.\d{1,3})")

_tokens = {}              # sha256(token) -> {"uid", "t", "n"}
_notes = {}               # uid -> [{"n", "t", "title", "body", "tag"}]
_seq = {}                 # uid -> last note number
_polled = {}              # uid -> time of the app's last question
_state = {"checked": 0.0, "error": ""}


def admin_on():
    return features.admin_on("android")


def profile_on(uid):
    return features.profile_on("android", uid)


def allowed(uid):
    return features.allowed("android", uid)


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


async def fetch_apk(c=None):
    """Takes the newest release android-v… of the repo when it is newer than the kept one; the APK must match
    the SHA-256 and size in its android.json. Returns the version the Spark keeps now."""
    repo = load_config().get("chat", {}).get("esp32_repo") or "db9979/speech-on-dgx-spark"
    own = c is None
    c = c or httpx.AsyncClient(timeout=120, follow_redirects=True)
    try:
        api = os.environ.get("SPEECH_SPARK_GITHUB_API", "https://api.github.com")
        r = await c.get(f"{api}/repos/{repo}/releases", params={"per_page": 30})
        r.raise_for_status()
        rel = next((x for x in r.json() if str(x.get("tag_name", "")).startswith("android-v")
                    and not x.get("draft") and not x.get("prerelease")), None)
        if not rel:
            raise ValueError("Im Repo gibt es noch keine Android-App (android-v…).")
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
    err = ""
    try:
        await fetch_apk()
    except Exception as e:
        err = str(e)[:200]
        print("android: app check", type(e).__name__, err, flush=True)
    _state.update(checked=time.time(), error=err)
    return err


async def fetch_loop():
    while True:
        await asyncio.sleep(90)
        try:
            if admin_on() and time.time() - _state["checked"] > FETCH_EVERY:
                await _check()
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
    return n


def notes(uid, after, now=None):
    now = time.time() if now is None else now
    with _lock:
        _polled[uid] = now
        box = [x for x in _notes.get(uid, []) if now - x["t"] < NOTE_SECONDS]
        _notes[uid] = box
        return [dict(x) for x in box if x["n"] > after], _seq.get(uid, 0)


# ---------------------------------------------------------------- endpoints
def _on(prof=Depends(browser_profile)):
    if not admin_on():
        raise HTTPException(403, "the Android app is turned off")
    return prof


@router.get("/api/profile/android", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    return {"enabled": admin_on(), "on": profile_on(prof["id"]), "app": meta() if admin_on() else None,
            "minutes": TOKEN_SECONDS // 60, "notes": reachable(prof["id"])}


@router.post("/api/profile/android/link", dependencies=[Depends(assistant)])
async def profile_link(request: Request, prof=Depends(_on)):
    """A download link with a one-time token, as QR code for the phone's camera."""
    guard.limit(request, "android", prof["id"])
    body = await _json(request)
    if not profile_on(prof["id"]):
        raise HTTPException(403, "Erst „Android-App für mich“ einschalten.")
    if not meta():
        raise HTTPException(409, "Der Spark hat die App noch nicht geholt.")
    url = f"{_base(body)}/android/spark.apk?t={new_token(prof['id'])}"
    try:
        import mfa
        svg = mfa._qr_svg(url)
    except Exception:
        svg = ""
    print("android: download link made for", prof["name"], flush=True)
    return {"url": url, "qr": svg, "minutes": TOKEN_SECONDS // 60}


@router.get("/api/android/notes", dependencies=[Depends(assistant)])
def app_notes(request: Request, after: int = 0, prof=Depends(browser_profile)):
    """The app's question every 15 minutes: notes since number `after` (the app keeps the last one)."""
    guard.limit(request, "android", prof["id"])
    if not allowed(prof["id"]):
        raise HTTPException(403, "the Android app is turned off")
    items, last = notes(prof["id"], max(0, min(after, 10 ** 9)))
    m = meta()
    return {"notes": [{"n": x["n"], "title": x["title"], "body": x["body"], "tag": x["tag"]} for x in items],
            "last": last, "app": {"version": m["version"], "code": m["code"]} if m else None}


@router.get("/api/admin/android", dependencies=[Depends(auth)])
def admin_get():
    return {"app": meta(), "checked": _state["checked"], "error": _state["error"]}


@router.post("/api/admin/android/fetch", dependencies=[Depends(auth)])
async def admin_fetch(request: Request):
    guard.limit(request, "android", admin=True)
    err = await _check()
    if err:
        raise HTTPException(502, err)
    return admin_get()


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
