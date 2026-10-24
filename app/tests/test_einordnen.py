"""Alle Mails hier einordnen (einordnen.py, Dominik 2026-10-24 „1-3“): every mail of a folder once by the fixed rules.

- First a proposal (nothing moves): the profile's mail rules decide first, then, where „Mails aufräumen“ is on, its
  stages 1 to 3; a mail no rule knows stays, so does one for its own folder. No limit of days: a mail of 2019 counts.
- „Verschieben“ moves what was proposed; „Rückgängig“ brings every mail back into its folder by its Message-ID.
- Never out of sent, drafts, trash or junk; an unknown mailbox 404; a folder the server numbered anew moves nothing.
- „Abbrechen“ stops after the step running; one run per profile; off (Mails ordnen) and guests: nothing.
- Logs carry fixed words and numbers only (never a sender, subject or folder); the run for „Rückgängig“ lies sealed.

The fake mailbox (helpers.FakeMailbox); the runs go in threads, the tests wait for their state (no wall clock).
"""
import contextlib
import io
import os
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import einordnen  # noqa: E402
import guard  # noqa: E402
import mail  # noqa: E402
import mailregeln  # noqa: E402
import tidy  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FMB = helpers.FakeMailbox
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def old(frm, subject, mid, extra=""):
    return (f"From: {frm}\r\nTo: {helpers.MAIL_USER}\r\nSubject: {subject}\r\nMessage-ID: {mid}\r\n"
            f"Date: Tue, 05 Mar 2019 09:00:00 +0100\r\n{extra}Content-Type: text/plain; charset=utf-8\r\n\r\nHallo\r\n").encode()


def fill():
    FMB.reset()
    FMB.validity = b"1"
    for name in ("Archive", "Auto", "Deleted Messages", "Junk"):
        FMB.boxes[name] = []
    for i in range(3):
        FMB.put("Archive", old("Anna <anna@autohaus-kehl.de>", f"Werkstatt {i}", f"<w{i}@x>"))
    for i in range(2):
        FMB.put("Archive", old("Heise <news@heise.de>", f"Die Woche {i}", f"<n{i}@x>", "List-Unsubscribe: <mailto:u@heise.de>\r\n"))
    FMB.put("Archive", old("Oma <oma@example.de>", "Kuchen", "<o1@x>"))
    FMB.put("Auto", old("Anna <anna@autohaus-kehl.de>", "Schon da", "<w9@x>"))


def subjects(box):
    return sorted(m["raw"].decode().split("Subject: ")[1].split("\r\n")[0] for m in FMB.boxes.get(box, []))


