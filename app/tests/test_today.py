"""Ich → Heute (today.py, V01.0.286): only with a profile, only functions it may use, only numbers and short
titles."""
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
import today  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_features import ADMIN, profile  # noqa: E402


class Today(unittest.TestCase):
    def test_needs_a_profile(self):
        guest = TestClient(panel.app)
        self.assertEqual(guest.get("/api/profile/today").status_code, 401)

    def test_cards_follow_the_switches(self):
        c, uid = profile("HeuteHanna")
        helpers.set_config(memory=True, reminders=True, messages=False, calendar=False, documents=True, mfa=True,
                           iphone=False, speaker_id=False, pebble=False)
        profiles.add_reminder(uid, "Müll rausbringen", (time.time() + 3600) * 1000)
        d = c.get("/api/profile/today").json()
        self.assertEqual(d["cards"]["reminders"]["count"], 1)
        self.assertEqual(d["cards"]["reminders"]["next"]["text"], "Müll rausbringen")
        self.assertIn("memory", d["cards"])
        self.assertNotIn("messages", d["cards"])      # Spark off: no card
        self.assertNotIn("calendar", d["cards"])
        self.assertNotIn("setup", d)                   # what is still to set up is "Los geht's" (onboard.py)
        helpers.set_config(calendar=True)
        today._cal.clear()
        d = c.get("/api/profile/today").json()
        self.assertEqual(d["cards"]["calendar"], {"connected": False, "next": []})
        helpers.set_config(calendar=False)

    def test_a_slow_calendar_does_not_hold_the_page(self):
        c, uid = profile("HeuteHugo")
        import asyncio
        import calendars
        real, budget = calendars.events, today.CAL_BUDGET

        async def slow(*a):
            await asyncio.sleep(5)
        calendars.events, today.CAL_BUDGET = slow, 0.2
        today._cal.clear()
        helpers.set_config(calendar=True)
        try:
            t0 = time.monotonic()
            d = c.get("/api/profile/today").json()
            self.assertLess(time.monotonic() - t0, 3)
            self.assertTrue(d["cards"]["calendar"]["error"])
        finally:
            calendars.events, today.CAL_BUDGET = real, budget
            helpers.set_config(calendar=False)

    def test_app_key_reads_it(self):
        self.assertIn("/api/profile/today", profiles.APP_PATHS)
