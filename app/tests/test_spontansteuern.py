"""Spontanhilfe S2a Steuern (spontansteuern.py, plan spontanhilfe/s2-plan.md): one self-test for every protection rule,
with a program dummy instead of SparkHilfe. Off by default and 404 while off, under the Spontanhilfe switch; asking
needs a fresh code and an open help with a picture; the file only after the ask, only with her session key, only when
its SHA-256 matches; the key 128 bits, once, KEY_S seconds, only its hash kept, the same answer for every wrong one;
the program's socket refuses any Origin and learns the helper's name only after the key; pictures only JPEG (or PNG, S2d), at most
FPS a second, only after her answer; inputs only from fernsicht's lists and only while she allowed control and the
admin pressed „Steuern“; „Ablehnen“ leaves the help, closing the allowed program ends it, the end of the help closes
the program; logs in fixed words, Live and the history without content. No test depends on the time of day."""
import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import threading
import time
import types
import unittest
import unittest.mock

from tests import helpers
from tests.test_spontanhilfe import ADMIN, CODE, PERSON, Base, journal  # noqa: F401

import fernsicht  # noqa: E402
import fernzugang  # noqa: E402
import features  # noqa: E402
import spontanhilfe as sh  # noqa: E402
import spontansteuern as ss  # noqa: E402
import stufen  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 100
EXE = b"MZ" + b"\x00" * 200


def put_program(art="windows-x64", data=EXE, sha=None):
    os.makedirs(ss.CACHE, exist_ok=True)
    name = "SparkHilfe-" + art + ".exe"
    with open(os.path.join(ss.CACHE, name), "wb") as f:
        f.write(data)
    idx = {art: {"datei": name, "sha256": sha or hashlib.sha256(data).hexdigest()}}
    with open(os.path.join(ss.CACHE, "programme.json"), "w") as f:
        json.dump(idx, f)


class _On(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(spontansteuern=True)
        shutil.rmtree(ss.CACHE, ignore_errors=True)
        ss._sha.clear()

    def tearDown(self):
        helpers.set_config(spontansteuern=False)
        shutil.rmtree(ss.CACHE, ignore_errors=True)
        super().tearDown()

    def open_help(self):
        """A help in the state „offen“ without real sockets (the doors only look at the state)."""
        d = self.new()
        tok = self.start(nummer=d["nummer"]).json()["tok"]
        h = sh.current()
        h.stand, h.person, h.seit, h.bis = "offen", object(), time.time(), time.time() + 3600
        return h, tok

    def ask(self, code=True):
        sent = []

        async def rec(ws, d):
            sent.append(d)
        with unittest.mock.patch.object(sh, "_send", rec):
            r = ADMIN.post("/api/admin/spontanhilfe/steuern", headers=CODE if code else {})
        return r, sent


class Door(_On):
    def test_off_by_default_under_the_spontanhilfe_switch_and_404_while_off(self):
        self.assertNotIn("chat.spontansteuern", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["spontansteuern"].parent, "spontanhilfe")
        self.assertEqual(stufen.LIST[("POST", "/api/admin/spontanhilfe/steuern")][0], stufen.PROTECT)
        _h, tok = self.open_help()
        helpers.set_config(spontansteuern=False)
        self.assertEqual(self.ask()[0].status_code, 404)
        self.assertEqual(PERSON.post("/api/hilfe/programm", json={"tok": tok, "art": "windows-x64"}).status_code, 404)
        helpers.set_config(spontansteuern=True, spontanhilfe=False)        # the parent off: off too
        self.assertFalse(ss.admin_on())

    def test_asking_needs_a_fresh_code_and_an_open_help_with_a_picture(self):
        r, sent = self.ask()
        self.assertEqual(r.status_code, 404)                                # no help at all (not this login's)
        h, _tok = self.open_help()
        r, sent = self.ask(code=False)
        self.assertEqual(r.status_code, 428)
        self.assertIsNone(h.st)
        h.art = "shell"
        self.assertEqual(self.ask()[0].status_code, 409)
        h.art = "ansehen"
        put_program()
        with journal() as j:
            r, sent = self.ask()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sent, [{"typ": "steuern", "stand": "angefragt",
                                 "programme": {"windows-x64": hashlib.sha256(EXE).hexdigest()}, "zeile": True}])
        self.assertIn("spontanhilfe: steuern_frage | admin | 1", j.getvalue())
        fernzugang.ENTSPERRT.clear()
        self.assertEqual(self.ask()[0].status_code, 423)                    # only on the unlocked page


