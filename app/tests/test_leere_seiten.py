"""A page whose function is off says so (code review 2026-11-11, point 6): Mappen, Wissensbuch, Dungeon-Master and
Kontakte showed a lasting „Lade …“ (or nothing) when someone reached them by a link while the admin had the function
off. Each now shows one sentence with the way to its switch (base.js ausSatz, a jump link like every way); and the
footer stands at the bottom of a phone's window; Ich → Überblick is no copy of the menu; a finger hits every control on a
phone; every page of one's own things has the same head as the other pages (point 9). Static
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

    def test_every_own_page_has_the_same_head(self):
        """Code review 2026-11-11, point 9: Kalender, E-Mail, Listen, Kontakte … began with tabs in a card, without a
        title; on a phone they had no title and no way back, and the bar below marked „Heute“ or nothing. Now the
        title stands above the page on a computer (#phead, from the menu entry, text only) and in the app bar on a
        phone (with the way back to where one came from, never both), the bar below marks a tab the person has, and
        a page that fills the window still does not scroll."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 800, profile=True)
                try:
                    for seite, titel in (("kontakte", "Kontakte"), ("mappen", "Mappen")):
                        await pg.evaluate(f"goSec('{seite}')")
                        await pg.wait_for_function("t=>document.getElementById('pheadt').textContent===t", arg=titel, timeout=10000)
                        k = await pg.evaluate("""(()=>{const ph=document.getElementById('phead'),r=ph.getBoundingClientRect(),
                          s=document.querySelector('main>section.on').getBoundingClientRect();
                          return {da:!ph.hidden&&r.height>0,ueber:r.bottom<=s.top+1,satz:getComputedStyle(document.getElementById('pheadi')).display,
                                  rollt:document.documentElement.scrollHeight-innerHeight,kinder:document.getElementById('pheadt').children.length}})()""")
                        self.assertEqual((k["da"], k["ueber"], k["satz"], k["kinder"]), (True, True, "none", 0), seite)
                        self.assertLessEqual(k["rollt"], 1, seite + ": the title must not push a full page out of the window")
                    await pg.evaluate("goSec('chat')")
                    self.assertTrue(await pg.evaluate("document.getElementById('phead').hidden"))
                    await pg.evaluate("goSec('logs')")       # a page of a group keeps its title and its sentence
                    self.assertEqual(await pg.evaluate("[document.getElementById('pheadt').textContent,document.getElementById('phead').classList.contains('one')]"), ["Logs", False])
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
                kopf = """(()=>{const b=document.getElementById('apbar'),on=document.querySelector('#aptabs button.on');
                  return {titel:b.hidden?'':document.getElementById('aptitle').textContent,zurueck:document.querySelector('#apback span').textContent,
                          tab:on&&!on.hidden?on.dataset.tab:'',gross:getComputedStyle(document.getElementById('phead')).display}})()"""
                br, pg, errors = await self.page(p, 390, 760, profile=True)
                try:
                    await pg.wait_for_function("document.body.classList.contains('appview')", timeout=10000)
                    await pg.evaluate("APV.tab('today')")
                    await pg.evaluate("goSec('kontakte')")
                    self.assertEqual(await pg.evaluate(kopf), {"titel": "Kontakte", "zurueck": "Heute", "tab": "today", "gross": "none"})
                    await pg.click("#apback")
                    await pg.wait_for_function("document.body.classList.contains('appage')&&document.getElementById('aptoday').classList.contains('on')", timeout=10000)
                    await pg.evaluate("APV.tab('manage')")   # from „Verwalten“ (its search): back leads there, and it stays marked
                    await pg.evaluate("goSec('mappen')")
                    self.assertEqual(await pg.evaluate(kopf), {"titel": "Mappen", "zurueck": "Spark verwalten", "tab": "manage", "gross": "none"})
                    await pg.click("#apback")
                    await pg.wait_for_function("document.body.classList.contains('appage')&&document.getElementById('apmanage').classList.contains('on')", timeout=10000)
                    # the Dungeon-Master fills the phone's window with its own bars: no app bar over it, the tab stays marked
                    await pg.evaluate("goSec('dungeon')")
                    k = await pg.evaluate(kopf)
                    self.assertEqual((k["titel"], k["tab"]), ("", "manage"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
                br, pg, errors = await self.page(p, 390, 760)     # an admin without a profile has no „Heute“
                try:
                    await pg.wait_for_function("document.body.classList.contains('appview')", timeout=10000)
                    await pg.evaluate("goSec('kontakte')")
                    self.assertEqual(await pg.evaluate(kopf), {"titel": "Kontakte", "zurueck": "Spark verwalten", "tab": "manage", "gross": "none"})
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
                    # the last header, however many pages stand under it (one more page there made this red on the first try)
                    self.assertEqual(menu[-1], "Zugang")
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

    def test_a_finger_hits_every_control_on_a_phone(self):
        """Tap areas (code review 2026-11-11, point 6 step 3): on a touch screen nothing to tap on the main pages
        is lower than 40 px, counting the area a rule adds around a small mark (::after). Before: 178 of 271
        controls on Funktionen were lower (the „more“ arrow 22 px, a switch 20 px). And the filters of Funktionen
        show their whole words."""
        maß = """(()=>{const bad=[];
for(const e of document.querySelectorAll('main button, main a, main select, main summary, main label.tgl, main input:not([type=hidden]):not([type=checkbox])')){
  if(!e.offsetParent)continue;const r=e.getBoundingClientRect();if(r.width<1||r.height<1)continue;
  const a=getComputedStyle(e,'::after');let h=r.height;
  if(a.position==='absolute'&&a.content!=='none')h=r.height-(parseFloat(a.top)||0)-(parseFloat(a.bottom)||0);
  if(h<40)bad.push(e.tagName+'.'+String(e.className)+' '+Math.round(h))}
return bad})()"""
        async def go():
            async with async_playwright() as p:
                exe = test_ruhige_seiten.chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    ctx = await br.new_context(viewport={"width": 390, "height": 760}, locale="de-DE", bypass_csp=True,
                                               has_touch=True, is_mobile=True)
                    pg = await ctx.new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    base = f"http://127.0.0.1:{self.port}"
                    await pg.goto(base + "/")
                    self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
                    self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Ruhig", "pin": "4711"})).status, 200)
                    await pg.goto(base + "/")
                    await pg.wait_for_function("document.body.classList.contains('adm')", timeout=20000)
                    await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                    self.assertTrue(await pg.evaluate("matchMedia('(pointer:coarse)').matches"))
                    for seite, etwas in (("feat", "#pane-feat .fexp"), ("mon", "#mon button"), ("cfg", "#cfg button"),
                                         ("offen", "#offen button"), ("cal", "#cal button"), ("finden", "#finden button")):
                        await pg.evaluate(f"goSec('{seite}')")
                        await pg.wait_for_function(f"!!document.querySelector('{etwas}')&&!!window.lzIdle&&lzIdle()", timeout=20000)
                        self.assertEqual(await pg.evaluate(maß), [], seite)
                    await pg.evaluate("goSec('feat')")
                    await pg.wait_for_function("document.querySelectorAll('.ffilt button').length>3", timeout=20000)
                    self.assertEqual(await pg.evaluate(
                        "[...document.querySelectorAll('.ffilt button')].filter(b=>b.offsetParent&&b.scrollWidth>b.clientWidth+1).length"), 0)
                    self.assertFalse(await pg.evaluate("document.documentElement.scrollWidth>innerWidth"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
