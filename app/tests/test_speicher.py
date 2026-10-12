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
            self.assertTrue(all(p["url"] == f"http://127.0.0.1:{PORT}/" for p in act["store"].values()))
            self.assertNotIn("password", json.dumps(act["store"]))
        finally:
            helpers.set_config(svc_watch=False)
        # the profile switch off: no probe for its targets
        c.put("/api/profile/settings", json={"storage_on": False})
        self.assertFalse(any(uid in p["uids"] for p in speicher.probes().values()))


if __name__ == "__main__":
    unittest.main()


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
