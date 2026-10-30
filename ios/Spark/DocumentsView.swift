import QuickLook
import SwiftUI

/// Meine Sachen → Dokumente: the profile's documents on the Spark, the same as Ich → Dokumente in the panel
/// (Dominik 2026-10-17): one row per document with the Steckbrief's title, quick filters with their numbers,
/// source, sort and tag, groups by time, a search in titles, senders and tags (Enter also searches the content),
/// "Auswählen" for several at once and a page per document. Only while Eigene Dokumente is released for the
/// profile; the Spark checks every change (iphone.THINGS "documents").
@MainActor
final class DocumentsModel: ObservableObject {
    @Published var docs: [SparkDoc] = []
    /// what the admin released for the profile (GET /api/profile/wissen "allow": shared, brief, originals …)
    @Published var allow: [String: Bool] = [:]
    @Published var loading = true
    @Published var off = false
    @Published var error: String?
    @Published var note: String?
    /// the content search (Enter in the search field): hits with the document and a piece of its text
    @Published var hits: [ContentHit] = []
    @Published var searching = false
    /// source reMarkable: the last comparison with the account (GET /api/profile/wissen "remarkable"), nil while none is connected
    @Published var rmAt: Date?
    @Published var rmPages = 0
    @Published var rmError = false
    @Published var rmOn = false

