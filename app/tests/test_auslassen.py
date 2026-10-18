"""Ordner auslassen (auslassen.py, plan plaene/ordner-auslassen.md, Stufe A) against the fake WebDAV NAS of
test_nasquelle. One self-test per rule: a folder on the list is never read and what was read from it leaves the
search at once (documents.on_gone), nothing changes at the place; letting it in again reads it anew; name rules count
everywhere, case-blind, "*" only at the end; the tree marks what is left out; only the profile's own places, guests
never, a blocked profile keeps seeing and changing its list; the old per-folder field moves to the list once; the
Haushaltsordner follows the list of the admin profile that chose it; logs carry no path, no name and no profile.
Stufe B: the reMarkable reads no notebook below a left-out folder and drops what it read from one; the Begleiter gets
the list with its config (the rev goes up), reports its sub folders for the tree, names the folder of each file, and
the panel refuses a file from a left-out folder. No test reads the clock."""
import contextlib
import io
import json
import unittest

from tests import helpers

helpers.start()
import auslassen  # noqa: E402
import documents  # noqa: E402
import logfilter  # noqa: E402
import nasquelle  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_nasquelle import DAV, Base, profile, run  # noqa: E402

VERTRAEGE = "/dav/Ablage/Vertraege"


class Folders(Base):
    def test_left_out_is_not_read_and_leaves_the_search_at_once(self):
        c, uid, nid, sid = self.ready("AuOrdner")
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(documents.count_source(uid, "nas"), 4)
        gone = []
        documents.GONE.append(lambda u, ids, why: gone.append((u, sorted(ids), why)))
        try:
            p = c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE, "probe": True}).json()
            self.assertEqual(p, {"docs": 3, "known": False})
            self.assertEqual(auslassen.load(uid)["folders"], [])            # a probe changes nothing
            r = c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
            self.assertEqual((r.status_code, r.json()["removed"]), (200, 3), r.text)
        finally:
            documents.GONE.pop()
        self.assertEqual(documents.count_source(uid, "nas"), 1)
        self.assertEqual([(u, len(ids), why) for u, ids, why in gone], [(uid, 3, "ausgelassen")])
        self.assertFalse(documents.search(uid, "Mietvertrag Frist gekuendigt"))
        self.assertIn("dav/Ablage/Vertraege/miete.txt", DAV["files"])        # never deleted at the place
        got = run(nasquelle.sync_once(uid, sid))
        self.assertEqual(got["new"], 0, got)                                 # not read again
        self.assertEqual(nasquelle.state(uid, sid)["out"].get("ausgelassen"), 1)
        self.assertEqual(documents.count_source(uid, "nas"), 1)
        self.assertEqual(c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE}).status_code, 409)

    def test_let_in_again_reads_it_anew(self):
        c, uid, nid, sid = self.ready("AuZulassen")
        run(nasquelle.sync_once(uid, sid))
        c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
        run(nasquelle.sync_once(uid, sid))
        r = c.delete("/api/profile/auslassen", params={"ort": nid, "path": VERTRAEGE})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(nasquelle.due(uid, nasquelle.find(uid, sid), nasquelle.state(uid, sid), now=10 ** 10))
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(documents.count_source(uid, "nas"), 4)
        self.assertEqual(c.delete("/api/profile/auslassen", params={"ort": nid, "path": VERTRAEGE}).status_code, 404)

    def test_the_tree_and_the_preview_show_it(self):
        c, uid, nid, sid = self.ready("AuBaum")
        c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
        d = c.get(f"/api/profile/nasquelle/tree?nas={nid}&path=/dav/Ablage").json()
        self.assertEqual((d["dirs"], d["out"]), (["Fotos", "Vertraege"], {"Vertraege": "ordner"}))
        p = c.post("/api/profile/nasquelle/preview", json={"nas": nid, "path": "/dav/Ablage"}).json()
        self.assertEqual((p["files"], p["out"].get("ausgelassen")), (2, 1))   # falsch.pdf, Zebra.txt
        v = c.get("/api/profile/auslassen").json()
        self.assertEqual([(f["ort"], f["path"], f["place"]) for f in v["folders"]], [(nid, VERTRAEGE, "Keller")])
        self.assertEqual([(s["id"], s["path"]) for s in v["sources"]], [(sid, "/dav/Ablage")])
        self.assertTrue(v["tree"])


