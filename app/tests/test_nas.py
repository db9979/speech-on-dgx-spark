"""NAS-Verbindung (nas.py, plan synology-bauplan.md S1) against a fake NAS with a self-made certificate. One
self-test per rule: off without the admin's switch, never for guests; a certificate that does not fit is accepted
only by exactly its fingerprint and a new one stops the connection; the password never comes back and is sealed;
Eigener Speicher on a connection takes its login and certificate from there; a connection in use is not removed;
old speicher.json and offsite.json move over and keep working; logs carry no address and no user; Live, Logs,
backup, code levels and features know it. No test reads the clock."""
import asyncio
import base64
import contextlib
import http.server
import io
import json
import os
import ssl
import threading
import unittest

from tests import helpers
from tests.test_offsite import _cert

helpers.start()
import backup  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import logfilter  # noqa: E402
import nas  # noqa: E402
import offsite  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import speicher  # noqa: E402
import stufen  # noqa: E402
import zertpin  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
USER, PW = "spark-nas", "nas-geheim-4711"
CERT1, CERT2 = _cert("ds-keller.local"), _cert("jemand-anders.local")
NAS = {"files": {}, "dirs": set(), "auth": [], "pw": PW}


class H(http.server.BaseHTTPRequestHandler):
    def _ok(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0)) if self.command != "PUT" else None
        NAS["auth"].append(self.headers.get("Authorization", ""))
        return self.headers.get("Authorization", "") == "Basic " + base64.b64encode(f"{USER}:{NAS['pw']}".encode()).decode()

    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PROPFIND(self):
        if not self._ok():
            return self._send(401)
        self._send(207, b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop>'
                        b'<d:quota-available-bytes>1000000000</d:quota-available-bytes></d:prop></d:propstat>'
                        b'</d:response></d:multistatus>')

    def do_MKCOL(self):
        if not self._ok():
            return self._send(401)
        if self.path in NAS["dirs"]:
            return self._send(405)
        NAS["dirs"].add(self.path)
        self._send(201)

    def do_PUT(self):
        data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not self._ok():
            return self._send(401)
        NAS["files"][self.path] = data
        self._send(201)

    def do_GET(self):
        if not self._ok():
            return self._send(401)
        if self.path not in NAS["files"]:
            return self._send(404)
        self._send(200, NAS["files"][self.path])

    def do_DELETE(self):
        if not self._ok():
            return self._send(401)
        NAS["files"].pop(self.path, None)
        self._send(204)

    def log_message(self, *a):
        pass


def _serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT1[0], CERT1[1])
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, ctx


SRV, CTX = _serve()
URL = f"https://127.0.0.1:{SRV.server_address[1]}"
SHA1, SHA2 = zertpin.fingerprint(CERT1[2]), zertpin.fingerprint(CERT2[2])


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


class Base(unittest.TestCase):
    def setUp(self):
        guard._rate.clear()
        CTX.load_cert_chain(CERT1[0], CERT1[1])
        NAS.update(files={}, dirs=set(), auth=[], pw=PW)
        helpers.set_config(nas_on=True)

    def tearDown(self):
        CTX.load_cert_chain(CERT1[0], CERT1[1])
        helpers.set_config(nas_on=False, storage_own=False, storage_lan=False)

    def connect(self, c, **kw):
        body = dict(dict(name="Synology Keller", kind="webdav", url=URL, user=USER, password=PW, cert=SHA1), **kw)
        r = c.post("/api/profile/nas", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]


