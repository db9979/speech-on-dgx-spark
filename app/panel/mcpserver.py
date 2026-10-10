"""The Spark as an MCP server (plan plaene/spark-als-mcp-server.md, V01.0.303): other programs (Open WebUI,
n8n, Home Assistant, Claude, ...) use the Spark's abilities over the Model Context Protocol at /mcp.

The other direction (the Spark uses outside MCP servers) is mcp.py.

Who may: the admin switch chat.mcp_server and the profile's own switch mcps_on (features.py "mcpserver"),
never guests. A profile connects a program under Ich → Dienste per MCP; every connection belongs to that
profile, has its own token and its own list of tools, and ends after DAYS days without use or when it is
removed. Connections are made only in the profile's own browser login (with a code when it has the second
step); only hashes of the tokens are kept (STATE/mcp-server.json).

    "lokal"   a fixed key that works only from the home network: the direct peer is a private address
              and no proxy header is in the request (requests through the reverse proxy carry them)
    "extern"  also through the reverse proxy: a fixed key or OAuth 2.1 (claude.ai, ChatGPT ...). Only with
              the admin's chat.mcp_server_extern, the profile's second step and a fresh code, after a clear
              warning that what the program reads leaves the home network.

Everything from the program is data, never a command (fixed rules, the panel decides):
- only the tools of the fixed list TOOLS, and of those only what the connection was given and the profile
  may use right now (features.allowed), checked on every call
- "ask_spark" runs one turn of the assistant as the profile, but only with the read tools of the connection;
  the question counts as outside text from the start: nothing is switched, saved, learned, sent or proposed,
  no memory and no earlier conversations, and nothing of it is kept in the conversations (chat_turn.py "mcp")
- tools that change something (group "act", admin switch chat.mcp_server_act) only leave a proposal: the
  profile gets a push and confirms or declines it in its own browser login (Ich → Dienste per MCP), with its
  code window; only then the panel carries it out. Never: mail, memory, earlier conversations, secrets,
  settings, admin, running code (NEVER, checked by a self-test).
- limits: request size, argument sizes, calls per minute per connection, two calls at a time per connection,
  answers cut to MAX_RESULT; speech requests go to the services with the stage "hinten" (stufe.py), so
  people talking to the Spark always go first.
"""
import asyncio
import base64
import datetime
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

import features
import guard
import notaus
import profiles
from common import load_config
from core import admin_code, api_headers, app_version, auth, browser_profile, confirm_code

router = APIRouter()
STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
_lock = threading.Lock()

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DAYS = 90                    # a connection ends after this many days without use
MAX_CONNS = 10               # per profile
MAX_BODY = 16 * 1024 ** 2    # a request to /mcp (audio as base64)
MAX_JSON = 64 * 1024         # any other request
MAX_AUDIO = 10 * 1024 ** 2   # decoded audio for "transcribe"
MAX_SPEAK = 2000             # characters to speak
MAX_QUESTION = 2000
MAX_RESULT = 12000           # characters of a tool answer
MAX_AT_ONCE = 2              # calls per connection at the same time
MAX_ALL = 6                  # calls of all connections at the same time
ACCESS_SECONDS = 3600        # an OAuth access token
REFRESH_DAYS = 30            # an OAuth refresh token (renewed with every use)
CODE_SECONDS = 300           # an OAuth authorization code
ASK_SECONDS = 600            # an OAuth sign-in waiting in the panel
MAX_CLIENTS = 50             # registered OAuth programs
MAX_WAITING = 10             # actions waiting for the profile's decision
ACTION_SECONDS = 900         # how long an action waits for it
NAME = re.compile(r"[\w .,:()+&'\-äöüÄÖÜß]{1,60}")
TOKEN = re.compile(r"[A-Za-z0-9_\-]{20,100}")
CHALLENGE = re.compile(r"[A-Za-z0-9._~\-]{43,128}")

# ---------------------------------------------------------------- the tools
STR = {"type": "string"}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


# name -> (group, function in features.py it needs or None, German label, description, input schema)
TOOLS = {
    "transcribe": ("speech", None, "Sprache in Text (Spracherkennung)",
                   "Transcribe a recording with the Spark's speech recognition. audio: base64 of the file "
                   "(wav, mp3, ogg, webm, m4a, flac; at most 10 MB).",
                   _schema({"audio": STR, "format": {"type": "string", "enum": ["wav", "mp3", "ogg", "webm", "m4a", "flac"]},
                            "language": {"type": "string", "description": "e.g. de or en; empty: detected"}}, ["audio"])),
    "speak": ("speech", None, "Text in Sprache (Sprachausgabe)",
              "Speak a text with the Spark's voice; the answer is an mp3 recording.",
              _schema({"text": {"type": "string", "maxLength": MAX_SPEAK}, "voice": STR,
                       "language": {"type": "string", "description": "German or English (default German)"}}, ["text"])),
    "voices": ("speech", None, "Stimmen auflisten", "List the voice names the Spark can speak with.", _schema({})),
    "wikipedia": ("read", "wiki", "Wikipedia nachschlagen",
                  "Look up a term, person or place in Wikipedia (or the Spark's own Kiwix copy).",
                  _schema({"query": STR}, ["query"])),
    "archive_search": ("read", "kiwix", "Eigenes Kiwix-Archiv durchsuchen",
                       "Full-text search in the owner's offline archive (Kiwix: manuals, travel guides, reference works).",
                       _schema({"query": STR, "book": STR}, ["query"])),
    "document_search": ("read", "documents", "Eigene Dokumente durchsuchen",
                        "Search the profile's own uploaded documents; returns matching passages with their source.",
                        _schema({"query": STR}, ["query"])),
    "calendar_events": ("read", "calendar", "Termine lesen",
                        "The profile's appointments from a date (YYYY-MM-DD, default today) for 1 to 14 days.",
                        _schema({"date": STR, "days": {"type": "integer", "minimum": 1, "maximum": 14}})),
    "reminder_list": ("read", "reminders", "Erinnerungen lesen", "The profile's pending timers and reminders.", _schema({})),
    "today": ("read", None, "Heute (Überblick)",
              "Today at a glance: next appointments, the next reminder, unread messages (only numbers and titles).",
              _schema({})),
    "ask_spark": ("ask", None, "Spark fragen (nur lesend)",
                  "Ask the Spark's assistant a question in natural language. It answers as the profile's assistant "
                  "but can only read (with the read tools of this connection); it switches, saves and sends nothing.",
                  _schema({"question": {"type": "string", "maxLength": MAX_QUESTION}}, ["question"])),
    "home_assistant": ("act", "ha", "Smart Home schalten (mit Bestätigung)",
                       "Propose a smart home command in plain words (e.g. 'Licht im Flur aus'). Nothing happens until "
                       "the person confirms it on the Spark; check with action_status.",
                       _schema({"command": STR}, ["command"])),
    "reminder_set": ("act", "reminders", "Erinnerung anlegen (mit Bestätigung)",
                     "Propose a reminder: minutes from now or a local time 'YYYY-MM-DDTHH:MM'. Saved only after the "
                     "person confirms it on the Spark.",
                     _schema({"text": STR, "minutes": {"type": "number"}, "at": STR}, ["text"])),
    "calendar_add": ("act", "calendar", "Termin eintragen (mit Bestätigung)",
                     "Propose an appointment (start 'YYYY-MM-DDTHH:MM' or 'YYYY-MM-DD' for all day). Entered only "
                     "after the person confirms it on the Spark.",
                     _schema({"title": STR, "start": STR, "minutes": {"type": "integer"}, "days": {"type": "integer"},
                              "location": STR}, ["title", "start"])),
    "action_status": ("act", None, "Stand einer Bestätigung",
                      "Whether a proposed action was confirmed, declined or is still waiting.",
                      _schema({"id": STR}, ["id"])),
}
GROUPS = {"speech": ("Sprache", "Speech"), "read": ("Lesen", "Reading"), "ask": ("Spark fragen", "Ask Spark"),
          "act": ("Handeln mit Bestätigung", "Acting with confirmation")}
