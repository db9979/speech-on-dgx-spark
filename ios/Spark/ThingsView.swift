import AVFoundation
import SwiftUI

/// "Meine Sachen" (Dominik 2026-10-17, plan app-meine-sachen/plan.md): one page for everything the Spark keeps for
/// the profile: documents, made documents, pictures, music and memory, each as a tile with its number, and one search
/// over all of them. A tile shows only what the admin released for the profile (hello "areas", iphone.THINGS on the
/// Spark); every rule stays on the Spark.
@MainActor
final class ThingsModel: ObservableObject {
    @Published var docs: [SparkDoc] = []
    @Published var made: [MadeDoc] = []
    @Published var pictures: [Picture] = []
    @Published var songs: [Song] = []
    @Published var facts: [Fact] = []
    @Published var tidy = false
    @Published var loading = true
    @Published var error: String?

    func load(_ a: Allowed) async {
        guard let api = SparkAPI.current else { return }
        error = nil
        // each part on its own: one that is off or fails leaves the others standing
        if a.areas.contains("documents") {
            do { docs = try await api.docs() ?? [] } catch { self.error = error.localizedDescription }
        } else { docs = [] }
        if a.make, let d = try? await api.madeDocs() { made = d } else { made = [] }
        pictures = a.areas.contains("bilder") ? ((try? await api.pictures())?.pics ?? []) : []
        songs = a.areas.contains("musik") ? ((try? await api.songs())?.songs ?? []) : []
        if a.areas.contains("memory"), let m = try? await api.memory() {
            facts = m.facts
            tidy = m.tidy != nil
        } else { facts = []; tidy = false }
        loading = false
    }

    /// what came last, of every kind, newest first
    var recent: [ThingHit] {
        Array((docs.map { ThingHit(doc: $0) } + made.map { ThingHit(made: $0) } + pictures.map { ThingHit(picture: $0) }
               + songs.map { ThingHit(song: $0) }).sorted { $0.when > $1.when }.prefix(5))
    }

    /// the search over all parts: titles, file names, senders, tags, wishes, facts (on the iPhone, nothing is sent)
    func find(_ q: String) -> [ThingHit] {
        let q = q.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return [] }
        func has(_ s: String...) -> Bool { s.contains { $0.lowercased().contains(q) } }
        return docs.filter { has($0.shown, $0.name, $0.sender, $0.art, $0.tags.joined(separator: " ")) }.map { ThingHit(doc: $0) }
            + made.filter { has($0.title) }.map { ThingHit(made: $0) }
            + pictures.filter { has($0.wish) }.map { ThingHit(picture: $0) }
            + songs.filter { has($0.title, $0.lyrics) }.map { ThingHit(song: $0) }
            + facts.filter { has($0.text) }.map { ThingHit(fact: $0) }
    }
}

/// One thing of Meine Sachen in a mixed list (search, "Zuletzt dazugekommen").
struct ThingHit: Identifiable {
    let id: String
    let title: String
    let kind: LocalizedStringKey
    let icon: String
    let tint: Color
    let when: Date
    var doc: SparkDoc?
    var made: MadeDoc?
    var picture: Picture?
    var song: Song?
    var fact: Fact?

    init(doc: SparkDoc) {
        id = "d" + doc.id; title = doc.shown; kind = "Dokument"; icon = ThingsView.docIcon(doc); tint = .blue
        when = doc.created; self.doc = doc
    }
    init(made: MadeDoc) {
        id = "m" + made.id; title = made.title; kind = "Vom Spark erstellt"; icon = "wand.and.stars"; tint = .indigo
        when = made.updated; self.made = made
    }
    init(picture: Picture) {
        id = "p" + picture.id; title = picture.wish.isEmpty ? String(localized: "Bild") : picture.wish; kind = "Bild"
        icon = "photo"; tint = .orange; when = picture.created; self.picture = picture
    }
    init(song: Song) {
        id = "s" + song.id; title = song.title; kind = "Musik"; icon = "music.note"; tint = .pink; when = song.created
        self.song = song
    }
    init(fact: Fact) {
        id = "f" + fact.id; title = fact.text; kind = "Gedächtnis"; icon = "brain"; tint = .green; when = fact.created
        self.fact = fact
    }

