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
import time
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok

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


class Base(unittest.TestCase):
    NAME = "Ordnen Olga"

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, mail_manage=True)
        cls.c, cls.uid = profile(cls.NAME)
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


class Act(Base):
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


class Folders(Base):
    """Mailclient Stufe A (Dominik 2026-10-19 „1a 4a“): every folder read like the inbox, own folders made, renamed
    and (empty) removed, Markieren and Mehrfachauswahl. Never a message deleted, never a folder of the mail program
    or of Mails aufräumen renamed or removed."""
    NAME = "Ordner Ole"

    def setUp(self):
        super().setUp()
        FMB.put("Projekte", helpers.box_mail("Bob <bob@example.de>", "Plan", "Hier der Plan.", mid="<ord-3@x>"))
        postfach._trees.clear()

    def tree(self):
        r = self.c.get("/api/profile/mail/tree", params={"fresh": "true"})
        self.assertEqual(r.status_code, 200, r.text)
        return {f["name"]: f for f in r.json()["accounts"][0]["folders"]}

    def test_tree_roles_counts_and_what_may_change(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            t = self.tree()
        self.assertEqual(list(t)[0], "INBOX")
        self.assertEqual({n: f["role"] for n, f in t.items()},
                         {"INBOX": "inbox", "Drafts": "drafts", "Sent Messages": "sent", "Archive": "archive",
                          "Projekte": "folder", "Junk": "junk", "Deleted Messages": "trash"})
        self.assertEqual((t["INBOX"]["unseen"], t["Projekte"]["unseen"]), (2, 1))
        self.assertEqual([n for n, f in t.items() if f["own"]], ["Projekte"])
        self.assertIn("mail: tree shown | 7 |", out.getvalue())
        self.assertNotIn("Projekte", out.getvalue())      # never a folder name in the log

    def test_a_folder_is_read_like_the_inbox(self):
        r = self.c.get("/api/profile/mail/folder", params={"account": self.acct, "folder": "Projekte"})
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json()["items"]
        self.assertEqual([x["subject"] for x in items], ["Plan"])
        self.assertTrue(items[0]["unread"])
        m = self.c.get("/api/profile/mail/message", params={"id": items[0]["id"], "folder": "Projekte"})
        self.assertEqual(m.status_code, 200, m.text)
        self.assertIn("Hier der Plan", m.json()["text"])
        self.assertFalse(FMB.boxes["Projekte"][0]["seen"])   # reading keeps it unread (EXAMINE, PEEK)
        self.assertEqual(self.c.get("/api/profile/mail/folder", params={"account": self.acct, "folder": "Gibt es nicht"}).status_code, 404)
        self.assertEqual(self.c.get("/api/profile/mail/message", params={"id": items[0]["id"], "folder": "Pro\r\njekte"}).status_code, 400)

    def test_flag_and_move_out_of_a_folder(self):
        u = FMB.boxes["Projekte"][0]["uid"]
        r = self.c.post("/api/profile/mail/act", json={"id": f"{self.acct}:{u}", "action": "flag", "src": "Projekte"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("\\Flagged", FMB.boxes["Projekte"][0]["flags"])
        items = self.c.get("/api/profile/mail/folder", params={"account": self.acct, "folder": "Projekte"}).json()["items"]
        self.assertTrue(items[0]["flagged"])
        r = self.c.post("/api/profile/mail/act", json={"id": f"{self.acct}:{u}", "action": "move", "folder": "INBOX", "src": "Projekte"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((len(FMB.boxes["INBOX"]), FMB.boxes["Projekte"]), (3, []))
        # never moved out of sent, drafts, trash or junk
        FMB.put("Deleted Messages", helpers.box_mail("X <x@example.de>", "Alt", "alt", mid="<ord-4@x>"))
        u = FMB.boxes["Deleted Messages"][0]["uid"]
        r = self.c.post("/api/profile/mail/act", json={"id": f"{self.acct}:{u}", "action": "move", "folder": "INBOX", "src": "Deleted Messages"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(FMB.boxes["Deleted Messages"]), 1)

    def test_a_move_keeps_the_tree_and_reads_it_behind(self):
        """Dominik 2026-10-21 „reloaded immer die gesamte Ordnerliste“: after a move the tree is not thrown away (it comes
        at once, never waiting for the mailbox) and is read anew behind, so the next ask has the new numbers."""
        t = self.tree()
        self.assertEqual((t["INBOX"]["unseen"], t["Projekte"]["unseen"]), (2, 1))
        u = next(m["uid"] for m in FMB.boxes["INBOX"] if not m["seen"])
        r = self.c.post("/api/profile/mail/act", json={"id": f"{self.acct}:{u}", "action": "move", "folder": "Projekte"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(self.uid, postfach._trees)                                   # kept, not dropped
        for _ in range(50):
            if self.uid not in postfach._tree_busy:
                break
            time.sleep(0.1)
        got = self.c.get("/api/profile/mail/tree").json()
        f = {x["name"]: x for x in got["accounts"][0]["folders"]}
        self.assertEqual((f["INBOX"]["unseen"], f["Projekte"]["unseen"]), (1, 2))
        self.assertNotIn("neu", got)

    def test_many_at_once_and_back(self):
        ids = [f"{self.acct}:{m['uid']}" for m in FMB.boxes["INBOX"]]
        r = self.c.post("/api/profile/mail/acts", json={"ids": ids, "action": "read"})
        self.assertEqual((r.status_code, r.json()["n"]), (200, 2), r.text)
        self.assertEqual([m["seen"] for m in FMB.boxes["INBOX"]], [True, True])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.c.post("/api/profile/mail/acts", json={"ids": ids, "action": "move", "folder": "Projekte"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((FMB.boxes["INBOX"], len(FMB.boxes["Projekte"])), ([], 3))
        self.assertIn("mail: page many move done | 2 |", out.getvalue())
        r = self.c.post("/api/profile/mail/acts/back", json={"account": self.acct, "folder": "Projekte", "mids": d["moved"][0]["mids"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((len(FMB.boxes["INBOX"]), len(FMB.boxes["Projekte"])), (2, 1))
        self.assertEqual(self.c.post("/api/profile/mail/acts", json={"ids": ["x"] * 51, "action": "read"}).status_code, 400)
        self.assertEqual(self.c.post("/api/profile/mail/acts", json={"ids": ids, "action": "delete"}).status_code, 400)

    def test_own_folders_made_renamed_removed(self):
        new = lambda **b: self.c.post("/api/profile/mail/folder/new", json=dict(account=self.acct, **b))
        self.assertEqual(new(name="Auto").status_code, 200)
        r = new(folder="Auto", name="Werkstatt")
        self.assertEqual((r.status_code, r.json()["folder"]), (200, "Auto/Werkstatt"), r.text)
        self.assertIn("Auto/Werkstatt", FMB.boxes)
        for bad in ("", "Papierkorb", "Spam", "Archive", "INBOX", "Auto"):
            self.assertEqual(new(name=bad).status_code, 400, bad)
        self.assertEqual(new(folder="Deleted Messages", name="X").status_code, 400)   # nothing inside the trash
        r = self.c.post("/api/profile/mail/folder/rename", json={"account": self.acct, "folder": "Auto/Werkstatt", "name": "Garage"})
        self.assertEqual((r.status_code, r.json()["folder"]), (200, "Auto/Garage"), r.text)
        rm = lambda f: self.c.post("/api/profile/mail/folder/remove", json={"account": self.acct, "folder": f})
        self.assertEqual(rm("Auto").status_code, 400)          # holds a folder
        self.assertEqual(rm("Projekte").status_code, 400)      # holds a message: never deleted
        self.assertEqual(len(FMB.boxes["Projekte"]), 1)
        self.assertEqual(rm("Auto/Garage").status_code, 200)
        self.assertNotIn("Auto/Garage", FMB.boxes)
        for special in ("INBOX", "Sent Messages", "Drafts", "Archive", "Deleted Messages", "Junk"):
            self.assertEqual(rm(special).status_code, 400, special)
            self.assertIn(special, FMB.boxes)
            r = self.c.post("/api/profile/mail/folder/rename", json={"account": self.acct, "folder": special, "name": "Neu"})
            self.assertEqual(r.status_code, 400, special)

    def test_folders_of_mails_aufraeumen_stay(self):
        FMB.boxes["Spark"] = []
        FMB.boxes["Spark/Werbung"] = []
        t = self.tree()
        self.assertFalse(t["Spark"]["own"] or t["Spark/Werbung"]["own"])
        r = self.c.post("/api/profile/mail/folder/rename", json={"account": self.acct, "folder": "Spark/Werbung", "name": "Reklame"})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/profile/mail/folder/remove", json={"account": self.acct, "folder": "Spark/Werbung"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Spark/Werbung", FMB.boxes)

    def test_off_guests_and_other_profiles(self):
        other, _ = profile("Ordnen Otto")
        self.assertEqual(other.get("/api/profile/mail/folder", params={"account": self.acct, "folder": "Projekte"}).status_code, 400)
        self.assertEqual(other.post("/api/profile/mail/folder/new", json={"account": self.acct, "name": "X"}).status_code, 400)
        guest = TestClient(panel.app)
        for path in ("/api/profile/mail/tree", "/api/profile/mail/folder"):
            self.assertIn(guest.get(path).status_code, (401, 403))
        for path in ("/api/profile/mail/acts", "/api/profile/mail/folder/new", "/api/profile/mail/folder/remove"):
            self.assertIn(guest.post(path, json={}).status_code, (401, 403))
        helpers.set_config(mail_manage=False)
        try:
            self.assertEqual(self.c.get("/api/profile/mail/tree").status_code, 403)
            self.assertEqual(self.c.post("/api/profile/mail/folder/new", json={"account": self.acct, "name": "X"}).status_code, 403)
            m = self.c.get("/api/profile/mail/message", params={"id": f"{self.acct}:100", "folder": "Projekte"})
            self.assertEqual(m.status_code, 403)
        finally:
            helpers.set_config(mail_manage=True)
        self.assertNotIn("X", FMB.boxes)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
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
                    await b.until(pg, "!!document.querySelector('#postview .postfoot [data-o=archive]')")   # phone: at the thumb
                    await pg.click("#postview .postfoot [data-o=pick]")
                    await b.until(pg, "document.querySelectorAll('#postview .postmv [data-mv]').length>0")
                    await pg.click("#postview .postfoot [data-o=pick]")                                     # closes again
                    await b.until(pg, "!document.querySelector('#postview .postmv')")
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1)
                    await pg.click("#postview .postfoot [data-o=archive]")
                    await b.until(pg, "POST.data.items.length===1&&!!document.querySelector('#postview .postundo [data-u]')")
                    self.assertEqual(len(FMB.boxes["Archive"]), 1)
                    await pg.click("#postview .postundo [data-u]")
                    await b.until(pg, "!POST.busy&&POST.data.items.length===2")
                    self.assertEqual(FMB.boxes["Archive"], [])
                    # without the function no buttons
                    await pg.evaluate("ORD_ON=false;[...document.querySelectorAll('#postview .ld-row')][0].click()")
                    await b.until(pg, "!!POST.msg&&!!document.querySelector('#postview .posttext')")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview [data-o]').length"), 0)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_a_rule_from_a_mail_takes_sender_and_subject(self):
        """Dominik 2026-10-20: „Regel daraus …“ fills in the sender and the mail's subject (without Re:/AW:/Fwd:)."""
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        fill()

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1200, 900)
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
                    await b.until(pg, "!!document.querySelector('#postview [data-w=rule]')")
                    # Dominik 2026-10-20 „1 und 3“: one bar on top that stays, symbols with name and key on hover
                    self.assertEqual(await pg.evaluate("getComputedStyle(document.querySelector('#postview .postbar')).position"), "sticky")
                    self.assertEqual(await pg.evaluate("document.querySelector('#postview .postbar [data-o=archive]').dataset.tip"), "Archivieren · E")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .postfoot').length"), 0)   # thumb bar only on a phone
                    await pg.click("#postview [data-w=rule]")
                    await b.until(pg, "!!RULES.form")
                    self.assertEqual(await pg.evaluate("RULES.form.when"),
                                     {"from": "anna@example.de", "subject": "Werkstatt fertig", "to": "", "attach": False})
                    self.assertEqual(await pg.evaluate("postTopic('AW: Re: Fwd:  Angebot 4711 ')"), "Angebot 4711")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_folders_and_many_from_the_page(self):
        """Mailclient Stufe A: the folder tree left of the list, a smart mailbox, a folder opened, two mails ticked after
        „Auswählen“ and marked read."""
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        fill()
        FMB.put("Projekte", helpers.box_mail("Bob <bob@example.de>", "Plan", "Hier der Plan.", mid="<ord-3@x>"))
        FMB.boxes["INBOX"][1]["seen"] = True   # one read, one unread (the smart mailbox „Ungelesen“)
        postfach._trees.clear()

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1280, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    if not mail.get(uid)["accounts"]:
                        r = await pg.request.post(f"http://127.0.0.1:{self.port}/api/profile/mail",
                                                  data={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
                        self.assertEqual(r.status, 200, await r.text())
                    mail._cache.clear()
                    await pg.evaluate("MAIL_ON=true;ORD_ON=true;POST.box=null;POST.tree=null;POST.pick=[];const v=$('postview');if(v)v.remove();"
                                      "postStart({profile:PROFILE,mail:true});icTabSet('post','show');goSec('post');postOpen()")
                    await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.items.length===2")
                    # the mailboxes and folders stand left of the list like Apple Mail (Apple-Stil „1a“), the list stays
                    await pg.evaluate("POST.fopen=false;postDraw()")
                    await pg.click("#postview [data-k=tree]")
                    await b.until(pg, "!!document.querySelector('#postview .postfold [data-f=Projekte]')")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .ld-list [data-id]').length"), 2)
                    self.assertLess(await pg.evaluate("document.querySelector('#postview .postfold').getBoundingClientRect().right"),
                                    await pg.evaluate("document.querySelector('#postview .ld-list').getBoundingClientRect().left"))
                    # a smart mailbox: „Ungelesen“ lists only the unread one, a second tap shows all again
                    await pg.click("#postview .postfold [data-smart=unread]")
                    await b.until(pg, "!POST.busy&&POST.unread&&!!POST.data&&POST.data.items.length===1")
                    self.assertIn("Ungelesen", await pg.inner_text("#postview .ld-list .posthead"))
                    await pg.click("#postview .postfold [data-smart=unread]")
                    await b.until(pg, "!POST.busy&&!POST.unread&&!!POST.data&&POST.data.items.length===2")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .postfold [data-fa]').length"), 1)
                    # ⋯ at an own folder (Dominik 2026-10-21 „besser integriert“): a small menu beside it, nothing below moves,
                    # Esc closes; a right click opens it too
                    tops = "[...document.querySelectorAll('#postview .postfold .ld-row')].map(r=>Math.round(r.getBoundingClientRect().top))"
                    before = await pg.evaluate(tops)
                    await pg.click("#postview .postfold [data-fa]")
                    await b.until(pg, "!!document.querySelector('#postview .postfmenu [data-fo=rename]')")
                    self.assertEqual(await pg.evaluate(tops), before)
                    self.assertEqual(await pg.evaluate("getComputedStyle(document.querySelector('#postview .postfmenu')).position"), "fixed")
                    self.assertTrue(await pg.evaluate("(r=>r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight)(document.querySelector('#postview .postfmenu').getBoundingClientRect())"))
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .postfmenu [data-fo]').length"), 3)
                    await pg.keyboard.press("Escape")
                    await b.until(pg, "!document.querySelector('#postview .postfmenu')")
                    await pg.click("#postview .postfold [data-f=Projekte]", button="right")
                    await b.until(pg, "!!document.querySelector('#postview .postfmenu')")
                    await pg.mouse.click(5, 5)
                    await b.until(pg, "!document.querySelector('#postview .postfmenu')")
                    await pg.click("#postview .postfold [data-f=Projekte]")
                    await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.folder==='Projekte'&&POST.data.items.length===1")
                    self.assertIn("Projekte", await pg.inner_text("#postview .ld-list .posthead"))
                    await pg.click("#postview .postfold [data-all]")
                    await b.until(pg, "!POST.busy&&!!POST.data&&!POST.data.folder&&POST.data.items.length===2")
                    # ticks only after „Auswählen“ (Apple-Stil „1a“), the rows stay calm otherwise
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .ld-list [data-pick]').length"), 0)
                    await pg.click("#postview [data-k=pickmode]")
                    await b.until(pg, "document.querySelectorAll('#postview .ld-list [data-pick]').length===2")
                    for i in range(2):
                        await pg.locator("#postview .ld-list [data-pick]").nth(i).check()
                        await b.until(pg, f"POST.pick.length==={i + 1}")
                    await b.until(pg, "!!document.querySelector('#postview .postpick [data-m=read]')")
                    await pg.click("#postview .postpick [data-m=read]")
                    await b.until(pg, "POST.pick.length===0&&POST.data.items.every(x=>!x.unread)")
                    self.assertEqual([m["seen"] for m in FMB.boxes["INBOX"]], [True, True])
                    self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth"), 1)
                    # Umbenennen and Neuer Ordner darin right in the row, Enter keeps it (no window)
                    await pg.click("#postview .postfold [data-fa]")
                    await pg.click("#postview .postfmenu [data-fo=rename]")
                    await b.until(pg, "!!document.querySelector('#postview .postfold [data-fin=rename]')")
                    await pg.fill("#postview .postfold [data-fin=rename]", "Projekte2")
                    await pg.press("#postview .postfold [data-fin=rename]", "Enter")
                    await b.until(pg, "!!document.querySelector('#postview .postfold [data-f=Projekte2]')")
                    self.assertIn("Projekte2", FMB.boxes)
                    await pg.click("#postview .postfold [data-fa]")
                    await pg.click("#postview .postfmenu [data-fo=new]")
                    await b.until(pg, "!!document.querySelector('#postview .postfold [data-fin=new]')")
                    await pg.fill("#postview .postfold [data-fin=new]", "Unter")
                    await pg.press("#postview .postfold [data-fin=new]", "Enter")
                    await b.until(pg, "!!document.querySelector('#postview .postfold [data-f=\"Projekte2/Unter\"]')")
                    self.assertIn("Projekte2/Unter", FMB.boxes)
                    # Dominik 2026-10-21 „reloaded immer die gesamte Ordnerliste“: a move takes the mail off at once, the
                    # folders stay (never „Lade die Ordner“), only their numbers change; when the Spark says no it comes back
                    await pg.evaluate("postAct('unread','',null,'',POST.data.items[0].id)")
                    await b.until(pg, "POST.data.items[0].unread")
                    await pg.evaluate("postTreeLoad(true)")
                    unseen = "(n=>(POST.tree.accounts[0].folders.find(f=>f.name===n)||{}).unseen||0)"
                    await b.until(pg, f"!POST.treeBusy&&!!POST.tree.accounts&&{unseen}('INBOX')===1")
                    await pg.evaluate("window._lade=0;new MutationObserver(()=>{if(document.querySelector('#postview .postfold').textContent.includes('Lade die Ordner'))window._lade++})"
                                      ".observe(document.querySelector('#postview .postfold'),{childList:true,subtree:true,characterData:true});"
                                      "window._td=0;const o=postTreeLoad;postTreeLoad=(...a)=>o(...a).then(()=>{window._td++})")
                    before = await pg.evaluate(f"{unseen}('Projekte2')")
                    mid = await pg.evaluate("POST.data.items[0].id")
                    self.assertEqual(await pg.evaluate(f"window._p=postAct('move','Projekte2',null,'','{mid}');POST.data.items.length"), 1)   # at once
                    await pg.evaluate("window._p")
                    self.assertEqual((await pg.evaluate(f"{unseen}('INBOX')"), await pg.evaluate(f"{unseen}('Projekte2')")), (0, before + 1))
                    self.assertEqual(len(FMB.boxes["Projekte2"]), 2)
                    await b.until(pg, "window._td>=1&&!POST.treeBusy")                                # asked again quietly behind
                    self.assertEqual((await pg.evaluate(f"{unseen}('INBOX')"), await pg.evaluate(f"{unseen}('Projekte2')")), (0, before + 1))
                    self.assertEqual(await pg.evaluate("window._lade"), 0)
                    await pg.route("**/api/profile/mail/act", lambda r: r.fulfill(status=409, content_type="application/json", body='{"detail":"nein"}'))
                    left = await pg.evaluate("POST.data.items[0].id")
                    self.assertEqual(await pg.evaluate(f"window._p=postAct('archive','',null,'','{left}');POST.data.items.length"), 0)
                    await pg.evaluate("window._p")
                    self.assertEqual(await pg.evaluate("POST.data.items.map(i=>i.id)"), [left])           # back again
                    self.assertTrue(await pg.evaluate("!!POST.err"))
                    await pg.unroute("**/api/profile/mail/act")
                    await pg.evaluate("POST.err='';postDraw()")
                    # O hides the folders again and the choice is kept for the next visit
                    await pg.evaluate("document.activeElement&&document.activeElement.blur()")
                    await pg.keyboard.press("o")
                    await b.until(pg, "!POST.fopen&&document.querySelector('#postview .postfold').hidden")
                    self.assertEqual(await pg.evaluate("localStorage.getItem('spark.postFolds')"), "0")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
