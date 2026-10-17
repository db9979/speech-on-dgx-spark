"""Zustand → Modelle einfacher (Dominik 2026-10-17 „1a 2a 3a 4b“, modelle.such_*, modelle.probe_*, modellseite
eigen_suche, admin_messen probe, admin_probe_weg): the search at Hugging Face goes only through netguard, takes only
plain words, gives every hit the fixed quick rules and never adds or downloads anything; „Ausprobieren“ is „Messen“ with
a note that asks afterwards, once, for a day, removed by a switch of that kind or „Verwerfen“. Nothing depends on the
time of day."""
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import modelle  # noqa: E402
import modellseite  # noqa: E402
import steuer  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000.0
DSPARK = "qwen38-27b-nvfp4-dspark"


def hit(repo="beispiel/klein-8b", **k):
    return dict({"id": repo, "downloads": 1234, "tags": ["safetensors", "text-generation"],
                 "config": {"architectures": ["Qwen3ForCausalLM"]}, "safetensors": {"parameters": {"BF16": 8_000_000_000}},
                 "cardData": {"license": "apache-2.0"}, "gated": False}, **k)


class Suche(unittest.TestCase):
    def test_only_plain_words_go_out(self):
        for bad in ("", "a", "x" * 61, "qwen&limit=1000", "../api", "a\nb", "qwen?x", "q%20", "<b>"):
            with self.assertRaises(modelle.Fehler, msg=bad):
                modelle.such_url(bad)
        url = modelle.such_url("qwen coder 30b")
        self.assertTrue(url.startswith("https://huggingface.co/api/models?search=qwen%20coder%2030b&filter=safetensors&"))
        self.assertEqual(modelle.such_url("Qwen/Qwen3-8B").split("&")[0], "https://huggingface.co/api/models?search=Qwen%2FQwen3-8B")

    def test_every_hit_gets_the_quick_rules(self):
        kat = modelle.katalog()
        da = next(m["repo"] for m in kat.values() if m["art"] == "llm" and m.get("repo"))
        items = [hit(), hit("x/gated", gated="manual"), hit("x/code", tags=["safetensors", "custom_code"]),
                 hit("x/automap", config={"architectures": ["Qwen3ForCausalLM"], "auto_map": {"AutoModel": "m.X"}}),
                 hit("x/gguf", tags=["gguf"], safetensors=None), hit("x/arch", config={"architectures": ["MyOwnForCausalLM"]}),
                 hit("x/riesig", safetensors={"parameters": {"BF16": 200_000_000_000}}), hit(da),
                 hit("bad name/../x"), "kein dict", hit("x/sehen", config={"architectures": ["Qwen3VLForConditionalGeneration"]})]
        got = {h["repo"]: h["nein"] for h in modelle.such_treffer(items, "llm", 121.0, kat)}
        self.assertEqual(got, {"beispiel/klein-8b": "", "x/gated": "zugang", "x/code": "code", "x/automap": "code",
                               "x/gguf": "format", "x/arch": "architektur", "x/riesig": "budget", da: "schon", "x/sehen": ""})
        h = modelle.such_treffer([hit()], "llm", 121.0, kat)[0]
        self.assertEqual((h["gb"], h["need_gib"], h["lizenz"], h["gewerblich"], h["downloads"]), (16.0, 27, "apache-2.0", True, 1234))
        self.assertEqual(modelle.such_treffer([hit("x/l", config={"architectures": ["Qwen3ForCausalLM"]})], "sehen", 121.0, kat)[0]["nein"],
                         "architektur")      # a language model is no image understanding
        self.assertEqual(len(modelle.such_treffer([hit(f"x/m{i}") for i in range(50)], "llm", 121.0, kat)), modelle.SUCHE_MAX)
        for bad_art, items in (("asr", []), ("llm", {"error": "x"})):
            with self.assertRaises(modelle.Fehler):
                modelle.such_treffer(items, bad_art, 121.0, kat)


