"""The Windows check of the Fernzugang (stage 5), on a real Windows (GitHub runner windows-latest, as Administrator):
the panel's own file spark-anker-einrichten.cmd (fernwindows.cmd_file) sets up the anchor for real, a small stand-in
panel here (TLS with its own certificate pinned, the anchor's three doors, its WebSocket) pairs it with the file's
one-time key, a real SSH session goes through the anchor to the user spark (PowerShell, SFTP), sshd listens only on
127.0.0.1; then „abbauen“ from the panel and the watcher removes everything again: tasks, user, settings, program,
its Python, the entry in Apps, sshd as before.

    python tools/fernzugang_windows.py        (needs: cryptography, paramiko; Administrator; internet for python.org)

Exit code 0 when every check holds; each check prints one line „ok …“ or „FEHLER …“. Only for this check, never in
the panel: the stand-in answers only what the anchor asks."""
import base64
import datetime
import hashlib
import json
import os
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, os.path.join(APP, "panel"))
import fernwindows  # noqa: E402

PROGRAM = os.path.join(APP, "anker", "spark-anker.py")
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
FAILED = []


def check(ok, text):
    print(("ok " if ok else "FEHLER ") + text, flush=True)
    if not ok:
        FAILED.append(text)
    return ok


def ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True)
    return r.stdout.strip()


# ---------------------------------------------------------------- the stand-in panel
class Panel:
    def __init__(self, token):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
        from cryptography.x509.oid import NameOID
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=2)).sign(key, hashes.SHA256()))
        d = tempfile.mkdtemp(prefix="spark-panel-")
        self.cert, self.key = os.path.join(d, "cert.pem"), os.path.join(d, "key.pem")
        with open(self.cert, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(self.key, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
        self.fp = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        login = ed25519.Ed25519PrivateKey.generate()
        self.login_pem = login.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                             serialization.NoEncryption()).decode()
        self.login_pub = login.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                         serialization.PublicFormat.OpenSSH).decode()
        self.token, self.device = token, "fz_" + secrets.token_urlsafe(24)
        self.hostkey = None
        self.paired = self.removed = False
        self.ws = None                       # the anchor's connection: (socket, lock)
        self.hello = None
        self.events = {"offen": threading.Event(), "hallo": threading.Event()}
        self.inbox = []                      # binary data of channel 1
        self.lock = threading.Lock()
        with open(PROGRAM, "rb") as f:
            self.prog = f.read()
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(self.cert, self.key)
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]
        self.url = f"https://127.0.0.1:{self.port}"
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            c, _ = self.srv.accept()
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, raw):
        try:
            c = self.ctx.wrap_socket(raw, server_side=True)
            head = b""
            while b"\r\n\r\n" not in head:
                part = c.recv(4096)
                if not part:
                    return
                head += part
            top, _, body = head.partition(b"\r\n\r\n")
            lines = top.decode("latin-1").split("\r\n")
            method, path = lines[0].split(" ")[:2]
            h = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
            n = int(h.get("content-length") or 0)
            while len(body) < n:
                body += c.recv(n - len(body))
            if path == "/api/fernzugang/anker" and h.get("upgrade", "").lower() == "websocket":
                return self._ws(c, h)
            status, out = self._http(method, path, h, body)
            c.sendall(f"HTTP/1.1 {status} X\r\nContent-Length: {len(out)}\r\nConnection: close\r\n\r\n".encode() + out)
            c.close()
        except (OSError, ValueError, ssl.SSLError):
            pass

    def _http(self, method, path, h, body):
        if method == "GET" and path == "/fernzugang/anker":
            return 200, self.prog
        if method == "POST" and path == "/api/fernzugang/anker/koppeln":
            d = json.loads(body or b"{}")
            if d.get("token") != self.token or self.paired:
                return 403, b"{}"
            self.paired, self.hostkey = True, d.get("hostkey")
            check("windows" in str(d.get("os", "")).lower(), f"der Anker meldet Windows ({d.get('os')})")
            return 200, json.dumps({"id": "g_000000000001", "key": self.device, "user": "spark",
                                    "pi_key": self.login_pub + " spark-fernzugang-g_000000000001",
                                    "anker_sha256": hashlib.sha256(self.prog).hexdigest(), "wartet": True}).encode()
        if method == "POST" and path == "/api/fernzugang/anker/abgebaut":
            self.removed = h.get("authorization") == f"Bearer {self.device}"
            return 200, b"{}"
        return 404, b"{}"

    def _ws(self, c, h):
        if h.get("authorization") != f"Bearer {self.device}":
            c.sendall(b"HTTP/1.1 403 X\r\nContent-Length: 0\r\n\r\n")
            return c.close()
        acc = base64.b64encode(hashlib.sha1((h["sec-websocket-key"] + GUID).encode()).digest()).decode()
        c.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {acc}\r\n\r\n".encode())
        self.ws = (c, threading.Lock())
        buf = b""
        while True:
            part = c.recv(65536)
            if not part:
                break
            buf += part
            while True:
                got = _frame(buf)
                if got is None:
                    break
                op, data, buf = got
                if op == 1:
                    m = json.loads(data)
                    if m.get("typ") == "hallo":
                        self.hello = m
                        self.events["hallo"].set()
                    elif m.get("typ") == "offen":
                        self.events["offen"].set()
                elif op == 2 and data[:1] == b"\x01":
                    with self.lock:
                        self.inbox.append(data[1:])
                elif op == 8:
                    break
        self.ws = None

    def send(self, data, op):
        c, lock = self.ws
        n = len(data)
        head = bytes([0x80 | op]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack("!H", n) if n < 65536
                                     else bytes([127]) + struct.pack("!Q", n))
        with lock:
            c.sendall(head + data)


