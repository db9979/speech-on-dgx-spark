#!/usr/bin/env python3
"""spark-anker: lets the own Speech-on-DGX-Spark panel reach this server's SSH (Fernzugang → Systeme). Linux and macOS.

    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - einrichten https://<panel>   set up once (asks the code)
    sudo spark-anker entfernen                                                              removes everything again
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - entfernen                  the same without the program
    spark-anker zustand                                                                     set up? which panel?
    curl -fsSL https://<panel>/fernzugang/anker | python3 - hilfe https://<panel>           Spontanhilfe (S3): once
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - bildschirm                 the screen too (stage 4)
    sudo spark-anker bildschirm aus                                                         the screen off again
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - aktualisieren              this program anew (no code)

It calls the panel by itself (WebSocket over TLS, the panel's normal https address, no port opened here) and passes
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
import base64
import contextlib
import hashlib
import hmac
import http.client
import json
import os
import platform
import pwd
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

VERSION = "1.3.0"
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
MAX_MSG = 64 * 1024       # the panel takes no bigger message
CHUNK = 32 * 1024
PING_S = 25               # keeps the reverse proxy from closing a quiet connection
MARK = "spark-fernzugang-"  # the comment of the panel's line in authorized_keys
BILD_PORT = 5930          # x11vnc and wayvnc: only on 127.0.0.1
BILD = {"x11vnc": BILD_PORT, "wayvnc": BILD_PORT, "grd": 3389, "mac": 5900}   # the screen's one local port per kind
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
    print(f"spark-anker: {text}", flush=True)


def here(root, path):
    """path below root (/ normally; a temporary folder in the tests)."""
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
    try:
        with open("/etc/os-release") as f:
            m = re.search(r'^PRETTY_NAME="?([^"\n]*)', f.read(), re.M)
        name = m.group(1) if m else platform.system()
    except OSError:
        name = platform.system()
    return WORD.sub("", name)[:40]


class Lauf:
    """One connection to the panel: channels to the own sshd, nothing else. One thread for everything (a TLS socket
    is never read and written from two threads at once)."""

    def __init__(self, ws, bild="", conf=None, ctx=None):
        self.ws = ws
        self.bild = bild if bild in BILD else ""   # the screen's kind (`bildschirm`), its one port in BILD
        self.kanaele = {}      # n -> socket to the own sshd (or the screen's port)
        self.conf = conf or {}
        self.ctx = ctx or Ctx()

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
        if m.get("typ") == "auf" and isinstance(n, int) and 1 <= n < 64 and n not in self.kanaele:
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

    def run(self):
        self.ws.send_json({"typ": "hallo", "os": os_name(), "version": VERSION, "bild": self.bild,
                           "update": self._stand()})
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
                        if s is not None:
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
                wait = 0 if self.ws.sock.pending() else 1
                ready, _, _ = select.select([self.ws.sock, *self.kanaele.values()], [], [], wait)
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
                    except OSError:
                        data = b""
                    if data:
                        self.ws.send(bytes([n]) + data, 2)
                    else:
                        self._close(n, True)
        finally:
            for n in list(self.kanaele):
                self._close(n, False)


def cmd_run(args):
    conf = load()
    if not conf:
        say("nicht eingerichtet")
        return 1
    pause = 5
    while True:
        try:
            ws = WS.open(conf["url"], conf.get("fp") or "", "/api/fernzugang/anker", conf["key"])
            say("mit dem Panel verbunden")
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
    terminal always as it was afterwards. Without echo control the code is read visibly, with a hint."""
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
        self.s = MAC if (system or platform.system()) == "Darwin" else LINUX
        self.root = root
        self.run = run

    def path(self, p):
        return here(self.root, p)

    def out(self, cmd):
        """A command's output (empty when it fails); only for reading (dscl -list)."""
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

    def euid(self):
        return os.geteuid()

    def ids(self, name):
        """(uid, gid, home) of a user, None when there is none."""
        try:
            pw = pwd.getpwnam(name)
        except KeyError:
            return None
        return pw.pw_uid, pw.pw_gid, pw.pw_dir

    def chown(self, path, uid, gid):
        os.chown(path, uid, gid)

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


