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
  each in every world's style (Punkt 8a of 2026-10-24: never a fixed fantasy phrase, the foes neither), painted like
  the catalog; the hero form and „Das kann ich“ name the picture only once it is there and the pictures are on (else
  "" and the page shows a colour, never an emoji); a seat's form and a round the one of its world.
- Tools (art "werkzeug", Punkt 4 of 2026-10-24) have their own phrase and sign, never the scroll's.

No wall clock: the module's clock is set by the tests.
"""
import asyncio
import base64
import datetime
import io
import json
import os
import shutil
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
HERO = {"name": "Arvid", "volk": "mensch", "klasse": "krieger", "satz": "", "geschlecht": "maennlich"}
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
    shutil.rmtree(dungeon.ablage.DIR, ignore_errors=True)               # every round is a file of its own (Punkt 14)
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
        # the names rule (bilder.names) refuses words of every profile's name; the profiles other modules leave
        # behind ("Dungeon Dora" of test_dungeon) would refuse "Dungeon cells", so the shipped prompts are checked
        # against the word lists and „nie“ as in an installation without such names (red to V01.1.043); the names
        # rule itself is tested in test_bilder, here it is empty only because of profiles other modules left behind
        for target, new in (("dungeon_dingbild.clock", lambda: self.now[0]), ("dungeon_dingbild.TAG_MAX", 3),
                            ("bilder.names", lambda uid: set())):
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
        r = self.v.post("/api/dungeon/beitreten", json={"code": code, "held": {"name": "Bela", "volk": "elf", "klasse": "magier", "geschlecht": "weiblich"}})
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

    def test_paint_all_ignores_the_day_limit(self):
        """„Alle Bilder malen“ (Dominik 2026-10-24): the admin's run without the day limit; the stop still ends it."""
        r = dungeon.rules()
        few = db._want(r)[:8]
        with mock.patch("dungeon_dingbild._want", lambda r: few):
            self.run_now()
            self.assertEqual(len(self.calls), db.TAG_MAX)
            self.assertEqual(db._end_why("knopf"), "tag")
            self.assertEqual(db._end_why("alle"), "")                    # no day limit for it
            self.run_now("alle")
            self.assertEqual(len(self.calls), len(few))                  # everything missing, past the limit
            st = db._state()
            self.assertEqual((st["tag"]["n"], st["letzter"]["grund"], st["letzter"]["warum"]), (len(few), "alle", "fertig"))
        db._lauf["stop"] = True
        self.assertEqual(db._end_why("alle"), "angehalten")              # „Abbrechen“
        db._lauf["stop"] = False
        started = []
        with mock.patch("dungeon_dingbild.start", lambda g: started.append(g) or True):
            self.assertEqual(ADMIN.post("/api/admin/dungeon/dingbilder", json={"alle": True}).status_code, 200)
            self.assertEqual(ADMIN.post("/api/admin/dungeon/dingbilder").status_code, 200)   # no body: the old button
            self.assertEqual(ADMIN.post("/api/admin/dungeon/dingbilder", json={"alle": "ja"}).status_code, 200)
        self.assertEqual(started, ["alle", "knopf", "knopf"])

    def test_the_count_names_only_what_a_run_paints(self):
        """Dominik 2026-10-26: 3984/3990 and „Alle Bilder malen · 6“, but every run ended at once with 0 painted: an
        entry whose own picture the admin kept by hand (fest) and an entry refused too often are not open."""
        r = dungeon.rules()
        few = db._want(r)[:5]
        with mock.patch("dungeon_dingbild._want", lambda r: few):
            self.run_now("alle")
            self.assertEqual(len(self.calls), 5)
            (n0, _, k0), (n1, _, _) = few[0], few[1]
            d = db._state()
            os.replace(dungeon.bild_file(n0), dungeon.bild_file("ding-" + "f" * 16))
            d["fest"][k0] = "ding-" + "f" * 16                         # kept by hand, then the prompt changed
            dungeon._bild_rm(n1)
            d["fehl"][n1] = db.FEHL_MAX                                # refused too often
            db._save(d)
            db._files["m"] = None
            s = db.status(r)
            self.assertEqual((s["fertig"], s["von"], s["offen"], s["abgelehnt"]), (4, 5, 0, 1))
            self.assertEqual(db.missing(r), [])
            self.run_now("alle")
            self.assertEqual(len(self.calls), 5)                       # nothing to paint, and the page says 0
            dungeon._bild_rm(few[2][0])
            db._files["m"] = None
            self.assertEqual(db.status(r)["offen"], len(db.missing(r)))
            self.assertEqual(db.status(r)["offen"], 1)

    def test_a_foe_is_painted_from_its_description_size_and_kind(self):
        """Dominik 2026-10-24 „2“: a Cultist came out as a horned demon from its name alone."""
        r = dungeon.rules()
        style = dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None})
        kult = next(g for g in r["gegner"] if g["id"] == "kultist")
        p = db.prompt(style, kult)
        self.assertIn(kult["info"][1].rstrip("."), p)
        self.assertIn(db.WESEN_EN["mensch"], p)
        self.assertIn(db.GROESSE_EN["mittel"], p)
        self.assertNotIn("plain dark background", p)                       # the world's style asks for a background
        self.assertIn(db.WESEN_EN["humanoid"], db.prompt(style, next(g for g in r["gegner"] if g["id"] == "goblin")))
        wolf = db.prompt(style, next(g for g in r["gegner"] if g["id"] == "wolf"))
        self.assertFalse(any(w in wolf for w in db.WESEN_EN.values()))
        import dungeon_bestiarium                                          # what a foe is comes from its field „wesen“
        self.assertLessEqual(set(db.WESEN_EN), set(dungeon_bestiarium.WESEN))   # (review 2026-10-27 Z11), no list by hand
        for g in r["gegner"]:
            w = db.WESEN_EN.get(dungeon_bestiarium.wesen(g))
            self.assertTrue(w is None or w in db.prompt(style, g), g["id"])
        for i in ("seeraeuber", "dorfbewohner", "adliger", "wachhauptmann"):   # people the old list had missed
            g = next((g for g in r["gegner"] if g["id"] == i), None)
            if g:
                self.assertIn(db.WESEN_EN["mensch"], db.prompt(style, g), i)
        self.assertNotIn(db.WESEN_EN["mensch"], db.prompt(style, {k: v for k, v in kult.items() if k != "wesen"}))   # an own foe without it
        ghul = dict(next(g for g in r["gegner"] if g["id"] == "ghul"),   # a description the word list refuses stays out (the
                    info=["Ein Ghul voller Blut.", "A ghoul covered in gore."])   # catalog's own is child-safe since the SRD 5.2.1)
        self.assertNotIn(ghul["info"][1].rstrip("."), db.prompt(style, ghul))
        self.assertTrue(all(db._ok_text(db.prompt(style, g), r) for g in r["gegner"]))
        bad = dict(kult, info=[kult["info"][0], f"A cultist, {r['nie'][0]}."])
        self.assertFalse(db._ok_text(db.prompt(style, bad), r))            # the game's list „nie“ holds too
        want = dict(db.wanted(r))                                          # every foe (the 62 new of V01.1.039 too) is
        for g in r["gegner"]:                                              # painted at night and with „Alle Bilder malen“
            ws = [w["id"] for w in r["welten"] if "alle" in g.get("welten", ["alle"]) or w["id"] in g.get("welten", [])]
            self.assertTrue(ws and all(db.name_of(db.prompt(dungeon.style(r, {"welt": w, "ton": None}), g)) in want for w in ws), g["id"])
        self.assertIn(db.WESEN_EN["mensch"], db.prompt(style, next(g for g in r["gegner"] if g["id"] == "schmuggler")))

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


