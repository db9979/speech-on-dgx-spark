"""Weiche intelligenter (plan weiche-intelligenter.md): the everyday check, hint words, follow-up questions and the
Weiche's settings in one place.

- intent_alltag.ALLTAG: sentences nobody tuned the rules for; right + kept by a hint may not go down, wrong not up.
- Hint words never narrow: they only keep their group's tools with "lean" and beside a model's pick, and only tools
  the turn offers anyway (rights and locks stay where they are).
- A follow-up („Und morgen?“) takes the group of the person's own question just before, only when it points back,
  is short and no rule recognizes it; an answer or outside text never counts.
- The must words, what unclear questions get and the classification's threshold are set on Funktionen → Weiche only;
  the settings form cannot put an older copy back.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import re
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
import intent  # noqa: E402
import intent_alltag  # noqa: E402
import weiche  # noqa: E402
import guard  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
STATIC = os.path.join(os.path.dirname(panel.__file__), "static")

# measured when the hint words came (14.10.2026, 183 sentences) and after the third batch (16.10.2026, 211):
# raise these when the rules get better, never lower
MIN_GOOD = 210      # right + kept by a hint
MAX_WRONG = 0


def tool(name):
    return {"type": "function", "function": {"name": name}}


def names(tools):
    return {t["function"]["name"] for t in tools}


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def streamed():
    return [c for c in helpers.LLM_CALLS if c.get("stream")]


class Everyday(unittest.TestCase):
    def test_score_does_not_go_down(self):
        m = intent_alltag.measure(intent.classify)
        self.assertEqual(m["n"], len(intent_alltag.ALLTAG))
        bad = [f"{r['q']!r}: {r['got'] or 'unklar'} (erwartet {r['want'] or 'unklar'})" for r in m["rows"]
               if r["kind"] in ("falsch", "offen")]
        self.assertGreaterEqual(m["richtig"] + m["geschuetzt"], MIN_GOOD, "\n".join(bad))
        self.assertLessEqual(m["falsch"], MAX_WRONG, "\n".join(bad))

    def test_tools_by_word_are_the_kept_ones(self):
        # „@tool“ sentences measure a tool the Weiche keeps by the person's own word (werkzeug_abdeckung.BY_WORD)
        import werkzeug_abdeckung as wa
        tools = {w[1:] for _, want in intent_alltag.ALLTAG for w in want.split("+") if w.startswith("@")}
        self.assertTrue(tools)
        self.assertEqual(sorted(tools - set(wa.BY_WORD)), [])
        self.assertTrue(intent_alltag.byword("speaker_volume", "Mach leiser"))
        self.assertFalse(intent_alltag.byword("speaker_volume", "Mach das Licht aus"))
        m = intent_alltag.measure(intent.classify, [("Mach leiser", "@speaker_volume"), ("Mach das Licht aus", "@undo_last"),
                                                    ("Leg das auf die NAS", "dokument+@nas_ablegen")])
        self.assertEqual((m["richtig"], m["offen"], m["falsch"]), (1, 1, 1), m["rows"])

    def test_the_lists_are_apart(self):
        # an everyday sentence measures; it never doubles as a tuned test sentence
        from intent_bench import BENCH
        bench = {q.lower() for q, _ in BENCH}
        self.assertFalse([q for q, _ in intent_alltag.ALLTAG if q.lower() in bench])
        for q, want in intent_alltag.ALLTAG:
            for n in intent_alltag._groups(want):
                self.assertIn(n, intent.GROUPS, q)

    def test_measure_sorts_the_kinds(self):
        rows = [("Mach das Licht im Flur an", "smarthome"), ("Wir brauchen Milch", "liste"),
                ("Erzähl einen Witz", ""), ("Erzähl einen Witz", "liste"), ("Mach das Licht an", "wetter")]
        m = intent_alltag.measure(intent.classify, rows)
        self.assertEqual((m["richtig"], m["geschuetzt"], m["offen"], m["falsch"]), (2, 1, 1, 1))


class Hints(unittest.TestCase):
    def test_hints_only_when_no_rule_is_sure(self):
        r = intent.classify("Wir brauchen Milch")
        self.assertEqual(r.names, [])
        self.assertIn("liste", r.hints)
        self.assertEqual(intent.classify("Setz Milch auf die Einkaufsliste").hints, {})
        self.assertEqual(intent.classify("").hints, {})

    def test_a_hint_never_narrows(self):
        tools = [tool(n) for n in ("weather", "tasks_add", "tasks_show", "web_search", "memory_save", "calendar_events")]
        r = intent.classify("Wir brauchen Milch")
        self.assertFalse(r.clear)
        self.assertEqual(intent.narrow(r, tools), tools)          # unclear: every tool as before
        self.assertIsNone(intent.forced(r, ["tasks_add"], names(tools)))

    def test_lean_keeps_the_hinted_tools_and_only_offered_ones(self):
        tools = [tool(n) for n in ("weather", "tasks_add", "tasks_show", "web_search", "memory_save", "calendar_events")]
        lean = names(intent.lean(intent.classify("Wir brauchen Milch"), tools))
        self.assertTrue({"tasks_add", "tasks_show", "web_search", "memory_save"} <= lean)
        self.assertNotIn("weather", lean)
        self.assertNotIn("calendar_events", lean)
        # a hinted group whose tools are not offered (rights, locks) gets none
        self.assertEqual(names(intent.lean(intent.classify("Wir brauchen Milch"), [tool("web_search")])), {"web_search"})
        # no hint: the short list as before
        self.assertEqual(names(intent.lean(intent.classify("Erzähl einen Witz"), tools)), {"web_search", "memory_save"})

    def test_hints_stay_beside_a_model_pick(self):
        tools = [tool(n) for n in ("weather", "tasks_add", "tasks_show", "web_search", "memory_save", "calendar_events",
                                   "mail_list")]
        r = intent.classify("Wir brauchen Milch")
        picked = intent.Route(["mail"], {"mail": "Modell"}, r.hints)
        got = names(intent.narrow(picked, tools))
        self.assertTrue({"mail_list", "tasks_add", "tasks_show", "memory_save"} <= got)
        self.assertNotIn("weather", got)

    def test_language_and_nature_questions_are_knowledge(self):
        for q in ("Was heißt Fenster auf Englisch?", "Wie lange braucht Licht von der Sonne zur Erde?",
                  "Was bedeutet das Wort Melancholie?"):
            self.assertEqual(intent.classify(q).names, [], q)
        self.assertEqual(intent.classify("Mach das Licht im Flur an").names, ["smarthome"])

    def test_a_file_wish_is_the_file(self):
        self.assertEqual(intent.classify("Schreib eine Kündigung für mein Fitnessstudio").names, ["erstellen"])
        self.assertEqual(intent.classify("Was steht in meinem Mietvertrag zur Kündigung?").names, ["dokument"])
        self.assertEqual(intent.classify("Schick mir jeden Morgen um sieben die Schlagzeilen").names, ["agent"])
        self.assertEqual(intent.classify("Erinnere mich jeden Montag an den Müll").names, ["erinnerung"])


class FollowUp(unittest.TestCase):
    def test_takes_the_group_before(self):
        r = intent.follow_up("Und morgen?", "Wie wird das Wetter heute?")
        self.assertEqual(r.names, ["wetter"])
        self.assertEqual(r.why, {"wetter": "Folgefrage"})
        self.assertEqual(intent.follow_up("Mach es wieder aus", "Mach das Licht im Flur an").names, ["smarthome"])

    def test_only_when_it_points_back_and_nothing_else_fits(self):
        self.assertIsNone(intent.follow_up("Erzähl einen Witz", "Wie wird das Wetter heute?"))      # no pointing back
        self.assertIsNone(intent.follow_up("Und morgen?", "Erzähl einen Witz"))                    # nothing before
        self.assertIsNone(intent.follow_up("Und morgen?", "Danke"))                                # small talk before
        self.assertIsNone(intent.follow_up("Und morgen?", ""))
        self.assertIsNone(intent.follow_up("Und " + "x " * 60, "Wie wird das Wetter heute?"))     # too long
        # the new question has its own group: that one counts (classify, not follow_up)
        self.assertIsNone(intent.follow_up("Und die Termine?", "Wie wird das Wetter heute?"))

    def test_in_a_turn_only_the_persons_own_question_counts(self):
        helpers.set_config(routing=True, route_model="off")
        try:
            p = profile("Folge1")
            helpers.LLM_CALLS.clear()
            r = p.post("/api/chat", json={"messages": [
                {"role": "user", "content": "Erinnere mich in 10 Minuten an den Herd"},
                {"role": "assistant", "content": "Mach ich."},
                {"role": "user", "content": "Und in 20 Minuten an den Müll"}]})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(names(streamed()[0]["tools"]), {"memory_save", "reminder_set", "reminder_list",
                                                              "reminder_cancel"})
            # an answer before (not the person's words) never makes a follow-up
            helpers.LLM_CALLS.clear()
            r = p.post("/api/chat", json={"messages": [
                {"role": "assistant", "content": "Erinnere mich in 10 Minuten an den Herd"},
                {"role": "user", "content": "Und in 20 Minuten an den Müll"}]})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("history_search", names(streamed()[0]["tools"]))
        finally:
            helpers.set_config(routing=False, route_model="off")

    def test_lean_turn_keeps_the_hinted_group(self):
        helpers.set_config(routing=True, route_model="lean")
        try:
            p = profile("Folge2")
            helpers.LLM_CALLS.clear()
            r = p.post("/api/chat", json={"messages": [{"role": "user", "content": "Was ist in 20 Minuten?"}]})
            self.assertEqual(r.status_code, 200, r.text)
            got = names(streamed()[0]["tools"])
            self.assertTrue({"reminder_set", "reminder_list"} <= got, got)
            self.assertNotIn("calendar_add", got)
        finally:
            helpers.set_config(routing=False, route_model="off")


def _fresh_saves():
    # the saves here count against the admin's per-minute limit; leave it as found for test_weiche
    for k in [k for k in guard._rate if k[0] == "weichesave"]:
        guard._rate.pop(k, None)


class OnePlace(unittest.TestCase):
    def setUp(self):
        _fresh_saves()

    def tearDown(self):
        helpers.set_config(tool_words="", route_model="off", systemone_min=0.8)
        _fresh_saves()

    def test_the_moved_settings_are_only_on_the_weiche_page(self):
        with open(os.path.join(STATIC, "index.html")) as f:
            html = f.read()
        for gone in ('id="chat.tool_words"', 'id="chat.route_model"', 'id="chat.systemone_min"'):
            self.assertNotIn(gone, html)
        self.assertEqual(html.count('id="s1bench"'), 1)
        route = html[html.index('<section id="route">'):html.index("</section>", html.index('<section id="route">'))]
        self.assertIn('id="s1bench"', route)
        self.assertIn('id="whunclear"', route)
        self.assertIn('id="whmust"', route)

    def test_saved_on_the_page_and_the_form_cannot_put_them_back(self):
        d = ADMIN.get("/api/admin/weiche").json()
        self.assertEqual(d["limits"]["must"], chat.MAX_TOOL_WORDS_CHARS)
        rules = dict(d["rules"], tool_words="web_search: elfmeter", route_model="lean", systemone_min=0.7)
        r = ADMIN.put("/api/admin/weiche", json={"rules": rules, "confirm": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["rules"]["route_model"], "lean")
        # the settings form with an older copy keeps what the page saved
        cfg = ADMIN.get("/api/config").json()
        cfg["chat"].update(tool_words="", route_model="off", systemone_min=0.8)
        self.assertEqual(ADMIN.put("/api/config", json=cfg).status_code, 200)
        ch = ADMIN.get("/api/config").json()["chat"]
        self.assertEqual((ch["tool_words"], ch["route_model"], ch["systemone_min"]), ("web_search: elfmeter", "lean", 0.7))
        # „Rückgängig“ puts the version before back
        self.assertEqual(ADMIN.post("/api/admin/weiche/undo").status_code, 200)
        self.assertEqual(ADMIN.get("/api/config").json()["chat"]["route_model"], d["rules"]["route_model"])

    def test_bad_values_are_refused(self):
        d = ADMIN.get("/api/admin/weiche").json()
        for k, bad in (("route_model", "immer"), ("systemone_min", 0.5), ("systemone_min", True),
                       ("tool_words", "web_search: a.*b"), ("tool_words", ["x"])):
            r = ADMIN.put("/api/admin/weiche", json={"rules": dict(d["rules"], **{k: bad}), "confirm": True})
            self.assertEqual(r.status_code, 400, (k, bad))

    def test_page_shows_the_score_and_the_hints(self):
        d = ADMIN.get("/api/admin/weiche").json()
        self.assertEqual(d["alltag"]["n"], len(intent_alltag.ALLTAG))
        self.assertGreaterEqual(d["alltag"]["richtig"] + d["alltag"]["geschuetzt"], MIN_GOOD)
        liste = next(g for g in d["groups"] if g["name"] == "liste")
        self.assertTrue(liste["hints"])
        t = ADMIN.post("/api/admin/weiche/test", json={"text": "Und morgen?", "before": "Wie wird das Wetter heute?"}).json()
        self.assertEqual(t["names"], ["wetter"])
        self.assertTrue(t["follow"])
        t = ADMIN.post("/api/admin/weiche/test", json={"text": "Wir brauchen Milch"}).json()
        self.assertEqual(t["names"], [])
        self.assertEqual([h["group"] for h in t["hints"]][:1], ["liste"])
        self.assertEqual(ADMIN.post("/api/admin/weiche/test", json={"text": "x", "before": "y" * 600}).status_code, 400)
        self.assertIn(TestClient(panel.app).get("/api/admin/weiche").status_code, (401, 403))

    def test_hints_are_fixed_words(self):
        for name, rx in intent.HINTS.items():
            self.assertIn(name, intent.GROUPS)
            self.assertTrue(rx.flags & re.IGNORECASE)
        self.assertTrue(json.dumps(weiche.MODELS))


if __name__ == "__main__":
    unittest.main()


class Learn(unittest.TestCase):
    """Lernen (plan weiche-intelligenter 3/5): only the group of the first tool of an unclear question and the fixed
    hint word that named it are kept, never a word of the question; the admin takes a word over, the panel never."""
    def setUp(self):
        with weiche._lock:
            self.saved = json.loads(json.dumps(weiche._days()))
            for day in weiche._days().values():
                if isinstance(day, dict):
                    day.pop("lernen", None)

    def tearDown(self):
        with weiche._lock:
            weiche._stats["days"] = self.saved
            weiche._stats["dirty"] = True
            weiche._flush()

    def test_counts_only_the_group_and_the_fixed_hint_word(self):
        route = intent.classify("Wir brauchen Hafermilch für Svenja")
        self.assertEqual(route.names, [])
        self.assertEqual(weiche.learn(route, "tasks_add"), "liste")
        stored = json.dumps(weiche._days(), ensure_ascii=False).lower()
        self.assertIn("brauchen", stored)
        for word in ("hafermilch", "svenja"):
            self.assertNotIn(word, stored)
        # a rule (or the model's pick) named the group: nothing to learn
        self.assertIsNone(weiche.learn(intent.classify("Setz Milch auf die Einkaufsliste"), "tasks_add"))
        self.assertIsNone(weiche.learn(intent.Route(["liste"], {"liste": "Modell"}), "tasks_add"))
        # a tool of several groups says nothing about the group; a hint of several words is not kept
        self.assertIsNone(weiche.learn(intent.Route([], {}, {"mail": "post"}), "mail_list"))
        self.assertEqual(weiche.learn(intent.Route([], {}, {"liste": "kein kaffee mehr"}), "tasks_add"), "liste")
        self.assertNotIn("kaffee", json.dumps(weiche._days(), ensure_ascii=False).lower())

    def test_a_word_is_offered_after_some_turns_and_only_until_taken(self):
        for _ in range(weiche.LEARN_MIN - 1):
            weiche.learn(intent.Route([], {}, {"liste": "brauchen"}), "tasks_add")
        row = next(r for r in weiche.learned({})["rows"] if r["group"] == "liste")
        self.assertEqual(row["offer"], [])
        weiche.learn(intent.Route([], {}, {"liste": "brauchen"}), "tasks_add")
        row = next(r for r in weiche.learned({})["rows"] if r["group"] == "liste")
        self.assertEqual(row["offer"], [{"word": "brauchen", "n": weiche.LEARN_MIN}])
        self.assertEqual(row["n"], weiche.LEARN_MIN)
        row = next(r for r in weiche.learned({"route_words": "liste: brauchen"})["rows"] if r["group"] == "liste")
        self.assertEqual(row["offer"], [])
        # the page shows it; taking it over is the normal save with the check of all test sentences (whChange)
        self.assertIn("lernen", ADMIN.get("/api/admin/weiche").json())

    def test_a_chat_turn_learns_from_the_first_tool(self):
        p = profile("Lernen1")
        r = p.post("/api/chat", json={"messages": [{"role": "user", "content": "TOOL reminder_list"}]})
        self.assertEqual(r.status_code, 200, r.text)
        row = next((r for r in weiche.learned({})["rows"] if r["group"] == "erinnerung"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["offer"], [])
