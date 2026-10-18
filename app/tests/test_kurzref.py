"""Several voices at once (V01.0.800): a shorter reference for a cloned voice (kurzref.py, tts.ref_max_s), the
decoder batch and the prefix cache of the speech engine (engine.sh, tts.engine_decode_batch / engine_prefix_cache).
All three are off by default and change nothing then."""
import array
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import kurzref  # noqa: E402
import tts_proxy  # noqa: E402

RATE = 24000


def speech(seconds, pauses=(), rate=RATE):
    """16-bit mono PCM: a loud tone with silent 200 ms gaps starting at the given seconds."""
    pcm = array.array("h", [0]) * int(seconds * rate)
    for i in range(len(pcm)):
        pcm[i] = 8000 if (i // 40) % 2 else -8000
    for p in pauses:
        for i in range(int(p * rate), min(len(pcm), int((p + 0.2) * rate))):
            pcm[i] = 0
    return pcm.tobytes()


class Cut(unittest.TestCase):
    def test_short_recordings_stay(self):
        self.assertIsNone(kurzref.cut_at(RATE, 1, speech(11.5), 10))   # within the limit plus SLACK_S

    def test_cuts_in_the_pause_before_the_limit(self):
        keep = kurzref.cut_at(RATE, 1, speech(30, pauses=(4.0, 8.2, 12.0)), 10)
        self.assertTrue(8.2 * RATE <= keep <= 8.4 * RATE, keep / RATE)

    def test_never_shorter_than_the_minimum(self):
        keep = kurzref.cut_at(RATE, 1, speech(20, pauses=(1.0,)), 8)
        self.assertGreaterEqual(keep, kurzref.MIN_S * RATE)
        self.assertLessEqual(keep, 8 * RATE)

    def test_stereo_and_other_formats(self):
        stereo = array.array("h", [v for x in array.array("h", speech(30, pauses=(9.0,))) for v in (x, x)]).tobytes()
        keep = kurzref.cut_at(RATE, 2, stereo, 10)
        self.assertTrue(9.0 * RATE <= keep <= 9.2 * RATE, keep / RATE)
        wav = kurzref.write_wav(RATE, 1, speech(1))
        self.assertEqual(kurzref.read_wav(wav)[:2], (RATE, 1))
        self.assertIsNone(kurzref.read_wav(b"not a wav"))


class Words(unittest.TestCase):
    OWN = "Hallo, ich bin Dominik. Ich wohne in Berlin und spreche heute ein paar Sätze für den Spark."

    def test_keeps_the_own_spelling_of_what_was_heard(self):
        self.assertEqual(kurzref.keep_words(self.OWN, "hallo ich bin dominik ich wohne in berlin"),
                         "Hallo, ich bin Dominik. Ich wohne in Berlin")

    def test_small_slips_of_recognition_still_fit(self):
        self.assertEqual(kurzref.keep_words(self.OWN, "Hallo ich bin Dominic. Ich wohne in Berlin"),
                         "Hallo, ich bin Dominik. Ich wohne in Berlin")

    def test_other_words_do_not_fit(self):
        self.assertIsNone(kurzref.keep_words(self.OWN, "Das Wetter morgen wird sonnig und warm"))
        self.assertIsNone(kurzref.keep_words(self.OWN, ""))


class Proxy(unittest.TestCase):
    """tts_proxy: the shorter piece only with tts.ref_max_s, the whole recording until it is cut and when it fails."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=helpers.TMP)
        self._p = [mock.patch.object(tts_proxy, "VOICES_DIR", self.dir), mock.patch.dict(tts_proxy.cfg, {"ref_max_s": 10})]
        for p in self._p:
            p.start()
        for d in (tts_proxy._short, tts_proxy._short_tried, tts_proxy._ref_cache):
            d.clear()
        with open(os.path.join(self.dir, "dom.wav"), "wb") as f:
            f.write(kurzref.write_wav(RATE, 1, speech(30, pauses=(9.0,))))
        with open(os.path.join(self.dir, "dom.txt"), "w") as f:
            f.write(Words.OWN)

    def tearDown(self):
        for p in self._p:
            p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def shorten(self, heard):
        async def transcribe(wav):
            return heard
        with mock.patch.object(tts_proxy, "transcribe", transcribe), mock.patch("builtins.print") as out:
            asyncio.run(tts_proxy.shorten("dom"))
        return " ".join(str(c.args[0]) for c in out.call_args_list)

    def test_off_by_default(self):
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            tts = json.load(f)["tts"]
        self.assertEqual((tts["ref_max_s"], tts["engine_decode_batch"], tts["engine_prefix_cache"]), (0, 1, False))
        with mock.patch.dict(tts_proxy.cfg, {"ref_max_s": 0}):
            url, text = tts_proxy.clone_reference("dom")
            asyncio.run(tts_proxy.shorten("dom"))
        self.assertEqual(text, Words.OWN)
        self.assertFalse(tts_proxy._short)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "kurz")))

    def test_shortened_piece_with_its_words(self):
        whole, _ = tts_proxy.clone_reference("dom")
        log = self.shorten("Hallo ich bin Dominik ich wohne in Berlin")
        self.assertIn("tts: referenz gekuerzt 30.0 s auf 9.1 s", log)
        self.assertNotIn("dom", log)                              # no name, no text in the log
        url, text = tts_proxy.clone_reference("dom")
        self.assertEqual(text, "Hallo, ich bin Dominik. Ich wohne in Berlin")
        self.assertLess(len(url), len(whole) / 2)
        self.assertEqual(tts_proxy.clone_voices(), ["dom"])       # kurz/ is no voice of its own
        tts_proxy._short.clear()                                  # after a restart: from voices/kurz/
        with mock.patch("builtins.print") as out:
            asyncio.run(tts_proxy.shorten("dom"))
        self.assertIn("tts: referenz kurz geladen", out.call_args_list[0].args[0])
        self.assertEqual(tts_proxy.clone_reference("dom")[1], text)

    def test_a_new_recording_or_limit_cuts_again(self):
        self.shorten("Hallo ich bin Dominik ich wohne in Berlin")
        with mock.patch.dict(tts_proxy.cfg, {"ref_max_s": 15}):
            self.assertEqual(tts_proxy.clone_reference("dom")[1], Words.OWN)
            self.assertIsNone(kurzref.cached(self.dir, "dom", os.path.getmtime(os.path.join(self.dir, "dom.wav")), 15))

    def test_the_whole_recording_when_it_does_not_fit(self):
        self.assertIn("tts: referenz nicht gekuerzt passt nicht", self.shorten("Das Wetter wird morgen sonnig"))
        self.assertEqual(tts_proxy.clone_reference("dom")[1], Words.OWN)
        self.assertIn("tts: referenz nicht gekuerzt spracherkennung", (tts_proxy._short_tried.clear(), self.shorten(None))[1])
        self.assertFalse(tts_proxy._short)

    def test_without_a_transcript_only_the_sound(self):
        os.remove(os.path.join(self.dir, "dom.txt"))
        self.assertIn("tts: referenz gekuerzt", self.shorten("never asked"))
        self.assertEqual(tts_proxy.clone_reference("dom")[1], "")
        body = {}
        tts_proxy.apply_clone(body)
        self.assertTrue(body["x_vector_only_mode"])

    def test_short_recordings_and_other_formats_stay(self):
        with open(os.path.join(self.dir, "dom.wav"), "wb") as f:
            f.write(kurzref.write_wav(RATE, 1, speech(9)))
        self.assertIn("tts: referenz nicht gekuerzt schon kurz", self.shorten("x"))
        with open(os.path.join(self.dir, "dom.wav"), "wb") as f:
            f.write(b"RIFF....WAVEfmt float")
        os.utime(os.path.join(self.dir, "dom.wav"), (1, 1))
        self.assertIn("tts: referenz nicht gekuerzt format", self.shorten("x"))


class Engine(unittest.TestCase):
    """engine.sh: the decoder batch and the prefix cache go into the deploy file and the stage values only when on."""

    def run_part(self, tts):
        with open(os.path.join(helpers.APP, "engine.sh"), encoding="utf-8") as f:
            src = f.read()
        part = src[src.index("# Several voices at once"):src.index("# --disable-log-stats")]
        d = tempfile.mkdtemp(dir=helpers.TMP)
        os.makedirs(os.path.join(d, "venv", "bin"))
        with open(os.path.join(d, "base.yaml"), "w") as f:
            f.write("x: 1\n")
        with open(os.path.join(d, "venv", "bin", "python"), "w") as f:
            f.write(f"#!/bin/sh\necho {d}/base.yaml\n")
        os.chmod(os.path.join(d, "venv", "bin", "python"), 0o755)
        with open(os.path.join(d, "c.json"), "w") as f:
            json.dump({"tts": tts}, f)
        script = (f"set -euo pipefail; fail() {{ echo \"FAIL $1\"; exit 1; }}; CONFIG={d}/c.json; STATE_DIR={d}; "
                  f"VENV={d}/venv; ROLE=main; MEM0=0.04; MEM1=0.025; SEQS=2; MAXLEN=4096\n{part}\n"
                  'echo "OV $overrides"; [ -n "${deploy_file:-}" ] && cat "$deploy_file"; true')
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30).stdout
        shutil.rmtree(d, ignore_errors=True)
        return out

    def test_off_leaves_vllm_omnis_defaults(self):
        out = self.run_part({"initial_chunk_frames": 10, "engine_decode_batch": 1, "engine_prefix_cache": False})
        self.assertIn("codec_chunk_ramp", out)
        self.assertNotIn("decode_batch_max_size", out)
        self.assertNotIn("prefix", out)

    def test_on(self):
        out = self.run_part({"initial_chunk_frames": 0, "engine_decode_batch": 4, "engine_prefix_cache": True})
        self.assertIn("decode_batch_max_size: 4", out)
        self.assertIn("decode_cudagraph_batch_sizes: [1,2,3,4]", out)
        self.assertIn('"enable_prefix_caching":true', out)
        self.assertNotIn("codec_chunk_ramp", out)
        self.assertIn("FAIL invalid engine_decode_batch '3'", self.run_part({"engine_decode_batch": 3}))
        self.assertIn("FAIL invalid engine_prefix_cache", self.run_part({"engine_prefix_cache": "yes"}))


if __name__ == "__main__":
    unittest.main()
