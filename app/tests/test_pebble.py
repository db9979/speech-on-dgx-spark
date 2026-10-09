"""Pebble watch (pebblewatch.py, watch.py): pairing with a setup code, the key's narrow scope, the log line."""
import json
import unittest

from tests import helpers

helpers.start()
import guard  # noqa: E402
import panel  # noqa: E402
import pebblewatch  # noqa: E402
import profiles  # noqa: E402
import watch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
BASE = "http://tars:31080"


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def code_of(setup):
    base, code = setup.split("#pebble=")
    assert base == BASE, setup
    return code


class Pebble(unittest.TestCase):
    def setUp(self):
        helpers.set_config(pebble=True)
        pebblewatch._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:   # every test client shares one address
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(pebble=False, face="robot")

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["pebble"], False)
        self.assertIs(profiles.SETTINGS["pebble_on"][0], False)

    def test_pairing_needs_both_switches_and_works_once(self):
        a = profile("Paula")
        self.assertEqual(a.post("/api/profile/pebble/pair", json={"base": BASE}).status_code, 403)
        a.put("/api/profile/settings", json={"pebble_on": True})
        helpers.set_config(pebble=False)
        self.assertEqual(a.post("/api/profile/pebble/pair", json={"base": BASE}).status_code, 403)
        helpers.set_config(pebble=True, face="comic")
        for bad in ("tars", "http://tars/panel", "javascript:alert(1)", "http://a b"):
            self.assertEqual(a.post("/api/profile/pebble/pair", json={"base": bad}).status_code, 400, bad)
        self.assertEqual(a.post("/api/profile/pebble/pair", content="x" * 2000).status_code, 413)
        code = code_of(a.post("/api/profile/pebble/pair", json={"base": BASE}).json()["setup"])
        app = TestClient(panel.app)
        r = app.post("/api/pebble/pair", json={"code": code})
        self.assertEqual(r.status_code, 200, r.text)
        # the watch shows the face the admin picked
        self.assertEqual((r.json()["profile"], r.json()["face"]), ("Paula", "comic"))
        token = r.json()["token"]
        self.assertEqual(app.post("/api/pebble/pair", json={"code": code}).status_code, 400)
        self.assertNotIn(token, json.dumps(profiles._load()))   # only the hash is kept
        self.assertEqual(len(a.get("/api/profile/pebble").json()["watches"]), 1)

    def test_code_expires(self):
        profile("Pia")
        uid = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == "Pia")
        code = pebblewatch.new_code(uid, now=1000.0)
        self.assertIsNone(pebblewatch.take_code(code, now=1000.0 + pebblewatch.CODE_SECONDS + 1))
        code = pebblewatch.new_code(uid, now=2000.0)
        self.assertEqual(pebblewatch.take_code(code, now=2010.0), uid)
        self.assertIsNone(pebblewatch.take_code("../" * 10))

    def test_key_only_reaches_the_watch_paths(self):
        a = profile("Pepe")
        a.put("/api/profile/settings", json={"pebble_on": True})
        code = code_of(a.post("/api/profile/pebble/pair", json={"base": BASE}).json()["setup"])
        app = TestClient(panel.app)
        h = {"X-Speech-Device": app.post("/api/pebble/pair", json={"code": code}).json()["token"]}
        helpers.set_config(public=False)
        try:
            self.assertEqual(app.get("/api/watch/poll?id=nope", headers=h).status_code, 404)   # in, but no such answer
            self.assertEqual(app.post("/api/chat", json={"messages": [{"role": "user", "content": "Hi"}]},
                                      headers=h).status_code, 401)
            self.assertEqual(app.post("/api/siri/ask", json={"text": "Hi"}, headers=h).status_code, 401)
            self.assertEqual(app.get("/api/profile/settings", headers=h).status_code, 401)
            self.assertEqual(app.post("/api/profile/pebble/pair", json={"base": BASE}, headers=h).status_code, 401)
            # switched off: the key stops at once (profile switch, then admin switch)
            a.put("/api/profile/settings", json={"pebble_on": False})
            self.assertEqual(app.get("/api/watch/poll?id=nope", headers=h).status_code, 401)
            a.put("/api/profile/settings", json={"pebble_on": True})
            helpers.set_config(pebble=False)
            self.assertEqual(app.get("/api/watch/poll?id=nope", headers=h).status_code, 401)
        finally:
            helpers.set_config(public=True)

    def test_report_line_only_numbers_and_fixed_words(self):
        job = watch.Job(speak=True)
        job.first_text = job.start + 1.2
        line = watch.report_line(job, {"dictation_ms": 2100, "text_ms": "1800", "audio_ms": -5, "done_ms": 10 ** 9,
                                       "retries": 3, "chunk": 3800, "stalls": "2", "outcome": "<script>"})
        self.assertTrue(line.startswith("watch: zeit Diktat 2.1 s"), line)
        self.assertIn("erster Text auf der Uhr 1.8 s", line)
        self.assertIn("Spark: Text 1.2 s, Ton –", line)
        self.assertIn("fertig 600.0 s", line)
        self.assertIn("Aussetzer 2 ·", line)
        self.assertTrue(line.endswith("failed: unbekannt"), line)
        self.assertNotIn("<script>", line)
        # once per answer
        watch.JOBS[job.id] = job
        try:
            c = TestClient(panel.app)
            self.assertTrue(c.post("/api/watch/report", json={"id": job.id, "outcome": "ok"}).json()["ok"])
            self.assertFalse(c.post("/api/watch/report", json={"id": job.id, "outcome": "ok"}).json()["ok"])
            self.assertEqual(c.post("/api/watch/report", content="x" * 2000).status_code, 413)
        finally:
            watch.JOBS.pop(job.id, None)

    def test_qr_leads_to_the_app_file(self):
        a = profile("Pina")
        r = a.get("/api/profile/pebble/qr", params={"base": BASE})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["url"], BASE + "/pebble/speech-spark.pbw")
        self.assertIn("<svg", r.json()["qr"])
        for bad in ("javascript:alert(1)", "http://tars/x", "http://a\"><b"):
            self.assertEqual(a.get("/api/profile/pebble/qr", params={"base": bad}).status_code, 400, bad)
        helpers.set_config(pebble=False)
        self.assertEqual(a.get("/api/profile/pebble/qr", params={"base": BASE}).status_code, 403)

    def test_served_app_and_its_version_note(self):
        import zipfile
        with zipfile.ZipFile(pebblewatch.APP_FILE) as z:
            label = json.loads(z.read("appinfo.json"))["versionLabel"]
            js = z.read("pebble-js-app.js").decode()
        # the phone part tells the Spark its version; it must be the one the file says
        self.assertIn(f"var APP_VERSION = '{label}';", js)
        self.assertEqual(pebblewatch.app_version(), label)
        self.assertFalse(pebblewatch.newer_app(label))
        self.assertTrue(pebblewatch.newer_app("1.0.0"))
        self.assertFalse(pebblewatch.newer_app("99.0.0"))
        for odd in (None, "", "1.x", "<b>", 3, "1.2.3.4"):
            self.assertFalse(pebblewatch.newer_app(odd), odd)
        self.assertEqual(TestClient(panel.app).get("/pebble/speech-spark.pbw").status_code, 200)


if __name__ == "__main__":
    unittest.main()
