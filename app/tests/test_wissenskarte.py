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


if __name__ == "__main__":
    unittest.main()