    @MainActor @ViewBuilder var page: some View {
        if let doc { DocDetailView(doc: doc) }
        else if let made { MadeDocView(doc: made) }
        else if let picture { PictureView(picture: picture) }
        else if let song { SongsView(start: song.id) }
        else { MemoryView(search: title) }
    }
}

/// The parts of Meine Sachen, one per tile.
enum ThingPart: String, Identifiable {
    case documents, made, pictures, music, memory
    var id: String { rawValue }

    @MainActor @ViewBuilder var page: some View {
        switch self {
        case .documents: DocumentsView()
        case .made: MadeDocsView()
        case .pictures: PicturesView()
        case .music: SongsView()
        case .memory: MemoryView()
        }
    }
}

struct ThingsView: View {
    @ObservedObject private var talk = Conversation.shared
    @StateObject private var m = ThingsModel()
    @State private var search = ""
    /// the tile tapped last: several NavigationLinks in one List row all fire on a tap (Dominik 2026-10-17: a tile did
    /// not open its own part), so a tile is a Button and the page opens through navigationDestination
    @State private var open: ThingPart?

    nonisolated static func docIcon(_ d: SparkDoc) -> String {
        if d.source == "remarkable" { return "pencil.and.scribble" }
        return d.kind == "picture" ? "photo" : d.kind == "scan" ? "doc.viewfinder" : "doc.text"
    }

    /// whether the profile has any part of Meine Sachen (the button beside the conversation and the row in Einstellungen)
    static func any(_ a: Allowed) -> Bool {
        a.make || !a.areas.isDisjoint(with: ["documents", "bilder", "musik", "memory"])
    }

    private var a: Allowed { talk.allowed }
    private var none: Bool {
        !a.areas.contains("documents") && !a.make && !a.areas.contains("bilder") && !a.areas.contains("musik")
            && !a.areas.contains("memory")
    }

