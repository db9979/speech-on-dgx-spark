"""Sprachmodell per API (plan llm-api/plan.md, Dominik 2026-11-05 „1a 2a 3b 4a 5a, admin immer unbegrenzt“): own
programs (Python openai, Open WebUI, Continue, n8n …) use the Spark's language model with a key of their profile,
OpenAI-compatible at /v1 on the panel's own address (also through the reverse proxy).

Who may: the admin switch chat.llm_api (features.py "llmapi"), every profile the admin did not block, never guests.
A profile makes keys under Ich → Sprachmodell per API, only in its own browser login with the code window; at most
MAX_KEYS per profile. A key is shown once; only its SHA-256 is kept (STATE/llm-api.json) and compared in constant
time; it ends after DAYS days without use or when it is removed.

    "lokal"   works only from the home network (mcpserver.is_local: a private peer, no proxy header)
    "extern"  also through the reverse proxy: only with the admin's chat.llm_api_extern ("llmapiextern"), the
              profile's second step and a fresh code, after a clear warning

Fixed rules (the panel decides, never the model or the program):
- only POST llm.OPENAI_CHAT (also streamed) and GET /v1/models; the plain model, no tool of the Spark, no
  memory, no documents, nothing of the profile. A "tools" list of the program passes; the Spark runs nothing of it
- text only (3b): a message part that is not text (pictures, audio, files) is refused; the model name is always the
  Spark's own language model (never "sehen" or "helfer"); only the fields of FELDER pass, n is 1, max_tokens at
  most MAX_TOKENS; the LLM-Tor's own field guard comes on top (only with the Spark's own LLM-Tor, else 503)
- the request goes with the stage "hinten" (stufe.headers): whoever talks to the Spark always goes first
- limits per key (4a): chat.llm_api_minute requests per minute, AT_ONCE at once, the key's own tokens per 24 hours
  (sliding, at most chat.llm_api_tag_k thousand); all keys together ALL at once. Admin profiles (coadmin.unbegrenzt)
  have none of these limits; size and field guard stay for everyone. The profile's Kontingent (verbrauch.py) counts
  the tokens too ("Sprachmodell per API") and holds the key when it is used up
- contents are never kept and never logged: the journal ("llmapi: …") and Live hold counts, tokens and fixed words
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

import features
import guard
import notaus
import profiles
from common import STATE, load_config, write_json
from llm import OPENAI_CHAT
import core
from core import auth, admin_code, browser_profile, confirm_code

router = APIRouter()
_lock = threading.Lock()

DAYS = 90                     # a key ends after this many days without use
MAX_KEYS = 5                  # per profile (2a)
MAX_BODY = 2 * 1024 ** 2      # a request to llm.OPENAI_CHAT
MAX_JSON = 16 * 1024          # any other request
MAX_TOKENS = 8192             # max_tokens of one answer
MAX_MESSAGES = 400
AT_ONCE = 2                   # per key at the same time (4a)
ALL = 4                       # all keys together at the same time
MINUTE_DEFAULT, TAG_K_DEFAULT = 20, 300   # config.default.json chat.llm_api_minute / chat.llm_api_tag_k (4a)
TAG_K_MAX = 100000
AUFGABE = "Sprachmodell per API"          # the task name in verbrauch.AUFGABEN
NAME = re.compile(r"[\w .,:()+&'\-äöüÄÖÜß]{1,60}")
TOKEN = re.compile(r"sk-spark-[A-Za-z0-9_\-]{40,60}")
FELDER = ("messages", "stream", "max_tokens", "max_completion_tokens", "temperature", "top_p", "top_k", "min_p",
          "presence_penalty", "frequency_penalty", "repetition_penalty", "stop", "seed", "tools", "tool_choice",
          "parallel_tool_calls", "response_format", "user")
ROLES = ("system", "developer", "user", "assistant", "tool")
# the fixed words of a refusal (journal and Live): reason -> (status, German sentence for the program)
WHY = {"schluessel": (401, "Schlüssel fehlt, ist unbekannt oder abgelaufen."),
       "heimnetz": (403, "Dieser Schlüssel gilt nur im Heimnetz."),
       "aussen": (403, "Zugriff von außen ist vom Admin ausgeschaltet."),
       "gesperrt": (403, "Sprachmodell per API ist für dieses Profil aus."),
       "notaus": (503, "Mein Notaus ist an: dieser Zugang ist gesperrt."),
       "minute": (429, "Zu viele Anfragen in dieser Minute, bitte gleich noch einmal."),
       "gleichzeitig": (429, "Gerade zu viele Anfragen gleichzeitig, bitte gleich noch einmal."),
       "tageslimit": (429, "Das Tageslimit dieses Schlüssels ist erreicht."),
       "kontingent": (429, "Das Kontingent des Profils ist aufgebraucht (Ich → Verbrauch)."),
       "anfrage": (400, "Anfrage nicht erlaubt."),
       "kein_tor": (503, "Das Sprachmodell des Spark ist so nicht freigegeben."),
       "modell": (503, "Das Sprachmodell antwortet gerade nicht.")}

_busy = {}                    # key id -> requests running now
_minute = {}                  # key id -> [times of the last minute]
stats = {"requests": 0, "refused": 0, "tokens": 0, "day": ""}   # today's numbers for Live (memory only)


def admin_on():
    return features.admin_on("llmapi")


def extern_on():
    return features.admin_on("llmapiextern")


def _cfg():
    return load_config().get("chat", {})


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def per_minute():
    return _int(_cfg().get("llm_api_minute", MINUTE_DEFAULT), 1, 600, MINUTE_DEFAULT)


def tag_k_max():
    return _int(_cfg().get("llm_api_tag_k", TAG_K_DEFAULT), 1, TAG_K_MAX, TAG_K_DEFAULT)


def unlimited(uid):
    """Admin profiles never have a limit here (Dominik 2026-11-05 „admin immer unbegrenzt“): the one rule of coadmin."""
    import coadmin
    return coadmin.unbegrenzt(uid)


# ---------------------------------------------------------------- stored keys
def _file():
    return os.path.join(STATE, "llm-api.json")


def _load():
    try:
        with open(_file()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    if not isinstance(d.get("keys"), list):
        d["keys"] = []
    return d


def _save(d):
    write_json(_file(), d, indent=1, mode=0o600, ensure_ascii=False)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _alive(k, now):
    return now - max(k.get("last") or 0, k.get("created") or 0) < DAYS * 86400


def _hour(now):
    return int(now // 3600)


def used_24h(k, now=None):
    """Tokens of this key in the last 24 hours (hour buckets)."""
    h = _hour(time.time() if now is None else now)
    return sum(int(v) for b, v in (k.get("use") or {}).items() if str(b).isdigit() and h - int(b) < 24)


def _prune(d, now):
    ids = set(profiles.user_ids())
    d["keys"] = [k for k in d["keys"] if k.get("uid") in ids and _alive(k, now)]
    h = _hour(now)
    for k in d["keys"]:
        k["use"] = {b: v for b, v in (k.get("use") or {}).items() if str(b).isdigit() and h - int(b) < 24}


def public(k, now=None):
    now = time.time() if now is None else now
    return {"id": k["id"], "name": k["name"], "where": k["where"], "tag_k": k.get("tag_k"),
            "created": k.get("created"), "last": k.get("last"), "used": used_24h(k, now),
            "ends": int(max(k.get("last") or 0, k["created"]) + DAYS * 86400)}


def keys(uid):
    now = time.time()
    return [public(k, now) for k in _load()["keys"] if k["uid"] == uid and _alive(k, now)]


def add_key(uid, name, where, tag_k=None, now=None):
    """A new key; returns (token, key). The token is shown once."""
    now = time.time() if now is None else now
    token = "sk-spark-" + secrets.token_urlsafe(32)
    k = {"id": "l_" + secrets.token_hex(6), "uid": uid, "name": name, "where": where,
         "tag_k": tag_k, "token": _hash(token), "created": int(now), "last": None, "use": {}}
    with _lock:
        d = _load()
        _prune(d, now)
        if sum(1 for x in d["keys"] if x["uid"] == uid) >= MAX_KEYS:
            raise HTTPException(409, f"Schon {MAX_KEYS} Schlüssel. Erst einen löschen.")
        d["keys"].append(k)
        _save(d)
    return token, k


def remove(kid, uid=None):
    with _lock:
        d = _load()
        hit = next((k for k in d["keys"] if k["id"] == kid and (uid is None or k["uid"] == uid)), None)
        if hit:
            d["keys"].remove(hit)
            _save(d)
        return hit


def find(token, now=None):
    """The key behind a bearer token, or None."""
    now = time.time() if now is None else now
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        return None
    h = _hash(token)
    for k in _load()["keys"]:
        if _alive(k, now) and isinstance(k.get("token"), str) and hmac.compare_digest(k["token"], h):
            return k
    return None


def count(kid, tokens, now=None):
    """Adds the tokens of one answer to the key's hour bucket and marks it used."""
    now = time.time() if now is None else now
    with _lock:
        d = _load()
        hit = next((k for k in d["keys"] if k["id"] == kid), None)
        if not hit:
            return
        b = str(_hour(now))
        use = hit.setdefault("use", {})
        use[b] = int(use.get(b, 0)) + max(0, int(tokens))
        hit["last"] = int(now)
        _prune(d, now)
        _save(d)


