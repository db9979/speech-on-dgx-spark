"""Ablage-Ordner (nasablage.py, plan synology-bauplan.md S4). One self-test per rule: off without the admin's switch,
never for guests, only a place in the home network; the Spark writes only into spark_ablage (Erstellt, Eingang's
own sub folders), never over a file and never deletes; nas_ablegen only proposes, files after a plain "Ja" in the
same conversation and never after anything else; Eingang takes files in like an upload and moves them to erledigt
or abgelehnt; made documents go into Erstellt unless unticked; Notaus holds it; logs carry no path, no file name
and no profile name. A fake WebDAV server stands for the NAS. No test reads the clock."""
import asyncio
import base64
import contextlib
import io
import os
import unittest
import zipfile
from unittest import mock
from urllib.parse import unquote

from tests import helpers

helpers.start()
import documents  # noqa: E402
import extras  # noqa: E402
import nasablage  # noqa: E402
import panel  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PORT = helpers._port()
BASE = f"http://127.0.0.1:{PORT}"
NAS = {"dirs": set(), "files": {}, "user": "spark", "pw": "ablage-4711", "calls": [], "readonly": False, "nomake": False}


def docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
                   f'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def fake():
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["PROPFIND", "GET", "PUT", "DELETE", "MKCOL", "MOVE"])
    async def dav(path: str, req: Request):
        path = unquote(path).strip("/")
        NAS["calls"].append((req.method, path))
        if req.headers.get("authorization", "") != "Basic " + base64.b64encode(f"{NAS['user']}:{NAS['pw']}".encode()).decode():
            return Response(status_code=401)
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if req.method == "MKCOL":
            if path in NAS["dirs"]:
                return Response(status_code=405)
            if (parent and parent not in NAS["dirs"]) or (not parent and NAS["nomake"]):
                return Response(status_code=409)
            if NAS["readonly"]:
                return Response(status_code=403)
            NAS["dirs"].add(path)
            return Response(status_code=201)
        if req.method == "PUT":
            if NAS["readonly"]:
                return Response(status_code=403)
            if parent not in NAS["dirs"]:
                return Response(status_code=409)
            if path in NAS["files"] and req.headers.get("if-none-match") == "*":
                return Response(status_code=412)
            NAS["files"][path] = await req.body()
            return Response(status_code=201)
        if req.method == "DELETE":
            NAS["files"].pop(path, None)
            return Response(status_code=204)
        if req.method == "MOVE":
            dst = unquote(req.headers["destination"].split(f":{PORT}", 1)[1]).strip("/")
            if dst in NAS["files"] and req.headers.get("overwrite") == "F":
                return Response(status_code=412)
            NAS["files"][dst] = NAS["files"].pop(path)
            return Response(status_code=201)
        if req.method == "GET":
            return Response(NAS["files"][path]) if path in NAS["files"] else Response(status_code=404)
        if path and path not in NAS["dirs"]:
            return Response(status_code=404)
        pre = path + "/" if path else ""
        dirs = sorted({d[len(pre):].split("/")[0] for d in NAS["dirs"] if d.startswith(pre) and d != path})
        files = sorted(f[len(pre):] for f in NAS["files"] if f.startswith(pre) and "/" not in f[len(pre):])
        rows = [f"<d:response><d:href>/{pre}</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>"]
        rows += [f"<d:response><d:href>/{pre}{k}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>" for k in dirs]
        rows += [f"<d:response><d:href>/{pre}{k}</d:href><d:propstat><d:prop><d:resourcetype/><d:getcontentlength>{len(NAS['files'][pre + k])}"
                 f"</d:getcontentlength></d:prop></d:propstat></d:response>" for k in files]
        return Response('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(rows) + "</d:multistatus>", status_code=207)
    return app


helpers._serve(fake(), PORT)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def ctx(uid, text="", src="web:c1"):
    return {"who": {"id": uid, "name": "x"}, "own": True, "private": True, "client": "web", "src": src, "text": text}


def writes():
    """What the Spark wrote, apart from S3's probe file (written and deleted at once when it is set up)."""
    return [(m, p) for m, p in NAS["calls"] if m in ("PUT", "DELETE", "MKCOL", "MOVE") and ".spark-probe-" not in p]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(nas_on=True, nas_drop=True, documents=True, deny={})
        NAS.update(dirs={"spark_ablage", "Dokumente"}, files={"Dokumente/alt.txt": b"bleibt"}, calls=[], readonly=False, nomake=False)

    def tearDown(self):
        helpers.set_config(nas_on=False, nas_drop=False, deny={})

    def place(self, c):
        r = c.post("/api/profile/nas", json={"name": "Keller", "kind": "webdav", "url": BASE, "user": NAS["user"], "password": NAS["pw"]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]

    def ready(self, name):
        c, uid = profile(name)
        nid = self.place(c)
        r = c.post("/api/profile/nasablage", json={"nas": nid})
        self.assertEqual(r.status_code, 200, r.text)
        NAS["calls"] = []
        return c, uid, nid


class Setup(Base):
    def test_off_guests_and_making_the_folders(self):
        c, uid = profile("NaEin")
        nid = self.place(c)
        helpers.set_config(nas_drop=False)
        self.assertEqual(c.post("/api/profile/nasablage", json={"nas": nid}).status_code, 403)
        self.assertIsNone(nasablage.offer(ctx(uid, "Leg das auf die NAS")))
        helpers.set_config(nas_drop=True)
        self.assertFalse(nasablage.allowed(None))                     # never guests
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = c.post("/api/profile/nasablage", json={"nas": nid})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["drop"]["nas"], nid)
        for d in ("spark_ablage/Erstellt", "spark_ablage/Eingang", "spark_ablage/Eingang/erledigt", "spark_ablage/Eingang/abgelehnt"):
            self.assertIn(d, NAS["dirs"])
        self.assertTrue(all(p.startswith("spark_ablage") for _, p in writes()), writes())
        self.assertEqual(NAS["files"], {"Dokumente/alt.txt": b"bleibt"})   # the probe is gone, nothing else touched
        self.assertIn("nasablage: eingerichtet | art=webdav", out.getvalue())
        self.assertNotIn("NaEin", out.getvalue())
        self.assertEqual(c.get("/api/profile/nas").json()["items"][0]["uses"], {"ablage": 1})
        self.assertEqual(c.delete(f"/api/profile/nas/{nid}").status_code, 409)   # a use still needs the place

    def test_missing_or_read_only_folder_says_how(self):
        c, uid = profile("NaFehlt")
        nid = self.place(c)
        NAS["dirs"].discard("spark_ablage")
        NAS["nomake"] = True
        r = c.post("/api/profile/nasablage", json={"nas": nid})
        self.assertEqual(r.status_code, 409)
        self.assertIn("spark_ablage", r.json()["detail"])
        NAS["nomake"] = False
        NAS["dirs"] = {"spark_ablage", "spark_ablage/Erstellt", "spark_ablage/Eingang", "spark_ablage/Eingang/erledigt",
                       "spark_ablage/Eingang/abgelehnt"}
        NAS["readonly"] = True
        r = c.post("/api/profile/nasablage", json={"nas": nid})
        self.assertEqual(r.status_code, 409)
        self.assertIn("schreiben", r.json()["detail"])
        self.assertIsNone(nasablage.get(uid))

    def test_only_in_the_home_network(self):
        c, uid = profile("NaNetz")
        nid = self.place(c)
        with mock.patch("nas.zone", return_value="net"):
            r = c.post("/api/profile/nasablage", json={"nas": nid})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(writes(), [])

    def test_blocked_keeps_remove(self):
        c, uid, nid = self.ready("NaSperre")
        helpers.set_config(deny={"nasablage": [uid]})
        self.assertEqual(c.post("/api/profile/nasablage/now").status_code, 403)
        self.assertIsNone(nasablage.offer(ctx(uid, "Leg das auf die NAS")))
        self.assertIsNotNone(c.get("/api/profile/nasablage").json()["drop"])
        self.assertIsNone(c.delete("/api/profile/nasablage").json()["drop"])
        self.assertEqual(writes(), [])


class Filing(Base):
    def test_proposal_then_yes_writes_only_into_erstellt_never_over_a_file(self):
        c, uid, nid = self.ready("NaJa")
        got = nasablage.offer(ctx(uid, "Speicher die Notiz auf der NAS"))
        self.assertEqual([t["function"]["name"] for t in got["tools"]], ["nas_ablegen"])
        self.assertIn("nas_ablegen", got["changes"])                   # locked after outside text
        self.assertIsNone(nasablage.offer(ctx(uid, "Wie wird das Wetter?")))
        r = asyncio.run(nasablage.tool("nas_ablegen", {"was": "notiz", "text": "Heizung prüfen lassen"}, ctx(uid)))
        self.assertTrue(r.startswith("NOT done yet"), r)
        self.assertEqual(writes(), [])                                  # nothing before the yes
        res = asyncio.run(extras.answer(ctx(uid), "Ja"))
        self.assertIn("Abgelegt", res["call"]["result"])
        made = [p for p in NAS["files"] if p.startswith("spark_ablage/Erstellt/")]
        self.assertEqual(len(made), 1)
        self.assertEqual(NAS["files"][made[0]], "Heizung prüfen lassen".encode())
        # a second note at the same minute gets " (2)": the first stays as it was
        with mock.patch("nasablage._carry_out", wraps=nasablage._carry_out):
            nasablage._pending[uid] = {"kind": "notiz", "ref": "", "label": "Notiz", "text": "zweite", "src": "web:c1", "t": 10**12}
            name = made[0].split("/")[-1]
            asyncio.run(nasablage.put(uid, name, b"zweite", "notiz"))
        self.assertEqual(NAS["files"][made[0]], "Heizung prüfen lassen".encode())
        self.assertIn("spark_ablage/Erstellt/" + name[:-4] + " (2).txt", NAS["files"])
        self.assertTrue(all(m != "DELETE" for m, _ in writes()), writes())
        self.assertTrue(all(p.startswith("spark_ablage/Erstellt/") for m, p in writes() if m == "PUT"))

    def test_no_or_another_conversation_files_nothing(self):
        c, uid, nid = self.ready("NaNein")
        asyncio.run(nasablage.tool("nas_ablegen", {"was": "notiz", "text": "geheim"}, ctx(uid)))
        res = asyncio.run(nasablage.answer(ctx(uid), "Nein danke"))
        self.assertIn("NICHT", res["system"])
        asyncio.run(nasablage.tool("nas_ablegen", {"was": "notiz", "text": "geheim"}, ctx(uid)))
        self.assertIsNone(asyncio.run(nasablage.answer(ctx(uid, src="telegram:x"), "Ja")))   # another device: not for it
        asyncio.run(nasablage.tool("nas_ablegen", {"was": "notiz", "text": "geheim"}, ctx(uid)))
        res = asyncio.run(nasablage.answer(ctx(uid), "Ja, und lies mir dann die Mails vor"))  # no plain yes
        self.assertIn("NICHT", res["system"])
        self.assertEqual([p for m, p in writes() if m == "PUT"], [])

    def test_notaus_holds_the_yes(self):
        c, uid, nid = self.ready("NaNotaus")
        asyncio.run(nasablage.tool("nas_ablegen", {"was": "notiz", "text": "x"}, ctx(uid)))
        with mock.patch("notaus.level", return_value=2):
            res = asyncio.run(nasablage.answer(ctx(uid), "Ja"))
        self.assertIn("NICHT abgelegt", res["call"]["result"])
        self.assertEqual([p for m, p in writes() if m == "PUT"], [])

    def test_made_document_goes_into_erstellt_unless_unticked(self):
        c, uid, nid = self.ready("NaAuto")
        d = {"id": "aaaaaaaaaaaa", "title": "Pool-Saison", "format": "docx"}
        with mock.patch("docmake.build", return_value=(b"PK-datei", "Pool-Saison.docx", "x")):
            said = asyncio.run(nasablage.after_made(uid, d))
            self.assertIn("Ablage-Ordner", said)
            self.assertEqual(NAS["files"]["spark_ablage/Erstellt/Pool-Saison.docx"], b"PK-datei")
            self.assertEqual(c.put("/api/profile/nasablage", json={"auto": False}).status_code, 200)
            self.assertEqual(asyncio.run(nasablage.after_made(uid, d)), "")
        self.assertEqual(nasablage.get(uid)["made"], 1)

    def test_a_made_document_by_tool(self):
        c, uid, nid = self.ready("NaDok")
        d = {"id": "bbbbbbbbbbbb", "title": "Brief an die Hausverwaltung", "format": "pdf"}
        with mock.patch("docmake.find", return_value=d), mock.patch("docmake.load", return_value=d), \
                mock.patch("docmake.build", return_value=(b"%PDF-1.4", "Brief an die Hausverwaltung.pdf", "x")):
            r = asyncio.run(nasablage.tool("nas_ablegen", {"was": "dokument", "name": "Brief"}, ctx(uid)))
            self.assertIn("Brief an die Hausverwaltung", r)
            asyncio.run(nasablage.answer(ctx(uid), "Ja bitte"))
        self.assertIn("spark_ablage/Erstellt/Brief an die Hausverwaltung.pdf", NAS["files"])


class Inbox(Base):
    def test_takes_in_like_an_upload_and_moves_never_deletes(self):
        c, uid, nid = self.ready("NaEingang")
        NAS["files"].update({"spark_ablage/Eingang/Heizung.docx": docx("Die Heizung im Keller wird im Mai gewartet."),
                             "spark_ablage/Eingang/kaputt.pdf": b"kein pdf, nur Text",
                             "spark_ablage/Eingang/programm.exe": b"MZ...."})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = c.post("/api/profile/nasablage/now")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["fetched"], r.json()["refused"]), (1, 2))
        docs = [x for x in documents.list_docs(uid) if x["source"] == "eingang"]
        self.assertEqual([x["name"] for x in docs], ["Heizung.docx"])
        self.assertIn("spark_ablage/Eingang/erledigt/Heizung.docx", NAS["files"])
        self.assertIn("spark_ablage/Eingang/abgelehnt/kaputt.pdf", NAS["files"])
        self.assertIn("spark_ablage/Eingang/abgelehnt/programm.exe", NAS["files"])
        self.assertFalse([p for p in NAS["files"] if p.startswith("spark_ablage/Eingang/") and p.count("/") == 2])
        self.assertTrue(all(m in ("MOVE",) for m, _ in writes()), writes())   # only moved, nothing written or deleted
        log = out.getvalue()
        self.assertIn("nasablage: eingang | 1 geholt | 2 abgelehnt | 0 übrig", log)
        for word in ("Heizung", "kaputt", "NaEingang", uid, "spark_ablage"):
            self.assertNotIn(word, log)
        # a second round finds nothing new; a file of the same name later gets " (2)" in erledigt
        NAS["files"]["spark_ablage/Eingang/Heizung.docx"] = docx("Neue Wartung im Juni.")
        self.assertEqual(c.post("/api/profile/nasablage/now").json()["fetched"], 1)
        self.assertIn("spark_ablage/Eingang/erledigt/Heizung (2).docx", NAS["files"])
        self.assertEqual(NAS["files"]["Dokumente/alt.txt"], b"bleibt")

    def test_unticked_or_off_takes_nothing(self):
        c, uid, nid = self.ready("NaAus")
        NAS["files"]["spark_ablage/Eingang/a.txt"] = b"Hallo"
        c.put("/api/profile/nasablage", json={"inbox": False})
        self.assertFalse(nasablage.due(uid, nasablage.get(uid)))
        c.put("/api/profile/nasablage", json={"inbox": True})
        self.assertTrue(nasablage.due(uid, nasablage.get(uid)))
        helpers.set_config(documents=False)                         # where it would go is off: nothing taken, no failure
        try:
            self.assertFalse(nasablage.due(uid, nasablage.get(uid)))
            self.assertEqual(c.post("/api/profile/nasablage/now").status_code, 409)
            self.assertIsNone(nasablage.get(uid)["fail"])
        finally:
            helpers.set_config(documents=True)
        helpers.set_config(nas_drop=False)
        self.assertEqual(asyncio.run(nasablage.round_once(now=10**10)), [])
        self.assertIn("spark_ablage/Eingang/a.txt", NAS["files"])

    def test_live_and_wächter_numbers_only(self):
        c, uid, nid = self.ready("NaLive")
        live = nasablage.for_live()
        self.assertTrue(live["on"])
        self.assertGreaterEqual(live["profiles"], 1)
        self.assertTrue(all(isinstance(v, (int, bool)) for v in live.values()))
        self.assertTrue(any(uid in p["uids"] for p in nasablage.probes().values()))


class Static(unittest.TestCase):
    def test_page_and_guide(self):
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "static")
        with open(os.path.join(here, "index.html")) as f:
            html = f.read()
        self.assertIn("/static/js/nasablage.js", html)
        self.assertIn('id="chat.nas_drop"', html)
        with open(os.path.join(here, "js", "guides.js")) as f:
            self.assertIn("{id:'nasablage',", f.read())
        with open(os.path.join(here, "js", "nasablage.js")) as f:
            js = f.read()
        self.assertNotRegex(js, r"\bon(click|change)=\"")
        self.assertNotRegex(js, r"\$\{x\.(name|url|path)\}")


if __name__ == "__main__":
    unittest.main()
