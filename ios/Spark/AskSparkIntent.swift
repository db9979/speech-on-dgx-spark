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
            throw SparkError(message: "Die App ist noch nicht mit dem Spark gekoppelt.")
        }
        let answer = try await api.ask(question)
        return .result(value: answer, dialog: "\(answer)")
    }
}

struct SparkShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskSparkIntent(),
                    phrases: ["Frag \(.applicationName)", "\(.applicationName) fragen"],
                    shortTitle: "Spark fragen",
                    systemImageName: "waveform")
    }
}
