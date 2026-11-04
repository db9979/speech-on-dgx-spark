"""Spontanhilfe S2d: SparkHilfe for Linux X11 (the anchor program's `steuern`, spontansteuern._zeile; plan
spontanhilfe/s2-plan.md). One self-test for every protection rule, with a screen dummy instead of X11 (the container
has no X server): the line only after the ask, only with her session key and only for the panel's own address, no
secret in it; the key typed on her terminal (echo off), never an argument, an address or a variable, never shown or
logged; never as root; Wayland, no DISPLAY or no XTest say one sentence and connect nothing; the helper's name only
after the key was taken; her answer on the terminal (1, 2, 3, no answer: decline); inputs only from fernsicht's lists,
checked once more in the program and used only after „Erlauben“ while the admin says „Steuern“; pictures PNG, at most
fernsicht.MAX_FRAME; the end of the help ends the program and puts the screen back. No test depends on the time."""
import asyncio
import contextlib
import io
import json
import os
import ssl
import struct
import tempfile
import threading
import types
import unittest
import unittest.mock
import zlib

from tests import helpers
from tests.test_spontanhilfe import ADMIN, PERSON, journal, program  # noqa: F401
from tests.test_spontansteuern import _On

import fernsicht  # noqa: E402
import fernzugang  # noqa: E402
import panel  # noqa: E402
import spontanhilfe as sh  # noqa: E402
import spontansteuern as ss  # noqa: E402

ORIGIN = "https://testserver"          # the TestClient's Host: her page's own address
P = program()


class Screen:
    """The X11 screen as a dummy: a picture of fixed pixels, every input written down."""

    def __init__(self, w=320, h=200):
        self.w, self.h = w, h
        self.log, self.text, self.shown, self.closed, self.ends = [], "", False, False, []
        self.bild = bytes([10, 20, 200, 0]) * (w * h)

    def grab(self):
        return self.w, self.h, 4 * self.w, "bgrx", self.bild

    def show(self, text):
        self.shown, self.text = True, text

    def say(self, text):
        self.text = text

    def events(self):
        return [self.ends.pop()] if self.ends else []

    def fileno(self):
        return None

    def move(self, x, y):
        self.log.append(("move", x, y))

    def button(self, n, down):
        self.log.append(("button", n, down))

    def chord(self, syms):
        self.log.append(("chord", tuple(syms)))

    def type_char(self, ch):
        self.log.append(("char", ch))

    def flush(self):
        pass

    def close(self):
        self.closed = True


def png_pixels(png):
    """(width, height, rows without filter bytes) of a PNG bild_png made."""
    w, h = struct.unpack("!II", png[16:24])
    n = struct.unpack("!I", png[33:37])[0]
    data = zlib.decompress(png[41:41 + n])
    return w, h, [data[y * (1 + 3 * w) + 1:(y + 1) * (1 + 3 * w)] for y in range(h)]


