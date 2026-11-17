"""Eigene kleine Modelle (Dominik 2026-11-16 „alle 1-6“ point 2 „klein via ONNX“, 2026-11-17 „mache das projekt bis zu
ende durch“): an own re-ranking model is one .onnx file of a public repository on a pinned commit, with tokenizer.json,
no external data, no code, at most 2 GiB and the family of a checked re-ranker. It is kept on the panel's computer (it
runs there on the CPU), switched as the setting chat.rerank_model, and at its first start it must pass the fixed probe
(the answering passage scores higher), else the small checked one works. The embedding of the meaning search stays.
No real model and no network: the worker is a small script. Nothing depends on the time of day."""
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import embed_worker  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402
import nachsortieren  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SHA = "c" * 40
FILE_SHA = "d" * 64
CFG = {"architectures": ["XLMRobertaForSequenceClassification"], "model_type": "xlm-roberta"}
FAM = (modelle.familie(CFG),)
HERE = os.path.dirname(os.path.abspath(__file__))


def info(cfg=None, datei="onnx/model_quantized.onnx", size=500 * 2**20, extra=(), **over):
    i = {"id": "beispiel/reranker-de", "sha": SHA, "private": False, "gated": False, "disabled": False,
         "config": dict(CFG if cfg is None else cfg), "cardData": {"license": "apache-2.0"},
         "siblings": [{"rfilename": "config.json", "size": 900}, {"rfilename": "tokenizer.json", "size": 9000},
                      {"rfilename": datei, "lfs": {"size": size, "sha256": FILE_SHA}}] + [{"rfilename": f} for f in extra]}
    i.update(over)
    return i


def eigen():
    return modelle.klein_vorschlag(info(), "beispiel/reranker-de", "onnx/model_quantized.onnx", FAM)


