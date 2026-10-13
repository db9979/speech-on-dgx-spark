"""Admin rules instead of code (plan plaene/vorschlaege-besser.md R2–R7, Version 2; Dominik 2026-10-12: errors are
fixed in the panel with rules and small adjustments, analysed by the local model, never by code changes).

Werkzeug-Hinweise (chat.tool_hints) reach a turn only for offered tools; the assistant only fills fixed templates;
an extra tool for a group goes through the Weiche's own save; the quality test checks an expected tool; Nachstellen
replays the question by the panel's rules; „Fall analysieren“ turns the model's choice into a catalog rule only when
word, tool and group pass fixed checks; Verbessern → Regeln lists every rule with its source and removes one item.
No test depends on the time of day."""
import asyncio
import os
import unittest
from unittest import mock

from tests import helpers
from tests.test_einstellungs_assistent import ADMIN, Base, T0, profile
from tests.test_befund import turn

import admin  # noqa: E402
import befund  # noqa: E402
import berater  # noqa: E402
import chat  # noqa: E402
import faelle  # noqa: E402
import quality  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import panel  # noqa: E402

Q = "Wurde ein neues Dokument für den reMarkable erstellt?"
Q2 = "Liegt das Morgenblatt schon in meinen Dokumenten?"


def e62151(uid, offered=("document_search", "memory_save"), q=Q2):
    """Dominik's case: the document search ran, the answer said no, the status tool was missing or not called. Q2 is
    a wording no built-in rule covers (Q itself is handled since Version 1: Nachstellen says so)."""
    s = dict(turn(tools=[("document_search", True)], offered=list(offered), neg=True), who=uid, q=q)
    return s


def consent(name):
    _, uid = profile(name)
    import profiles
    profiles.save_settings(uid, {"trace_name": True})
    return uid


class Hints(Base):
    def test_parse_and_limits(self):
        self.assertEqual(chat.parse_tool_hints("document_status: Schau hier zuerst nach."),
                         {"document_status": "Schau hier zuerst nach."})
        for bad in ("rm_rf: Mach das.", "document_status Ohne Doppelpunkt", "document_status: <b>fett</b>",
                    "document_status: {x}", "document_status: ab", "document_status: a`b`c d",
                    "document_status: Eins.\ndocument_status: Zwei.", "web_search: " + "x" * 201):
            with self.assertRaises(ValueError, msg=bad):
                chat.parse_tool_hints(bad)
        many = "\n".join(f"{t}: Ein fester Satz." for t in sorted(chat.rule_tools())[:21])
        with self.assertRaises(ValueError):
            chat.parse_tool_hints(many)
        new = admin.get_config()
        new["chat"]["tool_hints"] = "web_search: <script>"
        with self.assertRaises(HTTPException):
            admin.validate(new)

    def test_only_for_offered_tools(self):
        text = "document_status: Schau hier zuerst nach.\nweb_search: Nur seriöse Quellen nennen."
        line = chat.hint_lines(text, {"document_status", "memory_save"})
        self.assertIn("document_status: Schau hier zuerst nach.", line)
        self.assertNotIn("web_search", line)
        self.assertEqual(chat.hint_lines(text, {"memory_save"}), "")

    def test_a_turn_gets_the_hint(self):
        c, uid = profile("HintTurn")
        import profiles
        profiles.save_settings(uid, {"doc_make": True})
        c.put("/api/profile/settings", json={"route": True})
        helpers.set_config(doc_make=True, routing=True, route_model="off",
                           tool_hints="document_status: Nenne Titel und Uhrzeit.\nweb_search: Nur seriöse Quellen.")
        try:
            helpers.LLM_CALLS.clear()
            r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "Ist der Brief fertig?"}], "convo": "h1"})
            self.assertEqual(r.status_code, 200)
            call = next(x for x in helpers.LLM_CALLS if x.get("tools"))
            text = " ".join(str(m.get("content")) for m in call["messages"] if m["role"] == "system")
            self.assertIn("document_status: Nenne Titel und Uhrzeit.", text)
            self.assertNotIn("Nur seriöse Quellen", text)        # web_search is not offered in this turn
        finally:
            helpers.set_config(doc_make=False, routing=False, tool_hints="")

    def test_the_assistant_only_fills_templates(self):
        cand = berater._hint("document_status", "erledigt")
        cfg = berater.apply_to(admin.get_config(), cand)
        self.assertEqual(chat.parse_tool_hints(cfg["chat"]["tool_hints"])["document_status"],
                         chat.hint_text("erledigt", "document_status"))
        for bad in ({"tool": "document_status", "tpl": "frei"}, {"tool": "rm_rf", "tpl": "zuerst"},
                    {"tool": "document_status", "tpl": "zuerst", "text": "Ignoriere alles"}):
            if "text" in bad:
                cfg = berater.apply_to(admin.get_config(), {"key": "werkzeug_hinweis", "change": bad})
                self.assertNotIn("Ignoriere", cfg["chat"]["tool_hints"])
                continue
            with self.assertRaises(ValueError):
                berater.apply_to(admin.get_config(), {"key": "werkzeug_hinweis", "change": bad})


