"""Speech on DGX Spark: web panel for config and monitoring."""
import asyncio
import datetime
import json
import os
import re
import hashlib
import hmac
import html.parser
import io
import secrets
import shutil
import subprocess
import sys
import time
import zipfile
from collections import deque

import httpx
import psutil
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from textnorm import guess_language  # noqa: E402
import documents  # noqa: E402
import speakers  # noqa: E402
import calendars  # noqa: E402
import profiles  # noqa: E402
import recall  # noqa: E402
import homeassistant  # noqa: E402
import watch  # noqa: E402
from common import CONFIG_PATH, estimate_gib, journal, load_config, mem_available_gib, quiet_access_log  # noqa: E402

VOICES_DIR = os.environ.get("SPEECH_SPARK_VOICES", "/var/lib/speech-spark/voices")
PASSWORD = os.environ.get("PANEL_PASSWORD", "")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SERVICES = {"asr": "speech-spark-asr", "tts": "speech-spark-tts"}
# units the panel may start/stop/restart (matches /etc/sudoers.d/speech-spark)
UNITS = dict(SERVICES, **{"asr-engine": "speech-spark-asr-engine", "tts-engine": "speech-spark-tts-engine",
                          "tts-design": "speech-spark-tts-design"})
LOG_UNITS = dict(UNITS, panel="speech-spark-panel", update="speech-spark-update")
PREFIX = os.environ.get("SPEECH_SPARK_PREFIX", "/opt/speech-spark")
# asr keys the vLLM engine reads; changing them restarts it
ASR_ENGINE_KEYS = ("model", "engine_port", "engine_mem", "engine_max_seqs")
# tts keys that only the vllm-omni engine reads; changing them restarts the engine
ENGINE_KEYS = ("model", "engine_port", "engine_mem_talker", "engine_mem_code2wav", "engine_max_seqs",
               "engine_max_model_len", "initial_chunk_frames")
DESIGN_KEYS = ("voicedesign_enabled", "voicedesign_model", "voicedesign_port",
               "engine_mem_talker", "engine_mem_code2wav", "engine_max_seqs", "engine_max_model_len", "initial_chunk_frames")
# Units installed by github.com/hasso5703/dgx-spark-qwen38; only one lane runs at a time.
QWEN38_UNITS = ["qwen38-sglang", "qwen38-sglang-1m", "qwen38-flash", "qwen38-image",
                "qwen38-video", "qwen38-llamacpp", "qwen38-keepalive", "qwen38-dashboard"]
LANGS = ["auto", "Chinese", "English", "German", "French", "Spanish", "Italian", "Portuguese",
         "Russian", "Japanese", "Korean", "Dutch", "Polish", "Turkish", "Arabic"]

app = FastAPI(title="Speech on DGX Spark")
security = HTTPBasic(auto_error=False)
history = deque(maxlen=400)  # one sample every 3 s, ~20 min


# Login: the voice assistant is open to everyone in the LAN (config chat.public), everything
# else needs the panel password. The browser logs in once and keeps a cookie; scripts can still
# send HTTP Basic. The password from the installer can be replaced in the panel; the new one is
# stored as a PBKDF2 hash in the state directory (the panel cannot write /etc).
PASSWORD_FILE = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "panel-password")
COOKIE = "speech_spark_admin"
# Browsers keep sending HTTP Basic credentials from the old login dialog; after "log out" this
# cookie makes the panel ignore them in that browser until the next password login.
NO_BASIC = "speech_spark_no_basic"


def _stored_hash():
    try:
        with open(PASSWORD_FILE) as f:
            salt, digest = f.read().split()
        return bytes.fromhex(salt), digest
    except (OSError, ValueError):
        return None


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


def password_set():
    return bool(_stored_hash() or PASSWORD)


def check_password(password):
    stored = _stored_hash()
    if stored:
        return secrets.compare_digest(_hash(password, stored[0]), stored[1])
    return bool(PASSWORD) and secrets.compare_digest(password.encode(), PASSWORD.encode())


def _session_token():
    """Derived from the current password: changing the password logs every browser out."""
    stored = _stored_hash()
    key = (stored[1] if stored else PASSWORD).encode()
    return hmac.new(key, b"speech-spark-admin-session", hashlib.sha256).hexdigest()


def is_admin(request: Request, creds: HTTPBasicCredentials | None):
    if not password_set():
        return True
    if creds and not request.cookies.get(NO_BASIC) and check_password(creds.password):
        return True
    return secrets.compare_digest(request.cookies.get(COOKIE, ""), _session_token())


def auth(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    if not is_admin(request, creds):
        raise HTTPException(401, "login required")


def assistant(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    """Voice chat endpoints: open when chat.public is on, otherwise like auth()."""
    if load_config().get("chat", {}).get("public", True):
        return
    auth(request, creds)


def run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def unit_state(unit):
    out = run(["systemctl", "is-active", unit])[1].split("\n")[0].strip()
    return out if re.fullmatch(r"[a-z\-]+", out) else "unknown"


def unit_exists(unit):
    code, out = run(["systemctl", "list-unit-files", unit + ".service", "--no-legend"])
    return code == 0 and out.startswith(unit + ".service")


def lane_fraction(unit):
    """The static share of the unified pool a qwen38 lane claims (0.50 / 0.76 / 0.85)."""
    code, out = run(["systemctl", "cat", unit])
    m = re.search(r"--mem-fraction-static\s+([0-9.]+)", out)
    if m:
        return float(m.group(1))
    if unit == "qwen38-flash":  # the flag lives in its launch script; installer default
        return 0.85
    return None


def gpu_stats():
    if not shutil.which("nvidia-smi"):
        return None
    fields = "name,utilization.gpu,temperature.gpu,power.draw,clocks.sm,memory.used,memory.total"
    code, out = run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
    if code != 0 or not out:
        return None
    vals = [v.strip() for v in out.splitlines()[0].split(",")]

    def num(v):
        try:
            return float(v)
        except ValueError:
            return None  # GB10 reports "[N/A]" for memory: it is the shared pool
    g = dict(zip(fields.split(","), vals))
    procs = []
    code, out = run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                     "--format=csv,noheader,nounits"])
    for line in out.splitlines() if code == 0 else []:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            procs.append({"pid": parts[0], "name": parts[1].split("/")[-1], "mem_mib": num(parts[2])})
    return {"name": g["name"], "util": num(g["utilization.gpu"]), "temp": num(g["temperature.gpu"]),
            "power": num(g["power.draw"]), "clock": num(g["clocks.sm"]), "processes": procs}


def system_stats():
    vm = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(), "load": os.getloadavg(),
            "mem_total_gib": round(vm.total / 2**30, 1), "mem_avail_gib": round(mem_available_gib(), 1),
            "mem_used_pct": vm.percent}


async def service_health(name, cfg):
    url = f"http://127.0.0.1:{cfg[name]['port']}/health"
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            return (await c.get(url)).json()
    except Exception:
        return None


@app.on_event("startup")
async def sampler():
    async def loop():
        psutil.cpu_percent()
        while True:
            try:
                cfg = load_config()
                g = gpu_stats() or {}
                s = system_stats()
                h = {n: await service_health(n, cfg) for n in SERVICES}
                history.append({"t": time.time(), "gpu": g.get("util"), "cpu": s["cpu"],
                                "avail": s["mem_avail_gib"], "temp": g.get("temp"), "power": g.get("power"),
                                "asr_req": (h["asr"] or {}).get("requests"),
                                "tts_req": (h["tts"] or {}).get("requests")})
            except Exception as e:
                print("sampler:", e, flush=True)
            await asyncio.sleep(3)
    asyncio.create_task(loop())


LEARN_EVERY = 300


async def learn_once():
    """Reads quiet conversations of profiles that allow it and keeps a few lasting facts (marked
    "auto"). Runs only while nobody is chatting, so it never slows down an answer."""
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    if not (ccfg.get("memory", True) and ccfg.get("history", True) and ccfg.get("llm_url")):
        return 0
    adm = profiles.defaults(ccfg.get("defaults"))
    headers = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
    saved = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
        for uid in profiles.user_ids():
            if not dict(adm, **profiles.settings(uid)).get("learn", True):
                continue
            prof = profiles.by_id(uid)
            for convo in recall.pending(uid, time.time() * 1000)[:5]:  # the rest next time
                if time.time() - _last_chat[0] < 60:
                    return saved  # someone is talking: try again later
                payload = {"model": await llm_model(c, ccfg, headers), "temperature": 0.2, "max_tokens": 400,
                           "messages": recall.learn_messages(prof, convo),
                           "chat_template_kwargs": {"enable_thinking": False}}
                r = await c.post(ccfg["llm_url"].rstrip("/") + "/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                known = {x["text"].lower() for x in profiles.memory(uid)}
                for fact in recall.parse_facts(r.json()["choices"][0]["message"].get("content") or ""):
                    if fact.lower() not in known:
                        saved += bool(profiles.remember(uid, fact, auto=True))
                recall.mark(uid, convo)
    return saved


@app.on_event("startup")
async def learner():
    async def loop():
        while True:
            await asyncio.sleep(LEARN_EVERY)
            try:
                n = await learn_once()
                if n:
                    print(f"learned {n} fact(s) from conversations", flush=True)
            except Exception as e:
                print("learning:", type(e).__name__, e, flush=True)
    asyncio.create_task(loop())


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})


# App files (installable assistant). Public like the start page: they hold no data.
PUBLIC_FILES = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png",
                "apple-touch-icon.png": "image/png", "favicon-32.png": "image/png",
                "manifest.webmanifest": "application/manifest+json"}


@app.get("/static/{name}")
def static_file(name: str):
    if name not in PUBLIC_FILES:
        raise HTTPException(404, "not found")
    return FileResponse(os.path.join(STATIC, name), media_type=PUBLIC_FILES[name],
                        headers={"Cache-Control": "max-age=86400"})


@app.get("/manifest.webmanifest")
def manifest():
    return static_file("manifest.webmanifest")


@app.get("/apple-touch-icon.png")
def apple_icon():
    return static_file("apple-touch-icon.png")


@app.get("/favicon.ico")
def favicon():
    return static_file("favicon-32.png")


