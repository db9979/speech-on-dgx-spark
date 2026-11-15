"""Zertifikat festpinnen: a NAS in the home network often has a certificate that does not fit its address (made
for itself, or for a name such as nas.local or xyz.synology.me while the address is 192.168.178.x). Checking is
never switched off for it. Instead the admin compares the fingerprint the page shows with the one the NAS shows
and accepts exactly that certificate: from then on only a server with that certificate (and its key) is trusted
for this address, checked inside the TLS handshake before anything is sent (the pinned certificate is the only
trust anchor, the name is not compared). A new certificate on the NAS stops the copy until it is accepted again.

Renewal (Dominik 2026-11-15, Let's Encrypt renews every month): when the accepted certificate comes from a
certificate authority (issuer is not the certificate itself), the Spark also trusts any certificate that a public
authority signed (the usual trust store) and that carries one of the accepted certificate's names (literally, a
wildcard only as the same wildcard). That is the check a browser does, only against the remembered name instead
of the address (an IP or nas.fritz.box). The accepted certificate itself stays trusted too. A self-made
certificate (issuer = subject) keeps the exact pin; a certificate of a private authority (Synology's own) passes
only as the exact pinned one, because the private authority is not in the trust store.

    fetch(url, level) -> {"sha256", "names", "until", "self_signed", "fits", "pem"}  (what the server presents)
    verify(pem)       -> what netguard.client(verify=...) takes: an SSLContext that trusts only this certificate,
                         or for an authority's certificate also its renewals under the same name
    problem(e)        -> "cert" when an exception is a refused certificate, else ""
"""
import asyncio
import datetime
import hashlib
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

import netguard

MAX_PEM = 16 * 1024
TIMEOUT = 10


def fingerprint(der):
    """SHA-256 like browsers and NAS pages show it: AB:CD:…"""
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


def _info(der, host):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    c = x509.load_der_x509_certificate(der)
    names = []
    try:
        san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = [str(n) for n in san.get_values_for_type(x509.DNSName)] + \
                [str(n) for n in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        pass
    if not names:
        names = [a.value for a in c.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    until = c.not_valid_after_utc
    return {"sha256": fingerprint(der), "names": [str(n)[:120] for n in names[:20]],
            "until": int(until.timestamp()), "self_signed": c.issuer == c.subject,
            "fits": _fits(host, names), "expired": until < datetime.datetime.now(datetime.timezone.utc),
            "pem": ssl.DER_cert_to_PEM_cert(der)}


def _fits(host, names):
    try:
        ip = ipaddress.ip_address(host)
        return any(n == str(ip) for n in names)
    except ValueError:
        h = host.lower().rstrip(".")
        for n in names:
            n = n.lower().rstrip(".")
            if n == h or n.startswith("*.") and h.endswith(n[1:]) and h.count(".") == n.count("."):
                return True
        return False


def _grab(url, level):
    u = urlsplit(url)
    if u.scheme != "https" or not u.hostname:
        raise ValueError("only https addresses have a certificate")
    port = u.port or 443
    ip = netguard.resolve(u.hostname, port, level)        # the Wächter decides, exactly as for the copy itself
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE                       # only to read the certificate; nothing is sent
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((ip, port), timeout=TIMEOUT) as s:
        with ctx.wrap_socket(s, server_hostname=u.hostname) as t:
            der = t.getpeercert(binary_form=True)
    if not der:
        raise ValueError("the server sent no certificate")
    return _info(der, u.hostname)


async def fetch(url, level):
    return await asyncio.wait_for(asyncio.to_thread(_grab, url, level), TIMEOUT + 5)


def clean(pem):
    """A stored certificate, checked: PEM of exactly one certificate, else ""."""
    if not isinstance(pem, str) or not pem or len(pem) > MAX_PEM or pem.count("BEGIN CERTIFICATE") != 1:
        return ""
    try:
        ssl.PEM_cert_to_DER_cert(pem)
    except ValueError:
        return ""
    return pem


def sha_of(pem):
    pem = clean(pem)
    return fingerprint(ssl.PEM_cert_to_DER_cert(pem)) if pem else ""


def _names(cert):
    """DNS and IP names of a certificate as ssl.getpeercert() gives it (a dict), lower case."""
    out = set()
    for kind, value in (cert or {}).get("subjectAltName", ()):
        if kind in ("DNS", "IP Address"):
            out.add(str(value).lower().rstrip("."))
    return out


def _check(obj):
    names = obj.context.spark_names
    if not names & _names(obj.getpeercert()):
        raise ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED: name does not match the accepted certificate")


class _NamedObject(ssl.SSLObject):
    """The asynchronous connection (httpx through anyio): after the handshake the name must fit."""
    def do_handshake(self):
        super().do_handshake()
        _check(self)


class _NamedSocket(ssl.SSLSocket):
    """The blocking connection: after the handshake the name must fit (the socket is closed otherwise)."""
    def do_handshake(self, block=False):
        super().do_handshake(block)
        try:
            _check(self)
        except ssl.SSLCertVerificationError:
            self.close()
            raise


class _NamedContext(ssl.SSLContext):
    sslobject_class = _NamedObject
    sslsocket_class = _NamedSocket
    spark_names = frozenset()


def renewing(pem):
    """The names under which renewals of this accepted certificate count: only for a certificate an authority
    issued (not self-made), only DNS and IP names; an empty set keeps the exact pin."""
    pem = clean(pem)
    if not pem:
        return frozenset()
    try:
        from cryptography import x509
        c = x509.load_pem_x509_certificate(pem.encode())
    except (ValueError, ImportError):
        return frozenset()
    if c.issuer == c.subject:
        return frozenset()
    try:
        san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return frozenset()
    names = [str(n) for n in san.get_values_for_type(x509.DNSName)] + \
            [str(n) for n in san.get_values_for_type(x509.IPAddress)]
    return frozenset(n.lower().rstrip(".") for n in names if n and len(n) <= 253)


TRUST_FILE = None    # selftests only: a file with one more authority (a test authority); never set by a setting


def _store(ctx):
    if TRUST_FILE:
        ctx.load_verify_locations(cafile=TRUST_FILE)
        return
    try:
        import certifi                  # the same trust store httpx uses for every other address
        ctx.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        ctx.load_default_certs()


def verify(pem):
    """True (the normal check) without a pinned certificate; with one an SSLContext that trusts only it, for an
    authority's certificate also every certificate the trust store vouches for under one of its names."""
    from common import pinned_context
    pem = clean(pem)
    if not pem:
        return True
    names = renewing(pem)
    if not names:
        return pinned_context(pem)
    ctx = _NamedContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False          # the address is an IP or a home name; the names are checked after the handshake
    ctx.verify_mode = ssl.CERT_REQUIRED  # the chain to a trusted authority (or the pinned certificate) inside the handshake
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    _store(ctx)
    try:
        ctx.load_verify_locations(cadata=pem)
    except (ssl.SSLError, ValueError, TypeError):
        pass
    ctx.spark_names = names
    return ctx


def problem(e):
    """"cert" when e (or what caused it) is a refused certificate."""
    seen = 0
    while e is not None and seen < 6:
        if isinstance(e, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            return "cert"
        e = e.__cause__ or e.__context__
        seen += 1
    return ""
