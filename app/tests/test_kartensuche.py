"""Karte hilft der Suche (wissenskarte.liste, plan wissensgraph Stufe 3): off by default, a child of „Personen, Firmen und
Fristen“, never for guests and never for a profile the admin blocked; the fixed rules of the list (the words hit points
by name or other name as ent_norm compares them, a legal form or a number alone never; their neighbours one step away;
their places; a piece with a point the words hit before one with only neighbours, more points before fewer; at most
KARTE_MOST; piece ids from 1), the same filters as documents.search (documents in use and read, the documents it keeps
to, never another profile's pieces, never for shared_only), the fixed weight that only adds (a piece only the map names
stays below every piece the words found), the mark "karte" on a hit and under the answer, read only, a failure that never
stops the search, the journal with fixed words and numbers, and the live line with numbers only. No test depends on the
clock; runs in a copy with app/ only."""
import contextlib
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
import profiles  # noqa: E402
import wissen  # noqa: E402
import wissensbuch  # noqa: E402
import wissenskarte as wk  # noqa: E402
from tests.test_wissenskarte import ADMIN, profile, run, uid_of  # noqa: E402

KEYS = ("documents", "doc_semantic", "doc_brief", "knowledge_book", "knowledge_map", "knowledge_ents",
        "knowledge_search", "deny", "rerank", "rmfresh")
ON = dict(documents=True, doc_semantic=False, doc_brief=False, knowledge_book=True, knowledge_map=True,
          knowledge_ents=True, knowledge_search=True, deny={}, rerank=False)


def anlegen(uid, ids, knoten, verbindungen=()):
    """The points as a model without mistakes would propose them, through the panel's fixed rules (apply_ents): every
    point in every piece of these documents where its name stands, every connection in a piece that names both ends.
    knoten: [{"art", "name"}], verbindungen: [{"von", "nach", "art"}] by name. Used by test_suchpruefung too."""
    for doc in ids:
        parts = wissensbuch.pieces(uid, doc, None)
        dinge, links = [], []
        for e in knoten:
            dinge += [{"art": e["art"], "name": e["name"], "quelle": n} for n, _, text in parts
                      if wk.stands(e["name"], text, e["art"])]
        for v in verbindungen:
            for n, _, _ in parts:
                a = [i for i, d in enumerate(dinge) if d["name"] == v["von"] and d["quelle"] == n]
                b = [i for i, d in enumerate(dinge) if d["name"] == v["nach"] and d["quelle"] == n]
                if a and b:
                    links.append({"von": f"D{a[0] + 1}", "nach": f"D{b[0] + 1}", "art": v["art"], "quelle": n})
        wk.apply_ents(uid, doc, {"dinge": dinge, "verbindungen": links}, [], parts)


TEXTS = {
    "a": "Die Hausverwaltung Kranich GmbH schickt die Abrechnung der Nebenkosten für die Wohnung Lindenweg 12.",
    "b": "Die Hausratversicherung gilt für die Wohnung Lindenweg 12 und kostet 9,80 Euro im Monat.",
    "c": "Die Hanse Schutz versichert den Hausrat. Kündigung bis 30.09.2026 möglich.",
    "d": "Für die Kürbissuppe braucht man Hokkaido, Ingwer und Kokosmilch.",
}
KNOTEN = [{"art": "firma", "name": "Hausverwaltung Kranich GmbH"}, {"art": "ort", "name": "Lindenweg 12"},
          {"art": "firma", "name": "Hanse Schutz"}, {"art": "frist", "name": "30.09.2026"}]
