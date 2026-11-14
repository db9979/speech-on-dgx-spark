"""Lange Gespräche zusammenfassen (verlaufkurz.py, idea from OmniBot, Dominik 2026-11-14 „1-2“): what the trimming of a long
conversation drops comes back as a short summary, written in the background, bound to exactly those messages, never with
mail or web text, never for guests; off by default. No clock: times are passed in."""
import asyncio
import json
import os
import unittest

from tests import helpers

helpers.start()
import chat  # noqa: E402
import features  # noqa: E402
import panel  # noqa: E402
import verlaufkurz  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0


def talk(n, size=40, mark_at=()):
    out = []
    for i in range(n):
        m = {"role": "user" if i % 2 == 0 else "assistant", "content": f"Nachricht {i} " + "x" * size}
        if i in mark_at:
            m["mark"] = "outside"
        out.append(m)
    return out


class Rules(unittest.TestCase):
    def setUp(self):
        verlaufkurz.forget()

    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(PANEL), "config.default.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f)["chat"]["history_summary"], False)
        self.assertNotIn("chat.history_summary", features.DEFAULT_ON)
        self.assertFalse(features.allowed(verlaufkurz.KEY, None, {}))

    def test_a_summary_belongs_to_exactly_its_messages(self):
        msgs = talk(6)
        h = verlaufkurz._chain("u1", msgs)
        verlaufkurz.keep("u1", 4, h[3], "- Thema Garten", now=NOW)
        self.assertEqual(verlaufkurz.best("u1", msgs, now=NOW)["text"], "- Thema Garten")
        self.assertEqual(verlaufkurz.best("u1", msgs[:4], now=NOW)["n"], 4)
        self.assertIsNone(verlaufkurz.best("u1", msgs[:3], now=NOW), "fewer messages: it does not fit")
        changed = [dict(m) for m in msgs]
        changed[1]["content"] = "anders"
        self.assertIsNone(verlaufkurz.best("u1", changed, now=NOW), "an edited message: never")
        self.assertIsNone(verlaufkurz.best("u2", msgs, now=NOW), "another profile: never")

    def test_the_newest_fitting_one_wins_and_old_ones_go(self):
        msgs = talk(8)
        h = verlaufkurz._chain("u1", msgs)
        verlaufkurz.keep("u1", 2, h[1], "zwei", now=NOW)
        verlaufkurz.keep("u1", 6, h[5], "sechs", now=NOW)
        self.assertEqual(verlaufkurz.best("u1", msgs, now=NOW)["text"], "sechs")
        self.assertIsNone(verlaufkurz.best("u1", msgs, now=NOW + verlaufkurz.KEEP_S + 1))
        for i in range(verlaufkurz.PER_PROFILE + 3):
            verlaufkurz.keep("u3", 1, f"h{i}", str(i), now=NOW)
        self.assertEqual(len(verlaufkurz._store["u3"]), verlaufkurz.PER_PROFILE)

    def test_outside_text_never_goes_in(self):
        text = verlaufkurz._text(talk(4, mark_at=(1,)))
        self.assertIn(verlaufkurz.LEFT_OUT, text)
        self.assertNotIn("Nachricht 1 ", text)
        self.assertIn("Nachricht 2 ", text)

    def test_the_summary_is_short_and_without_thinking(self):
        out = verlaufkurz.clean("<think>geheim</think>\n\n- a\n" + "- " + "b" * 2000)
        self.assertEqual(out, "- a")
        self.assertLessEqual(len(verlaufkurz.clean("- x\n" * 2000)), verlaufkurz.MAX_CHARS)

    def test_the_job_reads_only_what_is_new_and_keeps_the_result(self):
        msgs = talk(6)
        h = verlaufkurz._chain("u4", msgs)
        verlaufkurz.keep("u4", 2, h[1], "- alt", now=NOW)
        seen = {}

        async def fake(system, user, job, max_tokens, **kw):
            seen.update(user=user, job=job, who=kw.get("who"))
            return "- alt\n- neu"
        asyncio.run(verlaufkurz.job("u4", msgs, verlaufkurz.best("u4", msgs, now=NOW), h[-1], {}, fake))
        self.assertEqual(seen["job"], verlaufkurz.JOB)
        self.assertEqual(seen["who"], "u4")
        self.assertIn("- alt", seen["user"])
        self.assertNotIn("Nachricht 1 ", seen["user"])
        self.assertIn("Nachricht 5 ", seen["user"])
        self.assertEqual(verlaufkurz.best("u4", msgs)["text"], "- alt\n- neu")
        self.assertNotIn("u4", verlaufkurz._running)

    def test_a_failing_model_keeps_nothing(self):
        msgs = talk(4)

        async def broken(*a, **kw):
            raise ValueError("kaputt")
        asyncio.run(verlaufkurz.job("u5", msgs, None, verlaufkurz._chain("u5", msgs)[-1], {}, broken))
        self.assertIsNone(verlaufkurz.best("u5", msgs))
        self.assertNotIn("u5", verlaufkurz._running)


