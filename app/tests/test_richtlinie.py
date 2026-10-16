"""Coding-Richtlinie (docs/de/richtlinien.md, Dominik 2026-10-12): the rules of the guideline that were only agreed
until now get a self-test here.

- Values shipped on in config.default.json are listed with their reason in features.DEFAULT_ON (part 3).
- Journal lines name a profile only with its consent (profiles.log_name, part 4).
- app/VERSION, the newest CHANGELOG.md line and the first line of "Letzte Änderungen"/"Latest changes" in both
  READMEs agree, and each README keeps exactly 10 lines there (part 11).
- The guideline exists in German and English, CLAUDE.md points to it, and every self-test it names exists.

Tests that read files outside app/ skip in the app/-only copy the Spark tests in. No wall clock dependence.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import glob
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import profiles  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
PANEL = os.path.join(APP, "panel")


def repo_file(*parts):
    path = os.path.join(ROOT, *parts)
    if not os.path.exists(path):
        raise unittest.SkipTest(f"{'/'.join(parts)} is not in this copy (the Spark tests only app/)")
    with open(path, encoding="utf-8") as f:
        return f.read()


class DefaultOn(unittest.TestCase):
    def test_every_value_shipped_on_has_a_reason(self):
        with open(os.path.join(APP, "config.default.json")) as f:
            cfg = json.load(f)
        on = set()

        def walk(d, path):
            for k, v in d.items():
                key = path + k
                if key == "chat.defaults":
                    continue        # a profile's own manners, never a function (test_features)
                if isinstance(v, dict):
                    walk(v, key + ".")
                elif v is True:
                    on.add(key)
        walk(cfg, "")
        self.assertEqual(sorted(on - set(features.DEFAULT_ON)), [],
                         "shipped on without a reason: add it to features.DEFAULT_ON or ship it off")
        self.assertEqual(sorted(set(features.DEFAULT_ON) - on), [], "listed in features.DEFAULT_ON but shipped off")
        for key, why in features.DEFAULT_ON.items():
            self.assertGreater(len(why.strip()), 10, key)


class JournalNames(unittest.TestCase):
    NAME = re.compile(r"""\b(prof|who|p|u|user|owner|person|target)\[["']name["']\]|\b(prof|who|user)\.get\(["']name["']""")

    def test_no_profile_name_in_a_journal_line(self):
        found = []
        for path in sorted(glob.glob(os.path.join(PANEL, "*.py"))):
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for m in re.finditer(r"print\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)", src):
                if self.NAME.search(m.group(0)):
                    found.append(f"{os.path.basename(path)}:{src[:m.start()].count(chr(10)) + 1}")
        self.assertEqual(found, [], "journal lines name profiles only through profiles.log_name(prof)")

    def test_name_only_with_consent(self):
        uid = profiles.add_user("Richtlinie Rita", "4711")
        prof = profiles.by_id(uid)
        self.assertEqual(profiles.log_name(None), "guest")
        self.assertEqual(profiles.log_name(prof), "Profil " + uid[-4:])
        profiles.save_settings(uid, {"trace_name": True})
        self.assertEqual(profiles.log_name(prof), "Richtlinie Rita")
        profiles.save_settings(uid, {"trace_name": False})
        self.assertNotIn("Rita", profiles.log_name(prof))


class Versions(unittest.TestCase):
    def test_version_changelog_and_readmes_agree(self):
        with open(os.path.join(APP, "VERSION")) as f:
            version = f.read().strip()
        log = repo_file("CHANGELOG.md")
        first = re.search(r"^- \*\*(V\d+\.\d+\.\d+)\*\*", log, re.M)
        self.assertIsNotNone(first)
        self.assertEqual(first.group(1), version, "newest CHANGELOG.md line must be app/VERSION")
        for name, head in (("README.md", "## Latest changes"), ("README.de.md", "## Letzte Änderungen")):
            text = repo_file(name)
            self.assertIn(head, text, name)
            part = text.split(head, 1)[1].split("\n## ", 1)[0]
            lines = re.findall(r"^- \*\*(V\d+\.\d+\.\d+)\*\*", part, re.M)
            self.assertEqual(len(lines), 10, f"{name}: keep exactly 10 lines under {head}")
            self.assertEqual(lines[0], version, f"{name}: the newest line must be app/VERSION")
            self.assertEqual(len(set(lines)), 10, f"{name}: a version twice")


class Guideline(unittest.TestCase):
    def test_no_tear_down_turns_off_a_switch_that_ships_on(self):
        """A test puts a switch back the way it was (helpers.keep_chat), never to False when it ships on:
        test_rmpapier.TaskParts left the calendar off, and test_sperre_ueberall later failed four times (2026-10-16)."""
        import ast
        with open(os.path.join(helpers.APP, "config.default.json"), encoding="utf-8") as f:
            on = {k for k, v in json.load(f)["chat"].items() if v is True}
        bad = []
        for path in glob.glob(os.path.join(helpers.APP, "tests", "test_*.py")):
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef) or fn.name not in ("tearDown", "tearDownClass"):
                    continue
                for call in ast.walk(fn):
                    if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "set_config":
                        bad += [f"{os.path.basename(path)}: {kw.arg}" for kw in call.keywords
                                if kw.arg in on and isinstance(kw.value, ast.Constant) and kw.value.value is False]
        self.assertEqual(bad, [], "use helpers.keep_chat(self, …) in setUp")

    def test_both_languages_and_claude_md_point_to_it(self):
        de = repo_file("docs", "de", "richtlinien.md")
        en = repo_file("docs", "en", "guidelines.md")
        claude = repo_file("CLAUDE.md")
        self.assertIn("docs/de/richtlinien.md", claude)
        self.assertIn("docs/en/guidelines.md", claude)
        for text in (de, en):
            self.assertIn("sicherheits-checkliste.md" if text is de else "security-checklist.md", text)
        repo_file("docs", "de", "sicherheits-checkliste.md")
        repo_file("docs", "en", "security-checklist.md")

    def test_every_named_self_test_exists(self):
        """A renamed or removed test must not leave the guideline pointing at nothing."""
        modules, methods = set(), set()
        for path in glob.glob(os.path.join(APP, "tests", "test_*.py")):
            modules.add(os.path.basename(path)[:-3])
            with open(path, encoding="utf-8") as f:
                methods.update(re.findall(r"def (test_[a-z0-9_]+)\(", f.read()))
        for parts in (("docs", "de", "richtlinien.md"), ("docs", "en", "guidelines.md"), ("CLAUDE.md",)):
            named = set(re.findall(r"\b(test_[a-z0-9_]*[a-z0-9])\b", repo_file(*parts)))
            self.assertEqual(sorted(named - modules - methods), [], f"{'/'.join(parts)} names self-tests that do not exist")


if __name__ == "__main__":
    unittest.main()
