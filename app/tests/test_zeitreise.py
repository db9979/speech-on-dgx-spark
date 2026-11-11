"""Tests do not depend on the date (code review 2026-11-11, Dominik „1-11“): the fixed clock for tests with fixed
moments (helpers.feste_uhr) and the nightly run with the clock months ahead (tools/zeitreise.py, GitHub
"Zeitreise"). On 2026-11-11 main went red without any push: fixed moments of 12.10. met a 30-day window of the
real clock. (tools/ and .github are not part of an app/-only copy; those tests are skipped there.)"""
import contextlib
import importlib.util
import io
import os
import tempfile
import time
import types
import unittest
from unittest import mock

from tests import helpers

TOOL = os.path.join(helpers.APP, "..", "tools", "zeitreise.py")
T0 = 1_791_800_000.0


def tool():
    if not os.path.exists(TOOL):
        raise unittest.SkipTest("tools/zeitreise.py is not part of this copy")
    spec = importlib.util.spec_from_file_location("zeitreise_tool", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FesteUhr(unittest.TestCase):
    def test_only_the_named_module_gets_the_clock_and_only_for_the_test(self):
        a, b = types.SimpleNamespace(time=time), types.SimpleNamespace(time=time)

        class One(unittest.TestCase):
            def test_x(self):
                uhr = helpers.feste_uhr(self, T0, a)
                self.assertIs(a.time, uhr)
                self.assertIs(b.time, time)
                self.assertTrue(T0 <= a.time.time() < T0 + 5)
                self.assertEqual(a.time.strftime("%Y-%m-%d"), time.strftime("%Y-%m-%d", time.localtime(T0)))
                self.assertEqual(a.time.gmtime().tm_year, time.gmtime(T0).tm_year)
                self.assertEqual(a.time.localtime(0), time.localtime(0))          # a given moment stays itself
                self.assertIs(a.time.sleep, time.sleep)                            # the rest is the real module
                self.assertIs(a.time.monotonic, time.monotonic)

        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(One))
        self.assertTrue(r.wasSuccessful(), r.failures + r.errors)
        self.assertEqual(r.testsRun, 1)
        self.assertIs(a.time, time)                                                # back after the test

    def test_the_clock_goes_on_and_a_class_keeps_it_until_its_end(self):
        a = types.SimpleNamespace(time=time)

        class Two(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                cls.uhr = helpers.feste_uhr(cls, T0, a)

            def test_1(self):
                t = a.time.time()
                time.sleep(0.05)
                self.assertGreaterEqual(a.time.time() - t, 0.04)                  # waits and limits still pass

            def test_2(self):
                self.assertIs(a.time, self.uhr)

        r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(Two))
        self.assertTrue(r.wasSuccessful(), r.failures + r.errors)
        self.assertEqual(r.testsRun, 2)
        self.assertIs(a.time, time)