# what "ask_spark" may use in the assistant's turn, per tool of the connection (chat tool names)
ASK_TOOLS = {"wikipedia": {"wikipedia", "article_more"}, "archive_search": {"archive_search", "article_more"},
             "document_search": {"document_search"}, "calendar_events": {"calendar_events"},
             "reminder_list": {"reminder_list"}}
# never offered to a program, by any name (a self-test checks TOOLS and ASK_TOOLS against it)
NEVER = {"mail_list", "mail_search", "mail_read", "mail_draft", "mail_tidy_overview", "mail_tidy_propose",
         "memory_save", "memory_forget", "history_search", "daily_briefing", "web_search", "reminder_cancel",
         "home_assistant_action", "home_assistant_states", "home_assistant_history", "home_assistant_todo",
         "iphone_action", "message_send", "agent_task", "code", "shell", "settings", "secrets"}
MCP_HINT = ("Diese Frage kommt von einem anderen Programm über die MCP-Schnittstelle, nicht direkt vom Nutzer. "
            "Antworte sachlich und vollständig in Textform. Du kannst hier nur nachlesen: nichts schalten, speichern, "
            "senden oder vorschlagen, und du kennst keine gespeicherten Notizen oder früheren Gespräche.")


def admin_on():
    return features.admin_on("mcpserver")


def extern_on():
    return features.admin_on("mcpextern")


def act_on():
    return features.admin_on("mcpact")


def tool_ok(name, uid):
    """May the profile use this tool right now (the Spark's and its own switches)?"""
    spec = TOOLS.get(name)
    if not spec or name in NEVER:
        return False
    if spec[0] == "act" and not act_on():
        return False
    if name == "wikipedia":
        return features.allowed("wiki", uid) or features.allowed("kiwix", uid)
    return features.allowed(spec[1], uid) if spec[1] else True


# ---------------------------------------------------------------- stored connections
def _file():
    return os.path.join(STATE, "mcp-server.json")


