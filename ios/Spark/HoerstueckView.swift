import AVFoundation
import MediaPlayer
import SwiftUI

// ---------------------------------------------------------------- Hörstück aus einer Mappe (hoerstueck.py, Push 5b)
/// One Hörstück of a Mappe in the list: its state and progress. The title is the model's checked words: plain text only.
struct HsStueck: Identifiable, Hashable {
    let id: String
    let titel: String
    let stand: String
    let zeilen: Int
    let fertig: Int
    let dauer: Int
    let stimmen: Int
    let laenge: Int
    let ton: Bool
    let geaendert: Bool
    let erzwungen: Bool

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, id.range(of: "^[0-9a-f]{12}$", options: .regularExpression) != nil else { return nil }
        self.id = id
        titel = String((d["titel"] as? String ?? "").prefix(80))
        let s = d["stand"] as? String ?? "x"
        stand = ["wartet", "sprechen", "fertig", "leer", "x"].contains(s) ? s : "x"
        zeilen = (d["zeilen"] as? NSNumber)?.intValue ?? 0
        fertig = (d["fertig_zeilen"] as? NSNumber)?.intValue ?? 0
        dauer = (d["dauer_s"] as? NSNumber)?.intValue ?? 0
        stimmen = (d["stimmen"] as? NSNumber)?.intValue ?? 2
        laenge = (d["laenge"] as? NSNumber)?.intValue ?? 5
        ton = d["ton"] as? Bool ?? false
        geaendert = d["geaendert"] as? Bool ?? false
        erzwungen = d["erzwungen"] as? Bool ?? false
    }

    var offen: Bool { stand == "wartet" || stand == "sprechen" }

    var standText: String {
        if erzwungen && offen {
            return String(localized: "Wird sofort erstellt · \(fertig) von \(zeilen) Zeilen gesprochen · echte Sprache geht vor")
        }
        switch stand {
        case "wartet": return String(localized: "Drehbuch folgt, sobald niemand spricht")
        case "sprechen": return String(localized: "Drehbuch fertig · \(fertig) von \(zeilen) Zeilen gesprochen · wartet auf ruhige Minuten")
        case "fertig": return HsStueck.clock(dauer) + " min · " + String(localized: "\(stimmen) Stimmen")
        case "leer": return String(localized: "Daraus lässt sich kein Hörstück machen: zu wenig geprüfte Zeilen")
        default: return String(localized: "ging nicht; „Löschen“ und neu erstellen")
        }
    }

    static func clock(_ s: Int) -> String { String(max(0, s) / 60) + ":" + String(format: "%02d", max(0, s) % 60) }
}

/// One line of the script: its voice (A, B, C, the panel's fixed roles), its words, where it starts in the sound and,
/// for a line with a place, the document's title and page.
struct HsZeile: Identifiable, Hashable {
    let id: Int
    let sprecher: String
    let text: String
    let art: String
    let dok: String
    let page: Int
    let ab: Double?

    init?(_ i: Int, _ d: [String: Any]) {
        let sp = d["sprecher"] as? String ?? ""
        guard ["A", "B", "C"].contains(sp) else { return nil }
        id = i
        sprecher = sp
        text = String((d["text"] as? String ?? "").prefix(400))
        art = d["art"] as? String ?? ""
        dok = String((d["dok"] as? String ?? "").prefix(120))
        page = (d["page"] as? NSNumber)?.intValue ?? 0
        ab = (d["ab"] as? NSNumber)?.doubleValue
    }
}

/// One Hörstück with its script.
struct HsDetail {
    let id: String
    let titel: String
    let mappe: String
    let stand: String
    let ton: Bool
    let telegram: Bool
    let dauer: Int
    let zeilen: [HsZeile]
    let rollen: [String: String]

