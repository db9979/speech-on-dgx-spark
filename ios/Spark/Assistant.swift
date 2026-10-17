import Foundation
import SwiftUI
import UIKit
import UserNotifications

/// The assistant: listens (button, hands-free or wake word), asks the Spark, speaks the answer,
/// says notes by itself, rings for reminders and offers routes and calls.
@MainActor
final class Conversation: ObservableObject {
    struct Message: Identifiable {
        /// stays the same when the conversation is caught up from the Spark (catchUp), so the bubbles keep their place
        var id = UUID()
        let role: String
        var text: String
        var mark: String?
        /// "📷 Brief.jpg": the question was asked about a photo or document (shown, never the read text)
        var label: String?
        /// 👍/👎 (Einstellungs-Assistent): the id the Spark gave this answer, and the vote once given
        var rateId: String?
        var rated: Bool?
        /// a picture painted for this answer (bilder.py): its job, and its prompt for the conversation list
        var picJob: String?
        var picPrompt: String?
        /// „Das kannst du auch sagen“ (saetze.py): the Spark's sentences under this answer and their kind
        var more: [MoreItem]?
        var moreKind: String?
    }

    /// The painted picture kept with an answer ("att" "bild" on the Spark, profiles._att): its job and prompt.
    static func picture(_ d: [String: Any]) -> (job: String, prompt: String)? {
        guard let att = d["att"] as? [[String: Any]],
              let a = att.first(where: { $0["k"] as? String == "bild" && SparkAPI.isJob($0["j"] as? String ?? "") }) else { return nil }
        return (a["j"] as? String ?? "", a["p"] as? String ?? "")
    }

    static func message(_ d: [String: Any]) -> Message? {
        guard let role = d["role"] as? String, role == "user" || role == "assistant",
              let text = d["content"] as? String else { return nil }
        let mark = d["mail"] as? Bool == true ? "mail" : d["outside"] as? Bool == true ? "outside" : nil
        var m = Message(role: role, text: text, mark: mark)
        if role == "assistant", let p = picture(d) { m.picJob = p.job; m.picPrompt = p.prompt }
        return m
    }


    /// 👍/👎 under an answer (POST /api/chat/rate). 👎 with one of five reasons, a short text and, only when the
    /// person says so, the question. A vote can be changed.
    struct RateReason: Identifiable {
        let id: String
        let label: LocalizedStringKey
    }
    static let rateReasons = [
        RateReason(id: "werkzeug", label: "falsches Werkzeug"), RateReason(id: "antwort", label: "falsche Antwort"),
        RateReason(id: "langsam", label: "zu langsam"), RateReason(id: "verstanden", label: "nicht verstanden"),
        RateReason(id: "aussprache", label: "falsch ausgesprochen")]
    /// „Hätte nachsehen sollen in …“ (faelle.SOLL on the Spark): only the chosen key goes along
    static let rateSoll = [
        RateReason(id: "dokumente", label: "meinen Dokumenten"), RateReason(id: "erstellt", label: "erstellten Dokumenten"),
        RateReason(id: "kalender", label: "Kalender"), RateReason(id: "mail", label: "Mails"),
        RateReason(id: "geraete", label: "Geräten"), RateReason(id: "erinnerung", label: "Erinnerungen"),
        RateReason(id: "web", label: "Web"), RateReason(id: "verlauf", label: "früheren Gesprächen")]

    func rate(_ id: UUID, good: Bool, reason: String = "", note: String = "", question: Bool = false, soll: String = "") async {
        guard let i = messages.firstIndex(where: { $0.id == id }), let rid = messages[i].rateId,
              let api = SparkAPI.current else { return }
        var body: [String: Any] = ["id": rid, "good": good]
        if !good {
            body["grund"] = reason
            body["text"] = String(note.trimmingCharacters(in: .whitespacesAndNewlines).prefix(200))
            body["frage"] = question
            if !soll.isEmpty { body["soll"] = soll }
        }
        do {
            _ = try await api.post("api/chat/rate", body)
            if let j = messages.firstIndex(where: { $0.id == id }) { messages[j].rated = good }
            notice = good ? String(localized: "Danke!") : String(localized: "Danke, notiert.")
        } catch {
            self.error = error.localizedDescription
        }
    }
    enum Phase: Equatable { case idle, waiting, listening, transcribing, thinking, speaking }

