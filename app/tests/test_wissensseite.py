"""Seite und Punkt, Typregeln, Fristen (wissenskarte.py and wissensbuch.py, addition to plan wissensgraph Stufe 2,
Dominik 2026-10-30 „1-4“): a page of the Wissensbuch and a point of the kind person, firma or ort with the same name
are one point on the map, linked only by the fixed rule (wk_entpage, when points are read, at night and once as
migration), its connections merged in view, rund_um, weg and liste; renaming the point renames the page in the same
step and the old title keeps finding the page (no double page when working in again or after "Neu schreiben");
"Seite umbenennen" for a page without a point with the code of „Bestätigen“; a deleted page drops its link;
GEAENDERT only for points. The fixed type rules of every kind of connection (TYPEN, check_edge "typ"), deadlines only
with a date or a number with a unit in their name (words for numbers by ZAHLWORTE), and the nightly check that takes
out what was stored before. Journal lines with fixed words and numbers only. No test depends on the clock."""
import contextlib
import datetime
import io
import os
import sqlite3
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
import wissensbuch  # noqa: E402
import wissenskarte as wk  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_wissenskarte import DAY, book, profile, run, uid_of  # noqa: E402

TEXT = ("Dominik Bornhäuser arbeitet bei der Hansa Wohnbau in Bremen. Erika Muster ist seine Kollegin. Der Mietvertrag "
        "ist mit einem Monat Frist kündbar.")
PAGES = (("Dominik Bornhäuser", "Person", "Dominik Bornhäuser arbeitet bei der Hansa Wohnbau."),
         ("Hansa Wohnbau", "Firma", "Die Hansa Wohnbau sitzt in Bremen."),
         ("Mietvertrag", "Ding", "Der Mietvertrag ist kündbar."))
NIGHT = datetime.datetime(2027, 2, 10, 3, 0).timestamp()     # in suchpruefung's night window (local hours)


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "documents", "doc_semantic", "doc_brief", "knowledge_book", "knowledge_book_day",
                          "knowledge_map", "knowledge_map_day", "knowledge_ents", "knowledge_ents_day",
                          "knowledge_search", "deny")
        helpers.set_config(documents=True, doc_semantic=False, doc_brief=False, knowledge_book=True, knowledge_book_day=40,
                           knowledge_map=True, knowledge_map_day=200, knowledge_ents=True, knowledge_ents_day=200,
                           knowledge_search=True, deny={})
        wk._live.update(at=0.0, d=None)
        self.heard = []
        self.addCleanup(lambda: wk.GEAENDERT.remove(self.hear) if self.hear in wk.GEAENDERT else None)
        wk.GEAENDERT.append(self.hear)

    def hear(self, uid, alt, neu, was):
        self.heard.append((alt, neu, was))

    def fresh(self, name):
        """A profile with one document worked into the book (PAGES) and its points; the map's own step is done."""
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with wk._Db(uid) as con:
            for t in ("wb_pages", "wb_sent", "wb_docs", "wb_block", "wb_alttitel", "wb_state", "wk_edges", "wk_docs",
                      "wk_block", "wk_ent", "wk_ment", "wk_entdocs", "wk_entblock", "wk_entpage"):
                con.execute(f"DELETE FROM {t}")
        a = documents.add(uid, "Miete.txt", TEXT.encode(), text=TEXT)["id"]
        with mock.patch.object(wissensbuch, "ask_model", mock.AsyncMock(return_value=book(*PAGES))), \
                contextlib.redirect_stdout(io.StringIO()):
            run(wissensbuch.work_in(uid, DAY))
        with wk._Db(uid) as con:
            con.execute("INSERT OR REPLACE INTO wk_docs (doc, state, at, sig) SELECT doc, 'ok', 0, sig FROM wb_docs")
        return c, uid, a

    def work(self, uid, got):
        out = io.StringIO()
        self.heard.clear()
        with contextlib.redirect_stdout(out), mock.patch.object(wk, "ask_ents", mock.AsyncMock(return_value=got)):
            run(wk.ents_work_in(uid, DAY))
        return out.getvalue()

    @staticmethod
    def things(*items, links=()):
        return {"dinge": [{"art": a, "name": n, "quelle": q} for a, n, q in items],
                "verbindungen": [{"von": x, "nach": y, "art": k, "quelle": 1, "detail": ""} for x, y, k in links]}

    def standard(self, uid):
        return self.work(uid, self.things(("person", "Dominik Bornhäuser", 1), ("person", "Erika Muster", 1),
                                          ("firma", "Hansa Wohnbau", 1), ("ort", "Bremen", 1), ("frist", "einem Monat", 1),
                                          links=(("D1", "D3", "arbeitet bei"), ("D3", "D4", "liegt in"),
                                                 ("D5", "K3", "Frist für"))))

    @staticmethod
    def ent(uid, name):
        return next(x for x in wk.knoten_liste(uid, None, "", 200) if x["name"] == name)

    @staticmethod
    def page_id(uid, title):
        return next(p["id"] for p in wissensbuch.index(uid) if p["title"] == title)

    @staticmethod
    def links(uid):
        with wk._Db(uid) as con:
            return {r[0]: r[1] for r in con.execute("SELECT ent, page FROM wk_entpage")}


