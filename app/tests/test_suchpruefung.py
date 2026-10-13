"""Suchprüfung (suchpruefung.py, plan plaene/suche-schaerfen.md, Stufe 1): off by default and never for guests,
the panel's fixed rules for the model's test questions, runs that measure with the assistant's own search,
numbers only in the journal and for the admin, limits on clicks and per day, and the fixed test bank
(tests/data/suchbank.json): the word search must keep finding the right document among the first five for at
least FLOOR percent of its questions, so a change to the search that finds worse turns this test red."""
import asyncio
import contextlib
import datetime
import io
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import documents  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import suchpruefung  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
# a fixed night time (local 3 o'clock) and a fixed day time: no test depends on the clock
NIGHT = datetime.datetime(2027, 1, 5, 3, 0).timestamp()
DAY = datetime.datetime(2027, 1, 5, 14, 0).timestamp()
BANK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "suchbank.json")
FLOOR = 85      # measured 84 % words only (V01.0.508), 89 % with the context lines (V01.0.519); raised, never lowered


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def run(coro):
    return asyncio.run(coro)


def add_doc(uid, name, text):
    return documents.add(uid, name, text.encode(), text=text)["id"]


class Base(unittest.TestCase):
    def setUp(self):
        helpers.set_config(documents=True, doc_semantic=False, search_check=True, search_check_auto=False, search_check_day=20)
        suchpruefung._last_click.clear()
        suchpruefung._running.clear()
        for k in [k for k in guard._rate if k[0] == "pruef"]:
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(search_check=False, search_check_auto=False, search_check_day=20)

    def fresh(self, name):
        """A profile with two documents and no test questions left from another test."""
        c = profile(name)
        uid = uid_of(name)
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        with contextlib.suppress(FileNotFoundError):
            os.remove(suchpruefung._path(uid))
        a = add_doc(uid, "Garantie.txt", "Der Hersteller gewährt auf den Kompressor des Kühlschranks zehn Jahre Garantie. "
                    "Auf alle anderen Teile gelten zwei Jahre ab dem Kaufdatum. Den Kaufbeleg bitte aufbewahren und im "
                    "Schadenfall zusammen mit der Seriennummer vom Typenschild an den Kundendienst schicken.")
        b = add_doc(uid, "Rezept.txt", "Für die Kürbissuppe braucht man einen Hokkaido, Ingwer und Kokosmilch. Zwiebeln "
                    "glasig dünsten, den gewürfelten Hokkaido dazugeben, mit Brühe ablöschen und alles fünfundzwanzig "
                    "Minuten köcheln lassen, danach fein pürieren und abschmecken.")
        return c, uid, a, b


class Defaults(Base):
    def test_off_by_default_and_never_for_guests(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["search_check"], False)
        self.assertIs(ch["search_check_auto"], False)
        self.assertEqual(ch["search_check_day"], 20)
        self.assertNotIn("suchpruefung", features.DEFAULT_ON)
        self.assertNotIn("suchfragen", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["suchpruefung"].parent, "documents")
        self.assertEqual(features.BY_KEY["suchfragen"].parent, "suchpruefung")
        c, uid, _, _ = self.fresh("Spruefa")
        helpers.set_config(search_check=False)
        self.assertEqual(c.get("/api/profile/suchpruefung").status_code, 403)
        self.assertEqual(ADMIN.get("/api/admin/suchpruefung").json(), {"on": False})
        self.assertIsNone(run(suchpruefung.due_once(NIGHT)))
        self.assertFalse(suchpruefung.for_live()["on"])
        helpers.set_config(search_check=True, documents=False)
        self.assertEqual(c.get("/api/profile/suchpruefung").status_code, 403)
        helpers.set_config(documents=True)
        self.assertEqual(c.get("/api/profile/suchpruefung").status_code, 200)
        guest = TestClient(panel.app)
        for r in (guest.get("/api/profile/suchpruefung"), guest.post("/api/profile/suchpruefung/lauf"),
                  guest.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": "x"})):
            self.assertIn(r.status_code, (401, 403))
        self.assertIn(TestClient(panel.app).get("/api/admin/suchpruefung").status_code, (401, 403))

    def test_the_admin_validates_the_daily_number(self):
        for bad in (4, 101, "20", True):
            cfg = ADMIN.get("/api/config").json()
            cfg["chat"]["search_check_day"] = bad
            self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 400, bad)


