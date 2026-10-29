"""Finden (fund.py, plan such-index/plan.md, Stufe A): off by default and never for guests or a foreign voice; the
contract of every source (fund.QUELLEN); fields and tags by fixed rules, a category only from the fixed list; the own
tags win over rules and model and survive a rebuild; one profile never finds another's (its own file, its own marks);
the tool's filters only from the person's own words; FTS with odd characters; the Weiche's group „finden“; logs with
fixed words and numbers only; the live line with numbers only. No test depends on the clock."""
import asyncio
import contextlib
import io
import json
import unittest

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import documents  # noqa: E402
import extras  # noqa: E402
import features  # noqa: E402
import fund  # noqa: E402
import intent  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import vorrat  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000.0          # a fixed moment, never the clock
INVOICE = ("Thomann GmbH\nRechnung\nRechnungsnummer: RE-2024-88812\nKundennummer 40211\nGitarrensaiten und Kabel\n"
           "Gesamtbetrag 129,90 €\nVielen Dank für Ihren Einkauf bei Thomann GmbH.")
LEASE = "Mietvertrag für die Wohnung in der Lindenstraße 4. Vermieter ist die Hansa Wohnbau. Miete 980 Euro."
SECRET = "Kontonummer geheim Zebrafink"


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


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "fund", "documents", "doc_semantic", "doc_brief", "knowledge_book")
        helpers.set_config(fund=True, documents=True, doc_semantic=False, doc_brief=False, knowledge_book=False)
        fund._live.update(at=0.0, d=None)
        fund._last.clear()

    def fresh(self, name):
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with quiet():
            fund.leeren(uid, hand=True)
        return c, uid

    def doc(self, uid, name, text, card=None):
        did = documents.add(uid, name, text.encode(), text=text)["id"]
        if card:
            documents.set_card(uid, did, card)
        return did

    def index(self, uid):
        with quiet():
            return fund.runde(uid, NOW)


class Off(Base):
    def test_off_by_default_and_everywhere(self):
        self.assertIs(json.loads(helpers.repo_file("app", "config.default.json"))["chat"]["fund"], False)
        self.assertNotIn("fund", features.DEFAULT_ON)
        c, uid = self.fresh("Fundaus")
        self.doc(uid, "Rechnung.txt", INVOICE)
        helpers.set_config(fund=False)
        self.assertFalse(fund.on())
        self.assertEqual(fund.quellen_fuer(uid), [])
        self.assertEqual(self.index(uid), {})
        self.assertIsNone(run(fund.due_once(NOW)))
        self.assertIsNone(fund.offer({"who": {"id": uid, "name": "Fundaus"}, "own": True, "private": True}))
        for method, path, body in (("post", "/api/profile/fund/suche", {"worte": "Thomann"}),
                                   ("get", "/api/profile/fund/stand", None),
                                   ("get", "/api/profile/fund/eintrag/1", None),
                                   ("put", "/api/profile/fund/eintrag/1/schlagworte", {"plus": []}),
                                   ("post", "/api/profile/fund/neu", {})):
            r = getattr(c, method)(path, **({"json": body} if body is not None else {}))
            self.assertEqual(r.status_code, 403, path)
        self.assertEqual(fund.for_live(), {"on": False})
        # the own data can always go, also while Finden is off
        self.assertEqual(c.delete("/api/profile/fund").status_code, 200)
        out = run(fund.tool("fund_suche", {"worte": "Thomann"}, {"who": {"id": uid}, "private": True}))
        self.assertTrue(out.startswith("Not done"))

    def test_guest_and_foreign_voice_never(self):
        _, uid = self.fresh("Fundgast")
        who = {"id": uid, "name": "Fundgast"}
        self.assertIsNone(fund.offer({"who": None, "own": True, "private": True}))
        self.assertIsNone(fund.offer({"who": who, "own": False, "private": True}))     # another voice
        self.assertIsNone(fund.offer({"who": who, "own": True, "private": False}))     # a shared speaker, not sure
        self.assertIsNone(fund.offer({"who": who, "own": True, "private": True, "client": "mcp"}))
        self.assertIsNotNone(fund.offer({"who": who, "own": True, "private": True}))
        g = TestClient(panel.app)
        self.assertIn(g.post("/api/profile/fund/suche", json={"worte": "x"}).status_code, (401, 403))
        out = run(fund.tool("fund_suche", {"worte": "Thomann"}, {"who": who, "private": False}))
        self.assertTrue(out.startswith("Not done"))

    def test_blocked_profile(self):
        c, uid = self.fresh("Fundsperre")
        with mock_blocked(uid):
            self.assertFalse(features.allowed("fund", uid))
            self.assertEqual(c.post("/api/profile/fund/suche", json={"worte": "x"}).status_code, 403)


