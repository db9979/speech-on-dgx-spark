"""Tempo der Wissenskarte (Wissenskarte Stufe 2 statt Neo4j, Dominik 2026-10-30): the map answers as before, only
faster, and the higher limits hold. No test measures a time: they check how the work is done (the query plan uses the
indexes, the number of points looked at, how often the build of the map is made), and that every answer is the same as
the answer of the slow way (a run over every point, a walk over the whole map). No test depends on the clock; runs in
a copy with app/ only."""
import contextlib
import io
import json
import sqlite3
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import wissensbuch  # noqa: E402
import wissensdoppelt as wd  # noqa: E402
import wissenskarte as wk  # noqa: E402
from tests.test_kartensuche import KNOTEN, ON, TEXTS, VERB, anlegen  # noqa: E402
from tests.test_kartensuche import KEYS as KS_KEYS  # noqa: E402
from tests.test_wissenskarte import DAY, profile, run, uid_of  # noqa: E402

KEYS = KS_KEYS + ("knowledge_map_day",)


def langsam(uid, q):
    """liste the slow way: every point is a candidate (the run over all of them before the word index)."""
    def alle(con, *_):
        return con.execute("SELECT id, art, norm, alias FROM wk_ent ORDER BY id").fetchall()
    with mock.patch.object(wk, "_kandidaten", alle):
        return wk.liste(uid, q)


def weg_langsam(uid, a, b, tiefe=wk.WEG_MOST):
    """weg the slow way: the whole walk from a (as before), then back from b over the smallest ids."""
    ents = wk.ents_allowed(uid)
    with wk._Db(uid) as con:
        if wk._there(con, list({a, b}), ents) < len({a, b}):
            return None
        links = wk._links(con, ents)
        if ents:
            a, b = wk._haupt(con, a), wk._haupt(con, b)
        if a == b:
            return {"pages": [a], "edges": []}
        dist = wk._rund_um(con, a, tiefe, ents)
        if b not in dist:
            return None
        pages, edges, here = [b], [], b
        while here != a:
            o, i = min((y if x == here else x, i) for i, x, y, _ in wk._kanten_um(con, [here], ents, links)
                       if dist.get(y if x == here else x) == dist[here] - 1)
            pages.append(o)
            edges.append(i)
            here = o
    return {"pages": pages[::-1], "edges": edges[::-1]}


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
            for t in ("wk_edges", "wk_ent", "wk_ment", "wk_entdocs", "wk_entblock", "wb_pages", "wb_sent"):
                con.execute(f"DELETE FROM {t}")
        ids = {k: documents.add(uid, f"{k}.txt", v.encode(), text=v)["id"] for k, v in TEXTS.items()}
        anlegen(uid, ids.values(), KNOTEN, VERB)
        return uid, ids

    def viele(self, uid, doc, n=300):
        """n more points of all kinds with one place each, a few accounts and other names."""
        with documents._Db(uid) as con:
            chunk = con.execute("SELECT MIN(n) FROM chunks WHERE doc=?", (doc,)).fetchone()[0]
        with wk._Db(uid) as con:
            for i in range(n):
                art = wk.ENT_ARTEN[i % len(wk.ENT_ARTEN)]
                name = f"DE12 3456 {i:04d} 7788 99" if art == "konto" else f"Punkt{i:03d} Beispielname{i % 7}"
                kid = con.execute("INSERT INTO wk_ent (art, name, norm, alias) VALUES (?, ?, ?, ?)",
                                  (art, name, wk.ent_norm(name), json.dumps([f"Anders{i:03d} GmbH"] if i % 10 == 0 else []))).lastrowid
                con.execute("INSERT INTO wk_ment (ent, doc, chunk) VALUES (?, ?, ?)", (kid, doc, chunk))


