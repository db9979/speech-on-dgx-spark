"""KI-Dungeon-Master: small gestures while the table is idle (LlamaTale idea 7, dungeon_warten.geste_faellig/geste,
the person and its line from the main thread's dungeon_nsc.geste; Dominik 2026-10-27 „1-7“).

- Only with the switch dungeongesten (on top of „NSC-Gedächtnis und Chronik“), only while the turn is open and nobody
  did anything at the table for GESTE_S (no action, no table talk, no gesture), never in a fight, a pause, while the
  Dungeon Master answers; at most GESTE_ZUG a turn.
- Never while a seat plays from the car (dungeon_auto.im_auto): nothing in the feed then.
- A gesture is a log line of art "geste" and changes nothing else in the round; maybe_close asks on every request.
- Live and the journal: numbers and fixed words only.

No wall clock in the checks: every time is given.
"""
import contextlib
import io
import unittest

from tests import helpers
from tests.test_dungeon import Base

import dungeon  # noqa: E402
import dungeon_auto  # noqa: E402
import dungeon_warten as warten  # noqa: E402


class Gestures(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_nsc", "dungeon_gesten")
        helpers.set_config(dungeon_nsc=True, dungeon_gesten=True)
        self.rid = self.new_round()["rid"]
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][self.rid]
            rd["nsc"] = {"oskar": {"name": "Oskar", "karte": {}, "kanten": [], "haltung": {}, "gesehen": rd["zug"],
                                   "wesen": {"freundlich": 3}, "ziele": []}}
            rd["log"].append({"art": "dm", "text": "Oskar steht am Tresen.", "npc": [], "n": rd["zug"]})
            rd["zug_t"] = 1000.0
            dungeon._write(d)
        old = getattr(dungeon_auto, "im_auto")
        self.addCleanup(setattr, dungeon_auto, "im_auto", old)
        dungeon_auto.im_auto = lambda uid, now=None: False

    def gestures(self):
        return [e for e in self.state(self.rid)["log"] if e["art"] == "geste"]

    def test_due_only_when_the_table_is_idle(self):
        rd = self.state(self.rid)
        t = 1000.0 + warten.GESTE_S
        self.assertFalse(warten.geste_faellig(rd, t - 1))
        self.assertTrue(warten.geste_faellig(rd, t))
        for k, v in (("kampf", {"gegner": []}), ("pause", True), ("dm", "denkt"), ("echt_frage", {"zug": 1}), ("status", "ende")):
            self.assertFalse(warten.geste_faellig(dict(rd, **{k: v}), t), k)
        self.assertFalse(warten.geste_faellig(dict(rd, offen={"p": {"text": "x", "t": t - 5}}), t))        # an action just now
        self.assertFalse(warten.geste_faellig(dict(rd, tisch=[{"n": 1, "text": "x", "t": t - 5}]), t))   # table talk just now
        self.assertFalse(warten.geste_faellig(dict(rd, geste={"zug": rd["zug"], "n": warten.GESTE_ZUG, "t": 0}), t))
        self.assertTrue(warten.geste_faellig(dict(rd, geste={"zug": rd["zug"] - 1, "n": warten.GESTE_ZUG, "t": 0}), t))  # a new turn
        helpers.set_config(dungeon_gesten=False)
        self.assertFalse(warten.geste_faellig(rd, t))

    def test_a_gesture_in_the_feed_at_most_twice_a_turn(self):
        before = self.state(self.rid)
        t = 1000.0 + warten.GESTE_S
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(dungeon.maybe_close(self.rid, t))          # the request's hook: the gesture, the turn stays open
        g = self.gestures()
        self.assertEqual([(x["nsc"], x["geste"], x["text"][0]) for x in g], [("Oskar", "freundlich+", "Oskar nickt euch freundlich zu.")])
        self.assertIn("dungeon: geste | gezeigt", out.getvalue())
        after = self.state(self.rid)
        self.assertEqual({k: v for k, v in after.items() if k not in ("log", "geste")},
                         {k: v for k, v in before.items() if k not in ("log", "geste")})    # nothing else changes
        self.assertIsNone(warten.geste(dungeon, self.rid, t + 1))     # the next only after another GESTE_S
        self.assertIsNotNone(warten.geste(dungeon, self.rid, t + warten.GESTE_S))
        self.assertIsNone(warten.geste(dungeon, self.rid, t + 2 * warten.GESTE_S))   # GESTE_ZUG reached this turn
        self.assertEqual(len(self.gestures()), warten.GESTE_ZUG)
        self.assertTrue(all(isinstance(v, int) for v in warten.gesten_live().values()))

    def test_never_while_a_seat_plays_from_the_car(self):
        dungeon_auto.im_auto = lambda uid, now=None: uid == self.uid
        before = warten.gesten_live()["auto"]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(warten.geste(dungeon, self.rid, 1000.0 + warten.GESTE_S))
        self.assertEqual(self.gestures(), [])
        self.assertIn("dungeon: geste | auto", out.getvalue())
        self.assertEqual(warten.gesten_live()["auto"], before + 1)

    def test_nobody_fitting_waits_another_while(self):
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][self.rid]["nsc"]["oskar"]["wesen"] = {"freundlich": 1}
            dungeon._write(d)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(warten.geste(dungeon, self.rid, 1000.0 + warten.GESTE_S))
        self.assertIn("dungeon: geste | keine person", out.getvalue())
        self.assertEqual(self.gestures(), [])
        self.assertFalse(warten.geste_faellig(self.state(self.rid), 1000.0 + warten.GESTE_S + 1))


if __name__ == "__main__":
    unittest.main()
