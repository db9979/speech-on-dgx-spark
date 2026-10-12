"""Updates from GitHub: version check, start/stop, progress and the lock while an update runs."""
import asyncio
import json
import os
import re
import sys
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBasicCredentials
from fastapi.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import journal  # noqa: E402
from core import PREFIX, admin_code, app_version, auth, browser_profile, is_admin, run, security  # noqa: E402
import backup  # noqa: E402
import ghtoken  # noqa: E402
import guard  # noqa: E402

router = APIRouter()


# ---------------------------------------------------------------- updates
_remote_cache = {"time": 0, "data": None}
# by itself (page views, the app's notice) GitHub is asked at most this often; "Jetzt prüfen", the night
# update and an update start from the app always ask (Dominik, 2026-10-12: the 60 per hour ran out)
AUTO_EVERY = 3 * 3600


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


def pick_green(runs, branch, head):
    """From the Actions API's runs of "Tests": the newest commit of the branch whose run passed, and
    what is known about the newest commit (head): "green", "running", "red" or "unknown"."""
    green, state = None, "unknown"
    for r in runs if isinstance(runs, list) else []:
        if not isinstance(r, dict) or r.get("head_branch") != branch:
            continue
        sha = str(r.get("head_sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            continue
        if sha == head and state == "unknown":
            state = {"success": "green", None: "running"}.get(r.get("conclusion"), "red")
        if green is None and r.get("conclusion") == "success":
            green = sha
    if head and green == head:
        state = "green"
    return green, state


class GitHubRefused(Exception):
    """GitHub answered with an error status; until: when its hourly limit allows the next question."""

    def __init__(self, status, until=None):
        super().__init__(f"HTTP {status}")
        self.status, self.until = status, until


def rate_limit_until(status, headers, now):
    """When GitHub's limit for unauthenticated questions (60 per hour and address) is reached: the time
    it is lifted again, from Retry-After or X-RateLimit-Reset, at most one hour ahead; else None."""
    if status not in (403, 429):
        return None
    try:
        after = int(headers.get("retry-after", ""))
        return now + max(0, min(after, 3600))
    except ValueError:
        pass
    if headers.get("x-ratelimit-remaining") != "0" and status != 429:
        return None
    try:
        reset = int(headers.get("x-ratelimit-reset", ""))
    except ValueError:
        reset = 0
    return min(max(reset, now + 60), now + 3600)


async def green_runs(repo, branch, passed=False):
    """The newest runs of the "Tests" workflow (update.sh asks the same before it installs anything);
    passed: only the ones that passed (when many pushes in a row cancelled each other's runs, the
    newest 30 can hold no green one although an older commit passed)."""
    params = {"branch": branch, "event": "push", "per_page": 30}
    if passed:
        params.update(status="success", per_page=5)
    url = f"https://api.github.com/repos/{repo}/actions/workflows/tests.yml/runs"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await ghtoken.get(c, url, params=params, headers={"Accept": "application/vnd.github+json"})
    if r.status_code != 200:
        raise GitHubRefused(r.status_code, rate_limit_until(r.status_code, r.headers, time.time()))
    return r.json().get("workflow_runs")


# a failed question to GitHub is not repeated at once: every page view and the app ask for the
# state, and without this a refusal turned into a flood of questions and log lines
_FAIL_PAUSE = 900
_failed = {"until": 0.0, "data": None, "limited": False}


def _remember_failure(data, until, limited):
    _failed.update(until=until, data=data, limited=limited)
    data["retry_at"] = until
    return data


async def remote_state(force=False):
    """Newest commit on the remote branch and the commits since the installed one (and, when GitHub was really
    asked, the way and its outcome on Zustand → Live)."""
    t0 = time.time()
    data = await _remote_state(force)
    if isinstance(data, dict) and (data.get("checked") or 0) >= t0:
        import live
        live.update_checked(data, t0)
    return data


async def _remote_state(force=False):
    now = time.time()
    if not force and _remote_cache["data"] and now - _remote_cache["time"] < AUTO_EVERY:
        return _remote_cache["data"]
    # after a refusal: wait the pause out; GitHub's hourly limit holds even for "Jetzt prüfen"
    if _failed["data"] and now < _failed["until"] and (_failed["limited"] or not force):
        return _failed["data"]
    ver = installed_version()
    remote, branch = ver.get("remote"), ver.get("branch", "main")
    data = {"checked": time.time(), "latest": None, "behind": None, "commits": [], "error": None}
    if not remote:
        data["error"] = "installed without git: run install.sh from a git clone once"
        return data
    # the service account has no usable home: no git config, no credential prompt, a safe HOME
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", HOME=os.environ.get("SPEECH_SPARK_STATE", "/tmp"),
               GIT_CONFIG_NOSYSTEM="1")
    # up to 30 s over the network: in a worker thread, the panel keeps answering meanwhile
    code, out = await asyncio.to_thread(run, ["git", "ls-remote", remote, f"refs/heads/{branch}"], timeout=30, env=env)
    sha = re.search(r"^([0-9a-f]{40})\s+refs/heads/", out or "", re.M)
    if code != 0 or not sha:
        print(f"update check: git ls-remote {remote} -> {code}: {out[-300:]}", flush=True)
        data["error"] = f"could not reach {remote}: {out[-200:] or 'no answer'}"
        return data
    data["latest"] = data["head"] = sha.group(1)
    # Only versions that passed GitHub's tests are offered (update.sh checks the same as root): the
    # newest commit of main can be red for a while when several changes land at once.
    repo = github_repo(remote)
    if repo:
        until, limited, answered = now + _FAIL_PAUSE, False, False
        try:
            green, data["head_state"] = pick_green(await green_runs(repo, branch), branch, data["head"])
            if not green:
                green = pick_green(await green_runs(repo, branch, passed=True), branch, None)[0]
            answered = True
        except GitHubRefused as e:
            green, limited = None, e.until is not None
            until = e.until or until
            if limited:
                print(f"update check: GitHub rate limit reached (HTTP {e.status}), next check after "
                      f"{time.strftime('%H:%M', time.localtime(until))}", flush=True)
            else:
                print(f"update check: GitHub test results not readable: HTTP {e.status}", flush=True)
        except (httpx.HTTPError, ValueError) as e:
            print(f"update check: GitHub test results not readable: {type(e).__name__}", flush=True)
            green = None
        if not green:
            if limited:
                data["error"] = ("GitHub beantwortet gerade keine Abfragen mehr (Grenze von 60 pro Stunde erreicht). "
                                 f"Nächste Prüfung ab {time.strftime('%H:%M', time.localtime(until))}; "
                                 "solange wird nichts installiert.")
            elif answered:
                data["no_green"] = True
                data["error"] = ("Auf GitHub hat noch keine Version die Tests bestanden; "
                                 "ohne bestandene Tests wird nichts installiert")
            else:
                data["error"] = "GitHub-Testergebnisse nicht abrufbar; ohne sie wird nichts installiert"
            data["latest"] = None
            return _remember_failure(data, until, limited)
        data["latest"] = green
    if data["latest"] == ver.get("commit"):
        data["behind"] = 0
    else:
        if repo and ver.get("commit"):
            try:
                url = f"https://api.github.com/repos/{repo}/compare/{ver['commit']}...{data['latest']}"
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await ghtoken.get(c, url, headers={"Accept": "application/vnd.github+json"})
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
    _failed.update(until=0.0, data=None, limited=False)
    _remote_cache.update(time=time.time(), data=data)
    return data


# ---------------------------------------------------------------- update lock
# update.sh writes its progress to this file; while it runs the panel refuses changes (all
# mutating requests except the ones the assistant needs) and the page shows a locked progress bar.
UPDATE_PROGRESS = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"),
                               "update-progress.json")
