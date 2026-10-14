"""A read-only GitHub token for the Spark's own questions to api.github.com (Einstellungen → Update).

Without a token GitHub answers 60 questions per hour for every device behind the same internet connection
together; with one, 5000 for this token. It is a fine-grained token of the admin with "Public repositories"
and no permission, so it can read what anybody can read and change nothing. Only the main admin sets it,
with a fresh code; it lives sealed in the vault (STATE/github-token.json), is never shown or logged, and goes
only to https://api.github.com (never to a download address, never to a test address from the environment).
Asked: the update check, the device updates (XiaoZhi), the downloads of the Android app, the companion and
the speaker firmware. When GitHub refuses it (401: revoked or expired) the Spark asks without it again and
says so under Einstellungen → Update and on Zustand → Live, until a new one is saved.
The token for "Probleme melden" (meldung.py, write access to issues of one repository) stays a separate one.
"""
import json
import os
import re
import sys
import time

from fastapi import APIRouter, Depends, HTTPException, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guard  # noqa: E402
import vault  # noqa: E402
from common import write_json  # noqa: E402
from core import admin_code_fresh, auth, json_body  # noqa: E402

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
TOKEN_FILE = os.path.join(STATE, "github-token.json")
API = "https://api.github.com/"
TOKEN = re.compile(r"github_pat_[A-Za-z0-9_]{20,255}")
_state = {"refused": False, "t": 0, "ok": None, "why": "", "until": None, "limit": None}


def _read():
    try:
        with open(TOKEN_FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _token():
    try:
        t = vault.open_(_read().get("token", ""))
    except Exception:
        return ""
    return t if isinstance(t, str) and TOKEN.fullmatch(t) else ""


def auth_header(url):
    """The Authorization header for one question, only for https://api.github.com/… and only while GitHub
    did not refuse the token; else {} (the question goes without it, as before)."""
    if not isinstance(url, str) or not url.startswith(API) or _state["refused"]:
        return {}
    t = _token()
    return {"Authorization": f"Bearer {t}"} if t else {}


def used():
    """For Live and the update page: "mit Token", "Token abgelehnt" or "ohne Token" (fixed words)."""
    if not _token():
        return "ohne Token"
    return "Token abgelehnt" if _state["refused"] else "mit Token"


async def get(c, url, headers=None, **kw):
    """c.get(url) with the token when it may go there; GitHub refusing the token (401: revoked or expired)
    marks it and asks once more without it, so nothing gets worse than without a token."""
    plain = dict(headers or {})
    tok = auth_header(url)
    r = await c.get(url, headers={**plain, **tok}, **kw)
    if r.status_code == 401 and tok:
        _state.update(refused=True, ok=False, why="Token abgelehnt oder abgelaufen", t=int(time.time()))
        print("ghtoken: refused by GitHub (401), asking without it until a new one is saved", flush=True)
        r = await c.get(url, headers=plain, **kw)
    return r


def info():
    d = _read()
    return {"set": bool(_token()), "since": d.get("since"), "until": _state["until"] or d.get("until"),
            "checked": _state["t"] or None, "ok": _state["ok"], "why": _state["why"], "limit": _state["limit"],
            "used": used()}


def save(token, now=None):
    if not vault.available():
        raise HTTPException(503, "Verschlüsselung fehlt (python3-cryptography).")
    d = {"token": vault.seal(token), "since": int(time.time() if now is None else now), "until": None}
    write_json(TOKEN_FILE, d, mode=0o600)
    _state.update(refused=False, t=0, ok=None, why="", until=None, limit=None)


def drop():
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass
    _state.update(refused=False, t=0, ok=None, why="", until=None, limit=None)


async def _client():
    import netguard
    return netguard.client(netguard.PUBLIC, origin=API.rstrip("/"), max_bytes=64 * 1024, timeout=20)


async def check():
    """GET /rate_limit with the token (costs nothing of the limit): works, how many per hour, until when."""
    t = _token()
    if not t:
        _state.update(t=int(time.time()), ok=False, why="kein Token", limit=None)
        return info()
    try:
        async with await _client() as c:
            r = await c.get(API + "rate_limit", headers={"Authorization": f"Bearer {t}",
                                                         "Accept": "application/vnd.github+json"})
        ok = r.status_code == 200
        limit = None
        if ok:
            core = ((r.json() or {}).get("resources") or {}).get("core") or {}
            limit = core.get("limit") if isinstance(core.get("limit"), int) else None
        m = re.match(r"(\d{4}-\d{2}-\d{2})", r.headers.get("github-authentication-token-expiration", ""))
        why = "" if ok else {401: "Token abgelehnt oder abgelaufen"}.get(r.status_code, f"GitHub antwortet {r.status_code}")
        _state.update(t=int(time.time()), ok=ok, why=why, limit=limit, until=m.group(1) if m else None,
                      refused=r.status_code == 401)
    except Exception as e:
        _state.update(t=int(time.time()), ok=False, why="GitHub nicht erreichbar")
        print("ghtoken: check", type(e).__name__, flush=True)
    return info()


# ---------------------------------------------------------------- the admin (only the main admin sets it)
@router.get("/api/admin/ghtoken", dependencies=[Depends(auth)])
def admin_state(request: Request):
    guard.limit(request, "ghtoken", admin=True)
    return info()


@router.put("/api/admin/ghtoken", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_save(request: Request):
    guard.limit(request, "ghtoken", admin=True)
    tok = str((await json_body(request, 1024)).get("token") or "").strip()
    if not TOKEN.fullmatch(tok):
        raise HTTPException(400, "Nur ein fine-grained Token (beginnt mit github_pat_), nur „Public repositories“, ohne Rechte.")
    save(tok)
    guard.log("github_token", detail="GitHub-Token für Updates gesetzt")
    print("ghtoken: set", flush=True)
    return await check()


@router.delete("/api/admin/ghtoken", dependencies=[Depends(auth)])
def admin_drop(request: Request):
    guard.limit(request, "ghtoken", admin=True)
    drop()
    guard.log("github_token", detail="GitHub-Token für Updates entfernt")
    print("ghtoken: removed", flush=True)
    return info()


@router.post("/api/admin/ghtoken/check", dependencies=[Depends(auth)])
async def admin_check(request: Request):
    guard.limit(request, "ghtoken", admin=True)
    return await check()
