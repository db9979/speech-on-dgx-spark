"""Mails löschen und Regel-Vorschlag auf der Seite E-Mail (postfach.py, mailregeln.learn; Dominik 2026-10-20):

- „Löschen“ only with its own switch (chat.mail_delete, off): the message goes into the mailbox's trash (\\Trash),
  „Rückgängig“ brings it back by its Message-ID; nothing is ever removed on the way.
- „Endgültig löschen“ only out of the trash, only with "sure" after the page's question, only the one message whose
  Message-ID matches, with UID EXPUNGE (UIDPLUS); never a plain EXPUNGE, never another message marked deleted.
- A rule never deletes (its "then" knows no such thing); an ordinary move still never goes into the trash.
- The third move of one sender into one folder brings a rule hint once, not again until three more; never with a rule
  for it already there or after „Nicht mehr fragen“. Logs carry fixed words and numbers only.

The fake mailbox (helpers.FakeMailbox); no wall clock, no network.
"""
import asyncio
import contextlib
import io
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import guard  # noqa: E402
import mail  # noqa: E402
import mailregeln  # noqa: E402
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
    FMB.reset(inbox=[helpers.box_mail("Anna <anna@example.de>", "Werkstatt fertig", "Der Wagen ist fertig.", mid="<del-1@x>"),
                     helpers.box_mail("Shop <shop@example.de>", "Rechnung", "Danke", mid="<del-2@x>")])
    for name in ("Archive", "Projekte", "Deleted Messages", "Junk"):
        FMB.boxes[name] = []
    FMB.after_login = ("IMAP4REV1", "MOVE", "UIDPLUS")


class Base(unittest.TestCase):
    NAME = "Loesch Lotte"

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True, mail_delete=True)
        cls.c, cls.uid = profile(cls.NAME)
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        FMB.after_login = ("IMAP4REV1", "MOVE")
        helpers.set_config(mail=False, mail_manage=False, mail_delete=False)
        mailregeln.forget(cls.uid)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True, mail_delete=True)
        mailregeln.forget(self.uid)
        for k in [k for k in guard._rate if k[0] == "postordnen"]:
            guard._rate.pop(k, None)

    def act(self, action, uid=100, folder="", mid="", src="INBOX", **extra):
        return self.c.post("/api/profile/mail/act", json=dict({"id": f"{self.acct}:{uid}", "action": action, "folder": folder,
                                                               "mid": mid, "src": src}, **extra))


