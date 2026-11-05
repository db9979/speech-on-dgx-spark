"""Mappen ruhiger (plan mappen-layout, Dominik 2026-11-05 „die seite sieht leider etwas unübersichtlich aus“, draft
„ok“: 1a 2a 3a): the page Mappen in a real browser at 1440 and 390 px.

- no tabs on the page (1a): no „Einstellungen“ beside the list, the explanation sits in the ⓘ beside the budget, and no
  way „Mappen → Einstellungen“ is left (features.OWN_NO_SETTINGS, kalender.js OWN_NO_SET);
- the list (300 px) is narrower than the open Mappe; on the phone first the list, then the Mappe with „‹ Mappen“;
- in every part (Einträge, Auswertungen, Hörstück) at most one blue button, and that is „Fragen“ (2a);
- no title is cut off and nothing scrolls sideways;
- the level of an entry is a small menu (3a): choosing „aus“ reaches the Spark; ⋯ → „Aus der Mappe nehmen“ takes it
  out; „Erstellen“ in the part Hörstück makes one; the Auswertungen part lists the documents with their analyses.
"""
import asyncio
import os
import sys
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "panel"))
import auswertung  # noqa: E402
import documents  # noqa: E402
import features  # noqa: E402
import hilfe  # noqa: E402
import hoerstueck  # noqa: E402
import mappen  # noqa: E402

NAME, PIN = "Mappenseite", "8531"   # this file's own profile (test_richtlinie: one name per test file)
LONG = "Angebot Gastherme Müller mit Wartungsvertrag, Einbau und Entsorgung der alten Anlage bis Ende Oktober.pdf"