    init?(_ d: [String: Any]) {
        guard let id = d["id"] as? String, id.range(of: "^[0-9a-f]{12}$", options: .regularExpression) != nil else { return nil }
        self.id = id
        titel = String((d["titel"] as? String ?? "").prefix(80))
        mappe = String((d["mappe_name"] as? String ?? "").prefix(60))
        stand = d["stand"] as? String ?? "x"
        ton = d["ton"] as? Bool ?? false
        telegram = d["telegram"] as? Bool ?? false
        dauer = (d["dauer_s"] as? NSNumber)?.intValue ?? 0
        let raw = (d["drehbuch"] as? [[String: Any]] ?? []).prefix(200)
        zeilen = raw.enumerated().compactMap { HsZeile($0.offset, $0.element) }
        let en = Locale.current.language.languageCode?.identifier != "de"
        var r: [String: String] = [:]
        for (k, v) in d["rollen"] as? [String: [String]] ?? [:] where ["A", "B", "C"].contains(k) && v.count == 2 {
            r[k] = String(v[en ? 1 : 0].prefix(30))
        }
        rollen = r
    }

    /// the line being heard at this time: the last one whose start lies behind it
    func current(_ t: Double) -> Int? { zeilen.last(where: { ($0.ab ?? .infinity) <= t + 0.05 })?.id }
}

