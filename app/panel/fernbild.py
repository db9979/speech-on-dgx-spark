"""Fernzugang, Bildschirm (plan ssh-vermittlung stage 4, Dominik 2026-10-29 „Empfehlung“ 1a, 2a, 3a): the screen of a
paired system in the browser, through the same anchor pipe as its shell. guacd (Apache Guacamole's proxy, from the
Debian packages, install.sh --fernbild, only on 127.0.0.1:4822) speaks VNC or RDP; the panel speaks the Guacamole
protocol with guacd and with the browser (guacamole-common-js 1.5.0, Apache-2.0, vendored and pinned in GUAC).

    browser (Guacamole.Client) ──WS /api/fernzugang/bildschirm?t=──► panel ──TCP──► guacd (127.0.0.1:4822)
                                                                      ▲                 │ VNC/RDP to 127.0.0.1:<port>
                                                                      └── one local port for this session, then the
                                                                          anchor's channel „ziel: bild“ to the one
                                                                          screen port over there (spark-anker BILD)

On the system `sudo spark-anker bildschirm` sets it up (X11: x11vnc on demand; GNOME on Wayland: gnome-remote-desktop
as RDP; other Wayland: wayvnc; macOS: the built-in Bildschirmfreigabe), always on 127.0.0.1 there; it asks this panel
for a random password (POST /api/fernzugang/anker/bildschirm), which only the vault keeps. On a Mac the macOS user and
password are typed in the panel for every session, kept only in the one ticket and in guacd's connection, never stored,
never logged.

Rules (fixed, Sicherheits-Checkliste):
- Admin switch chat.fernbild (Funktionen → Fernzugang zu Servern → Bildschirm, off), under chat.fernzugang. Admins in
  their own browser only, with a second sign-in step, on the unlocked page (fernzugang._frei); a one-time ticket
  (fernzugang.TICKET_S, bound to the login) opens the socket, which checks the switch, Origin, the admin, the Notaus,
  the ticket and the room itself. A screen session counts with the shells (chat.fernzugang_sitzungen), shows the red
  line, ends on idle (chat.fernzugang_leerlauf_min, mouse and keys count), on „Trennen“, „Alle trennen“ and the Notaus.
- First it only shows: mouse and keys go to the system only after „Steuern“ (an instruction of this panel,
  „spark-steuern“), and back to „Ansehen“ at any time. The clipboard is off (guacd disable-copy and disable-paste)
  unless chat.fernbild_zwischenablage is on, and even then the browser's clipboard reaches the system only while
  „Steuern“ is on.
- The browser may send only the instructions in ALWAYS (sync, size, ack, nop, disconnect), the ones in CONTROL while
  „Steuern“ is on, and a clipboard stream only as above; everything else (files, pipes, audio, arguments) is dropped,
  each message checked for size (MAX_IN). guacd's output passes as it is (pictures of the screen), never kept.
- The anchor reaches only the one screen port it set up, on 127.0.0.1 over there; guacd reaches only the one local
  port of this session, which takes exactly one connection and closes.
- Logs „fernzugang: bild_<word> | <reason> | <number>“ in fixed words and numbers; never a password, a user name, a
  picture or a key typed. Live: kind and count (fernzugang.counts „bildschirm“). The history (fernzugang-verlauf.json)
  notes the kind „Bildschirm“ like a shell.

    admin in the browser (core.auth + fernzugang.is_admin_browser):
    POST   /api/admin/fernzugang/bildschirm {geraet, breite, hoehe, sparsam[, benutzer, passwort (macOS)]}
                                                        -> {ticket, gilt_s}; „sparsam“: 16-bit colours
    WS     /api/fernzugang/bildschirm?t=<ticket>        the Guacamole tunnel (subprotocol "guacamole")
    anchor (Bearer key, `sudo spark-anker bildschirm`):
    POST   /api/fernzugang/anker/bildschirm {art}       -> {passwort[, benutzer]} (a new random one, kept sealed)
    DELETE /api/fernzugang/anker/bildschirm             the screen is off over there
"""
import asyncio
import codecs
import contextlib
import hashlib
import hmac
import re
import secrets
import socket
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

import core
import features
import fernzugang
import guard
import vault
from core import auth, json_body

router = APIRouter()