class Keep(Base):
    """Dominik 2026-10-24: pictures of the Bestiarium were gone after every restart (the sweep after a start took
    them when a new version changed the prompt). A picture stays shown until the new prompt's is there, one the admin
    painted by hand stays for good, and no sweep runs on rules that fell back."""
    def test_a_changed_prompt_keeps_the_old_picture_until_the_new_one_is_there(self):
        r = dungeon.rules()
        style = dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None})
        foe = next(g for g in r["gegner"] if g["id"] == "kultist")
        k = db.key_of(style, foe)
        old = "ding-00000000000000aa"                               # painted under an older prompt
        dungeon._bild_save(old, PNG)
        st = db._state()
        st["zuletzt"][k] = old
        db._save(st)
        self.assertEqual(db.picture_of(r, foe), (old, True))         # shown, not gone
        self.assertEqual(db.sweep(force=True), 0)
        self.assertIn(old, db.files())                               # the sweep after a restart keeps it
        self.assertIn(db.picture_of(r, foe)[0], db.files())
        self.assertIn(db.name_of(db.prompt(style, foe)), dict(db.missing(r)))   # the run still paints the new prompt
        new = db.name_of(db.prompt(style, foe))
        dungeon._bild_save(new, PNG)
        st = db._state()
        st["zuletzt"][k] = new
        db._save(st)
        self.assertEqual(db.picture_of(r, foe)[0], new)
        self.assertEqual(db.sweep(force=True), 1)                    # now the old one may go
        self.assertNotIn(old, db.files())
        self.assertIn(new, db.files())

    def test_the_admins_own_picture_stays_and_is_not_painted_over(self):
        r = dungeon.rules()
        style = dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None})
        foe = next(g for g in r["gegner"] if g["id"] == "goblin")
        n = db.name_of(db.prompt(style, foe))
        dungeon._bild_save("neu-" + n[5:], PNG)                     # „Malen“ on the rules page, kept
        db.settle(r, foe, True)
        k = db.key_of(style, foe)
        self.assertEqual(db._state()["fest"][k], n)
        with mock.patch("dungeon_dingbild.prompt", lambda s, c, f=db.prompt: f(s, c) + (", v2" if c is foe or c.get("id") == "goblin" else "")):
            self.assertEqual(db.picture_of(r, foe), (n, True))       # a later version's prompt: still the admin's
            self.assertNotIn(db.name_of(db.prompt(style, foe)), dict(db.missing(r)))   # and never painted over
            db.sweep(force=True)
            self.assertIn(n, db.files())

    def test_no_sweep_on_rules_that_fell_back(self):
        r = dungeon.rules()
        keep = db.name_of(db.prompt(dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None}), r["gegner"][0]))
        dungeon._bild_save(keep, PNG)
        thin = dict(r, gegner=[])                                     # dungeon.rules without the SRD data
        with mock.patch("dungeon.rules", lambda: thin):
            self.assertFalse(db._complete(thin))
            self.assertEqual(db.sweep(force=True), 0)
        self.assertIn(keep, db.files())
        self.assertTrue(db._complete(r))


