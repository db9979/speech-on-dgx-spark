"""Spark-Hilfe quality (plan plaene/hilfe-besser.md 8 and 10, V01.0.343): about 60 everyday questions, each with the
answer it must find among the first three hits and where the Weiche must send it. Questions about the Spark go to
the help (fixed rules, before the model is asked), questions about the person's own data stay with their tools.
Then where a question came from: the page of the face, the channel (speaker, Telegram, apps, MCP), the "?" at a
switch. Nothing here asks a model or depends on the wall clock.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402,F401
import hilfe  # noqa: E402
import intent  # noqa: E402

# (question, page, expected title part among the first three hits, expected route: "spark", a data group or None)
CASES = (
    ("Wie bekomme ich schnellere Antworten?", None, "Schnelle", "spark"),
    ("Wie richte ich den zweiten Anmeldeschritt ein?", None, "Zweiter Anmeldeschritt", "spark"),
    ("Wie verbinde ich Home Assistant?", None, "Home Assistant", "spark"),
    ("Wie lade ich jemanden ein?", None, "einladen", "spark"),
    ("Warum antwortet der Assistent nicht auf Hey Spark?", None, "Hey Spark", "spark"),
    ("Wie füge ich meinen Kalender hinzu?", None, "Kalender", "spark"),
    ("Was bedeutet Vorab holen bei Rückfrage?", None, "Vorab holen", "spark"),
    ("Wie stelle ich die Stimme um?", None, "Stimme", "spark"),
    ("Was ist der Notaus?", None, "Notaus", "spark"),
    ("Was ist Mein Notaus?", None, "Mein Notaus", "spark"),
    ("Wie bekomme ich Mails vorgelesen?", None, "E-Mail", "spark"),
    ("Wie mache ich ein Backup?", None, "Sicherung", "spark"),
    ("Welche Einstellungen empfiehlst du für mich?", None, "Tipp", "spark"),
    ("Wie verbinde ich die iPhone App?", None, "iPhone-App", "spark"),
    ("wo sehe ich die logs", None, "Logs", "spark"),
    ("Wie lerne ich dem Spark meine Stimme?", None, "Sprechererkennung", "spark"),
    ("Wie schalte ich die Websuche an?", None, "Websuche", "spark"),
    ("Was ist die Gezielte Werkzeugwahl?", None, "Gezielte Werkzeugwahl", "spark"),
    ("Wie benutze ich den reMarkable?", None, "reMarkable", "spark"),
    ("Wie richte ich Telegram ein?", None, "Telegram", "spark"),
    ("Was ist der Raummodus?", None, "Raum-Modus", "spark"),
    ("Wie richte ich eigene MCP-Dienste ein?", None, "Eigene MCP-Dienste", "spark"),
    ("Wie verbinde ich die Pebble?", None, "Pebble", "spark"),
    ("Wie richte ich einen ESP32-Lautsprecher ein?", None, "ESP32", "spark"),
    ("Was ist Von selbst?", None, "Von selbst", "spark"),
    ("Wie funktioniert das Weckwort?", None, "Hey Spark", "spark"),
    ("Wie schalte ich die Sprechererkennung ein?", None, "Sprechererkennung", "spark"),
    ("Wie nutze ich Kiwix?", None, "Kiwix", "spark"),
    ("Was bedeutet Erst lokal suchen?", None, "Erst lokal suchen", "spark"),
    ("Wie richte ich Passkeys ein?", None, "Passkeys", "spark"),
    ("Wie installiere ich die Android-App?", None, "Android-App", "spark"),
    ("Was ist die Schreibhilfe?", None, "Schreibhilfe", "spark"),
    ("Wie benutze ich den Spark als MCP-Server?", None, "MCP-Server", "spark"),
    ("Wie stelle ich die Antwortlänge ein?", None, "Antwortlänge", "spark"),
    ("Wie aktiviere ich das Tagesbriefing?", None, "Tagesbriefing", "spark"),
    ("Wo sehe ich die Live-Übersicht?", None, "Live", "spark"),
    ("Wie richte ich die Einkaufsliste ein?", None, "Einkaufsliste", "spark"),
    ("Wie ändere ich meine PIN?", None, "PIN ändern", "spark"),
    ("Wie ändere ich mein Passwort?", None, "PIN ändern", "spark"),
    ("Wie spiele ich ein Update ein?", None, "Update", "spark"),
    ("Wie mache ich den Spark sicherer?", None, "sicherer", "spark"),
    ("Wie verbinde ich Wyoming?", None, "Wyoming", "spark"),
    ("Wie schalte ich Funktionen vorschlagen ein?", None, "Funktionen vorschlagen", "spark"),
    ("Was kannst du alles?", None, None, "spark"),
    # asked through the face on a page: the page itself first
    ("Was macht dieser Schalter hier?", "feat", "Funktionen", "spark"),
    ("Was kann ich hier einstellen?", "me/setbox", "Ich → Gespräch", "spark"),
    ("Wieso ist Vorab holen bei mir ausgegraut?", "me/setbox", "Vorab holen", "spark"),
    ("Was zeigt mir diese Seite?", "mon", "Zustand", None),
    ("Wo sehe ich die Logs?", "mon", "Logs", "spark"),
    # English
    ("How do I connect Home Assistant?", None, "Home Assistant", "spark"),
    ("Where are the logs?", None, "logs", None),
    ("How do I invite someone?", None, "Inviting", "spark"),
    ("What is the emergency stop?", None, None, "spark"),
    # the person's own data: not the help
    ("Wie wird das Wetter morgen?", None, None, "wetter"),
    ("Mach das Licht im Wohnzimmer an", None, None, "smarthome"),
    ("Wo ist mein Paket?", None, None, "paket"),
    ("Was steht heute im Kalender?", None, None, "kalender"),
    ("Wo finde ich meinen Termin morgen?", None, None, "kalender"),
    ("Was ist mein Morgenbriefing?", None, None, "kalender"),
    ("Was habe ich morgen vor?", None, None, "kalender"),
    ("Wie spät ist es?", None, None, "-spark"),
    ("Warum ist die Banane krumm?", None, None, "-spark"),
    ("Wie mache ich Pfannkuchen?", None, None, "-spark"),
    ("Erzähl mir einen Witz", None, None, "-spark"),
)


class Quality(unittest.TestCase):
    def test_about_sixty_questions(self):
        self.assertGreaterEqual(len(CASES), 60)

    def test_each_question_finds_its_answer_and_its_way(self):
        bad = []
        for q, page, title, route in CASES:
            lang = "en" if q.split()[0] in ("How", "Where", "What") else "de"
            if title:
                hits = [h["title"] for h in hilfe.search(q, lang, page, n=3, level="admin")]
                if not any(title.lower() in h.lower() for h in hits):
                    bad.append(f"{q}: {title} not in {hits}")
            if route:
                names = intent.classify(q).names
                to_help = hilfe.page_rule(page, q, names) if page else False
                if route == "spark" and "spark" not in names and not to_help:
                    bad.append(f"{q}: Weiche {names}, not the help")
                elif route == "-spark" and "spark" in names:
                    bad.append(f"{q}: Weiche sends it to the help")
                elif route not in ("spark", "-spark") and (route not in names or "spark" in names):
                    bad.append(f"{q}: Weiche {names}, expected {route}")
        self.assertEqual(bad, [])

    def test_a_profile_finds_its_own_ways_only(self):
        for q in ("Wie ändere ich meine PIN?", "Wie richte ich Passkeys ein?", "Was ist Mein Notaus?"):
            hits = hilfe.search(q, "de", None, n=3, level="profile")
            self.assertTrue(hits, q)
            for h in hits:
                self.assertNotIn(h["kind"], ("setting",), q)
        # the admin's frequent questions stay with the admin
        self.assertFalse([h for h in hilfe.search("Wie mache ich ein Backup?", "de", None, n=5, level="profile")
                          if h["kind"] == "faq" and "Sicherung" in h["title"]])


class Origin(unittest.TestCase):
    """Where a question came from (plan 10): only from what the panel knows, never from the question."""

    class Req:
        def __init__(self, headers=None, scope=None):
            self.headers = headers or {}
            self.scope = scope or {}

    def test_the_channel_comes_from_the_panel_not_the_question(self):
        r = self.Req()
        self.assertEqual(hilfe.origin({}, r), "panel")
        self.assertEqual(hilfe.origin({"page": "chat"}, r), "panel")
        self.assertEqual(hilfe.origin({"page": "feat"}, r), "kopf")
        self.assertEqual(hilfe.origin({"page": "../etc"}, r), "panel")
        for c in ("telegram", "speaker", "watch", "siri", "mcp"):
            self.assertEqual(hilfe.origin({"client": c, "page": "feat"}, r), c)
        self.assertEqual(hilfe.origin({"client": "root"}, r), "panel")
        self.assertEqual(hilfe.origin({}, self.Req(scope={"speech_mcp": True})), "mcp")
        ua = "Mozilla/5.0 (Linux; Android 15; wv) SparkAndroid/1.0.0"
        self.assertEqual(hilfe.origin({}, self.Req(headers={"user-agent": ua})), "android")

    def test_a_page_rule_sends_setting_pages_to_the_help_and_keeps_data(self):
        self.assertTrue(hilfe.page_rule("feat", "Was macht das?", []))
        self.assertTrue(hilfe.page_rule("me/setbox", "Und das hier?", []))
        self.assertFalse(hilfe.page_rule("me/setbox", "Wie wird das Wetter morgen?", ["wetter"]))
        self.assertTrue(hilfe.page_rule("mon", "Warum ist das rot?", []))
        self.assertFalse(hilfe.page_rule("mon", "Erzähl mir einen Witz", []))
        self.assertFalse(hilfe.page_rule("chat", "Was macht das?", []))
        self.assertFalse(hilfe.page_rule(None, "Was macht das?", []))

    def test_the_way_is_written_as_the_person_sees_it(self):
        self.assertEqual(hilfe.way("Funktionen → Websuche", "panel"), "Funktionen → Websuche")
        self.assertEqual(hilfe.way("Funktionen → Websuche", "panel", app=True), "Verwalten → Funktionen → Websuche")
        self.assertEqual(hilfe.way("Funktionen → Websuche", "android"), "Verwalten → Funktionen → Websuche")
        self.assertEqual(hilfe.way("Ich → Gespräch", "android"), "Ich → Gespräch")
        self.assertIn("im Panel im Browser", hilfe.way("Ich → Gespräch", "iphone"))
        self.assertIn("im Panel im Browser", hilfe.way("Ich → Gespräch", "telegram"))
        self.assertTrue(hilfe.app_view({"view": "app"}))
        self.assertFalse(hilfe.app_view({"view": "<b>"}))

    def test_the_answer_says_where_it_was_asked_and_how_to_answer_there(self):
        q = "Wie schalte ich die Websuche an?"
        spoken = hilfe.answer_text(q, None, "admin", org="speaker")
        self.assertIn("Gefragt über: Lautsprecher", spoken)
        self.assertIn("zum Vorlesen", spoken)
        import live   # the Live page gets the channel and the count, never the question
        last = [e for e in live._events if e[1] == "Spark-Hilfe"][-1][2]
        self.assertTrue(last.startswith("Frage über Lautsprecher"), last)
        self.assertNotIn("Websuche", last)
        text = hilfe.answer_text(q, None, "admin", page="feat", org="kopf")
        self.assertIn("Gefragt über: Kopf auf einer Seite", text)
        self.assertIn("Seite: Funktionen", text)
        self.assertIn("Weg genau", text)
        self.assertIn("umschalten geht nur im Panel", hilfe.answer_text(q, None, "admin", org="telegram"))
        # over MCP a program asks: no help offered at all
        self.assertIsNone(hilfe.offer({"who": {"id": "x"}, "own": True, "client": "mcp"}))

    def test_a_question_mark_at_a_switch_puts_that_switch_first(self):
        self.assertIsNone(hilfe.focus_of({"focus": "sw:../x"}, None))
        self.assertIsNone(hilfe.focus_of({"focus": "<script>"}, None))
        hits = hilfe.search("Was macht „Gezielte Werkzeugwahl“ und wie steht es bei mir?", "de", "feat", n=3,
                            level="admin", focus="sw:chat.routing")
        self.assertIn("Gezielte Werkzeugwahl", hits[0]["title"])


if __name__ == "__main__":
    unittest.main()
