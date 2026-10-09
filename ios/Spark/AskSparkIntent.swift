import AppIntents

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

struct SparkShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskSparkIntent(),
                    phrases: ["Frag \(.applicationName)", "\(.applicationName) fragen"],
                    shortTitle: "Spark fragen",
                    systemImageName: "questionmark.bubble")
        AppShortcut(intent: StartListeningIntent(),
                    phrases: ["\(.applicationName) zuhören", "Mit \(.applicationName) sprechen"],
                    shortTitle: "Spark zuhören",
                    systemImageName: "waveform")
    }
}