    var body: some View {
        List {
            if !search.isEmpty {
                let hits = m.find(search)
                if hits.isEmpty { Text("Nichts gefunden.").foregroundStyle(.secondary) }
                ForEach(hits) { h in NavigationLink { h.page } label: { row(h) } }
            } else {
                Section {
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                        if a.areas.contains("documents") {
                            tile(.documents, "Dokumente", "doc.text", .blue, m.docs.count, docNote)
                        }
                        if a.make {
                            tile(.made, "Vom Spark erstellt", "wand.and.stars", .indigo, m.made.count,
                                 m.made.first.map { Text($0.updated, format: .relative(presentation: .named)) })
                        }
                        if a.areas.contains("bilder") {
                            tile(.pictures, "Bilder", "photo.on.rectangle", .orange, m.pictures.count, nil)
                        }
                        if a.areas.contains("musik") {
                            tile(.music, "Musik", "music.note", .pink, m.songs.count, m.songs.first.map { Text(verbatim: $0.title) })
                        }
                        if a.areas.contains("memory") {
                            tile(.memory, "Gedächtnis", "brain", .green, m.facts.count, m.tidy ? Text("Vorschläge zum Aufräumen") : nil)
                        }
                    }
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                }
                if none && !m.loading {
                    Text(SparkAPI.way(String(localized: "Der Admin hat dafür noch nichts freigegeben (Funktionen → Eigene Dokumente, Bilder malen, Musik machen, Gedächtnis).")))
                        .foregroundStyle(.secondary)
                }
                if !m.recent.isEmpty {
                    Section("Zuletzt dazugekommen") {
                        ForEach(m.recent) { h in NavigationLink { h.page } label: { row(h) } }
                    }
                }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Meine Sachen")
        .searchable(text: $search, prompt: Text("In allem suchen"))
        .refreshable { await m.load(a) }
        .task { await m.load(a) }
        .overlay { if m.loading { ProgressView() } }
        .navigationDestination(item: $open) { $0.page }
        .onChange(of: talk.allowed) { _, a in Task { await m.load(a) } }
    }

    private var docNote: Text? {
        let due = m.docs.filter { !$0.due.isEmpty && $0.due >= Self.today }.count
        let reading = m.docs.filter { $0.todo > 0 }.count
        if due > 0 { return Text("Fristen: \(due)") }
        if reading > 0 { return Text("Wird gelesen: \(reading)") }
        return nil
    }

    /// today as the Spark writes deadlines (YYYY-MM-DD)
    nonisolated static var today: String {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    private func tile(_ part: ThingPart, _ name: LocalizedStringKey, _ icon: String, _ tint: Color, _ count: Int,
                      _ note: Text?) -> some View {
        Button { open = part } label: {
            VStack(alignment: .leading, spacing: 4) {
                Image(systemName: icon).font(.title3).foregroundStyle(.white)
                    .frame(width: 34, height: 34).background(tint, in: RoundedRectangle(cornerRadius: 8))
                Text(verbatim: String(count)).font(.title.bold()).foregroundStyle(.primary)
                Text(name).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                (note ?? Text(verbatim: " ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
            .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.borderless)
    }

    private func row(_ h: ThingHit) -> some View {
        HStack(spacing: 10) {
            Image(systemName: h.icon).foregroundStyle(.white).frame(width: 28, height: 28)
                .background(h.tint, in: RoundedRectangle(cornerRadius: 7))
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: h.title).lineLimit(1)
                HStack(spacing: 4) {
                    Text(h.kind)
                    if h.when.timeIntervalSince1970 > 0 { Text(verbatim: "·"); Text(h.when, format: .dateTime.day().month()) }
                }
                .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

/// Meine Sachen on its own, from the button beside the conversation.
struct ThingsSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ThingsView()
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }
    }
}

// ---------------------------------------------------------------- pictures (bilder.py)
struct Picture: Identifiable, Equatable {
    let id: String
    let wish: String
    let created: Date
    let width: Int
    let height: Int
    let size: Int
}

/// A song the Spark made (musik.py).
struct Song: Identifiable, Equatable {
    let id: String
    let title: String
    let lyrics: String
    let created: Date
    let seconds: Int
    let sung: Bool
    let size: Int
}

extension SparkAPI {
    /// The profile's pictures, newest first, and how many are still being painted.
    func pictures() async throws -> (pics: [Picture], painting: Int) {
        let d = try await object("GET", "api/bilder")
        let pics = (d["pics"] as? [[String: Any]] ?? []).compactMap { p -> Picture? in
            guard let id = p["id"] as? String, Self.isJob(id) else { return nil }
            return Picture(id: id, wish: String((p["wish"] as? String ?? "").prefix(300)),
                           created: Date(timeIntervalSince1970: (p["t"] as? NSNumber)?.doubleValue ?? 0),
                           width: (p["w"] as? NSNumber)?.intValue ?? 0, height: (p["h"] as? NSNumber)?.intValue ?? 0,
                           size: (p["bytes"] as? NSNumber)?.intValue ?? 0)
        }
        let jobs = (d["jobs"] as? [[String: Any]] ?? []).filter { ["wait", "run"].contains($0["state"] as? String ?? "") }
        return (pics.sorted { $0.created > $1.created }, jobs.count)
    }

    /// Paint one from the person's own wish (the Spark checks the wish and the day limit).
    func paint(_ wish: String) async throws {
        _ = try await call("POST", "api/bilder", body: ["wunsch": String(wish.prefix(500))])
    }

    func deletePicture(_ id: String) async throws {
        guard Self.isJob(id) else { return }
        _ = try await call("DELETE", "api/bilder/\(id)")
    }

    /// The profile's songs, newest first, and how many are still being made.
    func songs() async throws -> (songs: [Song], making: Int) {
        let d = try await object("GET", "api/musik")
        let songs = (d["songs"] as? [[String: Any]] ?? []).compactMap { s -> Song? in
            guard let id = s["id"] as? String, Self.isJob(id) else { return nil }
            let wish = s["wish"] as? String ?? "", caption = s["caption"] as? String ?? ""
            return Song(id: id, title: String((wish.isEmpty ? caption : wish).prefix(200)),
                        lyrics: String((s["lyrics"] as? String ?? "").prefix(2000)),
                        created: Date(timeIntervalSince1970: (s["t"] as? NSNumber)?.doubleValue ?? 0),
                        seconds: (s["length_s"] as? NSNumber)?.intValue ?? 0, sung: s["sung"] as? Bool ?? false,
                        size: (s["bytes"] as? NSNumber)?.intValue ?? 0)
        }
        let jobs = (d["jobs"] as? [[String: Any]] ?? []).filter { ["wait", "run"].contains($0["state"] as? String ?? "") }
        return (songs.sorted { $0.created > $1.created }, jobs.count)
    }

    /// Make one from the person's own description (instrumental; singing and lyrics stay in the panel).
    func makeSong(_ wish: String) async throws {
        _ = try await call("POST", "api/musik", body: ["wunsch": String(wish.prefix(500))])
    }

    func deleteSong(_ id: String) async throws {
        guard Self.isJob(id) else { return }
        _ = try await call("DELETE", "api/musik/\(id)")
    }

    /// The song itself (MP3, only of the own profile).
    func songFile(_ id: String) async throws -> Data {
        guard Self.isJob(id) else { throw SparkError(message: String(localized: "Das Lied gibt es nicht.")) }
        let (data, response) = try await URLSession.shared.data(for: request("api/musik/\(id)/datei"))
        try Self.check(data, response)
        return data
    }
}

/// A picture of the profile, loaded once per id while the app runs (the files never change).
@MainActor
final class PictureCache {
    static let shared = PictureCache()
    private let cache = NSCache<NSString, UIImage>()

    init() { cache.countLimit = 120 }

    func image(_ id: String) async -> UIImage? {
        if let i = cache.object(forKey: id as NSString) { return i }
        guard let api = SparkAPI.current, let d = try? await api.pictureFile(id), let i = UIImage(data: d) else { return nil }
        cache.setObject(i, forKey: id as NSString)
        return i
    }
}

struct PictureThumb: View {
    let id: String
    @State private var image: UIImage?

    var body: some View {
        Color(.secondarySystemFill)
            .aspectRatio(1, contentMode: .fit)
            .overlay {
                if let image { Image(uiImage: image).resizable().scaledToFill() } else { ProgressView() }
            }
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .task(id: id) { image = await PictureCache.shared.image(id) }
    }
}

@MainActor
final class PicturesModel: ObservableObject {
    @Published var pics: [Picture] = []
    @Published var painting = 0
    @Published var loading = true
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            (pics, painting) = try await api.pictures()
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    /// while something is being painted: look again every 4 s, at most 5 minutes
    func follow() async {
        for _ in 0..<75 where painting > 0 && !Task.isCancelled {
            try? await Task.sleep(for: .seconds(4))
            await load()
        }
    }
}

struct PicturesView: View {
    @StateObject private var m = PicturesModel()
    @State private var wish = ""
    @State private var search = ""

    private var shown: [Picture] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? m.pics : m.pics.filter { $0.wish.lowercased().contains(q) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    TextField("Was soll ich malen?", text: $wish, axis: .vertical).textFieldStyle(.roundedBorder).lineLimit(1...3)
                    Button("Malen") { Task { await paint() } }
                        .buttonStyle(.borderedProminent)
                        .disabled(wish.trimmingCharacters(in: .whitespaces).count < 3)
                }
                if m.painting > 0 { Label("Wird gemalt …", systemImage: "paintbrush").font(.footnote).foregroundStyle(.secondary) }
                if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red).font(.footnote) }
                if !m.loading && m.pics.isEmpty { Text("Noch keine Bilder.").foregroundStyle(.secondary) }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 3)], spacing: 3) {
                    ForEach(shown) { p in
                        NavigationLink { PictureView(picture: p, removed: { Task { await m.load() } }) } label: { PictureThumb(id: p.id) }
                            .accessibilityLabel(Text(verbatim: p.wish))
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Bilder")
        .searchable(text: $search)
        .refreshable { await m.load() }
        .task { await m.load(); await m.follow() }
        .overlay { if m.loading { ProgressView() } }
    }

    private func paint() async {
        do {
            try await SparkAPI.current?.paint(wish)
            wish = ""
            await m.load()
            await m.follow()
        } catch { m.error = error.localizedDescription }
    }
}

