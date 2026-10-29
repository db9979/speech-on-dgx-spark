"""Fernzugang, Bildschirm (fernbild.py, anker/spark-anker.py `bildschirm`, plan ssh-vermittlung stage 4): one self-test
for every protection rule. Off by default under the Fernzugang and 404 while off; only an admin in the browser with a
second step on the unlocked page gets a ticket, once, bound to the login; a system without the screen set up or with
an old anchor gets none; a Mac's sign-in only in the ticket, never in a log or a file; the anchor's password comes
from the vault and only for a known key; the browser may send only the fixed instructions, mouse and keys only after
„Steuern“, the clipboard only with its own setting and „Steuern“; the anchor reaches only the one screen port and only
when it is set up; the vendored guacamole-common-js is the pinned one. The whole way for real: the anchor program,
the panel's sockets on one uvicorn with TLS, guacd, x11vnc on an Xvfb display. No test depends on the time of day."""
import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import types
import unittest
import unittest.mock

from tests import helpers
from tests.test_fernzugang import ADMIN, CODE, HOST_PUB, OUT, Base, journal, program  # noqa: F401

import fernbild  # noqa: E402
import fernzugang  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class FbBase(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(fernbild=True, fernbild_zwischenablage=False)

    def tearDown(self):
        helpers.set_config(fernbild=False)
        super().tearDown()

    def screen(self, art="x11vnc", version="1.2.0"):
        """A paired system whose anchor set up the screen (its password from the panel)."""
        d = self.pair()
        r = TestClient(panel.app).post("/api/fernzugang/anker/bildschirm", json={"art": art},
                                       headers={"Authorization": "Bearer " + d["key"]})
        self.assertEqual(r.status_code, 200, r.text)
        fernzugang._update(d["id"], anker=version)
        return d, r.json()


class Protocol(unittest.TestCase):
    def test_instructions_whole_and_only_whole(self):
        raw = fernbild.enc("size", "0", "800", "600") + fernbild.enc("blob", "1", "äöü;,.") + "4.sy"
        got, rest = fernbild.split(raw)
        self.assertEqual([e for _, e in got], [["size", "0", "800", "600"], ["blob", "1", "äöü;,."]])
        self.assertEqual(rest, "4.sy")
        self.assertEqual("".join(r for r, _ in got) + rest, raw)
        for bad in ("x.size;", "4.size:", "99999999999.a;"):
            with self.assertRaises(ValueError):
                fernbild.split(bad)
        with self.assertRaises(ValueError):
            fernbild.split("20.abc;", limit=10)

    def test_only_fixed_instructions_mouse_and_keys_only_after_steuern(self):
        f = fernbild.Filter(clipboard=False)
        self.assertEqual(f.take(["mouse", "10", "10", "1"]), (None, None))         # watching only
        self.assertEqual(f.take(["key", "65", "1"]), (None, None))
        self.assertEqual(f.take(["sync", "123"])[0], fernbild.enc("sync", "123"))
        self.assertEqual(f.take(["", "ping", "77"]), (None, fernbild.enc("", "ping", "77")))   # answered here
        for op in ("file", "pipe", "audio", "argv", "put", "select", "connect"):
            self.assertEqual(f.take([op, "1", "x"]), (None, None))
        f.take([fernbild.STEUERN, "1"])
        self.assertEqual(f.take(["key", "65", "1"])[0], fernbild.enc("key", "65", "1"))
        self.assertEqual(f.take(["clipboard", "3", "text/plain"]), (None, None))   # clipboard off
        f.take([fernbild.STEUERN, "0"])
        self.assertEqual(f.take(["mouse", "1", "1", "0"]), (None, None))

    def test_clipboard_only_with_its_setting_and_steuern(self):
        f = fernbild.Filter(clipboard=True)
        self.assertEqual(f.take(["clipboard", "3", "text/plain"]), (None, None))   # not while watching
        f.take([fernbild.STEUERN, "1"])
        self.assertIsNotNone(f.take(["clipboard", "3", "text/plain"])[0])
        self.assertIsNotNone(f.take(["blob", "3", "aGFsbG8="])[0])
        self.assertIsNone(f.take(["blob", "4", "eA=="])[0])                       # not its stream
        self.assertIsNotNone(f.take(["end", "3"])[0])
        self.assertIsNone(f.take(["blob", "3", "eA=="])[0])                       # ended
        self.assertIsNone(f.take(["clipboard", "5", "application/octet-stream"])[0])

    def test_guacd_gets_the_clipboard_off_and_no_drive(self):
        v = fernbild.values_for("vnc", 40000, "pw")
        self.assertEqual((v["hostname"], v["port"], v["disable-copy"], v["disable-paste"]), ("127.0.0.1", "40000", "true", "true"))
        r = fernbild.values_for("rdp", 40001, "pw", "spark-bild", clipboard=True)
        self.assertEqual((r["disable-copy"], r["enable-drive"], r["disable-upload"], r["username"]), ("", "", "true", "spark-bild"))

    def test_sparsam_is_16_bit(self):
        self.assertEqual(fernbild.values_for("vnc", 40000, "pw")["color-depth"], "24")
        self.assertEqual(fernbild.values_for("vnc", 40000, "pw", sparsam=True)["color-depth"], "16")
        self.assertEqual(fernbild.values_for("rdp", 40000, "pw", "u", sparsam=True)["color-depth"], "16")

    def test_at_most_fps_pictures_a_second_in_order(self):
        f = fernbild.Filter()
        step = 1 / fernbild.FPS
        self.assertEqual(f.sync_delay(100.0), 0)                       # the first at once
        self.assertAlmostEqual(f.sync_delay(100.01), step - 0.01)       # the next one a frame later
        self.assertAlmostEqual(f.sync_delay(100.02), 2 * step - 0.02)   # and in order
        self.assertEqual(f.sync_delay(200.0), 0)                       # a quiet screen waits for nothing
        self.assertLessEqual(fernbild.FPS, 15)

    def test_vendored_library_is_the_pinned_one(self):
        for name, want in fernbild.GUAC.items():
            path, _ = fernbild.guac_file(name)
            with open(path, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), want, name)
        r = ADMIN.get("/static/guac/guacamole-common.min.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ADMIN.get("/static/guac/other.js").status_code, 404)

    def test_anchor_versions(self):
        self.assertTrue(fernbild.anchor_ok("1.2.0"))
        self.assertTrue(fernbild.anchor_ok("1.10.0"))
        self.assertFalse(fernbild.anchor_ok("1.1.9"))
        self.assertFalse(fernbild.anchor_ok(""))


class Door(FbBase):
    def test_off_by_default_under_the_fernzugang_and_404_while_off(self):
        with open(helpers.APP + "/config.default.json") as f:
            c = json.load(f)["chat"]
        self.assertIs(c["fernbild"], False)
        self.assertIs(c["fernbild_zwischenablage"], False)
        import features
        self.assertNotIn("chat.fernbild", features.DEFAULT_ON)
        self.assertIn("fernbild", features.SPARK_ONLY)
        d, _ = self.screen()
        helpers.set_config(fernbild=False)
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]}).status_code, 404)
        self.assertEqual(TestClient(panel.app).post("/api/fernzugang/anker/bildschirm", json={"art": "x11vnc"},
                                                    headers={"Authorization": "Bearer " + d["key"]}).status_code, 404)

    def test_ticket_only_unlocked_online_set_up_and_new_enough(self):
        d, _ = self.screen()
        self.assertEqual(ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]}).status_code, 409)  # offline
        fernzugang.ANKER[d["id"]] = types.SimpleNamespace(seit=time.time(), kanaele={}, wait={})
        try:
            with journal() as j:
                r = ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"], "breite": 1600, "hoehe": 900})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("fernzugang: bild_ticket | admin | 1", j.getvalue())
            tk = next(v for v in fernzugang.TICKETS.values() if v.get("art") == "bildschirm")
            self.assertEqual((tk["cols"], tk["rows"], tk["mac"]), (1600, 900, ("", "")))
            fernzugang._update(d["id"], anker="1.1.0")
            self.assertEqual(ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]}).status_code, 409)
            fernzugang._update(d["id"], anker="1.2.0", bild=None)
            self.assertEqual(ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]}).status_code, 409)
            fernzugang._update(d["id"], bild="x11vnc")
            fernzugang.ENTSPERRT.clear()
            self.assertEqual(ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]}).status_code, 423)
        finally:
            fernzugang.ANKER.pop(d["id"], None)

    def test_a_mac_sign_in_only_in_the_ticket(self):
        d, pw = self.screen("mac")
        self.assertEqual(pw["passwort"], "")
        fernzugang.ANKER[d["id"]] = types.SimpleNamespace(seit=time.time(), kanaele={}, wait={})
        try:
            self.assertEqual(ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]}).status_code, 400)
            with journal() as j:
                r = ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"], "benutzer": "dominik",
                                                                         "passwort": "Geheim-Mac-42"})
            self.assertEqual(r.status_code, 200, r.text)
            for secret in ("dominik", "Geheim-Mac-42"):
                self.assertNotIn(secret, j.getvalue())
                with open(fernzugang.FILE, encoding="utf-8") as f:
                    self.assertNotIn(secret, f.read())
        finally:
            fernzugang.ANKER.pop(d["id"], None)

    def test_the_anchor_gets_a_password_only_with_its_key_and_only_sealed_here(self):
        d = self.pair()
        c = TestClient(panel.app)
        self.assertEqual(c.post("/api/fernzugang/anker/bildschirm", json={"art": "x11vnc"},
                                headers={"Authorization": "Bearer fz_wrong"}).status_code, 403)
        self.assertEqual(c.post("/api/fernzugang/anker/bildschirm", json={"art": "teamviewer"},
                                headers={"Authorization": "Bearer " + d["key"]}).status_code, 400)
        with journal() as j:
            r = c.post("/api/fernzugang/anker/bildschirm", json={"art": "grd"}, headers={"Authorization": "Bearer " + d["key"]})
        pw = r.json()["passwort"]
        self.assertRegex(pw, r"^[A-Za-z0-9]{24}$")
        self.assertEqual(r.json()["benutzer"], "spark-bild")
        self.assertNotIn(pw, j.getvalue())
        with open(fernzugang.FILE, encoding="utf-8") as f:
            self.assertNotIn(pw, f.read())
        self.assertRegex(c.post("/api/fernzugang/anker/bildschirm", json={"art": "x11vnc"},
                                headers={"Authorization": "Bearer " + d["key"]}).json()["passwort"], r"^[A-Za-z0-9]{8}$")
        self.assertEqual(c.delete("/api/fernzugang/anker/bildschirm", headers={"Authorization": "Bearer " + d["key"]}).status_code, 200)
        self.assertIsNone(fernzugang._read()["geraete"][d["id"]].get("bild"))


