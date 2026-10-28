"""KI-Dungeon-Master: the admin's tab „Regeln“ (dungeon_regelseite.py, Dominik 2026-10-24 „das besarium zu sehen zu
bearbeten gegenstände etc.“, „einzelne neue bilder erzeugen“, „zu stark nur hinweis“).

- Only the admin: a profile gets nothing, an unknown part is refused.
- A part lists every entry with where it comes from and, for foes and items, the balance mark and the picture.
- „Ändern“ writes the whole entry into the own rules and passes check_rules like the JSON editor (a broken entry is
  refused with its errors and nothing is written); „zu stark“ comes back as a hint and is saved all the same.
- „Ausblenden“ takes the entry out of the game but keeps it in the list; „Zurück auf mitgeliefert“ takes the own
  entry out again (an empty part leaves the own rules).
- „Malen“ of a missing picture puts it in place; „Nochmal malen“ paints a candidate next to the one in use, the admin
  keeps the new or the old one; the day limit and the switch hold; a candidate nobody settles goes after a day.
- A foe's prompt is fixed by the panel; Live only counts.

No wall clock: the picture module's clock is set by the tests (test_dungeon_dingbild.Base).
"""
import asyncio
import os
import time
import unittest

from tests.test_dungeon_dingbild import ADMIN, Base
import dungeon  # noqa: E402
import dungeon_dingbild as db  # noqa: E402
import dungeon_regelseite as rs  # noqa: E402
from tests import helpers  # noqa: E402

K = "/api/admin/dungeon/katalog/"


