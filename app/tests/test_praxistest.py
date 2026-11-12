"""Zustand → Praxistest (praxistest.py, praxistest.json; plan plaene/verbesserungen-2026-10-16.md, 4a): one list of
points in the repository, numbers never change, only admins see and mark them, the mark is all that is kept, old
points fold away, „Braucht dich“ stays quiet (info), every result writes a fixed log line. Three tiers (code review
2026-11-11, point 7): „Jetzt wichtig“ is short, a point covered by a self-test names a test that is there."""
import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout

from tests import helpers

helpers.start()
import panel  # noqa: E402
import health  # noqa: E402
import praxistest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HOME = ("192.168.178.20", 50000)


def admin():
    c = TestClient(panel.app, client=HOME)
    assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    return c


def read(*p):
    with open(os.path.join(helpers.APP, "panel", *p), encoding="utf-8") as f:
        return f.read()


class Liste(unittest.TestCase):
    def test_points_are_well_formed(self):
        with open(praxistest.PUNKTE_FILE, encoding="utf-8") as f:
            raw = json.load(f)["punkte"]
        ids = [p["id"] for p in raw]
        self.assertEqual(len(ids), len(set(ids)), "a number twice")
        self.assertEqual(ids, [f"P{i:03d}" for i in range(1, len(ids) + 1)], "numbers in order, none left out")
        for p in raw:
            self.assertTrue(set(p) <= {"id", "v", "titel", "text", "thread", "erledigt", "aktuell", "test", "wichtig"}, p["id"])
            self.assertIn(p.get("wichtig", True), (True,), p["id"] + ": wichtig is true or left out")
            self.assertFalse("test" in p and "wichtig" in p, p["id"] + ": covered by a self-test or important, not both")
            self.assertIsInstance(p["v"], int, p["id"])
            self.assertTrue(100 <= p["v"] < 10000, p["id"])
            self.assertTrue(p["titel"].strip() and len(p["titel"]) <= 120, p["id"])
            self.assertTrue(p["text"].strip() and len(p["text"]) <= 2500, p["id"])
            self.assertNotRegex(p["text"] + p["titel"], r"(?i)<\s*/?\s*(script|a|img|iframe|style|div|span|svg)\b", p["id"] + ": no markup")
        self.assertEqual(len(praxistest.punkte()), len(raw))

    def test_a_covered_point_names_a_test_that_is_there(self):
        """„Durch Selbsttest abgedeckt“ takes a point out of what waits for the admin, so the named test has to be
        there: module.Class.test_name in tests/, read as text (no import, also in a copy with only app/)."""
        named = [p for p in praxistest.punkte() if "test" in p]
        self.assertTrue(named)
        for p in named:
            self.assertRegex(str(p["test"]), r"^test_[a-z0-9_]+\.[A-Za-z0-9_]+\.test_[a-z0-9_]+$", p["id"])
            mod, cls, name = p["test"].split(".")
            path = os.path.join(helpers.APP, "tests", mod + ".py")
            self.assertTrue(os.path.isfile(path), p["id"])
            with open(path, encoding="utf-8") as f:
                src = f.read()
            m = re.search(rf"^class {cls}\b.*?(?=^class |\Z)", src, re.S | re.M)
            self.assertTrue(m, p["id"] + ": class " + cls)
            body = re.search(rf"^    def {name}\(self\):\n(.*?)(?=^    def |\Z)", m.group(0), re.S | re.M)
            self.assertTrue(body, p["id"] + ": " + name)
            self.assertNotRegex(body.group(1), r"SkipTest|skipTest", p["id"] + ": the test must really run")

    def test_guideline_points_here(self):
        if not os.path.isdir(os.path.join(os.path.dirname(helpers.APP), "docs")):
            raise unittest.SkipTest("only app/ in this copy")
        for parts in (("docs", "de", "richtlinien.md"), ("docs", "en", "guidelines.md")):
            with open(os.path.join(os.path.dirname(helpers.APP), *parts), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("app/panel/praxistest.json", text, parts)
            self.assertNotIn("praxistest-tars-2.md", text, parts)


class Seite(unittest.TestCase):
    def setUp(self):
        if os.path.exists(praxistest.STAND_FILE):
            os.remove(praxistest.STAND_FILE)
        self.addCleanup(lambda: os.path.exists(praxistest.STAND_FILE) and os.remove(praxistest.STAND_FILE))

    def test_admin_only(self):
        c = TestClient(panel.app, client=HOME)
        self.assertIn(c.get("/api/admin/praxistest").status_code, (401, 403))
        self.assertIn(c.post("/api/admin/praxistest/P001", json={"stand": "ok"}).status_code, (401, 403))
        self.assertIn(c.post("/api/admin/praxistest/alt", json={}).status_code, (401, 403))

    def test_mark_keeps_only_the_word_and_logs_it(self):
        a = admin()
        newest = max(praxistest.punkte(), key=lambda p: p["v"])["id"]
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(a.post(f"/api/admin/praxistest/{newest}", json={"stand": "problem"}).status_code, 200)
            self.assertEqual(a.post("/api/admin/praxistest/P999", json={"stand": "ok"}).status_code, 404)
            self.assertEqual(a.post(f"/api/admin/praxistest/{newest}", json={"stand": "erledigt"}).status_code, 400)
            self.assertEqual(a.post(f"/api/admin/praxistest/{newest}", json={"stand": "x" * 300}).status_code, 413)
        lines = out.getvalue().splitlines()
        self.assertIn(f"praxistest: problem {newest}", lines)
        self.assertIn("praxistest: abgelehnt punkt", lines)
        self.assertIn("praxistest: abgelehnt stand", lines)
        with open(praxistest.STAND_FILE, encoding="utf-8") as f:
            kept = json.load(f)
        self.assertEqual(set(kept), {newest})
        self.assertEqual(set(kept[newest]), {"s", "t"})
        d = a.get("/api/admin/praxistest").json()
        self.assertEqual(d["punkte"][0]["v"], max(p["v"] for p in praxistest.punkte()), "the newest first")
        self.assertEqual(next(p for p in d["punkte"] if p["id"] == newest)["stand"], "problem")
        self.assertEqual(d["zahlen"]["problem"], 1)
        a.post(f"/api/admin/praxistest/{newest}", json={"stand": "offen"})
        self.assertNotIn(newest, praxistest.stand())

    def test_old_points_fold_away_and_go_at_once(self):
        a = admin()
        d = a.get("/api/admin/praxistest").json()
        alt = [p for p in d["punkte"] if p["alt"]]
        self.assertTrue(alt)
        self.assertTrue(all(p["v"] < praxistest.ALT_BIS for p in alt))
        self.assertFalse(any(p["alt"] for p in d["punkte"] if p["v"] >= praxistest.ALT_BIS))
        out = io.StringIO()
        with redirect_stdout(out):
            r = a.post("/api/admin/praxistest/alt", json={})
        self.assertEqual(r.json()["n"], len(alt))
        self.assertIn(f"praxistest: alt erledigt {len(alt)}", out.getvalue().splitlines())
        d = a.get("/api/admin/praxistest").json()
        self.assertEqual(d["zahlen"]["alt"], 0)
        self.assertEqual(d["zahlen"]["erledigt"], len(alt) + sum(1 for p in praxistest.punkte() if p.get("erledigt")))

    def test_braucht_dich_is_quiet(self):
        a = [x for x in health.alerts() if x["kind"] == "praxistest"]
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["level"], a[0]["go"]), ("info", "Zustand → Praxistest"))
        self.assertRegex(a[0]["text"], r"^\d+ Praxistests? (ist|sind) jetzt wichtig\.$")
        self.assertLessEqual(int(a[0]["text"].split()[0]), praxistest.WICHTIG_MAX, "the line counts only „Jetzt wichtig“")
        for p in praxistest.punkte():
            praxistest._merke([p["id"]], "ok")
        self.assertEqual([x for x in health.alerts() if x["kind"] == "praxistest"], [])


