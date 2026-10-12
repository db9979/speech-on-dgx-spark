"""Sprung-Links (Dominik 12.10.2026: „bei solchen Meldungen immer direkt Link anbieten“): every hint that names a
place in the panel ("unter Einstellungen → Spark → Betrieb → Logs „Live-Seite“") is a link to that place
(static/js/way.js). The rule stays: this test collects every such way from the panel's texts (scripts, page,
server messages) and checks in a real browser that each step of it is found on the page, so a new hint links
itself and a hint whose place was renamed or moved turns this test red instead of leaving a dead way."""
import ast
import asyncio
import glob
import json
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import PAGE_READY, async_playwright, browser_ok, chromium

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(APP, "panel")
DE_ROOTS = ("Personen und Geräte", "Einstellungen", "Funktionen", "Zustand", "Ich")
EN_ROOTS = ("People and devices", "Settings", "Features", "Status", "Me")
HINT = re.compile(r"(?<![\w-])(?<!Mein )(?<!My )(?<!→ )(" + "|".join(DE_ROOTS + EN_ROOTS) + r")\s*→")
# a way that starts like ours but means another program (the iPhone's or Open WebUI's settings, …): text that
# names it right before the way. Everything else that starts with one of the names above must be found.
NAMES = (r"iPhone|iOS|iPad|Android|Windows|Mac|macOS|Outlook|Word|Excel|Open WebUI|WebUI|Pebble|Home Assistant|"
         r"Telegram|Kiwix|SearXNG|reMarkable-App|Chrome|Safari|Firefox|App Store|TestFlight|Xcode|Apple|Google|Gmail|"
         r"GitHub|Systemeinstellungen|System Settings|Begleiter|Companion|Wear OS|Siri|Kurzbefehle|Shortcuts|E-Mail-Einstellungen")
OTHER = re.compile(r"(" + NAMES + r")[\w\s()\-:,]{0,20}$")
# Ways whose place is not on the panel page on purpose (said elsewhere or only once a person is chosen)
KNOWN = {}


def _sources():
    """(file, text) of everything the panel or the assistant can show: the scripts, the page and the server's
    Python files, without code comments."""
    out = []
    for p in sorted(glob.glob(os.path.join(PANEL, "static", "js", "*.js"))):
        if os.path.basename(p) == "way.js":
            continue
        out.append((p, re.sub(r"(?m)(^|\s)//.*$", r"\1", open(p, encoding="utf-8").read())))
    out.append((os.path.join(PANEL, "static", "index.html"), open(os.path.join(PANEL, "static", "index.html"), encoding="utf-8").read()))
    for p in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
        out.append((p, "\n".join(_py_strings(open(p, encoding="utf-8").read()))))
    return out


def _py_strings(src):
    """The strings of a Python file that can reach a person (not docstrings): f-strings with {} in their gaps."""
    tree, docs, out = ast.parse(src), set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            docs.add(id(n.value))
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values))
            docs.update(id(v) for v in n.values)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            out.append(n.value)
    return out


def hints():
    """{way text: [where]} for every way in the sources, cut where its string ends."""
    found = {}
    for path, text in _sources():
        for m in HINT.finditer(text):
            if OTHER.search(text[max(0, m.start() - 60):m.start()]):
                continue
            s = text[m.start():m.start() + 220]
            cut = r"\n|\{" if path.endswith(".py") else r"(?<!\\)['`\"]|\\n|\n|<|\$\{"
            s = re.split(cut, s)[0].replace("\\'", "'")
            line = text.count("\n", 0, m.start()) + 1
            found.setdefault(s, []).append(f"{os.path.relpath(path, APP)}:{line}")
    return found


