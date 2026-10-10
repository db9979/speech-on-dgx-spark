import SwiftUI

/// "Mein Zustand" (hintergrund.py): what the Spark does in the background for this profile and whether its
/// connected services answer. Read only in the app; the actions stay in the panel. Off (403) or not reachable:
/// the page shows nothing, never a text from the server.
struct BgRow: Identifiable {
    let id: String
    let area: String
    let name: String
    let state: String
    let tag: String?
    let detail: String
    let label: String
    let done: Int
    let total: Int
    let last: Date?
    let next: Date?
}

struct BgSum {
    var run = 0, wait = 0, ok = 0, bad = 0, idle = 0, need = 0
}

extension SparkAPI {
    /// [de, en] from the Spark in the app's language (the same rule as FeaturesView.pick)
    static func pickWord(_ x: Any?, max: Int = 200) -> String? {
        guard let a = x as? [String], a.count == 2 else { return nil }
        return String(a[(Locale.preferredLanguages.first?.hasPrefix("en") ?? false) ? 1 : 0].prefix(max))
    }

    /// /api/features: whether this profile may use a function (Spark and own switch on)
    func can(_ key: String) async -> Bool {
        guard let d = try? await object("GET", "api/features"), let list = d["features"] as? [[String: Any]] else { return false }
        return list.prefix(200).contains { $0["key"] as? String == key && $0["can"] as? Bool == true }
    }

    func background() async throws -> (rows: [BgRow], sum: BgSum, now: Date?) {
        let d = try await object("GET", "api/profile/hintergrund")
        let states: Set<String> = ["run", "wait", "ok", "bad", "idle"]
        let int: (Any?) -> Int? = { ($0 as? NSNumber)?.intValue }
        let date: (Any?) -> Date? = { x in
            guard let t = int(x), t > 0 else { return nil }
            return Date(timeIntervalSince1970: TimeInterval(t))
        }
        var seen: [String: Int] = [:]
        let rows = (d["rows"] as? [[String: Any]] ?? []).prefix(200).compactMap { r -> BgRow? in
            guard let key = r["key"] as? String, let area = r["area"] as? String, ["jobs", "services"].contains(area),
                  let state = r["state"] as? String, states.contains(state) else { return nil }
            let label = String((r["label"] as? String ?? "").prefix(80))
            // the same key can come twice with different labels: keep the ids apart for the list
            let base = key + "|" + label
            seen[base, default: 0] += 1
            return BgRow(id: base + "|" + String(seen[base] ?? 0), area: area, name: Self.pickWord(r["name"], max: 80) ?? key,
                         state: state, tag: Self.pickWord(r["why_text"], max: 80), detail: Self.pickWord(r["detail"]) ?? "",
                         label: label, done: int(r["done"]) ?? 0, total: int(r["total"]) ?? 0,
                         last: date(r["last"]), next: date(r["next"]))
        }
        let s = d["sum"] as? [String: Any] ?? [:]
        let sum = BgSum(run: int(s["run"]) ?? 0, wait: int(s["wait"]) ?? 0, ok: int(s["ok"]) ?? 0,
                        bad: int(s["bad"]) ?? 0, idle: int(s["idle"]) ?? 0, need: int(s["need"]) ?? 0)
        return (rows, sum, date(d["now"]))
    }
}

@MainActor
final class MyStatusModel: ObservableObject {
    @Published var rows: [BgRow] = []
    @Published var sum = BgSum()
    @Published var now: Date?
    @Published var loaded = false

    /// errors (also 403 when the function is off) keep what is shown; nothing from the server is shown as text
    func load() async {
        guard let api = SparkAPI.current, let r = try? await api.background() else { return }
        rows = r.rows
        sum = r.sum
        now = r.now
        loaded = true
    }
}

struct MyStatusView: View {
    @StateObject private var m = MyStatusModel()

