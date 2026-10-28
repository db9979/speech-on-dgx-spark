"""KI-Dungeon-Master: Spielleiter gibt Dinge (dungeon_geben.py; Dominik 2026-10-28 „der admin soll die möglichkeit
haben den karakteren items zu geben (gegenstände gold runen etc.)“, „1a 2a 3a 4a 5a“).

- Off by default: the admin's switch chat.dungeon_geben (5a); off, the console has no „Geben“ and the request says so.
- Only the host, only as admin (1a): the panel's admin login or the host's own login as an admin profile; never a
  guest, another seat or the model; the view's „geben“ is the host's alone (dungeon_sicht.NUR_GASTGEBER).
- Everything of the catalog of the round's world up to „episch“, never a legend nor a fixed legendary thing (2a).
- The game's caps (3a): a full bag, GOLD_GEBEN at once and never above GOLD_MAX, runes only with „Runen und Sockel“
  and never above the rune bag, experience at most up to the next level.
- A fixed line at the table and the narration's facts and task (4a); journal lines for every outcome.
"""
import contextlib
import io
import unittest
from unittest import mock

from tests import helpers
from tests.test_dungeon import Base

import dungeon  # noqa: E402
import dungeon_geben as geben  # noqa: E402
import dungeon_runen as runen  # noqa: E402