class Static(unittest.TestCase):
    def test_finds_the_ways(self):
        h = hints()
        self.assertGreater(len(h), 40)
        self.assertTrue(any(s.startswith("Einstellungen → Spark → Betrieb → Logs „Live-Seite“") for s in h), h.keys())

    def test_ways_start_with_a_menu_name(self):
        """„unter Sprachausgabe → …“ cannot be found (and was an old name): a way after „unter“/„under“ starts with
        Einstellungen, Funktionen, Zustand, Personen und Geräte or Ich, or it names another program."""
        rx = re.compile(r"\b(?:[Uu]nter|[Uu]nder) ([A-ZÄÖÜ][^\s→'\"`<.:]*(?: [^\s→'\"`<.:]+){0,3}?) →")
        bad = []
        for path, text in _sources():
            for m in rx.finditer(text):
                if m.group(1) in DE_ROOTS + EN_ROOTS or re.search(NAMES, m.group(1)):
                    continue
                bad.append(f"{os.path.relpath(path, APP)}: {m.group(0)}")
        self.assertEqual(bad, [])

    def test_way_js_is_loaded_and_only_moves(self):
        html = open(os.path.join(PANEL, "static", "index.html"), encoding="utf-8").read()
        self.assertIn('<script src="/static/js/way.js"></script>', html)
        js = open(os.path.join(PANEL, "static", "js", "way.js"), encoding="utf-8").read()
        # a link only opens a place: no request, no saving, no HTML from the text
        for bad in ("api(", "fetch(", "innerHTML", "localStorage", "eval(", "PUT", "POST"):
            self.assertNotIn(bad, js, bad)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        import panel
        import profiles
        cls.port = helpers._port()
        helpers._serve(panel.app, cls.port)
        try:
            profiles.add_user("Wegtest", "4711")
        except Exception:
            pass

    async def until(self, pg, expr, seconds=20):
        for _ in range(int(seconds * 10)):
            try:
                if await pg.evaluate(expr):
                    return
            except Exception:
                pass
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    async def page(self, p, locale="de-DE", width=1280, profile=True):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": width, "height": 900}, locale=locale, bypass_csp=True)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        r = await pg.request.post(base + "/api/login", data={"password": "secret-admin"})
        self.assertEqual(r.status, 200)
        if profile:
            r = await pg.request.post(base + "/api/profile/login", data={"name": "Wegtest", "pin": "4711"})
            self.assertEqual(r.status, 200)
        await pg.goto(base + "/")
        await self.until(pg, PAGE_READY + "&&ADMIN===true" + ("&&!!PROFILE" if profile else ""))
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        if profile:   # Ich draws its rows when it opens
            await pg.evaluate("openMe('setbox')")
            await pg.wait_for_timeout(1500)
            await pg.evaluate("closeProf()")
        return br, pg, errors

    def test_every_way_is_found(self):
        """Each step of every way names a page, a part or a row the panel has (German and English texts)."""
        found = hints()

        async def go():
            bad = []
            async with async_playwright() as p:
                for locale, roots in (("de-DE", DE_ROOTS), ("en-US", EN_ROOTS)):
                    br, pg, errors = await self.page(p, locale)
                    for s in ("mon", "logs", "test", "prof", "apps", "who", "int", "cfg"):   # pages draw their parts on opening
                        await pg.evaluate(f"goSec('{s}')")
                        await pg.wait_for_timeout(400)
                    ways = [s for s in found if s.startswith(roots) and not (locale == "de-DE" and s.startswith(EN_ROOTS))]
                    res = await pg.evaluate("ws=>ws.map(w=>{const r=wayParse(w,0,true);return r?[r.steps,r.want,r.quoted]:null})", ways)
                    for w, r in zip(ways, res):
                        if w in KNOWN:
                            continue
                        first = HINT.sub("", w, count=1).lstrip().lstrip('„“"')
                        if not r and not re.match(r"[A-ZÄÖÜ0-9]", first):
                            continue   # „Ich → einschalten“: what to do, no place
                        if not r:   # the first step names no page or part the viewer has
                            bad.append(f"{w!r} ({', '.join(found[w][:3])}): {r}")
                    self.assertEqual(errors, [])
                    await br.close()
            return bad

        bad = asyncio.run(go())
        self.assertEqual(bad, [], "Wege ohne Ziel:\n" + "\n".join(bad))

    def test_live_hint_links_to_its_switch(self):
        """Dominik's example: the Live page is off, its hint opens Einstellungen → Betrieb and marks „Live-Seite“."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, profile=False)
                await pg.evaluate("goSec('live')")
                await self.until(pg, "!!document.querySelector('#live a.wayl')")
                text = await pg.evaluate("document.querySelector('#live a.wayl').textContent")
                self.assertEqual(text, "Einstellungen → Spark → Betrieb → Logs „Live-Seite“")
                await pg.click("#live a.wayl")
                await self.until(pg, "document.querySelector('#pane-sysc').classList.contains('on')")
                await self.until(pg, "!!document.querySelector('#pane-sysc .sflash')")
                flashed = await pg.evaluate("document.querySelector('#pane-sysc .sflash').textContent")
                self.assertIn("Live-Seite", flashed)
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())

    def test_ich_hint_links_for_a_profile_only(self):
        """A way into Ich is a link for a signed-in profile and opens that page; admin ways are not links for a
        profile without admin rights, and nothing is a link inside a text field."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p)
                await pg.evaluate("""(()=>{const d=document.createElement('div');d.id='waytest';
                  d.innerHTML='<p>Steht unter Ich → Sicherheit.</p><textarea>Ich → Sicherheit</textarea>';document.querySelector('main').appendChild(d)})()""")
                await self.until(pg, "!!document.querySelector('#waytest p a.wayl')")
                self.assertEqual(await pg.evaluate("document.querySelector('#waytest p a.wayl').textContent"), "Ich → Sicherheit")
                self.assertEqual(await pg.evaluate("document.querySelector('#waytest textarea').value"), "Ich → Sicherheit")
                await pg.click("#waytest p a.wayl")
                await self.until(pg, "$('profmodal').style.display==='grid'&&document.querySelector('#ptabs button.on').dataset.t==='secbox'")
                # without admin rights the admin pages are no way to go
                await pg.evaluate("closeProf();ADMIN=false")
                await pg.evaluate("""(()=>{const p=document.createElement('p');p.id='wayadm';p.textContent='Unter Einstellungen → Sicherheit.';document.querySelector('main').appendChild(p)})()""")
                await pg.wait_for_timeout(300)
                self.assertEqual(await pg.evaluate("document.querySelectorAll('#wayadm a').length"), 0)
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
