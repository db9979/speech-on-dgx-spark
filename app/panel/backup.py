"""Backups of everything the panel keeps: profiles (memory, conversations, documents, calendars,
Home Assistant, voices of speaker ID), cloned voices, settings and the panel password.

    BACKUP_DIR/speech-spark-<YYYYmmdd-HHMMSS>[-<why>].tar.gz

One automatic backup a day (and one before every update), the newest KEEP are kept. A backup holds
users/, voices/, config.json and state/panel-password. The key for the encrypted secrets
(state/secret.key) is not in it: restored on this Spark everything works, restored on another one
calendar passwords and Home Assistant tokens have to be entered again.

Restore first makes a backup of the current state ("before-restore"), then replaces users/ and
voices/ and writes config.json; the speech services pick up restored settings at their next start.
"""
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import threading
import time

from common import CONFIG_PATH

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
BASE = os.path.dirname(STATE.rstrip("/"))
BACKUP_DIR = os.environ.get("SPEECH_SPARK_BACKUPS", os.path.join(BASE, "backups"))
USERS = os.environ.get("SPEECH_SPARK_USERS", os.path.join(BASE, "users"))
VOICES = os.environ.get("SPEECH_SPARK_VOICES", os.path.join(BASE, "voices"))
KEEP = 7
DAILY = 86400
NAME = re.compile(r"speech-spark-\d{8}-\d{6}(-[a-z\-]{1,20})?\.tar\.gz")
MAX_UPLOAD = 2 * 1024**3
_lock = threading.Lock()


def _add_dir(tar, path, arc):
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.endswith(".tmp"):
                    continue
                full = os.path.join(root, f)
                tar.add(full, arcname=os.path.join(arc, os.path.relpath(full, path)), recursive=False)


def create(why=""):
    """Writes a backup and returns its entry; keeps the newest KEEP."""
    with _lock:
        os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)
        name = time.strftime("speech-spark-%Y%m%d-%H%M%S") + (f"-{why}" if why else "") + ".tar.gz"
        path = os.path.join(BACKUP_DIR, name)
        tmp = path + ".part"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            with tarfile.open(fileobj=f, mode="w:gz") as tar:
                meta = json.dumps({"created": int(time.time()), "why": why, "format": 1}).encode()
                info = tarfile.TarInfo("backup.json")
                info.size, info.mtime = len(meta), int(time.time())
                tar.addfile(info, io.BytesIO(meta))
                _add_dir(tar, USERS, "users")
                _add_dir(tar, VOICES, "voices")
                if os.path.exists(CONFIG_PATH):
                    tar.add(CONFIG_PATH, arcname="config.json")
                pw = os.path.join(STATE, "panel-password")
                if os.path.exists(pw):
                    tar.add(pw, arcname="state/panel-password")
        os.replace(tmp, path)
        for old in listing()[KEEP:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old["name"]))
            except OSError:
                pass
        return next(x for x in listing() if x["name"] == name)


def listing():
    try:
        names = [n for n in os.listdir(BACKUP_DIR) if NAME.fullmatch(n)]
    except OSError:
        return []
    out = []
    for n in sorted(names, reverse=True):
        st = os.stat(os.path.join(BACKUP_DIR, n))
        m = NAME.fullmatch(n)
        out.append({"name": n, "size": st.st_size, "created": int(st.st_mtime),
                    "why": (m.group(1) or "-")[1:]})
    return out


def path_of(name):
    if not NAME.fullmatch(name or "") or not os.path.exists(os.path.join(BACKUP_DIR, name)):
        raise FileNotFoundError(name)
    return os.path.join(BACKUP_DIR, name)


def remove(name):
    os.remove(path_of(name))


def due():
    last = listing()
    return not last or time.time() - last[0]["created"] > DAILY


ALLOWED = re.compile(r"(backup\.json|config\.json|state/panel-password|users/[\w.\-/]+|voices/[\w.\-/ ]+)")


def _check(tar):
    """Only plain files and folders below the known places; nothing else is extracted."""
    members = []
    for m in tar.getmembers():
        n = m.name.lstrip("./")
        if m.isdir():
            continue
        if not m.isfile() or ".." in n.split("/") or not ALLOWED.fullmatch(n):
            raise ValueError(f"unexpected entry in the backup: {m.name[:80]}")
        members.append(m)
    if not any(m.name.lstrip("./") == "backup.json" for m in members):
        raise ValueError("this is not a backup of the panel (backup.json missing)")
    return members


def restore(fileobj):
    """Restores a backup (file object of a .tar.gz); returns what was restored."""
    with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
        members = _check(tar)
        work = tempfile.mkdtemp(prefix="restore-", dir=BASE if os.path.isdir(BASE) else None)
        try:
            for m in members:
                m.mode = 0o600
                tar.extract(m, work, filter="data")
            create("before-restore")
            with _lock:
                done = []
                for sub, target in (("users", USERS), ("voices", VOICES)):
                    src = os.path.join(work, sub)
                    if os.path.isdir(src):
                        old = target + ".old"
                        shutil.rmtree(old, ignore_errors=True)
                        if os.path.isdir(target):
                            os.replace(target, old)
                        shutil.copytree(src, target)
                        os.chmod(target, 0o700)
                        shutil.rmtree(old, ignore_errors=True)
                        done.append(sub)
                cfg = os.path.join(work, "config.json")
                if os.path.exists(cfg):
                    with open(cfg) as f:
                        json.load(f)  # must be valid JSON
                    shutil.copyfile(cfg, CONFIG_PATH + ".tmp")
                    os.chmod(CONFIG_PATH + ".tmp", 0o640)
                    os.replace(CONFIG_PATH + ".tmp", CONFIG_PATH)
                    done.append("config")
                pw = os.path.join(work, "state", "panel-password")
                if os.path.exists(pw):
                    os.makedirs(STATE, exist_ok=True)
                    shutil.copyfile(pw, os.path.join(STATE, "panel-password"))
                    done.append("password")
            return done
        finally:
            shutil.rmtree(work, ignore_errors=True)
