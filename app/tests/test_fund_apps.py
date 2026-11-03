"""Finden, Stufe E (plan such-index): the apps and the last open part of Stufe B.

- A mail's detail lists its attachments (names only, at most fund.ANHANG_MOST), on the page too (real browser);
  „Zu Dokumenten übernehmen“ follows with wissen.aufnehmen (another thread), so there is no way for it yet.
- The Begleiter: the Sofort-Karte's „Original öffnen“ is #fund=<number> beside the pages of chat.DESK_GOTO, nothing
  else; the programs (Windows, Mac) take only that form.
- The iPhone app: a page of its own (FindenView.swift) under Meine Sachen with the admin release of Finden (hello
  "areas", iphone.THINGS "fund"), every path it calls is one of THINGS "fund", the Sofort-Karte's card with
  „Original öffnen“ (#fund=<number> in the panel inside the app) and „In Finden ansehen“, every text with English.
- Android shows the panel itself (appview.js): the page Finden comes with features.OWN_PAGES like every page.
Files outside app/ skip in the app/-only copy. A fixed moment, never the clock.
"""
import asyncio
import contextlib
import io
import json
import os
import re
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import chat  # noqa: E402
import documents  # noqa: E402
import features  # noqa: E402
import fund  # noqa: E402
import fundmail  # noqa: E402
import iphone  # noqa: E402
import mail  # noqa: E402
from tests.test_fund_mail import FMB, NOW, fill  # noqa: E402
from tests.test_mailclient_c import profile  # noqa: E402
from tests.test_ui_browser import browser_ok  # noqa: E402

ROOT = os.path.dirname(helpers.APP)


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def src(*parts):
    path = os.path.join(ROOT, *parts)
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{'/'.join(parts)} is not part of this copy (the Spark tests only app/)")
    with open(path, encoding="utf-8") as f:
        return f.read()


class Base(unittest.TestCase):
    NAME = "Fundapp Ada"

    def setUp(self):
        helpers.keep_chat(self, "fund", "fund_mail", "mail", "documents", "knowledge_book", "mail_idle")
        helpers.set_config(fund=True, fund_mail=True, mail=True, documents=True, knowledge_book=False)
        self.saved = mail.IMAP
        mail.IMAP = FMB
        self.addCleanup(setattr, mail, "IMAP", self.saved)
        fill()
        self.c, self.uid = profile(self.NAME)
        for a in mail.get(self.uid)["accounts"]:
            mail.remove(self.uid, a["id"])
        for d in documents.list_docs(self.uid):
            documents.delete(self.uid, d["id"])
        with quiet():
            fund.leeren(self.uid, hand=True)
        self.aid = mail.add(self.uid, mail.entry({"kind": "icloud", "user": helpers.MAIL_USER,
                                                  "password": helpers.MAIL_PW}))["accounts"][0]["id"]
        self.addCleanup(lambda: [mail.remove(self.uid, a["id"]) for a in mail.get(self.uid)["accounts"]])
        for p in (mock.patch.object(fundmail, "_ruhig", lambda now: True), mock.patch.object(fundmail, "_platz", lambda uid: True)):
            p.start()
            self.addCleanup(p.stop)
        fundmail._last.clear()
        fundmail._poke.clear()
        fundmail._names.clear()
        with quiet():
            fundmail.runde(self.uid, NOW, 60)

    def attachment(self):
        """(the attachment's entry, its mail's entry) of the invoice PDF."""
        with fund._Db(self.uid) as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM fund_item WHERE quelle='anhang'")]
        for r in rows:
            if fund.klar(self.uid, r)[0] == "Beleg-Quokka.pdf":
                return r["id"], r["eltern"]
        self.fail("no attachment in the index")



