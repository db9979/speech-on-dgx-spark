"""CarPlay stabil (Dominik 2026-10-20: the assistant ended itself or switched away, rows stayed selected and did nothing;
then „1a 2a 3a 4a 5a“). Static checks of the iPhone app's sources, one per rule; outside app/ they skip in the
app/-only copy the Spark tests. No wall clock dependence."""
import os
import re
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
IOS = os.path.join(ROOT, "ios", "Spark")


def read(name):
    path = os.path.join(IOS, name)
    if not os.path.exists(path):
        raise unittest.SkipTest(f"ios/Spark/{name} is not in this copy (the Spark tests only app/)")
    with open(path, encoding="utf-8") as f:
        return f.read()


def body(src, head):
    """The function starting with `head`, up to its closing brace at four spaces."""
    s = src[src.index(head):]
    return s[:s.index("\n    }\n")]


class VoiceWindow(unittest.TestCase):
    def test_present_and_dismiss_one_at_a_time(self):
        car = read("CarPlayScene.swift")
        sync = body(car, "private func sync()")
        # CarPlay itself says whether the window is up, never an own flag; the next step waits for the completion
        self.assertIn("interface.presentedTemplate === voice", sync)
        self.assertIn("!moving", sync)
        self.assertRegex(sync, r"presentTemplate\(voice, animated: true\) \{ \[weak self\] ok, _ in")
        self.assertRegex(sync, r"dismissTemplate\(animated: true\) \{ \[weak self\] ok, _ in")
        self.assertNotIn("private var shown", car)
        self.assertNotRegex(car, r"(present|dismiss)Template\([^)]*completion: nil\)")
        moved = body(car, "private func moved(")
        self.assertIn("moving = false", moved)
        self.assertIn("refused < 3", moved)   # a refused step is tried again, but not forever

    def test_errors_show_before_the_list_comes_back(self):
        car = read("CarPlayScene.swift")
        for state in ('"offline"', '"fail"', '"none"'):
            self.assertIn(f"CPVoiceControlState(identifier: {state}", car)
        show = body(car, "private func show(")
        self.assertIn('flash("offline")', show)
        self.assertIn('flash("fail")', show)
        self.assertIn("later(0.8)", show)


class Rows(unittest.TestCase):
    def test_every_row_answers_at_once_and_acts(self):
        car = read("CarPlayScene.swift")
        handlers = re.findall(r"\.handler = \{[^\n]*\n\s*(\S[^\n]*)", car)
        self.assertGreaterEqual(len(handlers), 6)
        self.assertEqual(set(handlers), {"done()"})   # the row lets go first, never stays spinning
        begin = body(car, "private func begin(")
        self.assertIn("talk.stop()", begin)   # also while Spark speaks or thinks
        self.assertIn("reachable", begin)

    def test_no_question_from_the_car_waits_in_the_outbox(self):
        car = read("CarPlayScene.swift")
        self.assertEqual(car.count("Conversation.shared.write("), 1)
        self.assertIn("reachable { Conversation.shared.write(question) }", car)
        reach = body(car, "private func reachable(")
        self.assertIn("await talk.check()", reach)
        self.assertIn('flash("offline")', reach)

    def test_repeat_row(self):
        car = read("CarPlayScene.swift")
        self.assertIn('String(localized: "Letzte Antwort wiederholen")', car)
        self.assertIn("[start, repeatRow, fresh]", car)
        self.assertIn("unasked = true", body(read("Assistant.swift"), "func repeatLast()"))


class Sound(unittest.TestCase):
    def test_the_car_lets_go_of_the_sound(self):
        a = read("Assistant.swift")
        self.assertIn("guard !foreground || inCar,", body(a, "private func sleepAudio()"))
        self.assertIn("else if phase == .idle { sleepAudio() }", body(a, "private func played()"))

    def test_a_silent_microphone_does_not_listen_forever(self):
        a = read("Assistant.swift")
        self.assertIn("watchInput(startedAt)", body(a, "private func listen("))
        self.assertIn("lastInput = Date()", body(a, "private func input("))
        w = body(a, "private func watchInput(")
        self.assertIn("self.audio.startInput()", w)
        self.assertIn("self.base()", w)

    def test_listening_again_after_an_interruption(self):
        e = read("Engine.swift")
        self.assertIn("self.onInterrupt?(!ended)", e)
        self.assertIn("!self.interrupted", body(e, "private func watchStopped()"))
        a = read("Assistant.swift")
        self.assertIn("listenAfter = inCar", body(a, "private func interrupted("))


class Use(unittest.TestCase):
    def test_no_microphone_after_a_note_in_the_car(self):
        a = read("Assistant.swift")
        self.assertIn("if unasked && inCar", body(a, "private func answered()"))
        self.assertIn("unasked = true", body(a, "private func sayNote()"))
        self.assertIn("unasked = false", body(a, "private func send("))

    def test_no_wake_word_in_the_car(self):
        self.assertRegex(body(read("Assistant.swift"), "var canWake: Bool"), r"guard Prefs\.wake,[^\n]*!inCar else")

    def test_saying_thanks_ends(self):
        a = read("Assistant.swift")
        self.assertIn("if inCar && Self.bye(text)", a)
        rx = re.search(r'static func bye\(_ t: String\) -> Bool \{\n\s*t\.lowercased\(\)\.range\(of: #"(.+?)"#', a).group(1)
        for t in ("Danke.", "danke schön", "Vielen Dank!", "Ende", "Tschüss", "Das war's", "Stopp", "Thanks", "that's all"):
            self.assertRegex(t.lower(), rx)
        for t in ("Danke, und wie wird das Wetter?", "Ende der Woche Termine?", "stopp die Musik"):
            self.assertNotRegex(t.lower(), rx)

    def test_a_tone_at_the_end(self):
        self.assertIn("func endTone(sad: Bool)", read("Engine.swift"))
        a = read("Assistant.swift")
        self.assertIn("audio.endTone(sad: sad)", body(a, "private func carEnd("))
        self.assertIn("carEnd(sad: true)", body(a, "private func fail("))


class Diary(unittest.TestCase):
    def test_carplay_steps_are_kept_with_fixed_words(self):
        e = read("Engine.swift")
        self.assertIn('UserDefaults.standard.set(diary, forKey: diaryKey)', e)
        car = read("CarPlayScene.swift")
        notes = re.findall(r'AudioEngine\.note\(([^\n]*)\)', car)
        self.assertGreaterEqual(len(notes), 6)
        for n in notes:
            # only fixed words and the fixed names of states, buttons and directions, never what was said
            self.assertNotRegex(n, r"question|text|error|localized")


if __name__ == "__main__":
    unittest.main()
