import AppIntents
import UniformTypeIdentifiers

/// "Hey Siri, Frag Spark": Siri asks for the question, the Spark answers, Siri reads it out.
/// Works without opening the app, also on the lock screen, with AirPods and through Siri in the car.
struct AskSparkIntent: AppIntent {
    static var title: LocalizedStringResource = "Spark fragen"
    static var description = IntentDescription("Stellt dem Spark eine Frage und liest die Antwort vor.")
    static var openAppWhenRun = false

    @Parameter(title: "Frage", requestValueDialog: IntentDialog("Was möchtest du wissen?"))
    var question: String

    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        let answer = try await api.ask(question)
        return .result(value: answer, dialog: "\(answer)")
    }
}

/// Quick start: opens the app and it listens at once. For the Action button (Settings → Action Button →
/// Shortcut → Spark), the lock screen and "Hey Siri, Spark zuhören".
struct StartListeningIntent: AppIntent {
    static var title: LocalizedStringResource = "Spark zuhören"
    static var description = IntentDescription("Öffnet die App und hört sofort zu.")
    static var openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        Conversation.shared.listenNow()
        return .result()
    }
}

enum SparkList: String, AppEnum {
    case einkauf, aufgaben
    static var typeDisplayRepresentation: TypeDisplayRepresentation = "Liste"
    static var caseDisplayRepresentations: [SparkList: DisplayRepresentation] = [
        .einkauf: "Einkaufsliste", .aufgaben: "Aufgaben"]
}

/// Shortcuts: puts entries on the Spark's shopping or to-do list (profile switch "Apple Erinnerungen").
struct AddToListIntent: AppIntent {
    static var title: LocalizedStringResource = "Auf die Liste beim Spark"
    static var description = IntentDescription("Setzt etwas auf die Einkaufsliste oder die Aufgaben des Spark. Mehreres mit Komma trennen.")

    @Parameter(title: "Liste", default: .einkauf)
    var list: SparkList

    @Parameter(title: "Was", requestValueDialog: IntentDialog("Was soll auf die Liste?"))
    var text: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        try await api.addToList(list.rawValue, text)
        return .result(dialog: "Steht drauf.")
    }
}

/// Shortcuts: a reminder at the Spark ("morgen um 8 an den Müll").
struct RemindIntent: AppIntent {
    static var title: LocalizedStringResource = "Erinnerung beim Spark"
    static var description = IntentDescription("Der Spark erinnert dich, mit Push und auf allen Geräten.")

    @Parameter(title: "Woran und wann", requestValueDialog: IntentDialog("Woran soll ich dich wann erinnern?"))
    var text: String

    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        let answer = try await api.ask(String(localized: "Erinnere mich \(text)"))
        return .result(value: answer, dialog: "\(answer)")
    }
}

/// Shortcuts: a file into "Meine Dokumente" (profile switch "Dokumente aus der App ablegen").
/// The iPhone reads the text itself, as in the app.
struct StoreDocumentIntent: AppIntent {
    static var title: LocalizedStringResource = "Dokument beim Spark ablegen"
    static var description = IntentDescription("Liest den Text einer Datei auf dem iPhone und legt ihn unter „Meine Dokumente“ ab.")

    @Parameter(title: "Datei")
    var file: IntentFile

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        let name = file.filename.isEmpty ? "Dokument" : file.filename
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let url = dir.appendingPathComponent((name as NSString).lastPathComponent)
        try file.data.write(to: url)
        let a = try await Reader.file(url)
        try await api.storeDoc(name: a.name, text: a.text)
        return .result(dialog: "Abgelegt.")
    }
}

struct SparkShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskSparkIntent(),
                    phrases: ["Frag \(.applicationName)", "\(.applicationName) fragen"],
                    shortTitle: "Spark fragen",
                    systemImageName: "questionmark.bubble")
        AppShortcut(intent: AddToListIntent(),
                    phrases: ["Mit \(.applicationName) auf die Liste", "\(.applicationName) Einkaufsliste"],
                    shortTitle: "Auf die Liste",
                    systemImageName: "cart")
        AppShortcut(intent: StartListeningIntent(),
                    phrases: ["\(.applicationName) zuhören", "Mit \(.applicationName) sprechen"],
                    shortTitle: "Spark zuhören",
                    systemImageName: "waveform")
    }
}