class Names(Base):
    def test_rules_are_plain_names(self):
        for ok in ("Archiv", "Alt*", "Alte Schule", "2009-2015"):
            self.assertEqual(auslassen.clean_name(ok), ok)
        for bad in ("", " ", "a/b", "a\\b", "*Alt", "A*t", ".", "..", "*", "x" * 81, "a\nb"):
            with self.assertRaises(ValueError, msg=bad):
                auslassen.clean_name(bad)
        self.assertEqual(auslassen.name_hit(["archiv"], "ARCHIV"), "archiv")
        self.assertEqual(auslassen.name_hit(["Alt*"], "alte Rechnungen"), "Alt*")
        self.assertEqual(auslassen.name_hit(["Alt"], "Alte Rechnungen"), "")          # no "*": the whole name
        self.assertEqual(auslassen.name_hit(["Alt*"], "Halt"), "")
        d = {"folders": [], "names": ["Fotos"]}
        self.assertEqual(auslassen.why("u_x", "abcdef", "/a/fotos/b", d), "name")      # anywhere in the path
        self.assertEqual(auslassen.why("u_x", "abcdef", "/a/Fotoalbum", d), "")
        d = {"folders": [{"ort": "abcdef", "path": "/a/b", "t": 0}], "names": []}
        self.assertEqual(auslassen.why("u_x", "abcdef", "/a/b/c", d), "ordner")
        self.assertEqual(auslassen.why("u_x", "abcdef", "/a/bc", d), "")                # not a mere prefix
        self.assertEqual(auslassen.why("u_x", "fedcba", "/a/b", d), "")                 # another place
        self.assertEqual(auslassen.why(None, "abcdef", "/a/b", d), "")                  # no profile, no list

    def test_a_name_counts_everywhere(self):
        c, uid, nid, sid = self.ready("AuName")
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(c.post("/api/profile/auslassen", json={"name": "vertr*", "probe": True}).json()["docs"], 3)
        r = c.post("/api/profile/auslassen", json={"name": "vertr*"})
        self.assertEqual((r.status_code, r.json()["removed"]), (200, 3), r.text)
        self.assertEqual(c.post("/api/profile/auslassen", json={"name": "VERTR*"}).status_code, 409)
        self.assertEqual(c.post("/api/profile/auslassen", json={"name": "a/b"}).status_code, 400)
        d = c.get(f"/api/profile/nasquelle/tree?nas={nid}&path=/dav/Ablage").json()
        self.assertEqual(d["out"], {"Vertraege": "name"})
        self.assertEqual(c.delete("/api/profile/auslassen", params={"name": "Vertr*"}).status_code, 200)
        self.assertEqual(auslassen.load(uid)["names"], [])
        r = c.post("/api/profile/auslassen", json={"name": "Ablage"})      # the chosen folder itself: nothing is read
        self.assertEqual(r.json()["removed"], 1)
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(documents.count_source(uid, "nas"), 0)

    def test_at_most_fifty_names(self):
        c, uid = profile("AuViele")
        profiles._write(profiles._path(uid, auslassen.FILE), {"names": [f"n{i}" for i in range(auslassen.MAX_NAMES)]})
        r = c.post("/api/profile/auslassen", json={"name": "Einer zu viel"})
        self.assertEqual(r.status_code, 400, r.text)


