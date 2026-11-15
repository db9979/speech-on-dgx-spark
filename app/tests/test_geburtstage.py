"""Geburtstage im Kalender (Nextcloud-Ideen K3, Dominik 2026-11-15): the contacts' birthdays as a read-only calendar
of its own on the page Kalender (calendars.EXTRA, contacts.bday_calendar).

- Off (admin switch chat.calendar_bdays, default off): no calendar „Geburtstage“, even with contacts.
- On: all day on the right date, with the age when the year is known, never changeable ("edit" false, why
  "geburtstag"), named through "made" so the page and the apps say it in their language; also without any calendar
  connected.
- Nothing is stored: the profile folder holds no new file.

Fixed dates; no wall clock.
"""
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import contacts  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
WEEK = {"start": "2026-03-09", "days": 7, "tz": "Europe/Berlin"}


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Geburtstage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, contacts=True, contacts_edit=True, calendar_bdays=False)
        cls.c, cls.uid = profile("Geburtstag Gerda")
        for card in ({"given": "Anna", "family": "Apfel", "bday": "1985-03-11", "book": "spark"},
                     {"given": "Bert", "family": "Birne", "bday": "--03-13", "book": "spark"},
                     {"given": "Cleo", "family": "Kirsch", "bday": "1990-07-01", "book": "spark"}):
            r = cls.c.post("/api/profile/contacts/card", json=card)
            assert r.status_code == 200, r.text

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(contacts=False, contacts_edit=False, calendar_bdays=False)

    def tearDown(self):
        helpers.set_config(calendar_bdays=False)

    def view(self):
        r = self.c.get("/api/profile/calendar/view", params=WEEK)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_off_no_calendar(self):
        d = self.view()
        self.assertNotIn(contacts.BDAY_CAL, d.get("calendars", []))
        self.assertFalse(d["connected"])                 # no calendar of its own either

    def test_on_birthdays_all_day_read_only(self):
        helpers.set_config(calendar_bdays=True)
        d = self.view()
        self.assertTrue(d["connected"])
        i = d["calendars"].index(contacts.BDAY_CAL)
        self.assertEqual(d["made"], {str(i): "geburtstag"})
        evs = sorted((x for x in d["events"] if x["cal"] == i), key=lambda x: x["start"])
        self.assertEqual([x["title"] for x in evs], ["Anna Apfel (41)", "Bert Birne"])   # Cleo is in July
        for x in evs:
            self.assertTrue(x["allday"])
            self.assertFalse(x["edit"])
            self.assertEqual(x["why"], "geburtstag")
            self.assertEqual(x["end"] - x["start"], 86400)
        self.assertEqual(evs[0]["start"], 1773183600)    # 2026-03-11 00:00 Europe/Berlin
        self.assertNotIn(i, d["edit"] + d["add"])        # never a target for a new appointment

    def test_not_for_another_profile_or_blocked(self):
        helpers.set_config(calendar_bdays=True)
        self.assertIsNone(contacts.bday_calendar("kein-profil", None, 7, None))
        other, _ = profile("Geburtstag Gustav")
        r = other.get("/api/profile/calendar/view", params=WEEK)
        self.assertNotIn(contacts.BDAY_CAL, r.json().get("calendars", []))

    def test_nothing_stored(self):
        helpers.set_config(calendar_bdays=True)
        before = set(os.listdir(profiles._path(self.uid, "")))
        self.view()
        self.assertEqual(set(os.listdir(profiles._path(self.uid, ""))), before)

    def test_hook_registered_once(self):
        self.assertEqual(calendars.EXTRA.count(contacts.bday_calendar), 1)


if __name__ == "__main__":
    unittest.main()
