"""Pi-Stimme (plan alzeo-mischbetrieb M4): with the models on another computer, the panel computer speaks by itself with
the Piper voice Thorsten only when the admin switched chat.notbetrieb_tts on and the model computer's speech output is
gone (Notbetrieb) or given away by its Speicher-Wache (Mischbetrieb). The voice package is pinned by its SHA-256 and
unpacked only below its own folder; its files never become clips of another voice. No real model, no network."""
import asyncio
import io
import json
import os
import shutil
import struct
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import ack  # noqa: E402
import common  # noqa: E402
import notbetrieb  # noqa: E402
import pistimme  # noqa: E402
import steuer  # noqa: E402
import wartung  # noqa: E402

KEY = {"Authorization": "Bearer sk-test"}


def paket(path, extra=None):
    """A small package like the real one; extra: (TarInfo, bytes) to add."""
    with tarfile.open(path, "w:bz2") as t:
        for name, data in ((pistimme.PAKET + "/" + pistimme.MODELL, b"onnx"), (pistimme.PAKET + "/tokens.txt", b"a 1\n")):
            i = tarfile.TarInfo(name)
            i.size = len(data)
            t.addfile(i, io.BytesIO(data))
        if extra:
            t.addfile(extra[0], io.BytesIO(extra[1]) if extra[1] is not None else None)
    return pistimme._hash(path)


