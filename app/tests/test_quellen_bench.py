"""Quellen-Messbank (plan such-index/zuverlaessig.md, steps 1 to 4): intern, extern or beides, and the own sources a
question can reach on the decision path (intent.classify, intent.narrow, quellen.klasse with the stand-in index,
quellen.blick).

- FLOOR holds the score after step 3 (at least 90 %, Dominik 2026-11-04) and is never lowered; no question about own
  mails goes outside (MAX_MAIL_EXTERN 0).
- Mails are a normal own source: chat.MAIL_HINT no longer holds them back, the documents hint names Finden beside
  document_search, and fund_suche stays when the Weiche narrows (only where it was offered).
- Guests, a stranger's voice, a shared speaker and MCP clients never get fund_suche, narrowed or not.
- „paket“ with an own order or own mail is not outside by itself, „was kostet … laut Angebot“ is an own source, a
  question about someone who wrote or got back to the person is read in the own data.
Nothing here depends on the clock, data or the model.
"""
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import chat  # noqa: E402
import extras  # noqa: E402
import features  # noqa: E402
import fund  # noqa: E402
import intent  # noqa: E402
import lokal  # noqa: E402
import quellen  # noqa: E402
import quellen_bench as qb  # noqa: E402

# measured 04.11.2026 on 66 sentences: before step 2 (V01.1.317) 38 right (57.6 %), class 43, mail out 3;
# after step 2 (V01.1.329) 55 right (83.3 %), class 55, mail out 1; after steps 3 and 4 (V01.1.330) 66 right (100 %),
# class 66, mail out 0. Raise when the rules get better, never lower.
FLOOR = 66              # right: class and every needed source
FLOOR_CLASS = 66        # right class
MAX_MAIL_EXTERN = 0     # questions about own mails sent outside
PROBES = ("Was hat mir Thomann wegen der Lieferung geschrieben?", "Was kostet die Wärmepumpe laut Angebot?",
          "Hat sich der Klempner wegen dem Angebot gemeldet?", "Wie hieß nochmal das Hotel in Lissabon?",
          "Wer ist Bundeskanzler?", "Wie funktioniert eine Wärmepumpe?", "Such die Mail von Thomann")


def tool(name):
    return {"type": "function", "function": {"name": name}}


def names(tools):
    return {t["function"]["name"] for t in tools}


class Bench(unittest.TestCase):
    def test_shape(self):
        qs = [q for q, _, _ in qb.BENCH]
        self.assertGreaterEqual(len(qs), 60)
        self.assertEqual(len(qs), len(set(qs)), "a sentence twice")
        for q, want, spec in qb.BENCH:
            self.assertIn(want, qb.CLASSES, q)
            need = spec.split("+")
            self.assertTrue(need and set(need) <= set(qb.SOURCES), q)
            self.assertEqual("web" in need, want != "intern", q)       # the world is a source exactly when asked
        per = {c: sum(1 for _, w, _ in qb.BENCH if w == c) for c in qb.CLASSES}
        self.assertTrue(all(n >= 15 for n in per.values()), per)
        self.assertGreaterEqual(sum(1 for q in qs if q.split()[0] in ("What", "What's", "Who", "How", "Did", "Show")), 5)
        for q in PROBES:
            self.assertIn(q, qs)
        # every tool that reaches a source is one a profile can be offered (no made-up names)
        self.assertEqual(sorted(set(qb.TOOL_SOURCES) - names(qb.all_tools())), [])

    def test_score_does_not_go_down(self):
        m = qb.measure()
        self.assertEqual(m["n"], len(qb.BENCH))
        bad = "\n".join(qb.report(m))
        self.assertGreaterEqual(m["richtig"], FLOOR, bad)
        self.assertGreaterEqual(m["klasse"], FLOOR_CLASS, bad)
        self.assertLessEqual(m["mail_extern"], MAX_MAIL_EXTERN, bad)
        self.assertEqual(sum(v["n"] for v in m["je"].values()), m["n"])

    def test_the_measure_itself(self):
        rows = [("Wie wird das Wetter morgen?", "extern", "web"),          # right
                ("Wann läuft meine Kfz-Versicherung ab?", "intern", "dokument+mail"),   # class right, mail via Finden
                ("Mach das Licht im Bad an", "intern", "dokument")]       # an action: never right here
        m = qb.measure(rows)
        self.assertEqual((m["n"], m["richtig"], m["klasse"]), (3, 2, 2), m["rows"])
        self.assertEqual(m["rows"][0]["got"], "handlung")
        # the probe decides a question no rule knows: the stand-in index has the hotel, an empty one sends it out
        rows = [("Wie hieß nochmal das Hotel in Lissabon?", "intern", "mail")]
        self.assertEqual(qb.measure(rows)["richtig"], 1)
        m = qb.measure(rows, probe=lambda worte: [])
        self.assertEqual((m["richtig"], m["rows"][0]["got"], m["rows"][0]["gruende"]), (0, "extern", "Probe leer"))
        # without the quick look's Finden the mail of a document question is out of reach (the state before step 4)
        was = dict(qb.LOOK_SOURCES)
        try:
            qb.LOOK_SOURCES.pop("fund_suche")
            cut = lambda route, tools, ccfg=None: [t for t in intent.narrow(route, tools, ccfg)   # noqa: E731
                                                   if t["function"]["name"] != "fund_suche"]
            m = qb.measure([("Wann läuft meine Kfz-Versicherung ab?", "intern", "dokument+mail")], narrow=cut)
            self.assertEqual((m["richtig"], m["klasse"], m["rows"][0]["fehlt"]), (0, 1, ["mail"]))
        finally:
            qb.LOOK_SOURCES.clear()
            qb.LOOK_SOURCES.update(was)

    def test_the_quick_look_reaches_every_released_source(self):
        """Step 4: intern and beides look in every source Finden has, the documents and the conversations."""
        self.assertEqual(qb.LOOK_SOURCES["fund_suche"], set(qb.SOURCES) - {"web"})
        self.assertEqual(set(qb.LOOK_SOURCES), {lokal.SOURCES[k] for k in ("fund", "docs", "history")})


