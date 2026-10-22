"""Background voices never become a question (fremdstimme.py, fixed rule): after an answer the browser opened
the microphone by itself and the voices from the TV went to the assistant as a question (Dominik 2026-10-13,
Anfrage d80a75). A recording the page opened by itself (barge-in, follow-up window, hands-free) of a profile
that taught its voice counts only with a known voice; a tapped recording, a short follow-up and a profile
without voiceprint are never held back. The voice comparison is a mock here, nothing depends on the clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
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
import fremdstimme  # noqa: E402
import panel  # noqa: E402
import speakers  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SR = 16000
ASR_TEXT = ["Und dann sagte der Kommissar, dass er den Fall morgen abschließen will, Geheimwort."]
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


def numbers(score, other=-1.0, why=""):
    return {"ok": not why, "why": why, "score": score, "other": other, "need": 0.75, "seconds": 2.0, "here": 0}


class Rule(unittest.TestCase):
    def setUp(self):
        self.verify, self.has = speakers.verify, speakers.has_voice

    def tearDown(self):
        speakers.verify, speakers.has_voice = self.verify, self.has

    def test_only_known_ways_of_opening(self):
        for v in ("barge", "follow", "hands", " Barge "):
            self.assertEqual(fremdstimme.opened(v), v.strip().lower())
        for v in ("", "tap", "wake", "barge; rm", None, 3, "x" * 50, "car"):
            self.assertEqual(fremdstimme.opened(v), "", v)
        self.assertNotIn("car", fremdstimme.OPEN)   # the car's microphone is never compared (CarPlay follow-ups)

    def test_checked_only_with_a_voiceprint_and_speaker_recognition(self):
        speakers.has_voice = lambda uid: True
        on = {"chat": {"speaker_id": True}}
        self.assertTrue(fremdstimme.applies(on, "u1", "barge"))
        self.assertFalse(fremdstimme.applies({"chat": {"speaker_id": False}}, "u1", "barge"))
        self.assertFalse(fremdstimme.applies(on, "u1", ""))           # tapped: the person's own decision
        self.assertFalse(fremdstimme.applies(on, None, "follow"))     # guests: no voice is compared
        speakers.has_voice = lambda uid: False
        self.assertFalse(fremdstimme.applies(on, "u1", "hands"))      # no voiceprint, nothing to compare

    def test_known_voices_count_strangers_not(self):
        cases = [
            (numbers(0.82), None),                                              # the profile itself
            (numbers(0.40, why=fremdstimme.SHORT), None),                       # "Und morgen?": too short to tell
            (numbers(0.40, other=0.85, why="voice not recognized"), None),      # another profile of the household
            (numbers(0.78, other=0.76, why="too close to another profile's voice"), None),
            (numbers(0.0, why="the profile has not taught its voice"), None),
            (numbers(0.52, other=0.31, why="voice not recognized"), "foreign voice"),   # the TV
            (numbers(0.52, other=0.78, why="voice not recognized"), None),
            (numbers(0.60, other=0.62, why="voice not recognized"), "foreign voice"),   # nobody clearly
        ]
        for v, want in cases:
            speakers.verify = lambda uid, data, th, _v=v: dict(_v)
            self.assertEqual(fremdstimme.check("u1", b"", 0.75)[0], want, v)


class Endpoint(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.port = json.load(f)["asr"]["port"]
        self.set_port(ASR_PORT)
        helpers.set_config(speaker_id=True)
        self.verify, self.has, self.identify = speakers.verify, speakers.has_voice, speakers.identify
        speakers.has_voice = lambda uid: True
        speakers.identify = lambda data, th=0.75: (None, 0.3)
        self.client = profile("Fernsehabend")

    def tearDown(self):
        speakers.verify, speakers.has_voice, speakers.identify = self.verify, self.has, self.identify
        helpers.set_config(speaker_id=False)
        self.set_port(self.port)

    def set_port(self, port):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["asr"]["port"] = port
        helpers.write_config(c)

    def heard(self, opened, v):
        speakers.verify = lambda uid, data, th, did=None: dict(v)
        data = {"language": "de"}
        if opened is not None:
            data["opened"] = opened
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.client.post("/api/test/asr", files={"file": ("frage.wav", speech(), "audio/wav")}, data=data)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json(), out.getvalue()

    def test_tv_after_an_answer_is_no_question(self):
        tv = numbers(0.48, other=0.2, why="voice not recognized")
        for how in ("barge", "follow", "hands"):
            got, log = self.heard(how, tv)
            self.assertEqual(got, {"text": "", "ignored": "foreign voice"}, how)
            self.assertIn("chat: ignored (foreign voice, ", log)
            self.assertIn("match 0.48 of 0.75 needed", log)
            self.assertNotIn("Geheimwort", log)
            self.assertNotIn("Fernsehabend", log)

    def test_own_voice_short_follow_ups_and_taps_still_count(self):
        got, log = self.heard("follow", numbers(0.83))
        self.assertEqual(got["text"], ASR_TEXT[0])
        self.assertIn("chat: open microphone voice checked (follow-up window)", log)
        self.assertIn("| known voice |", log)
        got, log = self.heard("barge", numbers(0.3, why=fremdstimme.SHORT))
        self.assertEqual(got["text"], ASR_TEXT[0])
        self.assertIn("too short to check", log)
        # a tapped "Sprechen" is never compared, whatever the voice
        for opened in (None, "", "tap"):
            got, log = self.heard(opened, numbers(0.1, why="voice not recognized"))
            self.assertEqual(got["text"], ASR_TEXT[0], opened)
            self.assertNotIn("open microphone", log)

    def test_without_speaker_recognition_nothing_is_compared(self):
        helpers.set_config(speaker_id=False)
        got, _ = self.heard("barge", numbers(0.1, why="voice not recognized"))
        self.assertEqual(got["text"], ASR_TEXT[0])


class Browser(unittest.TestCase):
    """The page says how the microphone opened and learns the room level while the answer plays."""
    def setUp(self):
        with open(os.path.join(JS, "chat.js"), encoding="utf-8") as f:
            self.js = f.read()

    def test_page_names_how_the_microphone_opened(self):
        js = self.js
        self.assertIn("rec.opened=o.opened||(o.speaking?'barge':o.follow?'follow':'');", js)
        self.assertIn("if(opened)fd.append('opened',opened);", js)
        self.assertIn("asrText(blob,opened,h)", js)
        self.assertIn("rec.opened,null,tt)", js[js.index("function liveSnap("):])
        self.assertEqual(js.count("startListening({opened:'hands'})"), 2)
        self.assertIn("startListening({rec,parts,floor,speaking:true,held:", js)     # barge-in (paused or ended, zwischenruf.py)
        # the tap and "Hey Spark" stay unmarked
        self.assertIn("if(chat.rec)stopListening(false);else startListening()};", js)
        self.assertIn("chime();wake.busy=false;startListening()", js)
        self.assertIn("/foreign/.test(r.ignored)", js)

    def test_a_voice_must_stand_out_from_the_room(self):
        js = self.js
        self.assertRegex(js, r"const BARGE=\{low:\[[\d.]+,\d+,[\d.]+,[\d.]+\],mid:\[[\d.]+,\d+,[\d.]+,[\d.]+\],high:")
        barge = js[js.index("function startBarge("):js.index("function stopBarge(")]
        self.assertIn("const gate=Math.max(thr*0.7,amb*b[3]);", barge)
        self.assertIn("if(out<0.004&&m<=gate)", barge)      # learned only while the Spark is quiet, never from a voice
        self.assertIn("amb*b[3]*0.8", barge)
        vad = js[js.index("function startVad("):js.index("function stopVad(")]
        self.assertIn("o.follow||o.opened==='hands'?roomLevel()*2:0", vad)
        self.assertTrue(re.search(r"rms>Math\.max\(0\.015,floor\*2\.5,amb\)", vad))


class App(unittest.TestCase):
    """The iPhone app says the same when it opened the microphone by itself (barge-in, hands-free)."""
    def test_swift_names_how_the_microphone_opened(self):
        root = os.path.join(os.path.dirname(__file__), "..", "..", "ios")
        if not os.path.exists(os.path.join(root, "Spark", "Assistant.swift")):
            self.skipTest("copy with app/ only")
        with open(os.path.join(root, "Spark", "Assistant.swift"), encoding="utf-8") as f:
            a = f.read()
        with open(os.path.join(root, "Shared", "SparkAPI.swift"), encoding="utf-8") as f:
            api = f.read()
        self.assertIn('listen(preroll: 0.6, fromWake: false, opened: "barge")', a)
        self.assertIn('listen(preroll: 0, fromWake: false, opened: "hands")', a)
        self.assertIn("api.transcribe(wav: wav, language: Store.language, opened: how,", a)
        self.assertIn('let woke = fromWake, how = inCar ? "car" : opened, asked = held', a)   # never a voiceprint in the car
        self.assertIn('name=\\"opened\\"', api)


if __name__ == "__main__":
    unittest.main()
