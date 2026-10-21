"""Einladungen aus Mails (Dominik 2026-10-21 „ja alles umsetzen 1-6“, Punkt 3): an invitation (.ics) in a mail into a
calendar with one tap, the answer to the organiser like Apple Mail.

- Off by default: without the admin switch the endpoints are 403 and mail.show never says "invite".
- show: what, when, where, who invites, how many people, the calendars to choose; "reply" only with „Mails senden“,
  an own ATTENDEE line and METHOD:REQUEST.
- Zusagen puts a calendar of the Spark's own making into the calendar: only the kept fields (no VALARM, no ATTACH,
  no URL), the description cut, the own PARTSTAT set; the same invitation again replaces it (one place per UID);
  Absagen takes it out; a cancellation only with „Aus dem Kalender entfernen“.
- The answer mail: METHOD:REPLY with the own PARTSTAT, to the organiser, from the mailbox it came to, counted.
- Refused: two appointments, too big, an unsupported METHOD, an answer that does not fit; Notaus 423.
- The bar on the page (390 px): what and when, „Zusagen“ puts it into the calendar and says so, no page error.

Fake mailbox and SMTP, a Spark calendar; fixed dates (2026-03), no wall clock.
"""
import asyncio
import email.message
import email.policy
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import einladung  # noqa: E402
import guard  # noqa: E402
import mail  # noqa: E402
import notaus  # noqa: E402
import senden  # noqa: E402
import sparkkalender  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_ui_browser import browser_ok  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ME = "ida@example.org"


def ics(method="REQUEST", uid="inv-1@example.com", seq=0, extra="", second=""):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Fremd//EN\r\nMETHOD:" + method + "\r\n"
            "BEGIN:VTIMEZONE\r\nTZID:Europe/Berlin\r\nBEGIN:STANDARD\r\nDTSTART:19701025T030000\r\nTZOFFSETFROM:+0200\r\n"
            "TZOFFSETTO:+0100\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n"
            f"BEGIN:VEVENT\r\nUID:{uid}\r\nSEQUENCE:{seq}\r\nDTSTAMP:20260301T080000Z\r\n"
            "DTSTART;TZID=Europe/Berlin:20260312T100000\r\nDTEND;TZID=Europe/Berlin:20260312T113000\r\n"
            "SUMMARY:Planung Einladung\r\nLOCATION:Raum 4\r\nDESCRIPTION:" + "x" * 5000 + "\r\n"
            "ORGANIZER;CN=Olga Organ:mailto:olga@example.com\r\n"
            f"ATTENDEE;CN=Ida;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{ME}\r\n"
            "ATTENDEE;CN=Bert;PARTSTAT=ACCEPTED:mailto:bert@example.com\r\n"
            "URL:https://evil.example/track\r\nATTACH:https://evil.example/file\r\n" + extra +
            "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT\r\n" + second +
            "END:VCALENDAR\r\n")


