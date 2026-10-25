"""KI-Dungeon-Master: echte Würfel am Tisch (dungeon_echt.py, dungeonwarten.js; D&D idea 5, Dominik 2026-10-25 „1-12“).

- Off by default: without the admin's switch (chat.dungeon_echtwuerfel) or without the host's seats (rd["echt"])
  nobody is asked and the panel rolls as always.
- Never in the car: a seat whose profile plays from the car is not asked; until dungeon_auto.im_auto exists nobody is.
- The number is data: only the own seat, only the turn asked, only whole numbers 1 to 20, as many as asked, once.
- The panel waits at most WARTE_S, then rolls itself; a seat's d20 comes from its numbers first, then from the dice.
- Live and the journal: numbers and fixed words only.

No wall clock in the checks: every time is given, the waits are made short.
"""
import asyncio
import os
import random
import threading
import time
import unittest

from tests import helpers
from tests.test_dungeon import Base

import dungeon  # noqa: E402
import dungeon_auto  # noqa: E402
import dungeon_echt as echt  # noqa: E402
import guard  # noqa: E402

PANEL = os.path.dirname(os.path.abspath(echt.__file__))


def car(test, fn):
    """dungeon_auto.im_auto for the test (the main thread's helper), taken back afterwards."""
    had = hasattr(dungeon_auto, "im_auto")
    old = getattr(dungeon_auto, "im_auto", None)
    dungeon_auto.im_auto = fn
    test.addCleanup(lambda: setattr(dungeon_auto, "im_auto", old) if had else delattr(dungeon_auto, "im_auto"))


def round_dict(echt_pids=("p1",)):
    return {"owner": "u1", "echt": list(echt_pids), "zug": 3,
            "plaetze": {"p1": {"held": {"name": "Mira"}, "uid": "u1"}, "p2": {"held": {"name": "Bo"}}, "p3": {}}}


