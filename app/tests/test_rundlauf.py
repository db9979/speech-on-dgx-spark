"""Rundlauf-Wächter (rundlauf.py, plan verbesserungen 3a): off by default, a real round trip with the stage "hinten",
fixed words for the step that hakt, a Störung only after FAIL_N runs in a row and told through the Dienst-Wächter,
left out while someone talks, only numbers kept, a fixed log line for every result."""
import asyncio
import io
import json
import os
import time
import unittest
import wave
from contextlib import redirect_stdout

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import dienstwacht  # noqa: E402
import health  # noqa: E402
import live  # noqa: E402
import rundlauf  # noqa: E402
import update  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PORT = helpers._port()
SEEN = []          # (path, x-spark-stufe) of every request the fake speech services got
HEARD = ["Heute ist ein schöner Tag, und der Spark spricht wieder."]
TTS_CODE = [200]


def _wav(seconds=1.0):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * int(16000 * seconds))
    return buf.getvalue()


def fake_speech():
    app = FastAPI()

    @app.post("/v1/audio/speech")
    async def speech(req: Request):
        SEEN.append(("tts", req.headers.get("x-spark-stufe", "")))
        if TTS_CODE[0] != 200:
            return Response(b'{"detail": "x"}', status_code=TTS_CODE[0], media_type="application/json")
        return Response(_wav(), media_type="audio/wav")

    @app.post("/v1/audio/transcriptions")
    async def asr(req: Request):
        SEEN.append(("asr", req.headers.get("x-spark-stufe", "")))
        return {"text": HEARD[0]}
    return app


helpers._serve(fake_speech(), PORT)


def url(art, path="", cfg=None):
    return f"http://127.0.0.1:{PORT}{path}"


