"""Silence never becomes words (stille.py, fixed rule): after an answer the app listened again and a
click, its chime or the room came back from the speech recognition as "Ja" or "Okay", which went to
the assistant as a question nobody asked (Dominik 2026-10-13). A recording without voice, a known
sentence of silence ("Untertitel im Auftrag des ZDF") and a lone short word from a recording with
hardly any voice give no text; a real "Ja", a short question and the wake word still count.

The recordings are made up here (tone bursts in a quiet room), nothing depends on the clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import io
import json
import os
import unittest
import wave

import numpy as np

from tests import helpers

helpers.start()
import panel  # noqa: E402
import stille  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SR = 16000
ASR_TEXT = [""]   # what the fake speech recognition hears next
ASR_CALLS = [0]


def recording(voice_s, total_s=2.0, level=0.2, room=0.001, seed=1):
    """A quiet room with voice_s seconds of a loud, changing tone in the middle (float, 16 kHz)."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, room, int(total_s * SR)).astype(np.float32)
    n = int(voice_s * SR)
    if n:
        t = np.arange(n) / SR
        a = int((len(x) - n) / 2)
        x[a:a + n] += (level * np.sin(2 * np.pi * (180 + 60 * np.sin(2 * np.pi * 4 * t)) * t)).astype(np.float32)
    return x


def wav_bytes(x):
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
        ASR_CALLS[0] += 1
        return {"text": ASR_TEXT[0], "duration": 2.0}
    return app


ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


ASR_PORT = helpers._port()
helpers._serve(fake_asr(), ASR_PORT)


class Rule(unittest.TestCase):
    def test_voice_is_measured(self):
        self.assertLess(stille.voiced_seconds(recording(0)), stille.MIN_VOICED)
        self.assertLess(stille.voiced_seconds(np.zeros(SR, np.float32)), stille.MIN_VOICED)
        self.assertAlmostEqual(stille.voiced_seconds(recording(0.6)), 0.6, delta=0.07)
        # a noisy room is no voice, a word over it is
        self.assertLess(stille.voiced_seconds(recording(0, room=0.02)), stille.MIN_VOICED)
        self.assertGreater(stille.voiced_seconds(recording(0.4, room=0.02)), stille.FILLER_VOICED)
        # speech from end to end (no pause around it) still counts
        self.assertGreater(stille.voiced_seconds(recording(1.0, total_s=1.0)), 0.8)
        self.assertEqual(stille.voiced_seconds(np.zeros(10, np.float32)), 0.0)

    def test_silence_gives_no_text_whatever_was_recognized(self):
        for text in ("Ja.", "Okay.", "Wie wird das Wetter morgen?", ""):
            self.assertEqual(stille.check(text, 0.0), "silence", text)
            self.assertEqual(stille.check(text, 0.05), "silence", text)

    def test_sentences_of_silence(self):
        for text in ("Untertitel im Auftrag des ZDF, 2020", "Untertitelung des ZDF für funk, 2017",
                     "Vielen Dank fürs Zuschauen!", "Thanks for watching!", "Copyright WDR 2021",
                     "Untertitel der Amara.org-Community", "[Musik]", "(Applaus)", "♪♪", "*Musik*"):
            self.assertEqual(stille.check(text, 1.5), "silence phrase", text)
        for text in ("Untertitel einschalten", "Spiel Musik", "Musik", "Danke", "Thank you"):
            self.assertIsNone(stille.check(text, 1.5), text)

    def test_lone_short_word_needs_voice(self):
        for text in ("Ja.", "Okay", "OK!", "ja ja", "Hm.", "Danke.", "Yes.", "Thanks"):
            self.assertEqual(stille.check(text, 0.15), "too short", text)
            self.assertIsNone(stille.check(text, 0.3), text)          # a spoken "Ja" is longer
        for text in ("Ja, mach das", "Licht an", "Stopp", "ja nein"):
            self.assertIsNone(stille.check(text, 0.15), text)

    def test_unreadable_audio_only_checks_the_text(self):
        self.assertIsNone(stille.check("Ja.", None))
        self.assertEqual(stille.check("Untertitel im Auftrag des ZDF", None), "silence phrase")
        self.assertIsNone(stille.measure(b"not audio"))


class Endpoint(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.port = json.load(f)["asr"]["port"]
        self.set_port(ASR_PORT)
        self.client = profile("Stella")

    def tearDown(self):
        self.set_port(self.port)

    def set_port(self, port):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["asr"]["port"] = port
        helpers.write_config(c)

    def heard(self, text, x):
        ASR_TEXT[0] = text
        r = self.client.post("/api/test/asr", files={"file": ("frage.wav", wav_bytes(x), "audio/wav")},
                             data={"language": "de"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_silence_after_an_answer_is_no_question(self):
        out = self.heard("Ja.", recording(0))
        self.assertEqual(out, {"text": "", "ignored": "silence"})
        self.assertEqual(self.heard("Okay.", recording(0.12))["ignored"], "too short")
        self.assertEqual(self.heard("Untertitel im Auftrag des ZDF, 2020", recording(1.2))["ignored"], "silence phrase")

    def test_real_words_still_count(self):
        self.assertEqual(self.heard("Ja.", recording(0.35))["text"], "Ja.")
        self.assertEqual(self.heard("Wie spät ist es?", recording(0.9))["text"], "Wie spät ist es?")

    def test_the_log_names_only_the_reason(self):
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.heard("Okay geheim", recording(0))
        line = buf.getvalue()
        self.assertIn("chat: ignored (silence)", line)
        self.assertNotIn("geheim", line)


class App(unittest.TestCase):
    """The iPhone app records no chime and needs some voice before a recording counts."""
    def test_swift_listens_only_to_voice(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "ios", "Spark", "Assistant.swift")
        if not os.path.exists(path):
            self.skipTest("copy with app/ only")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("guard now >= deafUntil else { return }", src)
        self.assertIn("if loud >= Self.minSpeech { heard = true }", src)


if __name__ == "__main__":
    unittest.main()
