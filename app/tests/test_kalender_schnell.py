"""Kalender: Schnell eintragen, schwebende Karte, Verschieben (Dominik 2026-10-19 „kalender: 1a 2a 3a“).

- calendars.quick reads one line by fixed rules (no model): day (heute, morgen, übermorgen, a weekday, „in 3 Tagen“,
  dd.mm.[yyyy]), time (10 Uhr, 10:30, 14-15 Uhr, 3pm), place after „bei/in/im“, the rest is the title. A day
  without a time is all day; a short weekday (Mo, So) only as „am So“ or „So.“, so words in a title stay words.
- GET /api/profile/calendar/quick only reads: nothing is saved; saving goes through the form's POST as before.
- The page at 1280 px: the line shows what it understood as chips, Enter saves; the appointment tapped opens a card
  floating beside it (the view keeps its whole width); „+1 Tag“ moves it, „Rückgängig“ puts it back; the mouse drags
  it to another hour. At 390 px the card is a sheet from below.

Fixed dates (2026-03), the fake CalDAV server; times are passed in, no wall clock.
"""
import asyncio
import datetime
import unittest
import zoneinfo

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import panel  # noqa: E402,F401
import calendars  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_kalender_aendern import TZ, connect, profile  # noqa: E402

ZONE = zoneinfo.ZoneInfo(TZ)
NOW = datetime.datetime(2026, 3, 9, 14, 0, tzinfo=ZONE)   # a Monday afternoon


def q(text):
    d = calendars.quick(text, NOW)
    return d["title"], d["start"], d["end"], d["location"]


def clean():
    for k in [k for k, v in helpers.CAL_EVENTS.items() if "Schnell" in v]:
        helpers.CAL_EVENTS.pop(k, None)
    calendars._cache.clear()