    /// one change, then the list again
    func change(_ what: @escaping (SparkAPI) async throws -> String?) async {
        guard let api = SparkAPI.current else { return }
        do {
            note = try await what(api)
            error = nil
        } catch { self.error = error.localizedDescription }
        await load()
    }

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            if let d = try await api.docs() { docs = d; off = false } else { off = true }
            if !off, let w = try? await api.object("GET", "api/profile/wissen") {
                allow = (w["allow"] as? [String: Bool]) ?? [:]
                let r = w["remarkable"] as? [String: Any]
                rmOn = r != nil
                let at = (r?["at"] as? NSNumber)?.doubleValue ?? 0
                rmAt = at > 0 ? Date(timeIntervalSince1970: at) : nil
                rmPages = (r?["pages"] as? NSNumber)?.intValue ?? 0
                rmError = r?["error"] as? Bool ?? false
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    /// several documents at once (POST /api/profile/wissen/batch): delete, use, unuse, share, unshare, reread
    func batch(_ what: String, _ ids: Set<String>) async {
        await change { api in
            let r = try await api.object("POST", "api/profile/wissen/batch", body: ["do": what, "ids": Array(ids.prefix(200))], timeout: 180)
            let done = (r["done"] as? NSNumber)?.intValue ?? 0, failed = (r["failed"] as? NSNumber)?.intValue ?? 0
            return failed > 0 ? String(localized: "\(done) erledigt, \(failed) nicht.") : String(localized: "\(done) erledigt.")
        }
    }

    func searchContent(_ q: String) async {
        let q = q.trimmingCharacters(in: .whitespaces)
        guard let api = SparkAPI.current, q.count >= 2 else { hits = []; return }
        searching = true
        defer { searching = false }
        do {
            let r = try await api.object("POST", "api/profile/wissen/search", body: ["q": String(q.prefix(300))], timeout: 60)
            hits = (r["hits"] as? [[String: Any]] ?? []).compactMap { h in
                guard let id = h["id"] as? String, SparkAPI.isDoc(id) else { return nil }
                return ContentHit(id: id, page: (h["page"] as? NSNumber)?.intValue, text: String((h["text"] as? String ?? "").prefix(300)))
            }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

/// A place in a document the content search found (Enter in the search field).
struct ContentHit: Identifiable {
    let id: String
    let page: Int?
    let text: String
}

/// The quick filters above the list, each with its number.
enum DocFilter: String, CaseIterable, Identifiable {
    case all, due, reading, shared, unused, broken
    var id: String { rawValue }

    var name: LocalizedStringKey {
        switch self {
        case .all: "Alle"
        case .due: "Frist offen"
        case .reading: "Wird gelesen"
        case .shared: "Für alle"
        case .unused: "Suche aus"
        case .broken: "Nicht lesbar"
        }
    }

    func has(_ d: SparkDoc) -> Bool {
        switch self {
        case .all: true
        case .due: !d.due.isEmpty && d.due >= ThingsView.today
        case .reading: d.todo > 0 || d.state == "reading"
        case .shared: d.shared
        case .unused: !d.use
        case .broken: d.state == "error"
        }
    }
}

enum DocSort: String, CaseIterable, Identifiable {
    case newest, name, due, size
    var id: String { rawValue }

    var name: LocalizedStringKey {
        switch self {
        case .newest: "Neueste zuerst"
        case .name: "Nach Name"
        case .due: "Nach Frist"
        case .size: "Nach Größe"
        }
    }
}

struct DocumentsView: View {
    @StateObject private var m = DocumentsModel()
    @State private var search = ""
    @State private var filter = DocFilter.all
    @AppStorage("docSort") private var sort = DocSort.newest
    @AppStorage("docSource") private var source = ""
    @State private var tag = ""
    @State private var picked = Set<String>()
    @State private var edit: EditMode = .inactive
    @State private var removing = false

    /// where a document came from, as the panel names it (me.js DOCSRC)
    static let sources: [(String, LocalizedStringKey)] = [
        ("upload", "Hochgeladen"), ("app", "iPhone-App"), ("begleiter", "Begleiter"), ("remarkable", "reMarkable"),
        ("agent", "Aufträge"), ("spark", "Vom Spark erstellt"), ("nas", "Wissensordner"), ("eingang", "NAS-Eingang"),
    ]

    static func source(_ d: SparkDoc) -> String { sources.contains { $0.0 == d.source } ? d.source : "upload" }

    private var shown: [SparkDoc] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        var l = m.docs.filter { d in
            filter.has(d) && (source.isEmpty || Self.source(d) == source)
                && (tag.isEmpty || d.tags.contains { $0.caseInsensitiveCompare(tag) == .orderedSame })
                && (q.isEmpty || [d.shown, d.name, d.sender, d.art, d.tags.joined(separator: " ")].contains { $0.lowercased().contains(q) })
        }
        switch sort {
        case .newest: break
        case .name: l.sort { $0.shown.localizedStandardCompare($1.shown) == .orderedAscending }
        case .due: l.sort { ($0.due.isEmpty ? "9999" : $0.due) < ($1.due.isEmpty ? "9999" : $1.due) }
        case .size: l.sort { $0.size > $1.size }
        }
        return l
    }

    /// source reMarkable: when the Spark last compared with the account and how many pages it read anew (Dominik 2026-10-22 „1a“)
    private var rmLine: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let at = m.rmAt {
                Text("Letzter Abgleich \(at.formatted(date: .abbreviated, time: .shortened)) · \(m.rmPages) Seiten neu")
            } else {
                Text("Noch kein Abgleich mit dem reMarkable")
            }
            if m.rmError { Text(SparkAPI.way(String(localized: "Der letzte Abgleich hatte einen Fehler (Ich → reMarkable)."))).foregroundStyle(.red) }
        }
        .font(.caption).foregroundStyle(.secondary)
    }

    /// the groups by time (only for "Neueste zuerst"): this week, this month, older
    private var groups: [(LocalizedStringKey, [SparkDoc])] {
        let l = shown
        guard sort == .newest else { return [("", l)] }
        let now = Date(), cal = Calendar.current
        let week = cal.date(byAdding: .day, value: -7, to: now) ?? now, month = cal.date(byAdding: .day, value: -31, to: now) ?? now
        return [("Diese Woche", l.filter { $0.when >= week }), ("Diesen Monat", l.filter { $0.when < week && $0.when >= month }),
                ("Älter", l.filter { $0.when < month })].filter { !$0.1.isEmpty }
    }

    private var tags: [(String, Int)] {
        var n: [String: Int] = [:]
        for d in m.docs { for t in d.tags { n[t, default: 0] += 1 } }
        return n.sorted { $0.value == $1.value ? $0.key < $1.key : $0.value > $1.value }.prefix(30).map { ($0.key, $0.value) }
    }

    var body: some View {
        List(selection: $picked) {
            if m.loading {
                ProgressView()
            } else if m.off {
                Text(SparkAPI.way(String(localized: "Der Admin hat Eigene Dokumente noch nicht freigegeben (Funktionen → Eigene Dokumente).")))
            } else if m.docs.isEmpty {
                Text("Noch keine Dokumente.").foregroundStyle(.secondary)
            } else {
                Section { chips }
                    .listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
                if source == "remarkable" && m.rmOn { rmLine }
            }
            if !m.hits.isEmpty || m.searching {
                Section("Im Inhalt gefunden") {
                    if m.searching { ProgressView() }
                    ForEach(m.hits) { h in
                        if let d = m.docs.first(where: { $0.id == h.id }) {
                            NavigationLink { DocumentView(doc: d) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(verbatim: d.shown).lineLimit(1)
                                    // the document's own words: plain text, nothing in it is a link or a command
                                    Text(verbatim: h.text).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                                }
                            }
                        }
                    }
                }
            }
            ForEach(groups, id: \.1.first?.id) { g in
                Section {
                    ForEach(g.1) { d in
                        NavigationLink { DocDetailView(doc: d, changed: { Task { await m.load() } }) } label: { DocRow(doc: d) }
                            .tag(d.id)
                            .swipeActions(edge: .trailing) {
                                Button(role: .destructive) { picked = [d.id]; removing = true } label: { Label("Löschen", systemImage: "trash") }
                            }
                    }
                } header: { HStack { Text(g.0); Spacer(); Text(verbatim: String(g.1.count)) } }
            }
            if !m.loading && !m.off && !m.docs.isEmpty && shown.isEmpty {
                Text("Kein Dokument passt zum Filter.").foregroundStyle(.secondary)
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            if !m.off && !m.loading {
                Section {
                    // only while the admin released the knowledge book for this profile (hello "areas")
                    if Conversation.shared.allowed.areas.contains("wissensbuch") {
                        NavigationLink("Wissensbuch") { WissensbuchView() }
                    }
                    NavigationLink("Schalter für Dokumente") { DocSwitchesView() }
                    NavigationLink("Ausgelassene Ordner") { LeftOutView() }
                }
            }
        }
        .environment(\.editMode, $edit)
        .navigationTitle("Dokumente")
        .searchable(text: $search, prompt: Text("Titel, Absender, Tag"))
        .onSubmit(of: .search) { Task { await m.searchContent(search) } }
        .onChange(of: search) { _, v in if v.isEmpty { m.hits = [] } }
        .toolbar { toolbar }
        .refreshable { await m.load() }
        .task { await m.load() }
        .confirmationDialog("Dokumente löschen?", isPresented: $removing, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) {
                let ids = picked
                Task { await m.batch("delete", ids); picked = []; edit = .inactive }
            }
        } message: { Text(verbatim: String(picked.count)) }
    }

