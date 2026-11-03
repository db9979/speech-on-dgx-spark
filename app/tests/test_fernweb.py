"""Fernzugang, Webdienste (fernweb.py, anker/spark-anker.py „ziel: web“, Dominik 2026-10-30 „1a, 2a“): one self-test for
every protection rule. Off by default under the Fernzugang and 404 while off; only an admin in the browser on the
unlocked page; the targets on both sides (the panel's ziel_ok and the anchor's own web_ziel): loopback always, private
addresses only with „Netz dahinter“, never this Pi's own networks, link-local, the metadata address, multicast, a name
or the panel's own address; „Netz dahinter“ asks for the code; an old anchor (before 1.6.0) gets no tunnel and the page
says „Anker aktualisieren“; the ticket works once; none of the panel's cookies and no Authorization reach the service,
each service keeps its own cookies apart; frames only from the panel; at most MAX_TUNNEL tunnels and MAX_KANAELE
connections each, with flow control; the Notaus, Sperren and the switch end every tunnel and its channels. The whole
way for real: the anchor program, the panel's sockets on one uvicorn with TLS, the door, a web service with a
WebSocket. No test depends on the time of day."""
import asyncio
import contextlib
import http.client
import ipaddress
import json
import pathlib
import socket
import ssl
import tempfile
import threading
import unittest
import unittest.mock

from tests import helpers
from tests.test_fernzugang import ADMIN, CODE, Base, journal, program  # noqa: F401

import fernweb  # noqa: E402
import fernzugang  # noqa: E402
import h11  # noqa: E402
import notaus  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

NETZE = (ipaddress.ip_network("192.168.178.0/24"),)   # „this Pi's own network“ in the tests


def reset_web():
    fernweb.TUNNEL.clear()
    fernweb.TICKETS.clear()
    fernweb.GEFUNDEN.clear()


class FwBase(Base):
    def setUp(self):
        super().setUp()
        reset_web()
        helpers.set_config(fernweb=True, fernweb_adresse="")

    def tearDown(self):
        helpers.set_config(fernweb=False, fernweb_adresse="")
        reset_web()
        super().tearDown()

    def system(self, version="1.6.0"):
        d = self.pair()
        fernzugang._update(d["id"], anker=version)
        return d


class Targets(unittest.TestCase):
    """The same matrix on both sides: the panel decides, and the anchor decides again for itself."""
    CASES = (   # host, netz, panel, anchor
        ("127.0.0.1", False, True, True), ("::1", False, True, True), ("[::1]", False, True, True),
        ("127.0.0.53", False, True, True), ("::ffff:127.0.0.1", False, True, True),
        ("192.168.1.5", False, False, False), ("192.168.1.5", True, True, True), ("10.1.2.3", True, True, True),
        ("172.20.0.4", True, True, True), ("fd00::4", True, True, True),
        ("192.168.178.20", True, False, True),        # in this Pi's own network: the panel never
        ("169.254.169.254", True, False, False), ("169.254.1.1", True, False, False), ("fe80::1", True, False, False),
        ("224.0.0.1", True, False, False), ("0.0.0.0", True, False, False), ("::", True, False, False),
        ("255.255.255.255", True, False, False), ("8.8.8.8", True, False, False), ("100.64.0.1", True, False, False),
        ("localhost", True, False, False), ("router.fritz.box", True, False, False), ("", True, False, False))

    def test_the_matrix_on_both_sides(self):
        p = program()
        for host, netz, panel_ok, anchor_ok in self.CASES:
            with self.subTest(host=host, netz=netz):
                self.assertEqual(fernweb.ziel_ok(host, 80, netz, NETZE) is not None, panel_ok)
                self.assertEqual(p.web_ziel({"host": host, "port": 80, "netz": netz}) is not None, anchor_ok)

    def test_ports_and_types_are_checked_too(self):
        p = program()
        for port in (0, 65536, "80", True, None, 80.0):
            self.assertIsNone(fernweb.ziel_ok("127.0.0.1", port))
            self.assertIsNone(p.web_ziel({"host": "127.0.0.1", "port": port}))
        self.assertIsNone(p.web_ziel({"host": "192.168.1.5", "port": 80, "netz": "yes"}))   # only True counts
        self.assertIsNone(fernweb.ziel_ok("192.168.1.5", 80, "yes", NETZE))

    def test_the_anchor_never_reaches_the_panel_it_talks_to(self):
        p = program()
        self.assertIsNone(p.web_ziel({"host": "192.168.1.2", "port": 443, "netz": True}, "192.168.1.2"))
        self.assertIsNone(p.web_ziel({"host": "127.0.0.1", "port": 443}, "127.0.0.1"))   # a panel on the same machine
        self.assertEqual(p.web_ziel({"host": "192.168.1.3", "port": 443, "netz": True}, "192.168.1.2"), ("192.168.1.3", 443))

    def test_the_pis_own_networks_from_its_routes(self):
        route = ("Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
                 "eth0\t00000000\t01B2A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
                 "eth0\t00B2A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n")
        real = open
        def fake(path, *a, **k):
            if path == "/proc/net/route":
                import io
                return io.StringIO(route)
            if path == "/proc/net/ipv6_route":
                raise OSError
            return real(path, *a, **k)
        with unittest.mock.patch("builtins.open", fake):
            fernweb._NETZE["t"] = 0
            nets = fernweb.eigene_netze()
        fernweb._NETZE["t"] = 0
        self.assertEqual(nets, (ipaddress.ip_network("192.168.178.0/24"),))   # the default route is no network


