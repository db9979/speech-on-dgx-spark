"""Spontanhilfe (spontanhilfe.py, plan spontanhilfe S1): one self-test for every protection rule. Off by default and
404 while off; only admins in their browser with a second step help, only on the unlocked Fernzugang page (locked:
423, GET says only that it is on), a fresh code for „Verlängern“ every time; the number works once, 10 minutes, dies after 5 wrong tries and every wrong try gets the same
answer; the link key works once and never reaches a log; the page's own strict CSP and screen sharing only there;
both sockets check Origin themselves, the person's key only in its first message, the admin's ticket once and bound
to the login; only fixed message kinds pass, checked for form and size; the clock warns and ends, „Verlängern“ never
past the setting; the Notaus ends it; Live without an address and names only with live_names; the history without a
name; a fixed invitation and a fixed push; logs in fixed words only. No test depends on the time of day."""
import asyncio
import contextlib
import io
import json
import os
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
    def test_fixed_text_from_the_own_mailbox_only(self):
        acct = {"user": "dominik@example.org"}
        msg = sh.invitation(acct, {"name": "Dominik"}, "helga@example.org", OUT + "/hilfe#" + "k" * 22, "482913", "de")
        body = msg.get_content()
        self.assertEqual(msg["Subject"], "Hilfe am Bildschirm von Dominik")
        self.assertIn(OUT + "/hilfe#" + "k" * 22, body)
        self.assertIn("482 913", body)
        self.assertIn("30 Minuten", body)
        self.assertEqual(msg.get_content_type(), "text/plain")                  # no HTML
        self.assertEqual(sh.invitation(acct, {"name": "D"}, "h@example.org", "x", "123456", "en")["Subject"], "Screen help from D")

    def test_the_panel_password_has_no_mailbox(self):
        d = self.new()
        r = ADMIN.post("/api/admin/spontanhilfe/einladung", json={"an": "helga@example.org", "link": d["link"]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung", json={"an": "x", "link": d["link"]}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/spontanhilfe/einladung",
                                    json={"an": "helga@example.org", "link": OUT + "/hilfe#" + "z" * 22}).status_code, 400)

    def test_mail_module_untouched(self):
        with open(sh.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("senden.send_now", src)
        self.assertNotIn("smtplib", src)


if __name__ == "__main__":
    unittest.main()