class Anhaenge(Base):
    def test_the_detail_lists_a_mails_attachments_only_names(self):
        aid, mid = self.attachment()
        it = self.c.get(f"/api/profile/fund/eintrag/{mid}").json()
        self.assertEqual([a["titel"] for a in it["anhaenge"]][:1], ["Beleg-Quokka.pdf"])
        self.assertIn(aid, [a["id"] for a in it["anhaenge"]])
        self.assertLessEqual(len(it["anhaenge"]), fund.ANHANG_MOST)
        self.assertTrue(all(set(a) == {"id", "titel"} for a in it["anhaenge"]))
        self.assertNotIn("zu_dokumenten", it)
        att = self.c.get(f"/api/profile/fund/eintrag/{aid}").json()
        self.assertNotIn("anhaenge", att)                                        # an attachment has none of its own
        cb, _ = profile("Fundapp Bert")
        self.assertEqual(cb.get(f"/api/profile/fund/eintrag/{mid}").status_code, 404)   # never another profile's

    def test_no_way_into_the_documents_yet(self):
        aid, _ = self.attachment()
        before = len(documents.list_docs(self.uid))
        self.assertIn(self.c.post(f"/api/profile/fund/eintrag/{aid}/zu-dokumenten").status_code, (404, 405))
        self.assertEqual(len(documents.list_docs(self.uid)), before)
        self.assertFalse(any(re.compile(p).fullmatch(f"/api/profile/fund/eintrag/{aid}/zu-dokumenten")
                             for _, p in iphone.THINGS["fund"]))


class Begleiter(unittest.TestCase):
    def test_the_sofort_karte_opens_the_original(self):
        out = chat.desk_cards([], [{"type": "goto", "to": "fund", "q": "Rechnung Thomann", "id": 42}])
        self.assertEqual(out["cards"][0]["buttons"], [{"label": "Original öffnen", "open": "#fund=42", "main": True},
                                                      {"label": "In Finden ansehen", "open": "#me=fundbox"}])
        out = chat.desk_cards([], [{"type": "goto", "to": "fund", "q": "Rechnung"}])     # not clearly ahead
        self.assertEqual(out["cards"][0]["buttons"], [{"label": "In Finden ansehen", "open": "#me=fundbox"}])
        for bad in ("42x", "javascript:1", "#fund=1", "1" * 13, -1, None, True):
            out = chat.desk_cards([], [{"type": "goto", "to": "fund", "q": "x", "id": bad}])
            self.assertEqual([b["open"] for b in out["cards"][0]["buttons"]], ["#me=fundbox"], bad)

    def test_the_programs_take_only_that_form(self):
        cs = src("tools", "begleiter", "windows", "Karten.cs")
        self.assertIn('@"^#fund=[0-9]{1,12}\\z"', cs)
        self.assertIn("Allowed(page) ? page : null", cs)
        sw = src("tools", "begleiter", "mac", "Sources", "Karten.swift")
        self.assertIn('"^#fund=[0-9]{1,12}$"', sw)
        self.assertIn("allowed($0) ? $0 : nil", sw)
        self.assertEqual(chat.DESK_ORIGINAL, ("Original öffnen", "#fund="))
        start = helpers.repo_file("app", "panel", "static", "js", "start.js")
        self.assertIn(r"/^#fund=(\d{1,12})$/", start)                            # the panel opens only a number