class Probe(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(), "probe.json")
        self.kat = modelle.katalog()

    def test_asks_once_the_measurement_is_there(self):
        for mid, art in (("x; reboot", "llm"), (DSPARK, "musik")):
            with self.assertRaises(modelle.Fehler):
                modelle.probe_merken(mid, art, self.p, now=T0)
        self.assertIsNone(modelle.probe_stand(self.kat, {}, [], False, self.p, now=T0))
        modelle.probe_merken(DSPARK, "llm", self.p, now=T0)
        alt = {"modelle": {DSPARK: {"zeit": T0 - 3600, "tok_s": 20.0}, "qwen38-27b-nvfp4": {"tok_s": 24.7}}}
        s = modelle.probe_stand(self.kat, alt, ["qwen38-27b-nvfp4"], False, self.p, now=T0 + 60)
        self.assertEqual((s["fertig"], s["jetzt_id"], s["jetzt_tok_s"]), (False, "qwen38-27b-nvfp4", 24.7))   # an older one
        neu = {"modelle": {DSPARK: {"zeit": T0 + 900, "tok_s": 31.2, "ok": True}, "qwen38-27b-nvfp4": {"tok_s": 24.7}}}
        self.assertFalse(modelle.probe_stand(self.kat, neu, ["qwen38-27b-nvfp4"], True, self.p, now=T0 + 900)["fertig"])  # still measuring
        s = modelle.probe_stand(self.kat, neu, ["qwen38-27b-nvfp4"], False, self.p, now=T0 + 1000)
        self.assertEqual((s["fertig"], s["ok"], s["tok_s"]), (True, True, 31.2))
        neu["modelle"][DSPARK]["ok"] = False
        self.assertFalse(modelle.probe_stand(self.kat, neu, [], False, self.p, now=T0 + 1000)["ok"])
        self.assertIsNone(modelle.probe_stand(self.kat, neu, [], False, self.p, now=T0 + modelle.PROBE_SEK + 1))   # a day
        with open(self.p, "w") as f:
            json.dump({"id": DSPARK, "art": "sehen", "zeit": T0}, f)          # changed by hand: counts as none
        self.assertIsNone(modelle.probe_stand(self.kat, neu, [], False, self.p, now=T0))
        self.assertTrue(modelle.probe_weg(self.p))
        self.assertFalse(modelle.probe_weg(self.p))


