"""Fernzugang, große Dateien (ferngross.py, stage 3b): in pieces with a SHA-256 each, „Weiter“ after „Trennen“, the
server's own checksum at the end, a fetch by link (the address as one quoted word, never in the journal), a file of
an NAS place streamed piece by piece; the switch, the limits and the free space checked before anything is written.

The way is the real one: the anchor program, the panel's SSH client with SFTP and exec channels, a small SSH server on
a folder; the server's commands (df, sha256sum, curl) are played by the test from the words it gets, so a command
that is not one of the fixed ones with its values as single words fails."""
import asyncio
import hashlib
import os
import shlex
import sys
import threading
import time
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tests import helpers  # noqa: E402
from tests import test_fernzugang as tz  # noqa: E402 (the module, so its tests do not run twice)

import features  # noqa: E402
import ferngross  # noqa: E402
import fernzugang  # noqa: E402
import nasquelle  # noqa: E402


class Rules(unittest.TestCase):
    def test_only_a_plain_https_address(self):
        good = ("https://example.org/datei.iso", "https://dl.example.org:8443/a/b-c_d.tar.gz?x=1&y=%20",
                "https://10.0.0.5/x", "https://example.org/a;b$(c)")
        for u in good:
            self.assertEqual(ferngross.url_ok(u), u, u)
        bad = ("http://example.org/x", "ftp://example.org/x", "https://user:pw@example.org/x", "https://user@example.org/x",
               "https://example.org/a b", "https://example.org/a'b", 'https://example.org/a"b', "https://example.org/a\\b",
               "https://example.org/a`b", "https://example.org/\nx", "https://-bad.org/", "https://example.org:0/",
               "https://example.org:99999/", "https:///x", "https://example.org/" + "a" * 2048, "", None, "file:///etc/passwd",
               "https://example.org/a#frag", "https://example.org/a<b>")
        for u in bad:
            self.assertIsNone(ferngross.url_ok(u), u)

    def test_a_checksum_is_64_hex_or_nothing(self):
        self.assertEqual(ferngross.sha_ok(""), "")
        self.assertEqual(ferngross.sha_ok(None), "")
        self.assertEqual(ferngross.sha_ok("A" * 64), "a" * 64)
        for v in ("a" * 63, "a" * 65, "g" * 64, "a" * 32 + " " + "a" * 31):
            self.assertIsNone(ferngross.sha_ok(v), v)

    def test_every_value_is_one_word_of_a_fixed_command(self):
        evil = "https://example.org/x;rm -rf ~/$(id)`id`&&reboot"
        for kind in ("linux", "macos"):
            cmd = ferngross._befehl(kind, "holen", most=5, datei="/home/spark/.a b.spark-teil-1", url=evil)
            words = shlex.split(cmd)
            self.assertEqual(words[0], "curl")
            self.assertEqual(words[-2:], ["--", evil])
            self.assertIn("/home/spark/.a b.spark-teil-1", words)
            self.assertEqual(words[words.index("--proto") + 1], "=https")
            self.assertEqual(words[words.index("--proto-redir") + 1], "=https")
            self.assertEqual(shlex.split(ferngross._befehl(kind, "frei", ordner="/x y"))[-2:], ["--", "/x y"])
            self.assertEqual(shlex.split(ferngross._befehl(kind, "summe", datei="-a"))[-2:], ["--", "-a"])
        self.assertEqual(shlex.split(ferngross._befehl("macos", "summe", datei="/f"))[:3], ["shasum", "-a", "256"])
        self.assertNotIn("windows", ferngross.BEFEHL)      # stage 5

    def test_what_the_server_says_is_read_as_numbers_only(self):
        df = b"Filesystem 1024-blocks Used Available Capacity Mounted on\r\n/dev/sda1 1000 10 990 2% /\r\n"
        self.assertEqual(ferngross._frei_kb(df), 990)
        self.assertIsNone(ferngross._frei_kb(b"df: kaputt\r\n"))
        self.assertIsNone(ferngross._frei_kb(b"x\n/dev/a 1 2 viel 4% /\n"))
        head = (b"HTTP/1.1 302 Found\r\nContent-Length: 0\r\nLocation: https://cdn/x\r\n\r\n"
                b"HTTP/2 200\r\ncontent-length: 12345\r\n\r\n")
        self.assertEqual(ferngross._laenge(head), 12345)
        self.assertIsNone(ferngross._laenge(b"HTTP/2 200\r\n\r\n"))
        self.assertIsNone(ferngross._laenge(b"x-content-length: 5\r\n"))
        h = hashlib.sha256(b"x").hexdigest()
        self.assertEqual(ferngross._summe(f"\\{h}  /a\\nb\r\n".encode()), h)
        self.assertIsNone(ferngross._summe(b"sha256sum: /a: No such file\r\n"))

    def test_the_setting_and_the_switch(self):
        self.assertEqual(fernzugang.gross_mb({}), 20480)
        self.assertEqual(fernzugang.gross_mb({"fernzugang_gross_mb": 5}), 5)
        self.assertIsNone(fernzugang.check({"fernzugang_gross_mb": 1048576}))
        for v in (0, 1048577, True, "5"):
            self.assertIsNotNone(fernzugang.check({"fernzugang_gross_mb": v}), v)
        c = fernzugang.load_config()["chat"]
        self.assertIs(c["fernzugang_gross"], False)
        self.assertEqual(c["fernzugang_gross_mb"], 20480)
        self.assertNotIn("chat.fernzugang_gross", features.DEFAULT_ON)
        self.assertIn("ferngross", features.SPARK_ONLY)
        self.assertEqual(next(f for f in features.FEATURES if f.key == "ferngross").parent, "fernzugang")
        self.assertFalse(ferngross.admin_on({"fernzugang": True}))
        self.assertLessEqual(ferngross.TEIL, 8 * 1024 * 1024)


