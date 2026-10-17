"""Das kannst du auch sagen (saetze.py, plan plaene/funktionen-zeigen.md, Dominik 2026-10-16 „1-10 umsetzen“): the
panel's fixed sentences for functions that are on but never used.

Off by default and never for guests, after outside text, under the Notaus or over MCP. The sentences are fixed and each
one reaches its tool through the Weiche (werkzeug_abdeckung.SENTENCES, FOLLOW), a „Meintest du …?“ word never does and
its sentence does. Only tools the profile never used come, one row per answer, six a day, the same tool again after 14
days at the earliest, at a speaker one sentence a day. Counted are tool names and numbers, never a question. No test
depends on the wall clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import json
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import features  # noqa: E402
import intent  # noqa: E402
import notaus  # noqa: E402
import profiles  # noqa: E402
import saetze  # noqa: E402
import taten  # noqa: E402
import tipps  # noqa: E402
import werkzeug_abdeckung as wa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000
ON = dict(spark_help=True, feature_tips=True, feature_sentences=True)
OFF = dict(spark_help=False, feature_tips=False, feature_sentences=False, feature_sentences_voice=False)


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c, next(u["id"] for u in profiles._load()["users"] if u["name"] == name)


class Turn:
    """What saetze.row and saetze.spoken read of a turn (chat_turn.Turn)."""

    def __init__(self, uid, text="Merk dir, dass ich Tee mag", org="panel", body=None, carry=None, own=True):
        self.who = {"id": uid} if uid else None
        self.own_browser = own
        self.hilfe_origin = org
        self.body = body or {}
        self.messages = [{"role": "user", "content": text}]
        self.carry = carry
        self.pics = []
        self.ask_text = text
        self.route = intent.classify(text)
        self.ccfg = features.chat_cfg()


def calls(*names):
    return [{"name": n, "args": "", "result": "ok"} for n in names]


class Sentences(unittest.TestCase):
    """The one list of sentences: every one is a plain request that reaches its tool (guideline part 1, row 29)."""

    def test_every_example_is_in_one_area(self):
        listed = [t for _, _, _, ts in saetze.AREAS for t in ts]
        self.assertEqual(len(listed), len(set(listed)), "a tool in two areas")
        self.assertEqual(sorted(set(wa.SENTENCES) - set(listed)), [], "a sentence of SENTENCES in no area of saetze.AREAS")
        self.assertEqual(sorted(t for t in listed if not saetze.text_of(t)), [])
        for tool, (de, en) in wa.SENTENCES.items():
            self.assertTrue(de and en and de != en and len(de) <= 80 and len(en) <= 80, tool)

    def test_follow_ups_reach_their_tool(self):
        for after, rows in saetze.FOLLOW.items():
            self.assertIn(after, saetze.KEYS_OF, after)
            for tool, de, en in rows:
                self.assertIn(tool, saetze.KEYS_OF, tool)
                self.assertTrue(en and len(de) <= 80, de)
                self.assertIn(tool, intent.classify(de).tools(), f"{de!r} -> {intent.classify(de).label()}")

    def test_near_words_are_no_rule_and_their_sentence_is(self):
        cases = (("Klingel mich morgen um sieben an", "anruf_planen", "Ruf mich morgen um sieben an"),
                 ("Denk in zehn Minuten an den Tee", "reminder_set", "Erinnere mich in zehn Minuten an den Tee"),
                 ("Notier Milch für den Einkauf", "tasks_add", "Setz Milch auf die Einkaufsliste"),
                 ("Bau mir einen Vortrag über den Mauerfall", "document_plan", "Mach eine Präsentation über den Mauerfall"))
        self.assertEqual(len(cases), len(saetze.NEAR), "a case per NEAR entry")
        for said, tool, offered in cases:
            self.assertNotIn(tool, intent.classify(said).tools(), f"{said!r} reaches {tool} itself: no NEAR entry needed")
            hit = saetze.near(said)
            self.assertEqual(hit and (hit[0], hit[1][0]), (tool, offered), said)
            self.assertIn(tool, intent.classify(offered).tools(), offered)
        self.assertIsNone(saetze.near("Mal mir einen Drachen"))
        self.assertIsNone(saetze.near("Klingel mich morgen an\nund noch mehr"))
        self.assertIsNone(saetze.near("Denk " + "x" * 300 + " an den Tee"))
        self.assertIsNone(saetze.near("Klingel mich morgen um sieben an", ("anruf_planen",)))   # it ran anyway

    def test_voice_and_start_lists_name_real_tools(self):
        for name in ("VOICE", "NOT_START", "ONLY", "READY"):
            self.assertEqual(sorted(set(getattr(saetze, name)) - set(saetze.KEYS_OF)), [], name)


class Rows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.uid = profile("Satztest")

    def setUp(self):
        helpers.set_config(memory=True, history=True, reminders=True, **ON)
        tipps.forget(self.uid)

    def tearDown(self):
        try:
            os.remove(notaus.FILE)
        except FileNotFoundError:
            pass
        helpers.set_config(**OFF)

    def test_off_by_default_and_never_for_guests(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "config.default.json")) as f:
            chat = json.load(f)["chat"]
        self.assertIs(chat["feature_sentences"], True)  # Grundausstattung (2026-10-17)
        self.assertIn("chat.feature_sentences", features.GRUNDAUSSTATTUNG)
        self.assertIs(chat["feature_sentences_voice"], False)
        self.assertIs(profiles.SETTINGS["voice_tips"][0], True)   # unasked at a speaker: a preference, on unless off
        self.assertIsNone(saetze.row(Turn(None), calls("memory_save"), now=T0))
        helpers.set_config(feature_sentences=False)
        self.assertIsNone(saetze.row(Turn(self.uid), calls("memory_save"), now=T0))
        self.assertEqual(saetze.start(self.uid, now=T0), [])
        self.assertEqual(self.p.get("/api/profile/saetze").json(), {"on": False, "areas": [], "start": []})
        self.assertEqual(self.p.delete("/api/profile/saetze").status_code, 403)
        self.assertEqual(TestClient(panel.app).get("/api/profile/saetze").status_code, 401)

    def test_a_follow_up_only_for_a_tool_never_used(self):
        ev = saetze.row(Turn(self.uid), calls("memory_save"), now=T0)
        self.assertEqual(ev["kind"], "follow")
        self.assertEqual([x["tool"] for x in ev["items"]], ["history_search"])
        self.assertEqual(ev["items"][0]["text"][0], "Haben wir schon mal darüber gesprochen?")
        st = tipps._st(self.uid)
        self.assertIn("memory_save", st["used"])
        self.assertEqual(json.dumps(st).count("Tee"), 0, "never a word of the question")
        # the same tool's sentence not again within 14 days, and never once the profile used it
        self.assertIsNone(saetze.row(Turn(self.uid), calls("memory_save"), now=T0 + 3600))
        saetze.row(Turn(self.uid), calls("history_search"), now=T0 + 7200)
        self.assertIsNone(saetze.row(Turn(self.uid), calls("memory_save"), now=T0 + 20 * 86400))

    def test_six_rows_a_day(self):
        n = 0
        for i in range(10):
            tipps._mut(self.uid, lambda st: st.update(said={}, used={}))
            if saetze.row(Turn(self.uid), calls("memory_save"), now=T0 + i * 60):
                n += 1
        self.assertEqual(n, saetze.DAY_MAX)

    def test_none_after_outside_text_under_the_notaus_over_mcp_or_another_voice(self):
        self.assertIsNone(saetze.row(Turn(self.uid), calls("memory_save"), outside=True, now=T0))
        self.assertIsNone(saetze.row(Turn(self.uid, carry="mail"), calls("memory_save"), now=T0))
        self.assertIsNone(saetze.row(Turn(self.uid, org="mcp"), calls("memory_save"), now=T0))
        self.assertIsNone(saetze.row(Turn(self.uid, org="speaker"), calls("memory_save"), now=T0))
        self.assertIsNone(saetze.row(Turn(self.uid, own=False), calls("memory_save"), now=T0))
        with mock.patch.object(notaus, "refuse", return_value=True):
            self.assertIsNone(saetze.row(Turn(self.uid), calls("memory_save"), now=T0))
            self.assertEqual(saetze.start(self.uid, now=T0), [])
        self.assertIsNotNone(saetze.row(Turn(self.uid), calls("memory_save"), now=T0))

    def test_telegram_gets_only_sentences_that_change_nothing(self):
        ev = saetze.row(Turn(self.uid, org="telegram"), calls("memory_save"), now=T0)
        self.assertEqual([x["tool"] for x in ev["items"]], ["history_search"])
        tipps.forget(self.uid)
        self.assertIsNone(saetze.row(Turn(self.uid, org="telegram"), calls("web_search"), now=T0))   # memory_save, …: act
        self.assertIn("memory_save", taten.KIND)

    def test_meintest_du(self):
        helpers.set_config(tasks=True)
        try:
            ev = saetze.row(Turn(self.uid, "Notier Milch für den Einkauf"), [], now=T0)
            self.assertEqual((ev["kind"], ev["items"][0]["text"][0]), ("near", "Setz Milch auf die Einkaufsliste"))
        finally:
            helpers.set_config(tasks=False)
        self.assertIsNone(saetze.row(Turn(self.uid, "Notier Milch für den Einkauf"), [], now=T0))   # tasks off: nothing

    def test_was_kannst_du_lists_what_the_profile_can_use(self):
        helpers.keep_chat(self, "search", "bilder")
        helpers.set_config(search=False, bilder=False)   # other test modules may leave them on
        ev = saetze.row(Turn(self.uid, "Was kannst du alles?"), [], now=T0)
        self.assertEqual(ev["kind"], "kann")
        tools = {x["tool"] for x in ev["items"]}
        self.assertIn("memory_save", tools)
        self.assertNotIn("web_search", tools)   # off on this Spark
        areas = self.p.get("/api/profile/saetze").json()
        self.assertTrue(areas["on"])
        self.assertIn("memory_save", {x["tool"] for a in areas["areas"] for x in a["items"]})
        self.assertNotIn("bild_malen", {x["tool"] for a in areas["areas"] for x in a["items"]})

    def test_start_changes_by_the_week_and_skips_what_needs_a_before(self):
        # the Grundausstattung's help sentence comes first until it was used once (test_grundausstattung.FirstChat)
        self.assertEqual(saetze.start(self.uid, now=T0)[0]["tool"], "spark_hilfe")
        tipps._mut(self.uid, lambda st: st["used"].update(spark_hilfe=T0))
        a = [x["tool"] for x in saetze.start(self.uid, now=T0)]
        self.assertEqual(a, [x["tool"] for x in saetze.start(self.uid, now=T0 + 3600)])
        self.assertTrue(a and not set(a) & saetze.NOT_START)
        self.assertLessEqual(len(a), saetze.MAX_START)
        r = self.p.get("/api/profile/saetze?nur=start").json()
        self.assertEqual((r["on"], r["areas"]), (True, []))

    def test_a_tap_counts_only_the_tool_and_delete_forgets(self):
        self.assertTrue(saetze.tapped(self.uid, "history_search"))
        self.assertFalse(saetze.tapped(self.uid, "rm -rf"))
        self.assertEqual(tipps._st(self.uid)["zahl"]["tap"], {"history_search": 1})
        view = saetze.admin_view(now=T0)
        self.assertTrue(view["on"])
        self.assertGreaterEqual(view["tap"], 1)
        self.assertEqual(self.p.delete("/api/profile/saetze").json(), {"ok": True})
        self.assertEqual(tipps._st(self.uid)["zahl"], {})
        self.assertEqual(features.OWN[saetze.KEY][0](self.uid), 0)

    def test_the_chat_sends_the_row_and_counts_the_tap(self):
        r = self.p.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL memory_save {"text": "Ich mag Tee"}'}],
                                           "speak": False})
        more = [e for e in helpers.events(r) if e.get("type") == "more"]
        self.assertEqual(len(more), 1, more)
        self.assertEqual(more[0]["items"][0]["tool"], "history_search")
        self.p.post("/api/chat", json={"messages": [{"role": "user", "content": "Haben wir schon mal darüber gesprochen?"}],
                                       "speak": False, "more": "history_search"})
        self.assertEqual(tipps._st(self.uid)["zahl"].get("tap"), {"history_search": 1})


class Spoken(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.uid = profile("Satzstimme")

    def setUp(self):
        helpers.set_config(memory=True, history=True, feature_sentences_voice=True, **ON)
        tipps.forget(self.uid)
        profiles.save_settings(self.uid, {"voice_tips": True})

    def tearDown(self):
        helpers.set_config(**OFF)

    def test_once_a_day_only_at_spoken_channels(self):
        self.assertEqual(saetze.spoken(Turn(self.uid), calls("memory_save"), now=T0), "")   # the panel has buttons
        s = saetze.spoken(Turn(self.uid, org="speaker"), calls("memory_save"), now=T0)
        self.assertEqual(s, "Übrigens: du kannst auch sagen „Haben wir schon mal darüber gesprochen?“.")
        tipps._mut(self.uid, lambda st: st.update(said={}))
        self.assertEqual(saetze.spoken(Turn(self.uid, org="speaker"), calls("memory_save"), now=T0 + 3600), "")
        self.assertTrue(saetze.spoken(Turn(self.uid, org="iphone", body={"car": True}), calls("memory_save"), en=True,
                                      now=T0 + 90000).startswith("By the way"))

    def test_the_profile_and_the_admin_can_switch_it_off(self):
        profiles.save_settings(self.uid, {"voice_tips": False})
        self.assertEqual(saetze.spoken(Turn(self.uid, org="speaker"), calls("memory_save"), now=T0), "")
        profiles.save_settings(self.uid, {"voice_tips": True})
        helpers.set_config(feature_sentences_voice=False)
        self.assertEqual(saetze.spoken(Turn(self.uid, org="speaker"), calls("memory_save"), now=T0), "")

    def test_only_what_works_by_voice(self):
        for t in ("bild_malen", "document_plan", "camera_describe", "iphone_action"):
            self.assertNotIn(t, saetze.VOICE)


if __name__ == "__main__":
    unittest.main()