class TypeRules(Base):
    def test_every_kind_has_its_rule_and_the_rule_holds(self):
        self.assertEqual(set(wk.TYPEN), set(wk.ARTEN))
        kinds = set(wk.ENT_ARTEN) | {wk.SEITE}
        for art, (von, nach) in wk.TYPEN.items():
            self.assertTrue(von <= kinds and nach <= kinds, art)
            self.assertIn(wk.SEITE, von, art)          # a page has no kind of its own: it may stand on either end
            self.assertIn(wk.SEITE, nach, art)
        self.assertTrue(wk.erlaubt("arbeitet_bei", "person", "firma"))
        self.assertTrue(wk.erlaubt("arbeitet_bei", "person", "ort"))
        for von, nach in (("person", "person"), ("firma", "person"), ("ort", "firma"), ("frist", "firma")):
            self.assertFalse(wk.erlaubt("arbeitet_bei", von, nach), (von, nach))
        self.assertFalse(wk.erlaubt("frist_fuer", "person", "vertrag"))
        self.assertFalse(wk.erlaubt("wohnt_in", "person", "firma"))
        self.assertFalse(wk.erlaubt("hasst", "person", "person"))
        nodes = {"D1": {"id": "k1", "title": "Dominik Bornhäuser", "kind": "person"},
                 "D2": {"id": "k2", "title": "Erika Muster", "kind": "person"},
                 "D3": {"id": "k3", "title": "Hansa Wohnbau", "kind": "firma"}}
        src = {1: (0, TEXT)}
        e = lambda a, b, k="arbeitet bei": wk.check_edge({"von": a, "nach": b, "art": k, "quelle": 1}, nodes, src)  # noqa: E731
        self.assertEqual(e("D1", "D2"), (None, "typ"))
        self.assertEqual(e("D3", "D1"), (None, "typ"))
        self.assertEqual(e("D1", "D3")[0]["art"], "arbeitet_bei")

    def test_reading_refuses_and_logs_violations(self):
        c, uid, a = self.fresh("Wspregel")
        log = self.work(uid, self.things(("person", "Dominik Bornhäuser", 1), ("person", "Erika Muster", 1),
                                         ("firma", "Hansa Wohnbau", 1),
                                         links=(("D1", "D2", "arbeitet bei"), ("D3", "D1", "arbeitet bei"),
                                                ("D1", "D3", "arbeitet bei"))))
        self.assertIn("| 1 verbindungen |", log)
        self.assertIn("kante_typ=2", log)
        for word in ("Dominik", "Erika", "Hansa"):
            self.assertNotIn(word, log)
        # the map step between pages: a page that belongs to a point counts as the point's kind
        parts = wissensbuch.pieces(uid, a)
        text = "\n\n".join(f"[S{n}] {t}" for n, _, t in parts)
        nodes = wk.nodes_for(uid, a, text)
        kinds = {p["title"]: p["kind"] for p in nodes}
        self.assertEqual(kinds, {"Dominik Bornhäuser": "person", "Hansa Wohnbau": "firma", "Mietvertrag": wk.SEITE})
        keyed = {p["title"]: f"K{i + 1}" for i, p in enumerate(nodes)}
        got = {"verbindungen": [{"von": keyed["Hansa Wohnbau"], "nach": keyed["Dominik Bornhäuser"], "art": "arbeitet bei",
                                 "quelle": 1}, {"von": keyed["Mietvertrag"], "nach": keyed["Hansa Wohnbau"],
                                                "art": "betrifft", "quelle": 1}]}
        cnt = wk.apply(uid, a, got, nodes, parts, DAY)
        self.assertEqual((cnt["neu"], cnt["gruende"]), (1, {"typ": 1}))
        helpers.set_config(knowledge_ents=False)       # without the points every page is a page
        self.assertEqual({p["kind"] for p in wk.nodes_for(uid, a, text)}, {wk.SEITE})


