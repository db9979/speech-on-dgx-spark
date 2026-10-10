"""TestFlight gate (V01.0.321): only a commit with passed Tests goes up. A run cancelled by a newer
push may be replaced by the newest green main commit, but only one that contains the iOS commit;
failed Tests still stop. (The workflow is not in an app/-only copy, then this is skipped.)"""
import importlib.util
import os
import unittest
from unittest import mock

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


    def test_revokes_only_its_own_certificates(self):
        i = self.wf.index("Revoke this run's certificates")
        step = self.wf[i:self.wf.index("- name: Clean up", i)]
        self.assertIn("if: always()", step)
        self.assertIn('asc_certs.py "$RUNNER_TEMP/signing.keychain-db"', step)
        self.assertLess(i, self.wf.index("security delete-keychain"))


class RevokeOwnCertificates(unittest.TestCase):
    """V01.0.330: the cleanup revokes only certificates whose serial is in the run's own keychain."""

    def setUp(self):
        path = os.path.join(ROOT, "ios", "ci", "asc_certs.py")
        if not os.path.exists(path):
            self.skipTest("ios/ is not in an app/-only copy")
        spec = importlib.util.spec_from_file_location("asc_certs", path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_only_matching_serials(self):
        listed = {"data": [{"id": "AAA1", "attributes": {"serialNumber": "0A1B", "name": "mine"}},
                           {"id": "BBB2", "attributes": {"serialNumber": "77FF", "name": "Dominik's Mac"}},
                           {"id": "../x", "attributes": {"serialNumber": "C0DE", "name": "odd id"}}]}
        calls = []

        def call(method, url, tok):
            calls.append((method, url))
            return listed if method == "GET" else {}
        with mock.patch.object(self.m, "own_serials", return_value={"A1B", "C0DE"}), \
                mock.patch.object(self.m, "token", return_value="t"), mock.patch.object(self.m, "call", call), \
                mock.patch.object(self.m.sys, "argv", ["x", "kc", "p8"]):
            self.assertEqual(self.m.main(), 0)
        deleted = [u for meth, u in calls if meth == "DELETE"]
        self.assertEqual(deleted, [self.m.API + "/AAA1"])

    def test_nothing_without_own_certificates(self):
        with mock.patch.object(self.m, "own_serials", return_value=set()), \
                mock.patch.object(self.m, "call", side_effect=AssertionError("no API call")), \
                mock.patch.object(self.m.sys, "argv", ["x", "kc", "p8"]):
            self.assertEqual(self.m.main(), 0)

    def test_signature_to_raw(self):
        der = bytes([0x30, 0x45, 0x02, 0x21, 0x00]) + b"\x81" * 32 + bytes([0x02, 0x20]) + b"\x02" * 32
        self.assertEqual(self.m.der_to_raw(der), b"\x81" * 32 + b"\x02" * 32)


if __name__ == "__main__":
    unittest.main()
