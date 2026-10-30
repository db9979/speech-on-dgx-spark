#!/usr/bin/env python3
"""spark-anker: lets the own Speech-on-DGX-Spark panel reach this server's SSH (Fernzugang → Systeme). Linux, macOS
and Windows (stage 5: the panel's file spark-anker-einrichten.cmd starts it, see below).

    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - einrichten https://<panel>   set up once (asks the code)
    sudo spark-anker entfernen                                                              removes everything again
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - entfernen                  the same without the program
    spark-anker zustand                                                                     set up? which panel?
    curl -fsSL https://<panel>/fernzugang/anker | python3 - hilfe https://<panel>           Spontanhilfe (S3): once
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - bildschirm                 the screen too (stage 4)
    sudo spark-anker bildschirm aus                                                         the screen off again
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - aktualisieren              this program anew (no code)

It calls the panel by itself (WebSocket over TLS, the panel's normal https address, no port opened here; paired at
home, first the panel's own address there for INTERN_S seconds, its certificate pinned, so big files do not go
through a proxy in front of the panel) and passes
bytes only between the panel and this server's own sshd on 127.0.0.1:22. SSH runs end to end between the panel and
sshd: the anchor never sees a password, a key or a command. Only the Python standard library.

Set up (as root, once):
- the pairing code is typed on this terminal (read from /dev/tty, never an argument, an address or a variable, never
  written anywhere); the panel's certificate is checked against the system's authorities, or against the SHA-256
  pinned in the command (the panel at home with its own certificate) — the fingerprint is shown;
- the panel answers with this server's own device key and the panel's public SSH key; the program is fetched once
  more over the same checked connection and compared with the SHA-256 the panel named;
- the user `spark` (made here when it did not exist) gets the panel's key in ~/.ssh/authorized_keys with
  from="127.0.0.1,::1",restrict,pty: only through the anchor, no forwarding, no agent, a terminal. It has no sudo;
  whoever wants one adds it here by hand;
- the system user `spark-anker` runs the anchor (systemd unit spark-anker, hardened: no new privileges, read-only
  system, no home, only its own folder /var/lib/spark-anker writable);
- a second unit (spark-anker-abbau.path, root) watches for the panel's „abbauen“: then `spark-anker entfernen` runs.

On macOS (13 or newer; the same one-liner, /usr/bin/python3 from Apple's command line tools) the same steps go through
launchd and dscl: the hidden user `spark` (number below 500, home /var/spark) and `_sparkanker`, the jobs
/Library/LaunchDaemons/de.speech-spark.anker.plist and …anker-abbau.plist (WatchPaths), the program in
/Library/Application Support/SparkAnker, the settings in /Library/Preferences/SparkAnker. When Entfernte Anmeldung
(Remote Login) was off, the anchor switches it on only for itself: /etc/ssh/sshd_config.d/000-spark-anker.conf
(AllowUsers spark@127.0.0.1, no passwords) and the list „nur diese Benutzer“ with spark alone; removing switches it
off again. When it was on, spark joins an existing list and nothing else of sshd changes. Missing host keys are made
with `ssh-keygen -A`.

The screen (stage 4, `bildschirm`, as root, after `einrichten`): the anchor looks at the graphical session and sets
up what fits, always only on 127.0.0.1 and with a random password the panel makes and keeps in its vault:
- X11: x11vnc, started by systemd only when the panel opens the screen (socket spark-anker-bild on 127.0.0.1:5930,
  password file /etc/spark-anker/bild.pw, root only); x11vnc is installed with apt when it is missing;
- GNOME on Wayland: gnome-remote-desktop as RDP (`grdctl --system`, its own self-signed certificate, the user
  spark-bild with that password); RDP listens on port 3389 like GNOME always does;
- other Wayland desktops (wlroots: Sway, Hyprland …): wayvnc in the user's session (a user unit, 127.0.0.1:5930);
- macOS: the built-in Bildschirmfreigabe on port 5900 (switched on by the person; the macOS user and password are
  asked in the panel for every session and never stored).
The anchor then opens channels to that one port too (the panel asks with „ziel“: „bild“), never to another address.
`bildschirm aus` and `entfernen` take it all away again.

Webdienste (1.6.0): the panel asks for a channel „ziel“: „web“ with an IP address and a port; the anchor opens it only
by its own rules (web_ziel), whatever the panel asks: loopback always, the private ranges only when the panel names
„Netz dahinter“ for this system, never link-local, multicast, the metadata address or the panel's own address, never
a name (nothing is resolved). Each such channel has its own flow control (WEB_FENSTER bytes on the way, then „mehr“).
„ports“ lists the listening TCP ports reached through loopback with program names where this user may see them, and
whether HTTP, HTTPS or something else answers (ports_report); never an address, a path or content. The panel's key in
authorized_keys keeps `restrict`: no SSH forwarding is needed for it.

On Windows (10 or 11, 64-bit; stage 5) the panel's file spark-anker-einrichten.cmd (fernwindows.py, as Administrator)
adds OpenSSH Server when it is missing, unpacks python.org's embeddable Python (PY_EMBED: version and SHA-256, the one
source) to %ProgramFiles%/SparkAnker/python-<version> for this program only and runs `einrichten <panel> --token -`
with its one-time key on stdin (no code typed; the panel then waits for the admin's „Bestätigen“). The same steps then
go through sc.exe, reg, icacls, schtasks and PowerShell: sshd only on 127.0.0.1 without passwords, AllowUsers
spark@127.0.0.1, PowerShell as its shell and its firewall rule off, all only when sshd did not run before (else only a
marked block „Match User spark“); the user spark (no Administrator, a random password made and forgotten inside
PowerShell, hidden from the sign-in screen; in „OpenSSH Users“ when sshd_config names AllowGroups) with the panel's
line in %ProgramData%/SparkAnker/authorized_keys (owned by SYSTEM); the
task SparkAnker (this program as LOCAL SERVICE) and SparkAnker-Waechter (SYSTEM: „abbauen“ and „aktualisieren“ like
the root units); „Spark Anker“ under Settings, Apps to remove it. Removing puts sshd, its shell and firewall rule back
as they were and takes user, tasks, settings, program and its Python away (the folder with the running Python, and the
profile of spark Windows holds after an SSH session, through a one-off SYSTEM task: right after this process, else at
the next start). Not yet on Windows: `bildschirm` and `hilfe`.

Spontanhilfe S3 (`hilfe`, never as root, nothing set up): the person types the number and her first name on this
terminal, the program opens WSS /api/hilfe/shell (no key, no Origin) and waits. When the admin accepts, it asks once
more („j“); only then her own shell runs in a PTY with her rights, its output goes to the panel and to this terminal,
the admin's keys (and hers) into it. Strg+C, „Beenden“ in the panel, the session clock or the Notaus end it: the shell
gets SIGHUP, the terminal is as it was, and nothing is left behind (no file, no user, no service).

Updating (since 1.3.0): „Aktualisieren“ in the panel sends the new version, its SHA-256 and an Ed25519 signature of
both over the channel. The anchor fetches the program only from its own panel (the same checked or pinned TLS), checks
the SHA-256 and the signature against the panel's signing key pinned at pairing (or by `aktualisieren`), takes only a
newer version, and leaves it in its folder with the flag „aktualisieren“. A root unit (spark-anker-update.path, on a
Mac the launchd job …anker-update) checks it all again, keeps the program before, swaps it atomically, writes the
units of the new one and restarts the anchor; when the new one has not come back to the panel within 60 seconds, the
one before is back. The pairing (device key, the panel's SSH key, host key) stays as it is. An anchor before 1.3.0
gets the same with the one line `aktualisieren` (as root, no code): it replaces program and units in place, keeps keys
and pairing and pins the signing key.

Removing (`entfernen`, or „Entfernen“ in the panel): stops and deletes both units, the program, the configuration,
the anchor's folder, the user spark-anker, the panel's line in authorized_keys and the user spark with its home when
the anchor made it; then it tells the panel (best effort) so it forgets this server too.
"""
import argparse
import ast
import base64
import contextlib
import getpass
import hashlib
import hmac
import http.client
import io
import ipaddress
import json
import os
import platform
import queue
import re
import secrets
import select
import shutil
import signal
import socket
import ssl
import stat
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import zipfile

try:
    import pwd
except ImportError:      # Windows: no passwd database (the anchor asks `net user` there)
    pwd = None

VERSION = "1.6.0"
LIB = "/usr/local/lib/spark-anker"
PROG = LIB + "/spark-anker.py"
BIN = "/usr/local/bin/spark-anker"
ETC = "/etc/spark-anker"
CONF = ETC + "/anker.json"
VAR = "/var/lib/spark-anker"
FLAG = VAR + "/abbauen"
UNITS = ("/etc/systemd/system/spark-anker.service", "/etc/systemd/system/spark-anker-abbau.path",
         "/etc/systemd/system/spark-anker-abbau.service", "/etc/systemd/system/spark-anker-update.path",
         "/etc/systemd/system/spark-anker-update.service")
USER = "spark"            # the login the panel uses (its key only, only from 127.0.0.1)
RUNNER = "spark-anker"    # the system user the anchor runs as
SSHD = ("127.0.0.1", 22)
HOSTKEY = "/etc/ssh/ssh_host_ed25519_key.pub"
URL = re.compile(r"https://([A-Za-z0-9.\-]{1,253}|\[[0-9A-Fa-f:.]{2,45}\])(?::(\d{1,5}))?/?")
FP = re.compile(r"[0-9a-f]{64}")
# the panel's own address inside the home net (named by the panel at pairing from there): an IPv4 address, a port
INTERN = re.compile(r"https://(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):(\d{1,5})")
INTERN_S = 3              # seconds the anchor tries the address inside the home net before the normal one
MAX_MSG = 64 * 1024       # the panel takes no bigger message
CHUNK = 32 * 1024
PING_S = 25               # keeps the reverse proxy from closing a quiet connection
MARK = "spark-fernzugang-"  # the comment of the panel's line in authorized_keys
BILD_PORT = 5930          # x11vnc and wayvnc: only on 127.0.0.1
BILD = {"x11vnc": BILD_PORT, "wayvnc": BILD_PORT, "grd": 3389, "mac": 5900}   # the screen's one local port per kind
# Webdienste (1.6.0): channels „ziel: web“ to one port of a web service, numbered 64 and up (one byte: at most WEB_MAX)
WEB_MAX = 250
WEB_ERSTER = 64           # the shells, files and the screen keep 1..63
WEB_FENSTER = 256 * 1024  # bytes per web channel and direction on the way before the other side says „mehr“
WEB_MEHR = 64 * 1024      # „mehr“ goes back after this many bytes taken, or when all that waited is written
WEB_OPEN_S = 5            # connecting to the service at most this long
WEB_PORTS = 64            # listening ports reported at most („Gefunden“)
NETZ_PRIVAT = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))
METADATA = ipaddress.ip_address("169.254.169.254")
BILD_PW = ETC + "/bild.pw"
BILD_UNITS = ("/etc/systemd/system/spark-anker-bild.socket", "/etc/systemd/system/spark-anker-bild@.service")
WAYVNC_UNIT = "/etc/systemd/user/spark-anker-wayvnc.service"
WAYVNC_CONF = ETC + "/wayvnc.conf"
RDP_USER = "spark-bild"
RDP_FILES = (ETC + "/rdp.key", ETC + "/rdp.crt")
WORD = re.compile(r"[^A-Za-z0-9._\- ()/+]")
VER = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}")
PROG_MAX = 1024 * 1024    # the program is far smaller; nothing bigger is read
UPDATE_S = 60             # a new version that has not reached the panel by then: the one before is back
SIGN_TEXT = "spark-anker {version} {sha256}"   # what the panel's signing key signs (Ed25519)

UNIT_RUN = """[Unit]
Description=Spark-Anker (Fernzugang des Spark-Panels zu diesem sshd)
After=network-online.target
Wants=network-online.target

[Service]
User=spark-anker
Group=spark-anker
ExecStart=/usr/bin/python3 -I /usr/local/lib/spark-anker/spark-anker.py lauf
Restart=always
RestartSec=10
StateDirectory=spark-anker
StateDirectoryMode=0700
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
ProtectProc=invisible
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
"""
UNIT_BILD_SOCKET = """[Unit]
Description=Spark-Anker: Bildschirm (x11vnc nur auf 127.0.0.1, erst wenn das Panel ihn öffnet)

[Socket]
ListenStream=127.0.0.1:5930
Accept=yes
MaxConnections=2

[Install]
WantedBy=sockets.target
"""
# x11vnc finds the display of the person signed in (-find, as root: her X authority) and reads the password file;
# no PrivateTmp/ProtectHome: it needs /tmp/.X11-unix and that authority
UNIT_BILD = """[Unit]
Description=Spark-Anker: x11vnc für eine Bildschirm-Sitzung des Panels

[Service]
ExecStart=/usr/bin/x11vnc -inetd -find -passwdfile /etc/spark-anker/bild.pw -shared -noxdamage -nolookup -quiet
StandardInput=socket
StandardError=journal
NoNewPrivileges=yes
"""
UNIT_WAYVNC = """[Unit]
Description=Spark-Anker: wayvnc nur auf 127.0.0.1 für das Panel
ConditionUser={user}
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/wayvnc -C /etc/spark-anker/wayvnc.conf
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical-session.target
"""
WAYVNC_TEXT = "address=127.0.0.1\nport={port}\nenable_auth=true\nrelax_encryption=true\nusername=spark\npassword={pw}\n"
UNIT_PATH = """[Unit]
Description=Spark-Anker: Abbau, wenn das Panel ihn verlangt

[Path]
PathExists=/var/lib/spark-anker/abbauen

[Install]
WantedBy=multi-user.target
"""
UNIT_ABBAU = """[Unit]
Description=Spark-Anker abbauen (alles entfernen, was er eingerichtet hat)

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/lib/spark-anker/spark-anker.py entfernen --vom-panel
"""
UNIT_UPDATE_PATH = """[Unit]
Description=Spark-Anker: neue Version einspielen, wenn der Anker eine geprüfte geladen hat

[Path]
PathExists=/var/lib/spark-anker/aktualisieren

[Install]
WantedBy=multi-user.target
"""
UNIT_UPDATE = """[Unit]
Description=Spark-Anker aktualisieren (prüfen, tauschen, neu starten, sonst zurück)

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I /usr/local/lib/spark-anker/spark-anker.py aktualisieren --vom-anker
"""


class Fehler(Exception):
    pass


def say(text):
    try:
        print(f"spark-anker: {text}", flush=True)
    except UnicodeEncodeError:                 # a console page without „→“ (Windows cp1252 through a pipe)
        print(f"spark-anker: {text}".encode("ascii", "replace").decode(), flush=True)


def here(root, path):
    """path below root (/ normally; a temporary folder in the tests). A Windows path keeps its drive only at the real
    root: below a temporary folder „C:“ is dropped (never a real path when the tests pass a root)."""
    if root != "/" and re.match(r"[A-Za-z]:[/\\]", path):
        path = path[2:].replace("\\", "/")
    return os.path.join(root, path.lstrip("/"))


# ---------------------------------------------------------------- TLS to the panel (checked before anything goes out)
def base_url(url):
    m = URL.fullmatch(str(url or "").strip())
    if not m:
        raise Fehler("Adresse: https://name oder https://name:port des Panels")
    return f"https://{m.group(1)}" + (f":{m.group(2)}" if m.group(2) and m.group(2) != "443" else "")


# where the system keeps its authorities when Python brings none of its own (python.org's Python on a Mac without
# „Install Certificates“; some Linux builds): only files of the system, verification is never switched off
CA_FILES = {"Darwin": ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"),
            "Linux": ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/ca-bundle.pem",
                      "/etc/ssl/cert.pem")}


def authorities(system=None, root="/"):
    """The default context; when it holds no authority, the system's bundle file is added."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0):
        return ctx
    for p in CA_FILES.get(system or platform.system(), CA_FILES["Linux"]):
        path = here(root, p)
        if os.path.isfile(path):
            try:
                ctx.load_verify_locations(cafile=path)
            except (OSError, ssl.SSLError):
                continue
            if ctx.cert_store_stats().get("x509_ca", 0):
                break
    return ctx


def tls_connect(base, fp, timeout=20):
    """A TLS socket to the panel: with fp exactly that certificate (SHA-256 of the DER), else checked against the
    system's authorities and the name. Nothing is sent before the check."""
    u = urllib.parse.urlsplit(base)
    host = u.hostname
    if fp:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx = authorities()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    raw = socket.create_connection((host, u.port or 443), timeout=timeout)
    s = ctx.wrap_socket(raw, server_hostname=host)
    got = hashlib.sha256(s.getpeercert(binary_form=True) or b"").hexdigest()
    if fp and not hmac.compare_digest(got, fp):
        s.close()
        raise Fehler("Das Zertifikat des Panels passt nicht zum Fingerabdruck. Nichts gesendet.")
    return s, got


