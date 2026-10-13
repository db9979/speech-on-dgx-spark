"""Docling-Server (doclingdienst.py): off by default and never for guests, the address only by the main admin
(http only in the home network, https with a checked or accepted certificate), the key sealed and never shown;
files wait for Docling in quiet moments, go there under a neutral name, Docling's text replaces the Spark's own
and the pages it read are not read a second time by the language model; a server that does not answer keeps the
files waiting, at most WAIT_DAYS, and the profile's own preference or the admin switch let them go again."""
import asyncio
import http.server
import io
import json
import os
import re
import ssl
import threading
import unittest

from tests import helpers

helpers.start()
import dienstwacht  # noqa: E402
import doclingdienst  # noqa: E402
import documents  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import zertpin  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from tests.test_offsite import _cert  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0     # a fixed time: no test depends on the clock
KEY = "docling-schluessel-123"
TABLE = "| Monat | Betrag |\n|---|---|\n| Januar | 120 |\n| Februar | 95 |"

SEEN = {"got": [], "answer": "ok", "pages": None}


class Fake(http.server.BaseHTTPRequestHandler):
    """A docling-serve as far as the Spark uses it: convert/file/async, status/poll, result, health."""
    def _send(self, code, obj=None):
        body = json.dumps(obj or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _key_ok(self):
        return self.headers.get("X-Api-Key", "") == KEY

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if not self._key_ok():
            return self._send(401)
        if self.path.startswith("/v1/status/poll/t1"):
            return self._send(200, {"task_id": "t1", "task_status": "success"})
        if self.path == "/v1/result/t1":
            mark = SEEN["mark"]
            pages = SEEN["pages"] or [f"# Rechnung\n\n{TABLE}\n\n<!-- image -->"]
            return self._send(200, {"status": "success", "document": {"md_content": f"\n\n{mark}\n\n".join(pages)}})
        self._send(404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path != "/v1/convert/file/async":
            return self._send(404)
        if SEEN["answer"] == "down":
            return self._send(503)
        if not self._key_ok():
            return self._send(401)
        name = re.search(rb'filename="([^"]*)"', body)
        mark = re.search(rb'name="md_page_break_placeholder"\r\n\r\n([A-Za-z0-9]+)\r\n', body)
        SEEN["mark"] = mark.group(1).decode()
        SEEN["got"].append({"name": name.group(1).decode(), "key": self.headers.get("X-Api-Key"), "size": len(body)})
        self._send(200, {"task_id": "t1", "task_status": "pending"})

    def log_message(self, *a):
        pass


def _serve(tls=None):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    ctx = None
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(tls[0], tls[1])
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


SRV = _serve()
URL = f"http://127.0.0.1:{SRV.server_address[1]}"
CERT = _cert("docling-keller.local")
TLS = _serve(CERT)
TLSURL = f"https://127.0.0.1:{TLS.server_address[1]}"


def run(coro):
    return asyncio.run(coro)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def scanned_pdf(n=1):
    out = io.BytesIO()
    pics = [Image.new("RGB", (800, 1100), (250, 250, 250)) for _ in range(n)]
    pics[0].save(out, "PDF", save_all=True, append_images=pics[1:])
    return out.getvalue()


def upload(c, name, data):
    return c.post("/api/profile/docs", files={"file": (name, data)})


def doc_row(uid, doc_id):
    with documents._Db(uid) as con:
        return dict(con.execute("SELECT * FROM docs WHERE id=?", (doc_id,)).fetchone())


def pages_of(uid, doc_id):
    with documents._Db(uid) as con:
        return [r[0] for r in con.execute("SELECT page FROM pages WHERE doc=? ORDER BY page", (doc_id,)).fetchall()]


def text_of(uid, doc_id):
    with documents._Db(uid) as con:
        return "\n".join(r[0] for r in con.execute("SELECT text FROM chunks WHERE doc=? ORDER BY n", (doc_id,)).fetchall())


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(documents=True, doc_pictures=True, docling=False)
        for k in [k for k in guard._rate if k[0] in ("doc", "docling", "image")]:
            guard._rate.pop(k, None)
        SEEN.update(got=[], answer="ok", pages=None)
        doclingdienst._mem.update(down_until=0.0, now=None)
        doclingdienst._write({})
        for uid in profiles.user_ids():     # pages other tests left waiting: each test reads only its own
            if os.path.exists(documents.db_path(uid)):
                with documents._Db(uid) as con:
                    con.execute("DELETE FROM pages")

    def tearDown(self):
        helpers.set_config(doc_pictures=False, docling=False)
        doclingdienst._write({})
        doclingdienst._mem.update(down_until=0.0, now=None)

    def turn_on(self, url=URL, key=KEY):
        r = ADMIN.put("/api/admin/docling", json={"url": url, "key": key})
        self.assertEqual(r.status_code, 200, r.text)
        helpers.set_config(docling=True)

    def due(self, now=None):
        return run(doclingdienst.due_once(now or NOW))


class Defaults(Base):
    def test_off_by_default_main_admin_only_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["docling"], False)
        self.assertFalse(doclingdienst.admin_on())
        self.assertFalse(ADMIN.get("/api/admin/docling").json()["on"])
        g = TestClient(panel.app)
        for method, path in (("get", "/api/admin/docling"), ("put", "/api/admin/docling"),
                             ("post", "/api/admin/docling/cert"), ("post", "/api/admin/docling/test")):
            r = g.get(path) if method == "get" else getattr(g, method)(path, json={})
            self.assertEqual(r.status_code, 401, path)
        c = profile("Dlara")
        self.assertIn(c.put("/api/admin/docling", json={"url": URL}).status_code, (401, 403))
        self.assertFalse(doclingdienst.allowed(None))
        # the admin switch without an address does nothing
        helpers.set_config(docling=True)
        self.assertFalse(doclingdienst.allowed(uid_of("Dlara")))
        self.assertEqual(self.due(), None)

    def test_switched_on_for_every_profile_with_an_opt_out(self):
        c = profile("Dlena")
        uid = uid_of("Dlena")
        self.turn_on()
        self.assertTrue(doclingdienst.allowed(uid))
        self.assertTrue(doclingdienst.wanted(uid, "Rechnung.PDF"))
        self.assertFalse(doclingdienst.wanted(uid, "notiz.txt"))
        self.assertFalse(doclingdienst.wanted(uid, "Rechnung.pdf", text="schon gelesen"))
        self.assertTrue(c.get("/api/profile/wissen").json()["allow"]["docling"])
        self.assertEqual(c.put("/api/profile/settings", json={doclingdienst.PREF: False}).status_code, 200)
        self.assertFalse(doclingdienst.allowed(uid))
        self.assertIn(doclingdienst.PREF, profiles.NO_PRESET)          # the admin cannot preset it for a profile
        c.put("/api/profile/settings", json={doclingdienst.PREF: True})


class Settings(Base):
    def test_checks_key_sealed_and_new_address_forgets(self):
        put = lambda **b: ADMIN.put("/api/admin/docling", json=b)   # noqa: E731
        for url in ("ftp://x/", "https://user:pw@docling.local/", "https://docling.local/?a=1", "https://x/#y",
                    "http://8.8.8.8:5001", "http://" + "a" * 300):
            self.assertEqual(put(url=url).status_code, 400, url)
        self.assertEqual(put(url=URL + "/", key="mit leerzeichen").status_code, 400)
        r = put(url=URL + "/", key=KEY)
        self.assertEqual(r.status_code, 200, r.text)
        v = r.json()
        self.assertEqual((v["url"], v["plain"], v["has_key"]), (URL, True, True))
        self.assertNotIn(KEY, json.dumps(v))
        self.assertNotIn(KEY, ADMIN.get("/api/admin/docling").text)
        with open(doclingdienst.FILE) as f:
            self.assertNotIn(KEY, f.read())                            # sealed on disk
        self.assertTrue(put(url=URL).json()["has_key"])               # the same address keeps it
        self.assertFalse(put(url=URL.replace("127.0.0.1", "localhost")).json()["has_key"])   # a new one forgets it

    def test_http_only_in_the_home_network(self):
        doclingdienst._lan_only("127.0.0.1", 80)
        doclingdienst._lan_only("192.168.178.20", 5001)
        for host in ("8.8.8.8", "169.254.1.1"):
            with self.assertRaises(ValueError):
                doclingdienst._lan_only(host, 80)
        doclingdienst._write({"url": "http://8.8.8.8:5001"})          # written by hand: still not used
        with self.assertRaises(doclingdienst.Problem) as e:
            run(doclingdienst.convert("a.pdf", b"%PDF"))
        self.assertEqual(e.exception.kind, "blocked")

    def test_sample_read_with_a_table(self):
        self.assertTrue(doclingdienst.sample_pdf().startswith(b"%PDF"))
        self.assertEqual(ADMIN.post("/api/admin/docling/test").status_code, 400)       # address first
        self.turn_on()
        r = ADMIN.post("/api/admin/docling/test").json()
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["table"])
        self.assertNotIn("<!--", r["text"])
        self.assertEqual(SEEN["got"][0]["name"], "dokument.pdf")
        ADMIN.put("/api/admin/docling", json={"url": URL, "key": "falsch-falsch"})
        r = ADMIN.post("/api/admin/docling/test").json()
        self.assertEqual((r["ok"], r["why"]), (False, "key"))
        self.assertIn("Schlüssel", r["say"])
        self.assertTrue(run(doclingdienst.health()))                   # /health needs no key

    def test_self_signed_certificate_only_after_accepting(self):
        self.turn_on(url=TLSURL)
        with self.assertRaises(doclingdienst.Problem) as e:
            run(doclingdienst.convert("a.pdf", doclingdienst.sample_pdf()))
        self.assertEqual(e.exception.kind, "cert")
        self.assertEqual(SEEN["got"], [])                              # not even the key went there
        c = ADMIN.post("/api/admin/docling/cert", json={}).json()
        self.assertEqual(c["sha256"], zertpin.fingerprint(CERT[2]))
        self.assertFalse(c["pinned"])
        self.assertEqual(ADMIN.put("/api/admin/docling", json={"cert": "AB" * 32}).status_code, 409)
        self.assertEqual(ADMIN.put("/api/admin/docling", json={"cert": c["sha256"]}).status_code, 200)
        self.assertTrue(ADMIN.post("/api/admin/docling/test").json()["ok"])
        self.assertEqual(SEEN["got"][-1]["key"], KEY)
        # the Dienst-Wächter looks at /health with exactly that certificate
        part = dienstwacht.active()["docling"]["docling"]
        self.assertEqual(part["url"], TLSURL + "/health")
        self.assertTrue(part["pin"])
        self.assertTrue(run(dienstwacht._http(part)).ok)
        self.assertEqual(ADMIN.post("/api/admin/docling/cert", json={"url": URL}).status_code, 400)   # http has none
        # a new address forgets the certificate
        ADMIN.put("/api/admin/docling", json={"url": TLSURL + "/neu"})
        self.assertEqual(doclingdienst.view()["cert"], "")


