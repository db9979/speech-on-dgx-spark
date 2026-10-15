"""Terminal-Client (plan plaene/tui-client.md, Dominik 2026-10-15 „1b 2b 3a 4a“): `spark-tui`, one Python file
(app/tui/spark-tui.py, Textual) for a terminal, e.g. the ClockworkPi uConsole, also over SSH. It talks to the panel
like the iPhone app: chat with the streamed answer, the profile's conversations, Heute, and the agent's jobs, plans
and routines (agent.py, with the admin's levels as everywhere).

Off until the admin switches chat.terminal on (Funktionen → Terminal-Client); then it works for every profile the
admin did not block; guests never. Pairing: the profile's own browser login (with its second step, when it has one)
asks for a setup line "https://<host>:<https port>#tui=<code>&fp=<sha256 of the panel's certificate>" at home, or
"https://<outside address>#tui=<code>" when the browser is on an outside address (a reverse proxy with a certificate
of a known authority: checked as usual, nothing pinned). The program checks the certificate (against fp when there is
one, then pinned), keeps the address and trades the code (144 bits, once, CODE_SECONDS, only its hash kept,
kopplung.py) for its own device key with scope "tui". That key reaches only TUI_RULES (profiles.current), only while
the switch is on (TUI_GATE); removing the device in Ich → Terminal stops it at once. Texts are data: nothing here acts
on them, the answers come from the normal assistant with its own rules (Weiche, tools, code word, Notaus).

    browser login (own profile):
    GET    /api/profile/terminal             the paired terminals, the program file (size, SHA-256)
    POST   /api/profile/terminal/pair {origin} a setup line (confirmation code first)
    DELETE /api/profile/terminal/{did}       remove a terminal (its key stops at once)
    program:
    POST   /api/tui/pair {code, name}        -> {"key", "profile"}
    GET    /api/tui/hello                    -> version, profile, parts (also the "online" mark for Live)
    and the panel's own paths in TUI_RULES (chat, conversations, Heute, agent)
"""
import hashlib
import os
import re
import ssl
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import core
import features
import guard
import kopplung
import profiles
from account import browser_profile
from common import TLS_DIR, load_config
from core import app_version, assistant, confirm_code, own_profile

router = APIRouter()

CODE_SECONDS = 600
MAX_PENDING = 20          # open codes on the whole Spark
PER_PROFILE = 3           # open codes of one profile (a new one replaces the oldest)
MAX_DEVICES = 5           # paired terminals per profile
MAX_BODY = 1024
SEEN_SECONDS = 180        # a terminal that said hello this recently counts as open (Live: only the number)
ORIGIN = re.compile(r"(https?)://([A-Za-z0-9.\-]{1,253}|\[[0-9A-Fa-f:.]{2,45}\])(?::(\d{1,5}))?")
NAME = re.compile(r"[\w .\-]{1,40}")
PROGRAM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tui", "spark-tui.py")

_codes = kopplung.Codes(kopplung.link_code, kopplung.link_form, CODE_SECONDS, MAX_PENDING, PER_PROFILE, kind="tui")
_seen = {}   # device id -> time of its last hello (in memory only)

# The panel's own paths a terminal's key reaches: (methods, pattern), fullmatch. The agent's paths want the
# profile's browser login (reports can hold private data); for these the key counts like it (profiles.current sets
# speech_app_area "tui"), nothing else: no security, devices, connections or secrets.
_ID = r"[0-9a-f]{6,16}"
TUI_RULES = (
    (("POST",), r"/api/chat"),
    (("GET", "PUT"), r"/api/profile/convos"),
    (("DELETE",), r"/api/profile/convos/[\w\-]{1,40}"),
    (("GET",), r"/api/profile/today"),
    (("GET",), r"/api/features"),
    (("GET",), r"/api/tui/hello"),
    (("GET",), r"/api/profile/agent"),
    (("POST",), r"/api/profile/agent/jobs"),
    (("GET", "DELETE"), rf"/api/profile/agent/jobs/{_ID}"),
    (("POST",), rf"/api/profile/agent/jobs/{_ID}/(?:cancel|doc)"),
    (("POST",), rf"/api/profile/agent/plans/{_ID}/(?:pause|run)"),
)
_RULES = tuple((m, re.compile(p)) for m, p in TUI_RULES)
AGENT = re.compile(r"/api/profile/agent(?:/.*)?")


