"""Alles auch im Hochformat (Dominik 2026-11-14: „es werden nicht alle Funktionen im Hochformat angezeigt und sind nur
über Querformat aufrufbar“). Below 760 px a phone shows the app view (appview.js) instead of the menu on the left:
its tabs, Heute and „Spark verwalten“. E-Mail, Kontakte, Wissensbuch, Finden, Mappen and the Dungeon-Master had no
entry there and were reachable in landscape only. Now every page of the menu has its place in portrait: the tabs
(Assistent, Chats), Heute → Meine Seiten (one's own pages, in the menu's order) and Spark verwalten (the admin's pages);
a phone in the computer layout lists a profile's own pages in its menu sheet as well. Static checks everywhere, the
browser check where Playwright and Chromium exist; no test reads the clock."""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests import test_ruhige_seiten
from tests.test_ui_browser import async_playwright, browser_ok

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


def nav_pages():
    """The pages of the menu (nav button data-s) in its order, split at „Ich“: own pages above, the admin's below."""
    nav = re.search(r"<nav>(.*?)</nav>", read("index.html"), re.S).group(1)
    own, admin = nav.split('id="navme"')
    return re.findall(r'data-s="(\w+)"', own), re.findall(r'data-s="(\w+)"', admin)


class Static(unittest.TestCase):
    def test_every_own_page_of_the_menu_is_an_own_page_of_the_app_view(self):
        own, _ = nav_pages()
        js = read("js", "appview.js")
        listed = set(re.search(r"const OWN=new Set\(\[([^\]]+)\]\)", js).group(1).replace("'", "").split(","))
        for s in own:
            if s not in ("chat", "chats"):   # these two are tabs of their own
                self.assertIn(s, listed, s)

    def test_every_admin_page_of_the_menu_is_in_spark_verwalten(self):
        _, admin = nav_pages()
        js = read("js", "appview.js")
        body = js[js.index("function renderManage"):js.index("manage.addEventListener")]
        for s in admin:
            self.assertIn(f"['{s}',", body, s)

    def test_meine_seiten_in_both_languages(self):
        self.assertIn("t('Meine Seiten','My pages')", read("js", "appview.js"))


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

    def test_every_page_of_the_menu_is_reachable_in_portrait(self):
        """Every page of the menu shown (here all of them, as when the admin released every function) has a row or a
        tab on a phone in portrait, and that row opens the page; back goes to where it came from."""
        own, admin = nav_pages()
        show = "document.querySelectorAll('nav button[data-s]').forEach(b=>b.hidden=false);$('navowui').hidden=false"

        async def go():
            async with async_playwright() as p:
                for w, h in ((390, 844), (430, 932)):
                    br, pg, errors = await self.page(p, w, h, profile=True)
                    try:
                        await pg.wait_for_function("typeof PROFILE!=='undefined'&&!!PROFILE", timeout=20000)
                        await pg.evaluate(show)
                        tabs = await pg.evaluate("[...document.querySelectorAll('#aptabs button')].map(b=>b.dataset.tab)")
                        self.assertIn("spark", tabs)
                        self.assertIn("chats", tabs)
                        await pg.evaluate("document.querySelector('#aptabs [data-tab=today]').click()")
                        await pg.wait_for_selector("#aptoday [data-own]", timeout=20000)
                        rows = await pg.evaluate("[...document.querySelectorAll('#aptoday [data-own]')].map(b=>b.dataset.own)")
                        self.assertEqual(rows, [s for s in own if s not in ("chat", "chats")], w)
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#aptoday [data-owui]').length"), 1)
                        for s in rows:
                            await pg.evaluate(f"document.querySelector('#aptoday [data-own={s}]').click()")
                            await pg.wait_for_function("s=>document.querySelector('main>section.on').id===s", arg=s, timeout=10000)
                            # one's own page, back to Heute (not to Verwalten)
                            self.assertEqual(await pg.evaluate("APV.current()"), "today", s)
                            await pg.evaluate("document.querySelector('#aptabs [data-tab=today]').click()")
                            await pg.wait_for_selector(f"#aptoday [data-own={s}]", timeout=10000)
                        await pg.evaluate("document.querySelector('#aptabs [data-tab=manage]').click()")
                        await pg.wait_for_selector("#apmanage [data-sec]", timeout=20000)
                        secs = await pg.evaluate("[...document.querySelectorAll('#apmanage [data-sec]')].map(b=>b.dataset.sec)")
                        for s in admin:
                            self.assertIn(s, secs, (w, s))
                        # a phone in the computer layout: the menu sheet lists the pages too
                        await pg.evaluate("localStorage.setItem('appview','off');APV.apply();" + show + ";$('mmenu').click()")
                        listed = await pg.evaluate("[...$('madmin').querySelectorAll('button')].map(b=>b.dataset.s)")
                        self.assertEqual(listed, own + admin, w)
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_a_profile_sees_its_own_pages_in_the_menu_sheet(self):
        """Without the admin: the computer layout's menu sheet on a phone lists the profile's own pages (before only
        an admin got pages there, so a profile reached E-Mail and Kontakte in landscape only)."""
        own, admin = nav_pages()

        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 390, 844, profile=True)
                try:
                    await pg.wait_for_function("typeof PROFILE!=='undefined'&&!!PROFILE", timeout=20000)
                    await pg.evaluate("ADMIN=false;localStorage.setItem('appview','off');APV.apply();"
                                      "document.querySelectorAll('nav button[data-s]').forEach(b=>b.hidden=false);$('mmenu').click()")
                    listed = await pg.evaluate("[...$('madmin').querySelectorAll('button')].map(b=>b.dataset.s)")
                    self.assertEqual(listed, own)
                    for s in admin:
                        self.assertNotIn(s, listed)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
