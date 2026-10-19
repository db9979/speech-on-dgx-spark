"""Termine auf der Seite Kalender anlegen, ändern und löschen (plan kalender-mail Stufe 2, Dominik 2026-10-19 „baue alle
Stufen“): the page's form is the person's own yes; the server checks like the assistant's way.

- POST /api/profile/calendar/event adds to the first own CalDAV calendar, or to the one named (also one shared with
  "add"); never to an iCal link; a form without title, or an end before the start, is refused.
- PUT /api/profile/calendar/event changes (title, place, start, end) or deletes exactly the one appointment the page
  shows, only in an own CalDAV calendar, never a repeating one, with the server's etag (If-Match); an appointment
  that is no longer there as shown gives 409; a shared calendar is never changed by the other profile.
- The view marks which appointments the page may change ("edit") and where it may add ("add").
- The form at 390 px: „+ Termin“, fill, „Speichern“, the appointment is on the page; „Ändern“ and „Löschen“ in its
  details.

Fixed dates (2026-03), the fake CalDAV server; no wall clock.
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
REPEAT = ("/dav/privat/aendern-rr.ics",
          "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:aendern-rr\r\n"
          "DTSTART;TZID=Europe/Berlin:20260302T080000\r\nDTEND;TZID=Europe/Berlin:20260302T083000\r\n"
          "RRULE:FREQ=WEEKLY\r\nSUMMARY:Joggen Aendern\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
TZ = "Europe/Berlin"


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def connect(uid, name="Privat"):
    calendars.add(uid, calendars.entry({"name": name, "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                        "user": "k", "password": "pw"}))


def clean():
    for k in [k for k, v in helpers.CAL_EVENTS.items() if "Aendern" in v]:
        helpers.CAL_EVENTS.pop(k, None)
    calendars._cache.clear()


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_share=True)
        cls.c, cls.uid = profile("Aendern Anja")
        connect(cls.uid)
        calendars.add(cls.uid, calendars.entry({"name": "Abo", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/abo.ics"}))

    @classmethod
    def tearDownClass(cls):
        clean()
        helpers.set_config(calendar_share=False)

    def setUp(self):
        clean()

    def view(self, c=None):
        calendars._cache.clear()
        return (c or self.c).get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7, "tz": TZ}).json()

    def add(self, **kw):
        body = dict({"title": "Zahnarzt Aendern", "start": "2026-03-12T10:00", "end": "2026-03-12T10:45",
                     "location": "Praxis", "tz": TZ}, **kw)
        return self.c.post("/api/profile/calendar/event", json=body)

    def mine(self, d):
        return [x for x in d["events"] if "Aendern" in x["title"]]

    def test_add_change_delete(self):
        r = self.add()
        self.assertEqual(r.status_code, 200, r.text)
        d = self.view()
        self.assertEqual(d["edit"], [0])
        self.assertEqual(d["add"], [0])        # never the iCal link
        x = self.mine(d)[0]
        self.assertEqual((x["title"], x["location"], x["end"] - x["start"], x["edit"]), ("Zahnarzt Aendern", "Praxis", 2700, True))
        r = self.c.put("/api/profile/calendar/event", json={
            "change": "edit", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ,
            "new": {"title": "Zahnarzt Aendern spät", "start": "2026-03-13T15:00", "end": "2026-03-13T16:00", "location": ""}})
        self.assertEqual(r.status_code, 200, r.text)
        y = self.mine(self.view())[0]
        self.assertEqual((y["title"], y["location"], y["end"] - y["start"]), ("Zahnarzt Aendern spät", "", 3600))
        self.assertEqual(y["start"] - x["start"], 29 * 3600)
        # the old place and title are gone: the page's old view no longer finds it
        r = self.c.put("/api/profile/calendar/event", json={"change": "delete", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ})
        self.assertEqual(r.status_code, 409)
        r = self.c.put("/api/profile/calendar/event", json={"change": "delete", "cal": y["cal"], "title": y["title"], "start": y["start"], "tz": TZ})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.mine(self.view()), [])
        self.assertGreaterEqual(calendars.page_today(), 3)   # Live: a number of changes, never which

    def test_all_day(self):
        self.assertEqual(self.add(allday=True, start="2026-03-11", end="2026-03-13").status_code, 200)
        x = self.mine(self.view())[0]
        self.assertTrue(x["allday"])
        self.assertEqual(x["end"] - x["start"], 2 * 86400)

    def test_refused(self):
        self.assertEqual(self.add(title=" ").status_code, 400)
        self.assertEqual(self.add(end="2026-03-12T09:00").status_code, 400)
        self.assertEqual(self.add(start="morgen").status_code, 400)
        self.assertEqual(self.add(calendar="Gibt es nicht").status_code, 400)
        self.assertEqual(self.c.put("/api/profile/calendar/event", json={"change": "alles", "cal": 0}).status_code, 400)
        helpers.CAL_EVENTS[REPEAT[0]] = REPEAT[1]
        x = self.mine(self.view())[0]
        self.assertFalse(x["edit"])           # a repeating one is never changed on the page
        r = self.c.put("/api/profile/calendar/event", json={"change": "delete", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ})
        self.assertEqual(r.status_code, 409)
        self.assertIn(REPEAT[0], helpers.CAL_EVENTS)
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/calendar/event", json={"title": "x"}).status_code, (401, 403))

    def test_a_shared_calendar_is_never_changed_by_the_other(self):
        other, oid = profile("Aendern Olaf")
        cid = calendars.get(self.uid)["calendars"][0]["id"]
        calendars.set_share(self.uid, cid, oid, "add")
        try:
            self.assertEqual(self.add().status_code, 200)
            d = self.view(other)
            x = self.mine(d)[0]
            self.assertFalse(x["edit"])
            self.assertEqual(d["edit"], [])
            self.assertEqual(d["add"], [0])   # "add": the form may enter there
            r = other.put("/api/profile/calendar/event", json={"change": "delete", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(len(self.mine(self.view())), 1)
            r = other.post("/api/profile/calendar/event", json={"title": "Probe Aendern", "start": "2026-03-10T18:00", "end": "2026-03-10T19:00",
                                                                "calendar": d["calendars"][0], "tz": TZ})
            self.assertEqual(r.status_code, 200, r.text)
            # without naming it, nothing goes into someone else's calendar
            r = other.post("/api/profile/calendar/event", json={"title": "Probe Aendern 2", "start": "2026-03-10T18:00", "end": "2026-03-10T19:00", "tz": TZ})
            self.assertEqual(r.status_code, 400)
        finally:
            calendars.set_share(self.uid, cid, oid, "")


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        clean()

    def test_new_change_delete_on_the_page(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    if not calendars.get(uid)["calendars"]:
                        connect(uid)
                    await pg.evaluate("CAL_ON=true;icTabSet('cal','show');KAL.day=new Date(2026,2,10);KAL.view='list';goSec('cal')")
                    await b.until(pg, "!KAL.busy&&!!KAL.data&&KAL.data.add&&KAL.data.add.length>0")
                    await pg.click("#kalview [data-k=new]")
                    await pg.fill("#kalview [data-f=title]", "Elternabend Aendern")
                    await pg.fill("#kalview [data-f=sd]", "2026-03-11")
                    await pg.fill("#kalview [data-f=st]", "19:00")
                    await pg.fill("#kalview [data-f=ed]", "2026-03-11")
                    await pg.fill("#kalview [data-f=et]", "20:30")
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1, "the form scrolls sideways")
                    await pg.click("#kalview [data-act=save]")
                    await b.until(pg, "!KAL.busy&&KAL.data.events.some(x=>x.title==='Elternabend Aendern'&&x.edit)")
                    await pg.evaluate("document.querySelector('#kalview .kli[data-i]') && [...document.querySelectorAll('#kalview .kli[data-i]')].find(e=>e.textContent.includes('Elternabend')).click()")
                    await b.until(pg, "!!document.querySelector('#kalview .kaldet [data-act=edit]')")
                    await pg.click("#kalview .kaldet [data-act=edit]")
                    await pg.fill("#kalview [data-f=title]", "Elternabend Aendern neu")
                    await pg.click("#kalview [data-act=save]")
                    await b.until(pg, "!KAL.busy&&KAL.data.events.some(x=>x.title==='Elternabend Aendern neu')")
                    pg.on("dialog", lambda dlg: asyncio.ensure_future(dlg.accept()))
                    await pg.evaluate("[...document.querySelectorAll('#kalview .kli[data-i]')].find(e=>e.textContent.includes('Elternabend')).click()")
                    await b.until(pg, "!!document.querySelector('#kalview .kaldet [data-act=del]')")
                    await pg.click("#kalview .kaldet [data-act=del]")
                    await b.until(pg, "!KAL.busy&&!KAL.data.events.some(x=>x.title.startsWith('Elternabend'))")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