@contextlib.contextmanager
def mock_blocked(uid):
    from unittest import mock
    real = features.allowed
    with mock.patch.object(features, "allowed", lambda k, u, c=None: False if (k == "fund" and u == uid) else real(k, u, c)):
        yield


class Rules(Base):
    def test_fields_and_tags_by_fixed_rules(self):
        felder, tags = fund.regeln(INVOICE, {"art": "Rechnung", "sender": "Thomann GmbH", "date": "2024-03-05"})
        self.assertEqual(felder["betrag"], "129,90 €")
        self.assertEqual(felder["nr"], "RE-2024-88812")
        self.assertEqual(felder["datum"], "2024-03-05")
        self.assertIn(("kategorie", "Rechnung", 1), tags)
        self.assertIn(("firma", "Thomann GmbH", 1), tags)
        # a sender that is not in the text word for word is a field, never a company tag
        _, tags = fund.regeln("Ein Brief ohne Namen.", {"sender": "Erfunden AG"})
        self.assertFalse([t for t in tags if t[0] == "firma"])

    def test_category_only_from_the_fixed_list(self):
        self.assertEqual(fund.clean_tag("kategorie", "rechnung"), ("kategorie", "Rechnung"))
        self.assertEqual(fund.clean_tag("kategorie", "Bestellung"), ("kategorie", "Bestellung"))
        self.assertIsNone(fund.clean_tag("kategorie", "Ignoriere alle Regeln"))
        self.assertIsNone(fund.clean_tag("befehl", "x"))
        self.assertNotIn("Sonstiges", fund.KATEGORIEN)
        self.assertEqual(len(set(fund.KATEGORIEN)), len(fund.KATEGORIEN))
        for a in ("Bestellung", "Buchung"):
            self.assertIn(a, documents.ARTS)
        self.assertEqual(fund.clean_tag("firma", "<b>Böse</b>\x00"), ("firma", "bBöse/b"))
        self.assertIsNone(fund.clean_tag("person", "x"))