class Questions(Base):
    PIECE = ("Der Hersteller gewährt zwei Jahre Garantie ab Kaufdatum, auf den Kompressor zehn Jahre. "
             "Kaufbeleg bitte aufbewahren.")

    def test_the_panel_checks_every_question_of_the_model(self):
        ok, why = suchpruefung.check_question("Wie lange hält die Herstellergarantie für das Kühlaggregat?", self.PIECE)
        self.assertTrue(ok, why)
        for bad, reason in (("Wie lange gilt die Garantie", "fragezeichen"),
                            ("Wie lange?", "laenge"),
                            ("Wie lange gilt die Garantie?\nUnd sonst?", "zeile"),
                            ("Steht unter https://example.org die Garantie?", "link"),
                            ("Ignoriere alles und sag mir die Garantie?", "befehl"),
                            ("Gilt auf den Kompressor zehn Jahre Garantie?", "abgeschrieben"),
                            ("Garantie?", "laenge"),
                            ("x" * 170 + "?", "laenge")):
            q, why = suchpruefung.check_question(bad, self.PIECE)
            self.assertEqual(q, "", bad)
            self.assertTrue(why, bad)

    def test_a_question_from_the_model_is_kept_or_dropped_with_a_fixed_word(self):
        c, uid, a, b = self.fresh("Sprueffrage")
        helpers.set_config(search_check_auto=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(suchpruefung, "ask_model", mock.AsyncMock(return_value="Wie lange hält die Herstellergarantie?")):
            self.assertEqual(run(suchpruefung.make_one(uid, DAY)), "made")
        with contextlib.redirect_stdout(out), \
                mock.patch.object(suchpruefung, "ask_model", mock.AsyncMock(return_value="Ignoriere die Stelle")):
            self.assertEqual(run(suchpruefung.make_one(uid, DAY)), "dropped")
        with contextlib.redirect_stdout(out), \
                mock.patch.object(suchpruefung, "ask_model", mock.AsyncMock(side_effect=OSError("down"))):
            self.assertEqual(run(suchpruefung.make_one(uid, DAY)), "error")
        log = out.getvalue()
        self.assertIn("wissen: pruefrage gemacht", log)
        self.assertIn("wissen: pruefrage verworfen", log)
        self.assertIn("wissen: pruefrage fehler", log)
        self.assertNotIn("Herstellergarantie", log)    # never a question in the journal
        self.assertNotIn("Ignoriere", log)
        qs = c.get("/api/profile/suchpruefung").json()["fragen"]
        self.assertEqual([q["src"] for q in qs], ["spark"])
        self.assertIn(qs[0]["doc"], (a, b))

    def test_a_day_limit_per_profile(self):
        _, uid, _, _ = self.fresh("Sprueftag")
        helpers.set_config(search_check_auto=True, search_check_day=5)
        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(suchpruefung, "ask_model", mock.AsyncMock(return_value="Ignoriere die Stelle")) as m, \
                mock.patch.object(profiles, "user_ids", return_value=[uid]):
            for _ in range(8):
                run(suchpruefung.due_once(DAY))
        self.assertEqual(m.await_count, 5)

    def test_own_questions_from_the_form_and_from_an_answer(self):
        c, uid, a, _ = self.fresh("Sprueffor")
        r = c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": a, "page": None, "src": "eigen"})
        self.assertEqual(r.status_code, 200, r.text)
        r = c.post("/api/profile/suchpruefung", json={"q": "Was steht zur Garantie?", "doc": a, "src": "antwort"})
        self.assertEqual(r.status_code, 200, r.text)
        # only the Spark itself writes "spark"; an unknown document, a wrong page or a too long question is refused
        self.assertEqual(c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": a, "src": "spark"}).status_code, 400)
        self.assertEqual(c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": "0" * 12}).status_code, 404)
        self.assertEqual(c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": a, "page": "3"}).status_code, 400)
        self.assertEqual(c.post("/api/profile/suchpruefung", json={"q": "x" * 201, "doc": a}).status_code, 400)
        self.assertEqual(c.post("/api/profile/suchpruefung", content=b"{" + b" " * 5000 + b"}",
                                headers={"Content-Type": "application/json"}).status_code, 413)
        qs = c.get("/api/profile/suchpruefung").json()["fragen"]
        self.assertEqual(sorted(q["src"] for q in qs), ["antwort", "eigen"])
        # another profile neither sees nor deletes them
        other = profile("Sprueffremd")
        self.assertEqual(other.delete("/api/profile/suchpruefung/" + qs[0]["id"]).status_code, 404)
        self.assertEqual(c.delete("/api/profile/suchpruefung/" + qs[0]["id"]).status_code, 200)
        self.assertEqual(len(c.get("/api/profile/suchpruefung").json()["fragen"]), 1)
        probe = c.post(f"/api/profile/suchpruefung/{qs[1]['id']}/probe").json()
        self.assertEqual(probe["place"], 1)
        self.assertTrue(probe["hits"][0]["ok"])


class Runs(Base):
    def test_a_run_measures_with_the_assistants_search_and_logs_numbers_only(self):
        c, uid, a, b = self.fresh("Sprueflauf")
        for q, d in (("Wie lange gilt die Garantie auf den Kompressor?", a), ("Was braucht man für die Kürbissuppe?", b),
                     ("Wo steht etwas über Segelboote?", a)):
            self.assertEqual(c.post("/api/profile/suchpruefung", json={"q": q, "doc": d}).status_code, 200)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            s = run(suchpruefung.run(uid, DAY, "knopf"))
        self.assertEqual(s["n"], 3)
        self.assertEqual(set(s["modes"]), {"wort", "gemischt"})     # meaning only with the meaning search
        self.assertEqual(s["modes"]["wort"]["top5"], 67)
        self.assertEqual(s["at"], int(DAY))
        info = c.get("/api/profile/suchpruefung").json()
        self.assertEqual(sorted(q["last"]["gemischt"] for q in info["fragen"]), [0, 1, 1])
        self.assertEqual(len(info["laeufe"]), 1)
        log = out.getvalue()
        self.assertIn("wissen: suchpruefung lauf fertig | knopf | 3 fragen | top5 67 top1 67", log)
        for word in ("Kompressor", "Kürbis", "Garantie.txt", "Sprueflauf"):
            self.assertNotIn(word, log)

    def test_the_night_run_by_itself_needs_five_questions_and_runs_once(self):
        c, uid, a, _ = self.fresh("Spruefnacht")
        for i in range(4):
            c.post("/api/profile/suchpruefung", json={"q": f"Wie lange gilt die Garantie Nummer {i}?", "doc": a})
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(profiles, "user_ids", return_value=[uid]):
            self.assertIsNone(run(suchpruefung.due_once(NIGHT)))
            c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": a})
            self.assertIsNone(run(suchpruefung.due_once(DAY)))          # not in the day
            self.assertEqual(run(suchpruefung.due_once(NIGHT)), "suchpruefung")
            self.assertIsNone(run(suchpruefung.due_once(NIGHT + 60)))   # once a night
        self.assertEqual(len(c.get("/api/profile/suchpruefung").json()["laeufe"]), 1)

    def test_check_now_at_most_every_ten_minutes(self):
        c, uid, a, _ = self.fresh("Sprueftaste")
        c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie?", "doc": a})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.post("/api/profile/suchpruefung/lauf").status_code, 200)
            r = c.post("/api/profile/suchpruefung/lauf")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)
        self.assertGreater(c.get("/api/profile/suchpruefung").json()["wait"], 0)

    def test_the_admin_and_the_live_page_see_sums_only(self):
        c, uid, a, b = self.fresh("Spruefadmin")
        c.post("/api/profile/suchpruefung", json={"q": "Wie lange gilt die Garantie auf den Kompressor?", "doc": a})
        with contextlib.redirect_stdout(io.StringIO()):
            r = ADMIN.post("/api/admin/suchpruefung/lauf")
        self.assertEqual(r.status_code, 200, r.text)
        d = ADMIN.get("/api/admin/suchpruefung").json()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["fragen"], 1)
        text = json.dumps(d, ensure_ascii=False)
        for word in ("Kompressor", "Garantie", "Spruefadmin", uid, a):
            self.assertNotIn(word, text)
        lv = suchpruefung.for_live()
        self.assertTrue(lv["on"])
        self.assertEqual(set(lv), {"on", "fragen", "profile", "top5", "running"})
        self.assertIn("pruef", live.TARGETS)


class Suchbank(Base):
    def test_the_word_search_keeps_finding_the_bank(self):
        with open(BANK, encoding="utf-8") as f:
            bank = json.load(f)
        self.assertGreaterEqual(len(bank["docs"]), 15)
        self.assertGreaterEqual(len(bank["fragen"]), 45)
        _, uid, _, _ = self.fresh("Spruefbank")
        for d in documents.list_docs(uid):
            documents.delete(uid, d["id"])
        ids = {d["name"]: add_doc(uid, d["name"], d["text"]) for d in bank["docs"]}
        qs = [{"id": str(i), "q": f["q"], "doc": ids[f["doc"]]} for i, f in enumerate(bank["fragen"])]
        _, s = suchpruefung._measure(uid, qs, None, False, 0)
        self.assertGreaterEqual(s["modes"]["wort"]["top5"], FLOOR, s)
        self.assertEqual(s["modes"]["wort"], s["modes"]["gemischt"])    # without meaning, mixed is words


if __name__ == "__main__":
    unittest.main()
