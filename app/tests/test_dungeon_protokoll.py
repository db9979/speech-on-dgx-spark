"""KI-Dungeon-Master: Protokoll-Prüfer (Dominik 2026-10-28 „es kommen zu viele fehler aktuell … mache mir vorschläge“,
Vorschlag 5, „ok“): every round copied from the page and kept in tests/dungeon_protokolle/ gives exactly the findings
of its header; the fixed checks run once more over the narration the panel keeps and over the round's names.
Nothing here depends on the clock or on the model.
"""
import contextlib
import glob
import io
import os
import re
import sys
import unittest
from unittest import mock

from tests import helpers  # noqa: F401,E402  (sets the paths like every test module)
with contextlib.redirect_stdout(io.StringIO()):
    import dungeon  # noqa: E402
    import dungeon_protokoll as P  # noqa: E402

FAELLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dungeon_protokolle")


def main(argv):
    """cd app && python3 -m tests.test_dungeon_protokoll copy.txt [--fall name] [--en]: the findings of a round copied
    from the page; --fall keeps it in tests/dungeon_protokolle/ as a case with them as its header."""
    with open(argv[0], encoding="utf-8") as f:
        text = f.read()
    with contextlib.redirect_stdout(io.StringIO()):
        found = P.text_faults(dungeon, P.read(text), "en" if "--en" in argv else "de")
    line = "# befunde:" + ",".join(f" {k} {'-' if z is None else z}" for k, z in found)
    print(line)
    if "--fall" in argv:
        name = re.sub(r"[^a-z0-9_]", "_", argv[argv.index("--fall") + 1].lower())
        os.makedirs(FAELLE, exist_ok=True)
        with open(os.path.join(FAELLE, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(line + "\n" + ("# lang: en\n" if "--en" in argv else "")
                    + "".join(x + "\n" for x in text.split("\n") if not x.startswith("# ")))
        print("written", name)


class Protokoll(unittest.TestCase):
    def test_every_kept_round_gives_its_findings(self):
        files = sorted(glob.glob(os.path.join(FAELLE, "*.txt")))
        self.assertTrue(files)
        for f in files:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
            want = P.header(text)
            self.assertIsNotNone(want, f"{os.path.basename(f)}: no line „# befunde:“")
            with contextlib.redirect_stdout(io.StringIO()):
                got = P.text_faults(dungeon, P.read(text), "en" if "\n# lang: en" in text else "de")
            self.assertEqual(got, want, os.path.basename(f))
            self.assertLessEqual({k for k, _ in got}, set(P.ARTEN))

    def test_the_library_round_shows_each_of_its_faults(self):
        """Dominik's points 1 to 9 of 2026-10-28, each found by its own rule in the copy he sent."""
        with open(os.path.join(FAELLE, "alte_bibliothek.txt"), encoding="utf-8") as f:
            turns = P.read(f.read())
        self.assertEqual([t["zug"] for t in turns], [None] + list(range(4, 14)))
        self.assertEqual(turns[1]["aktionen"], [("Gandalf", "betrete die biblithek")])
        self.assertIn("Das Panel bestätigt", turns[6]["erzaehlung"])
        with contextlib.redirect_stdout(io.StringIO()):
            got = {k for k, _ in P.text_faults(dungeon, turns)}
        self.assertEqual(got, set(P.ARTEN))

    def test_the_kept_narration_and_the_names_of_the_round(self):
        with mock.patch.object(dungeon.erz, "faults", lambda *a: [("gegner", ["Wolf"]), ("knapp", []), ("gegner", ["Bär"])]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            before = P.for_live()
            self.assertEqual(P.rest(dungeon, {}, {"text": "x"}), ["gegner", "knapp", "gegner"])
        self.assertIn("dungeon: protokoll | rest | gegner knapp\n", out.getvalue())
        with mock.patch.object(dungeon.erz, "faults", lambda *a: []), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(P.rest(dungeon, {}, {"text": "x"}), [])
        self.assertIn("dungeon: protokoll | ok\n", out.getvalue())
        rd = {"kampf": {"gegner": [{"name": "keine 1"}, {"name": "Schattenwächter 2"}]},
              "nsc": {"s": {"name": "Schattenwächter"}, "x": {"name": "Silas"}}, "wahrheit": {"personen": [{"name": "Niemand"}]}}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(P.runde(dungeon, rd), [("platzhalter", 2), ("person_gegner", 1)])
            self.assertEqual(P.runde(dungeon, {"nsc": {"x": {"name": "Silas"}}}), [])
        self.assertIn("dungeon: protokoll | platzhalter | 2", out.getvalue())
        now = P.for_live()
        self.assertEqual((now["protokoll_geprueft"] - before["protokoll_geprueft"], now["protokoll_rest"] - before["protokoll_rest"],
                          now["protokoll_namen"] - before["protokoll_namen"]), (2, 1, 3))

    def test_a_copy_becomes_a_case(self):
        """„python3 -m tests.test_dungeon_protokoll copy.txt --fall name“ writes the case with its findings as header."""
        import tempfile
        with tempfile.TemporaryDirectory() as d, open(os.path.join(FAELLE, "alte_bibliothek.txt"), encoding="utf-8") as f:
            src = os.path.join(d, "kopie.txt")
            with open(src, "w", encoding="utf-8") as g:
                g.write("".join(x + "\n" for x in f.read().split("\n") if not x.startswith("# ")))
            with mock.patch(f"{__name__}.FAELLE", d), contextlib.redirect_stdout(io.StringIO()) as out:
                main([src, "--fall", "Neue Runde"])
            with open(os.path.join(d, "neue_runde.txt"), encoding="utf-8") as g:
                case = g.read()
        self.assertIn("written neue_runde", out.getvalue())
        self.assertTrue(case.startswith("# befunde: stufe 4, haendler 4"))


if __name__ == "__main__":
    if sys.argv[1:] and not sys.argv[1].startswith("-"):
        main(sys.argv[1:])
    else:
        unittest.main()
