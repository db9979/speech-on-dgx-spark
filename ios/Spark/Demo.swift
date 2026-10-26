import Foundation

/// Example screens for the App Store pictures (workflow "App Store screenshots"), and the demo "Ohne Spark ansehen"
/// on the pairing screen (scene "live"): for Apple's review and anyone without a Spark yet. The pictures need a Debug
/// build and the launch argument `-SparkDemo <scene>`. Nothing goes to a Spark: no pairing, no network (the app is not
/// paired, so it has no key and no address), made-up example content, typed questions answered here (answer).
enum Demo {
    /// chat, photo, remind, profile, history; "live" while the demo runs
    static var scene: String? { launch ?? (live ? "live" : nil) }

    private static let launch: String? = {
        #if DEBUG
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-SparkDemo"), i + 1 < a.count { return a[i + 1] }
        #endif
        return nil
    }()

    /// "Ohne Spark ansehen" is running (AppState.startDemo / endDemo)
    static var live = false

    private static var en: Bool { Locale.preferredLanguages.first?.hasPrefix("en") ?? false }
    private static func t(_ de: String, _ en: String) -> String { Self.en ? en : de }

    /// the mouth moves on the speaking picture
    static var out: Float? { scene == "chat" ? 0.45 : nil }

    @MainActor
    static func fill(_ c: Conversation, _ scene: String) {
        var a = Allowed()
        a.profile = t("Anna", "Anna")
        a.listen = true
        a.act = true
        a.proactive = true
        a.docs = true
        a.ios = true
        c.allowed = a
        c.unreachable = false
        func say(_ role: String, _ text: String, label: String? = nil) {
            c.messages.append(.init(role: role, text: text, label: label))
        }
        switch scene {
        case "photo":
            let name = t("Brief.jpg", "Letter.jpg")
            c.attachment = Attachment(kind: "photo", name: name, text: String(repeating: "x", count: 1184))
            say("user", t("Was will die Versicherung von mir?", "What does the insurance want from me?"), label: "📷 " + name)
            say("assistant", t("Die Versicherung braucht bis zum 31. Oktober den aktuellen Kilometerstand deines Autos. Du kannst ihn online melden oder die beiliegende Karte zurückschicken. An deinem Beitrag ändert sich sonst nichts.",
                               "The insurance needs your car's current mileage by 31 October. You can report it online or send back the enclosed card. Nothing else changes about your premium."))
            say("user", t("Erinner mich am Wochenende daran.", "Remind me at the weekend."))
            say("assistant", t("Mach ich: Samstag um 10 Uhr, Kilometerstand an die Versicherung melden.",
                               "Will do: Saturday at 10 am, report the mileage to the insurance."))
        case "remind":
            say("user", t("Erinner mich morgen um 8 an den Müll.", "Remind me about the bins tomorrow at 8."))
            say("assistant", t("Mach ich: morgen um 8 Uhr, Müll rausbringen.", "Will do: tomorrow at 8 am, take out the bins."))
            let due = Calendar.current.date(byAdding: .day, value: 1, to: Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date()) ?? Date()
            c.offer = PhoneAction.remindOffer(Reminder(id: "demo", text: t("Müll rausbringen", "Take out the bins"), due: due))
        case "profile", "history":
            say("user", t("Wie wird das Wetter morgen?", "What's the weather like tomorrow?"))
            say("assistant", t("Morgen wird es sonnig und bis 19 Grad warm.", "Tomorrow will be sunny, up to 19 degrees."))
        case "live":
            say("assistant", t("Das ist eine Vorführung ohne Spark. Ich zeige dir mit Beispielen, wie die App aussieht; nichts verlässt dieses iPhone. Schreib mir etwas, zum Beispiel „Wie wird das Wetter?“ oder „Was kannst du?“.",
                               "This is a demo without a Spark. I show you with examples what the app looks like; nothing leaves this iPhone. Write me something, for example \"What's the weather like?\" or \"What can you do?\"."))
            say("user", t("Wie wird das Wetter morgen?", "What's the weather like tomorrow?"))
            say("assistant", t("Morgen wird es sonnig und bis 19 Grad warm. (Beispiel)", "Tomorrow will be sunny, up to 19 degrees. (Example)"))
            c.phase = .idle
        default:
            say("user", t("Wie wird das Wetter morgen?", "What's the weather like tomorrow?"))
            say("assistant", t("Morgen wird es sonnig und bis 19 Grad warm. Am Nachmittag frischt der Wind auf, für den Abend reicht eine leichte Jacke.",
                               "Tomorrow will be sunny, up to 19 degrees. The wind picks up in the afternoon, so a light jacket is enough for the evening."))
            say("user", t("Und was steht morgen an?", "And what's on tomorrow?"))
            say("assistant", t("Um 9 Uhr der Zahnarzt, um 14 Uhr das Telefonat mit dem Steuerbüro. Abends ist nichts eingetragen.",
                               "The dentist at 9, the call with the tax office at 2 pm. Nothing in the evening."))
            c.phase = .speaking
        }
    }