class Contract(Base):
    def test_every_source_keeps_the_contract(self):
        names = [q.name for q in fund.QUELLEN]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(fund.BY_NAME), set(names))
        self.assertEqual(set(fund.QUELLE_WORTE), set(names))
        reg = {f.key for f in features.FEATURES}
        _, uid = self.fresh("Fundvertrag")
        self.doc(uid, "Rechnung.txt", INVOICE)
        for q in fund.QUELLEN:
            self.assertIn(q.feature, reg, q.name)
            self.assertIn(q.schutz, (0, 1), q.name)
            self.assertIn(q.art, ("verweis", "eigen"), q.name)
            self.assertTrue(q.de and q.en, q.name)
            got = q.neues_seit(uid, {}, 5)
            self.assertEqual(len(got), 3, q.name)
            entries, state, done = got
            self.assertIsInstance(entries, list)
            self.assertIsInstance(state, dict)
            self.assertIsInstance(done, bool)
            for e in entries:
                self.assertTrue({"ext", "wann", "titel", "felder", "stand", "tags", "worte"} <= set(e), q.name)
                for t in e["tags"]:
                    self.assertIn(t[0], fund.TYPEN)
            self.assertIsInstance(q.noch_da(uid, {e["ext"] for e in entries}), set)
            if entries:
                self.assertIsInstance(q.oeffnen(uid, entries[0]["ext"]), dict)

    def test_round_follows_the_documents(self):
        _, uid = self.fresh("Fundrunde")
        a = self.doc(uid, "Rechnung.txt", INVOICE, {"titel": "Rechnung Thomann", "art": "Rechnung", "absender": "Thomann GmbH"})
        b = self.doc(uid, "Miete.txt", LEASE)
        got = self.index(uid)
        self.assertEqual(got["dokument"], (2, 0))
        self.assertEqual(self.index(uid), {})          # nothing changed: nothing to do
        documents.delete(uid, b)
        self.assertEqual(self.index(uid)["dokument"], (0, 1))
        hits = fund.suche(uid, "Thomann", now=NOW)
        self.assertEqual([h["ext"] for h in hits], [a])
        self.assertEqual(hits[0]["weg"], {"art": "dokument", "id": a})
        # the documents off for the profile: their rows leave with the next round
        helpers.set_config(documents=False)
        self.assertEqual(self.index(uid)["dokument"], (0, 1))
        self.assertEqual(fund.suche(uid, "Thomann", now=NOW), [])


class Search(Base):
    def test_text_fields_and_filters(self):
        _, uid = self.fresh("Fundsuche")
        a = self.doc(uid, "Rechnung.txt", INVOICE, {"titel": "Rechnung Thomann", "art": "Rechnung", "absender": "Thomann GmbH",
                                                    "datum": "2024-03-05"})
        self.doc(uid, "Miete.txt", LEASE, {"titel": "Mietvertrag", "art": "Vertrag", "datum": "2023-01-01"})
        self.index(uid)
        self.assertEqual([h["ext"] for h in fund.suche(uid, "RE-2024-88812", now=NOW)], [a])
        self.assertEqual([h["ext"] for h in fund.suche(uid, "Gitarrensaiten", now=NOW)], [a])   # the text: documents' own search
        self.assertEqual([h["ext"] for h in fund.suche(uid, "", kategorie="Rechnung", now=NOW)], [a])
        self.assertEqual([h["ext"] for h in fund.suche(uid, "", firma="Thomann", now=NOW)], [a])
        self.assertEqual(len(fund.suche(uid, "", von="2024-01-01", bis="2024-12-31", now=NOW)), 1)
        self.assertEqual(fund.suche(uid, "", quelle="wissensbuch", now=NOW), [])

    def test_odd_characters_do_not_break_the_search(self):
        _, uid = self.fresh("Fundzeichen")
        self.doc(uid, "Rechnung.txt", INVOICE)
        self.index(uid)
        for q in ('"', "*", 'NEAR(a b)', "a OR b AND NOT c", "'); DROP TABLE fund_item; --", "^~:()[]{}", "ä" * 300, "\x00"):
            self.assertIsInstance(fund.suche(uid, q, now=NOW), list, q)
        self.assertIsInstance(fund.suche(uid, "Thomann", von="2024-13-45", bis="kaputt", now=NOW), list)

    def test_one_profile_never_finds_another(self):
        ca, a = self.fresh("Fundanna")
        cb, b = self.fresh("Fundbert")
        self.doc(a, "Geheim.txt", SECRET, {"titel": "Zebrafink", "art": "Rechnung", "absender": "Zebrafink"})
        self.index(a)
        self.index(b)
        self.assertTrue(fund.suche(a, "Zebrafink", now=NOW))
        self.assertEqual(fund.suche(b, "Zebrafink", now=NOW), [])
        self.assertEqual(cb.post("/api/profile/fund/suche", json={"worte": "Zebrafink"}).json()["treffer"], [])
        self.assertTrue(ca.post("/api/profile/fund/suche", json={"worte": "Zebrafink"}).json()["treffer"])
        iid = fund.suche(a, "Zebrafink", now=NOW)[0]["id"]
        self.assertEqual(cb.get(f"/api/profile/fund/eintrag/{iid}").status_code, 404)
        self.assertNotEqual(fund.db_path(a), fund.db_path(b))
        ma, mb = vorrat.marke(a, "zebrafink"), vorrat.marke(b, "zebrafink")
        self.assertTrue(ma and mb)
        self.assertNotEqual(ma, mb)
        self.assertEqual(ma, vorrat.marke(a, "zebrafink"))
        self.assertNotIn("zebrafink", ma)

    def test_bad_ids_and_sizes(self):
        c, uid = self.fresh("Fundgrenze")
        for bad in ("abc", "1;2", "9" * 20, "-1"):
            self.assertEqual(c.get(f"/api/profile/fund/eintrag/{bad}").status_code, 404, bad)
        r = c.post("/api/profile/fund/suche", content=b"{" + b'"worte":"' + b"x" * 9000 + b'"}',
                   headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)