class Liste(Base):
    QS = ("Was gibt es zur Hausverwaltung Kranich?", "Lindenweg 12", "Kranichs Abrechnung", "Punkt017 und Punkt018",
          "Beispielname3", "Beispielnamen", "Anders010", "Überweisung auf DE12345600237788 99", "gmbh", "Hanse",
          "xx yy", "Punkt0", "Frist 30.09.2026", "beispielname1 punkt001")

    def test_the_word_index_finds_what_the_run_over_every_point_found(self):
        uid, ids = self.fresh("Wtempoa")
        self.viele(uid, ids["d"])
        for q in self.QS:
            self.assertEqual(wk.liste(uid, q), langsam(uid, q), q)
        self.assertTrue(wk.liste(uid, "Punkt017"))

    def test_only_candidates_from_the_index_are_looked_at(self):
        uid, ids = self.fresh("Wtempob")
        self.viele(uid, ids["d"], 600)
        with wk._Db(uid) as con:
            alle = con.execute("SELECT COUNT(*) FROM wk_ent").fetchone()[0]
        seen = []
        real = wk._trifft
        with mock.patch.object(wk, "_trifft", lambda nn, *a: seen.append(nn) or real(nn, *a)):
            got = wk.liste(uid, "Punkt017 Beispielname5")
        self.assertTrue(got)
        self.assertGreater(alle, 600)
        self.assertLess(len(seen), alle // 4, "liste looked at nearly every point")      # bounded by rows, not time
        with wk._Db(uid) as con:
            plan = " ".join(r[3] for r in con.execute(
                "EXPLAIN QUERY PLAN SELECT id, art, norm, alias FROM wk_ent WHERE id IN (SELECT ent FROM wk_entwort WHERE "
                "wort IN (SELECT value FROM json_each(?)) UNION SELECT ent FROM wk_entwortneu) ORDER BY id", ("[]",)))
            self.assertIn("USING INDEX wk_entwort_wort", plan)
            self.assertNotIn("SCAN wk_ent ", plan + " ")
            plan = " ".join(r[3] for r in con.execute(
                "EXPLAIN QUERY PLAN SELECT c.id, m.ent FROM wk_ment m JOIN chunks c ON c.doc=m.doc AND c.n=m.chunk JOIN "
                "docs d ON d.id=m.doc WHERE m.ent IN (SELECT value FROM json_each(?)) AND d.use=1 AND d.state='ready'", ("[]",)))
            self.assertIn("COVERING INDEX chunks_doc_n", plan)        # the places without text and vector of the pieces

    def test_every_change_of_a_point_reaches_the_index(self):
        uid, ids = self.fresh("Wtempoc")
        self.viele(uid, ids["d"], 60)
        kid = wk.finde_knoten(uid, "Punkt012 Beispielname5")[0]["id"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wk.umbenennen(uid, kid, "Zitronenfalter Holding"), "ok")
        for q in ("Zitronenfalter", "Punkt012 Beispielname5", "Beispielname5"):
            self.assertEqual(wk.liste(uid, q), langsam(uid, q), q)
        self.assertTrue(wk.liste(uid, "Zitronenfalter"))
        other = wk.finde_knoten(uid, "Punkt018 Beispielname4")[0]["id"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wk.zusammen(uid, other, kid), "ok")
            self.assertTrue(wk.loeschen(uid, wk.finde_knoten(uid, "Punkt024 Beispielname3")[0]["id"]))
        for q in ("Punkt018", "Punkt024", "Zitronenfalter", "Beispielname3"):
            self.assertEqual(wk.liste(uid, q), langsam(uid, q), q)
        with wk._Db(uid) as con:
            self.assertFalse(con.execute("SELECT 1 FROM wk_entwort WHERE ent NOT IN (SELECT id FROM wk_ent)").fetchone())
            self.assertFalse(con.execute("SELECT 1 FROM wk_entwortneu").fetchone())       # written with the commit
        # a point written by another connection (no commit through _Db yet): marked, and liste finds it already
        raw = sqlite3.connect(documents.db_path(uid))
        with raw:
            nid = raw.execute("INSERT INTO wk_ent (art, name, norm) VALUES ('person', 'Erna Zaunkönig', 'erna zaunkonig')").lastrowid
            raw.execute("INSERT INTO wk_ment (ent, doc, chunk) SELECT ?, doc, chunk FROM wk_ment LIMIT 1", (nid,))
        raw.close()
        self.assertTrue(wk.liste(uid, "Zaunkönig"))
        self.assertEqual(wk.liste(uid, "Zaunkönig"), langsam(uid, "Zaunkönig"))

    def test_a_changed_rule_writes_all_keys_again_once(self):
        uid, ids = self.fresh("Wtempod")
        self.viele(uid, ids["d"], 30)
        raw = sqlite3.connect(documents.db_path(uid))     # as an older version left it (no commit through _Db)
        with raw:
            raw.execute("UPDATE wb_state SET val=0 WHERE key='wk_entwort'")
            raw.execute("DELETE FROM wk_entwort")
        raw.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), wk._Db(uid) as con:
            n = con.execute("SELECT COUNT(DISTINCT ent) FROM wk_entwort").fetchone()[0]
        self.assertIn("wissen: wissenskarte wortindex aufgebaut |", out.getvalue())
        with wk._Db(uid) as con:
            self.assertEqual(n, con.execute("SELECT COUNT(*) FROM wk_ent").fetchone()[0])


