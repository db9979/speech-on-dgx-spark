"""Every model on a pinned commit (Dominik 2026-10-18, Abgleich sichere KI-Architektur Punkt 2): the speech models,
the search models and the picture check load like the language models only the commit the catalog names, only the
allowed file kinds, each file checked against its hash. Nothing depends on the time of day."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "panel"))
import modelle  # noqa: E402
import bildmodell  # noqa: E402
import embed_worker  # noqa: E402


def read(*p):
    with open(os.path.join(APP, *p), encoding="utf-8") as f:
        return f.read()


class Katalog(unittest.TestCase):
    def test_every_speech_search_and_check_model_is_pinned(self):
        for mid, m in modelle.katalog().items():
            if m["engine"] in ("qwen-asr", "qwen-tts", "onnx-cpu"):
                self.assertRegex(m["revision"], modelle.REV, mid)
        self.assertEqual(modelle.eintrag("nsfw-pruefung")["revision"], bildmodell.CHECKER.revision)   # one source
        self.assertRegex(bildmodell.CHECKER.revision, modelle.REV)

    def test_fest_only_for_a_pinned_catalog_repository(self):
        m = modelle.fest("Qwen/Qwen3-ASR-1.7B")
        self.assertEqual(m["id"], "qwen3-asr-1.7b")
        for repo in ("someone/else", "Qwen/Qwen3-VL-8B-Instruct-FP8", ""):     # unknown, or only measured (no pin)
            with self.assertRaises(modelle.Fehler):
                modelle.fest(repo)
        out = subprocess.run([sys.executable, os.path.join(APP, "modelle.py"), "fest", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.split(), ["qwen3-tts-0.6b", modelle.eintrag("qwen3-tts-0.6b")["revision"]])
        out = subprocess.run([sys.executable, os.path.join(APP, "modelle.py"), "erlaubt"], capture_output=True, text=True,
                             timeout=60)
        self.assertEqual(json.loads(out.stdout), list(modelle.ERLAUBT))

    def test_lokal_gives_only_the_checked_pinned_snapshot(self):
        rev = modelle.eintrag("qwen3-asr-0.6b")["revision"]
        with tempfile.TemporaryDirectory() as hf:
            d = os.path.join(hf, "hub", "models--Qwen--Qwen3-ASR-0.6B")
            with self.assertRaisesRegex(modelle.Fehler, "fehlt"):
                modelle.lokal("Qwen/Qwen3-ASR-0.6B", hf_home=hf)
            os.makedirs(os.path.join(d, "blobs"))
            snap = os.path.join(d, "snapshots", rev)
            os.makedirs(snap)
            for name, data in (("model.safetensors", b"x" * 500), ("config.json", b"{}")):
                blob = hashlib.sha256(data).hexdigest() if len(data) > 100 else \
                    hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
                with open(os.path.join(d, "blobs", blob), "wb") as f:
                    f.write(data)
                os.symlink(os.path.join("..", "..", "blobs", blob), os.path.join(snap, name))
            self.assertEqual(modelle.lokal("Qwen/Qwen3-ASR-0.6B", hf_home=hf), snap)
            with open(os.path.join(snap, "x.py"), "w") as f:
                f.write("print(1)")
            with self.assertRaisesRegex(modelle.Fehler, "dateiart"):
                modelle.lokal("Qwen/Qwen3-ASR-0.6B", hf_home=hf)


class Ladewege(unittest.TestCase):
    def test_install_downloads_the_pinned_commit_and_checks_it(self):
        sh = helpers.repo_file("install.sh")
        dl = sh[sh.index("  dl() {"):]
        dl = dl[:dl.index("\n  }\n")]
        for need in ('modelle.py" fest "$2"', "revision=sys.argv[2]", "allow_patterns=", 'modelle.py" erlaubt',
                     'modelle.py" pruefen "$id"'):
            self.assertIn(need, dl)
        self.assertIn('sha256sum "$INSTALL_FROM/app/modelle.json"', sh)        # a new pin fetches again on update

    def test_engines_and_servers_load_the_pinned_commit(self):
        eng = read("engine.sh")
        self.assertIn('modelle.py" fest "$MODEL"', eng)
        self.assertEqual(eng.count('serve "$MODEL" --revision "$REV"'), 2)    # ASR and TTS engine
        for f in ("asr_server.py", "tts_server.py"):
            src = read(f)
            self.assertIn("from_pretrained(modelle.lokal(cfg[\"model\"])" if f == "asr_server.py"
                          else "modelle.lokal(cfg[\"model\"])", src)
            self.assertNotIn('from_pretrained(cfg["model"]', src)
        self.assertIn('forced_aligner"] = modelle.lokal(cfg["aligner_model"])', read("asr_server.py"))
        for f in ("docembed.py", "nachsortieren.py"):
            self.assertIn('m["repo"], m["revision"]', read("panel", f))


class Worker(unittest.TestCase):
    def test_refuses_a_call_without_a_pinned_commit(self):
        for args in ([], ["rank", "klein"], ["embed", "Xenova/multilingual-e5-small", "main"],
                     ["rank", "klein", "a/b", "c" * 40, "x"], ["embed", "../x", "c" * 40]):
            out = subprocess.run([sys.executable, "-I", os.path.join(APP, "panel", "embed_worker.py"), *args],
                                 capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            self.assertFalse(json.loads(out.stdout.splitlines()[0])["ready"], args)

    def test_a_file_that_differs_from_its_name_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            good = b"y" * 300
            blob = os.path.join(d, hashlib.sha256(good).hexdigest())
            with open(blob, "wb") as f:
                f.write(good)
            link = os.path.join(d, "model.onnx")
            os.symlink(blob, link)
            import huggingface_hub
            with mock.patch.object(huggingface_hub, "hf_hub_download", return_value=link) as dl:
                self.assertEqual(embed_worker.hole("a/b", "c" * 40, "model.onnx"), (link, hashlib.sha256(good).hexdigest()))
            self.assertEqual(dl.call_args.kwargs["revision"], "c" * 40)
            with open(blob, "r+b") as f:
                f.write(b"z")
            with mock.patch.object(huggingface_hub, "hf_hub_download", return_value=link):
                with self.assertRaises(RuntimeError):
                    embed_worker.hole("a/b", "c" * 40, "model.onnx")


if __name__ == "__main__":
    unittest.main()