def _load():
    try:
        with open(_file()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    d.setdefault("conns", [])
    d.setdefault("clients", [])
    return d


def _save(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = _file() + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _file())


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _same(a, b):
    return isinstance(a, str) and isinstance(b, str) and hmac.compare_digest(a, b)


def _alive(c, now):
    return now - max(c.get("last") or 0, c.get("created") or 0) < DAYS * 86400


def _prune(d, now):
    ids = set(profiles.user_ids())
    d["conns"] = [c for c in d["conns"] if c.get("uid") in ids and _alive(c, now)]
    used = {c.get("client") for c in d["conns"]}
    # a registered program that never got a connection is forgotten after a day
    d["clients"] = [x for x in d["clients"] if x["id"] in used or now - x.get("created", 0) < 86400][-MAX_CLIENTS:]


def clean_tools(names, uid):
    if not isinstance(names, list) or len(names) > len(TOOLS):
        raise HTTPException(400, "tools: a list of tool names")
    out = []
    for n in names:
        if n not in TOOLS or n in NEVER:
            raise HTTPException(400, f"unknown tool {str(n)[:40]}")
        if TOOLS[n][0] == "act" and not act_on():
            raise HTTPException(403, "Handeln mit Bestätigung ist vom Admin ausgeschaltet.")
        if n not in out:
            out.append(n)
    if any(TOOLS[n][0] == "act" for n in out) and "action_status" not in out:
        out.append("action_status")
    return out


def public(c, now=None):
    now = time.time() if now is None else now
    return {"id": c["id"], "name": c["name"], "kind": c["kind"], "where": c["where"], "tools": c["tools"],
            "created": c.get("created"), "last": c.get("last"), "ends": int(max(c.get("last") or 0, c["created"]) + DAYS * 86400),
            "client": c.get("client_name", "")}


def conns(uid):
    now = time.time()
    return [public(c, now) for c in _load()["conns"] if c["uid"] == uid and _alive(c, now)]


def add_key(uid, name, tools, where, now=None):
    """A fixed key for one program; returns (token, connection). The token is shown once."""
    now = time.time() if now is None else now
    token = "spk_mcp_" + secrets.token_urlsafe(32)
    c = {"id": "m_" + secrets.token_hex(6), "uid": uid, "name": name, "kind": "key", "where": where,
         "tools": tools, "token": _hash(token), "created": int(now), "last": None}
    with _lock:
        d = _load()
        _prune(d, now)
        if sum(1 for x in d["conns"] if x["uid"] == uid) >= MAX_CONNS:
            raise HTTPException(409, f"Schon {MAX_CONNS} Verbindungen. Erst eine entfernen.")
        d["conns"].append(c)
        _save(d)
    return token, c


def remove(cid, uid=None):
    with _lock:
        d = _load()
        hit = next((c for c in d["conns"] if c["id"] == cid and (uid is None or c["uid"] == uid)), None)
        if hit:
            d["conns"].remove(hit)
            _save(d)
        return hit


def change(cid, uid, tools=None, where=None, name=None):
    with _lock:
        d = _load()
        hit = next((c for c in d["conns"] if c["id"] == cid and c["uid"] == uid), None)
        if not hit:
            return None
        if tools is not None:
            hit["tools"] = tools
        if where is not None:
            hit["where"] = where
        if name is not None:
            hit["name"] = name
        _save(d)
        return dict(hit)


def find(token, now=None):
    """The connection behind a bearer token (a fixed key or an OAuth access token), or None."""
    now = time.time() if now is None else now
    if not isinstance(token, str) or not TOKEN.fullmatch(token.replace("spk_mcp_", "", 1)):
        return None
    h = _hash(token)
    for c in _load()["conns"]:
        if not _alive(c, now):
            continue
        if c["kind"] == "key" and _same(c.get("token"), h):
            return c
        if c["kind"] == "oauth" and _same(c.get("access"), h) and now < c.get("access_until", 0):
            return c
    return None


def touch(cid, now=None):
    now = int(time.time() if now is None else now)
    with _lock:
        d = _load()
        hit = next((c for c in d["conns"] if c["id"] == cid), None)
        if hit and (hit.get("last") or 0) < now - 60:   # once a minute is enough
            hit["last"] = now
            _save(d)


# ---------------------------------------------------------------- where a request comes from
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip")


def is_local(request):
    """The program sits in the home network: a private peer address, no proxy header at all and not one of
    the reverse proxies the admin listed (panel.trusted_proxies)."""
    if any(request.headers.get(h) for h in PROXY_HEADERS):
        return False
    peer = (request.client.host if request.client else "") or ""
    if peer in guard._proxies():
        return False
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return (ip.is_private or ip.is_loopback) and not ip.is_unspecified


def base_url(request):
    """The address programs reach the Spark at (for OAuth): the reverse proxy's when it says so."""
    host = request.headers.get("x-forwarded-host") if guard.from_lan(request) else None
    host = (host or request.headers.get("host") or "").split(",")[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,200}(:\d{1,5})?|\[[0-9a-fA-F:.]{2,60}\](:\d{1,5})?", host):
        host = "localhost"
    return ("https" if guard.https(request) else "http") + "://" + host


def origin_ok(request):
    """A browser page of another site must not use the endpoint (DNS rebinding): Origin, when sent, is ours."""
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return not origin
    return urlsplit(origin).netloc.lower() == urlsplit(base_url(request)).netloc.lower()


# ---------------------------------------------------------------- the endpoint
_busy = {}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _unauthorized(request, why):
    head = 'Bearer realm="spark"'
    if extern_on():
        head += f', resource_metadata="{base_url(request)}/.well-known/oauth-protected-resource"'
    return JSONResponse({"error": "invalid_token", "error_description": why}, status_code=401,
                        headers={"WWW-Authenticate": head, "Cache-Control": "no-store"})


def check_conn(request, now=None):
    """(connection, None) or (None, response) for a request to /mcp."""
    head = request.headers.get("authorization", "")
    token = head[7:].strip() if head[:7].lower() == "bearer " else ""
    c = find(token, now) if token else None
    if not c:
        return None, _unauthorized(request, "token missing, unknown or expired")
    if c["where"] == "lokal" and not is_local(request):
        print("mcp-server:", c["name"][:40], "- refused: a home network key from outside", flush=True)
        return None, JSONResponse({"error": "Dieser Schlüssel gilt nur im Heimnetz."}, status_code=403)
    if c["where"] == "extern" and not extern_on():
        return None, JSONResponse({"error": "Zugriff von außen ist vom Admin ausgeschaltet."}, status_code=403)
    if not features.allowed("mcpserver", c["uid"]):
        return None, JSONResponse({"error": "Spark als MCP-Server ist für dieses Profil aus."}, status_code=403)
    return c, None


def tool_list(c):
    out = []
    for n in c["tools"]:
        if tool_ok(n, c["uid"]):
            group, _, label, desc, schema = TOOLS[n]
            out.append({"name": n, "title": label, "description": desc, "inputSchema": schema,
                        "annotations": {"readOnlyHint": group != "act", "openWorldHint": False}})
    return out


@router.post("/mcp")
async def mcp_post(request: Request):
    if not admin_on():
        raise HTTPException(404, "not found")
    if not origin_ok(request):
        return JSONResponse({"error": "request from another page refused"}, status_code=403)
    c, refused = check_conn(request)
    if refused:
        return refused
    ver = request.headers.get("mcp-protocol-version")
    if ver and ver not in PROTOCOLS:
        return JSONResponse(_error(None, -32600, "unsupported protocol version"), status_code=400)
    guard.limit(request, "mcp", "mcp:" + c["id"])
    raw = await _body(request, MAX_BODY)
    try:
        msg = json.loads(raw)
    except ValueError:
        return JSONResponse(_error(None, -32700, "parse error"), status_code=400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return JSONResponse(_error(None, -32600, "one JSON-RPC 2.0 request"), status_code=400)
    rid, method = msg.get("id"), msg["method"]
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if rid is None:   # a notification or an answer: nothing to say
        return Response(status_code=202)
    if not isinstance(rid, (str, int)) or isinstance(rid, bool) or len(str(rid)) > 100:
        return JSONResponse(_error(None, -32600, "invalid id"), status_code=400)
    touch(c["id"])
    if method == "initialize":
        want = params.get("protocolVersion")
        return _ok(rid, {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": "spark", "title": "Spark (Speech on DGX Spark)", "version": app_version()},
                         "instructions": "Tools of the Spark home assistant for one person. Actions are only proposed "
                                         "and need that person's confirmation on the Spark."})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": tool_list(c)})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or name not in c["tools"] or not tool_ok(name, c["uid"]):
            return _ok(rid, _result(f"Das Werkzeug {str(name)[:40]} ist für diese Verbindung nicht freigegeben.", True))
        if not isinstance(args, dict):
            return _ok(rid, _result("arguments must be an object", True))
        return _ok(rid, await call(request, c, name, args))
    return JSONResponse(_error(rid, -32601, "method not found"))


@router.get("/mcp")
def mcp_get():
    """No server-sent event stream: every answer comes with its request."""
    if not admin_on():
        raise HTTPException(404, "not found")
    return Response(status_code=405, headers={"Allow": "POST"})


def _ok(rid, result):
    return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result}, headers={"Cache-Control": "no-store"})


def _result(text, error=False):
    return {"content": [{"type": "text", "text": str(text)[:MAX_RESULT]}], "isError": bool(error)}


