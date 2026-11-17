"""Eigene Modelle für Hören und Sprechen (Dominik 2026-11-16 „alle 1-6“ points 2 and 4, 2026-11-17 „mache das projekt
bis zu ende durch“): an own speech model must be the same family (modelle.FAMILIE_KEYS of its config.json) as a checked
model of its kind's program (modelle.SPRACH), only safetensors, no code; it becomes an own entry of that program on a
pinned commit, root switches to it through the configuration and a restart, and the fixed probe (bench.sprachprobe:
speech output → recognition, at least PROBE_MIN of the words) decides, else back to the model before. Nothing depends
on the time of day."""
import asyncio
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import bench  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402

SHA = "b" * 40
ASR_CFG = {"architectures": ["Qwen3ASRForConditionalGeneration"], "model_type": "qwen3_asr"}
HERE = os.path.dirname(os.path.abspath(__file__))


def info(cfg=None, **over):
    i = {"id": "beispiel/asr-de", "sha": SHA, "private": False, "gated": False, "disabled": False,
         "config": dict(ASR_CFG if cfg is None else cfg), "cardData": {"license": "apache-2.0"},
         "siblings": [{"rfilename": "config.json", "size": 900},
                      {"rfilename": "model.safetensors", "lfs": {"size": 4 * 2**30}}]}
    i.update(over)
    return i


FAM = (modelle.familie(ASR_CFG),)


