"""Bilder für Ausrüstung und Zauber (dungeon_dingbild.py, plan dungeon-master „5i“): one picture per catalog entry and
world, painted at night or on the admin's button, and an own picture for a named rare find.

- Off by default: without its admin switch (chat.dungeon_bilder) or without „Bilder malen“ nothing is painted, the
  button is refused, and every item keeps the sign of its kind.
- The catalog's prompt is fixed by the panel (the world's style, the English name, the kind's phrase); a prompt the
  picture rules refuse is never sent and not tried again; without the picture check no picture (the run stops).
- The run keeps the day's limit, stops on „Anhalten“, and at night only inside the window (once a night).
- A find: only a named, known item from „rar“ on, only with „Bilder malen“ of the host, checked like the round's
  scene text, counted to the game's day limit; never twice.
- A seat sees the pictures through view() as a copy (the round's file stays as it was); a profile without the game
  and a wrong code get nothing; a name outside the pattern is refused.
- The sweep removes pictures nobody asks for; Live only counts.
- Peoples, classes and class abilities of the hero form (Dominik 2026-10-24 „bilder keine icons“): one fixed prompt
  each in the first world's style, painted like the catalog; the hero form and „Das kann ich“ name the picture only
  once it is there and the pictures are on (else "" and the page shows a colour, never an emoji).

No wall clock: the module's clock is set by the tests.
"""
import asyncio
import base64
import datetime
import io
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import dungeon  # noqa: E402
import dungeon_dingbild as db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
HERO = {"name": "Arvid", "volk": "mensch", "klasse": "krieger", "satz": ""}
NOON = datetime.datetime(2026, 3, 4, 12, 0).timestamp()
NIGHT = datetime.datetime(2026, 3, 4, 2, 0).timestamp()


def png():
    """A real picture as the service sends it, with its AI mark in a text chunk."""
    from PIL import Image, PngImagePlugin
    meta = PngImagePlugin.PngInfo()
    meta.add_itxt("KI", "KI-Bild")
    out = io.BytesIO()
    Image.new("RGB", (db.SIZE, db.SIZE), (90, 40, 20)).save(out, "PNG", pnginfo=meta)
    return out.getvalue()


PNG = png()
_PROFILES = {}


def profile(name):
    if name not in _PROFILES:
        guard.reset()
        r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
        assert r.status_code in (200, 409), r.text
        c = TestClient(panel.app)
        assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
        _PROFILES[name] = (c, c.get("/api/whoami").json()["profile"]["id"])
    return _PROFILES[name]