class Sort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True, mail_tidy=True)
        cls.c, cls.uid = profile("Einordnen Erna")
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        FMB.validity = b"1"
        helpers.set_config(mail=False, mail_manage=False, mail_tidy=False)
        mailregeln.forget(cls.uid)
        einordnen.forget(cls.uid)
        tidy._mut(cls.uid, lambda d: tidy.acct_state(d, cls.acct).update(mode="off"))

    def setUp(self):
        fill()
        mail.IMAP = FMB
        mailregeln.forget(self.uid)
        einordnen.forget(self.uid)
        tidy._mut(self.uid, lambda d: tidy.acct_state(d, self.acct).update(mode="off"))
        for k in [k for k in guard._rate if k[0] in ("postordnen", "postmehr")]:
            guard._rate.pop(k, None)
        r = self.c.post("/api/profile/mail/rules", json={"account": self.acct, "when": {"from": "@autohaus-kehl.de"},
                                                          "then": {"folder": "Auto"}})
        assert r.status_code == 200, r.text

    def wait(self):
        for _ in range(2000):
            j = einordnen._jobs.get(self.uid)
            if not j or j["state"] not in ("scan", "move", "back"):
                return self.c.get("/api/profile/mail/einordnen").json()
            time.sleep(0.005)
        self.fail("the run never ended")

    def run_logged(self, fn):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = fn()
            got = self.wait()
        return r, got, out.getvalue()

    def test_proposal_move_and_back(self):
        r, got, log = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"}))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((got["state"], got["by"], got["stays"], got["looked"]), ("ready", [["Auto", 3]], 3, 6))
        self.assertEqual(len(FMB.boxes["Archive"]), 6)                               # a proposal moves nothing
        self.assertIn("mail: sort folder proposal | 6 looked, 3 to move, 3 stay", log)
        r, got, log = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen/go"))
        self.assertEqual((r.status_code, got["state"], got["moved"]), (200, "done", 3), r.text)
        self.assertEqual(subjects("Auto"), ["Schon da", "Werkstatt 0", "Werkstatt 1", "Werkstatt 2"])
        self.assertEqual(subjects("Archive"), ["Die Woche 0", "Die Woche 1", "Kuchen"])
        self.assertEqual(got["undo"]["n"], 3)
        self.assertIn("mail: sort folder moved | 3", log)
        for secret in ("autohaus", "Werkstatt", "Archive", "Auto ", "Anna"):
            self.assertNotIn(secret, log)
        # sealed: no sender's Message-ID in the file
        with open(einordnen._file(self.uid), encoding="utf-8") as f:
            self.assertNotIn("<w0@x>", f.read())
        self.assertEqual(oct(os.stat(einordnen._file(self.uid)).st_mode & 0o777), "0o600")
        r, got, log = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen/back"))
        self.assertEqual((r.status_code, got["kind"], got["state"], got["moved"]), (200, "back", "done", 3), r.text)
        self.assertEqual(len(FMB.boxes["Archive"]), 6)
        self.assertEqual(subjects("Auto"), ["Schon da"])                             # the mail that was there stays
        self.assertIsNone(got["undo"])
        self.assertEqual(self.c.post("/api/profile/mail/einordnen/back").status_code, 404)

    def test_tidying_stages_where_it_is_on(self):
        tidy._mut(self.uid, lambda d: tidy.acct_state(d, self.acct).update(mode="safe"))
        _, got, _ = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"}))
        self.assertEqual(dict(map(tuple, got["by"])), {"Auto": 3, "Spark/Newsletter": 2})
        self.assertEqual(got["stays"], 1)                                            # Oma: no rule knows her
        self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen/go"))
        self.assertEqual(subjects("Spark/Newsletter"), ["Die Woche 0", "Die Woche 1"])   # the folder was made
        self.assertEqual(subjects("Archive"), ["Kuchen"])

    def test_the_inbox_and_never_special_folders(self):
        FMB.put("INBOX", old("Anna <anna@autohaus-kehl.de>", "Neu", "<i1@x>"))
        _, got, _ = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "INBOX"}))
        self.assertEqual((got["state"], got["folder"], got["by"]), ("ready", "INBOX", [["Auto", 1]]))
        self.c.post("/api/profile/mail/einordnen/stop")                               # Verwerfen
        self.assertNotIn("state", self.c.get("/api/profile/mail/einordnen").json())
        for folder in ("Sent Messages", "Deleted Messages", "Junk", "Drafts"):
            r = self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": folder})
            self.assertEqual(r.status_code, 400, folder)
        self.assertEqual(self.c.post("/api/profile/mail/einordnen", json={"account": "m00000000", "folder": "Archive"}).status_code, 404)
        self.assertEqual(self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Gibtsnicht"}).status_code, 404)
        self.assertEqual(self.c.post("/api/profile/mail/einordnen/go").status_code, 404)

    def test_renumbered_folder_moves_nothing(self):
        self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"}))
        FMB.validity = b"2"
        _, got, log = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen/go"))
        self.assertEqual((got["state"], got["err"], got["moved"]), ("error", "renumbered", 0))
        self.assertEqual(len(FMB.boxes["Archive"]), 6)
        self.assertIn("mail: sort folder move failed (ValueError)", log)

    def test_stop_after_the_step_and_one_run_at_a_time(self):
        def hold(*a, **k):
            einordnen._jobs[self.uid]["stop"] = True
        with mock.patch.object(einordnen, "PACK", 2), mock.patch.object(einordnen.vorrang, "hold", side_effect=hold):
            _, got, _ = self.run_logged(lambda: self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"}))
        self.assertEqual((got["state"], got["looked"]), ("stopped", 2))
        self.assertEqual(self.c.post("/api/profile/mail/einordnen/go").status_code, 404)   # a stopped proposal is not carried out
        einordnen._jobs[self.uid] = dict(einordnen._jobs[self.uid], state="scan")
        try:
            r = self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"})
            self.assertEqual(r.status_code, 400)
        finally:
            einordnen._jobs.pop(self.uid, None)
        busy = {f"x{i}": {"state": "move"} for i in range(einordnen.JOBS)}
        with mock.patch.dict(einordnen._jobs, busy):
            r = self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"})
            self.assertEqual(r.status_code, 400)
            self.assertEqual(einordnen.for_live()["going"], einordnen.JOBS)

    def test_off_and_guests(self):
        helpers.set_config(mail=True, mail_manage=False, mail_tidy=True)
        try:
            self.assertEqual(self.c.get("/api/profile/mail/einordnen").status_code, 403)
            self.assertEqual(self.c.post("/api/profile/mail/einordnen", json={"account": self.acct, "folder": "Archive"}).status_code, 403)
        finally:
            helpers.set_config(mail=True, mail_manage=True, mail_tidy=True)
        anon = TestClient(panel.app)
        self.assertIn(anon.get("/api/profile/mail/einordnen").status_code, (401, 403))
        self.assertIn(anon.post("/api/profile/mail/einordnen/go").status_code, (401, 403))
        self.assertEqual(set(einordnen.for_live()), {"going", "runs", "moved", "back"})


if __name__ == "__main__":
    unittest.main()
