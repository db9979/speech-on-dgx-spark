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
        # since the Code-Review of 10.11.2026 (C8) on the iPhone too: after a note never listening, also with Freihändig
        a = read("Assistant.swift")
        self.assertIn("if unasked {", body(a, "private func answered()"))
        self.assertNotIn("unasked && inCar", a)
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
        # only the Spark's fixed word for a foreign voice (fremdstimme.py); silence and echo end quietly (Code-Review B4)
        self.assertIn('if text.isEmpty && inCar && ignored == "foreign voice"', a)
        self.assertEqual(a.count('lastEnd = "unknown"'), 1)
        self.assertIn('"eigenes Echo" : "Stille erkannt"', a)
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
        # since the Code-Review of 10.11.2026 (B5) one watch over every turn, not a timer in send() alone: recognizing the
        # speech, a turn of the game, a note or a repeated answer read aloud and text without sound are limited too
        a = read("Assistant.swift")
        self.assertIn("static let carSlow: TimeInterval = 30", a)
        self.assertNotIn("tooSlow(", body(a, "private func send("))
        self.assertIn("phaseChanged(from: oldValue)", a)
        watch = body(a, "private func phaseChanged(")
        self.assertIn("self.checkTurn()", watch)
        self.assertIn("try? await Task.sleep(for: .seconds(2))", watch)
        self.assertIn("phase == .transcribing || phase == .thinking || phase == .speaking", a)
        check = body(a, "private func checkTurn()")
        self.assertIn("guard inCar, held == nil, !(phase == .speaking && audio.busy) else { return }", check)
        self.assertIn("now.timeIntervalSince(max(turnAt, audio.lastPiece)) > Self.carSlow { tooSlow() }", check)
        self.assertIn("if tone == nil { lastPiece = Date() }", read("Engine.swift"))
        slow = body(a, "private func tooSlow(")
        self.assertIn("guard turnRunning, inCar", slow)
        self.assertIn("task?.cancel()", slow)
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


class DungeonInTheCar(unittest.TestCase):
    """KI-Dungeon-Master per CarPlay (Dominik 2026-10-24, Punkte 8-13): the app only carries the Spark's answers
    (dungeon_auto.py decides everything, test_dungeon_auto), asks back before acting, waits without giving up."""

    def test_only_yes_sends_what_was_said_back(self):
        a = read("Assistant.swift")
        self.assertIn('gameAsk = d["frage"] as? Bool == true ? sent : nil', body(a, "private func tellGame("))
        self.assertIn('if gameAsk != nil && Self.yes(text) { playGame("", confirmed: true); return }', a)
        self.assertIn("if gameAsk != nil && Self.no(text) { gameAsk = nil; sayGame(", a)
        play = body(a, "private func playGame(")
        self.assertIn('if confirmed, let ask = gameAsk { body = ask; body["ok"] = true }', play)
        self.assertEqual(a.count('["ok"] = true'), 1)   # ok is sent nowhere else
        self.assertIn("gameAsk = nil", body(a, "private func base("))

    def test_leaving_the_game(self):
        a = read("Assistant.swift")
        self.assertIn("if inCar && Self.bye(text) || inCar && game && Self.leave(text)", a)
        rx = re.search(r'static func leave\(_ t: String\) -> Bool \{\n\s*t\.lowercased\(\)\.range\(of: #"(.+?)"#', a).group(1)
        for t in ("Pause", "Spiel beenden", "spiel verlassen", "Aufhören.", "leave the game"):
            self.assertRegex(t.lower(), rx)
        for t in ("Ich mache eine Pause am Feuer", "Uma hört auf den Wind", "Kampfstand"):
            self.assertNotRegex(t.lower(), rx)
        car = read("CarPlayScene.swift")
        self.assertIn("talk.leaveGame()", body(car, "didDisconnectInterfaceController"))
        self.assertIn("if !game { endWatch() }", body(a, "private func listen("))

    def test_waiting_never_gives_up_after_ten_minutes(self):
        a = read("Assistant.swift")
        self.assertNotIn("gameMax", a)
        self.assertIn("static let gameLong: TimeInterval = 4 * 3600", a)
        self.assertIn("waitTurn()", body(a, "private func answered()"))
        w = body(a, "private func waitTurn()")
        self.assertIn('base("Spiel wartet")', w)
        self.assertIn("gone < Self.gameQuick ? Self.gamePoll : Self.gameSlowPoll", w)
        self.assertIn("guard self.inCar, gone < Self.gameLong else { break }", w)
        self.assertEqual(w.count("guard self.phase == .idle || self.phase == .waiting else { continue }"), 2)   # never over a question

    def test_the_rounds_own_voices(self):
        a = read("Assistant.swift")
        t = body(a, "private func tellGame(")
        self.assertIn('api.dungeonFile("api/profile/dungeon/\\(rid)/ton/\\(n)/\\(i)")', t)
        self.assertIn('rid.range(of: "^r[0-9a-f]{10}$", options: .regularExpression) != nil', t)
        self.assertIn("(voiced ? [] : Self.pieces(say)) + Self.pieces(after)", t)
        self.assertIn('b[8..<12].elementsEqual("WAVE".utf8)', body(a, "static func pcm("))
        self.assertIn("static func pieces(_ text: String, max: Int = 900)", a)
        allowed = open(os.path.join(APP, "panel", "iphone.py"), encoding="utf-8").read()
        self.assertIn(r'/api/profile/dungeon/r[0-9a-f]{10}/ton/[0-9]{1,4}/[0-9]{1,4}', allowed)

    def test_choosing_a_round_in_the_car(self):
        car = read("CarPlayScene.swift")
        self.assertIn("DungeonModel.runden(d).filter { $0.laeuft && !$0.held.isEmpty }", body(car, "private func playGame()"))
        rows = body(car, "private func gameList(")
        self.assertIn('String(localized: "Neue Runde")', rows)
        self.assertIn('String(localized: "Spiel verlassen")', rows)
        self.assertIn("interface.pushTemplate(sub, animated: true)", rows)
        self.assertIn("reachable { Conversation.shared.startGame(rid, new: new) }", car)
        self.assertIn("runden = Self.runden(d)", read("DungeonView.swift"))   # one parser for the app and the car


