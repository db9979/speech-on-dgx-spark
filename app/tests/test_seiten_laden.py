"""Seiten sichtbar laden (plan plaene/seiten-laden.md, Dominik 12.10.2026): while a page loads it says so. A bar on
top after a click, placeholders in a box until its data is there, „dauert länger als sonst …“, the error in the box
with „Noch einmal“, at most 30 s for a read, a band when the Spark is gone; Ich loads its boxes side by side, and one
failing box no longer signs the profile out. Slow reads are one line in Zustand → Logs → Diagnose. Static and API
checks run everywhere, the browser checks where Playwright and Chromium exist; the browser checks wait for states
(a route held until the test lets it go), never for the clock."""
import asyncio
import json
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import PAGE_READY, async_playwright, browser_ok, chromium

helpers.start()
import logfilter  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_loaded_after_base_before_the_pages(self):
        scripts = re.findall(r'<script src="/static/js/([\w]+)\.js"', read("index.html"))
        self.assertEqual(scripts.index("laden"), scripts.index("base") + 1)
        for page in ("me", "extras", "who", "weiche", "logs", "start"):
            self.assertLess(scripts.index("laden"), scripts.index(page), page)

    def test_api_goes_through_the_loading_fetch(self):
        js = read("js", "base.js")
        body = js[js.index("const api=async"):js.index("const apiTry=")]
        self.assertIn("(window.lzFetch||fetch)(p,", body)
        self.assertNotRegex(body, r"[^.\w]fetch\(p,")

    def test_built_with_text_only_and_nothing_stored(self):
        js = read("js", "laden.js")
        self.assertNotIn("innerHTML", js)
        self.assertNotRegex(js, r"\bon(click|change|input)\s*=")
        self.assertNotRegex(js, r"localStorage|sessionStorage|indexedDB")
        self.assertNotIn("eval(", js)
        # the band and the error offer buttons only through data-on (strict CSP)
        self.assertIn("dataset.on='lzAgain'", js)
        self.assertIn("dataset.on='lzPing'", js)

    def test_every_text_in_both_languages(self):
        js = read("js", "laden.js")
        for de in ("wird aktualisiert …", "dauert länger als sonst …", "Noch einmal", "Spark antwortet nicht.", "Jetzt versuchen", "Seite lädt"):
            self.assertRegex(js, r"t\('" + re.escape(de) + r"','[^']+'\)", de)
        self.assertRegex(js, r"t\(`Neuer Versuch in \$\{left\} s …`,`[^`]+`\)")

    def test_a_box_stops_waiting_after_30_seconds_without_cutting_the_request(self):
        js = read("js", "laden.js")
        self.assertIn("wait:30e3", js)
        self.assertRegex(js, r"const t3=setTimeout\(.*lzErr\(box,at,o,lzTimeout\(\)\)\},LZ\.wait\)")
        # nothing is aborted: a late answer still fills the box (a cut request was an error on a busy runner)
        body = js[js.index("window.lzFetch="):js.index("// ---------------------------------------------------------------- the band")]
        self.assertNotIn("AbortController", body)
        self.assertNotIn(".abort(", body)

    def test_ich_loads_side_by_side_and_signs_out_only_on_401(self):
        js = read("js", "me.js")
        body = js[js.index("async function meLoad"):js.index("window.openMe=openMe")]
        self.assertNotIn("await showFacts();await showDocs()", body)
        self.assertIn("lzPool(", body)
        self.assertIn("auth:true", body)
        self.assertIn("e.status===401)out=true", body)
        self.assertNotIn("catch{setProfile(null)", body)
        for box in ("factbox", "docbox", "mailbox", "habox", "secbox", "logbox"):
            self.assertIn(f"['{box}',", body)
        # the calendar settings moved to the page Kalender (V01.0.805) and load there the same way
        self.assertIn("lzb(b,showCal,{auth:true})", read("js", "kalender.js"))
        ex = read("js", "extras.js")
        self.assertIn("function extrasJobs()", ex)
        self.assertNotIn("window[", ex[ex.index("function extrasJobs"):ex.index("async function showExtras")])

    def test_browser_tests_wait_for_the_load_not_for_a_pause(self):
        """After goSec('feat'|'cfg') a browser test waits for lzIdle() (every box loaded), never only for a fixed
        pause: a switch flipped before the settings are there is set back by them (test_voraussetzungen_mit_einschalten
        was red on main 2026-10-12)."""
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("test_ui_browser.py", "test_einstellungen_neu.py"):
            lines = open(os.path.join(here, name), encoding="utf-8").read().splitlines()
            for i, line in enumerate(lines):
                if re.search(r"""evaluate\("goSec\('(feat|cfg)'\)"\)$""", line.strip()):
                    nxt = lines[i + 1].strip()
                    self.assertNotRegex(nxt, r"^await pg\.wait_for_timeout\(", f"{name}:{i + 2}")

    def test_pages_load_through_the_box(self):
        js = read("js", "base.js")
        body = js[js.index("function showSec(s)"):js.index("const NARROW=")]
        for f in ("loadCfg", "loadProf", "loadLogs", "loadInt", "loadWho", "loadWeiche"):
            self.assertNotRegex(body, rf"[^,\w]{f}\(\)", f)    # never called bare, always through lzb(box, f, …)
            self.assertRegex(body, rf"lzb\([^;]+,{f}[,)]", f)
        self.assertIn("lzSkelIn($('lvroot')", body)

    def test_chains_load_side_by_side(self):
        self.assertIn("Promise.all([api('/api/config')", read("js", "admin.js"))
        who = read("js", "who.js")
        body = who[who.index("async function loadWho"):who.index("function whoGuest")]
        self.assertNotIn("await loadCfg()", body)

    def test_calm_for_those_who_ask_for_it(self):
        css = read("app.css")
        self.assertRegex(css, r"@media\(prefers-reduced-motion:reduce\)\{#lzbar i\{animation:none[^}]*\}\.lz-sk i\{animation:none\}\}")
        self.assertIn(".lz-err p{margin:0;flex-basis:100%;overflow-wrap:anywhere}", css)

    def test_slow_area_in_diagnose(self):
        self.assertIn("seite", logfilter.FILTERS)
        self.assertRegex(read("js", "logs.js"), r"seite:\[t\('Seite lädt','Page loading'\)")


