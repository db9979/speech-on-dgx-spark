"""Sicherung nach außen (offsite.py, V01.0.286): off by default, main admin only, https only, passwords sealed;
the copy is encrypted before it leaves (nothing can be cut off, swapped or changed unnoticed) and restores with the
backup password like a move backup."""
import asyncio
import io
import json
import os
import tarfile
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
