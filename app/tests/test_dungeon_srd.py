"""Der SRD-Katalog des KI-Dungeon-Masters (dungeon_srd.json, Thread „DnDAppFiles für den Dungeon-Master“, Dominik
2026-10-23 „1-6“): Gegner, Gegenstände, Zauber, Zustände, Schwierigkeiten, Hintergründe, Völker und Klassen aus dem
System Reference Document 5.1 (CC-BY-4.0), dazu eigene Einträge für Horror, Sci-Fi und Piraten.

- Nur feste Daten im Repo: die Datei trägt die Namensnennung des SRD, keine Adresse außer der Lizenz, nichts wird
  nachgeladen; die Doku (de und en) nennt Quelle und Lizenz.
- Die Schicht passt zu den Grundregeln: check_rules auf dem zusammengeführten Stand ist leer, keine id kommt in
  dungeon_regeln.json und dungeon_srd.json zugleich vor (eine gleiche id ersetzte still); Ergänzungen alter Einträge
  nur als „dazu“, so bestehen die Grundregeln auch ohne die SRD-Datei.
- Alles ist erreichbar: jede Waffe gehört zu mindestens einer Klasse, jeder Gegenstand passt zu mindestens einer
  Klasse und Welt, jeder Zustand eines Gegners steht in der Liste, jede Startausrüstung eines Hintergrunds ist ein
  Gegenstand; jede Welt außer „eigene“ hat genug Gegner aller Stufen.
- Kräfte nur, wenn man sie kann (Dominik 2026-10-23 „1-3“): jede Klasse hat 1 bis 2 Startfähigkeiten aus ihrer eigenen
  Liste, jeder Zauber hat einen Grad und steht bei einer Klasse nur unter diesem Grad, jeder Zauber gehört zu mindestens
  einer Klasse mit Zaubern; die Ladungen gelten für Stufe 1 bis 10 und wachsen nie nach unten, auf Stufe 1 gibt es
  Ladungen nur für Grad 1.
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import dungeon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRD = os.path.join(os.path.dirname(HERE), "panel", "dungeon_srd.json")
DOCS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "docs")


def srd():
    with open(SRD, encoding="utf-8") as f:
        return json.load(f)


class Srd(unittest.TestCase):
    def test_nur_daten_mit_namensnennung(self):
        s = srd()
        self.assertIn("System Reference Document 5.1", s["lizenz"])
        self.assertIn("creativecommons.org/licenses/by/4.0", s["lizenz"])
        rest = json.dumps({k: v for k, v in s.items() if k != "lizenz"}, ensure_ascii=False)
        self.assertNotRegex(rest, r"https?://|www\.", "nur die Lizenz nennt eine Adresse")
        for name in ("de/assistent.md", "en/assistant.md"):
            with open(os.path.join(DOCS, name), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("SRD 5.1", text, name)
            self.assertIn("CC-BY-4.0", text, name)

    def test_schicht_besteht_die_regeln(self):
        self.assertEqual(dungeon.check_rules(dungeon._base_rules(srd=False)), [], "die Grundregeln bestehen allein")
        r = dungeon._base_rules()
        self.assertEqual(dungeon.check_rules(r), [], "sonst spielt das Panel still ohne SRD")
        s = srd()
        for k in ("gegner", "zustaende", "hintergruende"):
            self.assertEqual(len(r[k]), len(s[k]), k)
        self.assertEqual(r["sg"], s["sg"])

    def test_keine_id_doppelt(self):
        with open(dungeon.DATA, encoding="utf-8") as f:
            base = json.load(f)
        for k, v in srd().items():
            if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
                continue
            have = {x["id"] for x in base.get(k) or []}
            ids = [x["id"] for x in v if "dazu" not in x]
            self.assertEqual(len(ids), len(set(ids)), k)
            self.assertFalse(set(ids) & have, k)
            for x in v:
                if "dazu" in x:                     # appends to an entry of the base rules, never replaces it
                    self.assertEqual(set(x), {"id", "dazu"}, (k, x["id"]))
                    self.assertIn(x["id"], have, k)

    def test_alles_erreichbar(self):
        r = dungeon._base_rules()
        welten = {w["id"] for w in r["welten"]}
        klassen = {k["id"]: k for k in r["klassen"]}
        items = {x["id"]: x for x in r["gegenstaende"]}
        for x in srd()["gegenstaende"]:
            if "dazu" in x:
                self.assertTrue(set(x["dazu"]["klassen"]) <= set(klassen), x["id"])
                continue
            if x["art"] == "waffe":
                self.assertTrue(any(x["id"] in k["waffen"] for k in klassen.values()), x["id"])
            self.assertTrue(set(x.get("klassen") or klassen) <= set(klassen), x["id"])
            self.assertTrue(set(x.get("welten") or welten) <= welten, x["id"])
            if "hilft" in x:
                self.assertEqual(x["art"], "rolle", x["id"])
                self.assertTrue(all(re.fullmatch(r"[a-zäöüß]{2,20}", w) for w in x["hilft"]["worte"]), x["id"])
        zid = {z["id"] for z in r["zustaende"]}
        for g in r["gegner"]:
            self.assertTrue(set(g.get("zustaende") or []) <= zid, g["id"])
            self.assertTrue(set(g["welten"]) <= welten | {"alle"}, g["id"])
        for h in r["hintergruende"]:
            self.assertTrue(set(h["start"]) <= set(items), h["id"])

    def test_jede_welt_hat_gegner_jeder_staerke(self):
        r = dungeon._base_rules()
        for w in r["welten"]:
            if w["id"] == "eigene":
                continue
            mine = [g for g in r["gegner"] if w["id"] in g["welten"] or "alle" in g["welten"]]
            self.assertGreaterEqual(len(mine), 15, w["id"])
            self.assertTrue(any(g["stufe"] <= 0.5 for g in mine), w["id"])
            self.assertTrue(any(g["stufe"] >= 5 for g in mine), w["id"])

    def test_kraefte_nur_wenn_man_sie_kann(self):
        r = dungeon._base_rules()
        items = {x["id"]: x for x in r["gegenstaende"]}
        bekannt = set()
        for k in r["klassen"]:
            own = {f["id"] for f in k["faehigkeiten"]}
            self.assertTrue(1 <= len(k["start_faehigkeiten"]) <= 2 and set(k["start_faehigkeiten"]) <= own, k["id"])
            for g, ids in (k.get("zauber") or {}).items():
                for i in ids:
                    self.assertEqual((items[i]["art"], items[i]["grad"]), ("zauber", int(g)), (k["id"], i))
                    bekannt.add(i)
        self.assertEqual({i for i, x in items.items() if x["art"] == "zauber"}, bekannt, "jeder Zauber gehört zu einer Klasse")
        la = r["ladungen"]
        self.assertEqual(len(la), 10)
        self.assertTrue(all(len(x) == 5 and all(0 <= n <= 9 for n in x) for x in la))
        self.assertTrue(all(a <= b for x, y in zip(la, la[1:]) for a, b in zip(x, y)))
        self.assertEqual(la[0][1:], [0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
