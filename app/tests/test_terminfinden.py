"""Termin finden (Nextcloud-Ideen 3, terminfinden.py): free times of everybody in a chat as a poll.

- Off (chat.calendar_find, default off): the endpoints say no, the state says termin false.
- The search (pure, fixed days): only appointments with a time make busy; at most two times a day, never in the past,
  at most MAX_SLOTS; only times within the hours asked for.
- The endpoint answers only times and a count of members without a calendar, never a title of somebody else's
  appointment; only in a chat of this Spark.
- The poll: 2 to MAX_SLOTS times, art "termin", the title sealed; closing it enters the winning time for who asked and
  for everybody who voted for it, nobody else; without a vote nothing.
"""
import asyncio
import contextlib
import datetime
import io
import json
import os
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from tests import helpers

helpers.start()
import calendars  # noqa: E402
import chats  # noqa: E402
import panel  # noqa: E402
import terminfinden  # noqa: E402
import umfrage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TZ = ZoneInfo("Europe/Berlin")
DAY = datetime.date(2030, 3, 4)                    # a Monday far ahead, so no time of day changes a result
NOW = datetime.datetime(2030, 3, 1, 12, 0, tzinfo=TZ).timestamp()


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "2468"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "2468"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def at(d, h, m=0):
    return datetime.datetime.combine(DAY + datetime.timedelta(days=d), datetime.time(h, m), TZ)


class Suchen(unittest.TestCase):
    def test_rules(self):
        busy = [(at(0, 8), at(0, 10))]
        got = terminfinden.suchen(busy, DAY, 2, 60, 8, 20, TZ, NOW)
        self.assertEqual(got[0], (at(0, 10), at(0, 11)))                         # after the busy time
        self.assertEqual(got[1][0], at(0, 13))                                   # the second at least 2 h later
        self.assertEqual(got[2][0], at(1, 8))
        self.assertEqual(len(got), 4)                                            # two a day
        self.assertTrue(all(8 <= s.hour and e.hour <= 20 for s, e in got))
        self.assertEqual(terminfinden.suchen([(at(0, 0), at(0, 23, 59))], DAY, 1, 60, 8, 20, TZ, NOW), [])
        self.assertEqual(terminfinden.suchen([], DAY, 1, 60, 8, 20, TZ, at(0, 15).timestamp())[0][0], at(0, 15))   # never past
        self.assertEqual(len(terminfinden.suchen([], DAY, 14, 30, 8, 20, TZ, NOW)), terminfinden.MAX_SLOTS)

    def test_allday_is_never_busy(self):
        self.assertEqual(terminfinden._busy([{"start": at(0, 0), "end": at(1, 0), "allday": True},
                                             {"start": at(0, 9), "end": at(0, 10), "allday": False}]),
                         [(at(0, 9), at(0, 10))])


