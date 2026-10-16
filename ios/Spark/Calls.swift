import AVFoundation
import CallKit
import PushKit
import SwiftUI
import UIKit
import WebRTC

// Anrufe (app/panel/anrufe.py, plaene/iphone-aufwerten.md, Dominik 2026-10-16 "1a"): voice and video with another
// profile of this Spark, in a chat of two. The Spark only brings the two devices together (start, answer, signal, end
// over /api/anrufe/*, its news over the Chats stream); sound and picture go from device to device (WebRTC, DTLS-SRTP),
// from outside through the Spark's own Vermittler (TURN). The iPhone rings like a phone call (CallKit), also locked or
// with the app closed: Apple's VoIP push carries only the call's random id, the app asks the Spark who calls.
// The same protocol as the panel's anrufe.js: the caller makes the offer once the other side took the call.

/// What the call screen shows.
enum CallPhase: Equatable {
    case idle
    case calling        // ringing at the other side
    case ringing        // ringing here (CallKit shows it)
    case connecting
    case talking
    case ended(String)  // the reason in words, shown a moment
}

/// One call at a time, for the whole app.
@MainActor
final class CallCenter: ObservableObject {
    static let shared = CallCenter()

    @Published private(set) var phase: CallPhase = .idle
    @Published private(set) var name = ""
    @Published private(set) var video = false
    @Published private(set) var muted = false
    @Published private(set) var cameraOff = false
    @Published private(set) var speaker = false
    @Published private(set) var started: Date?
    @Published private(set) var remoteVideo: RTCVideoTrack?
    @Published private(set) var localVideo: RTCVideoTrack?

    /// a call runs or rings: the assistant does not listen meanwhile (Assistant.canWake)
    var active: Bool { if case .idle = phase { return false }; if case .ended = phase { return false }; return true }

    /// this app's device id for signals (a fresh one per start, like a page in the browser)
    private let dev = (0..<6).map { _ in String(format: "%02x", UInt8.random(in: 0...255)) }.joined()
    private let bridge = CallBridge()
    private lazy var provider: CXProvider = {
        let c = CXProviderConfiguration()
        c.supportsVideo = true
        c.maximumCallsPerCallGroup = 1
        c.maximumCallGroups = 1
        c.supportedHandleTypes = [.generic]
        c.includesCallsInRecents = false   // the Spark keeps one line per call in the chat; nothing in the Phone app
        let p = CXProvider(configuration: c)
        p.setDelegate(bridge, queue: nil)
        return p
    }()
    private let controller = CXCallController()
    private var registry: PKPushRegistry?

    private var uuid: UUID?
    private var cur = ""   // the call's id on the Spark
    private var cid = ""
    private var outgoing = false
    private var servers: [RTCIceServer] = []
    private var pc: RTCPeerConnection?
    private var audioTrack: RTCAudioTrack?
    private var capturer: RTCCameraVideoCapturer?
    private var front = true
    private var pending: [[String: Any]] = []        // signals that came before the connection was made
    private var candidates: [RTCIceCandidate] = []   // candidates that came before the other side's description
    private var listen: Task<Void, Never>?
    private var answered = false

    private static let factory: RTCPeerConnectionFactory = {
        RTCInitializeSSL()
        return RTCPeerConnectionFactory(encoderFactory: RTCDefaultVideoEncoderFactory(),
                                        decoderFactory: RTCDefaultVideoDecoderFactory())
    }()

    private init() {
        bridge.center = self
        // CallKit hands the audio session over; WebRTC plays and records only while it is active
        RTCAudioSession.sharedInstance().useManualAudio = true
        RTCAudioSession.sharedInstance().isAudioEnabled = false
    }

    // ---------------------------------------------------------------- ringing through Apple (PushKit)
    private static let wantKey = "callsVoip"

    /// At start-up: the registry must exist at once, or a VoIP push that woke the app is lost (and iOS stops
    /// sending them). Only when calls were allowed last time.
    func wake() {
        if UserDefaults.standard.bool(forKey: Self.wantKey) { register() }
    }

    /// What the Spark allows now (hello): calls and Apple push on → this iPhone rings for calls, else not.
    func follow(_ a: Allowed) {
        let want = a.calls && a.push
        UserDefaults.standard.set(want, forKey: Self.wantKey)
        if want { register() } else if let r = registry { r.desiredPushTypes = [] }
    }