class Connection(Base):
    def test_off_without_the_admin_switch_and_never_for_guests(self):
        c, uid = profile("NasAus")
        helpers.set_config(nas_on=False)
        self.assertFalse(c.get("/api/whoami").json().get("nas"))
        self.assertEqual(c.get("/api/profile/nas").status_code, 403)
        r = c.post("/api/profile/nas", json={"name": "N", "kind": "webdav", "url": URL, "user": USER, "password": PW})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(NAS["auth"], [])                       # nothing went to the NAS
        helpers.set_config(nas_on=True)
        self.assertTrue(c.get("/api/whoami").json().get("nas"))
        self.assertTrue(c.get("/api/profile/nas").json()["on"])     # no profile switch: the admin's is enough
        self.assertEqual(features.BY_KEY["nas"].pref, "")
        self.assertFalse(features.allowed("nas", None))
        helpers.set_config(public=True)
        try:
            self.assertIn(TestClient(panel.app).get("/api/profile/nas").status_code, (401, 403))
            self.assertIn(TestClient(panel.app).post("/api/profile/nas", json={}).status_code, (401, 403))
        finally:
            helpers.set_config(public=False)
        self.assertEqual(TestClient(panel.app).get("/api/admin/nas").status_code, 401)

    def test_certificate_only_by_its_fingerprint_and_the_password_never_comes_back(self):
        c, uid = profile("NasZert")
        body = dict(name="Synology Keller", kind="webdav", url=URL, user=USER, password=PW)
        r = c.post("/api/profile/nas", json=body)               # self-made, not for 127.0.0.1: asked, not stored
        self.assertEqual(r.status_code, 409, r.text)
        shown = r.json()["detail"]["cert"]
        self.assertEqual((shown["sha256"], shown["fits"], shown["self_signed"]), (SHA1, False, True))
        self.assertNotIn("pem", shown)
        self.assertEqual(nas.load(uid), [])
        self.assertTrue(all(a == "" for a in NAS["auth"]))      # the password never went to the unchecked NAS
        self.assertEqual(c.post("/api/profile/nas", json=dict(body, cert=SHA2)).status_code, 409)
        self.assertEqual(nas.load(uid), [])
        nid = self.connect(c)
        got = c.get("/api/profile/nas")
        self.assertNotIn(PW, got.text)
        item = got.json()["items"][0]
        self.assertNotIn("password", item)
        self.assertEqual((item["has_password"], item["cert"], item["kind"], item["url"], item["zone"]), (True, SHA1, "webdav", URL, "lan"))
        with open(profiles._path(uid, "nas.json")) as f:
            raw = f.read()
        self.assertNotIn(PW, raw)                               # sealed
        self.assertEqual(nas.vault.open_(nas.find(uid, nid)["password"]), PW)
        self.assertEqual(c.post("/api/profile/nas", json=dict(name="Doppelt", kind="webdav", url=URL + "/", user=USER, password=PW, cert=SHA1)).status_code, 409)
        # the NAS shows another certificate: the check stops and says so, nothing is sent with the password
        CTX.load_cert_chain(CERT2[0], CERT2[1])
        NAS["auth"].clear()
        r = c.post(f"/api/profile/nas/{nid}/check")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["cert"]["sha256"], SHA2)
        self.assertEqual(NAS["auth"], [])
        self.assertEqual(nas.find(uid, nid)["checked"]["kind"], "cert")
        r = c.put(f"/api/profile/nas/{nid}", json={"cert": SHA2})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["items"][0]["cert"], SHA2)
        self.assertTrue(r.json()["items"][0]["checked"]["ok"])

    def test_addresses_and_fields(self):
        c, uid = profile("NasAdr")
        for kind, url in (("webdav", "ftp://nas.local"), ("webdav", "https://u:p@nas.local"), ("webdav", "https://nas.local/?x=1"),
                          ("webdav", "http://nas.example.de"), ("smb", "smb://nas.example.de"), ("sftp", "https://nas.local"),
                          ("nfs", "nfs://nas.local"), ("webdav", "https://nas.local/a/../b")):
            r = c.post("/api/profile/nas", json={"name": "N", "kind": kind, "url": url, "user": "u", "password": "p"})
            self.assertEqual(r.status_code, 400, (kind, url, r.text))
        self.assertEqual(nas.split("https://NAS.local:443/dav/x/", "webdav"), ("https://nas.local", "/dav/x"))
        self.assertEqual(nas.split("https://nas.local:5006", "webdav"), ("https://nas.local:5006", ""))
        self.assertEqual(nas.split("smb://192.168.1.5/share/a", "smb"), ("smb://192.168.1.5", "/share/a"))
        self.assertEqual(c.post("/api/profile/nas", json={"name": "<b>", "kind": "webdav", "url": URL, "user": USER, "password": PW}).status_code, 400)
        nid = self.connect(c)
        self.assertEqual(c.put(f"/api/profile/nas/{nid}", json={"url": "https://anders.local"}).status_code, 400)
        self.assertEqual(c.put(f"/api/profile/nas/{nid}", json={"user": "jemand"}).status_code, 400)   # needs the password
        r = c.put(f"/api/profile/nas/{nid}", json={"password": "falsch"})
        self.assertEqual(r.status_code, 502)                    # refused by the NAS: nothing changed
        self.assertEqual(nas.vault.open_(nas.find(uid, nid)["password"]), PW)
        self.assertEqual(c.put(f"/api/profile/nas/{nid}", json={"name": "Keller"}).json()["items"][0]["name"], "Keller")
        self.assertEqual(c.put("/api/profile/nas/abcdef", json={"name": "x"}).status_code, 404)
        other, _ = profile("NasAnders")
        self.assertEqual(other.delete(f"/api/profile/nas/{nid}").status_code, 404)   # only the own connections

    def test_logs_and_live_carry_no_address_and_no_user(self):
        c, uid = profile("NasLog")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            nid = self.connect(c)
            c.post(f"/api/profile/nas/{nid}/check")
            c.delete(f"/api/profile/nas/{nid}")
        text = out.getvalue()
        self.assertIn("nas: verbunden art=webdav", text)
        self.assertIn("nas: entfernt", text)
        for secret in ("127.0.0.1", USER, PW, "Synology Keller"):
            self.assertNotIn(secret, text)
        self.assertIn("nas", dict(logfilter.AREAS))
        for k in ("nas_add", "nas_change", "nas_remove"):
            self.assertIn(k, guard.LIVE_WORDS)
        nid = self.connect(c)
        d = nas.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["conns"], 1)
        self.assertNotIn(USER, json.dumps(d))
        self.assertIn("nas", live.TARGETS)
        a = ADMIN.get("/api/admin/nas").json()
        self.assertTrue(a["on"])
        self.assertNotIn(PW, json.dumps(a))
        row = next(x for x in a["rows"] if x["name"] == "Synology Keller")
        self.assertNotIn("url", row)
        self.assertNotIn("user", row)
        c.delete(f"/api/profile/nas/{nid}")
        helpers.set_config(nas_on=False)
        self.assertFalse(nas.for_live()["on"])

    def test_known_everywhere(self):
        self.assertIn(("POST", "/api/profile/nas"), stufen.LIST)
        self.assertIn(("PUT", "/api/profile/nas/{nid}"), stufen.LIST)
        self.assertIn("nas-admin.json", backup.STATE_FILES)
        self.assertEqual(speicher.LOCAL["nas.json"], "Login")
        self.assertIn("nas_on", features.BY_KEY["nas"].admin)
        with open(features.DEFAULTS) as f:
            self.assertIs(json.load(f)["chat"]["nas_on"], False)