class SlowReads(unittest.TestCase):
    def setUp(self):
        panel._slow_said.clear()

    def test_only_slow_reads_once_a_minute(self):
        self.assertIsNone(panel.slow_read("GET", "/api/status", 0.4, 100.0))
        self.assertIsNone(panel.slow_read("POST", "/api/chat", 9.0, 100.0))
        self.assertIsNone(panel.slow_read("GET", "/static/app.css", 9.0, 100.0))
        self.assertEqual(panel.slow_read("GET", "/api/profile/calendar", 4.24, 100.0), "seite: slow GET /api/profile/calendar 4.2 s")
        self.assertIsNone(panel.slow_read("GET", "/api/profile/calendar", 5.0, 130.0))   # same route within a minute
        self.assertIsNotNone(panel.slow_read("GET", "/api/profile/calendar", 5.0, 161.0))
        self.assertIsNotNone(panel.slow_read("GET", "/api/profile/mail", 2.0, 130.0))

    def test_the_line_names_the_route_never_the_query_or_ids(self):
        routes, old = [], panel.slow_read
        panel.slow_read = lambda m, r, took, now: routes.append(r)
        try:
            c = TestClient(panel.app)
            c.post("/api/login", json={"password": "secret-admin"})
            c.get("/api/admin/traces/abc123secret?q=geheim")
        finally:
            panel.slow_read = old
        self.assertIn("/api/admin/traces/{tid}", routes)
        self.assertFalse(any("abc123secret" in x or "geheim" in x for x in routes))

    def test_diagnose_sorts_and_marks_the_line(self):
        line = "seite: slow GET /api/profile/calendar 4.2 s"
        self.assertEqual(next(k for k, rx in logfilter._AREAS if rx.search(line)), "seite")
        self.assertTrue(logfilter.WARN.search(line))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(memory=True)
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Ladeseite", "4711")
        except Exception:
            pass

    async def page(self, p, w=1280, h=900):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE", bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/profile/login", data={"name": "Ladeseite", "pin": "4711"})).status, 200)
        await pg.goto(base + "/")
        await pg.wait_for_function(PAGE_READY)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        await pg.evaluate("CAL_ON=true;LZ.show=0")
        return br, pg, errors

    @staticmethod
    async def hold(pg, pattern):
        """Holds every request to pattern until the returned event is set, then answers it normally."""
        go = asyncio.Event()

        async def later(route):
            await go.wait()
            await route.continue_()
        await pg.route(pattern, later)
        return go

    def test_box_shows_placeholders_until_its_data_is_there(self):
        async def run():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                try:
                    go = await self.hold(pg, "**/api/profile/security")
                    await pg.evaluate("openMe('secbox');0")   # not awaited: the page goes on loading
                    await pg.wait_for_selector("#secbox[aria-busy=true] .lz-sk")
                    # the other boxes do not wait for this one any more
                    await pg.wait_for_function("document.getElementById('factbox').dataset.lzok==='1'")
                    # what the browser tests wait for after opening a page: not idle while one box still loads
                    self.assertFalse(await pg.evaluate("lzIdle()"))
                    go.set()
                    await pg.wait_for_function("!document.querySelector('#secbox .lz-sk')&&!document.getElementById('secbox').hasAttribute('aria-busy')")
                    await pg.wait_for_function("lzIdle()")
                    # opened again: the old data stays, dimmed, with „wird aktualisiert …“
                    go2 = await self.hold(pg, "**/api/profile/security")
                    await pg.evaluate("openMe('secbox');0")   # not awaited: the page goes on loading
                    await pg.wait_for_selector("#secbox.lz-stale .lz-chip")
                    self.assertEqual(await pg.evaluate("document.querySelector('#secbox .lz-chip').textContent"), "wird aktualisiert …")
                    go2.set()
                    await pg.wait_for_function("!document.querySelector('#secbox.lz-stale')")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(run())

    def test_error_stays_in_its_box_and_tries_again(self):
        async def run():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                try:
                    fail = {"on": True}

                    async def cal(route):
                        if fail["on"]:
                            await route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "kaputt"}))
                        else:
                            await route.continue_()
                    await pg.route("**/api/profile/security", cal)
                    await pg.evaluate("openMe('secbox');0")   # not awaited: the page goes on loading
                    await pg.wait_for_selector("#secbox .lz-err button[data-on=lzAgain]")
                    # still signed in: the profile's page, not the login (before: any error looked like being signed out)
                    self.assertTrue(await pg.evaluate("!!PROFILE&&document.getElementById('profhead').textContent==='Ladeseite'"))
                    self.assertIn("kaputt", await pg.evaluate("document.querySelector('#secbox .lz-err p').textContent"))
                    fail["on"] = False
                    await pg.click("#secbox .lz-err button[data-on=lzAgain]")
                    await pg.wait_for_function("!document.querySelector('#secbox .lz-err')&&document.getElementById('secbox').dataset.lzok==='1'")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(run())

    def test_slow_then_timeout(self):
        async def run():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                try:
                    go = await self.hold(pg, "**/api/profile/security")
                    await pg.evaluate("LZ.slow=50;LZ.wait=400")
                    await pg.evaluate("openMe('secbox');0")   # not awaited: the page goes on loading
                    await pg.wait_for_selector("#secbox.lz-slow .lz-chip.w")
                    await pg.wait_for_selector("#secbox .lz-err")
                    self.assertIn("30 Sekunden", await pg.evaluate("document.querySelector('#secbox .lz-err p').textContent"))
                    self.assertFalse(await pg.evaluate("!!document.querySelector('#secbox.lz-slow')"))
                    # the answer comes late after all: it fills the box and the error goes
                    go.set()
                    await pg.wait_for_function("!document.querySelector('#secbox .lz-err')&&document.getElementById('secbox').dataset.lzok==='1'")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(run())

    def test_band_when_the_spark_is_gone_and_back(self):
        async def run():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                try:
                    await pg.route("**/api/**", lambda r: r.abort("failed"))   # the whole Spark is gone
                    await pg.evaluate("openMe('secbox');0")   # not awaited: the page goes on loading
                    await pg.wait_for_selector("#lzband:not([hidden])")
                    self.assertIn("Spark antwortet nicht.", await pg.evaluate("document.getElementById('lzband').textContent"))
                    # back, but only the button's probe may bring the band away: a poll that answers first would
                    # hide the band before the click (flaky in the full run); after the probe everything goes through
                    back = {"pinged": False}

                    async def only_ping(route):
                        if "/api/whoami" in route.request.url:
                            back["pinged"] = True
                        if back["pinged"]:
                            await route.continue_()
                        else:
                            await route.abort("failed")
                    await pg.unroute("**/api/**")
                    await pg.route("**/api/**", only_ping)
                    await pg.click("#lzband button[data-on=lzPing]")
                    await pg.wait_for_selector("#lzband", state="hidden")
                    await pg.wait_for_function("document.getElementById('secbox').dataset.lzok==='1'")
                    self.assertTrue(back["pinged"])
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(run())

    def test_bar_after_a_click(self):
        async def run():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                try:
                    go = await self.hold(pg, "**/api/profile/security")
                    await pg.click("#navme")
                    await pg.wait_for_selector("#lzbar:not([hidden])")
                    go.set()
                    await pg.wait_for_selector("#lzbar", state="hidden")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(run())

    def test_states_fit_on_small_phones(self):
        async def run():
            async with async_playwright() as p:
                for w, h in ((390, 844), (320, 640)):
                    br, pg, errors = await self.page(p, w, h)
                    try:
                        state = {"fail": True}
                        go = asyncio.Event()

                        async def cal(route):
                            if state["fail"]:
                                await route.fulfill(status=500, content_type="application/json",
                                                    body=json.dumps({"detail": "Die Sicherheit " + "x" * 200 + " antwortet nicht"}))
                            else:
                                await go.wait()
                                await route.continue_()
                        await pg.route("**/api/profile/security", cal)
                        await pg.evaluate("LZ.slow=50")
                        await pg.evaluate("openMe('secbox');0")   # not awaited: the page goes on loading
                        await pg.wait_for_selector("#secbox .lz-err")
                        await self.fits(pg, f"{w} Fehler")
                        state["fail"] = False
                        await pg.click("#secbox .lz-err button[data-on=lzAgain]")
                        await pg.wait_for_selector("#secbox .lz-chip.w")
                        await pg.wait_for_selector("#secbox .lz-sk")
                        await self.fits(pg, f"{w} dauert länger")
                        go.set()
                        await pg.wait_for_function("document.getElementById('secbox').dataset.lzok==='1'")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(run())

    async def fits(self, pg, what):
        over = await pg.evaluate("(()=>{const b=document.querySelector('#profmodal .mebody');return b?b.scrollWidth-b.clientWidth:0})()")
        self.assertLessEqual(over, 0, what)
        self.assertLessEqual(await pg.evaluate("document.scrollingElement.scrollWidth-document.scrollingElement.clientWidth"), 0, what)


