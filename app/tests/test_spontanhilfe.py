"""Spontanhilfe (spontanhilfe.py, plan spontanhilfe S1): one self-test for every protection rule. Off by default and
404 while off; only admins in their browser with a second step help, only on the unlocked Fernzugang page (locked:
423, GET says only that it is on), a fresh code for „Verlängern“ every time; the number works once, 10 minutes, dies after 5 wrong tries and every wrong try gets the same
answer; the link key works once and never reaches a log; the page's own strict CSP and screen sharing only there;
both sockets check Origin themselves, the person's key only in its first message, the admin's ticket once and bound
to the login; only fixed message kinds pass, checked for form and size; the clock warns and ends, „Verlängern“ never
past the setting; the Notaus ends it; Live without an address and names only with live_names; the history without a
name; a fixed invitation and a fixed push; logs in fixed words only. S3 Shell: one line without sudo and never a
number in it; the program's socket refuses any Origin, checks number and name like the page; no byte passes before her
„j“ (her „n“ ends it); the real anchor program runs her shell in a PTY, never as root, and leaves nothing behind. No
test depends on the time of day."""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import re
import ssl
import tempfile
import threading
import time
import types
import unittest
import unittest.mock

from tests import helpers

helpers.start()
import fernzugang  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import mfa  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import spontanhilfe as sh  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
OTHER = TestClient(panel.app)
OTHER.post("/api/login", json={"password": "secret-admin"})
OUT = "https://spark.example.org"
CODE = {"x-speech-code": "123456"}
PERSON = TestClient(panel.app)       # no login at all