class Heads(unittest.TestCase):
    def tunnel(self, port=8080, schema="http"):
        t = fernweb.Tunnel.__new__(fernweb.Tunnel)
        t.dienst = {"id": "w_0011aabb", "schema": schema, "host": "127.0.0.1", "port": port, "pfad": "/"}
        t.marke, t.panel = "swabc12345_", "https://pi.example:31443"
        return t

    def test_cookie_isolation_none_of_the_panels_and_no_authorization(self):
        t = self.tunnel()
        heads = [(b"host", b"pi:31090"), (b"cookie", b"spark_admin=geheim; spark_profile=p; __Host-spark-tunnel=x; "
                                                   b"swabc12345_sid=1; swffff0000_sid=fremd; __Host-swabc12345_tok=2"),
                 (b"authorization", b"Basic YWRtaW46eA=="), (b"proxy-authorization", b"x"), (b"x-forwarded-for", b"1.2.3.4"),
                 (b"forwarded", b"for=1.2.3.4"), (b"x-real-ip", b"1.2.3.4"), (b"origin", b"https://pi:31090"),
                 (b"referer", b"https://pi:31090/a?b"), (b"accept", b"*/*"), (b"connection", b"keep-alive")]
        out = dict(fernweb.kopf_rein(heads, t, "https://pi:31090", None))
        self.assertEqual(out[b"cookie"], b"sid=1; __Host-tok=2")       # only this service's own, without the mark
        for k in (b"authorization", b"proxy-authorization", b"x-forwarded-for", b"forwarded", b"x-real-ip", b"connection"):
            self.assertNotIn(k, out)
        self.assertEqual((out[b"host"], out[b"origin"], out[b"referer"]),
                         (b"127.0.0.1:8080", b"http://127.0.0.1:8080", b"http://127.0.0.1:8080/a?b"))
        self.assertEqual(out[b"accept"], b"*/*")
        foreign = dict(fernweb.kopf_rein([(b"origin", b"https://evil.example"), (b"referer", b"https://evil.example/")],
                                         t, "https://pi:31090", None))
        self.assertNotIn(b"origin", foreign)                            # a foreign page's Origin never becomes the service's
        self.assertNotIn(b"referer", foreign)
        self.assertNotIn(b"cookie", dict(fernweb.kopf_rein([(b"cookie", b"spark_admin=geheim")], t, "https://pi:31090", None)))

    def test_answers_framed_only_by_the_panel_cookies_marked_location_a_path(self):
        t = self.tunnel()
        heads = [(b"set-cookie", b"sid=1; Domain=pi; Path=/; HttpOnly"), (b"set-cookie", b"__Host-tok=2; Path=/; Secure"),
                 (b"x-frame-options", b"DENY"), (b"strict-transport-security", b"max-age=1"), (b"clear-site-data", b'"*"'),
                 (b"alt-svc", b"h3=\":443\""), (b"content-security-policy", b"default-src 'self'; frame-ancestors 'self'"),
                 (b"location", b"http://127.0.0.1:8080/ziel?x=1"), (b"content-type", b"text/html")]
        out = fernweb.kopf_raus(heads, t)
        cookies = [v for k, v in out if k == b"set-cookie"]
        self.assertEqual(cookies, [b"swabc12345_sid=1; Path=/; HttpOnly; Secure", b"__Host-swabc12345_tok=2; Path=/; Secure"])
        names = [k for k, _ in out]
        for k in (b"x-frame-options", b"strict-transport-security", b"clear-site-data", b"alt-svc"):
            self.assertNotIn(k, names)
        csp = [v for k, v in out if k == b"content-security-policy"]
        self.assertEqual(csp, [b"default-src 'self'", b"frame-ancestors https://pi.example:31443"])
        self.assertIn((b"location", b"/ziel?x=1"), out)
        for loc, want in (("http://localhost:8080/a", "/a"), ("https://127.0.0.1:8080/a", "/a"), ("/rel", "/rel"),
                          ("https://example.org/x", "https://example.org/x"), ("http://127.0.0.1:9999/a", "http://127.0.0.1:9999/a")):
            self.assertEqual(fernweb._location(loc, t), want)

    def test_a_service_cookie_round_trip_keeps_its_name(self):
        t = self.tunnel()
        c = fernweb._set_cookie("grafana_session=abc; Path=/; SameSite=Lax", t.marke)
        name, val = c.split(";")[0].split("=", 1)
        out = dict(fernweb.kopf_rein([(b"cookie", f"{name}={val}".encode())], t, "https://pi:31090", None))
        self.assertEqual(out[b"cookie"], b"grafana_session=abc")


