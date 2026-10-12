"""Eigener Speicher (speicher.py) against a fake WebDAV server and a temporary folder. One self-test per rule of
the plan: off without switches, never for guests or device keys, the password never comes back, only the
allowlisted areas leave the Spark and only encrypted, only changed files go again, deleted ones wait in the bin,
offline/full/sign-in refused keep everything local and tell the owner once, "Fehlendes zurückholen" never
overwrites and checks every file, paths cannot leave their folders, the admin sees no file names, Live and the
Dienst-Wächter know the targets. No test reads the clock (times are set in the stored state)."""
import asyncio
import base64
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import dienstwacht  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import logfilter  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import speicher  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PORT = helpers._port()
BASE = f"http://127.0.0.1:{PORT}/dav/"
DAV = {"files": {}, "dirs": set(), "user": "spark", "pw": "nas-pass-4711", "mode": "", "calls": []}
SECRET_WORD = "Kuchenrezept-Geheimnis-0815"


def fake():
    app = FastAPI()

    @app.api_route("/dav/{path:path}", methods=["MKCOL", "PUT", "GET", "DELETE", "PROPFIND"])
    async def dav(path: str, req: Request):
        DAV["calls"].append((req.method, path))
        if DAV["mode"] == "down":
            return Response(status_code=503)
        a = req.headers.get("authorization", "")
        want = "Basic " + base64.b64encode(f"{DAV['user']}:{DAV['pw']}".encode()).decode()
        if a != want:
            return Response(status_code=401)
        if req.method == "MKCOL":
            if path in DAV["dirs"]:
                return Response(status_code=405)
            DAV["dirs"].add(path)
            return Response(status_code=201)
        if req.method == "PUT":
            if DAV["mode"] == "full":
                return Response(status_code=507)
            DAV["files"][path] = await req.body()
            return Response(status_code=201)
        if req.method == "GET":
            if path not in DAV["files"]:
                return Response(status_code=404)
            return Response(DAV["files"][path], media_type="application/octet-stream")
        if req.method == "DELETE":
            DAV["files"].pop(path, None)
            return Response(status_code=204)
        used = sum(len(v) for v in DAV["files"].values())
        return Response(f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop>'
                        f'<d:quota-available-bytes>{10 ** 9}</d:quota-available-bytes><d:quota-used-bytes>{used}'
                        f'</d:quota-used-bytes></d:prop></d:propstat></d:response></d:multistatus>', status_code=207)
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


def objects():
    return {k: v for k, v in DAV["files"].items() if "/o/" in k}


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(storage_own=True, storage_lan=True, storage_folder=False, storage_root="")
        DAV.update(files={}, dirs=set(), mode="", calls=[], pw="nas-pass-4711")
        speicher._running.clear()

    def tearDown(self):
        helpers.set_config(storage_own=False, storage_lan=False, storage_folder=False, storage_root="")

    def ready(self, name):
        c, uid = profile(name)
        self.assertEqual(c.put("/api/profile/settings", json={"storage_on": True}).status_code, 200)
        return c, uid

    def add(self, c, **kw):
        body = dict(dict(name="NAS Keller", kind="webdav", url=BASE, user="spark", password="nas-pass-4711"), **kw)
        r = c.post("/api/profile/speicher", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]

    def write(self, uid, rel, data):
        p = profiles._path(uid, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)
        return p

    def manifest(self, uid):
        key = speicher._key(uid)
        name = next(k for k in DAV["files"] if k.endswith("manifest.enc"))
        return json.loads(speicher.open_bytes(DAV["files"][name], key, "manifest"))


