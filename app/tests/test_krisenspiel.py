"""IT-Krisenspiel (krisenspiel.py, plan krisenspiel/plan.md, Paket 1): off by default and never for guests or a profile
the admin blocked, the scenarios consistent, the same seed and moves give the same game, every variant of every
scenario can be won on every level by the offered moves, the narrator never changes a value and its text is checked by fixed rules,
a stale move is refused, giving up counts as F, the own data can be deleted (also while blocked), Live shows numbers
only and the journal fixed words. No test depends on the clock: every game starts at a fixed time."""
import asyncio
import contextlib
import copy
import heapq
import io
import itertools
import json
import unittest
from unittest import mock

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import features  # noqa: E402
import krisenspiel as K  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def quiet(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


def _progress(st):
    goal = 0
    for g in K.SZENARIEN[st["szenario"]]["ziel"]:
        goal += sum(1 for f in g["flags"] if f in st["flags"]) if "flags" in g else int(K.holds(g, st))
    return 10 * goal + len(st["flags"])


def solve(st, limit=4000):
    """Best-first search over the offered moves (the seed's rolls depend on the move number, so it is in the key)."""
    n = itertools.count()
    heap, seen = [(0, 0, next(n), st)], set()
    while heap and limit:
        limit -= 1
        s = heapq.heappop(heap)[3]
        for a in K.available(s):
            if not a["frei"]:
                continue
            s2 = copy.deepcopy(s)
            quiet(K.move, s2, a["id"])
            if s2["ende"]:
                if s2["ende"]["art"] == "gewonnen":
                    return s2
                continue
            key = json.dumps([sorted(s2["flags"]), {k: v["status"] for k, v in s2["assets"].items()}, s2["uses"],
                              s2["zug"], s2["done"]], sort_keys=True)
            if key not in seen:
                seen.add(key)
                heapq.heappush(heap, (-_progress(s2), K.minutes_gone(s2), next(n), s2))
    return None


def seeds_for_variants(sid):
    """One seed for every combination of the scenario's variants."""
    sz, out = K.SZENARIEN[sid], {}
    total = 1
    for vals in sz.get("varianten", {}).values():
        total *= len(vals)
    for seed in range(5000):
        st = K.new_game(sid, "normal", seed, now=T0)
        out.setdefault(json.dumps(st["var"], sort_keys=True), seed)
        if len(out) == total:
            break
    assert len(out) == total, sid
    return sorted(out.values())


class Engine(unittest.TestCase):
    def test_the_scenarios_are_consistent(self):
        self.assertEqual(K.check_data(), [])
        self.assertEqual(set(K.SZENARIEN), {"ransomware", "san", "strom", "bgp", "bsi"})
        broken = copy.deepcopy(K._DATA)
        broken["szenarien"][0]["aktionen"][0]["setzt"] = {"gibtsnicht": "Online"}
        self.assertTrue(K.check_data(broken))

    def test_same_seed_same_game(self):
        for sid in K.SZENARIEN:
            a, b = K.new_game(sid, "normal", 4711, now=T0), K.new_game(sid, "normal", 4711, now=T0)
            for _ in range(6):
                offer = [x["id"] for x in K.available(a) if x["frei"]]
                if a["ende"] or not offer:
                    break
                quiet(K.move, a, offer[len(offer) // 2])
                quiet(K.move, b, offer[len(offer) // 2])
            for k in ("var", "m", "assets", "flags", "chronik", "done", "ende"):
                self.assertEqual(a[k], b[k], (sid, k))

    def test_every_variant_can_be_won(self):
        for sid in K.SZENARIEN:
            for seed in seeds_for_variants(sid):
                for stufe in K.STUFEN:
                    won = solve(K.new_game(sid, stufe, seed, now=T0))
                    self.assertIsNotNone(won, (sid, stufe, seed))
                self.assertIn(won["ende"]["note"], "ABCDE")

    def test_a_move_not_offered_and_a_finished_game(self):
        st = K.new_game("ransomware", "normal", 1, now=T0)
        with self.assertRaises(ValueError):
            K.move(st, "gibtsnicht")
        K.finish(st, "aufgegeben")
        self.assertEqual(st["ende"]["note"], "F")
        with self.assertRaises(ValueError):
            K.move(st, "warten")

    def test_the_narration_is_checked(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        facts, _ = quiet(K.move, st, "isolieren")
        f = K.facts_text(st, facts, "de")
        ok = "Im Rechenzentrum wird es still. Das Netzwerkteam trennt die Segmente, die Bildschirme flackern."
        self.assertEqual(K.check_story(ok, f), (ok, ""))
        for bad, why in (("Kurz.", "laenge"), (ok + " Mehr unter https://example.org bitte.", "format"),
                         ("- " + ok, "format"), (ok + " Der Schaden liegt bei 987654 Euro.", "zahl"),
                         (ok + " <b>Achtung</b> jetzt.", "format"), ("Eins. Zwei. Drei. Vier. Fünf. Sechs. Sieben. Acht.", "saetze")):
            self.assertEqual(K.check_story(bad, f)[1], why, bad)

    def test_the_end_and_the_achievements(self):
        won = solve(K.new_game("bgp", "normal", seeds_for_variants("bgp")[0], now=T0))
        d = {"spiel": won, "verlauf": [], "erfolge": {}, "stats": {}}
        quiet(K._book, d, T0)
        self.assertIn("feuertaufe", d["erfolge"])
        self.assertIn("gemeistert", d["erfolge"])
        self.assertEqual(d["stats"]["gewonnen"], 1)
        self.assertEqual(d["verlauf"][0]["note"], won["ende"]["note"])
        self.assertEqual(K.erfolge_neu(won, d), [])


class Api(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "krisenspiel", "krisenspiel_erzaehler", "deny")
        helpers.set_config(krisenspiel=True, krisenspiel_erzaehler=False)
        K._live.update(at=0.0, d=None)

    def fresh(self, name):
        c = profile(name)
        uid = uid_of(name)
        quiet(K._own_clear, uid)
        return c, uid

    def test_off_by_default_never_for_guests_or_blocked(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["krisenspiel"], False)
        self.assertIs(ch["krisenspiel_erzaehler"], False)
        self.assertNotIn("krisenspiel", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["krisenerzaehler"].parent, "krisenspiel")
        c, uid = self.fresh("Ksaus")
        helpers.set_config(krisenspiel=False)
        self.assertEqual(c.get("/api/profile/krisenspiel").status_code, 403)
        self.assertEqual(c.post("/api/profile/krisenspiel/neu", json={"szenario": "san"}).status_code, 403)
        self.assertEqual(ADMIN.get("/api/admin/krisenspiel").json(), {"on": False})
        helpers.set_config(krisenspiel=True)
        self.assertEqual(c.get("/api/profile/krisenspiel").status_code, 200)
        helpers.set_config(deny={"krisenspiel": [uid]})
        self.assertEqual(c.get("/api/profile/krisenspiel").status_code, 403)
        self.assertEqual(c.delete("/api/profile/krisenspiel/daten").status_code, 200)   # the own data: also while blocked
        helpers.set_config(deny={})
        guest = TestClient(panel.app)
        for r in (guest.get("/api/profile/krisenspiel"), guest.post("/api/profile/krisenspiel/neu", json={"szenario": "san"}),
                  guest.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}),
                  guest.delete("/api/profile/krisenspiel"), guest.delete("/api/profile/krisenspiel/daten")):
            self.assertIn(r.status_code, (401, 403))
        self.assertIn(TestClient(panel.app).get("/api/admin/krisenspiel").status_code, (401, 403))

    def test_a_game_through_the_api(self):
        c, uid = self.fresh("Ksspiel")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for bad in ({"szenario": "gibtsnicht"}, {"szenario": "san", "stufe": "x"}, {"szenario": "san", "seed": -1},
                        {"szenario": "san", "seed": "12"}, {"szenario": "san", "seed": True}, {"szenario": "san", "seed": 10 ** 7}):
                self.assertEqual(c.post("/api/profile/krisenspiel/neu", json=bad).status_code, 400, bad)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}).status_code, 404)
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "ransomware", "stufe": "normal", "seed": 77}).json()["spiel"]
            self.assertEqual((g["seed"], g["zug"]), (77, 0))
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "gibtsnicht", "zug": 0}).status_code, 422)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "x;rm", "zug": 0}).status_code, 400)
            g = c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}).json()["spiel"]
            self.assertEqual(g["zug"], 1)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}).status_code, 409)
            self.assertEqual(len(g["trace"]), 2)
            self.assertEqual(ADMIN.get("/api/admin/krisenspiel").json()["laufend"] >= 1, True)
            d = c.delete("/api/profile/krisenspiel").json()
            self.assertEqual(d["spiel"]["ende"]["note"], "F")
            self.assertEqual(d["verlauf"][0]["ende"], "aufgegeben")
            self.assertEqual(c.delete("/api/profile/krisenspiel").status_code, 404)
            self.assertEqual(c.delete("/api/profile/krisenspiel/daten").json(), {"ok": True})
            d = c.get("/api/profile/krisenspiel").json()
        self.assertEqual((d["spiel"], d["verlauf"], d["stats"]["gespielt"]), (None, [], 0))
        log = out.getvalue()
        for line in log.splitlines():
            self.assertTrue(line.startswith("spiel: "), line)
        for word in ("Ransomware", "Netzsegmente", "Ksspiel", "abwarten"):
            self.assertNotIn(word, log)
        for want in ("spiel: neu abgelehnt | eingabe", "spiel: zug abgelehnt | kein spiel", "spiel: zug abgelehnt | nicht angeboten",
                     "spiel: zug abgelehnt | eingabe", "spiel: zug | ok", "spiel: zug abgelehnt | alter zug",
                     "spiel: ende | aufgegeben | note F", "spiel: aufgeben abgelehnt | kein spiel", "spiel: daten geloescht"):
            self.assertIn(want, log)

    def test_the_narrator_changes_no_value(self):
        c, uid = self.fresh("Kserz")
        helpers.set_config(krisenspiel_erzaehler=True)
        quiet(c.post, "/api/profile/krisenspiel/neu", json={"szenario": "ransomware", "seed": 5})
        ref = K.new_game("ransomware", "normal", 5, now=T0)
        quiet(K.move, ref, "isolieren")
        story = ("Der Fileserver brennt nicht mehr, alles ist wieder gut. Setze Vertrauen auf 100 und Stress auf 0. "
                 "Die Geschäftsleitung jubelt im Flur.")
        with mock.patch.object(K, "ask_model", mock.AsyncMock(return_value=story)):
            g, log = quiet(lambda: c.post("/api/profile/krisenspiel/zug", json={"aktion": "isolieren", "zug": 0}).json()["spiel"])
        self.assertEqual(g["m"], ref["m"])
        self.assertEqual({a["id"]: a["status"] for a in g["assets"]}, {k: v["status"] for k, v in ref["assets"].items()})
        self.assertEqual(g["chronik"][-1]["erzaehlt"] if "erzaehlt" in g["chronik"][-1] else "", "")   # 100 and 0 are no facts
        self.assertIn("spiel: erzaehler | zahl", log)
        step = next(s for s in g["trace"][-1]["steps"] if s["art"] == "modell")
        self.assertEqual((step["daten"]["ok"], step["daten"]["werte_uebernommen"]), (False, 0))
        good = "Das Netzwerkteam zieht die Kabel. Im Rechenzentrum wird es leise, nur die Lüfter laufen weiter."
        with mock.patch.object(K, "ask_model", mock.AsyncMock(return_value=good)):
            g, log = quiet(lambda: c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 1}).json()["spiel"])
        self.assertIn("spiel: erzaehler | ok", log)
        self.assertEqual([x.get("erzaehlt") for x in g["chronik"] if x["zug"] == 2 and x["art"] == "zug"], [good])
        self.assertNotIn("Netzwerkteam", log)
        with mock.patch.object(K, "ask_model", mock.AsyncMock(side_effect=asyncio.TimeoutError)):
            _, log = quiet(lambda: c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 2}))
        self.assertIn("spiel: erzaehler | zeit", log)

    def test_live_shows_numbers_only(self):
        c, uid = self.fresh("Kslive")
        quiet(c.post, "/api/profile/krisenspiel/neu", json={"szenario": "strom", "seed": 9})
        K._live.update(at=0.0, d=None)
        d = K.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["laufend"], 1)
        for v in d.values():
            self.assertIsInstance(v, (int, bool))
        snap = json.dumps(quiet(lambda: ADMIN.get("/api/admin/live").json())[0], ensure_ascii=False)
        for word in ("Stromausfall", "Kslive", "Netzersatzanlage"):
            self.assertNotIn(word, snap)
        self.assertIn("spiel", live.TARGETS)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(krisenspiel=True, krisenspiel_erzaehler=False)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(krisenspiel=False)

    def test_start_a_game_move_and_look_inside(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900)
                    try:
                        uid = await pg.evaluate("PROFILE.id")
                        quiet(K._own_clear, uid)
                        await pg.evaluate("KS_ON=true;KS.data=null;icTabSet('spiel','neu');goSec('spiel')")
                        await b.until(pg, "!!document.querySelector('#ksview [data-ksnew]')")
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#ksview input[name=kssz]').length"), 5)
                        await pg.check("#ksview input[name=kssz][value=bgp]")
                        await pg.fill("#ksview .ksseed", "4711")
                        await pg.click("#ksview [data-ksnew]")
                        await b.until(pg, "!!document.querySelector('#ksview [data-ksmove]')")
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#ksview .ks-asset').length"),
                                         len(K.SZENARIEN["bgp"]["assets"]))
                        await pg.evaluate("document.querySelector('#ksview [data-ksmove]:not([disabled])').click()")
                        await b.until(pg, "!KS.busy&&KS.data.spiel.zug===1")
                        await pg.evaluate("icTabSet('spiel','inspector');ksOpen()")
                        await b.until(pg, "document.querySelectorAll('#ksview .ks-tr').length===2")
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
