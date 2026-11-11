"""A page whose function is off says so (code review 2026-11-11, point 6): Mappen, Wissensbuch, Dungeon-Master and
Kontakte showed a lasting „Lade …“ (or nothing) when someone reached them by a link while the admin had the function
off. Each now shows one sentence with the way to its switch (base.js ausSatz, a jump link like every way); and the
footer stands at the bottom of a phone's window; Ich → Überblick is no copy of the menu. Static
checks everywhere, the browser check where Playwright and Chromium exist; no test reads the clock."""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok
from tests import test_ruhige_seiten

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")
# page (goSec) -> (script, the function's name as features.py has it, de and en)
SEITEN = {"mappen": ("mappen.js", "Mappen", "Collections"), "wbuch": ("wissensbuch.js", "Wissensbuch", "Knowledge book"),
          "dungeon": ("dungeon.js", "KI-Dungeon-Master", "AI Dungeon Master"), "kontakte": ("kontakte.js", "Kontakte", "Contacts")}


def read(name):
    with open(os.path.join(STATIC, "js", name), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_every_page_names_its_function_as_the_panel_does(self):
        import features
        namen = {(f[1], f[2]) for f in features.FEATURES}
        for seite, (js, de, en) in SEITEN.items():
            self.assertIn(f"ausSatz('{de}','{en}')", read(js), seite)
            self.assertIn((de, en), namen, seite)

    def test_one_sentence_with_the_way_for_all(self):
        base = read("base.js")
        m = re.search(r"const ausSatz=\(de,en\)=>t\(`([^`]+)`,`([^`]+)`\);", base)
        self.assertTrue(m)
        self.assertIn("Funktionen → ${de}", m.group(1))
        self.assertIn("Features → ${en}", m.group(2))
        self.assertEqual(sum(read(f).count("const ausSatz") for f in os.listdir(os.path.join(STATIC, "js"))), 1)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(memory=True, documents=True, search=True)
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Ruhig", "4711")
        except Exception:
            pass

    page = test_ruhige_seiten.Browser.page

    def test_a_page_whose_function_is_off_says_so_and_never_keeps_loading(self):
        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 800), (390, 760)):
                    br, pg, errors = await self.page(p, w, h, profile=True)
                    try:
                        for seite, (_, de, _en) in SEITEN.items():
                            await pg.evaluate(f"goSec('{seite}')")
                            satz = f"Die Funktion „{de}“ ist ausgeschaltet."
                            await pg.wait_for_function(
                                "s=>document.getElementById(s[0]).innerText.includes(s[1])", arg=[seite, satz], timeout=10000)
                            text = await pg.evaluate(f"document.getElementById('{seite}').innerText")
                            self.assertNotIn("Lade", text, (w, seite))
                            # the way is a jump link, like every way
                            self.assertTrue(await pg.evaluate(
                                f"[...document.querySelectorAll('#{seite} a.wayl')].some(a=>a.textContent.includes('{de}'))"), (w, seite))
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_the_footer_stands_at_the_bottom_on_a_phone(self):
        """On a short page the footer stood in the middle of the phone's screen, on a long one it ended under the
        tab bar: now it is the last thing above the tab bar, and the chat has none as before."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 390, 760, profile=True)
                try:
                    maß = ("(()=>{const c=document.getElementById('credit').getBoundingClientRect(),"
                           "b=document.getElementById('aptabs').getBoundingClientRect();"
                           "return [Math.round(c.bottom),Math.round(b.top),Math.round(c.height),"
                           "document.documentElement.scrollHeight,innerHeight]})()")
                    for seite in ("mappen", "offen"):                 # short pages
                        await pg.evaluate(f"goSec('{seite}')")
                        await pg.wait_for_timeout(600)
                        unten, leiste, hoch, ganz, fenster = await pg.evaluate(maß)
                        self.assertGreater(hoch, 0, seite)
                        self.assertEqual(ganz, fenster, seite)        # nothing to scroll
                        self.assertLessEqual(unten, leiste + 1, seite)
                        self.assertGreater(unten, leiste - 24, seite)
                    await pg.evaluate("goSec('feat')")                # a long page: scrolled to its end
                    await pg.wait_for_timeout(600)
                    await pg.evaluate("scrollTo(0,document.documentElement.scrollHeight)")
                    await pg.wait_for_timeout(200)
                    unten, leiste, hoch, ganz, fenster = await pg.evaluate(maß)
                    self.assertGreater(ganz, fenster)
                    self.assertLessEqual(unten, leiste + 1)
                    await pg.evaluate("goSec('chat')")
                    await pg.wait_for_timeout(400)
                    self.assertEqual((await pg.evaluate(maß))[2], 0)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_the_me_overview_is_no_copy_of_the_menu(self):
        """Ich → Überblick (code review 2026-11-11, point 6): every group header stands once in the menu („Meine
        Daten“ stood twice), the overview lists only pages that have something to say, and „Los geht's“ stands
        there once."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900, profile=True)
                try:
                    await pg.evaluate("openMe('overbox')")
                    await pg.wait_for_function("document.querySelectorAll('#overbox .overrow b').length>0", timeout=20000)
                    menu = await pg.evaluate("[...document.querySelectorAll('#ptabs .mgrp')].map(e=>e.textContent)")
                    self.assertGreater(len(menu), 2)
                    self.assertEqual(len(menu), len(set(menu)), menu)
                    self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#ptabs button')].pop().previousElementSibling.textContent"), "Zugang")
                    rows = await pg.evaluate("[...document.querySelectorAll('#overbox .overlist .overrow')].map(b=>[b.dataset.go,b.querySelector('span').textContent])")
                    self.assertIn("factbox", [r[0] for r in rows])
                    self.assertTrue(all(r[1].strip() for r in rows), rows)
                    self.assertLess(len(rows), await pg.evaluate("document.querySelectorAll('#ptabs button').length") - 1)
                    self.assertLessEqual(await pg.evaluate("document.querySelectorAll('#overbox [data-go=gobox]').length"), 1)
                    heads = await pg.evaluate("[...document.querySelectorAll('#overbox .overlist .mgrp')].map(e=>e.textContent)")
                    self.assertEqual(len(heads), len(set(heads)), heads)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
