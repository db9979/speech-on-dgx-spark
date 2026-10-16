"""Terminal-Client (terminal.py, tui/spark-tui.py): off by default, pairing with a setup line (pinned at home,
checked as usual through an outside address), the key's narrow scope (terminal.TUI_RULES), the agent's pages only
for it, Live counts, log lines, and the program's own checks (line, pin, no plain http). No test reads the clock."""
import hashlib
import importlib.util
import json
import os
import unittest

from tests import helpers

helpers.start()
import guard  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import terminal  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
HOME = "https://tars:31443"
FP = "ab" * 32


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in profiles.names() if u["name"] == name)


def paired(client, origin="https://tars:31443"):
    """(test client, headers) of a terminal paired by the profile behind client."""
    setup = client.post("/api/profile/terminal/pair", json={"origin": origin}).json()["setup"]
    code = setup.split("#tui=")[1].split("&")[0]
    app = TestClient(panel.app)
    r = app.post("/api/tui/pair", json={"code": code, "name": "uConsole"})
    assert r.status_code == 200, r.text
    return app, {"X-Speech-Device": r.json()["key"]}


def program():
    spec = importlib.util.spec_from_file_location("spark_tui", terminal.PROGRAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Terminal(unittest.TestCase):
    def setUp(self):
        helpers.set_config(terminal=True, deny={}, public=False)   # public on (left by another test) opens settings and chat to anyone
        terminal._codes.pending.clear()
        self._fp = terminal.cert_sha256
        terminal.cert_sha256 = lambda: FP   # the test panel has no certificate of its own
        for k in [k for k in guard._rate if k[0] == "pair"]:   # every test client shares one address
            guard._rate.pop(k, None)

    def tearDown(self):
        terminal.cert_sha256 = self._fp
        helpers.set_config(terminal=False, deny={})

    def test_off_by_default_and_no_profile_switch(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["terminal"], False)
        self.assertNotIn("terminal_on", profiles.SETTINGS)
        a = profile("Tara")
        helpers.set_config(terminal=False)
        self.assertEqual(a.post("/api/profile/terminal/pair", json={"origin": HOME}).status_code, 403)
        helpers.set_config(terminal=True, deny={"terminal": [uid_of("Tara")]})   # the admin blocks this profile
        self.assertEqual(a.post("/api/profile/terminal/pair", json={"origin": HOME}).status_code, 403)

    def test_never_for_guests(self):
        self.assertIn(TestClient(panel.app).post("/api/profile/terminal/pair", json={"origin": HOME}).status_code, (401, 403))
        self.assertEqual(TestClient(panel.app).get("/api/tui/hello").status_code, 401)

    def test_setup_line_pins_at_home_and_not_outside(self):
        a = profile("Theo")
        r = a.post("/api/profile/terminal/pair", json={"origin": "http://tars:31080"}).json()
        self.assertRegex(r["setup"], r"^https://tars:31443#tui=[A-Za-z0-9_\-]{20,40}&fp=" + FP + "$")
        self.assertTrue(r["pinned"])
        r = a.post("/api/profile/terminal/pair", json={"origin": "https://spark.example.org"}).json()
        self.assertRegex(r["setup"], r"^https://spark\.example\.org#tui=[A-Za-z0-9_\-]{20,40}$")   # nothing pinned outside
        self.assertFalse(r["pinned"])
        self.assertEqual(a.post("/api/profile/terminal/pair", json={"origin": "http://spark.example.org"}).status_code, 409)
        for bad in ("tars", "https://tars/panel", "javascript:alert(1)", "https://a b", ""):
            self.assertEqual(a.post("/api/profile/terminal/pair", json={"origin": bad}).status_code, 400, bad)
        self.assertEqual(a.post("/api/profile/terminal/pair", content="x" * 2000).status_code, 413)
        terminal.cert_sha256 = lambda: ""   # no certificate at home: no line, never plain http
        self.assertEqual(a.post("/api/profile/terminal/pair", json={"origin": "http://tars:31080"}).status_code, 409)

    def test_pairing_works_once_and_keeps_only_the_hash(self):
        a = profile("Tilo")
        setup = a.post("/api/profile/terminal/pair", json={"origin": HOME}).json()["setup"]
        code = setup.split("#tui=")[1].split("&")[0]
        app = TestClient(panel.app)
        r = app.post("/api/tui/pair", json={"code": code, "name": "uConsole"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(app.post("/api/tui/pair", json={"code": code}).status_code, 400)
        self.assertNotIn(r.json()["key"], json.dumps(profiles._load()))
        items = a.get("/api/profile/terminal").json()["devices"]
        self.assertEqual([x["name"] for x in items], ["Terminal · uConsole"])
        dev = next(x for x in ADMIN.get("/api/admin/profiles").json()["devices"] if x["user"] == uid_of("Tilo"))
        self.assertEqual(dev["kind"], "tui")
        self.assertEqual(ADMIN.put(f"/api/admin/devices/{dev['id']}", json={"user": uid_of("Tilo")}).status_code, 400)

    def test_code_expires(self):
        profile("Tina")
        uid = uid_of("Tina")
        code = terminal._codes.new(uid, now=1000.0)
        self.assertIsNone(terminal._codes.take(code, now=1000.0 + terminal.CODE_SECONDS + 1))
        code = terminal._codes.new(uid, now=2000.0)
        self.assertEqual(terminal._codes.take(code, now=2010.0), uid)
        self.assertIsNone(terminal._codes.take("../" * 10))

    def test_key_reaches_only_the_terminal_paths(self):
        a = profile("Toni")
        app, h = paired(a)
        hello = app.get("/api/tui/hello", headers=h).json()
        self.assertEqual(hello["sha256"], terminal.program()["sha256"])   # what "spark-tui update" checks against
        self.assertEqual(app.get("/api/profile/convos", headers=h).status_code, 200)
        self.assertEqual(app.get("/api/profile/today", headers=h).status_code, 200)
        r = app.post("/api/chat", json={"messages": [{"role": "user", "content": "Hallo"}], "speak": False}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(any(e.get("type") == "done" for e in helpers.events(r)))
        # nothing else: settings, security, devices, pairing, memory, the admin's pages
        for method, path in (("GET", "/api/profile/settings"), ("GET", "/api/profile/memory"), ("GET", "/api/profile/terminal"),
                             ("POST", "/api/profile/terminal/pair"), ("GET", "/api/profile/mfa/passkeys"),
                             ("GET", "/api/admin/profiles"), ("POST", "/api/siri/ask"), ("GET", "/api/watch/poll"),
                             ("DELETE", "/api/profile/memory"), ("GET", "/api/profile/convos/stream")):
            self.assertIn(app.request(method, path, json={}, headers=h).status_code, (401, 403), path)
        # off or blocked: "not now" (503), the pairing stays and works again once released
        helpers.set_config(deny={"terminal": [uid_of("Toni")]})
        self.assertEqual(app.get("/api/tui/hello", headers=h).status_code, 503)
        helpers.set_config(deny={})
        self.assertEqual(app.get("/api/tui/hello", headers=h).status_code, 200)
        helpers.set_config(terminal=False)
        self.assertEqual(app.post("/api/chat", json={"messages": [{"role": "user", "content": "Hi"}]}, headers=h).status_code, 503)

    def test_agent_pages_only_through_its_rules(self):
        a = profile("Tom")
        app, h = paired(a)
        helpers.set_config(agent=True)
        try:
            # the agent's pages want the browser login: the terminal's key counts like it there and only there
            self.assertEqual(app.get("/api/profile/agent", headers=h).status_code, 200)
        finally:
            helpers.set_config(agent=False)
        self.assertIn(app.put("/api/profile/agent/mail", json={}, headers=h).status_code, (401, 403))
        self.assertIn(app.post("/api/profile/agent/routines", json={}, headers=h).status_code, (401, 403))
        self.assertEqual(terminal.reaches(type("R", (), {"scope": {"path": "/api/profile/agent"}, "method": "GET"})()), "agent")
        self.assertEqual(terminal.reaches(type("R", (), {"scope": {"path": "/api/chat"}, "method": "POST"})()), "panel")
        self.assertIsNone(terminal.reaches(type("R", (), {"scope": {"path": "/api/chat"}, "method": "GET"})()))

    def test_remove_stops_the_key_and_live_counts(self):
        a = profile("Tessa")
        app, h = paired(a)
        terminal._seen.clear()
        self.assertEqual(app.get("/api/tui/hello", headers=h).status_code, 200)
        self.assertEqual(terminal.online(), 1)
        self.assertTrue(any(c["name"] == "Terminal-Client" and c["n"] == 1 for c in live._conns(__import__("time").time())))
        self.assertEqual(terminal.online(now=next(iter(terminal._seen.values())) + terminal.SEEN_SECONDS + 1), 0)
        did = a.get("/api/profile/terminal").json()["devices"][0]["id"]
        self.assertEqual(TestClient(panel.app).delete(f"/api/profile/terminal/{did}", headers=h).status_code, 401)
        self.assertEqual(a.delete(f"/api/profile/terminal/{did}").status_code, 200)
        self.assertEqual(app.get("/api/tui/hello", headers=h).status_code, 401)
        self.assertEqual(a.delete(f"/api/profile/terminal/{did}").status_code, 404)

    def test_trace_and_conversation_kind(self):
        import tracelog
        import verlauf
        self.assertIn("tui", tracelog.CLIENTS)
        self.assertEqual(live.CLIENT["tui"], "Terminal")
        self.assertEqual(verlauf.KINDS["tui"], "Terminal")

    def test_program_file_is_served_with_its_checksum(self):
        a = profile("Tjark")
        info = a.get("/api/profile/terminal").json()["program"]
        r = TestClient(panel.app).get("/tui/spark-tui.py")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(hashlib.sha256(r.content).hexdigest(), info["sha256"])
        self.assertEqual(info["version"], program().VERSION)


class Program(unittest.TestCase):
    """spark-tui itself: the pairing line, https only, the pin checked before anything is sent."""

    def test_line(self):
        p = program()
        self.assertTrue(p.LINE.fullmatch("https://tars:31443#tui=" + "A" * 24 + "&fp=" + FP))
        self.assertTrue(p.LINE.fullmatch("https://spark.example.org#tui=" + "A" * 24))
        for bad in ("http://tars:31080#tui=" + "A" * 24, "https://tars#tui=short", "https://tars#tui=" + "A" * 24 + "&fp=zz"):
            self.assertIsNone(p.LINE.fullmatch(bad), bad)
        self.assertIsNone(p.URL.fullmatch("http://spark.example.org"))

    def test_fetch_line_checks_the_sum_before_it_installs(self):
        # V01.0.661: Ich → Terminal installs the command spark-tui only after sha256sum -c with the page's value
        with open(os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js", "extras.js")) as f:
            js = f.read()
        line = js[js.index("get=`curl"):js.index(";", js.index("get=`curl"))]
        self.assertIn("sha256sum -c && install -Dm755 spark-tui.py ~/.local/bin/spark-tui", line)
        self.assertLess(line.index("sha256sum -c"), line.index("install "))
        self.assertIn("~/.local/bin/spark-tui koppeln", js)

    def test_window_uses_its_own_textual_environment(self):
        # V01.0.661: Debian refuses pip outside a venv; without Textual the window restarts in spark-tui's own one
        import sys
        import tempfile
        p = program()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "bin"))
            py = os.path.join(d, "bin", "python3")
            open(py, "w").close()
            calls = []
            old = (p.VENV, p.need, p.os.execv, sys.modules.get("textual.app"))
            p.VENV, p.need = d, lambda: {"key": "k", "urls": []}
            p.os.execv = lambda exe, argv: calls.append((exe, argv)) or (_ for _ in ()).throw(SystemExit(0))
            sys.modules["textual.app"] = None   # import fails as without Textual
            try:
                with self.assertRaises(SystemExit):
                    p.cmd_window(None)
            finally:
                p.VENV, p.need, p.os.execv = old[:3]
                if old[3] is None:
                    sys.modules.pop("textual.app", None)
                else:
                    sys.modules["textual.app"] = old[3]
        self.assertEqual(calls[0][0], py)

    def test_update_keeps_only_the_named_sum(self):
        # spark-tui update: the file from the Spark replaces the program only when its SHA-256 is the one hello names
        import tempfile
        p = program()
        new = b"#!/usr/bin/env python3\nVERSION = \"9.9.9\"\n"

        class R:
            def __init__(self, data):
                self.data = data

            def read(self, n):
                return self.data[:n]

        class C:
            def close(self):
                pass

        class Sp:
            def __init__(self, sha, data):
                self.sha, self.data, self.fetched = sha, data, 0

            def call(self, method, path, body=None):
                return {"program": "9.9.9", "sha256": self.sha}

            def open(self, method, path, body=None, **kw):
                self.fetched += 1
                return C(), R(self.data)
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "spark-tui")
            with open(target, "wb") as f:
                f.write(b"#!/usr/bin/env python3\nVERSION = \"1\"\n")
            bad = Sp(hashlib.sha256(new).hexdigest(), new + b"# changed on the way\n")
            with self.assertRaises(p.SparkError):
                p.update_file(bad, target)
            with open(target, "rb") as f:
                self.assertNotIn(b"9.9.9", f.read())   # nothing changed
            with self.assertRaises(p.SparkError):
                p.update_file(Sp("", new), target)   # no sum named: nothing fetched
            good = Sp(hashlib.sha256(new).hexdigest(), new)
            self.assertEqual(p.update_file(good, target), "9.9.9")
            with open(target, "rb") as f:
                self.assertEqual(f.read(), new)
            self.assertTrue(os.access(target, os.X_OK))
            self.assertEqual(p.update_file(good, target), "")   # already current: not fetched again
            self.assertEqual(good.fetched, 1)
            self.assertEqual(sorted(os.listdir(d)), ["spark-tui"])

    def test_wrong_pin_sends_nothing(self):
        p = program()
        sent = []

        class Conn:
            def __init__(self, *a, **k):
                self.sock = type("S", (), {"getpeercert": lambda s, binary_form=False: b"other certificate"})()

            def connect(self):
                pass

            def request(self, *a, **k):
                sent.append(a)

            def close(self):
                pass
        old = p.http.client.HTTPSConnection
        p.http.client.HTTPSConnection = Conn
        try:
            sp = p.Spark({"key": "sd_x", "urls": [{"url": "https://tars:31443", "fp": FP}]})
            with self.assertRaises(p.SparkError):
                sp.call("GET", "/api/tui/hello")
            self.assertEqual(sent, [])
            with self.assertRaises(p.SparkError):
                p.Spark({"key": "sd_x", "urls": [{"url": "http://tars:31080", "fp": ""}]}).call("GET", "/api/tui/hello")
            self.assertEqual(sent, [])
        finally:
            p.http.client.HTTPSConnection = old

    def test_answer_stream(self):
        p = program()

        class Resp:
            status = 200

            def __iter__(self):
                for ev in ({"type": "text", "delta": "Hallo "}, {"type": "text", "delta": "Welt!!"},
                           {"type": "retract", "drop": 2}, {"type": "done"}):
                    yield ("data: " + json.dumps(ev) + "\n").encode()

        sp = p.Spark({"key": "k", "urls": []})
        sp.open = lambda *a, **k: (type("C", (), {"close": lambda s: None})(), Resp())
        seen = []
        self.assertEqual(sp.ask([{"role": "user", "content": "Hi"}], on_text=seen.append), "Hallo Welt")
        self.assertEqual(seen[-1], "Hallo Welt")

    def test_device_file_only_for_the_owner(self):
        p = program()
        d = helpers.tmpdir() if hasattr(helpers, "tmpdir") else __import__("tempfile").mkdtemp()
        p.CONF = os.path.join(d, "spark-tui", "geraet.json")
        p.save({"key": "sd_x", "urls": [{"url": HOME, "fp": FP}]})
        self.assertEqual(os.stat(p.CONF).st_mode & 0o777, 0o600)
        self.assertEqual(p.load()["key"], "sd_x")


if __name__ == "__main__":
    unittest.main()