class IPhone(unittest.TestCase):
    def test_a_page_of_its_own_with_the_release_of_finden(self):
        view = src("ios", "Spark", "FindenView.swift")
        things = src("ios", "Spark", "ThingsView.swift")
        self.assertIn('if a.areas.contains("fund") {', things)
        self.assertIn("NavigationLink { FindenView() }", things)
        self.assertIn("fund", iphone.THINGS)
        # every path the app calls is one of iphone.THINGS "fund" (the Spark checks the release on each)
        rules = [(set(m), re.compile(p)) for m, p in iphone.THINGS["fund"]]
        calls = re.findall(r'api\.(?:object|call)\("([A-Z]+)", "(api/profile/fund[^"]*)"(?: \+ String\(\w+\)( \+ "[^"]*")?)?', view)
        self.assertGreaterEqual(len(calls), 6, calls)
        for method, path, tail in calls:
            full = "/" + path + ("1" + tail.strip(' +"') if path.endswith("/") else "")
            self.assertTrue(any(method in m and r.fullmatch(full) for m, r in rules), (method, full))
        for word in ("Original öffnen", "In Finden ansehen", "Anhänge", "Neu aufbauen", "Index löschen",
                     "Schlagwort hinzufügen", "vom Modell"):
            self.assertIn(f'"{word}"', view)
        self.assertNotRegex(view, r"UserDefaults|FileManager|Merken\.keep")      # nothing of the index kept on the iPhone

    def test_the_sofort_karte_in_the_chat(self):
        api = src("ios", "Shared", "SparkAPI.swift")
        self.assertIn('case "goto" where ev["to"] as? String == "fund":', api)
        self.assertIn("(1...999_999_999_999).contains($0)", api)
        panel_api = src("ios", "Spark", "PanelAPI.swift")
        self.assertIn('"/#fund=" + String(id)', panel_api)
        views = src("ios", "Spark", "Views.swift")
        self.assertIn('talk.allowed.areas.contains("fund") { FundKarte(q: q, id: m.fundId) }', views)
        self.assertIn("case .fund(let q, let id): edit { $0.fundQ = q; $0.fundId = id }", src("ios", "Spark", "Assistant.swift"))

    def test_every_text_has_english(self):
        strings = json.loads(src("ios", "Spark", "Localizable.xcstrings"))["strings"]
        view = src("ios", "Spark", "FindenView.swift")
        rx = re.compile(r'(?:Text|LocalizedStringKey|navigationTitle|Section|Label|Button|Picker|TextField|confirmationDialog|'
                        r'String\(localized:)\s*\(?\s*"((?:[^"\\]|\\.)*)"')
        keys = {m.group(1) for m in rx.finditer(view) if re.search(r"[A-Za-zÄÖÜäöüß]", m.group(1)) and "\\(" not in m.group(1)}
        self.assertGreater(len(keys), 40)
        missing = sorted(k for k in keys if not (strings.get(k) or {}).get("localizations", {}).get("en"))
        self.assertEqual(missing, [])

    def test_android_takes_the_panels_page(self):
        self.assertIn(("fundbox", "finden", "Finden", "Find"), features.OWN_PAGES)
        view = helpers.repo_file("app", "panel", "static", "js", "appview.js")
        self.assertIn("sec.id==='finden'", view)     # the page of its own sits in the app view's tab like Kalender


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    """A mail's attachments in its detail on the page Finden in a real browser (strict CSP, 1280 and 390 px)."""
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def setUp(self):
        helpers.keep_chat(self, "fund", "fund_mail", "mail", "mail_manage", "documents", "knowledge_book")
        helpers.set_config(fund=True, fund_mail=True, mail=True, mail_manage=True, documents=True, knowledge_book=False)
        self.saved = mail.IMAP
        mail.IMAP = FMB
        self.addCleanup(setattr, mail, "IMAP", self.saved)
        for p in (mock.patch.object(fundmail, "_ruhig", lambda now: True), mock.patch.object(fundmail, "_platz", lambda uid: True)):
            p.start()
            self.addCleanup(p.stop)
        fill()

    def test_a_mails_detail_lists_its_attachments(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900, csp=True)
                    try:
                        await b.until(pg, "window.FUND_ON===true")
                        uid = await pg.evaluate("PROFILE.id")
                        for a in mail.get(uid)["accounts"]:
                            mail.remove(uid, a["id"])
                        for d in documents.list_docs(uid):
                            documents.delete(uid, d["id"])
                        mail.add(uid, mail.entry({"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW}))
                        self.addCleanup(lambda u=uid: [mail.remove(u, a["id"]) for a in mail.get(u)["accounts"]])
                        with quiet():
                            fund.leeren(uid, hand=True)
                            fundmail.runde(uid, NOW, 60)
                        await pg.evaluate("goSec('finden')")
                        await b.until(pg, "!!document.querySelector('#fundview .fundq')&&!!FUND.stand")
                        await pg.fill("#fundview .fundq", "Ohrensessel")
                        await pg.press("#fundview .fundq", "Enter")
                        await b.until(pg, "document.querySelectorAll('#fundview [data-fundsel]').length===1")
                        await pg.click("#fundview [data-fundsel]")
                        await b.until(pg, "!!document.querySelector('#fundview .funddet:not([hidden]) .fundanh')")
                        self.assertIn("Beleg-Quokka.pdf", await pg.text_content("#fundview .fundanh"))
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#fundview .funddet button').length>0"), True)
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
