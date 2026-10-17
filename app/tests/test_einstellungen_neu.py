"""Einstellungsseiten neu (plaene/einstellungen-neu.md): one page frame for every settings page. The rows of a section
sit in one box (.sgrp), short fixed choices are segment buttons, the save bar floats only while something is unsaved,
and on phones the face no longer covers the switches. Static checks run everywhere, the browser checks where
Playwright and Chromium exist (container, GitHub "Tests"); no test reads the clock."""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_page_frame_is_loaded_after_the_pages(self):
        html = read("index.html")
        self.assertIn('<script src="/static/js/seite.js"></script>', html)
        scripts = re.findall(r'<script src="/static/js/([\w]+)\.js"', html)
        # it groups what guides.js, admin.js and me.js put on the pages, so it comes after them
        for before in ("admin", "me", "guides", "notaus"):
            self.assertLess(scripts.index(before), scripts.index("seite"), before)

    def test_frame_only_changes_the_look(self):
        js = read("js", "seite.js")
        # no new requests, no HTML from data: buttons get their text with textContent
        self.assertNotIn("fetch(", js)
        self.assertNotIn("api(", js)
        self.assertNotRegex(js, r"innerHTML\s*=\s*[^'\"]")
        # lists filled from data (profiles, voices, models) never become segment buttons
        self.assertIn("voice|model", js)
        self.assertIn(".setpane .setrow select", js)

    def test_notaus_key_field_fits_its_row(self):
        # the field was 100 % wide next to its button and pushed it out of the page (V01.0.406)
        html = read("index.html")
        self.assertIn('<div class="ctl full"><input class="wide" id="nakeyname"', html)

    def test_settings_are_where_they_belong(self):
        # plaene/einstellungen-anordnung.md: Update and Sicherung are two pages, the traffic light sits on
        # "Auf einen Blick", "Notaus von selbst" under Notaus, the live overview has its own section under Betrieb
        html = read("index.html")
        def pane(p):
            a = html.index(f'id="pane-{p}"')
            b = html.find('<div class="card pane"', a)
            return html[a:b if b > 0 else len(html)]
        self.assertIn('data-p="bak"', html)
        for el in ('id="bakgo"', 'id="offbox"'):
            self.assertIn(el, pane("bak"))
            self.assertNotIn(el, pane("upd"))
        self.assertIn('id="secglance"', pane("start"))
        self.assertNotIn('id="secglance"', pane("sec"))
        sec = pane("sec")
        self.assertLess(sec.index('<h3 class="sec">Notaus</h3>'), sec.index("notaus_auto"))
        self.assertIn('<h3 class="sec">Live-Übersicht</h3>', pane("sysc"))
        # every page of the menu has its symbol
        js = read("js", "seite.js")
        for p in re.findall(r'<button data-p="(\w+)"', html[html.index('id="cfgnav"'):html.index('id="cfgback"')]):
            self.assertRegex(js, rf"\b{p}:\[", p)

    def test_feature_groups_match(self):
        # the Funktionen page (guides.js) and the feature register (features.py, Gesperrte Funktionen, the apps) use the
        # same groups in the same order; the technical switches have their own group (Anordnung, Umzug 2)
        import features
        js = read("js", "guides.js")
        keys = re.findall(r"\['(\w+)','[^']+','[^']+'\]", js[js.index("const GGROUPS"):js.index("const GSECT")])
        self.assertEqual(keys, [g for g, _, _ in features.GROUPS])
        speed = {f.key for f in features.FEATURES if f.group == "speed"}
        self.assertEqual(speed, {"toolthink", "routing", "direct", "hoeren", "ack", "vorab", "einordnung", "einordnungpost", "einordnungtest",
                                 "einordnungrat", "einordnungcheck", "einordnungklage"})
        for k in speed:
            self.assertIn(f"{{id:'{k}',grp:'speed'", js)

    def test_feature_detail_only_moves_rows(self):
        html = read("index.html")
        scripts = re.findall(r'<script src="/static/js/([\w]+)\.js"', html)
        self.assertLess(scripts.index("who"), scripts.index("fdetail"))
        self.assertLess(scripts.index("guides"), scripts.index("fdetail"))
        js = read("js", "fdetail.js")
        # who may use it: the same endpoints as the table, nothing new
        calls = re.findall(r"api\(`?'?(/api/[\w/]+)", js)
        self.assertTrue(calls)
        self.assertEqual({c.rstrip("/") for c in calls}, {"/api/admin/features"})
        self.assertNotRegex(js, r"innerHTML\s*=\s*[^'\"`]")
        self.assertIn("presetMove", read("js", "admin.js"))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Frame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(memory=True, documents=True, search=True, calendar=True, weather=True)
        import panel
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Rahmen", "4711")
        except Exception:
            pass

    async def page(self, p, w, h):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Rahmen", "pin": "4711"})).status, 200)
        await pg.goto(base + "/")
        await pg.wait_for_timeout(800)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        return br, pg, errors

    async def panes(self, pg):
        await pg.evaluate("goSec('cfg')")
        await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)   # the settings are there (laden.js)
        return await pg.evaluate("[...document.querySelectorAll('#cfgnav button[data-p]')].map(b=>b.dataset.p).filter(p=>p!=='feat')")

    async def open_pane(self, pg, p_id):
        await pg.evaluate("goSec('cfg')")
        await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)
        await pg.evaluate(f"document.querySelector('#cfgnav button[data-p={p_id}]').click()")
        await pg.wait_for_timeout(250)

    def test_rows_sit_in_boxes(self):
        """Every visible setting row of a settings page is in a box (or in Erweitert), none floats loose on the page."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                try:
                    for p_id in await self.panes(pg):
                        await self.open_pane(pg, p_id)
                        loose = await pg.evaluate(f"""[...document.querySelectorAll('#pane-{p_id} .setrow')]
                            .filter(r=>r.offsetParent&&!r.closest('.sgrp,details.adv,.sglance')).map(r=>r.textContent.trim().slice(0,40))""")
                        self.assertEqual(loose, [], p_id)
                        boxes = await pg.evaluate(f"document.querySelectorAll('#pane-{p_id} .sgrp').length")
                        self.assertGreater(boxes, 0, p_id)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_segments_follow_the_select(self):
        """Empfindlichkeit under Vorgaben: segment buttons; a click sets the select (and marks the page unsaved),
        setting the value from code moves the buttons; the select itself stays for saving."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                try:
                    await self.open_pane(pg, "talk")
                    await pg.wait_for_timeout(400)
                    sel = await pg.evaluate("(()=>{const s=document.querySelector('#chatdefaults select.segsel');return s&&s.id})()")
                    self.assertTrue(sel, "no segment buttons under Vorgaben")
                    opts = await pg.evaluate(f"[...document.getElementById('{sel}').options].map(o=>o.value)")
                    await pg.evaluate(f"document.getElementById('{sel}').previousElementSibling.querySelectorAll('button')[{len(opts) - 1}].click()")
                    self.assertEqual(await pg.evaluate(f"document.getElementById('{sel}').value"), opts[-1])
                    self.assertTrue(await pg.evaluate("$('pane-talk').classList.contains('dirty')"))
                    self.assertTrue(await pg.evaluate("$('pane-talk').querySelector('.savebar').classList.contains('dirty')"))
                    self.assertTrue(await pg.evaluate("!!$('pane-talk').querySelector('.setrow.dirtyrow')"))
                    await pg.evaluate(f"document.getElementById('{sel}').value='{opts[0]}'")
                    on = await pg.evaluate(f"document.getElementById('{sel}').previousElementSibling.querySelector('button.on').dataset.v")
                    self.assertEqual(on, opts[0])
                    # profile lists (data) stay a select
                    self.assertFalse(await pg.evaluate("$('coadmnotify')&&$('coadmnotify').classList.contains('segsel')"))
                    await pg.evaluate("loadCfg()")
                    await pg.wait_for_timeout(500)
                    self.assertFalse(await pg.evaluate("$('pane-talk').classList.contains('dirty')"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_phone_face_and_title_leave_room(self):
        """Phone (app view): on settings pages the face sits in the top bar, not over a switch or button of the page,
        and the back label never runs into the title."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 390, 844)
                try:
                    for p_id in await self.panes(pg):
                        await self.open_pane(pg, p_id)
                        hit = await pg.evaluate(f"""(()=>{{const f=document.querySelector('#fab .fabface');if(!f||!f.offsetParent)return [];
                            const a=f.getBoundingClientRect();
                            return [...document.querySelectorAll('#pane-{p_id} .tgl,#pane-{p_id} button,#pane-{p_id} input,#pane-{p_id} select')]
                              .filter(e=>e.offsetParent).map(e=>[e,e.getBoundingClientRect()])
                              .filter(([e,b])=>b.width&&b.left<a.right&&b.right>a.left&&b.top<a.bottom&&b.bottom>a.top).map(([e])=>e.id||e.textContent.trim())}})()""")
                        self.assertEqual(hit, [], p_id)
                        clash = await pg.evaluate("""(()=>{const b=$('apback'),t=$('aptitle');if(!b||b.hidden||!t.textContent)return 0;
                            return b.querySelector('span').getBoundingClientRect().right-t.getBoundingClientRect().left})()""")
                        self.assertLessEqual(clash, 0, p_id)
                        await pg.evaluate("$('cfgback').click()")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


    def test_feature_detail_on_the_right(self):
        """Funktionen on a computer: the open function shows on the right with its settings and "Wer darf es", one at a
        time; closing puts the rows back. The preset of "Rückfrage ohne Weckwort" sits there, not under Vorgaben, and
        saving Funktionen keeps it. On a phone the function opens below its line as before."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                try:
                    # the way people get there: Funktionen in the sidebar (no settings menu, the page takes the width)
                    await pg.evaluate("goSec('feat')")
                    await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)
                    self.assertGreater(await pg.evaluate("$('pane-feat').getBoundingClientRect().width"), 700)
                    self.assertTrue(await pg.evaluate("$('pane-feat').classList.contains('fsplit')"))
                    self.assertTrue(await pg.is_visible("#fdet .fdempty"))
                    await pg.evaluate("featOpen($('chat.search').closest('.fitem'),true)")
                    await pg.wait_for_timeout(400)
                    self.assertTrue(await pg.evaluate("$('fdet').contains($('chat.search_url'))"))
                    self.assertTrue(await pg.is_visible("#chat\\.search_url"))
                    self.assertTrue(await pg.evaluate("!!document.querySelector('#fdet .fwho:not([hidden])')"))
                    # a second one replaces the first, which gets its rows back
                    await pg.evaluate("featOpen($('chat.follow_up').closest('.fitem'),true)")
                    await pg.wait_for_timeout(400)
                    self.assertTrue(await pg.evaluate("$('chat.search').closest('.fitem').contains($('chat.search_url'))"))
                    self.assertFalse(await pg.evaluate("$('chat.search').closest('.fitem').classList.contains('open')"))
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#pane-feat .fitem.open').length"), 1)
                    self.assertTrue(await pg.evaluate("$('fdet').contains($('set_chatdefaults_follow'))"))
                    self.assertFalse(await pg.evaluate("$('pane-talk').contains($('set_chatdefaults_echo'))"))
                    opts = await pg.evaluate("[...$('set_chatdefaults_follow').options].map(o=>o.value)")
                    await pg.evaluate(f"const s=$('set_chatdefaults_follow');s.value='{opts[-1]}';s.dispatchEvent(new Event('change',{{bubbles:true}}))")
                    self.assertTrue(await pg.evaluate("$('pane-feat').classList.contains('dirty')"))
                    await pg.evaluate("$('pane-feat').querySelector('.savebtn').click()")
                    await pg.wait_for_timeout(800)
                    cfg = await pg.evaluate("fetch('/api/config').then(r=>r.json())")
                    self.assertEqual(str(cfg["chat"]["defaults"]["follow"]), opts[-1])
                    await pg.evaluate("loadCfg()")
                    await pg.wait_for_timeout(500)
                    # loaded again (twice): still in the detail, once
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#set_chatdefaults_follow').length"), 1)
                    self.assertTrue(await pg.evaluate("$('pane-feat').contains($('set_chatdefaults_follow'))"))
                    await pg.evaluate("document.querySelector('#fdet .fdx').click()")
                    self.assertTrue(await pg.evaluate("$('chat.follow_up').closest('.fitem').contains($('set_chatdefaults_follow'))"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
                br, pg, errors = await self.page(p, 390, 844)
                try:
                    await self.open_pane(pg, "feat")
                    self.assertFalse(await pg.evaluate("$('pane-feat').classList.contains('fsplit')"))
                    await pg.evaluate("featOpen($('chat.search').closest('.fitem'),true)")
                    self.assertTrue(await pg.evaluate("$('chat.search').closest('.fitem').contains($('chat.search_url'))"))
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_who_may_use_it_is_one_line(self):
        """Dominik 2026-10-16 option 1: "Wer darf es" in the function's detail is one line („alle Profile“ and who is
        blocked); the profile chips show only after a tap, once for the function. A chip blocks the profile at once
        (the Spark holds it, the line names it), tapped again it lifts the block. On a computer and on a phone."""
        import features
        import profiles
        me = next(u["id"] for u in profiles._load()["users"] if u["name"] == "Rahmen")
        self.addCleanup(helpers.set_config, deny={})

        def denied():
            return {k for k, v in (features.chat_cfg().get("deny") or {}).items() if me in v}

        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 900), (390, 844)):
                    helpers.set_config(deny={})
                    br, pg, errors = await self.page(p, w, h)
                    try:
                        await self.open_pane(pg, "feat")
                        await pg.evaluate("featOpen($('chat.weather').closest('.fitem'),true)")
                        await pg.wait_for_selector(".fwho:not([hidden]) .fwline")
                        line = await pg.text_content(".fwho:not([hidden]) .fwline")
                        self.assertIn("Wer darf es: alle Profile", line)
                        self.assertNotIn("gesperrt:", line)
                        self.assertFalse(await pg.query_selector(".fwho .fwc"), w)   # the chips only after a tap
                        await pg.click(".fwho:not([hidden]) .fwline .wlink")
                        chip = ".fwho:not([hidden]) .fwc[aria-label^='Wetter – Rahmen']"
                        await pg.wait_for_selector(chip)
                        await pg.click(chip)
                        await pg.wait_for_function("(document.querySelector('.fwho:not([hidden]) .fwblk')||{}).textContent==='gesperrt: Rahmen'",
                                                   timeout=10000)
                        self.assertEqual(denied(), {"weather"}, w)
                        await pg.click(chip)
                        await pg.wait_for_function("!document.querySelector('.fwho:not([hidden]) .fwblk')", timeout=10000)
                        self.assertEqual(denied(), set(), w)
                        await pg.click(".fwho:not([hidden]) .fwline .wlink")     # Fertig: the chips fold away again
                        await pg.wait_for_function("!document.querySelector('.fwho .fwc')", timeout=10000)
                        over = await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                        self.assertLessEqual(over, 1, w)
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_me_is_a_page_with_sections(self):
        """Ich → Gespräch: no tabs, the groups one below the other in boxes, no switch for what the admin releases (it
        works at once), what the admin switched off collected at the bottom; symbols in the column, no "Schließen"."""
        helpers.set_config(routing=True, transit=False, wiki=False)
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                try:
                    await pg.evaluate("openMe('setbox')")
                    await pg.wait_for_selector("#setform .setpane h3.sec")
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#setform .ptabs').length"), 0)
                    heads = await pg.evaluate("[...document.querySelectorAll('#setform .setpane>h3.sec')].filter(h=>h.offsetParent).map(h=>h.textContent)")
                    self.assertEqual(heads[:2], ["Zuhören", "Antwort"])
                    loose = await pg.evaluate("[...document.querySelectorAll('#setform .setrow')].filter(r=>!r.closest('.sgrp')).length")
                    self.assertEqual(loose, 0)
                    # Freigabe vereinfachen (Dominik 2026-10-13): what the admin releases works at once, so Ich has
                    # no switch for it any more (Gezielte Werkzeugwahl, Wikipedia direkt); an empty group stays hidden
                    gone = await pg.evaluate("[!!$('set_setform_route'),!!$('set_setform_wiki_on'),!!$('set_setform_chats_on')]")
                    self.assertEqual(gone, [False, False, False])
                    self.assertFalse(await pg.evaluate("[...document.querySelectorAll('#setform details.mefold')].some(d=>!d.hidden&&!d.querySelector('.setrow'))"))
                    # what the admin switched off stays visible, locked, in the box at the bottom, with its reason
                    locked = await pg.evaluate("[...document.querySelectorAll('#setform .setrow.locked')].map(r=>[!!r.closest('details.melockrows'),!!r.querySelector('em.why'),[...r.querySelectorAll('input,select,textarea')].every(e=>e.disabled)])")
                    self.assertTrue(all(x == [True, True, True] for x in locked), locked)
                    self.assertTrue(await pg.evaluate("[...document.querySelectorAll('#ptabs button[data-t]')].every(b=>b.querySelector('.cic'))"))
                    self.assertFalse(await pg.is_visible("#profclose"))
                    self.assertEqual(await pg.text_content("#mepage"), "Gespräch")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        try:
            asyncio.run(go())
        finally:
            helpers.set_config(routing=False)

    def test_people_list_and_detail_and_app_tiles(self):
        """Personen und Geräte: wide, the open person sits beside the list (with the space for uploads); narrow it
        opens below its line. Apps und Schnittstellen: a tile per app, one opens over the full width, the function
        tiles show their switch."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                try:
                    await pg.evaluate("goSec('prof')")
                    await pg.wait_for_selector("#proflist [data-prow]")
                    self.assertTrue(await pg.evaluate("document.querySelector('#prof .pcard').classList.contains('split')"))
                    await pg.evaluate("document.querySelector('#proflist [data-prow] td').click()")
                    await pg.wait_for_selector("#pside #pdetail .pdet")
                    self.assertTrue(await pg.evaluate("!!$('pside').querySelector('#pquota')"))
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#proflist #pdetail').length"), 0)
                    await pg.evaluate("goSec('apps')")
                    await pg.wait_for_selector(".atile[data-sw] .atstate")
                    n = await pg.evaluate("document.querySelectorAll('#apps .atile').length")
                    self.assertGreaterEqual(n, 8)
                    self.assertFalse(await pg.is_visible("#int-curl"))
                    tall = await pg.evaluate("document.documentElement.scrollHeight")
                    self.assertLess(tall, 1500)   # was about 4000 px
                    await pg.evaluate("$('int-curl').closest('.atile').querySelector('.atbtn').click()")
                    self.assertTrue(await pg.is_visible("#int-curl"))
                    self.assertEqual(await pg.evaluate("document.querySelectorAll('#apps .atile.open').length"), 1)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
                br, pg, errors = await self.page(p, 390, 844)
                try:
                    await pg.evaluate("goSec('prof')")
                    await pg.wait_for_selector("#proflist [data-popen]")
                    await pg.evaluate("document.querySelector('#proflist [data-popen]').click()")
                    await pg.wait_for_selector("#proflist #pdetail .pdet")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

if __name__ == "__main__":
    unittest.main()
