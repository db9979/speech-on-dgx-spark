"""Anrufe per Assistent (rufen.py, Dominik 2026-10-18): „Ruf Sabine an“ only by the panel's fixed rules from the
person's own words, off until the admin switches it on, nothing before the plain "Ja" on the same device, the call
starts on a device with a screen or waits for one tap after a note, „übers Telefon“ only on Android and only for one
contact of the own address book, never for guests or another voice, the Notaus stops it, and Live and journal with
numbers only. Push and contacts are replaced here; no test reads the clock for a rule (times are passed in)."""
import asyncio
import contextlib
import io
import json
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import anrufe  # noqa: E402
import chats  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import rufen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ANDROID = "Mozilla/5.0 (Linux; Android 15) SparkAndroid/1.4.2"
NOW = 1_800_000_000.0


def profile(name, pin="1357", headers=None):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app, headers=headers or {})
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    uid = c.get("/api/whoami").json()["profile"]["id"]
    c.put("/api/profile/settings", json={"pro_quiet": ""})   # quiet hours off: no test depends on the time of day
    return c, uid


def block(tc, uid, key, on=False):
    r = ADMIN.put(f"/api/admin/features/{key}/profiles/{uid}", json={"on": on})
    assert r.status_code == 200, r.text
    if not on:
        tc.addCleanup(block, tc, uid, key, True)


def ask(client, text, convo="r1"):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "convo": convo})
    assert r.status_code == 200, r.text
    return helpers.events(r)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def ctx(uid, client="", **kw):
    return dict({"who": profiles.by_id(uid), "own": True, "private": True, "src": client + ":c1", "client": client,
                 "app": False, "android": False}, **kw)


