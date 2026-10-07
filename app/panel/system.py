"""System page: backups, the live check of the real services and the alerts shown on top."""
import asyncio
import os
import sys
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backup  # noqa: E402
import guard  # noqa: E402
import health  # noqa: E402
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
