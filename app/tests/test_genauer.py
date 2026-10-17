"""Assistent genauer und schneller (plan genauer-und-schneller.md): measuring per kind of question (latency.MEASURE),
the cap for answers that are only heard (chat.answer_tokens) and the names for the speech recognition (hoerwoerter)."""
import json
import os
import unittest
from types import SimpleNamespace

from tests import helpers  # noqa: F401  (sets up paths and a throw-away state directory)
import chat  # noqa: E402
import esp32  # noqa: E402
import features  # noqa: E402
import hoerwoerter  # noqa: E402
import latency  # noqa: E402
import profiles  # noqa: E402

NOW = 2_000_000_000


class Measure(unittest.TestCase):
    def setUp(self):
        self.old = latency._load()
        with open(latency._file(), "w") as f:
            json.dump([], f)
        self.addCleanup(self._back)

    def _back(self):
        with open(latency._file(), "w") as f:
            json.dump(self.old, f)

    def test_only_fixed_words_and_numbers_are_kept(self):
        latency.add(2.0, "web", now=NOW, measure={"g": "kalender", "n": 5, "r": 2, "h": 80, "f": 1.234, "e": 4.0,
                                                    "v": "V01.0.750", "q": "Wann ist mein Termin?"})
        latency.add(2.0, "web", now=NOW, measure={"g": "Wann ist mein Termin?", "n": -1, "h": 300, "v": "evil", "e": True})
        good, bad = latency._load()[-2:]
        self.assertEqual({k: good[k] for k in "gnrhfev"}, {"g": "kalender", "n": 5, "r": 2, "h": 80, "f": 1.23, "e": 4.0,
                                                           "v": "V01.0.750"})
        self.assertNotIn("q", good)
        self.assertEqual(set(bad), {"t", "a", "c"})   # nothing of the nonsense, never a question's text

    def test_per_group_and_per_version(self):
        for i in range(4):
            latency.add(1.0 + i, "web", now=NOW - 60, measure={"g": "wetter", "h": 90, "v": "V01.0.750"})
            latency.add(5.0 + i, "speaker", now=NOW - 60, measure={"g": "unklar", "n": 37, "h": 40, "v": "V01.0.749"})
        latency.add(9.0, "web", now=NOW - 8 * 86400, measure={"g": "mail", "v": "V01.0.740"})   # older than 7 days
        s = latency.summary(now=NOW)
        self.assertEqual([r["group"] for r in s["groups"]], ["unklar", "wetter"])   # slowest first, mail too old
        self.assertEqual(s["groups"][0]["tools"], 37)
        self.assertEqual(s["groups"][1]["cache"], 90)
        self.assertEqual([r["version"] for r in s["versions"]], ["V01.0.750", "V01.0.749", "V01.0.740"])
        self.assertEqual(s["versions"][0]["median"], 2.5)

    def test_the_answer_keeps_its_measure(self):
        turn = SimpleNamespace(route=SimpleNamespace(label=lambda: "kalender"), tools=[{}, {}])
        tm = {"rounds": [{"first": 101.0, "usage": {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 750}}},
                         {"first": None, "usage": {"prompt_tokens": 1000}}], "audio": 102.5}
        chat.note_wait(turn, tm, 100.0, "speaker", end=106.0)
        chat.note_wait(turn, tm, 100.0, "speaker", end=106.0)   # once per answer
        rows = latency._load()
        self.assertEqual(len(rows), 1)
        self.assertEqual({k: rows[0][k] for k in "acgnrhfe"},
                         {"a": 2.5, "c": "speaker", "g": "kalender", "n": 2, "r": 2, "h": 38, "f": 1.0, "e": 6.0})
        chat.note_wait(turn, {"rounds": [], "audio": None}, 100.0, "web")   # no sound: nothing
        self.assertEqual(len(latency._load()), 1)


class SpokenAnswers(unittest.TestCase):
    def test_only_heard_answers_are_capped(self):
        c = {"max_tokens": 4096}
        for client in chat.SPOKEN_ONLY:
            self.assertEqual(chat.answer_tokens(c, {"client": client}), chat.SPOKEN_MAX_TOKENS)
        self.assertEqual(chat.answer_tokens(c, {"client": "app"}, car=True), chat.SPOKEN_MAX_TOKENS)
        self.assertEqual(chat.answer_tokens(c, {"client": "web"}), 4096)
        self.assertEqual(chat.answer_tokens({"max_tokens": 300}, {"client": "speaker"}), 300)   # never more than the admin's


class Names(unittest.TestCase):
    def setUp(self):
        self.saved = (profiles.names, features.allowed, hoerwoerter._contacts)
        profiles.names = lambda: [{"id": "u1", "name": "Dominik", "call": "Dom"}, {"id": "u2", "name": "Anke", "call": ""}]
        features.allowed = lambda key, uid, c=None, s=None: True
        hoerwoerter._contacts = lambda uid, cfg: ["Herr Meier", "Anke", "1234"]
        hoerwoerter._cache["u1"] = (10 ** 12, ["Arbeitszimmer", "Whirlpool"])   # fresh: no background read

    def tearDown(self):
        profiles.names, features.allowed, hoerwoerter._contacts = self.saved
        hoerwoerter._cache.pop("u1", None)

    def test_off_gives_nothing(self):
        self.assertEqual(hoerwoerter.words({"chat": {"hoer_namen": False}}, "u1"), [])
        self.assertEqual(hoerwoerter.prompt({"chat": {}, "asr": {"context": "Spark"}}, "u1"), "Spark")

    def test_own_profile_gets_rooms_devices_and_contacts(self):
        cfg = {"chat": {"hoer_namen": True}, "asr": {"context": "GB10"}}
        self.assertEqual(hoerwoerter.words(cfg, "u1"), ["Dominik", "Anke", "Dom", "Arbeitszimmer", "Whirlpool", "Herr Meier"])
        p = hoerwoerter.prompt(cfg, "u1", extra="Hey Spark.")
        self.assertTrue(p.startswith("Hey Spark. Dominik, Anke"), p)
        self.assertTrue(p.endswith("GB10"), p)
        self.assertLessEqual(len(hoerwoerter.prompt(cfg, "u1", extra="x" * 2000)), hoerwoerter.MAX_CHARS)

    def test_shared_speaker_never_gets_contacts(self):
        cfg = {"chat": {"hoer_namen": True}, "asr": {}}
        self.assertNotIn("Herr Meier", hoerwoerter.words(cfg, "u1", shared=True))
        self.assertEqual(hoerwoerter.words(cfg, None, shared=True), ["Dominik", "Anke", "Dom"])

    def test_not_released_means_not_read(self):
        features.allowed = lambda key, uid, c=None, s=None: key not in ("ha", "contacts")
        hoerwoerter._contacts = self.saved[2]
        self.assertEqual(hoerwoerter.words({"chat": {"hoer_namen": True}, "asr": {}}, "u1"), ["Dominik", "Anke", "Dom"])

    def test_speaker_uses_the_admins_language(self):
        f = esp32._asr_form({"chat": {"hoer_namen": False}, "asr": {"default_language": "German"}})
        self.assertEqual(f, {"language": "German", "response_format": "json"})
        f = esp32._asr_form({"chat": {"hoer_namen": True}, "asr": {}})
        self.assertEqual(f["language"], "auto")
        self.assertIn("Anke", f["prompt"])


if __name__ == "__main__":
    unittest.main()
