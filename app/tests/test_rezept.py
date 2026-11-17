"""Rezept-Editor (Dominik 2026-11-16 „1-6“, model catalog stage B1): an own model gets the engine settings a catalog
entry has. The protection rules, each with its test:

- only the fields of modelle.REZEPT_FELDER, numbers only within their ranges, words only from fixed lists, never a
  flag of its own (nothing reaches vLLM that vllm_args does not build);
- a draft model of a pinned own entry needs its own pinned commit; it is fetched by the same file rules;
- the memory must fit this computer (hardware profile), a model that runs is never changed;
- a changed recipe drops the old measurement (its numbers were for another recipe);
- the catalog line is the entry as it is, checked by the catalog's rules, nothing is written;
- the endpoints are behind the admin switch for own models, with login, limit and size.
Nothing depends on the time of day."""
import json
import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SHA, DSHA = "a" * 40, "d" * 40


def eigen(**over):
    m = {"id": "eigen-mini-lm-8b", "art": "llm", "name": {"de": "Mini", "en": "Mini"}, "engine": "vllm",
         "repo": "beispiel/Mini-LM-8B", "revision": SHA, "lizenz": "apache-2.0", "gewerblich": True, "platte_gb": 13,
         "need_gib": 24, "gemessen": False, "gpu_gib": 25.2, "kontext": 32768, "kann_sehen": False, "werkzeuge": True,
         "vllm": {"reasoning_parser": "qwen3", "tool_call_parser": "hermes", "max_seqs": 4}, "anfrage": {},
         "messen": "auf_wunsch", "betrieb": "resident", "eigen": True}
    m.update(over)
    return modelle.eigen_ok(m)


class Regeln(unittest.TestCase):
    def test_the_form_gets_every_field(self):
        r = modelle.rezept(eigen())
        self.assertEqual(set(r), set(modelle.REZEPT_FELDER))
        self.assertEqual((r["kontext"], r["mtp"], r["entwurf"], r["tool_call_parser"]), (32768, 0, "", "hermes"))

    def test_a_good_recipe(self):
        n = modelle.rezept_anwenden(eigen(), {"kontext": 65536, "gpu_gib": 30.5, "mtp": 3, "batched_tokens": 16384,
                                              "kv_cache_dtype": "fp8", "entwurf": "beispiel/Mini-Draft",
                                              "entwurf_revision": DSHA}, 120.0)
        self.assertEqual((n["kontext"], n["gpu_gib"]), (65536, 30.5))
        self.assertEqual(n["vllm"]["entwurf_revision"], DSHA)
        a = modelle.vllm_args(n, pool_gib=120.0)
        spec = json.loads(a[a.index("--speculative-config") + 1])
        self.assertEqual((spec["model"], spec["revision"], spec["num_speculative_tokens"]), ("beispiel/Mini-Draft", DSHA, 3))
        self.assertEqual(a[a.index("--max-num-batched-tokens") + 1], "16384")
        self.assertNotIn("--trust-remote-code", a)
        # 0 and "" take a field out; without a tool parser it has no tools
        o = modelle.rezept_anwenden(n, {"mtp": 0, "entwurf": "", "entwurf_revision": "", "tool_call_parser": ""}, 120.0)
        self.assertNotIn("mtp", o["vllm"])
        self.assertFalse(o["werkzeuge"])
        self.assertNotIn("--speculative-config", modelle.vllm_args(o, pool_gib=120.0))

    def test_fixed_words_for_everything_else(self):
        cases = [({"extra": "--trust-remote-code"}, "felder"), ({}, "felder"), ("kontext", "felder"),
                 ({"kontext": 1024}, "kontext"), ({"kontext": True}, "kontext"), ({"kontext": "65536"}, "kontext"),
                 ({"kontext": 4096.5}, "kontext"), ({"max_seqs": 99}, "max_seqs"), ({"gpu_gib": 0}, "gpu_gib"),
                 ({"tool_call_parser": "x; rm -rf /"}, "tool_call_parser"), ({"kv_cache_dtype": "fp4"}, "kv_cache_dtype"),
                 ({"mtp": 3, "entwurf": "beispiel/D"}, "entwurf"),                       # a pinned entry: a pinned drafter
                 ({"mtp": 3, "entwurf": "../x", "entwurf_revision": DSHA}, "entwurf"),
                 ({"mtp": 3, "entwurf": "beispiel/D", "entwurf_revision": "main"}, "entwurf_revision"),
                 ({"bilder_pro_frage": 2}, "bilder_pro_frage"), ({"gpu_gib": 100}, "budget")]
        for felder, word in cases:
            with self.assertRaises(modelle.Fehler, msg=felder) as e:
                modelle.rezept_anwenden(eigen(), felder, 120.0)
            self.assertEqual(str(e.exception), word, felder)
        self.assertEqual(modelle.rezept_anwenden(eigen(), {"gpu_gib": 100}, 278.3)["gpu_gib"], 100.0)   # a Station
        with self.assertRaises(modelle.Fehler):
            modelle.rezept_anwenden(modelle.eintrag("qwen36-35b-a3b-nvfp4"), {"kontext": 4096}, 120.0)   # catalog: never

    def test_saving_drops_the_measurement_and_never_while_it_runs(self):
        d = tempfile.mkdtemp(dir=helpers.TMP)
        pfad, mess = os.path.join(d, "eigene.json"), os.path.join(d, "messung.json")
        with open(pfad, "w") as f:
            json.dump({"modelle": [dict(eigen(), zeit=5)]}, f)
        with open(mess, "w") as f:
            json.dump({"modelle": {"eigen-mini-lm-8b": {"ok": True, "tok_s": 40}, "andere": {"ok": True}}}, f)
        aus = {"llm": {"enabled": False}}
        n = modelle.eigen_aendern("eigen-mini-lm-8b", {"kontext": 65536}, 120.0, aus, pfad, mess)
        self.assertEqual(n["kontext"], 65536)
        gespeichert = json.load(open(pfad))["modelle"][0]
        self.assertEqual((gespeichert["kontext"], gespeichert["zeit"]), (65536, 5))
        self.assertEqual(set(json.load(open(mess))["modelle"]), {"andere"})
        for mid, felder, cfg, word in (("eigen-gibts-nicht", {"kontext": 4096}, aus, "unbekannt"),
                                       ("eigen-mini-lm-8b", {"kontext": 65536}, aus, "schon"),
                                       ("eigen-mini-lm-8b", {"kontext": 4096},
                                        {"llm": {"enabled": True, "modell": "eigen-mini-lm-8b"}}, "aktiv")):
            with mock.patch.object(modelle, "katalog", return_value={"eigen-mini-lm-8b": n}):
                with self.assertRaises(modelle.Fehler) as e:
                    modelle.eigen_aendern(mid, felder, 120.0, cfg, pfad, mess)
            self.assertEqual(str(e.exception), word)

    def test_the_catalog_line(self):
        z = json.loads(modelle.katalog_zeile(eigen(), {"modelle": {"eigen-mini-lm-8b": {"ok": True}}}))
        self.assertEqual(z["id"], "mini-lm-8b")
        self.assertNotIn("eigen", z)
        self.assertTrue(z["gemessen"])
        modelle.pruefe_eintrag(z)
        self.assertFalse(json.loads(modelle.katalog_zeile(eigen(), {}))["gemessen"])
        with self.assertRaises(modelle.Fehler):
            modelle.katalog_zeile(modelle.eintrag("qwen36-35b-a3b-nvfp4"), {})


