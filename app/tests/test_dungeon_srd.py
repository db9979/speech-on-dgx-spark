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
- Kampf Teil 2: Schadensart, Resistenz, Immunität und Schwäche jedes Gegners nur aus der festen Liste der
  Schadensarten, keine Art zugleich in zwei dieser Listen, „boss“ nur als true; jede Waffe der SRD-Datei hat eine Schadensart und
  Eigenschaften nur aus der festen Liste.
- Wirtschaft und Schadensarten (Dominik 2026-10-25 „1-12“): ein eigener Preis liegt im Band seiner Seltenheit
  (gewöhnlich bis 50, selten bis 250, rar bis 1000, episch bis 4000), Legendäres hat keinen Preis; jeder Schatz hat
  eine Klasse (klein, mittel, groß) und keinen eigenen Preis; Schutz nennt nur Schadensarten der Liste und ist nie
  mehr als halber Schaden (kein immun bei Helden-Dingen).
- Mehrfachangriff (Dominik 2026-10-25, Tabletop-Punkt 12): "angriffe" nur 2 bis 5, fehlt = 1.
- NSC-Tabellen, Silben und Orakel (Tabletop-Punkte 5 und 8): jede Tabelle mindestens 6 Zeilen je Welt, jedes Volk hat
  Silben („namensilben“, nicht „silben“: das sind die Ortsnamen der Karte), die Orakel-Zeilen aus Datasworn nur aus CC-BY-4.0 mit Namensnennung.
- SRD 5.2.1 (Tabletop-Punkt 13): die Tabelle „budget“ (leicht, mittel, schwer, je 10 Stufen, steigend) mit Namensnennung
  in der Datei und der Doku; kein Name und kein Text eines Gegners, Dings, Zustands, Volks, einer Klasse oder eines
  Hintergrunds trägt ein Wort aus der Wortliste des Kindertons (der Erzähler dürfte ihn am Kindertisch nie sagen).
- Kampf-Audit Welle 2 (H4, N6, N7): ein Zauber mit Rettungswurf nennt genau einen der sechs Werte, ein Zustand nur aus
  der Liste und nur mit Rettungswurf, „halb“ nur als true bei Schaden mit Rettungswurf; jeder Zauber ohne Schaden mit
  Zustand hat einen Rettungswurf; „verbuendeter“ nur bei Heilung; jeder Gegner hat einen SG von 5 bis 30, die Wache sticht.
- Nacht-Gegner (LlamaTale 1 „Tageszeit vom Panel“): „nacht“ nur als true; in jeder Welt passen für einen Helden der
  Stufe 1, 2 und 3 mindestens 5 Nacht-Gegner ins Budget (sonst bietet das Panel nachts alle an), auf jeder Stufe des
  Bestiariums von 0 bis 5 gibt es welche.
- Runen und Sockel (Plan dungeon-runen, Dominik 2026-10-27 „1a 2b 3a …“): 13 Runen mit den Rängen 1 bis 13 und den Preisen
  der Plan-Tabelle, 7 Runenwörter aus vorhandenen Runen mit Sockelzahl = Zahl der Runen; dungeon_runen.check_rules
  lehnt fremde Schlüssel, Treffer außerhalb der Waffe, Effekte am falschen Ort, Lücken im Rang und falsche Sockel ab.
- NSC-Tabellen (Hauptthread 2026-10-27): jeder Beruf nennt die männliche und die weibliche Form („m“, „w“), die erste
  Spalte ist eine davon; „Aussehen“ beschreibt nur Äußeres, Art und Verhalten stehen unter „Art“ (feste Wortliste
  dungeon_tabellen.AUSSEHEN_NICHT), keine Zeile steht in beiden Tabellen; kein Beruf ist eine Maschine („Bord-KI“,
  Prüfbericht 2026-10-27 Z2/Z8).
- Was ein Gegner ist (Prüfbericht 2026-10-27 Z7, Z9, Z11, T24a): jeder Gegner trägt „wesen“ aus
  dungeon_bestiarium.WESEN (auch die Lücken der alten Handlisten: Seeräuber, Dorfbewohner, Goblinkrieger, Werbär),
  „friedlich“ nur true; jeder Gefährte trägt geschlecht, alter (nie Kind) und art; die Aussehen-Tabellen Haar, Augen,
  Bart und Statur nennen ihre Farbe als festes Wort, und der Text der Zeile zeigt dieselbe Farbe (dungeon_erzaehler).