class Rundlauf(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "rundlauf", "rundlauf_min", "svc_watch")
        rundlauf.reset()
        self.addCleanup(rundlauf.reset)
        old = (rundlauf.URL, rundlauf.STARTED)
        rundlauf.URL, rundlauf.STARTED = url, 0
        self.addCleanup(lambda: setattr(rundlauf, "URL", old[0]) or setattr(rundlauf, "STARTED", old[1]))
        SEEN.clear()
        HEARD[0] = health.LIVE_SENTENCE
        TTS_CODE[0] = 200

    def on(self, **kw):
        helpers.set_config(rundlauf=True, svc_watch=True, **kw)

    def run_once(self):
        return asyncio.run(rundlauf.run_once())

    def test_off_by_default(self):
        with open(os.path.join(helpers.APP, "config.default.json"), encoding="utf-8") as f:
            c = json.load(f)["chat"]
        self.assertIs(c["rundlauf"], False)
        self.assertEqual(c["rundlauf_min"], 5)
        helpers.set_config(rundlauf=False)
        self.assertEqual(rundlauf.fuer_status(), {"an": False})
        self.assertEqual(rundlauf.alerts(), [])
        self.assertEqual(rundlauf.for_live(), ({"on": False}, []))
        self.assertIsNone(asyncio.run(rundlauf.tick()))
        helpers.set_config(rundlauf=True, svc_watch=False)   # needs the Dienst-Wächter
        self.assertFalse(rundlauf.an())

    def test_a_good_run_goes_behind_people_and_keeps_numbers_only(self):
        self.on()
        res = self.run_once()
        self.assertTrue(res["ok"], res)
        self.assertEqual(set(res["ms"]), {"tts", "asr", "llm", "ganz"})
        self.assertEqual(SEEN, [("tts", "0"), ("asr", "0")], "the stage hinten: people first")
        self.assertEqual(helpers.LLM_CALLS[-1]["max_tokens"], rundlauf.LLM_TOKENS)
        self.assertEqual(helpers.LLM_CALLS[-1]["messages"], [{"role": "user", "content": rundlauf.LLM_QUESTION}])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(rundlauf.record(res), "")
        self.assertRegex(out.getvalue().strip(), r"^rundlauf: ok tts \d+ asr \d+ llm \d+ ms$")
        with open(rundlauf.FILE, encoding="utf-8") as f:
            kept = json.load(f)
        self.assertEqual(set(kept["runs"][0]), {"t", "ok", "step", "why", "ms"})
        self.assertNotIn("Tag", json.dumps(kept), "nothing of what was said")
        st = rundlauf.fuer_status()
        self.assertTrue(st["an"] and st["letzt"]["ok"])
        self.assertEqual(st["heute"]["ok"], 1)

    def test_the_step_that_hakt_with_a_fixed_word(self):
        self.on()
        HEARD[0] = "Ganz etwas anderes."
        res = self.run_once()
        self.assertEqual((res["ok"], res["step"], res["why"]), (False, "asr", "falsch"))
        self.assertNotIn("llm", res["ms"])
        TTS_CODE[0] = 503
        res = self.run_once()
        self.assertEqual((res["step"], res["why"]), ("tts", "fehler"))
        self.assertEqual([s for s, _ in SEEN].count("asr"), 1, "no Hören without sound")

    def test_two_failures_make_a_stoerung_told_once_and_its_end(self):
        self.on()
        told = []
        old = dienstwacht.warn
        dienstwacht.warn = lambda sid, words, bad, now=None: told.append((sid, words, bad))
        self.addCleanup(lambda: setattr(dienstwacht, "warn", old))
        bad = {"t": int(time.time()), "ok": False, "step": "asr", "why": "falsch", "ms": {"tts": 400, "asr": 300}}
        good = {"t": int(time.time()), "ok": True, "step": "", "why": "", "ms": {"tts": 400, "asr": 300, "llm": 200, "ganz": 900}}
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(rundlauf.record(dict(bad)), "")
            self.assertEqual(rundlauf.alerts(), [])
            self.assertEqual(rundlauf.record(dict(bad)), "stoerung")
            self.assertEqual(rundlauf.record(dict(bad)), "")
        a = rundlauf.alerts()
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["level"], a[0]["go"]), ("bad", "Zustand → Monitoring"))
        self.assertRegex(a[0]["text"], r"^Rundlauf: Hören versteht den Satz nicht \(seit \d\d:\d\d\)\.$")
        self.assertIn(a[0], health.alerts())
        self.assertEqual(told, [("rundlauf", "Hören versteht den Satz nicht", True)])
        self.assertIn("rundlauf", dienstwacht.SVC)
        _svc, hints = rundlauf.for_live()
        self.assertEqual(hints, [{"at": "asr", "level": "bad", "word": "Rundlauf: versteht den Satz nicht"}])
        with redirect_stdout(out):
            self.assertEqual(rundlauf.record(dict(good)), "wieder")
        self.assertEqual(rundlauf.alerts(), [])
        self.assertEqual(told[1:], [("rundlauf", "läuft wieder durch", False)])
        lines = out.getvalue().splitlines()
        self.assertEqual(lines.count("rundlauf: fehler asr falsch"), 3)
        self.assertIn("rundlauf: stoerung asr", lines)
        self.assertIn("rundlauf: wieder ok", lines)

    def test_much_slower_is_a_quiet_line(self):
        self.on()
        now = time.time()
        for i in range(rundlauf.MIN_N + 1):
            rundlauf.record({"t": int(now - 600 + i), "ok": True, "step": "", "why": "",
                             "ms": {"tts": 400, "asr": 300, "llm": 200, "ganz": 900}})
        self.assertEqual(rundlauf.alerts(now), [])
        rundlauf.record({"t": int(now), "ok": True, "step": "", "why": "", "ms": {"tts": 400, "asr": 1500, "llm": 200, "ganz": 2100}})
        a = rundlauf.alerts(now)
        self.assertEqual([(x["level"], x["text"]) for x in a], [("info", "Rundlauf: Hören langsamer als sonst (1,5 s statt 300 ms).")])
        self.assertEqual(rundlauf.fuer_status(now)["langsam"], ["asr"])

    def test_left_out_while_someone_talks(self):
        self.on()
        old = update.talking
        update.talking = lambda now=None: {"now": True, "ago": 3}
        self.addCleanup(lambda: setattr(update, "talking", old))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertIsNone(asyncio.run(rundlauf.tick(time.time() + 3600)))
        self.assertEqual(SEEN, [])
        self.assertIn("rundlauf: ausgelassen gespraech", out.getvalue().splitlines())
        self.assertIn("Gespräch läuft", rundlauf.for_live()[0]["sub"])

    def test_pace_is_checked(self):
        for v, ok in ((2, True), (5, True), (15, True), (7, False), ("5", False), (True, False)):
            self.assertEqual(rundlauf.check({"rundlauf_min": v}) is None, ok, v)
        c = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertEqual(c.post("/api/login", json={"password": "secret-admin"}).status_code, 200)
        cfg = c.get("/api/config").json()
        cfg["chat"]["rundlauf_min"] = 7
        self.assertEqual(c.put("/api/config", json=cfg).status_code, 400)

    def test_on_the_live_page_and_monitoring(self):
        self.on()
        rundlauf.record({"t": int(time.time()), "ok": True, "step": "", "why": "", "ms": {"tts": 400, "asr": 300, "llm": 200, "ganz": 900}})
        snap = live.snapshot("admin")
        box = next(x for x in snap["targets"] if x["id"] == "rundlauf")
        self.assertEqual(box["sub"], "alle 5 min · ok in 900 ms (Sprechen 400 ms · Hören 300 ms · Modell 200 ms)")
        self.assertEqual(rundlauf.fuer_status()["kurve"], [900])


if __name__ == "__main__":
    unittest.main()
