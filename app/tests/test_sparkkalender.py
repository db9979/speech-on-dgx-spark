"""Spark-Kalender, Stufe 3 (Dominik 2026-10-19 „5a“): a calendar that lives only on the Spark.

- POST /api/profile/calendar {"spark": true} makes one; the page, the assistant's way and the view use it like any
  CalDAV calendar: add, change, delete, a shared one read by another profile.
- Bound: the client of one entry answers only for that entry; another entry id, another host or an odd object name
  is 404; a PUT that is no iCalendar with an appointment is refused; etags guard a change made meanwhile.
- Kept only encrypted in the profile folder, read back after a restart; removing the entry deletes its appointments.
- The form for an address never takes spark.invalid; a guest never makes one.
- The page (390 px): provider „Spark-Kalender“ hides the address, „Anlegen“ makes it, „Entfernen“ asks first.

Fixed dates (2026-03); no wall clock.
"""
import asyncio
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import sparkkalender  # noqa: E402
import vault  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TZ = "Europe/Berlin"
EVENT = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:spark-1\r\n"
         "DTSTART;TZID=Europe/Berlin:20260310T103000\r\nDTEND;TZID=Europe/Berlin:20260310T120000\r\n"
         "SUMMARY:Zahnarzt Funkel\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def ask(uid, cid, method, path, body=b"", **headers):
    async def go():
        async with sparkkalender.client(uid, cid) as c:
            return await c.request(method, path, content=body, headers=headers)
    return asyncio.run(go())


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_share=True)
        cls.c, cls.uid = profile("Funkel Frida")
        for x in calendars.get(cls.uid)["calendars"]:
            calendars.remove(cls.uid, x["id"])
        r = cls.c.post("/api/profile/calendar", json={"spark": True, "name": "Zuhause"})
        assert r.status_code == 200, r.text
        cls.cal = next(x for x in r.json()["calendars"] if x["spark"])

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(calendar_share=False)

    def view(self, c=None):
        calendars._cache.clear()
        return (c or self.c).get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7, "tz": TZ}).json()

    def mine(self, d):
        return [x for x in d["events"] if "Funkel" in x["title"]]

    def test_add_change_delete_on_the_page(self):
        self.assertEqual(self.cal["name"], "Zuhause")
        self.assertTrue(self.cal["url"].startswith("https://spark.invalid/"))
        r = self.c.post("/api/profile/calendar/event", json={"title": "Zahnarzt Funkel", "start": "2026-03-12T10:00",
                                                             "end": "2026-03-12T10:45", "location": "Praxis", "tz": TZ})
        self.assertEqual(r.status_code, 200, r.text)
        d = self.view()
        self.assertIn(0, d["edit"])
        x = self.mine(d)[0]
        self.assertEqual((x["title"], x["location"], x["end"] - x["start"]), ("Zahnarzt Funkel", "Praxis", 2700))
        r = self.c.put("/api/profile/calendar/event", json={
            "change": "edit", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ,
            "new": {"title": "Zahnarzt Funkel spät", "start": "2026-03-13T15:00", "end": "2026-03-13T16:00", "location": ""}})
        self.assertEqual(r.status_code, 200, r.text)
        y = self.mine(self.view())[0]
        self.assertEqual((y["title"], y["end"] - y["start"]), ("Zahnarzt Funkel spät", 3600))
        # only encrypted on the disk, and read back after a restart (memory dropped)
        with open(sparkkalender._file(self.uid)) as f:
            raw = f.read()
        self.assertNotIn("Funkel", raw)
        self.assertTrue(json.loads(raw)["enc"].startswith(vault.PREFIX))
        sparkkalender.drop_profile(self.uid)
        self.assertEqual([z["title"] for z in self.mine(self.view())], ["Zahnarzt Funkel spät"])
        r = self.c.put("/api/profile/calendar/event", json={"change": "delete", "cal": y["cal"], "title": y["title"],
                                                            "start": y["start"], "tz": TZ})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.mine(self.view()), [])

    def test_the_assistants_way(self):
        where = asyncio.run(calendars.add_event(self.uid, {"title": "Chor Funkel", "start": "2026-03-11T19:00",
                                                           "end": "2026-03-11T21:00", "tz": TZ, "calendar": "Zuhause"}))
        self.assertEqual(where, "Zuhause")
        self.assertEqual([x["title"] for x in self.mine(self.view())], ["Chor Funkel"])
        x = self.mine(self.view())[0]
        self.c.put("/api/profile/calendar/event", json={"change": "delete", "cal": x["cal"], "title": x["title"],
                                                        "start": x["start"], "tz": TZ})

    def test_bound_and_checked(self):
        cid, other = self.cal["id"], "c00000000"
        base = f"https://spark.invalid/{cid}/"
        self.assertEqual(ask(self.uid, cid, "GET", f"https://spark.invalid/{other}/x.ics").status_code, 404)
        self.assertEqual(ask(self.uid, cid, "GET", f"https://example.org/{cid}/x.ics").status_code, 404)
        self.assertEqual(ask("someone-else", cid, "PROPFIND", base).status_code, 404)   # not that profile's entry
        self.assertEqual(ask(self.uid, cid, "PUT", base + "../x.ics", EVENT.encode()).status_code, 404)
        self.assertEqual(ask(self.uid, cid, "PUT", base + "a b.ics", EVENT.encode()).status_code, 404)
        self.assertEqual(ask(self.uid, cid, "PUT", base + "x.ics", b"<script>").status_code, 415)
        self.assertEqual(ask(self.uid, cid, "PUT", base + "x.ics", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n").status_code, 415)
        r = ask(self.uid, cid, "PUT", base + "x.ics", EVENT.encode(), **{"If-None-Match": "*"})
        self.assertEqual(r.status_code, 201)
        tag = r.headers["etag"]
        self.assertEqual(ask(self.uid, cid, "PUT", base + "x.ics", EVENT.encode(), **{"If-None-Match": "*"}).status_code, 412)
        self.assertEqual(ask(self.uid, cid, "DELETE", base + "x.ics", **{"If-Match": '"old"'}).status_code, 412)
        self.assertEqual(ask(self.uid, cid, "GET", base + "x.ics").text, EVENT)
        self.assertEqual(ask(self.uid, cid, "MOVE", base + "x.ics").status_code, 405)
        self.assertEqual(ask(self.uid, cid, "DELETE", base + "x.ics", **{"If-Match": tag}).status_code, 204)
        self.assertEqual(ask(self.uid, cid, "GET", base + "x.ics").status_code, 404)

    def test_shared_with_another_profile(self):
        other, oid = profile("Funkel Fritz")
        calendars.set_share(self.uid, self.cal["id"], oid, "see")
        try:
            ask(self.uid, self.cal["id"], "PUT", self.cal["url"] + "s.ics", EVENT.encode())
            self.assertEqual([x["title"] for x in self.mine(self.view(other))], ["Zahnarzt Funkel"])
            x = self.mine(self.view(other))[0]
            r = other.put("/api/profile/calendar/event", json={"change": "delete", "cal": x["cal"], "title": x["title"],
                                                               "start": x["start"], "tz": TZ})
            self.assertEqual(r.status_code, 409)   # seeing is not changing
        finally:
            calendars.set_share(self.uid, self.cal["id"], oid, "")
            ask(self.uid, self.cal["id"], "DELETE", self.cal["url"] + "s.ics")

    def test_never_by_address_never_for_guests(self):
        with self.assertRaises(ValueError):
            calendars.entry({"url": f"https://spark.invalid/{self.cal['id']}/"})
        with self.assertRaises(ValueError):
            calendars.entry({"url": "https://SPARK.invalid./c12345678/"})
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/calendar", json={"spark": True}).status_code, (401, 403))

    def test_removing_it_deletes_its_appointments(self):
        r = self.c.post("/api/profile/calendar", json={"spark": True, "name": "Weg"})
        cal = next(x for x in r.json()["calendars"] if x["name"] == "Weg")
        ask(self.uid, cal["id"], "PUT", cal["url"] + "w.ics", EVENT.encode())
        self.c.delete(f"/api/profile/calendar/{cal['id']}")
        self.assertNotIn(cal["id"], sparkkalender._load(self.uid))
        sparkkalender.drop_profile(self.uid)
        self.assertNotIn(cal["id"], sparkkalender._load(self.uid))
        self.assertEqual(ask(self.uid, cal["id"], "GET", cal["url"] + "w.ics").status_code, 404)

    def test_without_the_key_none_is_made(self):
        real = vault.available
        vault.available = lambda: False
        try:
            r = self.c.post("/api/profile/calendar", json={"spark": True, "name": "Ohne"})
        finally:
            vault.available = real
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("Ohne", [x["name"] for x in calendars.public(self.uid)["calendars"]])

    def test_live_numbers_only(self):
        d = sparkkalender.for_live()
        self.assertEqual(set(d), {"calendars", "items"})
        self.assertTrue(all(isinstance(v, int) for v in d.values()))


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def test_make_and_remove_on_the_page(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    await pg.evaluate("CAL_ON=true;showCal();goSec('cal');document.getElementById('calbox').hidden=false;"
                                      "document.getElementById('caladd').open=true")
                    await b.until(pg, "!!document.querySelector('#calkind option[value=spark]')")
                    await pg.select_option("#calkind", "spark")
                    self.assertFalse(await pg.is_visible("#calurl"))
                    self.assertFalse(await pg.is_visible("#caluser"))
                    await pg.fill("#calname", "Garten")
                    await pg.click("#calsave")
                    await b.until(pg, "[...document.querySelectorAll('#callist .calc')].some(e=>e.textContent.includes('Garten'))")
                    cal = next(x for x in calendars.get(uid)["calendars"] if x["name"] == "Garten")
                    self.assertTrue(cal["spark"])
                    asked = []

                    def answer(dlg):
                        asked.append(dlg.message)
                        asyncio.ensure_future(dlg.accept())
                    pg.on("dialog", answer)
                    await pg.evaluate("calRemove(%s,'Garten',1)" % json.dumps(cal["id"]))
                    await b.until(pg, "![...document.querySelectorAll('#callist .calc')].some(e=>e.textContent.includes('Garten'))")
                    self.assertIn("gelöscht", asked[0])
                    self.assertNotIn(cal["id"], sparkkalender._load(uid))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