def admin_on():
    return features.admin_on("terminal")


def reaches(request):
    """The rule of TUI_RULES this request of a terminal's key matches: None (not for it), "panel", or "agent"."""
    path, method = request.scope.get("path") or "", request.method
    if not any(method in m and p.fullmatch(path) for m, p in _RULES):
        return None
    return "agent" if AGENT.fullmatch(path) else "panel"


profiles.TUI_GATE[0] = lambda uid: features.allowed("terminal", uid)
profiles.TUI_REACH[0] = reaches


def devices(uid):
    return [x for x in profiles.own_devices(uid) if x.get("tui")]


def online(now=None):
    """How many terminals said hello in the last SEEN_SECONDS (Zustand → Live, only the number)."""
    now = time.time() if now is None else now
    return sum(1 for t in list(_seen.values()) if now - t < SEEN_SECONDS)


def cert_sha256():
    """SHA-256 of the panel's https certificate (DER, hex), "" while there is none: the program pins exactly it."""
    try:
        with open(os.path.join(TLS_DIR, "cert.pem")) as f:
            der = ssl.PEM_cert_to_DER_cert(f.read())
    except (OSError, ValueError):
        return ""
    return hashlib.sha256(der).hexdigest()


_prog = {}


def program():
    """The program file the panel hands out: name, size and SHA-256 (to compare after the download)."""
    try:
        st = os.stat(PROGRAM)
    except OSError:
        return {}
    if _prog.get("mtime") != st.st_mtime:
        with open(PROGRAM, "rb") as f:
            data = f.read()
        m = re.search(rb'^VERSION = "([0-9.]{1,12})"', data, re.M)
        _prog.update(mtime=st.st_mtime, info={"name": "spark-tui.py", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                              "version": m.group(1).decode() if m else ""})
    return _prog["info"]


def setup_base(origin, pcfg):
    """(address, pin) for the setup line from the address the profile's browser is on: at home (the panel's own
    ports) the panel's https port with its certificate pinned; through an outside address (a reverse proxy with a
    certificate of a known authority) that https address as it is, checked against the usual authorities.
    None when it cannot be (no https at home, plain http outside)."""
    m = ORIGIN.fullmatch(str(origin or "").strip().lower().rstrip("/"))
    if not m:
        raise HTTPException(400, "origin: http(s)://name or http(s)://name:port, without a path")
    scheme, host, port = m.group(1), m.group(2), int(m.group(3) or (443 if m.group(1) == "https" else 80))
    if port in (pcfg.get("port"), pcfg.get("https_port")):
        fp = cert_sha256()
        return (f"https://{host}:{int(pcfg['https_port'])}", fp) if pcfg.get("https_port") and fp else None
    if scheme != "https":
        return None
    return (f"https://{host}" + ("" if port == 443 else f":{port}"), "")


def _on(request: Request, prof=Depends(browser_profile)):
    """Pairing and removing terminals: only from the profile's own browser login, never with a device key."""
    if not admin_on():
        raise HTTPException(403, "the terminal client is turned off")
    if request.method not in ("GET", "HEAD", "DELETE") and features.blocked("terminal", prof["id"]):   # own data: also while blocked
        raise HTTPException(403, "blocked for this profile by the admin (Funktionen → Wer darf was)")
    return prof


@router.get("/api/profile/terminal", dependencies=[Depends(assistant)])
def profile_get(prof=Depends(own_profile)):
    now = time.time()
    items = [dict(x, online=now - _seen.get(x["id"], -1e12) < SEEN_SECONDS) for x in devices(prof["id"])]
    return {"enabled": admin_on(), "on": features.allowed("terminal", prof["id"]), "devices": items, "minutes": CODE_SECONDS // 60,
            "max": MAX_DEVICES, "https": bool(load_config("panel").get("https_port") and cert_sha256()),
            "program": program()}


