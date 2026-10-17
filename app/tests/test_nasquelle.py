"""Wissensordner (nasquelle.py, plan synology-bauplan.md S2) against a fake WebDAV NAS. One self-test per rule: off
without the admin's switch, never for guests, a blocked profile still sees and removes its folders; only reading
(PROPFIND and GET, nothing else reaches the NAS); new, changed and deleted files follow the folder; a document
deleted under Dokumente stays left out until the file changes; hidden folders, foreign kinds, too large files and
content that does not fit the ending are never read; outside listings with entities are refused; the own limit for
documents from places; opening fetches the file from the place; a place in use is not removed; logs carry no path,
no file name and no profile name; Live and the Dienst-Wächter know it. No test reads the clock."""
import asyncio
import base64
import contextlib
import email.utils
import io
import os
import unittest
import zipfile
from unittest import mock

from tests import helpers

helpers.start()
import backup  # noqa: E402
import dienstwacht  # noqa: E402
import documents  # noqa: E402
import features  # noqa: E402
import live  # noqa: E402
import logfilter  # noqa: E402
import nasquelle  # noqa: E402
import panel  # noqa: E402
import speicher  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PORT = helpers._port()
BASE = f"http://127.0.0.1:{PORT}"
SECRET = "Geheimvertrag-Zebra"
DAV = {"files": {}, "user": "leser", "pw": "nas-lesen-4711", "mode": "", "calls": []}
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
                   f'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


DOCX = docx("Der Brief an die Hausverwaltung wegen der Heizung.")