class Heroes(Base):
    def test_peoples_classes_and_abilities_get_one_fixed_picture_each(self):
        r = dungeon.rules()
        first = dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None})
        want = dict(db.wanted(r))
        hs = db.heroes(r)
        self.assertEqual(len(hs), len(r["voelker"]) + len(r["klassen"]) + sum(len(k["faehigkeiten"]) for k in r["klassen"]) + len(r["hintergruende"]))
        for art, c in hs:
            p = db.hero_prompt(r, art, c)
            self.assertTrue(p.startswith(first) and p.endswith(dungeon.BILD_ENDE), p)
            self.assertIn(c["name"][1], p)
            for w in r["welten"]:                                              # every world's style (Punkt 8a)
                q = db.hero_prompt(r, art, c, w["id"])
                self.assertIn(db.name_of(q), want)                              # painted like the catalog
                self.assertTrue(q.startswith(dungeon.style(r, {"welt": w["id"], "ton": None})), q)
                self.assertTrue(db._ok_text(q), q)                              # the picture rules pass the shipped data
        self.assertFalse(any("fantasy" in t for t in list(db.HELD_EN.values()) + [db.FOE_EN]))   # the world's style says it
        scifi = next(w["id"] for w in r["welten"] if "science fiction" in w["bildstil"])
        foe = next(g for g in r["gegner"] if "alle" in g.get("welten", ["alle"]) or scifi in g["welten"])
        self.assertNotIn("fantasy", db.prompt(dungeon.style(r, {"welt": scifi, "ton": None}), foe))
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
        m = db.name_of(db.hero_prompt(r, "volk", mensch, scifi))               # the same people in the sci-fi world
        self.assertNotEqual(m, n)
        with open(dungeon.bild_file(m), "wb") as f:
            f.write(PNG)
        db._files["m"] = None
        x = next(x for x in dungeon._choices("de")["voelker"] if x["id"] == "mensch")
        self.assertEqual(x["bilder"], {r["welten"][0]["id"]: n, scifi: m})   # the new round's form: each world's
        x = next(x for x in dungeon._choices("de", False, scifi)["voelker"] if x["id"] == "mensch")
        self.assertEqual((x["bild"], "bilder" in x), (m, False))             # a seat's form: its round's world only
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
            self.assertEqual(set(z), {"grad", "name", "satz", "info", "art", "bild", "bilder"})   # bilder: per world
        self.assertTrue(all("bilder" in x for x in st["f"]))
        st = dungeon.start_powers(r, mag, "de", r["welten"][1]["id"])         # a seat's form: its round's world
        self.assertFalse(any("bilder" in x for x in st["f"] + st["z"]))
        self.assertTrue(all(x["art"] in dungeon.KANN_ARTEN for x in st["f"] + st["z"]))
        kinds = {f["id"]: dungeon.power_kind(f) for k in r["klassen"] for f in k["faehigkeiten"]}
        self.assertEqual((kinds["rundumschlag"], kinds["eisenhaut"], kinds["handauflegen"]), ("angriff", "schutz", "heilen"))
        heal = next(c for c in r["gegenstaende"] if c.get("heilung"))
        self.assertEqual(dungeon.power_kind(heal), "heilen")                 # healing by the catalog's number, not a word

    def test_tools_have_their_own_kind_picture_and_sign(self):
        r = dungeon.rules()
        style = dungeon.style(r, {"welt": r["welten"][0]["id"], "ton": None})
        tools = [c for c in r["gegenstaende"] if c["art"] == "werkzeug"]
        self.assertTrue(len(tools) >= 30)
        for c in tools:
            p = db.prompt(style, c)
            self.assertIn(db.ART_EN["werkzeug"], p)
            self.assertNotIn("scroll", p.lower().replace(c["name"][1].lower(), ""))   # never painted as a scroll
        self.assertEqual(db.ZEICHEN["werkzeug"], "🧰")
        self.assertEqual(set(db.ART_EN), set(dungeon.ARTEN))
        self.assertEqual(set(db.ORT_EN), set(dungeon.ARTEN))                    # every kind has its places (Flair 2a)
        self.assertEqual(set(db.ZEICHEN), set(dungeon.ARTEN))
        import dungeon_regelseite
        self.assertEqual(set(dungeon_regelseite.ART), set(dungeon.ARTEN))      # the rules page names every kind

