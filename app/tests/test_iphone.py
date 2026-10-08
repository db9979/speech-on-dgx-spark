"""iPhone app (iphone.py): pairing with a one-time link, the key's narrow scope, the switches."""
import json
import unittest
import urllib.parse

from tests import helpers

helpers.start()
import guard  # noqa: E402
import iphone  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BASE = "https://speech.example.de"


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def code_of(link):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    assert q["url"] == [BASE], link
    return q["code"][0]


def pair(c, name="Annas iPhone"):
    r = c.post("/api/profile/iphone/pair", json={"base": BASE})
    assert r.status_code == 200, r.text
    assert r.json()["link"].startswith("spark-app://pair?")
    return TestClient(panel.app).post("/api/iphone/pair", json={"code": code_of(r.json()["link"]), "name": name})


class IPhone(unittest.TestCase):
    def setUp(self):
        helpers.set_config(iphone=True)
        iphone._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:   # every test client shares one address
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(iphone=False)

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["iphone"], False)
        for k in ("app_on", "app_ha"):
            self.assertIs(profiles.SETTINGS[k][0], False)

    def test_pairing_needs_both_switches_and_works_once(self):
        a = profile("Iris")
        self.assertEqual(a.post("/api/profile/iphone/pair", json={"base": BASE}).status_code, 403)
        a.put("/api/profile/settings", json={"app_on": True})
        helpers.set_config(iphone=False)
        self.assertEqual(a.post("/api/profile/iphone/pair", json={"base": BASE}).status_code, 403)
        helpers.set_config(iphone=True)
        # the app needs a real certificate: https only, no path
        for bad in ("http://speech.example.de", "https://x.de/panel", "javascript:alert(1)"):
            self.assertEqual(a.post("/api/profile/iphone/pair", json={"base": bad}).status_code, 400, bad)
        link = a.post("/api/profile/iphone/pair", json={"base": BASE}).json()["link"]
        code = code_of(link)
        app = TestClient(panel.app)
        r = app.post("/api/iphone/pair", json={"code": code, "name": "Iris <b>Phone"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["profile"], "Iris")
        token = r.json()["token"]
        # used once: never again
        self.assertEqual(app.post("/api/iphone/pair", json={"code": code}).status_code, 400)
        self.assertEqual(app.post("/api/iphone/pair", json={"code": "x" * 24}).status_code, 400)
        ph = a.get("/api/profile/iphone").json()["phones"]
        self.assertEqual([p["name"] for p in ph], ["Iris bPhone"])
        self.assertNotIn(token, json.dumps(profiles._load()))   # only the hash is kept
        h = {"X-Speech-Device": token}
        self.assertEqual(app.get("/api/iphone/hello", headers=h).json()["profile"], "Iris")

    def test_code_expires(self):
        profile("Ida")
        uid = uid_of("Ida")
        code = iphone.new_code(uid, now=1000.0)
        self.assertIsNone(iphone.take_code(code, now=1000.0 + iphone.CODE_SECONDS + 1))
        code = iphone.new_code(uid, now=2000.0)
        self.assertEqual(iphone.take_code(code, now=2000.0 + 10), uid)
        # a profile holds only a few open codes; a new one replaces the oldest
        codes = [iphone.new_code(uid, now=3000.0 + i) for i in range(iphone.PER_PROFILE + 2)]
        self.assertIsNone(iphone.take_code(codes[0], now=3010.0))
        self.assertEqual(iphone.take_code(codes[-1], now=3010.0), uid)

    def test_key_only_asks_and_listens(self):
        a = profile("Ina")
        a.put("/api/profile/settings", json={"app_on": True})
        token = pair(a).json()["token"]
        app = TestClient(panel.app)
        h = {"X-Speech-Device": token}
        r = app.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(app.post("/api/siri/ask", json={"text": "Hallo"}, headers=h).status_code, 200)
        # nothing else: no settings, no memory, no devices, no pairing of more phones, no mail or calendar pages
        self.assertEqual(app.get("/api/profile/settings", headers=h).status_code, 401)
        self.assertEqual(app.put("/api/profile/settings", json={"app_ha": True}, headers=h).status_code, 401)
        self.assertIn(app.get("/api/profile/facts", headers=h).status_code, (401, 404))
        self.assertEqual(app.get("/api/profile/iphone", headers=h).status_code, 401)
        self.assertEqual(app.post("/api/profile/iphone/pair", json={"base": BASE}, headers=h).status_code, 401)
        self.assertEqual(app.get("/api/tasks/inbox?list=einkauf", headers=h).status_code, 401)
        # switched off: the key stops at once (profile switch, then admin switch)
        a.put("/api/profile/settings", json={"app_on": False})
        self.assertEqual(app.get("/api/iphone/hello", headers=h).status_code, 401)
        a.put("/api/profile/settings", json={"app_on": True})
        self.assertEqual(app.get("/api/iphone/hello", headers=h).status_code, 200)
        helpers.set_config(iphone=False)
        self.assertEqual(app.get("/api/iphone/hello", headers=h).status_code, 401)
        self.assertEqual(app.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]},
                                  headers=h).status_code, 401)

    def test_remove_and_admin_cannot_move_it(self):
        a, b = profile("Ilse"), profile("Ivo")
        a.put("/api/profile/settings", json={"app_on": True})
        token = pair(a).json()["token"]
        did = a.get("/api/profile/iphone").json()["phones"][0]["id"]
        self.assertEqual(ADMIN.put(f"/api/admin/devices/{did}", json={"user": uid_of("Ivo")}).status_code, 400)
        self.assertEqual(b.delete(f"/api/profile/iphone/{did}").status_code, 404)   # not Ivo's
        h = {"X-Speech-Device": token}
        app = TestClient(panel.app)
        self.assertEqual(app.delete(f"/api/profile/iphone/{did}", headers=h).status_code, 401)
        self.assertEqual(a.delete(f"/api/profile/iphone/{did}").json()["phones"], [])
        self.assertEqual(app.get("/api/iphone/hello", headers=h).status_code, 401)

    def test_smart_home_only_when_allowed_for_the_app(self):
        a = profile("Isa")
        url = f"http://127.0.0.1:{helpers.HA_PORT}"
        try:
            self.assertEqual(a.put("/api/profile/homeassistant", json={"url": url, "token": helpers.HA_TOKEN}).status_code, 200)
            a.put("/api/profile/settings", json={"app_on": True})
            h = {"X-Speech-Device": pair(a).json()["token"]}
            app = TestClient(panel.app)

            def said(text):
                r = app.post("/api/chat", json={"messages": [{"role": "user", "content": text}]}, headers=h)
                return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
            cmd = 'TOOL home_assistant {"command": "Licht in der Küche an"}'
            self.assertIn("NO TOOL home_assistant", said(cmd))
            # the request cannot claim to be something else
            r = app.post("/api/chat", json={"messages": [{"role": "user", "content": cmd}], "client": "watch"}, headers=h)
            self.assertIn("NO TOOL home_assistant", "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text"))
            a.put("/api/profile/settings", json={"app_ha": True})
            self.assertNotIn("NO TOOL home_assistant", said(cmd))
        finally:
            a.delete("/api/profile/homeassistant")

    def test_pair_is_rate_limited(self):
        app = TestClient(panel.app)
        codes = [app.post("/api/iphone/pair", json={"code": "y" * 24}).status_code for _ in range(15)]
        self.assertIn(429, codes)
        self.assertNotIn(200, codes)


if __name__ == "__main__":
    unittest.main()
