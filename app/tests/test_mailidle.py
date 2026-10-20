"""Neue Mails sofort (mailidle.py, Vorwärmen Stufe C, Dominik 2026-10-19 „6a“): IMAP IDLE for profiles that read mail.

- Off (admin switch chat.mail_idle) nothing is opened; on, only profiles that read their mail in the last
  mailidle.ACTIVE_SECONDS get a connection, newest first, at most mailidle.MAX_OPEN; a profile the admin blocked,
  Mein Notaus and a server without IDLE get none.
- The connection only reads (EXAMINE); EXISTS or EXPUNGE start the rules, the listing and the listeners, at most every
  QUIET seconds (a change in between is handled once QUIET is over, never lost); stop ends IDLE with DONE.
- What the server sends is data: BYE ends the connection, an endless line breaks it, nothing else is looked at.
- Logs: fixed words and numbers, never a sender or subject; Live: connections and new mails as numbers.

A fake IDLE server on a socket pair; no wall clock beyond short waits, no network.
"""
import contextlib
import io
import socket
import threading
import time
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import mail  # noqa: E402
import mailidle  # noqa: E402
import mailregeln  # noqa: E402
import notaus  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


class FakeIdle(helpers.FakeMailbox):
    """The fake mailbox with IDLE: each connection gets a socket pair; the server side answers IDLE and DONE."""
    after_login = ("IMAP4REV1", "MOVE", "IDLE")
    servers = []           # the server ends of open connections
    heard = []             # lines the client sent while idling

    def __init__(self, host, port, ssl_context=None, timeout=None):
        super().__init__(host, port, ssl_context, timeout)
        self.sock, srv = socket.socketpair()
        self.sock.settimeout(timeout)
        FakeIdle.servers.append(srv)
        threading.Thread(target=self._serve, args=(srv,), daemon=True).start()

    def logout(self):
        with contextlib.suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        return "BYE", [b""]

    @staticmethod
    def _serve(srv):
        f = srv.makefile("rb")
        tag = b""
        for line in f:
            line = line.rstrip(b"\r\n")
            FakeIdle.heard.append(line)
            if line.endswith(b" IDLE"):
                tag = line.split()[0]
                srv.sendall(b"+ idling\r\n")
            elif line == b"DONE":
                srv.sendall(tag + b" OK IDLE terminated\r\n")
        f.close()
        srv.close()

    @classmethod
    def push(cls, line):
        for srv in list(cls.servers):
            try:
                srv.sendall(line + b"\r\n")
            except OSError:
                pass


