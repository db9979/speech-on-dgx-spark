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


class OverviewTest(unittest.TestCase):
    """V01.0.212: the page gets rows with time, area and level, counts per area, a small history and the
    newest error with a fixed hint; extra detail per area is admin only, off by default and ends by itself."""

    def test_json_rows_counts_and_hint(self):
        r, _ = get(ADMIN, f="room,esp32", format="json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual({x["area"] for x in d["rows"]}, {"room", "esp32"})
        self.assertEqual(d["counts"]["chat"], 1)         # counts cover every line, not only the filter
        self.assertEqual(d["counts"]["search"], 1)       # web search is its own area
        self.assertGreaterEqual(d["counts"]["errors"], 2)
        self.assertEqual(d["last_error"]["area"], "mail")   # the newest line with an error word
        self.assertNotIn("abcdefghijklmnop", r.text)
        r, _ = get(ADMIN, f="errors", format="json")
        self.assertTrue(all(x["level"] == "err" for x in r.json()["rows"]))
        self.assertEqual(get(ADMIN, format="xml")[0].status_code, 400)

    def test_levels_and_hints_are_fixed_rules(self):
        row = logfilter.parse("2026-01-01T10:00:00+0000 tars python[1]: homeassistant: lookup failed: HTTPStatusError 401")
        self.assertEqual((row["t"], row["area"], row["level"]), ("10:00:00", "ha", "err"))
        self.assertEqual(logfilter.parse("2026-01-01T10:00:00+0000 tars p[1]: room: ignored (tv voice)")["level"], "warn")
        self.assertEqual(logfilter.parse("2026-01-01T10:00:00+0000 tars p[1]: weiche: homeassistant")["area"], "weiche")
        # a speaker in a room that kept personal things from an unknown voice: Lautsprecher, yellow
        w = logfilter.parse("2026-01-01T10:00:00+0000 tars p[1]: esp32: personal data withheld at Wohnzimmer - "
                            "voice not recognized - guest rights for this question")
        self.assertEqual((w["area"], w["level"]), ("esp32", "warn"))
        now = logfilter._when("2026-01-01T10:30:00+0000")
        s = logfilter.summary([row], 60, now)
        self.assertIn("Token", s["last_error"]["hint"]["de"])
        self.assertEqual(sum(s["spark"]["ha"]), 1)
        self.assertEqual(len(s["spark"]["ha"]), logfilter.BUCKETS)

    def test_detail_switch(self):
        guard._rate.clear()
        logfilter._verbose.clear()
        anon = TestClient(panel.app)
        self.assertEqual(anon.get("/api/logverbose").status_code, 401)
        self.assertEqual(anon.post("/api/logverbose", json={"area": "room", "minutes": 15}).status_code, 401)
        self.assertEqual(ADMIN.get("/api/logverbose").json()["areas"], {"room": 0, "esp32": 0, "ha": 0, "chat": 0})
        for bad in ({"area": "shell", "minutes": 15}, {"area": "room", "minutes": 7}, {"area": "room", "minutes": True},
                    {"area": "room", "minutes": "15"}, ["room"]):
            self.assertEqual(ADMIN.post("/api/logverbose", json=bad).status_code, 400, bad)
        with mock.patch.object(logfilter.time, "time", return_value=1000.0):
            self.assertEqual(ADMIN.post("/api/logverbose", json={"area": "room", "minutes": 15}).json()["areas"]["room"], 900)
        with mock.patch("builtins.print") as out, mock.patch.object(logfilter.time, "time", return_value=1500.0):
            logfilter.detail("room", "heard 4 words token=geheim")
            logfilter.detail("esp32", "not on")
        lines = [" ".join(map(str, c.args)) for c in out.call_args_list]
        self.assertEqual(lines, ["room: detail heard 4 words token=***"])
        with mock.patch("builtins.print"), mock.patch.object(logfilter.time, "time", return_value=1000.0 + 901):
            self.assertFalse(logfilter.verbose("room"))   # ended by itself
        self.assertEqual(ADMIN.get("/api/logverbose").json()["areas"]["room"], 0)
        logfilter._verbose.clear()

    def test_room_detail_never_has_the_heard_text(self):
        import asyncio
        import room
        logfilter._verbose.clear()
        with mock.patch.object(logfilter.time, "time", return_value=1000.0):
            logfilter._verbose["room"] = 5000.0
            with mock.patch("builtins.print") as out:
                try:
                    asyncio.run(room.heard("u1", "r1", "Mein geheimes Passwort ist Pferd", {}))
                except Exception:
                    pass   # only the detail line matters here
        logfilter._verbose.clear()
        text = " ".join(" ".join(map(str, c.args)) for c in out.call_args_list)
        self.assertIn("room: detail heard 5 words", text)
        self.assertNotIn("Pferd", text)
        self.assertNotIn("Passwort", text)


if __name__ == "__main__":
    unittest.main()