class System:
    def __init__(self, **kw):
        self.__dict__.update(kw)


LINUX = System(name="Linux", lib=LIB, prog=PROG, bin=BIN, etc=ETC, conf=CONF, var=VAR, flag=FLAG, services=UNITS,
               python="/usr/bin/python3", units=linux_units,
               runner=RUNNER, check=linux_check, users=linux_users, start=linux_start, stop=linux_stop,
               after=linux_after, last=linux_last, started="der Dienst spark-anker läuft")
MAC = System(name="Darwin", lib=MAC_LIB, prog=MAC_LIB + "/spark-anker.py", bin=BIN,
             etc=MAC_ETC, conf=MAC_ETC + "/anker.json", var=MAC_VAR, flag=MAC_VAR + "/abbauen", services=MAC_PLISTS,
             python=MAC_PY, units=mac_units, runner=MAC_RUNNER, check=mac_check, users=mac_users, start=mac_start, stop=mac_stop,
             after=mac_after, last=mac_last, started="der Dienst de.speech-spark.anker läuft (launchd)")


def cmd_setup(args, code_reader=read_code, run=run_cmd, ctx=None):
    ctx = ctx or Ctx(run=run)
    s = ctx.s
    if ctx.euid() != 0:
        say("bitte mit sudo")
        return 1
    if load(ctx.root, s):
        say("schon eingerichtet. Neue Version: `curl -fsSL <Panel>/fernzugang/anker | sudo python3 - aktualisieren` "
            "(die Zeile steht im Panel beim System; Kopplung und Schlüssel bleiben). Neu koppeln: erst `sudo spark-anker entfernen`")
        return 1
    base = base_url(args.adresse)
    fp = (args.fp or "").lower()
    if fp and not FP.fullmatch(fp):
        raise Fehler("--fp: 64 Zeichen 0-9 a-f")
    state = s.check(ctx)
    with open(ctx.path(HOSTKEY)) as f:
        hostkey = " ".join(f.read().split()[:2])
    sock, got = tls_connect(base, fp)
    sock.close()
    say(f"Panel {base}, Zertifikat SHA-256 {got[:16]}…{got[-8:]}" + (" (festgelegt)" if fp else " (geprüft gegen die Zertifizierungsstellen)"))
    code = code_reader()
    status, raw = http_call(base, fp, "POST", "/api/fernzugang/anker/koppeln",
                            {"code": code, "hostkey": hostkey, "os": os_name(s), "version": VERSION})
    code = ""
    if status != 200:
        raise Fehler({403: "Code falsch oder abgelaufen", 404: "Fernzugang im Panel ist aus",
                      409: "zu viele Server gekoppelt", 429: "zu viele Versuche, später noch einmal"}.get(status, f"Panel antwortet {status}"))
    d = json.loads(raw)
    status, prog = http_call(base, fp, "GET", "/fernzugang/anker")
    if status != 200 or not hmac.compare_digest(hashlib.sha256(prog).hexdigest(), str(d.get("anker_sha256", ""))):
        raise Fehler("das Programm vom Panel passt nicht zu seiner Prüfsumme")
    conf = {"url": base, "fp": fp, "id": d["id"], "key": d["key"], "user_neu": not ctx.ids(USER), "seit": int(time.time()),
            **state}
    if _b64(d.get("sign_pub"), 32):            # the panel's signing key for updates, pinned with the pairing
        conf["sign_pub"] = d["sign_pub"]
    user, runner = s.users(ctx, conf)
    ssh = ctx.path(os.path.join(user[2], ".ssh"))
    os.makedirs(ssh, mode=0o700, exist_ok=True)
    ak = os.path.join(ssh, "authorized_keys")
    with open(ak, "a") as f:
        f.write(key_line(str(d["pi_key"])) + "\n")
    for p, m in ((ssh, 0o700), (ak, 0o600)):
        ctx.chown(p, user[0], user[1])
        os.chmod(p, m)
    write(ctx.path(s.prog), prog.decode(), 0o755)
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
    say("entfernen: sudo spark-anker entfernen (oder im Panel „Entfernen“)")
    return 0


