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
        /// "📷 Brief.jpg": the question was asked about a photo or document (shown, never the read text)
        var label: String?
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
    /// messages from other profiles: nil while they are off for this profile, else the unread count
    @Published var unreadMessages: Int?
    /// a tap on a message notification opens the list
    @Published var showMessages = false
    @Published var allowed = Allowed() {
        didSet { Reader.sendPictures = allowed.images }
    }
    @Published var charging = false
    @Published var speechAllowed = false
    /// CarPlay is connected: short answers, the conversation goes on hands-free, notes are said aloud
    @Published var inCar = false
    /// text read from a photo or document; goes along with every question until removed or a new conversation
    @Published var attachment: Attachment?
    @Published var reading = false
    /// the attachment was stored under "Meine Dokumente" (or is being stored)
    @Published var stored = false
    @Published var storing = false
    /// the Spark cannot be reached (no network, Spark or proxy down): typed questions wait in the outbox
    @Published var unreachable = false
    @Published var outbox: [Outbox.Item] = Outbox.load()

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
    private var wantListen = false
    private var labelShown = false
    private var checking = false
    private let net = NetWatch()
    /// the id under which this conversation is kept in the profile's list (the panel's Protokoll)
    private(set) var convoId = Conversation.newId()

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
        Relay.shared.onDue = { [weak self] text in MainActor.assumeIsolated { self?.local(String(localized: "Erinnerung: \(text)")) } }
        net.onChange = { [weak self] up in
            MainActor.assumeIsolated {
                guard let self else { return }
                if !up { self.unreachable = true } else if self.unreachable { Task { await self.check() } }
            }
        }
    }

    static func newId() -> String {
        "app-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(16).lowercased()
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
        case .idle: return String(localized: "Tippen und sprechen")
        case .waiting: return String(localized: "Sag „\(Prefs.wakeWord.rawValue)“ oder tippe")
        case .listening: return String(localized: "Ich höre zu …")
        case .transcribing: return String(localized: "Erkenne Sprache …")
        case .thinking: return String(localized: "Denke nach …")
        case .speaking: return String(localized: "Spricht … tippen zum Anhalten")
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
        if let a { allowed = a; unreachable = false } else { await check() }
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
        if allowed.ios { await AppleReminders.syncLists() }
        if allowed.proactive && Prefs.speakNotes, let api = SparkAPI.current, let n = try? await api.greet(), await api.notePlayed(n.id) { notes.append(n) }
        if phase == .idle || phase == .waiting { base() }
        if wantListen { wantListen = false; listenNow() }
        flushNext()
    }

    /// Quick start (Action button, Control Center, lock screen, "Spark zuhören"): listen right away.
    func listenNow() {
        notice = nil
        lastActivity = Date()
        guard started else { wantListen = true; return }
        switch phase {
        case .idle, .waiting: tap()
        case .speaking, .thinking, .transcribing:
            stop()
            tap()
        case .listening: break
        }
    }

    func scene(_ p: ScenePhase) {
        foreground = p == .active
        if foreground {
            lastActivity = Date()
            if unreachable { Task { await check() } }
            if allowed.ios && started { Task { await AppleReminders.syncLists() } }
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
                notice = String(localized: "Die Spracherkennung auf dem iPhone kann diese Sprache nicht ohne Internet. Das Weckwort bleibt aus (Einstellungen → Allgemein → Tastatur → Diktat).")
            }
            if phase == .idle || phase == .waiting { base() }
        }
    }

    private func tick() {
        if phase == .waiting && !canWake {
            base()
            notice = String(localized: "Weckwort pausiert, um Akku zu sparen. Tippen startet es wieder.")
        }
        if unreachable { Task { await check() } }
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
        case .idle, .waiting:
            guard !unreachable else {
                // spoken questions need the Spark (it recognizes the speech): check once, else say so
                Task {
                    if await check() { listen(preroll: 0, fromWake: false) }
                    else { error = String(localized: "Spark nicht erreichbar. Schreib die Frage, sie geht raus, sobald er wieder da ist.") }
                }
                return
            }
            listen(preroll: 0, fromWake: false)
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
        fresh()
        attachment = nil
        error = nil
        last = .distantPast
    }

    /// A new conversation: a new id in the list (an attached photo stays until it is removed).
    private func fresh() {
        messages = []
        convoId = Self.newId()
        labelShown = false
    }

    /// Continue a conversation from the list (also one from the panel).
    func resume(_ c: SavedConvo) {
        stop()
        messages = c.msgs.compactMap { d in
            guard let role = d["role"] as? String, role == "user" || role == "assistant",
                  let text = d["content"] as? String else { return nil }
            let mark = d["mail"] as? Bool == true ? "mail" : d["outside"] as? Bool == true ? "outside" : nil
            return Message(role: role, text: text, mark: mark)
        }
        convoId = c.id
        attachment = nil
        labelShown = false
        error = nil
        last = Date()
    }

    func attach(_ a: Attachment) {
        attachment = a
        labelShown = false
        stored = false
        error = nil
    }

    /// The attached document's whole text into the profile's "Meine Dokumente" (only with the panel switch).
    func storeAttachment() async {
        guard let a = attachment, allowed.docs, !storing, let api = SparkAPI.current else { return }
        storing = true
        defer { storing = false }
        do {
            try await api.storeDoc(name: a.name, text: a.text)
            stored = true
            notice = String(localized: "Unter „Meine Dokumente“ gespeichert. Der Spark findet es auch später.")
        } catch {
            fail(error)
        }
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
            self.error = String(localized: "Kein Zugriff aufs Mikrofon. Einstellungen → Spark → Mikrofon.")
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
                notice = Prefs.handsFree ? String(localized: "Nichts gehört, Mikrofon aus. Tippen zum Sprechen.") : nil
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
                    if woke { listen(preroll: 0, fromWake: false) } else { error = String(localized: "Nichts verstanden."); base() }
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
        t.lowercased().range(of: #"^\W*(ja|jawohl|ja bitte|ja,? mach( das)?|okay|ok|yes|yes please|yeah|sure)\W*$"#, options: .regularExpression) != nil
    }

    static func no(_ t: String) -> Bool {
        t.lowercased().range(of: #"^\W*(nein|nee|nö|abbrechen|lass( es)?|no|nope|cancel)\W*$"#, options: .regularExpression) != nil
    }

    // ---------------------------------------------------------------- asking
    func write(_ text: String) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let api = SparkAPI.current else { return }
        lastActivity = Date()
        if unreachable {
            queue(text)
            Task { await check() }
            return
        }
        task?.cancel()
        audio.stopPlaying()
        error = nil
        task = Task { await send(text, api, typed: true) }
    }

    /// typed: a typed question that waits in the outbox when the Spark cannot be reached.
    private func send(_ text: String, _ api: SparkAPI, typed: Bool = false) async {
        if Date().timeIntervalSince(last) > Self.newAfter { fresh() }
        var question = Message(role: "user", text: text)
        if let a = attachment, !labelShown {
            question.label = (a.kind == "photo" ? "📷 " : "📄 ") + (a.name.isEmpty ? String(localized: "Anhang") : a.name)
            labelShown = true
        }
        messages.append(question)
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
        var got = false
        do {
            for try await ev in api.chat(history, car: inCar, attachment: attachment) {
                got = true
                unreachable = false
                switch ev {
                case .text(let t): edit { $0.text += t }
                case .drop(let n): edit { $0.text = String($0.text.dropLast(n)) }
                case .audio(let pcm):
                    audio.play(pcm)
                    phase = .speaking
                case .mark(let m): edit { $0.mark = $0.mark == "mail" ? "mail" : m }
                case .error(let e): error = e
                case .reminderSet(let r):
                    if !allowed.push { Task { await Alarms.add(r) } }
                    // Apple's Reminders only after "Ja" (offered after the answer, like a route)
                    if allowed.ios && offer == nil { offer = PhoneAction.remindOffer(r) }
                case .reminderCancel(let ids):
                    Alarms.remove(ids)
                    AppleReminders.remove(ids)
                case .action(let kind, let target): Task { await propose(kind, target) }
                }
            }
            streamDone = true
            last = Date()
            messages.removeAll { $0.id == answer.id && $0.text.isEmpty }
            save(api)
            if !audio.busy { answered() }
            return
        } catch is CancellationError {
        } catch {
            if typed && !got && NetWatch.offline(error) {
                // nothing came back: the question waits and goes out once the Spark is there again
                messages.removeAll { $0.id == answer.id || $0.id == question.id }
                if question.label != nil { labelShown = false }
                queue(text)
            }
            fail(error)
        }
        messages.removeAll { $0.id == answer.id && $0.text.isEmpty }
    }

    /// The conversation into the profile's list (the photo's or document's text never goes there).
    private func save(_ api: SparkAPI) {
        let msgs: [[String: Any]] = messages.suffix(60).compactMap { m in
            guard !m.text.isEmpty else { return nil }
            var d: [String: Any] = ["role": m.role, "content": m.label.map { $0 + "\n" + m.text } ?? m.text]
            if let mark = m.mark { d[mark] = true }
            return d
        }
        guard let first = messages.first(where: { $0.role == "user" }) else { return }
        let id = convoId
        Task { try? await api.saveConvo(id: id, title: String(first.text.prefix(60)), msgs: msgs) }
    }

    // ---------------------------------------------------------------- without the Spark
    private func queue(_ text: String) {
        if Outbox.add(text) {
            outbox = Outbox.load()
            notice = String(localized: "Gespeichert. Die Frage geht raus, sobald der Spark wieder erreichbar ist.")
        } else {
            error = String(localized: "Es warten schon zehn Fragen. Diese ist nicht gespeichert.")
        }
    }

    /// Is the Spark there? Then the waiting questions go out one by one.
    @discardableResult
    func check() async -> Bool {
        guard let api = SparkAPI.current, !checking else { return !unreachable }
        checking = true
        defer { checking = false }
        do {
            allowed = try await api.hello(timeout: 8)
            unreachable = false
            Task { await refreshMessages() }
            flushNext()
            return true
        } catch {
            if NetWatch.offline(error) { unreachable = true }
            return false
        }
    }

    func refreshMessages() async {
        guard let api = SparkAPI.current else { return }
        if let box = try? await api.messages() { unreadMessages = box.unread } else { unreadMessages = nil }
    }

    /// Sends the oldest waiting question, if the assistant is free.
    @discardableResult
    private func flushNext() -> Bool {
        outbox = Outbox.load()
        guard !unreachable, phase == .idle || phase == .waiting, let api = SparkAPI.current, let item = outbox.first else { return false }
        outbox.removeFirst()
        Outbox.save(outbox)
        task = Task { await send(item.text, api, typed: true) }
        return true
    }

    func dropOutbox() {
        Outbox.clear()
        outbox = []
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
        if !outbox.isEmpty && !unreachable {
            phase = .idle
            if flushNext() { return }
        }
        if Prefs.handsFree || inCar || offer != nil && canWake {
            listen(preroll: 0, fromWake: false)
        } else {
            base()
        }
    }

    private func fail(_ e: Error) {
        if e is CancellationError || (e as? URLError)?.code == .cancelled { return }
        if NetWatch.offline(e) {
            unreachable = true
            error = nil
        } else {
            error = e.localizedDescription
        }
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
            noteSince = max(noteSince, n.t)
            if await api.notePlayed(n.id) { notes.append(n) }   // another device said it already: stay silent
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
        if Date().timeIntervalSince(last) > Self.newAfter { fresh() }
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

    /// "msg-<id>": a message from another profile (messages.py)
    static func messageId(_ info: [AnyHashable: Any]) -> String? {
        guard let k = info["k"] as? String, k.hasPrefix("msg-") else { return nil }
        let id = String(k.dropFirst(4))
        return id.range(of: "^[0-9a-f]{8,32}$", options: .regularExpression) != nil ? id : nil
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent n: UNNotification,
                                withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        // someone else's words are not read aloud by themselves: banner, sound, the count goes up
        if Self.messageId(n.request.content.userInfo) != nil {
            Task { @MainActor in await Conversation.shared.refreshMessages() }
            return done([.banner, .sound])
        }
        guard let text = n.request.content.userInfo["spark"] as? String else { return done([.banner, .sound]) }
        // a reminder of this iPhone: only when no other device played it already
        guard let rid = n.request.content.userInfo["rid"] as? String, let api = SparkAPI.current else {
            DispatchQueue.main.async { self.onDue?(text) }
            return done([.banner, .sound])
        }
        Task {
            let play = await api.played(rid)
            if play { DispatchQueue.main.async { self.onDue?(text) } }
            done(play ? [.banner, .sound] : [])
        }
    }

    /// A tap on a message opens the list; "Antworten" in the notification sends the typed text back.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler done: @escaping () -> Void) {
        guard let mid = Self.messageId(response.notification.request.content.userInfo) else { return done() }
        if let r = response as? UNTextInputNotificationResponse {
            let text = r.userText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty, let api = SparkAPI.current else { return done() }
            Task {
                do {
                    try await api.reply(to: mid, text: String(text.prefix(500)))
                } catch {
                    await Self.tell(String(localized: "Antwort nicht gesendet: \(error.localizedDescription)"))
                }
                done()
            }
            return
        }
        if response.actionIdentifier == UNNotificationDefaultActionIdentifier {
            Task { @MainActor in Conversation.shared.showMessages = true }
        }
        done()
    }

    /// A short local notification when an answer from the notification did not go out.
    private static func tell(_ text: String) async {
        let c = UNMutableNotificationContent()
        c.title = "Spark"
        c.body = text
        try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil))
    }

    /// The "Antworten" field on message notifications (the extension sets the category).
    static func registerCategories() {
        let reply = UNTextInputNotificationAction(identifier: "reply", title: String(localized: "Antworten"), options: [],
                                                  textInputButtonTitle: String(localized: "Senden"),
                                                  textInputPlaceholder: String(localized: "Antwort"))
        UNUserNotificationCenter.current().setNotificationCategories([
            UNNotificationCategory(identifier: "msg", actions: [reply], intentIdentifiers: [], options: [])])
    }
}
