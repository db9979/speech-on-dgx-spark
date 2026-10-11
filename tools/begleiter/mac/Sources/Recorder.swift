import AVFoundation
import AppKit

/// The converted samples (16 kHz, mono, 16 bit), filled on the audio thread.
final class PCMSink: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()
    private var lastLevel: Double = 0
    let limit: Int

    init(limit: Int) {
        self.limit = limit
    }

    func reset() {
        lock.lock()
        data = Data()
        lastLevel = 0
        lock.unlock()
    }

    /// loudness of the last buffer, 0…1 (only for the little bars on screen)
    var level: Double {
        lock.lock()
        defer { lock.unlock() }
        return lastLevel
    }

    func setLevel(_ l: Double) {
        lock.lock()
        lastLevel = l
        lock.unlock()
    }

    func append(_ d: Data) {
        lock.lock()
        if data.count < limit {
            data.append(d.prefix(limit - data.count))
        }
        lock.unlock()
    }

    func take() -> Data {
        lock.lock()
        defer { lock.unlock() }
        let d = data
        data = Data()
        return d
    }

    var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return data.count
    }
}

/// whether the converter already got the one buffer of this call
private final class Fed {
    var done = false
}

enum RecorderError: Error {
    case noInput
}

/// Records the microphone with AVAudioEngine and converts right away to what the Spark takes:
/// PCM 16 bit, mono, 16 kHz, at most 60 seconds (1.92 MB, under the 2 MB limit).
@MainActor
final class Recorder {
    static let sampleRate = 16000.0
    static let maxSeconds = 60.0

    private var engine: AVAudioEngine?
    private let sink = PCMSink(limit: Int(maxSeconds * sampleRate) * 2)

    var isRecording: Bool { engine != nil }

    /// seconds recorded so far
    var seconds: Double { Double(sink.count) / (Self.sampleRate * 2) }

    /// 0…1, for the level bars
    var level: Double { sink.level }

    static func micAllowed() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .audio)
        default:
            return false
        }
    }

    static func openMicSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
            NSWorkspace.shared.open(url)
        }
    }

    func start() throws {
        guard engine == nil else { return }
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0,
              let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Self.sampleRate,
                                            channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: inFormat, to: outFormat) else {
            throw RecorderError.noInput
        }
        converter.downmix = true
        sink.reset()
        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat,
                         block: Self.makeTap(converter: converter, outFormat: outFormat, sink: sink))
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            throw RecorderError.noInput
        }
        self.engine = engine
    }

    /// Stops and gives the raw samples (without WAV header).
    func stop() -> Data {
        if let engine {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        engine = nil
        return sink.take()
    }

    /// Runs on the audio thread: converts each buffer and adds it to the sink.
    nonisolated private static func makeTap(converter: AVAudioConverter, outFormat: AVAudioFormat,
                                            sink: PCMSink) -> AVAudioNodeTapBlock {
        return { buffer, _ in
            let ratio = outFormat.sampleRate / buffer.format.sampleRate
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
            guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) else { return }
            let fed = Fed()
            var error: NSError?
            let status = converter.convert(to: out, error: &error) { _, inputStatus in
                if fed.done {
                    inputStatus.pointee = .noDataNow
                    return nil
                }
                fed.done = true
                inputStatus.pointee = .haveData
                return buffer
            }
            guard status != .error, out.frameLength > 0, let ch = out.int16ChannelData else { return }
            let n = Int(out.frameLength)
            sink.append(Data(bytes: ch[0], count: n * 2))
            var sum = 0.0
            for i in 0..<n {
                let v = Double(ch[0][i]) / 32768
                sum += v * v
            }
            // RMS on a rough dB scale: about -50 dB -> 0, 0 dB -> 1
            let rms = (sum / Double(n)).squareRoot()
            let db = 20 * log10(max(rms, 1e-6))
            sink.setLevel(min(max((db + 50) / 50, 0), 1))
        }
    }
}
