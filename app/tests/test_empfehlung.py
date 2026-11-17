"""Empfehlung in der Modellsuche (Dominik 2026-11-16 „wie wäre es noch mit einer empfehlung welches model gut passen
würde? je nach anwendung“, „1-3“): the hits that fit come first, the others with their reason (another task such as an
embedding, code, size); the star goes by a fixed rule (the format this computer runs best, room beside the running
models, downloads), never by a model; the checked catalog names one recommendation per kind of computer, never an own
model and never a variant by inheritance. Nothing depends on the time of day."""
import os
import unittest

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import hardware  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SPARK = {"id": "gb10", "gemeinsam": True, "pool_gib": 121.0, "ram_gib": 121.0, "system_gib": 6}
STATION = {"id": "gb300", "gemeinsam": False, "pool_gib": 279.0, "ram_gib": 496.0, "system_gib": 2}
FREMD = {"id": "andere", "gemeinsam": False, "pool_gib": 48.0, "ram_gib": 128.0, "system_gib": 2}
JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static", "js")


def hit(repo, n=8_000_000_000, dtype="BF16", downloads=1000, **k):
    return dict({"id": repo, "downloads": downloads, "tags": ["safetensors"], "pipeline_tag": "text-generation",
                 "config": {"architectures": ["Qwen3ForCausalLM"]}, "safetensors": {"parameters": {dtype: n}},
                 "cardData": {"license": "apache-2.0"}, "gated": False}, **k)


class Regel(unittest.TestCase):
    def setUp(self):
        self.kat = modelle.katalog(eigene=[])

    def test_another_task_is_no_language_model(self):
        items = [hit("x/emb", pipeline_tag="feature-extraction"), hit("x/tts", pipeline_tag="text-to-speech"),
                 hit("x/chat"), hit("x/ohne", pipeline_tag=None)]
        got = {h["repo"]: (h["nein"], h["aufgabe"]) for h in modelle.such_treffer(items, "llm", 121.0, self.kat, SPARK)}
        self.assertEqual(got["x/emb"], ("aufgabe", "feature-extraction"))
        self.assertEqual(got["x/tts"], ("aufgabe", "text-to-speech"))
        self.assertEqual(got["x/chat"][0], "")
        self.assertEqual(got["x/ohne"][0], "")       # no task named: the other rules decide
        self.assertEqual(modelle.such_treffer([hit("x/chat")], "sehen", 121.0, self.kat, SPARK)[0]["nein"], "aufgabe")

    def test_fitting_first_by_format_then_downloads_and_one_star(self):
        items = [hit("x/emb", pipeline_tag="feature-extraction", downloads=10**9),
                 hit("x/gross-bf16", downloads=10**8), hit("x/klein-FP8", dtype="F8_E4M3", downloads=10**6),
                 hit("x/neu-NVFP4", dtype="U8", n=4_000_000_000, downloads=10**5)]
        spark = modelle.such_treffer(items, "llm", 121.0, self.kat, SPARK, raum_gib=60)
        self.assertEqual([h["repo"] for h in spark], ["x/neu-NVFP4", "x/klein-FP8", "x/gross-bf16", "x/emb"])
        self.assertEqual([h["format"] for h in spark], ["nvfp4", "fp8", "bf16", "bf16"])
        self.assertEqual([h["empfohlen"] for h in spark], [True, False, False, False])
        self.assertEqual(spark[0]["warum"], {"format": "nvfp4", "need_gib": spark[0]["need_gib"], "raum_gib": 60})
        # a GPU without NVFP4: FP8 first, NVFP4 last of the fitting ones
        fremd = modelle.such_treffer(items, "llm", 48.0, self.kat, FREMD, raum_gib=40)
        self.assertEqual([h["repo"] for h in fremd][:3], ["x/klein-FP8", "x/gross-bf16", "x/neu-NVFP4"])
        self.assertTrue(fremd[0]["empfohlen"])

    def test_star_only_with_room_beside_the_running_models(self):
        items = [hit("x/a-NVFP4", dtype="U8", n=60_000_000_000), hit("x/b-fp8", dtype="F8_E4M3", n=8_000_000_000)]
        h = modelle.such_treffer(items, "llm", 121.0, self.kat, SPARK, raum_gib=20)
        self.assertEqual(h[0]["repo"], "x/a-NVFP4")
        self.assertEqual([x["empfohlen"] for x in h], [False, True])
        self.assertNotIn("warum", h[0])
        none = modelle.such_treffer(items, "llm", 121.0, self.kat, SPARK, raum_gib=1)
        self.assertFalse(any(x["empfohlen"] for x in none))

    def test_gated_only_with_the_token_private_never(self):
        items = [hit("x/gated", gated="manual"), hit("x/privat", private=True)]
        ohne = {h["repo"]: h["nein"] for h in modelle.such_treffer(items, "llm", 121.0, self.kat, SPARK)}
        mit = {h["repo"]: h["nein"] for h in modelle.such_treffer(items, "llm", 121.0, self.kat, SPARK, mit_token=True)}
        self.assertEqual(ohne, {"x/gated": "zugang", "x/privat": "zugang"})
        self.assertEqual(mit, {"x/gated": "", "x/privat": "zugang"})

    def test_format_from_name_and_dtypes(self):
        self.assertEqual(modelle.format_wort("nvidia/Qwen3.6-35B-A3B-NVFP4"), "nvfp4")
        self.assertEqual(modelle.format_wort("x/m", {"F8_E4M3": 9, "BF16": 1}), "fp8")
        self.assertEqual(modelle.format_wort("x/m-AWQ"), "int")
        self.assertEqual(modelle.format_wort("x/m", {"BF16": 9}), "bf16")
        self.assertEqual(set(modelle.FORMATE), set(modelle.FORMAT_RANG[True]))
        self.assertEqual(set(modelle.FORMATE), set(modelle.FORMAT_RANG[False]))


