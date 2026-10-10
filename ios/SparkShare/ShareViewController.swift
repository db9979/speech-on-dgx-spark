import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// "Teilen → Spark" from any app: a text, a web page, a PDF or a photo. The iPhone reads the text
/// (a web page is fetched here, like Safari would), then you ask about it or store it under
/// "Meine Dokumente". The Spark gets only text and treats it as outside text (actions stay locked).
final class ShareViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        let model = ShareModel(items: extensionContext?.inputItems as? [NSExtensionItem] ?? []) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
        let host = UIHostingController(rootView: ShareView(m: model))
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
    }
}

@MainActor
final class ShareModel: ObservableObject {
    static let pageBytes = 3 * 1024 * 1024

    @Published var attachment: Attachment?
    @Published var question = String(localized: "Fass das kurz zusammen.")
    @Published var answer = ""
    @Published var busy = true
    @Published var asking = false
    @Published var error: String?
    @Published var notice: String?
    @Published var docs = false
    /// "Text verbessern" for shared text: nil hidden (no plain text, or the Spark does not know it), false off in the panel
    @Published var write: Bool?
    @Published var art = WriteArt.korrigieren
    @Published var writing = false
    @Published var improved: WriteResult?
    @Published var result = ""
    private var plain = false
    let done: () -> Void
    private let items: [NSExtensionItem]

    init(items: [NSExtensionItem], done: @escaping () -> Void) {
        self.items = items
        self.done = done
        Task { await load() }
    }

    private func load() async {
        defer { busy = false }
        guard let api = SparkAPI.current else {
            error = String(localized: "Erst die Spark-App öffnen und koppeln.")
            return
        }
        let allowed = try? await api.hello(timeout: 10)
        docs = allowed?.docs ?? false
        Reader.sendPictures = allowed?.images ?? false
        do {
            attachment = try await read()
            if attachment == nil { error = String(localized: "Damit kann der Spark nichts anfangen.") }
            if plain { write = try? await api.writeOn() }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func read() async throws -> Attachment? {
        let providers = items.flatMap { $0.attachments ?? [] }
        func has(_ t: UTType) -> NSItemProvider? { providers.first { $0.hasItemConformingToTypeIdentifier(t.identifier) } }
        if let p = has(.pdf) ?? has(.image) ?? has(.fileURL) {
            let type = [UTType.pdf, .image, .fileURL].first { p.hasItemConformingToTypeIdentifier($0.identifier) }!
            let item = try await p.loadItem(forTypeIdentifier: type.identifier, options: nil)
            if let url = item as? URL { return try await Reader.file(url) }
            if let image = item as? UIImage { return try await Reader.photo(image, name: String(localized: "Foto")) }
            if let data = item as? Data, let image = UIImage(data: data) { return try await Reader.photo(image, name: String(localized: "Foto")) }
        }
        if let p = has(.url), let url = try await p.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) as? URL,
           url.scheme == "https" || url.scheme == "http" {
            return try await page(url)
        }
        if let p = has(.plainText) ?? has(.text), let text = try await p.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) as? String {
            let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
            plain = !t.isEmpty
            return t.isEmpty ? nil : Attachment(kind: "document", name: String(localized: "Text"), text: String(t.prefix(Reader.maxChars)))
        }
        return nil
    }