class Zeitreise(unittest.TestCase):
    def test_red_ahead_and_green_today_depends_on_the_date(self):
        z = tool()
        self.assertEqual(z.urteil("gruen", "gruen"), "gruen")
        self.assertEqual(z.urteil("rot", "gruen"), "datum")
        self.assertEqual(z.urteil("haengt", "gruen"), "datum")
        self.assertEqual(z.urteil("rot", "rot"), "gestoert")                       # libfaketime itself disturbs it
        self.assertEqual(z.urteil("rot", "haengt"), "gestoert")
        self.assertGreaterEqual(z.TAGE, 91)                                        # past every 30-, 60-, 90-day window

    def test_a_green_module_runs_once_a_red_one_again_with_todays_date(self):
        z = tool()
        calls = []

        def lauf(py, name, tage, frist=0):
            calls.append((name, tage))
            return {("test_a", 120): ("gruen", []), ("test_b", 120): ("rot", ["test_x (test_b.C.test_x)"]),
                    ("test_b", 0): ("gruen", []), ("test_c", 120): ("haengt", []), ("test_c", 0): ("rot", ["y"])}[name, tage]

        with mock.patch.object(z, "lauf", lauf):
            self.assertEqual(z.pruefe("py", "test_a", 120), ("test_a", "gruen", []))
            self.assertEqual(z.pruefe("py", "test_b", 120), ("test_b", "datum", ["test_x (test_b.C.test_x)"]))
            self.assertEqual(z.pruefe("py", "test_c", 120)[1], "gestoert")
        self.assertEqual(calls, [("test_a", 120), ("test_b", 120), ("test_b", 0), ("test_c", 120), ("test_c", 0)])

    def test_every_module_runs_and_an_unknown_name_is_refused(self):
        z = tool()
        have = sorted(f[:-3] for f in os.listdir(os.path.join(helpers.APP, "tests"))
                      if f.startswith("test_") and f.endswith(".py"))
        self.assertEqual(z.module(), have)
        self.assertEqual(z.module(["test_zeitreise", "test_zeitreise"]), ["test_zeitreise"])
        with self.assertRaises(ValueError):
            z.module(["test_gibt_es_nicht"])

    def test_the_run_is_red_only_for_the_date_and_names_the_tests(self):
        z = tool()
        out = {"test_a": ("test_a", "gruen", []), "test_b": ("test_b", "datum", ["test_x (test_b.C.test_x)"]),
               "test_c": ("test_c", "gestoert", ["y"])}
        with tempfile.TemporaryDirectory() as d:
            note = os.path.join(d, "note.md")

            def main(names, which="/usr/bin/faketime", folgt=True):
                with mock.patch.object(z, "module", return_value=names), \
                        mock.patch.object(z, "dateizeit", return_value=folgt), \
                        mock.patch.object(z, "pruefe", lambda py, n, tage: out[n]), \
                        mock.patch.object(z.shutil, "which", return_value=which), \
                        mock.patch.dict(os.environ, {"ZEITREISE_NOTE": note}), \
                        contextlib.redirect_stdout(io.StringIO()) as o:
                    return z.main([]), o.getvalue()

            code, text = main(["test_a", "test_b", "test_c"])
            self.assertEqual(code, 1)
            self.assertIn("1 green | 1 depend on the date | 1 disturbed", text)
            with open(note, encoding="utf-8") as f:
                body = f.read()
            self.assertIn("- `test_x (test_b.C.test_x)`", body.split("gestört")[0])
            self.assertIn("- `test_c`", body.split("gestört")[1])
            self.assertEqual(main(["test_a", "test_c"])[0], 0)                     # disturbed alone is never red
            self.assertEqual(main(["test_a"], which=None)[0], 2)                   # no faketime: no verdict
            code, text = main(["test_a"], folgt=False)                             # a fresh file would look months old
            self.assertEqual(code, 2)
            self.assertIn("file times do not follow the moved clock", text)

    def test_a_module_that_hangs_goes_with_its_children(self):
        """faketime starts Python as its child: after the limit the whole group goes, nothing keeps running."""
        z = tool()
        with tempfile.TemporaryDirectory() as d:
            fake, pid = os.path.join(d, "faketime"), os.path.join(d, "pid")
            with open(fake, "w") as f:      # stands in for faketime: starts a child that sleeps, and waits for it
                f.write(f"#!/bin/sh\nsleep 300 &\necho $! > {pid}\nwait\n")
            os.chmod(fake, 0o755)
            with mock.patch.dict(os.environ, {"PATH": d + os.pathsep + os.environ.get("PATH", "")}):
                self.assertEqual(z.lauf("python3", "test_zeitreise", 120, frist=1), ("haengt", []))
            with open(pid) as f:
                child = int(f.read())
            for _ in range(50):
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    break
                try:                                   # a zombie of this test process' grandchild: reaped by init
                    with open(f"/proc/{child}/stat") as f:
                        if f.read().split(")")[-1].split()[0] == "Z":
                            break
                except OSError:
                    break
                time.sleep(0.1)
            else:
                self.fail("the child of the hanging run is still there")

    def test_file_times_must_follow_the_clock(self):
        """libfaketime 0.9.10 moves the clock but not the file times Python 3.11 reads: three tests were red only
        because a file written just now looked months old. The run measures it and loads its own part if needed."""
        z = tool()
        seen = []

        def folgt(py, tage):
            seen.append((tage, z._shim["so"]))
            return bool(z._shim["so"])

        with tempfile.TemporaryDirectory() as d, mock.patch.object(z, "_folgt", folgt), \
                mock.patch.dict(z._shim, {"so": None}), \
                mock.patch.object(z.subprocess, "run", return_value=mock.Mock(returncode=0)) as cc:
            self.assertTrue(z.dateizeit("py", 120, d))
            so = os.path.join(d, "zeitreise_stat.so")
            self.assertEqual(seen, [(120, None), (120, so), (0, so)])              # measured first, built, measured again
            self.assertEqual(cc.call_args[0][0][:2], ["cc", "-shared"])
            self.assertIn(z.SHIM, cc.call_args[0][0])
            env = z._umgebung(120)
            self.assertEqual((env["LD_PRELOAD"], env["ZEITREISE_STAT"]), (so, str(120 * 86400)))
            self.assertEqual(z._umgebung(0)["ZEITREISE_STAT"], "0")
            self.assertEqual(env["SPEECH_SPARK_NO_BROWSER"], "1")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(z, "_folgt", return_value=False), \
                mock.patch.dict(z._shim, {"so": None}), \
                mock.patch.object(z.subprocess, "run", return_value=mock.Mock(returncode=1)):
            self.assertFalse(z.dateizeit("py", 120, d))                            # no cc: no verdict
        self.assertTrue(os.path.exists(z.SHIM))
        with open(z.SHIM, encoding="utf-8") as f:
            text = f.read()
        for name in ("stat64", "lstat64", "fstat64", "fstatat64", "utimensat", "futimens", "ZEITREISE_STAT"):
            self.assertIn(name, text)

    def test_github_runs_it_every_night_and_says_so(self):
        text = helpers.repo_file(".github", "workflows", "zeitreise.yml")
        for part in ("schedule:", "cron:", "faketime", "python tools/zeitreise.py", 'gh issue create -R "$R" -t "Zeitreise rot"',
                     "issues: write", "ZEITREISE_NOTE"):
            self.assertIn(part, text)
        self.assertNotIn("continue-on-error: true\n        run: python tools/zeitreise.py", text)


if __name__ == "__main__":
    unittest.main()
