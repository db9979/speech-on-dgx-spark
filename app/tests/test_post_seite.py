"""The page E-Mail (Dominik 2026-10-18, plan kalender-mail/plan.md 2a 4a): the profile's mailboxes as a page of its own
in the menu, everything set up for mail (mailboxes, Aufräumen, Mailstil, Pakete) in its tab „Einstellungen“, no longer
pages of Ich.

- GET /api/profile/mail/inbox lists only the own mailboxes' newest messages (sender, subject, time, unread), at most
  mail.INBOX_MAX; GET /api/profile/mail/message gives one as plain text and only of an own mailbox; guests and a
  profile without the function get nothing.
- The page lists, opens and reads at 320, 390 and 1280 px without sideways scrolling; text from a mail is text, never
  markup, an HTML mail only as the Spark cleaned it in a frame where nothing runs (mailansicht.py, test_mailansicht); „Einstellungen“ holds #mailbox and #parbox; Ich lists neither; #me=mailbox (the apps) opens the page.
- The Von-selbst rows for mail sit under E-Mail → Einstellungen, Termin-Vorlauf under Kalender → Einstellungen, not
  under Ich → Von selbst.

Fixed dates, a fake mailbox; no wall clock, no network.
"""
import asyncio
import email
import email.policy
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import mail  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ACCT = {"id": "m0a1b2c3d", "name": "Privat", "host": "imap.example.de", "port": 993, "user": "ich", "password": "pw"}
RAW = {7: ("From: Anna Alt <anna@example.de>\r\nTo: ich@example.de\r\nSubject: Werkstatt <b>Auto</b>\r\n"
           "Date: Tue, 10 Mar 2026 09:30:00 +0100\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
           "<p>Hallo, der Wagen ist <b>fertig</b>.</p><img src=\"https://tracker.example/x.gif\">"
           "<a href=\"https://werkstatt.example/r\">www.bank.example</a>\r\n"),
       8: ("From: shop@example.de\r\nTo: ich@example.de\r\nSubject: Rechnung\r\n"
           "Date: Mon, 09 Mar 2026 18:00:00 +0100\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nDanke\r\n")}
OWNERS = {}   # uid -> [account]: the fake profiles' mailboxes


class Box:
    """Answers like an IMAP session of one account: two messages, one of them read."""
    def __init__(self, acct):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def search(self, *crit):
        words = [crit[i + 1].strip('"').lower() for i, x in enumerate(crit) if x == "TEXT"]
        return [u for u, raw in RAW.items() if all(w in raw.lower() for w in words)]

    def headers(self, uids):
        out = {}
        for u in uids:
            m = email.message_from_string(RAW[u], policy=email.policy.default)
            out[u] = {"from": mail._addr(m["From"]), "subject": mail._hdr(m["Subject"]), "date": mail._date(m["Date"]), "unread": u == 7}
        return out

    def body(self, uid, most=0):
        return email.message_from_string(RAW[uid], policy=email.policy.default) if uid in RAW else None


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Fake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (mail._Session, mail.get)
        mail._Session = Box
        real = mail.get
        mail.get = lambda uid: {"accounts": OWNERS[uid]} if uid in OWNERS else real(uid)
        mail._cache.clear()
        helpers.set_config(mail=True)

    @classmethod
    def tearDownClass(cls):
        mail._Session, mail.get = cls.saved
        mail._cache.clear()
        helpers.set_config(mail=False)


class Api(Fake):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c, cls.uid = profile("Post Paula")
        OWNERS[cls.uid] = [ACCT]

    def test_inbox_lists_header_fields_only(self):
        d = self.c.get("/api/profile/mail/inbox", params={"days": 30}).json()
        self.assertEqual(d["boxes"], ["Privat"])
        self.assertEqual([x["id"] for x in d["items"]], ["m0a1b2c3d:7", "m0a1b2c3d:8"])   # newest first
        a = d["items"][0]
        self.assertEqual((a["from"], a["subject"], a["unread"], a["box"]), ("Anna Alt <anna@example.de>", "Werkstatt <b>Auto</b>", True, 0))
        self.assertFalse(d["items"][1]["unread"])
        self.assertEqual(set(a), {"id", "from", "subject", "date", "unread", "flagged", "attach", "box"})   # never the text
        self.assertEqual(self.c.get("/api/profile/mail/inbox", params={"q": "rechnung", "days": 30}).json()["items"][0]["subject"], "Rechnung")

    def test_message_as_plain_text(self):
        m = self.c.get("/api/profile/mail/message", params={"id": "m0a1b2c3d:7"}).json()
        self.assertIn("der Wagen ist fertig", m["text"])
        self.assertNotIn("<", m["text"])
        self.assertNotIn("tracker.example", m["text"])
        self.assertEqual(m["subject"], "Werkstatt <b>Auto</b>")
        self.assertEqual(self.c.get("/api/profile/mail/message", params={"id": "m0a1b2c3d:99"}).status_code, 404)
        self.assertEqual(self.c.get("/api/profile/mail/message", params={"id": "kaputt"}).status_code, 400)

    def test_only_own_and_never_guests(self):
        other, _ = profile("Post Pit")
        self.assertEqual(other.get("/api/profile/mail/inbox").json(), {"connected": False, "boxes": [], "items": [], "errors": []})
        self.assertEqual(other.get("/api/profile/mail/message", params={"id": "m0a1b2c3d:7"}).status_code, 400)   # not his mailbox
        guest = TestClient(panel.app)
        for path in ("/api/profile/mail/inbox", "/api/profile/mail/message?id=m0a1b2c3d:7"):
            self.assertIn(guest.get(path).status_code, (401, 403), path)

    def test_off_gives_nothing(self):
        helpers.set_config(mail=False)
        try:
            for path in ("/api/profile/mail/inbox", "/api/profile/mail/message?id=m0a1b2c3d:7"):
                self.assertIn(self.c.get(path).status_code, (403, 503), path)
        finally:
            helpers.set_config(mail=True)

    def test_limits(self):
        seen = []
        orig = mail.find

        def spy(uid, query="", days=7, unread=False, limit=8, **kw):
            seen.append((len(query), days, limit))
            return orig(uid, query, days, unread, limit, **kw)
        mail.find = spy
        try:
            mail.inbox(self.uid, "x" * 500, 900, False, 900)
            mail.inbox(self.uid, "", -4, False, -1)
        finally:
            mail.find = orig
        self.assertEqual(seen, [(100, mail.DAYS, mail.INBOX_MAX), (0, 1, 1)])


