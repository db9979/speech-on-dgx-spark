"""Leistung messen (V01.0.163): every number gets a level and a sentence from fixed rules in bench.rate(),
the ASR part counts the words it got right, and the last ten runs are kept for the comparison."""
import json
import os
import unittest

from tests import helpers

helpers.start()
import bench  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def result(ttfa=0.62, rtf=0.38, tts_par=3.1, tts_first_max=2.37, asr_s=0.94, acc=0.98, asr_par=30.7, free=10.4,
           qwen38=("qwen38-flash.service",), errors=()):
    """A measurement like one from tars (time fixed, nothing depends on the clock)."""
    return {"time": 1760000000, "host": "tars", "qwen38_active": list(qwen38), "errors": list(errors),
            "config": {"tts": {"model": "m", "backend": "vllm-omni"}, "asr": {"model": "m", "backend": "b"}},
            "tts": {"streaming": True, "single": {"ttfa_s": ttfa, "total_s": 6.0, "audio_s": 15.8, "rtf": rtf},
                    "parallel": {"n": 4, "wall_s": 20, "ttfa_s": 1.4, "ttfa_max_s": tts_first_max, "x_realtime": tts_par}},
            "asr": {"audio_s": 15.8, "single": {"total_s": asr_s, "rtf": 0.06}, "parallel": {"n": 8, "wall_s": 4,
                                                                                            "x_realtime": asr_par},
                    "heard": bench.TEXT, "accuracy": acc},
            "memory_after": {"mem_available_gib": free, "units": {}}}


def rows(r, prev=None):
    return {x["key"]: x for g in bench.rate(r, prev)["groups"] for x in g["rows"]}


