"""Spark-Begleiter (plan plaene/schreibhilfe.md, „für alles“): a small program in the Windows notification area
and the Mac menu bar (tools/begleiter/windows, tools/begleiter/mac) with these parts, each on or off per device:

    write    Schreibhilfe on the marked text (schreib.py, needs its switches too)
    ask      Frag Spark: a question as text, the answer as text (chat.text_ask, like Siri's shortcut)
    dictate  Diktieren: a recording becomes text at the cursor (admin.test_asr)
    notes    Meldungen: the Spark's notes as system notifications (push.py picks "desk" like the Android app)
    status   the icon shows whether the Spark answers and whether a Notaus holds
    notaus   the profile's own Notaus (notaus.post_mine), never lifting it

Off until the admin switches chat.desk on (Funktionen → Spark-Begleiter) and the profile its own desk_on
(Ich → Begleiter); guests never. Which parts a device has is set centrally in the panel (Ich → Begleiter),
per device, and reaches the program with its next poll (rev). Hotkeys are the program's own business.

The program gets its own device key (scope "desk", profiles.DESK_PATHS) through a one-time code
("<address>#begleiter=XXXX-XXXX", schreib.new_code), good only for its paths and only for its parts. Texts are
data: nothing here acts on them; the answers come from the normal assistant with its own rules.

    browser login (own profile):
    GET    /api/profile/desk                    the devices, their settings, what is allowed
    POST   /api/profile/desk/pair {base}        a setup line (confirmation code first)
    PUT    /api/profile/desk/devices/{did}      one device's settings
    DELETE /api/profile/desk/devices/{did}      remove a device (its key stops at once)
    program:
    POST   /api/desk/pair {code, name, kind}    -> {"key", "profile"}
    GET    /api/desk/config                     -> parts, write defaults, rev
    GET    /api/desk/poll?after=n               -> rev, notes, Notaus stage (also the "online" mark)
    POST   /api/desk/ask {text, tz?}            -> {"answer"}
    POST   /api/desk/dictate (multipart file)   -> {"text"}
    POST   /api/desk/notaus {}                  -> {"on": true}
    GET    /api/desk/update?arch=x64|arm64|mac  -> the newer program file the Spark keeps (see below)

Updates: GitHub Actions publish each build with begleiter.json (version, and per arch name, size, SHA-256) in
the releases begleiter-windows and begleiter-mac. The Spark fetches the newest one once a day for the kinds
that are paired (only GitHub's download addresses, size and SHA-256 checked, else nothing is kept) and keeps
it in STATE/begleiter. A program tells its version and arch on every config and poll; when the Spark keeps a
newer one, config names it (version, size, SHA-256) and /api/desk/update hands out the file. The program
installs only after a click and only when size and SHA-256 match. Nothing comes from anywhere else.
"""
import hashlib
import asyncio
import json
import os
import re
import threading
import time

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

import features
import guard
import notaus
import profiles
import schreib
from common import load_config
from core import assistant, auth, browser_profile, confirm_code

router = APIRouter()
PARTS = ("write", "ask", "dictate", "notes", "status", "notaus")
PART_NAMES = {"write": "Schreibhilfe", "ask": "Frag Spark", "dictate": "Diktieren", "notes": "Meldungen",
              "status": "Zustandspunkt", "notaus": "Mein Notaus"}
KINDS = {"windows": "Windows", "mac": "Mac"}
MAX_DEVICES = 10
MAX_BODY = 8 * 1024
MAX_AUDIO = 3 * 1024 * 1024       # request body of a dictation (60 s of 16 kHz mono WAV is 1.9 MB; panel.py)
POLL = 30
ONLINE = 120               # seconds after the last poll a device counts as online
NOTE_SECONDS = 6 * 3600    # notes wait this long for the program
NOTE_MAX = 30
DICT_LANGS = ("auto", "de", "en", "fr", "es", "it", "nl")
RELEASES = {"windows": "https://github.com/db9979/speech-on-dgx-spark/releases/tag/begleiter-windows",
            "mac": "https://github.com/db9979/speech-on-dgx-spark/releases/tag/begleiter-mac"}
# a new device: writing help, questions, notes and the state on; dictation and the Notaus button only on request
DEFAULT = {"parts": {"write": True, "ask": True, "dictate": False, "notes": True, "status": True, "notaus": False},
           "write": {"art": "korrigieren", "sprache": "en", "wunsch": "", "arts": list(schreib.ARTS), "preview": True},
           "dictate": {"sprache": "auto"}, "autostart": True}