class Chat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = "Langgespraech"
        ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "4821"})
        cls.c = TestClient(panel.app)
        assert cls.c.post("/api/profile/login", json={"name": name, "pin": "4821"}).status_code == 200
        cls.uid = cls.c.get("/api/whoami").json()["profile"]["id"]

    def setUp(self):
        helpers.keep_chat(self, "history_summary", "history_chars")
        verlaufkurz.forget()
        self.started = []
        real = verlaufkurz.start

        def fake_start(uid, dropped, hit, chain, ccfg, ask):
            self.started.append((uid, len(dropped)))
            return False
        verlaufkurz.start = fake_start
        self.addCleanup(setattr, verlaufkurz, "start", real)

    def ask(self, msgs, client=None):
        c = client or self.c
        helpers.LLM_CALLS.clear()
        r = c.post("/api/chat", json={"messages": msgs, "speak": False})
        self.assertEqual(r.status_code, 200, r.text)
        helpers.events(r)
        return [b for b in helpers.LLM_CALLS if b.get("stream")][-1]["messages"][0]["content"]

    def long_talk(self):
        return talk(40, size=300) + [{"role": "user", "content": "Und jetzt?"}]

    def test_off_nothing_changes(self):
        helpers.set_config(history_summary=False, history_chars=4000)
        system = self.ask(self.long_talk())
        self.assertNotIn(verlaufkurz.NOTE.strip()[:20], system)
        self.assertEqual(self.started, [])

    def test_on_the_summary_comes_along_and_the_rest_is_started(self):
        helpers.set_config(history_summary=True, history_chars=4000)
        msgs = self.long_talk()
        system = self.ask(msgs)
        self.assertNotIn("Früher in diesem Gespräch", system)   # none yet: the job starts
        self.assertEqual(len(self.started), 1)
        uid, n = self.started[0]
        self.assertEqual(uid, self.uid)
        h = verlaufkurz._chain(self.uid, msgs[:n])
        verlaufkurz.keep(self.uid, n, h[-1], "- Es ging um den Garten.")
        self.started.clear()
        system = self.ask(msgs)
        self.assertIn("Früher in diesem Gespräch", system)
        self.assertIn("- Es ging um den Garten.", system)
        self.assertEqual(self.started, [], "all dropped messages are covered")

    def test_a_short_conversation_needs_none(self):
        helpers.set_config(history_summary=True, history_chars=chat.HISTORY_CHARS)
        self.ask([{"role": "user", "content": "Hallo"}])
        self.assertEqual(self.started, [])

    def test_never_for_guests(self):
        helpers.keep_chat(self, "public")
        helpers.set_config(history_summary=True, history_chars=4000, public=True)
        self.ask(self.long_talk(), TestClient(panel.app))
        self.assertEqual(self.started, [])


if __name__ == "__main__":
    unittest.main()