    private func register() {
        if registry == nil {
            let r = PKPushRegistry(queue: .main)
            r.delegate = bridge
            registry = r
        }
        registry?.desiredPushTypes = [.voIP]
    }

    func token(_ data: Data) {
        let hex = data.map { String(format: "%02x", $0) }.joined()
        Task { _ = try? await SparkAPI.current?.pushToken(hex, kind: "voip") }
    }

    /// A VoIP push: report the call to CallKit at once (Apple's rule), then ask the Spark who calls.
    func pushed(_ payload: [AnyHashable: Any], done: @escaping () -> Void) {
        let id = payload["call"] as? String ?? ""
        let u = Self.callUUID(id)
        let update = CXCallUpdate()
        update.remoteHandle = CXHandle(type: .generic, value: String(localized: "Spark-Anruf"))
        update.localizedCallerName = String(localized: "Spark-Anruf")
        update.hasVideo = false
        update.supportsHolding = false
        update.supportsGrouping = false
        update.supportsUngrouping = false
        update.supportsDTMF = false
        let fresh = Self.callId(id) && !active
        provider.reportNewIncomingCall(with: u, update: update) { [weak self] error in
            done()
            // not a call id, or already in another call: it showed and ends at once (a second push for the running
            // call is refused by CallKit as the same UUID and changes nothing)
            guard !fresh, error == nil else { return }
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self?.provider.reportCall(with: u, endedAt: nil, reason: .failed) }
            }
        }
        guard fresh else { return }
        start(incoming: id, uuid: u)
    }

    private func start(incoming id: String, uuid u: UUID) {
        reset()
        uuid = u
        cur = id
        outgoing = false
        phase = .ringing
        Conversation.shared.stop()
        listenToSpark()
        Task {
            guard let api = SparkAPI.current, let d = try? await api.callInfo(id) else { return }
            guard cur == id else { return }
            if d["state"] as? String != "ring" {
                finish(String(localized: "Anruf vorbei."), reason: .remoteEnded)
                return
            }
            cid = d["id"] as? String ?? ""
            name = String((d["name"] as? String ?? "").prefix(60))
            video = d["video"] as? Bool ?? false
            let update = CXCallUpdate()
            update.remoteHandle = CXHandle(type: .generic, value: name)
            update.localizedCallerName = name
            update.hasVideo = video
            provider.reportCall(with: u, updated: update)
        }
    }

    // ---------------------------------------------------------------- calling from a chat
    /// From a chat of two: CallKit starts the call (it then shows in the status bar and works with AirPods).
    func dial(chat: String, name: String, video: Bool) {
        guard !active, SparkAPI.current != nil else { return }
        reset()
        let u = UUID()
        uuid = u
        cid = chat
        self.name = String(name.prefix(60))
        self.video = video
        outgoing = true
        phase = .calling
        Conversation.shared.stop()
        let action = CXStartCallAction(call: u, handle: CXHandle(type: .generic, value: self.name))
        action.isVideo = video
        controller.request(CXTransaction(action: action)) { [weak self] error in
            guard error != nil else { return }
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self?.finish(String(localized: "Anruf ging nicht."), reason: nil) }
            }
        }
        show()
    }

    func startAction(_ action: CXStartCallAction) {
        guard action.callUUID == uuid, let api = SparkAPI.current else { action.fail(); return }
        Task {
            do {
                try configureAudio()
                makeLocal()
                let r = try await api.callStart(chat: cid, video: video, dev: dev)
                servers = Self.servers(r["servers"])
                let state = r["state"] as? String ?? ""
                guard state == "ring", let id = r["call"] as? String, Self.callId(id) else {
                    action.fulfill()
                    finish(state == "busy" ? String(localized: "Besetzt.") : String(localized: "Nimmt gerade nicht ab."),
                           reason: .unanswered)
                    return
                }
                cur = id
                listenToSpark()
                action.fulfill()
                provider.reportOutgoingCall(with: action.callUUID, startedConnectingAt: nil)
            } catch {
                action.fail()
                finish(error.localizedDescription, reason: nil)
            }
        }
    }

    // ---------------------------------------------------------------- answering, ending
    func answerAction(_ action: CXAnswerCallAction) {
        guard action.callUUID == uuid, !cur.isEmpty, let api = SparkAPI.current else { action.fail(); return }
        phase = .connecting
        answered = true
        show()
        Task {
            do {
                try configureAudio()
                servers = Self.servers(try await api.object("GET", "api/anrufe/ice")["servers"])
                makeLocal()
                makeConnection()
                _ = try await api.post("api/anrufe/answer", ["call": cur, "dev": dev])
                action.fulfill()
            } catch {
                action.fail()
                finish(error.localizedDescription, reason: .failed)
            }
        }
    }

    func endAction(_ action: CXEndCallAction) {
        guard action.callUUID == uuid else { action.fulfill(); return }
        let id = cur
        let why = !outgoing && !answered ? "reject" : "hangup"
        action.fulfill()
        cleanUp(why == "reject" ? String(localized: "Abgelehnt.") : String(localized: "Aufgelegt."))
        guard Self.callId(id), let api = SparkAPI.current else { return }
        Task { _ = try? await api.post("api/anrufe/end", ["call": id, "dev": dev, "why": why]) }
    }

    func muteAction(_ action: CXSetMutedCallAction) {
        muted = action.isMuted
        audioTrack?.isEnabled = !action.isMuted
        action.fulfill()
    }

    /// The red button on the call screen.
    func hangUp() {
        guard let u = uuid else { cleanUp(nil); return }
        controller.request(CXTransaction(action: CXEndCallAction(call: u))) { _ in }
    }

    func toggleMute() {
        guard let u = uuid else { return }
        controller.request(CXTransaction(action: CXSetMutedCallAction(call: u, muted: !muted))) { _ in }
    }

    func toggleCamera() {
        cameraOff.toggle()
        localVideo?.isEnabled = !cameraOff
    }

    func switchCamera() {
        front.toggle()
        startCapture()
    }

    func toggleSpeaker() {
        speaker.toggle()
        try? AVAudioSession.sharedInstance().overrideOutputAudioPort(speaker ? .speaker : .none)
    }

    func audioOn(_ session: AVAudioSession) {
        RTCAudioSession.sharedInstance().audioSessionDidActivate(session)
        RTCAudioSession.sharedInstance().isAudioEnabled = true
        if speaker { try? session.overrideOutputAudioPort(.speaker) }
    }

    func audioOff(_ session: AVAudioSession) {
        RTCAudioSession.sharedInstance().audioSessionDidDeactivate(session)
        RTCAudioSession.sharedInstance().isAudioEnabled = false
    }

    func providerReset() { cleanUp(nil) }

    // ---------------------------------------------------------------- news from the Spark (the Chats stream)
    private func listenToSpark() {
        listen?.cancel()
        listen = Task { [weak self] in
            while !Task.isCancelled {
                guard let api = SparkAPI.current else { return }
                do {
                    for try await ev in api.chatEvents() {
                        guard let self else { return }
                        await self.event(ev)
                    }
                } catch {}
                try? await Task.sleep(for: .seconds(2))   // the stream ends now and then: open it again
            }
        }
    }

    private func event(_ ev: [String: Any]) async {
        guard let type = ev["type"] as? String, type.hasPrefix("call"), ev["call"] as? String == cur, !cur.isEmpty else { return }
        switch type {
        case "call_taken" where ev["dev"] as? String != dev && !answered:
            finish(String(localized: "Auf einem anderen Gerät angenommen."), reason: .answeredElsewhere)
        case "call_ok" where outgoing && pc == nil:
            phase = .connecting
            makeConnection()
            guard let pc else { return }
            do {
                let offer = try await Self.offer(pc, video: video)
                try await Self.setLocal(pc, offer)
                await send(["sdp": ["type": "offer", "sdp": offer.sdp]])
            } catch { hangUp() }
        case "call_sig" where ev["to"] as? String == dev:
            await signal(ev["data"] as? [String: Any] ?? [:])
        case "call_end":
            let why = ev["why"] as? String ?? ""
            let text: String
            switch why {
            case "reject": text = String(localized: "Abgelehnt.")
            case "missed": text = String(localized: "Nicht angenommen.")
            case "busy", "quiet": text = String(localized: "Nimmt gerade nicht ab.")
            default: text = String(localized: "Aufgelegt.")
            }
            finish(text, reason: why == "missed" ? .unanswered : why == "reject" && !outgoing ? .declinedElsewhere : .remoteEnded)
        default: break
        }
    }

    private func signal(_ d: [String: Any]) async {
        guard let pc else { pending.append(d); return }
        do {
            if let s = d["sdp"] as? [String: Any], let text = s["sdp"] as? String, let kind = s["type"] as? String {
                let desc = RTCSessionDescription(type: kind == "offer" ? .offer : .answer, sdp: text)
                try await Self.setRemote(pc, desc)
                if kind == "offer" {
                    let answer = try await Self.answer(pc, video: video)
                    try await Self.setLocal(pc, answer)
                    await send(["sdp": ["type": "answer", "sdp": answer.sdp]])
                }
                for c in candidates { pc.add(c) { _ in } }
                candidates = []
            } else if let c = d["ice"] as? [String: Any], let sdp = c["candidate"] as? String {
                let cand = RTCIceCandidate(sdp: sdp, sdpMLineIndex: Int32((c["sdpMLineIndex"] as? NSNumber)?.intValue ?? 0),
                                           sdpMid: c["sdpMid"] as? String)
                if pc.remoteDescription != nil { pc.add(cand) { _ in } } else { candidates.append(cand) }
            }
        } catch {
            phase = .ended(String(localized: "Verbindung klappt nicht."))
        }
    }

    private func send(_ data: [String: Any]) async {
        guard Self.callId(cur), let api = SparkAPI.current else { return }
        _ = try? await api.post("api/anrufe/signal", ["call": cur, "dev": dev, "data": data])
    }

    // ---------------------------------------------------------------- the connection (WebRTC)
    private func configureAudio() throws {
        let s = AVAudioSession.sharedInstance()
        try s.setCategory(.playAndRecord, mode: video ? .videoChat : .voiceChat, options: [.allowBluetooth, .allowBluetoothA2DP])
        speaker = video
    }

    private func makeLocal() {
        let f = Self.factory
        if audioTrack == nil {
            let source = f.audioSource(with: RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil))
            audioTrack = f.audioTrack(with: source, trackId: "a0")
        }
        if video && localVideo == nil {
            let source = f.videoSource()
            capturer = RTCCameraVideoCapturer(delegate: source)
            localVideo = f.videoTrack(with: source, trackId: "v0")
            startCapture()
        }
    }

    private func startCapture() {
        guard let capturer else { return }
        let want: AVCaptureDevice.Position = front ? .front : .back
        guard let device = RTCCameraVideoCapturer.captureDevices().first(where: { $0.position == want })
                ?? RTCCameraVideoCapturer.captureDevices().first else { return }
        // the format closest to 1280×720 (as the panel asks for), at most 30 pictures a second
        let formats = RTCCameraVideoCapturer.supportedFormats(for: device)
        guard let format = formats.min(by: { a, b in
            let x = CMVideoFormatDescriptionGetDimensions(a.formatDescription), y = CMVideoFormatDescriptionGetDimensions(b.formatDescription)
            return abs(Int(x.width) - 1280) + abs(Int(x.height) - 720) < abs(Int(y.width) - 1280) + abs(Int(y.height) - 720)
        }) else { return }
        let fps = min(30, Int(format.videoSupportedFrameRateRanges.map { $0.maxFrameRate }.max() ?? 30))
        capturer.stopCapture()
        capturer.startCapture(with: device, format: format, fps: fps)
    }

    private func makeConnection() {
        guard pc == nil else { return }
        let config = RTCConfiguration()
        config.iceServers = servers
        config.sdpSemantics = .unifiedPlan
        config.continualGatheringPolicy = .gatherContinually
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: ["DtlsSrtpKeyAgreement": kRTCMediaConstraintsValueTrue])
        guard let pc = Self.factory.peerConnection(with: config, constraints: constraints, delegate: bridge) else {
            phase = .ended(String(localized: "Verbindung klappt nicht."))
            return
        }
        self.pc = pc
        if let audioTrack { pc.add(audioTrack, streamIds: ["s0"]) }
        if let localVideo { pc.add(localVideo, streamIds: ["s0"]) }
        let waiting = pending
        pending = []
        Task { for d in waiting { await signal(d) } }
    }

    func candidate(_ c: RTCIceCandidate) {
        var ice: [String: Any] = ["candidate": c.sdp, "sdpMLineIndex": Int(c.sdpMLineIndex)]
        if let mid = c.sdpMid { ice["sdpMid"] = mid }
        Task { await send(["ice": ice]) }
    }

    func remote(_ track: RTCMediaStreamTrack) {
        if let v = track as? RTCVideoTrack { remoteVideo = v }
    }

    func state(_ s: RTCPeerConnectionState) {
        switch s {
        case .connected:
            if started == nil {
                started = Date()
                if outgoing, let u = uuid { provider.reportOutgoingCall(with: u, connectedAt: nil) }
            }
            phase = .talking
        case .failed:
            phase = .connecting   // the stream may still bring a new way; ending stays with the people
        default: break
        }
    }

    // ---------------------------------------------------------------- the end
    /// The other side or the Spark ended it: CallKit learns why, the screen shows it a moment.
    private func finish(_ text: String, reason: CXCallEndedReason?) {
        if let u = uuid, let reason { provider.reportCall(with: u, endedAt: nil, reason: reason) }
        cleanUp(text)
    }

    private func cleanUp(_ text: String?) {
        listen?.cancel()
        listen = nil
        capturer?.stopCapture()
        pc?.close()
        pc = nil
        capturer = nil
        audioTrack = nil
        remoteVideo = nil
        localVideo = nil
        uuid = nil
        cur = ""
        cid = ""
        pending = []
        candidates = []
        answered = false
        started = nil
        muted = false
        cameraOff = false
        if let text, window != nil {
            phase = .ended(text)
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
                MainActor.assumeIsolated {
                    guard let self, case .ended = self.phase else { return }
                    self.phase = .idle
                    self.hide()
                }
            }
        } else {
            phase = .idle
            hide()
        }
        Conversation.shared.settingsChanged()   // the assistant may listen again
    }

    private func reset() {
        if pc != nil || uuid != nil { cleanUp(nil) }
        front = true
        speaker = false
    }

    // ---------------------------------------------------------------- the call screen, above everything else
    private var window: UIWindow?

    private func show() {
        guard window == nil, let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }) ?? UIApplication.shared.connectedScenes.first as? UIWindowScene
        else { return }
        let w = UIWindow(windowScene: scene)
        w.windowLevel = .alert + 1
        w.rootViewController = UIHostingController(rootView: CallView().environmentObject(self))
        w.makeKeyAndVisible()
        window = w
    }

    private func hide() {
        window?.isHidden = true
        window = nil
    }

    /// Back in front during a call (answered from the lock screen): the screen comes up.
    func foreground() {
        if active && phase != .ringing { show() }
    }

    // ---------------------------------------------------------------- helpers
    static func callId(_ s: String) -> Bool { s.range(of: "^[0-9a-f]{16}$", options: .regularExpression) != nil }

    /// The same call always gets the same UUID: a second push for it is no second call.
    static func callUUID(_ id: String) -> UUID {
        let hex = Array((callId(id) ? id : String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(16))).utf8)
        var b = [UInt8](repeating: 0x5a, count: 16)
        for i in 0..<8 {
            let pair = String(decoding: hex[(2 * i)..<(2 * i + 2)], as: UTF8.self)
            b[i] = UInt8(pair, radix: 16) ?? 0
        }
        return UUID(uuid: (b[0], b[1], b[2], b[3], b[4], b[5], 0x40 | (b[6] & 0x0f), b[7],
                           0x80 | (b[8] & 0x3f), b[9], b[10], b[11], b[12], b[13], b[14], b[15]))
    }

    /// The Vermittler's addresses from the Spark (anrufe.ice): STUN and TURN with a short-lived access.
    static func servers(_ v: Any?) -> [RTCIceServer] {
        (v as? [[String: Any]] ?? []).prefix(4).compactMap { s in
            let urls = (s["urls"] as? [String] ?? (s["urls"] as? String).map { [$0] } ?? [])
                .filter { $0.hasPrefix("stun:") || $0.hasPrefix("turn:") }
            guard !urls.isEmpty else { return nil }
            if let user = s["username"] as? String, let cred = s["credential"] as? String {
                return RTCIceServer(urlStrings: urls, username: user, credential: cred)
            }
            return RTCIceServer(urlStrings: urls)
        }
    }

    private static func media(_ video: Bool) -> RTCMediaConstraints {
        RTCMediaConstraints(mandatoryConstraints: ["OfferToReceiveAudio": "true", "OfferToReceiveVideo": video ? "true" : "false"],
                            optionalConstraints: nil)
    }

    private static func offer(_ pc: RTCPeerConnection, video: Bool) async throws -> RTCSessionDescription {
        try await withCheckedThrowingContinuation { c in
            pc.offer(for: media(video)) { sdp, error in
                if let sdp { c.resume(returning: sdp) } else { c.resume(throwing: error ?? SparkError(message: "offer")) }
            }
        }
    }

    private static func answer(_ pc: RTCPeerConnection, video: Bool) async throws -> RTCSessionDescription {
        try await withCheckedThrowingContinuation { c in
            pc.answer(for: media(video)) { sdp, error in
                if let sdp { c.resume(returning: sdp) } else { c.resume(throwing: error ?? SparkError(message: "answer")) }
            }
        }
    }

    private static func setLocal(_ pc: RTCPeerConnection, _ d: RTCSessionDescription) async throws {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            pc.setLocalDescription(d) { error in if let error { c.resume(throwing: error) } else { c.resume() } }
        }
    }

    private static func setRemote(_ pc: RTCPeerConnection, _ d: RTCSessionDescription) async throws {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            pc.setRemoteDescription(d) { error in if let error { c.resume(throwing: error) } else { c.resume() } }
        }
    }
}

