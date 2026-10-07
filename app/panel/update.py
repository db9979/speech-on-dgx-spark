"""Updates from GitHub: version check, start/stop, progress and the lock while an update runs."""
import asyncio
import json
import os
import re
import sys
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import journal  # noqa: E402
from core import PREFIX, auth, run  # noqa: E402
import backup  # noqa: E402
import guard  # noqa: E402

router = APIRouter()


# ---------------------------------------------------------------- updates
_remote_cache = {"time": 0, "data": None}


def installed_version():
    try:
        with open(os.path.join(PREFIX, "VERSION.json")) as f:
            return json.load(f)
    except Exception:
        return {"commit": None, "subject": "unknown"}


def previous_version():
    """The version that ran before the last update (update.sh keeps it), or None."""
    try:
        with open(os.path.join(PREFIX, "VERSION.prev.json")) as f:
            d = json.load(f)
        return d if re.fullmatch(r"[0-9a-f]{40}", str(d.get("commit"))) else None
    except Exception:
        return None


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
        if repo:  # the version number of the newest state, for the notice on the page
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(f"https://raw.githubusercontent.com/{repo}/{data['latest']}/app/VERSION")
                if r.status_code == 200 and re.fullmatch(r"V[\d.]{1,20}", r.text.strip()):
                    data["version"] = r.text.strip()
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
                ("Downloading", 62, "Modelle prüfen"), ("Installing application files", 72, "Programmdateien installieren"),
                ("Self-test", 76, "Selbsttest"),
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


async def update_lock(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and not request.url.path.startswith(UNLOCKED) and await asyncio.to_thread(update_running):
        return Response('{"detail": "update running: changes are locked until it has finished"}',
                        status_code=423, media_type="application/json")
    return await call_next(request)


@router.get("/api/update/progress", dependencies=[Depends(auth)])
def update_progress_api(log: bool = True):
    p = update_progress() or {}
    p["running"] = update_running()
    if log:
        p["log"] = [x for x in journal("speech-spark-update", 8).splitlines() if x.strip()][-8:]
    return p


@router.get("/api/update", dependencies=[Depends(auth)])
async def update_status(check: bool = False):
    code, out = run(["systemctl", "show", "speech-spark-update", "-p", "ActiveState,Result,ExecMainExitTimestamp"])
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"installed": installed_version(), "previous": previous_version(), "remote": await remote_state(force=check),
            "running": props.get("ActiveState") in ("activating", "active"),
            "last_result": props.get("Result"), "last_finished": props.get("ExecMainExitTimestamp") or None}


def _backup_first(why):
    try:
        backup.create(why)
    except Exception as e:  # a failed backup does not block the update, but it is noted
        guard.log("backup_failed", detail=f"{type(e).__name__}: {e}"[:200])


@router.post("/api/update", dependencies=[Depends(auth)])
def start_update():
    _backup_first("before-update")
    return _start()


@router.post("/api/update/rollback", dependencies=[Depends(auth)])
def rollback():
    """Installs the version that ran before the last update again."""
    prev = previous_version()
    if not prev:
        raise HTTPException(404, "no previous version known (it is kept from the next update on)")
    _backup_first("before-rollback")
    with open(os.path.join(os.path.dirname(UPDATE_PROGRESS), "update-target"), "w") as f:
        f.write(prev["commit"])
    guard.log("rollback", detail=f"back to {prev.get('version') or prev.get('short')}")
    try:
        return _start()
    except HTTPException:
        os.remove(os.path.join(os.path.dirname(UPDATE_PROGRESS), "update-target"))
        raise


def _start():
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "speech-spark-update"], timeout=20)
    if code != 0:
        raise HTTPException(500, out or "could not start the update")
    _remote_cache["data"] = None
    return {"started": True}


@router.delete("/api/update", dependencies=[Depends(auth)])
def stop_update():
    code, out = run(["sudo", "-n", "/usr/bin/systemctl", "stop", "speech-spark-update"], timeout=60)
    if code != 0:
        raise HTTPException(500, out or "could not stop the update")
    _remote_cache["data"] = None
    return {"stopped": True}
