"""Web-App aufräumen (Dominik 2026-11-16: „Web App sieht nicht gut aus … überprüfe alles“, Plan webapp-aufraeumen/plan.md,
Schritt 1): on a phone the conversation's head has four buttons at most (Neu, Verlauf, „● N“, „⋯“) and its title touches
none of them, „⋯“ holds Suchen and Gespräch einstellen; the tab bar has five tabs at most, each name whole, and it lies
inside what one sees (the column is as high as the visible window, not 100dvh, which iOS 26 Safari counts under its
floating bar). Between 761 and 1100 px (iPad upright) the side menu shows symbols only, so Zustand's content keeps room
for its tiles; a computer keeps the side menu with names. Schritt 2: the phone's head counts the notes and what needs
one under Offen in one „● N“ (a sheet with both, no line „Noch offen“ above the conversation there), and a card in the
conversation is small: two buttons and „⋯“ in one row, the rest behind it. Static checks everywhere, the browser where it exists; no
test reads the clock."""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests import test_ruhige_seiten
from tests.test_ui_browser import async_playwright, browser_ok, chromium

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_five_tabs_at_most(self):
        tabs = re.search(r"const TABS=\[(.*?)\];", read("js", "appview.js")).group(1)
        self.assertLessEqual(len(re.findall(r"\['\w+',", tabs)), 5)
        self.assertNotIn("['docs',", tabs)   # Dokumente lives under Ich → Dokumente

    def test_the_conversation_column_follows_the_visible_window(self):
        css = read("app.css")
        self.assertNotIn("body.inchat{height:100dvh", css)
        self.assertEqual(css.count("body.inchat{height:var(--apph,100dvh)"), 2)
        self.assertIn("setProperty('--apph'", read("js", "phone.js"))

    def test_the_rail_width_is_a_token(self):
        self.assertIn("@media (min-width:761px) and (max-width:1100px){:root{--side-w:72px}}", read("tokens.css"))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(memory=True, documents=True, search=True, report=True, vorgaenge=True, reminders=True)
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Ruhig", "4711")
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(report=False)

    page = test_ruhige_seiten.Browser.page

    async def own_page(self, p, w, h, name):
        """A browser signed in as the admin and as the profile name (PIN 4711): this test's cards stay in its own day."""
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": name, "pin": "4711"})).status, 200)
        await pg.goto(base + "/")
        await pg.wait_for_function("document.body.classList.contains('adm')", timeout=20000)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        return br, pg, errors

    def test_phone_head_tabs_and_tablet_room(self):
        head = """(()=>{const bar=document.getElementById('apbar');if(!bar||bar.hidden)return null;
          const bs=[...bar.querySelectorAll('button')].filter(b=>!b.hidden&&b.getClientRects().length);
          const t=document.getElementById('aptitle'),g=document.createRange();g.selectNodeContents(t);const r=g.getBoundingClientRect();
          const hit=bs.filter(b=>{const q=b.getBoundingClientRect();return q.left<r.right&&q.right>r.left&&q.top<r.bottom&&q.bottom>r.top}).map(b=>b.dataset.ap||b.id);
          return {n:bs.length,hit,more:!!bar.querySelector('[data-ap=more]'),find:!!bar.querySelector('[data-ap=find]')}})()"""
        tabs = """(()=>{const bs=[...document.querySelectorAll('#aptabs button')].filter(b=>!b.hidden&&b.getClientRects().length);
          const cut=bs.filter(b=>{const s=b.querySelector('span');return s.scrollWidth>s.clientWidth+1}).map(b=>b.dataset.tab);
          const r=document.getElementById('aptabs').getBoundingClientRect();
          return {n:bs.length,cut,bottom:r.bottom,h:innerHeight,body:document.body.getBoundingClientRect().height}})()"""

        async def go():
            async with async_playwright() as p:
                for w, h in ((390, 844), (320, 640)):
                    br, pg, errors = await self.page(p, w, h, profile=True)
                    try:
                        await pg.wait_for_function("typeof PROFILE!=='undefined'&&!!PROFILE", timeout=20000)
                        await pg.evaluate("goSec('chat')")
                        await pg.wait_for_function("!document.getElementById('apbar').hidden", timeout=20000)
                        d = await pg.evaluate(head)
                        self.assertLessEqual(d["n"], 4, (w, d))
                        self.assertEqual(d["hit"], [], (w, d))
                        self.assertTrue(d["more"] and not d["find"], (w, d))
                        t = await pg.evaluate(tabs)
                        self.assertLessEqual(t["n"], 5, (w, t))
                        self.assertEqual(t["cut"], [], (w, t))
                        self.assertLessEqual(t["bottom"], t["h"] + 0.5, (w, t))
                        self.assertLessEqual(abs(t["body"] - t["h"]), 1, (w, t))
                        await pg.click("#aptrail [data-ap=more]")
                        await pg.wait_for_selector("#apsheet [data-sa=pal]", state="visible", timeout=10000)
                        rows = await pg.evaluate("[...document.querySelectorAll('#apsheet [data-sa]')].map(b=>b.dataset.sa)")
                        for want in ("pal", "set", "bug"):
                            self.assertIn(want, rows, (w, rows))
                        await pg.click("#apsheet [data-sa=set]")
                        self.assertTrue(await pg.is_hidden("#apsheet"), w)
                        self.assertEqual(errors, [], w)
                    finally:
                        await br.close()
                # the side menu: symbols only on an iPad upright, names on a computer
                for w, h, most, least in ((820, 1180, 80, 0), (1280, 900, 400, 200)):
                    br, pg, errors = await self.page(p, w, h)
                    try:
                        await pg.evaluate("goSec('mon')")
                        await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)
                        side = await pg.evaluate("document.querySelector('header').getBoundingClientRect().width")
                        self.assertLessEqual(side, most, w)
                        self.assertGreaterEqual(side, least, w)
                        if w < 1100:
                            cards = await pg.evaluate("[...document.querySelectorAll('#mon .zcards:not([hidden])>*')].filter(c=>c.getClientRects().length).map(c=>c.getBoundingClientRect().width)")
                            self.assertTrue(cards, w)
                            self.assertGreaterEqual(min(cards), 180, (w, cards))
                            # no entry of the menu shows words beside its symbol, and none sticks out of the rail
                            out = await pg.evaluate("[...document.querySelectorAll('header nav button')].filter(b=>b.getClientRects().length&&b.getBoundingClientRect().right>document.querySelector('header').getBoundingClientRect().right+0.5).length")
                            self.assertEqual(out, 0, w)
                        self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth"), w, w)
                        self.assertEqual(errors, [], w)
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_one_counter_and_small_cards(self):
        import profiles
        import vorgaenge
        try:
            profiles.add_user("Ordnung", "4711")
        except Exception:
            pass   # there from an earlier run of this class
        uid = next(u for u in profiles.user_ids() if (profiles.by_id(u) or {}).get("name") == "Ordnung")
        x, _ = vorgaenge.put(uid, "vorschlag", "ordnung:1", "Regel-Vorschlag: Mails von noreply@example.org",
                             "War in „Rechnungen“, du hast sie nach „Benachrichtigungen“ gelegt. Soll das künftig eine Regel machen?",
                             say=True)
        self.assertIsNotNone(x)
        card = """(()=>{const c=[...document.querySelectorAll('#chatlog .vk')].find(c=>c.dataset.vg===%r);if(!c)return null;
          const bs=[...c.querySelectorAll(':scope>.vk-b>button,:scope>.vk-b>.vk-sp>button')].filter(b=>b.getClientRects().length);
          return {small:c.classList.contains('kompakt'),n:bs.length,spread:(m=>Math.max(...m)-Math.min(...m))(bs.map(b=>{const r=b.getBoundingClientRect();return (r.top+r.bottom)/2})),
                  more:!!c.querySelector('.vk-mehr'),out:c.getBoundingClientRect().right<=innerWidth+0.5}})()""" % x["id"]

        async def go():
            async with async_playwright() as p:
                for w, h in ((390, 844), (1280, 900)):
                    br, pg, errors = await self.own_page(p, w, h, "Ordnung")
                    try:
                        await pg.wait_for_function("typeof PROFILE!=='undefined'&&!!PROFILE", timeout=20000)
                        await pg.evaluate("goSec('chat')")
                        await pg.wait_for_function("typeof VG!=='undefined'&&VG.loaded", timeout=20000)
                        await pg.evaluate("convoLook(true)")
                        await pg.wait_for_function("!!document.querySelector('#chatlog .vk[data-vg=%s]')" % x["id"], timeout=20000)
                        d = await pg.evaluate(card)
                        self.assertTrue(d["small"] and d["more"] and d["out"], (w, d))
                        self.assertLessEqual(d["n"], 3, (w, d))
                        self.assertLess(d["spread"], 12, (w, d))   # one row: the buttons' middles at one height
                        await pg.click("#chatlog .vk[data-vg=%s] .vk-mehr" % x["id"])
                        menu = await pg.evaluate("[...document.querySelectorAll('#chatlog .vk[data-vg=%s] .vk-pop button')].map(b=>b.textContent)" % x["id"])
                        self.assertIn("Auf der Seite Offen", menu, w)
                        if w < 760:
                            self.assertFalse(await pg.evaluate("!!document.getElementById('vgstrip')&&!!document.getElementById('vgstrip').getClientRects().length"), w)
                            await pg.wait_for_selector("#aptrail [data-ap=offen]", state="visible", timeout=10000)
                            await pg.click("#aptrail [data-ap=offen]")
                            await pg.wait_for_selector("#apsheet [data-sa=vg]", state="visible", timeout=10000)
                            self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#apsheet [data-sa=vg]')].map(b=>b.dataset.id)"), [x["id"]])
                            await pg.click("#apsheet [data-sa=vg]")
                            await pg.wait_for_function("document.querySelector('main>section.on').id==='offen'", timeout=10000)
                        self.assertEqual(errors, [], w)
                    finally:
                        await br.close()
        try:
            asyncio.run(go())
        finally:
            vorgaenge.forget(uid)


if __name__ == "__main__":
    unittest.main()
