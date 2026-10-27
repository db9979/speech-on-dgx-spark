"""Gleiches Gesicht für NSCs (dungeon_gesicht.py, Tabletop-Punkt 15, plan 1a-5a): one portrait per person met, a
reference picture for later scene pictures.

- Off by default: without its admin switch (chat.dungeon_gesicht), „NSC-Gedächtnis und Chronik“ or „Bilder malen“
  nothing is painted, the view names no face and the scene picture takes no reference.
- A person is painted only once met, and only once it spoke or WARTE_ZUEGE turns later; the prompt comes from fixed
  parts (style, voice traits, the card's English column, the fixed lists), never with the person's name; it counts to
  the game's day limit; a refused description is not sent.
- A scene picture takes at most VORLAGEN portraits: the last narration's people (speaking first), then a hero who
  acted in that turn; each with its fixed phrase, the pictures go to the service as refs.
- The host may have a face painted again (nobody else); the old one stays until the new one is there and stays when
  the new one does not come.
- Only a seat of a round that names a face loads it; the sweep removes the faces nobody names; Live only counts.
- A hired companion (round 2, idea 9) gets its face at once, from its fixed English line, never with its name, only while
  „Gefährten anheuern“ is allowed too; its row shows it, a scene that names it takes it as a reference, the sweep keeps it.
- A person of the people catalog (Dominik 2026-10-27 „portrait fehlt bei den npc“) without a face from a round is a
  catalog picture of its world's style (fixed parts, never its name); the rules page shows it in list and detail and
  „Malen“ paints it; a face from a round stands as it is; a round's copy survives the sweep.

No wall clock: the date comes from the picture module's clock, set by the tests.
"""
import asyncio
import base64
import datetime
import io
import json
import os
import random
import shutil
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import dungeon  # noqa: E402
import dungeon_dingbild as db  # noqa: E402
import dungeon_gesicht as gesicht  # noqa: E402
import dungeon_nsc as nsc  # noqa: E402
import dungeon_stimmen as stimmen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
HERO = {"name": "Arvid", "volk": "mensch", "klasse": "krieger", "satz": ""}
NOON = datetime.datetime(2026, 3, 4, 12, 0).timestamp()