UPDATE_TIMEOUT = 45 * 60  # then the page offers to wait or cancel (the unit itself may run 2 h)
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


UNLOCKED = ("/api/chat", "/api/test/asr", "/api/assistant/", "/api/watch/", "/api/esp32/", "/api/iphone/", "/api/login", "/api/logout",
            "/api/profile/login", "/api/profile/logout", "/api/update")


async def update_lock(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and not request.url.path.startswith(UNLOCKED) and await asyncio.to_thread(update_running):
        return Response('{"detail": "update running: changes are locked until it has finished"}',
                        status_code=423, media_type="application/json", headers={"Retry-After": "60"})
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
    code, out = await asyncio.to_thread(run, ["systemctl", "show", "speech-spark-update", "-p",
                                              "ActiveState,Result,ExecMainExitTimestamp"])
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"installed": installed_version(), "previous": previous_version(), "remote": await remote_state(force=check),
            "running": props.get("ActiveState") in ("activating", "active"),
            "last_result": props.get("Result"), "last_finished": props.get("ExecMainExitTimestamp") or None,
            "talking": talking(), "night": night_on()}


def _backup_first(why):
    try:
        backup.create(why)
    except Exception as e:  # a failed backup does not block the update, but it is noted
        guard.log("backup_failed", detail=f"{type(e).__name__}: {e}"[:200])


@router.post("/api/update", dependencies=[Depends(auth)])
def start_update():
    import live
    live.mark("Update", "Update gestartet")
    _backup_first("before-update")
    return _start()


@router.post("/api/update/rollback", dependencies=[Depends(auth), Depends(admin_code)])
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


# ---------------------------------------------------------------- somebody is talking, overnight install
BUSY_S = 120          # speech within this many seconds counts as "a conversation is going on"
NIGHT = (3, 5)        # "Heute Nacht einspielen": from 03:00 to before 05:00 (the Spark's local time)
NIGHT_RETRY = 900     # GitHub not reachable: ask again after this many seconds, within the same night
NIGHT_FILE = os.path.join(os.path.dirname(UPDATE_PROGRESS), "update-night.json")
_night = {"asked": 0.0}


