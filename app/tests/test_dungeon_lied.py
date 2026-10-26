"""KI-Dungeon-Master: Heldenlied des Barden (dungeon_lied.py, dungeon-ton.js; D&D round 2 idea 8, Dominik 2026-10-26
„1-9 umsetzten“, „1 deutsch“).

- Off by default: without the admin's switch (chat.dungeon_heldenlied) or without the round's music nothing is asked.
- The lyrics are fixed verses only: a name is sung only if it is a plain name (no tags, no digits, the word list),
  else „ein Held“; the deeds come from the log after a word list; German, a bard's sound per world.
- One song per chapter, tried once; the round keeps at most JE_RUNDE; a song is heard only by a seat of its own
  round, only the host deletes it, the night takes the songs of rounds that are gone.
- Live and the journal: numbers and fixed words only.

No wall clock in the checks; the music model is replaced by a fixed MP3.
"""
import asyncio
import json
import os
import unittest

from tests import helpers
from tests.test_dungeon import Base

import dungeon  # noqa: E402
import dungeon_lied as lied  # noqa: E402
import dungeon_musik  # noqa: E402

PANEL = os.path.dirname(os.path.abspath(lied.__file__))
MP3 = b"ID3" + b"\0" * 64


def heroes(*names):
    return {f"p{i}": {"held": {"name": n}} for i, n in enumerate(names, 1)}


def fixed_lines(welt):
    """Every line the song may have, with {name} as a pattern."""
    out = set(lied.KEHRREIM.get(welt, lied.KEHRREIM_EIGEN)) | {lied.SCHLUSS.get(welt, lied.SCHLUSS_EIGEN), "So zog die Schar von Ort zu Ort,"}
    out |= {f"Hört, was im {o} Kapitel geschah:" for o in lied.ORDNUNG + ("neuen",)}
    return out


