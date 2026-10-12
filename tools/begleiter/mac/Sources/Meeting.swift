import AVFoundation
import AppKit
import CoreMedia
import ScreenCaptureKit
import SwiftUI

/// whether the converter already got the one buffer of this call
private final class MeetingFed {
    var done = false
}

/// Converts one buffer to 16 kHz mono Int16 (little endian) — used on the audio threads.
enum MeetingConvert {
    static let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Double(MeetingAudio.rate),
                                         channels: 1, interleaved: true)

    static func convert(_ buffer: AVAudioPCMBuffer, with converter: AVAudioConverter) -> Data? {
        guard let outFormat else { return nil }
        let ratio = outFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) else { return nil }
        let fed = MeetingFed()
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
        guard status != .error, out.frameLength > 0, let ch = out.int16ChannelData else { return nil }
        return Data(bytes: ch[0], count: Int(out.frameLength) * 2)
    }
}

/// The system sound through ScreenCaptureKit (macOS 13+): audio buffers in, 16 kHz mono into the sink.
final class SystemAudioTap: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    let sink: PCMSink
    private let lock = NSLock()
    private var converter: AVAudioConverter?
    private var inRate: Double = 0
    private var inChannels: UInt32 = 0
    private var inFlags: UInt32 = 0
    private(set) var stopped = false

    init(sink: PCMSink) {
        self.sink = sink
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, CMSampleBufferDataIsReady(sampleBuffer),
              let fd = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbdPtr = CMAudioFormatDescriptionGetStreamBasicDescription(fd) else { return }
        let frames = CMSampleBufferGetNumSamples(sampleBuffer)
        guard frames > 0 else { return }
        var asbd = asbdPtr.pointee
        lock.lock()
        defer { lock.unlock() }
        if converter == nil || asbd.mSampleRate != inRate || asbd.mChannelsPerFrame != inChannels || asbd.mFormatFlags != inFlags {
            guard let inFormat = AVAudioFormat(streamDescription: &asbd), let outFormat = MeetingConvert.outFormat,
                  let c = AVAudioConverter(from: inFormat, to: outFormat) else { return }
            c.downmix = true
            converter = c
            inRate = asbd.mSampleRate
            inChannels = asbd.mChannelsPerFrame
            inFlags = asbd.mFormatFlags
        }
        guard let converter,
              let buf = AVAudioPCMBuffer(pcmFormat: converter.inputFormat, frameCapacity: AVAudioFrameCount(frames)) else { return }
        buf.frameLength = AVAudioFrameCount(frames)
        let st = CMSampleBufferCopyPCMDataIntoAudioBufferList(sampleBuffer, at: 0, frameCount: Int32(frames),
                                                               into: buf.mutableAudioBufferList)
        guard st == noErr, let d = MeetingConvert.convert(buf, with: converter) else { return }
        sink.append(d)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        lock.lock()
        stopped = true
        lock.unlock()
    }
}

/// Part "meeting" (Besprechung mitschreiben): only by click or ⌥⌘R, the first time after a consent dialog. While it
/// runs a red pill is always on top ("Besprechung wird mitgeschrieben · mm:ss · Beenden"). Microphone plus the
/// system sound (ScreenCaptureKit, if the permission "Bildschirmaufnahme" is there; else microphone only, and the
/// pill says so), mixed to mono 16 kHz, every 30 s a WAV piece to the Spark. Max 3 h. Nothing is stored on the Mac.
@MainActor
final class Meeting: ObservableObject {
    static let shared = Meeting()
    static let consentKey = "meeting.consent"

    enum Phase: Equatable {
        case idle, starting, running, ending
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var elapsed = 0
    @Published private(set) var micOnly = false
    @Published private(set) var chars = 0
    @Published private(set) var note = ""

    private var id: String?
    private var started = Date()
    private var engine: AVAudioEngine?
    private var stream: SCStream?
    private var systemTap: SystemAudioTap?
    private let micSink = PCMSink(limit: Int(MeetingAudio.bufferSeconds) * MeetingAudio.rate * 2)
    private let sysSink = PCMSink(limit: Int(MeetingAudio.bufferSeconds) * MeetingAudio.rate * 2)
    private var ticker: Task<Void, Never>?
    private var lastChunk = Date()
    private var uploads: Task<Void, Never>?
    private var failedPieces = 0
    private var configObserver: NSObjectProtocol?

