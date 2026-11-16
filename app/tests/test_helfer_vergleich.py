"""Hilfsmodell vergleichen (quality.helfer_run), Dominik 2026-11-16 „ok testen wir das ganze mal“.

Plain questions go once to the language model and once to the helper model ("helfer"), streamed and without tools;
the panel's own checks judge both, a fixed rule says whether it is worth it. Only a measurement: nothing about who
answers in a real turn changes. Not ready (503 "loading") is waited for, no room (503 "memory") is said. No clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import contextlib
import io
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import httpx  # noqa: E402
import llm  # noqa: E402
import quality  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _status(code, text):
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    return httpx.HTTPStatusError(text, request=req, response=httpx.Response(code, text=text, request=req))


class HelferVergleich(unittest.TestCase):
    def tearDown(self):
        with contextlib.suppress(OSError):
            os.remove(quality.HELFER_RESULT)

    def test_both_models_get_the_same_plain_questions(self):
        helpers.LLM_CALLS.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            res = asyncio.run(quality.helfer_run("test"))
        self.assertNotIn("error", res)
        self.assertEqual(len(res["cases"]), len(quality.helfer_cases()))
        self.assertGreaterEqual(len(res["cases"]), 12)
        streamed = [b for b in helpers.LLM_CALLS if b.get("stream")]
        names = [b["model"] for b in streamed]
        self.assertEqual(names.count(llm.HELFER), len(res["cases"]) + 1)   # +1: the readiness question
        self.assertEqual(len(names) - names.count(llm.HELFER), len(res["cases"]))
        self.assertFalse([b for b in streamed if b.get("tools")])       # plain answers, never a tool
        byid = {x["id"]: x for x in res["cases"]}
        self.assertTrue(byid["witz"]["main"]["ok"] and byid["witz"]["helfer"]["ok"])
        self.assertFalse(byid["plaudern-hauptstadt"]["helfer"]["ok"])   # the fake model says "Hallo."
        self.assertIsNotNone(res["main"]["first"])
        self.assertEqual(res["helfer"]["total"], len(res["cases"]))
        self.assertEqual(res["load_s"], 0)
        self.assertIn(res["verdict"]["level"], ("ok", "warn"))
        self.assertTrue(res["verdict"]["de"] and res["verdict"]["en"])
        # the log: fixed words and numbers, never a question or an answer
        line = [x for x in out.getvalue().splitlines() if "helfer compare" in x][0]
        self.assertTrue(line.startswith("quality: "))
        self.assertNotIn("Hallo", line)
        self.assertNotIn("Frankreich", line)

    def test_the_admin_starts_it_and_sees_the_result(self):
        c = TestClient(panel.app)
        self.assertIn(c.post("/api/quality", json={"sampling": "helfer"}).status_code, (401, 403))
        c.post("/api/login", json={"password": "secret-admin"})
        with mock.patch.object(quality, "helfer_run", mock.AsyncMock(return_value=None)) as run, \
                mock.patch.object(quality, "run", mock.AsyncMock(return_value=None)) as other:
            c.post("/api/quality", json={"sampling": "helfer"})
        run.assert_called_once()
        other.assert_not_called()
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(quality.helfer_run("test"))
        self.assertEqual(c.get("/api/quality").json()["helfer"]["reason"], "test")

    def test_loading_is_waited_for_and_no_room_is_said(self):
        calls = []

        async def loading_once(c, ccfg, model, case):
            calls.append(model)
            if len(calls) == 1:
                raise _status(503, '{"detail":"loading"}')
            return {"first": 0.1, "seconds": 0.2, "answer": "Hallo.", "raw": "Hallo.", "held": []}
        with mock.patch.object(quality, "_helfer_case", loading_once), mock.patch.object(quality, "HELFER_POLL_S", 0):
            self.assertEqual(asyncio.run(quality._helfer_ready(None, {})), 0)
        self.assertEqual(calls, [llm.HELFER, llm.HELFER])

        async def no_room(c, ccfg, model, case):
            raise _status(503, '{"detail":"memory"}')
        with mock.patch.object(quality, "_helfer_case", no_room), contextlib.redirect_stdout(io.StringIO()):
            res = asyncio.run(quality.helfer_run("test"))
        self.assertEqual(res["error"], "memory")
        self.assertEqual(res["cases"], [])
        self.assertEqual(res["verdict"]["level"], "bad")
        self.assertIn("Speicher", res["verdict"]["de"])

    def test_worth_it_only_when_clearly_faster_and_barely_worse(self):
        def v(a, b, pa, pb):
            return quality.helfer_verdict({"main": {"first": a, "passed": pa}, "helfer": {"first": b, "passed": pb}})
        self.assertEqual(v(2.0, 0.5, 12, 11)["level"], "ok")
        self.assertEqual(v(2.0, 1.5, 12, 12)["level"], "warn")      # only 0.5 s sooner
        self.assertIn("schlechter", v(3.0, 0.5, 12, 9)["de"])      # faster, but three fewer right
        self.assertEqual(v(None, 0.5, 12, 12)["level"], "warn")


if __name__ == "__main__":
    unittest.main()