class Rights(Base):
    def test_own_places_only_guests_never_blocked_keep_their_list(self):
        c, uid, nid, sid = self.ready("AuRechte")
        other, ouid = profile("AuFremd")
        self.assertEqual(other.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE}).status_code, 404)
        for bad in ({"ort": nid, "path": "/dav/../etc"}, {"ort": nid, "path": "/"}, {"ort": "zz", "path": "/a"}, {}):
            self.assertEqual(c.post("/api/profile/auslassen", json=bad).status_code, 400, bad)
        helpers.set_config(public=True)
        try:
            g = TestClient(panel.app)
            for r in (g.get("/api/profile/auslassen"), g.post("/api/profile/auslassen", json={"name": "x"}),
                      g.delete("/api/profile/auslassen", params={"name": "x"})):
                self.assertIn(r.status_code, (401, 403))
        finally:
            helpers.set_config(public=False)
        c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
        helpers.set_config(deny={"nasquelle": [uid]})
        v = c.get("/api/profile/auslassen").json()
        self.assertEqual((len(v["folders"]), v["tree"]), (1, False))                  # own data stays visible
        self.assertEqual(c.delete("/api/profile/auslassen", params={"ort": nid, "path": VERTRAEGE}).status_code, 200)

    def test_the_old_field_moves_to_the_list_once(self):
        c, uid, nid, sid = self.ready("AuUmzug")
        with open(nasquelle._file(uid)) as f:
            raw = json.load(f)
        raw["sources"][0]["skip"] = ["Vertraege", "../boese"]
        profiles._write(nasquelle._file(uid), raw)
        self.assertEqual([s["id"] for s in nasquelle.sources(uid)], [sid])
        self.assertEqual([(f["ort"], f["path"]) for f in auslassen.load(uid)["folders"]], [(nid, VERTRAEGE)])
        with open(nasquelle._file(uid)) as f:
            self.assertNotIn("skip", json.load(f)["sources"][0])
        self.assertNotIn("skip", c.get("/api/profile/nasquelle").json()["sources"][0])
        run(nasquelle.sync_once(uid, sid))
        self.assertEqual(documents.count_source(uid, "nas"), 1)

    def test_logs_without_paths_names_or_profiles(self):
        c, uid, nid, sid = self.ready("AuLogZebra")
        run(nasquelle.sync_once(uid, sid))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE, "probe": True})
            c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
            c.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
            c.post("/api/profile/auslassen", json={"name": "Geheimname"})
            c.delete("/api/profile/auslassen", params={"name": "Geheimname"})
            c.delete("/api/profile/auslassen", params={"name": "Geheimname"})
            c.delete("/api/profile/auslassen", params={"ort": nid, "path": VERTRAEGE})
        lines = [x for x in out.getvalue().splitlines() if x.startswith("auslassen:")]
        for want in ("probe | ordner | 3 dokumente", "ausgelassen | ordner | 3 dokumente raus", "schon da | ordner",
                     "ausgelassen | name | 0 dokumente raus", "zugelassen | name", "zulassen | name | nicht gefunden",
                     "zugelassen | ordner"):
            self.assertTrue(any(want in x for x in lines), (want, lines))
        for word in ("Vertraege", "Geheimname", "AuLogZebra", uid, "Ablage", nid):
            self.assertNotIn(word, out.getvalue())
        self.assertTrue(all(logfilter.parse(x)["area"] == "wissen" for x in lines), lines)


class Haushalt(Base):
    """The Haushaltsordner an admin profile chose follows that profile's list."""
    def setUp(self):
        super().setUp()
        import notaus
        self._old = notaus.admin_uids
        self._admins = []
        notaus.admin_uids = lambda: list(self._admins)
        helpers.set_config(nas_shared=True)

    def tearDown(self):
        import notaus
        notaus.admin_uids = self._old
        for s in nasquelle.sources(nasquelle.HAUS):
            nasquelle.remove_source(nasquelle.HAUS, s["id"])
        helpers.set_config(nas_shared=False)
        super().tearDown()

    def test_the_admin_profiles_list_counts(self):
        a, auid = profile("AuHausAdmin")
        self._admins.append(auid)
        nid = self.place(a)
        sid = a.post("/api/profile/nasquelle", json={"nas": nid, "path": "/dav/Ablage", "haus": True}).json()["added"]
        run(nasquelle.sync_once(nasquelle.HAUS, sid))
        self.assertEqual(documents.count_source(nasquelle.HAUS, "nas"), 4)
        v = a.get("/api/profile/auslassen").json()
        self.assertEqual([(s["id"], s["haus"]) for s in v["sources"]], [(sid, True)])
        r = a.post("/api/profile/auslassen", json={"ort": nid, "path": VERTRAEGE})
        self.assertEqual(r.json()["removed"], 3, r.text)
        self.assertEqual(documents.count_source(nasquelle.HAUS, "nas"), 1)
        run(nasquelle.sync_once(nasquelle.HAUS, sid))
        self.assertEqual(documents.count_source(nasquelle.HAUS, "nas"), 1)


