"""Gesperrte Dienste sofort ansagen (chat_turn.sperre, Dominik 2026-11-18: „du sagst, du guckst nach, und dann passiert
nichts“): when every Weiche group of a question is held off by the Notaus or its service is gone (Dienst-Wächter), the
panel says so at once in a fixed sentence (what is locked, try again later), without the model and without an instant
"Ich schau nach" before it; on every client, since it is the panel's fixed answer of /api/chat. A group that can still
do something leaves the turn to the model as before. No test depends on the time of day."""
import types
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat_turn  # noqa: E402
import dienstwacht  # noqa: E402
import intent  # noqa: E402
import kiwix  # noqa: E402
import notaus  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_notaus import off, profile  # noqa: E402

ASK = "Suche im Internet nach Rezepten für Lasagne"


def turn(names, offered, weg=(), held=0, uid="u_x", **kw):
    z = types.SimpleNamespace(who={"id": uid}, own_browser=True, mcp=False, pics=False, carry=None, room_far=False,
                              messages=[{"role": "user", "content": ASK}], route=intent.Route(list(names), {}),
                              intent=intent, offered_all=set(offered), notaus_weg=set(weg), held=held)
    z.__dict__.update(kw)
    return z


class Rules(unittest.TestCase):
    def test_the_route_must_name_the_group(self):
        self.assertTrue(intent.classify(ASK).names and "websuche" in intent.classify(ASK).names)

    def test_notaus_internet(self):
        s = chat_turn.sperre(turn(["websuche"], set(), weg={"web_search"}, held=1))
        self.assertEqual(s["art"], "gesperrt")
        self.assertIn("Internet ist gerade gesperrt", s["de"])
        self.assertIn("später noch einmal", s["de"])
        self.assertIn("try again later", s["en"])

    def test_actions_and_mein_notaus(self):
        tools = set(intent.GROUPS["erinnerung"][0])
        s = chat_turn.sperre(turn(["erinnerung"], set(), weg=tools, held=2))
        self.assertIn("Aktionen sind gerade gesperrt", s["de"])
        s = chat_turn.sperre(turn(["erinnerung"], set(), weg=tools, held=0))
        self.assertIn("Ich → Sicherheit", s["de"])

    def test_a_free_group_leaves_it_to_the_model(self):
        # one group still has its tool: the model answers (and says what the Notaus holds, notaus_note)
        self.assertIsNone(chat_turn.sperre(turn(["websuche", "kalender"], {"calendar_events"}, weg={"web_search"}, held=1)))
        self.assertIsNone(chat_turn.sperre(turn(["websuche"], {"web_search"})))
        self.assertIsNone(chat_turn.sperre(turn([], set(), weg={"web_search"}, held=1)))      # nothing recognised
        self.assertIsNone(chat_turn.sperre(turn(["websuche"], set())))      # only not offered: the model says why

    def test_never_guests_mcp_or_pictures(self):
        for kw in ({"who": None}, {"mcp": {"tools": []}}, {"pics": True}, {"own_browser": False}):
            self.assertIsNone(chat_turn.sperre(turn(["websuche"], set(), weg={"web_search"}, held=1, **kw)), kw)

    def test_service_gone(self):
        with mock.patch.object(dienstwacht, "tool_gone", lambda name, uid: name == "calendar_events"), \
                mock.patch.object(dienstwacht, "down_sentence",
                                  lambda name, uid, en=False: "gone-en" if en else "Kalender ist gerade nicht erreichbar."):
            s = chat_turn.sperre(turn(["kalender"], {"calendar_events"}))
            self.assertEqual((s["art"], s["de"], s["en"]), ("gesperrt", "Kalender ist gerade nicht erreichbar.", "gone-en"))
            # another tool of the group still works: free
            self.assertIsNone(chat_turn.sperre(turn(["kalender"], {"calendar_events", "daily_briefing"})))

    def test_web_search_with_the_own_archive_stays_free(self):
        with mock.patch.object(dienstwacht, "tool_gone", lambda name, uid: True), \
                mock.patch.object(kiwix, "web_fallback", lambda uid: True):
            self.assertIsNone(chat_turn.sperre(turn(["websuche"], {"web_search"})))


class InTheAnswer(unittest.TestCase):
    def setUp(self):
        off()
        helpers.keep_chat(self, "search", "search_url", "routing")
        # an address that is never asked here: the Notaus locks the search before it
        helpers.set_config(search=True, search_url="http://127.0.0.1:9", routing=True)
        helpers.LLM_CALLS.clear()

    def tearDown(self):
        off()

    def ask(self, c):
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": ASK}]})
        self.assertEqual(r.status_code, 200, r.text)
        return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")

    def test_notaus_said_at_once_without_the_model(self):
        c, _ = profile("Sperra")
        notaus.trigger(1, "Admin", "", "panel")
        said = self.ask(c)
        self.assertIn("Das Internet ist gerade gesperrt", said)
        self.assertEqual(helpers.LLM_CALLS, [])          # no model, no "Ich schau nach" and then nothing
        off()
        self.assertNotIn("gesperrt", self.ask(c))       # without the Notaus the question goes on as before

    def test_guests_get_no_fixed_lock_sentence(self):
        helpers.set_config(public=True)
        self.addCleanup(helpers.set_config, public=False)
        notaus.trigger(1, "Admin", "", "panel")
        r = TestClient(panel.app).post("/api/chat", json={"messages": [{"role": "user", "content": ASK}]})
        if r.status_code == 200:
            said = "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
            self.assertNotIn("Das Internet ist gerade gesperrt, der Notaus", said)


if __name__ == "__main__":
    unittest.main()
