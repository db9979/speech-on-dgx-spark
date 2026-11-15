"""Zertifikat-Erneuerung (zertpin.py, Dominik 2026-11-15: "Let's Encrypt ändert das Zertifikat jeden Monat"). One
self-test per rule: an accepted certificate of an authority also lets its renewal under the same name through,
over the asynchronous (httpx, Dienst-Wächter) and the blocking way; a certificate of the same authority for
another name, a self-made certificate under the same name and a renewal from an authority outside the trust store
are refused before anything is sent; the accepted certificate itself keeps working. No test reads the clock."""
import asyncio
import datetime
import os
import socket
import ssl
import tempfile
import threading
import unittest

from tests import helpers

helpers.start()
import dienstwacht  # noqa: E402
import netguard  # noqa: E402
import zertpin  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

START = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
DIR = tempfile.mkdtemp(prefix="spark-zertpin-")


def _name(n):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, n)])


def _pem(c):
    return c.public_bytes(serialization.Encoding.PEM)


def _authority(n):
    key = ec.generate_private_key(ec.SECP256R1())
    c = (x509.CertificateBuilder().subject_name(_name(n)).issuer_name(_name(n)).public_key(key.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(START)
         .not_valid_after(START + datetime.timedelta(days=365 * 60))
         .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
         .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                      key_encipherment=False, data_encipherment=False, key_agreement=False,
                                      encipher_only=False, decipher_only=False), critical=True)
         .sign(key, hashes.SHA256()))
    return c, key


def _leaf(n, by=None):
    """A server certificate for name n, signed by an authority (by) or made by itself; a fresh key each time, as
    Synology makes one on every renewal."""
    key = ec.generate_private_key(ec.SECP256R1())
    issuer, signer = (by[0].subject, by[1]) if by else (_name(n), key)
    b = (x509.CertificateBuilder().subject_name(_name(n)).issuer_name(issuer).public_key(key.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(START)
         .not_valid_after(START + datetime.timedelta(days=365 * 60))
         .add_extension(x509.SubjectAlternativeName([x509.DNSName(n)]), critical=False))
    if by:
        b = b.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(by[1].public_key()), critical=False)
    c = b.sign(signer, hashes.SHA256())
    d = tempfile.mkdtemp(dir=DIR)
    cp, kp = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
    with open(cp, "wb") as f:
        f.write(_pem(c))
    with open(kp, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return cp, kp, _pem(c).decode()


CA, OTHER_CA = _authority("Test Authority"), _authority("Nicht im Speicher")
TRUST = os.path.join(DIR, "trust.pem")
with open(TRUST, "wb") as f:
    f.write(_pem(CA[0]))
NAME = "nas.beispiel.example"
JUNI, JULI = _leaf(NAME, CA), _leaf(NAME, CA)                # the accepted one and its renewal
FREMD = _leaf("angreifer.example", CA)                         # same authority, another name
SELBST1, SELBST2 = _leaf(NAME), _leaf(NAME)                    # self-made, same name
PRIVAT = _leaf(NAME, OTHER_CA)                                 # an authority outside the trust store


def _server():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(JUNI[0], JUNI[1])
    srv = socket.create_server(("127.0.0.1", 0))

    def run():
        while True:
            try:
                s, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=one, args=(s,), daemon=True).start()

    def one(s):
        try:
            with ctx.wrap_socket(s, server_side=True) as t:
                t.settimeout(5)
                t.recv(4096)
                t.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except (OSError, ssl.SSLError):
            pass
    threading.Thread(target=run, daemon=True).start()
    return srv, ctx


SRV, SRVCTX = _server()
URL = f"https://127.0.0.1:{SRV.getsockname()[1]}/"


def _shows(leaf):
    SRVCTX.load_cert_chain(leaf[0], leaf[1])


def _async_ok(pin):
    p = {"url": URL, "level": netguard.HOME, "verify": True, "pin": pin}
    return asyncio.run(dienstwacht._http(p)).ok


def _blocking_ok(pin):
    try:
        with socket.create_connection(("127.0.0.1", SRV.getsockname()[1]), timeout=5) as s:
            with zertpin.verify(pin).wrap_socket(s, server_hostname="127.0.0.1"):
                return True
    except ssl.SSLCertVerificationError as e:
        assert zertpin.problem(e) == "cert"
        return False


class Renewal(unittest.TestCase):
    def setUp(self):
        zertpin.TRUST_FILE = TRUST

    def tearDown(self):
        zertpin.TRUST_FILE = None
        _shows(JUNI)

    def test_names_only_for_an_authoritys_certificate(self):
        self.assertEqual(zertpin.renewing(JUNI[2]), {NAME})
        self.assertEqual(zertpin.renewing(SELBST1[2]), frozenset())        # self-made: the exact pin stays
        self.assertEqual(zertpin.renewing(""), frozenset())
        self.assertEqual(zertpin.verify(SELBST1[2]).cert_store_stats()["x509"], 1)

    def test_renewal_under_the_same_name_passes(self):
        for leaf in (JUNI, JULI):
            _shows(leaf)
            self.assertTrue(_async_ok(JUNI[2]), leaf)
            self.assertTrue(_blocking_ok(JUNI[2]), leaf)

    def test_another_name_of_the_same_authority_is_refused(self):
        _shows(FREMD)
        self.assertFalse(_async_ok(JUNI[2]))
        self.assertFalse(_blocking_ok(JUNI[2]))

    def test_self_made_keeps_the_exact_pin(self):
        _shows(SELBST2)
        self.assertFalse(_async_ok(SELBST1[2]))
        self.assertFalse(_blocking_ok(SELBST1[2]))
        _shows(SELBST1)
        self.assertTrue(_async_ok(SELBST1[2]))

    def test_an_authority_outside_the_trust_store_passes_only_as_the_pinned_one(self):
        _shows(PRIVAT)
        self.assertFalse(_async_ok(JUNI[2]))
        self.assertTrue(_async_ok(PRIVAT[2]))                             # accepted exactly: as before
        _shows(_leaf(NAME, OTHER_CA))
        self.assertFalse(_async_ok(PRIVAT[2]))                            # its renewal needs accepting again

    def test_without_the_test_authority_the_renewal_is_refused(self):
        zertpin.TRUST_FILE = None                                         # the real trust store does not know it
        _shows(JULI)
        self.assertFalse(_async_ok(JUNI[2]))
        _shows(JUNI)
        self.assertTrue(_async_ok(JUNI[2]))                               # the accepted one itself still passes


if __name__ == "__main__":
    unittest.main()