GUACD = ("127.0.0.1", 4822)
GUACD_UNIT = "speech-spark-guacd"
GUACD_S = 10            # guacd answers the handshake within this long
GUAC_VERSION = "1.5.0"  # guacamole-common-js, vendored in static/guac (Apache-2.0)
GUAC = {"guacamole-common.min.js": "f543f240fee1f04653a5921aa1398eb5c680e8760cb3ddf0a9ee5f8c1963774e",
        "LICENSE": "3c7f148c26065e0a581b5dda114e68e16243bf5ae0b4f6209749a0e3373201d5"}
ANKER_MIN = (1, 2, 0)   # spark-anker knows „ziel: bild“ from this version on
ARTEN = {"x11vnc": "vnc", "wayvnc": "vnc", "mac": "vnc", "grd": "rdp"}   # what the anchor set up -> guacd's protocol
RDP_USER = "spark-bild"
MAX_IN = 16 * 1024      # one message of the browser
MAX_ELEMENT = 8 * 1024 * 1024   # one element of guacd's output (a picture's piece) at most
MAX_OUT = 256 * 1024    # characters per message to the browser (whole instructions, several at once)
ALWAYS = {"sync", "size", "ack", "nop", "disconnect"}
CONTROL = {"mouse", "key"}
CLIPBOARD = {"clipboard", "blob", "end"}
STEUERN = "spark-steuern"
SIZE = ((320, 7680), (200, 4320))   # pixels: width, height
FPS = 15                # at most this many pictures a second: the page's „sync“ reaches guacd no faster (guacd waits
                        # for it before the next frame), so a fast screen never floods a slow line
RATE_S = 5              # every this long the page learns the rate (instruction „spark-rate“, KB/s): below LANGSAM it
LANGSAM = 100           # shows a hint (the Synology proxy carries about 50-70 KB/s, the direct https path much more)
CRED = re.compile(r"[^\x00-\x1f\x7f]{1,256}")


def log(word, why="", n=1):
    fernzugang.log("bild_" + word, why, n)


def admin_on(c=None):
    """Funktionen → Fernzugang zu Servern → Bildschirm (admin, off); a Spark-wide door under the Fernzugang."""
    return features.admin_on("fernbild", c) and fernzugang.admin_on(c)


def clipboard_on(c=None):
    """Funktionen → … → Bildschirm → Zwischenablage (admin, off)."""
    return features.admin_on("fernbildablage", c)


def anchor_ok(version):
    """The anchor knows the screen's channel (ANKER_MIN)."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    return bool(m) and tuple(int(x) for x in m.groups()) >= ANKER_MIN


# ---------------------------------------------------------------- the Guacamole protocol
def enc(*parts):
    """One instruction: every element as <length>.<value>, the length in characters."""
    return ",".join(f"{len(p)}.{p}" for p in parts) + ";"


def split(buf, limit=MAX_ELEMENT):
    """Whole instructions from the start of buf: ([(raw, [opcode, args …]), …], rest). Raises ValueError when buf is
    no Guacamole protocol."""
    out, i, n = [], 0, len(buf)
    while i < n:
        start, elems = i, []
        while True:
            dot = buf.find(".", i, i + 12)
            if dot < 0:
                if n - i > 11:
                    raise ValueError("length")
                return out, buf[start:]
            size = buf[i:dot]
            if not size.isdigit() or int(size) > limit:
                raise ValueError("length")
            end = dot + 1 + int(size)
            if end >= n:
                return out, buf[start:]
            elems.append(buf[dot + 1:end])
            if buf[end] == ";":
                i = end + 1
                out.append((buf[start:i], elems))
                break
            if buf[end] != ",":
                raise ValueError("separator")
            i = end + 1
    return out, ""


class Filter:
    """What the browser may send to guacd (ALWAYS, CONTROL only while „Steuern“ is on, a clipboard stream only with
    chat.fernbild_zwischenablage and „Steuern“), and the panel's own instruction „spark-steuern“."""

    def __init__(self, clipboard=False):
        self.steuern = False
        self.clipboard = clipboard
        self.streams = set()     # the browser's clipboard streams
        self.next_sync = 0.0     # FPS: when the next „sync“ may reach guacd

    def sync_delay(self, now):
        """Seconds to hold this „sync“ back so that guacd draws at most FPS pictures a second (in order)."""
        at = max(now, self.next_sync)
        self.next_sync = at + 1 / FPS
        return at - now

    def take(self, elems):
        """(what goes to guacd or None, the answer to the browser or None)."""
        op, args = elems[0], elems[1:]
        if op == "" and args[:1] == ["ping"]:
            return None, enc("", *args[:2])          # the tunnel's own ping: answered here (the Java servlet does it too)
        if op == STEUERN:
            self.steuern = args[:1] == ["1"]
            if not self.steuern:
                self.streams.clear()
            return None, None
        if op in ALWAYS:
            return enc(*elems), None
        if op in CONTROL:
            return (enc(*elems), None) if self.steuern else (None, None)
        if op in CLIPBOARD and self.clipboard and self.steuern:
            if op == "clipboard" and len(args) == 2 and args[0].isdigit() and args[1] == "text/plain":
                self.streams.add(args[0])
                return enc(*elems), None
            if op in ("blob", "end") and args[:1] and args[0] in self.streams:
                if op == "end":
                    self.streams.discard(args[0])
                return enc(*elems), None
        return None, None


