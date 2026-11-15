"""Abwesenheit and Beschäftigt im Termin (Nextcloud-Ideen 1, abwesenheit.py): an entry from–until under Kalender → Einstellungen.

- Off (chat.away, default off): the endpoint says no, no calendar „Abwesenheit“, nobody is away.
- On: saved sealed (abwesenheit.bin, never plain text); wrong days are refused; the calendar shows one read-only
  all-day entry; the chats list and the chat show „abwesend bis …“ for the other one; a Spark call does not ring (a
  missed one at once); the mail thread's aktiv() gives {von, bis, text} only with „Mail-Antwort“; ON_CHANGE after
  each save and delete; deleting ends it everywhere.
Beschäftigt im Termin (chat.calendar_busy, off): only while an appointment with a time runs (never all day), busy
like the Begleiter's „Nicht stören“ (notes wait, one summary after), never over the Begleiter's own busy time; chats get
the word only. The appointments are given, the time is fixed.
The days are counted from today in both directions (from yesterday to tomorrow), so no time of day changes a result.
"""
import asyncio
import datetime
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import abwesenheit  # noqa: E402
import anrufe  # noqa: E402
import chats  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TODAY = datetime.date.today()
DAY = datetime.timedelta(days=1)
TZ = "Europe/Berlin"


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1357"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1357"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def entry(**kw):
    return dict({"von": str(TODAY - DAY), "bis": str(TODAY + DAY), "text": "Bin weg.", "vertretung": "Sabine",
                 "mail": False, "kalender": True, "tz": TZ}, **kw)


class Abwesenheit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Abwesend Alma")
        cls.b, cls.buid = profile("Abwesend Bruno")

    def setUp(self):
        helpers.keep_chat(self, "away", "chats", "chats_calls")
        helpers.set_config(away=True)
        self.changed = []
        abwesenheit.ON_CHANGE.append(self.changed.append)

    def tearDown(self):
        abwesenheit.ON_CHANGE.remove(self.changed.append)
        abwesenheit.STORE.forget(self.uid)

    def put(self, **kw):
        return self.c.put("/api/profile/abwesenheit", json=entry(**kw))

    def week(self):
        r = self.c.get("/api/profile/calendar/view", params={"start": str(TODAY - 3 * DAY), "days": 7, "tz": TZ})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_off(self):
        helpers.set_config(away=False)
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["away"], False)
        self.assertEqual(self.c.get("/api/profile/abwesenheit").status_code, 403)
        self.assertEqual(self.put().status_code, 403)
        abwesenheit.speichern(self.uid, entry())
        self.assertIsNone(abwesenheit.jetzt(self.uid))
        self.assertIsNone(profiles.away(self.uid))
        self.assertNotIn(abwesenheit.CAL, self.week().get("calendars", []))

    def test_wrong_days_refused(self):
        for kw in ({"von": "morgen"}, {"bis": str(TODAY - 2 * DAY)}, {"von": str(TODAY - 400 * DAY)},
                   {"von": str(TODAY - 9 * DAY), "bis": str(TODAY - 2 * DAY)}):
            self.assertEqual(self.put(**kw).status_code, 400, kw)
        self.assertIsNone(self.c.get("/api/profile/abwesenheit").json()["eintrag"])
        self.assertEqual(self.changed, [])

    def test_saved_sealed_and_deleted(self):
        r = self.put(text="x" * 5000, vertretung="  Sabine  ")
        self.assertEqual(r.status_code, 200, r.text)
        e = r.json()["eintrag"]
        self.assertEqual((e["von"], e["bis"], e["vertretung"], len(e["text"])),
                         (str(TODAY - DAY), str(TODAY + DAY), "Sabine", abwesenheit.MAX_TEXT))
        self.assertEqual(self.changed, [self.uid])
        with open(profiles._path(self.uid, abwesenheit.NAME)) as f:
            raw = f.read()
        self.assertNotIn("Sabine", raw)                       # sealed, never plain text
        self.assertEqual(self.c.get("/api/profile/abwesenheit").json()["eintrag"]["bis"], str(TODAY + DAY))
        self.assertEqual(self.c.delete("/api/profile/abwesenheit").status_code, 200)
        self.assertIsNone(self.c.get("/api/profile/abwesenheit").json()["eintrag"])
        self.assertIsNone(abwesenheit.jetzt(self.uid))
        self.assertEqual(self.changed, [self.uid, self.uid])

    def test_mail_interface(self):
        self.put()
        self.assertIsNone(abwesenheit.aktiv(self.uid))         # without „Mail-Antwort“
        self.put(mail=True)
        a = abwesenheit.aktiv(self.uid)
        self.assertEqual(set(a), {"von", "bis", "text"})
        self.assertEqual(a["text"], "Bin weg.")
        self.assertAlmostEqual(a["bis"] - a["von"], 3 * 86400, delta=3600)   # three whole days (one may change the clock)
        self.assertIsNone(abwesenheit.aktiv(self.uid, now=a["bis"]))    # the day after the last one: over
        self.assertIsNone(abwesenheit.aktiv(self.uid, now=a["von"] - 1))
        self.assertIsNone(abwesenheit.aktiv(self.buid))

    def test_calendar_entry_read_only(self):
        self.put()
        d = self.week()
        i = d["calendars"].index(abwesenheit.CAL)
        self.assertEqual(d["made"][str(i)], "abwesend")
        evs = [x for x in d["events"] if x["cal"] == i]
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["allday"])
        self.assertFalse(evs[0]["edit"])
        self.assertEqual(evs[0]["title"], "Abwesend · Vertretung Sabine")
        self.assertNotIn(i, d["edit"] + d["add"])
        self.put(kalender=False)
        self.assertNotIn(abwesenheit.CAL, self.week().get("calendars", []))

    def test_chats_and_calls(self):
        helpers.set_config(chats=True, chats_calls=True)
        r = self.b.post("/api/chats/open", json={"to": self.uid})
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["id"]
        self.b.post("/api/chats/send", json={"id": cid, "text": "Hallo"})
        self.put()
        self.assertIn("Abwesend Alma ist bis", abwesenheit.satz(self.uid))
        self.assertTrue(abwesenheit.satz(self.uid).endswith(", Vertretung Sabine."))
        self.assertEqual(self.b.get("/api/chats/items", params={"id": cid}).json().get("away"), str(TODAY + DAY))
        row = next(x for x in chats.listing(self.buid) if x["id"] == cid)
        self.assertEqual(row.get("away"), str(TODAY + DAY))
        self.assertNotIn("away", next(x for x in chats.listing(self.uid) if x["id"] == cid))   # Bruno is not away
        anrufe._calls.clear()
        with mock.patch.object(anrufe, "_quiet", return_value=False), \
                mock.patch.object(anrufe, "_push", new=mock.AsyncMock()), \
                mock.patch.object(chats, "_send_event") as ev:
            r = self.b.post("/api/anrufe/start", json={"id": cid, "video": False, "dev": "b2" * 6})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["state"], "missed")       # never rings while away
            self.assertFalse([c for c in ev.call_args_list if c.args[1].get("type") == "call"])
        anrufe._calls.clear()
        self.c.delete("/api/profile/abwesenheit")
        self.assertNotIn("away", next(x for x in chats.listing(self.buid) if x["id"] == cid))

    def test_hooks_registered_once(self):
        import calendars
        self.assertEqual(calendars.EXTRA.count(abwesenheit.kalender), 1)
        self.assertEqual(profiles.AWAY.count(abwesenheit.away), 1)



