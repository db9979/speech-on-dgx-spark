"""A faster start of the answer (thread "Schnellere Antwort", V01.0.302):

- "Schneller Antwortbeginn" (chat.prompt_cache): the system prompt and the tool list stay the same from turn to
  turn; what holds for one turn only (time, locks, fewer tools for this question, results of a yes) goes with the
  question, and the panel still runs only the tools the rules left (chat_tools.run). The kept conversation
  starts at an anchor question (chat.trim_history), so the LLM server can keep it in its cache.
- "Eindeutiges direkt abrufen" (chat.direct_read + profile direct_read): a short, plain reading question gets
  its tool called by the panel (intent.DIRECT), the model's first round is saved.
- Logs → Anfragen: the parts of each call in characters (chat.prompt_sizes).
No model, no clock.
"""
import json
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
import intent  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, **settings):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    if settings:
        c.put("/api/profile/settings", json=settings)
    return c


def ask(client, messages):
    r = client.post("/api/chat", json={"messages": messages})
    assert r.status_code == 200, r.text
    return helpers.events(r)


def streamed():
    return [c for c in helpers.LLM_CALLS if c.get("stream")]


def names(call):
    return [t["function"]["name"] for t in call.get("tools", [])]


def system_of(call):
    return next((m["content"] for m in call["messages"] if m["role"] == "system"), "")


def text_of(evs):
    return "".join(e.get("delta", "") for e in evs if e["type"] == "text")


class StableStart(unittest.TestCase):
    def setUp(self):
        helpers.set_config(prompt_cache=True, routing=True)
        helpers.LLM_CALLS.clear()

    def tearDown(self):
        helpers.set_config(prompt_cache=False, routing=False, direct_read=False, public=False)

    def test_same_start_for_different_questions(self):
        p = profile("Anfang1", route=True)
        ask(p, [{"role": "user", "content": "Erinnere mich in 10 Minuten an den Herd"}])
        a = streamed()[0]
        helpers.LLM_CALLS.clear()
        ask(p, [{"role": "user", "content": "Erzähl mir einen Witz"}])
        b = streamed()[0]
        self.assertEqual(system_of(a), system_of(b))
        self.assertEqual(names(a), names(b))                      # the same list, though the rules narrowed one
        self.assertIn("reminder_set", names(b))
        last = a["messages"][-1]["content"]
        self.assertIn(chat.TOOLS_NOW, last)                       # what is left for this question goes with it
        self.assertIn("reminder_set", last.split(chat.TOOLS_NOW, 1)[1])
        self.assertNotIn("history_search", last.split(chat.TOOLS_NOW, 1)[1])

    def test_panel_still_runs_only_what_the_rules_left(self):
        p = profile("Anfang2", route=True)
        evs = ask(p, [{"role": "user", "content": "TOOL history_search {} Erinnere mich in 10 Minuten an den Herd"}])
        self.assertIn("history_search", names(streamed()[0]))      # visible to the model ...
        self.assertIn("Not done: this tool is not available", text_of(evs))   # ... but not run

    def test_smalltalk_sees_the_list_but_calls_nothing(self):
        p = profile("Anfang3", route=True)
        ask(p, [{"role": "user", "content": "Hallo"}])
        call = streamed()[0]
        self.assertTrue(names(call))
        self.assertEqual(call.get("tool_choice"), "none")

    def test_lock_line_goes_with_the_question(self):
        p = profile("Anfang4", route=True)
        ask(p, [{"role": "user", "content": "Erzähl mir einen Witz"}])
        plain = system_of(streamed()[0])
        helpers.LLM_CALLS.clear()
        ask(p, [{"role": "user", "content": "Was steht auf der Seite?"},
                {"role": "assistant", "content": "Die Seite sagt etwas.", "outside": True},
                {"role": "user", "content": "Erinnere mich daran"}])
        call = streamed()[0]
        self.assertEqual(system_of(call), plain)
        self.assertIn("Gesperrt in dieser Antwort", call["messages"][-1]["content"])

    def test_off_everything_in_the_system_prompt(self):
        helpers.set_config(prompt_cache=False)
        p = profile("Anfang5", route=True)
        ask(p, [{"role": "user", "content": "Erinnere mich in 10 Minuten an den Herd"}])
        call = streamed()[0]
        self.assertEqual(set(names(call)), {"memory_save", "reminder_set", "reminder_list", "reminder_cancel"})
        self.assertEqual(call["messages"][-1]["content"], "Erinnere mich in 10 Minuten an den Herd")

    def test_notes_never_in_the_history(self):
        p = profile("Anfang6", route=True)
        ask(p, [{"role": "user", "content": "Erinnere mich in 10 Minuten an den Herd"}])
        log = json.dumps(p.get("/api/profile/toollog").json(), ensure_ascii=False)
        self.assertNotIn(chat.TOOLS_NOW, log)
        self.assertNotIn(chat.TIME_NOTE, log)


