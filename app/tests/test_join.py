"""New people by invitation and "Los geht's" (join.py, onboard.py, V01.0.269): off unless the admin
switches it on, one-time codes kept only as hashes, lockout for wrong codes, packs switch on only what the
Spark has on and never a role, the second step before mail, documents and jobs, the setup list checked by
the panel, and "Am Handy weitermachen" only after the matching number on the computer."""
import json
import time
import unittest

from tests import helpers

helpers.start()
import agent  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import join  # noqa: E402
import mfa  # noqa: E402
import onboard  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import wissen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BASE = "https://spark.example"


def reset_guard():
    with guard._lock:
        guard._locks.clear()
        guard._fails.clear()
        guard._day.clear()
    for k in [k for k in guard._rate if k[0] in ("pair", "handoff", "features")]:
        guard._rate.pop(k, None)


def switch(**kw):
    r = ADMIN.put("/api/admin/join", json=kw)
    assert r.status_code == 200, r.text


def invite(name="", pack="", days=7, uid=None):
    body = {"name": name, "pack": pack, "days": days, "base": BASE}
    if uid:
        body["uid"] = uid
    r = ADMIN.post("/api/admin/join/invites", json=body)
    assert r.status_code == 200, r.text
    link = r.json()["link"]
    assert link.startswith(BASE + "/#join="), link
    return link.split("#join=", 1)[1], r.json()


def uid_of(name):
    return next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Off(unittest.TestCase):
    def setUp(self):
        reset_guard()

    def test_everything_is_404_while_off(self):
        switch(mode="off", handoff=False)
        c = TestClient(panel.app)
        for path in ("/api/join/check", "/api/join", "/api/iphone/join", "/api/handoff/claim", "/api/handoff/finish"):
            self.assertEqual(c.post(path, json={"code": "x" * 22}).status_code, 404, path)
        r = ADMIN.post("/api/admin/join/invites", json={"name": "Nobody", "base": BASE})
        self.assertEqual(r.status_code, 409)

    def test_pin_links_work_while_new_people_are_off(self):
        switch(mode="invite")
        new_code, _ = invite("Olaf Spät")
        switch(mode="off")
        ADMIN.post("/api/admin/profiles", json={"name": "Otto Off", "pin": "1234"})
        code, _ = invite(uid=uid_of("Otto Off"), days=1)
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/join/check", json={"code": code}).json()["kind"], "pin")
        self.assertEqual(c.post("/api/join/check", json={"code": new_code}).status_code, 400)   # new people stay off
        self.assertEqual(c.post("/api/join", json={"code": new_code, "name": "Olaf Spät", "pin": "123456"}).status_code, 400)
        self.assertEqual(c.post("/api/join", json={"code": code, "pin": "654321"}).status_code, 200)
        reset_guard()
        self.assertEqual(c.post("/api/join/check", json={"code": code}).status_code, 404)   # no PIN link open: dark again

    def test_default_is_off(self):
        self.assertEqual(join.PACKS[0]["id"], "familie")
        with open(join.FILE + ".missing", "w"):
            pass
        real = join.FILE
        join.FILE = join.FILE + ".missing"
        try:
            self.assertEqual(join.mode(), "off")
            self.assertEqual(join.settings()["mfa"], "data")
            self.assertFalse(join.settings()["handoff"])
        finally:
            join.FILE = real

    def test_switching_needs_the_admin(self):
        self.assertEqual(TestClient(panel.app).put("/api/admin/join", json={"mode": "invite"}).status_code, 401)
        self.assertEqual(ADMIN.put("/api/admin/join", json={"mode": "open"}).status_code, 400)
        self.assertEqual(ADMIN.put("/api/admin/join", json={"app_link": "http://x.example"}).status_code, 400)
        self.assertEqual(ADMIN.put("/api/admin/join", json={"app_link": "javascript:alert(1)"}).status_code, 400)