class Katalog(unittest.TestCase):
    def test_one_checked_recommendation_per_kind_and_computer(self):
        kat = modelle.katalog(eigene=[])
        for art in modelle.ARTEN:
            for k in hardware.KLASSEN:
                n = [mid for mid, m in kat.items() if m["art"] == art and k in m.get("empfohlen", ())]
                self.assertLessEqual(len(n), 1, (art, k, n))
        for art in ("llm", "helfer", "sehen", "asr", "tts", "bild", "musik"):
            for p in (SPARK, STATION):
                mid = modelle.empfohlen(art, kat, p)
                self.assertTrue(mid, (art, p["id"]))
                self.assertFalse(kat[mid].get("eigen"))
        # a variant does not inherit its base's recommendation
        self.assertNotIn("empfohlen", kat["qwen36-35b-a3b-nvfp4-ohne-mtp"])

    def test_wrong_lists_and_own_entries_are_refused(self):
        m = dict(modelle.katalog(eigene=[])["qwen3-asr-1.7b"])
        for bad in ("gb10", ["gb10", "gb10"], ["dgx"], [1]):
            with self.assertRaises(modelle.Fehler, msg=bad):
                modelle.pruefe_eintrag(dict(m, empfohlen=bad))
        eigen = {"id": "eigen-x", "art": "llm", "name": {"de": "x", "en": "x"}, "engine": "vllm", "repo": "a/b",
                 "revision": "a" * 40, "lizenz": "apache-2.0", "gewerblich": True, "platte_gb": 1, "need_gib": 1,
                 "gemessen": False, "gpu_gib": 2, "kontext": 4096, "kann_sehen": False, "werkzeuge": False,
                 "vllm": {}, "anfrage": {}, "messen": "auf_wunsch", "betrieb": "resident", "eigen": True}
        modelle.eigen_ok(dict(eigen))
        with self.assertRaises(modelle.Fehler):
            modelle.eigen_ok(dict(eigen, empfohlen=["gb10"]))

    def test_kind_of_computer(self):
        self.assertEqual(hardware.klasse(SPARK), "gb10")
        self.assertEqual(hardware.klasse(STATION), "gb300")
        self.assertEqual(hardware.klasse(FREMD), "gb10")
        self.assertEqual(hardware.klasse(dict(FREMD, pool_gib=240.0)), "gb300")
        self.assertEqual(hardware.klasse({"id": "ohne_gpu", "gemeinsam": True}), "gb10")


class Seite(unittest.TestCase):
    def test_rows_and_kinds_name_the_recommendation(self):
        d = modellseite.seite()
        for a in d["arten"]:
            marked = [m["id"] for m in a["modelle"] if m["empfohlen"]]
            self.assertEqual(marked, [a["empfohlen"]] if a["empfohlen"] else [], a["art"])
        self.assertTrue(next(a for a in d["arten"] if a["art"] == "llm")["empfohlen"])

    def test_both_pages_show_star_reason_and_recommendation(self):
        with open(os.path.join(JS, "modelle.js"), encoding="utf-8") as f:
            m = f.read()
        with open(os.path.join(JS, "konsole.js"), encoding="utf-8") as f:
            k = f.read()
        for src in (m, k):
            self.assertIn("aufgabe:", src)
            self.assertIn("Geprüfte Empfehlung", src)
            self.assertIn("m.empfohlen", src)
            self.assertIn("warum", src)
        self.assertIn("(d.treffer||[]).map(treffer)", k)

    def test_two_shelves_checked_first_own_below(self):
        """Dominik 2026-11-16 „es sollten geprüfte angezeigt werden sowie auch alles mögliche“, 2026-11-17 „ja lege damit
        los“: the checked catalog and the own models stand apart, in the panel and in the Konsole."""
        with open(os.path.join(JS, "modelle.js"), encoding="utf-8") as f:
            m = f.read()
        with open(os.path.join(JS, "konsole.js"), encoding="utf-8") as f:
            k = f.read()
        regale = m[m.index("function mdRegale"):m.index("// after „Ausprobieren“")]
        self.assertIn("a.modelle.filter(m=>!m.eigen)", regale)
        self.assertIn("a.modelle.filter(m=>m.eigen)", regale)
        self.assertLess(regale.index("'Geprüft'"), regale.index("'Eigene, ungeprüft'"))
        self.assertIn("${mdRegale(a,w)}", m)
        self.assertIn("a.modelle.filter(m=>!m.eigen).map(m=>zeile(a,m))", k)
        self.assertIn("'Eigene, ungeprüft'", k)


if __name__ == "__main__":
    unittest.main()
