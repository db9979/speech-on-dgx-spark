"""Prüfzugang für die iPhone-App (pruefzugang.py, Dominik 2026-10-17 "1+2"): Apple's app review pairs with a typed code.

Off unless the admin switches chat.iphone_review on; only the code's hash is kept; the code works DAYS days for at most
MAX_USES iPhones; wrong codes count like wrong PINs; never for an admin-role profile; while a profile has a review
access LOCKED is blocked for it; deleting the access, its expiry and deleting the profile remove the paired iPhones.
The demo mode of the app ("Ohne Spark ansehen") sends nothing: checked on the Swift source, skipped in the app/-only
copy. Times come from `now`, never the wall clock alone.
"""
import json
import os
import time
import unittest

from tests import helpers

helpers.start()
import coadmin  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import iphone  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import pruefzugang  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_iphone import ADMIN, BASE, profile, uid_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IOS = os.path.join(ROOT, "ios", "Spark")


def reset_guard():
    with guard._lock:
        guard._locks.clear()
        guard._fails.clear()
        guard._day.clear()
    for k in [k for k in guard._rate if k[0] == "pair"]:
        guard._rate.pop(k, None)


def clear():
    with pruefzugang._lock:
        pruefzugang._write({"codes": {}})


def make(name):
    profile(name)
    r = ADMIN.post("/api/admin/pruefzugang", json={"uid": uid_of(name), "base": BASE})
    assert r.status_code == 200, r.text
    return r.json()


def pair(code, name="Review iPhone"):
    return TestClient(panel.app).post("/api/iphone/pair", json={"code": code, "name": name})