class _Conn(http.client.HTTPSConnection):
    def __init__(self, base, fp, timeout=20):
        u = urllib.parse.urlsplit(base)
        super().__init__(u.hostname, u.port or 443, timeout=timeout)
        self._base, self._fp = base, fp

    def connect(self):
        self.sock, _ = tls_connect(self._base, self._fp, self.timeout)


def http_call(base, fp, method, path, body=None, key=None, timeout=20):
    """(status, bytes) of one request to the panel."""
    c = _Conn(base, fp, timeout)
    head = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": f"spark-anker/{VERSION}"}
    if key:
        head["Authorization"] = f"Bearer {key}"
    try:
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=head)
        r = c.getresponse()
        return r.status, r.read(2 * 1024 * 1024)
    finally:
        c.close()


# ---------------------------------------------------------------- WebSocket client (RFC 6455, only what is needed)
class WS:
    def __init__(self, sock):
        self.sock = sock
        self.lock = threading.Lock()

    @classmethod
    def open(cls, base, fp, path, key, timeout=20):
        s, _ = tls_connect(base, fp, timeout)
        u = urllib.parse.urlsplit(base)
        nonce = base64.b64encode(secrets.token_bytes(16)).decode()
        host = u.hostname + (f":{u.port}" if u.port else "")
        auth = f"Authorization: Bearer {key}\r\n" if key else ""     # the Spontanhilfe has no key (S3)
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n{auth}"
               f"User-Agent: spark-anker/{VERSION}\r\n\r\n")
        s.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            part = s.recv(4096)
            if not part or len(head) > 16384:
                s.close()
                raise Fehler("keine Antwort")
            head += part
        top, _, rest = head.partition(b"\r\n\r\n")
        lines = top.decode("latin-1").split("\r\n")
        status = lines[0].split(" ")[1] if len(lines[0].split(" ")) > 1 else "?"
        if status != "101":
            s.close()
            raise Fehler(f"Panel antwortet {status}")
        want = base64.b64encode(hashlib.sha1((nonce + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        got = next((ln.split(":", 1)[1].strip() for ln in lines[1:] if ln.lower().startswith("sec-websocket-accept:")), "")
        if not hmac.compare_digest(got, want):
            s.close()
            raise Fehler("kein WebSocket")
        s.settimeout(None)
        ws = cls(s)
        ws.buf, ws.part = rest, None
        return ws

    def send(self, data, op):
        head = bytearray([0x80 | op])
        n = len(data)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = secrets.token_bytes(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(data)) if n < 4096 else _mask(data, mask)
        with self.lock:
            self.sock.sendall(bytes(head) + mask + body)

    def send_json(self, d):
        self.send(json.dumps(d).encode(), 1)

    def feed(self):
        """Reads what the socket has (one TLS record at least); False when the panel closed it."""
        part = self.sock.recv(65536)
        if not part:
            return False
        self.buf += part
        if len(self.buf) > 4 * (MAX_MSG + 16):
            raise Fehler("zu viel auf einmal")
        return True

    def frame(self):
        """The next whole message (opcode, payload) from the buffer, or None; pings are answered here."""
        while True:
            buf = self.buf
            if len(buf) < 2:
                return None
            b1, b2 = buf[0], buf[1]
            op, n, i = b1 & 0x0F, b2 & 0x7F, 2
            if n == 126:
                if len(buf) < 4:
                    return None
                n, i = struct.unpack("!H", buf[2:4])[0], 4
            elif n == 127:
                if len(buf) < 10:
                    return None
                n, i = struct.unpack("!Q", buf[2:10])[0], 10
            if n > MAX_MSG + 16:
                raise Fehler("Nachricht zu groß")
            mask = b""
            if b2 & 0x80:
                mask, i = buf[i:i + 4], i + 4
            if len(buf) < i + n:
                return None
            data, self.buf = buf[i:i + n], buf[i + n:]
            if mask:
                data = _mask(data, mask)
            if op == 9:
                self.send(data, 10)
                continue
            if op == 10:
                continue
            if op == 8:
                raise EOFError
            if op in (1, 2):
                self.part = (op, [data])
            elif op == 0 and getattr(self, "part", None):
                self.part[1].append(data)
            else:
                continue
            if b1 & 0x80:
                first, parts = self.part
                self.part = None
                return first, b"".join(parts)

    def close(self):
        try:
            self.send(struct.pack("!H", 1000), 8)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def _mask(data, mask):
    m = int.from_bytes((mask * (len(data) // 4 + 1))[:len(data)], "big")
    return (int.from_bytes(data, "big") ^ m).to_bytes(len(data), "big") if data else b""


# ---------------------------------------------------------------- updating: Ed25519 and the checks
# Ed25519 verification after RFC 8032 (5.1.7, its reference code): Python's standard library has none, and the anchor
# brings nothing else along. Only public data goes in (the panel's public key, the program, the signature).
_EP = 2 ** 255 - 19
_EL = 2 ** 252 + 27742317777372353535851937790883648493
_ED = -121665 * pow(121666, _EP - 2, _EP) % _EP
_EI = pow(2, (_EP - 1) // 4, _EP)


def _ed_add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    pa, pb = (y1 - x1) * (y2 - x2) % _EP, (y1 + x1) * (y2 + x2) % _EP
    pc, pd = t1 * 2 * _ED * t2 % _EP, z1 * 2 * z2 % _EP
    e, f, g, h = pb - pa, pd - pc, pd + pc, pb + pa
    return e * f % _EP, g * h % _EP, f * g % _EP, e * h % _EP


def _ed_mul(k, pt):
    q = (0, 1, 1, 0)
    while k > 0:
        if k & 1:
            q = _ed_add(q, pt)
        pt = _ed_add(pt, pt)
        k >>= 1
    return q


def _ed_same(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _EP == 0 and (a[1] * b[2] - b[1] * a[2]) % _EP == 0


def _ed_x(y, sign):
    if y >= _EP:
        return None
    x2 = (y * y - 1) * pow(_ED * y * y + 1, _EP - 2, _EP)
    if x2 % _EP == 0:
        return None if sign else 0
    x = pow(x2, (_EP + 3) // 8, _EP)
    if (x * x - x2) % _EP:
        x = x * _EI % _EP
    if (x * x - x2) % _EP:
        return None
    return _EP - x if (x & 1) != sign else x


def _ed_point(b):
    y = int.from_bytes(b, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _ed_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _EP)


_EGY = 4 * pow(5, _EP - 2, _EP) % _EP
_EG = (_ed_x(_EGY, 0), _EGY, 1, _ed_x(_EGY, 0) * _EGY % _EP)


def ed25519_ok(pub, msg, sig):
    """True only for a valid Ed25519 signature of msg by the 32-byte public key pub."""
    if not (isinstance(pub, bytes) and isinstance(sig, bytes)) or len(pub) != 32 or len(sig) != 64:
        return False
    a, r = _ed_point(pub), _ed_point(sig[:32])
    k = int.from_bytes(sig[32:], "little")
    if a is None or r is None or k >= _EL:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), "little") % _EL
    return _ed_same(_ed_mul(k, _EG), _ed_add(r, _ed_mul(h, a)))


def _ver(v):
    return tuple(int(x) for x in v.split(".")) if isinstance(v, str) and VER.fullmatch(v) else None


def newer(a, b):
    """Version a is newer than b (never a step back)."""
    va, vb = _ver(a), _ver(b)
    return bool(va) and (vb is None or va > vb)


def prog_version(data):
    m = re.search(rb'^VERSION = "(\d{1,3}\.\d{1,3}\.\d{1,3})"$', data or b"", re.M)
    return m.group(1).decode() if m else ""


def _b64(text, n):
    try:
        raw = base64.b64decode(str(text or ""), validate=True)
    except ValueError:
        return None
    return raw if len(raw) == n else None


def pruefen(prog, version, sha, sig, pub):
    """The checks of a new program, before anything changes: "" when all hold, else the fixed word of the first that
    fails (size, SHA-256, the version in it, the signature of the panel's key)."""
    if not isinstance(prog, bytes) or not prog or len(prog) > PROG_MAX:
        return "gross"
    got = hashlib.sha256(prog).hexdigest()
    if not hmac.compare_digest(got, str(sha or "")):
        return "pruefsumme"
    if prog_version(prog) != version:
        return "version"
    key, s = _b64(pub, 32), _b64(sig, 64)
    if key is None or s is None or not ed25519_ok(key, SIGN_TEXT.format(version=version, sha256=got).encode(), s):
        return "signatur"
    return ""


def read_plain(path, cap):
    """A regular file, never through a symlink, at most cap bytes (root reads what the anchor's user left)."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            raise OSError("not a plain file")
        with os.fdopen(fd, "rb") as f:
            fd = None
            data = f.read(cap + 1)
    finally:
        if fd is not None:
            os.close(fd)
    if len(data) > cap:
        raise OSError("too big")
    return data


def write_atomic(path, data, mode):
    """Written beside it and moved over it in one step: the program is never half there."""
    tmp = f"{path}.neu{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


# ---------------------------------------------------------------- running (systemd unit or launchd job spark-anker)
def load(root="/", s=None):
    try:
        with open(here(root, (s or Ctx().s).conf)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("url") and d.get("key") else None


def os_name(s=None):
    if (s or Ctx().s) is MAC:
        return WORD.sub("", "macOS " + platform.mac_ver()[0]).strip()[:40]
    if (s or Ctx().s) is WIN:
        edition = getattr(platform, "win32_edition", lambda: "")() or ""
        return WORD.sub("", f"Windows {platform.release()} {edition}").strip()[:40]
    try:
        with open("/etc/os-release") as f:
            m = re.search(r'^PRETTY_NAME="?([^"\n]*)', f.read(), re.M)
        name = m.group(1) if m else platform.system()
    except OSError:
        name = platform.system()
    return WORD.sub("", name)[:40]


def web_ziel(m, peer=""):
    """(host, port) a web channel may reach, else None: its own rules, whatever the panel asks. Only an IP address
    (never a name, so nothing is resolved and nothing slips through a DNS answer), port 1 to 65535; loopback always;
    the private ranges (NETZ_PRIVAT) only with „netz“ (the panel's „Netz dahinter“ for this system); never link-local,
    multicast, unspecified, reserved, the metadata address 169.254.169.254 or the panel's own address (peer)."""
    host, port = m.get("host"), m.get("port")
    if not isinstance(host, str) or len(host) > 45 or not isinstance(port, int) or isinstance(port, bool) \
            or not 1 <= port <= 65535:
        return None
    try:
        ip = ipaddress.ip_address(host[1:-1] if host.startswith("[") and host.endswith("]") else host)
    except ValueError:
        return None
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if ip == METADATA or ip.is_link_local or ip.is_multicast or ip.is_unspecified or \
            (ip.is_reserved and not ip.is_loopback):     # ::1 lies in IPv6's reserved ::/8
        return None
    with contextlib.suppress(ValueError):
        p = ipaddress.ip_address(str(peer or "").split("%")[0]) if peer else None
        if p is not None and (getattr(p, "ipv4_mapped", None) or p) == ip:
            return None
    if ip.is_loopback:
        return str(ip), port
    if m.get("netz") is True and any(ip in n for n in NETZ_PRIVAT if n.version == ip.version):
        return str(ip), port
    return None


def _hex_ip(h):
    b = bytes.fromhex(h)
    if len(b) == 4:
        return socket.inet_ntop(socket.AF_INET, b[::-1])
    return socket.inet_ntop(socket.AF_INET6, b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4)))


def _lokal(host):
    """A listening address reached through 127.0.0.1 or ::1 (any address, or loopback): the one to probe, else None."""
    h = host.strip("[]").split("%")[0]
    if h in ("0.0.0.0", "*") or h.startswith("127.") or h in ("::ffff:127.0.0.1", "::ffff:0.0.0.0"):
        return "127.0.0.1"
    if h in ("::", "::1"):
        return "::1"
    return None


def _listen_linux(root="/"):
    """{port: (probe host, program)} from /proc/net/tcp{,6} (no program needed, no root: a program name only when this
    user may see the process)."""
    out, inodes = {}, {}
    for name in ("proc/net/tcp", "proc/net/tcp6"):
        try:
            with open(os.path.join(root, name)) as f:
                lines = f.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if len(f) < 10 or f[3] != "0A":
                continue
            addr, _, port = f[1].partition(":")
            try:
                host, port = _lokal(_hex_ip(addr)), int(port, 16)
            except (ValueError, OSError):
                continue
            if host and port not in out:
                out[port] = (host, "")
                inodes[f[9]] = port
    with contextlib.suppress(OSError):
        for pid in os.listdir(os.path.join(root, "proc")):
            if not pid.isdigit():
                continue
            fds = os.path.join(root, "proc", pid, "fd")
            try:
                links = [os.readlink(os.path.join(fds, x)) for x in os.listdir(fds)]
            except OSError:
                continue
            hits = [inodes[x[8:-1]] for x in links if x.startswith("socket:[") and x[8:-1] in inodes]
            if hits:
                try:
                    with open(os.path.join(root, "proc", pid, "comm")) as f:
                        comm = f.read().strip()
                except OSError:
                    comm = ""
                for port in hits:
                    out[port] = (out[port][0], comm)
    return out


def _listen_text(text, kind):
    """{port: (probe host, program)} from `netstat -an -p tcp` (macOS) or `netstat -ano` (Windows; programs from
    `tasklist`, passed in as {pid: name} under the key "pids")."""
    out = {}
    pids = kind.get("pids", {}) if isinstance(kind, dict) else {}
    win = isinstance(kind, dict)
    for line in text.splitlines():
        f = line.split()
        if win:
            if len(f) < 5 or f[0] != "TCP" or f[3] != "LISTENING":
                continue
            host, _, port = f[1].rpartition(":")
            prog = pids.get(f[4], "")
        else:
            if len(f) < 6 or not f[0].startswith("tcp") or f[5] != "LISTEN":
                continue
            host, _, port = f[3].rpartition(".")
            prog = ""
        h = _lokal(host)
        if h and port.isdigit() and int(port) not in out:
            out[int(port)] = (h, prog)
    return out


def listening(s=None, run=None):
    """The listening TCP ports of this system reached through loopback, at most WEB_PORTS: [(port, host, program)]."""
    s = s or Ctx().s
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout)
    try:
        if s is WIN:
            pids = {}
            for line in run(["tasklist", "/FO", "CSV", "/NH"]).splitlines():
                f = [x.strip('"') for x in line.split('","')]
                if len(f) >= 2 and f[1].isdigit():
                    pids[f[1]] = f[0]
            found = _listen_text(run(["netstat", "-ano", "-p", "TCP"]) + "\n" + run(["netstat", "-ano", "-p", "TCPv6"]),
                                 {"pids": pids})
        elif s is MAC:
            found = _listen_text(run(["netstat", "-an", "-p", "tcp"]), "mac")
        else:
            found = _listen_linux()
    except (OSError, subprocess.SubprocessError, ValueError):
        found = {}
    return [(p, h, WORD.sub("", prog)[:40]) for p, (h, prog) in sorted(found.items())][:WEB_PORTS]


def _server_word(head):
    """The word of a „Server:“ header (nginx, Caddy …), letters only, as the name when the program is unknown."""
    m = re.search(rb"\r\nserver:[ \t]*([^\r\n/ ]{1,40})", head, re.I)
    return WORD.sub("", m.group(1).decode("latin-1"))[:40] if m else ""


def port_art(host, port, timeout=0.6):
    """(„https“, „http“ or „tcp“, the „Server:“ word or ""): what answers there (a server that talks first is no web
    server; then TLS; then a plain HEAD). Only on this system's own loopback."""
    def conn():
        c = socket.create_connection((host, port), timeout=timeout)
        c.settimeout(timeout)
        return c
    head = b"HEAD / HTTP/1.0\r\nHost: " + (b"[::1]" if ":" in host else host.encode()) + b"\r\n\r\n"

    def answer(c):
        c.sendall(head)
        got = b""
        with contextlib.suppress(socket.timeout, OSError, ssl.SSLError):
            while len(got) < 4096 and b"\r\n\r\n" not in got:
                part = c.recv(4096)
                if not part:
                    break
                got += part
        return got
    try:
        c = conn()
    except OSError:
        return "tcp", ""
    try:
        try:
            if c.recv(1, socket.MSG_PEEK):
                return "tcp", ""          # SSH, SMTP, a database: it greets first
        except (socket.timeout, OSError):
            pass
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with ctx.wrap_socket(c, server_hostname=None) as t:
                return "https", _server_word(answer(t))
        except (ssl.SSLError, OSError):
            pass
    finally:
        with contextlib.suppress(OSError):
            c.close()
    try:
        c = conn()
        got = answer(c)
        c.close()
        return ("http", _server_word(got)) if got.startswith(b"HTTP/") else ("tcp", "")
    except OSError:
        return "tcp", ""


def ports_report(s=None):
    """„Gefunden“ for the panel: ports, program names (or the „Server:“ word) and the kind only (never an address, a
    path or content)."""
    out = []
    for p, h, prog in listening(s):
        art, word = port_art(h, p)
        out.append({"port": p, "prog": prog or word, "art": art})
    return out


class Lauf:
    """One connection to the panel: channels to the own sshd, nothing else. One thread for everything (a TLS socket
    is never read and written from two threads at once)."""

    def __init__(self, ws, bild="", conf=None, ctx=None):
        self.ws = ws
        self.bild = bild if bild in BILD else ""   # the screen's kind (`bildschirm`), its one port in BILD
        self.kanaele = {}      # n -> socket to the own sshd (or the screen's port, or a web service)
        self.web = {}          # n -> {"raus": bytes the panel has not taken yet, "rein": bytearray to the service,
                               #       "genommen": written since the last „mehr“} (the Webdienste' own flow control)
        self.conf = conf or {}
        self.ctx = ctx or Ctx()
        self.antworten = queue.SimpleQueue()   # what a helper thread found („ports“), sent by the one thread
        self.ports_laeuft = False
        try:
            self.peer = ws.sock.getpeername()[0]
        except (OSError, AttributeError, IndexError, TypeError):
            self.peer = ""

    def _update(self, m):
        """„Aktualisieren“ from the panel: fetch the program from the own panel only (the same checked TLS), check it
        (pruefen) and leave it with the flag for the root unit; a fixed word back to the panel either way."""
        v, conf, s = str(m.get("version") or ""), self.conf, self.ctx.s
        if not conf.get("sign_pub"):
            return "kein_schluessel"
        if not newer(v, VERSION):
            return "nicht_neuer"
        try:
            status, prog = http_call(conf["url"], conf.get("fp") or "", "GET", "/fernzugang/anker", timeout=30)
        except (OSError, Fehler, ssl.SSLError, http.client.HTTPException):
            return "laden"
        if status != 200:
            return "laden"
        why = pruefen(prog, v, m.get("sha256"), m.get("sig"), conf["sign_pub"])
        if why:
            return why
        try:
            write_atomic(self.ctx.path(s.var + "/neu.py"), prog, 0o600)
            write_atomic(self.ctx.path(s.var + "/neu.json"), json.dumps(
                {"version": v, "sha256": m.get("sha256"), "sig": m.get("sig")}).encode(), 0o600)
            write_atomic(self.ctx.path(s.var + "/aktualisieren"), b"1\n", 0o600)   # the root unit takes it from here
        except OSError:
            return "schreiben"
        return "laeuft"

    def _stand(self):
        """What the root unit wrote after the last update (ok, zurueck or why not), for the panel's „hallo“."""
        try:
            d = json.loads(read_plain(self.ctx.path(self.ctx.s.lib + "/update.json"), 4096))
        except (OSError, ValueError):
            return {}
        return {k: d[k] for k in ("stand", "version", "t") if isinstance(d, dict) and isinstance(d.get(k), (str, int))}

    def _close(self, n, tell):
        s = self.kanaele.pop(n, None)
        self.web.pop(n, None)
        if s is None:
            return
        try:
            s.close()
        except OSError:
            pass
        if tell:
            self.ws.send_json({"typ": "zu", "kanal": n})

    def _control(self, m):
        n = m.get("kanal")
        if m.get("typ") == "abbauen":
            return "abbauen"
        if m.get("typ") == "update":
            self.ws.send_json({"typ": "update_stand", "stand": self._update(m)})
            return None
        if m.get("typ") == "mehr" and isinstance(n, int) and n in self.web and isinstance(m.get("n"), int):
            w = self.web[n]
            w["raus"] = max(0, w["raus"] - m["n"])
            return None
        if m.get("typ") == "ports":
            if not self.ports_laeuft:
                self.ports_laeuft = True
                threading.Thread(target=self._ports, daemon=True).start()
            return None
        if m.get("typ") == "auf" and m.get("ziel") == "web" and isinstance(n, int) and WEB_ERSTER <= n <= WEB_MAX \
                and n not in self.kanaele:
            target = web_ziel(m, self.peer)        # its own rules, whatever the panel asked
            if target is None:
                self.ws.send_json({"typ": "fehler", "kanal": n, "grund": "ziel"})
                return None
            try:
                s = socket.create_connection(target, timeout=WEB_OPEN_S)
                s.setblocking(False)
            except OSError:
                self.ws.send_json({"typ": "fehler", "kanal": n, "grund": "dienst"})
                return None
            self.kanaele[n] = s
            self.web[n] = {"raus": 0, "rein": bytearray(), "genommen": 0}
            self.ws.send_json({"typ": "offen", "kanal": n})
            return None
        if m.get("typ") == "auf" and isinstance(n, int) and 1 <= n < WEB_ERSTER and n not in self.kanaele:
            target = SSHD
            if m.get("ziel") == "bild":          # the screen: only its one port on 127.0.0.1, only when set up
                if not self.bild:
                    self.ws.send_json({"typ": "fehler", "kanal": n})
                    return None
                target = ("127.0.0.1", BILD[self.bild])
            try:
                s = socket.create_connection(target, timeout=10)   # only these, never another address
                s.settimeout(None)
            except OSError:
                self.ws.send_json({"typ": "fehler", "kanal": n})
                return None
            self.kanaele[n] = s
            self.ws.send_json({"typ": "offen", "kanal": n})
        elif m.get("typ") == "zu" and isinstance(n, int):
            self._close(n, False)
        return None

    def _ports(self):
        try:
            liste = ports_report(self.ctx.s)
        except Exception:
            liste = []
        self.antworten.put({"typ": "ports", "liste": liste})

    def _web_rein(self, n, data):
        """Bytes of the panel for a web service: kept in order, written as the service takes them; more than the
        window at once is a broken panel and closes the channel."""
        w = self.web[n]
        w["rein"] += data
        if len(w["rein"]) > WEB_FENSTER:
            self._close(n, True)
            return
        self._web_schreiben(n)

    def _web_schreiben(self, n):
        w, s = self.web.get(n), self.kanaele.get(n)
        if w is None or s is None:
            return
        try:
            k = s.send(w["rein"]) if w["rein"] else 0
        except (BlockingIOError, InterruptedError):
            k = 0
        except OSError:
            self._close(n, True)
            return
        del w["rein"][:k]
        w["genommen"] += k
        if w["genommen"] and (w["genommen"] >= WEB_MEHR or not w["rein"]):
            self.ws.send_json({"typ": "mehr", "kanal": n, "n": w["genommen"]})
            w["genommen"] = 0

    def run(self):
        self.ws.send_json({"typ": "hallo", "os": os_name(), "version": VERSION, "bild": self.bild,
                           "update": self._stand(), "web": 1})
        last = time.monotonic()
        try:
            while True:
                while True:     # whole messages already read
                    got = self.ws.frame()
                    if got is None:
                        break
                    op, data = got
                    if op == 2:
                        s = self.kanaele.get(data[0]) if data else None
                        if s is not None and data[0] in self.web:
                            self._web_rein(data[0], data[1:])
                        elif s is not None:
                            try:
                                s.sendall(data[1:])
                            except OSError:
                                self._close(data[0], True)
                        continue
                    try:
                        m = json.loads(data.decode())
                    except ValueError:
                        continue
                    if isinstance(m, dict) and self._control(m) == "abbauen":
                        return "abbauen"
                if time.monotonic() - last > PING_S:
                    self.ws.send(b"", 9)
                    last = time.monotonic()
                while True:
                    try:
                        self.ws.send_json(self.antworten.get_nowait())
                        self.ports_laeuft = False
                    except queue.Empty:
                        break
                wait = 0 if self.ws.sock.pending() else 1
                lesen = [v for k, v in self.kanaele.items() if k not in self.web or self.web[k]["raus"] < WEB_FENSTER]
                schreiben = [self.kanaele[k] for k, w in self.web.items() if w["rein"] and k in self.kanaele]
                ready, frei, _ = select.select([self.ws.sock, *lesen], schreiben, [], wait)
                for w in frei:
                    n = next((k for k, v in self.kanaele.items() if v is w), None)
                    if n is not None:
                        self._web_schreiben(n)
                if self.ws.sock.pending() and self.ws.sock not in ready:
                    ready.append(self.ws.sock)
                for r in ready:
                    if r is self.ws.sock:
                        if not self.ws.feed():
                            return "zu"
                        continue
                    n = next((k for k, v in self.kanaele.items() if v is r), None)
                    if n is None:
                        continue
                    try:
                        data = r.recv(CHUNK)
                    except (BlockingIOError, InterruptedError):
                        continue
                    except OSError:
                        data = b""
                    if data:
                        if n in self.web:
                            self.web[n]["raus"] += len(data)
                        self.ws.send(bytes([n]) + data, 2)
                    else:
                        self._close(n, True)
        finally:
            for n in list(self.kanaele):
                self._close(n, False)


def intern_ok(v):
    """{"url", "fp"} of the panel inside the home net when the panel named a plain one (always with its certificate
    pinned), else None."""
    if not isinstance(v, dict):
        return None
    url, fp = str(v.get("url") or ""), str(v.get("fp") or "").lower()
    m = INTERN.fullmatch(url)
    if not m or not FP.fullmatch(fp) or not 0 < int(m.group(2)) < 65536 or any(int(x) > 255 for x in m.group(1).split(".")):
        return None
    return {"url": url, "fp": fp}


def verbinden(conf):
    """(WebSocket, "intern" | "extern"): the panel inside the home net first (its own address, its certificate pinned,
    INTERN_S seconds), else the normal address the anchor was set up with."""
    i = intern_ok(conf.get("intern"))
    if i:
        try:
            return WS.open(i["url"], i["fp"], "/api/fernzugang/anker", conf["key"], INTERN_S), "intern"
        except (OSError, EOFError, Fehler, ValueError):
            pass
    return WS.open(conf["url"], conf.get("fp") or "", "/api/fernzugang/anker", conf["key"]), "extern"


def cmd_run(args):
    conf = load()
    if not conf:
        say("nicht eingerichtet")
        return 1
    pause = 5
    while True:
        try:
            ws, wo = verbinden(conf)
            say("mit dem Panel verbunden" + (" (im Heimnetz)" if wo == "intern" else ""))
            pause = 5
            with contextlib.suppress(OSError):       # an update waits for this: the new version reached the panel
                write_atomic(Ctx().path(Ctx().s.var + "/ok"), VERSION.encode(), 0o600)
            if Lauf(ws, str(conf.get("bild") or ""), conf).run() == "abbauen":
                say("das Panel verlangt den Abbau")
                try:
                    with open(Ctx().s.flag, "w") as f:   # spark-anker-abbau.path or the launchd job (root) runs `entfernen`
                        f.write("1\n")
                    ws.send_json({"typ": "abbau_laeuft"})
                except OSError:
                    pass
                ws.close()
                time.sleep(60)
                continue
        except (OSError, EOFError, Fehler, ValueError) as e:
            say(f"getrennt ({type(e).__name__}), neuer Versuch in {pause} s")
        time.sleep(pause)
        pause = min(300, pause * 2)


# ---------------------------------------------------------------- setting up
def tty_line(prompt):
    """A line typed on the terminal (not stdin: stdin is the program itself when it comes through curl)."""
    with open("/dev/tty", "r+") as t:
        t.write(prompt)
        t.flush()
        return t.readline().strip()


def _again(fn, *a):
    """fn(*a), again when a signal interrupted it (EINTR; macOS under `curl | sudo`)."""
    for n in range(5):
        try:
            return fn(*a)
        except Exception as e:     # termios.error is no OSError; both carry errno 4 for EINTR
            code = getattr(e, "errno", None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
            if code != 4 or n == 4:
                raise


def read_code(tty="/dev/tty"):
    """The pairing code, typed on this terminal (never stdin: that is the program itself when it comes through curl),
    echo off on that terminal; SIGTTOU ignored meanwhile (not the foreground group under `curl | sudo`), the
    terminal always as it was afterwards. Without echo control the code is read visibly, with a hint. Windows: the
    console itself, hidden (getpass reads the console there, not stdin)."""
    if os.name == "nt":
        return getpass.getpass("Kopplungs-Code aus dem Panel: ").strip()
    try:
        fd = os.open(tty, os.O_RDWR | getattr(os, "O_NOCTTY", 0))
    except OSError:
        raise Fehler("kein Terminal für den Code: den Befehl aus dem Panel in einem Terminal-Fenster ausführen. "
                     "Es wurde nichts eingerichtet.")
    try:
        import termios
    except ImportError:
        termios = None
    old = handler = None
    try:
        if termios is not None:
            with contextlib.suppress(ValueError, OSError, AttributeError):
                handler = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
            try:
                old = _again(termios.tcgetattr, fd)
                quiet = list(old)
                quiet[3] &= ~termios.ECHO
                _again(termios.tcsetattr, fd, termios.TCSANOW, quiet)
            except (termios.error, OSError):
                old = None
        prompt = "Kopplungs-Code aus dem Panel: " if old else "Kopplungs-Code aus dem Panel (wird angezeigt): "
        _again(os.write, fd, prompt.encode())
        line = b""
        while True:
            ch = _again(os.read, fd, 1)
            if not ch:
                break
            if ch in (b"\n", b"\r"):
                line += b"\n"
                break
            line += ch
            if len(line) > 200:
                break
        if old:
            _again(os.write, fd, b"\n")
    finally:
        if old is not None:
            with contextlib.suppress(Exception):
                _again(termios.tcsetattr, fd, termios.TCSADRAIN, old)
        if handler is not None:
            with contextlib.suppress(Exception):
                signal.signal(signal.SIGTTOU, handler)
        os.close(fd)
    if not line.endswith(b"\n") and not line.strip():
        raise Fehler("abgebrochen: kein Code eingegeben. Es wurde nichts eingerichtet.")
    return line.decode("utf-8", "replace").strip()


def run_cmd(cmd):
    return subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE).returncode


def user_exists(name):
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def key_line(pi_key):
    return f'from="127.0.0.1,::1",restrict,pty {pi_key}'


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


class Ctx:
    """Everything setting up and removing touch outside this file: the system's paths, commands, users, the own
    sshd's port. The self-tests pass a temporary root and record the commands; nothing else changes it."""

    def __init__(self, system=None, root="/", run=run_cmd):
        system = system or platform.system()
        self.s = MAC if system == "Darwin" else WIN if system == "Windows" else LINUX
        self.root = root
        self.run = run

    def path(self, p):
        return here(self.root, p)

    def out(self, cmd):
        """A command's output (empty when it fails); only for reading (dscl -list, reg query, sc qc)."""
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

    def euid(self):
        """0 for root, on Windows for an elevated Administrator (the .cmd file asks for it)."""
        if self.s is WIN:
            try:
                import ctypes
                return 0 if ctypes.windll.shell32.IsUserAnAdmin() else 1
            except (ImportError, AttributeError, OSError):
                return 1
        return os.geteuid()

    def ids(self, name):
        """(uid, gid, home) of a user, None when there is none (Windows: only whether `net user` knows it)."""
        if self.s is WIN:
            return (0, 0, "") if self.run(["net", "user", name]) == 0 else None
        try:
            pw = pwd.getpwnam(name)
        except KeyError:
            return None
        return pw.pw_uid, pw.pw_gid, pw.pw_dir

    def chown(self, path, uid, gid):
        if self.s is not WIN:                  # Windows: icacls in win_users
            os.chown(path, uid, gid)

    def fetch(self, url, cap):
        return fetch_https(url, cap)

    def port_open(self):
        try:
            socket.create_connection(SSHD, timeout=3).close()
            return True
        except OSError:
            return False

    def wait(self, seconds):
        time.sleep(seconds)


# ---------------------------------------------------------------- Linux (systemd, useradd)
def linux_check(ctx):
    """Before anything changes: the host key and the own sshd (only explained, never installed here)."""
    if not os.path.isfile(ctx.path(HOSTKEY)):
        raise Fehler(f"{HOSTKEY} fehlt: sshd mit einem ed25519-Schlüssel ist nötig. Abhilfe: `sudo ssh-keygen -A` "
                     "legt die fehlenden Schlüssel an; ist sshd gar nicht da, erst `sudo apt install openssh-server` "
                     "(Fedora: `sudo dnf install openssh-server`), dann den Befehl aus dem Panel noch einmal")
    if not ctx.port_open():
        raise Fehler("sshd hört nicht auf 127.0.0.1:22. Abhilfe: `sudo systemctl enable --now ssh` "
                     "(Fedora: `sshd`), dann den Befehl aus dem Panel noch einmal")
    return {}


def linux_users(ctx, conf):
    if conf["user_neu"] and ctx.run(["useradd", "--create-home", "--shell", "/bin/bash", USER]):
        raise Fehler(f"Benutzer {USER} ließ sich nicht anlegen")
    if not ctx.ids(RUNNER) and ctx.run(["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", RUNNER]):
        raise Fehler(f"Benutzer {RUNNER} ließ sich nicht anlegen")
    return ctx.ids(USER), ctx.ids(RUNNER)


def linux_units(ctx):
    """The units of this version (setting up, `einheiten` after an update, `aktualisieren`); none is started here."""
    for path, text in zip(UNITS, (UNIT_RUN, UNIT_PATH, UNIT_ABBAU, UNIT_UPDATE_PATH, UNIT_UPDATE)):
        write(ctx.path(path), text)
    ctx.run(["systemctl", "daemon-reload"])
    return ctx.run(["systemctl", "enable", "--now", "spark-anker-update.path"])


def linux_start(ctx, runner):
    linux_units(ctx)
    if ctx.run(["systemctl", "enable", "--now", "spark-anker.service", "spark-anker-abbau.path"]):
        raise Fehler("systemd ließ den Dienst nicht starten (journalctl -u spark-anker)")


def linux_stop(ctx, conf):
    ctx.run(["systemctl", "disable", "--now", "spark-anker.service", "spark-anker-abbau.path", "spark-anker-update.path"])
    bild_off(ctx, conf)


def linux_after(ctx, conf, home_gone):
    ctx.run(["systemctl", "daemon-reload"])
    if conf.get("user_neu") and (ctx.root != "/" or ctx.ids(USER)):
        ctx.run(["userdel", "--remove", USER])
    if ctx.root != "/" or ctx.ids(RUNNER):
        ctx.run(["userdel", RUNNER])


def linux_last(ctx, conf):
    pass


# ---------------------------------------------------------------- macOS (launchd, dscl, Entfernte Anmeldung)
MAC_LIB = "/Library/Application Support/SparkAnker"
MAC_ETC = "/Library/Preferences/SparkAnker"
MAC_VAR = "/var/db/spark-anker"
MAC_JOB = "de.speech-spark.anker"
MAC_JOB_ABBAU = "de.speech-spark.anker-abbau"
MAC_JOB_UPDATE = "de.speech-spark.anker-update"
MAC_PLISTS = ("/Library/LaunchDaemons/" + MAC_JOB + ".plist", "/Library/LaunchDaemons/" + MAC_JOB_ABBAU + ".plist",
              "/Library/LaunchDaemons/" + MAC_JOB_UPDATE + ".plist")
MAC_SSHD_CONF = "/etc/ssh/sshd_config.d/000-spark-anker.conf"
MAC_SSHD_MAIN = "/etc/ssh/sshd_config"
MAC_SSH_GROUP = "com.apple.access_ssh"   # „Zugriff erlauben: nur diese Benutzer“ of Entfernte Anmeldung
MAC_RUNNER = "_sparkanker"
MAC_HOME = "/var/spark"
MAC_PY = "/usr/bin/python3"
MAC_IDS = range(401, 500)                # below 500: hidden from the login window and the user list
MAC_TEILEN = "Systemeinstellungen → Allgemein → Teilen → „Entfernte Anmeldung“"
# Only when Entfernte Anmeldung was off before: sshd then lets in nobody but the anchor (first value wins, the
# include stands at the top of macOS's sshd_config). ListenAddress counts when sshd runs on its own; launchd's
# socket on port 22 ignores it, AllowUsers and the access group hold either way.
MAC_SSHD_TEXT = """# spark-anker: Entfernte Anmeldung nur für den Fernzugang des Spark-Panels
# (geht wieder mit `sudo spark-anker entfernen`, dann ist die Entfernte Anmeldung wieder aus)
ListenAddress 127.0.0.1
ListenAddress ::1
AllowUsers spark@127.0.0.1 spark@::1
PasswordAuthentication no
KbdInteractiveAuthentication no
"""
MAC_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>{label}</string>
	<key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>-I</string><string>{prog}</string>{args}</array>
{extra}</dict>
</plist>
"""
MAC_RUN_EXTRA = f"""	<key>UserName</key><string>{MAC_RUNNER}</string>
	<key>GroupName</key><string>{MAC_RUNNER}</string>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ThrottleInterval</key><integer>10</integer>
	<key>Umask</key><integer>63</integer>
	<key>ProcessType</key><string>Background</string>
	<key>StandardOutPath</key><string>{MAC_VAR}/anker.log</string>
	<key>StandardErrorPath</key><string>{MAC_VAR}/anker.log</string>
"""
MAC_ABBAU_EXTRA = f"""	<key>WatchPaths</key><array><string>{MAC_VAR}/abbauen</string></array>
"""
MAC_UPDATE_EXTRA = f"""	<key>WatchPaths</key><array><string>{MAC_VAR}/aktualisieren</string></array>
"""


def mac_check(ctx):
    """Before anything changes: /usr/bin/python3 for the service, sshd's include folder, missing host keys made."""
    if ctx.run(["/usr/bin/xcode-select", "-p"]) or not os.path.exists(ctx.path(MAC_PY)):
        raise Fehler("/usr/bin/python3 fehlt (die Befehlszeilen-Werkzeuge von Apple). Abhilfe: `xcode-select --install`, "
                     "danach den Befehl aus dem Panel noch einmal. Es wurde nichts eingerichtet.")
    before = ctx.port_open()
    if not before:
        try:
            with open(ctx.path(MAC_SSHD_MAIN)) as f:
                main = f.read()
        except OSError:
            main = ""
        if not re.search(r"^\s*Include\s+/etc/ssh/sshd_config\.d/\*", main, re.M | re.I):
            raise Fehler("dieses macOS liest /etc/ssh/sshd_config.d nicht (erst ab macOS 13). Es wurde nichts eingerichtet.")
    if not os.path.isfile(ctx.path(HOSTKEY)) and ctx.run(["/usr/bin/ssh-keygen", "-A"]):
        raise Fehler("die Host-Schlüssel ließen sich nicht anlegen (`sudo ssh-keygen -A`). Es wurde nichts eingerichtet.")
    return {"anmeldung_vorher": before}


def mac_free_id(ctx):
    used = set()
    for kind, key in (("/Users", "UniqueID"), ("/Groups", "PrimaryGroupID")):
        used |= {int(x) for x in re.findall(r"(-?\d+)\s*$", ctx.out(["/usr/bin/dscl", ".", "-list", kind, key]), re.M)}
    for n in MAC_IDS:
        if n not in used:
            return n
    raise Fehler("keine freie Benutzernummer unter 500")


def mac_make(ctx, name, real, shell, home):
    """A hidden user with its own group of the same number (dscl, as System Settings does it underneath)."""
    if ctx.run(["/usr/bin/dscl", ".", "-read", "/Groups/" + name]) == 0:
        raise Fehler(f"eine Gruppe {name} gibt es schon; bitte zuerst entfernen")
    n = mac_free_id(ctx)
    cmds = [["/usr/bin/dscl", ".", "-create", "/Groups/" + name],
            ["/usr/bin/dscl", ".", "-create", "/Groups/" + name, "PrimaryGroupID", str(n)],
            ["/usr/bin/dscl", ".", "-create", "/Groups/" + name, "Password", "*"],
            ["/usr/bin/dscl", ".", "-create", "/Users/" + name]]
    for key, value in (("UniqueID", str(n)), ("PrimaryGroupID", str(n)), ("UserShell", shell), ("NFSHomeDirectory", home),
                       ("RealName", real), ("Password", "*"), ("IsHidden", "1")):
        cmds.append(["/usr/bin/dscl", ".", "-create", "/Users/" + name, key, value])
    for cmd in cmds:
        if ctx.run(cmd):
            raise Fehler(f"Benutzer {name} ließ sich nicht anlegen")
    return n, n, home


def mac_users(ctx, conf):
    if conf["user_neu"]:
        uid, gid, home = mac_make(ctx, USER, "Spark Fernzugang", "/bin/zsh", MAC_HOME)
        os.makedirs(ctx.path(home), mode=0o700, exist_ok=True)
        ctx.chown(ctx.path(home), uid, gid)
        user = (uid, gid, home)
    else:
        user = ctx.ids(USER)
    runner = ctx.ids(MAC_RUNNER) or mac_make(ctx, MAC_RUNNER, "Spark-Anker", "/usr/bin/false", "/var/empty")
    # only these users may use Entfernte Anmeldung: spark joins an existing list; when it was off, a list with spark alone
    if ctx.run(["/usr/bin/dscl", ".", "-read", "/Groups/" + MAC_SSH_GROUP]) == 0:
        conf["ssh_gruppe"] = "dazu"
    elif not conf["anmeldung_vorher"]:
        if ctx.run(["/usr/sbin/dseditgroup", "-o", "create", "-r", "Remote Login", MAC_SSH_GROUP]):
            raise Fehler("die Liste der Benutzer für die Entfernte Anmeldung ließ sich nicht anlegen")
        conf["ssh_gruppe"] = "neu"
    if conf.get("ssh_gruppe") and ctx.run(["/usr/sbin/dseditgroup", "-o", "edit", "-a", USER, "-t", "user", MAC_SSH_GROUP]):
        raise Fehler(f"{USER} ließ sich nicht zur Entfernten Anmeldung hinzufügen")
    if not conf["anmeldung_vorher"]:
        write(ctx.path(MAC_SSHD_CONF), MAC_SSHD_TEXT, 0o644)
        conf["sshd_conf"] = True
        if ctx.run(["/usr/sbin/sshd", "-t"]):
            os.remove(ctx.path(MAC_SSHD_CONF))
            raise Fehler("sshd nimmt die Einstellungen des Ankers nicht an; nichts an sshd geändert")
        mac_login(ctx, True)
        for _ in range(10):
            if ctx.port_open():
                break
            ctx.wait(0.5)
        else:
            ctx.run(["/usr/sbin/systemsetup", "-f", "-setremotelogin", "on"])
            if not ctx.port_open():
                mac_login(ctx, False)
                raise Fehler(f"die Entfernte Anmeldung ließ sich nicht einschalten. Abhilfe: {MAC_TEILEN} einschalten, "
                             "dann den Befehl aus dem Panel noch einmal")
        conf["anmeldung_an"] = True
    return user, runner


def mac_login(ctx, on):
    """Entfernte Anmeldung (Apple's sshd under launchd) on or off; systemsetup would need Full Disk Access."""
    if on:
        ctx.run(["/bin/launchctl", "enable", "system/com.openssh.sshd"])
        ctx.run(["/bin/launchctl", "bootstrap", "system", "/System/Library/LaunchDaemons/ssh.plist"])
    else:
        ctx.run(["/bin/launchctl", "bootout", "system/com.openssh.sshd"])
        ctx.run(["/bin/launchctl", "disable", "system/com.openssh.sshd"])


MAC_JOBS = ((MAC_PLISTS[0], MAC_JOB, "<string>lauf</string>", MAC_RUN_EXTRA),
            (MAC_PLISTS[1], MAC_JOB_ABBAU, "<string>entfernen</string><string>--vom-panel</string>", MAC_ABBAU_EXTRA),
            (MAC_PLISTS[2], MAC_JOB_UPDATE, "<string>aktualisieren</string><string>--vom-anker</string>", MAC_UPDATE_EXTRA))


def mac_plist(ctx, path, label, args, extra):
    write(ctx.path(path), MAC_PLIST.format(label=label, prog=MAC.prog, args=args, extra=extra), 0o644)
    ctx.chown(ctx.path(path), 0, 0)


def mac_units(ctx):
    """The jobs of this version written again (`einheiten`, `aktualisieren`); only the update job is loaded when it is
    not yet (launchd keeps a loaded job as it is; the update job may be the very one running this)."""
    for job in MAC_JOBS:
        mac_plist(ctx, *job)
    ctx.run(["/bin/launchctl", "bootstrap", "system", MAC_PLISTS[2]])   # already loaded: launchd says so, nothing changes
    return 0


def mac_start(ctx, runner):
    var = ctx.path(MAC_VAR)
    os.makedirs(var, mode=0o700, exist_ok=True)
    ctx.chown(var, runner[0], runner[1])
    for path, label, args, extra in MAC_JOBS:
        mac_plist(ctx, path, label, args, extra)
        if ctx.run(["/bin/launchctl", "bootstrap", "system", path]):
            raise Fehler(f"launchd ließ den Dienst nicht starten (sudo launchctl print system/{label})")


def mac_stop(ctx, conf):
    ctx.run(["/bin/launchctl", "bootout", "system/" + MAC_JOB])
    ctx.run(["/bin/launchctl", "bootout", "system/" + MAC_JOB_UPDATE])


def mac_after(ctx, conf, home_gone):
    if conf.get("sshd_conf") and os.path.isfile(ctx.path(MAC_SSHD_CONF)):
        os.remove(ctx.path(MAC_SSHD_CONF))
    if conf.get("ssh_gruppe") == "neu":
        ctx.run(["/usr/sbin/dseditgroup", "-o", "delete", MAC_SSH_GROUP])
    elif conf.get("ssh_gruppe") == "dazu":
        ctx.run(["/usr/sbin/dseditgroup", "-o", "edit", "-d", USER, "-t", "user", MAC_SSH_GROUP])
    if conf.get("user_neu"):
        ctx.run(["/usr/bin/dscl", ".", "-delete", "/Users/" + USER])
        ctx.run(["/usr/bin/dscl", ".", "-delete", "/Groups/" + USER])
        if home_gone:
            shutil.rmtree(home_gone, ignore_errors=True)
    if ctx.root != "/" or ctx.ids(MAC_RUNNER):
        ctx.run(["/usr/bin/dscl", ".", "-delete", "/Users/" + MAC_RUNNER])
        ctx.run(["/usr/bin/dscl", ".", "-delete", "/Groups/" + MAC_RUNNER])
    if conf.get("anmeldung_an"):                       # the anchor switched it on: off again, as it was
        mac_login(ctx, False)


def mac_last(ctx, conf):
    """The removal job stops itself only at the very end (launchd would end this very process)."""
    ctx.run(["/bin/launchctl", "bootout", "system/" + MAC_JOB_ABBAU])


# ---------------------------------------------------------------- Windows (OpenSSH Server, Aufgabenplanung, net user)
def _win_dir(key, name, default, drive=""):
    """A folder of Windows as the registry names it (never from variables; %SystemDrive% as the system's drive),
    else the usual one."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
            value = winreg.QueryValueEx(k, name)[0]
    except (ImportError, OSError):
        value = ""
    if isinstance(value, str) and drive:
        value = re.sub(r"(?i)%SystemDrive%", drive, value)
    return (value if isinstance(value, str) and re.fullmatch(r"[A-Za-z]:\\[^%]*", value) else default).replace("\\", "/").rstrip("/")


WIN_ROOT = _win_dir(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "SystemRoot", "C:/Windows")
WIN_PF = _win_dir(r"SOFTWARE\Microsoft\Windows\CurrentVersion", "ProgramFilesDir", "C:/Program Files")
WIN_PD = _win_dir(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList", "ProgramData", "C:/ProgramData", WIN_ROOT[:2])
WIN_SYS = WIN_ROOT + "/System32"
WIN_LIB = WIN_PF + "/SparkAnker"                     # the program, its own Python (python-<version>), spark-anker.cmd
WIN_ETC = WIN_PD + "/SparkAnker"                     # settings and the panel's key line: SYSTEM and Administrators only
WIN_VAR = WIN_ETC + "/var"                           # the anchor's own folder (LOCAL SERVICE may write)
WIN_KEYS = WIN_ETC + "/authorized_keys"              # sshd reads it for spark only (Match User spark)
WIN_SSH = WIN_PD + "/ssh"
WIN_SSHD_CONF = WIN_SSH + "/sshd_config"
WIN_OPENSSH = WIN_SYS + "/OpenSSH"
WIN_PS = WIN_SYS + "/WindowsPowerShell/v1.0/powershell.exe"
WIN_TASK, WIN_TASK_W = "SparkAnker", "SparkAnker-Waechter"
WIN_TASK_E = "SparkAnker-Einmal"      # name start of a PowerShell after this process (win_once); the task deletes itself
WIN_SIDS = {"system": "S-1-5-18", "admins": "S-1-5-32-544", "lokal": "S-1-5-19"}   # LOCAL SERVICE runs the anchor
WIN_CAP = "OpenSSH.Server~~~~0.0.1.0"
WIN_REG_OPENSSH = r"HKLM\SOFTWARE\OpenSSH"
WIN_REG_HIDE = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList"
WIN_REG_APPS = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SparkAnker"   # Apps → „Spark Anker“
WIN_FW_RULE = "OpenSSH-Server-In-TCP"
WIN_SSH_GROUP = "OpenSSH Users"      # sshd_config of newer OpenSSH: AllowGroups administrators "openssh users"
WIN_MARK = ("# spark-anker anfang", "# spark-anker ende")
WIN_SSHD_TOP = ("ListenAddress 127.0.0.1\nPasswordAuthentication no\n"
                f"AllowUsers {USER}@127.0.0.1\n")
WIN_SSHD_MATCH = f"Match User {USER}\n    AuthorizedKeysFile __PROGRAMDATA__/SparkAnker/authorized_keys\n"
WIN_WAECHTER_S = 5                                   # the root side looks for „abbauen“ and „aktualisieren“ this often
# Python for the anchor on Windows: python.org's embeddable package (PSF licence), only in WIN_LIB, never on PATH. The
# one source of version and SHA-256 (the panel's .cmd file reads them from here; a new runtime comes with a signed
# anchor like every update).
PY_EMBED = {"version": "3.13.16", "amd64": "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297",
            "arm64": "790d097697a2020477549a6764d89d22194c88d6e42caebcb2db63791e004c94"}
PY_EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-{arch}.zip"
PY_EMBED_MAX = 64 * 1024 * 1024


def py_embed(prog):
    """PY_EMBED as a program names it ({"version", "amd64", "arm64"}), None when it names none or a malformed one."""
    m = re.search(rb"^PY_EMBED = (\{.*?\})\r?$", prog or b"", re.M | re.S)   # \r: a checkout with CRLF
    try:
        pins = ast.literal_eval(m.group(1).decode()) if m else None
    except (ValueError, SyntaxError):
        return None
    ok = isinstance(pins, dict) and VER.fullmatch(str(pins.get("version") or "")) and \
        all(FP.fullmatch(str(pins.get(a) or "")) for a in ("amd64", "arm64"))
    return pins if ok else None
WIN_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{desc}</Description></RegistrationInfo>
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{sid}</UserId><RunLevel>{level}</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author"><Exec><Command>{python}</Command><Arguments>-I "{prog}" {arg}</Arguments></Exec></Actions>
</Task>
"""
WIN_ONCE_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Spark-Anker: einmal nach dem Anker</Description></RegistrationInfo>
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{sid}</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT1H</ExecutionTimeLimit><Hidden>true</Hidden></Settings>
  <Actions Context="Author"><Exec><Command>{ps}</Command><Arguments>{args}</Arguments></Exec></Actions>
</Task>
"""
WIN_CMD = """@echo off
rem spark-anker: Fernzugang des Spark-Panels (entfernen, zustand); fragt selbst nach Administratorrechten
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs" & exit /b)
"{python}" -I "{prog}" %*
pause
"""
# the user spark: a random password made and forgotten inside PowerShell (never an argument, never stored), hidden
WIN_USER_PS = ("$b=New-Object byte[] 24;[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b);"
               "$p=ConvertTo-SecureString ([Convert]::ToBase64String($b)+'aA1!') -AsPlainText -Force;"
               f"New-LocalUser -Name {USER} -Password $p -PasswordNeverExpires -UserMayNotChangePassword "
               "-Description 'Spark Fernzugang' | Out-Null")
WIN_SID_PS = f"(Get-LocalUser -Name {USER}).SID.Value"
# the user spark away with its profile: its processes end first (a session still open keeps the profile loaded, and a
# new spark would get the folder spark.<PC>); a profile Windows still holds goes later (WIN_LATER_PS)
WIN_USER_WEG_PS = (f"$u=Get-LocalUser -Name {USER} -ErrorAction SilentlyContinue; if($u){{"
                   "Get-Process -IncludeUserName -ErrorAction SilentlyContinue | Where-Object {$_.UserName -like "
                   f"'*\\{USER}'}} | Stop-Process -Force -ErrorAction SilentlyContinue;"
                   "Get-CimInstance Win32_UserProfile | Where-Object {$_.SID -eq $u.SID.Value} | "
                   "Remove-CimInstance -ErrorAction SilentlyContinue;"
                   f"Remove-LocalUser -Name {USER}}}")
# spark joins the group AllowGroups lets in (exit 3: joined now, 0: was in it already)
WIN_GROUP_PS = (f"$g='{WIN_SSH_GROUP}';if(-not (Get-LocalGroupMember -Group $g -Member {USER} -ErrorAction SilentlyContinue))"
                f"{{Add-LocalGroupMember -Group $g -Member {USER};exit 3}}")
WIN_GROUP_WEG_PS = f"Remove-LocalGroupMember -Group '{WIN_SSH_GROUP}' -Member {USER} -ErrorAction SilentlyContinue"
# after the anchor (win_once): its folder once the Python in it ended (never a folder a new setup made: then anker.json
# is there again) and the profile of the removed spark once Windows let go of it (after an SSH session Windows keeps it
# loaded until the next start); two minutes, then again at every start until both are gone
WIN_LATER_PS = ("$l='{lib}';$s='{sid}';$lw=$false;$fertig=$false;for($i=0;$i -lt 60;$i++){{"
                "if(-not $lw){{if(Test-Path -LiteralPath '{conf}'){{$lw=$true}}else{{"
                "Remove-Item -LiteralPath $l -Recurse -Force -ErrorAction SilentlyContinue;$lw=-not (Test-Path -LiteralPath $l)}}}};"
                "$p=$null;if($s){{$p=Get-CimInstance Win32_UserProfile | Where-Object {{$_.SID -eq $s}};"
                "if($p){{try{{$p | Remove-CimInstance -ErrorAction Stop;$p=$null}}catch{{}}}}}};"
                "if($lw -and -not $p){{$fertig=$true;break}};Start-Sleep 2}};if(-not $fertig){{exit 1}}")


def win_native(p):
    return p.replace("/", "\\")


def win_once(ctx, name, script):
    """script (PowerShell) once more after this process ended, as SYSTEM in a task of its own: a child of this process
    would end with the task's job (the Task Scheduler takes it down). The task deletes itself when the script ends
    without „exit“; else it runs again at the next start. name: WIN_TASK_E-<name>, one task per purpose."""
    name = f"{WIN_TASK_E}-{name}"
    xml = ctx.path(f"{WIN_LIB}/{name}.xml")
    args = f'-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "{script}; schtasks /delete /tn {name} /f"'
    with open(xml, "w", encoding="utf-16") as f:
        f.write(WIN_ONCE_XML.format(sid=WIN_SIDS["system"], ps=win_native(WIN_PS), args=args.replace("&", "&amp;")
                                    .replace("<", "&lt;").replace(">", "&gt;")))
    rc = ctx.run(["schtasks", "/create", "/tn", name, "/xml", win_native(xml), "/f"]) or \
        ctx.run(["schtasks", "/run", "/tn", name])
    with contextlib.suppress(OSError):
        os.remove(xml)
    return rc


def win_ps(ctx, script):
    return ctx.run([WIN_PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])


def win_runtime_dir(version=None):
    return f"{WIN_LIB}/python-{version or PY_EMBED['version']}"


def win_arch():
    """The Python this runs on (the one the file chose for this Windows): amd64 or arm64."""
    return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"


def _marked(block):
    return f"{WIN_MARK[0]}\n{block}{WIN_MARK[1]}\n"


def win_unmark(text):
    """The sshd settings without the anchor's marked blocks (everything else as the owner left it)."""
    return re.sub(rf"(?ms)^{re.escape(WIN_MARK[0])}\n.*?^{re.escape(WIN_MARK[1])}\n?", "", text)


def win_sshd_text(text, own):
    """The anchor's blocks into sshd_config: the first values count, so ListenAddress and AllowUsers go to the top
    (only when the anchor switched sshd on); Match User spark always at the very end."""
    text = win_unmark(text)
    if text and not text.endswith("\n"):
        text += "\n"
    return (_marked(WIN_SSHD_TOP) if own else "") + text + _marked(WIN_SSHD_MATCH)


def win_reg_value(ctx, key, name):
    """A registry value as `reg query` prints it, "" when there is none."""
    m = re.search(rf"^\s*{re.escape(name)}\s+REG_\w+\s+(.*?)\s*$", ctx.out(["reg", "query", key, "/v", name]), re.M)
    return m.group(1) if m else ""


def win_check(ctx):
    """Before anything changes: OpenSSH Server there (the .cmd file adds it), its settings readable, the host key
    (made by ssh-keygen -A when sshd never ran), a list „AllowUsers“ of the owner that would keep spark out."""
    if not os.path.isfile(ctx.path(WIN_OPENSSH + "/sshd.exe")):
        raise Fehler("OpenSSH-Server fehlt. Abhilfe: die Datei spark-anker-einrichten.cmd aus dem Panel nehmen (sie "
                     "richtet ihn ein) oder Einstellungen → System → Optionale Features → „OpenSSH-Server“. "
                     "Es wurde nichts eingerichtet.")
    before = ctx.port_open()
    conf = ctx.path(WIN_SSHD_CONF)
    if not os.path.isfile(conf):
        default = ctx.path(WIN_OPENSSH + "/sshd_config_default")
        if not os.path.isfile(default):
            raise Fehler("sshd_config fehlt und keine Vorlage da. Es wurde nichts eingerichtet.")
        os.makedirs(os.path.dirname(conf), exist_ok=True)
        shutil.copyfile(default, conf)
    with open(conf, encoding="utf-8", errors="replace") as f:
        text = win_unmark(f.read())
    allow = re.findall(r"^\s*AllowUsers\s+(.+)$", text, re.M | re.I)
    listen = [x for x in re.findall(r"^\s*ListenAddress\s+(\S+)", text, re.M | re.I) if x not in ("127.0.0.1", "127.0.0.1:22")]
    if not before and listen:
        raise Fehler(f"sshd_config nennt eigene Adressen (ListenAddress). Der Anker schaltet sshd nur für 127.0.0.1 ein; "
                     f"bitte dort entfernen oder sshd selbst starten, dann die Datei noch einmal. Es wurde nichts eingerichtet.")
    if before and allow and not any(re.fullmatch(rf"{USER}(@\S+)?", w, re.I) for a in allow for w in a.split()):
        raise Fehler(f"sshd lässt hier nur bestimmte Benutzer herein (AllowUsers in {win_native(WIN_SSHD_CONF)}). "
                     f"Abhilfe: dort {USER}@127.0.0.1 ergänzen, dann die Datei noch einmal. Es wurde nichts eingerichtet.")
    groups = [g.strip('"').lower() for a in re.findall(r"^\s*AllowGroups\s+(.+)$", text, re.M | re.I)
              for g in re.findall(r'"[^"]*"|\S+', a)]
    if groups and WIN_SSH_GROUP.lower() not in groups:
        raise Fehler(f"sshd lässt hier nur bestimmte Gruppen herein (AllowGroups in {win_native(WIN_SSHD_CONF)}). "
                     f"Abhilfe: dort \"{WIN_SSH_GROUP.lower()}\" ergänzen, dann die Datei noch einmal. Es wurde nichts eingerichtet.")
    if not os.path.isfile(ctx.path(WIN_SSH + "/ssh_host_ed25519_key.pub")) and ctx.run([WIN_OPENSSH + "/ssh-keygen.exe", "-A"]):
        raise Fehler("die Host-Schlüssel ließen sich nicht anlegen (ssh-keygen -A). Es wurde nichts eingerichtet.")
    start = re.search(r"START_TYPE\s*:\s*\d+\s+(\w+)", ctx.out(["sc.exe", "qc", "sshd"]))
    return {"sshd_vorher": before, "sshd_start_vorher": start.group(1).lower() if start else "demand",
            "ssh_gruppe_noetig": bool(groups)}


def win_acl(ctx, path, *grants):
    """Only these may touch path (no rights inherited from above): SYSTEM and Administrators always."""
    return ctx.run(["icacls", win_native(ctx.path(path)), "/inheritance:r", "/grant:r",
                    f"*{WIN_SIDS['system']}:(OI)(CI)F", f"*{WIN_SIDS['admins']}:(OI)(CI)F", *grants])


def win_users(ctx, conf):
    for d in (WIN_ETC, WIN_VAR):
        os.makedirs(ctx.path(d), exist_ok=True)
    if win_acl(ctx, WIN_ETC, f"*{WIN_SIDS['lokal']}:(OI)(CI)RX") or \
            ctx.run(["icacls", win_native(ctx.path(WIN_VAR)), "/grant", f"*{WIN_SIDS['lokal']}:(OI)(CI)M"]):
        raise Fehler(f"die Rechte von {win_native(WIN_ETC)} ließen sich nicht setzen")
    if conf["user_neu"]:
        if win_ps(ctx, WIN_USER_PS):
            raise Fehler(f"Benutzer {USER} ließ sich nicht anlegen")
        ctx.run(["reg", "add", WIN_REG_HIDE, "/v", USER, "/t", "REG_DWORD", "/d", "0", "/f"])   # not on the sign-in screen
    if conf.get("ssh_gruppe_noetig"):           # AllowGroups: spark joins „OpenSSH Users“ (no other right comes with it)
        rc = win_ps(ctx, WIN_GROUP_PS)
        if rc not in (0, 3):
            raise Fehler(f"Benutzer {USER} ließ sich nicht in die Gruppe {WIN_SSH_GROUP} aufnehmen")
        conf["ssh_gruppe"] = "dazu" if rc == 3 else ""
    path = ctx.path(WIN_SSHD_CONF)
    with open(path, encoding="utf-8", errors="replace") as f:
        old = f.read()
    own = not conf["sshd_vorher"]
    write_atomic(path, win_sshd_text(old, own).encode(), 0o644)
    conf["sshd_conf"] = True
    if ctx.run([WIN_OPENSSH + "/sshd.exe", "-t"]):
        write_atomic(path, old.encode(), 0o644)
        raise Fehler("sshd nimmt die Einstellungen des Ankers nicht an; nichts an sshd geändert")
    if own:
        conf["shell_vorher"] = win_reg_value(ctx, WIN_REG_OPENSSH, "DefaultShell")
        ctx.run(["reg", "add", WIN_REG_OPENSSH, "/v", "DefaultShell", "/t", "REG_SZ", "/d", win_native(WIN_PS), "/f"])
        win_ps(ctx, f"Disable-NetFirewallRule -Name {WIN_FW_RULE} -ErrorAction SilentlyContinue")
        conf["sshd_an"] = True
        ctx.run(["sc.exe", "config", "sshd", "start=", "auto"])
        ctx.run(["sc.exe", "start", "sshd"])
        for _ in range(20):
            if ctx.port_open():
                break
            ctx.wait(0.5)
        else:
            raise Fehler("sshd ließ sich nicht starten (Dienste → OpenSSH SSH Server)")
    else:
        win_ps(ctx, "Restart-Service sshd")      # reads Match User spark; sessions already open stay
    return (0, 0, ""), (0, 0, "")


def win_keys(ctx, user, line):
    """The panel's line (LF only) in WIN_KEYS; sshd takes the file only when SYSTEM or Administrators own it, so the
    owner is set to SYSTEM (an elevated admin would otherwise own it on a PC without UAC)."""
    with open(ctx.path(WIN_KEYS), "a", encoding="ascii", newline="\n") as f:
        f.write(line + "\n")
    if ctx.run(["icacls", win_native(ctx.path(WIN_KEYS)), "/setowner", f"*{WIN_SIDS['system']}"]):
        raise Fehler(f"die Rechte von {win_native(WIN_KEYS)} ließen sich nicht setzen")


def win_units(ctx):
    """The tasks of this version (the anchor as LOCAL SERVICE, the watcher as SYSTEM, both at start), spark-anker.cmd
    and the entry in Apps, always with the Python running this (its own, in WIN_LIB)."""
    py, prog, rc = win_native(sys.executable), win_native(WIN.prog), 0
    os.makedirs(ctx.path(WIN_ETC + "/aufgaben"), exist_ok=True)
    for name, sid, level, arg, desc in ((WIN_TASK, WIN_SIDS["lokal"], "LeastPrivilege", "lauf", "Spark-Anker"),
                                         (WIN_TASK_W, WIN_SIDS["system"], "HighestAvailable", "waechter", "Spark-Anker Abbau und Aktualisieren")):
        xml = ctx.path(f"{WIN_ETC}/aufgaben/{name}.xml")
        with open(xml, "w", encoding="utf-16") as f:
            f.write(WIN_TASK_XML.format(desc=desc, sid=sid, level=level, python=py, prog=prog, arg=arg))
        rc |= ctx.run(["schtasks", "/create", "/tn", name, "/xml", win_native(xml), "/f"])
    with open(ctx.path(WIN_LIB + "/spark-anker.cmd"), "w", newline="\r\n") as f:
        f.write(WIN_CMD.format(python=py, prog=prog))
    cmd = win_native(WIN_LIB + "/spark-anker.cmd")
    for name, typ, value in (("DisplayName", "REG_SZ", "Spark Anker"), ("DisplayVersion", "REG_SZ", VERSION),
                             ("Publisher", "REG_SZ", "Speech on DGX Spark"), ("InstallLocation", "REG_SZ", win_native(WIN_LIB)),
                             ("UninstallString", "REG_SZ", f'"{cmd}" entfernen'), ("NoModify", "REG_DWORD", "1"),
                             ("NoRepair", "REG_DWORD", "1")):
        ctx.run(["reg", "add", WIN_REG_APPS, "/v", name, "/t", typ, "/d", value, "/f"])
    return rc


def win_start(ctx, runner):
    if win_units(ctx):
        raise Fehler("die Aufgabenplanung nahm die Aufgaben nicht an (Aufgabenplanung → SparkAnker)")
    for name in (WIN_TASK_W, WIN_TASK):
        if ctx.run(["schtasks", "/run", "/tn", name]):
            raise Fehler(f"die Aufgabe {name} ließ sich nicht starten (Aufgabenplanung)")


def win_stop(ctx, conf):
    ctx.run(["schtasks", "/end", "/tn", WIN_TASK])
    ctx.run(["schtasks", "/delete", "/tn", WIN_TASK, "/f"])      # the watcher goes last (win_last): it may be the one removing


def win_after(ctx, conf, home_gone):
    """sshd, its shell and firewall rule, the user spark and the entry in Apps as they were before the anchor."""
    path = ctx.path(WIN_SSHD_CONF)
    if conf.get("sshd_conf") and os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        write_atomic(path, win_unmark(text).encode(), 0o644)
    if conf.get("sshd_an"):
        ctx.run(["sc.exe", "stop", "sshd"])
        ctx.run(["sc.exe", "config", "sshd", "start=", {"auto": "auto", "disabled": "disabled"}.get(conf.get("sshd_start_vorher"), "demand")])
        if conf.get("shell_vorher"):
            ctx.run(["reg", "add", WIN_REG_OPENSSH, "/v", "DefaultShell", "/t", "REG_SZ", "/d", conf["shell_vorher"], "/f"])
        else:
            ctx.run(["reg", "delete", WIN_REG_OPENSSH, "/v", "DefaultShell", "/f"])
        win_ps(ctx, f"Enable-NetFirewallRule -Name {WIN_FW_RULE} -ErrorAction SilentlyContinue")
    elif conf.get("sshd_conf"):
        win_ps(ctx, "Restart-Service sshd")
    if conf.get("ssh_gruppe") == "dazu" and not conf.get("user_neu"):   # a new spark leaves the group with itself
        win_ps(ctx, WIN_GROUP_WEG_PS)
    if conf.get("user_neu"):
        conf["sid_weg"] = ctx.out([WIN_PS, "-NoProfile", "-NonInteractive", "-Command", WIN_SID_PS]).strip()   # win_last
        win_ps(ctx, WIN_USER_WEG_PS)
        ctx.run(["reg", "delete", WIN_REG_HIDE, "/v", USER, "/f"])
    if conf.get("sshd_neu"):                         # the .cmd file added OpenSSH Server: away again
        win_ps(ctx, f"Remove-WindowsCapability -Online -Name {WIN_CAP} | Out-Null")
    ctx.run(["reg", "delete", WIN_REG_APPS, "/f"])


def win_last(ctx, conf):
    """The program's folder holds the very Python running this: a small PowerShell takes it away once it is free.
    The watcher's task last of all (when it is the one removing, deleting it may end this process)."""
    sid = conf.get("sid_weg", "") if re.fullmatch(r"S-1-5-21(-\d{1,10}){1,8}", str(conf.get("sid_weg", ""))) else ""
    # one task per removed spark (its SID's last number): a new spark removed before the next start has its own
    win_once(ctx, "weg-" + (sid.rsplit("-", 1)[-1] if sid else "0"), WIN_LATER_PS.format(lib=win_native(ctx.path(WIN_LIB)), conf=win_native(ctx.path(WIN.conf)), sid=sid))
    ctx.run(["schtasks", "/delete", "/tn", WIN_TASK_W, "/f"])


def win_runtime(ctx, prog):
    """The Python a new program names (PY_EMBED in it, signed with it), fetched from python.org only when it is not
    there yet, checked by its SHA-256 and unpacked beside the one running: the path of its python.exe, "" when it
    fails (the update then stays with the one before)."""
    pins = py_embed(prog)
    if not isinstance(pins, dict) or not VER.fullmatch(str(pins.get("version") or "")) or not FP.fullmatch(str(pins.get(win_arch()) or "")):
        return ""
    target = ctx.path(win_runtime_dir(pins["version"]))
    exe = os.path.join(target, "python.exe")
    if os.path.isfile(exe):
        return exe
    url = PY_EMBED_URL.format(v=pins["version"], arch=win_arch())
    try:
        data = ctx.fetch(url, PY_EMBED_MAX)
    except (OSError, Fehler, ssl.SSLError, http.client.HTTPException):
        return ""
    if not data or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), pins[win_arch()]):
        return ""
    tmp = target + ".neu"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") or ":" in n:
                    return ""
            z.extractall(tmp)
        os.replace(tmp, target)
    except (OSError, zipfile.BadZipFile):
        shutil.rmtree(tmp, ignore_errors=True)
        return ""
    return exe if os.path.isfile(exe) else ""


def fetch_https(url, cap):
    """GET url with the system's authorities (python.org for the runtime), at most cap bytes, no redirect."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname:
        raise Fehler("nur https")
    c = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=60, context=authorities())
    try:
        c.request("GET", u.path, headers={"User-Agent": f"spark-anker/{VERSION}"})
        r = c.getresponse()
        if r.status != 200:
            raise Fehler(f"{u.hostname} antwortet {r.status}")
        data = r.read(cap + 1)
    finally:
        c.close()
    if len(data) > cap:
        raise Fehler("zu groß")
    return data


def win_old_runtimes(ctx):
    """Pythons of earlier versions the watcher no longer runs from (after a runtime update)."""
    here_ = os.path.dirname(os.path.abspath(sys.executable)).replace("\\", "/").lower()
    lib = ctx.path(WIN_LIB)
    with contextlib.suppress(OSError):
        for n in os.listdir(lib):
            p = os.path.join(lib, n)
            if n.startswith("python-") and os.path.isdir(p) and p.replace("\\", "/").lower() != here_:
                shutil.rmtree(p, ignore_errors=True)


def cmd_watch(args, ctx=None, rounds=None):
    """`waechter` (Windows, the task SparkAnker-Waechter as SYSTEM): what the root units do on Linux. „abbauen“ from
    the panel removes everything, „aktualisieren“ swaps the program (cmd_apply); after a new Python the watcher
    starts again on it."""
    ctx = ctx or Ctx()
    s = ctx.s
    if s is not WIN or ctx.euid() != 0:
        say("nur unter Windows als SYSTEM (Aufgabe SparkAnker-Waechter)")
        return 1
    win_old_runtimes(ctx)
    n = 0
    while rounds is None or n < rounds:
        n += 1
        if os.path.lexists(ctx.path(s.flag)):
            cmd_remove(argparse.Namespace(vom_panel=True), ctx=ctx)
            return 0
        if os.path.lexists(ctx.path(s.var + "/aktualisieren")):
            cmd_apply(args, ctx)
            if os.path.normcase(getattr(ctx, "python_neu", "") or sys.executable) != os.path.normcase(sys.executable):
                win_once(ctx, "neu", f"Start-Sleep 3; Start-ScheduledTask -TaskName {WIN_TASK_W}")   # again, on the new Python
                return 0
        ctx.wait(WIN_WAECHTER_S)
    return 0


class System:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def home_keys(ctx, user, line):
    """The panel's line in ~/.ssh/authorized_keys of the user spark (Linux, macOS)."""
    ssh = ctx.path(os.path.join(user[2], ".ssh"))
    os.makedirs(ssh, mode=0o700, exist_ok=True)
    ak = os.path.join(ssh, "authorized_keys")
    with open(ak, "a") as f:
        f.write(line + "\n")
    for p, m in ((ssh, 0o700), (ak, 0o600)):
        ctx.chown(p, user[0], user[1])
        os.chmod(p, m)


SUDO = "bitte mit sudo"
LINUX = System(name="Linux", lib=LIB, prog=PROG, bin=BIN, etc=ETC, conf=CONF, var=VAR, flag=FLAG, services=UNITS,
               python="/usr/bin/python3", units=linux_units, hostkey=HOSTKEY, keys=home_keys, sudo=SUDO,
               weg="sudo spark-anker entfernen", runner=RUNNER, check=linux_check, users=linux_users, start=linux_start,
               stop=linux_stop, after=linux_after, last=linux_last, started="der Dienst spark-anker läuft")
MAC = System(name="Darwin", lib=MAC_LIB, prog=MAC_LIB + "/spark-anker.py", bin=BIN,
             etc=MAC_ETC, conf=MAC_ETC + "/anker.json", var=MAC_VAR, flag=MAC_VAR + "/abbauen", services=MAC_PLISTS,
             python=MAC_PY, units=mac_units, hostkey=HOSTKEY, keys=home_keys, sudo=SUDO, weg="sudo spark-anker entfernen",
             runner=MAC_RUNNER, check=mac_check, users=mac_users, start=mac_start, stop=mac_stop,
             after=mac_after, last=mac_last, started="der Dienst de.speech-spark.anker läuft (launchd)")
WIN = System(name="Windows", lib=WIN_LIB, prog=WIN_LIB + "/spark-anker.py", bin=None, etc=WIN_ETC,
             conf=WIN_ETC + "/anker.json", var=WIN_VAR, flag=WIN_VAR + "/abbauen", services=(), python=sys.executable,
             units=win_units, hostkey=WIN_SSH + "/ssh_host_ed25519_key.pub", keys=win_keys,
             sudo="bitte als Administrator (die Datei aus dem Panel fragt selbst danach)",
             weg="in den Windows-Einstellungen unter Apps „Spark Anker“ deinstallieren", runner=WIN_SIDS["lokal"], check=win_check,
             users=win_users, start=win_start, stop=win_stop, after=win_after, last=win_last,
             started="die Aufgabe SparkAnker läuft (Aufgabenplanung)")


TOKEN = re.compile(r"[A-Za-z0-9_\-]{20,64}")


def read_token(stream=None):
    """The one-time key of the Windows file (spark-anker-einrichten.cmd hands it over on stdin, never as an argument)."""
    s = stream or sys.stdin
    raw = getattr(s, "buffer", s).readline(400)      # bytes from PowerShell's pipe: a BOM or UTF-16 zeros are dropped
    line = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw).replace("\x00", "").lstrip("\ufeff").strip()
    if not TOKEN.fullmatch(line):
        raise Fehler("der Einmal-Schlüssel der Datei fehlt oder ist kaputt: die Datei im Panel neu laden. "
                     "Es wurde nichts eingerichtet.")
    return line


def cmd_setup(args, code_reader=read_code, run=run_cmd, ctx=None, token_reader=read_token):
    ctx = ctx or Ctx(run=run)
    s = ctx.s
    if ctx.euid() != 0:
        say(s.sudo)
        return 1
    if load(ctx.root, s):
        if s is WIN:
            say(f"schon eingerichtet. Neu koppeln: erst {s.weg}, dann die Datei aus dem Panel noch einmal")
        else:
            say("schon eingerichtet. Neue Version: `curl -fsSL <Panel>/fernzugang/anker | sudo python3 - aktualisieren` "
                "(die Zeile steht im Panel beim System; Kopplung und Schlüssel bleiben). Neu koppeln: erst `sudo spark-anker entfernen`")
        return 1
    base = base_url(args.adresse)
    fp = (args.fp or "").lower()
    if fp and not FP.fullmatch(fp):
        raise Fehler("--fp: 64 Zeichen 0-9 a-f")
    token = token_reader() if getattr(args, "token", "") == "-" else ""
    state = s.check(ctx)
    with open(ctx.path(s.hostkey)) as f:
        hostkey = " ".join(f.read().split()[:2])
    with contextlib.suppress(IndexError, ValueError):   # the panel shows it the same way, to compare before „Bestätigen“
        say("Host-Schlüssel dieses Systems: SHA256:" + base64.b64encode(
            hashlib.sha256(base64.b64decode(hostkey.split()[1])).digest()).decode().rstrip("="))
    sock, got = tls_connect(base, fp)
    sock.close()
    say(f"Panel {base}, Zertifikat SHA-256 {got[:16]}…{got[-8:]}" + (" (festgelegt)" if fp else " (geprüft gegen die Zertifizierungsstellen)"))
    secret = {"token": token} if token else {"code": code_reader()}
    status, raw = http_call(base, fp, "POST", "/api/fernzugang/anker/koppeln",
                            {**secret, "hostkey": hostkey, "os": os_name(s), "version": VERSION})
    secret = token = None
    if status != 200:
        raise Fehler({403: "Code falsch oder abgelaufen" if not getattr(args, "token", "") else
                      "die Datei ist abgelaufen oder schon benutzt: im Panel neu laden",
                      404: "Fernzugang im Panel ist aus", 409: "zu viele Server gekoppelt",
                      429: "zu viele Versuche, später noch einmal"}.get(status, f"Panel antwortet {status}"))
    d = json.loads(raw)
    status, prog = http_call(base, fp, "GET", "/fernzugang/anker")
    if status != 200 or not hmac.compare_digest(hashlib.sha256(prog).hexdigest(), str(d.get("anker_sha256", ""))):
        raise Fehler("das Programm vom Panel passt nicht zu seiner Prüfsumme")
    conf = {"url": base, "fp": fp, "id": d["id"], "key": d["key"], "user_neu": not ctx.ids(USER), "seit": int(time.time()),
            **state}
    if getattr(args, "sshd_neu", False):         # the .cmd file added OpenSSH Server just now: removing takes it away
        conf["sshd_neu"] = True
    if _b64(d.get("sign_pub"), 32):            # the panel's signing key for updates, pinned with the pairing
        conf["sign_pub"] = d["sign_pub"]
    if intern_ok(d.get("intern")):
        conf["intern"] = intern_ok(d.get("intern"))   # paired at home: the panel's own address first (verbinden)
    user, runner = s.users(ctx, conf)
    s.keys(ctx, user, key_line(str(d["pi_key"])))
    os.makedirs(os.path.dirname(ctx.path(s.prog)), exist_ok=True)
    write_atomic(ctx.path(s.prog), prog, 0o755)     # the bytes as checked (no line ends changed on Windows)
    if s.bin:
        bin_ = ctx.path(s.bin)
        os.makedirs(os.path.dirname(bin_), exist_ok=True)
        if os.path.lexists(bin_):
            os.remove(bin_)
        os.symlink(s.prog, bin_)
    write(ctx.path(s.conf), json.dumps(conf, indent=1), 0o640)
    ctx.chown(ctx.path(s.conf), 0, runner[1])
    ctx.chown(ctx.path(s.etc), 0, runner[1])
    os.chmod(ctx.path(s.etc), 0o750)
    s.start(ctx, runner)
    say(f"eingerichtet: der Panel-Schlüssel darf als {USER} nur über den Anker herein; {s.started}")
    if d.get("wartet"):
        say("jetzt im Panel das neue System bestätigen (Fernzugang → Systeme); erst dann geht eine Sitzung")
    say(f"entfernen: {s.weg} (oder im Panel „Entfernen“)")
    return 0


# ---------------------------------------------------------------- removing everything
def remove_paths(root="/", s=None):
    """Every path the anchor made (the user spark's home only when the anchor made the user). Windows: not the program's
    folder, it holds the Python running this (its standard library too); win_last takes it away after this process."""
    s = s or LINUX
    extra = (*BILD_UNITS, WAYVNC_UNIT) if s is LINUX else ()
    return [here(root, p) for p in (*s.services, *extra, s.bin, s.lib if s is not WIN else None, s.etc, s.var) if p]


def strip_key(path):
    """Takes the panel's line(s) out of authorized_keys; the file stays when other lines are left."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    keep = [ln for ln in lines if MARK not in ln]
    if len(keep) == len(lines):
        return False
    if keep:
        with open(path, "w") as f:
            f.write("\n".join(keep) + "\n")
    else:
        os.remove(path)
    return True


def cmd_remove(args, root="/", run=run_cmd, tell=True, home=None, ctx=None):
    ctx = ctx or Ctx(root=root, run=run)
    s = ctx.s
    if ctx.root == "/" and ctx.euid() != 0:
        say(ctx.s.sudo)
        return 1
    conf = load(ctx.root, s) or {}
    s.stop(ctx, conf)
    for p in remove_paths(ctx.root, s):
        if os.path.islink(p) or os.path.isfile(p):
            os.remove(p)
        elif os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
    if home is None:
        found = ctx.ids(USER)
        home = found[2] if found else ""
    if home:
        strip_key(os.path.join(home, ".ssh", "authorized_keys"))
    s.after(ctx, conf, home if conf.get("user_neu") else "")
    say("entfernt: Dienste, Programm, Einstellungen, Schlüssel" + (f", Benutzer {USER}" if conf.get("user_neu") else "")
        + (", Entfernte Anmeldung wieder aus" if conf.get("anmeldung_an") else ""))
    if tell and conf.get("url") and conf.get("key"):
        try:
            status, _ = http_call(conf["url"], conf.get("fp") or "", "POST", "/api/fernzugang/anker/abgebaut", {}, conf["key"], 10)
            say("dem Panel gemeldet" if status == 200 else f"Panel antwortet {status}")
        except (OSError, Fehler):
            say("Panel nicht erreicht; dort „Entfernen“ wählen")
    s.last(ctx, conf)
    return 0


# ---------------------------------------------------------------- the screen (stage 4)
def linux_bild_art(ctx):
    """(kind, user) of the graphical session signed in here: X11 → x11vnc, GNOME on Wayland → grd, other Wayland →
    wayvnc; the active one first. None of them: a fixed sentence, nothing set up."""
    found = []
    for line in ctx.out(["loginctl", "list-sessions", "--no-legend"]).splitlines():
        sid = line.split()[0] if line.split() else ""
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", sid):
            continue
        d = dict(x.split("=", 1) for x in ctx.out(["loginctl", "show-session", sid, "-p", "Type", "-p", "Desktop",
                                                   "-p", "Name", "-p", "Class", "-p", "Active"]).splitlines() if "=" in x)
        if d.get("Class") == "user" and d.get("Type") in ("x11", "wayland") and re.fullmatch(r"[a-z_][a-z0-9_.\-]{0,31}", d.get("Name", "")):
            found.append((d.get("Active") != "yes", d["Type"], d.get("Desktop", "").lower(), d["Name"]))
    if not found:
        raise Fehler("keine grafische Sitzung angemeldet (ein Server ohne Bildschirm?). Erst am Gerät anmelden, dann "
                     "den Befehl noch einmal. Es wurde nichts eingerichtet.")
    _, typ, desk, user = sorted(found)[0]
    if typ == "x11":
        return "x11vnc", user
    return ("grd" if "gnome" in desk else "wayvnc"), user


def bild_off(ctx, conf):
    """Everything of the screen away again (`bildschirm aus`, `entfernen`): units, files, GNOME's RDP as it was."""
    art = conf.get("bild")
    if art == "x11vnc":
        ctx.run(["systemctl", "disable", "--now", "spark-anker-bild.socket"])
    if art == "wayvnc":
        ctx.run(["systemctl", "--global", "disable", "spark-anker-wayvnc.service"])
    if art == "grd":
        ctx.run(["grdctl", "--system", "rdp", "disable"])
        ctx.run(["grdctl", "--system", "rdp", "clear-credentials"])
        if conf.get("grd_neu"):
            ctx.run(["systemctl", "disable", "--now", "gnome-remote-desktop.service"])
    for p in (*BILD_UNITS, WAYVNC_UNIT, BILD_PW, WAYVNC_CONF, *RDP_FILES):
        with contextlib.suppress(OSError):
            os.remove(ctx.path(p))


def _restart_anchor(ctx):
    if ctx.s is WIN:
        ctx.run(["schtasks", "/end", "/tn", WIN_TASK])
        ctx.run(["schtasks", "/run", "/tn", WIN_TASK])
    elif ctx.s is MAC:
        ctx.run(["/bin/launchctl", "kickstart", "-k", "system/" + MAC_JOB])
    else:
        ctx.run(["systemctl", "restart", "spark-anker.service"])


def cmd_screen(args, run=run_cmd, ctx=None):
    """`bildschirm [aus]`: the screen of this system for the panel (stage 4), or off again."""
    ctx = ctx or Ctx(run=run)
    s = ctx.s
    if ctx.euid() != 0:
        say(ctx.s.sudo)
        return 1
    conf = load(ctx.root, s)
    if not conf:
        say("erst einrichten (der Befehl aus dem Panel unter System koppeln)")
        return 1
    if getattr(args, "aus", "") == "aus":
        bild_off(ctx, conf)
        conf.pop("bild", None)
        conf.pop("grd_neu", None)
        write(ctx.path(s.conf), json.dumps(conf, indent=1), 0o640)
        with contextlib.suppress(OSError, Fehler):
            http_call(conf["url"], conf.get("fp") or "", "DELETE", "/api/fernzugang/anker/bildschirm", None, conf["key"], 10)
        _restart_anchor(ctx)
        say("Bildschirm aus: nichts davon ist mehr da")
        return 0
    if s is MAC:
        art, user = "mac", ""
        if ctx.run(["/bin/launchctl", "print", "system/com.apple.screensharing"]):
            raise Fehler("die Bildschirmfreigabe ist aus. Systemeinstellungen → Allgemein → Teilen → „Bildschirmfreigabe“ "
                         "einschalten, dann den Befehl noch einmal. Es wurde nichts geändert.")
    else:
        art, user = linux_bild_art(ctx)
    status, raw = http_call(conf["url"], conf.get("fp") or "", "POST", "/api/fernzugang/anker/bildschirm", {"art": art}, conf["key"])
    if status != 200:
        raise Fehler({404: "Bildschirm im Panel ist aus (Funktionen → Fernzugang zu Servern → Bildschirm)",
                      403: "das Panel kennt diesen Anker nicht mehr"}.get(status, f"Panel antwortet {status}"))
    d = json.loads(raw)
    pw = str(d.get("passwort") or "")
    if art != "mac" and not re.fullmatch(r"[A-Za-z0-9]{8,64}", pw):
        raise Fehler("das Panel gab kein Passwort")
    bild_off(ctx, conf)                     # a kind set up before goes first
    if art == "x11vnc":
        if not shutil.which("x11vnc") and ctx.root == "/" and ctx.run(["apt-get", "install", "-y", "-q", "x11vnc"]):
            raise Fehler("x11vnc ließ sich nicht installieren (`sudo apt install x11vnc`). Es wurde nichts geändert.")
        write(ctx.path(BILD_PW), pw + "\n", 0o600)
        write(ctx.path(BILD_UNITS[0]), UNIT_BILD_SOCKET)
        write(ctx.path(BILD_UNITS[1]), UNIT_BILD)
        ctx.run(["systemctl", "daemon-reload"])
        if ctx.run(["systemctl", "enable", "--now", "spark-anker-bild.socket"]):
            raise Fehler("systemd ließ spark-anker-bild.socket nicht starten (journalctl -u spark-anker-bild.socket)")
    elif art == "wayvnc":
        if not shutil.which("wayvnc") and ctx.root == "/" and ctx.run(["apt-get", "install", "-y", "-q", "wayvnc"]):
            raise Fehler("wayvnc ließ sich nicht installieren (`sudo apt install wayvnc`). Es wurde nichts geändert.")
        ids = ctx.ids(user)
        write(ctx.path(WAYVNC_CONF), WAYVNC_TEXT.format(port=BILD_PORT, pw=pw), 0o600)
        if ids:
            ctx.chown(ctx.path(WAYVNC_CONF), ids[0], ids[1])
        write(ctx.path(WAYVNC_UNIT), UNIT_WAYVNC.format(user=user))
        ctx.run(["systemctl", "--global", "enable", "spark-anker-wayvnc.service"])
    elif art == "grd":
        if ctx.run(["grdctl", "--system", "--help"]):
            raise Fehler("gnome-remote-desktop mit `grdctl --system` fehlt (ab GNOME 46). Es wurde nichts geändert.")
        conf["grd_neu"] = bool(ctx.run(["systemctl", "is-enabled", "--quiet", "gnome-remote-desktop.service"]))
        key, crt = (ctx.path(p) for p in RDP_FILES)
        os.makedirs(os.path.dirname(key), exist_ok=True)
        if ctx.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "3650", "-subj",
                    "/CN=spark-anker", "-keyout", key, "-out", crt]):
            raise Fehler("openssl ließ kein Zertifikat für RDP machen. Es wurde nichts geändert.")
        ids = ctx.ids("gnome-remote-desktop")
        for p in (key, crt):
            if ids:
                ctx.chown(p, ids[0], ids[1])
            with contextlib.suppress(OSError):
                os.chmod(p, 0o600)
        for cmd in (["grdctl", "--system", "rdp", "set-tls-key", key], ["grdctl", "--system", "rdp", "set-tls-cert", crt],
                    ["grdctl", "--system", "rdp", "set-credentials", RDP_USER, pw], ["grdctl", "--system", "rdp", "enable"],
                    ["systemctl", "enable", "--now", "gnome-remote-desktop.service"]):
            if ctx.run(cmd):
                raise Fehler(f"`{cmd[0]} {' '.join(cmd[1:4])}` ging nicht. `sudo spark-anker bildschirm aus` räumt auf.")
    pw = ""
    conf["bild"] = art
    write(ctx.path(s.conf), json.dumps(conf, indent=1), 0o640)
    _restart_anchor(ctx)
    say({"x11vnc": "Bildschirm eingerichtet: x11vnc startet nur, wenn das Panel den Bildschirm öffnet (127.0.0.1:5930)",
         "wayvnc": f"Bildschirm eingerichtet: wayvnc in der Sitzung von {user} (127.0.0.1:5930), ab der nächsten Anmeldung",
         "grd": "Bildschirm eingerichtet: GNOME-Remotedesktop (RDP) mit eigenem Zertifikat und Passwort aus dem Panel",
         "mac": "Bildschirm eingerichtet: die Bildschirmfreigabe von macOS; Benutzer und Passwort fragt das Panel jedes Mal"}[art])
    say("aus: sudo spark-anker bildschirm aus")
    return 0


