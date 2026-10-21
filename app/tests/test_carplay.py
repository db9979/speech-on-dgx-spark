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
        self.assertIn("reachable { Conversation.shared.write(question, hint: hint) }", car)
        reach = body(car, "private func reachable(")
        self.assertIn("await talk.check()", reach)
        self.assertIn('flash("offline")', reach)

    def test_repeat_row(self):
        car = read("CarPlayScene.swift")
        self.assertIn('String(localized: "Letzte Antwort wiederholen")', car)
        self.assertIn("[start, day, repeatRow]", car)
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
        self.assertIn('self.base("Mikrofon stumm")', w)

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



class RoundTwo(unittest.TestCase):
    """Dominik 2026-10-21 „Alles umsetzen, auch 6b“ after the drive whose Ton-Protokoll showed every conversation ending
    right after the answer without a reason."""

    def test_no_barge_in_in_the_car(self):
        a = read("Assistant.swift")
        self.assertIn("guard Prefs.bargeIn, !inCar,", a)

    def test_the_chime_is_not_heard_as_a_question(self):
        # deaf until the chime has really played; a tone never waits the rebuffer time of an answer
        a = read("Assistant.swift")
        self.assertIn("deafUntil = Date().addingTimeInterval(audio.chime() + Self.afterChime)", a)
        e = read("Engine.swift")
        self.assertIn("let dry = queued == 0 && heard && !holding && tone == nil", e)
        self.assertIn("func chime() -> Double", e)

    def test_every_end_in_the_car_has_a_reason(self):
        a = read("Assistant.swift")
        b = body(a, "private func base(")
        self.assertIn('AudioEngine.note("Ende: "', b)
        self.assertIn("Zeile \\(line)", b)   # an end without a reason names its caller
        for why in ("Stille", "fremde Stimme", "Danke gesagt", "Hinweis gesagt", "zu langsam", "Unterbrechung",
                    "Mikrofon stumm", "nichts gehört", "nichts verstanden"):
            self.assertIn(f'"{why}"', a)
        self.assertIn('stop("Auto getrennt")', read("CarPlayScene.swift"))

    def test_an_unknown_voice_is_said(self):
        a = read("Assistant.swift")
        self.assertIn('if text.isEmpty && inCar && !ignored.isEmpty', a)
        self.assertIn('lastEnd = "unknown"', a)
        car = read("CarPlayScene.swift")
        self.assertIn('talk.lastEnd == "unknown" { flash("unknown") }', car)
        self.assertIn('d["ignored"] as? String', read(os.path.join("..", "Shared", "SparkAPI.swift")))

    def test_a_drop_out_does_not_end_the_conversation(self):
        car = read("CarPlayScene.swift")
        gone = body(car, "didDisconnectInterfaceController")
        self.assertIn("Self.away = Task", gone)
        self.assertIn("Task.sleep(for: .seconds(Self.dropOut))", gone)
        self.assertNotRegex(gone.split("Self.away = Task")[0], r"talk\.stop\(")
        self.assertIn("static let dropOut: TimeInterval = 5", car)
        self.assertIn('"CarPlay: wieder da"', car)

    def test_slow_answers_free_the_car(self):
        a = read("Assistant.swift")
        self.assertIn("static let carSlow: TimeInterval = 30", a)
        self.assertIn("self?.tooSlow(id)", body(a, "private func send("))
        slow = body(a, "private func tooSlow(")
        self.assertIn("guard phase == .thinking", slow)
        self.assertIn('base("zu langsam")', slow)
        car = read("CarPlayScene.swift")
        for kind in ('"Mails", hint:', '"Fristen", hint:', '"Termine", hint:', '"MeinTag", hint:'):
            self.assertIn(kind, car)
        self.assertIn("self.phase == .thinking", body(a, "func write("))   # the hint never talks over the answer

    def test_my_day_reminder_and_briefing_rows(self):
        car = read("CarPlayScene.swift")
        self.assertIn('String(localized: "Mein Tag")', car)
        self.assertIn('String(localized: "Erinnerung sprechen")', car)
        self.assertIn("Conversation.shared.allowed.reminders, let remind", car)
        self.assertIn('identifier: "remind"', car)
        self.assertIn("remindNext = true", body(read("Assistant.swift"), "func listenForReminder()"))
        brief = body(car, "private func briefingOnConnect()")
        self.assertIn("guard Prefs.carBriefing, Prefs.carBriefingDay != today", brief)   # off unless chosen, once a day
        self.assertIn("talk.phase == .idle || talk.phase == .waiting", brief)
        self.assertIn('static var carBriefing: Bool { get { d.bool(forKey: "carBriefing") }', read("Phone.swift"))


if __name__ == "__main__":
    unittest.main()