class Deadlines(Base):
    def test_a_deadline_needs_a_number_or_a_date_in_its_name(self):
        self.assertEqual(wk.zahlen("einem Monat"), "1 Monat")
        self.assertEqual(wk.zahlen("zwei Wochen"), "2 Wochen")
        self.assertEqual(wk.zahlen("Zwölf Monate"), "12 Monate")
        self.assertEqual(wk.zahlen("two weeks"), "2 weeks")
        self.assertEqual(wk.zahlen("eine Frist"), "eine Frist")          # only before a unit of time
        for good, want in (("1 Monat", "1 Monat"), ("14 Tage", "14 Tage"), ("31.12.2026", "31.12.2026"),
                           ("einem Monat", "1 Monat"), ("drei Werktagen", "3 Werktagen"), ("bis 1. März 2026", "bis 1. März 2026")):
            self.assertEqual(wk.frist_name(good), want, good)
        for bad in ("einem", "zwei", "Monat", "Kollegin", "eine Frist", "Kündigung", "Version 3"):
            self.assertEqual(wk.frist_name(bad), "", bad)
        src = {1: (0, TEXT), 2: (0, "Die Kündigungsfrist beträgt 14 Tage zum Monatsende.")}
        ok = lambda n, q=1: wk.check_ent({"art": "frist", "name": n, "quelle": q}, src)   # noqa: E731
        self.assertEqual(ok("einem Monat")[0]["name"], "1 Monat")        # said as words, kept as digits
        self.assertEqual(ok("einem Monat")[0]["norm"], "1 monat")
        self.assertEqual(ok("1 Monat")[0]["name"], "1 Monat")            # the digits stand there as words
        self.assertEqual(ok("14 Tage", 2)[0]["name"], "14 Tage")
        self.assertEqual(ok("einem"), (None, "no date"))
        self.assertEqual(ok("Kollegin"), (None, "no date"))
        self.assertEqual(ok("zwei Wochen"), (None, "not named"))         # a number the piece does not say
        self.assertEqual(ok("3 Monate"), (None, "not named"))
        c, uid, a = self.fresh("Wspfrist")
        log = self.work(uid, self.things(("frist", "einem Monat", 1), ("frist", "Kollegin", 1)))
        self.assertIn("no_date=1", log)
        self.assertEqual([x["name"] for x in wk.knoten_liste(uid, "frist")], ["1 Monat"])


