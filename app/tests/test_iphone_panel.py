"""Panel areas in the iPhone app (iphone.AREAS, V01.0.246): the admin switch chat.iphone_panel opens every area
for every profile at once, only the admin blocks single profiles (App-Gleichstand, Dominik 2026-10-14: no switch
per area any more); the app's key reaches only the areas' paths; "Spark verwalten" stays the profile's own
choice, set in the browser only, never from the app; a closed area opens nothing."""
import json
import unittest

from tests import helpers

helpers.start()
import guard  # noqa: E402
import iphone  # noqa: E402
import profiles  # noqa: E402
from tests.test_iphone import pair, profile  # noqa: E402

H = profiles.DEVICE_HEADER


class Areas(unittest.TestCase):
    def setUp(self):
        helpers.set_config(iphone=True, iphone_panel=True)
        iphone._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(iphone=False, iphone_panel=False)

    def app(self, name):
        c = profile(name)
        r = pair(c)
        self.assertEqual(r.status_code, 200, r.text)
        from fastapi.testclient import TestClient
        import panel
        a = TestClient(panel.app)
        a.headers[H] = r.json()["token"]
        return c, a

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["iphone_panel"], False)
        # "Spark verwalten in der App" (app_admin) is gone since V01.0.541: the admin role decides, by the app key
        self.assertNotIn("app_admin", profiles.SETTINGS)
        self.assertIn("app_admin", iphone.GONE)
        # no profile switch per area any more: the admin release decides (Freigabe nur durch Admin)
        for k in iphone.AREAS:
            self.assertNotIn(k, profiles.SETTINGS, k)
            self.assertIn(k, iphone.GONE, k)
        # hello names every area, so older apps keep finding their keys
        self.assertEqual(set(iphone.AREAS) - set(iphone.RIGHTS_PANEL), set())

    def test_areas_follow_the_admin_release(self):
        c, a = self.app("Pia")
        self.assertEqual(a.get("/api/profile/memory").status_code, 200)
        self.assertTrue(a.get("/api/iphone/hello").json()["areas"]["app_mine"])
        self.assertNotIn("app_admin", a.get("/api/iphone/hello").json()["areas"])   # no area, the role decides
        # an old switch from the browser or an old app changes nothing
        c.put("/api/profile/settings", json={"app_mine": False})
        self.assertNotIn("app_mine", profiles.settings(self.uid("Pia")))
        self.assertEqual(a.get("/api/profile/memory").status_code, 200)
        helpers.set_config(deny={"iphonepanel": [self.uid("Pia")]})
        try:
            self.assertEqual(a.get("/api/profile/memory").status_code, 401)
            self.assertFalse(a.get("/api/iphone/hello").json()["areas"]["app_mine"])
        finally:
            helpers.set_config(deny={})
        helpers.set_config(iphone_panel=False)
        self.assertEqual(a.get("/api/profile/memory").status_code, 401)
        self.assertFalse(a.get("/api/iphone/hello").json()["areas"]["app_mine"])
        helpers.set_config(iphone_panel=True)

    def test_only_the_area_paths_and_methods(self):
        c, a = self.app("Quinn")
        uid = next(u["id"] for u in profiles._load()["users"] if u["name"] == "Quinn")
        profiles.remember(uid, "Mag Tee")
        fid = profiles.memory(uid)[0]["id"]
        self.assertEqual(a.delete(f"/api/profile/memory/{fid}").json()["removed"], 1)
        # forgetting everything at once stays in the browser, like the rest of the panel
        self.assertEqual(a.delete("/api/profile/memory").status_code, 401)
        for path in ("/api/profile/settings", "/api/profile/tasks", "/api/admin/profiles", "/api/profile/memory/../settings"):
            self.assertIn(a.get(path).status_code, (401, 403, 404), path)
        self.assertEqual(a.put("/api/profile/settings", json={"app_admin": True}).status_code, 401)

    def test_rights_never_from_the_app(self):
        c, a = self.app("Rosa")
        for k in ("app_on", "app_ha", "app_room"):
            self.assertEqual(a.put("/api/iphone/settings", json={k: True}).status_code, 400, k)
        a.put("/api/iphone/settings", json={"app_admin": True})          # gone: ignored, never stored
        self.assertNotIn("app_admin", profiles.settings(self.uid("Rosa")))
        # with "Mein Alltag" the app changes the conversation switches, only those
        self.assertEqual(a.put("/api/iphone/settings", json={"learn": False}).status_code, 200)
        self.assertIs(a.get("/api/iphone/settings").json()["settings"]["learn"], False)
        helpers.set_config(iphone_panel=False)
        try:
            self.assertEqual(a.put("/api/iphone/settings", json={"learn": True}).status_code, 400)
            self.assertNotIn("learn", a.get("/api/iphone/settings").json()["settings"])
        finally:
            helpers.set_config(iphone_panel=True)

    def test_no_admin_path_without_a_role(self):
        c, a = self.app("Sami")
        c.put("/api/profile/settings", json={"app_admin": True})        # an old switch changes nothing
        self.assertNotIn("app_admin", profiles.settings(self.uid("Sami")))
        self.assertIsNone(a.get("/api/iphone/hello").json().get("admin_role") or None)
        for path in ("/api/admin/profiles", "/api/config", "/api/update"):
            self.assertIn(a.get(path).status_code, (401, 403), path)

    def uid(self, name):
        return next(u["id"] for u in profiles._load()["users"] if u["name"] == name)

    def test_every_area_opens_with_the_release_and_closes_with_it(self):
        c, a = self.app("Uli")
        probe = ("/api/profile/wissen", "/api/profile/voice", "/api/profile/weather", "/api/profile/security",
                 "/api/profile/calendar")
        for path in probe:
            self.assertEqual(a.get(path).status_code, 200, path)
        helpers.set_config(iphone_panel=False)
        try:
            for path in probe:
                self.assertEqual(a.get(path).status_code, 401, path)
        finally:
            helpers.set_config(iphone_panel=True)

    def test_setting_up_the_second_step_stays_in_the_browser(self):
        c, a = self.app("Vera")
        helpers.set_config(mfa=True)
        try:
            self.assertEqual(a.get("/api/profile/mfa").status_code, 200)
            for path in ("/api/profile/mfa/setup", "/api/profile/mfa/enable"):
                self.assertEqual(a.post(path, json={"code": "123456"}).status_code, 401, path)
        finally:
            helpers.set_config(mfa=False)

    def test_secrets_from_the_app_need_the_second_step_and_a_code(self):
        import mfa
        c, a = self.app("Wim")
        helpers.set_config(mail=True, speaker_id=True)
        body = {"kind": "gmail", "user": "wim@example.org", "password": "pw"}
        real = (mfa.enabled, mfa.verify)
        try:
            r = a.post("/api/profile/mail", json=body)
            self.assertEqual(r.status_code, 403, r.text)
            self.assertIn("zweiten Anmeldeschritt", r.json()["detail"])
            self.assertEqual(a.post("/api/profile/voice", files={"file": ("a.wav", b"x")}).status_code, 403)
            mfa.enabled = lambda who: True
            mfa.verify = lambda who, code: False
            self.assertEqual(a.post("/api/profile/mail", json=body).status_code, 428)
            self.assertEqual(a.post("/api/profile/mail", json=body, headers={"X-Speech-Code": "000000"}).status_code, 428)
            self.assertEqual(a.post("/api/profile/voice", files={"file": ("a.wav", b"x")}).status_code, 428)
        finally:
            mfa.enabled, mfa.verify = real
            helpers.set_config(mail=False, speaker_id=False)
            guard._fails.clear()
            guard._locks.clear()
        # the smart home code word stays in the browser
        self.assertEqual(a.put("/api/profile/homeassistant/code", json={"code": "x"}).status_code, 401)
        # a Telegram link is a new way into the profile: the same rule as passwords
        import inspect
        import telegram
        self.assertIn("secret_profile", inspect.signature(telegram.profile_link).parameters["prof"].default.dependency.__name__)

    def test_document_and_service_switches_with_the_release(self):
        c, a = self.app("Xena")
        for k in iphone.MINE_FIELDS + iphone.DOC_FIELDS + iphone.AUTO_FIELDS:
            self.assertEqual(a.put("/api/iphone/settings", json={k: True}).status_code, 200, k)
        # an old app still sending an area switch: ignored, never stored
        self.assertEqual(a.put("/api/iphone/settings", json={"app_docs_edit": False}).status_code, 200)
        self.assertNotIn("app_docs_edit", profiles.settings(self.uid("Xena")))
        helpers.set_config(iphone_panel=False)
        try:
            for k in iphone.MINE_FIELDS + iphone.DOC_FIELDS:
                self.assertEqual(a.put("/api/iphone/settings", json={k: True}).status_code, 400, k)
        finally:
            helpers.set_config(iphone_panel=True)

    def test_feature_switches_from_the_app_only_plain_ones(self):
        """Einstellungen → Funktionen in "Spark verwalten": the admin's login; only chat on/off switches,
        never the sensitive ones nor the ones that close the app out."""
        import admin
        from fastapi.testclient import TestClient
        import panel
        x = TestClient(panel.app)
        self.assertEqual(x.get("/api/admin/switches").status_code, 401)
        self.assertEqual(x.put("/api/admin/switches", json={"key": "weather", "on": True}).status_code, 401)
        x.post("/api/login", json={"password": "secret-admin"})
        keys = set(x.get("/api/admin/switches").json()["switches"])
        self.assertIn("weather", keys)
        for k in ("public", "mfa", "iphone", "iphone_panel"):
            self.assertNotIn(k, keys)
            self.assertEqual(x.put("/api/admin/switches", json={"key": k, "on": False}).status_code, 400, k)
        self.assertEqual(x.put("/api/admin/switches", json={"key": "llm_url", "on": True}).status_code, 400)
        self.assertEqual(x.put("/api/admin/switches", json={"key": "weather", "on": "yes"}).status_code, 400)
        self.assertEqual(set(admin.app_switches()) & {k for sec, k in admin.SENSITIVE if sec == "chat"}, set())
        r = x.put("/api/admin/switches", json={"key": "weather", "on": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIs(x.get("/api/admin/switches").json()["switches"]["weather"], True)
        x.put("/api/admin/switches", json={"key": "weather", "on": False})
        self.assertIs(x.get("/api/config").json()["chat"]["weather"], False)


    def test_the_password_never_from_the_app(self):
        """Since V01.0.541 the panel password is the emergency access, only in a browser; the app is admin by
        the profile's role and its own key (test_coadmin), never by the password."""
        import mfa
        c, a = self.app("Tamo")
        real = (mfa.enabled, mfa.verify)
        try:
            mfa.enabled = lambda who: who == mfa.ADMIN
            mfa.verify = lambda who, code: who == mfa.ADMIN and code == "123456"
            for body in ({"password": "secret-admin"}, {"password": "secret-admin", "code": "123456"}):
                self.assertEqual(a.post("/api/login", json=body).status_code, 403)
            from fastapi.testclient import TestClient
            import panel
            x = TestClient(panel.app)
            x.headers[H] = "not-a-key"
            self.assertEqual(x.post("/api/login", json={"password": "secret-admin", "code": "123456"}).status_code, 403)
            self.assertFalse(a.get("/api/whoami").json()["admin"])
        finally:
            mfa.enabled, mfa.verify = real
            guard._fails.clear()
            guard._locks.clear()


if __name__ == "__main__":
    unittest.main()
