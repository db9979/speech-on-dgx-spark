"""Notbetrieb mit Parakeet (plan Raspberry-Pi split B5c): with the models on another computer and that computer gone,
the panel computer's own Parakeet hears only when the admin switched chat.notbetrieb_asr on; a few fixed commands work
by fixed rules without a model (Home Assistant through the panel's path, the time, the own reminders), everything else
keeps the fixed sentence; speakers hear the answers from files made before, never a name or a text of a profile.
No real models; the time is always given, never read from the clock."""
import asyncio
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

import httpx

from tests import helpers

helpers.start()
import chat  # noqa: E402
import common  # noqa: E402
import notbetrieb  # noqa: E402
import steuer  # noqa: E402
import wartung  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZONE = datetime.timezone(datetime.timedelta(hours=2))


def run(coro):
    with redirect_stdout(io.StringIO()) as out:
        got = asyncio.run(coro)
    return got, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.old = common.load_config()
        self.addCleanup(helpers.write_config, self.old)
        c = json.loads(json.dumps(self.old))
        c["models"]["host"] = "192.168.178.171"
        c["chat"]["notbetrieb_asr"] = True
        helpers.write_config(c)
        self.cfg = c
        p = mock.patch.object(steuer, "weg", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def turn(self, text, **kw):
        t = types.SimpleNamespace(who={"id": "u1", "name": "Dominik"}, messages=[{"role": "user", "content": text}],
                                  body={}, ha=None, ha_direct=None, src="browser", direct=None)
        for k, v in kw.items():
            setattr(t, k, v)
        return t


class Hoeren(Base):
    def test_off_by_default_means_the_fixed_sentence_only(self):
        self.cfg["chat"]["notbetrieb_asr"] = False
        helpers.write_config(self.cfg)
        self.assertFalse(notbetrieb.hoert())
        self.assertTrue(wartung.paused("asr"), "without the switch nothing is heard in Notbetrieb")
        self.assertTrue(common.model_url("asr", "/x").startswith("https://192.168.178.171:"))

    def test_switched_on_the_recordings_go_to_this_computer(self):
        self.assertTrue(notbetrieb.hoert())
        self.assertEqual(common.model_url("asr", "/v1/audio/transcriptions"),
                         f"http://127.0.0.1:{common.NOTASR_PORT}/v1/audio/transcriptions")
        self.assertFalse(wartung.paused("asr"))
        self.assertTrue(wartung.paused("llm") and wartung.paused("tts"), "the models stay paused: no model is asked")
        self.assertTrue(common.model_url("tts", "/x").startswith("https://"), "only the recognizer moves")

    def test_with_the_model_computer_there_nothing_changes(self):
        with mock.patch.object(steuer, "weg", return_value=False):
            self.assertFalse(notbetrieb.hoert())
            self.assertTrue(common.model_url("asr", "/x").startswith("https://"))

    def test_all_in_one_never(self):
        helpers.write_config(dict(self.cfg, models=self.old["models"]))
        self.assertFalse(notbetrieb.hoert())
        self.assertIsNone(notbetrieb.for_live())


class Befehle(Base):
    def test_the_time_without_a_model(self):
        now = datetime.datetime(2026, 10, 15, 14, 20, tzinfo=ZONE)
        got, log = run(notbetrieb.antwort(self.turn("Wie spät ist es?"), False, now))
        self.assertEqual(got, "Es ist 14 Uhr 20.")
        self.assertIn("notbetrieb: uhrzeit", log)
        got, _ = run(notbetrieb.antwort(self.turn("What time is it?"), True, now.replace(minute=5)))
        self.assertEqual(got, "It is 14:05.")
        self.assertEqual(notbetrieb.uhrzeit(now.replace(minute=0))[1], ["es_ist", "h14"])

    def test_anything_else_keeps_the_fixed_sentence(self):
        got, log = run(notbetrieb.antwort(self.turn("Erzähl mir einen Witz über Pinguine"), False))
        self.assertIsNone(got)
        self.assertIn("notbetrieb: fester satz", log)

    def test_switching_through_the_panels_own_path(self):
        async def ok(*a):
            return True, "turned on light.wohnzimmer", ["Licht Wohnzimmer"], "home_assistant (Panel)", "", None
        with mock.patch.object(chat, "_ha_panel", ok):
            got, log = run(notbetrieb.antwort(self.turn("Mach das Licht an", ha={"url": "x"}, ha_direct="Mach das Licht an"), False))
        self.assertEqual(got, "Erledigt.", "a fixed sentence, never Home Assistant's text")
        self.assertIn("notbetrieb: befehl ok", log)
        self.assertNotIn("Wohnzimmer", log)

        async def gone(*a):
            raise httpx.ConnectError("x")
        with mock.patch.object(chat, "_ha_panel", gone):
            got, _ = run(notbetrieb.antwort(self.turn("Licht aus", ha={"url": "x"}, ha_direct="Licht aus"), True))
        self.assertEqual(got, notbetrieb.SAETZE["ha_weg"][1])

    def test_the_own_reminders_count_to_hear_list_as_text(self):
        items = [{"due": 1792000000000, "text": "Müll rausbringen"}, {"due": 1792003600000, "text": "Arzt anrufen"}]
        with mock.patch("profiles.reminders", return_value=items):
            got, log = run(notbetrieb.antwort(self.turn("Welche Erinnerungen habe ich?", direct="reminder_list"), False))
        self.assertTrue(got.startswith("Du hast 2 Erinnerungen.\n"))
        self.assertIn("Müll rausbringen", got)
        self.assertIn("notbetrieb: erinnerungen 2", log)
        self.assertNotIn("Müll", log, "the log holds numbers, never a text")
        text, blocks = notbetrieb.erinnerungen([], ZONE)
        self.assertEqual((text, blocks), (notbetrieb.SAETZE["keine"][0], ["keine"]))
        self.assertEqual(notbetrieb.erinnerungen(items * 6, ZONE)[1], ["viele"])


class Lautsprecher(Base):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp(dir=helpers.TMP)
        self.addCleanup(shutil.rmtree, self.dir, True)
        p = mock.patch.object(notbetrieb, "CLIPS", self.dir)
        p.start()
        self.addCleanup(p.stop)
        notbetrieb._clip_try["t"] = 0.0

    def test_files_are_made_a_few_at_a_time_and_build_the_answer(self):
        said = []

        async def speak(text):
            said.append(text)
            yield b"\x01\x00" * notbetrieb.RATE
        rounds = 0
        while run(notbetrieb.make_clips(1000.0, speak))[0]:
            rounds += 1
        have, need = notbetrieb.files_ready()
        self.assertEqual(have, need)
        self.assertGreater(rounds, 1, "never all files in one round of the loop")
        self.assertFalse([t for t in said if "Dominik" in t], "no name of a profile in a file")
        text = notbetrieb.merken(*notbetrieb.uhrzeit(datetime.datetime(2026, 1, 1, 7, 3, tzinfo=ZONE)))
        pcm = notbetrieb.ton(text)
        self.assertGreater(len(pcm), 3 * notbetrieb.RATE * 2)
        self.assertIsNone(notbetrieb.ton("Ein Satz, den der Notbetrieb nie sagt."))

    def test_a_missing_block_gives_no_half_sentence(self):
        text = notbetrieb.merken(*notbetrieb.satz("erledigt"))
        self.assertIsNone(notbetrieb.ton(text))

    def test_a_failed_speech_output_waits(self):
        async def broken(text):
            raise httpx.ConnectError("x")
            yield b""
        got, log = run(notbetrieb.make_clips(1000.0, broken))
        self.assertFalse(got)
        self.assertIn("notbetrieb: satzdateien fehlgeschlagen ConnectError 0", log)
        self.assertFalse(run(notbetrieb.make_clips(1000.0 + 60, broken))[0])
        self.assertEqual(os.listdir(self.dir), [])

    def test_nothing_is_made_with_the_switch_off(self):
        self.cfg["chat"]["notbetrieb_asr"] = False
        helpers.write_config(self.cfg)

        async def speak(text):
            yield b"\x01\x00" * notbetrieb.RATE
        self.assertFalse(run(notbetrieb.make_clips(1000.0, speak))[0])


class Dienst(unittest.TestCase):
    def test_the_front_end_in_notbetrieb(self):
        """asr_proxy.py with SPEECH_SPARK_NOTASR=1: Parakeet, only 127.0.0.1, not loaded at the start."""
        env = dict(os.environ, SPEECH_SPARK_NOTASR="1")
        code = ("import asr_proxy as a, common; print(a.cfg['recognizer'], a.cfg['host'], a.cfg['port'] == common.NOTASR_PORT,"
                " a.local.status)")
        r = subprocess.run([sys.executable, "-c", code], cwd=APP, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(r.stdout.split(), ["parakeet", "127.0.0.1", "True", "loading"])

    def test_unload_gives_the_memory_back(self):
        sys.path.insert(0, APP)
        import parakeet
        rec = parakeet.Recognizer()
        rec.rec, rec.status = object(), "ready"
        with redirect_stdout(io.StringIO()):
            rec.unload()
        self.assertEqual((rec.rec, rec.status), (None, "idle"))


if __name__ == "__main__":
    unittest.main()
