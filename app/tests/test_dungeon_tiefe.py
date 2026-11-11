"""KI-Dungeon-Master: Regeltiefe statt 58 Schalter (dungeon_tiefe.py; plan „Dungeon-Schalter: 58 auf 8“, Ausdünnen
Punkt 1, Dominik 2026-11-11 „Ok“).

- One table: every part of the game in exactly one group (Kern, Voll, Pult or one of six own switches), each own
  switch a function in features.py below the Dungeon-Master; no module asks features with a part that has no switch.
- Kern and Pult work with the game itself, a Voll part only in a round at Regeltiefe „voll“; the admin sets the
  standard for new rounds, the host chooses per round (making it and in the Spielleiter-Pult), „Nur Narben“ is the
  round's choice.
- The old switches are taken over once at the start: „voll“ when at least half of the Voll parts were on, a new
  switch on when one of its old parts was, never the pictures; then the old keys are gone.
- Live counts the open rounds per Regeltiefe, only numbers. Nothing here depends on the clock.
"""
import contextlib
import glob
import io
import json
import os
import re
import tempfile
import unittest

from tests import helpers
from tests.test_dungeon import Base

import dungeon  # noqa: E402
import dungeon_tiefe as T  # noqa: E402
import features  # noqa: E402

PANEL = os.path.dirname(os.path.abspath(T.__file__))


class Table(unittest.TestCase):
    def test_every_part_in_one_group_and_every_switch_a_function(self):
        teile = list(T.KERN) + list(T.VOLL_TEILE) + list(T.PULT) + [t for ts in T.SCHALTER.values() for t in ts]
        self.assertEqual(len(teile), len(set(teile)))
        self.assertEqual(set(teile), set(T.GRUPPE))
        for sw in T.SCHALTER:
            f = features.BY_KEY[sw]
            self.assertEqual((f.parent, f.me), ("dungeon", "dmbox"), sw)
            self.assertNotIn("chat." + f.admin[0], features.DEFAULT_ON, sw)          # every own switch off from the start
        # features knows the game and its six switches, never a part without a switch of its own
        dm = {f.key for f in features.FEATURES if f.key == "dungeon" or f.parent == "dungeon"}
        self.assertEqual(dm, {"dungeon"} | set(T.SCHALTER))
        self.assertEqual({T.schalter(t) for t in T.KERN + T.VOLL_TEILE + T.PULT}, {"dungeon"})
        # every old switch is in the take-over, and no old key is shipped any more
        self.assertEqual(set(T.ALT) - set(T.GRUPPE), {"dungeonnarbennur"})
        with open(os.path.join(PANEL, "..", "config.default.json")) as f:
            chat = json.load(f)["chat"]
        self.assertEqual(chat[T.STANDARD], T.EINFACH)
        self.assertFalse(set(T.ALT.values()) & set(chat))
        self.assertEqual({k for k in chat if k.startswith("dungeon")},
                         {"dungeon", T.STANDARD} | {features.BY_KEY[sw].admin[0] for sw in T.SCHALTER})

    def test_no_module_asks_features_with_a_part(self):
        """Every module asks dungeon_tiefe (an, fuer, admin_an, fehlt): a part handed to features would be a switch
        nobody can set (KeyError, caught as off)."""
        teile = set(T.GRUPPE) - set(features.BY_KEY)
        call = re.compile(r"features\.(?:allowed|admin_on|missing_text|reason|profile_on)\(\s*(?:\"(dungeon\w+)\"|'(dungeon\w+)'|(\w+\.)?KEY\b)")
        bad = []
        for p in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
            with open(p, encoding="utf-8") as f:
                src = f.read()
            key = re.search(r'^KEY = "(dungeon\w+)"', src, re.M)
            for m in call.finditer(src):
                k = m.group(1) or m.group(2)
                if k is None and m.group(3) is None:
                    k = key.group(1) if key else None
                if k in teile:
                    bad.append((os.path.basename(p), k))
        self.assertEqual(bad, [])