def png():
    from PIL import Image, PngImagePlugin
    meta = PngImagePlugin.PngInfo()
    meta.add_itxt("KI", "KI-Bild")
    out = io.BytesIO()
    Image.new("RGB", (db.SIZE, db.SIZE), (40, 60, 90)).save(out, "PNG", pnginfo=meta)
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
    db._files["m"] = None


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Gesicht Greta")

    def setUp(self):
        helpers.keep_chat(self, "dungeon", "dungeon_nsc", "dungeon_gesicht", "dungeon_bilder", "bilder", "dungeon_gefaehrte", "dungeon_personen")
        helpers.set_config(dungeon=True, dungeon_nsc=True, dungeon_gesicht=True, dungeon_bilder=False, bilder=True)
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
        # the names rule (bilder.names) refuses words of every profile's name; profiles other modules leave behind
        # would refuse fixed words of the prompts here (as in test_dungeon_dingbild, red to V01.1.043)
        for target, new in (("dungeon_dingbild.clock", lambda: self.now[0]), ("bilder.names", lambda uid: set())):
            p = mock.patch(target, new)
            p.start()
            self.addCleanup(p.stop)
        gesicht._malt.clear()
        gesicht._vorlagen.clear()
        gesicht._sweep[0] = 0.0
        gesicht._day.clear()                                        # today's numbers from zero (the counter's own day)
        self.calls, self.nsfw = [], [0.01]

        async def no_wait(*a, **k):
            return 0

        async def call(path, body=None, timeout=0):
            self.calls.append(body)
            d = {"png": base64.b64encode(PNG).decode(), "w": body["width"], "h": body["height"], "seconds": 1.0}
            if self.nsfw[0] is not None:
                d["nsfw"] = self.nsfw[0]
            return 200, d
        self.spawned = []

        def run(coro, name=""):
            self.spawned.append(name)
            coro.close()
        for target, new in (("vorrang.quiet", no_wait), ("bilder.call", call), ("dungeon_gesicht.spawn", run)):
            p = mock.patch(target, new)
            p.start()
            self.addCleanup(p.stop)

    def _image(self, on):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c.setdefault("image", {})["enabled"] = on
        helpers.write_config(c)

    def new_round(self, **kw):
        b = {"titel": "Die Glocke", "welt": "fantasy", "ton": 12, "zug_s": 120, "stunden": 6, "held": dict(HERO)}
        b.update(kw)
        r = self.c.post("/api/profile/dungeon/runde", json=b)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["rid"]

    def meet(self, rid, name="Mara", spoke=True, said="", zug=None):
        """A person of the truth with its card, met in the last narration (which names it), its voice heard or not."""
        r = dungeon.rules()
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            if zug is not None:
                rd["zug"] = zug
            w = rd.setdefault("wahrheit", {"personen": []})
            w.setdefault("personen", []).append({"name": name, "rolle": "", "ziel": "", "sprache": "", "geschlecht": "weiblich"})   # written on the card (V01.1.162)
            nsc.sync(r, rd, random.Random(7))
            rd["nsc"][name.lower()]["gesehen"] = rd.get("zug", 0)
            if spoke:
                n = stimmen.data()["npc"]
                rd.setdefault("npc_stimmen", {})[name.lower()] = dict({k: next(iter(n[k])) for k in stimmen.MERKMALE}, alter="alt", geschlecht="weiblich")
            npc = [{"name": name, "sagt": said}] if said else []
            dungeon._log(rd, "dm", text=f"{name} steht am Tresen und nickt.", npc=npc)
            dungeon._write(d)

    def paint_all(self):
        jobs = gesicht.queue()
        for job in jobs:
            asyncio.run(gesicht.paint(*job))
        db._files["m"] = None
        return jobs

    def card(self, rid, name="mara"):
        return dungeon._read()["runden"][rid]["nsc"][name]