def cmd_state(args):
    conf = load()
    if not conf:
        say("nicht eingerichtet")
        return 1
    say(f"eingerichtet für {conf['url']}" + (" (Zertifikat festgelegt)" if conf.get("fp") else "") + f", Version {VERSION}"
        + ("" if conf.get("sign_pub") else "; Aktualisieren aus dem Panel erst nach einmal `aktualisieren`"))
    if intern_ok(conf.get("intern")):
        say(f"im Heimnetz zuerst {conf['intern']['url']} (Zertifikat festgelegt)")
    return 0


# ---------------------------------------------------------------- updating: the root side
def cmd_units(args, ctx=None):
    """`einheiten` (root, from the update): the units or launchd jobs of this version; the update starts the anchor."""
    ctx = ctx or Ctx()
    if ctx.euid() != 0:
        say(ctx.s.sudo)
        return 1
    return 1 if ctx.s.units(ctx) else 0


def _wait_ok(ctx, path, version, t0, seconds):
    """The new anchor reached its panel: it wrote its version into „ok“ after t0 (lstat: never through a link)."""
    end = time.monotonic() + seconds
    while True:
        try:
            st = os.lstat(path)
            if stat.S_ISREG(st.st_mode) and st.st_mtime >= t0 - 1 and read_plain(path, 64).strip() == version.encode():
                return True
        except OSError:
            pass
        if time.monotonic() >= end:
            return False
        ctx.wait(1)


