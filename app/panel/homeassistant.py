"""Home Assistant per profile: each profile connects its own Home Assistant (address and long-lived
access token); only that profile's requests can use it, guests never.

    USERS_DIR/<user id>/homeassistant.json  {"url", "token", "verify", "agent", "language"}

Commands go to Home Assistant's own Assist (POST /api/conversation/process), so Home Assistant
decides what is allowed: only the entities exposed to Assist (Settings → Voice assistants →
Expose) can be switched or asked about, and the token's user rights apply. The token never leaves
the Spark again: the panel only learns whether one is stored.
"""
import json
import re
import threading
import time

import httpx

import profiles

_lock = threading.Lock()


def _file(uid):
    return profiles._path(uid, "homeassistant.json")


def get(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("url") and d.get("token") else None
    except (OSError, ValueError):
        return None


def public(uid):
    d = get(uid)
    return {"url": d["url"], "verify": d.get("verify", True), "agent": d.get("agent", ""),
            "has_token": True} if d else {"url": "", "verify": True, "agent": "", "has_token": False}


def entry(body, old=None):
    """A checked connection from the panel's form; an empty token keeps the stored one."""
    url = str(body.get("url", "")).strip().rstrip("/")
    if not re.fullmatch(r"https?://[^\s/]{1,200}(/[^\s]{0,200})?", url, re.I):
        raise ValueError("the address must start with http:// or https://, e.g. http://homeassistant.local:8123")
    token = str(body.get("token", "")).strip() or (old or {}).get("token", "")
    if not re.fullmatch(r"[\w.\-]{20,1000}", token):
        raise ValueError("a long-lived access token is required (Home Assistant: your profile → Security)")
    agent = str(body.get("agent", "")).strip()
    if agent and not re.fullmatch(r"[\w.\-]{1,100}", agent):
        raise ValueError("invalid agent id")
    return {"url": url, "token": token, "verify": body.get("verify", True) is not False, "agent": agent}


def save(uid, item):
    with _lock:
        profiles._write(_file(uid), dict(item, updated=int(time.time())))
    return public(uid)


def remove(uid):
    with _lock:
        try:
            import os
            os.remove(_file(uid))
        except OSError:
            pass
    return public(uid)


def _client(item):
    return httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), verify=item.get("verify", True),
                             headers={"Authorization": f"Bearer {item['token']}"})


async def check(item):
    """Raises ValueError with a readable reason when Home Assistant cannot be used."""
    try:
        async with _client(item) as c:
            r = await c.get(item["url"] + "/api/")
    except httpx.HTTPError as e:
        raise ValueError(f"Home Assistant not reachable: {type(e).__name__}")
    if r.status_code == 401:
        raise ValueError("Home Assistant rejected the token (401)")
    if r.status_code != 200:
        raise ValueError(f"Home Assistant answered HTTP {r.status_code}")
    try:
        r.json()
    except ValueError:
        raise ValueError("this address does not look like Home Assistant (no JSON from /api/)")
    return {"ok": True}


async def command(item, text, language="de"):
    """Hands one spoken command to Home Assistant's Assist; returns (ok, answer, targets)."""
    body = {"text": str(text)[:500], "language": language}
    if item.get("agent"):
        body["agent_id"] = item["agent"]
    async with _client(item) as c:
        r = await c.post(item["url"] + "/api/conversation/process", json=body)
    if r.status_code == 401:
        return False, "Home Assistant rejected the token.", []
    r.raise_for_status()
    res = (r.json() or {}).get("response") or {}
    speech = ((res.get("speech") or {}).get("plain") or {}).get("speech", "")
    data = res.get("data") or {}
    targets = [x.get("name") for x in (data.get("success") or data.get("targets") or []) if x.get("name")]
    failed = [x.get("name") for x in data.get("failed") or [] if x.get("name")]
    ok = res.get("response_type") != "error" and not failed
    if failed:
        speech += " Failed: " + ", ".join(failed)
    return ok, speech.strip() or ("Done." if ok else "Home Assistant could not do that."), targets[:10]
