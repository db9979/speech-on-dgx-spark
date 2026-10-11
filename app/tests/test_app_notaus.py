"""Notaus from the iPhone app (V01.0.370, Paket 3): the app's key switches on Mein Notaus (the button and Siri),
never the whole Spark (that needs the admin login of "Spark verwalten") and never lifts anything. Afterwards the
key only reads the state; everything else answers 503 with "notaus", which the app shows plainly."""
import unittest

from tests.test_notaus import Base, profile, client, profiles
from tests import helpers
import notaus  # noqa: E402


class AppNotaus(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(iphone=True)

    def tearDown(self):
        helpers.set_config(iphone=False)
        super().tearDown()

    def app(self, name, pin="1234"):
        p, uid = profile(name, pin=pin)
        p.put("/api/profile/settings", json={"app_on": True})
        a = client()
        a.headers[profiles.DEVICE_HEADER] = profiles.add_device(name + " App", uid, scope="app")
        return p, uid, a

    def test_mine_from_the_app(self):
        p, uid, a = self.app("NxAppMia")
        self.assertEqual(a.get("/api/notaus").json()["mine"]["on"], False)
        self.assertNotIn("may", a.get("/api/notaus").json())               # no admin details for a profile
        self.assertEqual(a.post("/api/notaus", json={"level": 2}).status_code, 403)   # never the whole Spark
        self.assertEqual(notaus.level(), 0)
        r = a.post("/api/notaus/mine", json={})
        self.assertEqual((r.status_code, r.json()["mine"]["on"]), (200, True))
        self.assertTrue(notaus.own(uid))
        self.assertEqual(a.get("/api/notaus").status_code, 200)           # the state stays readable
        self.assertTrue(a.get("/api/notaus").json()["mine"]["on"])
        r = a.get("/api/iphone/hello")
        self.assertEqual(r.status_code, 503)
        self.assertIn("notaus", r.json())                                  # the app tells it apart
        self.assertTrue(r.json()["detail"].startswith("Mein Notaus"))
        self.assertEqual(a.post("/api/notaus/mine", json={}).status_code, 503)
        self.assertIn(a.post("/api/notaus/mine/off", json={"pin": "1234"}).status_code, (401, 403, 503))
        self.assertTrue(notaus.own(uid))                                   # lifting never from the app

    def test_off_paths_stay_closed_to_the_app(self):
        self.assertIn("/api/notaus/mine", profiles.APP_PATHS)
        for path in ("/api/notaus/mine/off", "/api/admin/notaus/off", "/api/admin/notaus/mine/off"):
            self.assertNotIn(path, profiles.APP_PATHS)
        _, uid, a = self.app("NxAppOle")
        self.assertIn(a.post("/api/admin/notaus/off", json={"to": 0}).status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
