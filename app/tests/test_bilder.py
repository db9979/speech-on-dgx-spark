"""Bilder malen (bilder.py, bild_server.py, bildmodell.py; plan plaene/bildgenerierung.md, Dominik 2026-10-14
„1c 2a 3a 4a 5a 6a 7a 8b“): off by default and without the installed model; never for guests or blocked profiles;
text from outside never starts a picture; the word list, the names rule and the image check refuse with fixed rules
(no picture without the check); limits per profile; only the profile's own files, sent as PNG with nosniff; journal
lines without prompts or names; the service checks every field itself. The picture service is faked (no GPU);
nothing depends on the time of day."""
import asyncio
import base64
import contextlib
import io
import json
import os
import unittest
import urllib.parse
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import admin as admin_mod  # noqa: E402
import bilder  # noqa: E402
import extras  # noqa: E402
import features  # noqa: E402
import intent  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import bild_server  # noqa: E402
import bildmodell  # noqa: E402

HOME = ("192.168.178.20", 50000)
bilder.BACKGROUND = False      # the tests run the job themselves


def client():
    return TestClient(panel.app, client=HOME)


def admin():
    c = client()
    assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    return c


def image(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c.setdefault("image", {}).update(kw)
    helpers.write_config(c)


def block(uid, yes=True):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        deny = dict(json.load(f)["chat"].get("deny") or {})
    deny["bilder"] = [u for u in deny.get("bilder", []) if u != uid] + ([uid] if yes else [])
    helpers.set_config(deny=deny)


def profile(name, pin="1234"):
    a = admin()
    r = a.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = client()
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    prof = next(u for u in profiles._load()["users"] if u["name"] == name)
    block(prof["id"], False)
    return c, prof


def png(w=64, h=48):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


def fake(nsfw=0.01, code=200, detail=None, data=None):
    """A stand-in for bild_server's /v1/bild (bilder.call)."""
    calls = []

    async def call(path, body=None, timeout=0):
        calls.append((path, body))
        if code != 200:
            return code, {"detail": detail}
        return 200, {"png": base64.b64encode(data if data is not None else png()).decode(), "seconds": 2.5,
                     "nsfw": nsfw, "w": body["width"], "h": body["height"], "seed": -1, "refs": 0}
    return call, calls


async def no_wait(job, sleep=None):
    return 0


def run(j):
    with mock.patch("vorrang.quiet", no_wait):
        asyncio.run(bilder._work(j))


class On(unittest.TestCase):
    def setUp(self):
        helpers.set_config(bilder=True)
        image(enabled=True)

    def tearDown(self):
        helpers.set_config(bilder=False)
        image(enabled=False)
        bilder._jobs.clear()
        bilder._recent.clear()


class Off(unittest.TestCase):
    def test_off_by_default_and_without_the_model(self):
        with open(os.path.join(os.path.dirname(bilder.__file__), "..", "config.default.json")) as f:
            d = json.load(f)
        self.assertFalse(d["chat"]["bilder"])
        self.assertFalse(d["image"]["enabled"])
        self.assertNotIn("chat.bilder", features.DEFAULT_ON)
        c, prof = profile("Malerin Aus")
        self.assertEqual(c.get("/api/bilder").status_code, 403)
        helpers.set_config(bilder=True)            # switched on, but the model is not installed
        try:
            self.assertFalse(features.allowed(bilder.KEY, prof["id"]))
            self.assertEqual(c.get("/api/bilder").status_code, 403)
            self.assertIn("einzurichten", features.missing_text("bilder", prof["id"]))
        finally:
            helpers.set_config(bilder=False)
        o = bilder.offer({"who": prof, "own": True, "text": "Mal mir eine Katze"})
        self.assertEqual(o["tools"], [])           # asked while off: no tool, only where to switch it on
        self.assertIn("Bilder malen", o["hint"])


class Access(On):
    def test_guests_and_blocked_profiles_never_paint(self):
        self.assertIsNone(bilder.offer({"who": None, "own": False, "text": "Mal mir eine Katze"}))
        self.assertIn(client().get("/api/bilder").status_code, (401, 403))
        c, prof = profile("Malerin Gesperrt")
        self.assertEqual(c.get("/api/bilder").status_code, 200)
        block(prof["id"])
        try:
            self.assertFalse(features.allowed(bilder.KEY, prof["id"]))
            self.assertEqual(c.get("/api/bilder").status_code, 403)
            self.assertEqual(c.post("/api/bilder", json={"wunsch": "Ein Haus"}).status_code, 403)
            o = bilder.offer({"who": prof, "own": True, "text": "Mal mir eine Katze"})
            self.assertEqual(o["tools"], [])
            with self.assertRaises(ValueError):
                bilder.start(prof, "a cat", "Katze", "quadrat")
        finally:
            block(prof["id"], False)

    def test_only_on_the_persons_own_words_and_locked_after_outside_text(self):
        _, prof = profile("Malerin Worte")
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "Wie wird das Wetter morgen?"}))
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "Mal mir was", "client": "mcp"}))
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "Mal mir eine Katze", "private": False}))
        o = extras.offer({"who": prof, "own": True, "text": "Mal mir eine Katze auf einem Skateboard"})
        self.assertIn("bild_malen", [t["function"]["name"] for t in o["tools"]])
        # a changing tool: chat.py locks it after mail, web or document text, the Notaus from stage 2 on
        self.assertIn("bild_malen", o["changes"])
        self.assertIn("bild_malen", notaus.locked_tools(2, o["changes"]))
        self.assertNotIn("bild_malen", notaus.locked_tools(1, o["changes"]))

    def test_a_short_yes_after_a_wish_still_paints(self):
        """Dominik 2026-10-14: „Erstelle mir ein Bild … mit Putin“ was refused, the assistant asked „fiktiv?“, the
        answer „ja fiktiv“ then searched the web. A short yes within FOLLOW_SECONDS after the own wish keeps the
        tool; without a wish before, or later, or a long message, it does not."""
        _, prof = profile("Malerin Rueckfrage")
        bilder._recent.pop(prof["id"], None)
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "ja fiktiv"}))
        self.assertIsNotNone(bilder.offer({"who": prof, "own": True, "text": "Erstelle mir ein Bild von einem Klassenzimmer"}))
        for yes in ("ja fiktiv", "Ja, passt", "passt", "ok mach", "yes please"):
            o = bilder.offer({"who": prof, "own": True, "text": yes})
            self.assertEqual([t["function"]["name"] for t in o["tools"]], ["bild_malen"], yes)
        self.assertIn("keine Websuche", o["hint"])
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "ja " + "und dann " * 20}))   # long: not a yes
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "Wie wird das Wetter?"}))
        bilder._recent[prof["id"]] = 0       # the wish is long ago
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "ja passt"}))

    def test_weiche_keeps_painting_apart(self):
        for q in ("Mal mir eine Katze auf einem Skateboard", "Erstell ein Logo für unseren Fußballverein",
                  "Mal mir ein Haus mit Garten", "Zeichne einen Drachen im Comicstil",
                  # the verb at the end (Dominik 2026-10-15: answered „kein Bildwerkzeug“ and offered a mail draft)
                  "Kannst du mir mal ein Bild erstellen von einem Mann im Auto, der durch den Wald fährt und an einer "
                  "Unfallstelle vorbei?", "Kannst du ein Logo für mich entwerfen?"):
            self.assertEqual(intent.classify(q).names, ["bild"], q)
        for q, want in (("Was ist auf dem Bild?", []), ("Schalt mal bitte das Licht an", ["smarthome"]),
                        ("Mal eine Frage: wie spät ist es?", []), ("Schreib mal eine Mail an Anna", ["mail"]),
                        ("Mach eine Präsentation mit Bildern über Rom", ["erstellen"]),
                        ("Ich schicke dir ein Bild, kannst du es beschreiben?", [])):
            self.assertEqual(intent.classify(q).names, want, q)