def fake():
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["PROPFIND", "GET", "PUT", "DELETE", "MKCOL", "MOVE"])
    async def dav(path: str, req: Request):
        DAV["calls"].append(req.method)
        if DAV["mode"] == "down":
            return Response(status_code=503)
        if req.headers.get("authorization", "") != "Basic " + base64.b64encode(f"{DAV['user']}:{DAV['pw']}".encode()).decode():
            return Response(status_code=401)
        path = path.strip("/")
        if req.method == "GET":
            if path not in DAV["files"]:
                return Response(status_code=404)
            return Response(DAV["files"][path][0], media_type="application/octet-stream")
        if req.method != "PROPFIND":
            return Response(status_code=403)
        pre = path + "/" if path else ""
        if path and path not in DAV["files"] and not any(k.startswith(pre) for k in DAV["files"]):
            return Response(status_code=404)
        kids = {}
        for k, (data, mt) in DAV["files"].items():
            if k.startswith(pre):
                rest = k[len(pre):]
                kids[rest.split("/")[0]] = None if "/" in rest else (len(data), mt)
        rows = [f"<d:response><d:href>/{pre}</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype>"
                f"</d:prop></d:propstat></d:response>"]
        for n, x in kids.items():
            href = "/" + pre + n
            if x is None:
                rows.append(f"<d:response><d:href>{href}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype>"
                            f"</d:prop></d:propstat></d:response>")
            else:
                rows.append(f"<d:response><d:href>{href}</d:href><d:propstat><d:prop><d:resourcetype/><d:getcontentlength>{x[0]}"
                            f"</d:getcontentlength><d:getlastmodified>{email.utils.formatdate(x[1], usegmt=True)}</d:getlastmodified>"
                            f"</d:prop></d:propstat></d:response>")
        return Response('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(rows) + "</d:multistatus>", status_code=207)
    return app


helpers._serve(fake(), PORT)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def run(coro):
    return asyncio.run(coro)


def tree():
    DAV["files"] = {
        "dav/Ablage/Vertraege/miete.txt": (b"Der Mietvertrag kann mit drei Monaten Frist gekuendigt werden.", 1_700_000_000),
        "dav/Ablage/Vertraege/notiz.md": (b"# Notiz\nStrom wechselt im Mai.", 1_700_000_000),
        "dav/Ablage/Vertraege/brief.docx": (DOCX, 1_700_000_000),
        f"dav/Ablage/{SECRET}.txt": (b"Zebra steht im Zoo.", 1_700_000_000),
        "dav/Ablage/programm.exe": (b"MZ\x90\x00", 1_700_000_000),
        "dav/Ablage/falsch.pdf": (b"MZ\x90\x00 kein pdf", 1_700_000_000),
        "dav/Ablage/@eaDir/miete.txt@SynoEAStream": (b"x", 1_700_000_000),
        "dav/Ablage/.versteckt.txt": (b"versteckt", 1_700_000_000),
        "dav/Ablage/Fotos/bild.jpg": (b"\xff\xd8\xff\xe0 jpg", 1_700_000_000),
    }


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(nas_on=True, nas_sources=True, documents=True, deny={})
        DAV.update(mode="", calls=[], pw="nas-lesen-4711")
        tree()
        nasquelle._running.clear()
        self._spawn = mock.patch.object(nasquelle, "spawn", lambda coro: coro.close())   # rounds run in the test, in order
        self._spawn.start()

    def tearDown(self):
        self._spawn.stop()
        helpers.set_config(nas_on=False, nas_sources=False, deny={})

    def place(self, c):
        r = c.post("/api/profile/nas", json={"name": "Keller", "kind": "webdav", "url": BASE, "user": DAV["user"], "password": DAV["pw"]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]

    def folder(self, c, nid, path="/dav/Ablage", **kw):
        r = c.post("/api/profile/nasquelle", json=dict(dict(nas=nid, path=path), **kw))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]

    def ready(self, name):
        c, uid = profile(name)
        nid = self.place(c)
        return c, uid, nid, self.folder(c, nid)

    def docs(self, uid):
        return {d["name"]: d for d in documents.list_docs(uid) if d.get("source") == "nas"}


class Switches(Base):
    def test_off_without_the_admin_switch_and_never_for_guests(self):
        c, uid = profile("NqAus")
        nid = self.place(c)
        helpers.set_config(nas_sources=False)
        DAV["calls"] = []
        self.assertFalse(c.get("/api/whoami").json().get("nasquelle"))
        self.assertFalse(c.get("/api/profile/nasquelle").json()["on"])
        self.assertEqual(c.post("/api/profile/nasquelle", json={"nas": nid, "path": "/dav/Ablage"}).status_code, 403)
        self.assertEqual(c.get(f"/api/profile/nasquelle/tree?nas={nid}&path=/dav").status_code, 403)
        self.assertEqual(c.post("/api/profile/nasquelle/preview", json={"nas": nid, "path": "/dav"}).status_code, 403)
        self.assertEqual(DAV["calls"], [])                                  # nothing went to the NAS
        helpers.set_config(nas_sources=True)
        self.assertTrue(c.get("/api/whoami").json().get("nasquelle"))       # no profile switch: the admin's is enough
        self.assertEqual(features.BY_KEY["nasquelle"].pref, "")
        helpers.set_config(nas_on=False)                                    # hangs below "Speicher und NAS"
        self.assertFalse(nasquelle.allowed(uid))
        helpers.set_config(nas_on=True, documents=False)                    # and needs Eigene Dokumente
        self.assertFalse(nasquelle.allowed(uid))
        helpers.set_config(documents=True, public=True)
        try:
            g = TestClient(panel.app)
            for r in (g.get("/api/profile/nasquelle"), g.post("/api/profile/nasquelle", json={}),
                      g.get("/api/profile/nasquelle/tree"), g.delete("/api/profile/nasquelle/abc123")):
                self.assertIn(r.status_code, (401, 403))
        finally:
            helpers.set_config(public=False)
        self.assertEqual(TestClient(panel.app).get("/api/admin/nasquelle").status_code, 401)

    def test_a_blocked_profile_keeps_seeing_and_removing_its_folders(self):
        c, uid, nid, sid = self.ready("NqSperre")
        run(nasquelle.sync_once(uid, sid))
        helpers.set_config(deny={"nasquelle": [uid]})
        self.assertFalse(nasquelle.allowed(uid))
        self.assertEqual(c.post(f"/api/profile/nasquelle/{sid}/now").status_code, 403)
        self.assertNotIn(uid, [u for u, _ in run(nasquelle.round_once(now=10 ** 10))])   # the round skips it
        v = c.get("/api/profile/nasquelle").json()
        self.assertEqual((v["on"], [s["id"] for s in v["sources"]]), (False, [sid]))
        r = c.delete(f"/api/profile/nasquelle/{sid}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(nasquelle.sources(uid), [])
        self.assertEqual(documents.count_source(uid, "nas"), 0)


class Reading(Base):
    def test_reads_only_what_fits_and_never_writes_to_the_place(self):
        c, uid, nid, sid = self.ready("NqLesen")
        got = run(nasquelle.sync_once(uid, sid))
        self.assertTrue(got["ok"], got)
        st = nasquelle.state(uid, sid)
        read = sorted(x["p"] for x in st["files"].values() if x.get("d"))
        self.assertEqual(read, sorted(["Vertraege/miete.txt", "Vertraege/notiz.md", "Vertraege/brief.docx", f"{SECRET}.txt"]))
        self.assertEqual(st["out"].get("art"), 1)                 # programm.exe
        self.assertEqual(st["out"].get("inhalt"), 1)              # falsch.pdf is no PDF
        self.assertEqual(st["out"].get("gruppe"), 1)              # bild.jpg: pictures not picked
        self.assertGreaterEqual(st["out"].get("versteckt", 0), 2)  # @eaDir and .versteckt.txt
        self.assertEqual(set(DAV["calls"]), {"PROPFIND", "GET"})   # only reading
        self.assertEqual(documents.count_source(uid, "nas"), 4)
        hits = documents.search(uid, "Mietvertrag Frist gekuendigt")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["place"], "/dav/Ablage/Vertraege")          # the source shows the folder
        self.assertEqual(self.docs(uid)["miete.txt"]["place"], "/dav/Ablage/Vertraege")

    def test_new_changed_and_deleted_files_follow_the_folder(self):
        c, uid, nid, sid = self.ready("NqFolgen")
        run(nasquelle.sync_once(uid, sid))
        st = nasquelle.state(uid, sid)
        old = {x["p"]: x["d"] for x in st["files"].values() if x.get("d")}
        DAV["files"]["dav/Ablage/Vertraege/miete.txt"] = (b"Neu: sechs Monate Frist.", 1_700_000_500)
        DAV["files"]["dav/Ablage/neu.txt"] = (b"Ganz neu.", 1_700_000_500)
        del DAV["files"]["dav/Ablage/Vertraege/notiz.md"]
        got = run(nasquelle.sync_once(uid, sid))
        self.assertEqual((got["new"], got["gone"]), (2, 1), got)
        now = {x["p"]: x["d"] for x in nasquelle.state(uid, sid)["files"].values() if x.get("d")}
        self.assertNotIn("Vertraege/notiz.md", now)
        self.assertIn("neu.txt", now)
        self.assertNotEqual(now["Vertraege/miete.txt"], old["Vertraege/miete.txt"])
        self.assertEqual(documents.count_source(uid, "nas"), 4)
        got = run(nasquelle.sync_once(uid, sid))
        self.assertEqual((got["new"], got["gone"]), (0, 0))         # nothing changed: nothing read again

    def test_deleted_under_documents_stays_out_until_the_file_changes(self):
        c, uid, nid, sid = self.ready("NqAus2")
        run(nasquelle.sync_once(uid, sid))
        doc = next(x["d"] for x in nasquelle.state(uid, sid)["files"].values() if x["p"] == "Vertraege/miete.txt")
        self.assertEqual(c.delete(f"/api/profile/docs/{doc}").status_code, 200)
        self.assertEqual(documents.count_source(uid, "nas"), 3)
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(documents.count_source(uid, "nas"), 3)
        self.assertIn("dav/Ablage/Vertraege/miete.txt", DAV["files"])            # never deleted at the place
        DAV["files"]["dav/Ablage/Vertraege/miete.txt"] = (b"Geaendert.", 1_700_000_900)
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(documents.count_source(uid, "nas"), 4)

    def test_groups_and_left_out_sub_folders(self):
        c, uid, nid, sid = self.ready("NqGruppen")
        run(nasquelle.sync_once(uid, sid))
        r = c.put(f"/api/profile/nasquelle/{sid}", json={"groups": ["text"], "skip": ["Vertraege"]})
        self.assertEqual(r.status_code, 200, r.text)
        run(nasquelle.sync_once(uid, sid))
        read = sorted(x["p"] for x in nasquelle.state(uid, sid)["files"].values() if x.get("d"))
        self.assertEqual(read, [f"{SECRET}.txt"])
        self.assertEqual(documents.count_source(uid, "nas"), 1)

    def test_own_limit_for_documents_from_places(self):
        c, uid, nid, sid = self.ready("NqVoll")
        with mock.patch.object(nasquelle, "max_docs", lambda: 2):
            got = run(nasquelle.sync_once(uid, sid))
        self.assertTrue(got["full"])
        self.assertEqual(documents.count_source(uid, "nas"), 2)
        self.assertEqual(nasquelle.state(uid, sid)["fail"]["kind"], "voll")
        self.assertGreaterEqual(nasquelle.MAX_SOURCES, 1)
        self.assertEqual(nasquelle._int("nas_max_docs", 5000, 100, 20000), 5000)

    def test_over_the_limit_documents_first_then_the_newest(self):
        """Dominik 2026-10-14: which files get in when a folder holds more than the limit. Documents, tables and text
        before pictures and scans, the newest first; the preview says how many stay out and how many rounds."""
        items = [("Fotos/a.jpg", 1, 300), ("alt.pdf", 1, 100), ("neu.pdf", 1, 200), ("Fotos/b.png", 1, 400),
                 ("notiz.txt", 1, None)]
        self.assertEqual([x[0] for x in sorted(items, key=nasquelle.first)],
                         ["neu.pdf", "alt.pdf", "notiz.txt", "Fotos/b.png", "Fotos/a.jpg"])
        gb = 1024 ** 3
        self.assertEqual(nasquelle.plan(16932, 8 * gb, 5000), {"read": 5000, "left_out": 11932, "rounds": 25})
        self.assertEqual(nasquelle.plan(300, 5 * gb, 5000), {"read": 300, "left_out": 0, "rounds": 5})   # 1 GB per round
        self.assertEqual(nasquelle.plan(10, gb, 0), {"read": 0, "left_out": 10, "rounds": 0})

    def test_opening_fetches_the_file_from_the_place(self):
        c, uid, nid, sid = self.ready("NqOeffnen")
        run(nasquelle.sync_once(uid, sid))
        doc = next(x["d"] for x in nasquelle.state(uid, sid)["files"].values() if x["p"] == "Vertraege/brief.docx")
        r = c.get(f"/api/profile/wissen/{doc}/file")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, DOCX)
        self.assertEqual(os.listdir(nasquelle._tmp_dir()), [])     # the temporary file is gone
        DAV["mode"] = "down"
        self.assertEqual(c.get(f"/api/profile/wissen/{doc}/file").status_code, 503)

    def test_wrong_password_is_a_failure_with_its_reason(self):
        c, uid, nid, sid = self.ready("NqPasswort")
        DAV["pw"] = "anders"
        got = run(nasquelle.sync_once(uid, sid))
        self.assertEqual(got, {"ok": False, "kind": "auth"})
        v = c.get("/api/profile/nasquelle").json()["sources"][0]
        self.assertEqual(v["fail"]["kind"], "auth")
        self.assertEqual(c.post(f"/api/profile/nasquelle/{sid}/now").status_code, 502)

    def test_a_place_in_use_is_not_removed(self):
        c, uid, nid, sid = self.ready("NqInUse")
        r = c.delete(f"/api/profile/nas/{nid}")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("Wissensordner", r.text)
        self.assertEqual(c.delete(f"/api/profile/nasquelle/{sid}").status_code, 200)
        self.assertEqual(c.delete(f"/api/profile/nas/{nid}").status_code, 200)


