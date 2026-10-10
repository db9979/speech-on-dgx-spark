"""Backups of everything the panel keeps: profiles (memory, conversations, documents, calendars, mail,
Home Assistant, voices of speaker ID), cloned voices, settings, the panel password and the shared
state of this Spark (admin second step, iPhone push key and device tokens, Telegram bot, browser push
key, ESP32 speakers, agent services, own quality test questions).

    BACKUP_DIR/speech-spark-<YYYYmmdd-HHMMSS>[-<why>].tar.gz

One automatic backup a day (and one before every update, rollback or restore): the newest KEEP
daily/manual ones and the newest KEEP_EVENT of the others are kept, so a few updates never push
the daily backups out. A backup holds
users/ (without the messages between profiles), voices/, config.json, state/panel-password and the files in STATE_FILES. The key for the
encrypted secrets (state/secret.key) is not in it: restored on this Spark everything works, restored
on another one calendar and mail passwords, tokens and keys have to be entered again.

A move backup ("Umzug", create(..., password=...)) also carries that key, sealed with a password the
admin types (scrypt + Fernet, state/move-keys.json); restoring it needs the same password and then
works on another Spark without entering anything again. The login keys of this Spark (users/secret,
admin-session.key) are never in any backup: everyone signs in again after a move.

Restore unpacks everything first (size capped), checks config.json like the settings page does,
makes a backup of the current state ("before-restore"), then swaps users/, voices/, config.json and
the state files;
if one step fails, the parts already swapped are put back. The speech services pick up restored
settings at their next start.
"""
import base64
import hashlib
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
# shared state of this Spark (not the logs, counters, lockouts or login keys); name -> kind
STATE_FILES = {
    "mfa-admin.json": "json",       # the admin's second step (secret sealed with secret.key)
    "apns.json": "json",            # iPhone push: Apple key (sealed), key id, team
    "apns-tokens.json": "json",     # iPhone push: the devices' tokens
    "telegram.json": "json",        # Telegram bot (token sealed)
    "vapid.pem": "pem",             # browser push key: the browsers' push subscriptions belong to it
    "esp32.json": "json",           # ESP32 speakers: board variant, firmware, automatic updates
    "agent.json": "json",           # agent levels and MCP services (tokens sealed)
    "personen-vorrang.json": "json",  # priority for people: the stage the admin gave each profile (stufe.py)
    "quality-cases.json": "json",   # own quality test questions
    "quality-history.json": "json",
    "setup.json": "json",           # first-start wizard done
    "doc-quotas.json": "json",      # the admin's own document space per profile (wissen.py)
    "admins.json": "json",          # profiles as admins: roles, the switch, who hears of admin modes (coadmin.py)
    "features-seen.json": "json",   # when each function was first on ("Neu, noch nie an", features.py)
    "join.json": "json",            # new people by invitation: the switch, invitations (code hashes), packs (join.py)
}
MAX_STATE_FILE = 8 * 1024**2
MOVE_FILE = "move-keys.json"
MOVE_MIN, MOVE_MAX = 12, 200        # password length
SCRYPT = {"n": 2**15, "r": 8, "p": 1}


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
                if arc == "users" and re.match(r"[^/]+/messages(\.json|-pending\.json|/)", os.path.relpath(full, path)):
                    continue  # messages between profiles are short-lived (messages.py): not in backups
                if f.endswith((".db-journal", ".db-wal", ".db-shm")):
                    continue  # (an SQLite file is copied whole below)
                if f.endswith(".db"):
                    # an SQLite file (documents, wissen.db) may be written right now: a consistent copy
                    import documents
                    with tempfile.TemporaryDirectory() as tmp:
                        copy = os.path.join(tmp, "copy.db")
                        documents.sqlite_copy(full, copy)
                        tar.add(copy, arcname=os.path.join(arc, os.path.relpath(full, path)), recursive=False)
                    continue
                tar.add(full, arcname=os.path.join(arc, os.path.relpath(full, path)), recursive=False)