def cmd_apply(args, ctx=None, wait=UPDATE_S):
    """`aktualisieren --vom-anker` (root, spark-anker-update.path or the launchd job): checks again what the anchor
    left (pruefen against the pinned key, only newer), keeps the program before, swaps, writes the new units and
    restarts the anchor; when the new one has not reached the panel within `wait` seconds, the one before is back.
    The result (fixed word, version, time) goes to update.json beside the program for the panel."""
    ctx = ctx or Ctx()
    s = ctx.s
    if ctx.euid() != 0:
        say(ctx.s.sudo)
        return 1
    var = lambda n: ctx.path(s.var + "/" + n)
    with contextlib.suppress(OSError):
        os.unlink(var("aktualisieren"))

    def done(stand, version=""):
        with contextlib.suppress(OSError):
            write_atomic(ctx.path(s.lib + "/update.json"), json.dumps(
                {"stand": stand, "version": version, "t": int(time.time())}).encode(), 0o644)
        for n in ("neu.py", "neu.json"):
            with contextlib.suppress(OSError):
                os.unlink(var(n))
        say(f"aktualisieren: {stand}" + (f" ({version})" if version else ""))
        return 0 if stand == "ok" else 1
    conf = load(ctx.root, s)
    if not conf or not conf.get("sign_pub"):
        return done("kein_schluessel")
    try:
        meta = json.loads(read_plain(var("neu.json"), 4096))
        prog = read_plain(var("neu.py"), PROG_MAX)
    except (OSError, ValueError):
        return done("unlesbar")
    v = str(meta.get("version") or "") if isinstance(meta, dict) else ""
    if not newer(v, VERSION):
        return done("nicht_neuer", v if VER.fullmatch(v) else "")
    why = pruefen(prog, v, meta.get("sha256"), meta.get("sig"), conf["sign_pub"])
    if why:
        return done(why, v)
    path = ctx.path(s.prog)
    with open(path, "rb") as f:
        before = f.read()
    write_atomic(path + ".alt", before, 0o644)
    write_atomic(path, prog, 0o755)
    with contextlib.suppress(OSError):
        os.unlink(var("ok"))
    t0 = time.time()
    python = s.python
    if s is WIN:                 # the Python the new program names (PY_EMBED, signed with it), beside the one running
        python = win_runtime(ctx, prog)
    if python and ctx.run([python, "-I", s.prog, "einheiten"]) == 0:
        _restart_anchor(ctx)
        if _wait_ok(ctx, var("ok"), v, t0, wait):
            os.unlink(path + ".alt")
            ctx.python_neu = python
            return done("ok", v)
    write_atomic(path, before, 0o755)        # back to the one before, its own units, and started again
    os.unlink(path + ".alt")
    ctx.run([s.python, "-I", s.prog, "einheiten"])
    _restart_anchor(ctx)
    return done("zurueck", v)


