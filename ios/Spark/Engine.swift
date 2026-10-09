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

    /// Main thread: 16 kHz samples and their loudness (0...1).
    var onInput: (([Int16], Float) -> Void)?
    /// Audio thread: the raw microphone buffer (for the wake word).
    var onRaw: ((AVAudioPCMBuffer) -> Void)?
    /// Main thread: everything queued has been played.
    var onIdle: (() -> Void)?
    /// Loudness of what is playing right now (0...1), for the face's mouth.
    private(set) var outLevel: Float = 0

    var busy: Bool { queued > 0 }
    var listening: Bool { tapOn }

    init() {
        engine.attach(node)
        NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] n in
            guard let self, let raw = n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  AVAudioSession.InterruptionType(rawValue: raw) == .ended else { return }
            try? self.ensureRunning()
            self.resume()
        }
        NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            guard let self else { return }
            let wasListening = self.tapOn
            self.removeTap()
            self.converter = nil
            try? self.ensureRunning()
            // switching on voice processing (first answer) or a headset change stops the engine
            // and with it the player: play again what had not been heard yet
            self.resume()
            if wasListening { try? self.startInput() }
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
        try configure()
        if !engine.isRunning {
            try AVAudioSession.sharedInstance().setActive(true)
            engine.prepare()
            try engine.start()
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
    func play(_ pcm: Data) {
        let data = rest + pcm
        let frames = data.count / 2
        rest = data.count % 2 == 1 ? Data(data.suffix(1)) : Data()
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: playFormat, frameCapacity: AVAudioFrameCount(frames)) else { return }
        buffer.frameLength = AVAudioFrameCount(frames)
        let out = buffer.floatChannelData![0]
        data.withUnsafeBytes { raw in
            for i in 0..<frames {
                out[i] = Float(Int16(littleEndian: raw.loadUnaligned(fromByteOffset: i * 2, as: Int16.self))) / 32768
            }
        }
        do { try ensureRunning() } catch { return }
        queued += 1
        nextId += 1
        pending.append((nextId, buffer))
        schedule(nextId, buffer)
        node.play()
    }

    /// Before an answer arrives: set the engine up now, so the configuration change that
    /// voice processing causes happens before the first piece of the answer plays.
    func warmUp() {
        try? ensureRunning()
    }

    private func schedule(_ id: Int, _ buffer: AVAudioPCMBuffer) {
        let gen = generation
        node.scheduleBuffer(buffer) { [weak self] in
            DispatchQueue.main.async {
                guard let self, gen == self.generation else { return }
                self.pending.removeAll { $0.0 == id }
                self.queued -= 1
                if self.queued == 0 {
                    self.outLevel = 0
                    self.onIdle?()
                }
            }
        }
    }

    /// After the engine was restarted: schedule again what has not been played and start the player.
    private func resume() {
        guard !pending.isEmpty, engine.isRunning else { return }
        generation += 1
        node.stop()
        queued = pending.count
        for (id, buffer) in pending { schedule(id, buffer) }
        node.play()
    }

    func stopPlaying() {
        generation += 1
        queued = 0
        pending = []
        rest = Data()
        outLevel = 0
        node.stop()
    }

    /// A short rising tone: "I am listening".
    func chime() {
        let sr = 24000.0, n = Int(sr * 0.18)
        var d = Data(capacity: n * 2)
        for i in 0..<n {
            let t = Double(i) / sr
            let f = 660 + 440 * t / 0.18
            let env = min(1, Double(i) / 300) * min(1, Double(n - i) / 900)
            let v = Int16(sin(2 * .pi * f * t) * env * 9000)
            withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) }
        }
        play(d)
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
