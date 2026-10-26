"""KI-Dungeon-Master: the own throw (dungeon_warten.py, dungeonwarten.js, dungeon-ton.js; Dominik 2026-10-25
„1a 2a 3 4a b c“).

- 1a: an own die not thrown when the narration came waits in its seat's feed at its place, the narration after it
  veiled until the throw, at most WURF_MAX_S, then it throws itself; only its own seat sees it waiting; the number
  stays the one the panel rolled before, the tap only shows it.
- 2a/3: the throw flies, hits, hops and always lands on the panel's number; the landing's colour (made, missed, 20, 1).
- 4: the phone buzzes on the landing, a long press throws further (display only), a waiting die chimes once.

No wall clock in the checks: every time is given.
"""
import os
import re
import unittest

from tests import helpers  # noqa: F401 - the panel's path and state folder

import dungeon_warten as warten  # noqa: E402

PANEL = os.path.dirname(os.path.abspath(warten.__file__))


def js(name):
    with open(os.path.join(PANEL, "static", "js", name), encoding="utf-8") as f:
        return f.read()


def round_with_dice(thrown=False):
    die = {"pid": "p1", "name": "Mira", "wert": "ges", "w": 17, "gesamt": 19, "schwer": 14, "ok": True}
    rd = {"dm": "denkt", "zug": 4, "plaetze": {"p1": {}, "p2": {}},
          "warten": {"s": "erzaehlen", "wt": 1000.0, "w": [dict(die, geworfen=thrown), dict(die, pid="p2", name="Bo", w=3, gesamt=4, ok=False)]},
          "log": [dict({k: die[k] for k in ("pid", "name", "wert", "w", "gesamt", "schwer", "ok")}, art="wurf", n=4),
                  {"art": "wurf", "pid": "p2", "name": "Bo", "wert": "ges", "w": 3, "gesamt": 4, "schwer": 14, "ok": False, "n": 4},
                  {"art": "dm", "text": "Mira springt.", "n": 4}]}
    return rd


class WaitsInTheFeed(unittest.TestCase):
    def test_own_die_waits_after_the_narration(self):
        rd = round_with_dice()
        warten.end(rd, now=2000.0)
        self.assertNotIn("warten", rd)
        self.assertEqual(warten.waiting(rd, "p1", now=2005.0),
                         [{"name": "Mira", "wert": "ges", "schwer": 14, "n": 4, "rest": warten.WURF_MAX_S - 5}])
        self.assertEqual(len(warten.waiting(rd, "p2", now=2005.0)), 1)
        self.assertNotIn("w", warten.waiting(rd, "p1", now=2005.0)[0])          # never the number, only what is checked
        self.assertEqual(warten.waiting(rd, "p1", now=2000.0 + warten.WURF_MAX_S + 1), [])   # then it throws itself

    def test_a_thrown_die_does_not_wait(self):
        rd = round_with_dice(thrown=True)
        warten.end(rd, now=2000.0)
        self.assertEqual(warten.waiting(rd, "p1", now=2001.0), [])

    def test_the_throw_ends_the_wait_of_its_seat_only(self):
        rd = round_with_dice()
        warten.end(rd, now=2000.0)
        self.assertTrue(warten.throw(rd, "p1"))
        self.assertEqual(warten.waiting(rd, "p1", now=2001.0), [])
        self.assertEqual(len(warten.waiting(rd, "p2", now=2001.0)), 1)
        self.assertTrue(warten.throw(rd, "p2"))
        self.assertNotIn("wurf_offen", rd)
        self.assertFalse(warten.throw(rd, "p2"))

    def test_old_waits_go_with_the_next_narration(self):
        rd = round_with_dice()
        warten.end(rd, now=2000.0)
        rd["warten"] = {"s": "erzaehlen", "w": []}
        warten.end(rd, now=2000.0 + warten.WURF_MAX_S + 5)
        self.assertNotIn("wurf_offen", rd)

    def test_no_log_line_no_wait(self):
        rd = round_with_dice()
        rd["log"] = []                                    # the narration failed: nothing to throw into the feed
        warten.end(rd, now=2000.0)
        self.assertNotIn("wurf_offen", rd)


class RoundTwo(unittest.TestCase):
    """D&D round 2 idea 1 (Dominik 2026-10-26 „1-9 umsetzten“): a check missed by 1 or 2 and passed at a price carries
    "knapp", the price's id and its line from the dice receipt (dungeon_knapp) into the wait; the others see it only
    once the die is open."""
    def test_missed_by_a_little_goes_into_the_wait(self):
        rd = {"dm": "denkt", "welt": "fantasy", "plaetze": {"p1": {}, "p2": {}}}
        die = {"pid": "p1", "name": "Mira", "wert": "ges", "w": 12, "gesamt": 13, "schwer": 14, "ok": True, "knapp": True, "preis": "laerm", "preis_t": "Es poltert laut."}
        warten.step(rd, "wuerfeln", wuerfe=[die, dict(die, pid="p2", name="Bo", knapp=False, preis="")])
        self.assertEqual([(x["knapp"], x["preis"]) for x in rd["warten"]["w"]], [(True, "laerm"), (False, "")])
        wt = rd["warten"]["wt"]
        own = warten._die(rd["warten"]["w"][0], "p1", wt, wt)
        self.assertEqual((own["knapp"], own["preis"], own["preis_t"]), (True, "laerm", "Es poltert laut."))
        hidden = warten._die(rd["warten"]["w"][0], "p2", wt + 1, wt)        # another seat's die, not thrown yet
        self.assertNotIn("knapp", hidden)
        self.assertNotIn("w", hidden)
        self.assertIn("Knapp geschafft, mit Preis", js("dungeonwarten.js"))


class Page(unittest.TestCase):
    def test_feed_keeps_the_die_and_veils_what_follows(self):
        w, d = js("dungeonwarten.js"), js("dungeon.js")
        self.assertIn("window.dmWFeed?dmWFeed(v,col)", d)
        self.assertIn("dm-verhuellt", w)
        self.assertIn("const WURF_MAX=%d;" % warten.WURF_MAX_S, w)     # one number on both sides
        self.assertRegex(w, r"dmWAuto\(v,k,o\.rest\)")                  # it throws itself when the ring ran down
        self.assertRegex(w, r"dmWOffen\(v,e\)")

    def test_the_throw_lands_on_the_panels_number(self):
        t = js("dungeon-ton.js")
        body = t[t.index("function dmtWurf("):]
        self.assertIn("num.textContent=x.w", body)
        self.assertNotRegex(body, r"num\.textContent=String\(f\)[^}]*\}\s*,\s*DMT_WURF_MS\)")   # the last face is never a random one
        self.assertIn("prefers-reduced-motion", body)
        self.assertIn("navigator.vibrate", t)
        self.assertRegex(t, r"dran:v=>")
        self.assertRegex(t, r"klack:v=>")
        self.assertNotIn(".mp3", t)

    def test_landing_colours(self):
        css = open(os.path.join(PANEL, "static", "app.css"), encoding="utf-8").read()
        for c in ("dm-wok", "dm-wbad", "dm-wkrit", "dm-wpatzer"):
            self.assertIn(c, css)
            self.assertIn(c, js("dungeon-ton.js"))


if __name__ == "__main__":
    unittest.main()