class Anchor(unittest.TestCase):
    """The program's side: which kind fits the session, the channel only to the one port, `bildschirm` and its end."""

    def test_the_kind_from_the_graphical_session(self):
        p = program()

        def ctx_for(sessions):
            c = types.SimpleNamespace(out=lambda cmd: sessions.get(tuple(cmd[:3]), "") if cmd[1] == "show-session" else
                                      "\n".join(f"{k} 1000 x seat0" for k in sessions_ids))
            return c
        cases = {"x11": ("x11vnc", "anna"), "wayland gnome": ("grd", "anna"), "wayland sway": ("wayvnc", "anna")}
        for kind, want in cases.items():
            typ, _, desk = kind.partition(" ")
            sessions_ids = ["2"]
            sessions = {("loginctl", "show-session", "2"): f"Type={typ}\nDesktop={desk}\nName=anna\nClass=user\nActive=yes\n"}
            self.assertEqual(p.linux_bild_art(ctx_for(sessions)), want, kind)
        sessions_ids = ["3"]
        sessions = {("loginctl", "show-session", "3"): "Type=tty\nName=root\nClass=user\nActive=yes\n"}
        with self.assertRaises(p.Fehler):
            p.linux_bild_art(ctx_for(sessions))

    def test_the_channel_only_to_the_one_screen_port_and_only_when_set_up(self):
        p = program()
        sent = []
        ws = types.SimpleNamespace(send_json=sent.append)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        with unittest.mock.patch.dict(p.BILD, {"x11vnc": srv.getsockname()[1]}):
            p.Lauf(ws, "")._control({"typ": "auf", "kanal": 3, "ziel": "bild"})      # not set up: no channel
            self.assertEqual(sent[-1], {"typ": "fehler", "kanal": 3})
            run = p.Lauf(ws, "x11vnc")
            run._control({"typ": "auf", "kanal": 4, "ziel": "bild", "host": "10.0.0.1"})   # no address from the panel
            self.assertEqual(sent[-1], {"typ": "offen", "kanal": 4})
            conn, _ = srv.accept()
            self.assertEqual(conn.getpeername()[0], "127.0.0.1")
            conn.close()
            run._close(4, False)
        self.assertEqual(p.Lauf(ws, "teamviewer").bild, "")
        srv.close()

    def test_bildschirm_sets_up_x11vnc_on_demand_only_on_127_0_0_1_and_aus_takes_it_away(self):
        p = program()
        root = tempfile.mkdtemp(prefix="anker-bild-")
        ran = []
        ctx = p.Ctx(system="Linux", root=root, run=lambda c: ran.append(c) or 0)
        ctx.euid = lambda: 0
        ctx.out = lambda cmd: ("2 1000 anna seat0\n" if cmd[1] == "list-sessions"
                               else "Type=x11\nDesktop=xfce\nName=anna\nClass=user\nActive=yes\n")
        conf = {"url": "https://spark.example.org", "fp": "", "id": "g_000000000001", "key": "fz_k"}
        p.write(ctx.path(p.CONF), json.dumps(conf), 0o640)
        calls = []

        def http(base, fp, method, path, body=None, key=None, timeout=20):
            calls.append((method, path, body, key))
            return 200, json.dumps({"passwort": "Ab3dEf7h"}).encode()
        with unittest.mock.patch.object(p, "http_call", http), unittest.mock.patch.object(p.shutil, "which", lambda n: "/usr/bin/" + n):
            self.assertEqual(p.cmd_screen(types.SimpleNamespace(aus=""), ctx=ctx), 0)
            with open(ctx.path(p.BILD_UNITS[0])) as f:
                self.assertIn("ListenStream=127.0.0.1:5930", f.read())
            with open(ctx.path(p.BILD_UNITS[1])) as f:
                unit = f.read()
            self.assertIn("-passwdfile /etc/spark-anker/bild.pw", unit)
            self.assertIn("-inetd", unit)
            self.assertEqual(os.stat(ctx.path(p.BILD_PW)).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(open(ctx.path(p.CONF)).read())["bild"], "x11vnc")
            self.assertIn(["systemctl", "enable", "--now", "spark-anker-bild.socket"], ran)
            self.assertIn(["systemctl", "restart", "spark-anker.service"], ran)
            self.assertEqual(calls[0][:4], ("POST", "/api/fernzugang/anker/bildschirm", {"art": "x11vnc"}, "fz_k"))
            self.assertEqual(p.cmd_screen(types.SimpleNamespace(aus="aus"), ctx=ctx), 0)
        for path in (*p.BILD_UNITS, p.BILD_PW):
            self.assertFalse(os.path.exists(ctx.path(path)), path)
        self.assertNotIn("bild", json.loads(open(ctx.path(p.CONF)).read()))
        self.assertIn(["systemctl", "disable", "--now", "spark-anker-bild.socket"], ran)
        self.assertEqual(calls[-1][:2], ("DELETE", "/api/fernzugang/anker/bildschirm"))
        self.assertIn(p.here(root, p.BILD_UNITS[0]), p.remove_paths(root))      # `entfernen` takes it too
        shutil.rmtree(root, ignore_errors=True)

    def test_gnome_rdp_with_its_own_certificate_and_the_panels_password(self):
        p = program()
        root = tempfile.mkdtemp(prefix="anker-grd-")
        ran = []
        ctx = p.Ctx(system="Linux", root=root, run=lambda c: ran.append(c) or (1 if c[:2] == ["systemctl", "is-enabled"] else 0))
        ctx.euid = lambda: 0
        ctx.ids = lambda n: None
        ctx.out = lambda cmd: ("2 1000 anna seat0\n" if cmd[1] == "list-sessions"
                               else "Type=wayland\nDesktop=GNOME\nName=anna\nClass=user\nActive=yes\n")
        p.write(ctx.path(p.CONF), json.dumps({"url": "https://s.example.org", "fp": "", "id": "g_1", "key": "fz_k"}), 0o640)
        pw = "A" * 24
        with unittest.mock.patch.object(p, "http_call", lambda *a, **k: (200, json.dumps({"passwort": pw}).encode())):
            self.assertEqual(p.cmd_screen(types.SimpleNamespace(aus=""), ctx=ctx), 0)
        self.assertIn(["grdctl", "--system", "rdp", "set-credentials", "spark-bild", pw], ran)
        self.assertIn(["grdctl", "--system", "rdp", "enable"], ran)
        self.assertTrue(any(c[:2] == ["openssl", "req"] for c in ran))
        conf = json.loads(open(ctx.path(p.CONF)).read())
        self.assertEqual((conf["bild"], conf["grd_neu"]), ("grd", True))
        self.assertNotIn(pw, json.dumps(conf))
        ran.clear()
        self.assertEqual(p.cmd_screen(types.SimpleNamespace(aus="aus"), ctx=ctx), 0)
        self.assertIn(["grdctl", "--system", "rdp", "disable"], ran)
        self.assertIn(["systemctl", "disable", "--now", "gnome-remote-desktop.service"], ran)
        shutil.rmtree(root, ignore_errors=True)


