"""Apple push to the iPhone app (apns.py): off by default, the .p8 sealed and never sent back, device
tokens only from the app's own key, Apple sees only a fixed sentence, the text waits on the Spark for
the profile's own app, limits, and CarPlay never unlocks the smart home by itself."""
import asyncio
import json
import unittest

from tests import helpers

helpers.start()
import apns  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import ADMIN, pair, profile, uid_of  # noqa: E402

PEM = ec.generate_private_key(ec.SECP256R1()).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
GOOD = {"key": PEM, "key_id": "ABC123DEFG", "team": "TEAM123456", "bundle": "io.github.db9979.speechspark", "sandbox": True}
T1 = "a" * 64
T2 = "b" * 64


class Reply:
    def __init__(self, status, reason=""):
        self.status_code = status
        self._reason = reason

    def json(self):
        return {"reason": self._reason} if self._reason else {}


class Dummy:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class Apns(unittest.TestCase):
    def setUp(self):
        helpers.set_config(iphone=True, iphone_push=True)
        apns._sent.clear()
        apns._inbox.clear()
        self.posted = []
        self.answer = Reply(200)

        async def post(c, s, token, body, now):
            self.posted.append((token, body))
            return self.answer
        self._post, apns._post = apns._post, post
        # no network and no h2 needed in the self-test
        self._client, apns._client = apns._client, lambda: Dummy()

    def tearDown(self):
        apns._post, apns._client = self._post, self._client
        apns.forget()
        helpers.set_config(iphone=False, iphone_push=False)

    def phone(self, name):
        c = profile(name)
        c.put("/api/profile/settings", json={"app_on": True})
        return c, {"X-Speech-Device": pair(c).json()["token"]}

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["iphone_push"], False)
        for k in ("app_push", "app_car_ha"):
            self.assertIs(profiles.SETTINGS[k][0], False)
        self.assertFalse(apns.ready())

    def test_key_only_for_the_admin_sealed_and_never_returned(self):
        c, h = self.phone("Pia")
        self.assertEqual(c.put("/api/admin/apns", json=GOOD).status_code, 401)
        self.assertEqual(TestClient(panel.app).put("/api/admin/apns", json=GOOD, headers=h).status_code, 401)
        for bad in ({"key": "-----BEGIN PRIVATE KEY-----\nxx\n-----END PRIVATE KEY-----"}, {"key_id": "abc"},
                    {"team": "../x"}, {"bundle": "a b"}):
            self.assertEqual(ADMIN.put("/api/admin/apns", json=dict(GOOD, **bad)).status_code, 400, bad)
        r = ADMIN.put("/api/admin/apns", json=GOOD)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("PRIVATE", r.text)
        self.assertNotIn("PRIVATE", ADMIN.get("/api/admin/apns").text)
        with open(apns._file("apns.json")) as f:
            self.assertNotIn("PRIVATE KEY", f.read())
        self.assertTrue(apns.ready())
        # other fields change without sending the key again
        self.assertEqual(ADMIN.put("/api/admin/apns", json=dict(GOOD, key="", sandbox=False)).status_code, 200)
        self.assertTrue(apns.ready())
        self.assertFalse(apns.settings()["sandbox"])

    def test_token_only_from_the_app_key(self):
        ADMIN.put("/api/admin/apns", json=GOOD)
        c, h = self.phone("Paula")
        app = TestClient(panel.app)
        self.assertEqual(c.post("/api/iphone/push-token", json={"token": T1}).status_code, 403)
        for bad in ("x" * 64, "a" * 10, "a" * 300, 5):
            self.assertEqual(app.post("/api/iphone/push-token", json={"token": bad}, headers=h).status_code, 400, bad)
        r = app.post("/api/iphone/push-token", json={"token": T1.upper()}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["push"])                 # the profile has not switched it on
        uid = uid_of("Paula")
        self.assertEqual(apns.profile_tokens(uid)[0][1], T1)
        self.assertFalse(apns.reachable(uid))
        c.put("/api/profile/settings", json={"app_push": True})
        self.assertTrue(apns.reachable(uid))
        self.assertTrue(app.get("/api/iphone/hello", headers=h).json()["push"])
        # admin switch off: nothing goes out
        helpers.set_config(iphone_push=False)
        self.assertFalse(apns.reachable(uid))

    def test_apple_sees_only_a_fixed_sentence_and_the_app_fetches_the_text(self):
        ADMIN.put("/api/admin/apns", json=GOOD)
        c, h = self.phone("Petra")
        app = TestClient(panel.app)
        app.post("/api/iphone/push-token", json={"token": T1}, headers=h)
        c.put("/api/profile/settings", json={"app_push": True})
        uid = uid_of("Petra")
        n = asyncio.run(apns.send(uid, "⏰ Tee", "Geheimer Termin beim Arzt", tag="rem-1", now=1000))
        self.assertEqual(n, 1)
        token, body = self.posted[-1]
        self.assertEqual(token, T1)
        raw = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("Arzt", raw)
        self.assertNotIn("Tee", raw)
        self.assertEqual(body["aps"]["alert"]["body"], apns.GENERIC)
        nid = body["n"]
        # the text comes only to the profile's own app key, by its random id, and not too late
        self.assertEqual(apns.note(uid, nid, now=1001)["body"], "Geheimer Termin beim Arzt")
        self.assertIsNone(apns.note(uid, nid, now=1000 + apns.INBOX_SECONDS + 1))
        self.assertIsNone(apns.note("u_000000000000", nid, now=1001))
        self.assertIsNone(apns.note(uid, "../x", now=1001))
        other, oh = self.phone("Pauline")
        self.assertEqual(TestClient(panel.app).get("/api/iphone/note", params={"id": nid}, headers=oh).status_code, 404)

    def test_limits_and_gone_tokens(self):
        ADMIN.put("/api/admin/apns", json=GOOD)
        c, h = self.phone("Pina")
        TestClient(panel.app).post("/api/iphone/push-token", json={"token": T2}, headers=h)
        c.put("/api/profile/settings", json={"app_push": True})
        uid = uid_of("Pina")
        sent = sum(asyncio.run(apns.send(uid, "x", "y", now=5000 + i)) for i in range(apns.PER_HOUR + 5))
        self.assertEqual(sent, apns.PER_HOUR)
        apns._sent.clear()
        self.answer = Reply(410, "Unregistered")
        self.assertEqual(asyncio.run(apns.send(uid, "x", "y", now=9000)), 0)
        self.assertEqual(apns.profile_tokens(uid), [])

    def test_removed_iphone_gets_nothing(self):
        ADMIN.put("/api/admin/apns", json=GOOD)
        c, h = self.phone("Polly")
        TestClient(panel.app).post("/api/iphone/push-token", json={"token": T1}, headers=h)
        c.put("/api/profile/settings", json={"app_push": True})
        did = c.get("/api/profile/iphone").json()["phones"][0]["id"]
        uid = next(x["user"] for x in profiles._load()["devices"] if x["id"] == did)
        self.assertEqual(len(apns.profile_tokens(uid)), 1)
        c.delete("/api/profile/iphone/" + did)
        self.assertEqual(apns.profile_tokens(uid), [])

    def test_car_mode_never_unlocks_the_smart_home(self):
        a = profile("Pit")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        try:
            self.assertEqual(a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN}).status_code, 200)
            a.put("/api/profile/settings", json={"app_on": True, "app_ha": True})
            h = {"X-Speech-Device": pair(a).json()["token"]}
            app = TestClient(panel.app)
            cmd = 'TOOL home_assistant {"command": "Licht in der Küche an"}'

            def said(car):
                r = app.post("/api/chat", json={"messages": [{"role": "user", "content": cmd}], "car": car}, headers=h)
                return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
            self.assertNotIn("NO TOOL home_assistant", said(False))
            self.assertIn("NO TOOL home_assistant", said(True))
            a.put("/api/profile/settings", json={"app_car_ha": True})
            self.assertNotIn("NO TOOL home_assistant", said(True))
            # the car switch alone is not enough
            a.put("/api/profile/settings", json={"app_ha": False})
            self.assertIn("NO TOOL home_assistant", said(True))
        finally:
            a.delete("/api/profile/homeassistant")


if __name__ == "__main__":
    unittest.main()
