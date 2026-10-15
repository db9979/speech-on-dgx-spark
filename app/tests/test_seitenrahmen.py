"""Ein Rahmen für alle Seiten mit Seitenleiste (Dominik 2026-10-14 „Alle Reiter wie Technik framen, hüpft bei den
anderen nach links und nutzt nicht den ganzen Platz“). Before, only Technik widened the page (body.intech, 1800 px)
while the other Zustand tabs stayed at 1240 px in the middle: switching tabs moved the menu column and the content.
Einstellungen (1040 px), Funktionen (1320 px) and Ich (1040 px, its own centre) each had their own frame too.
Now one frame (--frame, --sidecol, --sidegap in app.css) holds every page with a side menu: the menu column and the
content start at the same place and have the same width on every tab, on phones nothing is wider than the screen."""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import async_playwright, browser_ok, chromium

helpers.start()

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")
ZUSTAND = ("mon", "live", "test", "logs", "verb", "usage", "models", "tech")
OTHERS = ("feat", "who", "route", "int", "prof", "apps", "cfg")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_one_frame_defined_once(self):
        css = read("app.css")
        self.assertEqual(len(re.findall(r"--frame:", css)), 1)
        self.assertIn("body.adm main{max-width:var(--frame)}", css)
        # no page widens or narrows the frame on its own any more (Technik did, so the others jumped)
        for name in ("app.css", "technik.css", "live.css", "weiche.css"):
            self.assertIsNone(re.search(r"body\.[\w.:()]+ main\{max-width:\d", read(name)), name)
            self.assertNotIn("intech", read(name), name)
        self.assertNotIn("intech", read("js", "base.js"))
        self.assertIsNone(re.search(r"#cfg \.cfgwrap[^{]*\{max-width:\d", css))
        self.assertIsNone(re.search(r"#profmodal \.mecard\{width:min\(\d", css))

    def test_every_side_menu_uses_the_same_column(self):
        css = read("app.css")
        self.assertIn("main.hassub{display:grid;grid-template-columns:var(--sidecol) minmax(0,1fr);column-gap:var(--sidegap)", css)
        self.assertIn("#cfg .cfgwrap{max-width:none;grid-template-columns:var(--sidecol) minmax(0,1fr);gap:var(--sidegap)}", css)
        self.assertIn("body.adm #profmodal .mewrap{grid-template-columns:var(--sidecol) minmax(0,1fr);gap:var(--sidegap)}", css)
        self.assertIsNone(re.search(r"main\.hassub\{grid-template-columns:\d", css))


# where the menu column and the page sit: [menu left, menu width, content left, content width]
FRAME = """(()=>{const me=document.getElementById('profmodal').style.display==='grid';
const nav=me?document.querySelector('#profmodal .menav'):(document.querySelector('#cfg.on .cfgwrap:not(.featmode)>.cfgnav')||document.getElementById('subnav'));
const body=me?document.querySelector('#profmodal .mebody'):(document.querySelector('#cfg.on .cfgwrap>div:not(.cfgnav)')||document.querySelector('main>section.on'));
const r=e=>{const b=e.getBoundingClientRect();return[Math.round(b.left),Math.round(b.width)]};return[...r(nav),...r(body)]})()"""
WIDE = "document.documentElement.scrollWidth<=document.documentElement.clientWidth"