@app.get("/pebble/speech-spark.pbw")
def pebble_app():
    """The Pebble watch app, to open on the phone with the Pebble app (public: it holds no data)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pebble", "speech-spark.pbw")
    if not os.path.exists(path):
        raise HTTPException(404, "not built")
    return FileResponse(path, media_type="application/octet-stream", filename="speech-spark.pbw")


@app.get("/sw.js")
def service_worker():  # served from / so it may control the whole panel
    return FileResponse(os.path.join(STATIC, "sw.js"), media_type="text/javascript", headers={"Cache-Control": "no-cache"})


def app_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return ""


@app.get("/api/whoami")
def whoami(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    cfg = load_config()
    return {"admin": is_admin(request, creds), "version": app_version(), "public": cfg.get("chat", {}).get("public", True),
            "profile": profiles.current(request), "documents": cfg.get("chat", {}).get("documents", True),
            "reminders": cfg.get("chat", {}).get("reminders", True),
            "speaker_id": cfg.get("chat", {}).get("speaker_id", False),
            "calendar": cfg.get("chat", {}).get("calendar", True),
            "homeassistant": cfg.get("chat", {}).get("homeassistant", False),
            # what the assistant needs without the full configuration (which holds keys)
            "assistant": {"default_voice": cfg["tts"].get("default_voice"),
                          "asr_language": cfg["asr"].get("default_language"),
                          "https_port": cfg["panel"].get("https_port")}}


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if not check_password(str(body.get("password", ""))):
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "wrong password")
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(COOKIE, _session_token(), max_age=30 * 86400, httponly=True, samesite="strict")
    r.delete_cookie(NO_BASIC)
    return r


@app.post("/api/logout")
def logout():
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(COOKIE)
    r.set_cookie(NO_BASIC, "1", max_age=365 * 86400, httponly=True, samesite="strict")
    return r


# ---------------------------------------------------------------- profiles
# Who is talking to the assistant. A browser logs in to a profile with its PIN (cookie), a speaker
# sends its device key. Everything stored for a profile is only reachable through that login.
@app.post("/api/profile/login", dependencies=[Depends(assistant)])
async def profile_login(request: Request):
    body = await request.json()
    value = profiles.login(str(body.get("name", "")), str(body.get("pin", "")))
    if not value:
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "wrong name or PIN")
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(profiles.COOKIE, value, max_age=365 * 86400, httponly=True, samesite="lax")
    return r


@app.post("/api/profile/logout")
def profile_logout():
    r = Response('{"ok": true}', media_type="application/json")
    r.delete_cookie(profiles.COOKIE)
    return r


def own_profile(request: Request):
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "no profile")
    return prof


@app.get("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_memory(prof=Depends(own_profile)):
    return {"profile": prof, "facts": profiles.memory(prof["id"])}


@app.delete("/api/profile/memory/{fact_id}", dependencies=[Depends(assistant)])
def profile_forget(fact_id: str, prof=Depends(own_profile)):
    return {"removed": profiles.forget(prof["id"], fact_id=fact_id)}


@app.delete("/api/profile/memory", dependencies=[Depends(assistant)])
def profile_forget_all(prof=Depends(own_profile)):
    return {"removed": profiles.forget(prof["id"])}


@app.get("/api/profile/convos", dependencies=[Depends(assistant)])
def profile_convos(prof=Depends(own_profile)):
    return profiles.convos(prof["id"])


@app.put("/api/profile/convos", dependencies=[Depends(assistant)])
async def profile_save_convo(request: Request, prof=Depends(own_profile)):
    item = profiles.save_convo(prof["id"], await request.json())
    if not item:
        raise HTTPException(400, "invalid conversation")
    return {"ok": True}


@app.delete("/api/profile/convos/{cid}", dependencies=[Depends(assistant)])
def profile_delete_convo(cid: str, prof=Depends(own_profile)):
    profiles.delete_convo(prof["id"], cid)
    return {"ok": True}


# Documents: profiles only. Guests can neither upload nor search anything.
@app.get("/api/profile/docs", dependencies=[Depends(assistant)])
def profile_docs(prof=Depends(own_profile)):
    return documents.list_docs(prof["id"])


@app.post("/api/profile/docs", dependencies=[Depends(assistant)])
async def profile_add_doc(file: UploadFile = File(...), prof=Depends(own_profile)):
    if not load_config().get("chat", {}).get("documents", True):
        raise HTTPException(403, "documents are turned off (Konfiguration -> Wissen)")
    data = await file.read(documents.MAX_FILE + 1)
    try:
        return await asyncio.to_thread(documents.add, prof["id"], file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/profile/docs/{doc_id}", dependencies=[Depends(assistant)])
def profile_delete_doc(doc_id: str, prof=Depends(own_profile)):
    return {"removed": documents.delete(prof["id"], doc_id)}


@app.get("/api/profile/reminders", dependencies=[Depends(assistant)])
def profile_reminders(prof=Depends(own_profile)):
    return profiles.reminders(prof["id"])


@app.delete("/api/profile/reminders/{rid}", dependencies=[Depends(assistant)])
def profile_reminder_done(rid: str, prof=Depends(own_profile)):
    return {"removed": profiles.remove_reminders(prof["id"], {rid})}


# Calendar and briefing topics: profiles only; the stored password is never sent back.
def calendar_on():
    if not load_config().get("chat", {}).get("calendar", True):
        raise HTTPException(403, "calendar and daily briefing are turned off")


@app.get("/api/profile/calendar", dependencies=[Depends(assistant)])
def profile_calendar(prof=Depends(own_profile)):
    return calendars.public(prof["id"])


@app.post("/api/profile/calendar", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_add(request: Request, prof=Depends(own_profile)):
    """Adds a calendar only after it could be read once."""
    body = await request.json()
    body = body if isinstance(body, dict) else {}
    try:
        item = calendars.entry(body)
        found = await calendars.check(item, user_zone(body.get("tz")))
        return dict(calendars.add(prof["id"], item), check=found)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(400, f"calendar not reachable: {type(e).__name__}")


@app.delete("/api/profile/calendar/{cid}", dependencies=[Depends(assistant)])
def profile_calendar_remove(cid: str, prof=Depends(own_profile)):
    return calendars.remove(prof["id"], cid)


@app.put("/api/profile/calendar/topics", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_topics(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    return calendars.set_topics(prof["id"], body.get("topics") if isinstance(body, dict) else [])


@app.post("/api/profile/calendar/test", dependencies=[Depends(assistant), Depends(calendar_on)])
async def profile_calendar_test(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    try:
        return await calendars.test(prof["id"], user_zone(body.get("tz")))
    except ValueError as e:
        raise HTTPException(400, str(e))


# Home Assistant: each profile connects its own; the token is never sent back.
def ha_on():
    if not load_config().get("chat", {}).get("homeassistant", False):
        raise HTTPException(403, "Home Assistant is turned off")


@app.get("/api/profile/homeassistant", dependencies=[Depends(assistant)])
def profile_ha(prof=Depends(own_profile)):
    return homeassistant.public(prof["id"])


@app.put("/api/profile/homeassistant", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_save(request: Request, prof=Depends(own_profile)):
    """Stores the connection only after Home Assistant accepted the token."""
    body = await request.json()
    try:
        item = homeassistant.entry(body if isinstance(body, dict) else {}, homeassistant.get(prof["id"]))
        await homeassistant.check(item)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return homeassistant.save(prof["id"], item)


@app.delete("/api/profile/homeassistant", dependencies=[Depends(assistant)])
def profile_ha_remove(prof=Depends(own_profile)):
    return homeassistant.remove(prof["id"])


@app.post("/api/profile/homeassistant/test", dependencies=[Depends(assistant), Depends(ha_on)])
async def profile_ha_test(request: Request, prof=Depends(own_profile)):
    item = homeassistant.get(prof["id"])
    if not item:
        raise HTTPException(400, "no Home Assistant connected")
    body = await request.json()
    text = str((body or {}).get("text", "")).strip()
    try:
        if not text:
            return await homeassistant.check(item)
        ok, answer, targets = await homeassistant.command(item, text)
        return {"ok": ok, "answer": answer, "targets": targets}
    except (ValueError, httpx.HTTPError) as e:
        raise HTTPException(400, str(e) or type(e).__name__)


def speaker_on():
    if not load_config().get("chat", {}).get("speaker_id", False):
        raise HTTPException(403, "speaker identification is turned off")


@app.get("/api/profile/voice", dependencies=[Depends(assistant)])
def profile_voice(prof=Depends(own_profile)):
    return {"samples": len(speakers.samples(prof["id"])), "enabled": load_config()["chat"].get("speaker_id", False)}


@app.post("/api/profile/voice", dependencies=[Depends(assistant), Depends(speaker_on)])
async def profile_voice_add(file: UploadFile = File(...), prof=Depends(own_profile)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "recording is too large")
    try:
        n = await asyncio.to_thread(speakers.enroll, prof["id"], data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"samples": n}


@app.delete("/api/profile/voice", dependencies=[Depends(assistant)])
def profile_voice_delete(prof=Depends(own_profile)):
    speakers.forget(prof["id"])
    return {"samples": 0}


@app.post("/api/assistant/say", dependencies=[Depends(assistant)])
async def assistant_say(request: Request):
    """Speaks a short text (a due reminder) as streamed PCM events, like the chat's audio."""
    body = await request.json()
    text = str(body.get("text", "")).strip()[:6000]   # a reminder, or an answer read out again
    if not text:
        raise HTTPException(400, "text is required")
    cfg = load_config()
    who = profiles.current(request)
    pset = dict(profiles.defaults(cfg.get("chat", {}).get("defaults")), **(profiles.settings(who["id"]) if who else {}))
    req = {"input": text, "stream": True, "response_format": "pcm"}
    if who and pset.get("voice"):
        req["voice"] = pset["voice"]
    if pset.get("speed", 1.0) != 1.0:
        req["speed"] = pset["speed"]

    async def gen():
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
            async with c.stream("POST", f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech",
                                json=req, headers=api_headers()) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data:") and "speech.audio.delta" in line:
                        try:
                            yield f"data: {json.dumps({'type': 'audio', 'audio': json.loads(line[5:])['audio']})}\n\n"
                        except (ValueError, KeyError):
                            continue
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/profile/settings", dependencies=[Depends(assistant)])
def profile_settings(request: Request):
    """Conversation settings: the admin's defaults, overlaid with the profile's own (if logged in)."""
    prof = profiles.current(request)
    base = profiles.defaults(load_config().get("chat", {}).get("defaults"))
    return {"settings": dict(base, **(profiles.settings(prof["id"]) if prof else {})), "defaults": base,
            "profile": prof}


@app.put("/api/profile/settings", dependencies=[Depends(assistant)])
async def profile_save_settings(request: Request, prof=Depends(own_profile)):
    return {"settings": profiles.save_settings(prof["id"], await request.json())}


@app.get("/api/assistant/voices", dependencies=[Depends(assistant)])
async def assistant_voices(prof=Depends(own_profile)):
    """Voice names to choose from in the conversation settings (profiles only; guests get the default)."""
    v = await tts_voices()
    return {"voices": [x for x in v.get("voices", []) if isinstance(x, str)]}


@app.get("/api/admin/profiles", dependencies=[Depends(auth)])
def admin_profiles():
    return profiles.admin_list()