class Paket(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.ziel = os.path.join(self.dir, "pistimme")
        self.tar = os.path.join(self.dir, "p.tar.bz2")

    def test_pinned_and_fixed(self):
        self.assertTrue(pistimme.URL.startswith("https://github.com/k2-fsa/sherpa-onnx/releases/download/"))
        self.assertRegex(pistimme.SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(common.NOTTTS_PORT, 31022)
        self.assertIn(common.NOTTTS_PORT, range(31000, 31100), "own ports stay at or below 31099")

    def test_a_wrong_file_is_never_unpacked(self):
        paket(self.tar)
        with self.assertRaises(ValueError) as e:
            pistimme.entpacken(self.tar, self.ziel)
        self.assertEqual(e.exception.args[0], "hash")
        self.assertFalse(os.path.exists(self.ziel))
        self.assertFalse(pistimme.da(self.ziel))

    def test_the_pinned_file_is_unpacked_and_noted(self):
        h = paket(self.tar)
        with mock.patch.object(pistimme, "SHA256", h):
            pistimme.entpacken(self.tar, self.ziel)
            self.assertTrue(pistimme.da(self.ziel))
        self.assertFalse(pistimme.da(self.ziel), "another pin: fetched again")

    def test_links_and_paths_out_are_refused(self):
        link = tarfile.TarInfo(pistimme.PAKET + "/x")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        weg = tarfile.TarInfo(pistimme.PAKET + "/../../boese")
        weg.size = 1
        fremd = tarfile.TarInfo("anderes/datei")
        fremd.size = 1
        for extra, wort in (((link, None), "art"), ((weg, b"x"), "pfad"), ((fremd, b"x"), "pfad")):
            with self.subTest(wort=wort):
                h = paket(self.tar, extra)
                with mock.patch.object(pistimme, "SHA256", h), self.assertRaises(ValueError) as e:
                    pistimme.entpacken(self.tar, self.ziel)
                self.assertEqual(e.exception.args[0], wort)
                self.assertFalse(os.path.exists(os.path.join(self.dir, "boese")))
                self.assertFalse(pistimme.da(self.ziel))


class Anfrage(unittest.TestCase):
    def test_only_the_small_part_of_the_api(self):
        self.assertEqual(pistimme.anfrage({"input": "Hallo."}), ("Hallo.", "pcm", False, 1.0))
        self.assertEqual(pistimme.anfrage({"input": "Hallo.", "response_format": "wav", "stream": True, "speed": 1.2,
                                           "voice": "eigen-x"})[1:], ("wav", True, 1.2))
        self.assertEqual(pistimme.anfrage({"input": "Hallo.", "speed": 9})[3], 1.0)
        for body, wort in (({"input": "x", "response_format": "mp3"}, "format"), ({"input": " "}, "input"),
                           ({"input": "x" * (pistimme.MAX_INPUT + 1)}, "lang"), ([], "input")):
            with self.subTest(wort=wort), self.assertRaises(ValueError) as e:
                pistimme.anfrage(body)
            self.assertEqual(e.exception.args[0], wort)

    def test_24_khz_like_every_other_voice(self):
        pcm = pistimme.pcm16([0.0, 0.5, -0.5, 1.0] * 2205)
        self.assertEqual(len(pcm) // 2, 9600)
        self.assertEqual(pistimme.wav(pcm)[:4], b"RIFF")
        self.assertEqual(struct.unpack("<I", pistimme.wav(pcm)[24:28])[0], 24000)


class FakeStimme(pistimme.Stimme):
    def __init__(self, d):
        super().__init__(d, idle=600)
        self.gesagt = []

    def sprich(self, satz, speed=1.0):
        self.gesagt.append(satz)
        return b"\x01\x00" * 100


class Dienst(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.stimme = FakeStimme(self.dir)
        self.c = TestClient(pistimme.app_bauen(self.stimme))
        p = mock.patch.object(pistimme, "da", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def post(self, body, headers=KEY):
        with redirect_stdout(io.StringIO()) as out:
            r = self.c.post("/v1/audio/speech", json=body, headers=headers)
        return r, out.getvalue()

    def test_the_api_key_is_needed(self):
        r, _ = self.post({"input": "Hallo."}, headers={})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.stimme.gesagt, [])

    def test_sentence_by_sentence_as_events(self):
        r, log = self.post({"input": "Hallo. Wie geht es dir?", "stream": True})
        self.assertEqual(r.status_code, 200)
        events = [json.loads(ln[5:]) for ln in r.text.splitlines() if ln.startswith("data:")]
        self.assertEqual([e["type"] for e in events], ["speech.audio.delta"] * 2 + ["speech.audio.done"])
        self.assertEqual(len(self.stimme.gesagt), 2)
        self.assertIn("notbetrieb: pistimme gesprochen 2 saetze", log)
        self.assertNotIn("Hallo", log, "never a text in the log")

    def test_pcm_and_wav_but_no_mp3(self):
        r, _ = self.post({"input": "Hallo.", "response_format": "wav"})
        self.assertEqual(r.content[:4], b"RIFF")
        r, _ = self.post({"input": "Hallo."})
        self.assertEqual(r.content, b"\x01\x00" * 100)
        r, log = self.post({"input": "Hallo.", "response_format": "mp3"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("notbetrieb: pistimme abgelehnt format", log)

    def test_missing_voice_says_so(self):
        with mock.patch.object(pistimme, "da", return_value=False):
            r, log = self.post({"input": "Hallo."})
        self.assertEqual(r.status_code, 503)
        self.assertIn("notbetrieb: pistimme fehlt", log)

    def test_it_forgets_after_the_idle_time(self):
        self.stimme.tts = object()
        with redirect_stdout(io.StringIO()):
            self.assertFalse(self.stimme.vergessen(self.stimme.used + 10))
            self.assertTrue(self.stimme.vergessen(self.stimme.used + 601))
        self.assertIsNone(self.stimme.tts)


class Panel(unittest.TestCase):
    def setUp(self):
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)
        c = json.loads(json.dumps(self.old))
        c["models"]["host"] = "192.168.178.171"
        c["chat"]["notbetrieb_tts"] = True
        helpers.write_config(c)
        self.cfg = c
        for name, v in (("weg", True), ("stimme_frei", False)):
            p = mock.patch.object(steuer, name, return_value=v)
            p.start()
            self.addCleanup(p.stop)

    def test_off_by_default(self):
        with open(os.path.join(os.path.dirname(common.__file__), "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["notbetrieb_tts"], False)
        self.cfg["chat"]["notbetrieb_tts"] = False
        helpers.write_config(self.cfg)
        self.assertFalse(notbetrieb.spricht())
        self.assertTrue(wartung.paused("tts"))
        self.assertTrue(common.model_url("tts", "/x").startswith("https://192.168.178.171:"))

    def test_in_notbetrieb_this_computer_speaks(self):
        self.assertTrue(notbetrieb.spricht())
        self.assertEqual(common.model_url("tts", "/v1/audio/speech"),
                         f"http://127.0.0.1:{common.NOTTTS_PORT}/v1/audio/speech")
        self.assertFalse(wartung.paused("tts"))
        self.assertTrue(wartung.paused("llm"), "the language model stays paused")

    def test_while_the_guard_gave_the_voice_away(self):
        with mock.patch.object(steuer, "weg", return_value=False), \
                mock.patch.object(steuer, "stimme_frei", return_value=True):
            self.assertTrue(notbetrieb.spricht())
            self.assertFalse(wartung.paused("tts"))
        with mock.patch.object(steuer, "weg", return_value=False):
            self.assertFalse(notbetrieb.spricht(), "with the model computer speaking nothing changes")
            self.assertTrue(common.model_url("tts", "/x").startswith("https://"))

    def test_all_in_one_never(self):
        helpers.write_config(dict(self.cfg, models=self.old["models"]))
        self.assertFalse(notbetrieb.spricht())

    def test_its_sound_never_becomes_a_clip_of_another_voice(self):
        url = common.model_url("tts", "/v1/audio/speech")
        with mock.patch.object(ack, "_record", side_effect=AssertionError("asked")):
            got = asyncio.run(ack.record_missing(url, KEY, {"voice": "vivian"}, "German", texts=["Moment."]))
        self.assertEqual(got, 0)
        with mock.patch("esp32.make_pause_clips", side_effect=AssertionError("made")), \
                mock.patch.object(notbetrieb, "make_clips", side_effect=AssertionError("made")):
            self.cfg["chat"]["esp32"] = True
            helpers.write_config(self.cfg)
            self.assertFalse(asyncio.run(wartung.clips_tick(1000.0)))

    def test_live_shows_it(self):
        with mock.patch.object(pistimme, "da", return_value=True):
            d = notbetrieb.for_live()
        self.assertTrue(d["stimme"] and d["spricht"] and d["stimme_da"])


if __name__ == "__main__":
    unittest.main()
