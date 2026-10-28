"""KI-Dungeon-Master: the Satz-Prüfstand (Dominik 2026-10-28 „es kommen zu viele fehler aktuell … mache mir vorschläge“,
Vorschlag 1, „ok“): every word list that sorts a typed action sorts every fixed sentence of tests/dungeon_saetze.py
as written there. A sentence a list got wrong at the table comes in with its fix; nothing here depends on the clock or
on the model.
"""
import contextlib
import io
import unittest

from tests import helpers  # noqa: F401,E402  (sets the paths like every test module)
with contextlib.redirect_stdout(io.StringIO()):
    import dungeon  # noqa: E402
from tests.dungeon_saetze import SAETZE  # noqa: E402

KAMPF = {"angriff": "angriff", "bezug": "bezug", "frieden": "frieden", "flucht": "flucht"}
GETIPPT = ("gehen", "kauf", "verkauf", "rast")


def sorted_as(text):
    """What every list says about one sentence."""
    return {"intent": dungeon.kampf.intent(text), "typed": dungeon.typed(text), "asks": dungeon.erz.asks(text),
            "everyday": dungeon.everyday(text)}


def wrong(art, got):
    """The parts of got that do not fit the kind art (the table in tests/dungeon_saetze.py), [] when it fits."""
    out = []
    if got["intent"] != KAMPF.get(art, ""):
        out.append(f"intent {got['intent']!r}")
    if art in GETIPPT and got["typed"] != art or art not in GETIPPT and art not in KAMPF and got["typed"]:
        out.append(f"typed {got['typed']!r}")
    if art == "frage" and not got["asks"]:
        out.append("asks False")
    if art == "alltag" and not got["everyday"] or art in ("sonst", "angriff", "bezug") and got["everyday"]:
        out.append(f"everyday {got['everyday']}")
    return out


class Saetze(unittest.TestCase):
    def test_kampf_angriffswoerter_tabelle(self):
        """Kampf-Audit 1: the fixed word lists decide what an action does in a fight; new words only through the table
        of tests/dungeon_saetze.py (it holds this test's sentences since 2026-10-28)."""
        for art, texts in SAETZE.items():
            for t in texts:
                self.assertEqual(dungeon.kampf.intent(t), KAMPF.get(art, ""), (art, t))

    def test_every_list_sorts_every_sentence(self):
        bad = [(art, t, wrong(art, sorted_as(t))) for art, texts in SAETZE.items() for t in texts
               if wrong(art, sorted_as(t))]
        self.assertEqual(bad, [])

    def test_the_table_is_sound(self):
        """No sentence twice, every kind known, enough sentences of each."""
        alle = [t for texts in SAETZE.values() for t in texts]
        self.assertEqual(len(alle), len(set(alle)))
        self.assertLessEqual(set(SAETZE), set(KAMPF) | set(GETIPPT) | {"frage", "alltag", "sonst"})
        for art, texts in SAETZE.items():
            self.assertGreaterEqual(len(texts), 2, art)


if __name__ == "__main__":
    unittest.main()
