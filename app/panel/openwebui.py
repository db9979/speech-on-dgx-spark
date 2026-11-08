"""Open WebUI einbinden (plan open-webui/plan.md, Dominik 2026-11-08 „1-2“): Open WebUI keeps running where it is
(home network, outside through the owner's proxy); the Spark only makes connecting it easy and watches it.

1. One step under Ich → Sprachmodell per API → „Open WebUI verbinden“ (with the code window): it makes one key for the
   language model (llmapi.add_key) and, when the profile may use the Spark as MCP server, one MCP connection with
   only the reading tools and „Spark fragen“ (mcpserver.add_key), both named „Open WebUI“ and both „nur Heimnetz“
   (Open WebUI asks the Spark from its own server in the home network, also when it is opened from outside).
   The two tokens are shown once with the fields to copy; „Trennen“ removes both at once. Connecting again
   replaces the old pair. Only the ids of the pair are kept (STATE/openwebui.json), never a token.
2. The admin enters Open WebUI's address in the home network (chat.openwebui_url) and, if it has one, its address
   from outside (chat.openwebui_link_url). The menu shows „Open WebUI“: from the home network the inner address,
   through the reverse proxy the outer one (none without it). The Dienst-Wächter asks only GET /health of the inner
   address (dienstwacht.py, netguard HOME, no login, no key), Zustand → Live shows reachable or not.

Fixed rules (the panel decides, never Open WebUI or a model):
- whatever Open WebUI sends is data: the key and the connection have exactly the rights of llmapi and mcpserver
  (limits, „hinten“, read tools only, nothing saved or switched); no tool of the group „Handeln“ is ever given here
- the address is a plain http(s) address (URL), no user, no query; a link never carries a key or token
- the function is off (admin switch chat.openwebui, built on „Sprachmodell per API“), never for guests
- logs and Live: fixed words and numbers only (`openwebui: …`), never a token, an address or a profile id
"""
import json
import os
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import STATE, load_config, write_json
from core import auth, browser_profile, confirm_code

router = APIRouter()
_lock = threading.Lock()

NAME = "Open WebUI"                      # the name of the key and the connection it makes
URL = re.compile(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[\w.\-~/]*)?")
GROUPS = ("read", "ask")                 # the MCP tool groups it gives: reading and „Spark fragen“, never „Handeln“
HEALTH = "/health"                       # Open WebUI answers it without a login


def _cfg():
    return load_config().get("chat", {})


def admin_on():
    return features.admin_on("openwebui")


def _url(key):
    url = str(_cfg().get(key) or "").strip().rstrip("/")
    return url if URL.fullmatch(url) else ""


def base():
    """Open WebUI's address in the home network (chat.openwebui_url) or ''."""
    return _url("openwebui_url")


def link_base():
    """Its address from outside (chat.openwebui_link_url) or ''."""
    return _url("openwebui_link_url")


def link_for(request):
    """The address the menu opens: the inner one in the home network, the outer one through the proxy."""
    import mcpserver
    if mcpserver.is_local(request):
        return base() or link_base()
    return link_base()


def probes():
    """For the Dienst-Wächter: GET /health of the inner address, home network level, no login."""
    if not admin_on() or not base():
        return {}
    import netguard
    return {"openwebui": {"url": base() + HEALTH, "level": netguard.HOME, "verify": True}}


# ---------------------------------------------------------------- the pair of one profile (ids only)
def _file():
    return os.path.join(STATE, "openwebui.json")


