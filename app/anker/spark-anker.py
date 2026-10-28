#!/usr/bin/env python3
"""spark-anker: lets the own Speech-on-DGX-Spark panel reach this server's SSH (Fernzugang → Fern-Server). Linux and macOS.

    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - einrichten https://<panel>   set up once (asks the code)
    sudo spark-anker entfernen                                                              removes everything again
    curl -fsSL https://<panel>/fernzugang/anker | sudo python3 - entfernen                  the same without the program
    spark-anker zustand                                                                     set up? which panel?

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
import struct
import subprocess
import sys
import threading
import time
import urllib.parse

VERSION = "1.0.0"
LIB = "/usr/local/lib/spark-anker"
PROG = LIB + "/spark-anker.py"
BIN = "/usr/local/bin/spark-anker"
ETC = "/etc/spark-anker"
CONF = ETC + "/anker.json"
VAR = "/var/lib/spark-anker"
FLAG = VAR + "/abbauen"
UNITS = ("/etc/systemd/system/spark-anker.service", "/etc/systemd/system/spark-anker-abbau.path",
         "/etc/systemd/system/spark-anker-abbau.service")
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
WORD = re.compile(r"[^A-Za-z0-9._\- ()/+]")

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
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\nAuthorization: Bearer {key}\r\n"
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

    def __init__(self, ws):
        self.ws = ws
        self.kanaele = {}      # n -> socket to the own sshd

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
        if m.get("typ") == "auf" and isinstance(n, int) and 1 <= n < 64 and n not in self.kanaele:
            try:
                s = socket.create_connection(SSHD, timeout=10)   # only the own sshd, never another address
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
        self.ws.send_json({"typ": "hallo", "os": os_name(), "version": VERSION})
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
            if Lauf(ws).run() == "abbauen":
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


def linux_start(ctx, runner):
    for path, text in zip(UNITS, (UNIT_RUN, UNIT_PATH, UNIT_ABBAU)):
        write(ctx.path(path), text)
    ctx.run(["systemctl", "daemon-reload"])
    if ctx.run(["systemctl", "enable", "--now", "spark-anker.service", "spark-anker-abbau.path"]):
        raise Fehler("systemd ließ den Dienst nicht starten (journalctl -u spark-anker)")


def linux_stop(ctx, conf):
    ctx.run(["systemctl", "disable", "--now", "spark-anker.service", "spark-anker-abbau.path"])


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
MAC_PLISTS = ("/Library/LaunchDaemons/" + MAC_JOB + ".plist", "/Library/LaunchDaemons/" + MAC_JOB_ABBAU + ".plist")
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


def mac_start(ctx, runner):
    var = ctx.path(MAC_VAR)
    os.makedirs(var, mode=0o700, exist_ok=True)
    ctx.chown(var, runner[0], runner[1])
    for path, label, args, extra in ((MAC_PLISTS[0], MAC_JOB, "<string>lauf</string>", MAC_RUN_EXTRA),
                                     (MAC_PLISTS[1], MAC_JOB_ABBAU, "<string>entfernen</string><string>--vom-panel</string>", MAC_ABBAU_EXTRA)):
        write(ctx.path(path), MAC_PLIST.format(label=label, prog=MAC.prog, args=args, extra=extra), 0o644)
        ctx.chown(ctx.path(path), 0, 0)
        if ctx.run(["/bin/launchctl", "bootstrap", "system", path]):
            raise Fehler(f"launchd ließ den Dienst nicht starten (sudo launchctl print system/{label})")


def mac_stop(ctx, conf):
    ctx.run(["/bin/launchctl", "bootout", "system/" + MAC_JOB])


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
               runner=RUNNER, check=linux_check, users=linux_users, start=linux_start, stop=linux_stop,
               after=linux_after, last=linux_last, started="der Dienst spark-anker läuft")
MAC = System(name="Darwin", lib=MAC_LIB, prog=MAC_LIB + "/spark-anker.py", bin=BIN,
             etc=MAC_ETC, conf=MAC_ETC + "/anker.json", var=MAC_VAR, flag=MAC_VAR + "/abbauen", services=MAC_PLISTS,
             runner=MAC_RUNNER, check=mac_check, users=mac_users, start=mac_start, stop=mac_stop,
             after=mac_after, last=mac_last, started="der Dienst de.speech-spark.anker läuft (launchd)")


def cmd_setup(args, code_reader=read_code, run=run_cmd, ctx=None):
    ctx = ctx or Ctx(run=run)
    s = ctx.s
    if ctx.euid() != 0:
        say("bitte mit sudo")
        return 1
    if load(ctx.root, s):
        say("schon eingerichtet; erst `sudo spark-anker entfernen`")
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
    return [here(root, p) for p in (*s.services, s.bin, s.lib, s.etc, s.var)]


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


def cmd_state(args):
    conf = load()
    if not conf:
        say("nicht eingerichtet")
        return 1
    say(f"eingerichtet für {conf['url']}" + (" (Zertifikat festgelegt)" if conf.get("fp") else "") + f", Version {VERSION}")
    return 0


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
    args = p.parse_args(argv)
    try:
        return {"einrichten": cmd_setup, "entfernen": cmd_remove, "lauf": cmd_run, "zustand": cmd_state}[args.cmd](args)
    except Fehler as e:
        say(str(e))
        return 1
    except (KeyboardInterrupt, EOFError):
        say("abgebrochen. " + ("Es wurde nichts eingerichtet." if args.cmd == "einrichten" else ""))
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
