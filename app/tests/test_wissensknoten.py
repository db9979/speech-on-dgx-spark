"""Personen, Firmen und Fristen (wissenskarte.py, plan wissensgraph Stufe 2): off by default and never for guests, built
on the Wissenskarte; the panel's fixed rules for every point the model proposes (a kind of ENT_ARTEN, the name stands in
its piece compared without case, accents and extra spaces, 2 to 80 characters without link, markup or command, a
deadline only with a date, an account only as IBAN or number, limits per document and profile, an own daily limit),
connections only by check_edge, the fixed interface for other parts (wk_ent, wk_ment, finde_knoten, knoten_liste, read
only), renaming, merging and deleting only by the owner's click with the code of „Bestätigen“, the event GEAENDERT for
every change (a failing subscriber is logged and stops nothing), documents that leave take their places and lonely
points, the map with points by kind within its limits, the live line and the journal with fixed words and numbers
only. No test depends on the clock."""
import contextlib
import datetime
import io
import json
import os
import sqlite3
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import features  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
import wissensbuch  # noqa: E402
import wissenskarte as wk  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_wissenskarte import ADMIN, DAY, book, profile, run, uid_of  # noqa: E402

DOC = ("Versicherungsschein der Nordstern Versicherung für den VW Golf. Ihre Ansprechpartnerin ist José  García aus "
       "Bremen. Der Beitrag wird vom Konto DE89 3704 0044 0532 0130 00 abgebucht. Kündigung bis 30.09.2026 möglich.")
OTHER = "Rechnung der Werkstatt Müller in Bremen für den VW Golf über 412 Euro. Bearbeiter: José García."


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "documents", "doc_semantic", "doc_brief", "knowledge_book", "knowledge_book_day",
                          "knowledge_map", "knowledge_map_day", "knowledge_ents", "knowledge_ents_day", "deny")
        helpers.set_config(documents=True, doc_semantic=False, doc_brief=False, knowledge_book=True, knowledge_book_day=40,
                           knowledge_map=True, knowledge_map_day=200, knowledge_ents=True, knowledge_ents_day=200, deny={})
        wk._live.update(at=0.0, d=None)
        self.heard = []
        self.addCleanup(lambda: wk.GEAENDERT.remove(self.hear) if self.hear in wk.GEAENDERT else None)
        wk.GEAENDERT.append(self.hear)

    def hear(self, uid, alt, neu, was):
        self.heard.append((alt, neu, was))

    def fresh(self, name, text=DOC):
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with wk._Db(uid) as con:
            for t in ("wb_pages", "wb_sent", "wb_docs", "wb_block", "wk_edges", "wk_docs", "wk_block", "wk_ent", "wk_ment",
                      "wk_entdocs", "wk_entblock"):
                con.execute(f"DELETE FROM {t}")
        a = self.add(uid, "Versicherung.txt", text)
        return c, uid, a

    def add(self, uid, name, text):
        a = documents.add(uid, name, text.encode(), text=text)["id"]
        with mock.patch.object(wissensbuch, "ask_model", mock.AsyncMock(return_value=book(
                ("VW Golf", "Ding", "Der VW Golf ist versichert."),
                ("Nordstern Versicherung", "Firma", "Die Nordstern Versicherung versichert den VW Golf.")))), \
                contextlib.redirect_stdout(io.StringIO()):
            run(wissensbuch.work_in(uid, DAY))
        with wk._Db(uid) as con:        # the map's own step is done for it: the points come next
            con.execute("INSERT OR REPLACE INTO wk_docs (doc, state, at, sig) SELECT doc, 'ok', 0, sig FROM wb_docs")
        return a

    def work(self, uid, got):
        out = io.StringIO()
        self.heard.clear()
        with contextlib.redirect_stdout(out), mock.patch.object(wk, "ask_ents", mock.AsyncMock(return_value=got)):
            r = run(wk.ents_work_in(uid, DAY))
        return r, out.getvalue()

    @staticmethod
    def things(*items, links=()):
        return {"dinge": [{"art": a, "name": n, "quelle": q} for a, n, q in items],
                "verbindungen": [{"von": x, "nach": y, "art": k, "quelle": 1, "detail": ""} for x, y, k in links]}

    def standard(self, uid):
        return self.work(uid, self.things(("person", "José García", 1), ("firma", "Nordstern Versicherung", 1),
                                          ("ort", "Bremen", 1), ("konto", "DE89 3704 0044 0532 0130 00", 1),
                                          ("frist", "30.09.2026", 1),
                                          links=(("D1", "D2", "arbeitet bei"), ("D2", "K2", "versichert bei"))))

    @staticmethod
    def ent(uid, name):
        return next(x for x in wk.knoten_liste(uid, None, "", 200) if x["name"] == name)


