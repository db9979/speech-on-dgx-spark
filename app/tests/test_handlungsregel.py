"""The action check as a built-in answer rule (answercheck.action_check, Dominik 2026-10-12 „wie empfohlen
umsetzten“, plan handlungs-pruefung): chat.speak asks answercheck, which decides only through taten.check;
Zustand → Verbessern → Regeln shows both built-in rules with switch state and today's count, never with „Entfernen“;
R4 and the Spark-Tagebuch know the same kinds as the check (taten.KIND, taten.STATUS). No wall clock: times are passed.
Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import os
import re
import unittest

from tests import helpers
from tests.test_einstellungs_assistent import ADMIN, Base, T0
from tests.test_regeln_admin import consent, e62151

helpers.start()
import answercheck  # noqa: E402
import berater  # noqa: E402
import chat  # noqa: E402
import faelle  # noqa: E402
import tagebuch  # noqa: E402
import taten  # noqa: E402

PANEL = os.path.join(helpers.APP, "panel")


class Rule(unittest.TestCase):
    def test_decides_like_taten_check(self):
        acts_ok = [{"art": "geraet", "ok": True, "what": "Fernseher"}]
        acts_bad = [{"art": "geraet", "ok": False, "what": "Fernseher"}]
        for text, acts, offered, looked in (
                ("Ich habe den Fernseher eingeschaltet.", acts_ok, {"home_assistant_action"}, False),
                ("Ich habe den Fernseher eingeschaltet.", acts_bad, {"home_assistant_action"}, False),
                ("Ich habe den Fernseher eingeschaltet.", [], set(), False),
                ("Erledigt.", [], {"home_assistant_action"}, False),
                ("Fertig.", [], {"home_assistant_action"}, True),
                ("Soll ich den Fernseher einschalten?", [], {"home_assistant_action"}, False)):
            self.assertEqual(answercheck.action_check(text, acts, offered, looked), taten.check(text, acts, offered, looked))
        self.assertEqual(answercheck.action_check("Ich habe den Fernseher eingeschaltet.", acts_bad,
                                                  {"home_assistant_action"}), ["geraet"])

    def test_chat_asks_the_rule_not_taten_directly(self):
        src = ""
        for name in ("chat.py", "chat_modell.py"):   # the model side of an answer lives in chat_modell.py
            with open(os.path.join(PANEL, name), encoding="utf-8") as f:
                src += f.read()
        self.assertIn("answercheck.action_check(piece,", src)
        self.assertNotIn("taten.check(", src)

    def test_builtin_rows_with_switch_and_count(self):
        day = T0 + 86400 * 3
        taten._live.update(day="", held=0, loop=0)
        taten.note_live("held", now=day)
        taten.note_live("held", now=day)
        taten.note_live("loop", now=day)
        rows = {r["key"]: r for r in answercheck.builtin({"loop_stop": False}, now=day)}
        self.assertEqual(set(rows), {"action_check", "loop_stop"})
        self.assertEqual((rows["action_check"]["on"], rows["action_check"]["today"]), (True, 2))   # standard on
        self.assertEqual((rows["loop_stop"]["on"], rows["loop_stop"]["today"]), (False, 1))
        self.assertEqual(answercheck.builtin({}, now=day + 86400)[0]["today"], 0)               # a new day
        for r in rows.values():
            self.assertTrue(all(isinstance(x, str) and x for x in r["name"] + r["what"]))

    def test_panel_shows_them_without_remove(self):
        with open(os.path.join(PANEL, "static", "js", "verbessern.js"), encoding="utf-8") as f:
            js = f.read()
        fn = re.search(r"function vbBuiltin\(d\)\{.*?\n(?=function |//)", js, re.S).group(0)
        self.assertNotIn("data-vbrule", fn)
        self.assertIn("html=vbBuiltin(d)+", js)


class Overview(Base):
    def test_overview_lists_the_builtin_rules(self):
        self.on()
        d = ADMIN.get("/api/admin/berater").json()
        self.assertEqual([r["key"] for r in d["eingebaut"]], ["action_check", "loop_stop"])
        self.assertNotIn("action_check", [r["key"] for r in d["regeln"]])    # never one of the admin's own rules


class Kinds(Base):
    def test_diary_knows_every_kind_of_the_check(self):
        self.assertLessEqual(set(taten.KIND.values()), set(tagebuch.ARTEN))
        self.assertLessEqual(set(taten.STATUS), set(tagebuch.ARTEN))
        enum = tagebuch.TOOL["function"]["parameters"]["properties"]["art"]["enum"]
        self.assertLessEqual(set(taten.KIND.values()), set(enum))

    def test_r4_no_without_the_status_tool(self):
        self.on()
        uid = consent("RegelNein")
        q = "Hast du das Morgenblatt schon erstellt?"
        self.assertTrue(chat.DONE_WORDS.search(q))
        case = faelle.add("schlecht", e62151(uid, ("document_search", "document_status"), q=q), grund="antwort", now=T0)
        faelle.set_want_tool(case["id"], "document_status")
        hints = [c["change"] for c in berater.candidates(faelle.get(case["id"])) if c["key"] == "werkzeug_hinweis"]
        self.assertIn({"tool": "document_status", "tpl": "erledigt"}, hints)
        self.assertIn({"tool": "document_status", "tpl": "kein_nein"}, hints)   # taten.STATUS: the status tool
        # a tool that is no status tool gets no „never say no“ hint
        case2 = faelle.add("schlecht", e62151(uid, ("document_search", "memory_save"), q=q), grund="antwort", now=T0 + 1)
        faelle.set_want_tool(case2["id"], "memory_save")
        hints2 = [c["change"] for c in berater.candidates(faelle.get(case2["id"])) if c["key"] == "werkzeug_hinweis"]
        self.assertNotIn({"tool": "memory_save", "tpl": "kein_nein"}, hints2)


if __name__ == "__main__":
    unittest.main()
