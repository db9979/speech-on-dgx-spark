"""Fernzugang, Webdienste (Dominik 2026-10-30 „1a, 2a“): the web pages of a paired system (Grafana, a router page,
Home Assistant over there …) in the admin's browser, through the same anchor as its shell, never opened to the
internet over there.

    browser ──https──► the Tunnel-Tür (this module, port TOR_PORT, own origin) ──WSS of the anchor, channel
    „ziel: web“──► spark-anker ──TCP──► 127.0.0.1:<port> over there (or, with „Netz dahinter“, a private address)

The tunnelled pages never come from the panel's own origin: the door listens on its own port (TOR_PORT) with the
panel's certificate; from the internet under its own name (chat.fernweb_adresse, e.g. fernwartung.example.org,
a rule of the reverse proxy to <Pi>:TOR_PORT with the WebSocket headers), at home directly as <Pi>:TOR_PORT.
Without a name only at home; the page says how to add the rule.

Rules (fixed, Sicherheits-Checkliste):
- Admin switch chat.fernweb (Funktionen → Fernzugang zu Servern → Webdienste, off), under chat.fernzugang. Admins in
  their own browser only, on the unlocked page (fernzugang._frei) with a second sign-in step; never a guest, never a
  profile part, never a tool of the model: nothing of it reaches a model.
- Targets (ziel_ok, and the anchor's own web_ziel, both always): only an IP address (never a name: nothing is
  resolved), loopback always; the private ranges only with the system's admin switch „Netz dahinter“ (web_netz, off),
  and never an address in one of this Pi's own networks; never link-local, multicast, unspecified, reserved, the
  metadata address or the panel's own address. The anchor checks the same itself (1.6.0, spark-anker web_ziel).
- „Öffnen“ makes a one-time ticket (TICKET_S, bound to the login and its unlock); the door takes it once, sets its
  own cookie (COOKIE: host only, HttpOnly, Secure, SameSite=Strict) for that one tunnel and forgets the ticket. Every
  request after that needs the cookie, the unlock of the login that opened it, the switch and no Notaus.
- Requests over there carry none of the panel's cookies and no Authorization: only the service's own cookies, which the
  door keeps apart per service (renamed with the service's mark, Domain dropped, always Secure). Host and Origin say
  the service's own address; a Location to it becomes a path. Answers may be framed only by the panel's own origin
  (Content-Security-Policy frame-ancestors; X-Frame-Options, HSTS, Alt-Svc and Clear-Site-Data are dropped).
- https over there with its own certificate: its SHA-256 is shown and pinned on „Vertrauen“ (fp), checked on every
  connection; a changed one ends the connection.
- MAX_TUNNEL tunnels at most, one per browser (a new one in the same browser ends the one before); MAX_KANAELE
  connections per tunnel at the same time (more wait), REQ_MIN requests a minute, a request body at most MAX_BODY_MB;
  flow control per channel (spark-anker WEB_FENSTER) so a slow browser or service never fills the memory. The idle end
  after LEERLAUF_S; „Schließen“, Sperren, Abmelden, the switch off, „Alle trennen“ and the Notaus end every tunnel.
- Logs „fernzugang: web_<word> | <reason> | <number>“: fixed words and port numbers, never an address, a path, a name
  or content. Live: tunnels, systems and minutes (names only with logs.live_names).

    admin in the browser (core.auth + fernzugang.is_admin_browser, the unlocked page):
    GET    /api/admin/fernzugang/web/{gid}                   services, „Netz dahinter“, the last „Gefunden“, tunnels
    POST   /api/admin/fernzugang/web/{gid}/dienste           {name, schema, host, port, pfad} a saved service
    DELETE /api/admin/fernzugang/web/{gid}/dienste/{did}
    POST   /api/admin/fernzugang/web/{gid}/netz              {an} „Netz dahinter“ (admin_code_fresh, stufen: Schutz)
    POST   /api/admin/fernzugang/web/{gid}/suchen            the anchor's listening ports („Gefunden“)
    POST   /api/admin/fernzugang/web/{gid}/dienste/{did}/zertifikat        -> {fp} of the certificate over there
    POST   /api/admin/fernzugang/web/{gid}/dienste/{did}/vertrauen {fp}    pins it
    POST   /api/admin/fernzugang/web/oeffnen                 {geraet, dienst} -> {url, tunnel}
    GET    /api/admin/fernzugang/web/tunnel                  this login's tunnels (the strip: rate, idle)
    DELETE /api/admin/fernzugang/web/tunnel/{tid}            „Schließen“
    the door (port TOR_PORT, its own origin): GET /__spark/ticket?t=&weiter=, then the service itself
"""
import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import ssl
import time
from urllib.parse import parse_qs, urlsplit

import h11
from fastapi import APIRouter, Depends, HTTPException, Request

import core
import features
import fernzugang
import guard
from core import admin_code_fresh, auth, json_body

router = APIRouter()

TOR_PORT = 31090          # the door's own port (an own origin; the reverse proxy's rule points here)
ANKER_MIN = (1, 6, 0)     # spark-anker knows „ziel: web“ and „ports“ from this version on
ERSTER, LETZTER = 64, 250  # the channel numbers of the Webdienste (spark-anker WEB_ERSTER, WEB_MAX)
FENSTER = 256 * 1024      # bytes per channel and direction on the way (spark-anker WEB_FENSTER)
MEHR = 64 * 1024          # „mehr“ to the anchor after this many bytes taken
STUECK = 32 * 1024        # bytes per message to the anchor
MAX_TUNNEL = 4            # tunnels at most, of all admins
MAX_KANAELE = 8           # connections per tunnel at the same time; more wait for a free one (WARTEN_S)
WARTEN_S = 30
MAX_DIENSTE = 20          # saved services per system
LEERLAUF_S = 15 * 60      # a tunnel nobody used this long ends
TICKET_S = 30
REQ_MIN = 1200            # requests per tunnel and minute at most
MAX_BODY_MB = 512         # one request body at most
MAX_KOPF = 64 * 1024      # the head of a request or an answer at most
OPEN_S = 10               # the anchor opens the channel within this long
SUCHEN_S = 20             # the anchor answers „ports“ within this long
WACHE_S = 5               # the door's watch: start or stop with the switch, idle ends
RATE_S = 5                # the strip's rate (KB/s) over this long; below fernbild.LANGSAM it says the line is slow
COOKIE = "__Host-spark-tunnel"
TICKET_PFAD = "/__spark/ticket"
NAME = re.compile(r"[^\x00-\x1f\x7f<>\"'`&]{1,40}")
PFAD = re.compile(r"/[\x21-\x7e]{0,511}")
FP = re.compile(r"[0-9a-f]{64}")
DID = re.compile(r"w_[0-9a-f]{8}")
TID = re.compile(r"t_[0-9a-f]{12}")
SCHEMA = ("http", "https")
PRIVAT = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))
METADATA = ipaddress.ip_address("169.254.169.254")
WEG_REIN = {b"authorization", b"proxy-authorization", b"cookie", b"host", b"origin", b"referer", b"forwarded",
            b"x-real-ip", b"connection", b"keep-alive", b"proxy-connection", b"te", b"trailer", b"upgrade",
            b"expect", b"http2-settings", b"transfer-encoding"}