class Faces(Base):
    def test_off_paints_nothing_and_names_no_face(self):
        rid = self.new_round()
        self.meet(rid)
        for off in ({"dungeon_gesicht": False}, {"dungeon_nsc": False}, {"bilder": False}):
            helpers.set_config(**dict({"dungeon_gesicht": True, "dungeon_nsc": True, "bilder": True}, **off))
            self.assertEqual(gesicht.queue(), [], off)
            self.assertEqual(gesicht.vorlagen(dungeon.rules(), dungeon._read()["runden"][rid]), ([], ""))
        self.assertEqual(self.calls, [])
        helpers.set_config(dungeon_gesicht=False, dungeon_nsc=True, bilder=True)
        v = self.c.get(f"/api/profile/dungeon/{rid}").json()
        self.assertTrue(all("bild" not in p for p in v["nsc"]["leute"]))

    def test_a_met_person_gets_one_fixed_portrait(self):
        rid = self.new_round()
        self.meet(rid, "Mara", spoke=False, zug=3)
        self.assertEqual(gesicht.queue(), [])                       # not spoken yet: wait WARTE_ZUEGE turns
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][rid]["zug"] += gesicht.WARTE_ZUEGE
            dungeon._write(d)
        jobs = self.paint_all()
        self.assertEqual(len(jobs), 1)
        _, key, n, p = jobs[0]
        rd = dungeon._read()["runden"][rid]
        x = rd["nsc"]["mara"]
        self.assertEqual(key, "mara")
        self.assertTrue(p.startswith(dungeon.style(dungeon.rules(), rd)) and p.endswith(dungeon.BILD_ENDE), p)
        self.assertIn(gesicht.GESICHT_EN, p)
        for f in ("beruf", "aussehen", "art"):
            if f in x["karte"]:
                self.assertIn(x["karte"][f][1], p)                  # the card's English column
        self.assertNotIn("Mara", p)                                 # never the person's name
        self.assertTrue(db._ok_text(p, dungeon.rules()), p)
        self.assertEqual(x["gesicht"]["st"], "ok")
        self.assertTrue(os.path.exists(dungeon.bild_file(n)))
        self.assertEqual(gesicht.queue(), [])                       # once
        self.assertEqual(len(self.calls), 1)
        v = self.c.get(f"/api/profile/dungeon/{rid}").json()
        self.assertEqual(next(q for q in v["nsc"]["leute"] if q["name"] == "Mara")["bild"], n)
        self.assertEqual(v["nsc_geheim"]["Mara"]["gesicht"], "ok")
        self.assertEqual(self.c.get(f"/api/profile/dungeon/ding/{n}").status_code, 200)
        c2, _ = profile("Gesicht Gustav")                           # not at the table: nothing
        self.assertEqual(c2.get(f"/api/profile/dungeon/ding/{n}").status_code, 404)
        self.assertEqual(self.c.get("/api/profile/dungeon/ding/nsc-0123").status_code, 404)

    def test_the_voice_decides_age_and_gender_and_the_picture_book_stays_soft(self):
        rid = self.new_round()
        self.meet(rid, "Mara")
        rd = dungeon._read()["runden"][rid]
        self.assertTrue(gesicht.text(rd, rd["nsc"]["mara"]).startswith("an old woman"))
        kid = self.new_round(titel="Kinder", ton=min(t["id"] for t in dungeon.rules()["toene"]), held=dict(HERO, name="Ole"))
        self.meet(kid, "Mara")
        rk = dungeon._read()["runden"][kid]
        p, why = gesicht.prompt(dungeon.rules(), rk, "mara", rk["nsc"]["mara"])
        self.assertEqual(why, "")
        self.assertTrue(p.startswith(dungeon.BILD_KIND))
        self.assertFalse(any(x in p for x in db.SANFT))

    def test_the_day_limit_and_the_word_list_hold(self):
        rid = self.new_round()
        self.meet(rid)
        with mock.patch("dungeon._bild_tag_voll", lambda *a: True):
            self.assertEqual(gesicht.queue(), [])
        self.assertEqual(self.card(rid)["gesicht"]["st"], "tag")
        self.assertEqual(gesicht.queue(), [])                       # not again the same day
        self.now[0] += 86400
        with mock.patch("dungeon.picture_text", lambda r, rd, t: ("", "wortliste")):
            self.assertEqual(gesicht.queue(), [])
        self.assertEqual(self.card(rid)["gesicht"]["st"], "weg")
        self.assertEqual(self.calls, [])


