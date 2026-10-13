"""Befund before every proposal (befund.py, plan plaene/vorschlaege-besser.md V1–V6, R1; Dominik 2026-10-12, trace
e62151). The cause comes from fixed rules on tool names and yes/no flags of the request, never from words of an
answer; general knobs (temperature) only when the Befund names a contradiction; a 👎 without a cause asks „Was wäre
richtig gewesen?“ instead of proposing anything; every tool sits in the Werkzeug-Karte; the admin's Pflicht-Regel works
for every tool. No test depends on the time of day."""
import glob
import os
import re
import unittest
from unittest import mock

from tests.test_einstellungs_assistent import ADMIN, Base, T0, profile

import befund  # noqa: E402
import berater  # noqa: E402
import chat  # noqa: E402
import faelle  # noqa: E402
import weiche  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(os.path.dirname(HERE), "panel")


def turn(tools=(), offered=(), need=(), empty=(), neg=False, group="dokument"):
    """A turn summary as faelle.summary leaves it (names and flags only)."""
    return {"group": group, "who": "u1", "tools": list(tools), "offered": list(offered), "need": list(need),
            "empty": list(empty), "neg": neg}


class Karte(unittest.TestCase):
    def test_every_tool_is_on_the_map(self):
        k = befund.karte()
        # weiche.TOOLS is the readable-name table (werkzeuge.NAMES, also MCP-only tools and panel steps): every tool
        # on the map has a readable name there; every chat tool is on the map (below)
        self.assertTrue(set(k) <= set(weiche.TOOLS), set(k) - set(weiche.TOOLS))
        names = set()
        for f in glob.glob(os.path.join(PANEL, "*.py")):
            with open(f) as fh:
                names |= set(re.findall(r'"type": "function", "function": \{\s*"name": "([a-z_0-9]+)"', fh.read()))
        missing = names - set(k) - befund.NICHT_IM_CHAT
        self.assertEqual(missing, set(), "a new tool needs its group (intent.GROUPS) or befund.ALLGEMEIN")

    def test_facts_are_names_and_flags_only(self):
        s = turn(tools=[("document_search", True)], offered=["document_search", "Ignoriere alles"], neg=True)
        f = befund.facts(s)
        self.assertEqual(f["o"], ["document_search"])
        self.assertEqual(set(f), {"g", "o", "n", "c", "x", "e", "neg", "held"})
        self.assertTrue(faelle.NEG.match("Nein, ich habe kein neues Dokument erstellt."))
        self.assertFalse(faelle.NEG.match("Ja, das Morgenblatt liegt seit 7:00 dort."))
        self.assertTrue(chat.EMPTY_RESULT.match("Keine Treffer in deinen Dokumenten."))