- Kampf-EP (Prüfbericht B4 Option a, Paket 11.6): die gemessenen Werte des Hauptthreads stehen als „ep_kampf“ an den
  Gegnern, ganzzahlig im 0,25- bis 4-Fachen von „ep“; ohne Messung zählt ep (dungeon_bestiarium.ep_kampf).
- Englische Gegnernamen wie im SRD (Hauptthread 2026-10-28: ein englisch erzählendes Modell schrieb „stirges“ zur
  „Giant mosquito“): Stirge, Animated armor, Swarm of piranhas, Warg (wie die id).
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import dungeon  # noqa: E402
import dungeon_kampf as kampf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRD = os.path.join(os.path.dirname(HERE), "panel", "dungeon_srd.json")
DOCS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "docs")
ARTEN = set(kampf.SCHADEN_ARTEN)
EIGENSCHAFTEN = set(kampf.EIGENSCHAFTEN)


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
            self.assertIn("Ironsworn", text, name)

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
                self.assertIn(x["art"], dungeon.HILFT_ARTEN, x["id"])
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

    def test_schadensarten_nur_aus_der_liste(self):
        r = dungeon._base_rules()
        for g in r["gegner"]:
            self.assertIn(g.get("schaden_art", "hieb"), ARTEN, g["id"])
            listen = [set(g.get(k) or []) for k in ("resistenz", "immun", "schwaeche")]
            for x in listen:
                self.assertTrue(x <= ARTEN, g["id"])
            self.assertEqual(sum(map(len, listen)), len(set().union(*listen)), g["id"])
            self.assertIn(g.get("boss", True), (True,), g["id"])
        for x in srd()["gegenstaende"]:
            if x.get("art") == "waffe":
                self.assertIn(x.get("schaden_art"), ARTEN, x["id"])
                self.assertTrue(set(x.get("eigenschaften") or []) <= EIGENSCHAFTEN, x["id"])

    def test_preise_im_band_und_schaetze_nach_klasse(self):
        for x in srd()["gegenstaende"]:
            if "dazu" in x:
                continue
            if x["art"] == "schatz":
                self.assertIn(x.get("klasse"), dungeon.SCHATZ, x["id"])
                self.assertNotIn("preis", x, x["id"])
            elif x.get("seltenheit") == "legendaer":
                self.assertNotIn("preis", x, x["id"])
            elif "preis" in x:
                self.assertLessEqual(x["preis"], dungeon.PREISBAND[x.get("seltenheit", "gewoehnlich")], x["id"])

    def test_schutz_nur_aus_der_liste(self):
        for x in srd()["gegenstaende"]:
            if "oel" in x:
                self.assertEqual(x["art"], "trank", x["id"])
                self.assertIn(x["oel"], ARTEN - set(kampf.KOERPER), x["id"])
            if "widerstand" in x:
                self.assertIn(x["art"], dungeon.WIDERSTAND_ARTEN, x["id"])
                self.assertTrue(x["widerstand"] and set(x["widerstand"]) <= ARTEN, x["id"])
                self.assertNotIn("immun", x, x["id"])

    def test_jede_welt_trifft_donner_blitz_feuer_kaelte(self):
        # Wirtschaft Punkt 9: a foe weak to one of these kinds is never out of reach, by weapon or by an oil for every world
        r = dungeon._base_rules()
        oele = {x["oel"] for x in r["gegenstaende"] if "oel" in x and not x.get("welten")}
        for w in r["welten"]:
            if w["id"] == "eigene":
                continue
            for a in ("donner", "blitz", "feuer", "kaelte"):
                waffen = [x for x in r["gegenstaende"] if x["art"] == "waffe" and x.get("schaden_art") == a
                          and w["id"] in (x.get("welten") or [w["id"]])]
                self.assertTrue(waffen or a in oele, (w["id"], a))

    def test_jeder_gegner_hat_eine_sage(self):
        # D&D-Repo-Idee 12 (Monster-Album): every catalogue foe has its own legend line, both languages, at most 200 characters
        for g in srd()["gegner"]:
            self.assertEqual(len(g.get("sage") or []), 2, g["id"])
            self.assertTrue(all(isinstance(x, str) and 0 < len(x) <= 200 for x in g["sage"]), g["id"])

    def test_runde2_fuer_jede_szene_und_welt(self):
        # D&D-Ideen Runde 2: each kind of place and room of the map has at least 3 props (a fight scene draws 2 to 3), each
        # world has wishes and companions, the children's table has mild prices and an animal friend
        i = srd()["ideen"]
        karte = json.load(open(os.path.join(os.path.dirname(dungeon.__file__), "dungeon_karte.json"), encoding="utf-8"))
        welten = [w["id"] for w in dungeon._base_rules()["welten"] if w["id"] != "eigene"]
        for a in [x["id"] for x in karte["ortsarten"] + karte["raeume"]]:
            self.assertGreaterEqual(sum(a in x["arten"] for x in i["requisiten"]), 3, a)
        for w in welten:
            self.assertTrue(i["wuensche"].get(w), w)
            self.assertGreaterEqual(sum(g["welt"] == w for g in i["gefaehrten"]), 4, w)
        self.assertTrue([x for x in i["knapp"] if x.get("kinder")] and i["gefaehrten_kinder"])
        self.assertEqual([x["stufe"] for x in i["gefaehrte_werte"]], list(range(1, 11)))

    def test_angriffe_zwei_bis_fuenf(self):
        for g in dungeon._base_rules()["gegner"]:
            if "angriffe" in g:
                self.assertIn(g["angriffe"], range(2, 6), g["id"])

    def test_tabellen_und_silben(self):
        r = dungeon._base_rules()
        welten = [w["id"] for w in r["welten"]]
        ids = [t["id"] for t in r["tabellen"]]
        self.assertEqual(len(ids), len(set(ids)))
        for t in r["tabellen"]:
            self.assertIn(t["gruppe"], ("nsc", "orakel"), t["id"])
            for w in welten:
                self.assertGreaterEqual(sum(1 for z in t["zeilen"] if w in (z.get("welten") or welten)), 6, (t["id"], w))
            for z in t["zeilen"]:
                self.assertTrue(set(z.get("welten") or []) <= set(welten), t["id"])
        voelker = {v["id"] for v in r["voelker"]}
        self.assertTrue(voelker <= set(r["namensilben"]), "jedes Volk hat Silben")
        for k, s in r["namensilben"].items():
            self.assertTrue(len(s["anfang"]) >= 6 and len(s["ende"]) >= 6, k)
        self.assertIn("Ironsworn", srd()["lizenz"])

    def test_budget_aus_dem_srd_521(self):
        b = srd()["budget"]
        self.assertEqual(set(b), {"leicht", "mittel", "schwer"})
        for k, v in b.items():
            self.assertEqual(len(v), 10, k)
            self.assertTrue(all(a < c for a, c in zip(v, v[1:])), k)
        self.assertTrue(all(l < m < s for l, m, s in zip(b["leicht"], b["mittel"], b["schwer"])))
        self.assertIn("SRD 5.2.1", srd()["lizenz"])
        for name in ("de/assistent.md", "en/assistant.md"):
            with open(os.path.join(DOCS, name), encoding="utf-8") as f:
                self.assertIn("SRD 5.2.1", f.read(), name)

    def test_kinderton_im_katalog(self):
        r = dungeon._base_rules()
        woerter = next(t for t in r["toene"] if t["id"] == 8)["woerter"]
        for k in ("gegner", "gegenstaende", "zustaende", "voelker", "klassen", "hintergruende"):
            for x in r[k]:
                for f in ("name", "info"):
                    for text in x.get(f) or []:
                        low = " " + text.lower() + " "       # as dungeon.bad_words reads it
                        self.assertEqual([w for w in woerter if w in low], [], (k, x["id"], f))

    def test_ideen_tabellen_und_sagen(self):
        """D&D-Ideen 2, 4, 8, 9, 12 (Dominik 2026-10-25 „1-12“): „ideen“ und „sage“ an den Gegnern prüft
        dungeon_ideen.check_rules; fehlt etwas, sagt es was. Steht „ideen“ in der Datei, hat jeder Gegner eine Sage, und
        kein Satz trägt ein Wort des Kindertons."""
        import dungeon_ideen as ideen
        r = dungeon._base_rules()
        zust = r["zustaende"][0]["id"] if r.get("zustaende") else None
        wert = r["werte"][0]["id"]
        w12 = [{"w": n, "t": [f"Satz {n}", f"Line {n}"]} for n in range(1, 13)]
        good = {"krit": {"hieb": w12}, "patzer": {"zauber": w12},
                "landschaften": [{"id": "weg", "name": ["Unterwegs", "On the road"], "ortsarten": []}],
                "nachtwachen": {"weg": [{"von": 1, "bis": 2, "art": "ueberfall", "t": ["a", "a"]}, {"von": 3, "bis": 20, "art": "ruhig", "t": ["b", "b"]}]},
                "reise_ereignisse": {"weg": [{"ergebnis": "verirrt", "t": ["c", "c"]}]},
                "fragekarten": {"alle": [["Was vermisst du?", "What do you miss?"]]},
                "reise_rollen": [{"id": "wache", "wert": wert, "name": {"alle": ["Wache", "Guard"]}, "gelingt": ["ja", "yes"],
                                  "misslingt": ["nein", "no"], "folge_misslingt": "ueberrascht"}],
                "narben": [{"von": 1, "bis": 1, "t": ["Knie", "Knee"], "folge": {"wert": wert, "minus": 1}}, {"von": 2, "bis": 20, "t": ["Narbe", "Scar"]}],
                "narben_kinder": [["Pflaster", "Plaster"]], "narben_sprueche": [["„{narbe}?“", "\"{narbe}?\""], ["Prost", "Cheers"]]}
        self.assertEqual(ideen.check_rules(dict(r, ideen=good)), [])
        if zust:
            good["krit"]["hieb"] = [dict(w12[0], zustand=zust, zuege=2)] + w12[1:]
            self.assertEqual(ideen.check_rules(dict(r, ideen=good)), [])
        bad = {"krit": {"laser": w12}, "patzer": {"nahkampf": w12[:11]}, "nachtwachen": {"weg": [{"von": 1, "bis": 19, "art": "ruhig", "t": ["a", "a"]}]},
               "narben": [{"von": 1, "bis": 20, "t": ["x", "x"], "folge": {"wert": wert, "minus": 3}}], "narben_sprueche": [["{narbe}", "no"]],
               "landschaften": [{"id": "weg", "name": ["U", "O"], "ortsarten": []}], "reise_rollen": [dict(good["reise_rollen"][0], folge_misslingt="tot")],
               "geheim": []}
        err = " ".join(ideen.check_rules(dict(r, ideen=bad)))
        for teil in ("ideen: nur", "ideen.krit:", "ideen.patzer nahkampf", "ideen.nachtwachen weg", "ideen.narben:", "ideen.narben_sprueche",
                     "ideen.reise_rollen"):
            self.assertIn(teil, err)
        g = dict(r["gegner"][0], sage=["", "x"])
        self.assertIn("sage", " ".join(ideen.check_rules(dict(r, gegner=[g]))))
        self.assertIn("ideen.krit", " ".join(dungeon.check_rules(dict(r, ideen=bad))))   # part of the rules' check
        s = srd()
        if "ideen" in s:                         # the catalog's own tables: every foe with a saying, the children's tone kept
            self.assertEqual([x["id"] for x in s["gegner"] if "sage" not in x], [])
            woerter = next(t for t in r["toene"] if t["id"] == 8)["woerter"]
            texte = re.findall(r'"((?:[^"\\]|\\.)*)"', json.dumps([s["ideen"], [x.get("sage") for x in s["gegner"]]], ensure_ascii=False))
            ids = {z["id"] for z in r["zustaende"]}    # a state's id (blutend) is no spoken text, its name is checked above
            self.assertEqual([t for t in texte if t not in ids and any(w in " " + t.lower() + " " for w in woerter)], [])

    def test_rettung_zustand_halb_und_sg(self):
        s, r = srd(), dungeon._base_rules()
        werte, zids = {w["id"] for w in r["werte"]}, {z["id"] for z in r["zustaende"]}
        zauber = {x["id"]: x for x in s["gegenstaende"] if x.get("art") in ("zauber", "rolle")}
        for x in zauber.values():
            rw = x.get("rettung")
            self.assertTrue(rw is None or isinstance(rw, dict) and set(rw) == {"wert"} and rw["wert"] in werte, x["id"])
            self.assertTrue("zustand" not in x or rw and x["zustand"] in zids, x["id"])
            self.assertTrue("halb" not in x or x["halb"] is True and rw and x.get("schaden_art"), x["id"])
            self.assertTrue(x.get("ziel") != "verbuendeter" or x.get("heilung"), x["id"])
        for k in ("brennende_haende", "donnerwelle", "blitzstrahl", "kaeltekegel", "flammenschlag", "todeswolke"):
            self.assertTrue(zauber[k]["rettung"] and zauber[k]["halb"], k)    # half damage on a success, as in the SRD
        self.assertEqual((zauber["schlaf"]["zustand"], zauber["person_festhalten"]["zustand"], zauber["verstricken"]["rettung"]["wert"]),
                         ("bewusstlos", "gelaehmt", "staerke"))
        self.assertEqual({zauber[k]["ziel"] for k in ("wiederbeleben", "tote_erwecken", "wunden_heilen", "heilendes_wort")}, {"verbuendeter"})
        for g in s["gegner"]:
            self.assertTrue(isinstance(g.get("sg"), int) and not isinstance(g["sg"], bool) and 5 <= g["sg"] <= 30, g["id"])
        self.assertEqual(next(g for g in s["gegner"] if g["id"] == "wache")["schaden_art"], "stich")

    def test_nacht_gegner_je_welt_und_stufe(self):
        s, r = srd(), dungeon._base_rules()
        self.assertEqual([g["id"] for g in s["gegner"] if g.get("nacht", True) is not True], [])
        nacht = [g for g in s["gegner"] if g.get("nacht")]
        for w in [x["id"] for x in r["welten"]]:
            for stufe in (1, 2, 3):
                b = kampf.BUDGET[stufe - 1] * kampf.group_factor(1) * kampf.SCHWER    # one hero, the smallest budget at the table
                n = [g["id"] for g in nacht if kampf.plays_in(r, g, w) and 0 < g["ep"] <= b]
                self.assertGreaterEqual(len(n), 5, f"{w} Stufe {stufe}: {n}")
        self.assertLessEqual(set(range(6)), {int(g["stufe"]) for g in nacht})

    def test_runen_und_runenwoerter(self):
        import dungeon_runen as runen
        s, r = srd(), dungeon._base_rules()
        preise = {"uruz": 20, "ehwaz": 25, "ansuz": 30, "fehu": 50, "kenaz": 120, "isa": 150, "thurisaz": 150, "nauthiz": 180,
                  "jera": 300, "berkano": 500, "sowilo": 500, "algiz": 900, "tiwaz": 1500}
        self.assertEqual({x["id"]: x["preis"] for x in s["runen"]}, preise)
        self.assertEqual(sorted(x["rang"] for x in s["runen"]), list(range(1, 14)))
        self.assertEqual(len(s["runenwoerter"]), 7)
        self.assertEqual(runen.check_rules(r), [])
        sturm = next(x for x in r["runenwoerter"] if x["id"] == "sturmlied")
        self.assertEqual((sturm["runen"], sturm["sockel"], sturm["ort"]), (["thurisaz", "ehwaz", "uruz"], 3, "waffe"))
        uruz = next(x for x in r["runen"] if x["id"] == "uruz")
        for bad in (dict(uruz, ruestung={"treffer": 1}), dict(uruz, ruestung={"effekt": "feuer"}), dict(uruz, waffe={"magie": 1}),
                    dict(uruz, waffe={"werte": ["staerke"]}), dict(uruz, rang=14), {k: v for k, v in uruz.items() if k != "schild"}):
            self.assertNotEqual(runen.check_rules(dict(r, runen=[bad] + [x for x in r["runen"] if x["id"] != "uruz"])), [], bad)
        for bad in (dict(sturm, sockel=2), dict(sturm, runen=["thurisaz", "ehwaz", "gibtsnicht"]), dict(sturm, ort="haende"),
                    dict(sturm, ort="nebenhand", zusatz={"schaden": 1})):
            self.assertNotEqual(runen.check_rules(dict(r, runenwoerter=[bad])), [], bad)
        algiz = dict(next(x for x in r["runenwoerter"] if x["id"] == "glut"), runen=["algiz", "uruz"])   # Algiz never in a weapon
        self.assertNotEqual(runen.check_rules(dict(r, runenwoerter=[algiz])), [])
        self.assertIn("runen", " ".join(dungeon.check_rules(dict(r, runen=[dict(uruz, rang=0)]))))   # part of the rules' check
        woerter = next(t for t in r["toene"] if t["id"] == 8)["woerter"]
        namen = [n for x in s["runen"] + s["runenwoerter"] for n in x["name"] + x.get("sinn", [])]
        self.assertEqual([n for n in namen if any(w in " " + n.lower() + " " for w in woerter)], [])

    def test_berufe_mit_formen_und_aussehen_nur_aeusseres(self):
        import dungeon_tabellen as tabellen
        s, r = srd(), dungeon._base_rules()
        t = {x["id"]: x for x in s["tabellen"]}
        self.assertEqual([z["t"][0] for z in t["nsc_beruf"]["zeilen"] if z["t"][0] not in (z.get("m"), z.get("w"))], [])
        bergmann = next(z for z in t["nsc_beruf"]["zeilen"] if z["t"][0] == "Bergmann")
        self.assertEqual((bergmann["m"], bergmann["w"]), ("Bergmann", "Bergfrau"))
        self.assertEqual([z["t"][0] for z in t["nsc_beruf"]["zeilen"] if re.search(r"\bKI\b|roboter|droide", z["t"][0], re.I)], [])   # a person, no machine
        aussehen = {z["t"][0] for z in t["nsc_aussehen"]["zeilen"]}
        self.assertEqual(aussehen & {z["t"][0] for z in t["nsc_art"]["zeilen"]}, set())
        self.assertNotIn("wirkt zerstreut", aussehen)
        self.assertIn("zerstreut", {z["t"][0] for z in t["nsc_art"]["zeilen"]})
        self.assertEqual(tabellen.check_rules(r), [])
        tab = lambda tid, zeilen: dict(r, tabellen=[dict(tabellen.table(r, tid), zeilen=zeilen)])   # noqa: E731
        beruf = tabellen.table(r, "nsc_beruf")["zeilen"]
        self.assertIn("\"m\" und \"w\"", " ".join(tabellen.check_rules(tab("nsc_beruf", [{"t": ["Wirt", "innkeeper"]}] + beruf))))
        self.assertNotEqual(tabellen.check_rules(tab("nsc_art", [{"t": ["still", "quiet"], "m": "x", "w": "y"}] * 6)), [])
        self.assertIn("nsc_art", " ".join(tabellen.check_rules(tab("nsc_aussehen", [{"t": ["wirkt zerstreut", "seems distracted"]}] * 6))))

    def test_wesen_und_gefaehrten(self):
        import dungeon_bestiarium as best
        import dungeon_erzaehler as erz
        import dungeon_ideen as ideen
        import dungeon_tabellen as tabellen
        s, r = srd(), dungeon._base_rules()
        self.assertEqual([g["id"] for g in s["gegner"] if g.get("wesen") not in best.WESEN], [])
        by = {g["id"]: best.wesen(g) for g in s["gegner"]}
        self.assertEqual({by[i] for i in ("seeraeuber", "dorfbewohner", "spaeher", "akolyth", "bandit")}, {"mensch"})
        self.assertEqual({by[i] for i in ("goblinkrieger", "werbaer", "meervolk", "grimlock", "dunkelelf")}, {"humanoid"})
        self.assertEqual((by["zombie"], by["troll"], by["kampfsynth"], by["wolf"], by["dryade"]), ("untot", "riese", "konstrukt", "tier", "fee"))
        self.assertTrue(all(g.get("friedlich", True) is True for g in s["gegner"] if "friedlich" in g))
        self.assertTrue(best.friedlich(next(g for g in s["gegner"] if g["id"] == "dorfbewohner")))
        self.assertEqual(best.check_rules(r), [])
        g0 = r["gegner"][0]
        self.assertTrue(best.check_rules(dict(r, gegner=[dict(g0, wesen="gott")])))
        self.assertTrue(best.check_rules(dict(r, gegner=[dict(g0, friedlich="ja")])))
        self.assertIn("wesen", " ".join(dungeon.check_rules(dict(r, gegner=[dict(g0, wesen="gott")] + r["gegner"][1:]))))
        eigen = {k: v for k, v in g0.items() if k != "wesen"}      # an admin's own foe may leave it out
        self.assertEqual((best.check_rules(dict(r, gegner=[eigen])), best.wesen(eigen)), ([], ""))
        gef = s["ideen"]["gefaehrten"] + s["ideen"]["gefaehrten_kinder"]
        self.assertEqual([x["id"] for x in gef if x.get("geschlecht") not in dungeon.GESCHLECHT or x.get("alter") not in ideen.ALTER
                          or x.get("art") not in ideen.GEF_ART], [])
        by = {x["id"]: (x["geschlecht"], x["alter"], x["art"]) for x in gef}
        self.assertEqual((by["grete"], by["brunhild"], by["k7"][2], by["wuschel"][2]), (("weiblich", "mittel", "mensch"), ("weiblich", "alt", "mensch"), "maschine", "tier"))
        self.assertNotIn("kind", ideen.ALTER)
        i = dict(r["ideen"], gefaehrten=[dict(r["ideen"]["gefaehrten"][0], alter="kind")] + r["ideen"]["gefaehrten"][1:])
        self.assertIn("ideen.gefaehrten:", " ".join(ideen.check_rules(dict(r, ideen=i))))
        teil = {"nsc_haar": "haar", "nsc_augen": "augen", "nsc_bart": "bart"}
        t = {x["id"]: x for x in s["tabellen"]}
        self.assertEqual(set(teil), set(tabellen.FARBE))
        self.assertIn("kein Bart", [z["t"][0] for z in t["nsc_bart"]["zeilen"]])
        self.assertGreaterEqual(len(t["nsc_statur"]["zeilen"]), 8)
        for tid, k in teil.items():
            for z in t[tid]["zeilen"]:
                want = {k: z["farbe"]} if "farbe" in z else {}
                self.assertEqual((erz._koerper(z["t"][0]), erz._koerper(z["t"][1])), (want, want), z["t"])
        self.assertTrue(any("farbe" in z for tid in teil for z in t[tid]["zeilen"]))
        statur = dict(t["nsc_statur"], zeilen=[{"t": ["hager", "gaunt"], "farbe": "rot"}] * 3)
        self.assertTrue(tabellen.check_rules(dict(r, tabellen=[statur])))
        haar = dict(t["nsc_haar"], zeilen=[{"t": ["rotes Haar", "red hair"], "farbe": "Rot!"}] * 3)
        self.assertTrue(tabellen.check_rules(dict(r, tabellen=[haar])))

    def test_kampf_ep(self):
        import dungeon_bestiarium as best
        s, r = srd(), dungeon._base_rules()
        by = {g["id"]: g for g in s["gegner"]}
        mit = [g for g in s["gegner"] if "ep_kampf" in g]
        self.assertGreaterEqual(len(mit), 240)
        self.assertEqual([g["id"] for g in mit if g.get("friedlich")], [])
        self.assertEqual((by["schlurfhaufen"]["ep_kampf"], by["erzmagier"]["ep_kampf"], by["ork_krieger"]["ep_kampf"]), (6300, 2800, 100))
        self.assertEqual((best.ep_kampf(by["schlurfhaufen"]), best.ep_kampf(by["dorfbewohner"])), (6300, by["dorfbewohner"]["ep"]))
        self.assertEqual(best.check_rules(r), [])
        g0 = dict(by["goblin"])
        for bad in (g0["ep"] * 5, g0["ep"] // 5, "64", True, 64.5):
            self.assertTrue(best.check_rules(dict(r, gegner=[dict(g0, ep_kampf=bad)])), bad)
        self.assertEqual(best.check_rules(dict(r, gegner=[{k: v for k, v in g0.items() if k != "ep_kampf"}])), [])

    def test_englische_namen_wie_im_srd(self):
        by = {g["id"]: g["name"][1] for g in srd()["gegner"]}
        self.assertEqual((by["stirge"], by["belebte_ruestung"], by["piranhaschwarm"], by["warg"]), ("Stirge", "Animated armor", "Swarm of piranhas", "Warg"))
        self.assertEqual([i for i, n in by.items() if re.search(r"(?i)armour|giant mosquito|quipper", n)], [])


if __name__ == "__main__":
    unittest.main()
