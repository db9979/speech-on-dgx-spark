"""KI-Dungeon-Master: the balance bench „Balance-Prüfstand“ (dungeon_pruefstand.py, Dominik 2026-10-24 „alle umsetzen“,
Idee 5).

- The bench fights with the real rules: a group of the level built like a player's hero, an encounter of exactly the
  danger asked, the fight through dungeon_kampf's attacks and the foes' turn; the same seed gives the same table.
- The aim: at „mittel“ a group wins AIM (70 to 90 per cent) at every level and group size.
- Only while „Balance-Prüfstand“ is on: the night runs once a night in its window, the admin's button at most once a
  minute and one run at a time; a profile gets nothing.
- The live overview has numbers only; nothing of a round is touched, nothing counts into the day's numbers.

No wall clock: the module's clock is set by the tests.
"""
import asyncio
import datetime
import os
import unittest
from unittest import mock

from tests.test_dungeon_dingbild import ADMIN, Base
import dungeon  # noqa: E402
import dungeon_kampf as kampf  # noqa: E402
import dungeon_pruefstand as ps  # noqa: E402
import live  # noqa: E402
from tests import helpers  # noqa: E402

P = "/api/admin/dungeon/pruefstand"
NIGHT = datetime.datetime(2026, 3, 4, 3, 0).timestamp()
NOON = datetime.datetime(2026, 3, 4, 12, 0).timestamp()


class Bench(unittest.TestCase):
    def test_a_group_an_encounter_and_a_fight_by_the_real_rules(self):
        import random
        r = dungeon.rules()
        rng = random.Random(1)
        held = ps.party(r, 5, 4, rng)
        self.assertEqual([h["klasse"] for h in held], [k["id"] for k in r["klassen"]][:5])
        for h in held:
            self.assertEqual((h["stufe"], h["leben"]), (4, dungeon.life(r, h)))
            self.assertEqual(dungeon._c(r, h["an"]["haupthand"])["art"], "waffe")
            self.assertIn(h["an"]["koerper"]["id"] if h["an"].get("koerper") else "",
                          [x["id"] for x in r["gegenstaende"] if x["art"] == "ruestung"] + [""])
        for gefahr in ("leicht", "mittel", "schwer"):
            wahl = ps.encounter(r, held, gefahr, rng)
            self.assertTrue(wahl, gefahr)
            flat = [g for g, n in wahl for _ in range(n)]
            self.assertLessEqual(len(flat), kampf.GEGNER_MAX)
            self.assertEqual(kampf.danger(kampf.adjusted(flat), kampf.budget(dungeon, r, {}, held)), gefahr)
        x = ps.fight(r, held, ps.encounter(r, held, "mittel", rng), rng)
        self.assertEqual(set(x), {"sieg", "leben", "runden"})
        self.assertTrue(0 <= x["leben"] <= 1 and 1 <= x["runden"] <= ps.RUNDEN)
        before = dict(dungeon._day)
        a = ps.bench(r, kaempfe=10, stufen=[2], gruppen=[3])
        self.assertEqual(a, ps.bench(r, kaempfe=10, stufen=[2], gruppen=[3]))       # the same seed, the same table
        self.assertEqual(set(a["2/3"]), {"siege", "leben", "runden"})
        self.assertEqual(dict(dungeon._day), before)                               # no fight of the bench counts

    def test_the_aim_at_medium_for_every_level_and_group(self):
        """The self-test of the balance (Dominik 2026-10-24, Idee 5 „Ein Selbsttest hält das Ziel“)."""
        z = ps.bench(dungeon.rules(), kaempfe=ps.KAEMPFE, seed="selbsttest")      # as at night: 200 per cell
        self.assertEqual(len(z), dungeon.rules()["grenzen"]["stufe_max"] * ps.GRUPPE_MAX)
        off = {k: c["siege"] for k, c in z.items() if not ps.AIM[0] <= c["siege"] <= ps.AIM[1]}
        self.assertEqual(off, {}, "Stufe/Gruppe außerhalb des Ziels")


    def test_the_economy_keeps_its_aim(self):
        """Wirtschaft Punkt 6 (Dominik 2026-10-25 „1-12“): at every level a hero earns 1.2 to 2 times what normal play
        costs (median), and no find sells for more than ten times a level's income; the inn grows with the level."""
        import dungeon_gold as gold
        w = ps.economy(dungeon.rules())
        self.assertEqual(len(w), dungeon.rules()["grenzen"]["stufe_max"])
        off = {k: c["verhaeltnis"] for k, c in w.items() if not ps.WIRTSCHAFT[0] <= c["verhaeltnis"] <= ps.WIRTSCHAFT[1]}
        self.assertEqual(off, {}, "Stufe außerhalb des Ziels")
        self.assertEqual({k: c["fund_max"] for k, c in w.items() if c["fund_max"] > ps.JACKPOT * c["einnahmen"]}, {})
        self.assertEqual(gold.PREIS["gasthaus"], 10)
        self.assertEqual(ps.economy(dungeon.rules(), laeufe=5, stufen=[2]), ps.economy(dungeon.rules(), laeufe=5, stufen=[2]))