class TerminFinden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.aid = profile("Termin Tina")
        cls.b, cls.bid = profile("Termin Theo")
        cls.c, cls.cid_ = profile("Termin Toni")

    def setUp(self):
        helpers.keep_chat(self, "chats", "chats_groups", "chats_polls", "calendar", "calendar_find")
        helpers.set_config(chats=True, chats_groups=True, chats_polls=True, calendar=True, calendar_find=True)
        r = self.a.post("/api/chats/group", json={"name": "Treffen", "members": [self.bid, self.cid_]})
        self.assertEqual(r.status_code, 200, r.text)
        self.cid = r.json()["id"]
        self.cal = {self.aid: [{"start": at(0, 8), "end": at(0, 12), "allday": False, "title": "Geheimtermin Zahnarzt"}],
                    self.bid: [{"start": at(0, 12), "end": at(0, 14), "allday": False, "title": "Anderes"}]}

        async def events(uid, start, end, zone, shared=False, stale=False):
            return None if uid not in self.cal else (self.cal[uid], [])
        p = mock.patch.object(calendars, "events", new=events)
        p.start()
        self.addCleanup(p.stop)
        self.added = []

        async def add(uid, item, out=None, wait=True):
            self.added.append((uid, item["title"], item["start"][:16]))
            return "Kalender"
        q = mock.patch.object(calendars, "add_event", new=add)
        q.start()
        self.addCleanup(q.stop)

    def free(self, client=None, **kw):
        return (client or self.a).post("/api/chats/termin/frei", json=dict(
            {"id": self.cid, "from": str(DAY), "days": 1, "minutes": 60, "von": 8, "bis": 20, "tz": "Europe/Berlin"}, **kw))

    def test_off(self):
        helpers.set_config(calendar_find=False)
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["calendar_find"], False)
        self.assertEqual(self.free().status_code, 403)
        self.assertFalse(self.a.get("/api/chats").json()["termin"])

    def test_free_times_only(self):
        r = self.free()
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["ohne"], 1)                                            # Toni has no calendar
        self.assertEqual([x["start"][11:16] for x in d["slots"]], ["14:00", "17:00"])
        self.assertEqual(d["slots"][0]["label"], "Mo 4.3. 14:00–15:00")
        self.assertNotIn("Geheimtermin", r.text)
        self.assertNotIn("Anderes", r.text)
        self.assertEqual(self.free(days=30).status_code, 400)
        self.assertEqual(self.free(minutes=45).status_code, 400)
        self.assertEqual(self.free(von=20, bis=8).status_code, 400)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.free()
        self.assertIn("calendar: find | members 3 | free 2 | without 1", out.getvalue())

    def test_poll_and_entry_for_who_voted(self):
        slots = self.free().json()["slots"]
        r = self.a.post("/api/chats/termin", json={"id": self.cid, "title": "Planung", "slots": slots[:1], "tz": "Europe/Berlin"})
        self.assertEqual(r.status_code, 400)                                      # 2 times at least
        r = self.a.post("/api/chats/termin", json={"id": self.cid, "title": "Planung", "slots": slots, "tz": "Europe/Berlin"})
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["item"]["id"]
        with open(chats._chat_file(self.cid), encoding="utf-8") as f:
            self.assertNotIn("Planung", f.read())                                 # the title sealed
        x = next(y for y in self.b.get("/api/chats/items", params={"id": self.cid}).json()["items"] if y["id"] == mid)
        self.assertEqual(x["text"], "📅 Planung")
        self.assertEqual(x["poll"]["art"], "termin")
        self.assertEqual(x["poll"]["opts"], ["Mo 4.3. 14:00–15:00", "Mo 4.3. 17:00–18:00"])
        self.b.post("/api/chats/poll/vote", json={"id": self.cid, "mid": mid, "picks": [1]})
        self.c.post("/api/chats/poll/vote", json={"id": self.cid, "mid": mid, "picks": [0]})
        self.a.post("/api/chats/poll/vote", json={"id": self.cid, "mid": mid, "picks": [1]})
        with mock.patch.object(terminfinden.core, "later", side_effect=asyncio.run):
            self.assertEqual(umfrage.schliessen(self.aid, self.cid, mid), 1)
        self.assertEqual(sorted(self.added), sorted([(self.aid, "Planung", "2030-03-04T17:00"),
                                                     (self.bid, "Planung", "2030-03-04T17:00")]))   # not Toni

    def test_nothing_without_a_vote(self):
        slots = self.free().json()["slots"]
        mid = self.a.post("/api/chats/termin", json={"id": self.cid, "title": "Leer", "slots": slots}).json()["item"]["id"]
        with mock.patch.object(terminfinden.core, "later", side_effect=asyncio.run):
            self.assertEqual(umfrage.schliessen(self.aid, self.cid, mid), -1)
        self.assertEqual(self.added, [])

    def test_live_numbers_only(self):
        v = terminfinden.for_live()
        self.assertEqual(set(v), {"on", "gesucht", "gestellt", "eingetragen"})
        self.assertIs(umfrage.ON_CLOSE["termin"], terminfinden._closed)


if __name__ == "__main__":
    unittest.main()
