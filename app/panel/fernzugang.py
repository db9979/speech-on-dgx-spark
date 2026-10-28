"""Fernzugang (plan ssh-vermittlung, Dominik 2026-10-28 „umsetzten“, Stufe 1): a server elsewhere (a VPS, a NAS at
friends') calls the panel by itself and the admin works in its shell in the browser, like Raspberry Pi Connect but the
relay is the own Pi. No new port: the anchor reaches the panel the way the browser does (443 → reverse proxy → :31443),
only as WebSocket over TLS.

    remote server                 panel (this module)                         browser of an admin
    spark-anker (app/anker) ──WSS /api/fernzugang/anker──► relay ◄──WSS /api/fernzugang/terminal── xterm.js
    127.0.0.1:22 (own sshd) ◄── bytes only ── paramiko SSH client (key from the vault, host key pinned)

The anchor only passes bytes between the panel and its own sshd on 127.0.0.1:22; SSH runs end to end between the Pi
(paramiko, SSH client) and that sshd, so neither the reverse proxy nor the anchor sees the session. The Pi logs in only
with its own ed25519 key of this device (made at pairing, sealed in the vault, never shown), as the user `spark`, whose
authorized_keys line carries from="127.0.0.1,::1",restrict,pty. The server's host key is pinned at pairing: a different
one is no connection, a Wachposten note („Schutz geändert“) and a Dienst-Wächter warning.

Rules (fixed, Sicherheits-Checkliste):
- Admin switch chat.fernzugang (Funktionen → Fernzugang zu Servern), off. Admins only (the panel password or a profile
  with the role Admin in its own browser), never the Verwalter, never guests, never a device key; no tool for the model.
- Pairing: „Koppeln (Code)“ asks for a fresh code or passkey (stufen „Schutz ändern“) and shows a one-time code
  (CODE_S, kopplung.Codes, only its hash kept); the anchor trades it once for its own device key (only the SHA-256
  kept, compared with hmac.compare_digest). At most MAX_ANKER systems.
- A session: „Shell“ asks for a fresh code or passkey (Schutz ändern) every time, then a ticket (TICKET_S, once, bound
  to the login's cookies) opens the terminal WebSocket. Starlette's http middleware does not see WebSockets, so the
  terminal checks the Origin itself (same_origin), the admin login, the ticket, the switch and the Notaus. At most
  chat.fernzugang_sitzungen sessions, idle for chat.fernzugang_leerlauf_min minutes ends one, MAX_MSG bytes per
  message on both sockets, rate limits on every door.
- The anchor's socket takes no cookies, only the device key (Bearer). A removed system's key gets nothing but the
  fixed answer „abbauen“: the anchor then removes everything it set up.
- Notaus (any stage) closes every session and anchor and lets none in until it is lifted.
- Logs: „fernzugang: <word> | <reason> | <number>“, fixed words and numbers only, profiles only as
  profiles.log_name; never keystrokes, never output, never a code, key or address. Nothing is recorded.
- The assistant never types: next to the terminal it only shows fixed command chips (CHIPS); a tap puts one into the
  line, Enter is the person's. Shell output never goes to the model.

    admin (core.auth):
    GET    /api/admin/fernzugang                         systems, counts, sessions, the anchor file (size, SHA-256), chips
    POST   /api/admin/fernzugang/koppeln {name}          one-time code (admin_code_fresh)
    POST   /api/admin/fernzugang/sitzung {geraet, cols, rows}  ticket for the terminal (admin_code_fresh)
    PUT    /api/admin/fernzugang/geraete/{gid} {erlaubt} may connect or not
    POST   /api/admin/fernzugang/geraete/{gid}/trennen   ends its sessions and its anchor connection
    DELETE /api/admin/fernzugang/geraete/{gid}           removes it; the anchor cleans itself up (admin_code)
    POST   /api/admin/fernzugang/alle-trennen            ends every session and anchor connection
    WS     /api/fernzugang/terminal?t=<ticket>           the terminal (binary: keys in, output out; text: size, state)
    anchor (no cookies):
    GET    /fernzugang/anker                             the program (public, no secrets; 404 while off)
    POST   /api/fernzugang/anker/koppeln {code, hostkey, os, version}  -> {id, key, pi_key, user, anker_sha256}
    POST   /api/fernzugang/anker/abgebaut                (Bearer key) the anchor removed itself
    WS     /api/fernzugang/anker                         (Bearer key) the pipe; text: control, binary: channel byte + data

    STATE/fernzugang.json  {"geraete": {gid: {name, os, anker, key_sha, hostkey, pi_key (sealed), pi_pub, seit,
                            zuletzt, stand ("ok" | "abbau"), abbau_seit, erlaubt, hostkey_falsch}}}
"""
import asyncio
import base64
import contextlib
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

import core
import features
import guard
import kopplung
import notaus
import profiles
import vault
from common import STATE, load_config, read_json, write_json
from core import admin_code, admin_code_fresh, auth, json_body

router = APIRouter()

FILE = os.path.join(STATE, "fernzugang.json")
PROGRAM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "anker", "spark-anker.py")
XTERM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "xterm")
# xterm.js 5.5.0 (MIT, npm @xterm/xterm, the package's sha512 checked when it was taken in), unchanged and served
# by the panel only (CSP script-src 'self'); test_fernzugang compares the files with these pinned SHA-256 sums
XTERM_VERSION = "5.5.0"
XTERM = {"xterm.js": "1f991ac3b4b283ebf96e60ae23a00a52765dd3a2e46fa6fdda9f1aab032f7495",
         "xterm.css": "ba8e6985669488981ccf40c0cefe3aba80722cb6c92de7ad628b0bd717faf2b6",
         "LICENSE": "b569f629d00f2626a8100df2a1798210535621e42164dfd426a6fe5aac7b0ccd"}

