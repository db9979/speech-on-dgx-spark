"""Backups of everything the panel keeps: profiles (memory, conversations, documents, calendars, mail,
Home Assistant, voices of speaker ID), cloned voices, settings and the panel password.

    BACKUP_DIR/speech-spark-<YYYYmmdd-HHMMSS>[-<why>].tar.gz

One automatic backup a day (and one before every update, rollback or restore): the newest KEEP
daily/manual ones and the newest KEEP_EVENT of the others are kept, so a few updates never push
the daily backups out. A backup holds
users/, voices/, config.json and state/panel-password. The key for the encrypted secrets
(state/secret.key) is not in it: restored on this Spark everything works, restored on another one
calendar and mail passwords and Home Assistant tokens have to be entered again.

Restore unpacks everything first (size capped), checks config.json like the settings page does,
makes a backup of the current state ("before-restore"), then swaps users/, voices/ and config.json;
if one step fails, the parts already swapped are put back. The speech services pick up restored
settings at their next start.
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
KEEP_EVENT = 5
REGULAR = ("", "daily", "manual")
DAILY = 86400
NAME = re.compile(r"speech-spark-\d{8}-\d{6}(-[a-z\-]{1,20})?\.tar\.gz")
MAX_UPLOAD = 2 * 1024**3
MAX_UNPACKED = 8 * 1024**3  # a small archive must not unpack into a full disk
_lock = threading.Lock()


def _add_dir(tar, path, arc):
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.endswith(".tmp"):
                    continue
                full = os.path.join(root, f)
                if arc == "users" and os.path.relpath(full, path) == "secret":
                    continue  # the login key of this Spark: with it, a backup file could forge profile logins
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
        _prune()
        return next(x for x in listing() if x["name"] == name)


def _prune():
    """Keeps the newest KEEP daily/manual backups and the newest KEEP_EVENT of the others."""
    items = listing()
    regular = [x for x in items if (x["why"] if x["why"] != "-" else "") in REGULAR]
    events = [x for x in items if x not in regular]
    for old in regular[KEEP:] + events[KEEP_EVENT:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old["name"]))
        except OSError:
            pass


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
    total = sum(m.size for m in members)
    if total > MAX_UNPACKED:
        raise ValueError("the backup unpacks to more than 8 GB")
    free = shutil.disk_usage(BASE if os.path.isdir(BASE) else "/").free
    if total * 2 + 512 * 1024**2 > free:  # unpacked copy + the swapped-in copy + some room
        raise ValueError("not enough free disk space to restore this backup")
    return members


def restore(fileobj, check_config=None):
    """Restores a backup (file object of a .tar.gz); returns what was restored.

    check_config(dict) -> dict: checks the backup's settings (and may fill newer keys); it raises
    ValueError when they are not acceptable, and nothing is changed then."""
    with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
        members = _check(tar)
        work = tempfile.mkdtemp(prefix="restore-", dir=BASE if os.path.isdir(BASE) else None)
        try:
            for m in members:
                m.mode = 0o600
                tar.extract(m, work, filter="data")
            new_cfg = None
            cfg = os.path.join(work, "config.json")
            if os.path.exists(cfg):
                with open(cfg) as f:
                    new_cfg = json.load(f)  # must be valid JSON
                if not isinstance(new_cfg, dict):
                    raise ValueError("config.json in the backup is not a settings file")
                if check_config:
                    new_cfg = check_config(new_cfg)
            create("before-restore")
            with _lock:
                return _swap(work, new_cfg)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _swap(work, new_cfg):
    """Puts the unpacked parts in place; on an error the parts already swapped are put back."""
    done, undo = [], []
    try:
        for sub, target in (("users", USERS), ("voices", VOICES)):
            src = os.path.join(work, sub)
            if os.path.isdir(src):
                staged, old = target + ".new", target + ".old"
                shutil.rmtree(staged, ignore_errors=True)
                shutil.rmtree(old, ignore_errors=True)
                shutil.copytree(src, staged)
                os.chmod(staged, 0o700)
                if sub == "users":
                    # keep this Spark's own login key (older backups still carry one)
                    try:
                        os.remove(os.path.join(staged, "secret"))
                    except OSError:
                        pass
                    if os.path.exists(os.path.join(target, "secret")):
                        shutil.copy2(os.path.join(target, "secret"), os.path.join(staged, "secret"))
                had = os.path.isdir(target)
                if had:
                    os.replace(target, old)
                os.replace(staged, target)
                undo.append((target, old if had else None))
                done.append(sub)
        if new_cfg is not None:
            prev = None
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "rb") as f:
                    prev = f.read()
            tmp = CONFIG_PATH + ".tmp"
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640), "w") as f:
                json.dump(new_cfg, f, indent=2)
            os.replace(tmp, CONFIG_PATH)
            undo.append((CONFIG_PATH, prev))
            done.append("config")
        pw = os.path.join(work, "state", "panel-password")
        if os.path.exists(pw):
            os.makedirs(STATE, exist_ok=True)
            tmp = os.path.join(STATE, "panel-password.tmp")
            shutil.copyfile(pw, tmp)
            os.chmod(tmp, 0o600)
            os.replace(tmp, os.path.join(STATE, "panel-password"))
            done.append("password")
    except Exception:
        for target, old in reversed(undo):
            try:
                if target == CONFIG_PATH:
                    if old is not None:
                        with open(CONFIG_PATH, "wb") as f:
                            f.write(old)
                    continue
                shutil.rmtree(target, ignore_errors=True)
                if old:
                    os.replace(old, target)
            except OSError:
                pass
        raise
    for target, old in undo:
        if target != CONFIG_PATH and old:
            shutil.rmtree(old, ignore_errors=True)
    return done
