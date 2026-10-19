"""Mailclient Stufe C (Dominik 2026-10-19 „4a 5a“): search with operators, attachments as downloads, forwarding.

- Suche: von:, betreff:, hat:anhang, ist:markiert (and from:, subject:, has:attachment, is:flagged) are compared as
  text on the header fields, never run; an unknown prefix is only a word; in a folder the server searches too.
- Anhang laden (with Mails ordnen): only from an own message, as a download (octet-stream, nosniff, sandbox), never
  shown in the page; a number that is not there is 404; the log never carries a file name.
- Weiterleiten (with Mails senden): the original below the own words, subject „Fwd: …“, its files only when asked
  and together at most senden.FORWARD_FILES; from a folder only with Mails ordnen; nothing goes out before „Senden“.

The fake mailbox (helpers.FakeMailbox) and a fake SMTP; no wall clock, no network.
"""
import contextlib
import email
import email.policy
import io
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import mail  # noqa: E402
import netguard  # noqa: E402
import postfach  # noqa: E402
import senden  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_mails_senden import FakeSMTP, fresh_day  # noqa: E402

FMB = helpers.FakeMailbox
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PDF = b"%PDF-1.4 Rechnung 4711 %%EOF"


def with_file(frm, subject, name="Rechnung 4711.pdf", data=PDF, mid=None):
    import base64
    b64 = base64.b64encode(data).decode()
    raw = (f"From: {frm}\r\nTo: {helpers.MAIL_USER}\r\nSubject: {subject}\r\nMessage-ID: {mid or '<f-1@x>'}\r\n"
           f"Date: Mon, 19 Oct 2026 10:00:00 +0200\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=XX\r\n\r\n"
           f"--XX\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nAnbei die Rechnung.\r\n"
           f"--XX\r\nContent-Type: application/pdf\r\nContent-Disposition: attachment; filename=\"{name}\"\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--XX--\r\n").encode()
    return raw


def fill():
    FMB.reset(inbox=[helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Werkstatt fertig", "Der Wagen ist fertig.", mid="<c-1@x>"),
                     with_file("Shop <rechnung@shop.de>", "Ihre Rechnung", mid="<c-2@x>"),
                     helpers.box_mail("Heise <news@heise.de>", "Rechnung? Nein, Newsletter", "…", mid="<c-3@x>")])
    FMB.boxes["Archive"] = [dict(FMB.boxes["INBOX"][1], uid=7)]
    FMB.boxes["INBOX"][0]["flags"] = ["\\Flagged"]
    FakeSMTP.sent, FakeSMTP.tls_offered, FakeSMTP.refuse = [], True, set()


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Base(unittest.TestCase):
    NAME = "Stufe Clara"

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        senden.SMTP = senden.SMTP_SSL = FakeSMTP
        helpers.set_config(mail=True, mail_manage=True, mail_send=True)
        cls.c, cls.uid = profile(cls.NAME)
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        senden.SMTP, senden.SMTP_SSL = netguard.SMTP, netguard.SMTP_SSL
        helpers.set_config(mail=False, mail_manage=False, mail_send=False)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        senden._pending.clear()
        fresh_day()
        mail._cache.clear()
        mail._bodies.clear()
        for k in [k for k in guard._rate if k[0] in ("post", "postordnen", "mailsenden")]:
            guard._rate.pop(k, None)

    def ref(self, n, box="INBOX"):
        return f"{self.acct}:{FMB.boxes[box][n]['uid']}"


class Search(Base):
    NAME = "Stufe Sara"

    def test_words_and_operators(self):
        self.assertEqual(mail._words("von:Anna betreff:werkstatt hat:anhang"), ["from:anna", "subject:werkstatt", "hat:anhang"])
        self.assertEqual(mail._words("from:x@y.de is:flagged has:attachment"), ["from:x@y.de", "ist:markiert", "hat:anhang"])
        self.assertEqual(mail._words("ab:morgen Mails von Anna"), ["morgen", "anna"])     # no operator, no filler
        h = {"from": "Anna <anna@x.de>", "subject": "Rechnung", "attach": False, "flagged": True, "unread": False}
        self.assertTrue(mail.fits(["from:anna", "ist:markiert"], h))
        self.assertFalse(mail.fits(["subject:anna"], h))
        self.assertFalse(mail.fits(["hat:anhang"], h))
        self.assertFalse(mail.fits(["ist:ungelesen"], h))

    def query(self, q):
        r = self.c.get("/api/profile/mail/inbox", params={"q": q})
        self.assertEqual(r.status_code, 200, r.text)
        return sorted(x["subject"] for x in r.json()["items"])

    def test_inbox_search(self):
        self.assertEqual(self.query("rechnung"), ["Ihre Rechnung", "Rechnung? Nein, Newsletter"])
        self.assertEqual(self.query("betreff:rechnung von:shop"), ["Ihre Rechnung"])
        self.assertEqual(self.query("hat:anhang"), ["Ihre Rechnung"])
        self.assertEqual(self.query("ist:markiert"), ["Werkstatt fertig"])
        items = self.c.get("/api/profile/mail/inbox").json()["items"]
        self.assertEqual(sorted((x["subject"], x["attach"]) for x in items)[0], ("Ihre Rechnung", True))

    def test_folder_search_on_the_server(self):
        r = self.c.get("/api/profile/mail/folder", params={"account": self.acct, "folder": "Archive", "q": "hat:anhang"})
        self.assertEqual((r.status_code, [x["subject"] for x in r.json()["items"]]), (200, ["Ihre Rechnung"]), r.text)
        r = self.c.get("/api/profile/mail/folder", params={"account": self.acct, "folder": "Archive", "q": "von:anna"})
        self.assertEqual(r.json()["items"], [])