def _mine(uid):
    return [k for k in _load()["keys"] if k.get("uid") == uid]


def _clear(uid):
    for k in _mine(uid):
        if remove(k["id"], uid):
            guard.log("llmapi_remove", uid=uid, detail=k.get("name", ""))


# own data for Ich while the admin blocks the function for the profile (features.OWN): its keys
features.OWN["llmapi"] = (lambda uid: len(_mine(uid)), _clear)


# ---------------------------------------------------------------- the checks (pure where it can be, tested)
def _today():
    return time.strftime("%Y-%m-%d")


def _note(what, kid="", prof=None, extra=""):
    """One journal line with fixed words and numbers only."""
    if stats["day"] != _today():
        stats.update(requests=0, refused=0, tokens=0, day=_today())
    if what != "antwort":
        stats["refused"] += 1
    who = profiles.log_name(prof) if prof else "-"
    print(f"llmapi: {what} | {who} | {kid or '-'}" + (f" | {extra}" if extra else ""), flush=True)


def _refuse(why, kid="", prof=None):
    _note("abgelehnt " + why, kid, prof)
    status, text = WHY[why]
    heads = {"Cache-Control": "no-store"}
    if status == 401:
        heads["WWW-Authenticate"] = 'Bearer realm="spark"'
    if status == 429:
        heads["Retry-After"] = "60" if why != "gleichzeitig" else "5"
    return JSONResponse({"error": {"message": text, "type": why, "code": status}}, status_code=status, headers=heads)


