"""Mails ordnen auf der Seite E-Mail (postfach.py, plan kalender-mail Stufe 2; function off until the admin allows it):
read/unread, archive, move into an own folder, back right after. Never deleted.

- POST /api/profile/mail/act marks exactly the one message read or unread, moves it into the archive (the server's
  \\Archive folder) or a chosen ordinary folder, and back into the inbox by its Message-ID.
- Never into the trash, the junk, sent or drafts, never a folder created, never a message removed without its copy;
  an id of a mailbox of another profile, an unknown action or a message no longer there is refused.
- Off (admin switch) and guests: nothing. Every outcome has a log line with fixed words, never sender or subject.
- The page shows the buttons only with the function, archives a message off the list and takes it back.

The fake mailbox (helpers.FakeMailbox); no wall clock, no network.
"""
import asyncio
import contextlib
import io
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import mail  # noqa: E402
import postfach  # noqa: E402
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


def fill():
    FMB.reset(inbox=[helpers.box_mail("Anna <anna@example.de>", "Werkstatt fertig", "Der Wagen ist fertig.", mid="<ord-1@x>"),
                     helpers.box_mail("Shop <shop@example.de>", "Rechnung", "Danke", mid="<ord-2@x>")])
    for name in ("Archive", "Projekte", "Deleted Messages", "Junk"):
        FMB.boxes[name] = []


class Act(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True)
        cls.c, cls.uid = profile("Ordnen Olga")
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        for k in [k for k in guard._rate if k[0] == "postordnen"]:
            guard._rate.pop(k, None)

    def act(self, action, uid=100, folder="", mid="", c=None):
        return (c or self.c).post("/api/profile/mail/act", json={"id": f"{self.acct}:{uid}", "action": action, "folder": folder, "mid": mid})

    def test_folders_never_trash_junk_sent_or_drafts(self):
        d = self.c.get("/api/profile/mail/folders", params={"account": self.acct}).json()
        self.assertEqual(d["archive"], "Archive")
        self.assertEqual(d["folders"], ["Archive", "Projekte"])

    def test_read_unread_only_that_message(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.act("read").status_code, 200)
        self.assertEqual([m["seen"] for m in FMB.boxes["INBOX"]], [True, False])
        self.assertEqual(self.act("unread").status_code, 200)
        self.assertEqual([m["seen"] for m in FMB.boxes["INBOX"]], [False, False])
        self.assertIn("mail: page read done", out.getvalue())
        self.assertNotIn("Anna", out.getvalue())
        self.assertNotIn("Werkstatt", out.getvalue())

    def test_archive_and_back(self):
        r = self.act("archive")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["folder"], d["mid"]), ("Archive", "<ord-1@x>"))
        self.assertEqual(len(FMB.boxes["INBOX"]), 1)
        self.assertEqual(len(FMB.boxes["Archive"]), 1)
        r = self.act("back", uid=0, folder="Archive", mid=d["mid"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)
        self.assertEqual(FMB.boxes["Archive"], [])
        self.assertGreaterEqual(postfach.today(), 2)     # Live: a number, never which

    def test_move_into_an_own_folder_only(self):
        self.assertEqual(self.act("move", folder="Projekte").status_code, 200)
        self.assertEqual(len(FMB.boxes["Projekte"]), 1)
        n = FMB.total()
        for bad in ("Deleted Messages", "Junk", "Sent Messages", "Drafts", "INBOX", "Neu angelegt"):
            self.assertEqual(self.act("move", uid=101, folder=bad).status_code, 400, bad)
        self.assertEqual(FMB.total(), n)                    # nothing went anywhere, nothing gone
        self.assertNotIn("Neu angelegt", FMB.boxes)          # never a folder created
        self.assertFalse([c for c in FMB.calls if c[0] in ("CREATE", "EXPUNGE", "RENAME")])

    def test_refused(self):
        self.assertEqual(self.act("delete").status_code, 400)
        self.assertEqual(self.act("read", uid=999).status_code, 404)
        self.assertEqual(self.act("back", uid=0, folder="Archive", mid="<gibt-es-nicht@x>").status_code, 404)
        # code check 19.10. C5: a forged id with a line break never reaches the IMAP command
        self.assertEqual(self.act("back", uid=0, folder="Archive", mid="<a@x>\r\nA1 DELETE INBOX").status_code, 404)
        other, _ = profile("Ordnen Otto")
        self.assertEqual(self.act("archive", c=other).status_code, 400)      # not his mailbox
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/mail/act", json={}).status_code, (401, 403))
        helpers.set_config(mail_manage=False)
        try:
            self.assertEqual(self.act("archive").status_code, 403)
            self.assertEqual(self.c.get("/api/profile/mail/folders", params={"account": self.acct}).status_code, 403)
            self.assertFalse(self.c.get("/api/whoami").json().get("mail_manage"))
        finally:
            helpers.set_config(mail_manage=True)
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False, mail_manage=False)

    def test_archive_from_the_page_and_undo(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        fill()

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    if not mail.get(uid)["accounts"]:
                        r = await pg.request.post(f"http://127.0.0.1:{self.port}/api/profile/mail",
                                                  data={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
                        self.assertEqual(r.status, 200, await r.text())
                    mail._cache.clear()
                    await pg.evaluate("MAIL_ON=true;ORD_ON=true;postStart({profile:PROFILE,mail:true});icTabSet('post','show');goSec('post')")
                    await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.items.length===2")
                    await pg.evaluate("[...document.querySelectorAll('#postview .ld-row')].find(e=>e.textContent.includes('Werkstatt')).click()")
                    await b.until(pg, "!!document.querySelector('#postview .postord [data-o=archive]')")
                    await b.until(pg, "document.querySelectorAll('#postview .postord select option').length>1")
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1)
                    await pg.click("#postview .postord [data-o=archive]")
                    await b.until(pg, "POST.data.items.length===1&&!!document.querySelector('#postview .postundo [data-u]')")
                    self.assertEqual(len(FMB.boxes["Archive"]), 1)
                    await pg.click("#postview .postundo [data-u]")
                    await b.until(pg, "!POST.busy&&POST.data.items.length===2")
                    self.assertEqual(FMB.boxes["Archive"], [])
                    # without the function no buttons
                    await pg.evaluate("ORD_ON=false;[...document.querySelectorAll('#postview .ld-row')][0].click()")
                    await b.until(pg, "!!POST.msg&&!!document.querySelector('#postview .posttext')")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .postord').length"), 0)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