struct PictureView: View {
    let picture: Picture
    var removed: () -> Void = {}
    @State private var image: UIImage?
    @State private var asking = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let image {
                    Image(uiImage: image).resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius: 8))
                } else { ProgressView().frame(maxWidth: .infinity, minHeight: 200) }
                // the person's own wish: plain text, nothing in it is a link or a command
                if !picture.wish.isEmpty { Text(verbatim: picture.wish) }
                Text(picture.created, format: .dateTime.day().month().year().hour().minute()).font(.caption).foregroundStyle(.secondary)
                if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            }
            .padding()
        }
        .navigationTitle("Bild")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let image {
                ToolbarItem(placement: .primaryAction) {
                    ShareLink(item: Image(uiImage: image), preview: SharePreview("Bild", image: Image(uiImage: image)))
                }
            }
            ToolbarItem(placement: .destructiveAction) {
                Button(role: .destructive) { asking = true } label: { Label("Löschen", systemImage: "trash") }
            }
        }
        .confirmationDialog("Bild löschen?", isPresented: $asking, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) {
                Task {
                    do { try await SparkAPI.current?.deletePicture(picture.id); removed(); dismiss() }
                    catch { self.error = error.localizedDescription }
                }
            }
        }
        .task { image = await PictureCache.shared.image(picture.id) }
    }
}

