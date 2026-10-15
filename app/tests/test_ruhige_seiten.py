"""Ruhigere Seiten ohne Springen (plaene/ruhige-seiten.md, Dominik 2026-10-14): what the person has open stays open
and in its place. Saving never reloads the page, a reload the page must do comes back to the same place (base.js
placeNow, start.js placeBack), the update shows one calm window (no band, the bar never goes back), open parts stay
open when their box is drawn anew, and Zustand polls only while it is seen. Static checks everywhere, browser checks
where Playwright and Chromium exist; no test reads the clock."""
import asyncio
import os
import re
import time
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_one_way_to_reload(self):
        # the old "versec" (only the main page) is gone; every reload of the page itself goes through verReload
        for f in os.listdir(os.path.join(STATIC, "js")):
            self.assertNotIn("versec", read("js", f), f)
        base = read("js", "base.js")
        self.assertIn("sessionStorage.setItem('place'", base)
        self.assertIn("sessionStorage.getItem('place'", read("js", "start.js"))

    def test_saving_does_not_reload(self):
        base = read("js", "base.js")
        who = base[base.index("async function whoCheck"):base.index("// a page change while saved functions wait")]
        self.assertNotIn("verReload", who)
        self.assertIn("WHO_PENDING=true", who)

    def test_update_window_is_alone(self):
        admin = read("js", "admin.js")
        upd = admin[admin.index("// Update lock"):admin.index("// ---------------------------------------------------------------- previous version")]
        self.assertNotIn("location.reload", upd)
        self.assertNotIn("confirm(", upd)
        self.assertIn("Math.max(ul.max", upd)          # the bar never goes back
        self.assertIn("updBusy()", read("js", "laden.js"))   # no band over the window
        self.assertIn("if(updBusy())return", read("js", "base.js"))   # no "new version" bar either
        self.assertNotIn("$('updprev').onclick=async()=>{if(!confirm", admin)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(memory=True, documents=True, search=True, calendar=True, weather=True)
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Ruhig", "4711")
        except Exception:
            pass

    async def page(self, p, w, h, profile=False):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
        if profile:
            self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Ruhig", "pin": "4711"})).status, 200)
        await pg.goto(base + "/")
        await pg.wait_for_function("document.body.classList.contains('adm')", timeout=20000)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        return br, pg, errors

    async def idle(self, pg):
        await pg.wait_for_function("!!window.lzIdle&&lzIdle()", timeout=20000)

    def test_saving_a_function_keeps_it_open(self):
        """Funktionen: an open function, scrolled down, switched and saved: the page does not reload, the function
        stays open, the scroll stays; the next change of page loads the new menu, at that page."""
        async def go():
            async with async_playwright() as p:
                for w, h in ((1280, 800), (390, 760)):
                    br, pg, errors = await self.page(p, w, h)
                    try:
                        await pg.evaluate("goSec('feat')")
                        await self.idle(pg)
                        await pg.evaluate("window.__same=1;const it=document.querySelector('#pane-feat .fitem[data-sw=\"chat.weather\"]');featOpen(it,true);it.scrollIntoView({block:'center'})")
                        await pg.wait_for_timeout(200)
                        y = await pg.evaluate("Math.round(scrollY)")
                        await pg.evaluate("const s=document.getElementById('chat.weather');s.checked=!s.checked;s.dispatchEvent(new Event('change',{bubbles:true}))")
                        await pg.evaluate("document.querySelector('.savebtn[data-p=feat]').click()")
                        try:
                            await pg.wait_for_function("WHO_PENDING===true", timeout=15000)
                        except Exception:
                            self.fail(await pg.evaluate("document.querySelector('.savebtn[data-p=feat]').nextElementSibling.textContent+' | '+document.getElementById('chat.weather').checked"))
                        await pg.wait_for_timeout(600)
                        self.assertEqual(await pg.evaluate("window.__same"), 1, w)   # no reload
                        self.assertTrue(await pg.evaluate("document.querySelector('#pane-feat .fitem[data-sw=\"chat.weather\"]').classList.contains('open')"), w)
                        self.assertLess(abs(await pg.evaluate("Math.round(scrollY)") - y), 40, w)
                        # the next page: it loads itself once, right there
                        async with pg.expect_navigation():
                            await pg.evaluate("goSec('prof')")
                        await pg.wait_for_function("document.body.classList.contains('adm')", timeout=20000)
                        self.assertTrue(await pg.evaluate("document.getElementById('prof').classList.contains('on')"), w)
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())

    def test_reload_comes_back_to_the_place(self):
        """A reload the page does itself (new version, update finished) comes back to Einstellungen → Update."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 800)
                try:
                    await pg.evaluate("goCfg('upd')")
                    await self.idle(pg)
                    async with pg.expect_navigation():
                        await pg.evaluate("verReload()")
                    await pg.wait_for_function("document.getElementById('pane-upd').classList.contains('on')&&document.getElementById('cfg').classList.contains('on')", timeout=20000)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_update_window_is_calm(self):
        """The update: one window, no band while the panel restarts, the bar never goes back, and at the end one
        reload back at the same place (the progress answers come from the test, not from a real update)."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 800)
                try:
                    await pg.evaluate("goCfg('upd')")
                    await self.idle(pg)
                    steps = {"n": 0}

                    async def progress(route):
                        steps["n"] += 1
                        n = steps["n"]
                        if n in (3, 4, 5):   # the panel restarts: no answer
                            await route.abort()
                            return
                        if n >= 7:
                            await route.fulfill(json={"done": True, "ok": True, "started": 1e10, "version": "V9", "running": False})
                            return
                        await route.fulfill(json={"running": True, "started": 1e10, "now": 1e10 + 30, "timeout": 900,
                                                  "percent": 60 if n < 3 else 20, "text": "Schritt"})
                    await pg.route("**/api/update/progress*", progress)
                    # every other request fails meanwhile, as during a restart
                    await pg.route("**/api/status", lambda r: r.abort())
                    await pg.evaluate("ul.clicked=Date.now();ulShow();window.__w=[];window.__iv=setInterval(()=>__w.push(parseFloat(document.getElementById('ulfill').style.width)||0),100)")
                    await pg.wait_for_function("ul.miss>=2", timeout=20000)
                    await pg.evaluate("for(let i=0;i<3;i++)lzNet(0)")
                    self.assertFalse(await pg.evaluate("!!document.getElementById('lzband')&&!document.getElementById('lzband').hidden"))
                    self.assertFalse(await pg.evaluate("!!document.getElementById('verbanner')"))
                    await pg.wait_for_function("ul.miss===0&&parseFloat(document.getElementById('ulfill').style.width)>0", timeout=20000)
                    seen = await pg.evaluate("__w")
                    self.assertTrue(all(b >= a for a, b in zip(seen, seen[1:])), seen)   # never back
                    self.assertGreaterEqual(max(seen), 60)
                    async with pg.expect_navigation(timeout=30000):
                        pass
                    await pg.wait_for_function("document.getElementById('pane-upd').classList.contains('on')", timeout=20000)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_update_window_ignores_the_last_updates_file(self):
        """Dominik 2026-10-15: in the first seconds of an update the unit runs while the progress file is still the
        one of the update before; its start must not count, or the window says „zu lange“ (102 minutes = the time
        since then) and stops asking. Here: the old file first, then this update's, then done."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 800)
                try:
                    await pg.evaluate("goCfg('upd')")
                    await self.idle(pg)
                    steps = {"n": 0}

                    async def progress(route):
                        steps["n"] += 1
                        n, now = steps["n"], time.time()
                        if n <= 3:      # the last update's file, the new unit already active
                            await route.fulfill(json={"running": True, "started": now - 6120, "now": now, "timeout": 2700,
                                                      "done": True, "ok": True, "text": "Fertig", "percent": 100})
                        elif n <= 5:
                            await route.fulfill(json={"running": True, "started": now - 5, "now": now, "timeout": 2700,
                                                      "percent": 40, "text": "Schritt"})
                        else:
                            await route.fulfill(json={"done": True, "ok": True, "started": now - 60, "version": "V9", "running": False})
                    await pg.route("**/api/update/progress*", progress)
                    # another tab sees an update running with the old file: it starts the clock now, not at the old start
                    await pg.evaluate("ulWatch()")
                    self.assertGreater(await pg.evaluate("ul.clicked"), (time.time() - 60) * 1000)
                    await pg.evaluate("ulStop();ul.clicked=Date.now();ulShow()")
                    await pg.wait_for_function("document.getElementById('ultime').textContent!==''", timeout=20000)
                    self.assertNotIn("zu lange", await pg.evaluate("document.getElementById('updlock').innerText"))
                    self.assertLess(await pg.evaluate("parseInt(document.getElementById('ultime').textContent)"), 5)
                    async with pg.expect_navigation(timeout=30000):
                        pass
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_open_parts_stay_open(self):
        """A part the person opened stays open when its box is drawn anew (a save, a poll)."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 800)
                try:
                    await pg.evaluate("""goSec('prof');const b=document.createElement('div');b.id='ruhigbox';
                        b.innerHTML='<details><summary>Mehr (3)</summary><p>x</p></details>';document.getElementById('prof').prepend(b)""")
                    await pg.click("#ruhigbox summary")
                    await pg.wait_for_timeout(100)
                    await pg.evaluate("document.getElementById('ruhigbox').innerHTML='<details><summary>Mehr (4)</summary><p>y</p></details>'")
                    await pg.wait_for_timeout(100)
                    self.assertTrue(await pg.evaluate("document.querySelector('#ruhigbox details').open"))
                    # closed by hand stays closed, even when drawn with "open"
                    await pg.click("#ruhigbox summary")
                    await pg.wait_for_timeout(100)
                    await pg.evaluate("document.getElementById('ruhigbox').innerHTML='<details open><summary>Mehr (5)</summary><p>z</p></details>'")
                    await pg.wait_for_timeout(100)
                    self.assertFalse(await pg.evaluate("document.querySelector('#ruhigbox details').open"))
                    await pg.evaluate("document.getElementById('ruhigbox').remove()")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())

    def test_status_polls_only_when_seen(self):
        """Zustand asks every 3 s only while it is open; elsewhere at most every 30 s."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 800)
                try:
                    calls = []
                    pg.on("request", lambda r: calls.append(1) if r.url.endswith("/api/status") else None)
                    await pg.evaluate("goSec('prof')")
                    await self.idle(pg)
                    await pg.wait_for_timeout(500)
                    calls.clear()
                    await pg.evaluate("REFRESH_AT=Date.now();for(let i=0;i<5;i++)refresh()")
                    await pg.wait_for_timeout(300)
                    self.assertEqual(calls, [])
                    await pg.evaluate("goSec('mon')")
                    await pg.wait_for_timeout(500)
                    self.assertGreaterEqual(len(calls), 1)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