class Regeln(unittest.TestCase):
    def test_one_onnx_file_of_the_same_family_becomes_a_reranker(self):
        m = eigen()
        self.assertEqual((m["art"], m["rolle"], m["engine"], m["revision"], m["variante"]),
                         ("klein", "nachsortieren", "onnx-cpu", SHA, m["id"]))
        self.assertEqual(m["datei"], {"path": "onnx/model_quantized.onnx", "sha256": FILE_SHA, "size": 500 * 2**20})
        self.assertTrue(m["eigen"] and m["id"].startswith("eigen-"))
        self.assertFalse({"vllm", "wahl", "empfohlen", "basis"} & set(m))

    def test_other_family_code_data_files_size_and_access_say_no(self):
        bad = ((info(cfg={"architectures": ["BertModel"], "model_type": "bert"}), "onnx/model_quantized.onnx", "familie"),
               (info(cfg={}), "onnx/model_quantized.onnx", "familie"),
               (info(cfg=dict(CFG, auto_map={"AutoModel": "x.Y"})), "onnx/model_quantized.onnx", "code"),
               (info(extra=("onnx/model_quantized.onnx_data",)), "onnx/model_quantized.onnx", "format"),
               (dict(info(), siblings=[x for x in info()["siblings"] if x["rfilename"] != "tokenizer.json"]),
                "onnx/model_quantized.onnx", "format"),
               (info(datei="pytorch_model.bin"), "pytorch_model.bin", "format"),
               (info(datei="../x.onnx"), "../x.onnx", "format"),
               (info(size=3 * 2**30), "onnx/model_quantized.onnx", "budget"),
               (info(private=True), "onnx/model_quantized.onnx", "zugang"),
               (info(gated=True), "onnx/model_quantized.onnx", "zugang"))
        for i, datei, wort in bad:
            with self.assertRaises(modelle.Fehler, msg=wort) as e:
                modelle.klein_vorschlag(i, "beispiel/reranker-de", datei, FAM)
            self.assertEqual(str(e.exception), wort)
        with self.assertRaises(modelle.Fehler):
            modelle.klein_vorschlag(info(), "beispiel/reranker-de", "onnx/model_quantized.onnx", ())

    def test_own_small_entries_keep_their_rules(self):
        m = eigen()
        for bad in (dict(m, engine="vllm"), dict(m, rolle="suche"), dict(m, variante="klein"), dict(m, wahl="x"),
                    dict(m, datei=dict(m["datei"], path="m.gguf")), dict(m, datei=dict(m["datei"], size=3 * 2**30)),
                    dict(m, revision=""), dict(m, eigen=False), dict(m, empfohlen=["gb10"])):
            with self.assertRaises(modelle.Fehler):
                modelle.eigen_ok(bad)
        modelle.eigen_ok(dict(m))

    def test_choosing_needs_the_role_and_not_the_one_set(self):
        m = eigen()
        kat = dict(modelle.katalog(eigene=[]), **{m["id"]: m})
        cfg = {"chat": {"rerank": True, "rerank_model": "klein"}}
        self.assertEqual(modelle.klein_pruefen(m["id"], cfg, kat)["id"], m["id"])
        self.assertEqual(modelle.klein_pruefen("rerank-gross", cfg, kat)["variante"], "gross")
        for mid, c, wort in (("rerank-klein", cfg, "schon"), (m["id"], {"chat": {"rerank_model": m["id"]}}, "schon"),
                             ("e5-small", cfg, "art"), ("nicht-da", cfg, "art")):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.klein_pruefen(mid, c, kat)
            self.assertEqual(str(e.exception), wort)

    def test_the_probe_wants_the_answer_first(self):
        self.assertEqual(modelle.klein_probe([3.2, -5.0]), (True, "ok"))
        self.assertEqual(modelle.klein_probe([-5.0, 3.2]), (False, "reihenfolge"))
        self.assertEqual(modelle.klein_probe([1.0, 1.0]), (False, "reihenfolge"))
        for bad in (None, [], [1.0], [True, False], ["1", "0"]):
            self.assertEqual(modelle.klein_probe(bad), (False, "antwort"))

    def test_the_worker_takes_only_a_clean_onnx_path(self):
        for args in (["rank", "eigen", "a/b", SHA, "../x.onnx"], ["rank", "eigen", "a/b", SHA, "x.bin"],
                     ["rank", "eigen", "a/b", "main", "x.onnx"], ["rank", "eigen", "a/b", SHA]):
            out = io.StringIO()
            with mock.patch.object(sys, "argv", ["embed_worker.py"] + args), contextlib.redirect_stdout(out):
                embed_worker.main()
            self.assertIn("usage", json.loads(out.getvalue())["error"], args)


