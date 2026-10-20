import AppKit

/// Part "post" (Begleiter nachziehen 1a/2a, Dominik 2026-10-20): the section "Post" of the tray panel. Every 5 minutes
/// (and when the panel opens or an important new mail came) GET /api/desk/post: unread mail and Für dich as numbers,
/// the up to 3 urgent Für-dich cards with Erledigt and Erinnern (POST /api/desk/post/act; the panel finds the card
/// itself), "E-Mail öffnen". Which new mail becomes a note the panel decides; sender and subject are only text.
@MainActor
final class PostCenter: ObservableObject {
    static let shared = PostCenter()
    static let interval: TimeInterval = 300

    @Published private(set) var post = PostBox()
    @Published private(set) var problem = ""
    @Published private(set) var loaded = false

    private var timer: Timer?
    private var active = false
    private var loading = false
    private var lastLoad: Date?

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let t = Timer(timeInterval: Self.interval, repeats: true) { _ in
                Task { @MainActor in await PostCenter.shared.refresh() }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            Task { await refresh() }
        } else {
            guard active else { return }
            active = false
            timer?.invalidate()
            timer = nil
            post = PostBox()
            loaded = false
            problem = ""
        }
    }

    /// the tray panel opened: fresh when the last load is older than a minute
    func refreshSoon() {
        guard active else { return }
        if let l = lastLoad, Date().timeIntervalSince(l) < 60 { return }
        Task { await refresh() }
    }

    func refresh() async {
        guard active, !loading, let client = AppModel.shared.client, AppModel.shared.part("post") else { return }
        loading = true
        defer { loading = false }
        do {
            let d = try await client.get("api/desk/post", timeout: 30)
            let p = PostBox(d)
            guard active else { return }
            post = p
            loaded = true
            problem = ""
            lastLoad = Date()
        } catch is CancellationError {
        } catch {
            problem = AppModel.shared.absorb(error)
        }
    }

    /// Erledigt / Erinnern on a card; the answer as a notification, then the section anew.
    func act(_ card: PostBox.Card, _ act: String) {
        guard let client = AppModel.shared.client else { return }
        Task { @MainActor in
            do {
                let d = try await client.postJSON("api/desk/post/act", ["card": card.id, "act": act], timeout: 30)
                let text = DeskConfig.plain(d["text"] as? String ?? "", max: 240)
                Notifier.plain(title: "Spark", body: text.isEmpty ? "Erledigt." : text)
            } catch {
                Notifier.plain(title: "Spark", body: AppModel.shared.absorb(error))
            }
            lastLoad = nil
            await refresh()
        }
    }
}

/// GET /api/desk/post, every value checked.
struct PostBox: Equatable {
    struct Card: Equatable, Identifiable {
        let id: String
        let title: String
        let line: String
        let acts: [String]
    }

    var unread: Int?
    var more = false
    var fuerdich: Int?
    var cards: [Card] = []
    var loading = false
    var noMail = false

    init() {}

    init(_ d: [String: Any]) {
        func count(_ v: Any?) -> Int? {
            guard let n = v as? NSNumber, n.intValue >= 0 else { return nil }
            return n.intValue
        }
        unread = count(d["unread"])
        fuerdich = count(d["fuerdich"])
        more = (d["more"] as? Bool) == true
        loading = (d["loading"] as? Bool) == true
        noMail = (d["nomail"] as? Bool) == true
        cards = (d["cards"] as? [Any] ?? []).prefix(3).compactMap { x -> Card? in
            guard let c = x as? [String: Any], let id = c["id"] as? String, !id.isEmpty, id.count <= 40 else { return nil }
            let acts = (c["acts"] as? [Any] ?? []).compactMap { $0 as? String }
            return Card(id: id, title: PlainText.line(c["title"], max: 120), line: PlainText.line(c["line"], max: 200),
                        acts: ["done", "fdremind"].filter { acts.contains($0) })
        }
    }

    /// "4 ungelesen · 2 Für dich"
    var summary: String {
        if noMail { return "Kein Postfach verbunden (E-Mail → Einstellungen)." }
        let u = unread.map { (more ? "\($0)+" : "\($0)") + " ungelesen" } ?? "Ungelesen: …"
        return fuerdich.map { "\(u) · \($0) Für dich" } ?? u
    }
}

/// Part "lists" (Begleiter nachziehen 8a): the section "Listen" of the tray panel. Every 5 minutes (and when the panel
/// opens or something was captured) GET /api/desk/lists: the lists with open entries, how many are open and what
/// came last as a fixed sentence; "Öffnen" goes to the page Listen. Entries are only text.
@MainActor
final class ListsCenter: ObservableObject {
    static let shared = ListsCenter()

    struct Row: Equatable, Identifiable {
        let id: String
        let name: String
        let icon: String
        let open: Int?
        let last: String

        var detail: String {
            (open.map { "\($0) offen" } ?? "nicht erreichbar") + (last.isEmpty ? "" : " · " + last)
        }
    }

    @Published private(set) var rows: [Row] = []
    @Published private(set) var problem = ""
    @Published private(set) var loaded = false

    private var timer: Timer?
    private var active = false
    private var loading = false
    private var lastLoad: Date?

    func apply(on: Bool) {
        if on {
            guard !active else { return }
            active = true
            let t = Timer(timeInterval: PostCenter.interval, repeats: true) { _ in
                Task { @MainActor in await ListsCenter.shared.refresh() }
            }
            RunLoop.main.add(t, forMode: .common)
            timer = t
            Task { await refresh() }
        } else {
            guard active else { return }
            active = false
            timer?.invalidate()
            timer = nil
            rows = []
            loaded = false
            problem = ""
        }
    }

    func refreshSoon() {
        guard active else { return }
        if let l = lastLoad, Date().timeIntervalSince(l) < 60 { return }
        Task { await refresh() }
    }

    func refresh() async {
        guard active, !loading, let client = AppModel.shared.client, AppModel.shared.part("lists") else { return }
        loading = true
        defer { loading = false }
        do {
            let d = try await client.get("api/desk/lists", timeout: 30)
            let r = Self.parse(d)
            guard active else { return }
            rows = r
            loaded = true
            problem = ""
            lastLoad = Date()
        } catch is CancellationError {
        } catch {
            problem = AppModel.shared.absorb(error)
        }
    }

    /// GET /api/desk/lists, every value checked: at most 6
    static func parse(_ d: [String: Any]) -> [Row] {
        (d["lists"] as? [Any] ?? []).prefix(6).compactMap { x -> Row? in
            guard let l = x as? [String: Any], let id = l["id"] as? String, !id.isEmpty, id.count <= 20 else { return nil }
            let open = (l["open"] as? NSNumber).flatMap { $0.intValue >= 0 ? $0.intValue : nil }
            return Row(id: id, name: PlainText.line(l["name"], max: 40), icon: PlainText.line(l["icon"], max: 4),
                       open: open, last: PlainText.line(l["last"], max: 120))
        }
    }
}