class Pages(Base):
    def test_tree_and_preview(self):
        c, uid = profile("NqBaum")
        nid = self.place(c)
        d = c.get(f"/api/profile/nasquelle/tree?nas={nid}&path=/dav/Ablage").json()
        self.assertEqual(d["dirs"], ["Fotos", "Vertraege"])        # @eaDir never shown
        p = c.post("/api/profile/nasquelle/preview", json={"nas": nid, "path": "/dav/Ablage"}).json()
        self.assertEqual(p["files"], 5)                           # 3 text, 1 docx, 1 pdf (content is checked when read)
        self.assertEqual((p["read"], p["left_out"], p["rounds"], p["limit"]), (5, 0, 1, 5000))
        self.assertEqual(p["out"].get("art"), 1)
        self.assertTrue(p["complete"])
        self.assertEqual(c.get(f"/api/profile/nasquelle/tree?nas={nid}&path=/dav/../etc").status_code, 400)
        self.assertEqual(c.post("/api/profile/nasquelle", json={"nas": nid, "path": "/dav/Gibtsnicht"}).status_code, 502)
        self.assertEqual(c.post("/api/profile/nasquelle", json={"nas": "ffffff", "path": "/dav"}).status_code, 404)

    def test_outside_listings_are_data(self):
        evil = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "boom">]><d:multistatus xmlns:d="DAV:">'
                b'<d:response><d:href>/a/&e;</d:href></d:response></d:multistatus>')
        with self.assertRaises(nasquelle.SourceError):
            nasquelle.parse_multistatus(evil, "/a")
        ok = (b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
              b'<d:response><d:href>/a/b.txt</d:href><d:propstat><d:prop><d:getcontentlength>9999999999999999999</d:getcontentlength></d:prop></d:propstat></d:response>'
              b'<d:response><d:href>/a/../etc/passwd</d:href></d:response><d:response><d:href>/anders/x.txt</d:href></d:response>'
              b'<d:response><d:href>/a/sub/tief.txt</d:href></d:response></d:multistatus>')
        self.assertEqual(nasquelle.parse_multistatus(ok, "/a"), [("b.txt", False, 0, 0)])

    def test_kinds_and_content(self):
        self.assertEqual(nasquelle.classify("a/b.exe", 10, ["dokumente"]), "art")
        self.assertEqual(nasquelle.classify(".git/x.txt", 10, ["text"]), "versteckt")
        self.assertEqual(nasquelle.classify("~$brief.docx", 10, ["dokumente"]), "versteckt")
        self.assertEqual(nasquelle.classify("x.jpg", 10, ["bilder"], pictures=False), "gruppe")
        self.assertIsNone(nasquelle.classify("x.jpg", 10, ["bilder"], pictures=True))
        self.assertEqual(nasquelle.classify("x.txt", documents.MAX_OTHER + 1, ["text"]), "gross")
        self.assertTrue(nasquelle.fits("a.pdf", PDF))
        self.assertFalse(nasquelle.fits("a.pdf", b"MZ\x90"))
        self.assertFalse(nasquelle.fits("a.txt", b"text\0binary"))
        self.assertTrue(nasquelle.fits("a.docx", b"PK\x03\x04"))
        self.assertFalse(nasquelle.fits("a.docx", b"%PDF"))
        for bad in ("/a/../b", "/a/\x00b"):
            with self.assertRaises(ValueError):
                nasquelle.clean_path(bad)


