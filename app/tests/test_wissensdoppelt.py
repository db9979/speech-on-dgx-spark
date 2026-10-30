"""Doppelte der Wissenskarte (wissensdoppelt.py, plan wissensgraph, Nachtrag zu Stufe 2): the one rule aehnlich decides by
fixed words and distances, never the model ("gleich" only for people and places that differ by a title, the spelling or
the order of the names, accounts, contracts and deadlines only by the same normal form, a company's legal form only a
suggestion, an initial only when one person fits); a name "gleich" to a point becomes its other name while reading; the
quiet run merges through wissenskarte.zusammen (GEAENDERT "zusammen"), finds suggestions in blocks within its limits
(5000 points never all with all), „Verschieden“ is kept for good, merging needs the code of „Bestätigen“; endpoints
with login, profile, size and rate limit, never for guests, off with Personen, Firmen und Fristen; Live and the journal
with fixed words and numbers only. No test depends on the clock."""
import asyncio
import contextlib
import io
import json
import os
import re
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import iphone  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import stufen  # noqa: E402
import wissensbuch  # noqa: E402
import wissensdoppelt as wd  # noqa: E402
import wissenskarte as wk  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.test_ui_browser import async_playwright, browser_ok, chromium  # noqa: E402
from tests.test_wissenskarte import DAY, book, profile, run, uid_of  # noqa: E402

DOC = ("Herr Dominik Bornhäuser schreibt an die Müller GmbH. Bornhäuser, Dominik, Kundennummer 4711. Unterschrift: "
       "Dr. Dominik Bornhäuser. Kopie an Dominik Bornhäußer und D. Bornhäuser. Die Müller AG antwortet. Herr Hans Kranich "
       "wohnt in der Hauptstr. 5 in Bremen. Konto DE89 3704 0044 0532 0130 00, Kündigung bis 30.09.2026.")
NAMES = ("Herr Dominik Bornhäuser", "Dominik Bornhäußer", "Bornhäuser, Dominik", "D. Bornhäuser", "Dr. Dominik Bornhäuser")