class Intern(unittest.TestCase):
    """Paired at home, the anchor goes to the panel's own address first (its certificate pinned), so a big file does
    not go through the proxy in front of the panel; from the internet it gets none."""

    class Sock:
        def __init__(self, *a):
            self.to = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def connect(self, addr):
            self.to = addr

        def getsockname(self):
            return ("192.168.1.2", 40000)

    def intern(self, ip, wo="zuhause"):
        with unittest.mock.patch.object(fernzugang, "_herkunft", lambda c: wo), \
                unittest.mock.patch.object(fernzugang.guard, "client_ip", lambda c: ip), \
                unittest.mock.patch.object(fernzugang, "_cert_sha", lambda: "c" * 64), \
                unittest.mock.patch.object(fernzugang.socket, "socket", self.Sock):
            return fernzugang._intern(object())

    def test_the_panel_names_its_own_address_only_at_home(self):
        port = fernzugang.load_config("panel")["https_port"]
        self.assertEqual(self.intern("192.168.1.50"), {"url": f"https://192.168.1.2:{port}", "fp": "c" * 64})
        for ip, wo in (("192.168.1.50", "internet"), ("8.8.8.8", "zuhause"), ("127.0.0.1", "zuhause"),
                       ("fd00::5", "zuhause"), ("169.254.1.1", "zuhause"), ("kaputt", "zuhause")):
            self.assertIsNone(self.intern(ip, wo), ip)

    def test_the_anchor_tries_it_first_and_falls_back(self):
        p = tz.program()
        ok = {"url": "https://192.168.1.2:31443", "fp": "d" * 64}
        self.assertEqual(p.intern_ok(ok), ok)
        for bad in ({"url": "https://8.8.8.8:31443", "fp": "d" * 64}, {"url": "https://192.168.1.2:31443", "fp": "x"},
                    {"url": "http://192.168.1.2:31443", "fp": "d" * 64}, {"url": "https://192.168.1.300:31443", "fp": "d" * 64},
                    {"url": "https://192.168.1.2:31443/x", "fp": "d" * 64}, {"url": "https://192.168.1.2", "fp": "d" * 64}, "x", None):
            self.assertIsNone(p.intern_ok(bad), bad)
        calls = []

        def opened(base, fp, path, key, timeout=20):
            calls.append((base, fp, timeout))
            if base.startswith("https://192.168."):
                raise OSError("no route")
            return "ws"
        conf = {"url": "https://spark.example.org", "fp": "", "key": "k", "intern": ok}
        with unittest.mock.patch.object(p.WS, "open", opened):
            self.assertEqual(p.verbinden(conf), ("ws", "extern"))
            self.assertEqual(calls, [(ok["url"], ok["fp"], p.INTERN_S), ("https://spark.example.org", "", 20)])
            calls.clear()
            self.assertEqual(p.verbinden({**conf, "intern": {"url": "https://8.8.8.8:1", "fp": "d" * 64}}), ("ws", "extern"))
            self.assertEqual(len(calls), 1)
        with unittest.mock.patch.object(p.WS, "open", lambda *a, **k: "ws"):
            self.assertEqual(p.verbinden(conf), ("ws", "intern"))