def check_key(request, now=None):
    """(key, profile, None) or (None, None, response) for a request to /v1."""
    head = request.headers.get("authorization", "")
    token = head[7:].strip() if head[:7].lower() == "bearer " else ""
    k = find(token, now) if token else None
    if not k:
        return None, None, _refuse("schluessel")
    prof = profiles.by_id(k["uid"])
    import mcpserver
    if k["where"] == "lokal" and not mcpserver.is_local(request):
        return None, None, _refuse("heimnetz", k["id"], prof)
    if k["where"] == "extern" and not extern_on() and not mcpserver.is_local(request):
        return None, None, _refuse("aussen", k["id"], prof)
    if notaus.own(k["uid"]):
        return None, None, _refuse("notaus", k["id"], prof)
    if not features.allowed("llmapi", k["uid"]):
        return None, None, _refuse("gesperrt", k["id"], prof)
    return k, prof, None


def _text_only(content):
    """The text of a message's content: a string, or a list of text parts; anything else is refused (3b)."""
    if content is None or isinstance(content, str):
        return content
    if isinstance(content, list) and all(isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str)
                                         for p in content):
        return [{"type": "text", "text": p["text"]} for p in content]
    raise ValueError("nur_text")


def clean(body):
    """The request as it may go on: known fields only, text only, one answer, max_tokens within MAX_TOKENS.
    ValueError with a fixed word on anything else."""
    if not isinstance(body, dict):
        raise ValueError("objekt")
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not msgs or len(msgs) > MAX_MESSAGES:
        raise ValueError("messages")
    out = {k: body[k] for k in FELDER if k in body and body[k] is not None}
    clean_msgs = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ROLES:
            raise ValueError("rolle")
        keep = {k: m[k] for k in ("role", "content", "name", "tool_calls", "tool_call_id") if k in m}
        keep["content"] = _text_only(m.get("content"))
        clean_msgs.append(keep)
    out["messages"] = clean_msgs
    if body.get("n") not in (None, 1):
        raise ValueError("n")
    for key in ("max_tokens", "max_completion_tokens"):
        if key in out:
            v = out[key]
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX_TOKENS:
                raise ValueError(key)
    if "max_tokens" not in out and "max_completion_tokens" not in out:
        out["max_tokens"] = MAX_TOKENS
    if not isinstance(out.get("stream", False), bool):
        raise ValueError("stream")
    if out.get("stream"):
        out["stream_options"] = {"include_usage": True}
    kw = body.get("chat_template_kwargs")
    if isinstance(kw, dict) and isinstance(kw.get("enable_thinking"), bool):   # thinking on or off, nothing else
        out["chat_template_kwargs"] = {"enable_thinking": kw["enable_thinking"]}
    return out