# ---------------------------------------------------------------- guacd
def _start_guacd():
    import subprocess
    with contextlib.suppress(Exception):
        subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", GUACD_UNIT], timeout=30, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def _guacd():
    """A connection to guacd; its unit started once when it is not there (install.sh --fernbild)."""
    for n in range(2):
        try:
            return await asyncio.wait_for(asyncio.open_connection(*GUACD), 5)
        except (OSError, asyncio.TimeoutError):
            if n:
                raise
            await asyncio.to_thread(_start_guacd)
            await asyncio.sleep(1.5)


async def _read_one(reader, state):
    """The next whole instruction from guacd (handshake only)."""
    while True:
        got, state["rest"] = split(state["rest"])
        if got:
            state["rest"] = "".join(r for r, _ in got[1:]) + state["rest"]
            return got[0][1]
        data = await reader.read(65536)
        if not data:
            raise EOFError
        state["rest"] += state["dec"].decode(data)


async def handshake(reader, writer, proto, values, width, height):
    """select → args → size, audio, video, image, connect (each argument guacd asks for by name) → ready."""
    state = {"rest": "", "dec": codecs.getincrementaldecoder("utf-8")()}
    writer.write(enc("select", proto).encode())
    await writer.drain()
    args = await asyncio.wait_for(_read_one(reader, state), GUACD_S)
    if args[0] != "args":
        raise ValueError("guacd")
    names = args[1:]
    if names and names[0].startswith("VERSION_"):       # guacd 1.1 and newer: its version first, then the names
        answer = [names[0]] + [values.get(k, "") for k in names[1:]]
    else:
        answer = [values.get(k, "") for k in names]
    writer.write((enc("size", str(width), str(height), "96") + enc("audio") + enc("video")
                  + enc("image", "image/png", "image/jpeg", "image/webp") + enc("connect", *answer)).encode())
    await writer.drain()
    ready = await asyncio.wait_for(_read_one(reader, state), GUACD_S)
    if ready[0] != "ready":
        raise ValueError("guacd " + ready[0][:10])
    return state


def values_for(proto, port, password, user="", clipboard=False, sparsam=False):
    """guacd's arguments. guacd sends JPEG or WebP by itself where the screen changes fast (the page offers both);
    „sparsam“ halves the colours (16 bit) for a slow line."""
    v = {"hostname": "127.0.0.1", "port": str(port), "password": password, "username": user,
         "disable-copy": "" if clipboard else "true", "disable-paste": "" if clipboard else "true",
         "read-only": "", "color-depth": "16" if sparsam else "24", "cursor": "local"}
    if proto == "rdp":
        v.update({"security": "any", "ignore-cert": "true", "resize-method": "display-update",
                  "disable-audio": "true", "enable-drive": "", "enable-printing": "", "disable-upload": "true",
                  "disable-download": "true"})
    return v


