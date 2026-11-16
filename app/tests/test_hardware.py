"""Hardware-Profil (Dominik 2026-11-16 „1-6“, stage A): the catalog names GiB, the computer decides the share.
The protection rules, each with its test:

- the profile comes from one fixed nvidia-smi query; anything it does not know is a fixed word ("andere"), never its text;
- without nvidia-smi (panel computer, tests) the reference DGX Spark, so nothing depends on the test computer;
- an engine's share is its GiB of this computer's pool, never above ANTEIL_MAX (a model too big for a computer is
  refused, not squeezed);
- on a computer whose GPU has its own memory (DGX Station) the CPU models do not count in the GPU's pool;
- the profile the Wärter sends is checked field by field; a model computer before stage A counts as a DGX Spark;
- an own entry saved before stage A (a share) becomes the same GiB;
- a measurement says on which kind of computer it was made, the page names another one.
Nothing depends on the time of day."""
import copy
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import hardware  # noqa: E402
import modelle  # noqa: E402

GB10 = hardware.aus_smi(0, "NVIDIA GB10, [N/A]", 119.7)
GB300 = hardware.aus_smi(0, "NVIDIA GB300, 285000", 496.0)


class Erkennen(unittest.TestCase):
    def test_the_kinds(self):
        self.assertEqual(GB10, {"id": "gb10", "gemeinsam": True, "pool_gib": 119.7, "ram_gib": 119.7, "system_gib": 6})
        self.assertEqual(GB300, {"id": "gb300", "gemeinsam": False, "pool_gib": 278.3, "ram_gib": 496.0, "system_gib": 2})
        self.assertEqual(hardware.aus_smi(0, "NVIDIA RTX PRO 6000 <b>x</b>, 97887", 256.0)["id"], "andere")
        for code, out in ((1, ""), (0, ""), (0, "x"), (0, "a, b, c"), (127, "not found")):
            p = hardware.aus_smi(code, out, 64.0)
            self.assertEqual((p["id"], p["pool_gib"]), ("ohne_gpu", hardware.BEZUG_GIB), out)

    def test_only_the_fixed_query(self):
        hardware.profil.cache_clear()
        self.addCleanup(hardware.profil.cache_clear)
        with mock.patch.object(hardware.shutil, "which", return_value="/usr/bin/nvidia-smi"), \
                mock.patch.object(hardware, "run", return_value=(0, "NVIDIA GB10, [N/A]")) as run, \
                mock.patch.object(hardware, "_ram_gib", return_value=119.7):
            self.assertEqual(hardware.profil()["id"], "gb10")
            hardware.profil()
        run.assert_called_once_with(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], timeout=15)
        hardware.profil.cache_clear()
        with mock.patch.object(hardware.shutil, "which", return_value=None):
            self.assertEqual(hardware.profil()["pool_gib"], hardware.BEZUG_GIB)

    def test_what_the_waerter_sends_is_checked(self):
        self.assertEqual(hardware.gueltig(GB300), GB300)
        for bad in (None, [], dict(GB300, id="<b>"), dict(GB300, extra=1), dict(GB300, pool_gib=True),
                    dict(GB300, pool_gib=-1), dict(GB300, gemeinsam="ja"), {k: v for k, v in GB300.items() if k != "id"}):
            self.assertIsNone(hardware.gueltig(bad), bad)

    def test_the_line_for_the_page(self):
        self.assertEqual(hardware.text(GB10), "DGX Spark (GB10) · 119,7 GiB gemeinsam")
        self.assertEqual(hardware.text(GB300, "en"), "DGX Station (GB300) · 278.3 GiB GPU + 496 GiB memory")