/// Hörstücke in the app: the same endpoints as the panel's part (iphone.THINGS "hoerstueck"), only while the admin
/// released them for the profile. The sound is the AAC copy (?form=m4a: AVFoundation plays no Ogg), held in memory
/// while it plays, never stored on the iPhone. Background and lock screen through the audio session and Now Playing.
@MainActor
final class HoerstueckModel: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var list: [HsStueck] = []
    @Published var heute = 0
    @Published var grenze = 3
    @Published var max = 10
    @Published var alle = 0
    @Published var laengen = [5, 10, 20]
    /// „Sofort erstellen": only when the server says the admin asks (hoerstueck.ist_admin); it checks it again on POST
    @Published var sofort = false
    @Published var sofortFrei = true
    @Published var loaded = false
    @Published var error: String?
    @Published var note: String?
    @Published var playing: String?
    @Published var paused = false
    @Published var time: Double = 0
    @Published var fetching: String?
    private var player: AVAudioPlayer?
    private var ticker: Task<Void, Never>?
    private var commands = false

    func load(_ mid: String) async {
        guard let api = SparkAPI.current else { return }
        defer { loaded = true }
        do {
            let d = try await api.object("GET", "api/profile/mappen/" + mid + "/hoerstuecke")
            list = (d["stuecke"] as? [[String: Any]] ?? []).prefix(20).compactMap { HsStueck($0) }
            heute = (d["heute"] as? NSNumber)?.intValue ?? 0
            grenze = (d["grenze"] as? NSNumber)?.intValue ?? 3
            max = (d["max"] as? NSNumber)?.intValue ?? 10
            alle = (d["alle"] as? NSNumber)?.intValue ?? 0
            laengen = (d["laengen"] as? [NSNumber])?.map { $0.intValue } ?? [5, 10, 20]
            sofort = d["sofort"] as? Bool ?? false
            sofortFrei = d["sofort_frei"] as? Bool ?? true
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    /// queued: the script comes in the app's language (German or English), with the panel's rules
    func make(_ mid: String, laenge: Int, stimmen: Int) async {
        guard let api = SparkAPI.current else { return }
        let en = Locale.current.language.languageCode?.identifier != "de"
        do {
            _ = try await api.object("POST", "api/profile/mappen/" + mid + "/hoerstuecke",
                                     body: ["laenge": laenge, "stimmen": stimmen, "sprache": en ? "en" : "de"])
            note = String(localized: "Eingereiht: das Drehbuch entsteht in der nächsten ruhigen Minute, dann Zeile für Zeile.")
            error = nil
            await load(mid)
        } catch { self.error = error.localizedDescription }
    }

    /// the admin's „Sofort erstellen": a new one at once (mid), or one that waits pulled forward (hid); without the quiet
    /// minutes and the day's limit, real speech still first
    func now(_ mid: String, hid: String? = nil, laenge: Int = 5, stimmen: Int = 2) async {
        guard let api = SparkAPI.current else { return }
        let en = Locale.current.language.languageCode?.identifier != "de"
        do {
            if let hid {
                _ = try await api.object("POST", "api/profile/hoerstueck/" + hid + "/sofort", body: [:])
            } else {
                _ = try await api.object("POST", "api/profile/mappen/" + mid + "/hoerstuecke/sofort",
                                         body: ["laenge": laenge, "stimmen": stimmen, "sprache": en ? "en" : "de"])
            }
            note = String(localized: "Wird jetzt erstellt; echte Sprache geht vor.")
            error = nil
            await load(mid)
        } catch { self.error = error.localizedDescription }
    }

    func detail(_ hid: String) async -> HsDetail? {
        guard let api = SparkAPI.current else { return nil }
        do {
            let d = try await api.object("GET", "api/profile/hoerstueck/" + hid)
            error = nil
            return HsDetail(d)
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    func delete(_ hid: String) async -> Bool {
        guard let api = SparkAPI.current else { return false }
        if playing == hid { stop() }
        do {
            _ = try await api.object("DELETE", "api/profile/hoerstueck/" + hid)
            list.removeAll { $0.id == hid }
            error = nil
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    /// „An Telegram": the Spark sends it only to the profile's own linked chat
    func telegram(_ hid: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            _ = try await api.object("POST", "api/profile/hoerstueck/" + hid + "/telegram", body: [:])
            note = String(localized: "An deinen Telegram-Chat geschickt.")
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    // ---------------------------------------------------------------- the player
    func toggle(_ d: HsDetail) async {
        if playing == d.id, let p = player {
            if p.isPlaying { p.pause(); paused = true } else { p.play(); paused = false }
            nowPlaying(d)
            return
        }
        stop()
        guard let api = SparkAPI.current else { return }
        fetching = d.id
        defer { fetching = nil }
        do {
            var r = api.request("api/profile/hoerstueck/" + d.id + "/ton")
            var c = URLComponents(url: api.base.appendingPathComponent("api/profile/hoerstueck/" + d.id + "/ton"),
                                  resolvingAgainstBaseURL: false)
            c?.queryItems = [URLQueryItem(name: "form", value: "m4a")]
            r.url = c?.url
            let (data, response) = try await URLSession.shared.data(for: r)
            try SparkAPI.check(data, response)
            let p = try AVAudioPlayer(data: data, fileTypeHint: AVFileType.m4a.rawValue)
            try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
            try? AVAudioSession.sharedInstance().setActive(true)
            p.delegate = self
            player = p
            guard p.play() else { return }
            playing = d.id
            paused = false
            remote()
            nowPlaying(d)
            ticker = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(400))
                    guard let self, let p = self.player else { return }
                    self.time = p.currentTime
                }
            }
        } catch { self.error = error.localizedDescription }
    }

    /// plays from the start of one line (its time in the script)
    func seek(_ t: Double, _ d: HsDetail) {
        guard playing == d.id, let p = player else { return }
        p.currentTime = Swift.max(0, Swift.min(t, p.duration))
        time = p.currentTime
        if !p.isPlaying { p.play(); paused = false }
        nowPlaying(d)
    }

    func stop() {
        ticker?.cancel()
        ticker = nil
        player?.stop()
        player = nil
        playing = nil
        paused = false
        time = 0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }

    private func nowPlaying(_ d: HsDetail) {
        guard let p = player else { return }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = [
            MPMediaItemPropertyTitle: d.titel.isEmpty ? String(localized: "Hörstück") : d.titel,
            MPMediaItemPropertyAlbumTitle: d.mappe,
            MPMediaItemPropertyArtist: "Spark",
            MPMediaItemPropertyPlaybackDuration: p.duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: p.currentTime,
            MPNowPlayingInfoPropertyPlaybackRate: p.isPlaying ? 1.0 : 0.0,
        ]
    }

    /// the lock screen's and the headphones' buttons (once per app run)
    private func remote() {
        guard !commands else { return }
        commands = true
        let cc = MPRemoteCommandCenter.shared()
        cc.playCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.player?.play(); self?.paused = false; self?.refresh() }
            return .success
        }
        cc.pauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.player?.pause(); self?.paused = true; self?.refresh() }
            return .success
        }
        cc.togglePlayPauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in
                guard let p = self?.player else { return }
                if p.isPlaying { p.pause(); self?.paused = true } else { p.play(); self?.paused = false }
                self?.refresh()
            }
            return .success
        }
        cc.changePlaybackPositionCommand.addTarget { [weak self] e in
            guard let e = e as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            let t = e.positionTime
            Task { @MainActor in self?.player?.currentTime = t; self?.refresh() }
            return .success
        }
    }

    private func refresh() {
        guard let p = player, var info = MPNowPlayingInfoCenter.default().nowPlayingInfo else { return }
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = p.currentTime
        info[MPNowPlayingInfoPropertyPlaybackRate] = p.isPlaying ? 1.0 : 0.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        time = p.currentTime
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }
}

