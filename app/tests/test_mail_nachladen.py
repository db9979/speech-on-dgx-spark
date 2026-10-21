"""Ältere E-Mails nachladen (Dominik 2026-10-21 „1a 2a 5a 6a“, part of E-Mail lesen, no switch of its own; mail.more):

- The page asks with the mark „vor“ of its last page for the next PAGE older messages, in the inbox and in every
  folder, without a limit of days, down to the first mail of the mailbox; then the mark is empty (the end).
- A search goes over the whole mailbox on the server (sender, subject and text, also beyond ASCII), page by page.
- Nothing of it goes into the Mail-Vorrat or onto the disk; the pages live in memory and go when the page changes a
  message.
- A mark names only the profile's own mailboxes (else 400); a folder's mark only its own mailbox; own rate limit.
- A mailbox that does not answer is named and tried again with the next page; no row is skipped when date and UID
  disagree.
- spark-tui mails --anzahl N follows the marks.

The fake mailbox (helpers.FakeMailbox); dates relative to now, no wall clock in the assertions.
"""
import asyncio
import datetime
import email.utils
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import mail  # noqa: E402
import mailvorrat  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_mailclient_c import profile  # noqa: E402
from tests.test_terminal import program  # noqa: E402

FMB = helpers.FakeMailbox
NOW = datetime.datetime.now(datetime.timezone.utc)
ALL = 130


def raw(i, hours, subject=None, frm=None, text="Hallo"):
    when = email.utils.format_datetime(NOW - datetime.timedelta(hours=hours))
    return (f"From: {frm or f'Anna <anna{i}@example.de>'}\r\nTo: {helpers.MAIL_USER}\r\nSubject: {subject or f'Brief {i}'}\r\n"
            f"Message-ID: <n{i}@x>\r\nDate: {when}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{text}\r\n").encode()


def fill():
    # uid 100 is the oldest (64 days), uid 229 the newest; every twelve hours one
    FMB.reset(inbox=[raw(i, (ALL - 1 - i) * 12) for i in range(ALL)])
    FMB.put("INBOX", raw(900, 61 * 24, "Steuerbescheid 2024", "Finanzamt <post@finanzamt.de>"))
    FMB.put("INBOX", raw(901, 50 * 24, "Auszug", "Bank <bank@x.de>", "Ihr Kontoauszug liegt bereit"))
    FMB.put("INBOX", raw(902, 40 * 24, "Grüße von Müller", "Müller <m@x.de>"))
    FMB.boxes["Archive"] = []
    for i in range(70):
        FMB.put("Archive", raw(500 + i, 24 * (100 - i)))
    FMB.boxes["Klein"] = []
    FMB.put("Klein", raw(800, 5))