class Rating(unittest.TestCase):
    def test_every_value_gets_a_level_and_a_sentence(self):
        got = rows(result())
        self.assertEqual(set(got), {"tts_first", "tts_speed", "tts_par", "tts_par_first", "asr_time", "asr_acc",
                                    "asr_par", "mem_free"})
        for x in got.values():
            self.assertIn(x["level"], bench.LEVELS)
            self.assertTrue(x["why"].endswith("."), x)
            self.assertTrue(x["word"])

    def test_borders(self):
        cases = [("tts_first", dict(ttfa=0.5), "top"), ("tts_first", dict(ttfa=0.9), "ok"),
                 ("tts_first", dict(ttfa=1.8), "warn"), ("tts_first", dict(ttfa=2.5), "bad"),
                 ("tts_speed", dict(rtf=1 / 2.6), "top"), ("tts_speed", dict(rtf=1 / 1.2), "warn"),
                 ("tts_speed", dict(rtf=1.2), "bad"),
                 ("tts_par", dict(tts_par=6.5), "top"), ("tts_par", dict(tts_par=4.2), "ok"),
                 ("tts_par", dict(tts_par=3.1), "warn"), ("tts_par", dict(tts_par=2.0), "bad"),
                 ("asr_time", dict(asr_s=1.2), "top"), ("asr_time", dict(asr_s=6), "bad"),
                 ("asr_acc", dict(acc=0.96), "top"), ("asr_acc", dict(acc=0.91), "ok"),
                 ("asr_acc", dict(acc=0.86), "warn"), ("asr_acc", dict(acc=0.7), "bad"),
                 ("mem_free", dict(free=20), "ok"), ("mem_free", dict(free=10.4), "warn"), ("mem_free", dict(free=8.5), "bad")]
        for key, kw, level in cases:
            self.assertEqual(rows(result(**kw))[key]["level"], level, (key, kw))
        self.assertEqual(rows(result(tts_par=2.0))["tts_par"]["word"], "stockt")
        self.assertIn("2 gleichzeitig gehen flüssig", rows(result(tts_par=2.0))["tts_par"]["why"])

    def test_verdict(self):
        v = bench.rate(result())["verdict"]
        self.assertEqual(v["level"], "warn")
        self.assertEqual(v["title"], "Gut für ein Gespräch, bei 4 gleichzeitig wird es knapp.")
        self.assertIn("qwen38-flash lief während der Messung", v["detail"])
        self.assertIn("freier Speicher", v["detail"])
        good = bench.rate(result(tts_par=6, tts_first_max=0.8, free=20, qwen38=()))["verdict"]
        self.assertEqual((good["level"], good["title"], good["detail"]),
                         ("ok", "Alles flüssig, auch bei mehreren gleichzeitig.", ""))
        bad = bench.rate(result(rtf=1.3))["verdict"]
        self.assertEqual((bad["level"], bad["title"]), ("bad", "Hier hakt es: Tempo der Stimme."))
        none = bench.rate({"errors": ["TTS not measured: unreachable"], "qwen38_active": []})
        self.assertEqual((none["verdict"]["level"], none["groups"]), ("bad", []))
        part = bench.rate(result(tts_par=6, tts_first_max=0.8, free=20, errors=["ASR: x"]))["verdict"]
        self.assertEqual(part["level"], "warn")
        self.assertIn("Nicht alles gemessen", part["detail"])

    def test_compared_with_the_last_run(self):
        got = rows(result(), {"values": {"tts_first": 0.58, "asr_acc": 0.97, "mem_free": 12.0}})
        self.assertEqual(got["tts_first"]["before"], "0,58 s")
        self.assertEqual(got["asr_acc"]["before"], "97 %")
        self.assertEqual(got["mem_free"]["before"], "12,0 GiB")
        self.assertNotIn("before", got["tts_speed"])
        self.assertNotIn("before", rows(result())["tts_first"])

    def test_word_accuracy(self):
        self.assertEqual(bench.word_accuracy(bench.TEXT, bench.TEXT), 1.0)
        n = len(bench._words(bench.TEXT))
        self.assertAlmostEqual(bench.word_accuracy(bench.TEXT.replace("Morgen", "Morgan"), bench.TEXT), 1 - 1 / n, 3)
        self.assertEqual(bench.word_accuracy("", bench.TEXT), 0.0)
        self.assertEqual(bench.word_accuracy("guten morgen dies", "Guten Morgen, dies!"), 1.0)
        self.assertIsNone(bench.word_accuracy("x", ""))
        # long garbage stays cheap (capped at 400 words)
        self.assertEqual(bench.word_accuracy("a " * 100000, bench.TEXT), 0.0)

    def test_history_keeps_ten_runs(self):
        for i in range(13):
            bench.save_history(bench.load_history() + [{"time": i, "qwen38": False, "values": {"tts_first": i}}])
        h = bench.load_history()
        self.assertEqual([x["time"] for x in h], list(range(3, 13)))
        with open(bench.HISTORY, "w") as f:
            f.write("[1, {\"time\": 1}, {\"values\": {}}]")
        self.assertEqual(bench.load_history(), [{"values": {}}])
        with open(bench.HISTORY, "w") as f:
            f.write("kaputt")
        self.assertEqual(bench.load_history(), [])

    def test_panel_sends_the_rating_only_to_the_admin(self):
        os.makedirs(os.path.dirname(bench.RESULT), exist_ok=True)
        r = result()
        r["previous"] = {"time": 1, "values": {"tts_first": 0.58}}
        with open(bench.RESULT, "w") as f:
            json.dump(r, f)
        try:
            self.assertEqual(TestClient(panel.app).get("/api/bench").status_code, 401)
            admin = TestClient(panel.app)
            admin.post("/api/login", json={"password": "secret-admin"})
            got = admin.get("/api/bench").json()
            self.assertEqual(got["rating"]["verdict"]["level"], "warn")
            self.assertEqual(got["rating"]["groups"][0]["rows"][0]["before"], "0,58 s")
            self.assertIn("words right: 98 %", got["report"])
        finally:
            os.remove(bench.RESULT)


if __name__ == "__main__":
    unittest.main()
