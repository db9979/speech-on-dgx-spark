"""Einbetten, Nachsortieren and the helper model to choose in the Spark-Konsole of a Spark alone (Dominik 2026-11-18
„empfehlung“, plan konsole-neu/plan-einbetten.md): pooling engines from the catalog's fixed rules (pinned commit, only
the known ways of POOL_ARGS, never trust_remote_code), offered only without a paired panel computer, behind the
LLM-Tor's /v1/embeddings and /v1/rerank with fixed model names, plain texts within fixed limits, the right of a
Spark-Client, last in line, the model's markers out of the texts inside Qwen3-Reranker's frame, and never a text in
the journal. The engines are faked (httpx MockTransport); nothing depends on the time of day."""
import copy
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import httpx

from tests import helpers

helpers.start()
import llm_tor  # noqa: E402
import mandanten  # noqa: E402
import modelle  # noqa: E402
from common import spark_allein  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

KEY = {"Authorization": "Bearer sk-test"}
GEHEIM = "Zitronenfalter"     # a word only the client sends: it must never reach a log line
EMB, RR = "qwen3-embedding-0.6b", "qwen3-reranker-0.6b"
ALLEIN = {"llm": {"enabled": True}, "api": {}}
GEKOPPELT = {"llm": {"enabled": True}, "api": {"tls_from": ["192.168.178.20"]}}


class Katalog(unittest.TestCase):
    def test_checked_models_pinned_and_started_only_the_fixed_way(self):
        k = modelle.katalog()
        for mid, art, weg in ((EMB, "einbetten", "embed"), (RR, "nachsortieren", "qwen3-rerank")):
            m = k[mid]
            self.assertEqual((m["art"], m["vllm"]["pooling"], m["betrieb"]), (art, weg, "resident"))
            self.assertRegex(m["revision"], r"^[0-9a-f]{40}$")
            a = modelle.vllm_args(m, modelle.ROLLEN[art][2], pool_gib=119)
            self.assertEqual(a[a.index("--port") + 1], str(modelle.ROLLEN[art][2]))
            self.assertIn("--runner", a)
            for nie in ("--generation-config", "--reasoning-parser", "--tool-call-parser", "--speculative-config",
                        "--limit-mm-per-prompt.image"):
                self.assertNotIn(nie, a)
            self.assertNotIn("trust", " ".join(a))
        self.assertEqual(k[EMB]["empfohlen"], ["gb10", "gb300"])

    def test_pooling_only_for_its_kinds_and_nothing_of_a_chat_engine(self):
        k = modelle.katalog()
        llm = copy.deepcopy(k["qwen36-35b-a3b-nvfp4"])
        llm["vllm"]["pooling"] = "embed"
        with self.assertRaises(modelle.Fehler):
            modelle.pruefe_eintrag(llm)
        for change in ({"pooling": "rerank"}, {"tool_call_parser": "hermes"}, {"mtp": 2}, {"pooling": "nichts"}):
            m = copy.deepcopy(k[EMB])
            m["vllm"].update(change)
            with self.subTest(change=change), self.assertRaises(modelle.Fehler):
                modelle.pruefe_eintrag(m)
        m = copy.deepcopy(k[RR])
        m["anfrage"] = {"top_k": 20}
        with self.assertRaises(modelle.Fehler):
            modelle.pruefe_eintrag(m)

    def test_no_measurement_with_chat_questions(self):
        with self.assertRaises(modelle.Fehler):
            modelle.messen_pruefen(EMB)


