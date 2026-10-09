import ActivityKit
import AppIntents
import Foundation
import WidgetKit

/// The Live Activity on the lock screen (and in the Dynamic Island) while a device of the profile is in
/// room mode: only where and until when, never what was heard. The app starts, updates and ends it
/// itself while it runs (no push); after the end time it shows "vorbei" until the app looks again.
/// Compiled into the app and the widget extension (folder Rooms).
struct RoomActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var names: [String]     // at most 4
        var count: Int
        var until: Date
    }
}

/// "Beenden" on the Live Activity and the widget, and "Raummodus beenden mit Spark" for Siri:
/// ends room mode on all devices of the profile. Only ending, never starting (the app key may not start).
struct EndRoomsIntent: LiveActivityIntent {
    static var title: LocalizedStringResource = "Raum-Modus beenden"
    static var description = IntentDescription("Beendet den Raum-Modus an allen Geräten deines Profils.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let api = SparkAPI.current else {
            throw SparkError(message: String(localized: "Die App ist noch nicht mit dem Spark gekoppelt."))
        }
        try await api.endRoom()
        await RoomLive.show([])
        return .result(dialog: "Raum-Modus beendet.")
    }
}

/// Keeps the one Live Activity and the room widget in step with the list from the Spark.
enum RoomLive {
    static let widgetKind = "spark.rooms"

    static func show(_ rooms: [ListeningRoom]) async {
        let running = Activity<RoomActivityAttributes>.activities
        let now = Date()
        let live = rooms.filter { $0.until > now }
        guard let until = live.map(\.until).max() else {
            for a in running { await a.end(nil, dismissalPolicy: .immediate) }
            WidgetCenter.shared.reloadTimelines(ofKind: widgetKind)
            return
        }
        let state = RoomActivityAttributes.ContentState(names: Array(live.map(\.name).prefix(4)), count: live.count, until: until)
        let content = ActivityContent(state: state, staleDate: until)
        if let a = running.first {
            if a.content.state != state { await a.update(content) }
            for b in running.dropFirst() { await b.end(nil, dismissalPolicy: .immediate) }
        } else if ActivityAuthorizationInfo().areActivitiesEnabled {
            // only possible while the app is in front; without permission the line in the chat stays
            _ = try? Activity.request(attributes: RoomActivityAttributes(), content: content, pushType: nil)
        }
        WidgetCenter.shared.reloadTimelines(ofKind: widgetKind)
    }

    /// "Küche" or "Küche und Bad" or "3 Geräte"
    static func label(_ names: [String], count: Int? = nil) -> String {
        let n = count ?? names.count
        if n == 1, let first = names.first { return first.isEmpty ? String(localized: "Ein Gerät") : first }
        if n == 2, names.count == 2 { return String(localized: "\(names[0]) und \(names[1])") }
        return String(localized: "\(n) Geräte")
    }

    /// "Küche hört zu" or "Küche und Bad hören zu"
    static func listening(_ names: [String], count: Int? = nil) -> String {
        let who = label(names, count: count)
        return (count ?? names.count) == 1 ? String(localized: "\(who) hört zu") : String(localized: "\(who) hören zu")
    }
}
