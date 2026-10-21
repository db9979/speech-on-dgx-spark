"""Kalender wie Apple Kalender (Apple-Stil „4a“ „5a“, Dominik 2026-10-20): repeat, alert, people, note and link of an
appointment, a repeating one changed „Nur dieser Termin“ or „Alle künftigen“, „Rückgängig“ after every save.

- kalserie.py on fixed iCal texts: reading the fields, checking the page's fields (only those it names: a move or an
  older app keeps the rest), one occurrence deleted (EXDATE) or changed (RECURRENCE-ID), all future ones from the first
  (the series itself) or from a later one (the old series ends before it, a new one goes on, COUNT counted down).
- People are written with SCHEDULE-AGENT=CLIENT: the calendar server sends no invitation.
- PUT /api/profile/calendar/event with uid, rid and scope on the fake CalDAV server; a wrong rid gives 409, another
  profile never reaches the series; the undo token puts the old objects back once, then 410.
- The page: drag in free time makes an appointment, the year view, the series question, the phone's week strip.

Fixed dates (2026-03), the fake CalDAV server; no wall clock.
"""
import asyncio
import datetime
import unittest
import zoneinfo

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import guard  # noqa: E402
import icalendar  # noqa: E402
import kalserie  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TZ = "Europe/Berlin"
ZONE = zoneinfo.ZoneInfo(TZ)
HREF = "/dav/privat/serie-rr.ics"


def series(rule="FREQ=WEEKLY", extra=""):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:serie-rr\r\n"
            "DTSTART;TZID=Europe/Berlin:20260302T080000\r\nDTEND;TZID=Europe/Berlin:20260302T083000\r\n"
            f"RRULE:{rule}\r\n{extra}SUMMARY:Joggen Serie\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


def epoch(y, m, d, h=8, mi=0):
    return int(datetime.datetime(y, m, d, h, mi, tzinfo=ZONE).timestamp())


def item(title="Joggen Serie", start="2026-03-09T08:00", end="2026-03-09T08:30", **kw):
    return calendars.page_item(dict({"title": title, "start": start, "end": end}, **kw), ZONE)


def starts(text, a="2026-03-01", b="2026-04-30"):
    import recurring_ical_events
    cal = icalendar.Calendar.from_ical(text)
    return sorted((str(x.get("SUMMARY")), x.get("DTSTART").dt.astimezone(ZONE).strftime("%m-%d %H:%M"))
                  for x in recurring_ical_events.of(cal).between(datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)))


