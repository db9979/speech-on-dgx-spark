"""Musik machen, stage M0 (musik.py, musik_server.py, musikmodell.py, bedarf.py; plan plaene/musik.md, Dominik
2026-10-16 „1a 2a 3a 4a 5a“): off unless installed; only the admin measures, never a profile or a guest; the
measurement uses fixed songs only and keeps numbers, never a caption or lyrics in the journal; the service sets every
field of the engine itself, takes only an MP3 back and marks it as made by an AI; the model files and the engine are
pinned; install.sh builds it only on request. The music service is faked (no GPU); nothing depends on the time."""
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
import musik  # noqa: E402
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
        music(enabled=False)
        wait_done()

    def test_only_the_admin_measures(self):
        self.assertEqual(client().post("/api/admin/musik-test").status_code, 401)
        self.assertEqual(client().get("/api/admin/musik-test").status_code, 401)
        self.assertEqual(client().get("/api/admin/musik-test/1.mp3").status_code, 401)

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
        self.assertEqual([t["why"] for t in last["tests"]], ["missing", "missing"])
        self.assertFalse(last["ok"])
        for line in out.getvalue().splitlines():
            self.assertTrue(line.startswith("musik: "), line)

    def test_fixed_songs_numbers_and_files(self):
        music(enabled=True)
        sent = []

        async def fake(path, body=None, timeout=0):
            if path == "/health":
                return 200, {"service": "musik", "status": "ready"}
            sent.append(body)
            mp3 = musik_server.finish(FRAME, body["title"])
            return 200, {"mp3": base64.b64encode(mp3).decode(), "seconds": 12.5, "lm_s": 3.0, "synth_s": 9.5,
                         "peak_gib": 8.1, "length_s": body["seconds"]}

        a = admin()
        out = io.StringIO()
        with mock.patch.object(musik, "call", fake), contextlib.redirect_stdout(out):
            self.assertEqual(a.post("/api/admin/musik-test").status_code, 200)
            wait_done()
            d = a.get("/api/admin/musik-test").json()
        self.assertTrue(d["last"]["ok"], d)
        self.assertEqual([t["peak_gib"] for t in d["last"]["tests"]], [8.1, 8.1])
        # the songs come from the fixed list only: nothing from a person or a model
        self.assertEqual([(b["caption"], b["lyrics"]) for b in sent], [(t["caption"], t["lyrics"]) for t in musik.TESTS])
        r = a.get("/api/admin/musik-test/2.mp3")
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "audio/mpeg"))
        self.assertTrue(r.content.startswith(b"ID3"))
        self.assertEqual(a.get("/api/admin/musik-test/3.mp3").status_code, 404)
        # the journal names numbers, never a caption or the lyrics
        log = out.getvalue()
        for t in musik.TESTS:
            self.assertNotIn(t["caption"], log)
            self.assertNotIn("Morgen", log)
        self.assertEqual(musik.for_live(), {"on": True, "run": False, "ok": 2, "total": 2})   # Live: numbers only

    def test_a_maintenance_pause_waits(self):
        music(enabled=True)
        a = admin()
        asked = []

        async def fake(path, body=None, timeout=0):
            asked.append(path)
            return 200, {"service": "musik", "status": "ready"}

        with mock.patch.object(wartung, "paused", lambda part: part == "musik"), \
                mock.patch.object(musik, "call", fake), contextlib.redirect_stdout(io.StringIO()):
            a.post("/api/admin/musik-test")
            wait_done()
        self.assertEqual([t["why"] for t in musik.last_test()["tests"]], ["pause", "pause"])
        self.assertNotIn("/v1/musik", asked, "no song during a Wartungspause")

    def test_install_keys_stay(self):
        a = admin()
        cfg = a.get("/api/config").json()
        new = json.loads(json.dumps(cfg))
        new["music"].update(enabled=True, variant="xl", port=1, engine_port=2, idle_min=99)
        admin_mod.validate(new)
        self.assertEqual(new["music"], cfg["music"])


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

        async def ready():
            e.state = "ready"

        with mock.patch.object(e, "start", ready), mock.patch.object(e, "alive", lambda: True), \
                mock.patch.object(musik_server, "POLL_S", 0):
            raw, lm_s, synth_s, peak = asyncio.run(e.make(req))
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
            asyncio.run(e.start())
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
