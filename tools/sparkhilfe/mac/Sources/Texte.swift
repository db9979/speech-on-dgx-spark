import Foundation

/// Alle Texte des Programms, deutsch und englisch (nach der ersten Sprache des Macs). Platzhalter: {0} der Name des
/// Helfers, {1} die Adresse des Sparks; nie etwas anderes von außen.
enum Texte {
    private static let all: [String: (de: String, en: String)] = [
        "fenster": ("SparkHilfe", "SparkHilfe"),
        "verbinde": ("Verbinde mit {1} …", "Connecting to {1} …"),
        "name_falsch": ("Dieses Programm gehört zu keiner Hilfe. Bitte laden Sie es auf der Hilfe-Seite neu.",
                        "This program belongs to no help. Please load it again on the help page."),
        "neu_laden": ("Dieses Programm ist abgelaufen oder schon benutzt. Bitte laden Sie es auf der Hilfe-Seite neu.",
                      "This program has expired or was used already. Please load it again on the help page."),
        "keine_verbindung": ("Keine Verbindung zu {1}. Bitte prüfen Sie das Internet und laden Sie das Programm auf der Hilfe-Seite neu.",
                             "No connection to {1}. Please check the internet and load the program again on the help page."),
        "schritt1": ("Schritt 1 von 2: Bildschirmaufnahme", "Step 1 of 2: Screen Recording"),
        "fehlt_bild": ("Es fehlt die Freigabe „Bildschirmaufnahme“: in den Systemeinstellungen unter Datenschutz & Sicherheit SparkHilfe einschalten und das Programm danach neu öffnen.",
                       "The permission “Screen Recording” is missing: turn on SparkHilfe in System Settings under Privacy & Security and open the program again afterwards."),
        "schritt2": ("Schritt 2 von 2: Bedienungshilfen", "Step 2 of 2: Accessibility"),
        "fehlt_bedienen": ("Zum Steuern fehlt die Freigabe „Bedienungshilfen“: in den Systemeinstellungen unter Datenschutz & Sicherheit SparkHilfe einschalten; ohne sie geht nur Ansehen.",
                           "To be controlled, the permission “Accessibility” is missing: turn on SparkHilfe in System Settings under Privacy & Security; without it only viewing works."),
        "einstellungen": ("Einstellungen öffnen", "Open Settings"),
        "ohne": ("Ohne weiter (nur ansehen)", "Go on without (view only)"),
        "nur_ansehen_jetzt": ("Steuern geht erst mit der Freigabe „Bedienungshilfen“; jetzt nur ansehen.",
                              "Control needs the permission “Accessibility”; view only for now."),
        "frage": ("{0} ({1}) möchte Ihren Mac steuern.", "{0} ({1}) would like to control your Mac."),
        "frage_mehr": ("Nur, wenn Sie gerade selbst um Hilfe gebeten haben. Solange es läuft, sehen Sie einen roten Rahmen und oben „Beenden“. Passwörter und Fenster mit Schloss geben Sie selbst ein. Es wird nichts aufgezeichnet.",
                       "Only if you asked for help just now. While it runs you see a red frame and “End” at the top. Passwords and windows with a lock you enter yourself. Nothing is recorded."),
        "ablehnen": ("Ablehnen", "Decline"),
        "ansehen": ("Nur ansehen", "View only"),
        "erlauben": ("Erlauben", "Allow"),
        "countdown": ("Ohne Antwort gilt in {0} s „Ablehnen“.", "Without an answer, “Decline” applies in {0} s."),
        "leiste_ansehen": ("{0} sieht Ihren Bildschirm", "{0} sees your screen"),
        "leiste_erlaubt": ("{0} sieht Ihren Bildschirm · Steuern erlaubt", "{0} sees your screen · control allowed"),
        "leiste_aktiv": ("Steuerung aktiv · {0}", "Control active · {0}"),
        "beenden": ("Beenden", "End"),
        "schliessen": ("Schließen", "Close"),
        "abgelehnt": ("Abgelehnt. Niemand steuert Ihren Mac.", "Declined. Nobody controls your Mac."),
        "beendet": ("Die Hilfe ist beendet. Sie können dieses Fenster schließen.", "The help has ended. You can close this window."),
        "laeuft_schon": ("SparkHilfe läuft bereits.", "SparkHilfe is already running."),
    ]

    /// Deutsch, wenn der Mac zuerst deutsch spricht; sonst englisch.
    static let german = (Locale.preferredLanguages.first ?? "de").lowercased().hasPrefix("de")

    static func t(_ key: String, helper: String = "", host: String = "") -> String {
        raw(key).replacingOccurrences(of: "{1}", with: host).replacingOccurrences(of: "{0}", with: helper)
    }

    /// der Text mit „{0}“ als Platzhalter für eine Zahl (Countdown)
    static func raw(_ key: String) -> String {
        guard let p = all[key] else { return key }
        return german ? p.de : p.en
    }

    /// for the self-test: every key with both languages
    static var keys: [String] { Array(all.keys) }
    static func pair(_ key: String) -> (de: String, en: String)? { all[key] }
}