/// Meine Sachen → Mappen → a Mappe → Hörstück: length and voices, „Erstellen“, the list with its progress.
struct HoerstueckView: View {
    let mappe: MpMappe
    @StateObject private var m = HoerstueckModel()
    @State private var laenge = 5
    @State private var stimmen = 2
    @State private var busy = false

    var body: some View {
        List {
            Section {
                Picker("Länge", selection: $laenge) {
                    ForEach(m.laengen, id: \.self) { n in Text(verbatim: String(n) + " min").tag(n) }
                }
                .pickerStyle(.segmented)
                Picker("Stimmen", selection: $stimmen) {
                    Text(verbatim: "2").tag(2)
                    Text(verbatim: "3").tag(3)
                }
                .pickerStyle(.segmented)
                Button {
                    Task { busy = true; await m.make(mappe.id, laenge: laenge, stimmen: stimmen); busy = false }
                } label: { Label("Erstellen", systemImage: "waveform") }
                    .disabled(busy || m.alle >= m.max || m.heute >= m.grenze)
                if m.sofort {
                    Button {
                        Task { busy = true; await m.now(mappe.id, laenge: laenge, stimmen: stimmen); busy = false }
                    } label: { Label("Sofort erstellen", systemImage: "bolt") }
                        .disabled(busy || m.alle >= m.max || !m.sofortFrei)
                    Text("Nur Admin: ohne ruhige Minuten und Tagesgrenze; echte Sprache geht trotzdem vor.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text(m.alle >= m.max ? String(localized: "Höchstens \(m.max) Hörstücke; lösch erst eins.")
                     : m.heute >= m.grenze ? String(localized: "Für heute ist die Grenze erreicht.")
                     : String(localized: "heute \(m.heute) von \(m.grenze) · läuft in ruhigen Minuten"))
                    .font(.caption).foregroundStyle(.secondary)
            } header: { Text("Neues Hörstück") }
            Section("Hörstücke") {
                if !m.loaded { LadeZeilen(rows: 2) }
                if m.loaded && m.list.isEmpty {
                    Text("Noch kein Hörstück aus dieser Mappe.").foregroundStyle(.secondary)
                }
                ForEach(m.list) { s in
                    NavigationLink { HoerstueckDetailView(stueck: s, mappe: mappe.id, model: m) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: s.titel.isEmpty ? String(localized: "Hörstück") : s.titel)
                            Text(verbatim: s.standText).font(.caption).foregroundStyle(.secondary)
                            if s.stand == "sprechen", s.zeilen > 0 {
                                ProgressView(value: Double(s.fertig), total: Double(s.zeilen))
                            }
                            if s.geaendert {
                                Text("Die Mappe hat sich seitdem geändert.").font(.caption).foregroundStyle(Theme.warnText)
                            }
                        }
                    }
                }
            }
            Section {
                Text("Das Modell schreibt nur ein Drehbuch. Der Spark prüft jede Zeile: jede Aussage mit Fundstelle, jede Zahl im Dokument, Überleitungen ohne Zahlen und Namen. Ein Hörstück wird nie zu einem Dokument.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
        }
        .navigationTitle("Hörstück")
        .refreshable { await m.load(mappe.id) }
        .task {
            await m.load(mappe.id)
            // something waits or speaks: look again while the page is open
            while !Task.isCancelled && m.list.contains(where: { $0.stand == "wartet" || $0.stand == "sprechen" }) {
                try? await Task.sleep(for: .seconds(30))
                if !Task.isCancelled { await m.load(mappe.id) }
            }
        }
    }
}

/// One Hörstück: the player (also in the background and on the lock screen), „An Telegram“, „Löschen“ and the script
/// with the line being heard marked; a line's time plays from there.
struct HoerstueckDetailView: View {
    let stueck: HsStueck
    let mappe: String
    @ObservedObject var model: HoerstueckModel
    @Environment(\.dismiss) private var dismiss
    @State private var d: HsDetail?
    @State private var loaded = false
    @State private var askDelete = false