class PageAndPoint(Base):
    def test_one_point_on_the_map_with_the_connections_of_both(self):
        c, uid, a = self.fresh("Wspkarte")
        log = self.standard(uid)
        self.assertIn("| 2 mit seite", log)
        dom, hansa, bremen, erika = (self.ent(uid, n)["id"] for n in ("Dominik Bornhäuser", "Hansa Wohnbau", "Bremen",
                                                                      "Erika Muster"))
        pd, ph, pm = (self.page_id(uid, t) for t in ("Dominik Bornhäuser", "Hansa Wohnbau", "Mietvertrag"))
        self.assertEqual(self.links(uid), {dom: pd, hansa: ph})
        self.assertNotIn(erika, self.links(uid))
        # the map step brings the same connection between the pages and one more: merged with the points'
        parts = wissensbuch.pieces(uid, a)
        nodes = wk.nodes_for(uid, a, "\n\n".join(f"[S{n}] {t}" for n, _, t in parts))
        keyed = {p["id"]: f"K{i + 1}" for i, p in enumerate(nodes)}
        wk.apply(uid, a, {"verbindungen": [{"von": keyed[pd], "nach": keyed[ph], "art": "arbeitet bei", "quelle": 1},
                                           {"von": keyed[pm], "nach": keyed[pd], "art": "betrifft", "quelle": 1}]},
                 nodes, parts, DAY)
        v = c.get("/api/profile/wissenskarte").json()
        ids = {n["id"]: n for n in v["nodes"]}
        self.assertNotIn(pd, ids)                       # one point, not a round and a square one
        self.assertNotIn(ph, ids)
        self.assertEqual((ids[f"k{dom}"]["seite"], ids[f"k{dom}"]["ent"]), (pd, "person"))
        self.assertEqual(ids[f"k{bremen}"]["seite"], "")
        pairs = [(e["a"], e["b"], e["art"]) for e in v["edges"]]
        self.assertEqual(pairs.count((f"k{dom}", f"k{hansa}", "arbeitet_bei")), 1)   # the same connection once
        self.assertIn((pm, f"k{dom}", "betrifft"), pairs)                             # the page's own, on the point
        self.assertEqual(ids[f"k{dom}"]["deg"], 2)
        v = c.get(f"/api/profile/wissenskarte?um={pd}&tiefe=1").json()               # around the page: its point
        self.assertEqual(v["um"], f"k{dom}")
        self.assertEqual({n["id"] for n in v["nodes"]}, {f"k{dom}", f"k{hansa}", pm})
        self.assertEqual(wk.rund_um(uid, pd, 1), {f"k{dom}": 0, f"k{hansa}": 1, pm: 1})
        self.assertEqual(wk.weg(uid, pm, f"k{bremen}")["pages"], [pm, f"k{dom}", f"k{hansa}", f"k{bremen}"])
        self.assertEqual(wk.weg(uid, pd, f"k{dom}"), {"pages": [f"k{dom}"], "edges": []})
        # the search over the map reaches the neighbours of the page too (read only)
        self.assertTrue(wk.liste(uid, "Was macht Dominik Bornhäuser?"))
        con = wk._lesen(uid)
        try:
            self.assertEqual(wk._rund_um(con, pd, 1, True), {f"k{dom}": 0, f"k{hansa}": 1, pm: 1})
        finally:
            con.close()
        self.assertEqual(self.heard, [])

    def test_the_rule_never_the_model_and_one_page_one_point(self):
        c, uid, a = self.fresh("Wspregel2")
        with wk._Db(uid) as con:      # a filed answer of the same name never belongs to a point
            con.execute("UPDATE wb_pages SET art='Antwort' WHERE title='Hansa Wohnbau'")
        self.standard(uid)
        self.assertEqual(set(self.links(uid)), {self.ent(uid, "Dominik Bornhäuser")["id"]})
        # a firma and a person of the same name: the page of the kind Person takes the person
        with wk._Db(uid) as con:
            con.execute("INSERT INTO wk_ent (art, name, norm) VALUES ('firma', 'Dominik Bornhäuser', 'dominik bornhauser')")
            con.execute("DELETE FROM wk_entpage")
            self.assertEqual(wk._verbinde(con), 1)
            self.assertEqual(con.execute("SELECT e.art FROM wk_entpage l JOIN wk_ent e ON e.id=l.ent").fetchone()[0], "person")
            self.assertEqual(wk._verbinde(con), 0)          # nothing twice
        # the model's proposal holds no link: only names and kinds go through the rules
        self.assertNotIn("seite", wk.ENT_PROMPT.lower().split("seiten")[0])

    def test_a_deleted_page_drops_its_link_and_points_report_only_points(self):
        c, uid, a = self.fresh("Wspweg")
        self.standard(uid)
        dom = self.ent(uid, "Dominik Bornhäuser")["id"]
        pd = self.page_id(uid, "Dominik Bornhäuser")
        self.heard.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.delete(f"/api/profile/wissensbuch/{pd}").status_code, 200)
        self.assertNotIn(dom, self.links(uid))
        self.assertEqual(self.heard, [])                   # a page is no point: GEAENDERT stays quiet
        v = c.get("/api/profile/wissenskarte").json()
        self.assertEqual(next(n for n in v["nodes"] if n["id"] == f"k{dom}")["seite"], "")
        # deleting the point keeps the page and drops the link
        _, uid2, _ = self.fresh("Wspweg2")
        self.standard(uid2)
        hansa = self.ent(uid2, "Hansa Wohnbau")["id"]
        ph = self.page_id(uid2, "Hansa Wohnbau")
        self.assertTrue(wk.loeschen(uid2, hansa))
        self.assertNotIn(hansa, self.links(uid2))
        self.assertIn(ph, {p["id"] for p in wissensbuch.index(uid2)})

    def test_the_link_is_made_once_as_migration(self):
        c, uid, a = self.fresh("Wspmig")
        self.standard(uid)
        path = documents.db_path(uid)
        con = sqlite3.connect(path)
        con.execute("DROP TABLE wk_entpage")
        con.commit()
        con.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with wk._Db(uid):
                pass
        self.assertIn("wissen: wissenskarte seiten verbunden | 2 punkte | einmalig", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with wk._Db(uid):
                pass
        self.assertNotIn("einmalig", out.getvalue())
        self.assertEqual(len(self.links(uid)), 2)


class Rename(Base):
    def test_renaming_the_point_renames_its_page_and_the_old_title_finds_it(self):
        c, uid, a = self.fresh("Wspname")
        self.standard(uid)
        dom = self.ent(uid, "Dominik Bornhäuser")["id"]
        pd = self.page_id(uid, "Dominik Bornhäuser")
        self.heard.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = c.post(f"/api/profile/wissenskarte/knoten/{dom}/name", json={"name": "Dominik Bornhaeuser"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.heard, [(dom, dom, "name")])
        self.assertIn("wissen: wissenskarte knoten umbenannt | 1 knoten", out.getvalue())
        p = wissensbuch.page(uid, pd)
        self.assertEqual((p["title"], p["frueher"], p["punkt"]), ("Dominik Bornhaeuser", ["Dominik Bornhäuser"], True))
        self.assertEqual(self.ent(uid, "Dominik Bornhaeuser")["alias"], ["Dominik Bornhäuser"])
        n_pages = len(wissensbuch.index(uid))
        # working in again under the old title lands on the renamed page: no double page
        parts = wissensbuch.pieces(uid, a)
        got = book(("Dominik Bornhäuser", "Person", "Dominik Bornhäuser ist bei der Hansa Wohnbau."))
        self.assertEqual(wissensbuch.apply(uid, a, got, parts, DAY)["neu"], 0)
        self.assertEqual(len(wissensbuch.index(uid)), n_pages)
        self.assertEqual(len(wissensbuch.page(uid, pd)["saetze"]), 2)
        # "Neu schreiben": the page goes and comes back under the new title, and the rule links it again
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pd}/neu").status_code, 200)
        self.assertEqual(wissensbuch.apply(uid, a, got, parts, DAY)["neu"], 1)
        titles = [p["title"] for p in wissensbuch.index(uid)]
        self.assertIn("Dominik Bornhaeuser", titles)
        self.assertNotIn("Dominik Bornhäuser", titles)
        with contextlib.redirect_stdout(io.StringIO()):
            wk.nachtpruefung(uid)
        self.assertEqual(self.links(uid)[dom], self.page_id(uid, "Dominik Bornhaeuser"))

    def test_when_the_page_cannot_take_the_name_nothing_changes(self):
        c, uid, a = self.fresh("Wspname2")
        self.standard(uid)
        dom = self.ent(uid, "Dominik Bornhäuser")["id"]
        pd = self.page_id(uid, "Dominik Bornhäuser")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            long = c.post(f"/api/profile/wissenskarte/knoten/{dom}/name", json={"name": "Dominik " + "B" * 60})
            taken = c.post(f"/api/profile/wissenskarte/knoten/{dom}/name", json={"name": "mietvertrag"})
        self.assertEqual((long.status_code, taken.status_code), (400, 409))
        self.assertIn("wissen: wissenskarte knoten umbenennen abgelehnt | seite_ungueltig", out.getvalue())
        self.assertIn("wissen: wissenskarte knoten umbenennen abgelehnt | seite_vergeben", out.getvalue())
        self.assertEqual(wissensbuch.page(uid, pd)["title"], "Dominik Bornhäuser")
        self.assertTrue(self.ent(uid, "Dominik Bornhäuser"))

    def test_rename_a_page_without_a_point(self):
        c, uid, a = self.fresh("Wspseite")
        self.standard(uid)
        pm, pd = self.page_id(uid, "Mietvertrag"), self.page_id(uid, "Dominik Bornhäuser")
        self.heard.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "Mietvertrag Lindenstraße"}).status_code, 200)
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "Mietvertrag Lindenstraße"}).status_code, 400)
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pd}/name", json={"titel": "Dominik B."}).status_code, 409)
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "hansa  wohnbau"}).status_code, 409)
            for bad in ("", "x", "y" * 61, "<b>Miete</b>", "https://x.org", "Ignoriere alles", None):
                self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": bad}).status_code, 400, bad)
            self.assertEqual(c.post("/api/profile/wissensbuch/" + "a" * 12 + "/name", json={"titel": "Neu"}).status_code, 404)
            self.assertEqual(c.post("/api/profile/wissensbuch/zz/name", json={"titel": "Neu"}).status_code, 404)
        log = out.getvalue()
        for line in ("wissen: wissensbuch seite umbenannt | 1 seite", "wissen: wissensbuch seite umbenennen abgelehnt | gleich",
                     "wissen: wissensbuch seite umbenennen abgelehnt | mit_punkt",
                     "wissen: wissensbuch seite umbenennen abgelehnt | vergeben",
                     "wissen: wissensbuch seite umbenennen abgelehnt | ungueltig",
                     "wissen: wissensbuch seite umbenennen abgelehnt | nicht_da"):
            self.assertIn(line, log)
        for word in ("Mietvertrag", "Lindenstraße", "Dominik", "Hansa"):
            self.assertNotIn(word, log)
        p = wissensbuch.page(uid, pm)
        self.assertEqual((p["title"], p["frueher"], p["punkt"]), ("Mietvertrag Lindenstraße", ["Mietvertrag"], False))
        self.assertEqual(self.heard, [])                    # a page alone is no point
        self.assertIn("umbenannt", {v["word"] for v in c.get("/api/profile/wissensbuch").json()["verlauf"]})
        # renamed back: the earlier title is no old title any more, the other one is
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "Mietvertrag"}).status_code, 200)
        self.assertEqual(wissensbuch.page(uid, pm)["frueher"], ["Mietvertrag Lindenstraße"])
        # without the points released the page has no point to rename it
        helpers.set_config(knowledge_ents=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post(f"/api/profile/wissensbuch/{pd}/name", json={"titel": "Dominik B."}).status_code, 200)

    def test_the_code_of_confirm_size_and_who(self):
        self.assertEqual(stufen.LIST[("POST", "/api/profile/wissensbuch/{pid}/name")][0], stufen.CONFIRM)
        from tests.test_zweiter_schritt import fake_second_step
        import core
        import mfa
        c, uid, a = self.fresh("Wspcode")
        pm = self.page_id(uid, "Mietvertrag")
        self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", content=b'{"titel": "' + b"x" * 600 + b'"}',
                                headers={"content-type": "application/json"}).status_code, 413)
        fake_second_step(uid)
        self.addCleanup(lambda: os.path.exists(mfa._own_path(uid)) and os.remove(mfa._own_path(uid)))
        core._windows.clear()
        self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "Miete"}).status_code, 428)
        self.assertEqual(wissensbuch.page(uid, pm)["title"], "Mietvertrag")       # nothing changed without the code
        guest = TestClient(panel.app)
        self.assertIn(guest.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "Miete"}).status_code, (401, 403))
        helpers.set_config(knowledge_book=False)
        self.assertEqual(c.post(f"/api/profile/wissensbuch/{pm}/name", json={"titel": "Miete"}).status_code, 403)


