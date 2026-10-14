import QuickLook
import SwiftUI

/// "Meine Dokumente": the profile's documents on the Spark, to look at again (only with the profile's
/// switch "Dokumente aus der App"). A kept PDF or picture opens in Apple's viewer; otherwise, and always
/// as a second tab, the text the Spark stored. With "Dokumente verwalten in der App" (app_docs_edit) also
/// delete, "Für alle", searchable, tags, read again and a deadline reminder; the Spark checks each of them.
@MainActor
final class DocumentsModel: ObservableObject {
    @Published var docs: [SparkDoc] = []
    @Published var loading = true
    @Published var off = false
    @Published var error: String?
    @Published var note: String?

    /// one change to a document, then the list again
    func change(_ d: SparkDoc, _ what: @escaping (SparkAPI) async throws -> String?) async {
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
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }
}

struct DocumentsView: View {
    var manage = false
    @StateObject private var m = DocumentsModel()
    @State private var search = ""
    @State private var removing: SparkDoc?
    @State private var tagging: SparkDoc?
    @State private var tagText = ""

    private var shown: [SparkDoc] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? m.docs : m.docs.filter { $0.name.lowercased().contains(q) }
    }

    var body: some View {
        List {
            if m.loading {
                ProgressView()
            } else if m.off {
                Text(SparkAPI.way(String(localized: "Dafür im Panel unter Ich → iPhone-App „Dokumente aus der App“ einschalten.")))
            } else if m.docs.isEmpty {
                Text("Noch keine Dokumente.").foregroundStyle(.secondary)
            }
            ForEach(shown) { d in
                NavigationLink { DocumentView(doc: d) } label: {
                    HStack {
                        Image(systemName: d.kind == "picture" ? "photo" : d.kind == "scan" ? "doc.viewfinder" : "doc.text")
                            .foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: d.name).lineLimit(2)
                            HStack(spacing: 6) {
                                Text(d.created, format: .dateTime.day().month().year())
                                if d.pages > 1 { Text("\(d.pages) Seiten") }
                                if d.state == "reading" && d.pages > 0 { Text("Seite \(d.pages - d.todo) von \(d.pages) gelesen") }
                                else if d.state != "ready" || d.todo > 0 { Text("wird noch gelesen") }
                            }
                            .font(.caption).foregroundStyle(.secondary)
                            if d.source == "nas" {      // from a knowledge folder: where it lies on the NAS (the folder, never more)
                                Label { Text(verbatim: "NAS · " + (d.place.isEmpty ? "/" : d.place)) } icon: { Image(systemName: "externaldrive") }
                                    .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                            }
                            if manage { badges(d) }
                        }
                    }
                }
                .swipeActions(edge: .trailing) {
                    if manage { Button(role: .destructive) { removing = d } label: { Label("Löschen", systemImage: "trash") } }
                }
                .contextMenu { if manage { menu(d) } }
            }
            if let e = m.error { Text(SparkAPI.way(e)).foregroundStyle(.red) }
            if let n = m.note { Text(verbatim: n).foregroundStyle(.secondary) }
            if manage && !m.off {
                Section {
                    NavigationLink("Schalter für Dokumente") { DocSwitchesView() }
                } footer: { Text("Lange drücken für „Für alle“, Tags, Neu einlesen und Frist-Erinnerung. Wischen zum Löschen.") }
            }
        }
        .navigationTitle("Meine Dokumente")
        .searchable(text: $search)
        .refreshable { await m.load() }
        .task { await m.load() }
        .confirmationDialog("Dokument löschen?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
                            titleVisibility: .visible, presenting: removing) { d in
            Button("Löschen", role: .destructive) {
                Task { await m.change(d) { try await $0.deleteDoc(d.id); return nil } }
            }
        } message: { d in Text(verbatim: d.name) }
        .alert("Tags", isPresented: Binding(get: { tagging != nil }, set: { if !$0 { tagging = nil } })) {
            TextField("Rechnung, Auto, Steuer", text: $tagText)
            Button("Speichern") {
                guard let d = tagging else { return }
                let tags = tagText.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
                Task { await m.change(d) { try await $0.setDoc(d.id, ["tags": Array(tags.prefix(12))]); return nil } }
            }
            Button("Automatische Tags") {
                guard let d = tagging else { return }
                Task { await m.change(d) { try await $0.setDoc(d.id, ["tags": NSNull()]); return nil } }
            }
            Button("Abbrechen", role: .cancel) {}
        } message: { Text("Mit Komma getrennt. Geht nur, wenn „Steckbrief und Tags“ an ist.") }
    }

    @ViewBuilder private func badges(_ d: SparkDoc) -> some View {
        HStack(spacing: 6) {
            if d.shared { Label("Für alle", systemImage: "person.2").labelStyle(.titleAndIcon) }
            if !d.use { Text("wird nicht durchsucht") }
            if !d.due.isEmpty { Label(d.due, systemImage: "calendar.badge.exclamationmark") }
        }
        .font(.caption2).foregroundStyle(.secondary)
        if !d.tags.isEmpty {
            Text(verbatim: d.tags.map { "#" + $0 }.joined(separator: " ")).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
        }
    }

    @ViewBuilder private func menu(_ d: SparkDoc) -> some View {
        Button {
            Task { await m.change(d) { try await $0.setDoc(d.id, ["shared": !d.shared]); return nil } }
        } label: { d.shared ? Label("Nur für mich", systemImage: "person") : Label("Für alle freigeben", systemImage: "person.2") }
        Button {
            Task { await m.change(d) { try await $0.setDoc(d.id, ["use": !d.use]); return nil } }
        } label: { d.use ? Label("Nicht mehr durchsuchen", systemImage: "eye.slash") : Label("Wieder durchsuchen", systemImage: "eye") }
        Button {
            tagText = d.tags.joined(separator: ", ")
            tagging = d
        } label: { Label("Tags bearbeiten", systemImage: "tag") }
        if d.file {
            Button {
                Task { await m.change(d) { _ = try await $0.docAction(d.id, "reread"); return String(localized: "Wird neu eingelesen.") } }
            } label: { Label("Neu einlesen", systemImage: "arrow.clockwise") }
        }
        if !d.due.isEmpty {
            Button {
                Task {
                    await m.change(d) { api in
                        let r = try await api.docAction(d.id, "remind")
                        let when = Date(timeIntervalSince1970: ((r["due"] as? NSNumber)?.doubleValue ?? 0) / 1000)
                        return String(localized: "Erinnerung am \(when.formatted(date: .abbreviated, time: .shortened)).")
                    }
                }
            } label: { Label("An die Frist erinnern", systemImage: "bell") }
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