WEG_RAUS = {b"x-frame-options", b"strict-transport-security", b"alt-svc", b"clear-site-data", b"connection",
            b"keep-alive", b"proxy-connection", b"transfer-encoding", b"trailer", b"upgrade", b"set-cookie",
            b"location", b"content-security-policy", b"public-key-pins"}

TUNNEL = {}      # tid -> Tunnel (memory only)
TICKETS = {}     # sha256(ticket) -> {"tid", "bis"}
GEFUNDEN = {}    # gid -> {"t", "liste"} the last „Gefunden“ (memory only: ports and program names)
_WARTEN = {}     # gid -> Future of the anchor's „ports“
_TOR = {"server": None, "loop": None, "fehler": ""}


def log(word, why="", n=1):
    fernzugang.log("web_" + word, why, n)


def admin_on(c=None):
    """Funktionen → Fernzugang zu Servern → Webdienste (admin, off); a Spark-wide door under the Fernzugang."""
    return features.admin_on("fernweb", c) and fernzugang.admin_on(c)


def adresse(c=None):
    """chat.fernweb_adresse: the door's own name from the internet ("" = only at home), a plain host name."""
    c = features.chat_cfg() if c is None else c
    v = str(c.get("fernweb_adresse") or "").strip().lower()
    return v if re.fullmatch(r"(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", v) else ""


def check(c):
    """None when chat.fernweb_adresse is fine (empty or a host name), else the reason (admin.validate)."""
    v = str(c.get("fernweb_adresse") or "").strip()
    if v and not adresse({"fernweb_adresse": v}):
        return "fernweb_adresse: ein Name wie fernwartung.example.org (ohne https:// und ohne Port)"
    return None


def anchor_ok(version):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    return bool(m) and tuple(int(x) for x in m.groups()) >= ANKER_MIN


# ---------------------------------------------------------------- where a tunnel may go
_NETZE = {"t": 0.0, "netze": ()}


def eigene_netze():
    """This Pi's own networks (the routes of its interfaces, IPv4 and IPv6), cached for a minute: never a target over
    there, even with „Netz dahinter“ (a system's network that looks like the own one would reach this home)."""
    if time.time() - _NETZE["t"] < 60:
        return _NETZE["netze"]
    out = []
    with contextlib.suppress(OSError, ValueError):
        with open("/proc/net/route") as f:
            for line in f.read().splitlines()[1:]:
                p = line.split()
                if len(p) >= 8 and p[7] != "00000000":
                    dest = ipaddress.IPv4Address(bytes.fromhex(p[1])[::-1])
                    mask = ipaddress.IPv4Address(bytes.fromhex(p[7])[::-1])
                    out.append(ipaddress.ip_network(f"{dest}/{mask}", strict=False))
    with contextlib.suppress(OSError, ValueError):
        with open("/proc/net/ipv6_route") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and int(p[1], 16) > 0:
                    net = ipaddress.ip_network(f"{ipaddress.IPv6Address(bytes.fromhex(p[0]))}/{int(p[1], 16)}", strict=False)
                    if not net.is_link_local and not net.is_multicast and not net.is_loopback:
                        out.append(net)
    _NETZE.update(t=time.time(), netze=tuple(out))
    return _NETZE["netze"]


def ziel_ok(host, port, netz=False, netze=None):
    """(host, port) when the panel lets a tunnel go there (the same rules as spark-anker web_ziel, and never into one
    of this Pi's own networks), else None. Only an IP address: a name is never resolved."""
    if not isinstance(host, str) or len(host) > 45 or not isinstance(port, int) or isinstance(port, bool) \
            or not 1 <= port <= 65535:
        return None
    try:
        ip = ipaddress.ip_address(host[1:-1] if host.startswith("[") and host.endswith("]") else host)
    except ValueError:
        return None
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if ip == METADATA or ip.is_link_local or ip.is_multicast or ip.is_unspecified or (ip.is_reserved and not ip.is_loopback):
        return None
    if ip.is_loopback:
        return str(ip), port
    if netz is not True or not any(ip in n for n in PRIVAT if n.version == ip.version):
        return None
    if any(ip in n for n in (eigene_netze() if netze is None else netze) if n.version == ip.version):
        return None
    return str(ip), port


# ---------------------------------------------------------------- the saved services of a system
def _dienste(x):
    out = []
    for d in (x.get("web") or [])[:MAX_DIENSTE]:
        if isinstance(d, dict) and DID.fullmatch(str(d.get("id") or "")):
            out.append({k: d.get(k) for k in ("id", "name", "schema", "host", "port", "pfad", "fp")})
    return out


def _dienst(x, did):
    return next((d for d in _dienste(x) if d["id"] == did), None)