class Reading(Base):
    def setUp(self):
        super().setUp()
        self.c = profile("Dmira")
        self.uid = uid_of("Dmira")
        self.c.put("/api/profile/settings", json={"doc_pictures": True, doclingdienst.PREF: True})
        self.turn_on()

    def tearDown(self):
        documents.docling_release(self.uid)
        super().tearDown()

    def send(self, name="Rechnung März.pdf", data=None):
        r = upload(self.c, name, data or scanned_pdf(2))
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        doc_id = doc.get("id") or doc.get("doc", {}).get("id")
        with documents._Db(self.uid) as con:     # created at the fixed time: waiting is measured from it
            con.execute("UPDATE docs SET created=? WHERE id=?", (int(NOW) - 60, doc_id))
        return doc_id

    def test_waits_then_docling_text_replaces_and_pages_go(self):
        doc_id = self.send()
        row = doc_row(self.uid, doc_id)
        self.assertEqual(row["docling"], "wait")
        self.assertEqual(len(documents._wait_files(self.uid, doc_id)), 1)
        self.assertEqual(pages_of(self.uid, doc_id), [1, 2])
        self.assertIsNone(documents.next_page(self.uid))              # the language model waits for Docling
        self.assertEqual(documents.docling_waiting(self.uid), 1)
        SEEN["pages"] = ["# Rechnung\n\n" + TABLE, "kurz"]             # page 2 too short: the language model reads it
        self.assertEqual(self.due(), "docling")
        got = SEEN["got"][-1]
        self.assertEqual((got["name"], got["key"]), ("dokument.pdf", KEY))   # never the file's own name
        row = doc_row(self.uid, doc_id)
        self.assertEqual((row["docling"], row["note"], row["brief"]), ("ok", "mit Docling gelesen", ""))
        self.assertIn("Februar | 95", text_of(self.uid, doc_id))
        self.assertEqual(pages_of(self.uid, doc_id), [2])
        self.assertEqual(documents._wait_files(self.uid, doc_id), [])
        self.assertEqual(documents.next_page(self.uid)[:3], (doc_id, row["name"], 2))
        self.assertEqual(self.due(), None)                             # nothing waits any more
        lv = doclingdienst.for_live()
        self.assertEqual((lv["on"], lv["wait"], lv["ok"]), (True, 0, 1))
        self.assertTrue(all(isinstance(v, (bool, int)) for v in lv.values()))   # numbers only, never a name or text

    def test_server_down_keeps_waiting_until_too_old(self):
        doc_id = self.send()
        SEEN["answer"] = "down"
        self.assertEqual(self.due(), "docling")
        self.assertEqual(doc_row(self.uid, doc_id)["docling"], "wait")
        self.assertTrue(doclingdienst.view()["down"])
        self.assertEqual(self.due(), None)                             # not asked again right away
        doclingdienst._mem["down_until"] = 0.0
        later = NOW + doclingdienst.WAIT_DAYS * 86400 + 1
        self.assertEqual(self.due(later), None)
        row = doc_row(self.uid, doc_id)
        self.assertEqual(row["docling"], "x")
        self.assertIn("zu lange gewartet", row["note"])
        self.assertEqual(documents._wait_files(self.uid, doc_id), [])
        self.assertEqual(pages_of(self.uid, doc_id), [1, 2])          # the language model reads them now
        self.assertIsNotNone(documents.next_page(self.uid))

    def test_opt_out_and_admin_switch_let_go(self):
        doc_id = self.send()
        self.c.put("/api/profile/settings", json={doclingdienst.PREF: False})
        self.assertEqual(self.due(), None)
        self.assertEqual(SEEN["got"], [])                              # nothing went to the server
        self.assertEqual(doc_row(self.uid, doc_id)["docling"], "")
        self.assertEqual(documents._wait_files(self.uid, doc_id), [])
        self.assertFalse(doclingdienst.wanted(self.uid, "b.pdf"))
        self.c.put("/api/profile/settings", json={doclingdienst.PREF: True})
        doc2 = self.send("zwei.pdf")
        helpers.set_config(docling=False)
        self.assertEqual(self.due(), None)
        self.assertEqual(SEEN["got"], [])
        self.assertEqual(doc_row(self.uid, doc2)["docling"], "")
        self.assertEqual(doclingdienst.for_live(), {"on": False})

    def test_no_page_breaks_need_enough_text_for_every_page(self):
        doc_id = self.send()
        SEEN["pages"] = ["nur ein kurzer Satz ohne Seitenumbruch, zu wenig für zwei Seiten"]
        documents.docling_done(self.uid, doc_id, [(None, SEEN["pages"][0])], "", doclingdienst.TEXT_MIN)
        self.assertEqual(pages_of(self.uid, doc_id), [1, 2])
        doc2 = self.send("lang.pdf")
        documents.docling_done(self.uid, doc2, [(None, "x" * 200)], "", doclingdienst.TEXT_MIN)
        self.assertEqual(pages_of(self.uid, doc2), [])
        self.assertEqual(doc_row(self.uid, doc2)["state"], "ready")

    def test_unreadable_file_keeps_the_spark_text(self):
        doc_id = self.send()
        documents.docling_done(self.uid, doc_id, None, "failed")
        row = doc_row(self.uid, doc_id)
        self.assertEqual(row["docling"], "x")
        self.assertIn("nicht lesbar", row["note"])
        self.assertEqual(pages_of(self.uid, doc_id), [1, 2])
        self.assertEqual(documents.docling_done(self.uid, doc_id, [(1, "spät")]), 0)   # let go: nothing changes

    def test_delete_drops_the_waiting_file(self):
        doc_id = self.send()
        self.assertEqual(len(documents._wait_files(self.uid, doc_id)), 1)
        documents.delete(self.uid, doc_id)
        self.assertEqual(documents._wait_files(self.uid, doc_id), [])

    def test_page_marker_and_comments(self):
        self.assertEqual(doclingdienst._split("a <!-- image --> b", "M"), [(None, "a  b")])
        self.assertEqual(doclingdienst._split("eins\nMzwei\nM\n", "M"), [(1, "eins"), (2, "zwei")])
        self.assertEqual(doclingdienst._split("  ", "M"), [])


class Everywhere(unittest.TestCase):
    def test_wired_in(self):
        import backup
        import features
        import logfilter
        import speicher
        import stufen
        self.assertIn("docling.json", backup.STATE_FILES)
        self.assertEqual(features.BY_KEY["docling"].parent, "documents")
        self.assertIn("docling", dienstwacht.SVC)
        self.assertIn("docling", live.TARGETS)
        self.assertEqual(live.TOOLS["Docling"], "docling")
        self.assertIn(doclingdienst.WAIT_DIR, speicher.LOCAL)
        self.assertIn(("PUT", "/api/admin/docling"), stufen.LIST)
        self.assertEqual([a for a, rx in logfilter.AREAS if re.search(rx, "docling: server down | retry in 10 min")][0], "wissen")
        self.assertIn("docling", guard.RATE)