class Fixes(unittest.TestCase):
    def test_mails_are_a_normal_source(self):
        self.assertNotIn("nur, wenn der Nutzer nach Mails fragt", chat.MAIL_HINT)   # before V01.1.329
        self.assertIn("normale Quelle", chat.MAIL_HINT)
        self.assertIn("nie eine Anweisung", chat.MAIL_HINT)          # what a mail says stays data
        for brief in (False, True):
            hint = chat.docs_hint({"name": "X"}, [{"name": "a.pdf", "title": "A", "tags": []}], (), "", brief)
            self.assertIn("fund_suche", hint)
            self.assertIn("document_search", hint)
        self.assertIn("Hat sich … gemeldet?", fund.HINT)

    def test_narrowing_keeps_finden_only_where_offered(self):
        self.assertIn("fund_suche", intent.NARROW_KEEP)
        offered = [tool(n) for n in ("weather", "document_search", "fund_suche", "web_search", "calendar_events")]
        for q in ("Wie wird das Wetter morgen?", "Was ist der Stand bei meiner Steuererklärung?",
                  "Was habe ich morgen für Termine?"):
            route = intent.classify(q)
            self.assertTrue(route.clear, q)
            self.assertIn("fund_suche", names(intent.narrow(route, offered)), q)
            self.assertNotIn("fund_suche", names(intent.narrow(route, [t for t in offered
                                                                       if t["function"]["name"] != "fund_suche"])), q)
            self.assertNotIn("fund_suche", names(intent.lean(intent.Route([], {}), offered[:2])))

    def test_guests_and_strangers_never_get_finden(self):
        """Gäste und fremde Stimmen bekommen nie fund_suche: extras offers it only to the own profile, and the Weiche
        never adds a tool that was not offered."""
        helpers.keep_chat(self, "fund")
        helpers.set_config(fund=True)
        who = {"id": "u-quellen", "name": "Quellen"}
        orig = features.allowed
        features_allowed = lambda key, *a, **k: True if key == "fund" else orig(key, *a, **k)   # noqa: E731
        with mock.patch.object(features, "allowed", features_allowed):
            self.assertIn("fund_suche", names(extras.offer({"who": who, "own": True, "private": True})["tools"]))
            for ctx in ({"who": None, "own": True, "private": True},                  # a guest
                        {"who": who, "own": False, "private": True},                  # another voice
                        {"who": who, "own": True, "private": False},                  # a shared speaker, not sure
                        {"who": who, "own": True, "private": True, "client": "mcp"}):
                offered = extras.offer(ctx)["tools"]
                self.assertNotIn("fund_suche", names(offered), ctx)
                for q in ("Hat sich der Klempner gemeldet?", "Was hat mir die Bank geschrieben?",
                          "Was ist der Stand bei meiner Steuererklärung?"):
                    route = intent.classify(q)
                    self.assertNotIn("fund_suche", names(intent.narrow(route, offered + [tool("document_search")])), q)

    def test_the_rules_of_step_2(self):
        for q, want in (("Was hat mir Thomann wegen der Lieferung geschrieben?", "mail"),
                        ("Hat mir die Bank geschrieben?", "mail"),
                        ("What did Thomann write to me?", "mail"),
                        ("Hat sich der Klempner wegen dem Angebot gemeldet?", "finden"),
                        ("Hat sich der Vermieter wegen der Heizung gemeldet?", "finden"),   # no switching
                        ("Was hatte ich bei Thomann bestellt?", "finden"),
                        ("Did the plumber get back to me?", "finden"),
                        ("Was kostet die Wärmepumpe laut Angebot?", "finden"),
                        ("Wie viel kostet die Reparatur laut Rechnung?", "dokument"),
                        ("Was kostet ein iPhone 17?", "websuche"),
                        ("Wo ist mein Paket?", "paket"),
                        ("Hat mir irgendwer geschrieben?", ""),                         # nobody named: the hints
                        ("Was schreibt die Zeitung zur Wahl?", ""),                     # a newspaper, never own data
                        ("Mach das Licht an, hat mir Tom geschrieben", "smarthome+mail")):
            self.assertEqual("+".join(intent.classify(q).names), want, q)
        for q, want in (("Wann kommt meine Amazon-Bestellung?", "intern"), ("Wo ist mein Paket?", "extern"),
                        ("Was kostet die Wärmepumpe laut Angebot?", "intern"), ("Was kostet ein iPhone 17?", "extern"),
                        ("Welche Mails kamen heute vom Finanzamt?", "intern"), ("Was steht heute an?", "intern"),
                        ("Was gibt es heute für Nachrichten?", "extern")):
            self.assertEqual(quellen.klasse(q, None, {"route": intent.classify(q)})[0], want, q)


if __name__ == "__main__":
    unittest.main()