VERB = [{"von": "Hausverwaltung Kranich GmbH", "nach": "Lindenweg 12", "art": "betrifft"}]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, *KEYS)
        helpers.set_config(**ON)

    def fresh(self, name):
        profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with wk._Db(uid) as con:
            for t in ("wk_edges", "wk_ent", "wk_ment", "wk_entdocs", "wk_entblock"):
                con.execute(f"DELETE FROM {t}")
        ids = {k: documents.add(uid, f"{k}.txt", v.encode(), text=v)["id"] for k, v in TEXTS.items()}
        anlegen(uid, ids.values(), KNOTEN, VERB)
        return uid, ids

    @staticmethod
    def piece(uid, doc):
        with documents._Db(uid) as con:
            return con.execute("SELECT id FROM chunks WHERE doc=? ORDER BY n LIMIT 1", (doc,)).fetchone()[0]


class Defaults(Base):
    def test_off_by_default_a_child_of_the_points_and_never_for_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["knowledge_search"], False)
        self.assertNotIn("kartensuche", features.DEFAULT_ON)
        f = features.BY_KEY["kartensuche"]
        self.assertEqual(f.parent, "wissensknoten")
        self.assertEqual(f.me, "wbbox")
        self.assertNotIn("knowledge_search", profiles.SETTINGS)          # no switch for a profile
        uid, ids = self.fresh("Kartsuchea")
        q = "Was gibt es zur Hausverwaltung Kranich?"
        self.assertTrue(wk.liste(uid, q))
        for off in ({"knowledge_search": False}, {"knowledge_ents": False}, {"knowledge_map": False},
                    {"knowledge_book": False}):
            helpers.set_config(**off)
            self.assertEqual(wk.liste(uid, q), [], off)
            self.assertFalse(any(h.get("karte") for h in documents.search(uid, q, 5, karte=True)), off)
            helpers.set_config(**ON)
        helpers.set_config(deny={"kartensuche": [uid]})                  # the admin blocks one profile
        self.assertEqual(wk.liste(uid, q), [])
        helpers.set_config(deny={})
        for guest in (None, "", 0):
            self.assertEqual(wk.liste(guest, q), [])
            self.assertFalse(wk.suche_allowed(guest))

    def test_the_search_without_the_switch_is_the_search_of_before(self):
        uid, _ = self.fresh("Kartsucheb")
        q = "Was gibt es zur Hausverwaltung Kranich?"
        before = documents.search(uid, q, 5)
        self.assertEqual(documents.search(uid, q, 5, karte=False), before)
        helpers.set_config(knowledge_search=False)
        self.assertEqual(documents.search(uid, q, 5, karte=True), before)