    /// the microphone is the Begleiter's own (for "quiet")
    var capturing: Bool { phase == .running || phase == .starting }

    var running: Bool { phase != .idle }

    func toggle() {
        switch phase {
        case .idle: Task { await start() }
        case .running: Task { await end() }
        case .starting, .ending: break
        }
    }

    // ------------------------------------------------------------------ start

    func start() async {
        let model = AppModel.shared
        guard let client = model.client else {
            Windows.showPairing()
            return
        }
        guard model.part("meeting") else {
            HUD.show(AppModel.offHint("Besprechung mitschreiben"))
            return
        }
        guard phase == .idle else { return }
        guard consent() else { return }
        guard await Recorder.micAllowed() else {
            NSApp.activate(ignoringOtherApps: true)
            let a = NSAlert()
            a.messageText = "Kein Zugriff aufs Mikrofon"
            a.informativeText = "Zum Mitschreiben braucht der Spark-Begleiter das Mikrofon. Erlauben unter Systemeinstellungen → Datenschutz & Sicherheit → Mikrofon."
            a.addButton(withTitle: "Systemeinstellungen öffnen")
            a.addButton(withTitle: "Abbrechen")
            if a.runModal() == .alertFirstButtonReturn { Recorder.openMicSettings() }
            return
        }
        phase = .starting
        note = ""
        chars = 0
        failedPieces = 0
        elapsed = 0
        MeetingPill.show(self)
        do {
            id = try await client.meetingStart()
        } catch {
            phase = .idle
            MeetingPill.hide()
            HUD.show(model.absorb(error), symbol: "exclamationmark.triangle")
            return
        }
        micSink.reset()
        sysSink.reset()
        guard startMic() else {
            phase = .idle
            MeetingPill.hide()
            if let id { Task { _ = try? await client.meetingEnd(id: id) } }
            id = nil
            HUD.show("Das Mikrofon lässt sich nicht öffnen.", symbol: "mic.slash")
            return
        }
        micOnly = !(await startSystemAudio())
        started = Date()
        lastChunk = started
        phase = .running
        MeetingPill.show(self)
        if micOnly {
            HUD.show("Nur das Mikrofon wird mitgeschrieben: Für den Ton des Macs (die anderen im Anruf) braucht der Begleiter die Freigabe „Bildschirmaufnahme“ (Einstellungen → Berechtigungen).",
                     symbol: "mic", seconds: 9)
        }
        ticker?.cancel()
        ticker = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 500_000_000)
                guard let self, self.phase == .running else { return }
                let now = Date()
                let s = Int(now.timeIntervalSince(self.started))
                if s != self.elapsed { self.elapsed = s }
                if Double(s) >= MeetingAudio.maxSeconds {
                    self.note = "3 Stunden erreicht."
                    await self.end()
                    return
                }
                if now.timeIntervalSince(self.lastChunk) >= MeetingAudio.chunkSeconds {
                    self.lastChunk = now
                    self.sendPiece()
                }
            }
        }
    }

    /// "Alle Beteiligten müssen einverstanden sein …" — the first time on this Mac
    private func consent() -> Bool {
        if UserDefaults.standard.bool(forKey: Self.consentKey) { return true }
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Besprechung mitschreiben"
        a.informativeText = """
            Alle Beteiligten müssen einverstanden sein, dass mitgeschrieben wird.

            Der Begleiter nimmt das Mikrofon und – wenn erlaubt – den Ton des Macs auf und schickt ihn alle 30 Sekunden \
            an deinen eigenen Spark. Auf dem Mac bleibt nichts gespeichert. Solange es läuft, ist oben eine rote \
            Leiste zu sehen; höchstens 3 Stunden.
            """
        a.addButton(withTitle: "Verstanden, starten")
        let no = a.addButton(withTitle: "Abbrechen")
        no.keyEquivalent = "\u{1b}"
        guard a.runModal() == .alertFirstButtonReturn else { return false }
        UserDefaults.standard.set(true, forKey: Self.consentKey)
        return true
    }

    private func startMic() -> Bool {
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0, let outFormat = MeetingConvert.outFormat,
              let converter = AVAudioConverter(from: inFormat, to: outFormat) else { return false }
        converter.downmix = true
        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat, block: Self.makeTap(converter: converter, sink: micSink))
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            return false
        }
        self.engine = engine
        // another microphone: open anew, the meeting goes on
        configObserver = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange,
                                                                object: engine, queue: .main) { _ in
            Task { @MainActor in Meeting.shared.reopenMic() }
        }
        return true
    }

    private func reopenMic() {
        guard phase == .running else { return }
        stopMic()
        if !startMic() { note = "Das Mikrofon ist weg – es läuft nur noch der Ton des Macs." }
    }

    private func stopMic() {
        if let o = configObserver {
            NotificationCenter.default.removeObserver(o)
            configObserver = nil
        }
        if let engine {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        engine = nil
    }

    nonisolated private static func makeTap(converter: AVAudioConverter, sink: PCMSink) -> AVAudioNodeTapBlock {
        return { buffer, _ in
            if let d = MeetingConvert.convert(buffer, with: converter) { sink.append(d) }
        }
    }

    /// true when the system sound runs
    private func startSystemAudio() async -> Bool {
        guard ScreenAsk.permitted else { return false }
        guard #available(macOS 13.0, *) else { return false }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            guard let display = content.displays.first else { return false }
            let filter = SCContentFilter(display: display, excludingWindows: [])
            let cfg = SCStreamConfiguration()
            cfg.capturesAudio = true
            cfg.excludesCurrentProcessAudio = true
            cfg.sampleRate = 48000
            cfg.channelCount = 2
            // the picture is not wanted: as small and as rare as possible
            cfg.width = 2
            cfg.height = 2
            cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
            cfg.showsCursor = false
            let tap = SystemAudioTap(sink: sysSink)
            let s = SCStream(filter: filter, configuration: cfg, delegate: tap)
            let queue = DispatchQueue(label: "de.db9979.spark.begleiter.meeting-audio")
            try s.addStreamOutput(tap, type: .audio, sampleHandlerQueue: queue)
            try s.addStreamOutput(tap, type: .screen, sampleHandlerQueue: queue)
            try await s.startCapture()
            stream = s
            systemTap = tap
            return true
        } catch {
            stream = nil
            systemTap = nil
            return false
        }
    }

    private func stopSystemAudio() async {
        if let s = stream {
            try? await s.stopCapture()
        }
        stream = nil
        systemTap = nil
    }

    // ------------------------------------------------------------------ the pieces

    /// takes what is there (≤ 55 s each source), mixes and sends it after the pieces before it
    private func sendPiece(last: Bool = false) {
        let pcm = MeetingAudio.mix(micSink.take(), sysSink.take())
        guard let id, let client = AppModel.shared.client else { return }
        guard pcm.count >= MeetingAudio.rate else { return }    // under half a second: nothing to say
        let wav = Wav.wrap(pcm: pcm, sampleRate: MeetingAudio.rate)
        let before = uploads
        uploads = Task { @MainActor [weak self] in
            _ = await before?.value
            await self?.upload(wav, id: id, client: client)
        }
    }

    private func upload(_ wav: Data, id: String, client: SparkClient) async {
        for attempt in 0..<2 {
            do {
                chars = try await client.meetingChunk(id: id, wav: wav)
                return
            } catch is CancellationError {
                return
            } catch {
                let m = AppModel.shared.absorb(error)
                if let p = error as? SparkProblem {
                    switch p {
                    case .unknownDevice, .off, .notaus:
                        note = m
                        if phase == .running { Task { await self.abort(m) } }
                        return
                    default: break
                    }
                }
                if attempt == 0 { try? await Task.sleep(nanoseconds: 5_000_000_000) }
            }
        }
        failedPieces += 1
        note = failedPieces == 1 ? "Ein Stück kam nicht beim Spark an." : "\(failedPieces) Stücke kamen nicht beim Spark an."
    }

    // ------------------------------------------------------------------ end

    private func stopCapture() async {
        ticker?.cancel()
        ticker = nil
        stopMic()
        await stopSystemAudio()
    }

    func end() async {
        guard phase == .running else { return }
        phase = .ending
        MeetingPill.show(self)
        await stopCapture()
        sendPiece(last: true)
        _ = await uploads?.value
        uploads = nil
        micSink.reset()
        sysSink.reset()
        guard let id, let client = AppModel.shared.client else {
            finishIdle()
            return
        }
        do {
            let r = try await client.meetingEnd(id: id)
            finishIdle()
            MeetingResultBox.show(MeetingResultBox(id: id, result: r,
                                                   remarkable: AppModel.shared.config?.v4.meetingRemarkable ?? false))
        } catch {
            let m = AppModel.shared.absorb(error)
            finishIdle()
            NSApp.activate(ignoringOtherApps: true)
            let a = NSAlert()
            a.messageText = "Die Besprechung ließ sich nicht abschließen."
            a.informativeText = m
            a.runModal()
        }
    }

    /// the part went off, or the Spark said no: stop without a summary
    func abort(_ why: String) async {
        guard phase != .idle else { return }
        await stopCapture()
        uploads?.cancel()
        uploads = nil
        micSink.reset()
        sysSink.reset()
        finishIdle()
        HUD.show("Mitschreiben beendet: " + why, symbol: "exclamationmark.triangle", seconds: 8)
    }

    private func finishIdle() {
        phase = .idle
        id = nil
        elapsed = 0
        MeetingPill.hide()
    }

    func apply(on: Bool) {
        if !on && phase != .idle {
            Task { await self.abort("Der Teil ist im Panel aus.") }
        }
    }
}

