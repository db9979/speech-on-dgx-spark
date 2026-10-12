"""Fewer speech gaps in long answers (V01.0.430): while the LLM still writes it shares the GPU with the speech
engine (~1.2x real time), so the next piece goes to TTS while more audio is left (chat.WRITE_LEAD, times the
speaking rate); once the answer is written the old margin holds. The iPhone app collects a little audio after
it ran dry and starts softly after silence. (ios/ is not in an app/-only copy, then that part is skipped.)
No model, no clock."""
import os
import re
import unittest

from tests import helpers

helpers.start()
import chat  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Margin(unittest.TestCase):
    def test_more_lead_while_writing(self):
        self.assertEqual(chat.piece_margin(0.4, True), chat.WRITE_LEAD)
        self.assertGreater(chat.piece_margin(0.4, True), chat.piece_margin(0.4, False))

    def test_lead_grows_with_the_speaking_rate(self):
        self.assertAlmostEqual(chat.piece_margin(0.4, True, 1.2), chat.WRITE_LEAD * 1.2)
        self.assertEqual(chat.piece_margin(0.4, True, 0.8), chat.WRITE_LEAD)   # slower speech needs no less
        self.assertEqual(chat.piece_margin(0.4, True, 9), chat.WRITE_LEAD * 2)   # capped
        for bad in (None, "", "schnell", [1]):
            self.assertEqual(chat.piece_margin(0.4, True, bad), chat.WRITE_LEAD)

    def test_written_answer_keeps_the_old_margin(self):
        self.assertEqual(chat.piece_margin(0.2, False, 1.2), 1.8)
        self.assertAlmostEqual(chat.piece_margin(2.0, False, 1.2), 5.8)
        self.assertAlmostEqual(chat.piece_margin(3.0, True), 8.3)   # a slow engine start still wins

    def test_answer_marks_when_it_is_written(self):
        with open(chat.__file__) as f:
            src = f.read()
        end = src.index('tm["written"] = True')
        self.assertLess(end, src.index("await sentences.put(None)", end))
        self.assertIn('piece_margin(ttfa, not tm.get("written"), tts_body.get("speed"))', src)


class IPhone(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(ROOT, "ios", "Spark", "Engine.swift")
        if not os.path.isfile(self.path):
            self.skipTest("ios/ is not in an app/-only copy")
        with open(self.path) as f:
            self.src = f.read()

    def test_ran_dry_collects_audio_first(self):
        play = self.src[self.src.index("func play(_ pcm: Data)"):self.src.index("func warmUp()")]
        self.assertIn("let dry = queued == 0 && heard && !holding", play)
        self.assertIn("dry ? Self.rebuffer :", play)
        self.assertTrue(re.search(r"static let rebuffer: TimeInterval = 0\.[2-6]\b", self.src))

    def test_every_answer_starts_fresh(self):
        for fn in ("func warmUp()", "func stopPlaying()"):
            body = self.src[self.src.index(fn):]
            self.assertIn("heard = false", body[:body.index("}")])

    def test_soft_start_after_silence(self):
        play = self.src[self.src.index("func play(_ pcm: Data)"):self.src.index("func warmUp()")]
        self.assertIn("if queued == 0 {", play)
        self.assertIn("Float(i) / Float(Self.fadeIn)", play)


if __name__ == "__main__":
    unittest.main()
