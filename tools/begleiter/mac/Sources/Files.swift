import AppKit

/// Part "files": Finder → Rechtsklick → Dienste → "Mit Spark zusammenfassen / übersetzen / erklären / ins Wissen
/// übernehmen". macOS hands over the file URLs; the files go only to the own Spark (POST /api/desk/file).
extension ServiceProvider {
    @objc(summarizeFiles:userData:error:)
    func summarizeFiles(_ pboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        FileJobs.take(pboard, what: "zusammenfassen", error: error)
    }

    @objc(translateFiles:userData:error:)
    func translateFiles(_ pboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        FileJobs.take(pboard, what: "uebersetzen", error: error)
    }

    @objc(explainFiles:userData:error:)
    func explainFiles(_ pboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        FileJobs.take(pboard, what: "erklaeren", error: error)
    }

    @objc(learnFiles:userData:error:)
    func learnFiles(_ pboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        FileJobs.take(pboard, what: "wissen", error: error)
    }
}

@MainActor
enum FileJobs {
    static let maxFiles = 10
    /// target language for "übersetzen" (the person reads German)
    static let translateTo = "de"

    static func take(_ pboard: NSPasteboard, what: String, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        let model = AppModel.shared
        let urls = (pboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]) ?? []
        guard !urls.isEmpty else {
            error.pointee = "Keine Datei." as NSString
            HUD.show("Erst eine Datei auswählen.")
            return
        }
        guard model.paired else {
            error.pointee = "Nicht gekoppelt." as NSString
            Windows.showPairing()
            return
        }
        guard model.part("files") else {
            error.pointee = "Teil aus." as NSString
            HUD.show(AppModel.offHint("Rechtsklick auf Dateien"))
            return
        }
        // the service returns at once; the work goes on in the background
        Task { await run(Array(urls.prefix(maxFiles)), what: what) }
        if urls.count > maxFiles {
            HUD.show("Nur die ersten \(maxFiles) Dateien.", symbol: "doc.on.doc")
        }
    }

    struct Loaded {
        let name: String
        let type: String
        let data: Data
    }

    /// Reads a file off the main thread; a German reason when it cannot go.
    nonisolated static func load(_ url: URL) -> Result<Loaded, SparkProblem> {
        let name = url.lastPathComponent
        guard let type = FileKinds.mime(for: name) else {
            return .failure(.failed("„\(name)“: Diese Dateiart nimmt der Spark nicht (PDF, Word, Excel, PowerPoint, Text, Bilder …)."))
        }
        let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        guard values?.isRegularFile == true else { return .failure(.failed("„\(name)“ ist keine Datei.")) }
        guard let size = values?.fileSize, size > 0 else { return .failure(.failed("„\(name)“ ist leer.")) }
        guard size <= FileKinds.maxBytes else { return .failure(.failed("„\(name)“ ist größer als 20 MB.")) }
        guard let data = try? Data(contentsOf: url), data.count <= FileKinds.maxBytes else {
            return .failure(.failed("„\(name)“ lässt sich nicht lesen."))
        }
        return .success(Loaded(name: name, type: type, data: data))
    }

    static func run(_ urls: [URL], what: String) async {
        if what == "wissen" {
            await learn(urls)
            return
        }
        for url in urls {
            let loaded = await Task.detached(priority: .userInitiated) { load(url) }.value
            let label = FileKinds.title(what) + ": " + url.lastPathComponent
            await AskController.shared.perform(question: label) { client in
                let f = try loaded.get()
                return try await client.file(f.data, name: f.name, type: f.type, what: what,
                                             sprache: what == "uebersetzen" ? translateTo : nil)
            }
        }
    }

    /// "Ins Wissen übernehmen": no window, a short message at the end.
    private static func learn(_ urls: [URL]) async {
        guard let client = AppModel.shared.client else { return }
        HUD.show("Spark übernimmt \(urls.count == 1 ? "die Datei" : "\(urls.count) Dateien") …", symbol: "tray.and.arrow.down", seconds: 300)
        var ok = 0, already = 0
        var problems: [String] = []
        for url in urls {
            let loaded = await Task.detached(priority: .userInitiated) { load(url) }.value
            switch loaded {
            case .failure(let p):
                problems.append(p.message)
            case .success(let f):
                do {
                    _ = try await client.file(f.data, name: f.name, type: f.type, what: "wissen", sprache: nil)
                    ok += 1
                } catch SparkProblem.conflict {
                    already += 1
                } catch {
                    problems.append(AppModel.shared.absorb(error))
                }
            }
        }
        var parts: [String] = []
        if ok > 0 { parts.append(ok == 1 ? "1 Datei ins Wissen übernommen." : "\(ok) Dateien ins Wissen übernommen.") }
        if already > 0 { parts.append(already == 1 ? "1 Datei war schon im Wissen." : "\(already) Dateien waren schon im Wissen.") }
        if let first = problems.first { parts.append(first) }
        HUD.show(parts.joined(separator: " "), symbol: problems.isEmpty ? "checkmark.circle" : "exclamationmark.triangle",
                 seconds: problems.isEmpty ? 4 : 8)
    }
}
