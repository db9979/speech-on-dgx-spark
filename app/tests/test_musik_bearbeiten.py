"""Musik bearbeiten, stage E1 (musik.py, musik_server.py; plan musik-experte/plan.md, Dominik 2026-10-20 „alles nach
Empfehlung umsetzten“, „texte anpassen strophen hinzufügen und verschieben … mit drag and drop“): an own admin switch,
off by default, below Musik machen; guests and blocked profiles never edit; an own file only with the rights tick and
a known format; every number of a change is checked by the panel and again by the service; every change is a new
version at its song, the original stays; the tool always takes the newest own song, never one the model names; ffmpeg
gets fixed arguments only; the journal never names a wish, lyrics or a file name. The music service is faked (no GPU);
nothing depends on the time."""
import asyncio
import base64
import contextlib
import io
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import features  # noqa: E402
import intent  # noqa: E402
import musik  # noqa: E402
import musik_server  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from tests.test_musik import FRAME, block, client, fake_song, music, no_wait, profile  # noqa: E402

LIM = {"max_s": 300, "default_s": 120, "day": 10, "store_mb": 500}


def edit_on(yes=True):
    helpers.set_config(musik_bearbeiten=yes)


def song(uid, **kw):
    """One made song of 120 s in the profile's folder, as Musik machen keeps it."""
    meta = dict({"wish": "Ruhiges Klavier", "caption": "calm piano", "lyrics": "", "sung": False, "language": "",
                 "length_s": 120, "model": "2b", "src": "seite"}, **kw)
    return musik.keep(uid, musik_server.finish(FRAME, "x"), meta)


def fake_service():
    """A stand-in for musik_server (musik.call): edits give one MP3 per suggestion, Erkennen fixed fields."""
    calls = []

    async def call(path, body=None, timeout=0):
        calls.append((path, body))
        mp3 = base64.b64encode(musik_server.finish(FRAME, "x", "edited")).decode()
        if path == "/v1/musik/erkennen":
            return 200, {"bpm": 92, "key": "A minor", "caption": "soft piano"}
        if path == "/v1/musik/ton":
            return 200, {"mp3": mp3, "length_s": 60}
        if path == "/v1/musik":
            return 200, {"mp3": mp3, "seconds": 9.0, "length_s": body["seconds"], "variant": "2b"}
        return 200, {"mp3s": [mp3] * body.get("suggestions", 1), "seconds": 12.5, "variant": "2b"}
    return call, calls


def run(j):
    with mock.patch("vorrang.quiet", no_wait):
        asyncio.run(musik._work(j))


class On(unittest.TestCase):
    def setUp(self):
        helpers.set_config(musik=True)
        edit_on()
        music(enabled=True)

    def tearDown(self):
        helpers.set_config(musik=False)
        edit_on(False)
        music(enabled=False, model="")
        musik._jobs.clear()
        musik._recent.clear()


class Off(unittest.TestCase):
    def test_off_by_default_below_making_music(self):
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertFalse(json.load(f)["chat"]["musik_bearbeiten"])
        self.assertNotIn("chat.musik_bearbeiten", features.DEFAULT_ON)
        f = next(x for x in features.FEATURES if x.key == musik.EDIT_KEY)
        self.assertEqual(f.parent, "musik")
        helpers.set_config(musik=True)
        music(enabled=True)
        try:
            c, prof = profile("Bearbeiterin Aus")
            self.assertFalse(features.allowed(musik.EDIT_KEY, prof["id"]))
            self.assertEqual(c.get("/api/musik").json()["edit"], {"on": False})
            s = song(prof["id"])
            for r in (c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "remix"}),
                      c.post(f"/api/musik/{s['id']}/erkennen"), c.post(f"/api/musik/{s['id']}/eigenes"),
                      c.post("/api/musik/hochladen?rechte=1", content=FRAME)):
                self.assertEqual(r.status_code, 403, r.text)
            self.assertNotIn(musik.TOOL_EDIT, (musik.offer({"who": prof, "own": True,
                                                            "text": "Mach mein Lied länger"}) or {}).get("tools", []))
        finally:
            helpers.set_config(musik=False)
            music(enabled=False)


