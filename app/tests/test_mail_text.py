"""The text of a mail without quoted replies and signature (mail.plain): what the model and the page get. Dominik
2026-10-21 „2“: shorter text for summaries and reply suggestions, the person's own words only."""
import email
import email.policy
import unittest

from tests import helpers

import panel  # noqa: E402
import mail  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FMB = helpers.FakeMailbox


def own(body):
    raw = f"From: a@x.de\r\nSubject: s\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode()
    return mail.plain(email.message_from_bytes(raw, policy=email.policy.default))[0]


class Plain(unittest.TestCase):
    def test_quotes_and_signatures_go(self):
        for tail in ("Am 20.10.2026 um 10:00 schrieb Anna <anna@x.de>:\r\n> alt",
                     "Am Mo., 20. Okt. 2026 um 10:00 Uhr schrieb Anna <\r\nanna@x.de>:\r\n> alt",
                     "On Mon, Oct 20, 2026 at 10:00 AM Anna <\r\nanna@x.de> wrote:\r\n> old",
                     "________________________________\r\nVon: Anna\r\nGesendet: Montag",
                     "Von meinem iPhone gesendet", "Sent from my iPhone", "Get Outlook for iOS",
                     "-- \r\nAnna Muster\r\nTel. 123"):
            with self.subTest(tail=tail[:30]):
                self.assertEqual(own("Passt, bis morgen.\r\n\r\n" + tail), "Passt, bis morgen.")

    def test_own_words_stay(self):
        text = "Am Montag kommt der Techniker.\r\nEr schrieb mir gestern: alles gut."
        self.assertEqual(own(text), text.replace("\r", ""))
        self.assertEqual(own("> nur ein Zitat"), "> nur ein Zitat")      # only a forwarded text: kept



def letter(frm, mid, subject, text, refs="", hour=10):
    head = f"In-Reply-To: {refs.split()[-1]}\r\nReferences: {refs}\r\n" if refs else ""
    return (f"From: {frm}\r\nTo: x@y.de\r\nSubject: {subject}\r\nMessage-ID: {mid}\r\n{head}"
            f"Date: Mon, 20 Oct 2026 {hour}:00:00 +0200\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{text}\r\n").encode()


class Thread(unittest.TestCase):
    """Unterhaltung (Dominik 2026-10-21 „1“): the other mails of a conversation by Message-ID, from the inbox and the
    sent folder, oldest first, each with its own text only; a mail that only looks alike never counts."""

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True)
        admin = TestClient(panel.app)
        admin.post("/api/login", json={"password": "secret-admin"})
        admin.post("/api/admin/profiles", json={"name": "Verlauf Vio", "pin": "1234"})
        cls.c = TestClient(panel.app)
        assert cls.c.post("/api/profile/login", json={"name": "Verlauf Vio", "pin": "1234"}).status_code == 200
        cls.uid = cls.c.get("/api/whoami").json()["profile"]["id"]
        FMB.reset()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False)

    def setUp(self):
        FMB.reset()
        mail.IMAP = FMB
        mail._bodies.clear()
        self.a = FMB.put("INBOX", letter("Bob <bob@x.de>", "<t-a@x>", "Grillen", "Kommst du Samstag?"))
        FMB.put("Sent Messages", letter(f"Anna <{helpers.MAIL_USER}>", "<t-b@x>", "Re: Grillen",
                                        "Ja, gern.\r\n\r\nAm 20.10.2026 um 10:00 schrieb Bob <bob@x.de>:\r\n> Kommst du Samstag?", "<t-a@x>", 11))
        self.c3 = FMB.put("INBOX", letter("Bob <bob@x.de>", "<t-c@x>", "Re: Grillen", "Super, bis dann.", "<t-a@x> <t-b@x>", 12))
        FMB.put("INBOX", letter("Eve <eve@x.de>", "<t-d@x>", "Re: Grillen", "Fremd", "<t-a@x>2", 13))   # only looks alike

    def test_the_conversation_oldest_first_own_words_only(self):
        r = self.c.get("/api/profile/mail/thread", params={"id": f"{self.acct}:{self.c3}"})
        self.assertEqual(r.status_code, 200, r.text)
        got = r.json()["items"]
        self.assertEqual([(x["text"], x["own"]) for x in got], [("Kommst du Samstag?", False), ("Ja, gern.", True)])
        self.assertEqual(got[1]["folder"], "Sent Messages")
        got = self.c.get("/api/profile/mail/thread", params={"id": f"{self.acct}:{self.a}"}).json()["items"]
        self.assertEqual([x["text"] for x in got], ["Ja, gern.", "Super, bis dann."])            # the replies to it
        self.assertFalse([c for c in FMB.calls if c[0] == "STORE"])                               # nothing marked read

    def test_none_others_and_guests(self):
        lone = FMB.put("INBOX", letter("Zoe <z@x.de>", "<t-e@x>", "Allein", "Nur ich."))
        self.assertEqual(self.c.get("/api/profile/mail/thread", params={"id": f"{self.acct}:{lone}"}).json()["items"], [])
        self.assertEqual(self.c.get("/api/profile/mail/thread", params={"id": "m00000000:1"}).status_code, 400)
        self.assertIn(TestClient(panel.app).get("/api/profile/mail/thread", params={"id": f"{self.acct}:{lone}"}).status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