// ------------------------------------------------------------------ the red pill

struct MeetingPillView: View {
    @ObservedObject var meeting: Meeting

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(Color.white)
                .frame(width: 9, height: 9)
            VStack(alignment: .leading, spacing: 1) {
                Text(verbatim: title)
                    .font(.system(size: 13, weight: .semibold))
                if !sub.isEmpty {
                    Text(verbatim: sub)
                        .font(.system(size: 11))
                        .opacity(0.85)
                }
            }
            if meeting.phase == .running {
                Text(verbatim: MeetingAudio.clock(meeting.elapsed))
                    .font(.system(size: 12, design: .monospaced))
                Button("Beenden") { Task { await meeting.end() } }
                    .buttonStyle(MeetingButtonStyle())
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .foregroundColor(.white)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Capsule().fill(Theme.bad))
        .overlay(Capsule().stroke(Color.white.opacity(0.25), lineWidth: 1))
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(verbatim: "Besprechung wird mitgeschrieben"))
    }

    private var title: String {
        switch meeting.phase {
        case .starting: return "Besprechung startet …"
        case .ending: return "Wird zusammengefasst …"
        default: return "Besprechung wird mitgeschrieben"
        }
    }

    private var sub: String {
        if !meeting.note.isEmpty { return meeting.note }
        if meeting.phase == .running && meeting.micOnly { return "nur Mikrofon (ohne Ton des Macs)" }
        return ""
    }
}

