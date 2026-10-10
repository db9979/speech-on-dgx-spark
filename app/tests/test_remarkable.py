"""reMarkable notebooks as knowledge (remarkable.py), V01.0.270.

Against a fake reMarkable cloud in memory (the real hosts are fixed and public, so the requests are
answered by replacing remarkable._request): pairing with a one-time code seals the device token, only
picked notebooks are read, typed text comes at once, handwriting waits for the language model like a
scan, an unchanged page is never fetched again, notebooks gone from the cloud or no longer picked
disappear, writing only adds a new EPUB in the folder "Spark". Off without both switches, never guests;
the note tool only when the person's own words name the reMarkable, and it is locked after outside text.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import asyncio
import datetime
import hashlib
import io
import json
import os
import unittest
import uuid
import zipfile

import httpx

from tests import helpers

helpers.start()
import panel  # noqa: E402
import documents  # noqa: E402
import extras  # noqa: E402
import guard  # noqa: E402
import profiles  # noqa: E402
import remarkable  # noqa: E402
import wissen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
DEVICE_TOKEN = "dev." + "D" * 60
USER_TOKEN = "usr." + "U" * 60
try:
    from rmscene import scene_items as si
    from rmscene import scene_stream as ss
    from rmscene.crdt_sequence import CrdtSequenceItem
    from rmscene.tagged_block_common import CrdtId
except ImportError:      # the self-test on an older install: page files are then given as already parsed
    si = None


def run(c):
    return asyncio.run(c)


def page_file(text="", strokes=0):
    """A v6 page file with typed text and some strokes."""
    if si is None:
        return json.dumps({"text": text, "strokes": strokes}).encode()
    blocks = list(ss.simple_text_document(text or " "))
    for n in range(strokes):
        line = si.Line(color=si.PenColor.BLACK, tool=si.Pen.BALLPOINT_1, thickness_scale=1.0, starting_length=0.0,
                       points=[si.Point(x=float(i * 6), y=200.0 + 40 * n + (i % 5), speed=1, direction=1, width=3, pressure=90)
                               for i in range(30)])
        blocks.append(ss.SceneLineItemBlock(parent_id=CrdtId(0, 11), item=CrdtSequenceItem(
            item_id=CrdtId(1, 30 + n), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=line)))
    b = io.BytesIO()
    ss.write_blocks(b, blocks, options={"version": "3.1"})
    return b.getvalue()


class Cloud:
    """A reMarkable cloud: content-addressed files, a root index with a generation."""
    def __init__(self):
        self.files, self.gen, self.calls, self.codes = {}, 1, [], {"abcdefgh"}
        self.upload_answer, self.root_answer = 200, 200     # what writes are answered with (errors, 202 ...)
        self.entries = {}          # id -> (hash, subfiles, size)
        self.root = self.put(b"4\n0:.:0:0\n")
        self.commit()

    def put(self, data):
        h = hashlib.sha256(data).hexdigest()
        self.files[h] = data
        return h

    def commit(self):
        lines = "".join(f"{h}:0:{i}:{n}:{s}\n" for i, (h, n, s) in sorted(self.entries.items()))
        self.root = self.put(f"4\n0:.:{len(self.entries)}:0\n{lines}".encode())

    def doc(self, did, name, pages=(), parent="", folder=False, kind="notebook", deleted=False, times=None):
        """pages: [(page id, page file)]; times: {page id: when it changed (ms)} as newer software writes it."""
        meta = {"visibleName": name, "parent": parent, "type": "CollectionType" if folder else "DocumentType",
                "deleted": deleted, "lastModified": "1760000000000"}
        files = [(did + ".metadata", json.dumps(meta).encode())]
        if not folder:
            content = {"fileType": kind, "formatVersion": 2,
                       "cPages": {"pages": [dict({"id": p, "idx": {"value": f"b{i:03d}"}},
                                                 **({"modifed": {"timestamp": "1:2", "value": str(times[p])}} if p in (times or {}) else {}))
                                            for i, (p, _) in enumerate(pages)]}}
            files.append((did + ".content", json.dumps(content).encode()))
            files += [(f"{did}/{p}.rm", data) for p, data in pages if data is not None]
        rows = sorted((self.put(data), fid, len(data)) for fid, data in files)
        rows.sort(key=lambda r: r[1])
        index = "3\n" + "".join(f"{h}:0:{fid}:0:{s}\n" for h, fid, s in rows)
        dh = hashlib.sha256(b"".join(bytes.fromhex(h) for h, _, _ in rows)).hexdigest()
        self.files[dh] = index.encode()
        self.entries[did] = (dh, len(rows), sum(s for _, _, s in rows))
        self.commit()

    def drop(self, did):
        self.entries.pop(did, None)
        self.commit()

    def listed(self):
        """{id: name} of what the root index holds now (read like a device would)."""
        out = {}
        for e in remarkable.parse_index(self.files[self.root]):
            for f in remarkable.parse_index(self.files[e["hash"]]):
                if f["id"].endswith(".metadata"):
                    out[e["id"]] = json.loads(self.files[f["hash"]])
        return out

    async def request(self, method, url, token="", most=remarkable.MAX_INDEX, headers=None, **kw):
        self.calls.append((method, url.split("/sync/")[-1] if "/sync/" in url else url, (headers or {}).get("rm-filename", "")))
        if not remarkable.host_ok(url):
            raise remarkable.CloudError("host not allowed")
        if url == remarkable.DEVICE_URL:
            code = kw["json"]["code"]
            if code in self.codes:
                self.codes.discard(code)
                return httpx.Response(200, text=DEVICE_TOKEN)
            return httpx.Response(400, text="bad code")
        if url == remarkable.USER_URL:
            return httpx.Response(200 if token == DEVICE_TOKEN else 401, text=USER_TOKEN)
        if token != USER_TOKEN:
            return httpx.Response(401)
        if url == remarkable.ROOT_URL:
            return httpx.Response(200, json={"hash": self.root, "generation": self.gen, "schemaVersion": 4})
        if url.startswith(remarkable.FILES_URL):
            h = url[len(remarkable.FILES_URL):]
            if method == "GET":
                if h not in self.files:
                    return httpx.Response(404)
                if len(self.files[h]) > most:
                    raise remarkable.netguard.TooLarge("too big")
                return httpx.Response(200, content=self.files[h])
            data = kw["content"]
            if headers.get("rm-filename", "").endswith(".docSchema") and headers["rm-filename"] != "root.docSchema":   # a document index: the hash of its entries
                rows = remarkable.parse_index(data)
                assert hashlib.sha256(b"".join(bytes.fromhex(e["hash"]) for e in rows)).hexdigest() == h
            else:
                assert hashlib.sha256(data).hexdigest() == h
            assert headers.get("x-goog-hash", "").startswith("crc32c=")
            if self.upload_answer >= 300:
                return httpx.Response(self.upload_answer, text="Bad Request: x-goog-hash mismatch for " + USER_TOKEN)
            self.files[h] = data
            return httpx.Response(self.upload_answer)
        if url == remarkable.ROOT_PUT_URL and method == "PUT":
            body = kw["json"]
            if body["generation"] != self.gen:
                return httpx.Response(412)
            self.gen += 1
            self.root = body["hash"]
            self.entries = {e["id"]: (e["hash"], e["subfiles"], e["size"]) for e in remarkable.parse_index(self.files[self.root])}
            return httpx.Response(self.root_answer, json={"hash": self.root, "generation": self.gen})
        return httpx.Response(404)


CLOUD = [None]
REAL_REQUEST = remarkable._request


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


P1, P2, P3 = (str(uuid.UUID(int=i)) for i in (1, 2, 3))
NB, NB2, PDF, FOLDER = (str(uuid.UUID(int=i)) for i in (101, 102, 103, 104))


class Base(unittest.TestCase):
    def setUp(self):
        CLOUD[0] = Cloud()
        remarkable._request = CLOUD[0].request
        remarkable._user.clear()
        remarkable._auto_last.clear()
        remarkable._peek_last.clear()
        remarkable.BACKGROUND = False
        if si is None:
            remarkable.parse_page = lambda data, draw=True: (json.loads(data)["text"], [], b"jpeg" if draw and json.loads(data)["strokes"] else None,
                                                              bool(json.loads(data)["strokes"]))
        helpers.set_config(documents=True, doc_pictures=True, remarkable=True, remarkable_send=False)
        for k in [k for k in guard._rate if k[0].startswith("rm")]:
            guard._rate.pop(k, None)

    def tearDown(self):
        remarkable._request = REAL_REQUEST
        helpers.set_config(doc_pictures=False, remarkable=False, remarkable_send=False, remarkable_fresh=False)

    def ready(self, name, pictures=True):
        c = profile(name)
        r = c.put("/api/profile/settings", json={"rm_on": True, "doc_pictures": pictures})
        self.assertEqual(r.status_code, 200, r.text)
        return c, uid_of(name)

    def paired(self, name, pictures=True):
        c, uid = self.ready(name, pictures)
        r = c.post("/api/profile/remarkable/pair", json={"code": "abcdefgh"})
        self.assertEqual(r.status_code, 200, r.text)
        run(remarkable.refresh_library(uid))        # after pairing it runs in the background
        self.assertEqual(c.get("/api/profile/remarkable").json()["progress"], [])  # loading counter gone
        return c, uid

    def docs(self, uid):
        return [d for d in documents.list_docs(uid) if d["source"] == "remarkable"]


class Switches(Base):
    def test_off_by_default_both_switches_needed_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["remarkable"], False)
        self.assertIs(ch["remarkable_send"], False)
        self.assertIs(profiles.SETTINGS["rm_on"][0], False)
        self.assertIs(profiles.SETTINGS["rm_send"][0], False)
        c = profile("Rmoff")
        self.assertEqual(c.get("/api/profile/remarkable").status_code, 403)        # profile switch off
        c.put("/api/profile/settings", json={"rm_on": True})
        self.assertEqual(c.get("/api/profile/remarkable").status_code, 200)
        helpers.set_config(remarkable=False)
        self.assertEqual(c.get("/api/profile/remarkable").status_code, 403)        # admin switch off
        helpers.set_config(remarkable=True, doc_pictures=False)
        self.assertEqual(c.get("/api/profile/remarkable").status_code, 403)        # builds on "Bilder und Scans lesen"
        helpers.set_config(doc_pictures=True)
        g = TestClient(panel.app)
        for method, path in (("get", "/api/profile/remarkable"), ("post", "/api/profile/remarkable/pair"),
                             ("put", "/api/profile/remarkable/pick"), ("post", "/api/profile/remarkable/sync"),
                             ("post", "/api/profile/remarkable/send"), ("delete", "/api/profile/remarkable")):
            r = getattr(g, method)(path, **({"json": {}} if method in ("post", "put") else {}))
            self.assertIn(r.status_code, (401, 403), path)
        self.assertFalse(remarkable.allowed(""))

    def test_device_keys_cannot_manage_it(self):
        c, uid = self.ready("Rmkey")
        key = ADMIN.post("/api/admin/devices", json={"name": "Kurzbefehl", "user": uid}).json()["token"]
        dev = TestClient(panel.app, headers={profiles.DEVICE_HEADER: key})
        self.assertEqual(dev.get("/api/profile/remarkable").status_code, 403)
        self.assertEqual(dev.post("/api/profile/remarkable/pair", json={"code": "abcdefgh"}).status_code, 403)
        self.assertEqual(dev.post("/api/profile/remarkable/send", json={"title": "x", "text": "y"}).status_code, 403)


class Pairing(Base):
    def test_code_checked_token_sealed_never_shown(self):
        c, uid = self.ready("Rmpair")
        self.assertEqual(c.post("/api/profile/remarkable/pair", json={"code": "abc"}).status_code, 400)
        self.assertEqual(c.post("/api/profile/remarkable/pair", json={"code": "zzzzzzzz"}).status_code, 400)
        r = c.post("/api/profile/remarkable/pair", json={"code": "ABCDEFGH "})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["connected"])
        with open(remarkable._file(uid)) as f:
            raw = f.read()
        self.assertNotIn(DEVICE_TOKEN, raw)
        self.assertIn("enc1:", raw)
        self.assertEqual(remarkable.device_token(uid), DEVICE_TOKEN)
        self.assertNotIn(DEVICE_TOKEN, c.get("/api/profile/remarkable").text)
        self.assertNotIn(USER_TOKEN, json.dumps(remarkable.load(uid)))
        self.assertEqual(remarkable._redact("401 for " + DEVICE_TOKEN), "401 for …")

    def test_unpair_removes_everything_on_the_spark(self):
        c, uid = self.paired("Rmgone")
        CLOUD[0].doc(NB, "Projekt", [(P1, page_file("Notiz eins"))])
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        run(remarkable.sync(uid))
        self.assertEqual(len(self.docs(uid)), 1)
        r = c.delete("/api/profile/remarkable")
        self.assertEqual(r.status_code, 200)
        self.assertIn("my.remarkable.com", r.json()["hint"])
        self.assertEqual(self.docs(uid), [])
        self.assertFalse(os.path.exists(remarkable._file(uid)))
        self.assertIn(NB, CLOUD[0].entries)                          # the cloud is never touched


class Reading(Base):
    def test_only_picked_typed_text_at_once_handwriting_for_the_model(self):
        c, uid = self.paired("Rmread")
        CLOUD[0].doc(FOLDER, "Arbeit", folder=True)
        CLOUD[0].doc(NB, "Meeting Müller", [(P1, page_file("Budget 2027 freigeben")), (P2, page_file("", strokes=3)),
                                            (P3, None)], parent=FOLDER)
        CLOUD[0].doc(NB2, "Privat", [(P1, page_file("Tagebuch geheim"))])
        CLOUD[0].doc(PDF, "Handbuch", [(P1, page_file("Randnotiz"))], kind="pdf")
        run(remarkable.sync(uid))
        self.assertEqual(self.docs(uid), [])                          # nothing picked: nothing read
        lib = {x["name"]: x for x in c.get("/api/profile/remarkable").json()["library"]}
        self.assertEqual(lib["Meeting Müller"]["path"], "Arbeit/Meeting Müller")
        self.assertEqual(lib["Meeting Müller"]["pages"], 3)
        r = c.put("/api/profile/remarkable/pick", json={"ids": [FOLDER], "all": False})
        self.assertEqual(r.status_code, 200)
        self.assertTrue({x["name"]: x for x in r.json()["library"]}["Meeting Müller"]["read"])
        res = run(remarkable.sync(uid))
        self.assertEqual(res["docs"], 1)
        d = self.docs(uid)
        self.assertEqual([x["name"] for x in d], ["Arbeit/Meeting Müller"])
        self.assertEqual((d[0]["kind"], d[0]["state"], d[0]["todo"]), ("notebook", "reading", 1))
        hits = documents.search(uid, "Budget freigeben")
        self.assertTrue(hits and hits[0]["source"] == "remarkable")
        self.assertTrue(wissen.where(hits[0]).startswith("reMarkable: Arbeit/Meeting Müller, Seite 1"))
        self.assertEqual(documents.search(uid, "Tagebuch geheim"), [])
        real = wissen.read_page

        async def read(jpeg):
            return "Handschrift: Angebot bis Freitag an Müller schicken"
        wissen.read_page = read
        try:
            for _ in range(5):
                if run(wissen.due_once(idle=True)) != "page":
                    break
        finally:
            wissen.read_page = real
        hits = documents.search(uid, "Angebot Freitag")
        self.assertTrue(hits and hits[0]["page"] == 2, hits)
        self.assertEqual(self.docs(uid)[0]["state"], "ready")
        # "all": every notebook, never PDFs or books
        c.put("/api/profile/remarkable/pick", json={"ids": [], "all": True})
        run(remarkable.sync(uid))
        self.assertEqual(sorted(x["name"] for x in self.docs(uid)), ["Arbeit/Meeting Müller", "Privat"])

    def test_unchanged_pages_are_not_fetched_again_changes_and_removals_follow(self):
        c, uid = self.paired("Rmdelta")
        first = page_file("Brenner 2019 eingebaut")
        CLOUD[0].doc(NB, "Heizung", [(P1, first), (P2, page_file("Wartung im Mai"))])
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        run(remarkable.sync(uid))
        doc = self.docs(uid)[0]["id"]
        CLOUD[0].calls.clear()
        self.assertEqual(run(remarkable.sync(uid))["docs"], 0)       # nothing changed: no page fetched
        self.assertFalse([x for x in CLOUD[0].calls if x[2].endswith(".rm")])
        CLOUD[0].doc(NB, "Heizung", [(P1, first), (P2, page_file("Wartung im Juni"))])
        CLOUD[0].calls.clear()
        res = run(remarkable.sync(uid))
        self.assertEqual((res["docs"], res["pages"]), (1, 1))      # only the changed page
        self.assertEqual([x[2] for x in CLOUD[0].calls if x[2].endswith(".rm")], [f"{NB}/{P2}.rm"])
        self.assertEqual(self.docs(uid)[0]["id"], doc)               # same document, same place
        self.assertTrue(documents.search(uid, "Brenner eingebaut"))
        self.assertTrue(documents.search(uid, "Wartung Juni"))
        self.assertFalse(documents.search(uid, "Mai"))
        CLOUD[0].drop(NB)                                            # deleted on the reMarkable
        self.assertEqual(run(remarkable.sync(uid))["removed"], 1)
        self.assertEqual(self.docs(uid), [])

    def test_deleted_under_documents_stays_away(self):
        c, uid = self.paired("Rmskip")
        CLOUD[0].doc(NB, "Einkauf", [(P1, page_file("Milch"))])
        c.put("/api/profile/remarkable/pick", json={"ids": [], "all": True})
        run(remarkable.sync(uid))
        documents.delete(uid, self.docs(uid)[0]["id"])
        run(remarkable.sync(uid))
        self.assertEqual(self.docs(uid), [])                          # not brought back
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": True})
        run(remarkable.sync(uid))
        self.assertEqual(len(self.docs(uid)), 1)                      # picked again on purpose

    def test_handwriting_waits_while_pictures_are_off(self):
        c, uid = self.paired("Rmnopic", pictures=False)
        CLOUD[0].doc(NB, "Skizzen", [(P1, page_file("Titel", strokes=2))])
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        run(remarkable.sync(uid))
        d = self.docs(uid)[0]
        self.assertEqual((d["state"], d["todo"]), ("ready", 0))
        self.assertIn("Handschrift nicht gelesen", d["note"])
        c.put("/api/profile/settings", json={"doc_pictures": True})
        run(remarkable.sync(uid))
        self.assertEqual(self.docs(uid)[0]["todo"], 1)               # now it waits for the model

    def test_background_only_when_quiet_and_due(self):
        c, uid = self.paired("Rmbg")
        CLOUD[0].doc(NB, "Ideen", [(P1, page_file("Gartenhaus planen"))])
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        self.assertIsNone(run(remarkable.due_once(idle=False)))
        for other in profiles.user_ids():          # other tests' profiles are not due
            if other != uid:
                remarkable._auto_last[other] = remarkable._peek_last[other] = 1e12
        self.assertEqual(run(remarkable.due_once(idle=True)), uid)
        self.assertEqual(len(self.docs(uid)), 1)
        self.assertIsNone(run(remarkable.due_once(idle=True)))       # not due again yet


class Writing(Base):
    def test_send_only_adds_an_epub_in_the_spark_folder(self):
        c, uid = self.paired("Rmsend")
        CLOUD[0].doc(NB, "Alt", [(P1, page_file("bleibt"))])
        before = dict(CLOUD[0].entries)
        self.assertEqual(c.post("/api/profile/remarkable/send", json={"title": "x", "text": "y"}).status_code, 403)
        helpers.set_config(remarkable_send=True)
        self.assertEqual(c.post("/api/profile/remarkable/send", json={"title": "x", "text": "y"}).status_code, 403)
        c.put("/api/profile/settings", json={"rm_send": True})
        r = c.post("/api/profile/remarkable/send", json={"title": "Rezept <Brot>", "text": "Mehl\n\nWasser & Salz"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["title"], "Rezept Brot")
        for k, v in before.items():
            self.assertEqual(CLOUD[0].entries[k], v)                 # nothing existing changed
        listed = CLOUD[0].listed()
        folders = [i for i, m in listed.items() if m["type"] == "CollectionType" and m["visibleName"] == "Spark"]
        self.assertEqual(len(folders), 1)
        sent = [m for m in listed.values() if m["visibleName"] == "Rezept Brot"]
        self.assertEqual(sent[0]["parent"], folders[0])
        book = next(d for h, d in CLOUD[0].files.items() if d[:2] == b"PK")
        with zipfile.ZipFile(io.BytesIO(book)) as z:
            self.assertEqual(z.read("mimetype"), b"application/epub+zip")
            self.assertIn("Wasser &amp; Salz", z.read("text.xhtml").decode())
        c.post("/api/profile/remarkable/send", json={"title": "Zwei", "text": "noch eins"})
        listed = CLOUD[0].listed()
        self.assertEqual(len([m for m in listed.values() if m["visibleName"] == "Spark"]), 1)   # folder reused
        d = remarkable.load(uid)
        d["sent"] = {"day": __import__("time").strftime("%Y-%m-%d"), "n": remarkable.SEND_DAY}
        remarkable.save(uid, d)
        self.assertEqual(c.post("/api/profile/remarkable/send", json={"title": "x", "text": "y"}).status_code, 400)

    def test_note_tool_only_on_own_words_and_locked_after_outside_text(self):
        c, uid = self.paired("Rmtool")
        helpers.set_config(remarkable_send=True)
        c.put("/api/profile/settings", json={"rm_send": True})
        who = {"id": uid, "name": "Rmtool"}
        self.assertIsNone(remarkable.offer({"who": who, "own": True, "text": "Wie wird das Wetter?"}))
        self.assertIsNone(remarkable.offer({"who": who, "own": False, "text": "Schreib aufs reMarkable: Milch"}))
        self.assertIsNone(remarkable.offer({"who": None, "own": True, "text": "Schreib aufs reMarkable: Milch"}))
        self.assertIsNone(remarkable.offer({"who": who, "own": True, "private": False, "text": "Schreib aufs reMarkable: Milch"}))
        o = remarkable.offer({"who": who, "own": True, "text": "Schreib aufs reMarkable: Milch"})
        self.assertEqual([t["function"]["name"] for t in o["tools"]], ["remarkable_note"])
        self.assertIn("remarkable_note", o["changes"])                # locked after web pages, mails, documents
        ex = extras.offer({"who": who, "own": True, "text": "Schreib aufs Remarkable: Milch"})
        self.assertIs(ex["run"]["remarkable_note"], remarkable)
        self.assertIn("remarkable_note", ex["changes"])
        out = run(remarkable.tool("remarkable_note", {"title": "Einkauf", "text": "Milch, Brot"}, {"who": who}))
        self.assertIn("Einkauf", out)


class Target(Base):
    """V01.0.291: "Ablegen in" picks one own folder for new documents (default "Spark"); only new documents go
    there, a folder that is gone means "Spark" again and the person is told."""
    def test_chosen_folder_and_fallback(self):
        c, uid = self.paired("Rmtarget")
        CLOUD[0].doc(FOLDER, "Notizen", folder=True)
        CLOUD[0].doc(NB, "Alt", [(P1, page_file("bleibt"))], parent=FOLDER)
        run(remarkable.refresh_library(uid))
        self.assertEqual(c.put("/api/profile/remarkable/target", json={"id": FOLDER}).status_code, 403)   # sending off
        helpers.set_config(remarkable_send=True)
        c.put("/api/profile/settings", json={"rm_send": True})
        self.assertEqual(c.get("/api/profile/remarkable").json()["target_path"], "Spark")
        for bad in (NB, str(uuid.UUID(int=999)), "../x", 5):      # a notebook, unknown, no id
            self.assertEqual(c.put("/api/profile/remarkable/target", json={"id": bad}).status_code, 400, bad)
        r = c.put("/api/profile/remarkable/target", json={"id": FOLDER})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["target_path"], "Notizen")
        before = dict(CLOUD[0].entries)
        r = c.post("/api/profile/remarkable/send", json={"title": "Hier", "text": "y"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["where"], r.json()["lost"]), ("Notizen", False))
        for k, v in before.items():
            self.assertEqual(CLOUD[0].entries[k], v)                 # nothing existing changed, the folder neither
        listed = CLOUD[0].listed()
        self.assertEqual(next(m for m in listed.values() if m["visibleName"] == "Hier")["parent"], FOLDER)
        self.assertNotIn("Spark", [m["visibleName"] for m in listed.values()])   # no Spark folder needed
        CLOUD[0].drop(FOLDER)                                          # deleted on the device
        r = c.post("/api/profile/remarkable/send", json={"title": "Danach", "text": "y"})
        self.assertEqual((r.json()["where"], r.json()["lost"]), ("Spark", True))
        listed = CLOUD[0].listed()
        spark = next(i for i, m in listed.items() if m["visibleName"] == "Spark")
        self.assertEqual(next(m for m in listed.values() if m["visibleName"] == "Danach")["parent"], spark)
        self.assertNotIn("target", remarkable.load(uid))
        ok, note = run(remarkable.send_answer(uid, "Fass zusammen", "Text"))
        self.assertIn("„Spark“", note)
        self.assertNotIn("nicht mehr da", note)                         # told once, then Spark is the choice

class SendErrors(Base):
    """V01.0.290: a refused upload says which file and what the cloud answered (never a token), any 2xx counts,
    and a root line the Spark does not understand stops the write before anything could vanish."""
    def ready_send(self, name):
        c, uid = self.paired(name)
        helpers.set_config(remarkable_send=True)
        c.put("/api/profile/settings", json={"rm_send": True})
        return c, uid

    def test_refused_upload_is_explained(self):
        c, uid = self.ready_send("Rmerr")
        CLOUD[0].upload_answer = 400
        r = c.post("/api/profile/remarkable/send", json={"title": "x", "text": "y"})
        self.assertEqual(r.status_code, 502)
        msg = r.json()["detail"]
        self.assertIn("HTTP 400", msg)
        self.assertIn("x-goog-hash mismatch", msg)
        self.assertNotIn(USER_TOKEN, msg)
        ok, note = run(remarkable.send_answer(uid, "Fass zusammen", "Text"))
        self.assertFalse(ok)
        self.assertIn("HTTP 400", note)

    def test_accepted_counts(self):
        c, uid = self.ready_send("Rm202")
        CLOUD[0].upload_answer, CLOUD[0].root_answer = 201, 202
        r = c.post("/api/profile/remarkable/send", json={"title": "Zwei", "text": "y"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("Zwei", [m["visibleName"] for m in CLOUD[0].listed().values()])

    def test_unknown_root_line_writes_nothing(self):
        c, uid = self.ready_send("Rmodd")
        CLOUD[0].doc(NB, "Bleibt", [(P1, page_file("x"))])
        body = CLOUD[0].files[CLOUD[0].root] + b"zzz:0:seltsam:0:1\n"
        CLOUD[0].root = CLOUD[0].put(body)
        before = (CLOUD[0].root, CLOUD[0].gen)
        r = c.post("/api/profile/remarkable/send", json={"title": "x", "text": "y"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("nothing written", r.json()["detail"])
        self.assertEqual((CLOUD[0].root, CLOUD[0].gen), before)          # the account stays as it was

class AnswerToRemarkable(Base):
    """V01.0.279: "... und leg es aufs reMarkable" puts the whole answer there, by a fixed panel rule on the
    person's own words (the tool was cut by the switch and locked after the web search)."""
    ASK = "Fass die politische Lage zusammen und leg es auf dem reMarkable ab"

    def test_rule_on_own_words(self):
        for text in (self.ASK, "Such nach dem Wetter und schick mir das aufs reMarkable",
                     "Speichere die Zusammenfassung auf meinem reMarkable", "Fasse die Nachrichten zusammen und schreib es aufs Remarkable",
                     "Summarize the news and put it on my reMarkable"):
            self.assertTrue(remarkable.answer_wanted(text), text)
        for text in ("Schreib aufs reMarkable: Milch kaufen", "Was steht auf meinem reMarkable?",
                     "Notier auf dem reMarkable Brot", "Wie funktioniert ein reMarkable?", "Leg das Licht aufs Sofa", ""):
            self.assertFalse(remarkable.answer_wanted(text), text)
        self.assertEqual(remarkable.answer_title(self.ASK), "Fass die politische Lage zusammen")

    def test_panel_sends_the_answer_never_the_model(self):
        c, uid = self.paired("Rmanswer")
        helpers.set_config(remarkable_send=True)
        helpers.LLM_CALLS.clear()
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": self.ASK}], "convo": "neu"})
        said = "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
        self.assertNotIn("liegt jetzt", said)                                  # profile switch rm_send off: nothing
        self.assertNotIn(remarkable.ANSWER_HINT, json.dumps(helpers.LLM_CALLS, ensure_ascii=False))
        c.put("/api/profile/settings", json={"rm_send": True})
        helpers.LLM_CALLS.clear()
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": self.ASK}], "convo": "neu"})
        said = "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
        self.assertIn("liegt jetzt auf deinem reMarkable", said)
        call = helpers.LLM_CALLS[0]
        self.assertIn(remarkable.ANSWER_HINT, call["messages"][0]["content"])
        self.assertNotIn("remarkable_note", [t["function"]["name"] for t in call.get("tools") or []])
        sent = [m for m in CLOUD[0].listed().values() if m["visibleName"] == "Fass die politische Lage zusammen"]
        self.assertEqual(len(sent), 1)
        book = next(d for h, d in CLOUD[0].files.items() if d[:2] == b"PK")
        with zipfile.ZipFile(io.BytesIO(book)) as z:
            self.assertIn("Hallo.", z.read("text.xhtml").decode())             # the answer itself
        self.assertIsNone(remarkable.offer({"who": {"id": uid}, "own": True, "text": self.ASK}))   # no tool as well
        # a guest never: the same words send nothing
        before = len(CLOUD[0].files)
        g = TestClient(panel.app)
        g.post("/api/chat", json={"messages": [{"role": "user", "content": self.ASK}], "convo": "neu"})
        self.assertEqual(len(CLOUD[0].files), before)

    def test_failure_is_said(self):
        c, uid = self.paired("Rmanswerfail")
        helpers.set_config(remarkable_send=True)
        c.put("/api/profile/settings", json={"rm_send": True})
        d = remarkable.load(uid)
        d["sent"] = {"day": __import__("time").strftime("%Y-%m-%d"), "n": remarkable.SEND_DAY}
        remarkable.save(uid, d)
        ok, note = run(remarkable.send_answer(uid, self.ASK, "Text"))
        self.assertFalse(ok)
        self.assertIn("ging es nicht", note)


