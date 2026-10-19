"""Mail times in the local zone (Dominik, 2026-10-12): a mail that came at 20:30 was read out as 18:30.
The Date header keeps the sender's offset (often +0000) and mail_read printed it as it was.

- mail.local() puts a mail's time into the person's zone, without one into the Spark's (Europe/Berlin).
- mail_read, mail_list/mail_search and the parcel scan all use it.
No model, no clock: fixed dates, summer and winter time.
"""
import datetime
import email
import unittest
from zoneinfo import ZoneInfo

from tests import helpers

helpers.start()
import chat  # noqa: E402
import mail  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")
RAW = ("From: Anna <anna@example.de>\r\nTo: x@example.de\r\nSubject: Test\r\n"
       "Date: {}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nHallo\r\n")


class _Box:
    def __init__(self, date):
        self.date = date

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def body(self, uid):
        return email.message_from_string(RAW.format(self.date))


class MailZeit(unittest.TestCase):
    def setUp(self):
        self.saved = (mail._Session, mail.get, list(chat._system_zone))
        chat._system_zone[:] = [BERLIN]
        mail.get = lambda uid: {"accounts": [{"id": "m1a2b3c4d", "name": "Privat"}]}

    def tearDown(self):
        mail._Session, mail.get, chat._system_zone[:] = self.saved

    def read(self, date, zone=None):
        # every read is another mailbox under the same id: the opened-mail memory (mail._bodies, V01.0.819) would
        # hand back the first one, so it is dropped like after a change of the mailbox settings
        mail._drop("u1")
        mail._Session = lambda acct: _Box(date)
        return mail.read("u1", "m1a2b3c4d:5", zone)

    def test_utc_header_read_in_berlin_time(self):
        self.assertIn("Date: 12.10.2026 20:30", self.read("Mon, 12 Oct 2026 18:30:00 +0000"))
        self.assertIn("Date: 12.01.2026 19:30", self.read("Mon, 12 Jan 2026 18:30:00 +0000"))     # winter time
        self.assertIn("Date: 12.10.2026 20:30", self.read("Mon, 12 Oct 2026 20:30:00 +0200"))     # already local

    def test_person_zone_wins(self):
        self.assertIn("Date: 12.10.2026 14:30", self.read("Mon, 12 Oct 2026 18:30:00 +0000", ZoneInfo("America/New_York")))

    def test_local_helper_and_day(self):
        d = mail._date("Mon, 12 Oct 2026 23:30:00 +0000")
        self.assertEqual(mail.local(d).strftime("%d.%m. %H:%M"), "13.10. 01:30")     # the parcel scan's day too
        self.assertEqual(mail.local(d, datetime.timezone.utc).hour, 23)

    def test_tool_passes_the_persons_zone(self):
        import inspect
        import chat_tools
        src = inspect.getsource(chat_tools)
        self.assertRegex(src, r"mail\.read, [^\n]*\n\s*chat\.user_zone\(")
        self.assertNotIn('h["date"].astimezone(zone) if zone else h["date"]', inspect.getsource(mail))


if __name__ == "__main__":
    unittest.main()