def cmd_upgrade(args, ctx=None):
    """`curl … | sudo python3 - aktualisieren` (root, for an anchor before 1.3.0 too): this very program in place of the
    one set up, with the units of this version and the panel's signing key pinned; the device key, the panel's SSH key
    and the pairing stay as they are, no code. Only from the own panel (the stored address and its checked TLS), the
    program it hands out checked by SHA-256 and signature, never a step back."""
    if getattr(args, "vom_anker", False):
        return cmd_apply(args, ctx)
    ctx = ctx or Ctx()
    s = ctx.s
    if ctx.euid() != 0:
        say(ctx.s.sudo)
        return 1
    conf = load(ctx.root, s)
    if not conf:
        say("nicht eingerichtet: erst `einrichten` mit der Zeile aus dem Panel (+ System koppeln)")
        return 1
    status, raw = http_call(conf["url"], conf.get("fp") or "", "GET", "/api/fernzugang/anker/stand", None, conf["key"])
    if status != 200:
        raise Fehler({403: "das Panel kennt diesen Server nicht mehr: neu koppeln", 404: "Fernzugang im Panel ist aus"}
                     .get(status, f"Panel antwortet {status}"))
    d = json.loads(raw)
    if d.get("version") != VERSION:
        raise Fehler("das Panel hat inzwischen ein anderes Programm: die Zeile aus dem Panel noch einmal")
    status, prog = http_call(conf["url"], conf.get("fp") or "", "GET", "/fernzugang/anker")
    why = "laden" if status != 200 else pruefen(prog, VERSION, d.get("sha256"), d.get("sig"), d.get("sign_pub"))
    if why:
        raise Fehler(f"das Programm vom Panel ließ sich nicht prüfen ({why}); es wurde nichts geändert")
    path = ctx.path(s.prog)
    try:
        with open(path, "rb") as f:
            installed = prog_version(f.read(PROG_MAX))
    except OSError:
        installed = ""
    if installed and newer(installed, VERSION):
        raise Fehler(f"hier läuft schon {installed}, neuer als {VERSION}: es wurde nichts geändert")
    write_atomic(path, prog, 0o755)
    conf["sign_pub"] = d["sign_pub"]
    write(ctx.path(s.conf), json.dumps(conf, indent=1), 0o640)
    runner = ctx.ids(s.runner)
    if runner:
        ctx.chown(ctx.path(s.conf), 0, runner[1])
    s.units(ctx)
    _restart_anchor(ctx)
    say(f"aktualisiert: {installed or 'vorher'} → {VERSION}; Kopplung und Schlüssel bleiben, {s.started}")
    return 0