@router.post("/api/profile/terminal/pair", dependencies=[Depends(assistant)])
async def profile_pair(request: Request, prof=Depends(_on)):
    """A one-time setup line for `spark-tui koppeln '…'` (after the confirmation code: a new way into the profile)."""
    body = await core.json_body(request, MAX_BODY, lenient=True)
    if not features.allowed("terminal", prof["id"]):
        raise HTTPException(403, "Den Terminal-Client hat der Admin für dein Profil gesperrt (Funktionen → Wer darf was).")
    if len(devices(prof["id"])) >= MAX_DEVICES:
        raise HTTPException(409, f"Schon {MAX_DEVICES} Terminals gekoppelt. Erst eins entfernen.")
    base = setup_base(body.get("origin"), load_config("panel"))
    if not base:
        print("terminal: setup line refused | no https", flush=True)
        raise HTTPException(409, "Über diese Adresse geht es nur mit https. Der Terminal-Client spricht nur verschlüsselt mit dem Spark.")
    await confirm_code(request, prof["id"], prof["name"])
    code = _codes.new(prof["id"])
    print("terminal: setup line made for", profiles.log_name(prof), "|", "pinned" if base[1] else "outside address", flush=True)
    return {"setup": f"{base[0]}#tui={code}" + (f"&fp={base[1]}" if base[1] else ""), "minutes": CODE_SECONDS // 60,
            "pinned": bool(base[1])}


@router.delete("/api/profile/terminal/{did}", dependencies=[Depends(assistant)])
def profile_remove(did: str, prof=Depends(browser_profile)):
    if not any(x["id"] == did for x in devices(prof["id"])):
        print("terminal: remove refused | not this profile's terminal", flush=True)
        raise HTTPException(404, "no such terminal")
    _remove(did)
    print("terminal: terminal removed for", profiles.log_name(prof), flush=True)
    return profile_get(prof)


def _remove(did):
    profiles.delete_device(did)
    _seen.pop(did, None)
    _live_mark("Terminal entfernt")


def _clear(uid):
    for x in devices(uid):
        _remove(x["id"])


# own data for Ich while the admin blocks the terminal client for the profile (features.OWN): its paired terminals
features.OWN["terminal"] = (lambda uid: len(devices(uid)), _clear)


@router.post("/api/tui/pair")
async def program_pair(request: Request):
    """The program's first contact: the one-time code gives it its own key (scope "tui")."""
    guard.limit(request, "pair")
    body = await core.json_body(request, MAX_BODY, lenient=True)
    uid = _codes.take(body.get("code"))
    prof = uid and profiles.by_id(uid)
    if not prof or not features.allowed("terminal", uid):
        print("terminal: pairing refused | code unknown or expired", flush=True)
        raise HTTPException(400, "Der Kopplungscode passt nicht oder ist abgelaufen. Im Panel unter Ich → Terminal einen neuen holen.")
    if len(devices(uid)) >= MAX_DEVICES:
        print("terminal: pairing refused | too many terminals", flush=True)
        raise HTTPException(409, "Zu viele Terminals für dieses Profil.")
    name = str(body.get("name") or "").strip()
    key = profiles.add_device("Terminal · " + (name if NAME.fullmatch(name) else "spark-tui"), uid, scope="tui")
    print("terminal: terminal paired for", profiles.log_name(prof), flush=True)
    _live_mark("Terminal gekoppelt")
    return {"key": key, "profile": prof["name"]}


@router.get("/api/tui/hello", dependencies=[Depends(assistant)])
def program_hello(request: Request, prof=Depends(own_profile)):
    """What the program shows in its head line; also its "online" mark (Live counts only the number)."""
    dev = profiles.device(request)
    if not dev or dev.get("scope") != "tui":
        raise HTTPException(403, "only for a paired terminal")
    _seen[dev["id"]] = time.time()
    if len(_seen) > 1000:
        _seen.clear()
    import agent
    uid = prof["id"]
    return {"spark": app_version(), "profile": prof["name"], "program": program().get("version", ""),
            "agent": agent.level(uid) if agent.admin_on() else "", "today": True}


def _live_mark(text):
    """Zustand → Live: a line under Ereignisse, fixed words only (never the profile's name)."""
    try:
        import live
        live.mark("Eingang", text)
    except Exception:
        pass