class HoerstueckInTheCar(unittest.TestCase):
    """Hörstück in CarPlay (Dominik 2026-11-05): a row while Hörstück is released, the finished ones to listen to, one
    player for the app and the car (HoerstueckPlayer.swift), the sound only in memory, a conversation pauses it."""

    def test_the_row_and_the_list_only_to_listen(self):
        car = read("CarPlayScene.swift")
        rows = body(car, "private func items(")
        self.assertIn('if areas.contains("hoerstueck")', rows)
        self.assertIn('String(localized: "Hörstücke")', rows)
        self.assertLess(rows.index("[start, day, repeatRow]"), rows.index('areas.contains("hoerstueck")'))
        get = body(car, "private func hoerstuecke()")
        self.assertIn('api.object("GET", "api/profile/hoerstuecke")', get)
        self.assertIn(".prefix(12)", get)
        self.assertIn("reachable {", get)
        self.assertIn("interface.pushTemplate(sub, animated: true)", body(car, "private func hsShow("))
        self.assertNotRegex(car, r'"POST"[^\n]*hoerstueck|hoerstuecke/sofort|hoerstueck[^\n]*/telegram')   # nothing is made
        hs = car[car.index("private func hoerstuecke()"):car.index("/// Rückfrage bei unklaren Aktionen")]
        self.assertNotIn("Conversation.shared.write(", hs)
        self.assertNotIn("presentTemplate", hs)   # the voice window only through sync()
        self.assertIn('String(localized: "15 Sekunden zurück")', body(car, "private func hsRows()"))

    def test_the_car_going_away_pauses_and_comes_back(self):
        car = read("CarPlayScene.swift")
        gone = body(car, "didDisconnectInterfaceController")
        self.assertLess(gone.index("HsPlayer.shared.carGone()"), gone.index("Self.away = Task"))
        self.assertIn("if back { HsPlayer.shared.carBack() }", car)
        self.assertIn("watchHs = nil", gone)

    def test_sound_only_in_memory(self):
        p = read("HoerstueckPlayer.swift")
        self.assertIn("AVAudioPlayer(data: data, fileTypeHint: AVFileType.m4a.rawValue)", p)
        self.assertIn("URLSession(configuration: .ephemeral)", p)
        self.assertIn('URLQueryItem(name: "form", value: "m4a")', p)
        for no in ("contentsOf", "FileManager", "write(to:", "download(", "documentDirectory", "cachesDirectory"):
            self.assertNotIn(no, p)
        self.assertNotIn("AVAudioPlayer", read("HoerstueckView.swift").replace("AVFoundation", ""))   # one player only
        self.assertEqual(p.count("static let shared = HsPlayer()"), 1)
        # only the place is kept: the id and whole seconds, never a title
        self.assertIn('$0.id + ":" + String(Int($0.t))', body(p, "private static func store("))

    def test_a_conversation_goes_first(self):
        p = read("HoerstueckPlayer.swift")
        talk = body(p, "private func talk(")
        self.assertIn('pause("Pause für Gespräch")', talk)
        self.assertIn("guard let self, self.heldForTalk, phase == .idle || phase == .waiting", talk)
        self.assertIn('Conversation.shared.giveSound("Hörstück")', body(p, "func play("))
        self.assertIn('Conversation.shared.giveSound("Hörstück")', body(p, "func resume()"))
        self.assertIn("try? s.setCategory(.playback, mode: .spokenAudio)", body(p, "private func session("))
        self.assertIn(".notifyOthersOnDeactivation", body(p, "private func session("))
        a = read("Assistant.swift")
        give = body(a, "func giveSound(")
        self.assertIn("stop(why)", give)
        self.assertIn("audio.sleep()", give)
        self.assertRegex(body(a, "var canWake: Bool"), r"!HsPlayer\.claiming, !inCar else")   # no wake word while it plays
        self.assertIn("if s.category != .playAndRecord", read("Engine.swift"))   # the conversation gets its session back

    def test_now_playing_and_the_buttons(self):
        p = read("HoerstueckPlayer.swift")
        r = body(p, "private func remote()")
        for c in ("playCommand", "pauseCommand", "togglePlayPauseCommand", "skipForwardCommand", "skipBackwardCommand",
                  "nextTrackCommand", "previousTrackCommand", "changePlaybackPositionCommand"):
            self.assertIn("cc." + c, r)
        self.assertIn("static let skip: Double = 15", p)
        self.assertIn("MPMediaItemPropertyAlbumTitle: s.mappe", body(p, "private func info()"))
        self.assertIn("oldDeviceUnavailable", p)   # the car or the headphones gone: pause
        notes = re.findall(r'AudioEngine\.note\(([^\n]*)\)', p)
        self.assertGreaterEqual(len(notes), 6)
        for n in notes:
            self.assertRegex(n, r'^(why|"[^"\\]*"( \+ why)?|[^"]*\? "[^"\\]*" : "[^"\\]*")$')   # fixed words only