# ---------------------------------------------------------------- Spontanhilfe S3: once, in the person's terminal
HILFE_PFAD = "/api/hilfe/shell"
NUMMER = re.compile(r"\d{6}")
HILFE_START = ("Spark-Hilfe: Hier geben Sie die Nummer ein, die Ihnen genannt wurde, und Ihren Vornamen. Erst wenn Sie "
               "danach „j“ tippen, arbeitet die helfende Person in dieser Shell, mit Ihren Rechten; Sie sehen alles mit. "
               "Strg+C beendet jederzeit, danach bleibt nichts zurück.\n")
HILFE_FEHLER = {"nummer": "Nummer nicht gültig. Bitte die Nummer noch einmal erfragen; es wurde nichts verbunden.",
                "name": "Bitte nur den Vornamen eingeben (Buchstaben, bis 30). Es wurde nichts verbunden."}


class Tty:
    """The person's terminal (/dev/tty: stdin is the program itself under curl): lines typed, the shell's output shown.
    While the helper works: no echo and no line mode (Strg+C stays a signal); afterwards always as it was."""

    def __init__(self, rfd, wfd):
        self.rfd, self.wfd, self.buf, self.saved = rfd, wfd, b"", None

    @classmethod
    def open(cls):
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        return cls(fd, fd)

    def write(self, data):
        data = data.encode() if isinstance(data, str) else data
        while data:
            data = data[os.write(self.wfd, data):]

    def feed(self):
        part = os.read(self.rfd, 1024)
        if not part:
            raise EOFError
        self.buf += part

    def line(self):
        if b"\n" not in self.buf:
            return None
        ln, _, self.buf = self.buf.partition(b"\n")
        return ln.decode(errors="replace").strip()

    def ask(self, prompt):
        self.write(prompt)
        while True:
            ln = self.line()
            if ln is not None:
                return ln
            self.feed()

    def take(self):
        data, self.buf = self.buf, b""
        return data

    def quiet(self):
        try:
            import termios
            self.saved = termios.tcgetattr(self.rfd)
            new = termios.tcgetattr(self.rfd)
            new[3] &= ~(termios.ECHO | termios.ICANON)
            termios.tcsetattr(self.rfd, termios.TCSANOW, new)
        except Exception:       # no terminal (a pipe in the tests): nothing to switch
            self.saved = None

    def restore(self):
        if self.saved is not None:
            import termios
            with contextlib.suppress(Exception):
                termios.tcsetattr(self.rfd, termios.TCSANOW, self.saved)
            self.saved = None

    def close(self):
        self.restore()
        with contextlib.suppress(OSError):
            os.close(self.rfd)