class Remarkable(Base):
    ITEMS = {"f": {"name": "Arbeit", "parent": "", "folder": True},
             "g": {"name": "Alt", "parent": "f", "folder": True},
             "a": {"name": "Plan", "parent": "f", "folder": False, "kind": "notebook"},
             "b": {"name": "Notiz 2019", "parent": "g", "folder": False, "kind": "notebook"},
             "c": {"name": "Lose", "parent": "", "folder": False, "kind": "notebook"}}

    def test_no_notebook_below_a_left_out_folder(self):
        import remarkable
        _, uid = profile("AuRm")
        d = {"picked": ["f", "c"], "all": False, "docs": {}}
        self.assertEqual(sorted(remarkable.wanted(uid, self.ITEMS, d)), ["a", "b", "c"])
        auslassen.add_folders(uid, [("rm", "/Arbeit/Alt")])
        self.assertEqual(sorted(remarkable.wanted(uid, self.ITEMS, d)), ["a", "c"])
        self.assertEqual(sorted(remarkable.wanted(uid, self.ITEMS, dict(d, picked=["b"]))), [])   # the list wins
        with auslassen._lock:
            auslassen._save(uid, {"folders": [], "names": ["arb*"]})
        self.assertEqual(sorted(remarkable.wanted(uid, self.ITEMS, dict(d, all=True))), ["c"])

    def test_what_was_read_leaves_at_once(self):
        import remarkable
        c, uid = profile("AuRmWeg")
        remarkable._save_library(uid, self.ITEMS)
        doc = documents.add(uid, "Notiz 2019.txt", b"Steuer Notiz von damals", source="remarkable")
        remarkable.save(uid, {"picked": ["f"], "all": False, "docs": {"b": {"doc": doc["id"], "h": "x"}}})
        p = c.post("/api/profile/auslassen", json={"ort": "rm", "path": "/Arbeit/Alt", "probe": True}).json()
        self.assertEqual(p["docs"], 1)
        r = c.post("/api/profile/auslassen", json={"ort": "rm", "path": "/Arbeit/Alt"})
        self.assertEqual((r.status_code, r.json()["removed"]), (200, 1), r.text)
        self.assertFalse(documents.has_doc(uid, doc["id"]))
        self.assertEqual(remarkable.load(uid)["docs"], {})
        self.assertEqual(remarkable.load(uid)["picked"], ["f"])               # nothing changes at the reMarkable
        self.assertEqual(c.get("/api/profile/auslassen/tree?ort=rm&path=/").status_code, 403)   # not connected


