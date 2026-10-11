"""Gentler updates and quieter logs (log review on tars, 2026-10-11): "Heute Nacht einspielen" (off by default,
once a night, never while somebody talks, never during the Notaus), the update button knows whether somebody is
talking, the Live page shows the update, and refusals that repeat (no Android release yet, tasks switched off,
the update lock, a reverse proxy that is not entered) say how long to wait or are logged once."""
import asyncio
import json
import os
import time
import unittest

from tests import helpers

helpers.start()
import admin  # noqa: E402
import android  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import update  # noqa: E402
import vorrang  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NIGHT = time.mktime((2026, 10, 11, 3, 30, 0, 0, 0, -1))   # 03:30 local time, wherever the test runs
DAY = time.mktime((2026, 10, 11, 14, 0, 0, 0, 0, -1))


def set_panel(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        cfg = json.load(f)
    cfg["panel"].update(kw)
    with open(os.environ["SPEECH_SPARK_CONFIG"], "w") as f:
        json.dump(cfg, f)


class Night(unittest.TestCase):
    def setUp(self):
        self.real = (update.remote_state, update.update_running, update._start, update._backup_first, vorrang.last_speech,
                     notaus.blocks)
        self.started, self.asked, self.last = [], [], 0.0
        self.remote = {"latest": "b" * 40, "behind": 3, "version": "V01.0.999"}

        async def remote(force=False):
            self.asked.append(force)
            return self.remote
        update.remote_state = remote
        update.update_running = lambda: False
        update._start = lambda: self.started.append(1) or {"started": True}
        update._backup_first = lambda why: None
        vorrang.last_speech = lambda: self.last
        notaus.blocks = lambda kind, uid=None: False
        update._night["asked"] = 0.0
        if os.path.exists(update.NIGHT_FILE):
            os.remove(update.NIGHT_FILE)
        set_panel(update_night=True)

    def tearDown(self):
        (update.remote_state, update.update_running, update._start, update._backup_first, vorrang.last_speech,
         notaus.blocks) = self.real
        set_panel(update_night=False)

    def run_at(self, t):
        return asyncio.run(update.night_once(now=t))

    def test_off_by_default(self):
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["panel"]["update_night"], False)
        set_panel(update_night=False)
        self.assertEqual(self.run_at(NIGHT), "")
        self.assertEqual(self.started, [])

    def test_only_at_night_and_once(self):
        self.assertEqual(self.run_at(DAY), "")
        self.assertEqual(self.run_at(NIGHT), "started")
        self.assertEqual(self.started, [1])
        self.assertEqual(self.asked, [True])          # asks GitHub fresh, only versions that passed the tests
        self.assertEqual(self.run_at(NIGHT + 600), "")  # the same night: not again
        self.assertEqual(self.started, [1])

    def test_waits_while_somebody_talks(self):
        self.last = NIGHT - 30
        self.assertEqual(self.run_at(NIGHT), "talking")
        self.last = NIGHT - 3600
        self.assertEqual(self.run_at(NIGHT + 60), "started")

    def test_nothing_newer_ends_the_night(self):
        self.remote = {"latest": "a" * 40, "behind": 0}
        self.assertEqual(self.run_at(NIGHT), "current")
        self.remote = {"latest": "b" * 40, "behind": 1}
        self.assertEqual(self.run_at(NIGHT + 600), "")
        self.assertEqual(self.started, [])

    def test_github_down_asks_again_later_in_the_night(self):
        self.remote = {"error": "GitHub nicht erreichbar"}
        self.assertEqual(self.run_at(NIGHT), "retry")
        self.assertEqual(self.run_at(NIGHT + 60), "retry")
        self.assertEqual(len(self.asked), 1)
        self.remote = {"latest": "b" * 40, "behind": 1}
        self.assertEqual(self.run_at(NIGHT + update.NIGHT_RETRY + 1), "started")

    def test_notaus_and_a_running_update_stop_it(self):
        notaus.blocks = lambda kind, uid=None: kind == "auto"
        self.assertEqual(self.run_at(NIGHT), "")
        notaus.blocks = lambda kind, uid=None: False
        update.update_running = lambda: True
        self.assertEqual(self.run_at(NIGHT), "running")
        self.assertEqual(self.started, [])

    def test_switch_is_validated_and_needs_the_second_step(self):
        cfg = ADMIN.get("/api/config").json()
        cfg["panel"]["update_night"] = "yes"
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400)
        self.assertIn(("panel", "update_night"), admin.SENSITIVE)


class Talking(unittest.TestCase):
    def setUp(self):
        self.real = vorrang.last_speech

    def tearDown(self):
        vorrang.last_speech = self.real

    def test_update_button_knows_about_a_conversation(self):
        vorrang.last_speech = lambda: 1000.0
        self.assertEqual(update.talking(now=1030.0), {"now": True, "ago": 30})
        self.assertEqual(update.talking(now=1000.0 + update.BUSY_S + 1)["now"], False)
        vorrang.last_speech = lambda: 0.0
        self.assertEqual(update.talking(now=1030.0), {"now": False, "ago": None})
        self.assertIn("talking", ADMIN.get("/api/update").json())