# ---------------------------------------------------------------- the local port guacd connects to
class Port:
    """One port on 127.0.0.1 that takes exactly one connection (guacd's) and joins it with the session's pipe to the
    anchor (fernzugang.Sitzung.theirs); closes after that one."""

    def __init__(self, pipe):
        self.pipe = pipe
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.srv.settimeout(GUACD_S + 5)
        self.port = self.srv.getsockname()[1]
        self.conn = None
        threading.Thread(target=self._run, name="fernbild-port", daemon=True).start()

    def _pump(self, a, b):
        while True:
            try:
                data = a.recv(32 * 1024)
            except OSError:
                data = b""
            if not data:
                break
            try:
                b.sendall(data)
            except OSError:
                break
        for x in (a, b):
            with contextlib.suppress(OSError):
                x.shutdown(socket.SHUT_RDWR)

    def _run(self):
        try:
            conn, _ = self.srv.accept()
        except OSError:
            return
        finally:
            with contextlib.suppress(OSError):
                self.srv.close()
        self.conn = conn
        self.pipe.setblocking(True)
        threading.Thread(target=self._pump, args=(self.pipe, conn), daemon=True).start()
        self._pump(conn, self.pipe)

    def close(self):
        for x in (self.srv, self.conn):
            with contextlib.suppress(OSError, AttributeError):
                x.close()


# ---------------------------------------------------------------- admin: the ticket
def _on(request):
    if not admin_on():
        raise HTTPException(404, "Bildschirm ist aus (Funktionen → Fernzugang zu Servern → Bildschirm)")
    fernzugang._browser(request)
    if fernzugang._notaus(count=True):
        log("abgewiesen", "notaus", 0)
        raise HTTPException(503, "Notaus: Fernzugang gesperrt")


def _px(v, rng, default):
    return v if isinstance(v, int) and not isinstance(v, bool) and rng[0] <= v <= rng[1] else default


@router.post("/api/admin/fernzugang/bildschirm", dependencies=[Depends(auth)])
async def admin_screen(request: Request):
    """„Bildschirm“: on the unlocked page a ticket that opens the screen once, within fernzugang.TICKET_S seconds."""
    _on(request)
    fernzugang._second_step(request)
    fernzugang._frei(request)
    guard.limit(request, "fernzugang_sitzung", admin=True)
    body = await json_body(request, fernzugang.MAX_BODY)
    gid = str(body.get("geraet") or "")
    x = fernzugang._read()["geraete"].get(gid) if fernzugang.GID.fullmatch(gid) else None
    if not x or x.get("stand") == "abbau":
        log("ticket", "unbekannt", 0)
        raise HTTPException(404, "no such system")
    if gid not in fernzugang.ANKER:
        log("ticket", "offline", 0)
        raise HTTPException(409, "offline")
    art = x.get("bild")
    if art not in ARTEN:
        log("ticket", "nicht eingerichtet", 0)
        raise HTTPException(409, "Auf dem System ist der Bildschirm nicht eingerichtet: dort `sudo spark-anker bildschirm`.")
    if not anchor_ok(x.get("anker")):
        log("ticket", "anker alt", 0)
        raise HTTPException(409, "Der Anker ist zu alt für den Bildschirm: den Befehl `bildschirm` aus dem Panel dort noch einmal.")
    if len(fernzugang.SITZUNG) >= fernzugang.max_sitzungen():
        log("ticket", "voll", 0)
        raise HTTPException(429, "too many sessions")
    user = password = ""
    if art == "mac":         # the macOS user and password: only in this ticket and in guacd's connection
        user, password = str(body.get("benutzer") or ""), str(body.get("passwort") or "")
        if not CRED.fullmatch(user) or not CRED.fullmatch(password) or len(user) > 64:
            log("ticket", "mac anmeldung fehlt", 0)
            raise HTTPException(400, "benutzer und passwort: die Anmeldung am Mac")
    t = secrets.token_urlsafe(32)
    now = time.time()
    for k in [k for k, v in fernzugang.TICKETS.items() if v["until"] < now]:
        fernzugang.TICKETS.pop(k, None)
    prof = core.acting_profile(request)
    fernzugang.TICKETS[hashlib.sha256(t.encode()).hexdigest()] = {
        "gid": gid, "login": fernzugang._login(request), "until": now + fernzugang.TICKET_S, "art": "bildschirm",
        "cols": _px(body.get("breite"), SIZE[0], 1280), "rows": _px(body.get("hoehe"), SIZE[1], 800),
        "who": fernzugang._who(request), "uid": prof["id"] if prof else None, "mac": (user, password),
        "sparsam": body.get("sparsam") is True}
    log("ticket", fernzugang._who(request), 1)
    return {"ticket": t, "gilt_s": fernzugang.TICKET_S}


