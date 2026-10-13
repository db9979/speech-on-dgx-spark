"""Treffer nachsortieren (nachsortieren.py, plan plaene/suche-schaerfen.md, Stufe 3): off by default, only the
admin's switch, the cross-encoder's order with a fixed floor, never longer than the budget, never waiting for a
start or another re-ranking (then the mix's order stays), numbers only in the journal and the trace, pinned model
files. No real model: the worker's answer is replaced."""
import asyncio
import contextlib
import io
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import embed_worker  # noqa: E402
import features  # noqa: E402
import nachsortieren  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import suchpruefung  # noqa: E402
import wissen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
DAY = 1_800_000_000.0


def uid_of(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def hits(n):
    return [{"id": f"{i:012x}", "name": f"d{i}.txt", "page": None, "text": f"Stelle {i}", "head": "", "score": 1 / (60 + i)}
            for i in range(n)]


class Running:
    """The model as if it ran: scores from a function, after a delay."""
    def __init__(self, scores, delay=0.0):
        self.scores, self.delay, self.calls = scores, delay, 0

    async def __call__(self, query, texts):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return [self.scores(i, t) for i, t in enumerate(texts)]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(documents=True, rerank=True, rerank_model="klein", rerank_ms=800)
        nachsortieren._lock = None
        self.patches = [mock.patch.object(nachsortieren, "running", return_value=True),
                        mock.patch.object(nachsortieren, "_size", "klein")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        helpers.set_config(rerank=False, rerank_model="klein", rerank_ms=800)

    def rank(self, scores, delay=0.0, n=30, k=5, keep=True, trace=None):
        fake = Running(scores, delay)
        out = io.StringIO()
        with mock.patch.object(nachsortieren, "_scores", fake), contextlib.redirect_stdout(out):
            got, word = asyncio.run(nachsortieren.rank("Wie hoch ist die Kaution?", hits(n), k, keep, trace))
        return got, word, out.getvalue(), fake


class Defaults(Base):
    def test_off_by_default_only_the_admin_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["rerank"], False)
        self.assertEqual((ch["rerank_model"], ch["rerank_ms"]), ("klein", 800))
        self.assertNotIn("nachsortieren", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["nachsortieren"].parent, "documents")
        helpers.set_config(rerank=False)
        self.assertFalse(nachsortieren.allowed(uid_of("Nachsortieren Aus")))
        self.assertFalse(nachsortieren.allowed(None))      # a guest has no profile
        helpers.set_config(rerank=True)
        self.assertTrue(nachsortieren.allowed(uid_of("Nachsortieren Aus")))

    def test_the_admin_validates_model_and_budget(self):
        for key, bad in (("rerank_ms", 299), ("rerank_ms", 2001), ("rerank_ms", "800"), ("rerank_model", "riesig")):
            cfg = ADMIN.get("/api/config").json()
            cfg["chat"][key] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, (key, bad))
        self.assertEqual(set(embed_worker.RANK), set(nachsortieren.SIZES))


class Ranking(Base):
    def test_the_cross_encoders_order_with_a_floor(self):
        # the mix had 0..29; the model likes 7 best, then 3; everything else does not answer the question
        got, word, log, _ = self.rank(lambda i, t: {7: 5.0, 3: 2.0, 12: -3.5}.get(i, -9.0))
        self.assertEqual(word, "ok")
        self.assertEqual([h["text"] for h in got], ["Stelle 7", "Stelle 3", "Stelle 12"])
        self.assertIn("wissen: nachsortieren | 30 -> 3 |", log)
        self.assertNotIn("Kaution", log)
        got, _, _, _ = self.rank(lambda i, t: -9.0)
        self.assertEqual(got, [])         # nothing answers the question: nothing found, honestly

    def test_too_slow_keeps_the_mix_and_frees_the_model_afterwards(self):
        helpers.set_config(rerank_ms=300)
        fake = Running(lambda i, t: float(i), delay=0.6)

        async def go():
            with mock.patch.object(nachsortieren, "_scores", fake):
                first = await nachsortieren.rank("Frage", hits(30), 5)
                busy = await nachsortieren.rank("Frage", hits(30), 5)      # the slow one still holds the model
                await asyncio.sleep(0.5)
                again = await nachsortieren.rank("Frage", hits(30), 5)
            return first, busy, again
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            (got, word), (_, word2), (_, word3) = asyncio.run(go())
        self.assertEqual(word, "langsam")
        self.assertEqual([h["text"] for h in got], [f"Stelle {i}" for i in range(5)])
        self.assertEqual(word2, "belegt")
        self.assertEqual(word3, "langsam")
        self.assertIn("wissen: nachsortieren langsam | 30 treffer | reihenfolge der mischung", out.getvalue())

    def test_a_search_never_waits_for_the_start(self):
        for p in self.patches:
            p.stop()
        self.patches = []
        with mock.patch.object(nachsortieren, "running", return_value=False), \
                mock.patch.object(nachsortieren, "_start", mock.AsyncMock()) as start:
            got, word, log, fake = self.rank(lambda i, t: 1.0)
            self.assertEqual(word, "startet")
            self.assertEqual(len(got), 5)
            got, word, log, fake = self.rank(lambda i, t: 1.0, keep=False)   # "Erst lokal" rides along only
            self.assertEqual(word, "aus")
        self.assertEqual(fake.calls, 0)
        self.assertEqual(start.await_count, 1)

    def test_a_broken_model_keeps_the_mix(self):
        async def broken(query, texts):
            raise RuntimeError("no answer")
        out = io.StringIO()
        with mock.patch.object(nachsortieren, "_scores", broken), mock.patch.object(nachsortieren, "_stop") as stop, \
                contextlib.redirect_stdout(out):
            got, word = asyncio.run(nachsortieren.rank("Frage", hits(10), 5))
        self.assertEqual((word, len(got)), ("fehler", 5))
        stop.assert_called()

    def test_the_trace_gets_numbers_only(self):
        class Tr:
            steps = []

            def step(self, kind, name, start, end=None, **info):
                self.steps.append((kind, name, info))
        tr = Tr()
        self.rank(lambda i, t: float(-i), trace=tr)
        self.assertEqual(tr.steps, [("tool", "Nachsortieren", {"n": 30, "keep": 5, "state": "ok"})])


