"""The person's page of the Spontanhilfe (/hilfe, spontanhilfe-seite.js) in the browser at 320, 390 and 1280 px, with its
own strict CSP on (Dominik 2026-11-04: „Programm laden“ said „too many requests, please wait a moment“ in English, and
the page looked dreadful; Bild spontanhilfe/seite2/vorschlag-schlicht.png). The panel's two doors are played by the
test (the start POST, the person's WebSocket and the program POST), so the page runs its real code: a 429 shows only
the fixed text with a countdown from Retry-After, the button off with that reason, and on again afterwards; no
server text ever shows; the header says what is seen and offers „Sitzung beenden“; the request lists its steps,
the checksum only on a click; messages have their field on top and name plus time; on the phone one column with the
messages under the request; nothing sideways and at least 80 px free at the bottom."""
import asyncio
import json
import time
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok, chromium

helpers.start()
import guard  # noqa: E402
import spontanhilfe as sh  # noqa: E402

WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
SHA = "ab" * 32
SERVER_TEXT = "too many requests"


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)
        helpers.set_config(fernzugang=True, spontanhilfe=True)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(spontanhilfe=False)

    def setUp(self):
        sh.HILFE.clear()
        for k in [k for k in guard._rate if str(k[0]).startswith("spontanhilfe")]:
            guard._rate.pop(k, None)

    async def open(self, p, width, height):
        """/hilfe with a link, the start answered, the socket played: open, a message from the helper, then
        „Steuern anfragen“ for Windows x64. The program POST answers 429 with Retry-After 2."""
        exe = chromium()
        br = await p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                           "--auto-select-desktop-capture-source=Entire screen"],
                                     **({"executable_path": exe} if exe else {}))
        ctx = await br.new_context(viewport={"width": width, "height": height}, locale="de-DE", user_agent=WINDOWS)
        pg = await ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text else None)
        calls = []

        async def start(route):
            calls.append("start")
            await route.fulfill(status=200, content_type="application/json", body=json.dumps({"tok": "t" * 40, "admin": "Dominik"}))

        async def programm(route):
            calls.append("programm")
            await route.fulfill(status=429, content_type="application/json", headers={"Retry-After": "2"},
                                body=json.dumps({"detail": "too many requests, please wait a moment"}))
        await pg.route("**/api/hilfe/start", start)
        await pg.route("**/api/hilfe/programm", programm)
        sock = []

        def ws(route):
            sock.append(route)

            def got(msg):
                m = json.loads(msg)
                if m.get("typ") == "hallo":
                    route.send(json.dumps({"typ": "stand", "stand": "wartet", "admin": "Dominik"}))
                    route.send(json.dumps({"typ": "stand", "stand": "offen", "bis": int(time.time()) + 3540, "ice": []}))
                    route.send(json.dumps({"typ": "chat", "text": "Hallo, ich schaue mir das kurz an."}))
            route.on_message(got)
        await pg.route_web_socket("**/api/hilfe/ws", ws)
        base = f"http://127.0.0.1:{self.port}"
        r = await pg.goto(base + "/hilfe#" + "k" * 22)
        self.assertEqual(r.status, 200)
        self.assertIn("default-src 'none'", r.headers["content-security-policy"])       # the page's own CSP, not bypassed
        self.assertEqual(await pg.evaluate("location.hash"), "")                        # the key left the address bar
        await pg.fill("#name", "Helga")
        await pg.click("#f-start button")
        await pg.wait_for_selector("#s-offen:not([hidden])", timeout=20000)
        return br, pg, errors, calls, sock

    def test_the_page_in_three_widths(self):
        from tests.test_ui_browser import async_playwright

        async def go():
            async with async_playwright() as p:
                for width, height in ((1280, 900), (390, 844), (320, 640)):
                    br, pg, errors, calls, sock = await self.open(p, width, height)
                    try:
                        await self.check(pg, width, calls, sock)
                        self.assertEqual(errors, [], width)
                    finally:
                        await br.close()
        asyncio.run(go())

    async def check(self, pg, width, calls, sock):
        # the header: the brand, what is seen, with whom and until when, and the way out
        self.assertEqual(await pg.inner_text(".brand"), "Spark Fernhilfe")
        self.assertIn("Dominik ist bereit, noch sieht man nichts", await pg.inner_text("#state"))
        self.assertRegex(await pg.inner_text("#baruhr"), r"^mit Dominik · endet spätestens in \d+ min$")
        self.assertEqual(await pg.inner_text("#ende"), "Sitzung beenden")
        self.assertTrue(await pg.is_visible("#ende"))
        self.assertTrue(await pg.is_visible("#teilen"))
        self.assertFalse(await pg.is_visible("#prev"))                                  # no preview before sharing
        # messages: the field on top, every message with its name and time, only as text
        await pg.wait_for_selector("#chat .msg")
        self.assertEqual(await pg.inner_text("#chat .msg .who"), "Dominik")
        self.assertRegex(await pg.inner_text("#chat .msg time"), r"^\d\d:\d\d$")
        self.assertEqual(await pg.get_attribute("#chatin", "placeholder"), "Nachricht an Dominik …")
        field, log = await pg.eval_on_selector("#f-chat", "e=>e.getBoundingClientRect().top"), \
            await pg.eval_on_selector("#chat", "e=>e.getBoundingClientRect().top")
        self.assertLess(field, log)
        await pg.fill("#chatin", "Danke!")
        await pg.click("#f-chat button")
        self.assertEqual(await pg.inner_text("#chat .msg.mine .who"), "Sie")
        # sharing: the header turns to „Bildschirm wird geteilt“, the preview is small and can be hidden
        await pg.click("#teilen")
        try:
            await pg.wait_for_selector("#prev:not([hidden])", timeout=10000)
            shared = True
        except Exception:
            shared = False   # a Chromium without a capture source: the rest still runs
        if shared:
            self.assertIn("Bildschirm wird geteilt", await pg.inner_text("#state"))
            self.assertLessEqual(await pg.eval_on_selector(".pv", "e=>e.getBoundingClientRect().width"), 180)
            await pg.click("#prevweg")
            self.assertFalse(await pg.is_visible("#pvrow"))
            self.assertEqual(await pg.inner_text("#prevweg"), "einblenden")
            await pg.click("#prevweg")
            self.assertTrue(await pg.is_visible("#pvrow"))
        # the request: a title, a sentence, three steps, the checksum only on a click
        sock[0].send(json.dumps({"typ": "steuern", "stand": "angefragt", "programme": {"windows-x64": SHA}, "zeile": True}))
        await pg.wait_for_selector("#steuern:not([hidden])")
        self.assertEqual(await pg.inner_text("#steuerntitel"), "Dominik möchte Ihren Computer steuern")
        self.assertEqual(await pg.eval_on_selector_all("#schritte li", "l=>l.map(x=>x.textContent)"),
                         ["Programm laden", "Die geladene Datei öffnen", "Im Programm „Erlauben“ wählen"])
        self.assertEqual(await pg.inner_text("#nein"), "Nur ansehen lassen")
        self.assertFalse(await pg.is_visible("#pruef"))
        await pg.click("#pruefknopf")
        self.assertEqual(await pg.inner_text("#pruef"), SHA)
        # a 429: the fixed text with a countdown, the button off with that reason, never the server's words
        await pg.click("#laden")
        await pg.wait_for_selector("#hinweis:not([hidden])")
        text = await pg.inner_text("#hinweis")
        self.assertRegex(text, r"^Bitte einen Moment warten, dann noch einmal tippen \(noch [12] s\)\.$")
        self.assertTrue(await pg.is_disabled("#laden"))
        self.assertEqual(await pg.get_attribute("#laden", "title"), text)
        self.assertNotIn(SERVER_TEXT, (await pg.inner_text("body")).lower())
        for _ in range(100):                                    # polled: the strict CSP refuses wait_for_function
            if not await pg.is_disabled("#laden"):
                break
            await pg.wait_for_timeout(100)
        self.assertFalse(await pg.is_disabled("#laden"))
        self.assertIsNone(await pg.get_attribute("#laden", "title") or None)
        self.assertFalse(await pg.is_visible("#hinweis"))
        self.assertEqual(calls.count("programm"), 1)
        # the layout: phone one column with the messages under the request (above the preview), else beside it
        top = {k: await pg.eval_on_selector(s, "e=>e.getBoundingClientRect().top") for k, s in
               (("anfrage", "#steuern"), ("nachrichten", "#nachrichten"))}
        if width < 700:
            self.assertGreater(top["nachrichten"], top["anfrage"])
            if shared:
                self.assertLess(top["nachrichten"], await pg.eval_on_selector("#prev", "e=>e.getBoundingClientRect().top"))
        else:
            self.assertGreater(await pg.eval_on_selector("#nachrichten", "e=>e.getBoundingClientRect().left"),
                               await pg.eval_on_selector("#steuern", "e=>e.getBoundingClientRect().right"))
        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
        self.assertLessEqual(over, 1, f"{width} px scrolls sideways")
        self.assertGreaterEqual(await pg.evaluate("parseFloat(getComputedStyle(document.getElementById('sh')).paddingBottom)"), 80)
        self.assertEqual(await pg.inner_text("#fuss"), "Es wird nichts aufgezeichnet")      # http: not „verschlüsselt“
        # „Sitzung beenden“: the end, nothing left
        await pg.click("#ende")
        await pg.wait_for_selector("#s-zu:not([hidden])")
        self.assertFalse(await pg.is_visible("#ende"))


if __name__ == "__main__":
    unittest.main()