class Uses(Base):
    """Eigener Speicher and the backup to the NAS keep their login in the connection (S1, "Umstellung")."""
    def setUp(self):
        super().setUp()
        helpers.set_config(storage_own=True, storage_lan=True)
        speicher._running.clear()

    def test_own_storage_on_a_connection(self):
        c, uid = profile("NasSpeicher")
        nid = self.connect(c)
        r = c.post("/api/profile/speicher", json={"name": "Kopie", "nas": nid, "path": "/home/spark"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(PW, r.text)
        self.assertTrue(any(p.startswith("/home/spark/") for p in NAS["dirs"]))   # the certificate came from the connection
        with open(profiles._path(uid, "speicher.json")) as f:
            stored = json.load(f)["targets"][0]
        self.assertEqual((stored["nas"], stored["path"]), (nid, "/home/spark"))
        for k in ("url", "user", "password", "cert"):
            self.assertNotIn(k, stored)
        t = speicher.load(uid)["targets"][0]
        self.assertEqual((t["url"], t["user"], t["nas"]), (URL + "/home/spark/", USER, nid))
        self.assertEqual(zertpin.sha_of(t["cert"]), SHA1)
        self.assertEqual(c.get("/api/profile/nas").json()["items"][0]["uses"], {"speicher": 1})
        self.assertEqual(c.delete(f"/api/profile/nas/{nid}").status_code, 409)   # still in use
        self.assertEqual(c.post("/api/profile/speicher", json={"name": "X", "nas": "000000", "path": "/x"}).status_code, 404)
        # a new password counts for the use at once
        NAS["pw"] = "neues-nas-passwort-1"
        self.assertEqual(c.put(f"/api/profile/nas/{nid}", json={"password": NAS["pw"]}).status_code, 200)
        self.assertEqual(nas.vault.open_(speicher.load(uid)["targets"][0]["password"]), NAS["pw"])
        tid = speicher.load(uid)["targets"][0]["id"]
        self.assertEqual(c.delete(f"/api/profile/speicher/{tid}").status_code, 200)
        self.assertEqual(c.delete(f"/api/profile/nas/{nid}").status_code, 200)
        self.assertEqual(nas.load(uid), [])

    def test_old_files_move_over_and_keep_working(self):
        c, uid = profile("NasAlt")
        sealed = nas.vault.seal(PW)
        old = {"id": "abcd12", "name": "Alt", "kind": "webdav", "url": URL + "/alt/", "user": USER, "password": sealed,
               "areas": ["gedaechtnis"], "added": 1, "offload": False}
        profiles._write(profiles._path(uid, "speicher.json"), {"key": "", "targets": [old]})
        with open(offsite.FILE, "w") as f:
            json.dump({"on": False, "url": URL + "/backup/", "user": USER, "password": sealed, "sent": []}, f)
        try:
            self.assertGreaterEqual(nas.migrate_all(), 2)
            with open(profiles._path(uid, "speicher.json")) as f:
                moved = json.load(f)["targets"][0]
            self.assertEqual(moved["path"], "/alt")
            self.assertNotIn("password", moved)
            self.assertTrue(os.path.exists(profiles._path(uid, "speicher.vor-nas.json")))
            t = speicher.load(uid)["targets"][0]
            self.assertEqual((t["url"], t["user"], t["password"], t["areas"]), (URL + "/alt/", USER, sealed, ["gedaechtnis"]))
            raw = offsite._raw()
            self.assertEqual(raw.get("path"), "/backup")
            self.assertNotIn("password", raw)
            self.assertEqual((offsite._read()["url"], offsite._read()["user"]), (URL + "/backup/", USER))
            self.assertEqual(len(nas.load(nas.ADMIN)), 1)
            self.assertEqual(nas.uses(nas.ADMIN), {nas.load(nas.ADMIN)[0]["id"]: {"sicherung": 1}})
            self.assertEqual(nas.migrate_all(), 0)                   # once
        finally:
            offsite._write({})
            for p in (os.path.join(nas.STATE, nas.ADMIN_FILE), offsite.FILE[:-5] + ".vor-nas.json"):
                if os.path.exists(p):
                    os.remove(p)

    def test_a_connection_that_is_gone_drops_the_use_not_the_page(self):
        c, uid = profile("NasWeg")
        profiles._write(profiles._path(uid, "speicher.json"), {"key": "", "targets": [
            {"id": "abcd13", "name": "Weg", "kind": "webdav", "nas": "fedcba", "path": "/x", "areas": [], "added": 1}]})
        self.assertEqual(speicher.load(uid)["targets"], [])
        self.assertIsNone(nas.expand(uid, {"nas": "fedcba", "path": "/../etc"}))


if __name__ == "__main__":
    unittest.main()
