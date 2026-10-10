"""Fewer codes, same protection (plan plaene/zweiter-schritt-seltener.md, V01.0.289): trusted browsers one by one
(days from panel.trust_days, end after 30 days without use, at most ten, removable), a right code counts ten
minutes only in the same login while the most important changes always ask, and the admin mode stays open longer
only in a trusted browser. No test depends on the wall clock: times are passed in or the window is set by hand."""
import asyncio
import secrets
import time
import unittest

from tests import helpers

helpers.start()
import coadmin  # noqa: E402
import core  # noqa: E402
import guard  # noqa: E402
import mfa  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import ADMIN, profile, uid_of  # noqa: E402

CODE = {"X-Speech-Code": "123456"}


class Req:
    """Just enough of a request for the functions below (cookies and headers of a TestClient)."""
    def __init__(self, client=None, headers=None):
        self.cookies = {k: v for k, v in (client.cookies.items() if client else [])}
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.scope = {}
        self.client = type("C", (), {"host": "127.0.0.1"})()


def fake_second_step(uid):
    """A second step for `uid` without an authenticator app: the file as mfa.finish writes it."""
    mfa._write(uid, {"secret": "x", "last": -1, "recovery": [], "tkey": secrets.token_hex(32), "since": 0})


class TrustedBrowsers(unittest.TestCase):
    def setUp(self):
        guard.reset()
        self.c = profile("TrustTina")
        self.uid = uid_of("TrustTina")
        fake_second_step(self.uid)

    def tearDown(self):
        mfa.disable(self.uid)
        guard.reset()

    def cookie(self, value):
        r = Req()
        r.cookies = {mfa.trust_cookie(self.uid): value}
        return r

    def test_listed_removed_and_limited(self):
        now = 1_000_000_000
        v = mfa.add_trusted(self.uid, "iPhone · Safari", now=now)
        self.assertTrue(mfa.trusted(self.uid, self.cookie(v), now=now + 3600))
        items = mfa.list_trusted(self.uid, self.cookie(v), now=now + 3600)
        self.assertEqual([(x["name"], x["this"]) for x in items], [("iPhone · Safari", True)])
        # a changed signature, another person's cookie name or an old cookie without id do not count
        self.assertFalse(mfa.trusted(self.uid, self.cookie(v[:-1] + ("0" if v[-1] != "0" else "1")), now=now))
        self.assertFalse(mfa.trusted(self.uid, self.cookie(v.split(".", 1)[1]), now=now))
        # removed one by one: asks again
        self.assertTrue(mfa.remove_trusted(self.uid, v.split(".")[0]))
        self.assertFalse(mfa.trusted(self.uid, self.cookie(v), now=now))
        self.assertFalse(mfa.remove_trusted(self.uid, v.split(".")[0]))
        # at most MAX_TRUSTED: the least recently used one drops out
        vals = [mfa.add_trusted(self.uid, f"B{i}", now=now + i) for i in range(mfa.MAX_TRUSTED + 1)]
        self.assertEqual(len(mfa.list_trusted(self.uid, now=now + 20)), mfa.MAX_TRUSTED)
        self.assertFalse(mfa.trusted(self.uid, self.cookie(vals[0]), now=now + 20))
        self.assertTrue(mfa.trusted(self.uid, self.cookie(vals[-1]), now=now + 20))
        # "forget all" ends every one
        mfa.forget_trust(self.uid)
        self.assertEqual(mfa.list_trusted(self.uid, now=now + 20), [])
        self.assertFalse(mfa.trusted(self.uid, self.cookie(vals[-1]), now=now + 20))

    def test_days_and_idle(self):
        now = 1_000_000_000
        v = mfa.add_trusted(self.uid, "Mac · Safari", now=now)
        days = mfa.trust_days()
        self.assertEqual(days, 60)   # Dominik's choice as the default
        # used every 20 days: holds until the days are over, not longer
        for d in range(20, days, 20):
            self.assertTrue(mfa.trusted(self.uid, self.cookie(v), now=now + d * 86400))
        self.assertFalse(mfa.trusted(self.uid, self.cookie(v), now=now + days * 86400 + 1))
        # not used for TRUST_IDLE_DAYS: asks again even within the days
        w = mfa.add_trusted(self.uid, "Windows · Edge", now=now)
        self.assertFalse(mfa.trusted(self.uid, self.cookie(w), now=now + (mfa.TRUST_IDLE_DAYS + 1) * 86400))

    def test_trust_days_validated(self):
        cfg = ADMIN.get("/api/config").json()
        for bad in (6, 91, "60", True):
            cfg["panel"]["trust_days"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, bad)
        self.assertIn(("panel", "trust_days"), __import__("admin").SENSITIVE)   # longer trust: a code when the second step is on

    def test_login_list_and_remove_over_http(self):
        real = mfa.verify
        mfa.verify = lambda who, code: code == "123456"
        try:
            n = TestClient(panel.app, headers={"user-agent": "Mozilla/5.0 (iPhone) Safari/605"})
            self.assertEqual(n.post("/api/profile/login", json={"name": "TrustTina", "pin": "1234"}).json(), {"code": True})
            r = n.post("/api/profile/login", json={"name": "TrustTina", "pin": "1234", "code": "123456", "trust": True})
            self.assertEqual(r.json(), {"ok": True})
            items = n.get("/api/profile/mfa/trusted").json()["items"]
            self.assertEqual([(x["name"], x["this"]) for x in items], [("iPhone · Safari", True)])
            self.assertFalse(self.c.get("/api/profile/mfa/trusted").json()["items"][0]["this"])
            # the trusted browser signs in with the PIN alone
            n.cookies.delete(profiles.COOKIE)
            self.assertEqual(n.post("/api/profile/login", json={"name": "TrustTina", "pin": "1234"}).json(), {"ok": True})
            # the admin sees it in the profile and removes it; then the code is asked again
            tid = items[0]["id"]
            self.assertEqual([x["id"] for x in ADMIN.get(f"/api/admin/profiles/{self.uid}").json()["trusted"]], [tid])
            self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{self.uid}/trusted/{tid}").status_code, 200)
            self.assertEqual(self.c.delete(f"/api/profile/mfa/trusted/{tid}").status_code, 404)
            self.assertEqual(self.c.delete("/api/profile/mfa/trusted/..%2Fx").status_code, 404)
            n.cookies.delete(profiles.COOKIE)
            self.assertEqual(n.post("/api/profile/login", json={"name": "TrustTina", "pin": "1234"}).json(), {"code": True})
            # the change is logged
            self.assertTrue(any(x.get("event") == "trusted_browser" and x.get("uid") == self.uid for x in guard.read(50)))
        finally:
            mfa.verify = real


