"""Appointments in the morning greeting (Dominik, 2026-10-11): "Guten Morgen" read yesterday's appointments
out of the conversation as today's, the calendar was only asked after he complained.

- "Guten Morgen" alone is a request for the day: the Weiche files it under the calendar and the first round
  must call daily_briefing (chat.MORNING, chat.NEED_TOOLS, chat_turn force).
- An appointment that has ended is marked "(already over)" in every calendar result (calendars.line).
- In an answer that read the calendar, the answer check takes times, dates and quoted titles only from this
  answer's question and results, never from earlier answers (answercheck.fresh, answercheck.unquoted).
No model, no clock.
"""
import datetime
import unittest
from zoneinfo import ZoneInfo

from tests import helpers

helpers.start()
import panel  # noqa: E402
import answercheck  # noqa: E402
import calendars  # noqa: E402
import chat  # noqa: E402
import intent  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
ZONE = ZoneInfo("Europe/Berlin")
OFFERED = {"daily_briefing", "calendar_events", "calendar_add", "home_assistant", "web_search"}


def profile(name):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


class MorningGreeting(unittest.TestCase):
    def test_greeting_needs_the_briefing(self):
        for text in ("Guten Morgen", "Guten Morgen, Spark!", "guten morgen spark, wie gehts?", "Good morning",
                     "Schönen Morgen zusammen"):
            self.assertIn("daily_briefing", chat.needed(text, OFFERED), text)
            self.assertEqual(intent.classify(text).names, ["kalender"], text)
        # without the briefing on offer: today's calendar at least
        self.assertEqual(chat.needed("Guten Morgen", {"calendar_events", "web_search"}), ["calendar_events"])
        # "morgen" as tomorrow, or a greeting before another request, is not the briefing
        for text in ("Morgen fahre ich weg", "Guten Morgen, mach das Licht im Wohnzimmer an", "Hallo", "Danke"):
            self.assertNotIn("daily_briefing", chat.needed(text, OFFERED), text)
        self.assertEqual(chat.needed("Termine im Kalender, guten Morgen", {"calendar_events"}), ["calendar_events"])

    def test_first_round_must_read_the_day(self):
        a = profile("Morgenmensch")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        calendars.add(uid, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                            "user": "m", "password": "pw"}))
        helpers.LLM_CALLS.clear()
        old = [{"role": "user", "content": "Was steht heute an?"},
               {"role": "assistant", "content": "Du hast „deBug & Coffee“ und „Addi Maintrail“ ab 18:30 Uhr."},
               {"role": "user", "content": "Guten Morgen"}]
        r = a.post("/api/chat", json={"messages": old, "tz": "Europe/Berlin"})
        self.assertEqual(r.status_code, 200, r.text)
        first = next(c for c in helpers.LLM_CALLS if c.get("stream"))
        self.assertEqual(first.get("tool_choice"), {"type": "function", "function": {"name": "daily_briefing"}})
        self.assertIn("veraltet", first["messages"][0]["content"] + first["messages"][-1]["content"])


class BriefingByName(unittest.TestCase):
    """Dominik 2026-10-20 at the phone: „Morgenbriefing“ as one word went to no group (and „Was ist mein
    Morgenbriefing?“ to the Spark-Hilfe), so no tool ran and the model made up the day."""

    def test_the_word_alone_needs_the_briefing(self):
        for text in ("Morgenbriefing", "Gib mir mein Morgenbriefing", "Was ist mein Morgenbriefing?", "Tagesbriefing bitte",
                     "Mach mir das Morgen-Briefing", "Lies mir mein Briefing vor", "Was steht heute an?"):
            self.assertIn("daily_briefing", chat.needed(text, OFFERED), text)
            self.assertEqual(intent.classify(text).names, ["kalender"], text)
        # about the function itself it stays the Spark-Hilfe
        for text in ("Was ist das Morgenbriefing?", "Wie stelle ich das Morgenbriefing ein?"):
            self.assertEqual(intent.classify(text).names, ["spark"], text)

    def test_first_round_reads_the_day(self):
        a = profile("Briefingmensch")
        uid = a.get("/api/whoami").json()["profile"]["id"]
        calendars.add(uid, calendars.entry({"name": "Privat", "url": f"http://127.0.0.1:{helpers.CAL_PORT}/dav/",
                                            "user": "m", "password": "pw"}))
        helpers.LLM_CALLS.clear()
        r = a.post("/api/chat", json={"messages": [{"role": "user", "content": "Gib mir mein Morgenbriefing"}],
                                      "tz": "Europe/Berlin"})
        self.assertEqual(r.status_code, 200, r.text)
        first = next(c for c in helpers.LLM_CALLS if c.get("stream"))
        self.assertEqual(first.get("tool_choice"), {"type": "function", "function": {"name": "daily_briefing"}})