def program():
    """The anchor program (app/anker/spark-anker.py) as a module, like `curl … | python3 -` runs it."""
    spec = importlib.util.spec_from_file_location("spark_anker", fernzugang.PROGRAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def until(test, s=10):
    for _ in range(int(s * 20)):
        if test():
            return True
        time.sleep(0.05)
    return False


@contextlib.contextmanager
def journal():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def reset():
    sh.HILFE.clear()
    sh.TICKETS.clear()
    fernzugang.ENTSPERRT.clear()
    sh.STATS.update(heute="", hilfen=0, falsch=0)
    with contextlib.suppress(OSError):
        os.remove(sh.VERLAUF)
    for k in [k for k in guard._rate if str(k[0]).startswith(("spontanhilfe", "fernzugang"))]:
        guard._rate.pop(k, None)
    guard.reset()


class Base(unittest.TestCase):
    def setUp(self):
        self.real = (mfa.enabled, mfa.verify)
        mfa.enabled = lambda who: who == mfa.ADMIN
        mfa.verify = lambda who, code: who == mfa.ADMIN and code == "123456"
        helpers.set_config(fernzugang=True, spontanhilfe=True, spontanhilfe_max_min=180, public=False, deny={})
        reset()
        self.unlock()

    def unlock(self, client=None):
        """The page Fernzugang unlocked (rule „Bereich entsperren“): Spontanhilfe is one of its tabs."""
        r = (client or ADMIN).post("/api/admin/fernzugang/entsperren", headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)

    def tearDown(self):
        mfa.enabled, mfa.verify = self.real
        helpers.set_config(spontanhilfe=False)
        if notaus.level():
            notaus._set(0, "test") if hasattr(notaus, "_set") else None
        reset()

    def new(self):
        r = ADMIN.post("/api/admin/spontanhilfe/neu", json={"origin": OUT})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def start(self, **body):
        return PERSON.post("/api/hilfe/start", json={"name": "Helga", **body})


class Door(Base):
    def test_off_by_default_and_404_while_off(self):
        import features
        self.assertNotIn("chat.spontanhilfe", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["spontanhilfe"].parent, "fernzugang")
        helpers.set_config(spontanhilfe=False)
        self.assertEqual(PERSON.get("/hilfe").status_code, 404)
        self.assertEqual(PERSON.post("/api/hilfe/start", json={"nummer": "123456", "name": "A"}).status_code, 404)
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/neu", json={}, headers=CODE).status_code, 404)
        helpers.set_config(spontanhilfe=True, fernzugang=False)          # the parent switch off: off too
        self.assertEqual(PERSON.get("/hilfe").status_code, 404)

    def test_page_has_its_own_strict_csp_and_screen_sharing_only_there(self):
        r = PERSON.get("/hilfe")
        self.assertEqual(r.status_code, 200)
        csp = r.headers["content-security-policy"]
        for part in ("default-src 'none'", "script-src 'self'", "frame-ancestors 'none'", "base-uri 'none'"):
            self.assertIn(part, csp)
        self.assertNotIn("unsafe", csp)
        self.assertIn("display-capture=(self)", r.headers["permissions-policy"])
        self.assertNotIn("<script>", r.text)                              # no inline script
        self.assertNotIn("display-capture", PERSON.get("/").headers.get("permissions-policy", ""))
        self.assertNotIn("display-capture", panel.SECURITY_HEADERS["Permissions-Policy"])
        js = PERSON.get("/static/js/spontanhilfe-seite.js").text
        self.assertNotIn("innerHTML", js)                                 # what the panel sends is shown as text only
        self.assertIn("history.replaceState", js)                         # the link key leaves the address bar

    def test_only_an_admin_on_the_unlocked_page_with_a_second_step(self):
        fernzugang.ENTSPERRT.clear()                                      # locked: no number, also with a code
        for path in ("/api/admin/spontanhilfe/neu", "/api/admin/spontanhilfe/annehmen", "/api/admin/spontanhilfe/verlaengern",
                     "/api/admin/spontanhilfe/einladung"):
            self.assertEqual(ADMIN.post(path, json={"origin": OUT}, headers=CODE).status_code, 423, path)
        self.assertEqual(ADMIN.request("DELETE", "/api/admin/spontanhilfe/verlauf", headers=CODE).status_code, 423)
        self.unlock(OTHER)                                                # another login unlocked: still locked here
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/neu", json={"origin": OUT}).status_code, 423)
        self.unlock()
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/neu", json={"origin": OUT}).status_code, 200)   # no new code
        self.assertIn(PERSON.post("/api/admin/spontanhilfe/neu", json={"origin": OUT}, headers=CODE).status_code, (401, 403))
        mfa.enabled = lambda who: False
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/neu", json={"origin": OUT}, headers=CODE).status_code, 403)
        import stufen
        self.assertEqual(stufen.LIST[("POST", "/api/admin/spontanhilfe/verlaengern")][0], stufen.PROTECT)   # a fresh code every time
        self.assertEqual(stufen.LIST[("POST", "/api/admin/fernzugang/entsperren")][0], stufen.PROTECT)
        for path in ("/api/admin/spontanhilfe/neu", "/api/admin/spontanhilfe/annehmen"):
            self.assertNotIn(("POST", path), stufen.LIST)                 # the unlock was their code
        self.assertEqual(stufen.LIST[("DELETE", "/api/admin/spontanhilfe/verlauf")][0], stufen.CONFIRM)

    def test_locked_page_tells_only_that_it_is_on(self):
        self.new()
        fernzugang.ENTSPERRT.clear()
        d = ADMIN.get("/api/admin/spontanhilfe").json()
        self.assertEqual(set(d), {"on", "gesperrt", "notaus"})
        self.assertTrue(d["gesperrt"])

    def test_the_person_is_no_profile_and_gets_no_tool(self):
        import werkzeug_abdeckung
        self.assertIn("spontanhilfe", werkzeug_abdeckung.WITHOUT)
        with open(sh.__file__, encoding="utf-8") as f:
            src = f.read()
        for word in ("llm.", "chat.run", "tools", "profiles.current("):
            self.assertNotIn(word, src)


class Number(Base):
    def test_six_digits_once_and_the_same_answer_for_every_wrong_try(self):
        d = self.new()
        self.assertRegex(d["nummer"], r"^\d{6}$")
        self.assertRegex(d["link"], r"^https://spark\.example\.org/hilfe#[A-Za-z0-9_\-]{20,30}$")
        wrong = str((int(d["nummer"]) + 1) % 10**6).zfill(6)
        answers = {self.start(nummer=wrong).json()["detail"], self.start(nummer="12").json()["detail"]}
        r = self.start(nummer=d["nummer"])
        self.assertEqual(r.status_code, 200)
        self.assertRegex(r.json()["tok"], r"^[A-Za-z0-9_\-]{30,60}$")
        answers.add(self.start(nummer=d["nummer"]).json()["detail"])                 # used
        self.assertEqual(answers, {"Nummer nicht gültig"})
        self.assertEqual(sh.current().stand, "wartet")

    def test_dead_after_five_wrong_tries_and_noted_without_a_name(self):
        d = self.new()
        wrong = str((int(d["nummer"]) + 1) % 10**6).zfill(6)
        with journal() as j:
            for _ in range(sh.FEHL):
                self.assertEqual(self.start(nummer=wrong).status_code, 403)
        self.assertIsNone(sh.current())
        self.assertEqual(self.start(nummer=d["nummer"]).status_code, 403)
        self.assertIn("spontanhilfe: nummer_tot | fehlversuche | 5", j.getvalue())
        self.assertEqual(sh.verlauf_read()[0]["art"], "nummer_gesperrt")

    def test_expires_after_ten_minutes_the_link_after_thirty(self):
        d = self.new()
        later = time.time() + sh.NUMMER_S + 1
        with unittest.mock.patch.object(sh.time, "time", lambda: later):
            self.assertEqual(self.start(nummer=d["nummer"]).status_code, 403)
            self.assertEqual(self.start(link=d["link"].split("#")[1]).status_code, 200)    # the link still works
        reset()
        self.unlock()
        d = self.new()
        later = time.time() + sh.LINK_S + 1
        with unittest.mock.patch.object(sh.time, "time", lambda: later):
            self.assertEqual(self.start(link=d["link"].split("#")[1]).status_code, 403)
        self.assertIsNone(sh.current())                                       # gone, noted as expired
        self.assertEqual(sh.verlauf_read()[0]["art"], "nummer_verfallen")

    def test_number_key_and_name_never_in_a_log(self):
        with journal() as j:
            d = self.new()
            self.start(nummer=d["nummer"], name="Wilhelmine")
        out = j.getvalue()
        key = d["link"].split("#")[1]
        for secret in (d["nummer"], key, "Wilhelmine"):
            self.assertNotIn(secret, out)
        for line in out.splitlines():
            if line.startswith("spontanhilfe:"):
                self.assertRegex(line, r"^spontanhilfe: [a-z_]+ \| [a-z ]+ \| \d+$")

    def test_rate_limited_per_address(self):
        self.new()
        codes = [self.start(nummer="000000").status_code for _ in range(guard.RATE["spontanhilfe_start"][0] + 1)]
        self.assertEqual(codes[-1], 429)

    def test_first_name_only(self):
        d = self.new()
        for bad in ("", "<b>x", "1234", "x" * 40):
            self.assertEqual(self.start(nummer=d["nummer"], name=bad).status_code, 400)
        self.assertEqual(sh.current().fehl, 0)                               # a bad name is no try

    def test_one_help_at_a_time(self):
        d = self.new()
        self.start(nummer=d["nummer"])
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/neu", json={"origin": OUT}, headers=CODE).status_code, 409)
        self.assertEqual(ADMIN.delete("/api/admin/spontanhilfe").status_code, 200)
        self.assertIsNone(sh.current())


class ShellLine(Base):
    def test_one_line_without_sudo_and_never_the_number(self):
        d = self.new()
        self.assertEqual(d["befehl"], "curl -fsSL https://spark.example.org/fernzugang/anker | python3 - hilfe https://spark.example.org")
        self.assertEqual(d["befehl_mac"], "curl -fsSL https://spark.example.org/fernzugang/anker | /usr/bin/python3 - hilfe https://spark.example.org")
        for line in (d["befehl"], d["befehl_mac"]):
            self.assertNotIn("sudo", line)
            self.assertNotIn(d["nummer"], line)
            self.assertNotIn(d["link"].split("#")[1], line)
        import terminal
        with unittest.mock.patch.object(terminal, "cert_sha256", lambda: "ab" * 32), \
                unittest.mock.patch.object(fernzugang, "_spki_pin", lambda: "sha256//QUJD"), \
                unittest.mock.patch.object(fernzugang, "load_config", lambda part: {"port": 31080, "https_port": 31443}):
            self.assertEqual(fernzugang.command("https://tars:31443", art="hilfe")["befehl"],
                             "curl -fsSLk --pinnedpubkey 'sha256//QUJD' https://tars:31443/fernzugang/anker | python3 - hilfe "
                             "https://tars:31443 --fp " + "ab" * 32)

    def test_the_program_never_as_root_and_without_a_key(self):
        p = program()
        args = types.SimpleNamespace(adresse="https://spark.example.org", fp="")
        with unittest.mock.patch.object(p, "as_root", lambda: True), unittest.mock.patch.object(p, "Tty") as tty:
            with self.assertRaises(p.Fehler):
                p.cmd_help(args)
            tty.open.assert_not_called()                                      # nothing asked, nothing connected
        sent = []

        class Sock:
            def sendall(self, b):
                sent.append(b)

            def recv(self, n):
                return b""

            def close(self):
                pass
        for key in ("", "k" * 40):
            with unittest.mock.patch.object(p, "tls_connect", lambda *a, **k: (Sock(), "")):
                with self.assertRaises(p.Fehler):
                    p.WS.open("https://spark.example.org", "", "/x", key)
        self.assertNotIn(b"Authorization", sent[0])                           # the Spontanhilfe has no key
        self.assertIn(b"Authorization: Bearer " + b"k" * 40, sent[1])


class Messages(unittest.TestCase):
    def test_only_fixed_kinds_in_their_form(self):
        sdp = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\n"
        self.assertEqual(sh.clean("person", {"typ": "sdp", "art": "offer", "sdp": sdp})["sdp"], sdp)
        self.assertIsNone(sh.clean("person", {"typ": "sdp", "art": "answer", "sdp": sdp}))
        self.assertIsNone(sh.clean("admin", {"typ": "sdp", "art": "offer", "sdp": sdp}))
        self.assertIsNone(sh.clean("person", {"typ": "sdp", "art": "offer", "sdp": "x" * 100}))
        self.assertIsNone(sh.clean("person", {"typ": "zeig", "x": 0.5, "y": 0.5}))      # only the admin shows
        self.assertIsNone(sh.clean("admin", {"typ": "zeig", "x": 2, "y": 0.5}))
        self.assertEqual(sh.clean("admin", {"typ": "zeig", "x": 0.25, "y": 1}), {"typ": "zeig", "x": 0.25, "y": 1.0})
        self.assertIsNone(sh.clean("admin", {"typ": "teilt", "an": True}))
        self.assertIsNone(sh.clean("admin", {"typ": "eval", "code": "x"}))
        self.assertEqual(len(sh.clean("person", {"typ": "chat", "text": "a" * 2000})["text"]), sh.CHAT_MAX)
        self.assertEqual(sh.clean("person", {"typ": "chat", "text": "hi\x1b[31m\x00"})["text"], "hi[31m")
        self.assertIsNone(sh.clean("person", {"typ": "chat", "text": "  "}))
        self.assertIsNone(sh.clean("person", {"typ": "ice", "c": {"candidate": "a\nb"}}))
        self.assertEqual(sh.clean("person", {"typ": "ice", "c": None}), {"typ": "ice", "c": None})


class Sockets(Base):
    """Both sockets on one uvicorn, the clients with the websockets library like the two pages would."""

    def setUp(self):
        super().setUp()
        import uvicorn
        from fastapi import FastAPI
        only = FastAPI()
        only.include_router(sh.router)
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error",
                                              timeout_graceful_shutdown=2))
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.loop = asyncio.new_event_loop()
        self.th = threading.Thread(target=lambda: self.loop.run_until_complete(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        for _ in range(400):
            if server.started:
                break
            time.sleep(0.05)
        self.origin = f"http://127.0.0.1:{self.port}"
        self.patches = [unittest.mock.patch.object(fernzugang, "is_admin_browser", lambda c: True),
                        unittest.mock.patch.object(fernzugang, "_login", lambda c: "L")]
        for p in self.patches:
            p.start()
        self.unlock()                                     # the login is "L" now: its own unlock

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.server.should_exit = True
        self.th.join(10)
        self.loop.close()
        super().tearDown()

    def ws(self, path, origin=None):
        import websockets.sync.client as wsc
        return wsc.connect(f"ws://127.0.0.1:{self.port}{path}", additional_headers={"Origin": origin or self.origin},
                           open_timeout=10)

    def refused(self, path, origin=None, first=None):
        """The socket never opens or closes before a word: both are a refusal."""
        try:
            c = self.ws(path, origin)
        except Exception:
            return
        if first is not None:
            c.send(first)
        with self.assertRaises(Exception):
            c.recv(timeout=10)

    def recv(self, c):
        return json.loads(c.recv(timeout=10))

    def waiting(self):
        d = self.new()
        tok = self.start(nummer=d["nummer"]).json()["tok"]
        p = self.ws("/api/hilfe/ws")
        p.send(json.dumps({"typ": "hallo", "tok": tok}))
        self.assertEqual(self.recv(p)["stand"], "wartet")
        return p

    def accept(self):
        r = ADMIN.post("/api/admin/spontanhilfe/annehmen", headers=CODE)
        self.assertEqual(r.status_code, 200, r.text)
        return self.ws("/api/spontanhilfe/admin?t=" + r.json()["ticket"])

    def test_a_whole_help_relays_only_checked_messages(self):
        with journal() as j:
            p = self.waiting()
            a = self.accept()
            mine = self.recv(a)
            self.assertEqual((mine["stand"], mine["name"]), ("offen", "Helga"))
            self.assertEqual(self.recv(p)["stand"], "offen")
            sdp = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\n"
            p.send(json.dumps({"typ": "zeig", "x": 0.1, "y": 0.1}))                 # not hers: dropped
            p.send(json.dumps({"typ": "sdp", "art": "offer", "sdp": sdp, "extra": "x"}))
            self.assertEqual(self.recv(a), {"typ": "sdp", "art": "offer", "sdp": sdp})
            a.send(json.dumps({"typ": "zeig", "x": 0.5, "y": 0.25}))
            self.assertEqual(self.recv(p), {"typ": "zeig", "x": 0.5, "y": 0.25})
            p.send(json.dumps({"typ": "chat", "text": "Da steht Offline"}))
            self.assertEqual(self.recv(a), {"typ": "chat", "text": "Da steht Offline"})
            self.assertEqual(sh.for_live()["sitzung"], 1)
            p.send(json.dumps({"typ": "ende"}))
            self.assertEqual(self.recv(a)["stand"], "zu")
        self.assertIsNone(sh.current())
        out = j.getvalue()
        self.assertIn("spontanhilfe: sitzung_auf | ansehen | 1", out)
        self.assertIn("spontanhilfe: sitzung_zu | person | 0", out)
        for secret in ("Offline", "Helga", "v=0"):
            self.assertNotIn(secret, out)
        row = sh.verlauf_read()[0]
        self.assertEqual((row["art"], row["ende"]), ("ansehen", "person"))
        self.assertNotIn("Helga", json.dumps(sh.verlauf_read()))

    def test_a_too_big_message_ends_the_help(self):
        p = self.waiting()
        a = self.accept()
        self.recv(a)
        self.recv(p)
        p.send("x" * (sh.MAX_MSG + 1))
        self.assertEqual(self.recv(a)["stand"], "zu")

    def test_the_person_key_only_in_the_first_message_and_once(self):
        d = self.new()
        tok = self.start(nummer=d["nummer"]).json()["tok"]
        bad = self.ws("/api/hilfe/ws")
        bad.send(json.dumps({"typ": "hallo", "tok": tok[:-1] + ("A" if tok[-1] != "A" else "B")}))
        with self.assertRaises(Exception):
            bad.recv(timeout=10)
        p = self.ws("/api/hilfe/ws")
        p.send(json.dumps({"typ": "hallo", "tok": tok}))
        self.assertEqual(self.recv(p)["stand"], "wartet")
        again = self.ws("/api/hilfe/ws")                                        # a second socket with the same key
        again.send(json.dumps({"typ": "hallo", "tok": tok}))
        with self.assertRaises(Exception):
            again.recv(timeout=10)

    def test_foreign_origin_refused_on_both_sockets(self):
        for path in ("/api/hilfe/ws", "/api/spontanhilfe/admin?t=x"):
            self.refused(path, origin="https://evil.example")

    def test_the_ticket_once_and_only_this_login(self):
        self.waiting()
        r = ADMIN.post("/api/admin/spontanhilfe/annehmen")
        t = r.json()["ticket"]
        with unittest.mock.patch.object(fernzugang, "_login", lambda c: "other"):
            self.refused("/api/spontanhilfe/admin?t=" + t)
        self.refused("/api/spontanhilfe/admin?t=" + t)                          # popped by the first try
        fernzugang.ENTSPERRT.clear()
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/annehmen").status_code, 423)   # only on the unlocked page

    def test_notaus_ends_the_help_and_kills_number_and_link(self):
        p = self.waiting()
        a = self.accept()
        self.recv(a)
        self.recv(p)
        with unittest.mock.patch.object(sh, "_notaus", lambda count=False: True):
            fut = asyncio.run_coroutine_threadsafe(sh.notaus_close(), self.loop)
            fut.result(10)
            self.assertEqual(self.recv(a)["stand"], "zu")
            self.assertIsNone(sh.current())
            self.assertEqual(self.start(nummer="123456").status_code, 503)


    # ------------------------------------------------------------ S3 Shell: the anchor program's socket
    def shell(self, nummer, name="Helga"):
        """The program's socket: no Origin header (a program, no page)."""
        import websockets.sync.client as wsc
        c = wsc.connect(f"ws://127.0.0.1:{self.port}/api/hilfe/shell", open_timeout=10)
        c.send(json.dumps({"typ": "hallo", "nummer": nummer, "name": name, "os": "Debian 13"}))
        return c

    def test_shell_bytes_pass_only_after_her_yes(self):
        with journal() as j:
            d = self.new()
            p = self.shell(d["nummer"])
            self.assertEqual(self.recv(p), {"typ": "stand", "stand": "wartet", "admin": "Admin"})
            self.assertEqual((sh.current().art, sh.current().os, sh.current().nummer), ("shell", "Debian 13", ""))
            a = self.accept()
            mine = self.recv(a)
            self.assertEqual((mine["stand"], mine["art"], mine["name"]), ("offen", "shell", "Helga"))
            self.assertNotIn("ice", mine)                                       # no picture, no TURN
            self.assertEqual(self.recv(p)["stand"], "frage")
            self.assertEqual(sh.for_live()["offen"]["art"], "Shell")
            a.send(b"rm -rf ~\n")                                               # before her „j“ nothing passes
            p.send(b"before")
            a.send(json.dumps({"typ": "groesse", "cols": 120, "rows": 40}))
            self.assertEqual(self.recv(p), {"typ": "groesse", "cols": 120, "rows": 40})
            a.send(json.dumps({"typ": "groesse", "cols": 9999, "rows": 40}))    # out of form: dropped
            a.send(json.dumps({"typ": "chat", "text": "x"}))                     # no chat in a shell
            p.send(json.dumps({"typ": "erlaubt", "an": True}))
            self.assertEqual(self.recv(a), {"typ": "erlaubt", "an": True})
            a.send(b"ls\n")
            self.assertEqual(p.recv(timeout=10), b"ls\n")                        # the first bytes she gets
            p.send(b"notes.txt\r\n")
            self.assertEqual(a.recv(timeout=10), b"notes.txt\r\n")
            p.send(b"x" * (sh.MAX_MSG + 1))                                     # too big: the help ends
            self.assertEqual(self.recv(a)["stand"], "zu")
            self.assertTrue(until(lambda: sh.verlauf_read()))
        out = j.getvalue()
        for line in ("spontanhilfe: wartet | shell | 1", "spontanhilfe: sitzung_auf | shell | 1",
                     "spontanhilfe: erlaubt | ja | 1", "spontanhilfe: abgewiesen | zu gross | 0"):
            self.assertIn(line, out)
        for secret in ("Helga", d["nummer"], "notes", "rm -rf", "Debian"):
            self.assertNotIn(secret, out)
        self.assertEqual(sh.verlauf_read()[0]["art"], "shell")
        self.assertNotIn("Helga", json.dumps(sh.verlauf_read()))

    def test_shell_her_no_ends_the_help(self):
        d = self.new()
        p = self.shell(d["nummer"])
        self.recv(p)
        a = self.accept()
        self.recv(a)
        self.recv(p)
        with journal() as j:
            p.send(json.dumps({"typ": "erlaubt", "an": False}))
            self.assertEqual(self.recv(a)["stand"], "zu")
            self.assertTrue(until(lambda: sh.verlauf_read()))
        self.assertIn("spontanhilfe: erlaubt | nein | 0", j.getvalue())
        self.assertEqual(sh.verlauf_read()[0]["ende"], "abgelehnt")
        self.assertIsNone(sh.current())

    def test_shell_socket_refuses_any_origin_a_wrong_number_and_a_wrong_name(self):
        d = self.new()
        hallo = json.dumps({"typ": "hallo", "nummer": d["nummer"], "name": "Helga"})
        self.refused("/api/hilfe/shell", origin=self.origin, first=hallo)     # even the panel's own page: no
        self.assertEqual(sh.current().stand, "neu")
        c = self.shell(d["nummer"], name="<b>Helga</b>")
        self.assertEqual(self.recv(c), {"typ": "fehler", "grund": "name"})
        self.assertEqual(sh.current().stand, "neu")
        wrong = str((int(d["nummer"]) + 1) % 10**6).zfill(6)
        for n in range(sh.FEHL):
            c = self.shell(wrong)
            self.assertEqual(self.recv(c), {"typ": "fehler", "grund": "nummer"})   # the same answer every time
            with self.assertRaises(Exception):
                c.recv(timeout=10)
        self.assertIsNone(sh.current())                                         # dead after FEHL, like the page
        self.assertEqual(sh.verlauf_read()[0]["art"], "nummer_gesperrt")


class ShellEndToEnd(Base):
    """S3 for real: the anchor program (its own WebSocket client, TLS pinned) in a terminal (two pipes), the panel's
    sockets on one uvicorn with TLS, the admin's side with the websockets library like the page."""

    def setUp(self):
        super().setUp()
        import uvicorn
        from fastapi import FastAPI
        from tests.test_fernzugang import _tls_files
        only = FastAPI()
        only.include_router(sh.router)
        self.tmp = tempfile.mkdtemp(prefix="sh-tls-")
        cf, kf, self.fp = _tls_files(self.tmp)
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error",
                                              ssl_certfile=cf, ssl_keyfile=kf, timeout_graceful_shutdown=2))
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.th = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        until(lambda: server.started, 20)
        self.base = f"https://localhost:{self.port}"
        self.patches = [unittest.mock.patch.object(fernzugang, "is_admin_browser", lambda c: True),
                        unittest.mock.patch.object(fernzugang, "_login", lambda c: "L")]
        for p in self.patches:
            p.start()
        self.unlock()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.server.should_exit = True
        self.th.join(10)
        super().tearDown()

    def test_the_program_runs_her_shell_only_after_her_yes_and_leaves_nothing(self):
        import websockets.sync.client as wsc
        p = program()
        p.as_root = lambda: False            # the test container may run as root; the rule itself is tested above
        d = self.new()
        r_in, w_in = os.pipe()
        r_out, w_out = os.pipe()
        shown = bytearray()

        def show():
            while True:
                b = os.read(r_out, 4096)
                if not b:
                    return
                shown.extend(b)
        threading.Thread(target=show, daemon=True).start()
        os.write(w_in, (d["nummer"][:3] + " " + d["nummer"][3:] + "\nHelga\n").encode())
        got = {}
        args = types.SimpleNamespace(adresse=self.base, fp=self.fp)
        anchor = threading.Thread(target=lambda: got.setdefault("rc", p.cmd_help(args, tty=p.Tty(r_in, w_out), shell="/bin/sh")),
                                  daemon=True)
        anchor.start()
        self.assertTrue(until(lambda: sh.current() is not None and sh.current().stand == "wartet"))
        r = ADMIN.post("/api/admin/spontanhilfe/annehmen", headers=CODE)
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        a = wsc.connect(f"wss://localhost:{self.port}/api/spontanhilfe/admin?t=" + r.json()["ticket"], ssl=ctx,
                        additional_headers={"Origin": self.base}, open_timeout=10)
        self.assertEqual(json.loads(a.recv(timeout=10))["art"], "shell")
        self.assertTrue(until(lambda: b"Erlauben? [j/n]" in shown))
        a.send(b"echo too-early\n")                                             # before her „j“: never in a shell
        os.write(w_in, b"j\n")
        self.assertEqual(json.loads(a.recv(timeout=10)), {"typ": "erlaubt", "an": True})
        a.send(json.dumps({"typ": "groesse", "cols": 100, "rows": 30}))
        a.send(b"echo spark$((40+2)) pid=$$ cols=$(stty size)\n")
        out = b""
        for _ in range(100):
            m = a.recv(timeout=10)
            if isinstance(m, bytes):
                out += m
            if b"spark42" in out and b"\n" in out.split(b"spark42", 1)[1]:
                break
        self.assertIn(b"spark42", out)
        self.assertIn(b"30 100", out)                                            # the admin's size
        self.assertNotIn(b"too-early", out)
        self.assertTrue(until(lambda: b"spark42" in shown))                     # she sees it all on her terminal
        pid = int(out.split(b"pid=")[-1].split()[0])
        a.send(json.dumps({"typ": "ende"}))
        anchor.join(15)
        self.assertEqual(got.get("rc"), 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)                                                     # her shell is gone
        self.assertIn("die Hilfe ist beendet".encode(), bytes(shown))
        self.assertIsNone(sh.current())
        for fd in (w_in, w_out, r_in):
            with contextlib.suppress(OSError):
                os.close(fd)


