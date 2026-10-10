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
                Text("Dafür im Panel unter Ich → iPhone-App „Dokumente aus der App“ einschalten.")
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
                            if manage { badges(d) }
                        }
                    }
                }
                .swipeActions(edge: .trailing) {
                    if manage { Button(role: .destructive) { removing = d } label: { Label("Löschen", systemImage: "trash") } }
                }
                .contextMenu { if manage { menu(d) } }
            }
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
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

/// The switches under Ich → Dokumente (each also needs the admin's switch; the Spark says which).
struct DocSwitchesView: View {
    @State private var on: [String: Bool] = [:]
    @State private var allow: [String: Bool] = [:]
    @State private var error: String?

    static let rows: [(String, String, LocalizedStringKey, LocalizedStringKey)] = [
        ("doc_pictures", "pictures", LocalizedStringKey("Bilder und Scans lesen"), LocalizedStringKey("Das Sprachmodell liest Fotos und gescannte Seiten, wenn der Spark Zeit hat.")),
        ("doc_semantic", "semantic", LocalizedStringKey("Nach Bedeutung suchen"), LocalizedStringKey("Findet auch Stellen mit anderen Worten.")),
        ("doc_originals", "originals", LocalizedStringKey("Originale aufheben"), LocalizedStringKey("Die Datei selbst bleibt auf dem Spark, zum Ansehen und Neu einlesen.")),
        ("doc_shared", "shared", LocalizedStringKey("Gemeinsame Dokumente"), LocalizedStringKey("Du darfst Dokumente für alle freigeben und siehst die der anderen.")),
        ("doc_brief", "brief", LocalizedStringKey("Steckbrief und Tags"), LocalizedStringKey("Titel, Absender, Datum, Frist und Tags zu jedem Dokument.")),
        ("doc_due", "brief", LocalizedStringKey("Fristen"), LocalizedStringKey("Erinnerung vor einer Frist, erst nach deinem Tippen.")),
    ]

    var body: some View {
        Form {
            ForEach(Self.rows, id: \.0) { r in
                if allow[r.1] ?? false {
                    Section {
                        Toggle(r.2, isOn: Binding(get: { on[r.0] ?? false }, set: { v in on[r.0] = v; Task { await save(r.0, v) } }))
                    } footer: { Text(r.3) }
                }
            }
            if allow.values.allSatisfy({ !$0 }) && !allow.isEmpty {
                Text("Der Admin hat keine dieser Funktionen eingeschaltet.").foregroundStyle(.secondary)
            }
            if let e = error { Text(verbatim: e).foregroundStyle(.red) }
        }
        .navigationTitle("Schalter für Dokumente")
        .task { await load() }
    }

    private func load() async {
        guard let api = SparkAPI.current else { return }
        do {
            let w = try await api.object("GET", "api/profile/wissen")
            allow = (w["allow"] as? [String: Bool]) ?? [:]
            let s = try await api.object("GET", "api/iphone/settings")
            on = ((s["settings"] as? [String: Any]) ?? [:]).compactMapValues { $0 as? Bool }
        } catch { self.error = error.localizedDescription }
    }

    private func save(_ key: String, _ value: Bool) async {
        do {
            _ = try await SparkAPI.current?.call("PUT", "api/iphone/settings", body: [key: value])
            error = nil
        } catch {
            self.error = error.localizedDescription
            on[key] = !value
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
                if let e = error { Text(verbatim: e).foregroundStyle(.red) }
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
        if doc.file { original = try? await api.docOriginal(doc.id) }
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
