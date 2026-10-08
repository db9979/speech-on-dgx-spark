"""System page: backups, the live check of the real services and the alerts shown on top."""
import asyncio
import json
import re
import os
import secrets
import sys
import tempfile
import time

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backup  # noqa: E402
import guard  # noqa: E402
import health  # noqa: E402
import profiles  # noqa: E402
import quality  # noqa: E402
from common import load_config  # noqa: E402
from core import DEFAULTS, admin_code, auth  # noqa: E402

router = APIRouter()


@router.get("/api/backups", dependencies=[Depends(auth)])
def backups():
    return {"backups": backup.listing(), "keep": backup.KEEP, "dir": backup.BACKUP_DIR}


@router.post("/api/backups", dependencies=[Depends(auth)])
async def backup_now():
    try:
        item = await asyncio.to_thread(backup.create, "manual")
    except OSError as e:
        raise HTTPException(500, f"backup failed: {e}")
    guard.log("backup", detail=item["name"])
    return item


# A backup holds every profile's data: downloading one needs the second step too. The browser first
# gets a one-time ticket (valid 60 s) with the code, then follows a plain link with it.
_tickets = {}


@router.post("/api/backups/{name}/ticket", dependencies=[Depends(auth), Depends(admin_code)])
def backup_ticket(name: str):
    try:
        backup.path_of(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")
    now = time.time()
    for k in [k for k, v in _tickets.items() if v[1] < now]:
        _tickets.pop(k, None)
    t = secrets.token_urlsafe(24)
    _tickets[t] = (name, now + 60)
    guard.log("backup_download", detail=name)
    return {"url": f"/api/backups/{name}?t={t}"}


@router.get("/api/backups/{name}", dependencies=[Depends(auth)])
def backup_download(name: str, t: str = ""):
    try:
        path = backup.path_of(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")
    got = _tickets.pop(t, None) if t else None
    if not got or got[0] != name or got[1] < time.time():
        raise HTTPException(403, "download only through the button (needs a fresh ticket)")
    return FileResponse(path, media_type="application/gzip", filename=name)


@router.delete("/api/backups/{name}", dependencies=[Depends(auth)])
def backup_delete(name: str):
    try:
        backup.remove(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")
    return {"backups": backup.listing()}


@router.post("/api/backups/{name}/restore", dependencies=[Depends(auth), Depends(admin_code)])
async def backup_restore(name: str):
    try:
        path = backup.path_of(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")
    return await _restore(open(path, "rb"), name)


@router.post("/api/backups-upload", dependencies=[Depends(auth), Depends(admin_code)])
async def backup_upload(file: UploadFile = File(...)):
    """Restores a backup file from this computer (e.g. one downloaded earlier or from another Spark)."""
    tmp = tempfile.TemporaryFile()
    size = 0
    while chunk := await file.read(1 << 20):
        size += len(chunk)
        if size > backup.MAX_UPLOAD:
            raise HTTPException(413, "backup too large")
        tmp.write(chunk)
    tmp.seek(0)
    return await _restore(tmp, file.filename or "upload")


def _check_config(new):
    """Settings from a backup get the same checks as the settings page: keys of this version only
    (newer keys from the defaults), the installed backends kept, every value validated."""
    import admin
    with open(DEFAULTS) as fh:
        defaults = json.load(fh)
    cur = load_config()
    out = {}
    for sec, vals in defaults.items():
        got = new.get(sec) if isinstance(new.get(sec), dict) else {}
        out[sec] = dict(vals, **{k: v for k, v in got.items() if k in vals})
    for sec in ("asr", "tts"):
        out[sec]["backend"] = cur.get(sec, {}).get("backend", out[sec]["backend"])
    if isinstance(out["chat"].get("defaults"), dict):
        out["chat"]["defaults"] = profiles.clean_settings(out["chat"]["defaults"])
    try:
        admin.validate(out)
    except HTTPException as e:
        raise ValueError(f"settings in the backup: {e.detail}")
    return out


async def _restore(f, name):
    try:
        with f:
            done = await asyncio.to_thread(backup.restore, f, _check_config)
    except (ValueError, OSError, EOFError) as e:
        raise HTTPException(400, f"restore failed: {e}")
    except Exception as e:  # broken archive
        raise HTTPException(400, f"restore failed: {type(e).__name__}")
    guard.log("restore", detail=f"{name}: {', '.join(done)}")
    return {"restored": done}


@router.get("/api/livecheck", dependencies=[Depends(auth)])
def livecheck_result():
    return health.last_live() or {}


@router.post("/api/livecheck", dependencies=[Depends(auth)])
async def livecheck_now():
    return await health.livecheck("manual")


@router.get("/api/quality", dependencies=[Depends(auth)])
def quality_result():
    return {"running": quality.running(), "last": quality.last(), "own": quality.own()}


@router.delete("/api/quality/cases/{cid}", dependencies=[Depends(auth)])
def quality_drop_case(cid: str):
    if not re.fullmatch(r"[0-9a-f]{8}", cid) or not quality.drop_own(cid):
        raise HTTPException(404, "no such case")
    return {"own": quality.own()}


@router.post("/api/quality", dependencies=[Depends(auth)])
async def quality_now():
    if not quality.running():
        asyncio.create_task(quality.run("manual"))
        await asyncio.sleep(0.1)
    return {"running": True, "last": quality.last()}


# ---------------------------------------------------------------- first-start wizard
SETUP_FILE = os.path.join(backup.STATE, "setup.json")


@router.get("/api/setup", dependencies=[Depends(auth)])
def setup_state():
    try:
        with open(SETUP_FILE) as f:
            done = json.load(f).get("done", False)
    except (OSError, ValueError):
        done = bool(profiles.user_ids())  # installed before the wizard existed: already set up
    return {"done": done, "profiles": len(profiles.user_ids())}


@router.post("/api/setup", dependencies=[Depends(auth)])
async def setup_done(request: Request):
    done = bool((await request.json()).get("done", True))
    os.makedirs(backup.STATE, exist_ok=True)
    with open(SETUP_FILE, "w") as f:
        json.dump({"done": done}, f)
    return {"done": done}


@router.post("/api/setup/llm-test", dependencies=[Depends(auth)])
async def setup_llm_test(request: Request):
    """Can the panel reach this LLM address (with this key, or the stored one)? Lists its models."""
    body = await request.json()
    ccfg = load_config().get("chat", {})
    url = str(body.get("url") or ccfg.get("llm_url", "")).rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "the address must start with http:// or https://")
    # the stored key only ever goes to the stored address, never to one typed into this test
    stored = str(ccfg.get("llm_key") or "") if url == str(ccfg.get("llm_url", "")).rstrip("/") else ""
    key = str(body.get("key") or stored)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url + "/models", headers={"Authorization": f"Bearer {key}"} if key else {})
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"not reachable ({type(e).__name__})"}
    if r.status_code in (401, 403):
        return {"ok": False, "error": "the key is rejected (401)"}
    try:
        models = [m["id"] for m in r.json()["data"]]
    except Exception:
        return {"ok": False, "error": f"no model list (HTTP {r.status_code})"}
    return {"ok": True, "models": models[:20]}