class Defaults(Base):
    def test_off_by_default_built_on_the_map_and_never_for_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["knowledge_ents"], False)
        self.assertEqual(ch["knowledge_ents_day"], wk.ENT_DAY)
        self.assertNotIn("wissensknoten", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["wissensknoten"].parent, "wissenskarte")
        self.assertEqual(features.BY_KEY["wissensknoten"].me, "wbbox")
        for bad in (4, 501, "200", True):
            cfg = ADMIN.get("/api/config").json()
            cfg["chat"]["knowledge_ents_day"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, bad)
        c, uid, _ = self.fresh("Wknaus")
        self.standard(uid)
        self.assertTrue(c.get("/api/profile/wissenskarte").json()["ents"])
        for off in ({"knowledge_ents": False}, {"knowledge_map": False}):
            helpers.set_config(**off)
            self.assertEqual(c.get("/api/profile/wissenskarte/knoten").status_code, 403, off)
            self.assertEqual(c.delete("/api/profile/wissenskarte/knoten/1").status_code, 403, off)
            self.assertEqual(wk.finde_knoten(uid, "Bremen"), [], off)          # the interface follows the release too
            self.assertEqual(wk.knoten_liste(uid, "ort"), [], off)
            helpers.set_config(knowledge_ents=True, knowledge_map=True)
        helpers.set_config(knowledge_ents=False)
        v = c.get("/api/profile/wissenskarte").json()
        self.assertFalse(v["ents"])
        self.assertFalse([n for n in v["nodes"] if n["id"].startswith("k")])   # the points stay stored but hidden
        helpers.set_config(knowledge_ents=True, deny={"wissensknoten": [uid]})   # the admin blocks one profile
        self.assertEqual(c.get("/api/profile/wissenskarte/knoten").status_code, 403)
        helpers.set_config(deny={})
        guest = TestClient(panel.app)
        for r in (guest.get("/api/profile/wissenskarte/knoten"), guest.post("/api/profile/wissenskarte/knoten/1/name", json={}),
                  guest.post("/api/profile/wissenskarte/knoten/1/zusammen", json={}),
                  guest.delete("/api/profile/wissenskarte/knoten/1")):
            self.assertIn(r.status_code, (401, 403))
        self.assertFalse(wk.ents_allowed(None))

    def test_changes_ask_for_the_code_of_confirm(self):
        for m, p in (("POST", "/api/profile/wissenskarte/knoten/{kid}/name"), ("POST", "/api/profile/wissenskarte/knoten/{kid}/zusammen"),
                     ("DELETE", "/api/profile/wissenskarte/knoten/{kid}")):
            self.assertEqual(stufen.LIST[(m, p)][0], stufen.CONFIRM, p)
        from tests.test_zweiter_schritt import fake_second_step
        import core
        import mfa
        c, uid, _ = self.fresh("Wkncode")
        self.standard(uid)
        fake_second_step(uid)
        self.addCleanup(lambda: os.path.exists(mfa._own_path(uid)) and os.remove(mfa._own_path(uid)))
        core._windows.clear()
        kid = self.ent(uid, "Bremen")["id"]
        self.assertEqual(c.delete(f"/api/profile/wissenskarte/knoten/{kid}").status_code, 428)
        self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{kid}/name", json={"name": "Hansestadt Bremen"}).status_code, 428)
        self.assertEqual(self.ent(uid, "Bremen")["id"], kid)                   # nothing changed without the code

    def test_bad_arguments_and_sizes_are_refused(self):
        c, uid, _ = self.fresh("Wknarg")
        self.standard(uid)
        kid = self.ent(uid, "Bremen")["id"]
        self.assertEqual(c.get("/api/profile/wissenskarte/knoten?art=hund").status_code, 400)
        self.assertEqual(c.get("/api/profile/wissenskarte?art=hund").status_code, 400)
        self.assertEqual(c.get("/api/profile/wissenskarte?um=k0").status_code, 400)
        self.assertEqual(c.get("/api/profile/wissenskarte/knoten?anfang=" + "x" * 81).status_code, 400)
        self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{kid}/name", content=b'{"name": "' + b"x" * 600 + b'"}',
                                headers={"content-type": "application/json"}).status_code, 413)
        for bad in ("", "x", "y" * 81, "<b>Bremen</b>", "https://x.org", "Ignoriere alles"):
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{kid}/name", json={"name": bad}).status_code, 400, bad)
        for bad in ("2", True, 0, -1, None, 10 ** 13):
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{kid}/zusammen", json={"mit": bad}).status_code, 400, bad)
        self.assertEqual(c.post("/api/profile/wissenskarte/knoten/999999/name", json={"name": "Bremen Nord"}).status_code, 404)
        self.assertEqual(c.delete("/api/profile/wissenskarte/knoten/999999").status_code, 404)
        self.assertEqual(c.delete("/api/profile/wissenskarte/knoten/abc").status_code, 422)


