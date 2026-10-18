"""Kalender teilen (Dominik 2026-10-18 „1a 2a“): a profile shares one of its calendars with another profile, "see" or
"add" (see and enter), under Kalender → Einstellungen; the function is off until the admin switches it on.

- Only the owner's browser login shares, only with another existing profile, only its own calendars; taking it back
  works at once; guests and the switched-off function get nothing.
- The other profile reads the shared calendar on the page and through the assistant as "<owner> · <calendar>"; a
  private appointment (CLASS PRIVATE) shows there only as „belegt“ with its time, without place; the owner still sees
  it in full. A third profile sees nothing, and the briefing (events without shared) stays with the own calendars.
- "add" lets the other profile's assistant enter an appointment there, only when it names that calendar; "see" never.
- Live counts the shares in numbers only. The Weiche takes „Was hat Sabine morgen?“ to the calendar.

Fixed dates, the fake CalDAV server; no wall clock.
"""
import asyncio
import datetime
import unittest
from zoneinfo import ZoneInfo

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import intent  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ZONE = ZoneInfo("Europe/Berlin")
EV = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:{uid}\r\n"
      "DTSTART;TZID=Europe/Berlin:20260311T{h}0000\r\nDTEND;TZID=Europe/Berlin:20260311T{h}3000\r\n"
      "SUMMARY:{title}\r\nLOCATION:{where}\r\n{cls}END:VEVENT\r\nEND:VCALENDAR\r\n")
OPEN = ("/dav/privat/teilen-1.ics", EV.format(uid="teilen-1", h="09", title="Elternabend Teilen", where="Schule", cls=""))
SECRET = ("/dav/privat/teilen-2.ics", EV.format(uid="teilen-2", h="14", title="Arzt Teilen", where="Praxis Teilen",
                                               cls="CLASS:PRIVATE\r\n"))


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def week(uid, shared=True):
    t0 = datetime.datetime(2026, 3, 9, tzinfo=ZONE)
    return asyncio.run(calendars.events(uid, t0, t0 + datetime.timedelta(days=7), ZONE, shared=shared))