class Base(unittest.TestCase):
    NAME = "Nachladen Nina"

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        FMB.since = True
        helpers.set_config(mail=True, mail_manage=True)
        cls.c, cls.uid = profile(cls.NAME)
        fill()
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        FMB.since = False
        helpers.set_config(mail=False, mail_manage=False)

    def setUp(self):
        fill()
        mail.IMAP = FMB
        for d in (mail._cache, mail._bodies, mail._pages):
            d.clear()
        for k in [k for k in guard._rate if k[0] in ("post", "postmehr", "postordnen")]:
            guard._rate.pop(k, None)

    def get(self, path="/api/profile/mail/inbox", **params):
        r = self.c.get(path, params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def walk(self, first, path="/api/profile/mail/inbox", **params):
        """All rows from the first page on, following the marks; (rows, pages)."""
        rows, page, n = list(first["items"]), first, 1
        while page["vor"]:
            page = self.get(path, vor=page["vor"], **params)
            rows += page["items"]
            n += 1
            self.assertLess(n, 20)
        return rows, n


class Pages(Base):
    def test_down_to_the_first_mail(self):
        first = self.get()
        self.assertLessEqual(len(first["items"]), mail.INBOX_MAX)
        self.assertTrue(first["vor"].startswith(self.acct + ":"))
        rows, n = self.walk(first)
        ids = [x["id"] for x in rows]
        self.assertEqual(len(set(ids)), ALL + 3)                                    # every mail, the 64 days old too
        self.assertIn(f"{self.acct}:100", ids)
        self.assertGreaterEqual(n, 3)
        dates = [x["date"] for x in rows if x["subject"].startswith("Brief")]
        self.assertEqual(dates, sorted(dates, reverse=True))                       # newest first, page after page
        # the three from before the period with the newest UIDs (moved back, far-off clock) come with the next page
        late = [x["subject"] for x in rows[len(first["items"]):len(first["items"]) + mail.PAGE]]
        self.assertTrue({"Steuerbescheid 2024", "Auszug", "Grüße von Müller"} <= set(late))

    def test_not_kept_in_the_supply(self):
        self.walk(self.get())
        kept = mailvorrat._load(self.uid)["heads"].get(self.acct, {})
        self.assertNotIn("100", kept)                                              # the supply stays at DAYS
        cut = NOW.timestamp() - mailvorrat.DAYS * 86400
        self.assertTrue(all(h["date"] >= cut for h in kept.values()))

    def test_pages_go_when_a_message_changes(self):
        first = self.get()
        self.get(vor=first["vor"])
        self.assertTrue(any(k[0] == self.uid for k in mail._pages))
        mail.changed(self.uid, f"{self.acct}:150", "read")
        self.assertFalse(any(k[0] == self.uid for k in mail._pages))


class Search(Base):
    NAME = "Nachladen Suse"

    def found(self, q):
        rows, _ = self.walk(self.get(q=q), q=q)
        return sorted(x["subject"] for x in rows)

    def test_whole_mailbox_by_the_server(self):
        self.assertEqual(self.found("steuerbescheid"), ["Steuerbescheid 2024"])   # 61 days old
        self.assertEqual(self.found("von:finanzamt"), ["Steuerbescheid 2024"])
        self.assertEqual(self.found("kontoauszug"), ["Auszug"])                    # only in the text
        self.assertEqual(self.found("müller"), ["Grüße von Müller"])               # beyond ASCII (CHARSET UTF-8)
        self.assertEqual(self.found("betreff:grüße"), ["Grüße von Müller"])

    def test_criteria(self):
        crit, lit, after = mail._criteria(["from:anna", "subject:rechnung", "hat:anhang", "ist:markiert", "brief"], True)
        self.assertEqual(crit, ["UNSEEN", "FROM", '"anna"', "SUBJECT", '"rechnung"', "FLAGGED", "TEXT", '"brief"'])
        self.assertEqual((lit, after), (None, ["hat:anhang"]))
        crit, lit, after = mail._criteria(["müller", "from:jürgen"], False)
        self.assertEqual(lit, ("TEXT", "müller"))
        self.assertEqual((crit, after), (["FROM", '"rgen"'], ["from:jürgen"]))   # the header decides


class Folders(Base):
    NAME = "Nachladen Olga"

    def test_folder_pages(self):
        first = self.get("/api/profile/mail/folder", account=self.acct, folder="Archive")
        self.assertEqual(len(first["items"]), 50)
        rows, _ = self.walk(first, "/api/profile/mail/folder", account=self.acct, folder="Archive")
        self.assertEqual(len({x["id"] for x in rows}), 70)

    def test_a_small_folder_has_no_mark(self):
        self.assertEqual(self.get("/api/profile/mail/folder", account=self.acct, folder="Klein")["vor"], "")


class Guard(Base):
    NAME = "Nachladen Paul"

    def test_only_own_mailboxes(self):
        for bad in ("m12345678:150", "x", f"{self.acct}:abc", f"{self.acct}:1.{self.acct}:2.m00000000:3.m11111111:4.m22222222:5"):
            r = self.c.get("/api/profile/mail/inbox", params={"vor": bad})
            self.assertEqual(r.status_code, 400, bad)
        r = self.c.get("/api/profile/mail/folder", params={"account": "m99999999", "folder": "Archive", "vor": f"{self.acct}:600"})
        self.assertEqual(r.status_code, 400)
        other = TestClient(panel.app)
        self.assertIn(other.get("/api/profile/mail/inbox", params={"vor": f"{self.acct}:150"}).status_code, (401, 403))

    def test_own_rate_limit(self):
        first = self.get()
        codes = [self.c.get("/api/profile/mail/inbox", params={"vor": first["vor"]}).status_code for _ in range(32)]
        self.assertEqual(codes[0], 200)
        self.assertEqual(codes[-1], 429)


class Merge(unittest.TestCase):
    """mail.more with fake mailboxes (_older): marks per mailbox, a mailbox down, date and UID out of step."""
    A1 = {"id": "m00000001", "name": "Privat"}
    A2 = {"id": "m00000002", "name": "Arbeit"}

    def setUp(self):
        self.saved = (mail._older, mail.get, mail.PAGE)
        mail.get = lambda uid: {"accounts": [self.A1, self.A2]}
        mail.PAGE = 3
        mail._pages.clear()
        self.down = set()
        self.boxes = {"m00000001": {9: 9, 8: 3, 7: 7, 6: 6}, "m00000002": {5: 8, 4: 5}}   # uid -> hours ago

        def fake(acct, folder, words, unread, below, days, want):
            if acct["id"] in self.down:
                raise OSError("timed out")
            got = [(acct["id"], u, {"from": "a", "subject": "s", "date": NOW - datetime.timedelta(hours=h), "unread": False})
                   for u, h in sorted(self.boxes[acct["id"]].items(), reverse=True) if below is None or u < below]
            return got[:want], 0, (got[want - 1][1] if len(got) > want else 0)
        mail._older = fake

    def tearDown(self):
        mail._older, mail.get, mail.PAGE = self.saved
        mail._pages.clear()

    def test_marks_and_a_mailbox_down(self):
        self.down.add("m00000002")
        p = mail.more("u1", "m00000001:.m00000002:")
        self.assertEqual(p["errors"], ["Arbeit"])
        self.assertIn("m00000002:", p["vor"].split("."))                           # tried again next time
        self.assertEqual([x["id"] for x in p["items"]], ["m00000001:8", "m00000001:7", "m00000001:9"])

    def test_nothing_is_skipped(self):
        seen, mark = [], "m00000001:.m00000002:"
        for _ in range(10):
            p = mail.more("u2", mark)
            seen += [x["id"] for x in p["items"] if x["id"] not in seen]
            mark = p["vor"]
            if not mark:
                break
        self.assertEqual(sorted(seen), sorted(f"{a}:{u}" for a, b in self.boxes.items() for u in b))


class Page(unittest.TestCase):
    """The page E-Mail at 1280 and 390 px: at the end of the list the older mails come by themselves, page by page,
    down to „Keine älteren Mails“; no row twice, nothing sideways."""
    ACCT = {"id": "m0b1c2d3e", "name": "Privat", "host": "imap.example.de", "port": 993, "user": helpers.MAIL_USER,
            "password": helpers.MAIL_PW}

    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)
        cls.saved = (mail.get, mail.IMAP)
        mail.get = lambda uid: {"accounts": [cls.ACCT]}
        mail.IMAP = FMB
        FMB.since = True
        helpers.set_config(mail=True)

    @classmethod
    def tearDownClass(cls):
        mail.get, mail.IMAP = cls.saved
        FMB.since = False
        helpers.set_config(mail=False)

    def test_scrolling_loads_the_older_ones(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for width in (1280, 390):
                    fill()
                    for d in (mail._cache, mail._bodies, mail._pages):
                        d.clear()
                    for k in [k for k in guard._rate if k[0] in ("post", "postmehr")]:
                        guard._rate.pop(k, None)
                    br, pg, errors = await b.page(p, width, 900)
                    try:
                        await pg.evaluate("MAIL_ON=true;postStart({profile:PROFILE,mail:true});icTabSet('post','show');goSec('post')")
                        await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.items.length>0&&!!document.querySelector('#postview [data-k=more]')")
                        first = await pg.evaluate("POST.data.items.length")
                        for _ in range(12):
                            await pg.evaluate("document.querySelector('#postview [data-more]').scrollIntoView({block:'end'})")
                            await pg.wait_for_timeout(250)
                            if await pg.evaluate("!POST.data.vor&&!POST.more"):
                                break
                        await b.until(pg, "!POST.data.vor&&!POST.more")
                        ids = await pg.evaluate("[...document.querySelectorAll('#postview .ld-row')].map(r=>r.dataset.id)")
                        self.assertGreater(len(ids), first)
                        self.assertEqual(len(ids), len(set(ids)))
                        self.assertEqual(len(ids), ALL + 3)
                        self.assertIn("Keine älteren Mails", await pg.inner_text("#postview [data-more]"))
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{width} px scrolls sideways")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


class Terminal(unittest.TestCase):
    def test_spark_tui_follows_the_marks(self):
        tui = program()
        pages = {"": {"items": [{"id": "a:3"}, {"id": "a:2"}], "vor": "a:2"}, "a:2": {"items": [{"id": "a:1"}], "vor": ""}}

        class Sp:
            def call(s, method, path):
                return pages["a:2" if "vor=" in path else ""]
        self.assertEqual([x["id"] for x in tui.mail_items(Sp(), 10)], ["a:3", "a:2", "a:1"])
        self.assertEqual(len(tui.mail_items(Sp(), 1)), 1)


if __name__ == "__main__":
    unittest.main()
