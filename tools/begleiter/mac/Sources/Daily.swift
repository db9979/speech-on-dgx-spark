import AppKit

/// Part "daily" (Tagesstart und Feierabend): the morning text on the first wake/unlock (or start) of the day after
/// a local time (default 06:00), the evening text on locking the screen after a local time (default 17:30), each
/// once a day: GET /api/desk/daily?kind=morning|evening, shown as notification and in the window of "Frag Spark".
/// The switches and times live on this Mac only.
@MainActor
final class Daily: ObservableObject {
    static let shared = Daily()

    static let morningOnKey = "daily.morning.on"
    static let eveningOnKey = "daily.evening.on"
    static let morningTimeKey = "daily.morning.minutes"
    static let eveningTimeKey = "daily.evening.minutes"
    static let morningLastKey = "daily.morning.last"
    static let eveningLastKey = "daily.evening.last"

    @Published var morningOn: Bool { didSet { UserDefaults.standard.set(morningOn, forKey: Self.morningOnKey) } }
    @Published var eveningOn: Bool { didSet { UserDefaults.standard.set(eveningOn, forKey: Self.eveningOnKey) } }
    @Published var morningMinutes: Int { didSet { UserDefaults.standard.set(morningMinutes, forKey: Self.morningTimeKey) } }
    @Published var eveningMinutes: Int { didSet { UserDefaults.standard.set(eveningMinutes, forKey: Self.eveningTimeKey) } }

    private var active = false
    private var observers: [(NotificationCenter, NSObjectProtocol)] = []
    private var fetching: Set<String> = []

    init() {
        let d = UserDefaults.standard
        morningOn = d.object(forKey: Self.morningOnKey) as? Bool ?? true
        eveningOn = d.object(forKey: Self.eveningOnKey) as? Bool ?? true
        morningMinutes = Self.clamp(d.object(forKey: Self.morningTimeKey) as? Int ?? DailyPlan.morningDefault)
        eveningMinutes = Self.clamp(d.object(forKey: Self.eveningTimeKey) as? Int ?? DailyPlan.eveningDefault)
    }

    static func clamp(_ m: Int) -> Int { min(max(m, 0), 24 * 60 - 1) }

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let ws = NSWorkspace.shared.notificationCenter
            let dn = DistributedNotificationCenter.default()
            observers.append((ws, ws.addObserver(forName: NSWorkspace.screensDidWakeNotification, object: nil, queue: .main) { _ in
                Task { @MainActor in Daily.shared.morningEvent() }
            }))
            observers.append((ws, ws.addObserver(forName: NSWorkspace.sessionDidBecomeActiveNotification, object: nil, queue: .main) { _ in
                Task { @MainActor in Daily.shared.morningEvent() }
            }))
            observers.append((dn, dn.addObserver(forName: Notification.Name("com.apple.screenIsUnlocked"), object: nil, queue: .main) { _ in
                Task { @MainActor in Daily.shared.morningEvent() }
            }))
            observers.append((dn, dn.addObserver(forName: Notification.Name("com.apple.screenIsLocked"), object: nil, queue: .main) { _ in
                Task { @MainActor in Daily.shared.eveningEvent() }
            }))
            // the program's start counts as the first start of the day
            morningEvent()
        } else {
            guard active else { return }
            active = false
            for (c, o) in observers { c.removeObserver(o) }
            observers = []
        }
    }

    private func morningEvent() {
        guard active, morningOn else { return }
        let last = UserDefaults.standard.string(forKey: Self.morningLastKey)
        guard DailyPlan.due(now: Date(), minutes: morningMinutes, lastDay: last) else { return }
        run("morning")
    }

    private func eveningEvent() {
        guard active, eveningOn else { return }
        let last = UserDefaults.standard.string(forKey: Self.eveningLastKey)
        guard DailyPlan.due(now: Date(), minutes: eveningMinutes, lastDay: last) else { return }
        run("evening")
    }

    /// also "Jetzt zeigen" in the settings (then it does not count as the day's one)
    func run(_ kind: String, manual: Bool = false) {
        guard AppModel.shared.part("daily"), let client = AppModel.shared.client, !fetching.contains(kind) else { return }
        fetching.insert(kind)
        Task { @MainActor in
            defer { self.fetching.remove(kind) }
            let title = kind == "evening" ? "Feierabend" : "Tagesstart"
            do {
                let (sent, md) = try await client.daily(kind)
                let text = sent.trimmingCharacters(in: .whitespacesAndNewlines)
                if !manual {
                    UserDefaults.standard.set(FolderLedger.dayString(Date()),
                                              forKey: kind == "evening" ? Self.eveningLastKey : Self.morningLastKey)
                }
                guard !text.isEmpty else { return }
                Notifier.plain(title: title, body: text)
                AskController.shared.run(question: title, md: md) { _ in text }
            } catch is CancellationError {
            } catch {
                let m = AppModel.shared.absorb(error)
                if manual { HUD.show(m, symbol: "exclamationmark.triangle") }
            }
        }
    }
}
