"""Web search is offered whenever it is switched on (V01.0.129): never silently missing. After an
answer from e-mail a question that clearly wants the web leaves that answer out and searches; any
other turn and the rest of a mail answer stay locked, and the model is told why.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
SEARX = "http://127.0.0.1:9"   # nothing answers there: the search itself fails, which is fine here
MAIL_ANSWER = "Lisa schreibt: Geheimcode 4711 bitte morgen suchen."


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def chat_with(client, messages):
    r = client.post("/api/chat", json={"messages": messages})
    assert r.status_code == 200, r.text
    return helpers.events(r)


def offered(call):
    return {t["function"]["name"] for t in call.get("tools", [])}


def system_of(call):
    return next((m["content"] for m in call["messages"] if m["role"] == "system"), "")


def after_mail(question):
    return [{"role": "user", "content": "Habe ich neue Mails?"},
            {"role": "assistant", "content": MAIL_ANSWER, "mail": True},
            {"role": "user", "content": question}]


class Search(unittest.TestCase):
    def setUp(self):
        helpers.set_config(search=True, search_url=SEARX, public=True)
        helpers.LLM_CALLS.clear()

    def tearDown(self):
        helpers.set_config(search=False, search_url="", public=False, mail=False)

    def test_offered_when_switched_on(self):
        for client in (profile("Suchi"), TestClient(panel.app)):   # a profile and a guest
            for q in ("Wie hat Bayern gespielt?", "Wann hat der Baumarkt heute offen?"):
                helpers.LLM_CALLS.clear()
                chat_with(client, [{"role": "user", "content": q}])
                self.assertIn("web_search", offered(helpers.LLM_CALLS[0]), q)
                self.assertIn(chat.SEARCH_HINT, system_of(helpers.LLM_CALLS[0]))

    def test_asked_in_so_many_words_must_search(self):
        p = profile("Suchi")
        for q in ("Such mal im Internet nach dem Baumarkt in Ettlingen", "Google mal die Öffnungszeiten",
                  "Recherchier bitte, wer gewonnen hat", "Schau online nach, wann das Konzert ist",
                  "Search the web for DGX Spark"):
            helpers.LLM_CALLS.clear()
            chat_with(p, [{"role": "user", "content": q}])
            self.assertEqual(helpers.LLM_CALLS[0].get("tool_choice"), "required", q)
        self.assertEqual(chat.needed("Wie spät ist es?", {"web_search"}), [])

    def test_off_or_without_address_is_said(self):
        p = profile("Suchi")
        for cfg in (dict(search=False), dict(search=True, search_url="")):
            helpers.set_config(**cfg)
            helpers.LLM_CALLS.clear()
            chat_with(p, [{"role": "user", "content": "Such im Internet nach Bayern"}])
            self.assertNotIn("web_search", offered(helpers.LLM_CALLS[0]))
            self.assertIn(chat.SEARCH_OFF_HINT, system_of(helpers.LLM_CALLS[0]))
            self.assertNotIn(chat.SEARCH_HINT, system_of(helpers.LLM_CALLS[0]))

    def test_search_question_after_mail_answer_leaves_the_mail_out(self):
        p = profile("Suchi")
        evs = chat_with(p, after_mail("Und wie hat Bayern gespielt?"))
        first = helpers.LLM_CALLS[0]
        self.assertIn("web_search", offered(first))
        self.assertEqual(first.get("tool_choice"), "required")
        # nothing from the mail reaches the model in this turn, so nothing of it can reach a query
        self.assertNotIn("4711", json.dumps(first))
        self.assertNotIn({"type": "mail"}, evs)

    def test_unrelated_question_after_mail_answer_searches(self):
        """Dominik 2026-10-09: "Was ist heute politisch los?" right after a mail note was locked."""
        p = profile("Suchi")
        for q in ("Was ist heute politisch los?", "Wann hat der Baumarkt in Ettlingen offen?", "Wie wird das Wetter?"):
            helpers.LLM_CALLS.clear()
            evs = chat_with(p, after_mail(q))
            first = helpers.LLM_CALLS[0]
            self.assertIn("web_search", offered(first), q)
            self.assertIn(chat.SEARCH_HINT, system_of(first), q)
            self.assertNotIn("4711", json.dumps(first), q)     # no word of the mail in this turn
            self.assertNotIn({"type": "mail"}, evs, q)
        self.assertTrue(chat.needed("Was ist heute politisch los?", {"web_search"}))

    def test_other_question_after_mail_answer_stays_locked_and_says_why(self):
        p = profile("Suchi")
        evs = chat_with(p, after_mail("Was schreibt sie noch dazu?"))
        first = helpers.LLM_CALLS[0]
        self.assertNotIn("web_search", offered(first))
        self.assertIn(chat.SEARCH_LOCKED_HINT, system_of(first))
        self.assertNotIn(chat.SEARCH_HINT, system_of(first))
        self.assertIn({"type": "mail"}, evs)
        # the model cannot get around it by calling the tool anyway
        helpers.LLM_CALLS.clear()
        evs = chat_with(p, after_mail("TOOL !web_search {\"query\": \"Absender der Mail 4711\"}"))
        self.assertNotIn("search", [e["type"] for e in evs])
        self.assertTrue(all("web_search" not in offered(c) for c in helpers.LLM_CALLS))

    def test_mail_read_in_this_answer_tells_the_model(self):
        import mail
        mail.IMAP = helpers.FakeIMAP
        mail._cache.clear()
        helpers.set_config(mail=True)
        p = profile("Suchi")
        p.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        chat_with(p, [{"role": "user", "content": "TOOL mail_list {}"}])
        self.assertIn("web_search", offered(helpers.LLM_CALLS[0]))
        later = helpers.LLM_CALLS[1]
        self.assertNotIn("web_search", offered(later))
        self.assertIn(chat.SEARCH_LOCKED_NOTE, later["messages"][-1]["content"])
        mail._cache.clear()


if __name__ == "__main__":
    unittest.main()