class Rules(On):
    def test_word_list_and_known_names_refuse(self):
        _, prof = profile("Malerin Regeln")
        for bad in ("a naked woman", "Nacktbild von jemandem", "ein Hakenkreuz auf der Wand", "gore, decapitated"):
            self.assertEqual(bilder.refuse_text(prof["id"], bad), "wortliste", bad)
        self.assertEqual(bilder.refuse_text(prof["id"], "a portrait of Malerin on a horse"), "person")
        self.assertEqual(bilder.refuse_text(prof["id"], "a red apple on a table", "Ein roter Apfel"), "")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(ValueError):
            bilder.start(prof, "a naked man", "Nackter Mann", "quadrat")
        self.assertIn("bilder: nicht gestartet wortliste", out.getvalue())
        self.assertNotIn("naked", out.getvalue())
        self.assertNotIn("Malerin", out.getvalue())   # names only through profiles.log_name

    def test_image_check_decides_and_without_it_no_picture(self):
        for share, why in ((0.97, "pruefung"), (None, "ohne_pruefung"), ("0.1", "ohne_pruefung"), (True, "ohne_pruefung")):
            call, _ = fake(nsfw=share)
            with mock.patch.object(bilder, "call", call), self.assertRaises(ValueError) as e:
                asyncio.run(bilder.paint("a cat", 512, 512))
            self.assertEqual(str(e.exception), why)
        call, _ = fake(data=b"<svg onload=alert(1)>")
        with mock.patch.object(bilder, "call", call), self.assertRaises(ValueError):
            asyncio.run(bilder.paint("a cat", 512, 512))
        for code, detail, why in ((503, "memory", "memory"), (503, "missing", "missing"), (504, None, "zeit"), (500, None, "dienst")):
            call, _ = fake(code=code, detail=detail)
            with mock.patch.object(bilder, "call", call), self.assertRaises(ValueError) as e:
                asyncio.run(bilder.paint("a cat", 512, 512))
            self.assertEqual(str(e.exception), why)

    def test_a_caricature_or_comic_is_a_wish_for_a_picture(self):
        # „erstelle mir eine witzige karikatur comic stiel.“ went to the plain model, which said it cannot draw (Dominik 2026-10-16)
        for wish in ("erstelle mir eine witzige karikatur comic stiel.", "Mach mir einen Comic von meinem Hund",
                     "Kannst du eine Karikatur von einem Koch erstellen?", "create a funny cartoon of a cat"):
            self.assertTrue(bilder.WORDS.search(wish), wish)
        for other in ("Ich lese gerade einen Comic.", "Was ist eine Karikatur?"):
            self.assertFalse(bilder.WORDS.search(other), other)

    def test_sizes_follow_the_format_and_the_admin_limit(self):
        for fmt in bilder.FORMATS:
            for side in (512, 1024, 1408):
                w, h = bilder.size(fmt, side)
                self.assertEqual(max(w, h), side)
                self.assertEqual((w % 16, h % 16), (0, 0))
                self.assertLessEqual(w * h, bild_server.MAX_PIXELS)
        self.assertEqual(bilder.size("quer", 1024), (1024, 768))
        self.assertEqual(bilder.size("hoch", 1024), (768, 1024))
        self.assertEqual(bilder.size("unbekannt", 1024), (1024, 1024))