class Fields(unittest.TestCase):
    def test_read_rule_alarm_people(self):
        ev = icalendar.Calendar.from_ical(series("FREQ=WEEKLY;INTERVAL=2;UNTIL=20260601T000000Z",
                                                 "ATTENDEE;CN=Anna:mailto:anna@example.org\r\nATTENDEE:mailto:kaputt\r\n"
                                                 "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT30M\r\nEND:VALARM\r\n")).walk("VEVENT")[0]
        self.assertEqual(kalserie.rule_of(ev), ("biweekly", "2026-06-01"))
        self.assertEqual(kalserie.alarm_of(ev), 30)
        self.assertEqual(kalserie.people_of(ev), [{"name": "Anna", "mail": "anna@example.org"}])
        for r in ("FREQ=WEEKLY;BYDAY=MO,WE", "FREQ=DAILY;COUNT=5", "FREQ=WEEKLY;INTERVAL=3"):
            self.assertEqual(kalserie.rule_of(icalendar.Calendar.from_ical(series(r)).walk("VEVENT")[0])[0], "custom", r)

    def test_page_fields_are_checked(self):
        s = datetime.datetime(2026, 3, 9, 8, tzinfo=ZONE)
        self.assertEqual(kalserie.people(["Anna Muster <anna@example.org>", "bert@example.org", {"name": "x", "mail": "ANNA@example.org"}]),
                         [{"name": "Anna Muster", "mail": "anna@example.org"}, {"name": "", "mail": "bert@example.org"}])
        for bad in (["anna"], ["<script>@x"], ["a@b"], [f"p{i}@example.org" for i in range(21)]):
            with self.assertRaises(ValueError):
                kalserie.people(bad)
        for body in ({"rule": "hourly"}, {"rule": "weekly", "until": "2026-03-01"}, {"rule": "weekly", "until": "2040-01-01"},
                     {"alarm": -5}, {"alarm": "bald"}, {"link": "javascript:alert(1)"}, {"link": "ftp://x"}):
            with self.assertRaises(ValueError, msg=body):
                kalserie.fields(body, s)
        # only what the page names: a move (title and times) keeps note, people, alert and rule as they are
        self.assertEqual(kalserie.fields({"title": "x"}, s), {})
        self.assertEqual(kalserie.fields({"note": "a\x07b\r\nc", "rule": "", "until": "2026-04-01"}, s),
                         {"note": "ab\nc", "rule": "", "until": ""})

    def test_people_get_no_invitation_and_a_move_keeps_the_rest(self):
        text = kalserie.new_calendar(item(start="2026-03-12T10:00", end="2026-03-12T11:00", note="Unterlagen", link="https://example.org/t",
                                          alarm=15, people=["Anna <anna@example.org>"]), "neu-serie").decode()
        flat = text.replace("\r\n ", "")
        self.assertIn("SCHEDULE-AGENT=CLIENT", flat)
        self.assertIn("mailto:anna@example.org", flat)
        moved = kalserie.change_single(text, item(start="2026-03-13T10:00", end="2026-03-13T11:00"))
        ev = icalendar.Calendar.from_ical(moved).walk("VEVENT")[0]
        self.assertEqual((str(ev["DESCRIPTION"]), str(ev["URL"]), kalserie.alarm_of(ev), len(kalserie.people_of(ev))),
                         ("Unterlagen", "https://example.org/t", 15, 1))
        self.assertEqual(int(ev["SEQUENCE"]), 1)
        cleared = kalserie.change_single(moved, item(start="2026-03-13T10:00", end="2026-03-13T11:00", note="", people=[], alarm=0))
        ev = icalendar.Calendar.from_ical(cleared).walk("VEVENT")[0]
        self.assertEqual((ev.get("DESCRIPTION"), kalserie.alarm_of(ev), kalserie.people_of(ev)), (None, 0, []))
        # a repeat rule makes the single one a series, in its own zone (the hour stays across summer time)
        rep = kalserie.change_single(text, item(start="2026-03-12T10:00", end="2026-03-12T11:00", rule="weekly", until="2026-04-30", zone=TZ))
        self.assertEqual(starts(rep, b="2026-06-30")[-1], ("Joggen Serie", "04-30 10:00"))   # ends with its last day
        self.assertIn("BEGIN:VTIMEZONE", rep)


