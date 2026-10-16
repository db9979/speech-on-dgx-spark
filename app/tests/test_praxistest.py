"""Zustand → Praxistest (praxistest.py, praxistest.json; plan plaene/verbesserungen-2026-10-16.md, 4a): one list of
points in the repository, numbers never change, only admins see and mark them, the mark is all that is kept, old
points fold away, „Braucht dich“ stays quiet (info), every result writes a fixed log line."""
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
            self.assertTrue(set(p) <= {"id", "v", "titel", "text", "thread", "erledigt", "aktuell"}, p["id"])
            self.assertIsInstance(p["v"], int, p["id"])
            self.assertTrue(100 <= p["v"] < 10000, p["id"])
            self.assertTrue(p["titel"].strip() and len(p["titel"]) <= 120, p["id"])
            self.assertTrue(p["text"].strip() and len(p["text"]) <= 2500, p["id"])
            self.assertNotRegex(p["text"] + p["titel"], r"(?i)<\s*/?\s*(script|a|img|iframe|style|div|span|svg)\b", p["id"] + ": no markup")
        self.assertEqual(len(praxistest.punkte()), len(raw))

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
        self.assertRegex(a[0]["text"], r"^\d+ Praxistests? (ist|sind) offen\.$")
        for p in praxistest.punkte():
            praxistest._merke([p["id"]], "ok")
        self.assertEqual([x for x in health.alerts() if x["kind"] == "praxistest"], [])


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
        self.assertEqual(sorted(set(re.findall(r"api\('(/api/admin/praxistest[a-z/]*)'", js))),
                         ["/api/admin/praxistest", "/api/admin/praxistest/", "/api/admin/praxistest/alt"])


if __name__ == "__main__":
    unittest.main()
