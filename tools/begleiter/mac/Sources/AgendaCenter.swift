import AppKit
import UserNotifications

/// the identifiers of the agenda notifications
let agendaPrefix = "agenda-"

/// Part "agenda" (Termine im Begleiter): every 5 minutes GET /api/desk/agenda (next 24 h); the tray panel shows
/// "Als Nächstes"; 10 minutes before each event a notification (once per event, title + time).
/// Notes get the button "In 20 Min erinnern" (POST /api/desk/remind).
@MainActor
final class AgendaCenter: ObservableObject {
    static let shared = AgendaCenter()
    static let interval: TimeInterval = 300
    static let toldKey = "agenda.told"

    @Published private(set) var agenda = Agenda()
    @Published private(set) var problem = ""
    @Published private(set) var loaded = false

    private var timer: Timer?
    private var active = false
    private var loading = false
    private var lastLoad: Date?
    private var told: SeenIDs

    init() {
        told = SeenIDs(UserDefaults.standard.stringArray(forKey: Self.toldKey) ?? [], limit: 200)
    }

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let t = Timer(timeInterval: Self.interval, repeats: true) { _ in
                Task { @MainActor in await AgendaCenter.shared.refresh() }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            Task { await refresh() }
        } else {
            guard active else { return }
            active = false
            timer?.invalidate()
            timer = nil
            agenda = Agenda()
            loaded = false
            problem = ""
            removePending(keep: [])
        }
    }

    /// the tray panel opened: fresh when the last load is older than a minute
    func refreshSoon() {
        guard active else { return }
        if let l = lastLoad, Date().timeIntervalSince(l) < 60 { return }
        Task { await refresh() }
    }

    func refresh() async {
        guard active, !loading, let client = AppModel.shared.client, AppModel.shared.part("agenda") else { return }
        loading = true
        defer { loading = false }
        do {
            let a = try await client.agenda()
            guard active else { return }
            agenda = a
            loaded = true
            problem = ""
            lastLoad = Date()
            schedule(a)
        } catch is CancellationError {
        } catch {
            problem = AppModel.shared.absorb(error)
        }
    }

    // ------------------------------------------------------------------ the notifications 10 min before

    private func schedule(_ a: Agenda) {
        let now = Date()
        var keep: Set<String> = []
        for e in a.events {
            guard let when = Agenda.alert(for: e, now: now) else { continue }
            let id = agendaPrefix + e.id
            guard !told.contains(e.id) else { continue }
            let c = UNMutableNotificationContent()
            c.title = e.title
            c.body = "Um " + IsoDate.short(e.start, now: now) + (e.place.isEmpty ? "" : " · " + e.place)
            c.sound = .default
            c.threadIdentifier = "agenda"
            switch when {
            case .at(let date):
                keep.insert(id)
                let trigger = UNTimeIntervalNotificationTrigger(timeInterval: max(1, date.timeIntervalSince(now)), repeats: false)
                UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: id, content: c, trigger: trigger)) { _ in }
            case .now:
                markTold(e.id)
                UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: id, content: c, trigger: nil)) { _ in }
            }
        }
        removePending(keep: keep)
        // what has been delivered by now counts as told (so a later refresh does not tell again)
        UNUserNotificationCenter.current().getDeliveredNotifications { list in
            let ids = list.map { $0.request.identifier }.filter { $0.hasPrefix(agendaPrefix) }
            Task { @MainActor in
                for id in ids { AgendaCenter.shared.markTold(String(id.dropFirst(agendaPrefix.count))) }
            }
        }
    }

    private func markTold(_ id: String) {
        guard !told.contains(id) else { return }
        told.add(id)
        UserDefaults.standard.set(told.list, forKey: Self.toldKey)
    }

    /// pending agenda notifications that no longer belong to an event go
    private func removePending(keep: Set<String>) {
        UNUserNotificationCenter.current().getPendingNotificationRequests { list in
            let gone = list.map { $0.identifier }.filter { $0.hasPrefix(agendaPrefix) && !keep.contains($0) }
            if !gone.isEmpty {
                UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: gone)
            }
        }
    }

    // ------------------------------------------------------------------ "In 20 Min erinnern"

    func remind(note: Int?, text: String?, minutes: Int = Remind.defaultMinutes) {
        guard AppModel.shared.part("agenda") else { return HUD.show(AppModel.offHint("Termine im Begleiter")) }
        guard let client = AppModel.shared.client else { return }
        Task { @MainActor in
            do {
                let due = try await client.remind(note: note, text: note == nil ? text : nil, minutes: minutes)
                let when = due.map { IsoDate.short($0) } ?? "in \(minutes) Minuten"
                Notifier.plain(title: "Spark", body: "Erinnerung kommt " + (due == nil ? when : "um " + when) + ".")
                await self.refresh()
            } catch {
                Notifier.plain(title: "Spark", body: AppModel.shared.absorb(error))
            }
        }
    }
}