class LiveShowsTheUpdate(unittest.TestCase):
    def setUp(self):
        self.real = (update.update_progress, update.update_running)

    def tearDown(self):
        update.update_progress, update.update_running = self.real

    def test_running_update_with_step_and_share(self):
        update.update_running = lambda: True
        update.update_progress = lambda: {"percent": 76, "text": "Selbsttest", "started": 100, "updated": 150,
                                          "done": False, "ok": None, "version": "V01.0.999"}
        u = live._upd(160)
        self.assertEqual((u["run"], u["pct"], u["step"], u["ver"], u["secs"]), (True, 76, "Selbsttest", "V01.0.999", 60))
        self.assertIn("upd", live.snapshot(now=160))

    def test_outcome_for_an_hour_then_gone(self):
        update.update_running = lambda: False
        update.update_progress = lambda: {"percent": 100, "text": "Fertig", "started": 100, "updated": 200,
                                          "done": True, "ok": True, "version": "V01.0.999"}
        self.assertIs(live._upd(300)["ok"], True)
        self.assertNotIn("ok", live._upd(200 + 3601))


class QuieterLogs(unittest.TestCase):
    def test_no_android_release_yet_is_a_state(self):
        real = android.fetch_apk

        async def none(c=None):
            raise android.NoRelease("Im Repo gibt es noch keine Android-App")

        async def broken(c=None):
            raise ValueError("android.json ist ungültig.")
        try:
            android.fetch_apk = none
            r = ADMIN.post("/api/admin/android/fetch")
            self.assertEqual(r.status_code, 200)
            self.assertIn("noch keine", r.json()["error"])
            android.fetch_apk = broken
            self.assertEqual(ADMIN.post("/api/admin/android/fetch").status_code, 502)
        finally:
            android.fetch_apk = real

    def test_tasks_switched_off_say_when_to_ask_again(self):
        r = ADMIN.post("/api/admin/profiles", json={"name": "Retry", "pin": "1234"})
        self.assertIn(r.status_code, (200, 409))
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/profile/login", json={"name": "Retry", "pin": "1234"}).status_code, 200)
        r = c.post("/api/tasks/inbox?list=einkauf&format=json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.headers.get("retry-after"), "3600")

    def test_update_lock_says_when_to_ask_again(self):
        real = update.update_running
        update.update_running = lambda: True
        try:
            r = ADMIN.post("/api/admin/profiles", json={"name": "Locked", "pin": "1234"})
            self.assertEqual(r.status_code, 423)
            self.assertEqual(r.headers.get("retry-after"), "60")
        finally:
            update.update_running = real

    def test_proxy_hint_once_a_day_also_after_a_restart(self):
        guard._hinted.clear()
        if os.path.exists(guard.HINTED):
            os.remove(guard.HINTED)
        self.assertTrue(guard._first_hint("192.168.178.5", now=DAY))
        self.assertFalse(guard._first_hint("192.168.178.5", now=DAY + 60))
        guard._hinted.clear()                                    # the panel restarted (an update)
        self.assertFalse(guard._first_hint("192.168.178.5", now=DAY + 120))
        self.assertTrue(guard._first_hint("192.168.178.9", now=DAY + 180))
        guard._hinted.clear()
        self.assertTrue(guard._first_hint("192.168.178.5", now=DAY + 86400))   # the next day once more
        guard._hinted.clear()


class InstallScript(unittest.TestCase):
    """install.sh / update.sh (only in the full repository; the self-test on the Spark has app/ alone)."""

    def files(self):
        root = os.path.dirname(helpers.APP)
        out = []
        for name in ("install.sh", "update.sh"):
            path = os.path.join(root, name)
            if not os.path.exists(path):
                raise unittest.SkipTest(f"{name} is not part of this copy")
            out.append(open(path).read())
        return out

    def test_update_does_only_what_changed(self):
        ins, upd = self.files()
        self.assertIn('if [ "$FROM_UPDATE" = 1 ] && dpkg -s $PKGS', ins)                 # apt only when a package is missing
        self.assertIn("same_pkgs", ins)                                                   # pip only when the list changed
        self.assertIn('"$(cat "$PREFIX/venv-panel/.locked" 2>/dev/null)" = "$lock_sum"', ins)
        self.assertIn('"$(cat "$PREFIX/.models")" = "$MODELS_SIG"', ins)                 # downloads only for new models
        self.assertIn("restart_front asr", ins)
        self.assertIn("restart_front tts", ins)
        self.assertNotIn("systemctl restart speech-spark-asr.service", ins)
        self.assertNotIn("systemctl restart speech-spark-tts.service", ins)
        self.assertIn('restart_engine tts-design', ins)
        self.assertIn('engine.sh=$(sha256sum "$PREFIX/app/engine.sh"', ins)   # new start options reach the engines
        self.assertIn("restart-map", ins)

    def test_self_test_is_gentle_and_short_only_for_a_tested_version(self):
        ins, upd = self.files()
        self.assertIn("nice -n 19 ionice -c 2 -n 7 timeout 900", ins)
        self.assertIn('[ "${SPEECH_SPARK_TESTED:-0}" = 1 ]', ins)
        self.assertIn("tests.test_rauchtest", ins)
        # update.sh says "tested" only for exactly the commit GitHub's test run passed, never for --newest or --to
        self.assertIn("TESTED=0", upd)
        self.assertEqual(upd.count("TESTED=1"), 1)
        self.assertLess(upd.index("new=$green"), upd.index("TESTED=1"))
        self.assertIn("SPEECH_SPARK_TESTED=$TESTED ./install.sh", upd)


if __name__ == "__main__":
    unittest.main()