    private var chips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(DocFilter.allCases) { f in
                    let n = m.docs.filter { f.has($0) }.count
                    if f == .all || n > 0 {
                        Button { filter = f } label: {
                            HStack(spacing: 4) { Text(f.name); Text(verbatim: String(n)).foregroundStyle(filter == f ? .white : .secondary) }
                                .font(.footnote).padding(.horizontal, 10).padding(.vertical, 6)
                                .background(filter == f ? Color.accentColor : Color(.secondarySystemGroupedBackground), in: Capsule())
                                .foregroundStyle(filter == f ? .white : .primary)
                        }
                        .buttonStyle(.borderless)   // each chip on its own in the List row
                    }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 4)
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .primaryAction) {
            Button(edit.isEditing ? "Fertig" : "Auswählen") { edit = edit.isEditing ? .inactive : .active; picked = [] }
        }
        ToolbarItem(placement: .topBarTrailing) {
            Menu {
                Picker("Sortieren", selection: $sort) { ForEach(DocSort.allCases) { Text($0.name).tag($0) } }
                Picker("Quelle", selection: $source) {
                    Text("Alle Quellen").tag("")
                    ForEach(Self.sources.filter { s in m.docs.contains { Self.source($0) == s.0 } }, id: \.0) { Text($0.1).tag($0.0) }
                }
                if !tags.isEmpty {
                    Picker("Tag", selection: $tag) {
                        Text("Alle Tags").tag("")
                        ForEach(tags, id: \.0) { t in Text(verbatim: "#\(t.0) (\(t.1))").tag(t.0) }
                    }
                }
            } label: {
                Image(systemName: source.isEmpty && tag.isEmpty && sort == .newest ? "line.3.horizontal.decrease.circle" : "line.3.horizontal.decrease.circle.fill")
            }
            .accessibilityLabel(Text("Sortieren und filtern"))
        }
        if edit.isEditing && !picked.isEmpty {
            ToolbarItemGroup(placement: .bottomBar) {
                Button(role: .destructive) { removing = true } label: { Label("Löschen", systemImage: "trash") }
                Spacer()
                Menu {
                    if m.allow["shared"] == true {
                        Button { act("share") } label: { Label("Für alle freigeben", systemImage: "person.2") }
                        Button { act("unshare") } label: { Label("Nur für mich", systemImage: "person") }
                    }
                    Button { act("use") } label: { Label("Wieder durchsuchen", systemImage: "eye") }
                    Button { act("unuse") } label: { Label("Nicht mehr durchsuchen", systemImage: "eye.slash") }
                    if picked.count <= 20 {
                        Button { act("reread") } label: { Label("Neu einlesen", systemImage: "arrow.clockwise") }
                    }
                } label: { Label("Mehr", systemImage: "ellipsis.circle") }
                Text(verbatim: String(picked.count)).foregroundStyle(.secondary)
            }
        }
    }

    private func act(_ what: String) {
        let ids = picked
        Task { await m.batch(what, ids); picked = []; edit = .inactive }
    }
}

/// One document in the list: symbol, title, kind · sender · source, date, and a mark only where something matters.
struct DocRow: View {
    let doc: SparkDoc

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: ThingsView.docIcon(doc)).foregroundStyle(.white).frame(width: 30, height: 30)
                .background(doc.source == "remarkable" ? Color.purple : Color.blue, in: RoundedRectangle(cornerRadius: 7))
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: doc.shown).lineLimit(1)
                Text(verbatim: sub).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 3) {
                Text(doc.when, format: .dateTime.day().month()).font(.caption).foregroundStyle(.secondary)
                mark
            }
        }
    }

    private var sub: String {
        [doc.art, doc.sender, doc.source == "nas" ? "NAS · " + (doc.place.isEmpty ? "/" : doc.place) : Self.sourceName(doc)]
            .filter { !$0.isEmpty }.joined(separator: " · ")
    }

    static func sourceName(_ d: SparkDoc) -> String {
        switch DocumentsView.source(d) {
        case "app": String(localized: "iPhone-App")
        case "begleiter": String(localized: "Begleiter")
        case "remarkable": "reMarkable"
        case "agent": String(localized: "Aufträge")
        case "spark": String(localized: "Vom Spark erstellt")
        case "nas": String(localized: "Wissensordner")
        case "eingang": String(localized: "NAS-Eingang")
        default: String(localized: "Hochgeladen")
        }
    }

    @ViewBuilder private var mark: some View {
        if !doc.due.isEmpty && doc.due >= ThingsView.today {
            badge(Text("Frist \(Self.day(doc.due))"), .red)
        } else if doc.state == "error" {
            badge(Text("nicht lesbar"), .red)
        } else if doc.todo > 0 && doc.pages > 0 {
            badge(Text(verbatim: "\(doc.pages - doc.todo)/\(doc.pages)"), .blue)
        } else if doc.todo > 0 || doc.state == "reading" {
            badge(Text("wird gelesen"), .blue)
        } else if doc.shared {
            badge(Text("für alle"), .green)
        } else if !doc.use {
            badge(Text("Suche aus"), .gray)
        }
    }

    /// "2026-10-30" as "30.10."
    static func day(_ iso: String) -> String {
        let p = iso.split(separator: "-")
        return p.count == 3 ? "\(p[2]).\(p[1])." : iso
    }

    private func badge(_ t: Text, _ c: Color) -> some View {
        t.font(.caption2.weight(.semibold)).padding(.horizontal, 6).padding(.vertical, 2)
            .background(c.opacity(0.15), in: Capsule()).foregroundStyle(c)
    }
}

