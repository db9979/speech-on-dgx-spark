"""Outside tools over MCP (Model Context Protocol): the admin adds a tool server (Paperless, Nextcloud,
GitHub ...) by its address, and the panel offers single tools of it to the assistant and to background
jobs (agent.py).

Only servers reached over HTTP ("Streamable HTTP"); the panel never starts a program for a server, so
nothing foreign runs on the Spark. Every server and every tool is off until the admin turns it on:

    mode "off"   not offered (default for every tool the server lists)
    mode "read"  offered to profiles with level "nur lesen" or higher; its answer is outside text
                 (locks switching and saving for the rest of the answer, never learned)
    mode "act"   only for level "auch handeln"; the model can only propose it, the person's "Ja" in
                 the next message runs it (agent.answer), never after outside text, never in a job

Adding, changing or removing a server or a tool's mode needs the admin's login and a fresh code
(admin_code). The token is kept sealed (vault.py) and never sent back. Connections go through
netguard.USER: public addresses, home network addresses only when the admin allows them (Einstellungen
→ Sicherheit), never the Spark's own services; answers are cut at MAX_BYTES.

    STATE/agent.json  "mcp": [{"id", "name", "url", "token" (sealed), "users": [uid],
                               "tools": [{"name", "desc", "schema", "mode"}], "checked"}]
"""
import json
import re
import time

import httpx

import netguard
import vault

PROTOCOL = "2025-06-18"
MAX_BYTES = 2 * 1024 * 1024
MAX_SERVERS = 8
MAX_TOOLS = 60           # per server
MAX_ARGS = 4000          # characters of JSON a call may send
MAX_RESULT = 8000        # characters of an answer handed to the model
MAX_SCHEMA = 4000
TIMEOUT = 30
MODES = ("off", "read", "act")
TOOL_NAME = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
EMPTY_SCHEMA = {"type": "object", "properties": {}}


def clean_text(text, most):
    """Plain text from the server: no control characters, no markers of outside text."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text or ""))
    return re.sub(r"<{3,}|>{3,}", " ", text).strip()[:most]


def clean_schema(s):
    """The tool's input schema, if it is a small JSON object; else an empty one."""
    if not isinstance(s, dict) or s.get("type", "object") != "object":
        return dict(EMPTY_SCHEMA)
    try:
        raw = json.dumps(s, ensure_ascii=False)
    except (TypeError, ValueError):
        return dict(EMPTY_SCHEMA)
    if len(raw) > MAX_SCHEMA or "<<<" in raw or ">>>" in raw:
        return dict(EMPTY_SCHEMA)
    return json.loads(raw)


def valid_url(url):
    """http(s) only, no user:password@ in the address (the token goes in its own field, sealed)."""
    return bool(re.fullmatch(r"https?://[^\s/?#@]+(/[^\s#]*)?", str(url or ""))) and len(url) <= 300


def _client(url, token):
    head = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
            "User-Agent": "speech-on-dgx-spark"}
    if token:
        head["Authorization"] = f"Bearer {token}"
    return netguard.client(netguard.USER, origin=url, max_bytes=MAX_BYTES,
                           timeout=httpx.Timeout(TIMEOUT, connect=8), headers=head, follow_redirects=False)


def _messages(r):
    """JSON-RPC messages of an answer: plain JSON or a stream of server-sent events."""
    kind = r.headers.get("content-type", "")
    if "text/event-stream" in kind:
        out = []
        for block in r.text.split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
            if data:
                try:
                    out.append(json.loads(data))
                except ValueError:
                    pass
        return out
    try:
        d = r.json()
    except ValueError:
        raise ValueError("the server did not answer with JSON")
    return d if isinstance(d, list) else [d]


class Session:
    """One short conversation with a server: initialize, then requests (each call opens its own)."""

    def __init__(self, url, token):
        self.url, self.token, self.sid, self.n = url, token, None, 0

    async def __aenter__(self):
        self.c = _client(self.url, self.token)
        await self.c.__aenter__()
        res = await self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                                "clientInfo": {"name": "speech-on-dgx-spark", "version": "1"}})
        if not isinstance(res, dict):
            raise ValueError("the server did not answer initialize")
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    async def __aexit__(self, *exc):
        await self.c.__aexit__(*exc)

    async def _post(self, msg):
        head = {"MCP-Protocol-Version": PROTOCOL}
        if self.sid:
            head["Mcp-Session-Id"] = self.sid
        r = await self.c.post(self.url, content=json.dumps(msg), headers=head)
        if r.status_code == 401 or r.status_code == 403:
            raise ValueError(f"the server refuses the token ({r.status_code})")
        if r.is_redirect:
            raise ValueError("the server redirects; enter the final address")
        if r.status_code >= 400:
            raise ValueError(f"the server answered {r.status_code}")
        sid = r.headers.get("mcp-session-id")
        if sid and re.fullmatch(r"[\x21-\x7e]{1,200}", sid):
            self.sid = sid
        return r

    async def request(self, method, params):
        self.n += 1
        r = await self._post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        for m in _messages(r):
            if isinstance(m, dict) and m.get("id") == self.n:
                if m.get("error"):
                    err = m["error"] if isinstance(m["error"], dict) else {}
                    raise ValueError("the server reports: " + clean_text(err.get("message") or "error", 200))
                return m.get("result")
        raise ValueError("no answer from the server")


