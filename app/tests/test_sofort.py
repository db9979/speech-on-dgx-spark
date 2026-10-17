"""Einfaches sofort beantworten (plan genauer-und-schneller, 6): sofort.answer and its way through /api/chat."""
import datetime
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import sofort  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

NOW = datetime.datetime(2026, 10, 16, 14, 20, tzinfo=datetime.timezone.utc)   # a Friday; never the clock

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


class Rules(unittest.TestCase):
    def test_time_and_date(self):
        self.assertEqual(sofort.answer("Wie spät ist es?", NOW), ("uhrzeit", "Es ist 14 Uhr 20."))
        self.assertEqual(sofort.answer("Welcher Tag ist heute?", NOW), ("datum", "Heute ist Freitag, der 16. Oktober 2026."))
        self.assertEqual(sofort.answer("Der Wievielte ist morgen?", NOW)[1], "Morgen ist Samstag, der 17. Oktober 2026.")
        self.assertEqual(sofort.answer("What day is it today?", NOW, en=True)[1], "Today is Friday, October 16, 2026.")

    def test_arithmetic(self):
        self.assertEqual(sofort.answer("Was ist 17 mal 23?", NOW), ("rechnen", "17 mal 23 ist 391."))
        self.assertEqual(sofort.answer("Wie viel ist 3,5 plus 2", NOW)[1], "3,5 plus 2 ist 5,5.")
        self.assertEqual(sofort.answer("Wie viel ist 120 geteilt durch 7?", NOW)[1], "120 geteilt durch 7 ist etwa 17,14.")
        self.assertEqual(sofort.answer("What is 6 times 7?", NOW, en=True)[1], "6 times 7 is 42.")
        self.assertIsNone(sofort.answer("Was ist 5 durch 0?", NOW))

    def test_units(self):
        self.assertEqual(sofort.answer("Wie viel sind 3 Zoll in Zentimeter?", NOW), ("einheit", "3 Zoll sind etwa 7,6 Zentimeter."))
        self.assertEqual(sofort.answer("Hey Spark, wie viel sind 180 Grad in Fahrenheit?", NOW)[0], "einheit")

    def test_anything_more_goes_to_the_model(self):
        for q in ("Wie spät ist es in Tokio?", "Was ist der Sinn des Lebens?", "Was ist 3 mal 4 und dann mal 5?",
                  "Stell einen Timer auf 10 Minuten", "Welcher Tag ist heute? Und wie wird das Wetter?",
                  "Rechne mir aus, wie viel Miete ich im Jahr zahle", "x" * 90, ""):
            self.assertIsNone(sofort.answer(q, NOW), q)


class Chat(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "sofort")
        helpers.LLM_CALLS.clear()

    def ask(self, p, q):
        r = p.post("/api/chat", json={"messages": [{"role": "user", "content": q}]})
        self.assertEqual(r.status_code, 200, r.text)
        return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")

    def test_on_no_model_is_asked(self):
        helpers.set_config(sofort=True)
        said = self.ask(profile("Sofort1"), "Was ist 17 mal 23?")
        self.assertEqual(said, "17 mal 23 ist 391.")
        self.assertEqual([c for c in helpers.LLM_CALLS if c.get("stream")], [])

    def test_off_the_model_answers(self):
        helpers.set_config(sofort=False)
        self.ask(profile("Sofort2"), "Was ist 17 mal 23?")
        self.assertTrue([c for c in helpers.LLM_CALLS if c.get("stream")])

    def test_blocked_profile_gets_the_model(self):
        helpers.set_config(sofort=True)
        p = profile("Sofort3")
        helpers.keep_chat(self, "deny")
        helpers.set_config(deny={"sofort": [p.get("/api/whoami").json()["profile"]["id"]]})   # the admin blocks it
        self.ask(p, "Was ist 17 mal 23?")
        self.assertTrue([c for c in helpers.LLM_CALLS if c.get("stream")])


if __name__ == "__main__":
    unittest.main()
