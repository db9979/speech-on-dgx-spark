"""Musik machen, stages M0 and M1 (musik.py, musik_server.py, musikmodell.py, bedarf.py; plan plaene/musik.md, Dominik
2026-10-16 „1a 2a 3a 4a 5a“): off unless installed; only the admin measures, never a profile or a guest; the
measurement uses fixed songs only and keeps numbers, never a caption or lyrics in the journal; the service sets every
field of the engine itself, takes only an MP3 back and marks it as made by an AI; the model files and the engine are
pinned; install.sh builds it only on request. M1 (Dominik 2026-10-16 „2a 3a“, „größeres Modell auswählen“): an own
admin switch, off by default; guests and blocked profiles never make music; fixed rules refuse (word list, artists,
secrets, other people's names); instrumental and 2 minutes unless asked; the picked model goes with every song; the
journal never names a wish or lyrics. The music service is faked (no GPU); nothing depends on the time."""
import asyncio
import base64
import contextlib
import io
import json
import os
import unittest

import httpx
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import admin as admin_mod  # noqa: E402
import features  # noqa: E402
import intent  # noqa: E402
import musik  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
import wartung  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import bedarf  # noqa: E402
import bildmodell  # noqa: E402
import common  # noqa: E402
import modelle  # noqa: E402
import musik_server  # noqa: E402
import musikmodell  # noqa: E402
import tlstor  # noqa: E402

HOME = ("192.168.178.20", 50000)
FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 400        # an MPEG-1 Layer III frame header and some bytes


def client():
    return TestClient(panel.app, client=HOME)


def admin():
    c = client()
    assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    return c


