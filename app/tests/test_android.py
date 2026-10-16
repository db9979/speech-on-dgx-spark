"""Android app (android.py): off by default, the APK only from a checked GitHub release, download links with a
one-time token, notes for the app while it is closed, and push picking the app when it asked lately."""
import asyncio
import hashlib
import json
import os
import time
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
        helpers.set_config(android=True, deny={})
        android._tokens.clear()
        android._notes.clear()
        android._polled.clear()
        for k in [k for k in guard._rate if k[0] in ("pair", "android")]:
            guard._rate.pop(k, None)
        for f in (android.APK, android.META):
            if os.path.exists(f):
                os.remove(f)

    def tearDown(self):
        helpers.set_config(android=False, deny={})
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
        self.assertNotIn("android_on", profiles.SETTINGS)   # no profile switch: released by the admin, it works

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
        helpers.set_config(deny={"android": [uid_of("Anja")]})   # the admin blocks this profile
        self.assertEqual(a.post("/api/profile/android/link", json={"base": BASE}).status_code, 403)
        helpers.set_config(deny={})                                # released: works at once
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
        helpers.set_config(deny={"android": [uid]})
        self.assertEqual(a.get("/api/android/notes").status_code, 403)   # blocked by the admin
        helpers.set_config(deny={})
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
        a.get("/api/android/notes")
        a.get("/api/profile/reminders", params={"page": 1}, headers={"user-agent": "Mozilla/5.0 SparkAndroid/1.0.0"})
        self.assertEqual(profiles.LAST_USED[uid][0], "and")
        a.get("/api/profile/reminders", params={"page": 1}, headers={"user-agent": "Mozilla/5.0"})
        self.assertEqual(profiles.LAST_USED[uid][0], "web")


