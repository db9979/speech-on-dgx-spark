"""Unit tests for text handling and helpers that need no server."""
import datetime
import unittest

from tests import helpers  # noqa: F401  (sets up paths and a throw-away state directory)
import calendars  # noqa: E402
import homeassistant  # noqa: E402
import recall  # noqa: E402
import textnorm  # noqa: E402


class Text(unittest.TestCase):
    def test_lines_end_with_a_full_stop(self):
        out = textnorm.clean_text("Einkaufsliste\n- Milch\n- Brot")
        for line in out.splitlines():
            self.assertTrue(line.endswith("."), line)

    def test_emoji_and_markdown_removed(self):
        out = textnorm.clean_text("**Hallo** 😀 Welt")
        self.assertNotIn("*", out)
        self.assertNotIn("😀", out)

    def test_language_guess(self):
        self.assertEqual(textnorm.guess_language("Wie spät ist es heute?"), "German")
        self.assertEqual(textnorm.guess_language("What is the weather like and when does the train leave?"), "English")


class HA(unittest.TestCase):
    def test_entry_validation(self):
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "ftp://x", "token": "a" * 40})
        with self.assertRaises(ValueError):
            homeassistant.entry({"url": "http://ha.local:8123", "token": "short"})
        e = homeassistant.entry({"url": "http://ha.local:8123/", "token": ""}, {"token": "k" * 40})
        self.assertEqual((e["url"], e["token"]), ("http://ha.local:8123", "k" * 40))


class Recall(unittest.TestCase):
    def test_parse_facts(self):
        self.assertEqual(recall.parse_facts('```json\n{"facts": ["Ben hat einen Hund.", "x"]}\n```'), ["Ben hat einen Hund."])
        self.assertEqual(recall.parse_facts("kein json"), [])


class Calendar(unittest.TestCase):
    def test_recurring_events_expand(self):
        ics = ("BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:1\nSUMMARY:Sport\n"
               "DTSTART:20261005T180000Z\nDTEND:20261005T190000Z\nRRULE:FREQ=WEEKLY\nEND:VEVENT\nEND:VCALENDAR\n")
        zone = datetime.timezone.utc
        start = datetime.datetime(2026, 10, 1, tzinfo=zone)
        evs = calendars._expand([ics], start, start + datetime.timedelta(days=21), zone, "Test")
        self.assertEqual(len(evs), 3)
        self.assertTrue(all(e["title"] == "Sport" for e in evs))


if __name__ == "__main__":
    unittest.main()