class Clock(Base):
    def test_warns_ten_minutes_before_and_extends_never_past_the_setting(self):
        sent = []
        h = sh.Hilfe(None, "Admin", "L", "123456", "k" * 22, time.time())
        h.stand, h.seit = "offen", time.time()
        h.bis = h.seit + 3600

        class Fake:
            async def send_text(self, s):
                sent.append(json.loads(s))
                sh.HILFE.clear()        # one round is enough

        h.admin = Fake()
        sh.HILFE["h"] = h

        async def run():
            h.ende = asyncio.Event()
            h.bis = time.time() + sh.HINWEIS_S - 1
            await sh._clock(h)
        asyncio.run(run())
        self.assertEqual(sent[0]["typ"], "hinweis")
        self.assertTrue(sent[0]["kann_verlaengern"])
        # „Verlängern“: +60, never past chat.spontanhilfe_max_min from the start
        h.admin = None
        sh.HILFE["h"] = h
        with unittest.mock.patch.object(fernzugang, "_login", lambda c: "L"):
            h.bis = h.seit + 3600
            self.unlock()                                     # unlocked, and still a fresh code each time
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/verlaengern").status_code, 428)
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/verlaengern", headers=CODE).status_code, 200)
            self.assertEqual(h.bis - h.seit, 7200)
            ADMIN.post("/api/admin/spontanhilfe/verlaengern", headers=CODE)
            self.assertEqual(h.bis - h.seit, 10800)
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/verlaengern", headers=CODE).status_code, 409)
            helpers.set_config(spontanhilfe_max_min=90)
            h.bis = h.seit + 3600
            ADMIN.post("/api/admin/spontanhilfe/verlaengern", headers=CODE)
            self.assertEqual(h.bis - h.seit, 5400)

    def test_ends_at_its_time(self):
        h = sh.Hilfe(None, "Admin", "L", "123456", "k" * 22, time.time())
        h.stand, h.seit, h.bis = "offen", time.time() - 7200, time.time() - 1
        sh.HILFE["h"] = h

        async def run():
            h.ende = asyncio.Event()
            await sh._clock(h)
        with journal() as j:
            asyncio.run(run())
        self.assertIsNone(sh.current())
        self.assertIn("spontanhilfe: sitzung_zu | zeit | 120", j.getvalue())

    def test_setting_checked(self):
        self.assertIsNone(sh.check({"spontanhilfe_max_min": 180}))
        self.assertIn("spontanhilfe_max_min", sh.check({"spontanhilfe_max_min": 5}))
        self.assertIn("spontanhilfe_max_min", sh.check({"spontanhilfe_max_min": 721}))


