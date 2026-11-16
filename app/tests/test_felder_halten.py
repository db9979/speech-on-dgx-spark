"""Polled pages keep what the user is doing (Dominik 2026-11-16 „nicht benutzbar weil anzeige immer wieder zurück
springt“, Spark-Konsole → Modelle → Eigenes Modell): zeichnen.felderNeu draws anew and keeps a field changed by hand,
the focus with its cursor, a [data-halten] box and the scroll position; the Konsole's models tab asks again only while
something runs."""
import asyncio
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "..", "panel", "static", "js")


def lesen(name):
    with open(os.path.join(JS, name), encoding="utf-8") as f:
        return f.read()


class Quelle(unittest.TestCase):
    def test_the_model_pages_draw_with_the_helper(self):
        k, m = lesen("konsole.js"), lesen("modelle.js")
        draw = k[k.index("function modDraw"):k.index("async function modAct")]
        self.assertIn("felderNeu(el,", draw)
        self.assertNotIn("el.innerHTML=`<h1>", draw)
        self.assertIn('id="kmtreffer" data-halten', draw)
        # a finished start stays on the page but does not ask every 5 seconds (that redraw took the fields away)
        self.assertRegex(draw, r"if\(busy\|\|\(w\.start&&!w\.start\.ende\)\)MOD_T=setTimeout")
        load = m[m.index("async function loadModelle"):]
        self.assertIn("felderNeu(main,", load)
        self.assertNotIn("main.innerHTML=", load)

    def test_one_helper_shared_by_panel_and_konsole(self):
        z = lesen("zeichnen.js")
        self.assertEqual(len(re.findall(r"function felderNeu\(", z)), 1)
        for name in os.listdir(JS):
            if name.endswith(".js") and name != "zeichnen.js":
                self.assertNotIn("function felderNeu(", lesen(name), name)


class ImBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_ui_browser as ui
        if not ui.browser_ok():
            raise unittest.SkipTest("no Playwright/Chromium here")
        cls.ui = ui

    def test_typed_fields_focus_box_and_scroll_stay(self):
        html = ('<div style="height:1500px"></div><div id="r"></div>')
        neu = ('`<select id="a"><option value="llm">L</option><option value="asr">A</option></select>'
               '<input id="q" value=""><input id="fest" value="${v}"><input id="c" type="checkbox">'
               '<div id="t" data-halten></div><div style="height:1500px"></div>`')

        async def go():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                exe = self.ui.chromium()
                br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
                try:
                    pg = await (await br.new_context(viewport={"width": 800, "height": 600})).new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    await pg.set_content(html)
                    await pg.add_script_tag(content=lesen("zeichnen.js"))
                    await pg.evaluate(f"window.zeichne=v=>felderNeu(document.getElementById('r'),{neu})")
                    await pg.evaluate("zeichne('1')")
                    await pg.select_option("#a", "asr")
                    await pg.fill("#q", "qwen3 nvfp4")
                    await pg.check("#c")
                    await pg.evaluate("document.getElementById('t').innerHTML='<b>Treffer</b>'")
                    await pg.evaluate("const q=document.getElementById('q');q.focus();q.setSelectionRange(2,4);scrollTo(0,900)")
                    await pg.evaluate("zeichne('2')")
                    got = await pg.evaluate("""()=>{const q=document.getElementById('q');return {
                        a:document.getElementById('a').value,q:q.value,c:document.getElementById('c').checked,
                        fest:document.getElementById('fest').value,t:document.getElementById('t').innerHTML,
                        fokus:document.activeElement.id,sel:[q.selectionStart,q.selectionEnd],y:scrollY}}""")
                    self.assertEqual(got["a"], "asr")
                    self.assertEqual(got["q"], "qwen3 nvfp4")
                    self.assertTrue(got["c"])
                    self.assertEqual(got["fest"], "2", "an untouched field takes the new value")
                    self.assertEqual(got["t"], "<b>Treffer</b>")
                    self.assertEqual(got["fokus"], "q")
                    self.assertEqual(got["sel"], [2, 4])
                    self.assertEqual(got["y"], 900)
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