@app.post("/api/admin/profiles", dependencies=[Depends(auth)])
async def admin_add_profile(request: Request):
    body = await request.json()
    name, pin = body.get("name", ""), body.get("pin", "")
    if not profiles.valid_name(name):
        raise HTTPException(400, "name: 1 to 40 characters")
    if not profiles.valid_pin(pin):
        raise HTTPException(400, "PIN: 4 to 64 characters without spaces")
    try:
        return {"id": profiles.add_user(name, pin)}
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/admin/profiles/{uid}", dependencies=[Depends(auth)])
async def admin_set_pin(uid: str, request: Request):
    pin = (await request.json()).get("pin", "")
    if not profiles.valid_pin(pin):
        raise HTTPException(400, "PIN: 4 to 64 characters without spaces")
    if not profiles.set_pin(uid, pin):
        raise HTTPException(404, "no such profile")
    return {"ok": True}


@app.delete("/api/admin/profiles/{uid}", dependencies=[Depends(auth)])
def admin_delete_profile(uid: str):
    profiles.delete_user(uid)
    return {"ok": True}


@app.post("/api/admin/devices", dependencies=[Depends(auth)])
async def admin_add_device(request: Request):
    body = await request.json()
    if not profiles.valid_name(body.get("name", "")):
        raise HTTPException(400, "name: 1 to 40 characters")
    try:
        return {"token": profiles.add_device(body["name"], str(body.get("user", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/admin/devices/{did}", dependencies=[Depends(auth)])
async def admin_set_device(did: str, request: Request):
    if not profiles.set_device_user(did, str((await request.json()).get("user", ""))):
        raise HTTPException(404, "no such device or profile")
    return {"ok": True}


@app.delete("/api/admin/devices/{did}", dependencies=[Depends(auth)])
def admin_delete_device(did: str):
    profiles.delete_device(did)
    return {"ok": True}


@app.post("/api/password", dependencies=[Depends(auth)])
async def change_password(request: Request):
    body = await request.json()
    new = str(body.get("new", ""))
    if len(new) < 6:
        raise HTTPException(400, "the new password needs at least 6 characters")
    if password_set() and not check_password(str(body.get("old", ""))):
        await asyncio.sleep(1)
        raise HTTPException(401, "current password is wrong")
    salt = secrets.token_bytes(16)
    os.makedirs(os.path.dirname(PASSWORD_FILE), exist_ok=True)
    tmp = PASSWORD_FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(f"{salt.hex()} {_hash(new, salt)}\n")
    os.replace(tmp, PASSWORD_FILE)
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(COOKIE, _session_token(), max_age=30 * 86400, httponly=True, samesite="strict")
    return r


@app.get("/api/status", dependencies=[Depends(auth)])
async def status():
    cfg = load_config()
    services = {}
    for name, unit in SERVICES.items():
        services[name] = {"unit": unit, "state": unit_state(unit), "enabled": cfg[name]["enabled"],
                          "port": cfg[name]["port"], "estimate_gib": estimate_gib(cfg[name]["model"]),
                          "health": await service_health(name, cfg)}
    total_gib = psutil.virtual_memory().total / 2**30
    a = cfg["asr"]
    if a.get("backend") == "vllm":
        gib = round(a["engine_mem"] * total_gib + 1.5, 1)
        services["asr"]["backend"] = "vllm"
        services["asr"]["estimate_gib"] = gib
        services["asr"]["engines"] = [
            {"name": "asr-engine", "kind": "vLLM", "unit": UNITS["asr-engine"], "state": unit_state(UNITS["asr-engine"]),
             "model": a["model"], "port": a["engine_port"], "estimate_gib": gib}]
    t = cfg["tts"]
    if t.get("backend") == "vllm-omni":
        per_engine = round((t["engine_mem_talker"] + t["engine_mem_code2wav"]) * total_gib + 1.5, 1)
        services["tts"]["backend"] = "vllm-omni"
        services["tts"]["estimate_gib"] = per_engine * (2 if t.get("voicedesign_enabled") else 1)
        services["tts"]["engines"] = [
            {"name": "tts-engine", "kind": "vllm-omni", "unit": UNITS["tts-engine"], "state": unit_state(UNITS["tts-engine"]),
             "model": t["model"], "port": t["engine_port"], "estimate_gib": per_engine}]
        if t.get("voicedesign_enabled") or unit_state(UNITS["tts-design"]) != "inactive":
            services["tts"]["engines"].append(
                {"name": "tts-design", "kind": "vllm-omni", "unit": UNITS["tts-design"], "state": unit_state(UNITS["tts-design"]),
                 "model": t["voicedesign_model"], "port": t["voicedesign_port"], "estimate_gib": per_engine})
    qwen38 = [{"unit": u, "state": unit_state(u), "mem_fraction": lane_fraction(u)}
              for u in QWEN38_UNITS if unit_exists(u)]
    return {"time": time.time(), "system": system_stats(), "gpu": gpu_stats(),
            "services": services, "qwen38": qwen38, "history": list(history)}


@app.get("/api/config", dependencies=[Depends(auth)])
def get_config():
    with open(DEFAULTS) as f:
        cfg = json.load(f)
    for sec, vals in load_config().items():  # fill keys added by newer versions
        cfg.setdefault(sec, {}).update(vals)
    return cfg


def api_headers():
    key = load_config().get("api", {}).get("key", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


DEFAULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.default.json")


def validate(new):
    old = load_config()
    with open(DEFAULTS) as f:
        defaults = json.load(f)
    for sec in defaults:
        if sec not in new or not isinstance(new[sec], dict):
            raise HTTPException(400, f"section '{sec}' missing")
        for k in new[sec]:
            if k not in defaults[sec]:
                raise HTTPException(400, f"unknown key {sec}.{k}")
    if not re.fullmatch(r"[A-Za-z0-9_\-]*", new["api"]["key"]):
        raise HTTPException(400, "API key: letters, digits, _ and - only")
    ch = new["chat"]
    if ch.get("search_url") and not re.fullmatch(r"https?://\S+", ch["search_url"]):
        raise HTTPException(400, "SearXNG address must start with http:// or https://")
    if not isinstance(ch.get("defaults"), dict) or profiles.clean_settings(ch["defaults"]) != ch["defaults"]:
        raise HTTPException(400, "chat defaults: invalid value")
    if ch.get("speaker_strictness") not in speakers.STRICTNESS:
        raise HTTPException(400, "speaker_strictness: low, normal or high")
    if not (isinstance(ch.get("search_results"), int) and 1 <= ch["search_results"] <= 10
            and isinstance(ch.get("search_pages"), int) and 0 <= ch["search_pages"] <= 5):
        raise HTTPException(400, "search: 1..10 results, 0..5 pages to read")
    a = new["asr"]
    if not isinstance(a.get("context", ""), str) or len(a.get("context", "")) > 2000:
        raise HTTPException(400, "ASR context: text up to 2000 characters")
    if a.get("backend") != old["asr"].get("backend"):
        raise HTTPException(400, "the ASR backend is chosen at install time: sudo ./install.sh --asr-backend ...")
    if not isinstance(a["engine_mem"], (int, float)) or not 0.01 <= a["engine_mem"] <= 0.5:
        raise HTTPException(400, "asr engine_mem must be a share of the memory pool between 0.01 and 0.5")
    if a.get("backend") == "vllm" and "1.7B" in a["model"] and a["engine_mem"] < 0.055:
        raise HTTPException(400, "Qwen3-ASR-1.7B needs an engine share of at least 0.055 (0.6B: 0.035)")
    if not isinstance(a["engine_max_seqs"], int) or not 1 <= a["engine_max_seqs"] <= 256:
        raise HTTPException(400, "asr engine_max_seqs must be 1..256")
    t = new["tts"]
    if t.get("backend") != old["tts"].get("backend"):
        raise HTTPException(400, "the TTS backend is chosen at install time: sudo ./install.sh --tts-backend ...")
    for k in ("engine_mem_talker", "engine_mem_code2wav"):
        if not isinstance(t[k], (int, float)) or not 0.01 <= t[k] <= 0.5:
            raise HTTPException(400, f"{k} must be a share of the memory pool between 0.01 and 0.5")
    if not isinstance(t["engine_max_model_len"], int) or not 512 <= t["engine_max_model_len"] <= 65536:
        raise HTTPException(400, "engine_max_model_len must be 512..65536")
    if not isinstance(t.get("temperature"), (int, float)) or not 0.05 <= t["temperature"] <= 2:
        raise HTTPException(400, "temperature must be 0.05..2")
    if not isinstance(t.get("top_p"), (int, float)) or not 0.05 <= t["top_p"] <= 1:
        raise HTTPException(400, "top_p must be 0.05..1")
    if not isinstance(t.get("initial_chunk_frames"), int) or not 0 <= t["initial_chunk_frames"] <= 25:
        raise HTTPException(400, "Speech output start (first audio block): a whole number of frames from 0 to 25")
    if t.get("numbers") not in ("off", "words", "blocks", "digits"):
        raise HTTPException(400, "numbers must be off, words, blocks or digits")
    if not isinstance(t.get("seed"), int) or t["seed"] < -1:
        raise HTTPException(400, "seed must be a whole number, -1 = random")
    if not isinstance(t["engine_max_seqs"], int) or not 1 <= t["engine_max_seqs"] <= 64:
        raise HTTPException(400, "engine_max_seqs must be 1..64")
    if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", str(t["voicedesign_model"])):
        raise HTTPException(400, "invalid VoiceDesign model id")
    ports = [new["asr"]["port"], t["port"], new["panel"]["port"]]
    if a.get("backend") == "vllm":
        ports.append(a["engine_port"])
    if t.get("backend") == "vllm-omni":
        ports += [t["engine_port"], t["voicedesign_port"]]
    if not isinstance(new["panel"].get("https_port"), int):
        raise HTTPException(400, "https_port must be a number, 0 = off")
    if new["panel"]["https_port"]:
        ports.append(new["panel"]["https_port"])
    for p in ports:
        if not isinstance(p, int) or not 1024 <= p <= 65535:
            raise HTTPException(400, f"invalid port {p}")
        if 30000 <= p <= 30099:
            raise HTTPException(400, f"port {p} is in the 30000-30099 range used by dgx-spark-qwen38")
    if len(set(ports)) != len(ports):
        raise HTTPException(400, "ports must differ")
    lg = new["logs"]
    if not isinstance(lg["max_mb"], int) or not 50 <= lg["max_mb"] <= 20000:
        raise HTTPException(400, "logs max_mb must be 50..20000")
    if not isinstance(lg["keep_days"], int) or not 1 <= lg["keep_days"] <= 365:
        raise HTTPException(400, "logs keep_days must be 1..365")
    ch = new["chat"]
    if not re.fullmatch(r"https?://[^\s]+", str(ch["llm_url"])):
        raise HTTPException(400, "chat llm_url must start with http:// or https://")
    if not isinstance(ch["max_tokens"], int) or not 16 <= ch["max_tokens"] <= 32768:
        raise HTTPException(400, "chat max_tokens must be 16..32768")
    for sec in ("asr", "tts"):
        if not re.fullmatch(r"[\w.\-/]+", str(new[sec]["model"])):
            raise HTTPException(400, f"invalid model id {new[sec]['model']}")
        if new[sec]["dtype"] not in ("bfloat16", "float16", "float32"):
            raise HTTPException(400, "dtype must be bfloat16, float16 or float32")
    return old


@app.put("/api/config", dependencies=[Depends(auth)])
async def put_config(request: Request):
    new = await request.json()
    old = validate(new)
    if new.get("chat", {}).get("llm_key") != old.get("chat", {}).get("llm_key"):
        new["chat"].pop("llm_key_from", None)  # typed by hand: updates keep it as is
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
    # the API key is read per request, so changing it needs no restart
    mem_changed = new["memory"] != old.get("memory")
    actions = {}  # unit name -> start | stop | restart
    for n in SERVICES:
        if new[n] != old[n] or mem_changed:
            actions[n] = "restart" if new[n]["enabled"] else "stop"
    a, oa = new["asr"], old["asr"]
    if a.get("backend") == "vllm":
        if not a["enabled"]:
            actions["asr-engine"] = "stop"
        elif any(a.get(k) != oa.get(k) for k in ASR_ENGINE_KEYS) or mem_changed or not oa["enabled"]:
            actions["asr-engine"] = "restart"
    t, ot = new["tts"], old["tts"]
    if t.get("backend") == "vllm-omni":
        changed = lambda keys: any(t.get(k) != ot.get(k) for k in keys)  # noqa: E731
        if not t["enabled"]:
            actions["tts-engine"] = actions["tts-design"] = "stop"
        else:
            if changed(ENGINE_KEYS) or mem_changed or not ot["enabled"]:
                actions["tts-engine"] = "restart"
            if not t["voicedesign_enabled"]:
                if ot.get("voicedesign_enabled"):
                    actions["tts-design"] = "stop"
            elif changed(DESIGN_KEYS) or mem_changed or not ot["enabled"]:
                actions["tts-design"] = "restart"
    errors = []
    for n, action in actions.items():
        code, out = run(["sudo", "-n", "/usr/bin/systemctl", action, UNITS[n]], timeout=60)
        if code != 0:
            errors.append(f"{UNITS[n]}: {out}")
    return {"saved": True, "restarted": [n for n, a in actions.items() if a == "restart"],
            "stopped": [n for n, a in actions.items() if a == "stop"], "errors": errors,
            "panel_restart_needed": new["panel"] != old["panel"]}


@app.post("/api/service/{name}/{action}", dependencies=[Depends(auth)])
def service_action(name: str, action: str):
    if name not in UNITS or action not in ("start", "stop", "restart"):
        raise HTTPException(400, "bad service or action")
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", action, UNITS[name]], timeout=60)
    if code != 0:
        raise HTTPException(500, out or f"systemctl {action} failed")
    return {"ok": True}


@app.get("/api/logs/{name}", dependencies=[Depends(auth)])
def logs(name: str, lines: int = 200):
    if name not in LOG_UNITS:
        raise HTTPException(400, "bad service")
    return Response(journal(LOG_UNITS[name], min(lines, 2000), "short-iso"), media_type="text/plain")


@app.get("/api/languages", dependencies=[Depends(auth)])
def languages():
    return LANGS


@app.post("/api/test/asr", dependencies=[Depends(assistant)])
async def test_asr(file: UploadFile = File(...), language: str = Form("auto"), wake: str = Form("")):
    cfg = load_config()
    data = await file.read()
    form = {"language": language, "response_format": "verbose_json"}
    if wake:  # wake-word check: tell the model to expect the phrase, besides the usual context
        form["prompt"] = f"{wake[:40]}. {cfg['asr'].get('context') or ''}".strip()
    # speaker identification runs on the CPU while the GPU transcribes
    spk = None
    if cfg.get("chat", {}).get("speaker_id", False) and not wake:
        th = speakers.STRICTNESS.get(cfg["chat"].get("speaker_strictness"), 0.75)
        spk = asyncio.create_task(asyncio.to_thread(speakers.identify, data, th))
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions",
                         files={"file": (file.filename or "audio.wav", data)},
                         data=form, headers=api_headers())
    if spk is None or r.status_code != 200:
        return Response(r.content, status_code=r.status_code, media_type="application/json")
    out = r.json()
    try:
        uid, score = await spk
    except Exception:  # unreadable audio etc.: just no speaker
        uid, score = None, 0.0
    who = uid and profiles.by_id(uid)
    if who:
        out["speaker"] = {"name": who["name"], "token": speakers.token(uid), "score": round(score, 3)}
    return out


@app.post("/api/test/tts", dependencies=[Depends(auth)])
async def test_tts(request: Request):
    cfg = load_config()
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", json=await request.json(),
                         headers=api_headers())
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"),
                    headers={k: v for k, v in r.headers.items() if k.lower() == "x-processing-seconds"})


@app.post("/api/test/tts-stream", dependencies=[Depends(auth)])
async def test_tts_stream(request: Request):
    """Passes the SSE stream through so the test page hears audio as it is generated."""
    cfg = load_config()
    body = await request.json()
    body.update(stream=True, response_format="pcm")
    c = httpx.AsyncClient(timeout=600)
    up = await c.send(c.build_request("POST", f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech",
                                      json=body, headers=api_headers()), stream=True)
    if up.status_code != 200:
        content = await up.aread()
        await up.aclose(); await c.aclose()
        return Response(content, status_code=up.status_code, media_type="application/json")

    async def relay():
        try:
            async for chunk in up.aiter_raw():
                yield chunk
        finally:
            await up.aclose(); await c.aclose()
    return StreamingResponse(relay(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- voice chat
# The browser records a question, /api/test/asr turns it into text, and /api/chat streams the
# answer: LLM tokens are cut into sentences as they arrive, each sentence goes to the streaming
# TTS while the LLM keeps writing, and text and audio come back as one Server-Sent Events stream.
ABBREV = {"z", "b", "d", "h", "u", "a", "bzw", "ca", "dr", "nr", "usw", "vgl", "etc", "evtl", "ggf", "inkl",
          "max", "min", "mio", "mrd", "str", "tel", "e.g", "i.e", "vs", "mr", "mrs", "st", "prof", "jr", "sr"}
BOUNDARY = re.compile(r"[.!?…]+[\"“”»')\]]*\s+|\n+")


def split_sentences(buf, first):
    """Cut finished sentences off the front of buf. Returns (sentences, rest). A long first
    sentence is also cut at a comma, so the first audio does not wait for the whole sentence."""
    out, start = [], 0
    for m in BOUNDARY.finditer(buf):
        head = buf[start:m.start()]
        word = re.findall(r"[\w.]+$", head)
        last = word[0].lower().rstrip(".") if word else ""
        if m.group(0)[0] == "." and (last in ABBREV or len(last) == 1 or last[-1:].isdigit()):
            continue  # "z. B.", "5. Oktober", "3.5" are no sentence ends
        piece = buf[start:m.end()].strip()
        if piece:
            out.append(piece)
        start = m.end()
    rest = buf[start:]
    if first and not out and len(rest) > 120 and ", " in rest[40:]:
        cut = rest.rindex(", ") + 1
        out, rest = [rest[:cut].strip()], rest[cut:]
    return out, rest


_llm_models = {}


async def llm_model(c, ccfg, headers):
    if ccfg.get("llm_model"):
        return ccfg["llm_model"]
    url = ccfg["llm_url"].rstrip("/")
    if url not in _llm_models:
        r = await c.get(url + "/models", headers=headers, timeout=10)
        r.raise_for_status()
        _llm_models[url] = r.json()["data"][0]["id"]
    return _llm_models[url]


# Web search through the user's own SearXNG instance, offered to the LLM as a tool. SearXNG must
# allow the JSON format (settings.yml: search.formats: [html, json]).
SEARCH_TOOL = {"type": "function", "function": {
    "name": "web_search",
    "description": "Search the web for current or unknown information (news, prices, weather, events, "
                   "facts after your training). Returns result snippets and the text of the top pages.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "search query"}},
                   "required": ["query"]}}}
SEARCH_HINT = ("Du kannst mit dem Werkzeug web_search im Internet suchen. Nutze es, wenn die Frage aktuelle "
               "oder dir unbekannte Informationen braucht, sonst nicht. Fasse das Gefundene in eigenen Worten "
               "kurz zusammen und lies keine Adressen oder Links vor.")


# Memory per profile. The tools only ever act on the profile of the request (cookie or device
# key); the model cannot name another profile.
MEMORY_TOOLS = [
    {"type": "function", "function": {
        "name": "memory_save",
        "description": "Remember a fact about the user for later conversations (name, preferences, people, "
                       "plans). Use it when the user asks you to remember something or tells you something "
                       "clearly worth keeping. One short fact per call, in the third person.",
        "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}}},
    {"type": "function", "function": {
        "name": "memory_forget",
        "description": "Forget remembered facts that contain the given words, when the user asks you to.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]


HISTORY_TOOL = {"type": "function", "function": {
    "name": "history_search",
    "description": "Search the user's earlier conversations with you (not the current one). Use it when the "
                   "user refers to something talked about before ('last time', 'what did you say about ...', "
                   "'what did we talk about yesterday'). Without a query it lists the recent conversations.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "keywords; empty for an overview"},
        "days": {"type": "integer", "description": "only conversations of the last N days"}}}}}
HISTORY_HINT = ("Mit history_search findest du, worüber ihr in früheren Gesprächen gesprochen habt. Nutze es, "
                "wenn der Nutzer sich auf etwas Früheres bezieht, und erfinde nichts, was dort nicht steht.")


HA_TOOL = {"type": "function", "function": {
    "name": "home_assistant",
    "description": "Control or ask the user's smart home through Home Assistant: switch lights and devices, "
                   "set temperatures, open covers, ask for states ('how warm is it in the living room?'). "
                   "Give one short command in the user's language, naming device and room as the user did.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string",
                   "description": "e.g. 'Schalte das Licht im Wohnzimmer an'"}}, "required": ["command"]}}}
HA_HINT = ("Mit home_assistant steuerst du das Smart Home des Nutzers (Licht, Geräte, Heizung, Rollläden) und "
           "fragst Zustände ab. Gib jeden Befehl einzeln weiter und sag danach kurz, was passiert ist; behaupte "
           "nichts, was Home Assistant nicht bestätigt hat.")


DOC_TOOL = {"type": "function", "function": {
    "name": "document_search",
    "description": "Search the user's own uploaded documents. Use it when a question may be answered by "
                   "them. Returns the best-matching passages with the document name.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "keywords"}},
                   "required": ["query"]}}}


REMINDER_TOOLS = [
    {"type": "function", "function": {
        "name": "reminder_set",
        "description": "Set a timer or reminder. Give either minutes from now (timers, 'in 10 minutes') or a "
                       "local date and time 'YYYY-MM-DDTHH:MM' (reminders at a clock time). The device rings "
                       "and speaks the text when it is due.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "what to remind of, short, e.g. 'Ofen ausschalten'"},
            "minutes": {"type": "number"}, "at": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "reminder_list", "description": "List the pending timers and reminders.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "reminder_cancel", "description": "Cancel timers or reminders whose text contains the words "
                                                  "(or all, with text 'alle').",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]
WATCH_HINT = ("Die Frage kommt von einer Smartwatch mit kleinem Display und kleinem Lautsprecher. Antworte "
              "kurz, meist in ein bis drei Sätzen, ohne Listen, Tabellen oder Links.")
REMINDER_HINT = ("Mit reminder_set stellst du Timer und Erinnerungen, mit reminder_list und reminder_cancel "
                 "siehst und löschst du sie. Bestätige kurz, wann es klingelt.")


CALENDAR_TOOL = {"type": "function", "function": {
    "name": "calendar_events",
    "description": "Read the user's calendar: the appointments from a local date for a number of days.",
    "parameters": {"type": "object", "properties": {
        "date": {"type": "string", "description": "first day, 'YYYY-MM-DD' (default today)"},
        "days": {"type": "integer", "description": "number of days, 1-31 (default 1)"}}}}}
BRIEFING_TOOL = {"type": "function", "function": {
    "name": "daily_briefing",
    "description": "Everything for a daily briefing: today's and tomorrow's appointments, today's reminders "
                   "and the latest on the user's chosen topics (news, weather ...).",
    "parameters": {"type": "object", "properties": {}}}}
BRIEFING_HINT = ("Wenn der Nutzer um ein Tagesbriefing bittet, wissen will, was heute ansteht, oder dich am "
                 "Morgen mit „Guten Morgen“ begrüßt, rufe daily_briefing auf. Fasse es gesprochen und natürlich "
                 "zusammen: kurzer Gruß, die heutigen Termine in zeitlicher Reihenfolge mit Uhrzeit, dann die "
                 "Erinnerungen, dann zu jedem Thema ein bis zwei Sätze. Keine Aufzählungszeichen, keine Links.")
CALENDAR_HINT = "Für Fragen zu Terminen an bestimmten Tagen nutze calendar_events."


def user_zone(tz):
    if isinstance(tz, str) and re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}", tz):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(tz)
        except Exception:
            pass
    return datetime.datetime.now().astimezone().tzinfo


def reminder_due(args, tz):
    """Epoch milliseconds when a reminder is due, or None."""
    try:
        if args.get("minutes") not in (None, ""):
            m = float(args["minutes"])
            return int((time.time() + m * 60) * 1000) if 0 < m <= 60 * 24 * 366 else None
        if args.get("at"):
            at = datetime.datetime.fromisoformat(str(args["at"]).strip().replace("Z", ""))
            if at.tzinfo is None:
                at = at.replace(tzinfo=user_zone(tz))
            due = int(at.timestamp() * 1000)
            return due if due > time.time() * 1000 else None
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def docs_hint(prof, docs):
    names = ", ".join(d["name"] for d in docs[:30]) + (" …" if len(docs) > 30 else "")
    return (f"{prof['name']} hat eigene Dokumente hochgeladen: {names}. Wenn eine Frage dazu passen könnte, "
            "suche mit document_search darin und antworte aus den Treffern; nenne das Dokument kurz.")


def memory_hint(prof):
    facts = profiles.memory(prof["id"])
    hint = (f"Du sprichst mit {prof['name']}. Mit memory_save merkst du dir dauerhaft, was {prof['name']} dir "
            "zum Merken sagt oder was für spätere Gespräche nützlich ist, mit memory_forget vergisst du es "
            "auf Wunsch. Sag kurz, dass du es dir gemerkt hast.")
    if facts:
        hint += f"\nWas du über {prof['name']} weißt:\n" + "\n".join("- " + x["text"] for x in facts)
    return hint


class _PageText(html.parser.HTMLParser):
    """Visible text of a web page, without scripts, styles and page furniture."""
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "template"}

    def __init__(self):
        super().__init__()
        self.depth, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth and data.strip():
            self.parts.append(data.strip())


async def page_text(c, url, limit=3000):
    try:
        async with c.stream("GET", url, timeout=6, follow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 (speech-on-dgx-spark)"}) as r:
            if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                return ""
            raw = b""
            async for chunk in r.aiter_bytes():
                raw += chunk
                if len(raw) > 1_500_000:
                    break
        p = _PageText()
        p.feed(raw.decode(r.encoding or "utf-8", errors="replace"))
        return re.sub(r"\s+", " ", " ".join(p.parts))[:limit]
    except Exception:
        return ""


class _SearxResults(html.parser.HTMLParser):
    """Results from SearXNG's normal HTML page, for instances that do not allow the JSON format:
    <article class="result ..."> with <h3><a href=URL>title</a></h3> and <p class="content">."""

    def __init__(self):
        super().__init__()
        self.results, self.cur, self.field = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "article" and "result" in cls:
            self.cur = {"title": "", "url": "", "content": ""}
            self.results.append(self.cur)
        elif self.cur is not None:
            if tag == "a" and self.field is None and not self.cur["url"] and self._in_h3:
                self.cur["url"], self.field = a.get("href", ""), "title"
            elif tag == "p" and "content" in cls:
                self.field = "content"
        if tag == "h3":
            self._in_h3 = True

    _in_h3 = False

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False
        if (tag == "a" and self.field == "title") or (tag == "p" and self.field == "content"):
            self.field = None
        if tag == "article":
            self.cur, self.field = None, None

    def handle_data(self, data):
        if self.cur is not None and self.field:
            self.cur[self.field] += data


async def web_search(c, ccfg, query):
    """Returns (text for the LLM, [{title, url}])."""
    url = ccfg["search_url"].rstrip("/")
    url = url if url.endswith("/search") else url + "/search"
    r = await c.get(url, params={"q": query, "format": "json"}, timeout=10, follow_redirects=True)
    if r.status_code == 403:  # JSON not enabled on this instance: read the normal results page
        r = await c.get(url, params={"q": query}, timeout=10, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) speech-on-dgx-spark",
            "Accept": "text/html", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
        if r.status_code == 429:
            raise RuntimeError("SearXNG rate limiter blocks the Spark (429): allow its IP in limiter.toml (pass_ip)")
        r.raise_for_status()
        p = _SearxResults()
        p.feed(r.text)
        raw = [{k: v.strip() for k, v in x.items()} for x in p.results]
    else:
        if r.status_code == 429:
            raise RuntimeError("SearXNG rate limiter blocks the Spark (429): allow its IP in limiter.toml (pass_ip)")
        r.raise_for_status()
        raw = r.json().get("results", [])
    results = [x for x in raw if str(x.get("url", "")).startswith(("http://", "https://"))]
    results = results[:int(ccfg.get("search_results") or 5)]
    if not results:
        return "No results.", []
    pages = int(ccfg.get("search_pages") or 0)
    texts = await asyncio.gather(*(page_text(c, x["url"]) for x in results[:pages]))
    lines = [f"Search results for: {query}"]
    for i, x in enumerate(results):
        lines.append(f"[{i + 1}] {x.get('title', '')} ({x['url']})\n{(x.get('content') or '').strip()}")
        if i < len(texts) and texts[i]:
            lines.append(f"Page text: {texts[i]}")
    return "\n\n".join(lines)[:12000], [{"title": x.get("title") or x["url"], "url": x["url"]} for x in results]


@app.get("/api/search-test", dependencies=[Depends(auth)])
async def search_test(q: str = "DGX Spark", url: str = ""):
    """Tests the address in the form (url), so it works before saving; else the saved one."""
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    if url:
        if not re.fullmatch(r"https?://\S+", url):
            raise HTTPException(400, "SearXNG address must start with http:// or https://")
        ccfg["search_url"] = url
    if not ccfg.get("search_url"):
        raise HTTPException(400, "no SearXNG address configured")
    async with httpx.AsyncClient() as c:
        t = time.time()
        try:
            text, sources = await web_search(c, dict(ccfg, search_pages=0), q)
        except Exception as e:
            raise HTTPException(502, f"SearXNG: {e}")
    return {"results": len(sources), "first": sources[:3], "seconds": round(time.time() - t, 2)}


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]


def now_line(tz=None):
    """The LLM does not know the date; the browser's time zone is used, else the Spark's."""
    now = None
    if isinstance(tz, str) and re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}", tz):
        try:
            from zoneinfo import ZoneInfo
            now = datetime.datetime.now(ZoneInfo(tz))
        except Exception:
            now = None
    if now is None:
        now, tz = datetime.datetime.now().astimezone(), time.strftime("%Z")
    return (f"Aktuelles Datum und Uhrzeit: {WEEKDAYS[now.weekday()]}, {now.day}. {MONTHS[now.month - 1]} "
            f"{now.year}, {now:%H:%M} Uhr (Zeitzone {tz}). Nutze das nur, wenn es zur Frage passt.")


_last_chat = [0.0]


@app.post("/api/chat", dependencies=[Depends(assistant)])
async def chat(request: Request):
    _last_chat[0] = time.time()
    body = await request.json()
    cfg = load_config()
    ccfg = dict(json.load(open(DEFAULTS))["chat"], **cfg.get("chat", {}))
    messages = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant") and m.get("content")]
    if not messages:
        raise HTTPException(400, "messages are required")
    system = ccfg.get("system_prompt") or ""
    if ccfg.get("datetime", True):
        system = (system + "\n\n" + now_line(body.get("tz"))).strip()
    search = bool(ccfg.get("search") and ccfg.get("search_url"))
    if search:
        system = (system + "\n\n" + SEARCH_HINT).strip()
    who = profiles.current(request)
    # A voice recognized by the speech recognition (signed token, see speakers.py) picks that
    # profile for this turn; its own settings apply then, not the ones this browser sends.
    heard = speakers.check(body.get("speaker")) if ccfg.get("speaker_id", False) and body.get("speaker") else None
    heard = heard and profiles.by_id(heard)
    own_browser = not heard or (who and who["id"] == heard["id"])
    if heard:
        who = heard
    # conversation settings: what the request sends, else the profile's, else the admin's defaults
    # (speakers with a device key send nothing and get their profile's voice, speed and length)
    pset = dict(profiles.defaults(ccfg.get("defaults")), **(profiles.settings(who["id"]) if who else {}))
    for k in (("voice", "speed", "length") if who else ("speed", "length")) if own_browser else ():
        if k in body and profiles.SETTINGS[k][1](body[k]):
            pset[k] = body[k]
    length = {"short": "Antworte besonders knapp, meist in ein bis zwei Sätzen.",
              "long": "Du darfst ausführlicher antworten, wenn die Frage es hergibt."}.get(pset["length"])
    if length:
        system = (system + "\n\n" + length).strip()
    if body.get("client") == "watch":
        system = (system + "\n\n" + WATCH_HINT).strip()
    prof = who if ccfg.get("memory", True) else None
    if prof:  # guests get no memory at all
        system = (system + "\n\n" + memory_hint(prof)).strip()
    past = bool(prof and ccfg.get("history", True))
    if past:
        system = (system + "\n\n" + HISTORY_HINT).strip()
    # Home Assistant only for the profile's own login or device key: a voice recognized at someone
    # else's device does not switch that profile's home
    ha = homeassistant.get(who["id"]) if who and own_browser and ccfg.get("homeassistant", False) else None
    if ha:
        system = (system + "\n\n" + HA_HINT).strip()
    docs = documents.list_docs(who["id"]) if who and ccfg.get("documents", True) else []
    if docs:
        system = (system + "\n\n" + docs_hint(who, docs)).strip()
    timers = bool(ccfg.get("reminders", True))
    if timers:
        system = (system + "\n\n" + REMINDER_HINT).strip()
    # guests keep their reminders in the browser, which sends them along; profiles keep them on the Spark
    guest_rem = [{"id": x["id"][:16], "text": str(x.get("text", ""))[:200], "due": x["due"]}
                 for x in (body.get("reminders") if isinstance(body.get("reminders"), list) else [])
                 if isinstance(x, dict) and isinstance(x.get("id"), str)
                 and isinstance(x.get("due"), (int, float))][:50] if not who else []
    briefing = bool(ccfg.get("calendar", True))
    cal = calendars.get(who["id"]) if who and briefing else {"calendars": [], "topics": []}
    if briefing:
        system = (system + "\n\n" + BRIEFING_HINT + (" " + CALENDAR_HINT if cal["calendars"] else "")).strip()
    tools = ([SEARCH_TOOL] if search else []) + (MEMORY_TOOLS if prof else []) + ([HISTORY_TOOL] if past else []) \
        + ([DOC_TOOL] if docs else []) + ([HA_TOOL] if ha else []) \
        + (REMINDER_TOOLS if timers else []) + ([BRIEFING_TOOL] if briefing else []) \
        + ([CALENDAR_TOOL] if cal["calendars"] else [])
    if system:
        messages = [{"role": "system", "content": system}] + messages
    lheaders = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
    tts_url = f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech"
    tts_body = {k: body[k] for k in ("language", "instructions") if body.get(k)}
    if pset["voice"]:
        tts_body["voice"] = pset["voice"]
    if pset["speed"] != 1.0:
        tts_body["speed"] = pset["speed"]
    c = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5))
    out = asyncio.Queue()
    if heard:
        out.put_nowait({"type": "speaker", "name": heard["name"]})
    sentences = asyncio.Queue()
    t0 = time.time()

    async def llm():
        try:
            model = await llm_model(c, ccfg, lheaders)
            base = {"model": model, "stream": True, "max_tokens": int(ccfg.get("max_tokens") or 4096)}
            if not ccfg.get("thinking"):
                base["chat_template_kwargs"] = {"enable_thinking": False}
            st = {"buf": "", "first": True, "think": False, "n": 0}
            msgs, finish = list(messages), None
            searches = 0
            for rnd in range(4):  # a few tool rounds (at most two searches), then the answer
                payload = dict(base, messages=msgs)
                offer = [t for t in tools if t is not SEARCH_TOOL or searches < 2] if rnd < 3 else []
                if offer:
                    payload["tools"] = offer
                finish, calls = await llm_round(payload, st)
                if not calls or finish == "length":
                    break
                msgs.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": x["id"], "type": "function", "function": {"name": x["name"], "arguments": x["arguments"]}}
                    for x in calls]})
                for x in calls:
                    try:
                        args = json.loads(x["arguments"] or "{}")
                        args = args if isinstance(args, dict) else {}
                    except ValueError:
                        args = {}
                    msgs.append({"role": "tool", "tool_call_id": x["id"], "content": await run_tool(x["name"], args, st)})
                    if x["name"] == "web_search":
                        searches += 1
            buf = st["buf"]
            if finish == "length":
                # The answer hit max_tokens mid-sentence: speak up to the last sentence end and
                # tell the browser how much of the shown text to drop.
                ends = [m.end() for m in BOUNDARY.finditer(buf + " ")]
                keep = buf[:min(ends[-1], len(buf))] if ends else ""
                await out.put({"type": "truncated", "drop": len(buf) - len(keep)})
                buf = keep
            if buf.strip():
                await sentences.put(buf.strip())
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (401, 403) or re.match(r"LLM HTTP 40[13]\b", str(e)):
                await out.put({"type": "error", "code": "llm_auth",
                               "message": "LLM: API key rejected (401). Set the qwen38 key under Konfiguration -> Assistent."})
            else:
                await out.put({"type": "error", "message": f"LLM: {type(e).__name__}: {e}"})
        finally:
            await sentences.put(None)

    async def run_tool(name, args, st):
        if name == "web_search" and search:
            query = str(args.get("query", "")).strip()
            if not query:
                return "No query given."
            await out.put({"type": "search", "query": query})
            if st["first"]:  # something to hear while the search runs
                st["first"] = False
                en = guess_language(messages[-1]["content"]) == "English"
                await sentences.put("Let me look that up." if en else "Ich schaue kurz nach.")
            try:
                result, sources = await web_search(c, ccfg, query)
                await out.put({"type": "sources", "items": sources})
                return result
            except Exception as e:
                await out.put({"type": "search_error", "message": str(e)})
                return f"Search failed: {e}"
        if name == "home_assistant" and ha:
            text = str(args.get("command", "")).strip()
            if not text:
                return "No command given."
            await out.put({"type": "home", "command": text})
            try:
                ok, answer, targets = await homeassistant.command(
                    ha, text, "en" if guess_language(text) == "English" else "de")
            except httpx.HTTPError as e:
                await out.put({"type": "home_done", "ok": False, "text": str(e)[:200]})
                return f"Home Assistant not reachable: {type(e).__name__}"
            await out.put({"type": "home_done", "ok": ok, "text": answer, "targets": targets})
            return ("Home Assistant: " if ok else "Home Assistant failed: ") + answer \
                + (f" (devices: {', '.join(targets)})" if targets else "")
        if name == "history_search" and past:
            query = str(args.get("query", "")).strip()
            try:
                days = min(3650, max(1, int(args["days"]))) if args.get("days") not in (None, "") else None
            except (TypeError, ValueError):
                days = None
            await out.put({"type": "historysearch", "query": query})
            skip = body.get("convo") if own_browser and isinstance(body.get("convo"), str) else None
            return await asyncio.to_thread(recall.search, prof["id"], query, days, skip)
        if name == "document_search" and docs:
            query = str(args.get("query", "")).strip()
            await out.put({"type": "docsearch", "query": query})
            hits = await asyncio.to_thread(documents.search, who["id"], query)
            if hits:
                await out.put({"type": "docsources", "items": sorted({h["name"] for h in hits})})
            return "\n\n".join(f"[{h['name']}]\n{h['text']}" for h in hits) or "No matching passages."
        if name.startswith("reminder_") and timers:
            pending = profiles.reminders(who["id"]) if who else guest_rem
            zone = user_zone(body.get("tz"))
            fmt = lambda x: datetime.datetime.fromtimestamp(x["due"] / 1000, zone).strftime("%d.%m. %H:%M")  # noqa: E731
            if name == "reminder_set":
                text = str(args.get("text", "")).strip() or "Timer"
                due = reminder_due(args, body.get("tz"))
                if not due:
                    return "Invalid time: give minutes from now or a future 'YYYY-MM-DDTHH:MM'."
                item = profiles.add_reminder(who["id"], text, due) if who else \
                    {"id": secrets.token_hex(4), "text": text[:200], "due": due}
                await out.put({"type": "reminder", "action": "set", "item": item, "foreign": not own_browser})
                return f"Set: '{item['text']}' at {fmt(item)}."
            if name == "reminder_list":
                return "\n".join(f"{fmt(x)}: {x['text']}" for x in pending) or "No pending reminders."
            if name == "reminder_cancel":
                t = str(args.get("text", "")).strip().lower()
                ids = {x["id"] for x in pending if t in ("alle", "all") or (t and t in x["text"].lower())}
                if who and ids:
                    profiles.remove_reminders(who["id"], ids)
                if ids:
                    await out.put({"type": "reminder", "action": "cancel", "ids": sorted(ids), "foreign": not own_browser})
                return f"Cancelled {len(ids)}."
        if name == "calendar_events" and cal["calendars"]:
            zone = user_zone(body.get("tz"))
            try:
                day = datetime.date.fromisoformat(str(args.get("date") or "")[:10])
            except ValueError:
                day = datetime.datetime.now(zone).date()
            try:
                days = min(31, max(1, int(args.get("days") or 1)))
            except (TypeError, ValueError):
                days = 1
            await out.put({"type": "calendar"})
            start = datetime.datetime.combine(day, datetime.time(), zone)
            try:
                evs, errors = await calendars.events(who["id"], start, start + datetime.timedelta(days=days), zone)
            except (ValueError, httpx.HTTPError) as e:
                return f"Calendar not reachable: {e}"
            return ("\n".join(calendars.line(x) for x in evs) or "No appointments in this period.") \
                + "".join(f"\nCalendar '{n}' could not be read: {e}" for n, e in errors)
        if name == "daily_briefing" and briefing:
            return await briefing_text(st)
        if name == "memory_save" and prof:
            fact = profiles.remember(prof["id"], args.get("fact", ""))
            if fact:
                await out.put({"type": "memory", "action": "saved", "text": fact})
            return "Saved." if fact else "Nothing to save."
        if name == "memory_forget" and prof:
            text = str(args.get("text", "")).strip()
            n = profiles.forget(prof["id"], text=text) if len(text) >= 2 else 0  # never "forget everything"
            if n:
                await out.put({"type": "memory", "action": "forgotten", "text": text})
            return f"Forgot {n} fact(s)."
        return f"Unknown tool {name}."

    async def briefing_text(st):
        zone = user_zone(body.get("tz"))
        now = datetime.datetime.now(zone)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        await out.put({"type": "briefing"})
        topics = cal["topics"] if search else []
        jobs = [calendars.events(who["id"], today, today + datetime.timedelta(days=2), zone)
                if cal["calendars"] else asyncio.sleep(0)]
        quick = dict(ccfg, search_pages=0, search_results=3)
        jobs += [web_search(c, quick, q) for q in topics]
        if topics:
            await out.put({"type": "search", "query": " · ".join(topics)})
            if st["first"]:  # something to hear while the searches run
                st["first"] = False
                await sentences.put("Einen Moment, ich stelle alles zusammen.")
        res = await asyncio.gather(*jobs, return_exceptions=True)
        parts = [now_line(body.get("tz")).split(" Nutze")[0]]
        if not cal["calendars"]:
            parts.append("Calendar: none connected" + ("" if who else " (guests have none)") + ".")
        elif isinstance(res[0], Exception):
            parts.append(f"Calendar not reachable: {res[0]}")
        else:
            res[0], errors = res[0]
            parts += [f"Calendar '{n}' could not be read: {e}" for n, e in errors]
            tomorrow = today + datetime.timedelta(days=1)
            for label, a, b in (("Today", today, tomorrow), ("Tomorrow", tomorrow, tomorrow + datetime.timedelta(days=1))):
                evs = [x for x in res[0] if x["start"] < b and (x["end"] > a or x["start"] >= a)]
                parts.append(f"{label}'s appointments:\n" + ("\n".join(
                    calendars.line(x) + (" (already over)" if not x["allday"] and x["end"] <= now else "")
                    for x in evs) or "none"))
        if timers:
            end = (today + datetime.timedelta(days=1)).timestamp() * 1000
            pend = [x for x in (profiles.reminders(who["id"]) if who else guest_rem) if x["due"] < end]
            parts.append("Reminders today:\n" + ("\n".join(
                f"{datetime.datetime.fromtimestamp(x['due'] / 1000, zone):%H:%M} {x['text']}" for x in pend) or "none"))
        srcs = []
        for q, r in zip(topics, res[1:]):
            if isinstance(r, Exception):
                parts.append(f"Topic '{q}': search failed")
            else:
                parts.append(f"Topic '{q}':\n{r[0][:2500]}")
                srcs += r[1][:2]
        if srcs:
            await out.put({"type": "sources", "items": srcs})
        return "\n\n".join(parts)

    async def llm_round(payload, st):
        """Streams one LLM call: text goes to the browser and, sentence by sentence, to TTS.
        Returns (finish_reason, tool calls)."""
        finish, calls = None, {}
        async with c.stream("POST", ccfg["llm_url"].rstrip("/") + "/chat/completions",
                            json=payload, headers=lheaders) as r:
            if r.status_code != 200:
                raise RuntimeError(f"LLM HTTP {r.status_code}: {(await r.aread()).decode(errors='replace')[:300]}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue  # SSE comments and keep-alives
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    choice = json.loads(data)["choices"][0]
                    delta = choice.get("delta") or {}
                except (ValueError, KeyError, IndexError):
                    continue
                finish = choice.get("finish_reason") or finish
                for tc in delta.get("tool_calls") or []:  # arrives in pieces, keyed by index
                    x = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                    x["id"] = tc.get("id") or x["id"]
                    fn = tc.get("function") or {}
                    x["name"] = fn.get("name") or x["name"]
                    x["arguments"] += fn.get("arguments") or ""
                text = delta.get("content") or ""
                if not text:
                    continue
                # models that think inline: drop <think>...</think> from what is spoken
                if "<think>" in text:
                    st["think"], text = True, text.split("<think>")[0]
                if st["think"]:
                    if "</think>" not in text:
                        continue
                    st["think"], text = False, text.split("</think>", 1)[1]
                if st["n"] == 0:
                    await out.put({"type": "timing", "llm_first_token": round(time.time() - t0, 3)})
                st["n"] += 1
                await out.put({"type": "text", "delta": text})
                st["buf"] += text
                done, st["buf"] = split_sentences(st["buf"], st["first"])
                for x in done:
                    st["first"] = False
                    await sentences.put(x)
        out_calls = [dict(v, id=v["id"] or f"call_{i}") for i, v in sorted(calls.items()) if v["name"]]
        return finish, out_calls

    async def tts():
        first, played_until, ttfa = True, 0.0, 0.5
        try:
            done = False
            while not done:
                text = await sentences.get()
                if text is None:
                    break
                # Every TTS request starts its own intonation, so sentence-by-sentence speech
                # wanders in tone. Only the first sentence goes alone (fast first audio); after
                # that, everything the LLM has written meanwhile is spoken as one piece.
                # Waiting for more text is fine while the listener still has buffered audio; the
                # next request starts while enough is left to cover its time to first audio and
                # its second audio block (slower while the LLM shares the GPU), so nothing stalls.
                margin = max(1.8, 2.5 * ttfa + 0.8)
                while not first and len(text) < 300:
                    slack = played_until - time.time() - margin
                    try:
                        nxt = (sentences.get_nowait() if not sentences.empty() or slack <= 0
                               else await asyncio.wait_for(sentences.get(), slack))
                    except (asyncio.QueueEmpty, asyncio.TimeoutError):
                        break
                    if nxt is None:
                        done = True
                        break
                    # a new line only before list items (clean_text strips their markers); plain
                    # sentences stay one paragraph, so the voice does not reset at each line
                    text += ("\n" if re.match(r"\s*(?:[-*+•]|\d+\.)\s", nxt) else " ") + nxt
                if "language" not in tts_body:  # one language for the whole answer
                    lang = guess_language(" ".join([messages[-1]["content"], text]))
                    if lang:
                        tts_body["language"] = lang
                req = dict(tts_body, input=text, stream=True, response_format="pcm")
                await out.put({"type": "tts_request", "chars": len(text)})  # for the stall details in the chat
                sent, got = time.time(), False
                async with c.stream("POST", tts_url, json=req, headers=api_headers()) as r:
                    if r.status_code != 200:
                        await out.put({"type": "error", "message": f"TTS HTTP {r.status_code}: "
                                       f"{(await r.aread()).decode(errors='replace')[:300]}"})
                        continue
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            ev = json.loads(line[5:])
                        except ValueError:
                            continue
                        if ev.get("type") == "speech.audio.delta" and ev.get("audio"):
                            if not got:
                                got, ttfa = True, time.time() - sent
                            if first:
                                first = False
                                played_until = time.time()
                                await out.put({"type": "timing", "first_audio": round(time.time() - t0, 3)})
                            # 16-bit mono PCM at 24 kHz: 48000 bytes per second of audio
                            played_until = max(played_until, time.time()) + len(ev["audio"]) * 3 / 4 / 48000
                            await out.put({"type": "audio", "audio": ev["audio"]})
                        elif ev.get("type") == "speech.audio.error":
                            await out.put({"type": "error", "message": f"TTS: {ev.get('error')}"})
        except Exception as e:
            await out.put({"type": "error", "message": f"TTS: {type(e).__name__}: {e}"})
        finally:
            await out.put(None)

    tasks = [asyncio.create_task(llm()), asyncio.create_task(tts())]

    async def events():
        try:
            while (ev := await out.get()) is not None:
                yield f"data: {json.dumps(ev)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'total': round(time.time() - t0, 3)})}\n\n"
        finally:  # also runs when the browser aborts (barge-in): stop LLM and TTS
            for t in tasks:
                t.cancel()
            await c.aclose()
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/watch/ask", dependencies=[Depends(assistant)])
async def watch_ask(request: Request):
    """Starts an answer for the Pebble app (device key in X-Speech-Device); fetch it with /api/watch/poll."""
    body = await request.json()
    text = str(body.get("text", "")).strip()[:2000]
    if not text:
        raise HTTPException(400, "text is required")
    history = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in body.get("history", [])[-10:]
               if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    inner = {"messages": history + [{"role": "user", "content": text}], "client": "watch"}
    if isinstance(body.get("tz"), str):
        inner["tz"] = body["tz"]
    data = json.dumps(inner).encode()

    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}
    watch.cleanup()
    job = watch.Job(speak=bool(body.get("speak", True)))
    response = await chat(Request(request.scope, receive))
    job.task = asyncio.create_task(watch.run(job, response))
    watch.JOBS[job.id] = job
    return {"id": job.id, "format": "ima-adpcm-8k"}


