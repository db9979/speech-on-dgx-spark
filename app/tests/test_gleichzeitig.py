"""Lesende Werkzeuge gleichzeitig (gleichzeitig.py, idea from OmniBot, Dominik 2026-11-14 „1-2“): reading tools of one round
start together, anything else runs one after the other; fixed rules of the panel, never the model, off by default.
No clock: the order of start and end is recorded, never a duration."""
import ast
import asyncio
import os
import unittest

from tests import helpers

helpers.start()
import chat  # noqa: E402
import chat_tools  # noqa: E402
import features  # noqa: E402
import gleichzeitig  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import taten  # noqa: E402
import werkzeuge  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def calls(*names):
    return [{"name": n, "id": f"c{i}", "arguments": "{}"} for i, n in enumerate(names)]


def choose(*names, stopped=()):
    return gleichzeitig.auswahl(calls(*names), set(stopped), notaus.INTERNET_TOOLS, chat.MAX_CALLS)


class Rules(unittest.TestCase):
    def test_reading_tools_start_together(self):
        self.assertEqual(choose("weather", "calendar_events"), (0, 1))
        self.assertEqual(choose("calendar_events", "reminder_list", "tasks_show"), (0, 1, 2))

    def test_one_call_or_none_runs_as_before(self):
        self.assertEqual(choose("weather"), ())
        self.assertEqual(choose(), ())

    def test_anything_that_changes_runs_alone(self):
        self.assertEqual(choose("calendar_events", "reminder_set"), ())
        self.assertEqual(choose("weather", "home_assistant_action"), ())
        self.assertEqual(choose("calendar_events", "mail_search"), ())

    def test_the_same_tool_twice_runs_one_after_the_other(self):
        # the Fehlerschleife counts per tool and may stop the second call
        self.assertEqual(choose("web_search", "web_search"), ())

    def test_at_most_one_internet_tool(self):
        # after an internet result the next internet tool may use its words (ausleiten.pool_dazu)
        self.assertEqual(choose("weather", "web_search"), ())
        self.assertEqual(choose("weather", "calendar_events", "contacts_search"), (0, 1, 2))

    def test_calls_left_over_are_not_started(self):
        self.assertEqual(choose("calendar_events", "reminder_list", stopped=("reminder_list",)), ())
        many = ("calendar_events", "reminder_list", "tasks_show", "contacts_search", "document_list")
        self.assertEqual(choose(*many), tuple(range(chat.MAX_CALLS)))

    def test_the_list_holds_only_reading_tools(self):
        never = set(taten.KIND) | chat.LOCKED_OUTSIDE | chat.HA_READS | {"pc_look", "memory_save", "memory_forget"}
        self.assertFalse(gleichzeitig.LESEN & never)
        self.assertFalse({n for n in gleichzeitig.LESEN if n.startswith(("mail_", "home_assistant", "pc_"))})
        self.assertFalse(gleichzeitig.LESEN - set(werkzeuge.NAMES), "every tool on the list exists")

    def test_locks_are_set_before_the_first_wait(self):
        # the rule that makes the locks come out as one after the other: chat_tools._run marks outside text, documents
        # and the Zusatzdienste' mail and outside tools before it waits for anything, and every tool of the list is
        # either one of the built-in reads or a Zusatzdienst (no mail branch, which marks mail only later)
        with open(os.path.join(PANEL, "chat_tools.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        run = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run")
        first_wait = min(n.lineno for n in ast.walk(run) if isinstance(n, ast.Await))
        marks = [n.lineno for n in ast.walk(run) if isinstance(n, ast.Assign) for t in n.targets
                 if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "st"
                 and isinstance(t.slice, ast.Constant) and t.slice.value in ("outside", "docs", "mail")]
        self.assertGreaterEqual(len(marks), 4)
        self.assertLess(max(marks), first_wait)


class Chat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = "Gleichzeitig"
        ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "4821"})
        cls.c = TestClient(panel.app)
        assert cls.c.post("/api/profile/login", json={"name": name, "pin": "4821"}).status_code == 200

    def setUp(self):
        helpers.keep_chat(self, "tools_parallel")
        self.log = []
        real = chat_tools.run

        async def fake(t, name, args, st):
            self.log.append(("start", name))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.log.append(("end", name))
            return f"Ergebnis {name}"
        chat_tools.run = fake
        self.addCleanup(setattr, chat_tools, "run", real)

    def ask(self, text):
        r = self.c.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "client": "web"})
        self.assertEqual(r.status_code, 200, r.text)
        return helpers.events(r)

    def tool_results(self):
        last = [b for b in helpers.LLM_CALLS if b.get("stream")][-1]
        return [m["content"] for m in last["messages"] if m["role"] == "tool"]

    def test_off_by_default(self):
        import json
        with open(os.path.join(os.path.dirname(PANEL), "config.default.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f)["chat"]["tools_parallel"], False)
        self.assertNotIn("chat.tools_parallel", features.DEFAULT_ON)
        self.assertFalse(features.allowed(gleichzeitig.KEY, None, {}))

    def test_off_one_after_the_other(self):
        helpers.set_config(tools_parallel=False)
        helpers.LLM_CALLS.clear()
        self.ask("BOTH reminder_list {} || tasks_show {}")
        self.assertEqual(self.log, [("start", "reminder_list"), ("end", "reminder_list"),
                                    ("start", "tasks_show"), ("end", "tasks_show")])
        self.assertEqual(self.tool_results(), ["Ergebnis reminder_list", "Ergebnis tasks_show"])

    def test_on_together_and_in_the_models_order(self):
        helpers.set_config(tools_parallel=True)
        helpers.LLM_CALLS.clear()
        with helpers_capture() as out:
            self.ask("BOTH reminder_list {} || tasks_show {}")
        self.assertEqual(self.log[:2], [("start", "reminder_list"), ("start", "tasks_show")])
        self.assertEqual(sorted(self.log[2:]), [("end", "reminder_list"), ("end", "tasks_show")])
        self.assertEqual(self.tool_results(), ["Ergebnis reminder_list", "Ergebnis tasks_show"])
        self.assertIn("chat: gleichzeitig: 2 Werkzeuge", out.getvalue())

    def test_on_but_a_change_among_them_runs_alone(self):
        helpers.set_config(tools_parallel=True)
        self.ask('BOTH reminder_list {} || reminder_set {"text": "Tee", "minutes": 5}')
        self.assertEqual(self.log, [("start", "reminder_list"), ("end", "reminder_list"),
                                    ("start", "reminder_set"), ("end", "reminder_set")])

    def test_never_for_guests(self):
        helpers.keep_chat(self, "public")
        helpers.set_config(tools_parallel=True, public=True)
        guest = TestClient(panel.app)
        r = guest.post("/api/chat", json={"messages": [{"role": "user", "content": "BOTH reminder_list {} || tasks_show {}"}],
                                          "speak": False})
        self.assertEqual(r.status_code, 200, r.text)
        helpers.events(r)
        # a guest is offered no tool (chat_tools refuses each, here replaced); nothing starts together for a guest
        self.assertEqual(self.log, [("start", "reminder_list"), ("end", "reminder_list"),
                                    ("start", "tasks_show"), ("end", "tasks_show")])


def helpers_capture():
    """stdout of the panel while a block runs (the journal lines)."""
    import contextlib
    import io

    class Cap(contextlib.redirect_stdout):
        def __init__(self):
            self.buf = io.StringIO()
            super().__init__(self.buf)

        def __enter__(self):
            super().__enter__()
            return self.buf
    return Cap()


if __name__ == "__main__":
    unittest.main()
