"""Rechnen mit festem Werkzeug (rechnen.py, Dominik 2026-10-22): the own parser with its limits, date arithmetic, the
tool rechnen (off by default, never guests, never over MCP) and the answer check that computes sums again."""
import datetime
import decimal
import json
import unittest

from tests import helpers

helpers.start()
import answercheck  # noqa: E402
import extras  # noqa: E402
import panel  # noqa: E402
import rechnen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

D = decimal.Decimal
TODAY = datetime.date(2026, 10, 16)   # a Friday; never the clock

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def value(text, en=False):
    return rechnen.calc(text, en)


class Core(unittest.TestCase):
    def test_exact_with_decimal(self):
        self.assertEqual(value("0.1 + 0.2", True), D("0.3"))
        self.assertEqual(value("17 mal 23"), 391)
        self.assertEqual(value("3,5 plus 2"), D("5.5"))
        self.assertEqual(value("(3 + 4) * 5"), 35)
        self.assertEqual(value("klammer auf 3 plus 4 klammer zu mal 5"), 35)
        self.assertEqual(value("2 hoch 10"), 1024)
        self.assertEqual(value("-3^2"), -9)
        self.assertEqual(value("wurzel aus 16 mal 2"), 8)
        self.assertEqual(value("17 x 23"), 391)
        self.assertEqual(value("1.000.000 geteilt durch 4"), 250000)
        self.assertEqual(value("1,000,000 / 4", True), 250000)

    def test_percent(self):
        self.assertEqual(value("19 % von 249"), D("47.31"))
        self.assertEqual(value("19 Prozent von 249 Euro"), D("47.31"))
        self.assertEqual(value("249 plus 19 %"), D("296.31"))
        self.assertEqual(value("100 - 7 %"), 93)
        self.assertEqual(value("(1200 - 200) * 19 %", True), 190)

    def test_never_eval_and_hard_limits(self):
        for bad, why in (("__import__('os').system('id')", "zeichen"), ("().__class__.__bases__", "zeichen"),
                         ("open('/etc/passwd')", "zeichen"), ("9^9^9", "hoch"), ("2^1000", "hoch"),
                         ("1" + "0" * 30, "gross"), ("10 / 0", "null"), ("(" * 20 + "1" + ")" * 20, "lang"),
                         ("1+" * 120 + "1", "lang"), ("wurzel aus -4", "wurzel"), ("(-8)^0.5", "hoch"),
                         ("5 von 10", "prozent"), ("3 +", "form"), ("(3 + 4", "form"), ("", "leer"),
                         ("3 mal 4 und dann mal 5", "zeichen")):
            with self.assertRaises(rechnen.Fehler, msg=bad) as e:
                rechnen.calc(bad)
            self.assertEqual(e.exception.args[0], why, bad)
            self.assertTrue(rechnen.why(why))
        import ast
        with open(rechnen.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertLessEqual(mods, {"datetime", "decimal", "re", "features", "chat"})   # no sympy, numpy, ast
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(calls & {"eval", "exec", "compile", "__import__", "getattr", "open"}, calls)

    def test_shown_and_spoken(self):
        self.assertEqual(rechnen.show(D(1) / 3), "0,3333333333")
        self.assertEqual(rechnen.say(D(120) / 7), "etwa 17,14")
        self.assertEqual(rechnen.say(D("47.31")), "47,31")
        self.assertEqual(rechnen.say(D(1234567)), "1.234.567")
        self.assertEqual(rechnen.say(D(120) / 7, True), "about 17.14")


class Days(unittest.TestCase):
    def test_days_until_and_between(self):
        self.assertIn("69 Tage (9 Wochen und 6 Tage)", rechnen.days("tage_bis", TODAY, bis="Weihnachten"))
        self.assertIn("364 Tage", rechnen.days("tage_zwischen", TODAY, von="2026-01-01", bis="2026-12-31"))
        self.assertIn("77 Tage (11 Wochen)", rechnen.days("tage_bis", TODAY, bis="1.1.2027"))
        self.assertIn("70 days", rechnen.days("tage_bis", TODAY, bis="christmas", en=True))

    def test_weekday_and_plus(self):
        self.assertEqual(rechnen.days("wochentag", TODAY, datum="24.12.2026"), "Der 24.12.2026 ist ein Donnerstag.")
        self.assertEqual(rechnen.days("wochentag", TODAY, datum="3. März 2027"), "Der 3.3.2027 ist ein Mittwoch.")
        self.assertEqual(rechnen.days("datum_plus", TODAY, tage=90),
                         "90 Tage nach dem 16.10.2026 ist Donnerstag, der 14. Januar 2027.")
        self.assertIn("vor dem", rechnen.days("datum_plus", TODAY, tage=-30))

    def test_limits(self):
        for kw in ({"datum": "2026-13-01"}, {"datum": "irgendwann"}, {"datum": "1.1.1800"}):
            with self.assertRaises(rechnen.Fehler):
                rechnen.days("wochentag", TODAY, **kw)
        with self.assertRaises(rechnen.Fehler):
            rechnen.days("datum_plus", TODAY, tage=10 ** 6)


class Tool(unittest.TestCase):
    def test_results_are_the_panels_words(self):
        art, out = rechnen.run({"ausdruck": "120 / 7"}, TODAY)
        self.assertEqual(art, "zahl")
        self.assertTrue(out.startswith(rechnen.PREFIX + "17,1428571429"), out)
        self.assertEqual(rechnen.value(out), D("17.1428571429"))
        art, out = rechnen.run({"ausdruck": "import os"}, TODAY)
        self.assertTrue(out.startswith("Fehler"), out)
        art, out = rechnen.run({"art": "wochentag", "datum": "2026-12-24"}, TODAY)
        self.assertEqual((art, out), ("wochentag", "Der 24.12.2026 ist ein Donnerstag."))
        art, out = rechnen.run({"art": "datum_plus", "tage": "viele"}, TODAY)
        self.assertTrue(out.startswith("Fehler"), out)

    def test_offered_only_when_on_never_guests_never_mcp(self):
        helpers.keep_chat(self, "rechnen")
        p = profile("Rechnen1")
        who = {"id": p.get("/api/whoami").json()["profile"]["id"], "name": "Rechnen1"}
        ctx = {"who": who, "own": True, "text": "Rechne 19 Prozent von 249 Euro aus"}
        helpers.set_config(rechnen=False)
        self.assertNotIn("rechnen", extras.offer(ctx)["run"])
        helpers.set_config(rechnen=True)
        self.assertIn("rechnen", extras.offer(ctx)["run"])
        self.assertIn("rechnen", extras.offer(ctx)["keep"])
        self.assertNotIn("rechnen", extras.offer(dict(ctx, who=None))["run"])        # a guest
        self.assertNotIn("rechnen", extras.offer(dict(ctx, own=False))["run"])       # another voice
        self.assertNotIn("rechnen", extras.offer(dict(ctx, client="mcp"))["run"])    # a program over MCP
        self.assertNotIn("rechnen", extras.offer(dict(ctx, text="Wie wird das Wetter?"))["run"])


class Check(unittest.TestCase):
    def test_a_wrong_result_is_replaced(self):
        self.assertEqual(rechnen.fix("17 mal 23 ist 381.")[:2], ("17 mal 23 ist 391.", 1))
        self.assertEqual(rechnen.fix("19 % von 249 € sind 47,30 €.")[:2], ("19 % von 249 € sind 47,31 €.", 1))
        self.assertEqual(rechnen.fix("3 x 4 sind 13 Stück.")[:2], ("3 x 4 sind 12 Stück.", 1))
        self.assertEqual(rechnen.fix("1.200 + 300 ergibt 1.400 Euro.")[:2], ("1.200 + 300 ergibt 1.500 Euro.", 1))
        self.assertEqual(rechnen.fix("6 times 7 is 41.", True)[:2], ("6 times 7 is 42.", 1))

    def test_right_rounded_or_no_sum_stays(self):
        for s in ("2 + 2 ist 4.", "Das macht 120 / 7 = 17,14.", "120 geteilt durch 7 ist etwa 17.",
                  "Zwischen 10-12 sind es 5 Grad.", "Um 14:20 + 5 ist es spät.", "Am 24.12. ist Heiligabend.",
                  "Ruf 0171 - 1234 ist die Nummer"):
            self.assertEqual(rechnen.fix(s)[:2], (s, 0), s)

    def test_panel_results_are_known_figures(self):
        have = answercheck.known([rechnen.PREFIX + "47,31 (gesprochen: 47,31). Sag genau diese Zahl."])
        self.assertEqual(answercheck.unsupported("Das sind 47,31 €.", have), [])
        self.assertTrue(answercheck.unsupported("Das sind 48,00 €.", have))
        self.assertEqual(answercheck.known(["Ergebnis vom Modell: 47,31"]), set())


class Chat(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "rechnen", "sofort")
        helpers.LLM_CALLS.clear()

    def ask(self, p, q):
        r = p.post("/api/chat", json={"messages": [{"role": "user", "content": q}]})
        self.assertEqual(r.status_code, 200, r.text)
        return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")

    def test_the_model_says_a_wrong_sum_the_panel_corrects_it(self):
        helpers.set_config(rechnen=True, sofort=False)
        said = self.ask(profile("Rechnen2"), "SAY | | 17 mal 23 ist 381.")
        self.assertEqual(said, "17 mal 23 ist 391.")

    def test_off_nothing_is_changed(self):
        helpers.set_config(rechnen=False, sofort=False)
        said = self.ask(profile("Rechnen3"), "SAY | | 17 mal 23 ist 381.")
        self.assertEqual(said, "17 mal 23 ist 381.")

    def test_the_tool_runs(self):
        helpers.set_config(rechnen=True, sofort=False)
        said = self.ask(profile("Rechnen4"), "TOOL rechnen " + json.dumps({"ausdruck": "19 % von 249"}))
        self.assertIn(rechnen.PREFIX + "47,31", said)


if __name__ == "__main__":
    unittest.main()
