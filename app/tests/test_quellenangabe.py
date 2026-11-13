"""Quellenangabe (quellenangabe.py, Dominik 2026-11-13): where an answer came from, by fixed rules of the panel.

- The line names every reading tool that ran and did not fail (werkzeuge.label) and what „Erst lokal“ found
  (kinds and numbers), never a tool that changes something, never a word of a result; without any source it says
  „nichts nachgeschlagen, nur Modellwissen“.
- Own data or the world: from the Weiche's groups (intent.GROUPS, quellen.OWN_GROUPS / WORLD_GROUPS).
- The hint: a question about the own data that looked in none, a question about current things that looked nowhere
  outside.
- „Woher weißt du das?“ is answered by the panel without the model, from the last answer of this profile on this
  device only, for 30 minutes.
- Off by default; never guests; the spoken sentence only at spoken channels and with the preference on.
- Logs and Logs → Anfragen hold fixed words only.
No test depends on the clock of the day.
"""
import asyncio
import contextlib
import io
import json
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import chat_modell  # noqa: E402
import features  # noqa: E402
import intent  # noqa: E402
import lokal  # noqa: E402
import profiles  # noqa: E402
import quellen  # noqa: E402
import quellenangabe as qa  # noqa: E402
import tracelog  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SECRET = "Zebrafink-Geheimnis"
ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1357"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1357"}).status_code == 200
    return c, c.get("/api/whoami").json()["profile"]["id"]


def teile(calls, found=None):
    return qa.teile(calls, quellen.werkzeug_art, found, lokal.art, lokal.ARTEN)


def call(name, result="Ein Ergebnis.", **args):
    return {"name": name, "args": json.dumps(args), "result": result}


class Teile(unittest.TestCase):
    def test_reading_tools_only_and_never_a_result(self):
        parts = teile([call("web_search", "Treffer " + SECRET, query="Goethe Geburtsjahr"),
                          call("calendar_events (Panel)", "3 Termine " + SECRET),
                          call("reminder_set", "Erinnerung gesetzt"),           # changes something: no source
                          call("document_search", "Fehler: nicht erreichbar"),  # failed: no source
                          call("Antwort-Prüfung", "x"),                         # a panel step: no tool
                          call("web_search", "noch mehr", query="Goethe Weimar")])
        self.assertEqual([p["tool"] for p in parts], ["web_search", "calendar_events"])
        self.assertEqual(parts[0]["n"], 2)
        self.assertEqual(parts[0]["mehr"], ["Goethe Geburtsjahr", "Goethe Weimar"])   # the call's words, for „Woher?“
        line = qa.zeile(parts)
        self.assertEqual(line, "Quelle: Websuche, Termine lesen")
        self.assertNotIn(SECRET, line)
        self.assertNotIn("Goethe", line)
        self.assertEqual(qa.zeile(parts, en=True), "Source: Web search, Read appointments")

    def test_nothing_looked_up(self):
        self.assertEqual(qa.zeile([]), "Quelle: nichts nachgeschlagen, nur Modellwissen")
        self.assertEqual(qa.satz([]), "Das weiß ich nur aus meinem Modellwissen, nachgeschlagen habe ich nichts.")

    def test_quick_look_kinds_and_numbers(self):
        found = {"hits": [{"src": "fund", "quelle": "mail", "title": SECRET, "text": SECRET},
                          {"src": "fund", "quelle": "mail", "title": SECRET, "text": SECRET},
                          {"src": "kiwix", "title": "Archiv: Goethe", "text": "x"}],
                 "n": {"fund": 2, "kiwix": 1}, "web": None}
        parts = teile([], found)
        self.assertEqual(qa.zeile(parts), "Quelle: 2 Mails, 1 Archiv-Artikel")
        self.assertEqual([p["art"] for p in parts], ["eigen", "welt"])
        empty = teile([], {"hits": [], "n": {"docs": 0}, "web": None})
        self.assertEqual(qa.zeile(empty), "Quelle: eigene Daten ohne Treffer")

    def test_own_or_world_from_the_weiche(self):
        self.assertEqual(quellen.werkzeug_art("web_search"), "welt")
        self.assertEqual(quellen.werkzeug_art("weather"), "welt")
        self.assertEqual(quellen.werkzeug_art("read_page"), "welt")
        self.assertEqual(quellen.werkzeug_art("calendar_events"), "eigen")
        self.assertEqual(quellen.werkzeug_art("mail_search"), "eigen")     # also a parcel's group: the own mail stays own data
        self.assertEqual(quellen.werkzeug_art("document_search"), "eigen")
        self.assertEqual(quellen.werkzeug_art("get_time"), "")

    def test_hint_when_the_source_does_not_fit(self):
        own = teile([call("calendar_events")])
        web = teile([call("web_search")])
        self.assertEqual(qa.warnung("intern", []), "intern")
        self.assertEqual(qa.warnung("intern", web), "intern")
        self.assertEqual(qa.warnung("intern", own), "")
        self.assertEqual(qa.warnung("extern", own), "extern")
        self.assertEqual(qa.warnung("extern", web), "")
        self.assertEqual(qa.warnung("beides", []), "")
        self.assertEqual(qa.zeile([], "intern"),
                         "Quelle: nichts nachgeschlagen, nur Modellwissen · Achtung: nicht in deinen Daten nachgesehen")
        self.assertEqual(qa.satz(web, "intern"), "Quelle: Websuche. In deinen Daten habe ich nicht nachgesehen.")
        self.assertEqual(qa.satz(teile([call("web_search"), call("calendar_events"), call("weather")]), en=True),
                         "Source: Web search, Read appointments and Weather.")