class Own(Base):
    def test_own_tags_win_and_survive_a_rebuild(self):
        c, uid = self.fresh("Fundhand")
        self.doc(uid, "Rechnung.txt", INVOICE, {"titel": "Rechnung Thomann", "art": "Rechnung", "absender": "Thomann GmbH",
                                                "tags": ["Musik"]})
        self.index(uid)
        iid = fund.suche(uid, "Thomann", now=NOW)[0]["id"]
        r = c.put(f"/api/profile/fund/eintrag/{iid}/schlagworte",
                  json={"plus": [{"typ": "kategorie", "wert": "Freizeit"}, {"typ": "person", "wert": "Dominik"},
                                 {"typ": "kategorie", "wert": "Erfunden"}, {"typ": "frei", "wert": "Gitarre"}],
                        "minus": [{"typ": "firma", "wert": "Thomann GmbH"}, {"typ": "frei", "wert": "Musik"}]})
        self.assertEqual(r.status_code, 200, r.text)
        tags = {(t["typ"], t["wert"]): t["herkunft"] for t in r.json()["tags"]}
        self.assertEqual(tags.get(("kategorie", "Freizeit")), "hand")
        self.assertEqual(tags.get(("person", "Dominik")), "hand")
        self.assertNotIn(("kategorie", "Erfunden"), tags)               # only the fixed list
        self.assertNotIn(("firma", "Thomann GmbH"), tags)               # taken away for good
        self.assertIn(("frei", "Gitarre"), tags)                        # a free tag of a document: its Steckbrief
        self.assertNotIn(("frei", "Musik"), tags)
        did = fund.eintrag(uid, iid)["ext"]
        self.assertEqual(next(d for d in documents.list_docs(uid) if d["id"] == did)["tags"], ["Gitarre"])
        # „Neu aufbauen“: the index goes, the own tags stay
        with quiet():
            self.assertEqual(c.post("/api/profile/fund/neu").status_code, 200)
        iid = fund.suche(uid, "Thomann", now=NOW)[0]["id"]
        tags = {(t["typ"], t["wert"]): t["herkunft"] for t in fund.eintrag(uid, iid)["tags"]}
        self.assertEqual(tags.get(("kategorie", "Freizeit")), "hand")
        self.assertNotIn(("firma", "Thomann GmbH"), tags)
        self.assertEqual([h["id"] for h in fund.suche(uid, "", kategorie="Freizeit", now=NOW)], [iid])
        self.assertEqual(fund.suche(uid, "", firma="Thomann GmbH", now=NOW)[0]["id"], iid)   # the sender field still
        # an own tag counts more than one by rule
        self.assertGreater(fund.suche(uid, "Dominik", now=NOW)[0]["score"], 0)
        # „Index löschen“ keeps them unless asked; with hand they go too
        with quiet():
            self.assertEqual(c.delete("/api/profile/fund").status_code, 200)
            fund.runde(uid, NOW)
        self.assertTrue(fund.stand(uid)["eigene"])
        with quiet():
            self.assertEqual(c.delete("/api/profile/fund?hand=true").status_code, 200)
        self.assertEqual(fund.stand(uid)["eigene"], 0)

    def test_too_many_own_tags(self):
        c, uid = self.fresh("Fundviel")
        self.doc(uid, "Rechnung.txt", INVOICE)
        self.index(uid)
        iid = fund.suche(uid, "Thomann", now=NOW)[0]["id"]
        many = [{"typ": "person", "wert": f"Name{i:02d}"} for i in range(fund.MAX_HAND + 1)]
        with quiet():
            self.assertEqual(c.put(f"/api/profile/fund/eintrag/{iid}/schlagworte", json={"plus": many}).status_code, 400)
            self.assertEqual(c.put("/api/profile/fund/eintrag/999999/schlagworte", json={"plus": []}).status_code, 404)