def music(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c.setdefault("music", {}).update(kw)
    helpers.write_config(c)


def wait_done():
    for _ in range(200):
        if not musik._run["run"]:
            return
        asyncio.run(asyncio.sleep(0.01))


class Admin(unittest.TestCase):
    def tearDown(self):
        music(enabled=False, model="")
        wait_done()

    def test_only_the_admin_measures(self):
        self.assertEqual(client().post("/api/admin/musik-test").status_code, 401)
        self.assertEqual(client().get("/api/admin/musik-test").status_code, 401)
        self.assertEqual(client().get("/api/admin/musik-test/2b/1.mp3").status_code, 401)

    def test_not_installed_says_so(self):
        music(enabled=False)
        a = admin()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = a.post("/api/admin/musik-test")
            wait_done()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(a.get("/api/admin/musik-test").json()["health"]["status"], "off_install")
        last = a.get("/api/admin/musik-test").json()["last"]
        self.assertEqual([t["why"] for run in last["runs"] for t in run["tests"]], ["missing", "missing"])
        self.assertFalse(last["ok"])
        for line in out.getvalue().splitlines():
            self.assertTrue(line.startswith("musik: "), line)

    def test_fixed_songs_numbers_and_files_for_every_installed_model(self):
        """Dominik 2026-10-16 („das größere Modell auch testen“): Musik testen measures each installed model with the
        same two fixed songs; the engine ends before each model, so its first song counts the loading too."""
        music(enabled=True)
        sent, stops = [], []

        async def fake(path, body=None, timeout=0):
            if path == "/health":
                return 200, {"service": "musik", "status": "ready", "installed": ["2b", "xl"], "variant": "2b"}
            if path == "/v1/musik/stop":
                stops.append(len(sent))
                return 200, {"ok": True}
            sent.append(body)
            mp3 = musik_server.finish(FRAME, body["title"])
            return 200, {"mp3": base64.b64encode(mp3).decode(), "seconds": 12.5, "lm_s": 3.0, "synth_s": 9.5,
                         "peak_gib": 8.1, "length_s": body["seconds"], "variant": body["variant"]}

        a = admin()
        out = io.StringIO()
        with mock.patch.object(musik, "call", fake), contextlib.redirect_stdout(out):
            self.assertEqual(a.post("/api/admin/musik-test").status_code, 200)
            wait_done()
            d = a.get("/api/admin/musik-test").json()
        self.assertTrue(d["last"]["ok"], d)
        self.assertEqual([run["variant"] for run in d["last"]["runs"]], ["2b", "xl"])
        self.assertEqual([t["peak_gib"] for run in d["last"]["runs"] for t in run["tests"]], [8.1] * 4)
        self.assertEqual(stops, [0, 2])
        self.assertEqual([b["variant"] for b in sent], ["2b", "2b", "xl", "xl"])
        # the songs come from the fixed list only: nothing from a person or a model
        self.assertEqual([(b["caption"], b["lyrics"]) for b in sent], [(t["caption"], t["lyrics"]) for t in musik.TESTS] * 2)
        for v in ("2b", "xl"):
            r = a.get(f"/api/admin/musik-test/{v}/2.mp3")
            self.assertEqual((r.status_code, r.headers["content-type"]), (200, "audio/mpeg"))
            self.assertTrue(r.content.startswith(b"ID3"))
        self.assertEqual(a.get("/api/admin/musik-test/2b/3.mp3").status_code, 404)
        self.assertEqual(a.get("/api/admin/musik-test/gross/1.mp3").status_code, 404)
        # the journal names numbers and the model, never a caption or the lyrics
        log = out.getvalue()
        self.assertIn("musik: test xl 2 ok", log)
        for t in musik.TESTS:
            self.assertNotIn(t["caption"], log)
            self.assertNotIn("Morgen", log)
        live = musik.for_live()                    # Live: numbers only
        self.assertEqual((live["installed"], live["test_run"], live["test_ok"], live["test_total"]), (True, False, 4, 4))
        self.assertTrue(all(isinstance(x, (bool, int)) for x in live.values()), live)

    def test_a_maintenance_pause_waits(self):
        music(enabled=True)
        a = admin()
        asked = []

        async def fake(path, body=None, timeout=0):
            asked.append(path)
            return 200, {"service": "musik", "status": "ready", "installed": ["2b"]}

        with mock.patch.object(wartung, "paused", lambda part: part == "musik"), \
                mock.patch.object(musik, "call", fake), contextlib.redirect_stdout(io.StringIO()):
            a.post("/api/admin/musik-test")
            wait_done()
        self.assertEqual([t["why"] for run in musik.last_test()["runs"] for t in run["tests"]], ["pause", "pause"])
        self.assertNotIn("/v1/musik", asked, "no song during a Wartungspause")

    def test_install_keys_stay_and_limits_are_checked(self):
        a = admin()
        cfg = a.get("/api/config").json()
        new = json.loads(json.dumps(cfg))
        new["music"].update(enabled=True, variant="xl", port=1, engine_port=2, idle_min=99)
        admin_mod.validate(new)
        for k in ("enabled", "variant", "port", "engine_port", "idle_min"):
            self.assertEqual(new["music"][k], cfg["music"][k], k)
        for k, bad in (("model", "../xl"), ("model", "gross"), ("day_limit", 0), ("day_limit", 101), ("store_mb", 10),
                       ("max_s", 5), ("max_s", 3600), ("day_limit", True)):
            new = json.loads(json.dumps(cfg))
            new["music"][k] = bad
            with self.assertRaises(HTTPException, msg=f"{k}={bad}"):
                admin_mod.validate(new)
        new = json.loads(json.dumps(cfg))
        new["music"].update(model="xl", day_limit=3, store_mb=100, max_s=60)
        admin_mod.validate(new)
        self.assertEqual(new["music"]["model"], "xl")


# ---------------------------------------------------------------- stage M1: Musik machen (Dominik 2026-10-16 „2a 3a“)
musik.BACKGROUND = False      # the tests run the job themselves


def block(uid, yes=True):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        deny = dict(json.load(f)["chat"].get("deny") or {})
    deny["musik"] = [u for u in deny.get("musik", []) if u != uid] + ([uid] if yes else [])
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


def fake_song(code=200, detail=None):
    """A stand-in for musik_server's /v1/musik (musik.call)."""
    calls = []

    async def call(path, body=None, timeout=0):
        calls.append((path, body))
        if code != 200:
            return code, {"detail": detail}
        mp3 = musik_server.finish(FRAME, body["title"])
        return 200, {"mp3": base64.b64encode(mp3).decode(), "seconds": 9.5, "length_s": body["seconds"],
                     "variant": body.get("variant") or "2b"}
    return call, calls


async def no_wait(job, sleep=None):
    return 0


def run(j):
    with mock.patch("vorrang.quiet", no_wait):
        asyncio.run(musik._work(j))


class On(unittest.TestCase):
    def setUp(self):
        helpers.set_config(musik=True)
        music(enabled=True)

    def tearDown(self):
        helpers.set_config(musik=False)
        music(enabled=False, model="")
        musik._jobs.clear()
        musik._recent.clear()


class Off(unittest.TestCase):
    def test_off_by_default_and_without_the_model(self):
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            d = json.load(f)
        self.assertFalse(d["chat"]["musik"])
        self.assertFalse(d["music"]["enabled"])
        self.assertNotIn("chat.musik", features.DEFAULT_ON)
        c, prof = profile("Musikerin Aus")
        self.assertEqual(c.get("/api/musik").status_code, 403)
        helpers.set_config(musik=True)            # switched on, but the model is not installed
        try:
            self.assertFalse(features.allowed(musik.KEY, prof["id"]))
            self.assertEqual(c.get("/api/musik").status_code, 403)
        finally:
            helpers.set_config(musik=False)
        o = musik.offer({"who": prof, "own": True, "text": "Mach mir ein Lied über unsere Katze"})
        self.assertEqual(o["tools"], [])          # asked while off: no tool, only where to switch it on
        self.assertIn("Musik machen", o["hint"])


class Access(On):
    def test_guests_and_blocked_profiles_never_make_music(self):
        self.assertIsNone(musik.offer({"who": None, "own": False, "text": "Mach mir ein Lied"}))
        self.assertIn(client().get("/api/musik").status_code, (401, 403))
        c, prof = profile("Musikerin Gesperrt")
        self.assertEqual(c.get("/api/musik").status_code, 200)
        block(prof["id"])
        try:
            self.assertFalse(features.allowed(musik.KEY, prof["id"]))
            self.assertEqual(c.get("/api/musik").status_code, 403)
            self.assertEqual(c.post("/api/musik", json={"wunsch": "Ein Lied"}).status_code, 403)
            self.assertEqual(musik.offer({"who": prof, "own": True, "text": "Mach mir ein Lied"})["tools"], [])
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                musik.start(prof, "calm piano", "Klavier")
        finally:
            block(prof["id"], False)

    def test_only_on_the_persons_own_words_and_locked_after_outside_text(self):
        _, prof = profile("Musikerin Worte")
        for no in ("Wie wird das Wetter morgen?", "Spiel Musik im Wohnzimmer", "Spiel das Lied von gestern nochmal",
                   "Mach die Musik aus", "Mach Musik an"):
            self.assertIsNone(musik.offer({"who": prof, "own": True, "text": no}), no)
        self.assertIsNone(musik.offer({"who": prof, "own": True, "text": "Mach mir ein Lied", "client": "mcp"}))
        self.assertIsNone(musik.offer({"who": prof, "own": True, "text": "Mach mir ein Lied", "private": False}))
        for yes in ("Mach mir ein Lied über unsere Katze", "Komponier ein Stück für Klavier",
                    "Kannst du einen Song zum Geburtstag schreiben?", "Make me a song about rain"):
            o = musik.offer({"who": prof, "own": True, "text": yes})
            self.assertEqual([t["function"]["name"] for t in o["tools"]], ["musik_machen"], yes)
        # a changing tool: chat.py locks it after mail, web or document text, the Notaus from stage 2 on
        self.assertIn("musik_machen", o["changes"])
        self.assertIn("musik_machen", notaus.locked_tools(2, o["changes"]))
        # a short yes after the wish keeps the tool; much later it does not
        self.assertIsNotNone(musik.offer({"who": prof, "own": True, "text": "ja, mit Gesang"}))
        musik._recent[prof["id"]] = 0
        self.assertIsNone(musik.offer({"who": prof, "own": True, "text": "ja, mit Gesang"}))

    def test_weiche_keeps_making_music_apart(self):
        for q in ("Mach mir ein Lied über unsere Katze", "Komponier ein Stück für Klavier"):
            self.assertEqual(intent.classify(q).names, ["musik"], q)
        self.assertNotIn("musik", intent.classify("Spiel Musik im Wohnzimmer").names)
        self.assertNotIn("musik", intent.classify("Schreib mal eine Mail an Anna").names)


class Rules(On):
    def test_word_list_artists_secrets_and_known_names_refuse(self):
        _, prof = profile("Musikerin Regeln")
        _, other = profile("Gertrude Nachbar")
        uid = prof["id"]
        self.assertEqual(musik.refuse_text(uid, "a song about a naked man"), "wortliste")
        self.assertEqual(musik.refuse_text(uid, "pop im Stil von Helene Fischer"), "kuenstler")
        self.assertEqual(musik.refuse_text(uid, "ein Lied", "[verse]\nmein Passwort: abc123"), "geheim")
        self.assertEqual(musik.refuse_text(uid, "a song about Gertrude"), "person")
        self.assertEqual(musik.refuse_text(uid, "a birthday song for Musikerin"), "")    # the own name is fine
        self.assertEqual(musik.refuse_text(uid, "calm piano", "Ruhiges Klavier"), "")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(ValueError):
            musik.start(prof, "a song about Gertrude", "Ein Lied über Gertrude")
        self.assertIn("musik: nicht gestartet person", out.getvalue())
        self.assertNotIn("Gertrude", out.getvalue())
        self.assertNotIn("Musikerin", out.getvalue())   # names only through profiles.log_name
        self.assertEqual(other["name"], "Gertrude Nachbar")

    def test_length_default_and_the_admin_limit(self):
        lim = musik.limits()
        self.assertEqual(lim["default_s"], 120)          # Dominik 3a: 2 minutes unless asked
        for asked, want in ((None, 120), (True, 120), ("90", 120), (-5, 120), (3, musik.MIN_S), (90, 90),
                            (99999, lim["max_s"])):
            self.assertEqual(musik.length(asked, lim), want, asked)
        music(max_s=60)
        self.assertEqual(musik.limits()["default_s"], 60)

    def test_engine_answers_become_reasons(self):
        for code, detail, why in ((503, "memory", "memory"), (503, "missing", "missing"), (502, "engine", "engine"),
                                  (504, None, "zeit"), (500, None, "dienst"), (503, "<script>", "dienst")):
            call, _ = fake_song(code=code, detail=detail)
            with mock.patch.object(musik, "call", call), self.assertRaises(ValueError) as e:
                asyncio.run(musik.make({"caption": "x", "seconds": 30, "title": "x"}))
            self.assertEqual(str(e.exception), why)


class Jobs(On):
    def test_make_store_play_and_delete(self):
        c, prof = profile("Musikerin Ablage")
        uid = prof["id"]
        musik.clear(uid)
        music(model="xl")
        call, calls = fake_song()
        out = io.StringIO()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(out):
            j = musik.start(prof, "calm piano with strings", "Ruhiges Klavier", None, True, "de",
                            "[verse]\nLa la la", "chat")
            run(musik._jobs[j["id"]])
        body = calls[0][1]
        self.assertEqual((calls[0][0], body["variant"], body["seconds"], body["language"]), ("/v1/musik", "xl", 120, "de"))
        self.assertEqual(body["lyrics"], "[verse]\nLa la la")
        self.assertEqual(musik._jobs[j["id"]]["state"], "done")
        log = out.getvalue()
        self.assertIn("musik: auftrag 120 s gesang chat", log)
        self.assertIn("musik: gemacht 120 s gesang", log)
        for word in ("piano", "Klavier", "La la"):
            self.assertNotIn(word, log)
        d = c.get("/api/musik").json()
        self.assertEqual(len(d["songs"]), 1)
        s = d["songs"][0]
        self.assertEqual((s["wish"], s["caption"], s["sung"], s["model"], s["job"]),
                         ("Ruhiges Klavier", "calm piano with strings", True, "xl", j["id"]))
        self.assertEqual(c.get("/api/musik/job/" + j["id"]).json()["song"]["id"], s["id"])
        kept = profiles._att([{"k": "musik", "p": "calm piano", "j": j["id"]}, {"k": "musik", "p": "x", "j": "../etc"}])
        self.assertEqual(kept, [{"k": "musik", "p": "calm piano", "j": j["id"]}, {"k": "musik", "p": "x"}])
        musik._jobs.pop(j["id"])                 # an hour later: the kept song still answers for its job
        self.assertEqual(c.get("/api/musik/job/" + j["id"]).json()["song"]["id"], s["id"])
        r = c.get(f"/api/musik/{s['id']}/datei")
        self.assertEqual((r.status_code, r.headers["content-type"], r.headers["x-content-type-options"]),
                         (200, "audio/mpeg", "nosniff"))
        self.assertTrue(r.content.startswith(b"ID3"))
        self.assertIn("attachment", c.get(f"/api/musik/{s['id']}/datei?dl=1").headers["content-disposition"])
        # another profile never sees it
        c2, _ = profile("Musikerin Fremd")
        self.assertEqual(c2.get(f"/api/musik/{s['id']}/datei").status_code, 404)
        self.assertEqual(c2.get("/api/musik/job/" + j["id"]).status_code, 404)
        self.assertEqual(c2.delete(f"/api/musik/{s['id']}").status_code, 404)
        count, clear = features.OWN["musik"]
        self.assertEqual(count(uid), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.delete(f"/api/musik/{s['id']}").status_code, 200)
        self.assertEqual(c.get("/api/musik").json()["songs"], [])
        self.assertEqual(count(uid), 0)

    def test_without_a_picked_model_the_service_decides(self):
        _, prof = profile("Musikerin Standard")
        musik.clear(prof["id"])
        call, calls = fake_song()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()):
            j = musik.start(prof, "calm piano", "Klavier")
            run(musik._jobs[j["id"]])
        self.assertNotIn("variant", calls[0][1])
        self.assertEqual((calls[0][1]["lyrics"], calls[0][1]["language"]), ("", ""))   # instrumental unless asked

    def test_page_makes_the_persons_own_wish(self):
        c, prof = profile("Musikerin Seite")
        musik.clear(prof["id"])
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.post("/api/musik", json={"wunsch": "Ein ruhiges <b>Klavierstück</b>", "sekunden": 60})
        self.assertEqual(r.status_code, 200, r.text)
        j = musik._jobs[r.json()["id"]]
        self.assertEqual((j["caption"], j["seconds"], j["sung"], j["src"]), ("Ein ruhiges b Klavierstück /b", 60, False, "seite"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post("/api/musik", json={"wunsch": "noch eins"}).status_code, 409)   # one at a time

    def test_limits_per_profile(self):
        _, prof = profile("Musikerin Grenzen")
        uid = prof["id"]
        musik.clear(uid)
        music(day_limit=1)
        call, _ = fake_song()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()) as out:
            run(musik._jobs[musik.start(prof, "calm piano", "Klavier")["id"]])
            with self.assertRaises(ValueError):
                musik.start(prof, "calm piano", "Klavier")
        self.assertIn("musik: nicht gestartet tageslimit", out.getvalue())
        music(day_limit=10)
        musik.clear(uid)

    def test_notaus_and_maintenance_hold_new_songs(self):
        _, prof = profile("Musikerin Pause")
        with mock.patch.object(wartung, "paused", lambda part: part == "musik"), \
                contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(ValueError):
            musik.start(prof, "calm piano", "Klavier")
        self.assertIn("musik: nicht gestartet wartung", out.getvalue())

    def test_a_failed_song_ends_with_a_reason(self):
        _, prof = profile("Musikerin Fehler")
        call, _ = fake_song(code=503, detail="memory")
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()) as out:
            j = musik.start(prof, "calm piano", "Klavier")
            run(musik._jobs[j["id"]])
        self.assertEqual(musik._jobs[j["id"]]["error"], musik.REFUSED["memory"][0])
        self.assertIn("musik: nicht gemacht memory", out.getvalue())

    def test_tool_answers_with_fixed_sentences_and_a_card_only_in_the_panel(self):
        _, prof = profile("Musikerin Werkzeug")
        musik.clear(prof["id"])

        async def go(args, client="web"):
            q = asyncio.Queue()
            text = await musik.tool("musik_machen", args, {"who": prof, "client": client, "out": q})
            return text, [q.get_nowait() for _ in range(q.qsize())]

        with contextlib.redirect_stdout(io.StringIO()):
            text, events = asyncio.run(go({"beschreibung_en": "calm piano", "wunsch": "Klavier"}))
            self.assertTrue(text.startswith("Started: a 120 s song, instrumental"), text)
            self.assertEqual([e["type"] for e in events], ["musik"])
            musik._jobs.clear()
            text, events = asyncio.run(go({"beschreibung_en": "calm piano"}, client="iphone"))
            self.assertEqual(events, [])
            self.assertIn("Ich → Musik", text)
            musik._jobs.clear()
            text, _ = asyncio.run(go({"beschreibung_en": "pop im Stil von Helene Fischer"}))
        self.assertTrue(text.startswith("Not done:"), text)


