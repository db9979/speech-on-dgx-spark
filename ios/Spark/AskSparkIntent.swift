import AppIntents
import SwiftUI
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
    static var description = IntentDescription("Liest den Text einer Datei und legt ihn unter „Meine Dokumente“ ab.")

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
        let a = try await Reader.file(url, picture: false)   // "Meine Dokumente" keeps text
        try await api.storeDoc(name: a.name, text: a.text)
        return .result(dialog: "Abgelegt.")
    }
}

/// "Nachricht an …": a chat message to someone of this Spark, without the language model. The name must match
/// one of the profiles that take messages from you (the Spark's contacts); before sending Siri asks once more.
/// It lands in the 1:1 chat (opened when there is none yet), "alle" in the fixed group "Alle".
struct SendMessageIntent: AppIntent {
    static var title: LocalizedStringResource = "Nachricht über den Spark"
    static var description = IntentDescription("Schickt jemandem dieses Sparks eine kurze Nachricht.")
    static var openAppWhenRun = false

    @Parameter(title: "An", requestValueDialog: IntentDialog("An wen?"))
    var recipient: String

    @Parameter(title: "Nachricht", requestValueDialog: IntentDialog("Was soll ich schreiben?"))
    var text: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        let s = try await api.chats()
        guard s.enabled else { throw SparkError(message: String(localized: "Chats sind auf dem Spark ausgeschaltet.")) }
        guard s.on else { throw SparkError(message: String(localized: "Chats sind für dein Profil aus.")) }
        let to = try await Self.resolve(recipient, list: s.contacts, all: s.all, ask: { names in
            try await $recipient.requestDisambiguation(among: names, dialog: IntentDialog("Wen meinst du?"))
        })
        let t = String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(s.maxText))
        guard !t.isEmpty else { throw SparkError(message: String(localized: "Die Nachricht ist leer.")) }
        try await requestConfirmation(result: .result(dialog: "Nachricht an \(to.name): „\(t)“. Senden?"))
        if to.id == "all" {
            guard let c = s.chats.first(where: { $0.fixed }) else {
                throw SparkError(message: String(localized: "Gerade nimmt niemand Nachrichten an alle an."))
            }
            try await api.chatSend(c.id, text: t)
        } else {
            try await api.chatSend(try await api.chatOpen(to: to.id), text: t)
        }
        return .result(dialog: "Gesendet.")
    }

    /// The recipient from the spoken name. Several fit (two "Thomas"): Siri asks which one among at most
    /// four, and the answer must be one of them. Never a list of every name: at most three similar ones.
    static func resolve(_ said: String, list: [Recipient], all: Bool, ask: ([String]) async throws -> String) async throws -> Recipient {
        switch match(said, list, all: all) {
        case .one(let r):
            return r
        case .several(let list):
            let chosen = try await ask(list.map(\.label))
            guard let r = list.first(where: { $0.label == chosen }) else {
                throw SparkError(message: String(localized: "Nicht gesendet: nicht klar, wen du meinst."))
            }
            return r
        case .tooMany(let n):
            throw SparkError(message: String(localized: "Zu viele passen (\(n)). Sag den ganzen Namen oder den Rufnamen."))
        case .none:
            guard !list.isEmpty else { throw SparkError(message: String(localized: "Gerade nimmt niemand Nachrichten von dir an.")) }
            let near = similar(said, list)
            throw SparkError(message: near.isEmpty
                ? String(localized: "Den Namen finde ich nicht.")
                : String(localized: "Den Namen finde ich nicht. Ähnlich: \(near.joined(separator: ", "))."))
        }
    }

    enum Match: Equatable {
        case one(Recipient), several([Recipient]), tooMany(Int), none
    }

    static let maxChoice = 4

    /// Fixed rules, no model (as on the Spark): the name or the Rufname (any case), else the first or the
    /// last name, else the only one starting with it; "alle" when allowed. Several fit: ask, never guess.
    static func match(_ said: String, _ list: [Recipient], all: Bool) -> Match {
        let s = said.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !s.isEmpty else { return .none }
        if all && ["alle", "allen", "all", "everyone", "everybody"].contains(s) {
            return .one(Recipient(id: "all", name: String(localized: "Alle")))
        }
        let keys: (Recipient) -> [String] = { r in [r.name.lowercased(), r.call.lowercased()].filter { !$0.isEmpty } }
        let tests: [(String) -> Bool] = [
            { $0 == s },
            { $0.split(separator: " ").first.map(String.init) == s },
            { $0.split(separator: " ").last.map(String.init) == s },
            { $0.hasPrefix(s) },
        ]
        for test in tests {
            let hits = list.filter { keys($0).contains(where: test) }
            if hits.count == 1 { return .one(hits[0]) }
            if hits.count > maxChoice { return .tooMany(hits.count) }
            if hits.count > 1 { return .several(hits) }
        }
        return .none
    }

    /// At most three names that share the first letters with what was said.
    static func similar(_ said: String, _ list: [Recipient]) -> [String] {
        let s = String(said.trimmingCharacters(in: .whitespacesAndNewlines).lowercased().prefix(3))
        guard s.count >= 2 else { return [] }
        return Array(list.filter { r in
            [r.name, r.call].contains { $0.lowercased().split(separator: " ").contains { $0.hasPrefix(s) } }
        }.map(\.name).prefix(3))
    }
}

