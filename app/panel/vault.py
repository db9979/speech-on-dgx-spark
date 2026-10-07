"""Secrets at rest: calendar passwords and Home Assistant tokens are stored encrypted, so a copy of
the profile folders (a backup, a look into the files) does not reveal them.

The key lives in STATE/secret.key (only the panel's user can read it), apart from the profile
folders and not part of a backup: a backup restored on another Spark keeps everything except these
secrets, which then have to be entered again. Values are "enc1:<Fernet token>"; older plain values
still read and get encrypted the next time they are saved.
"""
import os
import threading

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # the panel still works, the secrets stay as they were
    Fernet = None
    InvalidToken = ValueError

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
KEY_FILE = os.path.join(STATE, "secret.key")
PREFIX = "enc1:"
_lock = threading.Lock()
_fernet = None


def _key():
    global _fernet
    if _fernet or not Fernet:
        return _fernet
    with _lock:
        try:
            with open(KEY_FILE, "rb") as f:
                key = f.read().strip()
        except FileNotFoundError:
            os.makedirs(STATE, exist_ok=True)
            key = Fernet.generate_key()
            with open(os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                f.write(key)
        _fernet = Fernet(key)
    return _fernet


def seal(value):
    if not value or str(value).startswith(PREFIX):
        return value
    f = _key()
    return PREFIX + f.encrypt(str(value).encode()).decode() if f else value


def open_(value):
    """The plain secret; "" when it cannot be read (other key, e.g. after a restore elsewhere)."""
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    f = _key()
    if not f:
        return ""
    try:
        return f.decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        return ""


def available():
    return Fernet is not None