    var body: some View {
        List {
            if m.loaded {
                Section {
                    HStack(alignment: .top, spacing: 10) {
                        dot(headState).padding(.top, 6)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: head).font(.headline)
                            let sub = summary
                            if !sub.isEmpty { Text(verbatim: sub).font(.caption).foregroundStyle(.secondary) }
                        }
                    }
                }
                let jobs = m.rows.filter { $0.area == "jobs" }
                if !jobs.isEmpty {
                    Section { ForEach(jobs) { row($0) } } header: { Text("Im Hintergrund") }
                }
                let services = m.rows.filter { $0.area == "services" }
                if !services.isEmpty {
                    Section { ForEach(services) { row($0) } } header: { Text("Verbunden") } footer: {
                        Text("Nur was bei dir an und verbunden ist. Inhalte von Mails und Dokumenten stehen hier nie.")
                    }
                }
            }
        }
        .navigationTitle("Mein Zustand")
        .refreshable { await m.load() }
        .task {
            // while the page is open it follows the work every 10 seconds (the task ends when it closes)
            await m.load()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000)
                if Task.isCancelled { break }
                await m.load()
            }
        }
    }

    private var headState: String {
        m.rows.contains { $0.state == "bad" } ? "bad" : m.sum.run > 0 ? "run" : m.rows.isEmpty ? "idle" : "ok"
    }

    private var head: String {
        let need = m.rows.filter { $0.state == "bad" }
        if need.count == 1 { return String(localized: "\(need[0].name) braucht dich") }
        if need.count > 1 { return String(localized: "\(need.count) Dinge brauchen dich") }
        if m.sum.run > 0 { return String(localized: "Der Spark arbeitet für dich.") }
        if !m.rows.isEmpty { return String(localized: "Alles in Ordnung.") }
        return String(localized: "Für dich läuft nichts im Hintergrund.")
    }

    private var summary: String {
        var p: [String] = []
        let s = m.sum
        if s.bad > 0 { p.append(String(localized: "\(s.bad) gestört")) }
        if s.run > 0 { p.append(String(localized: "\(s.run) läuft")) }
        if s.wait > 0 { p.append(String(localized: "\(s.wait) wartet")) }
        if s.ok > 0 { p.append(String(localized: "\(s.ok) in Ordnung")) }
        if let now = m.now { p.append(String(localized: "Stand \(Self.when(now))")) }
        return p.joined(separator: " · ")
    }

    private func row(_ r: BgRow) -> some View {
        HStack(alignment: .top, spacing: 10) {
            dot(r.state).padding(.top, 6)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(verbatim: r.name)
                    Text(verbatim: r.tag ?? Self.word(r.state))
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(Self.color(r.state).opacity(0.15), in: Capsule())
                        .foregroundStyle(Self.color(r.state))
                }
                let line = Self.line(r)
                if !line.isEmpty { Text(verbatim: line).font(.caption).foregroundStyle(.secondary) }
                if r.total > 0 {
                    ProgressView(value: Double(min(max(r.done, 0), r.total)), total: Double(r.total))
                }
            }
        }
    }

    private func dot(_ state: String) -> some View {
        Circle().fill(Self.color(state)).frame(width: 10, height: 10)
    }

    static func color(_ state: String) -> Color {
        switch state {
        case "run": return .teal
        case "wait": return .orange
        case "ok": return .green
        case "bad": return .red
        default: return .gray
        }
    }

    static func word(_ state: String) -> String {
        switch state {
        case "run": return String(localized: "läuft")
        case "wait": return String(localized: "wartet")
        case "ok": return String(localized: "in Ordnung")
        case "bad": return String(localized: "braucht dich")
        default: return String(localized: "noch nichts")
        }
    }

    /// „label“ · detail · zuletzt … · nächstes Mal …
    static func line(_ r: BgRow) -> String {
        var p: [String] = []
        if !r.label.isEmpty { p.append("„" + r.label + "“") }
        if !r.detail.isEmpty { p.append(r.detail) }
        if let t = r.last { p.append(String(localized: "zuletzt \(when(t))")) }
        if let t = r.next { p.append(String(localized: "nächstes Mal \(when(t))")) }
        return p.joined(separator: " · ")
    }

    /// today: the time only, otherwise weekday and time
    static func when(_ d: Date) -> String {
        Calendar.current.isDateInToday(d) ? d.formatted(date: .omitted, time: .shortened)
                                           : d.formatted(.dateTime.weekday(.abbreviated).hour().minute())
    }
}