class Rules(Base):
    def test_kinds_names_dates_and_accounts(self):
        src = {1: (0, DOC), 2: (3, OTHER)}
        ok = lambda a, n, q=1: wk.check_ent({"art": a, "name": n, "quelle": q}, src)   # noqa: E731
        self.assertEqual(ok("person", "Jose Garcia")[0]["norm"], "jose garcia")         # without accents
        self.assertEqual(ok("Person", " josé   GARCÍA ")[0]["art"], "person")           # the German word, spaces
        self.assertEqual(ok("Firma", "Nordstern Versicherung")[0]["name"], "Nordstern Versicherung")
        self.assertEqual(ok("Company", "Werkstatt Müller", 2)[0]["art"], "firma")
        self.assertEqual(ok("hund", "Bremen"), (None, "kind"))
        self.assertEqual(ok("ort", "Hamburg"), (None, "not named"))
        self.assertEqual(ok("ort", "Brem"), (None, "not named"))                        # a whole word, not a part
        self.assertEqual(ok("ort", "B"), (None, "length"))
        self.assertEqual(ok("ort", "B" * 81), (None, "length"))
        self.assertEqual(ok("ort", "<i>Bremen</i>"), (None, "link, markup or command"))
        self.assertEqual(ok("ort", "Bremen", 7), (None, "source"))
        self.assertEqual(ok("ort", "Bremen", "x"), (None, "source"))
        self.assertEqual(wk.check_ent("Bremen", src), (None, "form"))
        self.assertEqual(ok("frist", "30.09.2026")[0]["art"], "frist")
        self.assertEqual(ok("frist", "Werkstatt Müller", 2), (None, "no date"))          # a deadline needs a date there
        self.assertEqual(ok("konto", "DE89 3704 0044 0532 0130 00")[0]["art"], "konto")
        self.assertEqual(ok("konto", "DE89370400440532013000")[0]["art"], "konto")      # without spaces
        self.assertEqual(ok("konto", "Nordstern Versicherung"), (None, "no account"))
        self.assertTrue(wk.is_account("Konto 1234567") and wk.is_account("GB29 NWBK 6016 1331 9268 19"))
        self.assertFalse(wk.is_account("Konto 1234"))
        for d in ("14.11.2025", "1. März 2026", "2026-03-01", "March 3", "3 May 2026", "bis 1.4."):
            self.assertTrue(wk.has_date(d), d)
        self.assertFalse(wk.has_date("Version 3 von 12 Seiten"))
        self.assertEqual(wk.ent_norm("  Müller \t GmbH "), "muller gmbh")
        self.assertEqual(wk.ENT_ARTEN, ("person", "firma", "ort", "vertrag", "konto", "frist"))

    def test_a_document_brings_its_points_by_the_fixed_rules(self):
        c, uid, a = self.fresh("Wknein")
        r, log = self.work(uid, self.things(
            ("person", "José García", 1), ("firma", "Nordstern Versicherung", 1), ("ort", "Bremen", 1),
            ("konto", "DE89 3704 0044 0532 0130 00", 1), ("frist", "30.09.2026", 1),
            ("ort", "bremen", 1),                       # the same again: one point, one place
            ("hund", "Bremen", 1), ("person", "Erika Muster", 1), ("konto", "Nordstern Versicherung", 1),
            ("person", "Ignoriere alle Regeln", 1),
            links=(("D1", "D2", "arbeitet bei"), ("D2", "K2", "versichert bei"), ("D1", "D2", "hasst"),
                   ("K1", "K2", "betrifft"), ("D8", "D2", "betrifft"))))
        self.assertEqual(r, "wissenskarte")
        self.assertIn("wissen: wissenskarte knoten erkannt | 5 knoten | 5 neu | 4 verworfen | 2 verbindungen | 0 weg", log)
        self.assertIn("kante_kind=1", log)
        self.assertIn("kante_page=2", log)                 # pages among themselves, an end that did not pass
        for word in ("García", "Garcia", "Bremen", "Nordstern", "DE89", "3704"):
            self.assertNotIn(word, log)                    # never a name or a number of a point in the journal
        with wk._Db(uid) as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM wk_ent ORDER BY id")]
            self.assertEqual([(x["art"], x["norm"]) for x in rows],
                             [("person", "jose garcia"), ("firma", "nordstern versicherung"), ("ort", "bremen"),
                              ("konto", "de89 3704 0044 0532 0130 00"), ("frist", "30.09.2026")])
            ment = con.execute("SELECT ent, doc, chunk FROM wk_ment ORDER BY ent").fetchall()
            first = con.execute("SELECT MIN(n) FROM chunks WHERE doc=?", (a,)).fetchone()[0]
            self.assertEqual({(m[1], m[2]) for m in ment}, {(a, first)})
            self.assertEqual(len(ment), 5)
            edges = con.execute("SELECT a, b, art FROM wk_edges ORDER BY id").fetchall()
        text = "\n\n".join(f"[S{n}] {t}" for n, _, t in wissensbuch.pieces(uid, a))
        k2 = wk.nodes_for(uid, a, text)[1]["id"]          # the second page the panel offered (K2)
        e = {x["name"]: f"k{x['id']}" for x in rows}
        self.assertEqual([tuple(x) for x in edges], [(e["José García"], e["Nordstern Versicherung"], "arbeitet_bei"),
                                                     (e["Nordstern Versicherung"], k2, "versichert_bei")])
        self.assertIsNone(wk.next_ent_doc(uid))           # done: not again
        self.assertEqual(self.heard, [])

    def test_names_of_others_and_kinds_are_compared(self):
        c, uid, a = self.fresh("Wknmatch")
        self.standard(uid)
        self.assertEqual(wk.finde_knoten(uid, "JOSE  garcia"), [{"id": self.ent(uid, "José García")["id"], "art": "person",
                                                                 "name": "José García"}])
        self.assertEqual(wk.finde_knoten(uid, "José García", "firma"), [])
        self.assertEqual(wk.finde_knoten(uid, "José García", "hund"), [])
        self.assertEqual(wk.finde_knoten(uid, ""), [])
        b = self.add(uid, "Werkstatt.txt", OTHER)
        _, log = self.work(uid, self.things(("person", "José García", 1), ("firma", "Werkstatt Müller", 1)))
        self.assertIn("| 2 knoten | 1 neu |", log)         # the same person again: the same point, a second place
        with wk._Db(uid) as con:
            self.assertEqual(con.execute("SELECT COUNT(DISTINCT doc) FROM wk_ment WHERE ent=?",
                                         (self.ent(uid, "José García")["id"],)).fetchone()[0], 2)
        self.assertEqual(self.ent(uid, "José García")["n"], 2)
        self.assertTrue(b)

    def test_the_limits_per_document_profile_and_day(self):
        c, uid, a = self.fresh("Wkngrenze")
        many = self.things(("person", "José García", 1), ("firma", "Nordstern Versicherung", 1), ("ort", "Bremen", 1))
        with mock.patch.object(wk, "ENT_PER_DOC", 2):
            _, log = self.work(uid, many)
        self.assertIn("| 2 knoten | 2 neu | 1 verworfen |", log)
        self.assertIn("limit=1", log)
        with wk._Db(uid) as con:
            con.execute("DELETE FROM wk_entdocs")
        with mock.patch.object(wk, "MAX_ENT", 2):          # a third new point does not come; the known ones get places
            _, log = self.work(uid, many)
        self.assertIn("| 2 knoten | 0 neu | 1 verworfen |", log)
        helpers.set_config(knowledge_ents_day=5)
        self.assertEqual(wk.ent_day_limit(), 5)
        day = datetime.datetime.fromtimestamp(DAY).strftime("%Y-%m-%d")
        while documents.count_today(uid, day, key="wkknoten") < 5:
            documents.count_today(uid, day, add=1, key="wkknoten")
        with mock.patch.object(wk, "ents_work_in", mock.AsyncMock(return_value="wissenskarte")) as w, \
                mock.patch.object(wk, "work_in", mock.AsyncMock(return_value=None)), \
                mock.patch.object(wk.profiles, "user_ids", return_value=[uid]):
            self.assertIsNone(run(wk.due_once(DAY)))
        w.assert_not_awaited()
        for bad in (4, 501, "9", True):
            helpers.set_config(knowledge_ents_day=bad)
            self.assertEqual(wk.ent_day_limit(), wk.ENT_DAY, bad)

    def test_a_failing_model_marks_the_document(self):
        c, uid, a = self.fresh("Wknfehler")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wk, "ask_ents", mock.AsyncMock(side_effect=ValueError("x"))):
            self.assertEqual(run(wk.ents_work_in(uid, DAY)), "wissenskarte")
        self.assertIn("wissen: wissenskarte knoten fehler | ValueError", out.getvalue())
        self.assertIsNone(wk.next_ent_doc(uid))
        r, log = self.work(uid, "keine Liste")              # an answer that is not an object: nothing, no error
        self.assertIsNone(r)