class Rules(unittest.TestCase):
    def test_bornhaeuser_in_every_spelling(self):
        a = "Dominik Bornhäuser"
        self.assertEqual(wd.aehnlich("person", "Herr Dominik Bornhäuser", a), ("gleich", "anrede"))
        self.assertEqual(wd.aehnlich("person", "Dr. Dominik Bornhäuser", a), ("gleich", "anrede"))
        self.assertEqual(wd.aehnlich("person", "Dipl.-Ing. Dominik Bornhäuser", a), ("gleich", "anrede"))
        self.assertEqual(wd.aehnlich("person", "Bornhäuser, Dominik", a), ("gleich", "reihenfolge"))
        self.assertEqual(wd.aehnlich("person", "Dominik Bornhaeuser", a), ("gleich", "schreibweise"))   # ä/ae
        self.assertEqual(wd.aehnlich("person", "Dominik Bornhäußer", a), ("vorschlag", "tippfehler"))  # ß is no ss here
        self.assertEqual(wd.aehnlich("person", "D. Bornhäuser", a), ("vorschlag", "initiale"))
        self.assertEqual(wd.aehnlich("person", "Herr Dominik Bornhäuser", "Frau Dominik Bornhäuser"), (None, ""))
        self.assertEqual(wd.aehnlich("person", "Herr Meier", "Meier")[0], "vorschlag")   # one word: never by itself
        self.assertEqual(wd.aehnlich("person", "Dominik Bornhäuser", "Daniel Bornhäuser"), (None, ""))
        self.assertEqual(wd.schluessel("person", "Herr Meier"), "")
        self.assertEqual(wd.aehnlich("person", "Straße Klaus", "Strasse Klaus"), ("gleich", "schreibweise"))  # ß/ss
        self.assertEqual(wd.aehnlich("person", "Klaus Kranich", "Kranich, Klaus"), ("gleich", "reihenfolge"))

    def test_a_company_only_ever_a_suggestion(self):
        self.assertEqual(wd.aehnlich("firma", "Müller GmbH", "Müller AG"), ("vorschlag", "rechtsform"))
        self.assertEqual(wd.aehnlich("firma", "Firma Meier & Co. KG", "Meier und Co"), ("vorschlag", "rechtsform"))
        self.assertEqual(wd.aehnlich("firma", "Müller GmbH", "Mueller GmbH"), ("vorschlag", "schreibweise"))
        self.assertEqual(wd.aehnlich("firma", "Hansa Wohnbau GmbH", "Hansa Wohnbua GmbH"), ("vorschlag", "tippfehler"))
        self.assertEqual(wd.aehnlich("firma", "GmbH", "AG"), (None, ""))
        self.assertEqual(wd.schluessel("firma", "Müller GmbH"), "")       # never merged by itself
        for a, b in (("Müller GmbH", "Müller AG"), ("Müller GmbH", "Mueller GmbH")):
            self.assertNotEqual(wd.aehnlich("firma", a, b)[0], "gleich")

    def test_accounts_contracts_and_deadlines_never_by_a_typing_error(self):
        iban = "DE89 3704 0044 0532 0130 00"
        self.assertEqual(wd.aehnlich("konto", iban, "DE89370400440532013000"), ("gleich", "schreibweise"))
        self.assertEqual(wd.aehnlich("konto", iban, "DE89 3704 0044 0532 0130 01"), (None, ""))
        self.assertEqual(wd.aehnlich("konto", "12345678", "12345679"), (None, ""))
        self.assertEqual(wd.aehnlich("frist", "30.09.2026", "30. 09. 2026"), ("gleich", "schreibweise"))
        self.assertEqual(wd.aehnlich("frist", "30.09.2026", "30.09.2027"), (None, ""))
        self.assertEqual(wd.aehnlich("vertrag", "Vertrag Nr. 12", "Vertrag Nr 12"), ("gleich", "schreibweise"))
        self.assertEqual(wd.aehnlich("vertrag", "Hausratvertrag", "Hausratvertrog"), (None, ""))

    def test_places_and_the_limits_of_distance(self):
        self.assertEqual(wd.aehnlich("ort", "Hauptstr. 5", "Hauptstraße 5"), ("gleich", "schreibweise"))
        self.assertEqual(wd.aehnlich("ort", "Hauptstraße 5", "Hauptstraße 7"), (None, ""))   # other numbers never
        self.assertEqual(wd.aehnlich("ort", "Bremen", "Bremem"), ("vorschlag", "tippfehler"))
        self.assertEqual(wd.aehnlich("ort", "Bremen", "Brmeen"), ("vorschlag", "tippfehler"))   # swapped once
        self.assertEqual(wd.aehnlich("ort", "Bremen", "Brxmxn"), ("vorschlag", "tippfehler"))   # 2 at 6 letters
        self.assertEqual(wd.aehnlich("ort", "Bremen", "Bxxmxn"), (None, ""))
        self.assertEqual(wd.aehnlich("ort", "Halle", "Hallo"), ("vorschlag", "tippfehler"))    # 1 at 4 to 5
        self.assertEqual(wd.aehnlich("ort", "Halle", "Hxllo"), (None, ""))
        self.assertEqual(wd.aehnlich("ort", "Ulm", "Ulf"), (None, ""))                         # under 4: never
        self.assertEqual(wd.abstand("kitten", "sitting", 2), 3)
        self.assertEqual(wd.abstand("abcdef", "abdcef", 2), 1)
        self.assertEqual(wd.aehnlich("hund", "a", "a"), (None, ""))
        self.assertTrue(set(wd.GRUENDE) >= {"schreibweise", "anrede", "reihenfolge", "initiale", "rechtsform", "tippfehler"})


