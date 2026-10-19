"""Spark-Kalender, Stufe 4 (Dominik 2026-10-19 „1a-5a“): the Spark as a CalDAV server for calendar apps.

- Off by default: without the admin switch /caldav and /.well-known/caldav do not exist (404).
- An app password per profile, only in the own login (with the code), shown once, only its hash on the disk;
  „Zugang löschen“ ends it at once, a new one replaces the old one. Guests never.
- The door: HTTP Basic (profile id, app password); wrong guesses lock like a PIN; a web page of another site is
  refused; a profile the admin blocked, or with Mein Notaus on, gets nothing.
- Only the profile's own Spark calendars under its own path: another profile's path, another profile's calendar
  and an iCloud entry are 404.
- CalDAV as a calendar app speaks it: discovery (well-known, principal, calendar home), PROPFIND, REPORT
  calendar-query and calendar-multiget, GET, PUT, DELETE with etags; a change shows on the page Kalender at once.
  The panel's own CalDAV client (calendars._calendars, _report) finds and reads it like any server.
- The page (390 px): Kalender → Einstellungen „Für Kalender-Apps“ shows server and user, makes the app password
  (shown once), „Zugang löschen“ asks first.

Fixed dates (2026-03); no wall clock.
"""
import asyncio
import base64
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import httpx  # noqa: E402
import kalenderserver  # noqa: E402
import notaus  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TZ = "Europe/Berlin"
EVENT = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iOS 26//EN\r\nBEGIN:VEVENT\r\nUID:dav-1\r\n"
         "DTSTART;TZID=Europe/Berlin:20260311T090000\r\nDTEND;TZID=Europe/Berlin:20260311T100000\r\n"
         "SUMMARY:Friseur Davida\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
