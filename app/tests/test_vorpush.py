"""The quick test before a push (tools/vorpush.py, guideline part 10 point 5): its guard list is the one list,
every name in it exists, the docs point to it, and it picks the tests of a changed file.

tools/ is not in a copy with only app/ (install selftest): then these tests are skipped."""
import importlib.util
import os
import re
import tempfile
import unittest

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

    def test_version_numbers_compare_as_numbers(self):
        self.assertGreater(self.v.version_num("V01.0.1000"), self.v.version_num("V01.0.999"))
        self.assertIsNone(self.v.version_num("01.0.5"))

    def test_playwright_pin_comes_from_the_workflow(self):
        self.assertRegex(self.v.playwright_pin() or "", r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