    static let newAfter: TimeInterval = 600     // a pause this long starts a new conversation
    static let endSilence: TimeInterval = 0.8   // quiet after speech that ends a question
    static let giveUp: TimeInterval = 8         // nothing said: the microphone goes off (as in the panel)
    static let maxQuestion: TimeInterval = 30
    /// In the car (CarPlay): the car's microphone is quieter and the road louder, people pause while driving.
    /// So a quieter voice counts, a longer pause ends a question, and the microphone stays open while
    /// anything like a voice comes in; it goes off only after this long without one.
    static let carEndSilence: TimeInterval = 1.6
    static let carGiveUp: TimeInterval = 15
    /// voice needed before a recording counts as a question: a click, a cough or the room never reach the Spark
    static let minSpeech: TimeInterval = 0.15
    /// after the chime the microphone ignores this long (the tone and the end of the answer still ring in it)
    static let afterChime: TimeInterval = 0.25

    @Published var messages: [Message] = []
    @Published var phase: Phase = .idle
    @Published var error: String? { didSet { if error != nil { errorAt = Date() } } }
    @Published var notice: String?
    @Published var level: Float = 0
    @Published var offer: PhoneAction.Offer?
    @Published var allowed = Allowed() {
        didSet {
            Reader.sendPictures = allowed.images
            if allowed.calls != oldValue.calls || allowed.push != oldValue.push { CallCenter.shared.follow(allowed) }
        }
    }
    @Published var charging = false
    @Published var speechAllowed = false
    /// CarPlay is connected: short answers, the conversation goes on hands-free, notes are said aloud
    @Published var inCar = false
    /// text read from a photo or document; goes along with every question until removed or a new conversation
    @Published var attachment: Attachment?
    /// a tapped sentence („Das kannst du auch sagen“) for the text field; the view takes it and sets it back to nil
    @Published var suggestion: String?
    private var suggested: MoreItem?
    @Published var reading = false
    /// the attachment was stored under "Meine Sachen" (or is being stored)
    @Published var stored = false
    @Published var storing = false
    /// the Spark cannot be reached (no network, Spark or proxy down): typed questions wait in the outbox
    @Published var unreachable = false { didSet { if unreachable != oldValue { offlineSoon() }; if !unreachable { certBad = false } } }
    /// the address answers with a certificate the iPhone does not trust (the band names the reverse proxy)
    @Published var certBad = false
    /// the band „Spark nicht erreichbar“: only after 3 s without the Spark, so a short network change or the Spark's
    /// restart during an update does not make it blink and push the page down (plaene/ruhige-seiten.md)
    @Published private(set) var offlineShown = false
    private var offlineTask: Task<Void, Never>?
    private func offlineSoon() {
        offlineTask?.cancel()
        guard unreachable else { offlineShown = false; return }
        offlineTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(3))
            guard let self, !Task.isCancelled, self.unreachable else { return }
            withAnimation(.easeInOut(duration: 0.25)) { self.offlineShown = true }
        }
    }
    @Published var outbox: [Outbox.Item] = Outbox.load()
    /// devices of the profile in room mode (only with "Raum-Modus in der App zeigen"): line in the chat, Live Activity, widget
    @Published var rooms: [ListeningRoom] = []

    /// One assistant for the phone screen and CarPlay.
    static let shared = Conversation()

    let audio = AudioEngine()
    let wake = WakeWord()
    private var task: Task<Void, Never>?
    private var pcm: [Int16] = []
    private var ring: [Int16] = []
    private var heard = false
    private var fromWake = false
    /// How the microphone opened by itself ("barge", "hands"): the Spark then takes only a known voice (fremdstimme.py)
    private var opened = ""
    private var startedAt = Date()
    private var lastLoud = Date()
    private var loud: TimeInterval = 0
    private var deafUntil = Date.distantPast
    private var loudSince: Date?
    private var floor: Float = 0.02
    /// last time something like a voice came in while listening (the car keeps the microphone open for it)
    private var lastVoice = Date()
    private var streamDone = true
    private var last = Date.distantPast
    private var lastActivity = Date()
    private var errorAt = Date.distantPast
    /// what the answer is doing, for the face ("Gesicht zeigt, was es tut")
    let faceActs = FaceActs()
    private var notes: [Note] = []
    private var noteSince = Int(Date().timeIntervalSince1970 * 1000)
    private var timer: Timer?
    private var foreground = true
    private var started = false
    private var wantListen = false
    private var labelShown = false
    private var checking = false
    private var roomsAt = Date.distantPast
    private var roomsShown: [ListeningRoom]?
    private let net = NetWatch()
    /// the id under which this conversation is kept in the profile's list (the panel's Protokoll)
    private(set) var convoId = Conversation.newId()
    /// how many of the messages the Spark's copy already has: only the ones after them are sent (added there),
    /// so what another device added to the same conversation meanwhile stays
    private var saved = 0
    /// newest change of the open conversation the app knows (ms, the Spark's clock): asks only for what came after
    private var seenAt = 0

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
        guard Prefs.wake, allowed.listen, speechAllowed, wake.onDevice, !CallCenter.shared.active else { return false }
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
            CallCenter.shared.foreground()
            lastActivity = Date()
            Task { await catchUp() }
            // what the profile may has possibly changed meanwhile (Gesperrte Funktionen in the panel): ask the Spark again
            if started { Task { await rightsCheck() } } else if unreachable { Task { await check() } }
            if allowed.ios && started { Task { await AppleReminders.syncLists() } }
            Task { await refreshRooms(now: true) }
            if phase == .idle || phase == .waiting { base() }
        } else if !canWake && !inCar {
            // no listening in the background unless the wake word is on
            if phase == .listening || phase == .waiting { stop() }
            sleepAudio()
        }
    }

    /// Akku: in the background with nothing to hear or say the audio engine stops, so iOS can put the app to sleep
    /// (an answer still playing finishes first: it ends in base(), which comes back here). Never during a call (CallKit owns the
    /// sound then) and never while the wake word or CarPlay listens.
    private func sleepAudio() {
        guard !foreground, !canWake, !inCar, phase == .idle, !CallCenter.shared.active else { return }
        audio.sleep()
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

    /// Rights arrive at once (V01.0.388): the app asks the Spark what the profile may on coming to the front and
    /// every minute in front; when something changed the wake word, push and the rest follow right away.
    private func rightsCheck() async {
        let before = allowed
        guard await check(), allowed != before else { return }
        if allowed.push && !before.push, await Alarms.allow() { UIApplication.shared.registerForRemoteNotifications() }
        if allowed.ios && !before.ios { await AppleReminders.syncLists() }
        if phase == .idle || phase == .waiting { base() }
    }

    private var ticks = 0

    private func tick() {
        ticks += 1
        if foreground && !unreachable && ticks % 3 == 0 { Task { await rightsCheck() } }
        if phase == .waiting && !canWake {
            base()
            notice = String(localized: "Weckwort pausiert, um Akku zu sparen. Tippen startet es wieder.")
        }
        if unreachable { Task { await check() } }
        if allowed.proactive && Prefs.speakNotes && (foreground || phase == .waiting || inCar) { Task { await pollNotes() } }
        if foreground { Task { await refreshRooms() } }
        if foreground && !unreachable && ticks % 2 == 0 { Task { await catchUp() } }
    }

    /// The open conversation shows what another device (panel, Telegram, a speaker) added meanwhile, and closes when it
    /// was deleted there: on coming to the front and about every 40 s in front, only while nothing runs here.
    private func catchUp() async {
        guard saved > 0, phase == .idle || phase == .waiting, let api = SparkAPI.current, Demo.scene == nil else { return }
        let id = convoId
        guard let got = try? await api.convos(since: seenAt), id == convoId,
              phase == .idle || phase == .waiting else { return }
        if !got.ids.contains(id) { fresh(); return }
        guard let c = got.items.first(where: { $0.id == id }) else { return }
        seenAt = max(seenAt, Int(c.updated.timeIntervalSince1970 * 1000))
        let theirs = c.msgs.compactMap { Self.message($0) }
        // only when the Spark has more than the app shows (the app keeps its own labels for what it asked itself)
        guard theirs.count > messages.suffix(60).count else { return }
        // the messages both have keep their identity, label and vote: SwiftUI only adds the new bubbles at the end
        // instead of drawing the whole conversation anew (before: every bubble new, the list jumped)
        let mine = messages.count <= theirs.count ? messages : []
        messages = theirs.enumerated().map { (i, m) -> Message in
            guard i < mine.count, mine[i].role == m.role else { return m }
            var k = m
            k.id = mine[i].id; k.label = mine[i].label; k.rateId = mine[i].rateId; k.rated = mine[i].rated
            if k.picJob == nil { k.picJob = mine[i].picJob; k.picPrompt = mine[i].picPrompt }   // the painted picture stays
            return k
        }
        saved = messages.count
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
        sleepAudio()   // in the background with nothing left to do (after an answer, a timed-out question)
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
        saved = 0
        seenAt = 0
        labelShown = false
    }

    /// Continue a conversation from the list (also one from the panel).
    func resume(_ c: SavedConvo) {
        stop()
        messages = c.msgs.compactMap { Self.message($0) }
        convoId = c.id
        saved = messages.count
        seenAt = Int(c.updated.timeIntervalSince1970 * 1000)
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

    /// The attached document's whole text into the profile's documents (only while Eigene Dokumente is released).
    func storeAttachment() async {
        guard let a = attachment, allowed.docs, !storing, let api = SparkAPI.current else { return }
        storing = true
        defer { storing = false }
        do {
            try await api.storeDoc(name: a.name, text: a.text)
            stored = true
            notice = String(localized: "Unter „Meine Sachen“ gespeichert. Der Spark findet es auch später.")
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

    private func listen(preroll: Double, fromWake: Bool, opened: String = "") {
        error = nil
        wake.stop()
        do { try audio.startInput() } catch {
            self.error = String(localized: "Kein Zugriff aufs Mikrofon. Einstellungen → Spark → Mikrofon.")
            phase = .idle
            return
        }
        if preroll == 0 && !fromWake {
            audio.chime()
            deafUntil = Date().addingTimeInterval(Self.afterChime)
        } else {
            deafUntil = .distantPast
        }
        // priority for people: the Spark frees itself for a profile with Vorrang before the question arrives
        // (it answers the same for every profile, so nothing to check here)
        if let api = SparkAPI.current { Task { _ = try? await api.post("api/vorrang/spricht", [:]) } }
        pcm = preroll > 0 ? Array(ring.suffix(Int(AudioEngine.rate * preroll))) : []
        heard = preroll > 0
        loud = 0
        self.fromWake = fromWake
        self.opened = opened
        startedAt = Date()
        lastLoud = Date()
        lastVoice = Date()
        phase = .listening
    }

    private func input(_ samples: [Int16], _ lvl: Float) {
        level = lvl
        ring.append(contentsOf: samples)
        if ring.count > Int(AudioEngine.rate * 2) { ring.removeFirst(ring.count - Int(AudioEngine.rate * 2)) }
        // the car: a quieter voice over the road noise still counts (see carEndSilence)
        let threshold = inCar ? max(0.025, floor * 1.8) : max(0.06, floor * 2.5)
        if lvl < threshold { floor = lvl < floor ? floor * 0.9 + lvl * 0.1 : floor * 0.995 + lvl * 0.005 }
        let now = Date()
        switch phase {
        case .listening:
            // the chime is no question: neither recorded nor counted (it came back as "Ja" or "Okay")
            guard now >= deafUntil else { return }
            pcm.append(contentsOf: samples)
            if lvl > threshold {
                lastLoud = now
                loud += Double(samples.count) / AudioEngine.rate
                if loud >= Self.minSpeech { heard = true }
            }
            if inCar && lvl > max(0.015, floor * 1.3) { lastVoice = now }
            if heard && now.timeIntervalSince(lastLoud) > (inCar ? Self.carEndSilence : Self.endSilence) { finish() }
            else if !heard && (inCar ? now.timeIntervalSince(lastVoice) > Self.carGiveUp
                                     : now.timeIntervalSince(startedAt) > Self.giveUp) {
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
                listen(preroll: 0.6, fromWake: false, opened: "barge")
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
        let woke = fromWake, how = opened
        task = Task {
            do {
                var text = try await api.transcribe(wav: wav, language: Store.language, opened: how)
                guard !Task.isCancelled else { return }
                if woke { text = wake.strip(text) }
                if text.isEmpty {
                    // the Spark heard only silence or a click (it says so instead of "Ja"/"Okay"): hands-free
                    // ends quietly as when nothing was said
                    if woke { listen(preroll: 0, fromWake: false) }
                    else if Prefs.handsFree || inCar { notice = String(localized: "Nichts gehört, Mikrofon aus. Tippen zum Sprechen."); base() }
                    else { error = String(localized: "Nichts verstanden."); base() }
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

    /// A tap on a suggested sentence: it goes into the text field, the person sends it themselves.
    func suggest(_ item: MoreItem) {
        suggested = item
        suggestion = item.text
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
        audio.warmUp()
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
        // sent exactly as suggested: the tool's name goes along (counted by the Spark, nothing else)
        let more = suggested?.text == text ? suggested?.tool : nil
        suggested = nil
        do {
            for try await ev in api.chat(history, car: inCar, attachment: attachment, speak: inCar || Prefs.speakAnswers, more: more) {
                got = true
                unreachable = false
                switch ev {
                case .text(let t): edit { $0.text += t }; faceActs.text()
                case .face(let name): faceActs.event(name)
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
                case .rate(let id): edit { $0.rateId = id }
                case .picture(let job, let prompt): edit { $0.picJob = job; $0.picPrompt = prompt }
                case .more(let kind, let items): edit { $0.more = items; $0.moreKind = kind }
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
        let start = min(saved, messages.count)
        let msgs: [[String: Any]] = messages[start...].suffix(60).compactMap { m in
            guard !m.text.isEmpty else { return nil }
            var d: [String: Any] = ["role": m.role, "content": m.label.map { $0 + "\n" + m.text } ?? m.text]
            if let mark = m.mark { d[mark] = true }
            // the picture stays with the answer, so the panel and every device show it again
            if let j = m.picJob, let p = m.picPrompt, !p.isEmpty { d["att"] = [["k": "bild", "p": p, "j": j]] }
            return d
        }
        guard !msgs.isEmpty, let first = messages.first(where: { $0.role == "user" }) else { return }
        saved = messages.count
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
            Task { await refreshRooms(now: true) }
            flushNext()
            return true
        } catch {
            if NetWatch.offline(error) { unreachable = true; certBad = NetWatch.certificate(error) }
            return false
        }
    }

    /// Where the profile's devices listen in room mode: every 30 s in front, on opening and on return.
    /// Only names and end times; the Spark decides (admin room mode and the profile switch app_room).
    func refreshRooms(now: Bool = false) async {
        guard allowed.rooms, let api = SparkAPI.current else {
            if roomsShown != [] {
                rooms = []
                roomsShown = []
                await RoomLive.show([])
            }
            return
        }
        guard now || Date().timeIntervalSince(roomsAt) >= 28 else { return }
        roomsAt = Date()
        guard let list = try? await api.rooms() else { return }
        if list != rooms { rooms = list }
        // Live Activity and widget only when something changed (or on return to the front)
        if now || list != roomsShown {
            roomsShown = list
            await RoomLive.show(list)
        }
    }

    /// "Beenden" in the chat line: one room or all of them.
    func endRoom(_ room: ListeningRoom? = nil) async {
        guard let api = SparkAPI.current else { return }
        do {
            try await api.endRoom(room?.id)
        } catch {
            self.error = error.localizedDescription
        }
        await refreshRooms(now: true)
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
            listen(preroll: 0, fromWake: false, opened: "hands")
        } else {
            base()
        }
    }

    private func fail(_ e: Error) {
        if e is CancellationError || (e as? URLError)?.code == .cancelled { return }
        if NetWatch.offline(e) {
            unreachable = true
            certBad = NetWatch.certificate(e)
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
        save(api)   // into the history at once, not only with the next question
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
        // someone else's words (a chat) are not read aloud by themselves: they carry no "spark" text
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
}