def _frame(buf):
    if len(buf) < 2:
        return None
    op, n, i = buf[0] & 0x0F, buf[1] & 0x7F, 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, i = struct.unpack("!H", buf[2:4])[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, i = struct.unpack("!Q", buf[2:10])[0], 10
    mask = buf[i:i + 4] if buf[1] & 0x80 else b""
    i += len(mask)
    if len(buf) < i + n:
        return None
    data = buf[i:i + n]
    if mask:
        data = bytes(b ^ mask[k % 4] for k, b in enumerate(data))
    return op, data, buf[i + n:]


def channel_socket(panel):
    """A local socket pair: one end for paramiko, the other bridged to channel 1 of the anchor."""
    a, b = socket.socketpair()

    def up():
        while True:
            try:
                d = b.recv(32768)
            except OSError:
                return
            if not d:
                return
            panel.send(b"\x01" + d, 2)

    def down():
        while True:
            with panel.lock:
                items, panel.inbox[:] = list(panel.inbox), []
            for d in items:
                try:
                    b.sendall(d)
                except OSError:
                    return
            time.sleep(0.01)
    threading.Thread(target=up, daemon=True).start()
    threading.Thread(target=down, daemon=True).start()
    return a


def wait(cond, seconds, step=1.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def task_there(name):
    return subprocess.run(["schtasks", "/query", "/tn", name], capture_output=True).returncode == 0


def reg_there(key):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key))
        return True
    except OSError:
        return False


