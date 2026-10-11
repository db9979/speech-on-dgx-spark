"""Releases aufräumen (V01.0.371): per series only the newest release stays, retired series go, drafts and
pre-releases are never touched, odd tags never reach the gh command line. (The script lives in .github,
which an app/-only copy does not have; then this is skipped.)"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "scripts", "releases_aufraeumen.py")
WF = os.path.join(ROOT, ".github", "workflows", "releases-aufraeumen.yml")


def rel(tag, day, **kw):
    return {"tag_name": tag, "published_at": f"2026-10-{day:02d}T10:00:00Z", **kw}


class ReleasesAufraeumen(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(SCRIPT):
            self.skipTest("the script is not in an app/-only copy")
        spec = importlib.util.spec_from_file_location("releases_aufraeumen", SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_series(self):
        self.assertEqual(self.m.series("fw-2.5.1.6"), "fw-")
        self.assertEqual(self.m.series("android-v1.10.0"), "android-v")
        self.assertEqual(self.m.series("begleiter-windows"), "begleiter-windows")

    def test_only_newest_per_series_stays(self):
        rs = [rel("fw-2.5.1.6", 11), rel("fw-2.5.1.5", 8), rel("fw-2.5.1.10", 9), rel("android-v1.1.0", 11),
              rel("android-v1.0.0", 10), rel("begleiter-windows", 10), rel("begleiter-mac", 10)]
        self.assertEqual(self.m.plan(rs), ["android-v1.0.0", "fw-2.5.1.10", "fw-2.5.1.5"])

    def test_retired_series_goes_completely(self):
        self.assertEqual(self.m.plan([rel("schreibhilfe-windows", 10), rel("begleiter-windows", 10)]),
                         ["schreibhilfe-windows"])

    def test_drafts_prereleases_and_odd_tags_untouched(self):
        rs = [rel("fw-2.5.1.6", 11, draft=True), rel("fw-2.5.1.7", 12, prerelease=True), rel("fw-2.5.1.5", 8),
              rel("-x", 1), rel("--yes", 1), rel("a b", 1), {"tag_name": "fw-1.0", "published_at": None}]
        self.assertEqual(self.m.plan(rs), [])

    def test_workflow_runs_only_after_success_and_never_on_untrusted_input(self):
        with open(WF) as f:
            wf = f.read()
        self.assertIn("github.event.workflow_run.conclusion == 'success'", wf)
        self.assertIn("branches: [main]", wf)
        self.assertNotIn("github.event.workflow_run.head", wf)  # no branch/commit text of the run in the script
        self.assertIn("contents: read", wf.split("jobs:")[0])