def _watch_job(job_id):
    job = watch.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown or expired answer")
    return job


@app.get("/api/watch/poll", dependencies=[Depends(assistant)])
async def watch_poll(id: str, t: int = 0, a: int = 0):
    return await watch.poll(_watch_job(id), max(0, t), max(0, a))


@app.delete("/api/watch/{job_id}", dependencies=[Depends(assistant)])
async def watch_cancel(job_id: str):
    job = watch.JOBS.pop(job_id, None)
    if job and job.task:
        job.task.cancel()
    return {"ok": True}


@app.get("/api/tts/voices", dependencies=[Depends(auth)])
async def tts_voices():
    cfg = load_config()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            return (await c.get(f"http://127.0.0.1:{cfg['tts']['port']}/v1/voices")).json()
    except Exception:
        return {"model_kind": None, "voices": [], "languages": []}


@app.get("/api/clone-voices", dependencies=[Depends(auth)])
def clone_voices():
    os.makedirs(VOICES_DIR, exist_ok=True)
    return sorted(f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))


@app.post("/api/clone-voices", dependencies=[Depends(auth)])
async def add_clone_voice(name: str = Form(...), text: str = Form(""), file: UploadFile = File(...)):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
        raise HTTPException(400, "name: letters, digits, _ and - only")
    os.makedirs(VOICES_DIR, exist_ok=True)
    data = await file.read()
    if not data.startswith(b"RIFF"):  # mp3, m4a, webm, ...: the engine expects WAV
        p = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "24000", "-f", "wav", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        data, err = await p.communicate(data)
        if p.returncode or not data:
            raise HTTPException(400, f"could not read the audio file: {err.decode(errors='replace')[:200]}")
    with open(os.path.join(VOICES_DIR, name + ".wav"), "wb") as f:
        f.write(data)
    txt = os.path.join(VOICES_DIR, name + ".txt")
    if text.strip():
        with open(txt, "w") as f:
            f.write(text.strip())
    elif os.path.exists(txt):
        os.remove(txt)
    return {"ok": True}


