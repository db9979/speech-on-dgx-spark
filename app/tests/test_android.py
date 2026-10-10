"""Android app (android.py): off by default, the APK only from a checked GitHub release, download links with a
one-time token, notes for the app while it is closed, and push picking the app when it asked lately."""
import asyncio
import hashlib
import json
import os
import unittest

from tests import helpers

helpers.start()
import android  # noqa: E402
import guard  # noqa: E402
import httpx  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BASE = "https://spark.example.de"
GH = "http://gh.test"
APK = b"PK\x03\x04 fake apk " * 100


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in profiles.names() if u["name"] == name)


def github(meta, apk=APK, url=GH + "/dl/spark.apk"):
    """A fake GitHub: one release android-v… with android.json and spark.apk (and an older fw- release)."""
    def handle(req):
        p = req.url.path
        if p.endswith("/releases"):
            return httpx.Response(200, json=[
                {"tag_name": "fw-1.0", "assets": []},
                {"tag_name": "android-v" + meta.get("version", "x"), "assets": [
                    {"name": "android.json", "browser_download_url": GH + "/dl/android.json"},
                    {"name": "spark.apk", "browser_download_url": url}]}])
        if p == "/dl/android.json":
            return httpx.Response(200, content=json.dumps(meta).encode())
        if p == "/dl/spark.apk":
            return httpx.Response(200, content=apk)
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def good(version="1.0.0", code=1, apk=APK):
    return {"version": version, "code": code, "size": len(apk), "sha256": hashlib.sha256(apk).hexdigest()}