struct MeetingButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Theme.bad)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(Capsule().fill(Color.white))
            .opacity(configuration.isPressed ? 0.8 : 1)
            .contentShape(Capsule())
    }
}

@MainActor
enum MeetingPill {
    private static var panel: NSPanel?

    static func show(_ m: Meeting) {
        let p = panel ?? FloatingPanel.make()
        p.level = .screenSaver           // above full-screen apps and presentations; it cannot be hidden
        panel = p
        FloatingPanel.show(p, MeetingPillView(meeting: m))
        if let s = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame {
            p.setFrameOrigin(NSPoint(x: s.maxX - p.frame.width - 16, y: s.maxY - p.frame.height - 10))
        }
    }

    static func hide() {
        panel?.orderOut(nil)
    }
}

// ------------------------------------------------------------------ the window after the end

@MainActor
final class MeetingResultBox: ObservableObject {
    static let windowID = "meeting"

    let id: String
    let result: MeetingResult
    let remarkable: Bool
    @Published var picked: Set<Int> = []
    @Published private(set) var busy = false
    @Published private(set) var status = ""
    @Published private(set) var failed = false

    init(id: String, result: MeetingResult, remarkable: Bool) {
        self.id = id
        self.result = result
        self.remarkable = remarkable
    }

    static func show(_ box: MeetingResultBox) {
        Windows.shared.close(windowID)
        Windows.shared.show(windowID, title: "Besprechung", size: NSSize(width: 560, height: 560)) {
            MeetingResultView(box: box)
        }
    }