@app.get("/api/clone-voices/{name}.wav", dependencies=[Depends(auth)])
def clone_voice_audio(name: str):
    path = os.path.join(VOICES_DIR, name + ".wav")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name) or not os.path.exists(path):
        raise HTTPException(404, "no such voice")
    return FileResponse(path, media_type="audio/wav")


@app.delete("/api/clone-voices/{name}", dependencies=[Depends(auth)])
def delete_clone_voice(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
        raise HTTPException(400, "bad name")
    for ext in (".wav", ".txt"):
        p = os.path.join(VOICES_DIR, name + ext)
        if os.path.exists(p):
            os.remove(p)
    return {"ok": True}


# A voice archive is a ZIP with <name>.wav, an optional <name>.txt (transcript of the reference)
# and voices.json describing the contents, so voices can move between Sparks or be backed up.
VOICE_NAME = re.compile(r"[A-Za-z0-9_\-]{1,40}")


@app.get("/api/clone-voices-export", dependencies=[Depends(auth)])
def export_clone_voices(names: str = ""):
    have = clone_voices()
    want = [n for n in names.split(",") if n] or have
    missing = [n for n in want if n not in have]
    if missing or not want:
        raise HTTPException(404, f"no such voice: {', '.join(missing)}" if missing else "no voices to export")
    buf, meta = io.BytesIO(), []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in want:
            z.write(os.path.join(VOICES_DIR, n + ".wav"), n + ".wav")
            entry = {"name": n, "audio": n + ".wav"}
            txt = os.path.join(VOICES_DIR, n + ".txt")
            if os.path.exists(txt):
                z.write(txt, n + ".txt")
                with open(txt) as f:
                    entry["transcript"] = f.read()
            meta.append(entry)
        z.writestr("voices.json", json.dumps({"format": "speech-spark-voices", "version": 1,
                                              "exported": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                              "voices": meta}, ensure_ascii=False, indent=2))
    fname = f"stimme-{want[0]}.zip" if len(want) == 1 else f"stimmen-{time.strftime('%Y-%m-%d')}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/clone-voices-import", dependencies=[Depends(auth)])
