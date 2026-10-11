"""selftest.py (Dominik 2026-10-11, choice 1): a failed test gets exactly one second try; failing twice stays red,
green only the second time passes with a visible warning, many failures get no second try. Same rule on GitHub
and on the Spark (install.sh)."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(APP, "selftest.py")

FLAKY = '''
import os, unittest
MARK = os.environ["FLAKY_MARK"]
class Wobbly(unittest.TestCase):
    def test_second_time_green(self):
        if not os.path.exists(MARK):
            open(MARK, "w").close()
            self.fail("first time red")
class Fine(unittest.TestCase):
    def test_ok(self):
        pass
'''

BROKEN = '''
import unittest
class Broken(unittest.TestCase):
    def test_always_red(self):
        self.fail("red every time")
'''

MANY = '''
import unittest
class Many(unittest.TestCase):
''' + "".join(f"    def test_red_{i}(self):\n        self.fail('x')\n" for i in range(7))

SETUPCLASS = '''
import os, unittest
MARK = os.environ["FLAKY_MARK"]
class Starts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(MARK):
            open(MARK, "w").close()
            raise RuntimeError("server did not start")
    def test_after_start(self):
        pass
'''


class Runner(unittest.TestCase):
    def run_tests(self, files, summary=False):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "tests"))
            open(os.path.join(d, "tests", "__init__.py"), "w").close()
            for name, text in files.items():
                with open(os.path.join(d, "tests", name), "w") as f:
                    f.write(textwrap.dedent(text))
            env = dict(os.environ, FLAKY_MARK=os.path.join(d, "mark"))
            env.pop("GITHUB_ACTIONS", None)
            out = os.path.join(d, "summary.md")
            if summary:
                env["GITHUB_STEP_SUMMARY"] = out
            else:
                env.pop("GITHUB_STEP_SUMMARY", None)
            p = subprocess.run([sys.executable, RUNNER, "discover", "-s", "tests", "-t", "."], cwd=d, env=env,
                               capture_output=True, text=True, timeout=120)
            text = open(out).read() if summary and os.path.exists(out) else ""
            return p.returncode, p.stdout + p.stderr, text

    def test_green_only_the_second_time_passes_with_a_warning(self):
        code, log, summary = self.run_tests({"test_flaky.py": FLAKY}, summary=True)
        self.assertEqual(code, 0, log)
        self.assertIn("WARNUNG erst im zweiten Versuch grün: tests.test_flaky.Wobbly.test_second_time_green", log)
        self.assertNotIn("Fine", log.split("second try for", 1)[1])        # only the failed test runs again
        self.assertIn("tests.test_flaky.Wobbly.test_second_time_green", summary)

    def test_failing_twice_stays_red(self):
        code, log, _ = self.run_tests({"test_flaky.py": FLAKY, "test_broken.py": BROKEN})
        self.assertEqual(code, 1, log)
        self.assertIn("failed twice", log)
        self.assertNotIn("WARNUNG", log)

    def test_many_failures_get_no_second_try(self):
        code, log, _ = self.run_tests({"test_many.py": MANY})
        self.assertEqual(code, 1, log)
        self.assertIn("no second try", log)
        self.assertNotIn("second try for", log)

    def test_a_class_that_did_not_start_runs_again_as_a_whole(self):
        code, log, _ = self.run_tests({"test_starts.py": SETUPCLASS})
        self.assertEqual(code, 0, log)
        self.assertIn("WARNUNG erst im zweiten Versuch grün: tests.test_starts.Starts", log)

    def test_github_and_the_spark_use_it(self):
        root = os.path.dirname(APP)
        for path, line in ((".github/workflows/tests.yml", "python selftest.py discover -s tests"),
                           ("install.sh", "selftest.py")):
            full = os.path.join(root, path)
            if not os.path.exists(full):
                self.skipTest("app/-only copy")
            with open(full) as f:
                self.assertIn(line, f.read(), path)


if __name__ == "__main__":
    unittest.main()