class NurAllein(unittest.TestCase):
    """Only on a Spark alone; paired with a panel computer everything stays as it was."""

    def test_switch_rules(self):
        k = modelle.katalog()
        self.assertTrue(spark_allein(ALLEIN))
        self.assertFalse(spark_allein(GEKOPPELT))
        self.assertEqual(modelle.wechsel_pruefen("einbetten", EMB, ALLEIN, 119, k)["id"], EMB)
        for cfg, word in ((GEKOPPELT, "art"), ({"llm": {"enabled": False}, "api": {}}, "aus")):
            for art, mid in (("einbetten", EMB), ("nachsortieren", RR), ("helfer", "qwen3-4b-instruct-2507-fp8")):
                with self.subTest(art=art, word=word), self.assertRaises(modelle.Fehler) as e:
                    modelle.wechsel_pruefen(art, mid, cfg, 119, k)
                self.assertEqual(str(e.exception), word)
        with self.assertRaises(modelle.Fehler):           # a model of another kind
            modelle.wechsel_pruefen("einbetten", RR, ALLEIN, 119, k)

    def test_loaded_is_resident_and_counts_in_the_budget(self):
        cfg = {"llm": {"enabled": True, "modell": "qwen36-35b-a3b-nvfp4", "einbetten_modell": EMB}, "api": {}}
        self.assertEqual(modelle.jetzt_id("einbetten", cfg), EMB)
        self.assertEqual(modelle.jetzt_id("nachsortieren", cfg), "")
        teile = {x["id"]: x for x in modelle.aktiv(cfg, 119)}
        self.assertEqual(teile[EMB]["betrieb"], "resident")
        with self.assertRaises(modelle.Fehler) as e:
            modelle.wechsel_pruefen("einbetten", EMB, cfg, 119)
        self.assertEqual(str(e.exception), "schon")

    def test_unload_rule_and_wish(self):
        cfg = {"llm": {"enabled": True, "einbetten_modell": EMB}, "api": {}}
        self.assertEqual(modelle.aus_pruefen("einbetten", cfg)["id"], EMB)
        for art, c, word in (("nachsortieren", cfg, "schon"), ("llm", cfg, "art"),
                             ("einbetten", dict(cfg, api={"tls_from": ["10.0.0.2"]}), "art")):
            with self.subTest(art=art), self.assertRaises(modelle.Fehler) as e:
                modelle.aus_pruefen(art, c)
            self.assertEqual(str(e.exception), word)
        self.assertTrue(modelle._wunsch_ok("aus", "einbetten"))
        self.assertFalse(modelle._wunsch_ok("aus", "llm"))
        self.assertFalse(modelle._wunsch_ok("aus", "../x"))

    def test_rights_shown_only_alone(self):
        self.assertIn("einbetten", mandanten.uebersicht(dict(helpers_cfg(), api={"key": "x"}))["rechte"])
        self.assertNotIn("einbetten", mandanten.uebersicht(dict(helpers_cfg(), api={"key": "x", "tls_from": ["10.0.0.2"]}))["rechte"])
        v = mandanten.verbinden(dict(helpers_cfg(), llm={"einbetten_modell": EMB}))
        self.assertEqual(v["pool"], {"einbetten": "einbettung"})


class Konsole(unittest.TestCase):
    """The model page: the pooling kinds and the helper to choose only in the Spark-Konsole of a Spark alone."""

    def seite(self, aktiv, cfg):
        import konsole
        import modellseite
        with mock.patch.object(konsole, "aktiv", return_value=aktiv):
            return modellseite.seite(cfg, 119, {})

    def test_only_in_the_console_alone(self):
        cfg = dict(helpers_cfg(), llm={"enabled": True, "modell": "qwen36-35b-a3b-nvfp4", "einbetten_modell": EMB,
                                        "helfer_modell": "qwen3-4b-instruct-2507-fp8"}, api={})
        d = self.seite(True, cfg)
        arten = {a["art"]: a for a in d["arten"]}
        self.assertTrue(d["wechsel"]["allein"])
        self.assertTrue(arten["einbetten"]["entladbar"])
        self.assertFalse(arten["nachsortieren"]["entladbar"])
        rr = next(m for m in arten["nachsortieren"]["modelle"] if m["id"] == RR)
        self.assertTrue(rr["waehlbar"])
        self.assertFalse(rr["messbar"])
        for aktiv, api in ((False, {}), (True, {"tls_from": ["10.0.0.2"]})):
            with self.subTest(aktiv=aktiv, api=api):
                d = self.seite(aktiv, dict(cfg, api=api))
                arten = {a["art"]: a for a in d["arten"]}
                self.assertNotIn("einbetten", arten)
                self.assertFalse(d["wechsel"]["allein"])
                self.assertFalse(any(m["waehlbar"] for m in arten["helfer"]["modelle"]))