async def import_clone_voices(file: UploadFile = File(...), conflict: str = Form("rename")):
    """conflict: rename (keep both, the new one gets -2, -3, ...), overwrite or skip."""
    if conflict not in ("rename", "overwrite", "skip"):
        raise HTTPException(400, "conflict must be rename, overwrite or skip")
    try:
        z = zipfile.ZipFile(io.BytesIO(await file.read()))
    except zipfile.BadZipFile:
        raise HTTPException(400, "not a ZIP file (export voices in the panel to get one)")
    # only flat <name>.wav / <name>.txt entries count; sizes are checked before anything is unpacked
    files = {}
    for info in z.infolist():
        base = info.filename.rsplit("/", 1)[-1]
        stem, _, ext = base.rpartition(".")
        if ext.lower() in ("wav", "txt") and VOICE_NAME.fullmatch(stem):
            limit = 50 << 20 if ext.lower() == "wav" else 64 << 10
            if info.file_size > limit:
                raise HTTPException(400, f"{base} is too large")
            files.setdefault(stem, {})[ext.lower()] = info
    if not files or len(files) > 200:
        raise HTTPException(400, "the ZIP holds no voices (expected <name>.wav files)" if not files else "too many voices")
    os.makedirs(VOICES_DIR, exist_ok=True)
    have, done = set(clone_voices()), []
    for name, parts in sorted(files.items()):
        if "wav" not in parts:
            continue
        audio = z.read(parts["wav"])
        if not audio.startswith(b"RIFF"):
            done.append({"name": name, "result": "skipped", "reason": "not a WAV file"})
            continue
        target = name
        if name in have:
            if conflict == "skip":
                done.append({"name": name, "result": "skipped", "reason": "exists"})
                continue
            if conflict == "rename":
                i = 2
                while f"{name[:36]}-{i}" in have:
                    i += 1
                target = f"{name[:36]}-{i}"
        with open(os.path.join(VOICES_DIR, target + ".wav"), "wb") as f:
            f.write(audio)
        txt = os.path.join(VOICES_DIR, target + ".txt")
        text = z.read(parts["txt"]).decode("utf-8", errors="replace").strip() if "txt" in parts else ""
        if text:
            with open(txt, "w") as f:
                f.write(text)
        elif os.path.exists(txt):
            os.remove(txt)
        have.add(target)
        done.append({"name": name, "result": "imported", "as": target})
    return {"voices": done}