class Access(On):
    def test_guests_and_blocked_profiles_never_edit(self):
        self.assertIn(client().post("/api/musik/0123456789ab/bearbeiten", json={"art": "remix"}).status_code, (401, 403))
        self.assertIn(client().post("/api/musik/hochladen?rechte=1", content=FRAME).status_code, (401, 403))
        self.assertIsNone(musik.offer({"who": None, "own": False, "text": "Mach mein Lied länger"}))
        c, prof = profile("Bearbeiterin Gesperrt")
        s = song(prof["id"])
        block(prof["id"])
        try:
            self.assertEqual(c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "remix"}).status_code, 403)
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                musik.start_edit(prof, s["id"], "remix", {})
        finally:
            block(prof["id"], False)

    def test_only_own_songs(self):
        c, prof = profile("Bearbeiterin Eigen")
        _, other = profile("Bearbeiterin Fremd")
        s = song(other["id"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "remix"}).status_code, 409)
            self.assertEqual(c.post(f"/api/musik/{s['id']}/eigenes").status_code, 404)
            self.assertEqual(c.post("/api/musik/../x/bearbeiten", json={"art": "remix"}).status_code, 404)
            self.assertEqual(c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "rm -rf"}).status_code, 400)


class Upload(On):
    def test_rights_tick_format_and_no_name_in_the_journal(self):
        c, prof = profile("Bearbeiterin Hochladen")
        musik.clear(prof["id"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.post("/api/musik/hochladen?name=Geheim.mp3", content=FRAME).status_code, 400)
            self.assertEqual(c.post("/api/musik/hochladen?rechte=1&name=Geheim.exe", content=b"MZ\x90\x00" * 20).status_code, 409)
        self.assertIn("musik: hochladen nicht gemacht rechte fuer", out.getvalue())
        self.assertEqual(musik.file_format(b"RIFF\x00\x00\x00\x00WAVEfmt "), "wav")
        self.assertEqual(musik.file_format(b"fLaC\x00"), "flac")
        self.assertEqual(musik.file_format(b"<html>"), "")
        sent = []

        class Answer:
            status_code = 200

            def json(self):
                return {"mp3": base64.b64encode(musik_server.finish(FRAME, "x", "")).decode(), "length_s": 182.4}

        class Client:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, params=None, content=None, headers=None):
                sent.append((url, params, len(content)))
                return Answer()

        out = io.StringIO()
        with mock.patch.object(musik.httpx, "AsyncClient", Client), contextlib.redirect_stdout(out):
            r = c.post("/api/musik/hochladen?rechte=1&name=Geheim.mp3", content=FRAME)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["kind"], r.json()["wish"], r.json()["length_s"]), ("upload", "Geheim", 182.4))
        self.assertEqual(sent[0][1], {"art": "mp3"})
        self.assertTrue(sent[0][0].endswith("/v1/musik/quelle"))
        self.assertIn("musik: hochgeladen mp3 182 s fuer", out.getvalue())
        self.assertNotIn("Geheim", out.getvalue())
        row = musik.song_row(prof["id"], r.json()["id"])
        self.assertEqual(row["ai"], "")                          # no AI mark until it is edited
        self.assertEqual(c.get("/api/musik").json()["edit"]["uploads"], 1)


