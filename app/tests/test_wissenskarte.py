"""Wissenskarte (wissenskarte.py, plan wissensgraph/plan.md, Stufe 1): off by default and never for guests, built on the
Wissensbuch; the panel's fixed rules for every connection the model proposes (only offered pages, a kind from the
fixed list, both ends named in the source piece, a cause only with a word of cause, the detail's Zahlenprobe, limits),
"Stimmt nicht" for good, documents that leave take their connections, the visible part with its fixed limits, the
export as Mermaid and Graphviz text that cannot carry a statement, the live line and the journal with fixed words and
numbers only. No test depends on the clock."""
import asyncio
import contextlib
import datetime
import io
import json
import re
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import features  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import wissensbuch  # noqa: E402
import wissenskarte  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_ui_browser import async_playwright, browser_ok, chromium  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
DAY = datetime.datetime(2027, 2, 9, 14, 0).timestamp()
INS = ("Versicherungsschein der Nordstern Versicherung für den VW Golf, Kennzeichen HB-DB 482. Wegen des Parkschadens "
       "vom 14.11.2025 steigt der Jahresbeitrag um 18 Prozent auf 612 Euro.")
HOUSE = ("Mietvertrag für die Wohnung in der Lindenstraße 4 in Bremen. Vermieter ist die Hansa Wohnbau. "
         "Die Miete beträgt 980 Euro im Monat.")


def run(coro):
    return asyncio.run(coro)


def profile(name, pin="2468"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def book(*pages):
    return {"seiten": [{"titel": t, "art": a, "saetze": [{"text": x, "quelle": 1}]} for t, a, x in pages]}


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "documents", "doc_semantic", "doc_brief", "knowledge_book", "knowledge_book_day", "knowledge_map", "knowledge_map_day")
        helpers.set_config(documents=True, doc_semantic=False, doc_brief=False, knowledge_book=True, knowledge_book_day=40,
                           knowledge_map=True, knowledge_map_day=200)
        wissenskarte._live.update(at=0.0, d=None)

    def fresh(self, name):
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with wissenskarte._Db(uid) as con:
            for t in ("wb_pages", "wb_sent", "wb_docs", "wb_block", "wb_log", "wb_check", "wb_state", "wb_kiwix",
                      "wk_edges", "wk_docs", "wk_block"):
                con.execute(f"DELETE FROM {t}")
        a = documents.add(uid, "Versicherung.txt", INS.encode(), text=INS)["id"]
        with mock.patch.object(wissensbuch, "ask_model", mock.AsyncMock(return_value=book(
                ("VW Golf", "Ding", "Der VW Golf hat das Kennzeichen HB-DB 482."),
                ("Nordstern Versicherung", "Firma", "Die Nordstern Versicherung versichert den VW Golf."),
                ("Parkschaden", "Thema", "Der Parkschaden war am 14.11.2025.")))), contextlib.redirect_stdout(io.StringIO()):
            run(wissensbuch.work_in(uid, DAY))
        return c, uid, a

    def ids(self, uid):
        return {p["title"]: p["id"] for p in wissensbuch.index(uid)}

    def proposal(self, uid, doc, *edges):
        """[(from title, to title, kind, piece, detail)] → the model's JSON with the K numbers the panel offers."""
        text = "\n\n".join(f"[S{n}] {t}" for n, _, t in wissensbuch.pieces(uid, doc))
        nodes = wissenskarte.nodes_for(uid, doc, text)
        k = {p["title"]: f"K{i + 1}" for i, p in enumerate(nodes)}
        return {"verbindungen": [{"von": k.get(a, "K99"), "nach": k.get(b, "K99"), "art": art, "quelle": q, "detail": d}
                                 for a, b, art, q, d in edges]}

    def work(self, uid, got):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wissenskarte, "ask_model", mock.AsyncMock(return_value=got)):
            r = run(wissenskarte.work_in(uid, DAY))
        return r, out.getvalue()


class Defaults(Base):
    def test_off_by_default_built_on_the_book_and_never_for_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["knowledge_map"], False)
        self.assertEqual(ch["knowledge_map_day"], 200)
        self.assertEqual(wissenskarte.day_limit(), 200)
        for bad in (4, 501, "200", True):                   # the admin's number is checked like the book's
            cfg = ADMIN.get("/api/config").json()
            cfg["chat"]["knowledge_map_day"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, bad)
        self.assertNotIn("wissenskarte", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["wissenskarte"].parent, "wissensbuch")
        self.assertEqual(features.BY_KEY["wissenskarte"].me, "wbbox")
        c, uid, _ = self.fresh("Wkaus")
        helpers.set_config(knowledge_map=False)
        self.assertEqual(c.get("/api/profile/wissenskarte").status_code, 403)
        self.assertEqual(ADMIN.get("/api/admin/wissenskarte").json(), {"on": False})
        self.assertIsNone(run(wissenskarte.due_once(DAY)))
        helpers.set_config(knowledge_map=True, knowledge_book=False)      # the map needs the book
        self.assertEqual(c.get("/api/profile/wissenskarte").status_code, 403)
        helpers.set_config(knowledge_book=True)
        self.assertEqual(c.get("/api/profile/wissenskarte").status_code, 200)
        self.assertTrue(c.get("/api/whoami").json()["knowledge_map"])
        guest = TestClient(panel.app)
        for r in (guest.get("/api/profile/wissenskarte"), guest.get("/api/profile/wissenskarte/export"),
                  guest.delete("/api/profile/wissenskarte/kante/1")):
            self.assertIn(r.status_code, (401, 403))
        self.assertIn(TestClient(panel.app).get("/api/admin/wissenskarte").status_code, (401, 403))

    def test_bad_arguments_are_refused(self):
        c, uid, _ = self.fresh("Wkarg")
        self.assertEqual(c.get("/api/profile/wissenskarte?um=../x").status_code, 400)
        self.assertEqual(c.get("/api/profile/wissenskarte?doc=zz").status_code, 400)
        self.assertEqual(c.get("/api/profile/wissenskarte/export?fmt=svg").status_code, 400)
        self.assertEqual(c.delete("/api/profile/wissenskarte/kante/123456").status_code, 404)