class CodeReview(unittest.TestCase):
    """Code-Review of 10.11.2026, package P3 „iPhone und CarPlay“ (Dominik: „1a, Rest nach Empfehlung“): one rule each,
    findings B1-B13 of review-b-carplay, A-H2 (pairing anew) and C8 (a note after Stopp)."""

    def test_a_cancelled_turn_never_listens_again(self):
        # B1: a cancelled AsyncThrowingStream ends without an error; send(), sayNote(), tellGame() and repeatLast() check
        a = read("Assistant.swift")
        send = body(a, "private func send(")
        loop_end = send.index("streamDone = true", send.index("for try await ev in api.chat("))
        self.assertIn("guard !Task.isCancelled else {", send[send.index("for try await ev in api.chat("):loop_end])
        note = body(a, "private func sayNote()")
        self.assertLess(note.index("guard !Task.isCancelled else { return }"), note.index("answered()"))
        tell = body(a, "private func tellGame(")
        self.assertLess(tell.rindex("guard !Task.isCancelled else { return }"), tell.index("streamDone = true"))
        rep = body(a, "func repeatLast()")
        self.assertLess(rep.index("guard !Task.isCancelled else { return }"), rep.index("answered()"))
        # the car's short sentence is a task of its own, stopped with the turn
        self.assertIn("hintTask = Task {", body(a, "func write("))
        self.assertIn("!Task.isCancelled, self.phase == .thinking", body(a, "func write("))
        self.assertIn("hintTask?.cancel()", body(a, "func stop("))
        # a Spark call rings or runs: no microphone after an answer
        self.assertIn('if CallCenter.shared.active { base("Anruf"); return }', body(a, "private func answered()"))

    def test_the_sound_is_let_go_also_when_the_engine_stood(self):
        # B2: sleep() gives the session back without a running engine, and a failed listen() ends through base()
        e = body(read("Engine.swift"), "func sleep()")
        self.assertIn("engine.isRunning || !sleeping else { return }", e)
        self.assertNotRegex(e, r"guard engine\.isRunning,")
        self.assertIn("setActive(false, options: .notifyOthersOnDeactivation)", e)
        self.assertLess(e.index("if running {"), e.index("setActive(false"))
        listen = body(read("Assistant.swift"), "private func listen(")
        fail = listen[listen.index("do { try audio.startInput() } catch {"):listen.index("if preroll == 0")]
        self.assertIn('base(denied ? "Mikrofon fehlt" : "Mikrofon belegt")', fail)
        self.assertNotIn("phase = .idle", fail)

    def test_one_question_list_and_no_stale_button(self):
        # B3: one list of the open Rückfrage, replaced or taken away, each button carries the number of its question
        car = read("CarPlayScene.swift")
        self.assertNotIn("$gameChoices.removeDuplicates()", car)
        ch = body(car, "private func choices(")
        self.assertIn("choiceSub = nil", ch)
        self.assertIn("interface.popToRootTemplate(", ch)
        show = body(car, "private func showChoices(")
        self.assertIn("let n = talk.gameChoiceN", show)
        self.assertEqual(show.count("Conversation.shared.answerGame("), 2)
        self.assertEqual(len(re.findall(r"answerGame\([^\n]*, n\)", show)), 2)
        self.assertIn("talk.gameChoices == c", show)
        gone = body(car, "didDisconnectInterfaceController")
        self.assertIn("watchChoices = nil", gone)
        self.assertIn("choiceSub = nil", gone)
        a = read("Assistant.swift")
        self.assertIn("guard game, n == gameChoiceN, !gameChoices.isEmpty else", body(a, "func answerGame("))
        self.assertIn("gameChoiceN += 1", body(a, "private func tellGame("))
        self.assertIn("if !gameChoices.isEmpty { gameChoices = [] }", body(a, "private func playGame("))   # answered by voice
        self.assertIn("if !gameChoices.isEmpty { gameChoices = [] }", body(a, "private func base("))
        # the round and Hörstück lists only on top of the main list: a second tap lays no second one
        self.assertIn("interface.topTemplate === list", body(car, "private func gameList("))
        self.assertIn("interface.topTemplate === root", body(car, "private func hsShow("))

    def test_the_apps_words_are_the_sparks(self):
        # B4: the app compares fixed words of the Spark, never free text; they must stay these words there
        root = os.path.join(ROOT, "app", "panel")
        with open(os.path.join(root, "fremdstimme.py"), encoding="utf-8") as f:
            self.assertIn('return "foreign voice", v', f.read())
        with open(os.path.join(root, "echo.py"), encoding="utf-8") as f:
            src = f.read()
        for w in ('"own voice"', '"speaking pause"'):
            self.assertIn("return " + w, src)
            self.assertIn("ignored == " + w, read("Assistant.swift"))

    def test_sound_that_never_comes_back_ends_the_turn(self):
        # B6: shouldResume decides, a successful start ends an interruption without an end, stalled pieces end the turn
        e = read("Engine.swift")
        self.assertIn("AVAudioSession.InterruptionOptions.shouldResume.rawValue", e)
        self.assertIn("if lost { self.onLost?() }", e)
        self.assertIn("if interrupted { interrupted = false;", body(e, "func ensureRunning()"))
        self.assertIn("var stalled: Bool { queued > 0 && !engine.isRunning }", e)
        a = read("Assistant.swift")
        self.assertIn("static let soundStall: TimeInterval = 15", a)
        check = body(a, "private func checkTurn()")
        self.assertIn("if audio.stalled && held == nil {", check)
        self.assertIn('stop("Ton hängt")', check)
        self.assertIn('stop("Unterbrechung")', body(a, "private func soundLost()"))

    def test_a_phone_call_keeps_the_pieces_and_says_the_right_thing(self):
        # B7: pieces wait while the sound is taken, a busy microphone is not a refused one
        play = body(read("Engine.swift"), "func play(")
        keep = play[play.index("do { try ensureRunning() } catch {"):play.index("let dry =")]
        self.assertIn("guard interrupted else { return 0 }", keep)
        self.assertIn("pending.append((nextId, buffer))", keep)
        self.assertIn("AVAudioApplication.shared.recordPermission == .granted", read("Engine.swift"))
        listen = body(read("Assistant.swift"), "private func listen(")
        self.assertIn("let denied = !AudioEngine.microphoneGranted", listen)
        self.assertIn('String(localized: "Das Mikrofon ist gerade belegt', listen)

    def test_reachable_only_while_the_car_is_there_and_one_check(self):
        # B8: after the check the car must still be there; a running check is waited for, never the old state
        reach = body(read("CarPlayScene.swift"), "private func reachable(")
        self.assertIn("guard let self, self.interface != nil else", reach)
        self.assertLess(reach.index("await talk.check()"), reach.index("self.interface != nil"))
        check = body(read("Assistant.swift"), "func check() async -> Bool")
        self.assertIn("if let running = checkTask { return await running.value }", check)
        self.assertNotIn("checking", read("Assistant.swift"))

    def test_wake_word_restarts_only_its_own_recognition(self):
        # B10: the late callback of a cancelled recognition never restarts the new one
        w = read("WakeWord.swift")
        self.assertIn("DispatchQueue.main.async { self?.handle(result, error, g) }", w)
        self.assertIn("guard running, g == gen else { return }", w)
        self.assertIn("guard let self, self.running, self.gen == g else { return }", w)

    def test_the_voice_window_is_never_stuck_moving(self):
        # B11: a completion that never comes frees the window; a late one does not end a newer step
        car = read("CarPlayScene.swift")
        self.assertIn("static let moveWait: TimeInterval = 3", car)
        start = body(car, "private func startMove()")
        self.assertIn("guard let self, self.moving, self.moveN == n else { return }", start)
        self.assertIn('AudioEngine.note("CarPlay: Sprachfenster ohne Antwort")', start)
        moved = body(car, "private func moved(")
        self.assertIn("guard n == moveN else { return }", moved)
        self.assertIn("refused = 0   // given up for now", moved)
        self.assertEqual(body(car, "private func sync()").count("startMove()"), 2)

    def test_the_tap_keeps_its_own_converter(self):
        # B12: the audio thread never reads a property the main thread changes
        e = read("Engine.swift")
        self.assertNotIn("private var converter", e)
        tap = body(e, "func startInput()")
        self.assertIn("let converter = AVAudioConverter(from: format, to: target)", tap)
        self.assertIn("let raw = onRaw", tap)
        self.assertIn("raw?(buf)", tap)
        self.assertNotIn("self.onRaw", tap)

    def test_the_car_alone_starts_the_assistant(self):
        # B13: the car started the app alone: begin() (tick, microphone question); without the microphone a clear state
        car = read("CarPlayScene.swift")
        self.assertIn("Task { await talk.begin(nil) }", car)
        self.assertIn('CPVoiceControlState(identifier: "mic"', car)
        self.assertIn('String(localized: "Mikrofon in der App erlauben")', car)
        self.assertIn('flash("mic")', body(car, "private func micAllowed()"))
        self.assertIn("guard micAllowed() else { return }", body(car, "private func begin("))
        self.assertIn("guard micAllowed() else { return }", body(car, "private func remindMe()"))
        b = body(read("Assistant.swift"), "func begin(")
        self.assertLess(b.index("timer = Timer.scheduledTimer"), b.index("await AudioEngine.microphoneAllowed()"))

    def test_no_note_right_after_stop(self):
        # C8: „Stopp“ is quiet for a while, the waiting note comes later and never opens the microphone
        a = read("Assistant.swift")
        self.assertIn("quietUntil = Date().addingTimeInterval(Self.quietAfterStop)", body(a, "func stop("))
        self.assertIn("guard !notes.isEmpty, Date() >= quietUntil,", body(a, "private func sayNote()"))

    def test_pairing_anew_leaves_nothing_of_the_old_profile(self):
        # A-H2: another profile or Spark: conversation, outbox, keychain and kept data go; the old key's push addresses
        # are dropped on the Spark and the new key gets them
        c = body(read("Conversation.swift"), "func pair(")
        self.assertIn("Task { await before.forgetPush() }", c)
        other = c[c.index("if before != nil && (link.replacing != nil || r.profile != Store.profile) {"):c.index("Store.baseURL = link.base")]
        for step in ("ChatSec.shared.forget()", "Merken.forget()", "AppleReminders.forget()",
                     "Conversation.shared.dropOutbox()", "Conversation.shared.restart()"):
            self.assertIn(step, other)
        self.assertLess(c.index("ChatSec.shared.forget()"), c.index("Store.profile = r.profile"))   # named after the old one
        self.assertIn("CallCenter.shared.resendToken()", c)
        self.assertIn('post("api/iphone/push-token", ["forget": true])', read(os.path.join("..", "Shared", "SparkAPI.swift")))
        self.assertIn("registry?.pushToken(for: .voIP)", body(read("Calls.swift"), "func resendToken()"))


if __name__ == "__main__":
    unittest.main()