class Invite(unittest.TestCase):
    def setUp(self):
        reset_guard()
        helpers.set_config(weather=True, tasks=False, mfa=False)
        switch(mode="invite", mfa="data")

    def test_big_bodies_are_refused_before_reading(self):
        c = TestClient(panel.app)
        big = '{"code": "' + "a" * 5000 + '"}'
        for path in ("/api/join/check", "/api/join", "/api/iphone/join", "/api/handoff/finish"):
            r = c.post(path, content=big, headers={"content-type": "application/json"})
            self.assertIn(r.status_code, (403, 404, 413), path)   # handoff and the app are off here: refused before reading
        self.assertEqual(c.post("/api/join/check", content=big, headers={"content-type": "application/json"}).status_code, 413)

    def test_join_makes_a_profile_signs_in_and_uses_the_code_up(self):
        code, made = invite("Ina Neu", pack="familie")
        self.assertIn("<svg", made["qr"])
        c = TestClient(panel.app)
        d = c.post("/api/join/check", json={"code": code}).json()
        self.assertEqual((d["kind"], d["name"], d["pin_min"]), ("new", "Ina Neu", 6))
        self.assertEqual(c.post("/api/join", json={"code": code, "name": "Ina Neu", "pin": "12345"}).status_code, 400)  # too short
        r = c.post("/api/join", json={"code": code, "name": "Ina Neu", "pin": "123456"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.get("/api/whoami").json()["profile"]["name"], "Ina Neu")
        uid = uid_of("Ina Neu")
        s = profiles.settings(uid)
        self.assertIs(s.get("wx_on"), True)          # in the pack and on for the Spark
        self.assertNotIn("tasks_on", s)              # in the pack, but off for the Spark: stays off
        self.assertEqual(TestClient(panel.app).post("/api/join", json={"code": code, "name": "Ina Zwei", "pin": "123456"}).status_code, 400)
        self.assertTrue(onboard.state(uid)["fresh"])
        import coadmin
        self.assertEqual(coadmin.role(uid), "")       # never a role
        self.assertEqual([i["state"] for i in join.listing() if i["id"] == made["id"]], ["used"])

    def test_only_the_hash_is_kept_and_the_log_has_no_code(self):
        code, made = invite("Hash Test")
        with open(join.FILE) as f:
            self.assertNotIn(code, f.read())
        with open(guard.AUDIT) as f:
            self.assertNotIn(code, f.read())

    def test_taken_name_keeps_the_invitation(self):
        ADMIN.post("/api/admin/profiles", json={"name": "Schon Da", "pin": "1234"})
        code, _ = invite("Schon Da")
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/join", json={"code": code, "name": "schon da", "pin": "123456"}).status_code, 409)
        self.assertEqual(c.post("/api/join", json={"code": code, "name": "Neu Da", "pin": "123456"}).status_code, 200)

    def test_expired_and_revoked_do_not_work(self):
        code, made = invite("Alt")
        with join._lock:
            d = join._read()
            d["invites"][made["id"]]["until"] = int(time.time()) - 5
            join._write(d)
        self.assertEqual(TestClient(panel.app).post("/api/join/check", json={"code": code}).status_code, 400)
        code2, made2 = invite("Weg")
        self.assertEqual(ADMIN.delete("/api/admin/join/invites/" + made2["id"]).status_code, 200)
        self.assertEqual(TestClient(panel.app).post("/api/join", json={"code": code2, "name": "Weg", "pin": "123456"}).status_code, 400)

    def test_wrong_codes_lock_the_address(self):
        c = TestClient(panel.app)
        for _ in range(guard.MAX_FAILS):
            self.assertEqual(c.post("/api/join/check", json={"code": "A" * 22}).status_code, 400)
        code, _ = invite("Gesperrt")
        self.assertEqual(c.post("/api/join/check", json={"code": code}).status_code, 429)
        reset_guard()
        self.assertEqual(c.post("/api/join/check", json={"code": code}).status_code, 200)

    def test_invitations_need_https_and_a_limit(self):
        self.assertEqual(ADMIN.post("/api/admin/join/invites", json={"name": "X", "base": "http://spark.example"}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/join/invites", json={"name": "X", "base": BASE, "days": 3}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/join/invites", json={"name": "X", "base": BASE, "pack": "nope"}).status_code, 400)
        real = join.MAX_OPEN
        join.MAX_OPEN = len([i for i in join.listing() if i["state"] == "open"])
        try:
            self.assertEqual(ADMIN.post("/api/admin/join/invites", json={"name": "X", "base": BASE}).status_code, 409)
        finally:
            join.MAX_OPEN = real

    def test_packs_keep_only_known_functions(self):
        r = ADMIN.put("/api/admin/join/packs", json={"packs": [
            {"id": "kind", "name": "Kind <b>", "keys": ["weather", "nonsense", "iphoneupdate", "iphonepanel"]},
            {"id": "BAD ID", "name": "x", "keys": []}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["packs"], [{"id": "kind", "name": "Kind b", "keys": ["weather"]}])
        ADMIN.put("/api/admin/join/packs", json={"packs": [dict(p) for p in join.PACKS]})

    def test_pin_link_sets_a_new_pin_and_ends_old_logins(self):
        ADMIN.post("/api/admin/profiles", json={"name": "Pia Pin", "pin": "1234"})
        old = TestClient(panel.app)
        self.assertEqual(old.post("/api/profile/login", json={"name": "Pia Pin", "pin": "1234"}).status_code, 200)
        uid = uid_of("Pia Pin")
        code, _ = invite(uid=uid, days=1)
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/join/check", json={"code": code}).json()["kind"], "pin")
        r = c.post("/api/join", json={"code": code, "pin": "654321"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.get("/api/whoami").json()["profile"]["name"], "Pia Pin")
        self.assertIsNone(old.get("/api/whoami").json()["profile"])
        self.assertEqual(TestClient(panel.app).post("/api/profile/login", json={"name": "Pia Pin", "pin": "654321"}).status_code, 200)

    def test_pin_link_still_asks_the_second_step(self):
        ADMIN.post("/api/admin/profiles", json={"name": "Max Mfa", "pin": "1234"})
        uid = uid_of("Max Mfa")
        code, _ = invite(uid=uid, days=1)
        real = (mfa.enabled, mfa.verify)
        mfa.enabled = lambda who: who == uid
        mfa.verify = lambda who, c: c == "123456"
        try:
            c = TestClient(panel.app)
            self.assertTrue(c.post("/api/join/check", json={"code": code}).json()["code"])
            self.assertEqual(c.post("/api/join", json={"code": code, "pin": "654321"}).json(), {"code": True})
            self.assertEqual(c.post("/api/join", json={"code": code, "pin": "654321", "mfa_code": "000000"}).status_code, 401)
            self.assertEqual(c.post("/api/join", json={"code": code, "pin": "654321", "mfa_code": "123456"}).status_code, 200)
        finally:
            mfa.enabled, mfa.verify = real

    def test_iphone_app_joins_and_gets_its_key(self):
        helpers.set_config(iphone=True)
        try:
            code, _ = invite("App Anna")
            r = TestClient(panel.app).post("/api/iphone/join", json={"code": code, "name": "App Anna", "pin": "123456", "device": "Annas iPhone"})
            self.assertEqual(r.status_code, 200, r.text)
            uid = uid_of("App Anna")
            dev = next(x for x in profiles._load()["devices"] if x["user"] == uid)
            self.assertEqual(dev["scope"], "app")
            self.assertIs(profiles.settings(uid)["app_on"], True)
            h = TestClient(panel.app, headers={profiles.DEVICE_HEADER: r.json()["token"]}).get("/api/iphone/hello")
            self.assertEqual(h.json()["profile"], "App Anna")
        finally:
            helpers.set_config(iphone=False)


class SecondStep(unittest.TestCase):
    def setUp(self):
        reset_guard()
        helpers.set_config(mfa=True, documents=True, doc_pictures=True, agent=True)
        switch(mode="invite", mfa="data")

    def tearDown(self):
        helpers.set_config(mfa=False, doc_pictures=False, agent=False)

    def test_mail_documents_and_jobs_wait_for_the_second_step(self):
        code, _ = invite("Duty Dora")
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/join", json={"code": code, "name": "Duty Dora", "pin": "123456"}).status_code, 200)
        uid = uid_of("Duty Dora")
        self.assertTrue(join.mfa_due(uid))
        self.assertEqual(features.reason("docpics", uid), "profile")   # own switch still off: that comes first
        profiles.save_settings(uid, {"doc_pictures": True})
        self.assertEqual(features.reason("docpics", uid), "mfa")
        self.assertFalse(join._duty(uid, "weather"))   # only mail, documents and jobs wait
        r = c.post("/api/profile/mail", json={"host": "imap.example", "user": "x", "password": "y"})
        self.assertEqual(r.status_code, 403)
        with self.assertRaises(ValueError):
            wissen.add(uid, "a.txt", b"Hallo")
        agent.admin_state()
        self.assertEqual(agent.granted(uid), "")
        real = mfa.enabled
        mfa.enabled = lambda who: who == uid
        try:
            self.assertFalse(join.mfa_due(uid))
            self.assertIsNone(features.reason("docpics", uid))
            r = c.post("/api/profile/mfa/disable", headers={"X-Speech-Code": "1"})
            self.assertEqual(r.status_code, 403)    # the admin asks for it: not switched off by the profile
        finally:
            mfa.enabled = real

    def test_optional_means_no_duty(self):
        switch(mfa="off")
        code, _ = invite("Frei Fritz")
        TestClient(panel.app).post("/api/join", json={"code": code, "name": "Frei Fritz", "pin": "123456"})
        self.assertFalse(join.mfa_due(uid_of("Frei Fritz")))
        switch(mfa="data")

    def test_old_profiles_have_no_duty(self):
        ADMIN.post("/api/admin/profiles", json={"name": "Alt Anton", "pin": "1234"})
        self.assertFalse(join.mfa_due(uid_of("Alt Anton")))


class Setup(unittest.TestCase):
    def setUp(self):
        reset_guard()
        helpers.set_config(weather=True, calendar=True, mail=False, telegram=False)
        switch(mode="invite")

    def test_list_shows_what_the_spark_allows_and_checks_it_itself(self):
        code, _ = invite("Setup Sina")
        c = TestClient(panel.app)
        c.post("/api/join", json={"code": code, "name": "Setup Sina", "pin": "123456"})
        uid = uid_of("Setup Sina")
        d = c.get("/api/profile/setup").json()
        keys = {x["key"] for x in d["items"]}
        self.assertIn("weather", keys)
        self.assertIn("calendar", keys)
        self.assertNotIn("mail", keys)          # off for the Spark
        self.assertNotIn("telegram", keys)
        wx = next(x for x in d["items"] if x["key"] == "weather")
        self.assertFalse(wx["done"])
        import weather
        profiles._write(weather._file(uid), {"lat": 50.0, "lon": 8.0, "name": "Mainz"})
        onboard._cache.clear()
        wx = next(x for x in c.get("/api/profile/setup").json()["items"] if x["key"] == "weather")
        self.assertTrue(wx["done"])
        # the browser cannot tick anything off, only "Später" and the welcome step
        self.assertEqual(c.put("/api/profile/setup", json={"later": ["nonsense"]}).status_code, 400)
        r = c.put("/api/profile/setup", json={"later": ["calendar"], "welcome": True, "done": ["calendar"]})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Kalender verbinden", r.json()["summary"]["open"])
        w = c.get("/api/whoami").json()["setup"]
        self.assertIn("total", w)
        a = ADMIN.get("/api/admin/profiles/" + uid).json()
        self.assertIn("setup", a)
        # remind: once an hour
        self.assertEqual(ADMIN.post(f"/api/admin/profiles/{uid}/remind").status_code, 200)
        self.assertEqual(ADMIN.post(f"/api/admin/profiles/{uid}/remind").status_code, 429)

    def test_remarkable_step_only_where_allowed(self):
        switch(mode="invite", mfa="off")
        code, _ = invite("Rm Rita")
        c = TestClient(panel.app)
        c.post("/api/join", json={"code": code, "name": "Rm Rita", "pin": "123456"})
        uid = uid_of("Rm Rita")
        keys = lambda: {x["key"]: x for x in c.get("/api/profile/setup").json()["items"]}
        self.assertNotIn("remarkable", keys())
        helpers.set_config(documents=True, doc_pictures=True, remarkable=True)
        try:
            onboard._cache.clear()
            it = keys()["remarkable"]
            self.assertEqual((it["me"], it["done"]), ("rmbox", False))
            import remarkable
            remarkable.save(uid, dict(remarkable.load(uid), token="sealed"))
            onboard._cache.clear()
            self.assertTrue(keys()["remarkable"]["done"])
        finally:
            helpers.set_config(documents=False, doc_pictures=False, remarkable=False)

    def test_setup_only_for_profiles(self):
        self.assertIn(TestClient(panel.app).get("/api/profile/setup").status_code, (401, 403))
        self.assertIsNone(TestClient(panel.app).get("/api/whoami").json().get("setup"))


class Handoff(unittest.TestCase):
    def setUp(self):
        reset_guard()
        switch(handoff=True)

    def tearDown(self):
        switch(handoff=False)

    def _pc(self, name):
        ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
        pc = TestClient(panel.app)
        pc.post("/api/profile/login", json={"name": name, "pin": "1234"})
        r = pc.post("/api/profile/handoff", json={"base": BASE})
        self.assertEqual(r.status_code, 200, r.text)
        return pc, r.json()["id"], r.json()["link"].split("#hand=", 1)[1]

    def test_right_number_signs_the_phone_in_once(self):
        pc, hid, code = self._pc("Hand Hanna")
        phone = TestClient(panel.app)
        got = phone.post("/api/handoff/claim", json={"code": code}).json()
        self.assertEqual(TestClient(panel.app).post("/api/handoff/claim", json={"code": code}).status_code, 400)  # only once
        self.assertEqual(phone.post("/api/handoff/finish", json={"code": code, "wait": got["wait"]}).json(), {"wait": True})
        self.assertIsNone(phone.get("/api/whoami").json()["profile"])
        s = pc.get("/api/profile/handoff/" + hid).json()
        self.assertIn(got["num"], s["choices"])
        self.assertEqual(len(s["choices"]), 3)
        self.assertEqual(pc.post(f"/api/profile/handoff/{hid}/confirm", json={"num": got["num"]}).json()["state"], "ok")
        self.assertEqual(TestClient(panel.app).post("/api/handoff/finish", json={"code": code, "wait": "x" * 22}).status_code, 410)
        self.assertEqual(phone.post("/api/handoff/finish", json={"code": code, "wait": got["wait"]}).status_code, 200)
        self.assertEqual(phone.get("/api/whoami").json()["profile"]["name"], "Hand Hanna")
        self.assertEqual(phone.post("/api/handoff/finish", json={"code": code, "wait": got["wait"]}).status_code, 410)

    def test_wrong_number_ends_it(self):
        pc, hid, code = self._pc("Hand Hugo")
        phone = TestClient(panel.app)
        got = phone.post("/api/handoff/claim", json={"code": code}).json()
        wrong = next(n for n in pc.get("/api/profile/handoff/" + hid).json()["choices"] if n != got["num"])
        self.assertEqual(pc.post(f"/api/profile/handoff/{hid}/confirm", json={"num": wrong}).json()["state"], "dead")
        self.assertEqual(phone.post("/api/handoff/finish", json={"code": code, "wait": got["wait"]}).status_code, 410)
        self.assertIsNone(phone.get("/api/whoami").json()["profile"])

    def test_other_profiles_cannot_confirm_and_it_expires(self):
        pc, hid, code = self._pc("Hand Ida")
        other, _, _ = self._pc("Hand Otto")
        got = TestClient(panel.app).post("/api/handoff/claim", json={"code": code}).json()
        self.assertEqual(other.post(f"/api/profile/handoff/{hid}/confirm", json={"num": got["num"]}).status_code, 404)
        onboard._hand[hid]["t"] -= onboard.HAND_SECS + 1
        self.assertEqual(pc.get("/api/profile/handoff/" + hid).status_code, 404)

    def test_device_keys_cannot_start_it(self):
        ADMIN.post("/api/admin/profiles", json={"name": "Hand Key", "pin": "1234"})
        token = ADMIN.post("/api/admin/devices", json={"name": "Skript", "user": uid_of("Hand Key")}).json()["token"]
        r = TestClient(panel.app, headers={profiles.DEVICE_HEADER: token}).post("/api/profile/handoff", json={"base": BASE})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