class EndedAppointments(unittest.TestCase):
    def test_marked_over(self):
        day = datetime.datetime(2026, 10, 11, tzinfo=ZONE)
        coffee = {"start": day.replace(hour=8), "end": day.replace(hour=9), "allday": False, "title": "deBug & Coffee",
                  "location": "", "calendar": ""}
        trail = {"start": day.replace(hour=18, minute=30), "end": day.replace(hour=20), "allday": False,
                 "title": "Addi Maintrail", "location": "", "calendar": ""}
        whole = {"start": day, "end": day + datetime.timedelta(days=1), "allday": True, "title": "Martin Hartung",
                 "location": "", "calendar": ""}
        now = day.replace(hour=12)
        self.assertTrue(calendars.line(coffee, now).endswith("(already over)"))
        self.assertNotIn("already over", calendars.line(trail, now))
        self.assertNotIn("already over", calendars.line(whole, now))     # all day: still today
        self.assertNotIn("already over", calendars.line(coffee))         # no time given: unchanged
        self.assertIn("already over", chat.BRIEFING_HINT)
        self.assertIn("already over", chat.BRIEF_SYSTEM)


class BriefingParts(unittest.TestCase):
    def test_module_without_briefing_is_skipped(self):
        # roomfar has no briefing(): every briefing wrote "roomfar: briefing AttributeError" (Dominik, 2026-10-11)
        import asyncio
        import contextlib
        import io
        import extras
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            asyncio.run(extras.briefing("nobody", ZONE))
        self.assertNotIn("AttributeError", out.getvalue())
        self.assertFalse(hasattr(extras.roomfar, "briefing"))


class AnswerCheckCalendar(unittest.TestCase):
    MSGS = [{"role": "system", "content": "Aktuelles Datum und Uhrzeit: Sonntag, 11. Oktober 2026, 07:05 Uhr."},
            {"role": "user", "content": "Was steht heute an?"},
            {"role": "assistant", "content": "Du hast „deBug & Coffee“ im Büro und „Addi Maintrail“ ab 18:30 Uhr."},
            {"role": "user", "content": "Guten Morgen"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
                                                                   "function": {"name": "daily_briefing"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "Today's appointments:\nSo 11.10. ganztägig: Martin Hartung\n"
                                                              "Tomorrow's appointments:\nMo 12.10. 09:00–10:00: Zahnarzt"},
            {"role": "user", "content": answercheck.RETRY_NOTE}]

    def test_old_appointments_held_back(self):
        texts = [m.get("content") for m in self.MSGS]
        have = answercheck.known(texts)
        self.assertEqual(answercheck.unsupported("Addi Maintrail ab 18:30 Uhr.", have), [])   # the old check let it by
        fresh = answercheck.fresh(self.MSGS, have)
        self.assertEqual(answercheck.unsupported("„Addi Maintrail“ ab 18:30 Uhr.", fresh), [("t", 18, 30)])
        for ok in ("Heute ist Sonntag, der 11. Oktober.", "Morgen um 9 Uhr hast du den Zahnarzt.",
                   "Es ist 07:05 Uhr."):
            self.assertEqual(answercheck.unsupported(ok, fresh), [], ok)
        now = answercheck.fresh_texts(self.MSGS)
        self.assertEqual(answercheck.unquoted("Du hast „deBug & Coffee“ im Büro.", now), ["deBug & Coffee"])
        self.assertEqual(answercheck.unquoted("Heute steht „Martin Hartung“ ganztägig an.", now), [])
        self.assertEqual(answercheck.label(answercheck.OLD), "Termin aus früherer Antwort")


if __name__ == "__main__":
    unittest.main()
