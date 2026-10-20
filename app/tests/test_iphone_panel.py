"""Panel areas in the iPhone app (iphone.AREAS, V01.0.246): the admin switch chat.iphone_panel opens every area
for every profile at once, only the admin blocks single profiles (App-Gleichstand, Dominik 2026-10-14: no switch
per area any more); the app's key reaches only the areas' paths; "Spark verwalten" stays the profile's own
choice, set in the browser only, never from the app; a closed area opens nothing. The parts of Meine Sachen
(iphone.THINGS, Dominik 2026-10-17) open with the admin release of their own function instead."""
import json
import os
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
        cal = ("/api/profile/calendar/test", {"tz": "Europe/Berlin"})
        self.assertNotEqual(a.post(cal[0], json=cal[1]).status_code, 401)
        self.assertTrue(a.get("/api/iphone/hello").json()["areas"]["app_mine"])
        self.assertNotIn("app_admin", a.get("/api/iphone/hello").json()["areas"])   # no area, the role decides
        # an old switch from the browser or an old app changes nothing
        c.put("/api/profile/settings", json={"app_mine": False})
        self.assertNotIn("app_mine", profiles.settings(self.uid("Pia")))
        self.assertNotEqual(a.post(cal[0], json=cal[1]).status_code, 401)
        helpers.set_config(deny={"iphonepanel": [self.uid("Pia")]})
        try:
            self.assertEqual(a.post(cal[0], json=cal[1]).status_code, 401)
            self.assertFalse(a.get("/api/iphone/hello").json()["areas"]["app_mine"])
        finally:
            helpers.set_config(deny={})
        helpers.set_config(iphone_panel=False)
        self.assertEqual(a.post(cal[0], json=cal[1]).status_code, 401)
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
        # the lists themselves are Meine Sachen → Listen (iphone.THINGS), the search for CalDAV lists stays in the browser
        for path in ("/api/profile/settings", "/api/profile/tasks/collections", "/api/admin/profiles", "/api/profile/memory/../settings"):
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
        probe = ("/api/profile/voice", "/api/profile/weather", "/api/profile/security", "/api/profile/calendar")
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
            for k in iphone.MINE_FIELDS:
                self.assertEqual(a.put("/api/iphone/settings", json={k: True}).status_code, 400, k)
            for k in iphone.DOC_FIELDS:      # Meine Sachen → Dokumente: with Eigene Dokumente, not the panel switch
                self.assertEqual(a.put("/api/iphone/settings", json={k: True}).status_code, 200, k)
        finally:
            helpers.set_config(iphone_panel=True)
        helpers.set_config(deny={"documents": [self.uid("Xena")]})
        try:
            for k in iphone.DOC_FIELDS:
                self.assertEqual(a.put("/api/iphone/settings", json={k: True}).status_code, 400, k)
        finally:
            helpers.set_config(deny={})

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