def wipe():
    for f in (dungeon.FILE, dungeon.FIGUREN, dungeon.EIGENE, db.FILE):
        if os.path.exists(f):
            os.remove(f)
    if os.path.isdir(dungeon.BILD_DIR):
        for f in os.listdir(dungeon.BILD_DIR):
            os.remove(os.path.join(dungeon.BILD_DIR, f))
    dungeon._rules["r"] = None


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Ding Dora")

    def setUp(self):
        helpers.keep_chat(self, "dungeon", "dungeon_bilder", "bilder")
        helpers.set_config(dungeon=True, dungeon_bilder=True, bilder=True)
        self._image(True)
        self.addCleanup(self._image, False)
        guard.reset()
        for k in [k for k in guard._rate if str(k[0]).startswith("dungeon")]:
            guard._rate.pop(k, None)
        wipe()
        self.addCleanup(wipe)
        for f in (dungeon._hfile(self.uid), dungeon._kfile(self.uid)):
            if os.path.exists(f):
                os.remove(f)
        self.now = [NOON]
        for target, new in (("dungeon_dingbild.clock", lambda: self.now[0]), ("dungeon_dingbild.TAG_MAX", 3)):
            p = mock.patch(target, new)
            p.start()
            self.addCleanup(p.stop)
        db._lauf.update(task=None, grund="", start=0.0, gemalt=0, stop=False)
        db._funde.clear()
        db._files["m"] = None
        self.calls, self.nsfw = [], [0.01]

        async def no_wait(*a, **k):
            return 0

        async def call(path, body=None, timeout=0):
            self.calls.append(body)
            d = {"png": base64.b64encode(PNG).decode(), "w": body["width"], "h": body["height"], "seconds": 1.0}
            if self.nsfw[0] is not None:
                d["nsfw"] = self.nsfw[0]
            return 200, d
        for target, new in (("vorrang.quiet", no_wait), ("bilder.call", call)):
            p = mock.patch(target, new)
            p.start()
            self.addCleanup(p.stop)
        self.spawned = []
        old_spawn, old_ask = dungeon.spawn, dungeon.ask_model

        async def silent(*a, **k):
            raise TimeoutError("test")
        dungeon.ask_model = silent

        def run(coro, name=""):
            self.spawned.append(name)
            coro.close()
        dungeon.spawn = run
        self.addCleanup(setattr, dungeon, "spawn", old_spawn)
        self.addCleanup(setattr, dungeon, "ask_model", old_ask)
        self.v = TestClient(panel.app)

    def _image(self, on):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c.setdefault("image", {})["enabled"] = on
        helpers.write_config(c)

    def run_now(self, grund="knopf"):
        """A run in the test's own loop, to its end."""
        async def go():
            db._lauf.update(grund=grund, start=self.now[0], gemalt=0)
            await db._run(grund)
        asyncio.run(go())

    def new_round(self, **kw):
        b = {"titel": "Die Glocke", "welt": "fantasy", "ton": 12, "zug_s": 120, "stunden": 6, "held": dict(HERO)}
        b.update(kw)
        r = self.c.post("/api/profile/dungeon/runde", json=b)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["rid"]

    def give(self, rid, **it):
        """An item straight into the host's bag (as dungeon.loot would)."""
        r = dungeon.rules()
        with dungeon._lock:
            d = dungeon._read()
            h = next(p["held"] for p in d["runden"][rid]["plaetze"].values() if p.get("held"))
            x = dungeon.item(r, it.pop("cid", "schwert"), it.pop("s", "rar"), eigen=it.pop("eigen", ""), satz=it.pop("satz", ""))
            x.update(it)
            h["tasche"].append(x)
            dungeon._write(d)
        return x

    def guest(self, rid):
        r = self.c.post(f"/api/profile/dungeon/{rid}/platz", json={"base": "https://spark.example"})
        code = r.json()["link"].split("#spiel=", 1)[1]
        r = self.v.post("/api/dungeon/beitreten", json={"code": code, "held": {"name": "Bela", "volk": "elf", "klasse": "magier"}})
        self.assertEqual(r.status_code, 200, r.text)
        return code