class Review(unittest.TestCase):
    def setUp(self):
        helpers.set_config(iphone=True, iphone_review=True, deny={})
        reset_guard()
        clear()

    def tearDown(self):
        helpers.set_config(iphone=False, iphone_review=False, deny={})
        clear()
        reset_guard()

    def test_off_by_default_and_nothing_pairs_while_off(self):
        with open(features.DEFAULTS) as f:
            self.assertIs(json.load(f)["chat"]["iphone_review"], False)
        self.assertNotIn("iphonepruef", features.DEFAULT_ON)
        r = make("Review Off")
        helpers.set_config(iphone_review=False)
        self.assertEqual(ADMIN.post("/api/admin/pruefzugang", json={"uid": uid_of("Review Off"), "base": BASE}).status_code, 403)
        self.assertEqual(pair(r["code"]).status_code, 400)
        self.assertEqual(ADMIN.get("/api/admin/pruefzugang").status_code, 200)        # the list and deleting stay
        self.assertEqual(ADMIN.delete(f"/api/admin/pruefzugang/{r['id']}").status_code, 200)

    def test_admin_only_https_only(self):
        profile("Review Anna")
        stranger = profile("Review Fremd")
        self.assertIn(stranger.post("/api/admin/pruefzugang", json={"uid": uid_of("Review Anna"), "base": BASE}).status_code, (401, 403))
        self.assertIn(stranger.get("/api/admin/pruefzugang").status_code, (401, 403))
        self.assertEqual(ADMIN.post("/api/admin/pruefzugang", json={"uid": uid_of("Review Anna"), "base": "http://x.de"}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/pruefzugang", json={"uid": "u_000000000000", "base": BASE}).status_code, 404)

    def test_code_pairs_typed_in_any_case_and_only_its_hash_is_kept(self):
        r = make("Review Ben")
        self.assertRegex(r["code"], r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        with open(pruefzugang.FILE) as f:
            self.assertNotIn(r["code"].replace("-", ""), f.read())
        typed = " " + r["code"].lower().replace("-", " ") + " "
        p = pair(typed)
        self.assertEqual(p.status_code, 200, p.text)
        self.assertEqual(p.json()["profile"], "Review Ben")
        h = {"X-Speech-Device": p.json()["token"]}
        self.assertEqual(TestClient(panel.app).get("/api/iphone/hello", headers=h).status_code, 200)
        row = ADMIN.get("/api/admin/pruefzugang").json()["codes"][0]
        self.assertEqual((row["used"], row["phones"], row["state"]), (1, 1, "open"))

    def test_at_most_max_uses(self):
        r = make("Review Uses")
        profiles_before = len(iphone.phones(uid_of("Review Uses")))
        for i in range(pruefzugang.MAX_USES):
            self.assertEqual(pair(r["code"], f"iPhone {i}").status_code, 200)
        self.assertEqual(pair(r["code"]).status_code, 400)
        self.assertEqual(len(iphone.phones(uid_of("Review Uses"))), profiles_before + pruefzugang.MAX_USES)

    def test_wrong_codes_lock_the_address(self):
        make("Review Lock")
        codes = []
        for _ in range(12):
            codes.append(pair("ABCD-EFGH-JKMN").status_code)
            for k in [k for k in guard._rate if k[0] == "pair"]:   # the lockout, not the rate limit
                guard._rate.pop(k, None)
        self.assertIn(429, codes)
        self.assertNotIn(200, codes)

    def test_expired_code_pairs_no_more_and_its_iphones_go(self):
        r = make("Review Old")
        p = pair(r["code"])
        self.assertEqual(p.status_code, 200)
        with pruefzugang._lock:   # its 14 days are over
            d = pruefzugang._read()
            d["codes"][r["id"]]["until"] = int(time.time()) - 60
            pruefzugang._write(d)
        self.assertEqual(pair(r["code"]).status_code, 400)
        self.assertEqual(len(iphone.phones(uid_of("Review Old"))), 1)
        pruefzugang.tidy()
        self.assertEqual(iphone.phones(uid_of("Review Old")), [])
        h = {"X-Speech-Device": p.json()["token"]}
        self.assertIn(TestClient(panel.app).get("/api/iphone/hello", headers=h).status_code, (401, 403))

    def test_delete_removes_the_paired_iphones(self):
        r = make("Review Del")
        p = pair(r["code"])
        self.assertEqual(p.status_code, 200)
        self.assertEqual(ADMIN.delete(f"/api/admin/pruefzugang/{r['id']}").status_code, 200)
        h = {"X-Speech-Device": p.json()["token"]}
        self.assertIn(TestClient(panel.app).get("/api/iphone/hello", headers=h).status_code, (401, 403))
        self.assertEqual(pair(r["code"]).status_code, 400)
        self.assertEqual(ADMIN.delete(f"/api/admin/pruefzugang/{r['id']}").status_code, 404)

    def test_never_for_an_admin_role(self):
        profile("Review Chef")
        uid = uid_of("Review Chef")
        with coadmin._lock:
            d = coadmin._read()
            d["users"][uid] = {"role": "admin"}
            coadmin._write(d)
        try:
            self.assertEqual(ADMIN.post("/api/admin/pruefzugang", json={"uid": uid, "base": BASE}).status_code, 403)
        finally:
            coadmin.forget(uid)

    def test_profile_with_a_review_access_is_locked_out_of_the_outside(self):
        helpers.set_config(chats=True, ha=True, mail=True)
        try:
            profile("Review Lock2")
            uid = uid_of("Review Lock2")
            self.assertFalse(features.blocked("chats", uid))
            r = ADMIN.post("/api/admin/pruefzugang", json={"uid": uid, "base": BASE}).json()
            for key in pruefzugang.LOCKED:
                self.assertIn(key, features.BY_KEY, key)
                self.assertTrue(features.blocked(key, uid), key)
            self.assertTrue(features.blocked("chatgroups", uid))   # what builds on a locked function too
            self.assertFalse(features.blocked("weather", uid))
            ADMIN.delete(f"/api/admin/pruefzugang/{r['id']}")
            self.assertFalse(features.blocked("chats", uid))
        finally:
            helpers.set_config(chats=False, ha=False, mail=False)

    def test_deleting_the_profile_forgets_its_access(self):
        r = make("Review Gone")
        uid = uid_of("Review Gone")
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{uid}").status_code, 200)
        self.assertNotIn(r["id"], pruefzugang._read()["codes"])

    def test_link_codes_never_look_like_review_codes(self):
        import kopplung
        for _ in range(50):
            self.assertIsNone(pruefzugang.norm(kopplung.link_code()))
        self.assertIsNone(pruefzugang.norm("ABCD-EFGH-JKM0"))   # 0 is not in the alphabet
        self.assertIsNone(pruefzugang.norm(["ABCDEFGHJKMN"]))


class DemoMode(unittest.TestCase):
    """The app's demo shows examples only: no request leaves the phone while it runs."""

    def read(self, name):
        path = os.path.join(IOS, name)
        if not os.path.exists(path):
            raise unittest.SkipTest("ios/ is not in this copy (the Spark tests only app/)")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_demo_answers_on_the_phone(self):
        conv = self.read("Conversation.swift")
        self.assertIn("var demo", conv)
        demo = self.read("Demo.swift")
        self.assertIn("static func answer", demo)
        self.assertNotIn("SparkAPI", demo)
        self.assertNotIn("URLSession", demo)

    def test_review_code_field_in_the_pairing_view(self):
        views = self.read("Views.swift")
        self.assertIn("Mit Prüf-Code verbinden", views)
        self.assertIn("Ohne Spark ansehen", views)
        strings = self.read("Localizable.xcstrings")
        for de in ("Mit Prüf-Code verbinden", "Ohne Spark ansehen", "Vorführung beenden"):
            self.assertIn(f'"{de}"', strings)


if __name__ == "__main__":
    unittest.main()