class Rounds(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, T.STANDARD, "dungeon_bilder")
        helpers.set_config(dungeon_bilder=False, **{T.STANDARD: T.EINFACH})

    def test_kern_and_pult_with_the_game_voll_only_at_voll(self):
        rd = {"owner": self.uid}
        self.assertEqual(T.tiefe(rd), T.EINFACH)                                   # no choice: the admin's standard
        self.assertTrue(T.an("dungeongrenzen", rd) and T.an("dungeonorakel", rd))
        self.assertFalse(T.an("dungeonkrit", rd))
        self.assertFalse(T.an("dungeonwappen", rd))                                # its own switch is off
        self.assertTrue(T.fuer("dungeonkrit", self.uid))                           # every host may choose voll
        T.choose(rd, T.VOLL)
        self.assertTrue(T.an("dungeonkrit", rd))
        helpers.set_config(**{T.STANDARD: T.VOLL})
        self.assertEqual(T.tiefe({"owner": self.uid}), T.VOLL)                     # a round without a choice: the standard
        self.assertEqual(T.tiefe({"owner": self.uid, "tiefe": T.EINFACH}), T.EINFACH)   # the host's choice stays
        helpers.set_config(dungeon_bilder=True)
        self.assertTrue(T.an("dungeonwappen", rd))
        helpers.set_config(dungeon=False)                                          # the game off: nothing works
        self.assertFalse(any(T.an(t, rd) for t in T.GRUPPE))
        self.assertFalse(T.admin_an("dungeongrenzen"))
        self.assertIn("KI-Dungeon-Master", T.fehlt("dungeonkrit", self.uid))
        self.assertFalse(T.an("dungeonkrit", {"tiefe": T.VOLL}))                   # never without a host
        for v in ("", "VOLL", None, 1, "tief"):
            with self.assertRaises(ValueError):
                T.choose(rd, v)
        helpers.set_config(**{T.STANDARD: "tief"})
        self.assertEqual(T.standard(), T.EINFACH)                                  # an unknown standard: einfach

    def test_nur_narben_view_and_live_counts(self):
        rd = {"owner": self.uid, "tiefe": T.VOLL}
        self.assertFalse(T.nur_narben(rd))
        rd["nur_narben"] = "ja"
        self.assertFalse(T.nur_narben(rd))                                         # only a real true
        rd["nur_narben"] = True
        self.assertTrue(T.nur_narben(rd))
        self.assertEqual(T.view(rd, False, 0), {"wert": "voll", "name": "Voll"})  # a player sees the depth only
        self.assertEqual(T.view(rd, True, 1), {"wert": "voll", "name": "Full", "nur_narben": True,
                                               "wahl": [["einfach", "Simple"], ["voll", "Full"]]})
        runden = [rd, {"tiefe": T.EINFACH}, {"tiefe": T.VOLL, "status": "ende", "nur_narben": True}, {}]
        self.assertEqual(T.counts(runden), {"einfach": 2, "voll": 1, "nur_narben": 1})


