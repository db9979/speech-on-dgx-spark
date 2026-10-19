"""Spark-Kalender Stufe 1 (kalenderspiegel.py, Dominik 2026-10-19 „1a 2a“): every CalDAV calendar has a copy on the
Spark; the first look fetches it whole, later ones ask the server only for what changed.

- The first look: sync-collection, then the objects in one multiget. Within SYNC_SECONDS no request at all.
- Later: only changed objects are fetched, deleted ones leave the copy; a server without sync-collection (or with a
  token it no longer knows) is compared by etags, and still only changed objects are fetched.
- On the disk only encrypted (no title readable in the file); read back after a restart and compared first.
- A period gets only objects that can touch it; a repeating appointment always.
- Removing the calendar entry or the profile deletes the copy. Live: numbers only.

The fake CalDAV server of helpers; fixed dates, the sync age is set by hand, no wall clock.
"""
import asyncio
import contextlib
import datetime
import io
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import calendars  # noqa: E402
import kalenderspiegel as ks  # noqa: E402

UTC = datetime.timezone.utc
EV = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:{uid}\r\n"
      "DTSTART:{day}T090000Z\r\nDTEND:{day}T100000Z\r\nSUMMARY:{title}\r\n{rule}END:VEVENT\r\nEND:VCALENDAR\r\n")
CID = "c0a1b2c3d"