def _move_key(password, salt, n, r, p):
    raw = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024**2, dklen=32)
    return base64.urlsafe_b64encode(raw)


def _seal_keys(password):
    """state/move-keys.json: this Spark's vault key, sealed with the admin's password."""
    from cryptography.fernet import Fernet
    import vault
    vault._key()  # makes the key file when there is none yet
    with open(vault.KEY_FILE, "rb") as f:
        key = f.read().strip()
    salt = os.urandom(16)
    token = Fernet(_move_key(password, salt, **SCRYPT)).encrypt(json.dumps({"secret.key": key.decode()}).encode())
    return json.dumps({"v": 1, "kdf": "scrypt", **SCRYPT, "salt": base64.b64encode(salt).decode(),
                       "keys": token.decode()}).encode()


def _open_keys(raw, password):
    """The vault key from a move backup; ValueError for a wrong password or a broken file."""
    from cryptography.fernet import Fernet, InvalidToken
    try:
        d = json.loads(raw)
        n, r, p = int(d["n"]), int(d["r"]), int(d["p"])
        salt = base64.b64decode(d["salt"], validate=True)
        token = d["keys"].encode()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("the move keys in the backup are damaged")
    # only the cost this panel writes (a file must not make the Spark compute for minutes)
    if d.get("kdf") != "scrypt" or (n, r, p) != (SCRYPT["n"], SCRYPT["r"], SCRYPT["p"]) or len(salt) != 16:
        raise ValueError("the move keys in the backup are damaged")
    try:
        keys = json.loads(Fernet(_move_key(password, salt, n, r, p)).decrypt(token))
        key = keys["secret.key"].encode()
        Fernet(key)
    except InvalidToken:
        raise ValueError("wrong password for this move backup")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("the move keys in the backup are damaged")
    return key


def check_password(password):
    if not isinstance(password, str) or not MOVE_MIN <= len(password) <= MOVE_MAX:
        raise ValueError(f"the password needs {MOVE_MIN} to {MOVE_MAX} characters")


def _add_bytes(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size, info.mtime = len(data), int(time.time())
    tar.addfile(info, io.BytesIO(data))


def create(why="", password=None):
    """Writes a backup and returns its entry; keeps the newest KEEP. With a password it is a move
    backup that also carries the vault key, sealed with that password."""
    if password is not None:
        check_password(password)
        why = "move"
    with _lock:
        os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)
        name = time.strftime("speech-spark-%Y%m%d-%H%M%S") + (f"-{why}" if why else "") + ".tar.gz"
        path = os.path.join(BACKUP_DIR, name)
        tmp = path + ".part"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            with tarfile.open(fileobj=f, mode="w:gz") as tar:
                meta = json.dumps({"created": int(time.time()), "why": why, "format": 1}).encode()
                _add_bytes(tar, "backup.json", meta)
                if password is not None:
                    _add_bytes(tar, "state/" + MOVE_FILE, _seal_keys(password))
                _add_dir(tar, USERS, "users")
                _add_dir(tar, VOICES, "voices")
                if os.path.exists(CONFIG_PATH):
                    tar.add(CONFIG_PATH, arcname="config.json")
                pw = os.path.join(STATE, "panel-password")
                if os.path.exists(pw):
                    tar.add(pw, arcname="state/panel-password")
                for sf in STATE_FILES:
                    full = os.path.join(STATE, sf)
                    if os.path.isfile(full) and not os.path.islink(full):
                        tar.add(full, arcname="state/" + sf, recursive=False)
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


ALLOWED = re.compile(r"(backup\.json|config\.json|state/panel-password|state/(%s)|users/[\w.\-/]+|voices/[\w.\-/ ]+)"
                     % "|".join(re.escape(n) for n in list(STATE_FILES) + [MOVE_FILE]))


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