class Give(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_geben")
        helpers.keep_chat(self, "dungeon_runen")
        helpers.set_config(dungeon_geben=True)
        self.rid = self.new_round()["rid"]
        self.r = dungeon.rules()
        rd = self.state(self.rid)
        self.pid = next(p for p, x in rd["plaetze"].items() if x.get("uid") == self.uid)
        self.url = f"/api/profile/dungeon/{self.rid}/geben"
        self.admin = mock.patch("dungeon_geben.admin", return_value=True)
        self.admin.start()
        self.addCleanup(self.admin.stop)

    def me(self):
        return self.state(self.rid)["plaetze"][self.pid]["held"]

    def give(self, **b):
        return self.c.post(self.url, json=dict({"an": self.pid}, **b))

    def test_off_by_default_and_only_for_the_admin(self):
        helpers.set_config(dungeon_geben=False)
        self.assertIsNone(self.c.get(f"/api/profile/dungeon/{self.rid}").json()["geben"])
        self.assertEqual(self.give(art="gold", n=10).json()["detail"], "geben aus")
        self.assertEqual(self.c.get(self.url).json()["detail"], "geben aus")
        helpers.set_config(dungeon_geben=True)
        v = self.c.get(f"/api/profile/dungeon/{self.rid}").json()["geben"]
        self.assertEqual([x["pid"] for x in v["helden"]], [self.pid])
        self.assertEqual(v["selten"][-1]["id"], "episch")
        with mock.patch("dungeon_geben.admin", return_value=False), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.give(art="gold", n=10).json()["detail"], "geben admin")
            self.assertEqual(self.c.get(self.url).json()["detail"], "geben admin")
        self.assertIn("dungeon: geben | kein admin", out.getvalue())
        rd = self.state(self.rid)
        with self.assertRaises(LookupError):            # never another profile than the host
            geben.give(dungeon, self.r, self.rid, rd, "jemand", {"an": self.pid, "art": "gold", "n": 1})
        self.assertIn("geben", __import__("dungeon_sicht").NUR_GASTGEBER)

    def test_the_admin_check_wants_the_admin_login_or_an_admin_profile(self):
        self.admin.stop()
        req = mock.Mock()
        with mock.patch("core.is_main_admin", return_value=False), mock.patch("coadmin.session", return_value=None):
            self.assertFalse(geben.admin(req, self.uid))
        with mock.patch("core.is_main_admin", return_value=False), \
                mock.patch("coadmin.session", return_value={"id": self.uid, "role": "manager"}):
            self.assertFalse(geben.admin(req, self.uid))          # a manager is not the admin
        with mock.patch("core.is_main_admin", return_value=False), \
                mock.patch("coadmin.session", return_value={"id": "anderer", "role": "admin"}):
            self.assertFalse(geben.admin(req, self.uid))          # another profile's admin login
        with mock.patch("core.is_main_admin", return_value=False), \
                mock.patch("coadmin.session", return_value={"id": self.uid, "role": "admin"}):
            self.assertTrue(geben.admin(req, self.uid))
        with mock.patch("core.is_main_admin", return_value=True):
            self.assertTrue(geben.admin(req, self.uid))
        self.admin.start()

    def test_a_thing_up_to_epic_never_a_legend(self):
        kat = self.c.get(self.url).json()["dinge"]
        ids = {x["id"] for x in kat}
        self.assertIn("langschwert", ids)
        self.assertNotIn("vorpalschwert", ids)                    # a fixed legendary thing
        self.assertNotIn("entermesser", ids)                      # not of this world
        self.assertFalse([x for x in kat if x["s"] == "legendaer"])
        n = len(self.me()["tasche"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            v = self.give(art="ding", id="langschwert", s="episch")
        self.assertEqual(v.status_code, 200, v.text)
        self.assertIn("dungeon: geben | ding | ok", out.getvalue())
        h = self.me()
        self.assertEqual(len(h["tasche"]), n + 1)
        it = h["tasche"][-1]
        self.assertEqual((it["id"], it["s"]), ("langschwert", "episch"))
        self.assertNotIn("u", it)                                 # the game master knows what it gives
        rd = self.state(self.rid)
        e = rd["log"][-1]
        self.assertEqual((e["art"], e["name"]), ("geben", h["name"]))
        self.assertIn("Langschwert", e["ding"])
        self.assertEqual(geben.facts(rd), [{"wer": h["name"], "was": e["ding"]}])
        self.assertIn('"spielleiter_gibt"', dungeon.facts(self.r, rd).split("<<<")[0])
        self.assertIn("spielleiter_gibt", dungeon.system_text(self.r, rd, "erzaehlen"))
        for b in ({"id": "langschwert", "s": "legendaer"}, {"id": "vorpalschwert", "s": "episch"}, {"id": "entermesser"},
                  {"id": "langschwert", "n": 2}, {"id": "gibt_es_nicht"}):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.give(art="ding", **b).json()["detail"], "geben", b)
            self.assertIn("dungeon: geben | ding | nein", out.getvalue())
        self.assertEqual(self.give(art="ding", id="heiltrank", n=3).status_code, 200)        # a stack of potions
        self.assertEqual(sum(x.get("n", 1) for x in self.me()["tasche"] if x["id"] == "heiltrank") >= 3, True)
        self.assertEqual(self.give(art="ding", id="heiltrank", n=geben.STAPEL_GEBEN + 1).json()["detail"], "geben")

    def test_a_full_bag_takes_nothing(self):
        with dungeon._lock:
            d = dungeon._read()
            h = d["runden"][self.rid]["plaetze"][self.pid]["held"]
            h["tasche"] = [dungeon.item(self.r, "dolch") for _ in range(dungeon.TASCHE)]
            dungeon._write(d)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.give(art="ding", id="langschwert").json()["detail"], "geben voll")
        self.assertIn("dungeon: geben | ding | voll", out.getvalue())
        self.assertEqual(len(self.me()["tasche"]), dungeon.TASCHE)

    def test_gold_within_the_games_limit(self):
        g = self.me()["gold"]
        self.assertEqual(self.give(art="gold", n=geben.GOLD_GEBEN).status_code, 200)
        self.assertEqual(self.me()["gold"], g + geben.GOLD_GEBEN)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.give(art="gold", n=geben.GOLD_GEBEN + 1).json()["detail"], "geben")
        self.assertIn("dungeon: geben | gold | nein", out.getvalue())
        for bad in (0, -5, "10", True, 1.5):
            self.assertEqual(self.give(art="gold", n=bad).json()["detail"], "geben", bad)
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][self.rid]["plaetze"][self.pid]["held"]["gold"] = dungeon.GOLD_MAX - 10
            dungeon._write(d)
        self.assertEqual(self.give(art="gold", n=500).status_code, 200)
        self.assertEqual(self.me()["gold"], dungeon.GOLD_MAX)                           # never above
        self.assertEqual(self.give(art="gold", n=1).json()["detail"], "geben")
        self.assertEqual(self.give(art="nichts", n=1).json()["detail"], "geben")
        self.assertEqual(self.give(art="gold", n=1, an="p_gibt_es_nicht").json()["detail"], "geben")

    def test_runes_only_with_runes_and_never_above_the_bag(self):
        helpers.set_config(dungeon_runen=False)
        self.assertEqual(self.c.get(f"/api/profile/dungeon/{self.rid}").json()["geben"]["runen"], [])
        self.assertEqual(self.give(art="rune", id="uruz", n=1).json()["detail"], "geben")
        helpers.set_config(dungeon_runen=True)
        with mock.patch("dungeon_runen.wirkt", return_value=True):
            self.assertIn("uruz", [x["id"] for x in self.c.get(f"/api/profile/dungeon/{self.rid}").json()["geben"]["runen"]])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.give(art="rune", id="uruz", n=geben.RUNEN_GEBEN).status_code, 200)
            self.assertIn("dungeon: geben | rune | ok", out.getvalue())
            self.assertEqual(self.me()["runen"]["uruz"], geben.RUNEN_GEBEN)
            self.assertEqual(self.give(art="rune", id="uruz", n=geben.RUNEN_GEBEN + 1).json()["detail"], "geben")
            self.assertEqual(self.give(art="rune", id="gibt_es_nicht", n=1).json()["detail"], "geben")
            with dungeon._lock:
                d = dungeon._read()
                d["runden"][self.rid]["plaetze"][self.pid]["held"]["runen"] = {"uruz": runen.BEUTEL_MAX - 1}
                dungeon._write(d)
            self.assertEqual(self.give(art="rune", id="kenaz", n=2).json()["detail"], "geben")      # the bag's 40
            self.assertEqual(self.give(art="rune", id="kenaz", n=1).status_code, 200)

    def test_experience_at_most_up_to_the_next_level(self):
        h = self.me()
        m = geben.ep_max(self.r, h)
        self.assertEqual(m, self.r["stufen_ep"][h["stufe"]] - h["ep"])
        self.assertEqual(self.c.get(f"/api/profile/dungeon/{self.rid}").json()["geben"]["helden"][0]["ep_max"], m)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.give(art="ep", n=m + 1).json()["detail"], "geben ep")
        self.assertIn("dungeon: geben | ep | nein", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.give(art="ep", n=m).status_code, 200)
        self.assertIn("dungeon: stufe | 2", out.getvalue())
        h2 = self.me()
        self.assertEqual(h2["stufe"], h["stufe"] + 1)
        self.assertEqual([x["art"] for x in self.state(self.rid)["log"][-2:]], ["stufe", "geben"])
        top = dict(h2, stufe=self.r["grenzen"]["stufe_max"])
        self.assertEqual(geben.ep_max(self.r, top), 0)

    def test_numbers_for_the_live_view(self):
        self.give(art="gold", n=5)
        self.give(art="gold", n=geben.GOLD_GEBEN + 1)
        c = geben.for_live()
        self.assertGreaterEqual(c["gold"], 1)
        self.assertGreaterEqual(c["abgelehnt"], 1)
        self.assertEqual(set(c), {"ding", "gold", "rune", "ep", "abgelehnt"})


if __name__ == "__main__":
    unittest.main()