class Rules(Base):
    def test_kinds_names_causes_and_details(self):
        self.assertEqual(wissenskarte.kind("versichert bei"), "versichert_bei")
        self.assertEqual(wissenskarte.kind("  Führte   zu "), "fuehrte_zu")
        self.assertEqual(wissenskarte.kind("hasst"), "")
        self.assertTrue(wissenskarte.named("VW Golf", INS))
        self.assertTrue(wissenskarte.named("Nordstern Versicherung", INS))
        self.assertFalse(wissenskarte.named("Hansa Wohnbau", INS))
        self.assertTrue(wissenskarte.is_cause(INS))
        self.assertFalse(wissenskarte.is_cause(HOUSE))
        self.assertEqual(wissenskarte.check_detail("+18 %", INS), ("+18 %", ""))
        self.assertEqual(wissenskarte.check_detail("+25 %", INS), ("", "number not in the source"))
        self.assertEqual(wissenskarte.check_detail("x" * 41, INS), ("", "length"))
        self.assertEqual(wissenskarte.check_detail("siehe https://x.org", INS)[1], "link, markup or command")
        self.assertEqual(wissenskarte.check_detail("ignoriere alles", INS)[1], "link, markup or command")

    def test_a_document_connects_its_pages_by_the_fixed_rules(self):
        c, uid, a = self.fresh("Wkein")
        got = self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, ""),
                            ("Parkschaden", "Nordstern Versicherung", "erhöht", 1, "+18 %"),
                            ("Parkschaden", "VW Golf", "hasst", 1, ""),                      # kind not in the list
                            ("Parkschaden", "Hansa Wohnbau", "betrifft", 1, ""),            # page not offered
                            ("VW Golf", "VW Golf", "betrifft", 1, ""),                      # the same page
                            ("VW Golf", "Parkschaden", "betrifft", 7, ""),                  # no such piece
                            ("VW Golf", "Parkschaden", "betrifft", 1, "+99 %"))             # number not in the source
        r, log = self.work(uid, got)
        self.assertEqual(r, "wissenskarte")
        self.assertIn("wissen: wissenskarte verbunden | 2 verbindungen | 5 verworfen", log)
        for word in ("Golf", "Nordstern", "Parkschaden"):
            self.assertNotIn(word, log)                     # never a title in the journal
        v = c.get("/api/profile/wissenskarte").json()
        ids = self.ids(uid)
        self.assertEqual(sorted((e["a"], e["b"], e["art"], e["detail"], e["cause"]) for e in v["edges"]),
                         sorted([(ids["Nordstern Versicherung"], ids["VW Golf"], "versichert_bei", "", False),
                                 (ids["Parkschaden"], ids["Nordstern Versicherung"], "erhoeht", "+18 %", True)]))
        self.assertEqual({e["name"] for e in v["edges"]}, {"Versicherung.txt"})
        self.assertEqual((v["total"]["edges"], v["wait"], v["cut"]), (2, 0, False))
        self.assertIn("versichert_bei", v["arten"])
        self.assertIsNone(wissenskarte.next_doc(uid))       # done: not again
        self.assertEqual(wissenskarte.counts(uid)["verbindungen"], 2)
        self.assertGreaterEqual(ADMIN.get("/api/admin/wissenskarte").json()["verbindungen"], 2)   # summed over profiles

    def test_a_cause_needs_a_word_of_cause_in_its_source(self):
        c, uid, a = self.fresh("Wkgrund")
        hb = documents.add(uid, "Miete.txt", HOUSE.encode(), text=HOUSE)["id"]
        with mock.patch.object(wissensbuch, "ask_model", mock.AsyncMock(return_value=book(
                ("Wohnung Lindenstraße", "Ort", "Die Wohnung liegt in der Lindenstraße 4 in Bremen."),
                ("Hansa Wohnbau", "Firma", "Vermieter ist die Hansa Wohnbau.")))), contextlib.redirect_stdout(io.StringIO()):
            run(wissensbuch.work_in(uid, DAY))
        with wissenskarte._Db(uid) as con:                  # the insurance is done, so the lease comes next
            con.execute("INSERT INTO wk_docs (doc, state, at, sig) SELECT doc, 'ok', 0, sig FROM wb_docs WHERE doc=?", (a,))
        _, log = self.work(uid, self.proposal(uid, hb, ("Hansa Wohnbau", "Wohnung Lindenstraße", "verursacht", 1, ""),
                                              ("Wohnung Lindenstraße", "Hansa Wohnbau", "Vertrag mit", 1, "980 Euro")))
        self.assertIn("| 1 verbindungen | 1 verworfen | no_cause=1", log)

    def test_wrong_for_good_documents_leave_and_reading_again(self):
        c, uid, a = self.fresh("Wkweg")
        got = self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, ""))
        self.work(uid, got)
        e = c.get("/api/profile/wissenskarte").json()["edges"][0]
        self.assertEqual(c.delete(f"/api/profile/wissenskarte/kante/{e['id']}").status_code, 200)
        self.assertEqual(c.get("/api/profile/wissenskarte").json()["edges"], [])
        with wissenskarte._Db(uid) as con:                  # worked in again: the same connection stays out
            con.execute("DELETE FROM wk_docs")
        _, log = self.work(uid, got)
        self.assertIn("| 0 verbindungen | 1 verworfen | blocked=1", log)
        # the book's fingerprint changes (read again): the map works the document in again
        with wissenskarte._Db(uid) as con:
            con.execute("DELETE FROM wk_block")
            con.execute("UPDATE wb_docs SET sig='other'")
        self.assertEqual(wissenskarte.next_doc(uid)[0], a)
        self.work(uid, got)
        self.assertEqual(len(c.get("/api/profile/wissenskarte").json()["edges"]), 1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(c.delete(f"/api/profile/docs/{a}").json()["removed"])   # documents.on_gone: at once
        self.assertIn("wissen: wissenskarte quelle weg | 1 dokumente | 1 verbindungen | geloescht", out.getvalue())
        self.assertEqual(wissenskarte.counts(uid)["verbindungen"], 0)

    def test_the_limits_per_document_and_profile(self):
        c, uid, a = self.fresh("Wkgrenze")
        many = self.proposal(uid, a, *[("Nordstern Versicherung", "VW Golf", k, 1, "") for k in
                                       ("versichert bei", "Vertrag mit", "betrifft", "gehört zu", "besitzt")])
        with mock.patch.object(wissenskarte, "EDGES_PER_DOC", 3):
            _, log = self.work(uid, many)
        self.assertIn("| 3 verbindungen | 2 verworfen | limit=2", log)
        with wissenskarte._Db(uid) as con:
            con.execute("DELETE FROM wk_docs")
        with mock.patch.object(wissenskarte, "MAX_EDGES", 3):
            _, log = self.work(uid, many)
        self.assertIn("| 0 verbindungen |", log)
        with mock.patch.object(wissenskarte, "VIEW_NODES", 2):
            v = c.get("/api/profile/wissenskarte").json()
        self.assertEqual(len(v["nodes"]), 2)

    def test_a_failing_model_marks_the_document_and_the_daily_limit_holds(self):
        c, uid, a = self.fresh("Wkfehler")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wissenskarte, "ask_model", mock.AsyncMock(side_effect=OSError("x"))):
            self.assertEqual(run(wissenskarte.work_in(uid, DAY)), "wissenskarte")
        self.assertIn("wissen: wissenskarte fehler | OSError", out.getvalue())
        self.assertIsNone(wissenskarte.next_doc(uid))
        helpers.set_config(knowledge_book_day=200, knowledge_map_day=5)   # the map's own limit counts, not the book's
        day = datetime.datetime.fromtimestamp(DAY).strftime("%Y-%m-%d")
        while documents.count_today(uid, day, key="wkarte") < 5:
            documents.count_today(uid, day, add=1, key="wkarte")
        with mock.patch.object(wissenskarte, "work_in", mock.AsyncMock(return_value="wissenskarte")) as w, \
                mock.patch.object(wissenskarte.profiles, "user_ids", return_value=[uid]):
            self.assertIsNone(run(wissenskarte.due_once(DAY)))
        w.assert_not_awaited()