class Regeln(unittest.TestCase):
    def test_same_family_becomes_an_entry_of_the_program(self):
        m = modelle.eigen_vorschlag(info(), "asr", "beispiel/asr-de", 121, familien=FAM)
        self.assertEqual((m["engine"], m["art"], m["revision"], m["betrieb"]), ("qwen-asr", "asr", SHA, "resident"))
        self.assertEqual(m["need_gib"], 4 + modelle.SPRACH_EXTRA_GIB)
        self.assertTrue(m["eigen"] and m["id"].startswith("eigen-"))
        self.assertFalse({"vllm", "wahl", "rolle", "empfohlen"} & set(m))
        t = modelle.eigen_vorschlag(info(cfg={"architectures": ["Qwen3TTSForConditionalGeneration"]}), "tts",
                                    "beispiel/tts-de", 121, familien=(modelle.familie({"architectures": ["Qwen3TTSForConditionalGeneration"]}),))
        self.assertEqual(t["engine"], "qwen-tts")

    def test_other_family_code_pickle_and_size_say_no(self):
        for i, fam, wort in ((info(cfg={"architectures": ["WhisperForConditionalGeneration"], "model_type": "whisper"}), FAM, "familie"),
                             (info(), (), "familie"), (info(cfg={}), FAM, "familie"),
                             (info(cfg=dict(ASR_CFG, auto_map={"AutoModel": "x.Y"})), FAM, "code"),
                             (info(siblings=[{"rfilename": "pytorch_model.bin", "lfs": {"size": 2**30}}]), FAM, "format"),
                             (info(siblings=[{"rfilename": "m.safetensors", "lfs": {"size": 400 * 2**30}}]), FAM, "budget"),
                             (info(private=True), FAM, "zugang")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.eigen_vorschlag(i, "asr", "beispiel/asr-de", 121, familien=fam)
            self.assertEqual(str(e.exception), wort)

    def test_own_speech_entries_keep_their_rules(self):
        m = modelle.eigen_vorschlag(info(), "asr", "beispiel/asr-de", 121, familien=FAM)
        for bad in (dict(m, engine="qwen-tts"), dict(m, engine="vllm"), dict(m, wahl="1.7b"), dict(m, vllm={}),
                    dict(m, empfohlen=["gb10"]), dict(m, revision=""), dict(m, id="asr-de"), dict(m, eigen=False)):
            with self.assertRaises(modelle.Fehler):
                modelle.eigen_ok(bad)
        modelle.eigen_ok(dict(m))

    def test_search_hits_need_the_task_and_the_family(self):
        def hit(repo, cfg, tag="automatic-speech-recognition"):
            return {"id": repo, "downloads": 5, "tags": ["safetensors"], "pipeline_tag": tag, "config": cfg,
                    "safetensors": {"parameters": {"BF16": 1_000_000_000}}, "cardData": {"license": "mit"}}
        kat = modelle.katalog(eigene=[])
        got = {h["repo"]: h["nein"] for h in modelle.such_treffer(
            [hit("x/gut", ASR_CFG), hit("x/whisper", {"architectures": ["WhisperForConditionalGeneration"]}),
             hit("x/tts", ASR_CFG, "text-to-speech")], "asr", 121.0, kat, familien=FAM)}
        self.assertEqual(got, {"x/gut": "", "x/whisper": "familie", "x/tts": "aufgabe"})


class Wechsel(unittest.TestCase):
    def test_root_switches_an_own_one_by_configuration_and_probe(self):
        m = modelle.eigen_vorschlag(info(), "asr", "beispiel/asr-de", 121, familien=FAM)
        kat = dict(modelle.katalog(eigene=[]), **{m["id"]: m})
        cfg = modelle.load_config()
        cfg = dict(cfg, asr=dict(cfg.get("asr", {}), enabled=True, recognizer="qwen", model="Qwen/Qwen3-ASR-1.7B"))
        with mock.patch.object(modelle, "budget", return_value={"regel": "alle"}):
            got = modelle.wechsel_pruefen("asr", m["id"], cfg, 121.0, kat)
        self.assertEqual(modelle.wechsel_weg("asr", got), f"sprache beispiel/asr-de {SHA}")
        self.assertEqual(modelle.wechsel_weg("asr", kat["qwen3-asr-0.6b"]), "wahl 0.6b")
        self.assertEqual(modelle.mit_wechsel(cfg, "asr", m)["asr"]["model"], "beispiel/asr-de")
        with open(os.path.join(HERE, "..", "speech-spark.sh"), encoding="utf-8") as f:
            sh = f.read()
        teil = sh[sh.index('if [ "$kind" = sprache ]'):sh.index('elif [ "$kind" = wahl ]')]
        for step in ('vorbereiten "$mid" --revision "$rev"', 'probe=sprachprobe', 'wechsel-schalten "$art" "$mid"',
                     'dienst_neu "$art"', 'modelle.py "$probe" "$art"', 'feld "$alt" wahl', 'wechsel-schalten "$art" "$alt"'):
            self.assertIn(step, teil)
        self.assertLess(teil.index('"$probe" "$art"'), teil.index('wechsel-schalten "$art" "$alt"'))


class Probe(unittest.TestCase):
    class Fake:
        def __init__(self, states, heard="", fehler=False):
            self.states, self.heard, self.fehler = list(states), heard, fehler

        async def ready(self, svc):
            return self.states.pop(0) if self.states else "ready"

        async def tts_wav(self, text):
            if self.fehler:
                raise RuntimeError("TTS 500")
            return {"wav": b"RIFF"}

        async def asr_once(self, wav, name):
            return 0.1, self.heard

    def test_round_trip_decides(self):
        s = bench.PROBE_SATZ
        self.assertEqual(bench.sprachprobe(0, bench=self.Fake([], heard=s))[:2], (True, "ok"))
        ok, wort, anteil = bench.sprachprobe(0, bench=self.Fake([], heard="ganz etwas anderes"))
        self.assertEqual((ok, wort), (False, "genauigkeit"))
        self.assertLess(anteil, bench.PROBE_MIN)
        self.assertEqual(bench.sprachprobe(0, bench=self.Fake([], fehler=True))[:2], (False, "antwort"))
        self.assertEqual(bench.sprachprobe(0, bench=self.Fake(["error"]))[:2], (False, "asr-error"))
        self.assertEqual(bench.sprachprobe(0, bench=self.Fake(["ready", "loading"]))[:2], (False, "tts-zeit"))


class Seite(unittest.TestCase):
    def test_families_come_from_the_checked_models_pinned_commits(self):
        seen = []

        async def fake(repo, rev=""):
            seen.append((repo, rev))
            return {"config": ASR_CFG}
        with mock.patch.object(modellseite, "_hf_info", fake):
            fam = asyncio.run(modellseite._familien("asr"))
            self.assertEqual(asyncio.run(modellseite._familien("llm")), ())
        kat = modelle.katalog(eigene=[])
        self.assertEqual(fam, FAM)
        self.assertEqual(seen, [(kat[r]["repo"], kat[r]["revision"]) for r in modelle.SPRACH["asr"][1]])


if __name__ == "__main__":
    unittest.main()
