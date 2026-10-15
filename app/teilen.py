"""Spark teilen (plan Raspberry-Pi split, B3): what the model computer needs besides the TLS-Tor (tlstor.py).

- Its own certificate (common.TOR_CERT, self-signed EC P-256, made by install.sh --teilen, apart from the panel's): the pairing
  hands its SHA-256 fingerprint to the panel computer, which then trusts exactly that one (models.cert).
- A firewall (nftables, table inet speech_spark_teilen): the ports of the door answer only the panel computer
  (api.tls_from), everyone else is dropped before the handshake. Loopback stays open for the DGX itself.

The rules are built from checked values only (IP addresses, port numbers), never from text. Logs ("teilen:" lines)
carry counts and fixed words, never addresses.

- The pairing (B6a): the model computer shows a code of 6 characters (`speech-spark teilen code`, 10 minutes, one
  use, three wrong tries end it) and waits on KOPPEL_PORT with TLS 1.3 and its own certificate. The panel computer
  (`speech-spark teilen koppeln <dgx>`) connects, takes the certificate it sees (fingerprint F) and proves the code
  with HMAC under K = scrypt(code, F). The model computer computes K with its own F, so a proof only fits when the
  panel saw the real certificate: a man in the middle shows another one and fails, and scrypt makes guessing the
  code from a captured proof far slower than the 10 minutes it lives. Then the model computer answers, signed with
  K, with a fresh Wärter key and the API key; the panel computer pins exactly the certificate it saw (models.cert).
  Nothing listens on KOPPEL_PORT outside these 10 minutes, the code lives only in memory.

    python3 teilen.py regeln           the nftables rules for this config (printed, applied by speech-spark teilen)
    python3 teilen.py fingerabdruck    the fingerprint of the door's certificate (TOR_CERT)
    python3 teilen.py warten <datei> [<ordner>]   show a code, wait for the pairing, the result into <datei>; with
                                       <ordner> (umzug.bin, passwort from umziehen.py packen) the move goes along
    python3 teilen.py koppeln <host> <datei> [<ordner> -- <einspielen …>]  ask for the code, pair, the result into
                                       <datei>; a move the other side sends lands in <ordner> and <einspielen> restores it

- The move (B6c, umziehen): the computer that gives the panel adds its move backup to the pairing; the other one
  checks size and SHA-256 (inside the signed answer), restores it and answers with a signed "fertig". Only after a
  "fertig ok" does the giving computer change its role; a failed move changes nothing there.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import sys
import time

from common import TLS_DIR, TOR_CERT, TOR_KEY, load_config, write_json

TABLE = "speech_spark_teilen"
MAX_FROM = 4           # panel computers that may use the door (one, plus room for a move)
KOPPEL_PORT = 31008    # only while a pairing code is shown
PANEL_CERT, PANEL_KEY = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
CODE_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 32 signs, no I/O/0/1: 30 bits in 6 characters
CODE_LEN = 6
CODE_SECS = 600        # a code lives 10 minutes
CODE_TRIES = 3         # wrong proofs before the code is gone
CONN_SECS = 30         # one pairing conversation at most
MAX_MSG = 65536        # bytes of one message (the move's answer carries the panel's certificate and key)
UMZUG_SECS = 1800      # the other side restores the move backup at most this long
MAX_UMZUG = 8 * 1024 ** 3
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}
SALT = b"speech-spark-koppeln-1"
HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|[0-9A-Fa-f:.]{2,45}")


class Fehler(ValueError):
    pass


def _ip(v):
    try:
        ip = ipaddress.ip_address(str(v).split("%")[0])
    except ValueError:
        raise Fehler("adresse")
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
        raise Fehler("adresse")
    return ip


def pruefen(cfg):
    """(listen address, [panel addresses], [ports]) from api.tls_listen / api.tls_from, checked; Fehler otherwise."""
    import tlstor
    api = cfg.get("api") or {}
    listen = _ip(api.get("tls_listen"))
    von = api.get("tls_from") or []
    if not isinstance(von, list) or not 1 <= len(von) <= MAX_FROM:
        raise Fehler("absender")
    von = sorted({_ip(a) for a in von}, key=lambda a: (a.version, int(a)))
    ports = sorted(set(tlstor.ports(cfg)))
    if not all(isinstance(p, int) and 1024 <= p <= 65535 for p in ports):
        raise Fehler("port")
    return listen, von, ports


def regeln(cfg):
    """The nftables rules: the door's ports only from the panel computer; loads atomically with nft -f."""
    _, von, ports = pruefen(cfg)
    p = ", ".join(str(x) for x in ports)
    v4 = ", ".join(str(a) for a in von if a.version == 4)
    v6 = ", ".join(str(a) for a in von if a.version == 6)
    out = [f"table inet {TABLE}", f"delete table inet {TABLE}", f"table inet {TABLE} {{",
           "  chain input {", "    type filter hook input priority filter; policy accept;", '    iif "lo" accept']
    if v4:
        out.append(f"    ip saddr {{ {v4} }} tcp dport {{ {p} }} accept")
    if v6:
        out.append(f"    ip6 saddr {{ {v6} }} tcp dport {{ {p} }} accept")
    out += [f"    tcp dport {{ {p} }} drop", "  }", "}", ""]
    return "\n".join(out)