def talking(now=None):
    """Whether somebody talked with the Spark lately (ASR, TTS or a streamed answer; vorrang.py), and how
    many seconds ago. The update button asks before it interrupts that."""
    import vorrang
    now = time.time() if now is None else now
    last = vorrang.last_speech()
    ago = int(now - last) if last else None
    return {"now": ago is not None and 0 <= ago < BUSY_S, "ago": ago}


def night_on():
    """Admin switch panel.update_night (Einstellungen → Update), off by default."""
    from common import load_config
    return load_config().get("panel", {}).get("update_night", False) is True


def _night_day():
    try:
        with open(NIGHT_FILE) as f:
            d = json.load(f)
        return str(d.get("day", "")) if isinstance(d, dict) else ""
    except (OSError, ValueError):
        return ""


def _night_done(day):
    try:
        with open(NIGHT_FILE + ".part", "w") as f:
            json.dump({"day": day}, f)
        os.replace(NIGHT_FILE + ".part", NIGHT_FILE)
    except OSError:
        pass


async def night_once(now=None):
    """Called every minute: with the switch on, between 03:00 and 05:00, once a night, while nobody talks,
    a newer version that passed GitHub's tests is installed (backup first, like the button). Returns a fixed
    word for the tests: "" (nothing to do), "talking", "running", "retry", "current" or "started"."""
    now = time.time() if now is None else now
    if not night_on():
        return ""
    t = time.localtime(now)
    day = time.strftime("%Y-%m-%d", t)
    if not NIGHT[0] <= t.tm_hour < NIGHT[1] or _night_day() == day:
        return ""
    import notaus
    if notaus.blocks("auto") or notaus.blocks("internet"):   # Notaus: nothing by itself, nothing from outside
        return ""
    if talking(now)["now"]:
        return "talking"
    if await asyncio.to_thread(update_running):
        return "running"
    if 0 <= now - _night["asked"] < NIGHT_RETRY:
        return "retry"
    _night["asked"] = now
    remote = await remote_state(force=True)
    if remote.get("error"):
        return "retry"
    _night_done(day)
    if not remote.get("latest") or remote.get("behind") in (0, None):
        return "current"
    version = remote.get("version") or str(remote["latest"])[:7]
    import live
    live.mark("Update", f"Update in der Nacht gestartet: {version}")
    await asyncio.to_thread(_backup_first, "before-update")
    _start()
    guard.log("update_night", detail=str(version)[:40])
    print("update: started overnight,", version, flush=True)
    return "started"


# ---------------------------------------------------------------- changelog
# "Was ist neu": CHANGELOG.md of the installed version (install.sh puts a copy into app/; in a checkout it is
# the one at the repository root). One line per version; read only, plain text to the page (never HTML).
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOG_FILES = (os.path.join(APP_DIR, "CHANGELOG.md"), os.path.join(APP_DIR, "..", "CHANGELOG.md"))
CHANGELOG_MAX_BYTES = 2_000_000
CHANGELOG_MAX_ENTRIES = 3000
CHANGELOG_MAX_TEXT = 2000
_CL_LINE = re.compile(r"- (?:\*\*(V\d{1,3}\.\d{1,4}\.\d{1,6})\*\* · )?(\d{4}-\d{2}-\d{2}) · (.+)")
_cl_cache = {"key": None, "entries": []}


def parse_changelog(text):
    """[{version, date, text}] newest first, from the lines "- **V01.0.351** · 2026-10-11 · text" (older ones
    without a version); every other line is skipped, the text loses its ** marks and is cut to a fixed length."""
    out = []
    for line in str(text or "").splitlines():
        m = _CL_LINE.fullmatch(line.strip())
        if not m:
            continue
        txt = m.group(3).replace("**", "").strip()
        if len(txt) > CHANGELOG_MAX_TEXT:
            txt = txt[:CHANGELOG_MAX_TEXT - 1].rstrip() + "…"
        out.append({"version": m.group(1), "date": m.group(2), "text": txt})
        if len(out) >= CHANGELOG_MAX_ENTRIES:
            break
    return out


def changelog():
    """The parsed changelog (cached until the file changes), [] when there is none."""
    for path in CHANGELOG_FILES:
        try:
            st = os.stat(path, follow_symlinks=False)
        except OSError:
            continue
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        key = (path, st.st_mtime_ns, st.st_size)
        if _cl_cache["key"] != key:
            with open(path, "rb") as f:
                raw = f.read(CHANGELOG_MAX_BYTES)
            _cl_cache.update(key=key, entries=parse_changelog(raw.decode("utf-8", "replace")))
        return _cl_cache["entries"]
    return []


@router.get("/api/changelog")
def changelog_api(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    """For the admin and every profile in its own browser login (no guests, no device keys)."""
    if is_admin(request, creds):
        guard.limit(request, "changelog", admin=True)
    else:
        guard.limit(request, "changelog", browser_profile(request)["id"])
    return {"version": app_version(), "entries": changelog()}