COFFEE = "https://buymeacoffee.com/zquu1xu570"
# updates: arch -> (platform, file key in begleiter.json); platform -> release tag
ARCHS = {"x64": ("windows", "x64"), "arm64": ("windows", "arm64"), "mac": ("mac", "mac")}
TAGS = {"windows": "begleiter-windows", "mac": "begleiter-mac"}
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
UPD_DIR = os.path.join(STATE, "begleiter")
MAX_FILE = 150 * 1024 * 1024
MAX_META = 4096
FETCH_EVERY = 24 * 3600
VERSION_RE = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,5}")
FILE_RE = re.compile(r"[\w.\-]{1,80}")

_lock = threading.Lock()
_info = {}                 # device id -> {"version", "arch"} as the program last said
_upd = {"checked": {}, "error": {}}
_seen = {}                 # device id -> last poll
_notes = {}                # uid -> [{"n", "t", "title", "body", "tag"}]
_seq = {}


def _file():
    return profiles._path("begleiter.json")


def _load():
    try:
        with open(_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def admin_on():
    return features.admin_on("begleiter")


def allowed(uid):
    return bool(uid) and features.allowed("begleiter", uid)


profiles.DESK_GATE[0] = allowed


def may(uid):
    """The parts the switches allow at all for this profile (the writing help has its own)."""
    return {p: (schreib.allowed(uid) if p == "write" else True) for p in PARTS}


def clean(cfg):
    """A device's settings, every value checked; anything unknown or wrong falls back to the default."""
    cfg = cfg if isinstance(cfg, dict) else {}
    parts = cfg.get("parts") if isinstance(cfg.get("parts"), dict) else {}
    w = cfg.get("write") if isinstance(cfg.get("write"), dict) else {}
    dw = DEFAULT["write"]
    arts = [a for a in (w.get("arts") if isinstance(w.get("arts"), list) else dw["arts"]) if a in schreib.ARTS]
    wish = schreib.CTRL.sub("", str(w.get("wunsch") or ""))[:schreib.MAX_WISH] if isinstance(w.get("wunsch"), str) else ""
    d = cfg.get("dictate") if isinstance(cfg.get("dictate"), dict) else {}
    return {"parts": {p: parts[p] if isinstance(parts.get(p), bool) else DEFAULT["parts"][p] for p in PARTS},
            "write": {"art": w.get("art") if w.get("art") in schreib.ARTS and w.get("art") != "antwort" else dw["art"],
                      "sprache": w.get("sprache") if w.get("sprache") in schreib.LANGS and w.get("sprache") != "auto"
                      else dw["sprache"],
                      "wunsch": wish, "arts": arts or ["korrigieren"],
                      "preview": w["preview"] if isinstance(w.get("preview"), bool) else True},
            "dictate": {"sprache": d.get("sprache") if d.get("sprache") in DICT_LANGS else "auto"},
            "autostart": cfg["autostart"] if isinstance(cfg.get("autostart"), bool) else True}


def device_cfg(did):
    """(settings, rev) of one device."""
    e = _load().get(did) or {}
    return clean(e.get("cfg")), int(e.get("rev") or 1)


def _save_cfg(did, uid, cfg):
    with _lock:
        d = _load()
        rev = int((d.get(did) or {}).get("rev") or 0) + 1
        d[did] = {"uid": uid, "cfg": clean(cfg), "rev": rev}
        mine = {x["id"] for x in profiles._load()["devices"]}
        d = {k: v for k, v in d.items() if k in mine}      # removed devices go
        profiles._write(_file(), d)
    return rev


def devices(uid):
    return [x for x in profiles.own_devices(uid) if x.get("desk")]


def part_on(uid, did, part):
    """May this device use this part now: the switches allow it and the device has it on."""
    if not allowed(uid) or not may(uid).get(part):
        return False
    return bool(device_cfg(did)[0]["parts"].get(part))


def kind_of(name):
    """"Begleiter Windows" / "Begleiter Mac" for logs and Zustand → Live (the device's own name stays out)."""
    m = re.match(r"Begleiter (\w+)", str(name or ""))
    return "Begleiter " + (m.group(1) if m and m.group(1) in KINDS.values() else "")


def _live(text):
    try:
        import live
        live.event("Begleiter", text)
    except Exception:
        pass


# ---------------------------------------------------------------- notes (push.py, kind "desk")
def reachable(uid, now=None):
    """A device of the profile with "Meldungen" polled lately."""
    now = time.time() if now is None else now
    if not allowed(uid):
        return False
    return any(now - _seen.get(x["id"], -1e12) < ONLINE and part_on(uid, x["id"], "notes") for x in devices(uid))


def keep(uid, title, body, tag="", now=None):
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
        box = [x for x in _notes.get(uid, []) if now - x["t"] < NOTE_SECONDS]
        _notes[uid] = box
        return [{k: x[k] for k in ("n", "title", "body", "tag")} for x in box if x["n"] > after], _seq.get(uid, 0)


# ---------------------------------------------------------------- the panel (own browser login)
def _need(prof):
    if not allowed(prof["id"]):
        raise HTTPException(403, "Der Spark-Begleiter ist aus (Funktionen → Spark-Begleiter, Ich → Begleiter).")
    return prof


async def _body(request, limit=MAX_BODY):
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > limit:
        raise HTTPException(413, "too large")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise HTTPException(413, "too large")
    try:
        body = json.loads(bytes(raw) or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    return body if isinstance(body, dict) else {}


@router.get("/api/profile/desk", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(browser_profile)):
    uid = prof["id"]
    now = time.time()
    out = []
    for x in devices(uid):
        cfg, rev = device_cfg(x["id"])
        out.append({"id": x["id"], "name": x["name"], "created": x.get("created"),
                    "online": now - _seen.get(x["id"], -1e12) < ONLINE, "cfg": cfg,
                    "version": (_info.get(x["id"]) or {}).get("version", "")})
    return {"on": allowed(uid), "allowed": may(uid), "devices": out, "minutes": schreib.CODE_SECONDS // 60,
            "downloads": RELEASES, "arts": [{"id": k, "de": v[0], "en": v[1]} for k, v in schreib.ARTS.items()
                                            if k != "antwort"],
            "langs": [{"id": k, "de": v[0], "en": v[1]} for k, v in schreib.LANGS.items() if k != "auto"]}


@router.post("/api/profile/desk/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(browser_profile)):
    _need(prof)
    guard.limit(request, "desk", prof["id"])
    body = await _body(request)
    base = schreib._base(body.get("base"))
    if len(devices(prof["id"])) >= MAX_DEVICES:
        raise HTTPException(409, f"Schon {MAX_DEVICES} Geräte gekoppelt. Erst eines entfernen.")
    await confirm_code(request, prof["id"], prof["name"])   # a new way into the profile
    code = schreib.new_code(prof["id"], what="begleiter")
    shown = code[:4] + "-" + code[4:]
    print("begleiter: Einrichtungscode erzeugt", flush=True)
    return {"setup": f"{base}#begleiter={shown}", "code": shown, "minutes": schreib.CODE_SECONDS // 60}


@router.put("/api/profile/desk/devices/{did}", dependencies=[Depends(assistant)])
async def profile_set(did: str, request: Request, prof=Depends(browser_profile)):
    _need(prof)
    guard.limit(request, "desk", prof["id"])
    if not any(x["id"] == did for x in devices(prof["id"])):
        raise HTTPException(404, "no such device")
    body = await _body(request)
    _save_cfg(did, prof["id"], body.get("cfg"))
    _live("Einstellungen eines Geräts geändert")
    return profile_get(prof)


@router.delete("/api/profile/desk/devices/{did}", dependencies=[Depends(assistant)])
def profile_unpair(did: str, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in devices(prof["id"])):
        raise HTTPException(404, "no such device")
    profiles.delete_device(did)
    with _lock:
        d = _load()
        if d.pop(did, None) is not None:
            profiles._write(_file(), d)
    _seen.pop(did, None)
    _live("Gerät entkoppelt")
    print("begleiter: Gerät entkoppelt", flush=True)
    return profile_get(prof)


# ---------------------------------------------------------------- the program (key scope "desk")
@router.post("/api/desk/pair")
async def program_pair(request: Request):
    """The program's first contact: the one-time code gives it its own key (scope "desk")."""
    guard.limit(request, "pair")
    body = await _body(request)
    kind = body.get("kind")
    name = str(body.get("name") or "").strip()
    if kind not in KINDS:
        raise HTTPException(400, "kind: " + ", ".join(KINDS))
    if not schreib.DEVNAME.fullmatch(name):
        name = KINDS[kind]
    uid = schreib.take_code(body.get("code"), what="begleiter")
    prof = uid and profiles.by_id(uid)
    if not prof or not allowed(uid):
        raise HTTPException(400, "Der Einrichtungscode passt nicht oder ist abgelaufen. Im Panel einen neuen holen.")
    if len(devices(uid)) >= MAX_DEVICES:
        raise HTTPException(409, "Zu viele Geräte für dieses Profil.")
    key = profiles.add_device(f"Begleiter {KINDS[kind]} · {name}", uid, scope="desk")
    h = hashlib.sha256(key.encode()).hexdigest()
    did = next((x["id"] for x in profiles._load()["devices"] if x.get("token") == h), None)
    if did:
        _save_cfg(did, uid, DEFAULT)
    _live(f"Gerät gekoppelt ({KINDS[kind]})")
    print(f"begleiter: Gerät gekoppelt ({KINDS[kind]})", flush=True)
    return {"key": key, "profile": prof["name"]}


def _program(request):
    """(profile, device) of a request from a paired program; 401 for anything else."""
    prof = profiles.current(request)
    dev = profiles.device(request) if prof else None
    if not prof or not dev or dev["scope"] != "desk":
        raise HTTPException(401, "Der Spark kennt dieses Gerät nicht mehr. Neu koppeln.")
    return prof, dev


def _part(prof, dev, part):
    if not part_on(prof["id"], dev["id"], part):
        raise HTTPException(403, f"{PART_NAMES[part]} ist für dieses Gerät aus (Ich → Begleiter).")


@router.get("/api/desk/config", dependencies=[Depends(assistant)])
def program_config(request: Request, version: str = "", arch: str = ""):
    prof, dev = _program(request)
    guard.limit(request, "desk", prof["id"])
    cfg, rev = device_cfg(dev["id"])
    ok = may(prof["id"])
    _tell(dev["id"], version, arch)
    return {"rev": rev, "profile": prof["name"], "poll": POLL, "coffee": COFFEE, "update": newer(arch, version),
            "parts": {p: bool(cfg["parts"][p] and ok[p]) for p in PARTS}, "allowed": ok,
            "write": cfg["write"], "dictate": cfg["dictate"], "autostart": cfg["autostart"],
            "arts": [{"id": k, "de": v[0], "en": v[1], "changes": v[4]} for k, v in schreib.ARTS.items() if k != "antwort"],
            "langs": [{"id": k, "de": v[0], "en": v[1]} for k, v in schreib.LANGS.items() if k != "auto"]}


@router.get("/api/desk/poll", dependencies=[Depends(assistant)])
def program_poll(request: Request, after: int = 0, version: str = "", arch: str = ""):
    prof, dev = _program(request)
    guard.limit(request, "desk", prof["id"])
    _seen[dev["id"]] = time.time()
    if len(_seen) > 1000:
        _seen.clear()
    cfg, rev = device_cfg(dev["id"])
    items, last = notes(prof["id"], max(0, min(after, 10 ** 9))) if part_on(prof["id"], dev["id"], "notes") \
        else ([], _seq.get(prof["id"], 0))
    _tell(dev["id"], version, arch)
    up = newer(arch, version)
    return {"rev": rev, "notes": items, "last": last, "notaus": {"level": notaus.level()},
            "update": up["version"] if up else None}


@router.post("/api/desk/ask", dependencies=[Depends(assistant)])
async def program_ask(request: Request):
    prof, dev = _program(request)
    _part(prof, dev, "ask")
    guard.limit(request, "deskask", prof["id"])
    body = await _body(request)
    profiles.used(prof["id"], "desk")
    import chat
    _live("Frage gestellt")
    out = await chat.text_ask(request, prof, {"text": body.get("text"), "tz": body.get("tz")}, "desk")
    return {"answer": str(out.get("answer") or "")}


@router.post("/api/desk/dictate", dependencies=[Depends(assistant)])
async def program_dictate(request: Request, file: UploadFile = File(...), sprache: str = Form("auto")):
    prof, dev = _program(request)
    _part(prof, dev, "dictate")
    import admin
    if sprache not in DICT_LANGS:
        sprache = "auto"
    profiles.used(prof["id"], "desk")
    out = await admin.test_asr(request, file, sprache, "", "")
    if not isinstance(out, dict):     # the recognition's own answer, passed on as it came
        try:
            out = json.loads(out.body) if out.status_code == 200 else None
        except (AttributeError, ValueError):
            out = None
    if not isinstance(out, dict):
        raise HTTPException(502, "Die Spracherkennung hat nicht geantwortet.")
    text = str(out.get("text") or "")[:20000]
    _live(f"Diktat ({len(text)} Zeichen)")
    return {"text": str(text or "")}


@router.post("/api/desk/notaus", dependencies=[Depends(assistant)])
async def program_notaus(request: Request):
    """Mein Notaus from the program (the same as Ich → Sicherheit); lifting it only in the browser with the PIN."""
    prof, dev = _program(request)
    _part(prof, dev, "notaus")
    _live("Mein Notaus vom Begleiter")
    r = await notaus.post_mine(request)
    return {"on": bool(json.loads(r.body or b"{}").get("mine", {}).get("on"))} if hasattr(r, "body") else {"on": True}


# ---------------------------------------------------------------- updates (begleiter.json from GitHub Actions)
def _vt(v):
    return tuple(int(x) for x in v.split("."))


def _tell(did, version, arch):
    """What the program said about itself (memory only; the panel shows the version)."""
    if VERSION_RE.fullmatch(str(version or "")) and arch in ARCHS:
        if len(_info) > 1000:
            _info.clear()
        _info[did] = {"version": version, "arch": arch}


def kept(platform):
    """{"version", "files": {key: {"name", "size", "sha256"}}} the Spark keeps for this platform, or None."""
    try:
        with open(os.path.join(UPD_DIR, platform, "begleiter.json")) as f:
            m = json.load(f)
        if not VERSION_RE.fullmatch(str(m.get("version", ""))) or not isinstance(m.get("files"), dict):
            return None
        files = {}
        for k, v in m["files"].items():
            path = os.path.join(UPD_DIR, platform, str(v.get("name", "")))
            if FILE_RE.fullmatch(str(v.get("name", ""))) and os.path.isfile(path) \
                    and os.path.getsize(path) == v.get("size") and re.fullmatch(r"[0-9a-f]{64}", str(v.get("sha256", ""))):
                files[k] = {"name": v["name"], "size": v["size"], "sha256": v["sha256"]}
        return {"version": m["version"], "files": files}
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def newer(arch, version):
    """{"version", "size", "sha256"} when the Spark keeps a newer program for this arch than `version`, else None.
    A program without a proper version (a development build) never gets one."""
    if arch not in ARCHS or not VERSION_RE.fullmatch(str(version or "")):
        return None
    platform, key = ARCHS[arch]
    m = kept(platform)
    f = m and m["files"].get(key)
    if not f or _vt(m["version"]) <= _vt(version):
        return None
    return {"version": m["version"], "size": f["size"], "sha256": f["sha256"]}


def _allowed_download(url):
    test = os.environ.get("SPEECH_SPARK_GITHUB_API")
    if test and url.startswith(test.rstrip("/") + "/"):
        return True
    return bool(re.fullmatch(r"https://github\.com/[\w.\-]+/[\w.\-]+/releases/download/[^\s?#]+", url))


async def _download(c, url, limit, path=None):
    """GitHub download with a byte limit; into `path` when given (big files), else returned."""
    if not _allowed_download(url):
        raise ValueError("Download-Adresse ist nicht von GitHub.")
    out, n, h = bytearray(), 0, hashlib.sha256()
    f = open(path, "wb") if path else None
    try:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                n += len(chunk)
                if n > limit:
                    raise ValueError("Datei ist größer als angegeben, nichts übernommen.")
                h.update(chunk)
                if f:
                    f.write(chunk)
                else:
                    out += chunk
    finally:
        if f:
            f.close()
    return (n, h.hexdigest()) if path else bytes(out)


def platforms():
    """The platforms with at least one paired Begleiter (only those are fetched)."""
    names = [str(x.get("name") or "") for x in profiles._load()["devices"] if x.get("scope") == "desk"]
    return [p for p, k in (("windows", "Windows"), ("mac", "Mac")) if any(n.startswith(f"Begleiter {k} ") for n in names)]


async def fetch(platform, c=None):
    """Takes the newest build of this platform when it is newer than the kept one; every file must match size
    and SHA-256 of its begleiter.json. Returns the version the Spark keeps now."""
    repo = load_config().get("chat", {}).get("esp32_repo") or "db9979/speech-on-dgx-spark"
    own = c is None
    c = c or httpx.AsyncClient(timeout=300, follow_redirects=True)
    folder = os.path.join(UPD_DIR, platform)
    try:
        api = os.environ.get("SPEECH_SPARK_GITHUB_API", "https://api.github.com")
        r = await c.get(f"{api}/repos/{repo}/releases/tags/{TAGS[platform]}")
        if r.status_code == 404:
            raise ValueError("Im Repo gibt es diese Version noch nicht.")
        r.raise_for_status()
        assets = {a.get("name"): a.get("browser_download_url", "") for a in r.json().get("assets", [])}
        if "begleiter.json" not in assets:
            raise ValueError("Die Version hat kein begleiter.json.")
        m = json.loads(await _download(c, assets["begleiter.json"], MAX_META))
        ver, files = str(m.get("version", "")), m.get("files")
        if not VERSION_RE.fullmatch(ver) or not isinstance(files, dict) or not files:
            raise ValueError("begleiter.json ist ungültig.")
        want = {k for p, k in ARCHS.values() if p == platform}
        clean = {}
        for k, v in files.items():
            if k not in want or not isinstance(v, dict):
                continue
            name, size, sha = str(v.get("name", "")), v.get("size"), str(v.get("sha256", ""))
            if not (FILE_RE.fullmatch(name) and name in assets and isinstance(size, int) and 0 < size <= MAX_FILE
                    and re.fullmatch(r"[0-9a-f]{64}", sha)):
                raise ValueError("begleiter.json ist ungültig.")
            clean[k] = {"name": name, "size": size, "sha256": sha}
        cur = kept(platform)
        if cur and _vt(cur["version"]) >= _vt(ver) and set(cur["files"]) >= set(clean):
            return cur["version"]
        os.makedirs(folder, exist_ok=True)
        for k, v in clean.items():
            part = os.path.join(folder, v["name"] + ".part")
            n, h = await _download(c, assets[v["name"]], v["size"], part)
            if n != v["size"] or h != v["sha256"]:
                os.remove(part)
                raise ValueError(f"{v['name']}: Prüfsumme passt nicht, nichts übernommen.")
        old = {f["name"] for f in (cur or {}).get("files", {}).values()}
        for v in clean.values():
            os.replace(os.path.join(folder, v["name"] + ".part"), os.path.join(folder, v["name"]))
        with open(os.path.join(folder, "begleiter.json.part"), "w") as f:
            json.dump({"version": ver, "files": clean}, f)
        os.replace(os.path.join(folder, "begleiter.json.part"), os.path.join(folder, "begleiter.json"))
        for name in old - {v["name"] for v in clean.values()}:
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
        _live(f"Neue Version geholt ({'Windows' if platform == 'windows' else 'Mac'} {ver})")
        print(f"begleiter: {platform} {ver} geholt", flush=True)
        return ver
    finally:
        if own:
            await c.aclose()


async def check(platform):
    err = ""
    try:
        await fetch(platform)
    except Exception as e:
        err = str(e)[:200]
        print("begleiter: update check", platform, type(e).__name__, err, flush=True)
    _upd["checked"][platform] = time.time()
    _upd["error"][platform] = err
    return err


async def fetch_loop():
    while True:
        await asyncio.sleep(90)
        try:
            if admin_on() and not notaus.blocks("internet"):
                for p in platforms():
                    if time.time() - _upd["checked"].get(p, 0) > FETCH_EVERY:
                        await check(p)
        except Exception as e:
            print("begleiter: loop", type(e).__name__, e, flush=True)


@router.get("/api/desk/update", dependencies=[Depends(assistant)])
def program_update(request: Request, arch: str = ""):
    prof, dev = _program(request)
    guard.limit(request, "deskupd", prof["id"])
    if arch not in ARCHS:
        raise HTTPException(400, "arch: " + ", ".join(ARCHS))
    platform, key = ARCHS[arch]
    m = kept(platform)
    f = m and m["files"].get(key)
    if not f:
        raise HTTPException(404, "Der Spark hat keine neue Version.")
    _live(f"Update geladen ({'Windows' if platform == 'windows' else 'Mac'} {m['version']})")
    return FileResponse(os.path.join(UPD_DIR, platform, f["name"]), media_type="application/octet-stream",
                        filename=f["name"], headers={"Cache-Control": "no-store"})


@router.get("/api/admin/desk", dependencies=[Depends(auth)])
def admin_get():
    return {p: {"version": (kept(p) or {}).get("version"), "checked": _upd["checked"].get(p),
                "error": _upd["error"].get(p, "")} for p in TAGS} | {"paired": platforms()}


@router.post("/api/admin/desk/fetch", dependencies=[Depends(auth)])
async def admin_fetch(request: Request):
    guard.limit(request, "deskupd", admin=True)
    if notaus.blocks("internet"):
        raise HTTPException(503, "Notaus: kein Internet.")
    for p in platforms() or list(TAGS):
        await check(p)
    return admin_get()
