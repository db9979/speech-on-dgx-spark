import Foundation
import SwiftUI
import UIKit

/// Pairing state of the app. A pairing link always asks first which Spark it leads to,
/// so a link from somewhere else cannot quietly send the questions to a strange server.
@MainActor
final class AppState: ObservableObject {
    struct Link: Identifiable {
        let id = UUID()
        let base: URL
        let code: String
    }

    @Published var paired = Store.paired
    @Published var profile = Store.profile
    @Published var busy = false
    @Published var message: String?
    @Published var offered: Link?

    /// spark-app://pair?url=https://...&code=... (from the panel: QR code or link)
    func open(_ url: URL) {
        guard url.scheme == "spark-app", url.host == "pair",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let raw = items.first(where: { $0.name == "url" })?.value,
              let code = items.first(where: { $0.name == "code" })?.value,
              code.range(of: "^[A-Za-z0-9_-]{20,40}$", options: .regularExpression) != nil,
              let base = Self.checked(raw) else {
            message = "Das ist kein gültiger Kopplungs-Link vom Spark."
            return
        }
        offered = Link(base: base, code: code)
    }

    /// Only https with a real certificate, a host and no path (as the panel makes the link).
    static func checked(_ raw: String) -> URL? {
        guard let u = URL(string: raw.trimmingCharacters(in: .whitespaces)), u.scheme == "https",
              let host = u.host, !host.isEmpty, u.path.isEmpty || u.path == "/", u.query == nil, u.user == nil else { return nil }
        return u
    }

    func pair(_ link: Link) async {
        offered = nil
        busy = true
        defer { busy = false }
        do {
            let r = try await SparkAPI.pair(base: link.base, code: link.code, name: UIDevice.current.name)
            Store.baseURL = link.base
            Store.key = r.key
            Store.profile = r.profile
            Store.language = r.language
            profile = r.profile
            paired = true
            message = nil
        } catch {
            message = error.localizedDescription
        }
    }

    func refresh() async {
        guard let api = SparkAPI.current else { return }
        if let r = try? await api.hello() {
            Store.profile = r.profile
            Store.language = r.language
            profile = r.profile
        }
    }

    func unpair() {
        Store.forget()
        paired = false
        profile = ""
    }
}

/// One conversation: record, recognize on the Spark, stream the answer and play it.
@MainActor
final class Conversation: ObservableObject {
    struct Message: Identifiable {
        let id = UUID()
        let role: String
        var text: String
        var mark: String?
    }

    enum Phase: Equatable { case idle, listening, transcribing, thinking, speaking }

    static let newAfter: TimeInterval = 600   // a pause this long starts a new conversation

    @Published var messages: [Message] = []
    @Published var phase: Phase = .idle
    @Published var error: String?
    @Published var level: Float = 0

    private let recorder = Recorder()
    private let player = Player()
    private var task: Task<Void, Never>?
    private var meter: Timer?
    private var last = Date.distantPast

    init() {
        player.onIdle = { [weak self] in
            guard let self else { return }
            if self.phase == .speaking { self.phase = .idle }
        }
    }

    var status: String {
        switch phase {
        case .idle: return "Tippen und sprechen"
        case .listening: return "Ich höre zu … tippen, wenn du fertig bist"
        case .transcribing: return "Erkenne Sprache …"
        case .thinking: return "Denke nach …"
        case .speaking: return "Spricht … tippen zum Anhalten"
        }
    }

    func tap() {
        switch phase {
        case .idle: listen()
        case .listening: finish()
        default: stop()
        }
    }

    func listen() {
        error = nil
        Task {
            guard await AudioSetup.microphoneAllowed() else {
                error = "Die App darf das Mikrofon nicht benutzen. Einstellungen → Spark → Mikrofon."
                return
            }
            do {
                try recorder.start()
                phase = .listening
                meter = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
                    Task { @MainActor in
                        guard let self else { return }
                        self.level = self.recorder.level
                        if self.phase == .listening && !self.recorder.isRecording { self.finish() }   // time limit reached
                    }
                }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    func finish() {
        meter?.invalidate()
        meter = nil
        level = 0
        guard let wav = recorder.stop(), let api = SparkAPI.current else {
            phase = .idle
            return
        }
        phase = .transcribing
        task = Task {
            do {
                let text = try await api.transcribe(wav: wav, language: Store.language)
                guard !Task.isCancelled else { return }
                if text.isEmpty {
                    error = "Nichts verstanden."
                    phase = .idle
                    return
                }
                await send(text, api)
            } catch {
                fail(error)
            }
        }
    }

    func write(_ text: String) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let api = SparkAPI.current else { return }
        stop()
        error = nil
        task = Task { await send(text, api) }
    }

    private func send(_ text: String, _ api: SparkAPI) async {
        if Date().timeIntervalSince(last) > Self.newAfter { messages = [] }
        messages.append(Message(role: "user", text: text))
        let answer = Message(role: "assistant", text: "")
        messages.append(answer)
        phase = .thinking
        // the browser does the same: earlier answers made from mail or web text keep their mark,
        // so the Spark keeps its locks for the next turn
        let history: [[String: Any]] = messages.dropLast().suffix(20).map { m in
            var d: [String: Any] = ["role": m.role, "content": m.text]
            if let mark = m.mark { d[mark] = true }
            return d
        }
        func edit(_ change: (inout Message) -> Void) {
            if let i = messages.firstIndex(where: { $0.id == answer.id }) { change(&messages[i]) }
        }
        do {
            for try await ev in api.chat(history) {
                switch ev {
                case .text(let t): edit { $0.text += t }
                case .drop(let n): edit { $0.text = String($0.text.dropLast(n)) }
                case .audio(let pcm):
                    player.play(pcm)
                    phase = .speaking
                case .mark(let m): edit { $0.mark = $0.mark == "mail" ? "mail" : m }
                case .error(let e): error = e
                }
            }
            last = Date()
            if !player.busy { phase = .idle }
        } catch is CancellationError {
        } catch {
            fail(error)
        }
        messages.removeAll { $0.id == answer.id && $0.text.isEmpty }
    }

    private func fail(_ e: Error) {
        if (e as? URLError)?.code == .cancelled { return }
        error = e.localizedDescription
        phase = .idle
    }

    func stop() {
        task?.cancel()
        task = nil
        meter?.invalidate()
        meter = nil
        recorder.cancel()
        player.stop()
        level = 0
        phase = .idle
    }

    func restart() {
        stop()
        messages = []
        error = nil
        last = .distantPast
    }
}