def fingerabdruck(path=None):
    """SHA-256 of the certificate like browsers show it (AB:CD:…), or "" without one."""
    import hashlib
    try:
        with open(path or TOR_CERT) as f:
            der = ssl.PEM_cert_to_DER_cert(f.read())
    except (OSError, ValueError):
        return ""
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


# ---------------------------------------------------------------- pairing (B6a)
def code_neu():
    return "".join(secrets.choice(CODE_ABC) for _ in range(CODE_LEN))


def code_lesen(text):
    """The code as typed (spaces, dashes and small letters allowed), or Fehler("code")."""
    c = re.sub(r"[\s-]", "", str(text or "")).upper()
    if len(c) != CODE_LEN or any(ch not in CODE_ABC for ch in c):
        raise Fehler("code")
    return c


def zeigen(code):
    return code[:3] + "-" + code[3:]


def schluessel(code, der):
    """K = scrypt(code, salt + SHA-256 of the certificate): bound to the one certificate both sides look at."""
    return hashlib.scrypt(code.encode(), salt=SALT + hashlib.sha256(der).digest(), **SCRYPT)


def _mac(k, *teile):
    return hmac.new(k, b"|".join(teile), hashlib.sha256).hexdigest()


def _daten_bytes(daten):
    return json.dumps(daten, sort_keys=True, separators=(",", ":")).encode()


def beweis(k, n_pi):
    return _mac(k, b"pi", n_pi.encode())


def antwort_mac(k, n_pi, n_dgx, daten):
    return _mac(k, b"dgx", n_pi.encode(), n_dgx.encode(), _daten_bytes(daten))


def _lesen(conn, rest=False):
    """One JSON line; with rest=True also the bytes that came after it in the same reads."""
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(1024)
        if not chunk:
            break
        buf += chunk
        if len(buf) > MAX_MSG:
            raise Fehler("gross")
    line, _, after = buf.partition(b"\n")
    try:
        d = json.loads(line or b"null")
    except ValueError:
        raise Fehler("form")
    if not isinstance(d, dict):
        raise Fehler("form")
    return (d, after) if rest else d


def _schreiben(conn, d):
    conn.sendall(json.dumps(d, separators=(",", ":")).encode() + b"\n")


def _hexn(v, n=32):
    return isinstance(v, str) and re.fullmatch(f"[0-9a-f]{{{n}}}", v) is not None


def api_key_neu():
    """The API key in the form of `speech-spark key new`."""
    return "sk-" + secrets.token_hex(24)