class Haushalt(Base):
    """S5: an admin profile picks a folder at its place for the whole household; every profile the admin released it
    for finds its documents (marked "Haushalt"), guests and blocked profiles never; it hangs on the admin's place."""
    def setUp(self):
        super().setUp()
        import notaus
        self._admins = []
        self._old = notaus.admin_uids
        notaus.admin_uids = lambda: list(self._admins)
        helpers.set_config(nas_shared=True)

    def tearDown(self):
        import notaus
        notaus.admin_uids = self._old
        for s in nasquelle.sources(nasquelle.HAUS):
            nasquelle.remove_source(nasquelle.HAUS, s["id"])
        helpers.set_config(nas_shared=False)
        super().tearDown()

    def admin(self, name):
        c, uid = profile(name)
        self._admins.append(uid)
        return c, uid, self.place(c)

    def haus(self, c, nid):
        r = c.post("/api/profile/nasquelle", json={"nas": nid, "path": "/dav/Ablage", "haus": True})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]

    def test_only_an_admin_profile_with_the_switch_chooses_it(self):
        c, uid = profile("NqHausNein")
        nid = self.place(c)
        r = c.post("/api/profile/nasquelle", json={"nas": nid, "path": "/dav/Ablage", "haus": True})
        self.assertEqual(r.status_code, 403, r.text)                    # no admin profile
        self.assertFalse(c.get("/api/profile/nasquelle").json()["haus"]["may"])
        a, auid, anid = self.admin("NqHausAdmin")
        helpers.set_config(nas_shared=False)
        self.assertEqual(a.post("/api/profile/nasquelle", json={"nas": anid, "path": "/dav/Ablage", "haus": True}).status_code, 403)
        helpers.set_config(nas_shared=True)
        self.assertTrue(a.get("/api/profile/nasquelle").json()["haus"]["may"])
        sid = self.haus(a, anid)
        self.assertEqual(nasquelle.sources(auid), [])                    # not the admin's own Wissensordner
        s = nasquelle.find(nasquelle.HAUS, sid)
        self.assertEqual((s["owner"], s["nas"]), (auid, anid))
        self.assertEqual([x["id"] for x in a.get("/api/profile/nasquelle").json()["haus"]["sources"]], [sid])
        self.assertEqual(c.delete(f"/api/profile/nasquelle/{sid}").status_code, 404)   # another profile cannot touch it
        self.assertEqual(c.post(f"/api/profile/nasquelle/{sid}/now").status_code, 404)

    def test_every_released_profile_finds_it_guests_and_blocked_never(self):
        a, auid, anid = self.admin("NqHausLeser")
        sid = self.haus(a, anid)
        got = run(nasquelle.sync_once(nasquelle.HAUS, sid))
        self.assertTrue(got["ok"], got)
        self.assertEqual(set(DAV["calls"]), {"PROPFIND", "GET"})       # only reading
        b, buid = profile("NqHausAnna")
        import wissen
        hits = run(wissen.search(buid, "Mietvertrag Frist gekuendigt", semantic=False))
        self.assertTrue(hits and hits[0].get("owner") == "Haushalt", hits)
        self.assertIn("Haushalt", [d["owner"] for d in wissen.shared_list(buid)])
        doc = next(x["d"] for x in nasquelle.state(nasquelle.HAUS, sid)["files"].values() if x["p"] == "Vertraege/brief.docx")
        r = b.get(f"/api/profile/wissen/{doc}/file")                    # opened from the admin's place, not kept
        self.assertEqual((r.status_code, r.content), (200, DOCX))
        self.assertFalse(nasquelle.haus_find(None))                      # guests: never
        helpers.set_config(deny={"nashaushalt": [buid]})
        self.assertFalse(run(wissen.search(buid, "Mietvertrag Frist gekuendigt", semantic=False)))
        self.assertEqual(b.get(f"/api/profile/wissen/{doc}/file").status_code, 404)
        helpers.set_config(deny={}, nas_shared=False)
        self.assertFalse(run(wissen.search(buid, "Mietvertrag Frist gekuendigt", semantic=False)))
        self.assertNotIn(nasquelle.HAUS, [u for u, _ in run(nasquelle.round_once(now=10 ** 10))])

    def test_it_hangs_on_the_admin_and_its_place(self):
        a, auid, anid = self.admin("NqHausOrt")
        sid = self.haus(a, anid)
        run(nasquelle.sync_once(nasquelle.HAUS, sid))
        self.assertGreater(documents.count_source(nasquelle.HAUS, "nas"), 0)
        r = a.delete(f"/api/profile/nas/{anid}")
        self.assertEqual(r.status_code, 409, r.text)                     # the place is in use for the household
        self._admins.remove(auid)                                        # no admin any more: nothing is read
        self.assertEqual(run(nasquelle.sync_once(nasquelle.HAUS, sid)), {"ok": False, "kind": "gone"})
        self._admins.append(auid)
        self.assertEqual(a.delete(f"/api/profile/nasquelle/{sid}").status_code, 200)
        self.assertEqual(documents.count_source(nasquelle.HAUS, "nas"), 0)
        sid = self.haus(a, anid)
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{auid}").status_code, 200)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(nasquelle.round_once(now=10 ** 10))
        self.assertIsNone(nasquelle.find(nasquelle.HAUS, sid))            # the profile is gone, so is its folder
        self.assertIn("nasquelle: haushalt entfernt | besitzer weg", out.getvalue())