class Rules(Base):
    def test_a_point_the_words_hit_comes_before_its_neighbours(self):
        uid, ids = self.fresh("Kartsuchec")
        got = wk.liste(uid, "Was gibt es zur Hausverwaltung Kranich?")
        # a names the company (and its neighbour Lindenweg 12), b only the neighbour; c and d nothing of them
        self.assertEqual(got, [(self.piece(uid, ids["a"]), 1), (self.piece(uid, ids["b"]), 2)])

    def test_more_points_in_a_piece_come_first(self):
        uid, ids = self.fresh("Kartsuched")
        got = wk.liste(uid, "Kranich und Lindenweg 12")
        self.assertEqual([c for c, _ in got], [self.piece(uid, ids["a"]), self.piece(uid, ids["b"])])
        self.assertEqual([r for _, r in got], [1, 2])

    def test_how_words_hit_a_name(self):
        self.assertEqual(wk.trifft("Hausverwaltung Kranich GmbH", "firma", "zur hausverwaltung  KRANICH gmbh?", set()), 2)
        q = {"stadtwerken", "weserland"}
        self.assertEqual(wk.trifft("Stadtwerke Nord", "firma", "Stadtwerken", q), 1)       # a short ending more
        self.assertEqual(wk.trifft("Stadtwerke Nord", "firma", "Stadtwerkenhaus", {"stadtwerkenhaus"}), 0)
        self.assertEqual(wk.trifft("Kranich GmbH", "firma", "GmbH", {"gmbh"}), 0)         # a legal form alone never
        self.assertEqual(wk.trifft("30.09.2026", "frist", "Was war 2026?", {"was", "war", "2026"}), 0)   # nor a number
        self.assertEqual(wk.trifft("30.09.2026", "frist", "Was ist am 30.09.2026?", {"was", "ist", "am"}), 2)
        self.assertEqual(wk.trifft("José García", "person", "Jose Garcia", {"jose", "garcia"}), 2)   # accents count not
        self.assertEqual(wk.trifft("DE89 3704 0044", "konto", "Konto DE8937040044", {"konto"}), 2)

    def test_an_other_name_hits_like_the_name(self):
        uid, ids = self.fresh("Kartsuchee")
        kid = wk.finde_knoten(uid, "Hanse Schutz", "firma")[0]["id"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wk.umbenennen(uid, kid, "Hanseatische Versicherung"), "ok")
        self.assertEqual([c for c, _ in wk.liste(uid, "Was gibt es zur Hanse Schutz?")], [self.piece(uid, ids["c"])])
        self.assertEqual([c for c, _ in wk.liste(uid, "Hanseatische Versicherung")], [self.piece(uid, ids["c"])])

    def test_at_most_k_and_never_more_than_karte_most(self):
        uid, ids = self.fresh("Kartsuchef")
        self.assertEqual(len(wk.liste(uid, "Kranich Lindenweg 12", 1)), 1)
        self.assertLessEqual(len(wk.liste(uid, "Kranich", 10 ** 6)), wk.KARTE_MOST)
        self.assertEqual(wk.liste(uid, ""), [])
        self.assertEqual(wk.liste(uid, "Kürbissuppe Ingwer"), [])            # no point named: nothing
        self.assertEqual(wk.liste(uid, ["Hanse", "Schutz", 7]), [(self.piece(uid, ids["c"]), 1)])   # a list of words


class Filters(Base):
    def test_only_pieces_this_search_may_show(self):
        uid, ids = self.fresh("Kartsucheg")
        q = "Was gibt es zur Hausverwaltung Kranich?"
        documents.set_use(uid, ids["b"], False)                         # „Suche aus“ for one document
        self.assertNotIn(self.piece(uid, ids["b"]), [c for c, _ in wk.liste(uid, q)])
        self.assertNotIn(ids["b"], [h["id"] for h in documents.search(uid, q, 5, karte=True)])
        documents.set_use(uid, ids["b"], True)
        b = self.piece(uid, ids["b"])
        documents.delete(uid, ids["b"])                                 # gone (also „ausgelassen“ deletes)
        self.assertNotIn(b, [c for c, _ in wk.liste(uid, q)])
        hits = documents.search(uid, q, 5, only_docs={ids["c"]}, karte=True)     # the documents it keeps to
        self.assertTrue(all(h["id"] == ids["c"] for h in hits))
        self.assertEqual(documents.search(uid, "Kranich", 5, shared_only=True, karte=True), [])  # never for others

    def test_never_the_pieces_of_another_profile(self):
        a, ids = self.fresh("Kartsucheh")
        b, _ = self.fresh("Kartsuchei")
        with wk._Db(b) as con:
            con.execute("DELETE FROM wk_ment")
            con.execute("DELETE FROM wk_ent")
        mine = {self.piece(a, d) for d in ids.values()}
        self.assertEqual(wk.liste(b, "Hausverwaltung Kranich"), [])
        self.assertTrue(mine & {c for c, _ in wk.liste(a, "Hausverwaltung Kranich")})

    def test_read_only(self):
        uid, _ = self.fresh("Kartsuchej")
        path = documents.db_path(uid)
        with sqlite3.connect(path) as con:
            before = [tuple(r) for t in ("wk_ent", "wk_ment", "wk_edges") for r in con.execute(f"SELECT * FROM {t}")]
        opened = []
        real = sqlite3.connect
        with mock.patch.object(wk.sqlite3, "connect", side_effect=lambda *a, **k: opened.append(a[0]) or real(*a, **k)):
            wk.liste(uid, "Kranich Lindenweg 12")
        self.assertTrue(opened and all("mode=ro" in x for x in opened), opened)
        with sqlite3.connect(path) as con:
            after = [tuple(r) for t in ("wk_ent", "wk_ment", "wk_edges") for r in con.execute(f"SELECT * FROM {t}")]
        self.assertEqual(before, after)
        profile("Kartsuchek")
        empty = uid_of("Kartsuchek")
        for d in documents.list_docs(empty):
            documents.delete(empty, d["id"])
        if os.path.exists(documents.db_path(empty)):
            os.remove(documents.db_path(empty))
        self.assertEqual(wk.liste(empty, "Kranich"), [])
        self.assertFalse(os.path.exists(documents.db_path(empty)))      # nothing made


