"""Wappen für Gruppe und Fraktionen (dungeon_wappen.py, D&D-Idee 10): coats of arms as SVG of the panel's own parts.

- The same start value always gives the same arms; every code is words of the fixed lists; the old rule of tinctures
  holds (metal next to colour, a charge that stands out or is counterchanged).
- check lets only the elements and attributes of ERLAUBT through: no script, no handler, no link, no style, no text,
  no reference out of the picture; every arms the panel can build passes it.
- A faction never carries the group's colour with the group's charge.
- Off by default: without its admin switch (chat.dungeon_wappen) the view has no arms and the choice is refused.
- A seat sees the group's arms and those of the factions it knows (their clock, their banner); an unknown faction's
  arms only the host (sight filter), with the choice.
- Only the host chooses colour and charge; the rest of the arms stays; a campaign keeps them from chapter to chapter;
  the sweep drops the choices of rounds that are gone; Live only counts.
"""
import os
import re
import shutil
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import guard  # noqa: E402
import dungeon  # noqa: E402
import dungeon_wappen as wappen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
HERO = {"name": "Arvid", "volk": "mensch", "klasse": "krieger", "satz": ""}
_PROFILES = {}


def profile(name):
    if name not in _PROFILES:
        guard.reset()
        r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
        assert r.status_code in (200, 409), r.text
        c = TestClient(panel.app)
        assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
        _PROFILES[name] = (c, c.get("/api/whoami").json()["profile"]["id"])
    return _PROFILES[name]


def wipe():
    for f in (dungeon.FILE, dungeon.FIGUREN, dungeon.EIGENE):
        if os.path.exists(f):
            os.remove(f)
    shutil.rmtree(dungeon.ablage.DIR, ignore_errors=True)               # every round is a file of its own (Punkt 14)
    dungeon._rules["r"] = None


class Drawing(unittest.TestCase):
    def test_same_start_value_same_arms_by_the_old_rule(self):
        seen = set()
        for i in range(400):
            c = wappen.make(f"probe|{i}")
            self.assertEqual(c, wappen.make(f"probe|{i}"))
            schild, teilung, t1, t2, z, tz = wappen._parts(c)
            self.assertNotEqual(t1 in wappen.METALLE, t2 in wappen.METALLE, c)      # metal next to colour
            if teilung in wappen.VERWECHSELT:
                self.assertEqual(tz, "x", c)                                       # counterchanged on a divided field
            else:
                self.assertNotEqual(t1 in wappen.METALLE, tz in wappen.METALLE, c)  # the charge stands out
                self.assertNotEqual(tz, t2, c)
            seen.add(c)
        self.assertGreater(len(seen), 390)

    def test_a_choice_changes_only_colour_and_charge(self):
        a = wappen._parts(wappen.make("gruppe|x"))
        b = wappen._parts(wappen.make("gruppe|x", "blau", "turm"))
        self.assertEqual((b[2], b[4]), ("blau", "turm"))
        self.assertEqual(a[:2], b[:2])                                             # shield and division stay
        self.assertEqual(wappen.make("gruppe|x", "nicht", "da"), wappen.make("gruppe|x"))

    def test_every_arms_passes_the_check(self):
        for sh in wappen.SCHILDE:
            for t in wappen.TEILUNGEN:
                for z in wappen.CHARGES:
                    code = "-".join((sh, t, "gold", "rot", z, "x" if t in wappen.VERWECHSELT else "blau"))
                    s = wappen.svg(code)
                    self.assertTrue(s.startswith("<svg "), code)
                    self.assertLess(len(s), wappen.SVG_MAX)
        for z in wappen.CHARGES:
            wappen.check(wappen.zeichen_svg(z))

    def test_only_codes_of_the_lists(self):
        for bad in ("", None, "spitz", "spitz-schlicht-gold-rot-stern-blau-x", "spitz-schlicht-gold-rot-<script>-blau",
                    "SPITZ-schlicht-gold-rot-stern-blau", "spitz-schlicht-gold-rot-stern-blau\n"):
            self.assertEqual(wappen.svg(bad), "", bad)

    def test_check_refuses_anything_that_could_run_or_fetch(self):
        ns = 'xmlns="http://www.w3.org/2000/svg"'
        for bad in (f'<svg {ns}><script>alert(1)</script></svg>',
                    f'<svg {ns} onload="alert(1)"><path d="M0 0"/></svg>',
                    f'<svg {ns}><path d="M0 0" onclick="x()"/></svg>',
                    f'<svg {ns}><image href="https://example.org/x.png"/></svg>',
                    f'<svg {ns} xmlns:x="http://www.w3.org/1999/xlink"><path x:href="#a" d="M0 0"/></svg>',
                    f'<svg {ns}><path d="M0 0" fill="url(https://example.org/#a)"/></svg>',
                    f'<svg {ns}><path d="M0 0" style="fill:red"/></svg>',
                    f'<svg {ns}><foreignObject/></svg>',
                    f'<svg {ns}><text>hallo</text></svg>',
                    f'<svg {ns}><path d="M0 0" transform="matrix(1 0 0 1 0 0)"/></svg>',
                    '<svg><path d="M0 0"/></svg>',
                    f'<!DOCTYPE svg [<!ENTITY a "b">]><svg {ns}><path d="&a;"/></svg>',
                    f'<svg {ns}>' + "<g>" * 20 + "x" * wappen.SVG_MAX + "</g>" * 20 + "</svg>",
                    "kein svg"):
            with self.assertRaises(ValueError, msg=bad[:60]):
                wappen.check(bad)