def restore(fileobj, check_config=None, password=None):
    """Restores a backup (file object of a .tar.gz); returns what was restored.

    check_config(dict) -> dict: checks the backup's settings (and may fill newer keys); it raises
    ValueError when they are not acceptable, and nothing is changed then. A move backup needs its
    password; a wrong one changes nothing."""
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
            key = None
            moved = os.path.join(work, "state", MOVE_FILE)
            if os.path.exists(moved):
                if not password:
                    raise ValueError("this is a move backup: enter the password it was made with")
                with open(moved, "rb") as f:
                    key = _open_keys(f.read(4096), password)
                os.remove(moved)
            notes = _check_state(work, key)
            create("before-restore")
            with _lock:
                return _swap(work, new_cfg, key) + notes
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _active_key(key):
    if key:
        return key
    import vault
    try:
        with open(vault.KEY_FILE, "rb") as f:
            return f.read().strip()
    except OSError:
        return None


def _opens(sealed, key):
    """True when a sealed value can be read with key (plain values always can)."""
    import vault
    if not isinstance(sealed, str) or not sealed.startswith(vault.PREFIX):
        return True
    try:
        from cryptography.fernet import Fernet
        Fernet(key).decrypt(sealed[len(vault.PREFIX):].encode())
        return True
    except Exception:
        return False


def _check_state(work, key):
    """Checks the state files of the backup; drops what would do harm here. Returns notes."""
    notes = []
    for name, kind in STATE_FILES.items():
        full = os.path.join(work, "state", name)
        if not os.path.exists(full):
            continue
        if os.path.getsize(full) > MAX_STATE_FILE:
            raise ValueError(f"state/{name} in the backup is too large")
        with open(full, "rb") as f:
            raw = f.read()
        if kind == "json":
            try:
                d = json.loads(raw)
            except ValueError:
                raise ValueError(f"state/{name} in the backup is not valid")
            if not isinstance(d, (dict, list)):
                raise ValueError(f"state/{name} in the backup is not valid")
            if name == "mfa-admin.json":
                # a second step whose secret cannot be read here would only leave the recovery codes:
                # then the admin keeps the second step of this Spark
                k = _active_key(key)
                if not isinstance(d, dict) or not k or not _opens(d.get("secret"), k):
                    os.remove(full)
                    notes.append("admin-mfa-kept")
        else:
            try:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import ec
                pk = serialization.load_pem_private_key(raw, None)
                if not isinstance(pk, ec.EllipticCurvePrivateKey):
                    raise ValueError
            except ImportError:
                os.remove(full)
                continue
            except (ValueError, TypeError):
                raise ValueError(f"state/{name} in the backup is not valid")
    return notes


def _forget_cached():
    """Modules that keep a key in memory read it again."""
    import sys
    for mod, attr, empty in (("vault", "_fernet", None), ("push", "_key", None), ("apns", "_jwt", (0.0, "", ""))):
        m = sys.modules.get(mod)
        if m is not None and hasattr(m, attr):
            setattr(m, attr, empty)


def _swap(work, new_cfg, key=None):
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
        files = [(os.path.join(work, "state", n), n) for n in STATE_FILES]
        files = [(src, n) for src, n in files if os.path.exists(src)]
        if key:
            import vault
            files.append((key, os.path.basename(vault.KEY_FILE)))
        for src, name in files:
            os.makedirs(STATE, exist_ok=True)
            target = os.path.join(STATE, name)
            prev = None
            if os.path.exists(target):
                with open(target, "rb") as f:
                    prev = f.read()
            tmp = target + ".tmp"
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "wb") as f:
                if isinstance(src, bytes):
                    f.write(src)
                else:
                    with open(src, "rb") as g:
                        f.write(g.read())
            os.replace(tmp, target)
            undo.append((target, ("file", prev)))
        if files:
            done.append("state")
        if key:
            done.append("keys")
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
                if isinstance(old, tuple):  # a state file: its old content, or None when there was none
                    if old[1] is None:
                        os.remove(target)
                    else:
                        with open(target, "wb") as f:
                            f.write(old[1])
                    continue
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
    finally:
        _forget_cached()
    for target, old in undo:
        if target != CONFIG_PATH and isinstance(old, str):
            shutil.rmtree(old, ignore_errors=True)
    return done
