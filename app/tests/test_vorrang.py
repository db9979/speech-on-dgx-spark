"""Speech first (vorrang.py, V01.0.225): background work waits while somebody speaks, its requests to
the language model are cancelled when speech starts, speech services mark themselves, the systemd
units give speech the larger share. No test depends on the time of day."""
import asyncio
import os
import re
import tempfile
import threading
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
import common  # noqa: E402
import vorrang  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)


def _read(path):
    with open(path) as f:
        return f.read()
ADMIN.post("/api/login", json={"password": "secret-admin"})


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = (vorrang.GRACE, vorrang.MARK, vorrang.POLL, common.SPEECH_MARK)
        vorrang.GRACE, vorrang.POLL = 20, 0.01
        vorrang.MARK = common.SPEECH_MARK = os.path.join(self.dir, "speech-active")
        vorrang._local[0] = 0.0
        common._speech_marked[0] = 0.0

    def tearDown(self):
        vorrang.GRACE, vorrang.MARK, vorrang.POLL, common.SPEECH_MARK = self.saved
        vorrang._local[0] = 0.0

    def silence(self):
        vorrang._local[0] = 0.0
        if os.path.exists(vorrang.MARK):
            os.remove(vorrang.MARK)


class Speaking(Base):
    def test_speaking_until_grace_after_the_last_speech(self):
        now = 1_000_000.0
        vorrang.mark(now)
        self.assertTrue(vorrang.speaking(now + 19))
        self.assertFalse(vorrang.speaking(now + 21))

    def test_mark_of_another_process_counts(self):
        now = time.time()
        common.speech_mark(now, vorrang.MARK)          # e.g. the TTS service
        self.assertEqual(vorrang._local[0], 0.0)
        self.assertTrue(vorrang.speaking(now + 1))
        self.assertFalse(vorrang.speaking(now + 30))

    def test_mark_rate_limit_but_end_always_written(self):
        common.speech_mark(100.0, vorrang.MARK)
        common.speech_mark(100.5, vorrang.MARK)
        self.assertEqual(os.path.getmtime(vorrang.MARK), 100.0)
        common.speech_mark(100.6, vorrang.MARK, end=True)
        self.assertAlmostEqual(os.path.getmtime(vorrang.MARK), 100.6, places=3)

    def test_mark_never_fails(self):
        common.speech_mark(1.0, "/nonexistent-dir/speech-active")   # no exception


class Gate(Base):
    def test_quiet_waits_while_somebody_speaks(self):
        vorrang.mark()
        slept = []

        async def sleep(s):
            slept.append(s)
            self.silence()
        asyncio.run(vorrang.quiet("Test", sleep=sleep))
        self.assertEqual(len(slept), 1)
        self.assertGreaterEqual(vorrang.today()["held"], 1)

    def test_no_wait_in_a_pause(self):
        async def sleep(s):
            raise AssertionError("must not wait")
        self.assertEqual(asyncio.run(vorrang.quiet("Test", sleep=sleep)), 0)

    def test_running_request_is_cancelled_when_speech_starts_and_repeated(self):
        attempts, cancelled = [], []

        async def sleep(s):
            self.silence()

        async def work():
            attempts.append(1)
            if len(attempts) == 1:
                try:
                    vorrang.mark()                  # somebody starts talking while it runs
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.append(1)
                    raise
            return "fertig"
        before = vorrang.today()["cancelled"]
        self.assertEqual(asyncio.run(vorrang.run("Test", work, sleep=sleep)), "fertig")
        self.assertEqual((len(attempts), len(cancelled)), (2, 1))
        self.assertEqual(vorrang.today()["cancelled"], before + 1)

    def test_gives_up_after_retries(self):
        async def sleep(s):
            self.silence()

        async def work():
            vorrang.mark()
            await asyncio.sleep(30)
        with self.assertRaises(vorrang.Busy):
            asyncio.run(vorrang.run("Test", work, retries=2, sleep=sleep))

    def test_one_background_request_at_a_time(self):
        running, most = [0], [0]

        async def work():
            running[0] += 1
            most[0] = max(most[0], running[0])
            await asyncio.sleep(0.02)
            running[0] -= 1

        async def both():
            await asyncio.gather(*[vorrang.run("Test", work) for _ in range(3)])
        asyncio.run(both())
        self.assertEqual(most[0], 1)

    def test_thread_work_runs_with_low_priority(self):
        def nice():
            return os.getpriority(os.PRIO_PROCESS, threading.get_native_id())
        mine = os.getpriority(os.PRIO_PROCESS, 0)
        got = asyncio.run(vorrang.in_thread("Test", nice))
        self.assertGreaterEqual(got, min(vorrang.LOW_NICE, 19) if mine <= vorrang.LOW_NICE else mine)
        self.assertEqual(os.getpriority(os.PRIO_PROCESS, 0), mine)   # the panel itself stays as it was

    def test_thread_errors_reach_the_caller(self):
        def boom():
            raise ValueError("x")
        with self.assertRaises(ValueError):
            asyncio.run(vorrang.in_thread("Test", boom))

    def test_hold_in_a_worker_thread(self):
        vorrang.mark()
        waits = []
        vorrang.hold("Test", sleep=lambda s: (waits.append(s), self.silence()))
        self.assertEqual(len(waits), 1)


