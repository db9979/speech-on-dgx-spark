import AVFoundation

enum AudioSetup {
    /// Recording and playing in one session: the answer comes from the loudspeaker (or AirPods / the car).
    static func activate() throws {
        let s = AVAudioSession.sharedInstance()
        try s.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker, .allowBluetooth, .allowBluetoothA2DP])
        try s.setActive(true)
    }

    static func microphoneAllowed() async -> Bool {
        await AVAudioApplication.requestRecordPermission()
    }
}

/// Records the question as 16 kHz mono WAV, what the speech recognition on the Spark wants.
final class Recorder {
    static let maxSeconds: TimeInterval = 60
    private var recorder: AVAudioRecorder?
    private let url = FileManager.default.temporaryDirectory.appendingPathComponent("frage.wav")

    func start() throws {
        try AudioSetup.activate()
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
        let r = try AVAudioRecorder(url: url, settings: settings)
        r.isMeteringEnabled = true
        guard r.record(forDuration: Self.maxSeconds) else {
            throw SparkError(message: "Die Aufnahme ließ sich nicht starten.")
        }
        recorder = r
    }

    /// 0 (quiet) to 1 (loud), for the ring around the button.
    var level: Float {
        guard let r = recorder else { return 0 }
        r.updateMeters()
        return max(0, min(1, (r.averagePower(forChannel: 0) + 50) / 50))
    }

    var isRecording: Bool { recorder?.isRecording ?? false }

    /// The recording, or nil when it was too short to hold a question.
    func stop() -> Data? {
        guard let r = recorder else { return nil }
        let seconds = r.currentTime
        r.stop()
        recorder = nil
        guard seconds > 0.4 else { return nil }
        let data = try? Data(contentsOf: url)
        try? FileManager.default.removeItem(at: url)
        return data
    }

    func cancel() {
        recorder?.stop()
        recorder?.deleteRecording()
        recorder = nil
    }
}

/// Plays the streamed answer (16-bit PCM, 24 kHz) piece after piece without gaps.
final class Player {
    private let engine = AVAudioEngine()
    private let node = AVAudioPlayerNode()
    private let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24000, channels: 1, interleaved: false)!
    private var rest = Data()
    private var queued = 0
    private var generation = 0
    /// Called on the main thread when everything queued has been played.
    var onIdle: (() -> Void)?

    init() {
        engine.attach(node)
        engine.connect(node, to: engine.mainMixerNode, format: format)
    }

    var busy: Bool { queued > 0 }

    func play(_ pcm: Data) {
        let data = rest + pcm
        let frames = data.count / 2
        rest = data.count % 2 == 1 ? Data(data.suffix(1)) : Data()
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)) else { return }
        buffer.frameLength = AVAudioFrameCount(frames)
        let out = buffer.floatChannelData![0]
        data.withUnsafeBytes { raw in
            for i in 0..<frames {
                out[i] = Float(Int16(littleEndian: raw.loadUnaligned(fromByteOffset: i * 2, as: Int16.self))) / 32768
            }
        }
        if !engine.isRunning {
            try? AudioSetup.activate()
            do { try engine.start() } catch { return }
        }
        queued += 1
        let gen = generation
        node.scheduleBuffer(buffer) { [weak self] in
            DispatchQueue.main.async {
                guard let self, gen == self.generation else { return }
                self.queued -= 1
                if self.queued == 0 { self.onIdle?() }
            }
        }
        if !node.isPlaying { node.play() }
    }

    func stop() {
        generation += 1
        queued = 0
        rest = Data()
        node.stop()
    }
}
