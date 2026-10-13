"""Zertifikat festpinnen: a NAS in the home network often has a certificate that does not fit its address (made
for itself, or for a name such as nas.local or xyz.synology.me while the address is 192.168.178.x). Checking is
never switched off for it. Instead the admin compares the fingerprint the page shows with the one the NAS shows
and accepts exactly that certificate: from then on only a server with that certificate (and its key) is trusted
for this address, checked inside the TLS handshake before anything is sent (the pinned certificate is the only
trust anchor, the name is not compared). A new certificate on the NAS stops the copy until it is accepted again.

    fetch(url, level) -> {"sha256", "names", "until", "self_signed", "fits", "pem"}  (what the server presents)
    verify(pem)       -> what netguard.client(verify=...) takes: an SSLContext that trusts only this certificate
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


def verify(pem):
    """True (the normal check) without a pinned certificate; with one an SSLContext that trusts only it."""
    pem = clean(pem)
    if not pem:
        return True
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False                            # the name may not fit: the certificate itself must
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN     # the pinned (leaf) certificate is the only anchor
    ctx.load_verify_locations(cadata=pem)
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
