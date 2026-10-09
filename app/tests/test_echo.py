"""The assistant does not answer its own voice (echo.py; admin chat.no_self_echo, per profile "echo"):
off by default, only for profiles, a recording made of what the Spark just said (another device
answering) counts as silence, the speaking pause holds back only other devices of the same profile,
short sentences and the wake word always count, and nothing but the reason reaches the log.

Times are passed in (now=...), so no test depends on the clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import contextlib
import io
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import echo  # noqa: E402
import profiles  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
JS = os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js")
ANSWER = "Morgen wird es sonnig und warm mit zwanzig Grad am Nachmittag."
ASR_TEXT = [""]   # what the fake speech recognition hears next


def fake_asr():
    app = FastAPI()

    @app.post("/v1/audio/transcriptions")
    async def tr(req: Request):
        await req.body()
        return {"text": ASR_TEXT[0], "duration": 3.0}
    return app


ASR_PORT = helpers._port()
helpers._serve(fake_asr(), ASR_PORT)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in profiles.admin_list()["users"] if u["name"] == name)


def heard(client, text):
    ASR_TEXT[0] = text
    wav = b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 16 + (16000).to_bytes(4, "little") + b"\0" * 12 + b"\0" * 32000
    r = client.post("/api/test/asr", files={"file": ("f.wav", wav, "audio/wav")})
    assert r.status_code == 200, r.text
    return r.json()


class Echo(unittest.TestCase):
    def setUp(self):
        echo.clear()
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.port = json.load(f)["asr"]["port"]

    def tearDown(self):
        echo.clear()
        helpers.set_config(no_self_echo=False, self_echo_mode="pause")
        self.asr_port(self.port)

    def asr_port(self, port):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["asr"]["port"] = port
        with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
            json.dump(c, f)

    def test_off_by_default_and_only_for_profiles(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["no_self_echo"], False)
        self.assertEqual(ch["self_echo_mode"], "pause")
        self.assertIs(profiles.SETTINGS["echo"][0], True)
        a = profile("Eva")
        self.assertFalse(a.get("/api/profile/settings").json()["allow"]["echo"])
        # switched off: nothing is kept and nothing is dropped
        self.assertIsNone(echo.said(ANSWER, uid_of("Eva"), "dev:x", now=100))
        self.assertIsNone(echo.check(uid_of("Eva"), "dev:y", ANSWER, 3, now=101))
        helpers.set_config(no_self_echo=True)
        self.assertTrue(a.get("/api/profile/settings").json()["allow"]["echo"])
        helpers.set_config(public=True)
        try:
            self.assertFalse(TestClient(panel.app).get("/api/profile/settings").json()["allow"]["echo"])
        finally:
            helpers.set_config(public=False)
        echo.said(ANSWER, uid_of("Eva"), "dev:x", now=100)
        self.assertIsNone(echo.check(None, "web:guest", ANSWER, 3, now=101))   # never for guests

    def test_own_words_are_dropped_new_ones_not(self):
        helpers.set_config(no_self_echo=True)
        profile("Eva")
        u = uid_of("Eva")
        echo.said(ANSWER, u, "dev:speaker", now=100)
        self.assertEqual(echo.check(u, "dev:phone", ANSWER, 3, now=104), "own voice")
        # half of it, slightly misheard, is still the Spark's own voice
        self.assertEqual(echo.check(u, "dev:phone", "warm mit zwanzig Grad am Nachmittag", 2, now=104), "own voice")
        # a real follow-up with a few of the same words counts
        self.assertIsNone(echo.check(u, "dev:phone", "Und wird es übermorgen auch sonnig?", 2, now=104))
        self.assertIsNone(echo.check(u, "dev:phone", "Wie wird das Wetter in Hamburg morgen?", 2, now=104))
        # short sentences and the wake word always count
        for text in ("Ja", "Stopp", "Ja bitte", "Morgen wird", "Spark, morgen wird es sonnig und warm mit zwanzig Grad"):
            self.assertIsNone(echo.check(u, "dev:phone", text, 1, now=104), text)
        # after 60 seconds it is forgotten
        self.assertIsNone(echo.check(u, "dev:phone", ANSWER, 3, now=100 + echo.KEEP + 1))
        self.assertEqual(echo._pieces, [])

    def test_other_profiles_and_the_profile_switch(self):
        helpers.set_config(no_self_echo=True)
        a = profile("Eva")
        profile("Ole")
        echo.said(ANSWER, uid_of("Ole"), "dev:speaker", now=100)
        # what the Spark said on Ole's speaker is its own voice at Eva's iPhone too
        self.assertEqual(echo.check(uid_of("Eva"), "dev:phone", ANSWER, 3, now=101), "own voice")
        self.assertEqual(a.put("/api/profile/settings", json={"echo": False}).json()["settings"]["echo"], False)
        self.assertIsNone(echo.check(uid_of("Eva"), "dev:phone", ANSWER, 3, now=101))
        for bad in ("nein", 0, None):
            self.assertIs(a.put("/api/profile/settings", json={"echo": bad}).json()["settings"]["echo"], False, bad)
        a.put("/api/profile/settings", json={"echo": True})

    def test_speaking_pause(self):
        helpers.set_config(no_self_echo=True)
        profile("Eva")
        profile("Ole")
        u = uid_of("Eva")
        p = echo.said("Das ist eine lange Antwort.", u, "dev:speaker", start=100, now=100)
        echo.played(p, 110)
        echo.played(p, 105)                       # never moves back
        self.assertEqual(p["t1"], 110)
        # recorded 104-108 on the phone while the speaker talked: garbled words, still dropped
        self.assertEqual(echo.check(u, "dev:phone", "Bas mist eine Bange", 4, now=108), "speaking pause")
        # the speaker itself is never held back ("Stopp" while it speaks)
        self.assertIsNone(echo.check(u, "dev:speaker", "Bas mist eine Bange", 4, now=108))
        # mostly after the answer ended (+1 s): a real question
        self.assertIsNone(echo.check(u, "dev:phone", "Wie spät ist es jetzt", 4, now=114))
        # another profile's device is not held back
        self.assertIsNone(echo.check(uid_of("Ole"), "dev:other", "Bas mist eine Bange", 4, now=108))
        # mode "text": no speaking pause
        helpers.set_config(self_echo_mode="text")
        self.assertIsNone(echo.check(u, "dev:phone", "Bas mist eine Bange", 4, now=108))
        # nonsense lengths are ignored
        helpers.set_config(self_echo_mode="pause")
        for bad in (True, -1, 0, 10_000, "4"):
            self.assertIsNone(echo.check(u, "dev:phone", "Bas mist eine Bange", bad, now=108), bad)

    def test_memory_is_bounded(self):
        helpers.set_config(no_self_echo=True)
        for i in range(echo.MAX_PIECES * 3):
            echo.said("Satz Nummer %d ist hier" % i, None, "dev:x", now=100)
        self.assertEqual(len(echo._pieces), echo.MAX_PIECES)
        p = echo.said(" ".join(["wort"] * 5000), None, "dev:x", now=100)
        self.assertLessEqual(len(p["pairs"]), echo.MAX_WORDS)

    def test_recording_of_the_spark_counts_as_silence(self):
        """A spoken answer through /api/chat, then another browser of the profile records it."""
        self.asr_port(ASR_PORT)
        a = profile("Eva")
        b = profile("Eva")
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "SAY |x| " + ANSWER}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(heard(b, ANSWER)["text"], ANSWER)      # switched off: as before
        helpers.set_config(no_self_echo=True)
        a.post("/api/chat", json={"messages": [{"role": "user", "content": "SAY |x| " + ANSWER}]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = heard(b, ANSWER)
        self.assertEqual(got, {"text": "", "ignored": "own voice"})
        self.assertIn("chat: ignored (own voice)", out.getvalue())
        self.assertNotIn("sonnig", out.getvalue())              # never the text in the log
        self.assertEqual(heard(b, "Wie spät ist es eigentlich gerade?")["text"], "Wie spät ist es eigentlich gerade?")
        # guests are never filtered
        helpers.set_config(public=True)
        try:
            self.assertEqual(heard(TestClient(panel.app), ANSWER)["text"], ANSWER)
        finally:
            helpers.set_config(public=False)

    def test_admin_values_are_checked(self):
        cfg = ADMIN.get("/api/config").json()
        for k, bad in (("no_self_echo", "ja"), ("self_echo_mode", "alles")):
            new = json.loads(json.dumps(cfg))
            new["chat"][k] = bad
            self.assertEqual(ADMIN.put("/api/config", json=new).status_code, 400, k)

    def test_browser_and_profile_page(self):
        with open(os.path.join(JS, "chat.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("ignored:d.ignored||''", js)
        self.assertIn("r.ignored?t('Eigene Stimme überhört.'", js)
        with open(os.path.join(JS, "me.js"), encoding="utf-8") as f:
            self.assertIn("{k:'echo',type:'bool',prof:1,need:'echo'", f.read())


if __name__ == "__main__":
    unittest.main()