class Bau(Base):
    def test_the_build_is_made_once_per_stand_and_every_change_makes_it_new(self):
        uid, ids = self.fresh("Wtempoe")
        wk._BAU.clear()
        made = []
        real = wk._baue
        with mock.patch.object(wk, "_baue", lambda con, ents: made.append(ents) or real(con, ents)):
            first = wk.view(uid)
            self.assertEqual(wk.view(uid), first)
            self.assertEqual(wk.view(uid, doc=ids["a"])["doc"], ids["a"])
            self.assertEqual(len(made), 1)
            pid = "%012x" % 0xabc000000001
            with wk._Db(uid) as con:            # a change in any table of STAND_TABELLEN: made anew
                con.execute("INSERT INTO wb_pages (id, title, art, made, changed) VALUES (?, 'Neue Seite', 'Thema', 1, 1)", (pid,))
                k = con.execute("SELECT 'k' || MIN(id) FROM wk_ent").fetchone()[0]
                con.execute("INSERT INTO wk_edges (a, b, art, detail, doc, made) VALUES (?, ?, 'betrifft', '', ?, 1)",
                            (pid, k, ids["a"]))
            second = wk.view(uid)
            self.assertEqual(len(made), 2)
            self.assertIn(pid, [n["id"] for n in second["nodes"]])
            with documents._Db(uid) as con:
                con.execute("UPDATE docs SET use=0 WHERE id=?", (ids["a"],))
            third = wk.view(uid)
            self.assertEqual(len(made), 3)
            self.assertNotIn(pid, [n["id"] for n in third["nodes"]])
        with wk._Db(uid) as con:
            names = {r[1] for r in con.execute("SELECT type, name FROM sqlite_master WHERE type='trigger'")}
        for t in wk.STAND_TABELLEN:
            for e in "iud":
                self.assertIn(f"wk_stand_{t}_{e}", names)

    def test_at_most_bau_most_builds_are_kept(self):
        wk._BAU.clear()
        uids = []
        for i in range(wk.BAU_MOST + 2):
            uid, _ = self.fresh(f"Wtempof{i}")
            wk.view(uid)
            uids.append(uid)
        self.assertLessEqual(len(wk._BAU), wk.BAU_MOST)


