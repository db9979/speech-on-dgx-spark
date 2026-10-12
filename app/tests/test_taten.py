"""Taten prüfen und Fehlerschleife stoppen (taten.py, plan handlungs-pruefung, Dominik 2026-10-12 „wie empfohlen“):
a sentence that claims a deed no tool managed in this answer is not said, the panel says one fixed sentence instead;
the same tool failing twice with the same details is not run a third time. Fixed rules, no model, no clock."""
import re
import unittest

from tests import helpers

helpers.start()
import chat  # noqa: E402
import features  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
import taten  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def ask(c, text):
    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": text}], "client": "web"})
    assert r.status_code == 200, r.text
    evs = helpers.events(r)
    return "".join(e.get("delta", "") for e in evs if e.get("type") == "text"), evs


class Rules(unittest.TestCase):
    def test_claims(self):
        for text, kinds in [("Der Fernseher ist aus.", {"geraet"}), ("Das Licht ist jetzt an.", {"geraet"}),
                            ("Ich habe das Licht im Flur eingeschaltet.", {"geraet"}),
                            ("Ich habe den Termin eingetragen.", {"termin"}), ("Steht jetzt in deinem Kalender.", {"termin"}),
                            ("Die Erinnerung ist gestellt.", {"erinnerung"}), ("Ich erinnere dich um 8.", {"erinnerung"}),
                            ("Die Nachricht an Anna ist gesendet.", {"nachricht"}), ("Habe ich mir gemerkt.", {"merken"}),
                            ("Das Dokument habe ich erstellt.", {"dokument"}), ("Erledigt.", {""}),
                            ("The light is now on.", {"geraet"}), ("I'll remind you at 8.", {"erinnerung"})]:
            self.assertEqual(taten.claims(text), kinds, text)
        for text in ["Soll ich das Licht einschalten?", "Möchtest du, dass ich es eintrage?", "Es ist jetzt 10 Uhr.",
                     "Der Fernseher ist nicht aus.", "Ich habe nachgesehen: Das Licht brennt.", "Hallo.",
                     "Das hat nicht geklappt: Fernseher."]:
            self.assertEqual(taten.claims(text), set(), text)

    def test_check(self):
        off = [{"art": "geraet", "ok": False, "wait": False, "what": "tv"}]
        on = [{"art": "geraet", "ok": True, "wait": False, "what": "tv"}]
        self.assertEqual(taten.check("Der Fernseher ist aus.", off, {"home_assistant"}), ["geraet"])
        self.assertEqual(taten.check("Der Fernseher ist aus.", [], {"home_assistant"}), ["geraet"])
        self.assertEqual(taten.check("Der Fernseher ist aus.", on, {"home_assistant"}), [])
        self.assertEqual(taten.check("Erledigt.", [], {"home_assistant"}), [""])
        self.assertEqual(taten.check("Erledigt.", [], {"weather"}), [])          # nothing that changes things offered
        self.assertEqual(taten.check("Erledigt.", on, {"home_assistant"}), [])
        self.assertEqual(taten.check("Fertig.", [], {"home_assistant"}, looked=True), [])   # a look-up that worked
        # in doubt the sentence is said: one of the deeds it names worked
        both = taten.claims("Ich habe den Termin eingetragen und die Nachricht an Anna gesendet.")
        self.assertEqual(both, {"termin", "nachricht"})
        self.assertEqual(taten.check("Ich habe den Termin eingetragen und die Nachricht an Anna gesendet.",
                                     [{"art": "termin", "ok": True}], set()), [])

    def test_results(self):
        self.assertTrue(taten.failed("Fehler: not found"))
        self.assertTrue(taten.failed("Not done: code word missing"))
        self.assertTrue(taten.failed(""))
        self.assertTrue(taten.failed(None))
        self.assertFalse(taten.failed("Set: 'Tee' at 19:42."))
        a = taten.act("calendar_add", {"title": "Zahnarzt"}, "NOT saved yet. Read this proposal to the user")
        self.assertEqual((a["art"], a["ok"], a["wait"]), ("termin", False, True))
        a = taten.act("home_assistant", {"entity_id": "media_player.tv_wohnzimmer"}, "Fehler")
        self.assertEqual((a["ok"], a["what"]), (False, "tv wohnzimmer"))
        self.assertIsNone(taten.act("weather", {}, "12 Grad"))
        self.assertEqual(taten.sentence("geraet", "failed", what="Fernseher"), "Das hat nicht geklappt: Fernseher.")
        self.assertEqual(taten.sentence("geraet", "missing"), "Das habe ich nicht ausgeführt.")
        self.assertEqual(taten.sentence("termin", "failed", en=True), "That did not work: the appointment.")

    def test_every_tool_that_changes_something_has_a_kind(self):
        names = {t["function"]["name"] for t in vars(chat).values() if isinstance(t, dict) and t.get("type") == "function"}
        names |= {t["function"]["name"] for v in vars(chat).values() if isinstance(v, list)
                  for t in v if isinstance(t, dict) and t.get("type") == "function"}
        writes = {n for n in names if re.search(r"_(set|add|send|save|forget|change|draft|action|note|cancel|plan|"
                                                r"attachment|announce)$|^home_assistant$", n)}
        self.assertTrue(writes)
        self.assertEqual(sorted(writes - set(taten.KIND)), [])
        self.assertTrue(set(taten.STATUS) <= set(taten.KIND.values()))

    def test_only_re_and_time(self):
        src = open(taten.__file__).read()
        self.assertEqual(sorted(set(re.findall(r"^import (\w+)|^from (\w+)", src, re.M)) - {("", "")}),
                         [("re", ""), ("time", "")])


