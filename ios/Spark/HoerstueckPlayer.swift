import AVFoundation
import Combine
import MediaPlayer

// ---------------------------------------------------------------- Hörstück: one player for the app and CarPlay
/// One finished Hörstück to listen to: its id, title (the model's checked words, plain text only), the Mappe's name and
/// the length. From the app's Mappe (HoerstueckView) or from GET /api/profile/hoerstuecke (CarPlay „Hörstücke").
struct HsSpur: Hashable {
    let id: String
    let titel: String
    let mappe: String
    let dauer: Int

    init(id: String, titel: String, mappe: String, dauer: Int) {
        self.id = id
        self.titel = titel
        self.mappe = mappe
        self.dauer = dauer
    }

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, id.range(of: "^[0-9a-f]{12}$", options: .regularExpression) != nil else { return nil }
        self.init(id: id, titel: String((d["titel"] as? String ?? "").prefix(80)),
                  mappe: String((d["mappe_name"] as? String ?? "").prefix(60)), dauer: (d["dauer_s"] as? NSNumber)?.intValue ?? 0)
    }

    var name: String { titel.isEmpty ? String(localized: "Hörstück") : titel }
}

/// The one player of Hörstücke (the app's page and CarPlay share it, so one never talks over the other). The sound is
/// the AAC copy (?form=m4a), held in memory while it plays, never stored on the iPhone; only the place where listening
/// stopped is kept (id and seconds, at most `placesMax`), so it goes on there. Before it plays the conversation stops
/// and the audio engine lets go of the sound (Conversation.giveSound: playAndRecord → playback, spoken audio); the wake
/// word stays off while it plays (canWake, `claiming`). A conversation with Spark pauses it, and it goes on by itself
/// once the conversation ended. Siri, a call or the navigation's voice pause it the usual way (interruption), and so
/// does a lost route (the car or the headphones gone). Now Playing and the remote buttons (lock screen, the car's
/// screen and steering wheel, headphones): play, pause, 15 s back and forward, the next and the previous one.
@MainActor
final class HsPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    static let shared = HsPlayer()
    /// a Hörstück is loaded, being fetched or waits for a conversation to end: the wake word stays off (Conversation.canWake
    /// asks this without touching `shared`, so the two singletons never build each other)
    private(set) static var claiming = false
    static let skip: Double = 15
    static let placesMax = 20
    private static let placesKey = "hoerstueckStelle"
    /// no cache and no cookies on the iPhone: the sound lives only in memory
    private static let net = URLSession(configuration: .ephemeral)

    @Published private(set) var playing: String?
    @Published private(set) var paused = false
    @Published private(set) var time: Double = 0
    @Published private(set) var fetching: String?
    private(set) var spur: HsSpur?
    private var queue: [HsSpur] = []
    private var player: AVAudioPlayer?
    private var ticker: Task<Void, Never>?
    private var commands = false
    /// paused because a conversation runs (it goes on afterwards), or because the car went away (on when it comes back)
    private var heldForTalk = false
    private var heldForCar = false
    private var watchTalk: AnyCancellable?

    override private init() {
        super.init()
        watchTalk = Conversation.shared.$phase.removeDuplicates().receive(on: RunLoop.main).sink { [weak self] p in self?.talk(p) }
        NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] n in
            let raw = n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            let opts = n.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
            MainActor.assumeIsolated { self?.interrupted(raw == AVAudioSession.InterruptionType.began.rawValue, again: opts & 1 == 1) }
        }
        NotificationCenter.default.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] n in
            let why = n.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            guard why == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue else { return }
            MainActor.assumeIsolated { self?.pause("Weg weg") }
        }
    }

    private func claim() { Self.claiming = playing != nil && !paused || fetching != nil || heldForTalk }

    // ---------------------------------------------------------------- playing
    /// Plays `s` (`queue`: the list it was picked from, for the next and the previous one), from where it stopped last.
    /// Already loaded: plays on. Throws when the Spark gave no sound.
    func play(_ s: HsSpur, queue q: [HsSpur]) async throws {
        if !q.isEmpty { queue = q }
        if playing == s.id, player != nil { resume(); return }
        guard fetching == nil, let api = SparkAPI.current else { return }
        fetching = s.id
        stop()
        claim()
        Conversation.shared.giveSound("Hörstück")
        defer { fetching = nil; claim() }
        var r = api.request("api/profile/hoerstueck/" + s.id + "/ton")
        var c = URLComponents(url: api.base.appendingPathComponent("api/profile/hoerstueck/" + s.id + "/ton"), resolvingAgainstBaseURL: false)
        c?.queryItems = [URLQueryItem(name: "form", value: "m4a")]
        r.url = c?.url
        r.cachePolicy = .reloadIgnoringLocalCacheData   // in memory only: nothing of the sound lands in a cache on the iPhone
        let data: Data
        do {
            let got = try await Self.net.data(for: r)
            try SparkAPI.check(got.0, got.1)
            data = got.0
        } catch {
            AudioEngine.note("Hörstück: Laden fehlgeschlagen")
            Conversation.shared.soundBack()
            throw error
        }
        let p = try AVAudioPlayer(data: data, fileTypeHint: AVFileType.m4a.rawValue)
        session(true)
        p.delegate = self
        let at = Self.place(s.id)
        if at > 5 && at < p.duration - 5 { p.currentTime = at - 2 }   // a little before, to find back in
        player = p
        spur = s
        guard p.play() else {
            player = nil
            spur = nil
            AudioEngine.note("Hörstück: Start abgelehnt")
            session(false)
            return
        }
        playing = s.id
        paused = false
        heldForTalk = false
        heldForCar = false
        claim()
        AudioEngine.note(at > 5 ? "Hörstück: spielt weiter" : "Hörstück: spielt")
        remote()
        info()
        ticker = Task { [weak self] in
            var n = 0
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(400))
                guard let self, let p = self.player else { return }
                self.time = p.currentTime
                n += 1
                if n % 25 == 0 && p.isPlaying { self.keep() }   // every 10 s the place, so a hard end of the app loses little
            }
        }
    }

    func toggle() {
        guard let p = player else { return }
        if p.isPlaying { pause("Pause") } else { resume() }
    }

    func pause(_ why: String = "Pause") {
        guard let p = player, p.isPlaying else { return }
        p.pause()
        paused = true
        keep()
        claim()
        info()
        AudioEngine.note("Hörstück: " + why)
    }

    func resume() {
        guard let p = player, !p.isPlaying else { return }
        heldForTalk = false
        heldForCar = false
        Conversation.shared.giveSound("Hörstück")
        session(true)
        p.play()
        paused = false
        claim()
        info()
        AudioEngine.note("Hörstück: weiter")
    }

    /// 15 s back or forward (the car's rows, the remote buttons)
    func skip(_ by: Double) { seek((player?.currentTime ?? 0) + by) }

    func seek(_ t: Double) {
        guard let p = player else { return }
        p.currentTime = Swift.max(0, Swift.min(t, p.duration - 0.5))
        time = p.currentTime
        keep()
        info()
    }

    /// the next (`by` 1) or the previous one (-1) of the list it was picked from; back to the start first after 5 s
    func step(_ by: Int) {
        guard let now = spur else { return }
        if by < 0 && time > 5 { seek(0); return }
        guard let i = queue.firstIndex(where: { $0.id == now.id }), queue.indices.contains(i + by) else { return }
        let to = queue[i + by]
        AudioEngine.note(by > 0 ? "Hörstück: nächstes" : "Hörstück: voriges")
        Task { try? await self.play(to, queue: []) }
    }

    func stop(keepPlace: Bool = true) {
        guard player != nil || spur != nil else { return }
        if keepPlace { keep() }
        ticker?.cancel()
        ticker = nil
        player?.stop()
        player = nil
        spur = nil
        playing = nil
        paused = false
        heldForTalk = false
        heldForCar = false
        time = 0
        claim()
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        session(false)
    }

    /// deleted in the app: its place goes too
    func forget(_ id: String) {
        if spur?.id == id { stop(keepPlace: false) }
        var all = Self.places()
        all.removeAll { $0.id == id }
        Self.store(all)
    }

    // ---------------------------------------------------------------- CarPlay
    /// the car went away (also for a moment, wireless): pause, and play on when it comes back within the drop-out time
    func carGone() {
        guard player?.isPlaying == true else { return }
        pause("Auto getrennt")
        heldForCar = true
    }

    func carBack() {
        guard heldForCar else { return }
        resume()
    }

    // ---------------------------------------------------------------- a conversation, Siri, a call
    private func talk(_ p: Conversation.Phase) {
        switch p {
        case .listening, .transcribing, .thinking, .speaking:
            guard player?.isPlaying == true else { return }
            pause("Pause für Gespräch")
            heldForTalk = true
            claim()
        case .idle, .waiting:
            guard heldForTalk else { return }
            // a moment later: the end tone of the car still plays
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(1.5))
                let phase = Conversation.shared.phase
                guard let self, self.heldForTalk, phase == .idle || phase == .waiting else { return }
                self.resume()
            }
        }
    }

    private func interrupted(_ began: Bool, again: Bool) {
        guard let p = player else { return }
        if began {
            guard !paused else { return }
            paused = true
            keep()
            info()
            AudioEngine.note("Hörstück: unterbrochen")
        } else if again && paused && !heldForTalk && !heldForCar {
            session(true)
            p.play()
            paused = false
            info()
            AudioEngine.note("Hörstück: weiter nach Unterbrechung")
        }
        claim()
    }

    /// playback while it plays; let go when it ends, so radio and music come back (notifyOthersOnDeactivation)
    private func session(_ on: Bool) {
        let s = AVAudioSession.sharedInstance()
        if on {
            try? s.setCategory(.playback, mode: .spokenAudio)
            try? s.setActive(true)
        } else {
            try? s.setActive(false, options: .notifyOthersOnDeactivation)
            Conversation.shared.soundBack()
        }
    }

    // ---------------------------------------------------------------- where it stopped (id and seconds only)
    private static func places() -> [(id: String, t: Double)] {
        (UserDefaults.standard.array(forKey: placesKey) as? [String] ?? []).compactMap { e in
            let p = e.split(separator: ":")
            guard p.count == 2, let t = Double(p[1]) else { return nil }
            return (String(p[0]), t)
        }
    }

    private static func store(_ all: [(id: String, t: Double)]) {
        UserDefaults.standard.set(all.suffix(placesMax).map { $0.id + ":" + String(Int($0.t)) }, forKey: placesKey)
    }

    static func place(_ id: String) -> Double { places().first { $0.id == id }?.t ?? 0 }

    private func keep() {
        guard let s = spur, let p = player else { return }
        var all = Self.places()
        all.removeAll { $0.id == s.id }
        if p.currentTime < p.duration - 5 { all.append((s.id, p.currentTime)) }   // heard to the end: from the start next time
        Self.store(all)
    }

    // ---------------------------------------------------------------- Now Playing and the remote buttons
    private func info() {
        guard let p = player, let s = spur else { return }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = [
            MPMediaItemPropertyTitle: s.name,
            MPMediaItemPropertyAlbumTitle: s.mappe,
            MPMediaItemPropertyArtist: "Spark",
            MPMediaItemPropertyPlaybackDuration: p.duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: p.currentTime,
            MPNowPlayingInfoPropertyPlaybackRate: p.isPlaying ? 1.0 : 0.0,
            MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaType.audio.rawValue,
        ]
        time = p.currentTime
    }

    /// once per app run; every button only acts on a loaded Hörstück
    private func remote() {
        guard !commands else { return }
        commands = true
        let cc = MPRemoteCommandCenter.shared()
        func on(_ c: MPRemoteCommand, _ act: @escaping @MainActor (HsPlayer, MPRemoteCommandEvent) -> Void) {
            c.isEnabled = true
            c.addTarget { [weak self] e in
                MainActor.assumeIsolated { () -> MPRemoteCommandHandlerStatus in
                    guard let self, self.player != nil else { return .noActionableNowPlayingItem }
                    act(self, e)
                    return .success
                }
            }
        }
        on(cc.playCommand) { me, _ in me.resume() }
        on(cc.pauseCommand) { me, _ in me.pause() }
        on(cc.togglePlayPauseCommand) { me, _ in me.toggle() }
        cc.skipForwardCommand.preferredIntervals = [NSNumber(value: Self.skip)]
        cc.skipBackwardCommand.preferredIntervals = [NSNumber(value: Self.skip)]
        on(cc.skipForwardCommand) { me, _ in me.skip(Self.skip) }
        on(cc.skipBackwardCommand) { me, _ in me.skip(-Self.skip) }
        on(cc.nextTrackCommand) { me, _ in me.step(1) }
        on(cc.previousTrackCommand) { me, _ in me.step(-1) }
        on(cc.changePlaybackPositionCommand) { me, e in
            if let e = e as? MPChangePlaybackPositionCommandEvent { me.seek(e.positionTime) }
        }
    }

    /// heard to the end: its place goes (from the start next time); the next one only on a tap or a remote button
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            AudioEngine.note("Hörstück: zu Ende")
            if let id = self.spur?.id { self.forget(id) } else { self.stop() }
        }
    }
}