async def _body(request, most):
    if int(request.headers.get("content-length") or 0) > most:
        raise HTTPException(413, "too large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > most:
            raise HTTPException(413, "too large")
    return bytes(data)


async def call(request, c, name, args):
    """One tool call with the limits (at once per connection and overall); its line in the journal says
    only who, which tool and how it went, never what was asked or answered."""
    with _lock:
        if _busy.get(c["id"], 0) >= MAX_AT_ONCE or sum(_busy.values()) >= MAX_ALL:
            return _result("Gerade zu viele Anfragen gleichzeitig, bitte gleich noch einmal.", True)
        _busy[c["id"]] = _busy.get(c["id"], 0) + 1
    t0 = time.monotonic()
    try:
        res = await run(request, c, name, args)
    except (httpx.HTTPError, OSError) as e:
        res = _result(f"Der Dienst antwortet gerade nicht ({type(e).__name__}).", True)
    except (ValueError, TypeError, KeyError) as e:
        res = _result(f"Ungültige Angaben: {str(e)[:200]}", True)
    finally:
        with _lock:
            _busy[c["id"]] = max(0, _busy.get(c["id"], 1) - 1)
            if not _busy[c["id"]]:
                _busy.pop(c["id"], None)
    print(f"mcp-server: {c['name'][:40]} ({c['where']}) {name} {'Fehler' if res.get('isError') else 'ok'} "
          f"{int((time.monotonic() - t0) * 1000)} ms", flush=True)
    return res


def _text(args, key, most):
    v = args.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key} fehlt")
    if len(v) > most:
        raise ValueError(f"{key}: höchstens {most} Zeichen")
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", v).strip()


async def run(request, c, name, args):
    uid = c["uid"]
    group = TOOLS[name][0]
    if group == "speech":
        return await speech(name, args, uid)
    if name == "ask_spark":
        guard.limit(request, "mcpask", "mcp:" + c["id"])
        return _result(await ask(request, c, _text(args, "question", MAX_QUESTION)))
    if name == "action_status":
        return _result(status(uid, str(args.get("id") or "")[:20]))
    if group == "act":
        return _result(await propose(c, name, args))
    return _result(await read(name, args, uid))


# ---------------------------------------------------------------- speech
async def speech(name, args, uid):
    import stufe
    cfg = load_config()
    low = stufe.headers("hinten")   # people talking to the Spark go first
    if name == "voices":
        async with httpx.AsyncClient(timeout=10) as cl:
            v = (await cl.get(f"http://127.0.0.1:{cfg['tts']['port']}/v1/voices", headers=api_headers())).json()
        names = [x for x in (v.get("voices") or []) if isinstance(x, str) and 0 < len(x) <= 64][:200] if isinstance(v, dict) else []
        return _result(", ".join(names) or "Keine Stimmen gefunden.")
    if name == "transcribe":
        raw = args.get("audio")
        if not isinstance(raw, str) or len(raw) > MAX_AUDIO * 4 // 3 + 8:
            raise ValueError("audio: base64, höchstens 10 MB")
        try:
            data = base64.b64decode(raw, validate=True)
        except ValueError:
            raise ValueError("audio: kein gültiges base64")
        if not data or len(data) > MAX_AUDIO:
            raise ValueError("audio: leer oder größer als 10 MB")
        fmt = args.get("format") if args.get("format") in ("wav", "mp3", "ogg", "webm", "m4a", "flac") else "wav"
        lang = str(args.get("language") or "")
        form = {"response_format": "json"}
        if re.fullmatch(r"[A-Za-z]{2,12}", lang):
            form["language"] = lang
        async with httpx.AsyncClient(timeout=300) as cl:
            r = await cl.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions",
                              files={"file": ("audio." + fmt, data)}, data=form, headers=dict(api_headers(), **low))
        if r.status_code != 200:
            return _result(f"Die Spracherkennung hat abgelehnt (HTTP {r.status_code}).", True)
        return _result(str(r.json().get("text", "")).strip() or "(nichts erkannt)")
    text = _text(args, "text", MAX_SPEAK)
    voice = str(args.get("voice") or profiles.settings(uid).get("voice") or "")
    if not re.fullmatch(r"[\w .\-]{0,64}", voice):
        raise ValueError("voice: nur Buchstaben, Ziffern, Leerzeichen, . _ -")
    lang = "English" if str(args.get("language") or "").lower() in ("en", "english", "englisch") else "German"
    body = {"input": text, "language": lang, "response_format": "mp3"}
    if voice:
        body["voice"] = voice
    out = bytearray()
    async with httpx.AsyncClient(timeout=300) as cl:
        async with cl.stream("POST", f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech", json=body,
                             headers=dict(api_headers(), **low)) as r:
            if r.status_code != 200:
                return _result(f"Die Sprachausgabe hat abgelehnt (HTTP {r.status_code}).", True)
            async for part in r.aiter_bytes():
                out += part
                if len(out) > 8 * 1024 ** 2:
                    return _result("Die Aufnahme wäre zu lang, bitte kürzeren Text.", True)
    return {"content": [{"type": "audio", "data": base64.b64encode(bytes(out)).decode(), "mimeType": "audio/mpeg"}],
            "isError": False}


# ---------------------------------------------------------------- reading
async def read(name, args, uid):
    import wiki
    if name in ("wikipedia", "archive_search"):
        q = _text(args, "query", 300)
        return await wiki.tool(name, {"query": q, "book": str(args.get("book") or "")[:120]}, {"who": {"id": uid}, "own": True})
    if name == "document_search":
        import wissen
        q = _text(args, "query", 300)
        hits = await wissen.search(uid, q)
        return "\n\n".join(f"[{wissen.where(h)}]\n{h['text']}" for h in hits) or "Keine passende Stelle in den Dokumenten."
    zone = _zone(uid)
    if name == "calendar_events":
        import calendars
        try:
            day = datetime.date.fromisoformat(str(args.get("date") or "")[:10])
        except ValueError:
            day = datetime.datetime.now(zone).date()
        days = args.get("days") if isinstance(args.get("days"), int) and not isinstance(args.get("days"), bool) else 1
        days = min(14, max(1, days))
        start = datetime.datetime.combine(day, datetime.time(), zone)
        r = await asyncio.wait_for(calendars.events(uid, start, start + datetime.timedelta(days=days), zone), 30)
        if r is None:
            return "Kein Kalender verbunden."
        evs, errors = r
        return ("\n".join(calendars.line(x) for x in evs) or "Keine Termine in diesem Zeitraum.") \
            + "".join(f"\nKalender „{n}“ nicht lesbar." for n, _ in errors)
    if name == "reminder_list":
        items = profiles.reminders(uid)
        return "\n".join(f"{_when(x['due'], zone)}: {x['text']}" for x in items) or "Keine offenen Erinnerungen."
    if name == "today":
        return await today_text(uid, zone)
    return "Unbekanntes Werkzeug."