class Switches(Base):
    def test_off_without_switches_and_never_for_guests_or_devices(self):
        c, uid = profile("SpAus")
        helpers.set_config(storage_own=False)
        self.assertEqual(c.get("/api/profile/speicher").status_code, 403)
        self.assertFalse(c.get("/api/whoami").json().get("storage"))
        helpers.set_config(storage_own=True)
        self.assertTrue(c.get("/api/whoami").json().get("storage"))       # the Ich page shows, the own switch is off
        self.assertFalse(c.get("/api/profile/speicher").json()["on"])
        r = c.post("/api/profile/speicher", json={"name": "N", "kind": "webdav", "url": BASE, "user": "spark", "password": "x"})
        self.assertEqual(r.status_code, 403)
        helpers.set_config(public=True)
        self.assertIn(TestClient(panel.app).get("/api/profile/speicher").status_code, (401, 403))
        helpers.set_config(public=False)
        # nothing runs for a profile whose switch is off
        with mock.patch.object(speicher, "spawn", lambda coro: coro.close()):
            self.assertNotIn(uid, [u for u, _ in run(speicher.round_once(now=speicher.STARTED + 10 ** 6))])

    def test_home_network_only_with_its_switch(self):
        c, uid = self.ready("SpLan")
        helpers.set_config(storage_lan=False)
        r = c.post("/api/profile/speicher", json={"name": "N", "kind": "webdav", "url": BASE, "user": "spark",
                                                  "password": "nas-pass-4711"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Heimnetz", r.text)
        self.assertEqual(speicher.targets(uid), [])

    def test_folder_kind_only_with_its_switch(self):
        c, uid = self.ready("SpOrdnerAus")
        r = c.post("/api/profile/speicher", json={"name": "N", "kind": "folder", "folder": "anna"})
        self.assertEqual(r.status_code, 400)


class Targets(Base):
    def test_add_checks_by_writing_and_never_returns_the_password(self):
        c, uid = self.ready("SpNeu")
        r = c.post("/api/profile/speicher", json={"name": "NAS", "kind": "webdav", "url": BASE, "user": "spark",
                                                  "password": "falsch"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("Anmeldung", r.json()["detail"])
        self.assertEqual(speicher.targets(uid), [])
        tid = self.add(c)
        view = c.get("/api/profile/speicher").json()
        self.assertNotIn("nas-pass-4711", json.dumps(view))
        self.assertTrue(view["targets"][0]["has_password"])
        self.assertEqual(view["targets"][0]["areas"], list(speicher.AREAS))
        with open(profiles._path(uid, "speicher.json")) as f:
            self.assertNotIn("nas-pass-4711", f.read())       # sealed on disk too
        self.assertFalse(any(k.endswith("probe.enc") for k in DAV["files"]))   # the probe is gone again
        # at most MAX_TARGETS; another profile cannot touch it
        self.add(c, name="Zweiter")
        r = c.post("/api/profile/speicher", json={"name": "Dritter", "kind": "webdav", "url": BASE, "user": "spark",
                                                  "password": "nas-pass-4711"})
        self.assertEqual(r.status_code, 400)
        b, _ = self.ready("SpFremd")
        b.delete(f"/api/profile/speicher/{tid}")
        self.assertTrue(speicher.find(uid, tid))
        self.assertEqual(b.get("/api/profile/speicher").json()["targets"], [])

    def test_new_address_needs_the_password_again(self):
        c, uid = self.ready("SpAdresse")
        tid = self.add(c)
        r = c.put(f"/api/profile/speicher/{tid}", json={"url": f"http://127.0.0.1:{PORT}/dav/neu/"})
        self.assertEqual(r.status_code, 400)
        r = c.put(f"/api/profile/speicher/{tid}", json={"url": f"http://127.0.0.1:{PORT}/dav/neu/", "password": "nas-pass-4711"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(speicher.find(uid, tid)["url"], f"http://127.0.0.1:{PORT}/dav/neu/")

    def test_addresses(self):
        for bad in ("ftp://nas/x", "https://u:p@nas.example/x", "https://nas.example/x?a=1", "http://nas.example.com/x",
                    "https://nas.example/a/../b", "https:///x", "https://nas.example/x\ny"):
            with self.assertRaises(ValueError, msg=bad):
                speicher.check_url(bad)
        self.assertEqual(speicher.check_url("http://192.168.178.20:5005/spark"), "http://192.168.178.20:5005/spark/")
        self.assertEqual(speicher.check_url("https://cloud.example.org/remote.php/dav/files/a"),
                         "https://cloud.example.org/remote.php/dav/files/a/")

    def test_paths_stay_in_their_folders(self):
        for bad in ("../secret", "docs/files/../../secret", "settings.json", "mail.json", "docs/files/", "docs/files/.x",
                    "erstellt/a/b.json", "speicher.json", "mfa.json", "push.json", "docs/files/x.tmp"):
            self.assertFalse(speicher._rel_ok(bad), bad)
        for good in ("memory.json", "wissen.db", "docs/files/0123456789ab.pdf", "erstellt/0123456789ab.json"):
            self.assertTrue(speicher._rel_ok(good), good)
        for bad in ("/etc", "/srv/../etc", "/tmp/x", "/srv//x", "srv/x", "/srv/x y"):
            self.assertFalse(speicher.check_root(bad, quiet=True), bad)


class Copy(Base):
    def test_only_the_allowlist_goes_and_only_encrypted(self):
        c, uid = self.ready("SpKopie")
        tid = self.add(c)
        self.write(uid, "memory.json", json.dumps([{"text": SECRET_WORD}]))
        self.write(uid, "docs/files/0123456789ab.txt", SECRET_WORD * 50)
        for never in ("settings.json", "mail.json", "calendar.json", "push.json", "mfa.json"):
            self.write(uid, never, json.dumps({"x": SECRET_WORD}))
        os.symlink("/etc/hostname", profiles._path(uid, "docs/files/aaaaaaaaaaaa.txt"))
        last = run(speicher.copy_once(uid, tid))
        self.assertTrue(last["ok"], last)
        man = self.manifest(uid)["files"]
        self.assertIn("memory.json", man)
        self.assertIn("docs/files/0123456789ab.txt", man)
        self.assertFalse({"settings.json", "mail.json", "calendar.json", "push.json", "mfa.json", "speicher.json",
                          "docs/files/aaaaaaaaaaaa.txt"} & set(man))
        for k, v in DAV["files"].items():
            self.assertNotIn(SECRET_WORD.encode(), v, k)                          # the storage sees only noise
            self.assertNotIn(b"memory", v, k)
        self.assertTrue(all(speicher.OBJ.fullmatch(k.rsplit("/", 1)[1][:-4]) for k in objects()))
        folder = speicher.folder_name(speicher._key(uid))
        self.assertEqual([k for k in DAV["files"] if not k.startswith(folder + "/")], [])
        self.assertNotIn(uid, folder)

    def test_only_changes_go_again_and_deleted_files_wait_in_the_bin(self):
        c, uid = self.ready("SpWieder")
        tid = self.add(c, areas=["gedaechtnis", "dokumente"])
        self.write(uid, "memory.json", "[1]")
        doc = self.write(uid, "docs/files/0123456789ab.txt", "eins")
        run(speicher.copy_once(uid, tid))
        first = set(objects())
        self.assertEqual(len(first), 2)
        self.assertEqual(run(speicher.copy_once(uid, tid))["n"], 0)              # nothing changed: nothing goes
        self.assertEqual(set(objects()), first)
        os.utime(doc, ns=(1, 1))                                                  # only a new time stamp: no new object
        self.assertEqual(run(speicher.copy_once(uid, tid))["n"], 0)
        self.write(uid, "memory.json", "[1, 2]")
        os.remove(doc)
        self.assertEqual(run(speicher.copy_once(uid, tid))["n"], 1)
        st = speicher._state(uid, tid)
        self.assertEqual(len(st["trash"]), 2)                                     # the old memory and the deleted doc
        self.assertEqual(len(objects()), 3)                                       # still there for TRASH_DAYS
        st["trash"] = [dict(x, t=1) for x in st["trash"]]
        speicher._put_state(uid, tid, st)
        run(speicher.copy_once(uid, tid))
        self.assertEqual(len(objects()), 1)
        self.assertEqual(speicher._state(uid, tid)["trash"], [])
        # an area taken off the list: its files go to the bin as well
        c.put(f"/api/profile/speicher/{tid}", json={"areas": ["dokumente"]})
        run(speicher.copy_once(uid, tid))
        self.assertEqual(self.manifest(uid)["files"], {})

    def test_database_copy_is_consistent(self):
        import sqlite3
        c, uid = self.ready("SpDb")
        tid = self.add(c, areas=["dokumente"])
        con = sqlite3.connect(profiles._path(uid, "wissen.db"))
        con.execute("CREATE TABLE t (x TEXT)")
        con.execute("INSERT INTO t VALUES ('hallo')")
        con.commit()
        con.close()
        run(speicher.copy_once(uid, tid))
        os.remove(profiles._path(uid, "wissen.db"))
        self.assertEqual(run(speicher.restore_missing(uid, tid))["n"], 1)
        con = sqlite3.connect(profiles._path(uid, "wissen.db"))
        self.assertEqual(con.execute("SELECT x FROM t").fetchall(), [("hallo",)])
        con.close()


class Outages(Base):
    def test_offline_keeps_everything_and_tells_the_owner_after_an_hour(self):
        c, uid = self.ready("SpWeg")
        tid = self.add(c, areas=["gedaechtnis"])
        self.write(uid, "memory.json", "[1]")
        DAV["mode"] = "down"
        sent = []
        with mock.patch("push.send", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append(a) or 1)):
            last = run(speicher.copy_once(uid, tid))
            self.assertFalse(last["ok"])
            self.assertEqual(last["kind"], "offline")
            self.assertEqual(sent, [])                                            # not after a few minutes
            self.assertTrue(os.path.exists(profiles._path(uid, "memory.json")))
            st = speicher._state(uid, tid)
            st["fail"]["since"] -= 2 * speicher.NOTE_AFTER
            speicher._put_state(uid, tid, st)
            run(speicher.copy_once(uid, tid))
            self.assertEqual(len(sent), 1)
            self.assertIn("nicht erreichbar", sent[0][1])
            self.assertNotIn("127.0.0.1", sent[0][1] + sent[0][2])                # no address in a note
            run(speicher.copy_once(uid, tid))
            self.assertEqual(len(sent), 1)                                        # once a day per kind
            DAV["mode"] = ""
            self.assertTrue(run(speicher.copy_once(uid, tid))["ok"])
            self.assertEqual(len(sent), 2)
            self.assertIn("wieder da", sent[1][1])
        self.assertIsNone(speicher._state(uid, tid)["fail"])

    def test_refused_sign_in_and_full_are_told_at_once(self):
        c, uid = self.ready("SpVoll")
        tid = self.add(c, areas=["gedaechtnis"])
        self.write(uid, "memory.json", "[1]")
        sent = []
        with mock.patch("push.send", new=mock.AsyncMock(side_effect=lambda *a, **k: sent.append(a) or 1)):
            DAV["pw"] = "geändert"
            self.assertEqual(run(speicher.copy_once(uid, tid))["kind"], "auth")
            self.assertIn("Anmeldung", sent[-1][1])
            self.assertIn("Ich → Speicher", sent[-1][2])                         # the way to fix it
            DAV.update(pw="nas-pass-4711", mode="full")
            self.assertEqual(run(speicher.copy_once(uid, tid))["kind"], "full")
            self.assertIn("voll", sent[-1][1])
        self.assertTrue(os.path.exists(profiles._path(uid, "memory.json")))
        # a refused sign-in waits long before the next try; an outage only a little
        st = speicher._state(uid, tid)
        st["fail"] = {"kind": "auth", "n": 1, "since": 1000}
        st["last"] = {"t": 1000}
        self.assertFalse(speicher.due(uid, speicher.find(uid, tid), st, now=1000 + 20 * 60))
        st["fail"]["kind"] = "offline"
        self.assertTrue(speicher.due(uid, speicher.find(uid, tid), st, now=1000 + 20 * 60))

    def test_missing_key_is_said(self):
        c, uid = self.ready("SpSchluessel")
        tid = self.add(c, areas=["gedaechtnis"])
        d = speicher.load(uid)
        d["key"] = "enc1:kaputt"
        speicher.save(uid, d)
        with mock.patch("push.send", new=mock.AsyncMock(return_value=1)):
            self.assertEqual(run(speicher.copy_once(uid, tid))["kind"], "key")


class Restore(Base):
    def test_only_missing_files_each_checked(self):
        c, uid = self.ready("SpZurueck")
        tid = self.add(c, areas=["gedaechtnis", "dokumente"])
        self.write(uid, "memory.json", "[1]")
        self.write(uid, "docs/files/0123456789ab.txt", "Original")
        self.write(uid, "docs/files/bbbbbbbbbbbb.txt", "Zweites")
        run(speicher.copy_once(uid, tid))
        self.write(uid, "memory.json", "[1, 2, 3]")                               # there: never overwritten
        os.remove(profiles._path(uid, "docs/files/0123456789ab.txt"))
        os.remove(profiles._path(uid, "docs/files/bbbbbbbbbbbb.txt"))
        # one object changed on the storage: it does not open, the file stays missing
        man = self.manifest(uid)["files"]
        bad = next(k for k in objects() if man["docs/files/bbbbbbbbbbbb.txt"]["o"] in k)
        DAV["files"][bad] = DAV["files"][bad][:-5] + b"xxxxx"
        r = c.post(f"/api/profile/speicher/{tid}/restore")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["restored"], {"n": 1, "skipped": 1})
        with open(profiles._path(uid, "docs/files/0123456789ab.txt")) as f:
            self.assertEqual(f.read(), "Original")
        with open(profiles._path(uid, "memory.json")) as f:
            self.assertEqual(f.read(), "[1, 2, 3]")
        self.assertFalse(os.path.exists(profiles._path(uid, "docs/files/bbbbbbbbbbbb.txt")))

    def test_objects_bind_their_name_and_their_end(self):
        key = os.urandom(32)
        data = speicher.seal_bytes(b"x" * (speicher.CHUNK + 10), key, "a" * 24)
        self.assertEqual(speicher.open_bytes(data, key, "a" * 24), b"x" * (speicher.CHUNK + 10))
        for bad in (lambda: speicher.open_bytes(data, key, "b" * 24),             # moved to another name
                    lambda: speicher.open_bytes(data, os.urandom(32), "a" * 24),  # another key
                    lambda: speicher.open_bytes(data[:speicher.CHUNK], key, "a" * 24),  # cut after the first piece
                    lambda: speicher.open_bytes(data, key, "a" * 24, most=100)):  # larger than allowed
            with self.assertRaises(ValueError):
                bad()


class Folder(Base):
    def test_folder_on_the_spark(self):
        top = tempfile.mkdtemp(prefix="spark-speicher-")
        try:
            with mock.patch.object(speicher, "ROOTS", (os.path.dirname(top) + "/",)):
                self.assertEqual(ADMIN.put("/api/config", json={"chat": {"storage_root": "/etc/x"}}).status_code, 400)
                helpers.set_config(storage_folder=True, storage_root=top)
                c, uid = self.ready("SpOrdner")
                self.assertEqual(c.post("/api/profile/speicher", json={"name": "O", "kind": "folder", "folder": "../x"}).status_code, 400)
                r = c.post("/api/profile/speicher", json={"name": "Platte", "kind": "folder", "folder": "anna",
                                                          "areas": ["gedaechtnis"]})
                self.assertEqual(r.status_code, 200, r.text)
                tid = r.json()["added"]
                self.write(uid, "memory.json", json.dumps([SECRET_WORD]))
                self.assertTrue(run(speicher.copy_once(uid, tid))["ok"])
                base = os.path.join(top, "anna", speicher.folder_name(speicher._key(uid)))
                self.assertTrue(os.path.isfile(os.path.join(base, "manifest.enc")))
                self.assertEqual(len(os.listdir(os.path.join(base, "o"))), 1)
                for d, _, fs in os.walk(top):
                    for n in fs:
                        with open(os.path.join(d, n), "rb") as f:
                            self.assertNotIn(SECRET_WORD.encode(), f.read())
                self.assertEqual(os.stat(os.path.join(top, "anna")).st_mode & 0o777, 0o700)
                # a symlink put into the folder is refused
                shutil.rmtree(os.path.join(base, "o"))
                os.symlink("/tmp", os.path.join(base, "o"))
                self.write(uid, "memory.json", "[2]")
                self.assertFalse(run(speicher.copy_once(uid, tid))["ok"])
                # switched off: nothing is written there any more
                helpers.set_config(storage_folder=False)
                self.assertEqual(run(speicher.copy_once(uid, tid))["kind"], "blocked")
        finally:
            shutil.rmtree(top, ignore_errors=True)


class Shown(Base):
    def test_admin_sees_no_file_names_and_others_see_nothing(self):
        c, uid = self.ready("SpAdmin")
        tid = self.add(c, areas=["dokumente"])
        self.write(uid, "docs/files/0123456789ab.txt", "x")
        run(speicher.copy_once(uid, tid))
        d = ADMIN.get("/api/admin/speicher").json()
        row = next(r for r in d["rows"] if r["profile"] == "SpAdmin")
        self.assertEqual((row["files"], row["kind"], row["zone"]), (1, "webdav", "lan"))
        self.assertNotIn("0123456789ab", json.dumps(d))
        self.assertNotIn("nas-pass", json.dumps(d))
        self.assertEqual(c.get("/api/admin/speicher").status_code, 401)
        self.assertEqual(TestClient(panel.app).get("/api/admin/speicher").status_code, 401)

    def test_live_watch_and_logs_know_it(self):
        c, uid = self.ready("SpLive")
        self.add(c)
        self.assertEqual(live.TOOLS["Speicher-Abgleich"], "speicher")
        self.assertIn("speicher", live.TARGETS)
        for k in ("storage_add", "storage_change", "storage_remove"):
            self.assertIn(k, guard.LIVE_WORDS)
        self.assertIn("speicher", dict(logfilter.AREAS))
        helpers.set_config(svc_watch=True)
        try:
            act = dienstwacht.active()
            self.assertIn("store", act)
            self.assertTrue(all(p["url"] == f"http://127.0.0.1:{PORT}/" for p in act["store"].values() if not p.get("tcp")))
            self.assertNotIn("password", json.dumps(act["store"]))
        finally:
            helpers.set_config(svc_watch=False)
        # the profile switch off: no probe for its targets
        c.put("/api/profile/settings", json={"storage_on": False})
        self.assertFalse(any(uid in p["uids"] for p in speicher.probes().values()))


if __name__ == "__main__":
    unittest.main()


class Offload(Base):
    """Originale auslagern: only kept originals of documents, only after OFFLOAD_DAYS unchanged and unused, each
    read back and checked before the Spark deletes it, fetched back and checked when opened, never lost. The files
    get a time stamp from 1970, so no test depends on the clock."""
    def setUp(self):
        super().setUp()
        helpers.set_config(storage_offload=True)

    def tearDown(self):
        helpers.set_config(storage_offload=False)
        super().tearDown()

    def doc(self, uid, text="Mietvertrag Seite eins", old=True):
        import documents
        d = documents.add(uid, "Vertrag.txt", text.encode(), keep=10 ** 6)
        self.assertTrue(d["file"], d)
        rel = "docs/files/" + d["id"] + ".txt"
        if old:
            os.utime(profiles._path(uid, rel), ns=(10 ** 9, 10 ** 9))
        return d["id"], rel, profiles._path(uid, rel)

    def on(self, c, tid):
        r = c.put(f"/api/profile/speicher/{tid}", json={"offload": True})
        self.assertEqual(r.status_code, 200, r.text)

    def test_needs_the_admin_switch_and_only_one_storage(self):
        c, uid = self.ready("SpAusSchalter")
        tid = self.add(c, areas=["dokumente"])
        helpers.set_config(storage_offload=False)
        self.assertEqual(c.put(f"/api/profile/speicher/{tid}", json={"offload": True}).status_code, 400)
        self.assertEqual(c.put(f"/api/profile/speicher/{tid}", json={"offload": "ja"}).status_code, 400)
        self.assertFalse(c.get("/api/profile/speicher").json()["offload"])
        _, rel, p = self.doc(uid)
        run(speicher.copy_once(uid, tid))
        self.assertTrue(os.path.exists(p))                                        # switch off: nothing moves
        helpers.set_config(storage_offload=True)
        self.on(c, tid)
        r = c.post("/api/profile/speicher", json=dict(name="Zweiter", kind="webdav", url=BASE, user="spark",
                                                      password="nas-pass-4711", offload=True))
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("einen Speicher", r.json()["detail"])
        helpers.set_config(storage_offload=False)                                 # admin switch off again: nothing moves
        run(speicher.copy_once(uid, tid))
        self.assertTrue(os.path.exists(p))

    def test_moved_out_after_a_check_and_fetched_back_when_opened(self):
        import documents
        c, uid = self.ready("SpAuslagern")
        tid = self.add(c, areas=["gedaechtnis", "dokumente"])
        self.on(c, tid)
        doc_id, rel, p = self.doc(uid)
        old_mem = self.write(uid, "memory.json", "[1]")
        os.utime(old_mem, ns=(10 ** 9, 10 ** 9))
        _, _, fresh = self.doc(uid, "Neue Rechnung", old=False)
        self.assertTrue(run(speicher.copy_once(uid, tid))["ok"])
        self.assertFalse(os.path.exists(p))                                       # old original: only there now
        self.assertTrue(os.path.exists(fresh))                                    # changed lately: stays
        self.assertTrue(os.path.exists(old_mem))                                  # not a document original: stays
        self.assertEqual(speicher.away(uid), {tid: 1})
        self.assertEqual(c.get("/api/profile/speicher").json()["targets"][0]["away"], 1)
        self.assertIn(rel, self.manifest(uid)["files"])                           # still listed, not in the bin
        self.assertEqual(speicher._state(uid, tid)["trash"], [])
        got = documents.original(uid, doc_id)                                     # opened: fetched and checked
        self.assertIsNotNone(got)
        with open(got[0]) as f:
            self.assertEqual(f.read(), "Mietvertrag Seite eins")
        self.assertEqual(speicher.away(uid), {})
        run(speicher.copy_once(uid, tid))
        self.assertTrue(os.path.exists(p))                                        # just used: not moved again
        self.assertEqual(speicher.away(uid), {})

    def test_never_deleted_without_a_good_copy_and_unreachable_is_said(self):
        import documents
        c, uid = self.ready("SpPruefen")
        tid = self.add(c, areas=["dokumente"])
        doc_id, rel, p = self.doc(uid)
        run(speicher.copy_once(uid, tid))
        o = self.manifest(uid)["files"][rel]["o"]
        name = next(k for k in objects() if o in k)
        good = DAV["files"][name]
        DAV["files"][name] = good[:-5] + b"xxxxx"                                 # broken on the storage
        self.on(c, tid)
        run(speicher.copy_once(uid, tid))
        self.assertTrue(os.path.exists(p))                                        # read back, did not match: stays
        DAV["files"][name] = good
        run(speicher.copy_once(uid, tid))
        self.assertFalse(os.path.exists(p))
        DAV["mode"] = "down"                                                      # storage gone: nothing invented
        self.assertIsNone(documents.original(uid, doc_id))
        self.assertTrue(documents.away(uid, doc_id))
        self.assertEqual(speicher.away(uid), {tid: 1})
        DAV["mode"] = ""
        DAV["files"][name] = good[:-5] + b"xxxxx"                                 # changed there: never written here
        self.assertIsNone(documents.original(uid, doc_id))
        self.assertFalse(os.path.exists(p))
        DAV["files"][name] = good
        self.assertIsNotNone(documents.original(uid, doc_id))
        self.assertFalse(documents.away(uid, doc_id))

    def test_kept_while_only_there_and_a_deleted_document_goes_to_the_bin(self):
        import documents
        c, uid = self.ready("SpBleibt")
        tid = self.add(c, areas=["dokumente"])
        self.on(c, tid)
        doc_id, rel, p = self.doc(uid)
        run(speicher.copy_once(uid, tid))
        self.assertFalse(os.path.exists(p))
        r = c.delete(f"/api/profile/speicher/{tid}")                              # would lose the only copy
        self.assertEqual(r.status_code, 409, r.text)
        r = c.put(f"/api/profile/speicher/{tid}", json={"url": BASE + "anders/", "password": "nas-pass-4711"})
        self.assertEqual(r.status_code, 409, r.text)
        r = c.put(f"/api/profile/speicher/{tid}", json={"areas": []})             # area off: still kept there
        self.assertEqual(r.status_code, 200, r.text)
        run(speicher.copy_once(uid, tid))
        self.assertIn(rel, speicher._state(uid, tid)["files"])
        o = speicher._state(uid, tid)["files"][rel]["o"]
        self.assertNotIn(o, [x["o"] for x in speicher._state(uid, tid)["trash"]])
        self.assertTrue(documents.delete(uid, doc_id))                            # the document itself deleted
        run(speicher.copy_once(uid, tid))
        self.assertNotIn(rel, speicher._state(uid, tid)["files"])
        self.assertIn(o, [x["o"] for x in speicher._state(uid, tid)["trash"]])    # in the bin for TRASH_DAYS
        self.assertEqual(c.delete(f"/api/profile/speicher/{tid}").status_code, 200)

    def test_restore_brings_every_original_back(self):
        c, uid = self.ready("SpAlleZurueck")
        tid = self.add(c, areas=["dokumente"])
        self.on(c, tid)
        _, rel, p = self.doc(uid)
        run(speicher.copy_once(uid, tid))
        self.assertFalse(os.path.exists(p))
        c.put(f"/api/profile/speicher/{tid}", json={"offload": False})
        self.assertEqual(run(speicher.restore_missing(uid, tid))["n"], 1)
        self.assertTrue(os.path.exists(p))
        self.assertEqual(speicher.away(uid), {})
        self.assertEqual(c.delete(f"/api/profile/speicher/{tid}").status_code, 200)

    def test_bring_back_stays_in_its_folder(self):
        _, uid = self.ready("SpPfad")
        for bad in ("docs/files/../../speicher.json", "memory.json", "docs/files/x/../../../y"):
            self.assertFalse(speicher.bring_back(uid, bad))


class Classified(unittest.TestCase):
    def test_every_profile_file_is_copied_or_stays_local(self):
        """Richtlinie Teil 1, Punkt 24: each name the code passes to profiles._path(uid, "…") is in speicher.AREAS
        (may go encrypted to the own storage) or in speicher.LOCAL with a reason (stays on the Spark)."""
        import re
        panel_dir = os.path.dirname(speicher.__file__)
        names = set()
        for f in os.listdir(panel_dir):
            if f.endswith(".py"):
                src = open(os.path.join(panel_dir, f), encoding="utf-8").read()
                names |= set(re.findall(r'_path\([^,()]+(?:\([^)]*\))?[^,()]*,\s*"([^"/]+)"', src))
        copied = {p.split("/")[0] for _de, _en, files in speicher.AREAS.values() for p in files}
        self.assertGreater(len(names), 20)
        self.assertEqual(sorted(names - copied - set(speicher.LOCAL)), [],
                         "new file under users/<id>/: put it into speicher.AREAS or speicher.LOCAL")
        self.assertEqual(sorted(copied & set(speicher.LOCAL)), [])
        self.assertTrue(all(isinstance(v, str) and v for v in speicher.LOCAL.values()))


# ---------------------------------------------------------------- SFTP and SMB (V2)
import socket  # noqa: E402
import threading  # noqa: E402

import paramiko  # noqa: E402

SFTP = {"root": tempfile.mkdtemp(prefix="spark-sftp-"), "user": "spark", "pw": "ssh-pass-4711", "down": False,
        "key": paramiko.ECDSAKey.generate()}


class _Handle(paramiko.SFTPHandle):
    def stat(self):
        return paramiko.SFTPAttributes.from_stat(os.fstat(self.readfile.fileno() if hasattr(self, "readfile") else self.writefile.fileno()))


class _Fs(paramiko.SFTPServerInterface):
    """A tiny SFTP server on a temp folder (paths are jailed into it)."""

    def _p(self, path):
        p = os.path.normpath(os.path.join(SFTP["root"], path.lstrip("/")))
        if not p.startswith(SFTP["root"]):
            raise PermissionError(path)
        return p

    def _err(self, e):
        return paramiko.SFTPServer.convert_errno(e.errno or 1)

    def canonicalize(self, path):
        return "/" + os.path.relpath(self._p(path), SFTP["root"]).replace(".", "") if path in (".", "") else path

    def stat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(os.stat(self._p(path)))
        except OSError as e:
            return self._err(e)
    lstat = stat

    def open(self, path, flags, attr):
        try:
            p = self._p(path)
            mode = "wb" if flags & os.O_WRONLY else "rb"
            f = open(p, mode)
        except OSError as e:
            return self._err(e)
        h = _Handle(flags)
        if mode == "wb":
            h.writefile = f
        else:
            h.readfile = f
        return h

    def mkdir(self, path, attr):
        try:
            os.mkdir(self._p(path))
            return paramiko.SFTP_OK
        except OSError as e:
            return self._err(e)

    def remove(self, path):
        try:
            os.remove(self._p(path))
            return paramiko.SFTP_OK
        except OSError as e:
            return self._err(e)

    def rename(self, a, b):
        try:
            os.rename(self._p(a), self._p(b))
            return paramiko.SFTP_OK
        except OSError as e:
            return self._err(e)

    def posix_rename(self, a, b):
        return self.rename(a, b)


class _Auth(paramiko.ServerInterface):
    def check_auth_password(self, user, pw):
        return paramiko.AUTH_SUCCESSFUL if (user, pw) == (SFTP["user"], SFTP["pw"]) else paramiko.AUTH_FAILED

    def get_allowed_auths(self, user):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


def _sftp_server(port):
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("127.0.0.1", port))
    ls.listen(20)

    def one(sock):
        if SFTP["down"]:
            sock.close()
            return
        tr = paramiko.Transport(sock)
        tr.add_server_key(SFTP["key"])
        tr.set_subsystem_handler("sftp", paramiko.SFTPServer, _Fs)
        try:
            tr.start_server(server=_Auth())
        except Exception:
            tr.close()

    def loop():
        while True:
            s, _ = ls.accept()
            threading.Thread(target=one, args=(s,), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()


SPORT = helpers._port()
_sftp_server(SPORT)
SURL = f"sftp://127.0.0.1:{SPORT}/store"


def sftp_objects():
    out = {}
    for d, _, fs in os.walk(SFTP["root"]):
        for f in fs:
            with open(os.path.join(d, f), "rb") as x:
                out[os.path.relpath(os.path.join(d, f), SFTP["root"])] = x.read()
    return out


class SftpTarget(Base):
    def setUp(self):
        super().setUp()
        shutil.rmtree(SFTP["root"], ignore_errors=True)
        os.makedirs(os.path.join(SFTP["root"], "store"))
        SFTP.update(down=False, pw="ssh-pass-4711")

    def add_sftp(self, c, **kw):
        body = dict(dict(name="SSH", kind="sftp", url=SURL, user="spark", password="ssh-pass-4711"), **kw)
        r = c.post("/api/profile/speicher", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"]

    def test_copy_and_restore_encrypted_with_the_server_key_pinned(self):
        c, uid = self.ready("SpSftp")
        tid = self.add_sftp(c)
        t = speicher.find(uid, tid)
        self.assertEqual(t["hostkey"], speicher.hostkey_of(SFTP["key"]))
        view = c.get("/api/profile/speicher").json()["targets"][0]
        self.assertEqual(view["hostkey"], t["hostkey"])
        self.assertNotIn("ssh-pass-4711", json.dumps(view))
        self.write(uid, "memory.json", json.dumps({"x": SECRET_WORD}))
        last = run(speicher.copy_once(uid, tid))
        self.assertTrue(last["ok"], last)
        files = sftp_objects()
        self.assertTrue(any(k.endswith("manifest.enc") for k in files))
        self.assertTrue(any("/o/" in k for k in files))
        self.assertFalse(any(k.endswith(".part") or k.endswith("probe.enc") for k in files))
        self.assertFalse(any(SECRET_WORD.encode() in v for v in files.values()))
        os.remove(profiles._path(uid, "memory.json"))
        r = run(speicher.restore_missing(uid, tid))
        self.assertEqual(r["n"], 1)
        with open(profiles._path(uid, "memory.json")) as f:
            self.assertIn(SECRET_WORD, f.read())

    def test_wrong_password_and_a_server_that_is_gone(self):
        c, uid = self.ready("SpSftpFalsch")
        r = c.post("/api/profile/speicher", json={"name": "SSH", "kind": "sftp", "url": SURL, "user": "spark", "password": "nein"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("Anmeldung", r.json()["detail"])
        tid = self.add_sftp(c)
        SFTP["down"] = True
        last = run(speicher.copy_once(uid, tid))
        self.assertEqual((last["ok"], last["kind"]), (False, "offline"))
        SFTP["down"] = False
        SFTP["pw"] = "geaendert"
        self.write(uid, "memory.json", "{}")
        last = run(speicher.copy_once(uid, tid))
        self.assertEqual((last["ok"], last["kind"]), (False, "auth"))

    def test_another_server_key_stops_everything_until_accepted(self):
        c, uid = self.ready("SpSftpKey")
        tid = self.add_sftp(c)
        old = SFTP["key"]
        SFTP["key"] = paramiko.ECDSAKey.generate()
        try:
            self.write(uid, "memory.json", json.dumps({"x": SECRET_WORD}))
            last = run(speicher.copy_once(uid, tid))
            self.assertEqual((last["ok"], last["kind"]), (False, "hostkey"))
            self.assertFalse(any("/o/" in k for k in sftp_objects()))      # nothing went to the other server
            # accepting needs the password (and the code, stufen.py)
            r = c.put(f"/api/profile/speicher/{tid}", json={"url": SURL, "user": "spark", "accept_key": True})
            self.assertEqual(r.status_code, 400)
            r = c.put(f"/api/profile/speicher/{tid}", json={"url": SURL, "user": "spark", "accept_key": True,
                                                         "password": "ssh-pass-4711"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(speicher.find(uid, tid)["hostkey"], speicher.hostkey_of(SFTP["key"]))
            self.assertTrue(run(speicher.copy_once(uid, tid))["ok"])
        finally:
            SFTP["key"] = old

    def test_watched_by_the_dienst_waechter(self):
        c, uid = self.ready("SpSftpWacht")
        self.add_sftp(c)
        p = next(p for p in speicher.probes().values() if uid in p["uids"])
        self.assertEqual((p["tcp"], p["ssh"], p["port"]), (True, True, SPORT))
        self.assertTrue(run(dienstwacht.probe("store", "x", p, {})).ok)
        SFTP["down"] = True
        try:
            self.assertFalse(run(dienstwacht.probe("store", "x", dict(p, port=helpers._port()), {})).ok)
        finally:
            SFTP["down"] = False

    def test_addresses(self):
        self.assertEqual(speicher.check_url("sftp://nas.fritz.box/volume1/spark/", "sftp"), "sftp://nas.fritz.box/volume1/spark")
        self.assertEqual(speicher.check_url("sftp://server.example.org:2222/home/a", "sftp"), "sftp://server.example.org:2222/home/a")
        self.assertEqual(speicher.check_url("smb://192.168.178.20/daten/spark", "smb"), "smb://192.168.178.20/daten/spark")
        for url, kind in (("smb://nas.example.com/daten", "smb"), ("smb://nas.fritz.box", "smb"), ("smb://nas.fritz.box/", "smb"),
                          ("https://nas.fritz.box/x", "sftp"), ("sftp://u@nas/x", "sftp"), ("sftp://nas/a/../b", "sftp"),
                          ("sftp://nas/a%2f..", "sftp"), ("smb://nas/da*ten", "smb"), ("sftp://nas/x", "webdav")):
            with self.assertRaises(ValueError, msg=url):
                speicher.check_url(url, kind)


class SmbTarget(Base):
    """SMB through smbclient, with the share faked on a temp folder: the connection goes to the checked address,
    only encrypted, its own connection cache, closed after the run."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp(prefix="spark-smb-")
        self.calls = []
        import smbclient
        from smbprotocol import exceptions as x
        test = self

        def local(p):
            self.assertTrue(p.startswith("\\\\127.0.0.1\\daten\\"), p)
            return os.path.join(self.root, *p.split("\\")[4:])

        def register_session(server, **kw):
            test.calls.append(("session", server, kw.get("encrypt"), kw.get("port"), kw.get("connection_cache") is not None))
            if kw.get("password") != "smb-pass-4711":
                raise x.SMBAuthenticationError("logon failure")

        def stat_(p, **kw):
            return os.stat(local(p))

        def mkdir(p, **kw):
            os.mkdir(local(p))

        def open_file(p, mode="rb", **kw):
            return open(local(p), mode)

        def replace(a, b, **kw):
            os.replace(local(a), local(b))

        def remove(p, **kw):
            os.remove(local(p))

        def reset(connection_cache=None):
            test.calls.append(("reset", connection_cache is not None))
        self.patches = [mock.patch.object(smbclient, n, f) for n, f in (
            ("register_session", register_session), ("stat", stat_), ("mkdir", mkdir), ("open_file", open_file),
            ("replace", replace), ("remove", remove), ("reset_connection_cache", reset))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def test_copy_and_restore_only_encrypted_and_only_at_home(self):
        c, uid = self.ready("SpSmb")
        r = c.post("/api/profile/speicher", json={"name": "Win", "kind": "smb", "url": "smb://127.0.0.1/daten/spark",
                                                  "user": "spark", "password": "falsch"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("Anmeldung", r.json()["detail"])
        r = c.post("/api/profile/speicher", json={"name": "Win", "kind": "smb", "url": "smb://127.0.0.1/daten/spark",
                                                  "user": "spark", "password": "smb-pass-4711"})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()["added"]
        self.assertIn(("session", "127.0.0.1", True, 445, True), self.calls)
        self.assertIn(("reset", True), self.calls)
        self.write(uid, "memory.json", json.dumps({"x": SECRET_WORD}))
        self.assertTrue(run(speicher.copy_once(uid, tid))["ok"])
        stored = []
        for d, _, fs in os.walk(self.root):
            for f in fs:
                with open(os.path.join(d, f), "rb") as x:
                    stored.append((f, x.read()))
        self.assertTrue(any(f == "manifest.enc" for f, _ in stored))
        self.assertFalse(any(SECRET_WORD.encode() in v for _, v in stored))
        os.remove(profiles._path(uid, "memory.json"))
        self.assertEqual(run(speicher.restore_missing(uid, tid))["n"], 1)
        # never over the internet, and the home network only with its switch
        r = c.post("/api/profile/speicher", json={"name": "Weg", "kind": "smb", "url": "smb://files.example.com/daten",
                                                  "user": "spark", "password": "smb-pass-4711"})
        self.assertEqual(r.status_code, 400)
        p = next(p for p in speicher.probes().values() if uid in p["uids"])
        self.assertEqual((p["tcp"], p["ssh"], p["port"]), (True, False, 445))


class Packages(unittest.TestCase):
    def test_extra_lock_matches_the_main_lock(self):
        """requirements-speicher.lock (for an environment made before the lock file) holds exactly the SFTP and SMB
        packages, with the same versions and hashes as requirements-panel.lock."""
        import re

        def blocks(name):
            with open(os.path.join(helpers.APP, name)) as f:
                text = f.read()
            out = {}
            for b in re.split(r"\n(?=[a-z0-9])", text):
                m = re.match(r"([a-z0-9_.\-]+)==(\S+)", b)
                if m:
                    out[m.group(1)] = (m.group(2), sorted(re.findall(r"sha256:([0-9a-f]{64})", b)))
            return out
        extra, main = blocks("requirements-speicher.lock"), blocks("requirements-panel.lock")
        self.assertEqual(set(extra), {"bcrypt", "invoke", "paramiko", "pynacl", "pyspnego", "smbprotocol"})
        for k, v in extra.items():
            self.assertEqual(v, main[k], k)
            self.assertTrue(v[1], k)