def main():
    import paramiko
    pf, pd = os.environ["ProgramFiles"], os.environ["ProgramData"]
    sshd_before = ps("(Get-Service sshd -ErrorAction SilentlyContinue).Status")
    print(f"sshd vorher: {sshd_before or 'nicht da'}", flush=True)
    token = secrets.token_urlsafe(24)
    panel = Panel(token)
    data = fernwindows.cmd_file(panel.url, panel.fp, token, PROGRAM)
    check(bool(data) and b"\r\n" in data and token.encode() in data, "das Panel macht die Datei (CRLF, mit Einmal-Schlüssel)")
    folder = tempfile.mkdtemp(prefix="spark-datei-")
    path = os.path.join(folder, fernwindows.NAME)
    with open(path, "wb") as f:
        f.write(data)
    t0 = time.monotonic()
    r = subprocess.run(["cmd.exe", "/c", path], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       errors="replace", timeout=1800)
    print(r.stdout[-6000:], r.stderr[-3000:], sep="\n", flush=True)
    if not check("spark-anker: eingerichtet:" in r.stdout, f"die Datei richtet ein ({int(time.monotonic() - t0)} s)"):
        return 1
    check(not os.path.exists(path), "die Datei hat sich danach selbst gelöscht")
    check(panel.paired, "gekoppelt mit dem Einmal-Schlüssel der Datei")
    check(os.path.isfile(os.path.join(pf, "SparkAnker", "python-" + fernwindows.pins(panel.prog, PROGRAM)["version"], "python.exe")),
          "Python nur für den Anker liegt in Program Files")
    check(not any("SparkAnker" in p for p in os.environ.get("PATH", "").split(os.pathsep)), "und nicht im PATH")
    check(task_there("SparkAnker") and task_there("SparkAnker-Waechter"), "die beiden Aufgaben sind da")
    check(reg_there(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SparkAnker"), "„Spark Anker“ steht unter Apps")
    if not check(wait(lambda: panel.events["hallo"].is_set(), 120), "der Anker (LOCAL SERVICE) meldet sich beim Panel"):
        print(ps("Get-ScheduledTask -TaskName SparkAnker* | Get-ScheduledTaskInfo | Format-List | Out-String"), flush=True)
        return 1
    print("hallo:", json.dumps(panel.hello), flush=True)
    listen = ps("Get-NetTCPConnection -LocalPort 22 -State Listen | ForEach-Object LocalAddress")
    if sshd_before != "Running":         # the anchor switched sshd on: only for itself
        check(listen and all(a in ("127.0.0.1",) for a in listen.split()), f"sshd hört nur auf 127.0.0.1 ({listen})")
    acl = ps(f"(Get-Acl '{pd}\\SparkAnker\\anker.json').Access | ForEach-Object IdentityReference")
    check("Users" not in acl and "Benutzer" not in acl, f"die Einstellungen liest nicht jeder ({acl.split()})")
    # a real SSH session through the anchor: channel 1, the pinned host key, the panel's key, the user spark
    panel.send(json.dumps({"typ": "auf", "kanal": 1}).encode(), 1)
    check(panel.events["offen"].wait(20), "der Anker öffnet den Kanal zu sshd")
    sock = channel_socket(panel)
    t = paramiko.Transport(sock)
    t.start_client(timeout=30)
    got = t.get_remote_server_key()
    check(f"{got.get_name()} {got.get_base64()}" == panel.hostkey, "Host-Schlüssel wie bei der Kopplung")
    import io
    try:
        t.auth_publickey("spark", paramiko.Ed25519Key.from_private_key(io.StringIO(panel.login_pem)))
    except paramiko.AuthenticationException:
        pass
    if not check(t.is_authenticated(), "Anmeldung als spark mit dem Schlüssel des Panels"):
        print(ps("Get-WinEvent -LogName OpenSSH/Operational -MaxEvents 25 | Sort-Object TimeCreated | "
                 "ForEach-Object { $_.Message } | Out-String -Width 300"), flush=True)
        print(ps(f"icacls '{pd}\\SparkAnker\\authorized_keys'; Get-Content '{pd}\\ssh\\sshd_config' -Tail 30"),
              flush=True)
        return 1
    ch = t.open_session()
    own = sshd_before != "Running"      # the anchor switched sshd on: PowerShell is the shell; else the owner's stays
    ch.exec_command("$PSVersionTable.PSEdition; whoami" if own else "whoami")
    out = b""
    while True:
        d = ch.recv(4096)
        if not d:
            break
        out += d
    text = out.decode(errors="replace")
    print("shell:", text.strip(), flush=True)
    if own:
        check("spark" in text.lower() and ("desktop" in text.lower() or "core" in text.lower()), "PowerShell als spark")
    else:
        check("spark" in text.lower(), "die Shell des Besitzers als spark")
    sftp = paramiko.SFTPClient.from_transport(t)
    home = sftp.normalize(".")
    check(home.startswith("/") and "spark" in home.lower(), f"Dateien (SFTP): {home}")
    sftp.putfo(io.BytesIO(b"hallo"), home.rstrip("/") + "/probe.txt")
    check(sftp.stat(home.rstrip("/") + "/probe.txt").st_size == 5, "hochladen geht")
    t.close()
    sid = ps("(Get-LocalUser -Name spark).SID.Value")
    # „abbauen“ from the panel: the anchor leaves the flag, the watcher (SYSTEM) removes everything
    panel.send(json.dumps({"typ": "abbauen"}).encode(), 1)
    if not check(wait(lambda: panel.removed, 300, 2), "der Abbau meldet sich beim Panel"):
        print(ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'python.exe','powershell.exe' } | "
                 "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" } | Out-String -Width 300"), flush=True)
    check(wait(lambda: not any(task_there(n) for n in ("SparkAnker", "SparkAnker-Waechter")), 120, 2), "die Aufgaben sind weg")
    if not check(wait(lambda: not os.path.exists(os.path.join(pf, "SparkAnker")), 300, 3), "Programm und Python sind weg"):
        print(ps("Get-ScheduledTask -TaskName SparkAnker* | Format-List TaskName,State | Out-String; "
                 f"Get-ChildItem -Recurse -Name '{pf}\\SparkAnker' | Select-Object -First 10"), flush=True)
    check(not os.path.exists(os.path.join(pd, "SparkAnker")), "Einstellungen und Schlüssel sind weg")
    check(not reg_there(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SparkAnker"), "kein Eintrag mehr unter Apps")
    check(subprocess.run(["net", "user", "spark"], capture_output=True).returncode != 0, "der Benutzer spark ist weg")
    prof = home.strip("/").replace("/", "\\")
    # Windows keeps the profile of an SSH user loaded until the next start: then its own task removes it at the start
    clean = "SparkAnker-Einmal-weg-" + sid.rsplit("-", 1)[-1]
    gone = wait(lambda: not os.path.exists(prof) and not task_there(clean), 180, 3)
    held = not gone and ps(f"(Get-CimInstance Win32_UserProfile | Where-Object {{ $_.SID -eq '{sid}' }}).Loaded") == "True"
    boot = held and "BootTrigger" in subprocess.run(["schtasks", "/query", "/tn", clean, "/xml"], capture_output=True,
                                                     text=True, errors="replace").stdout
    if not check(gone or boot, f"sein Profil ist weg ({prof})" if gone else
                 f"Windows hält sein Profil bis zum nächsten Start, dann räumt es die Aufgabe {clean}"):
        print(ps("Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like '*spark*' } | "
                 "Format-List LocalPath,SID,Loaded,Special | Out-String; "
                 "try { Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like '*spark*' } | "
                 "Remove-CimInstance -ErrorAction Stop; 'Remove-CimInstance ok' } catch { $_.Exception.Message }; "
                 f"Test-Path '{prof}'; "
                 "Get-Process -IncludeUserName | Where-Object { $_.UserName -notlike 'NT AUTHORITY*' -and "
                 "$_.UserName -notlike '*runneradmin' } | Format-Table Id,Name,UserName | Out-String"), flush=True)
    conf = os.path.join(pd, "ssh", "sshd_config")
    if os.path.isfile(conf):
        with open(conf, encoding="utf-8", errors="replace") as f:
            check("spark-anker" not in f.read(), "sshd_config ohne die Zeilen des Ankers")
    after = ps("(Get-Service sshd -ErrorAction SilentlyContinue).Status")
    check((after or "") in (("", "Stopped") if sshd_before != "Running" else ("Running",)),
          f"sshd wie vorher ({sshd_before or 'nicht da'} -> {after or 'nicht da'})")
    print(f"\n{len(FAILED)} Fehler" if FAILED else "\nalles ok", flush=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
