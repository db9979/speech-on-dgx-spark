"""Der Dungeon-Master als eigenes Paket (Kritische Prüfung 2026-11-12 point 7): the game (69 modules dungeon*.py) is
reached from the rest of the panel only through few doors, and the doors only get fewer. On V01.1.399 live.py went
from 43 game imports to dungeon_live.for_live(); TUEREN below is what is left (a ratchet like test_aufraeumen: a new
door is red, a door that closed must be taken out).

Reads only app/panel, so it runs in the app/-only copy too. No wall clock dependence.
"""
import ast
import glob
import os
import unittest

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
# module outside the game -> the game modules it may import (only shrinks)
TUEREN = {
    "admin": {"dungeon_auto", "dungeon_tiefe"},
    "live": {"dungeon_erzaehlstand", "dungeon_gast", "dungeon_import", "dungeon_live", "dungeon_pruefstand"},
    "panel": {"dungeon", "dungeon_buch", "dungeon_chronik", "dungeon_dingbild", "dungeon_echt", "dungeon_erzaehlstand",
              "dungeon_fluestern", "dungeon_geschichten", "dungeon_gesicht", "dungeon_import", "dungeon_karte",
              "dungeon_knapp", "dungeon_lied", "dungeon_musik", "dungeon_pruefstand", "dungeon_rast",
              "dungeon_regelseite", "dungeon_tiefe", "dungeon_wappen", "dungeon_wunsch"},
    "rmplus": {"dungeon_buch"},
}


def doors():
    files = {os.path.basename(p)[:-3]: p for p in glob.glob(os.path.join(PANEL, "*.py"))}
    out = {}
    for mod, path in files.items():
        if mod.startswith("dungeon"):
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                if name in files and name.startswith("dungeon"):
                    out.setdefault(mod, set()).add(name)
    return out


class Grenze(unittest.TestCase):
    def test_no_new_door_into_the_game(self):
        now = doors()
        new = {m: sorted(d - TUEREN.get(m, set())) for m, d in now.items() if d - TUEREN.get(m, set())}
        self.assertEqual(new, {}, "a new import of a game module from outside: go through dungeon_live (Live) or an "
                                  "existing door")
        closed = {m: sorted(d - now.get(m, set())) for m, d in TUEREN.items() if d - now.get(m, set())}
        self.assertEqual(closed, {}, "these doors are closed now: take them out of TUEREN")


if __name__ == "__main__":
    unittest.main()
