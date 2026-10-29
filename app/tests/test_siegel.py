"""Profildaten nur über einen Weg (plan nutzerwissen, Stufe 4): memory, conversations and what the Spark learned about a
person are read and written only through profiles.read_own / write_own / drop_own, never with open() or
profiles._write on their path, so they can be sealed at rest in one place. Times are never read."""
import ast
import os
import stat
import tempfile
import unittest

from tests import helpers

helpers.start()
import profiles  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
HELPERS = {"read_own", "write_own", "drop_own"}
# moved to the helpers ahead of their seal (V01.1.250): siegel= in dateien.py follows in V01.1.251 and V01.1.252
VORAB = {"memory.json", "convos.json", "toollog.json", "room-history.json", "interessen.json", "tagebuch.json",
         "zuordnungen.json", "learned.json", "memory-ask.json"}


def own_files():
    return set(VORAB)


def direct_uses(names, folder=PANEL):
    """(file, line, name) of every string constant naming one of names outside a call of the helpers."""
    out = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".py") or fn == "dateien.py":
            continue
        with open(os.path.join(folder, fn), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        ok = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and ast.unparse(n.func).split(".")[-1] in HELPERS:
                ok.update(id(a) for a in n.args[1:2])
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
                ok.add(id(n.value))          # a docstring
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and n.value in names and id(n) not in ok:
                out.append((fn, n.lineno, n.value))
    return out


class OnlyThroughTheHelpers(unittest.TestCase):
    def test_no_module_opens_an_own_file_itself(self):
        self.assertEqual(direct_uses(own_files()), [],
                         "read or write this file through profiles.read_own / write_own / drop_own (plan nutzerwissen, Stufe 4)")

    def test_the_scan_finds_a_direct_open(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x.py"), "w") as f:
                f.write('"""memory.json in a docstring is fine."""\nimport profiles\n'
                        'a = profiles.read_own(uid, "memory.json", [])\n'
                        'with open(profiles._path(uid, "memory.json")) as f:\n    pass\n')
            self.assertEqual(direct_uses({"memory.json"}, d), [("x.py", 4, "memory.json")])


class Helpers(unittest.TestCase):
    UID = "u_5e9e1000aa01"

    def setUp(self):
        os.makedirs(profiles._path(self.UID), exist_ok=True)
        self.addCleanup(profiles.drop_own, self.UID, "memory.json")

    def test_round_trip_only_for_the_service_user(self):
        profiles.write_own(self.UID, "memory.json", [{"id": "x1", "text": "Ein Satz mit ä."}])
        self.assertEqual(profiles.read_own(self.UID, "memory.json", []), [{"id": "x1", "text": "Ein Satz mit ä."}])
        self.assertEqual(stat.S_IMODE(os.stat(profiles._path(self.UID, "memory.json")).st_mode), 0o600)

    def test_missing_or_broken_gives_the_default(self):
        self.assertEqual(profiles.read_own(self.UID, "memory.json", []), [])
        with open(profiles._path(self.UID, "memory.json"), "w") as f:
            f.write("[{")
        self.assertEqual(profiles.read_own(self.UID, "memory.json", {"d": 1}), {"d": 1})

    def test_drop(self):
        profiles.write_own(self.UID, "memory.json", [])
        self.assertTrue(profiles.drop_own(self.UID, "memory.json"))
        self.assertFalse(profiles.drop_own(self.UID, "memory.json"))


if __name__ == "__main__":
    unittest.main()