def ev(uid, day, title, rule=""):
    return EV.format(uid=uid, day=day, title=title, rule=rule)


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = dict(helpers.CAL_EVENTS)
        helpers.CAL_EVENTS.clear()
        helpers.CAL_NOSYNC[0] = False
        helpers.CAL_SEEN.clear()
        ks.forget([CID])
        calendars._found.clear()
        self.d = {"id": CID, "name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/", "user": "k",
                  "password": "pw"}

    def tearDown(self):
        ks.forget([CID])
        helpers.CAL_EVENTS.clear()
        helpers.CAL_EVENTS.update(self.saved)
        helpers.CAL_NOSYNC[0] = False
        calendars._found.clear()

    def read(self, a="20260301", b="20260401"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            texts, _ = asyncio.run(calendars._fetch(self.d, datetime.datetime.strptime(a, "%Y%m%d").replace(tzinfo=UTC),
                                                   datetime.datetime.strptime(b, "%Y%m%d").replace(tzinfo=UTC)))
        self.log = out.getvalue()
        return sorted(re.search(r"SUMMARY:([^\r\n]*)", t).group(1) for t in texts)

    def older(self):
        """As if SYNC_SECONDS had passed."""
        for cal in ks._mem.get(CID, {}).values():
            cal["at"] -= ks.SYNC_SECONDS + 1

    def seen(self):
        out = [k for _, k in helpers.CAL_SEEN if k != "find"]
        helpers.CAL_SEEN.clear()
        return out


class Sync(Base):
    def test_first_whole_then_only_the_changes(self):
        helpers.CAL_EVENTS.update({"/dav/privat/a.ics": ev("a", "20260310", "Zahnarzt"),
                                   "/dav/privat/b.ics": ev("b", "20260312", "Elternabend")})
        self.assertEqual(self.read(), ["Elternabend", "Zahnarzt"])
        self.assertEqual(self.seen(), ["sync", "multiget"])
        self.assertIn("calendar: mirror full | 2 new or changed, 0 gone, 2 kept", self.log)
        self.assertEqual(self.read(), ["Elternabend", "Zahnarzt"])   # fresh: the copy answers, nobody is asked
        self.assertEqual(self.seen(), [])
        self.older()
        self.read()
        self.assertEqual(self.seen(), ["sync"])                      # nothing changed: no object fetched
        self.assertEqual(self.log, "")
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260311", "Zahnarzt neu")
        helpers.CAL_EVENTS.pop("/dav/privat/b.ics")
        self.older()
        self.assertEqual(self.read(), ["Zahnarzt neu"])
        self.assertEqual(self.seen(), ["sync", "multiget"])
        self.assertIn("calendar: mirror changed | 1 new or changed, 1 gone, 1 kept", self.log)

    def test_without_sync_collection_by_etags(self):
        helpers.CAL_NOSYNC[0] = True
        helpers.CAL_EVENTS.update({"/dav/privat/a.ics": ev("a", "20260310", "Zahnarzt"),
                                   "/dav/privat/b.ics": ev("b", "20260312", "Elternabend")})
        self.assertEqual(self.read(), ["Elternabend", "Zahnarzt"])
        self.assertEqual(self.seen(), ["sync", "etags", "multiget"])
        helpers.CAL_EVENTS["/dav/privat/b.ics"] = ev("b", "20260313", "Elternabend neu")
        self.older()
        self.assertEqual(self.read(), ["Elternabend neu", "Zahnarzt"])
        self.assertEqual(self.seen(), ["sync", "etags", "multiget"])
        self.assertIn("1 new or changed, 0 gone", self.log)

    def test_an_old_server_is_read_by_month(self):
        helpers.CAL_NOSYNC[0] = 2
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.assertEqual(self.read(), ["Zahnarzt"])
        self.assertEqual(self.seen(), ["sync", "etags", "query"])
        self.assertIn("calendar: mirror not possible", self.log)
        self.assertEqual(self.read(), ["Zahnarzt"])          # not asked again for a while: straight the old way
        self.assertEqual(self.seen(), ["query"])
        self.assertFalse(os.path.exists(ks._file(CID)))

    def test_a_calendar_checked_before_it_is_saved_gets_no_copy(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        r = asyncio.run(calendars.check(dict(self.d), UTC))
        self.assertEqual(r["found"], 1)
        self.assertNotIn(CID, ks._mem)
        self.assertEqual(self.seen(), ["query"])

    def test_a_token_the_server_forgot_starts_again(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.read()
        self.seen()
        for cal in ks._mem[CID].values():
            cal["token"] = "tvergessen"
        self.older()
        self.assertEqual(self.read(), ["Zahnarzt"])
        self.assertEqual(self.seen(), ["sync", "etags"])   # refused, compared by etags: nothing to fetch again

    def test_only_what_touches_the_period_and_repeating_always(self):
        helpers.CAL_EVENTS.update({"/dav/privat/a.ics": ev("a", "20260310", "März"),
                                   "/dav/privat/b.ics": ev("b", "20260710", "Juli"),
                                   "/dav/privat/c.ics": ev("c", "20250105", "Sport", "RRULE:FREQ=WEEKLY\r\n")})
        self.assertEqual(self.read(), ["März", "Sport"])
        self.assertEqual(self.read("20260701", "20260801"), ["Juli", "Sport"])


class Disk(Base):
    def test_encrypted_on_disk_read_back_and_compared_first(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Geheimtermin")
        self.read()
        with open(ks._file(CID)) as f:
            raw = f.read()
        self.assertNotIn("Geheimtermin", raw)
        self.assertTrue(json.loads(raw)["enc"].startswith("enc1:"))
        self.assertEqual(oct(os.stat(ks._file(CID)).st_mode & 0o777), "0o600")
        ks._mem.clear()                                   # the panel starts again
        helpers.CAL_SEEN.clear()
        self.assertEqual(self.read(), ["Geheimtermin"])
        self.assertEqual(self.seen(), ["sync"])           # with the kept token: only the question, no object

    def test_removing_the_entry_or_the_profile_deletes_the_copy(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.read()
        self.assertTrue(os.path.exists(ks._file(CID)))
        saved = calendars.get
        calendars.get = lambda uid: {"calendars": [dict(self.d)], "topics": []}
        try:
            calendars.remove("nobody", CID)
        finally:
            calendars.get = saved
        self.assertFalse(os.path.exists(ks._file(CID)))
        self.assertNotIn(CID, ks._mem)
        self.read()
        calendars.get = lambda uid: {"calendars": [dict(self.d)], "topics": []}
        try:
            calendars.forget("nobody")
        finally:
            calendars.get = saved
        self.assertFalse(os.path.exists(ks._file(CID)))

    def test_a_change_here_asks_the_server_at_the_next_look(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.read()
        self.seen()
        ks.stale([CID])
        self.read()
        self.assertEqual(self.seen(), ["sync"])

    def test_only_entry_ids_name_a_file(self):
        ks.forget(["../../etc/passwd", "c1"])             # nothing outside its folder, no error
        with self.assertRaises(ValueError):
            asyncio.run(ks.texts(None, "../x", "http://x/", datetime.datetime(2026, 3, 1, tzinfo=UTC),
                                 datetime.datetime(2026, 4, 1, tzinfo=UTC)))


class Live(Base):
    def test_numbers_only(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.read()
        d = ks.for_live(now=ks._last[0] + 180)
        self.assertEqual((d["calendars"], d["items"], d["ago"]), (1, 1, 3))
        self.assertNotIn("Zahnarzt", json.dumps(d))


if __name__ == "__main__":
    unittest.main()
