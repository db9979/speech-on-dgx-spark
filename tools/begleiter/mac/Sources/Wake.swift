import AVFoundation
import AppKit

/// whether the converter already got the one buffer of this call
private final class WakeFed {
    var done = false
}

/// The level gate behind a lock: fed on the audio thread, switched from the main thread.
final class GateFeeder: @unchecked Sendable {
    private let lock = NSLock()
    private var gate = LevelGate(maxSeconds: 5)
    private var skip = 0

    func set(_ g: LevelGate, skipSeconds: Double = 0) {
        lock.lock()
        gate = g
        skip = Int(skipSeconds * Double(LevelGate.rate))
        lock.unlock()
    }

    func feed(_ samples: [Int16]) -> [LevelGate.Event] {
        lock.lock()
        defer { lock.unlock() }
        if skip > 0 {
            let n = min(skip, samples.count)
            skip -= n
            if n == samples.count { return [] }
            return gate.feed(Array(samples[n...]))
        }
        return gate.feed(samples)
    }
}

/// Part "wake": while on (and not paused), the microphone listens for the Spark's wake word. The level gate cuts out
/// sentences (≤ 5 s); each goes to the own Spark (POST /api/desk/hear), at most one at a time. "Hey Spark, …" asks
/// right away; "Hey Spark" alone plays a tone and takes the question until a pause (≤ 15 s). macOS shows its
/// orange microphone dot, the menu-bar face shows a ring.
@MainActor
final class Wake: ObservableObject {
    static let shared = Wake()
    static let pausedKey = "wake.paused"

    /// the microphone is open for the wake word
    @Published private(set) var listening = false
    /// "Weckwort pausieren" (only on this Mac)
    @Published private(set) var paused: Bool
    /// recording the question after the wake word
    @Published private(set) var question = false
    @Published private(set) var problem = ""

    private var wanted = false
    private var engine: AVAudioEngine?
    private let feeder = GateFeeder()
    private var hearing = false
    private var starting = false
    private var configObserver: NSObjectProtocol?

    init() {
        paused = UserDefaults.standard.bool(forKey: Self.pausedKey)
    }

    var word: String { AppModel.shared.config?.wakeWord ?? "Hey Spark" }

    func apply(on: Bool) {
        wanted = on
        refresh()
    }

    func togglePause() {
        paused.toggle()
        UserDefaults.standard.set(paused, forKey: Self.pausedKey)
        refresh()
    }

    private func refresh() {
        if wanted && !paused {
            if engine == nil && !starting {
                starting = true
                Task { @MainActor in
                    await self.startEngine()
                    self.starting = false
                }
            }
        } else {
            stopEngine()
        }
    }

    // ------------------------------------------------------------------ the microphone