class Parse(unittest.TestCase):
    def test_lines(self):
        self.assertEqual(q("Zahnarzt morgen 10 Uhr bei Dr. Weber"), ("Zahnarzt", "2026-03-10T10:00", "2026-03-10T11:00", "Dr. Weber"))
        self.assertEqual(q("Team Freitag 14-15 Uhr"), ("Team", "2026-03-13T14:00", "2026-03-13T15:00", ""))
        self.assertEqual(q("Essen um 19:30 im Lokal Sonne"), ("Essen", "2026-03-09T19:30", "2026-03-09T20:30", "Lokal Sonne"))
        self.assertEqual(q("Laufen 7 Uhr"), ("Laufen", "2026-03-10T07:00", "2026-03-10T08:00", ""))   # passed today: tomorrow
        self.assertEqual(q("Call tomorrow 3pm"), ("Call", "2026-03-10T15:00", "2026-03-10T16:00", ""))
        self.assertEqual(q("Arzt 25.03.2026 9:15-10"), ("Arzt", "2026-03-25T09:15", "2026-03-25T10:00", ""))
        self.assertEqual(q("Sport nächsten Montag 18 Uhr"), ("Sport", "2026-03-16T18:00", "2026-03-16T19:00", ""))
        self.assertEqual(q("Yoga am Mi 9 Uhr"), ("Yoga", "2026-03-11T09:00", "2026-03-11T10:00", ""))

    def test_all_day_and_words_that_stay_words(self):
        self.assertEqual(q("Geburtstag Anna 24.12."), ("Geburtstag Anna", "2026-12-24", "2026-12-25", ""))
        self.assertEqual(q("Treffen mit Anna in 3 Tagen"), ("Treffen mit Anna", "2026-03-12", "2026-03-13", ""))
        self.assertTrue(calendars.quick("Urlaub übermorgen", NOW)["allday"])
        self.assertEqual(q("Essen so um 20 Uhr")[0], "Essen so")          # „so“ is no Sunday
        self.assertEqual(q("Montagsrunde 10 Uhr")[0], "Montagsrunde")
        self.assertEqual(q("Kurs 25 Uhr")[1], "2026-03-09")               # no such hour: not a time, the day all day
        self.assertEqual(q("Kurs 31.02.")[1], "2026-03-09")               # no such day

    def test_without_a_title_and_too_long(self):
        for text in ("", "morgen 10 Uhr", "   "):
            with self.assertRaises(ValueError):
                calendars.quick(text, NOW)
        self.assertLessEqual(len(calendars.quick("x" * 5000, NOW)["title"]), 200)

    def test_the_form_takes_it(self):
        d = calendars.quick("Zahnarzt morgen 10 Uhr bei Dr. Weber", NOW)
        item = calendars.page_item(d, ZONE)
        self.assertEqual((item["title"], item["location"]), ("Zahnarzt", "Dr. Weber"))
        self.assertEqual(datetime.datetime.fromisoformat(item["start"]), datetime.datetime(2026, 3, 10, 10, tzinfo=ZONE))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True)
        cls.c, cls.uid = profile("Schnell Sina")
        connect(cls.uid)

    def test_reads_only(self):
        before = dict(helpers.CAL_EVENTS)
        r = self.c.get("/api/profile/calendar/quick", params={"text": "Schnell morgen 9 Uhr", "tz": TZ})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["title"], r.json()["allday"]), ("Schnell", False))
        self.assertEqual(helpers.CAL_EVENTS, before)
        self.assertEqual(self.c.get("/api/profile/calendar/quick", params={"text": "morgen 9 Uhr"}).status_code, 400)

    def test_signed_in_and_released_only(self):
        self.assertIn(TestClient(panel.app).get("/api/profile/calendar/quick", params={"text": "x"}).status_code, (401, 403))
        helpers.set_config(calendar=False)
        try:
            self.assertIn(self.c.get("/api/profile/calendar/quick", params={"text": "x"}).status_code, (403, 404))
        finally:
            helpers.set_config(calendar=True)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        clean()

    def test_quick_card_move_undo_drag(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        start = "KAL.data.events.find(x=>x.title==='Schnell Sitzung')"

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1280, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    if not calendars.get(uid)["calendars"]:
                        connect(uid)
                    await pg.evaluate("CAL_ON=true;icTabSet('cal','show');KAL.day=new Date(2026,2,10);KAL.view='week';goSec('cal')")
                    await b.until(pg, "!KAL.busy&&!!KAL.data&&KAL.data.add&&KAL.data.add.length>0")
                    # the view has the whole width beside the column of calendars (Apple-Stil „4a“): the card never takes a column
                    wide = await pg.evaluate("(document.querySelector('#kalview .kalmain').getBoundingClientRect().width+"
                                             "document.querySelector('#kalview .kalside').getBoundingClientRect().width)/"
                                             "document.querySelector('#kalroot').getBoundingClientRect().width")
                    self.assertGreater(wide, 0.9)
                    await pg.fill("#kalview [data-q]", "Schnell Sitzung 11.03.2026 9 Uhr im Saal")
                    await b.until(pg, "document.querySelector('#kalview .kqchips').textContent.includes('Saal')")
                    await pg.press("#kalview [data-q]", "Enter")
                    await b.until(pg, f"!KAL.busy&&!!{start}")
                    self.assertEqual(await pg.evaluate("document.querySelector('#kalview [data-q]').value"), "")
                    t0 = await pg.evaluate(f"{start}.start")
                    # the card floats beside it, on the screen
                    await pg.evaluate(f"document.querySelector(`#kalview .kalmain [data-i=\"${{KAL.data.events.indexOf({start})}}\"]`).click()")
                    await b.until(pg, "!document.querySelector('#kalview .kaldet').hidden")
                    box = await pg.evaluate("(()=>{const r=document.querySelector('#kalview .kaldet').getBoundingClientRect();"
                                            "return [r.left,r.right,getComputedStyle(document.querySelector('#kalview .kaldet')).position]})()")
                    self.assertGreaterEqual(box[0], 0)
                    self.assertLessEqual(box[1], 1280)
                    self.assertEqual(box[2], "absolute")
                    await pg.click("#kalview .kaldet [data-act=day]")
                    await b.until(pg, f"!KAL.busy&&!!{start}&&{start}.start==={t0 + 86400}")
                    await pg.click("#kalview .kalundo [data-u]")
                    await b.until(pg, f"!KAL.busy&&!!{start}&&{start}.start==={t0}")
                    # dragged an hour down with the mouse
                    r = await pg.evaluate(f"(()=>{{const e=document.querySelector(`#kalview .kalmain [data-i=\"${{KAL.data.events.indexOf({start})}}\"]`).getBoundingClientRect();return [e.left+e.width/2,e.top+8]}})()")
                    await pg.mouse.move(r[0], r[1])
                    await pg.mouse.down()
                    for i in range(1, 12):
                        await pg.mouse.move(r[0], r[1] + i * 4)
                    await pg.mouse.up()
                    await b.until(pg, f"!KAL.busy&&!!{start}&&{start}.start==={t0 + 3600}")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
                # a phone: the card is a sheet from below
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    await pg.evaluate("CAL_ON=true;icTabSet('cal','show');KAL.day=new Date(2026,2,11);KAL.view='list';goSec('cal')")
                    await b.until(pg, f"!KAL.busy&&!!KAL.data&&!!{start}")
                    await pg.evaluate(f"document.querySelector(`#kalview .kalmain [data-i=\"${{KAL.data.events.indexOf({start})}}\"]`).click()")
                    await b.until(pg, "document.querySelector('#kalview .kaldet').classList.contains('sheet')&&!document.querySelector('#kalview .kalshade').hidden")
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1)
                    await pg.keyboard.press("Escape")
                    await b.until(pg, "document.querySelector('#kalview .kaldet').hidden")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