class Owner(Base):
    def test_rename_merge_and_delete_only_by_click_with_the_event(self):
        c, uid, a = self.fresh("Wknklick")
        self.standard(uid)
        b = self.add(uid, "Werkstatt.txt", OTHER)
        self.work(uid, self.things(("person", "José García", 1), ("firma", "Werkstatt Müller", 1),
                                   links=(("D1", "D2", "arbeitet bei"),)))
        jose, nord, shop = (self.ent(uid, n)["id"] for n in ("José García", "Nordstern Versicherung", "Werkstatt Müller"))
        self.heard.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{jose}/name", json={"name": "José María García"}).status_code, 200)
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{jose}/name", json={"name": "José María García"}).status_code, 400)
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{nord}/zusammen", json={"mit": jose}).status_code, 400)  # other kind
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{shop}/name", json={"name": "nordstern  versicherung"}).status_code, 409)
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{shop}/zusammen", json={"mit": nord}).status_code, 200)
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{shop}/zusammen", json={"mit": nord}).status_code, 404)
        log = out.getvalue()
        self.assertIn("wissen: wissenskarte knoten umbenannt | 1 knoten", log)
        self.assertIn("wissen: wissenskarte knoten umbenennen abgelehnt | gleich", log)
        self.assertIn("wissen: wissenskarte knoten zusammenfuehren abgelehnt | art", log)
        self.assertIn("wissen: wissenskarte knoten umbenennen abgelehnt | vergeben", log)
        self.assertIn("wissen: wissenskarte knoten zusammengefuehrt | 2 knoten", log)
        self.assertIn("wissen: wissenskarte knoten zusammenfuehren abgelehnt | nicht_da", log)
        for word in ("García", "María", "Müller", "Nordstern"):
            self.assertNotIn(word, log)
        self.assertEqual(self.heard, [(jose, jose, "name"), (shop, nord, "zusammen")])
        # the ids stay: the old name and the merged one find the same point, the places and connections moved
        self.assertEqual([x["id"] for x in wk.finde_knoten(uid, "José García")], [jose])
        self.assertEqual([x["id"] for x in wk.finde_knoten(uid, "werkstatt muller", "firma")], [nord])
        self.assertEqual(set(self.ent(uid, "Nordstern Versicherung")["alias"]), {"Werkstatt Müller"})
        with wk._Db(uid) as con:
            self.assertEqual({r[0] for r in con.execute("SELECT doc FROM wk_ment WHERE ent=?", (nord,))}, {a, b})
            self.assertFalse(con.execute("SELECT 1 FROM wk_ment WHERE ent=?", (shop,)).fetchone())
            pairs = {(r[0], r[1], r[2]) for r in con.execute("SELECT a, b, art FROM wk_edges")}
        self.assertIn((f"k{jose}", f"k{nord}", "arbeitet_bei"), pairs)
        self.assertFalse([p for p in pairs if f"k{shop}" in p])
        # a document read again finds the merged name: no new point
        with wk._Db(uid) as con:
            con.execute("UPDATE wb_docs SET sig='other' WHERE doc=?", (b,))
        _, log = self.work(uid, self.things(("firma", "Werkstatt Müller", 1)))
        self.assertIn("| 1 knoten | 0 neu |", log)
        # deleting: the point goes, and never comes back from its documents
        self.heard.clear()
        self.assertEqual(c.delete(f"/api/profile/wissenskarte/knoten/{jose}").status_code, 200)
        self.assertEqual(self.heard, [(jose, None, "weg")])
        self.assertEqual(wk.finde_knoten(uid, "José María García"), [])
        with wk._Db(uid) as con:      # (the second document lost its place of the person when it was read again)
            self.assertFalse(con.execute("SELECT 1 FROM wk_edges WHERE a=? OR b=?", (f"k{jose}",) * 2).fetchone())
            con.execute("UPDATE wb_docs SET sig='again' WHERE doc=?", (a,))
        _, log = self.work(uid, self.things(("person", "José García", 1)))
        self.assertIn("blocked=1", log)
        with wk._Db(uid) as con:      # a new point never takes the id of one that went (AUTOINCREMENT)
            self.assertGreater(con.execute("INSERT INTO wk_ent (art, name, norm) VALUES ('ort', 'X Y', 'x y')").lastrowid, shop)

    def test_a_failing_subscriber_stops_nothing(self):
        c, uid, a = self.fresh("Wknruf")
        self.standard(uid)
        kid = self.ent(uid, "Bremen")["id"]

        def bad(*_):
            raise RuntimeError("Bremen")
        wk.GEAENDERT.insert(0, bad)
        self.addCleanup(wk.GEAENDERT.remove, bad)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.post(f"/api/profile/wissenskarte/knoten/{kid}/name", json={"name": "Hansestadt Bremen"}).status_code, 200)
        self.assertIn("wissen: wissenskarte knoten meldung fehler | RuntimeError", out.getvalue())
        self.assertNotIn("Bremen", out.getvalue())
        self.assertEqual(self.heard, [(kid, kid, "name")])   # the next subscriber was still called

    def test_documents_that_leave_take_their_places_and_lonely_points(self):
        c, uid, a = self.fresh("Wknweg")
        self.standard(uid)
        b = self.add(uid, "Werkstatt.txt", OTHER)
        self.work(uid, self.things(("person", "José García", 1), ("firma", "Werkstatt Müller", 1)))
        jose, shop, nord = (self.ent(uid, n)["id"] for n in ("José García", "Werkstatt Müller", "Nordstern Versicherung"))
        self.heard.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(c.delete(f"/api/profile/docs/{b}").json()["removed"])          # documents.on_gone: at once
        self.assertIn("wissen: wissenskarte knoten quelle weg | 2 fundstellen | 1 knoten | geloescht", out.getvalue())
        self.assertEqual(self.heard, [(shop, None, "weg")])
        self.assertEqual(self.ent(uid, "José García")["n"], 1)                           # still in the first document
        left = sorted(x["id"] for x in wk.knoten_liste(uid, None, "", 50))
        self.assertIn(jose, left)
        self.assertIn(nord, left)
        self.heard.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            documents.delete(uid, a)
            documents.on_gone(uid, [a], "ausgelassen")
        self.assertEqual(self.heard, [(x, None, "weg") for x in left])
        self.assertEqual(wk.knoten_liste(uid, None), [])
        with wk._Db(uid) as con:
            self.assertFalse(con.execute("SELECT 1 FROM wk_edges WHERE a LIKE 'k%' OR b LIKE 'k%'").fetchone())

    def test_own_data_can_go(self):
        c, uid, a = self.fresh("Wknown")
        self.standard(uid)
        count, clear = features.OWN["wissensknoten"]
        self.assertEqual(count(uid), 5)
        self.heard.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            clear(uid)
        self.assertEqual(count(uid), 0)
        self.assertEqual(len(self.heard), 5)


