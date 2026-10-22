"""Satzende am Tonfall: messen (satzende.py on the panel, smartturn.py and POST /v1/turn on the model computer; admin
chat.turn_tone, off by default). Smart Turn only measures: a pause snapshot gets an id, the page reports later what the
word list said and whether the voice went on, and only these numbers are kept and logged. Never words, never a
profile, never guests; nothing is decided with it. The model file is checked against its SHA-256 before it loads.
Nothing here depends on the clock (the times are given).

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
import unittest
import wave

import numpy as np

from tests import helpers

helpers.start()
import panel  # noqa: E402
import satzende  # noqa: E402
import smartturn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SR = 16000
TURN = [{"p": 0.9, "ms": 12}]
JS = os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js")


def wav(seconds=2.0, rate=SR):
    t = np.arange(int(seconds * rate)) / rate
    x = (0.2 * np.sin(2 * np.pi * (180 + 60 * np.sin(2 * np.pi * 4 * t)) * t)).astype(np.float32)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return b.getvalue()


def fake_asr():
    app = FastAPI()

    @app.post("/v1/audio/transcriptions")
    async def tr(req: Request):
        await req.body()
        return {"text": "Wie wird das Wetter in Leipzig", "duration": 2.0}

    @app.post("/v1/turn")
    async def turn(req: Request):
        body = await req.body()
        smartturn.pcm(body)   # the panel sends what the model computer takes: 16 kHz mono WAV, at most 8 s
        TURN.append(len(body))
        return TURN[0]
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


class Measure(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        self.port = c["asr"]["port"]
        c["asr"]["port"] = ASR_PORT
        helpers.write_config(c)
        self.client = profile("Satzender")
        satzende._pending.clear()
        if os.path.exists(satzende.FILE):
            os.remove(satzende.FILE)

    def tearDown(self):
        helpers.set_config(turn_tone=False, public=False, deny={})
        TURN[0] = {"p": 0.9, "ms": 12}
        satzende._pending.clear()
        if os.path.exists(satzende.FILE):
            os.remove(satzende.FILE)
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["asr"]["port"] = self.port
        helpers.write_config(c)

    def heard(self, client, **data):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = client.post("/api/test/asr", files={"file": ("frage.wav", wav(), "audio/wav")},
                            data=dict({"language": "de"}, **data))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json(), out.getvalue()

    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["turn_tone"], False)
        self.assertFalse(self.client.get("/api/profile/settings").json()["allow"]["turn_tone"])
        got, log = self.heard(self.client, turn="1")
        self.assertNotIn("turn", got)
        self.assertEqual(satzende._pending, {})

    def test_only_numbers_are_kept_and_logged(self):
        helpers.set_config(turn_tone=True)
        got, _ = self.heard(self.client, turn="1")
        key = got["turn"]
        self.assertRegex(key, r"^[A-Za-z0-9_-]{12}$")
        self.assertEqual(got["text"], "Wie wird das Wetter in Leipzig")   # the recognition itself is unchanged
        self.assertLessEqual(TURN[-1], 44 + 2 * SR * smartturn.SECONDS)    # only the end of the recording goes out
        _, log = self.heard(self.client, turns=f"{key}:neutral:0")
        self.assertIn("hoeren: satzende p=0.90 regel=neutral weiter=nein ms=12", log)
        with open(satzende.FILE) as f:
            kept = f.read()
        self.assertEqual(json.loads(kept)["rows"], [[0.9, "neutral", 0, 12]])
        for words in ("Leipzig", "Wetter", "Satzender"):
            self.assertNotIn(words, kept)
            self.assertNotIn(words, log)
        s = ADMIN.get("/api/admin/satzende").json()
        self.assertEqual((s["n"], s["hits"], s["false"]), (1, 1, 0))
        self.assertEqual(s["saved_s"], (satzende.END_MS - satzende.PAUSE_MS) / 1000)
        # the same id twice, someone else's id, or a made-up report: no row
        _, log = self.heard(self.client, turns=f"{key}:neutral:0,xxxxxxxxxxxx:fertig:1,<script>")
        self.assertEqual(log.count("hoeren: satzende unbekannt"), 3)
        self.assertEqual(satzende.summary()["n"], 1)

    def test_a_missing_model_changes_nothing(self):
        helpers.set_config(turn_tone=True)
        TURN[0] = {"detail": "turn model not installed"}
        got, _ = self.heard(self.client, turn="1")
        _, log = self.heard(self.client, turns=f"{got['turn']}:offen:1")
        self.assertIn("hoeren: satzende p=none regel=offen weiter=ja ms=-", log)
        self.assertEqual(satzende.summary()["rated"], 0)

    def test_another_profile_cannot_report(self):
        helpers.set_config(turn_tone=True)
        got, _ = self.heard(self.client, turn="1")
        other = profile("Andere Satzende")
        _, log = self.heard(other, turns=f"{got['turn']}:fertig:0")
        self.assertIn("hoeren: satzende unbekannt", log)
        self.assertEqual(satzende.summary()["n"], 0)

    def test_never_guests_and_the_admin_can_block(self):
        helpers.set_config(turn_tone=True, public=True)
        guest = TestClient(panel.app)
        self.assertFalse(guest.get("/api/profile/settings").json()["allow"]["turn_tone"])
        got, _ = self.heard(guest, turn="1")
        self.assertNotIn("turn", got)
        uid = next(u["id"] for u in __import__("profiles").admin_list()["users"] if u["name"] == "Satzender")
        helpers.set_config(deny={"satzende": [uid]})
        got, _ = self.heard(self.client, turn="1")
        self.assertNotIn("turn", got)

    def test_it_stops_after_its_rows_or_days(self):
        satzende._pending.clear()
        from common import write_json
        write_json(satzende.FILE, {"since": 1000.0, "rows": [[0.5, "neutral", 0, 9]] * satzende.ROWS})
        self.assertFalse(satzende.measuring(now=1001.0))
        write_json(satzende.FILE, {"since": 1000.0, "rows": [[0.5, "neutral", 0, 9]]})
        self.assertTrue(satzende.measuring(now=1000.0 + satzende.DAYS * 86400 - 1))
        self.assertFalse(satzende.measuring(now=1000.0 + satzende.DAYS * 86400))


class Summary(unittest.TestCase):
    def test_hits_false_alarms_and_saved_time(self):
        rows = [[0.95, "neutral", 0, 10], [0.85, "fertig", 0, 20], [0.9, "neutral", 1, 30], [0.1, "offen", 1, 40],
                [None, "neutral", 0, None], [0.5, "neutral", 0, 50]]
        from common import write_json
        write_json(satzende.FILE, {"since": 5.0, "rows": rows})
        try:
            s = satzende.summary(now=6.0)
        finally:
            os.remove(satzende.FILE)
        self.assertEqual((s["n"], s["rated"], s["hits"], s["false"], s["low_right"]), (6, 5, 2, 1, 1))
        self.assertEqual(s["saved_s"], (satzende.END_MS - satzende.PAUSE_MS) / 1000)   # only the neutral hit waited
        self.assertEqual(s["ms"], 30)


class Page(unittest.TestCase):
    def test_the_page_reports_pauses_with_the_next_recording(self):
        with open(os.path.join(JS, "chat.js"), encoding="utf-8") as f:
            js = f.read()
        # one number each: satzende knows when the page takes its snapshot and when it ends the turn
        self.assertIn(f"if(quiet>={satzende.PAUSE_MS})", js)
        self.assertIn(f"quiet>(chat.turnWait||{satzende.END_MS})", js)
        self.assertIn("tt=pause&&ALLOW.turn_tone", js)
        self.assertIn("if(turn)fd.append('turn','1')", js)
        self.assertIn("fd.append('turns',chat.turnOut.splice(0,8).join(','))", js)
        # the words never go out: only the word list's verdict
        self.assertIn("({done:'fertig',open:'offen'}[p.st]||'neutral')", js)


class Model(unittest.TestCase):
    def test_features_hear_the_last_eight_seconds(self):
        rng = np.random.default_rng(3)
        x = (0.1 * rng.standard_normal(SR * 3)).astype(np.float32)
        f = smartturn.features(x)
        self.assertEqual(f.shape, (80, 800))
        self.assertEqual(f.dtype, np.float32)
        # shorter recordings get silence in front, longer ones keep their end
        np.testing.assert_array_equal(f, smartturn.features(np.concatenate([np.zeros(SR * 2, np.float32), x])))
        long = np.concatenate([(0.3 * rng.standard_normal(SR * 6)).astype(np.float32), x, x, x])
        np.testing.assert_array_equal(smartturn.features(long), smartturn.features(np.concatenate([x[SR:], x, x])))
        self.assertLessEqual(float(f.max()), 1.5)

    def test_only_a_checked_model_loads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.onnx")
            with open(path, "wb") as f:
                f.write(b"not the model")
            old, smartturn.MODEL, smartturn._session = smartturn.MODEL, path, None
            try:
                self.assertTrue(smartturn.present())
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    smartturn.predict(np.zeros(SR, np.float32))
                self.assertIsNone(smartturn._session)
            finally:
                smartturn.MODEL = old
        self.assertNotEqual(hashlib.sha256(b"not the model").hexdigest(), smartturn.MODEL_SHA256)

    def test_only_16k_mono_wav_of_limited_size(self):
        self.assertEqual(smartturn.pcm(wav(1.0)).shape, (SR,))
        for bad in (wav(1.0, rate=8000), b"RIFF....WAVE", b"x" * (smartturn.MAX_BYTES + 1)):
            with self.assertRaises(ValueError):
                smartturn.pcm(bad)

    def test_the_service_answers_only_with_a_model(self):
        import asr_proxy
        key = asr_proxy.load_config().get("api", {}).get("key") or ""
        c = TestClient(asr_proxy.app)
        h = {"Authorization": "Bearer " + key}
        old = smartturn.present, smartturn.predict
        try:
            smartturn.present = lambda: False
            self.assertEqual(c.post("/v1/turn", content=wav(1.0), headers=h).status_code, 503)
            smartturn.present = lambda: True
            smartturn.predict = lambda audio: (0.77, 5)
            r = c.post("/v1/turn", content=wav(1.0), headers=h)
            self.assertEqual(r.json(), {"p": 0.77, "ms": 5})
            self.assertEqual(c.post("/v1/turn", content=b"no wav", headers=h).status_code, 415)
            self.assertEqual(c.post("/v1/turn", content=b"x" * (smartturn.MAX_BYTES + 1), headers=h).status_code, 413)
        finally:
            smartturn.present, smartturn.predict = old

    def test_install_checks_wheel_and_model(self):
        root = os.path.join(os.path.dirname(__file__), "..", "..", "install.sh")
        if not os.path.exists(root):
            self.skipTest("copy with app/ only")
        with open(root, encoding="utf-8") as f:
            sh = f.read()
        self.assertIn('[ "$(sha256sum "$stmp/w.whl" | cut -c1-64)" = "$ST_WHEEL" ]', sh)
        self.assertIn('[ "$(sha256sum "$stmp/m.onnx" | cut -c1-64)" = "$ST_SHA" ]', sh)
        self.assertTrue(re.search(r"^WHEEL_SHA256 = \"[0-9a-f]{64}\"$", open(smartturn.__file__).read(), re.M))


if __name__ == "__main__":
    unittest.main()