class File(_On):
    def test_the_file_only_after_the_ask_with_her_key_and_a_new_one_time_key_each_time(self):
        h, tok = self.open_help()
        put_program()
        body = {"tok": tok, "art": "windows-x64"}
        self.assertEqual(PERSON.post("/api/hilfe/programm", json=body).status_code, 403)     # not asked yet
        self.ask()
        wrong = PERSON.post("/api/hilfe/programm", json={**body, "tok": tok[:-1] + ("A" if tok[-1] != "A" else "B")})
        self.assertEqual((wrong.status_code, wrong.json()["detail"]), (403, "Bitte die Seite neu laden."))
        with journal() as j:
            r = PERSON.post("/api/hilfe/programm", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, EXE)
        key = r.headers["x-spark-schluessel"]
        self.assertRegex(key, r"^[A-Za-z0-9_\-]{22}$")                       # 128 bits
        self.assertEqual(r.headers["x-spark-sha256"], hashlib.sha256(EXE).hexdigest())
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(h.st.key_h, hashlib.sha256(key.encode()).hexdigest())   # only the hash kept
        self.assertNotIn(key, j.getvalue())
        self.assertIn("spontanhilfe: programm | windows | 1", j.getvalue())
        again = PERSON.post("/api/hilfe/programm", json=body).headers["x-spark-schluessel"]
        self.assertNotEqual(again, key)
        self.assertEqual(h.st.key_h, hashlib.sha256(again.encode()).hexdigest())  # the one before stops
        self.assertEqual(PERSON.post("/api/hilfe/programm", json={**body, "art": "windows-x86"}).status_code, 404)

    def test_a_file_that_does_not_match_its_checksum_is_never_delivered(self):
        _h, tok = self.open_help()
        put_program(sha="0" * 64)
        self.ask()
        self.assertEqual(ss.angebot(), {})
        self.assertEqual(PERSON.post("/api/hilfe/programm", json={"tok": tok, "art": "windows-x64"}).status_code, 404)
        put_program()
        self.assertIsNotNone(ss.programm("windows-x64"))
        with open(os.path.join(ss.CACHE, "SparkHilfe-windows-x64.exe"), "ab") as f:   # changed afterwards
            f.write(b"evil")
        self.assertIsNone(ss.programm("windows-x64"))
        with open(os.path.join(ss.CACHE, "programme.json"), "w") as f:      # a name outside the cache
            json.dump({"windows-x64": {"datei": "../spontanhilfe-verlauf.json", "sha256": "0" * 64}}, f)
        self.assertIsNone(ss.programm("windows-x64"))


