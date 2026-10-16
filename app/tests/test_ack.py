"""Instant acknowledgement (ack.py, admin chat.instant_ack, off; then on for every profile unless the admin blocks
one under Personen und Geräte → Gesperrte Funktionen; never guests):
a ready-made sentence of what the Spark does now, chosen by fixed rules and played from a recording made once per
voice; kept apart from the answer's first sound. No model, no clock."""
import asyncio
import base64
import os
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import panel  # noqa: E402
import ack  # noqa: E402
import intent  # noqa: E402
import latency  # noqa: E402
import tracelog  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
CLIP = b"\x07\x00" * 1200      # what a recording sounds like here (not what the fake TTS sends)


def profile(name, **settings):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    if settings:
        c.put("/api/profile/settings", json=settings)
    return c


def record_all(tts_body=None, lang="German"):
    for t in ack.all_texts(lang == "English"):
        ack.save(ack.key(tts_body or {}, t, lang), CLIP)


def ask(client, text):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200, r.text
    return helpers.events(r)


class Coverage(unittest.TestCase):
    def test_every_weiche_group_has_sentences(self):
        """A new Weiche group needs its sentences (or a reason in ack.NO_ACK): the list grows with the Spark."""
        for g in intent.GROUPS:
            if g not in ack.NO_ACK:
                self.assertIn(g, ack.PHRASES, f"Weiche group {g!r} has no ready-made sentence in ack.PHRASES")
        for extra in ("lokal", "bridge"):
            self.assertIn(extra, ack.PHRASES)

    def test_sentences_never_say_a_result(self):
        for g, opts in ack.PHRASES.items():
            for de, en in opts:
                for s in (de, en):
                    self.assertLessEqual(len(s), 60, s)
                    self.assertFalse(any(ch.isdigit() for ch in s), s)          # no figures, no times
                    self.assertNotRegex(s.lower(), r"\b(ja|nein|yes|no|erledigt|done|gemacht)\b", s)


class Rules(unittest.TestCase):
    def test_which_sentence(self):
        self.assertEqual(ack.group_of(["kalender"]), "kalender")
        self.assertEqual(ack.group_of(["wetter"]), "wetter")
        self.assertIsNone(ack.group_of(["plaudern"]))                     # small talk: none
        self.assertIsNone(ack.group_of(["smarthome"]))                    # a direct command is quick
        self.assertIsNone(ack.group_of(["kalender", "mail"]))             # two at once: no promise
        self.assertIsNone(ack.group_of(["kalender", "smarthome"]))
        self.assertIsNone(ack.group_of([]))                               # nothing recognised
        self.assertEqual(ack.group_of([], local=True), "lokal")           # "Erst lokal" looks
        self.assertEqual(ack.group_of([], direct="weather"), "wetter")
        self.assertEqual(ack.group_of(["spark"], direct="spark_hilfe"), "spark")

    def test_variants_never_repeat_soon(self):
        """Dominik 2026-10-12: many variants, never monotonous: never one of the profile's last few sentences."""
        said = [ack.phrase("kalender", "turns1") for _ in range(40)]
        for i in range(1, len(said)):
            self.assertNotIn(said[i], said[max(0, i - ack.RECENT):i])
        self.assertGreater(len(set(said)), 5)
        self.assertIsNone(ack.phrase("gibtsnicht", "turns1"))

    def test_only_recorded_ones(self):
        rec = {ack.PHRASES["wetter"][2][0]}
        for _ in range(5):
            self.assertEqual(ack.pick("wetter", "turns2", have=rec.__contains__), ack.PHRASES["wetter"][2][0])
        self.assertIsNone(ack.pick("wetter", "turns2", have=lambda t: False))
        self.assertEqual(ack.pick("wetter", "turns3", english=True, have={"Let me check the weather."}.__contains__),
                         "Let me check the weather.")

    def test_plenty_of_variants(self):
        for g, opts in ack.PHRASES.items():
            self.assertGreaterEqual(len(opts), 5, g)
            self.assertEqual(len({de for de, _ in opts}), len(opts), g)      # no doubles in a group
        self.assertGreaterEqual(len(ack.PHRASES["bridge"]), 8)
        texts = ack.all_texts()
        for opts in ack.PHRASES.values():                                    # each group's first one is recorded early
            self.assertIn(opts[0][0], texts[:len(ack.PHRASES)])
        self.assertLessEqual(2 * len(texts), ack.MAX_CLIPS)                  # both languages of a voice fit

    def test_recording_per_voice(self):
        k1 = ack.key({"voice": "ryan"}, "Moment.", "German")
        k2 = ack.key({"voice": "serena"}, "Moment.", "German")
        k3 = ack.key({"voice": "ryan", "speed": 1.2}, "Moment.", "German")
        self.assertEqual(len({k1, k2, k3}), 3)
        self.assertTrue(ack.save(k1, CLIP))
        self.assertEqual(ack.clip(k1), CLIP)
        self.assertIsNone(ack.clip(k2))
        self.assertIsNone(ack.clip("../../etc/passwd"))                   # only its own names
        self.assertFalse(ack.save(k2, b"\0" * (ack.MAX_CLIP_BYTES + 2)))  # never a long recording
        self.assertEqual(b"".join(base64.b64decode(x) for x in ack.chunks(CLIP)), CLIP)
        self.assertEqual(oct(os.stat(ack._path(k1)).st_mode & 0o777), "0o600")

    def test_record_missing_in_a_pause(self):
        body = {"voice": "ackrec"}
        texts = ["Ich schau in deinen Kalender.", "Moment."]
        got = []

        async def fake(c, url, headers, b):
            got.append((b, headers))
            return CLIP

        with mock.patch.object(ack, "_record", fake), mock.patch("vorrang.speaking", return_value=False):
            made = asyncio.run(ack.record_missing("http://tts", {}, body, "German", texts))
            again = asyncio.run(ack.record_missing("http://tts", {}, body, "German", texts))
        self.assertEqual((made, again), (2, 0))                            # once per voice
        self.assertEqual(got[0][0]["voice"], "ackrec")
        self.assertEqual(got[0][0]["language"], "German")
        self.assertEqual(ack.clip(ack.key(body, "Moment.", "German")), CLIP)

    def test_stats_show_what_went_without(self):
        ack.stats.clear()
        ack.count("kalender", True, now=1_000_000)
        ack.count("unklar", False, now=1_000_000)
        ack.count("unklar", False, now=1_000_000)
        ack.count("bahn", False, now=1_000_000)
        s = ack.today(now=1_000_000)
        self.assertEqual((s["with"], s["without"]), (1, 3))
        self.assertEqual(s["top"][0], {"group": "unklar", "n": 2})

    def test_latency_keeps_it_apart(self):
        try:
            os.remove(latency._file())
        except OSError:
            pass
        latency.add(4.0, now=2_000_000)
        latency.add_ack(0.2, now=2_000_000)
        s = latency.summary(now=2_000_001)
        self.assertEqual(s["day"]["median"], 4.0)                          # the answer's first sound only
        self.assertEqual(s["ack"]["median"], 0.2)

    def test_trace_mark(self):
        self.assertIn("ack", tracelog.MARKS)
        self.assertIn("ack", tracelog.KINDS)