class Anchor(unittest.TestCase):
    def conversation(self, n):
        out = []
        for i in range(n):
            out += [{"role": "user", "content": f"Frage Nummer {i} mit etwas Text"},
                    {"role": "assistant", "content": f"Antwort Nummer {i} mit etwas mehr Text dazu"}]
        return out

    def test_the_start_stays_while_the_window_moves(self):
        conv = self.conversation(30)
        budget = 400   # about eight messages
        starts, plain = [], []
        for turn in range(10, 30):
            window = conv[:2 * turn + 1][-20:]                    # the browser sends the last 20
            starts.append(chat.trim_history(window, budget, anchor=True)[0]["content"])
            plain.append(chat.trim_history(window, budget)[0]["content"])
        self.assertEqual(len(set(plain)), len(plain))             # without: a new start every turn
        self.assertLess(len(set(starts)), len(starts) // 2)      # with: the same start for several turns
        for turn in range(10, 30):
            kept = chat.trim_history(conv[:2 * turn + 1][-20:], budget, anchor=True)
            self.assertEqual(kept[0]["role"], "user")
            self.assertLessEqual(sum(len(m["content"]) for m in kept), budget)
            self.assertEqual(kept[-1], conv[2 * turn])            # the question itself always stays

    def test_short_conversation_unchanged(self):
        conv = self.conversation(2)[:3]
        self.assertEqual(chat.trim_history(conv, 24000, anchor=True)[-1], conv[-1])


class Direct(unittest.TestCase):
    def setUp(self):
        helpers.set_config(direct_read=True, reminders=True)
        helpers.LLM_CALLS.clear()

    def tearDown(self):
        helpers.set_config(direct_read=False, public=False)

    def test_rules(self):
        offered = {"mail_list", "reminder_list", "weather", "parcels"}
        for text, want in (("Habe ich neue Mails?", "mail_list"), ("Hab ich ungelesene E-Mails", "mail_list"),
                           ("Welche Erinnerungen habe ich?", "reminder_list"), ("Wie ist das Wetter?", "weather"),
                           ("Wie wird das Wetter heute?", "weather"), ("Wo ist mein Paket?", "parcels"),
                           ("Wie wird das Wetter morgen?", None), ("Wie ist das Wetter in Berlin?", None),
                           ("Habe ich neue Mails von Tom?", None), ("Welche Erinnerungen habe ich morgen?", None),
                           ("Lösch alle Erinnerungen", None), ("Hallo", None)):
            self.assertEqual(intent.direct(text, offered), want, text)
        self.assertIsNone(intent.direct("Habe ich neue Mails?", {"weather"}))   # only what the turn offers
        self.assertIsNone(intent.direct("Wie ist das Wetter?" + " " * 100, offered))

    def test_panel_calls_the_tool_and_saves_a_round(self):
        p = profile("Direkt1", direct_read=True)
        evs = ask(p, [{"role": "user", "content": "Welche Erinnerungen habe ich?"}])
        calls = streamed()
        self.assertEqual(len(calls), 1)                            # only the answer round
        msgs = calls[0]["messages"]
        self.assertEqual(msgs[-2]["tool_calls"][0]["function"]["name"], "reminder_list")
        self.assertEqual(msgs[-1]["role"], "tool")
        self.assertTrue(text_of(evs).startswith("Ergebnis:"))

    def test_off_for_the_profile_or_the_spark(self):
        p = profile("Direkt2", direct_read=False)
        ask(p, [{"role": "user", "content": "Welche Erinnerungen habe ich?"}])
        self.assertEqual(streamed()[0]["messages"][-1]["role"], "user")
        self.assertFalse(p.get("/api/profile/settings").json()["allow"].get("direct_read") is None)
        helpers.set_config(direct_read=False)
        helpers.LLM_CALLS.clear()
        q = profile("Direkt3", direct_read=True)
        ask(q, [{"role": "user", "content": "Welche Erinnerungen habe ich?"}])
        self.assertEqual(streamed()[0]["messages"][-1]["role"], "user")

    def test_never_guests(self):
        helpers.set_config(public=True)
        g = TestClient(panel.app)
        ask(g, [{"role": "user", "content": "Welche Erinnerungen habe ich?"}])
        self.assertEqual(streamed()[0]["messages"][-1]["role"], "user")

    def test_admin_value_checked(self):
        cfg = ADMIN.get("/api/config").json()
        cfg["chat"]["direct_read"] = "ja"
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)


class Sizes(unittest.TestCase):
    def test_prompt_sizes(self):
        size = chat.prompt_sizes({"messages": [{"role": "system", "content": "abcd"}, {"role": "user", "content": "xy"}],
                                  "tools": [{"type": "function", "function": {"name": "a"}}]})
        self.assertEqual(size["system"], 4)
        self.assertEqual(size["history"], len('"xy"') + len('""'))
        self.assertEqual(size["tools"], len(json.dumps([{"type": "function", "function": {"name": "a"}}])))


if __name__ == "__main__":
    unittest.main()