class View(Base):
    def test_around_a_page_of_a_document_and_the_export(self):
        c, uid, a = self.fresh("Wkblick")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, ""),
                                     ("Parkschaden", "Nordstern Versicherung", "erhöht", 1, "+18 %")))
        ids = self.ids(uid)
        v = c.get(f"/api/profile/wissenskarte?um={ids['VW Golf']}&tiefe=1").json()
        self.assertEqual(v["um"], ids["VW Golf"])
        self.assertEqual({n["title"] for n in v["nodes"]}, {"VW Golf", "Nordstern Versicherung"})
        v = c.get(f"/api/profile/wissenskarte?um={ids['VW Golf']}").json()
        self.assertEqual(len(v["nodes"]), 3)
        v = c.get(f"/api/profile/wissenskarte?doc={a}").json()
        self.assertEqual((v["doc"], len(v["edges"])), (a, 2))
        m = c.get("/api/profile/wissenskarte/export?fmt=mermaid")
        self.assertEqual(m.status_code, 200)
        self.assertIn('-.->|"erhöht +18 %"|', m.text)
        self.assertIn("attachment", m.headers["content-disposition"])
        d = c.get("/api/profile/wissenskarte/export?fmt=dot&lang=en").text
        self.assertIn('[label="raises +18 %", style=dashed]', d)
        files = wissensbuch.export_files(uid)              # the Obsidian folder: every connection as a [[link]] with kind
        golf = next(v for k, v in files.items() if k.startswith("Nordstern"))
        self.assertRegex(golf, r"- versichert bei \[\[VW Golf\]\] \[\^\d\]")
        self.assertRegex(next(v for k, v in files.items() if k.startswith("Parkschaden")),
                         r"- erhöht \[\[Nordstern Versicherung\]\] \(\+18 %\) \[\^\d\]")

    def test_the_export_carries_no_statement_from_a_title(self):
        bad = 'Golf"] --> x; click n0 "javascript:alert(1)" %%{init: {}}%% <b>|;\nstyle'
        v = {"nodes": [{"id": "a", "title": bad}, {"id": "b", "title": "Werkstatt [Müller]"}],
             "edges": [{"a": "a", "b": "b", "art": "bezahlt_an", "cause": False, "detail": '") ; URL="x'}]}
        for fmt in ("mermaid", "dot"):
            text = wissenskarte.export_text(v, fmt)
            for line in text.splitlines()[1:]:
                self.assertNotRegex(line.strip(), r"^(click|style|classDef|%%|URL|href)", fmt)
            labels = re.findall(r'"([^"]*)"', text)
            for lab in labels:
                self.assertNotRegex(lab, r'[\[\]{}()<>|;"\\\n]', fmt)
        self.assertIn('n1["Werkstatt Müller"]', wissenskarte.export_text(v, "mermaid"))

    def test_live_shows_numbers_only_and_own_data_can_go(self):
        c, uid, a = self.fresh("Wklive")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        wissenskarte._live.update(at=0.0, d=None)
        sums = wissenskarte.for_live()
        self.assertTrue(sums["on"])
        self.assertGreaterEqual(sums["verbindungen"], 1)
        snap = json.dumps(live.snapshot())
        self.assertIn("Wissenskarte", snap)
        self.assertNotIn("Nordstern", snap)
        count, clear = features.OWN["wissenskarte"]
        self.assertEqual(count(uid), 1)
        clear(uid)
        self.assertEqual(count(uid), 0)