class NoIdle(FakeIdle):
    after_login = ("IMAP4REV1", "MOVE")


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def until(test, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if test():
            return True
        time.sleep(0.02)
    return False


class Base(unittest.TestCase):
    NAME = "Idle Ida"

    @classmethod
    def setUpClass(cls):
        mail.IMAP = FakeIdle
        helpers.set_config(mail=True, mail_idle=True, mail_manage=True, deny={})
        cls.c, cls.uid = profile(cls.NAME)
        FakeIdle.reset(inbox=[helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Werkstatt fertig", "Fertig.", mid="<i-1@x>")])
        r = cls.c.post("/api/profile/mail", json={"kind": "icloud", "user": helpers.MAIL_USER, "password": helpers.MAIL_PW})
        assert r.status_code == 200, r.text
        cls.acct = mail.get(cls.uid)["accounts"][0]

    @classmethod
    def tearDownClass(cls):
        mailidle.stop_all()
        mail.IMAP = helpers.FakeIMAP
        mail._used.pop(cls.uid, None)
        mailregeln.forget(cls.uid)
        helpers.set_config(mail=False, mail_idle=False, mail_manage=False, deny={})

    def setUp(self):
        mail.IMAP = FakeIdle
        FakeIdle.servers, FakeIdle.heard = [], []
        mailidle._no_idle.clear()
        mail._used.clear()
        self.old = (mailidle.QUIET, mailidle.WAIT, mailidle.BACKOFF, mailidle.news)
        mailidle.QUIET, mailidle.WAIT, mailidle.BACKOFF = 1.0, 0.1, 0.1

    def tearDown(self):
        mailidle.stop_all()
        mailidle.QUIET, mailidle.WAIT, mailidle.BACKOFF, mailidle.news = self.old
        helpers.set_config(mail_idle=True, deny={})


class Who(Base):
    def test_only_lately_reading_profiles_and_at_most_max(self):
        now = time.time() + 10 * mailidle.ACTIVE_SECONDS                 # whoever read mail did so long ago
        self.assertEqual(mailidle.wanted(now), [])
        mail._used[self.uid] = now - 60
        self.assertEqual([u for u, _ in mailidle.wanted(now)], [self.uid])
        mail._used[self.uid] = now - mailidle.ACTIVE_SECONDS - 1
        self.assertEqual(mailidle.wanted(now), [])                      # too long ago
        mail._used[self.uid] = now - 60
        old = mailidle.MAX_OPEN
        mailidle.MAX_OPEN = 0
        try:
            self.assertEqual(mailidle.wanted(now), [])
        finally:
            mailidle.MAX_OPEN = old

    def test_switch_block_and_notaus_open_nothing(self):
        mail._used[self.uid] = time.time()
        helpers.set_config(mail_idle=False)
        self.assertEqual(mailidle.wanted(), [])
        helpers.set_config(mail_idle=True, deny={"mailidle": [self.uid]})   # the admin blocks this profile
        self.assertFalse(features.allowed("mailidle", self.uid))
        self.assertEqual(mailidle.wanted(), [])
        helpers.set_config(deny={})
        old = notaus.blocks
        notaus.blocks = lambda kind, uid=None: kind == "auto"
        try:
            self.assertEqual(mailidle.wanted(), [])
        finally:
            notaus.blocks = old
        self.assertEqual(len(mailidle.wanted()), 1)


class Connection(Base):
    NAME = "Idle Ivo"

    def test_new_mail_is_heard_at_once_and_nothing_is_lost(self):
        got = []
        mailidle.news = got.append
        mail._used[self.uid] = time.time()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(mailidle.look()[:2], (1, 1))
            w = mailidle._open[(self.uid, self.acct["id"])]
            self.assertTrue(until(lambda: w.idling))
            self.assertEqual(mailidle.for_live()["open"], 1)
            new = mailidle.for_live()["new"]
            FakeIdle.push(b"* 2 EXISTS")
            self.assertTrue(until(lambda: got == [self.uid]))
            FakeIdle.push(b"* 3 EXISTS")                                  # within QUIET: later, once, never lost
            FakeIdle.push(b"* 1 EXPUNGE")
            time.sleep(0.1)
            self.assertEqual(got, [self.uid])
            self.assertTrue(until(lambda: got == [self.uid, self.uid]))
            time.sleep(1.2)
            self.assertEqual(len(got), 2)
            self.assertEqual(mailidle.for_live()["new"], new + 2)
            FakeIdle.push(b"* 4 FETCH (FLAGS (\\Seen))")                   # anything else is not looked at
            time.sleep(0.4)
            self.assertEqual(len(got), 2)
            mailidle.stop_all()
            self.assertTrue(until(lambda: not w.is_alive()))
        self.assertIn(b"DONE", FakeIdle.heard)
        self.assertTrue(any(x.endswith(b" IDLE") for x in FakeIdle.heard))
        log = out.getvalue()
        self.assertIn("mail: idle looked | 1 open, 1 started, 0 stopped", log)
        self.assertIn("mail: idle open |", log)
        self.assertIn("mail: idle stopped |", log)
        self.assertNotIn("Anna", log)

    def test_switch_off_closes(self):
        mailidle.news = lambda uid: None
        mail._used[self.uid] = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            mailidle.look()
            w = mailidle._open[(self.uid, self.acct["id"])]
            self.assertTrue(until(lambda: w.idling))
            helpers.set_config(mail_idle=False)
            self.assertEqual(mailidle.look(), (0, 0, 1))
            self.assertTrue(until(lambda: not w.is_alive()))
        self.assertEqual(mailidle.for_live(), {"on": False, "open": 0, "new": mailidle._count.counts()["neu"]})

    def test_a_server_without_idle_is_left_to_keep_fresh(self):
        mail.IMAP = NoIdle
        mail._used[self.uid] = time.time()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mailidle.look()
            w = mailidle._open[(self.uid, self.acct["id"])]
            self.assertTrue(until(lambda: not w.is_alive()))
            self.assertIn(self.acct["id"], mailidle._no_idle)
            self.assertEqual(mailidle.wanted(), [])                       # asked again after a day
            self.assertEqual(mailidle.look()[0], 0)
        self.assertIn("mail: idle not offered, kept fresh every 5 min |", out.getvalue())

    def test_bye_and_endless_lines_end_the_connection(self):
        mailidle.news = lambda uid: None
        mail._used[self.uid] = time.time()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mailidle.look()
            w = mailidle._open[(self.uid, self.acct["id"])]
            self.assertTrue(until(lambda: w.idling))
            FakeIdle.push(b"* BYE going away")
            self.assertTrue(until(lambda: "mail: idle lost (EOFError), again in" in out.getvalue()))
            self.assertTrue(until(lambda: w.idling))                      # tried again after BACKOFF
            FakeIdle.push(b"x" * (mailidle.LINE_MAX + 10))
            self.assertTrue(until(lambda: "mail: idle lost (ValueError)" in out.getvalue()))
            mailidle.stop_all()
            self.assertTrue(until(lambda: not w.is_alive()))


class News(Base):
    NAME = "Idle Inge"

    def test_rules_listing_and_listeners(self):
        heard = []
        mailidle.on_new(heard.append)
        try:
            FakeIdle.boxes["Auto"] = []
            r = self.c.post("/api/profile/mail/rules", json={"account": self.acct["id"], "when": {"from": "@autohaus-kehl.de"},
                                                             "then": {"folder": "Auto"}})
            self.assertEqual(r.status_code, 200, r.text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                mailregeln.run(self.uid)                                  # the first look: what is there stays
                FakeIdle.put("INBOX", helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Rechnung", "Anbei.", mid="<i-2@x>"))
                mailidle.news(self.uid)
                self.assertEqual(len(FakeIdle.boxes["Auto"]), 1)          # the rule took it at once
                helpers.set_config(mail_manage=False)
                FakeIdle.put("INBOX", helpers.box_mail("Anna <anna@autohaus-kehl.de>", "Noch eine", "…", mid="<i-3@x>"))
                mailidle.news(self.uid)
                self.assertEqual(len(FakeIdle.boxes["Auto"]), 1)          # without Mails ordnen no rule runs
            self.assertEqual(heard, [self.uid, self.uid])
            self.assertEqual(sorted(x["subject"] for x in mail.inbox(self.uid)["items"]), ["Noch eine", "Werkstatt fertig"])
            log = out.getvalue()
            self.assertIn("mail: idle news |", log)
            for word in ("Anna", "Rechnung", "Auto", "autohaus"):
                self.assertNotIn(word, log)
        finally:
            mailidle.LISTENERS.remove(heard.append)
            helpers.set_config(mail_manage=True)


if __name__ == "__main__":
    unittest.main()