class Things(unittest.TestCase):
    """Meine Sachen (Dominik 2026-10-17, plan app-meine-sachen/plan.md): documents, memory, pictures and music open
    for the app's key with the admin release of their own function, not with the panel switch; the admin's block for
    the profile closes them at once; forgetting everything at once stays in the browser."""
    # (method, path, the answer that shows the request got through to the endpoint): ordering and sending have no
    # plain GET, an empty request reaches their own checks (400) only with the release
    PROBE = {"documents": ("GET", "/api/profile/wissen", 200), "memory": ("GET", "/api/profile/memory", 200),
             "bilder": ("GET", "/api/bilder", 200), "musik": ("GET", "/api/musik", 200),
             "wissensbuch": ("GET", "/api/profile/wissensbuch", 200),
             "calendar": ("GET", "/api/profile/calendar/view", 200), "mail": ("GET", "/api/profile/mail/inbox", 200),
             "mailmanage": ("GET", "/api/profile/mail/folders", 400), "mailsend": ("POST", "/api/profile/mail/send/preview", 400),
             "calserver": ("GET", "/api/profile/calserver", 200), "fuerdich": ("GET", "/api/profile/fuerdich", 200),
             "ichweiss": ("GET", "/api/profile/ichweiss", 200), "tasks": ("GET", "/api/profile/tasks", 200),
             "vorgaenge": ("GET", "/api/profile/vorgaenge", 200)}

    app, uid = Areas.app, Areas.uid

    @staticmethod
    def section(name, **kw):
        """Switches a part of the config ("image", "music") and gives back how it was."""
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        old = dict(c.get(name) or {})
        c.setdefault(name, {}).update(kw)
        helpers.write_config(c)
        return old

    def setUp(self):
        helpers.keep_chat(self, "iphone", "iphone_panel", "bilder", "musik", "deny", "documents", "knowledge_book",
                          "calendar", "mail", "mail_manage", "mail_send", "calendar_server", "mail_insight", "tasks", "reminders", "vorgaenge")
        helpers.set_config(iphone=True, iphone_panel=False, bilder=True, musik=True, deny={}, documents=True,
                           knowledge_book=True, calendar=True, mail=True, mail_manage=True, mail_send=True,
                           calendar_server=True, mail_insight=True, tasks=True, reminders=True, vorgaenge=True)
        for name in ("image", "music"):     # the picture and music models count as installed
            old = self.section(name, enabled=True)
            self.addCleanup(lambda n=name, o=old: self.section(n, **dict({"enabled": False}, **o)))
        iphone._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:
            guard._rate.pop(k, None)

    def test_every_part_has_its_function_and_a_probe(self):
        import features
        self.assertEqual(set(iphone.THINGS), set(self.PROBE))
        for k in iphone.THINGS:
            self.assertIn(k, features.BY_KEY, k)           # the key is the function's own key in features.py
            self.assertNotIn(k, profiles.SETTINGS, k)       # never a profile switch
        self.assertEqual(set(iphone.THINGS) & set(iphone.AREAS), set())

    @staticmethod
    def ancestors(features, key):
        out, k = [], features.BY_KEY[key].parent
        while k:
            out.append(k)
            k = features.BY_KEY[k].parent if k in features.BY_KEY else ""
        return out

    def test_each_part_opens_with_its_own_release_only(self):
        import features
        c, a = self.app("Thea")
        hello = a.get("/api/iphone/hello").json()["areas"]
        for k, (method, path, ok) in self.PROBE.items():
            self.assertTrue(hello[k], k)
            self.assertEqual(a.request(method, path, **self.body(method)).status_code, ok, k)   # without the panel switch
        for k, (method, path, ok) in self.PROBE.items():
            helpers.set_config(deny={k: [self.uid("Thea")]})
            try:
                self.assertFalse(a.get("/api/iphone/hello").json()["areas"][k], k)
                self.assertEqual(a.request(method, path, **self.body(method)).status_code, 401, k)
                for other, (m2, p2, ok2) in self.PROBE.items():   # the others stay open (the Wissensbuch hangs on Dokumente,
                    if other != k and k not in self.ancestors(features, other):   # Was ich über dich weiß on Für dich on Mail)
                        self.assertEqual(a.request(m2, p2, **self.body(m2)).status_code, ok2, (k, other))
            finally:
                helpers.set_config(deny={})
        helpers.set_config(bilder=False)
        self.assertEqual(a.get("/api/bilder").status_code, 401)
        self.assertFalse(a.get("/api/iphone/hello").json()["areas"]["bilder"])

    def test_delete_mail_shows_only_with_its_own_switch(self):
        """Mails löschen in the app (iphone.FLAGS): hello names it only with its own admin switch (off); the
        paths stay those of Mails ordnen, where the Spark checks the switch again (postfach._may_delete)."""
        helpers.keep_chat(self, "mail_delete")
        c, a = self.app("Delia")
        self.assertFalse(a.get("/api/iphone/hello").json()["areas"]["maildelete"])
        helpers.set_config(mail_delete=True)
        self.assertTrue(a.get("/api/iphone/hello").json()["areas"]["maildelete"])
        r = a.post("/api/profile/mail/act", json={"id": "x", "action": "delete"})
        self.assertNotEqual(r.status_code, 401)   # reaches the mail checks (no such mail), not refused by the key
        helpers.set_config(deny={"maildelete": [self.uid("Delia")]})
        try:
            self.assertFalse(a.get("/api/iphone/hello").json()["areas"]["maildelete"])
        finally:
            helpers.set_config(deny={})

    def test_quick_add_from_the_app(self):
        """Schnell eintragen and „Als Termin“ in the app (V01.0.82x catch-up, Dominik 2026-10-19 „a“): the Spark reads
        the line with its fixed rules for the app's key too, only with the calendar's release; nothing is saved."""
        c, a = self.app("Quentin")
        r = a.get("/api/profile/calendar/quick", params={"text": "Morgen 15 Uhr Zahnarzt", "tz": "Europe/Berlin"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["title"], "Zahnarzt")
        self.assertFalse(r.json()["allday"])
        helpers.set_config(deny={"calendar": [self.uid("Quentin")]})
        try:
            self.assertEqual(a.get("/api/profile/calendar/quick", params={"text": "Morgen Zahnarzt"}).status_code, 401)
        finally:
            helpers.set_config(deny={})

    @staticmethod
    def body(method):
        return {"json": {}} if method == "POST" else {}

    def test_memory_from_the_app(self):
        c, a = self.app("Theo")
        uid = self.uid("Theo")
        for t in ("Mag Tee", "Wohnt in Kiel", "Hat einen Hund"):
            profiles.remember(uid, t)
        ids = {f["text"]: f["id"] for f in profiles.memory(uid)}
        r = a.put(f"/api/profile/memory/{ids['Mag Tee']}", json={"text": "Mag grünen Tee"})
        self.assertEqual(r.status_code, 200, r.text)
        r = a.post("/api/profile/memory/forget", json={"ids": [ids["Wohnt in Kiel"]]})
        self.assertEqual((r.status_code, r.json()["removed"]), (200, 1), r.text)
        self.assertEqual({f["text"] for f in profiles.memory(uid)}, {"Mag grünen Tee", "Hat einen Hund"})
        # forgetting everything at once stays in the browser, and other profiles' facts are never reached
        self.assertEqual(a.delete("/api/profile/memory").status_code, 401)
        d, b = self.app("Thilo")
        self.assertEqual(b.delete(f"/api/profile/memory/{ids['Hat einen Hund']}").json()["removed"], 0)
        self.assertIn("Hat einen Hund", {f["text"] for f in profiles.memory(uid)})

    def test_left_out_folders_from_the_app(self):
        """Ordner auslassen, Stufe C: the app shows the list, adds and removes name rules and lets folders in again
        with the release of Eigene Dokumente; the folder tree stays in the browser."""
        import auslassen
        c, a = self.app("Theodor")
        uid = self.uid("Theodor")
        self.assertEqual(a.get("/api/profile/auslassen").status_code, 200)
        r = a.post("/api/profile/auslassen", json={"name": "Archiv", "probe": True})
        self.assertEqual((r.status_code, r.json()["docs"]), (200, 0), r.text)
        self.assertEqual(a.post("/api/profile/auslassen", json={"name": "Archiv"}).status_code, 200)
        self.assertEqual(auslassen.load(uid)["names"], ["Archiv"])
        self.assertEqual(a.delete("/api/profile/auslassen", params={"name": "Archiv"}).status_code, 200)
        self.assertEqual(auslassen.load(uid)["names"], [])
        self.assertEqual(a.get("/api/profile/auslassen/tree?ort=pc").status_code, 401)
        helpers.set_config(deny={"documents": [uid]})
        try:
            self.assertEqual(a.get("/api/profile/auslassen").status_code, 401)
        finally:
            helpers.set_config(deny={})

    def test_knowledge_book_from_the_app(self):
        """Wissensbuch Stufe E: the app reads the book, settles sentences and files a kept answer; writing a page
        again and deleting one stay in the browser."""
        c, a = self.app("Tara")
        self.assertEqual(a.get("/api/profile/wissensbuch").status_code, 200)
        self.assertEqual(a.post("/api/profile/wissensbuch/satz/99999/stimmt").status_code, 404)   # through, no such sentence
        self.assertEqual(a.post("/api/profile/wissensbuch/satz/99999/noch").status_code, 404)
        self.assertEqual(a.delete("/api/profile/wissensbuch/satz/99999").status_code, 404)
        self.assertEqual(a.post("/api/profile/wissensbuch/ablegen", json={"id": "0" * 16}).status_code, 404)
        self.assertEqual(a.get("/api/profile/wissensbuch/export").status_code, 200)
        self.assertEqual(a.delete("/api/profile/wissensbuch/" + "a" * 12).status_code, 401)
        self.assertEqual(a.post("/api/profile/wissensbuch/" + "a" * 12 + "/neu").status_code, 401)


if __name__ == "__main__":
    unittest.main()