    /// The page's text, fetched here on the iPhone (at most 3 MB, scripts and styles left out).
    private func page(_ url: URL) async throws -> Attachment {
        var r = URLRequest(url: url)
        r.timeoutInterval = 20
        let (bytes, response) = try await URLSession.shared.bytes(for: r)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw SparkError(message: String(localized: "Die Seite antwortet nicht."))
        }
        var data = Data()
        for try await b in bytes {
            data.append(b)
            if data.count > Self.pageBytes { break }
        }
        let html = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) ?? ""
        var t = html.replacingOccurrences(of: "(?is)<(script|style|noscript)[^>]*>.*?</\\1>", with: " ", options: .regularExpression)
        t = t.replacingOccurrences(of: "(?i)<br\\s*/?>|</(p|div|h\\d|li|tr)>", with: "\n", options: .regularExpression)
        t = t.replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
        for (a, b) in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", "\""), ("&#39;", "'")] {
            t = t.replacingOccurrences(of: a, with: b)
        }
        t = t.replacingOccurrences(of: "[ \\t]+", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\n\\s*\\n+", with: "\n\n", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { throw SparkError(message: String(localized: "Auf der Seite habe ich keinen Text gefunden.")) }
        return Attachment(kind: "document", name: url.host ?? url.absoluteString, text: String(t.prefix(Reader.maxChars)))
    }

    func ask() {
        guard let a = attachment, let api = SparkAPI.current, !asking else { return }
        let q = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }
        asking = true
        answer = ""
        error = nil
        Task {
            do {
                for try await ev in api.chat([["role": "user", "content": q]], attachment: a, speak: false) {
                    switch ev {
                    case .text(let t): answer += t
                    case .drop(let n): answer = String(answer.dropLast(n))
                    case .error(let e): error = e
                    default: break
                    }
                }
            } catch {
                self.error = error.localizedDescription
            }
            asking = false
        }
    }

    /// The shared text through the Spark's writing help; the result can be edited and copied.
    func improve() {
        guard let a = attachment, let api = SparkAPI.current, !asking else { return }
        asking = true
        writing = true
        improved = nil
        error = nil
        let art = self.art
        Task {
            do {
                let r = try await api.improve(a.text, art: art)
                improved = r
                result = r.text
            } catch {
                self.error = error.localizedDescription
            }
            writing = false
            asking = false
        }
    }

    func store() {
        guard let a = attachment, let api = SparkAPI.current, !asking else { return }
        asking = true
        Task {
            do {
                try await api.storeDoc(name: a.name, text: a.text)
                notice = String(localized: "Unter „Meine Dokumente“ gespeichert. Der Spark findet es auch später.")
            } catch {
                self.error = error.localizedDescription
            }
            asking = false
        }
    }
}

struct ShareView: View {
    @ObservedObject var m: ShareModel

    var body: some View {
        NavigationStack {
            Form {
                if m.busy {
                    ProgressView("Lese den Text …")
                }
                if let a = m.attachment {
                    Section {
                        Label { Text(verbatim: a.name).lineLimit(1) } icon: { Image(systemName: a.kind == "photo" ? "photo" : "doc.text") }
                        if a.image != nil {
                            Text("Der Spark sieht sich das Foto an.").foregroundStyle(.secondary)
                        } else {
                            Text("\(a.text.count) Zeichen").foregroundStyle(.secondary)
                        }
                    }
                    Section("Frage") {
                        TextField("Frage", text: $m.question, axis: .vertical)
                        Button("Fragen") { m.ask() }.disabled(m.asking)
                        if m.docs && a.image == nil {
                            Button("In „Meine Dokumente“ speichern") { m.store() }.disabled(m.asking)
                        }
                    }
                }
                if let w = m.write, m.attachment != nil {
                    Section("Text verbessern") {
                        if w {
                            Picker("Art", selection: $m.art) {
                                ForEach(WriteArt.allCases) { Text(verbatim: $0.label).tag($0) }
                            }
                            Button("Text verbessern") { m.improve() }.disabled(m.asking)
                        } else {
                            Text(verbatim: SparkAPI.writeOff).foregroundStyle(.secondary)
                        }
                    }
                }
                if m.writing { ProgressView("Der Spark schreibt …") }
                if let r = m.improved {
                    Section("Verbessert") {
                        if let diff = r.diff {
                            Text(Self.marked(diff)).textSelection(.enabled)
                        }
                        TextField("Verbessert", text: $m.result, axis: .vertical)
                        Button { UIPasteboard.general.string = m.result } label: { Label("Kopieren", systemImage: "doc.on.doc") }
                    }
                }
                if m.asking && !m.writing && m.answer.isEmpty { ProgressView() }
                if !m.answer.isEmpty {
                    Section("Antwort") {
                        Text(verbatim: m.answer).textSelection(.enabled)
                        ShareLink(item: m.answer) { Label("Teilen (z. B. als Notiz)", systemImage: "square.and.arrow.up") }
                        Button { UIPasteboard.general.string = m.answer } label: { Label("Kopieren", systemImage: "doc.on.doc") }
                    }
                }
                if let n = m.notice { Section { Text(verbatim: n) } }
                if let e = m.error { Section { Text(verbatim: e).foregroundStyle(.red) } }
            }
            .navigationTitle("An Spark")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { m.done() } } }
        }
    }

    /// The changes: removed words red and struck through, added ones green.
    static func marked(_ diff: [(op: String, text: String)]) -> AttributedString {
        var out = AttributedString()
        for (op, text) in diff {
            var piece = AttributedString(text)
            if op == "-" {
                piece[AttributeScopes.SwiftUIAttributes.ForegroundColorAttribute.self] = Color.red
                piece[AttributeScopes.SwiftUIAttributes.StrikethroughStyleAttribute.self] = Text.LineStyle.single
            } else if op == "+" {
                piece[AttributeScopes.SwiftUIAttributes.ForegroundColorAttribute.self] = Color.green
            }
            out += piece
        }
        return out
    }
}