/// One document on its own page: its Steckbrief, open it, tags, the switches and the actions, instead of a menu
/// behind a long press. Every change goes to the Spark, which checks it.
struct DocDetailView: View {
    @State var doc: SparkDoc
    var changed: () -> Void = {}
    @State private var allow: [String: Bool] = [:]
    @State private var newTag = ""
    @State private var removing = false
    @State private var note: String?
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    // what the language model read from the document: plain text, nothing in it is a link or a command
                    Text(verbatim: [doc.art, doc.sender].filter { !$0.isEmpty }.joined(separator: " · ")).font(.subheadline.bold())
                    HStack(spacing: 4) {
                        Text(verbatim: DocRow.sourceName(doc))
                        Text(verbatim: "·")
                        Text(doc.when, format: .dateTime.day().month().year())
                        if doc.pages > 0 { Text(verbatim: "·"); Text("\(doc.pages) Seiten") }
                        if doc.size > 0 { Text(verbatim: "·"); Text(verbatim: ByteCountFormatter.string(fromByteCount: Int64(doc.size), countStyle: .file)) }
                    }
                    .font(.caption).foregroundStyle(.secondary)
                    if !doc.brief.isEmpty { Text(verbatim: doc.brief).font(.callout) }
                    if !doc.due.isEmpty { Label { Text("Frist \(DocRow.day(doc.due))") } icon: { Image(systemName: "calendar.badge.exclamationmark") }.foregroundStyle(.red) }
                    if doc.state == "error" && !doc.note.isEmpty { Text(SparkAPI.way(doc.note)).foregroundStyle(.red).font(.caption) }
                    if doc.title != "" && doc.title != doc.name { Text(verbatim: doc.name).font(.caption2).foregroundStyle(.secondary) }
                }
            }
            Section("Öffnen") {
                NavigationLink { DocumentView(doc: doc) } label: {
                    Label(doc.file || doc.source == "nas" ? LocalizedStringKey("Original und Text") : LocalizedStringKey("Gelesener Text"),
                          systemImage: "doc.richtext")
                }
            }
            if allow["brief"] == true {
                Section {
                    FlowTags(tags: doc.tags) { t in Task { await setTags(doc.tags.filter { $0 != t }) } }
                    HStack {
                        TextField("Neuer Tag", text: $newTag).onSubmit { addTag() }
                        Button("Dazu") { addTag() }.disabled(newTag.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    Button("Automatische Tags") { Task { await save(["tags": NSNull()]) } }
                } header: { Text("Tags") }
            }
            Section("Einstellen") {
                Toggle("Assistent sucht darin", isOn: Binding(get: { doc.use }, set: { v in Task { await save(["use": v]) } }))
                if allow["shared"] == true {
                    Toggle("Für alle", isOn: Binding(get: { doc.shared }, set: { v in Task { await save(["shared": v]) } }))
                }
                if !doc.due.isEmpty {
                    Button { Task { await remind() } } label: { Label("An die Frist erinnern", systemImage: "bell") }
                }
            }
            Section {
                if doc.file {
                    Button { Task { await reread() } } label: { Label("Neu einlesen", systemImage: "arrow.clockwise") }
                }
                Button(role: .destructive) { removing = true } label: { Label("Löschen", systemImage: "trash") }
            }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle(Text(verbatim: doc.shown))
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if let w = try? await SparkAPI.current?.object("GET", "api/profile/wissen") { allow = (w["allow"] as? [String: Bool]) ?? [:] }
        }
        .confirmationDialog("Dokument löschen?", isPresented: $removing, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) {
                Task {
                    do { try await SparkAPI.current?.deleteDoc(doc.id); changed(); dismiss() }
                    catch { self.error = error.localizedDescription }
                }
            }
        } message: { Text(verbatim: doc.shown) }
    }

    private func addTag() {
        let t = newTag.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard !t.isEmpty, !doc.tags.contains(where: { $0.caseInsensitiveCompare(t) == .orderedSame }) else { newTag = ""; return }
        newTag = ""
        Task { await setTags(Array((doc.tags + [String(t.prefix(24))]).prefix(12))) }
    }

    private func setTags(_ tags: [String]) async {
        await save(["tags": tags.isEmpty ? NSNull() as Any : tags as Any])
    }

    private func save(_ body: [String: Any]) async {
        guard let api = SparkAPI.current else { return }
        do {
            try await api.setDoc(doc.id, body)
            if let v = body["use"] as? Bool { doc.use = v }
            if let v = body["shared"] as? Bool { doc.shared = v }
            if let fresh = try await api.docs()?.first(where: { $0.id == doc.id }) { doc = fresh }
            error = nil
            changed()
        } catch { self.error = error.localizedDescription }
    }

    private func remind() async {
        do {
            guard let r = try await SparkAPI.current?.docAction(doc.id, "remind") else { return }
            let when = Date(timeIntervalSince1970: ((r["due"] as? NSNumber)?.doubleValue ?? 0) / 1000)
            note = String(localized: "Erinnerung am \(when.formatted(date: .abbreviated, time: .shortened)).")
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func reread() async {
        do {
            _ = try await SparkAPI.current?.docAction(doc.id, "reread")
            note = String(localized: "Wird neu eingelesen.")
            error = nil
            changed()
        } catch { self.error = error.localizedDescription }
    }
}

/// The tags of a document as small buttons; a tap takes one away.
struct FlowTags: View {
    let tags: [String]
    let remove: (String) -> Void

    var body: some View {
        if tags.isEmpty {
            Text("Noch keine Tags.").foregroundStyle(.secondary)
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(tags, id: \.self) { t in
                        Button { remove(t) } label: {
                            Label { Text(verbatim: "#" + t) } icon: { Image(systemName: "xmark") }
                                .labelStyle(.titleAndIcon).font(.footnote)
                                .padding(.horizontal, 8).padding(.vertical, 4)
                                .background(Color(.secondarySystemFill), in: Capsule())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Text("Tag \(t) entfernen"))
                    }
                }
            }
        }
    }
}

/// The document functions under Ich → Dokumente: what the admin released is on for every profile at once (no own
/// switch per profile); only the reminder before a deadline stays the profile's own choice ("Fristen").
struct DocSwitchesView: View {
    @State private var due = false
    @State private var allow: [String: Bool] = [:]
    @State private var error: String?

    static let rows: [(String, LocalizedStringKey, LocalizedStringKey)] = [
        ("pictures", LocalizedStringKey("Bilder und Scans lesen"), LocalizedStringKey("Das Sprachmodell liest Fotos und gescannte Seiten, wenn der Spark Zeit hat.")),
        ("semantic", LocalizedStringKey("Nach Bedeutung suchen"), LocalizedStringKey("Findet auch Stellen mit anderen Worten.")),
        ("originals", LocalizedStringKey("Originale aufheben"), LocalizedStringKey("Die Datei selbst bleibt auf dem Spark, zum Ansehen und Neu einlesen.")),
        ("shared", LocalizedStringKey("Gemeinsame Dokumente"), LocalizedStringKey("Du darfst Dokumente für alle freigeben und siehst die der anderen.")),
        ("brief", LocalizedStringKey("Steckbrief und Tags"), LocalizedStringKey("Titel, Absender, Datum, Frist und Tags zu jedem Dokument.")),
    ]