def letter(cal):
    m = email.message.EmailMessage(policy=email.policy.default)
    m["From"] = "Olga Organ <olga@example.com>"
    m["To"] = ME
    m["Subject"] = "Einladung: Planung"
    m.set_content("Bitte kommen.")
    m.add_alternative(cal, subtype="calendar", params={"method": "REQUEST"})
    return m


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Invite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(calendar=True, mail=True, mail_invites=True, mail_send=True)
        cls.c, cls.uid = profile("Ida Invite")
        for x in calendars.get(cls.uid)["calendars"]:
            calendars.remove(cls.uid, x["id"])
        r = cls.c.post("/api/profile/calendar", json={"spark": True, "name": "Zuhause"})
        assert r.status_code == 200, r.text
        cls.cal = next(x for x in r.json()["calendars"] if x["spark"])
        cls.real = (mail.get, mail.message, mail.whole, senden._smtp)
        cls.box = {"accounts": [{"id": "m0000abcd", "name": "Ida", "host": "imap.example.org", "port": 993,
                                 "user": ME, "password": "pw"}]}
        mail.get = lambda uid: cls.box if uid == cls.uid else cls.real[0](uid)
        cls.sent = []
        senden._smtp = lambda acct, msg: cls.sent.append((acct["user"], msg)) or 0

    @classmethod
    def tearDownClass(cls):
        mail.get, mail.message, mail.whole, senden._smtp = cls.real
        helpers.set_config(mail_invites=False, mail_send=False, mail=False)

    def setUp(self):
        guard.reset()
        self.sent.clear()
        sparkkalender.calendar(self.uid, self.cal["id"])["items"].clear()
        self.use(ics())

    def use(self, cal):
        msg = letter(cal)
        mail.message = lambda uid, ref, folder="INBOX": msg
        mail.whole = lambda uid, ref, folder="INBOX": msg

    def items(self):
        return sparkkalender.calendar(self.uid, self.cal["id"])["items"]

    def take(self, answer, **more):
        return self.c.post("/api/profile/mail/invite", json=dict({"id": "m0000abcd:7", "answer": answer}, **more))

    def test_show(self):
        r = self.c.get("/api/profile/mail/invite", params={"id": "m0000abcd:7"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["method"], d["title"], d["place"], d["people"], d["mine"], d["in"], d["reply"]),
                         ("request", "Planung Einladung", "Raum 4", 2, "needs-action", "", True))
        self.assertEqual(d["organizer"], {"name": "Olga Organ", "addr": "olga@example.com"})
        self.assertEqual(d["end"] - d["start"], 90 * 60)
        self.assertEqual([x["name"] for x in d["calendars"]], ["Zuhause"])
        self.assertTrue(einladung.has(self.uid, letter(ics())))
        helpers.set_config(mail_send=False)
        try:
            self.assertFalse(self.c.get("/api/profile/mail/invite", params={"id": "m0000abcd:7"}).json()["reply"])
        finally:
            helpers.set_config(mail_send=True)

    def test_accept_cleans_replies_and_replaces(self):
        r = self.take("accept")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"in": "Zuhause", "replied": True})
        self.assertEqual(len(self.items()), 1)
        text = next(iter(self.items().values()))[1].replace("\r\n ", "")   # unfolded
        for gone in ("VALARM", "ATTACH", "evil.example", "x" * 4001):
            self.assertNotIn(gone, text)
        self.assertIn("x" * 4000, text)
        self.assertIn("PARTSTAT=ACCEPTED", text)
        self.assertIn("UID:inv-1@example.com", text)
        self.assertIn("BEGIN:VTIMEZONE", text)
        # the answer to the organiser
        (frm, msg), = self.sent
        self.assertEqual((frm, msg["To"], msg["Subject"]), (ME, "olga@example.com", "Zugesagt: Planung Einladung"))
        part = next(p for p in msg.walk() if p.get_content_type() == "text/calendar")
        self.assertEqual(part.get_param("method"), "REPLY")
        reply = part.get_content()
        self.assertIn("METHOD:REPLY", reply)
        self.assertIn("PARTSTAT=ACCEPTED", reply)
        self.assertIn(f"mailto:{ME}", reply)
        self.assertNotIn("bert@example.com", reply)
        # the update of the same invitation replaces it, nothing twice
        self.use(ics(seq=1).replace("Planung Einladung", "Planung neu"))
        self.assertEqual(self.take("tentative", reply=False).json(), {"in": "Zuhause", "replied": False})
        self.assertEqual(len(self.items()), 1)
        self.assertIn("Planung neu", next(iter(self.items().values()))[1])
        self.assertEqual(len(self.sent), 1)
        # Absagen takes it out
        self.assertEqual(self.take("decline").json(), {"in": "", "replied": True})
        self.assertEqual(len(self.items()), 0)

    def test_cancel_only_with_remove(self):
        self.take("accept", reply=False)
        self.use(ics("CANCEL"))
        d = self.c.get("/api/profile/mail/invite", params={"id": "m0000abcd:7"}).json()
        self.assertEqual((d["method"], d["in"], d["reply"]), ("cancel", "Zuhause", False))
        self.assertEqual(self.take("accept").status_code, 400)
        self.assertEqual(len(self.items()), 1)
        self.assertEqual(self.take("remove").json(), {"in": "", "replied": False})
        self.assertEqual(len(self.items()), 0)
        self.use(ics())
        self.assertEqual(self.take("remove").status_code, 400)

    def test_refused(self):
        for bad in (ics(second="BEGIN:VEVENT\r\nUID:other\r\nDTSTART:20260313T100000Z\r\nEND:VEVENT\r\n"),
                    ics("COUNTER"), ics(extra="COMMENT:" + "y" * 300000 + "\r\n")):
            self.use(bad)
            self.assertIn(self.c.get("/api/profile/mail/invite", params={"id": "m0000abcd:7"}).status_code, (400, 404))
            self.assertIn(self.take("accept").status_code, (400, 404))
        self.assertEqual(len(self.items()), 0)
        self.use(ics())
        self.assertEqual(self.take("maybe").status_code, 400)
        self.assertEqual(self.c.get("/api/profile/mail/invite", params={"id": "m9999abcd:7"}).status_code, 400)
        self.assertEqual(self.sent, [])

    def test_notaus_and_switch(self):
        real = notaus.stop

        def stop(what, uid):
            raise notaus.NotausAktiv()
        notaus.stop = stop
        try:
            self.assertEqual(self.take("accept").status_code, 423)
        finally:
            notaus.stop = real
        self.assertEqual(len(self.items()), 0)
        helpers.set_config(mail_invites=False)
        try:
            self.assertEqual(self.c.get("/api/profile/mail/invite", params={"id": "m0000abcd:7"}).status_code, 403)
            self.assertEqual(self.take("accept").status_code, 403)
            self.assertFalse(einladung.has(self.uid, letter(ics())))
        finally:
            helpers.set_config(mail_invites=True)
        self.assertEqual(self.sent, [])

    def test_live_numbers_only(self):
        self.c.get("/api/profile/mail/invite", params={"id": "m0000abcd:7"})
        d = einladung.for_live()
        self.assertEqual(set(d), {"on", "shown", "saved", "answered"})
        self.assertGreaterEqual(d["shown"], 1)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)
        helpers.set_config(calendar=True, mail=True, mail_invites=True, mail_send=False)
        import profiles
        cls.uid = next(u for u in profiles.user_ids() if (profiles.by_id(u) or {}).get("name") == "Uitest")
        if not any(x.get("spark") for x in calendars.get(cls.uid)["calendars"]):
            calendars.add_spark(cls.uid, "Zuhause")
        cls.cid = next(x["id"] for x in calendars.get(cls.uid)["calendars"] if x.get("spark"))
        cls.real = (mail.get, mail.message, mail.whole)
        box = {"accounts": [{"id": "m0000abcd", "name": "Ui", "host": "imap.example.org", "port": 993, "user": ME,
                             "password": "pw"}]}
        msg = letter(ics(uid="page-1@example.com"))
        mail.get = lambda uid: box if uid == cls.uid else cls.real[0](uid)
        mail.message = mail.whole = lambda uid, ref, folder="INBOX": msg

    @classmethod
    def tearDownClass(cls):
        mail.get, mail.message, mail.whole = cls.real
        helpers.set_config(mail_invites=False, mail=False)

    def test_bar_accept(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    await pg.evaluate("const h=document.createElement('h3');h.id='einh';document.body.prepend(h);"
                                      "einShow(h,'m0000abcd:7','INBOX')")
                    await b.until(pg, "!!document.querySelector('.einbar button[data-ein=accept]')")
                    text = await pg.text_content(".einbar")
                    self.assertIn("Planung Einladung", text)
                    self.assertIn("Olga Organ", text)
                    self.assertIsNone(await pg.query_selector(".einbar input[data-ein=reply]"))   # no „Mails senden“
                    await pg.click(".einbar button[data-ein=accept]")
                    await b.until(pg, "document.querySelector('.einbar').textContent.includes('Im Kalender „Zuhause“.')")
                    self.assertEqual(len(sparkkalender.calendar(self.uid, self.cid)["items"]), 1)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