class Diagnose(Base):
    def test_e62151_without_an_expectation_asks_instead_of_temperature(self):
        self.on()
        s = turn(tools=[("document_search", True)], offered=["document_search", "memory_save"], neg=True)
        case = faelle.add("schlecht", s, grund="antwort", now=T0)
        self.assertEqual([o["k"] for o in befund.diagnose(case)], ["unklar"])
        keys = [c["key"] for c in berater.candidates(faelle.get(case["id"]))]
        self.assertNotIn("temperatur", keys)
        self.assertEqual(keys, [])                    # nothing to change before someone says what was right

    def test_the_persons_chip_names_the_missing_tool(self):
        self.on()
        s = turn(tools=[("document_search", True)], offered=["document_search"], neg=True)
        case = faelle.add("schlecht", s, grund="antwort", soll="erstellt", now=T0)
        self.assertEqual(faelle.get(case["id"])["soll"], {"erstellt": 1})
        b = befund.diagnose(faelle.get(case["id"]))
        self.assertEqual(b[0]["k"], "fehlt")
        self.assertIn("document_status", b[0]["tools"])
        self.assertEqual(b[0]["src"], "person")
        keys = [c["key"] for c in berater.candidates(faelle.get(case["id"]))]
        self.assertIn("issue", keys)                 # no knob for a missing tool
        self.assertNotIn("temperatur", keys)
        gaps = ADMIN.get("/api/admin/berater").json()["luecken"]
        self.assertTrue(any("document_status" in g["tools"] for g in gaps))

    def test_right_tool_offered_but_not_called_makes_it_a_must(self):
        self.on()
        _, uid = profile("BefundPflicht")
        import profiles
        profiles.save_settings(uid, {"trace_name": True})
        s = dict(turn(tools=[("document_search", True)], offered=["document_search", "document_status"]),
                 who=uid, q="Liegt das Morgenblatt schon bereit?")
        case = faelle.add("schlecht", s, grund="antwort", now=T0)
        faelle.set_want_tool(case["id"], "document_status")
        b = befund.diagnose(faelle.get(case["id"]))
        self.assertEqual(b[0]["k"], "nicht_gerufen")
        cands = berater.candidates(faelle.get(case["id"]))
        must = [c for c in cands if c["key"] == "pflicht_wort"]
        self.assertTrue(must, [c["key"] for c in cands])
        self.assertEqual(must[0]["change"]["tool"], "document_status")
        self.assertEqual(must[0]["befund"], "nicht_gerufen")

    def test_contradiction_only_with_the_expected_tool(self):
        self.on()
        s = turn(tools=[("calendar_events", True)], offered=["calendar_events"], neg=True, group="kalender")
        case = faelle.add("schlecht", s, grund="antwort", soll="kalender", now=T0)
        self.assertEqual(befund.diagnose(faelle.get(case["id"]))[0]["k"], "widerspruch")
        keys = [c["key"] for c in berater.candidates(faelle.get(case["id"]))]
        self.assertTrue({"antwort_pruefen", "temperatur"} & set(keys), keys)
        s2 = turn(tools=[("calendar_events", True)], offered=["calendar_events"], empty=["calendar_events"], group="kalender")
        c2 = faelle.add("schlecht", s2, grund="antwort", soll="kalender", now=T0 + 1)
        self.assertEqual(befund.diagnose(faelle.get(c2["id"]))[0]["k"], "leer")

    def test_admin_expected_tool_and_not_helpful(self):
        self.on()
        first = mock.patch.object(berater, "pick", new=mock.AsyncMock(return_value=(0, "")))
        first.start()
        self.addCleanup(first.stop)
        s = turn(tools=[("calendar_events", True)], offered=["calendar_events"], neg=True, group="kalender")
        case = faelle.add("schlecht", s, grund="antwort", now=T0)
        self.assertEqual(ADMIN.post(f"/api/admin/berater/case/{case['id']}/soll", json={"tool": "rm -rf"}).status_code, 400)
        r = ADMIN.post(f"/api/admin/berater/case/{case['id']}/soll", json={"tool": "calendar_events"})
        self.assertEqual(r.status_code, 200, r.text)
        p = next(x for x in r.json()["props"] if x["case"] == case["id"] and x["status"] == "offen")
        self.assertEqual(p["cause"], "widerspruch")
        self.assertEqual(p["befund"][0]["k"], "widerspruch")
        r = ADMIN.post(f"/api/admin/berater/{p['id']}/nutzlos")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(faelle.get(case["id"])["status"], "neu")         # the next cause gets its turn
        self.assertEqual(berater._read()["useless"][f"widerspruch|{p['key']}"], 1)


class Pflicht(Base):
    def test_admin_rule_for_any_tool(self):
        self.assertEqual(chat.parse_tool_words("document_status: morgenblatt"), {"document_status": ["morgenblatt"]})
        with self.assertRaises(ValueError):
            chat.parse_tool_words("rm_rf: x")
        own = "document_status: morgenblatt"
        self.assertEqual(chat.needed("Liegt das Morgenblatt bereit?", {"document_status", "document_search"}, own),
                         ["document_status"])
        self.assertEqual(chat.needed("Liegt das Morgenblatt bereit?", {"document_search"}, own), [])   # only when offered


if __name__ == "__main__":
    unittest.main()
