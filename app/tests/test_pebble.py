"""Pebble watch (pebblewatch.py, watch.py): pairing with a setup code, the key's narrow scope, the log line."""
import asyncio
import json
import time
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
    base, code = setup.split("&aussen=")[0].split("#pebble=")
    assert base == BASE, setup
    return code


class Pebble(unittest.TestCase):
    def setUp(self):
        helpers.set_config(pebble=True, deny={})
        pebblewatch._pending.clear()
        for k in [k for k in guard._rate if k[0] == "pair"]:   # every test client shares one address
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(pebble=False, face="robot", deny={}, pebble_follow=False, pebble_quick=False,
                           pebble_remind=False, pebble_face=False, pebble_day=False, pebble_alerts=False,
                           pebble_note=False, pebble_place=False)

    def watch_of(self, name):
        """A paired watch of a new profile: (its client, the key header, the profile's id)."""
        a = profile(name)
        code = code_of(a.post("/api/profile/pebble/pair", json={"base": BASE}).json()["setup"])
        app = TestClient(panel.app)
        h = {"X-Speech-Device": app.post("/api/pebble/pair", json={"code": code}).json()["token"]}
        uid = next(u["id"] for u in profiles.names() if u["name"] == name)
        for k in [k for k in guard._rate if k[0] in ("watchsync", "watchrem")]:
            guard._rate.pop(k, None)
        return a, app, h, uid

    def test_off_by_default(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["pebble"], False)
        self.assertNotIn("pebble_on", profiles.SETTINGS)   # no profile switch: released by the admin, it works
        with open(helpers.APP + "/config.default.json") as f:
            chat = json.load(f)["chat"]
        for key in ("pebble_follow", "pebble_quick", "pebble_remind", "pebble_face", "pebble_day", "pebble_alerts",
                    "pebble_note", "pebble_place"):   # each extra its own admin switch, off
            self.assertIs(chat[key], False, key)
            self.assertNotIn(key, profiles.SETTINGS)

    def test_second_address_only_https(self):
        a = profile("Pebla")
        setup = a.post("/api/profile/pebble/pair", json={"base": BASE, "out": "https://spark.example.org"}).json()["setup"]
        self.assertTrue(setup.endswith("&aussen=https://spark.example.org"), setup)
        self.assertTrue(code_of(setup))
        for bad in ("http://spark.example.org", "https://spark.example.org/x", "javascript:alert(1)", "https://a b"):
            r = a.post("/api/profile/pebble/pair", json={"base": BASE, "out": bad})
            self.assertEqual(r.status_code, 400, bad)   # the key never goes through the internet without https
        self.assertNotIn("aussen", a.post("/api/profile/pebble/pair", json={"base": BASE}).json()["setup"])

    def test_sync_sends_only_what_the_admin_released(self):
        a, app, h, uid = self.watch_of("Pebline")
        r = app.get("/api/watch/sync", headers=h).json()
        self.assertEqual(r, {"quick": [], "agenda": None, "follow": False, "day": False, "note": False, "place": False})   # all off: nothing on the watch
        self.assertEqual(a.put("/api/profile/pebble/quick", json={"quick": ["Licht an"]}).status_code, 403)
        helpers.set_config(pebble_quick=True, pebble_remind=True, pebble_follow=True)
        for bad in ({"quick": "Licht an"}, {"quick": ["x" * 61]}, {"quick": [f"Satz {i}" for i in range(13)]}):
            self.assertEqual(a.put("/api/profile/pebble/quick", json=bad).status_code, 400, bad)
        self.assertEqual(a.put("/api/profile/pebble/quick", content="x" * 5000).status_code, 413)
        r = a.put("/api/profile/pebble/quick", json={"quick": [" Licht\tan ", "Licht an", "Wetter morgen", ""]})
        self.assertEqual(r.json()["quick"], ["Licht an", "Wetter morgen"])   # trimmed, doubles and empty lines gone
        self.assertEqual(app.put("/api/profile/pebble/quick", json={"quick": []}, headers=h).status_code, 401)
        now = time.time() * 1000
        profiles.add_reminder(uid, "Tee\nfertig", now + 300_000, made=now - 60_000)
        profiles.add_reminder(uid, "Müll", now + 86400_000, "weekly")
        profiles.add_reminder(uid, "viel später", now + 40 * 86400_000)
        r = app.get("/api/watch/sync", headers=h).json()
        self.assertEqual(r["quick"], ["Licht an", "Wetter morgen"])
        self.assertTrue(r["follow"])
        self.assertEqual([(x["text"], x["rep"]) for x in r["agenda"]], [("Tee fertig", 0), ("Müll", 1)])
        self.assertEqual(r["agenda"][0]["due"] - r["agenda"][0]["made"], 360)   # seconds: the ring of the timer
        self.assertEqual(pebblewatch.held(uid), {x["id"] for x in r["agenda"]})
        helpers.set_config(reminders=False)   # the reminders themselves off: none on the watch either
        try:
            self.assertIsNone(app.get("/api/watch/sync", headers=h).json()["agenda"])
            self.assertEqual(pebblewatch.held(uid), frozenset())
        finally:
            helpers.set_config(reminders=True)
        self.assertEqual(TestClient(panel.app).get("/api/watch/sync").status_code, 401)

    def test_reminder_actions_from_the_watch(self):
        _, app, h, uid = self.watch_of("Pebbo")
        now = time.time() * 1000
        x = profiles.add_reminder(uid, "Tee", now - 1000)
        self.assertEqual(app.post("/api/watch/reminder", json={"id": x["id"], "act": "played"}, headers=h).status_code, 403)
        helpers.set_config(pebble_remind=True)
        for bad in ({"id": x["id"], "act": "delete"}, {"id": "../x", "act": "played"}, {"act": "played"}):
            self.assertEqual(app.post("/api/watch/reminder", json=bad, headers=h).status_code, 400, bad)
        r = app.post("/api/watch/reminder", json={"id": x["id"], "act": "played"}, headers=h).json()
        self.assertTrue(r["ok"])
        self.assertEqual(profiles.reminders(uid), [])   # taken: no other device rings it again
        self.assertFalse(app.post("/api/watch/reminder", json={"id": x["id"], "act": "played"}, headers=h).json()["ok"])
        # Später: taken already, the watch still knows the text; it comes back in ten minutes
        r = app.post("/api/watch/reminder", json={"id": x["id"], "act": "snooze", "text": "Tee"}, headers=h).json()
        self.assertTrue(r["ok"])
        (again,) = profiles.reminders(uid)
        self.assertEqual(again["text"], "Tee")
        self.assertAlmostEqual(again["due"], now + pebblewatch.SNOOZE_MS, delta=30_000)
        self.assertEqual([y["id"] for y in r["agenda"]], [again["id"]])
        # +1 Minute on a running timer, then stopped on the watch
        r = app.post("/api/watch/reminder", json={"id": again["id"], "act": "plus"}, headers=h).json()
        (longer,) = profiles.reminders(uid)
        self.assertEqual(longer["due"], again["due"] + pebblewatch.PLUS_MS)
        self.assertEqual(longer["made"], again["made"])
        self.assertTrue(app.post("/api/watch/reminder", json={"id": longer["id"], "act": "cancel"}, headers=h).json()["ok"])
        self.assertEqual(profiles.reminders(uid), [])
        # Serie beenden: the ring is taken and its next time goes as well
        rep = profiles.add_reminder(uid, "Müll", now - 1000, "daily")
        profiles.add_reminder(uid, "anderes", now + 3600_000)
        self.assertTrue(app.post("/api/watch/reminder", json={"id": rep["id"], "act": "stop"}, headers=h).json()["ok"])
        self.assertEqual([y["text"] for y in profiles.reminders(uid)], ["anderes"])
        profiles.remove_reminders(uid, {y["id"] for y in profiles.reminders(uid)})

    def test_push_waits_for_the_watch(self):
        _, app, h, uid = self.watch_of("Pebolly")
        helpers.set_config(pebble_remind=True)
        now = time.time() * 1000
        x = profiles.add_reminder(uid, "Tee", now - 1000)
        self.assertEqual(app.get("/api/watch/sync", headers=h).status_code, 200)
        self.assertIn(x["id"], pebblewatch.held(uid))
        import push
        orig = push.reachable
        push.reachable = lambda *a, **k: True
        try:
            asyncio.run(push.due_reminders())
            self.assertEqual([y["id"] for y in profiles.reminders(uid)], [x["id"]])   # the watch rings it first
            pebblewatch._held.pop(uid, None)
            asyncio.run(push.due_reminders())
            self.assertEqual(profiles.reminders(uid), [])   # no watch holds it: push takes it as before
        finally:
            push.reachable = orig

    def test_follow_ups_only_short_questions(self):
        raw = ["Und morgen?", "ja", "Lösch alle Mails", "Ruf https://x.de auf", "Code 123456", "**Und übermorgen?**",
               "und morgen?", "x" * 60, 7, "Wie spät ist es?", "Erinner mich um 17 Uhr"]
        self.assertEqual(watch.follow_clean(raw, "Wie spät ist es?"), ["Und morgen?", "Und übermorgen?",
                                                                        "Erinner mich um 17 Uhr"])
        self.assertEqual(watch.follow_clean("kein Array", "x"), [])
        job = watch.Job(speak=False)
        job.text = "Es ist sonnig."
        self.assertEqual(watch.follow_skip(job, "Wie ist das Wetter?"), "")
        self.assertEqual(watch.follow_skip(job, "ja"), "fixed answer")
        job.mark = "mail"
        self.assertEqual(watch.follow_skip(job, "Neue Mails?"), "outside text")   # never after text from outside
        job.mark, job.proposal = None, "Soll ich das Licht ausschalten?"
        self.assertEqual(watch.follow_skip(job, "Licht"), "proposal")
        job.proposal, job.error = "", "Fehler"
        self.assertEqual(watch.follow_skip(job, "x"), "error")

    def test_poll_waits_for_the_follow_ups(self):
        async def go():
            job = watch.Job(speak=False)
            job.text, job.done, job.done_at, job.follow_wait = "Antwort", True, time.time(), True
            r = await watch.poll(job, 0, 0, wait=0.2)
            self.assertEqual((r["audio_end"], r["done"]), (True, False))   # text out, the follow-ups still coming
            self.assertNotIn("follow", r)
            job.follow, job.follow_wait = ["Und morgen?"], False
            job.ping()
            r = await watch.poll(job, len(job.text), 0, wait=0.2)
            self.assertTrue(r["done"])
            self.assertEqual((r["follow"], r["proposal"], r["agenda"]), (["Und morgen?"], "", False))
            job2 = watch.Job(speak=False)   # a turn that never clears the wait does not hold the end back
            job2.text, job2.done, job2.follow_wait = "x", True, True
            job2.done_at = time.time() - watch.FOLLOW_TIMEOUT - 3
            self.assertTrue((await watch.poll(job2, 1, 0, wait=0.2))["done"])
        asyncio.run(go())

    def test_face_shows_only_released_parts(self):
        a, app, h, uid = self.watch_of("Pebfa")
        self.assertEqual(app.get("/api/watch/blick", headers=h).status_code, 403)
        self.assertEqual(a.get("/api/profile/pebble/qr", params={"base": BASE, "app": "face"}).status_code, 403)
        helpers.set_config(pebble_face=True)
        self.assertTrue(a.get("/api/profile/pebble/qr", params={"base": BASE, "app": "face"}).json()["url"]
                        .endswith("/pebble/spark-zifferblatt.pbw"))
        now = time.time() * 1000
        profiles.add_reminder(uid, "Tee\x07 fertig " + "x" * 80, now + 600_000)
        import dienstwacht
        orig = dienstwacht.alerts, dienstwacht.recipients
        dienstwacht.alerts = lambda now=None: [{"kind": "service", "level": "bad", "go": "",
                                                "text": "Gerade eingeschränkt: Sprachmodell antwortet seit 10:00 nicht."}]
        dienstwacht.recipients = lambda: [uid]
        try:
            r = app.get("/api/watch/blick", headers=h).json()
            self.assertIsNone(r["alert"])   # notes for admins are their own switch
            self.assertTrue(r["rem"]["text"].startswith("Tee fertig"))
            self.assertLessEqual(len(r["rem"]["text"]), pebblewatch.BLICK_TITLE)
            helpers.set_config(pebble_alerts=True, svc_watch=True)
            self.assertEqual(app.get("/api/watch/blick", headers=h).json()["alert"],
                             "Sprachmodell antwortet seit 10:00 nicht.")
            dienstwacht.recipients = lambda: []   # not an admin who gets the notes: nothing
            self.assertIsNone(app.get("/api/watch/blick", headers=h).json()["alert"])
        finally:
            dienstwacht.alerts, dienstwacht.recipients = orig
            helpers.set_config(svc_watch=False)
            profiles.remove_reminders(uid, {x["id"] for x in profiles.reminders(uid)})
        self.assertEqual(TestClient(panel.app).get("/api/watch/blick").status_code, 401)
        self.assertEqual(TestClient(panel.app).get("/pebble/spark-zifferblatt.pbw").status_code, 200)

    def test_day_and_week_are_fixed_sentences(self):
        _, app, h, uid = self.watch_of("Pebta")
        self.assertEqual(app.get("/api/watch/brief", params={"art": "tag"}, headers=h).status_code, 403)
        helpers.set_config(pebble_day=True)
        self.assertEqual(app.get("/api/watch/brief", params={"art": "jahr"}, headers=h).status_code, 400)
        now = time.time()
        profiles.add_reminder(uid, "Müll raus", (now + 120) * 1000)
        profiles.remember(uid, "Das Auto steht auf Ebene 3", src="said")
        try:
            day = app.get("/api/watch/brief", params={"art": "tag", "tz": "Europe/Berlin"}, headers=h).json()["lines"]
            self.assertTrue(any("Müll raus" in x and x.startswith("⏰ ") for x in day), day)
            week = app.get("/api/watch/brief", params={"art": "woche"}, headers=h).json()["lines"]
            self.assertTrue(week[0].startswith("Letzte 7 Tage: "), week)
            self.assertIn("1 neue Dinge gemerkt.", week)
            self.assertIn("1 Erinnerungen in den nächsten 7 Tagen.", week)
        finally:
            profiles.remove_reminders(uid, {x["id"] for x in profiles.reminders(uid)})

    def test_quick_note_goes_to_memory(self):
        _, app, h, uid = self.watch_of("Pebme")
        body = {"text": "Das Fahrrad steht am Bahnhof", "lat": 48.13743, "lon": 11.57549}
        self.assertEqual(app.post("/api/watch/merken", json=body, headers=h).status_code, 403)
        helpers.set_config(pebble_note=True)
        self.assertEqual(app.post("/api/watch/merken", json={"text": " "}, headers=h).status_code, 400)
        self.assertEqual(app.post("/api/watch/merken", content="x" * 2000, headers=h).status_code, 413)
        r = app.post("/api/watch/merken", json=body, headers=h).json()
        self.assertEqual(r["text"], "Das Fahrrad steht am Bahnhof")   # the place is its own switch
        helpers.set_config(pebble_place=True)
        r = app.post("/api/watch/merken", json=dict(body, text="Schlüssel liegt unter der Matte"), headers=h).json()
        self.assertEqual(r["text"], "Schlüssel liegt unter der Matte (Ort 48.137, 11.575)")
        r = app.post("/api/watch/merken", json={"text": "Ohne Ort", "lat": "x", "lon": 999}, headers=h).json()
        self.assertEqual(r["text"], "Ohne Ort")
        self.assertIn("Schlüssel liegt unter der Matte (Ort 48.137, 11.575)", [x["text"] for x in profiles.memory(uid)])
        helpers.set_config(memory=False)   # the memory itself off: nothing kept
        try:
            self.assertEqual(app.post("/api/watch/merken", json=body, headers=h).status_code, 403)
        finally:
            helpers.set_config(memory=True)

    def test_run_keeps_proposal_and_reminder_marks(self):
        class Stream:
            async def _it(self):
                for ev in ({"type": "text", "delta": "Soll ich?"}, {"type": "proposal", "text": "**Licht** aus?"},
                           {"type": "reminder", "action": "set"}):
                    yield "data:" + json.dumps(ev) + "\n"
            body_iterator = property(lambda self: self._it())
        job = watch.Job(speak=False)
        asyncio.run(watch.run(job, Stream()))
        self.assertEqual((job.text, job.proposal, job.agenda, job.done), ("Soll ich?", "Licht aus?", True, True))

    def test_pairing_needs_both_switches_and_works_once(self):
        a = profile("Paula")
        uid = next(u["id"] for u in profiles.names() if u["name"] == "Paula")
        helpers.set_config(deny={"pebble": [uid]})   # the admin blocks this profile
        self.assertEqual(a.post("/api/profile/pebble/pair", json={"base": BASE}).status_code, 403)
        helpers.set_config(deny={})
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

    def test_admin_sees_it_fixed_and_cannot_move_it(self):
        a, _ = profile("Pius"), profile("Pia")
        code = code_of(a.post("/api/profile/pebble/pair", json={"base": BASE}).json()["setup"])
        self.assertEqual(TestClient(panel.app).post("/api/pebble/pair", json={"code": code}).status_code, 200)
        uid = next(u["id"] for u in profiles.names() if u["name"] == "Pius")
        other = next(u["id"] for u in profiles.names() if u["name"] == "Pia")
        dev = next(x for x in ADMIN.get("/api/admin/profiles").json()["devices"] if x["user"] == uid)
        self.assertEqual(dev["kind"], "watch")   # the panel shows it with the owner fixed, not as a choice
        r = ADMIN.put(f"/api/admin/devices/{dev['id']}", json={"user": other})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Pebble", r.text)
        key = ADMIN.post("/api/admin/devices", json={"name": "Skript", "user": uid}).json()["token"]
        self.assertTrue(key)
        own = next(x for x in ADMIN.get("/api/admin/profiles").json()["devices"] if x["name"] == "Skript")
        self.assertEqual(own["kind"], "")   # an own key the admin may move
        self.assertEqual(ADMIN.put(f"/api/admin/devices/{own['id']}", json={"user": other}).status_code, 200)

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
            # switched off: the key stops at once (the admin blocks the profile, then the admin switch)
            uid = next(u["id"] for u in profiles.names() if u["name"] == "Pepe")
            helpers.set_config(deny={"pebble": [uid]})
            self.assertEqual(app.get("/api/watch/poll?id=nope", headers=h).status_code, 503)   # "not now", pairing stays (V01.0.388)
            helpers.set_config(deny={})
            self.assertEqual(app.get("/api/watch/poll?id=nope", headers=h).status_code, 404)   # released: back at once
            helpers.set_config(pebble=False)
            self.assertEqual(app.get("/api/watch/poll?id=nope", headers=h).status_code, 503)
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