def _limits(k, prof, now):
    """The fixed word of a limit this request would pass, or ""; also takes the request's place."""
    import verbrauch
    if verbrauch.over(k["uid"], now):
        return "kontingent"
    if unlimited(k["uid"]):
        with _lock:
            _busy[k["id"]] = _busy.get(k["id"], 0) + 1
        return ""
    lim_k = min(tag_k_max(), k.get("tag_k") or tag_k_max())
    if used_24h(k, now) >= lim_k * 1000:
        return "tageslimit"
    with _lock:
        q = [t for t in _minute.get(k["id"], []) if now - t < 60]
        if len(q) >= per_minute():
            _minute[k["id"]] = q
            return "minute"
        if _busy.get(k["id"], 0) >= AT_ONCE or sum(_busy.values()) >= ALL:
            return "gleichzeitig"
        q.append(now)
        _minute[k["id"]] = q
        _busy[k["id"]] = _busy.get(k["id"], 0) + 1
    return ""


def _leave(kid):
    with _lock:
        n = _busy.get(kid, 0) - 1
        if n > 0:
            _busy[kid] = n
        else:
            _busy.pop(kid, None)


def _target():
    """(chat config, address, headers) of the Spark's own LLM-Tor, or None while the chat uses another server."""
    import llm
    import stufe
    ccfg = load_config("chat")
    if not llm.own_tor(ccfg):
        return None
    return ccfg, llm.url(ccfg), {**llm.headers(ccfg), **stufe.headers("hinten")}


def _done(k, prof, usage, ms, status):
    import verbrauch
    u = usage if isinstance(usage, dict) else {}
    tin, tout = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    if status == 200:
        count(k["id"], tin + tout)
        verbrauch.llm(AUFGABE, usage, ms, who=k["uid"])
        stats["requests"] += 1
        stats["tokens"] += tin + tout
        _note("antwort", k["id"], prof, f"{tin} in {tout} aus {ms} ms")
    else:
        _note("fehler modell", k["id"], prof, f"HTTP {int(status)}")


_client = None


def client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=5))
    return _client


# ---------------------------------------------------------------- the endpoints programs use
@router.get("/v1/models")
async def models(request: Request):
    if not admin_on():
        raise HTTPException(404, "not found")
    k, prof, refused = check_key(request)
    if refused:
        return refused
    import llm
    t = _target()
    if not t:
        return _refuse("kein_tor", k["id"], prof)
    try:
        name = await llm.model(client(), t[0])
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return _refuse("modell", k["id"], prof)
    return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "spark"}]}