    var body: some View {
        ScrollViewReader { proxy in
            List {
                if let d {
                    Section {
                        Text(verbatim: d.mappe.isEmpty ? "" : String(localized: "Hörstück aus der Mappe „\(d.mappe)“"))
                            .font(.caption).foregroundStyle(.secondary)
                        if d.ton {
                            Button { Task { await model.toggle(d) } } label: {
                                Label(model.playing == d.id && !model.paused ? String(localized: "Pause") : String(localized: "Abspielen"),
                                      systemImage: model.playing == d.id && !model.paused ? "pause.fill" : "play.fill")
                            }
                            .disabled(model.fetching != nil)
                            if model.playing == d.id {
                                Text(verbatim: HsStueck.clock(Int(model.time)) + " / " + HsStueck.clock(d.dauer))
                                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            }
                            if d.telegram {
                                Button { Task { await model.telegram(d.id) } } label: { Label("An Telegram", systemImage: "paperplane") }
                            } else {
                                Text(SparkAPI.way(String(localized: "„An Telegram“ geht, sobald Telegram verknüpft ist und Persönliches dort erlaubt ist: Ich → Telegram")))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        } else {
                            Text(verbatim: stueck.standText).foregroundStyle(.secondary)
                            if model.sofort && stueck.offen && !stueck.erzwungen {
                                Button { Task { await model.now(mappe, hid: stueck.id); await load() } } label: {
                                    Label("Jetzt erstellen", systemImage: "bolt")
                                }
                                .disabled(!model.sofortFrei)
                            }
                        }
                        Button("Löschen", role: .destructive) { askDelete = true }
                    }
                    Section("Drehbuch") {
                        let cur = model.playing == d.id ? d.current(model.time) : nil
                        ForEach(d.zeilen) { z in
                            line(z, d, on: z.id == cur).id(z.id)
                        }
                    }
                } else if !loaded {
                    LadeZeilen(rows: 3)
                }
                if let n = model.note { Text(verbatim: n).foregroundStyle(.secondary) }
                if let e = model.error { Text(SparkAPI.way(e)).foregroundStyle(Theme.badText) }
            }
            .onChange(of: model.playing == stueck.id ? d?.current(model.time) : nil) { _, now in
                if let now { withAnimation { proxy.scrollTo(now, anchor: .center) } }
            }
        }
        .navigationTitle(Text(verbatim: stueck.titel.isEmpty ? String(localized: "Hörstück") : stueck.titel))
        .refreshable { await load() }
        .task { await load() }
        .confirmationDialog("Hörstück löschen?", isPresented: $askDelete, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) {
                Task { if await model.delete(stueck.id) { dismiss() } }
            }
        }
    }

    @ViewBuilder private func line(_ z: HsZeile, _ d: HsDetail, on: Bool) -> some View {
        HStack(alignment: .top, spacing: Theme.s3) {
            Text(verbatim: z.sprecher)
                .font(.caption.weight(.semibold))
                .frame(width: 26, height: 26)
                .background(on ? Theme.onAccent.opacity(0.25) : Theme.soft, in: Circle())
                .accessibilityLabel(Text(verbatim: d.rollen[z.sprecher] ?? z.sprecher))
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: z.text)
                if z.art == "inhalt", !z.dok.isEmpty {
                    Text(verbatim: z.dok + (z.page > 0 ? " · " + String(localized: "S. \(z.page)") : ""))
                        .font(.caption).foregroundStyle(on ? Theme.onAccent : Theme.muted)
                }
            }
            Spacer(minLength: 0)
            if let ab = z.ab, model.playing == d.id {
                Button(HsStueck.clock(Int(ab))) { model.seek(ab, d) }
                    .font(.caption.monospacedDigit())
                    .buttonStyle(.borderless)
                    .accessibilityLabel(Text("Ab hier anhören"))
            }
        }
        .foregroundStyle(on ? Theme.onAccent : Theme.fg)
        .listRowBackground(on ? Theme.accent : nil)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func load() async {
        defer { loaded = true }
        if let got = await model.detail(stueck.id) { d = got }
    }
}