def bfs_view(con, docs, um, tiefe, doc):
    """The map's part as view() chose it before V01.1.242 (all connections in Python, a walk ring by ring): the yardstick
    the queries in SQLite must meet (Stufe 1)."""
    pages = {r["id"]: dict(r) for r in con.execute("SELECT id, title, art FROM wb_pages")}
    rows = [dict(r) for r in con.execute("SELECT * FROM wk_edges ORDER BY id")]
    rows = [e for e in rows if e["a"] in pages and e["b"] in pages and e["doc"] in docs]
    deg = {}
    for e in rows:
        deg[e["a"]] = deg.get(e["a"], 0) + 1
        deg[e["b"]] = deg.get(e["b"], 0) + 1
    if um and um in pages:
        pick, ring = [um], {um}
        for _ in range(tiefe):
            nxt = set()
            for e in rows:
                if e["a"] in ring and e["b"] not in pick:
                    nxt.add(e["b"])
                if e["b"] in ring and e["a"] not in pick:
                    nxt.add(e["a"])
            pick += sorted(nxt, key=lambda x: (-deg.get(x, 0), pages[x]["title"]))
            ring = nxt
    elif doc and doc in docs:
        pick = sorted({x for e in rows if e["doc"] == doc for x in (e["a"], e["b"])}, key=lambda x: (-deg.get(x, 0), pages[x]["title"]))
    else:
        pick = sorted(deg, key=lambda x: (-deg[x], pages[x]["title"]))
    keep = set(pick[:wissenskarte.VIEW_NODES])
    edges = [e["id"] for e in rows if e["a"] in keep and e["b"] in keep and (not doc or um or e["doc"] == doc)]
    per_doc = {}
    for e in rows:
        per_doc[e["doc"]] = per_doc.get(e["doc"], 0) + 1
    return (pick[:wissenskarte.VIEW_NODES], [deg.get(p, 0) for p in pick[:wissenskarte.VIEW_NODES]],
            edges[:wissenskarte.VIEW_EDGES], len(pick) > wissenskarte.VIEW_NODES or len(edges) > wissenskarte.VIEW_EDGES,
            (len(deg), len(rows)), sorted(per_doc.items(), key=lambda x: -x[1])[:40])


class Rekursiv(Base):
    """Stufe 1 (V01.1.242): view() walks in SQLite (WITH RECURSIVE, at most two steps, UNION against rings) and
    answers as before; weg() and rund_um() are fixed queries with parameters only."""
    def graph(self, name):
        """A ring of 6 pages, a star of 220 pages around one hub, a chain, and connections that do not count (a
        document of nobody, a page that is gone): more than VIEW_NODES points and VIEW_EDGES connections."""
        c, uid, a = self.fresh(name)
        other = documents.add(uid, "Miete.txt", HOUSE.encode(), text=HOUSE)["id"]
        pid = lambda i: "%012x" % (0xabc000000000 + i)
        with wissenskarte._Db(uid) as con:
            con.executemany("INSERT INTO wb_pages (id, title, art, made, changed) VALUES (?, ?, 'Thema', 1, 1)",
                            [(pid(i), "Seite %03d" % ((i * 37) % 240)) for i in range(240)])
            e = [(pid(i), pid((i + 1) % 6), a) for i in range(6)]                            # ring 0-5
            e += [(pid(10), pid(i), a if i % 3 else other) for i in range(11, 231)]          # star around 10
            e += [(pid(i), pid(i + 1), a) for i in range(231, 239)]                         # chain 231-239
            e += [(pid(i), pid(10), other) for i in range(11, 200, 2)]                      # second edges into the hub
            e += [(pid(i), pid(10), a) for i in range(11, 231)] * 2                         # and two more for each
            e += [(pid(5), pid(10), a), (pid(3), pid(231), other), (pid(0), pid(0), a)]     # bridges and a loop
            e += [(pid(1), pid(2), "ffffffffffff"), (pid(1), "%012x" % 0xdead, a)]          # do not count
            con.executemany("INSERT INTO wk_edges (a, b, art, detail, doc, made) VALUES (?, ?, 'betrifft', '', ?, 1)", e)
        return c, uid, a, other, pid

    def same(self, uid, um="", tiefe=2, doc=""):
        v = wissenskarte.view(uid, um, tiefe, doc)
        with wissenskarte._Db(uid) as con:
            want = bfs_view(con, wissensbuch._own_ready(con), um, tiefe, doc)
        got = ([n["id"] for n in v["nodes"]], [n["deg"] for n in v["nodes"]], [e["id"] for e in v["edges"]], v["cut"],
               (v["total"]["nodes"], v["total"]["edges"]), [(d["id"], d["n"]) for d in v["docs"]])
        self.assertEqual(got, want, (um, tiefe, doc))
        return v

    def test_the_view_in_sqlite_answers_as_the_walk_in_python(self):
        c, uid, a, other, pid = self.graph("Wkrekursiv")
        v = self.same(uid)
        self.assertTrue(v["cut"])
        self.assertEqual(len(v["nodes"]), wissenskarte.VIEW_NODES)
        self.assertEqual(len(v["edges"]), wissenskarte.VIEW_EDGES)          # more were there: cut at the limit
        for um in (pid(0), pid(3), pid(10), pid(231), pid(235), pid(150)):
            for tiefe in (1, 2):
                self.same(uid, um, tiefe)
        self.same(uid, doc=a)
        self.same(uid, doc=other)
        self.same(uid, pid(0), 2, a)
        self.same(uid, "%012x" % 0xdead)                    # a page that is gone: the best connected ones
        self.assertTrue(self.same(uid, pid(10), 1)["cut"])
        self.assertEqual(c.get(f"/api/profile/wissenskarte?um={pid(235)}&tiefe=1").json()["nodes"][0]["id"], pid(235))

    def test_rings_end_and_depth_holds(self):
        c, uid, a, other, pid = self.graph("Wkzyklus")
        got = wissenskarte.rund_um(uid, pid(0), 4)
        for i in range(6):
            self.assertEqual(got[pid(i)], min(i, 6 - i))     # around the ring both ways, each page once
        self.assertEqual(got[pid(10)], 2)                    # 0 → 5 → 10
        self.assertEqual(wissenskarte.rund_um(uid, pid(0)), {pid(0): 0, pid(1): 1, pid(5): 1})
        self.assertEqual(max(wissenskarte.rund_um(uid, pid(231), 99).values()), wissenskarte.WEG_MOST)
        self.assertNotIn(pid(239), wissenskarte.rund_um(uid, pid(231), 99))   # five steps away: past the limit
        self.assertNotIn("%012x" % 0xdead, wissenskarte.rund_um(uid, pid(1), 4))

    def test_the_shortest_way_is_found_and_always_the_same(self):
        c, uid, a, other, pid = self.graph("Wkweg")
        w = wissenskarte.weg(uid, pid(0), pid(3))
        self.assertEqual(len(w["pages"]), 4)                 # three steps, either way round the ring
        self.assertEqual(w["pages"], [pid(0), pid(1), pid(2), pid(3)])
        self.assertEqual(w, wissenskarte.weg(uid, pid(0), pid(3)))
        with wissenskarte._Db(uid) as con:
            for (x, y), eid in zip(zip(w["pages"], w["pages"][1:]), w["edges"]):
                r = con.execute("SELECT a, b FROM wk_edges WHERE id=?", (eid,)).fetchone()
                self.assertEqual({r[0], r[1]}, {x, y})
        self.assertEqual(wissenskarte.weg(uid, pid(0), pid(231))["pages"], [pid(0), pid(1), pid(2), pid(3), pid(231)])
        self.assertEqual(len(wissenskarte.weg(uid, pid(1), pid(12))["pages"]), 5)      # 1 → 0 → 5 → 10 → 12
        self.assertIsNone(wissenskarte.weg(uid, pid(0), pid(3), tiefe=2))
        self.assertIsNone(wissenskarte.weg(uid, pid(231), pid(239)))                   # eight steps: past WEG_MOST
        self.assertEqual(wissenskarte.weg(uid, pid(4), pid(4)), {"pages": [pid(4)], "edges": []})
        self.assertIsNone(wissenskarte.weg(uid, pid(1), "%012x" % 0xdead))             # a page that is gone

    def test_only_ids_go_in_as_parameters(self):
        c, uid, a, other, pid = self.graph("Wkfest")
        for bad in ("x' OR 1=1 --", pid(0) + "'", "", None, 7, "ABCDEF000000", pid(0) + "; DROP TABLE wk_edges"):
            self.assertEqual(wissenskarte.rund_um(uid, bad), {}, bad)
            self.assertIsNone(wissenskarte.weg(uid, bad, pid(1)), bad)
            self.assertIsNone(wissenskarte.weg(uid, pid(1), bad), bad)
        with wissenskarte._Db(uid) as con:
            self.assertGreater(con.execute("SELECT COUNT(*) FROM wk_edges").fetchone()[0], 400)
        for sql in (wissenskarte._COUNTS, wissenskarte._OK, wissenskarte._UM):
            self.assertNotIn("{", sql)
            self.assertNotIn("%", sql)
        self.assertEqual(wissenskarte._UM.count("json_each(?)"), 2)                  # the ring of a step is one parameter
        with wissenskarte._Db(uid) as con:                                            # a step goes over the indexes on a and b
            for ents in (False, True):
                plan = " ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + wissenskarte._SQL[ents][2], ("[]", "[]")))
                self.assertIn("USING INDEX wk_edges_a", plan)
                self.assertIn("USING INDEX wk_edges_b", plan)
                self.assertNotIn("SCAN e", plan)