class Jobs(On):
    def test_paint_store_show_and_delete(self):
        c, prof = profile("Malerin Ablage")
        uid = prof["id"]
        bilder.clear(uid)
        call, calls = fake()
        out = io.StringIO()
        with mock.patch.object(bilder, "call", call), contextlib.redirect_stdout(out):
            j = bilder.start(prof, "a red apple on a table, oil painting", "Ein roter Apfel", "quer")
            run(bilder._jobs[j["id"]])
        self.assertEqual(calls[0][1]["width"], 1024)
        self.assertEqual(calls[0][1]["height"], 768)
        self.assertEqual(bilder._jobs[j["id"]]["state"], "done")
        log = out.getvalue()
        self.assertIn("bilder: auftrag 1024x768 quer chat", log)
        self.assertIn("bilder: gemalt 1024x768", log)
        self.assertNotIn("apple", log)
        self.assertNotIn("Apfel", log)
        d = c.get("/api/bilder").json()
        self.assertEqual(len(d["pics"]), 1)
        p = d["pics"][0]
        self.assertEqual((p["prompt"], p["wish"], p["format"]), ("a red apple on a table, oil painting", "Ein roter Apfel", "quer"))
        self.assertEqual(c.get("/api/bilder/job/" + j["id"]).json()["pic"]["id"], p["id"])
        # the chat finds the picture again by its job (after a reload, on every device): the answer keeps the job id
        self.assertEqual(p["job"], j["id"])
        kept = profiles._att([{"k": "bild", "p": "a red apple", "j": j["id"]}, {"k": "bild", "p": "x", "j": "../etc"}])
        self.assertEqual(kept, [{"k": "bild", "p": "a red apple", "j": j["id"]}, {"k": "bild", "p": "x"}])
        # an hour later the panel forgot the job; the kept picture still answers for it (only for its own profile)
        bilder._jobs.pop(j["id"])
        again = c.get("/api/bilder/job/" + j["id"]).json()
        self.assertEqual((again["state"], again["pic"]["id"]), ("done", p["id"]))
        self.assertEqual(c.get("/api/bilder/job/0123456789ab").status_code, 404)
        r = c.get(f"/api/bilder/{p['id']}/datei")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertTrue(r.content.startswith(bilder.PNG_SIG))
        self.assertIn("attachment", c.get(f"/api/bilder/{p['id']}/datei?dl=1").headers["content-disposition"])
        # another profile never sees it
        c2, _ = profile("Malerin Fremd")
        self.assertEqual(c2.get(f"/api/bilder/{p['id']}/datei").status_code, 404)
        self.assertEqual(c2.get("/api/bilder/job/" + j["id"]).status_code, 404)
        self.assertEqual(c2.delete(f"/api/bilder/{p['id']}").status_code, 404)
        # Daten löschen of the Freigabe counts and removes the same
        count, clear = features.OWN["bilder"]
        self.assertEqual(count(uid), 1)
        self.assertEqual(c.delete(f"/api/bilder/{p['id']}").status_code, 200)
        self.assertEqual(c.get("/api/bilder").json()["pics"], [])
        self.assertEqual(count(uid), 0)

    def test_iphone_app_shows_the_picture_in_its_chat(self):
        """iOS (Dominik 2026-10-14): the app gets the card's event and may read the job and the picture file of its
        own profile with its key; nothing else of Ich → Bilder (looking at all, painting, deleting stays an area)."""
        c, prof = profile("Malerin iPhone")
        bilder.clear(prof["id"])
        helpers.set_config(iphone=True)
        try:
            r = c.post("/api/profile/iphone/pair", json={"base": "https://spark.example"})
            self.assertEqual(r.status_code, 200, r.text)
            code = urllib.parse.parse_qs(urllib.parse.urlparse(r.json()["link"]).query)["code"][0]
            token = TestClient(panel.app).post("/api/iphone/pair", json={"code": code, "name": "Malerin"}).json()["token"]
            call, _ = fake()
            out = asyncio.Queue()
            with mock.patch.object(bilder, "call", call), contextlib.redirect_stdout(io.StringIO()):
                said = asyncio.run(bilder.tool("bild_malen", {"prompt_en": "a green frog", "wunsch": "Ein Frosch"},
                                               {"who": prof, "own": True, "client": "iphone", "out": out}))
                ev = out.get_nowait()
                run(bilder._jobs[ev["job"]])
            self.assertEqual(ev["type"], "bild")
            self.assertIn("hier im Chat", said)
            app = TestClient(panel.app)
            h = {"X-Speech-Device": token}
            j = app.get("/api/bilder/job/" + ev["job"], headers=h).json()
            self.assertEqual(j["state"], "done")
            f = app.get(f"/api/bilder/{j['pic']['id']}/datei", headers=h)
            self.assertEqual(f.status_code, 200)
            self.assertTrue(f.content.startswith(bilder.PNG_SIG))
            # the list is Meine Sachen → Bilder (iphone.THINGS): only with the release of Bilder malen for the profile
            self.assertEqual(app.get("/api/bilder", headers=h).status_code, 200)
            helpers.set_config(deny={"bilder": [prof["id"]]})
            self.assertEqual(app.get("/api/bilder", headers=h).status_code, 401)
            self.assertEqual(app.delete(f"/api/bilder/{j['pic']['id']}", headers=h).status_code, 401)
            self.assertEqual(app.post("/api/bilder", json={"wunsch": "x"}, headers=h).status_code, 401)
        finally:
            helpers.set_config(iphone=False, deny={})
            bilder.clear(prof["id"])

    def test_page_paints_the_persons_own_sentence(self):
        c, prof = profile("Malerin Seite")
        bilder.clear(prof["id"])
        r = c.post("/api/bilder", json={"wunsch": "Ein Leuchtturm bei Sturm <b>", "format": "hoch"})
        self.assertEqual(r.status_code, 200, r.text)
        j = bilder._jobs[r.json()["id"]]
        self.assertEqual(j["prompt"], "Ein Leuchtturm bei Sturm b")   # angle brackets never reach the service
        self.assertEqual((j["w"], j["h"]), (768, 1024))
        self.assertEqual(c.post("/api/bilder", json={"wunsch": "Noch eins"}).status_code, 409)   # one open job
        j["state"] = "error"
        self.assertEqual(c.post("/api/bilder", json={"wunsch": "x" * 20000}).status_code, 413)

    def test_limits_per_profile(self):
        _, prof = profile("Malerin Grenzen")
        uid = prof["id"]
        bilder.clear(uid)
        image(day_limit=2, store_mb=50)
        try:
            call, _ = fake()
            with mock.patch.object(bilder, "call", call):
                for _ in range(2):
                    run(bilder._jobs[bilder.start(prof, "a cat", "Katze", "quadrat")["id"]])
                with self.assertRaises(ValueError) as e:
                    bilder.start(prof, "a cat", "Katze", "quadrat")
                self.assertIn("Heute sind schon 2 Bilder", e.exception.args[0][0])
            # the 24 hours are counted back from now, not by the clock's day
            items = bilder.all_pics(uid)
            self.assertEqual(bilder.today_count(uid, now=max(x["t"] for x in items) + bilder.DAY_S + 1), 0)
            image(day_limit=30)
            with mock.patch.object(bilder, "used_bytes", lambda u: 50 * 1024 * 1024):
                with self.assertRaises(ValueError) as e:
                    bilder.start(prof, "a cat", "Katze", "quadrat")
                self.assertIn("ganzen Platz", e.exception.args[0][0])
        finally:
            image(day_limit=30, store_mb=500)
            bilder.clear(uid)

    def test_an_admin_has_no_daily_limit(self):
        """Dominik 2026-10-24: Tageslimits gelten nicht für Admins (coadmin.unbegrenzt); der Platz schon."""
        import coadmin
        c, prof = profile("Malerin Admin")
        uid = prof["id"]
        bilder.clear(uid)
        image(day_limit=1, store_mb=50)
        try:
            call, _ = fake()
            with mock.patch.object(bilder, "call", call), \
                    mock.patch.object(coadmin, "acts", lambda u: "admin" if u == uid else ""):
                for _ in range(3):
                    run(bilder._jobs[bilder.start(prof, "a cat", "Katze", "quadrat")["id"]])
                self.assertEqual(bilder.today_count(uid), 3)
                self.assertTrue(c.get("/api/bilder").json()["frei"])
                with mock.patch.object(bilder, "used_bytes", lambda u: 50 * 1024 * 1024), self.assertRaises(ValueError) as e:
                    bilder.start(prof, "a cat", "Katze", "quadrat")
                self.assertIn("ganzen Platz", e.exception.args[0][0])
            self.assertFalse(c.get("/api/bilder").json()["frei"])
            with self.assertRaises(ValueError) as e:        # without the role the limit is back
                bilder.start(prof, "a cat", "Katze", "quadrat")
            self.assertIn("Heute sind schon 1 Bilder", e.exception.args[0][0])
        finally:
            image(day_limit=30, store_mb=500)
            bilder.clear(uid)

    def test_notaus_holds_new_pictures(self):
        _, prof = profile("Malerin Notaus")
        with mock.patch.object(notaus, "level", lambda: 2), self.assertRaises(ValueError) as e:
            bilder.start(prof, "a cat", "Katze", "quadrat")
        self.assertIn("Notaus", e.exception.args[0][0])

    def test_maintenance_pause_holds_pictures(self):
        import wartung
        self.assertEqual(wartung.PARTS["bild"][0], "bild")   # the Dienst-Wächter id of the picture service
        _, prof = profile("Malerin Pause")
        with mock.patch.object(wartung, "paused", lambda part: part == "bild"):
            with self.assertRaises(ValueError) as e:
                bilder.start(prof, "a cat", "Katze", "quadrat")
            self.assertEqual(e.exception.args[0], bilder.REFUSED["wartung"])
            j = {"uid": prof["id"], "log": "x", "prompt": "a cat", "w": 64, "h": 64, "state": "wait"}
            run(j)
            self.assertEqual((j["state"], j["error"]), ("error", bilder.REFUSED["wartung"][0]))

    def test_paths_stay_inside_the_profile(self):
        c, prof = profile("Malerin Pfade")
        for bad in ("../../profiles", "..%2f..%2fx", "abc", "0123456789ab/../x"):
            self.assertIsNone(bilder.pic_path(prof["id"], bad))
            self.assertIn(c.get(f"/api/bilder/{bad}/datei").status_code, (404, 422))
        with self.assertRaises(ValueError):
            bilder._dir("../x")

    def test_tool_answers_with_fixed_sentences(self):
        _, prof = profile("Malerin Werkzeug")
        bilder.clear(prof["id"])
        q = asyncio.Queue()

        async def go(args):
            return await bilder.tool("bild_malen", args, {"who": prof, "client": "web", "out": q})
        res = asyncio.run(go({"prompt_en": "a dog with a hat", "wunsch": "Hund mit Hut"}))
        self.assertTrue(res.startswith("Started:"), res)
        ev = q.get_nowait()
        self.assertEqual((ev["type"], ev["prompt"]), ("bild", "a dog with a hat"))
        bilder._jobs.clear()
        res = asyncio.run(go({"prompt_en": "a nude person"}))
        self.assertTrue(res.startswith("Not done:"), res)


