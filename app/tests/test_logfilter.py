"""Diagnose filters on Übersicht → Logs (V01.0.141): admin only, fixed filter list matched in Python,
only numbers from fixed lists reach journalctl, capped lines, secrets blacked out, rate limited.
journalctl is mocked; nothing depends on the clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import logfilter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})

JOURNAL = "\n".join([
    "2026-01-01T10:00:00+0000 tars python[1]: chat: web search 2 results",
    "2026-01-01T10:00:01+0000 tars python[1]: chat: tools offered",
    "2026-01-01T10:00:02+0000 tars python[1]: room: on at speaker Wohnzimmer for 30 min",
    "2026-01-01T10:00:03+0000 tars python[1]: esp32: wake word at Wohnzimmer",
    "2026-01-01T10:00:04+0000 tars python[1]: homeassistant: switched light.kueche",
    "2026-01-01T10:00:05+0000 tars python[1]: telegram: error https://api.telegram.org/bot123456789:"
    "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ/getUpdates",
    "2026-01-01T10:00:06+0000 tars python[1]: mail: login failed password=hunter2 for https://bob:geheim@x.example/",
    "2026-01-01T10:00:07+0000 tars python[1]: esp32: answer Authorization: Bearer abcdefghijklmnop token: xyz123",
]) + "\n"


class FakeRun:
    def __init__(self, out=JOURNAL):
        self.out, self.cmds = out, []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        return mock.Mock(stdout=self.out, returncode=0)


def get(client, **params):
    guard._rate.clear()
    fake = FakeRun()
    with mock.patch.object(logfilter.subprocess, "run", fake):
        r = client.get("/api/logfilter", params=params)
    return r, fake


class LogFilterTest(unittest.TestCase):
    def test_needs_admin_login(self):
        r, fake = get(TestClient(panel.app), f="room")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(fake.cmds, [])

    def test_filters_match_like_grep(self):
        r, _ = get(ADMIN, f="room,esp32", minutes=10, lines=30)
        self.assertEqual(r.status_code, 200)
        body = r.text.splitlines()
        self.assertTrue(body[0].startswith("# Filter: room, esp32 · letzte 10 min · 3 von 3"))
        self.assertTrue(all("room:" in x or "esp32:" in x for x in body[1:]), body)
        r, _ = get(ADMIN, f="search")
        self.assertEqual(len(r.text.splitlines()), 2)
        self.assertIn("chat: web search", r.text)

    def test_line_cap_keeps_the_newest(self):
        r, _ = get(ADMIN, f="", lines=30)
        self.assertEqual(len(r.text.splitlines()), 9)  # header + all 8
        lines = [logfilter.pick(JOURNAL * 10, [], 30)][0]
        self.assertEqual(len(lines[0]), 30)
        self.assertEqual(lines[1], 80)

    def test_only_fixed_values_reach_journalctl(self):
        for bad in ({"f": "room;id"}, {"f": "$(id)"}, {"f": "room", "minutes": 7}, {"f": "room", "lines": 5000},
                    {"f": "room", "minutes": "-1 day"}):
            r, fake = get(ADMIN, **bad)
            self.assertIn(r.status_code, (400, 422), bad)
            self.assertEqual(fake.cmds, [], bad)
        r, fake = get(ADMIN, f="update,errors", minutes=120, lines=100)
        self.assertEqual(r.status_code, 200)
        cmd = fake.cmds[0]
        self.assertIsInstance(cmd, list)       # never a shell string
        self.assertIn("--since=-120min", cmd)
        self.assertEqual(cmd[cmd.index("-u") + 1], "speech-spark-update")

    def test_secrets_are_blacked_out(self):
        r, _ = get(ADMIN)
        for secret in ("AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ", "hunter2", "geheim", "abcdefghijklmnop", "xyz123"):
            self.assertNotIn(secret, r.text)
        self.assertIn("password=***", r.text)

    def test_rate_limited(self):
        guard._rate.clear()
        with mock.patch.object(logfilter.subprocess, "run", FakeRun()):
            codes = [ADMIN.get("/api/logfilter", params={"f": "room"}).status_code for _ in range(62)]
        self.assertIn(429, codes)
        guard._rate.clear()


if __name__ == "__main__":
    unittest.main()
