"""Eingabefelder wachsen mit dem Text (Dominik 2026-10-19: „die ganzen Eingabefenster sind starr … bei langen Eingaben
gut einsehbar“, Plan eingabefelder/plan.md 1a 2a 3a 4a 5a 6a).

- feld.js is the one place: every <textarea> (also future ones and ones filled by code or while hidden) is as high as its
  text, at least its rows, at most data-zeilen lines or half the window, then it scrolls inside; no other script
  computes a field's height (chats.js cxGrow is gone).
- The assistant's line, „Frag etwas zu dieser Seite“ and the chat composer are textareas with data-senden: Enter sends,
  Shift+Enter makes a new line, on a phone the key makes a new line and the arrow sends.
- From 4 lines ⤢ opens the large view (Fertig keeps the text, Senden sends, Esc never loses it); from 80 % of maxlength
  a counter stands at the field.
- The iPhone composer grows (axis: .vertical) and has the large view; spark-tui asks in a TextArea.
Pages at 390 and 1280 px without sideways scrolling.
"""
import asyncio
import os
import re
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok, chromium

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(APP, "panel", "static")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class Source(unittest.TestCase):
    def test_feld_is_loaded_first_and_is_the_only_height_code(self):
        html = read(STATIC, "index.html")
        self.assertIn('<script src="/static/js/laden.js"></script>\n<script src="/static/js/feld.js"></script>', html)   # right after base.js and laden.js
        for name in sorted(os.listdir(os.path.join(STATIC, "js"))):
            if name in ("feld.js",) or not name.endswith(".js"):
                continue
            src = read(STATIC, "js", name)
            # a textarea that sets its own height from scrollHeight: that is feld.js's job (one source)
            self.assertNotRegex(src, r"\.style\.height\s*=[^;]*scrollHeight", name)
        self.assertNotIn("cxGrow", read(STATIC, "js", "chats.js"))

    def test_long_inputs_are_growing_fields_that_send_with_enter(self):
        html = read(STATIC, "index.html")
        for i, n in (("chattext", "6"), ("fabq", "4"), ("cxtext", "6")):
            m = re.search(r'<textarea id="%s"[^>]*>' % i, html)
            self.assertTrue(m, i)
            self.assertIn(f'data-zeilen="{n}"', m.group(0))
            self.assertIn("data-senden=", m.group(0))
        js = "".join(read(STATIC, "js", f) for f in ("agent.js", "schreib.js", "erstellen.js"))
        for i in ('id="agwtask"', 'id="agptask"', 'id="agsteerin-', 'id="wrwish"', "data-mkw"):
            self.assertRegex(js, r"<textarea[^>]*" + re.escape(i), i)
        # Enter sends only in feld.js, no second handler beside it
        self.assertNotIn("$('chattext').onkeydown", read(STATIC, "js", "users.js"))

    def test_iphone_and_terminal_grow_too(self):
        s = helpers.repo_file("ios", "Spark", "Views.swift")   # its text; skipped in a copy with only app/
        self.assertRegex(s, r'TextField\(talk\.attachment == nil[^\n]*axis: \.vertical\)')
        self.assertIn(".lineLimit(1...5)", s)
        self.assertIn("struct GrossAnsicht", s)
        tui = read(APP, "tui", "spark-tui.py")
        self.assertIn("class AskArea(TextArea)", tui)
        self.assertNotIn('yield Input(placeholder="Frag den Spark', tui)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class InBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        import panel  # noqa: F401
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Feldtest", "4712")
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
        self.fail("timed out: " + expr)

    async def page(self, p, width, height, phone=False):
        exe = chromium()
        br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": width, "height": height}, locale="de-DE", bypass_csp=True,
                                   has_touch=phone, is_mobile=phone)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        r = await pg.request.post(base + "/api/login", data={"password": "secret-admin"})
        self.assertEqual(r.status, 200)
        r = await pg.request.post(base + "/api/profile/login", data={"name": "Feldtest", "pin": "4712"})
        self.assertEqual(r.status, 200)
        await pg.goto(base + "/")
        await self.until(pg, "typeof PROFILE!=='undefined'&&!!PROFILE&&PROFILE.name==='Feldtest'")
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        await pg.evaluate("goSec('chat')")
        await self.until(pg, "$('chattext').getClientRects().length>0")
        return br, pg, errors

    def test_computer(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                h0 = await pg.evaluate("$('chattext').offsetHeight")
                await pg.focus("#chattext")
                await pg.keyboard.type("Schreib bitte eine kurze Mail an Herrn Keller, dass der Termin am Dienstag "
                                       "verschoben wird und dass ich die Unterlagen noch nachreiche.")
                await pg.keyboard.press("Shift+Enter")
                await pg.keyboard.press("Shift+Enter")
                await pg.keyboard.type("Freundlich, aber knapp.")
                self.assertEqual(await pg.evaluate("$('chattext').value.split('\\n').length"), 3)   # Shift+Enter: a new line
                await self.until(pg, f"$('chattext').offsetHeight>{h0}+30")
                # at most 6 lines, then it scrolls inside
                await pg.keyboard.type("\n" * 0)
                for _ in range(8):
                    await pg.keyboard.press("Shift+Enter")
                    await pg.keyboard.type("Noch eine Zeile.")
                await pg.wait_for_timeout(100)
                lh, hi, over = await pg.evaluate("[parseFloat(getComputedStyle($('chattext')).lineHeight),$('chattext').offsetHeight,getComputedStyle($('chattext')).overflowY]")
                self.assertLessEqual(hi, 6 * lh + 40)
                self.assertEqual(over, "auto")
                # ⤢ from 4 lines: the large view keeps the text; Fertig puts it back, Esc too
                await self.until(pg, "!$('feldgross').hidden")
                await pg.click("#feldgross")
                await self.until(pg, "$('feldmodal').style.display==='grid'&&document.activeElement===$('feldtext')")
                self.assertEqual(await pg.evaluate("$('feldtext').value===$('chattext').value"), True)
                self.assertFalse(await pg.evaluate("$('feldsenden').hidden"))
                await pg.keyboard.press("Enter")   # in the large view Enter makes a new line, never sends
                await pg.keyboard.type("Danke!")
                await pg.keyboard.press("Escape")
                self.assertEqual(await pg.evaluate("$('feldmodal').style.display"), "none")
                self.assertTrue(await pg.evaluate("$('chattext').value.endsWith('\\nDanke!')"))
                # Enter sends, the field goes back to one line
                n = await pg.evaluate("document.querySelectorAll('#chatlog .msg').length")
                await pg.focus("#chattext")
                await pg.keyboard.press("Enter")
                await self.until(pg, f"document.querySelectorAll('#chatlog .msg').length>{n}")
                await self.until(pg, f"$('chattext').value===''&&$('chattext').offsetHeight<={h0}+1")
                # any other field: filled by code while hidden, it grows as soon as it shows; a counter from 80 %
                await pg.evaluate("""(()=>{const d=document.createElement('div');d.id='ftbox';d.style.display='none';
                    d.innerHTML='<textarea id="ftx" rows="2" maxlength="100"></textarea>';$('chatlog').before(d);
                    $('ftx').value='eins\\nzwei\\ndrei\\nvier\\nfünf\\nsechs\\nsieben';d.style.display='block'})()""")
                await self.until(pg, "$('ftx').scrollHeight<=$('ftx').clientHeight+1&&$('ftx').offsetHeight>60")
                await pg.focus("#ftx")
                await pg.keyboard.press("End")
                await pg.keyboard.type("x" * 50)
                await self.until(pg, "!$('feldzahl').hidden&&$('feldzahl').textContent.includes('/ 100')")
                await pg.evaluate("$('ftbox').remove()")
                over = await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                self.assertLessEqual(over, 1)
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())

    def test_phone(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 390, 844, phone=True)
                await pg.focus("#chattext")
                await pg.keyboard.type("Eine Frage")
                await pg.keyboard.press("Enter")   # on a phone the key makes a new line, the arrow sends
                await pg.keyboard.type("über zwei Zeilen")
                self.assertEqual(await pg.evaluate("$('chattext').value"), "Eine Frage\nüber zwei Zeilen")
                self.assertIn("hastext", await pg.evaluate("document.querySelector('.composer').className"))
                for _ in range(4):
                    await pg.keyboard.press("Enter")
                    await pg.keyboard.type("weiter")
                await self.until(pg, "!$('feldgross').hidden")
                await pg.click("#feldgross")
                await self.until(pg, "$('feldmodal').style.display==='grid'")
                box = await pg.evaluate("[$('feldmodal').querySelector('.feldcard').offsetWidth,$('feldmodal').querySelector('.feldcard').offsetHeight]")
                self.assertEqual(box[0], 390)   # the whole screen
                self.assertGreater(box[1], 700)
                n = await pg.evaluate("document.querySelectorAll('#chatlog .msg').length")
                await pg.click("#feldsenden")
                await self.until(pg, f"document.querySelectorAll('#chatlog .msg').length>{n}")
                await self.until(pg, "$('chattext').value===''")
                over = await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                self.assertLessEqual(over, 1)
                self.assertEqual(errors, [])
                await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