def _log(text):
    print(f"teilen: kopplung {text}", file=sys.stderr, flush=True)


def _umzug_kopf(pfad):
    """The move file of umziehen.py packen: (header dict, offset of the backup, its size, its SHA-256)."""
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        kopf = json.loads(f.readline(MAX_MSG) or b"null")
        start = f.tell()
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
        size = f.tell() - start
    if not isinstance(kopf, dict):
        raise Fehler("umzug")
    return kopf, start, size, h.hexdigest()


def _fertig_mac(k, n_dgx, ok):
    return _mac(k, b"fertig", n_dgx.encode(), b"ok" if ok else b"nein")


def warten(cfg, code, ctx, sock, uhr=time.monotonic, umzug=None):
    """Model computer (or, with umzug, the computer that gives the panel): wait on the listening socket until the
    other computer proves the code. Returns its address, our address, a fresh Wärter key and the API key, or
    Fehler("abgelaufen"|"abgelehnt"). One conversation at a time; the code is gone after the first fit, after
    CODE_TRIES misses or after CODE_SECS. umzug = {"pfad", "passwort"}: the move file goes along (size and SHA-256
    inside the signed answer), then the other side reports with a signed "fertig" whether it restored it
    ("umzug_ok" in the result); only then may this computer change its role."""
    k = schluessel(code, ssl.PEM_cert_to_DER_cert(ctx.pem))
    ende, falsch = uhr() + CODE_SECS, 0
    kopf = _umzug_kopf(umzug["pfad"]) if umzug else None
    while True:
        rest = ende - uhr()
        if rest <= 0:
            _log("abgelaufen")
            raise Fehler("abgelaufen")
        sock.settimeout(min(rest, 5))
        try:
            raw, addr = sock.accept()
        except socket.timeout:
            continue
        try:
            raw.settimeout(CONN_SECS)
            with ctx.wrap_socket(raw, server_side=True) as conn:
                d = _lesen(conn)
                n_pi, got = d.get("n"), d.get("beweis")
                if d.get("v") != 1 or not _hexn(n_pi) or not _hexn(got, 64):
                    raise Fehler("form")
                if not hmac.compare_digest(got, beweis(k, n_pi)):
                    falsch += 1
                    _schreiben(conn, {"ok": False})
                    _log("falscher code")
                    if falsch >= CODE_TRIES:
                        _log("abgelehnt")
                        raise Fehler("abgelehnt")
                    continue
                von = str(ipaddress.ip_address(addr[0].split("%")[0]))
                ip = ipaddress.ip_address(von)
                if ip.version == 6 and ip.ipv4_mapped:
                    von = str(ip.ipv4_mapped)
                hier = conn.getsockname()[0].split("%")[0]
                hip = ipaddress.ip_address(hier)
                if hip.version == 6 and hip.ipv4_mapped:
                    hier = str(hip.ipv4_mapped)
                api_key = str((cfg.get("api") or {}).get("key") or "") or api_key_neu()
                daten = {"waerter_key": secrets.token_hex(32), "api_key": api_key}
                if kopf:
                    head, start, size, sha = kopf
                    daten["umzug"] = {"groesse": size, "sha256": sha, "passwort": umzug["passwort"],
                                      "cert": str(head.get("cert") or ""), "key": str(head.get("key") or "")}
                n_dgx = secrets.token_hex(16)
                _schreiben(conn, {"ok": True, "n": n_dgx, "daten": daten, "mac": antwort_mac(k, n_pi, n_dgx, daten)})
                _log("ok")
                out = {"von": von, "hier": hier, "waerter_key": daten["waerter_key"], "api_key": api_key}
                if kopf:
                    with open(umzug["pfad"], "rb") as f:
                        f.seek(start)
                        for chunk in iter(lambda: f.read(256 * 1024), b""):
                            conn.sendall(chunk)
                    _log("umzug gesendet")
                    conn.settimeout(UMZUG_SECS)
                    try:
                        e = _lesen(conn)
                    except (Fehler, OSError):
                        e = {}
                    ok = e.get("fertig") is True and isinstance(e.get("mac"), str) \
                        and hmac.compare_digest(e["mac"], _fertig_mac(k, n_dgx, True))
                    out["umzug_ok"] = ok
                    _log("umzug fertig ok" if ok else "umzug fertig fehler")
                return out
        except Fehler as e:
            if str(e) == "abgelehnt":
                raise
            _log(f"fehler {e}")
        except (OSError, ssl.SSLError, ValueError):
            _log("fehler verbindung")


