"""Profiles as admins (coadmin.py, V01.0.255): off by default, only with both second steps and a fresh code,
the main admin's own things stay his, admin profiles are changed only by him, a Verwalter reaches only his
list, taking the role away ends the admin mode at once, the iPhone app only with its switch, every admin
action is logged with who did it."""
import time
import unittest

from tests import helpers

helpers.start()
import coadmin  # noqa: E402
import guard  # noqa: E402
import iphone  # noqa: E402
import mfa  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import ADMIN, pair, profile, uid_of  # noqa: E402

CODE = {"X-Speech-Code": "123456"}


class FakeRequest:
    def __init__(self, cookies, path="/api/status", method="GET"):
        self.cookies, self.scope, self.method = cookies, {"path": path}, method


class CoAdmin(unittest.TestCase):
    def setUp(self):
        self.real = (mfa.enabled, mfa.verify)
        self.mfa_on = {mfa.ADMIN}
        mfa.enabled = lambda who: who in self.mfa_on
        mfa.verify = lambda who, code: who in self.mfa_on and code == "123456"
        guard.reset()

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        try:
            import os
            os.remove(coadmin.FILE)
        except OSError:
            pass
        guard.reset()

    def give(self, name, role="coadmin", with_mfa=True):
        c = profile(name)
        uid = uid_of(name)
        if with_mfa:
            self.mfa_on.add(uid)
        coadmin.set_on(True)
        coadmin.set_role(uid, role)
        return c, uid

    def elevate(self, c):
        r = c.post("/api/admin/elevate", headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        return r

    def test_off_by_default(self):
        self.assertFalse(coadmin.listing()["on"])
        c = profile("KoOlaf")
        self.assertEqual(c.post("/api/admin/elevate", headers=CODE).status_code, 403)
        self.assertIsNone(c.get("/api/whoami").json()["admin_role"])
        self.assertIn("admins.json", __import__("backup").STATE_FILES)

    def test_switch_needs_main_second_step(self):
        self.mfa_on.clear()
        with self.assertRaises(ValueError):
            coadmin.set_on(True)
        self.assertEqual(ADMIN.put("/api/admin/roles", json={"on": True}).status_code, 409)
        self.mfa_on.add(mfa.ADMIN)
        self.assertEqual(ADMIN.put("/api/admin/roles", json={"on": True}).status_code, 428)   # the main admin's code
        r = ADMIN.put("/api/admin/roles", json={"on": True}, headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["on"])

    def test_role_alone_is_not_enough(self):
        c, uid = self.give("KoPaul", with_mfa=False)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)   # the profile login is no admin login
        self.assertEqual(c.post("/api/admin/elevate", headers=CODE).status_code, 409)   # own second step missing
        self.mfa_on.add(uid)
        self.assertEqual(c.post("/api/admin/elevate").status_code, 428)   # always a fresh code
        self.assertEqual(c.post("/api/admin/elevate", headers={"X-Speech-Code": "000000"}).status_code, 428)
        self.elevate(c)
        w = c.get("/api/whoami").json()
        self.assertTrue(w["admin"])
        self.assertEqual(w["admin_by"], "coadmin")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)

    def test_guests_and_other_profiles_never(self):
        g = TestClient(panel.app)
        coadmin.set_on(True)
        self.assertEqual(g.post("/api/admin/elevate", headers=CODE).status_code, 401)
        c = profile("KoQuirin")
        self.mfa_on.add(uid_of("KoQuirin"))
        self.assertEqual(c.post("/api/admin/elevate", headers=CODE).status_code, 403)   # no role
        with self.assertRaises(ValueError):
            coadmin.set_role(uid_of("KoQuirin"), "root")

    def test_main_admin_only(self):
        c, uid = self.give("KoRita")
        self.elevate(c)
        for method, path in (("GET", "/api/audit"), ("GET", "/api/admin/roles"), ("PUT", "/api/admin/roles"),
                             ("PUT", f"/api/admin/roles/{uid}"), ("POST", "/api/password"), ("GET", "/api/mfa"),
                             ("POST", "/api/mfa/disable"), ("POST", "/api/logout-everywhere"),
                             ("POST", "/api/backups/x.tar.gz/restore"), ("POST", "/api/backups/x.tar.gz/ticket"),
                             ("GET", "/api/backups/x.tar.gz"), ("DELETE", "/api/backups/x.tar.gz"),
                             ("POST", "/api/backups/move")):
            r = c.request(method, path, json={"role": "coadmin", "on": False}, headers=CODE)
            self.assertEqual(r.status_code, 403, (method, path, r.text))
        self.assertEqual(coadmin.role(uid), "coadmin")   # it could not change itself
        self.assertTrue(coadmin.on())

    def test_admin_profiles_only_by_the_main_admin(self):
        c, uid = self.give("KoSven")
        _, other = self.give("KoTara")
        profile("KoUdo")
        normal = uid_of("KoUdo")
        self.elevate(c)
        for u in (uid, other):
            self.assertEqual(c.put(f"/api/admin/profiles/{u}", json={"pin": "9999"}, headers=CODE).status_code, 403)
            self.assertEqual(c.delete(f"/api/admin/profiles/{u}/mfa", headers=CODE).status_code, 403)
            self.assertEqual(c.delete(f"/api/admin/profiles/{u}", headers=CODE).status_code, 403)
            self.assertEqual(c.post("/api/admin/devices", json={"name": "Box", "user": u}, headers=CODE).status_code, 403)
        # a normal profile: like the main admin, the most important changes with the profile's own code (the code that
        # opened the admin mode counts for ten minutes, core.CONFIRM_WINDOW; "Bestätigung beenden" ends that)
        self.assertEqual(c.put(f"/api/admin/profiles/{normal}", json={"pin": "9998"}).status_code, 200)
        self.assertEqual(c.post("/api/confirm/end").json()["ended"], 1)
        self.assertEqual(c.put(f"/api/admin/profiles/{normal}", json={"pin": "9999"}).status_code, 428)
        self.assertEqual(c.put(f"/api/admin/profiles/{normal}", json={"pin": "9999"}, headers=CODE).status_code, 200)
        tok = c.post("/api/admin/devices", json={"name": "Box", "user": normal}, headers=CODE)
        self.assertEqual(tok.status_code, 200)
        did = next(x["id"] for x in profiles.own_devices(normal) if x["name"] == "Box")
        self.assertEqual(c.put(f"/api/admin/devices/{did}", json={"user": other}, headers=CODE).status_code, 403)
        # the main admin may
        self.assertEqual(ADMIN.put(f"/api/admin/profiles/{other}", json={"pin": "9999"}, headers=CODE).status_code, 200)

    def test_manager_reaches_only_his_list(self):
        c, uid = self.give("KoVera", role="manager")
        self.elevate(c)
        self.assertEqual(c.get("/api/whoami").json()["admin_by"], "manager")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        self.assertEqual(c.get("/api/admin/switches").status_code, 200)
        self.assertEqual(c.get("/api/admin/protocol").status_code, 200)
        for method, path in (("GET", "/api/config"), ("PUT", "/api/config"), ("POST", "/api/update"),
                             ("POST", "/api/service/tts/restart"), ("GET", "/api/backups"), ("POST", "/api/backups"),
                             ("GET", "/api/clone-voices"), ("GET", "/api/admin/telegram")):
            self.assertEqual(c.request(method, path, json={}).status_code, 403, (method, path))

    def test_owner_is_the_main_admin_but_not_the_password(self):
        """Vereinheitlichen Phase 7: the role Haupt-Admin gives one login for everything the panel password may,
        except the password's own things; only the password gives it, and only one profile has it."""
        c, uid = self.give("KoOtto", role="owner")
        self.elevate(c)
        self.assertEqual(c.get("/api/whoami").json()["admin_by"], "owner")
        self.assertEqual(c.get("/api/admin/roles").status_code, 200)
        self.assertEqual(c.get("/api/audit").status_code, 200)
        self.assertEqual(c.get("/api/backups/nichtda.tar.gz").status_code in (400, 404), True)   # reaches it, no 403
        for method, path in (("POST", "/api/password"), ("GET", "/api/mfa"), ("POST", "/api/mfa/disable"),
                             ("POST", "/api/logout-everywhere")):
            self.assertEqual(c.request(method, path, json={}, headers=CODE).status_code, 403, (method, path))
        other = profile("KoOttosKind")
        oid = uid_of("KoOttosKind")
        self.assertEqual(c.put(f"/api/admin/roles/{oid}", json={"role": "owner"}, headers=CODE).status_code, 403)
        self.assertEqual(c.put(f"/api/admin/roles/{uid}", json={"role": ""}, headers=CODE).status_code, 403)
        self.assertEqual(c.put(f"/api/admin/roles/{oid}", json={"role": "coadmin"}, headers=CODE).status_code, 200)
        # he changes another admin profile, not his own one here
        self.assertEqual(c.put(f"/api/admin/profiles/{oid}", json={"pin": "5555"}, headers=CODE).status_code, 200)
        self.assertEqual(c.put(f"/api/admin/profiles/{uid}", json={"pin": "5555"}, headers=CODE).status_code, 403)
        with self.assertRaises(ValueError):
            coadmin.set_role(oid, "owner")                # only one Haupt-Admin
        self.assertEqual(ADMIN.put(f"/api/admin/roles/{oid}", json={"role": "owner"}, headers=CODE).status_code, 409)
        ADMIN.put(f"/api/admin/profiles/{oid}/call", json={"call": "Kindchen"})
        events = c.get("/api/admin/protocol").json()["events"]
        self.assertTrue(any(e.get("by") == "main" for e in events))   # he sees the main admin's actions too

    def test_manager_profile_detail_without_rights(self):
        c, uid = self.give("KoVeit", role="manager")
        self.elevate(c)
        other = profile("KoVeitsKind")
        oid = uid_of("KoVeitsKind")
        d = c.get(f"/api/admin/profiles/{oid}").json()
        self.assertNotIn("rights", d)                 # agent, update and upload space are not his pages
        self.assertFalse(d["main"])
        self.assertEqual(c.put(f"/api/admin/agent/levels/{oid}", json={"level": "read"}).status_code, 403)
        sid = d["sessions"][0]["id"]
        self.assertEqual(c.delete(f"/api/admin/profiles/{oid}/sessions/{sid}").status_code, 200)   # protective, his list
        self.assertIsNone(other.get("/api/whoami").json()["profile"])
        self.assertIn("rights", ADMIN.get(f"/api/admin/profiles/{oid}").json())

    def test_taking_away_ends_it_at_once(self):
        c, uid = self.give("KoWim")
        self.elevate(c)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        coadmin.set_role(uid, "manager")            # a changed role: the old admin mode ends too
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        coadmin.set_role(uid, "coadmin")
        self.elevate(c)
        coadmin.set_on(False)                       # the switch off: no profile is admin any more
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        coadmin.set_on(True)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)   # back on: the same admin mode (role kept)
        self.mfa_on.discard(uid)                    # the profile's second step off
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        self.mfa_on.add(uid)
        self.mfa_on.discard(mfa.ADMIN)              # the main admin's second step off
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        self.mfa_on.add(mfa.ADMIN)
        ADMIN.put(f"/api/admin/roles/{uid}", json={"role": ""}, headers=CODE)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        self.assertEqual(coadmin.role(uid), "")

    def test_ends_with_the_login_and_on_request(self):
        c, uid = self.give("KoXaver")
        self.elevate(c)
        stolen = c.cookies.get(coadmin.COOKIE)
        thief = TestClient(panel.app)
        thief.cookies.set(coadmin.COOKIE, stolen)
        self.assertEqual(thief.get("/api/admin/profiles").status_code, 401)   # not without the profile's own login
        c.post("/api/admin/elevate/end")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        c.cookies.set(coadmin.COOKIE, stolen)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)        # the old copy is worthless as well
        self.elevate(c)
        c.post("/api/profile/logout")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)

    def test_times(self):
        _, uid = self.give("KoYara")
        now = 1_000_000
        value = coadmin.start(uid, "b", now=now)
        u = next(x for x in profiles._load()["users"] if x["id"] == uid)
        req = FakeRequest({coadmin.COOKIE: value, profiles.COOKIE: profiles._cookie_value(u, issued=time.time())})
        self.assertIsNotNone(coadmin.session(req, now=now + coadmin.IDLE - 1))
        self.assertIsNone(coadmin.session(req, now=now + coadmin.IDLE + 1))
        # used: renewed with the same start, but never past LONGEST
        later = now + coadmin.IDLE - 10
        req.cookies[coadmin.COOKIE] = coadmin._token(uid, now, coadmin._parse(value)["family"], "b", later)
        self.assertIsNotNone(coadmin.session(req, now=later + 5))
        self.assertIsNone(coadmin.session(FakeRequest({coadmin.COOKIE: coadmin._token(
            uid, now, "a" * 16, "b", now + coadmin.LONGEST), profiles.COOKIE: req.cookies[profiles.COOKIE]}), now=now + coadmin.LONGEST + 1))
        self.assertIsNone(coadmin.session(FakeRequest({coadmin.COOKIE: value[:-1] + ("0" if value[-1] != "0" else "1"),
                                                       profiles.COOKIE: req.cookies[profiles.COOKIE]}), now=now + 5))

    def test_iphone_app(self):
        helpers.set_config(iphone=True, iphone_panel=True)
        iphone._pending.clear()
        try:
            c, uid = self.give("KoZoe", with_mfa=False)
            c.put("/api/profile/settings", json={"app_on": True})
            for k in [k for k in guard._rate if k[0] == "pair"]:
                guard._rate.pop(k, None)
            key = pair(c).json()["token"]
            self.mfa_on.add(uid)
            a = TestClient(panel.app)
            a.headers[profiles.DEVICE_HEADER] = key
            self.assertEqual(a.post("/api/admin/elevate", headers=CODE).status_code, 403)   # "Spark verwalten" off
            c.put("/api/profile/settings", json={"app_admin": True})
            self.assertEqual(a.post("/api/admin/elevate").status_code, 428)
            r = a.post("/api/admin/elevate", headers=CODE)
            self.assertEqual(r.status_code, 200, r.text)
            s = TestClient(panel.app)                       # the app's admin session: the cookie only
            s.cookies.set(coadmin.COOKIE, a.cookies.get(coadmin.COOKIE))
            self.assertEqual(s.get("/api/admin/profiles").status_code, 200)
            c.put("/api/profile/settings", json={"app_admin": False})
            self.assertEqual(s.get("/api/admin/profiles").status_code, 401)
            c.put("/api/profile/settings", json={"app_admin": True})
            self.assertEqual(s.get("/api/admin/profiles").status_code, 200)
            did = next(x["id"] for x in profiles.own_devices(uid) if x["app"])
            c.delete(f"/api/profile/devices/{did}")        # the iPhone removed: its admin mode ends
            self.assertEqual(s.get("/api/admin/profiles").status_code, 401)
        finally:
            helpers.set_config(iphone=False, iphone_panel=False)

    def test_protocol_says_who(self):
        c, uid = self.give("KoAnke")
        profile("KoBodo")
        self.elevate(c)
        self.assertEqual(c.put(f"/api/admin/profiles/{uid_of('KoBodo')}/call", json={"call": "Bodo B."}).status_code, 200)
        ADMIN.put(f"/api/admin/profiles/{uid_of('KoBodo')}/call", json={"call": "Bodo C."})
        main = ADMIN.get("/api/admin/protocol").json()
        self.assertTrue(main["all"])
        mine = [x for x in main["events"] if x.get("by") == uid and x.get("path", "").endswith("/call")]
        self.assertTrue(mine, main["events"][:5])
        self.assertTrue(any(x.get("by") == "main" and x.get("path", "").endswith("/call") for x in main["events"]))
        self.assertTrue(any(x.get("event") == "admin_mode_on" and x.get("uid") == uid for x in main["events"]))
        own = c.get("/api/admin/protocol").json()
        self.assertFalse(own["all"])
        self.assertTrue(own["events"])
        self.assertTrue(all(x.get("by") == uid or x.get("uid") == uid for x in own["events"]))


if __name__ == "__main__":
    unittest.main()