class ConfirmWindow(unittest.TestCase):
    def setUp(self):
        guard.reset()
        core._windows.clear()
        self.real = (mfa.enabled, mfa.verify)
        self.on = {mfa.ADMIN}
        mfa.enabled = lambda who: who in self.on
        mfa.verify = lambda who, code: who in self.on and code == "123456"

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        core._windows.clear()
        guard.reset()

    def test_admin_window_same_login_only(self):
        self.assertEqual(ADMIN.post("/api/admin/devices", json={"name": "Box1", "user": "x"}).status_code, 428)
        r = ADMIN.post("/api/admin/devices", json={"name": "Box1", "user": "x"}, headers=CODE)
        self.assertNotEqual(r.status_code, 428, r.text)
        until = ADMIN.get("/api/whoami").json()["confirm_until"]
        self.assertGreater(until, 0)
        # the next important change in the same login: no code
        self.assertNotEqual(ADMIN.post("/api/admin/devices", json={"name": "Box2", "user": "x"}).status_code, 428)
        # another admin login of the same password: asks
        other = TestClient(panel.app)
        other.cookies.set(core.COOKIE, core._session_token())
        self.assertEqual(other.get("/api/whoami").json()["confirm_until"], 0)
        self.assertEqual(other.post("/api/admin/devices", json={"name": "Box3", "user": "x"}).status_code, 428)
        # the most important ones always ask: password, second step, roles, backups
        self.assertEqual(ADMIN.post("/api/password", json={"old": "secret-admin", "new": "secret-admin"}).status_code, 428)
        self.assertEqual(ADMIN.post("/api/mfa/recovery").status_code, 428)
        self.assertEqual(ADMIN.put("/api/admin/roles", json={"on": False}).status_code, 428)
        self.assertEqual(ADMIN.post("/api/backups/x.tar.gz/restore").status_code, 428)
        # over: asks again (the window is set back by hand instead of waiting)
        key = next(iter(core._windows))
        core._windows[key] = 1
        self.assertEqual(ADMIN.post("/api/admin/devices", json={"name": "Box4", "user": "x"}).status_code, 428)
        # "Beenden" ends it
        ADMIN.post("/api/admin/devices", json={"name": "Box5", "user": "x"}, headers=CODE)
        self.assertGreater(ADMIN.get("/api/whoami").json()["confirm_until"], 0)
        self.assertEqual(ADMIN.post("/api/confirm/end").json()["ended"], 1)
        self.assertEqual(ADMIN.get("/api/whoami").json()["confirm_until"], 0)
        self.assertEqual(ADMIN.post("/api/admin/devices", json={"name": "Box6", "user": "x"}).status_code, 428)

    def test_profile_window_per_login(self):
        a = profile("WinWilma")
        uid = uid_of("WinWilma")
        b = TestClient(panel.app)
        b.post("/api/profile/login", json={"name": "WinWilma", "pin": "1234"})
        self.on.add(uid)
        run = lambda c, **k: asyncio.run(core.confirm_code(Req(c, k.get("headers")), uid, "WinWilma", k.get("fresh", False)))
        with self.assertRaises(HTTPException):
            run(a)
        run(a, headers=CODE)
        run(a)                                 # within the window: no code
        with self.assertRaises(HTTPException):
            run(b)                             # the same profile in another browser
        with self.assertRaises(HTTPException):
            run(a, fresh=True)                 # always fresh
        with self.assertRaises(HTTPException):  # the window is the profile's, not the admin's
            asyncio.run(core.confirm_code(Req(a), mfa.ADMIN, guard.ADMIN))
        # logging out ends it (and with it the login)
        core.end_window(Req(a))
        with self.assertRaises(HTTPException):
            run(a)
        # nothing is kept without a checked login (a made-up cookie)
        self.assertIsNone(core._login_key(Req(headers={}), uid))
        fake = Req()
        fake.cookies = {profiles.COOKIE: f"{uid}.{int(time.time())}.{'0' * 16}.{'0' * 64}"}
        self.assertIsNone(core._login_key(fake, uid))

    def test_window_is_capped(self):
        now = 1_000_000_000
        for i in range(core.MAX_WINDOWS + 5):
            core._open_window("u_000000000000", f"p:{i:016x}", now=now)
        self.assertLessEqual(len(core._windows), core.MAX_WINDOWS)
        self.assertEqual(core.CONFIRM_WINDOW, 600)


