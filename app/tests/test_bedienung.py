"""Plan "Bedienung gesamt" (V01.0.262+): browser protection headers, the list of signed-in browsers,
the sign-in duration, short PINs and "Sicherheit auf einen Blick"."""
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234", agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app, headers={"user-agent": agent})
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


class Headers(unittest.TestCase):
    def test_every_answer_is_protected(self):
        c = TestClient(panel.app)
        for path in ("/", "/api/whoami", "/static/app.css", "/api/nothing-here"):
            r = c.get(path)
            self.assertEqual(r.headers.get("x-frame-options"), "SAMEORIGIN", path)
            self.assertEqual(r.headers.get("x-content-type-options"), "nosniff", path)
            self.assertEqual(r.headers.get("referrer-policy"), "same-origin", path)
            self.assertIn("frame-ancestors 'self'", r.headers.get("content-security-policy", ""), path)
            self.assertIn("microphone=(self)", r.headers.get("permissions-policy", ""), path)
            self.assertNotIn("strict-transport-security", r.headers, path)   # plain http: no HSTS

    def test_https_gets_hsts_and_secure_cookies(self):
        c = TestClient(panel.app, base_url="https://testserver")
        r = c.post("/api/login", json={"password": "secret-admin"})
        self.assertIn("max-age=", r.headers.get("strict-transport-security", ""))
        self.assertIn("secure", r.headers.get("set-cookie", "").lower())

    def test_refused_foreign_page_is_protected_too(self):
        c = TestClient(panel.app)
        r = c.post("/api/profile/settings", json={}, headers={"origin": "https://evil.example"})
        self.assertEqual(r.headers.get("x-frame-options"), "SAMEORIGIN")


class Sessions(unittest.TestCase):
    def test_list_and_end_one_browser(self):
        a = profile("BedLisa")
        b = profile("BedLisa", agent="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36")
        d = a.get("/api/profile/sessions").json()
        mine = [x for x in d["sessions"] if x["this"]]
        other = [x for x in d["sessions"] if not x["this"]]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["agent"], "iPhone · Safari")
        self.assertTrue(any(x["agent"] == "Windows · Chrome" for x in other))
        self.assertNotIn("ip", mine[0])   # no address is kept
        for x in other:
            self.assertEqual(a.delete("/api/profile/sessions/" + x["id"]).status_code, 200)
        self.assertIsNone(b.get("/api/whoami").json()["profile"])
        self.assertEqual(a.get("/api/whoami").json()["profile"]["name"], "BedLisa")

    def test_cannot_end_another_profiles_browser(self):
        a, b = profile("BedMara"), profile("BedNils")
        sid = next(x["id"] for x in b.get("/api/profile/sessions").json()["sessions"])
        self.assertEqual(a.delete("/api/profile/sessions/" + sid).status_code, 404)
        self.assertEqual(a.delete("/api/profile/sessions/..%2f..").status_code, 404)
        self.assertEqual(b.get("/api/whoami").json()["profile"]["name"], "BedNils")

    def test_admin_sees_and_ends_browsers(self):
        p = profile("BedOlga")
        uid = p.get("/api/whoami").json()["profile"]["id"]
        d = ADMIN.get(f"/api/admin/profiles/{uid}").json()
        self.assertEqual(len(d["sessions"]), 1)
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{uid}/sessions/{d['sessions'][0]['id']}").status_code, 200)
        self.assertIsNone(p.get("/api/whoami").json()["profile"])
        self.assertEqual(TestClient(panel.app).delete(f"/api/admin/profiles/{uid}/sessions/0123456789abcdef").status_code, 401)

    def test_logout_ends_the_session(self):
        p = profile("BedPaul")
        raw = p.cookies.get(profiles.COOKIE)
        p.post("/api/profile/logout")
        stolen = TestClient(panel.app)
        stolen.cookies.set(profiles.COOKIE, raw)
        self.assertIsNone(stolen.get("/api/whoami").json()["profile"])

    def test_old_three_part_logins_still_work_and_get_a_session(self):
        profile("BedQuirin")
        u = next(x for x in profiles._load()["users"] if x["name"] == "BedQuirin")
        issued = int(time.time() - 2 * 86400)
        old = TestClient(panel.app)
        old.cookies.set(profiles.COOKIE, f"{u['id']}.{issued}.{profiles._sign(u, issued)}")
        self.assertEqual(old.get("/api/whoami").json()["profile"]["name"], "BedQuirin")
        self.assertEqual(old.get("/api/profile/sessions").status_code, 200)
        new = [c.value for c in old.cookies.jar if c.name == profiles.COOKIE]
        self.assertTrue(any(v.count(".") == 3 for v in new))   # renewed with a session

    def test_sign_in_ends_after_the_set_days(self):
        profile("BedRita")
        u = next(x for x in profiles._load()["users"] if x["name"] == "BedRita")
        c = TestClient(panel.app)
        c.cookies.set(profiles.COOKIE, profiles._cookie_value(u, time.time() - 31 * 86400))
        self.assertIsNone(c.get("/api/whoami").json()["profile"])   # default 30 days
        cfg = ADMIN.get("/api/config").json()
        cfg["panel"]["session_days"] = 6
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)
        cfg["panel"]["session_days"] = "60"
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)


class Glance(unittest.TestCase):
    def test_short_pin_and_admin_mfa_show(self):
        profile("BedSven", pin="1212")
        d = ADMIN.get("/api/admin/security-glance").json()
        keys = {x["key"]: x for x in d["items"]}
        self.assertEqual(keys["admin_mfa"]["lvl"], "bad")
        self.assertIn("BedSven", profiles.short_pins())
        self.assertEqual(keys["short_pins"]["lvl"], "warn")
        self.assertEqual(d["items"][0]["lvl"], "bad")   # red first
        profile("BedTina", pin="123456")
        d = ADMIN.get("/api/admin/security-glance").json()
        self.assertNotIn("BedTina", profiles.short_pins())

    def test_only_admins(self):
        self.assertEqual(TestClient(panel.app).get("/api/admin/security-glance").status_code, 401)
        self.assertIn(profile("BedUwe").get("/api/admin/security-glance").status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
