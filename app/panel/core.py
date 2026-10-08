"""Shared panel helpers: paths, logins (admin password, profiles) and small system calls."""
import os
import re
import hashlib
import hmac
import secrets
import subprocess
import sys
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guard  # noqa: E402
import profiles  # noqa: E402
from common import load_config  # noqa: E402


VOICES_DIR = os.environ.get("SPEECH_SPARK_VOICES", "/var/lib/speech-spark/voices")
PASSWORD = os.environ.get("PANEL_PASSWORD", "")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SERVICES = {"asr": "speech-spark-asr", "tts": "speech-spark-tts"}
# units the panel may start/stop/restart (matches /etc/sudoers.d/speech-spark)
UNITS = dict(SERVICES, **{"asr-engine": "speech-spark-asr-engine", "tts-engine": "speech-spark-tts-engine",
                          "tts-design": "speech-spark-tts-design"})
LOG_UNITS = dict(UNITS, panel="speech-spark-panel", update="speech-spark-update")
PREFIX = os.environ.get("SPEECH_SPARK_PREFIX", "/opt/speech-spark")
# asr keys the vLLM engine reads; changing them restarts it
ASR_ENGINE_KEYS = ("model", "engine_port", "engine_mem", "engine_max_seqs")
# tts keys that only the vllm-omni engine reads; changing them restarts the engine
ENGINE_KEYS = ("model", "engine_port", "engine_mem_talker", "engine_mem_code2wav", "engine_max_seqs",
               "engine_max_model_len", "initial_chunk_frames")
DESIGN_KEYS = ("voicedesign_enabled", "voicedesign_model", "voicedesign_port",
               "engine_mem_talker", "engine_mem_code2wav", "engine_max_seqs", "engine_max_model_len", "initial_chunk_frames")
# Units installed by github.com/hasso5703/dgx-spark-qwen38; only one lane runs at a time.
QWEN38_UNITS = ["qwen38-sglang", "qwen38-sglang-1m", "qwen38-flash", "qwen38-image",
                "qwen38-video", "qwen38-llamacpp", "qwen38-keepalive", "qwen38-dashboard"]
LANGS = ["auto", "Chinese", "English", "German", "French", "Spanish", "Italian", "Portuguese",
         "Russian", "Japanese", "Korean", "Dutch", "Polish", "Turkish", "Arabic"]
security = HTTPBasic(auto_error=False)


# Login: the voice assistant is open to everyone in the LAN (config chat.public), everything
# else needs the panel password. The browser logs in once and keeps a cookie; scripts can still
# send HTTP Basic. The password from the installer can be replaced in the panel; the new one is
# stored as a PBKDF2 hash in the state directory (the panel cannot write /etc).
PASSWORD_FILE = os.path.join(os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state"), "panel-password")
COOKIE = "speech_spark_admin"
# Browsers keep sending HTTP Basic credentials from the old login dialog; after "log out" this
# cookie makes the panel ignore them in that browser until the next password login.
NO_BASIC = "speech_spark_no_basic"


def _stored_hash():
    try:
        with open(PASSWORD_FILE) as f:
            salt, digest = f.read().split()
        return bytes.fromhex(salt), digest
    except (OSError, ValueError):
        return None


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


def password_set():
    return bool(_stored_hash() or PASSWORD)


def check_password(password):
    stored = _stored_hash()
    if stored:
        return secrets.compare_digest(_hash(password, stored[0]), stored[1])
    return bool(PASSWORD) and secrets.compare_digest(password.encode(), PASSWORD.encode())


# The admin login "<issued>.<signature>" is signed with the current password (changing it logs
# every browser out) and ends after ADMIN_IDLE seconds without use; the panel renews it while used.
ADMIN_IDLE = 7 * 86400
ADMIN_RENEW = 3600


def _session_token(issued=None):
    stored = _stored_hash()
    key = (stored[1] if stored else PASSWORD).encode()
    issued = int(issued or time.time())
    return f"{issued}." + hmac.new(key, f"speech-spark-admin-session:{issued}".encode(), hashlib.sha256).hexdigest()


def _admin_cookie_age(request: Request):
    """Seconds since the admin cookie was issued, or None when it is missing, wrong or expired."""
    raw = request.cookies.get(COOKIE, "")
    issued = raw.split(".", 1)[0]
    if not issued.isdigit() or time.time() - int(issued) > ADMIN_IDLE or guard.revoked(raw):
        return None
    return time.time() - int(issued) if secrets.compare_digest(raw, _session_token(issued)) else None


def is_admin(request: Request, creds: HTTPBasicCredentials | None):
    if not password_set():
        return True
    if creds and not request.cookies.get(NO_BASIC) and not guard.wait_left(request, guard.BASIC):
        if check_password(creds.password):
            return True
        guard.failed(request, guard.BASIC, what="admin_basic")
    return _admin_cookie_age(request) is not None


def admin_cookie_ok(request: Request):
    return not password_set() or _admin_cookie_age(request) is not None


def renewed_admin_cookie(request: Request):
    age = _admin_cookie_age(request)
    return _session_token() if age is not None and age > ADMIN_RENEW else None


def auth(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    if not is_admin(request, creds):
        raise HTTPException(401, "login required")


def assistant(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    """Voice chat endpoints: open when chat.public is on; otherwise for logged-in profiles (cookie or
    device key) and the admin, so guests are locked out but profiles can still sign in."""
    if load_config().get("chat", {}).get("public", False) or profiles.current(request):
        return
    auth(request, creds)


def run(cmd, timeout=10, env=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def unit_state(unit):
    out = run(["systemctl", "is-active", unit])[1].split("\n")[0].strip()
    return out if re.fullmatch(r"[a-z\-]+", out) else "unknown"


def unit_exists(unit):
    code, out = run(["systemctl", "list-unit-files", unit + ".service", "--no-legend"])
    return code == 0 and out.startswith(unit + ".service")


def app_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return ""


def own_profile(request: Request):
    prof = profiles.current(request)
    if not prof:
        raise HTTPException(401, "no profile")
    return prof


# Calendar and briefing topics: profiles only; the stored password is never sent back.
def calendar_on():
    if not load_config().get("chat", {}).get("calendar", True):
        raise HTTPException(403, "calendar and daily briefing are turned off")


# Home Assistant: each profile connects its own; the token is never sent back.
def ha_on():
    if not load_config().get("chat", {}).get("homeassistant", False):
        raise HTTPException(403, "Home Assistant is turned off")


# E-mail: each profile connects its own mailboxes, read only; the password is never sent back.
def mail_on():
    if not load_config().get("chat", {}).get("mail", False):
        raise HTTPException(403, "reading e-mail is turned off")


def speaker_on():
    if not load_config().get("chat", {}).get("speaker_id", False):
        raise HTTPException(403, "speaker identification is turned off")


def api_headers():
    key = load_config().get("api", {}).get("key", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


DEFAULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.default.json")
