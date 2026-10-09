"""V01.0.214: background work starts once per process (the https server runs without lifespan), a Telegram
"Conflict" waits longer and longer with a fixed hint instead of logging every 15 s, and a passing failure of
the weather service is a warning that is tried again, not an error. No test depends on the wall clock."""
import asyncio
import contextlib
import datetime
import io
import unittest
from unittest import mock

import httpx

from tests import helpers

helpers.start()
import panel  # noqa: E402
import proactive  # noqa: E402
import telegram  # noqa: E402
import weather  # noqa: E402

TOKEN = "123456789:" + "B" * 35


class OnePoller(unittest.TestCase):
    def test_https_server_does_not_run_the_startup_handlers_again(self):
        cfg = panel.https_config({"host": "127.0.0.1", "https_port": 31443}, "c.pem", "k.pem")
        self.assertEqual(cfg.lifespan, "off")

    def test_second_loop_returns_at_once(self):
        out = io.StringIO()
        with mock.patch.dict(telegram._poller, on=True), contextlib.redirect_stdout(out):
            asyncio.run(asyncio.wait_for(telegram.loop(), 2))
        self.assertIn("a poller runs already", out.getvalue())


class Conflict(unittest.TestCase):
    def setUp(self):
        telegram.conflict.update(count=0, since=0.0)

    def tearDown(self):
        telegram.conflict.update(count=0, since=0.0)

    def test_waits_grow_and_the_log_stays_quiet(self):
        e = ValueError("Conflict: terminated by other getUpdates request; make sure that only one bot instance is running")
        self.assertTrue(telegram.is_conflict(e))
        self.assertFalse(telegram.is_conflict(ValueError("Unauthorized")))
        self.assertFalse(telegram.is_conflict(httpx.ConnectError("conflict")))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(telegram, "token", return_value=TOKEN):
            waits = [telegram.on_conflict(1000.0 + i) for i in range(40)]
        self.assertEqual(waits[:6], [5, 30, 60, 120, 300, 600])
        self.assertEqual(max(waits), 600)
        lines = [x for x in out.getvalue().splitlines() if x]
        self.assertEqual(len(lines), 3, lines)          # the 2nd, 20th and 40th, not 40 lines
        self.assertTrue(all("retry" in x and TOKEN not in x for x in lines))
        self.assertEqual(telegram.conflict["since"], 1000.0)

    def test_hint_only_while_it_lasts_and_only_with_telegram_on(self):
        with mock.patch.object(telegram, "admin_on", return_value=True), contextlib.redirect_stdout(io.StringIO()):
            telegram.on_conflict(1.0)
            self.assertEqual(telegram.alert(), [])       # one right after a restart is normal
            telegram.on_conflict(2.0)
            a = telegram.alert()
            self.assertEqual(len(a), 1)
            self.assertIn("BotFather", a[0]["text"])
            self.assertNotIn(TOKEN, a[0]["text"])
            with mock.patch.object(telegram, "admin_on", return_value=False):
                self.assertEqual(telegram.alert(), [])
            telegram.conflict_over()
            self.assertEqual(telegram.alert(), [])

    def test_log_page_hint_names_the_token(self):
        import logfilter
        row = logfilter.parse("2026-10-09T17:41:00+0200 tars python[1]: telegram: ValueError Conflict: terminated "
                              "by other getUpdates request; make sure that only one bot instance is running")
        hint = next(de for a, rx, de, en in logfilter._HINTS if (a is None or a == row["area"]) and rx.search(row["msg"]))
        self.assertIn("denselben Bot-Token", hint)


class OwnRequests(unittest.TestCase):
    def test_log_page_polls_are_no_errors(self):
        """V01.0.215: "?f=errors" in the address made the log page's own requests count as errors."""
        import logfilter
        pre = "2026-10-09T18:35:30+0200 tars python[1]: INFO:     192.168.178.218:46578 - "
        ok = logfilter.parse(pre + '"GET /api/logfilter?format=json&f=errors&minutes=60&lines=100 HTTP/1.1" 200 OK')
        self.assertEqual(ok["level"], "")
        bad = logfilter.parse(pre + '"GET /api/status HTTP/1.1" 500 Internal Server Error')
        self.assertEqual(bad["level"], "err")
        self.assertEqual(logfilter.parse(pre.split("INFO")[0] + "chat: tts failed")["level"], "err")

    def test_log_page_polls_stay_out_of_the_journal(self):
        import logging
        import common
        common.quiet_access_log()
        rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "GET %s HTTP/1.1" %d',
                                ("1.2.3.4:5", "/api/logfilter?f=errors", 200), None)
        self.assertFalse(all(f.filter(rec) for f in logging.getLogger("uvicorn.access").filters))


class PassingWeather(unittest.TestCase):
    def _err(self, code):
        req = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
        return httpx.HTTPStatusError("x", request=req, response=httpx.Response(code, request=req))

    def test_passing_or_not(self):
        self.assertIn("503", weather.passing(self._err(503)))
        self.assertIn("429", weather.passing(self._err(429)))
        self.assertEqual(weather.passing(self._err(400)), "")
        self.assertTrue(weather.passing(httpx.ReadTimeout("slow")))
        self.assertTrue(weather.passing(httpx.ConnectError("down")))
        self.assertEqual(weather.passing(ValueError("x")), "")

    def test_503_is_tried_again_and_logged_as_warning(self):
        import logfilter
        uid = "wx-retry"
        store = {}
        p = {"pro_weather_at": "07:00"}
        now = datetime.datetime(2026, 1, 5, 7, 30)
        calls = []

        async def busy(u):
            calls.append(u)
            raise self._err(503)

        def mut(u, fn):
            return fn(store)
        out = io.StringIO()
        with mock.patch.object(proactive, "state", side_effect=lambda u: dict(store)), \
                mock.patch.object(proactive, "_mut", side_effect=mut), \
                mock.patch.object(proactive, "blocked", return_value=""), \
                mock.patch.object(weather, "usable", return_value=True), \
                mock.patch.object(weather, "notable_tomorrow", side_effect=busy), contextlib.redirect_stdout(out):
            asyncio.run(proactive.check_weather(uid, p, now))
            self.assertEqual(store["weather_day"], "")      # not done for today
            self.assertGreater(store["weather_wait"], 0)
            asyncio.run(proactive.check_weather(uid, p, now))
            self.assertEqual(len(calls), 1)                 # waits before the next try
            store["weather_wait"] = 0
            with mock.patch.object(weather, "notable_tomorrow", return_value=("", [])):
                asyncio.run(proactive.check_weather(uid, p, now))
            self.assertEqual(store["weather_day"], "2026-01-05")
        line = out.getvalue().strip().splitlines()[0]
        self.assertIn("retry", line)
        self.assertEqual(logfilter.parse(line)["level"], "warn")

    def test_other_failures_still_raise(self):
        store = {}

        async def bad(u):
            raise self._err(400)
        with mock.patch.object(proactive, "state", side_effect=lambda u: dict(store)), \
                mock.patch.object(proactive, "_mut", side_effect=lambda u, fn: fn(store)), \
                mock.patch.object(proactive, "blocked", return_value=""), \
                mock.patch.object(weather, "usable", return_value=True), \
                mock.patch.object(weather, "notable_tomorrow", side_effect=bad):
            with self.assertRaises(httpx.HTTPStatusError):
                asyncio.run(proactive.check_weather("wx-bad", {"pro_weather_at": "07:00"},
                                                    datetime.datetime(2026, 1, 5, 7, 30)))


if __name__ == "__main__":
    unittest.main()
