import AppKit

/// Part "office" on the Mac: Word and Excel get the Spark's Office add-in (its manifest into their "wef" folder),
/// Outlook for Mac gets the file shown plus Microsoft's page "Aus Datei hinzufügen" (Microsoft lets only the person
/// add it there). Outlook classic is Windows only. Part off: the files go again.
@MainActor
enum OfficeSetup {
    /// app in the Spark (/api/desk/office/<app>.xml) -> the Office app's container on this Mac
    static let webApps: [(app: String, bundle: String)] = [("word", "com.microsoft.Word"), ("excel", "com.microsoft.Excel")]
    static let sideloadPage = URL(string: "https://aka.ms/olksideload")!
    static let maxBytes = 64 * 1024

    static func wefFolder(_ bundle: String) -> URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Containers/\(bundle)/Data/Documents/wef", isDirectory: true)
    }

    static var ownFolder: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("SparkBegleiter/Office", isDirectory: true)
    }

    /// whether the Office app is installed on this Mac (its container exists)
    static func installed(_ bundle: String) -> Bool {
        FileManager.default.fileExists(atPath: wefFolder(bundle).deletingLastPathComponent().path)
    }

    static func anySetUp() -> Bool {
        webApps.contains { FileManager.default.fileExists(atPath: wefFolder($0.bundle).appendingPathComponent("spark-\($0.app).xml").path) }
    }

    /// Part off: take the files out again.
    static func apply(on: Bool) {
        guard !on, anySetUp() else { return }
        for w in webApps {
            try? FileManager.default.removeItem(at: wefFolder(w.bundle).appendingPathComponent("spark-\(w.app).xml"))
        }
        HUD.show("Die Office-Knöpfe des Spark sind ausgetragen (wirkt beim nächsten Start von Word und Excel).")
    }

    /// Menu "Office-Add-ins einrichten …": asks first, then Word and Excel, then on request Outlook.
    static func start(model: AppModel) {
        guard model.part("office"), let client = model.client else {
            HUD.show(AppModel.offHint("Office-Add-ins"))
            return
        }
        guard model.config?.officeWeb == true else {
            HUD.show("Dafür das Panel einmal über seine https-Adresse öffnen, unter Ich → Begleiter speichern und "
                     + "„In anderen Programmen“ der Schreibhilfe einschalten.")
            return
        }
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Office-Add-ins einrichten?"
        a.informativeText = """
            Word und Excel bekommen den Knopf „Spark Schreibhilfe“. Er wirkt beim nächsten Start der Programme. \
            Gesendet wird nie etwas.
            """
        a.addButton(withTitle: "Einrichten")
        a.addButton(withTitle: "Abbrechen")
        guard a.runModal() == .alertFirstButtonReturn else { return }
        Task { @MainActor in
            var done: [String] = []
            do {
                for w in webApps where installed(w.bundle) {
                    let dir = wefFolder(w.bundle)
                    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                    try await client.download("api/desk/office/\(w.app).xml", to: dir.appendingPathComponent("spark-\(w.app).xml"),
                                              maxBytes: maxBytes)
                    done.append(w.app == "word" ? "Word" : "Excel")
                }
                if askOutlook() {
                    try FileManager.default.createDirectory(at: ownFolder, withIntermediateDirectories: true)
                    let file = ownFolder.appendingPathComponent("spark-outlook.xml")
                    try await client.download("api/desk/office/outlook.xml", to: file, maxBytes: maxBytes)
                    NSWorkspace.shared.activateFileViewerSelecting([file])
                    NSWorkspace.shared.open(sideloadPage)
                    done.append("Outlook (Datei bereit)")
                }
                HUD.show(done.isEmpty ? "Word und Excel sind auf diesem Mac nicht installiert."
                         : "Eingerichtet: \(done.joined(separator: ", ")). Bitte die Programme neu starten.")
            } catch {
                HUD.show((done.isEmpty ? "" : "Eingerichtet: \(done.joined(separator: ", ")). ") + error.localizedDescription)
            }
        }
    }

    private static func askOutlook() -> Bool {
        let a = NSAlert()
        a.messageText = "Auch in Outlook?"
        a.informativeText = """
            Microsoft lässt das nur von dir selbst hinzufügen: Es öffnet sich eine Seite, dort „Aus Datei hinzufügen“ \
            wählen und die gezeigte Datei „spark-outlook.xml“ nehmen. Das gilt für dein Postfach (Microsoft 365, \
            Exchange oder Outlook.com, nicht iCloud oder IMAP).
            """
        a.addButton(withTitle: "Ja")
        a.addButton(withTitle: "Nein")
        return a.runModal() == .alertFirstButtonReturn
    }
}