// ---------------------------------------------------------------- music (musik.py)
@MainActor
final class SongsModel: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var songs: [Song] = []
    @Published var making = 0
    @Published var loading = true
    @Published var error: String?
    @Published var playing: String?
    @Published var fetching: String?
    private var player: AVAudioPlayer?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            (songs, making) = try await api.songs()
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    func follow() async {
        for _ in 0..<90 where making > 0 && !Task.isCancelled {
            try? await Task.sleep(for: .seconds(4))
            await load()
        }
    }

    func toggle(_ s: Song) async {
        if playing == s.id { stop(); return }
        stop()
        fetching = s.id
        defer { fetching = nil }
        do {
            guard let api = SparkAPI.current else { return }
            let d = try await api.songFile(s.id)
            let p = try AVAudioPlayer(data: d, fileTypeHint: AVFileType.mp3.rawValue)
            try? AVAudioSession.sharedInstance().setCategory(.playback)
            try? AVAudioSession.sharedInstance().setActive(true)
            p.delegate = self
            player = p
            if p.play() { playing = s.id }
        } catch { self.error = error.localizedDescription }
    }

    func stop() {
        player?.stop()
        player = nil
        playing = nil
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }
}

struct SongsView: View {
    var start: String?
    @StateObject private var m = SongsModel()
    @State private var wish = ""
    @State private var removing: Song?

