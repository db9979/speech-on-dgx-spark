"""Listen in Erinnerungen (listendav.py, Listen Stufe 3): the Spark lists as task lists (VTODO) of the calendar
server, both ways.

- Off by default: without the admin switch (chat.tasks_dav) the calendar home shows no list and a list path is 404.
- On: the home shows Einkauf, Aufgaben and own lists as VTODO collections; a list kept in a calendar account and
  another profile's list (also a shared one) never.
- A calendar app reads (PROPFIND, REPORT query and multiget, GET with etag) and writes: a new VTODO puts the entry
  on with the source „iPhone Erinnerungen“ and keeps the app's name and UID; COMPLETED ticks it off, back takes it
  back, DELETE deletes it, a wrong If-Match is 412, anything but one VTODO with a summary is 415.
- The door is the calendar server's: wrong password 401, another profile's path 404, Mein Notaus 503.
- Journal lines with fixed words and numbers only (never the entry), Live counts the changes.

No wall clock in the checks.
"""
import base64
import contextlib
import io
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import listendav  # noqa: E402
import notaus  # noqa: E402
import tasks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
TODO = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iOS 26//EN\r\nBEGIN:VTODO\r\nUID:{uid}\r\n"
        "DTSTAMP:20260311T090000Z\r\nSUMMARY:{text}\r\n{extra}END:VTODO\r\nEND:VCALENDAR\r\n")
QUERY = (b'<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
         b'<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
         b'<c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>')


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


