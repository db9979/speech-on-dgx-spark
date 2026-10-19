"""Kalender schnell (Dominik 2026-10-19 „kalender langsam, caching für einträge und hintergrund aktualisierung“):

- The cache keeps whole calendar months per calendar; every reader (page, assistant, briefing, check every minute)
  hits the same blocks, a fetch per block runs once however many ask.
- The page waits at most VIEW_BUDGET: a calendar not done by then is named under "loading", its fetch goes on in the
  background and lands in the cache, so the next look shows it (before, the fetch was cancelled and never cached).
- The page shows a block older than CACHE_SECONDS (up to STALE_SECONDS) at once and fetches it anew behind; the
  assistant waits for a fresh one. A change (drop) during a fetch never stores the older answer.
- Where an address's calendars are (CalDAV discovery) is kept FOUND_SECONDS: the next fetch goes straight to them.
- keep_fresh refreshes this and the next month of the profiles that read their calendars in the last day.

Fixed dates and a fake fetch or the fake CalDAV server; times are passed in, no wall clock.
"""
import asyncio
import datetime
import time
import unittest
import zoneinfo

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import calendars  # noqa: E402

ZONE = zoneinfo.ZoneInfo("Europe/Berlin")
DAY = datetime.datetime(2026, 3, 9, tzinfo=ZONE)
EVENT = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:tempo-1\r\n"
         "DTSTART;TZID=Europe/Berlin:20260310T103000\r\nDTEND;TZID=Europe/Berlin:20260310T120000\r\n"
         "SUMMARY:Zahnarzt\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


class Fake:
    """Replaces calendars._fetch: counts the calls, waits `delay` seconds, answers EVENT."""

    def __init__(self, delay=0.0, fail=False):
        self.calls, self.delay, self.fail = [], delay, fail

    async def __call__(self, d, a, b):
        self.calls.append((d["id"], a.date().isoformat()))
        await asyncio.sleep(self.delay)
        if self.fail:
            raise ValueError("the calendar server answered 503")
        return [EVENT], 1


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (calendars._fetch, calendars.get, calendars.reading, calendars.VIEW_BUDGET)
        calendars._cache.clear()
        calendars._inflight.clear()
        calendars._used.clear()
        self.cals = [{"id": "t1", "name": "Privat", "url": "http://x/", "user": "k"}]
        calendars.get = lambda uid: {"calendars": list(self.cals), "topics": []}
        calendars.reading = calendars.get

    def tearDown(self):
        calendars._fetch, calendars.get, calendars.reading, calendars.VIEW_BUDGET = self.saved
        calendars._cache.clear()
        calendars._inflight.clear()
        calendars._used.clear()


class Blocks(Base):
    def test_months_and_one_fetch_per_block(self):
        utc = datetime.timezone.utc
        m = calendars._months(datetime.datetime(2026, 1, 28, tzinfo=utc), datetime.datetime(2026, 3, 2, tzinfo=utc))
        self.assertEqual([x.date().isoformat() for x in m], ["2026-01-01", "2026-02-01", "2026-03-01"])
        f = calendars._fetch = Fake(delay=0.05)

        async def go():
            # three readers at once, the same month: one fetch
            await asyncio.gather(*(calendars._one("u1", self.cals[0], DAY, DAY + datetime.timedelta(days=d), ZONE)
                                   for d in (1, 2, 7)))
            return await calendars._one("u1", self.cals[0], DAY, DAY + datetime.timedelta(days=3), ZONE)
        evs = asyncio.run(go())
        self.assertEqual(f.calls, [("t1", "2026-03-01")])
        self.assertEqual([x["title"] for x in evs], ["Zahnarzt"])