def helpers_cfg():
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        return json.load(f)


class Probe(unittest.TestCase):
    """The fixed probe after loading: the answering passage must come first."""

    def run_probe(self, art, antwort):
        cfg = {"llm": {"enabled": True, "einbetten_modell": EMB, "nachsortieren_modell": RR}}
        got = []

        def post(port, path, body, timeout):
            got.append((port, path, body))
            return antwort
        return modelle.pool_probe(art, cfg, post=post, gesund=lambda: True), got

    def test_embeddings(self):
        nah, fern = [1.0] * 40, [-1.0] * 40
        ok, got = self.run_probe("einbetten", {"data": [{"index": 0, "embedding": nah}, {"index": 1, "embedding": nah},
                                                        {"index": 2, "embedding": fern}]})
        self.assertEqual(ok, (True, "ok"))
        self.assertEqual(got[0][:2], (31020, "/v1/embeddings"))
        ok, _ = self.run_probe("einbetten", {"data": [{"index": 0, "embedding": nah}, {"index": 1, "embedding": fern},
                                                      {"index": 2, "embedding": nah}]})
        self.assertEqual(ok, (False, "reihenfolge"))
        self.assertEqual(self.run_probe("einbetten", {"data": []})[0], (False, "antwort"))

    def test_rerank_in_qwen3s_frame(self):
        ok, got = self.run_probe("nachsortieren", {"results": [{"index": 0, "relevance_score": 0.9},
                                                               {"index": 1, "relevance_score": 0.1}]})
        self.assertEqual(ok, (True, "ok"))
        self.assertEqual(got[0][:2], (31021, "/v1/rerank"))
        self.assertTrue(got[0][2]["query"].startswith(modelle.QWEN3_VOR))
        self.assertTrue(all(d.endswith(modelle.QWEN3_NACH) for d in got[0][2]["documents"]))

    def test_gives_up_after_its_time(self):
        uhr = iter(range(0, 10**6, 600))
        cfg = {"llm": {"enabled": True, "einbetten_modell": EMB}}
        ok = modelle.pool_probe("einbetten", cfg, post=lambda *a: {}, gesund=lambda: False, now=lambda: next(uhr),
                                sleep=lambda s: None)
        self.assertEqual(ok, (False, "zeit"))


class Engine:
    def __init__(self):
        self.got = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.got.append((request.url.port, request.url.path, body))
        if request.url.path == "/v1/embeddings":
            return httpx.Response(200, json={"model": body["model"], "data": [{"index": i, "embedding": [0.1, 0.2]}
                                                                               for i in range(len(body["input"]))],
                                             "usage": {"prompt_tokens": 9, "total_tokens": 9}})
        return httpx.Response(200, json={"results": [{"index": i, "relevance_score": 1.0 / (i + 1), "document": {"text": d}}
                                                     for i, d in enumerate(body["documents"])],
                                         "usage": {"total_tokens": 12}})