class NoSettingsTab(unittest.TestCase):
    def test_no_way_to_a_tab_that_is_gone(self):
        self.assertIn("mpbox", features.OWN_NO_SETTINGS)
        for lang, word in (("de", "Mappen → Einstellungen"), ("en", "Collections → Settings")):
            self.assertNotIn(word, hilfe.funktionen_liste(lang))
        for rel in (("docs", "de", "assistent.md"), ("docs", "en", "assistant.md")):
            try:
                text = helpers.repo_file(*rel)
            except (OSError, unittest.SkipTest):
                continue   # a copy with app/ only
            self.assertNotIn("Mappen → Einstellungen", text)
            self.assertNotIn("Collections → Settings", text)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def setUp(self):
        helpers.keep_chat(self, "mappen", "mappe_token", "hoerstueck", "hoerstueck_day", "hoerstueck_stimmen", "documents",
                          "doc_semantic", "doc_brief", "doc_auswertung", "knowledge_book", "knowledge_map")
        helpers.set_config(mappen=True, mappe_token=mappen.TOKEN, hoerstueck=True, hoerstueck_day=hoerstueck.DAY_MAX,
                           hoerstueck_stimmen=[], documents=True, doc_semantic=False, doc_brief=False, doc_auswertung=True,
                           knowledge_book=False, knowledge_map=False)
        hoerstueck._stimmen.update(t=4e9, design=False)   # never asks the speech output for its list
        hoerstueck._hold["tts"] = 0.0

    def data(self):
        """A Mappe with three documents (one with a long title), a note, an analysis and one finished Hörstück."""
        from tests import test_hoerstueck as th
        c = th.profile(NAME, PIN)
        uid = th.uid_of(NAME)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        for m in mappen.liste(uid):
            mappen.loeschen(uid, m["id"])
        mid = mappen.neu(uid, "Wärmepumpe", ziel="Heizung tauschen bis zum Winter", symbol="haus")
        mappen.neu(uid, "Steuer 2025", symbol="geld")
        ids = []
        for name, text, lvl in (("Angebot Wärme Nord.pdf", th.OFFER, "ganz"), ("Förderbescheid BAFA.pdf", th.GRANT, "kurz"),
                                (LONG, "Angebot Müller\n\nGas-Brennwerttherme 9 800 Euro mit Einbau.", "kurz")):
            d = documents.add(uid, name, text.encode(), text=text)["id"]
            ids.append(d)
            mappen.dazu(uid, mid, [("dok", d, lvl)])
        auswertung._store(uid, ids[1], "kurz", "ok", [{"text": "Kurzfassung des Bescheids.", "page": 1}], now=th.NOW)
        r = c.post(f"/api/profile/mappen/{mid}/notiz", json={"titel": "Fragen an den Monteur", "text": "Wie laut ist sie?"})
        self.assertEqual(r.status_code, 200, r.text)
        t = th.Base("run")
        t.make(c, mid, laenge=5, stimmen=2)
        model, voice = th.Model(lambda tx, s: th.good_script(tx, 2)), th.Voice()
        for _ in range(60):
            if hoerstueck.liste(uid, mid)["stuecke"][0]["stand"] == "fertig":
                break
            t.step(uid, model, voice)
        self.assertEqual(hoerstueck.liste(uid, mid)["stuecke"][0]["stand"], "fertig")
        return uid, mid, ids

    def test_list_detail_one_blue_button_whole_titles(self):
        from tests.test_ui_browser import Browser, async_playwright
        uid, mid, ids = self.data()
        b = Browser("run")
        b.port = self.port
        tabs = "[...document.querySelectorAll('#mpview .mpsegbar button')].map(x=>x.firstChild.textContent)"
        shown = "x=>x.offsetParent!==null"
        cut = ("[...document.querySelectorAll('#mpview .mpdet .ld-mid b,#mpview .mptop .mpname b,#mpview .ld-list .ld-mid b')]"
               ".filter(" + shown + ").filter(x=>x.scrollWidth>x.clientWidth+1).map(x=>x.textContent)")

        async def go():
            async with async_playwright() as p:
                for w, h in ((1440, 900), (390, 844)):
                    br, pg, errors = await b.page(p, w, h, who=(NAME, PIN))
                    try:
                        await pg.evaluate("goSec('mappen')")
                        await b.until(pg, f"!!MP.list&&!!document.querySelector('#mpview [data-mpsel=\"{mid}\"]')")
                        # 1a: no tabs on the page, ＋ in the list's head
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#mappen .ic-tabs').length"), 0)
                        self.assertTrue(await pg.evaluate("!!document.querySelector('#mpview .mphead [data-mpneu]')"))
                        await pg.click(f"#mpview [data-mpsel='{mid}']")
                        await b.until(pg, f"!!MP.one&&MP.one.id==='{mid}'&&!!document.querySelector('#mpview .mptop')")
                        if w > 660:
                            lw, dw = await pg.evaluate("[document.querySelector('#mpview .ld-list'),document.querySelector('#mpview .mpdet')].map(x=>x.getBoundingClientRect().width)")
                            self.assertLess(lw, dw, "the list is narrower than the open Mappe")
                            self.assertLessEqual(lw, 310)
                        else:   # the phone: the Mappe is the page, the list waits behind „‹ Mappen“
                            self.assertTrue(await pg.evaluate("document.querySelector('#mpview .ld-list').offsetParent===null"))
                            self.assertTrue(await pg.evaluate("document.querySelector('#mpview .ld-back').offsetParent!==null"))
                        await b.until(pg, tabs + ".length===3")
                        self.assertEqual(await pg.evaluate(tabs), ["Einträge", "Auswertungen", "Hörstück"])
                        for i, part in enumerate(("e", "a", "h")):
                            await pg.evaluate(f"document.querySelectorAll('#mpview .mpsegbar button')[{i}].click()")
                            await b.until(pg, f"MP.tab==='{part}'")
                            if part == "h":
                                await b.until(pg, "!!document.querySelector('#mpview .hsbox .hsmake')&&!!document.querySelector('#mpview .hsbox audio')")
                            if part == "a":
                                # one row per document of the Mappe (the note too), ⋯ took one out on the computer
                                await b.until(pg, "document.querySelectorAll('#mpview .mptab [data-mpdoc]').length===MP.one.eintraege.filter(e=>e.art_eintrag==='dok').length&&MP.one.eintraege.length>=3")
                                self.assertIn("Kurzfassung", await pg.text_content("#mpview .mptab"))
                            blue = await pg.evaluate("[...document.querySelectorAll('#mappen .b.p')].filter(" + shown + ").map(x=>x.textContent.trim())")
                            self.assertEqual(blue, ["Fragen"], f"{w}/{part}: one blue button only")
                            self.assertEqual(await pg.evaluate(cut), [], f"{w}/{part}: titles are never cut off")
                            over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                            self.assertLessEqual(over, 1, f"{w}/{part}: the page scrolls sideways")
                        # the ⓘ holds what the tab „Einstellungen“ said
                        await pg.click("#mpview .mpinfo")
                        await b.until(pg, "!!document.querySelector('#mpview .mpinfobox')")
                        self.assertIn("Budget", await pg.text_content("#mpview .mpinfobox"))
                        if w > 660:
                            await pg.evaluate("document.querySelectorAll('#mpview .mpsegbar button')[0].click()")
                            await b.until(pg, f"!!document.querySelector('#mpview .mptab [data-mpref=\"{ids[0]}\"] select[data-mplvl]')")
                            self.assertIn(LONG, await pg.text_content("#mpview .mptab"))
                            # 3a: the level is a small menu
                            await pg.select_option(f"#mpview [data-mpref='{ids[0]}'] select[data-mplvl]", "aus")
                            await b.until(pg, f"MP.one.eintraege.find(e=>e.ref==='{ids[0]}').stufe==='aus'")
                            self.assertEqual(next(e for e in mappen.mappe(uid, mid)["eintraege"] if e["ref"] == ids[0])["stufe"], "aus")
                            # ⋯ → Aus der Mappe nehmen
                            row = f"#mpview [data-mpref='{ids[2]}']"
                            await pg.click(row + " [data-mpmenu]")
                            await b.until(pg, f"document.querySelector(\"{row} .ic-pop\").hidden===false")
                            await pg.click(row + " [data-mpweg]")
                            await b.until(pg, f"!MP.one.eintraege.some(e=>e.ref==='{ids[2]}')")
                            self.assertNotIn(ids[2], [e["ref"] for e in mappen.mappe(uid, mid)["eintraege"]])
                            self.assertIn(ids[2], [d["id"] for d in documents.list_docs(uid)], "the document stays")
                            # Hörstück: „Erstellen“ in the part's one row, a normal button
                            await pg.evaluate("document.querySelectorAll('#mpview .mpsegbar button')[2].click()")
                            await b.until(pg, "!!document.querySelector('#mpview .hsbox [data-hsmake]')")
                            self.assertFalse(await pg.evaluate("document.querySelector('#mpview .hsbox [data-hsmake]').classList.contains('p')"))
                            await pg.click("#mpview .hsbox [data-hsmake]")
                            await b.until(pg, "!!HS.data&&HS.data.stuecke.length===2")
                            self.assertEqual(len(hoerstueck.liste(uid, mid)["stuecke"]), 2)
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