class ServiceModel(unittest.TestCase):
    def test_a_known_model_or_the_installed_one(self):
        self.assertEqual(musik_server.pick({"variant": "xl"}), "xl")
        with self.assertRaises(HTTPException) as c:
            musik_server.pick({"variant": "../../etc"})
        self.assertEqual(c.exception.status_code, 400)
        self.assertIn(musik_server.pick({}), musikmodell.VARIANTS)

    def test_another_model_ends_the_running_engine_first(self):
        e = musik_server.Engine()
        e.state, e.variant = "ready", "2b"
        ended, spawned = [], []

        def stop(why=""):
            ended.append(why)
            e.state = "off"

        def spawn(cmd, folder):
            spawned.append(cmd[0])
            e.state = "starting"

        e.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))

        with mock.patch.object(musikmodell, "installed", lambda v, folder=None: True), \
                mock.patch.object(musik_server, "check_memory", lambda *a, **k: None), \
                mock.patch.object(e, "alive", lambda: e.state in ("ready", "starting")), \
                mock.patch.object(e, "stop", stop), mock.patch.object(e, "spawn", spawn), \
                contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(e.start("2b"))
            self.assertEqual((ended, spawned), ([], []))           # the same model stays loaded
            asyncio.run(e.start("xl"))
        self.assertEqual((ended, len(spawned), e.variant, e.state), (["anderes modell"], 1, "xl", "ready"))


