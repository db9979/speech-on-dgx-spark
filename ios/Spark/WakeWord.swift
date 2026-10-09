import AVFoundation
import Speech

/// Listens for the wake word with Apple's speech recognition ON THE IPHONE (never Apple's servers:
/// without on-device support for the language the wake word stays off). Nothing goes to the Spark
/// before the wake word was heard.
final class WakeWord {
    enum Word: String, CaseIterable, Identifiable {
        case spark = "Hey Spark", jarvis = "Jarvis", computer = "Computer"
        var id: String { rawValue }
        /// what the recognizer may write for it
        var tokens: Set<String> {
            switch self {
            case .spark: return ["spark", "sparc", "spak", "sparks", "spark's"]
            case .jarvis: return ["jarvis", "javis", "jarwis", "jervis", "travis"]
            case .computer: return ["computer", "komputer", "kompjuter"]
            }
        }
    }

    private let recognizer = SFSpeechRecognizer(locale: WakeWord.locale)

    /// The language of the app's surface: English on an English iPhone, else German.
    static var locale: Locale {
        guard Bundle.main.preferredLocalizations.first == "en" else { return Locale(identifier: "de-DE") }
        let want = "en-" + (Locale.current.region?.identifier ?? "US")
        let known = SFSpeechRecognizer.supportedLocales().map { $0.identifier.replacingOccurrences(of: "_", with: "-") }
        return Locale(identifier: known.contains(want) ? want : "en-US")
    }
    private let lock = NSLock()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var started = Date()
    private var seen = 0
    private(set) var running = false
    var word: Word = .spark
    /// Main thread: the wake word was heard.
    var onWake: (() -> Void)?

    var onDevice: Bool { recognizer?.supportsOnDeviceRecognition == true }

    static func authorize() async -> Bool {
        await withCheckedContinuation { c in
            SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0 == .authorized) }
        }
    }

    func start() {
        stop()
        guard let r = recognizer, r.supportsOnDeviceRecognition, r.isAvailable else { return }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.requiresOnDeviceRecognition = true
        req.shouldReportPartialResults = true
        req.contextualStrings = [word.rawValue]
        lock.lock(); request = req; lock.unlock()
        seen = 0
        started = Date()
        running = true
        task = r.recognitionTask(with: req) { [weak self] result, error in
            DispatchQueue.main.async { self?.handle(result, error) }
        }
    }

    func stop() {
        running = false
        lock.lock()
        request?.endAudio()
        request = nil
        lock.unlock()
        task?.cancel()
        task = nil
    }

    /// Audio thread.
    func feed(_ buf: AVAudioPCMBuffer) {
        lock.lock()
        request?.append(buf)
        lock.unlock()
    }

    private func handle(_ result: SFSpeechRecognitionResult?, _ error: Error?) {
        guard running else { return }
        if let result {
            let words = result.bestTranscription.formattedString.lowercased()
                .components(separatedBy: CharacterSet.letters.inverted).filter { !$0.isEmpty }
            if words.count > seen {
                let new = words[max(0, seen - 1)...]   // one word back: partial results revise the last word
                seen = words.count
                if new.contains(where: word.tokens.contains) {
                    stop()
                    onWake?()
                    return
                }
            }
            if result.isFinal { start(); return }
        }
        // a recognition task runs about a minute at most; start a fresh one in time
        if error != nil || Date().timeIntervalSince(started) > 50 { start() }
    }

    /// The question without the wake word in front ("Hey Spark, wie spät ist es" → "wie spät ist es").
    func strip(_ text: String) -> String {
        var t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let parts = t.split(separator: " ", omittingEmptySubsequences: true)
        for n in 1...min(3, max(1, parts.count)) where parts.count >= n {
            let head = parts.prefix(n).joined(separator: " ").lowercased()
                .components(separatedBy: CharacterSet.letters.inverted).filter { !$0.isEmpty }
            if head.contains(where: word.tokens.contains) {
                t = parts.dropFirst(n).joined(separator: " ")
                break
            }
        }
        return t.trimmingCharacters(in: CharacterSet(charactersIn: " ,.!?").union(.whitespacesAndNewlines))
    }
}