class InTheAnswer(unittest.TestCase):
    def setUp(self):
        helpers.set_config(routing=True, instant_ack=True)
        helpers.LLM_CALLS.clear()
        record_all()

    def tearDown(self):
        helpers.set_config(routing=False, instant_ack=False)

    def audio(self, evs):
        return [base64.b64decode(e["audio"]) for e in evs if e["type"] == "audio"]

    def test_sentence_comes_first_and_apart(self):
        p = profile("Ack1")
        evs = ask(p, "Welche Termine habe ich morgen?")
        sound = self.audio(evs)
        self.assertTrue(sound and sound[0] == CLIP[:ack.CHUNK])            # the recording before anything else
        self.assertTrue(any(e["type"] == "timing" and "first_ack" in e for e in evs))
        self.assertFalse(any(e["type"] == "text" and "Kalender" in e.get("delta", "") for e in evs))   # not in the text

    def test_small_talk_gets_none(self):
        p = profile("Ack2")
        evs = ask(p, "Hallo, wie geht's?")
        self.assertNotIn(CLIP[:ack.CHUNK], self.audio(evs))

    def test_off_for_a_blocked_profile_or_the_spark(self):
        p = profile("Ack3")
        uid = p.get("/api/whoami").json()["profile"]["id"]
        helpers.set_config(deny={"ack": [uid]})                 # the admin blocks this one profile
        self.addCleanup(helpers.set_config, deny={})
        self.assertNotIn(CLIP[:ack.CHUNK], self.audio(ask(p, "Welche Termine habe ich morgen?")))
        helpers.set_config(deny={}, instant_ack=False)
        q = profile("Ack4")
        self.assertNotIn(CLIP[:ack.CHUNK], self.audio(ask(q, "Welche Termine habe ich morgen?")))

    def test_never_guests(self):
        helpers.set_config(public=True)
        try:
            r = TestClient(panel.app).post("/api/chat", json={"messages": [{"role": "user",
                                                                           "content": "Welche Termine habe ich morgen?"}]})
            if r.status_code == 200:
                self.assertNotIn(CLIP[:ack.CHUNK], self.audio(helpers.events(r)))
        finally:
            helpers.set_config(public=False)


if __name__ == "__main__":
    unittest.main()
