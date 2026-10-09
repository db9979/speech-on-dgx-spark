import Foundation
import SwiftUI
import UIKit
import UserNotifications

/// The assistant: listens (button, hands-free or wake word), asks the Spark, speaks the answer,
/// says notes by itself, rings for reminders and offers routes and calls.
@MainActor
final class Conversation: ObservableObject {
    struct Message: Identifiable {
        let id = UUID()
        let role: String
        var text: String
        var mark: String?
    }

    enum Phase: Equatable { case idle, waiting, listening, transcribing, thinking, speaking }

    static let newAfter: TimeInterval = 600     // a pause this long starts a new conversation
    static let endSilence: TimeInterval = 0.8   // quiet after speech that ends a question
    static let giveUp: TimeInterval = 8         // nothing said: the microphone goes off (as in the panel)
    static let maxQuestion: TimeInterval = 30

    @Published var messages: [Message] = []
    @Published var phase: Phase = .idle
    @Published var error: String? { didSet { if error != nil { errorAt = Date() } } }
    @Published var notice: String?
    @Published var level: Float = 0
    @Published var offer: PhoneAction.Offer?
    @Published var allowed = Allowed()
    @Published var charging = false
    @Published var speechAllowed = false
    /// CarPlay is connected: short answers, the conversation goes on hands-free, notes are said aloud
    @Published var inCar = false

    /// One assistant for the phone screen and CarPlay.
    static let shared = Conversation()

    let audio = AudioEngine()
    let wake = WakeWord()
    private var task: Task<Void, Never>?
    private var pcm: [Int16] = []
    private var ring: [Int16] = []
    private var heard = false
    private var fromWake = false
    private var startedAt = Date()
    private var lastLoud = Date()
    private var loudSince: Date?
    private var floor: Float = 0.02
    private var streamDone = true
    private var last = Date.distantPast
    private var lastActivity = Date()
    private var errorAt = Date.distantPast
    private var notes: [Note] = []
    private var noteSince = Int(Date().timeIntervalSince1970 * 1000)
    private var timer: Timer?
    private var foreground = true
    private var started = false

