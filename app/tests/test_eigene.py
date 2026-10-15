"""Eigene Modelle, stage E5 (modelle.py eigen_*, panel modellseite.py; plan plaene/eigene-modelle.md): the admin adds a
Hugging Face model for the language model or image understanding only by fixed rules (safetensors only, no code from
the repository, an architecture the engine knows, open, within the memory share, a pinned commit). A broken own entry
never breaks the catalog, one that runs or can still come back is never deleted, the cache folder goes only inside
hub/models--*, and everything is behind an admin switch that is off by default. Nothing depends on the time of day."""
import json
import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SHA = "a" * 40
T0 = 1_800_000_000.0


def info(**over):
    """A Hugging Face answer for one commit, like /api/models/<repo>/revision/<rev>?blobs=true."""
    i = {"id": "beispiel/Mini-LM-8B", "sha": SHA, "private": False, "gated": False, "disabled": False,
         "config": {"architectures": ["Qwen3ForCausalLM"], "model_type": "qwen3"},
         "cardData": {"license": "apache-2.0"},
         "siblings": [{"rfilename": "config.json", "size": 900},
                      {"rfilename": "model-00001-of-00002.safetensors", "lfs": {"size": 8 * 2**30}},
                      {"rfilename": "model-00002-of-00002.safetensors", "lfs": {"size": 4 * 2**30}},
                      {"rfilename": "tokenizer.json", "size": 7000}]}
    i.update(over)
    return i


class Regeln(unittest.TestCase):
    def test_a_good_model_becomes_a_pinned_entry(self):
        m = modelle.eigen_vorschlag(info(), "llm", "beispiel/Mini-LM-8B", 128)
        self.assertEqual(m["id"], "eigen-mini-lm-8b")
        self.assertEqual((m["revision"], m["engine"], m["messen"]), (SHA, "vllm", "auf_wunsch"))
        self.assertTrue(m["eigen"] and m["gewerblich"] and m["werkzeuge"])
        self.assertEqual(m["need_gib"], 12 + modelle.KV_GIB["llm"])
        self.assertNotIn("trust_remote_code", json.dumps(m))
        self.assertIn("--revision", modelle.vllm_args(m))
        self.assertNotIn("--trust-remote-code", modelle.vllm_args(m))
        sehen = modelle.eigen_vorschlag(info(config={"architectures": ["Qwen2_5_VLForConditionalGeneration"]}),
                                        "sehen", "beispiel/Mini-VL", 128)
        self.assertTrue(sehen["kann_sehen"])
        self.assertEqual(sehen["betrieb"], "bei_bedarf")

    def test_fixed_rules_say_no_with_a_fixed_word(self):
        pickle_only = [{"rfilename": "pytorch_model.bin", "lfs": {"size": 2**30}}, {"rfilename": "config.json"}]
        cases = [
            (info(), "asr", "beispiel/x", "art"), (info(), "bild", "beispiel/x", "art"),
            (info(), "llm", "kein-name", "repo"), (info(), "llm", "a/../b", "repo"), (info(), "llm", "a/b c", "repo"),
            (info(sha="main"), "llm", "beispiel/x", "antwort"), ("<html>", "llm", "beispiel/x", "antwort"),
            (info(gated="auto"), "llm", "beispiel/x", "zugang"), (info(private=True), "llm", "beispiel/x", "zugang"),
            (info(siblings=pickle_only), "llm", "beispiel/x", "format"),
            (info(siblings=[{"rfilename": "m.safetensors"}]), "llm", "beispiel/x", "format"),       # size unknown
            (info(config={"architectures": ["Qwen3ForCausalLM"], "auto_map": {"AutoModel": "x.Model"}}), "llm", "beispiel/x", "code"),
            (info(config={"architectures": ["Qwen3ForCausalLM"], "tokenizer_config": {"auto_map": ["t.Tok", None]}}),
             "llm", "beispiel/x", "code"),
            (info(config={"architectures": ["MyOwnForCausalLM"]}), "llm", "beispiel/x", "architektur"),
            (info(config={}), "llm", "beispiel/x", "architektur"),
            (info(), "sehen", "beispiel/x", "architektur"),                   # a text model cannot see
            (info(siblings=[{"rfilename": "m.safetensors", "lfs": {"size": 120 * 2**30}}]), "llm", "beispiel/x", "budget"),
        ]
        for i, art, repo, word in cases:
            with self.assertRaises(modelle.Fehler, msg=(art, repo, word)) as e:
                modelle.eigen_vorschlag(i, art, repo, 128)
            self.assertEqual(str(e.exception), word, (art, repo))

    def test_unknown_licence_is_private_use(self):
        m = modelle.eigen_vorschlag(info(cardData={}), "llm", "beispiel/x", 128)
        self.assertEqual((m["lizenz"], m["gewerblich"]), ("unbekannt", False))

    def test_own_entries_keep_the_extra_rules(self):
        m = modelle.eigen_vorschlag(info(), "llm", "beispiel/Mini-LM-8B", 128)
        for bad in (dict(m, eigen=False), dict(m, id="mini"), dict(m, revision=""), dict(m, messen="immer"),
                    dict(m, art="asr"), dict(m, engine="extern"), dict(m, vllm=dict(m["vllm"], venv="kolibri")),
                    dict(m, vllm=dict(m["vllm"], quantization="x"))):
            with self.assertRaises(modelle.Fehler):
                modelle.eigen_ok(bad)