class Service(unittest.TestCase):
    def test_service_sets_every_field_itself(self):
        b = musik_server.request_body({"caption": "piano <b>calm</b>", "seconds": 30})
        self.assertNotIn("<", b["caption"])
        self.assertEqual((b["lyrics"], b["vocal_language"]), (musik_server.INSTRUMENTAL, "unknown"))
        self.assertEqual((b["inference_steps"], b["output_format"], b["synth_batch_size"]), (musikmodell.STEPS, "mp3", 1))
        v = musikmodell.VARIANTS[musikmodell.DEFAULT]
        self.assertEqual((b["synth_model"], b["lm_model"]), (v["dit"].name, v["lm"].name))   # the whole file name
        s = musik_server.request_body({"caption": "pop", "seconds": 60, "lyrics": "[verse]\nHallo", "language": "de"})
        self.assertEqual((s["vocal_language"], s["lyrics"]), ("de", "[verse]\nHallo"))
        for bad in ({"caption": "", "seconds": 30}, {"caption": "x" * 601, "seconds": 30}, {"caption": "a", "seconds": 5},
                    {"caption": "a", "seconds": 601}, {"caption": "a", "seconds": True}, {"caption": "a", "seconds": 30, "language": "xx"},
                    {"caption": "a", "seconds": 30, "seed": "1"}, {"caption": "a", "seconds": 30, "lyrics": "x" * 4001}, []):
            with self.assertRaises(HTTPException):
                musik_server.request_body(bad)

    def test_finish_marks_and_takes_only_mp3(self):
        old = b"ID3\x03\x00\x00\x00\x00\x00\x0aTIT2" + b"\x00" * 6 + FRAME
        out = musik_server.finish(old, "Probe")
        self.assertTrue(out.startswith(b"ID3\x03"))
        self.assertTrue(out.endswith(FRAME))
        self.assertIn("KI-erzeugt".encode("utf-16-le"), out)
        self.assertEqual(out.count(b"ID3"), 1)
        for bad in (b"RIFF....WAVE", b"", b"ID3\x03\x00\x00\x00\x00\x00\x00ID3"):
            with self.assertRaises(ValueError):
                musik_server.finish(bad, "x")

    def test_audio_part_out_of_the_multipart_answer(self):
        body = (b"--b\r\nContent-Type: application/octet-stream\r\n\r\n" + b"\x00" * 64 + b"\r\n"
                b"--b\r\nContent-Type: audio/mpeg\r\n\r\n" + FRAME + b"\r\n--b--\r\n")
        res = mock.Mock(headers={"content-type": 'multipart/mixed; boundary="b"'}, content=body)
        self.assertEqual(musik_server.audio_part(res), FRAME)
        res.content = body.replace(FRAME, b"RIFF" + b"\x00" * 60)
        with self.assertRaises(ValueError):
            musik_server.audio_part(res)
        with self.assertRaises(ValueError):
            musik_server.audio_part(mock.Mock(headers={"content-type": "audio/mpeg"}, content=FRAME))

    def test_a_song_through_an_engine_that_answers_like_ace_server(self):
        """The wire format of ace-server at musikmodell.ACECPP_COMMIT (tars 2026-10-16: every song failed): job ids are
        16 hex digits, models are named by their whole file name, /lm hands back a JSON array, /synth a
        multipart/mixed answer with an audio and a latent part."""
        names = {f.name for f in musikmodell.files(musikmodell.DEFAULT)}
        jobs, seen = {}, []

        def handler(req):
            if req.method == "POST" and req.url.path in ("/lm", "/synth"):
                body = json.loads(req.content)
                seen.append((req.url.path, body.get("lm_model"), body.get("synth_model"), body.get("audio_codes")))
                if body["lm_model"] not in names or body["synth_model"] not in names:
                    return httpx.Response(200, json={"id": "00000000000000ff"})   # ace-server: "LM not found"
                job = f"{len(jobs) + 0xa1b2c3d4e5f60700:016x}"
                jobs[job] = (req.url.path, body)
                return httpx.Response(200, json={"id": job})
            if req.url.path == "/job":
                job = req.url.params.get("id")
                if job not in jobs:
                    return httpx.Response(200, json={"status": "failed"})
                if req.url.params.get("result") != "1":
                    return httpx.Response(200, json={"status": "done"})
                step, body = jobs[job]
                if step == "/lm":
                    return httpx.Response(200, json=[dict(body, audio_codes="12,7,99", bpm=96)])
                multi = (b"--ace-batch-boundary\r\nContent-Type: audio/mpeg\r\n\r\n" + FRAME + b"\r\n"
                         b"--ace-batch-boundary\r\nContent-Type: application/octet-stream\r\n"
                         b"Content-Disposition: form-data; name=\"latent\"\r\n\r\n" + b"\x00" * 256 + b"\r\n"
                         b"--ace-batch-boundary--\r\n")
                return httpx.Response(200, content=multi,
                                      headers={"content-type": "multipart/mixed; boundary=ace-batch-boundary"})
            return httpx.Response(404)

        e = musik_server.Engine()
        e.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        req = musik_server.request_body({"caption": "calm piano", "seconds": 30})

        async def ready(v):
            e.state, e.variant = "ready", v

        with mock.patch.object(e, "start", ready), mock.patch.object(e, "alive", lambda: True), \
                mock.patch.object(musik_server, "POLL_S", 0):
            raw, lm_s, synth_s, peak = asyncio.run(e.make(req, "2b"))
        self.assertEqual(raw, FRAME)
        self.assertEqual([s[0] for s in seen], ["/lm", "/synth"])
        self.assertEqual(seen[1][3], "12,7,99")            # the codes of the planner go on to the sound model
        self.assertTrue(musik_server.finish(raw, "x").startswith(b"ID3"))

    def test_too_little_memory_loads_nothing(self):
        e = musik_server.Engine()
        with mock.patch.object(musikmodell, "installed", lambda v, folder=None: True), \
                mock.patch.object(musik_server, "check_memory", side_effect=MemoryError), \
                mock.patch.object(e, "spawn", side_effect=AssertionError("started")), \
                contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(HTTPException) as c:
            asyncio.run(e.start("2b"))
        self.assertEqual(c.exception.detail, "memory")
        self.assertTrue(out.getvalue().startswith("musik: engine nicht gestartet"))
        self.assertIsInstance(e, bedarf.OnDemand)

    def test_engine_only_on_this_machine(self):
        cmd = musik_server.Engine().command()
        self.assertEqual(cmd[cmd.index("--host") + 1], "127.0.0.1")
        self.assertNotIn("--adapters", cmd)

    def test_engine_gets_only_options_it_knows(self):
        """ace-server ends with its help and code 1 on an unknown option ("--mp3-bitrate" on tars, 2026-10-16):
        every option is one of its `--help` at musikmodell.ACECPP_COMMIT."""
        known = {"--models", "--adapters", "--device", "--keep-loaded", "--vae-chunk", "--vae-overlap", "--host",
                 "--port", "--max-batch", "--max-seq", "--no-fsm", "--no-fa", "--no-batch-cfg", "--clamp-fp16"}
        self.assertEqual(musikmodell.ACECPP_COMMIT[:7], "6013134", "a new commit: compare its --help with `known`")
        cmd = musik_server.Engine().command()
        self.assertEqual([a for a in cmd if a.startswith("--") and a not in known], [])

    def test_models_are_pinned(self):
        for v in musikmodell.VARIANTS:
            for f in musikmodell.files(v):
                self.assertRegex(f.sha256, r"^[0-9a-f]{64}$")
                self.assertGreater(f.size, 100_000_000)
                self.assertRegex(f.revision, r"^[0-9a-f]{40}$")
                self.assertTrue(f.name.endswith(".gguf"))
            self.assertGreater(musikmodell.disk_gb(v), 1)
        self.assertEqual(musikmodell.variant("../../x"), musikmodell.DEFAULT)
        self.assertRegex(musikmodell.ACECPP_COMMIT, r"^[0-9a-f]{40}$")
        with mock.patch.object(musikmodell, "ENGINE", "/nonexistent/ace-server"):
            self.assertIn("engine", musikmodell.missing("2b", "/nonexistent"))
            self.assertFalse(musikmodell.installed("2b", "/nonexistent"))

    def test_catalog_and_ports(self):
        kat = modelle.katalog()
        m = modelle.zur_variante("musik", "2b", kat)
        self.assertEqual((m["betrieb"], m["lizenz"], m["need_gib"]), ("bei_bedarf", "MIT", musikmodell.VARIANTS["2b"]["need_gib"]))
        self.assertEqual([x["wahl"] for x in modelle.wahl("musik", kat)], list(musikmodell.VARIANTS))
        cfg = json.load(open(os.path.join(helpers.APP, "config.default.json")))
        self.assertLessEqual(max(cfg["music"]["port"], cfg["music"]["engine_port"]), 31099)
        self.assertNotIn(cfg["music"]["port"], tlstor.ports(cfg))
        cfg["music"]["enabled"] = True
        self.assertIn(cfg["music"]["port"], tlstor.ports(cfg))
        self.assertNotIn(cfg["music"]["engine_port"], tlstor.ports(cfg))
        self.assertEqual(common.model_url("musik", "/health", cfg), f"http://127.0.0.1:{cfg['music']['port']}/health")
        self.assertIn("musik", [x["art"] for x in modelle.aktiv(cfg, 120)])


