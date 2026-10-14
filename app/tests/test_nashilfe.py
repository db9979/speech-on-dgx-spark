"""Synology-Komfort (nashilfe.py, plan synology-bauplan.md S3). One self-test per rule: finding only listens to mDNS
and keeps only private IPv4 addresses and plain names (outside data), refuses under Notaus and is off without the
admin's switch, never for guests; the rights view only reads, writes a probe only in spark_ablage and deletes it
at once, warns about admin-like accounts without blocking, says what SMB cannot show; logs carry no folder name,
no address and no profile name. No test reads the clock."""
import asyncio
import base64
import contextlib
import io
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import nashilfe  # noqa: E402
import panel  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PORT = helpers._port()
BASE = f"http://127.0.0.1:{PORT}"
DAV = {"dirs": set(), "user": "spark", "pw": "nas-rechte-4711", "calls": [], "write": True, "files": {}}


def fake():
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["PROPFIND", "GET", "PUT", "DELETE", "MKCOL"])
    async def dav(path: str, req: Request):
        path = path.strip("/")
        DAV["calls"].append((req.method, path))
        if req.headers.get("authorization", "") != "Basic " + base64.b64encode(f"{DAV['user']}:{DAV['pw']}".encode()).decode():
            return Response(status_code=401)
        if req.method == "PUT":
            if not DAV["write"]:
                return Response(status_code=403)
            DAV["files"][path] = await req.body()
            return Response(status_code=201)
        if req.method == "DELETE":
            DAV["files"].pop(path, None)
            return Response(status_code=204)
        if req.method != "PROPFIND":
            return Response(status_code=405)
        if path == "dav/geheim":
            return Response(status_code=403)
        pre = path + "/" if path else ""
        kids = sorted({d[len(pre):].split("/")[0] for d in DAV["dirs"] if d.startswith(pre) and d != path})
        rows = [f"<d:response><d:href>/{pre}</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>"]
        rows += [f"<d:response><d:href>/{pre}{k}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>" for k in kids]
        return Response('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(rows) + "</d:multistatus>", status_code=207)
    return app


helpers._serve(fake(), PORT)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


RAW = [{"type": "_webdavs._tcp.local.", "name": "DS920 Keller\x00<script>", "addrs": ["192.168.178.20"], "port": 5006,
        "props": {b"vendor": b"Synology", b"model": b"DS920+"}},
       {"type": "_smb._tcp.local.", "name": "DS920 Keller", "addrs": ["192.168.178.20"], "port": 445, "props": {}},
       {"type": "_smb._tcp.local.", "name": "Fremd", "addrs": ["8.8.8.8"], "port": 445, "props": {}},
       {"type": "_sftp-ssh._tcp.local.", "name": "Raspi", "addrs": ["10.0.0.5", "fe80::1"], "port": 2222, "props": {}},
       {"type": "_printer._tcp.local.", "name": "Drucker", "addrs": ["192.168.178.30"], "port": 631, "props": {}},
       {"type": "_smb._tcp.local.", "name": "Fritz", "addrs": ["127.0.0.1"], "port": 445, "props": {}}]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(nas_on=True, deny={})
        DAV.update(dirs={"dav", "dav/Dokumente", "dav/homes", "dav/spark_ablage", "dav/geheim", "dav/@eaDir"},
                   calls=[], write=True, files={})

    def tearDown(self):
        helpers.set_config(nas_on=False, deny={})

    def place(self, c):
        r = c.post("/api/profile/nas", json={"name": "Keller", "kind": "webdav", "url": BASE, "user": DAV["user"], "password": DAV["pw"]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]


class Finding(Base):
    def test_finds_only_home_network_devices_with_plain_names(self):
        items = nashilfe.merge(RAW)
        self.assertEqual([x["addr"] for x in items], ["192.168.178.20", "10.0.0.5"])   # Synology first; no public, loopback, v6
        ds = items[0]
        self.assertEqual((ds["synology"], ds["model"], ds["name"]), (True, "DS920+", "DS920 Kellerscript"))
        self.assertEqual(ds["suggest"], {"kind": "webdav", "url": "https://192.168.178.20:5006"})
        self.assertEqual(items[1]["suggest"], {"kind": "sftp", "url": "sftp://10.0.0.5:2222"})
        self.assertEqual(nashilfe.suggest({"addr": "192.168.1.2", "synology": False, "offers": {"smb": 445}}),
                         {"kind": "smb", "url": "smb://192.168.1.2"})

    def test_route_switch_guests_notaus_and_logs(self):
        c, uid = profile("NhSuche")
        with mock.patch.object(nashilfe, "_browse", mock.AsyncMock(return_value=RAW)) as b:
            helpers.set_config(nas_on=False)
            self.assertEqual(c.get("/api/profile/nas/find").status_code, 403)
            helpers.set_config(nas_on=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                r = c.get("/api/profile/nas/find")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(len(r.json()["items"]), 2)
            log = out.getvalue()
            self.assertIn("nas: gesucht | 2 gefunden | 1 synology", log)
            for word in ("192.168", "DS920", "NhSuche", uid):
                self.assertNotIn(word, log)
            helpers.set_config(public=True)
            try:
                self.assertIn(TestClient(panel.app).get("/api/profile/nas/find").status_code, (401, 403))
            finally:
                helpers.set_config(public=False)
            calls = b.await_count
            with mock.patch("notaus.level", return_value=1):
                self.assertEqual(c.get("/api/profile/nas/find").status_code, 503)
            self.assertEqual(b.await_count, calls)                 # nothing went out under Notaus

    def test_no_network_means_an_empty_list(self):
        with mock.patch.object(nashilfe, "_browse", mock.AsyncMock(side_effect=OSError("no multicast"))):
            self.assertEqual(asyncio.run(nashilfe.find()), [])


class Rights(Base):
    def test_reads_lists_writes_only_a_probe_in_spark_ablage_and_warns(self):
        c, uid = profile("NhRechte")
        nid = self.place(c)
        # the place's own folder: the connection URL has no path, so the top level is the server root
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = c.post(f"/api/profile/nas/{nid}/rights")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["supported"])
        self.assertEqual([f["name"] for f in d["folders"]], ["dav"])
        writes = [x for x in DAV["calls"] if x[0] in ("PUT", "DELETE", "MKCOL")]
        self.assertEqual(writes, [])                                # no spark_ablage at the root: nothing written
        self.assertEqual(d["drop"], "fehlt")
        log = out.getvalue()
        self.assertIn("nas: rechte | art=webdav | 1 ordner | ablage=fehlt | admin=nein", log)

    def test_inside_a_share_with_homes(self):
        c, uid = profile("NhAdmin")
        nid = self.place(c)
        import nas
        conn = dict(nas.find(uid, nid))
        conn["url"] = conn["url"] + "/dav"
        DAV["calls"] = []
        d = asyncio.run(nashilfe.rights(conn))
        self.assertEqual({f["name"]: f["right"] for f in d["folders"]},
                         {"Dokumente": "lesen", "geheim": "nein", "homes": "lesen", "spark_ablage": "schreiben"})
        self.assertTrue(d["admin_like"])                            # warns, does not block
        self.assertEqual(d["drop"], "schreiben")
        writes = [x for x in DAV["calls"] if x[0] in ("PUT", "DELETE", "MKCOL")]
        self.assertEqual([m for m, _ in writes], ["PUT", "DELETE"])
        self.assertTrue(all(p.startswith("dav/spark_ablage/.spark-probe-") for _, p in writes), writes)
        self.assertEqual(DAV["files"], {})                          # the probe is gone
        DAV["write"] = False
        self.assertEqual(asyncio.run(nashilfe.rights(conn))["drop"], "lesen")

    def test_smb_says_what_it_cannot_show_and_errors_have_reasons(self):
        self.assertFalse(asyncio.run(nashilfe.rights({"kind": "smb", "url": "smb://nas.local"}))["supported"])
        c, uid = profile("NhFalsch")
        nid = self.place(c)
        DAV["pw"] = "anders"
        try:
            self.assertEqual(c.post(f"/api/profile/nas/{nid}/rights").status_code, 502)
        finally:
            DAV["pw"] = "nas-rechte-4711"
        self.assertEqual(c.post("/api/profile/nas/ffffff/rights").status_code, 404)

    def test_page_and_guide_know_it(self):
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")
        with open(os.path.join(here, "index.html")) as f:
            self.assertIn("/static/js/nashilfe.js", f.read())
        with open(os.path.join(here, "js", "guides.js")) as f:
            self.assertIn("{id:'synology',", f.read())
        with open(os.path.join(here, "js", "nashilfe.js")) as f:
            js = f.read()
        self.assertNotRegex(js, r"\bon(click|change)=\"")
        self.assertNotRegex(js, r"\$\{(x|f)\.(name|model|addr)\}")      # outside text always through esc()


class McpTemplate(unittest.TestCase):
    """S7: the guide "MCP-Server auf der NAS" and its hardened template (docs/vorlagen/nas-mcp) stay hardened."""
    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

    def read(self, name):
        path = os.path.join(self.ROOT, "docs", "vorlagen", "nas-mcp", name)
        if not os.path.exists(path):
            raise unittest.SkipTest("docs/ is not in this copy (the Spark tests only app/)")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_guide_is_honest_and_keeps_writing_off(self):
        with open(os.path.join(self.ROOT, "app", "panel", "static", "js", "guides.js"), encoding="utf-8") as f:
            js = f.read()
        g = js[js.index("{id:'nasmcp',"):]
        g = g[:g.index("\n{id:")]
        self.assertNotIn("sw:", g[:g.index("t:[")])                 # only a guide, no switch of its own
        for word in ("Wissensordner", "Software von Dritten", "docs/vorlagen/nas-mcp", "bleibt „Aus“", ":ro"):
            self.assertIn(word, g)

    def test_template_is_hardened(self):
        compose, docker, nginx = self.read("compose.yaml"), self.read("Dockerfile"), self.read("nginx.conf")
        self.assertRegex(docker, r"(?m)^FROM [^\s]+@sha256:")
        self.assertIn("npm ci", docker)
        self.assertIn("--ignore-scripts", docker)
        self.assertNotIn("npm install", docker)
        self.assertRegex(compose, r"image: [^\s]+@sha256:")
        self.assertIn(":/data:ro", compose)
        self.assertEqual(compose.count("read_only: true"), 2)
        self.assertEqual(compose.count("cap_drop: [ALL]"), 2)
        self.assertEqual(compose.count("no-new-privileges:true"), 2)
        self.assertIn('user: "1000:1000"', compose)
        self.assertIn("internal: true", compose)
        ports = [line for line in compose.splitlines() if "ports:" in line]
        self.assertEqual(ports, ['    ports: ["127.0.0.1:8765:8080"]         # nur für den Reverse-Proxy der NAS selbst'])
        self.assertIn('$http_authorization != "Bearer SCHLUESSEL"', nginx)
        self.assertIn("location / { return 404; }", nginx)
        pkg = self.read("package.json")
        self.assertNotRegex(pkg, r'"[\^~]|latest')                  # exact versions only


if __name__ == "__main__":
    unittest.main()