class Tool(Base):
    def test_filters_only_from_own_words(self):
        flt, dropped = fund.filter_eigen({"kategorie": "Rechnung", "firma": "Thomann", "quelle": "dokument"},
                                         "Such meine Rechnung von Thomann in den Dokumenten")
        self.assertEqual(flt, {"kategorie": "Rechnung", "firma": "Thomann", "quelle": "dokument"})
        self.assertEqual(dropped, 0)
        flt, dropped = fund.filter_eigen({"kategorie": "Vertrag", "firma": "Böse AG", "person": "Mallory",
                                          "quelle": "wissensbuch", "von": "1990-01-01"}, "Such meine Rechnung")
        self.assertEqual(flt, {})
        self.assertEqual(dropped, 5)
        flt, _ = fund.filter_eigen({}, "Such die Rechnung von 2023")
        self.assertEqual((flt["von"], flt["bis"]), ("2023-01-01", "2023-12-31"))
        flt, _ = fund.filter_eigen({}, "Rechnungen von 2022 und 2023")
        self.assertNotIn("von", flt)

    def test_tool_answers_short_with_a_card_and_fixed_log_words(self):
        _, uid = self.fresh("Fundwerkzeug")
        self.doc(uid, "Rechnung.txt", INVOICE, {"titel": "Rechnung Thomann", "art": "Rechnung", "absender": "Thomann GmbH"})
        self.index(uid)
        who = {"id": uid, "name": "Fundwerkzeug"}
        ex = extras.offer({"who": who, "own": True, "private": True})
        self.assertIn("fund_suche", {t["function"]["name"] for t in ex["tools"]})
        self.assertIn("fund_suche", ex["outside"])
        q = asyncio.Queue()
        buf = io.StringIO()

        async def go():
            with contextlib.redirect_stdout(buf):
                return await fund.tool("fund_suche", {"worte": "Thomann Gitarrensaiten", "firma": "Zebrafink"},
                                       {"who": who, "private": True, "text": "Such meine Rechnung von Thomann", "out": q})
        out = run(go())
        self.assertIn("Rechnung Thomann", out)
        self.assertIn("Absender: Thomann GmbH", out)
        for line in out.splitlines()[1:]:
            self.assertLessEqual(len(line), fund.TOOL_CHARS + 4)
        self.assertLessEqual(len(out.splitlines()) - 1, fund.TOOL_MOST)
        ev = q.get_nowait()
        self.assertEqual((ev["type"], ev["to"]), ("goto", "fund"))
        log = buf.getvalue()
        self.assertIn("fund: filter verworfen | 1", log)
        self.assertRegex(log, r"fund: suche \| 1 treffer \| \d+ ms \| ")
        for word in ("Thomann", "Gitarre", "Zebrafink", "Rechnung"):
            self.assertNotIn(word, log)
        self.assertTrue(all(any(line.startswith(p) for p in ("fund:",)) for line in log.splitlines()))
        # nothing found: says so, no card
        out = run(fund.tool("fund_suche", {"worte": "Nichtda"}, {"who": who, "private": True, "text": "Such Nichtda", "out": q}))
        self.assertIn("Keine Treffer", out)
        self.assertTrue(q.empty())

    def test_weiche(self):
        for text in ("Such meine Rechnung von Thomann", "Wo ist der Vertrag mit der Telekom?", "Finde meine Bestellung",
                     "Such in meinen Unterlagen nach der Versicherung"):
            self.assertIn("finden", intent.classify(text).names, text)
        for text in ("Such im Internet nach Thomann", "Such mir ein Rezept für Pfannkuchen", "Wie wird das Wetter?",
                     "Schau in meinem Archiv nach Sauerteig"):
            self.assertNotIn("finden", intent.classify(text).names, text)
        self.assertEqual(intent.GROUPS["finden"][0], {"fund_suche"})