def _load():
    try:
        with open(_file()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def _save(d):
    write_json(_file(), d, indent=1, mode=0o600)


def pair(uid):
    """The ids of the profile's key and connection that still exist: {"llm": id or None, "mcp": id or None}."""
    import llmapi
    import mcpserver
    p = _load().get(uid)
    p = p if isinstance(p, dict) else {}
    keys = {k["id"] for k in llmapi.keys(uid)}
    conns = {c["id"] for c in mcpserver.conns(uid)}
    return {"llm": p.get("llm") if p.get("llm") in keys else None,
            "mcp": p.get("mcp") if p.get("mcp") in conns else None}


def disconnect(uid):
    """Removes the profile's key and connection made here; returns how many were removed."""
    import llmapi
    import mcpserver
    with _lock:
        d = _load()
        p = d.pop(uid, None)
        if p is not None:
            _save(d)
    n = 0
    if isinstance(p, dict):
        if p.get("llm") and llmapi.remove(str(p["llm"]), uid):
            n += 1
        if p.get("mcp") and mcpserver.remove(str(p["mcp"]), uid):
            n += 1
    return n


def tools(uid):
    """The MCP tools it gives: every reading tool and „Spark fragen“ the profile may use now."""
    import mcpserver
    return [n for n, spec in mcpserver.TOOLS.items() if spec[0] in GROUPS and mcpserver.tool_ok(n, uid)]


def connect(uid):
    """Makes the pair (after the old one is gone); returns (llm token, mcp token or None)."""
    import llmapi
    import mcpserver
    disconnect(uid)
    ltoken, k = llmapi.add_key(uid, NAME, "lokal")
    mtoken, c = None, None
    if features.allowed("mcpserver", uid):
        names = tools(uid)
        if names:
            try:
                mtoken, c = mcpserver.add_key(uid, NAME, names, "lokal")
            except HTTPException:
                llmapi.remove(k["id"], uid)
                raise
    with _lock:
        d = _load()
        d[uid] = {"llm": k["id"], "mcp": c["id"] if c else None}
        _save(d)
    return ltoken, mtoken


def _clear(uid):
    if disconnect(uid):
        guard.log("openwebui_remove", uid=uid, detail=NAME)


# own data for Ich while the admin blocks the function for the profile (features.OWN): its pair
features.OWN["openwebui"] = (lambda uid: sum(1 for v in pair(uid).values() if v), _clear)


# ---------------------------------------------------------------- Ich → Sprachmodell per API → Open WebUI
def _on(prof=Depends(browser_profile)):
    """Only from the profile's own browser login (never with a device key or a key of this function)."""
    if not admin_on():
        raise HTTPException(403, "Open WebUI einbinden ist vom Admin ausgeschaltet.")
    return prof


def for_me(request, uid):
    import mcpserver
    on = features.allowed("openwebui", uid)
    p = pair(uid) if on else {"llm": None, "mcp": None}
    return {"enabled": admin_on(), "on": on, "mcp": features.allowed("mcpserver", uid),
            "connected": bool(p["llm"] or p["mcp"]), "llm": bool(p["llm"]), "mcp_conn": bool(p["mcp"]),
            "url": mcpserver.base_url(request), "link": link_for(request) if on else "",
            "tools": tools(uid) if on and features.allowed("mcpserver", uid) else []}


@router.get("/api/profile/openwebui")
def profile_get(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "features", prof["id"])
    return for_me(request, prof["id"])


@router.post("/api/profile/openwebui")
async def profile_connect(request: Request, prof=Depends(_on)):
    uid = prof["id"]
    guard.limit(request, "openwebui", uid)
    if not features.allowed("openwebui", uid):
        print(f"openwebui: verbinden gesperrt | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, "Open WebUI einbinden ist für dein Profil gesperrt.")
    await confirm_code(request, uid, prof["name"])
    try:
        ltoken, mtoken = connect(uid)
    except HTTPException as e:
        print(f"openwebui: verbinden abgelehnt | {profiles.log_name(prof)} | {e.status_code}", flush=True)
        raise
    guard.log("openwebui_connect", uid=uid, detail=NAME + (" (Sprachmodell und MCP)" if mtoken else " (Sprachmodell)"))
    print(f"openwebui: verbunden | {profiles.log_name(prof)} | mcp {1 if mtoken else 0}", flush=True)
    import mcpserver
    url = mcpserver.base_url(request)
    return {"llm_token": ltoken, "mcp_token": mtoken, "v1": url + "/v1", "mcp": url + "/mcp" if mtoken else ""}


@router.delete("/api/profile/openwebui")
def profile_disconnect(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "openwebui", prof["id"])
    n = disconnect(prof["id"])
    if not n:
        print(f"openwebui: trennen nichts | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "not connected")
    guard.log("openwebui_remove", uid=prof["id"], detail=NAME)
    print(f"openwebui: getrennt | {profiles.log_name(prof)} | {n}", flush=True)
    return {"ok": True, "removed": n}


# ---------------------------------------------------------------- the admin and Zustand → Live
@router.get("/api/admin/openwebui", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "openwebui", admin=True)
    names = {u["id"]: u["name"] for u in profiles.names()}
    return {"enabled": admin_on(), "inner": bool(base()), "outer": bool(link_base()),
            "profiles": sorted(names[u] for u in profiles.user_ids() if u in names and any(pair(u).values()))}


def for_live(now=None):
    """Box „Open WebUI“: profiles connected, whether the inner address is set. Numbers only."""
    if not admin_on():
        return {"on": False}
    return {"on": True, "connected": sum(1 for u in profiles.user_ids() if any(pair(u).values())),
            "inner": bool(base()), "outer": bool(link_base())}


def live_sub(v):
    teile = [f"verbunden: {v.get('connected', 0)} Profile"]
    teile.append("Heimnetz-Adresse da" if v.get("inner") else "ohne Heimnetz-Adresse")
    if v.get("outer"):
        teile.append("Adresse von außen da")
    return " · ".join(teile)
