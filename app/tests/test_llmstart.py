"""What the own language model does while it switches or starts (Dominik 2026-10-18 „1a 2a 3a 4a 5a“): the six fixed
steps with their times, the engine's phase as a fixed word, the expected minutes, the panel's check of what the model
computer sends and the chat's sentence. Fixed times, nothing depends on the clock."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "panel"))
import llmstart  # noqa: E402

T0 = 1_800_000_000


def read(*p):
    with open(os.path.join(APP, *p), encoding="utf-8") as f:
        return f.read()
JOURNAL = """Started speech-spark-llm.service - own language model.
INFO Loading weights took 41.20 seconds
INFO Model loading took 22.1 GiB and 44.8 seconds
INFO torch.compile takes 310.5 s in total
INFO Available KV cache memory: 11.92 GiB
INFO Capturing CUDA graphs (mixed prefill-decode, PIECEWISE): 100%
INFO:     Application startup complete."""


class Ablauf(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "llm-start.json")
        self.z = os.path.join(self.d, "llm-startzeiten.json")
        self.e = os.path.join(self.d, "speech-spark-llm.json")

    def lesen(self, now, gesund=False, journal="", messung=None):
        return llmstart.lesen(gesund, journal, messung, "qwen36-35b-a3b-nvfp4", now=now, path=self.f, zeiten=self.z,
                              engine=self.e)

    def test_a_switch_goes_through_six_steps_and_keeps_its_start_time(self):
        mid = "qwen36-35b-a3b-nvfp4"
        for n, t in ((1, 0), (2, 2), (3, 40), (4, 55)):
            llmstart.schritt("wechsel", n, mid, now=T0 + t, path=self.f)
        x = self.lesen(T0 + 355, journal=JOURNAL.split("torch")[0])
        self.assertEqual((x["schritt"], x["n"], x["dauer_s"], x["schritt_s"], x["teil"]), ("starten", 4, 355, 300, "kernel"))
        self.assertEqual(x["seit"], {"pruefen": 0, "dateien": 2, "anhalten": 40, "starten": 55})
        self.assertEqual(x["erwartet_s"], 0)                         # never started before, nothing measured
        self.assertEqual(llmstart.rest_min(x), 0)
        self.assertEqual(self.lesen(T0 + 355, messung={"modelle": {mid: {"laden_s": 1041}}})["erwartet_s"], 1041)
        llmstart.stufe("probe", now=T0 + 1100, path=self.f)          # the engine answers: step 5
        llmstart.stufe("satz", path=self.f)
        x = self.lesen(T0 + 1110)
        self.assertEqual((x["n"], x["teil"]), (5, "satz"))
        llmstart.ende("ok", now=T0 + 1130, path=self.f, zeiten=self.z)
        x = self.lesen(T0 + 1200, gesund=True)
        self.assertEqual((x["n"], x["ende"], x["ergebnis"], x["dauer_s"]), (6, True, "ok", 1130))
        with open(self.z) as f:
            self.assertEqual(json.load(f), {mid: 1045})              # step 4 to 5: the next start expects this
        self.assertIsNone(self.lesen(T0 + 1130 + llmstart.ZEIGEN_S + 1, gesund=True))   # the result goes after a while
        llmstart.schritt("platz", 3, now=T0 + 5000, path=self.f)    # „Lange Gespräche“: starts afresh at step 3
        llmstart.schritt("platz", 4, now=T0 + 5010, path=self.f)
        x = self.lesen(T0 + 5070)
        self.assertEqual((x["vorgang"], x["n"], x["erwartet_s"], x["seit"]), ("platz", 4, 1045, {"anhalten": 0, "starten": 10}))
        self.assertEqual(llmstart.rest_min(x), 18)                   # (1045 - 60 + 60) s, rounded up

    def test_taken_back_keeps_rundlaufs_word_and_shows_the_restart_of_the_model_before(self):
        llmstart.schritt("wechsel", 1, "qwen36-35b-a3b-nvfp4", now=T0, path=self.f)
        llmstart.schritt("wechsel", 4, now=T0 + 60, path=self.f)
        llmstart.stufe("fehler", grund="httperror", path=self.f)
        llmstart.ende("zurueck", now=T0 + 70, path=self.f, zeiten=self.z)
        with open(self.e, "w") as f:
            json.dump({"status": "loading", "error": "loading", "time": "2027-01-15T09:00:00+00:00"}, f)
        x = self.lesen(T0 + 80)
        self.assertEqual((x["vorgang"], x["n"], x["ende"]), ("neustart", 4, False))   # the model before starts again
        x = self.lesen(T0 + 300, gesund=True)
        self.assertEqual((x["ergebnis"], x["grund"], x["ende"]), ("zurueck", "httperror", True))
        self.assertFalse(os.path.exists(self.z))                     # never reached the test question: no time kept
        llmstart.ende("ok", now=T0 + 400, path=self.f, zeiten=self.z)   # an ended switch stays ended
        self.assertEqual(self.lesen(T0 + 400, gesund=True)["ergebnis"], "zurueck")

    def test_a_plain_restart_comes_from_the_engines_state(self):
        self.assertIsNone(self.lesen(T0))
        with open(self.e, "w") as f:
            json.dump({"status": "loading", "error": "x", "time": "2027-01-15T08:00:00+00:00"}, f)
        x = self.lesen(1_800_003_600, journal=JOURNAL)
        self.assertEqual((x["vorgang"], x["n"], x["teil"], x["dauer_s"]), ("neustart", 4, "bereit", 3600))
        self.assertIsNone(self.lesen(T0, gesund=True))               # it answers: nothing to show
        with open(self.e, "w") as f:
            json.dump({"status": "blocked", "error": "not enough unified memory", "time": "2027-01-15T08:00:00+00:00"}, f)
        x = self.lesen(T0)
        self.assertEqual((x["grund"], x["teil"]), ("speicher", ""))    # engine.sh's words, never its message
        self.assertIn("nicht starten", llmstart.satz(x))
        with open(self.e, "w") as f:
            json.dump({"status": "ready"}, f)
        self.assertIsNone(self.lesen(T0))

    def test_a_stale_file_and_bad_words_are_refused(self):
        llmstart.schritt("wechsel", 4, "qwen36-35b-a3b-nvfp4", now=T0, path=self.f)
        self.assertIsNone(self.lesen(T0 + llmstart.ALT_S + 1))       # a killed unit never shows forever
        for args in (("x", 1), ("wechsel", 7), ("wechsel", 0), ("wechsel", 1, "Qwen/Repo")):
            with self.assertRaises(ValueError):
                llmstart.schritt(*args, path=self.f)
        with self.assertRaises(ValueError):
            llmstart.ende("vielleicht", path=self.f)
        llmstart.schritt("wechsel", 1, now=T0, path=self.f)
        llmstart.ende("zurueck", "Traceback: boom 1", now=T0, path=self.f, zeiten=self.z)
        self.assertEqual(self.lesen(T0, gesund=True)["grund"], "fehler")   # a word of fixed shape only

    def test_phase_reads_only_this_start_and_only_fixed_patterns(self):
        self.assertEqual(llmstart.phase(""), "gewichte")
        self.assertEqual(llmstart.phase(JOURNAL.split("INFO torch")[0]), "kernel")
        self.assertEqual(llmstart.phase(JOURNAL.split("INFO Capturing")[0]), "speicher")
        self.assertEqual(llmstart.phase(JOURNAL), "bereit")
        self.assertEqual(llmstart.phase(JOURNAL + "\nStarting speech-spark-llm.service - own language model."), "gewichte")

    def test_cli_writes_steps_and_refuses_others(self):
        import subprocess
        env = dict(os.environ, SPEECH_SPARK_STATE=self.d)
        py = os.path.join(APP, "llmstart.py")
        for a in (["schritt", "wechsel", "1", "qwen36-35b-a3b-nvfp4"], ["schritt", "wechsel", "4"], ["teil", "satz"]):
            self.assertEqual(subprocess.run([sys.executable, py, *a], env=env, timeout=60).returncode, 0, a)
        r = subprocess.run([sys.executable, py, "schritt", "rm", "1"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stderr.strip()), (2, "modelle: llmstart abgelehnt schritt"))
        with open(self.f) as f:
            d = json.load(f)
        self.assertEqual((d["vorgang"], d["schritt"], d["ziel"]), ("wechsel", 4, "qwen36-35b-a3b-nvfp4"))


class Panel(unittest.TestCase):
    X = {"vorgang": "wechsel", "ziel": "qwen36-35b-a3b-nvfp4", "schritt": "starten", "n": 4,
         "seit": {"pruefen": 0, "dateien": 2, "anhalten": 40, "starten": 55}, "dauer_s": 355, "schritt_s": 300,
         "erwartet_s": 1041, "teil": "kernel", "ende": False, "ergebnis": "", "grund": ""}

    def test_the_panel_takes_only_the_fixed_shape(self):
        self.assertEqual(llmstart.pruefen(dict(self.X)), self.X)
        self.assertIsNone(llmstart.pruefen(None))
        for bad in ({"teil": "Loading weights took 41 s"}, {"grund": "Traceback"}, {"n": 9}, {"vorgang": "rm"},
                    {"seit": {"x": 1}}, {"ziel": "../etc"}, {"dauer_s": -1}, {"ende": "ja"}):
            self.assertIsNone(llmstart.pruefen(dict(self.X, **bad)), bad)
        x = dict(self.X)
        del x["teil"]
        self.assertIsNone(llmstart.pruefen(x))

    def test_steuer_drops_a_wrong_start_but_keeps_the_page(self):
        import steuer
        d = {"gesamt_gib": 121.7, "lanes": [], "messung": {}, "wechsel": {}, "eigene": [], "laeuft": True, "misst": False,
             "stand": [], "start": dict(self.X, teil="<b>")}
        with mock.patch.object(steuer, "call", return_value=json.loads(json.dumps(d))):
            self.assertIsNone(steuer.modelle({})["start"])
        with mock.patch.object(steuer, "call", return_value=dict(d, start=dict(self.X))):
            self.assertEqual(steuer.modelle({})["start"], self.X)

    def test_the_sentence_says_how_long(self):
        self.assertEqual(llmstart.rest_min(self.X), 14)                   # 1041 - 300 + 60 s
        self.assertEqual(llmstart.satz(self.X), "Mein Sprachmodell startet gerade neu, etwa noch 14 Minuten. "
                                                 "Frag mich dann bitte noch einmal.")
        self.assertIn("about 14 more minutes", llmstart.satz(self.X, en=True))
        self.assertEqual(llmstart.satz(dict(self.X, erwartet_s=0)),
                         "Mein Sprachmodell startet gerade neu. Frag mich dann bitte noch einmal.")
        self.assertEqual(llmstart.satz(None), "")
        self.assertIn("gemessen", llmstart.satz(None, misst=True))
        self.assertEqual(llmstart.satz(dict(self.X, ende=True)), "")

    def test_chat_and_page_use_the_one_reader(self):
        import chat_modell
        import modellseite
        with mock.patch.object(modellseite, "lage", return_value={"start": dict(self.X), "misst": False}):
            self.assertIn("etwa noch 14 Minuten", asyncio.run(chat_modell.llm_start_satz(False)))
        with mock.patch.object(modellseite, "lage", side_effect=RuntimeError("weg")):
            self.assertEqual(asyncio.run(chat_modell.llm_start_satz(False)), "")
        z = modellseite._start_zeigen(dict(self.X), {"qwen36-35b-a3b-nvfp4": {"name": {"de": "Qwen3.6", "en": "Qwen3.6"}}}, 0)
        self.assertEqual((z["titel"], z["name"], z["teil_name"], len(z["schritte"]), z["rest_min"]),
                         ("Sprachmodell wechselt", "Qwen3.6", "Kernel übersetzen", 6, 14))
        self.assertIsNone(modellseite._start_zeigen(None, {}, 0))
        src = read("panel", "chat_modell.py")
        self.assertIn("note = await llm_start_satz(en_q) or note", src)            # not reachable while it starts
        self.assertIn("await llm_start_satz(en_p) or wartung.sentence(en_p)", src)  # the switch's maintenance pause

    def test_the_switch_writes_each_step_in_order(self):
        sh = read("speech-spark.sh")
        w = sh[sh.index("\nwechsel() {"):]
        w = w[:w.index("\n}\n")]
        order = [w.index(x) for x in ('llmschritt schritt wechsel 1', 'llmschritt schritt wechsel 2',
                                      'llmschritt schritt wechsel 3', 'systemctl stop speech-spark-llm',
                                      'llmschritt schritt wechsel 4', 'systemctl start speech-spark-llm',
                                      'llmschritt ende ok')]
        self.assertEqual(order, sorted(order))
        self.assertGreater(w.rindex('llmschritt ende zurueck'), order[-1])     # the test question failed: back
        p = sh[sh.index("\nplatz_setzen() {"):]
        p = p[:p.index("\n}\n")]
        self.assertLess(p.index('llmschritt schritt platz 4 "$jetzt"'), p.index("systemctl start speech-spark-llm"))
        self.assertIn("llmschritt ende ok", p)
        self.assertIn("ok, wort = rundlauf(load_config(), log, stufe=llmstart.stufe)",
                      read("modelle.py"))


if __name__ == "__main__":
    unittest.main()