class Rate(_On):
    """Dominik 2026-11-04: „Programm laden“ said „too many requests“. From outside everyone comes through the reverse
    proxy with one address; the number's limit stays per address, her program door counts per help once her key is
    right, a wrong key still per address."""

    def test_her_program_door_counts_per_help_not_per_address(self):
        import guard
        h, tok = self.open_help()
        put_program()
        self.ask()
        body = {"tok": tok, "art": "windows-x64"}
        tries = [PERSON.post("/api/hilfe/start", json={"name": "Helga", "nummer": "000000"}).status_code
                 for _ in range(guard.RATE["spontanhilfe_start"][0] + 1)]        # someone guesses behind the same proxy
        self.assertEqual(tries[-1], 429)                                        # guessing stays capped
        wrong = {**body, "tok": tok[:-1] + ("A" if tok[-1] != "A" else "B")}
        with journal() as j:
            bad = [PERSON.post("/api/hilfe/programm", json=wrong) for _ in range(guard.RATE["spontanhilfe_programm"][0] + 1)]
        self.assertEqual([r.status_code for r in bad[:-1]], [403] * guard.RATE["spontanhilfe_programm"][0])
        self.assertEqual(bad[-1].status_code, 429)                              # wrong keys: per address
        self.assertIn("spontanhilfe: zu_oft | programm | 0", j.getvalue())
        ok = [PERSON.post("/api/hilfe/programm", json=body) for _ in range(guard.RATE["spontanhilfe_programm"][1] + 1)]
        self.assertEqual([r.status_code for r in ok[:-1]], [200] * guard.RATE["spontanhilfe_programm"][1])   # hers
        self.assertEqual(ok[-1].status_code, 429)                               # but not without end
        self.assertTrue(1 <= int(ok[-1].headers["retry-after"]) <= 60)
        # a second help behind the same address (a minute later for the number) has its own budget
        sh.HILFE.clear()
        for k in [k for k in guard._rate if k[0] == "spontanhilfe_start"]:
            guard._rate.pop(k, None)
        h2, tok2 = self.open_help()
        self.ask()
        self.assertNotEqual(h2.id, h.id)
        self.assertEqual(PERSON.post("/api/hilfe/programm", json={**body, "tok": tok2}).status_code, 200)

    def test_every_429_of_a_door_writes_a_line(self):
        import guard
        self.new()
        with journal() as j:
            for _ in range(guard.RATE["spontanhilfe_start"][0] + 1):
                self.start(nummer="000000")
        self.assertIn("spontanhilfe: zu_oft | start | 0", j.getvalue())
        self.assertEqual(sh.WORDS.count("zu_oft"), 1)


class Messages(unittest.TestCase):
    def test_inputs_only_from_fernsichts_lists(self):
        self.assertIsNone(sh.clean("admin", {"typ": "eingabe", "events": [{"t": "key", "k": "win"}, {"t": "key", "k": "alt+tab"}]}))
        self.assertEqual(sh.clean("admin", {"typ": "eingabe", "events": [{"t": "click", "x": 0.5, "y": 2}, {"t": "key", "k": "enter"},
                                                                         {"t": "click", "x": 0.25, "y": 0.5, "b": "middle"}]}),
                         {"typ": "eingabe", "events": [{"t": "key", "k": "enter"}]})
        self.assertEqual(sh.clean("admin", {"typ": "modus", "modus": "steuern"}), {"typ": "modus", "modus": "steuern"})
        self.assertIsNone(sh.clean("admin", {"typ": "modus", "modus": "root"}))
        self.assertIsNone(sh.clean("person", {"typ": "eingabe", "events": [{"t": "key", "k": "enter"}]}))   # never hers
        self.assertIsNone(sh.clean("person", {"typ": "modus", "modus": "steuern"}))
        self.assertEqual(sh.clean("person", {"typ": "steuern_nein", "x": 1}), {"typ": "steuern_nein"})
        for k in ("win", "cmd", "alt+tab", "ctrl+alt+delete"):
            self.assertNotIn(k, fernsicht.KEYS)