class Table(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Wappen Walda")
        cls.g, cls.guid = profile("Wappen Gunda")

    def setUp(self):
        helpers.keep_chat(self, "dungeon", "dungeon_wappen", "dungeon_fraktionen")
        helpers.set_config(dungeon=True, dungeon_wappen=True, dungeon_fraktionen=True)
        guard.reset()
        for k in [k for k in guard._rate if str(k[0]).startswith("dungeon")]:
            guard._rate.pop(k, None)
        wipe()
        self.addCleanup(wipe)
        for f in (dungeon._hfile(self.uid), dungeon._kfile(self.uid), wappen._file(self.uid)):
            if os.path.exists(f):
                os.remove(f)
        wappen._sweep[0] = 0.0
        wappen._day.clear()

    def new_round(self, **kw):
        b = {"titel": "Die Glocke", "welt": "fantasy", "ton": 12, "zug_s": 120, "stunden": 6, "held": dict(HERO)}
        b.update(kw)
        r = self.c.post("/api/profile/dungeon/runde", json=b)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["rid"]

    def factions(self, rid):
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][rid]["fraktionen"] = {
                "die rabengilde": {"name": "Die Rabengilde", "will": "", "felder": 6, "stand": 1, "bekannt": True,
                                   "voll": None, "ort": None, "eigen": False},
                "der sternorden": {"name": "Der Sternorden", "will": "", "felder": 4, "stand": 0, "bekannt": False,
                                   "voll": None, "ort": None, "eigen": False}}
            dungeon._write(d)

    def guest_view(self, rid):
        """The view of a second seat (a profile at the table, not the host)."""
        with dungeon._lock:
            d = dungeon._read()
            rd = d["runden"][rid]
            rd["plaetze"]["pgast0001"] = {"h": "", "uid": self.guid, "held": None, "made": 1, "gast": False}
            dungeon._write(d)
        return dungeon.view(rid, "pgast0001")

    def test_off_shows_nothing_and_refuses_the_choice(self):
        rid = self.new_round()
        helpers.set_config(dungeon_wappen=False)
        v = self.c.get(f"/api/profile/dungeon/{rid}").json()
        self.assertNotIn("wappen", v)
        r = self.c.post(f"/api/profile/dungeon/{rid}/wappen", json={"farbe": "blau"})
        self.assertEqual(r.status_code, 409)
        self.assertFalse(os.path.exists(wappen._file(self.uid)))

    def test_a_seat_sees_only_the_factions_it_knows(self):
        rid = self.new_round()
        self.factions(rid)
        host = self.c.get(f"/api/profile/dungeon/{rid}").json()
        w = host["wappen"]
        self.assertTrue(wappen._parts(w["gruppe"]))
        self.assertEqual(set(w["fr"]), {"die rabengilde"})
        geheim = {x["name"]: x["wappen"] for x in host["fraktionen_geheim"]["alle"]}
        self.assertEqual(set(geheim), {"Die Rabengilde", "Der Sternorden"})
        self.assertIn(geheim["Der Sternorden"], w["svg"])                       # the host draws every faction
        self.assertIn("wahl", w)
        seat = self.guest_view(rid)
        sw = seat["wappen"]
        self.assertEqual(sw["gruppe"], w["gruppe"])
        self.assertEqual(sw["fr"], w["fr"])
        self.assertNotIn(geheim["Der Sternorden"], sw["svg"])                  # an unknown faction's arms: host only
        self.assertNotIn("wahl", sw)
        self.assertNotIn("Sternorden", repr(sw))
        for s in sw["svg"].values():
            wappen.check(s)

    def test_a_faction_never_wears_the_groups_colour_with_its_charge(self):
        rid = self.new_round()
        rd = dungeon._read()["runden"][rid]
        g = wappen._parts(wappen.gruppe(rd))
        for i in range(300):
            f = wappen._parts(wappen.fraktion(rd, f"Gilde {i}"))
            self.assertNotEqual((f[2], f[4]), (g[2], g[4]))
        self.assertEqual(wappen.fraktion(rd, " "), "")

    def test_only_the_host_chooses_and_the_rest_stays(self):
        rid = self.new_round()
        before = self.c.get(f"/api/profile/dungeon/{rid}").json()["wappen"]["gruppe"]
        r = self.c.post(f"/api/profile/dungeon/{rid}/wappen", json={"farbe": "purpur", "zeichen": "krone"})
        self.assertEqual(r.status_code, 200, r.text)
        now = r.json()["wappen"]
        self.assertEqual((now["wahl"]["farbe"], now["wahl"]["zeichen"]), ("purpur", "krone"))
        a, b = wappen._parts(before), wappen._parts(now["gruppe"])
        self.assertEqual((b[2], b[4]), ("purpur", "krone"))
        self.assertEqual(a[:2], b[:2])
        self.assertEqual(self.c.post(f"/api/profile/dungeon/{rid}/wappen", json={"farbe": "lila"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/profile/dungeon/{rid}/wappen", json={"zeichen": "<b>"}).status_code, 400)
        self.guest_view(rid)
        with self.assertRaises(LookupError):
            wappen.choose(self.guid, rid, {"farbe": "rot"})                    # a seat that is not the host
        r = self.c.post(f"/api/profile/dungeon/{rid}/wappen", json={"zufall": True})
        self.assertEqual(r.json()["wappen"]["gruppe"], before)                 # back to the start value's arms
        self.assertEqual(wappen._day.counts()["gewaehlt"], 2)
        self.assertEqual(wappen._day.counts()["abgelehnt"], 2)

    def test_a_campaign_keeps_its_arms_and_the_sweep_drops_rounds_that_are_gone(self):
        rid = self.new_round()
        with dungeon._lock:
            d = dungeon._read()
            d["runden"][rid]["kid"] = "kprobe"
            dungeon._write(d)
        wappen.choose(self.uid, rid, {"farbe": "gruen", "zeichen": "baum"})
        code = wappen.gruppe(dungeon._read()["runden"][rid])
        other = {"owner": self.uid, "kid": "kprobe", "made": 99}               # the next chapter: another round
        self.assertEqual(wappen.gruppe(other), code)
        self.assertEqual(wappen._choices(self.uid), {"k:kprobe": {"farbe": "gruen", "zeichen": "baum"}})
        wipe()                                                                  # round and campaign gone
        self.assertEqual(wappen.sweep(10_000.0), 1)
        self.assertEqual(wappen._choices(self.uid), {})

    def test_live_counts_only(self):
        self.new_round()
        live = wappen.for_live()
        self.assertEqual(set(live), {"on", "runden", "gewaehlt", "abgelehnt"})
        self.assertTrue(all(isinstance(v, (bool, int)) for v in live.values()))
        helpers.set_config(dungeon_wappen=False)
        self.assertEqual(wappen.for_live(), {"on": False})

    def test_the_page_shows_arms_only_as_pictures(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "panel", "static", "js", "dungeonwappen.js")) as f:
            js = f.read()
        self.assertNotRegex(js, r"innerHTML\s*=.*svg\[")                        # never the SVG itself into the page
        self.assertTrue(re.search(r"data:image/svg\+xml;charset=utf-8,'\+encodeURIComponent", js))


if __name__ == "__main__":
    unittest.main()