class Series(unittest.TestCase):
    def test_only_this_one(self):
        gone = kalserie.change_one(series(), "serie-rr", epoch(2026, 3, 9), None, ZONE)
        self.assertNotIn(("Joggen Serie", "03-09 08:00"), starts(gone))
        self.assertIn(("Joggen Serie", "03-16 08:00"), starts(gone))
        late = kalserie.change_one(series(), "serie-rr", epoch(2026, 3, 9), item(title="Joggen Serie spät", start="2026-03-09T18:00",
                                                                                  end="2026-03-09T18:30"), ZONE)
        got = starts(late)
        self.assertIn(("Joggen Serie spät", "03-09 18:00"), got)
        self.assertIn(("Joggen Serie", "03-16 08:00"), got)
        self.assertEqual(len(got), len(starts(series())))
        with self.assertRaises(LookupError):   # no occurrence at that time
            kalserie.change_one(series(), "serie-rr", epoch(2026, 3, 10), None, ZONE)
        with self.assertRaises(LookupError):
            kalserie.change_one(series(), "andere", epoch(2026, 3, 9), None, ZONE)

    def test_all_future_from_the_first_is_the_series(self):
        rest, new = kalserie.change_future(series(), "serie-rr", epoch(2026, 3, 2), item(start="2026-03-02T07:00", end="2026-03-02T07:30"), ZONE, "x")
        self.assertIsNone(new)
        self.assertEqual(starts(rest)[:2], [("Joggen Serie", "03-02 07:00"), ("Joggen Serie", "03-09 07:00")])
        self.assertEqual(kalserie.change_future(series(), "serie-rr", epoch(2026, 3, 2), None, ZONE, "x"), (None, None))

    def test_all_future_from_a_later_one(self):
        rest, new = kalserie.change_future(series(), "serie-rr", epoch(2026, 3, 16),
                                           item(title="Laufen Serie", start="2026-03-16T19:00", end="2026-03-16T19:45", rule="weekly", zone=TZ),
                                           ZONE, "neu@speech-spark")
        self.assertEqual(starts(rest), [("Joggen Serie", "03-02 08:00"), ("Joggen Serie", "03-09 08:00")])
        self.assertEqual(starts(new)[:2], [("Laufen Serie", "03-16 19:00"), ("Laufen Serie", "03-23 19:00")])
        self.assertIn("UID:neu@speech-spark", new)
        rest, new = kalserie.change_future(series(), "serie-rr", epoch(2026, 3, 16), None, ZONE, "x")
        self.assertEqual((len(starts(rest)), new), (2, None))
        # COUNT: the new series has only the occurrences the old one still had
        rest, new = kalserie.change_future(series("FREQ=WEEKLY;COUNT=4"), "serie-rr", epoch(2026, 3, 16),
                                           item(start="2026-03-16T09:00", end="2026-03-16T09:30", zone=TZ), ZONE, "n")
        self.assertEqual((len(starts(rest)), len(starts(new))), (2, 2))


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def clean():
    helpers.cal_changed_behind()
    for k in [k for k, v in helpers.CAL_EVENTS.items() if "Serie" in v]:
        helpers.CAL_EVENTS.pop(k, None)
    helpers.cal_changed_behind()


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True)
        cls.c, cls.uid = profile("Serie Sven")
        calendars.add(cls.uid, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                                "user": "k", "password": "pw"}))

    @classmethod
    def tearDownClass(cls):
        clean()

    def setUp(self):
        clean()
        guard.reset()
        helpers.CAL_EVENTS[HREF] = series()
        helpers.cal_changed_behind()

    def view(self, c=None, start="2026-03-09", days=14):
        calendars._cache.clear()
        return [x for x in (c or self.c).get("/api/profile/calendar/view", params={"start": start, "days": days, "tz": TZ}).json()["events"]
                if "Serie" in x["title"]]

    def at(self, evs, day):
        return [x for x in evs if datetime.datetime.fromtimestamp(x["start"], ZONE).strftime("%m-%d") == day]

    def put(self, x, scope, new=None, c=None):
        body = {"change": "edit" if new else "delete", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ,
                "uid": x["uid"], "rid": x["rid"], "scope": scope}
        if new:
            body["new"] = new
        r = (c or self.c).put("/api/profile/calendar/event", json=body)
        helpers.cal_changed_behind()
        return r

    def test_only_this_one_and_undo(self):
        x = self.at(self.view(), "03-09")[0]
        self.assertEqual((x["rule"], x["uid"], x["rid"], x["edit"]), ("weekly", "serie-rr", epoch(2026, 3, 9), True))
        r = self.put(x, "one", {"title": "Joggen Serie Park", "start": "2026-03-09T18:00", "end": "2026-03-09T18:45"})
        self.assertEqual(r.status_code, 200, r.text)
        evs = self.view()
        self.assertEqual([y["title"] for y in self.at(evs, "03-09")], ["Joggen Serie Park"])
        self.assertEqual([y["title"] for y in self.at(evs, "03-16")], ["Joggen Serie"])
        self.assertEqual(len(helpers.CAL_EVENTS[HREF].split("BEGIN:VEVENT")), 3)   # the series and its changed one
        u = self.c.post("/api/profile/calendar/undo", json={"undo": r.json()["undo"]})
        self.assertEqual(u.status_code, 200, u.text)
        helpers.cal_changed_behind()
        self.assertEqual([y["title"] for y in self.at(self.view(), "03-09")], ["Joggen Serie"])
        # once only, and only the profile's own token
        self.assertEqual(self.c.post("/api/profile/calendar/undo", json={"undo": r.json()["undo"]}).status_code, 410)
        self.assertEqual(self.c.post("/api/profile/calendar/undo", json={"undo": "0" * 24}).status_code, 410)
        self.assertGreaterEqual(calendars.page_today("serie"), 1)   # Live: a number, never which
        self.assertGreaterEqual(calendars.page_today("undo"), 1)

    def test_all_future_delete_and_new_series(self):
        x = self.at(self.view(), "03-16")[0]
        r = self.put(x, "future", {"title": "Laufen Serie", "start": "2026-03-16T19:00", "end": "2026-03-16T19:45", "rule": "weekly", "until": ""})
        self.assertEqual(r.status_code, 200, r.text)
        evs = self.view(days=21)
        self.assertEqual([y["title"] for y in self.at(evs, "03-09")], ["Joggen Serie"])
        self.assertEqual([y["title"] for y in self.at(evs, "03-23")], ["Laufen Serie"])
        self.assertEqual(sum(1 for v in helpers.CAL_EVENTS.values() if "Serie" in v), 2)   # the old series ends, a new one
        # „Rückgängig“ removes the new one and puts the old back
        self.assertEqual(self.c.post("/api/profile/calendar/undo", json={"undo": r.json()["undo"]}).status_code, 200)
        helpers.cal_changed_behind()
        self.assertEqual([y["title"] for y in self.at(self.view(days=21), "03-23")], ["Joggen Serie"])
        self.assertEqual(sum(1 for v in helpers.CAL_EVENTS.values() if "Serie" in v), 1)
        x = self.at(self.view(), "03-16")[0]
        self.assertEqual(self.put(x, "future").status_code, 200)
        evs = self.view(days=21)
        self.assertEqual((len(self.at(evs, "03-09")), len(self.at(evs, "03-16")), len(self.at(evs, "03-23"))), (1, 0, 0))

    def test_fields_round_trip_and_a_move_keeps_them(self):
        helpers.CAL_EVENTS.pop(HREF)
        helpers.cal_changed_behind()
        r = self.c.post("/api/profile/calendar/event", json={
            "title": "Arzt Serie", "start": "2026-03-11T10:00", "end": "2026-03-11T10:30", "tz": TZ, "alarm": 30,
            "note": "Karte mitnehmen", "link": "https://example.org/praxis", "people": ["Anna <anna@example.org>"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["undo"])
        x = self.at(self.view(), "03-11")[0]
        self.assertEqual((x["alarm"], x["note"], x["link"], x["people"], x["rule"] if "rule" in x else ""),
                         (30, "Karte mitnehmen", "https://example.org/praxis", [{"name": "Anna", "mail": "anna@example.org"}], ""))
        # a move from an older app: only title and times; the rest stays
        r = self.c.put("/api/profile/calendar/event", json={"change": "edit", "cal": x["cal"], "title": x["title"], "start": x["start"], "tz": TZ,
                                                              "new": {"title": "Arzt Serie", "start": "2026-03-12T10:00", "end": "2026-03-12T10:30"}})
        self.assertEqual(r.status_code, 200, r.text)
        helpers.cal_changed_behind()
        y = self.at(self.view(), "03-12")[0]
        self.assertEqual((y["alarm"], y["note"], len(y["people"])), (30, "Karte mitnehmen", 1))

    def test_refused(self):
        x = self.at(self.view(), "03-09")[0]
        bad = dict(x, rid=x["rid"] + 3600)
        self.assertEqual(self.put(bad, "one").status_code, 409)
        self.assertEqual(self.put(x, "alle").status_code, 400)
        self.assertEqual(self.put(x, "one", {"title": "x Serie", "start": "2026-03-09T08:00", "end": "2026-03-09T09:00",
                                             "people": ["niemand"]}).status_code, 400)
        self.assertEqual(self.put(dict(x, uid="fremd"), "one").status_code, 409)
        other, _ = profile("Serie Olga")
        self.assertEqual(self.put(x, "one", c=other).status_code, 409)
        self.assertEqual(other.post("/api/profile/calendar/undo", json={"undo": "a" * 24}).status_code, 410)
        self.assertEqual(helpers.CAL_EVENTS[HREF], series())
        self.assertIn(TestClient(panel.app).post("/api/profile/calendar/undo", json={"undo": "a"}).status_code, (401, 403))


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

    def setUp(self):
        clean()
        guard.reset()
        helpers.CAL_EVENTS[HREF] = series()
        helpers.cal_changed_behind()

    def go(self, width, steps):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def run():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, width, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    if not calendars.get(uid)["calendars"]:
                        calendars.add(uid, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                                            "user": "k", "password": "pw"}))
                    await pg.evaluate("CAL_ON=true;icTabSet('cal','show');KAL.day=new Date(2026,2,9);"
                                      "KAL.view=NARROW()?'day':'week';goSec('cal')")
                    await b.until(pg, "!KAL.busy&&!!KAL.data&&KAL.data.events.some(x=>x.title==='Joggen Serie')")
                    await steps(b, pg)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(run())

    def test_drag_creates_and_a_series_asks(self):
        async def steps(b, pg):
            # a drag in free time: the inspector with the times, the title typed, closed = saved
            r = await pg.evaluate("(()=>{const c=document.querySelectorAll('#kalview .kcol')[2].getBoundingClientRect();"
                                  "return [c.left+c.width/2,c.top+(10-KAL.h0)*KAL_H+5]})()")
            await pg.mouse.move(r[0], r[1])
            await pg.mouse.down()
            for i in range(1, 10):
                await pg.mouse.move(r[0], r[1] + i * 9)
            await pg.mouse.up()
            await b.until(pg, "!!document.querySelector('#kalview .kaldet [data-f=title]')")
            self.assertEqual(await pg.evaluate("document.querySelector('#kalview [data-f=st]').value"), "10:00")
            await pg.keyboard.type("Planung Serie")
            await pg.keyboard.press("Escape")
            await b.until(pg, "!KAL.busy&&KAL.data.events.some(x=>x.title==='Planung Serie')")
            # the series: a change asks; „Abbrechen“ changes nothing, „Nur dieser Termin“ only the one
            await pg.evaluate("[...document.querySelectorAll('#kalview [data-i]')].find(e=>e.textContent.includes('Joggen')).click()")
            await b.until(pg, "document.querySelector('#kalview .kaldet [data-f=title]')?.value==='Joggen Serie'")
            await pg.fill("#kalview [data-f=title]", "Joggen Serie Park")
            await pg.click("#kalview [data-act=save]")
            await b.until(pg, "!document.querySelector('#kalview .kalask').hidden")
            self.assertEqual(await pg.evaluate("document.querySelectorAll('#kalview .kalask [data-s]').length"), 3)
            await pg.click("#kalview .kalask [data-s=one]")
            await b.until(pg, "!KAL.busy&&KAL.data.events.some(x=>x.title==='Joggen Serie Park')")
            helpers.cal_changed_behind()
            self.assertEqual(len(helpers.CAL_EVENTS[HREF].split("BEGIN:VEVENT")), 3)
            # the year view: twelve months
            await pg.evaluate("KAL.view='year';kalLoad()")
            await b.until(pg, "document.querySelectorAll('#kalview .kalyear .kmini').length===12")
        self.go(1280, steps)

    def test_phone_week_strip(self):
        async def steps(b, pg):
            await b.until(pg, "document.querySelectorAll('#kalview .kweek [data-wd]').length===7")
            await pg.click("#kalview .kweek [data-wd='2026-03-11']")
            await b.until(pg, "kalIso(KAL.day)==='2026-03-11'&&document.querySelector('#kalview .kweek [data-wd=\"2026-03-11\"]').classList.contains('on')")
            over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
            self.assertLessEqual(over, 1, "the day scrolls sideways")
        self.go(390, steps)


if __name__ == "__main__":
    unittest.main()