/// The delegates of CallKit, PushKit and WebRTC. CallKit and PushKit call on the main queue; WebRTC on its own thread,
/// so those go to the main queue first.
final class CallBridge: NSObject, CXProviderDelegate, PKPushRegistryDelegate, RTCPeerConnectionDelegate {
    weak var center: CallCenter?

    private func main(_ f: @escaping @MainActor (CallCenter) -> Void) {
        DispatchQueue.main.async { [weak self] in
            MainActor.assumeIsolated { if let c = self?.center { f(c) } }
        }
    }

    // CallKit
    func providerDidReset(_ provider: CXProvider) { main { $0.providerReset() } }
    func provider(_ provider: CXProvider, perform action: CXStartCallAction) { main { $0.startAction(action) } }
    func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) { main { $0.answerAction(action) } }
    func provider(_ provider: CXProvider, perform action: CXEndCallAction) { main { $0.endAction(action) } }
    func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) { main { $0.muteAction(action) } }
    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) { main { $0.audioOn(audioSession) } }
    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) { main { $0.audioOff(audioSession) } }

    // PushKit: the report to CallKit must happen before this returns, so it runs right here on the main queue
    func pushRegistry(_ registry: PKPushRegistry, didUpdate credentials: PKPushCredentials, for type: PKPushType) {
        let data = credentials.token
        MainActor.assumeIsolated { center?.token(data) }
    }

    func pushRegistry(_ registry: PKPushRegistry, didReceiveIncomingPushWith payload: PKPushPayload, for type: PKPushType,
                      completion: @escaping () -> Void) {
        let p = payload.dictionaryPayload
        MainActor.assumeIsolated {
            if let c = center { c.pushed(p, done: completion) } else { completion() }
        }
    }

    func pushRegistry(_ registry: PKPushRegistry, didInvalidatePushTokenFor type: PKPushType) {}

    // WebRTC
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {
        guard let v = stream.videoTracks.first else { return }
        main { $0.remote(v) }
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) { main { $0.candidate(candidate) } }
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCPeerConnectionState) { main { $0.state(newState) } }
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd rtpReceiver: RTCRtpReceiver, streams mediaStreams: [RTCMediaStream]) {
        guard let t = rtpReceiver.track else { return }
        main { $0.remote(t) }
    }
}