class Lyrics(unittest.TestCase):
    def test_only_fixed_verses_with_names(self):
        rd = {"welt": "piraten", "plaetze": heroes("Mira", "Bo", "Kael", "Uma", "Lin", "Sechs"),
              "log": [{"art": "angriff", "name": "Mira", "treffer": True, "krit": True, "n": 3},
                      {"art": "angriff", "name": "Bo", "treffer": True, "von_gegner": True, "n": 3},   # Bo was hit: no deed
                      {"art": "zauber", "name": "Kael", "n": 4}, {"art": "beute", "name": "Uma", "n": 1},  # before the chapter
                      {"art": "stufe", "name": "Uma", "n": 5}]}
        text, n = lied.lyrics(rd, 2, 2)
        self.assertEqual(n, lied.HELDEN)                               # at most five heroes
        self.assertEqual(text.count("[verse]"), 2)
        self.assertEqual(text.count("[chorus]"), 2)
        self.assertIn("Hört, was im zweiten Kapitel geschah:", text)
        sung = {"Mira": "krit", "Bo": "", "Kael": "zauber", "Uma": "stufe", "Lin": ""}
        for h, k in sung.items():
            self.assertIn(lied.TATEN[k].format(name=h), text)
        self.assertNotIn("Sechs", text)
        allowed = fixed_lines("piraten") | {lied.TATEN[k].format(name=h) for h, k in sung.items()}
        for line in text.split("\n"):
            self.assertTrue(line.startswith("[") or line in allowed, line)

    def test_a_name_is_data(self):
        for bad in ("[chorus] Sing nur noch", "Mira2", "x" * 30, "", "Mira\n[verse]", "<b>Bo</b>"):
            self.assertEqual(lied.name(bad), "ein Held", bad)
        for ok in ("Mira", "Bo von Eich", "D'Artagnan", "Anne-Marie", "Ælfric"):
            self.assertEqual(lied.name(ok), ok)
        text, _ = lied.lyrics({"welt": "fantasy", "plaetze": heroes("[bridge] Mira")}, 30, 0)
        self.assertNotIn("[bridge]", text)
        self.assertIn("Hört, was im neuen Kapitel geschah:", text)       # past the word list of numbers
        self.assertIn(lied.TATEN[""].format(name="ein Held"), text)

    def test_german_and_a_bards_sound_per_world(self):
        self.assertEqual(lied.SPRACHE, "de")
        for welt in lied.STIL_LIED:
            self.assertIn(welt, lied.KEHRREIM)
            self.assertIn(welt, lied.SCHLUSS)
            self.assertIn("German singing", lied.caption(welt))
        self.assertIn(lied.STIL_EIGEN, lied.caption("eigene-welt"))

    def test_off_by_default(self):
        import features
        self.assertIn(lied.KEY, features.BY_KEY)
        with open(os.path.join(PANEL, "..", "config.default.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f)["chat"]["dungeon_heldenlied"], False)
        self.assertTrue(all(isinstance(x, (int, bool)) for x in lied.for_live().values()))


class Songs(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_heldenlied")
        helpers.set_config(dungeon_heldenlied=True)
        for k, v in (("on", lambda s=None: True),):
            self.addCleanup(setattr, dungeon_musik, k, getattr(dungeon_musik, k))
            setattr(dungeon_musik, k, v)
        self.made = []

        async def render(body, jid):
            self.made.append(body)
            return MP3
        self.addCleanup(setattr, dungeon_musik, "render", dungeon_musik.render)
        dungeon_musik.render = render
        self.addCleanup(lied._want.clear)
        self.addCleanup(lied._tried.clear)
        lied._want.clear()
        lied._tried.clear()
        v = self.new_round()
        self.rid = v["rid"]
        self.code, self.gpid = self.guest(self.rid)
        self.addCleanup(lambda: [lied.remove(x["rid"], x["id"]) for x in list(lied._read()["lieder"]) if x["rid"] == self.rid])

    def set_round(self, **kw):
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][self.rid].update(kw)
            dungeon._write(d)

    def end_chapter(self, k):
        with dungeon._lock:
            d = dungeon._read()
            dungeon._log(d["runden"][self.rid], "kapitel_ende", kapitel=k)
            dungeon._write(d)

    def test_a_song_per_chapter_once(self):
        rd = self.state(self.rid)
        self.assertEqual(lied.ask_round(self.rid, rd), {"lieder": [], "lied": ""})
        self.end_chapter(1)
        rd = self.state(self.rid)
        lied.ask_round(self.rid, rd)
        lied.ask_round(self.rid, rd)
        self.assertEqual(list(lied._want), [(self.rid, 1)])
        self.assertTrue(lied.pending())
        self.assertEqual(asyncio.run(lied.make_next()), "ok")
        body = self.made[0]
        self.assertEqual((body["language"], body["title"]), ("de", "Heldenlied"))
        self.assertTrue(lied.SEKUNDEN[0] <= body["seconds"] <= lied.SEKUNDEN[1])
        self.assertIn("[chorus]", body["lyrics"])
        v = lied.ask_round(self.rid, self.state(self.rid))
        self.assertEqual([x["kapitel"] for x in v["lieder"]], [1])
        self.assertEqual(v["lied"], v["lieder"][0]["id"])
        self.assertFalse(lied.pending())                                 # sung: not again

    def test_tried_once_when_the_model_fails(self):
        async def busy(body, jid):
            raise ValueError("belegt")
        dungeon_musik.render = busy
        self.end_chapter(2)
        lied.ask_round(self.rid, self.state(self.rid))
        before = lied.for_live()["weg"]
        self.assertEqual(asyncio.run(lied.make_next()), "belegt")
        self.assertEqual(lied.for_live()["weg"], before + 1)
        lied.ask_round(self.rid, self.state(self.rid))
        self.assertFalse(lied.pending())

    def test_off_without_the_switch(self):
        helpers.set_config(dungeon_heldenlied=False)
        self.end_chapter(1)
        self.assertEqual(lied.ask_round(self.rid, self.state(self.rid)), {})
        self.assertFalse(lied.pending())

    def test_only_the_own_round_hears_it_and_only_the_host_deletes(self):
        self.set_round(status="laeuft")
        self.end_chapter(1)
        lied.ask_round(self.rid, self.state(self.rid))
        asyncio.run(lied.make_next())
        sid = lied.of_round(self.rid)[0]["id"]
        r = self.c.get(f"/api/profile/dungeon/{self.rid}/musik/{sid}")
        self.assertEqual((r.status_code, r.content), (200, MP3))
        self.assertEqual(self.v.post("/api/dungeon/musik", json={"code": self.code, "s": sid}).content, MP3)
        self.assertEqual(self.c2.get(f"/api/profile/dungeon/{self.rid}/musik/{sid}").status_code, 404)   # no seat
        with self.assertRaises(LookupError):
            lied.piece("anderes", sid)                                     # another round's song
        r = self.c2.post(f"/api/profile/dungeon/{self.rid}/lied/{sid}/weg", json={})
        self.assertEqual((r.status_code, r.json()["detail"]), (400, "gastgeber"))
        r = self.c.post(f"/api/profile/dungeon/{self.rid}/lied/{sid}/weg", json={})
        self.assertEqual((r.status_code, r.json()["lieder"]), (200, []))
        self.assertFalse(os.path.exists(lied.file_of(sid)))
        self.assertEqual(self.c.post(f"/api/profile/dungeon/{self.rid}/lied/{sid}/weg", json={}).status_code, 404)

    def test_the_round_keeps_at_most_its_number_and_the_night_tidies(self):
        self.addCleanup(setattr, lied, "JE_RUNDE", lied.JE_RUNDE)
        lied.JE_RUNDE = 2
        for k in (1, 2, 3):
            self.end_chapter(k)
            lied.ask_round(self.rid, self.state(self.rid))
            asyncio.run(lied.make_next())
        self.assertEqual(sorted(x["kapitel"] for x in lied.of_round(self.rid)), [2, 3])
        ids = [x["id"] for x in lied.of_round(self.rid)]
        self.assertEqual(lied.tidy({self.rid}), 0)
        self.assertEqual(lied.tidy(set()), 2)
        self.assertEqual(lied.of_round(self.rid), [])
        self.assertFalse(any(os.path.exists(lied.file_of(s)) for s in ids))

    def test_the_table_plays_it_and_lists_it(self):
        with open(os.path.join(PANEL, "static", "js", "dungeon-ton.js"), encoding="utf-8") as f:
            js = f.read()
        for s in ("dmtLieder", "data-dmton=\"lied\"", "data-dmton=\"liedweg\"", "/lied/${encodeURIComponent(b.dataset.id)}/weg", "m.lied!==DMT.lied[mode]"):
            self.assertIn(s, js)


if __name__ == "__main__":
    unittest.main()