class Live(unittest.TestCase):
    """"Mitteilungen sofort": a lasting wait instead of a question every 15 minutes (android.py, LiveConn.kt)."""
    def setUp(self):
        Android.setUp(self)
        android._waiters.clear()
        for k in [k for k in guard._rate if k[0] == "androidwait"]:
            guard._rate.pop(k, None)
        self.wait = android.WAIT_SECONDS

    def tearDown(self):
        android.WAIT_SECONDS = self.wait
        helpers.set_config(android_live=False)
        Android.tearDown(self)

    def test_off_by_default_and_needs_both_switches(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["android_live"], False)
        self.assertIs(profiles.SETTINGS["android_live"][0], True)   # a preference: on unless the profile opts out
        a = profile("Lina")
        uid = uid_of("Lina")
        self.addCleanup(profiles.save_settings, uid, {"android_live": True})
        self.assertFalse(a.get("/api/android/notes").json()["live"])
        self.assertEqual(a.get("/api/android/wait").status_code, 403)          # the admin's switch is off
        helpers.set_config(android_live=True)
        self.assertTrue(a.get("/api/android/notes").json()["live"])            # released: works at once
        self.assertTrue(a.get("/api/profile/android").json()["live_enabled"])
        a.put("/api/profile/settings", json={"android_live": False})           # the profile opts out
        self.assertFalse(a.get("/api/android/notes").json()["live"])
        self.assertEqual(a.get("/api/android/wait").status_code, 403)
        a.put("/api/profile/settings", json={"android_live": True})
        helpers.set_config(deny={"androidlive": [uid]})                       # the admin blocks this profile
        self.assertEqual(a.get("/api/android/wait").status_code, 403)
        helpers.set_config(deny={"android": [uid]})                           # ... or the app it builds on
        r = a.get("/api/profile/android").json()
        self.assertEqual((r["on"], r["live"]), (False, False))
        helpers.set_config(deny={})
        self.assertEqual(TestClient(panel.app).get("/api/android/wait").status_code, 401)   # guests never

    def test_a_note_wakes_the_waiting_app_at_once(self):
        import threading
        import time
        helpers.set_config(android_live=True)
        a = profile("Luka")
        uid = uid_of("Luka")
        last = a.get("/api/android/notes").json()["last"]
        android.WAIT_SECONDS = 10
        got = {}

        def wait():
            t0 = time.monotonic()
            got["r"] = a.get("/api/android/wait", params={"after": last}).json()
            got["took"] = time.monotonic() - t0
        th = threading.Thread(target=wait)
        th.start()
        for _ in range(100):
            if android.live_count():
                break
            time.sleep(0.05)
        self.assertEqual(android.live_count(), 1)
        self.assertEqual(asyncio.run(push.send(uid, "Chat", "Neue Nachricht", tag="chat")), 1)
        th.join(10)
        self.assertLess(got["took"], 5)
        self.assertEqual([x["title"] for x in got["r"]["notes"]], ["Chat"])
        self.assertEqual(android.live_count(), 0)
        # something already there: answered without waiting; nothing: empty after the wait
        self.assertEqual(len(a.get("/api/android/wait", params={"after": 0}).json()["notes"]), 1)
        android.WAIT_SECONDS = 0.2
        self.assertEqual(a.get("/api/android/wait", params={"after": got["r"]["last"]}).json()["notes"], [])

    def test_the_app_chooses_a_longer_hold_within_limits(self):
        # Akku (2026-10-16): ?hold= lets the app wait longer per question (fewer radio wake-ups), never past WAIT_MAX
        import time
        helpers.set_config(android_live=True)
        a = profile("Mara")
        last = a.get("/api/android/notes").json()["last"]
        self.assertEqual((android.WAIT_MIN, android.WAIT_MAX), (20, 280))
        lo, hi = android.WAIT_MIN, android.WAIT_MAX
        self.addCleanup(setattr, android, "WAIT_MIN", lo)
        self.addCleanup(setattr, android, "WAIT_MAX", hi)
        android.WAIT_MIN, android.WAIT_MAX, android.WAIT_SECONDS = 0.1, 0.3, 30
        t0 = time.monotonic()
        self.assertEqual(a.get("/api/android/wait", params={"after": last, "hold": 240}).json()["notes"], [])
        self.assertLess(time.monotonic() - t0, 5)                    # capped at WAIT_MAX, not 240 s
        android.WAIT_SECONDS = 0.2
        self.assertEqual(a.get("/api/android/wait", params={"after": last}).json()["notes"], [])   # old apps: WAIT_SECONDS
        root = os.path.join(helpers.APP, "..", "android", "app", "src", "main", "java", "io", "github", "db9979", "spark")
        if os.path.isdir(root):
            with open(os.path.join(root, "LiveConn.kt"), encoding="utf-8") as f:
                live = f.read()
            self.assertIn("&hold=$hold", live)
            self.assertIn("LONG_HOLD = 240", live)
            self.assertIn("SHORT_HOLD = 50", live)                   # a proxy that cuts: back to 50 s by itself

    def test_waiting_is_not_a_slow_page_and_the_app_has_its_service(self):
        self.assertIsNone(panel.slow_read("GET", "/api/android/wait", 50.0, 1000.0))
        self.assertIsNotNone(panel.slow_read("GET", "/api/android/notes", 50.0, 1000.0))
        root = os.path.join(helpers.APP, "..", "android", "app", "src", "main")
        if not os.path.isdir(root):   # a copy with only app/
            return
        with open(os.path.join(root, "AndroidManifest.xml")) as f:
            man = f.read()
        self.assertIn('android:name=".LiveConn"', man)
        self.assertIn('android:foregroundServiceType="specialUse"', man)
        self.assertIn("FOREGROUND_SERVICE_SPECIAL_USE", man)
        with open(os.path.join(root, "java", "io", "github", "db9979", "spark", "LiveConn.kt")) as f:
            kt = f.read()
        self.assertIn("/api/android/wait", kt)
        self.assertIn("code == 401 || code == 403", kt)   # switched off or signed out: the connection ends

