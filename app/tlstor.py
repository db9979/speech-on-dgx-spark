"""TLS-Tor (plan Raspberry-Pi split, B2): the door of the model computer for the panel on another computer.

When the panel runs on a Raspberry Pi (or another computer) and the models stay on the DGX, speech, text and pictures
cross the home network. They never do that in plain text: the services (speech recognition, speech output, the
LLM-Tor, pictures, the Wärter) then listen only on 127.0.0.1, and this door listens on the DGX's network address
(api.tls_listen) on the same port numbers with TLS 1.3 and the DGX's own certificate (common.TOR_CERT). The panel trusts
exactly that certificate (common.model_mounts, pinned at the pairing), so a stranger in the network can neither
read along nor pose as the DGX. Only the addresses in api.tls_from (the panel computer) are let in; the API key
is still checked by every service itself. The door only passes bytes on, it never reads or changes a request.

Both set by install.sh and the pairing, never from the panel. Empty api.tls_listen: the door stays shut (the
all-in-one install). Logs ("tlstor:" lines) carry only ports, counts and fixed words, never addresses or content.

    python3 tlstor.py           runs the door (unit speech-spark-tlstor)
    ports(cfg)                  the ports it opens
    server_context(cert, key)   TLS 1.3, this machine's certificate
    make_cert(cert, key, names) a fresh self-signed certificate (EC P-256), for the pairing and the self-tests
"""
import asyncio
import ipaddress
import os
import ssl
import sys

from common import TOR_CERT, TOR_KEY, WAERTER_PORT, load_config

MAX_CONN = 64          # open connections at once; one more is closed at once
IDLE = 900             # seconds without a byte in either direction before a connection is closed
CONNECT = 5            # seconds to reach the service behind the door
HANDSHAKE = 10         # seconds for the TLS handshake
CHUNK = 64 * 1024

_open = set()


def ports(cfg):
    """The ports the door opens: speech recognition and output, the LLM-Tor, pictures and music when installed, and
    the Wärter (tarswart.py)."""
    out = []
    for sec in ("asr", "tts", "llm", "image", "music"):
        c = cfg.get(sec) or {}
        if c.get("enabled", sec in ("asr", "tts")) and c.get("port"):
            out.append(int(c["port"]))
    return out + [WAERTER_PORT]


def allowed(peer, cfg):
    """True when the address is one of api.tls_from (the panel computer)."""
    try:
        ip = ipaddress.ip_address(str(peer).split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return any(ip == ipaddress.ip_address(str(a)) for a in (cfg.get("api") or {}).get("tls_from") or [])
    except ValueError:
        return False


def server_context(cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert, key)
    return ctx


def make_cert(cert, key, names):
    """A self-signed certificate (EC P-256, 10 years) for these names and addresses; key file 0600."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    alt = []
    for n in names:
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            alt.append(x509.DNSName(n))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "speech-spark")])
    now = datetime.datetime.now(datetime.timezone.utc)
    c = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(k.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
         .not_valid_after(now + datetime.timedelta(days=3650))
         .add_extension(x509.SubjectAlternativeName(alt), critical=False)
         .sign(k, hashes.SHA256()))
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()))
    with open(cert, "wb") as f:
        f.write(c.public_bytes(serialization.Encoding.PEM))


async def _pipe(reader, writer):
    try:
        while True:
            data = await asyncio.wait_for(reader.read(CHUNK), IDLE)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (OSError, asyncio.TimeoutError, ssl.SSLError):
        pass
    finally:
        try:
            writer.close()
        except (OSError, RuntimeError):
            pass


def _shut(writer):
    try:
        writer.close()
    except (OSError, RuntimeError):
        pass


async def handle(port, reader, writer, cfg=None):
    """One connection: only from the panel computer, then bytes both ways to the service on 127.0.0.1:port."""
    cfg = load_config() if cfg is None else cfg
    peer = (writer.get_extra_info("peername") or ("",))[0]
    if not allowed(peer, cfg):
        print(f"tlstor: absender abgelehnt port {port}", flush=True)
        return _shut(writer)
    if len(_open) >= MAX_CONN:
        print(f"tlstor: zu viele verbindungen port {port} ({MAX_CONN})", flush=True)
        return _shut(writer)
    try:
        lr, lw = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), CONNECT)
    except (OSError, asyncio.TimeoutError):
        print(f"tlstor: dienst nicht erreichbar port {port}", flush=True)
        return _shut(writer)
    me = asyncio.current_task()
    _open.add(me)
    try:
        await asyncio.gather(_pipe(reader, lw), _pipe(lr, writer))
    finally:
        _open.discard(me)


async def serve(cfg, cert=None, key=None):
    """Opens the door on api.tls_listen for every port; returns the servers (empty when it stays shut)."""
    listen = str((cfg.get("api") or {}).get("tls_listen") or "").strip()
    if not listen:
        print("tlstor: aus (keine adresse)", flush=True)
        return []
    ctx = server_context(cert or TOR_CERT, key or TOR_KEY)
    servers = []
    for port in ports(cfg):
        async def on(r, w, _port=port):
            await handle(_port, r, w)
        try:
            servers.append(await asyncio.start_server(on, listen, port, ssl=ctx, ssl_handshake_timeout=HANDSHAKE))
        except OSError:
            # the services must listen on 127.0.0.1 only (asr.host, tts.host, llm.host), else the port is taken
            print(f"tlstor: port belegt {port}", flush=True)
            for s in servers:
                s.close()
            raise
    print(f"tlstor: offen {len(servers)} ports", flush=True)
    return servers


async def main():
    servers = await serve(load_config())
    if not servers:
        return 0
    await asyncio.gather(*(s.serve_forever() for s in servers))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except (OSError, ssl.SSLError):
        print("tlstor: start fehlgeschlagen", flush=True)
        sys.exit(1)
