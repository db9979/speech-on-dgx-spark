"""Admin pages: status, configuration, services, logs, tests, cloned voices, benchmark, profiles and devices."""
import asyncio
import json
import os
import re
import io
import secrets
import sys
import time
import zipfile

import httpx
import psutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guard  # noqa: E402
import health  # noqa: E402
import speakers  # noqa: E402
import profiles  # noqa: E402
from common import CONFIG_PATH, estimate_gib, journal, load_config  # noqa: E402
from core import (  # noqa: E402
    ASR_ENGINE_KEYS,
    ADMIN_IDLE,
    COOKIE,
    DEFAULTS,
    DESIGN_KEYS,
    ENGINE_KEYS,
    LANGS,
    LOG_UNITS,
    PASSWORD_FILE,
    QWEN38_UNITS,
    SERVICES,
    UNITS,
    VOICES_DIR,
    _hash,
    _session_token,
    api_headers,
    assistant,
    auth,
    check_password,
    password_set,
    run,
    unit_exists,
    unit_state)
from monitor import gpu_stats, history, lane_fraction, service_health, system_stats  # noqa: E402
from chat import web_search  # noqa: E402

router = APIRouter()


@router.get("/api/audit", dependencies=[Depends(auth)])
def audit(limit: int = 300):
    """The change log: logins, failed logins, lockouts and every change, newest first."""
    names = {u: (profiles.by_id(u) or {}).get("name") for u in profiles.user_ids()}
    return {"events": guard.read(max(1, min(limit, 2000))), "names": names}


@router.get("/api/admin/profiles", dependencies=[Depends(auth)])
def admin_profiles():
    return profiles.admin_list()


@router.post("/api/admin/profiles", dependencies=[Depends(auth)])
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


@router.put("/api/admin/profiles/{uid}", dependencies=[Depends(auth)])
async def admin_set_pin(uid: str, request: Request):
    pin = (await request.json()).get("pin", "")
    if not profiles.valid_pin(pin):
        raise HTTPException(400, "PIN: 4 to 64 characters without spaces")
    if not profiles.set_pin(uid, pin):
        raise HTTPException(404, "no such profile")
    return {"ok": True}


@router.delete("/api/admin/profiles/{uid}", dependencies=[Depends(auth)])
def admin_delete_profile(uid: str):
    profiles.delete_user(uid)
    return {"ok": True}


@router.post("/api/admin/devices", dependencies=[Depends(auth)])
async def admin_add_device(request: Request):
    body = await request.json()
    if not profiles.valid_name(body.get("name", "")):
        raise HTTPException(400, "name: 1 to 40 characters")
    try:
        return {"token": profiles.add_device(body["name"], str(body.get("user", "")))}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/api/admin/devices/{did}", dependencies=[Depends(auth)])
async def admin_set_device(did: str, request: Request):
    if not profiles.set_device_user(did, str((await request.json()).get("user", ""))):
        raise HTTPException(404, "no such device or profile")
    return {"ok": True}


@router.delete("/api/admin/devices/{did}", dependencies=[Depends(auth)])
def admin_delete_device(did: str):
    profiles.delete_device(did)
    return {"ok": True}


@router.post("/api/password", dependencies=[Depends(auth)])
async def change_password(request: Request):
    body = await request.json()
    new = str(body.get("new", ""))
    if len(new) < 6:
        raise HTTPException(400, "the new password needs at least 6 characters")
    guard.check(request)
    if password_set() and not check_password(str(body.get("old", ""))):
        guard.failed(request, what="admin_password")
        await asyncio.sleep(1)
        raise HTTPException(401, "current password is wrong")
    salt = secrets.token_bytes(16)
    os.makedirs(os.path.dirname(PASSWORD_FILE), exist_ok=True)
    tmp = PASSWORD_FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(f"{salt.hex()} {_hash(new, salt)}\n")
    os.replace(tmp, PASSWORD_FILE)
    r = Response('{"ok": true}', media_type="application/json")
    r.set_cookie(COOKIE, _session_token(), max_age=ADMIN_IDLE, httponly=True, samesite="strict")
    guard.log("admin_password_changed", ip=guard.client_ip(request))
    return r


@router.get("/api/status", dependencies=[Depends(auth)])
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
            "services": services, "qwen38": qwen38, "history": list(history),
            "alerts": health.alerts(), "watchdog": health.events[-10:]}


@router.get("/api/config", dependencies=[Depends(auth)])
def get_config():
    with open(DEFAULTS) as f:
        cfg = json.load(f)
    for sec, vals in load_config().items():  # fill keys added by newer versions
        cfg.setdefault(sec, {}).update(vals)
    return cfg


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
    w = new["watch"]
    if not isinstance(w.get("watchdog"), bool):
        raise HTTPException(400, "watch watchdog must be true or false")
    if not isinstance(w.get("warn_gib"), (int, float)) or not 2 <= w["warn_gib"] <= 64:
        raise HTTPException(400, "watch warn_gib must be 2..64")
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


@router.put("/api/config", dependencies=[Depends(auth)])
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


@router.post("/api/service/{name}/{action}", dependencies=[Depends(auth)])
def service_action(name: str, action: str):
    if name not in UNITS or action not in ("start", "stop", "restart"):
        raise HTTPException(400, "bad service or action")
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", action, UNITS[name]], timeout=60)
    if code != 0:
        raise HTTPException(500, out or f"systemctl {action} failed")
    return {"ok": True}


@router.get("/api/logs/{name}", dependencies=[Depends(auth)])
def logs(name: str, lines: int = 200):
    if name not in LOG_UNITS:
        raise HTTPException(400, "bad service")
    return Response(journal(LOG_UNITS[name], min(lines, 2000), "short-iso"), media_type="text/plain")


@router.get("/api/languages", dependencies=[Depends(auth)])
def languages():
    return LANGS


@router.post("/api/test/asr", dependencies=[Depends(assistant)])
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


@router.post("/api/test/tts", dependencies=[Depends(auth)])
async def test_tts(request: Request):
    cfg = load_config()
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", json=await request.json(),
                         headers=api_headers())
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"),
                    headers={k: v for k, v in r.headers.items() if k.lower() == "x-processing-seconds"})


@router.post("/api/test/tts-stream", dependencies=[Depends(auth)])
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


@router.get("/api/search-test", dependencies=[Depends(auth)])
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


@router.get("/api/tts/voices", dependencies=[Depends(auth)])
async def tts_voices():
    cfg = load_config()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            return (await c.get(f"http://127.0.0.1:{cfg['tts']['port']}/v1/voices")).json()
    except Exception:
        return {"model_kind": None, "voices": [], "languages": []}


@router.get("/api/clone-voices", dependencies=[Depends(auth)])
def clone_voices():
    os.makedirs(VOICES_DIR, exist_ok=True)
    return sorted(f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))


@router.post("/api/clone-voices", dependencies=[Depends(auth)])
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


@router.get("/api/clone-voices/{name}.wav", dependencies=[Depends(auth)])
def clone_voice_audio(name: str):
    path = os.path.join(VOICES_DIR, name + ".wav")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name) or not os.path.exists(path):
        raise HTTPException(404, "no such voice")
    return FileResponse(path, media_type="audio/wav")


@router.delete("/api/clone-voices/{name}", dependencies=[Depends(auth)])
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


@router.get("/api/clone-voices-export", dependencies=[Depends(auth)])
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


@router.post("/api/clone-voices-import", dependencies=[Depends(auth)])
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


@router.get("/api/bench", dependencies=[Depends(auth)])
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


@router.post("/api/bench", dependencies=[Depends(auth)])
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
