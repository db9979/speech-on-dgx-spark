"""KI-Dungeon-Master: the Satz-Prüfstand (Dominik 2026-10-28 „es kommen zu viele fehler aktuell … mache mir vorschläge“,
Vorschlag 1 and 7, „ok“): the one sorting of a typed action (dungeon_einordnung.kind) gives every fixed sentence of
tests/dungeon_saetze.py exactly its kind, and each helper the game asks (fight, asks, typed, everyday) says the same.
A sentence sorted wrong at the table comes in with its fix; nothing here depends on the clock or on the model.
"""
import contextlib
import io
import unittest

from tests import helpers  # noqa: F401,E402  (sets the paths like every test module)
with contextlib.redirect_stdout(io.StringIO()):
    import dungeon_einordnung as E  # noqa: E402
from tests.dungeon_saetze import SAETZE  # noqa: E402


def want(art):
    return "" if art == "sonst" else art


class Saetze(unittest.TestCase):
    def test_kampf_angriffswoerter_tabelle(self):
        """Kampf-Audit 1: the fixed word lists decide what an action does in a fight; new words only through the table
        of tests/dungeon_saetze.py (it holds this test's sentences since 2026-10-28)."""
        for art, texts in SAETZE.items():
            for t in texts:
                self.assertEqual(E.fight(t), want(art) if art in E.KAMPF else "", (art, t))

    def test_every_sentence_has_its_one_kind(self):
        bad = [(art, t, E.kind(t)) for art, texts in SAETZE.items() for t in texts if E.kind(t) != want(art)]
        self.assertEqual(bad, [])

    def test_every_helper_says_what_the_kind_says(self):
        """No list says something of a sentence its kind does not: typed only for GETIPPT, everyday only for alltag,
        asks for frage and for peace in words of talking only."""
        for art, texts in SAETZE.items():
            for t in texts:
                self.assertEqual(E.typed(t), want(art) if art in E.GETIPPT else "", (art, t))
                self.assertEqual(E.everyday(t), art == "alltag", (art, t))
                if art == "frage":
                    self.assertTrue(E.asks(t), t)
                elif art != "frieden":
                    self.assertFalse(E.asks(t), (art, t))
        self.assertTrue(E.asks("Lasst uns verhandeln"))     # asking for peace talks too
        self.assertFalse(E.asks("Wir ergeben uns"))         # without a word of talking it only asks for peace
        self.assertEqual(E.kind(""), "")

    def test_the_table_is_sound(self):
        """No sentence twice, every kind known, enough sentences of each, every kind of the order in the table."""
        alle = [t for texts in SAETZE.values() for t in texts]
        self.assertEqual(len(alle), len(set(alle)))
        self.assertEqual(set(SAETZE), set(E.ARTEN) | {"sonst"})
        self.assertLessEqual(set(E.KAMPF) | set(E.GETIPPT), set(E.ARTEN))
        for art, texts in SAETZE.items():
            self.assertGreaterEqual(len(texts), 2, art)

    def test_the_values_of_a_check_by_the_words(self):
        """One table for the value of a check by the player's words (dungeon.fitting_value and the hints of
        dungeon_anleiten): its order decides, an action without such a word names none."""
        self.assertEqual(E.values("Ich klettere hinauf und lausche"), ["geschick", "weisheit"])
        self.assertEqual(E.values("I read the letter"), ["intelligenz"])
        self.assertEqual(E.values("Ich warte"), [])


if __name__ == "__main__":
    unittest.main()
