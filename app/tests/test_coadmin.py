"""Profiles as admins (coadmin.py; since V01.0.541 without the admin mode, plan plaene/admin-ohne-zweite-stufe.md):
a role only with the profile's second step, then admin at once in its own login made with that step, never with
the PIN alone; "Bestätigen" never asks admins, "Schutz ändern" always; the password's own things stay with it; the
main admin profile and the last admin role are protected; a Verwalter reaches only his list; taking the role away
or the second step off ends it at once; the iPhone app is admin by its key; every admin action says who."""
import json
import os
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


class CoAdmin(unittest.TestCase):
    def setUp(self):
        self.real = (mfa.enabled, mfa.verify, mfa.mark)
        self.mfa_on = {mfa.ADMIN}
        self.gen = {}                      # a new setup of the second step gives a new mark
        mfa.enabled = lambda who: who in self.mfa_on
        mfa.verify = lambda who, code: who in self.mfa_on and code == "123456"
        mfa.mark = lambda who: f"m{self.gen.get(who, 0)}-{who}" if who in self.mfa_on else ""
        guard.reset()

    def tearDown(self):
        mfa.enabled, mfa.verify, mfa.mark = self.real
        try:
            os.remove(coadmin.FILE)
        except OSError:
            pass
        guard.reset()

    def signin(self, name, code=True, pin="1234"):
        c = TestClient(panel.app)
        r = c.post("/api/profile/login", json={"name": name, "pin": pin, **({"code": "123456"} if code else {})})
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def give(self, name, role="admin"):
        profile(name)
        uid = uid_of(name)
        self.mfa_on.add(uid)
        coadmin.set_role(uid, role)
        return self.signin(name), uid

    def test_off_by_default(self):
        self.assertEqual(coadmin.listing()["users"], [])
        c = profile("KoOlaf")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        self.assertIsNone(c.get("/api/whoami").json()["admin_role"])
        self.assertIn("admins.json", __import__("backup").STATE_FILES)
        # the admin mode is gone, there is nothing to open
        self.assertIn(c.post("/api/admin/elevate", headers=CODE).status_code, (404, 405))

    def test_role_only_with_the_second_step(self):
        profile("KoPaul")
        uid = uid_of("KoPaul")
        with self.assertRaises(ValueError):
            coadmin.set_role(uid, "admin")
        self.assertEqual(ADMIN.put(f"/api/admin/roles/{uid}", json={"role": "admin"}, headers=CODE).status_code, 409)
        with self.assertRaises(ValueError):
            coadmin.set_role(uid, "root")
        self.mfa_on.add(uid)
        self.assertEqual(ADMIN.put(f"/api/admin/roles/{uid}", json={"role": "admin"}).status_code, 428)   # Schutz ändern
        self.assertEqual(ADMIN.put(f"/api/admin/roles/{uid}", json={"role": "admin"}, headers=CODE).status_code, 200)
        self.assertEqual(coadmin.role(uid), "admin")

    def test_admin_at_once_after_signing_in_with_the_code(self):
        c, uid = self.give("KoQuirin")
        w = c.get("/api/whoami").json()
        self.assertTrue(w["admin"])
        self.assertEqual(w["admin_by"], "admin")
        self.assertTrue(w["admin_role"]["acts"])
        self.assertTrue(w["confirm_free"])
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        self.assertEqual(c.get("/api/audit").status_code, 200)
        self.assertEqual(c.get("/api/admin/roles").status_code, 200)
        self.assertIn(c.get("/api/backups/nichtda.tar.gz").status_code, (400, 404))   # reaches it, no 403

    def test_pin_alone_is_never_admin(self):
        profile("KoRita")
        uid = uid_of("KoRita")
        pin_only = TestClient(panel.app)
        pin_only.post("/api/profile/login", json={"name": "KoRita", "pin": "1234"})   # before the second step was on
        self.mfa_on.add(uid)
        coadmin.set_role(uid, "admin")
        self.assertEqual(pin_only.get("/api/admin/profiles").status_code, 401)
        w = pin_only.get("/api/whoami").json()
        self.assertFalse(w["admin"])
        self.assertFalse(w["admin_role"]["acts"])                # Ich → Sicherheit says why it rests
        c = self.signin("KoRita")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        self.gen[uid] = 1                                         # the second step set up again: old logins no more
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        self.assertEqual(self.signin("KoRita").get("/api/admin/profiles").status_code, 200)

    def test_guests_never(self):
        g = TestClient(panel.app)
        self.assertEqual(g.get("/api/admin/profiles").status_code, 401)
        self.assertIsNone(coadmin.session(type("R", (), {"cookies": {}, "headers": {}, "scope": {}})()))

    def test_the_passwords_own_things_stay_with_it(self):
        c, uid = self.give("KoSven")
        for method, path in (("POST", "/api/password"), ("GET", "/api/mfa"), ("POST", "/api/mfa/disable"),
                             ("POST", "/api/logout-everywhere")):
            self.assertEqual(c.request(method, path, json={}, headers=CODE).status_code, 403, (method, path))
        # the panel password is the emergency access: never from the app
        self.assertEqual(TestClient(panel.app).post("/api/login", json={"password": "secret-admin"},
                                                    headers={profiles.DEVICE_HEADER: "x" * 40}).status_code, 403)

    def test_confirm_never_asks_admins_protect_always(self):
        c, uid = self.give("KoTara")
        profile("KoUdo")
        normal = uid_of("KoUdo")
        self.assertEqual(c.put(f"/api/admin/profiles/{normal}", json={"pin": "9998"}).status_code, 200)   # Bestätigen
        self.assertEqual(ADMIN.put(f"/api/admin/profiles/{normal}", json={"pin": "9997"}).status_code, 200)
        self.assertEqual(c.put(f"/api/admin/roles/{normal}", json={"role": "manager"}).status_code, 428)   # Schutz ändern
        # a profile without a role is still asked at "Bestätigen"
        profile("KoUlla")
        self.mfa_on.add(uid_of("KoUlla"))
        p = self.signin("KoUlla")
        self.assertFalse(p.get("/api/whoami").json()["confirm_free"])

    def test_main_admin_and_last_role_are_protected(self):
        a, ua = self.give("KoVera")              # the first admin the password gives is the main one
        self.assertEqual(coadmin.main_uid(), ua)
        b, ub = self.give("KoVeit")
        profile("KoVeitsKind")
        normal = uid_of("KoVeitsKind")
        # another admin never changes the main admin's profile or role, nor itself here
        self.assertEqual(b.put(f"/api/admin/profiles/{ua}", json={"pin": "5555"}).status_code, 403)
        self.assertEqual(b.put(f"/api/admin/profiles/{ub}", json={"pin": "5555"}).status_code, 403)
        self.assertEqual(b.put(f"/api/admin/roles/{ua}", json={"role": ""}, headers=CODE).status_code, 403)
        self.assertEqual(b.put("/api/admin/roles", json={"main": ub}, headers=CODE).status_code, 403)
        # the main admin changes the other admin profile (a new PIN signs it out) and may hand "main" on
        self.assertEqual(b.put(f"/api/admin/profiles/{normal}", json={"pin": "5556"}).status_code, 200)
        self.assertEqual(a.put(f"/api/admin/profiles/{ub}", json={"pin": "5555"}).status_code, 200)
        b = self.signin("KoVeit", pin="5555")
        self.assertEqual(a.put("/api/admin/roles", json={"main": ub}, headers=CODE).status_code, 200)
        self.assertEqual(coadmin.main_uid(), ub)
        # the last admin role: never taken by a profile, only by the password
        self.assertEqual(b.put(f"/api/admin/roles/{ua}", json={"role": ""}, headers=CODE).status_code, 200)
        self.assertEqual(b.put(f"/api/admin/roles/{ub}", json={"role": "manager"}, headers=CODE).status_code, 409)
        self.assertEqual(ADMIN.put(f"/api/admin/roles/{ub}", json={"role": ""}, headers=CODE).status_code, 200)
        self.assertEqual(coadmin.main_uid(), "")

    def test_manager_reaches_only_his_list(self):
        c, uid = self.give("KoWim", role="manager")
        self.assertEqual(c.get("/api/whoami").json()["admin_by"], "manager")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        self.assertEqual(c.get("/api/admin/switches").status_code, 200)
        self.assertEqual(c.get("/api/admin/protocol").status_code, 200)
        for method, path in (("GET", "/api/config"), ("PUT", "/api/config"), ("POST", "/api/update"),
                             ("POST", "/api/service/tts/restart"), ("GET", "/api/backups"), ("POST", "/api/backups"),
                             ("GET", "/api/clone-voices"), ("GET", "/api/admin/telegram"), ("GET", "/api/admin/roles"),
                             ("GET", "/api/audit")):
            self.assertEqual(c.request(method, path, json={}).status_code, 403, (method, path))
        _, other = self.give("KoXaver")
        self.assertEqual(c.put(f"/api/admin/profiles/{other}", json={"pin": "5555"}).status_code, 403)
        profile("KoXaversKind")
        d = c.get(f"/api/admin/profiles/{uid_of('KoXaversKind')}").json()
        self.assertNotIn("rights", d)

    def test_ends_at_once(self):
        c, uid = self.give("KoYara")
        _, keep = self.give("KoYves")           # so KoYara is not the last admin
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        coadmin.set_role(uid, "manager")
        self.assertEqual(c.get("/api/config").status_code, 403)          # a Verwalter now
        coadmin.set_role(uid, "admin")
        self.mfa_on.discard(uid)                # the second step off: the rights rest
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        self.mfa_on.add(uid)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 200)
        ADMIN.put(f"/api/admin/roles/{uid}", json={"role": ""}, headers=CODE)
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)
        coadmin.set_role(uid, "admin")
        c.post("/api/profile/logout")
        self.assertEqual(c.get("/api/admin/profiles").status_code, 401)

    def test_iphone_app_is_admin_by_its_key(self):
        helpers.set_config(iphone=True)
        iphone._pending.clear()
        try:
            c, uid = self.give("KoZoe")
            for k in [k for k in guard._rate if k[0] == "pair"]:
                guard._rate.pop(k, None)
            key = pair(c).json()["token"]
            a = TestClient(panel.app)
            a.headers[profiles.DEVICE_HEADER] = key
            self.assertEqual(a.get("/api/admin/profiles").status_code, 200)
            self.assertEqual(a.get("/api/iphone/hello").json().get("admin_role"), "admin")
            self.mfa_on.discard(uid)
            self.assertEqual(a.get("/api/admin/profiles").status_code, 401)
            self.mfa_on.add(uid)
            helpers.set_config(iphone=False)          # the app switched off by the admin
            self.assertEqual(a.get("/api/admin/profiles").status_code, 401)
            helpers.set_config(iphone=True)
            did = next(x["id"] for x in profiles.own_devices(uid) if x["app"])
            c.delete(f"/api/profile/devices/{did}")  # the iPhone removed
            self.assertEqual(a.get("/api/admin/profiles").status_code, 401)
            # other device keys never act as admin
            tok = ADMIN.post("/api/admin/devices", json={"name": "KoBox", "user": uid}, headers=CODE).json()["token"]
            did = next(x["id"] for x in profiles._load()["devices"] if x.get("name") == "KoBox")
            self.addCleanup(ADMIN.delete, f"/api/admin/devices/{did}", headers=CODE)
            self.assertEqual(TestClient(panel.app).get("/api/admin/profiles", headers={profiles.DEVICE_HEADER: tok}).status_code, 401)
        finally:
            helpers.set_config(iphone=False)

    def test_admin_log_shows_the_newest(self):
        """The protocol comes newest first; the page keeps the first lines, so a fresh sign-in is never cut off."""
        c, uid = self.give("KoNele")
        ev = ADMIN.get("/api/admin/protocol").json()["events"]
        self.assertEqual([x["t"] for x in ev], sorted((x["t"] for x in ev), reverse=True))
        self.assertTrue(any(x.get("event") == "admin_profile_login" and x.get("uid") == uid for x in ev[:5]))
        js = open(os.path.join(helpers.APP, "panel", "static", "js", "logs.js")).read()
        self.assertIn("(await adminRows()).slice(0,LG.lines)", js)
        self.assertIn("(await auditRows()).slice(0,LG.lines)", js)

    def test_protocol_says_who(self):
        c, uid = self.give("KoAnke")
        profile("KoBodo")
        self.assertEqual(c.put(f"/api/admin/profiles/{uid_of('KoBodo')}/call", json={"call": "Bodo B."}).status_code, 200)
        ADMIN.put(f"/api/admin/profiles/{uid_of('KoBodo')}/call", json={"call": "Bodo C."})
        main = ADMIN.get("/api/admin/protocol").json()
        self.assertTrue(main["all"])
        self.assertTrue([x for x in main["events"] if x.get("by") == uid and x.get("path", "").endswith("/call")])
        self.assertTrue(any(x.get("by") == "main" and x.get("path", "").endswith("/call") for x in main["events"]))
        self.assertTrue(any(x.get("event") == "admin_profile_login" and x.get("uid") == uid for x in main["events"]))
        self.assertTrue(c.get("/api/admin/protocol").json()["events"])

    def test_old_file_is_read_as_before(self):
        profile("KoCarl")
        profile("KoDora")
        profile("KoEmil")
        ids = [uid_of(n) for n in ("KoCarl", "KoDora", "KoEmil")]
        old = {"on": True, "notify": ids[2], "users": {ids[0]: {"role": "owner"}, ids[1]: {"role": "coadmin"},
                                                        ids[2]: {"role": "manager"}}}
        with open(coadmin.FILE, "w") as f:
            json.dump(old, f)
        self.assertEqual([coadmin.role(u) for u in ids], ["admin", "admin", "manager"])
        self.assertEqual(coadmin.main_uid(), ids[0])              # the old Haupt-Admin keeps the password's code
        with open(coadmin.FILE, "w") as f:
            json.dump(dict(old, on=False), f)                     # the switch was off: no role counted, none counts
        self.assertEqual([coadmin.role(u) for u in ids], ["", "", ""])
        self.assertEqual(coadmin.main_uid(), "")


if __name__ == "__main__":
    unittest.main()