class Android(unittest.TestCase):
    def setUp(self):
        self.gh = os.environ.get("SPEECH_SPARK_GITHUB_API")   # other tests run their own fake GitHub
        os.environ["SPEECH_SPARK_GITHUB_API"] = GH
        helpers.set_config(android=True)
        android._tokens.clear()
        android._notes.clear()
        android._polled.clear()
        for k in [k for k in guard._rate if k[0] in ("pair", "android")]:
            guard._rate.pop(k, None)
        for f in (android.APK, android.META):
            if os.path.exists(f):
                os.remove(f)

    def tearDown(self):
        helpers.set_config(android=False)
        if self.gh is None:
            os.environ.pop("SPEECH_SPARK_GITHUB_API", None)
        else:
            os.environ["SPEECH_SPARK_GITHUB_API"] = self.gh

    def fetch(self, meta, **kw):
        async def go():
            async with github(meta, **kw) as c:
                return await android.fetch_apk(c)
        return asyncio.run(go())

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["android"], False)
        self.assertIs(profiles.SETTINGS["android_on"][0], False)

    def test_apk_only_with_matching_checksum_from_github(self):
        self.assertEqual(self.fetch(good()), "1.0.0")
        self.assertEqual(android.meta()["code"], 1)
        # an older or equal release changes nothing
        self.assertEqual(self.fetch(good("0.9.0", 1)), "1.0.0")
        bad = good("1.1.0", 2)
        bad["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.fetch(bad)
        with self.assertRaises(ValueError):   # larger than it says
            self.fetch(dict(good("1.1.0", 2), size=10))
        with self.assertRaises(ValueError):   # a download from anywhere else than GitHub
            self.fetch(good("1.1.0", 2), url="http://evil.test/dl/spark.apk")
        for broken in ({"version": "1.1", "code": 2}, dict(good("1.1.0", 2), code="2"), dict(good("1.1.0", 2), size=10 ** 9)):
            with self.assertRaises(ValueError):
                self.fetch(broken)
        self.assertEqual(android.meta()["version"], "1.0.0")   # nothing replaced the good one

    def test_download_link_needs_both_switches_and_expires(self):
        self.fetch(good())
        a = profile("Anja")
        self.assertEqual(a.post("/api/profile/android/link", json={"base": BASE}).status_code, 403)
        a.put("/api/profile/settings", json={"android_on": True})
        for bad in ("spark", "https://spark/x", "javascript:alert(1)"):
            self.assertEqual(a.post("/api/profile/android/link", json={"base": bad}).status_code, 400, bad)
        self.assertEqual(a.post("/api/profile/android/link", content="x" * 2000).status_code, 413)
        r = a.post("/api/profile/android/link", json={"base": BASE})
        self.assertEqual(r.status_code, 200, r.text)
        url = r.json()["url"]
        self.assertTrue(url.startswith(BASE + "/android/spark.apk?t="))
        token = url.split("t=")[1]
        phone = TestClient(panel.app)   # the phone's browser is not signed in
        r = phone.get("/android/spark.apk", params={"t": token})
        self.assertEqual((r.status_code, r.content), (200, APK))
        self.assertEqual(r.headers["content-type"], "application/vnd.android.package-archive")
        self.assertEqual(phone.get("/android/spark.apk", params={"t": "x" * 32}).status_code, 404)
        self.assertEqual(phone.get("/android/spark.apk").status_code, 404)
        for _ in range(android.TOKEN_USES - 1):
            self.assertEqual(phone.get("/android/spark.apk", params={"t": token}).status_code, 200)
        self.assertEqual(phone.get("/android/spark.apk", params={"t": token}).status_code, 404)   # used up
        # only the hash is kept, and the link is gone after TOKEN_SECONDS (without the wall clock)
        self.assertNotIn(token, json.dumps(list(android._tokens)))
        t2 = android.new_token(uid_of("Anja"), now=1000.0)
        self.assertEqual(android.use_token(t2, now=1000.0 + android.TOKEN_SECONDS - 1), uid_of("Anja"))
        self.assertIsNone(android.use_token(t2, now=1000.0 + android.TOKEN_SECONDS + 1))
        # the admin switch off stops downloads too
        t3 = android.new_token(uid_of("Anja"))
        helpers.set_config(android=False)
        self.assertEqual(phone.get("/android/spark.apk", params={"t": t3}).status_code, 404)

    def test_guests_and_device_keys_get_nothing(self):
        guest = TestClient(panel.app)
        self.assertIn(guest.get("/api/android/notes").status_code, (401, 403))
        self.assertIn(guest.post("/api/profile/android/link", json={"base": BASE}).status_code, (401, 403))
        self.assertIn(guest.get("/api/admin/android").status_code, (401, 403))
        self.assertIn(guest.post("/api/admin/android/fetch").status_code, (401, 403))
        a = profile("Arne")
        self.assertIn(a.get("/api/admin/android").status_code, (401, 403))

    def test_notes_for_the_app_and_push_picks_it(self):
        a = profile("Alma")
        uid = uid_of("Alma")
        self.assertEqual(a.get("/api/android/notes").status_code, 403)   # own switch off
        a.put("/api/profile/settings", json={"android_on": True})
        self.assertFalse(android.reachable(uid))
        r = a.get("/api/android/notes")
        self.assertEqual(r.json()["notes"], [])
        self.assertTrue(android.reachable(uid))
        self.assertEqual(push.pick(uid)[0], "and")
        self.assertEqual(asyncio.run(push.send(uid, "Erinnerung", "Tee ist fertig", tag="rem")), 1)
        r = a.get("/api/android/notes", params={"after": 0}).json()
        self.assertEqual([(x["title"], x["body"]) for x in r["notes"]], [("Erinnerung", "Tee ist fertig")])
        self.assertEqual(a.get("/api/android/notes", params={"after": r["last"]}).json()["notes"], [])
        # another profile never sees it
        b = profile("Bodo")
        b.put("/api/profile/settings", json={"android_on": True})
        self.assertEqual(b.get("/api/android/notes").json()["notes"], [])
        # old notes and quiet apps drop out (without the wall clock)
        android.keep(uid, "x", "y", now=0.0)
        self.assertNotIn("x", [x["title"] for x in android.notes(uid, 0, now=android.NOTE_SECONDS + 1)[0]])
        self.assertFalse(android.reachable(uid, now=android._polled[uid] + android.POLLED_KEEP + 1))
        for i in range(android.NOTE_MAX + 5):
            android.keep(uid, f"n{i}", "b")
        self.assertEqual(len(android._notes[uid]), android.NOTE_MAX)

    def test_page_inside_the_app_gets_the_notes(self):
        a = profile("Ali")
        uid = uid_of("Ali")
        a.put("/api/profile/settings", json={"android_on": True})
        a.get("/api/android/notes")
        a.get("/api/profile/reminders", params={"page": 1}, headers={"user-agent": "Mozilla/5.0 SparkAndroid/1.0.0"})
        self.assertEqual(profiles.LAST_USED[uid][0], "and")
        a.get("/api/profile/reminders", params={"page": 1}, headers={"user-agent": "Mozilla/5.0"})
        self.assertEqual(profiles.LAST_USED[uid][0], "web")


if __name__ == "__main__":
    unittest.main()
