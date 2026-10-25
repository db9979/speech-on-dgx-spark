"""KI-Dungeon-Master: das Bestiarium (Bestiarium-Punkte 3 und 9, Dominik 2026-10-24 „Ja, alles nach Empfehlung umsetzen“).

- Lücken geschlossen: jede Welt, auch die eigene (sie nimmt die Gegner von dungeon_legenden.SONST) und eine neue des
  Admins, hat auf jeder Stufe 1 bis 12 mindestens drei Gegner (dungeon_kampf.plays_in, dieselbe Regel wie die Begegnung).
- Die eigenen neuen Gegner tragen „seit“ mit einer gültigen Version und reden im Ton des Kindertischs.
- Die Regelseite zeigt je Gegner Schadensart, Schwäche, Widerstand und Immunität als Symbole (jede Schadensart hat
  eines), die Boss-Marke mit Phase 2 und zwei Angriffen, die EP je Held, die Welten und „neu“ für NEU_FUER Versionen;
  die Filter nach Welt kommen vom Panel.
"""
import json
import os
import re
import unittest

from tests.test_dungeon_dingbild import ADMIN, Base
import dungeon  # noqa: E402
import dungeon_kampf as kampf  # noqa: E402
import dungeon_regelseite as rs  # noqa: E402

K = "/api/admin/dungeon/katalog/"
SRD = os.path.join(os.path.dirname(os.path.abspath(dungeon.__file__)), "dungeon_srd.json")
HART = ("blut", "tod", "tote", "leiche", "untot", "schlacht", "ertrunk", "death", "dead", "blood", "corpse", "drown")


def srd():
    with open(SRD, encoding="utf-8") as f:
        return json.load(f)


class Bestand(unittest.TestCase):
    def test_jede_welt_hat_drei_gegner_je_stufe(self):
        r = dungeon._base_rules()
        welten = [w["id"] for w in r["welten"]] + ["neu_vom_admin"]
        for w in welten:
            for s in range(1, 13):
                n = [g["id"] for g in r["gegner"] if int(g["stufe"]) == s and kampf.plays_in(r, g, w)]
                self.assertGreaterEqual(len(n), 3, (w, s, n))

    def test_eigene_welt_wie_sonst(self):
        r = dungeon._base_rules()
        fan = next(g for g in r["gegner"] if g["welten"] == ["fantasy"])
        sci = next(g for g in r["gegner"] if g["welten"] == ["scifi"])
        self.assertTrue(kampf.plays_in(r, fan, "eigene"))
        self.assertFalse(kampf.plays_in(r, sci, "eigene"))
        self.assertFalse(kampf.plays_in(r, fan, "scifi"))
        alle = next(g for g in r["gegner"] if "alle" in g["welten"])
        self.assertTrue(all(kampf.plays_in(r, alle, w["id"]) for w in r["welten"]))

    def test_neue_gegner_mit_version_und_im_ton(self):
        neu = [g for g in srd()["gegner"] if "seit" in g]
        self.assertGreaterEqual(len(neu), 62)
        jetzt = rs._vnum(rs.app_version())
        for g in neu:
            v = rs._vnum(g["seit"])
            self.assertIsNotNone(v, g["id"])
            self.assertLessEqual(v, jetzt, g["id"])
            text = " ".join(g["name"] + g["info"]).lower()
            self.assertFalse([w for w in HART if re.search(r"\b" + w, text)], g["id"])     # word starts: „bleiche“ is fine

    def test_neu_nur_fuer_eine_weile(self):
        self.assertEqual((rs._vnum("V01.1.038"), rs._vnum("V01.0.999"), rs._vnum("x"), rs._vnum(None)), (1038, 999, None, None))
        self.assertTrue(rs.frisch({"seit": "V01.0.990"}, "V01.1.005"))          # over the step to the next series
        self.assertTrue(rs.frisch({"seit": "V01.1.038"}, "V01.1.038"))
        self.assertFalse(rs.frisch({"seit": "V01.1.038"}, f"V01.1.{38 + rs.NEU_FUER:03d}"))
        self.assertFalse(rs.frisch({"seit": "V01.1.040"}, "V01.1.038"))
        self.assertFalse(rs.frisch({}, "V01.1.038"))

    def test_jede_schadensart_hat_ein_symbol(self):
        self.assertEqual(set(kampf.ART_ZEICHEN), set(kampf.SCHADEN_ARTEN))
        self.assertTrue(all(kampf.ART_ZEICHEN.values()))


class Seite(Base):
    def test_zeilen_mit_symbolen_boss_und_filtern(self):
        d = ADMIN.get(K + "gegner").json()
        r = dungeon.rules()
        self.assertEqual([w["id"] for w in d["weltfilter"]], [w["id"] for w in r["welten"]])
        self.assertEqual(set(d["arten"]), set(kampf.SCHADEN_ARTEN))
        rows = {x["id"]: x for x in d["zeilen"]}
        for x in rows.values():
            self.assertTrue({"arten", "boss", "welten", "frisch"} <= set(x), x["id"])
            self.assertIn(x["arten"]["art"], kampf.SCHADEN_ARTEN, x["id"])
        sk = rows["skelett"]
        self.assertIn("wucht", sk["arten"]["schwaeche"])
        self.assertIn("eigene", rows["goblin"]["welten"])          # the own world takes the fantasy foes
        self.assertEqual(rows["sturmhueter"]["welten"], [w["id"] for w in r["welten"]])
        boss = next(x for x in rows.values() if x["boss"])
        w = dict(boss["werte"])
        self.assertIn(f"+{kampf.BOSS_PHASE} zum Treffen", w["Boss"])
        self.assertIn("zwei Angriffe", w["Boss"])
        g = dict(rows["goblin"]["werte"])
        self.assertEqual(g["EP je Held"], "2: 25 · 3: 16 · 4: 12 · 5: 10")
        self.assertIn("Hieb", g["Schadensart"])
        self.assertNotIn("Boss", g)
        en = {x["id"]: dict(x["werte"]) for x in ADMIN.get(K + "gegner?lang=en").json()["zeilen"]}
        self.assertIn("slashing", en["goblin"]["Damage kind"])


if __name__ == "__main__":
    unittest.main()