def _free(port):
    """A port reserved with helpers._port given back, for a program that binds it itself right after."""
    s = helpers._HELD.pop(port, None)
    if s is not None:
        s.close()
    return port


# the vendored library itself in a real browser, with the page's module shim (fernbild.js fbLaden), against the panel
CLIENT_PAGE = """<!doctype html><meta charset="utf-8"><div id="d"></div>
<script>window.module={exports:{}}</script><script src="/static/guac/guacamole-common.min.js"></script>
<script>const shim=typeof window.module;delete window.module;window.st=[];window.shim=shim;
const tun=new Guacamole.WebSocketTunnel('wss://'+location.host+'/api/fernzugang/bildschirm');const c=new Guacamole.Client(tun),inner=tun.oninstruction;
tun.oninstruction=(op,a)=>{if(op==='spark-rate'){window.rate=a[0];return}inner(op,a)};
c.onstatechange=s=>window.st.push(s);c.onerror=e=>{window.err=e&&e.message};document.getElementById('d').appendChild(c.getDisplay().getElement());
window.go=t=>c.connect('t='+encodeURIComponent(t));window.c=c;window.tun=tun</script>"""


class EndToEnd(FbBase):
    """The whole way for real: Xvfb with x11vnc (the system's screen, its password from the panel), the anchor program
    (TLS pinned) → the panel's sockets on one uvicorn → the local port → guacd → the browser's Guacamole tunnel."""

    def setUp(self):
        super().setUp()
        for tool in ("Xvfb", "x11vnc", "guacd"):
            if not shutil.which(tool) and not os.path.exists("/usr/sbin/" + tool):
                self.fail(f"{tool} missing (apt install xvfb x11vnc guacd libguac-client-vnc0)")
        import uvicorn
        from fastapi import FastAPI
        from tests.test_fernzugang import _tls_files
        self.procs = []
        only = FastAPI()
        only.include_router(fernzugang.router)
        only.include_router(fernbild.router)
        from fastapi.responses import FileResponse, HTMLResponse

        @only.get("/static/guac/{name}")
        def _guac(name: str):
            path, media = fernbild.guac_file(name)
            return FileResponse(path, media_type=media)

        @only.get("/t")
        def _page():
            return HTMLResponse(CLIENT_PAGE)
        self.tmp = tempfile.mkdtemp(prefix="fb-tls-")
        cf, kf, self.fp = _tls_files(self.tmp)
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error",
                                              ssl_certfile=cf, ssl_keyfile=kf, timeout_graceful_shutdown=2,
                                              ssl_context_factory=panel.tls_context))   # the panel's own TLS
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.th = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        helpers.until(lambda: server.started, 20)
        self.base = f"https://localhost:{self.port}"
        self.patches = [unittest.mock.patch.object(fernzugang, "is_admin_browser", lambda c: True),
                        unittest.mock.patch.object(fernzugang, "_login", lambda c: "L")]
        for x in self.patches:
            x.start()
        self.unlock()

    def tearDown(self):
        for x in self.patches:
            x.stop()
        for pr in reversed(self.procs):
            pr.terminate()
            with contextlib.suppress(Exception):
                pr.wait(5)
        self.server.should_exit = True
        self.th.join(10)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def start(self, cmd):
        pr = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(pr)
        return pr

    def display(self):
        for n in range(91, 140):
            if not os.path.exists(f"/tmp/.X11-unix/X{n}") and not os.path.exists(f"/tmp/.X{n}-lock"):
                self.start(["Xvfb", f":{n}", "-screen", "0", "800x600x24", "-nolisten", "tcp"])
                if helpers.until(lambda: os.path.exists(f"/tmp/.X11-unix/X{n}"), 10):
                    return n
        self.fail("no X display")

    def test_the_screen_through_the_anchor_watching_first(self):
        import websockets.sync.client as wsc
        d, pw = self.screen()
        password = pw["passwort"]
        n = self.display()
        vnc = _free(helpers._port())
        self.start(["x11vnc", "-display", f":{n}", "-localhost", "-rfbport", str(vnc), "-passwd", password,
                    "-forever", "-shared", "-quiet", "-noxdamage", "-nolookup"])
        gd = _free(helpers._port())
        self.start([shutil.which("guacd") or "/usr/sbin/guacd", "-f", "-b", "127.0.0.1", "-l", str(gd), "-L", "error"])
        self.assertTrue(helpers.until(lambda: _open(vnc) and _open(gd), 20), "x11vnc or guacd did not start")
        p = program()
        p.BILD["x11vnc"] = vnc
        ws = p.WS.open(self.base, self.fp, "/api/fernzugang/anker", d["key"])
        run = p.Lauf(ws, "x11vnc")
        threading.Thread(target=run.run, daemon=True).start()
        self.assertTrue(helpers.until(lambda: d["id"] in fernzugang.ANKER and fernzugang._read()["geraete"][d["id"]].get("anker") == p.VERSION))
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with unittest.mock.patch.object(fernbild, "GUACD", ("127.0.0.1", gd)), \
                unittest.mock.patch.object(fernbild, "RATE_S", 0), journal() as j:
            r = ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"], "breite": 1024, "hoehe": 768,
                                                                    "sparsam": True})
            self.assertEqual(r.status_code, 200, r.text)
            b = wsc.connect(f"wss://localhost:{self.port}/api/fernzugang/bildschirm?t={r.json()['ticket']}", ssl=ctx,
                            subprotocols=["guacamole"], additional_headers={"Origin": self.base}, max_size=2 ** 24,
                            open_timeout=helpers.WS_OPEN_S)
            first = b.recv(timeout=30)
            self.assertRegex(first, r"^0\.,8\.[0-9a-f]{8};$")                      # the tunnel's id first
            seen = set()
            for _ in range(200):
                got, rest = fernbild.split(b.recv(timeout=30))
                self.assertEqual(rest, "")                                          # whole instructions only
                seen |= {e[0] for _, e in got}
                if {"size", "img", "blob", "sync", "spark-rate"} <= seen:
                    break
            self.assertTrue({"size", "img", "blob", "sync"} <= seen, seen)          # the screen's picture came
            self.assertIn("spark-rate", seen)                                      # and the rate for the page
            self.assertEqual(fernzugang.counts()["bildschirm"], 1)
            b.send(fernbild.enc("", "ping", "42"))
            for _ in range(100):
                m = b.recv(timeout=30)
                if m.startswith("0.,4.ping"):
                    break
            self.assertEqual(m, fernbild.enc("", "ping", "42"))
            b.send(fernbild.enc(fernbild.STEUERN, "1"))
            b.send(fernbild.enc("mouse", "10", "10", "0"))
            self.assertTrue(helpers.until(lambda: "fernzugang: bild_steuern | an | 1" in j.getvalue()))
            b.send("x" * (fernbild.MAX_IN + 1))                                     # too big: the session ends
            self.assertTrue(helpers.until(lambda: not fernzugang.SITZUNG, 15))
            # the session leaves SITZUNG first and writes its last lines after closing everything
            self.assertTrue(helpers.until(lambda: "fernzugang: bild_rate | kb_s |" in j.getvalue(), 15))
            with contextlib.suppress(Exception):
                b.close()
        out = j.getvalue()
        self.assertIn("fernzugang: bild_auf | admin | 1", out)
        self.assertIn("fernzugang: bild_zu | zu_gross | 0", out)
        self.assertRegex(out, r"fernzugang: bild_rate \| kb_s \| \d+")
        self.assertNotIn(password, out)
        self.assertEqual(fernzugang.verlauf_read()[0]["art"], "bildschirm")
        ws.sock.shutdown(socket.SHUT_RDWR)

    def test_the_vendored_client_in_a_real_browser(self):
        """guacamole-common-js 1.5.0 as the page loads it: the tunnel's id and ping, the picture of the screen, the
        panel's rate; „Trennen“ ends the session."""
        from tests.test_ui_browser import browser_ok
        if not browser_ok():
            raise unittest.SkipTest("no Playwright/Chromium here")
        from tests.test_ui_browser import async_playwright, chromium
        d, pw = self.screen()
        n = self.display()
        vnc = _free(helpers._port())
        self.start(["x11vnc", "-display", f":{n}", "-localhost", "-rfbport", str(vnc), "-passwd", pw["passwort"],
                    "-forever", "-shared", "-quiet", "-noxdamage", "-nolookup"])
        gd = _free(helpers._port())
        self.start([shutil.which("guacd") or "/usr/sbin/guacd", "-f", "-b", "127.0.0.1", "-l", str(gd), "-L", "error"])
        self.assertTrue(helpers.until(lambda: _open(vnc) and _open(gd), 20), "x11vnc or guacd did not start")
        p = program()
        p.BILD["x11vnc"] = vnc
        ws = p.WS.open(self.base, self.fp, "/api/fernzugang/anker", d["key"])
        threading.Thread(target=p.Lauf(ws, "x11vnc").run, daemon=True).start()
        self.assertTrue(helpers.until(lambda: fernzugang._read()["geraete"][d["id"]].get("anker") == p.VERSION))

        async def go():
            async with async_playwright() as pl:
                exe = chromium()
                br = await pl.chromium.launch(**({"executable_path": exe} if exe else {}))
                ctx = await br.new_context(ignore_https_errors=True)
                pg = await ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                await pg.goto(self.base + "/t")
                self.assertEqual(await pg.evaluate("window.shim"), "object")
                self.assertFalse(await pg.evaluate("'module' in window"))           # the shim is gone again
                r = ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"], "breite": 800, "hoehe": 600})
                self.assertEqual(r.status_code, 200, r.text)
                await pg.evaluate("t=>window.go(t)", r.json()["ticket"])
                await pg.wait_for_function("window.st.includes(3)", timeout=30000)      # CONNECTED
                await pg.wait_for_function("window.c.getDisplay().getWidth()===800", timeout=30000)
                self.assertEqual(await pg.evaluate("window.c.getDisplay().getHeight()"), 600)
                await pg.wait_for_timeout(1500)                                        # the tunnel's pings pass
                self.assertNotIn(5, await pg.evaluate("window.st"))                     # still connected
                self.assertIsNone(await pg.evaluate("window.err||null"))
                await pg.evaluate("window.c.disconnect()")
                await br.close()
                return errors
        with unittest.mock.patch.object(fernbild, "GUACD", ("127.0.0.1", gd)), journal() as j:
            errors = asyncio.run(go())
            self.assertTrue(helpers.until(lambda: not fernzugang.SITZUNG, 15))
            self.assertTrue(helpers.until(lambda: "fernzugang: bild_zu |" in j.getvalue(), 15))
        self.assertEqual(errors, [])
        ws.sock.shutdown(socket.SHUT_RDWR)

    def test_no_guacd_ends_with_a_fixed_word(self):
        import websockets.sync.client as wsc
        d, _ = self.screen()
        p = program()
        ws = p.WS.open(self.base, self.fp, "/api/fernzugang/anker", d["key"])
        threading.Thread(target=p.Lauf(ws, "x11vnc").run, daemon=True).start()
        self.assertTrue(helpers.until(lambda: fernzugang._read()["geraete"][d["id"]].get("anker") == p.VERSION))
        dead = _free(helpers._port())
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with unittest.mock.patch.object(fernbild, "GUACD", ("127.0.0.1", dead)), \
                unittest.mock.patch.object(fernbild, "_start_guacd", lambda: None), journal() as j:
            r = ADMIN.post("/api/admin/fernzugang/bildschirm", json={"geraet": d["id"]})
            b = wsc.connect(f"wss://localhost:{self.port}/api/fernzugang/bildschirm?t={r.json()['ticket']}", ssl=ctx,
                            subprotocols=["guacamole"], additional_headers={"Origin": self.base}, open_timeout=helpers.WS_OPEN_S)
            self.assertEqual(b.recv(timeout=30), fernbild.enc("error", "guacd", "519"))
            self.assertTrue(helpers.until(lambda: not fernzugang.SITZUNG))
        self.assertIn("fernzugang: bild_guacd | fehlt | 0", j.getvalue())
        ws.sock.shutdown(socket.SHUT_RDWR)

    def test_foreign_origin_and_a_shell_ticket_refused(self):
        import websockets.sync.client as wsc
        d, _ = self.screen()
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        from tests.test_fernzugang import secrets_ticket
        t = secrets_ticket(d["id"], 80, 24)                                         # a shell's ticket
        for origin, ticket in (("https://evil.example", "x" * 40), (self.base, t)):
            with self.assertRaises(Exception):
                c = wsc.connect(f"wss://localhost:{self.port}/api/fernzugang/bildschirm?t={ticket}", ssl=ctx,
                                subprotocols=["guacamole"], additional_headers={"Origin": origin}, open_timeout=helpers.WS_OPEN_S)
                c.recv(timeout=10)


def _open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


if __name__ == "__main__":
    unittest.main()