class Frage(unittest.TestCase):
    def test_whole_message_only(self):
        for s in ("Woher weißt du das?", "woher hast du das denn", "Spark, was war deine Quelle?", "Quelle?",
                  "Welche Quellen hast du benutzt?", "Wo hast du das her?", "Where did you get that?",
                  "What's your source?", "Nenn mir die Quelle bitte"):
            self.assertTrue(qa.frage(s), s)
        for s in ("Woher stammt die Kartoffel?", "Woher weißt du, dass es regnet?", "Quelle der Donau",
                  "Wie heißt die Quelle der Spree?", "Hallo", ""):
            self.assertFalse(qa.frage(s), s)


class Merken(unittest.TestCase):
    def test_this_profile_this_device_thirty_minutes(self):
        parts = teile([call("web_search", query="Goethe")])
        qa.merke("u1", "web:c1", parts, "", [{"title": "Goethe – Wikipedia", "url": "https://x"}], now=100.0)
        shown, spoken = qa.antwort("u1", "web:c1", now=101.0)
        self.assertIn("• Websuche: Goethe", shown)
        self.assertIn("• Seiten: Goethe – Wikipedia", shown)
        self.assertNotIn("•", spoken)
        self.assertTrue(qa.fremd("u1", "web:c1", now=101.0))     # titles from outside: the answer is marked "outside"
        self.assertIn("Websuche mit „Goethe“", spoken)
        none = "Dazu habe ich keine Quelle mehr"
        self.assertTrue(qa.antwort("u1", "web:c2", now=101.0)[0].startswith(none))   # another device
        self.assertTrue(qa.antwort("u2", "web:c1", now=101.0)[0].startswith(none))   # another profile
        self.assertTrue(qa.antwort("u1", "web:c1", now=100.0 + qa.TTL + 1)[0].startswith(none))
        qa.merke("u1", "web:c1", [], "intern", now=200.0)
        shown, _ = qa.antwort("u1", "web:c1", now=201.0)
        self.assertIn("nichts nachgeschlagen", shown)
        self.assertIn("Achtung: nicht in deinen Daten nachgesehen.", shown)
        self.assertFalse(qa.fremd("u1", "web:c1", now=201.0))
        qa.merke("u1", "web:c1", [], "", [{"title": "[klick](javascript:x) <b>Titel</b>"}], now=300.0)
        self.assertNotIn("[", qa.antwort("u1", "web:c1", now=301.0)[0])       # no markup from a page's title
        self.assertNotIn("<", qa.antwort("u1", "web:c1", now=301.0)[0])

    def test_trace_holds_fixed_words_only(self):
        rec = tracelog.Rec(0, "web")
        rec.source("Websuche, Termine lesen", "intern")
        self.assertEqual((rec.data()["quelle"], rec.data()["qwarn"]), ("Websuche, Termine lesen", "intern"))
        rec.source("Websuche, <script>", "boese")
        self.assertEqual((rec.quelle, rec.qwarn), ("Websuche", ""))


