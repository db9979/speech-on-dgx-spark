"""Sicherung nach außen (offsite.py, V01.0.286): off by default, main admin only, https only, passwords sealed;
the copy is encrypted before it leaves (nothing can be cut off, swapped or changed unnoticed) and restores with the
backup password like a move backup."""
import asyncio
import io
import json
import os
import tarfile
import tempfile
import unittest

import httpx

from tests import helpers

helpers.start()
import backup  # noqa: E402
import offsite  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
KEY = "ein langes Sicherungs-Passwort"


def enc(data, key=KEY):
    out = io.BytesIO()
    offsite.encrypt(io.BytesIO(data), out, key)
    return out.getvalue()


def dec(blob, key=KEY):
    out = io.BytesIO()
    offsite.decrypt(io.BytesIO(blob), out, key)
    return out.getvalue()


class Crypt(unittest.TestCase):
    def test_round_trip_and_tampering(self):
        data = os.urandom(offsite.CHUNK * 2 + 1234)
        blob = enc(data)
        self.assertTrue(blob.startswith(offsite.MAGIC))
        self.assertNotIn(data[:64], blob)
        self.assertEqual(dec(blob), data)
        self.assertEqual(dec(enc(b"")), b"")
        with self.assertRaisesRegex(ValueError, "wrong password"):
            dec(blob, "ein anderes Passwort!!")
        head = blob.index(b"\n", len(offsite.MAGIC)) + 1
        n = int.from_bytes(blob[head:head + 4], "big")
        first, rest = blob[head:head + 4 + n], blob[head + 4 + n:]
        with self.assertRaises(ValueError):            # the last piece cut off
            dec(blob[:head] + first)
        bad = bytearray(blob)
        bad[-5] ^= 1
        with self.assertRaises(ValueError):            # one bit changed
            dec(bytes(bad))
        n2 = int.from_bytes(rest[:4], "big")
        with self.assertRaises(ValueError):            # two pieces swapped
            dec(blob[:head] + rest[:4 + n2] + first + rest[4 + n2:])
        with self.assertRaises(ValueError):            # a costlier key derivation is refused
            dec(blob.replace(b'"n": 32768', b'"n": 1048576', 1))


class Settings(unittest.TestCase):
    def tearDown(self):
        offsite._write({})

    def test_off_by_default_and_main_admin_only(self):
        self.assertFalse(offsite.due())
        self.assertFalse(ADMIN.get("/api/admin/offsite").json()["on"])
        guest = TestClient(panel.app)
        self.assertEqual(guest.get("/api/admin/offsite").status_code, 401)
        self.assertEqual(guest.put("/api/admin/offsite", json={"on": True}).status_code, 401)
        self.assertEqual(guest.post("/api/admin/offsite/now").status_code, 401)

    def test_checks_and_sealed_passwords(self):
        put = lambda **b: ADMIN.put("/api/admin/offsite", json=b)   # noqa: E731
        for url in ("http://nas.local/dav/", "https://user:pw@nas.example.de/", "https://nas.example.de/?x=1", "ftp://x/"):
            self.assertEqual(put(url=url).status_code, 400, url)
        self.assertEqual(put(on=True, url="https://nas.example.de/dav").status_code, 400)   # no backup password yet
        self.assertEqual(put(key="kurz").status_code, 400)
        r = put(url="https://nas.example.de/dav", user="spark", password="webdav-geheim", key=KEY, on=True)
        self.assertEqual(r.status_code, 200, r.text)
        v = r.json()
        self.assertEqual((v["on"], v["url"], v["has_password"], v["has_key"]), (True, "https://nas.example.de/dav/", True, True))
        with open(offsite.FILE) as f:
            raw = f.read()
        self.assertNotIn("webdav-geheim", raw)
        self.assertNotIn(KEY, raw)
        self.assertNotIn("webdav-geheim", json.dumps(v))
        self.assertTrue(offsite.due())
        v = put(url="https://other.example.de/dav/").json()       # a new address needs the password again
        self.assertFalse(v["has_password"])
        self.assertTrue(v["has_key"])