def data_url(data=None):
    return "data:image/png;base64," + base64.b64encode(data if data is not None else png(64, 48)).decode()


class Change(On):
    """Bilder ändern (plan plaene/bildbearbeitung.md, Stufe 2a, Dominik 2026-10-16 „Umsetzen“): an own admin switch
    under Bilder malen; the panel picks the picture by a fixed rule (the photo of this turn, the result of the last
    change, a picture of Ich → Bilder), never the model and never a picture from outside; the word list grows by
    what is never changed; the result is a new picture marked as AI-edited."""

    def setUp(self):
        super().setUp()
        helpers.set_config(bilder_aendern=True)

    def tearDown(self):
        helpers.set_config(bilder_aendern=False)
        bilder._edits.clear()
        super().tearDown()

    def turn(self, prof, text, pics=(), client="web", **ctx):
        c = dict({"who": prof, "own": True, "client": client, "private": True}, **ctx)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            r = asyncio.run(bilder.from_turn(c, text, list(pics)))
        return r, out.getvalue()

    def test_off_by_default_and_without_painting(self):
        with open(os.path.join(os.path.dirname(bilder.__file__), "..", "config.default.json")) as f:
            self.assertFalse(json.load(f)["chat"]["bilder_aendern"])
        self.assertNotIn("chat.bilder_aendern", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY[bilder.EDIT_KEY].parent, "bilder")
        c, prof = profile("Aendern Aus")
        bilder.clear(prof["id"])
        helpers.set_config(bilder_aendern=False)
        r, log = self.turn(prof, "Mach den Himmel blau", [data_url()])
        self.assertIn("nicht freigegeben", r["call"]["result"])          # said, never started
        self.assertNotIn("event", r)
        self.assertIn("bilder: nicht gestartet aendern aus fuer", log)
        self.assertEqual(bilder.jobs_of(prof["id"]), [])
        self.assertIsNone(self.turn(prof, "noch heller")[0])             # no photo: nothing to say at all
        self.assertEqual(c.post("/api/bilder/foto", content=png(), headers={"Content-Type": "image/png"}).status_code, 403)
        self.assertEqual(c.post("/api/bilder/0123456789ab/aendern", json={"wunsch": "blau"}).status_code, 403)
        with self.assertRaises(ValueError):
            bilder.start(prof, "blau", "blau", "", ref=png())
        helpers.set_config(bilder_aendern=True, bilder=False)            # needs Bilder malen as well
        self.assertFalse(features.allowed(bilder.EDIT_KEY, prof["id"]))

    def test_photo_of_this_turn_is_changed_by_the_panel(self):
        c, prof = profile("Aendern Foto")
        bilder.clear(prof["id"])
        r, log = self.turn(prof, "Mach den Himmel blau", [data_url(png(64, 48)), data_url(png(32, 32))])
        self.assertEqual(r["call"]["result"], "gestartet")
        self.assertIn("rufe kein Werkzeug auf", r["system"])
        ev = r["event"]
        self.assertEqual((ev["type"], ev["art"]), ("bild", "aendern"))
        j = bilder._jobs[ev["job"]]
        self.assertEqual((j["art"], j["von"], j["w"], j["h"]), ("aendern", "foto", 1024, 768))   # the photo's shape
        self.assertIn("bilder: auftrag aendern 1024x768", log)
        self.assertNotIn("Himmel", log)
        call, calls = fake()
        out = io.StringIO()
        with mock.patch.object(bilder, "call", call), contextlib.redirect_stdout(out):
            run(j)
        refs = calls[0][1]["refs"]
        self.assertEqual(len(refs), 1)                                   # only the first photo, as sent
        self.assertEqual(base64.b64decode(refs[0]), png(64, 48))
        self.assertNotIn("ref", j)                                        # the photo leaves the memory with the job
        self.assertIn("bilder: geaendert 1024x768", out.getvalue())
        p = c.get("/api/bilder").json()["pics"][0]
        self.assertEqual((p["art"], p["von"]), ("aendern", "foto"))
        self.assertGreaterEqual(bilder.stats()["edited"], 1)
        self.assertIn("edited", bilder.for_live())
        # elsewhere than the own chat or the iPhone app: no card, the Spark says where it is
        j["state"] = "done"
        bilder._edits.clear()
        r2, _ = self.turn(prof, "Mach daraus ein Aquarell", [data_url()], client="telegram")
        self.assertNotIn("event", r2)
        self.assertIn("Ich → Bilder", r2["system"])
        for v in bilder._jobs.values():
            if v["uid"] == prof["id"] and v["state"] == "wait":
                v["state"] = "error"
        bilder.clear(prof["id"])

    def test_chat_turn_with_a_photo_changes_it(self):
        """The whole way through /api/chat: a photo attached with a change wish starts the change before the model
        answers, the card's event comes first; a question about the photo stays with Bilder erkennen."""
        import guard
        import images
        c, prof = profile("Aendern Chat")
        bilder.clear(prof["id"])
        helpers.set_config(images=True)
        try:
            for k in [k for k in guard._rate if k[0] == "image"]:
                guard._rate.pop(k, None)

            def ask(text):
                pid = c.post("/api/chat/image", content=png(64, 48), headers={"Content-Type": "image/png"}).json()["id"]
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "images": [pid]})
                self.assertEqual(r.status_code, 200, r.text)
                log.append(out.getvalue())
                return [e for e in helpers.events(r) if e.get("type") == "bild"]
            log = []
            self.assertEqual(ask("Was ist auf dem Bild?"), [])
            self.assertNotIn("weiche: Foto mit Änderungswunsch", log[-1])
            ev = ask("Mach den Himmel blau")
            # the Weiche names it (Logs → Anfragen: not „unklar · Werkzeuge 0 von 0“), no model pick starts
            self.assertIn("weiche: Foto mit Änderungswunsch - bild", log[-1])
            self.assertIn("weiche: Absicht bild ", log[-1])
            self.assertEqual(len(ev), 1)
            self.assertEqual(ev[0]["art"], "aendern")
            j = bilder._jobs[ev[0]["job"]]
            self.assertEqual((j["art"], j["von"], j["uid"]), ("aendern", "foto", prof["id"]))
            j["state"] = "error"
        finally:
            helpers.set_config(images=False)
            images._store.clear()

    def test_ways_to_ask_for_a_change(self):
        """The person's own words for a change (Dominik 2026-10-16: „mache den bart weg“ changed nothing)."""
        for text in ("mache den bart weg", "Bart weg bitte", "Lass den Hut weg", "Mach ihn ohne Brille",
                     "Mach den Bart ab", "Kannst du den Bart wegmachen?", "Entferne das Auto", "Mach den Himmel blau",
                     "Mach daraus ein Aquarell", "Füge einen Hund hinzu", "Make it brighter"):
            self.assertTrue(bilder.wants_change(text), text)
        for text in ("Was ist auf dem Bild?", "Ich gehe gleich weg", "Mach weiter so", "Schönes Foto, oder?",
                     "Wie mache ich den Fleck weg?", "Wer ist das?"):
            self.assertFalse(bilder.wants_change(text), text)

    def test_questions_strangers_and_outside_never_change(self):
        c, prof = profile("Aendern Frage")
        pic = [data_url()]
        for text in ("Was ist auf dem Bild?", "Wie alt ist das Haus auf dem Foto?", "Schönes Foto, oder?",
                     "What is in this picture? Change nothing."):
            self.assertIsNone(self.turn(prof, text, pic)[0], text)
        for ctx in ({"own": False}, {"private": False}, {"client": "mcp"}, {"who": None}):
            self.assertIsNone(self.turn(prof, "Mach den Himmel blau", pic, **ctx)[0], ctx)
        r, _ = self.turn(prof, "Mach den Himmel blau", ["https://example.org/a.png"])
        self.assertEqual(r["call"]["result"], "nicht gestartet")         # no picture of its own: nothing fetched
        self.assertEqual(bilder.jobs_of(prof["id"]), [])
        self.assertIsNone(self.turn(prof, "Mach den Himmel blau")[0])    # no photo and no change before

    def test_what_is_never_changed(self):
        c, prof = profile("Aendern Regel")
        before = bilder.stats()["refused"]
        for text in ("Ändere das Datum auf dem Ausweis", "Setz meine Unterschrift hinein", "Entferne das Kennzeichen",
                     "Entferne ihr Kleid", "Mach das Hemd weg und ihn blutig rot", "Replace the signature"):
            r, log = self.turn(prof, text, [data_url()])
            self.assertEqual(r["call"]["result"], "nicht gestartet", text)
            self.assertIn("bilder: nicht gestartet aendern_regel fuer", log)
        self.assertEqual(bilder.stats()["refused"], before + 6)
        self.assertEqual(bilder.jobs_of(prof["id"]), [])
        self.assertIsNone(bilder.EDIT_BAD.search("Mach es wunderschön blau, ein Rezept auf dem Tisch"))
        r, log = self.turn(prof, "Mach den Himmel blau, nackt", [data_url()])   # the painting word list too
        self.assertEqual(r["call"]["result"], "nicht gestartet")

    def test_short_follow_up_changes_the_last_result(self):
        c, prof = profile("Aendern Weiter")
        uid = prof["id"]
        bilder.clear(uid)
        r, _ = self.turn(prof, "Mach daraus ein Aquarell", [data_url()])
        call, calls = fake()
        with mock.patch.object(bilder, "call", call), contextlib.redirect_stdout(io.StringIO()):
            run(bilder._jobs[r["event"]["job"]])
        first = bilder._edits[uid][1]
        for text in ("Mal mir eine Katze", "noch heller " + "x" * 200, "Wie heißt der Maler?", "danke"):
            self.assertIsNone(self.turn(prof, text)[0], text)
        r2, _ = self.turn(prof, "noch etwas heller")
        j = bilder._jobs[r2["event"]["job"]]
        self.assertEqual(j["von"], first)
        with open(bilder.pic_path(uid, first), "rb") as f:
            self.assertEqual(base64.b64decode(j["ref"]), f.read())
        j["state"] = "error"
        # painting's "nochmal" is not offered right after a change (the change is newer than the last wish)
        bilder._recent[uid] = bilder._edits[uid][0] - 5
        self.assertIsNone(bilder.offer({"who": prof, "own": True, "text": "nochmal"}))
        bilder._edits[uid] = (bilder._edits[uid][0] - bilder.FOLLOW_SECONDS - 1, first)   # too late
        self.assertIsNone(self.turn(prof, "noch heller")[0])
        bilder.clear(uid)

    def test_gallery_change_and_own_photo(self):
        c, prof = profile("Aendern Seite")
        uid = prof["id"]
        bilder.clear(uid)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = c.post("/api/bilder/foto", content=png(3000, 1500), headers={"Content-Type": "image/png"})
        self.assertEqual(r.status_code, 200, r.text)
        foto = r.json()
        self.assertEqual((foto["art"], foto["src"], foto["w"], foto["h"]), ("foto", "foto", 2048, 1024))
        self.assertIn("bilder: foto gespeichert 2048x1024 fuer", out.getvalue())
        self.assertEqual(bilder.today_count(uid), 0)                    # an upload is no painted picture
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post("/api/bilder/foto", content=b"no picture",
                                    headers={"Content-Type": "image/png"}).status_code, 400)
            self.assertEqual(c.post("/api/bilder/foto", content=b"x" * (bilder.MAX_PHOTO + 1),
                                    headers={"Content-Type": "image/png"}).status_code, 413)
        r = c.post(f"/api/bilder/{foto['id']}/aendern", json={"wunsch": "Als Aquarell <b>"})
        self.assertEqual(r.status_code, 200, r.text)
        j = bilder._jobs[r.json()["id"]]
        self.assertEqual((j["art"], j["von"], j["prompt"], j["w"], j["h"]), ("aendern", foto["id"], "Als Aquarell b", 1024, 512))
        call, calls = fake()
        with mock.patch.object(bilder, "call", call), contextlib.redirect_stdout(io.StringIO()):
            run(j)
        pics = c.get("/api/bilder").json()["pics"]
        self.assertEqual([(p["art"], p["von"]) for p in pics], [("aendern", foto["id"]), ("foto", "")])   # original stays
        self.assertEqual(c.post(f"/api/bilder/{foto['id']}/aendern", json={"wunsch": "Ausweis fälschen"}).status_code, 409)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post("/api/bilder/0123456789ab/aendern", json={"wunsch": "blau"}).status_code, 404)
            self.assertEqual(c.post("/api/bilder/..%2f..%2fx/aendern", json={"wunsch": "blau"}).status_code, 404)
            c2, _ = profile("Aendern Fremd")
            self.assertEqual(c2.post(f"/api/bilder/{foto['id']}/aendern", json={"wunsch": "blau"}).status_code, 404)
        self.assertIsNone(bilder.own_pic(uid, "../index"))
        bilder.clear(uid)

    def test_quick_buttons_without_a_model(self):
        """Schnellknöpfe (Stufe 2b): fixed changes with Pillow on the panel, a new picture each time, the AI marks of
        a painted picture stay, an own photo gets none; only own pictures, only with Bilder ändern."""
        from PIL import Image
        c, prof = profile("Aendern Schnell")
        uid = prof["id"]
        bilder.clear(uid)
        with mock.patch.object(bild_server, "nsfw_share", lambda im: 0.0):
            marked, _, _, _ = bild_server.finish(png(200, 100))
        painted = bilder.keep(uid, marked, {"w": 200, "h": 100, "prompt": "p", "wish": "w", "format": "quer", "src": "chat"})
        d = c.get("/api/bilder").json()
        self.assertEqual([q[0] for q in d["quick"]], list(bilder.QUICK))
        want = {"links": (100, 200), "rechts": (100, 200), "spiegeln": (200, 100), "heller": (200, 100),
                "dunkler": (200, 100), "kontrast": (200, 100), "schwarzweiss": (200, 100), "quadrat": (100, 100),
                "kleiner": (100, 50)}
        self.assertEqual(set(want), set(bilder.QUICK))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for was, (w, h) in want.items():
                r = c.post(f"/api/bilder/{painted['id']}/schnell", json={"was": was})
                self.assertEqual(r.status_code, 200, was + r.text)
                x = r.json()
                self.assertEqual((x["w"], x["h"], x["art"], x["von"]), (w, h, "schnell", painted["id"]), was)
                with open(bilder.pic_path(uid, x["id"]), "rb") as f:
                    im = Image.open(f)
                    im.load()
                self.assertIn("KI-erzeugt", json.dumps(im.text, ensure_ascii=False), was)   # the marks stay
        self.assertIn("bilder: schnell links 100x200 fuer", out.getvalue())
        self.assertEqual(bilder.today_count(uid), 1)                   # only the painted one counts
        self.assertGreaterEqual(bilder.stats()["quick"], 9)
        self.assertEqual(len(c.get("/api/bilder").json()["pics"]), 10)   # the original stays
        with contextlib.redirect_stdout(io.StringIO()):
            foto = c.post("/api/bilder/foto", content=png(64, 64), headers={"Content-Type": "image/png"}).json()
            r = c.post(f"/api/bilder/{foto['id']}/schnell", json={"was": "spiegeln"}).json()
            with open(bilder.pic_path(uid, r["id"]), "rb") as f:
                self.assertNotIn("KI-", json.dumps(Image.open(f).text))   # an own photo is not called AI-made
            self.assertEqual(c.post(f"/api/bilder/{foto['id']}/schnell", json={"was": "kleiner"}).status_code, 409)
            self.assertEqual(c.post(f"/api/bilder/{foto['id']}/schnell", json={"was": "loeschen"}).status_code, 400)
            self.assertEqual(c.post("/api/bilder/0123456789ab/schnell", json={"was": "links"}).status_code, 404)
            c2, _ = profile("Aendern Schnell Fremd")
            self.assertEqual(c2.post(f"/api/bilder/{foto['id']}/schnell", json={"was": "links"}).status_code, 404)
            helpers.set_config(bilder_aendern=False)
            self.assertEqual(c.post(f"/api/bilder/{foto['id']}/schnell", json={"was": "links"}).status_code, 403)
            self.assertEqual(c.get("/api/bilder").json()["quick"], [])
        bilder.clear(uid)

    def test_app_paths_and_limits(self):
        import guard
        import iphone
        import re as re_
        mine = iphone.THINGS["bilder"]                                  # Meine Sachen → Bilder
        for method, path in (("POST", "/api/bilder/0123456789ab/aendern"), ("POST", "/api/bilder/0123456789ab/schnell"),
                             ("POST", "/api/bilder/foto")):
            self.assertTrue(any(method in m and re_.fullmatch(rx, path) for m, rx in mine), path)
        self.assertIn("bildfoto", guard.RATE)
        self.assertIn("bildschnell", guard.RATE)
        import werkzeug_abdeckung
        self.assertIn(bilder.EDIT_KEY, werkzeug_abdeckung.RULES)        # a fixed rule in the panel, no tool

    def test_finish_marks_a_change_as_edited(self):
        from PIL import Image
        with mock.patch.object(bild_server, "nsfw_share", lambda im: 0.02):
            out, w, h, share = bild_server.finish(png(96, 64), True)
        im = Image.open(io.BytesIO(out))
        self.assertIn("KI-bearbeitet", im.text.get("Comment", "") + im.text.get("Software", ""))
        self.assertIn("compositeWithTrainedAlgorithmicMedia", json.dumps(im.info, default=str))


