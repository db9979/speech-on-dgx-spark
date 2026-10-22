import AVFoundation
import UniformTypeIdentifiers
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
    /// the numbers on the tiles from last time (Merken.swift: only how many, never a name), while the Spark answers
    @Published var keptAt: Date?
    private var counts: [String: Int] = [:]

    /// a tile's number: the fresh one, or the kept one while nothing fresh came
    func count(_ part: String, _ n: Int) -> Int { keptAt != nil && n == 0 ? counts[part] ?? 0 : n }

    func load(_ a: Allowed) async {
        if loading, keptAt == nil, let k = Merken.object("sachen"), let c = k.d as? [String: Int] {
            counts = c
            keptAt = k.at
        }
        await Merken.timed("sachen") { await fetch(a) }
        if error == nil {
            keptAt = nil
            Merken.keepObject("sachen", ["documents": docs.count, "made": made.count, "bilder": pictures.count,
                                         "musik": songs.count, "memory": facts.count])
        }
    }

    private func fetch(_ a: Allowed) async {
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
        when = doc.when; self.doc = doc
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
        a.make || !a.areas.isDisjoint(with: ["documents", "bilder", "musik", "memory", "calendar", "mail", "tasks", "vorgaenge", "contacts"])
    }

    private var a: Allowed { talk.allowed }
    private var none: Bool {
        !a.areas.contains("documents") && !a.make && !a.areas.contains("bilder") && !a.areas.contains("musik")
            && !a.areas.contains("memory") && !a.areas.contains("calendar") && !a.areas.contains("mail")
            && !a.areas.contains("tasks") && !a.areas.contains("vorgaenge") && !a.areas.contains("contacts")
    }

    var body: some View {
        List {
            if !search.isEmpty {
                let hits = m.find(search)
                if hits.isEmpty { Text("Nichts gefunden.").foregroundStyle(.secondary) }
                ForEach(hits) { h in NavigationLink { h.page } label: { row(h) } }
            } else {
                if let at = m.keptAt { StandNote(at: at, loading: m.loading).listRowBackground(Color.clear) }
                // Kalender, E-Mail (KalenderPost.swift), Listen (ListenView.swift), Offen (Vorgaenge.swift), Kontakte: pages of their
                // own, like in the panel's menu
                if a.areas.contains("calendar") || a.areas.contains("mail") || a.areas.contains("tasks") || a.areas.contains("vorgaenge")
                    || a.areas.contains("contacts") {
                    Section {
                        if a.areas.contains("calendar") {
                            NavigationLink { KalenderView() } label: { Label("Kalender", systemImage: "calendar") }
                        }
                        if a.areas.contains("mail") {
                            NavigationLink { PostView() } label: { Label("E-Mail", systemImage: "envelope") }
                        }
                        if a.areas.contains("tasks") {
                            NavigationLink { ListenView() } label: { Label("Listen", systemImage: "checklist") }
                        }
                        if a.areas.contains("vorgaenge") {
                            NavigationLink { OffenView() } label: { Label("Offen", systemImage: "tray") }
                        }
                        if a.areas.contains("contacts") {
                            NavigationLink { KontakteView() } label: { Label("Kontakte", systemImage: "person.crop.circle") }
                        }
                    }
                }
                Section {
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                        if a.areas.contains("documents") {
                            tile(.documents, "Dokumente", "doc.text", .blue, m.count("documents", m.docs.count), docNote)
                        }
                        if a.make {
                            tile(.made, "Vom Spark erstellt", "wand.and.stars", .indigo, m.count("made", m.made.count),
                                 m.made.first.map { Text($0.updated, format: .relative(presentation: .named)) })
                        }
                        if a.areas.contains("bilder") {
                            tile(.pictures, "Bilder", "photo.on.rectangle", .orange, m.count("bilder", m.pictures.count), nil)
                        }
                        if a.areas.contains("musik") {
                            tile(.music, "Musik", "music.note", .pink, m.count("musik", m.songs.count), m.songs.first.map { Text(verbatim: $0.title) })
                        }
                        if a.areas.contains("memory") {
                            tile(.memory, "Gedächtnis", "brain", .green, m.count("memory", m.facts.count), m.tidy ? Text("Vorschläge zum Aufräumen") : nil)
                        }
                    }
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                }
                if none && !m.loading {
                    Text(SparkAPI.way(String(localized: "Der Admin hat dafür noch nichts freigegeben (Funktionen → Eigene Dokumente, Bilder malen, Musik machen, Gedächtnis, Kalender, E-Mail lesen).")))
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
        .overlay { if m.loading && m.keptAt == nil { LadeZeilen(rows: 4).padding() } }
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

/// A song the Spark made, an own file or a version of one (musik.py; kind "", "upload" or "edit").
struct Song: Identifiable, Equatable {
    let id: String
    let title: String
    let lyrics: String
    let created: Date
    let seconds: Int
    let sung: Bool
    let size: Int
    var kind = ""
    var root = ""
    /// what was changed, in the app's language (Musik bearbeiten)
    var label = ""
}

/// What Musik bearbeiten offers this profile (musik.py musik_list "edit"); nil when the admin switch is off.
struct SongEditing {
    let genres: [(key: String, de: String, en: String)]
    let maxAdd: Int
    let uploadMB: Int
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

    /// The profile's songs, newest first, how many are still being made and the lengths the admin allows (seconds).
    func songs() async throws -> (songs: [Song], making: Int, lengths: [Int], length: Int, editing: SongEditing?) {
        let d = try await object("GET", "api/musik")
        let en = Locale.current.language.languageCode?.identifier == "en"
        let songs = (d["songs"] as? [[String: Any]] ?? []).compactMap { s -> Song? in
            guard let id = s["id"] as? String, Self.isJob(id) else { return nil }
            let wish = s["wish"] as? String ?? "", caption = s["caption"] as? String ?? ""
            let label = s["label"] as? [String] ?? []
            let root = s["root"] as? String ?? ""
            return Song(id: id, title: String((wish.isEmpty ? caption : wish).prefix(200)),
                        lyrics: String((s["lyrics"] as? String ?? "").prefix(3000)),
                        created: Date(timeIntervalSince1970: (s["t"] as? NSNumber)?.doubleValue ?? 0),
                        seconds: (s["length_s"] as? NSNumber)?.intValue ?? 0, sung: s["sung"] as? Bool ?? false,
                        size: (s["bytes"] as? NSNumber)?.intValue ?? 0, kind: s["kind"] as? String ?? "",
                        root: Self.isJob(root) ? root : id,
                        label: String((label.count == 2 ? (en ? label[1] : label[0]) : "").prefix(120)))
        }
        var editing: SongEditing?
        if let e = d["edit"] as? [String: Any], e["on"] as? Bool == true {
            let genres = (e["genres"] as? [[String]] ?? []).compactMap { g -> (key: String, de: String, en: String)? in
                g.count == 3 ? (key: g[0], de: g[1], en: g[2]) : nil
            }
            editing = SongEditing(genres: genres, maxAdd: (e["max_add"] as? NSNumber)?.intValue ?? 120,
                                  uploadMB: (e["upload_mb"] as? NSNumber)?.intValue ?? 30)
        }
        let jobs = (d["jobs"] as? [[String: Any]] ?? []).filter { ["wait", "run"].contains($0["state"] as? String ?? "") }
        let lim = d["limits"] as? [String: Any] ?? [:]
        let most = (lim["max_s"] as? NSNumber)?.intValue ?? 120
        // the same choice as the length chips under Ich → Musik in the panel (musik.js MULENS)
        let lengths = [30, 60, 120, 180, 240, 300, 420, 600].filter { $0 <= most }
        return (songs.sorted { $0.created > $1.created }, jobs.count, lengths, (lim["default_s"] as? NSNumber)?.intValue ?? 120, editing)
    }

    /// Musik bearbeiten: one change of an own song ({art, …} as under Ich → Musik); the Spark checks every number.
    func editSong(_ id: String, _ body: [String: Any]) async throws {
        guard Self.isJob(id) else { return }
        _ = try await call("POST", "api/musik/\(id)/bearbeiten", body: body)
    }

    /// A version becomes a song of its own.
    func ownSong(_ id: String) async throws {
        guard Self.isJob(id) else { return }
        _ = try await call("POST", "api/musik/\(id)/eigenes")
    }

    /// An own music file, only after the tick for the rights; the raw file as the body.
    func uploadSong(_ data: Data, name: String) async throws {
        var c = URLComponents(url: base.appendingPathComponent("api/musik/hochladen"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "rechte", value: "1"), URLQueryItem(name: "name", value: String(name.prefix(120)))]
        var r = request("api/musik/hochladen", method: "POST")
        r.url = c.url
        r.timeoutInterval = 200
        r.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        r.httpBody = data
        let (body, response) = try await URLSession.shared.data(for: r)
        try Self.check(body, response)
    }

    /// Make one from the person's own description and length; with singing the lyrics in the language of the phone.
    /// The description may be a whole page (a firm's text as the template); the short music description from Text
    /// schreiben goes to the music model, which reads at most 600 characters.
    func makeSong(_ wish: String, seconds: Int, lyrics: String? = nil, caption: String = "") async throws {
        var body: [String: Any] = ["wunsch": String(wish.prefix(2000)), "sekunden": seconds]
        if let lyrics {
            body.merge(["gesang": true, "sprache": Self.songLanguage, "liedtext": String(lyrics.prefix(3000)),
                        "beschreibung": String(caption.prefix(600))]) { $1 }
        }
        _ = try await call("POST", "api/musik", body: body)
    }

    /// Text schreiben: the language model writes the lyrics from the description; artist names become style words in
    /// the description. Nothing is made yet, the person reads both first.
    func writeLyrics(_ wish: String, seconds: Int) async throws -> (lyrics: String, wish: String, names: Bool, caption: String) {
        let d = try await object("POST", "api/musik/liedtext", body: ["wunsch": String(wish.prefix(2000)), "sekunden": seconds,
                                                                    "sprache": Self.songLanguage], timeout: 120)
        return (String((d["liedtext"] as? String ?? "").prefix(3000)), String((d["wunsch"] as? String ?? wish).prefix(2000)),
                d["namen"] as? Bool ?? false, String((d["beschreibung"] as? String ?? "").prefix(600)))
    }

    static var songLanguage: String { Locale.current.language.languageCode?.identifier == "en" ? "en" : "de" }

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
    @Published var lengths: [Int] = []
    @Published var length = 120
    @Published var loading = true
    @Published var error: String?
    @Published var playing: String?
    @Published var fetching: String?
    @Published var editing: SongEditing?
    private var player: AVAudioPlayer?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.songs()
            (songs, making, lengths, editing) = (d.songs, d.making, d.lengths, d.editing)
            if !lengths.contains(length) { length = lengths.contains(d.length) ? d.length : (lengths.last ?? d.length) }
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
    @State private var changing: Song?
    @State private var picking = false
    @State private var upload: URL?
    @State private var sung = false
    @State private var lyrics = ""
    @State private var writing = false
    @State private var note: String?
    // the music description from Text schreiben and the description it belongs to; own changes drop it
    @State private var caption = ("", "")

    var body: some View {
        List {
            Section {
                HStack {
                    TextField("Was für Musik?", text: $wish, axis: .vertical).lineLimit(1...8)
                    Button("Machen") { Task { await make() } }
                        .buttonStyle(.borderedProminent)
                        .disabled(wish.trimmingCharacters(in: .whitespaces).count < 3 || writing)
                }
                if !m.lengths.isEmpty {
                    Picker("Länge", selection: $m.length) {
                        ForEach(m.lengths, id: \.self) { s in Text(verbatim: Self.clock(s)) }
                    }
                }
                Toggle("Mit Gesang", isOn: $sung)
                if sung {
                    // Text schreiben: the Spark writes the lyrics into the field, the song comes only from "Machen"
                    HStack {
                        Text("Liedtext").font(.subheadline.weight(.semibold))
                        Spacer()
                        if writing { ProgressView() }
                        Button("Text schreiben") { Task { await write() } }
                            .disabled(wish.trimmingCharacters(in: .whitespaces).count < 3 || writing)
                    }
                    TextField("[verse] … [chorus] …", text: $lyrics, axis: .vertical).lineLimit(3...12).font(.callout)
                    if let note { Text(note).font(.footnote).foregroundStyle(.secondary) }
                }
                if m.making > 0 { Label("Wird gemacht …", systemImage: "music.note") .foregroundStyle(.secondary) }
            } footer: { Text("Ohne Gesang wird es instrumental. Mit Gesang und leerem Liedtext schreibt der Spark den Text zuerst ins Feld; Künstlernamen werden dabei zu Stilwörtern. Die Beschreibung darf bis 2000 Zeichen lang sein, z. B. ein Firmentext als Vorlage.") }
            if !m.loading && m.songs.isEmpty { Text("Noch keine Musik.").foregroundStyle(.secondary) }
            // grouped by day like the list under Ich → Musik in the panel
            ForEach(Self.days(m.songs), id: \.0) { day, songs in
                Section(Self.dayNames[day]) {
                    ForEach(songs) { s in
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
                                if !s.label.isEmpty { Text(verbatim: "↳ " + s.label).font(.caption).foregroundStyle(.tint) }
                                else if s.kind == "upload" { Text("hochgeladen").font(.caption).foregroundStyle(.secondary) }
                                HStack(spacing: 4) {
                                    if s.seconds > 0 { Text(verbatim: Self.clock(s.seconds)); Text(verbatim: "·") }
                                    Text(s.sung ? LocalizedStringKey("mit Gesang") : LocalizedStringKey("ohne Gesang"))
                                    Text(verbatim: "·")
                                    if Calendar.current.isDateInToday(s.created) { Text(s.created, format: .dateTime.hour().minute()) }
                                    else { Text(s.created, format: .dateTime.weekday(.abbreviated).day().month()) }
                                }
                                .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .listRowBackground(s.id == start ? Color.accentColor.opacity(0.08) : nil)
                        .swipeActions { Button(role: .destructive) { removing = s } label: { Label("Löschen", systemImage: "trash") } }
                        .swipeActions(edge: .leading) {
                            if m.editing != nil { Button { changing = s } label: { Label("Bearbeiten", systemImage: "slider.horizontal.3") }.tint(.pink) }
                        }
                        .contextMenu {
                            if m.editing != nil {
                                Button { changing = s } label: { Label("Bearbeiten", systemImage: "slider.horizontal.3") }
                                if s.kind == "edit" && s.root != s.id {
                                    Button { Task { await own(s) } } label: { Label("Als eigenes Lied", systemImage: "music.note") }
                                }
                            }
                        }
                    }
                }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Musik")
        .toolbar {
            if m.editing != nil {
                Button { picking = true } label: { Label("Eigene Datei hochladen", systemImage: "square.and.arrow.up") }
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.audio, .mp3, .wav]) { result in
            if case .success(let url) = result { upload = url }
        }
        .confirmationDialog("Rechte an diesem Lied?", isPresented: Binding(get: { upload != nil }, set: { if !$0 { upload = nil } }),
                            titleVisibility: .visible, presenting: upload) { url in
            Button("Das ist meine Aufnahme oder ich habe die Rechte") { Task { await send(url) } }
        } message: { _ in Text("Hochladen geht nur mit eigenen Aufnahmen oder Liedern, an denen du die Rechte hast.") }
        .sheet(item: $changing) { s in
            if let e = m.editing {
                NavigationStack { SongEditView(song: s, editing: e) { await m.load(); await m.follow() } }
            }
        }
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

    static func clock(_ s: Int) -> String { String(format: "%d:%02d", s / 60, s % 60) }

    /// Heute, Gestern, Letzte 7 Tage, Älter: the groups of the panel's list (musik.js muGroup), in this order.
    static let dayNames: [LocalizedStringKey] = ["Heute", "Gestern", "Letzte 7 Tage", "Älter"]

    /// The songs by day: the index into dayNames and the songs of that group, empty groups left out.
    static func days(_ songs: [Song]) -> [(Int, [Song])] {
        let cal = Calendar.current, today = cal.startOfDay(for: Date())
        var groups: [[Song]] = [[], [], [], []]
        for s in songs {
            let n = cal.dateComponents([.day], from: cal.startOfDay(for: s.created), to: today).day ?? 0
            groups[n < 1 ? 0 : n < 2 ? 1 : n < 7 ? 2 : 3].append(s)
        }
        return groups.indices.filter { !groups[$0].isEmpty }.map { ($0, groups[$0]) }
    }

    private func own(_ s: Song) async {
        do { try await SparkAPI.current?.ownSong(s.id); await m.load() } catch { m.error = error.localizedDescription }
    }

    /// The picked file as it is (the Spark checks format, size and the day's count).
    private func send(_ url: URL) async {
        let open = url.startAccessingSecurityScopedResource()
        defer { if open { url.stopAccessingSecurityScopedResource() } }
        do {
            let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            if size > (m.editing?.uploadMB ?? 30) * 1_048_576 {
                m.error = String(localized: "Die Datei ist zu groß.")
                return
            }
            let data = try Data(contentsOf: url)
            try await SparkAPI.current?.uploadSong(data, name: url.deletingPathExtension().lastPathComponent)
            await m.load()
        } catch { m.error = error.localizedDescription }
    }

    private func write() async {
        writing = true
        defer { writing = false }
        do {
            guard let r = try await SparkAPI.current?.writeLyrics(wish, seconds: m.length) else { return }
            (lyrics, wish, caption) = (r.lyrics, r.wish, (r.caption, r.wish))
            note = (r.names ? String(localized: "Künstlernamen sind jetzt Stilwörter in der Beschreibung.") + " " : "")
                + String(localized: "Der Text steht im Feld: prüfen, ändern, dann „Machen“.")
            m.error = nil
        } catch { m.error = error.localizedDescription }
    }

    private func make() async {
        if sung && lyrics.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            await write()
            return
        }
        do {
            try await SparkAPI.current?.makeSong(wish, seconds: m.length, lyrics: sung ? lyrics : nil,
                                                 caption: caption.1 == wish ? caption.0 : "")
            (wish, lyrics, note, caption) = ("", "", nil, ("", ""))
            await m.load()
            await m.follow()
        } catch { m.error = error.localizedDescription }
    }
}

/// Musik bearbeiten in the app: the same kinds as under Ich → Musik in the panel, with fixed fields; the part of the
/// song as from/to seconds (the wave stays in the panel). Each change is a new version, the original stays.
struct SongEditView: View {
    let song: Song
    let editing: SongEditing
    var done: () async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var art = "verlaengern"
    @State private var wish = ""
    @State private var from = 0.0
    @State private var to = 0.0
    @State private var front = false
    @State private var add = 30
    @State private var genre = ""
    @State private var near = 2
    @State private var tempo = 100
    @State private var halftones = 0
    @State private var fadeIn = 0
    @State private var fadeOut = 0
    @State private var many = 1
    @State private var sending = false
    @State private var error: String?
    @State private var parts: [LyricPart] = []
    @State private var fresh = false
    @State private var length = 120

    /// One part of the lyrics ([verse], [chorus], …) for Text ändern.
    struct LyricPart: Identifiable {
        let id = UUID()
        var tag: String
        var text = ""
    }
    static let partKinds: [(String, LocalizedStringKey)] = [("verse", "Strophe"), ("chorus", "Refrain"), ("pre-chorus", "Vor-Refrain"),
        ("bridge", "Bridge"), ("intro", "Intro"), ("outro", "Outro"), ("instrumental", "Instrumental")]

    /// The lyrics as parts: a line "[tag]" starts one, lines before the first tag are a verse (musik.js muParts).
    static func parse(_ text: String) -> [LyricPart] {
        var out: [LyricPart] = []
        for line in text.components(separatedBy: "\n") {
            let l = line.trimmingCharacters(in: .whitespaces)
            if l.hasPrefix("["), l.hasSuffix("]"), (4...22).contains(l.count) {
                out.append(LyricPart(tag: String(l.dropFirst().dropLast()).lowercased()))
                continue
            }
            if out.isEmpty { if l.isEmpty { continue }; out.append(LyricPart(tag: "verse")) }
            out[out.count - 1].text += (out[out.count - 1].text.isEmpty ? "" : "\n") + line
        }
        return out.map { LyricPart(tag: $0.tag, text: $0.text.trimmingCharacters(in: .whitespacesAndNewlines)) }
    }

    static let arts: [(String, LocalizedStringKey)] = [("abschnitt", "Abschnitt neu"), ("verlaengern", "Verlängern"),
        ("richtung", "Musikrichtung"), ("remix", "Remix"), ("text", "Text ändern"), ("schneiden", "Schneiden & Blenden"),
        ("tempo", "Tempo & Tonart")]
    private var model: Bool { ["abschnitt", "verlaengern", "richtung", "remix", "text"].contains(art) }
    private var en: Bool { Locale.current.language.languageCode?.identifier == "en" }

    var body: some View {
        Form {
            // the same order as the panel's own page (Dominik 2026-10-21 „1“): the song on top, the tools as one row to
            // swipe, their fields below, the button fixed at the bottom
            Section {
                Text(verbatim: song.label.isEmpty ? song.title : song.label).font(.headline).lineLimit(2)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Self.arts, id: \.0) { a in
                            Button { art = a.0 } label: {
                                Text(a.1).font(.subheadline.weight(art == a.0 ? .semibold : .regular))
                                    .padding(.horizontal, 12).padding(.vertical, 7)
                                    .background(Capsule().fill(art == a.0 ? Color.accentColor : Color.secondary.opacity(0.12)))
                                    .foregroundStyle(art == a.0 ? Color.white : Color.primary)
                            }
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(art == a.0 ? .isSelected : [])
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
            if art == "abschnitt" || art == "schneiden" {
                Section("Bereich (Sekunden)") {
                    Stepper(value: $from, in: 0...Double(max(1, song.seconds)), step: 1) { Text("Von \(Int(from)) s") }
                    Stepper(value: $to, in: 0...Double(max(1, song.seconds)), step: 1) { Text("Bis \(Int(to)) s") }
                }
            }
            if art == "text" {
                // drag a part by holding it, swipe to remove it (the panel: the handle ⠿ or ↑/↓)
                Section {
                    ForEach($parts) { $p in
                        VStack(alignment: .leading) {
                            Picker("Teil", selection: $p.tag) {
                                ForEach(Self.partKinds, id: \.0) { Text($0.1).tag($0.0) }
                                if !Self.partKinds.contains(where: { $0.0 == p.tag }) { Text(verbatim: p.tag).tag(p.tag) }
                            }
                            TextField("Text", text: $p.text, axis: .vertical).lineLimit(2...8)
                        }
                    }
                    .onMove { parts.move(fromOffsets: $0, toOffset: $1) }
                    .onDelete { parts.remove(atOffsets: $0) }
                    Button("Strophe hinzufügen") { parts.append(LyricPart(tag: "verse")) }
                    Button("Refrain hinzufügen") { parts.append(LyricPart(tag: "chorus")) }
                } header: { Text("Liedtext") } footer: { Text("Zum Verschieben halten und ziehen, zum Entfernen nach links wischen.") }
                Section {
                    Toggle("Ganz neu machen, mit eigener Länge", isOn: $fresh)
                    if fresh { Stepper(value: $length, in: 30...600, step: 10) { Text("Länge \(length) s") } }
                    else { Stepper(value: $near, in: 0...4) { Text("Nähe zum Original: \(near + 1) von 5") } }
                }
            }
            Section {
                switch art {
                case "text":
                    EmptyView()
                case "abschnitt":
                    TextField("Was soll in dem Teil anders sein?", text: $wish, axis: .vertical).lineLimit(1...3)
                case "verlaengern":
                    Picker("Wo", selection: $front) { Text("Hinten").tag(false); Text("Vorne").tag(true) }.pickerStyle(.segmented)
                    Stepper(value: $add, in: 5...editing.maxAdd, step: 5) { Text("\(add) Sekunden länger") }
                    TextField("Wie soll es weitergehen? (frei lassen: wie bisher)", text: $wish, axis: .vertical).lineLimit(1...3)
                case "richtung":
                    Picker("Musikrichtung", selection: $genre) {
                        Text("Eigene Worte").tag("")
                        ForEach(editing.genres, id: \.key) { g in Text(verbatim: en ? g.en : g.de).tag(g.key) }
                    }
                    if genre.isEmpty { TextField("z. B. Bossa Nova mit Flöte", text: $wish) }
                    Stepper(value: $near, in: 0...4) { Text("Nähe zum Original: \(near + 1) von 5") }
                case "remix":
                    TextField("Wie soll der Remix klingen? (frei lassen: überraschen)", text: $wish, axis: .vertical).lineLimit(1...3)
                    Stepper(value: $near, in: 0...4) { Text("Nähe zum Original: \(near + 1) von 5") }
                case "schneiden":
                    Stepper(value: $fadeIn, in: 0...30) { Text("Einblenden \(fadeIn) s") }
                    Stepper(value: $fadeOut, in: 0...30) { Text("Ausblenden \(fadeOut) s") }
                default:
                    Stepper(value: $tempo, in: 75...125, step: 5) { Text("Tempo \(tempo) Prozent") }
                    Stepper(value: $halftones, in: -4...4) { Text("Tonart \(halftones) Halbtöne") }
                }
                if model { Stepper(value: $many, in: 1...3) { Text("\(many) Vorschläge") } }
            } footer: { Text("Teile außerhalb des Bereichs bleiben im Originalklang. Jede Änderung ist eine neue Fassung, das Original bleibt.") }
            if let error { Text(SparkAPI.way(error)).foregroundStyle(.red) }
        }
        .navigationTitle("Bearbeiten")
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } } }
        .safeAreaInset(edge: .bottom) {
            Button { Task { await send() } } label: {
                Text(model ? (many > 1 ? "\(many) Vorschläge machen" : "Vorschlag machen") : "Neue Fassung").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent).controlSize(.large).disabled(sending)
            .padding(.horizontal).padding(.vertical, 8).background(.bar)
        }
        .onAppear {
            to = Double(song.seconds)
            length = max(30, min(600, song.seconds))
            parts = Self.parse(song.lyrics)
            if parts.isEmpty { parts = [LyricPart(tag: "verse"), LyricPart(tag: "chorus")] }
        }
    }

    private func send() async {
        var b: [String: Any] = ["art": art]
        switch art {
        case "abschnitt": b.merge(["von": from, "bis": to, "wunsch": wish, "vorschlaege": many]) { $1 }
        case "verlaengern": b.merge(["wo": front ? "vorne" : "hinten", "sekunden": add, "wunsch": wish, "vorschlaege": many]) { $1 }
        case "richtung": b.merge(["richtung": genre, "worte": genre.isEmpty ? wish : "", "nah": near, "vorschlaege": many]) { $1 }
        case "remix": b.merge(["wunsch": wish, "nah": near, "vorschlaege": many]) { $1 }
        case "text":
            let text = parts.filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || $0.tag == "instrumental" }
                .map { "[\($0.tag)]\n" + $0.text.trimmingCharacters(in: .whitespacesAndNewlines) }.joined(separator: "\n\n")
            b.merge(["liedtext": text, "nah": near, "vorschlaege": fresh ? 1 : many]) { $1 }
            if fresh { b.merge(["neu": true, "sekunden": length]) { $1 } }
        case "schneiden":
            // the whole song: only the fades; else the part to keep (the Spark checks it against the length)
            if from > 0 || to < Double(song.seconds) { b.merge(["von": from, "bis": min(to, Double(song.seconds))]) { $1 } }
            b.merge(["einblenden": fadeIn, "ausblenden": fadeOut]) { $1 }
        default: b.merge(["tempo": tempo, "halbtoene": halftones]) { $1 }
        }
        sending = true
        defer { sending = false }
        do {
            try await SparkAPI.current?.editSong(song.id, b)
            await done()
            dismiss()
        } catch { self.error = error.localizedDescription }
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