class Hilfe:
    """One Spontanhilfe: the panel's socket, the person's terminal and (after her „j“) her shell in a PTY. One thread
    for everything, like Lauf."""

    def __init__(self, ws, tty, shell=None):
        self.ws, self.tty = ws, tty
        self.shell = shell or pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
        self.pid = self.fd = None
        self.size = (80, 24)
        self.admin, self.stand = "Admin", "hallo"

    def _say(self, text):
        self.tty.write(f"\r\nSpark-Hilfe: {text}\r\n")

    def _winsize(self):
        if self.fd is not None:
            import fcntl
            import termios
            with contextlib.suppress(OSError):
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.size[1], self.size[0], 0, 0))

    def _start(self):
        import pty
        pid, fd = pty.fork()
        if pid == 0:            # the child: her own shell, her rights, her home
            try:
                with contextlib.suppress(OSError):
                    os.chdir(os.path.expanduser("~"))
                os.putenv("TERM", "xterm-256color")     # otherwise her own variables, as in her terminal
                os.execv(self.shell, ["-" + os.path.basename(self.shell)])
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        self._winsize()
        self.tty.quiet()

    def _stop(self):
        fd, pid, self.fd, self.pid = self.fd, self.pid, None, None
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        if pid:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGHUP)
            for n in range(40):
                with contextlib.suppress(ChildProcessError):
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        break
                if n == 20:
                    with contextlib.suppress(OSError):
                        os.kill(pid, signal.SIGKILL)
                time.sleep(0.05)
        self.tty.restore()

    def _control(self, m):
        """A message of the panel; a number when the help is over."""
        t = m.get("typ")
        if t == "fehler":
            raise Fehler(HILFE_FEHLER.get(m.get("grund"), "Das Panel hat abgelehnt. Es wurde nichts verbunden."))
        if t == "stand" and m.get("stand") == "wartet":
            self.stand, self.admin = "wartet", WORD.sub("", str(m.get("admin") or "Admin"))[:40] or "Admin"
            self._say(f"verbunden. {self.admin} nimmt gleich an. Strg+C bricht ab.")
        elif t == "stand" and m.get("stand") == "frage" and self.stand == "wartet":
            self.stand = "frage"
            self.tty.buf = b""
            self.tty.write(f"\r\nSpark-Hilfe: {self.admin} möchte jetzt in dieser Shell arbeiten, mit Ihren Rechten. "
                           "Erlauben? [j/n] ")
        elif t == "stand" and m.get("stand") == "zu":
            self._say("die Hilfe ist beendet. Es bleibt nichts zurück.")
            return 0
        elif t == "groesse":
            c, r = m.get("cols"), m.get("rows")
            if isinstance(c, int) and isinstance(r, int) and 2 <= c <= 500 and 1 <= r <= 300:
                self.size = (c, r)
                self._winsize()
        elif t == "zeit" and isinstance(m.get("rest"), int):
            self._say(f"verlängert, noch {m['rest'] // 60} Minuten.")
        return None

    def _answer(self, ln):
        if ln.lower() in ("j", "ja", "y", "yes"):
            self.ws.send_json({"typ": "erlaubt", "an": True})
            self.stand = "offen"
            self._say(f"{self.admin} arbeitet jetzt in Ihrer Shell, mit Ihren Rechten. Sie sehen alles mit und können "
                      "mittippen. Strg+C beendet sofort.")
            self._start()
            return None
        self.ws.send_json({"typ": "erlaubt", "an": False})
        self._say("abgelehnt. Es bleibt nichts zurück.")
        return 0

    def run(self, nummer, name):
        self.ws.send_json({"typ": "hallo", "nummer": nummer, "name": name, "os": os_name()})
        last = time.monotonic()
        try:
            while True:
                while True:     # whole messages already read
                    got = self.ws.frame()
                    if got is None:
                        break
                    op, data = got
                    if op == 2:
                        if self.fd is not None:
                            while data:
                                data = data[os.write(self.fd, data):]
                        continue
                    try:
                        m = json.loads(data.decode())
                    except ValueError:
                        continue
                    if isinstance(m, dict) and self._control(m) is not None:
                        return 0
                if time.monotonic() - last > PING_S:
                    self.ws.send(b"", 9)
                    last = time.monotonic()
                watch = [self.ws.sock, self.tty.rfd] + ([self.fd] if self.fd is not None else [])
                ready, _, _ = select.select(watch, [], [], 0 if self.ws.sock.pending() else 1)
                if self.ws.sock.pending() and self.ws.sock not in ready:
                    ready.append(self.ws.sock)
                for r in ready:
                    if r is self.ws.sock:
                        if not self.ws.feed():
                            raise EOFError
                    elif self.fd is not None and r == self.fd:
                        try:
                            data = os.read(self.fd, 8192)
                        except OSError:
                            data = b""
                        if not data:
                            self.ws.send_json({"typ": "ende"})
                            self._say("die Shell ist beendet. Es bleibt nichts zurück.")
                            return 0
                        self.ws.send(data, 2)
                        self.tty.write(data)
                    elif r == self.tty.rfd:
                        self.tty.feed()
                        if self.stand == "frage":
                            ln = self.tty.line()
                            if ln is not None and self._answer(ln) is not None:
                                return 0
                        elif self.fd is not None:
                            data = self.tty.take()
                            while data:
                                data = data[os.write(self.fd, data):]
                        else:
                            self.tty.take()     # typed while waiting: goes nowhere
        except KeyboardInterrupt:
            with contextlib.suppress(OSError):
                self.ws.send_json({"typ": "ende"})
            self._say("beendet mit Strg+C. Es bleibt nichts zurück.")
            return 0
        except EOFError:
            if self.stand == "hallo":
                raise Fehler("Das Panel hat abgelehnt (Spontanhilfe aus, Nummer nicht gültig oder zu viele Versuche). "
                             "Es wurde nichts verbunden.")
            self._say("die Verbindung ist zu. Es bleibt nichts zurück.")
            return 0
        finally:
            self._stop()
            self.ws.close()