class Fresh(Base):
    """V01.0.299 "Neueste zuerst": newer notes count a little more, "Was habe ich zuletzt notiert?" lists the
    newest pages, and a quick look at the account's root every few minutes brings new notes in soon."""
    DAY = 86400
    NOW = 1_760_000_000          # fixed: no test depends on the clock

    def fresh(self, name):
        c, uid = self.paired(name)
        helpers.set_config(remarkable_fresh=True)
        self.assertEqual(c.put("/api/profile/settings", json={"rm_fresh": True}).status_code, 200)
        return c, uid

    def test_off_by_default_both_switches_never_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["remarkable_fresh"], False)
        self.assertIs(profiles.SETTINGS["rm_fresh"][0], False)
        c, uid = self.paired("Rmfreshoff")
        self.assertFalse(wissen.fresh_on(uid))
        helpers.set_config(remarkable_fresh=True)
        self.assertFalse(wissen.fresh_on(uid))                               # profile switch still off
        c.put("/api/profile/settings", json={"rm_fresh": True})
        self.assertTrue(wissen.fresh_on(uid))
        helpers.set_config(remarkable=False)
        self.assertFalse(wissen.fresh_on(uid))                               # sits under "reMarkable-Notizen"
        helpers.set_config(remarkable=True, remarkable_fresh=False)
        self.assertFalse(wissen.fresh_on(uid))
        self.assertFalse(wissen.fresh_on(""))                                # a guest never
        self.assertEqual(TestClient(panel.app).put("/api/profile/settings", json={"rm_fresh": True}).status_code, 401)

    def test_page_times_from_the_content(self):
        content = {"cPages": {"pages": [{"id": "a", "modifed": {"timestamp": "1:2", "value": "1760000000000"}},
                                        {"id": "b", "modified": "1760000500000"}, {"id": "c", "modifed": "x"},
                                        {"id": "d", "modifed": "5"}, {"id": "e"}, "f", {"id": 7, "modifed": "1760000000000"}]}}
        self.assertEqual(remarkable.page_times(content), {"a": 1760000000, "b": 1760000500})
        self.assertEqual(remarkable.page_times({}), {})
        self.assertEqual(remarkable.page_times({"cPages": []}), {})

    def test_newer_note_gains_a_little_old_good_fit_stays(self):
        c, uid = self.fresh("Rmfreshrank")
        old, _ = documents.notebook_put(uid, None, "Alt", [(1, "Heizung Wartung Termin beim Installateur", None)],
                                        changed=self.NOW - 400 * self.DAY)
        new, _ = documents.notebook_put(uid, None, "Neu", [(1, "Heizung Wartung Termin beim Installateur", None, self.NOW - self.DAY)],
                                        changed=self.NOW - 30 * self.DAY)
        plain = documents.search(uid, "Heizung Wartung Termin")
        self.assertEqual({h["id"] for h in plain}, {old, new})
        self.assertFalse(any("changed" in h for h in plain))                 # switch off: as before
        self.assertEqual([h["id"] for h in plain], [old, new])               # equal text: the order of storing
        before = {h["id"]: h["score"] for h in plain}
        hits = documents.search(uid, "Heizung Wartung Termin", fresh=True, now=self.NOW)
        self.assertEqual([h["id"] for h in hits], [new, old])                # one place up: newer counts
        self.assertEqual(hits[0]["changed"], self.NOW - self.DAY)            # the page's own time, not the notebook's
        gain = {h["id"]: h["score"] - before[h["id"]] for h in hits}
        self.assertTrue(0 < gain[new] <= documents.FRESH < 1 / 60 - 1 / 63)  # at most about two places, never three
        self.assertLess(gain[old], gain[new] / 100)                         # over a year old: next to nothing
        self.assertIn("geändert am", wissen.where(hits[0]))
        self.assertNotIn("geändert am", wissen.where(plain[0]))
        # through wissen.search, the one place document_search and "Erst lokal suchen" rank in
        got = run(wissen.search(uid, "Heizung Wartung Termin", semantic=False))
        self.assertEqual({h["id"]: h["changed"] for h in got}, {new: self.NOW - self.DAY, old: self.NOW - 400 * self.DAY})

    def test_recent_window_on_own_words(self):
        zone = datetime.timezone.utc
        now = datetime.datetime(2026, 10, 7, 15, 0, tzinfo=zone).timestamp()        # a Wednesday
        day = lambda *a: int(datetime.datetime(*a, tzinfo=zone).timestamp())     # noqa: E731
        cases = {"Was habe ich heute notiert?": (day(2026, 10, 7), None),
                 "Was habe ich gestern aufgeschrieben?": (day(2026, 10, 6), day(2026, 10, 7)),
                 "Was hab ich vorgestern notiert": (day(2026, 10, 5), day(2026, 10, 6)),
                 "Was habe ich diese Woche notiert?": (day(2026, 10, 5), None),
                 "Welche Notizen habe ich letzte Woche gemacht?": (day(2026, 9, 28), day(2026, 10, 5)),
                 "Was steht in meinen Notizen von diesem Monat?": (day(2026, 10, 1), None),
                 "Was habe ich letzten Monat notiert?": (day(2026, 9, 1), day(2026, 10, 1)),
                 "Was habe ich zuletzt notiert?": (0, None),
                 "Was sind meine neuesten Notizen?": (0, None),
                 "What did I note today?": (day(2026, 10, 7), None)}
        for text, want in cases.items():
            self.assertEqual(wissen.recent_window(text, zone, now), want, text)
        for text in ("Was hat mir Anna heute geschrieben?", "Notier heute Milch", "Schreib in meine Notizen: heute Milch",
                     "Wie wird das Wetter heute?", "Was steht in meinen Notizen über die Heizung?", "Leg meine Notizen von heute ab", ""):
            self.assertIsNone(wissen.recent_window(text, zone, now), text)

    def test_what_did_i_note_lately_lists_the_newest_pages(self):
        c, uid = self.fresh("Rmfreshask")
        CLOUD[0].doc(NB, "Einkauf", [(P1, page_file("Milch und Brot")), (P2, page_file("Gartenschlauch kaufen"))],
                     times={P1: (self.NOW - 90 * self.DAY) * 1000, P2: (self.NOW - self.DAY) * 1000})
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        run(remarkable.sync(uid))
        ask = 'TOOL document_search {"query": "Was habe ich zuletzt notiert"}'
        helpers.LLM_CALLS.clear()
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": ask}], "convo": "neu"})
        said = "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
        self.assertEqual(helpers.LLM_CALLS[0].get("tool_choice"), {"type": "function", "function": {"name": "document_search"}})
        self.assertIn("Gartenschlauch", said)
        self.assertLess(said.index("Gartenschlauch"), said.index("Milch"))   # newest first
        self.assertIn("geändert am", said)
        c.put("/api/profile/settings", json={"rm_fresh": False})            # switch off: the model decides, no dates
        helpers.LLM_CALLS.clear()
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "SAY | Was habe ich zuletzt notiert?"}], "convo": "neu"})
        self.assertNotEqual(helpers.LLM_CALLS[0].get("tool_choice"), {"type": "function", "function": {"name": "document_search"}})

    def test_nothing_in_the_window_is_said(self):
        c, uid = self.fresh("Rmfreshnone")
        CLOUD[0].doc(NB, "Alt", [(P1, page_file("Altes Rezept"))], times={P1: (self.NOW - 900 * self.DAY) * 1000})
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        run(remarkable.sync(uid))
        r = c.post("/api/chat", json={"messages": [{"role": "user", "content":
                   'TOOL document_search {"query": "Was habe ich heute notiert"}'}], "convo": "neu"})
        said = "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")
        self.assertIn("Nothing was noted", said)
        self.assertNotIn("Altes Rezept", said)

    def test_quick_look_brings_new_notes_soon(self):
        c, uid = self.paired("Rmpeek")
        CLOUD[0].doc(NB, "Ideen", [(P1, page_file("Gartenhaus planen"))])
        c.put("/api/profile/remarkable/pick", json={"ids": [NB], "all": False})
        for other in profiles.user_ids():          # other tests' profiles are not due
            if other != uid:
                remarkable._auto_last[other] = remarkable._peek_last[other] = 1e12
        self.assertEqual(run(remarkable.due_once(idle=True)), uid)
        d = remarkable.load(uid)
        self.assertEqual(d["root"], CLOUD[0].root)
        t = max(d["last"], remarkable._auto_last[uid])
        CLOUD[0].calls.clear()
        self.assertIsNone(run(remarkable.due_once(idle=True, now=t + 60)))       # not yet: no request at all
        self.assertEqual(CLOUD[0].calls, [])
        self.assertIsNone(run(remarkable.due_once(idle=True, now=t + remarkable.PEEK + 1)))
        self.assertEqual([x[1] for x in CLOUD[0].calls], ["v4/root"])         # one small look, nothing changed
        CLOUD[0].doc(NB, "Ideen", [(P1, page_file("Gartenhaus planen")), (P2, page_file("Teich anlegen"))])
        self.assertIsNone(run(remarkable.due_once(idle=True, now=t + remarkable.PEEK + 60)))   # the next look waits
        self.assertIsNone(run(remarkable.due_once(idle=False, now=t + 2 * remarkable.PEEK + 2)))   # never while busy
        self.assertEqual(run(remarkable.due_once(idle=True, now=t + 2 * remarkable.PEEK + 2)), uid)
        self.assertTrue(documents.search(uid, "Teich anlegen"))
        self.assertEqual(remarkable.load(uid)["root"], CLOUD[0].root)