class Seen(Base):
    def test_live_without_an_address_names_only_with_live_names(self):
        d = self.new()
        self.assertEqual(sh.for_live()["nummer"], 1)
        with unittest.mock.patch.object(live, "shown_outside", lambda c: True), unittest.mock.patch.object(live, "sender", lambda c: "84.150.3.4"):
            self.start(nummer=d["nummer"], name="Wilhelmine")
        h = sh.current()
        h.stand, h.seit = "offen", time.time() - 120
        with unittest.mock.patch.object(live, "cfg", lambda: {"live_names": False}):
            f = sh.for_live()
        text = json.dumps(f) + sh.live_sub(f)
        for no in ("84.150", "Wilhelmine"):
            self.assertNotIn(no, text)
        self.assertEqual(sh.live_sub(f), "1 Sitzung · Ansehen Person, Admin, Internet, 2 min")
        with unittest.mock.patch.object(live, "cfg", lambda: {"live_names": True}):
            self.assertEqual(sh.for_live()["offen"]["person"], "Wilhelmine")
        page = ADMIN.get("/api/admin/spontanhilfe").json()["hilfe"]          # the admin's own page
        self.assertEqual((page["name"], page["herkunft"], page["ip"]), ("Wilhelmine", "internet", "84.150.x.x"))
        self.assertIn("spontanhilfe", live.TARGETS)

    def test_push_with_fixed_words_when_a_person_waits(self):
        import push
        sent = []

        async def fake(uid, title, body, **kw):
            sent.append((uid, title, body))
            return 1
        h = sh.Hilfe(None, "Admin", "L", "123456", "k" * 22, time.time())
        h.name = "Wilhelmine"
        with unittest.mock.patch.object(push, "send", fake), unittest.mock.patch.object(sh, "_admins", lambda: ["u1"]):
            asyncio.run(sh._melden(h))
        self.assertEqual(sent, [("u1",) + sh.MELDUNG_PUSH])
        self.assertNotIn("Wilhelmine", json.dumps(sent))

    def test_history_kept_its_days_deleted_with_a_code_and_registered(self):
        h = sh.Hilfe(None, "Anna", "L", "123456", "k" * 22, time.time())
        h.stand, h.seit, h.name, h.grund = "offen", time.time() - 600, "Wilhelmine", "admin"
        sh.verlauf_add(h)
        old = sh.Hilfe(None, "Anna", "L", "123456", "k" * 22, time.time())
        old.seit = time.time() - 3 * 86400
        sh.verlauf_add(old)
        self.assertEqual(len(sh.verlauf_read()), 2)
        helpers.set_config(fernzugang_verlauf_tage=1)
        self.assertEqual(len(sh.verlauf_read()), 1)
        helpers.set_config(fernzugang_verlauf_tage=30)
        with open(sh.VERLAUF, encoding="utf-8") as f:
            self.assertNotIn("Wilhelmine", f.read())
        self.assertEqual(ADMIN.delete("/api/admin/spontanhilfe/verlauf", headers=CODE).status_code, 200)
        self.assertEqual(sh.verlauf_read(), [])
        import dateien
        with open(dateien.__file__, encoding="utf-8") as f:
            self.assertIn("spontanhilfe-verlauf.json", f.read())


