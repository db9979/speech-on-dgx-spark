"""Spark teilen (plan Raspberry-Pi split, B3): what the model computer needs besides the TLS-Tor (tlstor.py).

- Its own certificate in TLS_DIR (self-signed, made by install.sh like the panel's https certificate): the pairing
  hands its SHA-256 fingerprint to the panel computer, which then trusts exactly that one (models.cert).
- A firewall (nftables, table inet speech_spark_teilen): the ports of the door answer only the panel computer
  (api.tls_from), everyone else is dropped before the handshake. Loopback stays open for the DGX itself.

The rules are built from checked values only (IP addresses, port numbers), never from text. Logs ("teilen:" lines)
carry counts and fixed words, never addresses.

    python3 teilen.py regeln           the nftables rules for this config (printed, applied by speech-spark teilen)
    python3 teilen.py fingerabdruck    the fingerprint of the certificate in TLS_DIR
"""
import ipaddress
import os
import ssl
import sys

from common import TLS_DIR, load_config

TABLE = "speech_spark_teilen"
MAX_FROM = 4           # panel computers that may use the door (one, plus room for a move)


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
        with open(path or os.path.join(TLS_DIR, "cert.pem")) as f:
            der = ssl.PEM_cert_to_DER_cert(f.read())
    except (OSError, ValueError):
        return ""
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


def main(argv):
    cmd = argv[0] if argv else ""
    cfg = load_config()
    try:
        if cmd == "regeln":
            sys.stdout.write(regeln(cfg))
        elif cmd == "fingerabdruck":
            print(fingerabdruck())
        else:
            print("teilen.py regeln|fingerabdruck", file=sys.stderr)
            return 2
    except Fehler as e:
        print(f"teilen: abgelehnt {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