class Plan(unittest.TestCase):
    ROW = {"id": "0123456789ab", "length_s": 120, "caption": "calm piano", "wish": "Klavier", "lyrics": "", "sung": False}

    def plan(self, art, **p):
        return musik.plan_edit(self.ROW, art, p, LIM)

    def test_every_kind_with_its_bounds(self):
        f, label, after, model = self.plan("abschnitt", von=10, bis=20, wunsch="ruhiger")
        self.assertEqual((f["start"], f["end"], after, model), (10, 20, 120, True))
        self.assertEqual(label[0], "Abschnitt neu 0:10–0:20")
        f, label, after, _ = self.plan("verlaengern", sekunden=30, wo="vorne")
        self.assertEqual((f["add_s"], f["where"], after), (30, "vorne", 150))
        f, label, _a, _m = self.plan("richtung", richtung="reggae", nah=4)
        self.assertIn("reggae", f["caption"])
        self.assertEqual((f["near"], label), (musik.NEAR[4], ["Musikrichtung: Reggae", "Genre: Reggae"]))
        f, _l, after, model = self.plan("schneiden", von=0, bis=60, ausblenden=5)
        self.assertEqual((f["start"], f["end"], f["fade_out"], after, model), (0, 60, 5, 60, False))
        f, _l, after, _m = self.plan("tempo", tempo=80, halbtoene=-2)
        self.assertEqual((f["tempo"], f["halftones"], after), (0.8, -2, 150))
        for art, p in (("abschnitt", {"von": 10, "bis": 10.5, "wunsch": "x"}), ("abschnitt", {"von": 0, "bis": 500, "wunsch": "x"}),
                       ("abschnitt", {"von": 0, "bis": 30}), ("verlaengern", {"sekunden": 500, "wo": "hinten"}),
                       ("verlaengern", {"sekunden": 30, "wo": "mitte"}), ("verlaengern", {"sekunden": 200, "wo": "hinten"}),
                       ("richtung", {}), ("tempo", {"tempo": 200}), ("tempo", {"tempo": True, "halbtoene": 9}),
                       ("schneiden", {}), ("text", {"liedtext": "  "}), ("nichts", {})):
            with self.assertRaises(ValueError, msg=(art, p)):
                self.plan(art, **p)

    def test_new_lyrics_close_or_anew_with_its_own_length(self):
        text = "[chorus]\nRefrain\n\n[verse]\nNeue Strophe\n\n[verse]\nNoch eine"
        f, label, after, model = self.plan("text", liedtext=text, sprache="de")
        self.assertEqual((f["lyrics"], f["language"], f["near"], after, model), (text, "de", musik.NEAR[1], 120, True))
        self.assertNotIn("neu", f)
        f, label, after, _m = self.plan("text", liedtext=text, neu=True, sekunden=200)
        self.assertEqual((f["neu"], f["seconds"], after, label[0]), (True, 200, 200, "Neu mit neuem Text"))
        f, _l, after, _m = self.plan("text", liedtext=text, neu=True, sekunden=9000)
        self.assertEqual(after, LIM["max_s"])
        f, _l, _a, _m = self.plan("text", liedtext=text, sprache="xx")
        self.assertEqual(f["language"], "de")


