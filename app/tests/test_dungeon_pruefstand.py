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
        ks = [k["id"] for k in r["klassen"]]
        i = ks.index(held[0]["klasse"])
        self.assertEqual([h["klasse"] for h in held], [ks[(i + j) % len(ks)] for j in range(5)])     # in turn from a drawn start
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
            self.assertLessEqual(kampf.adjusted(flat, len(held)), kampf.budget(dungeon, r, {}, held) * kampf.SCHWER)   # B16: as at the table
        for _ in range(20):                                                       # B8: „mittel“ counted by the table's rule
            wahl = ps.encounter(r, held, "mittel", rng)
            self.assertEqual(wahl, kampf.fill([(g, 1) for g, _ in wahl], len(held), kampf.budget(dungeon, r, {}, held)))
        x = ps.fight(r, held, ps.encounter(r, held, "mittel", rng), rng)
        self.assertEqual(set(x), {"sieg", "leben", "runden"})
        self.assertTrue(0 <= x["leben"] <= 1 and 1 <= x["runden"] <= ps.RUNDEN)
        before = dict(dungeon._day)
        a = ps.bench(r, kaempfe=10, stufen=[2], gruppen=[3])
        self.assertEqual(a, ps.bench(r, kaempfe=10, stufen=[2], gruppen=[3]))       # the same seed, the same table
        self.assertEqual(set(a["2/3"]), {"siege", "leben", "runden"})
        self.assertEqual(dict(dungeon._day), before)                               # no fight of the bench counts

    def test_heroes_like_at_the_table(self):
        """Review 27.10. B6 and B11 (Dominik 2026-10-27 „ok“): the bench's heroes are raised like a player's, level by
        level with the first of the two abilities offered and every point on the class's order; every class of the world
        comes; the gear has the rarity of the median find from foes up to the level (never an assumption of its own); the
        budget grows with the level."""
        import random
        r = dungeon.rules()
        h = ps.raise_to(r, dungeon.new_hero(r, {"name": "Held 1", "volk": r["voelker"][0]["id"], "klasse": "heiler"}), 6, random.Random(2))
        k = dungeon._by(r, "klassen")["heiler"]
        self.assertEqual((h["stufe"], h["punkte"], h["wahl"]), (6, 0, []))
        self.assertEqual(len(h["faehigkeiten"]), len(k.get("start_faehigkeiten") or []) + sum(1 for x in r["faehigkeit_auf"] if x <= 6))
        fresh = dungeon.new_hero(r, {"name": "Held 1", "volk": r["voelker"][0]["id"], "klasse": "heiler"})
        self.assertEqual(sum(h["werte"].values()) - sum(fresh["werte"].values()), 5)
        self.assertEqual(h["werte"][k["reihe"][0]], min(dungeon.WERT_MAX, fresh["werte"][k["reihe"][0]] + 5))
        self.assertEqual(h["leben"], dungeon.life(r, h))
        seen = {x["klasse"] for i in range(40) for x in ps.party(r, 1, 1, random.Random(i))}
        self.assertEqual(seen, {k["id"] for k in r["klassen"]})
        order = [x["id"] for x in r["seltenheit"]]
        for stufe in range(1, 11):
            fund = sorted((dungeon.rarity(r, s, w)[1]["id"] for s in range(1, stufe + 1) for w in range(1, 101)), key=order.index)
            self.assertEqual(ps.gear_rarity(r, stufe), fund[len(fund) // 2])
        self.assertEqual(ps.gear_rarity(r, 1), "gewoehnlich")
        b = kampf.BUDGET[:r["grenzen"]["stufe_max"]]
        self.assertEqual(list(b), sorted(b))
        self.assertEqual(list(kampf.GRUPPE), sorted(kampf.GRUPPE))

    def test_the_aim_at_medium_for_every_level_and_group(self):
        """The self-test of the balance (Dominik 2026-10-24, Idee 5 „Ein Selbsttest hält das Ziel“)."""
        z = ps.bench(dungeon.rules(), kaempfe=ps.KAEMPFE, seed="selbsttest")      # as at night: 200 per cell
        self.assertEqual(len(z), dungeon.rules()["grenzen"]["stufe_max"] * ps.GRUPPE_MAX)
        off = {k: c["siege"] for k, c in z.items() if not ps.AIM[0] <= c["siege"] <= ps.AIM[1]}
        self.assertEqual(off, {}, "Stufe/Gruppe außerhalb des Ziels")


    def test_people_who_fight_keep_the_aim(self):
        """Personen-Katalog, balancing (Dominik 2026-10-26 „das ganze muss natürlich im balancing berücksichtigt
        werden“): encounters of people only, with their templates' weighted experience (dungeon_personen.GEWICHT), win
        70 to 90 per cent on average at „mittel“, every cell within SPANNE; the weight counts in the budget and the reward."""
        import dungeon_personen as P
        r = dungeon.rules()
        self.assertEqual(set(P.GEWICHT), set(P.templates()))
        by = dungeon._by(r, "gegner")
        self.assertEqual(P.weighted(by["schlaeger"])["ep"], round(by["schlaeger"]["ep"] * P.GEWICHT["schlaeger"]))
        z = ps.bench(r, kaempfe=ps.KAEMPFE, seed="selbsttest", personen=True)
        self.assertGreaterEqual(len(z), 40)
        mean = sum(c["siege"] for c in z.values()) / len(z)
        self.assertTrue(ps.AIM[0] <= mean <= ps.AIM[1], mean)
        self.assertEqual({k: c["siege"] for k, c in z.items() if not P.SPANNE[0] <= c["siege"] <= P.SPANNE[1]}, {})

    def test_runes_win_at_most_eight_points_more(self):
        """Review 27.10. 11.5 with the runes (bericht „Abstimmung mit den Runen“ 4, Dominik 2026-10-27 „ok“): the same
        groups with the runes found up to their level by the real find and trader rates, set as strong as the caps
        allow, win at most RUNEN_PLUS points more often than without (the mean of all cells), no cell makes a fight
        trivial (above the aim + RUNEN_PLUS), and the economy with every rune sold keeps its aim."""
        import random
        r = dungeon.rules()
        with mock.patch("dungeon_runen.wirkt", return_value=True):
            held = ps.party(r, 3, 8, random.Random(1), random.Random(2))
            self.assertTrue(any(it.get("ru") for h in held for it in dungeon.worn(h)))
            self.assertEqual([h["klasse"] for h in held], [h["klasse"] for h in ps.party(r, 3, 8, random.Random(1))])   # the same group
            for h in held:
                self.assertEqual(h["leben"], dungeon.life(r, h))
            ohne = ps.bench(r, kaempfe=ps.KAEMPFE // 2, seed="selbsttest")
            mit = ps.bench(r, kaempfe=ps.KAEMPFE // 2, seed="selbsttest", mit_runen=True)
            self.assertEqual(set(mit), set(ohne))
            self.assertLessEqual(ps.runes_plus(ohne, mit), ps.RUNEN_PLUS)
            self.assertEqual({k: c["siege"] for k, c in mit.items() if c["siege"] > ps.AIM[1] + ps.RUNEN_PLUS}, {})
            w = ps.economy(r, laeufe=ps.LAEUFE // 2, mit_runen=True)
        self.assertEqual({k: c["verhaeltnis"] for k, c in w.items() if not ps.WIRTSCHAFT[0] <= c["verhaeltnis"] <= ps.WIRTSCHAFT[1]}, {})

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