# ---------------------------------------------------------------- removing everything
def remove_paths(root="/", s=None):
    """Every path the anchor made (the user spark's home only when the anchor made the user)."""
    s = s or LINUX
    extra = (*BILD_UNITS, WAYVNC_UNIT) if s is LINUX else ()
    return [here(root, p) for p in (*s.services, *extra, s.bin, s.lib, s.etc, s.var)]


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
        say("bitte mit sudo")
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
    if ctx.s is MAC:
        ctx.run(["/bin/launchctl", "kickstart", "-k", "system/" + MAC_JOB])
    else:
        ctx.run(["systemctl", "restart", "spark-anker.service"])


def cmd_screen(args, run=run_cmd, ctx=None):
    """`bildschirm [aus]`: the screen of this system for the panel (stage 4), or off again."""
    ctx = ctx or Ctx(run=run)
    s = ctx.s
    if ctx.euid() != 0:
        say("bitte mit sudo")
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
    return 0


# ---------------------------------------------------------------- updating: the root side
def cmd_units(args, ctx=None):
    """`einheiten` (root, from the update): the units or launchd jobs of this version; the update starts the anchor."""
    ctx = ctx or Ctx()
    if ctx.euid() != 0:
        say("bitte mit sudo")
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
        say("bitte mit sudo")
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
    if ctx.run([s.python, "-I", s.prog, "einheiten"]) == 0:
        _restart_anchor(ctx)
        if _wait_ok(ctx, var("ok"), v, t0, wait):
            os.unlink(path + ".alt")
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
        say("bitte mit sudo")
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


# Systems the anchor does not set up (yet): a fixed sentence and nothing done, never half a setup.
NOT_YET = {
    "Windows": "Windows wird ab einer späteren Version unterstützt (Stufe 5); bitte Panel aktualisieren. Es wurde nichts eingerichtet.",
}


def not_yet(system=None):
    """The fixed sentence for a system the anchor cannot set up, else None (Linux, macOS)."""
    return NOT_YET.get(system or platform.system())


def main(argv=None, system=None):
    stop = not_yet(system)
    if stop:
        say(stop)
        return 1
    p = argparse.ArgumentParser(prog="spark-anker", description="Fernzugang des Spark-Panels zu diesem sshd")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("einrichten", help="einmal einrichten (fragt den Code im Terminal)")
    a.add_argument("adresse", help="https-Adresse des Panels")
    a.add_argument("--fp", default="", help="SHA-256 des Panel-Zertifikats (steht im Befehl aus dem Panel)")
    r = sub.add_parser("entfernen", help="alles entfernen, was der Anker eingerichtet hat")
    r.add_argument("--vom-panel", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("lauf", help="der Dienst (startet systemd bzw. launchd)")
    sub.add_parser("zustand", help="eingerichtet? welches Panel?")
    u = sub.add_parser("aktualisieren", help="dieses Programm anstelle des eingerichteten (ohne Code, Kopplung bleibt)")
    u.add_argument("--vom-anker", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("einheiten", help=argparse.SUPPRESS)
    b = sub.add_parser("bildschirm", help="den Bildschirm für das Panel einrichten (oder `bildschirm aus`)")
    b.add_argument("aus", nargs="?", default="", choices=["", "aus"], help="aus: alles vom Bildschirm wieder weg")
    h = sub.add_parser("hilfe", help="Spontanhilfe: einmal, in diesem Terminal, ohne sudo (fragt die Nummer)")
    h.add_argument("adresse", help="https-Adresse des Panels")
    h.add_argument("--fp", default="", help="SHA-256 des Panel-Zertifikats (steht im Befehl aus dem Panel)")
    args = p.parse_args(argv)
    try:
        return {"einrichten": cmd_setup, "entfernen": cmd_remove, "lauf": cmd_run, "zustand": cmd_state,
                "hilfe": cmd_help, "bildschirm": cmd_screen, "aktualisieren": cmd_upgrade, "einheiten": cmd_units}[args.cmd](args)
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