class Page(Base):
    def test_slow_calendar_keeps_loading_and_shows_next_time(self):
        f = calendars._fetch = Fake(delay=0.3)
        calendars.VIEW_BUDGET = 0.05

        async def go():
            first = await calendars.view("u1", DAY.date(), 7, ZONE)
            await asyncio.sleep(0.5)   # the fetch went on in the background
            second = await calendars.view("u1", DAY.date(), 7, ZONE)
            return first, second
        first, second = asyncio.run(go())
        self.assertEqual(first["loading"], ["Privat"])
        self.assertEqual(first["errors"], [])
        self.assertEqual(first["events"], [])
        self.assertEqual(second["loading"], [])
        self.assertEqual([x["title"] for x in second["events"]], ["Zahnarzt"])
        self.assertEqual(len(f.calls), 1)   # the second look came from the cache

    def test_stale_block_at_once_for_the_page_fresh_for_the_assistant(self):
        f = calendars._fetch = Fake(delay=0.2)
        old = time.time() - calendars.CACHE_SECONDS - 10
        calendars._cache[("u1", "t1", "2026-03-01")] = (old, [EVENT])
        calendars.VIEW_BUDGET = 0.1

        async def go():
            page = await calendars.view("u1", DAY.date(), 7, ZONE)
            calls_then = len(f.calls)
            await asyncio.sleep(0.3)
            return page, calls_then
        page, calls_then = asyncio.run(go())
        self.assertEqual(page["loading"], [])                     # shown at once from the older block
        self.assertEqual([x["title"] for x in page["events"]], ["Zahnarzt"])
        self.assertEqual(calls_then, 1)                           # and fetched anew behind
        self.assertGreater(calendars._cache[("u1", "t1", "2026-03-01")][0], old)
        # the assistant (events) waits for a fresh block
        calendars._cache[("u1", "t1", "2026-03-01")] = (old, [])
        evs, errors = asyncio.run(calendars.events("u1", DAY, DAY + datetime.timedelta(days=7), ZONE))
        self.assertEqual([x["title"] for x in evs], ["Zahnarzt"])
        self.assertEqual(len(f.calls), 2)

    def test_a_failing_calendar_is_named_not_loading(self):
        calendars._fetch = Fake(fail=True)
        d = asyncio.run(calendars.view("u1", DAY.date(), 7, ZONE))
        self.assertEqual(d["errors"], ["Privat"])
        self.assertEqual(d["loading"], [])

    def test_a_change_during_the_fetch_stores_nothing_old(self):
        calendars._fetch = Fake(delay=0.1)

        async def go():
            t = asyncio.ensure_future(calendars._one("u1", self.cals[0], DAY, DAY + datetime.timedelta(days=1), ZONE))
            await asyncio.sleep(0.02)
            calendars._drop("u1")   # e.g. an appointment saved on the page meanwhile
            await t
        asyncio.run(go())
        self.assertEqual(calendars._cache, {})


class Fresh(Base):
    def test_keep_fresh_only_for_recent_readers(self):
        f = calendars._fetch = Fake()
        helpers.set_config(calendar=True)
        now = datetime.datetime(2026, 3, 20, 12, tzinfo=datetime.timezone.utc).timestamp()
        calendars._used.update({"u1": now - 60, "u2": now - calendars.WARM_SECONDS - 60})
        people, n = asyncio.run(calendars.keep_fresh(now))
        self.assertEqual((people, n), (1, 1))
        self.assertEqual(sorted(f.calls), [("t1", "2026-03-01"), ("t1", "2026-04-01")])   # this and the next month
        self.assertNotIn("u2", calendars._used)
        # all fresh now: the next round fetches nothing
        f.calls.clear()
        asyncio.run(calendars.keep_fresh(now))
        self.assertEqual(f.calls, [])


class Discovery(unittest.TestCase):
    def test_the_second_fetch_skips_finding_the_calendars(self):
        helpers.CAL_EVENTS["/dav/privat/tempo-1.ics"] = EVENT
        d = {"id": "tempo", "name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/", "user": "k", "password": "pw"}
        found = []
        orig = calendars._calendars

        async def spy(c, url, comp="VEVENT"):
            found.append(url)
            return await orig(c, url, comp)
        calendars._calendars = spy
        calendars._found.clear()
        try:
            a = datetime.datetime(2026, 3, 1, tzinfo=datetime.timezone.utc)
            b = datetime.datetime(2026, 4, 1, tzinfo=datetime.timezone.utc)
            t1, _ = asyncio.run(calendars._fetch(d, a, b))
            t2, _ = asyncio.run(calendars._fetch(d, a, b))
            self.assertEqual(len(found), 1)
            self.assertTrue(any("Zahnarzt" in x for x in t1) and any("Zahnarzt" in x for x in t2))
            calendars._drop("nobody")   # any change of the settings asks anew
            asyncio.run(calendars._fetch(d, a, b))
            self.assertEqual(len(found), 2)
        finally:
            calendars._calendars = orig
            calendars._found.clear()
            helpers.CAL_EVENTS.pop("/dav/privat/tempo-1.ics", None)


if __name__ == "__main__":
    unittest.main()
