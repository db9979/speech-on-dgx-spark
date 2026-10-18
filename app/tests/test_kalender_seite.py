"""The page Kalender (Dominik 2026-10-18, plan kalender-mail/plan.md 1a 4a): the profile's calendars as a page of its own
in the menu, everything set up for calendars in its tab „Einstellungen“, no longer a page of Ich.

- GET /api/profile/calendar/view gives only the own appointments of the days asked (at most calendars.VIEW_DAYS), each
  with the place of its calendar; a wrong date is refused, guests and a profile without the function get nothing.
- The page shows day, week, month and list at 320, 390 and 1280 px without sideways scrolling; „Einstellungen“ holds
  the box that was Ich → Kalender; Ich no longer lists it; #me=calbox (the apps) and the old way open the page.

The appointments lie on fixed dates; no wall clock.
"""
import asyncio
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
EVENT = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:kal-seite-1\r\n"
         "DTSTART;TZID=Europe/Berlin:20260310T103000\r\nDTEND;TZID=Europe/Berlin:20260310T120000\r\n"
         "SUMMARY:Werkstatt Auto\r\nLOCATION:Offenburg\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
PATH = "/dav/privat/kal-seite-1.ics"


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def connect(uid, name="Privat"):
    calendars.add(uid, calendars.entry({"name": name, "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                        "user": "k", "password": "pw"}))


class View(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True)
        helpers.CAL_EVENTS[PATH] = EVENT
        cls.c, cls.uid = profile("Kalender Kai")
        connect(cls.uid)

    @classmethod
    def tearDownClass(cls):
        helpers.CAL_EVENTS.pop(PATH, None)

    def test_the_week_with_its_appointment(self):
        r = self.c.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7, "tz": "Europe/Berlin"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["connected"])
        self.assertEqual(d["calendars"], ["Privat"])
        ev = [x for x in d["events"] if x["title"] == "Werkstatt Auto"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["location"], "Offenburg")
        self.assertEqual(ev[0]["cal"], 0)
        self.assertFalse(ev[0]["allday"])
        self.assertEqual(ev[0]["end"] - ev[0]["start"], 5400)
        # another week does not hold it
        d = self.c.get("/api/profile/calendar/view", params={"start": "2026-03-16", "days": 7, "tz": "Europe/Berlin"}).json()
        self.assertEqual([x for x in d["events"] if x["title"].startswith("Werkstatt")], [])

    def test_limits(self):
        r = self.c.get("/api/profile/calendar/view", params={"start": "kein datum"})
        self.assertEqual(r.status_code, 400)
        # at most six weeks, at least one day
        day = __import__("datetime").date(2026, 3, 9)
        from zoneinfo import ZoneInfo
        got = []
        orig = calendars.events

        async def spy(uid, start, end, zone):
            got.append((end - start).days)
            return await orig(uid, start, end, zone)
        calendars.events = spy
        try:
            asyncio.run(calendars.view(self.uid, day, 500, ZoneInfo("Europe/Berlin")))
            asyncio.run(calendars.view(self.uid, day, -3, ZoneInfo("Europe/Berlin")))
        finally:
            calendars.events = orig
        self.assertEqual(got, [calendars.VIEW_DAYS, 1])

    def test_only_own_and_never_guests(self):
        other, _ = profile("Kalender Kim")
        d = other.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7}).json()
        self.assertEqual(d, {"connected": False, "calendars": [], "events": [], "errors": []})
        self.assertIn(TestClient(panel.app).get("/api/profile/calendar/view").status_code, (401, 403))

    def test_off_gives_nothing(self):
        helpers.set_config(calendar=False)
        try:
            self.assertIn(self.c.get("/api/profile/calendar/view").status_code, (403, 503))
        finally:
            helpers.set_config(calendar=True)

    def test_a_calendar_out_of_reach_is_named(self):
        c, uid = profile("Kalender Kurt")
        calendars.add(uid, calendars.entry({"name": "Weg", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/nirgends/"}))
        d = c.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7}).json()
        self.assertEqual(d["errors"], ["Weg"])


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)
        helpers.CAL_EVENTS[PATH] = EVENT

    @classmethod
    def tearDownClass(cls):
        helpers.CAL_EVENTS.pop(PATH, None)

    def test_views_fit_and_the_settings_sit_here(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for width in (1280, 390, 320):
                    br, pg, errors = await b.page(p, width, 900)
                    try:
                        # the browser's own profile gets the calendar (its id from the page, no name here)
                        uid = await pg.evaluate("PROFILE.id")
                        if not calendars.get(uid)["calendars"]:
                            connect(uid)
                        # a profile without the admin login sees the menu entry too (body.prof hides the admin's)
                        if width == 1280:
                            self.assertEqual(await pg.evaluate("getComputedStyle(document.querySelector('nav button[data-s=cal]')).display==='none'"), False)
                        # Ich no longer lists the calendar; the old place opens the page of its own
                        self.assertNotIn("calbox", await pg.evaluate("meAll().map(x=>x[0])"))
                        await pg.evaluate("openMe('calbox')")
                        await b.until(pg, "$('cal').classList.contains('on')&&$('kalroot').contains($('calbox'))&&!$('calbox').hidden")
                        await pg.evaluate("icTabSet('cal','show');KAL.day=new Date(2026,2,10);goSec('cal')")
                        for view in ("week", "month", "list", "day"):
                            await pg.evaluate(f"KAL.view='{view}';kalLoad()")
                            await b.until(pg, "!KAL.busy&&!!KAL.data&&KAL.data.events.some(x=>x.title.startsWith('Werkstatt'))")
                            await b.until(pg, "[...document.querySelectorAll('#kalview [data-i]')].some(e=>e.textContent.includes('Werkstatt'))")
                            # a title from the calendar is text, never markup
                            await pg.evaluate("KAL.data.events.push({...KAL.data.events[0],title:'<img src=x id=kalx>'});kalDraw()")
                            self.assertEqual(await pg.evaluate("document.querySelectorAll('#kalx').length"), 0)
                            await pg.evaluate("KAL.data.events.pop();kalDraw()")
                            over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                            self.assertLessEqual(over, 1, f"{view} at {width} px scrolls sideways")
                        # a tap shows the details
                        await pg.evaluate("document.querySelector('#kalview [data-i]').click()")
                        await b.until(pg, "!document.querySelector('#kalview .kaldet').hidden&&document.querySelector('#kalview .kaldet').textContent.includes('Offenburg')")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