class Page(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_pruefstand")
        helpers.set_config(dungeon_pruefstand=False)
        self.t = [NOON]
        for target, new in (("dungeon_pruefstand.clock", lambda: self.t[0]), ("dungeon_pruefstand.KAEMPFE", 2)):
            p = mock.patch(target, new)
            p.start()
            self.addCleanup(p.stop)
        ps._run.update(laeuft=False, seit=0)
        self._drop()
        self.addCleanup(self._drop)

    def _drop(self):
        if os.path.exists(ps.FILE):
            os.remove(ps.FILE)

    def test_only_the_admin_and_only_while_on(self):
        self.assertIn(self.c.get(P).status_code, (401, 403))
        self.assertIn(self.c.post(P, json={}).status_code, (401, 403))
        d = ADMIN.get(P).json()
        self.assertEqual((d["an"], d["zellen"], d["ziel"]), (False, {}, list(ps.AIM)))
        self.assertEqual(ADMIN.post(P, json={}).status_code, 409)
        self.t[0] = NIGHT
        asyncio.run(ps.due())
        self.assertFalse(os.path.exists(ps.FILE))                                   # off: no night run either
        self.assertEqual(live._pruefstand(), "")

    def test_the_button_the_night_and_the_live_line(self):
        helpers.set_config(dungeon_pruefstand=True)
        self.assertIn("noch ohne Lauf", live._pruefstand())
        with mock.patch("dungeon_pruefstand._spawn", ps._go):                    # the run in the request, not in a thread
            d = ADMIN.post(P, json={}).json()
            self.assertTrue(d["laeuft"])
            self.assertEqual(ADMIN.post(P, json={}).status_code, 429)              # at most once a minute
        d = ADMIN.get(P).json()
        n = dungeon.rules()["grenzen"]["stufe_max"] * ps.GRUPPE_MAX
        self.assertEqual((len(d["zellen"]), d["kaempfe"], d["laeuft"]), (n, 2, False))
        self.assertRegex(live._pruefstand(), r"^ · Prüfstand \d+ Felder, \d+ unter und \d+ über dem Ziel$")
        self.assertEqual(ps.last()["nacht"], "")                                  # the button is not the night's run
        asyncio.run(ps.due())                                                      # noon: no night run
        self.assertEqual(ps.last()["nacht"], "")
        self.t[0] = NIGHT
        asyncio.run(ps.due())
        self.assertEqual(ps.last()["nacht"], "2026-03-04")
        zeit = ps.last()["zeit"]
        self.t[0] = NIGHT + 600
        asyncio.run(ps.due())
        self.assertEqual(ps.last()["zeit"], zeit)                                  # once a night


if __name__ == "__main__":
    unittest.main()
