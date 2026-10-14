"""One profile's things never reach another profile (Prüfung pruefung/kontext-trennung-2026-10-14.md): a voice recognized
at someone else's browser (it could be a recording of that person) and Telegram without tg_private get no personal
data, the daily briefing's reminders and the Spark diary included. Fixed rule, no switch.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import contextlib
import io
import json
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import profiles  # noqa: E402
import speakers  # noqa: E402
import tagebuch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def tool_results(text, **body):
    """What the tools gave the model in this turn (the fake LLM calls the tool named in the question)."""
    def run(client):
        helpers.LLM_CALLS.clear()
        r = client.post("/api/chat", json=dict({"messages": [{"role": "user", "content": text}]}, **body))
        assert r.status_code == 200, r.text
        helpers.events(r)
        return json.dumps(helpers.LLM_CALLS, ensure_ascii=False)
    return run


class RecognizedVoiceElsewhere(unittest.TestCase):
    def setUp(self):
        helpers.set_config(speaker_id=True, reminders=True, calendar=True)
        self.addCleanup(helpers.set_config, speaker_id=False)

    def test_briefing_reads_no_reminders_of_the_voice_at_another_browser(self):
        x, _ = profile("Xaver")
        y, yid = profile("Yvonne")
        xid = x.get("/api/whoami").json()["profile"]["id"]
        profiles.add_reminder(yid, "Geheimtermin Zahnarzt", int(time.time() * 1000) + 3600_000)
        self.addCleanup(lambda: profiles.remove_reminders(yid, [r["id"] for r in profiles.reminders(yid)]))
        # her own browser: she hears her reminder
        self.assertIn("Geheimtermin Zahnarzt", tool_results("TOOL daily_briefing {}")(y))
        # her voice (or a recording of it) at his browser: no reminder of hers
        seen = tool_results("TOOL daily_briefing {}", speaker=speakers.token(yid, xid))(x)
        self.assertNotIn("Geheimtermin Zahnarzt", seen)

    def test_diary_only_for_the_own_login(self):
        _, uid = profile("Tagebuchfrau")
        helpers.set_config(tagebuch=True)
        self.addCleanup(helpers.set_config, tagebuch=False)
        ask = "Was hast du heute für mich gemacht?"
        self.assertIsNotNone(tagebuch.offer({"who": {"id": uid}, "own": True, "private": True, "text": ask}))
        self.assertIsNone(tagebuch.offer({"who": {"id": uid}, "own": False, "private": False, "text": ask}))
        self.assertIsNone(tagebuch.offer({"who": {"id": uid}, "own": True, "private": False, "text": ask}))   # Telegram


class JournalHoldsNoWords(unittest.TestCase):
    def test_home_command_the_panel_runs_is_logged_without_its_words(self):
        a, _ = profile("Hausfrau")
        helpers.set_config(homeassistant=True)
        a.put("/api/profile/homeassistant", json={"url": f"http://127.0.0.1:{helpers.HA_PORT}", "token": helpers.HA_TOKEN})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            evs = helpers.events(a.post("/api/chat", json={"messages": [
                {"role": "user", "content": "Mach das Licht in der Speisekammer an"}]}))
        self.assertTrue(any(e["type"] == "home_done" for e in evs), evs)
        self.assertIn("homeassistant: panel ran a command of 7 words", out.getvalue())
        self.assertNotIn("Speisekammer", out.getvalue())


class VerwalterSeesOnlyOwnReports(unittest.TestCase):
    """Probleme melden (meldung.py): only the admin roles count as staff (all drafts, send or delete another's); the
    Verwalter role reports like any profile (Prüfung 2026-10-14, B)."""

    def test_manager_is_no_staff(self):
        import coadmin
        import meldung
        from starlette.requests import Request
        req = Request({"type": "http", "method": "GET", "path": "/api/report", "headers": [], "query_string": b""})
        for role, staff in (("manager", False), ("admin", True)):
            with mock.patch.object(coadmin, "session", lambda r, role=role: {"name": "Vera", "id": "u_" + "a" * 12, "role": role}):
                self.assertEqual(meldung._staff(req) is not None, staff, role)


if __name__ == "__main__":
    unittest.main()