class Base(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "documents", "doc_semantic", "doc_brief", "knowledge_book", "knowledge_book_day",
                          "knowledge_map", "knowledge_map_day", "knowledge_ents", "knowledge_ents_day", "deny")
        helpers.set_config(documents=True, doc_semantic=False, doc_brief=False, knowledge_book=True, knowledge_book_day=40,
                           knowledge_map=True, knowledge_map_day=200, knowledge_ents=True, knowledge_ents_day=200, deny={})
        wd._live.update(at=0.0, d=None)
        wd._sig.clear()
        self.heard = []
        self.addCleanup(lambda: wk.GEAENDERT.remove(self.hear) if self.hear in wk.GEAENDERT else None)
        wk.GEAENDERT.append(self.hear)

    def hear(self, uid, alt, neu, was):
        self.heard.append((alt, neu, was))

    def fresh(self, name):
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with wd._Db(uid) as con:
            for t in ("wb_pages", "wb_sent", "wb_docs", "wb_block", "wk_edges", "wk_docs", "wk_block", "wk_ent", "wk_ment",
                      "wk_entdocs", "wk_entblock") + wd.TABELLEN:
                con.execute(f"DELETE FROM {t}")
            con.execute("DELETE FROM meta WHERE k='wkdoppelt'")
        a = documents.add(uid, "Brief.txt", DOC.encode(), text=DOC)["id"]
        with mock.patch.object(wissensbuch, "ask_model", mock.AsyncMock(return_value=book(
                ("Brief", "Thema", "Der Brief ging an die Müller GmbH.")))), contextlib.redirect_stdout(io.StringIO()):
            run(wissensbuch.work_in(uid, DAY))
        with wk._Db(uid) as con:
            con.execute("INSERT OR REPLACE INTO wk_docs (doc, state, at, sig) SELECT doc, 'ok', 0, sig FROM wb_docs")
        return c, uid, a

    def read_in(self, uid, *items):
        got = {"dinge": [{"art": a, "name": n, "quelle": 1} for a, n in items], "verbindungen": []}
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wk, "ask_ents", mock.AsyncMock(return_value=got)):
            run(wk.ents_work_in(uid, DAY))
        return out.getvalue()

    def standard(self, uid):
        return self.read_in(uid, *[("person", n) for n in NAMES], ("firma", "Müller GmbH"), ("firma", "Müller AG"),
                            ("person", "Herr Hans Kranich"), ("ort", "Hauptstr. 5"), ("konto", "DE89 3704 0044 0532 0130 00"))

    @staticmethod
    def ids(uid):
        return {x["name"]: x["id"] for x in wk.knoten_liste(uid, None, "", 200)}

    @staticmethod
    def put(uid, art, *names):
        """Points straight into the table (as an older version or the owner's renaming may have left them)."""
        with wd._Db(uid) as con:
            out = []
            for n in names:
                out.append(con.execute("INSERT INTO wk_ent (art, name, norm, alias) VALUES (?, ?, ?, '[]')",
                                       (art, n, wk.ent_norm(n))).lastrowid)
                con.execute("INSERT INTO wk_ment (ent, doc, chunk) SELECT ?, id, 1 FROM docs LIMIT 1", (out[-1],))
        return out

    def quiet(self, uid, now=DAY):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(wd.profiles, "user_ids", return_value=[uid]):
            got = run(wd.due_once(now))     # this profile only: the others of this file are not the question
        return got, out.getvalue()


class Reading(Base):
    def test_a_name_that_is_the_same_becomes_an_other_name(self):
        c, uid, _ = self.fresh("Wkdlesen")
        log = self.standard(uid)
        ids = self.ids(uid)
        self.assertIn("Herr Dominik Bornhäuser", ids)
        for gone in ("Bornhäuser, Dominik", "Dr. Dominik Bornhäuser"):
            self.assertNotIn(gone, ids)                       # no point of their own: other names of the first
        me = next(x for x in wk.knoten_liste(uid, "person") if x["name"] == "Herr Dominik Bornhäuser")
        self.assertEqual(me["alias"], ["Bornhäuser, Dominik", "Dr. Dominik Bornhäuser"])
        for own in ("Dominik Bornhäußer", "D. Bornhäuser", "Müller GmbH", "Müller AG"):
            self.assertIn(own, ids)                           # only suggestions: never merged by themselves
        self.assertEqual([x["id"] for x in wk.finde_knoten(uid, "Bornhäuser, Dominik")], [ids["Herr Dominik Bornhäuser"]])
        self.assertEqual(log.count("wissen: wissenskarte doppelt einlesen | 1 knoten | anrede"), 2)   # one line each
        self.assertNotIn("Bornhäuser", "".join(x for x in log.splitlines() if "doppelt" in x))
        # the same name again from another reading: still one point
        self.read_in(uid, ("person", "Dominik Bornhaeuser"))
        self.assertNotIn("Dominik Bornhaeuser", self.ids(uid))

    def test_a_different_pair_is_never_merged_while_reading(self):
        c, uid, _ = self.fresh("Wkdlesenzwei")
        a, b = self.put(uid, "person", "Hans Kranich", "Hans Kranisch")
        self.assertEqual(wd.verschieden(uid, a, b, DAY), "ok")
        self.read_in(uid, ("person", "Herr Hans Kranich"))
        self.assertEqual(self.ids(uid)["Hans Kranich"], a)       # gleich and not marked: an other name
        with wd._Db(uid) as con:
            con.execute("UPDATE wk_paar SET na=?, nb=? WHERE a=? AND b=?", ("hans kranich", "herr hans kranich", a, b))
            self.assertIsNone(wd.gleich_id(con, "person", "Herr Hans Kranich"))   # called different: never by itself