class Anteil(unittest.TestCase):
    def util(self, m, pool):
        a = modelle.vllm_args(m, revision=m["revision"] or "a" * 40, pool_gib=pool)
        return a[a.index("--gpu-memory-utilization") + 1]

    def test_the_same_gib_on_every_computer(self):
        q = modelle.eintrag("qwen36-35b-a3b-nvfp4")
        self.assertEqual(q["gpu_gib"], 36)
        self.assertEqual(self.util(q, 120.0), "0.30")
        self.assertEqual(self.util(q, 119.7), "0.30")
        self.assertEqual(self.util(q, GB300["pool_gib"]), "0.13")
        self.assertEqual(self.util(q, None), "0.30")      # no GPU here: the reference Spark

    def test_too_big_is_refused_not_squeezed(self):
        q = dict(modelle.eintrag("qwen36-35b-a3b-nvfp4"), gpu_gib=200)
        with self.assertRaises(modelle.Fehler) as e:
            modelle.vllm_args(q, pool_gib=120.0)
        self.assertEqual(str(e.exception), "budget")
        self.assertEqual(self.util(q, GB300["pool_gib"]), "0.72")    # fits a DGX Station

    def test_long_conversations_add_gib(self):
        q = modelle.eintrag("qwen36-35b-a3b-nvfp4")
        self.assertEqual(modelle.mit_platz(q, "1x256k")["gpu_gib"], q["gpu_gib"] + modelle.PLATZ["1x256k"][0])


class Budget(unittest.TestCase):
    CFG = {"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4"},
           "asr": {"enabled": True, "recognizer": "parakeet"}, "tts": {"enabled": False},
           "chat": {"doc_semantic": True}, "memory": {"reserve_gib": 10}}

    def test_cpu_models_live_in_the_cpu_memory_of_a_station(self):
        spark = modelle.budget(copy.deepcopy(self.CFG), 120.0, profil=GB10)
        station = modelle.budget(copy.deepcopy(self.CFG), GB300["pool_gib"], profil=GB300)
        cpu = {i for i, m in modelle.katalog().items() if m["engine"] == "onnx-cpu"}
        self.assertTrue(cpu & {x["id"] for x in spark["teile"]}, "the Spark counts its CPU models in the one memory")
        self.assertFalse(cpu & {x["id"] for x in station["teile"]})
        self.assertEqual((spark["system"], station["system"]), (6, 2))
        self.assertEqual(spark["regel"], "alle")
        self.assertGreater(station["frei"], spark["frei"])

    def test_the_page_takes_the_model_computers_profile(self):
        import modellseite
        d = {"gesamt_gib": GB300["pool_gib"], "messung": {"modelle": {"qwen36-35b-a3b-nvfp4": {"ok": True, "tok_s": 50}}},
             "wechsel": {}, "eigene": [], "laeuft": False, "misst": False, "start": None, "profil": GB300}
        with mock.patch.object(modellseite.steuer, "remote", return_value=True), \
                mock.patch.object(modellseite.steuer, "modelle", return_value=d):
            self.assertEqual(modellseite._quelle({})[8], GB300)
            s = modellseite.seite(cfg=dict(copy.deepcopy(self.CFG), features={}), lang="de")
            self.assertEqual(s["geraet"], hardware.text(GB300))
            rows = {m["id"]: m for a in s["arten"] for m in a["modelle"]}
            self.assertEqual(rows["qwen36-35b-a3b-nvfp4"]["gemessen_auf"], "DGX Spark (GB10)")   # before stage A: the Spark
            with mock.patch.object(modellseite.steuer, "modelle", return_value=dict(d, profil={"id": "boese"})):
                self.assertEqual(modellseite._quelle({})[8], hardware.profil())


class Alt(unittest.TestCase):
    def test_an_old_own_entry_keeps_its_memory(self):
        self.assertEqual(modelle._alt_anteil({"id": "eigen-x", "anteil": 0.25}), {"id": "eigen-x", "gpu_gib": 30.0})
        self.assertEqual(modelle._alt_anteil({"id": "eigen-x", "anteil": True}), {"id": "eigen-x"})
        self.assertEqual(modelle._alt_anteil({"id": "eigen-x", "gpu_gib": 9}), {"id": "eigen-x", "gpu_gib": 9})

    def test_a_measurement_names_its_computer(self):
        src = open(os.path.join(os.path.dirname(modelle.__file__), "modelle.py"), encoding="utf-8").read()
        self.assertIn('"profil": hardware.profil()["id"]', src[src.index("def messen_lauf"):][:600])


if __name__ == "__main__":
    unittest.main()