    var body: some View {
        List {
            Section {
                HStack {
                    TextField("Was für Musik?", text: $wish, axis: .vertical).lineLimit(1...3)
                    Button("Machen") { Task { await make() } }
                        .buttonStyle(.borderedProminent)
                        .disabled(wish.trimmingCharacters(in: .whitespaces).count < 3)
                }
                if m.making > 0 { Label("Wird gemacht …", systemImage: "music.note") .foregroundStyle(.secondary) }
            } footer: { Text(SparkAPI.way(String(localized: "Ohne Gesang. Gesang und eigener Text gehen im Panel unter Ich → Musik."))) }
            if !m.loading && m.songs.isEmpty { Text("Noch keine Musik.").foregroundStyle(.secondary) }
            ForEach(m.songs) { s in
                HStack(spacing: 12) {
                    Button { Task { await m.toggle(s) } } label: {
                        if m.fetching == s.id { ProgressView().frame(width: 32, height: 32) }
                        else { Image(systemName: m.playing == s.id ? "stop.circle.fill" : "play.circle.fill").font(.largeTitle) }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(m.playing == s.id ? Text("Anhalten") : Text("Abspielen"))
                    VStack(alignment: .leading, spacing: 2) {
                        // the person's own wish: plain text, nothing in it is a link or a command
                        Text(verbatim: s.title).lineLimit(2)
                        HStack(spacing: 4) {
                            if s.seconds > 0 { Text(verbatim: String(format: "%d:%02d", s.seconds / 60, s.seconds % 60)); Text(verbatim: "·") }
                            Text(s.sung ? LocalizedStringKey("mit Gesang") : LocalizedStringKey("ohne Gesang"))
                            Text(verbatim: "·")
                            Text(s.created, format: .dateTime.day().month())
                        }
                        .font(.caption).foregroundStyle(.secondary)
                    }
                }
                .listRowBackground(s.id == start ? Color.accentColor.opacity(0.08) : nil)
                .swipeActions { Button(role: .destructive) { removing = s } label: { Label("Löschen", systemImage: "trash") } }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Musik")
        .refreshable { await m.load() }
        .task { await m.load(); await m.follow() }
        .onDisappear { m.stop() }
        .confirmationDialog("Lied löschen?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
                            titleVisibility: .visible, presenting: removing) { s in
            Button("Löschen", role: .destructive) {
                Task {
                    do { if m.playing == s.id { m.stop() }; try await SparkAPI.current?.deleteSong(s.id); await m.load() }
                    catch { m.error = error.localizedDescription }
                }
            }
        } message: { s in Text(verbatim: s.title) }
    }

    private func make() async {
        do {
            try await SparkAPI.current?.makeSong(wish)
            wish = ""
            await m.load()
            await m.follow()
        } catch { m.error = error.localizedDescription }
    }
}

// ---------------------------------------------------------------- memory (Ich → Gedächtnis)
@MainActor
final class MemoryModel: ObservableObject {
    @Published var facts: [Fact] = []
    @Published var tidy: MemoryTidy?
    @Published var loading = true
    @Published var asking = false
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            (facts, tidy) = try await api.memory()
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    func run(_ what: @escaping (SparkAPI) async throws -> Void) async {
        guard let api = SparkAPI.current else { return }
        do { try await what(api); error = nil } catch { self.error = error.localizedDescription }
        await load()
    }

    func tidyStep(_ step: String) async {
        guard let api = SparkAPI.current else { return }
        asking = true
        defer { asking = false }
        do {
            tidy = try await api.tidyMemory(step)
            if step == "check" && tidy == nil { error = String(localized: "Nichts aufzuräumen.") }
            if step != "check" { await load() }
        } catch { self.error = error.localizedDescription }
    }
}

struct MemoryView: View {
    @State var search = ""
    @StateObject private var m = MemoryModel()
    @State private var editing: Fact?
    @State private var text = ""
    @State private var picked = Set<String>()
    @State private var edit: EditMode = .inactive

    private var shown: [Fact] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? m.facts : m.facts.filter { $0.text.lowercased().contains(q) }
    }

    var body: some View {
        List(selection: $picked) {
            if let t = m.tidy { tidySection(t) }
            Section {
                if !m.loading && m.facts.isEmpty { Text("Noch nichts gemerkt.").foregroundStyle(.secondary) }
                ForEach(shown) { f in
                    VStack(alignment: .leading, spacing: 2) {
                        // what the assistant noted: plain text, nothing in it is a link or a command
                        Text(verbatim: f.text)
                        HStack(spacing: 4) {
                            Text(f.learned ? LocalizedStringKey("aus einem Gespräch gelernt") : LocalizedStringKey("selbst gesagt"))
                            if f.created.timeIntervalSince1970 > 0 { Text(verbatim: "·"); Text(f.created, format: .dateTime.day().month().year()) }
                        }
                        .font(.caption).foregroundStyle(.secondary)
                    }
                    .tag(f.id)
                    .swipeActions {
                        Button(role: .destructive) { Task { await m.run { try await $0.forget(f.id) } } } label: { Label("Löschen", systemImage: "trash") }
                        Button { text = f.text; editing = f } label: { Label("Ändern", systemImage: "pencil") }.tint(.blue)
                    }
                }
            } header: {
                if !m.facts.isEmpty { Text(verbatim: String(shown.count)) }
            } footer: {
                if m.tidy == nil && !m.facts.isEmpty {
                    Button { Task { await m.tidyStep("check") } } label: {
                        if m.asking { ProgressView() } else { Label("Aufräumen vorschlagen", systemImage: "sparkles") }
                    }
                    .disabled(m.asking)
                }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .environment(\.editMode, $edit)
        .navigationTitle("Gedächtnis")
        .searchable(text: $search)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(edit.isEditing ? "Fertig" : "Auswählen") { edit = edit.isEditing ? .inactive : .active; picked = [] }
            }
            if edit.isEditing && !picked.isEmpty {
                ToolbarItem(placement: .bottomBar) {
                    Button(role: .destructive) {
                        let ids = Array(picked)
                        Task { await m.run { try await $0.forgetFacts(ids) }; picked = []; edit = .inactive }
                    } label: { Label("\(picked.count) löschen", systemImage: "trash") }
                }
            }
        }
        .refreshable { await m.load() }
        .task { await m.load() }
        .alert("Ändern", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
            TextField("Was der Spark sich merkt", text: $text)
            Button("Speichern") {
                guard let f = editing else { return }
                let t = text
                Task { await m.run { try await $0.changeFact(f.id, t) } }
            }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    @ViewBuilder private func tidySection(_ t: MemoryTidy) -> some View {
        Section("Vorschlag zum Aufräumen") {
            ForEach(Array(t.merge.enumerated()), id: \.offset) { _, x in
                VStack(alignment: .leading) {
                    Text("Zusammenfassen:").font(.caption.bold())
                    ForEach(x.old, id: \.self) { Text(verbatim: "– " + $0).font(.caption).foregroundStyle(.secondary) }
                    Text(verbatim: "→ " + x.text)
                }
            }
            ForEach(Array(t.drop.enumerated()), id: \.offset) { _, x in
                VStack(alignment: .leading) {
                    Text("Weglassen:").font(.caption.bold())
                    Text(verbatim: x.old).strikethrough()
                    if !x.why.isEmpty { Text(verbatim: x.why).font(.caption).foregroundStyle(.secondary) }
                }
            }
            HStack {
                Button("Übernehmen") { Task { await m.tidyStep("accept") } }.buttonStyle(.borderedProminent)
                Button("Verwerfen") { Task { await m.tidyStep("reject") } }.buttonStyle(.bordered)
            }
            .disabled(m.asking)
        }
    }
}
