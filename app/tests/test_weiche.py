"""Funktionen → Weiche (weiche.py): the switch shown and set up in the panel. The admin's rules only ever take out
or keep within the rights (Nicht bei, extra tools only from those offered, groups without narrowing), every change
is checked against all test sentences first, „Rückgängig“ puts the version before back, the counting keeps no word
of a question, and the protection rules are not on the page's list of settings at all. Admin only.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import intent  # noqa: E402
import weiche  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
NOW = 1_800_000_000          # a fixed moment: nothing here reads the clock for its result
CLEAN = dict(route_words="", route_not="", route_extra="", route_off=[], route_tests=[])


def tools(*names):
    return [{"function": {"name": n}} for n in names]


def offered(tool_list):
    return sorted(t["function"]["name"] for t in tool_list)


class Rules(unittest.TestCase):
    def setUp(self):
        helpers.set_config(**CLEAN)

    def test_not_words_only_take_out(self):
        self.assertEqual(intent.classify("Mach die Sauna an", "", "smarthome: sauna").names, ["smarthome"])
        r = intent.classify("Mach die Sauna an", "", "smarthome: sauna", "smarthome: sauna")
        self.assertEqual(r.names, [])
        # a „Nicht bei“ word of another group changes nothing, and never adds a group
        self.assertEqual(intent.classify("Mach das Licht an", "", "", "wetter: licht").names, ["smarthome"])
        self.assertEqual(intent.classify("Hallo Sauna", "", "", "smarthome: sauna").names, [])

    def test_extra_tools_stay_within_the_offer(self):
        route = intent.classify("Mach das Licht an")
        cfg = {"route_extra": "smarthome: weather, web_search"}
        have = tools("home_assistant_action", "weather", "memory_save", "transit")
        self.assertEqual(offered(intent.narrow(route, have, cfg)), ["home_assistant_action", "memory_save", "weather"])
        # not offered this turn (the profile may not search the web): not added
        self.assertNotIn("web_search", offered(intent.narrow(route, have, cfg)))
        self.assertEqual(offered(intent.narrow(route, have)), ["home_assistant_action", "memory_save"])
        for bad in ("smarthome: rm_rf", "tresor: weather", "smarthome weather", "smarthome: " + ", ".join(
                sorted(intent.known_tools())[:7]), 5):
            with self.assertRaises(ValueError, msg=bad):
                intent.parse_route_extra(bad)

    def test_groups_without_narrowing(self):
        route = intent.classify("Mach das Licht an")
        have = tools("home_assistant_action", "weather", "transit")
        self.assertEqual(intent.narrow(route, have, {"route_off": ["smarthome"]}), have)
        self.assertEqual(len(intent.narrow(route, have, {"route_off": ["wetter"]})), 1)
        for bad in ("smarthome", ["tresor"], [1]):
            with self.assertRaises(ValueError):
                intent.parse_route_off(bad)

    def test_test_sentences_checked(self):
        self.assertEqual(weiche.parse_tests([{"q": " Mach die Sauna an ", "want": "smarthome"},
                                             {"q": "mach die sauna an", "want": ""}]),
                         [{"q": "Mach die Sauna an", "want": "smarthome"}])
        for bad in ([{"q": "x" * 201, "want": ""}], [{"q": "a\nb", "want": ""}], [{"q": "Hallo", "want": "tresor"}],
                    [{"q": "Hallo", "want": "Smarthome"}], [{"q": "Hallo", "want": "", "x": 1}], "x",
                    [{"q": f"Satz {i}", "want": ""} for i in range(201)]):
            with self.assertRaises(ValueError):
                weiche.parse_tests(bad)

    def test_bench_green_with_clean_rules(self):
        wrong = [x for x in weiche.run_tests({}) if not x["ok"]]
        self.assertEqual(wrong, [])

    def test_trace_shows_the_whole_way(self):
        ch = dict(CLEAN, route_words="smarthome: sauna", route_extra="smarthome: weather")
        t = weiche.trace("Mach die Sauna an", ch)
        self.assertEqual(t["names"], ["smarthome"])
        self.assertEqual(t["why"][0]["source"], "eigen")
        kinds = {x["name"]: x["kind"] for x in t["tools"]}
        self.assertEqual(kinds["weather"], "zusatz")
        self.assertEqual(kinds["memory_save"], "immer")
        self.assertEqual(kinds["home_assistant_action"], "gruppe")
        import datetime
        w = weiche.trace("Wie wird das Wetter morgen?", CLEAN, datetime.date(2026, 10, 12))
        self.assertEqual((w["direct"], w["date"]), ("weather", "2026-10-13"))
        self.assertEqual(weiche.trace("Hallo", CLEAN)["narrow"], "plaudern")
        self.assertTrue(weiche.trace("Setz das auf die Liste", CLEAN)["refers"])
        off = weiche.trace("Mach das Licht an", dict(CLEAN, route_off=["smarthome"]))
        self.assertEqual((off["narrow"], off["tools"]), ("aus", []))

    def test_suggest_from_the_sentence_only(self):
        words = weiche.suggest("Wie voll ist die Zisterne heute?", "smarthome", {})
        self.assertIn("zisterne", words)
        self.assertNotIn("heute", words)   # a common word
        self.assertNotIn("licht", weiche.suggest("Ist das Licht in der Zisterne an?", "smarthome", {}))   # known already
        self.assertLessEqual(len(weiche.suggest(" ".join(f"Wortlang{c}" for c in "abcdefgh"), "smarthome", {})), 5)

    def test_counting_keeps_no_words(self):
        with weiche._lock:
            weiche._stats.update(days={}, dirty=False, flushed=0.0)
        weiche.count(intent.classify("Mach das Licht im Badezimmer an"), 6, 30, None, now=NOW)
        weiche.count(intent.classify("Wie wird das Wetter?"), 3, 30, "weather", now=NOW)
        weiche.count(intent.classify("Erzähl was über Quasare"), 30, 30, None, now=NOW)
        s = weiche.summary(now=NOW)
        self.assertEqual(s["groups"]["smarthome"]["n"], 1)
        self.assertEqual(s["groups"]["wetter"]["direct"], 1)
        self.assertEqual(s["groups"]["unklar"]["avg"], 30)
        self.assertEqual(s["total"]["n"], 3)
        weiche._flush()
        with open(os.path.join(weiche.STATE, "weiche-stats.json")) as f:
            raw = f.read()
        for word in ("Badezimmer", "Licht", "Quasare"):
            self.assertNotIn(word, raw)
        live = weiche.live_today(now=NOW)
        self.assertEqual((live["n"], live["unklar"]), (3, 1))
        self.assertEqual({g[0] for g in live["top"]}, {"Smart Home", "Wetter"})
        import live
        with open(os.environ["SPEECH_SPARK_CONFIG"]) as f:
            cfg = json.load(f)
        cfg["logs"]["live"] = True
        helpers.write_config(cfg)
        try:
            self.assertEqual(ADMIN.get("/api/admin/live").json()["weiche"]["n"], live._weiche_today()["n"])
        finally:
            cfg["logs"]["live"] = False
            helpers.write_config(cfg)
        # older than 8 days: gone
        weiche.count(intent.classify("Hallo"), 0, 0, None, now=NOW + 9 * 86400)
        self.assertNotIn(weiche._day(NOW), weiche._stats["days"])


class Page(unittest.TestCase):
    def setUp(self):
        helpers.set_config(**CLEAN)
        try:
            os.remove(os.path.join(weiche.STATE, "weiche-history.json"))
        except FileNotFoundError:
            pass

    def test_page(self):
        d = ADMIN.get("/api/admin/weiche").json()
        self.assertEqual({g["name"] for g in d["groups"]}, set(intent.GROUPS))
        self.assertEqual(d["tests"]["builtin"], d["tests"]["builtin_ok"])
        self.assertEqual({x["k"] for x in d["locks"]}, {"mail", "outside", "lookups", "notaus"})
        self.assertTrue(set(d["known"]) <= set(d["tools"]), set(d["known"]) - set(d["tools"]))
        t = ADMIN.post("/api/admin/weiche/test", json={"text": "Mach die Sauna an",
                                                       "rules": {"route_words": "smarthome: sauna"}}).json()
        self.assertEqual(t["names"], ["smarthome"])
        # trying with rules being edited saves nothing
        self.assertEqual(ADMIN.get("/api/admin/weiche").json()["rules"]["route_words"], "")
        for bad in ({"text": ""}, {"text": "x" * 501}, {"text": "Licht an", "rules": {"route_extra": "x: y"}},
                    {"text": "Licht an", "rules": {"answer_check": False}}):
            self.assertEqual(ADMIN.post("/api/admin/weiche/test", json=bad).status_code, 400, bad)

    def test_save_check_and_undo(self):
        r = ADMIN.put("/api/admin/weiche", json={"rules": {"route_words": "smarthome: sauna",
                                                           "route_tests": [{"q": "Mach die Sauna an", "want": "smarthome"}]}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tests"]["own"][0]["ok"], True)
        # a word that turns a built-in sentence around: stopped, shown, saved only when confirmed
        change = {"rules": {"route_not": "wetter: wetter"}}
        self.assertTrue(ADMIN.post("/api/admin/weiche/check", json=change).json()["count"] > 0)
        r = ADMIN.put("/api/admin/weiche", json=change)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(ADMIN.get("/api/admin/weiche").json()["rules"]["route_not"], "")
        r = ADMIN.put("/api/admin/weiche", json=dict(change, confirm=True))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rules"]["route_not"], "wetter: wetter")
        r = ADMIN.post("/api/admin/weiche/undo")
        self.assertEqual(r.json()["rules"]["route_not"], "")
        self.assertEqual(r.json()["rules"]["route_words"], "smarthome: sauna")
        ADMIN.post("/api/admin/weiche/undo")
        self.assertEqual(ADMIN.post("/api/admin/weiche/undo").status_code, 404)
        self.assertEqual(ADMIN.get("/api/admin/weiche").json()["rules"]["route_words"], "")

    def test_settings_form_keeps_the_rules(self):
        cfg = ADMIN.get("/api/config").json()   # the form, loaded before the Weiche page saved
        ADMIN.put("/api/admin/weiche", json={"rules": {"route_words": "smarthome: kamin"}})
        cfg["chat"]["answer_check"] = not cfg["chat"].get("answer_check", True)
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 200)
        self.assertEqual(ADMIN.get("/api/config").json()["chat"]["route_words"], "smarthome: kamin")
        # an invalid rule is still refused there (restore, old forms)
        bad = ADMIN.get("/api/config").json()
        bad["chat"]["route_extra"] = "smarthome: rm"
        self.assertEqual(ADMIN.put("/api/config", json=bad).status_code, 400)

    def test_bad_saves(self):
        for bad in ({"rules": {"route_words": "tresor: auf"}}, {"rules": {"route_off": "smarthome"}},
                    {"rules": {"route_tests": [{"q": "", "want": ""}]}}, {"rules": {"llm_url": "http://x"}},
                    {"rules": []}, [], {"rules": {"route_words": 5}}):
            self.assertEqual(ADMIN.put("/api/admin/weiche", json=bad).status_code, 400, bad)
        self.assertEqual(ADMIN.put("/api/admin/weiche", content=b"x" * (weiche.MAX_BODY + 1)).status_code, 413)

    def test_suggest_saves_nothing(self):
        r = ADMIN.post("/api/admin/weiche/suggest", json={"text": "Wie voll ist die Zisterne?", "want": "smarthome"})
        d = r.json()
        self.assertEqual(d["now"], "unklar")
        w = next(x for x in d["words"] if x["word"] == "zisterne")
        self.assertTrue(w["ok"])
        self.assertEqual(ADMIN.get("/api/admin/weiche").json()["rules"]["route_words"], "")
        for bad in ({"text": "x", "want": "tresor"}, {"text": "", "want": "smarthome"}, {"text": "x" * 201, "want": "wetter"}):
            self.assertEqual(ADMIN.post("/api/admin/weiche/suggest", json=bad).status_code, 400)

    def test_admin_only(self):
        helpers.set_config(public=True)
        try:
            p = ADMIN.post("/api/admin/profiles", json={"name": "Weiche7", "pin": "1234"})
            self.assertIn(p.status_code, (200, 409))
            prof = TestClient(panel.app)
            prof.post("/api/profile/login", json={"name": "Weiche7", "pin": "1234"})
            for c in (prof, TestClient(panel.app)):
                self.assertIn(c.get("/api/admin/weiche").status_code, (401, 403))
                for path in ("test", "check", "suggest", "undo"):
                    self.assertIn(c.post("/api/admin/weiche/" + path, json={"text": "Licht an"}).status_code, (401, 403))
                self.assertIn(c.put("/api/admin/weiche", json={"rules": {}}).status_code, (401, 403))
        finally:
            helpers.set_config(public=False)

    def test_protection_rules_are_not_settings(self):
        # the page sets only these keys; the locks, the Notaus and the lookup limit are none of them
        self.assertEqual(set(weiche.KEYS), {"route_words", "route_not", "route_extra", "route_off", "route_tests"})
        with open(os.path.join(os.path.dirname(panel.__file__), "..", "config.default.json")) as f:
            chat_defaults = json.load(f)["chat"]
        for k in weiche.KEYS:
            self.assertIn(k, chat_defaults)
            self.assertFalse(chat_defaults[k])   # new rules start empty


if __name__ == "__main__":
    unittest.main()