class Catalog(Base):
    def test_off_paints_nothing_and_keeps_the_sign(self):
        helpers.set_config(dungeon_bilder=False)
        self.assertFalse(db.on())
        self.assertFalse(db.start("knopf"))
        r = ADMIN.post("/api/admin/dungeon/dingbilder")
        self.assertEqual(r.status_code, 409)
        rid = self.new_round()
        self.give(rid)
        it = self.c.get(f"/api/profile/dungeon/{rid}").json()["ich"]["tasche"][-1]
        self.assertEqual((it["bild"], it["zeichen"]), ("", db.ZEICHEN["waffe"]))
        asyncio.run(db.due())
        self.assertEqual(self.calls, [])
        helpers.set_config(dungeon_bilder=True, bilder=False)      # the Spark's „Bilder malen“ is needed too
        self.assertFalse(db.on())
        self.assertFalse(ADMIN.get("/api/admin/dungeon").json()["dingbilder"]["bilder"])

    def test_run_paints_by_fixed_prompt_within_the_day_limit(self):
        r = dungeon.rules()
        self.run_now()
        self.assertEqual(len(self.calls), db.TAG_MAX)                 # the day's limit ends the run
        first = r["gegenstaende"][0]
        p = self.calls[0]["prompt"]
        self.assertTrue(p.startswith(dungeon.style(r, {"welt": r["welten"][0]["id"]})))
        self.assertIn(first["name"][1], p)
        self.assertIn(db.ART_EN[first["art"]], p)
        self.assertTrue(p.endswith(dungeon.BILD_ENDE))
        self.assertEqual((self.calls[0]["width"], self.calls[0]["height"]), (db.SIZE, db.SIZE))
        name = db.name_of(p)
        self.assertIn(name, db.files())
        from PIL import Image
        im = Image.open(dungeon.bild_file(name))
        self.assertEqual(im.size, (db.SIZE // 2, db.SIZE // 2))      # kept at half
        self.assertEqual(im.text.get("KI"), "KI-Bild")               # the AI mark stays
        st = db._state()
        self.assertEqual((st["tag"]["n"], st["letzter"]["warum"], st["letzter"]["gemalt"]), (3, "tag", 3))
        self.run_now()
        self.assertEqual(len(self.calls), db.TAG_MAX)                 # nothing more today
        self.now[0] += 86400
        self.run_now()
        self.assertEqual(len(self.calls), 2 * db.TAG_MAX)             # the next day goes on with what is missing
        self.assertEqual(len({c["prompt"] for c in self.calls}), len(self.calls))
        s = ADMIN.get("/api/admin/dungeon/dingbilder").json()
        self.assertEqual((s["fertig"], s["von"], s["heute"]), (6, len(db.wanted(r)), 3))

    def test_a_seat_sees_the_picture_as_a_copy(self):
        rid = self.new_round()
        x = self.give(rid, cid="heiltrank", s="gewoehnlich")
        r = dungeon.rules()
        c = dungeon._by(r, "gegenstaende")["heiltrank"]
        name = db.name_of(db.prompt(dungeon.style(r, self_rd := dungeon._read()["runden"][rid]), c))
        asyncio.run(db.paint_one(name, db.prompt(dungeon.style(r, self_rd), c)))
        before = json.dumps(dungeon._read()["runden"][rid], sort_keys=True)
        v = self.c.get(f"/api/profile/dungeon/{rid}").json()
        it = next(i for i in v["ich"]["tasche"] if i["i"] == x["i"])
        self.assertEqual((it["bild"], it["zeichen"]), (name, db.ZEICHEN["trank"]))
        self.assertEqual(json.dumps(dungeon._read()["runden"][rid], sort_keys=True), before)   # the round's file untouched
        got = self.c.get(f"/api/profile/dungeon/ding/{name}")
        self.assertEqual((got.status_code, got.headers["content-type"]), (200, "image/png"))
        code = self.guest(rid)
        self.assertEqual(self.v.post("/api/dungeon/ding", json={"code": code, "name": name}).content, got.content)
        self.assertEqual(self.v.post("/api/dungeon/ding", json={"code": "x" * 32, "name": name}).status_code, 400)
        self.assertEqual(self.c.get("/api/profile/dungeon/ding/..%2Fdungeon-runden").status_code, 404)
        self.assertEqual(self.c.get("/api/profile/dungeon/ding/ding-0123456789abcdef").status_code, 404)
        c2, uid2 = profile("Ding Emil")
        with mock.patch("features.allowed", lambda key, uid, *a: not (key == "dungeon" and uid == uid2)):
            self.assertEqual(c2.get(f"/api/profile/dungeon/ding/{name}").status_code, 403)
        # the youngest tone takes the picture book's style
        kid = self.new_round(titel="Kinder", ton=min(t["id"] for t in r["toene"]))
        self.assertIn(dungeon.BILD_KIND, db.styles(r))
        p = db.prompt(dungeon.style(r, dungeon._read()["runden"][kid]), c)
        self.assertTrue(p.startswith(dungeon.BILD_KIND))

    def test_refused_prompt_and_missing_check(self):
        own = {"gegenstaende": [{"id": "nacktschwert", "art": "waffe", "name": ["Nacktschwert", "Nude sword"], "schaden": 6, "wert": "staerke", "kg": 2, "preis": 30}]}
        r = ADMIN.put("/api/admin/dungeon", json={"eigene": own})
        self.assertEqual(r.status_code, 200, r.text)
        rules = dungeon.rules()
        c = dungeon._by(rules, "gegenstaende")["nacktschwert"]
        bad = db.name_of(db.prompt(db.styles(rules)[0], c))
        st = db._state()
        st["fehl"] = {n: db.FEHL_MAX for n, _ in db.wanted(rules) if n != bad}   # only the refused one is left
        db._save(st)
        self.run_now()
        self.assertEqual(self.calls, [])                               # never sent to the picture service
        self.assertEqual(db._state()["fehl"][bad], db.FEHL_MAX)
        self.assertEqual(db.missing(rules), [])                        # and not tried again
        self.assertEqual(ADMIN.get("/api/admin/dungeon/dingbilder").json()["abgelehnt"], len(db.wanted(rules)))
        # without the picture check the run stops at once (fail closed)
        db._save({})
        self.nsfw[0] = None
        self.run_now()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(db._state()["letzter"]["warum"], "ohne_pruefung")
        self.assertEqual(db.files(), frozenset())
        # held back by the check: not kept, the run goes on with the next one
        db._save({})
        self.nsfw[0] = 0.9
        self.run_now()
        self.assertEqual(len(self.calls), 1 + db.TAG_MAX)             # every one asked for counts to the day's limit
        self.assertEqual(db.files(), frozenset())
        self.assertEqual(sorted(db._state()["fehl"].values()), [1] * db.TAG_MAX, db._state()["fehl"])

    def test_night_window_once_a_night_and_stop(self):
        started = []
        with mock.patch("dungeon_dingbild.start", lambda g: started.append(g) or True):
            asyncio.run(db.due())
            self.assertEqual(started, [])                              # noon: no run
            self.now[0] = NIGHT
            asyncio.run(db.due())
            self.assertEqual(started, ["nacht"])
            st = db._state()
            st["nacht"] = db._date()
            db._save(st)
            asyncio.run(db.due())
            self.assertEqual(started, ["nacht"])                       # once a night
        self.assertEqual(db._end_why("nacht"), "")
        self.now[0] = NOON
        self.assertEqual(db._end_why("nacht"), "morgen")               # the morning ends a night's run
        self.assertEqual(db._end_why("knopf"), "")                     # the button's run is not bound to the night
        db._lauf["stop"] = True
        self.assertEqual(db._end_why("knopf"), "angehalten")
        with mock.patch("notaus.blocks", lambda kind, uid=None: kind == "auto"):
            db._lauf["stop"] = False
            self.assertEqual(db._end_why("knopf"), "notaus")
        self.assertEqual(ADMIN.delete("/api/admin/dungeon/dingbilder").json()["laeuft"], False)


class Finds(Base):
    def test_named_rare_find_gets_its_own_picture_once(self):
        rid = self.new_round()
        x = self.give(rid, eigen="Glockenbrecher", satz="Die Klinge summt leise.")
        self.give(rid, eigen="Rostiger Stock", s="gewoehnlich")            # too common
        self.give(rid, s="rar")                                          # no name
        u = self.give(rid, cid="ring", s="episch", eigen="Nachtauge")   # unknown magic: not yet
        self.assertTrue(u.get("u"))
        n0 = dungeon._bild_count(dungeon._read())
        jobs = db.queue_finds()
        self.assertEqual([n for n, _ in jobs], ["fund-" + x["i"]])
        self.assertIn("Glockenbrecher", jobs[0][1])
        self.assertTrue(jobs[0][1].startswith(dungeon.style(dungeon.rules(), dungeon._read()["runden"][rid])))
        self.assertEqual(dungeon._bild_count(dungeon._read()), n0 + 1)   # counts to the game's day limit
        self.assertEqual(db.queue_finds(), [])                          # on its way: never twice
        asyncio.run(db.paint_find(*jobs[0]))
        self.assertEqual(db.queue_finds(), [])
        it = next(i for i in self.c.get(f"/api/profile/dungeon/{rid}").json()["ich"]["tasche"] if i["i"] == x["i"])
        self.assertEqual(it["bild"], "fund-" + x["i"])
        self.assertEqual(db._day.counts()["funde"], 1)

    def test_find_limits(self):
        rid = self.new_round()
        self.give(rid, eigen="Glockenbrecher")
        with mock.patch("dungeon.pictures_on", lambda uid: False):     # the host has no „Bilder malen“
            self.assertEqual(db.queue_finds(), [])
        with dungeon._lock:
            d = dungeon._read()
            d["bilder"] = {"day": dungeon.DayCounter.date(), "n": dungeon.rules()["grenzen"]["bilder_tag"]}
            dungeon._write(d)
        self.assertEqual(db.queue_finds(), [])                          # the game's day limit
        self.assertEqual(list(v["st"] for v in db._state()["funde"].values()), ["tag"])
        y = self.give(rid, eigen="Nackter Zorn")                        # the picture rules refuse the name
        with dungeon._lock:
            d = dungeon._read()
            d["bilder"] = {}
            dungeon._write(d)
        db._save({})
        names = [n for n, _ in db.queue_finds()]
        self.assertNotIn("fund-" + y["i"], names)
        self.assertEqual(db._state()["funde"][y["i"]]["st"], "weg")

    def test_sweep_and_live(self):
        rid = self.new_round()
        x = self.give(rid, eigen="Glockenbrecher")
        for n in ("fund-" + x["i"], "fund-i00000000", "ding-0123456789abcdef"):
            dungeon._bild_save(n, PNG)
        keep = db.wanted(dungeon.rules())[0][0]
        dungeon._bild_save(keep, PNG)
        self.assertEqual(db.sweep(force=True), 2)
        self.assertEqual(db.files(), frozenset({"fund-" + x["i"], keep}))
        live = db.for_live()
        self.assertTrue(live["on"])
        self.assertTrue(all(isinstance(v, (bool, int)) for v in live.values()))
        self.assertNotIn("Glockenbrecher", json.dumps(live))
        helpers.set_config(dungeon_bilder=False)
        self.assertEqual(db.for_live(), {"on": False})


class Heroes(Base):
    def test_peoples_classes_and_abilities_get_one_fixed_picture_each(self):
        r = dungeon.rules()
        first = dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None})
        want = dict(db.wanted(r))
        hs = db.heroes(r)
        self.assertEqual(len(hs), len(r["voelker"]) + len(r["klassen"]) + sum(len(k["faehigkeiten"]) for k in r["klassen"]))
        for art, c in hs:
            p = db.hero_prompt(r, art, c)
            self.assertIn(db.name_of(p), want)                                  # painted like the catalog
            self.assertTrue(p.startswith(first) and p.endswith(dungeon.BILD_ENDE), p)
            self.assertIn(c["name"][1], p)
            self.assertTrue(db._ok_text(p), p)                                # the picture rules pass the shipped data
        kraft = r["klassen"][0]["faehigkeiten"][0]
        self.assertIn(kraft["satz"][1], db.hero_prompt(r, "kraft", kraft))
        self.assertNotIn("{}", "".join(db.hero_prompt(r, a, c) for a, c in hs))
        w = dungeon._choices("de")
        self.assertTrue(all(x["bild"] == "" for x in w["voelker"] + w["klassen"]))   # nothing painted yet: no name
        self.assertTrue(all(x["satz"] for x in w["voelker"][:5] + w["klassen"][:5]))   # the shipped ones have a sentence
        mensch = next(x for x in r["voelker"] if x["id"] == "mensch")
        n = db.name_of(db.hero_prompt(r, "volk", mensch))
        os.makedirs(dungeon.BILD_DIR, exist_ok=True)
        with open(dungeon.bild_file(n), "wb") as f:
            f.write(PNG)
        db._files["m"] = None
        self.assertEqual(next(x for x in dungeon._choices("de")["voelker"] if x["id"] == "mensch")["bild"], n)
        self.assertEqual(self.c.get(f"/api/profile/dungeon/ding/{n}").status_code, 200)   # loaded like an item's picture
        db.sweep(force=True)
        self.assertIn(n, db.files())                                          # the sweep keeps it
        helpers.set_config(dungeon_bilder=False)                              # off: no picture named
        self.assertEqual(next(x for x in dungeon._choices("de")["voelker"] if x["id"] == "mensch")["bild"], "")

    def test_powers_carry_picture_and_kind(self):
        r = dungeon.rules()
        mag = next(k for k in r["klassen"] if k["id"] == "magier")
        st = dungeon.start_powers(r, mag, "de")
        self.assertTrue(st["f"] and st["z"])
        for x in st["f"]:
            self.assertEqual(set(x) >= {"name", "satz", "wert", "bonus", "art", "bild"}, True)
        for z in st["z"]:
            self.assertEqual(set(z), {"grad", "name", "satz", "info", "art", "bild"})
        self.assertTrue(all(x["art"] in dungeon.KANN_ARTEN for x in st["f"] + st["z"]))
        kinds = {f["id"]: dungeon.power_kind(f) for k in r["klassen"] for f in k["faehigkeiten"]}
        self.assertEqual((kinds["rundumschlag"], kinds["eisenhaut"], kinds["handauflegen"]), ("angriff", "schutz", "heilen"))
        heal = next(c for c in r["gegenstaende"] if c.get("heilung"))
        self.assertEqual(dungeon.power_kind(heal), "heilen")                 # healing by the catalog's number, not a word


if __name__ == "__main__":
    unittest.main()
