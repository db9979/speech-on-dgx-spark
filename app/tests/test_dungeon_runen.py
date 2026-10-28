"""KI-Dungeon-Master: Runen und Sockel, Stufe 1 (dungeon_runen.py; plan dungeon-runen, Dominik 2026-10-27 „1a 2b 3a 4a 5a
6a 7a 8a 10a 11a“, caps 9a, switch off 13a).

- Off by default: the admin's switch chat.dungeon_runen; off later, runes stay but do nothing and fall no more.
- Sockets only in weapons and armour up to „rar“, their number by the base (3a).
- Every rune at every place through the rules that are there (effects, value bonus, life, armour class, resistance,
  discount, potion, gold), each under its cap; a weapon's runes to hit only for its attacks, never in checks.
- Every chain of up to three runes on every kind of base is under the cap or refused (plan point 3 of the bench);
  „rar“ with a +1W6 rune is always refused (review 27.10.).
- Finds: by the occasion, a boss always, the pity after PECH fights, rank at most level + 2, to the hero with the
  fewest; the trader sells ranks 1 to 4; set only with a preview first, never in a fight; the smith never makes a
  thing with runes better.
"""
import itertools
import json
import os
import random
import unittest

from tests import helpers
from tests.test_dungeon import HERO, Base

import dungeon  # noqa: E402
import dungeon_gold  # noqa: E402
import dungeon_kampf as kampf  # noqa: E402
import dungeon_runen as runen  # noqa: E402

PANEL = os.path.dirname(os.path.abspath(runen.__file__))


def thing(r, cid, s="gewoehnlich", so=None, ru=(), eff=None):
    it = {"i": "i" + os.urandom(4).hex(), "id": cid, "s": s, "bonus": dungeon._by(r, "seltenheit")[s]["bonus"], "eigen": "", "satz": ""}
    if eff:
        it["eff"] = eff
    if so is not None:
        it["so"], it["ru"] = so, list(ru)
    return it


def hero(r, klasse="krieger"):
    h = dungeon.new_hero(r, dict(HERO, klasse=klasse), random.Random(1))
    h["hid"] = "h" + os.urandom(4).hex()
    return h