class FlowControl(unittest.TestCase):
    def test_the_panel_waits_for_the_anchors_more(self):
        sent = []

        class A:
            kanaele = {}

            async def send_bytes(self, b):
                sent.append(len(b) - 1)

            async def send_json(self, d):
                sent.append(d)

        async def go():
            k = fernweb.Kanal(A(), 70, None)
            A.kanaele[70] = k
            w = asyncio.create_task(k.write(b"x" * (fernweb.FENSTER + fernweb.STUECK)))
            await asyncio.sleep(0.05)
            before = sum(x for x in sent if isinstance(x, int))
            self.assertEqual(before, fernweb.FENSTER)          # the window, then it waits
            self.assertFalse(w.done())
            k.mehr(fernweb.STUECK)
            await asyncio.wait_for(w, 2)
            self.assertEqual(sum(x for x in sent if isinstance(x, int)), fernweb.FENSTER + fernweb.STUECK)
            await k.from_anker(b"y" * (2 * fernweb.FENSTER + 1))   # a broken anchor: the channel closes
            self.assertTrue(k.zu)
            self.assertIn({"typ": "zu", "kanal": 70}, sent)
        asyncio.run(go())

    def test_the_anchor_closes_a_channel_flooded_past_its_window(self):
        p = program()

        class WS:
            def __init__(self):
                self.out = []
                self.sock = None

            def send_json(self, d):
                self.out.append(d)
        ws = WS()
        run = p.Lauf(ws, "")
        a, b = socket.socketpair()
        run.kanaele[70] = a
        run.web[70] = {"raus": 0, "rein": bytearray(), "genommen": 0}
        a.setblocking(False)
        run._web_rein(70, b"z" * 1000)
        self.assertEqual(b.recv(2000), b"z" * 1000)
        self.assertIn({"typ": "mehr", "kanal": 70, "n": 1000}, ws.out)
        b.setblocking(False)
        with contextlib.suppress(OSError):
            while True:
                a.send(b"x" * 65536)                       # the service reads nothing: its buffer is full
        run._web_rein(70, b"q" * (p.WEB_FENSTER + 1))
        self.assertNotIn(70, run.kanaele)                  # past the window: closed
        self.assertIn({"typ": "zu", "kanal": 70}, ws.out)
        b.close()

    def test_the_anchor_reads_no_more_while_the_panel_has_not_taken_it(self):
        p = program()
        src = pathlib.Path(fernzugang.PROGRAM).read_text()
        self.assertIn('self.web[k]["raus"] < WEB_FENSTER', src)    # select() leaves such a channel alone
        self.assertEqual((p.WEB_FENSTER, p.WEB_ERSTER, p.WEB_MAX), (fernweb.FENSTER, fernweb.ERSTER, fernweb.LETZTER))

    def test_the_anchor_opens_web_channels_only_by_its_rules(self):
        p = program()

        class WS:
            out = []
            sock = None

            def send_json(self, d):
                self.out.append(d)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        run = p.Lauf(WS(), "")
        run._control({"typ": "auf", "kanal": 70, "ziel": "web", "host": "192.168.1.5", "port": port})
        self.assertEqual(WS.out[-1], {"typ": "fehler", "kanal": 70, "grund": "ziel"})
        run._control({"typ": "auf", "kanal": 5, "ziel": "web", "host": "127.0.0.1", "port": port})   # below 64: no web
        self.assertNotIn(5, run.web)
        run._control({"typ": "auf", "kanal": 70, "ziel": "web", "host": "127.0.0.1", "port": port})
        self.assertEqual(WS.out[-1], {"typ": "offen", "kanal": 70})
        self.assertIn(70, run.web)
        run._control({"typ": "zu", "kanal": 70})
        self.assertNotIn(70, run.web)
        srv.close()