# ---------------------------------------------------------------- the browser's socket
async def _error(ws, why):
    """A reason the page understands (Guacamole „error“ with the panel's fixed word), then the socket closes."""
    with contextlib.suppress(Exception):
        await ws.send_text(enc("error", why, "519"))
    with contextlib.suppress(Exception):
        await ws.close(1000)


@router.websocket("/api/fernzugang/bildschirm")
async def screen_ws(ws: WebSocket):
    """The screen in the browser. Its own checks, in this order: switch, Origin, admin login, Notaus, ticket, room."""
    if not admin_on():
        return await fernzugang._refuse(ws, "bild aus", 4404)
    if not fernzugang.same_origin(ws):
        guard.log("foreign_page_refused", path="/api/fernzugang/bildschirm")
        return await fernzugang._refuse(ws, "fremde Seite")
    if not fernzugang.is_admin_browser(ws):
        return await fernzugang._refuse(ws, "kein Admin")
    if fernzugang._notaus(count=True):
        return await fernzugang._refuse(ws, "notaus", 4503)
    raw = ws.query_params.get("t", "")
    h = hashlib.sha256(raw.encode()).hexdigest() if re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", raw) else ""
    tk = fernzugang.TICKETS.pop(h, None) if h else None
    if not tk or tk.get("art") != "bildschirm" or tk["until"] < time.time() \
            or not hmac.compare_digest(tk["login"], fernzugang._login(ws)):
        return await fernzugang._refuse(ws, "ticket")
    _g, _a, _n, why = fernzugang._platz(tk["gid"])
    if why:
        return await fernzugang._refuse(ws, why, 4429 if why == "voll" else 4409)
    await ws.accept(subprotocol="guacamole")
    user, password = tk.pop("mac", ("", ""))
    try:                                         # guacd first: without it no channel is opened on the server
        reader, writer = await _guacd()
    except OSError:
        log("guacd", "fehlt", 0)
        return await _error(ws, "guacd")
    s, g, why = await fernzugang.aufbauen(tk["gid"], "bildschirm", ws, tk["who"], tk.get("uid"), tk["cols"], tk["rows"],
                                          tk["login"], ws)
    if s is None:
        writer.close()
        log("abgewiesen", why[:30], 0)
        return await _error(ws, why[:30])
    art = g.get("bild")
    proto = ARTEN.get(art, "vnc")
    if art != "mac":
        user = RDP_USER if proto == "rdp" else ""
        password = vault.open_(g.get("bild_pw", "")) or ""
    port = Port(s.theirs)
    s.bild_port = port
    try:
        state = await handshake(reader, writer, proto, values_for(proto, port.port, password, user, clipboard_on(), tk.get("sparsam")),
                                tk["cols"], tk["rows"])
    except Exception as e:
        log("guacd", "fehlt" if isinstance(e, OSError) else type(e).__name__.lower()[:20], 0)
        port.close()
        writer.close()
        await s.end("guacd")
        return
    finally:
        user = password = ""
    fernzugang.STATS["sitzungen"] += 1
    log("auf", s.who, len(fernzugang.SITZUNG))
    fernzugang._live("Fern-Bildschirm geöffnet")
    s.tasks.append(asyncio.create_task(fernzugang._melden(s, g)))
    await ws.send_text(enc("", s.id))            # the tunnel's own first instruction: its id (the page waits for it)
    filt = Filter(clipboard_on())
    s.tasks += [asyncio.create_task(_to_browser(s, ws, reader, state)), asyncio.create_task(s._idle())]
    try:
        await _from_browser(s, ws, writer, filt)
    finally:
        port.close()
        with contextlib.suppress(Exception):
            writer.close()
        await s.end(s.grund or "browser")


async def _to_browser(s, ws, reader, state):
    """guacd's output to the page, as whole instructions (the page's tunnel parses message by message)."""
    loop = asyncio.get_running_loop()
    mark, sent = loop.time(), 0
    try:
        while not s.ende.is_set():
            got, state["rest"] = split(state["rest"])
            if got:
                part = []
                size = 0
                for raw, elems in got:
                    if elems[0] == "error":
                        log("zu", "guacd fehler", 0)
                    part.append(raw)
                    size += len(raw)
                    if size >= MAX_OUT:
                        await ws.send_text("".join(part))
                        sent += size
                        part, size = [], 0
                if part:
                    await ws.send_text("".join(part))
                    sent += size
                now = loop.time()
                if now - mark >= RATE_S:
                    s.bild_bytes += sent
                    await ws.send_text(enc("spark-rate", str(int(sent / 1024 / (now - mark)))))
                    mark, sent = now, 0
                continue
            data = await reader.read(65536)
            if not data:
                break
            state["rest"] += state["dec"].decode(data)
    except (ValueError, WebSocketDisconnect, RuntimeError, OSError):
        pass
    s.bild_bytes += sent
    await s.end(s.grund or "server")


