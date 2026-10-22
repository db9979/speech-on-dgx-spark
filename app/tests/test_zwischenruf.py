"""Ins Wort fallen: erst anhalten (zwischenruf.py; admin chat.barge_hold, off by default): a barge-in only pauses the
answer and the panel decides with fixed words whether it plays on ("mhm", own or foreign voice, nothing heard), stops
("Stopp") or the sentence is the new question. Never for guests, never decided by the model, only the decision and
its fixed reason in the journal. Nothing here depends on the clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import contextlib
import io
import json
import os
import re
import unittest
import wave

import numpy as np

from tests import helpers

helpers.start()
import panel  # noqa: E402
import zwischenruf  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_ui_browser import browser_ok, chromium  # noqa: E402

try:
    from playwright.async_api import async_playwright
except ImportError:  # the panel venv on the Spark has no browser
    async_playwright = None

SR = 16000
ASR_TEXT = ["mhm"]
JS = os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js")


def speech(total_s=2.0):
    """A changing loud tone (enough "voice" for stille.py), 16 kHz WAV bytes."""
    t = np.arange(int(total_s * SR)) / SR
    x = (0.2 * np.sin(2 * np.pi * (180 + 60 * np.sin(2 * np.pi * 4 * t)) * t)).astype(np.float32)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return b.getvalue()


def fake_asr():
    app = FastAPI()

    @app.post("/v1/audio/transcriptions")
    async def tr(req: Request):
        await req.body()
        return {"text": ASR_TEXT[0], "duration": 2.0}
    return app


ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ASR_PORT = helpers._port()
helpers._serve(fake_asr(), ASR_PORT)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


class Words(unittest.TestCase):
    def test_listening_words_play_on(self):
        for text in ("mhm", "Mhm.", "Ja, genau!", "okay", "ach so, alles klar", "aha", "yeah", "uh-huh", "I see"):
            self.assertEqual(zwischenruf.decide(text), ("weiter", "rueckmeldung"), text)

    def test_stop_words_stop_even_with_listening_words(self):
        for text in ("Stopp!", "Halt", "Ruhe", "Okay, stopp", "Spark, hör auf", "Sei still.",
                     "Danke, reicht", "das reicht", "stop", "be quiet"):
            self.assertEqual(zwischenruf.decide(text), ("stopp", "stoppwort"), text)

    def test_anything_else_is_a_question(self):
        for text in ("Ja, aber was ist mit morgen?", "Nein", "Wie spät ist es", "Stopp mal, wie heißt der Film",
                     "mhm mhm mhm mhm mhm", "Hey Spark"):
            self.assertEqual(zwischenruf.decide(text)[0], "frage", text)

    def test_after_a_question_yes_is_an_answer(self):
        self.assertEqual(zwischenruf.decide("ja", asked=True), ("frage", "rueckfrage"))
        self.assertEqual(zwischenruf.decide("okay", asked=True), ("frage", "rueckfrage"))
        self.assertEqual(zwischenruf.decide("Stopp", asked=True), ("stopp", "stoppwort"))

    def test_nothing_or_an_ignored_voice_plays_on(self):
        self.assertEqual(zwischenruf.decide(""), ("weiter", "leer"))
        self.assertEqual(zwischenruf.decide(None), ("weiter", "leer"))
        for why in ("foreign voice", "own voice", "silence"):
            self.assertEqual(zwischenruf.decide("Wie spät ist es", ignored=why), ("weiter", "ueberhoert"), why)


class Endpoint(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        self.port = c["asr"]["port"]
        c["asr"]["port"] = ASR_PORT
        helpers.write_config(c)
        self.client = profile("Zwischenrufer")

    def tearDown(self):
        helpers.set_config(barge_hold=False)
        ASR_TEXT[0] = "mhm"
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["asr"]["port"] = self.port
        helpers.write_config(c)

    def heard(self, client, text, **data):
        ASR_TEXT[0] = text
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = client.post("/api/test/asr", files={"file": ("frage.wav", speech(), "audio/wav")},
                            data=dict({"language": "de"}, **data))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json(), out.getvalue()

    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["barge_hold"], False)
        self.assertFalse(self.client.get("/api/profile/settings").json()["allow"]["barge_hold"])
        got, log = self.heard(self.client, "mhm", opened="barge", hold="1")
        self.assertNotIn("barge", got)
        self.assertNotIn("zwischenruf", log)

    def test_decision_comes_back_and_only_its_reason_is_logged(self):
        helpers.set_config(barge_hold=True)
        self.assertTrue(self.client.get("/api/profile/settings").json()["allow"]["barge_hold"])
        got, log = self.heard(self.client, "mhm", opened="barge", hold="1")
        self.assertEqual(got["barge"], "weiter")
        self.assertIn("hoeren: zwischenruf weiter | listening words", log)
        got, log = self.heard(self.client, "Stopp", opened="barge", hold="1")
        self.assertEqual(got["barge"], "stopp")
        got, log = self.heard(self.client, "Wie wird das Wetter morgen in Leipzig", opened="barge", hold="1")
        self.assertEqual(got["barge"], "frage")
        self.assertEqual(got["text"], "Wie wird das Wetter morgen in Leipzig")
        self.assertNotIn("Leipzig", log)
        self.assertNotIn("Zwischenrufer", log)
        self.assertRegex(log, re.compile(r"^hoeren: zwischenruf frage \| a sentence \| from \w+$", re.M))
        got, _ = self.heard(self.client, "ja", opened="barge", hold="1", asked="1")
        self.assertEqual(got["barge"], "frage")

    def test_only_a_paused_barge_in_asks(self):
        helpers.set_config(barge_hold=True)
        for data in ({"opened": "barge"}, {"opened": "follow", "hold": "1"}, {"hold": "1"}):
            got, log = self.heard(self.client, "mhm", **data)
            self.assertNotIn("barge", got, data)
            self.assertNotIn("zwischenruf", log, data)

    def test_never_for_guests(self):
        helpers.set_config(barge_hold=True, public=True)
        try:
            guest = TestClient(panel.app)
            self.assertFalse(guest.get("/api/profile/settings").json()["allow"]["barge_hold"])
            got, log = self.heard(guest, "mhm", opened="barge", hold="1")
            self.assertNotIn("barge", got)
        finally:
            helpers.set_config(public=False)

    def test_the_admin_can_block_a_profile(self):
        uid = next(u["id"] for u in __import__("profiles").admin_list()["users"] if u["name"] == "Zwischenrufer")
        helpers.set_config(barge_hold=True, deny={"anhalten": [uid]})
        try:
            got, _ = self.heard(self.client, "mhm", opened="barge", hold="1")
            self.assertNotIn("barge", got)
        finally:
            helpers.set_config(deny={})


class Page(unittest.TestCase):
    def test_the_page_pauses_and_plays_on_by_itself(self):
        with open(os.path.join(JS, "chat.js"), encoding="utf-8") as f:
            js = f.read()
        # one number: the page waits as long as zwischenruf.HOLD_MAX says
        self.assertIn(f"const HOLD_MS={zwischenruf.HOLD_MAX * 1000};", js)
        self.assertIn("ALLOW.barge_hold&&holdAnswer()", js)
        self.assertIn("fd.append('hold','1')", js)
        # paused: the speech context is not woken by the next piece, the hint or the page coming back
        self.assertIn("chat.pctx.state!=='running'&&!chat.held", js)
        self.assertIn("[chat.ctx,chat.held?null:chat.pctx]", js)
        # an error or no decision in time: the answer plays on
        self.assertIn("if(h){resumeAnswer(h);return}", js)
        self.assertIn("setTimeout(()=>resumeAnswer(h),HOLD_MS)", js)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class PageInBrowser(unittest.TestCase):
    """The speech context really stops and plays on: a pause is not woken by the next piece of the stream, "weiter"
    plays on, "Stopp" (stopAnswer) ends it and leaves the context ready for the next answer."""
    @classmethod
    def setUpClass(cls):
        import profiles
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)
        try:
            profiles.add_user("Zwischenseite", "4711")
        except Exception:
            pass

    async def until(self, pg, expr, seconds=10):
        for _ in range(int(seconds * 10)):
            if await pg.evaluate(expr):
                return
            await pg.wait_for_timeout(100)
        self.fail(f"never true: {expr}")

    def test_pause_play_on_and_stop(self):
        async def go():
            async with async_playwright() as p:
                exe = chromium()
                br = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"],
                                             **({"executable_path": exe} if exe else {}))
                try:
                    pg = await (await br.new_context(locale="de-DE")).new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    base = f"http://127.0.0.1:{self.port}"
                    await pg.goto(base + "/")
                    r = await pg.request.post(base + "/api/profile/login", data={"name": "Zwischenseite", "pin": "4711"})
                    self.assertEqual(r.status, 200)
                    await pg.goto(base + "/")
                    await self.until(pg, "typeof PROFILE!=='undefined'&&!!PROFILE&&typeof holdAnswer==='function'")
                    # two seconds of a quiet tone as the answer, the speech context running
                    piece = ("(()=>{const n=48000,a=new Int16Array(n);for(let i=0;i<n;i++)a[i]=Math.round(800*Math.sin(i/9));"
                             "let s='';const b=new Uint8Array(a.buffer);for(let i=0;i<b.length;i++)s+=String.fromCharCode(b[i]);"
                             "return btoa(s)})()")
                    await pg.evaluate(f"playPcm({piece})")
                    await self.until(pg, "chat.pctx.state==='running'&&playing()")
                    self.assertTrue(await pg.evaluate("holdAnswer()"))
                    await self.until(pg, "chat.pctx.state==='suspended'")
                    # the next piece of the stream and the page coming back do not wake it
                    await pg.evaluate(f"playPcm({piece});micBack()")
                    await pg.wait_for_timeout(300)
                    self.assertEqual(await pg.evaluate("chat.pctx.state"), "suspended")
                    self.assertFalse(await pg.evaluate("holdAnswer()"))   # one pause at a time
                    # "weiter": it plays on where it stopped
                    await pg.evaluate("resumeAnswer(chat.held)")
                    await self.until(pg, "chat.pctx.state==='running'&&!chat.held&&playing()")
                    # paused again, then "Stopp": over, and the context runs for the next answer
                    self.assertTrue(await pg.evaluate("holdAnswer()"))
                    await self.until(pg, "chat.pctx.state==='suspended'")
                    await pg.evaluate("stopAnswer()")
                    await self.until(pg, "chat.pctx.state==='running'&&!chat.held&&!playing()")
                    self.assertEqual(errors, [])
                finally:
                    await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