    var body: some View {
        Form {
            if allow["brief"] ?? false {
                Section {
                    Toggle("Fristen", isOn: Binding(get: { due }, set: { v in due = v; Task { await save(v) } }))
                } footer: { Text("Erinnerung vor einer Frist, erst nach deinem Tippen.") }
            }
            Section {
                ForEach(Self.rows, id: \.0) { r in
                    LabeledContent {
                        Image(systemName: allow[r.0] == true ? "checkmark.circle.fill" : "xmark.circle")
                            .foregroundStyle(allow[r.0] == true ? .green : .secondary)
                    } label: {
                        Text(r.1)
                        Text(r.2)
                    }
                }
            } header: { Text("Funktionen") } footer: {
                if !allow.isEmpty && Self.rows.contains(where: { allow[$0.0] != true }) {
                    Text(SparkAPI.way(String(localized: "Der Admin hat das noch nicht freigegeben (Funktionen → Eigene Dokumente). Was er freigibt, gilt sofort für dich.")))
                }
            }
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Schalter für Dokumente")
        .task { await load() }
    }

    private func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let w = try await api.object("GET", "api/profile/wissen")
            allow = (w["allow"] as? [String: Bool]) ?? [:]
            due = (w["on"] as? [String: Any])?["due"] as? Bool ?? false
        } catch { self.error = error.localizedDescription }
    }

    private func save(_ value: Bool) async {
        do {
            _ = try await SparkAPI.current?.call("PUT", "api/iphone/settings", body: ["doc_due": value])
            error = nil
        } catch {
            self.error = error.localizedDescription
            due = !value
        }
    }
}

/// Ich → Dokumente → Ausgelassene Ordner (auslassen.py): folders and names the Spark never reads. The app shows the
/// list, lets a folder in again and adds or removes name rules; leaving out one folder happens in the panel's tree.
/// What the Spark sends is shown as text, never as a link or a command.
struct LeftOutView: View {
    struct Folder: Identifiable {
        let ort: String
        let path: String
        let place: String
        var id: String { ort + "\u{0}" + path }
    }

    @State private var folders: [Folder] = []
    @State private var names: [String] = []
    @State private var always: [String] = []
    @State private var loaded = false
    @State private var newName = ""
    @State private var askName = ""
    @State private var askDocs = 0
    @State private var asking = false
    @State private var note: String?
    @State private var error: String?