class Weg(Base):
    def test_from_both_ends_as_the_whole_walk(self):
        uid, ids = self.fresh("Wtempog")
        a, other = ids["a"], ids["b"]
        pid = lambda i: "%012x" % (0xabd000000000 + i)      # noqa: E731
        with wk._Db(uid) as con:
            con.executemany("INSERT INTO wb_pages (id, title, art, made, changed) VALUES (?, ?, 'Thema', 1, 1)",
                            [(pid(i), "Seite %03d" % i) for i in range(60)])
            e = [(pid(i), pid((i + 1) % 6), a) for i in range(6)]                       # a ring
            e += [(pid(10), pid(i), a if i % 3 else other) for i in range(11, 40)]      # a star
            e += [(pid(i), pid(i + 1), a) for i in range(40, 50)]                      # a chain
            e += [(pid(5), pid(10), a), (pid(3), pid(40), other), (pid(12), pid(13), a), (pid(13), pid(41), a),
                  (pid(0), pid(0), a), (pid(1), pid(2), "ffffffffffff"), (pid(1), pid(2), other)]
            k = [r[0] for r in con.execute("SELECT 'k' || id FROM wk_ent ORDER BY id")]
            e += [(k[0], pid(4), a), (k[1], pid(12), a), (pid(44), k[2], a)]
            con.executemany("INSERT INTO wk_edges (a, b, art, detail, doc, made) VALUES (?, ?, 'betrifft', '', ?, 1)", e)
            con.execute("INSERT OR IGNORE INTO wk_entpage (ent, page) VALUES (?, ?)", (int(k[3][1:]), pid(20)))
        nodes = [pid(i) for i in (0, 1, 2, 3, 4, 5, 10, 11, 12, 20, 30, 40, 42, 44, 49)] + k[:4] + ["%012x" % 0xdead]
        found = 0
        for ents in (False, True):
            helpers.set_config(knowledge_ents=ents)
            for x in nodes:
                for y in nodes:
                    for t in (1, 2, 3, 4):
                        got = wk.weg(uid, x, y, t)
                        self.assertEqual(got, weg_langsam(uid, x, y, t), (ents, x, y, t))
                        found += bool(got and len(got["pages"]) > 3)
        self.assertGreater(found, 50)
        seen = []
        real = wk._kanten_um
        with mock.patch.object(wk, "_kanten_um", lambda con, kn, *x: seen.append(len(kn)) or real(con, kn, *x)):
            self.assertIsNone(wk.weg(uid, pid(40), pid(49)))     # nine steps: both ends stop after WEG_MOST together
        self.assertLessEqual(len(seen), wk.WEG_MOST)


