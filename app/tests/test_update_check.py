"""Update check (update.py): GitHub's hourly limit for unauthenticated questions is recognised, the
next question waits until it is lifted, and a refusal is not repeated on every page view."""
import asyncio
import contextlib
import io
import os
import subprocess
import tempfile
import unittest

from tests import helpers

helpers.start()
import common  # noqa: E402
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
        async def runs(repo, branch, passed=False):
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

        async def runs(repo, branch, passed=False):
            return [{"head_branch": "main", "conclusion": "success", "head_sha": "a" * 40}]
        update.green_runs = runs
        # the installed version is the newest one: nothing else is asked from GitHub
        update.installed_version = lambda: {"remote": "https://github.com/x/y.git", "branch": "main", "commit": "a" * 40}
        d = asyncio.run(update.remote_state(force=True))
        self.assertEqual(d["latest"], "a" * 40)
        self.assertIsNone(d["error"])
        self.assertEqual(d["behind"], 0)
        self.assertIsNone(update._failed["data"])

    def answer(self, newest, green):
        async def runs(repo, branch, passed=False):
            self.asked += 1
            return green if passed else newest
        update.green_runs = runs

    def test_cancelled_runs_fall_back_to_the_newest_green_one(self):
        # pushes in a row cancel each other's runs: the newest 30 hold no green one
        cancelled = [{"head_branch": "main", "conclusion": "cancelled", "head_sha": c * 40} for c in "abc"]
        self.answer(cancelled, [{"head_branch": "main", "conclusion": "success", "head_sha": "e" * 40}])
        d = asyncio.run(update.remote_state(force=True))
        self.assertIsNone(d["error"])
        self.assertEqual((d["latest"], d["behind"]), ("e" * 40, 0))
        self.assertEqual(self.asked, 2)

    def test_no_green_version_is_not_called_unreadable(self):
        self.answer([{"head_branch": "main", "conclusion": "failure", "head_sha": "a" * 40}], [])
        d = asyncio.run(update.remote_state(force=True))
        self.assertIsNone(d["latest"])
        self.assertIn("noch keine Version die Tests bestanden", d["error"])
        self.assertNotIn("nicht abrufbar", d["error"])
        self.assertTrue(d["no_green"])

    def test_live_names_a_missing_green_version(self):
        import live
        seen, real = [], (live.on, live.job, live.event)
        live.on, live.job, live.event = (lambda: True), (lambda *a, **k: None), (lambda kind, text: seen.append(text))
        try:
            live.update_checked({"error": "x", "no_green": True}, NOW)
            live.update_checked({"error": "x"}, NOW)
        finally:
            live.on, live.job, live.event = real
        self.assertIn("keine Version mit bestandenen Tests", seen[0])
        self.assertIn("nicht erreichbar", seen[1])

    def test_failure_names_its_reason(self):
        """Logs → Anfragen showed only "GitHub nicht ok | error": every failure now carries a fixed reason word."""
        import live
        jobs, seen, real = [], [], (live.on, live.job, live.event)
        live.on, live.event = (lambda: True), (lambda kind, text: seen.append(text))
        live.job = lambda *a, **k: jobs.append(k.get("code"))
        try:
            self.refuse(403, NOW + 1200)
            self.assertEqual(asyncio.run(update.remote_state(force=True))["why"], "github_limit")
            update._failed.update(until=0.0, data=None, limited=False)
            self.refuse(401, None)
            self.assertEqual(asyncio.run(update.remote_state(force=True))["why"], "github_http_401")
            update._failed.update(until=0.0, data=None, limited=False)
            update.run = lambda *a, **k: (128, "fatal: unable to access")
            self.assertEqual(asyncio.run(update.remote_state(force=True))["why"], "git_ls_remote")
        finally:
            live.on, live.job, live.event = real
        self.assertEqual(jobs, ["github_limit", "github_http_401", "git_ls_remote"])
        self.assertIn("60 Abfragen", seen[0])
        self.assertIn("HTTP 401", seen[1])
        self.assertIn("nicht erreichbar", seen[2])

    def test_by_itself_github_is_asked_every_three_hours(self):
        self.answer([{"head_branch": "main", "conclusion": "success", "head_sha": "e" * 40}], [])
        asyncio.run(update.remote_state())
        self.clock[0] = NOW + 3 * 3600 - 1
        asyncio.run(update.remote_state())
        self.assertEqual(self.asked, 1)
        asyncio.run(update.remote_state(force=True))   # "Jetzt prüfen" always asks
        self.assertEqual(self.asked, 2)
        self.clock[0] = NOW + 2 * 3 * 3600
        asyncio.run(update.remote_state())
        self.assertEqual(self.asked, 3)

    def test_watchdog_never_asks_the_github_api(self):
        # every question to api.github.com counts against the 60 per hour the update check needs
        import dienstwacht
        self.assertFalse([u for u in dienstwacht.INET if "api.github.com" in u])

    def test_update_sh_asks_for_passed_runs_too(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            with open(os.path.join(root, "update.sh")) as f:
                sh = f.read()
        except OSError:
            self.skipTest("update.sh is not part of the app/ copy")
        self.assertIn("&status=success&per_page=5", sh)


if __name__ == "__main__":
    unittest.main()


class DeletedWorkingFolder(unittest.TestCase):
    """V01.1.315: install.sh swaps app/ and deletes the old copy; an install that stopped before the panel's restart
    left the panel in a deleted folder, and "Jetzt prüfen" showed git's "fatal: Unable to read current working
    directory". Every program from common.run now starts in an existing folder, and the card names the cause in words."""

    def setUp(self):
        self.home = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.real = (update.installed_version, common._START_DIR)
        update._remote_cache.update(time=0, data=None)
        update._failed.update(until=0.0, data=None, limited=False)

    def tearDown(self):
        os.chdir(self.home)
        update.installed_version, common._START_DIR = self.real
        update._remote_cache.update(time=0, data=None)
        update._failed.update(until=0.0, data=None, limited=False)
        self.tmp.cleanup()

    def leave_deleted(self):
        """This process now sits in a folder that no longer exists, as the panel after an aborted install.sh."""
        gone = os.path.join(self.tmp.name, "app-alt")
        os.mkdir(gone)
        os.chdir(gone)
        os.rmdir(gone)
        with self.assertRaises(OSError):
            os.getcwd()

    def repo(self):
        """A local repository with one commit on main: git ls-remote needs no network for it."""
        r = os.path.join(self.tmp.name, "repo")
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", "-c", "init.defaultBranch=main"]
        subprocess.run(g + ["init", "-q", r], check=True, cwd=self.tmp.name)
        subprocess.run(g + ["-C", r, "commit", "-q", "--allow-empty", "-m", "eins"], check=True, cwd=self.tmp.name)
        subprocess.run(g + ["-C", r, "branch", "-q", "-M", "main"], check=True, cwd=self.tmp.name)
        return r, subprocess.run(["git", "-C", r, "rev-parse", "HEAD"], capture_output=True, text=True,
                                 check=True).stdout.strip()

    def test_check_works_in_a_deleted_folder(self):
        r, sha = self.repo()
        update.installed_version = lambda: {"remote": r, "branch": "main", "commit": "e" * 40}
        start = os.path.join(self.tmp.name, "start")
        os.mkdir(start)
        common._START_DIR = start
        self.leave_deleted()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            d = asyncio.run(update.remote_state(force=True))
        self.assertIsNone(d["error"], d)
        self.assertEqual(d["latest"], sha)
        # the process went back to where it was started, and said so in fixed words
        self.assertEqual(os.getcwd(), start)
        self.assertIn("zustand: arbeitsordner fehlte, jetzt startordner", out.getvalue())
        self.assertIn("update check: ok", out.getvalue())

    def test_without_the_start_folder_the_root(self):
        common._START_DIR = os.path.join(self.tmp.name, "weg")
        self.leave_deleted()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(common.fester_ordner(), "/")
        self.assertEqual(os.getcwd(), "/")
        self.assertEqual(common.run(["git", "--version"])[0], 0)

    def test_failure_in_words_not_gits_text(self):
        secret = "https://user:ghp_geheim@github.com/x/y.git"
        update.installed_version = lambda: {"remote": secret, "branch": "main", "commit": "e" * 40}
        real = update.run
        cases = {"fatal: Unable to read current working directory: No such file or directory": "arbeitsordner",
                 "[Errno 2] No such file or directory: 'git'": "ohne_git",
                 f"Command '['git', 'ls-remote', '{secret}']' timed out after 30 seconds": "zeit",
                 f"fatal: unable to access '{secret}/': Could not resolve host: github.com": "netz"}
        try:
            for text, art in cases.items():
                update._failed.update(until=0.0, data=None, limited=False)
                update.run = lambda *a, _t=text, **k: (128, _t)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    d = asyncio.run(update.remote_state(force=True))
                self.assertEqual(update.git_fehlerart(128, text), art)
                self.assertEqual((d["error"], d["error_en"]), update.GIT_FEHLER[art])
                self.assertEqual(d["why"], "git_ls_remote")
                for x in (d["error"], d["error_en"], out.getvalue()):
                    self.assertNotIn("fatal", x)
                    self.assertNotIn("ghp_geheim", x)
                self.assertIn(f"update check failed: git ls-remote {art} (exit 128)", out.getvalue())
        finally:
            update.run = real