    init() {
        let w = wake
        audio.onRaw = { w.feed($0) }
        audio.onInput = { [weak self] s, l in MainActor.assumeIsolated { self?.input(s, l) } }
        audio.onIdle = { [weak self] in MainActor.assumeIsolated { self?.played() } }
        wake.onWake = { [weak self] in MainActor.assumeIsolated { self?.woke() } }
        UIDevice.current.isBatteryMonitoringEnabled = true
        charging = Self.onPower()
        NotificationCenter.default.addObserver(forName: UIDevice.batteryStateDidChangeNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.charging = Self.onPower()
                if self.charging { self.lastActivity = Date() }
                if self.phase == .idle || self.phase == .waiting { self.base() }
            }
        }
        Relay.shared.onDue = { [weak self] text in MainActor.assumeIsolated { self?.local("Erinnerung: " + text) } }
    }

    static func onPower() -> Bool {
        let s = UIDevice.current.batteryState
        return s == .charging || s == .full
    }

    // ---------------------------------------------------------------- what the face and the page show
    var mood: FaceMood {
        if Date().timeIntervalSince(errorAt) < 5 && (phase == .idle || phase == .waiting) { return .sad }
        switch phase {
        case .idle: return .idle
        case .waiting: return .waiting
        case .listening: return .listen
        case .transcribing, .thinking: return .think
        case .speaking: return .speak
        }
    }

    var status: String {
        switch phase {
        case .idle: return "Tippen und sprechen"
        case .waiting: return "Sag „\(Prefs.wakeWord.rawValue)“ oder tippe"
        case .listening: return "Ich höre zu …"
        case .transcribing: return "Erkenne Sprache …"
        case .thinking: return "Denke nach …"
        case .speaking: return "Spricht … tippen zum Anhalten"
        }
    }

    /// The wake word may listen: the app's switch, the profile allows it, recognition on the iPhone,
    /// and on battery only for a while after the last use.
    var canWake: Bool {
        guard Prefs.wake, allowed.listen, speechAllowed, wake.onDevice else { return false }
        if charging { return true }
        return Prefs.batteryMinutes > 0 && Date().timeIntervalSince(lastActivity) < Double(Prefs.batteryMinutes) * 60
    }

    var standing: Bool { Prefs.stand && charging }

    // ---------------------------------------------------------------- start, foreground, background
    func begin(_ a: Allowed?) async {
        if let a { allowed = a }
        if !started {
            started = true
            _ = await AudioEngine.microphoneAllowed()
            timer = Timer.scheduledTimer(withTimeInterval: 20, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.tick() }
            }
        }
        if Prefs.wake && allowed.listen { speechAllowed = await WakeWord.authorize() }
        // Apple push: the Spark reaches the closed app; reminders then come from there, not as local alarms
        if allowed.push, await Alarms.allow() { UIApplication.shared.registerForRemoteNotifications() }
        await syncAlarms()
        if allowed.proactive && Prefs.speakNotes, let api = SparkAPI.current, let n = try? await api.greet() { notes.append(n) }
        if phase == .idle || phase == .waiting { base() }
    }

    func scene(_ p: ScenePhase) {
        foreground = p == .active
        if foreground {
            lastActivity = Date()
            if phase == .idle || phase == .waiting { base() }
        } else if !canWake && !inCar {
            // no listening in the background unless the wake word is on
            if phase == .listening || phase == .waiting { stop() }
        }
    }

    func settingsChanged() {
        objectWillChange.send()
        Task {
            if Prefs.wake && allowed.listen && !speechAllowed { speechAllowed = await WakeWord.authorize() }
            if Prefs.wake && allowed.listen && !wake.onDevice {
                notice = "Die Spracherkennung auf dem iPhone kann kein Deutsch ohne Internet. Das Weckwort bleibt aus (Einstellungen → Allgemein → Tastatur → Diktat)."
            }
            if phase == .idle || phase == .waiting { base() }
        }
    }

    private func tick() {
        if phase == .waiting && !canWake {
            base()
            notice = "Weckwort pausiert, um Akku zu sparen. Tippen startet es wieder."
        }
        if allowed.proactive && Prefs.speakNotes && (foreground || phase == .waiting || inCar) { Task { await pollNotes() } }
    }

    // ---------------------------------------------------------------- resting state
    /// Waiting for the wake word, or quiet.
    private func base() {
        loudSince = nil
        if canWake {
            do {
                try audio.startInput()
                wake.word = Prefs.wakeWord
                if !wake.running { wake.start() }
                phase = .waiting
            } catch {
                self.error = error.localizedDescription
                phase = .idle
            }
        } else {
            wake.stop()
            audio.stopInput()
            level = 0
            phase = .idle
        }
        if !notes.isEmpty { sayNote() }
    }

    func tap() {
        notice = nil
        lastActivity = Date()
        switch phase {
        case .idle, .waiting: listen(preroll: 0, fromWake: false)
        case .listening: finish()
        default: stop()
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        audio.stopPlaying()
        streamDone = true
        pcm = []
        base()
    }

    func restart() {
        stop()
        messages = []
        error = nil
        last = .distantPast
    }

    // ---------------------------------------------------------------- listening
    private func woke() {
        guard phase == .waiting else { return }
        lastActivity = Date()
        listen(preroll: 1.5, fromWake: true)
    }

    private func listen(preroll: Double, fromWake: Bool) {
        error = nil
        wake.stop()
        do { try audio.startInput() } catch {
            self.error = "Kein Zugriff aufs Mikrofon. Einstellungen → Spark → Mikrofon."
            phase = .idle
            return
        }
        if preroll == 0 && !fromWake { audio.chime() }
        pcm = preroll > 0 ? Array(ring.suffix(Int(AudioEngine.rate * preroll))) : []
        heard = preroll > 0
        self.fromWake = fromWake
        startedAt = Date()
        lastLoud = Date()
        phase = .listening
    }

    private func input(_ samples: [Int16], _ lvl: Float) {
        level = lvl
        ring.append(contentsOf: samples)
        if ring.count > Int(AudioEngine.rate * 2) { ring.removeFirst(ring.count - Int(AudioEngine.rate * 2)) }
        let threshold = max(0.06, floor * 2.5)
        if lvl < threshold { floor = lvl < floor ? floor * 0.9 + lvl * 0.1 : floor * 0.995 + lvl * 0.005 }
        let now = Date()
        switch phase {
        case .listening:
            pcm.append(contentsOf: samples)
            if lvl > threshold { heard = true; lastLoud = now }
            if heard && now.timeIntervalSince(lastLoud) > Self.endSilence { finish() }
            else if !heard && now.timeIntervalSince(startedAt) > Self.giveUp {
                pcm = []
                notice = Prefs.handsFree ? "Nichts gehört, Mikrofon aus. Tippen zum Sprechen." : nil
                base()
            } else if now.timeIntervalSince(startedAt) > Self.maxQuestion { finish() }
        case .speaking:
            // talking over the answer stops it (iOS takes the Spark's own voice out of the microphone)
            guard Prefs.bargeIn, Prefs.handsFree || canWake, lvl > max(threshold * 1.6, 0.18) else { loudSince = nil; return }
            if loudSince == nil { loudSince = now }
            if let s = loudSince, now.timeIntervalSince(s) > 0.35 {
                loudSince = nil
                task?.cancel()
                audio.stopPlaying()
                streamDone = true
                listen(preroll: 0.6, fromWake: false)
            }
        default:
            break
        }
    }

    private func finish() {
        let wav = AudioEngine.wav(pcm)
        let wasHeard = heard
        pcm = []
        level = 0
        guard wasHeard, let api = SparkAPI.current else { base(); return }
        if !(Prefs.handsFree || canWake) { audio.stopInput() }
        phase = .transcribing
        let woke = fromWake
        task = Task {
            do {
                var text = try await api.transcribe(wav: wav, language: Store.language)
                guard !Task.isCancelled else { return }
                if woke { text = wake.strip(text) }
                if text.isEmpty {
                    if woke { listen(preroll: 0, fromWake: false) } else { error = "Nichts verstanden."; base() }
                    return
                }
                // a route or a call waits for "Ja": decided here on the iPhone, nothing else counts as yes
                if let o = offer {
                    if Self.yes(text) { offer = nil; PhoneAction.run(o); base(); return }
                    if Self.no(text) { offer = nil; base(); return }
                }
                await send(text, api)
            } catch {
                fail(error)
            }
        }
    }

    static func yes(_ t: String) -> Bool {
        t.lowercased().range(of: #"^\W*(ja|jawohl|ja bitte|ja,? mach( das)?|okay|ok)\W*$"#, options: .regularExpression) != nil
    }

    static func no(_ t: String) -> Bool {
        t.lowercased().range(of: #"^\W*(nein|nee|nö|abbrechen|lass( es)?)\W*$"#, options: .regularExpression) != nil
    }

    // ---------------------------------------------------------------- asking
    func write(_ text: String) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let api = SparkAPI.current else { return }
        task?.cancel()
        audio.stopPlaying()
        error = nil
        lastActivity = Date()
        task = Task { await send(text, api) }
    }

    private func send(_ text: String, _ api: SparkAPI) async {
        if Date().timeIntervalSince(last) > Self.newAfter { messages = [] }
        messages.append(Message(role: "user", text: text))
        let answer = Message(role: "assistant", text: "")
        messages.append(answer)
        phase = .thinking
        streamDone = false
        // earlier answers made from mail or outside text keep their mark, so the Spark keeps its locks
        let history: [[String: Any]] = messages.dropLast().suffix(20).map { m in
            var d: [String: Any] = ["role": m.role, "content": m.text]
            if let mark = m.mark { d[mark] = true }
            return d
        }
        func edit(_ change: (inout Message) -> Void) {
            if let i = messages.firstIndex(where: { $0.id == answer.id }) { change(&messages[i]) }
        }
        do {
            for try await ev in api.chat(history, car: inCar) {
                switch ev {
                case .text(let t): edit { $0.text += t }
                case .drop(let n): edit { $0.text = String($0.text.dropLast(n)) }
                case .audio(let pcm):
                    audio.play(pcm)
                    phase = .speaking
                case .mark(let m): edit { $0.mark = $0.mark == "mail" ? "mail" : m }
                case .error(let e): error = e
                case .reminderSet(let r): if !allowed.push { Task { await Alarms.add(r) } }
                case .reminderCancel(let ids): Alarms.remove(ids)
                case .action(let kind, let target): Task { await propose(kind, target) }
                }
            }
            streamDone = true
            last = Date()
            if !audio.busy { answered() }
        } catch is CancellationError {
        } catch {
            fail(error)
        }
        messages.removeAll { $0.id == answer.id && $0.text.isEmpty }
    }

    private func propose(_ kind: String, _ target: String) async {
        let (o, msg) = await PhoneAction.offer(kind: kind, target: target)
        if let o { offer = o } else if let msg { error = msg }
    }

    private func played() {
        if phase == .speaking && streamDone { answered() }
    }

    /// After an answer: hands-free listens again (also for "Ja"), else back to rest.
    private func answered() {
        lastActivity = Date()
        if Prefs.handsFree || inCar || offer != nil && canWake {
            listen(preroll: 0, fromWake: false)
        } else {
            base()
        }
    }

    private func fail(_ e: Error) {
        if e is CancellationError || (e as? URLError)?.code == .cancelled { return }
        error = e.localizedDescription
        streamDone = true
        base()
    }

    // ---------------------------------------------------------------- reminders and notes
    func syncAlarms() async {
        if allowed.push { await Alarms.sync([]); return }   // they come as push now: no double ringing
        guard allowed.reminders, let api = SparkAPI.current, let list = try? await api.reminders() else { return }
        await Alarms.sync(list)
    }

    private func pollNotes() async {
        guard let api = SparkAPI.current, let items = try? await api.notes(since: noteSince) else { return }
        for n in items where !notes.contains(where: { $0.id == n.id }) {
            notes.append(n)
            noteSince = max(noteSince, n.t)
        }
        if phase == .idle || phase == .waiting { sayNote() }
    }

    /// A reminder that is due while the app is open: said aloud too.
    private func local(_ text: String) {
        notes.append(Note(id: UUID().uuidString, t: 0, text: text, mail: false))
        if phase == .idle || phase == .waiting { sayNote() }
    }

    private func sayNote() {
        guard !notes.isEmpty, let api = SparkAPI.current else { return }
        let n = notes.removeFirst()
        if Date().timeIntervalSince(last) > Self.newAfter { messages = [] }
        // like the panel: a note counts as outside text for the next turn
        messages.append(Message(role: "assistant", text: n.text, mark: n.mail ? "mail" : "outside"))
        last = Date()
        wake.stop()
        phase = .speaking
        streamDone = false
        task = Task {
            do {
                for try await pcm in api.say(n.text) { audio.play(pcm) }
            } catch {}
            streamDone = true
            if !audio.busy { answered() }
        }
    }
}

/// Notifications that arrive while the app is open: shown and also said.
final class Relay: NSObject, UNUserNotificationCenterDelegate {
    static let shared = Relay()
    var onDue: ((String) -> Void)?

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent n: UNNotification,
                                withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        if let text = n.request.content.userInfo["spark"] as? String {
            DispatchQueue.main.async { self.onDue?(text) }
        }
        done([.banner, .sound])
    }
}