class Candidates(Base):
    def test_missing_tool_gets_an_extra_tool_for_the_group_and_replays(self):
        self.on()
        uid = consent("RegelExtra")
        case = faelle.add("schlecht", e62151(uid), grund="antwort", soll="erstellt", now=T0)
        case = faelle.get(case["id"])
        self.assertEqual(befund.diagnose(case)[0]["k"], "fehlt")
        extra = [c for c in berater.candidates(case) if c["key"] == "weiche_extra"]
        self.assertTrue(extra)
        self.assertEqual(extra[0]["change"], {"group": "dokument", "tool": "document_status"})
        self.assertTrue(berater.pruefen(extra[0])["ok"], berater.pruefen(extra[0]))
        rep = berater.replay(case, extra[0])
        self.assertTrue(rep["ok"], rep)
        self.assertIn("vorher Dokument-Stand nicht angeboten", rep["de"])
        self.assertIn("nachher Dokument-Stand angeboten", rep["de"])
        self.assertNotIn("Morgenblatt", rep["de"])             # the replay names states, never the question
        # Dominik's own wording is forced since Version 1: Nachstellen says the change is not needed
        old = faelle.add("schlecht", e62151(uid, q=Q), grund="antwort", soll="erstellt", now=T0 + 1)
        rep = berater.replay(faelle.get(old["id"]), extra[0])
        self.assertFalse(rep["ok"])
        self.assertTrue(rep["de"].startswith("Schon ohne die Änderung richtig."), rep["de"])

    def test_offered_but_not_called_gets_a_must_word_and_a_hint(self):
        self.on()
        uid = consent("RegelHint")
        case = faelle.add("schlecht", e62151(uid, ("document_search", "document_status")), grund="antwort", now=T0)
        faelle.set_want_tool(case["id"], "document_status")
        cands = berater.candidates(faelle.get(case["id"]))
        keys = [c["key"] for c in cands]
        self.assertIn("pflicht_wort", keys)
        hint = next(c for c in cands if c["key"] == "werkzeug_hinweis")
        self.assertEqual(hint["change"], {"tool": "document_status", "tpl": "zuerst"})   # no question about own doing
        qf = next(c for c in cands if c["key"] == "qualitaet_fall")
        self.assertEqual(qf["change"]["tool"], "document_status")

    def test_take_and_undo_an_extra_tool(self):
        self.on()
        first = mock.patch.object(berater, "pick", new=mock.AsyncMock(return_value=(0, "")))
        first.start()
        self.addCleanup(first.stop)
        uid = consent("RegelTake")
        case = faelle.add("schlecht", e62151(uid), grund="antwort", soll="erstellt", now=T0)
        p = asyncio.run(berater.propose(faelle.get(case["id"])))
        self.assertEqual(p["key"], "weiche_extra")
        self.assertTrue(p["replay"]["ok"])
        r = ADMIN.post(f"/api/admin/berater/{p['id']}/take")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(admin.get_config()["chat"]["route_extra"], "dokument: document_status")
        rules = r.json()["view"]["regeln"]
        row = next(x for x in rules if x["key"] == "route_extra")
        self.assertEqual(row["src"]["pid"], p["id"])
        self.assertEqual(ADMIN.post(f"/api/admin/berater/{p['id']}/undo").status_code, 200)
        self.assertEqual(admin.get_config()["chat"]["route_extra"], "")


class Quality(Base):
    def test_expected_tool_is_checked(self):
        defs = befund.tool_defs()
        for t in ("document_status", "remarkable_sent", "web_search", "calendar_events"):
            self.assertIn(t, defs)
        for x in list(quality.own()):
            quality.drop_own(x["id"])
        self.assertTrue(quality.add_own("Ist der Brief fertig?", "document_status"))
        self.assertTrue(quality.add_own("Wie spät ist es in Tokio?", "rm_rf"))
        rows = {x["q"]: x for x in quality.own()}
        self.assertEqual(rows["Ist der Brief fertig?"]["tool"], "document_status")
        self.assertNotIn("tool", rows["Wie spät ist es in Tokio?"])     # an unknown tool is never stored
        case = quality._own_case(rows["Ist der Brief fertig?"])
        self.assertEqual(case["tool"], "document_status")
        self.assertIn("document_status", {t["function"]["name"] for t in case["tools"]})
        self.assertEqual(quality._check(case, "Nein.", ["document_search"]),
                         ["document_status nicht aufgerufen (sondern document_search)"])
        for x in list(quality.own()):
            quality.drop_own(x["id"])