// ---------------------------------------------------------------- the call screen
struct CallView: View {
    @EnvironmentObject var c: CallCenter

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if c.video, let r = c.remoteVideo {
                VideoView(track: r, fill: true).ignoresSafeArea()
            } else {
                Image(systemName: "person.crop.circle.fill").font(.system(size: 110)).foregroundStyle(.white.opacity(0.5))
            }
            VStack {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(verbatim: c.name).font(.title2.bold())
                        TimelineView(.periodic(from: .now, by: 1)) { ctx in
                            Text(verbatim: status(ctx.date)).font(.subheadline)
                        }
                        if c.active {
                            Label("Ende-zu-Ende verschlüsselt", systemImage: "lock.fill").font(.caption).opacity(0.8)
                        }
                    }
                    .foregroundStyle(.white)
                    .shadow(radius: 3)
                    Spacer()
                    if c.video, let l = c.localVideo, !c.cameraOff {
                        VideoView(track: l, fill: true)
                            .frame(width: 96, height: 144)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.white, lineWidth: 2))
                    }
                }
                .padding()
                Spacer()
                HStack(spacing: 18) {
                    button(c.muted ? "mic.slash.fill" : "mic.fill", c.muted ? "Ton an" : "Stumm", on: c.muted) { c.toggleMute() }
                    if c.video {
                        button(c.cameraOff ? "video.slash.fill" : "video.fill", "Kamera", on: c.cameraOff) { c.toggleCamera() }
                        button("arrow.triangle.2.circlepath.camera", "Wechseln", on: false) { c.switchCamera() }
                    }
                    button(c.speaker ? "speaker.wave.3.fill" : "speaker.fill", "Lautsprecher", on: c.speaker) { c.toggleSpeaker() }
                    Button { c.hangUp() } label: {
                        Image(systemName: "phone.down.fill").font(.title2).foregroundStyle(.white)
                            .frame(width: 64, height: 64).background(Circle().fill(.red))
                    }
                    .accessibilityLabel("Auflegen")
                }
                .padding(.bottom, 40)
                .disabled(!c.active)
            }
        }
    }

    private func status(_ now: Date) -> String {
        switch c.phase {
        case .calling: return String(localized: "Klingelt …")
        case .ringing: return String(localized: "Ruft an …")
        case .connecting: return String(localized: "Verbinde …")
        case .talking:
            let s = Int(now.timeIntervalSince(c.started ?? now))
            return String(format: "%d:%02d", s / 60, s % 60)
        case .ended(let text): return text
        case .idle: return ""
        }
    }

    private func button(_ icon: String, _ label: LocalizedStringKey, on: Bool, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            Image(systemName: icon).font(.title3).foregroundStyle(on ? .black : .white)
                .frame(width: 56, height: 56).background(Circle().fill(on ? Color.white : Color.white.opacity(0.22)))
        }
        .accessibilityLabel(Text(label))
    }
}

