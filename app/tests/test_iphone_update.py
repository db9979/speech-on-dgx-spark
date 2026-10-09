"""Spark updates from the iPhone app (appupdate.py): rights only from the admin, starting only with the
app's key and a fresh code, the update gate stays, the notice comes once per version."""
import asyncio
import json
import os
import unittest

from tests import helpers

helpers.start()
import apns  # noqa: E402
import appupdate  # noqa: E402
import guard  # noqa: E402
import iphone  # noqa: E402
import mfa  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import update  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import ADMIN, pair, profile, uid_of  # noqa: E402

NEWER = {"latest": "a" * 40, "behind": 3, "version": "V09.9.999", "error": None,
         "commits": [{"sha": "aaaaaaa", "title": "Eins"}, {"sha": "bbbbbbb", "title": "Zwei"}, {"sha": "ccccccc", "title": "Drei"}]}


class AppUpdate(unittest.TestCase):
    def setUp(self):
        helpers.set_config(iphone=True, iphone_update=True)
        iphone._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:
            guard._rate.pop(k, None)
        try:
            os.remove(appupdate._file())
        except OSError:
            pass
        self.real = (mfa.enabled, mfa.verify, update.remote_state, update.update_running, update._start,
                     update._backup_first, apns.on_for, apns.send)
        self.with_mfa, self.codes, self.started, self.sent = set(), set(), [], []
        self.remote, self.running = dict(NEWER), False
        mfa.enabled = lambda who: who in self.with_mfa
        mfa.verify = lambda who, code: (who, code) in self.codes and not self.codes.discard((who, code))

        async def remote(force=False):
            return dict(self.remote)
        update.remote_state = remote
        update.update_running = lambda: self.running
        update._start = lambda: self.started.append(1) or {"started": True}
        update._backup_first = lambda why: None
        apns.on_for = lambda uid: True

        async def send(uid, title, body, tag="", now=None):
            self.sent.append((uid, title, body, tag))
            return 1
        apns.send = send

    def tearDown(self):
        (mfa.enabled, mfa.verify, update.remote_state, update.update_running, update._start,
         update._backup_first, apns.on_for, apns.send) = self.real
        helpers.set_config(iphone=False, iphone_update=False)

    def app_of(self, name):
        a = profile(name)
        a.put("/api/profile/settings", json={"app_on": True})
        return a, {"X-Speech-Device": pair(a).json()["token"]}, uid_of(name)

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["iphone_update"], False)
        a, h, uid = self.app_of("Uwe")
        app = TestClient(panel.app)
        self.assertEqual(app.get("/api/iphone/hello", headers=h).json()["update"], {"notify": False, "start": False})
        self.assertEqual(app.get("/api/iphone/update", headers=h).status_code, 403)
        self.assertEqual(app.post("/api/iphone/update", headers=dict(h, **{"X-Speech-Code": "123456"})).status_code, 403)
        self.assertEqual(self.started, [])

    def test_only_the_admin_gives_rights_and_start_needs_mfa(self):
        a, h, uid = self.app_of("Ute")
        # the profile cannot give itself the right, neither in the browser nor from the app
        self.assertEqual(a.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": True}).status_code, 401)
        self.assertEqual(TestClient(panel.app).put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": True},
                                                   headers=h).status_code, 401)
        self.assertNotIn("iphone_update", profiles.SETTINGS)
        # starting needs the profile's second login step
        r = ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": True})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": "ja", "start": False}).status_code, 400)
        self.assertEqual(ADMIN.put("/api/admin/iphone-update/nobody", json={"notify": True, "start": False}).status_code, 404)
        self.with_mfa.add(uid)
        self.assertEqual(ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": True}).json(),
                         {"notify": True, "start": True})
        self.assertEqual(TestClient(panel.app).get("/api/iphone/hello", headers=h).json()["update"], {"notify": True, "start": True})
        # second step switched off later: the start right is gone with it
        self.with_mfa.discard(uid)
        self.assertEqual(TestClient(panel.app).get("/api/iphone/hello", headers=h).json()["update"]["start"], False)
        listed = {p["id"]: p for p in ADMIN.get("/api/admin/iphone-update").json()["profiles"]}
        self.assertTrue(listed[uid]["notify"])

    def test_state_only_for_the_app_key(self):
        a, h, uid = self.app_of("Ulla")
        ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": False})
        self.assertEqual(a.get("/api/iphone/update").status_code, 403)       # the browser login
        d = TestClient(panel.app).get("/api/iphone/update", headers=h).json()
        self.assertEqual((d["latest"], d["behind"], d["newer"], d["start"]), ("V09.9.999", 3, True, False))
        self.assertEqual(d["changes"], ["Drei", "Zwei", "Eins"])
        self.remote = dict(NEWER, behind=0)
        d = TestClient(panel.app).get("/api/iphone/update", headers=h).json()
        self.assertEqual((d["latest"], d["newer"], d["changes"]), (None, False, []))
        # a key of another kind (own program, speaker) never
        tok = ADMIN.post("/api/admin/devices", json={"name": "Skript", "user": uid}).json()["token"]
        self.assertEqual(TestClient(panel.app).get("/api/iphone/update", headers={"X-Speech-Device": tok}).status_code, 403)

    def test_start_needs_right_fresh_code_and_a_newer_tested_version(self):
        a, h, uid = self.app_of("Udo")
        self.with_mfa.add(uid)
        app = TestClient(panel.app)
        code = lambda c: dict(h, **{"X-Speech-Code": c})   # noqa: E731
        # only notices: no start
        ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": False})
        self.codes.add((uid, "111111"))
        self.assertEqual(app.post("/api/iphone/update", headers=code("111111")).status_code, 403)
        ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": True})
        # no code, not six digits (no recovery codes here), wrong code
        self.assertEqual(app.post("/api/iphone/update", headers=h).status_code, 428)
        self.assertEqual(app.post("/api/iphone/update", headers=code("abcd-efgh")).status_code, 428)
        self.assertEqual(app.post("/api/iphone/update", headers=code("222222")).status_code, 428)
        # the browser login of the same profile cannot start it
        self.assertEqual(a.post("/api/iphone/update", headers={"X-Speech-Code": "111111"}).status_code, 403)
        # nothing newer and tested: refused, the code is spent anyway
        self.remote = dict(NEWER, behind=0)
        self.assertEqual(app.post("/api/iphone/update", headers=code("111111")).status_code, 409)
        self.remote = dict(NEWER, latest=None, error="GitHub-Testergebnisse nicht abrufbar")
        self.codes.add((uid, "333333"))
        self.assertEqual(app.post("/api/iphone/update", headers=code("333333")).status_code, 409)
        self.assertEqual(self.started, [])
        # the same code a second time does not work
        self.remote = dict(NEWER)
        self.assertEqual(app.post("/api/iphone/update", headers=code("333333")).status_code, 428)
        # running already
        self.running = True
        self.codes.add((uid, "444444"))
        self.assertEqual(app.post("/api/iphone/update", headers=code("444444")).status_code, 409)
        self.running = False
        self.codes.add((uid, "555555"))
        r = app.post("/api/iphone/update", headers=code("555555"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["version"], "V09.9.999")
        self.assertEqual(self.started, [1])
        self.assertTrue(any(e["event"] == "update_from_app" and e.get("uid") == uid for e in guard.read(50)))
        # one start per gap
        self.codes.add((uid, "666666"))
        self.assertEqual(app.post("/api/iphone/update", headers=code("666666")).status_code, 429)
        self.assertEqual(self.started, [1])
        # admin switch off: nothing
        helpers.set_config(iphone_update=False)
        self.assertEqual(app.get("/api/iphone/update", headers=h).status_code, 403)

    def test_others_with_notices_hear_who_started(self):
        a, h, uid = self.app_of("Uta")
        b, hb, other = self.app_of("Ulf")
        self.with_mfa.add(uid)
        ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": True})
        ADMIN.put(f"/api/admin/iphone-update/{other}", json={"notify": True, "start": False})
        self.codes.add((uid, "777777"))
        self.assertEqual(TestClient(panel.app).post("/api/iphone/update", headers=dict(h, **{"X-Speech-Code": "777777"})).status_code, 200)
        self.assertEqual([(s[0], s[3]) for s in self.sent], [(other, "update")])
        self.assertIn("Uta", self.sent[0][2])

    def test_notice_once_per_version_and_not_in_quiet_time(self):
        a, h, uid = self.app_of("Uli")
        b, hb, other = self.app_of("Urs")
        ADMIN.put(f"/api/admin/iphone-update/{uid}", json={"notify": True, "start": False})
        profiles.save_settings(other, {"pro_quiet": "00:00-23:59"})
        ADMIN.put(f"/api/admin/iphone-update/{other}", json={"notify": True, "start": False})
        appupdate._checked[0] = 0
        quiet = appupdate._quiet
        appupdate._quiet = lambda u, now: u == other
        try:
            self.assertEqual(asyncio.run(appupdate.due_once(now=10_000)), 1)
            self.assertEqual([s[0] for s in self.sent], [uid])
            self.assertIn("V09.9.999", self.sent[0][2])
            # within the check interval: nothing; later, same version: nothing again
            self.assertEqual(asyncio.run(appupdate.due_once(now=10_100)), 0)
            self.assertEqual(asyncio.run(appupdate.due_once(now=20_000)), 0)
            # a newer version: told again
            self.remote = dict(NEWER, version="V09.9.1000", latest="b" * 40)
            self.assertEqual(asyncio.run(appupdate.due_once(now=30_000)), 1)
            # admin switch off: no notices
            helpers.set_config(iphone_update=False)
            self.remote = dict(NEWER, version="V09.9.1001", latest="c" * 40)
            self.assertEqual(asyncio.run(appupdate.due_once(now=40_000)), 0)
        finally:
            appupdate._quiet = quiet
        self.assertNotIn(other, [s[0] for s in self.sent])

    def test_language_model_has_no_update_tool(self):
        import chat
        with open(chat.__file__) as f:
            src = f.read()
        self.assertNotIn("appupdate", src)
        self.assertNotIn("/api/iphone/update", src)


if __name__ == "__main__":
    unittest.main()