if __name__ == "__main__":
    unittest.main()


class Vorziehen(Base):
    """Stufe 2 (Dominik 2026-11-11 „ok“): „Zuerst einarbeiten“ puts a waiting document first in the book, the map and
    the points; only own searched ready documents, the map's ones never again, at most VOR_MOST wishes."""
    def docs(self, uid):
        b = documents.add(uid, "Miete.txt", HOUSE.encode(), text=HOUSE)["id"]
        c = documents.add(uid, "Miete2.txt", (HOUSE + " Kaution 2000 Euro.").encode(), text=HOUSE + " Kaution 2000 Euro.")["id"]
        return b, c

    def test_a_wished_document_goes_first_everywhere(self):
        cl, uid, a = self.fresh("Wkvor")
        b, c = self.docs(uid)
        first = wissensbuch.next_doc(uid)[0]
        other = c if first == b else b
        v = cl.get("/api/profile/wissenskarte").json()
        self.assertEqual({w["id"] for w in v["warten"]}, {a, b, c})
        self.assertEqual(v["warten_n"], 3)
        self.assertFalse(any(w["vor"] for w in v["warten"]))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cl.post(f"/api/profile/wissenskarte/vorziehen/{other}").status_code, 200)
        self.assertIn("wissen: wissenskarte vorgezogen | 1 dokument", out.getvalue())
        self.assertEqual(wissensbuch.next_doc(uid)[0], other)          # the book takes it first
        v = cl.get("/api/profile/wissenskarte").json()
        self.assertEqual((v["warten"][0]["id"], v["warten"][0]["vor"]), (other, True))
        with wissenskarte._Db(uid) as con:                               # the map and the points take it first too
            for d, at in ((b, DAY + 1), (c, DAY + 2)):
                con.execute("INSERT OR REPLACE INTO wb_docs (doc, state, at, sig) VALUES (?, 'ok', ?, '')", (d, at))
        self.assertEqual(wissenskarte.next_doc(uid)[0], other)
        self.assertEqual(wissenskarte.next_ent_doc(uid)[0], other)
        with wissenskarte._Db(uid) as con:
            con.execute("DELETE FROM wb_vor")
        self.assertEqual(wissenskarte.next_doc(uid)[0], a)               # without a wish the order of before

    def test_only_waiting_own_documents_and_the_limits(self):
        cl, uid, a = self.fresh("Wkvorn")
        b, c = self.docs(uid)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cl.post("/api/profile/wissenskarte/vorziehen/0123456789ab").status_code, 404)
            self.assertEqual(cl.post("/api/profile/wissenskarte/vorziehen/..%2Fx").status_code, 404)
            self.assertEqual(cl.post("/api/profile/wissenskarte/vorziehen/ZZZZ").status_code, 400)
            self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
            self.assertEqual(cl.post(f"/api/profile/wissenskarte/vorziehen/{a}").status_code, 409)     # the map has it
            with wissenskarte._Db(uid) as con:
                con.execute("INSERT OR REPLACE INTO wb_docs (doc, state, at) VALUES (?, 'fehler', ?)", (b, DAY))
            self.assertEqual(cl.post(f"/api/profile/wissenskarte/vorziehen/{b}").status_code, 409)     # the book could not
        self.assertIn("wissen: wissenskarte vorziehen abgelehnt | nicht_da", out.getvalue())
        self.assertIn("wissen: wissenskarte vorziehen abgelehnt | fertig", out.getvalue())
        self.assertIn("wissen: wissenskarte vorziehen abgelehnt | fehler", out.getvalue())
        self.assertIn("wissen: wissenskarte vorziehen abgelehnt | ungueltig", out.getvalue())
        self.assertTrue(next(w for w in cl.get("/api/profile/wissenskarte").json()["warten"] if w["id"] == b)["fehler"])
        other = profile("Wkvorfremd")                                    # never a document of another profile
        self.assertEqual(other.post(f"/api/profile/wissenskarte/vorziehen/{c}").status_code, 404)
        guest = TestClient(panel.app)
        self.assertIn(guest.post(f"/api/profile/wissenskarte/vorziehen/{c}").status_code, (401, 403))
        with mock.patch.object(wissensbuch, "VOR_MOST", 1):              # the oldest wish leaves
            self.assertEqual(wissenskarte.vorziehen(uid, c, now=DAY), "ok")
            with wissenskarte._Db(uid) as con:
                con.execute("UPDATE wb_docs SET state='ok' WHERE doc=?", (b,))
            self.assertEqual(wissenskarte.vorziehen(uid, b, now=DAY + 5), "ok")
            with wissenskarte._Db(uid) as con:
                self.assertEqual([r[0] for r in con.execute("SELECT doc FROM wb_vor")], [b])
        with wissenskarte._Db(uid) as con:                               # an old wish ends after VOR_S
            wissensbuch.vor_tidy(con, DAY + 5 + wissensbuch.VOR_S + 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM wb_vor").fetchone()[0], 0)
        helpers.set_config(knowledge_map=False)
        self.assertEqual(cl.post(f"/api/profile/wissenskarte/vorziehen/{c}").status_code, 403)

    def test_contradictions_are_marked_and_live_counts_numbers_only(self):
        cl, uid, a = self.fresh("Wkwider")
        b, _ = self.docs(uid)
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        golf = self.ids(uid)["VW Golf"]
        with wissenskarte._Db(uid) as con:
            con.execute("UPDATE wb_sent SET mark='widerspruch' WHERE page=?", (golf,))
        v = cl.get("/api/profile/wissenskarte").json()
        self.assertEqual({n["title"]: n["w"] for n in v["nodes"]}, {"VW Golf": 1, "Nordstern Versicherung": 0})
        wissenskarte.vorziehen(uid, b, now=DAY)
        wissenskarte._live.update(at=0.0, d=None)
        sums = wissenskarte.for_live()
        self.assertGreaterEqual(sums["vorgezogen"], 1)
        self.assertGreaterEqual(sums["widerspruch"], 1)
        snap = json.dumps(live.snapshot(), ensure_ascii=False)
        self.assertIn("vorgezogen", snap)
        self.assertIn("Seiten mit Widerspruch", snap)
        self.assertNotIn("Miete", snap)


class Lagen(Base):
    """Stufe 2 „Lagen merken“: a dragged point is pinned per profile (wk_lage) and comes with every part of the map
    until „Lösen“; only points of the map now, finite numbers within the limits, at most LAGE_JE per request."""
    def test_pin_show_and_loosen(self):
        cl, uid, a = self.fresh("Wklage")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        golf, nord = self.ids(uid)["VW Golf"], self.ids(uid)["Nordstern Versicherung"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = cl.post("/api/profile/wissenskarte/lage", json={"lagen": [{"id": golf, "x": 120.25, "y": -40},
                                                                         {"id": "0123456789ab", "x": 1, "y": 1}]})
        self.assertEqual(r.json(), {"ok": True, "n": 1})                  # a point that is not on the map is left out
        self.assertIn("wissen: wissenskarte angeheftet | 1 punkte", out.getvalue())
        self.assertEqual(cl.get("/api/profile/wissenskarte").json()["lage"], {golf: [120.2, -40.0]})
        self.assertEqual(cl.get(f"/api/profile/wissenskarte?um={nord}").json()["lage"], {golf: [120.2, -40.0]})
        other = profile("Wklagefremd")                                   # never in another profile's map
        self.assertEqual(other.get("/api/profile/wissenskarte").json()["lage"], {})
        self.assertEqual(cl.delete(f"/api/profile/wissenskarte/lage/{golf}").json(), {"ok": True, "n": 1})
        self.assertEqual(cl.get("/api/profile/wissenskarte").json()["lage"], {})
        wissenskarte.anheften(uid, [{"id": golf, "x": 1, "y": 2}, {"id": nord, "x": 3, "y": 4}], now=DAY)
        with contextlib.redirect_stdout(out):
            self.assertEqual(cl.delete("/api/profile/wissenskarte/lage").json(), {"ok": True, "n": 2})
        self.assertIn("wissen: wissenskarte geloest | 2 punkte", out.getvalue())
        wissenskarte.anheften(uid, [{"id": golf, "x": 1, "y": 2}], now=DAY)
        count, clear = features.OWN["wissenskarte"]
        clear(uid)                                                       # Daten löschen takes the places too
        with wissenskarte._Db(uid) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM wk_lage").fetchone()[0], 0)

    def test_bad_places_are_refused_and_the_limits_hold(self):
        cl, uid, a = self.fresh("Wklagen")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        golf, nord = self.ids(uid)["VW Golf"], self.ids(uid)["Nordstern Versicherung"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for bad in ([], [{"id": golf, "x": 1}], [{"id": golf, "x": "1", "y": 2}], [{"id": golf, "x": True, "y": 2}],
                        [{"id": golf, "x": wissenskarte.LAGE_WEIT + 1, "y": 0}], [{"id": "../x", "x": 0, "y": 0}],
                        [{"id": golf, "x": 0, "y": 0}] * (wissenskarte.LAGE_JE + 1), "x", None):
                self.assertEqual(cl.post("/api/profile/wissenskarte/lage", json={"lagen": bad}).status_code, 400, bad)
            self.assertEqual(cl.post("/api/profile/wissenskarte/lage", content=b"{" + b" " * 9000 + b"}",
                                     headers={"content-type": "application/json"}).status_code, 413)
            self.assertEqual(cl.delete("/api/profile/wissenskarte/lage/..x").status_code, 400)
        self.assertIn("wissen: wissenskarte anheften abgelehnt | ungueltig", out.getvalue())
        self.assertIsNone(wissenskarte.anheften(uid, [{"id": golf, "x": float("nan"), "y": 0}]))
        self.assertIsNone(wissenskarte.anheften(uid, [{"id": golf, "x": float("inf"), "y": 0}]))
        with mock.patch.object(wissenskarte, "LAGE_MOST", 1):           # the oldest place leaves
            wissenskarte.anheften(uid, [{"id": golf, "x": 1, "y": 1}], now=DAY)
            wissenskarte.anheften(uid, [{"id": nord, "x": 2, "y": 2}], now=DAY + 1)
        with wissenskarte._Db(uid) as con:
            self.assertEqual([r[0] for r in con.execute("SELECT id FROM wk_lage")], [nord])
        guest = TestClient(panel.app)
        self.assertIn(guest.post("/api/profile/wissenskarte/lage", json={"lagen": [{"id": golf, "x": 0, "y": 0}]}).status_code, (401, 403))
        self.assertIn(guest.delete("/api/profile/wissenskarte/lage").status_code, (401, 403))
        helpers.set_config(knowledge_map=False)
        self.assertEqual(cl.delete("/api/profile/wissenskarte/lage").status_code, 403)


class Zeit(Base):
    """Stufe 2 „Zeitraum, Neu seit letzter Woche, Zeitleiste“: connections by the date of their document (its
    Steckbrief, else the day it came) or by when they were made; dates checked by fixed rules, the clock passed in."""
    def test_period_new_and_dates_of_the_timeline(self):
        cl, uid, a = self.fresh("Wkzeit")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        with wissenskarte._Db(uid) as con:
            con.execute("UPDATE docs SET ddate='2025-11', due='2026-01-15' WHERE id=?", (a,))
            con.execute("UPDATE wk_edges SET made=?", (int(DAY),))
        v = cl.get("/api/profile/wissenskarte").json()
        self.assertEqual((v["edges"][0]["datum"], v["edges"][0]["frist"]), ("2025-11-01", "2026-01-15"))
        self.assertEqual(v["zeit"], {"von": "", "bis": "", "neu": 0, "neu_tage": [7, 30]})
        self.assertEqual(len(cl.get("/api/profile/wissenskarte?von=2025-10&bis=2025-11").json()["edges"]), 1)
        self.assertEqual(len(cl.get("/api/profile/wissenskarte?von=2025-11-02").json()["edges"]), 0)
        self.assertEqual(len(cl.get("/api/profile/wissenskarte?bis=2025-10-31").json()["edges"]), 0)
        empty = cl.get("/api/profile/wissenskarte?von=2026-01").json()
        self.assertEqual((empty["nodes"], empty["zeit"]["von"]), ([], "2026-01-01"))
        golf = self.ids(uid)["VW Golf"]                                 # around a point the filter takes connections only
        v = cl.get(f"/api/profile/wissenskarte?um={golf}&von=2026-01").json()
        self.assertEqual((v["um"], v["edges"]), (golf, []))
        self.assertEqual(len(wissenskarte.view(uid, neu=7, now=DAY + 6 * 86400)["edges"]), 1)
        self.assertEqual(len(wissenskarte.view(uid, neu=7, now=DAY + 8 * 86400)["edges"]), 0)
        self.assertEqual(len(wissenskarte.view(uid, neu=30, now=DAY + 8 * 86400)["edges"]), 1)
        m = cl.get("/api/profile/wissenskarte/export?fmt=mermaid&von=2026-01").text      # the export follows the filter
        self.assertNotIn("versichert", m)
        with wissenskarte._Db(uid) as con:                               # without a date of the Steckbrief: the day it came
            con.execute("UPDATE docs SET ddate='', due='x', created=? WHERE id=?", (int(DAY), a))
        v = cl.get("/api/profile/wissenskarte").json()["edges"][0]
        self.assertEqual((v["datum"], v["frist"]), (datetime.date.fromtimestamp(DAY).isoformat(), ""))

    def test_bad_times_are_refused(self):
        cl, uid, _ = self.fresh("Wkzeitn")
        for q in ("von=2025", "von=2025-13", "bis=25-01", "von=2026-02&bis=2026-01", "neu=8", "neu=-7", "neu=99999",
                  "neu=x", "von=2025-01-01%27"):
            self.assertEqual(cl.get("/api/profile/wissenskarte?" + q).status_code, 400, q)
            self.assertEqual(cl.get("/api/profile/wissenskarte/export?" + q).status_code, 400, q)
        self.assertIsNone(wissenskarte.zeit_ok(neu=1))
        self.assertEqual(wissenskarte.zeit_ok("2026-02", "2026-02"), ("2026-02-01", "2026-02-31", 0))


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(Base):
    """Wissensbuch → Karte (Stufe 2): „Wartet“ with „Zuerst“, a dragged point is pinned, the time bar and the timeline;
    fits 390 and 1280 px, nothing scrolls sideways, no script error."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    async def check(self, uid, golf, wait, w, shot=""):
        async with async_playwright() as p:
            exe = chromium()
            br = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
            try:
                ctx = await br.new_context(viewport={"width": w, "height": 900}, locale="de-DE", bypass_csp=True)
                pg = await ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                base = f"http://127.0.0.1:{self.port}"
                await pg.goto(base + "/")
                self.assertEqual((await pg.request.post(base + "/api/profile/login",
                                                        data={"name": "Wkseite2", "pin": "2468"})).status, 200)
                await pg.goto(base + "/")
                await pg.wait_for_function("typeof WK_ON!=='undefined'&&WK_ON&&typeof wkaFocus==='function'", timeout=30000)
                await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                await pg.evaluate("goSec('wbuch');icTabSet('wbuch','karte');wbOpen()")
                await pg.wait_for_function("document.querySelectorAll('#wkview .wkn').length>=2", timeout=30000)
                self.assertEqual(await pg.locator("#wkview .wkn.wid").count(), 1)          # the page with a contradiction
                row = pg.locator(f"#wkview .wkwait:has-text('Miete') button:has-text('Zuerst')")
                if await row.count():
                    await row.first.click()
                    await pg.wait_for_function("document.querySelector('#wkview .wkmsg').textContent.includes('Nächstes')", timeout=30000)
                self.assertIn("kommt zuerst", await pg.inner_text("#wkview .wkside"))
                await pg.locator("#wkview .wkmap").scroll_into_view_if_needed()
                box = await pg.locator(f"#wkview [data-n='{golf}'] rect").bounding_box()
                await pg.mouse.move(box["x"] + 10, box["y"] + 10)
                await pg.mouse.down()
                await pg.mouse.move(box["x"] + 60, box["y"] + 50, steps=5)
                await pg.mouse.up()
                await pg.wait_for_function(f"document.querySelector(\"#wkview [data-n='{golf}']\").classList.contains('pin')", timeout=30000)
                await pg.click("#wkview .wkzeit button:has-text('Neu seit letzter Woche')")
                await pg.wait_for_function("document.querySelector('#wkview .wkzeit button.on')", timeout=30000)
                await pg.click("#wkview .wkzeit .segc button:has-text('Zeitleiste')")
                await pg.wait_for_function("document.querySelectorAll('#wkview .wkt, #wkview .wkleer').length>0", timeout=30000)
                if shot:
                    await pg.screenshot(path=shot)
                self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth"), w)
                self.assertEqual(errors, [])
            finally:
                await br.close()

    def test_wait_pin_and_time_on_the_page(self):
        import os
        c, uid, a = self.fresh("Wkseite2")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        golf = self.ids(uid)["VW Golf"]
        b = documents.add(uid, "Miete.txt", HOUSE.encode(), text=HOUSE)["id"]
        with wissenskarte._Db(uid) as con:
            con.execute("UPDATE wb_sent SET mark='widerspruch' WHERE page=?", (golf,))
            con.execute("UPDATE docs SET ddate='2025-11', due='2026-01-15' WHERE id=?", (a,))
        for w in (390, 1280):
            asyncio.run(self.check(uid, golf, b, w, os.environ.get("WK_SHOT", "") and f"{os.environ['WK_SHOT']}-{w}.png"))
            wissenskarte.loesen(uid)
        with wissenskarte._Db(uid) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM wb_vor").fetchone()[0], 1)


class Inseln(Base):
    """Stufe 2 „Themen-Inseln“: islands by a fixed label propagation (no model), always the same for the same map; the
    overview names islands and their bridges, an island shows its points; the overview comes by itself only when the
    map has more points than one answer shows."""
    def test_the_fixed_rule_finds_the_same_islands(self):
        adj = {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b", "d"}, "d": {"c", "e"},
               "e": {"d", "f", "g"}, "f": {"e", "g"}, "g": {"e", "f"}}
        order = ["c", "e", "a", "b", "d", "f", "g"]
        got = wissenskarte.inseln(order, adj)
        self.assertEqual(got, wissenskarte.inseln(order, adj))           # the same map, the same islands
        self.assertEqual(got["a"], got["b"])
        self.assertEqual(got["f"], got["g"])
        self.assertNotEqual(got["a"], got["f"])
        self.assertTrue(all(got[x] in order for x in order))
        self.assertEqual(wissenskarte.inseln([], {}), {})
        self.assertEqual(wissenskarte.inseln(["x"], {}), {"x": "x"})

    def test_overview_island_and_arguments(self):
        cl, uid, a = self.fresh("Wkinsel")
        self.work(uid, self.proposal(uid, a, ("Nordstern Versicherung", "VW Golf", "versichert bei", 1, "")))
        v = cl.get("/api/profile/wissenskarte").json()                   # few points: no overview by itself
        self.assertFalse(v["inseln"]["an"])
        self.assertEqual(v["inseln"]["anzahl"], 1)
        o = cl.get("/api/profile/wissenskarte?inseln=1").json()
        self.assertTrue(o["inseln"]["an"])
        self.assertEqual(o["nodes"], [])
        isl = o["inseln"]["liste"][0]
        self.assertEqual((isl["n"], isl["name"] in ("VW Golf", "Nordstern Versicherung")), (2, True))
        i = cl.get(f"/api/profile/wissenskarte?insel={isl['id']}").json()
        self.assertEqual((i["insel"], len(i["nodes"]), len(i["edges"])), (isl["id"], 2, 1))
        self.assertEqual(i["insel_name"], isl["name"])
        nord = self.ids(uid)["Nordstern Versicherung"]
        other = nord if isl["id"] != nord else self.ids(uid)["VW Golf"]
        self.assertEqual(cl.get(f"/api/profile/wissenskarte?insel={other}").json()["insel"], "")   # not an island's id
        with mock.patch.object(wissenskarte, "VIEW_NODES", 1):         # more points than one answer: the overview
            b = documents.add(uid, "Miete.txt", HOUSE.encode(), text=HOUSE)["id"]
            with mock.patch.object(wissensbuch, "ask_model", mock.AsyncMock(return_value=book(
                    ("Lindenstraße 4", "Ort", "Die Wohnung liegt in der Lindenstraße 4 in Bremen."),
                    ("Hansa Wohnbau", "Firma", "Vermieter ist die Hansa Wohnbau.")))), contextlib.redirect_stdout(io.StringIO()):
                run(wissensbuch.work_in(uid, DAY))
            self.work(uid, self.proposal(uid, b, ("Hansa Wohnbau", "Lindenstraße 4", "besitzt", 1, "")))
            v = cl.get("/api/profile/wissenskarte").json()
            self.assertTrue(v["inseln"]["an"])
            self.assertEqual(v["inseln"]["anzahl"], 2)
            self.assertEqual(v["inseln"]["bruecken"], [])
            self.assertFalse(cl.get("/api/profile/wissenskarte?inseln=0").json()["inseln"]["an"])
            self.assertFalse(cl.get(f"/api/profile/wissenskarte?um={nord}").json()["inseln"]["an"])
        for q in ("insel=../x", "inseln=2", "inseln=ja"):
            self.assertEqual(cl.get("/api/profile/wissenskarte?" + q).status_code, 400, q)