class Versions(On):
    def test_a_change_keeps_suggestions_as_versions_and_the_original(self):
        c, prof = profile("Bearbeiterin Fassungen")
        uid = prof["id"]
        musik.clear(uid)
        s = song(uid)
        call, calls = fake_service()
        out = io.StringIO()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(out):
            r = c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "richtung", "richtung": "jazz", "vorschlaege": 2,
                                                                 "worte": "mit Saxofon"})
            self.assertEqual(r.status_code, 200, r.text)
            run(musik._jobs[r.json()["job"]["id"]])
        path, body = calls[0]
        self.assertEqual((path, body["art"], body["suggestions"]), ("/v1/musik/bearbeiten", "richtung", 2))
        self.assertTrue(base64.b64decode(body["mp3"]).startswith(b"ID3"))
        d = c.get("/api/musik").json()
        self.assertEqual(len(d["songs"]), 3)
        new = [x for x in d["songs"] if x["id"] != s["id"]]
        self.assertEqual({(x["kind"], x["root"], x["von"], x["art"]) for x in new}, {("edit", s["id"], s["id"], "richtung")})
        self.assertEqual(sorted(x["label"][0] for x in new), ["Musikrichtung: Jazz (1)", "Musikrichtung: Jazz (2)"])
        self.assertEqual(musik.song_row(uid, new[0]["id"])["ai"], "edited")
        log = out.getvalue()
        self.assertIn("musik: bearbeitung richtung 2 vorschlaege seite fuer", log)
        self.assertIn("musik: bearbeitet richtung 2 fassungen", log)
        self.assertNotIn("Saxofon", log)
        self.assertNotIn("Klavier", log)
        # „Als eigenes Lied“: a version becomes a song of its own
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post(f"/api/musik/{new[0]['id']}/eigenes").json()["root"], new[0]["id"])
        self.assertEqual(musik.stats()["edited"] >= 1, True)

    def test_new_lyrics_go_with_the_version_and_anew_uses_the_making_path(self):
        c, prof = profile("Bearbeiterin Text")
        uid = prof["id"]
        musik.clear(uid)
        s = song(uid, sung=True, language="de", lyrics="[verse]\nAlt")
        call, calls = fake_service()
        text = "[chorus]\nNeu oben\n\n[verse]\nAlt"
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()):
            j = musik.start_edit(prof, s["id"], "text", {"liedtext": text})
            run(musik._jobs[j["id"]])
            j2 = musik.start_edit(prof, s["id"], "text", {"liedtext": text, "neu": True, "sekunden": 180})
            run(musik._jobs[j2["id"]])
        self.assertEqual(calls[0][0], "/v1/musik/bearbeiten")
        self.assertEqual((calls[0][1]["lyrics"], calls[0][1]["language"]), (text, "de"))
        self.assertEqual((calls[1][0], calls[1][1]["seconds"], calls[1][1]["lyrics"]), ("/v1/musik", 180, text))
        rows = [x for x in musik.all_songs(uid) if x.get("kind") == "edit"]
        self.assertEqual({(x["lyrics"], x["sung"]) for x in rows}, {(text, True)})
        self.assertEqual(sorted(x["length_s"] for x in rows), [120, 180])

    def test_cut_and_tempo_at_once_without_the_model_and_the_limits(self):
        c, prof = profile("Bearbeiterin Ton")
        uid = prof["id"]
        musik.clear(uid)
        s = song(uid)
        call, calls = fake_service()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()):
            r = c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "schneiden", "von": 0, "bis": 60})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual((r.json()["song"]["kind"], r.json()["song"]["length_s"]), ("edit", 60))
            self.assertEqual((calls[0][0], calls[0][1]["mark"]), ("/v1/musik/ton", "made"))
            for _ in range(musik.MAX_VERSIONS - 2):    # versions kept before (without the rate limit of the page)
                musik.keep(uid, musik_server.finish(FRAME, "x"), musik._new_row(s, ["x", "x"], "tempo", 120))
            r = c.post(f"/api/musik/{s['id']}/bearbeiten", json={"art": "tempo", "tempo": 90})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Fassungen", r.json()["detail"])

    def test_detect_fills_only_fixed_fields(self):
        c, prof = profile("Bearbeiterin Erkennen")
        uid = prof["id"]
        musik.clear(uid)
        s = song(uid, caption="")
        call, _ = fake_service()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()):
            j = c.post(f"/api/musik/{s['id']}/erkennen").json()["job"]
            run(musik._jobs[j["id"]])
        row = musik.song_row(uid, s["id"])
        self.assertEqual((row["bpm"], row["key"], row["caption"], row["heard"]), (92, "A minor", "soft piano", True))