class Folder(unittest.TestCase):
    def test_files_are_looked_for_in_the_music_folder(self):
        """V01.0.672: missing() asked bildmodell.path without a folder and looked in the picture folder, so a complete
        install said "nicht vollständig installiert"."""
        import tempfile
        with tempfile.TemporaryDirectory() as music, tempfile.TemporaryDirectory() as pictures:
            engine = os.path.join(music, "ace-server")
            with open(engine, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(engine, 0o755)
            with mock.patch.object(musikmodell, "FOLDER", music), mock.patch.object(musikmodell, "ENGINE", engine), \
                    mock.patch.object(bildmodell, "FOLDER", pictures):
                self.assertEqual(len(musikmodell.missing("2b")), 4)
                for f in musikmodell.files("2b"):
                    with open(os.path.join(music, f.name), "wb") as out:
                        out.truncate(f.size)   # sparse: the size counts, the hash is checked when fetched
                self.assertEqual(musikmodell.missing("2b"), [])
                self.assertTrue(musikmodell.installed("2b"))


class Install(unittest.TestCase):
    """install.sh: the music service only on request, the engine built from the pinned commit, its unit like the
    picture service (no memory cap on unified memory, the first one the kernel may stop)."""

    def test_install_builds_pinned_and_stays_optional(self):
        path = os.path.join(os.path.dirname(helpers.APP), "install.sh")
        if not os.path.exists(path):
            self.skipTest("install.sh is not part of this copy")
        sh = open(path).read()
        self.assertIn('case "$MUSIK_PICK" in ""|2b|2b-klein|xl|none)', sh)
        self.assertIn('WITH_MUSIK=0; { [ "$MODE" = full ] || [ "$TEILEN" = 1 ]; } && [ "$(cfg \'.music.enabled // false\')" = true ] && WITH_MUSIK=1', sh)
        self.assertIn('WITH_BILD=0; WITH_MUSIK=0;', sh)
        self.assertIn('checkout --quiet "$ACECPP_COMMIT"', sh)
        # V01.0.672: ggml linked in, the moved engine finds every library, an older shared build is built again
        self.assertIn("-DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON", sh)
        self.assertIn('ldd "$PREFIX/acestep.new/bin/ace-server" | grep -q "not found"', sh)
        self.assertIn('!= "$ACECPP_COMMIT static" ]', sh)
        self.assertIn('printf \'%s\\n\' "$ACECPP_COMMIT static"', sh)
        unit = sh[sh.index("speech-spark-musik.service <<EOF"):]
        unit = unit[:unit.index("\nEOF")]
        self.assertIn("OOMScoreAdjust=1000", unit)
        self.assertNotIn("MemoryMax", unit)
        block = sh[sh.index("Musik machen (optional"):sh.index("# ---------------------------------------------------------------- models (ASR")]
        code = "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("docker", code.lower(), "no Docker for our services on the Spark")


if __name__ == "__main__":
    unittest.main()