def _zone(uid):
    from chat import user_zone
    return user_zone(profiles.settings(uid).get("tz", ""))


def _when(ms, zone):
    return datetime.datetime.fromtimestamp(ms / 1000, zone).strftime("%d.%m.%Y %H:%M")


async def today_text(uid, zone):
    import today
    lines = []
    if features.allowed("calendar", uid):
        cal = await today._events(uid, zone)
        nxt = cal.get("next") or []
        lines.append("Termine heute und morgen: " + ("; ".join(
            datetime.datetime.fromtimestamp(x["start"], zone).strftime("%d.%m. ") + ("ganztägig" if x["allday"] else
            datetime.datetime.fromtimestamp(x["start"], zone).strftime("%H:%M")) + " " + x["title"] for x in nxt)
            or ("keine" if cal.get("connected") else "kein Kalender verbunden")))
    if features.allowed("reminders", uid):
        now = time.time() * 1000
        rem = sorted((x for x in profiles.reminders(uid) if x.get("due", 0) >= now), key=lambda x: x["due"])
        lines.append(f"Offene Erinnerungen: {len(rem)}" + (f", nächste {_when(rem[0]['due'], zone)} {rem[0]['text'][:80]}" if rem else ""))
    if features.allowed("messages", uid):
        import messages
        lines.append(f"Ungelesene Nachrichten: {len(messages.unread(uid))}")
    return "\n".join(lines) or "Für dieses Profil ist nichts davon eingeschaltet."


# ---------------------------------------------------------------- ask the assistant
async def ask(request, c, question):
    """One turn of the assistant as the profile, only with the read tools of the connection (chat_turn.py
    reads "speech_mcp" from the request scope, which only the panel itself can set)."""
    import chat
    from starlette.requests import Request as Inner
    tools = sorted(set().union(*(ASK_TOOLS[n] for n in c["tools"] if n in ASK_TOOLS and tool_ok(n, c["uid"]))))
    body = {"messages": [{"role": "user", "content": question}], "client": "mcp", "speak": False,
            "tz": profiles.settings(c["uid"]).get("tz", "")}
    data = json.dumps(body).encode()
    scope = {"type": "http", "method": "POST", "path": "/api/chat", "headers": [], "query_string": b"",
             "client": request.scope.get("client") or ("mcp", 0), "server": ("127.0.0.1", 0), "scheme": "http",
             "speech_mcp": {"uid": c["uid"], "id": c["id"], "tools": tools}}

    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}
    response = await chat.chat(Inner(scope, receive))
    answer, error = "", ""
    async for chunk in getattr(response, "body_iterator", _none()):
        for line in (chunk.decode() if isinstance(chunk, bytes) else chunk).split("\n"):
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if ev.get("type") == "text":
                answer += str(ev.get("delta", ""))
            elif ev.get("type") in ("truncated", "retract"):
                answer = answer[:max(0, len(answer) - int(ev.get("drop") or 0))]
            elif ev.get("type") == "error" and not error:
                error = "Der Spark konnte gerade nicht antworten."
    from textnorm import hide_secrets
    return hide_secrets(answer.strip() or error or "Dazu habe ich keine Antwort.")


async def _none():
    if False:
        yield b""


# ---------------------------------------------------------------- acting with confirmation
def _acts_file(uid):
    return profiles._path(uid, "mcp-actions.json")


def actions(uid, now=None):
    now = time.time() if now is None else now
    try:
        with open(_acts_file(uid)) as f:
            items = json.load(f)
    except (OSError, ValueError):
        items = []
    items = [x for x in items if isinstance(x, dict) and now - x.get("t", 0) < 7 * 86400][-50:]
    for x in items:
        if x.get("state") == "wait" and now - x["t"] > ACTION_SECONDS:
            x["state"], x["result"] = "gone", "Nicht rechtzeitig bestätigt."
    return items


def _save_actions(uid, items):
    profiles._write(_acts_file(uid), items[-50:])


def _clean(text, most=200):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", " ", str(text or ""))).strip()[:most]


def plan(uid, name, args):
    """(what, item): the proposal in fixed words and what the panel will carry out; ValueError when it cannot be."""
    from chat import appointment, reminder_due
    tz = profiles.settings(uid).get("tz", "")
    if name == "home_assistant":
        import homeassistant
        if not homeassistant.get(uid):
            raise ValueError("Home Assistant ist für dieses Profil nicht verbunden")
        cmd = _clean(_text(args, "command", 200))
        return f"Smart Home: „{cmd}“", {"command": cmd}
    if name == "reminder_set":
        text = _clean(_text(args, "text", 200))
        due = reminder_due({k: args[k] for k in ("minutes", "at") if k in args}, tz)
        if not due:
            raise ValueError("Zeit fehlt oder liegt in der Vergangenheit: minutes oder at 'YYYY-MM-DDTHH:MM'")
        return f"Erinnerung „{text}“ am {_when(due, _zone(uid))}", {"text": text, "due": due}
    if name == "calendar_add":
        import calendars
        item = appointment({k: (_clean(v, 200) if isinstance(v, str) else v) for k, v in args.items()
                            if k in ("title", "start", "minutes", "days", "location")}, tz)
        if not calendars.get(uid)["calendars"]:
            raise ValueError("kein Kalender verbunden")
        return "Termin " + calendars.describe(item), {"event": item}
    raise ValueError("unknown action")


async def propose(c, name, args, now=None):
    """Leaves the action waiting for the profile's decision and tells it by push."""
    if notaus.refuse("aktion"):   # the Notaus holds every action off (notaus.py)
        return "Nicht vorgeschlagen: Der Notaus ist an, der Spark führt gerade nichts aus."
    now = time.time() if now is None else now
    uid = c["uid"]
    try:
        what, item = plan(uid, name, args)
    except (ValueError, TypeError, OverflowError) as e:
        return f"Nicht vorgeschlagen: {str(e)[:200]}"
    with _lock:
        items = actions(uid, now)
        if sum(1 for x in items if x["state"] == "wait") >= MAX_WAITING:
            return "Nicht vorgeschlagen: schon zu viele offene Vorschläge."
        aid = secrets.token_hex(4)
        items.append({"id": aid, "conn": c["id"], "by": c["name"], "tool": name, "what": what, "item": item,
                      "t": int(now), "state": "wait"})
        _save_actions(uid, items)
    try:
        import push
        await push.send(uid, "Spark: bitte bestätigen", f"„{c['name']}“ möchte: {what}. "
                        "Bestätigen unter Ich → Dienste per MCP.", tag="mcp")
    except Exception as e:
        print("mcp-server: push", type(e).__name__, flush=True)
    return (f"Vorgeschlagen, noch NICHT ausgeführt: {what}. Die Person entscheidet auf dem Spark "
            f"(höchstens {ACTION_SECONDS // 60} Minuten). Nummer {aid}, Stand mit action_status.")


