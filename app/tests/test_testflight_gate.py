"""TestFlight gate (V01.0.317): only a commit with passed Tests goes up. A run cancelled by a newer
push may be replaced by the newest green main commit, but only one that contains the iOS commit;
failed Tests still stop. (The workflow is not in an app/-only copy, then this is skipped.)"""
import os
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
WF = os.path.join(ROOT, ".github", "workflows", "testflight.yml")


class TestFlightGate(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(WF):
            self.skipTest("the workflow is not in an app/-only copy")
        with open(WF) as f:
            self.wf = f.read()
        self.gate = self.wf[self.wf.index("  gate:"):self.wf.index("  upload:")]

    def test_own_green_tests_first(self):
        self.assertIn('[ "$st" = "completed:success" ] && break', self.gate)

    def test_cancelled_only_with_newer_green_commit_that_contains_it(self):
        i = self.gate.index('if [ "$st" = "completed:cancelled" ]; then')
        block = self.gate[i:self.gate.index("sleep 30; continue", i)]
        self.assertIn("status=success", block)
        self.assertIn("branch=main", block)
        self.assertIn("/compare/$SHA...$newer", block)
        self.assertIn('if [ "$rel" = "ahead" ]; then', block)
        self.assertIn("*[!0-9a-f]*", block)  # the commit id from the API is checked before use

    def test_failed_tests_still_stop(self):
        self.assertRegex(self.gate, r'\[ "\$\{st%%:\*\}" = "completed" \]; then\s+echo "::error::')
        self.assertIn('|| { echo "::error::Tests did not finish in time"; exit 1; }', self.gate)

    def test_upload_builds_the_gate_commit(self):
        self.assertIn("ref: ${{ needs.gate.outputs.sha }}", self.wf)


if __name__ == "__main__":
    unittest.main()