class Erinnerungen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, calendar_server=True, tasks=True, tasks_dav=True, tasks_share=True)
        cls.c, cls.uid = profile("Erinn Ada")
        cls.o, cls.oid = profile("Erinn Otto")
        r = cls.c.post("/api/profile/calserver")
        assert r.status_code == 200, r.text
        cls.pw = r.json()["password"]
        cls.dav = TestClient(panel.app)
        cls.dav.headers.update(basic(cls.uid, cls.pw))
        cls.base = f"/caldav/{cls.uid}/"

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(calendar_server=False, tasks_dav=False, tasks_share=False)
        guard.reset()

    def setUp(self):
        guard.reset()
        helpers.set_config(tasks_dav=True)
        for u in (self.uid, self.oid):
            d = tasks._load(u)
            d["items"], d["shares"] = [], {}
            tasks._save(u, d)

    def find(self, path, depth="1"):
        r = self.dav.request("PROPFIND", path, headers={"Depth": depth})
        self.assertEqual(r.status_code, 207, r.text)
        return r.text

    def test_off_by_default_and_on_with_the_switch(self):
        self.assertNotIn("listdav", tasks.features.DEFAULT_ON)
        helpers.set_config(tasks_dav=False)
        self.assertNotIn("liste-einkauf", self.find(self.base))
        self.assertEqual(self.dav.request("PROPFIND", self.base + "liste-einkauf/", headers={"Depth": "0"}).status_code, 404)
        helpers.set_config(tasks_dav=True)
        home = self.find(self.base)
        self.assertIn(self.base + "liste-einkauf/", home)
        self.assertIn(self.base + "liste-aufgaben/", home)
        self.assertIn('<c:comp name="VTODO"/>', home)

    def test_both_ways(self):
        a = self.c
        a.post("/api/profile/tasks/einkauf", json={"text": "2 Milch"})
        path = self.base + "liste-einkauf/"
        r = self.dav.request("REPORT", path, content=QUERY, headers={"Depth": "1"})
        self.assertEqual(r.status_code, 207, r.text)
        self.assertIn("SUMMARY:Milch 2×", r.text)
        self.assertIn("STATUS:NEEDS-ACTION", r.text)
        ctag = self.find(path, "0")
        # from Reminders: a new entry keeps the app's name and UID
        body = TODO.format(uid="ABC-1", text="Butter", extra="")
        r = self.dav.put(path + "ABC-1.ics", content=body, headers={"If-None-Match": "*"})
        self.assertEqual(r.status_code, 201, r.text)
        etag = r.headers["ETag"]
        rows = a.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"]
        self.assertEqual(sorted((x["text"], x["src"]) for x in rows), [("Butter", "erinnerungen"), ("Milch", "panel")])
        self.assertNotEqual(self.find(path, "0"), ctag)                     # the app sees something changed
        got = self.dav.get(path + "ABC-1.ics")
        self.assertEqual((got.status_code, got.headers["ETag"]), (200, etag))
        self.assertIn("UID:ABC-1", got.text)
        # the same name again with If-None-Match: refused
        self.assertEqual(self.dav.put(path + "ABC-1.ics", content=body, headers={"If-None-Match": "*"}).status_code, 412)
        # ticked off there: done on the Spark, under „Zuletzt erledigt“
        done = TODO.format(uid="ABC-1", text="Butter", extra="STATUS:COMPLETED\r\nCOMPLETED:20260311T100000Z\r\n")
        self.assertEqual(self.dav.put(path + "ABC-1.ics", content=done, headers={"If-Match": "\"wrong\""}).status_code, 412)
        self.assertEqual(self.dav.put(path + "ABC-1.ics", content=done, headers={"If-Match": etag}).status_code, 204)
        lst = a.get("/api/profile/tasks").json()["lists"]["einkauf"]
        self.assertEqual([x["text"] for x in lst["items"]], ["Milch"])
        self.assertEqual([x["text"] for x in lst["done"]], ["Butter"])
        # back again, then ticked off on the page: the app reads COMPLETED
        self.assertEqual(self.dav.put(path + "ABC-1.ics", content=body).status_code, 204)
        milk = next(x["id"] for x in a.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"] if x["text"] == "Milch")
        a.post("/api/profile/tasks/einkauf/done", json={"ids": [milk]})
        r = self.dav.get(path + f"{milk}.ics")
        self.assertIn("STATUS:COMPLETED", r.text)
        # multiget, then delete
        mg = (f'<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:href>{path}ABC-1.ics'
              f'</d:href><d:href>{path}nope.ics</d:href></c:calendar-multiget>').encode()
        r = self.dav.request("REPORT", path, content=mg)
        self.assertIn("SUMMARY:Butter", r.text)
        self.assertIn("404 Not Found", r.text)
        self.assertEqual(self.dav.delete(path + "ABC-1.ics").status_code, 204)
        self.assertEqual(self.dav.delete(path + "ABC-1.ics").status_code, 404)
        self.assertNotIn("Butter", str(a.get("/api/profile/tasks").json()["lists"]["einkauf"]))

    def test_due_goes_both_ways(self):
        """„bis“ of an entry (a meeting's task, Dominik 2026-10-20) reaches Reminders as DUE (a date) and comes back:
        set, moved or taken away there, the Spark follows; ticking it off there keeps it."""
        import asyncio
        path = self.base + "liste-aufgaben/"
        asyncio.run(tasks.add(self.uid, "aufgaben", ["Angebot schicken"], src="besprechung", due="2026-10-24", qty=False))
        eid = tasks._load(self.uid)["items"][0]["id"]
        ctag = self.find(path, "0")
        r = self.dav.get(path + f"{eid}.ics")
        self.assertIn("DUE;VALUE=DATE:20261024", r.text)
        moved = TODO.format(uid=f"{eid}@speech-spark", text="Angebot schicken", extra="DUE;VALUE=DATE:20261027\r\n")
        self.assertEqual(self.dav.put(path + f"{eid}.ics", content=moved).status_code, 204)
        self.assertEqual(tasks._load(self.uid)["items"][0]["due"], "2026-10-27")
        self.assertNotEqual(self.find(path, "0"), ctag)
        timed = TODO.format(uid=f"{eid}@speech-spark", text="Angebot schicken",
                            extra="DUE:20261028T090000Z\r\nSTATUS:COMPLETED\r\n")
        self.assertEqual(self.dav.put(path + f"{eid}.ics", content=timed).status_code, 204)
        x = tasks._load(self.uid)["items"][0]
        self.assertEqual((x["due"], bool(x.get("done"))), ("2026-10-28", True))       # only the date
        gone = TODO.format(uid=f"{eid}@speech-spark", text="Angebot schicken", extra="")
        self.assertEqual(self.dav.put(path + f"{eid}.ics", content=gone).status_code, 204)
        self.assertNotIn("due", tasks._load(self.uid)["items"][0])
        new = TODO.format(uid="D-1", text="Raum buchen", extra="DUE;VALUE=DATE:20261030\r\n")
        self.assertEqual(self.dav.put(path + "D-1.ics", content=new, headers={"If-None-Match": "*"}).status_code, 201)
        self.assertEqual(next(y for y in tasks._load(self.uid)["items"] if y["text"] == "Raum buchen")["due"], "2026-10-30")

    def test_only_one_task_with_a_summary(self):
        path = self.base + "liste-aufgaben/"
        event = TODO.replace("VTODO", "VEVENT").format(uid="E1", text="Termin", extra="")
        for bad in (event, TODO.format(uid="E2", text="", extra=""), "kein Kalender", TODO.format(uid="E3", text="x" * 10, extra="") * 2):
            self.assertEqual(self.dav.put(path + "E.ics", content=bad).status_code, 415, bad[:40])
        self.assertEqual(self.dav.put(path + "x y.ics", content=TODO.format(uid="E4", text="a", extra="")).status_code, 404)
        self.assertEqual(self.c.get("/api/profile/tasks").json()["lists"]["aufgaben"]["items"], [])

    def test_own_lists_only_and_the_door(self):
        lid = self.c.post("/api/profile/listen", json={"name": "Baumarkt"}).json()["made"]
        self.assertIn(self.base + f"liste-{lid}/", self.find(self.base))
        # another profile's list, also shared with this one, never; its path neither
        olid = self.o.post("/api/profile/listen", json={"name": "Garten"}).json()["made"]
        self.o.put(f"/api/profile/listen/{olid}/share", json={"to": self.uid, "level": "add"})
        self.assertNotIn(olid, self.find(self.base))
        self.assertEqual(self.dav.request("PROPFIND", f"/caldav/{self.oid}/liste-{olid}/").status_code, 404)
        self.assertEqual(self.dav.request("PROPFIND", self.base + f"liste-{olid}/").status_code, 404)
        # a list kept in a calendar account stays out
        d = tasks._load(self.uid)
        d["targets"]["aufgaben"] = {"acc": "x", "url": "https://dav.example/tasks/", "name": "Nextcloud"}
        tasks._save(self.uid, d)
        try:
            self.assertNotIn("liste-aufgaben", self.find(self.base))
        finally:
            d = tasks._load(self.uid)
            d["targets"] = {}
            tasks._save(self.uid, d)
        # wrong password, Mein Notaus
        wrong = TestClient(panel.app)
        self.assertEqual(wrong.request("PROPFIND", self.base + "liste-einkauf/", headers=basic(self.uid, "falsch")).status_code, 401)
        real = notaus.own
        notaus.own = lambda uid: uid == self.uid
        try:
            r = self.dav.put(self.base + "liste-einkauf/N.ics", content=TODO.format(uid="N", text="Brot", extra=""))
            self.assertEqual(r.status_code, 503)   # Mein Notaus closes the door (kalenderserver.login)
        finally:
            notaus.own = real
        self.assertEqual(self.c.get("/api/profile/tasks").json()["lists"]["einkauf"]["items"], [])

    def test_journal_and_live_say_numbers_only(self):
        before = listendav.for_live()["saved"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.dav.put(self.base + "liste-einkauf/J.ics", content=TODO.format(uid="J", text="Geheimkäse", extra=""))
            self.dav.delete(self.base + "liste-einkauf/J.ics")
            self.dav.put(self.base + "liste-einkauf/K.ics", content="kaputt")
        log = out.getvalue()
        self.assertNotIn("Geheimkäse", log)
        self.assertIn("tasks: add einkauf | 1 entries from calendar app |", log)
        self.assertIn("tasks: delete einkauf | 1 entries from calendar app |", log)
        self.assertIn("tasks: add einkauf | failed (not a task) |", log)
        self.assertEqual(listendav.for_live()["saved"], before + 2)


if __name__ == "__main__":
    unittest.main()