class Services(Base):
    def app(self):
        a = FastAPI()

        @a.post("/v1/audio/speech")
        def speech():
            return {"ok": True}

        @a.get("/v1/audio/voices")
        def voices():
            return []
        a.add_middleware(common.SpeechMark)
        return TestClient(a)

    def test_speech_request_marks_and_other_requests_do_not(self):
        c = self.app()
        c.get("/v1/audio/voices")
        self.assertFalse(os.path.exists(vorrang.MARK))
        c.post("/v1/audio/speech")
        self.assertTrue(vorrang.speaking())

    def test_every_speech_service_has_the_mark_inside_the_key_check(self):
        for name in ("tts_proxy.py", "tts_server.py", "asr_proxy.py", "asr_server.py"):
            src = _read(os.path.join(helpers.APP, name))
            mark, limit = src.find("app.add_middleware(SpeechMark)"), src.find("app.add_middleware(BodyLimit")
            self.assertTrue(0 < mark < limit, name)   # added first = innermost: a request without key never counts


class Panel(Base):
    def test_an_answer_counts_as_speech(self):
        r = ADMIN.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(vorrang.speaking())

    def test_reading_uploads_waits_while_somebody_speaks(self):
        import wissen
        chat._last_chat[0] = 0
        self.assertTrue(wissen.quiet())
        vorrang.mark()
        self.assertFalse(wissen.quiet())

    def test_learning_waits_while_somebody_speaks(self):
        vorrang.mark()
        self.assertEqual(asyncio.run(chat.learn_once()), 0)

    def test_background_model_calls_go_through_the_gate(self):
        for name in ("chat.py", "agent.py", "memtidy.py", "proactive.py", "quality.py", "wissen.py"):
            src = _read(os.path.join(helpers.APP, "panel", name))
            self.assertIn("vorrang.post(", src, name)
        self.assertIn('vorrang.hold("Mail sortieren")', _read(os.path.join(helpers.APP, "panel", "tidy.py")))
        self.assertIn('vorrang.in_thread("Sicherung"', _read(os.path.join(helpers.APP, "panel", "panel.py")))

    def test_endpoints_need_the_admin(self):
        anon = TestClient(panel.app)
        self.assertIn(anon.get("/api/vorrang").status_code, (401, 403))
        self.assertIn(anon.post("/api/vorrang").status_code, (401, 403))
        d = ADMIN.get("/api/vorrang").json()
        self.assertIn("held", d["today"])

    def test_second_start_is_refused(self):
        vorrang._test["running"] = True
        try:
            self.assertEqual(ADMIN.post("/api/vorrang").status_code, 409)
        finally:
            vorrang._test["running"] = False

    def test_verdict_rules(self):
        a = {"first": 0.5, "rtf": 0.5}
        self.assertEqual(vorrang.verdict({"alone": a})["level"], "warn")
        self.assertEqual(vorrang.verdict({"alone": a, "load": a, "vorrang": a})["level"], "ok")
        slow = {"first": 2.0, "rtf": 0.9}
        v = vorrang.verdict({"alone": a, "load": slow, "vorrang": a})
        self.assertEqual(v["level"], "ok")
        self.assertIn("gleicht", v["title"]["de"])
        self.assertEqual(vorrang.verdict({"alone": a, "load": slow, "vorrang": slow})["level"], "bad")


class Logs(unittest.TestCase):
    def test_log_lines_have_their_own_area(self):
        import logfilter
        line = "2026-01-01T10:00:00+0000 tars p[1]: vorrang: Lernen aus Gesprächen wartet (Gespräch)"
        self.assertEqual(logfilter.parse(line)["area"], "vorrang")


class Units(unittest.TestCase):
    def test_speech_units_get_the_larger_share(self):
        src = _read(os.path.join(helpers.APP, "..", "install.sh"))
        for unit in ("speech-spark-asr.service", "speech-spark-tts.service", "speech-spark-$1.service"):
            body = src[src.index(unit):]
            body = body[:body.index("\nEOF")]
            for want in ("Nice=-5", "CPUWeight=1000", "IOWeight=1000", "OOMScoreAdjust=500"):
                self.assertIn(want, body, unit)
        panel_unit = src[src.index("speech-spark-panel.service"):]
        panel_unit = panel_unit[:panel_unit.index("\nEOF")]
        self.assertEqual(re.search(r"OOMScoreAdjust=(\d+)", panel_unit).group(1), "900")   # panel goes first


if __name__ == "__main__":
    unittest.main()