    var body: some View {
        Form {
            Section {
                Text("Ordner, die der Spark nie liest. Was schon gelesen war, verschwindet sofort aus der Suche. Am Ort ändert sich nichts; „Wieder zulassen“ liest neu.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Section {
                if loaded && folders.isEmpty { Text("Noch keiner.").foregroundStyle(.secondary) }
                ForEach(folders) { f in
                    LabeledContent {
                        Button("Wieder zulassen") { Task { await letIn(["ort": f.ort, "path": f.path]) } }
                    } label: {
                        Text(verbatim: f.path)
                        Text(verbatim: f.place)
                    }
                }
            } header: { Text("Ausgelassene Ordner") } footer: {
                Text(SparkAPI.way(String(localized: "Einen Ordner auslassen: im Panel unter Ich → Dokumente → Ausgelassene Ordner im Ordnerbaum.")))
            }
            Section {
                ForEach(names, id: \.self) { n in
                    Text(verbatim: n).swipeActions {
                        Button(role: .destructive) { Task { await letIn(["name": n]) } } label: { Label("Entfernen", systemImage: "trash") }
                    }
                }
                HStack {
                    TextField("Name, z. B. Archiv oder Alt*", text: $newName)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button("Hinzufügen") { Task { await probe() } }
                        .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } header: { Text("Ordnernamen, die überall ausgelassen werden") } footer: {
                Text("Groß und klein egal, * am Ende heißt „beginnt mit“.")
            }
            if !always.isEmpty {
                Section { Text(verbatim: always.joined(separator: " · ")).foregroundStyle(.secondary) } header: { Text("Immer ausgelassen") }
            }
            if let n = note { Text(verbatim: n).foregroundStyle(.secondary) }
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Ausgelassene Ordner")
        .task { await load() }
        .refreshable { await load() }
        .confirmationDialog("Überall auslassen?", isPresented: $asking, titleVisibility: .visible) {
            Button("Auslassen", role: .destructive) { Task { await add(askName) } }
        } message: {
            Text("Dokumente, die sofort aus der Suche verschwinden: \(askDocs). Am Ort bleibt alles.")
        }
    }

    private func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/auslassen")
            folders = ((d["folders"] as? [[String: Any]]) ?? []).compactMap { f in
                guard let o = f["ort"] as? String, let p = f["path"] as? String else { return nil }
                return Folder(ort: o, path: p, place: (f["place"] as? String) ?? "")
            }
            names = (d["names"] as? [String]) ?? []
            always = (d["always"] as? [String]) ?? []
            loaded = true
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func probe() async {
        let v = newName.trimmingCharacters(in: .whitespaces)
        do {
            let r = try await SparkAPI.current?.object("POST", "api/profile/auslassen", body: ["name": v, "probe": true]) ?? [:]
            askName = v
            askDocs = (r["docs"] as? Int) ?? 0
            if askDocs > 0 { asking = true } else { await add(v) }
        } catch { self.error = error.localizedDescription }
    }

    private func add(_ name: String) async {
        do {
            _ = try await SparkAPI.current?.call("POST", "api/profile/auslassen", body: ["name": name])
            newName = ""
            note = String(localized: "Ausgelassen. Der Spark nimmt die Dokumente im Hintergrund aus der Suche.")
            await load()
        } catch { self.error = error.localizedDescription }
    }

    private func letIn(_ q: [String: String]) async {
        do {
            _ = try await SparkAPI.current?.call("DELETE", "api/profile/auslassen", query: q)
            note = String(localized: "Wieder zugelassen. Der nächste Abgleich liest den Ordner neu.")
            await load()
        } catch { self.error = error.localizedDescription }
    }
}

struct DocumentView: View {
    let doc: SparkDoc
    @State private var original: URL?
    @State private var text: DocText?
    @State private var tab = 0
    @State private var loading = true
    @State private var error: String?
    @State private var more = false

    var body: some View {
        VStack(spacing: 0) {
            if original != nil {
                Picker("Ansicht", selection: $tab) {
                    Text("Original").tag(0)
                    Text("Text").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()
            }
            if loading {
                ProgressView().frame(maxHeight: .infinity)
            } else if let original, tab == 0 {
                QuickLookView(url: original)
            } else {
                textView
            }
        }
        .navigationTitle(Text(verbatim: doc.name))
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .onDisappear { if let original { try? FileManager.default.removeItem(at: original) } }
    }

    private var textView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
                if let t = text {
                    if t.parts.isEmpty {
                        Text(doc.todo > 0 ? "Der Spark liest das Dokument noch." : "Kein Text gespeichert.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(Array(t.parts.enumerated()), id: \.offset) { i, p in
                        if let page = p.page, page != (i > 0 ? t.parts[i - 1].page : nil) {
                            Text("Seite \(page)").font(.caption.bold()).foregroundStyle(.secondary)
                        }
                        // the document's own words: plain text, nothing in it is a link or a command
                        Text(verbatim: p.text).textSelection(.enabled)
                    }
                    if let next = t.next {
                        Button {
                            Task { await readOn(from: next) }
                        } label: {
                            if more { ProgressView() } else { Label("Weiterlesen", systemImage: "arrow.down.circle") }
                        }
                        .buttonStyle(.bordered)
                        .disabled(more)
                    }
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func load() async {
        guard let api = SparkAPI.current, loading else { return }
        if doc.file || doc.source == "nas" { original = try? await api.docOriginal(doc.id) }   // NAS: fetched fresh by the Spark
        do { text = try await api.docText(doc.id) } catch { self.error = error.localizedDescription }
        if original == nil { tab = 1 }
        loading = false
    }

    /// The next part of a long document, added below what is already shown.
    private func readOn(from start: Int) async {
        guard let api = SparkAPI.current, !more else { return }
        more = true
        defer { more = false }
        do {
            let part = try await api.docText(doc.id, start: start)
            text?.parts += part.parts
            text?.cut = part.cut
            text?.next = part.next.flatMap { $0 > start ? $0 : nil }
        } catch { self.error = error.localizedDescription }
    }
}

/// Apple's viewer for one local file (PDF or picture), with zoom, search and sharing.
struct QuickLookView: UIViewControllerRepresentable {
    let url: URL

    func makeCoordinator() -> Source { Source(url: url) }

    func makeUIViewController(context: Context) -> QLPreviewController {
        let c = QLPreviewController()
        c.dataSource = context.coordinator
        return c
    }

    func updateUIViewController(_ c: QLPreviewController, context: Context) {}

    final class Source: NSObject, QLPreviewControllerDataSource {
        let url: URL
        init(url: URL) { self.url = url }
        func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem { url as NSURL }
    }
}

/// "Vom Spark erstellt": the documents the Spark made (Dokumente erstellen, docmake.py) with a small preview of the
/// first slide, page or sheet; tapping opens Apple's viewer (Word, PowerPoint, Excel, PDF) with "Teilen" to save
/// it in Files, send it on or open it in another app. Reading only: making and changing stay with the assistant.
@MainActor
final class MadeDocsModel: ObservableObject {
    @Published var docs: [MadeDoc] = []
    @Published var loading = true
    @Published var off = false
    @Published var error: String?

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            if let d = try await api.madeDocs() { docs = d; off = false } else { off = true }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }
}

struct MadeDocsView: View {
    @StateObject private var m = MadeDocsModel()

    var body: some View {
        List {
            if m.loading {
                ProgressView()
            } else if m.off {
                Text(SparkAPI.way(String(localized: "Der Admin hat „Dokumente erstellen“ noch nicht freigegeben (Funktionen → Eigene Dokumente → Dokumente erstellen).")))
            } else if m.docs.isEmpty {
                Text("Noch nichts erstellt. Sag zum Beispiel „Mach eine Präsentation über unseren Urlaub“.")
                    .foregroundStyle(.secondary)
            }
            ForEach(m.docs) { d in
                NavigationLink { MadeDocView(doc: d) } label: {
                    HStack(alignment: .top, spacing: 12) {
                        PeekView(doc: d).frame(width: 96).accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: d.title).lineLimit(2)
                            HStack(spacing: 6) {
                                Text(verbatim: d.formatName)
                                Text("Version \(d.version)")
                                Text(d.updated, format: .dateTime.day().month())
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle("Vom Spark erstellt")
        .refreshable { await m.load() }
        .task { await m.load() }
    }
}

/// The small preview of a made document: the first part in a few lines, in the file's own colours (docrender.STYLES).
struct PeekView: View {
    let doc: MadeDoc
    var big = false

    private var dark: Bool { doc.style == "spark-dunkel" }
    private var accent: Color {
        switch doc.style {
        case "spark-hell": return Color(red: 0.36, green: 0.36, blue: 0.94)
        case "spark-dunkel": return Color(red: 0.55, green: 0.55, blue: 1)
        case "frisch": return Color(red: 0.06, green: 0.46, blue: 0.43)
        case "warm": return Color(red: 0.76, green: 0.25, blue: 0.05)
        default: return Color(red: 0.18, green: 0.23, blue: 0.31)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: big ? 4 : 2) {
            Text(verbatim: doc.heading.isEmpty ? doc.title : doc.heading)
                .font(.system(size: big ? 15 : 7, weight: .semibold)).foregroundStyle(accent).lineLimit(2)
            ForEach(Array(doc.rows.enumerated()), id: \.offset) { _, r in
                Text(verbatim: r.joined(separator: " · ")).lineLimit(1)
            }
            ForEach(Array(doc.lines.enumerated()), id: \.offset) { _, l in
                Text(verbatim: doc.kind == "praesentation" ? "• " + l : l).lineLimit(big ? 3 : 1)
            }
            Spacer(minLength: 0)
        }
        .font(.system(size: big ? 12 : 5))
        .foregroundStyle(dark ? Color(white: 0.92) : Color(red: 0.11, green: 0.14, blue: 0.2))
        .padding(big ? 12 : 5)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .aspectRatio(doc.kind == "praesentation" ? 16 / 9 : 1 / 1.1, contentMode: .fit)
        .background(dark ? Color(red: 0.04, green: 0.05, blue: 0.08) : Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.3)))
    }
}

/// One made document in Apple's viewer, "Teilen" in the bar; the preview while the file loads or when it cannot.
struct MadeDocView: View {
    let doc: MadeDoc
    @State private var file: URL?
    @State private var error: String?
    @State private var loading = true

    var body: some View {
        Group {
            if let file {
                QuickLookView(url: file)
            } else if loading {
                ProgressView().frame(maxHeight: .infinity)
            } else {
                VStack(spacing: 12) {
                    PeekView(doc: doc, big: true).padding()
                    if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
                    Spacer()
                }
            }
        }
        .navigationTitle(Text(verbatim: doc.title))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if let file { ShareLink(item: file) { Label("Teilen", systemImage: "square.and.arrow.up") } }
            }
        }
        .task { await load() }
        .onDisappear { if let file { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) } }
    }

    private func load() async {
        guard let api = SparkAPI.current, file == nil else { return }
        do { file = try await api.madeFile(doc) } catch { self.error = error.localizedDescription }
        loading = false
    }
}

// ---------------------------------------------------------------- Wissensbuch (wissensbuch.py, plan wissensbuch Stufe E)
/// One sentence of the knowledge book with its source: the text is the model's from an own document or a Kiwix
/// article, so it is shown as plain text only (Text(verbatim:)), never as a link or a command.
struct WbSentence: Identifiable, Hashable {
    let id: Int
    let text: String
    let source: String
    let page: Int?
    let contradiction: Bool
    let stale: Bool

    static func from(_ d: [String: Any]) -> WbSentence? {
        guard let id = (d["id"] as? NSNumber)?.intValue, id > 0 else { return nil }
        let p = (d["page"] as? NSNumber)?.intValue ?? 0
        return WbSentence(id: id, text: String((d["text"] as? String ?? "").prefix(400)),
                          source: String((d["name"] as? String ?? "").prefix(120)), page: p > 0 ? p : nil,
                          contradiction: d["mark"] as? String == "widerspruch", stale: d["flag"] as? String == "veraltet")
    }
}

struct WbPage: Identifiable, Hashable {
    let id: String
    let title: String
    let kind: String
    let count: Int
    let contradictions: Int
}

/// Meine Sachen → Dokumente → Wissensbuch: the pages by kind, what waits for the owner (contradictions and
/// out-of-date sentences), the map (Wissenskarte.swift) and the Obsidian folder, the same as the menu page
/// Wissensbuch in the panel. Only
/// while the admin released it for the profile; the Spark checks every change (iphone.THINGS "wissensbuch").
@MainActor
final class WissensbuchModel: ObservableObject {
    @Published var pages: [WbPage] = []
    @Published var contradictions: [(String, [WbSentence])] = []
    /// out-of-date sentences with the title of their page
    @Published var stale: [(page: String, s: WbSentence)] = []
    @Published var waiting = 0
    @Published var loading = true
    @Published var error: String?

    static let kinds: [(String, LocalizedStringKey)] = [
        ("Thema", LocalizedStringKey("Themen")), ("Person", LocalizedStringKey("Personen")), ("Firma", LocalizedStringKey("Firmen")),
        ("Ding", LocalizedStringKey("Dinge")), ("Ort", LocalizedStringKey("Orte")), ("Antwort", LocalizedStringKey("Abgelegte Antworten")),
    ]

    static func isPage(_ s: String) -> Bool { s.count == 12 && s.allSatisfy { $0.isHexDigit && !$0.isUppercase } }

    func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let d = try await api.object("GET", "api/profile/wissensbuch")
            pages = (d["seiten"] as? [[String: Any]] ?? []).prefix(500).compactMap { p in
                guard let id = p["id"] as? String, Self.isPage(id), (p["n"] as? NSNumber)?.intValue ?? 0 > 0 else { return nil }
                return WbPage(id: id, title: String((p["title"] as? String ?? "").prefix(120)), kind: p["art"] as? String ?? "Thema",
                              count: (p["n"] as? NSNumber)?.intValue ?? 0, contradictions: (p["widerspruch"] as? NSNumber)?.intValue ?? 0)
            }
            contradictions = (d["widersprueche"] as? [[String: Any]] ?? []).prefix(50).map { g in
                (String((g["seite"] as? String ?? "").prefix(120)), (g["werte"] as? [[String: Any]] ?? []).prefix(10).compactMap(WbSentence.from))
            }
            stale = (d["veraltet"] as? [[String: Any]] ?? []).prefix(50).compactMap { s in
                WbSentence.from(s).map { (page: String((s["seite"] as? String ?? "").prefix(120)), s: $0) }
            }
            waiting = (d["wait"] as? NSNumber)?.intValue ?? 0
            error = nil
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    /// "Stimmt nicht" (DELETE), "Stimmt" for one value of a contradiction, "Stimmt noch" for an out-of-date sentence
    func sentence(_ id: Int, _ what: String) async {
        guard let api = SparkAPI.current else { return }
        do {
            switch what {
            case "stimmt", "noch": _ = try await api.object("POST", "api/profile/wissensbuch/satz/\(id)/\(what)")
            default: _ = try await api.object("DELETE", "api/profile/wissensbuch/satz/\(id)")
            }
            error = nil
        } catch { self.error = error.localizedDescription }
        await load()
    }

    /// The whole book as an Obsidian folder (ZIP), written to the app's temporary folder for "Teilen".
    func export() async -> URL? {
        guard let api = SparkAPI.current else { return nil }
        do {
            var r = api.request("api/profile/wissensbuch/export")
            r.timeoutInterval = 120
            let (data, response) = try await URLSession.shared.data(for: r)
            try SparkAPI.check(data, response)
            guard data.count <= 25 * 1024 * 1024 else { throw SparkError(message: String(localized: "Die Datei ist zu groß.")) }
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("Wissensbuch.zip")
            try data.write(to: url, options: [.atomic, .completeFileProtection])
            return url
        } catch { self.error = error.localizedDescription; return nil }
    }
}

struct WissensbuchView: View {
    @StateObject private var m = WissensbuchModel()
    @State private var file: URL?
    @State private var exporting = false

    var body: some View {
        List {
            if m.loading { ProgressView() }
            if Conversation.shared.allowed.areas.contains("wissenskarte") && !m.pages.isEmpty {
                NavigationLink { WissenskarteView() } label: { Label("Karte", systemImage: "point.3.connected.trianglepath.dotted") }
            }
            if !m.contradictions.isEmpty {
                Section {
                    ForEach(Array(m.contradictions.enumerated()), id: \.offset) { _, g in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(verbatim: g.0).font(.subheadline.bold())
                            ForEach(g.1) { s in
                                HStack(alignment: .top) {
                                    WbSentenceText(s: s)
                                    Spacer()
                                    Button("Stimmt") { Task { await m.sentence(s.id, "stimmt") } }.buttonStyle(.bordered)
                                }
                            }
                        }
                    }
                } header: { Text("Widersprüche") } footer: { Text("„Stimmt“ behält diesen Wert, die anderen kommen aus ihren Dokumenten nie wieder.") }
            }
            if !m.stale.isEmpty {
                Section("Veraltet?") {
                    ForEach(m.stale.map { $0.s }) { x in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(verbatim: m.stale.first { $0.s.id == x.id }?.page ?? "").font(.caption).foregroundStyle(.secondary)
                            WbSentenceText(s: x)
                            HStack {
                                Button("Stimmt noch") { Task { await m.sentence(x.id, "noch") } }.buttonStyle(.bordered)
                                Button("Stimmt nicht", role: .destructive) { Task { await m.sentence(x.id, "weg") } }.buttonStyle(.bordered)
                            }
                        }
                    }
                }
            }
            ForEach(WissensbuchModel.kinds, id: \.0) { k in
                let l = m.pages.filter { $0.kind == k.0 }
                if !l.isEmpty {
                    Section {
                        ForEach(l) { p in
                            NavigationLink { WbPageView(page: p, model: m) } label: {
                                LabeledContent {
                                    Text(verbatim: String(p.count))
                                } label: {
                                    Text(verbatim: p.title)
                                    if p.contradictions > 0 { Text("Widerspruch").foregroundStyle(.orange) }
                                }
                            }
                        }
                    } header: { Text(k.1) }
                }
            }
            if !m.loading && m.pages.isEmpty && m.error == nil {
                Text("Noch keine Seiten. Sie entstehen nur, wenn niemand mit dem Spark spricht.").foregroundStyle(.secondary)
            }
            if m.waiting > 0 { Text(verbatim: String(localized: "Noch nicht eingearbeitet:") + " " + String(m.waiting)).foregroundStyle(.secondary) }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if !m.pages.isEmpty {
                Section {
                    if let file {
                        ShareLink(item: file) { Label("Als Obsidian-Ordner teilen", systemImage: "square.and.arrow.up") }
                    } else {
                        Button {
                            exporting = true
                            Task { file = await m.export(); exporting = false }
                        } label: {
                            if exporting { ProgressView() } else { Label("Als Obsidian-Ordner laden", systemImage: "arrow.down.doc") }
                        }
                    }
                } footer: { Text("Eine Notiz je Seite, Links zwischen den Seiten, die Quellen als Fußnoten.") }
            }
        }
        .navigationTitle("Wissensbuch")
        .refreshable { await m.load() }
        .task { await m.load() }
        .onDisappear { if let file { try? FileManager.default.removeItem(at: file) } }
    }
}

/// A sentence and below it its source in small letters (document and page, or "Kiwix: title").
struct WbSentenceText: View {
    let s: WbSentence

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(verbatim: s.text).textSelection(.enabled)
            Text(verbatim: s.page.map { s.source + " · " + String(localized: "S.") + " " + String($0) } ?? s.source)
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// One page with its sentences; "Stimmt nicht" removes a sentence for good from its document.
struct WbPageView: View {
    let page: WbPage
    @ObservedObject var model: WissensbuchModel
    @State private var sentences: [WbSentence] = []
    @State private var error: String?

    var body: some View {
        List {
            ForEach(sentences) { s in
                VStack(alignment: .leading, spacing: 4) {
                    WbSentenceText(s: s)
                    if s.contradiction { Text("Widerspruch").font(.caption).foregroundStyle(.orange) }
                    if s.stale { Text("Veraltet?").font(.caption).foregroundStyle(.orange) }
                }
                .swipeActions(edge: .trailing) {
                    Button(role: .destructive) { Task { await model.sentence(s.id, "weg"); await load() } } label: {
                        Label("Stimmt nicht", systemImage: "xmark")
                    }
                }
            }
            if Conversation.shared.allowed.areas.contains("wissenskarte") {
                NavigationLink { WissenskarteView(around: page.id) } label: { Label("Auf der Karte", systemImage: "point.3.connected.trianglepath.dotted") }
            }
            // renaming a page asks for the code of „Bestätigen“: in the panel (a page with a point: on the map)
            Text(SparkAPI.way(String(localized: "Seite umbenennen geht im Panel unter Wissensbuch → Seiten, eine Seite mit Punkt unter Wissensbuch → Karte.")))
                .font(.caption).foregroundStyle(.secondary)
            if let e = error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
        }
        .navigationTitle(Text(verbatim: page.title))
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        guard let api = SparkAPI.current, WissensbuchModel.isPage(page.id) else { return }
        do {
            let d = try await api.object("GET", "api/profile/wissensbuch/\(page.id)")
            sentences = (d["saetze"] as? [[String: Any]] ?? []).prefix(300).compactMap(WbSentence.from)
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}