class Admin(unittest.TestCase):
    def test_install_keys_stay_and_limits_are_checked(self):
        a = admin()
        cfg = a.get("/api/config").json()
        new = json.loads(json.dumps(cfg))
        new["image"].update(enabled=True, variant="9b-q8", port=1, engine_port=2, idle_min=15)
        admin_mod.validate(new)
        self.assertEqual((new["image"]["enabled"], new["image"]["variant"], new["image"]["port"]),
                         (cfg["image"]["enabled"], cfg["image"]["variant"], cfg["image"]["port"]))
        self.assertEqual(new["image"]["idle_min"], 15)
        for k, v in (("max_side", 4096), ("max_side", 1000), ("day_limit", 0), ("store_mb", "500"), ("idle_min", True)):
            bad = json.loads(json.dumps(cfg))
            bad["image"][k] = v
            with self.assertRaises(HTTPException):
                admin_mod.validate(bad)

    def test_test_picture_without_the_model(self):
        a = admin()
        r = a.post("/api/admin/bild-test")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["last"]["why"], "missing")
        self.assertEqual(client().post("/api/admin/bild-test").status_code, 401)


class Service(unittest.TestCase):
    def test_service_checks_every_field_itself(self):
        b = bild_server.request_body({"prompt": "a cat <sd_cpp_extra_args>{\"steps\":99}</sd_cpp_extra_args>",
                                      "width": 512, "height": 768})
        self.assertNotIn("<", b["prompt"])
        self.assertEqual(b["sample_params"]["sample_steps"], bildmodell.STEPS)
        self.assertEqual(b["sample_params"]["guidance"]["txt_cfg"], bildmodell.GUIDANCE)
        self.assertFalse(b["embed_image_metadata"])
        for bad in ({"prompt": "", "width": 512, "height": 512}, {"prompt": "x" * 2001, "width": 512, "height": 512},
                    {"prompt": "a", "width": 500, "height": 512}, {"prompt": "a", "width": 2048, "height": 2048},
                    {"prompt": "a", "width": 512, "height": 128}, {"prompt": "a", "width": 512, "height": 512, "seed": True},
                    {"prompt": "a", "width": 512, "height": 512, "refs": ["x", "y", "z"]}, ["not", "a", "dict"]):
            with self.assertRaises(HTTPException, msg=str(bad)[:80]):
                bild_server.request_body(bad)

    def test_finish_marks_and_reencodes(self):
        from PIL import Image
        with mock.patch.object(bild_server, "nsfw_share", lambda im: 0.02):
            out, w, h, share = bild_server.finish(png(96, 64))
        im = Image.open(io.BytesIO(out))
        self.assertEqual((w, h, share), (96, 64, 0.02))
        self.assertIn("KI-erzeugt", im.text.get("Comment", "") + im.text.get("Software", ""))
        self.assertIn("trainedAlgorithmicMedia", json.dumps(im.info, default=str))
        with self.assertRaises(ValueError):
            bild_server.finish(b"GIF89a....")

    def test_models_are_pinned(self):
        for v, m in bildmodell.VARIANTS.items():
            for f in bildmodell.files(v):
                self.assertRegex(f.sha256, r"^[0-9a-f]{64}$")
                self.assertGreater(f.size, 1_000_000)
                self.assertRegex(f.revision, r"^([0-9a-f]{40}|main)$")
            self.assertEqual(m["commercial"], v.startswith("4b"))
            self.assertGreater(bildmodell.disk_gb(v), 1)
        self.assertEqual(bildmodell.variant("../../x"), bildmodell.DEFAULT)
        self.assertRegex(bildmodell.SDCPP_COMMIT, r"^[0-9a-f]{40}$")
        with mock.patch.object(bildmodell, "ENGINE", "/nonexistent/sd-server"):
            self.assertIn("engine", bildmodell.missing("4b-q8", "/nonexistent"))
            self.assertFalse(bildmodell.installed("4b-q8", "/nonexistent"))