# ---------------------------------------------------------------- measuring
bench_state = {"running": False, "log": []}


@app.get("/api/bench", dependencies=[Depends(auth)])
def bench_status():
    import bench
    out = {"running": bench_state["running"], "log": bench_state["log"][-40:], "result": None, "report": None}
    try:
        with open(bench.RESULT) as f:
            out["result"] = json.load(f)
        out["report"] = bench.report(out["result"])
    except Exception:
        pass
    return out


@app.post("/api/bench", dependencies=[Depends(auth)])
async def bench_start():
    import bench
    if bench_state["running"]:
        raise HTTPException(409, "a measurement is already running")
    bench_state.update(running=True, log=["starting"])

    async def go():
        try:
            await bench.Bench(log=bench_state["log"].append).run()
        except Exception as e:
            bench_state["log"].append(f"failed: {type(e).__name__}: {e}")
        finally:
            bench_state["running"] = False
    asyncio.create_task(go())
    return {"started": True}


# ---------------------------------------------------------------- updates
_remote_cache = {"time": 0, "data": None}


def installed_version():
    try:
        with open(os.path.join(PREFIX, "VERSION.json")) as f:
            return json.load(f)
    except Exception:
        return {"commit": None, "subject": "unknown"}


def github_repo(remote):
    m = re.match(r"(?:https://github\.com/|git@github\.com:)([\w.\-]+/[\w.\-]+?)(?:\.git)?/?$", remote or "")
    return m.group(1) if m else None