def journal(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        res = fn()
    return res, [x for x in out.getvalue().splitlines() if x.startswith("chats: call assistant")]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(chats=True, chats_calls=True, calls_assistant=True)
        rufen._ready.clear()
        rufen._pushed.clear()
        rufen._count.clear()   # the numbers of today start at zero for each test
        anrufe._calls.clear()
        anrufe._started.clear()
        self.sent = []

        async def send(uid, title, body, tag="", private=True, **kw):
            self.sent.append((uid, title, body, tag, kw.get("to")))
            return 1
        p = mock.patch("push.send", new=send)
        p.start()
        self.addCleanup(p.stop)
        r = mock.patch("push.reachable", return_value=True)
        r.start()
        self.addCleanup(r.stop)

    def tearDown(self):
        helpers.set_config(chats=False, chats_calls=False, calls_assistant=False)
        rufen._ready.clear()
        anrufe._calls.clear()


class Parse(unittest.TestCase):
    def test_only_a_plain_request_to_call(self):
        cases = {"Ruf Sabine an": ("Sabine", "audio"), "Ruf Sabine per Video an": ("Sabine", "video"),
                 "Videoanruf mit Sabine": ("Sabine", "video"), "Kannst du Sabine anrufen?": ("Sabine", "audio"),
                 "Ruf meine Mama übers Telefon an": ("Mama", "phone"), "Starte einen Videoanruf mit Thomas Müller":
                 ("Thomas Müller", "video"), "Call Sabine": ("Sabine", "audio"), "Video call Sabine": ("Sabine", "video"),
                 "Telefoniere mit Ben": ("Ben", "audio"), "Hey Spark, ruf Ben an": ("Ben", "audio")}
        for said, want in cases.items():
            self.assertEqual(rufen.parse(said), want, said)
        for no in ("Ruf mich um acht an", "Ruf alle an", "Wie kann ich Sabine anrufen?", "Ich will dich anrufen",
                   "Ruf Sabine an und sag ihr hallo", "Wann ruft Sabine an?", "", "x" * 200):
            self.assertIsNone(rufen.parse(no), no)


class Spark(Base):
    def test_off_until_the_admin_and_the_admin_blocks(self):
        a, ua = profile("Rufa Eins")
        _, ub = profile("Rufb Zwei")
        helpers.set_config(calls_assistant=False)
        ask(a, "Ruf Rufb an")
        self.assertIsNone(rufen.pending(ua))
        helpers.set_config(calls_assistant=True)
        block(self, ua, "anrufassistent")
        ask(a, "Ruf Rufb an", convo="r2")
        self.assertIsNone(rufen.pending(ua))

    def test_yes_starts_the_call_on_this_device(self):
        a, ua = profile("Rufc Drei")
        b, ub = profile("Rufd Vier")
        evs = ask(a, "Videoanruf mit Rufd")
        p = rufen.pending(ua)
        self.assertEqual((p["kind"], p["to"], p["video"]), ("spark", ub, True))
        last = helpers.LLM_CALLS[-1]
        self.assertIn("Soll ich Rufd Vier per Spark-Videoanruf anrufen", json.dumps(last, ensure_ascii=False))
        self.assertFalse(last.get("tools"))                     # a fixed rule: the model only says it
        self.assertFalse([e for e in evs if e["type"] == "anruf"])   # nothing before the yes
        evs = ask(a, "Ja, nur Sprache")
        ev = [e for e in evs if e["type"] == "anruf"]
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["id"], ev[0]["video"]), (chats.one_id(ua, ub), False))
        self.assertIsNone(rufen.pending(ua))
        self.assertEqual(a.get("/api/chats").json()["ruf"]["id"], ev[0]["id"])
        # the ordinary call from that chat takes the waiting one
        r = a.post("/api/anrufe/start", json={"id": ev[0]["id"], "video": False, "dev": "a1" * 6})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(a.get("/api/chats").json()["ruf"])

    def test_no_drops_it(self):
        a, ua = profile("Rufe Fuenf")
        _, ub = profile("Ruff Sechs")
        ask(a, "Ruf Ruff an")
        self.assertIsNotNone(rufen.pending(ua))
        evs = ask(a, "Nein")
        self.assertFalse([e for e in evs if e["type"] == "anruf"])
        self.assertIsNone(rufen.pending(ua))
        self.assertIsNone(rufen.ready_for(ua))

    def test_yes_only_on_the_same_device_and_conversation(self):
        a, ua = profile("Rufg Sieben")
        _, ub = profile("Rufh Acht")
        ask(a, "Ruf Rufh an", convo="x1")
        evs = ask(a, "Ja", convo="x2")
        self.assertFalse([e for e in evs if e["type"] == "anruf"])

    def test_who_takes_no_calls_is_named_not_called(self):
        a, ua = profile("Rufi Neun")
        _, ub = profile("Rufj Zehn")
        block(self, ub, "anrufe")
        ask(a, "Ruf Rufj an")
        self.assertIsNone(rufen.pending(ua))
        self.assertIn("nimmt gerade keine", json.dumps(helpers.LLM_CALLS[-1], ensure_ascii=False))

    def test_never_for_guests_or_another_voice(self):
        _, ua = profile("Rufk Elf")
        _, ub = profile("Rufl Zwoelf")
        self.assertIsNone(run(rufen.answer(dict(ctx(ua), who=None), "Ruf Rufl an")))
        self.assertIsNone(run(rufen.answer(dict(ctx(ua), own=False), "Ruf Rufl an")))
        self.assertIsNone(run(rufen.answer(dict(ctx(ua, "telegram"), private=False), "Ruf Rufl an")))
        self.assertIsNone(rufen.pending(ua))

    def test_notaus_stops_it(self):
        _, ua = profile("Rufm Dreizehn")
        _, ub = profile("Rufn Vierzehn")
        c = ctx(ua)
        self.assertIn("Vorschlag", run(rufen.answer(c, "Ruf Rufn an"))["call"]["name"])
        with mock.patch("notaus.refuse", return_value=True):
            res = run(rufen.answer(c, "Ja"))
        self.assertIn("nicht möglich", res["call"]["name"])
        self.assertIsNone(rufen.ready_for(ua))


