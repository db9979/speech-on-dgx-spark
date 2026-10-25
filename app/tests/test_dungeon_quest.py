"""KI-Dungeon-Master: Quest-Gegenstände (dungeon_quest.py, Punkt 15 of the review of 2026-10-24, Dominik „alles
umsetzten“, 12:33 „echte Quest-Gegenstände“).

- A quest thing weighs nothing, is never for sale and passes from hero to hero; it comes from a planner's act, the map
  (dungeon.quest_legen) or a find of the narration, every one checked by fixed rules (name, word lists, QUEST_MAX, at
  most one find a turn, the narration must name it).
- An action that names a thing lying here takes it (before the narration, which hears it as data); a door asks
  quest_haben and quest_genannt; a used thing goes with a line (quest_verbrauchen) and is never laid again.
- A carrier who dies drops it; carried things go into the next chapter with their hero.
- Only while „Quest-Gegenstände“ is on; what lies hid stays with the host and the model (dungeon_sicht.GEHEIM).

The language model is a fixed fake; no wall clock.
"""
import asyncio
import json
import unittest
from unittest import mock

from tests import helpers
from tests.test_dungeon_dingbild import ADMIN
from tests import test_dungeon as T
import dungeon  # noqa: E402
import dungeon_quest as quest  # noqa: E402

KEY = {"id": "q_schluessel", "name": ["Messingschlüssel", "brass key"], "info": "öffnet die Krypta"}