@unittest.skipUnless(os.environ.get("SPEECH_UI_TESTS", "1") == "1", "browser tests off")
class Page(Fake):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def test_list_read_and_the_settings_sit_here(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for width in (1280, 390, 320):
                    br, pg, errors = await b.page(p, width, 900)
                    try:
                        # the browser's own profile gets the mailbox (its id from the page, no name here)
                        OWNERS[await pg.evaluate("PROFILE.id")] = [ACCT]
                        await pg.evaluate("MAIL_ON=true;postStart({profile:PROFILE,mail:true})")
                        if width == 1280:
                            self.assertNotEqual(await pg.evaluate("getComputedStyle(document.querySelector('nav button[data-s=post]')).display"), "none")
                        ids = await pg.evaluate("meAll().map(x=>x[0])")
                        self.assertNotIn("mailbox", ids)
                        self.assertNotIn("parbox", ids)
                        # the old place opens the settings of the page
                        await pg.evaluate("openMe('mailbox')")
                        await b.until(pg, "$('post').classList.contains('on')&&$('postroot').contains($('mailbox'))&&!$('mailbox').hidden&&$('mailbox').contains($('parbox'))")
                        # a second visit with „Einstellungen“ open: the settings are there again, never an empty card
                        # (Dominik 2026-10-19: clearing the card took the box out of the page), the same for Kalender
                        await pg.evaluate("goSec('cal')")
                        await pg.evaluate("goSec('post')")
                        await b.until(pg, "$('postroot').contains($('mailbox'))&&!$('mailbox').hidden")
                        await pg.evaluate("icTabSet('cal','set');goSec('cal')")
                        await pg.evaluate("goSec('post')")
                        await pg.evaluate("goSec('cal')")
                        await b.until(pg, "$('kalroot').contains($('calbox'))&&!$('calbox').hidden")
                        await pg.evaluate("icTabSet('post','show');goSec('post')")
                        await b.until(pg, "!POST.busy&&!!POST.data&&POST.data.items.length===2")
                        await b.until(pg, "document.querySelectorAll('#postview .ld-row').length===2")
                        # a subject from outside is text, never markup
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .ld-row b b').length"), 0)
                        self.assertIn("Werkstatt <b>Auto</b>", await pg.evaluate("$('postview').textContent"))
                        await pg.evaluate("document.querySelector('#postview .ld-row').click()")
                        # Apple-Stil „2a“: an HTML mail shows formatted in its frame, as the Spark cleaned it: the bold
                        # stays, the tracking picture from outside has no address, nothing runs, the page has no link
                        frame = "document.querySelector('#postview .postframe')"
                        await b.until(pg, f"!!POST.msg&&!!{frame}&&!!{frame}.contentDocument&&{frame}.contentDocument.body.textContent.includes('fertig')")
                        self.assertEqual(await pg.evaluate(f"{frame}.contentDocument.querySelector('b').textContent"), "fertig")
                        self.assertEqual(await pg.evaluate(f"[...{frame}.contentDocument.images].map(i=>i.getAttribute('src'))"), [None])
                        self.assertEqual(await pg.evaluate(f"{frame}.contentDocument.querySelectorAll('script,a[href]').length"), 0)
                        self.assertEqual(await pg.evaluate(f"{frame}.getAttribute('sandbox')"), "allow-same-origin")
                        self.assertTrue(await pg.evaluate("!!document.querySelector('#postview .postpics [data-k=pics]')"))
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .postdet img,#postview .postdet a').length"), 0)
                        await b.until(pg, f"{frame}.getBoundingClientRect().height>=48")   # sized to its content
                        # a link opens only after its real address was shown; a text naming another address is said
                        await pg.evaluate("window.opened=[];window.open=(...a)=>{window.opened.push(a)};0")
                        await pg.evaluate(f"{frame}.contentDocument.querySelector('[data-href]').click()")
                        await b.until(pg, "!document.querySelector('#postview .postlink').hidden")
                        say = await pg.inner_text("#postview .postlink")
                        self.assertIn("werkstatt.example", say)
                        self.assertIn("bank.example", say)
                        self.assertTrue(await pg.evaluate("!!document.querySelector('#postview .postlink .note.warn')"))
                        self.assertEqual(await pg.evaluate("window.opened"), [])
                        await pg.click("#postview .postlink [data-l=go]")
                        self.assertEqual(await pg.evaluate("window.opened"), [["https://werkstatt.example/r", "_blank", "noopener,noreferrer"]])
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{width} px scrolls sideways")
                        if width < 660:   # phones: the message instead of the list, back to the list
                            self.assertFalse(await pg.is_visible("#postview .ld-list"))
                            await pg.click("#postview .postdet .ld-back")
                            await b.until(pg, "!POST.sel&&document.querySelector('#postview .postdet').hidden")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_like_a_mail_client_keys_and_as_appointment(self):
        """Dominik 2026-10-19 „4a 5a“: the list by day with the sender's initials beside a wide reading pane; J/K
        go through the mails, Esc closes; „Als Termin“ brings the subject to Kalender → Schnell eintragen."""
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1280, 900)
                try:
                    OWNERS[await pg.evaluate("PROFILE.id")] = [ACCT]
                    await pg.evaluate("MAIL_ON=true;CAL_ON=true;postStart({profile:PROFILE,mail:true});icTabSet('post','show');goSec('post')")
                    await b.until(pg, "!POST.busy&&!!POST.data&&document.querySelectorAll('#postview .ld-row').length===2")
                    self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#postview .postav')].map(e=>e.textContent)"), ["AA", "S"])
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#postview .ld-grp').length"), 2)   # two days
                    await pg.keyboard.press("j")
                    await b.until(pg, "!!POST.msg&&POST.sel===POST.data.items[0].id")
                    widths = await pg.evaluate("[document.querySelector('#postview .ld-list').getBoundingClientRect().width,document.querySelector('#postview .postdet').getBoundingClientRect().width]")
                    self.assertGreater(widths[1], widths[0])   # the reading pane is the wide one
                    await pg.keyboard.press("j")
                    await b.until(pg, "POST.sel===POST.data.items[1].id")
                    await pg.keyboard.press("k")
                    await b.until(pg, "POST.sel===POST.data.items[0].id&&!!POST.msg&&!!document.querySelector('#postview [data-w=cal]')")
                    await pg.click("#postview [data-w=cal]")
                    await b.until(pg, "$('cal').classList.contains('on')&&KAL.q==='Werkstatt <b>Auto</b>'")
                    await pg.evaluate("goSec('post')")
                    await b.until(pg, "!!document.querySelector('#postview .ld-row')")
                    await pg.evaluate("document.querySelector('#postview .ld-row').click()")
                    await b.until(pg, "!!POST.sel")
                    await pg.keyboard.press("Escape")
                    await b.until(pg, "!POST.sel")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_proactive_rows_sit_on_the_pages(self):
        """Von selbst: the mail rows under E-Mail → Einstellungen, Termin-Vorlauf under Kalender → Einstellungen, none
        of them a second time under Ich → Von selbst (one place, Dominik 2026-10-18)."""
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        helpers.set_config(proactive=True)

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 1280, 900)
                try:
                    await pg.evaluate("PRO_ON=true;MAIL_ON=true;postStart({profile:PROFILE,mail:true})")
                    await pg.evaluate("openMe('mailbox')")
                    await b.until(pg, "!!document.querySelector('#promail input[data-k=pro_parcel]')")
                    mail_rows = await pg.evaluate("[...document.querySelectorAll('#promail input[data-k]')].map(e=>e.dataset.k)")
                    self.assertEqual(sorted(mail_rows), ["pro_fuerdich", "pro_mail", "pro_parcel", "pro_rueckblick", "pro_tidy"])
                    await pg.evaluate("proIn('procal')")
                    await b.until(pg, "!!document.querySelector('#procal input[data-k=pro_events]')")
                    await pg.evaluate("openMe('probox')")
                    await b.until(pg, "!!document.querySelector('#probox input[data-k=pro_on]')")
                    here = await pg.evaluate("[...document.querySelectorAll('#probox input[data-k]')].map(e=>e.dataset.k)")
                    for k in ("pro_events", "pro_mail", "pro_tidy", "pro_parcel", "pro_fuerdich", "pro_rueckblick"):
                        self.assertNotIn(k, here)
                    self.assertIn("E-Mail → Einstellungen", await pg.evaluate("$('probox').textContent"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        try:
            asyncio.run(go())
        finally:
            helpers.set_config(proactive=False)


if __name__ == "__main__":
    unittest.main()