class Night(Base):
    def test_the_nightly_check_takes_out_what_breaks_the_rules(self):
        c, uid, a = self.fresh("Wspnacht")
        self.standard(uid)
        dom, erika = self.ent(uid, "Dominik Bornhäuser")["id"], self.ent(uid, "Erika Muster")["id"]
        with wk._Db(uid) as con:      # stored before the rules: a person working at a person, a deadline without number
            con.execute("INSERT INTO wk_edges (a, b, art, detail, doc, part, dpage, made) VALUES (?, ?, 'arbeitet_bei', '', ?, 1, 0, 0)",
                        (f"k{dom}", f"k{erika}", a))
            kid = con.execute("INSERT INTO wk_ent (art, name, norm) VALUES ('frist', 'Kollegin', 'kollegin')").lastrowid
            chunk = con.execute("SELECT MIN(n) FROM chunks WHERE doc=?", (a,)).fetchone()[0]
            con.execute("INSERT INTO wk_ment (ent, doc, chunk) VALUES (?, ?, ?)", (kid, a, chunk))
            con.execute("INSERT INTO wk_edges (a, b, art, detail, doc, part, dpage, made) VALUES (?, ?, 'betrifft', '', ?, 1, 0, 0)",
                        (f"k{kid}", f"k{dom}", a))
            con.execute("DELETE FROM wk_entpage")
            con.execute("DELETE FROM wb_state WHERE key='wk_check_at'")
        before = dict(wk.NACHT)
        self.heard.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wk.profiles, "user_ids", return_value=[uid]):
            self.assertEqual(run(wk.due_once(NIGHT)), "wissenskarte-pruefung")
            self.assertNotEqual(run(wk.due_once(NIGHT + 60)), "wissenskarte-pruefung")    # once a night
        self.assertIn("wissen: wissenskarte geprueft | 1 verbindungen gegen typregeln | 1 fristen ohne zahl | 2 mit seite",
                      out.getvalue())
        self.assertEqual(self.heard, [(kid, None, "weg")])
        self.assertEqual([x["name"] for x in wk.knoten_liste(uid, "frist")], ["1 Monat"])
        with wk._Db(uid) as con:
            self.assertFalse(con.execute("SELECT 1 FROM wk_edges WHERE a=? AND b=?", (f"k{dom}", f"k{erika}")).fetchone())
            self.assertFalse(con.execute("SELECT 1 FROM wk_edges WHERE a=?", (f"k{kid}",)).fetchone())
            self.assertTrue(con.execute("SELECT 1 FROM wk_edges WHERE art='arbeitet_bei'").fetchone())   # the right one stays
        self.assertEqual(wk.NACHT["typ"] - before["typ"], 1)
        self.assertEqual(wk.NACHT["frist"] - before["frist"], 1)
        with mock.patch.object(wk.profiles, "user_ids", return_value=[uid]):        # by day: no check
            with wk._Db(uid) as con:
                con.execute("DELETE FROM wb_state WHERE key='wk_check_at'")
            with mock.patch.object(wk, "nachtpruefung") as check, contextlib.redirect_stdout(io.StringIO()):
                run(wk.due_once(DAY))
            check.assert_not_called()

    def test_live_shows_numbers_only(self):
        c, uid, a = self.fresh("Wsplive")
        self.standard(uid)
        wk._live.update(at=0.0, d=None)
        d = wk.for_live()
        self.assertGreaterEqual(d["mit_seite"], 2)
        self.assertEqual(set(d["nacht"]), {"typ", "frist", "laeufe"})
        wk.NACHT["laeufe"] += 1
        self.addCleanup(lambda: wk.NACHT.update(laeufe=wk.NACHT["laeufe"] - 1))
        line = live._kartennacht(wk.NACHT)
        self.assertIn("Verbindungen gegen Typregeln", line)
        snap = str(live.snapshot()) if hasattr(live, "snapshot") else ""
        for word in ("Dominik", "Hansa", "Bremen", "Monat"):
            self.assertNotIn(word, line)
            self.assertNotIn(word, snap)


if __name__ == "__main__":
    unittest.main()