class Lists(unittest.TestCase):
    def test_the_programs_lists_are_fernsichts_and_hold_no_free_combination(self):
        self.assertEqual(set(P.X_KEYS), set(fernsicht.KEYS))
        self.assertEqual(tuple(P.X_BUTTONS), tuple(fernsicht.BUTTONS))
        self.assertEqual((P.BILD_MAX, P.EVENTS_MAX, P.TEXT_MAX), (fernsicht.MAX_FRAME, fernsicht.MAX_EVENTS, fernsicht.TEXT_MAX))
        forbidden = {0xFFEB, 0xFFEC, 0xFFE7, 0xFFE8, 0xFFE9, 0xFFEA, 0xFE03}   # Super, Meta, Alt, AltGr
        for name, syms in P.X_KEYS.items():
            self.assertFalse(forbidden & set(syms), name)
            self.assertLessEqual(len(syms), 3, name)
        self.assertEqual(P.X_KEYS["tab"], (0xFF09,))

    def test_inputs_are_checked_again_in_the_program(self):
        raw = [{"t": "click", "x": 0.5, "y": 0.5, "b": "middle"}, {"t": "click", "x": 1.5, "y": 0.5},
               {"t": "move", "x": float("nan"), "y": 0.1}, {"t": "move", "x": True, "y": 0.1},
               {"t": "key", "k": "super"}, {"t": "key", "k": "alt+tab"}, {"t": "scroll", "dy": 99},
               {"t": "scroll", "dy": True}, {"t": "text", "s": "a\x1b[2Jb\nc" + "x" * 300}, {"t": "shell", "s": "rm"},
               {"t": "move", "x": 0, "y": 1}, {"t": "key", "k": "copy"}, "nonsense"]
        got = P.pruefe_eingaben(raw)
        self.assertEqual([e["t"] for e in got], ["scroll", "text", "move", "key"])
        self.assertEqual(got[0]["dy"], 10)
        self.assertNotIn("\x1b", got[1]["s"])
        self.assertLessEqual(len(got[1]["s"]), P.TEXT_MAX)
        self.assertEqual(len(P.pruefe_eingaben([{"t": "key", "k": "enter"}] * 100)), P.EVENTS_MAX)
        self.assertEqual(P.pruefe_eingaben("x"), [])

    def test_inputs_reach_the_screen_only_after_allow_and_while_the_admin_says_control(self):
        ev = [{"t": "click", "x": 1, "y": 0, "b": "double"}, {"t": "key", "k": "paste"}, {"t": "text", "s": "Ä\n"},
              {"t": "scroll", "dy": -2}, {"t": "key", "k": "super"}]
        for mode, steuern in (("view", True), ("control", False), ("no", True), ("", True)):
            s = Screen()
            st = P.Steuern(None, None, s, "spark.example.org", {})
            st.mode, st.steuern = mode, steuern
            self.assertEqual(st.apply(ev), 0)
            self.assertEqual(s.log, [])
        s = Screen()
        st = P.Steuern(None, None, s, "spark.example.org", {})
        st.mode, st.steuern = "control", True
        self.assertEqual(st.apply(ev), 4)                                 # „super“ is not on the list
        self.assertEqual(s.log, [("move", 319, 0), ("button", 1, True), ("button", 1, False), ("button", 1, True),
                                 ("button", 1, False), ("chord", (0xFFE3, 0x76)), ("char", "Ä"), ("char", "\n"),
                                 ("button", 5, True), ("button", 5, False), ("button", 5, True), ("button", 5, False)])
        self.assertEqual((P.keysym("Ä"), P.keysym("€"), P.keysym("\n"), P.keysym("a")), (0xC4, 0x010020AC, 0xFF0D, 0x61))

    def test_the_name_of_the_helper_keeps_no_control_or_direction_character(self):
        self.assertEqual(P.helfer_name("Do‮mi\x1bnik"), "Dominik")
        self.assertEqual(P.helfer_name(""), "Admin")
        self.assertLessEqual(len(P.helfer_name("x" * 100)), 40)