async def remote_state(force=False):
    """Newest commit on the remote branch and the commits since the installed one."""
    if not force and _remote_cache["data"] and time.time() - _remote_cache["time"] < 600:
        return _remote_cache["data"]
    ver = installed_version()
    remote, branch = ver.get("remote"), ver.get("branch", "main")
    data = {"checked": time.time(), "latest": None, "behind": None, "commits": [], "error": None}
    if not remote:
        data["error"] = "installed without git: run install.sh from a git clone once"
        return data
    code, out = run(["git", "ls-remote", remote, f"refs/heads/{branch}"], timeout=20)
    if code != 0 or not out:
        data["error"] = f"could not reach {remote}: {out[-200:]}"
        return data
    data["latest"] = out.split()[0]
    if data["latest"] == ver.get("commit"):
        data["behind"] = 0
    else:
        repo = github_repo(remote)
        if repo and ver.get("commit"):
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(f"https://api.github.com/repos/{repo}/compare/{ver['commit']}...{data['latest']}",
                                    headers={"Accept": "application/vnd.github+json"})
                if r.status_code == 200:
                    j = r.json()
                    data["behind"] = j.get("ahead_by")
                    data["commits"] = [{"sha": x["sha"][:7], "title": x["commit"]["message"].split("\n")[0],
                                        "date": x["commit"]["committer"]["date"]} for x in j.get("commits", [])][-30:]
            except Exception:
                pass
        if data["behind"] is None:
            data["behind"] = -1  # newer version exists, details unknown
    _remote_cache.update(time=time.time(), data=data)
    return data


# ---------------------------------------------------------------- update lock
# update.sh writes its progress to this file; while it runs the panel refuses changes (all
# mutating requests except the ones the assistant needs) and the page shows a locked progress bar.
UPDATE_PROGRESS = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"),
                               "update-progress.json")
UPDATE_TIMEOUT = 20 * 60
# install.sh sections -> (share of the bar, German label)
UPDATE_STEPS = [("Neue Version", 5, "Neue Version geladen"), ("System packages", 10, "Systempakete"),
                ("Service user", 14, "Dienstkonto und Ordner"), ("Git clone", 16, "Git-Kopie"),
                ("config.json", 20, "Einstellungen übernehmen"), ("qwen38 API key", 22, "Schlüssel für das Sprachmodell"),
                ("certificate", 24, "Zertifikat"), ("Checking ports", 26, "Ports prüfen"),
                ("Python env for Qwen3", 32, "Python-Umgebung Spracherkennung/-ausgabe"),
                ("Python env for the panel", 38, "Python-Umgebung Panel"),
                ("Python env for the engines", 48, "Python-Umgebung Engines (vLLM)"),
                ("Downloading", 62, "Modelle prüfen"), ("Installing application files", 74, "Programmdateien installieren"),
                ("systemd units", 80, "Dienste einrichten"), ("Starting services", 86, "Dienste neu starten und laden"),
                ("Smoke test", 95, "Kurztest"), ("Fertig", 100, "Fertig")]
_upd_cache = {"t": 0.0, "running": False}


def update_running():
    """True while the update unit runs (asked at most every 3 s)."""
    if time.time() - _upd_cache["t"] > 3:
        code, out = run(["systemctl", "show", "speech-spark-update", "-p", "ActiveState"])
        _upd_cache.update(t=time.time(), running=bool(re.search(r"^ActiveState=(activating|active)$", out, re.M)))
    return _upd_cache["running"]


def update_progress():
    try:
        with open(UPDATE_PROGRESS) as f:
            p = json.load(f)
    except (OSError, ValueError):
        return None
    text = str(p.get("text", ""))
    pct, label = 3, text
    for key, share, name in UPDATE_STEPS:
        if key.lower() in text.lower():
            pct, label = share, name
    if p.get("done"):
        pct = 100 if p.get("ok") else pct
        label = text
    return {"percent": pct, "text": label, "step": p.get("step"), "started": p.get("started"),
            "updated": p.get("updated"), "done": bool(p.get("done")), "ok": p.get("ok"),
            "version": p.get("version"), "now": int(time.time()), "timeout": UPDATE_TIMEOUT}


UNLOCKED = ("/api/chat", "/api/test/asr", "/api/assistant/", "/api/watch/", "/api/login", "/api/logout",
            "/api/profile/login", "/api/profile/logout", "/api/update")


@app.middleware("http")
async def update_lock(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and not request.url.path.startswith(UNLOCKED) and await asyncio.to_thread(update_running):
        return Response('{"detail": "update running: changes are locked until it has finished"}',
                        status_code=423, media_type="application/json")
    return await call_next(request)


@app.get("/api/update/progress", dependencies=[Depends(auth)])
def update_progress_api(log: bool = True):
    p = update_progress() or {}
    p["running"] = update_running()
    if log:
        p["log"] = [x for x in journal("speech-spark-update", 8).splitlines() if x.strip()][-8:]
    return p


@app.get("/api/update", dependencies=[Depends(auth)])
async def update_status(check: bool = False):
    code, out = run(["systemctl", "show", "speech-spark-update", "-p", "ActiveState,Result,ExecMainExitTimestamp"])
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"installed": installed_version(), "remote": await remote_state(force=check),
            "running": props.get("ActiveState") in ("activating", "active"),
            "last_result": props.get("Result"), "last_finished": props.get("ExecMainExitTimestamp") or None}


@app.post("/api/update", dependencies=[Depends(auth)])
def start_update():
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-update"], timeout=20)
    if code != 0:
        raise HTTPException(500, out or "could not start the update")
    _remote_cache["data"] = None
    return {"started": True}


@app.delete("/api/update", dependencies=[Depends(auth)])
def stop_update():
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", "stop", "speech-spark-update"], timeout=60)
    if code != 0:
        raise HTTPException(500, out or "could not stop the update")
    _remote_cache["data"] = None
    return {"stopped": True}


TLS_DIR = os.environ.get("SPEECH_SPARK_TLS", "/etc/speech-spark/tls")


class Server(uvicorn.Server):
    """Two servers (http and https) share one process; signals are handled once for both."""
    def capture_signals(self):
        import contextlib
        return contextlib.nullcontext()


async def serve():
    import signal
    quiet_access_log()
    pcfg = load_config("panel")
    servers = [Server(uvicorn.Config(app, host=pcfg["host"], port=pcfg["port"]))]
    cert, key = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
    # Browsers only allow the microphone on https (or localhost); the voice chat needs it.
    if pcfg.get("https_port") and os.path.exists(cert) and os.path.exists(key):
        servers.append(Server(uvicorn.Config(app, host=pcfg["host"], port=pcfg["https_port"],
                                             ssl_certfile=cert, ssl_keyfile=key)))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [setattr(x, "should_exit", True) for x in servers])
    await asyncio.gather(*(x.serve() for x in servers))


if __name__ == "__main__":
    asyncio.run(serve())