class Away(Base):
    def test_from_a_speaker_a_note_and_a_bar(self):
        a, ua = profile("Rufo Fuenfzehn")
        _, ub = profile("Rufp Sechzehn")
        c = ctx(ua, "speaker")
        run(rufen.answer(c, "Ruf Rufp an"))
        res, lines = journal(lambda: run(rufen.answer(c, "Ja")))
        self.assertNotIn("event", res)
        self.assertIn("aufs Handy", res["system"])
        self.assertEqual([(s[0], s[3], s[4]) for s in self.sent], [(ua, "ruf", "every")])
        self.assertIn("Rufp Sechzehn anrufen", self.sent[0][1])
        self.assertTrue(any("sent to devices" in x for x in lines))
        self.assertEqual(a.get("/api/chats").json()["ruf"]["id"], chats.one_id(ua, ub))
        # „Nicht jetzt“: gone on every device
        self.assertEqual(a.delete("/api/anrufe/bereit").json(), {"ok": True})
        self.assertIsNone(a.get("/api/chats").json()["ruf"])

    def test_the_bar_waits_only_a_few_minutes(self):
        _, ua = profile("Rufq Siebzehn")
        rufen._ready[ua] = {"id": "c" + "1" * 12, "name": "X", "video": False, "t": NOW}
        self.assertIsNotNone(rufen.ready_for(ua, now=NOW + rufen.READY_SECONDS - 1))
        self.assertIsNone(rufen.ready_for(ua, now=NOW + rufen.READY_SECONDS))

    def test_notes_per_hour(self):
        _, ua = profile("Rufr Achtzehn")
        p = {"name": "X", "video": False}
        for i in range(rufen.PUSH_PER_HOUR):
            self.assertEqual(run(rufen._push(ua, p, now=NOW + i)), 1)
        self.assertEqual(run(rufen._push(ua, p, now=NOW + 10)), 0)
        self.assertEqual(run(rufen._push(ua, p, now=NOW + 3601)), 1)

    def test_bar_endpoint_needs_the_own_login(self):
        r = TestClient(panel.app).delete("/api/anrufe/bereit")
        self.assertIn(r.status_code, (401, 403))


class Phone(Base):
    CARD = {"name": "Mama Muster", "phones": [["Festnetz", "0711 123456"], ["Handy", "+49 171 2345678"]]}

    def setUp(self):
        super().setUp()
        for name, val in (("contacts.usable", mock.MagicMock(return_value=True)),
                          ("contacts.search", mock.MagicMock(side_effect=lambda uid, q, limit=5:
                                                             [self.CARD] if "mama" in q.lower() else []))):
            p = mock.patch(name, new=val)
            p.start()
            self.addCleanup(p.stop)

    def test_android_dials_after_the_yes(self):
        a, ua = profile("Ruft Neunzehn", headers={"User-Agent": ANDROID})
        ask(a, "Ruf Mama übers Telefon an")
        p = rufen.pending(ua)
        self.assertEqual((p["kind"], p["number"]), ("phone", "+49 171 2345678"))   # the mobile number first
        evs = ask(a, "Ja")
        self.assertEqual([e["number"] for e in evs if e["type"] == "waehlen"], ["+49 171 2345678"])
        # the Android app's own assistant sheet too
        _, ub = profile("Rufu Zwanzig")
        c = ctx(ub, "android")
        run(rufen.answer(c, "Ruf Mama an"))
        self.assertEqual(run(rufen.answer(c, "Ja"))["event"]["type"], "waehlen")

    def test_never_on_other_devices(self):
        a, ua = profile("Rufv Einundzwanzig")
        ask(a, "Ruf Mama übers Telefon an")                          # a browser: no phone here
        self.assertIsNone(rufen.pending(ua))
        self.assertIsNone(run(rufen.answer(ctx(ua, "iphone", app=True), "Ruf Mama an")))   # the iPhone's own way
        self.assertIn("nicht möglich", run(rufen.answer(ctx(ua, "speaker"), "Ruf Mama übers Telefon an"))["call"]["name"])

    def test_only_one_contact_with_a_number(self):
        _, ua = profile("Rufw Zweiundzwanzig")
        res = run(rufen.answer(ctx(ua, "android"), "Ruf Niemand übers Telefon an"))
        self.assertIn("niemanden", res["system"])
        self.assertIsNone(rufen.pending(ua))


class LiveAndLogs(Base):
    def test_numbers_only(self):
        _, ua = profile("Rufx Dreiundzwanzig")
        _, ub = profile("Rufy Vierundzwanzig")
        c = ctx(ua)
        _, lines = journal(lambda: run(rufen.answer(c, "Ruf Rufy an")))
        self.assertTrue(lines and all("Rufy" not in x and ub not in x for x in lines))
        run(rufen.answer(c, "Ja"))
        live = rufen.for_live()
        self.assertEqual((live["asked"], live["started"], live["waiting"]), (1, 1, 1))
        got = chats.for_live()
        self.assertEqual((got["call_assist"], got["call_assist_started"]), (True, 1))
        helpers.set_config(calls_assistant=False)
        self.assertEqual(rufen.for_live(), {"on": False})

    def test_every_refusal_logs(self):
        _, ua = profile("Rufz Fuenfundzwanzig")
        _, lines = journal(lambda: run(rufen.answer(ctx(ua, "speaker"), "Ruf Mama übers Telefon an")))
        self.assertTrue(any("refused" in x for x in lines))


if __name__ == "__main__":
    unittest.main()