enum SparkWriteArt: String, AppEnum {
    case korrigieren, glaetten, kuerzer, freundlicher, foermlicher, englisch, deutsch
    static var typeDisplayRepresentation: TypeDisplayRepresentation = "Art"
    static var caseDisplayRepresentations: [SparkWriteArt: DisplayRepresentation] = [
        .korrigieren: "Korrigieren", .glaetten: "Glätten", .kuerzer: "Kürzer", .freundlicher: "Freundlicher",
        .foermlicher: "Förmlicher", .englisch: "Ins Englische", .deutsch: "Ins Deutsche"]
}

/// Shortcuts, Siri and the share sheet: the Spark's writing help (admin and profile switches "Schreibhilfe")
/// improves a text and gives it back, e.g. for the clipboard. Works without opening the app.
struct ImproveTextIntent: AppIntent {
    static var title: LocalizedStringResource = "Text mit Spark verbessern"
    static var description = IntentDescription("Der Spark korrigiert, glättet, kürzt oder übersetzt einen Text und gibt ihn zurück.")
    static var openAppWhenRun = false

    @Parameter(title: "Text", requestValueDialog: IntentDialog("Welchen Text soll ich verbessern?"))
    var text: String

    @Parameter(title: "Art", default: .korrigieren)
    var art: SparkWriteArt

    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog & ShowsSnippetView {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        let r = try await api.improve(text, art: WriteArt(rawValue: art.rawValue) ?? .korrigieren)
        let dialog: IntentDialog
        if let n = r.changes, n > 0 {
            dialog = "Geändert: \(n)"
        } else if r.changes == 0 {
            dialog = "Der Text war schon gut."
        } else {
            dialog = "Fertig."
        }
        return .result(value: r.text, dialog: dialog, view: Text(verbatim: r.text).lineLimit(12).padding())
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
        AppShortcut(intent: SendMessageIntent(),
                    phrases: ["Nachricht mit \(.applicationName)", "\(.applicationName) Nachricht schreiben"],
                    shortTitle: "Nachricht",
                    systemImageName: "envelope")
        AppShortcut(intent: ImproveTextIntent(),
                    phrases: ["Text mit \(.applicationName) verbessern", "\(.applicationName) Text verbessern"],
                    shortTitle: "Text verbessern",
                    systemImageName: "text.badge.checkmark")
        AppShortcut(intent: StartListeningIntent(),
                    phrases: ["\(.applicationName) zuhören", "Mit \(.applicationName) sprechen"],
                    shortTitle: "Spark zuhören",
                    systemImageName: "waveform")
        AppShortcut(intent: NotausIntent(),
                    phrases: ["\(.applicationName) Notaus", "Notaus mit \(.applicationName)"],
                    shortTitle: "Spark Notaus",
                    systemImageName: "exclamationmark.octagon")
        AppShortcut(intent: EndRoomsIntent(),
                    phrases: ["Raummodus beenden mit \(.applicationName)", "\(.applicationName) Raummodus beenden"],
                    shortTitle: "Raum-Modus beenden",
                    systemImageName: "ear")
    }
}

enum NotausScope: String, AppEnum {
    case mine, whole
    static var typeDisplayRepresentation: TypeDisplayRepresentation = "Notaus"
    static var caseDisplayRepresentations: [NotausScope: DisplayRepresentation] = [
        .mine: "Mein Notaus", .whole: "Ganzer Spark"]
}

/// "Spark Notaus": after a question Siri stops the own profile ("Mein Notaus"); in the app's admin mode it
/// asks first whether the whole Spark should stop (stage 2). Lifting is never possible here.
struct NotausIntent: AppIntent {
    static var title: LocalizedStringResource = "Spark Notaus"
    static var description = IntentDescription("Hält nach einer Rückfrage dein Profil an, als Admin auf Wunsch den ganzen Spark. Aufheben nur im Browser.")
    static var openAppWhenRun = false

    @Parameter(title: "Was")
    var scope: NotausScope?

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard SparkAPI.current != nil else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        let admin = AdminSession.shared.signedIn
        var what = scope ?? .mine
        if admin && scope == nil {
            let picked = try await $scope.requestValue(IntentDialog("Ganzer Spark oder nur dein Profil?"))
            what = picked ?? .mine
        }
        if what == .whole && !admin {
            throw SparkError(message: String(localized: "Den ganzen Spark hält nur ein Admin an. Erst unter Spark verwalten anmelden."))
        }
        if what == .whole {
            try await requestConfirmation(result: .result(dialog: "Den ganzen Spark auf Stufe 2 „Hände weg“ stellen? Aufheben nur als Admin im Browser im Heimnetz."))
            try await Notaus.whole()
            return .result(dialog: "Notaus Stufe 2 ist an.")
        }
        try await requestConfirmation(result: .result(dialog: "Dein Profil anhalten? Aufheben nur im Browser mit deiner PIN."))
        try await Notaus.mine()
        return .result(dialog: "Mein Notaus ist an.")
    }
}
