import AVFoundation

/// One audio engine for listening and speaking. Voice processing (iOS echo cancellation) is on,
/// so the microphone does not hear the Spark's own answer and the person can talk over it.
/// Input arrives as 16 kHz mono 16-bit samples plus a loudness value; the raw buffers go to the
/// wake word recognizer. Output is the Spark's 24 kHz PCM, played piece after piece without gaps.
final class AudioEngine {
    static let rate: Double = 16000

    private let engine = AVAudioEngine()
    private let node = AVAudioPlayerNode()
    private let playFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24000, channels: 1, interleaved: false)!
    private let target = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: AudioEngine.rate, channels: 1, interleaved: true)!
    private var converter: AVAudioConverter?
    private var rest = Data()
    private var queued = 0
    /// Buffers scheduled but not yet played, so they survive an engine restart.
    private var pending: [(Int, AVAudioPCMBuffer)] = []
    private var nextId = 0
    private var generation = 0
    private var tapOn = false
    private var configured = false
    /// Stopped on purpose (sleep()): a route change or the end of an interruption then does not start it again.
    private var sleeping = false
    /// When the engine last started: right after a start iOS may still switch the route (voice processing)
    /// and stop it again, which threw away the first answer. Pieces wait until the start has settled.
    private var startedAt = Date.distantPast
    private var holding = false
    private static let settle: TimeInterval = 0.6
    /// Something of this answer has played: if the player then runs dry before the next piece arrives
    /// (the Spark spoke slower than real time while it still wrote), the next pieces wait `rebuffer`
    /// seconds and play together, so one gap is heard instead of a stutter.
    private var heard = false
    private static let rebuffer: TimeInterval = 0.4
    /// After silence a piece starts with a 5 ms fade-in (24 kHz) instead of a step, which clicks.
    private static let fadeIn = 120

    /// "Ton-Protokoll" (Einstellungen): the last steps of the audio engine and of CarPlay, to copy into the thread or
    /// attach to a report. Only fixed words and numbers, never what was said. Kept on the iPhone across a restart of
    /// the app, so a drive whose app iOS ended still shows what happened (CarPlay stabil, V01.0.871).
    private(set) static var diary: [String] = UserDefaults.standard.stringArray(forKey: diaryKey) ?? []
    private static let diaryKey = "audioDiary"
    static func note(_ s: String) {
        let t = Date().formatted(.dateTime.hour(.twoDigits(amPM: .omitted)).minute(.twoDigits).second(.twoDigits))
        let route = AVAudioSession.sharedInstance().currentRoute.outputs.map { $0.portType.rawValue }.joined(separator: "+")
        diary.append("\(t) \(s) [\(route)]")
        if diary.count > 150 { diary.removeFirst(diary.count - 150) }
        UserDefaults.standard.set(diary, forKey: diaryKey)
    }

    /// Main thread: 16 kHz samples and their loudness (0...1).
    var onInput: (([Int16], Float) -> Void)?
    /// Audio thread: the raw microphone buffer (for the wake word).
    var onRaw: ((AVAudioPCMBuffer) -> Void)?
    /// Main thread: everything queued has been played.
    var onIdle: (() -> Void)?
    /// Main thread: Siri, a call or another app took the sound (true) or gave it back (false).
    var onInterrupt: ((Bool) -> Void)?
    /// Taken by another app: pieces not yet heard wait for the sound to come back instead of being given up.
    private var interrupted = false
    /// Loudness of what is playing right now (0...1), for the face's mouth.
    private(set) var outLevel: Float = 0

    var busy: Bool { queued > 0 }
    var listening: Bool { tapOn }

    init() {
        engine.attach(node)
        NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] n in
            guard let self, let raw = n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt else { return }
            let ended = raw == AVAudioSession.InterruptionType.ended.rawValue
            Self.note(ended ? "Unterbrechung vorbei" : "Unterbrechung")
            self.interrupted = !ended
            if ended && !self.sleeping {
                try? self.ensureRunning()
                self.resume()
            }
            self.onInterrupt?(!ended)
        }
        // where the sound goes (car, speaker, headset) and why it changed: the evidence after a drive
        NotificationCenter.default.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { n in
            let why = (n.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt).flatMap { AVAudioSession.RouteChangeReason(rawValue: $0) }
            let word: String
            switch why ?? .unknown {
            case .newDeviceAvailable: word = "neues Gerät"
            case .oldDeviceUnavailable: word = "Gerät weg"
            case .categoryChange: word = "Kategorie"
            case .override: word = "umgelenkt"
            case .routeConfigurationChange: word = "Konfiguration"
            default: word = "anderes"
            }
            Self.note("Weg geändert: \(word)")
        }
        NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            guard let self, !self.sleeping else { return }
            Self.note("Konfiguration geändert, offen \(self.pending.count)")
            let wasListening = self.tapOn
            self.removeTap()
            self.converter = nil
            // switching on voice processing (first answer) or a headset change stops the engine
            // and with it the player: play again what had not been heard yet
            self.restart(wasListening, tries: 3)
        }
    }

    /// Speaker plus Bluetooth headsets. iOS 26 renamed .allowBluetooth to .allowBluetoothHFP;
    /// this builds with the older Xcode (GitHub) and the newer one alike.
    private static var sessionOptions: AVAudioSession.CategoryOptions {
        var o: AVAudioSession.CategoryOptions = [.defaultToSpeaker, .allowBluetoothA2DP]
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) { o.insert(.allowBluetoothHFP) } else { o.insert(.allowBluetooth) }
        #else
        o.insert(.allowBluetooth)
        #endif
        return o
    }

    private func configure() throws {
        guard !configured else { return }
        let s = AVAudioSession.sharedInstance()
        try s.setCategory(.playAndRecord, mode: .voiceChat, options: Self.sessionOptions)
        try s.setActive(true)
        try engine.inputNode.setVoiceProcessingEnabled(true)
        engine.inputNode.voiceProcessingOtherAudioDuckingConfiguration = .init(enableAdvancedDucking: false, duckingLevel: .min)
        engine.connect(node, to: engine.mainMixerNode, format: playFormat)
        // the mouth follows what really plays
        node.installTap(onBus: 0, bufferSize: 1024, format: playFormat) { [weak self] buf, _ in
            let level = Self.rms(buf)
            DispatchQueue.main.async { self?.outLevel = level }
        }
        configured = true
    }

    func ensureRunning() throws {
        sleeping = false
        try configure()
        if !engine.isRunning {
            try AVAudioSession.sharedInstance().setActive(true)
            engine.prepare()
            do { try engine.start() } catch { Self.note("Start fehlgeschlagen: \(error.localizedDescription)"); throw error }
            startedAt = Date()
            Self.note("Engine gestartet")
        }
    }

    /// After a route change the session is sometimes not ready yet: try again a little later.
    private func restart(_ listen: Bool, tries: Int) {
        do {
            try ensureRunning()
            resume()
            if listen { try? startInput() }
        } catch {
            guard tries > 1 else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in self?.restart(listen, tries: tries - 1) }
        }
    }

    // ---------------------------------------------------------------- input
    func startInput() throws {
        try ensureRunning()
        guard !tapOn else { return }
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { throw SparkError(message: String(localized: "Kein Mikrofon verfügbar.")) }
        converter = AVAudioConverter(from: format, to: target)
        input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buf, _ in
            guard let self else { return }
            self.onRaw?(buf)
            let samples = self.convert(buf)
            let level = Self.level(samples)
            DispatchQueue.main.async { self.onInput?(samples, level) }
        }
        tapOn = true
    }

    func stopInput() {
        removeTap()
    }

    /// Akku (2026-10-16): nothing listens and nothing plays any more and the app is in the background: stop the
    /// engine and let go of the audio session. A running engine (voice processing, microphone) keeps the app awake
    /// through the "audio" background mode; stopped, iOS can put it to sleep. The next answer or listening starts
    /// it again (ensureRunning, with the usual settle time).
    func sleep() {
        guard engine.isRunning, !tapOn, queued == 0, pending.isEmpty, !holding else { return }
        sleeping = true
        node.stop()
        engine.stop()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        Self.note("Engine schläft (Hintergrund)")
    }

    private func removeTap() {
        if tapOn { engine.inputNode.removeTap(onBus: 0) }
        tapOn = false
    }

    private func convert(_ buf: AVAudioPCMBuffer) -> [Int16] {
        guard let converter else { return [] }
        let cap = AVAudioFrameCount(Double(buf.frameLength) * Self.rate / buf.format.sampleRate + 64)
        guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: cap) else { return [] }
        var fed = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if fed {
                status.pointee = .noDataNow
                return nil
            }
            fed = true
            status.pointee = .haveData
            return buf
        }
        guard error == nil, let ch = out.int16ChannelData else { return [] }
        return Array(UnsafeBufferPointer(start: ch[0], count: Int(out.frameLength)))
    }

    static func level(_ s: [Int16]) -> Float {
        guard !s.isEmpty else { return 0 }
        var sum: Float = 0
        for v in s { let f = Float(v) / 32768; sum += f * f }
        return min(1, (sum / Float(s.count)).squareRoot() * 4)
    }

    private static func rms(_ buf: AVAudioPCMBuffer) -> Float {
        guard let ch = buf.floatChannelData, buf.frameLength > 0 else { return 0 }
        var sum: Float = 0
        for i in 0..<Int(buf.frameLength) { sum += ch[0][i] * ch[0][i] }
        return min(1, (sum / Float(buf.frameLength)).squareRoot() * 5)
    }

    // ---------------------------------------------------------------- output
    /// tone: a short sound of its own (the chime, the end tone) with its fixed name for the Ton-Protokoll. It never waits
    /// the rebuffer time meant for a gap inside an answer (CarPlay Runde 2: the chime came 400 ms late, after the
    /// microphone's deaf time, and the car microphone took it for the start of a question). Returns the seconds until
    /// the piece starts playing.
    @discardableResult
    func play(_ pcm: Data, tone: String? = nil) -> Double {
        let data = rest + pcm
        let frames = data.count / 2
        rest = data.count % 2 == 1 ? Data(data.suffix(1)) : Data()
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: playFormat, frameCapacity: AVAudioFrameCount(frames)) else { return 0 }
        buffer.frameLength = AVAudioFrameCount(frames)
        let out = buffer.floatChannelData![0]
        data.withUnsafeBytes { raw in
            for i in 0..<frames {
                out[i] = Float(Int16(littleEndian: raw.loadUnaligned(fromByteOffset: i * 2, as: Int16.self))) / 32768
            }
        }
        if queued == 0 {   // the player is silent: begin softly
            for i in 0..<min(frames, Self.fadeIn) { out[i] *= Float(i) / Float(Self.fadeIn) }
        }
        do { try ensureRunning() } catch { return 0 }
        let dry = queued == 0 && heard && !holding && tone == nil
        let ahead = Double(pending.reduce(0) { $0 + Int($1.1.frameLength) }) / 24000
        queued += 1
        nextId += 1
        pending.append((nextId, buffer))
        if let tone { Self.note("Ton: \(tone)") } else if pending.count == 1 && !dry { Self.note("Antwort: erstes Stück") }
        let wait = dry ? Self.rebuffer : Self.settle - Date().timeIntervalSince(startedAt)
        if wait > 0 || holding {
            // just started: hold the pieces until a route switch would have happened, then play all of them;
            // ran dry mid-answer: collect a little audio first, so the next stretch plays without a stall
            if !holding {
                holding = true
                Self.note(dry ? "leergelaufen, puffere \(Int(wait * 1000)) ms" : "warte \(Int(wait * 1000)) ms")
                DispatchQueue.main.asyncAfter(deadline: .now() + max(wait, 0.05)) { [weak self] in
                    guard let self else { return }
                    self.holding = false
                    try? self.ensureRunning()
                    self.resume()
                }
            }
            return max(wait, Self.settle) + ahead
        }
        schedule(nextId, buffer)
        node.play()
        return ahead
    }

    /// Before an answer arrives: set the engine up now, so the configuration change that
    /// voice processing causes happens before the first piece of the answer plays.
    func warmUp() {
        heard = false
        try? ensureRunning()
    }

    private func schedule(_ id: Int, _ buffer: AVAudioPCMBuffer) {
        let gen = generation
        heard = true
        node.scheduleBuffer(buffer) { [weak self] in
            DispatchQueue.main.async {
                guard let self, gen == self.generation else { return }
                // the engine stopped (route switch): the player let go of the piece unheard; resume() plays it again
                guard self.engine.isRunning else {
                    Self.note("Stück verworfen, Engine aus")
                    self.watchStopped()
                    return
                }
                self.pending.removeAll { $0.0 == id }
                self.queued -= 1
                if self.queued == 0 {
                    self.outLevel = 0
                    self.onIdle?()
                }
            }
        }
    }

    /// The engine stopped with pieces left and nobody restarted it: try once, else give up so the
    /// conversation does not wait for sound that never comes.
    private func watchStopped() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            // taken by Siri, a call or the car's own voice: the pieces wait for the sound to come back (resume)
            guard let self, !self.engine.isRunning, !self.pending.isEmpty, !self.interrupted else { return }
            do { try self.ensureRunning(); self.resume() } catch {
                Self.note("aufgegeben")
                self.stopPlaying()
                self.onIdle?()
            }
        }
    }

    /// After the engine was restarted: schedule again what has not been played and start the player.
    private func resume() {
        guard !pending.isEmpty, engine.isRunning, !holding else { return }
        Self.note("spiele \(pending.count) Stücke")
        generation += 1
        node.stop()
        queued = pending.count
        for (id, buffer) in pending { schedule(id, buffer) }
        node.play()
    }

    func stopPlaying() {
        holding = false
        heard = false
        generation += 1
        queued = 0
        pending = []
        rest = Data()
        outLevel = 0
        node.stop()
    }

    /// A short rising tone: "I am listening". Returns the seconds until it has ended.
    @discardableResult
    func chime() -> Double { tone(from: 660, to: 1100, "Zuhören") }

    /// A short falling tone: the conversation in the car ended, lower when it did not work (Dominik 2026-10-20 „5a“),
    /// so nobody has to look at the car screen.
    func endTone(sad: Bool) { _ = tone(from: sad ? 440 : 880, to: sad ? 260 : 600, sad ? "Ende Fehler" : "Ende") }

    @discardableResult
    private func tone(from: Double, to: Double, _ name: String) -> Double {
        let sr = 24000.0, n = Int(sr * 0.18)
        var d = Data(capacity: n * 2)
        for i in 0..<n {
            let t = Double(i) / sr
            let f = from + (to - from) * t / 0.18
            let env = min(1, Double(i) / 300) * min(1, Double(n - i) / 900)
            let v = Int16(sin(2 * .pi * f * t) * env * 9000)
            withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) }
        }
        return play(d, tone: name) + 0.18
    }

    /// 16 kHz mono 16-bit samples as a WAV file for the Spark's speech recognition.
    static func wav(_ samples: [Int16]) -> Data {
        var d = Data()
        func u32(_ v: UInt32) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        func u16(_ v: UInt16) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        let bytes = UInt32(samples.count * 2)
        d.append(Data("RIFF".utf8)); u32(36 + bytes); d.append(Data("WAVE".utf8))
        d.append(Data("fmt ".utf8)); u32(16); u16(1); u16(1); u32(UInt32(rate)); u32(UInt32(rate) * 2); u16(2); u16(16)
        d.append(Data("data".utf8)); u32(bytes)
        samples.withUnsafeBufferPointer { p in
            for v in p { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        }
        return d
    }

    static func microphoneAllowed() async -> Bool {
        await AVAudioApplication.requestRecordPermission()
    }
}