class Page(Base):
    def rows(self, teil):
        r = ADMIN.get(K + teil)
        self.assertEqual(r.status_code, 200, r.text)
        return {str(x["id"]): x for x in r.json()["zeilen"]}, r.json()

    def test_only_the_admin_and_known_parts(self):
        self.assertIn(self.c.get(K + "gegner").status_code, (401, 403))
        self.assertIn(self.c.post(K + "gegner", json={"was": "aus", "id": "goblin"}).status_code, (401, 403))
        self.assertIn(self.c.post(K + "gegner/bild", json={"was": "malen", "id": "goblin"}).status_code, (401, 403))
        self.assertEqual(ADMIN.get(K + "geheim").status_code, 404)
        self.assertEqual(ADMIN.post(K + "toene/bild", json={"was": "malen", "id": "12"}).status_code, 404)   # a part without pictures
        self.assertEqual(ADMIN.get("/api/admin/dungeon/bild/..%2Fdungeon.json").status_code, 404)

    def test_every_part_lists_its_entries(self):
        r = dungeon.rules()
        for teil in rs.TEILE:
            rows, d = self.rows(teil)
            self.assertEqual(len(rows), len(r[teil]), teil)
            for x in rows.values():
                self.assertIn(x["stand"], ("grund", "srd"), teil)
                self.assertIsInstance(x["zeile"], str)
            self.assertEqual(set(d["eintraege"]), set(rows))
        foes, _ = self.rows("gegner")
        g = foes["goblin"]
        self.assertEqual((g["bild"], g["neu"], g["stufe"]), ("", "", 0.25))
        self.assertIn(g["marke"]["marke"], ("schwach", "ok", "stark", "zu_stark"))
        self.assertIn("Stufe ¼", g["zeile"])
        items, _ = self.rows("gegenstaende")
        self.assertTrue(all("marke" in x and "bild" in x for x in items.values()))

    def test_the_people_of_the_catalog(self):
        """Personen-Katalog 1 (Dominik 2026-10-26 „1-5“): „Personen (NSC)“ only for the admin and only while the switch
        is on; the admin adds a person (new id), changes it and deletes it; a wrong field, a word of „nie“ or a name the
        world has already is refused with its errors and nothing is written; wish and secret only here."""
        import dungeon_personen as pers
        helpers.keep_chat(self, "dungeon_nsc", "dungeon_personen")
        if os.path.exists(pers.FILE):
            os.remove(pers.FILE)
        self.addCleanup(lambda: os.path.exists(pers.FILE) and os.remove(pers.FILE))
        self.assertIn(self.c.get(K + "personen").status_code, (401, 403))
        x = ADMIN.get(K + "personen")
        self.assertEqual((x.status_code, x.json()["detail"]), (404, "personen aus"))
        self.assertEqual(ADMIN.post(K + "personen", json={"was": "setzen", "id": "oskar"}).json()["detail"], "personen aus")
        self.assertFalse(ADMIN.get("/api/admin/dungeon").json()["personen_an"])
        helpers.set_config(dungeon_nsc=True, dungeon_personen=True)
        self.assertTrue(ADMIN.get("/api/admin/dungeon").json()["personen_an"])
        self.assertIn(self.c.post(K + "personen", json={"was": "setzen", "id": "oskar"}).status_code, (401, 403))
        d = ADMIN.get(K + "personen").json()
        self.assertEqual((d["zeilen"], d["neu"]), ([], True))
        e = {"id": "oskar", "name": "Oskar", "welt": "fantasy", "rolle": "Wirt", "wesen": {"mut": 2},
             "karte": {"beruf": ["Wirt", "Innkeeper"], "geheimnis": ["Schuldet der Gilde Gold", "Owes the guild gold"]}}
        x = ADMIN.post(K + "personen", json={"was": "setzen", "id": "oskar", "eintrag": e})
        self.assertEqual(x.status_code, 200, x.text)
        (row,) = x.json()["zeilen"]
        self.assertEqual((row["name"], row["stand"], row["zeile"]), ("Oskar", "eigen", "Wirt · Fantasy · 0× getroffen"))
        self.assertIn(["Geheimnis", "Schuldet der Gilde Gold"], row["werte"])            # the admin sees wish and secret
        self.assertIn(["Wesen", "mutig"], row["werte"])
        en = ADMIN.get(K + "personen?lang=en").json()["zeilen"][0]
        self.assertEqual(en["zeile"], "Innkeeper · Fantasy · met 0×")
        bad = [dict(e, id="oskar2"),                                                     # the world has Oskar
               dict(e, id="o2", name="O"), dict(e, id="o3", welt="mond"), dict(e, id="o4", wesen={"mut": 9}),
               dict(e, id="o5", karte={"farbe": ["rot", "red"]}), dict(e, id="o6", rolle="nackt am Tresen")]
        for b in bad:
            x = ADMIN.post(K + "personen", json={"was": "setzen", "id": b["id"], "eintrag": b})
            self.assertEqual(x.status_code, 422, b)
            self.assertTrue(x.json()["detail"], b)
        self.assertEqual(ADMIN.post(K + "personen", json={"was": "setzen", "id": "Böse!", "eintrag": dict(e, id="Böse!")}).status_code, 422)
        self.assertEqual(set(pers.load()), {"oskar"})                                     # nothing else written
        x = ADMIN.post(K + "personen", json={"was": "setzen", "id": "oskar", "eintrag": dict(e, rolle="Alter Wirt")})
        self.assertEqual(x.status_code, 200, x.text)                                     # its own name again is fine
        self.assertEqual(pers.load()["oskar"]["rolle"], "Alter Wirt")
        self.assertEqual(ADMIN.post(K + "personen", json={"was": "weg", "id": "oskar"}).status_code, 422)
        x = ADMIN.post(K + "personen", json={"was": "zurueck", "id": "oskar"})
        self.assertEqual((x.status_code, x.json()["zeilen"]), (200, []))
        self.assertEqual(ADMIN.post(K + "personen", json={"was": "zurueck", "id": "oskar"}).status_code, 404)
        self.assertGreaterEqual((pers.for_live()["geaendert"], pers.for_live()["geloescht"]), (2, 1))

    def test_a_persons_voice(self):
        """Dominik 2026-10-27 „stimmen verändern, die genutzt werden wenn diese etwas sagen“: every person shows its voice
        (kept, or by its name); „Stimme speichern“ sets one value of each fixed list and nothing else of the person (a
        person from a round stays one), „Nach dem Namen“ gives it back; a wrong voice is refused and nothing is written;
        „▶ Probe“ speaks the fixed sentence in the panel's own description of the choice, only for the admin and only
        while the catalog is on; a round that meets the person speaks with that voice."""
        import contextlib
        import io
        import itertools
        from unittest import mock
        import dungeon_personen as pers
        import dungeon_stimmen as st
        helpers.keep_chat(self, "dungeon_nsc", "dungeon_personen")
        if os.path.exists(pers.FILE):
            os.remove(pers.FILE)
        self.addCleanup(lambda: os.path.exists(pers.FILE) and os.remove(pers.FILE))
        P = "/api/admin/dungeon/personen/probe"
        v = {"alter": "alt", "geschlecht": "weiblich", "klang": "rau", "wesen": "weise", "tempo": "langsam"}
        self.assertEqual(ADMIN.post(P, json={"stimme": v}).status_code, 404)              # the catalog off
        helpers.set_config(dungeon_nsc=True, dungeon_personen=True)
        pers._save({"silas": {"id": "silas", "name": "Silas", "welt": "fantasy", "karte": {"beruf": ["Mystikerin", "Mystic"]},
                              "wesen": {}, "rolle": "", "ziel": "", "stimme": {}, "haltung": {}, "treffen": 1, "made": 1, "t": 1, "stand": "runde"}})
        rows, d = self.rows("personen")
        self.assertEqual([m["k"] for m in d["stimmwahl"]], list(st.MERKMALE))
        self.assertTrue(all(len(m["werte"]) == len(st.data()["npc"][m["k"]]) for m in d["stimmwahl"]))
        by_name = st.of_name("Silas")
        self.assertIn(["Stimme", st.words(by_name, 0) + " (nach dem Namen)"], rows["silas"]["werte"])
        self.assertEqual((d["eintraege"]["silas"]["stimme"], d["eintraege"]["silas"]["stimme_jetzt"]), ({}, by_name))
        for bad in ({"alter": "alt"}, dict(v, klang="laut"), dict(v, extra="x"), "rau", [v]):
            x = ADMIN.post(K + "personen", json={"was": "stimme", "id": "silas", "eintrag": {"id": "silas", "stimme": bad}})
            self.assertEqual(x.status_code, 422, bad)
        self.assertEqual(pers.load()["silas"]["stimme"], {})                             # nothing written
        self.assertEqual(ADMIN.post(K + "personen", json={"was": "stimme", "id": "keiner", "eintrag": {"stimme": v}}).status_code, 404)
        self.assertIn(self.c.post(K + "personen", json={"was": "stimme", "id": "silas", "eintrag": {"stimme": v}}).status_code, (401, 403))
        x = ADMIN.post(K + "personen", json={"was": "stimme", "id": "silas", "eintrag": {"id": "silas", "stimme": v}})
        self.assertEqual(x.status_code, 200, x.text)
        p = pers.load()["silas"]
        self.assertEqual((p["stimme"], p["stand"], p["karte"]), (v, "runde", {"beruf": ["Mystikerin", "Mystic"]}))
        (row,) = x.json()["zeilen"]
        self.assertIn(["Stimme", "alt, weiblich, rau, weise, langsam"], row["werte"])
        en = ADMIN.get(K + "personen?lang=en").json()["zeilen"][0]
        self.assertIn(["Voice", "old, female, rough, wise, slow"], en["werte"])
        # a round that meets the person speaks with the voice (adopt puts it into the round's npc_stimmen)
        rd = {"npc_stimmen": {"silas": dict(p["stimme"])}}
        self.assertEqual(st.npc(rd, "Silas"), "An old woman, rough voice, wise and calm, slow speech")
        self.assertTrue(st.weiblich(rd, "Silas"))
        # the JSON of „Ändern“ carries the voice too, checked the same way
        e = dict(d["eintraege"]["silas"], stimme=dict(v, tempo="eilig"))
        e.pop("stimme_jetzt")
        self.assertEqual(ADMIN.post(K + "personen", json={"was": "setzen", "id": "silas", "eintrag": e}).status_code, 422)
        x = ADMIN.post(K + "personen", json={"was": "stimme", "id": "silas", "eintrag": {"id": "silas", "stimme": {}}})
        self.assertEqual(pers.load()["silas"]["stimme"], {})                             # „Nach dem Namen“
        # „▶ Probe“: the panel's own words, the female fixed voice without VoiceDesign
        self.assertIn(self.c.post(P, json={"stimme": v}).status_code, (401, 403))
        self.assertEqual(ADMIN.post(P, json={"stimme": {}}).status_code, 400)
        self.assertEqual(ADMIN.post(P, json={"stimme": dict(v, wesen="boese")}).status_code, 400)
        said = []

        async def probe(voice, lang, klang="", fest=""):
            said.append((voice, lang, klang, fest))
            return b"RIFF", False
        with mock.patch("dungeon.probe", probe), contextlib.redirect_stdout(io.StringIO()) as out:
            x = ADMIN.post(P, json={"stimme": v, "lang": "en"})
        self.assertEqual((x.status_code, x.headers["content-type"]), (200, "audio/wav"))
        voices = dungeon.voices(dungeon.rules())
        self.assertEqual(said, [("", "en", "An old woman, rough voice, wise and calm, slow speech", voices["npc_w"])])
        self.assertIn("dungeon: personen | probe", out.getvalue())
        n = st.data()["npc"]
        for t in itertools.product(*(n[k] for k in st.MERKMALE)):                         # every choice fits the speech output
            self.assertRegex(st.describe(dict(zip(st.MERKMALE, t))), dungeon.KLANG)
            self.assertLessEqual(len(st.describe(dict(zip(st.MERKMALE, t)))), 80)
        self.assertGreaterEqual(pers.for_live()["stimme"], 2)
        # Dominik 2026-10-27 „stimmprobe nahm bei jedem charakter das standard model“: the catalog and its sample look at
        # the speech output afresh while VoiceDesign counts as not running (never only after a round's view), and say so
        import admin
        for up in (False, True):
            async def tts_voices():
                return {"voices": ["Ryan"], "voicedesign": up}
            dungeon._stimmen.update(design=False, t=time.time() - dungeon.DESIGN_NEU_S)
            with mock.patch.object(admin, "tts_voices", tts_voices):
                self.assertIs(ADMIN.get(K + "personen").json()["stimme_design"], up)
            self.assertIs(dungeon._stimmen["design"], up)
        dungeon._stimmen.update(design=False, t=time.time())                              # just asked: not again
        with mock.patch.object(admin, "tts_voices", tts_voices):
            self.assertIs(ADMIN.get(K + "personen").json()["stimme_design"], False)

    def test_a_table_shows_every_row_and_its_sign(self):
        """Dominik 2026-10-25 „ich sehe gar nicht die tabellen“: the detail holds every row with its number and the
        worlds of a row that counts only in some, the die is the number of rows, every table has a sign."""
        r = dungeon.rules()
        rows, _ = self.rows("tabellen")
        for x in r["tabellen"]:
            row = rows[x["id"]]
            self.assertTrue(row["zeichen"] and row["zeichen"] != "·", x["id"])
            self.assertEqual([z["n"] for z in row["tafel"]], list(range(1, len(x["zeilen"]) + 1)))
            self.assertEqual([z["t"] for z in row["tafel"]], [y["t"][0] for y in x["zeilen"]])
            self.assertIn(["Würfel", f"W{len(x['zeilen'])}"], [[a, v.split(",")[0]] for a, v in row["werte"]])
        wn = {w["id"]: w["name"][0] for w in r["welten"]}
        ort = next(x for x in r["tabellen"] if any(y.get("welten") for y in x["zeilen"]))
        i, y = next((i, y) for i, y in enumerate(ort["zeilen"]) if y.get("welten"))
        self.assertEqual(rows[ort["id"]]["tafel"][i]["w"], ", ".join(wn[w] for w in y["welten"]))
        en = {str(x["id"]): x for x in ADMIN.get(K + "tabellen?lang=en").json()["zeilen"]}
        self.assertEqual(en[ort["id"]]["tafel"][0]["t"], ort["zeilen"][0]["t"][1])

    def test_every_foe_and_item_shows_what_it_does(self):
        """Dominik 2026-10-24 „sollten immer auch Werte anzeigen wie stark, was sie bewirken“: every foe and item
        has its values in the row and a list of what it does in the detail, in fixed words from the catalog."""
        items, _ = self.rows("gegenstaende")
        for x in items.values():
            labels = [a for a, _ in x["werte"]]
            self.assertIn("Art", labels, x["id"])
            self.assertIn("Gewicht", labels, x["id"])
        kw = {a: v for a, v in items["keule"]["werte"]}
        self.assertEqual(kw["Zählt auf"], "Stärke")
        wirkung = [v for a, v in items["keule"]["werte"] if a == "Wirkung"]      # one row per line of the item
        self.assertTrue(any("Schaden 1W4" in v for v in wirkung), wirkung)
        self.assertTrue(any(v.startswith("Wucht · leicht") for v in wirkung), wirkung)   # Kampf Teil 2: kind and properties
        self.assertTrue(items["keule"]["zeile"].startswith("Waffe · "))
        fb = items["feuerball"]
        self.assertTrue(any(a == "Wirkung" and "Intelligenz +4" in v for a, v in fb["werte"]), fb["werte"])
        self.assertIn("Segen INT +4", fb["zeile"])
        foes, _ = self.rows("gegner")
        gw = {a: v for a, v in foes["goblin"]["werte"]}
        self.assertEqual((gw["Leben"], gw["Stufe"]), ("7", "¼"))
        self.assertIn("im Schnitt 5.5", gw["Schaden"])
        self.assertIn("GES 14", gw["Werte"])
        self.assertIn("50 EP", foes["goblin"]["zeile"])
        poison = next(x for x in foes.values() if any(a == "Kann bewirken" for a, _ in x["werte"]))
        self.assertTrue(poison)
        en = {a: v for a, v in ADMIN.get(K + "gegner?lang=en").json()["zeilen"][0]["werte"]}
        self.assertIn("Life", en)

    def test_change_hint_hide_and_back(self):
        e = dict(dungeon._by(dungeon.rules(), "gegner")["goblin"], leben=120, angriff=12)
        r = ADMIN.post(K + "gegner", json={"was": "setzen", "id": "goblin", "eintrag": e})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["hinweis"]["marke"], "zu_stark")      # only a hint: saved all the same
        rows = {x["id"]: x for x in r.json()["zeilen"]}
        self.assertEqual((rows["goblin"]["stand"], rows["goblin"]["marke"]["marke"]), ("geaendert", "zu_stark"))
        self.assertEqual(dungeon._by(dungeon.rules(), "gegner")["goblin"]["leben"], 120)
        bad = dict(e, leben="viel")
        before = open(dungeon.EIGENE).read()
        r = ADMIN.post(K + "gegner", json={"was": "setzen", "id": "goblin", "eintrag": bad})
        self.assertEqual(r.status_code, 422)
        self.assertIsInstance(r.json()["detail"], list)
        self.assertEqual(open(dungeon.EIGENE).read(), before)
        self.assertEqual(ADMIN.post(K + "gegner", json={"was": "setzen", "id": "ork", "eintrag": e}).status_code, 422)
        self.assertEqual(ADMIN.post(K + "gegner", json={"was": "weg", "id": "goblin"}).status_code, 422)
        r = ADMIN.post(K + "gegner", json={"was": "aus", "id": "goblin"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual({x["id"]: x for x in r.json()["zeilen"]}["goblin"]["stand"], "aus")
        self.assertNotIn("goblin", dungeon._by(dungeon.rules(), "gegner"))
        self.assertEqual(rs.counts()["aus"], 1)
        r = ADMIN.post(K + "gegner", json={"was": "zurueck", "id": "goblin"})
        self.assertEqual({x["id"]: x for x in r.json()["zeilen"]}["goblin"]["stand"], "srd")
        self.assertNotIn("gegner", dungeon.own_rules())

    def test_own_copy_and_a_tone_by_number(self):
        e = dict(dungeon._by(dungeon.rules(), "gegenstaende")["heiltrank"], id="heiltrank_2")
        r = ADMIN.post(K + "gegenstaende", json={"was": "setzen", "id": "heiltrank_2", "eintrag": e})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual({x["id"]: x for x in r.json()["zeilen"]}["heiltrank_2"]["stand"], "eigen")
        self.assertEqual(rs.counts()["eigene"], 1)
        tone = dungeon.rules()["toene"][0]
        r = ADMIN.post(K + "toene", json={"was": "aus", "id": str(tone["id"])})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(dungeon.own_rules()["toene"], [{"id": tone["id"], "aus": True}])

    def test_runes_with_their_rules_and_switch(self):
        """Dominik 2026-10-28 „die runen sehe ich die auch unter den regeln wie alles andere?“: runes and runewords
        are parts of the page, with the fixed rules around them (sockets, caps) and the switch with its way."""
        helpers.keep_chat(self, "dungeon_runen")
        helpers.set_config(dungeon_runen=False)
        rows, d = self.rows("runen")
        self.assertEqual(len(rows), 13)
        self.assertEqual((rows["uruz"]["stand"], rows["uruz"]["zeichen"]), ("srd", "ᚱ"))
        self.assertIn("Rang 1", rows["uruz"]["zeile"])
        w = dict(rows["uruz"]["werte"])
        self.assertEqual(w["In einer Waffe"], "+1 Schaden")
        self.assertIn("Krämer", w["Fällt"])
        k = d["kasten"]
        self.assertEqual((k["schalter"]["name"], k["schalter"]["an"]), ("Runen und Sockel", False))
        self.assertEqual(k["schalter"]["weg"], "Funktionen → KI-Dungeon-Master → Runen und Sockel")
        z = dict(k["zeilen"])
        self.assertIn(f"Treffer höchstens +{rs.runen.TREFFER_MAX}", z["Obergrenzen"])
        self.assertIn("Waffe 6,5", z["Obergrenzen"])
        self.assertIn(f"zu {rs.runen.SOCKEL_FUND} von 100", z["Sockel"])
        helpers.set_config(dungeon_runen=True)
        self.assertIs(self.rows("runen")[1]["kasten"]["schalter"]["an"], True)
        words, d = self.rows("runenwoerter")
        self.assertEqual(len(words), 7)
        self.assertIn("Kenaz + Uruz", words["glut"]["zeile"])
        self.assertIn("noch nicht", dict(d["kasten"]["zeilen"])["Am Tisch"])
        en = ADMIN.get(K + "runen?lang=en").json()
        self.assertEqual(en["kasten"]["schalter"]["weg"], "Features → AI Dungeon Master → Runes and sockets")
        # a rune changed by its id (merged like every list), taken back; hiding one leaves a gap in the ranks: refused
        e = dict(dungeon._by(dungeon.rules(), "runen")["uruz"], preis=30)
        r = ADMIN.post(K + "runen", json={"was": "setzen", "id": "uruz", "eintrag": e})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual({x["id"]: x for x in r.json()["zeilen"]}["uruz"]["stand"], "geaendert")
        self.assertEqual((len(dungeon.rules()["runen"]), dungeon._by(dungeon.rules(), "runen")["uruz"]["preis"]), (13, 30))
        self.assertEqual(ADMIN.post(K + "runen", json={"was": "aus", "id": "uruz"}).status_code, 422)
        ADMIN.post(K + "runen", json={"was": "zurueck", "id": "uruz"})
        self.assertNotIn("runen", dungeon.own_rules())

    def test_effects_the_map_and_the_stall_events(self):
        """The rest of the catalog's lists (Dominik 2026-10-28 „fehlt sonst noch etwas unter den regeln?“): effects,
        the map's tables, the stall events; an entry without a name is named by its sentence."""
        r = dungeon.rules()
        eff, _ = self.rows("effekte")
        self.assertEqual(eff["feuer"]["name"], "Treffer brennen")
        self.assertIn("Feuer", eff["feuer"]["zeile"])
        self.assertEqual(dict(eff["riese"]["werte"])["Hebt"], "Stärke +2")
        traps, _ = self.rows("fallen")
        t = r["fallen"][0]
        self.assertIn(f"SG {t['schwer']}", traps[t["id"]]["zeile"])
        riddles, _ = self.rows("raetsel")
        q = r["raetsel"][0]
        self.assertEqual(dict(riddles[q["id"]]["werte"])["Lösung"], " / ".join(q["loesung"][0]))
        for teil in ("ortsarten", "raeume", "begegnungen"):
            rows, _ = self.rows(teil)
            self.assertTrue(all(x["zeile"] and x["zeichen"] for x in rows.values()), teil)
        stall, d = self.rows("stillstand")
        self.assertEqual(d["kasten"]["schalter"]["weg"], "Funktionen → KI-Dungeon-Master → Spieler anleiten")
        self.assertTrue(stall["bote"]["name"].startswith("Ein Bote"))
        self.assertLessEqual(len(stall["bote"]["name"]), rs.NAME_KURZ + 2)
        self.assertEqual(dict(stall["bote"]["werte"])["Am Kindertisch"], "ja")
        res = ADMIN.post(K + "stillstand", json={"was": "aus", "id": "bote"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual({x["id"]: x for x in res.json()["zeilen"]}["bote"]["stand"], "aus")
        self.assertNotIn("bote", [x["id"] for x in dungeon.rules()["stillstand"]])
        self.assertEqual(len(dungeon.rules()["stillstand"]), len(r["stillstand"]) - 1)
        ADMIN.post(K + "stillstand", json={"was": "zurueck", "id": "bote"})
        self.assertEqual(len(dungeon.rules()["stillstand"]), len(r["stillstand"]))

    def test_the_numbers_only_to_look_at(self):
        """„Zahlen und Tabellen“: the fixed numbers the panel uses, from the rules and the code, never changed here."""
        r = dungeon.rules()
        res = ADMIN.get(K + rs.ZAHLEN)
        self.assertEqual(res.status_code, 200, res.text)
        d = res.json()
        self.assertIs(d["fest"], True)
        rows = {x["id"]: x for x in d["zeilen"]}
        self.assertEqual(set(rows), {"stufen", "erfahrung", "fund", "gold", "preise", "sg", "budget", "grenzen"})
        st = rows["stufen"]["tabelle"]
        self.assertEqual([z[1] for z in st["zeilen"]], [str(x) for x in r["stufen_ep"]])
        fund = rows["fund"]["tabelle"]
        self.assertEqual(len(fund["kopf"]), len(r["seltenheit"]))
        self.assertEqual(fund["zeilen"][0][2], "nie")              # „rar“ never at level 1
        self.assertEqual(rows["budget"]["tabelle"]["zeilen"][0][1], str(rs.kampf.BUDGET[0]))
        self.assertEqual(dict(rows["sg"]["werte"])["mittel"], f"SG {dungeon.PROBE_SG['mittel']}")
        self.assertEqual(dict(rows["erfahrung"]["werte"])["gelungene Probe"], str(r["ep"]["probe"] * dungeon.PROBE_EP_SG // 10))
        self.assertEqual(ADMIN.post(K + rs.ZAHLEN, json={"was": "aus", "id": "gold"}).status_code, 404)
        self.assertIn(self.c.get(K + rs.ZAHLEN).status_code, (401, 403))
        self.assertEqual(ADMIN.get(K + "zahlen?lang=en").json()["zeilen"][0]["name"], "Levels and experience")


class Repaint(Base):
    def paint(self, cid, was):
        return ADMIN.post(K + "gegner/bild", json={"id": cid, "was": was})

    def test_paint_again_keep_new_or_old(self):
        r = dungeon.rules()
        c = dungeon._by(r, "gegner")["goblin"]
        name, there = db.picture_of(r, c)
        self.assertFalse(there)
        p = db.prompt(dungeon.style(r, {"welt": "fantasy", "ton": None}), c)
        self.assertIn(db.FOE_EN, p)
        self.assertIn("Goblin", p)
        x = self.paint("goblin", "malen")                              # missing: straight into place
        self.assertEqual(x.status_code, 200, x.text)
        self.assertEqual(x.json(), {"neu": "", "bild": name})
        db._files["m"] = None
        self.assertTrue(db.picture_of(r, c)[1])
        first = dungeon._png(name)
        x = self.paint("goblin", "malen")                              # there: a candidate next to it
        neu = x.json()["neu"]
        self.assertTrue(db.NEU.fullmatch(neu))
        self.assertEqual(db.candidates(), [neu])
        self.assertEqual(ADMIN.get("/api/admin/dungeon/bild/" + neu).status_code, 200)
        self.assertIn(self.c.get("/api/admin/dungeon/bild/" + neu).status_code, (401, 403))
        db._files["m"] = None
        row = {x["id"]: x for x in ADMIN.get(K + "gegner").json()["zeilen"]}["goblin"]
        self.assertEqual((row["bild"], row["neu"]), (name, neu))
        self.assertEqual(self.paint("goblin", "alt").status_code, 200)
        self.assertEqual(db.candidates(), [])
        self.assertEqual(dungeon._png(name), first)
        self.assertEqual(self.paint("goblin", "alt").status_code, 404)   # nothing left to settle
        self.assertEqual(self.paint("goblin", "malen").status_code, 200)
        x = self.paint("goblin", "malen")                              # TAG_MAX 3 in the tests: the day is over for
        self.assertEqual(x.status_code, 200, x.text)                   # the night run, never for the admin's button
        self.assertEqual(len(self.calls), 4)
        self.assertGreaterEqual(db._today(db._state()), db.TAG_MAX)    # it still counts
        self.assertEqual(db._end_why("knopf"), "tag")                   # the run over the whole catalog keeps its limit

    def test_keep_new_and_the_switch(self):
        r = dungeon.rules()
        c = dungeon._by(r, "gegner")["ork"] if "ork" in dungeon._by(r, "gegner") else r["gegner"][1]
        cid = c["id"]
        self.assertEqual(self.paint(cid, "malen").status_code, 200)
        neu = self.paint(cid, "malen").json()["neu"]
        name = db.picture_of(r, c)[0]
        cand = dungeon._png(neu)
        self.assertEqual(self.paint(cid, "neu").status_code, 200)
        self.assertEqual(dungeon._png(name), cand)
        self.assertEqual(db.candidates(), [])
        helpers.set_config(dungeon_bilder=False)
        x = self.paint(cid, "malen")
        self.assertEqual((x.status_code, x.json()["detail"]), (409, "aus"))
        self.assertEqual(self.paint("gibtsnicht", "malen").status_code, 404)

    def test_a_candidate_goes_after_a_day(self):
        r = dungeon.rules()
        c = r["gegner"][0]
        self.paint(c["id"], "malen")
        neu = self.paint(c["id"], "malen").json()["neu"]
        os.utime(dungeon.bild_file(neu), (1000, 1000))
        db.sweep(now=1000 + db.NEU_S - 5, force=True)
        self.assertEqual(db.candidates(), [neu])
        db.sweep(now=1000 + db.NEU_S + 5, force=True)
        self.assertEqual(db.candidates(), [])


if __name__ == "__main__":
    unittest.main()
