"""Guests only ask and get answers (Dominik 2026-10-13, plan plaene/freigabe-vereinfachen.md): without a profile the
language model answers from its own knowledge, with no tool at all. No web search, no timers, no briefing, no memory,
no history, no smart home. The same holds for the admin's browser without a profile of its own. Fixed rule, no switch.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
import features  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
EVERYTHING = dict(search=True, search_url="http://127.0.0.1:9", reminders=True, calendar=True, memory=True,
                  history=True, documents=True, weather=True, homeassistant=True, public=True)


def ask(client, text, **body):
    helpers.LLM_CALLS.clear()
    r = client.post("/api/chat", json=dict({"messages": [{"role": "user", "content": text}]}, **body))
    assert r.status_code == 200, r.text
    helpers.events(r)
    return helpers.LLM_CALLS[0]


def offered(call):
    return {t["function"]["name"] for t in call.get("tools", [])}


def system_of(call):
    return next((m["content"] for m in call["messages"] if m["role"] == "system"), "")


class GuestsOnlyAnswer(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            self.before = json.load(f)
        helpers.set_config(**EVERYTHING)

    def tearDown(self):   # exactly what was there before (other tests rely on Home Assistant staying on)
        helpers.write_config(self.before)

    def test_no_tool_for_a_guest(self):
        for q in ("Wie hat Bayern gespielt?", "Erinnere mich in 10 Minuten an den Tee", "Guten Morgen, was steht heute an?",
                  "Wie wird das Wetter morgen?", "Was weißt du über mich?"):
            call = ask(TestClient(panel.app), q)
            self.assertEqual(offered(call), set(), q)
            self.assertNotIn("tool_choice", call, q)
            self.assertIn(chat.GUEST_HINT, system_of(call), q)
            for hint in (chat.SEARCH_HINT, chat.REMINDER_HINT):
                self.assertNotIn(hint, system_of(call), q)

    def test_reminders_a_browser_sends_along_are_not_read(self):
        call = ask(TestClient(panel.app), "Welche Timer laufen?",
                   reminders=[{"id": "abcd", "text": "Geheimer Tee", "due": 4102444800000}])
        self.assertNotIn("Geheimer Tee", str(call["messages"]))
        self.assertEqual(offered(call), set())

    def test_admin_without_profile_is_a_guest_too(self):
        call = ask(ADMIN, "Wie hat Bayern gespielt?")
        self.assertEqual(offered(call), set())

    def test_a_profile_still_gets_its_tools(self):
        uid = ADMIN.post("/api/admin/profiles", json={"name": "Gaby", "pin": "1234"}).json()["id"]
        self.addCleanup(ADMIN.delete, f"/api/admin/profiles/{uid}")
        p = TestClient(panel.app)
        self.assertEqual(p.post("/api/profile/login", json={"name": "Gaby", "pin": "1234"}).status_code, 200)
        call = ask(p, "Wie hat Bayern gespielt?")
        self.assertIn("web_search", offered(call))
        self.assertNotIn(chat.GUEST_HINT, system_of(call))

    def test_no_function_is_ever_allowed_for_guests(self):
        for f in features.FEATURES:
            self.assertEqual(features.reason(f.key, None) in ("spark", "guest"), True, f.key)
            self.assertFalse(features.allowed(f.key, None), f.key)
        self.assertEqual(features.state(None), [])
        self.assertEqual(features.guests(), {"public": True})


if __name__ == "__main__":
    unittest.main()