class Files(Base):
    def test_download_only_as_a_file(self):
        msg = self.c.get("/api/profile/mail/message", params={"id": self.ref(1)}).json()
        self.assertEqual(msg["parts"], [{"n": 0, "name": "Rechnung 4711.pdf", "kb": 1}])
        before = mail.files_today()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.c.get("/api/profile/mail/file", params={"id": self.ref(1), "n": 0})
            self.assertEqual(self.c.get("/api/profile/mail/file", params={"id": self.ref(1), "n": 3}).status_code, 404)
            self.assertEqual(self.c.get("/api/profile/mail/file", params={"id": self.ref(0), "n": 0}).status_code, 404)
        self.assertEqual((r.status_code, r.content), (200, PDF))
        self.assertEqual(r.headers["content-type"], "application/octet-stream")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["content-security-policy"], "sandbox")
        self.assertTrue(r.headers["content-disposition"].startswith("attachment;"))
        log = out.getvalue()
        self.assertIn("mail: file shown | 1 KB |", log)
        self.assertIn("mail: file refused, not there |", log)
        self.assertNotIn("Rechnung", log)
        self.assertEqual(mail.files_today(), before + 1)                       # Live: a number, never which
        r = self.c.get("/api/profile/mail/file", params={"id": f"{self.acct}:7", "folder": "Archive", "n": 0})
        self.assertEqual((r.status_code, r.content), (200, PDF))

    def test_others_off_and_guests(self):
        other, _ = profile("Stufe Carlo")
        self.assertEqual(other.get("/api/profile/mail/file", params={"id": self.ref(1), "n": 0}).status_code, 400)
        self.assertIn(TestClient(panel.app).get("/api/profile/mail/file", params={"id": self.ref(1)}).status_code, (401, 403))
        helpers.set_config(mail_manage=False)
        try:
            self.assertEqual(self.c.get("/api/profile/mail/file", params={"id": self.ref(1), "n": 0}).status_code, 403)
        finally:
            helpers.set_config(mail_manage=True)

    def test_a_cut_message_gives_no_file(self):
        old = mail.FILE_MAX
        mail.FILE_MAX = 10           # the whole message is bigger than what may be fetched: never half a file
        try:
            self.assertEqual(self.c.get("/api/profile/mail/file", params={"id": self.ref(1), "n": 0}).status_code, 404)
        finally:
            mail.FILE_MAX = old


class Forward(Base):
    NAME = "Stufe Fritz"

    def preview(self, **kw):
        return self.c.post("/api/profile/mail/send/preview", json=dict({"to": "carla@example.org"}, **kw))

    def test_forward_with_and_without_files(self):
        r = self.preview(forward=self.ref(1), text="Schau mal.", files=True)
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual(p["subject"], "Fwd: Ihre Rechnung")
        self.assertTrue(p["text"].startswith("Schau mal.\n\n---------- Weitergeleitete Nachricht ----------\nVon: Shop"))
        self.assertIn("Anbei die Rechnung.", p["text"])
        self.assertEqual(p["files"], ["Rechnung 4711.pdf (1 KB)"])
        self.assertEqual(FakeSMTP.sent, [])                                  # the preview sends nothing
        self.assertEqual(self.c.post("/api/profile/mail/send", json={"token": p["token"]}).status_code, 200)
        sent = email.message_from_bytes(FakeSMTP.sent[0]["raw"], policy=email.policy.default)
        self.assertEqual([a.get_content() for a in sent.iter_attachments()], [PDF])
        p = self.preview(forward=self.ref(1)).json()                        # without files, without own words
        self.assertEqual(p["files"], [])
        self.assertTrue(p["text"].startswith("---------- Weitergeleitete Nachricht"))

    def test_limits(self):
        old = senden.FORWARD_FILES
        senden.FORWARD_FILES = 10
        try:
            r = self.preview(forward=self.ref(1), files=True)
            self.assertEqual(r.status_code, 400)
            self.assertIn("forward without them", r.json()["detail"])
        finally:
            senden.FORWARD_FILES = old
        self.assertEqual(self.preview(forward=f"{self.acct}:999").status_code, 404)
        helpers.set_config(mail_manage=False)
        try:
            self.assertEqual(self.preview(forward=f"{self.acct}:7", folder="Archive").status_code, 403)
            self.assertEqual(self.preview(forward=self.ref(1)).status_code, 200)    # the inbox needs only Mails senden
        finally:
            helpers.set_config(mail_manage=True)


if __name__ == "__main__":
    unittest.main()