class Liste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "eigene.json")
        self.m = modelle.eigen_vorschlag(info(), "llm", "beispiel/Mini-LM-8B", 128)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_broken_file_never_breaks_the_catalog(self):
        base = modelle.katalog(eigene=os.path.join(self.tmp.name, "fehlt.json"))
        with open(self.path, "w") as f:
            json.dump({"modelle": [dict(self.m, revision="main"), dict(self.m, eigen=False, id="eigen-x"), "kaputt",
                                   dict(self.m, id="qwen38-27b-nvfp4"), self.m]}, f)
        kat = modelle.katalog(eigene=self.path)
        self.assertEqual(set(kat) - set(base), {self.m["id"]})
        self.assertEqual(kat["qwen38-27b-nvfp4"], base["qwen38-27b-nvfp4"])       # never replaces a catalog entry
        with open(self.path, "w") as f:
            f.write("{nicht json")
        self.assertEqual(set(modelle.katalog(eigene=self.path)), set(base))
        self.assertIn(self.m["id"], modelle.messliste([self.m["id"]], kat=kat))

    def test_save_once_and_at_most_twenty(self):
        kat = modelle.katalog(eigene=os.path.join(self.tmp.name, "fehlt.json"))
        modelle.eigen_speichern(self.m, self.path, kat)
        self.assertEqual([x["id"] for x in modelle.eigene(self.path)], [self.m["id"]])
        with self.assertRaises(modelle.Fehler) as e:
            modelle.eigen_speichern(self.m, self.path, kat)
        self.assertEqual(str(e.exception), "schon")
        catalog_repo = dict(self.m, id="eigen-andere", repo=next(iter(kat.values()))["repo"])
        with self.assertRaises(modelle.Fehler):
            modelle.eigen_speichern(catalog_repo, self.path, kat)
        for n in range(modelle.EIGENE_MAX - 1):
            modelle.eigen_speichern(dict(self.m, id=f"eigen-m{n}", repo=f"beispiel/m{n}"), self.path, kat)
        with self.assertRaises(modelle.Fehler) as e:
            modelle.eigen_speichern(dict(self.m, id="eigen-zuviel", repo="beispiel/zuviel"), self.path, kat)
        self.assertEqual(str(e.exception), "voll")

    def test_never_deleted_while_it_runs_or_within_the_days(self):
        kat = modelle.katalog(eigene=os.path.join(self.tmp.name, "fehlt.json"))
        modelle.eigen_speichern(self.m, self.path, kat)
        wechsel = os.path.join(self.tmp.name, "wechsel.json")
        cfg = {"llm": {"enabled": True, "modell": self.m["id"]}}
        with mock.patch.object(modelle, "EIGENE", self.path):
            with self.assertRaises(modelle.Fehler) as e:
                modelle.eigen_loeschen(self.m["id"], cfg, T0, self.path, wechsel, self.tmp.name)
            self.assertEqual(str(e.exception), "aktiv")
            with open(wechsel, "w") as f:
                json.dump({"llm": {"alt": self.m["id"], "zeit": T0 - 2 * 86400}}, f)
            cfg = {"llm": {"enabled": True, "modell": "qwen38-27b-nvfp4"}}
            with self.assertRaises(modelle.Fehler) as e:
                modelle.eigen_loeschen(self.m["id"], cfg, T0, self.path, wechsel, self.tmp.name)
            self.assertEqual(str(e.exception), "frist")
            with self.assertRaises(modelle.Fehler) as e:
                modelle.eigen_loeschen("eigen-gibts-nicht", cfg, T0, self.path, wechsel, self.tmp.name)
            self.assertEqual(str(e.exception), "unbekannt")
            ordner = modelle.eigen_loeschen(self.m["id"], cfg, T0 + 8 * 86400, self.path, wechsel, self.tmp.name)
        self.assertEqual(modelle.eigene(self.path), [])
        self.assertEqual(os.path.basename(ordner), "models--beispiel--Mini-LM-8B")

    def test_the_folder_goes_only_inside_the_cache(self):
        hub = os.path.join(self.tmp.name, "hub")
        drin = os.path.join(hub, "models--beispiel--x")
        os.makedirs(os.path.join(drin, "blobs"))
        draussen = os.path.join(self.tmp.name, "models--fremd")
        os.makedirs(draussen)
        link = os.path.join(hub, "models--link")
        os.symlink(draussen, link)
        anders = os.path.join(hub, "datasets--x")
        os.makedirs(anders)
        self.assertFalse(modelle.ordner_weg(link, self.tmp.name))          # a link is never followed
        self.assertTrue(os.path.isdir(draussen))
        for bad in (draussen, anders):
            with self.assertRaises(modelle.Fehler):
                modelle.ordner_weg(bad, self.tmp.name)
            self.assertTrue(os.path.isdir(bad))
        self.assertFalse(modelle.ordner_weg(os.path.join(hub, "models--fehlt"), self.tmp.name))
        self.assertTrue(modelle.ordner_weg(drin, self.tmp.name))
        self.assertFalse(os.path.exists(drin))

    def test_an_own_image_model_is_measured_first(self):
        m = modelle.eigen_vorschlag(info(config={"architectures": ["Qwen2_5_VLForConditionalGeneration"]}),
                                    "sehen", "beispiel/Mini-VL", 128)
        kat = dict(modelle.katalog(eigene=os.path.join(self.tmp.name, "fehlt.json")), **{m["id"]: m})
        cfg = {"llm": {"enabled": True, "modell": "qwen38-27b-nvfp4", "sehen_modell": "gemma-4-26b-a4b"},
               "memory": {"reserve_gib": 10}}
        with self.assertRaises(modelle.Fehler) as e:
            modelle.wechsel_pruefen("sehen", m["id"], cfg, 128, kat=kat, messung={})
        self.assertEqual(str(e.exception), "ungeprueft")
        ok = modelle.wechsel_pruefen("sehen", m["id"], cfg, 128, kat=kat, messung={"modelle": {m["id"]: {"ok": True}}})
        self.assertEqual(ok["id"], m["id"])