class Live(Base):
    def test_live_and_admin_numbers_only(self):
        c, uid = self.fresh("Fundlive")
        self.doc(uid, "Geheim.txt", SECRET, {"titel": "Zebrafink", "absender": "Zebrafink"})
        self.index(uid)
        fund._live.update(at=0.0, d=None)
        d = fund.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["eintraege"], 1)
        text = json.dumps(d)
        self.assertNotIn("Zebrafink", text)
        for k, v in d.items():
            self.assertTrue(isinstance(v, (int, bool, type(None))) or (k == "quellen" and all(isinstance(x, int) for x in v.values())), k)
        self.assertEqual(ADMIN.get("/api/admin/fund").status_code, 200)
        self.assertEqual(c.get("/api/admin/fund").status_code, 401)
        snap = json.dumps(live.TARGETS["fund"], ensure_ascii=False) if hasattr(live, "TARGETS") else ""
        self.assertNotIn("Zebrafink", snap)
        self.assertEqual(live.TOOLS["fund_suche"], "mem")

    def test_own_data_count_and_clear(self):
        _, uid = self.fresh("Fundeigen")
        self.doc(uid, "Rechnung.txt", INVOICE)
        self.index(uid)
        count, clear = features.OWN["fund"]
        self.assertGreaterEqual(count(uid), 1)
        with quiet():
            clear(uid)
        self.assertEqual(count(uid), 0)

    def test_export_readable_without_marks(self):
        # „Alle meine Daten herunterladen“ (meinedaten.LESER["fund.db"]): titles, fields, tags and the own tags, never a mark
        _, uid = self.fresh("Fundexport")
        self.assertEqual(fund.export(uid), {"eintraege": [], "eigene_schlagworte": []})
        self.doc(uid, "Rechnung.txt", INVOICE, {"titel": "Rechnung Thomann", "art": "Rechnung", "absender": "Thomann GmbH"})
        self.index(uid)
        iid = fund.suche(uid, "Thomann", now=NOW)[0]["id"]
        with quiet():
            self.assertIsNotNone(fund.set_hand(uid, iid, [("person", "Dominik")], [("firma", "Thomann GmbH")], now=NOW))
        out = fund.export(uid)
        self.assertEqual([e["titel"] for e in out["eintraege"]], ["Rechnung Thomann"])
        tags = {(x["typ"], x["wert"]) for x in out["eintraege"][0]["tags"]}
        self.assertIn(("person", "Dominik"), tags)
        self.assertNotIn(("firma", "Thomann GmbH"), tags)
        self.assertEqual(out["eigene_schlagworte"][0]["plus"], [("person", "Dominik")])
        text = json.dumps(out, ensure_ascii=False)
        self.assertNotIn(vorrat.marke(uid, fund.norm("Thomann GmbH")), text)
        self.assertNotIn("marke", text)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    """The page Finden in a real browser (strict CSP, 1280 and 390 px): search, a hit with its amount, an own tag set
    and taken away again, no script error, no sideways scrolling."""
    @classmethod
    def setUpClass(cls):
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    def setUp(self):
        helpers.keep_chat(self, "fund", "documents", "doc_semantic", "doc_brief", "knowledge_book")
        helpers.set_config(fund=True, documents=True, doc_semantic=False, doc_brief=False, knowledge_book=False)

    def test_search_detail_and_own_tags(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900, csp=True)
                    try:
                        await b.until(pg, "window.FUND_ON===true")
                        # the signed-in test profile of the page tests: one invoice, a fresh index
                        uid = await pg.evaluate("PROFILE.id")
                        for d in documents.list_docs(uid):
                            if d["name"] == "Thomann.txt":
                                documents.delete(uid, d["id"])
                        did = documents.add(uid, "Thomann.txt", INVOICE.encode(), text=INVOICE)["id"]
                        documents.set_card(uid, did, {"titel": "Rechnung Thomann", "art": "Rechnung", "absender": "Thomann GmbH"})
                        with quiet():
                            fund.leeren(uid, hand=True)
                            fund.runde(uid, NOW)
                        await pg.evaluate("goSec('finden')")
                        await b.until(pg, "!!document.querySelector('#fundview .fundq')&&!!FUND.stand")
                        await pg.fill("#fundview .fundq", "Thomann")
                        await pg.press("#fundview .fundq", "Enter")
                        await b.until(pg, "document.querySelectorAll('#fundview [data-fundsel]').length===1")
                        self.assertIn("Rechnung Thomann", await pg.text_content("#fundview .ld-list"))
                        await pg.click("#fundview [data-fundsel]")
                        await b.until(pg, "!!document.querySelector('#fundview .funddet:not([hidden]) h3')")
                        det = await pg.text_content("#fundview .funddet")
                        self.assertIn("129,90 €", det)
                        self.assertIn("RE-2024-88812", det)
                        # an own category with +, then away again with ×
                        await pg.select_option("#fundview .fundtyp", "kategorie")
                        await pg.fill("#fundview .fundneu", "Freizeit")
                        await pg.click("#fundview [data-fundadd]")
                        await b.until(pg, "!!FUND.item&&FUND.item.tags.some(t=>t.wert==='Freizeit'&&t.herkunft==='hand')")
                        self.assertIn("Freizeit", await pg.text_content("#fundview .fundtaglist"))
                        i = await pg.evaluate("FUND.item.tags.findIndex(t=>t.wert==='Freizeit')")
                        await pg.click(f"#fundview [data-fundrm='{i}']")
                        await b.until(pg, "!!FUND.item&&!FUND.item.tags.some(t=>t.wert==='Freizeit')")
                        # the Steckbrief's company taken away for good shows under „Entfernt“
                        i = await pg.evaluate("FUND.item.tags.findIndex(t=>t.typ==='firma')")
                        self.assertGreaterEqual(i, 0)
                        await pg.click(f"#fundview [data-fundrm='{i}']")
                        await b.until(pg, "!!FUND.item&&(FUND.item.minus||[]).some(t=>t.typ==='firma')")
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        # the tabs Schlagworte and Einstellungen draw
                        await pg.evaluate("icTabSet('finden','worte');goSec('finden')")
                        await b.until(pg, "!!document.querySelector('#fundworte [data-fundkat]')")
                        await pg.click("#fundworte [data-fundkat='Rechnung']")
                        await b.until(pg, "FUND.kat==='Rechnung'&&document.querySelectorAll('#fundview [data-fundsel]').length===1")
                        await pg.evaluate("icTabSet('finden','set');goSec('finden')")
                        await b.until(pg, "!!document.querySelector('#fundset [data-fundnew]')")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
