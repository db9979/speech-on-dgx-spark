"""Ausleiten verhindern (ausleiten.py, Kritische Prüfung 2026-11-12 point 1): after outside text in an answer, a tool
that goes to the internet runs only with the person's own words or words a search of the same answer brought in, so a
calendar invitation cannot make the model put the memory, an appointment or an IBAN into a search word. The background
jobs use the same rule (agent._carries_out, checked in test_pruefung).

No test depends on the time of day.
"""
import asyncio
import contextlib
import io
import types
import unittest

from tests import helpers

helpers.start()
import ausleiten  # noqa: E402
import chat  # noqa: E402
import chat_tools  # noqa: E402
import notaus  # noqa: E402


def turn(ask):
    return types.SimpleNamespace(
        who=None, ex={"run": {}, "mail": set(), "outside": set(), "changes": set(), "own": set()},
        locked=lambda s: chat.LOCKED_OUTSIDE if s["outside"] else set(), body={}, own_browser=True, src="test",
        private_ok=True, hilfe_page=None, hilfe_admin=None, out=None, hilfe_origin=None, hilfe_app=None,
        hilfe_focus=None, ask_text=ask, request=None, search=False, web_own="", local_task=None, mailbox=None,
        drafts_on=False, ha=None, timers=None)


class Words(unittest.TestCase):
    def test_own_words_pass_others_do_not(self):
        self.assertEqual(ausleiten.fremd({"query": "Wetter Hamburg"}, "Wie wird das Wetter in Hamburg?"), [])
        self.assertEqual(ausleiten.fremd({"query": "Termine Zahnarzt"}, "zeig meine Termine"), ["zahnarzt"])
        # numbers are words: an IBAN or a phone number never passes
        self.assertEqual(ausleiten.fremd({"query": "DE12 3456 7890"}, "such das"), ["3456", "7890", "de12"])
        # any nesting of the arguments is read
        self.assertEqual(ausleiten.fremd({"a": {"b": ["Geheimnis"]}, "n": 4711}, ""), ["4711", "geheimnis"])
        self.assertEqual(ausleiten.fremd({}, ""), [])

    def test_pool_keeps_public_results_with_a_limit(self):
        st = {}
        ausleiten.pool_dazu(st, "Ergebnis: Hamburger Hafen")
        self.assertIn("Hafen", st["oeffentlich"])
        ausleiten.pool_dazu(st, "x" * (ausleiten.MAX_POOL * 2))
        self.assertLessEqual(len(st["oeffentlich"]), ausleiten.MAX_POOL)


class Chat(unittest.TestCase):
    def st(self, outside):
        return {"offered": set(notaus.INTERNET_TOOLS), "mail": False, "outside": outside}

    def test_after_outside_text_a_foreign_word_never_goes_out(self):
        for name in sorted(notaus.INTERNET_TOOLS):
            st = self.st(True)
            r = asyncio.run(chat_tools.run(turn("Was steht heute in meinem Kalender?"), name,
                                           {"query": "Zahnarzt Dr. Weber 0171 2345678", "place": "Zahnarzt"}, st))
            self.assertEqual(r, ausleiten.HINWEIS, name)

    def test_own_words_and_public_results_stay_allowed(self):
        t = turn("Such im Internet nach Wärmepumpen")
        st = self.st(True)
        r = asyncio.run(chat_tools.run(t, "web_search", {"query": "Wärmepumpen"}, st))
        self.assertNotEqual(r, ausleiten.HINWEIS)
        ausleiten.pool_dazu(st, "Förderung für Wärmepumpen bei der BAFA")
        r = asyncio.run(chat_tools.run(t, "web_search", {"query": "BAFA Förderung"}, st))
        self.assertNotEqual(r, ausleiten.HINWEIS)

    def test_before_outside_text_nothing_is_held(self):
        r = asyncio.run(chat_tools.run(turn("Wie wird das Wetter?"), "web_search", {"query": "Zahnarzt Weber"},
                                       self.st(False)))
        self.assertNotEqual(r, ausleiten.HINWEIS)

    def test_a_refusal_writes_a_log_line_without_the_words(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            asyncio.run(chat_tools.run(turn("Kalender?"), "web_search", {"query": "Geheimwort"}, self.st(True)))
        self.assertIn("ausleiten: gesperrt web_search 1", out.getvalue())
        self.assertNotIn("Geheimwort", out.getvalue())


if __name__ == "__main__":
    unittest.main()
