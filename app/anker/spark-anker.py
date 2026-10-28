#!/usr/bin/env python3
"""spark-anker: lets the own Speech-on-DGX-Spark panel reach this server's SSH (Funktionen → Fernzugang).

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

Removing (`entfernen`, or „Entfernen“ in the panel): stops and deletes both units, the program, the configuration,
the anchor's folder, the user spark-anker, the panel's line in authorized_keys and the user spark with its home when
the anchor made it; then it tells the panel (best effort) so it forgets this server too.
"""
import argparse
import base64
import getpass
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
        ctx = ssl.create_default_context()
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


# ---------------------------------------------------------------- running (systemd unit spark-anker)
def load(root="/"):
    try:
        with open(here(root, CONF)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("url") and d.get("key") else None


def os_name():
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
                    with open(FLAG, "w") as f:   # spark-anker-abbau.path (root) runs `entfernen`
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


def read_code():
    """The pairing code, typed on this terminal and shown nowhere (getpass reads /dev/tty)."""
    return getpass.getpass("Kopplungs-Code aus dem Panel: ").strip()


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


def cmd_setup(args, code_reader=read_code, run=run_cmd):
    if os.geteuid() != 0:
        say("bitte mit sudo")
        return 1
    if load():
        say("schon eingerichtet; erst `sudo spark-anker entfernen`")
        return 1
    base = base_url(args.adresse)
    fp = (args.fp or "").lower()
    if fp and not FP.fullmatch(fp):
        raise Fehler("--fp: 64 Zeichen 0-9 a-f")
    try:
        with open(HOSTKEY) as f:
            hostkey = " ".join(f.read().split()[:2])
    except OSError:
        raise Fehler(f"{HOSTKEY} fehlt: sshd mit einem ed25519-Schlüssel ist nötig")
    try:
        socket.create_connection(SSHD, timeout=3).close()
    except OSError:
        raise Fehler("sshd hört nicht auf 127.0.0.1:22")
    s, got = tls_connect(base, fp)
    s.close()
    say(f"Panel {base}, Zertifikat SHA-256 {got[:16]}…{got[-8:]}" + (" (festgelegt)" if fp else " (geprüft gegen die Zertifizierungsstellen)"))
    code = code_reader()
    status, raw = http_call(base, fp, "POST", "/api/fernzugang/anker/koppeln",
                            {"code": code, "hostkey": hostkey, "os": os_name(), "version": VERSION})
    code = ""
    if status != 200:
        raise Fehler({403: "Code falsch oder abgelaufen", 404: "Fernzugang im Panel ist aus",
                      409: "zu viele Server gekoppelt", 429: "zu viele Versuche, später noch einmal"}.get(status, f"Panel antwortet {status}"))
    d = json.loads(raw)
    status, prog = http_call(base, fp, "GET", "/fernzugang/anker")
    if status != 200 or not hmac.compare_digest(hashlib.sha256(prog).hexdigest(), str(d.get("anker_sha256", ""))):
        raise Fehler("das Programm vom Panel passt nicht zu seiner Prüfsumme")
    made = not user_exists(USER)
    if made and run(["useradd", "--create-home", "--shell", "/bin/bash", USER]):
        raise Fehler(f"Benutzer {USER} ließ sich nicht anlegen")
    if not user_exists(RUNNER) and run(["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", RUNNER]):
        raise Fehler(f"Benutzer {RUNNER} ließ sich nicht anlegen")
    pw = pwd.getpwnam(USER)
    ssh = os.path.join(pw.pw_dir, ".ssh")
    os.makedirs(ssh, mode=0o700, exist_ok=True)
    ak = os.path.join(ssh, "authorized_keys")
    with open(ak, "a") as f:
        f.write(key_line(str(d["pi_key"])) + "\n")
    for p, m in ((ssh, 0o700), (ak, 0o600)):
        os.chown(p, pw.pw_uid, pw.pw_gid)
        os.chmod(p, m)
    write(PROG, prog.decode(), 0o755)
    if os.path.lexists(BIN):
        os.remove(BIN)
    os.symlink(PROG, BIN)
    conf = {"url": base, "fp": fp, "id": d["id"], "key": d["key"], "user_neu": made, "seit": int(time.time())}
    write(CONF, json.dumps(conf, indent=1), 0o640)
    os.chown(CONF, 0, pwd.getpwnam(RUNNER).pw_gid)
    os.chown(ETC, 0, pwd.getpwnam(RUNNER).pw_gid)
    os.chmod(ETC, 0o750)
    for path, text in zip(UNITS, (UNIT_RUN, UNIT_PATH, UNIT_ABBAU)):
        write(path, text)
    run(["systemctl", "daemon-reload"])
    if run(["systemctl", "enable", "--now", "spark-anker.service", "spark-anker-abbau.path"]):
        raise Fehler("systemd ließ den Dienst nicht starten (journalctl -u spark-anker)")
    say(f"eingerichtet: der Panel-Schlüssel darf als {USER} nur über den Anker herein; der Dienst spark-anker läuft")
    say("entfernen: sudo spark-anker entfernen (oder im Panel „Entfernen“)")
    return 0


# ---------------------------------------------------------------- removing everything
def remove_paths(root="/"):
    """Every path the anchor made (the user spark's home only when the anchor made the user)."""
    return [here(root, p) for p in (*UNITS, BIN, LIB, ETC, VAR)]


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


def cmd_remove(args, root="/", run=run_cmd, tell=True, home=None):
    if root == "/" and os.geteuid() != 0:
        say("bitte mit sudo")
        return 1
    conf = load(root) or {}
    run(["systemctl", "disable", "--now", "spark-anker.service", "spark-anker-abbau.path"])
    for p in remove_paths(root):
        if os.path.islink(p) or os.path.isfile(p):
            os.remove(p)
        elif os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
    run(["systemctl", "daemon-reload"])
    if home is None:
        try:
            home = pwd.getpwnam(USER).pw_dir
        except KeyError:
            home = ""
    if home:
        strip_key(os.path.join(home, ".ssh", "authorized_keys"))
    if conf.get("user_neu") and (root != "/" or user_exists(USER)):
        run(["userdel", "--remove", USER])
    if root != "/" or user_exists(RUNNER):
        run(["userdel", RUNNER])
    say("entfernt: Dienste, Programm, Einstellungen, Schlüssel" + (f", Benutzer {USER}" if conf.get("user_neu") else ""))
    if tell and conf.get("url") and conf.get("key"):
        try:
            status, _ = http_call(conf["url"], conf.get("fp") or "", "POST", "/api/fernzugang/anker/abgebaut", {}, conf["key"], 10)
            say("dem Panel gemeldet" if status == 200 else f"Panel antwortet {status}")
        except (OSError, Fehler):
            say("Panel nicht erreicht; dort „Entfernen“ wählen")
    return 0


def cmd_state(args):
    conf = load()
    if not conf:
        say("nicht eingerichtet")
        return 1
    say(f"eingerichtet für {conf['url']}" + (" (Zertifikat festgelegt)" if conf.get("fp") else "") + f", Version {VERSION}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="spark-anker", description="Fernzugang des Spark-Panels zu diesem sshd")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("einrichten", help="einmal einrichten (fragt den Code im Terminal)")
    a.add_argument("adresse", help="https-Adresse des Panels")
    a.add_argument("--fp", default="", help="SHA-256 des Panel-Zertifikats (steht im Befehl aus dem Panel)")
    r = sub.add_parser("entfernen", help="alles entfernen, was der Anker eingerichtet hat")
    r.add_argument("--vom-panel", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("lauf", help="der Dienst (startet systemd)")
    sub.add_parser("zustand", help="eingerichtet? welches Panel?")
    args = p.parse_args(argv)
    try:
        return {"einrichten": cmd_setup, "entfernen": cmd_remove, "lauf": cmd_run, "zustand": cmd_state}[args.cmd](args)
    except Fehler as e:
        say(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