class Mix(Base):
    def test_the_weight_only_adds(self):
        self.assertLess(documents.KARTE_WEIGHT / 60, 1 / (60 + 29))     # below the last of 30 a list hands over
        uid, ids = self.fresh("Kartsuchel")
        q = "Was gibt es zur Hausverwaltung Kranich?"
        hits = documents.search(uid, q, 5, karte=True)
        by = {h["id"]: h for h in hits}
        self.assertTrue(by[ids["a"]].get("karte"))                       # found by the words and the map
        self.assertTrue(by[ids["b"]].get("karte"))                       # only the map (the neighbour)
        self.assertLess(by[ids["b"]]["score"], min(h["score"] for h in hits if h["id"] != ids["b"]))
        self.assertNotIn("karte", next(h for h in documents.search(uid, q, 5) if h["id"] == ids["a"]))
        plain = documents.search(uid, q, 5)
        self.assertGreater(by[ids["a"]]["score"], next(h for h in plain if h["id"] == ids["a"])["score"])

    def test_a_failure_never_stops_the_search(self):
        uid, ids = self.fresh("Kartsuchem")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wk, "liste", side_effect=sqlite3.OperationalError("x")):
            hits = documents.search(uid, "Hausverwaltung Kranich", 5, karte=True)
        self.assertEqual([h["id"] for h in hits], [h["id"] for h in documents.search(uid, "Hausverwaltung Kranich", 5)])
        self.assertIn("wissen: kartensuche fehler | OperationalError", out.getvalue())

    def test_the_assistants_search_uses_the_map_and_writes_one_line(self):
        uid, ids = self.fresh("Kartsuchen")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hits = run(wissen.search(uid, "Was gibt es zur Hausverwaltung Kranich?"))
        self.assertTrue(any(h.get("karte") for h in hits))
        line = [x for x in out.getvalue().splitlines() if x.startswith("wissen: kartensuche |")]
        self.assertEqual(line, [f"wissen: kartensuche | {sum(1 for h in hits if h.get('karte'))} von {len(hits)} "
                                "stellen über die karte"])
        helpers.set_config(knowledge_search=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hits = run(wissen.search(uid, "Was gibt es zur Hausverwaltung Kranich?"))
        self.assertFalse(any(h.get("karte") for h in hits))
        self.assertNotIn("kartensuche", out.getvalue())

    def test_the_mark_stays_under_the_answer(self):
        att = [{"k": "doc", "l": [{"n": "a.txt", "id": "0123456789ab", "p": 0, "w": 1},
                                  {"n": "b.txt", "id": "0123456789ac", "p": 2, "w": "ja"},
                                  {"n": "c.txt", "id": "0123456789ad", "p": 0, "w": True}]}]
        kept = profiles._att(att)[0]["l"]
        self.assertEqual([x.get("w") for x in kept], [1, None, 1])
        with open(os.path.join(helpers.APP, "panel", "static", "js", "chat.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("r.karte?{w:1}:{}", js)
        self.assertIn("t('über die Wissenskarte','via the knowledge map')", js)


class KnotenVonDok(Base):
    """knoten_von_dok (for the thread „Ideen aus Open Notebook übernehmen“): the points of one document, read only."""
    def test_the_points_of_one_document_by_kind_and_name(self):
        uid, ids = self.fresh("Kartsuchep")
        got = wk.knoten_von_dok(uid, ids["a"])
        self.assertEqual([(x["art"], x["name"]) for x in got],
                         [("firma", "Hausverwaltung Kranich GmbH"), ("ort", "Lindenweg 12")])
        self.assertEqual(set(got[0]), {"id", "art", "name"})
        self.assertEqual([x["name"] for x in wk.knoten_von_dok(uid, ids["a"], ["ort", "planet"])], ["Lindenweg 12"])
        self.assertEqual(wk.knoten_von_dok(uid, ids["a"], ["planet"]), [])          # unknown kinds only: nothing
        self.assertEqual(wk.knoten_von_dok(uid, ids["d"]), [])
        self.assertEqual(wk.knoten_von_dok(uid, "../x"), [])
        self.assertEqual([x["art"] for x in wk.knoten_von_dok(uid, ids["c"])], ["firma", "frist"])

    def test_bound_to_the_profile_and_off_without_the_points(self):
        uid, ids = self.fresh("Kartsucheq")
        other, _ = self.fresh("Kartsucher")
        self.assertEqual(wk.knoten_von_dok(other, ids["a"]), [])          # another profile's document: nothing
        for guest in (None, ""):
            self.assertEqual(wk.knoten_von_dok(guest, ids["a"]), [])
        helpers.set_config(knowledge_ents=False)
        self.assertEqual(wk.knoten_von_dok(uid, ids["a"]), [])
        helpers.set_config(knowledge_ents=True, knowledge_search=False)   # needs only the points, not the search
        self.assertTrue(wk.knoten_von_dok(uid, ids["a"]))
        helpers.set_config(deny={"wissensknoten": [uid]})
        self.assertEqual(wk.knoten_von_dok(uid, ids["a"]), [])

    def test_read_only_and_at_most_liste_most(self):
        uid, ids = self.fresh("Kartsuches")
        opened, real = [], sqlite3.connect
        with mock.patch.object(wk.sqlite3, "connect", side_effect=lambda *a, **k: opened.append(a[0]) or real(*a, **k)):
            wk.knoten_von_dok(uid, ids["a"])
        self.assertTrue(opened and all("mode=ro" in x for x in opened), opened)
        with wk._Db(uid) as con:
            for i in range(wk.LISTE_MOST + 5):
                kid = con.execute("INSERT INTO wk_ent (art, name, norm) VALUES ('person', ?, ?)",
                                  (f"Person {i:03d}", f"person {i:03d}")).lastrowid
                con.execute("INSERT INTO wk_ment (ent, doc, chunk) VALUES (?, ?, 1)", (kid, ids["d"]))
        got = wk.knoten_von_dok(uid, ids["d"])
        self.assertEqual(len(got), wk.LISTE_MOST)
        self.assertEqual(got[0]["name"], "Person 000")


class Live(Base):
    def test_numbers_only(self):
        wk._live.update(at=0.0, d=None)
        uid, _ = self.fresh("Kartsucheo")
        wk.liste(uid, "Hausverwaltung Kranich")
        s = wk.for_live()["suche"]
        self.assertEqual(set(s), {"on", "suchen", "stellen", "fehler"})
        self.assertTrue(s["on"])
        self.assertTrue(all(isinstance(v, int) for k, v in s.items() if k != "on"))
        self.assertGreaterEqual(s["suchen"], 1)
        snap = json.dumps(live.snapshot("admin"), ensure_ascii=False)
        self.assertIn("Suche über die Karte an: ", snap)
        self.assertNotIn("Kranich", snap)
        self.assertNotIn("Lindenweg", snap)
        helpers.set_config(knowledge_search=False)
        wk._live.update(at=0.0, d=None)
        self.assertFalse(wk.for_live()["suche"]["on"])


if __name__ == "__main__":
    unittest.main()