def as_root():
    return os.geteuid() == 0


def cmd_help(args, tty=None, shell=None):
    """`hilfe adresse [--fp]`: one Spontanhilfe in this terminal, never as root, nothing set up."""
    if as_root():
        raise Fehler("Spontanhilfe nie als root: den Befehl ohne sudo nehmen. Es wurde nichts verbunden.")
    base = base_url(args.adresse)
    fp = (args.fp or "").lower()
    if fp and not FP.fullmatch(fp):
        raise Fehler("--fp: der SHA-256 aus dem Befehl des Panels (64 Zeichen 0-9 a-f)")
    t = tty or Tty.open()
    try:
        t.write(HILFE_START)
        nummer = t.ask("Nummer (6 Ziffern): ").replace(" ", "")
        if not NUMMER.fullmatch(nummer):
            raise Fehler("Die Nummer hat 6 Ziffern. Es wurde nichts verbunden.")
        name = t.ask("Ihr Vorname: ")
        try:
            ws = WS.open(base, fp, HILFE_PFAD, "")
        except Fehler as e:
            if str(e).startswith("Panel antwortet"):
                raise Fehler("Das Panel hat abgelehnt (Spontanhilfe aus oder gerade gesperrt). Es wurde nichts verbunden.")
            raise
        return Hilfe(ws, t, shell).run(nummer, name)
    finally:
        if tty is None:
            t.close()
        else:
            t.restore()


# What the anchor does not do on a system (yet): a fixed sentence and nothing done, never half a setup.
NOT_YET = {
    ("Windows", "bildschirm"): "Den Bildschirm unter Windows richtet der Anker noch nicht ein (eine spätere Stufe). Es wurde nichts eingerichtet.",
    ("Windows", "hilfe"): "Die Spontanhilfe in der Shell gibt es unter Windows noch nicht; „Bildschirm teilen“ auf der Hilfe-Seite geht. Es wurde nichts verbunden.",
}


def not_yet(cmd, system=None):
    """The fixed sentence for what the anchor cannot do on this system, else None."""
    return NOT_YET.get((system or platform.system(), cmd))


def main(argv=None, system=None):
    p = argparse.ArgumentParser(prog="spark-anker", description="Fernzugang des Spark-Panels zu diesem sshd")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("einrichten", help="einmal einrichten (fragt den Code im Terminal)")
    a.add_argument("adresse", help="https-Adresse des Panels")
    a.add_argument("--fp", default="", help="SHA-256 des Panel-Zertifikats (steht im Befehl aus dem Panel)")
    a.add_argument("--token", default="", choices=["", "-"], help=argparse.SUPPRESS)   # Windows file: its key on stdin
    a.add_argument("--sshd-neu", action="store_true", help=argparse.SUPPRESS)       # Windows file: it added OpenSSH Server
    r = sub.add_parser("entfernen", help="alles entfernen, was der Anker eingerichtet hat")
    r.add_argument("--vom-panel", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("lauf", help="der Dienst (startet systemd, launchd oder die Aufgabenplanung)")
    sub.add_parser("zustand", help="eingerichtet? welches Panel?")
    u = sub.add_parser("aktualisieren", help="dieses Programm anstelle des eingerichteten (ohne Code, Kopplung bleibt)")
    u.add_argument("--vom-anker", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("einheiten", help=argparse.SUPPRESS)
    sub.add_parser("waechter", help=argparse.SUPPRESS)
    b = sub.add_parser("bildschirm", help="den Bildschirm für das Panel einrichten (oder `bildschirm aus`)")
    b.add_argument("aus", nargs="?", default="", choices=["", "aus"], help="aus: alles vom Bildschirm wieder weg")
    h = sub.add_parser("hilfe", help="Spontanhilfe: einmal, in diesem Terminal, ohne sudo (fragt die Nummer)")
    h.add_argument("adresse", help="https-Adresse des Panels")
    h.add_argument("--fp", default="", help="SHA-256 des Panel-Zertifikats (steht im Befehl aus dem Panel)")
    args = p.parse_args(argv)
    stop = not_yet(args.cmd, system)
    if stop:
        say(stop)
        return 1
    try:
        return {"einrichten": cmd_setup, "entfernen": cmd_remove, "lauf": cmd_run, "zustand": cmd_state,
                "hilfe": cmd_help, "bildschirm": cmd_screen, "aktualisieren": cmd_upgrade, "einheiten": cmd_units,
                "waechter": cmd_watch}[args.cmd](args)
    except Fehler as e:
        say(str(e))
        return 1
    except (KeyboardInterrupt, EOFError):
        say("abgebrochen. " + ("Es wurde nichts eingerichtet." if args.cmd == "einrichten" else
                               "Es wurde nichts verbunden." if args.cmd == "hilfe" else ""))
        return 1
    except ssl.SSLCertVerificationError:
        say(CERT_FEHLER)
        return 1
    except (ssl.SSLError, ConnectionError, socket.timeout, socket.gaierror) as e:
        say(f"das Panel war nicht zu erreichen ({type(e).__name__}): Adresse und Netz prüfen, dann den Befehl noch einmal.")
        return 1


# the one sentence when the panel's certificate cannot be checked (never a traceback, never without the check)
CERT_FEHLER = ("das Zertifikat des Panels ließ sich nicht prüfen (keine oder keine passende Zertifizierungsstelle). "
               "Abhilfe auf dem Mac: den Befehl mit /usr/bin/python3 statt python3; sonst den Befehl aus dem Panel "
               "über die Heim-Adresse nehmen (mit --fp). Es wurde nichts eingerichtet.")


if __name__ == "__main__":
    sys.exit(main())
