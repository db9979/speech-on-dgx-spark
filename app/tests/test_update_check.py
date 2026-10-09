"""Update check (update.py): GitHub's hourly limit for unauthenticated questions is recognised, the
next question waits until it is lifted, and a refusal is not repeated on every page view."""
import asyncio
import unittest

from tests import helpers

helpers.start()
import update  # noqa: E402

NOW = 2_000_000_000


class RateLimit(unittest.TestCase):
    def test_limit_recognised(self):
        until = update.rate_limit_until
        self.assertEqual(until(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(NOW + 900)}, NOW), NOW + 900)
        self.assertEqual(until(429, {"retry-after": "30"}, NOW), NOW + 30)
        # never longer than an hour, never in the past
        self.assertEqual(until(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(NOW + 99999)}, NOW), NOW + 3600)
        self.assertEqual(until(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1"}, NOW), NOW + 60)
        self.assertEqual(until(429, {"retry-after": "nonsense"}, NOW), NOW + 60)
        # a 403 that is not the limit (no rights), and other codes, are no limit
        self.assertIsNone(until(403, {"x-ratelimit-remaining": "12"}, NOW))
        self.assertIsNone(until(404, {}, NOW))
        self.assertIsNone(until(500, {"retry-after": "5"}, NOW))


class Check(unittest.TestCase):
    def setUp(self):
        self.real = (update.installed_version, update.run, update.green_runs, update.time.time)
        self.asked = 0
        self.clock = [float(NOW)]
        update.installed_version = lambda: {"remote": "https://github.com/x/y.git", "branch": "main", "commit": "e" * 40}
        update.run = lambda *a, **k: (0, "a" * 40 + "\trefs/heads/main\n")
        update.time.time = lambda: self.clock[0]
        update._remote_cache.update(time=0, data=None)
        update._failed.update(until=0.0, data=None, limited=False)

    def tearDown(self):
        update.installed_version, update.run, update.green_runs, update.time.time = self.real
        update._remote_cache.update(time=0, data=None)
        update._failed.update(until=0.0, data=None, limited=False)

    def refuse(self, status, until):
        async def runs(repo, branch):
            self.asked += 1
            raise update.GitHubRefused(status, until)
        update.green_runs = runs

    def test_limit_waits_even_for_check_now(self):
        self.refuse(403, NOW + 1200)
        d = asyncio.run(update.remote_state(force=True))
        self.assertIn("60 pro Stunde", d["error"])
        self.assertEqual(d["retry_at"], NOW + 1200)
        self.assertIsNone(d["latest"])
        for force in (False, True):
            asyncio.run(update.remote_state(force=force))
        self.assertEqual(self.asked, 1)
        self.clock[0] = NOW + 1201
        asyncio.run(update.remote_state(force=False))
        self.assertEqual(self.asked, 2)

    def test_other_refusal_pauses_page_views_not_check_now(self):
        self.refuse(502, None)
        d = asyncio.run(update.remote_state())
        self.assertIn("nicht abrufbar", d["error"])
        asyncio.run(update.remote_state())
        self.assertEqual(self.asked, 1)
        asyncio.run(update.remote_state(force=True))   # "Jetzt prüfen" asks again
        self.assertEqual(self.asked, 2)
        self.clock[0] = NOW + update._FAIL_PAUSE + 1
        asyncio.run(update.remote_state())
        self.assertEqual(self.asked, 3)

    def test_success_clears_the_pause(self):
        self.refuse(502, None)
        asyncio.run(update.remote_state())

        async def runs(repo, branch):
            return [{"head_branch": "main", "conclusion": "success", "head_sha": "a" * 40}]
        update.green_runs = runs
        # the installed version is the newest one: nothing else is asked from GitHub
        update.installed_version = lambda: {"remote": "https://github.com/x/y.git", "branch": "main", "commit": "a" * 40}
        d = asyncio.run(update.remote_state(force=True))
        self.assertEqual(d["latest"], "a" * 40)
        self.assertIsNone(d["error"])
        self.assertEqual(d["behind"], 0)
        self.assertIsNone(update._failed["data"])


if __name__ == "__main__":
    unittest.main()