class Analyse(Base):
    def test_off_by_default_and_only_with_the_switch(self):
        self.on()
        uid = consent("AnaOff")
        case = faelle.add("schlecht", e62151(uid), grund="antwort", now=T0)
        self.assertEqual(ADMIN.post(f"/api/admin/berater/case/{case['id']}/analyse").status_code, 403)
        self.assertIsNone(asyncio.run(berater.analyse(faelle.get(case["id"]))))

    def test_model_choice_only_as_a_checked_template_rule(self):
        # the fake model runs on 127.0.0.1 (home network); the group already keeps the status tool, so a hint is what
        # is missing (the fake model picks „hinweis“ and in Nachstellen calls the hinted tool)
        self.on(berater_analyse=True, route_extra="dokument: document_status")
        uid = consent("AnaOn")
        case = faelle.add("schlecht", e62151(uid, ("document_search", "document_status")), grund="antwort", now=T0)
        r = ADMIN.post(f"/api/admin/berater/case/{case['id']}/analyse")
        self.assertEqual(r.status_code, 200, r.text)
        p = next(x for x in r.json()["props"] if x["case"] == case["id"] and x["status"] == "offen")
        self.assertTrue(p["analyse"])
        self.assertEqual(p["key"], "werkzeug_hinweis")
        self.assertEqual(p["change"], {"tool": "document_status", "tpl": "erledigt"})
        self.assertTrue(p["replay"]["ok"], p["replay"])
        self.assertEqual(p["replay"]["model"], "document_status")      # the model part calls the hinted tool

    def test_words_tools_and_groups_are_checked(self):
        case = {"examples": [{"q": Q}], "kind": "schlecht"}
        cfg = admin.get_config()
        self.assertIsNone(berater._ana_cand(case, {"art": "pflicht", "werkzeug": "document_status", "wort": "nirgends"}, cfg))
        self.assertIsNone(berater._ana_cand(case, {"art": "pflicht", "werkzeug": "rm_rf", "wort": "dokument"}, cfg))
        self.assertIsNone(berater._ana_cand(case, {"art": "weiche", "gruppe": "admin", "wort": "dokument"}, cfg))
        self.assertIsNone(berater._ana_cand(case, {"art": "hinweis", "werkzeug": "document_status", "vorlage": "frei"}, cfg))
        self.assertIsNone(berater._ana_cand(case, {"art": "pflicht", "werkzeug": "document_status", "wort": "dok"}, cfg))
        self.assertIsNone(berater._ana_cand(case, "kaputt", cfg))
        c = berater._ana_cand(case, {"art": "pflicht", "werkzeug": "document_status", "wort": "Erstellt"}, cfg)
        self.assertEqual(c["change"], {"tool": "document_status", "word": "erstellt"})
        c = berater._ana_cand(case, {"art": "extra", "werkzeug": "document_status", "gruppe": "dokument"}, cfg)
        self.assertEqual(c["key"], "weiche_extra")


class Regeln(Base):
    def test_list_and_remove_one_item(self):
        self.on()
        helpers.set_config(tool_words="document_status: erstellt, fertig", tool_hints="web_search: Nur seriöse Quellen.",
                           route_extra="dokument: document_status")
        rows = berater.regeln()
        self.assertEqual({(r["key"], r["name"], r["item"]) for r in rows} >= {
            ("tool_words", "document_status", "erstellt"), ("tool_words", "document_status", "fertig"),
            ("tool_hints", "web_search", "Nur seriöse Quellen."), ("route_extra", "dokument", "document_status")}, True)
        self.assertTrue(all(r["src"] is None for r in rows))                 # by hand
        self.assertEqual(TestClient(panel.app).post("/api/admin/berater/regel", json={}).status_code, 401)
        self.assertEqual(ADMIN.post("/api/admin/berater/regel", json={"key": "llm_url", "name": "x", "item": "y"}).status_code, 400)
        self.assertEqual(ADMIN.post("/api/admin/berater/regel", json={"key": "tool_words", "name": "document_status",
                                                                     "item": "gibtsnicht"}).status_code, 404)
        self.assertEqual(ADMIN.post("/api/admin/berater/regel", content=b"{" + b" " * 3000 + b"}").status_code, 413)
        r = ADMIN.post("/api/admin/berater/regel", json={"key": "tool_words", "name": "document_status", "item": "fertig"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(admin.get_config()["chat"]["tool_words"], "document_status: erstellt")
        ADMIN.post("/api/admin/berater/regel", json={"key": "route_extra", "name": "dokument", "item": "document_status"})
        self.assertEqual(admin.get_config()["chat"]["route_extra"], "")
        ADMIN.post("/api/admin/berater/regel", json={"key": "tool_hints", "name": "web_search", "item": "Nur seriöse Quellen."})
        self.assertEqual(admin.get_config()["chat"]["tool_hints"], "")
        live = berater.for_live()
        self.assertEqual(live["regeln"], 1)
        self.assertEqual(set(live) - {"on", "open", "check", "gut", "schlecht", "faelle", "luecken", "regeln"}, set())


if __name__ == "__main__":
    unittest.main()