class RulesPage(Base):
    """Dominik 2026-10-24 „1a 2 und 3“: peoples, classes and backgrounds get a picture on the rules tab in the world
    chosen above the list (Malen, Nochmal malen, Neues/Altes behalten; a kept one stays), backgrounds are painted per
    world from name and description, and each world has a title picture in its own style (a landscape, no people)
    that the new round's world card shows instead of the sign."""
    K = "/api/admin/dungeon/katalog/"

    def test_backgrounds_per_world_and_kept(self):
        r = dungeon.rules()
        first = r["welten"][0]["id"]
        scifi = next(w["id"] for w in r["welten"] if "science fiction" in w["bildstil"])
        h = r["hintergruende"][0]
        want = dict(db.wanted(r))
        for w in r["welten"]:                                                   # painted at night and with „Alle“
            self.assertIn(db.name_of(db.hero_prompt(r, "hintergrund", h, w["id"])), want)
        d = ADMIN.get(self.K + "hintergruende?welt=" + scifi).json()
        self.assertEqual(d["welt"], scifi)
        self.assertEqual([w["id"] for w in d["welten"]], [w["id"] for w in r["welten"]])
        self.assertTrue(all("bild" in x and x["bild"] == "" for x in d["zeilen"]))   # nothing painted yet
        self.assertEqual(ADMIN.get(self.K + "hintergruende?welt=nirgends").json()["welt"], first)   # unknown: the first
        res = ADMIN.post(self.K + "hintergruende/bild", json={"id": h["id"], "was": "malen", "welt": scifi})
        self.assertEqual(res.status_code, 200, res.text)
        n = db.name_of(db.hero_prompt(r, "hintergrund", h, scifi))
        self.assertEqual(res.json()["bild"], n)                                # a missing one is put in place at once
        self.assertIn(n, db.files())
        self.assertEqual(db.entry_pic(r, "hintergruende", h, scifi), (n, True))
        self.assertFalse(db.entry_pic(r, "hintergruende", h, first)[1])       # the other world has none yet
        row = next(x for x in ADMIN.get(self.K + "hintergruende?welt=" + scifi).json()["zeilen"] if x["id"] == h["id"])
        self.assertEqual(row["bild"], n)
        res = ADMIN.post(self.K + "hintergruende/bild", json={"id": h["id"], "was": "malen", "welt": scifi})
        self.assertEqual(res.json()["neu"], "neu-" + n[5:])                    # „Nochmal malen“: a candidate
        self.assertEqual(ADMIN.post(self.K + "hintergruende/bild", json={"id": h["id"], "was": "neu", "welt": scifi}).status_code, 200)
        self.assertEqual(db._state()["fest"][db.key_of(dungeon.style(r, {"welt": scifi, "ton": None}), h, "hintergrund")], n)
        with mock.patch("dungeon_dingbild._hero_text", lambda s, a, c, f=db._hero_text: f(s, a, c) + ", v2"):
            self.assertEqual(db.entry_pic(r, "hintergruende", h, scifi), (n, True))   # kept: a later prompt keeps it
            self.assertNotIn(db.name_of(db.hero_prompt(r, "hintergrund", h, scifi)), dict(db.missing(r)))

    def test_classes_and_peoples_on_the_rules_tab(self):
        r = dungeon.rules()
        scifi = next(w["id"] for w in r["welten"] if "science fiction" in w["bildstil"])
        k = r["klassen"][0]
        res = ADMIN.post(self.K + "klassen/bild", json={"id": k["id"], "was": "malen", "welt": scifi})
        self.assertEqual(res.status_code, 200, res.text)
        n = db.name_of(db.hero_prompt(r, "klasse", k, scifi))                  # the same picture as the hero form's
        self.assertEqual(res.json()["bild"], n)
        x = next(x for x in dungeon._choices("de", False, scifi)["klassen"] if x["id"] == k["id"])
        self.assertEqual(x["bild"], n)
        self.assertIn("welten", ADMIN.get(self.K + "voelker").json())
        self.assertNotIn("welten", ADMIN.get(self.K + "gegner").json())          # a foe keeps its own world

    def test_world_title_picture(self):
        r = dungeon.rules()
        w = r["welten"][1]
        p = db.world_text(r, w)
        self.assertTrue(p.startswith(dungeon.style(r, {"welt": w["id"], "ton": None})), p)   # its own style
        self.assertIn("no people", p)
        self.assertIn(w["name"][1], p)
        self.assertTrue(all(db._ok_text(db.world_text(r, x), r) for x in r["welten"]))
        self.assertIn(db.name_of(p), dict(db.wanted(r)))                       # painted at night and with „Alle“
        self.assertTrue(all(x["bild"] == "" for x in dungeon._choices("de")["welten"]))   # the sign until painted
        res = ADMIN.post(self.K + "welten/bild", json={"id": w["id"], "was": "malen"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["bild"], db.name_of(p))
        self.assertEqual(next(x for x in dungeon._choices("de")["welten"] if x["id"] == w["id"])["bild"], db.name_of(p))
        self.assertEqual(self.c.get(f"/api/profile/dungeon/ding/{db.name_of(p)}").status_code, 200)
        helpers.set_config(dungeon_bilder=False)                               # off: the sign again
        self.assertTrue(all(x["bild"] == "" for x in dungeon._choices("de")["welten"]))

class Stage(Base):
    """The stage behind the story (Dominik 2026-10-24 „alle umsetzen“, idea 10; 2026-10-25 plan „Bilder mit Flair“ 6a):
    per kind of place and room in every style a day, a night and a fight picture, painted at night and with „Alle
    Bilder malen“ in the scene's 16:9, without people (a fight: only distant silhouettes); view() names the one the
    panel's rules pick as out["buehne"]["ersatz"] (kampf while rd["kampf"] is set, nacht for rd["tageszeit"] abend or
    nacht, else tag), the place's kind outside, the room's kind in a vault (a deleted entry: the first room of the same
    kind), "" without a map or with pictures off; the last painted one stays shown until the new prompt's is there."""
    def rd(self, art="dorf", drin=None, t="eingang", raum_art="eingang", **kw):
        k = {"orte": [{"art": art, "name": "Erlenbrück"}], "hier": 0, "drin": drin, "gw": {}}
        if drin is not None:
            k["gw"][str(drin)] = {"raeume": [{"t": t, "art": raum_art}], "hier": 0}
        return dict({"welt": "fantasy", "ton": 12, "karte": k}, **kw)

    def put(self, n):
        os.makedirs(dungeon.BILD_DIR, exist_ok=True)
        with open(dungeon.bild_file(n), "wb") as f:
            f.write(PNG)
        db._files["m"] = None

    def test_every_kind_three_ways_in_every_style_and_wide(self):
        r = dungeon.rules()
        want = dict(db.wanted(r))
        for s in db.styles(r) + [dungeon.BILD_KIND]:
            st = db.stages(r, s)
            self.assertTrue(st and len(st) % 3 == 0)
            for n, p, _ in st:
                self.assertTrue(s == dungeon.BILD_KIND or n in want)            # painted at night and with „Alle“
                self.assertTrue(p.startswith(s) and p.endswith(dungeon.BILD_ENDE), p)
                self.assertTrue("no people" in p or "silhouettes without faces" in p, p)
                self.assertTrue(db._ok_text(p, r), p)                           # the shipped kinds pass the word list
        dorf = next(x for x in r["ortsarten"] if x["id"] == "dorf")
        style = dungeon.style(r, self.rd())
        three = {db.stage_text(style, dorf, False, lg) for lg in db.LAGE_EN}
        self.assertEqual(len(three), 3)
        self.assertLessEqual(three, {p for _, p, _ in db.stages(r, style)})
        self.assertNotIn("clear weather", " ".join(three))                     # weather is the stage's layer
        self.assertNotEqual(db.stage_text(style, dorf), db.dungeon_karte.kind_prompt(style, dorf))   # not the map's vignette
        self.assertEqual(asyncio.run(db.paint_one("ding-00000000000000bb", db.stage_text(style, dorf))), "ok")
        self.assertEqual((self.calls[-1]["width"], self.calls[-1]["height"]), (dungeon.BILD_W, dungeon.BILD_H))
        self.assertEqual(asyncio.run(db.paint_one("ding-00000000000000cc", db.prompt(style, r["gegenstaende"][0]))), "ok")
        self.assertEqual((self.calls[-1]["width"], self.calls[-1]["height"]), (db.SIZE, db.SIZE))   # an item stays square

    def test_the_panel_picks_day_night_or_fight(self):
        self.assertEqual(db.lage(self.rd()), "tag")
        self.assertEqual([db.lage(self.rd(tageszeit=t)) for t in ("morgen", "tag", "abend", "nacht", "quatsch")],
                         ["tag", "tag", "nacht", "nacht", "tag"])                # an unknown daytime counts as day
        self.assertEqual(db.lage(self.rd(tageszeit="nacht", kampf={"gegner": []})), "kampf")
        r = dungeon.rules()
        dorf = next(x for x in r["ortsarten"] if x["id"] == "dorf")
        style = dungeon.style(r, self.rd())
        day, night, fight = (db.name_of(db.stage_text(style, dorf, False, lg)) for lg in ("tag", "nacht", "kampf"))
        for n in (day, night, fight):
            self.put(n)
        self.assertEqual(db.stage_pic(r, self.rd()), day)
        self.assertEqual(db.stage_pic(r, self.rd(tageszeit="abend")), night)
        self.assertEqual(db.stage_pic(r, self.rd(kampf={"gegner": []})), fight)

    def test_view_names_the_stand_in_of_place_and_room(self):
        r = dungeon.rules()
        rd = self.rd()
        style = dungeon.style(r, rd)
        dorf = next(x for x in r["ortsarten"] if x["id"] == "dorf")
        n = db.name_of(db.stage_text(style, dorf))
        self.assertEqual(db.add(r, rd, {})["buehne"], {"ersatz": ""})        # not painted yet
        self.put(n)
        self.assertEqual(db.add(r, rd, {})["buehne"], {"ersatz": n})
        self.assertEqual(db.stage_pic(r, {"welt": "fantasy", "ton": 12}), "")   # an old round without a map
        self.assertEqual(db.stage_pic(r, self.rd(art="geloescht")), "")       # a deleted kind of place
        ein = next(x for x in r["raeume"] if x["id"] == "eingang")
        m = db.name_of(db.stage_text(style, ein, True))
        self.put(m)
        self.assertEqual(db.stage_pic(r, self.rd(drin=0)), m)                 # in a vault: its room's kind
        self.assertEqual(db.stage_pic(r, self.rd(drin=0, t="geloescht")), m)  # a deleted room: the same kind's first
        helpers.set_config(dungeon_bilder=False)                              # off: no name
        self.assertEqual(db.add(r, rd, {})["buehne"], {"ersatz": ""})
        helpers.set_config(dungeon_bilder=True)
        db.sweep(force=True)
        self.assertIn(n, db.files())                                          # the sweep keeps it
        old = "ding-00000000000000dd"                                         # painted under an older prompt
        self.put(old)
        st = db._state()
        st["zuletzt"][db.stage_key(style, dorf, False, "nacht")] = old
        db._save(st)
        self.assertEqual(db.stage_pic(r, self.rd(tageszeit="nacht")), old)    # shown until the new one is there
        db.sweep(force=True)
        self.assertIn(old, db.files())


class Flair(Base):
    """Dominik 2026-10-25 „alles nach empfehlung umsetzten“ (plan „Bilder mit Flair“ 1a-5a): every picture takes light,
    angle and mood from fixed lists, one choice per entry and style (the same every time, never the model's); the
    picture book is never menacing or stormy, a dark world style never festive; an item lies in a place of its kind,
    a fixed rarity shows, a foe has a pose and surroundings by its size, a hero a place and a pose instead of a plain
    dark background; every shipped prompt passes the word list, and the choices vary."""
    def test_fixed_choices_that_vary(self):
        r = dungeon.rules()
        style = dungeon.style(r, {"welt": "fantasy", "ton": None})
        items = r["gegenstaende"]
        ps = [db.prompt(style, c) for c in items]
        self.assertEqual(ps, [db.prompt(style, c) for c in items])           # the same every time
        self.assertFalse(any("plain dark background" in p for p in ps))
        for lst in (db.LICHT_EN, db.WINKEL_EN, db.STIMMUNG_EN):              # every list is used, none rules the catalog
            n = [sum(1 for p in ps if x in p) for x in lst]
            self.assertTrue(all(n), (lst, n))
            self.assertLess(max(n), len(ps) * 0.5, (lst, n))
        same = sum(1 for a, b in zip(items, items[1:]) if db.flair(style, a, "ding") == db.flair(style, b, "ding"))
        self.assertLess(same, len(items) * 0.1)                               # neighbours rarely look alike
        for c in items[:40]:
            p = db.prompt(style, c)
            self.assertTrue(any(o in p for o in db.ORT_EN[c["art"]]), p)     # a place of its kind
        fixed = next(c for c in items if c.get("seltenheit") == "legendaer")
        self.assertIn(db.SELTEN_EN["legendaer"], db.prompt(style, fixed))
        self.assertFalse(any(v in db.prompt(style, c) for c in items if not c.get("seltenheit") for v in db.SELTEN_EN.values()))

    def test_world_style_rules_and_word_list(self):
        r = dungeon.rules()
        kid = dungeon.BILD_KIND
        horror = dungeon.style(r, {"welt": "horror", "ton": None})
        for c in r["gegenstaende"] + r["gegner"]:
            self.assertFalse(any(x in db.prompt(kid, c) for x in db.SANFT + db.HALTUNG_EN), c["id"])   # nothing scary
            self.assertNotIn("festive", db.prompt(horror, c))
        for s in db.styles(r) + [kid]:
            for c in r["gegenstaende"] + r["gegner"]:
                self.assertTrue(db._ok_text(db.prompt(s, c), r), (s, c["id"]))
            for a, c in db.heroes(r):
                self.assertTrue(db._ok_text(db._hero_text(s, a, c), r), (s, a, c["id"]))
        self.assertTrue(all(db._ok_text(db.world_text(r, w), r) for w in r["welten"]))

    def test_foes_and_heroes(self):
        r = dungeon.rules()
        style = dungeon.style(r, {"welt": "fantasy", "ton": None})
        for g in r["gegner"][:60]:
            p = db.prompt(style, g)
            self.assertTrue(any(h in p for h in db.HALTUNG_EN), p)
            big = g.get("groesse") in ("gross", "riesig")
            self.assertTrue(any(u in p for u in db.UMGEBUNG_EN["gross" if big else "klein"]), p)
        for a, c in db.heroes(r):
            p = db._hero_text(style, a, c)
            self.assertNotIn("plain dark background", p)
            self.assertEqual(a != "kraft", any(h in p for h in db.HALTUNG_HELD), p)
            if a != "kraft":
                self.assertNotIn("close-up", p)                               # a whole figure or head and shoulders


class Props(Base):
    """D&D-Idee 3 of round 2 (Umgebung nutzen, Dominik 2026-10-26 „1-9 umsetzten“): the props of a fight still there go
    into the scene picture by their English catalog name (at most REQUISITEN_MAX), never the model's text; a used prop
    and the switch off leave them out."""
    def test_the_fights_props_are_in_the_scene_picture(self):
        helpers.keep_chat(self, "dungeon_umgebung")
        helpers.set_config(dungeon_umgebung=True)
        r = dungeon.rules()
        rid = self.new_round()
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            rd["kampf"] = {"gegner": [], "requisiten": ["kronleuchter", "oelfass", "pulverfass", "felsblock"]}
            dungeon._write(d)
        rd = dungeon._read()["runden"][rid]
        rows = {x["id"]: x for x in r["ideen"]["requisiten"]}
        t = db.props(r, rd)
        for k in ("kronleuchter", "oelfass", "pulverfass"):
            self.assertIn(rows[k]["name"][1].lower(), t)
        self.assertNotIn(rows["felsblock"]["name"][1].lower(), t)          # at most REQUISITEN_MAX
        with mock.patch("dungeon.may_paint", lambda *a: ""):
            with dungeon._lock:
                d = dungeon._read()
                _, prompt = dungeon.queue_scene(r, d, rid, d["runden"][rid], "a hall with long shadows")
            dungeon._bilder_jobs.pop(rid, None)
        self.assertIn(t, prompt)
        self.assertTrue(prompt.endswith(dungeon.BILD_ENDE))
        rd["kampf"]["requisiten"] = ["oelfass"]                             # the others were used
        self.assertNotIn(rows["kronleuchter"]["name"][1].lower(), db.props(r, rd))
        helpers.set_config(dungeon_umgebung=False)
        self.assertEqual(db.props(r, rd), "")
        rd.pop("kampf")
        helpers.set_config(dungeon_umgebung=True)
        self.assertEqual(db.props(r, rd), "")


class Settlement(Base):
    """Dominik 2026-10-25 „so umsetzten“ (Siedlung mit Leben 1a/2a/4a): the settlement's head is the place's stage
    picture, every service (dungeon_gold.DIENSTE and „verbessern“) has a picture per style (painted at night and with
    „Alle Bilder malen“, no person in front) and a line of life per world from dungeon_siedlung.json (every world falls
    back to "alle"), chosen by fixed rules per turn and place, never by the model; with pictures off no names."""
    def test_every_service_painted_and_lined(self):
        import dungeon_gold
        r = dungeon.rules()
        self.assertLessEqual(set(dungeon_gold.DIENSTE) | {dungeon_gold.HEILER, dungeon_gold.GEFAEHRTE}, set(db.DIENST_EN))   # the healer (idea 8), the companion (round 2, idea 9)
        self.assertIn("verbessern", db.DIENST_EN)
        want = dict(db.wanted(r))
        for st in db.styles(r) + [dungeon.BILD_KIND]:
            for n, p, k in db.services(st):
                self.assertTrue(st == dungeon.BILD_KIND or n in want)
                self.assertTrue(db._ok_text(p, r), p)
                self.assertIn("no people in the foreground", p)
        z = db.lines()
        self.assertEqual(set(z["alle"]), set(db.DIENST_EN))                   # every service has lines in every world
        for welt, ds in z.items():
            self.assertTrue(welt == "alle" or welt in {w["id"] for w in r["welten"]}, welt)
            for d, pool in ds.items():
                self.assertIn(d, db.DIENST_EN)
                self.assertTrue(pool and all(len(x) == 2 and all(0 < len(t) <= 120 for t in x) for x in pool), (welt, d))

    def test_one_innkeeper_per_world(self):
        """Review 2026-10-27 Z13: the lines a world shows at once never name the innkeeper as „Wirt“ and „Wirtin“."""
        import re
        z = db.lines()
        for welt in z:
            seen = set()
            for d in db.DIENST_EN:
                for de, _ in z[welt].get(d) or z["alle"].get(d) or []:
                    seen.update(re.findall(r"\b(Wirtin|Wirt)\b", de))
            self.assertLessEqual(len(seen), 1, (welt, seen))

    def test_lines_by_fixed_rules(self):
        rd = {"welt": "piraten", "lang": "de", "zug": 4, "karte": {"hier": 2}}
        a = db.line(rd, "gasthaus")
        self.assertEqual(a, db.line(dict(rd), "gasthaus"))                     # the same within one turn and place
        self.assertIn(a, [x[0] for x in db.lines()["piraten"]["gasthaus"]])
        self.assertIn(db.line(dict(rd, lang="en"), "gasthaus"), [x[1] for x in db.lines()["piraten"]["gasthaus"]])
        self.assertGreater(len({db.line(dict(rd, zug=z), "gasthaus") for z in range(30)}), 1)   # another one later
        self.assertIn(db.line(dict(rd, welt="eigene"), "schmied"), [x[0] for x in db.lines()["alle"]["schmied"]])
        self.assertEqual(db.line(rd, "unbekannt"), "")

    def test_view_names_head_pictures_and_lines(self):
        r = dungeon.rules()
        k = {"orte": [{"art": "dorf", "name": "Erlenbrück"}], "hier": 0, "drin": None, "gw": {}}
        rd = {"welt": "fantasy", "ton": 12, "lang": "de", "zug": 1, "karte": k}
        style = dungeon.style(r, rd)
        sv = {"name": "Erlenbrück", "dienste": [{"id": d, "satz": "x"} for d in ("gasthaus", "lehre", "neu_unbekannt")]}
        out = db.add(r, rd, {"siedlung": sv})["siedlung"]
        self.assertEqual(out["kopf"], "")
        self.assertEqual([x["bild"] for x in out["dienste"]], ["", "", ""])
        self.assertTrue(out["dienste"][0]["zeile"] and out["dienste"][0]["satz"] == "x")   # „satz“ stays the description
        os.makedirs(dungeon.BILD_DIR, exist_ok=True)
        for n in (db.name_of(db.service_text(style, "gasthaus")), db.name_of(db.stage_text(style, next(x for x in r["ortsarten"] if x["id"] == "dorf")))):
            with open(dungeon.bild_file(n), "wb") as f:
                f.write(PNG)
        db._files["m"] = None
        out = db.add(r, rd, {"siedlung": sv})["siedlung"]
        self.assertEqual(out["dienste"][0]["bild"], db.name_of(db.service_text(style, "gasthaus")))
        self.assertTrue(out["kopf"])
        self.assertIsNone(db.add(r, rd, {"siedlung": None})["siedlung"])      # outside a settlement nothing changes
        helpers.set_config(dungeon_bilder=False)
        out = db.add(r, rd, {"siedlung": sv})["siedlung"]
        self.assertEqual((out["kopf"], out["dienste"][0]["bild"]), ("", ""))

if __name__ == "__main__":
    unittest.main()