class Picture(unittest.TestCase):
    def test_png_holds_the_right_pixels_and_every_kth(self):
        w, h, bpl = 5, 3, 24
        raw = bytearray(bpl * h)
        for y in range(h):
            for x in range(w):
                raw[y * bpl + 4 * x:y * bpl + 4 * x + 4] = bytes([x * 10, y * 20, 200, 0])     # B G R X
        ow, oh, rows = png_pixels(P.bild_png(bytes(raw), w, h, bpl, "bgrx", 2))
        self.assertEqual((ow, oh), (3, 2))
        self.assertEqual(list(rows[0]), [200, 0, 0, 200, 0, 20, 200, 0, 40])
        self.assertEqual(list(rows[1]), [200, 40, 0, 200, 40, 20, 200, 40, 40])
        xrgb = b"".join(bytes([0, 200, y * 20, x * 10]) for y in range(h) for x in range(w))          # X R G B
        self.assertEqual(png_pixels(P.bild_png(xrgb, w, h, 4 * w, "xrgb", 1))[2][2][3:6], bytes([200, 40, 10]))

    def test_no_picture_is_bigger_than_fernsichts_cap(self):
        w, h = 1920, 1080
        noise = bytes((i * 2654435761 >> 7) & 0xFF for i in range(4 * w * 64)) * (h // 64)
        png = P.bild_klein(noise, w, h, 4 * w, "bgrx")
        self.assertIsNotNone(png)
        self.assertLessEqual(len(png), fernsicht.MAX_FRAME)
        self.assertLessEqual(png_pixels(png)[0], P.BILD_BREITE)
        self.assertIsNone(P.bild_klein(noise, w, h, 4 * w, "bgrx", cap=100))     # too big at every step: none
        self.assertTrue(png.startswith(ss.BILDER[1]))


class Start(unittest.TestCase):
    """What happens before anything is connected."""

    def args(self):
        return types.SimpleNamespace(adresse="https://spark.example.org", fp="")

    def no_connect(self):
        return unittest.mock.patch.object(P.WS, "open", side_effect=AssertionError("verbunden"))

    def tty(self, typed=b""):
        r, w = os.pipe()
        out_r, out_w = os.pipe()
        os.write(w, typed)
        os.close(w)
        return P.Tty(r, out_w), out_r

    def test_never_as_root_and_nothing_connected(self):
        with self.no_connect(), unittest.mock.patch.object(P, "as_root", lambda: True):
            with self.assertRaises(P.Fehler) as e:
                P.cmd_control(self.args(), tty=self.tty()[0], screen=Screen(), env={"LANG": "de_DE.UTF-8"})
        self.assertIn("nie als root", str(e.exception))

    def test_wayland_no_display_and_no_xtest_say_one_sentence_before_any_question(self):
        with self.no_connect(), unittest.mock.patch.object(P, "as_root", lambda: False), \
                unittest.mock.patch.object(P.Tty, "open", side_effect=AssertionError("gefragt")):
            for env, word in (({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "LANG": "de_DE"}, "Wayland"),
                              ({"WAYLAND_DISPLAY": "wayland-0", "LANG": "en_GB"}, "Wayland"),
                              ({"LANG": "de_DE"}, "DISPLAY fehlt")):
                with self.assertRaises(P.Fehler) as e:
                    P.cmd_control(self.args(), env=env)
                self.assertIn(word, str(e.exception))
                self.assertIn("nichts verbunden" if env["LANG"].startswith("de") else "Nothing was connected", str(e.exception))
            import ctypes
            with unittest.mock.patch.object(ctypes, "CDLL", side_effect=OSError("fehlt")):
                with self.assertRaises(P.Fehler) as e:
                    P.cmd_control(self.args(), env={"DISPLAY": ":0", "LANG": "de_DE"})
            self.assertIn("libX11.so.6", str(e.exception))

    def test_the_key_comes_only_from_her_terminal_without_echo(self):
        src = open(fernzugang.PROGRAM).read()
        self.assertNotIn("environ", src)                                  # no key from a variable (the pairing rule too)
        self.assertNotIn("SPARKHILFE_SCHLUESSEL", src)
        self.assertEqual(set(P.SITZUNG), {"LC_ALL", "LC_MESSAGES", "LANG", "DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE"})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            P.main(["steuern", "https://spark.example.org", "A" * 22])       # no place for a key in the arguments
        body = src.split("    def secret(self, prompt):", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("~termios.ECHO", body)
        with self.no_connect(), unittest.mock.patch.object(P, "as_root", lambda: False):
            for typed in (b"zu-kurz\n", b"A" * 21 + b"!\n"):
                t, out = self.tty(typed)
                with self.assertRaises(P.Fehler) as e:
                    P.cmd_control(self.args(), tty=t, screen=Screen(), env={"LANG": "de_DE"})
                self.assertIn("neuen holen", str(e.exception))
                os.close(t.wfd)
                shown = os.read(out, 65536).decode()
                self.assertIn("Schlüssel von der Hilfe-Seite", shown)
                self.assertNotIn(typed.decode().strip(), shown)            # never shown back

    def test_texts_in_german_and_english_and_the_line_on_other_systems(self):
        for k, (de, en) in P.TEXTE.items():
            self.assertTrue(de and en and de != en, k)
            for text in (de, en):
                text.format(admin="A", host="h", s=1, lib="l")
        self.assertTrue(P.deutsch({"LANG": "de_AT.UTF-8"}))
        self.assertFalse(P.deutsch({"LC_ALL": "C", "LANG": "de_DE"}))
        self.assertFalse(P.deutsch({"LANG": "en_US.UTF-8"}))
        self.assertIn("1  Ablehnen", P.T("frage", {"LANG": "de"}, admin="A", host="h", s=60))
        self.assertIn("3  Allow", P.T("frage", {"LANG": "en"}, admin="A", host="h", s=60))
        self.assertIn("Windows", P.not_yet("steuern", "Windows"))
        self.assertIn("Mac", P.not_yet("steuern", "Darwin"))
        self.assertIsNone(P.not_yet("steuern", "Linux"))


class Line(_On):
    """The panel's side: the line for her terminal."""

    def body(self, tok, **kw):
        return {"tok": tok, "art": ss.ZEILE, "origin": ORIGIN, **kw}

    def test_only_after_the_ask_with_her_session_key_and_for_the_panels_own_address(self):
        h, tok = self.open_help()
        h.art = "ansehen"
        self.assertEqual(PERSON.post("/api/hilfe/programm", json=self.body(tok)).status_code, 403)   # not asked yet
        r, sent = self.ask()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIs(sent[0]["zeile"], True)
        self.assertEqual(PERSON.post("/api/hilfe/programm", json=self.body("x" * 40)).status_code, 403)
        for origin in ("https://evil.example.org", "", "javascript:alert(1)"):
            self.assertEqual(PERSON.post("/api/hilfe/programm", json=self.body(tok, origin=origin)).status_code, 404)
        self.assertEqual(h.st.key_h, "")                                   # no key for a refused request
        with journal() as j:
            r = PERSON.post("/api/hilfe/programm", json=self.body(tok))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers.get("cache-control"), "no-store")
        d = r.json()
        self.assertEqual(set(d), {"befehl", "schluessel"})
        key, line = d["schluessel"], d["befehl"]
        self.assertRegex(key, r"^[A-Za-z0-9_\-]{22}$")
        self.assertEqual(line, "curl -fsSL https://testserver/fernzugang/anker | python3 - steuern https://testserver")
        self.assertNotIn(key, line)                                        # no secret in the line
        self.assertNotIn("sudo", line)
        self.assertEqual(h.st.key_h, sh._h(key))                           # only the hash is kept
        self.assertNotIn(key, j.getvalue())
        self.assertIn("spontanhilfe: programm | linux | 1", j.getvalue())
        again = PERSON.post("/api/hilfe/programm", json=self.body(tok)).json()["schluessel"]
        self.assertNotEqual(again, key)
        self.assertEqual(h.st.key_h, sh._h(again))                         # the one before stops

    def test_the_page_copies_the_key_only_and_shows_it_as_text(self):
        with open(os.path.join(os.path.dirname(ss.__file__), "static", "js", "spontanhilfe-seite.js")) as f:
            js = f.read()
        self.assertIn("return 'linux-x11'", js)
        self.assertIn("origin:location.origin", js)
        self.assertIn("navigator.clipboard.writeText(S.key)", js)
        self.assertIn("$('zeile').textContent=b", js)
        self.assertNotIn("innerHTML", js)
        self.assertNotRegex(js, r"location\.(href|hash|search)\s*=")          # the key never into an address
        self.assertIn("/^[A-Za-z0-9_-]{22}$/.test(k)", js)


class EndToEnd(_On):
    """S2d for real: the anchor program (its own WebSocket client, TLS pinned) with a terminal (two pipes) and the
    screen dummy, the panel's sockets on one uvicorn with TLS, the admin's and her page's sockets like the pages."""

    def setUp(self):
        super().setUp()
        import uvicorn
        from fastapi import FastAPI
        from tests.test_fernzugang import _tls_files
        only = FastAPI()
        only.include_router(sh.router)
        only.include_router(ss.router)
        self.tmp = tempfile.mkdtemp(prefix="s2d-tls-")
        cf, kf, self.fp = _tls_files(self.tmp)
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error",
                                              ssl_certfile=cf, ssl_keyfile=kf, timeout_graceful_shutdown=2,
                                              ssl_context_factory=panel.tls_context))
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.loop = asyncio.new_event_loop()
        self.th = threading.Thread(target=lambda: self.loop.run_until_complete(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        helpers.until(lambda: server.started, 20)
        self.base = f"https://localhost:{self.port}"
        self.origin = self.base
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
        self.loop.close()
        super().tearDown()

    def recv(self, c):
        m = c.recv(timeout=10)
        return m if isinstance(m, bytes) else json.loads(m)

    def ws(self, path, origin="page"):
        import websockets.sync.client as wsc
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        headers = {"Origin": self.origin} if origin == "page" else ({"Origin": origin} if origin else {})
        return wsc.connect(f"wss://localhost:{self.port}{path}", ssl=ctx, additional_headers=headers,
                           open_timeout=helpers.WS_OPEN_S)

    def test_ask_allow_control_and_end_with_the_real_program(self):
        d = self.new()
        tok = self.start(nummer=d["nummer"]).json()["tok"]
        page = self.ws("/api/hilfe/ws")
        page.send(json.dumps({"typ": "hallo", "tok": tok}))
        self.assertEqual(self.recv(page)["stand"], "wartet")
        t = ADMIN.post("/api/admin/spontanhilfe/annehmen").json()["ticket"]
        a = self.ws("/api/spontanhilfe/admin?t=" + t)
        self.assertEqual(self.recv(a)["stand"], "offen")
        self.assertEqual(self.recv(page)["stand"], "offen")
        self.assertEqual(self.ask()[0].status_code, 200)
        key = PERSON.post("/api/hilfe/programm", json={"tok": tok, "art": ss.ZEILE, "origin": ORIGIN}).json()["schluessel"]
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
        screen = Screen()
        got = {}
        os.write(w_in, key.encode() + b"\n")
        args = types.SimpleNamespace(adresse=self.base, fp=self.fp)
        out = io.StringIO()
        with unittest.mock.patch.object(P, "as_root", lambda: False), contextlib.redirect_stdout(out):
            run = threading.Thread(target=lambda: got.setdefault("rc", P.cmd_control(
                args, tty=P.Tty(r_in, w_out), screen=screen, env={"LANG": "de_DE.UTF-8"})), daemon=True)
            run.start()
            self.assertEqual(self.recv(a), {"typ": "steuern", "stand": "programm"})
            self.assertEqual(self.recv(page), {"typ": "steuern", "stand": "programm"})
            self.assertTrue(helpers.until(lambda: "Ihre Wahl (1, 2 oder 3)".encode() in shown))
            self.assertIn("möchte Ihren Computer steuern".encode(), bytes(shown))
            self.assertFalse(screen.shown)                                  # no frame, no picture before her answer
            os.write(w_in, b"3\n")
            self.assertEqual(self.recv(a), {"typ": "steuern", "stand": "control", "steuern": False})
            self.assertEqual(self.recv(page), {"typ": "steuern", "stand": "control"})
            pic = a.recv(timeout=10)
            self.assertIsInstance(pic, bytes)
            self.assertTrue(pic.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertLessEqual(len(pic), fernsicht.MAX_FRAME)
            self.assertTrue(screen.shown)
            self.assertIn("hier klicken: Beenden", screen.text)
            a.send(json.dumps({"typ": "eingabe", "events": [{"t": "key", "k": "copy"}]}))   # before „Steuern“
            a.send(json.dumps({"typ": "modus", "modus": "steuern"}))
            self.assertTrue(helpers.until(lambda: screen.text.startswith("Steuerung aktiv")))
            self.assertEqual(screen.log, [])
            a.send(json.dumps({"typ": "eingabe", "events": [{"t": "click", "x": 0.5, "y": 0.5},
                                                            {"t": "key", "k": "copy"}, {"t": "key", "k": "super"},
                                                            {"t": "text", "s": "hi"}]}))
            self.assertTrue(helpers.until(lambda: ("char", "i") in screen.log))
            self.assertEqual(screen.log, [("move", 160, 100), ("button", 1, True), ("button", 1, False),
                                          ("chord", (0xFFE3, 0x63)), ("char", "h"), ("char", "i")])
            a.send(json.dumps({"typ": "ende"}))
            run.join(15)
        self.assertEqual(got.get("rc"), 0)
        self.assertTrue(screen.closed)
        self.assertTrue(helpers.until(lambda: "die Hilfe ist beendet".encode() in shown))
        self.assertIsNone(sh.current())
        self.assertNotIn(key.encode(), bytes(shown))
        self.assertNotIn(key, out.getvalue())
        for fd in (w_in, w_out, r_in):
            with contextlib.suppress(OSError):
                os.close(fd)

    def test_a_used_key_is_refused_and_the_name_never_shown(self):
        d = self.new()
        tok = self.start(nummer=d["nummer"]).json()["tok"]
        page = self.ws("/api/hilfe/ws")
        page.send(json.dumps({"typ": "hallo", "tok": tok}))
        self.recv(page)
        t = ADMIN.post("/api/admin/spontanhilfe/annehmen").json()["ticket"]
        a = self.ws("/api/spontanhilfe/admin?t=" + t)
        self.recv(a)
        self.recv(page)
        self.ask()
        name = sh.current().admin_name
        r_in, w_in = os.pipe()
        r_out, w_out = os.pipe()
        os.write(w_in, b"A" * 22 + b"\n")                                  # never handed out
        with unittest.mock.patch.object(P, "as_root", lambda: False):
            with self.assertRaises(P.Fehler) as e:
                P.cmd_control(types.SimpleNamespace(adresse=self.base, fp=self.fp), tty=P.Tty(r_in, w_out),
                              screen=Screen(), env={"LANG": "de_DE"})
        self.assertIn("neuen holen", str(e.exception))
        os.close(w_out)
        shown = os.read(r_out, 65536).decode()
        self.assertNotIn(name, shown)
        self.assertNotIn("möchte", shown)
        for fd in (w_in, r_in, r_out):
            with contextlib.suppress(OSError):
                os.close(fd)

