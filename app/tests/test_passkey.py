"""Passkeys instead of the typed code (passkey.py, V01.0.295): only over a host name, added only with a fresh code,
each challenge once and only for its person, login and host, the signature checked with the stored public key, and
a passkey counts wherever a code is asked (login, important changes). A small software authenticator below plays
the browser's part (P-256, as Face ID and Touch ID use)."""
import asyncio
import base64
import hashlib
import json
import re
import secrets
import unittest

from tests import helpers

helpers.start()
import core  # noqa: E402
import guard  # noqa: E402
import mfa  # noqa: E402
import panel  # noqa: E402
import passkey  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from fido2 import cbor  # noqa: E402
from tests.test_iphone import ADMIN, uid_of  # noqa: E402
from tests.test_zweiter_schritt import Req, fake_second_step  # noqa: E402

HOST = "speech.example.de"
BASE = "https://" + HOST
CODE = {"X-Speech-Code": "123456"}
b64 = passkey._b64


class Authenticator:
    """Makes and uses one passkey like a browser would, for one origin."""
    def __init__(self, origin=BASE):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cid = secrets.token_bytes(16)
        self.origin = origin
        self.count = 0

    def _client(self, kind, challenge):
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def create(self, options):
        pk = options["publicKey"]
        nums = self.key.public_key().public_numbers()
        cose = cbor.encode({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        auth = (hashlib.sha256(pk["rp"]["id"].encode()).digest() + bytes([0x45]) + (0).to_bytes(4, "big") + bytes(16)
                + len(self.cid).to_bytes(2, "big") + self.cid + cose)
        att = cbor.encode({"fmt": "none", "attStmt": {}, "authData": auth})
        return {"id": b64(self.cid), "rawId": b64(self.cid), "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64(self._client("webauthn.create", pk["challenge"])), "attestationObject": b64(att)}}

    def get(self, options, rp=HOST):
        pk = options["publicKey"]
        self.count += 1
        auth = hashlib.sha256(rp.encode()).digest() + bytes([0x05]) + self.count.to_bytes(4, "big")
        client = self._client("webauthn.get", pk["challenge"])
        sig = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.cid), "rawId": b64(self.cid), "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64(client), "authenticatorData": b64(auth), "signature": b64(sig)}}


def header_options(exc):
    raw = exc.headers.get(passkey.OPTIONS_HEADER) if exc.headers else None
    return json.loads(passkey._unb64(raw)) if raw else None


class Passkeys(unittest.TestCase):
    def setUp(self):
        guard.reset()
        core._windows.clear()
        self.c = TestClient(panel.app, base_url=BASE)
        r = ADMIN.post("/api/admin/profiles", json={"name": "PassPia", "pin": "1234"})
        self.assertIn(r.status_code, (200, 409))
        self.assertEqual(self.c.post("/api/profile/login", json={"name": "PassPia", "pin": "1234"}).status_code, 200)
        self.uid = uid_of("PassPia")
        fake_second_step(self.uid)
        self.real = mfa.verify
        mfa.verify = lambda who, code: code == "123456"

    def tearDown(self):
        mfa.verify = self.real
        mfa.disable(self.uid)
        core._windows.clear()
        guard.reset()

    def add(self, a=None, name="Mac"):
        a = a or Authenticator()
        self.assertEqual(self.c.post("/api/profile/mfa/passkeys/begin").status_code, 428)   # a new way in: fresh code
        o = self.c.post("/api/profile/mfa/passkeys/begin", headers=CODE)
        self.assertEqual(o.status_code, 200, o.text)
        o = o.json()
        r = self.c.post("/api/profile/mfa/passkeys/finish", json={"sid": o["sid"], "response": a.create(o["options"]), "name": name})
        self.assertEqual(r.status_code, 200, r.text)
        return a, r.json()

    def test_host_names_only(self):
        req = lambda h: Req(headers={"host": h})   # noqa: E731
        self.assertEqual(passkey.rp_id(req("speech.example.de:31443")), HOST)
        self.assertEqual(passkey.rp_id(req("Speech.Example.DE")), HOST)
        for bad in ("192.168.178.171", "192.168.178.171:31443", "localhost", "[::1]:31443", "", "a..b", "x" * 300 + ".de", "ex ample.de"):
            self.assertIsNone(passkey.rp_id(req(bad)), bad)
        lan = TestClient(panel.app, base_url="https://192.168.178.171")
        lan.post("/api/profile/login", json={"name": "PassPia", "pin": "1234", "code": "123456"})
        self.assertEqual(lan.post("/api/profile/mfa/passkeys/begin", headers=CODE).status_code, 409)

    def test_add_list_remove(self):
        a, d = self.add()
        self.assertEqual([(x["name"], x["rp"], x["here"]) for x in d["items"]], [("Mac", HOST, True)])
        self.assertNotIn("cred", json.dumps(d))           # the key data never goes back
        # the same passkey twice is refused, an old or foreign challenge too
        o = self.c.post("/api/profile/mfa/passkeys/begin", headers=CODE).json()
        r = self.c.post("/api/profile/mfa/passkeys/finish", json={"sid": o["sid"], "response": a.create(o["options"])})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.post("/api/profile/mfa/passkeys/finish", json={"sid": o["sid"], "response": {}}).status_code, 400)
        other = TestClient(panel.app, base_url=BASE)
        other.post("/api/profile/login", json={"name": "PassPia", "pin": "1234", "code": "123456"})
        o = self.c.post("/api/profile/mfa/passkeys/begin", headers=CODE).json()
        r = other.post("/api/profile/mfa/passkeys/finish", json={"sid": o["sid"], "response": Authenticator().create(o["options"])})
        self.assertEqual(r.status_code, 400)               # another login of the same profile cannot finish it
        # a page of another site cannot make one for us
        o = self.c.post("/api/profile/mfa/passkeys/begin", headers=CODE).json()
        r = self.c.post("/api/profile/mfa/passkeys/finish", json={"sid": o["sid"], "response": Authenticator("https://evil.example").create(o["options"])})
        self.assertEqual(r.status_code, 400)
        kid = d["items"][0]["id"]
        self.assertEqual(self.c.delete(f"/api/profile/mfa/passkeys/{kid}").status_code, 200)
        self.assertEqual(self.c.get("/api/profile/mfa/passkeys").json()["items"], [])
        self.assertEqual(self.c.delete(f"/api/profile/mfa/passkeys/{kid}").status_code, 404)
        # gone with the second step
        self.add()
        mfa.disable(self.uid)
        fake_second_step(self.uid)
        self.assertEqual(passkey.listing(self.uid), [])

    def test_confirm_with_passkey(self):
        a, _ = self.add()
        core._windows.clear()
        req = lambda **h: Req(self.c, dict({"host": HOST}, **h))   # noqa: E731
        run = lambda r, fresh=False: asyncio.run(core.confirm_code(r, self.uid, "PassPia", fresh))   # noqa: E731
        with self.assertRaises(HTTPException) as e:
            run(req())
        opt = header_options(e.exception)
        self.assertTrue(opt and opt["sid"])
        answer = {"sid": opt["sid"], "response": a.get(opt["options"])}
        signed = b64(json.dumps(answer).encode())
        run(req(**{passkey.HEADER: signed}), fresh=True)   # counts like a fresh code
        self.assertTrue(core.window_until(self.uid, core._login_key(req(), self.uid)))
        with self.assertRaises(HTTPException):   # the same signature a second time: no
            run(req(**{passkey.HEADER: signed}), fresh=True)
        # a signature for another host name or with another key: no
        for make in (lambda o: a.get(o, rp="evil.example"), lambda o: Authenticator().get(o)):
            with self.assertRaises(HTTPException) as e:
                run(req(), fresh=True)
            o2 = header_options(e.exception)
            with self.assertRaises(HTTPException):
                run(req(**{passkey.HEADER: b64(json.dumps({"sid": o2["sid"], "response": make(o2["options"])}).encode())}), fresh=True)
        with self.assertRaises(HTTPException):
            run(req(**{passkey.HEADER: "!!!"}), fresh=True)
        # another person cannot use this challenge
        with self.assertRaises(HTTPException) as e:
            run(req(), fresh=True)
        o3 = header_options(e.exception)
        self.assertFalse(passkey.finish_auth(mfa.ADMIN, {"sid": o3["sid"], "response": a.get(o3["options"])}, req(), "login"))
        # over an IP address nothing is offered
        with self.assertRaises(HTTPException) as e:
            run(Req(self.c, {"host": "192.168.178.171"}), fresh=True)
        self.assertIsNone(header_options(e.exception))

    def test_login_with_passkey(self):
        a, _ = self.add()
        n = TestClient(panel.app, base_url=BASE)
        r = n.post("/api/profile/login", json={"name": "PassPia", "pin": "1234"}).json()
        self.assertTrue(r["code"])
        opt = r["passkey"]
        bad = n.post("/api/profile/login", json={"name": "PassPia", "pin": "1234", "passkey": {"sid": opt["sid"], "response": Authenticator().get(opt["options"])}})
        self.assertEqual(bad.status_code, 401)
        r = n.post("/api/profile/login", json={"name": "PassPia", "pin": "1234"}).json()
        ok = n.post("/api/profile/login", json={"name": "PassPia", "pin": "1234", "passkey": {"sid": r["passkey"]["sid"], "response": a.get(r["passkey"]["options"])}})
        self.assertEqual(ok.json(), {"ok": True})
        self.assertGreater(passkey.listing(self.uid)[0]["last"], 0)
        # the wrong PIN never reveals a passkey challenge
        self.assertEqual(TestClient(panel.app, base_url=BASE).post("/api/profile/login", json={"name": "PassPia", "pin": "9999"}).status_code, 401)

    def test_states_are_capped_and_short(self):
        self.assertEqual(passkey.STATE_SECS, 120)
        for i in range(passkey.MAX_STATES + 5):
            passkey._keep("u_000000000000", "auth", {}, HOST, "x", now=1000)
        self.assertLessEqual(len(passkey._states), passkey.MAX_STATES)
        sid = passkey._keep("u_000000000000", "auth", {"c": 1}, HOST, "x", now=1000)
        self.assertIsNone(passkey._take(sid, "u_000000000000", "auth", HOST, "x", now=1000 + passkey.STATE_SECS + 1))
        passkey._states.clear()

    def test_installed_pinned_without_deps(self):
        # a new environment: from the lock with its hash; an older one (like tars): alone and without dependencies
        lock = open(helpers.os.path.join(helpers.APP, "requirements-panel.lock")).read()
        self.assertRegex(lock, r"fido2==2\.2\.1 \\\n    --hash=sha256:[0-9a-f]{64}")
        path = helpers.os.path.join(helpers.APP, "..", "install.sh")
        if not helpers.os.path.exists(path):
            self.skipTest("install.sh is not in an app/-only copy")
        sh = open(path).read()
        line = next(x for x in sh.splitlines() if "fido2==" in x and not x.lstrip().startswith("#"))
        self.assertIn("--no-deps", line)
        self.assertIn('"fido2==2.2.1"', line)
        panel_line = next(x for x in sh.splitlines() if x.lstrip().startswith("make_venv panel"))
        self.assertNotIn("fido2", panel_line)

if __name__ == "__main__":
    unittest.main()
