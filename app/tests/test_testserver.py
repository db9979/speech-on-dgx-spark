"""The panel a browser test class serves is stopped again when the class is done (helpers.serve_panel).

Main was red after V01.0.473: nine browser classes each started the panel and never stopped it, so their
background loops (learning, tidying, document briefs, update checks) kept running for the rest of the run,
the panel got slower with every class (GET /api/whoami 29 s) and took the work later tests wait for
(test_wissen „brief“). No wall clock dependence; runs in a copy with only app/.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import glob
import os
import re
import socket
import unittest
import urllib.request

from tests import helpers

helpers.start()

TESTS = os.path.dirname(os.path.abspath(__file__))


def reachable(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


class OnePanelAtATime(unittest.TestCase):
    def test_no_class_serves_the_panel_without_stopping_it(self):
        bad = []
        for path in glob.glob(os.path.join(TESTS, "test_*.py")):
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if re.search(r"_serve\(\s*panel\.app", line):
                        bad.append(f"{os.path.basename(path)}:{n}")
        self.assertEqual(bad, [], "serve the panel with helpers.serve_panel(cls, port): it stops with the class")

    def test_the_panel_stops_with_its_class(self):
        class Probe(unittest.TestCase):
            def test_up(self):
                pass
        port = helpers._port()
        before = helpers.panels_running()
        stop = helpers.serve_panel(Probe, port)
        self.assertTrue(reachable(port))
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30) as r:
            self.assertEqual(r.status, 200)
        self.assertEqual(helpers.panels_running(), before + 1)
        Probe.doClassCleanups()           # what the runner does after the class
        self.assertFalse(reachable(port))
        self.assertEqual(helpers.panels_running(), before)
        stop()                            # a second stop does nothing
        self.assertEqual(helpers.panels_running(), before)


if __name__ == "__main__":
    unittest.main()