class Beschaeftigt(unittest.TestCase):
    NOW = 1773230400                        # 2026-03-11 12:00 UTC

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Termin Tilda")

    def setUp(self):
        import begleiter
        import calendars
        self.b, self.cal = begleiter, calendars
        helpers.keep_chat(self, "calendar_busy", "calendar")
        helpers.set_config(calendar_busy=True, calendar=True)
        self.evs = []
        p = mock.patch.object(calendars, "events", new=mock.AsyncMock(side_effect=lambda *a, **k: (self.evs, [])))
        p.start()
        self.addCleanup(p.stop)
        self.sent = []
        r = mock.patch.object(begleiter, "release", new=mock.AsyncMock(side_effect=lambda uid, held: self.sent.append(held)))
        r.start()
        self.addCleanup(r.stop)
        u = mock.patch.dict(calendars._used, {self.uid: self.NOW}, clear=True)   # only this profile is looked at
        u.start()
        self.addCleanup(u.stop)

    def tearDown(self):
        self.b._quiet.pop(self.uid, None)
        abwesenheit._termin.discard(self.uid)

    def at(self, h, m=0):
        return datetime.datetime(2026, 3, 11, h, m, tzinfo=datetime.timezone.utc)

    def tick(self, plus=0):
        return asyncio.run(abwesenheit.minute(self.NOW + plus))

    def test_busy_only_in_an_appointment_with_a_time(self):
        self.evs = [{"start": self.at(0), "end": self.at(23, 59), "allday": True}]
        self.tick()
        self.assertFalse(self.b.busy(self.uid, self.NOW))
        self.evs = [{"start": self.at(11, 30), "end": self.at(12, 30), "allday": False}]
        self.assertEqual(self.tick(), 1)
        self.assertEqual(self.b.quiet_why(self.uid, self.NOW), "termin")
        self.assertTrue(self.b.hold(self.uid, "Neue Mail", "pro-mail", now=self.NOW + 10))     # a note waits
        self.assertFalse(self.b.hold(self.uid, "Notaus", "notaus", now=self.NOW + 10))        # never held
        self.assertEqual(profiles.away(self.uid)["busy"], True)
        self.assertNotIn("11:30", profiles.away(self.uid)["satz"])
        self.evs = [{"start": self.at(11, 30), "end": self.at(12, 0, ), "allday": False}]
        self.tick(60)
        self.assertFalse(self.b.busy(self.uid, self.NOW + 60))
        self.assertEqual([h["held"] for h in self.sent], [["Neue Mail"]])                    # one summary after
        self.assertIsNone(profiles.away(self.uid))

    def test_off_never(self):
        helpers.set_config(calendar_busy=False)
        self.evs = [{"start": self.at(11), "end": self.at(13), "allday": False}]
        self.assertEqual(self.tick(), 0)
        self.assertFalse(self.b.busy(self.uid, self.NOW))

    def test_the_begleiters_own_busy_time_stays(self):
        self.b.set_busy(self.uid, True, "call", self.NOW)
        self.evs = [{"start": self.at(11), "end": self.at(13), "allday": False}]
        self.tick()
        self.assertEqual(self.b.quiet_why(self.uid, self.NOW), "call")
        self.evs = []
        self.tick(30)
        self.assertEqual(self.b.quiet_why(self.uid, self.NOW + 30), "call")   # never ended by the calendar


if __name__ == "__main__":
    unittest.main()
