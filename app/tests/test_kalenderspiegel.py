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
        out = [k for _, k in helpers.CAL_SEEN if k not in ("find", "object")]
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

    def test_without_a_token_what_the_list_leaves_out_is_gone(self):
        # after a change made here the copy asks without its token: a server may leave out of its changes an
        # object made and removed after the old token (RFC 6578 3.5), the whole list cannot
        helpers.CAL_EVENTS.update({"/dav/privat/a.ics": ev("a", "20260310", "Zahnarzt"),
                                   "/dav/privat/b.ics": ev("b", "20260312", "Elternabend")})
        self.read()
        helpers.CAL_EVENTS.pop("/dav/privat/b.ics")
        for cal in ks._mem[CID].values():
            cal["token"] = ""
        self.older()
        self.assertEqual(self.read(), ["Zahnarzt"])
        self.assertIn("1 gone", self.log)

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


class Behind(Base):
    """Stufe 2 (Dominik 2026-10-19 „3a“): a change from the page lands in the copy at once and goes to the server
    behind it; a refusal puts the copy back, compares anew and leaves a note for the page."""

    def setUp(self):
        super().setUp()
        helpers.CAL_REFUSE[0] = 0
        self.saved_get = (calendars.get, calendars.reading)
        calendars.get = lambda uid: {"calendars": [dict(self.d)], "topics": []}
        calendars.reading = calendars.get
        calendars._notes.clear()
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.read()
        self.seen()

    def tearDown(self):
        helpers.CAL_REFUSE[0] = 0
        calendars.get, calendars.reading = self.saved_get
        calendars._notes.clear()
        super().tearDown()

    def run_page(self, coro_fn):
        """Runs the page's change and returns (what the copy holds right after, then after the server answered)."""
        async def go():
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                await coro_fn()
                now = sorted(re.search(r"SUMMARY:([^\r\n]*)", x[1]).group(1)
                             for x in ks._mem[CID][self.cal()]["items"].values())
                server_now = len(helpers.CAL_EVENTS)
                for _ in range(200):          # the change behind the page
                    if not ks._pending:
                        break
                    await asyncio.sleep(0.01)
            self.log = out.getvalue()
            return now, server_now
        return asyncio.run(go())

    def cal(self):
        return next(iter(ks._mem[CID]))

    def item(self):
        return {"title": "Elternabend", "start": "2026-03-12T18:00", "end": "2026-03-12T19:00", "allday": False,
                "location": "", "calendar": ""}

    def test_a_new_appointment_is_in_the_copy_at_once_and_on_the_server_behind(self):
        item = calendars.page_item(self.item(), UTC)
        now, server_now = self.run_page(lambda: calendars.add_event("u-behind", item, wait=False))
        self.assertEqual(now, ["Elternabend", "Zahnarzt"])           # the page sees it before the server has it
        self.assertEqual(server_now, 1)
        self.assertEqual(len(helpers.CAL_EVENTS), 2)                  # … and then the server has it
        self.assertIn("calendar: saved behind", self.log)
        self.assertNotIn("PROPFIND", [m for m, k in helpers.CAL_SEEN if k == "find"][1:])   # found once, not per change
        self.assertEqual(self.read(), ["Elternabend", "Zahnarzt"])

    def test_a_change_takes_the_object_from_the_copy(self):
        zone = UTC
        p = asyncio.run(calendars.page_find("u-behind", 0, "Zahnarzt",
                                            int(datetime.datetime(2026, 3, 10, 9, tzinfo=UTC).timestamp()), zone))
        self.seen()
        p.update(change="edit", new_title="Zahnarzt neu", new_start="2026-03-11T09:00+00:00",
                 new_end="2026-03-11T10:00+00:00", new_allday=False, new_location="")
        now, _ = self.run_page(lambda: calendars.change_event("u-behind", p, wait=False))
        self.assertEqual(now, ["Zahnarzt neu"])
        self.assertEqual([m for m, k in helpers.CAL_SEEN if k == "object"], ["PUT"])   # no GET first
        self.assertIn("Zahnarzt neu", helpers.CAL_EVENTS["/dav/privat/a.ics"])

    def test_a_comparison_running_during_a_change_never_puts_the_old_state_back(self):
        """V01.0.862 (busy GitHub runner): a comparison already asking the server when the page changed an object,
        and the server took the change before the comparison ended, held the old state; it put it back and marked
        the copy fresh, so the changed appointment showed its old time until the next look."""
        url = self.cal()
        cal = ks._mem[CID][url]
        h = next(iter(cal["items"]))
        old, new = cal["items"][h][1], ev("a", "20260311", "Zahnarzt neu")
        real = (ks._changes, ks._multiget)

        async def changes(c, u, token):   # while the server answers, the page changes the object and it is taken
            ks.put_local(CID, url, h, new)
            ks.taken(CID, url, h, "neu")
            return {h: "alt"}, [h + "x"], "token-alt"

        async def multiget(c, u, hrefs):
            return {x: ("alt", old) for x in hrefs}
        ks._changes, ks._multiget = changes, multiget
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                asyncio.run(ks._sync(None, CID, url, cal))
        finally:
            ks._changes, ks._multiget = real
        self.assertIn("Zahnarzt neu", cal["items"][h][1])
        self.assertEqual((cal["token"], cal["at"]), ("", 0.0))      # the next look compares everything again

    def test_a_refusal_puts_the_copy_back_and_leaves_a_note(self):
        helpers.CAL_REFUSE[0] = 503
        item = calendars.page_item(self.item(), UTC)
        now, _ = self.run_page(lambda: calendars.add_event("u-behind", item, wait=False))
        self.assertEqual(now, ["Elternabend", "Zahnarzt"])
        self.assertIn("calendar: not saved behind (503)", self.log)
        self.assertEqual(calendars.notes("u-behind"), ["Elternabend"])
        self.assertEqual(calendars.notes("u-behind", now=10 ** 11), [])   # gone after NOTE_SECONDS
        helpers.CAL_REFUSE[0] = 0
        self.assertEqual(self.read(), ["Zahnarzt"])                   # the server's version stands
        self.assertEqual(ks._mem[CID][self.cal()]["token"][:1], "t")  # compared anew from scratch

    def test_a_second_entry_of_the_same_calendar_sees_it_at_once(self):
        twin = dict(self.d, id="c0ffee123", name="Privat 2")
        calendars.get = lambda uid: {"calendars": [dict(self.d), twin], "topics": []}
        calendars.reading = calendars.get
        asyncio.run(calendars._fetch(twin, datetime.datetime(2026, 3, 1, tzinfo=UTC),
                                     datetime.datetime(2026, 4, 1, tzinfo=UTC)))
        try:
            item = calendars.page_item(self.item(), UTC)
            self.run_page(lambda: calendars.add_event("u-behind", item, wait=False))
            self.assertEqual(sorted(re.search(r"SUMMARY:([^\r\n]*)", x[1]).group(1)
                                    for x in ks._mem["c0ffee123"][self.cal()]["items"].values()),
                             ["Elternabend", "Zahnarzt"])
        finally:
            ks.forget(["c0ffee123"])

    def test_the_assistant_still_waits_for_the_server(self):
        helpers.CAL_REFUSE[0] = 503
        item = calendars.page_item(self.item(), UTC)
        with self.assertRaises(ValueError):
            asyncio.run(calendars.add_event("u-behind", item))
        self.assertEqual(self.read(), ["Zahnarzt"])


class Live(Base):
    def test_numbers_only(self):
        helpers.CAL_EVENTS["/dav/privat/a.ics"] = ev("a", "20260310", "Zahnarzt")
        self.read()
        d = ks.for_live(now=ks._last[0] + 180)
        self.assertEqual((d["calendars"], d["items"], d["ago"]), (1, 1, 3))
        self.assertNotIn("Zahnarzt", json.dumps(d))


if __name__ == "__main__":
    unittest.main()