class Panel(unittest.TestCase):
    def setUp(self):
        for k in [k for k in guard._rate if k[0] in ("modelle_eigen", "modelle", "modelle_messen", "modelle_wechsel")]:
            guard._rate.pop(k, None)
        self.saved = modellseite._lanes, modellseite._laeuft, modellseite._misst
        modellseite._lanes = lambda: []
        modellseite._laeuft = lambda: False
        modellseite._misst = lambda: False
        for f in (modelle.PROBE, modelle.MESS_WUNSCH, modelle.WUNSCH):
            self.addCleanup(lambda f=f: os.path.exists(f) and os.remove(f))

    def tearDown(self):
        modellseite._lanes, modellseite._laeuft, modellseite._misst = self.saved
        helpers.set_config(modelle_wechseln=False, modelle_eigene=False)
        modellseite._live["t"] = None

    def client(self, status=200, body=None, seen=None):
        seen = {} if seen is None else seen

        class Antwort:
            status_code = status

            def json(self):
                if body is None:
                    raise ValueError("kein json")
                return body

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
        return client

    def test_search_only_with_the_switch_only_through_netguard(self):
        seen = {}
        with mock.patch.object(modellseite.netguard, "client", self.client(body=[hit()], seen=seen)), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ADMIN.post("/api/admin/modelle/eigen/suche", json={"art": "llm", "q": "klein"}).status_code, 409)
            self.assertEqual(seen, {})
            helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
            self.assertEqual(ADMIN.post("/api/admin/modelle/eigen/suche", json={"art": "llm", "q": "a&limit=9"}).status_code, 400)
            self.assertEqual(seen, {})
            r = ADMIN.post("/api/admin/modelle/eigen/suche", json={"art": "llm", "q": "klein"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([h["repo"] for h in r.json()["treffer"]], ["beispiel/klein-8b"])
        self.assertEqual(seen["mode"], modellseite.netguard.PUBLIC)
        self.assertIs(seen["follow_redirects"], False)
        self.assertEqual(seen["max_bytes"], modelle.SUCHE_ANTWORT_MAX)
        self.assertTrue(seen["url"].startswith("https://huggingface.co/api/models?search=klein&"))
        self.assertIn("modelle: suche abgelehnt suche", out.getvalue())
        self.assertIn("modelle: suche 1 treffer", out.getvalue())
        self.assertFalse(os.path.exists(modelle.EIGENE))                   # searching adds nothing
        anon = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(anon.post("/api/admin/modelle/eigen/suche", json={"art": "llm", "q": "klein"}).status_code, (401, 403))

    def test_search_answers_when_hugging_face_does_not(self):
        helpers.set_config(modelle_wechseln=True, modelle_eigene=True)
        for status, body, code in ((500, [], 400), (200, None, 400), (200, {"error": "x"}, 400)):
            guard._rate.clear()
            with mock.patch.object(modellseite.netguard, "client", self.client(status, body)), redirect_stdout(io.StringIO()):
                self.assertEqual(ADMIN.post("/api/admin/modelle/eigen/suche", json={"art": "llm", "q": "klein"}).status_code, code)

    def test_try_measures_asks_and_goes_away(self):
        helpers.set_config(modelle_wechseln=True)
        done = subprocess.CompletedProcess([], 0, b"", b"")
        out = io.StringIO()
        with mock.patch.object(modellseite.subprocess, "run", return_value=done), mock.patch.object(steuer, "remote", return_value=False), \
                mock.patch.object(modelle, "gesamt_gib", return_value=121.0), redirect_stdout(out):
            r = ADMIN.post("/api/admin/modelle/messen", json={"id": "gemma-4-26b-a4b", "probe": True})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(modelle.read_json(modelle.PROBE, {})["id"], "gemma-4-26b-a4b")
            p = r.json()["wechsel"]["probe"]
            self.assertEqual((p["id"], p["fertig"]), ("gemma-4-26b-a4b", False))
            self.assertEqual(p["name"], modelle.katalog()["gemma-4-26b-a4b"]["name"]["de"])
            r = ADMIN.delete("/api/admin/modelle/probe")
            self.assertEqual(r.status_code, 200)
            self.assertIsNone(r.json()["wechsel"]["probe"])
            ADMIN.post("/api/admin/modelle/messen", json={"id": "gemma-4-26b-a4b"})          # „Messen“ alone: no question
            self.assertFalse(os.path.exists(modelle.PROBE))
        for word in ("ausprobieren angefragt", "ausprobieren verworfen"):
            self.assertIn("modelle: " + word, out.getvalue())

    def test_a_switch_of_that_kind_answers_the_question(self):
        helpers.set_config(modelle_wechseln=True)
        modelle.probe_merken("qwen3-asr-0.6b", "asr")
        target = "qwen3-asr-0.6b" if modelle.jetzt_id("asr", modelle.load_config()) != "qwen3-asr-0.6b" else "qwen3-asr-1.7b"
        done = subprocess.CompletedProcess([], 0, b"", b"")
        with mock.patch.object(modellseite.subprocess, "run", return_value=done), mock.patch.object(steuer, "remote", return_value=False), \
                mock.patch.object(modelle, "gesamt_gib", return_value=121.0), redirect_stdout(io.StringIO()) as out:
            r = ADMIN.post("/api/admin/modelle/wechseln", json={"art": "asr", "id": target})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(os.path.exists(modelle.PROBE))
        self.assertIn("modelle: ausprobieren erledigt", out.getvalue())

    def test_off_no_question_on_the_page(self):
        modelle.probe_merken("gemma-4-26b-a4b", "sehen")
        self.assertIsNone(ADMIN.get("/api/admin/modelle").json()["wechsel"]["probe"])


if __name__ == "__main__":
    unittest.main()