class Nacht(Base):
    def test_the_nightly_check_runs_in_slices_to_the_same_end(self):
        uid, ids = self.fresh("Wtempoh")
        with wk._Db(uid) as con:
            ks = [r[0] for r in con.execute("SELECT 'k' || id FROM wk_ent ORDER BY id")]
            for i in range(12):                              # „wohnt in“ between two companies: against TYPEN
                con.execute("INSERT INTO wk_edges (a, b, art, detail, doc, made) VALUES (?, ?, 'wohnt_in', '', ?, 1)",
                            (ks[0], ks[2], ids["a"]))
            for i in range(5):
                kid = con.execute("INSERT INTO wk_ent (art, name, norm) VALUES ('frist', ?, ?)",
                                  (f"bald{i}", f"bald{i}")).lastrowid
                con.execute("INSERT INTO wk_ment (ent, doc, chunk) SELECT ?, doc, chunk FROM wk_ment LIMIT 1", (kid,))
            con.execute("DELETE FROM wb_state WHERE key IN ('wk_check_at', 'wk_check_pos')")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wk, "NACHT_SCHEIBE", 3), \
                mock.patch.object(wk, "NACHT_FRISTEN", 2):
            steps = []
            for _ in range(30):
                r = wk.nachtpruefung(uid)
                steps.append(r)
                if r["fertig"]:
                    break
        self.assertTrue(steps[-1]["fertig"])
        self.assertGreater(len(steps), 4)
        self.assertEqual(sum(s["typ"] for s in steps), 12)
        self.assertEqual(sum(s["frist"] for s in steps), 5)
        self.assertTrue(all(s["frist"] <= 2 for s in steps))
        self.assertIn("| weiter", out.getvalue())
        with wk._Db(uid) as con:
            self.assertFalse(con.execute("SELECT 1 FROM wk_edges WHERE art='wohnt_in'").fetchone())
            self.assertFalse(con.execute("SELECT 1 FROM wb_state WHERE key='wk_check_pos'").fetchone())
            self.assertTrue(con.execute("SELECT 1 FROM wk_edges WHERE art='betrifft'").fetchone())

    def test_due_once_goes_on_with_the_next_slice(self):
        uid, ids = self.fresh("Wtempoi")
        helpers.set_config(knowledge_map_day=200)
        night = __import__("datetime").datetime(2027, 2, 10, 3, 0).timestamp()
        with wk._Db(uid) as con:
            con.execute("DELETE FROM wb_state WHERE key IN ('wk_check_at', 'wk_check_pos')")
            for i in range(7):
                con.execute("INSERT INTO wk_edges (a, b, art, detail, doc, made) SELECT 'k' || MIN(id), 'k' || MAX(id), "
                            "'betrifft', '', ?, 1 FROM wk_ent", (ids["a"],))
        import suchpruefung
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(wk, "NACHT_SCHEIBE", 3), \
                mock.patch.object(suchpruefung, "night", lambda now: True), \
                mock.patch.object(wk.profiles, "user_ids", return_value=[uid]):
            got = [run(wk.due_once(night + i)) for i in range(6)]
        self.assertEqual(got[:3], ["wissenskarte-pruefung"] * 3)          # 8 connections in slices of 3
        self.assertNotIn("wissenskarte-pruefung", got[4:])                # then once a night is done


