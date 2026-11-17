"""Probetag nach dem Wechsel (probetag.py, Dominik 2026-11-16 „1-6“ point 4, stage B2): off by default; after the
language model changed the fixed quality test runs once, and a fixed rule decides: more than SCHLECHTER questions fewer
right than the newest run of the model before → back (the way of „Zurückholen“), else it stays; no run before → stays
without a comparison; a broken test decides nothing. No real model: quality.run is replaced. No time of day."""
import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import modellseite  # noqa: E402
import probetag  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def lauf(passed, total=14, katalog="alt-modell"):
    return {"t": 1, "katalog": katalog, "passed": passed, "total": total}


class Regel(unittest.TestCase):
    def test_off_by_default(self):
        with open(os.path.join(HERE, "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["modelle_probetag"], False)

    def test_the_fixed_rule(self):
        s = probetag.SCHLECHTER
        self.assertEqual(probetag.urteil(lauf(12), lauf(12 + s + 1)), "zurueck")
        self.assertEqual(probetag.urteil(lauf(12), lauf(12 + s)), "behalten")
        self.assertEqual(probetag.urteil(lauf(14), lauf(10)), "behalten")
        self.assertEqual(probetag.urteil(lauf(12), None), "ohne_vergleich")
        self.assertEqual(probetag.urteil(lauf(12), lauf(14, total=15)), "ohne_vergleich")   # other questions
        for neu in (None, {"error": "x", "passed": 0, "total": 0}, lauf(0, total=0)):
            self.assertEqual(probetag.urteil(neu, lauf(14)), "fehler")

    def test_the_run_before_is_the_newest_of_that_catalog_model(self):
        h = [lauf(9), lauf(11, katalog="anderes"), lauf(13), {"katalog": "alt-modell", "passed": 0, "total": 0}]
        self.assertEqual(probetag.letzter_lauf("alt-modell", h)["passed"], 13)
        self.assertIsNone(probetag.letzter_lauf("nie", h))


class Ablauf(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(probetag, "STAND", os.path.join(tempfile.mkdtemp(), "probetag.json"))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        helpers.set_config(modelle_probetag=False)

    def cfg(self, mid, an=True):
        return {"llm": {"enabled": True, "modell": mid}, "chat": {"modelle_probetag": an, "modelle_wechseln": True}}

    def test_a_switch_is_noticed_only_with_the_switch_on(self):
        def an(c):
            return modellseite._probetag_an(c)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(probetag.schritt(self.cfg("alt-modell"), 100, an(self.cfg("alt-modell")), False), "neu")
            self.assertEqual(probetag.stand()["ergebnis"], "")                 # the first look: nothing to compare
            c = self.cfg("neu-modell", an=False)
            self.assertEqual(probetag.schritt(c, 200, an(c), False), "neu")
            self.assertEqual(probetag.stand()["ergebnis"], "")                 # switched off: no trial
            c = self.cfg("drittes")
            self.assertEqual(probetag.schritt(c, 300, an(c), False), "neu")
            self.assertEqual((probetag.stand()["ergebnis"], probetag.stand()["alt"]), ("wartet", "neu-modell"))
            self.assertEqual(probetag.schritt(c, 301, an(c), True), "")       # a test runs already
            self.assertEqual(probetag.schritt(c, 302, an(c), False), "start")
            self.assertEqual(probetag.schritt(c, 300 + probetag.WARTEN_S + 1, an(c), False), "")   # never answered
            self.assertEqual(probetag.stand()["ergebnis"], "fehler")
        self.assertIn("modelle: probetag wartet", out.getvalue())

    def run_trial(self, neu, vorher, an=True):
        probetag._merken({"gesehen": "neu-modell", "alt": "alt-modell", "seit": 1, "ergebnis": "wartet"})
        back = mock.Mock()

        async def fake_run():
            return neu

        async def ready():
            return True
        with contextlib.redirect_stdout(io.StringIO()) as out:
            asyncio.run(probetag.lauf("neu-modell", "alt-modell", lambda: an, ready, fake_run, lambda: vorher,
                                      lambda: back("llm", "zurueck")))
        return probetag.stand(), back, out.getvalue()

    def test_worse_goes_back_like_bring_back(self):
        with open(os.path.join(HERE, "..", "panel", "modellseite.py"), encoding="utf-8") as f:
            src = f.read()          # the page gives the fixed test and the way back: the same as „Zurückholen“
        teil = src[src.index("def probetag_schritt("):src.index("async def _neu_holen(")]
        for x in ('lambda: quality.run("probetag")', "quality.history", 'lambda: wunsch_ohne_seite("llm", "zurueck")',
                  "lambda: health.ready(load_config(), minutes=5)", "quality.running()"):
            self.assertIn(x, teil)
        d, back, log = self.run_trial(lauf(10, katalog="neu-modell"), [lauf(13)])
        back.assert_called_once_with("llm", "zurueck")
        self.assertEqual((d["ergebnis"], d["neu"], d["vorher"]), ("zurueck", [10, 14], [13, 14]))
        self.assertIn("modelle: probetag zurueck 10 13", log)

    def test_as_good_stays_and_nothing_switches(self):
        for neu, vorher, wort in ((lauf(12), [lauf(13)], "behalten"), (lauf(12), [], "ohne_vergleich"),
                                  (None, [lauf(13)], "fehler")):
            d, back, log = self.run_trial(neu, vorher)
            back.assert_not_called()
            self.assertEqual(d["ergebnis"], wort)
            self.assertIn(f"modelle: probetag {wort}", log)

    def test_switched_off_meanwhile_decides_nothing(self):
        d, back, _ = self.run_trial(lauf(3), [lauf(13)], an=False)
        back.assert_not_called()
        self.assertEqual(d["ergebnis"], "aus")

    def test_the_page_shows_the_result(self):
        probetag._merken({"gesehen": "neu-modell", "alt": "alt-modell", "seit": 1, "ergebnis": "zurueck",
                          "neu": [10, 14], "vorher": [13, 14]})
        z = probetag.zeigen(True, kat={})
        self.assertEqual((z["ergebnis"], z["neu"], z["vorher"], z["name"]), ("zurueck", [10, 14], [13, 14], "neu-modell"))
        with open(os.path.join(HERE, "..", "panel", "static", "js", "modelle.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("mdProbetag(d.probetag)", js)
        self.assertTrue(all(w in js for w in probetag.ERGEBNISSE))


if __name__ == "__main__":
    unittest.main()