class LongerAdminMode(unittest.TestCase):
    def setUp(self):
        guard.reset()
        core._windows.clear()
        self.c = profile("ModeMax")
        self.uid = uid_of("ModeMax")
        fake_second_step(self.uid)
        self.real = (mfa.enabled, mfa.verify)
        mfa.enabled = lambda who: who in (mfa.ADMIN, self.uid)
        mfa.verify = lambda who, code: code == "123456"
        coadmin.set_on(True)
        coadmin.set_role(self.uid, "coadmin")

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        mfa.disable(self.uid)
        core._windows.clear()
        try:
            import os
            os.remove(coadmin.FILE)
        except OSError:
            pass
        guard.reset()

    def test_limits(self):
        self.assertEqual(coadmin.limits("b"), (900, 8 * 3600))
        self.assertEqual(coadmin.limits("d_000000000000"), (900, 8 * 3600))
        self.assertEqual(coadmin.limits("t"), (3600, 12 * 3600))
        self.assertEqual(coadmin.limits("t", short=True), (900, 8 * 3600))

    def test_trusted_browser_longer_and_still_a_code(self):
        # opening asks for a code even in a trusted browser and with an open confirmation window
        v = mfa.add_trusted(self.uid, "Mac · Safari")
        self.c.cookies.set(mfa.trust_cookie(self.uid), v)
        asyncio.run(core.confirm_code(Req(self.c, CODE), self.uid, "ModeMax"))
        self.assertEqual(self.c.post("/api/admin/elevate").status_code, 428)
        r = self.c.post("/api/admin/elevate", headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        s = coadmin.session(Req(self.c))
        self.assertEqual(s["via"], "t")
        self.assertEqual(coadmin.expires(s) - s["issued"], 3600)
        # 30 minutes without use: still open (a plain browser would be closed)
        self.assertIsNotNone(coadmin.session(Req(self.c), now=s["issued"] + 1800))
        # trust removed: back to the short limits at once
        mfa.remove_trusted(self.uid, v.split(".")[0])
        self.assertIsNone(coadmin.session(Req(self.c), now=s["issued"] + 1800))
        s2 = coadmin.session(Req(self.c), now=s["issued"] + 60)
        self.assertTrue(s2["short"])
        self.assertEqual(coadmin.expires(s2) - s2["issued"], 900)

    def test_plain_browser_short(self):
        r = self.c.post("/api/admin/elevate", headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        s = coadmin.session(Req(self.c))
        self.assertEqual(s["via"], "b")
        self.assertIsNone(coadmin.session(Req(self.c), now=s["issued"] + 1000))
        # a cookie claiming "t" without a trusted browser does not pass the signature
        raw = self.c.cookies.get(coadmin.COOKIE).split(".")
        raw[4] = "t"
        forged = Req(self.c)
        forged.cookies[coadmin.COOKIE] = ".".join(raw)
        self.assertIsNone(coadmin.session(forged))


if __name__ == "__main__":
    unittest.main()