class Rules(unittest.TestCase):
    def setUp(self):
        car(self, lambda uid: False)

    def test_who_is_asked(self):
        rd = round_dict(("p1", "p2", "p3"))
        proben = [{"pid": "p1", "wert": "ges", "schwer": 14}, {"pid": "p2", "wert": "str", "schwer": 12, "vt": "vorteil"},
                  {"pid": "p3", "wert": "ges", "schwer": 10}, {"pid": "p9", "wert": "ges", "schwer": 10}]
        self.assertEqual(echt.seats(rd, proben), {"p1": [{"wert": "ges", "schwer": 14, "n": 1}], "p2": [{"wert": "str", "schwer": 12, "n": 2}]})
        self.assertEqual(echt.seats(round_dict(("p2",)), proben), {"p2": [{"wert": "str", "schwer": 12, "n": 2}]})   # only the host's seats

    def test_never_in_the_car(self):
        car(self, lambda uid: uid == "u1")
        rd = round_dict(("p1", "p2"))
        proben = [{"pid": "p1", "wert": "ges", "schwer": 14}, {"pid": "p2", "wert": "ges", "schwer": 14}]
        self.assertEqual(list(echt.seats(rd, proben)), ["p2"])          # a guest seat has no car
        delattr(dungeon_auto, "im_auto")
        self.addCleanup(setattr, dungeon_auto, "im_auto", lambda uid: False)
        self.assertEqual(echt.seats(rd, proben), {})                     # no car rule yet: nobody is asked

    def test_hand_takes_the_numbers_first(self):
        h = echt.Hand({"p1": [17, 4]})
        rng = random.Random(1)
        self.assertEqual([h.d20("p1", rng), h.d20("p1", rng)], [17, 4])
        self.assertTrue(1 <= h.d20("p1", rng) <= 20)                     # then the panel's dice (Glück, Heldenmut)
        self.assertTrue(h.used("p1"))
        self.assertFalse(h.used("p2"))
        self.assertTrue(1 <= h.d20("p2", rng) <= 20)
        self.assertFalse(h.used("p2"))

    def test_the_number_is_data(self):
        rd = round_dict(("p1", "p2"))
        rd["echt_frage"] = {"zug": 3, "t": 100.0, "plaetze": {"p1": {"fragen": [{"wert": "ges", "schwer": 14, "n": 2}], "zahlen": None}}}
        for bad in (None, [], [17], [0, 5], [21, 5], ["17", 5], [True, 5], [3.5, 5], [17, 5, 6], "17 5", [-1, 5]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                echt.give(rd, "p1", 3, bad)
        with self.assertRaises(TimeoutError):
            echt.give(rd, "p1", 2, [17, 5])                              # an old turn
        with self.assertRaises(TimeoutError):
            echt.give(rd, "p1", True, [17, 5])
        with self.assertRaises(LookupError):
            echt.give(rd, "p2", 3, [17])                                 # a seat not asked
        echt.give(rd, "p1", 3, [20, 1])
        self.assertEqual(rd["echt_frage"]["plaetze"]["p1"]["zahlen"], [20, 1])
        with self.assertRaises(FileExistsError):
            echt.give(rd, "p1", 3, [5, 5])                               # once

    def test_view_shows_only_the_own_questions(self):
        rd = round_dict(("p1", "p2"))
        self.assertIsNone(echt.view(rd, "p1", now=100.0))
        rd["echt_frage"] = {"zug": 3, "t": 100.0, "plaetze": {"p1": {"fragen": [{"wert": "ges", "schwer": 14, "n": 1}], "zahlen": None},
                                                             "p2": {"fragen": [{"wert": "str", "schwer": 9, "n": 1}], "zahlen": None}}}
        v = echt.view(rd, "p1", now=110.0)
        self.assertEqual((v["fragen"], v["rest"], v["andere"], v["fertig"]), ([{"wert": "ges", "schwer": 14, "n": 1}], echt.WARTE_S - 10, ["Bo"], False))
        self.assertNotIn("zahlen", str(v))
        rd["echt_frage"]["plaetze"]["p2"]["zahlen"] = [7]
        v = echt.view(rd, "p2", now=110.0)
        self.assertEqual((v["fragen"], v["fertig"], v["andere"]), ([], True, ["Mira"]))
        self.assertEqual(echt.view(rd, "p1", now=100.0 + echt.WARTE_S + 9)["rest"], 0)

    def test_switch_is_off_by_default(self):
        import json
        import features
        self.assertIn("dungeonechtwuerfel", features.BY_KEY)
        with open(os.path.join(PANEL, "..", "config.default.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f)["chat"]["dungeon_echtwuerfel"], False)
        self.assertIn("dungeonecht", guard.RATE)
        live = echt.for_live()
        self.assertTrue(all(isinstance(x, int) for x in live.values()))


class Table(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_echtwuerfel")
        helpers.set_config(dungeon_echtwuerfel=True)
        car(self, lambda uid: False)
        for k, v in (("WARTE_S", 5), ("TAKT_S", 0.02)):
            self.addCleanup(setattr, echt, k, getattr(echt, k))
            setattr(echt, k, v)
        v = self.new_round()
        self.rid = v["rid"]
        self.code, self.gpid = self.guest(self.rid)
        self.host = next(p for p, x in self.state(self.rid)["plaetze"].items() if x.get("uid") == self.uid)

    def set_round(self, **kw):
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][self.rid].update(kw)
            dungeon._write(d)

    def ask(self, give=None):
        """real_ask on the round with both seats' checks; give(turn) runs beside it like a player at the table."""
        rd = self.state(self.rid)
        proben = [{"pid": self.gpid, "wert": "ges", "schwer": 14}, {"pid": self.host, "wert": "str", "schwer": 12, "vt": "vorteil"}]
        out = {}

        async def go():
            if give:
                t = threading.Thread(target=give, args=(rd["zug"],))
                t.start()
            out["hand"] = await echt.real_ask(dungeon, self.rid, rd["zug"], rd, proben)
            if give:
                await asyncio.to_thread(t.join)
        asyncio.run(go())
        return out["hand"]

    def wait_for_question(self):
        for _ in range(200):
            if self.state(self.rid).get("echt_frage"):
                return
            time.sleep(0.01)
        self.fail("no question")

    def test_off_without_the_switch_or_the_seats(self):
        self.assertIsNone(self.ask())                                    # the host chose no seats
        self.set_round(echt=[self.gpid])
        helpers.set_config(dungeon_echtwuerfel=False)
        self.assertIsNone(self.ask())
        self.assertNotIn("echt_frage", self.state(self.rid))

    def test_numbers_from_the_table(self):
        self.set_round(echt=[self.gpid, self.host])

        def players(turn):
            self.wait_for_question()
            v = self.v.post("/api/dungeon/echt", json={"code": self.code, "zug": turn, "zahlen": [17]})
            self.assertEqual(v.status_code, 200, v.text)
            self.assertEqual(v.json()["echt"]["fertig"], True)
            self.assertEqual(self.c.post(f"/api/profile/dungeon/{self.rid}/echt", json={"zug": turn, "zahlen": [3]}).status_code, 400)  # two dice asked
            self.assertEqual(self.c.post(f"/api/profile/dungeon/{self.rid}/echt", json={"zug": turn, "zahlen": [20, 1]}).status_code, 200)
            self.assertEqual(self.v.post("/api/dungeon/echt", json={"code": self.code, "zug": turn, "zahlen": [5]}).status_code, 409)   # once
        hand = self.ask(players)
        rng = random.Random(3)
        self.assertEqual((hand.d20(self.gpid, rng), hand.d20(self.host, rng), hand.d20(self.host, rng)), (17, 20, 1))
        self.assertTrue(hand.used(self.gpid) and hand.used(self.host))
        self.assertNotIn("echt_frage", self.state(self.rid))             # the question goes with the roll

    def test_the_panel_rolls_after_the_wait(self):
        echt.WARTE_S = 0.2
        self.set_round(echt=[self.gpid])
        before = echt.for_live()["rueckfall"]
        hand = self.ask()
        self.assertFalse(hand.used(self.gpid))
        self.assertTrue(1 <= hand.d20(self.gpid, random.Random(1)) <= 20)
        self.assertEqual(echt.for_live()["rueckfall"], before + 1)
        self.assertNotIn("echt_frage", self.state(self.rid))

    def test_doors(self):
        self.set_round(echt=[self.gpid], echt_frage={"zug": 9, "t": time.time(), "plaetze": {self.gpid: {"fragen": [{"wert": "ges", "schwer": 14, "n": 1}], "zahlen": None}}})
        self.assertEqual(self.v.post("/api/dungeon/echt", json={"code": "x" * 32, "zug": 9, "zahlen": [5]}).status_code, 400)
        self.assertEqual(self.c2.post(f"/api/profile/dungeon/{self.rid}/echt", json={"zug": 9, "zahlen": [5]}).status_code, 404)   # no seat
        self.assertEqual(self.c.post(f"/api/profile/dungeon/{self.rid}/echt", json={"zug": 9, "zahlen": [5]}).status_code, 404)    # not asked
        for bad in ([0], [21], ["5"], [5, 5]):
            self.assertEqual(self.v.post("/api/dungeon/echt", json={"code": self.code, "zug": 9, "zahlen": bad}).status_code, 400)
        self.assertEqual(self.v.post("/api/dungeon/echt", json={"code": self.code, "zug": 8, "zahlen": [5]}).status_code, 409)
        self.assertEqual(self.v.post("/api/dungeon/echt", json={"code": self.code, "zug": 9, "zahlen": [5]}).status_code, 200)

    def test_view_and_page(self):
        self.set_round(echt=[self.gpid], echt_frage={"zug": 9, "t": time.time(), "plaetze": {self.gpid: {"fragen": [{"wert": "ges", "schwer": 14, "n": 1}], "zahlen": None}}})
        v = self.v.post("/api/dungeon/platz", json={"code": self.code})
        self.assertEqual(v.status_code, 200)
        host = self.c.get(f"/api/profile/dungeon/{self.rid}").json()
        self.assertEqual(host["echt"]["fragen"], [])
        self.assertEqual(host["echt"]["andere"], ["Bela"])
        with open(os.path.join(PANEL, "static", "js", "dungeonwarten.js"), encoding="utf-8") as f:
            js = f.read()
        for s in ("data-dmechtz", "/api/dungeon/echt", "/echt`", "dmEchtZahlen", "siebzehn:17", "seventeen:17"):
            self.assertIn(s, js)


if __name__ == "__main__":
    unittest.main()