class _Reader:
    """An NAS place for the test: one folder, files from a dict; pieces() notes when it hands out a piece."""

    def __init__(self, files, events):
        self.files, self.events, self.sizes = files, events, []

    async def list(self, rel):
        return [(n, False, len(b), 0) for n, b in self.files.items()] + [("unter", True, 0, 0)]

    async def pieces(self, rel, most, size=1 << 20):
        self.sizes.append(size)
        data = self.files[rel]
        for i in range(0, len(data), size):
            self.events.append(("lesen", i // size))
            yield data[i:i + size]

    async def close(self):
        pass


class Readers(unittest.TestCase):
    """nasquelle's readers hand a file out piece by piece, never more than asked, never more than the limit."""

    def test_webdav_pieces(self):
        import httpx
        body = os.urandom(5000)
        rd = nasquelle._Dav({"url": "https://nas.local/dav", "user": "", "password": ""}, "/ordner")
        seen = []

        def handler(req):
            seen.append(str(req.url))
            return httpx.Response(200, content=body)
        rd._client = lambda t, m: httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def take(most):
            return [p async for p in rd.pieces("a b.bin", most, 1024)]
        got = asyncio.run(take(10000))
        self.assertEqual(b"".join(got), body)
        self.assertTrue(all(len(p) <= 1024 for p in got))
        self.assertEqual(seen, ["https://nas.local/dav/ordner/a%20b.bin"])
        with self.assertRaises(nasquelle.SourceError):
            asyncio.run(take(4000))

    def test_sftp_pieces(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="nasq-")
        with open(os.path.join(d, "f.bin"), "wb") as f:
            f.write(b"x" * 3000)
        rd = nasquelle._remote({"kind": "sftp", "url": "sftp://nas.local", "user": "u", "password": "", "hostkey": ""}, "/top")
        rd.base = d
        rd._join = os.path.join

        async def run(fn, *a, timeout=0):
            return fn(*a)
        rd._run = run
        rd._size = os.path.getsize
        rd._open = open

        async def take(most):
            return [p async for p in rd.pieces("f.bin", most, 1000)]
        self.assertEqual([len(p) for p in asyncio.run(take(3000))], [1000, 1000, 1000])
        with self.assertRaises(nasquelle.SourceError):
            asyncio.run(take(2999))


class BigFiles(tz._FilesBase):
    def setUp(self):
        super().setUp()
        self.server.config.app.include_router(ferngross.router)
        helpers.set_config(fernzugang_gross=True, fernzugang_gross_mb=1)
        self.free_kb, self.urls, self.cmds, self.slow = 10 ** 9, {}, [], threading.Event()
        self.p = [unittest.mock.patch.object(ferngross, "TEIL", 1024), unittest.mock.patch.object(ferngross, "RESERVE", 0),
                  unittest.mock.patch.object(ferngross, "SCHREIB", 300), unittest.mock.patch.object(ferngross, "NAS_STUECK", 1000)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        ferngross.UPLOADS.clear()
        ferngross.JOBS.clear()
        ferngross.REST.clear()
        helpers.set_config(fernzugang_gross=False, fernzugang_gross_mb=20480)
        self.slow.set()
        super().tearDown()

    def on_disk(self, p):
        return os.path.join(self.root, os.path.normpath("/" + p).lstrip("/"))

    def run_cmd(self, command, ch):
        """The server's side of the fixed commands, from the words alone (never a shell)."""
        w = shlex.split(command)
        self.cmds.append(w)
        out, st = b"", 0
        if w[:2] == ["df", "-Pk"]:
            out = f"Filesystem 1024-blocks Used Available Capacity Mounted on\r\n/dev/x 100 1 {self.free_kb} 1% /\r\n".encode()
        elif w[0] in ("sha256sum", "shasum"):
            try:
                with open(self.on_disk(w[-1]), "rb") as f:
                    out = f"{hashlib.sha256(f.read()).hexdigest()}  {w[-1]}\r\n".encode()
            except OSError:
                out, st = b"no such file\r\n", 1
        elif w[0] == "curl" and "-I" in w:
            body = self.urls.get(w[-1])
            out = (b"HTTP/2 200\r\ncontent-length: %d\r\n\r\n" % len(body)) if isinstance(body, bytes) else b""
            st = 0 if isinstance(body, bytes) else 22
        elif w[0] == "curl":
            body, part = self.urls.get(w[-1]), self.on_disk(w[w.index("-o") + 1])
            if body == "langsam":
                with open(part, "wb") as f:
                    f.write(b"y" * 500)
                while not ch.closed and not self.slow.is_set():
                    time.sleep(0.05)
                return ch.close()
            if not isinstance(body, bytes):
                st = 22
            else:
                with open(part, "wb") as f:
                    f.write(body)
        ch.sendall(out)
        ch.send_exit_status(st)
        ch.close()

    def files(self, d):
        sshd = self.sftp_server(d["pi_key"].split()[1], run=self.run_cmd)
        ws, _ = self.anchor(d["key"], sshd.port)
        r = self.http.post("/api/admin/fernzugang/dateien", json={"geraet": d["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        return ws, r.json()["id"]

    def put(self, sid, uid, off, data, sha=None):
        return self.http.put(f"/api/admin/fernzugang/gross/{sid}/hoch/{uid}?offset={off}", content=data,
                             headers={"content-type": "application/octet-stream",
                                      "x-fz-sha256": sha or hashlib.sha256(data).hexdigest()})

    def wait(self, sid, jid, want=("fertig", "fehler")):
        end = time.monotonic() + 60
        while time.monotonic() < end:
            r = self.http.get(f"/api/admin/fernzugang/gross/{sid}/stand")
            self.assertEqual(r.status_code, 200, r.text)
            j = next(x for x in r.json()["jobs"] if x["id"] == jid)
            if j["stand"] in want:
                return j
            time.sleep(0.05)
        self.fail("the job did not end")

    def leftovers(self, folder):
        return [n for n in os.listdir(self.on_disk(folder)) if ".spark-teil-" in n]

    def test_in_pieces_with_resume_and_the_check_at_the_end(self):
        d = self.pair(hostkey=tz.HOST_PUB)
        data = os.urandom(2500)
        with tz.journal() as j:
            ws, sid = self.files(d)
            g = f"/api/admin/fernzugang/gross/{sid}"
            start = {"pfad": "/home/spark/unter", "name": "gross bild.iso", "groesse": len(data), "ersetzen": False}
            # too big, no room, a bad name: refused before anything is written
            self.assertEqual(self.http.post(g + "/hoch", json={**start, "groesse": 1024 * 1024 + 1}).status_code, 413)
            self.free_kb = 1
            self.assertEqual(self.http.post(g + "/hoch", json=start).status_code, 507)
            self.free_kb = 10 ** 9
            self.assertEqual(self.http.post(g + "/hoch", json={**start, "name": "../x"}).status_code, 400)
            self.assertEqual(self.http.post(g + "/hoch", json={**start, "sha256": "zz"}).status_code, 400)
            self.assertEqual(self.leftovers("/home/spark/unter"), [])
            r = self.http.post(g + "/hoch", json=start)
            self.assertEqual(r.status_code, 200, r.text)
            uid = r.json()["id"]
            self.assertEqual(r.json()["teil"], 1024)
            self.assertEqual(self.put(sid, uid, 0, data[:1024]).status_code, 200)
            # a piece that did not arrive whole is not written; one at the wrong place neither; none above a piece
            self.assertEqual(self.put(sid, uid, 1024, data[1024:2048], sha="0" * 64).status_code, 422)
            self.assertEqual(self.put(sid, uid, 0, data[:1024]).status_code, 409)
            self.assertEqual(self.put(sid, uid, 1024, data[1024:2049]).status_code, 413)
            part = self.on_disk("/home/spark/unter/" + self.leftovers("/home/spark/unter")[0])
            self.assertEqual(os.path.getsize(part), 1024)
            self.assertEqual(fernzugang.counts()["uebertragungen"], 1)
            # „Trennen“, a new files session of the same login: „Weiter“ at the last whole piece
            self.assertEqual(self.http.delete(f"/api/admin/fernzugang/dateien/{sid}").status_code, 200)
            with open(part, "ab") as f:
                f.write(b"halb")                         # half a piece that broke off: cut back
            r = self.http.post("/api/admin/fernzugang/dateien", json={"geraet": d["id"]})
            sid2 = r.json()["id"]
            g2 = f"/api/admin/fernzugang/gross/{sid2}"
            self.assertEqual(self.put(sid2, uid, 1024, data[1024:2048]).status_code, 404)   # not bound to it yet
            ups = self.http.get(g2 + "/stand").json()["uploads"]
            self.assertEqual([(u["id"], u["offset"], u["groesse"]) for u in ups], [(uid, 1024, 2500)])
            r = self.http.post(f"{g2}/hoch/{uid}/weiter")
            self.assertEqual(r.json(), {"offset": 1024, "groesse": 2500})
            self.assertEqual(os.path.getsize(part), 1024)
            self.assertEqual(self.http.post(f"{g2}/hoch/{uid}/fertig").status_code, 409)     # pieces missing
            self.assertEqual(self.put(sid2, uid, 1024, data[1024:2048]).status_code, 200)
            self.assertEqual(self.put(sid2, uid, 2048, data[2048:]).json(), {"offset": 2500})
            r = self.http.post(f"{g2}/hoch/{uid}/fertig")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["sha256"], hashlib.sha256(data).hexdigest())
            job = self.wait(sid2, r.json()["id"])
            self.assertEqual((job["stand"], job["sha256"]), ("fertig", hashlib.sha256(data).hexdigest()))
            with open(self.on_disk("/home/spark/unter/gross bild.iso"), "rb") as f:
                self.assertEqual(f.read(), data)
            self.assertEqual(self.leftovers("/home/spark/unter"), [])
            self.assertIn(["sha256sum", "--", part[len(self.root):]], self.cmds)
            # the same name again without „Ersetzen“: refused before a byte
            self.assertEqual(self.http.post(g2 + "/hoch", json=start).status_code, 409)
            # the server's file differs from what went in: deleted, an error, no target
            r = self.http.post(g2 + "/hoch", json={**start, "name": "kaputt.bin"})
            uid = r.json()["id"]
            for off in range(0, 2500, 1024):
                self.assertEqual(self.put(sid2, uid, off, data[off:off + 1024]).status_code, 200)
            part = self.on_disk("/home/spark/unter/" + self.leftovers("/home/spark/unter")[0])
            with open(part, "r+b") as f:
                f.write(b"X")
            job = self.wait(sid2, self.http.post(f"{g2}/hoch/{uid}/fertig").json()["id"])
            self.assertEqual((job["stand"], job["grund"]), ("fehler", "pruefsumme"))
            self.assertFalse(os.path.exists(self.on_disk("/home/spark/unter/kaputt.bin")))
            self.assertEqual(self.leftovers("/home/spark/unter"), [])
            # a given checksum that does not match: refused at the end, the part file goes
            r = self.http.post(g2 + "/hoch", json={**start, "name": "falsch.bin", "sha256": "a" * 64})
            uid = r.json()["id"]
            for off in range(0, 2500, 1024):
                self.put(sid2, uid, off, data[off:off + 1024])
            self.assertEqual(self.http.post(f"{g2}/hoch/{uid}/fertig").status_code, 422)
            self.assertEqual(self.leftovers("/home/spark/unter"), [])
            # „Abbrechen“ deletes what is there
            uid = self.http.post(g2 + "/hoch", json={**start, "name": "weg.bin"}).json()["id"]
            self.put(sid2, uid, 0, data[:1024])
            self.assertEqual(self.http.delete(f"{g2}/hoch/{uid}").status_code, 200)
            self.assertEqual(self.leftovers("/home/spark/unter"), [])
            self.assertEqual(ferngross.UPLOADS, {})
        out = j.getvalue()
        for line in ("fernzugang: gross_auf | zu gross | 1024", "fernzugang: gross_auf | voll | 2", "fernzugang: gross_auf | name ungueltig | 0",
                     "fernzugang: gross_auf | ok | 2", "fernzugang: gross_teil | ok | 1", "fernzugang: gross_teil | pruefsumme | 1",
                     "fernzugang: gross_teil | stelle | 0", "fernzugang: gross_teil | zu gross | 0", "fernzugang: gross_teil | kein upload | 0",
                     "fernzugang: gross_weiter | ok | 1", "fernzugang: gross_fertig | unvollstaendig | 1", "fernzugang: gross_fertig | ok | 2",
                     "fernzugang: gross_rate | kb_s |", "fernzugang: gross_auf | gibt es schon | 0", "fernzugang: gross_fertig | pruefsumme | 2",
                     "fernzugang: gross_ab | ok | 1"):
            self.assertIn(line, out)
        for secret in ("gross bild", "kaputt", "falsch.bin", "/home/spark", "spark-teil"):
            self.assertNotIn(secret, out)
        ws.sock.shutdown(tz.socket.SHUT_RDWR)

    def test_by_link_the_server_fetches_it_itself(self):
        d = self.pair(hostkey=tz.HOST_PUB)
        body = os.urandom(3000)
        url = "https://downloads.example.org/iso/debian.iso?sig=a;b$(id)&x=1"
        self.urls = {url: body, "https://downloads.example.org/fehlt": None, "https://downloads.example.org/langsam": "langsam"}
        with tz.journal() as j:
            ws, sid = self.files(d)
            g = f"/api/admin/fernzugang/gross/{sid}"
            base = {"pfad": "/home/spark", "name": "debian.iso", "ersetzen": False}
            for bad in ("http://downloads.example.org/x", "https://u:p@downloads.example.org/x", "https://a b/x", "https://x/'y"):
                self.assertEqual(self.http.post(g + "/holen", json={**base, "url": bad}).status_code, 400, bad)
            self.assertEqual(self.http.post(g + "/holen", json={**base, "url": url, "sha256": "xyz"}).status_code, 400)
            self.assertEqual(self.cmds, [])                       # nothing ran on the server
            r = self.http.post(g + "/holen", json={**base, "url": url, "sha256": hashlib.sha256(body).hexdigest()})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["groesse"], 3000)
            job = self.wait(sid, r.json()["id"])
            self.assertEqual((job["stand"], job["bytes"]), ("fertig", 3000), job)
            with open(self.on_disk("/home/spark/debian.iso"), "rb") as f:
                self.assertEqual(f.read(), body)
            fetch = next(w for w in self.cmds if w[0] == "curl" and "-o" in w)
            self.assertEqual(fetch[-2:], ["--", url])             # the address one word, after „--“
            self.assertEqual(fetch[fetch.index("--max-filesize") + 1], str(1024 * 1024))
            # a wrong checksum: the file goes; an address with an error: nothing stays; too big: refused before
            r = self.http.post(g + "/holen", json={**base, "url": url, "name": "b.iso", "sha256": "b" * 64})
            self.assertEqual(self.wait(sid, r.json()["id"])["grund"], "pruefsumme")
            self.assertFalse(os.path.exists(self.on_disk("/home/spark/b.iso")))
            r = self.http.post(g + "/holen", json={**base, "url": "https://downloads.example.org/fehlt", "name": "c.iso"})
            self.assertEqual(self.wait(sid, r.json()["id"])["grund"], "http")
            self.urls[url] = os.urandom(1024 * 1024 + 1)
            self.assertEqual(self.http.post(g + "/holen", json={**base, "url": url, "name": "d.iso"}).status_code, 413)
            # „Abbrechen“ hangs up the command there; the part file goes
            r = self.http.post(g + "/holen", json={**base, "url": "https://downloads.example.org/langsam", "name": "e.iso"})
            jid = r.json()["id"]
            helpers.until(lambda: self.leftovers("/home/spark"))
            self.assertEqual(self.http.delete(f"{g}/job/{jid}").status_code, 200)
            self.assertEqual(self.wait(sid, jid)["grund"], "abgebrochen")
            self.assertEqual(self.leftovers("/home/spark"), [])
            self.assertEqual(sorted(n for n in os.listdir(self.on_disk("/home/spark")) if n.endswith(".iso")), ["debian.iso"])
            # Windows comes with stage 5
            with unittest.mock.patch.object(ferngross, "_kind", lambda s: "windows"):
                self.assertEqual(self.http.post(g + "/holen", json={**base, "url": url}).status_code, 501)
        out = j.getvalue()
        for line in ("fernzugang: holen | ungueltig | 0", "fernzugang: holen | ok | 2", "fernzugang: holen_fertig | ok | 2",
                     "fernzugang: holen_fertig | pruefsumme | 2", "fernzugang: holen_fertig | http | 0",
                     "fernzugang: holen | zu gross | 1024", "fernzugang: holen_fertig | abgebrochen | 0",
                     "fernzugang: job_ab | ok | 1", "fernzugang: holen | windows | 0"):
            self.assertIn(line, out)
        for secret in ("downloads.example.org", "debian", "sig=", "https://", "/home/spark"):
            self.assertNotIn(secret, out)
        ws.sock.shutdown(tz.socket.SHUT_RDWR)

    def test_from_the_nas_piece_by_piece(self):
        d = self.pair(hostkey=tz.HOST_PUB)
        data, events = os.urandom(4500), []
        rd = _Reader({"film.mkv": data}, events)
        real_sftp = ferngross.ferndateien._sftp

        async def spy(s, fn):
            events.append(("schreiben",))
            return await real_sftp(s, fn)
        place = {"id": "n1", "name": "NAS", "kind": "sftp"}
        with tz.journal() as j, \
                unittest.mock.patch.object(ferngross, "_nas_ort", lambda req, nid, word: place), \
                unittest.mock.patch.object(nasquelle, "reader", lambda c, path: rd), \
                unittest.mock.patch.object(ferngross.ferndateien, "_sftp", spy):
            ws, sid = self.files(d)
            g = f"/api/admin/fernzugang/gross/{sid}"
            r = self.http.post(g + "/nas/liste", json={"nas": "n1", "pfad": "/video"})
            self.assertEqual(r.json()["dateien"], [{"name": "film.mkv", "groesse": 4500}])
            self.assertEqual(r.json()["ordner"], ["unter"])
            self.assertEqual(self.http.post(g + "/nas", json={"nas": "n1", "datei": "/video/../x", "pfad": "/home/spark",
                                                              "name": "x"}).status_code, 400)
            self.assertEqual(self.http.post(g + "/nas", json={"nas": "n1", "datei": "/video/gibtsnicht", "pfad": "/home/spark",
                                                              "name": "x"}).status_code, 404)
            r = self.http.post(g + "/nas", json={"nas": "n1", "datei": "/video/film.mkv", "pfad": "/home/spark", "name": "film.mkv"})
            self.assertEqual(r.status_code, 200, r.text)
            job = self.wait(sid, r.json()["id"])
            self.assertEqual((job["stand"], job["sha256"]), ("fertig", hashlib.sha256(data).hexdigest()))
            with open(self.on_disk("/home/spark/film.mkv"), "rb") as f:
                self.assertEqual(f.read(), data)
            # streamed: never more than one piece of the NAS at a time, the next read only after the last was written
            self.assertEqual(rd.sizes, [1000])
            order = [e for e in events if e[0] == "lesen" or e == ("schreiben",)]
            reads = [i for i, e in enumerate(order) if e[0] == "lesen"]
            self.assertEqual(len(reads), 5)
            for a, b in zip(reads, reads[1:]):
                self.assertIn(("schreiben",), order[a + 1:b])
        out = j.getvalue()
        for line in ("fernzugang: nas_liste | ok | 2", "fernzugang: nas_holen | pfad ungueltig | 0", "fernzugang: nas_holen | fehlt | 0",
                     "fernzugang: nas_holen | ok | 4", "fernzugang: nas_fertig | ok | 4"):
            self.assertIn(line, out)
        self.assertNotIn("film", out)
        ws.sock.shutdown(tz.socket.SHUT_RDWR)

    def test_off_and_not_for_others(self):
        d = self.pair(hostkey=tz.HOST_PUB)
        ws, sid = self.files(d)
        g = f"/api/admin/fernzugang/gross/{sid}"
        helpers.set_config(fernzugang_gross=False)
        self.assertEqual(self.http.get(g + "/stand").status_code, 404)
        helpers.set_config(fernzugang_gross=True)
        self.assertEqual(self.http.get(g + "/stand").status_code, 200)
        with unittest.mock.patch.object(fernzugang, "_login", lambda c: "M"):
            self.unlock()
            self.assertEqual(self.http.get(g + "/stand").status_code, 404)
        self.assertEqual(self.http.get("/api/admin/fernzugang/gross/ffff/stand").status_code, 404)
        ws.sock.shutdown(tz.socket.SHUT_RDWR)


if __name__ == "__main__":
    unittest.main()