class Desk(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(desk=True)
        import guard
        for k in [k for k in guard._rate if k[0] in ("desk", "deskfile", "deskapps", "pair")]:
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(desk=False)
        super().tearDown()

    def program(self, name):
        c, uid = profile(name)
        r = c.post("/api/profile/desk/pair", json={"base": "http://192.168.178.171:31080"})
        self.assertEqual(r.status_code, 200, r.text)
        prog = TestClient(panel.app, client=("192.168.178.20", 50000))
        r2 = prog.post("/api/desk/pair", json={"code": r.json()["code"], "name": "Laptop", "kind": "mac"})
        self.assertEqual(r2.status_code, 200, r2.text)
        prog.headers[profiles.DEVICE_HEADER] = r2.json()["key"]
        did = c.get("/api/profile/desk").json()["devices"][0]["id"]
        cfg = prog.get("/api/desk/config").json()
        r = c.put(f"/api/profile/desk/devices/{did}", json={"cfg": {"parts": dict(cfg["parts"], folder=True)}})
        self.assertEqual(r.status_code, 200, r.text)
        return c, uid, prog

    def send(self, prog, name, text, **data):
        return prog.post("/api/desk/file", files={"file": (name, text.encode(), "text/plain")}, data=dict(what="wissen", **data))

    def test_the_program_gets_the_list_and_the_panel_refuses_too(self):
        c, uid, prog = self.program("AuDesk")
        cfg = prog.get("/api/desk/config").json()
        self.assertEqual(cfg["auslassen"], {"names": [], "folders": []})
        self.assertEqual(self.send(prog, "plan.txt", "Projektplan Brücke", ordner="Projekte/Alt").status_code, 200)
        self.assertEqual(self.send(prog, "lies.txt", "Lies mich zuerst", ordner="/").status_code, 200)
        places = {d["name"]: d.get("place") for d in documents.list_docs(uid) if d["source"] == "begleiter"}
        self.assertEqual(places, {"plan.txt": "/Projekte/Alt", "lies.txt": "/"})
        r = c.post("/api/profile/auslassen", json={"ort": "pc", "path": "/Projekte/Alt"})
        self.assertEqual((r.status_code, r.json()["removed"]), (200, 1), r.text)
        self.assertEqual([d["name"] for d in documents.list_docs(uid) if d["source"] == "begleiter"], ["lies.txt"])
        cfg2 = prog.get("/api/desk/config").json()
        self.assertEqual(cfg2["auslassen"], {"names": [], "folders": ["Projekte/Alt"]})
        self.assertGreater(cfg2["rev"], cfg["rev"])                          # the program hears of it with the next poll
        self.assertEqual(self.send(prog, "plan.txt", "Projektplan", ordner="Projekte/Alt/2019").status_code, 409)
        self.assertEqual(self.send(prog, "x.txt", "x", ordner="../etc").status_code, 400)
        c.post("/api/profile/auslassen", json={"name": "Entwurf*"})
        self.assertEqual(self.send(prog, "e.txt", "Entwurf", ordner="/Briefe/entwurf 2").status_code, 409)
        self.assertEqual(self.send(prog, "r.txt", "Rechtsklick ohne Ordner").status_code, 200)   # right-click: no folder

    def test_an_older_send_without_folder_is_replaced(self):
        _, uid, prog = self.program("AuDeskAlt")
        self.assertEqual(self.send(prog, "notiz.txt", "Erste Fassung").status_code, 200)        # program before V01.0.777
        self.assertEqual(self.send(prog, "notiz.txt", "Erste Fassung", ordner="/Ablage").status_code, 200)
        self.assertEqual(self.send(prog, "notiz.txt", "Andere Datei", ordner="/").status_code, 200)
        got = sorted(d.get("place") for d in documents.list_docs(uid) if d["name"] == "notiz.txt")
        self.assertEqual(got, ["/", "/Ablage"])

    def test_sub_folders_for_the_tree(self):
        c, uid, prog = self.program("AuDeskBaum")
        self.assertEqual([s["nas"] for s in c.get("/api/profile/auslassen").json()["sources"]], [])
        r = prog.post("/api/desk/ordner", json={"dirs": ["Projekte", "Projekte/Alt", "../x", 7, "Fotos"]})
        self.assertEqual((r.status_code, r.json()), (200, {"dirs": 3}), r.text)
        self.assertEqual(prog.post("/api/desk/ordner", json={"dirs": "Projekte"}).status_code, 400)
        v = c.get("/api/profile/auslassen").json()
        self.assertEqual([(s["nas"], s["place"]) for s in v["sources"]], [("pc", "PC · Spark-Wissen")])
        c.post("/api/profile/auslassen", json={"ort": "pc", "path": "/Projekte/Alt"})
        d = c.get("/api/profile/auslassen/tree?ort=pc&path=/Projekte").json()
        self.assertEqual((d["dirs"], d["out"]), (["Alt"], {"Alt": "ordner"}))
        self.assertEqual(c.get("/api/profile/auslassen/tree?ort=pc&path=/../x").status_code, 400)
        self.assertEqual(c.get("/api/profile/auslassen/tree?ort=zz").status_code, 400)
        guest = TestClient(panel.app, client=("192.168.178.20", 50000))
        self.assertIn(guest.get("/api/profile/auslassen/tree?ort=pc").status_code, (401, 403))
        self.assertIn(prog.get("/api/profile/auslassen").status_code, (401, 403))   # the program's key: not the list


if __name__ == "__main__":
    unittest.main()