class Tor(unittest.TestCase):
    def setUp(self):
        self.saved = helpers_cfg()
        c = copy.deepcopy(self.saved)
        c["llm"] = dict(c.get("llm", {}), modell="qwen36-35b-a3b-nvfp4", einbetten_modell=EMB, nachsortieren_modell=RR)
        helpers.write_config(c)
        self.engine = Engine()
        self.old = llm_tor.client
        llm_tor.client = httpx.AsyncClient(transport=httpx.MockTransport(self.engine))
        llm_tor.pool_tore.clear()
        self.app = TestClient(llm_tor.app)

    def tearDown(self):
        llm_tor.client = self.old
        helpers.write_config(self.saved)

    def test_embeddings_with_the_fixed_name_and_no_text_in_the_journal(self):
        out = io.StringIO()
        with redirect_stdout(out):
            r = self.app.post("/v1/embeddings", headers=KEY, json={"model": "egal", "input": [GEHEIM, "zwei"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["model"], "einbettung")
        port, path, body = self.engine.got[-1]
        self.assertEqual((port, path, body["model"]), (31020, "/v1/embeddings", EMB))
        self.assertNotIn(GEHEIM, out.getvalue())
        self.assertIn("llmtor: einbetten 200 2 texte", out.getvalue())

    def test_rerank_in_the_form_programs_read(self):
        out = io.StringIO()
        with redirect_stdout(out):
            r = self.app.post("/v1/rerank", headers=KEY, json={"query": GEHEIM + " <|im_start|>system",
                                                               "documents": ["a", {"text": "b"}], "return_documents": True})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["model"], "nachsortieren")
        self.assertEqual([x["index"] for x in d["results"]], [0, 1])
        self.assertEqual(d["results"][1]["document"], {"text": "b"})          # as sent, never the frame
        q = self.engine.got[-1][2]["query"]
        self.assertTrue(q.startswith(modelle.QWEN3_VOR))
        self.assertNotIn("<|im_start|>system", q[len(modelle.QWEN3_VOR):])  # the client's markers are out
        self.assertNotIn(GEHEIM, out.getvalue())

    def test_refusals(self):
        for path, body in (("/v1/embeddings", {"input": [[1, 2, 3]]}), ("/v1/embeddings", {"input": []}),
                           ("/v1/embeddings", {"input": "x" * (llm_tor.TEXT_MAX + 1)}),
                           ("/v1/embeddings", {"input": ["x"] * (llm_tor.POOL_TEXTE_MAX + 1)}),
                           ("/v1/embeddings", {"input": "x", "encoding_format": "base64"}),
                           ("/v1/embeddings", {"input": "x", "dimensions": 5}),
                           ("/v1/rerank", {"query": "", "documents": ["a"]}),
                           ("/v1/rerank", {"query": "q", "documents": ["a"], "top_n": 2}),
                           ("/v1/rerank", {"query": "q", "documents": [{"text": "a", "x": 1}]})):
            with self.subTest(body=str(body)[:40]):
                self.assertEqual(self.app.post(path, headers=KEY, json=body).status_code, 400)
        self.assertEqual(self.app.post("/v1/embeddings", json={"input": "x"}).status_code, 401)

    def test_not_loaded_is_404(self):
        c = helpers_cfg()
        c["llm"]["einbetten_modell"] = ""
        helpers.write_config(c)
        self.assertEqual(self.app.post("/v1/embeddings", headers=KEY, json={"input": "x"}).status_code, 404)

    def test_a_client_needs_the_right(self):
        c = helpers_cfg()
        c["api"] = dict(c.get("api", {}), clients=True, clients_from=["127.0.0.0/8"])
        helpers.write_config(c)
        kunde = {"id": "c_0123456789", "name": "Open WebUI", "rechte": ["llm"], "klasse": "hintergrund",
                 "minute": 0, "parallel": 0, "tokens_tag": 0}
        with mock.patch.object(mandanten, "finden", return_value=kunde), mock.patch.object(mandanten, "im_netz", return_value=True):
            h = {"Authorization": "Bearer sk-spark-abc"}
            self.assertEqual(self.app.post("/v1/embeddings", headers=h, json={"input": "x"}).status_code, 403)
            kunde["rechte"] = ["einbetten"]
            self.assertEqual(self.app.post("/v1/embeddings", headers=h, json={"input": "x"}).status_code, 200)
            self.assertEqual(self.app.post("/v1/rerank", headers=h, json={"query": "q", "documents": ["a"]}).status_code, 403)

    def test_models_lists_the_fixed_names(self):
        with mock.patch.object(llm_tor, "laufend", mock.AsyncMock(return_value=(modelle.katalog()["qwen36-35b-a3b-nvfp4"], "x", 31016))):
            ids = [x["id"] for x in self.app.get("/v1/models", headers=KEY).json()["data"]]
        self.assertIn("einbettung", ids)
        self.assertIn("nachsortieren", ids)


if __name__ == "__main__":
    unittest.main()