class Seite(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: os.path.exists(modelle.EIGENE) and os.remove(modelle.EIGENE))
        # the switches go back off: left on, a later module in the same process (test_startprotokoll) saw
        # „Modelle wechseln“ on (Dauer-Wackler .510-.512)
        self.addCleanup(helpers.set_config, modelle_wechseln=False, modelle_eigene=False)

    def test_behind_the_switch_and_checked(self):
        r = ADMIN.put("/api/admin/modelle/eigen/eigen-mini-lm-8b/rezept", json={"kontext": 65536})
        self.assertEqual(r.status_code, 409)                         # own models off: nothing
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.put("/api/admin/modelle/eigen/eigen-mini-lm-8b/rezept", json={"kontext": 65536}).status_code, (401, 403))
        self.assertIn(anon.get("/api/admin/modelle/eigen/eigen-mini-lm-8b/katalogzeile").status_code, (401, 403))
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        modelle.eigen_speichern(eigen())
        with mock.patch.object(modelle, "gesamt_gib", return_value=120.0):
            r = ADMIN.put("/api/admin/modelle/eigen/eigen-mini-lm-8b/rezept", json={"kontext": 65536, "mtp": 2,
                                                                                  "entwurf": "beispiel/D", "entwurf_revision": DSHA})
            self.assertEqual(r.status_code, 200, r.text)
            row = next(m for a in r.json()["arten"] for m in a["modelle"] if m["id"] == "eigen-mini-lm-8b")
            self.assertEqual((row["rezept"]["kontext"], row["rezept"]["entwurf"]), (65536, "beispiel/D"))
            r = ADMIN.put("/api/admin/modelle/eigen/eigen-mini-lm-8b/rezept", json={"tool_call_parser": "<b>"})
            self.assertEqual((r.status_code, r.json()["detail"]), (400, "Wert außerhalb des erlaubten Bereichs: tool_call_parser"))
            r = ADMIN.put("/api/admin/modelle/eigen/eigen-mini-lm-8b/rezept", json={"gpu_gib": 500})
            self.assertEqual(r.status_code, 400)
            self.assertIn("Speicher", r.json()["detail"])
            self.assertEqual(ADMIN.put("/api/admin/modelle/eigen/..%2Fx/rezept", json={"kontext": 4096}).status_code, 404)
            self.assertEqual(ADMIN.put("/api/admin/modelle/eigen/eigen-mini-lm-8b/rezept",
                                       content=b"{" + b" " * 4000 + b"}").status_code, 413)
            r = ADMIN.get("/api/admin/modelle/eigen/eigen-mini-lm-8b/katalogzeile")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(json.loads(r.json()["zeile"])["id"], "mini-lm-8b")
            self.assertEqual(ADMIN.get("/api/admin/modelle/eigen/eigen-x/katalogzeile").status_code, 404)

    def test_the_model_computer_checks_again(self):
        import tarswart
        self.assertIn("eigen_rezept", tarswart.COMMANDS)
        self.assertIn("eigen_rezept", tarswart.WITH_DATA)
        with mock.patch.object(modelle, "eigen_aendern", side_effect=modelle.Fehler("kontext")), \
                mock.patch("builtins.print"):
            self.assertEqual(tarswart.eigen_rezept("eigen-x", {"kontext": 1}), {"ok": False, "fehler": "kontext"})
        with self.assertRaises(ValueError):
            tarswart.eigen_rezept("../x", {})
        self.assertIn(("PUT", "/api/admin/modelle/eigen/{mid}/rezept"), __import__("stufen").LIST)


if __name__ == "__main__":
    unittest.main()