class Chat(unittest.TestCase):
    def tearDown(self):
        helpers.set_config(action_check=True, loop_stop=True)

    def test_on_by_default_with_a_reason(self):
        import json
        import os
        cfg = json.load(open(os.path.join(helpers.APP, "config.default.json")))["chat"]
        self.assertTrue(cfg["action_check"] and cfg["loop_stop"])
        self.assertIn("chat.action_check", features.DEFAULT_ON)
        self.assertIn("chat.loop_stop", features.DEFAULT_ON)

    def test_claim_without_a_tool_is_not_said(self):
        c = profile("Taten1")
        said, evs = ask(c, "SAY |x| Gut. Habe ich mir gemerkt.")
        self.assertIn("Gut.", said)
        self.assertNotIn("gemerkt", said)
        self.assertIn("Das habe ich nicht ausgeführt.", said)
        helpers.set_config(action_check=False)
        said, _ = ask(c, "SAY |x| Gut. Habe ich mir gemerkt.")
        self.assertIn("Habe ich mir gemerkt.", said)

    def test_a_tool_that_worked_lets_it_through(self):
        c = profile("Taten2")
        said, _ = ask(c, 'TOOL reminder_set {"text": "Tee", "minutes": 10}')
        self.assertIn("Ergebnis: Set:", said)
        self.assertNotIn("nicht ausgeführt", said)

    def test_loop_stops_after_the_second_same_failure(self):
        c = profile("Taten3")
        helpers.LLM_CALLS.clear()
        said, _ = ask(c, 'LOOP reminder_set {"text": "Tee", "minutes": -5}')
        calls = [b for b in helpers.LLM_CALLS if b.get("stream")]
        tool_msgs = [m for m in calls[-1]["messages"] if m["role"] == "tool"]
        self.assertEqual(sum("Invalid time" in str(m["content"]) for m in tool_msgs), 2)   # run twice, never a third time
        self.assertIn(chat.LOOP_NOTE, tool_msgs[-1]["content"])
        self.assertNotIn("reminder_set", [t["function"]["name"] for t in calls[-1].get("tools") or []])
        node = next(x for x in live.snapshot("admin")["targets"] if x["id"] == "taten")
        self.assertIn("Schleifen gestoppt", node["sub"])
        self.assertNotIn("Tee", node["sub"])
        helpers.set_config(loop_stop=False)
        helpers.LLM_CALLS.clear()
        ask(c, 'LOOP reminder_set {"text": "Tee", "minutes": -5}')
        last = [b for b in helpers.LLM_CALLS if b.get("stream")][-1]
        self.assertGreater(sum("Invalid time" in str(m.get("content")) for m in last["messages"] if m["role"] == "tool"), 2)


if __name__ == "__main__":
    unittest.main()
