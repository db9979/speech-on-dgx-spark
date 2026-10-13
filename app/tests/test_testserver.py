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


class PortsStayReserved(unittest.TestCase):
    """helpers._port() keeps its port until the server for it starts; a busy port fails at once (run of V01.0.489:
    a fake server's port was taken on the runner and every test waited 60 s for it until the 45 min cut-off)."""

    def test_a_reserved_port_cannot_be_taken_and_refuses_until_served(self):
        port = helpers._port()
        other = socket.socket()
        try:
            with self.assertRaises(OSError):
                other.bind(("127.0.0.1", port))
        finally:
            other.close()
        self.assertFalse(reachable(port))            # like a dead port until a server uses it
        from fastapi import FastAPI
        stop = helpers._serve(FastAPI(), port)
        try:
            self.assertTrue(reachable(port))
        finally:
            stop()

    def test_a_busy_port_fails_at_once(self):
        import time
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        try:
            from fastapi import FastAPI
            t = time.monotonic()
            with self.assertRaises(RuntimeError) as e:
                helpers._serve(FastAPI(), busy.getsockname()[1])
            self.assertLess(time.monotonic() - t, 10)
            self.assertIn("busy", str(e.exception))
        finally:
            busy.close()


if __name__ == "__main__":
    unittest.main()