class Uebernahme(unittest.TestCase):
    def write(self, chat):
        fd, p = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(os.remove, p)
        with open(p, "w") as f:
            json.dump({"chat": chat, "andere": {"x": 1}}, f)
        return p

    def take(self, chat):
        p = self.write(chat)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            n = T.uebernehmen(p)
        with open(p) as f:
            return n, json.load(f), out.getvalue()

    def test_half_of_voll_on_makes_voll_and_the_old_keys_go(self):
        half = T.VOLL_TEILE[:(len(T.VOLL_TEILE) + 1) // 2]
        chat = {T.ALT[t]: True for t in half}
        chat.update({T.ALT[t]: False for t in T.VOLL_TEILE if t not in half})
        chat.update(dungeon_richter=True, dungeon_chronik=False, dungeon_gesicht=True, dungeon_import=True,
                    dungeon_narben_nur=True, dungeon=True, mail=True)
        n, cfg, out = self.take(chat)
        ch = cfg["chat"]
        self.assertEqual(n, len(T.VOLL_TEILE) + 5)
        self.assertEqual(ch[T.STANDARD], T.VOLL)
        self.assertIs(ch["dungeon_pruefung"], True)                    # richter was on
        self.assertIs(ch["dungeon_geschichten"], True)                 # import was on
        self.assertNotIn("dungeon_buecher", ch)                        # chronik was off: the default (off)
        self.assertNotIn("dungeon_bilder", ch)                         # never the pictures by themselves
        self.assertFalse(set(T.ALT.values()) & set(ch))
        self.assertEqual((ch["dungeon"], ch["mail"], cfg["andere"]), (True, True, {"x": 1}))   # the rest stays
        self.assertIn(f"dungeon: regeltiefe | uebernommen | voll | {n}", out)
        self.assertEqual(self.take(ch)[0], 0)                          # once: nothing more to take over

    def test_less_than_half_stays_einfach_and_nothing_to_do(self):
        few = T.VOLL_TEILE[:len(T.VOLL_TEILE) // 2 - 1]
        n, cfg, _ = self.take({T.ALT[t]: True for t in few})
        self.assertEqual((n, cfg["chat"][T.STANDARD]), (len(few), T.EINFACH))
        n, cfg, _ = self.take({T.ALT["dungeonkrit"]: True, T.STANDARD: T.VOLL})
        self.assertEqual(cfg["chat"][T.STANDARD], T.VOLL)               # an admin's standard stays
        self.assertEqual(self.take({"dungeon": True})[0], 0)            # no old key: the file is not written
        p = self.write({})
        with open(p, "w") as f:
            f.write("{kaputt")
        self.assertEqual(T.uebernehmen(p), 0)                           # a broken file: nothing, never a raise


class Endpoint(Base):
    def test_the_host_chooses_the_depth_and_nur_narben(self):
        helpers.keep_chat(self, T.STANDARD)
        helpers.set_config(**{T.STANDARD: T.VOLL})
        rid = self.new_round(tiefe="voll")["rid"]
        self.assertNotIn("tiefe", self.state(rid))                                 # the standard: follows the admin's
        self.assertEqual(T.tiefe(self.state(rid)), T.VOLL)
        rid2 = self.new_round(tiefe="einfach")["rid"]
        self.assertEqual(self.state(rid2)["tiefe"], T.EINFACH)                     # the host's own choice stays
        for bad in ("tief", ["einfach"], None, 3):
            rd = {}
            T.neu(rd, bad)
            self.assertEqual(rd, {})                                               # anything else: the standard
        url = f"/api/profile/dungeon/{rid}/erzaehler"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.c.post(url, json={"tiefe": "einfach"}).status_code, 200)
            self.assertEqual(self.c.post(url, json={"nur_narben": True}).status_code, 200)
        self.assertIn("dungeon: regeltiefe | einfach", out.getvalue())
        self.assertIn("dungeon: narbe | nur aussehen an", out.getvalue())
        rd = self.state(rid)
        self.assertEqual((rd["tiefe"], rd["nur_narben"]), (T.EINFACH, True))
        for bad in ({"tiefe": "tief"}, {"tiefe": ["voll"]}, {"nur_narben": "ja"}):
            self.assertEqual(self.c.post(url, json=bad).status_code, 400, bad)
        self.assertEqual(self.state(rid)["tiefe"], T.EINFACH)
        v = self.c.get(f"/api/profile/dungeon/{rid}").json()["tiefe"]
        self.assertEqual((v["wert"], v["nur_narben"], [k for k, _ in v["wahl"]]), ("einfach", True, ["einfach", "voll"]))
        # another profile never chooses
        self.assertIn(self.c2.post(url, json={"tiefe": "voll"}).status_code, (403, 404))
        self.assertEqual(self.state(rid)["tiefe"], T.EINFACH)
        live = dungeon.for_live()
        self.assertEqual((live["tiefe_einfach"], live["tiefe_voll"], live["tiefe_nur_narben"]), (2, 0, 1))
        snap = json.dumps(__import__("live").snapshot(), ensure_ascii=False)
        self.assertIn("Regeltiefe: 2 einfach, 0 voll, 1 nur Narben", snap)


if __name__ == "__main__":
    unittest.main()