    func keep(remarkable toRemarkable: Bool) {
        guard !busy, let client = AppModel.shared.client else { return }
        let tasks = toRemarkable ? [] : picked.sorted()
        if !toRemarkable && tasks.isEmpty {
            status = "Erst Aufgaben ankreuzen."
            failed = true
            return
        }
        busy = true
        status = ""
        Task { @MainActor in
            do {
                let r = try await client.meetingKeep(id: id, tasks: tasks, remarkable: toRemarkable)
                if toRemarkable {
                    status = r.remarkable ? "Liegt auf dem reMarkable." : "Das reMarkable hat es nicht angenommen."
                    failed = !r.remarkable
                } else {
                    status = r.reminders == 1 ? "1 Erinnerung angelegt." : "\(r.reminders) Erinnerungen angelegt."
                    failed = false
                }
            } catch {
                status = AppModel.shared.absorb(error)
                failed = true
            }
            busy = false
        }
    }
}

struct MeetingResultView: View {
    @ObservedObject var box: MeetingResultBox

    var body: some View {
        VStack(spacing: 0) {
            GradientBar()
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    FaceView(size: 28)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(verbatim: "Besprechung – Zusammenfassung")
                            .font(.system(size: 14, weight: .semibold))
                        Text(verbatim: "Nichts davon ist auf dem Mac gespeichert.")
                            .font(.system(size: 11))
                            .foregroundColor(Theme.muted)
                    }
                    Spacer()
                }
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(verbatim: box.result.summary.isEmpty ? "Keine Zusammenfassung." : box.result.summary)
                            .font(.system(size: 13))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        if !box.result.tasks.isEmpty {
                            Text(verbatim: "Aufgaben")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(Theme.muted)
                            ForEach(box.result.tasks) { t in
                                Toggle(isOn: binding(t.index)) {
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(verbatim: t.text)
                                            .font(.system(size: 13))
                                            .fixedSize(horizontal: false, vertical: true)
                                        if let due = t.due {
                                            Text(verbatim: "bis " + IsoDate.short(due))
                                                .font(.system(size: 11))
                                                .foregroundColor(Theme.muted)
                                        }
                                    }
                                }
                                .toggleStyle(.checkbox)
                            }
                        }
                    }
                    .padding(12)
                }
                .background(RoundedRectangle(cornerRadius: 10).fill(Theme.soft))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1))
                if !box.status.isEmpty {
                    Text(Wege.text(box.status))
                        .font(.system(size: 12))
                        .foregroundColor(box.failed ? Theme.bad : Theme.ok)
                }
                HStack(spacing: 8) {
                    Button("Kopieren") { Clip.put(box.result.summary) }
                        .buttonStyle(SoftButtonStyle())
                    Spacer()
                    if box.busy { ProgressView().controlSize(.small) }
                    if box.remarkable {
                        Button("Aufs reMarkable") { box.keep(remarkable: true) }
                            .buttonStyle(SoftButtonStyle())
                            .disabled(box.busy)
                    }
                    if !box.result.tasks.isEmpty {
                        Button("Ausgewählte als Erinnerung") { box.keep(remarkable: false) }
                            .buttonStyle(PrimaryButtonStyle())
                            .disabled(box.busy || box.picked.isEmpty)
                    }
                    Button("Schließen") { Windows.shared.close(MeetingResultBox.windowID) }
                        .buttonStyle(SoftButtonStyle())
                        .keyboardShortcut(.cancelAction)
                }
            }
            .padding(14)
        }
        .background(Theme.card)
        .foregroundColor(Theme.fg)
        .frame(minWidth: 440, minHeight: 360)
    }

    private func binding(_ i: Int) -> Binding<Bool> {
        Binding(get: { box.picked.contains(i) },
                set: { on in if on { box.picked.insert(i) } else { box.picked.remove(i) } })
    }
}