class Panel(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] in ("modelle_eigen", "modelle")]:
            guard._rate.pop(k, None)
        self.saved = modellseite._lanes, modellseite._laeuft
        modellseite._lanes = lambda: []
        modellseite._laeuft = lambda: False

    def tearDown(self):
        modellseite._lanes, modellseite._laeuft = self.saved
        helpers.set_config(modelle_wechseln=False, modelle_eigene=False)
        try:
            os.remove(modelle.EIGENE)
        except OSError:
            pass

    def test_off_by_default_and_admin_only(self):
        self.assertNotIn("modelleeigen", features.DEFAULT_ON)
        self.assertIn("modelleeigen", features.SPARK_ONLY)
        self.assertEqual(features.BY_KEY["modelleeigen"].parent, "modellwechsel")
        fake = mock.AsyncMock(return_value=info())
        with mock.patch.object(modellseite, "_hf_info", fake):
            self.assertEqual(ADMIN.post("/api/admin/modelle/eigen/pruefen", json={"art": "llm", "repo": "beispiel/x"}).status_code, 409)
            self.assertEqual(ADMIN.post("/api/admin/modelle/eigen", json={"art": "llm", "repo": "beispiel/x", "revision": SHA}).status_code, 409)
            self.assertEqual(ADMIN.delete("/api/admin/modelle/eigen/eigen-x").status_code, 409)
            anon = TestClient(panel.app, client=("192.168.178.20", 50000))
            self.assertIn(anon.post("/api/admin/modelle/eigen/pruefen", json={"art": "llm", "repo": "beispiel/x"}).status_code, (401, 403))
            self.assertIn(anon.post("/api/admin/modelle/eigen", json={"art": "llm", "repo": "beispiel/x", "revision": SHA}).status_code, (401, 403))
            self.assertIn(anon.delete("/api/admin/modelle/eigen/eigen-x").status_code, (401, 403))
        self.assertFalse(fake.called)                      # nothing goes out while it is off
        self.assertFalse(os.path.exists(modelle.EIGENE))
        self.assertFalse(ADMIN.get("/api/admin/modelle").json()["wechsel"]["eigene"])

    def test_check_add_and_delete(self):
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        with mock.patch.object(modellseite, "_hf_info", mock.AsyncMock(return_value=info())), \
                mock.patch.object(modelle, "gesamt_gib", return_value=128.0):
            r = ADMIN.post("/api/admin/modelle/eigen/pruefen", json={"art": "llm", "repo": "beispiel/Mini-LM-8B"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["vorschlag"]["revision"], SHA)
            self.assertFalse(os.path.exists(modelle.EIGENE))                  # checking keeps nothing
            self.assertEqual(ADMIN.post("/api/admin/modelle/eigen", json={"art": "llm", "repo": "beispiel/Mini-LM-8B",
                                                                         "revision": "b" * 40}).status_code, 400)
            self.assertEqual(ADMIN.post("/api/admin/modelle/eigen", json={"art": "llm", "repo": "beispiel/Mini-LM-8B",
                                                                         "revision": "main"}).status_code, 400)
            r = ADMIN.post("/api/admin/modelle/eigen", json={"art": "llm", "repo": "beispiel/Mini-LM-8B", "revision": SHA})
            self.assertEqual(r.status_code, 200, r.text)
            rows = [m for a in r.json()["arten"] for m in a["modelle"] if m["eigen"]]
            self.assertEqual([m["id"] for m in rows], ["eigen-mini-lm-8b"])
            self.assertEqual(ADMIN.delete("/api/admin/modelle/eigen/eigen-gibts-nicht").status_code, 404)
            self.assertEqual(ADMIN.delete("/api/admin/modelle/eigen/..%2F..%2Fetc").status_code, 404)
            r = ADMIN.delete("/api/admin/modelle/eigen/eigen-mini-lm-8b")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(modelle.eigene(), [])

    def test_a_refused_model_is_never_kept(self):
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        bad = info(config={"architectures": ["Qwen3ForCausalLM"], "auto_map": {"AutoModel": "m.M"}})
        with mock.patch.object(modellseite, "_hf_info", mock.AsyncMock(return_value=bad)), \
                mock.patch.object(modelle, "gesamt_gib", return_value=128.0):
            r = ADMIN.post("/api/admin/modelle/eigen", json={"art": "llm", "repo": "beispiel/x", "revision": SHA})
            self.assertEqual(r.status_code, 400)
            self.assertIn("eigenen Code", r.json()["detail"])
        with mock.patch.object(modellseite, "_hf_info", mock.AsyncMock(side_effect=modelle.Fehler("netz"))):
            r = ADMIN.post("/api/admin/modelle/eigen/pruefen", json={"art": "llm", "repo": "beispiel/x"})
            self.assertEqual(r.status_code, 503)
        self.assertFalse(os.path.exists(modelle.EIGENE))

    def test_metadata_goes_only_through_netguard(self):
        import asyncio
        with self.assertRaises(modelle.Fehler):
            asyncio.run(modellseite._hf_info("a/../b"))
        with self.assertRaises(modelle.Fehler):
            asyncio.run(modellseite._hf_info("beispiel/x", "main;rm"))
        seen = {}

        class Antwort:
            status_code = 403

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                seen["url"] = url
                return Antwort()

        def client(mode, **kw):
            seen.update(mode=mode, **kw)
            return Client()
        with mock.patch.object(modellseite.netguard, "client", client):
            with self.assertRaises(modelle.Fehler) as e:
                asyncio.run(modellseite._hf_info("beispiel/x", SHA))
        self.assertEqual(str(e.exception), "zugang")
        self.assertEqual(seen["mode"], modellseite.netguard.PUBLIC)
        self.assertIs(seen["follow_redirects"], False)
        self.assertEqual(seen["url"], f"https://huggingface.co/api/models/beispiel/x/revision/{SHA}?blobs=true")


if __name__ == "__main__":
    unittest.main()
