"""Gleichgewicht of the Dungeon Master's catalog (dungeon_balance.py, Dominik 2026-10-24 „1-5“, „zu stark nur hinweis“).

- The fixed tables mark a foe or an item by its numbers alone: a usual foe is „ausgewogen“, double damage „zu stark“,
  half of everything „schwach“; an item over its rarity's budget „stark“, far over it „zu stark“, with one sentence why.
- The shipped catalog (base rules and SRD layer) holds nothing „zu stark“ beyond the list below, which only shrinks.
- „Zu stark“ is only a hint: the admin's own rules with such an entry still save, and the rules page shows the mark.
"""
import unittest

from tests import helpers

helpers.start()
import dungeon  # noqa: E402
import dungeon_balance as balance  # noqa: E402

# shipped entries still marked „zu stark“, handed to the data thread „DnDAppFiles für den Dungeon-Master“ on 2026-10-24;
# this list only ever shrinks (a fixed entry leaves it in the same commit)
NOCH_ZU_STARK = {"bulette", "drachenblut", "hoher_heiltrank", "piranhaschwarm", "schwertwal", "seeschlange", "warg",
                 "wasseratmungstrank"}


class Marks(unittest.TestCase):
    def test_a_usual_foe_is_balanced_and_double_damage_is_too_strong(self):
        hp, ac, atk, dpr = balance.usual(3)
        g = {"stufe": 3, "leben": round(hp), "ruestung": round(ac), "angriff": round(atk), "schaden": 8, "anzahl_wuerfel": 1,
             "schaden_plus": round(dpr - 4.5)}
        self.assertEqual(balance.foe(g)["marke"], "ok")
        strong = dict(g, anzahl_wuerfel=4, schaden=10, leben=round(hp * 2))
        m = balance.foe(strong, "de")
        self.assertEqual(m["marke"], "zu_stark")
        self.assertIn("Stufe 3", m["grund"])
        self.assertEqual(balance.foe(dict(g, leben=5, schaden=2, schaden_plus=0))["marke"], "schwach")
        self.assertIn("level 3", balance.foe(strong, "en")["grund"])

    def test_items_by_their_rarity(self):
        self.assertEqual(balance.item({"art": "waffe", "schaden": 8})["marke"], "ok")
        self.assertEqual(balance.item({"art": "waffe", "schaden": 14})["marke"], "stark")
        self.assertEqual(balance.item({"art": "waffe", "schaden": 20})["marke"], "zu_stark")
        self.assertEqual(balance.item({"art": "waffe", "schaden": 20, "seltenheit": "legendaer", "preis": 3000})["marke"], "ok")
        self.assertEqual(balance.item({"art": "zauber", "grad": 5, "seltenheit": "gewoehnlich"})["marke"], "zu_stark")
        self.assertEqual(balance.item({"art": "zauber", "grad": 2, "seltenheit": "gewoehnlich"})["marke"], "stark")
        self.assertEqual(balance.item({"art": "zauber", "grad": 3, "seltenheit": "rar"})["marke"], "ok")
        cheap = balance.item({"art": "schmuck", "seltenheit": "legendaer", "preis": 10})
        self.assertEqual(cheap["marke"], "stark")
        self.assertIn("1500", cheap["grund"])
        self.assertEqual(balance.item({"art": "trank", "segen": {"bonus": 5, "zuege": 3}})["marke"], "zu_stark")


class Catalog(unittest.TestCase):
    def test_nothing_shipped_is_too_strong_beyond_the_list(self):
        s = balance.summary(dungeon.rules())
        too = {i for part in s.values() for i, m in part.items() if m["marke"] == "zu_stark"}
        self.assertEqual(too - NOCH_ZU_STARK, set(), "neu zu stark")
        self.assertEqual(NOCH_ZU_STARK - too, set(), "nicht mehr zu stark: aus NOCH_ZU_STARK nehmen")
        for part in s.values():
            for i, m in part.items():
                self.assertIn(m["marke"], balance.MARKEN, i)
                self.assertTrue(m["grund"] or m["marke"] == "ok", i)


if __name__ == "__main__":
    unittest.main()
