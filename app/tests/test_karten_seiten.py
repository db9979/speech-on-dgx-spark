"""Karten im Assistenten (plan kalender-mail Stufe 2): an answer that read appointments or one mail carries a way to
the own page, „Im Kalender ansehen“ (that day) or „Mail öffnen“ (that mail), event "goto" from chat_tools.py.

- calendar_events sends {"type": "goto", "to": "cal", "day": the day read}; mail_read sends {"to": "post", "id": the
  id} only when the mail was read, never for an unknown id or a message no longer there.
- The card under the answer is only a link: the page shows what the server allows; nothing happens without the click,
  never for another person's voice, never without the page (CAL_ON, MAIL_ON). At 390 px it opens the Calendar page
  on that day and the E-mail page with that mail.

Fixed dates (2026-03), the fake mailbox and CalDAV server; no wall clock.
"""
import asyncio
import types
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import panel  # noqa: E402
import calendars  # noqa: E402
import chat_tools  # noqa: E402
import mail  # noqa: E402
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


def events(coro_of_t):
    t = coro_of_t
    q = asyncio.Queue()
    t.out = q
    return q


def drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return [e for e in out if e["type"] == "goto"]


class Events(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, calendar=True)
        cls.c, cls.uid = profile("Karten Karla")
        FMB.reset(inbox=[helpers.box_mail("Anna <anna@example.de>", "Werkstatt fertig", "Der Wagen ist fertig.", mid="<k-1@x>")])
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]["id"]
        if not calendars.get(cls.uid)["calendars"]:
            calendars.add(cls.uid, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                                    "user": "k", "password": "pw"}))

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False)

    def turn(self):
        t = types.SimpleNamespace(who={"id": self.uid}, body={"tz": "Europe/Berlin"}, src="", own_browser=True,
                                  ex={"changes": False, "run": {}, "mail": set(), "outside": set()},
                                  locked=lambda st: set(), cal=calendars.reading(self.uid))
        return t, events(t)

    def test_mail_read_carries_the_mail(self):
        t, q = self.turn()
        st = {"mail": False}
        text = asyncio.run(chat_tools.mail_tool(t, "mail_read", {"id": f"{self.acct}:100"}, st))
        self.assertIn("Werkstatt", text)
        self.assertEqual(drain(q), [{"type": "goto", "to": "post", "id": f"{self.acct}:100"}])
        for ref in (f"{self.acct}:999", "m00000000:1", "egal"):
            t, q = self.turn()
            asyncio.run(chat_tools.mail_tool(t, "mail_read", {"id": ref}, {"mail": False}))
            self.assertEqual(drain(q), [], ref)

    def test_calendar_events_carry_the_day(self):
        t, q = self.turn()
        st = {"offered": {"calendar_events"}, "mail": False, "outside": False, "first": True}
        asyncio.run(chat_tools.run(t, "calendar_events", {"date": "2026-03-10", "days": 1}, st))
        self.assertEqual(drain(q), [{"type": "goto", "to": "cal", "day": "2026-03-10"}])


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mail.IMAP = FMB
        helpers.set_config(mail=True, calendar=True)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        mail.IMAP = helpers.FakeIMAP
        helpers.set_config(mail=False)

    def test_cards_open_the_pages(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port
        FMB.reset(inbox=[helpers.box_mail("Anna <anna@example.de>", "Werkstatt fertig", "Der Wagen ist fertig.", mid="<k-2@x>")])

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await b.page(p, 390, 900)
                try:
                    uid = await pg.evaluate("PROFILE.id")
                    if not mail.get(uid)["accounts"]:
                        r = await pg.request.post(f"http://127.0.0.1:{self.port}/api/profile/mail",
                                                  data={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
                        self.assertEqual(r.status, 200, await r.text())
                    acct = mail.get(uid)["accounts"][0]["id"]
                    mail._cache.clear()
                    await pg.evaluate("CAL_ON=true;MAIL_ON=true")
                    n = await pg.evaluate("gotoCard([{type:'goto',to:'cal',day:'2026-03-10'},{type:'goto',to:'post',id:'%s:100'}]).children.length" % acct)
                    self.assertEqual(n, 2)
                    # without the pages, or with something that is not a day or an id: no card
                    self.assertTrue(await pg.evaluate("CAL_ON=false;MAIL_ON=false;gotoCard([{to:'cal',day:'2026-03-10'},{to:'post',id:'%s:100'}])===null" % acct))
                    self.assertTrue(await pg.evaluate("CAL_ON=true;MAIL_ON=true;gotoCard([{to:'cal',day:'morgen'},{to:'post',id:'javascript:1'}])===null"))
                    # the card stands where the phone's tab bar (#aptabs, fixed at the bottom, shown once two tabs are
                    # on) never covers it: at the body's end it lay under the bar and the click never came (red at V01.1.272)
                    pin = ".style.cssText='position:fixed;top:120px;left:8px;right:8px;z-index:60'"
                    await pg.evaluate("(()=>{const c=document.body.appendChild(gotoCard([{to:'cal',day:'2026-03-10'}]));c.id='gk1';c%s})()" % pin)
                    await pg.click("#gk1 button")
                    await b.until(pg, "!!KAL.data&&!KAL.busy&&KAL.day.getFullYear()===2026&&KAL.day.getMonth()===2&&KAL.day.getDate()===10")
                    await pg.evaluate("(()=>{const c=document.body.appendChild(gotoCard([{to:'post',id:'%s:100'}]));c.id='gk2';c%s})()" % (acct, pin))
                    await pg.click("#gk2 button")
                    await b.until(pg, "!!POST.msg&&!!document.querySelector('#postview .posttext')")
                    self.assertIn("Wagen", await pg.evaluate("document.querySelector('#postview .posttext').textContent"))
                    over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    self.assertLessEqual(over, 1)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
