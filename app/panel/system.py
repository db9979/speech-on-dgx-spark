"""System page: backups, the live check of the real services and the alerts shown on top."""
import asyncio
import json
import os
import sys
import tempfile

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backup  # noqa: E402
import guard  # noqa: E402
import health  # noqa: E402
import profiles  # noqa: E402
from common import load_config  # noqa: E402
from core import auth  # noqa: E402

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


@router.get("/api/backups/{name}", dependencies=[Depends(auth)])
def backup_download(name: str):
    try:
        return FileResponse(backup.path_of(name), media_type="application/gzip", filename=name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")


@router.delete("/api/backups/{name}", dependencies=[Depends(auth)])
def backup_delete(name: str):
    try:
        backup.remove(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")
    return {"backups": backup.listing()}


@router.post("/api/backups/{name}/restore", dependencies=[Depends(auth)])
async def backup_restore(name: str):
    try:
        path = backup.path_of(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such backup")
    return await _restore(open(path, "rb"), name)


@router.post("/api/backups-upload", dependencies=[Depends(auth)])
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


async def _restore(f, name):
    try:
        with f:
            done = await asyncio.to_thread(backup.restore, f)
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
    key = str(body.get("key") or ccfg.get("llm_key") or "")
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