/// A WebRTC picture in SwiftUI (Metal view of the track).
struct VideoView: UIViewRepresentable {
    let track: RTCVideoTrack
    var fill = true

    func makeUIView(context: Context) -> RTCMTLVideoView {
        let v = RTCMTLVideoView(frame: .zero)
        v.videoContentMode = fill ? .scaleAspectFill : .scaleAspectFit
        v.clipsToBounds = true
        track.add(v)
        context.coordinator.track = track
        return v
    }

    func updateUIView(_ v: RTCMTLVideoView, context: Context) {
        if context.coordinator.track !== track {
            context.coordinator.track?.remove(v)
            track.add(v)
            context.coordinator.track = track
        }
    }

    static func dismantleUIView(_ v: RTCMTLVideoView, coordinator: Coordinator) {
        coordinator.track?.remove(v)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var track: RTCVideoTrack?
    }
}

// ---------------------------------------------------------------- the Spark's side
extension SparkAPI {
    /// Who calls, sound or video, and whether it still rings (only for the two people of the call).
    func callInfo(_ call: String) async throws -> [String: Any] {
        var c = URLComponents(url: base.appendingPathComponent("api/anrufe/info"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "call", value: call)]
        var r = request("api/anrufe/info")
        r.url = c.url
        r.timeoutInterval = 15
        let (data, response) = try await URLSession.shared.data(for: r)
        try Self.check(data, response)
        return Self.object(data)
    }

    func callStart(chat: String, video: Bool, dev: String) async throws -> [String: Any] {
        try await post("api/anrufe/start", ["id": chat, "video": video, "dev": dev])
    }

    /// The Chats stream (/api/chats/stream): one event per "data:" line; it ends after a while and is opened again.
    func chatEvents() -> AsyncThrowingStream<[String: Any], Error> {
        AsyncThrowingStream { cont in
            let task = Task {
                do {
                    var r = request("api/chats/stream")
                    r.timeoutInterval = 3600
                    r.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    let (bytes, response) = try await URLSession.shared.bytes(for: r)
                    guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                        throw SparkError(message: String(localized: "Der Spark gibt gerade keine Nachrichten durch."))
                    }
                    for try await line in bytes.lines where line.hasPrefix("data:") {
                        let json = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                        guard json.count < 64 * 1024, let data = json.data(using: .utf8),
                              let ev = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
                        cont.yield(ev)
                    }
                    cont.finish()
                } catch {
                    cont.finish(throwing: error)
                }
            }
            cont.onTermination = { _ in task.cancel() }
        }
    }
}