class Install(unittest.TestCase):
    """install.sh: the picture service only on request, the engine built from the pinned commit, its unit like the
    engines (no memory cap on unified memory, the first one the kernel may stop)."""

    def test_install_builds_pinned_and_stays_optional(self):
        path = os.path.join(os.path.dirname(helpers.APP), "install.sh")
        if not os.path.exists(path):
            self.skipTest("install.sh is not part of this copy")
        sh = open(path).read()
        self.assertIn('case "$BILD_PICK" in ""|4b-q8|4b-q4|9b-q8|9b-q4|none)', sh)
        # with the panel here, or on the model computer of a split install (Spark teilen), never without image.enabled
        self.assertIn('WITH_BILD=0; { [ "$MODE" = full ] || [ "$TEILEN" = 1 ]; } && [ "$(cfg \'.image.enabled // false\')" = true ] && WITH_BILD=1', sh)
        self.assertIn('PANEL_ONLY=1; WITH_ASR=0; WITH_TTS=0; WITH_BILD=0', sh)
        self.assertIn('checkout --quiet "$SDCPP_COMMIT"', sh)
        self.assertIn("-DCMAKE_CUDA_ARCHITECTURES=121", sh)
        self.assertIn("systemctl disable --now speech-spark-bild.service", sh)
        unit = sh.split("speech-spark-bild.service <<EOF", 1)[1].split("\nEOF\n", 1)[0]
        self.assertNotIn("MemoryMax", unit)
        self.assertIn("OOMScoreAdjust=1000", unit)
        self.assertIn("SPEECH_SPARK_SD_SERVER=$PREFIX/sdcpp/bin/sd-server", unit)
        self.assertEqual(bildmodell.ENGINE, "/opt/speech-spark/sdcpp/bin/sd-server")


if __name__ == "__main__":
    unittest.main()