class Rules(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_runen")
        helpers.set_config(dungeon_runen=True)
        self.r = dungeon.rules()

    def rd(self, **kw):
        return dict({"owner": self.uid, "lang": "de", "welt": "fantasy", "zug": 1, "log": []}, **kw)

    def test_switch_is_off_by_default(self):
        import features
        self.assertIn("dungeonrunen", features.BY_KEY)
        self.assertEqual(features.BY_KEY["dungeonrunen"].parent, "dungeon")
        with open(os.path.join(PANEL, "..", "config.default.json"), encoding="utf-8") as f:
            self.assertIs(json.load(f)["chat"]["dungeon_runen"], False)
        live = runen.for_live()
        self.assertTrue(live and all(isinstance(x, int) for x in live.values()))
        self.assertEqual(set(runen.ART_WELT), {"fantasy", "scifi", "piraten", "horror"})   # 10a: every world its word

    def test_sockets_by_the_base(self):
        r = self.r
        want = {"langschwert": 3, "zweihaender": 3, "schwert": 2, "dolch": 2, "kettenhemd": 3, "schild": 2, "helm": 2,
                "panzerhandschuhe": 1, "eisenstiefel": 1}
        for cid, n in want.items():
            for s in ("gewoehnlich", "selten", "rar"):
                self.assertEqual(runen.sockel_max(dungeon, r, thing(r, cid, s)), n, (cid, s))
            self.assertEqual(runen.sockel_max(dungeon, r, thing(r, cid, "episch")), 0, cid)    # 2b: up to „rar“
        ring = next(c["id"] for c in r["gegenstaende"] if c["art"] == "schmuck")
        self.assertEqual(runen.sockel_max(dungeon, r, thing(r, ring)), 0)
        it = thing(r, "schwert")
        it["leg"] = "x"
        self.assertEqual(runen.sockel_max(dungeon, r, it), 0)

    def test_every_rune_works_through_the_rules(self):
        r = self.r
        h = hero(r)
        h["an"]["haupthand"] = thing(r, "langschwert", so=3, ru=["kenaz", "uruz", "ehwaz"])
        wp = h["an"]["haupthand"]
        self.assertIn("feuer", [e["id"] for e in dungeon.item_effects(r, wp)])
        self.assertEqual((runen.damage(dungeon, r, wp), runen.hit(dungeon, r, wp)), (1, 1))
        self.assertEqual(dungeon.total(r, h, "staerke"), dungeon.body(r, h, "staerke", dinge=False))   # to hit never in checks
        h["an"]["koerper"] = thing(r, "kettenhemd", so=3, ru=["tiwaz"])
        rk0 = kampf.rk(dungeon, r, dict(h, an=dict(h["an"], koerper=thing(r, "kettenhemd"))))
        self.assertEqual(kampf.rk(dungeon, r, h), rk0 + 2)                 # Tiwaz on the body: protection +1, twice
        h["an"]["koerper"]["ru"] = ["algiz", "kenaz", "uruz"]
        self.assertEqual(kampf.rk(dungeon, r, h), rk0 + 1)
        self.assertIn("feuer", dungeon.resists(r, h))
        dungeon.relife(r, h)
        base = dungeon.life(r, dict(h, an={k: None for k in h["an"]}))
        self.assertEqual(h["leben_max"], base + 2)
        h["an"]["nebenhand"] = thing(r, "schild", so=2, ru=["berkano", "ehwaz"])
        self.assertEqual(runen.potion(dungeon, r, h), 2)
        self.assertEqual(dungeon.total(r, h, "geschick"), dungeon.body(r, h, "geschick", dinge=False) + 1)
        h["an"]["kopf"] = thing(r, "helm", so=2, ru=["fehu"])
        self.assertEqual(dungeon.rabatt(r, h), min(dungeon.RABATT[1], dungeon.RABATT[0] * max(0, dungeon.total(r, h, "charisma")) + 5))
        wp["ru"] = ["fehu"]
        g0 = h["gold"]
        runen.fight_gold(dungeon, r, self.rd(), [h], 3)
        self.assertEqual(h["gold"], g0 + 6)
        # the caps per hero: life at most LEBEN_HELD, armour class at most RK_HELD
        for k in ("koerper", "kopf", "haende", "fuesse", "nebenhand"):
            cid = {"koerper": "kettenhemd", "kopf": "helm", "haende": "panzerhandschuhe", "fuesse": "eisenstiefel", "nebenhand": "schild"}[k]
            h["an"][k] = thing(r, cid, so=runen.sockel_max(dungeon, r, thing(r, cid)), ru=["uruz", "algiz", "berkano"][:runen.sockel_max(dungeon, r, thing(r, cid))])
        self.assertLessEqual(runen.life(dungeon, r, h), runen.LEBEN_HELD)
        self.assertLessEqual(runen.armour(dungeon, r, h), runen.RK_HELD)

    def test_ansuz_raises_the_higher_value(self):
        r = self.r
        h = hero(r, "magier")
        h["werte"]["intelligenz"], h["werte"]["weisheit"] = 16, 12
        h["an"]["koerper"] = thing(r, "robe", so=3, ru=["ansuz"])
        self.assertEqual(dungeon.worn_bonus(r, h, "intelligenz"), 1)
        self.assertEqual(dungeon.worn_bonus(r, h, "weisheit"), 0)

    def test_off_the_runes_rest(self):
        r = self.r
        wp = thing(r, "langschwert", so=3, ru=["kenaz"])
        helpers.set_config(dungeon_runen=False)
        self.assertEqual(dungeon.item_effects(r, wp), [])
        self.assertEqual(dungeon.strength(r, wp), dungeon.strength(r, thing(r, "langschwert")))
        self.assertTrue(any("ruhen" in z for z in dungeon.item_view(r, wp, "de")["zeilen"]))
        self.assertEqual(runen.find(dungeon, r, self.rd(), [hero(r)], "boss", random.Random(1)), "")
        helpers.set_config(dungeon_runen=True)
        self.assertEqual([e["id"] for e in dungeon.item_effects(r, wp)], ["feuer"])     # 13a: on again, all as before

    def test_every_chain_is_under_the_cap_or_refused(self):
        """Plan point 3: every rune chain on every kind of base, each rarity with sockets and every own effect it can
        have; what the panel lets in stays under every cap."""
        r = self.r
        rd = self.rd()
        bases = ("zweihaender", "dolch", "kettenhemd", "schild", "helm", "panzerhandschuhe")
        ids = [x["id"] for x in r["runen"]]
        seen = 0
        for cid in bases:
            c = dungeon._by(r, "gegenstaende")[cid]
            pool = [None] + [e["id"] for e in r["effekte"] if not e.get("nur") or c["art"] in e["nur"]]
            for s in ("gewoehnlich", "selten", "rar"):
                for eff in pool if s == "rar" else [None]:
                    n = runen.sockel_max(dungeon, r, thing(r, cid, s))
                    todo = [[]]
                    while todo:
                        ru = todo.pop()
                        if len(ru) == n:
                            continue
                        for rid in ids:
                            h = {"runen": {rid: 1}}
                            it = thing(r, cid, s, so=n, ru=ru, eff=eff)
                            grund, z = runen.check(dungeon, r, rd, h, it, rid)
                            if grund != "ok":
                                continue
                            seen += 1
                            neu = it["ru"] + [rid]
                            it["ru"] = neu
                            o = runen.place(dungeon, r, it)
                            ws = [runen.by(r)[x][o] for x in neu]
                            self.assertLessEqual(runen.strength(dungeon, r, it), runen.cap(dungeon, r, it), (cid, s, eff, neu))
                            self.assertLessEqual(it["bonus"] + sum(w.get("treffer", 0) for w in ws), runen.TREFFER_MAX, (cid, neu))
                            self.assertLessEqual(runen._ac(dungeon, r, it, ws), runen.RK_DING, (cid, neu))
                            self.assertLessEqual(len({w["widerstand"] for w in ws if w.get("widerstand")}), runen.WIDERSTAND_DING)
                            effs = [w["effekt"] for w in ws if w.get("effekt")] + ([eff] if eff else [])
                            self.assertEqual(len(effs), len(set(effs)), (cid, neu))
                            todo.append(neu)
        self.assertGreater(seen, 100)

    def test_rare_with_a_d6_rune_is_refused(self):
        r = self.r
        for eff in [e["id"] for e in r["effekte"] if not e.get("nur") or "waffe" in e["nur"]]:
            it = thing(r, "langschwert", "rar", so=3, eff=eff)
            for rid in ("kenaz", "isa", "thurisaz", "nauthiz", "sowilo"):
                self.assertEqual(runen.check(dungeon, r, self.rd(), {"runen": {rid: 1}}, it, rid)[0], "deckel", (eff, rid))
        it = thing(r, "langschwert", so=3)
        self.assertEqual(runen.check(dungeon, r, self.rd(), {"runen": {"kenaz": 1}}, it, "kenaz")[0], "ok")
        self.assertEqual(runen.check(dungeon, r, self.rd(), {"runen": {"algiz": 1}}, it, "algiz")[0], "sockel")   # Algiz: no weapon

    def test_finds_by_the_rules(self):
        r = self.r
        rd = self.rd()
        held = [hero(r), hero(r)]
        for h in held:
            h["stufe"] = 1
        self.assertTrue(runen.find(dungeon, r, rd, held, "boss", random.Random(1)))           # a boss always
        self.assertEqual(sum(sum(h.get("runen", {}).values()) for h in held), 1)
        rd["runen_pech"] = 0
        never = random.Random(2)
        never.randrange = lambda n: n - 1                                 # a roll that never hits 5 in 100
        for k in range(runen.PECH):
            self.assertEqual(runen.find(dungeon, r, rd, held, "gegner", never), "")
            self.assertEqual(rd["runen_pech"], k + 1)
        self.assertTrue(runen.find(dungeon, r, rd, held, "gegner", never))                    # the pity
        self.assertEqual(rd["runen_pech"], 0)
        self.assertEqual([sum(h["runen"].values()) for h in held], [1, 1])                    # to the hero with the fewest
        rangs = set()
        for k in range(200):
            rangs.add(runen.by(r)[runen.find(dungeon, r, rd, held, "boss", random.Random(k))]["rang"])
            for h in held:
                h["runen"] = {}
        self.assertEqual(rangs, set(range(1, 2 + runen.RANG_PLUS)))      # level 1: ranks 1 to 3
        held[0]["runen"] = {"uruz": runen.BEUTEL_MAX}
        held[1]["runen"] = {"uruz": runen.BEUTEL_MAX}
        self.assertEqual(runen.find(dungeon, r, rd, held, "boss", random.Random(1)), "")       # a full bag: none
        self.assertEqual(runen.find(dungeon, r, rd, held, "markt", random.Random(1)), "")

    def test_sockets_on_a_find(self):
        r = self.r
        always = random.Random(1)
        always.randrange = lambda n: 0
        it = thing(r, "kettenhemd")
        runen.give_sockets(dungeon, r, self.rd(), it, always)
        self.assertEqual((it["so"], it["ru"]), (3, []))
        ep = thing(r, "kettenhemd", "episch")
        runen.give_sockets(dungeon, r, self.rd(), ep, always)
        self.assertNotIn("so", ep)
        off = thing(r, "kettenhemd")
        runen.give_sockets(dungeon, r, {"lang": "de"}, off, always)                          # no host: off
        self.assertNotIn("so", off)

    def test_the_trader_sells_only_the_first_four(self):
        r = self.r
        st = runen.stock(dungeon, r, self.rd(), "kraemer", random.Random(1))
        self.assertEqual({runen.by(r)[k]["rang"] for k in st}, set(range(1, runen.KRAEMER + 1)))
        self.assertEqual(runen.stock(dungeon, r, self.rd(), "schmied", random.Random(1)), {})

    def test_the_smith_never_betters_a_thing_with_runes(self):
        r = self.r
        self.assertIsNone(dungeon_gold.better(dungeon, r, thing(r, "schwert", so=2, ru=["uruz"])))
        self.assertEqual(dungeon_gold.better(dungeon, r, thing(r, "schwert", so=2)), "selten")

    def test_a_hero_read_keeps_only_the_rules(self):
        r = self.r
        h = hero(r)
        h["runen"] = {"uruz": 2, "erfunden": 3, "ehwaz": "x", "isa": 0}
        h["tasche"] = [thing(r, "dolch", so=9, ru=["uruz", "algiz", "zz", "kenaz", "isa"]), thing(r, "dolch", "episch", so=2, ru=["uruz"])]
        runen.fix(dungeon, r, h)
        self.assertEqual(h["runen"], {"uruz": 2})
        self.assertEqual((h["tasche"][0]["so"], h["tasche"][0]["ru"]), (2, ["uruz", "kenaz"]))   # Algiz never in a weapon
        self.assertNotIn("so", h["tasche"][1])


class Table(Base):
    def setUp(self):
        super().setUp()
        helpers.keep_chat(self, "dungeon_runen")
        helpers.set_config(dungeon_runen=True)
        self.rid = self.new_round()["rid"]
        self.r = dungeon.rules()
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][self.rid]
            self.pid = next(p for p, x in rd["plaetze"].items() if x.get("uid") == self.uid)
            h = rd["plaetze"][self.pid]["held"]
            h["tasche"] = [thing(self.r, "langschwert", so=3)]
            h["runen"] = {"kenaz": 1, "isa": 1, "uruz": 1}
            h["gold"] = 500
            self.iid = h["tasche"][0]["i"]
            dungeon._write(d)

    def held(self, **b):
        return self.c.post(f"/api/profile/dungeon/{self.rid}/held", json=dict(b, was="rune"))

    def me(self):
        return self.state(self.rid)["plaetze"][self.pid]["held"]

    def test_preview_first_then_set(self):
        v = self.held(tun="pruefen", rune="kenaz", i=self.iid)
        self.assertEqual(v.status_code, 200, v.text)
        pv = v.json()["rune_vorschau"]
        self.assertTrue(pv["ok"])
        self.assertIn("Kenaz", pv["text"])
        self.assertEqual(self.me()["tasche"][0]["ru"], [])                # the preview changes nothing
        self.assertEqual(self.held(tun="einsetzen", rune="kenaz", i=self.iid).status_code, 200)
        h = self.me()
        self.assertEqual((h["tasche"][0]["ru"], h["runen"]), (["kenaz"], {"isa": 1, "uruz": 1}))
        self.assertEqual(self.state(self.rid)["log"][-1]["art"], "rune")
        refused = self.held(tun="einsetzen", rune="isa", i=self.iid)    # a second element: too strong
        self.assertEqual((refused.status_code, refused.json()["detail"]), (400, "rune deckel"))
        pv = self.held(tun="pruefen", rune="isa", i=self.iid).json()["rune_vorschau"]
        self.assertEqual((pv["ok"], pv["grund"]), (False, "deckel"))
        self.assertEqual(self.held(tun="einsetzen", rune="uruz", i=self.iid).status_code, 200)
        sheet = self.c.get(f"/api/profile/dungeon/{self.rid}").json()["ich"]
        self.assertTrue(any(z.startswith("Sockel 3: Kenaz") for z in sheet["tasche"][0]["zeilen"]))
        self.assertEqual(sheet["runen"]["runen"][0]["id"], "isa")
        self.assertEqual(self.held(tun="einsetzen", rune="isa", i="i00000000").status_code, 400)   # not own

    def test_a_rune_told_as_found_is_struck(self):
        """Bericht „Abstimmung mit den Runen“ 7: the panel draws runes only after the narration, so a rune the narration
        hands out is the fault „fund“ (its sentence is struck); the world's word only whole („Perle“, not „Perlen“), a
        rune the hero has already and a person's name never count."""
        erz = dungeon.erz
        rd = self.state(self.rid)
        a = rd["plaetze"][self.pid]["held"]["name"]
        self.assertEqual(erz.found_untold(rd, {"text": "Im Staub glimmt etwas. Ihr findet eine Tiwaz-Rune."}), ["Gruppe: Tiwaz"])
        self.assertEqual(erz.found_untold(rd, {"text": f"{a} findet eine Rune unter dem Stein."}), [])   # has runes already
        self.assertEqual(erz.found_untold(rd, {"text": f"{a} findet eine Tiwaz-Rune unter dem Stein."}), [f"{a}: Tiwaz"])
        self.assertEqual(erz.found_untold(rd, {"text": f"{a} nimmt die Kenaz-Rune aus dem Beutel."}), [])   # her own
        self.assertEqual(erz.found_untold(rd, {"text": "Ihr findet keine Rune, der Boden ist leer."}), [])
        self.assertEqual(erz.found_untold(rd, {"text": "An der Wand sind alte Runen, die Gruppe findet den Weg."}), [])
        rd["welt"] = "piraten"
        self.assertEqual(erz.found_untold(rd, {"text": "Ihr findet eine Perle in der Muschel."}), ["Gruppe: Perle"])
        self.assertEqual(erz.found_untold(rd, {"text": "Ihr findet Perlen am Strand."}), [])
        rd["nsc"] = {"n1": {"name": "Tiwaz"}}
        self.assertEqual(erz.found_untold(rd, {"text": "Ihr findet Tiwaz am Hafen."}), [])        # a person of the round
        story = {"text": f"Die Flut steigt langsam über die schwarzen Felsen der Bucht, und der Wind riecht nach Salz und Teer. {a} "
                         "kniet am Ufer und findet eine Tiwaz-Perle im nassen Sand. Über dem Wrack kreischen die Möwen, und "
                         "die Laternen des Hafens schaukeln im Wind.", "ooc": [], "npc": []}
        self.assertIn("fund", [k for k, _ in erz.faults(dungeon, rd, story)])

    def test_never_in_a_fight(self):
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][self.rid]["kampf"] = {"gegner": []}
            dungeon._write(d)
        v = self.held(tun="einsetzen", rune="kenaz", i=self.iid)
        self.assertEqual((v.status_code, v.json()["detail"]), (409, "rune kampf"))
        self.assertEqual(self.me()["tasche"][0]["ru"], [])

    def test_off_nothing_is_set(self):
        helpers.set_config(dungeon_runen=False)
        v = self.held(tun="einsetzen", rune="kenaz", i=self.iid)
        self.assertEqual((v.status_code, v.json()["detail"]), (400, "rune aus"))

    def test_buy_and_sell_at_the_trader(self):
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][self.rid]
            rd["markt"] = {"name": "Krämer", "satz": "", "ware": [], "art": "kraemer", "kasse": 200, "runen": {"uruz": 1, "fehu": 1}}
            dungeon._write(d)
        m = self.c.get(f"/api/profile/dungeon/{self.rid}").json()["markt"]["runen"]
        self.assertEqual({x["id"] for x in m["ware"]}, {"uruz", "fehu"})
        self.assertEqual(self.held(tun="kaufen", rune="uruz").status_code, 200)
        h = self.me()
        self.assertEqual(h["runen"]["uruz"], 2)
        self.assertLess(h["gold"], 500)
        self.assertEqual(self.held(tun="kaufen", rune="uruz").status_code, 400)                 # only one there
        self.assertEqual(self.held(tun="verkaufen", rune="isa").status_code, 200)
        self.assertNotIn("isa", self.me()["runen"])


if __name__ == "__main__":
    unittest.main()