def status(uid, aid):
    x = next((x for x in actions(uid) if x["id"] == aid), None)
    if not x:
        return "Unbekannte Nummer."
    return {"wait": "Wartet noch auf die Entscheidung.", "done": "Bestätigt und ausgeführt: ",
            "no": "Abgelehnt.", "gone": "Nicht rechtzeitig bestätigt, nicht ausgeführt.",
            "fail": "Bestätigt, aber nicht ausgeführt: "}[x["state"]] + (x.get("result") or "" if x["state"] in ("done", "fail") else "")


async def carry_out(uid, x):
    """Runs a confirmed action; returns (ok, text)."""
    if notaus.refuse("aktion"):
        return False, "Der Notaus ist an, nichts ausgeführt."
    item = x["item"]
    if x["tool"] == "home_assistant":
        import homeassistant
        ha = homeassistant.get(uid)
        if not ha or not features.allowed("ha", uid):
            return False, "Home Assistant ist nicht verbunden oder aus."
        ok, answer, _ = await homeassistant.command(ha, item["command"], "de")
        return bool(ok), _clean(answer, 300)
    if x["tool"] == "reminder_set":
        if not features.allowed("reminders", uid):
            return False, "Erinnerungen sind aus."
        it = profiles.add_reminder(uid, item["text"], item["due"])
        return True, f"Erinnerung gespeichert für {_when(it['due'], _zone(uid))}."
    if x["tool"] == "calendar_add":
        import calendars
        if not features.allowed("calendar", uid):
            return False, "Kalender ist aus."
        where = await calendars.add_event(uid, item["event"])
        return True, f"Eingetragen in „{_clean(where, 60)}“."
    return False, "unbekannt"


async def decide(uid, aid, yes, now=None):
    now = time.time() if now is None else now
    with _lock:
        items = actions(uid, now)
        x = next((x for x in items if x["id"] == aid), None)
        if not x or x["state"] != "wait":
            raise HTTPException(404, "Dieser Vorschlag wartet nicht mehr.")
        x["state"] = "busy"
        _save_actions(uid, items)
    if yes and act_on() and any(c["id"] == x["conn"] for c in _load()["conns"]):
        try:
            ok, text = await carry_out(uid, x)
        except Exception as e:
            ok, text = False, type(e).__name__
        state, result = ("done" if ok else "fail"), text
    else:
        state, result = "no", ("Abgelehnt." if yes is False else "Verbindung oder Schalter nicht mehr da.")
    with _lock:
        items = actions(uid, now)
        for y in items:
            if y["id"] == aid:
                y.update(state=state, result=result, decided=int(now))
        _save_actions(uid, items)
    guard.log("mcp_action", uid=uid, detail=f"{x['by'][:40]}: {x['what'][:120]} → {state}")
    return {"state": state, "result": result}


# ---------------------------------------------------------------- OAuth 2.1 (only "extern")
_auth_asks = {}     # id -> the checked sign-in request waiting in the panel
_codes = {}         # sha256(code) -> what the code stands for


def _gone(store, seconds, now):
    for k in [k for k, v in store.items() if now - v["t"] > seconds]:
        store.pop(k, None)


def _redirect_ok(uri):
    if not isinstance(uri, str) or len(uri) > 300 or "#" in uri:
        return False
    u = urlsplit(uri)
    if u.scheme == "https" and u.hostname:
        return True
    return u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")


def _client(cid):
    return next((x for x in _load()["clients"] if _same(x["id"], cid)), None) if isinstance(cid, str) else None


def _extern_or_404():
    if not (admin_on() and extern_on()):
        raise HTTPException(404, "not found")


def _meta(request):
    b = base_url(request)
    return {"issuer": b, "authorization_endpoint": b + "/oauth/authorize", "token_endpoint": b + "/oauth/token",
            "registration_endpoint": b + "/oauth/register", "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"], "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": ["mcp"]}


@router.get("/.well-known/oauth-authorization-server")
def oauth_meta(request: Request):
    _extern_or_404()
    return JSONResponse(_meta(request), headers={"Cache-Control": "no-store"})


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def resource_meta(request: Request):
    _extern_or_404()
    b = base_url(request)
    return JSONResponse({"resource": b + "/mcp", "authorization_servers": [b], "bearer_methods_supported": ["header"],
                         "scopes_supported": ["mcp"]}, headers={"Cache-Control": "no-store"})


