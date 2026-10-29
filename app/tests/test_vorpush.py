"""The quick test before a push (tools/vorpush.py, guideline part 10 point 5): its guard list is the one list,
every name in it exists, the docs point to it, it runs every module (the slow browser test only for pages) and
it stops a push onto a red main (V01.0.820).

tools/ is not in a copy with only app/ (install selftest): then these tests are skipped."""
import importlib.util
import os
import re
import contextlib
import inspect
import io
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "tools", "vorpush.py")


def load():
    if not os.path.exists(SCRIPT):
        raise unittest.SkipTest("tools/vorpush.py is not in this copy (only app/)")
    spec = importlib.util.spec_from_file_location("vorpush", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Vorpush(unittest.TestCase):
    def setUp(self):
        self.v = load()

    def test_every_guard_test_exists(self):
        missing = [n for n in self.v.WAECHTER if not os.path.exists(os.path.join(HERE, n + ".py"))]
        self.assertEqual(missing, [], "guard tests named in tools/vorpush.py that do not exist")
        self.assertEqual(len(set(self.v.WAECHTER)), len(self.v.WAECHTER), "a guard test twice")

    def test_docs_point_to_the_script_and_keep_no_own_list(self):
        for parts in (("CLAUDE.md",), ("docs", "de", "richtlinien.md"), ("docs", "en", "guidelines.md")):
            text = read(*parts)
            self.assertIn("tools/vorpush.py", text, os.path.join(*parts))
            # a second hand-kept list drifts (rule 12): the quick-test paragraph names the script, not the tests
            for line in text.splitlines():
                if "tools/vorpush.py" in line:
                    named = set(re.findall(r"`(test_\w+)`", line))
                    self.assertLess(len(named), 3, os.path.join(*parts) + " lists guard tests again")

    def test_a_changed_file_brings_its_tests(self):
        with tempfile.TemporaryDirectory() as d:
            for name, body in (("test_live.py", ""), ("test_other.py", "open('static/js/live.js')"),
                               ("test_far.py", "nothing"), ("test_ver.py", "VERSION")):
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    f.write(body)
            self.assertEqual(self.v.tests_for(["app/panel/live.py"], d), ["test_live"])
            self.assertEqual(self.v.tests_for(["app/panel/static/js/live.js"], d), ["test_live", "test_other"])
            self.assertEqual(self.v.tests_for(["app/tests/test_far.py"], d), ["test_far"])
            self.assertEqual(self.v.tests_for(["app/VERSION"], d), [], "a bare name would match every test")

    def test_every_module_runs_and_the_slow_one_only_for_pages(self):
        """V01.0.820: picking by file name missed test_mail_zeit/test_hilfe_quality (main red .808-.817)."""
        with tempfile.TemporaryDirectory() as d:
            for name, body in (("test_ui_browser.py", "chat.js"), ("test_mail_zeit.py", "import chat_tools"),
                               ("test_hilfe_quality.py", "import hilfe")):
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    f.write(body)
            self.assertEqual(self.v.pick(["app/panel/chat_tools.py"], (), d), ["test_hilfe_quality", "test_mail_zeit"])
            self.assertIn("test_ui_browser", self.v.pick(["app/panel/static/js/me.js"], (), d))
            self.assertIn("test_ui_browser", self.v.pick(["app/panel/x.py"], ("test_ui_browser",), d))
        self.assertTrue(set(self.v.SLOW) <= {n[:-3] for n in os.listdir(HERE)})

    def test_red_main_stops_the_push_unless_it_is_the_fix(self):
        def run(c, t, sha="a"):
            return {"status": "completed" if c else "in_progress", "conclusion": c, "created_at": t, "head_sha": sha}
        ms = self.v.main_state
        self.assertEqual(ms([run(None, "T5"), run("failure", "T4"), run("cancelled", "T3"), run("failure", "T2"),
                             run("success", "T1")]), ("red", "T2"))
        self.assertEqual(ms([run("failure", "T2"), run("success", "T1")]), ("red", "T2"))
        self.assertEqual(ms([run(None, "T2"), run("success", "T1")]), ("green", None))
        self.assertEqual(ms([run("cancelled", "T1")]), ("unknown", None))
        self.assertEqual(ms("nonsense"), ("unknown", None))
        # vorpush keeps no copy of its own (rule 12): the one in update.py, read from the file
        self.assertNotIn('return "red", since', read("tools", "vorpush.py"))
        import io
        import json
        from unittest import mock
        body = json.dumps({"workflow_runs": [run("failure", "2026-10-18T21:44:59Z")]}).encode()
        with mock.patch.object(self.v.urllib.request, "urlopen", return_value=io.BytesIO(body)):
            with self.assertRaises(SystemExit):
                self.v.check_main(False)
            self.v.check_main(True)                       # the fix itself passes
        with mock.patch.object(self.v.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.v.check_main(False)                      # GitHub not readable: goes on, GitHub's full run decides

    def test_version_numbers_compare_as_numbers(self):
        self.assertGreater(self.v.version_num("V01.0.1000"), self.v.version_num("V01.0.999"))
        self.assertIsNone(self.v.version_num("01.0.5"))

    def test_playwright_pin_comes_from_the_workflow(self):
        self.assertRegex(self.v.playwright_pin() or "", r"^\d+\.\d+\.\d+$")

    def test_system_packages_come_from_the_workflow(self):
        """1b.: the apt packages are GitHub's (one list); the ones test_fernbild names are among them."""
        pkgs = self.v.apt_packages()
        self.assertIn("ffmpeg", pkgs)
        named = re.search(r"apt install ([a-z0-9. -]+)\)", read("app", "tests", "test_fernbild.py")).group(1).split()
        self.assertEqual([p for p in named if p not in pkgs], [], "test_fernbild names a package GitHub does not install")
        src = inspect.getsource(self.v.main)
        self.assertLess(src.index("if only_list"), src.index("system_packages()"))     # --liste changes nothing
        self.assertLess(src.index("system_packages()"), src.index("pool.map"))         # before the first test

    def run_check(self, missing_seq, root=True, have=("apt-get", "sudo")):
        """system_packages() with dpkg and apt-get faked: (calls, output, exit code or None)."""
        calls, seq = [], list(missing_seq)

        def run(cmd, **kw):
            calls.append(cmd)
            ok = not (cmd[0] == "which" and cmd[1] not in have)
            return unittest.mock.Mock(returncode=0 if ok else 1, stdout="", stderr="")
        out, code = io.StringIO(), None
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(self.v, "APT_MARK", os.path.join(d, "apt-ok")), \
                unittest.mock.patch.object(self.v, "apt_packages", lambda: ["guacd", "x11vnc"]), \
                unittest.mock.patch.object(self.v, "apt_missing", lambda pkgs: seq.pop(0) if seq else []), \
                unittest.mock.patch.object(self.v.subprocess, "run", run), \
                unittest.mock.patch.object(self.v.os, "geteuid", lambda: 0 if root else 1000), \
                contextlib.redirect_stdout(out):
            try:
                self.v.system_packages()
            except SystemExit as e:
                code = e.code
            mark = os.path.exists(os.path.join(d, "apt-ok"))
            if code is None:      # remembered: the next run asks dpkg nothing
                seq[:] = [["guacd"]]
                self.v.system_packages()
                self.assertEqual(seq, [["guacd"]])
        return calls, out.getvalue(), code, mark

    def test_missing_system_packages_are_installed_or_stop_before_any_test(self):
        calls, _, code, mark = self.run_check([[]])                          # all there: nothing installed
        self.assertIsNone(code)
        self.assertTrue(mark)
        self.assertFalse([c for c in calls if "install" in c])
        calls, _, code, mark = self.run_check([["x11vnc"], []])              # missing: installed, as root
        self.assertIsNone(code)
        self.assertIn(["apt-get", "install", "-y", "-q", "--no-install-recommends", "x11vnc"], calls)
        calls, _, code, _ = self.run_check([["x11vnc"], []], root=False)     # not root: with sudo -n
        self.assertIn(["sudo", "-n", "apt-get", "install", "-y", "-q", "--no-install-recommends", "x11vnc"], calls)
        for seq, root, have in (([["x11vnc"], ["x11vnc"]], True, ("apt-get",)),   # install fails
                                ([["x11vnc"]], False, ("apt-get",)),              # not root, no sudo
                                ([["x11vnc"]], True, ())):                        # no apt-get
            calls, out, code, mark = self.run_check(seq, root, have)
            self.assertEqual(code, 1, out)
            self.assertFalse(mark)
            self.assertIn("STOPP", out)
            self.assertIn("apt-get install -y -q --no-install-recommends x11vnc", out)   # the exact command


if __name__ == "__main__":
    unittest.main()