class Reference(Base):
    def test_the_scene_takes_the_faces_of_its_people_then_a_hero(self):
        rid = self.new_round()
        self.meet(rid, "Mara")
        self.meet(rid, "Odric")
        self.meet(rid, "Selda")
        self.paint_all()
        faces = {k: self.card(rid, k)["gesicht"]["n"] for k in ("mara", "odric", "selda")}
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            dungeon._log(rd, "dm", text="Selda flüstert, Mara lacht laut.", npc=[{"name": "Odric", "sagt": "Ruhe!"}])
            names, extra = gesicht.vorlagen(dungeon.rules(), rd)
        self.assertEqual(names, [faces["odric"], faces["selda"]])     # speaking first, then named in order; at most two
        self.assertEqual(extra, ", the old woman from reference image 1 with the same face, the old woman from reference image 2 with the same face")
        # a hero who acted in the turn takes a free place
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            pid, p = next((k, p) for k, p in rd["plaetze"].items() if p.get("held"))
            p["held"]["bild"] = p["held"]["stufe"]
            dungeon._bild_save("held-" + p["held"]["hid"], PNG)
            dungeon._log(rd, "aktion", pid=pid, name="Arvid", text="Ich frage Mara.")
            dungeon._log(rd, "dm", text="Mara zuckt mit den Schultern.", npc=[])
            names, extra = gesicht.vorlagen(dungeon.rules(), rd)
            dungeon._write(d)
        self.assertEqual(names, [faces["mara"], "held-" + p["held"]["hid"]])
        self.assertTrue(extra.endswith("the hero from reference image 2 with the same face"))

    def test_the_scene_picture_sends_the_faces_as_references(self):
        rid = self.new_round()
        self.meet(rid, "Mara")
        self.paint_all()
        r = dungeon.rules()
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            dungeon._log(rd, "dm", text="Mara reicht euch die Klinge.", npc=[])
            bid, prompt = dungeon.queue_scene(r, d, rid, rd, "a smithy with a glowing forge")
            dungeon._write(d)
        self.assertIn("from reference image 1 with the same face", prompt)
        self.calls.clear()
        asyncio.run(dungeon.paint_scene(rid, bid, prompt))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.calls[0]["refs"]), 1)
        self.assertEqual(base64.b64decode(self.calls[0]["refs"][0])[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(gesicht._vorlagen, {})
        helpers.set_config(dungeon_gesicht=False)                   # off: the scene comes without a reference
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            rd["bild_zug"] = -99
            bid, prompt = dungeon.queue_scene(r, d, rid, rd, "a smithy with a glowing forge")
            dungeon._write(d)
        self.assertNotIn("reference image", prompt)
        self.calls.clear()
        asyncio.run(dungeon.paint_scene(rid, bid, prompt))
        self.assertNotIn("refs", self.calls[0])


class Again(Base):
    def test_only_the_host_paints_again_and_the_old_face_stays_until_the_new(self):
        rid = self.new_round()
        self.meet(rid)
        self.paint_all()
        old = self.card(rid)["gesicht"]["n"]
        c2, _ = profile("Gesicht Gustav")
        self.assertEqual(c2.post(f"/api/profile/dungeon/{rid}/gesicht", json={"name": "Mara"}).status_code, 404)
        r = self.c.post(f"/api/profile/dungeon/{rid}/gesicht", json={"name": "Mara"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["nsc_geheim"]["Mara"]["gesicht"], "malt")
        self.assertEqual(next(q for q in r.json()["nsc"]["leute"] if q["name"] == "Mara")["bild"], old)   # the old one meanwhile
        self.assertEqual(self.spawned, ["dungeon-gesicht"])
        self.assertEqual(self.c.post(f"/api/profile/dungeon/{rid}/gesicht", json={"name": "Mara"}).status_code, 409)   # on its way
        g = self.card(rid)["gesicht"]
        self.assertEqual((g["st"], g["alt"]), ("malt", old))
        asyncio.run(gesicht.paint(rid, "mara", g["n"], "x"))
        new = self.card(rid)["gesicht"]
        self.assertEqual((new["st"], new["n"]), ("ok", g["n"]))
        self.assertFalse(os.path.exists(dungeon.bild_file(old)))
        # a new one that does not come keeps the old
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][rid]["nsc"]["mara"]["gesicht"]["st"] = "neu"
            dungeon._write(d)
        self.nsfw[0] = 0.99
        self.paint_all()
        self.assertEqual(self.card(rid)["gesicht"], {"n": new["n"], "st": "ok", "day": db._date()})
        self.assertTrue(os.path.exists(dungeon.bild_file(new["n"])))

    def test_the_sweep_keeps_only_named_faces_and_live_counts(self):
        rid = self.new_round()
        self.meet(rid)
        self.paint_all()
        n = self.card(rid)["gesicht"]["n"]
        dungeon._bild_save("nsc-00000000000000aa", PNG)
        db._files["m"] = None
        self.assertEqual(gesicht.sweep(self.now[0]), 1)
        self.assertFalse(os.path.exists(dungeon.bild_file("nsc-00000000000000aa")))
        self.assertTrue(os.path.exists(dungeon.bild_file(n)))
        live = gesicht.for_live()
        self.assertEqual((live["da"], live["gemalt"]), (1, 1))
        self.assertTrue(all(isinstance(v, (int, bool)) for v in live.values()))


class Companions(Base):
    SATZ = ["Söldnerin mit Speer, wortkarg und zuverlässig.", "A spear-carrying sellsword, curt and reliable."]

    def hire(self, rid):
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][rid].setdefault("gefaehrten", []).append(
                {"k": "gf:grete", "id": "grete", "name": ["Grete", "Grete"], "satz": list(self.SATZ), "hid": "", "stufe": 1, "leben": 8,
                 "max": 8, "kapitel": d["runden"][rid].get("kapitel", 0), "aus": "", "moral": False})
            dungeon._write(d)

    def test_a_hired_companion_gets_its_face_at_once(self):
        helpers.set_config(dungeon_gefaehrte=False)
        rid = self.new_round()
        self.hire(rid)
        self.assertEqual(gesicht.queue(), [])                       # „Gefährten anheuern“ off: no face
        helpers.set_config(dungeon_gefaehrte=True, dungeon_nsc=False)   # the cards' switch is not needed for it
        jobs = self.paint_all()
        self.assertEqual(len(jobs), 1)
        _, key, n, p = jobs[0]
        self.assertEqual(key, "gf:grete")
        rd0 = dungeon._read()["runden"][rid]
        self.assertIn("a companion of the heroes, a spear-carrying sellsword, curt and reliable", p)
        self.assertIn("a middle aged woman, a companion", p)            # gender and age from the data (review Z7)
        self.assertTrue(gesicht.text(rd0, {"k": "gf:wuschel", "id": "wuschel", "satz": ["", "A shaggy dog."]}).startswith(
            gesicht.GEFAEHRTE_ART_EN["tier"]))
        self.assertIn(gesicht.GESICHT_EN, p)
        self.assertNotIn("Grete", p)                                # never the name
        self.assertEqual(gesicht.queue(), [])                       # once
        rd = dungeon._read()["runden"][rid]
        self.assertEqual(rd["gefaehrten"][0]["gesicht"]["st"], "ok")
        v = self.c.get(f"/api/profile/dungeon/{rid}").json()
        self.assertEqual(v["gefaehrten"][0]["bild"], n)
        self.assertEqual(self.c.get(f"/api/profile/dungeon/ding/{n}").status_code, 200)
        c2, _ = profile("Gesicht Gustav")                           # not at the table: nothing
        self.assertEqual(c2.get(f"/api/profile/dungeon/ding/{n}").status_code, 404)
        with dungeon._lock:                                         # a part of a word is no name (review 2026-10-27 Z14)
            d = dungeon._read()
            dungeon._log(d["runden"][rid], "dm", text="Die Gretelsuppe dampft.", npc=[])
            self.assertEqual(gesicht.vorlagen(dungeon.rules(), d["runden"][rid]), ([], ""))
        # a scene that names the companion takes its face
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            dungeon._log(rd, "dm", text="Grete hebt den Speer und lauscht.", npc=[])
            names, extra = gesicht.vorlagen(dungeon.rules(), rd)
        self.assertEqual(names, [n])
        self.assertEqual(extra, ", the companion from reference image 1 with the same face")
        self.assertIn(n, gesicht.keep(dungeon._read()))
        self.assertEqual(gesicht.sweep(self.now[0]), 0)
        self.assertTrue(os.path.exists(dungeon.bild_file(n)))
        helpers.set_config(dungeon_gefaehrte=False)                 # off again: the row names no face
        self.assertNotIn("bild", (self.c.get(f"/api/profile/dungeon/{rid}").json().get("gefaehrten") or [{}])[0])


class Katalog(Base):
    def setUp(self):
        super().setUp()
        import dungeon_personen as pers
        self.pers = pers
        if os.path.exists(pers.FILE):
            os.remove(pers.FILE)
        self.addCleanup(lambda: os.path.exists(pers.FILE) and os.remove(pers.FILE))
        n = stimmen.data()["npc"]
        stimme = dict({k: next(iter(n[k])) for k in stimmen.MERKMALE}, alter="alt", geschlecht="weiblich")
        pers._save({"silas": {"id": "silas", "name": "Silas", "welt": "fantasy", "karte": {"beruf": ["Mystikerin", "mystic"],
                    "aussehen": ["wirkt zerstreut", "seems absent-minded"]}, "wesen": {}, "rolle": "", "ziel": "", "stimme": stimme,
                    "haltung": {}, "treffen": 1, "made": 1, "t": 1, "stand": "runde"},
                    "odo": {"id": "odo", "name": "Odo", "welt": "fantasy", "karte": {}, "wesen": {}, "rolle": "", "ziel": "",
                            "stimme": {}, "haltung": {}, "treffen": 1, "made": 1, "t": 1, "stand": "runde", "gesicht": {"n": "nsc-00000000000000bb"}}})
        dungeon._bild_save("nsc-00000000000000bb", PNG)                  # Odo's face from a round
        db._files["m"] = None

    def test_a_catalog_person_gets_its_face(self):
        r = dungeon.rules()
        silas = self.pers.load()["silas"]
        s, p = db.person_text(r, silas)
        self.assertEqual(db.people(r, s), [])                              # off: „Bilder für Ausrüstung“, faces and catalog
        helpers.set_config(dungeon_bilder=True, dungeon_personen=True)
        want = db.people(r, s)
        self.assertEqual([n for n, _, _ in want], [db.name_of(p)])          # Silas only: Odo has a face from a round
        self.assertIn((db.name_of(p), p), db.missing(r))                    # the night run and „Alle Bilder malen“ paint it
        self.assertTrue(p.startswith(s) and p.endswith(dungeon.BILD_ENDE), p)
        self.assertIn(gesicht.GESICHT_EN, p)
        self.assertIn("an old woman (mystic) who seems absent-minded", p)
        self.assertNotIn("Silas", p)
        self.assertTrue(db._ok_text(p, r), p)
        K = "/api/admin/dungeon/katalog/personen"
        rows = {x["id"]: x for x in ADMIN.get(K).json()["zeilen"]}
        self.assertEqual((rows["silas"]["bild"], rows["odo"]["bild"]), ("", "nsc-00000000000000bb"))
        self.assertTrue(ADMIN.get(K).json()["bilder_an"])
        x = ADMIN.post(K + "/bild", json={"id": "silas", "was": "malen"})   # „🖌 Malen“ on the rules page
        self.assertEqual(x.status_code, 200, x.text)
        db._files["m"] = None
        self.assertEqual(x.json()["bild"], db.name_of(p))
        self.assertEqual({x["id"]: x["bild"] for x in ADMIN.get(K).json()["zeilen"]}["silas"], db.name_of(p))
        self.assertEqual(ADMIN.get(f"/api/admin/dungeon/bild/{db.name_of(p)}").status_code, 200)
        self.assertIn(self.c.post(K + "/bild", json={"id": "silas", "was": "malen"}).status_code, (401, 403))
        self.assertEqual(ADMIN.post(K + "/bild", json={"id": "niemand", "was": "malen"}).status_code, 404)
        # a round that took Silas over keeps the same face, the sweep keeps it while the round names it
        rid = self.new_round()
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][rid]["nsc"] = {"silas": {"name": "Silas", "gesicht": {"n": db.name_of(p), "st": "ok"}, "gesehen": 0}}
            dungeon._write(d)
        self.pers._save({k: v for k, v in self.pers.load().items() if k != "silas"})
        db.sweep(self.now[0], force=True)
        self.assertTrue(os.path.exists(dungeon.bild_file(db.name_of(p))))
        helpers.set_config(dungeon_gesicht=False)                           # off: nothing more to paint, the faces stay
        self.assertEqual(db.people(r, s), [])
        self.assertFalse(ADMIN.get(K).json()["bilder_an"])


if __name__ == "__main__":
    unittest.main()