class Program(_On):
    """The program dummy on one uvicorn with both routers, the admin's and the person's sockets like the pages."""

    def setUp(self):
        super().setUp()
        import uvicorn
        from fastapi import FastAPI
        only = FastAPI()
        only.include_router(sh.router)
        only.include_router(ss.router)
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
        self.unlock()
        put_program()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.server.should_exit = True
        self.th.join(10)
        self.loop.close()
        super().tearDown()

    def ws(self, path, origin="page"):
        import websockets.sync.client as wsc
        headers = {"Origin": self.origin} if origin == "page" else ({"Origin": origin} if origin else {})
        return wsc.connect(f"ws://127.0.0.1:{self.port}{path}", additional_headers=headers, open_timeout=helpers.WS_OPEN_S)

    def recv(self, c):
        m = c.recv(timeout=10)
        return m if isinstance(m, bytes) else json.loads(m)

    def opened(self):
        """A help with both sockets open, the admin asked, the person loaded the file: (person, admin, key)."""
        d = self.new()
        tok = self.start(nummer=d["nummer"]).json()["tok"]
        p = self.ws("/api/hilfe/ws")
        p.send(json.dumps({"typ": "hallo", "tok": tok}))
        self.assertEqual(self.recv(p)["stand"], "wartet")
        t = ADMIN.post("/api/admin/spontanhilfe/annehmen").json()["ticket"]
        a = self.ws("/api/spontanhilfe/admin?t=" + t)
        self.assertEqual(self.recv(a)["stand"], "offen")
        self.assertEqual(self.recv(p)["stand"], "offen")
        self.assertEqual(self.ask()[0].status_code, 200)
        key = PERSON.post("/api/hilfe/programm", json={"tok": tok, "art": "windows-x64"}).headers["x-spark-schluessel"]
        return p, a, key

    def program(self, key, origin=None):
        g = self.ws("/api/hilfe/steuern", origin=origin)
        g.send(json.dumps({"typ": "hallo", "schluessel": key, "art": "windows-x64"}))
        return g

    def allowed(self, modus="control"):
        p, a, key = self.opened()
        g = self.program(key)
        hello = self.recv(g)
        self.assertEqual(self.recv(a), {"typ": "steuern", "stand": "programm"})
        self.assertEqual(self.recv(p), {"typ": "steuern", "stand": "programm"})
        g.send(json.dumps({"typ": "antwort", "modus": modus}))
        self.assertEqual(self.recv(a), {"typ": "steuern", "stand": modus, "steuern": False})
        self.assertEqual(self.recv(p), {"typ": "steuern", "stand": modus})
        return p, a, g, hello

    def test_any_origin_and_every_wrong_key_refused_the_name_only_after_the_key(self):
        _p, _a, key = self.opened()
        with self.assertRaises(Exception):                                 # a web page: never
            self.program(key, origin=self.origin).recv(timeout=10)
        bad = self.program(key[:-1] + ("A" if key[-1] != "A" else "B"))
        self.assertEqual(self.recv(bad), {"typ": "fehler", "grund": "neu laden"})   # no name, the same for all
        with self.assertRaises(Exception):
            bad.recv(timeout=10)
        sh.current().st.key_bis = time.time() - 1                         # older than KEY_S
        late = self.program(key)
        self.assertEqual(self.recv(late), {"typ": "fehler", "grund": "neu laden"})
        sh.current().st.key_bis = time.time() + ss.KEY_S
        g = self.program(key)
        hello = self.recv(g)
        self.assertEqual((hello["stand"], hello["admin"]), ("frage", sh.current().admin_name))
        self.assertEqual(hello["keys"], list(fernsicht.KEYS))
        once = self.program(key)                                          # once
        self.assertEqual(self.recv(once), {"typ": "fehler", "grund": "neu laden"})

    def test_wrong_program_keys_capped_per_address_a_right_one_per_help(self):
        import guard
        _p, _a, key = self.opened()
        bad = key[:-1] + ("A" if key[-1] != "A" else "B")
        for _ in range(guard.RATE["spontanhilfe_steuern"][0]):
            g = self.program(bad)
            self.assertEqual(self.recv(g), {"typ": "fehler", "grund": "neu laden"})
            g.close()
        with journal() as j:
            g = self.program(bad)
            self.assertEqual(self.recv(g), {"typ": "fehler", "grund": "neu laden"})   # the same answer, now capped
            g.close()
        for _ in range(100):
            if "zu_oft | steuern" in j.getvalue():
                break
            time.sleep(0.05)
        self.assertIn("spontanhilfe: zu_oft | steuern | 0", j.getvalue())
        g = self.program(key)                    # her right key: per help, not per (proxy) address
        self.assertEqual(self.recv(g)["stand"], "frage")

    def test_pictures_and_inputs_pass_only_as_allowed(self):
        with journal() as j:
            _p, a, g, _hello = self.allowed("control")
            g.send(JPEG)
            self.assertEqual(self.recv(a), JPEG)
            a.send(json.dumps({"typ": "eingabe", "events": [{"t": "key", "k": "enter"}]}))   # „Steuern“ not pressed
            a.send(json.dumps({"typ": "modus", "modus": "steuern"}))
            self.assertEqual(self.recv(g), {"typ": "modus", "steuern": True})                 # not the input before
            self.assertEqual(self.recv(a), {"typ": "steuern", "stand": "control", "steuern": True})
            a.send(json.dumps({"typ": "eingabe", "events": [{"t": "key", "k": "win"}, {"t": "click", "x": 0.5, "y": 0.5}]}))
            self.assertEqual(self.recv(g), {"typ": "eingabe", "events": [{"t": "click", "x": 0.5, "y": 0.5, "b": "left"}]})
            self.assertEqual(sh.for_live()["steuern"], 1)
            self.assertEqual(sh.for_live()["offen"]["art"], "Ansehen + Steuern")
            a.send(json.dumps({"typ": "modus", "modus": "ansehen"}))                           # „Nur ansehen“
            self.assertEqual(self.recv(g), {"typ": "modus", "steuern": False})
            self.recv(a)
            a.send(json.dumps({"typ": "eingabe", "events": [{"t": "key", "k": "enter"}]}))
            g.send(json.dumps({"typ": "ende"}))                                                # closing the allowed program
            self.assertEqual(self.recv(a)["stand"], "zu")                                      # ends the help
        self.assertIsNone(sh.current())
        for _ in range(200):                                              # written in a thread after „zu“
            if sh.verlauf_read():
                break
            time.sleep(0.05)
        self.assertEqual(sh.verlauf_read()[0]["art"], "steuern")
        out = j.getvalue()
        for line in ("spontanhilfe: programm | verbunden | 1", "spontanhilfe: steuern | erlaubt | 1",
                     "spontanhilfe: steuern | an | 1", "spontanhilfe: steuern | ansehen | 0",
                     "spontanhilfe: steuern_zu | programm | 0"):
            self.assertIn(line, out)
        self.assertNotIn("Helga", out)

    def test_view_only_never_passes_inputs_and_frames_are_capped(self):
        _p, a, g, _hello = self.allowed("view")
        a.send(json.dumps({"typ": "modus", "modus": "steuern"}))
        self.assertEqual(self.recv(g), {"typ": "modus", "steuern": False})   # she said view only
        self.recv(a)
        with unittest.mock.patch.object(ss, "time", types.SimpleNamespace(time=lambda: 1000.0)):   # one second
            for _ in range(ss.FPS + 3):
                g.send(JPEG)
            got = 0
            with contextlib.suppress(TimeoutError):
                while True:
                    m = a.recv(timeout=2)
                    if isinstance(m, bytes):
                        got += 1
        self.assertEqual(got, ss.FPS)
        g.send(b"not a jpeg")                                                 # anything else ends it
        self.assertEqual(self.recv(a)["stand"], "zu")

    def test_declining_leaves_the_help_and_her_page_may_say_no(self):
        with journal() as j:
            p, a, key = self.opened()
            p.send(json.dumps({"typ": "steuern_nein"}))
            self.assertEqual(self.recv(a), {"typ": "steuern", "stand": "nein"})
            g = self.program(key)
            self.recv(g)
            self.recv(a)
            self.recv(p)
            g.send(json.dumps({"typ": "antwort", "modus": "no"}))
            self.assertEqual(self.recv(a)["stand"], "no")
            self.assertEqual(self.recv(g), {"typ": "stand", "stand": "zu"})
        self.assertEqual(sh.current().stand, "offen")                         # looking goes on
        self.assertIsNone(sh.current().st.programm)
        self.assertIn("spontanhilfe: steuern | abgelehnt | 0", j.getvalue())
        self.assertIn("spontanhilfe: steuern | nein | 0", j.getvalue())

    def test_the_end_of_the_help_closes_the_program_and_kills_the_key(self):
        _p, a, g, _hello = self.allowed("control")
        fut = asyncio.run_coroutine_threadsafe(sh.notaus_close(), self.loop)
        fut.result(10)
        self.assertEqual(self.recv(g), {"typ": "stand", "stand": "zu"})
        self.assertIsNone(sh.current())


if __name__ == "__main__":
    unittest.main()