def _system(gid):
    x = fernzugang._read()["geraete"].get(gid) if fernzugang.GID.fullmatch(str(gid or "")) else None
    if not x or x.get("stand") == "abbau":
        log("abgewiesen", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    return x


# ---------------------------------------------------------------- one channel through the anchor
class Kanal:
    """A channel „ziel: web“ in the anchor's pipe (registered in fernzugang.Anker.kanaele like a session): bytes in
    order both ways, flow control with the anchor (FENSTER, „mehr“)."""

    def __init__(self, anker, n, tunnel):
        self.anker, self.n, self.tunnel = anker, n, tunnel
        self.art = "web"
        self.rein = bytearray()          # from the anchor, not taken yet
        self.da = asyncio.Event()
        self.frei = asyncio.Event()
        self.frei.set()
        self.unterwegs = 0               # sent to the anchor and not yet taken there
        self.genommen = 0                # taken here since the last „mehr“
        self.zu = False
        self.grund = ""

    async def from_anker(self, data):
        """Called by fernzugang.anker_ws for every message of this channel: only kept, never awaited on (the pipe
        carries the other channels too); more than the window at once is a broken anchor."""
        self.rein += data
        if len(self.rein) > 2 * FENSTER:
            await self.end("zu_viel")
        self.da.set()

    def mehr(self, k):
        if isinstance(k, int) and not isinstance(k, bool) and k > 0:
            self.unterwegs = max(0, self.unterwegs - k)
            if self.unterwegs < FENSTER:
                self.frei.set()

    async def read(self):
        """The next bytes (b"" when the channel is closed)."""
        while not self.rein and not self.zu:
            self.da.clear()
            await self.da.wait()
        data = bytes(self.rein)
        self.rein.clear()
        if data:
            self.genommen += len(data)
            if self.genommen >= MEHR or not self.zu:
                k, self.genommen = self.genommen, 0
                with contextlib.suppress(Exception):
                    await self.anker.send_json({"typ": "mehr", "kanal": self.n, "n": k})
        return data

    async def write(self, data):
        for i in range(0, len(data), STUECK):
            part = data[i:i + STUECK]
            while self.unterwegs >= FENSTER and not self.zu:
                self.frei.clear()
                await self.frei.wait()
            if self.zu:
                raise ConnectionError("zu")
            self.unterwegs += len(part)
            if self.unterwegs >= FENSTER:
                self.frei.clear()
            await self.anker.send_bytes(bytes([self.n]) + part)
            if self.tunnel is not None:
                self.tunnel.raus += len(part)

    async def end(self, why):
        if self.zu:
            return
        self.zu, self.grund = True, why
        self.da.set()
        self.frei.set()
        if self.anker.kanaele.get(self.n) is self:
            self.anker.kanaele.pop(self.n, None)
            with contextlib.suppress(Exception):
                await self.anker.send_json({"typ": "zu", "kanal": self.n})
        if self.tunnel is not None:
            self.tunnel.kanaele.discard(self)


class TlsKanal:
    """TLS to a service with its own certificate, over a Kanal (memory BIO): TLS 1.2 or newer, the certificate
    checked against its pinned SHA-256 (fp) instead of authorities (a service on 127.0.0.1 has none)."""

    def __init__(self, kanal):
        self.k = kanal
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE       # instead: the pinned SHA-256 below (fingerprint)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_alpn_protocols(["http/1.1"])
        self.inc, self.out = ssl.MemoryBIO(), ssl.MemoryBIO()
        self.obj = ctx.wrap_bio(self.inc, self.out, server_hostname=None)

    async def _flush(self):
        data = self.out.read()
        if data:
            await self.k.write(data)

    async def _fill(self):
        data = await self.k.read()
        if not data:
            self.inc.write_eof()
            return False
        self.inc.write(data)
        return True

    async def handshake(self):
        """The certificate's SHA-256 (hex) once TLS stands."""
        while True:
            try:
                self.obj.do_handshake()
                break
            except ssl.SSLWantReadError:
                await self._flush()
                if not await self._fill():
                    raise ConnectionError("tls")
        await self._flush()
        return hashlib.sha256(self.obj.getpeercert(binary_form=True) or b"").hexdigest()

    async def read(self):
        while True:
            try:
                return self.obj.read(65536)
            except ssl.SSLWantReadError:
                await self._flush()
                if not await self._fill():
                    return b""
            except (ssl.SSLZeroReturnError, ssl.SSLEOFError):
                return b""

    async def write(self, data):
        self.obj.write(data)
        await self._flush()

    async def end(self, why):
        with contextlib.suppress(ssl.SSLError):
            self.obj.unwrap()
        with contextlib.suppress(Exception):
            await self._flush()
        await self.k.end(why)


def _frei_n(a):
    return next((n for n in range(ERSTER, LETZTER + 1) if n not in a.kanaele and n not in a.wait), None)


async def kanal_auf(gid, host, port, netz, tunnel):
    """A Kanal to host:port over there through the anchor of gid (for the Tunnel, or None for the certificate's
    look), or raises ConnectionError(<fixed word>)."""
    a = fernzugang.ANKER.get(gid)
    if a is None:
        raise ConnectionError("offline")
    if ziel_ok(host, port, netz) is None:
        raise ConnectionError("ziel")
    n = _frei_n(a)
    if n is None:
        raise ConnectionError("voll")
    k = Kanal(a, n, tunnel)
    fut = asyncio.get_running_loop().create_future()
    a.wait[n] = fut
    a.kanaele[n] = k          # before „auf“: the service's first bytes may come right behind „offen“
    try:
        await a.send_json({"typ": "auf", "kanal": n, "ziel": "web", "host": host, "port": port, "netz": netz is True})
        ok = await asyncio.wait_for(fut, OPEN_S)
    except (asyncio.TimeoutError, Exception):
        ok = None
    finally:
        a.wait.pop(n, None)
    if not ok:
        a.kanaele.pop(n, None)
        raise ConnectionError("anker" if ok is None else "dienst")
    if tunnel is not None:
        tunnel.kanaele.add(k)
    return k


# ---------------------------------------------------------------- tunnels (memory only)
class Tunnel:
    def __init__(self, gid, dienst, netz, request):
        self.id = "t_" + secrets.token_hex(6)
        self.gid, self.dienst, self.netz = gid, dict(dienst), netz is True
        self.tor = fernzugang._tor(request)          # the unlock it lives on
        self.login = fernzugang._login(request)
        self.who = fernzugang._who(request)
        self.admin_name = fernzugang._admin_name((core.acting_profile(request) or {}).get("id"))
        self.panel = (request.headers.get("origin") or "").strip()   # the only page that may frame it
        self.cookie = secrets.token_urlsafe(32)
        self.seit = self.zuletzt = time.time()
        self.kanaele = set()
        self.verbindungen = set()
        self.plaetze = asyncio.Semaphore(MAX_KANAELE)
        self.anfragen = []                          # times of the requests in the last minute (REQ_MIN)
        self.rein = self.raus = 0                   # bytes to the browser / to the service
        self.mark, self.mark_bytes, self.kb_s = time.time(), 0, None
        self.ende = False
        self.grund = ""
        self.loop = asyncio.get_running_loop()
        mark = hashlib.sha256(dienst["id"].encode()).hexdigest()[:8]
        self.marke = f"sw{mark}_"                   # the service's own cookies carry this mark in the browser

    @property
    def ziel(self):
        return self.dienst["host"], int(self.dienst["port"])

    def origin_dort(self):
        """The service's own origin (its Host and Origin header say this)."""
        host, port = self.ziel
        h = f"[{host}]" if ":" in host else host
        default = 443 if self.dienst["schema"] == "https" else 80
        return f"{self.dienst['schema']}://{h}" + ("" if port == default else f":{port}")

    def lebt(self, now=None):
        """Still allowed: the switch, no Notaus, the unlock of the login that opened it, not idle too long."""
        now = time.time() if now is None else now
        if self.ende:
            return ""
        if fernzugang._notaus():
            return "notaus"
        if not admin_on():
            return "aus"
        e = fernzugang.ENTSPERRT.get(self.tor)
        if not e or e["bis"] <= now:
            return "gesperrt"
        if now - self.zuletzt > LEERLAUF_S:
            return "leerlauf"
        return "ok"

    def rate(self):
        now = time.time()
        if now - self.mark >= RATE_S:
            got = self.rein - self.mark_bytes
            self.kb_s = int(got / 1024 / (now - self.mark)) if got > 64 * 1024 else None   # only while it is busy
            self.mark, self.mark_bytes = now, self.rein
        return self.kb_s

    async def end(self, why):
        if self.ende:
            return
        self.ende, self.grund = True, why
        TUNNEL.pop(self.id, None)
        for k in list(self.kanaele):
            await k.end(why)
        for w in list(self.verbindungen):
            with contextlib.suppress(Exception):
                w.close()
        for h in [h for h, v in TICKETS.items() if v["tid"] == self.id]:
            TICKETS.pop(h, None)
        log("zu", why, int((time.time() - self.seit) // 60))
        fernzugang._live(f"Webdienst geschlossen ({why})")


async def close_all(why="alle"):
    """Every tunnel ends (Notaus, Alle trennen, the switch off)."""
    n = len(TUNNEL)
    for t in list(TUNNEL.values()):
        await t.end(why)
    TICKETS.clear()
    return n


def _ende(pick, why):
    """Ends the tunnels pick(t) chooses, also from a thread (logout and removing run in one)."""
    for t in list(TUNNEL.values()):
        if not pick(t):
            continue
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        loop = _TOR.get("loop") or t.loop
        if running is loop:
            running.create_task(t.end(why))
        else:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(t.end(why), loop)


def ende_tor(tor, why):
    """The tunnels living on this unlock (None: on every one) end at once (Sperren, Abmelden, the Notaus)."""
    _ende(lambda t: tor is None or hmac.compare_digest(t.tor, tor), why)


def ende_gid(gid, why):
    """The tunnels of one system end (removed, its anchor gone for good)."""
    _ende(lambda t: t.gid == gid, why)


def for_live(now=None):
    """Live: tunnels, of how many systems and their minutes; system names only with logs.live_names."""
    now = time.time() if now is None else now
    if not admin_on():
        return {"tunnel": 0}
    named = fernzugang._live_names()
    g = fernzugang._read(now)["geraete"]
    order = sorted((k for k in g if g[k].get("stand") != "abbau"), key=lambda k: str(g[k].get("name", "")).lower())
    nr = {k: i for i, k in enumerate(order, 1)}
    return {"tunnel": len(TUNNEL), "systeme": len({t.gid for t in TUNNEL.values()}),
            "offen": [{"system": str(g.get(t.gid, {}).get("name", "")) if named else f"System {nr.get(t.gid, 0)}",
                       "min": int((now - t.seit) // 60)} for t in sorted(TUNNEL.values(), key=lambda t: t.seit)]}


def live_sub(d):
    if not d.get("tunnel"):
        return ""
    return (f" · {d['tunnel']} Webdienste offen ({d['systeme']} Systeme)"
            + "".join(f" · Webdienst {x['system']}, {x['min']} min" for x in d.get("offen") or ()))


# ---------------------------------------------------------------- the anchor's „ports“
async def on_ports(gid, m):
    """The anchor's answer to „ports“: ports, program names (letters only) and the kind, nothing else."""
    liste = []
    for x in (m.get("liste") or [])[:64] if isinstance(m.get("liste"), list) else []:
        if not isinstance(x, dict):
            continue
        p = x.get("port")
        if not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= 65535:
            continue
        prog = re.sub(r"[^A-Za-z0-9._\- ()/+]", "", str(x.get("prog") or ""))[:40]
        liste.append({"port": p, "prog": prog, "art": x.get("art") if x.get("art") in ("http", "https") else "tcp"})
    GEFUNDEN[gid] = {"t": int(time.time()), "liste": liste}
    fut = _WARTEN.pop(gid, None)
    if fut is not None and not fut.done():
        fut.set_result(liste)


# ---------------------------------------------------------------- admin doors
def _on(request):
    if not admin_on():
        raise HTTPException(404, "Webdienste sind aus (Funktionen → Fernzugang zu Servern → Webdienste)")
    fernzugang._browser(request)
    if fernzugang._notaus(count=True):
        log("abgewiesen", "notaus", 0)
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")
    fernzugang._frei(request)
    guard.limit(request, "fernzugang_web", admin=True)


def tor_basis(request, c=None):
    """The door's address for this browser: from the internet its own name (chat.fernweb_adresse), at home the
    panel's host on TOR_PORT; "" when it cannot be reached from where the browser is."""
    if fernzugang._herkunft(request) == "internet":
        name = adresse(c)
        return f"https://{name}" if name else ""
    host = (request.headers.get("host") or "").strip()
    if host.startswith("["):
        host = host[:host.find("]") + 1]
    else:
        host = host.rsplit(":", 1)[0]
    if not host or not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}|\[[0-9A-Fa-f:.]{2,45}\]", host):
        return ""
    return f"https://{host}:{TOR_PORT}"


def _tunnel_row(t, now):
    return {"id": t.id, "geraet": t.gid, "dienst": t.dienst["id"], "seit": int(t.seit),
            "leerlauf_s": max(0, int(LEERLAUF_S - (now - t.zuletzt))), "kb_s": t.rate(), "kanaele": len(t.kanaele)}


@router.get("/api/admin/fernzugang/web/tunnel", dependencies=[Depends(auth)])
def admin_tunnels(request: Request):
    _on(request)
    login, now = fernzugang._login(request), time.time()
    import fernbild
    return {"tunnel": [_tunnel_row(t, now) for t in TUNNEL.values() if hmac.compare_digest(t.login, login)],
            "langsam": fernbild.LANGSAM}


@router.get("/api/admin/fernzugang/web/{gid}", dependencies=[Depends(auth)])
def admin_get(gid: str, request: Request):
    _on(request)
    x = _system(gid)
    c = features.chat_cfg()
    now = time.time()
    login = fernzugang._login(request)
    return {"dienste": [{k: v for k, v in d.items()} for d in _dienste(x)], "netz": x.get("web_netz") is True,
            "gefunden": GEFUNDEN.get(gid), "anker_ok": anchor_ok(x.get("anker")), "online": gid in fernzugang.ANKER,
            "tor": tor_basis(request, c), "adresse": adresse(c), "herkunft": fernzugang._herkunft(request),
            "port": TOR_PORT, "max_dienste": MAX_DIENSTE, "max_tunnel": MAX_TUNNEL, "tor_laeuft": _TOR["server"] is not None,
            "tunnel": [_tunnel_row(t, now) for t in TUNNEL.values() if t.gid == gid and hmac.compare_digest(t.login, login)]}


def _form(body, netz):
    name = str(body.get("name") or "").strip()
    schema = body.get("schema") if body.get("schema") in SCHEMA else None
    host = str(body.get("host") or "127.0.0.1").strip()
    port = body.get("port")
    pfad = str(body.get("pfad") or "/").strip() or "/"
    if not NAME.fullmatch(name):
        raise HTTPException(400, "name: 1 bis 40 Zeichen")
    if schema is None:
        raise HTTPException(400, "schema: http oder https")
    if not PFAD.fullmatch(pfad) or pfad.startswith("//"):
        raise HTTPException(400, "pfad: beginnt mit /")
    ok = ziel_ok(host, port, netz)
    if ok is None:
        log("dienst", "ziel", 0)
        raise HTTPException(400, "Ziel nicht erlaubt: 127.0.0.1 oder ::1; private Adressen nur mit „Netz dahinter“ "
                                 "und nie aus den eigenen Netzen des Spark.")
    return {"name": name, "schema": schema, "host": ok[0], "port": ok[1], "pfad": pfad}


@router.post("/api/admin/fernzugang/web/{gid}/dienste", dependencies=[Depends(auth)])
async def admin_add(gid: str, request: Request):
    _on(request)
    x = _system(gid)
    body = await json_body(request, fernzugang.MAX_BODY)
    d = _form(body, x.get("web_netz") is True)
    dienste = _dienste(x)
    if len(dienste) >= MAX_DIENSTE:
        log("dienst", "voll", 0)
        raise HTTPException(409, f"höchstens {MAX_DIENSTE} Webdienste je System")
    d["id"] = "w_" + secrets.token_hex(4)
    d["fp"] = ""
    dienste.append(d)
    await asyncio.to_thread(fernzugang._update, gid, web=dienste)
    log("dienst", "neu", d["port"])
    return {"ok": True, "dienst": d}


@router.delete("/api/admin/fernzugang/web/{gid}/dienste/{did}", dependencies=[Depends(auth)])
async def admin_remove(gid: str, did: str, request: Request):
    _on(request)
    x = _system(gid)
    dienste = _dienste(x)
    if not any(d["id"] == did for d in dienste):
        log("dienst", "unbekannt", 0)
        raise HTTPException(404, "no such service")
    for t in [t for t in TUNNEL.values() if t.dienst["id"] == did]:
        await t.end("geloescht")
    await asyncio.to_thread(fernzugang._update, gid, web=[d for d in dienste if d["id"] != did])
    log("dienst", "geloescht", 1)
    return {"ok": True}


@router.post("/api/admin/fernzugang/web/{gid}/netz", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_netz(gid: str, request: Request):
    """„Netz dahinter“ for this system (off): tunnels may then also reach private addresses over there."""
    _on(request)
    fernzugang._second_step(request)
    x = _system(gid)
    body = await json_body(request, fernzugang.MAX_BODY)
    an = body.get("an") is True
    dienste = _dienste(x)
    if not an:   # off: the services behind it go, their tunnels end
        for t in [t for t in TUNNEL.values() if t.gid == gid and t.netz]:
            await t.end("netz_aus")
        dienste = [d for d in dienste if ziel_ok(d.get("host"), d.get("port"), False)]
    await asyncio.to_thread(fernzugang._update, gid, web_netz=an, web=dienste)
    log("netz", "an" if an else "aus", 1 if an else 0)
    guard.log("fernzugang_web_netz", detail="Netz dahinter " + ("an" if an else "aus"))
    return {"ok": True, "netz": an}


@router.post("/api/admin/fernzugang/web/{gid}/suchen", dependencies=[Depends(auth)])
async def admin_search(gid: str, request: Request):
    """„Gefunden“: the anchor lists its listening ports (ports and program names only)."""
    _on(request)
    x = _system(gid)
    a = fernzugang.ANKER.get(gid)
    if a is None:
        log("suchen", "offline", 0)
        raise HTTPException(409, "offline")
    if not anchor_ok(x.get("anker")):
        log("suchen", "anker alt", 0)
        raise HTTPException(409, "anker_alt")
    fut = _WARTEN.get(gid)
    if fut is None or fut.done():
        fut = _WARTEN[gid] = asyncio.get_running_loop().create_future()
        await a.send_json({"typ": "ports"})
    try:
        liste = await asyncio.wait_for(asyncio.shield(fut), SUCHEN_S)
    except asyncio.TimeoutError:
        _WARTEN.pop(gid, None)
        log("suchen", "keine antwort", 0)
        raise HTTPException(504, "Der Anker hat nicht geantwortet.")
    log("suchen", "ok", len(liste))
    return GEFUNDEN.get(gid) or {"t": int(time.time()), "liste": liste}


async def _zertifikat(gid, x, d):
    """The SHA-256 of the service's certificate over there (a short TLS handshake through the anchor)."""
    k = await kanal_auf(gid, d["host"], int(d["port"]), x.get("web_netz") is True, None)
    tls = TlsKanal(k)
    try:
        return await asyncio.wait_for(tls.handshake(), OPEN_S)
    finally:
        await tls.end("zertifikat")


@router.post("/api/admin/fernzugang/web/{gid}/dienste/{did}/zertifikat", dependencies=[Depends(auth)])
async def admin_cert(gid: str, did: str, request: Request):
    _on(request)
    x = _system(gid)
    d = _dienst(x, did)
    if not d or d["schema"] != "https":
        raise HTTPException(404, "no such https service")
    if not anchor_ok(x.get("anker")):
        raise HTTPException(409, "anker_alt")
    try:
        fp = await _zertifikat(gid, x, d)
    except (ConnectionError, OSError, ssl.SSLError, asyncio.TimeoutError) as e:
        why = str(e) if isinstance(e, ConnectionError) and str(e) else "tls"
        log("fp", why, 0)
        raise HTTPException(502, f"keine TLS-Verbindung ({why})")
    log("fp", "gelesen", 1)
    return {"fp": fp, "gepinnt": d.get("fp") or "", "gleich": bool(d.get("fp")) and hmac.compare_digest(fp, d["fp"])}


@router.post("/api/admin/fernzugang/web/{gid}/dienste/{did}/vertrauen", dependencies=[Depends(auth)])
async def admin_trust(gid: str, did: str, request: Request):
    _on(request)
    x = _system(gid)
    body = await json_body(request, fernzugang.MAX_BODY)
    fp = str(body.get("fp") or "").lower()
    if not FP.fullmatch(fp):
        raise HTTPException(400, "fp: SHA-256 (64 Zeichen)")
    dienste = _dienste(x)
    d = next((d for d in dienste if d["id"] == did and d["schema"] == "https"), None)
    if not d:
        raise HTTPException(404, "no such https service")
    d["fp"] = fp
    for t in [t for t in TUNNEL.values() if t.dienst["id"] == did]:
        await t.end("zertifikat_neu")
    await asyncio.to_thread(fernzugang._update, gid, web=dienste)
    log("fp", "vertraut", 1)
    return {"ok": True}


@router.post("/api/admin/fernzugang/web/oeffnen", dependencies=[Depends(auth)])
async def admin_open(request: Request):
    """„Öffnen“: a tunnel to the saved service and a ticket for the door (once, TICKET_S seconds)."""
    _on(request)
    fernzugang._second_step(request)
    body = await json_body(request, fernzugang.MAX_BODY)
    gid, did = str(body.get("geraet") or ""), str(body.get("dienst") or "")
    x = _system(gid)
    d = _dienst(x, did)
    if not d:
        log("ticket", "unbekannt", 0)
        raise HTTPException(404, "no such service")
    if gid not in fernzugang.ANKER or not x.get("erlaubt", True) or x.get("wartet"):
        log("ticket", "offline", 0)
        raise HTTPException(409, "offline")
    if not anchor_ok(x.get("anker")):
        log("ticket", "anker alt", 0)
        raise HTTPException(409, "anker_alt")
    if ziel_ok(d.get("host"), d.get("port"), x.get("web_netz") is True) is None:
        log("ticket", "ziel", 0)
        raise HTTPException(409, "Ziel nicht mehr erlaubt („Netz dahinter“ ist aus).")
    if d["schema"] == "https" and not FP.fullmatch(str(d.get("fp") or "")):
        log("ticket", "zertifikat fehlt", 0)
        raise HTTPException(409, "zertifikat")
    basis = tor_basis(request)
    if not basis:
        log("ticket", "keine adresse", 0)
        raise HTTPException(409, "adresse")
    if _TOR["server"] is None:
        log("ticket", "tuer zu", 0)
        raise HTTPException(503, "tuer")
    login = fernzugang._login(request)
    t = next((t for t in TUNNEL.values() if t.dienst["id"] == did and hmac.compare_digest(t.login, login)), None)
    if t is None:
        if len(TUNNEL) >= MAX_TUNNEL:
            log("ticket", "voll", 0)
            raise HTTPException(429, f"Höchstens {MAX_TUNNEL} Webdienste gleichzeitig offen.")
        t = Tunnel(gid, d, x.get("web_netz") is True, request)
        TUNNEL[t.id] = t
        log("auf", t.who, d["port"])
        fernzugang._live("Webdienst geöffnet")
    raw = secrets.token_urlsafe(32)
    now = time.time()
    for h in [h for h, v in TICKETS.items() if v["bis"] < now]:
        TICKETS.pop(h, None)
    TICKETS[hashlib.sha256(raw.encode()).hexdigest()] = {"tid": t.id, "bis": now + TICKET_S}
    t.zuletzt = now
    log("ticket", t.who, 1)
    return {"url": f"{basis}{TICKET_PFAD}?t={raw}", "tunnel": t.id, "tor": basis}


@router.delete("/api/admin/fernzugang/web/tunnel/{tid}", dependencies=[Depends(auth)])
async def admin_close(tid: str, request: Request):
    _on(request)
    t = TUNNEL.get(tid) if TID.fullmatch(tid) else None
    if t is None or not hmac.compare_digest(t.login, fernzugang._login(request)):
        log("zu", "unbekannt", 0)
        raise HTTPException(404, "no such tunnel")
    await t.end("geschlossen")
    return {"ok": True}


# ---------------------------------------------------------------- the door (its own small server, TOR_PORT)
def _seite(status, text, panel=""):
    """A short page of the door itself (fixed text, no script)."""
    body = ("<!doctype html><meta charset=utf-8><title>Spark</title><body style=\"font:14px system-ui;margin:24px\">"
            f"<p>{text}</p>").encode()
    heads = [("content-type", "text/html; charset=utf-8"), ("content-length", str(len(body))),
             ("cache-control", "no-store"), ("x-content-type-options", "nosniff"),
             ("content-security-policy", "default-src 'none'; style-src 'unsafe-inline'; "
                                         f"frame-ancestors {panel or chr(39) + 'none' + chr(39)}")]
    return h11.Response(status_code=status, headers=heads), body


ZU = {"gesperrt": "Der Fernzugang ist gesperrt. Im Panel entsperren und den Webdienst neu öffnen.",
      "leerlauf": "Der Webdienst war zu lange unbenutzt. Im Panel neu öffnen.",
      "notaus": "Notaus: der Fernzugang ist gesperrt.", "aus": "Webdienste sind aus.",
      "kein": "Kein offener Webdienst in diesem Browser. Im Panel unter Fernzugang, Webdienste öffnen.",
      "offline": "Das System ist gerade nicht verbunden.", "anker": "Der Anker hat nicht geantwortet.",
      "dienst": "Auf dem System antwortet dort nichts.", "ziel": "Dieses Ziel ist nicht erlaubt.",
      "zertifikat": "Das Zertifikat des Dienstes hat sich geändert: im Panel neu prüfen.",
      "voll": "Zu viele Verbindungen, gleich noch einmal.", "zu_viel": "Zu viele Anfragen, gleich noch einmal.",
      "zu_gross": "Die Anfrage ist zu groß."}


def _cookies(raw):
    out = []
    for part in raw.split(";"):
        k, sep, v = part.strip().partition("=")
        if sep and k:
            out.append((k, v))
    return out


def _tunnel_aus(headers):
    """The tunnel the door's own cookie names (None when none or unknown)."""
    for k, v in headers:
        if k == b"cookie":
            for name, val in _cookies(v.decode("latin-1")):
                if name == COOKIE:
                    for t in TUNNEL.values():
                        if hmac.compare_digest(t.cookie, val):
                            return t
    return None


def _marke_weg(name, marke):
    """A cookie name in the browser -> the service's own name, or None when it is not this service's."""
    for pre in ("__Host-", "__Secure-", ""):
        if name.startswith(pre + marke):
            return pre + name[len(pre) + len(marke):]
    return None


def kopf_rein(headers, t, tor_origin, upgrade):
    """The request's head for the service: none of the panel's cookies, no Authorization, no forwarding headers;
    Host, Origin and Referer say the service's own address; only this service's own cookies, without their mark."""
    dort = t.origin_dort()
    out, cookies = [], []
    for k, v in headers:
        if k == b"cookie":
            for name, val in _cookies(v.decode("latin-1")):
                own = _marke_weg(name, t.marke)
                if own:
                    cookies.append(f"{own}={val}")
            continue
        if k == b"origin":
            if v.decode("latin-1") == tor_origin:
                out.append((b"origin", dort.encode()))
            continue
        if k == b"referer":
            r = v.decode("latin-1")
            if r == tor_origin or r.startswith(tor_origin + "/"):
                out.append((b"referer", (dort + r[len(tor_origin):]).encode()))
            continue
        if k in WEG_REIN or k.startswith(b"x-forwarded-") or k.startswith(b"cf-") or k.startswith(b"x-spark"):
            continue
        out.append((k, v))
    out.insert(0, (b"host", urlsplit(dort).netloc.encode()))
    if cookies:
        out.append((b"cookie", "; ".join(cookies).encode("latin-1")))
    if upgrade:
        out += [(b"connection", b"Upgrade"), (b"upgrade", upgrade)]
    return out


def _set_cookie(v, marke):
    name, sep, rest = v.partition("=")
    if not sep or not name.strip():
        return None
    name = name.strip()
    pre = next((p for p in ("__Host-", "__Secure-") if name.startswith(p)), "")
    value, _, attrs = rest.partition(";")
    keep = [a.strip() for a in attrs.split(";") if a.strip() and not a.strip().lower().startswith("domain")
            and a.strip().lower() != "secure"]
    return "; ".join([f"{pre}{marke}{name[len(pre):]}={value.strip()}"] + keep + ["Secure"])


def _location(v, t):
    """A Location to the service's own address becomes a path (the browser stays in the tunnel)."""
    u = urlsplit(v)
    if not u.scheme:
        return v
    host, port = t.ziel
    default = 443 if u.scheme == "https" else 80
    names = {host, "localhost"} if ipaddress.ip_address(host).is_loopback else {host}
    try:
        uport = u.port or default
    except ValueError:
        return v
    if u.scheme in SCHEMA and (u.hostname or "").strip("[]") in names and uport == port:
        return (u.path or "/") + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")
    return v


def _csp_ohne_rahmen(v):
    return "; ".join(d.strip() for d in v.split(";") if d.strip() and not d.strip().lower().startswith("frame-ancestors"))


def kopf_raus(headers, t):
    """The answer's head for the browser: the service's cookies with its mark (Domain dropped, always Secure), a
    Location to the service as a path, framed only by the panel (frame-ancestors), no HSTS, X-Frame-Options, Alt-Svc
    or Clear-Site-Data of the service."""
    out = []
    for k, v in headers:
        if k == b"set-cookie":
            c = _set_cookie(v.decode("latin-1"), t.marke)
            if c:
                out.append((b"set-cookie", c.encode("latin-1")))
        elif k == b"location":
            out.append((b"location", _location(v.decode("latin-1"), t).encode("latin-1")))
        elif k == b"content-security-policy":
            rest = _csp_ohne_rahmen(v.decode("latin-1"))
            if rest:
                out.append((k, rest.encode("latin-1")))
        elif k not in WEG_RAUS:
            out.append((k, v))
    out.append((b"content-security-policy", f"frame-ancestors {t.panel or chr(39) + 'none' + chr(39)}".encode()))
    return out


class _Weg:
    """One way to the service for one browser connection: the channel (with TLS for https) and its h11 client."""

    def __init__(self, t):
        self.t, self.k, self.io, self.conn, self.platz = t, None, None, None, False

    async def auf(self):
        t = self.t
        try:
            await asyncio.wait_for(t.plaetze.acquire(), WARTEN_S)
        except asyncio.TimeoutError:
            raise ConnectionError("voll")
        self.platz = True
        host, port = t.ziel
        self.k = await kanal_auf(t.gid, host, port, t.netz, t)
        self.io = self.k
        if t.dienst["schema"] == "https":
            tls = TlsKanal(self.k)
            fp = await asyncio.wait_for(tls.handshake(), OPEN_S)
            if not hmac.compare_digest(fp, str(t.dienst.get("fp") or "")):
                log("fp", "falsch", 0)
                await tls.end("zertifikat")
                raise ConnectionError("zertifikat")
            self.io = tls
        self.conn = h11.Connection(h11.CLIENT, max_incomplete_event_size=MAX_KOPF)

    async def event(self):
        while True:
            ev = self.conn.next_event()
            if ev is h11.NEED_DATA:
                data = await self.io.read()
                self.t.rein += len(data)
                self.conn.receive_data(data)
                continue
            return ev

    async def send(self, ev):
        data = self.conn.send(ev)
        if data:
            await self.io.write(data)

    async def zu(self, why):
        if self.io is not None:
            await self.io.end(why)
        if self.platz:
            self.platz = False
            self.t.plaetze.release()


async def _antwort(conn, writer, resp, body=b""):
    writer.write(conn.send(resp))
    if body:
        writer.write(conn.send(h11.Data(data=body)))
    writer.write(conn.send(h11.EndOfMessage()))
    await writer.drain()


def _rate_ok(t, now):
    t.anfragen = [x for x in t.anfragen if now - x < 60]
    if len(t.anfragen) >= REQ_MIN:
        return False
    t.anfragen.append(now)
    return True


async def _ticket(conn, writer, req, tor_origin):
    """GET /__spark/ticket?t=…: the ticket once; then the door's own cookie for that tunnel, on to its path. A tunnel
    this browser had before ends (one tunnel per browser)."""
    q = parse_qs(urlsplit(req.target.decode("latin-1")).query)
    raw = (q.get("t") or [""])[0]
    h = hashlib.sha256(raw.encode()).hexdigest() if re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", raw) else ""
    tk = TICKETS.pop(h, None) if h else None
    t = TUNNEL.get(tk["tid"]) if tk and tk["bis"] >= time.time() else None
    if t is None or t.lebt() != "ok":
        log("ticket", "ungueltig", 0)
        return await _antwort(conn, writer, *_seite(403, ZU["kein"]))
    vorher = _tunnel_aus(req.headers)
    if vorher is not None and vorher is not t:
        await vorher.end("ersetzt")
    pfad = str(t.dienst.get("pfad") or "/")
    heads = [("location", pfad), ("content-length", "0"), ("cache-control", "no-store"),
             ("set-cookie", f"{COOKIE}={t.cookie}; Path=/; Secure; HttpOnly; SameSite=Strict"),
             ("content-security-policy", f"frame-ancestors {t.panel}" if t.panel else "frame-ancestors 'none'")]
    t.zuletzt = time.time()
    log("ticket", "eingeloest", 1)
    writer.write(conn.send(h11.Response(status_code=303, headers=heads)))
    writer.write(conn.send(h11.EndOfMessage()))
    await writer.drain()


async def _pumpe(lesen, schreiben, t):
    """After an upgrade (WebSocket): bytes as they come, both ways, until one side closes."""
    with contextlib.suppress(Exception):
        while not t.ende:
            data = await lesen()
            if not data:
                break
            t.zuletzt = time.time()
            await schreiben(data)


async def verbindung(reader, writer):
    """One browser connection to the door: requests one after the other (h11), each checked, its head rewritten
    (kopf_rein, kopf_raus), its body passed on with flow control; an upgrade (WebSocket) then passes as it is."""
    conn = h11.Connection(h11.SERVER, max_incomplete_event_size=MAX_KOPF)
    weg, t = None, None
    peer = writer.get_extra_info("peername")
    log("verbindung", "auf", 1 if peer else 0)

    async def von_browser():
        while True:
            ev = conn.next_event()
            if ev is h11.NEED_DATA:
                conn.receive_data(await reader.read(65536))
                continue
            return ev
    try:
        while True:
            ev = await von_browser()
            if isinstance(ev, h11.ConnectionClosed) or ev is h11.PAUSED:
                break
            if not isinstance(ev, h11.Request):
                break
            host = next((v.decode("latin-1") for k, v in ev.headers if k == b"host"), "")
            tor_origin = f"https://{host}"
            if urlsplit(ev.target.decode("latin-1")).path == TICKET_PFAD:
                await _ticket(conn, writer, ev, tor_origin)
                if weg is not None:
                    await weg.zu("ticket")
                    weg = None
            else:
                neu = _tunnel_aus(ev.headers)
                now = time.time()
                why = neu.lebt(now) if neu else "kein"
                if why not in ("ok",):
                    if neu is not None and why:
                        await neu.end(why)
                    await _antwort(conn, writer, *_seite(403, ZU.get(why, ZU["kein"]), neu.panel if neu else ""))
                    break
                if not _rate_ok(neu, now):
                    log("abgewiesen", "rate", 0)
                    await _antwort(conn, writer, *_seite(429, ZU["zu_viel"], neu.panel))
                    break
                if t is not neu:
                    if weg is not None:
                        await weg.zu("anderer")
                        weg = None
                    if t is not None:
                        t.verbindungen.discard(writer)
                    t = neu
                    t.verbindungen.add(writer)
                t.zuletzt = now
                size = next((v for k, v in ev.headers if k == b"content-length"), b"0")
                if not size.isdigit() or int(size) > MAX_BODY_MB * 1024 * 1024:
                    await _antwort(conn, writer, *_seite(413, ZU["zu_gross"], t.panel))
                    break
                upgrade = next((v for k, v in ev.headers if k == b"upgrade"), None) \
                    if any(k == b"connection" and b"upgrade" in v.lower() for k, v in ev.headers) else None
                if weg is None:
                    weg = _Weg(t)
                    try:
                        await weg.auf()
                    except (ConnectionError, OSError, ssl.SSLError, asyncio.TimeoutError) as e:
                        word = str(e) if isinstance(e, ConnectionError) and str(e) in ZU else "dienst"
                        log("abgewiesen", word, t.dienst["port"])
                        await weg.zu(word)
                        weg = None
                        await _antwort(conn, writer, *_seite(502, ZU[word], t.panel))
                        break
                await weg.send(h11.Request(method=ev.method, target=ev.target,
                                           headers=kopf_rein(ev.headers, t, tor_origin, upgrade)))
                total = 0
                while True:      # the body, piece by piece (the anchor's window holds a fast browser back)
                    b = await von_browser()
                    if isinstance(b, h11.Data):
                        total += len(b.data)
                        if total > MAX_BODY_MB * 1024 * 1024:
                            raise ConnectionError("zu_gross")
                        await weg.send(b)
                    elif isinstance(b, h11.EndOfMessage):
                        await weg.send(b)
                        break
                    else:
                        raise ConnectionError("browser")
                while True:      # the answer: its head rewritten, its body as it comes
                    r = await weg.event()
                    if isinstance(r, h11.InformationalResponse):
                        if r.status_code == 101 and upgrade:
                            writer.write(conn.send(h11.InformationalResponse(
                                status_code=101, headers=kopf_raus(r.headers, t) + [(b"connection", b"Upgrade"),
                                                                                   (b"upgrade", upgrade)])))
                            await writer.drain()
                            log("websocket", "auf", t.dienst["port"])
                            rest_b, _ = conn.trailing_data
                            rest_d, _ = weg.conn.trailing_data
                            if rest_b:
                                await weg.io.write(rest_b)
                            if rest_d:
                                writer.write(rest_d)
                                await writer.drain()

                            async def zum_browser(data):
                                t.rein += len(data)
                                writer.write(data)
                                await writer.drain()
                            hin = asyncio.create_task(_pumpe(lambda: reader.read(65536), weg.io.write, t))
                            her = asyncio.create_task(_pumpe(weg.io.read, zum_browser, t))
                            await asyncio.wait({hin, her}, return_when=asyncio.FIRST_COMPLETED)
                            for x in (hin, her):
                                x.cancel()
                            return
                        continue
                    if isinstance(r, h11.Response):
                        writer.write(conn.send(h11.Response(status_code=r.status_code, reason=r.reason,
                                                            headers=kopf_raus(r.headers, t))))
                        await writer.drain()
                    elif isinstance(r, h11.Data):
                        t.rein += len(r.data)
                        writer.write(conn.send(r))
                        await writer.drain()
                        t.zuletzt = time.time()
                    elif isinstance(r, h11.EndOfMessage):
                        writer.write(conn.send(h11.EndOfMessage()))
                        await writer.drain()
                        break
                    else:
                        raise ConnectionError("dienst")
                if weg.conn.our_state is h11.MUST_CLOSE or weg.conn.their_state is h11.MUST_CLOSE:
                    await weg.zu("fertig")
                    weg = None
                else:
                    weg.conn.start_next_cycle()
            if conn.our_state is h11.MUST_CLOSE or conn.their_state is h11.MUST_CLOSE:
                break
            conn.start_next_cycle()
    except (h11.RemoteProtocolError, h11.LocalProtocolError):
        with contextlib.suppress(Exception):
            if conn.our_state in (h11.IDLE, h11.SEND_RESPONSE):
                await _antwort(conn, writer, *_seite(400, "Ungültige Anfrage."))
    except (ConnectionError, OSError, asyncio.IncompleteReadError, ssl.SSLError, asyncio.TimeoutError):
        pass
    finally:
        if weg is not None:
            await weg.zu("browser")
        if t is not None:
            t.verbindungen.discard(writer)
        with contextlib.suppress(Exception):
            writer.close()


def _tls():
    from common import TLS_DIR
    cert, key = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
    if not (os.path.exists(cert) and os.path.exists(key)):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.num_tickets = 0               # the same reason as the panel's own (panel.tls_context)
    ctx.set_alpn_protocols(["http/1.1"])
    ctx.load_cert_chain(cert, key)
    return ctx


async def tor_auf(host=None, port=TOR_PORT, ctx=None):
    """Starts the door (TLS with the panel's certificate) when it is not running; the reason word when it cannot."""
    if _TOR["server"] is not None:
        return ""
    ctx = ctx or _tls()
    if ctx is None:
        _TOR["fehler"] = "zertifikat"
        return "zertifikat"
    if host is None:
        from common import load_config
        host = (load_config("panel") or {}).get("host") or "0.0.0.0"
    try:
        _TOR["server"] = await asyncio.start_server(verbindung, host, port, ssl=ctx, limit=MAX_KOPF,
                                                    ssl_handshake_timeout=15)
    except OSError:
        _TOR["fehler"] = "port"
        log("tor", "port belegt", port)
        return "port"
    _TOR["fehler"] = ""
    _TOR["loop"] = asyncio.get_running_loop()    # the panel's loop: tunnels end there, also when a thread asks
    log("tor", "auf", port)
    return ""


async def tor_zu(why="aus"):
    s = _TOR["server"]
    _TOR["server"] = None
    await close_all(why)
    if s is not None:
        s.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(s.wait_closed(), 5)
        log("tor", why, 0)


async def wache():
    """The door's watch (panel.serve): open while the switch is on and no Notaus, closed otherwise; tunnels that
    are no longer allowed (lock, idle) end."""
    while True:
        with contextlib.suppress(Exception):
            want = admin_on() and not fernzugang._notaus()
            if want and _TOR["server"] is None:
                await tor_auf()
            elif not want and _TOR["server"] is not None:
                await tor_zu("notaus" if fernzugang._notaus() else "aus")
            now = time.time()
            for t in list(TUNNEL.values()):
                why = t.lebt(now)
                if why != "ok":
                    await t.end(why or "zu")
        await asyncio.sleep(WACHE_S)


def frame_src(request):
    """The door's origin for the panel's own frame-src (the page frames the tunnel), or "" while it is off."""
    try:
        return tor_basis(request) if admin_on() else ""
    except Exception:
        return ""
