"""Zurückstellen (spaeter.py, pl_mail-Ideen 2, Dominik 2026-11-13 „1-7“):

- Off until the admin switches chat.mail_later on; it needs „Mails ordnen“; a blocked profile gets 403.
- Fixed times in the profile's zone (heute Abend 18, morgen 8, Wochenende Sa 9, nächste Woche Mo 8) or one's own from
  five minutes to a year ahead; anything else is refused.
- The mail goes from the inbox into „<KI folder>/Später“ of its own mailbox; the list stays sealed in the profile.
- At its time (due, every minute) it comes back into the inbox, unread; also when the switch is off by then. A mail
  moved away by hand is dropped from the list; „Jetzt zurückholen“ brings one at once.
- Logs: fixed words and numbers only, never a subject or an address.

The fake mailbox (helpers.FakeMailbox); fixed times, no wall clock in the assertions.
"""
import contextlib
import datetime
import email.utils
import io
import time
import unittest
from zoneinfo import ZoneInfo

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import mail  # noqa: E402
import spaeter  # noqa: E402
import tidy  # noqa: E402
from tests.test_mailclient_c import profile  # noqa: E402

FMB = helpers.FakeMailbox
BERLIN = ZoneInfo("Europe/Berlin")


def raw(i, subject):
    when = email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1))
    return (f"From: Anna <anna{i}@example.de>\r\nTo: {helpers.MAIL_USER}\r\nSubject: {subject}\r\n"
            f"Message-ID: <sp{i}@x>\r\nDate: {when}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nHallo\r\n").encode()


class Zeiten(unittest.TestCase):
    def at(self, *a):
        return datetime.datetime(*a, tzinfo=BERLIN)

    def test_fixed_times(self):
        thu = self.at(2026, 11, 12, 10, 0)            # a Thursday morning
        self.assertEqual(spaeter.when("abend", thu), self.at(2026, 11, 12, 18, 0))
        self.assertEqual(spaeter.when("abend", self.at(2026, 11, 12, 17, 58)), self.at(2026, 11, 13, 18, 0))
        self.assertEqual(spaeter.when("morgen", thu), self.at(2026, 11, 13, 8, 0))
        self.assertEqual(spaeter.when("wochenende", thu), self.at(2026, 11, 14, 9, 0))
        self.assertEqual(spaeter.when("wochenende", self.at(2026, 11, 14, 10, 0)), self.at(2026, 11, 21, 9, 0))
        self.assertEqual(spaeter.when("woche", thu), self.at(2026, 11, 16, 8, 0))
        self.assertEqual(spaeter.when("woche", self.at(2026, 11, 16, 7, 0)), self.at(2026, 11, 23, 8, 0))
        with self.assertRaises(ValueError):
            spaeter.when("gleich", thu)

    def test_own_time_only_within_bounds(self):
        now = 1_800_000_000
        self.assertEqual(spaeter.until("u", "at", now + 3600, now), now + 3600)
        for bad in (now + 60, now + 400 * 86400, "1800003600", None):
            with self.assertRaises(ValueError):
                spaeter.until("u", "at", bad, now)


class Ablauf(unittest.TestCase):
    NAME = "Später Sina"

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        FMB.reset(inbox=[raw(1, "Steuer später"), raw(2, "Urlaub"), raw(3, "Weg damit")])
        helpers.set_config(mail=True, mail_manage=True, mail_later=False)
        cls.c, cls.uid = profile(cls.NAME)
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(mail=False, mail_manage=False, mail_later=False, deny={})

    def ref(self, subject):
        m = next(m for m in FMB.boxes["INBOX"] if f"Subject: {subject}".encode() in m["raw"])
        return f"{self.acct}:{m['uid']}"

    def where(self, i):
        return next((b for b, ms in FMB.boxes.items() for m in ms if f"<sp{i}@x>".encode() in m["raw"]), None)

    def test_a_off_blocked_and_input(self):
        r = self.c.post("/api/profile/mail/snooze", json={"id": self.ref("Urlaub"), "when": "morgen"})
        self.assertEqual(r.status_code, 403)                       # switch off
        helpers.set_config(mail_later=True)
        helpers.set_config(deny={"mailspaeter": [self.uid]})
        self.assertEqual(self.c.get("/api/profile/mail/snooze").status_code, 403)
        helpers.set_config(deny={})
        for bad in ({"id": self.ref("Urlaub"), "when": "gleich"}, {"id": self.ref("Urlaub"), "when": "at", "at": 5},
                    {"id": "../x", "when": "morgen"}):
            self.assertEqual(self.c.post("/api/profile/mail/snooze", json=bad).status_code, 400, bad)
        self.assertEqual(self.c.post("/api/profile/mail/snooze/back", json={"mid": "<nie@x>"}).status_code, 404)
        self.assertEqual(self.where(2), "INBOX")

    def test_b_put_due_back_unread_and_back_now(self):
        helpers.set_config(mail_later=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.c.post("/api/profile/mail/snooze", json={"id": self.ref("Steuer später"), "when": "woche"})
            self.assertEqual(r.status_code, 200, r.text)
            r2 = self.c.post("/api/profile/mail/snooze", json={"id": self.ref("Urlaub"), "when": "at",
                                                              "at": int(time.time()) + 7200})
            self.assertEqual(r2.status_code, 200, r2.text)
        later = tidy.state(self.uid)["root"] + "/" + spaeter.FOLDER if tidy.state(self.uid).get("root") else spaeter.FOLDER
        self.assertEqual((self.where(1), self.where(2)), (tidy._utf7(later), tidy._utf7(later)))
        got = self.c.get("/api/profile/mail/snooze")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual([x["subject"] for x in got.json()["items"]],
                         ["Urlaub", "Steuer später"])              # the soonest first
        self.assertIn("mail: later put", out.getvalue())
        self.assertNotIn("Steuer", out.getvalue())
        self.assertNotIn("anna", out.getvalue())
        # not due yet: nothing moves; due (a fixed now far ahead): back into the inbox, unread
        self.assertEqual(spaeter.bring(self.uid, now=time.time()), 0)
        helpers.set_config(mail_later=False)                       # off later: still comes back
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(spaeter.bring(self.uid, now=r2.json()["until"] + 1), 1)
        self.assertEqual(self.where(2), "INBOX")
        self.assertFalse(next(m for m in FMB.boxes["INBOX"] if b"<sp2@x>" in m["raw"])["seen"])
        helpers.set_config(mail_later=True)
        # „Jetzt zurückholen“
        r = self.c.post("/api/profile/mail/snooze/back", json={"mid": "<sp1@x>"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.where(1), "INBOX")
        self.assertEqual(self.c.get("/api/profile/mail/snooze").json()["items"], [])

    def test_c_moved_away_by_hand_is_dropped(self):
        helpers.set_config(mail_later=True)
        r = self.c.post("/api/profile/mail/snooze", json={"id": self.ref("Weg damit"), "when": "morgen"})
        self.assertEqual(r.status_code, 200, r.text)
        box = self.where(3)
        m = next(m for m in FMB.boxes[box] if b"<sp3@x>" in m["raw"])
        FMB.boxes[box].remove(m)                                   # the person moved it away in another program
        FMB.boxes.setdefault("Elsewhere", []).append(m)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(spaeter.bring(self.uid, now=r.json()["until"] + 1), 0)
        self.assertIn("mail: later gone | 1", out.getvalue())
        self.assertEqual(spaeter.items(self.uid), [])


if __name__ == "__main__":
    unittest.main()