CODE_S = 600            # a pairing code works this long, once
TICKET_S = 30           # a ticket opens the terminal this long after „Shell“, once
MAX_ANKER = 10          # paired systems at most
MAX_MSG = 64 * 1024     # bytes per WebSocket message, both ways
MAX_BODY = 4096         # JSON bodies of the HTTP doors
OPEN_S = 15             # the anchor has this long to open the channel to its sshd
SSH_S = 20              # SSH handshake and login at most this long
ABBAU_TAGE = 90         # a removed system that never came back is forgotten after this many days
USER = "spark"          # the user on the remote server (its own, sudo only when the admin adds it there)
LEERLAUF = (1, 120)     # chat.fernzugang_leerlauf_min, minutes
SITZUNGEN = (1, 4)      # chat.fernzugang_sitzungen
OFFLINE = (5, 1440)     # chat.fernzugang_offline_min: the Dienst-Wächter warns after this long offline
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\- ]{0,39}")
GID = re.compile(r"g_[0-9a-f]{12}")
HOSTKEY = re.compile(r"ssh-ed25519 [A-Za-z0-9+/]{60,100}={0,2}")
WORD = re.compile(r"[A-Za-z0-9._\- ()/+]{0,40}")
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"   # no 0/O, 1/I: typed from the screen
# the assistant's chips beside the terminal: fixed commands that only read, never chosen by a model, never with Enter
CHIPS = ("uptime", "df -h", "free -h", "systemctl --failed", "journalctl -p err -n 20 --no-pager",
         "ip -br address", "ss -tlnp", "top -bn1 | head -15")
# the journal's words (fernzugang: <word> | ...), one line for every result of every action
WORDS = ("koppeln_code", "koppeln", "anker_auf", "anker_zu", "anker_abgewiesen", "ticket", "sitzung_auf", "sitzung_zu",
         "sitzung_abgewiesen", "hostkey_falsch", "abbauen", "abgebaut", "trennen", "alle_trennen", "erlaubt", "download")


def _code():
    c = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{c[:4]}-{c[4:8]}-{c[8:]}"


def _code_form(v):
    v = re.sub(r"[\s\-]", "", str(v or "")).upper()
    return f"{v[:4]}-{v[4:8]}-{v[8:]}" if re.fullmatch(f"[{ALPHABET}]{{12}}", v) else None


CODES = kopplung.Codes(_code, _code_form, CODE_S, 5, 3, kind="fernzugang")


def _sum(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


# ---------------------------------------------------------------- switch and settings
def admin_on(c=None):
    """Funktionen → Fernzugang zu Servern (admin, off); a Spark-wide door, so no per-profile check (ADMIN_ON_OK)."""
    return features.admin_on("fernzugang", c)


def _num(key, rng, c=None):
    c = features.chat_cfg() if c is None else c
    v = c.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) and rng[0] <= v <= rng[1] else None


def leerlauf_s(c=None):
    return 60 * (_num("fernzugang_leerlauf_min", LEERLAUF, c) or LEERLAUF[0])


def max_sitzungen(c=None):
    return _num("fernzugang_sitzungen", SITZUNGEN, c) or SITZUNGEN[0]


def offline_s(c=None):
    return 60 * (_num("fernzugang_offline_min", OFFLINE, c) or OFFLINE[1])


def check(c):
    """None when the settings in chat are fine, else the reason (admin.validate)."""
    for key, (lo, hi) in (("fernzugang_leerlauf_min", LEERLAUF), ("fernzugang_sitzungen", SITZUNGEN),
                          ("fernzugang_offline_min", OFFLINE)):
        if key in c and _num(key, (lo, hi), c) is None:
            return f"{key}: {lo} bis {hi}"
    return None


# ---------------------------------------------------------------- log
def log(word, why="", n=1):
    """One journal line: fixed word, fixed reason, a number. Never a name of a system, a code or an address."""
    why = re.sub(r"[^A-Za-z0-9_ äöüÄÖÜß]", "", str(why))[:40] or "-"
    print(f"fernzugang: {word} | {why} | {int(n)}", flush=True)


def _who(conn):
    """Who acts, for the journal: "admin" (panel password) or profiles.log_name of the admin profile."""
    prof = core.acting_profile(conn) if hasattr(conn, "scope") else None
    if prof:
        return profiles.log_name(profiles.by_id(prof["id"]) or {"id": prof["id"], "name": ""})
    return "admin"


def _live(text):
    try:
        import live
        live.mark("Fernzugang", text)
    except Exception:
        pass


# ---------------------------------------------------------------- stored systems
_lock = threading.Lock()


def _read(now=None):
    now = time.time() if now is None else now
    d = read_json(FILE, {})
    g = d.get("geraete") if isinstance(d.get("geraete"), dict) else {}
    out = {}
    for gid, x in g.items():
        if not GID.fullmatch(str(gid)) or not isinstance(x, dict) or not isinstance(x.get("key_sha"), str):
            continue
        if x.get("stand") == "abbau" and now - float(x.get("abbau_seit") or now) > ABBAU_TAGE * 86400:
            continue   # never came back: forgotten
        out[gid] = x
    return {"geraete": out}


def _write(d):
    write_json(FILE, d)


def _update(gid, **fields):
    """Changes fields of one stored system (in a thread: the lock is never held across an await)."""
    with _lock:
        d = _read()
        if gid in d["geraete"]:
            d["geraete"][gid].update(fields)
            _write(d)


def _key_sha(key):
    return hashlib.sha256(str(key).encode()).hexdigest()