class Invitation(Base):
    LINK = OUT + "/hilfe#" + "k" * 22
    BIS = 1_800_000_000.0

    def parts(self, msg):
        return {p.get_content_type(): p.get_content() for p in msg.iter_parts()}

    def test_text_and_html_from_the_fixed_templates(self):
        acct = {"user": "dominik@example.org"}
        msg = sh.invitation(acct, {"name": "Dominik"}, "helga@example.org", self.LINK, "482913", "de", self.BIS)
        self.assertEqual(msg["Subject"], "Dominik möchte dir am Computer helfen")
        self.assertEqual(msg.get_content_type(), "multipart/alternative")
        p = self.parts(msg)
        self.assertEqual(sorted(p), ["text/html", "text/plain"])
        uhr = time.strftime("%H:%M", time.localtime(self.BIS))
        for body in p.values():
            self.assertIn(self.LINK, body)
            self.assertIn("482 913", body)
            self.assertIn("30", body)
            self.assertIn(uhr + " Uhr", body)
            self.assertIn("Dominiks Spark", body)
            self.assertNotRegex(body, r"\{(name|name_s|link|nummer|gueltig|domain|min)\}")   # every placeholder filled
        en = sh.invitation(acct, {"name": "Klaus"}, "h@example.org", self.LINK, "123456", "en", self.BIS)
        self.assertEqual(en["Subject"], "Klaus would like to help you with your computer")
        self.assertIn("Klaus’s Spark", self.parts(en)["text/plain"])
        self.assertIn('lang="en"', self.parts(en)["text/html"])
        de = sh.invitation(acct, {"name": "Klaus"}, "h@example.org", self.LINK, "123456", "de", self.BIS)
        self.assertIn("Klaus’ Spark", self.parts(de)["text/plain"])

    def test_the_name_is_escaped_and_no_header_injection(self):
        acct = {"user": "dominik@example.org"}
        msg = sh.invitation(acct, {"name": "<b>Do</b>\r\nBcc: x@y"}, "h@example.org", self.LINK, "482913", "de", self.BIS)
        page = self.parts(msg)["text/html"]
        self.assertNotIn("<b>Do</b>", page)
        self.assertIn("&lt;b&gt;Do&lt;/b&gt;", page)
        self.assertIsNone(msg["Bcc"])
        self.assertNotIn("\n", msg["Subject"])
        # a name that looks like a placeholder stays a name (one pass)
        p = self.parts(sh.invitation(acct, {"name": "{link}"}, "h@example.org", self.LINK, "482913", "de", self.BIS))
        self.assertIn("{link} möchte dir", p["text/plain"])

    def test_no_external_resources_and_the_panel_domain(self):
        import urllib.parse
        acct = {"user": "dominik@example.org"}
        host = urllib.parse.urlsplit(OUT).hostname
        for lang in ("de", "en"):
            page = self.parts(sh.invitation(acct, {"name": "D"}, "h@example.org", self.LINK, "482913", lang, self.BIS))["text/html"]
            self.assertNotRegex(page.lower(), r"(src|background)\s*=\s*[\"']?\s*(https?:)?//")
            self.assertNotRegex(page.lower(), r"url\(\s*[\"']?\s*(https?:)?//|<link\b|<img\b|<script\b|@import")
            hrefs = set(re.findall(r'href="([^"]+)"', page))
            self.assertEqual(hrefs, {self.LINK})                                     # only the help link, to the panel
            self.assertIn(f">{host}<", page)
        with open(os.path.join(sh.VORLAGEN, "einladung.de.html"), encoding="utf-8") as f:
            self.assertEqual(set(sh.FELD.findall(f.read())), {"name", "name_s", "link", "nummer", "gueltig", "domain", "min"})

    def test_the_panel_password_has_no_mailbox(self):
        d = self.new()
        r = ADMIN.post("/api/admin/spontanhilfe/einladung", json={"an": "helga@example.org", "link": d["link"]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json={"an": "x", "link": d["link"]}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung",
                                    json={"an": "helga@example.org", "link": OUT + "/hilfe#" + "z" * 22}).status_code, 400)

    def _mailbox(self):
        """An admin profile with a mailbox; senden.send_now counted, never sent."""
        import senden
        sent = []
        acct = {"user": "dominik@example.org"}
        stack = contextlib.ExitStack()
        stack.enter_context(unittest.mock.patch.object(sh, "_mail_acct", lambda request: ({"id": "p1", "name": "Dominik"}, acct)))
        stack.enter_context(unittest.mock.patch.object(senden, "send_now", lambda pid, a, msg: sent.append(msg)))
        self.addCleanup(stack.close)
        return sent

    def test_double_click_sends_exactly_one_mail(self):
        sent = self._mailbox()
        d = self.new()
        body = {"an": "Helga@example.org", "link": d["link"]}
        with journal() as j:
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=body).status_code, 200)
            r = ADMIN.post("/api/admin/spontanhilfe/einladung", json=dict(body, an="helga@EXAMPLE.org"))
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json()["detail"], "Einladung schon gesendet")
            # „Nochmal senden“ within 60 s, even confirmed: still one mail
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=dict(body, nochmal=True)).status_code, 409)
        self.assertEqual(len(sent), 1)
        self.assertIn(d["link"], sent[0].get_body(("plain",)).get_content())
        self.assertIn("spontanhilfe: einladung | mail | 1", j.getvalue())
        self.assertIn("spontanhilfe: einladung | doppelt | 0", j.getvalue())
        # another address is its own invitation
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=dict(body, an="karl@example.org")).status_code, 200)
        self.assertEqual(len(sent), 2)

    def test_a_click_while_sending_sends_nothing(self):
        sent = self._mailbox()
        d = self.new()
        sh.current().eingeladen["helga@example.org"] = {"t": 0.0, "laeuft": True}     # the first click still sends
        r = ADMIN.post("/api/admin/spontanhilfe/einladung", json={"an": "helga@example.org", "link": d["link"], "nochmal": True})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(sent, [])

    def test_send_again_only_confirmed_and_after_a_minute(self):
        sent = self._mailbox()
        d = self.new()
        body = {"an": "helga@example.org", "link": d["link"]}
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=body).status_code, 200)
        sh.current().eingeladen["helga@example.org"]["t"] -= sh.NOCHMAL_S + 1
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=body).status_code, 409)          # not confirmed
        with journal() as j:
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=dict(body, nochmal=True)).status_code, 200)
        self.assertEqual(len(sent), 2)
        self.assertIn("spontanhilfe: einladung | nochmal | 1", j.getvalue())

    def test_a_failed_send_may_be_tried_again(self):
        import senden
        self._mailbox()
        d = self.new()
        body = {"an": "helga@example.org", "link": d["link"]}

        def kaputt(pid, a, msg):
            raise OSError("smtp")
        with unittest.mock.patch.object(senden, "send_now", kaputt):
            self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=body).status_code, 502)
        self.assertEqual(sh.current().eingeladen, {})
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json=body).status_code, 200)

    def test_empty_fields_send_nothing(self):
        sent = self._mailbox()
        d = self.new()
        self.assertIsNone(sh.invitation_text("Dominik", "", "482913", "de", 1.0))
        self.assertIsNone(sh.invitation_text("Dominik", "https://x/hilfe#" + "k" * 22, "", "de", 1.0))
        self.assertIsNone(sh.invitation_text("", "https://x/hilfe#" + "k" * 22, "482913", "en", 1.0))
        self.assertIsNone(sh.invitation_text("Dominik", "https://x/hilfe#" + "k" * 22, "482913", "en", 0))
        self.assertIsNone(sh.invitation({"user": "d@example.org"}, {"name": "D"}, "h@example.org", "", "482913", "de", 1.0))
        sh.current().nummer = ""                       # what if the number were gone: refused, not an empty mail
        with journal() as j:
            r = ADMIN.post("/api/admin/spontanhilfe/einladung", json={"an": "helga@example.org", "link": d["link"]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(sent, [])
        self.assertIn("spontanhilfe: einladung | leer | 1", j.getvalue())

    def test_the_button_stays_off_while_sending(self):
        with open(os.path.join(os.path.dirname(sh.__file__), "static", "js", "spontanhilfe.js"), encoding="utf-8") as f:
            js = f.read()
        mail = js[js.index("async function shMail()"):js.index("async function shEnde()")]
        self.assertIn("b.disabled=true", mail)
        self.assertIn("if(!an||b.disabled)return", mail)
        self.assertIn("catch(e){shMailFrei()", mail)          # freed again only on an error (or a new address)
        self.assertEqual(mail.count("shMailFrei()"), 1)

    def test_mail_module_untouched(self):
        with open(sh.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("senden.send_now", src)
        self.assertNotIn("smtplib", src)


if __name__ == "__main__":
    unittest.main()
