"""Wartungspause (wartung.py, plan plaene/wartungspause.md).

Off without the admin's switch; only admins start and end it; a question during a pause of the language model gets
the fixed sentence at once and the model is never asked; background work on the model waits and runs afterwards;
the Dienst-Wächter and the watchdog leave a paused part alone until its time is over; at the end of the time the
pause ends only after OK_N good checks, else it stays, the admins get one push and the Dienst-Wächter counts again;
a damaged file is no pause; the shell command; Live shows the part as paused; the Notaus is never touched.
No test depends on the wall clock: times are passed in or taken relative to now.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import dienstwacht  # noqa: E402
import esp32  # noqa: E402
import guard  # noqa: E402
import health  # noqa: E402
import live  # noqa: E402
import notaus  # noqa: E402
import push  # noqa: E402
import vorrang  # noqa: E402
import wartung  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000.0


def run(coro):
    return asyncio.run(coro)


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(wartung=True, public=True)
        wartung.end("test")
        for k in [k for k in guard._rate if k[0] == "wartung"]:
            guard._rate.pop(k, None)

    def tearDown(self):
        wartung.end("test")
        helpers.set_config(wartung=False)


class Off(Base):
    def test_nothing_without_the_switch(self):
        wartung.start(["llm"], 30, "main", now=T0)
        helpers.set_config(wartung=False)
        self.assertFalse(wartung.paused("llm"))
        self.assertEqual(ADMIN.post("/api/admin/wartung", json={"parts": ["llm"], "minutes": 30}).status_code, 409)
        code, line = wartung.cli(["llm", "30"])
        self.assertEqual(code, 1)
        self.assertIn("Funktionen → Wartungspause", line)

    def test_switch_off_ends_a_running_pause(self):
        wartung.start(["llm"], 30, "main", now=T0)
        helpers.set_config(wartung=False)
        self.assertEqual(run(wartung.tick(T0 + 60)), "aus")
        self.assertFalse(wartung.state()["on"])

    def test_damaged_file_is_no_pause(self):
        with open(wartung.FILE, "w") as f:
            f.write("{kaputt")
        self.assertFalse(wartung.paused("llm"))
        with open(wartung.FILE, "w") as f:
            f.write('{"on": true, "parts": ["llm"], "since": 5, "until": 1}')
        self.assertFalse(wartung.paused("llm"))
        os.remove(wartung.FILE)


class Api(Base):
    def test_only_admins(self):
        anon = TestClient(panel.app)
        self.assertIn(anon.get("/api/admin/wartung").status_code, (401, 403))
        self.assertIn(anon.post("/api/admin/wartung", json={"parts": ["llm"], "minutes": 30}).status_code, (401, 403))
        self.assertIn(anon.post("/api/admin/wartung/weiter").status_code, (401, 403))
        self.assertFalse(wartung.state()["on"])

    def test_start_more_and_weiter(self):
        r = ADMIN.post("/api/admin/wartung", json={"parts": ["tts", "llm"], "minutes": 15})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["paused"])
        self.assertEqual(d["parts"], ["llm", "tts"])
        self.assertEqual(d["by"], "Admin")
        self.assertTrue(14 <= d["left"] <= 15)
        self.assertTrue(30 - 1 <= ADMIN.post("/api/admin/wartung", json={"more": True}).json()["left"] <= 30)
        self.assertFalse(ADMIN.post("/api/admin/wartung/weiter").json()["paused"])
        self.assertFalse(wartung.paused("llm"))

    def test_wrong_input_is_refused(self):
        for body in ({"parts": ["gpu"], "minutes": 30}, {"parts": [], "minutes": 30}, {"parts": ["llm"], "minutes": 1},
                     {"parts": ["llm"], "minutes": 999}, {"parts": ["llm"], "minutes": True}, {"parts": "llm", "minutes": 30},
                     {"more": True}):
            self.assertEqual(ADMIN.post("/api/admin/wartung", json=body).status_code, 400, body)
        self.assertEqual(ADMIN.post("/api/admin/wartung", content=b"x" * 300,
                                    headers={"Content-Type": "application/json"}).status_code, 413)
        self.assertFalse(wartung.state()["on"])

    def test_the_kill_switch_is_never_touched(self):
        before = notaus.level()
        ADMIN.post("/api/admin/wartung", json={"parts": ["llm", "asr", "tts"], "minutes": 30})
        ADMIN.post("/api/admin/wartung/weiter")
        self.assertEqual(notaus.level(), before)


class Chat(Base):
    def test_fixed_sentence_and_the_model_is_not_asked(self):
        wartung.start(["llm"], 30, "main")
        n = len(helpers.LLM_CALLS)
        r = ADMIN.post("/api/chat", json={"messages": [{"role": "user", "content": "Wie wird das Wetter morgen?"}]})
        self.assertEqual(r.status_code, 200, r.text)
        evs = helpers.events(r)
        said = "".join(e.get("delta", "") for e in evs if e["type"] == "text")
        self.assertTrue(said.startswith("Ich werde gerade aktualisiert und bin in etwa "), said)
        self.assertFalse([e for e in evs if e["type"] == "error"])
        self.assertEqual(len(helpers.LLM_CALLS), n, "the model was asked during the pause")
        self.assertGreaterEqual(wartung.view()["asked"], 1)

    def test_english_and_overdue(self):
        wartung.start(["llm"], 30, "main", now=T0)
        self.assertIn("about 30 minutes", wartung.sentence(True, now=T0))
        self.assertIn("in etwa 1 Minute wieder", wartung.sentence(False, now=T0 + 29 * 60 + 30))
        self.assertIn("gleich wieder da", wartung.sentence(False, now=T0 + 31 * 60))

    def test_only_tts_paused_gives_text_only(self):
        wartung.start(["tts"], 30, "main")
        n = len(helpers.LLM_CALLS)
        evs = helpers.events(ADMIN.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}]}))
        self.assertGreater(len(helpers.LLM_CALLS), n, "a pause of the speech output leaves the model alone")
        self.assertFalse([e for e in evs if e["type"] == "audio"])

    def test_weiche_and_systemone_do_not_ask(self):
        import intent
        import systemone
        wartung.start(["llm"], 30, "main")
        self.assertIsNone(run(intent.ask_model({"llm_url": "http://127.0.0.1:1/v1"}, "Wetter?")))
        with self.assertRaises(systemone.Unavailable):
            systemone._prep({"llm_url": "http://127.0.0.1:1/v1"}, next(iter(systemone.USES)), "x", [])


class Background(Base):
    def test_model_work_waits_and_runs_afterwards(self):
        wartung.start(["llm"], 30, "main", now=T0)
        ran, slept = [], []

        async def sleep(s):
            slept.append(s)
            if len(slept) == 3:
                wartung.end("weiter")

        async def work():
            ran.append(wartung.paused("llm"))
            return "ok"

        with mock.patch.object(vorrang, "speaking", lambda now=None: False):
            self.assertEqual(run(vorrang.run("Lernen", work, sleep=sleep)), "ok")
        self.assertEqual(ran, [False], "the work ran only after the pause")
        self.assertEqual(len(slept), 3)

    def test_other_waits_do_not_hold_without_model(self):
        wartung.start(["llm"], 30, "main", now=T0)
        with mock.patch.object(vorrang, "speaking", lambda now=None: False):
            self.assertEqual(run(vorrang.quiet("Sicherung")), 0)
            self.assertEqual(vorrang.hold("Sicherung"), 0)


class Watchers(Base):
    def test_dienstwacht_and_watchdog_stay_out_until_the_time_is_over(self):
        wartung.start(["asr", "llm"], 30, "main")
        self.assertTrue(dienstwacht._maintained("qwen"))
        self.assertTrue(dienstwacht._maintained("asr"))
        self.assertFalse(dienstwacht._maintained("tts"))
        restarted = []
        with mock.patch.object(health, "_restart", lambda *a: restarted.append(a[0])), \
                mock.patch.object(health, "service_health", mock.AsyncMock(return_value=None)), \
                mock.patch.object(health, "judge", lambda *a, **k: "antwortet nicht"):
            run(health.watch_once())
        self.assertNotIn("ASR", restarted)
        self.assertIn("TTS", restarted)
        s = wartung.state()
        wartung._write(dict(s, overdue=True))
        self.assertFalse(dienstwacht._maintained("qwen"), "after its time the Dienst-Wächter counts again")
        self.assertTrue(wartung.paused("llm"), "but the pause itself stays")


class Ending(Base):
    def setUp(self):
        super().setUp()
        self.sent = []

        async def send(uid, title, body, tag="", private=True, why="", to=""):
            self.sent.append((uid, title, tag))
            return 1
        self.patches = [mock.patch.object(push, "send", send), mock.patch.object(notaus, "admin_uids", lambda: ["a1", "a2"])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def test_ends_after_two_good_checks(self):
        wartung.start(["llm"], 15, "main", now=T0)

        async def good(part, cfg):
            return True
        self.assertEqual(run(wartung.tick(T0 + 60, answers=good)), "pause")
        self.assertEqual(run(wartung.tick(T0 + 15 * 60, answers=good)), "pruefen")
        self.assertTrue(wartung.paused("llm"))
        self.assertEqual(run(wartung.tick(T0 + 15 * 60 + 15, answers=good)), "aus")
        self.assertFalse(wartung.paused("llm"))
        self.assertEqual(self.sent, [])

    def test_not_answering_keeps_the_pause_and_tells_the_admins_once(self):
        wartung.start(["llm", "tts"], 15, "main", now=T0)
        answers = {"llm": False, "tts": True}

        async def check(part, cfg):
            return answers[part]
        self.assertEqual(run(wartung.tick(T0 + 15 * 60, answers=check)), "wartet")
        self.assertEqual(run(wartung.tick(T0 + 16 * 60, answers=check)), "wartet")
        self.assertTrue(wartung.paused("llm"))
        self.assertTrue(wartung.state()["overdue"])
        self.assertEqual(sorted(u for u, _, _ in self.sent), ["a1", "a2"])
        self.assertEqual({t for _, _, t in self.sent}, {"wartung"})
        answers["llm"] = True
        run(wartung.tick(T0 + 17 * 60, answers=check))
        self.assertEqual(run(wartung.tick(T0 + 17 * 60 + 15, answers=check)), "aus")


class Auto(Base):
    """Funktionen → Wartungspause → Automatisch bei Neustart: a restarting unit pauses its part by itself."""
    def setUp(self):
        super().setUp()
        helpers.set_config(wartung_auto=True)
        wartung._units.clear()
        self.units = {"qwen38-sglang": ("active", "100"), "qwen38-keepalive": ("active", "5"),
                      "speech-spark-tts-engine": ("active", "200")}
        self.patches = [mock.patch.object(wartung, "watched", lambda: {
            "llm": ["qwen38-sglang"], "asr": [], "tts": ["speech-spark-tts-engine"]})]
        for x in self.patches:
            x.start()

    def tearDown(self):
        for x in self.patches:
            x.stop()
        wartung._units.clear()
        helpers.set_config(wartung_auto=False)
        super().tearDown()

    def look(self, unit):
        return self.units.get(unit)

    def tick(self, now):
        return run(wartung.auto_tick(now, look=self.look))

    def test_first_look_only_notes(self):
        self.units["qwen38-sglang"] = ("activating", "100")
        self.assertEqual(self.tick(T0), [])
        self.assertFalse(wartung.state()["on"])

    def test_a_restart_pauses_its_part_and_it_ends_once_it_answers(self):
        self.tick(T0)
        self.units["qwen38-sglang"] = ("activating", "100")
        self.assertEqual(self.tick(T0 + 15), ["llm"])
        s = wartung.state()
        self.assertEqual((s["parts"], s["channel"], s["by"]), (["llm"], "automatisch", "automatisch"))
        self.assertEqual(s["until"] - s["since"], wartung.AUTO_MIN * 60)
        self.assertTrue(wartung.paused("llm"))
        self.assertFalse(wartung.paused("tts"))

        async def good(part, cfg):
            return True
        # still starting: no check, the pause holds
        self.assertEqual(run(wartung.tick(T0 + 30, answers=good)), "pause")
        self.units["qwen38-sglang"] = ("active", "900")   # up again, the model loads
        self.tick(T0 + 45)

        async def bad(part, cfg):
            return False
        self.assertEqual(run(wartung.tick(T0 + 60, answers=bad)), "pause")   # loading: no answer yet, nothing overdue
        self.assertFalse(wartung.state()["overdue"])
        self.assertEqual(run(wartung.tick(T0 + 75, answers=good)), "pruefen")
        self.assertEqual(run(wartung.tick(T0 + 90, answers=good)), "aus")
        self.assertFalse(wartung.state()["on"])

    def test_a_restart_between_two_looks_counts(self):
        self.tick(T0)
        self.units["speech-spark-tts-engine"] = ("active", "999")
        self.assertEqual(self.tick(T0 + 15), ["tts"])

    def test_not_for_our_watchdog_our_update_a_running_pause_or_the_switch_off(self):
        self.tick(T0)
        health._restarts["speech-spark-tts-engine"] = [T0]
        self.units["speech-spark-tts-engine"] = ("activating", "200")
        self.assertEqual(self.tick(T0 + 15), [])
        health._restarts.pop("speech-spark-tts-engine", None)
        self.units["qwen38-sglang"] = ("activating", "100")
        with mock.patch("update.update_running", lambda: True):
            self.assertEqual(self.tick(T0 + 30), [])
        wartung.start(["tts"], 30, "main", now=T0)
        self.assertEqual(self.tick(T0 + 45), [])
        self.assertEqual(wartung.state()["parts"], ["tts"])
        wartung.end("test")
        helpers.set_config(wartung_auto=False)
        self.assertEqual(self.tick(T0 + 60), [])
        self.assertFalse(wartung.state()["on"])

    def test_the_real_unit_list_leaves_out_what_is_no_model(self):
        for x in self.patches:
            x.stop()
        try:
            w = wartung.watched()
            self.assertIn("qwen38-sglang", w["llm"])
            self.assertNotIn("qwen38-keepalive", w["llm"])
            self.assertNotIn("qwen38-dashboard", w["llm"])
            self.assertIn("speech-spark-asr-engine", w["asr"])
        finally:
            for x in self.patches:
                x.start()


class Speakers(Base):
    """With the speech output paused speakers play the short sentence from its file (else a tone); with the speech
    recognition paused Home Assistant gets no text."""
    def setUp(self):
        super().setUp()
        for f in esp32.CLIP.values():
            if os.path.exists(f):
                os.remove(f)
        esp32._clip_try["t"] = 0.0

    def tearDown(self):
        for f in esp32.CLIP.values():
            if os.path.exists(f):
                os.remove(f)
        super().tearDown()

    def test_clip_file_or_tone(self):
        tone = esp32.pause_tone()
        self.assertEqual(esp32.pause_clip(), tone)
        made = []

        async def tts(uid, text):
            made.append((uid, text))
            yield b"\x01\x00" * esp32.OUT_RATE
        with mock.patch.object(esp32, "tts_stream", tts):
            self.assertTrue(run(esp32.make_pause_clips(T0)))
            self.assertFalse(run(esp32.make_pause_clips(T0 + 60)))   # fresh files are kept
        self.assertEqual(made, [("", wartung.SHORT[0]), ("", wartung.SHORT[1])])   # no profile, no profile voice
        self.assertEqual(esp32.pause_clip(), b"\x01\x00" * esp32.OUT_RATE)
        self.assertEqual(esp32.pause_clip(en=True), b"\x01\x00" * esp32.OUT_RATE)

    def test_a_failing_speech_output_is_tried_again_later_only(self):
        calls = []

        async def broken(uid, text):
            calls.append(1)
            raise RuntimeError("down")
            yield b""
        with mock.patch.object(esp32, "tts_stream", broken):
            self.assertFalse(run(esp32.make_pause_clips(T0)))
            self.assertFalse(run(esp32.make_pause_clips(T0 + 60)))
            self.assertEqual(len(calls), 1)
            run(esp32.make_pause_clips(T0 + esp32.CLIP_RETRY + 1))
            self.assertEqual(len(calls), 2)

    def test_no_new_file_while_the_speech_output_pauses(self):
        wartung.start(["tts"], 30, "main")
        with mock.patch.object(esp32, "make_pause_clips", side_effect=AssertionError("asked the paused TTS")):
            self.assertFalse(run(wartung.clips_tick()))

    def test_a_speaker_says_the_sentence_without_recognition_or_speech_output(self):
        try:
            esp32.Opus.lib()
        except OSError:
            self.skipTest("libopus missing")
        sent, sound = [], []

        class WS:
            async def send_text(self, t):
                sent.append(json.loads(t))

            async def send_bytes(self, b):
                sound.append(len(b))

        async def never(*a, **k):
            raise AssertionError("asked a paused part")
            yield b""
        wartung.start(["asr", "tts"], 30, "main")
        ses = esp32.Session(WS(), "t", {"id": "d_w", "user": "u_w", "name": "Flur"}, "c_w")
        with mock.patch.object(esp32, "transcribe", never), mock.patch.object(esp32, "tts_stream", never):
            run(ses.run_answer(b"\0" * 32000))
        texts = [m.get("text", "") for m in sent if m.get("state") == "sentence_start"]
        self.assertEqual(len(texts), 1)
        self.assertIn("aktualisiert", texts[0])
        self.assertTrue(sound, "the tone from the file (here: no file, so the tone) reached the board")

    def test_wyoming_plays_the_clip_and_hears_nothing(self):
        import wyoming
        wartung.start(["tts", "asr"], 30, "main")
        s = {"tts_port": 1, "asr_port": 1, "voice": "", "default_voice": "", "language": ""}
        rate, width, channels, pcm = run(wyoming.synthesize(s, "Das Licht ist an.", ""))
        self.assertEqual((rate, width, channels, pcm), (24000, 2, 1, esp32.pause_tone()))
        self.assertEqual(run(wyoming.transcribe(s, b"RIFF", "de")), "")


class Shell(Base):
    def test_pause_status_weiter(self):
        self.assertEqual(wartung.cli(["status"])[1], "Keine Wartungspause.")
        code, line = wartung.cli(["llm,tts", "45"], now=T0)
        self.assertEqual(code, 0, line)
        self.assertEqual(wartung.state()["parts"], ["llm", "tts"])
        self.assertEqual(wartung.state()["channel"], "kommandozeile")
        self.assertIn("noch 45 min", wartung.cli(["status"], now=T0)[1])
        self.assertEqual(wartung.cli(["weiter"], now=T0 + 600)[0], 0)
        self.assertFalse(wartung.state()["on"])
        self.assertEqual(wartung.cli(["alles"], now=T0)[0], 0)
        self.assertEqual(wartung.state()["parts"], list(wartung.PARTS))   # alles: every part, the picture service too
        for bad in (["gpu"], ["llm", "3"], ["llm", "abc"]):
            self.assertEqual(wartung.cli(bad, now=T0)[0], 2, bad)

    def test_the_script_runs_like_speech_spark_calls_it(self):
        # speech-spark.sh (as_panel_user) starts the file itself in app/panel with an empty environment: no PYTHONPATH,
        # so app/ (common.py) must come from the file's own path (tars 2026-10-14: ModuleNotFoundError 'common')
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1"}
        env.update({k: v for k, v in os.environ.items() if k.startswith("SPEECH_SPARK_")})

        def run(*args):
            return subprocess.run([sys.executable, os.path.join(helpers.APP, "panel", "wartung.py"), *args],
                                  cwd=os.path.join(helpers.APP, "panel"), env=env, capture_output=True, text=True,
                                  timeout=120)
        r = run("llm", "30")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertTrue(wartung.paused("llm"))
        r = run("status")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("Wartungspause: Sprachmodell", r.stdout)
        r = run("weiter")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertFalse(wartung.paused("llm"))

    def test_the_shell_command_runs_as_the_service_user(self):
        with open(os.path.join(helpers.APP, "speech-spark.sh")) as f:
            cli = f.read()
        self.assertIn("pause) shift; cmd_pause", cli)
        self.assertIn("weiter) shift; cmd_pause weiter", cli)
        self.assertRegex(cli, r"cmd_pause\(\) \{\n  need_root pause .*\n(.*\n)*?  as_panel_user wartung\.py")


class Shown(Base):
    def test_live_shows_the_paused_parts_without_who(self):
        wartung.start(["llm"], 30, "main")
        snap = live.snapshot("admin")
        self.assertEqual(snap["svc"]["qwen"]["st"], "pause")
        self.assertTrue(snap["wartung"]["on"])
        self.assertNotIn("by", snap["wartung"])
        wartung.end("weiter")
        self.assertFalse(live.snapshot("admin")["wartung"]["on"])

    def test_view_numbers_only(self):
        wartung.start(["llm"], 30, "main", now=time.time())
        d = wartung.view()
        self.assertEqual(set(d), {"on", "paused", "parts", "since", "until", "left", "overdue", "channel", "by", "asked",
                                  "held", "choices"})


if __name__ == "__main__":
    unittest.main()