class FakeTurn:
    def __init__(self, uid, org="panel", text="Wer war Goethe?"):
        self.who = {"id": uid}
        self.own_browser = True
        self.mcp = False
        self.hilfe_origin = org
        self.body = {}
        self.carry = None
        self.route = intent.classify(text)
        self.ccfg = features.chat_cfg()


class Gesagt(unittest.TestCase):
    """2a: the short sentence only at spoken channels, with the preference on."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Quellansage")

    def setUp(self):
        helpers.keep_chat(self, "source_note")
        helpers.set_config(source_note=True)
        profiles.save_settings(self.uid, {"quelle_sagen": True})
        self.addCleanup(profiles.save_settings, self.uid, {"quelle_sagen": True})

    def run_line(self, org):
        out, sentences = asyncio.Queue(), asyncio.Queue()
        trace = {"calls": [call("web_search", query="Goethe")], "said": "Goethe war ein Dichter."}
        st = {"acts": [], "links": []}
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            line = asyncio.run(chat_modell.quellenangabe_zeile(
                FakeTurn(self.uid, org), None, st, trace, out, {"id": self.uid}, "x:c1",
                [{"role": "user", "content": "Wer war Goethe?"}], sentences, None, lokal, quellen))
        said = []
        while not sentences.empty():
            said.append(sentences.get_nowait())
        return line, said, log.getvalue()

    def test_spoken_channels_only(self):
        line, said, log = self.run_line("panel")
        self.assertEqual(line["de"], "Quelle: Websuche")
        self.assertEqual(said, [])
        self.assertIn("quelle: Zeile 1 Quellen | Hinweis keiner | nicht gesagt", log)
        self.assertNotIn("Goethe", log)
        line, said, log = self.run_line("speaker")
        self.assertEqual(said, ["Quelle: Websuche."])
        profiles.save_settings(self.uid, {"quelle_sagen": False})
        line, said, _ = self.run_line("telefon")
        self.assertEqual(said, [])                       # the preference off: the line stays, nothing said
        self.assertEqual(line["de"], "Quelle: Websuche")


class Chat(unittest.TestCase):
    """The line under a real answer and „Woher weißt du das?“ without the model."""

    @classmethod
    def setUpClass(cls):
        cls.c, cls.uid = profile("Quellchat")

    def setUp(self):
        helpers.keep_chat(self, "source_note")
        helpers.LLM_CALLS.clear()

    def ask(self, text, c=None):
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            r = (c or self.c).post("/api/chat", json={"messages": [{"role": "user", "content": text}], "convo": "qa1"})
            self.assertEqual(r.status_code, 200, r.text)
            return helpers.events(r), log.getvalue()

    def herk(self, ev):
        return next((e for e in ev if e.get("type") == "herkunft"), None)

    def test_off_by_default(self):
        helpers.set_config(source_note=False)
        self.assertFalse(features.admin_on("quelle"))
        ev, _ = self.ask("Wer war Goethe?")
        self.assertIsNone(self.herk(ev))

    def test_line_and_question_without_the_model(self):
        helpers.set_config(source_note=True)
        ev, log = self.ask("Wer war Goethe?")
        self.assertEqual(self.herk(ev)["de"], "Quelle: nichts nachgeschlagen, nur Modellwissen")
        self.assertIn("quelle: Zeile 0 Quellen", log)
        n = len(helpers.LLM_CALLS)
        ev, log = self.ask("Woher weißt du das?")
        said = "".join(e.get("delta", "") for e in ev if e.get("type") == "text")
        self.assertIn("nichts nachgeschlagen", said)
        self.assertEqual(len(helpers.LLM_CALLS), n)          # the panel answered, the model was not asked
        self.assertIn("quelle: Nachfrage beantwortet", log)

    def test_never_for_guests(self):
        helpers.set_config(source_note=True)
        self.assertFalse(features.allowed(qa.KEY, None))
        self.assertFalse(features.allowed(qa.SAY_KEY, None))


if __name__ == "__main__":
    unittest.main()
