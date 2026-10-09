import Contacts
import Foundation
import UIKit
import UserNotifications

/// The app's own choices (on this iPhone). What the profile allows comes from the Spark (Allowed).
enum Prefs {
    private static let d = UserDefaults.standard
    static var handsFree: Bool { get { d.bool(forKey: "handsFree") } set { d.set(newValue, forKey: "handsFree") } }
    static var bargeIn: Bool { get { d.object(forKey: "bargeIn") as? Bool ?? true } set { d.set(newValue, forKey: "bargeIn") } }
    static var wake: Bool { get { d.bool(forKey: "wake") } set { d.set(newValue, forKey: "wake") } }
    static var wakeWord: WakeWord.Word {
        get { WakeWord.Word(rawValue: d.string(forKey: "wakeWord") ?? "") ?? .spark }
        set { d.set(newValue.rawValue, forKey: "wakeWord") }
    }
    static var stand: Bool { get { d.bool(forKey: "stand") } set { d.set(newValue, forKey: "stand") } }
    /// minutes the wake word keeps listening on battery (0 = only on the charger)
    static var batteryMinutes: Int { get { d.object(forKey: "batteryMinutes") as? Int ?? 30 } set { d.set(newValue, forKey: "batteryMinutes") } }
    static var speakNotes: Bool { get { d.object(forKey: "speakNotes") as? Bool ?? true } set { d.set(newValue, forKey: "speakNotes") } }
}

/// Timers and reminders the Spark set for this profile ring on the iPhone as notifications.
enum Alarms {
    private static let prefix = "spark-rem-"

    static func allow() async -> Bool {
        (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    static func add(_ r: Reminder) async {
        guard r.due > Date(), await allow() else { return }
        let c = UNMutableNotificationContent()
        c.title = "Spark"
        c.body = r.text
        c.sound = .default
        c.interruptionLevel = .timeSensitive
        c.userInfo = ["spark": r.text]
        let secs = max(1, r.due.timeIntervalSinceNow)
        let req = UNNotificationRequest(identifier: prefix + r.id, content: c,
                                        trigger: UNTimeIntervalNotificationTrigger(timeInterval: secs, repeats: false))
        try? await UNUserNotificationCenter.current().add(req)
    }

    static func remove(_ ids: [String]) {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ids.map { prefix + $0 })
    }

    /// The iPhone holds exactly the reminders the Spark has (set in the panel or another device too).
    static func sync(_ list: [Reminder]) async {
        let center = UNUserNotificationCenter.current()
        let pending = await center.pendingNotificationRequests().map(\.identifier).filter { $0.hasPrefix(prefix) }
        let want = Set(list.map { prefix + $0.id })
        center.removePendingNotificationRequests(withIdentifiers: pending.filter { !want.contains($0) })
        for r in list where !pending.contains(prefix + r.id) { await add(r) }
    }
}

/// What only the iPhone can do. The Spark only suggests; the app asks every time before it starts.
enum PhoneAction {
    struct Offer: Identifiable {
        let id = UUID()
        let question: String
        let url: URL
    }

    static func offer(kind: String, target: String) async -> (Offer?, String?) {
        switch kind {
        case "navigate":
            var c = URLComponents(string: "maps://")!
            c.queryItems = [URLQueryItem(name: "daddr", value: target)]
            guard let url = c.url else { return (nil, String(localized: "Das Ziel verstehe ich nicht.")) }
            return (Offer(question: String(localized: "Route nach „\(target)“ in Karten öffnen?"), url: url), nil)
        case "call":
            return await call(target)
        default:
            return (nil, nil)
        }
    }

    private static func call(_ name: String) async -> (Offer?, String?) {
        let store = CNContactStore()
        guard (try? await store.requestAccess(for: .contacts)) == true else {
            return (nil, String(localized: "Die App darf deine Kontakte nicht lesen. Einstellungen → Spark → Kontakte."))
        }
        let keys = [CNContactGivenNameKey, CNContactFamilyNameKey, CNContactPhoneNumbersKey] as [CNKeyDescriptor]
        let found = (try? store.unifiedContacts(matching: CNContact.predicateForContacts(matchingName: name), keysToFetch: keys)) ?? []
        let withPhone = found.filter { !$0.phoneNumbers.isEmpty }
        guard withPhone.count == 1, let contact = withPhone.first, let number = contact.phoneNumbers.first?.value.stringValue else {
            return (nil, withPhone.isEmpty ? String(localized: "Ich finde keinen Kontakt „\(name)“ mit Telefonnummer.")
                                           : String(localized: "Es gibt mehrere Kontakte „\(name)“. Sag bitte den ganzen Namen."))
        }
        let digits = number.filter { "+0123456789".contains($0) }
        guard !digits.isEmpty, let url = URL(string: "tel://" + digits) else { return (nil, String(localized: "Die Nummer verstehe ich nicht.")) }
        let who = [contact.givenName, contact.familyName].filter { !$0.isEmpty }.joined(separator: " ")
        return (Offer(question: String(localized: "\(who) anrufen (\(number))?"), url: url), nil)
    }

    @MainActor
    static func run(_ offer: Offer) {
        UIApplication.shared.open(offer.url)
    }
}