def _write_late(s, writer, data):
    if not s.ende.is_set():
        with contextlib.suppress(Exception):
            writer.write(data.encode())


async def _from_browser(s, ws, writer, filt):
    """The page's instructions, filtered (Filter), to guacd; mouse and keys count as activity even while only
    watching."""
    rest = ""
    loop = asyncio.get_running_loop()
    try:
        while not s.ende.is_set():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text") or ""
            if len(text) > MAX_IN or msg.get("bytes"):
                await _error(ws, "zu_gross")
                s.grund = "zu_gross"
                break
            if fernzugang._notaus() or not admin_on():
                s.grund = "notaus" if fernzugang._notaus() else "aus"
                break
            got, rest = split(rest + text, MAX_IN)
            if len(rest) > MAX_IN:
                break
            out = []
            for _raw, elems in got:
                if elems[0] in CONTROL:
                    s.zuletzt = time.time()
                was = filt.steuern
                fwd, back = filt.take(elems)
                if filt.steuern != was:
                    log("steuern", "an" if filt.steuern else "aus", 1 if filt.steuern else 0)
                if back:
                    await ws.send_text(back)
                if fwd and elems[0] == "sync":
                    wait = filt.sync_delay(loop.time())
                    if wait > 0:            # later, without holding the mouse and keys back
                        loop.call_later(wait, _write_late, s, writer, fwd)
                        continue
                if fwd:
                    out.append(fwd)
            if out:
                writer.write("".join(out).encode())
                await writer.drain()
    except (ValueError, WebSocketDisconnect, RuntimeError, OSError, ConnectionError):
        pass


# ---------------------------------------------------------------- the anchor: a password for the screen
def _anchor(request):
    if not admin_on():
        raise HTTPException(404, "not found")
    guard.limit(request, "fernzugang_koppeln")
    gid, _x = fernzugang.by_key(fernzugang._bearer(request))
    if not gid:
        guard.failed(request, "fernzugang-anker", what="fernzugang_anker")
        log("passwort", "schluessel", 0)
        raise HTTPException(403, "unknown key")
    return gid


@router.post("/api/fernzugang/anker/bildschirm")
async def anchor_screen(request: Request):
    """`sudo spark-anker bildschirm`: the kind it set up and a new random password (VNC takes 8 characters, RDP more),
    which only the vault keeps here; a Mac has none (the macOS sign-in is asked per session)."""
    gid = _anchor(request)
    body = await json_body(request, fernzugang.MAX_BODY)
    art = str(body.get("art") or "")
    if art not in ARTEN:
        log("passwort", "art", 0)
        raise HTTPException(400, "art: x11vnc, wayvnc, grd or mac")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    pw = "" if art == "mac" else "".join(secrets.choice(alphabet) for _ in range(24 if art == "grd" else 8))
    sealed = vault.seal(pw) if pw else ""
    if pw and not str(sealed).startswith(vault.PREFIX):
        log("passwort", "tresor fehlt", 0)
        raise HTTPException(503, "vault not available")
    await asyncio.to_thread(fernzugang._update, gid, bild=art, bild_pw=sealed)
    log("passwort", art, 1)
    fernzugang._live("Fern-Bildschirm eingerichtet")
    return {"passwort": pw, "benutzer": RDP_USER if art == "grd" else ""}


@router.delete("/api/fernzugang/anker/bildschirm")
async def anchor_screen_off(request: Request):
    gid = _anchor(request)
    await asyncio.to_thread(fernzugang._update, gid, bild=None, bild_pw=None)
    log("passwort", "aus", 0)
    return {"ok": True}


def guac_file(name):
    """(path, media type) for GET /static/guac/<name> (panel.py): only the pinned files of guacamole-common-js and its
    license (their SHA-256 in GUAC, test_fernbild checks them)."""
    import os
    if name not in GUAC:
        raise HTTPException(404, "not found")
    return (os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "guac", name),
            "text/plain" if name == "LICENSE" else "text/javascript")
