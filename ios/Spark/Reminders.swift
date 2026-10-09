import EventKit
import Foundation

/// Apple's Reminders app (only with the profile's app_ios switch and the iPhone's permission).
/// A Spark reminder goes there after "Ja", as an entry in the list "Spark" without its own alarm
/// (the Spark rings already, so nothing rings twice). New entries of the Spark's shopping and to-do
/// lists come into "Einkauf" and "Aufgaben". Nothing from Reminders goes to the Spark.
@MainActor
enum AppleReminders {
    private static let store = EKEventStore()
    private static let mapKey = "apple-reminders"     // Spark reminder id -> Apple's item id
    static let maxPerSync = 50

    static func allow() async -> Bool {
        if EKEventStore.authorizationStatus(for: .reminder) == .fullAccess { return true }
        return (try? await store.requestFullAccessToReminders()) ?? false
    }

    /// The list with this title, made once in the default account.
    private static func list(_ title: String) throws -> EKCalendar {
        if let c = store.calendars(for: .reminder).first(where: { $0.title == title && $0.allowsContentModifications }) {
            return c
        }
        let c = EKCalendar(for: .reminder, eventStore: store)
        c.title = title
        guard let source = store.defaultCalendarForNewReminders()?.source ?? store.sources.first(where: { $0.sourceType == .local }) else {
            throw SparkError(message: String(localized: "Die Erinnerungen-App hat kein Konto für neue Listen."))
        }
        c.source = source
        try store.saveCalendar(c, commit: true)
        return c
    }

    private static func add(_ title: String, due: Date?, to listTitle: String) throws -> String {
        let r = EKReminder(eventStore: store)
        r.title = String(title.prefix(300))
        r.calendar = try list(listTitle)
        if let due {
            r.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: due)
        }
        try store.save(r, commit: true)
        return r.calendarItemIdentifier
    }

    /// A Spark reminder, after "Ja".
    static func add(_ r: Reminder) async throws {
        guard await allow() else {
            throw SparkError(message: String(localized: "Die App darf nicht in Erinnerungen schreiben. Einstellungen → Spark → Erinnerungen."))
        }
        let id = try add(r.text, due: r.due, to: "Spark")
        var map = UserDefaults.standard.dictionary(forKey: mapKey) as? [String: String] ?? [:]
        map[r.id] = id
        UserDefaults.standard.set(Dictionary(uniqueKeysWithValues: map.suffix(200).map { ($0.key, $0.value) }), forKey: mapKey)
    }

    /// The Spark cancelled reminders: take out the ones this app put into Reminders.
    static func remove(_ ids: [String]) {
        var map = UserDefaults.standard.dictionary(forKey: mapKey) as? [String: String] ?? [:]
        guard EKEventStore.authorizationStatus(for: .reminder) == .fullAccess else { return }
        for id in ids {
            if let item = map.removeValue(forKey: id), let r = store.calendarItem(withIdentifier: item) as? EKReminder, !r.isCompleted {
                try? store.remove(r, commit: true)
            }
        }
        UserDefaults.standard.set(map, forKey: mapKey)
    }

    /// New entries of the Spark's lists into Reminders. Asks the Spark only with the permission,
    /// because the Spark hands each entry over once.
    static func syncLists() async {
        let ok = await allow()
        guard ok, let api = SparkAPI.current else { return }
        for (key, title) in [("einkauf", String(localized: "Einkauf")), ("aufgaben", String(localized: "Aufgaben"))] {
            guard let items = try? await api.takeList(key) else { continue }
            for text in items.prefix(maxPerSync) { _ = try? add(text, due: nil, to: title) }
        }
    }

    static func forget() { UserDefaults.standard.removeObject(forKey: mapKey) }
}