class Page:
    """Signs in as admin and opens pages; the browser classes below share it."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    async def _until(self, pg, expr):
        """The strict CSP refuses wait_for_function: poll (20 s, a GitHub runner is slow)."""
        for _ in range(200):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass   # the page is just loading again
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    async def _open(self, p, w, h):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": w, "height": h}, locale="de-DE")
        pg = await ctx.new_page()
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        pg.on("console", lambda m: self.errors.append(m.text) if "Content Security Policy" in m.text else None)
        base = f"http://127.0.0.1:{self.port}"
        # the first-start wizard would lie over the page: this browser sees the setup as done (nothing is stored)
        await pg.route("**/api/setup", lambda route: route.fulfill(json={"done": True})
                       if route.request.method == "GET" else route.continue_())
        await pg.goto(base + "/")
        self.assertEqual((await pg.request.post(base + "/api/login", data={"password": "secret-admin"})).status, 200)
        await pg.goto(base + "/")
        await self._until(pg, "typeof ADMIN!=='undefined'&&ADMIN===true&&document.body.classList.contains('adm')")
        return br, pg

    async def _go(self, pg, s):
        if s == "me":
            await pg.evaluate("openMe()")
            await self._until(pg, "document.getElementById('profmodal').style.display==='grid'")
        else:
            await pg.evaluate(f"goSec('{s}')")
            await self._until(pg, f"!!document.querySelector('main>section#{'cfg' if s == 'feat' else s}.on')")
        await self._until(pg, "!!window.lzIdle&&lzIdle()")



@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(Page, unittest.TestCase):
    async def _computer(self, w):
        async with async_playwright() as p:
            br, pg = await self._open(p, w, 900)
            try:
                frames = {}
                for s in ZUSTAND + OTHERS + ("me",):
                    await self._go(pg, s)
                    frames[s] = await pg.evaluate(FRAME)
                    self.assertTrue(await pg.evaluate(WIDE), f"{w}: {s}")
                    if s == "me":
                        await pg.evaluate("closeProf()")
                ref = frames["tech"]
                # every Zustand tab exactly like Technik: same menu, same content box (before: Technik 1451 px wide, the rest 1018)
                for s in ZUSTAND:
                    self.assertEqual(frames[s], ref, f"{w}: {s} vs Technik")
                # the other pages with a side menu start in the same place with the same width
                for s in OTHERS + ("me",):
                    self.assertEqual(frames[s][:3], ref[:3], f"{w}: {s} menu and content start")
                    self.assertLessEqual(abs(frames[s][3] - ref[3]), 20, f"{w}: {s} content width")
                # the content takes the room beside the menu (before: 1240 px in the middle of a wide screen)
                self.assertGreater(ref[3], w - 232 - 220 - 24 - 2 * 18 - 40, f"{w}: content uses the width")
                self.assertEqual(self.errors, [])
            finally:
                await br.close()

    async def _phone(self, w, h):
        async with async_playwright() as p:
            br, pg = await self._open(p, w, h)
            try:
                for s in ZUSTAND + OTHERS + ("me",):
                    await self._go(pg, s)
                    self.assertTrue(await pg.evaluate(WIDE), f"{w}: {s}")
                    if s == "me":
                        await pg.evaluate("closeProf()")
                self.assertEqual(self.errors, [])
            finally:
                await br.close()

    def test_same_frame_on_every_tab_on_computers(self):
        for w in (1920, 1280):
            asyncio.run(self._computer(w))

    def test_nothing_wider_than_a_phone(self):
        for w, h in ((390, 844), (320, 700)):
            asyncio.run(self._phone(w, h))


# every target box of the Live picture: its rect and whether its two lines stay inside it (and do not touch the next box)
BOXES = """(()=>{const out=[];document.querySelectorAll('#lvflow svg g.node[data-node]').forEach(g=>{const id=g.dataset.node;
if(!id.startsWith('t_'))return;const r=g.querySelector('rect').getBBox(),a=g.querySelector('text.a').getBBox(),b=g.querySelector('text.b').getBBox();
out.push({id,h:r.height,y:r.y,top:a.y-r.y,bottom:r.y+r.height-(b.y+b.height),right:Math.max(r.x+r.width-(a.x+a.width),r.x+r.width-(b.x+b.width))})});return out})()"""


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class LiveBoxes(Page, unittest.TestCase):
    """Dominik 2026-10-14: in Zustand → Live the boxes under „Dienste und Ziele“ were 22 high once there were 16 of
    them (NAS, Wissensordner …): name and state spilled over the edges, only fullscreen fitted. Now the picture grows
    with the number of targets, every box keeps its two lines inside, long words end in „…“."""

    async def _run(self, w, h):
        async with async_playwright() as p:
            br, pg = await self._open(p, w, h)
            try:
                async def many(route):
                    r = await route.fetch()
                    d = await r.json()
                    # home network ones: quiet internet targets would fold into „+ N ruhig“ depending on what else runs
                    lan = [{"id": f"t_l{i}", "name": f"Dienst im Heimnetz {i} mit einem langen Namen", "sub": "3 Verbindungen · 2 Profile · Sicherung heute fertig", "zone": "lan"} for i in range(14)]
                    d["targets"] = lan + d.get("targets", [])
                    await route.fulfill(response=r, json=d)
                await pg.route("**/api/admin/live", many)
                await self._go(pg, "live")
                await self._until(pg, "document.querySelectorAll('#lvflow svg g.node[data-node^=t_]').length>=14")
                boxes = await pg.evaluate(BOXES)
                self.assertGreaterEqual(len(boxes), 14)
                ys = sorted(b["y"] + b["h"] for b in boxes)
                for b in boxes:
                    self.assertGreaterEqual(b["h"], 40, b)
                    self.assertGreaterEqual(b["top"], 0, b)       # the name starts inside the box
                    self.assertGreaterEqual(b["bottom"], 0, b)    # the state ends inside the box
                    self.assertGreaterEqual(b["right"], 4, b)     # long words end in „…“ before the edge
                tops = sorted(b["y"] for b in boxes)
                self.assertTrue(all(tops[i + 1] >= ys[i] for i in range(len(tops) - 1)), "boxes overlap")
                self.assertTrue(await pg.evaluate(WIDE), f"{w}: Live")
                await pg.screenshot(path=os.path.join(os.environ.get("SPEECH_SPARK_SHOTS", helpers.TMP), f"live-ziele-{w}.png"), full_page=True)
                self.assertEqual(self.errors, [])
            finally:
                await br.close()

    def test_target_boxes_keep_their_text(self):
        import json as _json
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = _json.load(f)
        was = dict(c.get("logs", {}))
        c.setdefault("logs", {}).update(live=True)
        helpers.write_config(c)

        def undo():
            with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
                cb = _json.load(f)
            cb["logs"] = was
            helpers.write_config(cb)
        self.addCleanup(undo)
        for w, h in ((1280, 900), (1920, 1000)):
            asyncio.run(self._run(w, h))