    /// The demo's answer to a typed question: a fixed example, never a model and never the network.
    static func answer(_ text: String) -> String {
        let q = text.lowercased()
        func has(_ words: String...) -> Bool { words.contains { q.contains($0) } }
        if has("wetter", "weather", "regen", "rain") {
            return t("Morgen wird es sonnig und bis 19 Grad warm, am Abend frischt der Wind auf. (Beispiel)",
                     "Tomorrow will be sunny, up to 19 degrees, the wind picks up in the evening. (Example)")
        }
        if has("erinner", "remind", "timer", "wecker") {
            return t("Mit deinem Spark stelle ich Timer und Erinnerungen, auch auf dem Sperrbildschirm und in CarPlay. (Beispiel)",
                     "With your Spark I set timers and reminders, also on the lock screen and in CarPlay. (Example)")
        }
        if has("kannst", "can you", "hilfe", "help", "was ist", "what is") {
            return t("Mit deinem eigenen Spark beantworte ich Fragen per Sprache und Text, lese Fotos und Dokumente, erinnere dich und spreche im Auto mit dir. Alles läuft bei dir zu Hause, nicht in einer Cloud.",
                     "With your own Spark I answer questions by voice and text, read photos and documents, remind you and talk to you in the car. Everything runs at your home, not in a cloud.")
        }
        return t("In der Vorführung antworte ich nur mit Beispielen. Mit deinem eigenen Spark beantworte ich hier jede Frage.",
                 "In the demo I only answer with examples. With your own Spark I answer any question here.")
    }

    /// "Mein Profil" as /api/iphone/settings would bring it
    static var profile: [String: Any]? {
        guard scene != nil else { return nil }
        return [
            "settings": ["voice": "Clara", "speed": 1.0, "length": "normal",
                         "pro_on": true, "pro_quiet": "22:00-07:00", "pro_max": 6, "pro_events": true, "pro_lead": 20,
                         "pro_weather": true, "pro_place": "Freiburg", "pro_weather_at": "18:00", "pro_parcel": true,
                         "pro_bday": true, "pro_transit": false, "pro_greet": true, "pro_mail": false, "pro_mail_not": "", "briefing_at": "07:00"] as [String: Any],
            "style": t("Freundlich und eher kurz", "Friendly and rather brief"),
            "rights": ["app_ha": true, "app_car_ha": false, "app_act": true, "app_listen": true, "app_push": true],
            "services": ["wx_on": true, "par_on": true, "con_on": true, "transit_on": false],
            "allow": ["proactive": true],
        ]
    }

    static let voices = ["Clara", "Jonas", "Mira", "Theo"]

    static var convos: [SavedConvo]? {
        guard scene != nil else { return nil }
        let titles = [
            t("Wetter fürs Wochenende", "Weather for the weekend"),
            t("Brief der Versicherung", "Letter from the insurance"),
            t("Rezept für Linsensuppe", "Lentil soup recipe"),
            t("Zug nach München am Freitag", "Train to Munich on Friday"),
            t("Geschenkidee für Oma", "Gift idea for grandma"),
            t("Was heißt „Mahnbescheid“?", "What is a payment order?"),
            t("Licht im Wohnzimmer", "Living room lights"),
            t("Einkaufsliste fürs Grillen", "Shopping list for the barbecue"),
        ]
        // daytime hours over the last days (days back, hour, minute)
        let when = [(0, 8, 12), (1, 19, 45), (1, 12, 30), (2, 17, 5), (3, 20, 15), (4, 9, 40), (5, 18, 50), (6, 11, 20)]
        let cal = Calendar.current
        return titles.enumerated().map { i, title in
            let (d, h, m) = when[i]
            let day = cal.date(byAdding: .day, value: -d, to: Date()) ?? Date()
            let t = cal.date(bySettingHour: h, minute: m, second: 0, of: day) ?? day
            return SavedConvo(id: "demo\(i)", title: title, updated: t, msgs: [])
        }
    }
}