class Quest(T.Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_quest")
        helpers.set_config(dungeon_quest=False)
        v = self.new_round()
        self.rid, self.host = v["rid"], v["pid"]
        self.code, self.gp = self.guest(self.rid)

    def play(self, answers):
        old = dungeon.ask_model
        dungeon.ask_model = T.fake(answers)
        try:
            asyncio.run(dungeon.run_turn(self.rid, self.state(self.rid)["zug"]))
        finally:
            dungeon.ask_model = old
        return self.state(self.rid)

    def act(self, mine, theirs="Ich lausche."):
        z = self.state(self.rid)["zug"]
        self.assertEqual(self.c.post(f"/api/profile/dungeon/{self.rid}/aktion", json={"text": mine, "zug": z}).status_code, 200)
        self.assertEqual(self.v.post("/api/dungeon/aktion", json={"code": self.code, "text": theirs, "zug": z}).status_code, 200)

    def edit(self, fn):
        with dungeon._lock:
            d = dungeon._read()
            out = fn(d["runden"][self.rid])
            dungeon._write(d)
        return out

    def held(self, **b):
        return self.c.post(f"/api/profile/dungeon/{self.rid}/held", json=b)

    def test_off_nothing(self):
        self.assertRaises(PermissionError, self.edit, lambda rd: dungeon.quest_legen(rd, "", KEY))
        self.assertEqual(self.held(was="questaufheben", q="q_schluessel").json()["detail"], "quest aus")
        v = self.c.get(f"/api/profile/dungeon/{self.rid}").json()
        self.assertEqual((v["quest"], v["quest_geheim"]), (None, None))
        rd = self.state(self.rid)
        self.assertNotIn("quest_", dungeon.facts(dungeon.rules(), rd))
        self.assertNotIn("quest_fund", dungeon.system_text(dungeon.rules(), rd, "erzaehlen"))
        self.assertEqual(quest.check(dungeon, dungeon.rules(), rd, [{"wer": "Arvid", "name": "Messingschlüssel"}], "Der Messingschlüssel."), [])
        self.assertEqual(dungeon.for_live()["quest_dinge"], 0)

    def test_naming_takes_it_and_the_heroes_pass_it_on(self):
        helpers.set_config(dungeon_quest=True)
        self.assertEqual(self.edit(lambda rd: dungeon.quest_legen(rd, "", KEY)), "q_schluessel")
        self.assertEqual(self.edit(lambda rd: dungeon.quest_legen(rd, "", dict(KEY, name="Anders"))), "q_schluessel")   # the same id: nothing new
        self.assertRaises(ValueError, self.edit, lambda rd: dungeon.quest_legen(rd, "", dict(KEY, id="Schlüssel")))
        self.assertRaises(ValueError, self.edit, lambda rd: dungeon.quest_legen(rd, "", dict(KEY, id="q_x", name="X")))
        v = self.c.get(f"/api/profile/dungeon/{self.rid}").json()
        self.assertEqual(v["quest"]["hier"], [])                                   # not told yet: the table does not see it
        self.assertEqual([x["name"] for x in v["quest_geheim"]["alle"]], ["Messingschlüssel"])
        g = self.v.post("/api/dungeon/lage", json={"code": self.code}).json()
        self.assertIsNone(g["quest_geheim"])
        self.assertNotIn("Messingschlüssel", json.dumps(g, ensure_ascii=False))
        self.assertEqual(self.held(was="questaufheben", q="q_schluessel").json()["detail"], "quest")   # unseen: not by hand
        self.act("Ich nehme den Messingschlüssel vom Altar.")
        f = json.loads(dungeon.facts(dungeon.rules(), self.state(self.rid)).split("\n<<<", 1)[0])
        self.assertEqual(f["quest_genommen"], [{"name": "Messingschlüssel", "info": "öffnet die Krypta", "wer": "Arvid"}])   # as data
        self.assertNotIn("quest_hier", f)
        text = "Arvid hebt den Messingschlüssel vom Altar, Bela lauscht an der kalten Tür der Kapelle."
        rd = self.play([{"proben": []}, {"erzaehlung": text, "frage_an": ""}])
        self.assertEqual(rd["zug"], 2)
        self.assertEqual(dungeon.quest_haben(rd, "q_schluessel"), self.host)
        line = [e for e in rd["log"] if e["art"] == "quest"]
        self.assertEqual([(e["was"], e["name"], e["wer"]) for e in line], [("genommen", "Messingschlüssel", "Arvid")])
        v = self.held(was="questgeben", q="q_schluessel", an=self.gp).json()      # to Bela
        self.assertEqual((v["quest"]["meine"], [x["wer"] for x in v["quest"]["gruppe"]]), ([], ["Bela"]))
        self.assertEqual(self.held(was="questgeben", q="q_schluessel", an=self.gp).json()["detail"], "quest")   # not mine any more
        g = self.v.post("/api/dungeon/held", json={"code": self.code, "was": "questablegen", "q": "q_schluessel"}).json()
        self.assertEqual([x["name"] for x in g["quest"]["hier"]], ["Messingschlüssel"])
        self.assertEqual(dungeon.quest_haben(self.state(self.rid), "q_schluessel"), None)
        v = self.held(was="questaufheben", q="q_schluessel").json()
        self.assertEqual([x["name"] for x in v["quest"]["meine"]], ["Messingschlüssel"])
        self.assertEqual(self.held(was="questgeben", q="q_schluessel", an=self.host).json()["detail"], "quest")   # not to oneself
        self.assertEqual(self.held(was="questgeben", q="q_fremd", an=self.gp).json()["detail"], "quest")
        # a door of the map: an action that names it and the group carries it; used up with a line, never laid again
        rd = self.state(self.rid)
        self.assertTrue(dungeon.quest_genannt(rd, "q_schluessel", "Ich öffne die Krypta mit dem Messingschlüssel."))
        self.assertTrue(dungeon.quest_genannt(rd, "q_schluessel", "I open it with the brass key"))
        self.assertFalse(dungeon.quest_genannt(rd, "q_schluessel", "Ich öffne die Krypta."))
        self.assertFalse(self.edit(lambda rd: dungeon.quest_verbrauchen(rd, "q_schluessel", self.gp)))
        self.assertTrue(self.edit(lambda rd: dungeon.quest_verbrauchen(rd, "q_schluessel", self.host)))
        rd = self.state(self.rid)
        self.assertEqual((rd["quest"], rd["quest_weg"]), ({}, ["q_schluessel"]))
        self.assertEqual(rd["log"][-1]["was"], "verbraucht")
        self.assertEqual(self.edit(lambda rd: dungeon.quest_legen(rd, "", KEY)), "q_schluessel")
        self.assertEqual(self.state(self.rid)["quest"], {})
        live = dungeon.for_live()
        self.assertTrue(live["quest_genommen"] >= 2 and live["quest_gegeben"] >= 1 and live["quest_verbraucht"] >= 1, live)

    def test_a_find_of_the_narration_by_fixed_rules(self):
        helpers.set_config(dungeon_quest=True)
        r = dungeon.rules()
        rd = self.state(self.rid)
        self.assertIn("quest_fund", dungeon.system_text(r, rd, "erzaehlen"))
        ok = "Unter dem Stein findet Bela eine silberne Karte mit einem Weg durch das Moor."
        chk = lambda obj, text=ok: quest.check(dungeon, r, rd, obj, text)
        self.assertEqual(chk([{"wer": "Bela", "name": "Silberne Karte", "info": "zeigt den Weg"}]),
                         [{"wer": self.gp, "name": "Silberne Karte", "info": "zeigt den Weg"}])
        self.assertEqual(chk([{"wer": "Bela", "name": "Goldene Krone"}]), [])          # the narration does not name it
        self.assertEqual(chk([{"wer": "Bela", "name": "K"}], "K"), [])                 # too short
        self.assertEqual(chk([{"wer": "Niemand", "name": "Silberne Karte"}])[0]["wer"], None)   # nobody of the table: here
        self.assertEqual(chk("Silberne Karte"), [])
        self.act("Ich hebe den Stein an.", "Ich schaue darunter.")
        rd = self.play([{"proben": []}, {"erzaehlung": ok, "frage_an": "",
                                         "quest_fund": [{"wer": "Bela", "name": "Silberne Karte", "info": "zeigt den Weg"}]}])
        x = next(iter(rd["quest"].values()))
        self.assertEqual((x["name"], x["von"], dungeon.quest_haben(rd, x["q"])), (["Silberne Karte", "Silberne Karte"], "modell", self.gp))
        self.assertEqual(quest.check(dungeon, r, rd, [{"wer": "Bela", "name": "silberne karte"}], ok), [])   # the round has it already
        g = self.v.post("/api/dungeon/lage", json={"code": self.code}).json()
        self.assertEqual([y["name"] for y in g["quest"]["meine"]], ["Silberne Karte"])
        with mock.patch.object(quest, "QUEST_MAX", 1):                              # the round is full
            self.assertEqual(quest.check(dungeon, r, rd, [{"wer": "Bela", "name": "Moorlaterne"}], ok + " Eine Moorlaterne."), [])
            self.assertRaises(OverflowError, quest.legen, dungeon, r, rd, "", {"id": "q_rot", "name": "Rubin"})
        self.assertGreaterEqual(dungeon.for_live()["quest_gefunden"], 1)

    def test_a_carrier_who_dies_drops_it_and_the_next_chapter_keeps_it(self):
        helpers.set_config(dungeon_quest=True)
        r = dungeon.rules()

        def lay(rd):
            dungeon.quest_legen(rd, "", KEY)
            dungeon.quest_legen(rd, "", {"id": "q_siegel", "name": "Siegel des Abtes"})
            for x in rd["quest"].values():
                x["gesehen"] = True
            quest.hero(dungeon, rd, self.gp, {"q": "q_schluessel"}, "questaufheben")
            quest.hero(dungeon, rd, self.host, {"q": "q_siegel"}, "questaufheben")
            return rd
        rd = self.edit(lay)
        kept = quest.carry(quest.keep(rd))                                          # both carried: both go along, with their hero
        self.assertEqual(set(kept["quest"]), {"q_schluessel", "q_siegel"})
        self.assertTrue(all(x["wer"] is None and x["hid"] for x in kept["quest"].values()))

        def die(rd):
            rd["plaetze"][self.gp]["held"]["tot"] = True
            quest.learn(dungeon, r, rd, None, [])
            return rd
        rd = self.edit(die)
        self.assertEqual(dungeon.quest_haben(rd, "q_schluessel"), None)
        self.assertEqual([x["name"] for x in self.c.get(f"/api/profile/dungeon/{self.rid}").json()["quest"]["hier"]], ["Messingschlüssel"])
        self.assertEqual(set(quest.keep(rd)["quest"]), {"q_siegel"})                # a thing left lying stays behind
        # the next chapter: the host's hero sits down with the siegel in hand again (by its hero, not its seat)
        nxt = {"plaetze": {"p_neu": dict(rd["plaetze"][self.host])}, "owner": rd["owner"], "lang": "de", "zug": 1}
        nxt.update(quest.carry(quest.keep(rd)))
        self.assertEqual(quest.haben(dungeon, nxt, "q_siegel"), "p_neu")
        quest.learn(dungeon, r, nxt, None, [])
        self.assertEqual(nxt["quest"]["q_siegel"]["wer"], "p_neu")

    def test_the_story_planner_gives_an_act_its_thing(self):
        helpers.set_config(dungeon_quest=True)
        r = dungeon.rules()
        akt = {"titel": "Die Kapelle", "inhalt": "Die Helden suchen in der Kapelle nach dem Weg.", "wende": "Das Siegel bricht", "zuege": 4}
        plan = {"titel": "Glocke", "welt": "fantasy", "ton": 12, "idee": "Eine Glocke läutet von selbst.", "ziel": "Die Glocke stillen",
                "akte": [dict(akt, ding="Siegel des Abtes"), dict(akt, ding="X"), dict(akt)]}
        g, err = dungeon.check_plan(r, plan)
        self.assertEqual((g, err), (None, ["Akt 2: besonderes Ding 2 bis 40 Zeichen"]))
        plan["akte"][1].pop("ding")
        g, err = dungeon.check_plan(r, plan)
        self.assertEqual([a.get("ding") for a in g["akte"]], ["Siegel des Abtes", None, None])
        self.assertEqual(ADMIN.get("/api/admin/dungeon").json()["planer"]["quest"], quest.NAME_LEN)   # the planner's act field

        def run(rd):
            rd.update(plan=g, akt=0, akt_zug=1)
            quest.act_thing(dungeon, r, rd)
            quest.act_thing(dungeon, r, rd)                                         # once
            return rd
        rd = self.edit(run)
        self.assertEqual([(x["q"], x["von"], x["ort"]) for x in rd["quest"].values()], [("q_akt1", "plan", "")])
        helpers.set_config(dungeon_quest=False)
        off = dict(rd, quest={})
        quest.act_thing(dungeon, r, off)
        self.assertEqual(off["quest"], {})
        self.assertEqual(ADMIN.get("/api/admin/dungeon").json()["planer"]["quest"], 0)


if __name__ == "__main__":
    unittest.main()
