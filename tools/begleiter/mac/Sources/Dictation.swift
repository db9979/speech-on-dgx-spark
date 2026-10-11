import AppKit

/// Diktieren: the hotkey starts the recording, the same hotkey (or "Fertig") ends it; the Spark's text goes to the
/// cursor of the program that was in front (or into the question field of "Frag Spark").
@MainActor
final class Dictation: ObservableObject {
    static let shared = Dictation()

    enum Target {
        case cursor(NSRunningApplication?)
        case ask
    }

    @Published private(set) var recording = false
    @Published private(set) var working = false
    @Published private(set) var elapsed = 0
    @Published private(set) var forAsk = false
    /// 0…1, the microphone's loudness for the level bars
    @Published private(set) var level = 0.0

    /// where text for "Frag Spark" goes
    var onAskText: ((String) -> Void)?

    private let recorder = Recorder()
    private var target: Target = .cursor(nil)
    private var started = Date()
    private var ticker: Task<Void, Never>?

    func toggle(_ t: Target) {
        if recording {
            finish()
        } else {
            Task { await begin(t) }
        }
    }

    private func begin(_ t: Target) async {
        let model = AppModel.shared
        guard model.paired else {
            Windows.showPairing()
            return
        }
        guard model.part("dictate") else {
            HUD.show(AppModel.offHint("Diktieren"))
            return
        }
        guard !working else {
            HUD.show("Das letzte Diktat wird noch umgewandelt.")
            return
        }
        guard await Recorder.micAllowed() else {
            micDenied()
            return
        }
        guard !recording else { return }
        do {
            try recorder.start()
        } catch {
            HUD.show("Das Mikrofon lässt sich nicht öffnen.", symbol: "mic.slash")
            return
        }
        target = t
        if case .ask = t { forAsk = true } else { forAsk = false }
        recording = true
        elapsed = 0
        started = Date()
        RecordingIndicator.show(self, hotkey: model.hotkeyLabel(.dictate))
        ticker?.cancel()
        ticker = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 120_000_000)
                guard let self, self.recording else { return }
                let s = Date().timeIntervalSince(self.started)
                if self.elapsed != Int(s) { self.elapsed = Int(s) }
                self.level = self.recorder.level
                if s >= Recorder.maxSeconds {
                    self.finish()
                    return
                }
            }
        }
    }

    private func micDenied() {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Kein Zugriff aufs Mikrofon"
        a.informativeText = "Zum Diktieren braucht der Spark-Begleiter das Mikrofon. Erlauben unter Systemeinstellungen → Datenschutz & Sicherheit → Mikrofon."
        a.addButton(withTitle: "Systemeinstellungen öffnen")
        a.addButton(withTitle: "Abbrechen")
        if a.runModal() == .alertFirstButtonReturn {
            Recorder.openMicSettings()
        }
    }

    private func stopRecording() -> Data {
        ticker?.cancel()
        ticker = nil
        let pcm = recorder.stop()
        recording = false
        level = 0
        RecordingIndicator.hide()
        return pcm
    }

    /// Ends the recording and lets the Spark write it down.
    func finish() {
        guard recording else { return }
        let pcm = stopRecording()
        guard pcm.count >= Int(Recorder.sampleRate) else {     // half a second
            HUD.show("Zu kurz, nichts aufgenommen.", symbol: "mic")
            return
        }
        let wav = Wav.wrap(pcm: pcm, sampleRate: Int(Recorder.sampleRate))
        working = true
        let t = target
        Task { await send(wav, to: t) }
    }

    /// Ends the recording without sending anything.
    func discard() {
        guard recording else { return }
        _ = stopRecording()
        HUD.show("Aufnahme verworfen.", symbol: "mic.slash")
    }

    private func send(_ wav: Data, to t: Target) async {
        defer { working = false }
        let model = AppModel.shared
        guard let client = model.client else {
            HUD.show("Nicht gekoppelt.")
            return
        }
        HUD.show("Spark schreibt mit …", symbol: "waveform", seconds: 120)
        do {
            let raw = try await client.dictate(wav: wav, sprache: model.config?.dictateSprache ?? "auto")
            let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            HUD.hide()
            guard !text.isEmpty else {
                HUD.show("Nichts verstanden.", symbol: "mic")
                return
            }
            switch t {
            case .ask:
                onAskText?(text)
            case .cursor(let app):
                if await Clip.paste(text, into: app) {
                    // done
                } else {
                    HUD.show("Text ist in der Zwischenablage (⌘V fügt ihn ein).", symbol: "doc.on.clipboard")
                    Access.askOnce()
                }
            }
        } catch is CancellationError {
            HUD.hide()
        } catch {
            HUD.show(model.absorb(error), symbol: "exclamationmark.triangle")
        }
    }
}