class Everywhere(Base):
    def test_the_iphone_app_shows_the_nas_and_opens_from_it(self):
        """S8: documents from a place carry "NAS · folder" in Ich → Dokumente of the iPhone app and open from the
        place through the Spark (the profile's docs list gives source and place; never a file name of the folder)."""
        c, uid, nid, sid = self.ready("NqApp")
        run(nasquelle.sync_once(uid, sid))
        d = next(x for x in c.get("/api/profile/docs").json() if x["name"] == "miete.txt")
        self.assertEqual((d["source"], d["place"]), ("nas", "/dav/Ablage/Vertraege"))
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isdir(os.path.join(root, "ios")):
            self.skipTest("ios/ is not in an app/-only copy")
        with open(os.path.join(root, "ios", "Shared", "SparkAPI.swift"), encoding="utf-8") as f:
            api = f.read()
        with open(os.path.join(root, "ios", "Spark", "DocumentsView.swift"), encoding="utf-8") as f:
            view = f.read()
        self.assertIn('source: String((d["source"] as? String', api)
        self.assertIn('doc.source == "nas" ? "NAS · " + (doc.place.isEmpty ? "/" : doc.place)', view)   # the folder, never more
        self.assertIn('if doc.file || doc.source == "nas" { original = try? await api.docOriginal(doc.id) }', view)

    def test_logs_without_paths_names_or_profiles(self):
        c, uid, nid, sid = self.ready("NqLogZebra")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(nasquelle.sync_once(uid, sid))
            DAV["pw"] = "anders"
            run(nasquelle.sync_once(uid, sid))
            DAV["pw"] = "nas-lesen-4711"
            c.delete(f"/api/profile/nasquelle/{sid}")
        lines = [x for x in out.getvalue().splitlines() if x.startswith("nasquelle:")]
        self.assertTrue(any("abgeglichen" in x for x in lines), lines)
        self.assertTrue(any("fehler | art=auth" in x for x in lines), lines)
        self.assertTrue(any("entfernt" in x for x in lines), lines)
        text = out.getvalue()
        for word in (SECRET, "Vertraege", "miete", "NqLogZebra", uid, "Ablage", BASE):
            self.assertNotIn(word, text)
        self.assertTrue(all(logfilter.parse(x)["area"] == "nas" for x in lines), lines)

    def test_live_watch_backup_and_features(self):
        c, uid, nid, sid = self.ready("NqLive")
        run(nasquelle.sync_once(uid, sid))
        n = nasquelle.for_live()
        self.assertTrue(n["on"])
        self.assertGreaterEqual((n["profiles"], n["folders"], n["docs"]), (1, 1, 4))
        self.assertEqual(set(n), {"on", "profiles", "folders", "bad", "docs", "haus_folders", "haus_bad", "haus_docs"})   # numbers only
        self.assertTrue(all(type(v) is int for k, v in n.items() if k != "on"))
        self.assertIn("nasquelle", live.TARGETS)
        self.assertIn("wissen", dienstwacht.SVC)
        self.assertTrue(any(uid in p["uids"] for p in nasquelle.probes().values()))
        self.assertIn("nasquelle.json", speicher.LOCAL)
        self.assertIn("nasquelle-tmp", backup.STATE_LOCAL)
        self.assertEqual(features.BY_KEY["nasquelle"].parent, "nas")
        rows = ADMIN.get("/api/admin/nasquelle").json()["rows"]
        self.assertTrue(rows)
        self.assertNotIn("Ablage", str(rows))
        helpers.set_config(nas_sources=False)
        self.assertEqual(nasquelle.for_live(), {"on": False})
        self.assertEqual(nasquelle.probes(), {})


if __name__ == "__main__":
    unittest.main()