def by_key(key):
    """(gid, entry) of the device key, compared in constant time; (None, None) when unknown."""
    if not isinstance(key, str) or not re.fullmatch(r"fz_[A-Za-z0-9_\-]{30,60}", key):
        return None, None
    h = _key_sha(key)
    hit = (None, None)
    for gid, x in _read()["geraete"].items():
        if hmac.compare_digest(h, x["key_sha"]):
            hit = (gid, x)
    return hit


def fingerprint(hostkey):
    """SHA256:… of an OpenSSH public key line, as ssh-keygen -l shows it."""
    try:
        raw = base64.b64decode(hostkey.split()[1])
    except (IndexError, ValueError):
        return ""
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


def _new_keypair():
    """A fresh ed25519 key of the Pi for one system: (private key in OpenSSH form, public line)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                           serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return priv, pub


# ---------------------------------------------------------------- what runs (memory only)
class Anker:
    def __init__(self, ws, gid):
        self.ws, self.gid, self.seit = ws, gid, time.time()
        self.kanaele = {}       # n -> Sitzung
        self.wait = {}          # n -> Future (open answer)
        self.send_lock = asyncio.Lock()

    async def send_json(self, d):
        async with self.send_lock:
            await self.ws.send_text(json.dumps(d))

    async def send_bytes(self, b):
        async with self.send_lock:
            await self.ws.send_bytes(b)


ANKER = {}       # gid -> Anker
SITZUNG = {}     # sid -> Sitzung
TICKETS = {}     # sha256(ticket) -> {"gid", "login", "until", "cols", "rows", "who"}
STATS = {"heute": "", "sitzungen": 0, "abgewiesen": 0}


def _login(conn):
    """The login this request carries (both login cookies), as a hash: a ticket only opens in the same login."""
    raw = (conn.cookies.get(core.COOKIE, "") + "|" + conn.cookies.get(profiles.COOKIE, "")).encode()
    return hashlib.sha256(raw).hexdigest()


def is_admin_browser(conn):
    """The panel password's login or an admin profile (role Admin) in its own browser; never the Verwalter, a device
    key or a guest. Works for an HTTP request and a WebSocket (the role check reads no method)."""
    if conn.headers.get(profiles.DEVICE_HEADER):
        return False
    if core.password_set() and core._admin_cookie_age(conn) is not None:
        return True
    if not core.password_set():
        return True     # a Spark without a panel password is open to its admin (core.is_main_admin)
    import coadmin
    s = coadmin.session(conn)
    return bool(s and s["role"] == "admin" and s["via"] == "b")


def same_origin(conn):
    """The WebSocket's Origin is the panel's own page. Browsers always send Origin with a WebSocket; a missing or
    foreign one is refused (the http middleware's CSRF check never sees WebSockets)."""
    site = conn.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return False
    origin = conn.headers.get("origin", "")
    if not origin or origin == "null":
        return False
    host = conn.headers.get("x-forwarded-host") or conn.headers.get("host", "")
    return bool(host) and urlsplit(origin).netloc.lower() == host.split(",")[0].strip().lower()


def counts(now=None):
    """Numbers only (Live, Zustand, the app, the Steuerzentrale): paired, online, sessions, waiting for removal."""
    g = _read(now)["geraete"]
    ok = [k for k, x in g.items() if x.get("stand") != "abbau"]
    return {"gekoppelt": len(ok), "online": sum(1 for k in ok if k in ANKER), "sitzungen": len(SITZUNG),
            "abbau": len(g) - len(ok), "hostkey": sum(1 for k in ok if g[k].get("hostkey_falsch"))}


def for_live(now=None):
    if not admin_on():
        return {"on": False}
    return {"on": True, **counts(now)}


def live_sub(d):
    return (f"{d.get('gekoppelt', 0)} gekoppelt · {d.get('online', 0)} online · {d.get('sitzungen', 0)} Sitzungen"
            + (f" · {d['abbau']} warten auf Abbau" if d.get("abbau") else "")
            + (f" · {d['hostkey']} Host-Schlüssel falsch" if d.get("hostkey") else ""))


# ---------------------------------------------------------------- Dienst-Wächter
def probes(c=None):
    """One part per paired system the admin lets connect (dienstwacht.active)."""
    if not admin_on(c):
        return {}
    return {gid: {"fernanker": gid} for gid, x in _read()["geraete"].items()
            if x.get("stand") != "abbau" and x.get("erlaubt", True)}


def anker_ok(gid, now=None):
    """Online, or offline for less than chat.fernzugang_offline_min; never with a wrong host key."""
    now = time.time() if now is None else now
    x = _read(now)["geraete"].get(gid) or {}
    if x.get("hostkey_falsch"):
        return False
    if gid in ANKER:
        return True
    return now - float(x.get("weg") or x.get("seit") or now) < offline_s()


# ---------------------------------------------------------------- Notaus and closing
def _notaus(count=False):
    """The Notaus at any stage holds the whole Fernzugang off (Spark-wide, never a profile's own Notaus)."""
    if count:
        return notaus.refuse("aussen")
    return notaus.level() >= notaus.STAGE["aussen"]


async def _close_anker(a, code=4000):
    for s in list(a.kanaele.values()):
        await s.end("getrennt")
    with contextlib.suppress(Exception):
        await a.ws.close(code)


async def close_all(why="alle"):
    """Ends every session and anchor connection (Alle trennen, Notaus). The anchors come back after their pause
    unless the Notaus is on."""
    n = len(SITZUNG) + len(ANKER)
    for s in list(SITZUNG.values()):
        await s.end(why)
    for a in list(ANKER.values()):
        await _close_anker(a)
    TICKETS.clear()
    return n


async def notaus_close():
    """notaus.after_change: any stage closes everything; new ones are refused while it is on."""
    n = await close_all("notaus")
    log("alle_trennen", "notaus", n)


# ---------------------------------------------------------------- one terminal session
class Sitzung:
    def __init__(self, gid, anker, n, browser, who, uid):
        self.id = secrets.token_hex(4)
        self.gid, self.anker, self.n, self.browser = gid, anker, n, browser
        self.who, self.uid = who, uid
        self.seit = self.zuletzt = time.time()
        self.loop = asyncio.get_running_loop()
        self.ende = asyncio.Event()
        self.grund = ""
        self.ours, self.theirs = socket.socketpair()   # paramiko speaks to theirs, the anchor's bytes go through ours
        self.ours.setblocking(False)
        self.transport = self.chan = None
        self.offen = False   # True once SSH stands; before that a closed pipe is the setup's to report
        self.pipe_zu = False
        self.tasks = []

    async def from_anker(self, data):
        with contextlib.suppress(OSError):
            await self.loop.sock_sendall(self.ours, data)

    async def _to_anker(self):
        while not self.ende.is_set():
            try:
                data = await self.loop.sock_recv(self.ours, 32 * 1024)
            except OSError:
                break
            if not data:
                break
            try:
                await self.anker.send_bytes(bytes([self.n]) + data)
            except Exception:
                break
        self.pipe_zu = True
        if self.offen:     # while SSH is still being set up, the setup reports its own reason (hostkey, ssh)
            await self.end("anker")

    def _ssh(self, pin, priv, cols, rows):
        """In a thread: SSH over the pipe, host key against the pin, login with the vault's key, a shell with a pty."""
        import paramiko
        t = paramiko.Transport(self.theirs)
        t.banner_timeout = t.handshake_timeout = t.auth_timeout = SSH_S
        t.start_client(timeout=SSH_S)
        key = t.get_remote_server_key()
        got = f"{key.get_name()} {key.get_base64()}"
        if not hmac.compare_digest(got.encode(), pin.encode()):
            self.transport = t   # end() closes it, after the browser got the reason
            return "hostkey"
        t.auth_publickey(USER, paramiko.Ed25519Key.from_private_key(io.StringIO(priv)))
        chan = t.open_session(timeout=SSH_S)
        chan.get_pty(term="xterm-256color", width=cols, height=rows)
        chan.invoke_shell()
        self.transport, self.chan = t, chan
        return ""

    def _reader(self, q):
        """In a thread: the shell's output into the queue of the event loop (never kept, never logged)."""
        while True:
            try:
                data = self.chan.recv(32 * 1024)
            except Exception:
                data = b""
            self.loop.call_soon_threadsafe(q.put_nowait, data)
            if not data:
                return

    async def _to_browser(self, q):
        while True:
            data = await q.get()
            if not data:
                break
            try:
                await self.browser.send_bytes(data)
            except Exception:
                break
        await self.end("shell")

    async def _idle(self):
        while not self.ende.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.ende.wait(), 10)
            if time.time() - self.zuletzt > leerlauf_s():
                await self._say({"typ": "zu", "grund": "leerlauf"})
                await self.end("leerlauf")

    async def _say(self, d):
        with contextlib.suppress(Exception):
            await self.browser.send_text(json.dumps(d))

    async def end(self, why):
        if self.ende.is_set():
            return
        self.ende.set()
        self.grund = why
        SITZUNG.pop(self.id, None)
        self.anker.kanaele.pop(self.n, None)
        with contextlib.suppress(Exception):
            await self.anker.send_json({"typ": "zu", "kanal": self.n})
        for s in (self.ours,):
            with contextlib.suppress(OSError):
                s.close()

        def _shut():
            for x in (self.chan, self.transport, self.theirs):
                with contextlib.suppress(Exception):
                    if x is not None:
                        x.close()
        await asyncio.to_thread(_shut)
        await self._say({"typ": "zu", "grund": why})
        with contextlib.suppress(Exception):
            await self.browser.close(1000)
        mins = int((time.time() - self.seit) // 60)
        log("sitzung_zu", why, mins)
        _live(f"Fernsitzung beendet ({why})")
        await asyncio.to_thread(_update, self.gid, zuletzt=int(time.time()))


def _free_channel(a):
    return next((n for n in range(1, 64) if n not in a.kanaele and n not in a.wait), None)


async def _refuse(ws, why, code=4403):
    STATS["abgewiesen"] += 1
    log("sitzung_abgewiesen", why)
    with contextlib.suppress(Exception):
        await ws.close(code)


@router.websocket("/api/fernzugang/terminal")
async def terminal_ws(ws: WebSocket):
    """The browser's terminal. Its own checks, in this order: switch, Origin, admin login, Notaus, ticket, room."""
    if not admin_on():
        return await _refuse(ws, "aus", 4404)
    if not same_origin(ws):
        guard.log("foreign_page_refused", path="/api/fernzugang/terminal")
        return await _refuse(ws, "fremde Seite")
    if not is_admin_browser(ws):
        return await _refuse(ws, "kein Admin")
    if _notaus(count=True):
        return await _refuse(ws, "notaus", 4503)
    raw = ws.query_params.get("t", "")
    h = hashlib.sha256(raw.encode()).hexdigest() if re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", raw) else ""
    tk = TICKETS.pop(h, None) if h else None
    if not tk or tk["until"] < time.time() or not hmac.compare_digest(tk["login"], _login(ws)):
        return await _refuse(ws, "ticket")
    if len(SITZUNG) >= max_sitzungen():
        return await _refuse(ws, "voll", 4429)
    g = _read()["geraete"].get(tk["gid"])
    a = ANKER.get(tk["gid"])
    if not g or not a or g.get("stand") == "abbau" or not g.get("erlaubt", True) or g.get("hostkey_falsch"):
        return await _refuse(ws, "offline", 4409)
    n = _free_channel(a)
    if n is None:
        return await _refuse(ws, "voll", 4429)
    await ws.accept()
    import live
    t0 = time.time()
    rec = live.begin("web", "", t=t0, uid=tk.get("uid"), why="fernzugang", request=ws)
    if rec is not None and not tk.get("uid"):
        rec.kind = "admin"     # the panel password's login (no profile)
    if rec is not None:
        rec.step("in", "Fernsitzung", t0)
    s = Sitzung(tk["gid"], a, n, ws, tk["who"], tk.get("uid"))
    fut = asyncio.get_running_loop().create_future()
    a.wait[n] = fut
    ok = ""
    try:
        await a.send_json({"typ": "auf", "kanal": n})
        ok = "offen" if await asyncio.wait_for(fut, OPEN_S) else "sshd"
    except (asyncio.TimeoutError, Exception):
        ok = "anker"
    finally:
        a.wait.pop(n, None)
    if ok != "offen":
        await s._say({"typ": "fehler", "grund": ok})
        live_end = (rec, False, ok)
        await asyncio.to_thread(live.end, *live_end)
        log("sitzung_abgewiesen", ok)
        with contextlib.suppress(Exception):
            await ws.close(4502)
        return
    a.kanaele[n] = s
    SITZUNG[s.id] = s
    s.tasks.append(asyncio.create_task(s._to_anker()))
    await s._say({"typ": "stand", "stand": "ssh"})
    try:
        why = await asyncio.wait_for(asyncio.to_thread(s._ssh, g["hostkey"], vault.open_(g.get("pi_key", "")),
                                                       tk["cols"], tk["rows"]), SSH_S + 5)
    except Exception as e:
        why = "ssh_" + type(e).__name__.lower()[:20]
    if why:
        if why == "hostkey":
            await asyncio.to_thread(hostkey_wrong, tk["gid"])
        await s._say({"typ": "fehler", "grund": "hostkey" if why == "hostkey" else "ssh"})
        if rec is not None:
            rec.step("err", why[:30], time.time())
        await asyncio.to_thread(live.end, rec, False, re.sub(r"[^a-z0-9_]", "", why)[:30])
        await s.end(why[:30])
        return
    if rec is not None:
        rec.step("prep", "SSH", t0, time.time())
    await asyncio.to_thread(live.end, rec, True)
    s.offen = True
    if s.pipe_zu:          # the anchor's pipe closed while SSH was set up
        await s.end("anker")
        return
    STATS["sitzungen"] += 1
    log("sitzung_auf", s.who, len(SITZUNG))
    _live("Fernsitzung geöffnet")
    q = asyncio.Queue()
    threading.Thread(target=s._reader, args=(q,), name="fernzugang-lesen", daemon=True).start()
    s.tasks += [asyncio.create_task(s._to_browser(q)), asyncio.create_task(s._idle())]
    await s._say({"typ": "stand", "stand": "offen", "fp": fingerprint(g["hostkey"]), "leerlauf": leerlauf_s() // 60})
    try:
        while not s.ende.is_set():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            text = msg.get("text")
            if len(data or b"") > MAX_MSG or len(text or "") > MAX_MSG:
                await s._say({"typ": "zu", "grund": "zu_gross"})
                await s.end("zu_gross")
                break
            if _notaus() or not admin_on():
                await s.end("notaus" if _notaus() else "aus")
                break
            s.zuletzt = time.time()
            if data:
                await asyncio.to_thread(s.chan.sendall, data)
            elif text:
                try:
                    m = json.loads(text)
                except ValueError:
                    continue
                if isinstance(m, dict) and m.get("typ") == "groesse":
                    c, r = _size(m.get("cols"), m.get("rows"))
                    await asyncio.to_thread(s.chan.resize_pty, c, r)
    except (WebSocketDisconnect, RuntimeError, OSError, EOFError):
        pass
    except Exception as e:
        log("sitzung_zu", "fehler " + type(e).__name__[:20])
    finally:
        await s.end(s.grund or "browser")


def _size(cols, rows):
    c = cols if isinstance(cols, int) and 20 <= cols <= 400 else 80
    r = rows if isinstance(rows, int) and 5 <= rows <= 200 else 24
    return c, r


def hostkey_wrong(gid):
    """The server answered with another host key than the one pinned at pairing: no connection, the system is marked
    until it is paired again, the change log notes it (Wachposten „Schutz geändert“), the Dienst-Wächter warns."""
    with _lock:
        d = _read()
        x = d["geraete"].get(gid)
        if x is None:
            return
        x["hostkey_falsch"] = True
        _write(d)
    log("hostkey_falsch", "keine Verbindung")
    guard.log("fernzugang_hostkey", detail="Host-Schlüssel eines Fern-Servers geändert, keine Verbindung")
    _live("Host-Schlüssel falsch, keine Verbindung")
    try:
        import dienstwacht
        dienstwacht.warn("fernzugang", "Host-Schlüssel geändert", True)
    except Exception:
        pass


# ---------------------------------------------------------------- the anchor's pipe
def _bearer(conn):
    v = conn.headers.get("authorization", "")
    return v[7:].strip() if v.lower().startswith("bearer ") else ""


@router.websocket("/api/fernzugang/anker")
async def anker_ws(ws: WebSocket):
    """The anchor's pipe. No cookie counts here, only the device key. A removed system gets only „abbauen“."""
    if not admin_on():
        log("anker_abgewiesen", "aus")
        return await ws.close(4404)
    if _notaus(count=True):
        log("anker_abgewiesen", "notaus")
        return await ws.close(4503)
    try:
        guard.check(ws, "fernzugang-anker")
        guard.limit(ws, "fernzugang_anker")
    except HTTPException:
        log("anker_abgewiesen", "gesperrt")
        return await ws.close(4429)
    gid, x = by_key(_bearer(ws))
    if not gid:
        await asyncio.to_thread(guard.failed, ws, "fernzugang-anker", "fernzugang_anker")
        log("anker_abgewiesen", "schluessel")
        return await ws.close(4401)
    if x.get("stand") == "abbau":
        await ws.accept()
        log("abbauen", "beim kontakt")
        await _abbau_handshake(ws, gid)
        return
    if not x.get("erlaubt", True):
        log("anker_abgewiesen", "nicht erlaubt")
        return await ws.close(4403)
    await ws.accept()
    a = Anker(ws, gid)
    old = ANKER.get(gid)
    ANKER[gid] = a
    if old:
        await _close_anker(old)
    log("anker_auf", "ok", len(ANKER))
    _live("Fern-Server verbunden")
    await asyncio.to_thread(_update, gid, weg=None)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data, text = msg.get("bytes"), msg.get("text")
            if len(data or b"") > MAX_MSG + 1 or len(text or "") > MAX_MSG:
                log("anker_zu", "zu gross")
                break
            if _notaus() or not admin_on():
                break
            if data:
                s = a.kanaele.get(data[0])
                if s is not None:
                    await s.from_anker(data[1:])
                continue
            try:
                m = json.loads(text or "")
            except ValueError:
                continue
            if not isinstance(m, dict):
                continue
            await _on_anker_text(a, m)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        for s in list(a.kanaele.values()):
            await s.end("anker")
        if ANKER.get(gid) is a:
            ANKER.pop(gid, None)
            await asyncio.to_thread(_update, gid, weg=int(time.time()))
        log("anker_zu", "getrennt", len(ANKER))
        _live("Fern-Server getrennt")
        with contextlib.suppress(Exception):
            await ws.close(4000)


async def _on_anker_text(a, m):
    typ, n = m.get("typ"), m.get("kanal")
    if typ in ("offen", "fehler") and isinstance(n, int) and n in a.wait and not a.wait[n].done():
        a.wait[n].set_result(typ == "offen")
    elif typ == "zu" and isinstance(n, int) and n in a.kanaele:
        await a.kanaele[n].end("server")
    elif typ == "hallo":
        os_, ver = str(m.get("os", ""))[:40], str(m.get("version", ""))[:20]
        fields = {k: v for k, v in (("os", os_), ("anker", ver)) if v and WORD.fullmatch(v)}
        if fields:
            await asyncio.to_thread(_update, a.gid, **fields)
    elif typ == "abbau_laeuft":
        log("abbauen", "laeuft")


async def _abbau_handshake(ws, gid):
    """A removed system came back: it hears nothing but „abbauen“. It removes everything and then reports with
    POST /api/fernzugang/anker/abgebaut; only then the panel forgets it."""
    try:
        await ws.send_text(json.dumps({"typ": "abbauen"}))
        msg = await asyncio.wait_for(ws.receive(), 15)
        m = json.loads(msg.get("text") or "{}") if msg.get("type") == "websocket.receive" else {}
        log("abbauen", "laeuft" if isinstance(m, dict) and m.get("typ") == "abbau_laeuft" else "keine antwort")
    except Exception:
        log("abbauen", "keine antwort", 0)
    with contextlib.suppress(Exception):
        await ws.close(4000)


def _forget(gid, why):
    with _lock:
        d = _read()
        if d["geraete"].pop(gid, None) is None:
            return
        _write(d)
    log("abgebaut", why)
    guard.log("fernzugang_removed", detail="Fern-Server hat seinen Anker abgebaut")
    _live("Fern-Server abgebaut")


# ---------------------------------------------------------------- the anchor's HTTP doors
@router.post("/api/fernzugang/anker/koppeln")
async def anker_pair(request: Request):
    """The anchor's first contact: a one-time code from the admin (typed on the server, never in a URL or an argument)
    for its own device key, the Pi's public key for authorized_keys and the SHA-256 of the program."""
    if not admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_koppeln")
    guard.check(request, "fernzugang-koppeln")
    body = await json_body(request, MAX_BODY)
    hostkey = str(body.get("hostkey") or "").strip()
    raw = body.get("code")
    peek = _code_form(raw)
    expired = bool(peek) and any(hmac.compare_digest(k, hashlib.sha256(peek.encode()).hexdigest())
                                 and time.time() - v["t"] > CODE_S for k, v in list(CODES.pending.items()))
    name = CODES.take(raw)
    if not name:
        guard.failed(request, "fernzugang-koppeln", what="fernzugang_koppeln")
        log("koppeln", "abgelaufen" if expired else "falsch", 0)
        raise HTTPException(403, "code expired" if expired else "wrong code")
    if not HOSTKEY.fullmatch(hostkey) or not fingerprint(hostkey):
        log("koppeln", "hostkey ungueltig", 0)
        raise HTTPException(400, "hostkey: ssh-ed25519 only")
    with _lock:
        d = _read()
        if sum(1 for x in d["geraete"].values() if x.get("stand") != "abbau") >= MAX_ANKER:
            log("koppeln", "voll", 0)
            raise HTTPException(409, "too many systems")
        gid, key = "g_" + secrets.token_hex(6), "fz_" + secrets.token_urlsafe(32)
        priv, pub = _new_keypair()
        sealed = vault.seal(priv)
        if not str(sealed).startswith(vault.PREFIX):   # never a private key in plain text on the disk
            log("koppeln", "tresor fehlt", 0)
            raise HTTPException(503, "vault not available")
        os_ = str(body.get("os") or "")[:40]
        ver = str(body.get("version") or "")[:20]
        d["geraete"][gid] = {"name": name, "os": os_ if WORD.fullmatch(os_) else "", "anker": ver if WORD.fullmatch(ver) else "",
                             "key_sha": _key_sha(key), "hostkey": hostkey, "pi_key": sealed, "pi_pub": pub,
                             "seit": int(time.time()), "zuletzt": 0, "stand": "ok", "erlaubt": True}
        _write(d)
    guard.succeeded(request, "fernzugang-koppeln")
    log("koppeln", "ok", 1)
    guard.log("fernzugang_paired", detail="Fern-Server gekoppelt")
    _live("Fern-Server gekoppelt")
    return {"id": gid, "key": key, "pi_key": f"{pub} spark-fernzugang-{gid}", "user": USER,
            "anker_sha256": _sum(PROGRAM)}


@router.post("/api/fernzugang/anker/abgebaut")
async def anker_removed(request: Request):
    """`spark-anker entfernen` on the server tells the panel (best effort): the system is forgotten here too."""
    if not admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_koppeln")
    gid, _ = by_key(_bearer(request))
    if not gid:
        guard.failed(request, "fernzugang-anker", what="fernzugang_anker")
        log("abgebaut", "schluessel", 0)
        raise HTTPException(403, "unknown key")
    if gid in ANKER:
        await _close_anker(ANKER[gid])
    await asyncio.to_thread(_forget, gid, "vom server")
    return {"ok": True}


def download(request: Request):
    """GET /fernzugang/anker (panel.py): the program, without any secret; 404 while the switch is off."""
    if not admin_on() or not os.path.isfile(PROGRAM):
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_laden")
    log("download", "ok", 1)
    return FileResponse(PROGRAM, media_type="text/x-python", filename="spark-anker",
                        headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- admin pages
def _browser(request: Request):
    if not is_admin_browser(request):
        raise HTTPException(403, "only an admin in the browser")


def _on(request: Request):
    if not admin_on():
        raise HTTPException(404, "Fernzugang ist aus (Funktionen → Fernzugang zu Servern)")
    _browser(request)
    if _notaus(count=True):
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")


def _spki_pin():
    """sha256//… of the panel certificate's public key, for curl --pinnedpubkey (the panel's own certificate)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from common import TLS_DIR
        with open(os.path.join(TLS_DIR, "cert.pem"), "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        der = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    except (OSError, ValueError, ImportError):
        return ""
    return "sha256//" + base64.b64encode(hashlib.sha256(der).digest()).decode()


def command(origin):
    """The one line to paste on the server, from the address the admin's browser is on (terminal.setup_base, one
    rule for both): an outside address with a certificate of an authority as it is; the panel at home with its own
    certificate pinned (curl by the public key, the anchor by the certificate's SHA-256). The code is never in it."""
    import terminal
    try:
        base = terminal.setup_base(origin, load_config("panel"))
    except HTTPException:
        return None
    if not base:
        return None
    url, fp = base
    if not fp:
        return {"befehl": f"curl -fsSL {url}/fernzugang/anker | sudo python3 - einrichten {url}", "fp": ""}
    pin = _spki_pin()
    if not pin:
        return None
    return {"befehl": f"curl -fsSLk --pinnedpubkey '{pin}' {url}/fernzugang/anker | sudo python3 - einrichten {url} --fp {fp}",
            "fp": fp}


def _second_step(request):
    """A remote shell only for an admin with a second sign-in step (an admin profile always has one; the panel
    password needs its own, Ich → Sicherheit): the fresh code or passkey before pairing and before every session is
    then really asked, never skipped."""
    import mfa
    prof = core.acting_profile(request)
    if not mfa.enabled(prof["id"] if prof else mfa.ADMIN):
        log("koppeln_code" if request.url.path.endswith("/koppeln") else "ticket", "kein zweiter schritt", 0)
        raise HTTPException(403, "Fernzugang nur mit zweitem Anmeldeschritt (Ich → Sicherheit).")


def _program():
    try:
        size = os.path.getsize(PROGRAM)
    except OSError:
        size = 0
    return {"size": size, "sha256": _sum(PROGRAM)}


@router.get("/api/admin/fernzugang", dependencies=[Depends(auth)])
def admin_get(request: Request):
    guard.limit(request, "fernzugang", admin=True)
    c = features.chat_cfg()
    out = {"on": admin_on(c), "leerlauf": leerlauf_s(c) // 60, "max": max_sitzungen(c), "max_anker": MAX_ANKER,
           "chips": list(CHIPS), "anker": _program(), "code_s": CODE_S, "counts": counts(),
           "notaus": _notaus()}
    rows = []
    now = time.time()
    for gid, x in sorted(_read(now)["geraete"].items(), key=lambda kv: str(kv[1].get("name", "")).lower()):
        a = ANKER.get(gid)
        rows.append({"id": gid, "name": x.get("name", ""), "os": x.get("os", ""), "anker": x.get("anker", ""),
                     "online": a is not None, "online_seit": int(a.seit) if a else None, "weg": x.get("weg"),
                     "zuletzt": x.get("zuletzt") or None, "seit": x.get("seit"), "stand": x.get("stand", "ok"),
                     "erlaubt": x.get("erlaubt", True), "hostkey_falsch": bool(x.get("hostkey_falsch")),
                     "fp": fingerprint(x.get("hostkey", "")),
                     "sitzungen": sum(1 for s in SITZUNG.values() if s.gid == gid)})
    out["geraete"] = rows
    out["offen"] = [{"id": s.id, "geraet": s.gid, "seit": int(s.seit)} for s in SITZUNG.values()]
    return out


@router.post("/api/admin/fernzugang/koppeln", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_pair(request: Request):
    """„Koppeln (Code)“: a one-time code for one new system (fresh code or passkey first: a new way in)."""
    _on(request)
    _second_step(request)
    guard.limit(request, "fernzugang_code", admin=True)
    body = await json_body(request, MAX_BODY)
    name = str(body.get("name") or "").strip()
    if not NAME.fullmatch(name):
        log("koppeln_code", "name ungueltig", 0)
        raise HTTPException(400, "name: letters, digits, . _ - and spaces, up to 40")
    if counts()["gekoppelt"] >= MAX_ANKER:
        log("koppeln_code", "voll", 0)
        raise HTTPException(409, "too many systems")
    cmd = command(body.get("origin"))
    if not cmd:
        log("koppeln_code", "kein https", 0)
        raise HTTPException(409, "Über diese Adresse geht es nur mit https. Den Server erreicht der Anker nur verschlüsselt.")
    code = CODES.new(name)
    log("koppeln_code", _who(request), 1)
    guard.log("fernzugang_code", detail="Kopplungs-Code für einen Fern-Server erstellt")
    return {"code": code, "gilt_s": CODE_S, "anker": _program(), "user": USER, **cmd}


@router.post("/api/admin/fernzugang/sitzung", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_session(request: Request):
    """„Shell“: after a fresh code or passkey a ticket that opens the terminal once, within TICKET_S seconds."""
    _on(request)
    _second_step(request)
    guard.limit(request, "fernzugang_sitzung", admin=True)
    body = await json_body(request, MAX_BODY)
    gid = str(body.get("geraet") or "")
    x = _read()["geraete"].get(gid) if GID.fullmatch(gid) else None
    if not x or x.get("stand") == "abbau":
        log("ticket", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    if gid not in ANKER:
        log("ticket", "offline", 0)
        raise HTTPException(409, "offline")
    if x.get("hostkey_falsch"):
        log("ticket", "hostkey", 0)
        raise HTTPException(409, "host key changed: pair again")
    if len(SITZUNG) >= max_sitzungen():
        log("ticket", "voll", 0)
        raise HTTPException(429, "too many sessions")
    cols, rows = _size(body.get("cols"), body.get("rows"))
    t = secrets.token_urlsafe(32)
    now = time.time()
    for k in [k for k, v in TICKETS.items() if v["until"] < now]:
        TICKETS.pop(k, None)
    prof = core.acting_profile(request)
    TICKETS[hashlib.sha256(t.encode()).hexdigest()] = {"gid": gid, "login": _login(request), "until": now + TICKET_S,
                                                       "cols": cols, "rows": rows, "who": _who(request),
                                                       "uid": prof["id"] if prof else None}
    log("ticket", _who(request), 1)
    return {"ticket": t, "gilt_s": TICKET_S}


@router.put("/api/admin/fernzugang/geraete/{gid}", dependencies=[Depends(auth)])
async def admin_allow(gid: str, request: Request):
    _on(request)
    guard.limit(request, "fernzugang", admin=True)
    on = (await json_body(request, 256)).get("erlaubt")
    if not isinstance(on, bool) or not GID.fullmatch(gid):
        raise HTTPException(400, "erlaubt: true or false")
    with _lock:
        d = _read()
        if gid not in d["geraete"]:
            raise HTTPException(404, "no such system")
        d["geraete"][gid]["erlaubt"] = on
        _write(d)
    if not on and gid in ANKER:
        await _close_anker(ANKER[gid])
    log("erlaubt", "an" if on else "aus")
    guard.log("fernzugang_allow", detail="Fern-Server darf sich verbinden" if on else "Fern-Server gesperrt")
    return {"erlaubt": on}


@router.post("/api/admin/fernzugang/geraete/{gid}/trennen", dependencies=[Depends(auth)])
async def admin_cut(gid: str, request: Request):
    """Ends the system's sessions and its anchor connection now (it comes back after its pause; to keep it out, switch
    „Darf sich verbinden“ off)."""
    _browser(request)
    guard.limit(request, "fernzugang", admin=True)
    n = 0
    for s in [s for s in SITZUNG.values() if s.gid == gid]:
        await s.end("getrennt")
        n += 1
    if gid in ANKER:
        await _close_anker(ANKER[gid])
        n += 1
    log("trennen", _who(request), n)
    return {"n": n}


@router.post("/api/admin/fernzugang/alle-trennen", dependencies=[Depends(auth)])
async def admin_cut_all(request: Request):
    _browser(request)
    guard.limit(request, "fernzugang", admin=True)
    n = await close_all("alle")
    log("alle_trennen", _who(request), n)
    _live("Alle Fernsitzungen getrennt")
    return {"n": n}


@router.delete("/api/admin/fernzugang/geraete/{gid}", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_remove(gid: str, request: Request):
    """„Entfernen“: the key stops at once, the Pi's key and the pinned host key are deleted here; the anchor hears
    „abbauen“ now or at its next contact and removes everything it set up on the server."""
    _browser(request)
    guard.limit(request, "fernzugang", admin=True)
    with _lock:
        d = _read()
        x = d["geraete"].get(gid) if GID.fullmatch(gid) else None
        if x is None:
            raise HTTPException(404, "no such system")
        for k in ("pi_key", "pi_pub", "hostkey"):
            x.pop(k, None)
        x.update(stand="abbau", abbau_seit=int(time.time()), erlaubt=False)
        _write(d)
    guard.log("fernzugang_revoked", detail="Fern-Server entfernt")
    a = ANKER.get(gid)
    if a is None:
        log("abbauen", "offline")
        return {"stand": "abbau"}
    for s in list(a.kanaele.values()):
        await s.end("entfernt")
    try:
        await a.send_json({"typ": "abbauen"})
        log("abbauen", "ok")
    except Exception:
        log("abbauen", "nicht erreicht")
    return {"stand": "abbau"}


def xterm_file(name):
    """(path, media type) for GET /static/xterm/<name> (panel.py): only the pinned files of xterm.js and its license."""
    if name not in XTERM:
        raise HTTPException(404, "not found")
    return os.path.join(XTERM_DIR, name), {"xterm.js": "text/javascript", "xterm.css": "text/css",
                                           "LICENSE": "text/plain"}[name]