class Upload(unittest.TestCase):
    def setUp(self):
        self.seen = []

        def handler(request):
            self.seen.append((request.method, request.url.path, request.read() if request.method == "PUT" else b"",
                              request.headers.get("authorization", "")))
            return httpx.Response(201)
        self.real = offsite.netguard.client
        offsite.netguard.client = lambda level, origin=None, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        offsite._write({"on": True, "url": "https://nas.example.de/dav/", "user": "spark",
                        "password": offsite.vault.seal("webdav-geheim"), "key": offsite.vault.seal(KEY),
                        "sent": [f"speech-spark-2026010{i}-000000-offsite.tar.gz.enc" for i in range(1, 8)]})

    def tearDown(self):
        offsite.netguard.client = self.real
        offsite._write({})

    def test_sends_an_encrypted_move_backup(self):
        before = set(os.listdir(backup.BACKUP_DIR)) if os.path.isdir(backup.BACKUP_DIR) else set()
        last = asyncio.run(offsite.run("manual"))
        self.assertTrue(last["ok"], last)
        puts = [x for x in self.seen if x[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertTrue(puts[0][1].startswith("/dav/speech-spark-") and puts[0][1].endswith("-offsite.tar.gz.enc"))
        self.assertTrue(puts[0][3].startswith("Basic "))
        plain = dec(puts[0][2])
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
            names = tar.getnames()
        self.assertIn("backup.json", names)
        self.assertIn("state/" + backup.MOVE_FILE, names)    # restorable on a new Spark with the password
        # only the copies it sent itself are deleted there, the newest KEEP stay
        self.assertEqual([x[1] for x in self.seen if x[0] == "DELETE"], ["/dav/speech-spark-20260101-000000-offsite.tar.gz.enc"])
        self.assertEqual(len(offsite._read()["sent"]), offsite.KEEP)
        after = set(os.listdir(backup.BACKUP_DIR))
        self.assertEqual({x for x in after - before if "offsite" in x}, set())   # no local copy left

    def test_refusal_names_the_http_status(self):
        """A wrong WebDAV login: the request's line on Logs → Anfragen says http_401, not a bare error."""
        import live
        jobs, real = [], live.job
        offsite.netguard.client = lambda level, origin=None, **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(401)))
        live.job = lambda *a, **k: jobs.append(k.get("code"))
        try:
            last = asyncio.run(offsite.run("manual"))
        finally:
            live.job = real
        self.assertFalse(last["ok"])
        self.assertIn("HTTP 401", last["error"])
        self.assertEqual(jobs, ["http_401"])

    def test_restore_needs_the_password(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name in ("backup.json", "../../etc/evil"):
                info = tarfile.TarInfo(name)
                info.size = 2
                tar.addfile(info, io.BytesIO(b"{}"))
        blob = enc(buf.getvalue())
        r = ADMIN.post("/api/backups-upload", files={"file": ("x.tar.gz.enc", blob)})
        self.assertEqual(r.status_code, 400)
        self.assertIn("backup password", r.text)
        r = ADMIN.post("/api/backups-upload", files={"file": ("x.tar.gz.enc", blob)}, data={"password": "ein falsches Passwort"})
        self.assertIn("wrong password", r.text)
        r = ADMIN.post("/api/backups-upload", files={"file": ("x.tar.gz.enc", blob)}, data={"password": KEY})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("password", r.text)     # decrypted; the archive's own checks refuse the evil path


# ---------------------------------------------------------------- a NAS whose certificate does not fit its address
def _cert(name):
    """A self-made certificate for a name (not for 127.0.0.1): what a NAS in the home network often has."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    sub = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    start = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    c = (x509.CertificateBuilder().subject_name(sub).issuer_name(sub).public_key(key.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(start)
         .not_valid_after(start + datetime.timedelta(days=365 * 60))
         .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
         .sign(key, hashes.SHA256()))
    d = tempfile.mkdtemp(prefix="spark-cert-")
    cp, kp = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
    with open(cp, "wb") as f:
        f.write(c.public_bytes(serialization.Encoding.PEM))
    with open(kp, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return cp, kp, c.public_bytes(serialization.Encoding.DER)


NAS = {"got": []}
CERT1, CERT2 = _cert("nas-keller.local"), _cert("ein-anderer.local")


def _nas():
    import http.server
    import ssl
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def _any(self):
            n = int(self.headers.get("Content-Length") or 0)
            NAS["got"].append((self.command, self.path, self.headers.get("Authorization", ""), self.rfile.read(n)))
            self.send_response(201)
            self.send_header("Content-Length", "0")
            self.end_headers()
        do_PUT = do_DELETE = do_GET = _any

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT1[0], CERT1[1])
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, ctx


SRV, SRVCTX = _nas()
NASURL = f"https://127.0.0.1:{SRV.server_address[1]}/dav/"


class Certificate(unittest.TestCase):
    """Dominik 2026-10-13: "CERTIFICATE_VERIFY_FAILED … IP address mismatch" on his NAS. The check is never switched
    off: the admin compares the fingerprint and accepts exactly that certificate; nothing (no password, no copy)
    goes to any other one, and the message says where to do it."""

    def setUp(self):
        import guard
        guard._rate.clear()
        SRVCTX.load_cert_chain(CERT1[0], CERT1[1])
        NAS["got"].clear()
        offsite._write({"on": True, "url": NASURL, "user": "spark", "password": offsite.vault.seal("webdav-geheim"),
                        "key": offsite.vault.seal(KEY), "sent": []})

    def tearDown(self):
        SRVCTX.load_cert_chain(CERT1[0], CERT1[1])
        offsite._write({})

    def test_refused_without_accepting_and_said_with_a_way(self):
        last = asyncio.run(offsite.run("manual"))
        self.assertFalse(last["ok"])
        self.assertEqual(last.get("kind"), "cert")
        self.assertIn("Einstellungen → Sicherung", last["error"])
        self.assertEqual(NAS["got"], [])                       # not even the login went there

    def test_accept_exactly_that_certificate(self):
        import zertpin
        r = ADMIN.post("/api/admin/offsite/cert", json={})
        self.assertEqual(r.status_code, 200, r.text)
        c = r.json()
        self.assertEqual(c["sha256"], zertpin.fingerprint(CERT1[2]))
        self.assertEqual((c["fits"], c["self_signed"], c["pinned"]), (False, True, False))
        self.assertEqual(c["names"], ["nas-keller.local"])
        self.assertNotIn("pem", c)
        wrong = zertpin.fingerprint(CERT2[2])
        self.assertEqual(ADMIN.put("/api/admin/offsite", json={"cert": wrong}).status_code, 409)   # not what it shows
        r = ADMIN.put("/api/admin/offsite", json={"cert": c["sha256"].lower()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["cert"], c["sha256"])
        last = asyncio.run(offsite.run("manual"))
        self.assertTrue(last["ok"], last)
        self.assertEqual([x[0] for x in NAS["got"]], ["PUT"])
        self.assertTrue(NAS["got"][0][2].startswith("Basic "))
        self.assertTrue(ADMIN.post("/api/admin/offsite/cert", json={}).json()["pinned"])
        # the NAS shows another certificate: nothing goes there until it is accepted again
        SRVCTX.load_cert_chain(CERT2[0], CERT2[1])
        NAS["got"].clear()
        last = asyncio.run(offsite.run("manual"))
        self.assertEqual((last["ok"], last.get("kind")), (False, "cert"))
        self.assertEqual(NAS["got"], [])
        # the Dienst-Wächter sees the NAS with the accepted certificate only
        import dienstwacht
        p = {"url": NASURL, "level": offsite.netguard.HOME, "verify": True, "pin": offsite._read()["cert"]}
        self.assertFalse(asyncio.run(dienstwacht._http(p)).ok)
        SRVCTX.load_cert_chain(CERT1[0], CERT1[1])
        self.assertTrue(asyncio.run(dienstwacht._http(p)).ok)
        self.assertFalse(asyncio.run(dienstwacht._http(dict(p, pin=""))).ok)
        # a new address forgets it; "forget" too
        ADMIN.put("/api/admin/offsite", json={"url": NASURL + "neu/", "password": "webdav-geheim"})
        self.assertEqual(offsite.view()["cert"], "")
        ADMIN.put("/api/admin/offsite", json={"url": NASURL, "cert": c["sha256"]})
        self.assertEqual(offsite.view()["cert"], c["sha256"])
        ADMIN.put("/api/admin/offsite", json={"cert": ""})
        self.assertEqual(offsite.view()["cert"], "")

    def test_only_for_the_main_admin_and_only_https(self):
        guest = TestClient(panel.app)
        self.assertEqual(guest.post("/api/admin/offsite/cert", json={}).status_code, 401)
        self.assertEqual(ADMIN.post("/api/admin/offsite/cert", json={"url": "http://127.0.0.1/"}).status_code, 400)

    def test_pinned_context_trusts_nothing_else(self):
        import ssl
        import zertpin
        pem = ssl.DER_cert_to_PEM_cert(CERT1[2])
        self.assertIs(zertpin.verify(""), True)
        self.assertIs(zertpin.verify("kein Zertifikat"), True)
        ctx = zertpin.verify(pem)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(ctx.cert_store_stats()["x509"], 1)                # the pinned one is the only anchor
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(zertpin.problem(ValueError("x")), "")
        self.assertEqual(zertpin.problem(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")), "cert")