FIND = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_server=True)
        cls.c, cls.uid = profile("Davida Dahl")
        cls.o, cls.oid = profile("Davida Olsen")
        cls.cal = next(x for x in cls.c.post("/api/profile/calendar", json={"spark": True, "name": "Zuhause"}).json()["calendars"]
                       if x["spark"])
        cls.ocal = next(x for x in cls.o.post("/api/profile/calendar", json={"spark": True, "name": "Fremd"}).json()["calendars"]
                        if x["spark"])
        r = cls.c.post("/api/profile/calserver")
        assert r.status_code == 200, r.text
        cls.pw = r.json()["password"]
        cls.dav = TestClient(panel.app)
        cls.dav.headers.update(basic(cls.uid, cls.pw))

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(calendar_server=False)
        guard.reset()

    def setUp(self):
        guard.reset()

    def base(self):
        return f"/caldav/{self.uid}/{self.cal['id']}/"

    def test_password_once_and_only_its_hash(self):
        d = self.c.get("/api/profile/calserver").json()
        self.assertEqual((d["has"], d["user"], d["path"], d["calendars"]), (True, self.uid, "/caldav/", 1))
        self.assertNotIn("password", d)
        with open(kalenderserver._file(self.uid)) as f:
            raw = f.read()
        self.assertNotIn(self.pw, raw)
        self.assertEqual(oct(os.stat(kalenderserver._file(self.uid)).st_mode & 0o777), "0o600")
        self.assertRegex(self.pw, r"^([a-z2-9]{4}-){4}[a-z2-9]{4}$")
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/calserver").status_code, (401, 403))

    def test_discovery_like_a_calendar_app(self):
        r = self.dav.request("PROPFIND", "/.well-known/caldav", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (301, "/caldav/"))
        r = self.dav.request("PROPFIND", "/caldav/", content=FIND, headers={"Depth": "0"})
        self.assertEqual(r.status_code, 207)
        self.assertIn(f"<d:href>/caldav/{self.uid}/</d:href></d:current-user-principal>", r.text)
        r = self.dav.request("PROPFIND", f"/caldav/{self.uid}/", headers={"Depth": "1"})
        self.assertEqual(r.status_code, 207)
        self.assertIn("calendar-home-set", r.text)
        self.assertIn(f"<d:href>{self.base()}</d:href>", r.text)
        self.assertIn("<d:displayname>Zuhause</d:displayname>", r.text)
        self.assertIn("<d:write/>", r.text)
        self.assertNotIn(self.ocal["id"], r.text)   # never another profile's calendar

    def test_put_report_get_delete_and_the_page(self):
        href = self.base() + "dav-1.ics"
        r = self.dav.put(href, content=EVENT, headers={"If-None-Match": "*", "Content-Type": "text/calendar"})
        self.assertEqual(r.status_code, 201, r.text)
        tag = r.headers["etag"]
        view = self.c.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7, "tz": TZ}).json()
        self.assertIn("Friseur Davida", [x["title"] for x in view["events"]])   # on the page at once
        q = (b'<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/></d:prop>'
             b'<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="20260301T000000Z" '
             b'end="20260401T000000Z"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        r = self.dav.request("REPORT", self.base(), content=q, headers={"Depth": "1"})
        self.assertIn(f"<d:href>{href}</d:href>", r.text)
        r = self.dav.request("PROPFIND", self.base(), headers={"Depth": "1"})
        self.assertIn(tag.replace('"', "&quot;") if "&quot;" in r.text else tag, r.text)
        m = (b'<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/>'
             b'<c:calendar-data/></d:prop><d:href>' + href.encode() + b'</d:href><d:href>' + self.base().encode()
             + b'nix.ics</d:href></c:calendar-multiget>')
        r = self.dav.request("REPORT", self.base(), content=m, headers={"Depth": "1"})
        self.assertIn("Friseur Davida", r.text)
        self.assertIn("404 Not Found", r.text)
        self.assertEqual(self.dav.get(href).text, EVENT)
        self.assertEqual(self.dav.request("DELETE", href, headers={"If-Match": '"alt"'}).status_code, 412)
        self.assertEqual(self.dav.request("DELETE", href, headers={"If-Match": tag}).status_code, 204)
        view = self.c.get("/api/profile/calendar/view", params={"start": "2026-03-09", "days": 7, "tz": TZ}).json()
        self.assertNotIn("Friseur Davida", [x["title"] for x in view["events"]])

    def test_only_the_own_spark_calendars(self):
        for path in (f"/caldav/{self.oid}/", f"/caldav/{self.oid}/{self.ocal['id']}/",
                     f"/caldav/{self.uid}/{self.ocal['id']}/", f"/caldav/{self.uid}/c00000000/",
                     f"/caldav/{self.uid}/{self.cal['id']}/../x.ics", f"/caldav/{self.uid}/{self.cal['id']}/a/b/c.ics"):
            self.assertEqual(self.dav.request("PROPFIND", path, headers={"Depth": "1"}).status_code, 404, path)
        self.assertEqual(self.dav.put(self.base() + "x.ics", content=b"<html>").status_code, 415)
        self.assertEqual(self.dav.request("MKCALENDAR", f"/caldav/{self.uid}/neu/").status_code, 404)
        self.assertEqual(self.dav.request("PROPPATCH", self.base()).status_code, 403)

    def test_the_door(self):
        anon = TestClient(panel.app)
        r = anon.request("PROPFIND", "/caldav/")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Basic", r.headers["www-authenticate"])
        self.assertEqual(anon.request("PROPFIND", "/caldav/", headers=basic(self.oid, self.pw)).status_code, 401)
        r = self.dav.request("PROPFIND", "/caldav/", headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        codes = [anon.request("PROPFIND", "/caldav/", headers=basic(self.uid, "falsch-falsch")).status_code for _ in range(7)]
        self.assertEqual(codes[-1], 429)   # locked like a PIN
        guard.reset()
        real = notaus.own
        notaus.own = lambda uid: uid == self.uid
        try:
            self.assertEqual(self.dav.request("PROPFIND", "/caldav/").status_code, 503)
        finally:
            notaus.own = real
        real_allowed = features.allowed
        features.allowed = lambda key, uid=None: key != "calserver" and real_allowed(key, uid)
        try:
            self.assertEqual(self.dav.request("PROPFIND", "/caldav/").status_code, 403)
        finally:
            features.allowed = real_allowed

    def test_off_means_not_there(self):
        helpers.set_config(calendar_server=False)
        try:
            self.assertEqual(self.dav.request("PROPFIND", "/caldav/").status_code, 404)
            self.assertEqual(self.dav.request("PROPFIND", "/.well-known/caldav", follow_redirects=False).status_code, 404)
            self.assertEqual(self.c.get("/api/profile/calserver").status_code, 403)
        finally:
            helpers.set_config(calendar_server=True)

    def test_a_new_password_replaces_and_delete_ends(self):
        other, oid = profile("Davida Neu")
        pw1 = other.post("/api/profile/calserver").json()["password"]
        pw2 = other.post("/api/profile/calserver").json()["password"]
        anon = TestClient(panel.app)
        self.assertEqual(anon.request("PROPFIND", "/caldav/", headers=basic(oid, pw1)).status_code, 401)
        self.assertEqual(anon.request("PROPFIND", "/caldav/", headers=basic(oid, pw2)).status_code, 207)
        r = other.delete("/api/profile/calserver")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["has"])
        guard.reset()
        self.assertEqual(anon.request("PROPFIND", "/caldav/", headers=basic(oid, pw2)).status_code, 401)

    def test_the_panels_own_caldav_client_finds_it(self):
        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=panel.app), base_url="http://testserver",
                                         auth=(self.uid, self.pw)) as c:
                found = await calendars._calendars(c, "http://testserver/caldav/")
                put = await c.put(f"http://testserver{self.base()}dav-2.ics", content=EVENT.replace("dav-1", "dav-2"))
                import datetime
                texts = await calendars._report(c, found[0][0], datetime.datetime(2026, 3, 1, tzinfo=datetime.timezone.utc),
                                                datetime.datetime(2026, 4, 1, tzinfo=datetime.timezone.utc))
                await c.delete(f"http://testserver{self.base()}dav-2.ics")
                return found, put.status_code, texts
        found, status, texts = asyncio.run(go())
        self.assertEqual(found, [(f"http://testserver{self.base()}", "Zuhause")])
        self.assertEqual(status, 201)
        self.assertEqual(len(texts), 1)
        self.assertIn("dav-2", texts[0])

    def test_live_numbers_only(self):
        d = kalenderserver.for_live()
        self.assertEqual(set(d), {"on", "profiles", "requests", "refused", "saved"})
        self.assertGreaterEqual(d["profiles"], 1)
        json.dumps(d)


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_server=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(calendar_server=False)

    def test_make_and_delete_on_the_page(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    await pg.evaluate("CAL_ON=true;goSec('cal');document.getElementById('calbox').hidden=false;showCal()")
                    await b.until(pg, "!!document.querySelector('#calserver [data-srv=make]')")
                    self.assertEqual(await pg.text_content("#calsrvuser"), uid)
                    self.assertTrue((await pg.text_content("#calsrvurl")).endswith("/caldav/"))
                    await pg.click("#calserver [data-srv=make]")
                    await b.until(pg, "!!document.getElementById('calsrvpw')")
                    pw = await pg.text_content("#calsrvpw")
                    self.assertTrue(kalenderserver.hmac.compare_digest(kalenderserver._load(uid)["hash"], kalenderserver._hash(pw)))
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1, "the box scrolls sideways")
                    pg.on("dialog", lambda dlg: asyncio.ensure_future(dlg.accept()))
                    await pg.click("#calserver [data-srv=drop]")
                    await b.until(pg, "!document.querySelector('#calserver [data-srv=drop]')")
                    self.assertIsNone(kalenderserver._load(uid))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
