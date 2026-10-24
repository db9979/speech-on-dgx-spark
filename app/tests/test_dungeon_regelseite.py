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
        self.assertEqual(ADMIN.post(K + "klassen/bild", json={"was": "malen", "id": "krieger"}).status_code, 404)
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
        x = self.paint("goblin", "malen")                              # TAG_MAX 3 in the tests: the day is over
        self.assertEqual((x.status_code, x.json()["detail"]), (409, "tag"))
        self.assertEqual(len(self.calls), 3)

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