class Delete(Base):
    def test_delete_goes_to_the_trash_and_comes_back(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.act("delete")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["folder"], d["mid"]), ("Deleted Messages", "<del-1@x>"))
        self.assertEqual(len(FMB.boxes["INBOX"]), 1)
        self.assertEqual(len(FMB.boxes["Deleted Messages"]), 1)
        self.assertNotIn("EXPUNGE", [c[0] for c in FMB.calls if c[0] == "EXPUNGE"])
        self.assertIn("mail: page delete done | 1", out.getvalue())
        self.assertNotIn("Anna", out.getvalue())
        self.assertGreaterEqual(postfach.deleted_today(), 1)   # Live: a number, never which
        r = self.act("back", uid=0, folder="Deleted Messages", mid=d["mid"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)
        self.assertEqual(FMB.boxes["Deleted Messages"], [])

    def test_off_switch_deletes_nothing(self):
        helpers.set_config(mail=True, mail_manage=True, mail_delete=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.act("delete").status_code, 400)
            self.assertEqual(self.c.post("/api/profile/mail/acts", json={"ids": [f"{self.acct}:100"], "action": "delete"}).status_code, 400)
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)
        self.assertEqual(FMB.boxes["Deleted Messages"], [])
        self.assertIn("mail: page delete failed", out.getvalue())

    def test_many_into_the_trash_and_back(self):
        r = self.c.post("/api/profile/mail/acts", json={"ids": [f"{self.acct}:100", f"{self.acct}:101"], "action": "delete"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["n"], d["folder"]), (2, "Deleted Messages"))
        self.assertEqual(FMB.boxes["INBOX"], [])
        m = d["moved"][0]
        r = self.c.post("/api/profile/mail/acts/back", json={"account": m["acct"], "folder": "Deleted Messages", "mids": m["mids"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)

    def test_erase_only_from_the_trash_only_when_sure_only_that_one(self):
        self.assertEqual(self.act("delete").status_code, 200)
        self.assertEqual(self.act("delete", uid=101).status_code, 200)
        FMB.boxes["Deleted Messages"][1]["flags"].append("\\Deleted")   # another one marked by a mail program
        trash = FMB.boxes["Deleted Messages"]
        first = trash[0]["uid"]
        self.assertEqual(self.act("erase", uid=first, mid="<del-1@x>", src="Deleted Messages").status_code, 400)   # not sure
        self.assertEqual(self.act("erase", uid=first, mid="<del-1@x>", src="INBOX", sure=True).status_code, 400)
        self.assertEqual(self.act("erase", uid=first, mid="<del-2@x>", src="Deleted Messages", sure=True).status_code, 404)
        self.assertEqual(len(FMB.boxes["Deleted Messages"]), 2)
        self.assertEqual(self.c.post("/api/profile/mail/acts", json={"ids": [f"{self.acct}:{first}"], "action": "erase",
                                                                     "src": "Deleted Messages"}).status_code, 400)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.act("erase", uid=first, mid="<del-1@x>", src="Deleted Messages", sure=True)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([b"del-2@x" in m["raw"] for m in FMB.boxes["Deleted Messages"]], [True])   # the other one stays
        self.assertNotIn(("EXPUNGE", ()), FMB.calls)    # never a plain EXPUNGE
        self.assertIn("mail: page erase done | 1", out.getvalue())

    def test_erase_needs_uidplus(self):
        FMB.after_login = ("IMAP4REV1", "MOVE")
        self.assertEqual(self.act("delete").status_code, 200)
        u = FMB.boxes["Deleted Messages"][0]["uid"]
        self.assertEqual(self.act("erase", uid=u, mid="<del-1@x>", src="Deleted Messages", sure=True).status_code, 400)
        self.assertEqual(len(FMB.boxes["Deleted Messages"]), 1)

    def test_no_trash_no_delete(self):
        del FMB.boxes["Deleted Messages"]
        self.assertEqual(self.act("delete").status_code, 400)
        self.assertEqual(len(FMB.boxes["INBOX"]), 2)

    def test_a_move_still_never_goes_into_the_trash_and_rules_never_delete(self):
        self.assertEqual(self.act("move", folder="Deleted Messages").status_code, 400)
        self.assertEqual(FMB.boxes["Deleted Messages"], [])
        with self.assertRaises(ValueError):
            mailregeln.add(self.uid, {"account": self.acct, "when": {"from": "anna@example.de"},
                                      "then": {"folder": "Deleted Messages"}})
        self.assertEqual(set(mailregeln.clean(self.uid, {"when": {"from": "anna@example.de"}, "then": {"read": True, "delete": True}})["then"]),
                         {"folder", "read", "flag", "quiet"})


class Hint(Base):
    NAME = "Hinweis Hanna"

    def move_anna(self):
        FMB.put("INBOX", helpers.box_mail("Anna <anna@example.de>", "Noch was"))
        u = FMB.boxes["INBOX"][-1]["uid"]
        r = self.act("move", uid=u, folder="Projekte")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json().get("hint")

    def test_third_move_asks_once(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertIsNone(self.move_anna())
            self.assertIsNone(self.move_anna())
            h = self.move_anna()
        self.assertEqual(h, {"account": self.acct, "from": "anna@example.de", "folder": "Projekte", "n": 3})
        self.assertIn("mail: rule hint | 3", out.getvalue())
        self.assertNotIn("anna", out.getvalue())
        self.assertIsNone(self.move_anna())    # counted from zero again
        self.assertIsNone(self.move_anna())
        self.assertIsNotNone(self.move_anna())

    def test_never_and_an_existing_rule_keep_quiet(self):
        r = self.c.post("/api/profile/mail/rules/never", json={"account": self.acct, "from": "anna@example.de", "folder": "Projekte"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([self.move_anna() for _ in range(4)], [None] * 4)
        mailregeln.forget(self.uid)
        mailregeln.add(self.uid, {"account": self.acct, "when": {"from": "anna@example.de"}, "then": {"folder": "Projekte"}})
        self.assertEqual([self.move_anna() for _ in range(4)], [None] * 4)

    def test_old_moves_do_not_count(self):
        now = 10_000_000
        for i in range(2):
            self.assertIsNone(mailregeln.learn(self.uid, self.acct, ["anna@example.de"], "Projekte", now=now + i))
        later = now + mailregeln.LEARN_DAYS * 86400 + 10
        self.assertIsNone(mailregeln.learn(self.uid, self.acct, ["anna@example.de"], "Projekte", now=later))
        self.assertIsNone(mailregeln.learn(self.uid, self.acct, ["anna@example.de"], "Projekte", now=later + 1))
        self.assertIsNotNone(mailregeln.learn(self.uid, self.acct, ["anna@example.de"], "Projekte", now=later + 2))

    def test_never_needs_an_own_mailbox(self):
        r = self.c.post("/api/profile/mail/rules/never", json={"account": "m00000000", "from": "anna@example.de", "folder": "Projekte"})
        self.assertEqual(r.status_code, 400)


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(unittest.TestCase):
    """The page: the trash symbol and the Delete key, „Rückgängig“, „Endgültig löschen“ after the question, dragging a
    mail onto a folder of the folder box (it opens while dragging), and the rule hint with „Nur Regel“."""

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True, mail_delete=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        FMB.after_login = ("IMAP4REV1", "MOVE")
        helpers.set_config(mail=False, mail_manage=False, mail_delete=False)

    def open_page(self, b, pg, n):
        return pg.evaluate("MAIL_ON=true;ORD_ON=true;DEL_ON=true;POST.box=null;POST.tree=null;POST.pick=[];POST.done=null;POST.hint=null;"
                           "POST.fopen=false;const v=$('postview');if(v)v.remove();"
                           "postStart({profile:PROFILE,mail:true});icTabSet('post','show');goSec('post');postOpen()")

    async def login(self, pg):
        uid = await pg.evaluate("PROFILE.id")
        if not mail.get(uid)["accounts"]:
            r = await pg.request.post(f"http://127.0.0.1:{self.port}/api/profile/mail",
                                      data={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
            self.assertEqual(r.status, 200, await r.text())
        mail._cache.clear()
        mailregeln.forget(uid)
        return uid

    def test_delete_undo_and_for_good(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        fill()

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1280, 900)
                try:
                    await self.login(pg)
                    await self.open_page(b, pg, 2)
                    await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.items.length===2")
                    await pg.click("#postview .ld-list [data-id]")
                    await b.until(pg, "!!document.querySelector('#postview .postbar [data-o=delete]')")
                    self.assertEqual(await pg.get_attribute("#postview .postbar [data-o=delete]", "data-tip"), "Löschen (in den Papierkorb) · Entf")
                    await pg.click("#postview .postbar [data-o=delete]")
                    await b.until(pg, "POST.data.items.length===1&&!!document.querySelector('#postview .postundo [data-u]')")
                    self.assertIn("Papierkorb", await pg.inner_text("#postview .postundo"))
                    self.assertEqual(len(FMB.boxes["Deleted Messages"]), 1)
                    await pg.click("#postview .postundo [data-u]")
                    await b.until(pg, "!POST.busy&&POST.data.items.length===2")
                    self.assertEqual(FMB.boxes["Deleted Messages"], [])
                    # the Delete key on the open mail
                    await pg.click("#postview .ld-list [data-id]")
                    await b.until(pg, "!!POST.msg&&!!document.querySelector('#postview .posttext')")
                    await pg.evaluate("document.activeElement&&document.activeElement.blur()")
                    await pg.keyboard.press("Delete")
                    await b.until(pg, "POST.data.items.length===1")
                    # in the trash: „Endgültig löschen“ asks first; „Abbrechen“ keeps it
                    await pg.evaluate("POST.fopen=true;postDraw()")
                    await b.until(pg, "!!document.querySelector('#postview .postfold [data-role=trash]')")
                    await pg.click("#postview .postfold [data-role=trash]")
                    await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.folder==='Deleted Messages'&&POST.data.items.length===1")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .postfold [data-role=trash] b')[0].textContent"), "Papierkorb")
                    await pg.click("#postview .ld-list [data-id]")
                    await b.until(pg, "!!document.querySelector('#postview .postbar [data-o=erase]')")
                    self.assertFalse(await pg.evaluate("!!document.querySelector('#postview .postbar [data-o=delete]')"))
                    pg.once("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
                    await pg.click("#postview .postbar [data-o=erase]")
                    await pg.wait_for_timeout(300)
                    self.assertEqual(len(FMB.boxes["Deleted Messages"]), 1)
                    pg.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
                    await pg.click("#postview .postbar [data-o=erase]")
                    await b.until(pg, "POST.data.items.length===0")
                    self.assertEqual(FMB.boxes["Deleted Messages"], [])
                    self.assertIn("Endgültig gelöscht", await pg.inner_text("#postview .postundo"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_drag_onto_a_folder_and_the_rule_hint(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        fill()
        for i in range(3):
            FMB.put("INBOX", helpers.box_mail("Bob <bob@example.de>", f"Plan {i}", "Hier."))

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1280, 900)
                try:
                    uid = await self.login(pg)
                    await self.open_page(b, pg, 5)
                    await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.items.length===5")
                    await pg.evaluate("postFoldersFor(POST.data.items[0].id.split(':')[0])")
                    # the mailboxes are open by default (Apple-Stil „1a“); hidden by the person they come back while dragging
                    await pg.evaluate("postFolds(false)")
                    self.assertTrue(await pg.evaluate("$('postview').querySelector('.postfold').hidden"))
                    for n in range(3):
                        row = pg.locator("#postview .ld-list [data-id]", has_text="Bob").first
                        await row.hover()
                        await pg.mouse.down()
                        await pg.mouse.move(600, 400, steps=4)
                        # the folders come while dragging, though they were hidden
                        await b.until(pg, "!!document.querySelector('#postview .postfold [data-f=Projekte]')")
                        box = await pg.locator("#postview .postfold [data-f=Projekte]").bounding_box()
                        await pg.mouse.move(box["x"] + 20, box["y"] + box["height"] / 2, steps=6)
                        await pg.mouse.up()
                        await b.until(pg, f"POST.data.items.length==={4 - n}")
                    self.assertEqual(len(FMB.boxes["Projekte"]), 3)
                    await b.until(pg, "!!document.querySelector('#postview .posthint [data-h=save]')")
                    self.assertIn("bob@example.de", await pg.inner_text("#postview .posthint"))
                    await pg.click("#postview .posthint [data-h=save]")
                    await b.until(pg, "!document.querySelector('#postview .posthint')&&POST.note.includes('Regel angelegt')")
                    rules = mailregeln.load(uid)["rules"]
                    self.assertEqual([(r["when"]["from"], r["then"]["folder"]) for r in rules], [("bob@example.de", "Projekte")])
                    await b.until(pg, "document.querySelector('#postview .postfold').hidden")   # closed again after the drag
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
