"""selftest.py (Dominik 2026-10-11, choice 1): a failed test gets exactly one second try; failing twice stays red,
green only the second time passes with a visible warning, many failures get no second try. Same rule on GitHub
and on the Spark (install.sh)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(APP, "selftest.py")
if APP not in sys.path:
    sys.path.insert(0, APP)
import selftest  # noqa: E402

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
            # the outer run's report (Werkstatt and GitHub parts): the inner run must not write into it
            for k in ("GITHUB_ACTIONS", "SELFTEST_REPORT", "SELFTEST_NOTE", "SELFTEST_DAUER"):
                env.pop(k, None)
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

    def test_the_parts_together_run_every_test_once(self):
        """V01.0.502: GitHub runs the tests in parts at the same time; together they are the whole run, cut by
        module, a long class (entries per test in dauer.json) test by test."""
        files = {f"test_m{i}.py": "import unittest\n" + "".join(
            f"class C{j}(unittest.TestCase):\n    def test_a(self):\n        print('RAN m{i}.C{j}')\n"
            for j in range(3)) for i in range(5)}
        files["test_broken_import.py"] = "import not_a_module_anywhere\n"
        # a long class cut test by test (its tests have their own entries in dauer.json): each part starts it anew
        files["test_long.py"] = ("import unittest\nclass Long(unittest.TestCase):\n    @classmethod\n"
                                 "    def setUpClass(cls):\n        print('START Long')\n" + "".join(
                                     f"    def test_{j}(self):\n        print('RAN long.{j}')\n" for j in range(4)))
        seen = []
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "tests"))
            for name, text in files.items():
                with open(os.path.join(d, "tests", name), "w") as f:
                    f.write(text)
            with open(os.path.join(d, "tests", "dauer.json"), "w") as f:
                f.write('{"test_m0": 500, "test_m1": 300, "test_long.Long.test_0": 400, "test_long.Long.test_1": 400}')
            env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY")}
            reports = os.path.join(d, "teile")
            broken, starts = 0, 0
            for k in (1, 2, 3):
                os.makedirs(os.path.join(reports, f"teil-{k}"))
                env["SELFTEST_REPORT"] = os.path.join(reports, f"teil-{k}", "teil.json")
                p = subprocess.run([sys.executable, RUNNER, "discover", "-s", "tests", "--part", f"{k}/3"], cwd=d,
                                   env=env, capture_output=True, text=True, timeout=120)
                ran = [line.split()[1] for line in p.stdout.splitlines() if line.startswith("RAN ")]
                seen += ran
                for i in range(5):     # a module stays together: its classes may count on each other
                    self.assertIn(sum(f"m{i}.C{j}" in ran for j in range(3)), (0, 3))
                broken += "not_a_module_anywhere" in p.stdout + p.stderr
                starts += p.stdout.count("START Long")
                self.assertIn(f"part {k}/3", p.stdout)
            self.assertEqual(sorted(seen), sorted([f"m{i}.C{j}" for i in range(5) for j in range(3)]
                                                  + [f"long.{j}" for j in range(4)]))
            self.assertGreater(starts, 1)
            self.assertEqual(broken, 1)                       # a module that does not import is red in one part
            # the parts together: 16 tests, one failed (twice), within the limit; with a part missing it is red
            p = subprocess.run([sys.executable, RUNNER, "--sum", reports, "3"], capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertIn("20 tests in 3 parts, 1 failed the first time", p.stdout)
            p = subprocess.run([sys.executable, RUNNER, "--sum", reports, "4"], capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 1)
            self.assertIn("part 4/4 sent no result", p.stdout)

    def test_more_than_five_failures_over_all_parts_are_red(self):
        """The limit of MAX_RETRY first failures counts for the whole run, not per part."""
        with tempfile.TemporaryDirectory() as d:
            for k, fails in ((1, 3), (2, 3)):
                os.makedirs(os.path.join(d, f"teil-{k}"))
                with open(os.path.join(d, f"teil-{k}", "teil.json"), "w") as f:
                    json.dump({"failed_first": [f"t{k}.{i}" for i in range(fails)], "ran": 10}, f)
            self.assertEqual(selftest.total(d, 2), 1)
            self.assertEqual(selftest.total(d, 1), 0)

    def test_note_names_red_and_wobbly_tests(self):
        """V01.0.820: GitHub opens "main rot" with the tests that stayed red and counts the wobbly ones."""
        with tempfile.TemporaryDirectory() as d:
            for k, data in ((1, {"failed_first": ["t.a", "t.b"], "red": ["t.a"], "wobbly": ["t.b"], "ran": 5}),
                            (2, {"failed_first": [], "ran": 5})):
                os.makedirs(os.path.join(d, f"teil-{k}"))
                with open(os.path.join(d, f"teil-{k}", "teil.json"), "w") as f:
                    json.dump(data, f)
            note = os.path.join(d, "note.md")
            with mock.patch.dict(os.environ, {"SELFTEST_NOTE": note}):
                self.assertEqual(selftest.total(d, 2), 0)
            with open(note, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("- `t.a`", text.split(selftest.WARN)[0])
            self.assertIn("- `t.b`", text.split(selftest.WARN)[1])
            os.remove(note)
            with open(os.path.join(d, "teil-1", "teil.json"), "w") as f:
                json.dump({"failed_first": [], "ran": 5}, f)
            with mock.patch.dict(os.environ, {"SELFTEST_NOTE": note}):
                selftest.total(d, 2)
            self.assertFalse(os.path.exists(note), "all green and steady: no note")

    def test_the_report_counts_skipped_tests(self):
        """The Werkstatt shows skipped tests as "did not run", never as green (2026-10-21)."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "teil.json")
            result = unittest.TestResult()
            result.testsRun, result.skipped = 5, [(self, "no browser"), (self, "app/-only copy")]
            with mock.patch.dict(os.environ, {"SELFTEST_REPORT": path}):
                selftest._report([], result)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["skipped"], 2)

    def test_cut_is_complete_and_the_same_everywhere(self):
        keys = [f"test_x{i}.C{j}" for i in range(30) for j in range(4)]
        dur = {k: (i * 7) % 90 for i, k in enumerate(keys)}
        cut = selftest.parts(keys, 4, dur)
        self.assertEqual(sorted(k for p in cut for k in p), sorted(keys))
        self.assertEqual(cut, selftest.parts(list(reversed(keys)), 4, dur))
        loads = [sum(dur.get(k, selftest.NEW_UNIT) for k in p) for p in cut]
        self.assertLessEqual(max(loads) - min(loads), 90)
        with open(os.path.join(APP, "tests", "dauer.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertTrue(data and all(isinstance(v, (int, float)) and v >= 0 for v in data.values()))

    def test_github_runs_all_parts(self):
        path = os.path.join(os.path.dirname(APP), ".github", "workflows", "tests.yml")
        if not os.path.exists(path):
            self.skipTest("app/-only copy")
        with open(path) as f:
            text = f.read()
        n = len(re.search(r"part: \[([0-9, ]+)\]", text).group(1).split(","))
        self.assertIn(f"part: {list(range(1, n + 1))}", text)
        self.assertIn(f"--part ${{{{ matrix.part }}}}/{n}", text)
        self.assertIn(f'selftest.py --sum "$RUNNER_TEMP/teile" {n}', text)
        self.assertIn("cancel-in-progress: false", text)

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