class Doppelt(unittest.TestCase):
    """The quiet run for doubles (wissensdoppelt.lauf) in slices ends as the run in one go."""
    FIRST = ("Anna", "Bernd", "Carla", "Dieter", "Emil", "Frieda", "Gustav", "Hanna", "Ida", "Jonas")

    def setUp(self):
        helpers.keep_chat(self, *KEYS)
        helpers.set_config(**ON)
        self.addCleanup(wd._scheibe.clear)

    def punkte(self, name):
        profile(name)
        uid = uid_of(name)
        with wd._Db(uid) as con:
            for t in ("wk_edges", "wk_ent", "wk_ment", "wk_entdocs", "wk_entblock", "wk_entpage") + wd.TABELLEN:
                con.execute(f"DELETE FROM {t}")
            names = [("person", f"{self.FIRST[i % 10]} {chr(97 + i // 10 % 26)}{chr(97 + i // 7 % 26)}mann{i}")
                     for i in range(600)]
            names += [("person", f"{n.split()[1]}, {n.split()[0]}") for _, n in names[:25]]      # "gleich": merged
            names += [("person", "Herr Dominik Bornhäuser"), ("person", "Dominik Bornhäußer"), ("person", "D. Bornhäuser"),
                      ("firma", "Müller GmbH"), ("firma", "Müller AG"), ("ort", "Hauptstr. 5"), ("ort", "Hauptstraße 5")]
            for art, n in names:
                con.execute("INSERT INTO wk_ent (art, name, norm, alias) VALUES (?, ?, ?, '[]')", (art, n, wk.ent_norm(n)))
        return uid

    @staticmethod
    def stand(uid):
        with wd._Db(uid) as con:
            ents = sorted((r[0], r[1], r[2]) for r in con.execute("SELECT art, name, alias FROM wk_ent"))
            n = {r[0]: r[1] for r in con.execute("SELECT id, name FROM wk_ent")}
            paare = sorted((n[r[0]], n[r[1]], r[2]) for r in con.execute("SELECT a, b, grund FROM wk_paar"))
        return ents, paare

    def test_the_run_in_slices_ends_as_the_run_in_one(self):
        eins, scheiben = self.punkte("Wtempod1"), self.punkte("Wtempod2")
        with contextlib.redirect_stdout(io.StringIO()):
            ganz = wd.lauf(eins, DAY)
            got = []
            for _ in range(5000):                     # no time: every slice stops at its first look at the clock
                got.append(wd.lauf(scheiben, DAY, 0.0, True))
                if not got[-1]["weiter"]:
                    break
        self.assertTrue(ganz["fertig"])
        self.assertTrue(got[-1]["fertig"])
        self.assertGreater(len(got), 20)
        self.assertEqual(sum(c["auto"] for c in got), ganz["auto"])
        self.assertEqual(sum(c["neu"] for c in got), ganz["neu"])
        self.assertEqual(ganz["auto"], 26)
        self.assertGreaterEqual(ganz["neu"], 3)
        self.assertEqual(self.stand(scheiben), self.stand(eins))
        self.assertLess(max(c["auto"] for c in got), wd.ZUSAMMEN_SCHRITT)      # one merge per look at the clock,
        self.assertGreaterEqual(sum(c["auto"] == 1 for c in got), 26 - wd.ZUSAMMEN_SCHRITT)    # the last few at once
        self.assertTrue(all(c["vergleiche"] <= wd.VERGLEICHE_SCHRITT + wd.NACHBARN_MOST for c in got))
        self.assertNotIn(scheiben, wd._scheibe)

    def test_due_once_goes_on_and_counts_one_run(self):
        uid = self.punkte("Wtempod3")
        wd._sig.pop(uid, None)
        day = DAY + 86400 * 3
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wd, "SCHEIBE_S", 0.0), \
                mock.patch.object(wd.profiles, "user_ids", return_value=[uid]):
            for _ in range(5000):
                self.assertEqual(run(wd.due_once(day)), "wissensdoppelt")
                if uid not in wd._scheibe:
                    break
            self.assertIsNone(run(wd.due_once(day)))                        # done and nothing changed: no run
        log = out.getvalue()
        self.assertIn("vergleiche | weiter", log)
        self.assertRegex(log.strip().splitlines()[-1], r"wissen: wissenskarte doppelt geprueft \| \d+ zusammengefuehrt "
                                                       r"\| \d+ vorschlaege neu \| \d+ offen \| \d+ weg \| \d+ vergleiche \| fertig$")
        day_key = __import__("datetime").datetime.fromtimestamp(day).strftime("%Y-%m-%d")
        self.assertEqual(documents.count_today(uid, day_key, key="wkdoppelt"), 1)    # the slices of one run count once

    def test_changed_points_start_the_run_again(self):
        uid = self.punkte("Wtempod4")
        with contextlib.redirect_stdout(io.StringIO()):
            while wd.lauf(uid, DAY, 0.0, True)["weiter"] and wd._scheibe[uid]["teil"] != "vergleiche":
                pass
            self.assertEqual(wd._scheibe[uid]["teil"], "vergleiche")
            with wd._Db(uid) as con:
                con.execute("INSERT INTO wk_ent (art, name, norm, alias) VALUES ('person', 'Neu Punkt', 'neu punkt', '[]')")
            self.assertTrue(wd.lauf(uid, DAY, 0.0, True)["weiter"])
        self.assertEqual(wd._scheibe[uid]["teil"], "zusammen")
        with wd._Db(uid) as con:
            wd.leeren(con)
        self.assertEqual(wd._scheibe, {})                                   # no names stay in the memory


class Grenzen(unittest.TestCase):
    def test_the_limits_of_the_map_and_the_book(self):
        self.assertEqual((wissensbuch.MAX_PAGES, wk.MAX_EDGES, wk.MAX_ENT), (3000, 25000, 15000))
        self.assertEqual((wk.VIEW_NODES, wk.VIEW_EDGES), (150, 400))      # the visible part stays as it was
        self.assertEqual((wk.DAY, wk.ENT_DAY), (200, 200))                # the daily limits too (and stay settable)


if __name__ == "__main__":
    unittest.main()