class Update(unittest.TestCase):
    """"Update in der App": the app loads the APK from its own Spark with its sign-in (android.py, Updater.kt)."""
    def setUp(self):
        Android.setUp(self)
        android._seen.clear()

    fetch = Android.fetch

    def tearDown(self):
        helpers.set_config(android_update=False)
        android._seen.clear()
        Android.tearDown(self)

    def test_off_by_default_only_with_the_switch_and_never_blocked_or_for_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["android_update"], False)
        self.assertNotIn("android_update", profiles.SETTINGS)   # the admin releases it, no profile switch
        self.assertEqual(self.fetch(good("1.3.0", 5)), "1.3.0")
        a = profile("Uwe")
        uid = uid_of("Uwe")
        self.assertEqual(a.get("/api/android/apk").status_code, 403)                 # the admin's switch is off
        self.assertFalse(a.get("/api/android/notes").json()["update"])
        helpers.set_config(android_update=True)
        r = a.get("/api/android/apk")
        self.assertEqual((r.status_code, r.content), (200, APK))                      # released: works at once
        self.assertEqual(r.headers["content-type"], "application/vnd.android.package-archive")
        self.assertTrue(a.get("/api/android/notes").json()["update"])
        p = a.get("/api/profile/android").json()
        self.assertTrue(p["update"])
        self.assertEqual((p["app"]["version"], p["app"]["code"], p["app"]["size"]), ("1.3.0", 5, len(APK)))
        helpers.set_config(deny={"androidupdate": [uid]})                            # the admin blocks this profile
        self.assertEqual(a.get("/api/android/apk").status_code, 403)
        self.assertFalse(a.get("/api/profile/android").json()["update"])
        helpers.set_config(deny={"android": [uid]})                                  # ... or the app it builds on
        self.assertEqual(a.get("/api/android/apk").status_code, 403)
        helpers.set_config(deny={})
        self.assertEqual(TestClient(panel.app).get("/api/android/apk").status_code, 401)   # guests never

    def test_no_app_on_the_spark_and_a_rate_limit(self):
        helpers.set_config(android_update=True)
        a = profile("Vera")
        self.assertEqual(a.get("/api/android/apk").status_code, 409)
        self.assertEqual(self.fetch(good("1.3.0", 5)), "1.3.0")
        codes = [a.get("/api/android/apk").status_code for _ in range(25)]
        self.assertIn(429, codes)

    def test_the_version_each_app_runs_for_device_updates(self):
        import geraeteupdate
        self.assertEqual(self.fetch(good("1.3.0", 5)), "1.3.0")
        a = profile("Wim")
        uid = uid_of("Wim")
        a.get("/api/android/notes", headers={"user-agent": "SparkAndroid/1.2.0"})
        self.assertEqual(android.seen(uid), "1.2.0")
        self.assertEqual(android.seen(uid, now=time.time() + android.SEEN_KEEP + 1), "")   # old answers fade
        rows = geraeteupdate.devices(uid)["android"]
        self.assertEqual([(r["have"], r["newer"]) for r in rows], [("1.2.0", True)])
        a.get("/api/profile/android", headers={"user-agent": "Mozilla/5.0 SparkAndroid/1.3.0"})   # the page in the app
        self.assertEqual([(r["have"], r["newer"]) for r in geraeteupdate.devices(uid)["android"]], [("1.3.0", False)])
        a.get("/api/android/notes", headers={"user-agent": "Mozilla/5.0"})          # a browser names no version
        self.assertEqual(android.seen(uid), "1.3.0")
        self.assertEqual((android.newer("1.2.9", "1.10.0"), android.newer("", "1.0.0")), (True, None))

    def test_the_app_checks_before_android_installs(self):
        root = os.path.join(helpers.APP, "..", "android", "app", "src", "main")
        if not os.path.isdir(root):   # a copy with only app/
            return
        with open(os.path.join(root, "java", "io", "github", "db9979", "spark", "Updater.kt")) as f:
            kt = f.read()
        for must in ("/api/android/apk", "instanceFollowRedirects = false", "offer.sha", "info.packageName != ctx.packageName",
                     "longVersionCode <= BuildConfig.VERSION_CODE", "theirs.containsAll(own)", "PackageInstaller.SessionParams",
                     "f.delete()"):
            self.assertIn(must, kt)
        self.assertNotIn("github.com", kt)   # only the own Spark
        with open(os.path.join(root, "AndroidManifest.xml")) as f:
            man = f.read()
        self.assertIn("REQUEST_INSTALL_PACKAGES", man)
        self.assertIn('android:name=".InstallDone"\n            android:exported="false"', man)


if __name__ == "__main__":
    unittest.main()