    private func startEngine() async {
        guard await Recorder.micAllowed() else {
            problem = "Kein Zugriff aufs Mikrofon (Systemeinstellungen → Datenschutz & Sicherheit → Mikrofon)."
            return
        }
        guard wanted, !paused, engine == nil else { return }
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0,
              let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Double(LevelGate.rate),
                                            channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: inFormat, to: outFormat) else {
            problem = "Das Mikrofon lässt sich nicht öffnen."
            return
        }
        converter.downmix = true
        feeder.set(LevelGate(maxSeconds: 5))
        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat,
                         block: Self.makeTap(converter: converter, outFormat: outFormat, feeder: feeder))
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            problem = "Das Mikrofon lässt sich nicht öffnen."
            return
        }
        self.engine = engine
        problem = ""
        listening = true
        question = false
        // another microphone or a changed format: open anew
        configObserver = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange,
                                                                object: engine, queue: .main) { _ in
            Task { @MainActor in
                let w = Wake.shared
                w.stopEngine()
                w.refresh()
            }
        }
    }

    private func stopEngine() {
        if let o = configObserver {
            NotificationCenter.default.removeObserver(o)
            configObserver = nil
        }
        if let engine {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        engine = nil
        listening = false
        if question {
            question = false
            HUD.hide()
        }
    }

    /// Runs on the audio thread: converts each buffer to 16 kHz mono Int16 and feeds the gate.
    nonisolated private static func makeTap(converter: AVAudioConverter, outFormat: AVAudioFormat,
                                            feeder: GateFeeder) -> AVAudioNodeTapBlock {
        return { buffer, _ in
            let ratio = outFormat.sampleRate / buffer.format.sampleRate
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
            guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) else { return }
            let given = WakeFed()
            var error: NSError?
            let status = converter.convert(to: out, error: &error) { _, inputStatus in
                if given.done {
                    inputStatus.pointee = .noDataNow
                    return nil
                }
                given.done = true
                inputStatus.pointee = .haveData
                return buffer
            }
            guard status != .error, out.frameLength > 0, let ch = out.int16ChannelData else { return }
            let samples = Array(UnsafeBufferPointer(start: ch[0], count: Int(out.frameLength)))
            let events = feeder.feed(samples)
            for e in events {
                Task { @MainActor in Wake.shared.got(e) }
            }
        }
    }

    // ------------------------------------------------------------------ what was heard

    private func got(_ e: LevelGate.Event) {
        guard listening else { return }
        if question {
            questionDone(e)
            return
        }
        guard case .piece(let pcm) = e else { return }
        // while the person dictates, nothing goes to /hear
        if Dictation.shared.recording || Dictation.shared.working { return }
        guard !hearing, let client = AppModel.shared.client, AppModel.shared.part("wake") else { return }
        hearing = true
        let wav = Wav.wrap(pcm: pcm, sampleRate: LevelGate.rate)
        Task { @MainActor in
            defer { self.hearing = false }
            do {
                let r = try await client.hear(wav: wav)
                guard r.wake, self.listening else { return }
                if !r.rest.isEmpty {
                    let q = String(r.rest.prefix(SparkClient.askMax))
                    AskController.shared.run(question: q, spoken: true) { c in try await c.ask(q) }
                } else {
                    self.beginQuestion()
                }
            } catch is CancellationError {
            } catch {
                let m = AppModel.shared.absorb(error)
                if case .off? = error as? SparkProblem { self.problem = m }
            }
        }
    }

    private func beginQuestion() {
        question = true
        NSSound(named: NSSound.Name("Tink"))?.play()
        // the tone itself must not start the question: 0.4 s are skipped
        feeder.set(LevelGate(maxSeconds: 15, preRoll: 0.4, waitLimit: 8), skipSeconds: 0.4)
        HUD.show("Ich höre zu – deine Frage …", symbol: "ear", seconds: 25)
    }

    private func questionDone(_ e: LevelGate.Event) {
        question = false
        feeder.set(LevelGate(maxSeconds: 5))
        HUD.hide()
        guard case .piece(let pcm) = e else {
            HUD.show("Keine Frage gehört.", symbol: "ear")
            return
        }
        guard let client = AppModel.shared.client else { return }
        let wav = Wav.wrap(pcm: pcm, sampleRate: LevelGate.rate)
        let sprache = AppModel.shared.config?.dictateSprache ?? "auto"
        HUD.show("Spark schreibt mit …", symbol: "waveform", seconds: 60)
        Task { @MainActor in
            do {
                let text = try await client.dictate(wav: wav, sprache: sprache).trimmingCharacters(in: .whitespacesAndNewlines)
                HUD.hide()
                guard !text.isEmpty else {
                    HUD.show("Nichts verstanden.", symbol: "ear")
                    return
                }
                let q = String(text.prefix(SparkClient.askMax))
                AskController.shared.run(question: q, spoken: true) { c in try await c.ask(q) }
            } catch is CancellationError {
                HUD.hide()
            } catch {
                HUD.show(AppModel.shared.absorb(error), symbol: "exclamationmark.triangle")
            }
        }
    }
}