class Quiet(Base):
    def test_the_run_merges_what_is_the_same_and_suggests_the_rest(self):
        c, uid, _ = self.fresh("Wkdlauf")
        self.standard(uid)
        a, b = self.put(uid, "person", "Hans Kranich", "Kranich, Hans")      # older points, the same person
        x, = self.put(uid, "ort", "Hauptstraße 5")
        got, log = self.quiet(uid)
        self.assertEqual(got, "wissensdoppelt")
        ids = self.ids(uid)
        self.assertNotIn("Kranich, Hans", ids)
        self.assertNotIn("Hans Kranich", ids)                 # both went into the oldest: „Herr Hans Kranich“
        self.assertNotIn("Hauptstraße 5", ids)
        self.assertIn((a, ids["Herr Hans Kranich"], "zusammen"), self.heard)
        self.assertIn((b, ids["Herr Hans Kranich"], "zusammen"), self.heard)
        self.assertIn((x, ids["Hauptstr. 5"], "zusammen"), self.heard)
        self.assertRegex(log, r"wissen: wissenskarte doppelt geprueft \| 3 zusammengefuehrt \| 3 vorschlaege neu \| "
                              r"3 offen \| 0 weg \| \d+ vergleiche \| fertig")
        pairs = {(p["a"]["name"], p["b"]["name"]): p["grund"] for p in wd.paare(uid)["paare"]}
        self.assertEqual(pairs, {("Herr Dominik Bornhäuser", "D. Bornhäuser"): "initiale",
                                 ("Herr Dominik Bornhäuser", "Dominik Bornhäußer"): "tippfehler",
                                 ("Müller GmbH", "Müller AG"): "rechtsform"})
        self.assertEqual(self.quiet(uid), (None, ""))         # nothing changed: no run again
        wd._sig.clear()
        for _ in range(wd.LAEUFE_TAG - 1):
            self.assertEqual(self.quiet(uid)[0], "wissensdoppelt")
            wd._sig.clear()
        self.assertEqual(self.quiet(uid)[0], None)            # at most LAEUFE_TAG a day
        self.assertEqual(self.quiet(uid, DAY + 86400)[0], "wissensdoppelt")

    def test_an_initial_only_when_one_person_fits(self):
        c, uid, _ = self.fresh("Wkdinitiale")
        self.put(uid, "person", "D. Kranich", "Dora Kranich", "Detlef Kranich", "E. Specht", "Erna Specht")
        wd.lauf(uid, DAY)
        pairs = {(p["a"]["name"], p["b"]["name"]) for p in wd.paare(uid)["paare"]}
        self.assertEqual({tuple(sorted(p)) for p in pairs}, {("E. Specht", "Erna Specht")})

    def test_different_stays_different(self):
        c, uid, _ = self.fresh("Wkdverschieden")
        self.standard(uid)
        wd.lauf(uid, DAY)
        p = next(p for p in wd.paare(uid)["paare"] if p["grund"] == "rechtsform")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = c.post("/api/profile/wissenskarte/paare/verschieden", json={"a": p["a"]["id"], "b": p["b"]["id"]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("wissen: wissenskarte doppelt verschieden | 1 paar", out.getvalue())
        self.assertNotIn("rechtsform", [x["grund"] for x in wd.paare(uid)["paare"]])
        wd._sig.clear()
        wd.lauf(uid, DAY)
        self.assertNotIn("rechtsform", [x["grund"] for x in wd.paare(uid)["paare"]])     # never back
        # renamed: the old name stays an other name, the pair still never comes back
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wk.umbenennen(uid, p["b"]["id"], "Müller Holding AG"), "ok")
        wd.lauf(uid, DAY)
        self.assertNotIn("rechtsform", [x["grund"] for x in wd.paare(uid)["paare"]])
        self.assertEqual(c.get("/api/profile/wissenskarte/paare").json()["offen"], 2)

    def test_merging_from_a_suggestion_needs_the_code(self):
        from tests.test_zweiter_schritt import fake_second_step
        import core
        import mfa
        c, uid, _ = self.fresh("Wkdcode")
        self.standard(uid)
        wd.lauf(uid, DAY)
        p = wd.paare(uid)["paare"][0]
        self.assertEqual(stufen.LIST[("POST", "/api/profile/wissenskarte/knoten/{kid}/zusammen")][0], stufen.CONFIRM)
        fake_second_step(uid)
        self.addCleanup(lambda: os.path.exists(mfa._own_path(uid)) and os.remove(mfa._own_path(uid)))
        core._windows.clear()
        r = c.post(f"/api/profile/wissenskarte/knoten/{p['b']['id']}/zusammen", json={"mit": p["a"]["id"]})
        self.assertEqual(r.status_code, 428)
        self.assertEqual(len(wd.paare(uid)["paare"]), 3)        # nothing merged without the code
        os.remove(mfa._own_path(uid))
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.post(f"/api/profile/wissenskarte/knoten/{p['b']['id']}/zusammen", json={"mit": p["a"]["id"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(wd.paare(uid)["paare"]), 2)        # a merged pair leaves the list at once

    def test_five_thousand_points_in_bounded_time(self):
        c, uid, _ = self.fresh("Wkdviele")
        first = ("Anna", "Bernd", "Carla", "Dieter", "Emil", "Frieda", "Gustav", "Hanna", "Ida", "Jonas")
        names = [f"{first[i % 10]} {chr(97 + i // 260 % 26)}{chr(97 + i // 10 % 26)}mann{i}" for i in range(wk.MAX_ENT)]
        with wd._Db(uid) as con:
            con.executemany("INSERT INTO wk_ent (art, name, norm, alias) VALUES ('person', ?, ?, '[]')",
                            [(n, wk.ent_norm(n)) for n in names])
        t0 = time.monotonic()
        got = wd.lauf(uid, DAY)
        took = time.monotonic() - t0
        self.assertLessEqual(got["vergleiche"], wd.VERGLEICHE_MOST)
        self.assertLess(got["vergleiche"], len(names) * (len(names) - 1) // 2 // 20)   # never all with all
        self.assertLess(took, wd.LAUF_S + 20)
        self.assertLessEqual(got["neu"], wd.PAARE_LAUF)
        t0 = time.monotonic()
        short = wd.lauf(uid, DAY, budget=0.0)                # a tight budget stops at the next check and says so
        self.assertLess(time.monotonic() - t0, 20)
        self.assertLessEqual(short["vergleiche"], 500)
        self.assertFalse(short["fertig"])
        with wd._Db(uid) as con:
            kid = con.execute("SELECT id FROM wk_ent WHERE name=?", (names[0],)).fetchone()[0]
        t0 = time.monotonic()
        pick = wd.auswahl(uid, kid, "mann1")
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(len(pick["aehnlich"]), wd.AEHNLICH_MOST)
        self.assertEqual(len(pick["treffer"]), wd.TREFFER_MOST)


class Choice(Base):
    def test_the_most_similar_first_then_the_search(self):
        c, uid, _ = self.fresh("Wkdauswahl")
        self.standard(uid)
        ids = self.ids(uid)
        self.put(uid, "person", *[f"Gerda Muster{i}" for i in range(30)])
        r = c.get(f"/api/profile/wissenskarte/knoten/{ids['Herr Dominik Bornhäuser']}/aehnlich")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["aehnlich"]), wd.AEHNLICH_MOST)
        self.assertEqual({x["name"] for x in d["aehnlich"][:2]}, {"Dominik Bornhäußer", "D. Bornhäuser"})
        self.assertNotIn("Müller GmbH", [x["name"] for x in d["aehnlich"]])       # only the same kind
        self.assertNotIn(ids["Herr Dominik Bornhäuser"], [x["id"] for x in d["aehnlich"]])
        self.assertEqual(d["treffer"], [])
        hits = c.get(f"/api/profile/wissenskarte/knoten/{ids['Herr Dominik Bornhäuser']}/aehnlich?q=muster").json()["treffer"]
        self.assertEqual(len(hits), wd.TREFFER_MOST)
        self.assertTrue(all(x["name"].startswith("Gerda Muster") for x in hits))
        self.assertEqual(c.get(f"/api/profile/wissenskarte/knoten/{ids['Herr Dominik Bornhäuser']}/aehnlich?q=" + "x" * 81).status_code, 400)
        self.assertEqual(c.get("/api/profile/wissenskarte/knoten/999999/aehnlich").status_code, 404)
        wd.lauf(uid, DAY)
        mine = c.get(f"/api/profile/wissenskarte/knoten/{ids['D. Bornhäuser']}/aehnlich").json()["vielleicht"]
        self.assertEqual([(p["a"]["name"], p["grund"]) for p in mine], [("Herr Dominik Bornhäuser", "initiale")])


class Access(Base):
    def test_off_never_for_guests_and_checked_arguments(self):
        c, uid, _ = self.fresh("Wkdzugang")
        self.standard(uid)
        kid = self.ids(uid)["Müller GmbH"]
        self.assertEqual(c.get("/api/profile/wissenskarte/paare").status_code, 200)
        for bad in ({"a": 1}, {"a": "1", "b": 2}, {"a": True, "b": 2}, {"a": 0, "b": 2}):
            self.assertEqual(c.post("/api/profile/wissenskarte/paare/verschieden", json=bad).status_code, 400, bad)
        self.assertEqual(c.post("/api/profile/wissenskarte/paare/verschieden", json={"a": kid, "b": kid}).status_code, 400)
        self.assertEqual(c.post("/api/profile/wissenskarte/paare/verschieden", json={"a": kid, "b": 999999}).status_code, 404)
        other = self.ids(uid)["Herr Hans Kranich"]
        self.assertEqual(c.post("/api/profile/wissenskarte/paare/verschieden", json={"a": kid, "b": other}).status_code, 400)
        self.assertEqual(c.post("/api/profile/wissenskarte/paare/verschieden", content=b"{" + b" " * 300 + b"}",
                                headers={"content-type": "application/json"}).status_code, 413)
        for off in ({"knowledge_ents": False}, {"knowledge_map": False}, {"deny": {"wissensknoten": [uid]}}):
            helpers.set_config(**off)
            self.assertEqual(c.get("/api/profile/wissenskarte/paare").status_code, 403, off)
            self.assertEqual(c.get(f"/api/profile/wissenskarte/knoten/{kid}/aehnlich").status_code, 403, off)
            self.assertEqual(c.post("/api/profile/wissenskarte/paare/verschieden", json={"a": kid, "b": kid + 1}).status_code, 403, off)
            helpers.set_config(knowledge_ents=True, knowledge_map=True, deny={})
        helpers.set_config(knowledge_ents=False)
        self.assertEqual(self.quiet(uid), (None, ""))
        helpers.set_config(knowledge_ents=True)
        guest = TestClient(panel.app)
        for r in (guest.get("/api/profile/wissenskarte/paare"), guest.get(f"/api/profile/wissenskarte/knoten/{kid}/aehnlich"),
                  guest.post("/api/profile/wissenskarte/paare/verschieden", json={"a": 1, "b": 2})):
            self.assertIn(r.status_code, (401, 403))
        for m, p in (("GET", "/api/profile/wissenskarte/paare"), ("GET", f"/api/profile/wissenskarte/knoten/{kid}/aehnlich"),
                     ("POST", "/api/profile/wissenskarte/paare/verschieden")):
            self.assertTrue(any(m in ms and re.fullmatch(rx, p) for ms, rx in iphone.THINGS["wissensknoten"]), p)

    def test_own_data_goes_with_the_points(self):
        c, uid, _ = self.fresh("Wkdloeschen")
        self.standard(uid)
        wd.lauf(uid, DAY)
        p = wd.paare(uid)["paare"][0]
        wd.verschieden(uid, p["a"]["id"], p["b"]["id"], DAY)
        with contextlib.redirect_stdout(io.StringIO()):
            wk._ent_clear(uid)
        with wd._Db(uid) as con:
            for t in wd.TABELLEN:
                self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0, t)

    def test_live_shows_numbers_only(self):
        c, uid, _ = self.fresh("Wkdlive")
        self.standard(uid)
        self.quiet(uid)
        wd._live.update(at=0.0, d=None)
        d = wd.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["offen"], 3)
        self.assertGreaterEqual(d["auto"] + d["einlesen"], 2)
        wk._live.update(at=0.0, d=None)
        snap = json.dumps(live.snapshot(), ensure_ascii=False)
        self.assertIn("Doppelte: ", snap)
        for word in ("Bornhäuser", "Müller", "Kranich"):
            self.assertNotIn(word, snap)
        helpers.set_config(knowledge_ents=False)
        self.assertEqual(wd.for_live(), {"on": False})


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Browser(Base):
    """Wissensbuch → Karte: „Vielleicht doppelt“ above the map, at a point its suggestion, „Zusammenführen mit …“ as a
    search field with the most similar first; fits 390 and 1280 px, nothing scrolls sideways, no script error."""
    @classmethod
    def setUpClass(cls):
        cls.port = helpers._port()
        helpers.serve_panel(cls, cls.port)

    async def check(self, uid, kid, w, last):
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
                                                        data={"name": "Wkdseite", "pin": "2468"})).status, 200)
                await pg.goto(base + "/")
                await pg.wait_for_function("typeof WK_ON!=='undefined'&&WK_ON&&typeof wkaFocus==='function'", timeout=30000)
                await pg.evaluate("document.getElementById('wizmodal')&&(document.getElementById('wizmodal').style.display='none')")
                await pg.evaluate(f"goSec('wbuch');wkaFocus('k{kid}')")
                await pg.wait_for_function("[...document.querySelectorAll('#wkview .wkown li')].some(l=>l.textContent.includes('Vielleicht dieselbe Person'))", timeout=30000)
                await pg.wait_for_timeout(1500)   # the list of pairs comes after the map: it must not rebuild the chosen point
                det = await pg.inner_text("#wkview .wkdet")
                self.assertIn("Vielleicht dieselbe Person: Herr Dominik Bornhäuser", det)
                self.assertIn("Am ähnlichsten", det)
                self.assertEqual(await pg.locator("#wkview .wkown select").count(), 0)     # no long list any more
                await pg.fill("#wkview .wkown input[type=search]", "muster")
                await pg.wait_for_function("document.querySelector('#wkview .wkdet').textContent.includes('Treffer')", timeout=30000)
                self.assertEqual(await pg.locator("#wkview .wkown li:has-text('Gerda Muster')").count(), wd.TREFFER_MOST)
                await pg.locator("#wkview .wkown li:has-text('Gerda Muster') button").first.click()
                self.assertIn("geht in „Gerda Muster", await pg.inner_text("#wkview .wkdet"))
                self.assertFalse(await pg.is_disabled("#wkview .wkown .row button:has-text('Zusammenführen')"))
                chip = pg.locator("#wkview .wkcrumb button:has-text('Vielleicht doppelt')")
                self.assertEqual((await chip.inner_text()).strip(), "Vielleicht doppelt 3")
                await chip.click()
                await pg.wait_for_function("document.querySelector('#wkview .wkdet h3').textContent==='Vielleicht doppelt'")
                self.assertIn("Müller GmbH und Müller AG", await pg.inner_text("#wkview .wkdet"))
                if last:
                    await pg.locator("#wkview .wkdet li:has-text('Müller AG') button:has-text('Verschieden')").click()
                    await pg.wait_for_function("[...document.querySelectorAll('#wkview .wkcrumb button')].some(b=>b.textContent.trim()==='Vielleicht doppelt 2')", timeout=30000)
                self.assertLessEqual(await pg.evaluate("document.documentElement.scrollWidth"), w)
                self.assertEqual(errors, [])
            finally:
                await br.close()

    def test_maybe_double_and_the_search_to_merge(self):
        c, uid, _ = self.fresh("Wkdseite")
        self.standard(uid)
        self.put(uid, "person", *[f"Gerda Muster{i}" for i in range(25)])
        wd.lauf(uid, DAY)
        kid = self.ids(uid)["D. Bornhäuser"]
        for w, last in ((390, False), (1280, True)):
            asyncio.run(self.check(uid, kid, w, last))
        self.assertEqual(len(wd.paare(uid)["paare"]), 2)


if __name__ == "__main__":
    unittest.main()