class Probe(unittest.TestCase):
    """The first start of an own one: its file's SHA-256 and the probe decide; failed, the small checked one works."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = eigen()
        self.p = mock.patch.object(modelle, "EIGENE", os.path.join(self.tmp, "eigene.json"))
        self.p.start()
        modelle.eigen_speichern(self.m)
        helpers.set_config(rerank=True, rerank_model=self.m["id"])
        nachsortieren._abgelehnt.clear()
        nachsortieren._lock = None
        with contextlib.suppress(FileNotFoundError):
            os.remove(nachsortieren.PINS)

    def tearDown(self):
        nachsortieren._stop()
        nachsortieren._abgelehnt.clear()
        helpers.set_config(rerank=False, rerank_model="klein")
        self.p.stop()
        with contextlib.suppress(FileNotFoundError):
            os.remove(nachsortieren.PINS)

    def start(self, scores, sha=FILE_SHA):
        path = os.path.join(self.tmp, "fake_rank.py")
        hello = {"ready": True, "sha": {f"{self.m['repo']}/{self.m['datei']['path']}": sha, f"{self.m['repo']}/tokenizer.json": "1" * 64},
                 "commit": SHA}
        with open(path, "w") as f:
            f.write("import json, sys\nassert sys.argv[1:3] == ['rank', 'eigen'] and sys.argv[5].endswith('.onnx')\n"
                    f"sys.stdout.write({json.dumps(json.dumps(hello))} + '\\n'); sys.stdout.flush()\n"
                    "for line in sys.stdin:\n"
                    f"    sys.stdout.write(json.dumps({{'scores': {scores!r}}}) + '\\n'); sys.stdout.flush()\n")
        out = io.StringIO()
        with mock.patch.object(nachsortieren, "WORKER", path), mock.patch.object(nachsortieren, "_free_gib", return_value=10**6), \
                contextlib.redirect_stdout(out):
            asyncio.run(nachsortieren._start())
        return out.getvalue()

    def test_an_own_one_that_passes_works(self):
        self.assertEqual(nachsortieren.size(), self.m["id"])
        self.assertEqual(nachsortieren.need_gib(self.m["id"]), modelle.KLEIN_NEED_GIB)
        log = self.start([4.0, -6.0])
        self.assertIn("wissen: nachsortieren probe ok | ok", log)
        self.assertIn(f"wissen: nachsortieren modell bereit | {self.m['id']}", log)
        self.assertEqual(nachsortieren.status()["state"], "ready")

    def test_a_failed_probe_goes_back_to_the_small_checked_one(self):
        log = self.start([-6.0, 4.0])
        self.assertIn("wissen: nachsortieren probe fehler | reihenfolge", log)
        self.assertIn("wissen: nachsortieren modell fehler | probe", log)
        self.assertIn("Probe nicht bestanden", nachsortieren.status()["error"])
        self.assertEqual(nachsortieren.size(), "klein")

    def test_another_file_than_the_added_one_is_refused(self):
        log = self.start([4.0, -6.0], sha="e" * 64)
        self.assertIn("wissen: nachsortieren modell fehler | model files changed", log)
        self.assertNotIn("probe", log)
        self.assertFalse(os.path.exists(nachsortieren.PINS))

    def test_an_unknown_own_id_means_the_small_one(self):
        helpers.set_config(rerank_model="eigen-gibt-es-nicht")
        self.assertEqual(nachsortieren.size(), "klein")


class Seite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = mock.patch.object(modelle, "EIGENE", os.path.join(self.tmp, "eigene.json"))
        self.p.start()
        self.admin = TestClient(panel.app)
        self.admin.post("/api/login", json={"password": "secret-admin"})

    def tearDown(self):
        helpers.set_config(rerank=False, rerank_model="klein")
        self.p.stop()

    def test_families_come_from_the_checked_rerankers(self):
        seen = []

        async def fake(repo, rev=""):
            seen.append((repo, rev))
            return {"config": CFG}
        with mock.patch.object(modellseite, "_hf_info", fake):
            self.assertEqual(asyncio.run(modellseite._familien("klein")), FAM)
        kat = modelle.katalog(eigene=[])
        self.assertEqual(seen, [(kat[r]["repo"], kat[r]["revision"]) for r in modelle.KLEIN_ROLLE["nachsortieren"]])

    def test_the_setting_takes_an_own_one_of_the_catalog_only(self):
        cfg = self.admin.get("/api/config").json()
        cfg["chat"]["rerank_model"] = "eigen-gibt-es-nicht"
        self.assertEqual(self.admin.put("/api/config", json=cfg).status_code, 400)
        m = eigen()
        modelle.eigen_speichern(m)
        cfg["chat"]["rerank_model"] = m["id"]
        self.assertEqual(self.admin.put("/api/config", json=cfg).status_code, 200)
        with self.assertRaises(modelle.Fehler) as e:       # while it is the chosen one it stays on the list
            with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
                modelle.eigen_loeschen(m["id"], json.load(f), path=modelle.EIGENE)
        self.assertEqual(str(e.exception), "aktiv")

    def test_the_page_offers_the_onnx_form_and_the_switch(self):
        with open(os.path.join(HERE, "..", "panel", "static", "js", "modelle.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("a.art==='klein'?mdKleinDatei()", js)
        self.assertIn("b.dataset.mdw==='klein'", js)
        with open(os.path.join(HERE, "..", "panel", "modellseite.py"), encoding="utf-8") as f:
            py = f.read()
        self.assertIn('if art == "klein":       # the re-ranking model', py)
        self.assertIn('steuer.remote(cfg) and art != "klein"', py)


if __name__ == "__main__":
    unittest.main()