@router.post("/oauth/register")
async def oauth_register(request: Request):
    """Dynamic client registration (RFC 7591): a program says its name and where to send the code. This
    alone opens nothing; the person decides in the panel."""
    _extern_or_404()
    guard.limit(request, "mcpreg")
    try:
        body = json.loads(await _body(request, MAX_JSON))
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not 1 <= len(uris) <= 5 or not all(_redirect_ok(u) for u in uris):
        return JSONResponse({"error": "invalid_redirect_uri",
                             "error_description": "https addresses (or http://localhost), at most 5"}, status_code=400)
    name = _clean(body.get("client_name") or urlsplit(uris[0]).hostname, 60) or "Programm"
    now = time.time()
    item = {"id": "c_" + secrets.token_urlsafe(18), "name": name, "redirect": list(dict.fromkeys(uris)), "created": int(now)}
    with _lock:
        d = _load()
        _prune(d, now)
        if len(d["clients"]) >= MAX_CLIENTS:
            return JSONResponse({"error": "temporarily_unavailable"}, status_code=429)
        d["clients"].append(item)
        _save(d)
    print("mcp-server: program registered for OAuth:", name[:40], flush=True)
    return JSONResponse({"client_id": item["id"], "client_name": name, "redirect_uris": item["redirect"],
                         "client_id_issued_at": item["created"], "token_endpoint_auth_method": "none",
                         "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]},
                        status_code=201, headers={"Cache-Control": "no-store"})


@router.get("/oauth/authorize")
def oauth_authorize(request: Request):
    """Checks the request and hands it to the panel page (Ich → Dienste per MCP), where the signed-in
    profile sees the warning, picks the tools and confirms with its code."""
    _extern_or_404()
    guard.limit(request, "mcpreg")
    q = request.query_params
    client = _client(q.get("client_id"))
    uri = q.get("redirect_uri") or (client["redirect"][0] if client and len(client["redirect"]) == 1 else "")
    if not client or uri not in client["redirect"]:
        raise HTTPException(400, "Unbekanntes Programm oder Rücksprungadresse.")
    state = q.get("state") or ""
    if len(state) > 500:
        raise HTTPException(400, "state too long")

    def back(err):
        return RedirectResponse(uri + ("&" if "?" in uri else "?") + urlencode(
            {"error": err, **({"state": state} if state else {})}), status_code=302)
    if q.get("response_type") != "code":
        return back("unsupported_response_type")
    if q.get("code_challenge_method") != "S256" or not CHALLENGE.fullmatch(q.get("code_challenge") or ""):
        return back("invalid_request")
    now = time.time()
    rid = secrets.token_urlsafe(24)
    with _lock:
        _gone(_auth_asks, ASK_SECONDS, now)
        if len(_auth_asks) >= 50:
            return back("temporarily_unavailable")
        _auth_asks[rid] = {"t": now, "client": client["id"], "name": client["name"], "redirect": uri, "state": state,
                           "challenge": q.get("code_challenge"), "base": base_url(request)}
    return RedirectResponse("/#mcpauth=" + rid, status_code=302)


def auth_ask(rid, now=None):
    now = time.time() if now is None else now
    with _lock:
        _gone(_auth_asks, ASK_SECONDS, now)
        return _auth_asks.get(rid) if isinstance(rid, str) else None


def new_code(ask, uid, tools, name, now=None):
    now = time.time() if now is None else now
    code = secrets.token_urlsafe(32)
    with _lock:
        _gone(_codes, CODE_SECONDS, now)
        _codes[_hash(code)] = {"t": now, "uid": uid, "tools": tools, "name": name, "client": ask["client"],
                               "client_name": ask["name"], "redirect": ask["redirect"], "challenge": ask["challenge"]}
    return code


def _grant_error(err, why=""):
    return JSONResponse({"error": err, **({"error_description": why} if why else {})}, status_code=400,
                        headers={"Cache-Control": "no-store"})


def _tokens(c, now):
    access, refresh = "spo_" + secrets.token_urlsafe(32), "spr_" + secrets.token_urlsafe(32)
    c.update(access=_hash(access), access_until=int(now + ACCESS_SECONDS), refresh=_hash(refresh),
             refresh_until=int(now + REFRESH_DAYS * 86400), last=int(now))
    return {"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_SECONDS, "refresh_token": refresh,
            "scope": "mcp"}


@router.post("/oauth/token")
async def oauth_token(request: Request):
    _extern_or_404()
    guard.limit(request, "mcptoken")
    raw = await _body(request, MAX_JSON)
    if "json" in request.headers.get("content-type", ""):
        try:
            f = json.loads(raw)
        except ValueError:
            f = {}
        f = {k: v for k, v in f.items() if isinstance(v, str)} if isinstance(f, dict) else {}
    else:
        from urllib.parse import parse_qsl
        f = dict(parse_qsl(raw.decode("utf-8", "replace"), max_num_fields=20))
    now = time.time()
    if f.get("grant_type") == "authorization_code":
        with _lock:
            _gone(_codes, CODE_SECONDS, now)
            g = _codes.pop(_hash(f.get("code") or ""), None)
        if not g or not _same(g["client"], f.get("client_id")) or f.get("redirect_uri", g["redirect"]) != g["redirect"]:
            return _grant_error("invalid_grant")
        verifier = f.get("code_verifier") or ""
        want = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        if not CHALLENGE.fullmatch(verifier) or not _same(want, g["challenge"]):
            return _grant_error("invalid_grant", "PKCE check failed")
        c = {"id": "m_" + secrets.token_hex(6), "uid": g["uid"], "name": g["name"], "kind": "oauth", "where": "extern",
             "tools": g["tools"], "client": g["client"], "client_name": g["client_name"], "created": int(now)}
        out = _tokens(c, now)
        with _lock:
            d = _load()
            _prune(d, now)
            if sum(1 for x in d["conns"] if x["uid"] == g["uid"]) >= MAX_CONNS:
                return _grant_error("invalid_grant", "too many connections")
            d["conns"].append(c)
            _save(d)
        guard.log("mcp_connect", uid=g["uid"], detail=f"{g['name'][:40]} (OAuth, extern)")
        return JSONResponse(out, headers={"Cache-Control": "no-store"})
    if f.get("grant_type") == "refresh_token":
        h = _hash(f.get("refresh_token") or "")
        with _lock:
            d = _load()
            c = next((x for x in d["conns"] if x["kind"] == "oauth" and _same(x.get("refresh"), h)), None)
            if not c or now > c.get("refresh_until", 0) or not _same(c["client"], f.get("client_id")) or not _alive(c, now):
                return _grant_error("invalid_grant")
            out = _tokens(c, now)
            _save(d)
        return JSONResponse(out, headers={"Cache-Control": "no-store"})
    return _grant_error("unsupported_grant_type")


# ---------------------------------------------------------------- the profile's page (Ich → Dienste per MCP)
def _on(prof=Depends(browser_profile)):
    """Only from the profile's own browser login (never with a device key or a token of this server)."""
    if not admin_on():
        raise HTTPException(403, "Spark als MCP-Server ist vom Admin ausgeschaltet.")
    return prof


async def _json(request):
    try:
        d = json.loads(await _body(request, MAX_JSON) or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    if not isinstance(d, dict):
        raise HTTPException(400, "a JSON object")
    return d


def _name(v):
    v = str(v or "").strip()
    if not NAME.fullmatch(v):
        raise HTTPException(400, "Name: 1 bis 60 Zeichen (Buchstaben, Ziffern, Leerzeichen, . , : ( ) + & ' -)")
    return v


async def _where_ok(request, prof, where):
    """Home network with the code window; outside only with the admin's switch, the profile's second step
    and a fresh code (it opens a way into the profile from the internet)."""
    if where == "lokal":
        await confirm_code(request, prof["id"], prof["name"])
        return
    if where != "extern":
        raise HTTPException(400, "where: lokal or extern")
    if not extern_on():
        raise HTTPException(403, "Zugriff von außen ist vom Admin ausgeschaltet.")
    import mfa
    if not mfa.enabled(prof["id"]):
        raise HTTPException(403, "Für Zugriff von außen braucht dein Profil den zweiten Anmeldeschritt (Ich → Sicherheit).")
    await confirm_code(request, prof["id"], prof["name"], fresh=True)


def catalog(uid):
    return [{"name": n, "group": TOOLS[n][0], "label": TOOLS[n][2], "ok": tool_ok(n, uid)}
            for n in TOOLS if n != "action_status" and (TOOLS[n][0] != "act" or act_on())]


@router.get("/api/profile/mcp")
def profile_get(request: Request, prof=Depends(browser_profile)):
    import mfa
    uid = prof["id"]
    guard.limit(request, "features", uid)
    return {"enabled": admin_on(), "on": features.allowed("mcpserver", uid), "extern": extern_on(), "act": act_on(),
            "mfa": mfa.enabled(uid), "url": base_url(request) + "/mcp", "days": DAYS, "groups": GROUPS,
            "tools": catalog(uid) if admin_on() else [], "conns": conns(uid) if admin_on() else [],
            "actions": [{k: x.get(k) for k in ("id", "by", "what", "t", "state", "result")} for x in actions(uid)][::-1][:20]}


@router.post("/api/profile/mcp/keys")
async def profile_key(request: Request, prof=Depends(_on)):
    uid = prof["id"]
    guard.limit(request, "features", uid)
    if not features.allowed("mcpserver", uid):
        raise HTTPException(403, "Erst „Spark als MCP-Server für mich“ einschalten.")
    body = await _json(request)
    name, tools, where = _name(body.get("name")), clean_tools(body.get("tools"), uid), body.get("where", "lokal")
    await _where_ok(request, prof, where)
    token, c = add_key(uid, name, tools, where)
    guard.log("mcp_connect", uid=uid, detail=f"{name} (Schlüssel, {where})")
    return {"token": token, "conn": public(c), "url": base_url(request) + "/mcp"}


@router.put("/api/profile/mcp/conns/{cid}")
async def profile_change(cid: str, request: Request, prof=Depends(_on)):
    uid = prof["id"]
    guard.limit(request, "features", uid)
    body = await _json(request)
    old = next((c for c in conns(uid) if c["id"] == cid), None)
    if not old:
        raise HTTPException(404, "no such connection")
    tools = clean_tools(body["tools"], uid) if "tools" in body else None
    where = body.get("where") if "where" in body else None
    if old["kind"] == "oauth" and where not in (None, "extern"):
        raise HTTPException(400, "Eine OAuth-Verbindung ist immer extern.")
    if where == "extern" and old["where"] != "extern":
        await _where_ok(request, prof, "extern")
    elif where not in (None, "lokal", "extern"):
        raise HTTPException(400, "where: lokal or extern")
    else:
        await confirm_code(request, uid, prof["name"])
    c = change(cid, uid, tools=tools, where=where, name=_name(body["name"]) if "name" in body else None)
    guard.log("mcp_change", uid=uid, detail=f"{c['name']} ({c['where']}, {len(c['tools'])} Werkzeuge)")
    return public(c)


@router.delete("/api/profile/mcp/conns/{cid}")
def profile_remove(cid: str, request: Request, prof=Depends(browser_profile)):
    hit = remove(cid, prof["id"])
    if not hit:
        raise HTTPException(404, "no such connection")
    guard.log("mcp_remove", uid=prof["id"], detail=hit["name"])
    return {"ok": True}


@router.post("/api/profile/mcp/actions/{aid}")
async def profile_decide(aid: str, request: Request, prof=Depends(_on)):
    body = await _json(request)
    yes = body.get("yes")
    if not isinstance(yes, bool):
        raise HTTPException(400, "yes: true or false")
    if yes:
        await confirm_code(request, prof["id"], prof["name"])
    return await decide(prof["id"], str(aid)[:20], yes)


@router.get("/api/profile/mcp/oauth/{rid}")
def profile_auth_get(rid: str, prof=Depends(_on)):
    ask = auth_ask(rid)
    if not ask:
        raise HTTPException(404, "Diese Anmeldung ist abgelaufen. Im Programm noch einmal verbinden.")
    return {"name": ask["name"], "host": urlsplit(ask["redirect"]).hostname, "extern": extern_on(),
            "tools": catalog(prof["id"])}


@router.post("/api/profile/mcp/oauth/{rid}")
async def profile_auth_answer(rid: str, request: Request, prof=Depends(_on)):
    uid = prof["id"]
    ask = auth_ask(rid)
    if not ask:
        raise HTTPException(404, "Diese Anmeldung ist abgelaufen. Im Programm noch einmal verbinden.")
    body = await _json(request)
    sep = "&" if "?" in ask["redirect"] else "?"
    extra = {"state": ask["state"]} if ask["state"] else {}
    if body.get("yes") is not True:
        with _lock:
            _auth_asks.pop(rid, None)
        return {"redirect": ask["redirect"] + sep + urlencode({"error": "access_denied", **extra})}
    if not features.allowed("mcpserver", uid):
        raise HTTPException(403, "Erst „Spark als MCP-Server für mich“ einschalten.")
    tools = clean_tools(body.get("tools"), uid)
    name = _name(body.get("name") or ask["name"])
    await _where_ok(request, prof, "extern")
    with _lock:
        if not _auth_asks.pop(rid, None):
            raise HTTPException(404, "Diese Anmeldung ist abgelaufen.")
    code = new_code(ask, uid, tools, name)
    return {"redirect": ask["redirect"] + sep + urlencode({"code": code, **extra, "iss": ask["base"]})}


# ---------------------------------------------------------------- the admin's overview
@router.get("/api/admin/mcp", dependencies=[Depends(auth)])
def admin_list(request: Request):
    guard.limit(request, "features", admin=True)
    now = time.time()
    names = {u["id"]: u["name"] for u in profiles.names()}
    return {"enabled": admin_on(), "extern": extern_on(), "act": act_on(),
            "conns": [dict(public(c, now), profile=names.get(c["uid"], "?")) for c in _load()["conns"]
                      if _alive(c, now) and c["uid"] in names]}


@router.delete("/api/admin/mcp/{cid}", dependencies=[Depends(auth), Depends(admin_code)])
def admin_remove(cid: str):
    hit = remove(cid)
    if not hit:
        raise HTTPException(404, "no such connection")
    guard.log("mcp_remove", uid=hit["uid"], by="admin", detail=hit["name"])
    return {"ok": True}