class Tool(On):
    def test_the_newest_own_song_never_one_the_model_names(self):
        _, prof = profile("Bearbeiterin Werkzeug")
        uid = prof["id"]
        musik.clear(uid)
        song(uid)
        newest = song(uid, wish="Neuestes")
        call, calls = fake_service()

        async def go(args):
            return await musik.tool("musik_bearbeiten", args, {"who": prof, "client": "web", "out": asyncio.Queue()})
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()):
            text = asyncio.run(go({"art": "verlaengern", "sekunden": 30, "wo": "hinten", "id": "0123456789ab"}))
        self.assertFalse(text.startswith("Not done"), text)
        j = next(iter(musik._jobs.values()))
        self.assertEqual(j["von"], newest["id"])
        self.assertNotIn("text", musik.TOOL_EDIT["function"]["parameters"]["properties"]["art"]["enum"])
        musik._jobs.clear()
        with mock.patch.object(musik, "call", call), contextlib.redirect_stdout(io.StringIO()):
            text = asyncio.run(go({"art": "tempo", "tempo_prozent": 110}))
        self.assertTrue(text.startswith("Done:"), text)
        musik.clear(uid)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(asyncio.run(go({"art": "remix"})).startswith("Not done"))

    def test_offer_and_weiche(self):
        _, prof = profile("Bearbeiterin Weiche")
        musik.clear(prof["id"])
        song(prof["id"])
        o = musik.offer({"who": prof, "own": True, "text": "Mach mein letztes Lied 30 Sekunden länger"})
        self.assertIn(musik.TOOL_EDIT, o["tools"])
        self.assertIn("musik_bearbeiten", intent.classify("Mach aus meinem Lied eine Reggae-Version").tools())
        self.assertNotIn("musik_bearbeiten", intent.classify("Spiel Musik im Wohnzimmer").tools())


class Service(unittest.TestCase):
    def test_edit_body_fixed_fields(self):
        v = next(iter(musik_server.musikmodell.VARIANTS))
        b = musik_server.edit_body({"art": "verlaengern", "length_s": 120, "caption": "piano <b>", "add_s": 30,
                                    "where": "vorne", "suggestions": 2}, v)
        self.assertEqual((b["task_type"], b["repainting_start"], b["repainting_end"], b["synth_batch_size"]),
                         ("repaint", -30, -1, 2))
        self.assertNotIn("<", b["caption"])
        b = musik_server.edit_body({"art": "text", "length_s": 120, "caption": "pop", "lyrics": "[verse]\nHallo",
                                    "language": "de", "near": 0.45}, v)
        self.assertEqual((b["task_type"], b["vocal_language"], b["audio_cover_strength"]), ("cover", "de", 0.45))
        b = musik_server.edit_body({"art": "text", "length_s": 120, "caption": "pop", "lyrics": "[verse]\nHallo"}, v)
        self.assertEqual(b["vocal_language"], "unknown")
        for bad in ({"art": "lego", "length_s": 120, "caption": "x"}, {"art": "remix", "length_s": 120, "caption": ""},
                    {"art": "abschnitt", "length_s": 120, "caption": "x", "start": 5, "end": 5.5},
                    {"art": "remix", "length_s": 120, "caption": "x", "suggestions": 9},
                    {"art": "remix", "length_s": 120, "caption": "x", "near": 3}, []):
            with self.assertRaises(HTTPException, msg=bad):
                musik_server.edit_body(bad, v)

    def test_ffmpeg_gets_fixed_filters_only(self):
        f = musik_server.tone_filters({"length_s": 120, "start": 10, "end": 70, "fade_out": 5})
        self.assertTrue(f.startswith("atrim=start=10"))
        self.assertIn("afade=t=out", f)
        self.assertIn("atempo=0.8", musik_server.tone_filters({"length_s": 120, "tempo": 0.8}))
        self.assertIn("asetrate=", musik_server.tone_filters({"length_s": 120, "halftones": 2}))
        for bad in ({"length_s": 120}, {"length_s": 120, "tempo": 3}, {"length_s": 120, "halftones": 7},
                    {"length_s": 120, "start": 0, "end": 0.5}, {"length_s": 120, "tempo": "0.8;rm"}, "x"):
            with self.assertRaises(HTTPException, msg=bad):
                musik_server.tone_filters(bad)
        args = musik_server.decode_args("mp3")
        i = args.index("-i")
        w = args.index("-protocol_whitelist")
        self.assertTrue(w < i and args[w + 1] == "file,pipe")
        self.assertIn("pipe:0", args)
        with self.assertRaises(HTTPException):
            musik_server.source({"mp3": base64.b64encode(b"<html>").decode()})


if __name__ == "__main__":
    unittest.main()
