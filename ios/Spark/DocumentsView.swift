import QuickLook
import SwiftUI

/// "Meine Dokumente": the profile's documents on the Spark, to look at again (only with the profile's
/// switch "Dokumente aus der App"). A kept PDF or picture opens in Apple's viewer; otherwise, and always
/// as a second tab, the text the Spark stored. Looking only: nothing is changed or deleted from here.
@MainActor
final class DocumentsModel: ObservableObject {
    @Published var docs: [SparkDoc] = []
    @Published var loading = true
    @Published var off = false
    @Published var error: String?

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
    @StateObject private var m = DocumentsModel()
    @State private var search = ""

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
                                if d.state != "ready" || d.todo > 0 { Text("wird noch gelesen") }
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if let e = m.error { Text(verbatim: e).foregroundStyle(.red) }
        }
        .navigationTitle("Meine Dokumente")
        .searchable(text: $search)
        .refreshable { await m.load() }
        .task { await m.load() }
    }
}

struct DocumentView: View {
    let doc: SparkDoc
    @State private var original: URL?
    @State private var text: DocText?
    @State private var tab = 0
    @State private var loading = true
    @State private var error: String?

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
                    if t.cut { Text("Gekürzt. Das ganze Dokument steht im Panel.").font(.footnote).foregroundStyle(.secondary) }
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