class Guards(unittest.TestCase):
    def test_hosts_and_index_lines(self):
        for url in (remarkable.ROOT_URL, remarkable.DEVICE_URL, "https://storage.googleapis.com/x"):
            self.assertTrue(remarkable.host_ok(url), url)
        for url in ("http://internal.cloud.remarkable.com/x", "https://evil.example/x", "https://remarkable.com.evil.example/",
                    "https://127.0.0.1/", "file:///etc/passwd"):
            self.assertFalse(remarkable.host_ok(url), url)
        with self.assertRaises(remarkable.CloudError):
            run(REAL_REQUEST("GET", "https://evil.example/x"))
        h = "a" * 64
        idx = f"3\n{h}:0:x.metadata:0:5\n{h}:0:../../etc:0:5\nzz:0:y:0:1\n{h}:0:a/b.rm:0:x\n{h}:0:.:3:1\n".encode()
        self.assertEqual([e["id"] for e in remarkable.parse_index(idx)], ["x.metadata"])

    def test_page_order_and_names(self):
        a, b, c = (str(uuid.UUID(int=i)) for i in (7, 8, 9))
        content = {"cPages": {"pages": [{"id": b, "idx": {"value": "bb"}}, {"id": a, "idx": {"value": "ba"}},
                                        {"id": c, "idx": {"value": "bc"}, "deleted": {"value": 1}}, {"id": "../x"}]}}
        self.assertEqual(remarkable.page_order(content), [a, b])
        self.assertEqual(remarkable.page_order({"pages": [a, "nope"]}), [a])
        self.assertEqual(remarkable._clean('Böse<script>"\\\x00Name'), "BösescriptName")
        items = {"f": {"name": "A", "parent": "", "folder": True}, "n": {"name": "B", "parent": "f", "folder": False},
                 "t": {"name": "C", "parent": "trash", "folder": False}}
        self.assertEqual(remarkable.path_of(items, "n"), "A/B")
        self.assertIsNone(remarkable.path_of(items, "t"))

    @unittest.skipIf(si is None, "rmscene not installed")
    def test_real_page_file(self):
        typed, marks, jpeg, ink = remarkable.parse_page(page_file("Erste Zeile\nZweite Zeile", strokes=4))
        self.assertEqual(typed, "Erste Zeile\nZweite Zeile")
        self.assertTrue(ink and jpeg[:2] == b"\xff\xd8")
        self.assertIsNone(remarkable.parse_page(page_file("Nur Text"), draw=True)[2])
        with self.assertRaises(ValueError):
            remarkable.parse_page(b"reMarkable .lines file, version=5          ")

    def test_crc32c(self):
        self.assertEqual(remarkable.crc32c(b"123456789"), 0xE3069283)     # the standard check value


if __name__ == "__main__":
    unittest.main()