class StartwaechterStatic(unittest.TestCase):
    """Start-Wächter (Dominik 16.10.2026: after updates the page stood at „Zustand wird geladen …“ for good)."""

    def test_guard_loads_first_and_start_reports_to_it(self):
        html = read("index.html")
        first = re.search(r'<script src="/static/js/([a-z0-9\-]+)\.js"', html).group(1)
        self.assertEqual(first, "theme")   # first of all scripts: it also sees base.js or start.js missing
        self.assertLess(html.index("/static/js/theme.js"), html.index("</head>"))
        st, th = read("js", "start.js"), read("js", "theme.js")
        self.assertEqual(st.count("startPage().then("), 1)
        self.assertIn("sparkBootDone", st)
        self.assertIn("sparkBootFail", st)
        for name in ("window.sparkBootDone=", "window.sparkBootFail=", 'addEventListener("error"', 'addEventListener("load"'):
            self.assertIn(name, th)
        # no answer from the Spark: never an invented admin page
        self.assertNotIn("{admin:true}", st)
        self.assertNotRegex(st, r"\(async\(\)=>\{let who=")


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Startwaechter(unittest.TestCase):
    """A page loaded while the Spark restarts: a script or the first who-am-I gets the proxy's 502. The page shows the
    band and loads itself again once the Spark answers (waits for states, never for a fixed time)."""

    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    def broken_start(self, pattern):
        async def run():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                # the service worker would answer the page's requests itself, past the test's routes
                ctx = await br.new_context(viewport={"width": 390, "height": 844}, locale="de-DE",
                                           service_workers="block", bypass_csp=True)
                pg = await ctx.new_page()
                base = f"http://127.0.0.1:{self.port}"
                await pg.goto(base + "/")
                await pg.wait_for_function(PAGE_READY)
                down = {"on": True}

                async def proxy(route):
                    if down["on"]:
                        await route.fulfill(status=502, content_type="text/html", body="<html>502 Bad Gateway</html>")
                    else:
                        await route.continue_()
                await pg.route(pattern, proxy)
                await pg.reload()
                await pg.wait_for_selector("#bootband:not([hidden])")
                self.assertIn("nicht vollständig", await pg.text_content("#bootband"))
                # before: no version, no menu, Zustand's placeholders for good; now nothing invented meanwhile
                self.assertEqual(await pg.text_content("#ver"), "")
                down["on"] = False   # the Spark is back: the page loads itself again, all of it
                await pg.wait_for_function(PAGE_READY + "&&!document.getElementById('bootband')", timeout=20000)
                self.assertIsNone(await pg.evaluate("sessionStorage.getItem('boottry')"))
                await br.close()
        asyncio.run(run())

    def test_a_script_missing(self):
        self.broken_start("**/static/js/me.js*")

    def test_no_answer_from_whoami(self):
        self.broken_start("**/api/whoami")


if __name__ == "__main__":
    unittest.main()
