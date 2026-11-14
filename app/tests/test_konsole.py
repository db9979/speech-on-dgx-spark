"""Spark-Konsole (plan spark-entkoppeln E4, Dominik 2026-11-14 „Beides“): the panel's code as the model computer's own
page. The protection rules, each with its test:

- off by default (konsole.an); only root switches it on, and only with networks of the home network (private, not
  wider than /8), never without one;
- the console process answers only this machine and konsole.netze, and only the paths of konsole.WEGE: everything
  else (the assistant, profiles, tools) is 404 before a route reads the request; the panel without the console mode
  is unchanged;
- "/" is the console's own page, the rest needs the panel's login (401) and its codes;
- of the panel's background work only the sampler starts; the door's firewall lets the console's port in only from
  konsole.netze;
- every switch writes a journal line with fixed words and numbers.
Nothing depends on the time of day."""
import io
import re
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fastapi.testclient import TestClient

from tests import helpers

helpers.start()
import panel  # noqa: E402
import common  # noqa: E402
import core  # noqa: E402
import konsole  # noqa: E402
import teilen  # noqa: E402


def setze(**kw):
    with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
        c = json.load(f)
    c["konsole"] = dict(c.get("konsole") or {}, **kw)
    helpers.write_config(c)


class Base(unittest.TestCase):
    def setUp(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        self.before_k, self.before_api = c.get("konsole"), c.get("api")
        self.addCleanup(self.back)

    def back(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["konsole"], c["api"] = self.before_k, self.before_api
        helpers.write_config(c)


class Schalter(Base):
    def test_off_by_default_and_only_home_networks(self):
        with open(os.path.join(os.path.dirname(konsole.__file__), "config.default.json")) as f:
            d = json.load(f)
        self.assertEqual(d["konsole"], {"an": False, "port": konsole.PORT, "netze": []})
        self.assertFalse(konsole.an())
        self.assertTrue(konsole.erlaubt("127.0.0.1"))
        self.assertFalse(konsole.erlaubt("192.168.178.30"))
        for bad in (["8.8.8.0/24"], ["0.0.0.0/0"], ["10.0.0.0/7"], ["127.0.0.0/8"], ["kein netz"], []):
            with self.assertRaises(konsole.Fehler, msg=bad):
                konsole.schalten(True, bad)
        with redirect_stdout(io.StringIO()) as out:
            z = konsole.schalten(True, ["192.168.178.7/24"])
        self.assertEqual(z, {"an": True, "netze": ["192.168.178.0/24"], "port": konsole.PORT})
        self.assertIn("konsole: root an netze 1", out.getvalue())
        self.assertTrue(konsole.erlaubt("192.168.178.30"))
        self.assertTrue(konsole.erlaubt("::ffff:192.168.178.30"))
        self.assertFalse(konsole.erlaubt("192.168.10.5"))
        self.assertFalse(konsole.erlaubt("testclient"))
        with redirect_stdout(io.StringIO()) as out:
            konsole.schalten(False, [])
        self.assertFalse(konsole.erlaubt("192.168.178.30"))
        self.assertIn("konsole: root aus netze 0", out.getvalue())

    def test_port_only_below_31100(self):
        setze(port=8080)
        self.assertEqual(konsole.port(), 8080)
        setze(port=40000)
        self.assertEqual(konsole.port(), konsole.PORT)
        setze(port=True)
        self.assertEqual(konsole.port(), konsole.PORT)

    def test_only_its_own_paths(self):
        for ok in ("/", "/static/konsole.css", "/static/js/konsole.js", "/api/login", "/api/status", "/api/logs/llm",
                   "/api/update", "/api/update/progress", "/api/admin/spark-clients/neu", "/api/admin/modelle",
                   "/api/konsole/koppeln"):
            self.assertTrue(konsole.weg_ok(ok), ok)
        for bad in ("/api/chat", "/api/profile/login", "/api/updatexyz", "/api/admin/config", "/mcp",
                    "/api/statusx", "/v1/chat/completions", "/api/admin/spark-clientsx", "/api/admin/modellex",
                    "/api/konsolex"):
            self.assertFalse(konsole.weg_ok(bad), bad)


class Seite(Base):
    def test_the_console_process_answers_only_its_paths_and_networks(self):
        c = TestClient(panel.app)
        with mock.patch.object(panel, "KONSOLE", True), mock.patch.object(panel.konsole, "erlaubt", lambda h, cfg=None: True):
            r = c.get("/")
            self.assertEqual(r.status_code, 200)
            self.assertIn("Spark-Konsole", r.text)
            self.assertIn("/static/js/konsole.js?v=", r.text)
            self.assertEqual(c.get("/api/chat/history").status_code, 404)
            self.assertEqual(c.post("/api/chat", json={"text": "hallo"}).status_code, 404)
            self.assertEqual(c.get("/api/status").status_code, 401)
            self.assertEqual(c.get("/static/konsole.css").status_code, 200)
            self.assertIn("default-src 'self'", c.get("/api/chat/history").headers.get("content-security-policy", ""))
        with mock.patch.object(panel, "KONSOLE", True):
            self.assertEqual(c.get("/").status_code, 404)   # the test client is no address of the home network
        panel._PAGE.clear()
        r = c.get("/")
        self.assertNotIn("konsole.js", r.text)   # the panel itself is unchanged
        self.assertNotEqual(c.get("/api/whoami").status_code, 404)

    def test_clients_page_is_open_in_the_console(self):
        import sparkclients
        with mock.patch.object(sparkclients.features, "admin_on", lambda k, c=None: False):
            self.assertFalse(sparkclients.admin_on())
            with mock.patch.dict(os.environ, {konsole.ENV: "1"}):
                self.assertTrue(sparkclients.admin_on())

    def test_only_the_sampler_starts(self):
        names = {getattr(f, "__name__", "") for f in panel.app.router.on_startup}
        for n in panel.KONSOLE_START:
            self.assertIn(n, names)
        self.assertGreater(len(names), len(panel.KONSOLE_START))

    def test_page_names_only_files_that_exist(self):
        static = os.path.join(os.path.dirname(panel.__file__), "static")
        with open(os.path.join(static, "konsole.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("<script>", html)          # strict CSP: scripts only as files
        self.assertNotIn("onclick=", html)
        for f in ("konsole.css", "js/konsole.js", "favicon-32.png"):
            self.assertIn("/static/" + f, html)
            self.assertTrue(os.path.exists(os.path.join(static, f)), f)
        with open(os.path.join(static, "js", "konsole.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("const esc=", js)
        for path in ("/api/status", "/api/admin/spark-clients", "/api/update", "/api/logs/", "/api/login", "/api/whoami",
                     "/api/admin/modelle", "/api/konsole/koppeln"):
            self.assertIn(path, js)
            self.assertTrue(konsole.weg_ok(path.rstrip("/") + ("/x" if path.endswith("/") else "")), path)
        for name in re.search(r"const LOGS=\[([^\]]*)\]", js).group(1).replace("'", "").split(","):
            self.assertIn(name, core.LOG_UNITS)


class Koppeln(Base):
    """Assistent koppeln (E4b): root's unit shows the code; the console reads it only while it lives."""
    def test_code_only_while_it_lives_and_only_checked_shapes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "koppelcode.json")
            self.assertEqual(konsole.koppeln_stand(1000, p), {})
            f = ":".join(["AB"] * 32)
            teilen.konsole_schreiben({"code": "ABC-DEF", "bis": 1600, "fingerabdruck": f}, p)
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
            self.assertEqual(konsole.koppeln_stand(1000, p), {"code": "ABC-DEF", "bis": 1600, "rest": 600, "fingerabdruck": f})
            self.assertEqual(konsole.koppeln_stand(1600, p), {})
            teilen.konsole_schreiben({"code": "<b>x</b>", "bis": 1600}, p)
            self.assertEqual(konsole.koppeln_stand(1000, p), {})
            teilen.konsole_schreiben({"stand": "gekoppelt", "t": 1000}, p)
            self.assertEqual(konsole.koppeln_stand(1100, p), {"stand": "gekoppelt", "t": 1000})
            self.assertEqual(konsole.koppeln_stand(1000 + konsole.KOPPEL_ZEIGEN, p), {})
            teilen.konsole_schreiben({"stand": "irgendwas", "t": 1000}, p)
            self.assertEqual(konsole.koppeln_stand(1100, p), {})

    def test_only_in_the_console_and_only_with_login(self):
        c = TestClient(panel.app)
        self.assertEqual(c.get("/api/konsole/koppeln").status_code, 404)   # the panel itself has no such page
        with mock.patch.object(panel, "KONSOLE", True), mock.patch.object(panel.konsole, "erlaubt", lambda h, cfg=None: True):
            self.assertEqual(c.get("/api/konsole/koppeln").status_code, 401)
            self.assertEqual(c.post("/api/konsole/koppeln", json={}).status_code, 401)

    def test_start_is_the_fixed_unit_and_logs(self):
        seen = []
        with mock.patch.object(konsole.subprocess, "run", lambda a, **k: seen.append(a) or mock.Mock(returncode=0)), \
                redirect_stdout(io.StringIO()) as out:
            self.assertTrue(konsole.koppeln_starten())
        self.assertEqual(seen, [["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", konsole.KOPPEL_UNIT]])
        self.assertIn("konsole: koppeln gestartet", out.getvalue())
        with mock.patch.object(konsole.subprocess, "run", side_effect=OSError), redirect_stdout(io.StringIO()) as out:
            self.assertFalse(konsole.koppeln_starten())
        self.assertIn("konsole: koppeln fehler", out.getvalue())


class Firewall(Base):
    def test_door_rules_let_the_console_in_only_from_its_networks(self):
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            c = json.load(f)
        c["api"] = dict(c.get("api") or {}, tls_listen="192.168.178.171", tls_from=["192.168.178.20"])
        helpers.write_config(c)
        self.assertNotIn(str(konsole.PORT), teilen.regeln(common.load_config()))
        setze(an=True, netze=["192.168.178.0/24"])
        r = teilen.regeln(common.load_config())
        self.assertIn(f"ip saddr {{ 192.168.178.0/24 }} tcp dport {konsole.PORT} accept", r)
        self.assertIn(f"tcp dport {konsole.PORT} drop", r)
        self.assertLess(r.index(f"tcp dport {konsole.PORT} accept"), r.index(f"tcp dport {konsole.PORT} drop"))

    def test_unit_and_command(self):
        try:
            sh = helpers.repo_file("install.sh")
        except unittest.SkipTest:
            sh = ""   # the copy with only app/
        if sh:
            self.assertIn("Environment=SPEECH_SPARK_KONSOLE=1", sh)
            self.assertIn("systemctl disable --now speech-spark-konsole.service", sh)
            self.assertIn("ExecStart=/bin/bash $PREFIX/app/speech-spark.sh teilen code --konsole", sh)
            self.assertIn(f"/usr/bin/systemctl start --no-block {konsole.KOPPEL_UNIT}'", sh)
        with open(os.path.join(os.path.dirname(konsole.__file__), "speech-spark.sh"), encoding="utf-8") as f:
            cli = f.read()
        self.assertIn('konsole) shift; need_root konsole "$@"; cmd_konsole "$@" ;;', cli)
        self.assertIn('--konsole) k=1 ;;', cli)
        self.assertIn('TEILEN_KONSOLE="${TEILEN_KONSOLE:-0}"', cli)


if __name__ == "__main__":
    unittest.main()