class Reading(Base):
    def test_the_list_by_name_and_read_only(self):
        c, uid, a = self.fresh("Wknliste")
        self.standard(uid)
        self.assertEqual([x["name"] for x in wk.knoten_liste(uid, None, "", 50)],
                         ["30.09.2026", "Bremen", "DE89 3704 0044 0532 0130 00", "José García", "Nordstern Versicherung"])
        self.assertEqual([x["name"] for x in wk.knoten_liste(uid, "person", "JO")], ["José García"])
        self.assertEqual(wk.knoten_liste(uid, "person", "x"), [])
        self.assertEqual(len(wk.knoten_liste(uid, None, "", 2)), 2)
        self.assertEqual(wk.knoten_liste(uid, "hund"), [])
        r = c.get("/api/profile/wissenskarte/knoten?art=ort").json()
        self.assertEqual([x["name"] for x in r["knoten"]], ["Bremen"])
        self.assertEqual(r["arten"]["frist"], ["Frist", "Deadline"])
        # read only: a profile without a database gets nothing and nothing is made
        new = profile("Wknleer")
        self.assertTrue(new)
        nid = uid_of("Wknleer")
        path = documents.db_path(nid)
        if os.path.exists(path):
            os.remove(path)
        self.assertEqual((wk.finde_knoten(nid, "Bremen"), wk.knoten_liste(nid, None)), ([], []))
        self.assertFalse(os.path.exists(path))
        con = wk._lesen(uid)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM wk_ent")
        con.close()
        with wk._Db(uid) as con:            # the fixed interface: the table, its index on (art, norm), the places
            cols = [r[1] for r in con.execute("PRAGMA table_info(wk_ent)")]
            self.assertEqual(cols, ["id", "art", "name", "norm", "alias"])
            self.assertEqual([r[1] for r in con.execute("PRAGMA table_info(wk_ment)")], ["ent", "doc", "chunk"])
            idx = {r[0]: r[1] for r in con.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name IN ('wk_ent', 'wk_ment')")}
            self.assertIn("(art, norm)", idx["wk_ent_norm"])
            self.assertIn("wk_ment_doc", idx)
            self.assertEqual(json.loads(con.execute("SELECT alias FROM wk_ent LIMIT 1").fetchone()[0]), [])


class Map(Base):
    def test_points_on_the_map_by_kind_around_them_and_the_way(self):
        c, uid, a = self.fresh("Wknkarte")
        self.standard(uid)
        jose, nord = (self.ent(uid, n)["id"] for n in ("José García", "Nordstern Versicherung"))
        with wk._Db(uid) as con:
            page = con.execute("SELECT b FROM wk_edges WHERE a=? AND art='versichert_bei'", (f"k{nord}",)).fetchone()[0]
        self.assertIn(page, {p["id"] for p in wissensbuch.index(uid)})
        v = c.get("/api/profile/wissenskarte").json()
        self.assertTrue(v["ents"])
        self.assertEqual(v["knoten"]["person"], 1)
        n = {x["id"]: x for x in v["nodes"]}
        self.assertEqual((n[f"k{jose}"]["ent"], n[f"k{jose}"]["art"], n[f"k{jose}"]["n"]), ("person", "Person", 1))
        self.assertEqual(n[page]["ent"], "")
        self.assertEqual(v["ent_arten"]["konto"], ["Konto", "Account"])
        v = c.get("/api/profile/wissenskarte?art=ort").json()            # the kind with its neighbours, also alone
        self.assertEqual([x["title"] for x in v["nodes"]], ["Bremen"])
        v = c.get("/api/profile/wissenskarte?art=person").json()
        self.assertEqual([x["id"] for x in v["nodes"]][:1], [f"k{jose}"])
        self.assertIn(f"k{nord}", [x["id"] for x in v["nodes"]])
        v = c.get(f"/api/profile/wissenskarte?um=k{jose}&tiefe=2").json()
        self.assertEqual(v["um"], f"k{jose}")
        self.assertEqual({x["id"] for x in v["nodes"]}, {f"k{jose}", f"k{nord}", page})
        self.assertEqual(wk.rund_um(uid, f"k{jose}", 2), {f"k{jose}": 0, f"k{nord}": 1, page: 2})
        w = wk.weg(uid, f"k{jose}", page)
        self.assertEqual(w["pages"], [f"k{jose}", f"k{nord}", page])
        self.assertEqual(wk.rund_um(uid, "k999999"), {})
        self.assertIsNone(wk.weg(uid, f"k{jose}", "k999999"))
        for bad in ("k0", "k", "k1 OR 1=1", "K1", "k01", "e1"):
            self.assertEqual(wk.rund_um(uid, bad), {}, bad)
        m = c.get("/api/profile/wissenskarte/export?fmt=mermaid").text
        self.assertIn('["José García"]', m)
        with mock.patch.object(wk, "VIEW_NODES", 2), mock.patch.object(wk, "VIEW_EDGES", 1):   # the limits hold with points
            v = c.get("/api/profile/wissenskarte").json()
            self.assertEqual((len(v["nodes"]), len(v["edges"]), v["cut"]), (2, 1, True))
            v = c.get("/api/profile/wissenskarte?art=konto").json()
            self.assertEqual((len(v["nodes"]), v["cut"]), (1, False))
        helpers.set_config(knowledge_ents=False)                         # off: only pages, the walk over pages only
        self.assertEqual(wk.rund_um(uid, f"k{jose}"), {})
        self.assertEqual(c.get(f"/api/profile/wissenskarte?um=k{jose}").json()["um"], "")
        self.assertEqual(c.get("/api/profile/wissenskarte").json()["knoten"], {})

    def test_wrong_for_a_connection_of_a_point(self):
        c, uid, a = self.fresh("Wknfalsch")
        self.standard(uid)
        v = c.get("/api/profile/wissenskarte").json()
        e = next(x for x in v["edges"] if x["art"] == "arbeitet_bei")
        self.assertEqual(c.delete(f"/api/profile/wissenskarte/kante/{e['id']}").status_code, 200)
        with wk._Db(uid) as con:
            con.execute("DELETE FROM wk_entdocs")
        _, log = self.work(uid, self.things(("person", "José García", 1), ("firma", "Nordstern Versicherung", 1),
                                            links=(("D1", "D2", "arbeitet bei"),)))
        self.assertIn("kante_blocked=1", log)

    def test_live_shows_numbers_by_kind_only(self):
        c, uid, a = self.fresh("Wknlive")
        self.standard(uid)
        wk._live.update(at=0.0, d=None)
        sums = wk.for_live()
        self.assertGreaterEqual(sums["knoten"]["konto"], 1)
        snap = json.dumps(live.snapshot(), ensure_ascii=False)
        self.assertIn("Knoten (", snap)
        for word in ("García", "Nordstern", "DE89", "Bremen"):
            self.assertNotIn(word, snap)
        self.assertNotIn("García", json.dumps(ADMIN.get("/api/admin/wissenskarte").json(), ensure_ascii=False))
        helpers.set_config(knowledge_ents=False)
        wk._live.update(at=0.0, d=None)
        self.assertEqual(wk.for_live()["knoten"], {})


if __name__ == "__main__":
    unittest.main()
