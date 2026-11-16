"""Gespräche übersichtlich ablegen (Dominik 2026-11-14, Schritt 1): the conversations of the assistant as a list beside
the conversation (grouped by Heute, Gestern, Letzte 7 Tage, Älter, the open one in the accent) instead of a drop-down, a
narrow card opens the list over the conversation; under an answer one grey line for what it used and the actions only on
pointing (a phone: after a tap), the rare ones behind „⋯“, nothing jumps. Static checks everywhere, the page in a real
browser where Playwright and Chromium exist; the groups are seeded relative to now, so no test reads the clock."""
import os
import re
import time
import unittest

from tests import helpers
from tests import test_ui_browser as tub
from tests.test_ui_browser import async_playwright, browser_ok

helpers.start()
import profiles  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")


def read(*p):
    with open(os.path.join(STATIC, *p), encoding="utf-8") as f:
        return f.read()


class Static(unittest.TestCase):
    def test_a_list_instead_of_the_drop_down(self):
        html, js = read("index.html"), read("js", "chat.js")
        self.assertNotIn('id="convosel"', html)
        for part in ('id="convolist"', 'id="cvlrows"', 'id="cvlbtn"', 'id="cvlnew"', 'id="convotitle"', 'id="convofind"'):
            self.assertIn(part, html)
        for name in ("chat.js", "phone.js", "appview.js"):
            self.assertNotIn("convosel", read("js", name), name)
        # rows from the list building blocks, drawn in parts with a fixed key, texts only escaped
        self.assertIn("keyFill($('cvlrows'),parts)", js)
        self.assertIn('class="ld-row', js[js.index("function fillConvos"):])
        self.assertIn("esc(convoName(c))", js)
        # the wide view changes the card's padding: switched one frame later, or Chromium reports a ResizeObserver loop
        # as a page error (Dauer-Wackler test_profile_gets_the_same_shell, V01.1.457)
        self.assertIn("requestAnimationFrame(()=>e.target.classList.toggle('cvwide',w))", js)
        self.assertIn("const convoName=c=>(window.TOPICS_ON&&c.name)||c.title||'…'", js)
        # one source for the groups: the app view's sheet takes the same helpers
        av = read("js", "appview.js")
        self.assertIn("ldDayGroup(c.updated)", av)
        self.assertNotIn("function day(ts)", av)

    def test_calm_answers(self):
        js, css = read("js", "chat.js"), read("app.css")
        done = js[js.index("attRender(el,att,true);"):js.index("actsRow(el,acts,extra);")]
        # the rare ones go behind „⋯“, never straight under the answer
        for name in ("rpAnswerBar(rpaId)", "Aufs reMarkable", "Ins Wissensbuch"):
            self.assertIn(name, done)
        self.assertIn("extra.push(rpAnswerBar(rpaId))", done)
        self.assertNotIn("el.appendChild(rateBar", done)
        self.assertIn("acts.appendChild(rateBar(rateId))", done)
        # shown by opacity only, the room stays (nothing jumps)
        rule = re.search(r"\.macts\{[^}]*\}", css).group(0)
        self.assertIn("opacity:0", rule)
        self.assertNotIn("display:none", rule)
        self.assertIn(".msg:hover :is(.macts,.prorow)", css)
        self.assertIn("@media (hover:none){.msg:hover :is(.macts,.prorow){opacity:0}", css)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    # the page helpers of test_ui_browser, borrowed (a subclass would run all of its tests again)
    setUpClass = tub.Browser.__dict__["setUpClass"]
    B = tub.Browser
    run_async, _chrome, until, page = B.run_async, B._chrome, B.until, B.page

    def seed(self, uid):
        now = int(time.time() * 1000)
        day = 24 * 3600 * 1000
        for cid, title, at in (("c0000000a01", "Wo ist mein Paket?", now), ("c0000000a02", "Termine Dienstag", now - day),
                               ("c0000000a03", "Rezept Linsensuppe", now - 30 * day)):
            profiles.save_convo(uid, {"id": cid, "title": title, "updated": at,
                                      "msgs": [{"role": "user", "content": title}, {"role": "assistant", "content": "Antwort zu " + title}]})

    def test_list_beside_over_and_calm_actions(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1600, 900)
                uid = await pg.evaluate("PROFILE.id")
                self.seed(uid)
                await pg.evaluate("(async()=>{goSec('chat');await convos.sync();fillConvos()})()")
                await self.until(pg, "document.querySelectorAll('#cvlrows [data-cid]').length>=3")
                # wide: the list beside the conversation, groups in order, the list button hidden
                await self.until(pg, "$('convocard').classList.contains('cvwide')")
                heads = await pg.evaluate("[...document.querySelectorAll('#cvlrows .ld-grp')].map(e=>e.textContent)")
                self.assertEqual(heads, ["Heute", "Gestern", "Älter"])
                self.assertFalse(await pg.evaluate("!!$('cvlbtn').offsetParent"))
                # a click opens it, the title follows, the row is the open one; a row that did not change stays the
                # same node (keyFill)
                row = await pg.evaluate_handle("document.querySelector('#cvlrows [data-cid=c0000000a03]')")
                await pg.click("#cvlrows [data-cid=c0000000a02]")
                await self.until(pg, "chat.cid==='c0000000a02'")
                self.assertEqual(await pg.evaluate("$('convotitle').textContent"), "Termine Dienstag")
                self.assertTrue(await pg.evaluate("document.querySelector('#cvlrows [data-cid=c0000000a02]').classList.contains('on')"))
                self.assertTrue(await pg.evaluate("r=>r.isConnected", row))
                # the actions under an answer: invisible until pointing, the rare ones behind „⋯“
                await pg.evaluate("""(()=>{const el=[...document.querySelectorAll('#chatlog .bubble')].at(-1);
                  const acts=document.createElement('div');acts.className='macts';acts.appendChild(rateBar('x'));
                  actsRow(el,acts,[rpAnswerBar('y')])})()""")
                op = "getComputedStyle(document.querySelector('#chatlog .macts')).opacity"
                await pg.mouse.move(5, 5)
                await self.until(pg, op + "==='0'")
                self.assertFalse(await pg.evaluate("!!document.querySelector('#chatlog .macts .rpabar').offsetParent"))
                h0 = await pg.evaluate("document.querySelector('#chatlog .msg:last-child').offsetHeight")
                # pointing shows them; a device without hover (GitHub's headless Chromium, a phone) after a tap
                if await pg.evaluate("matchMedia('(hover:none)').matches"):
                    await pg.click("#chatlog .msg:last-child .bubble", position={"x": 4, "y": 4})
                    self.assertTrue(await pg.evaluate("document.querySelector('#chatlog .msg:last-child').classList.contains('sel')"))
                else:
                    await pg.hover("#chatlog .msg:last-child .bubble")
                await self.until(pg, op + "==='1'")
                self.assertEqual(await pg.evaluate("document.querySelector('#chatlog .msg:last-child').offsetHeight"), h0)
                await pg.click("#chatlog .macts .mmore")
                self.assertTrue(await pg.evaluate("!!document.querySelector('#chatlog .macts .rpabar').offsetParent"))
                # narrow (an iPad upright; up to 1100 px the side menu shows only symbols since 2026-11-16, so 1000 px
                # leaves the card wide enough for the list beside it): the list opens over the conversation with the
                # button, a pick closes it
                await pg.set_viewport_size({"width": 820, "height": 900})
                await self.until(pg, "!$('convocard').classList.contains('cvwide')")
                self.assertFalse(await pg.evaluate("!!$('convolist').offsetParent"))
                await pg.click("#cvlbtn")
                await self.until(pg, "!!$('convolist').offsetParent")
                await pg.click("#cvlrows [data-cid=c0000000a03]")
                await self.until(pg, "chat.cid==='c0000000a03'&&!$('convolist').offsetParent")
                self.assertEqual(errors, [])
        self.run_async(go())


if __name__ == "__main__":
    unittest.main()