class Ports(unittest.TestCase):
    def test_listening_ports_from_proc_with_names_only_where_visible(self):
        p = program()
        d = tempfile.mkdtemp()
        import os
        os.makedirs(d + "/proc/net")
        with open(d + "/proc/net/tcp", "w") as f:   # 127.0.0.1:3000 and 0.0.0.0:22 listen, 10.0.0.5:8080 not reached
            f.write("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
                    "   0: 0100007F:0BB8 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 111 1\n"
                    "   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 222 1\n"
                    "   2: 0500000A:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 333 1\n"
                    "   3: 0100007F:1F91 0100007F:0BB8 01 00000000:00000000 00:00000000 00000000     0        0 444 1\n")
        os.makedirs(d + "/proc/77/fd")
        os.symlink("socket:[111]", d + "/proc/77/fd/3")
        with open(d + "/proc/77/comm", "w") as f:
            f.write("grafana\n")
        self.assertEqual(p._listen_linux(d), {3000: ("127.0.0.1", "grafana"), 22: ("127.0.0.1", "")})

    def test_netstat_on_mac_and_windows(self):
        p = program()
        mac = ("Active Internet connections (including servers)\n"
               "tcp4       0      0  127.0.0.1.8080         *.*                    LISTEN     \n"
               "tcp6       0      0  *.5000                 *.*                    LISTEN     \n"
               "tcp4       0      0  192.168.1.4.9000       *.*                    LISTEN     \n")
        self.assertEqual(p._listen_text(mac, "mac"), {8080: ("127.0.0.1", ""), 5000: ("127.0.0.1", "")})
        win = ("  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1044\n"
               "  TCP    [::1]:8443             [::]:0                 LISTENING       2000\n"
               "  TCP    127.0.0.1:5000         127.0.0.1:50000        ESTABLISHED     12\n")
        self.assertEqual(p._listen_text(win, {"pids": {"1044": "svchost.exe"}}), {135: ("127.0.0.1", "svchost.exe"), 8443: ("::1", "")})

    def test_the_kind_of_a_port_http_or_tcp(self):
        import http.server
        p = program()
        class H(http.server.BaseHTTPRequestHandler):
            server_version, sys_version = "nginx/1.27", ""

            def do_HEAD(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

            def handle(self):
                with contextlib.suppress(Exception):    # the TLS probe first: garbage to a plain server
                    super().handle()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        banner = socket.socket()
        banner.bind(("127.0.0.1", 0))
        banner.listen(4)

        def greet():
            while True:
                try:
                    c, _ = banner.accept()
                except OSError:
                    return
                c.sendall(b"SSH-2.0-OpenSSH_9\r\n")
                c.close()
        threading.Thread(target=greet, daemon=True).start()
        try:
            self.assertEqual(p.port_art("127.0.0.1", srv.server_port), ("http", "nginx"))
            self.assertEqual(p.port_art("127.0.0.1", banner.getsockname()[1]), ("tcp", ""))
        finally:
            srv.shutdown()
            banner.close()

    def test_the_panel_keeps_ports_names_and_kinds_only(self):
        async def go():
            await fernweb.on_ports("g_000000000001", {"liste": [
                {"port": 3000, "prog": "graf<script>ana", "art": "http", "pfad": "/etc"}, {"port": 99999, "prog": "x"},
                {"port": 22, "prog": "sshd", "art": "ssh"}, "kaputt"]})
        asyncio.run(go())
        self.assertEqual(fernweb.GEFUNDEN["g_000000000001"]["liste"],
                         [{"port": 3000, "prog": "grafscriptana", "art": "http"}, {"port": 22, "prog": "sshd", "art": "tcp"}])
        fernweb.GEFUNDEN.clear()


class Door(FwBase):
    def test_off_by_default_under_the_fernzugang_and_404_while_off(self):
        with open(helpers.APP + "/config.default.json") as f:
            c = json.load(f)["chat"]
        self.assertIs(c["fernweb"], False)
        self.assertEqual(c["fernweb_adresse"], "")
        import features
        self.assertNotIn("chat.fernweb", features.DEFAULT_ON)
        self.assertIn("fernweb", features.SPARK_ONLY)
        d = self.system()
        helpers.set_config(fernweb=False)
        for method, path in (("GET", f"/api/admin/fernzugang/web/{d['id']}"), ("POST", "/api/admin/fernzugang/web/oeffnen"),
                             ("GET", "/api/admin/fernzugang/web/tunnel"), ("POST", f"/api/admin/fernzugang/web/{d['id']}/suchen")):
            self.assertEqual(ADMIN.request(method, path, json={}).status_code, 404, path)
        self.assertFalse(ADMIN.get("/api/admin/fernzugang").json()["webdienste"])
        self.assertEqual(fernweb.for_live(), {"tunnel": 0})

    def test_only_the_unlocked_admin_in_the_browser(self):
        d = self.system()
        fernzugang.ENTSPERRT.clear()
        self.assertEqual(ADMIN.get(f"/api/admin/fernzugang/web/{d['id']}").status_code, 423)
        self.unlock()
        self.assertEqual(ADMIN.get(f"/api/admin/fernzugang/web/{d['id']}").status_code, 200)
        self.assertIn(TestClient(panel.app).get(f"/api/admin/fernzugang/web/{d['id']}").status_code, (401, 403))

    def test_netz_dahinter_asks_for_the_code_and_off_blocks_private_targets(self):
        self.assertIn(("POST", "/api/admin/fernzugang/web/{gid}/netz"), stufen.LIST)
        self.assertEqual(stufen.LIST[("POST", "/api/admin/fernzugang/web/{gid}/netz")][0], stufen.PROTECT)
        d = self.system()
        base = f"/api/admin/fernzugang/web/{d['id']}"
        r = ADMIN.post(base + "/dienste", json={"name": "Router", "schema": "http", "host": "192.168.1.1", "port": 80})
        self.assertEqual(r.status_code, 400)                            # off: never a private address
        self.assertEqual(ADMIN.post(base + "/netz", json={"an": True}).status_code, 428)   # without the code
        with unittest.mock.patch.object(fernweb, "eigene_netze", lambda: NETZE):
            self.assertEqual(ADMIN.post(base + "/netz", json={"an": True}, headers=CODE).status_code, 200)
            r = ADMIN.post(base + "/dienste", json={"name": "Router", "schema": "http", "host": "192.168.1.1", "port": 80})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(ADMIN.post(base + "/dienste", json={"name": "Pi", "schema": "http", "host": "192.168.178.5",
                                                                 "port": 80}).status_code, 400)   # the Pi's own network
            with journal() as j:
                self.assertEqual(ADMIN.post(base + "/netz", json={"an": False}, headers=CODE).status_code, 200)
        self.assertEqual(ADMIN.get(base).json()["dienste"], [])           # off again: the private service is gone
        self.assertIn("fernzugang: web_netz | aus | 0", j.getvalue())
        self.assertNotIn("192.168", j.getvalue())

    def test_an_old_anchor_shows_anker_aktualisieren_and_gets_no_tunnel(self):
        d = self.system("1.5.0")
        base = f"/api/admin/fernzugang/web/{d['id']}"
        r = ADMIN.post(base + "/dienste", json={"name": "Grafana", "schema": "http", "port": 3000})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(ADMIN.get(base).json()["anker_ok"])
        row = next(x for x in ADMIN.get("/api/admin/fernzugang").json()["geraete"] if x["id"] == d["id"])
        self.assertFalse(row["web_anker"])
        fernzugang.ANKER[d["id"]] = fernzugang.Anker(None, d["id"])
        r = ADMIN.post("/api/admin/fernzugang/web/oeffnen", json={"geraet": d["id"], "dienst": r.json()["dienst"]["id"]}, headers=CODE)
        self.assertEqual((r.status_code, r.json()["detail"]), (409, "anker_alt"))
        self.assertIn("Anker aktualisieren", pathlib.Path(helpers.APP + "/panel/static/js/fernweb.js").read_text())
        self.assertEqual(ADMIN.post(base + "/suchen").status_code, 409)

    def test_services_are_checked_and_logged_without_names_or_addresses(self):
        d = self.system()
        base = f"/api/admin/fernzugang/web/{d['id']}"
        for bad in ({"name": "", "schema": "http", "port": 80}, {"name": "x", "schema": "ftp", "port": 80},
                    {"name": "x", "schema": "http", "port": 0}, {"name": "x", "schema": "http", "port": 80, "pfad": "x"},
                    {"name": "x", "schema": "http", "port": 80, "pfad": "//evil.example"},
                    {"name": "<b>", "schema": "http", "port": 80}, {"name": "x", "schema": "http", "host": "localhost", "port": 80}):
            self.assertEqual(ADMIN.post(base + "/dienste", json=bad).status_code, 400, bad)
        with journal() as j:
            r = ADMIN.post(base + "/dienste", json={"name": "Mein Grafana", "schema": "http", "port": 3000, "pfad": "/d/geheim"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("fernzugang: web_dienst | neu | 3000", j.getvalue())
        self.assertNotIn("Grafana", j.getvalue())
        self.assertNotIn("geheim", j.getvalue())
        with unittest.mock.patch.object(fernweb, "MAX_DIENSTE", 1):
            self.assertEqual(ADMIN.post(base + "/dienste", json={"name": "b", "schema": "http", "port": 1}).status_code, 409)

    def test_the_address_from_outside_is_a_plain_name(self):
        self.assertIsNone(fernweb.check({"fernweb_adresse": ""}))
        self.assertIsNone(fernweb.check({"fernweb_adresse": "fernwartung.metaluna9.i234.me"}))
        for bad in ("https://x.example", "x.example:31090", "x", "x.example/pfad", "a b.example", "1.2.3.4"):
            self.assertIsNotNone(fernweb.check({"fernweb_adresse": bad}), bad)
        self.assertIn("fernweb.check(ch)", pathlib.Path(helpers.APP + "/panel/admin.py").read_text())   # admin.validate asks it

    def test_the_panel_frames_the_door_only_while_on(self):
        r = ADMIN.get("/")
        self.assertIn("frame-src 'self' https://testserver:31090", r.headers["content-security-policy"])
        helpers.set_config(fernweb=False)
        self.assertIn("frame-src 'self';", ADMIN.get("/").headers["content-security-policy"])


# ---------------------------------------------------------------- the whole way for real
SERVICE_OUT = {}


def _service():
    """A web service on 127.0.0.1 „over there“: / answers with the head it got (JSON), /weiter redirects to its own
    address, /cookie sets one, /ws is a WebSocket echo."""
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    from websockets.sync.server import serve

    def answer(connection, request):
        if request.path == "/ws":
            return None
        heads = {k.lower(): v for k, v in request.headers.raw_items()}
        if request.path == "/weiter":
            return Response(302, "Found", Headers([("Location", f"http://127.0.0.1:{SERVICE_OUT['port']}/ziel"), ("Content-Length", "0")]), b"")
        body = json.dumps(heads).encode()
        h = [("Content-Type", "application/json"), ("Content-Length", str(len(body))), ("X-Frame-Options", "DENY")]
        if request.path == "/cookie":
            h.append(("Set-Cookie", "sid=42; Domain=127.0.0.1; Path=/; HttpOnly"))
        return Response(200, "OK", Headers(h), body)

    def echo(ws):
        for m in ws:
            ws.send(m)
    srv = serve(echo, "127.0.0.1", 0, process_request=answer)
    SERVICE_OUT["port"] = srv.socket.getsockname()[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class EndToEnd(FwBase):
    """The anchor program (TLS pinned) → the panel's sockets on one uvicorn → the door with TLS → the service."""

    def setUp(self):
        super().setUp()
        import uvicorn
        from fastapi import FastAPI
        from tests.test_fernzugang import _tls_files
        only = FastAPI()
        only.include_router(fernzugang.router)
        only.include_router(fernweb.router)
        self.tmp = tempfile.mkdtemp(prefix="fw-tls-")
        cf, kf, self.fp = _tls_files(self.tmp)
        self.door = helpers._port()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cf, kf)

        @only.post("/test/tuer")
        async def _door():
            s = helpers._HELD.pop(self.door, None)
            if s is not None:
                s.close()
            return {"fehler": await fernweb.tor_auf("127.0.0.1", self.door, ctx)}

        @only.post("/test/notaus")
        async def _stop():
            old, _ = notaus.trigger(1, "test", "", "panel")
            await notaus.after_change(old, 1, "test", "panel")
            return {}

        @only.post("/test/zu")
        async def _zu():
            await fernweb.tor_zu("test")
            return {}
        self.port = helpers._port()
        server = uvicorn.Server(uvicorn.Config(only, host="127.0.0.1", port=self.port, log_level="error",
                                              ssl_certfile=cf, ssl_keyfile=kf, timeout_graceful_shutdown=2,
                                              ssl_context_factory=panel.tls_context))
        server.install_signal_handlers = lambda: None
        sock = helpers.take_port(self.port)
        self.th = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        self.th.start()
        self.server = server
        helpers.until(lambda: server.started, 20)
        self.base = f"https://localhost:{self.port}"
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname, self.ctx.verify_mode = False, ssl.CERT_NONE
        self.post("/test/tuer")
        self.svc = _service()
        self.patches = [unittest.mock.patch.object(fernzugang, "is_admin_browser", lambda c: True),
                        unittest.mock.patch.object(fernzugang, "_login", lambda c: "L")]
        for x in self.patches:
            x.start()
        self.unlock()
        d = self.system()
        p = program()
        self.ws = p.WS.open(self.base, self.fp, "/api/fernzugang/anker", d["key"])
        run = p.Lauf(self.ws, "")
        run.peer = "192.0.2.1"     # the panel runs on this machine here; the anchor never reaches its own panel (Targets)
        threading.Thread(target=run.run, daemon=True).start()
        self.assertTrue(helpers.until(lambda: d["id"] in fernzugang.ANKER and
                                      fernzugang._read()["geraete"][d["id"]].get("anker") == p.VERSION))
        self.gid = d["id"]
        r = ADMIN.post(f"/api/admin/fernzugang/web/{self.gid}/dienste",
                       json={"name": "Dienst", "schema": "http", "port": SERVICE_OUT["port"], "pfad": "/"})
        self.assertEqual(r.status_code, 200, r.text)
        self.did = r.json()["dienst"]["id"]

    def tearDown(self):
        with contextlib.suppress(Exception):
            self.post("/test/zu")
        for x in self.patches:
            x.stop()
        with contextlib.suppress(Exception):
            self.ws.sock.shutdown(socket.SHUT_RDWR)
        self.svc.shutdown()
        self.server.should_exit = True
        self.th.join(10)
        super().tearDown()

    def post(self, path):
        c = http.client.HTTPSConnection("127.0.0.1", self.port, context=self.ctx, timeout=20)
        c.request("POST", path, body=b"{}", headers={"Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    def open(self):
        r = ADMIN.post("/api/admin/fernzugang/web/oeffnen", json={"geraet": self.gid, "dienst": self.did},
                       headers={**CODE, "Origin": "https://testserver"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def get(self, path, cookie="", extra=None):
        c = http.client.HTTPSConnection("127.0.0.1", self.door, context=self.ctx, timeout=20)
        heads = {"Host": f"127.0.0.1:{self.door}", **({"Cookie": cookie} if cookie else {}), **(extra or {})}
        c.request("GET", path, headers=heads)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r, body

    def redeem(self):
        d = self.open()
        path = d["url"].split(f":{fernweb.TOR_PORT}", 1)[1]
        r, _ = self.get(path, "spark_admin=geheim")
        self.assertEqual(r.status, 303)
        cookie = r.getheader("Set-Cookie")
        self.assertRegex(cookie, r"^__Host-spark-tunnel=[A-Za-z0-9_\-]{40,}; Path=/; Secure; HttpOnly; SameSite=Strict$")
        return d, path, cookie.split(";")[0]

    def test_through_the_door_once_per_ticket_no_panel_cookie_frames_only_from_the_panel(self):
        with journal() as j:
            d, path, cookie = self.redeem()
            r, _ = self.get(path)
            self.assertEqual(r.status, 403)                                  # the ticket works once
            r, _ = self.get("/")
            self.assertEqual(r.status, 403)                                  # no cookie: nothing
            r, body = self.get("/", cookie + "; spark_admin=geheim; spark_profile=p",
                               {"Authorization": "Basic YWRtaW46eA==", "Origin": f"https://127.0.0.1:{self.door}",
                                "X-Forwarded-For": "1.2.3.4"})
            self.assertEqual(r.status, 200, body)
            got = json.loads(body)
            self.assertNotIn("cookie", got)                                  # none of the panel's cookies, not the door's
            self.assertNotIn("authorization", got)
            self.assertNotIn("x-forwarded-for", got)
            self.assertEqual(got["host"], f"127.0.0.1:{SERVICE_OUT['port']}")
            self.assertEqual(got["origin"], f"http://127.0.0.1:{SERVICE_OUT['port']}")
            self.assertIsNone(r.getheader("X-Frame-Options"))
            self.assertEqual(r.getheader("Content-Security-Policy"), "frame-ancestors https://testserver")
            r, _ = self.get("/cookie", cookie)
            own = r.getheader("Set-Cookie")
            self.assertRegex(own, r"^sw[0-9a-f]{8}_sid=42; Path=/; HttpOnly; Secure$")
            r, body = self.get("/", cookie + "; " + own.split(";")[0])
            self.assertEqual(json.loads(body)["cookie"], "sid=42")             # its own cookie, under its own name
            r, _ = self.get("/weiter", cookie)
            self.assertEqual((r.status, r.getheader("Location")), (302, "/ziel"))
            self.assertEqual(len(fernweb.TUNNEL), 1)
            self.assertEqual(fernzugang.for_live()["web"]["tunnel"], 1)
            self.assertIn("1 Webdienste offen (1 Systeme)", fernzugang.live_sub(fernzugang.for_live()))
        out = j.getvalue()
        self.assertIn(f"fernzugang: web_auf | admin | {SERVICE_OUT['port']}", out)
        self.assertIn("fernzugang: web_ticket | eingeloest | 1", out)
        self.assertNotIn("127.0.0.1", out)
        self.assertNotIn("Dienst", out)

    def test_websocket_passes_through(self):
        import websockets.sync.client as wsc
        _, _, cookie = self.redeem()
        with wsc.connect(f"wss://127.0.0.1:{self.door}/ws", ssl=self.ctx, additional_headers={"Cookie": cookie},
                         open_timeout=helpers.WS_OPEN_S) as c:
            for m in ("hallo", "x" * 300000, b"\x00\x01binary"):
                c.send(m)
                self.assertEqual(c.recv(timeout=20), m)

    def test_notaus_ends_every_tunnel_and_its_channels(self):
        _, _, cookie = self.redeem()
        r, _ = self.get("/", cookie)
        self.assertEqual(r.status, 200)
        a = fernzugang.ANKER[self.gid]
        with journal() as j:
            self.post("/test/notaus")
            self.assertTrue(helpers.until(lambda: not fernweb.TUNNEL and not any(n >= fernweb.ERSTER for n in a.kanaele), 10))
        self.assertIn("fernzugang: web_zu | notaus", j.getvalue())
        r, _ = self.get("/", cookie)
        self.assertEqual(r.status, 403)

    def test_lock_ends_the_tunnel_and_another_ticket_in_the_same_browser_replaces_it(self):
        _, _, cookie = self.redeem()
        fernzugang.ENTSPERRT.clear()
        r, _ = self.get("/", cookie)
        self.assertEqual(r.status, 403)                                       # locked: the tunnel is gone
        self.assertEqual(fernweb.TUNNEL, {})
        self.unlock()
        _, _, first = self.redeem()
        second = ADMIN.post(f"/api/admin/fernzugang/web/{self.gid}/dienste",
                            json={"name": "Zwei", "schema": "http", "port": SERVICE_OUT["port"]}).json()["dienst"]["id"]
        r = ADMIN.post("/api/admin/fernzugang/web/oeffnen", json={"geraet": self.gid, "dienst": second}, headers=CODE).json()
        path = r["url"].split(f":{fernweb.TOR_PORT}", 1)[1]
        r, _ = self.get(path, first)                                          # the same browser: the first one ends
        self.assertEqual(r.status, 303)
        self.assertEqual([t.dienst["id"] for t in fernweb.TUNNEL.values()], [second])

    def test_at_most_max_tunnel_and_connections_wait_for_a_place(self):
        with unittest.mock.patch.object(fernweb, "MAX_TUNNEL", 1):
            self.open()
            other = ADMIN.post(f"/api/admin/fernzugang/web/{self.gid}/dienste",
                               json={"name": "Zwei", "schema": "http", "port": SERVICE_OUT["port"]}).json()["dienst"]["id"]
            r = ADMIN.post("/api/admin/fernzugang/web/oeffnen", json={"geraet": self.gid, "dienst": other}, headers=CODE)
            self.assertEqual(r.status_code, 429)
        reset_web()
        _, _, cookie = self.redeem()
        t = next(iter(fernweb.TUNNEL.values()))
        self.assertEqual(t.plaetze._value, fernweb.MAX_KANAELE)
        t.plaetze = asyncio.Semaphore(0)                                      # every place taken
        with unittest.mock.patch.object(fernweb, "WARTEN_S", 0.5):
            r, body = self.get("/", cookie)
        self.assertEqual(r.status, 502)
        self.assertIn("Zu viele Verbindungen".encode(), body)

    def test_the_switch_off_closes_the_door(self):
        self.redeem()
        self.post("/test/zu")
        self.assertEqual(fernweb.TUNNEL, {})
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.door), timeout=2)


class Rules(unittest.TestCase):
    def test_nothing_of_it_reaches_a_model(self):
        src = pathlib.Path(helpers.APP + "/panel/fernweb.py").read_text()
        for word in ("llm", "chat_turn", "tools", "verbrauch"):
            self.assertNotIn("import " + word, src)

    def test_h11_from_the_lock(self):
        self.assertTrue(h11.__version__)
        self.assertIn("h11==", pathlib.Path(helpers.APP + "/requirements-panel.lock").read_text())


if __name__ == "__main__":
    unittest.main()