class Share(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_share=True)
        helpers.CAL_EVENTS.update([OPEN, SECRET])
        cls.tina, cls.tina_id = profile("Teil Tina")
        cls.tom, cls.tom_id = profile("Teil Tom")
        cls.udo, cls.udo_id = profile("Teil Udo")
        calendars.add(cls.tina_id, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                                    "user": "k", "password": "pw"}))
        cls.cid = calendars.get(cls.tina_id)["calendars"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        for k in [k for k in helpers.CAL_EVENTS if "teilen" in k or k.endswith(".ics") and "Teilen" in helpers.CAL_EVENTS[k]]:
            helpers.CAL_EVENTS.pop(k, None)
        helpers.set_config(calendar_share=False)

    def share(self, level, to=None, who=None, cid=None):
        return (who or self.tina).put(f"/api/profile/calendar/{cid or self.cid}/share", json={"to": to or self.tom_id, "level": level})

    def tearDown(self):
        self.share("")
        calendars._cache.clear()

    def test_see_shows_busy_for_private_and_nothing_for_others(self):
        r = self.share("see")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["calendars"][0]["shares"], {self.tom_id: "see"})
        self.assertIn({"id": self.tom_id, "name": "Teil Tom"}, r.json()["people"])
        self.assertNotIn(self.tina_id, [p["id"] for p in r.json()["people"]])
        d = self.tom.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7, "tz": "Europe/Berlin"}).json()
        self.assertEqual(d["calendars"], ["Teil Tina · Privat"])
        self.assertEqual(d["shared"], [0])
        got = {(x["title"], x["location"]) for x in d["events"]}
        self.assertIn(("Elternabend Teilen", "Schule"), got)
        self.assertIn((calendars.BUSY, ""), got)
        self.assertNotIn("Arzt Teilen", str(d))
        self.assertNotIn("Praxis Teilen", str(d))
        # what Tom's Kalender → Einstellungen names, never the address or the password
        mine = self.tom.get("/api/profile/calendar").json()
        self.assertEqual(mine["shared"], [{"owner": "Teil Tina", "name": "Privat", "level": "see"}])
        self.assertNotIn("127.0.0.1", str(mine["shared"]))
        # the owner sees it in full, a third profile nothing
        own = {x["title"] for x in self.tina.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7}).json()["events"]}
        self.assertIn("Arzt Teilen", own)
        self.assertFalse(self.udo.get("/api/profile/calendar/view", params={"start": "2026-03-09"}).json()["connected"])

    def test_the_assistant_reads_it_by_name_and_the_briefing_does_not(self):
        self.share("see")
        evs, errors = week(self.tom_id)
        lines = [calendars.line(x) for x in evs]
        self.assertTrue(any("Elternabend Teilen" in x and "[Teil Tina · Privat]" in x for x in lines), lines)
        self.assertTrue(any(x.startswith("Mi 11.03. 14:00") and calendars.BUSY in x for x in lines), lines)
        self.assertNotIn("Arzt", " ".join(lines))
        self.assertIsNone(week(self.tom_id, shared=False))   # briefing, Von selbst: only the own calendars
        self.assertTrue(intent.CALENDAR_WORDS.search("Was hat Sabine morgen?"))
        self.assertTrue(intent.CALENDAR_WORDS.search("Hat Tom am Freitag Zeit?"))
        self.assertFalse(intent.CALENDAR_WORDS.search("Hat Lidl heute offen?"))

    def test_taking_back_works_at_once(self):
        self.share("see")
        self.assertTrue(self.tom.get("/api/profile/calendar/view", params={"start": "2026-03-09"}).json()["connected"])
        self.assertEqual(self.share("").json()["calendars"][0]["shares"], {})
        self.assertFalse(self.tom.get("/api/profile/calendar/view", params={"start": "2026-03-09"}).json()["connected"])
        self.assertEqual(self.tom.get("/api/profile/calendar").json()["shared"], [])

    def test_add_only_when_named_and_never_with_see(self):
        item = {"title": "Probe Teilen", "start": "2026-03-12T18:00:00+01:00", "end": "2026-03-12T19:00:00+01:00",
                "calendar": "Teil Tina · Privat"}
        self.share("see")
        with self.assertRaises(ValueError):
            asyncio.run(calendars.add_event(self.tom_id, item))
        self.share("add")
        before = set(helpers.CAL_EVENTS)
        self.assertEqual(asyncio.run(calendars.add_event(self.tom_id, item)), "Teil Tina · Privat")
        new = set(helpers.CAL_EVENTS) - before
        self.assertEqual(len(new), 1)
        self.assertIn("Probe Teilen", helpers.CAL_EVENTS[new.pop()])
        self.assertIn("Kalender: Teil Tina · Privat", calendars.describe(item))
        # „in Tinas Kalender“ names it too; without a name it never goes into someone else's calendar
        self.assertEqual(asyncio.run(calendars.add_event(self.tom_id, dict(item, calendar="Teil Tinas Kalender"))), "Teil Tina · Privat")
        with self.assertRaises(ValueError):
            asyncio.run(calendars.add_event(self.tom_id, dict(item, calendar="")))

    def test_refused(self):
        self.assertEqual(self.share("see", to=self.tina_id).status_code, 400)        # not with oneself
        self.assertEqual(self.share("see", to="u-gibt-es-nicht").status_code, 400)
        self.assertEqual(self.share("alles").status_code, 400)
        self.assertEqual(self.share("see", cid="c-fremd").status_code, 404)
        self.assertEqual(self.share("see", to=self.udo_id, who=self.tom).status_code, 404)         # Tina's calendar is not Tom's
        guest = TestClient(panel.app)
        self.assertIn(self.share("see", who=guest).status_code, (401, 403))
        helpers.set_config(calendar_share=False)
        try:
            self.assertEqual(self.share("see").status_code, 403)
            self.assertNotIn("people", self.tina.get("/api/profile/calendar").json())
            self.assertEqual(calendars.shared_to(self.tom_id), [])
            self.assertEqual(calendars.for_live(), {"on": False})
        finally:
            helpers.set_config(calendar_share=True)

    def test_live_counts_only(self):
        self.share("add")
        calendars._live[0] = 0.0
        live = calendars.for_live()
        self.assertEqual(live, {"on": True, "shares": 1, "owners": 1})


@unittest.skipUnless(__import__("os").environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    """Kalender → Einstellungen: „Teilen“ at each calendar with a choice per other profile; „Mit dir geteilt“."""
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_share=True)
        _, cls.other = profile("Teil Vera")
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(calendar_share=False)

    def test_share_from_the_settings(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    me = await pg.evaluate("PROFILE.id")
                    if not calendars.get(me)["calendars"]:
                        calendars.add(me, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/"}))
                    cid = calendars.get(me)["calendars"][0]["id"]
                    await pg.evaluate("CAL_ON=true;showCal()")
                    sel = f"#callist select[data-cal='{cid}'][data-to='{self.other}']"
                    await pg.wait_for_selector(sel, state="attached", timeout=20000)
                    self.assertEqual(await pg.eval_on_selector(sel, "e=>e.value"), "")
                    await pg.evaluate(f"(()=>{{const s=document.querySelector(\"{sel}\");s.value='add';s.dispatchEvent(new Event('change'))}})()")
                    await b.until(pg, "$('calmsg').textContent.length>0")
                    self.assertEqual(calendars.get(me)["calendars"][0].get("shares"), {self.other: "add"})
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1)
                    self.assertEqual(errors, [])
                finally:
                    calendars.set_share(me, cid, self.other, "")
                    await br.close()
        asyncio.run(go())

if __name__ == "__main__":
    unittest.main()