class Search(Base):
    def test_the_document_search_hands_over_thirty_and_gets_k(self):
        uid = uid_of("Nachsortieren Suche")
        seen = {}

        def fake_search(u, q, k, *a):
            seen["k"] = k
            return hits(k)
        with mock.patch.object(documents, "search", fake_search), mock.patch.object(wissen, "_sharers", return_value=[]), \
                mock.patch.object(nachsortieren, "_scores", Running(lambda i, t: float(i))), contextlib.redirect_stdout(io.StringIO()):
            got = asyncio.run(wissen.search(uid, "Kaution", k=4, semantic=False))
        self.assertEqual(seen["k"], nachsortieren.CANDIDATES)
        self.assertEqual([h["text"] for h in got], ["Stelle 29", "Stelle 28", "Stelle 27", "Stelle 26"])
        helpers.set_config(rerank=False)
        with mock.patch.object(documents, "search", fake_search), mock.patch.object(wissen, "_sharers", return_value=[]):
            got = asyncio.run(wissen.search(uid, "Kaution", k=4, semantic=False))
        self.assertEqual(seen["k"], 4)
        self.assertEqual(len(got), 4)

    def test_the_search_check_measures_the_reranked_order(self):
        helpers.set_config(search_check=True)
        self.addCleanup(helpers.set_config, search_check=False)
        uid = uid_of("Nachsortieren Pruefung")
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with contextlib.suppress(FileNotFoundError):
            os.remove(suchpruefung._path(uid))
        a = documents.add(uid, "Kaution.txt", b"x", text="Die Sicherheit beträgt drei Monatsmieten.")["id"]
        documents.add(uid, "Miete.txt", b"x", text="Die Miete und die Kaution zahlt man monatlich.")
        c = TestClient(panel.app)
        c.post("/api/profile/login", json={"name": "Nachsortieren Pruefung", "pin": "1234"})
        self.assertEqual(c.post("/api/profile/suchpruefung", json={"q": "Wie hoch ist die Kaution?", "doc": a}).status_code, 200)
        with mock.patch.object(nachsortieren, "_scores", Running(lambda i, t: 3.0 if "Sicherheit" in t else -1.0)), \
                contextlib.redirect_stdout(io.StringIO()):
            s = asyncio.run(suchpruefung.run(uid, DAY, "knopf"))
        self.assertEqual(s["modes"]["nachsortiert"], {"top5": 100, "top1": 100})
        self.assertIn("rank_ms", s)


class Pins(unittest.TestCase):
    def test_model_files_are_pinned_the_first_time(self):
        with contextlib.suppress(FileNotFoundError):
            os.remove(nachsortieren.PINS)
        self.assertTrue(nachsortieren._check_pins("klein", {"a/model.onnx": "1" * 64}))
        self.assertTrue(nachsortieren._check_pins("klein", {"a/model.onnx": "1" * 64}))
        self.assertFalse(nachsortieren._check_pins("klein", {"a/model.onnx": "2" * 64}))
        self.assertTrue(nachsortieren._check_pins("gross", {"b/model.onnx": "3" * 64}))   # each size its own
        self.assertFalse(nachsortieren._check_pins("klein", {}))
        os.remove(nachsortieren.PINS)


if __name__ == "__main__":
    unittest.main()
