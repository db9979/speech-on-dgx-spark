"""Vorwärmen (vorwaermen.py, Dominik 2026-10-19 „1a 3a 4a 5a 7a 9“): signing in or opening the panel or the app reads
the profile's calendars, mail, Für dich and address book ahead into their own caches, in the background.

- Only profiles (never guests or an unknown id), a profile at most every WARM_AGAIN seconds, never while the panel's
  loop is gone; ask() never waits.
- Only the functions this profile may use now; each step waits while somebody speaks (vorrang.quiet); a failing step
  does not stop the others; one journal line in the area "vorrang", with numbers and log_name only.
- Live: how many profiles were warmed in the last day and how long ago, numbers only.
- calendars.warm reads this and the next month; Heute reads the calendar from the same cache (no own copy).

Times are passed in, fakes instead of servers; no wall clock.
"""
import asyncio
import contextlib
import io
import threading
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import calendars  # noqa: E402
import logfilter  # noqa: E402
import profiles  # noqa: E402
import vorrang  # noqa: E402
import vorwaermen  # noqa: E402
from tests.test_features import profile  # noqa: E402


class Loop:
    """A running event loop in its own thread, like the panel's."""

    def __enter__(self):
        self.loop = asyncio.new_event_loop()
        self.t = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.t.start()
        return self.loop

    def __exit__(self, *a):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.t.join(5)
        self.loop.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (vorwaermen._steps, vorwaermen._loop[0], vorwaermen._sem[0], vorrang.quiet)
        vorwaermen._last.clear()
        self.quiet = []

        async def quiet(job, *a, **kw):
            self.quiet.append(job)
        vorrang.quiet = quiet

    def tearDown(self):
        vorwaermen._steps, vorwaermen._loop[0], vorwaermen._sem[0], vorrang.quiet = self.saved
        vorwaermen._last.clear()


class Ask(Base):
    def test_only_profiles_once_in_a_while_and_never_without_the_loop(self):
        _, uid = profile("WarmWilma")
        ran = threading.Event()

        async def step():
            ran.set()
        vorwaermen._steps = lambda u: [("calendar", step)]
        self.assertFalse(vorwaermen.ask(uid, now=1000))           # no loop yet (before the panel started)
        with Loop() as loop:
            vorwaermen.start(loop)
            self.assertFalse(vorwaermen.ask(None, now=1000))      # a guest
            self.assertFalse(vorwaermen.ask("nobody", now=1000))  # an id no profile has
            self.assertTrue(vorwaermen.ask(uid, now=1000))
            self.assertTrue(ran.wait(5))
            self.assertFalse(vorwaermen.ask(uid, now=1000 + vorwaermen.WARM_AGAIN - 1))   # just done
            self.assertTrue(vorwaermen.ask(uid, now=1000 + vorwaermen.WARM_AGAIN + 1))
        self.assertFalse(vorwaermen.ask(uid, now=99999))          # the loop stopped: nothing breaks, nothing runs

    def test_whoami_and_the_app_ask_for_it(self):
        c, uid = profile("WarmWalter")
        asked = []
        orig = vorwaermen.ask
        vorwaermen.ask = lambda u, now=None: asked.append(u)
        try:
            c.get("/api/whoami")
            c.get("/api/features")
        finally:
            vorwaermen.ask = orig
        self.assertEqual(asked, [uid, uid])


class Warm(Base):
    def test_steps_wait_for_voice_go_on_after_a_failure_and_log_numbers_only(self):
        _, uid = profile("WarmWanda")
        done = []

        async def ok():
            done.append("ok")

        async def bad():
            raise ValueError("the server said 503")
        vorwaermen._steps = lambda u: [("calendar", ok), ("mail", bad), ("contacts", ok)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            parts, failed = asyncio.run(vorwaermen.warm(uid))
        self.assertEqual((parts, failed), (2, 1))
        self.assertEqual(done, ["ok", "ok"])
        self.assertEqual(self.quiet, ["Vorwärmen"] * 3)            # voice first, before every step
        line = out.getvalue().strip()
        who = profiles.log_name(profiles.by_id(uid))
        # the whole line is fixed words, counts and the profile tag ("Profil " and the end of a random id, which
        # may hold "503" by chance), so nothing of the error text can be in it
        self.assertEqual(line, "vorwaermen: done | 2 parts, 1 failed | " + who)
        self.assertNotIn("WarmWanda", line)                        # no name without its consent
        self.assertNotIn("503", line[:-len(who)])
        self.assertEqual(next(k for k, rx in logfilter._AREAS if rx.search(line)), "vorrang")

    def test_only_what_the_profile_may_use(self):
        _, uid = profile("WarmWerner")
        helpers.set_config(calendar=False, mail=False, contacts=False)
        self.assertEqual(vorwaermen._steps(uid), [])
        saved = calendars.reading
        calendars.reading = lambda u: {"calendars": [{"id": "t1", "name": "Privat", "url": "http://x/"}]}
        try:
            helpers.set_config(calendar=True)
            self.assertEqual([n for n, _ in vorwaermen._steps(uid)], ["calendar"])
        finally:
            calendars.reading = saved
            helpers.set_config(calendar=False)


class Live(Base):
    def test_numbers_only(self):
        self.assertEqual(vorwaermen.for_live(now=10_000), {"profiles": 0, "ago": None})
        vorwaermen._last.update({"a": 10_000 - 300, "b": 10_000 - 120, "c": 10_000 - vorwaermen.WARM_SECONDS - 1})
        self.assertEqual(vorwaermen.for_live(now=10_000), {"profiles": 2, "ago": 2})


class Calendars(unittest.TestCase):
    def test_warm_reads_this_and_the_next_month(self):
        saved = (calendars._fetch, calendars.reading)
        calls = []

        async def fetch(d, a, b):
            calls.append(a.date().isoformat())
            return [], 1
        calendars._fetch = fetch
        calendars.reading = lambda u: {"calendars": [{"id": "w1", "name": "Privat", "url": "http://x/"}]}
        calendars._cache.clear()
        calendars._inflight.clear()
        try:
            import datetime
            now = datetime.datetime(2026, 3, 20, 12, tzinfo=datetime.timezone.utc).timestamp()
            self.assertEqual(asyncio.run(calendars.warm("w-user", now)), 1)
            self.assertEqual(sorted(calls), ["2026-03-01", "2026-04-01"])
            self.assertIn("w-user", calendars._used)                 # kept fresh from now on
        finally:
            calendars._fetch, calendars.reading = saved
            calendars._cache.clear()
            calendars._used.pop("w-user", None)


if __name__ == "__main__":
    unittest.main()