def _umzug_pruefen(u):
    if not isinstance(u, dict):
        raise Fehler("antwort")
    size, sha, pw = u.get("groesse"), u.get("sha256"), u.get("passwort")
    if not isinstance(size, int) or not 0 < size <= MAX_UMZUG or not _hexn(sha, 64):
        raise Fehler("antwort")
    if not isinstance(pw, str) or not 12 <= len(pw) <= 200:
        raise Fehler("antwort")
    for f in ("cert", "key"):
        if not isinstance(u.get(f), str) or len(u[f]) > 16384:
            raise Fehler("antwort")
    return u


def koppeln(host, port, code, ctx=None, umzug_ordner=None, einspielen=None):
    """Panel computer (or, with a move, the computer that takes the panel): connect, prove the code for the
    certificate we see, check the signed answer. Returns {pem, waerter_key, api_key} (and "umzug": True after a
    restored move) or Fehler("adresse"|"verbindung"|"code"|"antwort"|"umzug"). When the other side sends a move, it
    lands in umzug_ordner (umzug.tar.gz and umzug.json, 0600), is checked against the signed size and SHA-256, and
    einspielen() restores it; the signed "fertig" tells the other side whether that worked."""
    if not HOST_RE.fullmatch(str(host or "")):
        raise Fehler("adresse")
    code = code_lesen(code)
    if ctx is None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE        # trust comes from the code proof over this very certificate
    try:
        raw = socket.create_connection((host, port), timeout=CONN_SECS)
    except OSError:
        raise Fehler("verbindung")
    try:
        with ctx.wrap_socket(raw) as conn:
            der = conn.getpeercert(binary_form=True)
            if not der:
                raise Fehler("verbindung")
            k = schluessel(code, der)
            n_pi = secrets.token_hex(16)
            _schreiben(conn, {"v": 1, "n": n_pi, "beweis": beweis(k, n_pi)})
            d, rest = _lesen(conn, rest=True)
            if d.get("ok") is not True:
                raise Fehler("code")
            daten, n_dgx, mac = d.get("daten"), d.get("n"), d.get("mac")
            if not isinstance(daten, dict) or not _hexn(n_dgx) or not isinstance(mac, str):
                raise Fehler("antwort")
            if not hmac.compare_digest(mac, antwort_mac(k, n_pi, n_dgx, daten)):
                raise Fehler("antwort")
            wk, ak = daten.get("waerter_key"), daten.get("api_key")
            if not _hexn(wk, 64) or not isinstance(ak, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{16,128}", ak):
                raise Fehler("antwort")
            out = {"pem": ssl.DER_cert_to_PEM_cert(der), "waerter_key": wk, "api_key": ak}
            if "umzug" in daten:
                u = _umzug_pruefen(daten["umzug"])
                ok = False
                if umzug_ordner and einspielen:
                    ok = _umzug_holen(conn, rest, u, umzug_ordner) and bool(einspielen())
                _schreiben(conn, {"fertig": ok, "mac": _fertig_mac(k, n_dgx, ok)})
                _log("umzug eingespielt" if ok else "umzug fehler")
                if not ok:
                    raise Fehler("umzug")
                out["umzug"] = True
    except (OSError, ssl.SSLError):
        raise Fehler("verbindung")
    return out


def _umzug_holen(conn, rest, u, ordner):
    """The move file from the connection into ordner, checked against the signed size and SHA-256."""
    h, size = hashlib.sha256(), u["groesse"]
    pfad = os.path.join(ordner, "umzug.tar.gz")
    with open(os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        got = rest[:size]
        f.write(got)
        h.update(got)
        n = len(got)
        while n < size:
            chunk = conn.recv(min(256 * 1024, size - n))
            if not chunk:
                return False
            f.write(chunk)
            h.update(chunk)
            n += len(chunk)
    if not hmac.compare_digest(h.hexdigest(), u["sha256"]):
        _log("umzug pruefsumme falsch")
        return False
    head = {"passwort": u["passwort"], "cert": u["cert"], "key": u["key"]}
    with open(os.open(os.path.join(ordner, "umzug.json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(head, f)
    return True


class _Ctx:
    """The server context plus its certificate (PEM), which the proof is bound to."""
    def __init__(self, cert, key):
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        self.ctx.load_cert_chain(cert, key)
        with open(cert) as f:
            m = re.search(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", f.read(), re.S)
        if not m:
            raise Fehler("zertifikat")
        self.pem = m.group(0) + "\n"       # the first one: the certificate the handshake shows

    def wrap_socket(self, *a, **kw):
        return self.ctx.wrap_socket(*a, **kw)


def lauschen(port=KOPPEL_PORT, host=""):
    if socket.has_dualstack_ipv6() and not host:
        return socket.create_server(("::", port), family=socket.AF_INET6, dualstack_ipv6=True)
    return socket.create_server((host or "0.0.0.0", port))


def main(argv):
    cmd = argv[0] if argv else ""
    cfg = load_config()
    try:
        if cmd == "regeln":
            sys.stdout.write(regeln(cfg))
        elif cmd == "fingerabdruck":
            print(fingerabdruck())
        elif cmd == "warten" and len(argv) in (2, 3):
            # the door's certificate; a panel computer that gives the panel back has only the panel's own
            cert, key = (TOR_CERT, TOR_KEY) if os.path.exists(TOR_CERT) else (PANEL_CERT, PANEL_KEY)
            ctx = _Ctx(cert, key)
            umzug = None
            if len(argv) == 3:
                with open(os.path.join(argv[2], "passwort")) as f:
                    umzug = {"pfad": os.path.join(argv[2], "umzug.bin"), "passwort": f.read().strip()}
            code = code_neu()
            with lauschen() as sock:
                print(f"Kopplungscode: {zeigen(code)}  (10 Minuten gültig, einmal nutzbar)", flush=True)
                print(f"Fingerabdruck: {fingerabdruck(cert)}", flush=True)
                _log("code gezeigt")
                write_json(argv[1], warten(cfg, code, ctx, sock, umzug=umzug), mode=0o600)
        elif cmd == "koppeln" and (len(argv) == 3 or (len(argv) > 5 and argv[4] == "--")):
            code = os.environ.get("SPEECH_SPARK_CODE") or input("Kopplungscode vom anderen Rechner: ")
            ordner, befehl = (argv[3], argv[5:]) if len(argv) > 3 else (None, None)

            def einspielen():
                import subprocess
                return subprocess.run(befehl + [ordner], check=False).returncode == 0
            res = koppeln(argv[1], KOPPEL_PORT, code, umzug_ordner=ordner, einspielen=einspielen if befehl else None)
            der = ssl.PEM_cert_to_DER_cert(res["pem"])
            print("Fingerabdruck:", ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest()), flush=True)
            _log("ok")
            write_json(argv[2], res, mode=0o600)
        else:
            print("teilen.py regeln|fingerabdruck|warten <datei> [<umzug-ordner>]|"
                  "koppeln <host> <datei> [<umzug-ordner> -- <einspielen …>]", file=sys.stderr)
            return 2
    except Fehler as e:
        print(f"teilen: abgelehnt {e}", flush=True)
        return 1
    except OSError:
        print("teilen: fehler", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