@router.post(OPENAI_CHAT)
async def completions(request: Request):
    if not admin_on():
        raise HTTPException(404, "not found")
    k, prof, refused = check_key(request)
    if refused:
        return refused
    try:
        body = clean(await core.json_body(request, MAX_BODY))
    except ValueError as e:
        _note("abgelehnt anfrage", k["id"], prof, str(e)[:20])
        return JSONResponse({"error": {"message": WHY["anfrage"][1] + f" ({str(e)[:20]})", "type": "anfrage", "code": 400}},
                            status_code=400)
    t = _target()
    if not t:
        return _refuse("kein_tor", k["id"], prof)
    now = time.time()
    why = _limits(k, prof, now)
    if why:
        return _refuse(why, k["id"], prof)
    import llm
    ccfg, url, heads = t
    t0 = time.monotonic()
    try:
        body["model"] = await llm.model(client(), ccfg)
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        _leave(k["id"])
        return _refuse("modell", k["id"], prof)
    if not body.get("stream"):
        try:
            r = await client().post(url, json=body, headers=heads)
        except httpx.HTTPError:
            _leave(k["id"])
            return _refuse("modell", k["id"], prof)
        _leave(k["id"])
        try:
            usage = r.json().get("usage")
        except (ValueError, AttributeError):
            usage = None
        _done(k, prof, usage, int((time.monotonic() - t0) * 1000), r.status_code)
        return Response(r.content, status_code=r.status_code, media_type="application/json",
                        headers={"Cache-Control": "no-store"})
    try:
        r = await client().send(client().build_request("POST", url, json=body, headers=heads), stream=True)
    except httpx.HTTPError:
        _leave(k["id"])
        return _refuse("modell", k["id"], prof)
    if r.status_code != 200:
        content = await r.aread()
        await r.aclose()
        _leave(k["id"])
        _done(k, prof, None, 0, r.status_code)
        return Response(content, status_code=r.status_code, media_type="application/json")

    async def pieces():
        usage, rest = None, b""
        try:
            async for chunk in r.aiter_bytes():
                rest += chunk
                while b"\n" in rest:            # the usage piece comes last (stream_options include_usage)
                    line, rest = rest.split(b"\n", 1)
                    if line.startswith(b"data: {") and b'"usage"' in line:
                        try:
                            got = json.loads(line[6:]).get("usage")
                            usage = got if isinstance(got, dict) else usage
                        except ValueError:
                            pass
                yield chunk
        finally:
            await r.aclose()
            _leave(k["id"])
            _done(k, prof, usage, int((time.monotonic() - t0) * 1000), 200)
    return StreamingResponse(pieces(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- Ich → Sprachmodell per API
def _on(prof=Depends(browser_profile)):
    """Only from the profile's own browser login (never with a device key or a key of this function)."""
    if not admin_on():
        raise HTTPException(403, "Sprachmodell per API ist vom Admin ausgeschaltet.")
    return prof


def _name(v):
    v = str(v or "").strip()
    if not NAME.fullmatch(v):
        raise HTTPException(400, "Name: 1 bis 60 Zeichen (Buchstaben, Ziffern, Leerzeichen, . , : ( ) + & ' -)")
    return v


async def _where_ok(request, prof, where):
    """Home network with the code window; outside only with the admin's switch, the profile's second step and a
    fresh code (it opens a way to the model from the internet), like mcpserver._where_ok."""
    if where == "lokal":
        await confirm_code(request, prof["id"], prof["name"])
        return
    if not extern_on():
        raise HTTPException(403, "Zugriff von außen ist vom Admin ausgeschaltet.")
    import mfa
    if not mfa.enabled(prof["id"]):
        raise HTTPException(403, "Für Zugriff von außen braucht dein Profil den zweiten Anmeldeschritt (Ich → Sicherheit).")
    await confirm_code(request, prof["id"], prof["name"], fresh=True)


def for_me(request, uid):
    import mfa
    import mcpserver
    return {"enabled": admin_on(), "on": features.allowed("llmapi", uid), "extern": extern_on(),
            "mfa": mfa.enabled(uid), "url": mcpserver.base_url(request) + "/v1", "days": DAYS, "most": MAX_KEYS,
            "unlimited": unlimited(uid), "per_minute": per_minute(), "at_once": AT_ONCE, "tag_k": tag_k_max(),
            "keys": keys(uid) if admin_on() else []}


@router.get("/api/profile/llmapi")
def profile_get(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "features", prof["id"])
    return for_me(request, prof["id"])


@router.post("/api/profile/llmapi/keys")
async def profile_key(request: Request, prof=Depends(_on)):
    uid = prof["id"]
    guard.limit(request, "llmapi", uid)
    if not features.allowed("llmapi", uid):
        raise HTTPException(403, "Sprachmodell per API ist für dein Profil gesperrt.")
    body = await core.json_body(request, MAX_JSON)
    name, where = _name(body.get("name")), body.get("where", "lokal")
    if where not in ("lokal", "extern"):
        raise HTTPException(400, "where: lokal or extern")
    tag_k = body.get("tag_k")
    if tag_k is not None:
        if isinstance(tag_k, bool) or not isinstance(tag_k, int) or not 1 <= tag_k <= tag_k_max():
            raise HTTPException(400, f"tag_k: 1 bis {tag_k_max()} (tausend Tokens)")
    await _where_ok(request, prof, where)
    token, k = add_key(uid, name, where, tag_k)
    guard.log("llmapi_key", uid=uid, detail=f"{name} ({where})")
    print(f"llmapi: schluessel neu | {profiles.log_name(prof)} | {k['id']} | {where}", flush=True)
    import mcpserver
    return {"token": token, "key": public(k), "url": mcpserver.base_url(request) + "/v1"}


@router.delete("/api/profile/llmapi/keys/{kid}")
def profile_remove(kid: str, request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "llmapi", prof["id"])
    hit = remove(str(kid)[:20], prof["id"])
    if not hit:
        print(f"llmapi: schluessel loeschen unbekannt | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "no such key")
    guard.log("llmapi_remove", uid=prof["id"], detail=hit["name"])
    print(f"llmapi: schluessel geloescht | {profiles.log_name(prof)} | {hit['id']}", flush=True)
    return {"ok": True}


# ---------------------------------------------------------------- the admin's overview
@router.get("/api/admin/llmapi", dependencies=[Depends(auth)])
def admin_list(request: Request):
    guard.limit(request, "llmapi", admin=True)
    now = time.time()
    names = {u["id"]: u["name"] for u in profiles.names()}
    return {"enabled": admin_on(), "extern": extern_on(), "per_minute": per_minute(), "tag_k": tag_k_max(),
            "keys": [dict(public(k, now), profile=names.get(k["uid"], "?")) for k in _load()["keys"]
                     if _alive(k, now) and k["uid"] in names]}


@router.delete("/api/admin/llmapi/{kid}", dependencies=[Depends(auth), Depends(admin_code)])
def admin_remove(kid: str, request: Request):
    guard.limit(request, "llmapi", admin=True)
    hit = remove(str(kid)[:20])
    if not hit:
        print("llmapi: schluessel loeschen unbekannt | admin", flush=True)
        raise HTTPException(404, "no such key")
    guard.log("llmapi_remove", uid=hit["uid"], by="admin", detail=hit["name"])
    print(f"llmapi: schluessel geloescht | admin | {hit['id']}", flush=True)
    return {"ok": True}


# ---------------------------------------------------------------- Zustand → Live
def for_live(now=None):
    """Box „Sprachmodell per API“: keys, running, today's answers, refusals and tokens. Numbers only."""
    if not admin_on():
        return {"on": False}
    now = time.time() if now is None else now
    ks = [k for k in _load()["keys"] if _alive(k, now)]
    today = stats["day"] == _today()
    return {"on": True, "keys": len(ks), "extern": sum(1 for k in ks if k["where"] == "extern"),
            "running": sum(_busy.values()), "requests": stats["requests"] if today else 0,
            "refused": stats["refused"] if today else 0, "tokens": stats["tokens"] if today else 0}


def live_sub(v):
    teile = [f"Schlüssel: {v.get('keys', 0)}" + (f" ({v['extern']} von außen)" if v.get("extern") else "")]
    if v.get("running"):
        teile.append(f"läuft: {v['running']}")
    teile.append(f"heute {v.get('requests', 0)} Antworten, {v.get('tokens', 0)} Tokens")
    if v.get("refused"):
        teile.append(f"{v['refused']} abgelehnt")
    return " · ".join(teile)
