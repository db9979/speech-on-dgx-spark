"""The panel in a real browser (Chromium via Playwright), on a computer and on a phone screen: every page
opens without a script error and without sideways scrolling, the settings search finds a setting and
the Ich window starts with its overview. Skipped where Playwright or Chromium is missing (the update
self-test on the Spark); runs in the container and in the GitHub "Tests" workflow."""
import asyncio
import glob
import os
import unittest

from tests import helpers

try:
    from playwright.async_api import async_playwright
except ImportError:  # the panel venv on the Spark has no browser
    async_playwright = None


def chromium():
    if os.environ.get("SPEECH_SPARK_CHROMIUM"):
        return os.environ["SPEECH_SPARK_CHROMIUM"]
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return found[-1] if found else None   # None: Playwright's own download (GitHub workflow)


def browser_ok():
    if async_playwright is None or os.environ.get("SPEECH_SPARK_NO_BROWSER"):
        return False
    return bool(chromium()) or bool(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*")))


# what the hands-free test shows when the microphone did not come back
STATE = ("JSON.stringify({hidden:document.hidden,rec:!!chat.rec,live:micLive(),resume:chat.resumeMic,hands:S.hands,"
         "ctrl:!!chat.ctrl,playing:playing(),asr:!!chat.asrBusy,pctx:chat.pctx&&[chat.pctx.state,chat.pctx.currentTime],"
         "ctx:chat.ctx&&[chat.ctx.state,chat.ctx.currentTime],say:$('chatstate').textContent})")

SECTIONS = ("chat", "mon", "sys", "test", "logs", "cfg", "prof", "int", "apps")
VIEWS = (("pc", 1280, 900), ("handy", 390, 844))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.start()
        helpers.set_config(memory=True, documents=True, search=True, calendar=True, weather=True, mail=True,
                           homeassistant=True, speaker_id=True, telegram=True, wyoming=False)
        import panel
        import profiles
        cls.port = helpers._port()
        helpers._serve(panel.app, cls.port)
        try:
            profiles.add_user("Uitest", "4711")
        except Exception:
            pass   # already there from an earlier test class

    def run_async(self, coro):
        return asyncio.run(coro)

    async def page(self, p, width, height, mic=False):
        exe = chromium()
        args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required"] if mic else []
        br = await p.chromium.launch(args=args, **({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": width, "height": height}, locale="de-DE",
                                   permissions=["microphone"] if mic else [])
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{self.port}"
        await pg.goto(base + "/")
        r = await pg.request.post(base + "/api/login", data={"password": "secret-admin"})
        self.assertEqual(r.status, 200)
        r = await pg.request.post(base + "/api/profile/login", data={"name": "Uitest", "pin": "4711"})
        self.assertEqual(r.status, 200)
        await pg.goto(base + "/")
        await pg.wait_for_timeout(800)
        await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
        return br, pg, errors

    def test_every_page_without_errors_or_sideways_scrolling(self):
        async def go():
            async with async_playwright() as p:
                for name, w, h in VIEWS:
                    br, pg, errors = await self.page(p, w, h)
                    for s in SECTIONS:
                        await pg.evaluate(f"goSec('{s}')")
                        await pg.wait_for_timeout(300)
                        over = await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                        self.assertLessEqual(over, 1, f"{name}/{s}: {over}px zu breit")
                    await pg.evaluate("goSec('cfg')")
                    for p_id in await pg.evaluate("[...document.querySelectorAll('#cfgnav button[data-p]')].map(b=>b.dataset.p)"):
                        await pg.evaluate(f"document.querySelector('#cfgnav button[data-p={p_id}]').click()")
                        await pg.wait_for_timeout(150)
                        over = await pg.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                        self.assertLessEqual(over, 1, f"{name}/cfg-{p_id}: {over}px zu breit")
                        if name == "handy":
                            await pg.evaluate("$('cfgback').click()")
                    # design „Klar“: computers get the menu as a sidebar on the left, phones a bar at the bottom
                    if name == "pc":
                        box = await pg.evaluate("(()=>{const r=document.querySelector('header').getBoundingClientRect();return [r.left,r.width,r.height]})()")
                        self.assertEqual(box[0], 0)
                        self.assertLess(box[1], 300)
                        self.assertGreater(box[2], 600)
                        self.assertFalse(await pg.evaluate("getComputedStyle($('mbar')).display!=='none'"))
                    else:
                        self.assertTrue(await pg.evaluate("getComputedStyle($('mbar')).display!=='none'"))
                        await pg.evaluate("document.querySelector('#mbar button[data-m=mon]').click()")
                        self.assertTrue(await pg.evaluate("document.querySelector('nav button[data-s=mon]').classList.contains('on')"))
                    self.assertEqual(errors, [], name)
                    await br.close()
        self.run_async(go())

    def test_zustand_says_how_it_is_and_what_needs_you(self):
        """V01.0.146: Zustand starts with one sentence and lists unsaved settings pages under "Braucht dich"
        with a button that opens the page; the dot in the menu follows the sentence."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                await pg.evaluate("goSec('mon')")
                await pg.wait_for_function("$('zhead').dataset.lvl", timeout=8000)
                self.assertTrue((await pg.inner_text("#ztitle")).strip())
                lvl = await pg.evaluate("$('zhead').dataset.lvl")
                self.assertEqual(await pg.evaluate("$('hdot').className"), "hdot " + lvl)
                await pg.evaluate("markDirty($('pane-tts'),true)")
                self.assertFalse(await pg.evaluate("$('zneed').hidden"))
                self.assertIn("Sprachausgabe", await pg.inner_text("#zlist"))
                self.assertEqual(await pg.inner_text("#dirtycnt"), "1")
                await pg.evaluate("[...document.querySelectorAll('#zlist button')].pop().click()")
                await pg.wait_for_timeout(300)
                self.assertTrue(await pg.evaluate("$('pane-tts').classList.contains('on')"))
                await pg.evaluate("markDirty($('pane-tts'),false)")
                self.assertTrue(await pg.evaluate("$('zneed').hidden||!$('zlist').textContent.includes('Sprachausgabe')"))
                self.assertEqual(errors, [])
                await br.close()
        self.run_async(go())

    def test_settings_search_opens_the_setting(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                await pg.evaluate("goSec('cfg')")
                await pg.evaluate("document.querySelector('#cfgnav button[data-p=ai]').click()")
                await pg.fill("#cfgnav .sbox input", "searxng")
                hits = await pg.evaluate("[...document.querySelectorAll('#cfgnav .sres button b')].map(b=>b.textContent)")
                self.assertTrue(any("SearXNG" in x for x in hits), hits)
                await pg.press("#cfgnav .sbox input", "Enter")
                await pg.wait_for_timeout(300)
                self.assertTrue(await pg.evaluate("$('pane-feat').classList.contains('on')"))
                self.assertTrue(await pg.evaluate("!!document.querySelector('#pane-feat .sflash')"))
                await pg.fill("#cfgnav .sbox input", "zzzxq")
                self.assertIn("Nichts gefunden", await pg.inner_text("#cfgnav .sres"))
                self.assertEqual(errors, [])
                await br.close()
        self.run_async(go())

    def test_me_window_overview_and_search(self):
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 1280, 900)
                await pg.evaluate("goSec('chat')")
                await pg.evaluate("$('profbtn').click()")
                await pg.wait_for_timeout(800)
                self.assertTrue(await pg.evaluate("$('overbox').classList.contains('on')"))
                rows = await pg.evaluate("[...document.querySelectorAll('#overbox .overrow b')].map(b=>b.textContent)")
                self.assertIn("Gedächtnis", rows)
                await pg.fill("#ptabs .sbox input", "sprechtempo")
                await pg.press("#ptabs .sbox input", "Enter")
                await pg.wait_for_timeout(300)
                self.assertTrue(await pg.evaluate("$('setbox').classList.contains('on')"))
                self.assertTrue(await pg.evaluate("!!document.querySelector('#setbox .sflash')"))
                self.assertEqual(errors, [])
                await br.close()
        self.run_async(go())

    def test_hands_free_microphone_comes_back(self):
        """iOS ends the microphone track (lock screen, call, Siri): a dead stream is asked for again,
        the page says why it stopped, and hands-free listening opens the microphone again."""
        async def go():
            async with async_playwright() as p:
                br, pg, errors = await self.page(p, 390, 844, mic=True)
                await pg.evaluate("goSec('chat');S.hands=true;S.live=false;S.turn=false")
                await pg.evaluate("startListening()")
                await pg.wait_for_function("!!chat.rec&&micLive()", timeout=5000)
                first = await pg.evaluate("chat.stream.id")
                # the system takes the microphone away
                await pg.evaluate("chat.stream.getAudioTracks().forEach(x=>{x.stop();x.dispatchEvent(new Event('ended'))})")
                await pg.wait_for_function("!chat.rec", timeout=5000)
                self.assertIn("System hat das Mikrofon beendet", await pg.inner_text("#chatstate"))
                self.assertTrue(await pg.evaluate("chat.resumeMic&&!chat.stream"))
                # the page is visible again: hands-free listens again on a new stream
                await pg.evaluate("micBack()")
                try:
                    await pg.wait_for_function("!!chat.rec&&micLive()", timeout=5000)
                except Exception:
                    self.fail(await pg.evaluate(STATE))
                self.assertNotEqual(first, await pg.evaluate("chat.stream.id"))
                self.assertFalse(await pg.evaluate("chat.resumeMic"))
                # a stream whose track ended without telling us is not reused
                await pg.evaluate("stopListening(true)")
                await pg.wait_for_function("!chat.rec", timeout=5000)
                second = await pg.evaluate("chat.stream.id")
                await pg.evaluate("chat.stream.getAudioTracks().forEach(x=>{x.onended=null;x.stop()})")
                await pg.evaluate("startListening()")
                await pg.wait_for_function("!!chat.rec&&micLive()", timeout=5000)
                self.assertNotEqual(second, await pg.evaluate("chat.stream.id"))
                await pg.evaluate("stopListening(true)")
                self.assertEqual(errors, [])
                await br.close()
        self.run_async(go())
