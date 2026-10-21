"""Update lock from the click on (Dominik 2026-10-20 "sollte direkt nach installieren gesperrt sein"): update.begin
holds the lock and writes the first step before the backup, every start path goes through it, a unit that does not
start releases the lock with its reason, and update.sh ends every way with done + ok and a reason."""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from fastapi import HTTPException

from tests import helpers

helpers.start()
import steuer  # noqa: E402
import update  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
T0 = 2_000_000_000.0


def _src(name):
    with open(os.path.join(PANEL, name), encoding="utf-8") as f:
        return f.read()


class Pending(unittest.TestCase):
    def tearDown(self):
        update._pending.update(since=0.0, unit=0.0)

    def test_holds_while_the_backup_runs_and_lets_go_by_itself(self):
        update._pending.update(since=T0, unit=0.0)
        self.assertTrue(update._pending_holds(False, T0 + 60), "backup still running")
        self.assertFalse(update._pending_holds(False, T0 + update.PENDING_MAX), "a backup that never ends")
        self.assertEqual(update._pending["since"], 0.0)
        update._pending.update(since=T0, unit=T0 + 30)
        self.assertTrue(update._pending_holds(False, T0 + 30 + update.UNIT_GRACE - 1), "systemd does not show it yet")
        self.assertFalse(update._pending_holds(False, T0 + 30 + update.UNIT_GRACE), "unit ended at once")
        update._pending.update(since=T0, unit=T0 + 30)
        self.assertFalse(update._pending_holds(True, T0 + 31), "the unit's own state holds the lock now")
        self.assertEqual(update._pending["since"], 0.0)
        self.assertFalse(update._pending_holds(False, T0))


class Begin(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.file = os.path.join(self.dir, "update-progress.json")
        self.p = [mock.patch.object(update, "UPDATE_PROGRESS", self.file),
                  mock.patch.object(update, "update_running", side_effect=lambda: update._pending_holds(False))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        update._pending.update(since=0.0, unit=0.0)

    def read(self):
        with open(self.file) as f:
            return json.load(f)

    def test_locked_and_said_before_the_backup_then_the_unit(self):
        seen = []

        def backup(why):
            seen.append((why, update.update_running(), self.read()["text"], self.read()["done"]))
        with mock.patch.object(update, "_backup_first", side_effect=backup), \
                mock.patch.object(update, "_start", return_value={"started": True}) as start:
            self.assertEqual(update.begin("before-update", "V01.0.999"), {"started": True})
        self.assertEqual(seen, [("before-update", True, "Sicherung vor dem Update", False)])
        start.assert_called_once()
        p = self.read()
        self.assertEqual((p["text"], p["version"], p["done"]), ("Update startet", "V01.0.999", False))
        self.assertTrue(update.update_running(), "held until systemd shows the unit")
        self.assertEqual(update.update_progress()["percent"], 2)
        # a second start meanwhile: refused, nothing started twice
        with mock.patch.object(update, "_backup_first"), mock.patch.object(update, "_start") as again:
            with self.assertRaises(HTTPException) as e:
                update.begin()
            self.assertEqual(e.exception.status_code, 409)
            again.assert_not_called()

    def test_a_unit_that_does_not_start_releases_the_lock_and_says_why(self):
        with mock.patch.object(update, "_backup_first"), \
                mock.patch.object(update, "_start", side_effect=HTTPException(500, "no sudo")):
            with self.assertRaises(HTTPException):
                update.begin()
        self.assertFalse(update.update_running())
        p = self.read()
        self.assertTrue(p["done"])
        self.assertIs(p["ok"], False)
        self.assertIn("nicht starten", p["text"])

    def test_every_start_goes_through_begin(self):
        for name in ("update.py", "appupdate.py"):
            src = _src(name)
            calls = re.findall(r"(?<!def )(?<![\w.])(?:update\.)?_start\(\)", src)
            self.assertEqual(len(calls), 1 if name == "update.py" else 0, name)   # only begin() calls the unit
            self.assertNotRegex(src, r"_backup_first\(\s*\"before-", name)
        for way in ('return begin("before-update"', 'return begin("before-rollback"', 'to_thread(begin, "before-update"'):
            self.assertIn(way, _src("update.py"))   # button, rollback, overnight
        self.assertIn("update.begin", _src("appupdate.py"))

    def test_the_page_shows_why_it_did_not_start(self):
        js = _src(os.path.join("static", "js", "admin.js"))
        self.assertIn("ulFail(t('Update konnte nicht starten'", js)


class Bar(unittest.TestCase):
    def test_before_the_model_computer_the_bar_stays_at_zero(self):
        p = {"percent": 1, "text": "Sicherung vor dem Update", "started": 100, "updated": 100, "done": False, "ok": None}
        with mock.patch.object(update, "update_running", return_value=True), \
                mock.patch.object(update, "update_progress", return_value=p), \
                mock.patch.object(steuer, "remote", return_value=True), \
                mock.patch.object(steuer, "cached", return_value={"update": False}):
            g = update.gesamt(T0)
        self.assertEqual((g["teil"], g["pct"], g["step"]), ("", 0, "Sicherung vor dem Update"))


class Script(unittest.TestCase):
    def setUp(self):
        self.sh = helpers.repo_file("update.sh")   # skipped in a copy with only app/ (the Spark's own self-test)

    def test_every_end_says_done_with_a_reason(self):
        sh = self.sh
        self.assertIn("trap on_exit EXIT", sh)
        first = sh.index('step "Lädt und prüft die neue Version"')
        self.assertLess(sh.index("trap on_exit EXIT"), first)
        rest = sh[first:]
        # after the first step no bare "exit 1": stop_early writes the reason (the failed install keeps its own finish)
        self.assertEqual(re.findall(r"^\s*exit 1\s*$", rest, re.M), [])
        self.assertIn('git fetch --quiet origin "$BRANCH" || {', rest)
        for done in re.finditer(r"Already up to date[^\n]*\n\s*(\S+)", rest):
            self.assertEqual(done.group(1), "finish", "up to date ends as done")

    def test_steps_keep_the_start_time_and_name_the_model_computer(self):
        self.assertIn("if .done == false then .started else empty end", self.sh)
        self.assertLess(self.sh.index('step "Modell-Rechner wird zuerst aktualisiert"'), self.sh.index("teilen modelle-update"))
        self.assertNotIn("started: $now", self.sh, "never a new start time in the middle of an update")


class Begleiter(unittest.TestCase):
    def test_the_desk_program_shows_the_same_update(self):
        import begleiter
        g = {"run": True, "teil": "", "pct": 140, "step": "Sicherung vor dem Update" + "x" * 50, "done": False, "ok": None}
        with mock.patch.object(update, "gesamt", return_value=g):
            self.assertEqual(begleiter.spark_update(), {"pct": 100, "step": ("Sicherung vor dem Update" + "x" * 50)[:40]})
        for idle in (None, dict(g, run=False, done=True, ok=True)):
            with mock.patch.object(update, "gesamt", return_value=idle):
                self.assertIsNone(begleiter.spark_update())
        self.assertIn('"spark_update": spark_update()', _src("begleiter.py"))

    def test_both_programs_read_it(self):
        for client in (("windows", "SparkClient.cs"), ("mac", "Sources", "Model.swift")):
            code = helpers.repo_file("tools", "begleiter", *client)   # skipped in a copy with only app/
            self.assertIn('"spark_update"', code, client)
            self.assertIn("Spark-Update läuft", code, client)


if __name__ == "__main__":
    unittest.main()