async def list_tools(url, token):
    """[{"name", "desc", "schema"}] the server offers (at most MAX_TOOLS)."""
    out, cursor = [], None
    async with Session(url, token) as s:
        for _ in range(4):
            res = await s.request("tools/list", {"cursor": cursor} if cursor else {})
            res = res if isinstance(res, dict) else {}
            for t in res.get("tools") or []:
                if not isinstance(t, dict) or not TOOL_NAME.fullmatch(str(t.get("name", ""))):
                    continue
                if any(x["name"] == t["name"] for x in out):
                    continue
                out.append({"name": t["name"], "desc": clean_text(t.get("description"), 300),
                            "schema": clean_schema(t.get("inputSchema"))})
                if len(out) >= MAX_TOOLS:
                    return out
            cursor = res.get("nextCursor")
            if not isinstance(cursor, str) or not cursor or len(cursor) > 500:
                break
    return out


def result_text(res):
    """The readable text of a tools/call result."""
    res = res if isinstance(res, dict) else {}
    parts = []
    for c in res.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(str(c.get("text", "")))
        elif isinstance(c, dict):
            parts.append(f"[{clean_text(c.get('type'), 20) or 'content'} not shown]")
    if not parts and res.get("structuredContent") is not None:
        try:
            parts.append(json.dumps(res["structuredContent"], ensure_ascii=False))
        except (TypeError, ValueError):
            pass
    text = clean_text("\n".join(parts), MAX_RESULT)
    return ("The tool reports an error: " if res.get("isError") else "") + (text or "(no text)")


async def call(server, tool, args):
    if not isinstance(args, dict):
        args = {}
    raw = json.dumps(args, ensure_ascii=False)
    if len(raw) > MAX_ARGS:
        raise ValueError("the arguments are too long")
    async with Session(server["url"], token(server)) as s:
        return result_text(await s.request("tools/call", {"name": tool, "arguments": args}))


# ---------------------------------------------------------------- stored servers (in STATE/agent.json)
def token(server):
    return vault.open_(server.get("token", "")) if server.get("token") else ""


def public(server):
    """A server for the admin page: never the token."""
    return {"id": server["id"], "name": server["name"], "url": server["url"], "has_token": bool(server.get("token")),
            "users": list(server.get("users") or []), "checked": server.get("checked", 0),
            "tools": [{"name": t["name"], "desc": t["desc"], "mode": t.get("mode", "off")} for t in server.get("tools") or []]}


def exposed(sid, name):
    """The name the model sees: mcp_<server>_<tool>, letters, digits and _ only."""
    return ("mcp_" + sid + "_" + re.sub(r"[^a-z0-9_]", "_", name.lower()))[:64]


def tools_for(servers, uid, modes):
    """[(exposed name, server, tool)] of the tools in these modes that this profile may use."""
    out = []
    for s in servers:
        if uid not in (s.get("users") or []):
            continue
        for t in s.get("tools") or []:
            if t.get("mode") in modes:
                out.append((exposed(s["id"], t["name"]), s, t))
    return out


def as_tool(name, server, t):
    """The tool in the format the language model gets."""
    return {"type": "function", "function": {
        "name": name, "description": f"{t['desc'] or t['name']} (tool '{t['name']}' of {server['name']})"[:400],
        "parameters": t.get("schema") or dict(EMPTY_SCHEMA)}}


def new_server(name, url, tok, tools):
    import secrets
    return {"id": secrets.token_hex(3), "name": name, "url": url, "token": vault.seal(tok) if tok else "",
            "users": [], "tools": [dict(t, mode="off") for t in tools], "checked": int(time.time())}


def merge_tools(old, fresh):
    """After a new tools/list: modes stay for tools that are still there; a tool whose description or
    input changed goes back to off (the admin decided about the old one)."""
    was = {t["name"]: t for t in old}
    out = []
    for t in fresh:
        o = was.get(t["name"])
        keep = o and o.get("desc") == t["desc"] and o.get("schema") == t["schema"]
        out.append(dict(t, mode=o.get("mode", "off") if keep else "off"))
    return out