class Stufen(unittest.TestCase):
    """Code review 2026-11-11, point 7: three tiers with fixed rules; the list itself decides, with points of its own
    here so the test does not depend on what the threads add."""

    def setUp(self):
        if os.path.exists(praxistest.STAND_FILE):
            os.remove(praxistest.STAND_FILE)
        self.addCleanup(lambda: os.path.exists(praxistest.STAND_FILE) and os.remove(praxistest.STAND_FILE))
        old = dict(praxistest._punkte)
        self.addCleanup(lambda: praxistest._punkte.update(old))

    def use(self, pts):
        praxistest._punkte.update(mtime=os.path.getmtime(praxistest.PUNKTE_FILE), v=pts)

    @staticmethod
    def pt(i, v, **more):
        return dict({"id": f"P{i:03d}", "v": v, "titel": "t", "text": "x"}, **more)

    def tiers(self):
        d = praxistest.seite()
        return {p["id"]: p["stufe"] for p in d["punkte"]}, d["zahlen"]

    def test_the_newest_versions_are_important_the_rest_waits(self):
        self.use([self.pt(1, 300), self.pt(2, 700), self.pt(3, 1001), self.pt(4, 1002), self.pt(5, 1003), self.pt(6, 1003)])
        t, n = self.tiers()
        self.assertEqual(t, {"P001": "", "P002": "gelegenheit", "P003": "wichtig", "P004": "wichtig",
                             "P005": "wichtig", "P006": "wichtig"})
        self.assertEqual((n["wichtig"], n["gelegenheit"], n["abgedeckt"], n["alt"], n["offen"]), (4, 1, 0, 1, 5))
        praxistest._merke(["P006"], "ok")              # a marked point leaves its tier, the versions stay the newest three
        t, n = self.tiers()
        self.assertEqual((t["P006"], t["P002"], n["wichtig"]), ("", "gelegenheit", 3))

    def test_important_is_short_and_marked_points_come_first(self):
        pts = [self.pt(i, 1000 + i // 8) for i in range(1, 25)] + [self.pt(25, 700, wichtig=True)]
        self.use(pts)
        t, n = self.tiers()
        self.assertEqual(n["wichtig"], praxistest.WICHTIG_MAX)
        self.assertEqual(t["P025"], "wichtig", "a point marked for security is in although it is older")
        self.assertEqual(t["P024"], "wichtig")
        self.assertEqual(t["P001"], "gelegenheit")
        self.assertEqual(n["wichtig"] + n["gelegenheit"], 25)

    def test_a_covered_point_waits_for_nobody_and_a_problem_always_does(self):
        self.use([self.pt(1, 1001, test="test_praxistest.Stufen.test_x"), self.pt(2, 700), self.pt(3, 1002),
                  self.pt(4, 1003), self.pt(5, 1004)])
        t, n = self.tiers()
        self.assertEqual(t, {"P001": "abgedeckt", "P002": "gelegenheit", "P003": "wichtig", "P004": "wichtig",
                             "P005": "wichtig"})
        self.assertEqual((n["offen"], n["abgedeckt"]), (4, 1))
        praxistest._merke(["P003", "P004", "P005"], "ok")
        self.assertEqual(praxistest.alerts(), [], "what waits for when there is time or is covered asks for nobody")
        praxistest._merke(["P002"], "problem")
        t, n = self.tiers()
        self.assertEqual((t["P002"], n["problem"], n["wichtig"]), ("wichtig", 1, 0))
        self.assertEqual(praxistest.alerts()[0]["text"], "1 hat ein Problem.")
        praxistest._merke(["P001"], "ok")              # the admin may still mark a covered point
        self.assertEqual(self.tiers()[1]["abgedeckt"], 0)

    def test_the_tier_is_counted_never_kept(self):
        a = admin()
        d = a.get("/api/admin/praxistest").json()
        self.assertTrue(all(p["stufe"] in praxistest.STUFEN + ("",) for p in d["punkte"]))
        self.assertTrue(all(p["stufe"] == "" for p in d["punkte"] if p["alt"] or p["stand"] not in ("", "problem")))
        first = next(p for p in d["punkte"] if p["stufe"] == "wichtig")["id"]
        a.post(f"/api/admin/praxistest/{first}", json={"stand": "spaeter"})
        with open(praxistest.STAND_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)[first].keys(), {"s", "t"})


class Oberflaeche(unittest.TestCase):
    def test_wired_into_the_panel(self):
        html, base, js, co, en = (read("static", "index.html"), read("static", "js", "base.js"),
                                  read("static", "js", "praxistest.js"), read("static", "js", "coadmin.js"),
                                  read("static", "js", "i18n.js"))
        self.assertIn('<section id="praxis">', html)
        self.assertIn('<script src="/static/js/praxistest.js"></script>', html)
        self.assertIn("['praxis',t('Praxistest','Hands-on test')]", base)
        self.assertIn("lzb($('ptbox'),loadPraxis)", base)
        self.assertIn("x[0]!=='praxis'", co)          # a Verwalter does not see it
        self.assertIn('"Praxistest": "Hands-on test"', en)
        self.assertNotIn("innerHTML", js)              # the steps go in as text only
        self.assertNotIn("fetch(", js)
        for word in ("Jetzt wichtig", "Bei Gelegenheit", "Durch Selbsttest abgedeckt"):
            self.assertIn(word, js)
        self.assertEqual(sorted(set(re.findall(r"api\('(/api/admin/praxistest[a-z/]*)'", js))),
                         ["/api/admin/praxistest", "/api/admin/praxistest/", "/api/admin/praxistest/alt"])


if __name__ == "__main__":
    unittest.main()
